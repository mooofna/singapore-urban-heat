"""Invariants checked after every run; any violation fails the run."""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from sgheat.stages.context import RunContext
from sgheat.stages.grid import PLANNING_AREAS, SUBZONES, load_zones, zone_sets
from sgheat.stages.scenes import load_catalog

log = logging.getLogger(__name__)
STATUSES = {"pending", "accepted", "rejected", "failed"}


class ValidationError(RuntimeError):
    """One or more invariants do not hold."""


def check(ctx: RunContext) -> list[str]:
    """Return a list of violated invariants (empty when everything holds)."""
    problems: list[str] = []
    catalog = load_catalog(ctx)
    if catalog["item_id"].duplicated().any():
        problems.append("catalog has duplicate item ids")
    if not set(catalog["status"].dropna()) <= STATUSES:
        problems.append(f"unknown catalog status {set(catalog['status']) - STATUSES}")
    accepted = catalog.loc[catalog["status"] == "accepted", "item_id"]
    missing = [i for i in accepted if not ctx.paths.scene_stats(i).exists()]
    if missing:
        problems.append(f"{len(missing)} accepted scenes without statistics, e.g. {missing[:3]}")
    for zs in zone_sets(ctx):
        zones = load_zones(ctx, zs.name)
        if not zones["zone_id"].is_unique:
            problems.append(f"{zs.name}: duplicate zone ids")
        if (
            zs.kind == "hex"
            and not ((zones["land_frac"] > 0) & (zones["land_frac"] <= 1 + 1e-9)).all()
        ):
            problems.append(f"{zs.name}: land fraction outside (0, 1]")
        temporal_path = ctx.paths.temporal(zs.name)
        if not temporal_path.exists():
            continue
        temporal = pd.read_parquet(temporal_path)
        share = float(np.isfinite(temporal["alpha_k"]).mean())
        if share < 0.5:
            problems.append(f"{zs.name}: only {share:.0%} of zones have a composite")
        lst = temporal["lst_typical_c"].dropna()
        if len(lst) and not lst.between(10, 70).all():
            problems.append(f"{zs.name}: typical LST outside 10 to 70 C")
        feats_path = ctx.paths.features(zs.name)
        if feats_path.exists():
            feats = pd.read_parquet(feats_path)
            for col in ("water_frac", "hdb_coverage"):
                vals = feats[col].dropna()
                if len(vals) and not vals.between(0, 1 + 1e-6).all():
                    problems.append(f"{zs.name}: {col} outside [0, 1]")
            nd = feats["ndvi"].dropna()
            if len(nd) and not nd.between(-1, 1).all():
                problems.append(f"{zs.name}: NDVI outside [-1, 1]")
    pa_feats, sz_feats = ctx.paths.features(PLANNING_AREAS), ctx.paths.features(SUBZONES)
    if pa_feats.exists() and sz_feats.exists():
        pa_pop = pd.read_parquet(pa_feats)["population"].sum()
        sz_pop = pd.read_parquet(sz_feats)["population"].sum()
        if not np.isclose(pa_pop, sz_pop, rtol=1e-4):
            problems.append(
                f"population not conserved: planning areas {pa_pop:.0f}, subzones {sz_pop:.0f}"
            )
    for zs in zone_sets(ctx):
        path = ctx.paths.model(zs.name)
        if zs.kind != "hex" or not path.exists():
            continue
        report = json.loads(path.read_text())
        sem = next(m for m in report["models"] if m["kind"] == "SEM")
        if abs(sem["residual_moran"]["i"]) > 0.1:
            problems.append(f"{zs.name}: SEM residual Moran's I {sem['residual_moran']['i']:.2f}")
    manifest = ctx.config.paths.web_data_dir / "manifest.json"
    if manifest.exists():
        meta = json.loads(manifest.read_text())
        primary = meta["primary_zone_set"]
        scene_dir = ctx.config.paths.web_data_dir / "scenes" / primary
        n_bins = len(list(scene_dir.glob("*.bin")))
        if n_bins != len(accepted):
            problems.append(
                f"web bundle has {n_bins} scene files for {len(accepted)} accepted scenes"
            )
    return problems


def run(ctx: RunContext) -> None:
    """Raise :class:`ValidationError` if any invariant fails."""
    problems = check(ctx)
    for p in problems:
        log.error("invariant violated: %s", p)
    if problems:
        msg = f"{len(problems)} invariant(s) violated"
        raise ValidationError(msg)
    log.info("all invariants hold")
