"""Static data bundle for the web explorer.

Layout below ``web/static/data``::

    manifest.json                 index of everything below, units, sources, run metadata
    catalog.json                  every discovered scene with status and quality
    summary.json                  headline numbers (also rendered into the README)
    physics.json                  textbook LST estimators against USGS surface temperature
    zones/<set>.geojson           zone geometries (WGS84), feature index ``i``
    zones/<set>.json              per-zone columns aligned to ``i``
    scenes/<set>/<item>.bin       per-scene int16 arrays: anomaly and LST (0.01 K units)
    series/<set>/<chunk>.bin      int16 anomaly time series, ``CHUNK`` zones per file
    models/<set>.json             spatial regression report
    areas.json                    planning area and subzone indicators

Binary arrays are little-endian int16 with ``-32768`` for missing values.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from sgheat.provenance import git_state, package_version
from sgheat.stages.context import RunContext
from sgheat.stages.grid import PLANNING_AREAS, SUBZONES, load_zones, primary_zone_set, zone_sets
from sgheat.stages.scenes import load_catalog
from sgheat.temporal.seasons import SEASON_LABELS, Season

log = logging.getLogger(__name__)
SCHEMA_VERSION = 1
CHUNK = 512
MISSING = -32768
SCALE = 100.0  # int16 values are hundredths of a kelvin
WEB_ZONE_SETS_WITH_SCENES = ("primary", PLANNING_AREAS)
LISA_NAMES = {
    0: "not significant",
    1: "hot spot",
    2: "cool outlier",
    3: "cool spot",
    4: "hot outlier",
}


def _clean(value: Any) -> Any:
    if isinstance(value, float | np.floating):
        v = float(value)
        return None if not math.isfinite(v) else round(v, 4)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    """Compact JSON with NaN written as null and floats rounded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(payload), separators=(",", ":"), ensure_ascii=False))


def to_int16(values: np.ndarray) -> np.ndarray:
    """Hundredths of a kelvin as int16, missing as ``MISSING``."""
    v = np.asarray(values, dtype=np.float64) * SCALE
    out = np.full(v.shape, MISSING, dtype="<i2")
    ok = np.isfinite(v)
    out[ok] = np.clip(np.rint(v[ok]), -32767, 32767).astype("<i2")
    return out


def _column(series: pd.Series, digits: int) -> list[float | None]:
    arr = series.to_numpy(dtype=np.float64)
    return [None if not math.isfinite(x) else round(float(x), digits) for x in arr]


def zone_geometries(zones: gpd.GeoDataFrame, kind: str) -> gpd.GeoDataFrame:
    """Display geometries in WGS84: hexagons clipped to the coast, areas simplified."""
    if kind == "hex":
        clipped = zones["land_frac"] < 0.999
        geoms = np.where(
            clipped,
            gpd.GeoSeries(zones["land_geometry"]).simplify(5).to_numpy(),
            zones.geometry.to_numpy(),
        )
    else:
        geoms = shapely.coverage_simplify(zones.geometry.to_numpy(), tolerance=15.0)
    out = gpd.GeoDataFrame(
        {"i": np.arange(len(zones)), "id": zones["zone_id"].astype(str)},
        geometry=list(geoms),
        crs=zones.crs,
    )
    out = out.to_crs(epsg=4326)
    # 1e-6 degrees is about 0.1 m at the equator; shared vertices stay shared.
    out["geometry"] = shapely.set_precision(out.geometry.to_numpy(), 1e-6)
    return out


def export_zone_set(ctx: RunContext, name: str, kind: str, out: Path) -> dict[str, Any]:
    """Geometry, per-zone columns and model residuals of one zone set."""
    zones = load_zones(ctx, name)
    geo = zone_geometries(zones, kind)
    geo_path = out / "zones" / f"{name}.geojson"
    geo_path.parent.mkdir(parents=True, exist_ok=True)
    geo_path.write_text(
        geo.to_json(drop_id=True, to_wgs84=False, na="null", show_bbox=False).replace(" ", "")
    )
    temporal = (
        pd.read_parquet(ctx.paths.temporal(name)).set_index("zone_id").reindex(zones["zone_id"])
    )
    feats = pd.read_parquet(ctx.paths.features(name)).set_index("zone_id").reindex(zones["zone_id"])
    cols: dict[str, list[Any]] = {
        "id": zones["zone_id"].astype(str).tolist(),
        "pa": zones["pa_code"].astype("string").fillna("").tolist() if "pa_code" in zones else [],
        "land_km2": _column(zones["land_area_m2"] / 1e6, 4),
        "n_obs": temporal["n_obs"].astype(int).tolist(),
        "alpha": _column(temporal["alpha_k"], 2),
        "lst": _column(temporal["lst_typical_c"], 2),
        "trend": _column(temporal["trend_k_per_decade"], 2),
        "trend_q": _column(temporal["trend_q"], 4),
        "ndvi": _column(feats["ndvi_all"], 3),
        "water": _column(feats["water_frac_all"], 3),
        "pop_density": _column(feats["pop_density"], 3),
        "population": _column(feats["population"], 0),
        "hdb_coverage": _column(feats["hdb_coverage"], 4),
        "hdb_far": _column(feats["hdb_far"], 3),
        "hdb_storeys": _column(feats["hdb_mean_storeys"], 1),
        "dist_coast": _column(feats["dist_coast_km"], 2),
    }
    if "name" in zones:
        cols["name"] = zones["name"].astype(str).tolist()
    if "lisa_cluster" in temporal:
        cols["lisa"] = temporal["lisa_cluster"].fillna(0).astype(int).tolist()
    for season in Season:
        cols[f"season_{season.value}"] = _column(temporal[f"anomaly_{season.value}_k"], 2)
    years = sorted(
        int(c.split("_")[1])
        for c in temporal.columns
        if c.startswith("anomaly_") and c.split("_")[1].isdigit()
    )
    for year in years:
        cols[f"year_{year}"] = _column(temporal[f"anomaly_{year}_k"], 2)
    model_zone_path = ctx.paths.model_zones(name)
    if kind == "hex" and model_zone_path.exists():
        mz = pd.read_parquet(model_zone_path).set_index("zone_id").reindex(zones["zone_id"])
        cols["resid_sem"] = _column(mz["resid_sem"], 2)
        cols["resid_ols"] = _column(mz["resid_ols"], 2)
    write_json(out / "zones" / f"{name}.json", cols)
    return {"name": name, "kind": kind, "n_zones": len(zones), "years": years}


def export_scenes(ctx: RunContext, name: str, out: Path) -> list[str]:
    """Per-scene arrays and chunked time series of one zone set."""
    zones = load_zones(ctx, name)
    ids = zones["zone_id"].astype(str).tolist()
    anomalies = pd.read_parquet(ctx.paths.out / f"anomalies_{name}.parquet")
    wide = anomalies.pivot(index="zone_id", columns="item_id", values="anomaly_k").reindex(
        index=ids
    )
    stats = pd.read_parquet(ctx.paths.scene_zone_stats)
    stats = stats[stats["zone_set"] == name]
    lst = (
        stats.pivot(index="zone_id", columns="item_id", values="lst_k").reindex(index=ids) - 273.15
    )
    items = list(wide.columns)
    scene_dir = out / "scenes" / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        anomaly = wide[item].to_numpy()
        absolute = lst[item].to_numpy() if item in lst else np.full(len(ids), np.nan)
        absolute = np.where(np.isfinite(anomaly), absolute, np.nan)  # same validity as the anomaly
        (scene_dir / f"{item}.bin").write_bytes(
            to_int16(anomaly).tobytes() + to_int16(absolute).tobytes()
        )
    series_dir = out / "series" / name
    series_dir.mkdir(parents=True, exist_ok=True)
    matrix = wide.to_numpy()
    for c, start in enumerate(range(0, len(ids), CHUNK)):
        block = matrix[start : start + CHUNK]
        (series_dir / f"{c}.bin").write_bytes(to_int16(block).tobytes())
    return items


def export_catalog(ctx: RunContext, out: Path, scene_order: list[str]) -> list[dict[str, Any]]:
    """Catalog of every discovered scene."""
    catalog = load_catalog(ctx)
    effects = pd.read_parquet(
        ctx.paths.out / f"scene_effects_{primary_zone_set(ctx)}.parquet"
    ).set_index("item_id")
    order = {item: i for i, item in enumerate(scene_order)}
    rows = []
    for rec in catalog.sort_values("datetime_utc").to_dict("records"):
        item = rec["item_id"]
        rows.append(
            {
                "id": item,
                "date": rec["date_sgt"],
                "time": str(rec["datetime_sgt"])[11:16],
                "platform": rec["platform"],
                "season": rec["season"],
                "status": rec["status"],
                "reason": rec["reason"] or "",
                "clear": rec["sg_clear_frac"],
                "cloud_land": rec["cloud_cover_land"],
                "p50": rec["land_lst_p50_c"],
                "level": effects["scene_level_c"].get(item, np.nan)
                if item in effects.index
                else None,
                "n_zones": int(effects["n_valid_zones"].get(item, 0))
                if item in effects.index
                else 0,
                "series_index": order.get(item),
            }
        )
    write_json(out / "catalog.json", rows)
    return rows


def area_indicators(ctx: RunContext) -> dict[str, Any]:
    """Planning area and subzone indicators, with population-weighted heat from the hexagons."""
    primary = primary_zone_set(ctx)
    hexes = pd.read_parquet(ctx.paths.features(primary))
    htemp = pd.read_parquet(ctx.paths.temporal(primary))[
        ["zone_id", "alpha_k", "lisa_cluster", "trend_k_per_decade", "trend_q"]
    ]
    hexes = hexes.merge(htemp, on="zone_id")
    result: dict[str, Any] = {}
    for level, key in ((PLANNING_AREAS, "pa_code"), (SUBZONES, "sz_code")):
        zones = load_zones(ctx, level)
        temporal = pd.read_parquet(ctx.paths.temporal(level)).set_index("zone_id")
        feats = pd.read_parquet(ctx.paths.features(level)).set_index("zone_id")
        h = hexes.dropna(subset=[key, "alpha_k"])
        weighted = (
            h.assign(w=h["population"] * h["alpha_k"])
            .groupby(key)
            .agg(
                w=("w", "sum"),
                pop=("population", "sum"),
                n_hex=("zone_id", "size"),
                hot=("lisa_cluster", lambda s: float((s == 1).mean())),
                warming=("trend_q", lambda s: float((s < 0.05).mean())),
            )
        )
        by_zone: dict[str, dict[str, float]] = {
            str(k): {str(c): float(v) for c, v in d.items()}
            for k, d in weighted.to_dict("index").items()
        }
        rows = []
        for z in zones.itertuples():
            zid = str(z.zone_id)
            agg = by_zone.get(zid)
            pop = agg["pop"] if agg is not None else 0.0
            rows.append(
                {
                    "id": zid,
                    "name": str(z.name),
                    "pa": str(getattr(z, "pa_code", zid)),
                    "region": str(z.region).title(),
                    "alpha": temporal["alpha_k"].get(zid),
                    "lst": temporal["lst_typical_c"].get(zid),
                    "trend": temporal["trend_k_per_decade"].get(zid),
                    "population": feats["population"].get(zid),
                    "pop_weighted_alpha": (agg["w"] / pop) if agg is not None and pop > 0 else None,
                    "hot_spot_share": agg["hot"] if agg is not None else None,
                    "ndvi": feats["ndvi_all"].get(zid),
                    "hdb_coverage": feats["hdb_coverage"].get(zid),
                    "land_km2": float(z.land_area_m2) / 1e6,
                }
            )
        result[level] = rows
    return result


def summary(ctx: RunContext, catalog_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline numbers, each traceable to an exported artifact."""
    primary = primary_zone_set(ctx)
    accepted = [r for r in catalog_rows if r["status"] == "accepted"]
    temporal = pd.read_parquet(ctx.paths.temporal(primary))
    alpha = temporal["alpha_k"].dropna()
    feats = pd.read_parquet(ctx.paths.features(primary)).merge(
        temporal[["zone_id", "alpha_k"]], on="zone_id"
    )
    feats = feats.dropna(subset=["alpha_k", "ndvi_all"])
    green = feats["ndvi_all"] >= feats["ndvi_all"].quantile(0.9)
    grey = feats["ndvi_all"] <= feats["ndvi_all"].quantile(0.1)
    pa = (
        pd.read_parquet(ctx.paths.temporal(PLANNING_AREAS))
        .merge(pd.DataFrame(load_zones(ctx, PLANNING_AREAS)[["zone_id", "name"]]), on="zone_id")
        .dropna(subset=["alpha_k"])
        .sort_values("alpha_k")
    )
    trend = temporal.dropna(subset=["trend_q"])
    physics = (
        json.loads(ctx.paths.physics_report.read_text())
        if ctx.paths.physics_report.exists()
        else None
    )
    model = (
        json.loads(ctx.paths.model(primary).read_text())
        if ctx.paths.model(primary).exists()
        else None
    )
    join = json.loads((ctx.paths.out / "hdb_join_report.json").read_text())
    out: dict[str, Any] = {
        "scenes": {
            "discovered": len(catalog_rows),
            "accepted": len(accepted),
            "first": accepted[0]["date"] if accepted else None,
            "last": accepted[-1]["date"] if accepted else None,
            "landsat8": sum(r["platform"] == "landsat-8" for r in accepted),
            "landsat9": sum(r["platform"] == "landsat-9" for r in accepted),
        },
        "zones": {"primary": primary, "n": len(temporal), "with_composite": int(alpha.size)},
        "relative_heat": {
            "p10_k": float(alpha.quantile(0.1)),
            "p90_k": float(alpha.quantile(0.9)),
            "greenest_decile_k": float(feats.loc[green, "alpha_k"].median()),
            "least_green_decile_k": float(feats.loc[grey, "alpha_k"].median()),
            "hottest_planning_areas": pa.tail(3)[["name", "alpha_k"]].iloc[::-1].to_dict("records"),
            "coolest_planning_areas": pa.head(3)[["name", "alpha_k"]].to_dict("records"),
        },
        "trends": {
            "zones_tested": len(trend),
            "warming_significant": int(
                ((trend["trend_q"] < 0.05) & (trend["trend_k_per_decade"] > 0)).sum()
            ),
            "cooling_significant": int(
                ((trend["trend_q"] < 0.05) & (trend["trend_k_per_decade"] < 0)).sum()
            ),
        },
        "hdb_join": {
            "match_rate": join["match_rate"],
            "residential_match_rate": join["residential_match_rate"],
        },
    }
    if physics:
        ref = physics["scenes"][0]
        out["physics"] = {
            "reference_scene": ref["item_id"],
            "single_channel_bias_k": ref["single_channel"]["bias_k"],
            "radiative_transfer_rmse_k": ref["radiative_transfer"]["rmse_k"],
            "transmission": ref["atmosphere"]["transmission_mean"],
        }
    if model:
        out["model"] = {
            "n": model["n"],
            "lm_decision": model["lm_decision"],
            "lowest_aic": model["lowest_aic"],
            "period": model["period"],
        }
    return out


def run(ctx: RunContext) -> Path:
    """Write the complete bundle to ``paths.web_data_dir``."""
    out = ctx.config.paths.web_data_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    primary = primary_zone_set(ctx)
    zone_meta = []
    for zs in zone_sets(ctx):
        zone_meta.append({**export_zone_set(ctx, zs.name, zs.kind, out), "radius_m": zs.radius_m})
    scene_order: list[str] = []
    for name in (primary, PLANNING_AREAS):
        items = export_scenes(ctx, name, out)
        scene_order = scene_order or items
    (out / "models").mkdir(exist_ok=True)
    for zs in zone_sets(ctx):
        if zs.kind == "hex" and ctx.paths.model(zs.name).exists():
            shutil.copy(ctx.paths.model(zs.name), out / "models" / f"{zs.name}.json")
    catalog_rows = export_catalog(ctx, out, scene_order)
    write_json(out / "areas.json", area_indicators(ctx))
    if ctx.paths.physics_report.exists():
        shutil.copy(ctx.paths.physics_report, out / "physics.json")
    summ = summary(ctx, catalog_rows)
    write_json(out / "summary.json", summ)
    sha, dirty = git_state()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sgheat_version": package_version(),
        "git_sha": sha,
        "git_dirty": dirty,
        "data_tag": datetime.now(UTC).strftime("%Y%m%d%H%M"),
        "primary_zone_set": primary,
        "zone_sets": zone_meta,
        "scene_zone_sets": [primary, PLANNING_AREAS],
        "series_chunk": CHUNK,
        "int16_scale": SCALE,
        "int16_missing": MISSING,
        "seasons": {s.value: SEASON_LABELS[s] for s in Season},
        "lisa": LISA_NAMES,
        "model_period": [
            ctx.config.model.period_start.isoformat(),
            ctx.config.model.period_end.isoformat(),
        ],
        "summary": summ,
    }
    write_json(out / "manifest.json", manifest)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    log.info("web bundle written to %s (%.1f MB)", out, size / 1e6)
    return out
