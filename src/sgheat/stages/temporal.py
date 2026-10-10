"""Composites and trends from the per-scene zone statistics."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from sgheat.stages.context import RunContext
from sgheat.stages.grid import load_zones, primary_zone_set, zone_sets
from sgheat.stages.scenes import collect, load_catalog
from sgheat.stats.lisa import local_moran
from sgheat.stats.weights import hex_graph, to_w
from sgheat.temporal.anomaly import TwoWayFit, median_polish
from sgheat.temporal.seasons import Season, decimal_year
from sgheat.temporal.trends import theil_sen_mann_kendall

log = logging.getLogger(__name__)
STAGE_VERSION = 1
MIN_OBS_YEAR = 3


@dataclass(frozen=True)
class ZoneSceneMatrix:
    """Valid observations of one variable as a zones-by-scenes matrix."""

    zone_ids: list[str]
    item_ids: list[str]
    values: NDArray[np.float64]


def pivot(
    table: pd.DataFrame, zone_ids: list[str], item_ids: list[str], column: str
) -> ZoneSceneMatrix:
    """Pivot a long zone statistics table into a matrix aligned to the given ids."""
    wide = table.pivot(index="zone_id", columns="item_id", values=column)
    wide = wide.reindex(index=zone_ids, columns=item_ids)
    return ZoneSceneMatrix(zone_ids, item_ids, wide.to_numpy(dtype=np.float64))


def valid_observations(table: pd.DataFrame, ctx: RunContext) -> pd.DataFrame:
    """Rows whose zone was clear enough in that scene; LST, NDVI and water fraction kept."""
    cfg = ctx.config.scenes
    ok = (
        (table["obs_frac"] >= cfg.min_zone_clear_frac)
        & (table["lst_px"] >= cfg.min_zone_pixels)
        & np.isfinite(table["lst_k"])
    )
    return pd.DataFrame(table.loc[ok])


def _composite(
    values: NDArray[np.float64], cols: NDArray[np.bool_], min_obs: int
) -> NDArray[np.float64]:
    sub = values[:, cols]
    n = np.sum(np.isfinite(sub), axis=1)
    out = np.full(values.shape[0], np.nan)
    has = n >= min_obs
    if has.any():
        out[has] = np.nanmedian(sub[has], axis=1)
    return out


def summarise(
    ctx: RunContext,
    valid: pd.DataFrame,
    catalog: pd.DataFrame,
    zone_ids: list[str],
    period: tuple[date, date] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, TwoWayFit, ZoneSceneMatrix]:
    """Zone composites and scene effects for all scenes or a date range."""
    tcfg = ctx.config.temporal
    scenes = catalog[catalog["status"] == "accepted"].copy()
    scenes["date"] = pd.to_datetime(scenes["date_sgt"]).dt.date
    if period is not None:
        scenes = scenes[(scenes["date"] >= period[0]) & (scenes["date"] <= period[1])]
    scenes = scenes.sort_values("datetime_utc")
    item_ids = scenes["item_id"].tolist()
    lst = pivot(valid, zone_ids, item_ids, "lst_k")
    fit = median_polish(lst.values, max_iter=tcfg.polish_max_iter, tol=tcfg.polish_tol)
    anomaly = fit.anomaly()
    n_obs = np.sum(np.isfinite(lst.values), axis=1)
    ndvi = pivot(valid, zone_ids, item_ids, "ndvi").values
    water = pivot(valid, zone_ids, item_ids, "water_frac").values
    mndwi = pivot(valid, zone_ids, item_ids, "mndwi").values
    all_cols = np.ones(len(item_ids), dtype=bool)
    zone = pd.DataFrame(
        {
            "zone_id": zone_ids,
            "n_obs": n_obs,
            "alpha_k": np.where(n_obs >= tcfg.min_obs, fit.zone_effect, np.nan),
            "anomaly_median_k": _composite(anomaly, all_cols, tcfg.min_obs),
            "lst_typical_c": np.where(
                n_obs >= tcfg.min_obs, fit.overall + fit.zone_effect - 273.15, np.nan
            ),
            "ndvi": _composite(ndvi, all_cols, tcfg.min_obs),
            "mndwi": _composite(mndwi, all_cols, tcfg.min_obs),
            "water_frac": _composite(water, all_cols, tcfg.min_obs),
        }
    )
    seasons = scenes["season"].to_numpy()
    for season in Season:
        zone[f"anomaly_{season.value}_k"] = _composite(
            anomaly, seasons == season.value, tcfg.min_obs
        )
    years = scenes["date"].map(lambda d: d.year).to_numpy()
    for year in sorted(set(years.tolist())):
        zone[f"anomaly_{year}_k"] = _composite(anomaly, years == year, MIN_OBS_YEAR)
    t = np.array([decimal_year(pd.Timestamp(v).to_pydatetime()) for v in scenes["datetime_utc"]])
    trend = theil_sen_mann_kendall(
        t,
        anomaly,
        min_obs=tcfg.trend_min_obs,
        min_span_years=tcfg.trend_min_years,
        alpha=tcfg.fdr_alpha,
    )
    zone["trend_k_per_decade"] = trend.slope_per_decade
    zone["trend_low"] = trend.slope_low
    zone["trend_high"] = trend.slope_high
    zone["trend_p"] = trend.p_value
    zone["trend_q"] = trend.q_value
    scene_tab = pd.DataFrame(
        {
            "item_id": item_ids,
            "scene_effect_k": fit.scene_effect,
            "scene_level_c": fit.overall + fit.scene_effect - 273.15,
            "n_valid_zones": np.sum(np.isfinite(lst.values), axis=0),
        }
    )
    return zone, scene_tab, fit, lst


def run(ctx: RunContext) -> None:
    """Composites, trends and hot spots for every zone set."""
    catalog = load_catalog(ctx)
    table = collect(ctx)
    valid = valid_observations(table, ctx)
    mcfg = ctx.config.model
    primary = primary_zone_set(ctx)
    report: dict[str, dict[str, float | int]] = {}
    for zs in zone_sets(ctx):
        zones = load_zones(ctx, zs.name)
        zone_ids = zones["zone_id"].astype(str).tolist()
        sub = valid[valid["zone_set"] == zs.name]
        zone, scene_tab, fit, lst = summarise(ctx, sub, catalog, zone_ids)
        mzone, _, _, _ = summarise(
            ctx, sub, catalog, zone_ids, (mcfg.period_start, mcfg.period_end)
        )
        zone["alpha_model_k"] = mzone["alpha_k"].to_numpy()
        zone["n_obs_model"] = mzone["n_obs"].to_numpy()
        zone["ndvi_model"] = mzone["ndvi"].to_numpy()
        zone["water_frac_model"] = mzone["water_frac"].to_numpy()
        if zs.kind == "hex":
            zone["lisa_cluster"] = 0
            ok = np.isfinite(zone["alpha_k"].to_numpy())
            q = zones.loc[ok, "q"].to_numpy(dtype=np.int64)
            r = zones.loc[ok, "r"].to_numpy(dtype=np.int64)
            graph = hex_graph(q, r)
            if len(graph.isolates):
                log.info("%s: %d isolated zones excluded from LISA", zs.name, len(graph.isolates))
            keep = np.ones(len(q), dtype=bool)
            keep[np.asarray(graph.isolates, dtype=np.int64)] = False
            idx = np.flatnonzero(ok)[keep]
            w = to_w(hex_graph(q[keep], r[keep]))
            res = local_moran(
                zone.loc[idx, "alpha_k"].to_numpy(),
                w,
                permutations=mcfg.lisa_permutations if zs.name == primary else 999,
                seed=mcfg.seed,
            )
            zone.loc[idx, "lisa_cluster"] = res.cluster
            zone.loc[idx, "lisa_q"] = res.q_value
        out = ctx.paths.temporal(zs.name)
        out.parent.mkdir(parents=True, exist_ok=True)
        zone.to_parquet(out, index=False)
        scene_tab.to_parquet(ctx.paths.out / f"scene_effects_{zs.name}.parquet", index=False)
        anomalies = pd.DataFrame(fit.anomaly(), index=zone_ids, columns=lst.item_ids)
        long = anomalies.rename_axis("zone_id").reset_index()
        long = long.melt(id_vars="zone_id", var_name="item_id", value_name="anomaly_k")
        long = long.dropna(subset=["anomaly_k"])
        long.to_parquet(ctx.paths.out / f"anomalies_{zs.name}.parquet", index=False)
        report[zs.name] = {
            "n_zones": len(zone_ids),
            "n_scenes": len(lst.item_ids),
            "polish_iterations": fit.iterations,
            "polish_converged": int(fit.converged),
            "zones_with_composite": int(np.isfinite(zone["alpha_k"]).sum()),
            "median_n_obs": float(np.median(zone["n_obs"])),
            "overall_level_c": fit.overall - 273.15,
        }
        log.info(
            "%s: %d zones, %d scenes, polish %s after %d iterations",
            zs.name,
            len(zone_ids),
            len(lst.item_ids),
            "converged" if fit.converged else "stopped",
            fit.iterations,
        )
    (ctx.paths.out / "temporal_report.json").write_text(json.dumps(report, indent=2) + "\n")
