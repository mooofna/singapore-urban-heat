"""Landsat scenes: discovery, screening and per-zone statistics.

Every scene found on the STAC API is recorded in ``data/catalog/scenes.csv``
with a status: ``pending`` (not yet processed), ``accepted`` (zone statistics
written), ``rejected`` (too cloudy over Singapore, with the measured clear
fraction) or ``failed`` (network or data error, retried on the next run). An
item whose upstream ``created`` timestamp changes is processed again.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pystac
from numpy.typing import NDArray

from sgheat.geo.aoi import PixelGrid
from sgheat.geo.zonal import CoverageMatrix
from sgheat.io import landsat, stac
from sgheat.physics.indices import mndwi, ndvi
from sgheat.physics.qa import QAMasks, decode_qa_pixel
from sgheat.physics.scaling import surface_reflectance, surface_temperature_kelvin
from sgheat.stages.context import RunContext
from sgheat.stages.grid import landsat_grid_mask, load_coverage, pixel_grid, zone_sets
from sgheat.stages.static import load_boundaries
from sgheat.temporal.seasons import season_of

log = logging.getLogger(__name__)
ALGO_VERSION = 1
CATALOG_COLUMNS = [
    "item_id",
    "platform",
    "datetime_utc",
    "datetime_sgt",
    "date_sgt",
    "season",
    "wrs_path",
    "wrs_row",
    "collection_category",
    "cloud_cover",
    "cloud_cover_land",
    "created",
    "status",
    "reason",
    "sg_clear_frac",
    "sg_water_frac",
    "land_lst_p10_c",
    "land_lst_p50_c",
    "land_lst_p90_c",
    "algo_version",
    "processed_at",
]
_TEXT_COLUMNS = (
    "item_id",
    "platform",
    "datetime_utc",
    "datetime_sgt",
    "date_sgt",
    "season",
    "wrs_path",
    "wrs_row",
    "collection_category",
    "created",
    "status",
    "reason",
    "processed_at",
)


def _typed(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.reindex(columns=CATALOG_COLUMNS)
    for col in CATALOG_COLUMNS:
        if col in _TEXT_COLUMNS:
            out[col] = out[col].astype("object").where(out[col].notna(), None)
        elif col == "algo_version":
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out


def load_catalog(ctx: RunContext) -> pd.DataFrame:
    """Scene catalog, empty if none exists yet."""
    path = ctx.paths.catalog
    if not path.exists():
        return _typed(pd.DataFrame(columns=CATALOG_COLUMNS))
    frame = pd.read_csv(
        path, dtype=dict.fromkeys(_TEXT_COLUMNS, str), keep_default_na=False, na_values=[""]
    )
    return _typed(frame)


def save_catalog(ctx: RunContext, catalog: pd.DataFrame) -> None:
    """Write the catalog sorted by acquisition time."""
    path = ctx.paths.catalog
    path.parent.mkdir(parents=True, exist_ok=True)
    out = _typed(catalog).sort_values("datetime_utc", kind="stable")
    out.to_csv(path, index=False, float_format="%.4f")


def local_items(ctx: RunContext) -> dict[str, pystac.Item]:
    """STAC items stored as ``<folder>/item.json`` below ``paths.local_scenes_dir``."""
    root = ctx.config.paths.local_scenes_dir
    if root is None:
        return {}
    items = {}
    for path in sorted(root.glob("*/item.json")):
        item = pystac.Item.from_file(str(path))
        item.make_asset_hrefs_absolute()
        items[item.id] = item
    return items


def discover(ctx: RunContext, since: date | None = None) -> pd.DataFrame:
    """Find items (STAC API or local folder) and add new or reprocessed ones as ``pending``."""
    cfg = ctx.config
    if cfg.scenes.source == "local":
        items = list(local_items(ctx).values())
    else:
        _, _, land = load_boundaries(ctx)
        footprint = (
            gpd.GeoSeries([land], crs=cfg.aoi.crs_epsg).simplify(500).to_crs(epsg=4326).iloc[0]
        )
        items = stac.search_scenes(cfg.scenes, footprint, start=since)
    catalog = load_catalog(ctx)
    known = catalog.set_index("item_id") if len(catalog) else None
    new_rows = []
    n_new = n_reprocessed = 0
    for item in items:
        rec = stac.SceneRecord.from_item(item)
        if known is not None and rec.item_id in known.index:
            if str(known.at[rec.item_id, "created"]) != rec.created:
                catalog.loc[catalog["item_id"] == rec.item_id, ["status", "created"]] = [
                    "pending",
                    rec.created,
                ]
                n_reprocessed += 1
            continue
        sgt = rec.datetime_sgt
        new_rows.append(
            {
                "item_id": rec.item_id,
                "platform": rec.platform,
                "datetime_utc": rec.datetime_utc.isoformat(),
                "datetime_sgt": sgt.replace(tzinfo=None).isoformat(timespec="seconds"),
                "date_sgt": sgt.date().isoformat(),
                "season": season_of(sgt).value,
                "wrs_path": rec.wrs_path,
                "wrs_row": rec.wrs_row,
                "collection_category": rec.collection_category,
                "cloud_cover": rec.cloud_cover,
                "cloud_cover_land": rec.cloud_cover_land,
                "created": rec.created,
                "status": "pending",
                "reason": "",
                "algo_version": ALGO_VERSION,
            }
        )
        n_new += 1
    if new_rows:
        catalog = _typed(pd.concat([catalog, _typed(pd.DataFrame(new_rows))], ignore_index=True))
    stale = catalog["algo_version"].fillna(0).astype(int) < ALGO_VERSION
    catalog.loc[stale & catalog["status"].isin(["accepted", "rejected"]), "status"] = "pending"
    save_catalog(ctx, catalog)
    log.info(
        "%s: %d items, %d new, %d reprocessed upstream",
        cfg.scenes.source,
        len(items),
        n_new,
        n_reprocessed,
    )
    return catalog


@dataclass(frozen=True)
class SceneArrays:
    """Physical layers of one scene on the analysis grid."""

    masks: QAMasks
    lst_k: NDArray[np.float32]
    ndvi: NDArray[np.float32]
    mndwi: NDArray[np.float32]


def scene_arrays(raw: dict[str, NDArray[np.generic]]) -> SceneArrays:
    """Scale bands, apply the QA mask and compute indices."""
    masks = decode_qa_pixel(raw["qa_pixel"].astype(np.uint16))
    lst = surface_temperature_kelvin(raw["lwir11"])
    red = surface_reflectance(raw["red"])
    nir = surface_reflectance(raw["nir08"])
    green = surface_reflectance(raw["green"])
    swir = surface_reflectance(raw["swir16"])
    lst[~masks.land] = np.nan
    v = ndvi(red, nir)
    v[~masks.land] = np.nan
    w = mndwi(green, swir)
    w[~masks.observed] = np.nan
    return SceneArrays(masks=masks, lst_k=lst, ndvi=v, mndwi=w)


def zone_statistics(arrays: SceneArrays, coverage: CoverageMatrix) -> pd.DataFrame:
    """Per-zone means and quality fractions of one scene."""
    total = coverage.weight()
    observed = coverage.weight(arrays.masks.observed)
    water = coverage.weight(arrays.masks.water)
    lst, lst_px = coverage.mean(arrays.lst_k)
    nd, _ = coverage.mean(arrays.ndvi)
    mw, _ = coverage.mean(arrays.mndwi)
    with np.errstate(invalid="ignore", divide="ignore"):
        obs_frac = np.where(total > 0, observed / total, np.nan)
        water_frac = np.where(observed > 0, water / observed, np.nan)
    return pd.DataFrame(
        {
            "zone_id": list(coverage.zone_ids),
            "lst_k": lst.astype(np.float32),
            "ndvi": nd.astype(np.float32),
            "mndwi": mw.astype(np.float32),
            "obs_frac": obs_frac.astype(np.float32),
            "water_frac": water_frac.astype(np.float32),
            "lst_px": lst_px.astype(np.float32),
        }
    )


def scene_summary(arrays: SceneArrays, land: NDArray[np.bool_]) -> dict[str, float]:
    """Island-wide quality and temperature summary of a scene."""
    land_px = float(land.sum())
    observed = float((arrays.masks.observed & land).sum())
    water = float((arrays.masks.water & land).sum())
    vals = arrays.lst_k[land & np.isfinite(arrays.lst_k)] - 273.15
    p10, p50, p90 = np.percentile(vals, [10, 50, 90]) if vals.size else (np.nan, np.nan, np.nan)
    return {
        "sg_clear_frac": observed / land_px if land_px else np.nan,
        "sg_water_frac": water / observed if observed else np.nan,
        "land_lst_p10_c": float(p10),
        "land_lst_p50_c": float(p50),
        "land_lst_p90_c": float(p90),
    }


@dataclass
class ProcessingContext:
    """Objects loaded once and shared by all scenes of a run."""

    grid: PixelGrid
    land: NDArray[np.bool_]
    coverages: dict[str, CoverageMatrix]


def processing_context(ctx: RunContext) -> ProcessingContext:
    """Load the pixel grid, land mask and coverage matrices."""
    return ProcessingContext(
        grid=pixel_grid(ctx),
        land=landsat_grid_mask(ctx),
        coverages={zs.name: load_coverage(ctx, zs.name, "landsat") for zs in zone_sets(ctx)},
    )


def process_hrefs(
    ctx: RunContext, pctx: ProcessingContext, item_id: str, hrefs: dict[str, str]
) -> dict[str, Any]:
    """Screen one scene and, if clear enough, write its zone statistics."""
    cfg = ctx.config.scenes
    qa = landsat.read_window(hrefs["qa_pixel"], pctx.grid, fill_value=1)
    masks = decode_qa_pixel(qa.astype(np.uint16))
    land_px = float(pctx.land.sum())
    clear = float((masks.observed & pctx.land).sum()) / land_px
    result: dict[str, Any] = {
        "sg_clear_frac": clear,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if clear < cfg.min_scene_clear_frac:
        result.update(
            status="rejected",
            reason=f"clear land fraction {clear:.2f} below {cfg.min_scene_clear_frac:.2f}",
        )
        return result
    rest = {k: v for k, v in hrefs.items() if k != "qa_pixel"}
    raw = landsat.read_assets(rest, pctx.grid)
    raw["qa_pixel"] = qa
    arrays = scene_arrays(raw)
    frames = []
    for name, cov in pctx.coverages.items():
        stats = zone_statistics(arrays, cov)
        stats.insert(0, "zone_set", name)
        frames.append(stats)
    table = pd.concat(frames, ignore_index=True)
    table.insert(0, "item_id", item_id)
    out = ctx.paths.scene_stats(item_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, index=False)
    result.update(scene_summary(arrays, pctx.land))
    result.update(status="accepted", reason="")
    return result


def _process_item(ctx: RunContext, pctx: ProcessingContext, item_id: str) -> dict[str, Any]:
    try:
        if ctx.config.scenes.source == "local":
            item = local_items(ctx)[item_id]
        else:
            item = stac.get_item(ctx.config.scenes, item_id)
        return process_hrefs(ctx, pctx, item_id, landsat.item_hrefs(item))
    except landsat.LatticeMismatchError as exc:
        return {"status": "rejected", "reason": f"off lattice: {exc}"}
    except Exception as exc:
        log.debug("".join(traceback.format_exception(exc)))
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"[:300]}


def process(
    ctx: RunContext,
    item_ids: list[str] | None = None,
    workers: int = 3,
    limit: int | None = None,
) -> pd.DataFrame:
    """Process pending (or the given) catalog items."""
    catalog = load_catalog(ctx)
    # Self-heal: an accepted scene whose statistics file is missing is processed again.
    lost = (catalog["status"] == "accepted") & ~catalog["item_id"].map(
        lambda i: ctx.paths.scene_stats(str(i)).exists()
    )
    if lost.any():
        log.warning("%d accepted scenes lack statistics and are reprocessed", int(lost.sum()))
        catalog.loc[lost, "status"] = "pending"
    if item_ids:
        todo = [i for i in item_ids if i in set(catalog["item_id"])]
    else:
        todo = catalog.loc[catalog["status"].isin(["pending", "failed"]), "item_id"].tolist()
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        log.info("no scenes to process")
        return catalog
    pctx = processing_context(ctx)
    log.info("processing %d scenes with %d workers", len(todo), workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_item, ctx, pctx, i): i for i in todo}
        for n, fut in enumerate(as_completed(futures), start=1):
            item_id = futures[fut]
            res = fut.result()
            res["algo_version"] = ALGO_VERSION
            row = catalog["item_id"] == item_id
            for key, value in res.items():
                catalog.loc[row, key] = value
            log.info(
                "[%d/%d] %s %s %s", n, len(todo), item_id, res["status"], res.get("reason", "")
            )
            if n % 10 == 0:
                save_catalog(ctx, catalog)
    save_catalog(ctx, catalog)
    return catalog


def process_local(ctx: RunContext, folder: Path, product_id: str, item_id: str) -> dict[str, Any]:
    """Process a scene from a local USGS Level-2 product folder (offline mode)."""
    pctx = processing_context(ctx)
    return process_hrefs(ctx, pctx, item_id, landsat.local_hrefs(folder, product_id))


def recent_window(ctx: RunContext) -> date:
    """Start date for incremental discovery."""
    return datetime.now(UTC).date() - timedelta(days=ctx.config.scenes.recheck_days)


def collect(ctx: RunContext) -> pd.DataFrame:
    """Concatenate the zone statistics of all accepted scenes."""
    catalog = load_catalog(ctx)
    accepted = catalog.loc[catalog["status"] == "accepted", "item_id"].tolist()
    frames = [
        pd.read_parquet(ctx.paths.scene_stats(i))
        for i in accepted
        if ctx.paths.scene_stats(i).exists()
    ]
    if not frames:
        msg = "no accepted scenes with statistics; run `sgheat scenes process` first"
        raise RuntimeError(msg)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(ctx.paths.scene_zone_stats, index=False)
    return table
