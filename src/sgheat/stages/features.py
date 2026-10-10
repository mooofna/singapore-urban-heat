"""Urban form covariates per zone."""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from sgheat.stages.context import RunContext
from sgheat.stages.grid import load_coverage, load_zones, zone_sets

log = logging.getLogger(__name__)
STAGE_VERSION = 1

FEATURE_DESCRIPTIONS = {
    "ndvi": (
        "NDVI",
        "",
        "Median NDVI of clear land pixels over the model period (surface reflectance).",
    ),
    "water_frac": ("Water share", "", "Median share of clear pixels flagged as water in QA_PIXEL."),
    "pop_density": (
        "Population density",
        "1,000 per km²",
        "WorldPop R2025A constrained count per land km².",
    ),
    "hdb_coverage": ("HDB building coverage", "", "HDB footprint area per land area."),
    "hdb_far": ("HDB floor area ratio", "", "HDB footprint area times storeys per land area."),
    "hdb_commercial": (
        "HDB commercial coverage",
        "",
        "Footprint area of HDB blocks with shops or hawker centres per land area.",
    ),
    "dist_coast_km": (
        "Distance to coast",
        "km",
        "Distance from the zone to the outer land boundary.",
    ),
    "hdb_dwelling_density": (
        "HDB dwelling density",
        "1,000 per km²",
        "HDB dwelling units per land km².",
    ),
}


def hdb_features(
    zones: gpd.GeoDataFrame, blocks: gpd.GeoDataFrame, completed_by: int
) -> pd.DataFrame:
    """Footprint-based HDB covariates; blocks are split by area where they cross zone edges."""
    blk = blocks[blocks["year_completed"].fillna(9999) <= completed_by].copy()
    blk["commercial_any"] = blk["commercial"] | blk["market_hawker"]
    parts = gpd.GeoDataFrame(
        {"zone_id": zones["zone_id"].to_numpy()},
        geometry=list(zones["land_geometry"]),
        crs=zones.crs,
    )
    cols = [
        "max_floor_lvl",
        "total_dwelling_units",
        "commercial_any",
        "footprint_area_m2",
        "geometry",
    ]
    pieces = gpd.overlay(parts, blk[cols], how="intersection", keep_geom_type=True)
    pieces["a"] = pieces.geometry.area
    share = pieces["a"] / pieces["footprint_area_m2"]
    pieces["floor_area"] = pieces["a"] * pieces["max_floor_lvl"].astype(float)
    pieces["dwellings"] = share * pieces["total_dwelling_units"].astype(float)
    pieces["commercial_area"] = pieces["a"] * pieces["commercial_any"].astype(float)
    agg = pieces.groupby("zone_id").agg(
        footprint=("a", "sum"),
        floor_area=("floor_area", "sum"),
        dwellings=("dwellings", "sum"),
        commercial_area=("commercial_area", "sum"),
    )
    agg = agg.reindex(zones["zone_id"]).fillna(
        0.0
    )  # no HDB block in the zone means zero, not missing
    land = zones.set_index("zone_id")["land_area_m2"]
    return pd.DataFrame(
        {
            "zone_id": zones["zone_id"].to_numpy(),
            "hdb_coverage": (agg["footprint"] / land).to_numpy(),
            "hdb_far": (agg["floor_area"] / land).to_numpy(),
            "hdb_commercial": (agg["commercial_area"] / land).to_numpy(),
            "hdb_dwelling_density": (agg["dwellings"] / (land / 1e6) / 1000.0).to_numpy(),
            "hdb_mean_storeys": np.where(
                agg["footprint"] > 0,
                agg["floor_area"] / agg["footprint"].where(agg["footprint"] > 0),
                np.nan,
            ),
        }
    )


def population(ctx: RunContext, zone_set: str, zones: pd.DataFrame, year: int) -> np.ndarray:
    """Population per zone from WorldPop (coverage-weighted, mass conserving)."""
    cov = load_coverage(ctx, zone_set, f"worldpop{year}")
    with rasterio.open(ctx.paths.worldpop(year)) as src:
        pop = src.read(1, masked=True).astype(np.float64).filled(np.nan)
    totals = cov.total(pop)
    return np.where(np.isnan(totals), 0.0, totals)  # nodata in WorldPop marks unsettled land


def run(ctx: RunContext) -> None:
    """Write the feature table of every zone set."""
    cfg = ctx.config.model
    blocks = gpd.read_parquet(ctx.paths.hdb_blocks)
    for zs in zone_sets(ctx):
        zones = load_zones(ctx, zs.name)
        temporal = pd.read_parquet(ctx.paths.temporal(zs.name))
        frame = pd.DataFrame(zones.drop(columns=["geometry", "land_geometry"]))
        frame = frame.merge(
            hdb_features(zones, blocks, cfg.hdb_completed_by), on="zone_id", how="left"
        )
        pop = population(ctx, zs.name, frame, cfg.worldpop_year)
        frame["population"] = pop
        frame["pop_density"] = pop / (frame["land_area_m2"] / 1e6) / 1000.0
        frame = frame.merge(
            temporal[["zone_id", "ndvi_model", "water_frac_model", "ndvi", "water_frac"]].rename(
                columns={"ndvi": "ndvi_all", "water_frac": "water_frac_all"}
            ),
            on="zone_id",
            how="left",
        )
        frame = frame.rename(columns={"ndvi_model": "ndvi", "water_frac_model": "water_frac"})
        out = ctx.paths.features(zs.name)
        frame.to_parquet(out, index=False)
        log.info(
            "%s features: population %.0f, HDB coverage mean %.3f",
            zs.name,
            frame["population"].sum(),
            frame["hdb_coverage"].mean(),
        )
