"""Spatial regression of relative surface heat on urban form, per hexagon grid."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd

from sgheat.stages.context import RunContext
from sgheat.stages.features import FEATURE_DESCRIPTIONS
from sgheat.stages.grid import zone_sets
from sgheat.stats import models
from sgheat.stats.impacts import trace_powers
from sgheat.stats.weights import hex_graph, largest_component, to_w

log = logging.getLogger(__name__)
STAGE_VERSION = 1


def design(ctx: RunContext, zone_set: str) -> tuple[pd.DataFrame, list[str]]:
    """Model domain of a hexagon grid: complete cases in the largest connected component."""
    cfg = ctx.config.model
    variables = list(cfg.variables)
    feats = pd.read_parquet(ctx.paths.features(zone_set))
    temporal = pd.read_parquet(ctx.paths.temporal(zone_set))[
        ["zone_id", "alpha_model_k", "n_obs_model"]
    ]
    frame = feats.merge(temporal, on="zone_id")
    ok = np.isfinite(frame["alpha_model_k"]) & (frame["n_obs_model"] >= ctx.config.temporal.min_obs)
    for v in variables:
        ok &= np.isfinite(frame[v])
    frame = frame.loc[ok].reset_index(drop=True)
    keep = largest_component(frame["q"].to_numpy(np.int64), frame["r"].to_numpy(np.int64))
    dropped = int((~keep).sum())
    frame = frame.loc[keep].reset_index(drop=True)
    frame.attrs["dropped_outside_largest_component"] = dropped
    return frame, variables


def fit_zone_set(ctx: RunContext, zone_set: str) -> tuple[dict[str, Any], pd.DataFrame]:
    """Fit OLS, SAR, SEM and SDM on one grid and assemble the report."""
    cfg = ctx.config.model
    frame, variables = design(ctx, zone_set)
    y = frame["alpha_model_k"].to_numpy(np.float64)
    raw = frame[variables].to_numpy(np.float64)
    mean, sd = raw.mean(axis=0), raw.std(axis=0, ddof=0)
    x = (raw - mean) / sd
    w = to_w(hex_graph(frame["q"].to_numpy(np.int64), frame["r"].to_numpy(np.int64)))
    traces = trace_powers(w.sparse, seed=cfg.seed)
    ols = models.fit_ols(y, x, variables, w)
    sar = models.fit_lag(
        y, x, variables, w, traces=traces, impact_draws=cfg.impact_draws, seed=cfg.seed
    )
    sem = models.fit_error(y, x, variables, w)
    sdm = models.fit_lag(
        y,
        x,
        variables,
        w,
        durbin=True,
        durbin_exclude=cfg.durbin_exclude,
        traces=traces,
        impact_draws=cfg.impact_draws,
        seed=cfg.seed,
    )
    fitted = [ols, sar, sem, sdm]
    models.ensure_comparable(fitted)
    lr = [
        models.likelihood_ratio(ols, sar),
        models.likelihood_ratio(ols, sem),
        models.likelihood_ratio(sar, sdm),
        models.likelihood_ratio(sem, sdm),
    ]
    best = min(fitted, key=lambda m: m.aic)
    report: dict[str, Any] = {
        "zone_set": zone_set,
        "n": len(frame),
        "dropped_outside_largest_component": frame.attrs["dropped_outside_largest_component"],
        "outcome": {
            "name": "alpha_model_k",
            "label": "Relative surface heat",
            "unit": "K",
            "description": (
                "Zone effect of a two-way median polish of clear-sky land surface temperature over "
                f"{cfg.period_start.isoformat()} to {cfg.period_end.isoformat()}."
            ),
            "mean": float(y.mean()),
            "sd": float(y.std()),
        },
        "variables": [
            {
                "name": v,
                "label": FEATURE_DESCRIPTIONS[v][0],
                "unit": FEATURE_DESCRIPTIONS[v][1],
                "description": FEATURE_DESCRIPTIONS[v][2],
                "mean": float(m),
                "sd": float(s),
            }
            for v, m, s in zip(variables, mean, sd, strict=True)
        ],
        "standardised": True,
        "durbin_exclude": list(cfg.durbin_exclude),
        "vif": {v: float(f) for v, f in zip(variables, models.variance_inflation(x), strict=True)},
        "lm_decision": models.lm_decision(ols),
        "models": [m.to_dict() for m in fitted],
        "likelihood_ratio_tests": [vars(t) for t in lr],
        "lowest_aic": best.kind,
        "period": [cfg.period_start.isoformat(), cfg.period_end.isoformat()],
        "hdb_completed_by": cfg.hdb_completed_by,
        "worldpop_year": cfg.worldpop_year,
    }
    zone_out = pd.DataFrame(
        {
            "zone_id": frame["zone_id"],
            "y": y,
            **{f"resid_{m.kind.lower()}": m.residuals for m in fitted},
            **{f"fitted_{m.kind.lower()}": m.fitted for m in fitted},
        }
    )
    return report, zone_out


def run(ctx: RunContext) -> None:
    """Fit the models on every hexagon grid."""
    summary = {}
    for zs in zone_sets(ctx):
        if zs.kind != "hex":
            continue
        report, zone_out = fit_zone_set(ctx, zs.name)
        ctx.paths.model(zs.name).write_text(json.dumps(report, indent=2, default=float) + "\n")
        zone_out.to_parquet(ctx.paths.model_zones(zs.name), index=False)
        aics = {m["kind"]: round(m["aic"], 1) for m in report["models"]}
        summary[zs.name] = {"n": report["n"], "aic": aics, "lm_decision": report["lm_decision"]}
        log.info(
            "%s: n=%d, LM decision %s, AIC %s", zs.name, report["n"], report["lm_decision"], aics
        )
    (ctx.paths.out / "model_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
