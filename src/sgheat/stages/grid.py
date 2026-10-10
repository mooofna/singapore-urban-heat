"""Zone sets (hexagon grids, planning areas, subzones) and their coverage matrices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from sgheat.geo.aoi import PixelGrid, analysis_grid
from sgheat.geo.hexgrid import HexGridSpec, build_grid
from sgheat.geo.zonal import CoverageMatrix, coverage_on_grid, coverage_on_raster
from sgheat.paths import zone_set_name
from sgheat.provenance import local_input, write_provenance
from sgheat.stages.context import RunContext
from sgheat.stages.static import load_boundaries

log = logging.getLogger(__name__)
STAGE_VERSION = 1
PLANNING_AREAS = "pa"
SUBZONES = "sz"


@dataclass(frozen=True)
class ZoneSet:
    """Name and kind of a zone set."""

    name: str
    kind: str  # "hex" or "area"
    radius_m: int | None = None


def zone_sets(ctx: RunContext) -> list[ZoneSet]:
    """All zone sets of the run: every hexagon grid, planning areas and subzones."""
    hexes = [ZoneSet(zone_set_name(r), "hex", r) for r in ctx.config.grid.radii_m]
    return [*hexes, ZoneSet(PLANNING_AREAS, "area"), ZoneSet(SUBZONES, "area")]


def primary_zone_set(ctx: RunContext) -> str:
    """Name of the primary hexagon grid."""
    return zone_set_name(ctx.config.grid.primary_radius_m)


def pixel_grid(ctx: RunContext) -> PixelGrid:
    """Analysis pixel grid derived from the land polygon."""
    _, _, land = load_boundaries(ctx)
    return analysis_grid(land, ctx.config.aoi)


def _assign_areas(zones: gpd.GeoDataFrame, sz: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Planning area and subzone with the largest share of each zone's land."""
    parts = gpd.GeoDataFrame(
        {"zone_id": zones["zone_id"].to_numpy()},
        geometry=list(zones["land_geometry"]),
        crs=zones.crs,
    )
    pieces = gpd.overlay(
        parts,
        sz[["sz_code", "pa_code", "pa_name", "region", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    pieces["piece_area"] = pieces.geometry.area
    best = pieces.sort_values(["zone_id", "piece_area"], ascending=[True, False]).drop_duplicates(
        "zone_id"
    )
    best = best[["zone_id", "sz_code", "pa_code", "pa_name", "region"]]
    return zones.merge(best, on="zone_id", how="left")


def build_zones(ctx: RunContext) -> None:
    """Write every zone set as a GeoParquet table plus coverage matrices."""
    cfg = ctx.config
    pa, sz, land = load_boundaries(ctx)
    epsg = cfg.aoi.crs_epsg
    grid = analysis_grid(land, cfg.aoi)
    log.info(
        "analysis grid %d x %d pixels at %.0f m", grid.width, grid.height, cfg.aoi.pixel_size_m
    )
    coast = shapely.boundary(land)
    for zs in zone_sets(ctx):
        if zs.kind == "hex":
            assert zs.radius_m is not None
            zones = build_grid(
                land, HexGridSpec(radius_m=float(zs.radius_m)), cfg.grid.min_land_frac, epsg
            )
            zones = _assign_areas(zones, sz)
        elif zs.name == PLANNING_AREAS:
            zones = gpd.GeoDataFrame(
                {
                    "zone_id": pa["pa_code"].to_numpy(),
                    "name": pa["name"].to_numpy(),
                    "pa_code": pa["pa_code"].to_numpy(),
                    "region": pa["region"].to_numpy(),
                    "land_geometry": pa.geometry.to_numpy(),
                },
                geometry=pa.geometry.to_numpy(),
                crs=epsg,
            )
            zones["land_area_m2"] = zones.geometry.area
        else:
            zones = gpd.GeoDataFrame(
                {
                    "zone_id": sz["sz_code"].to_numpy(),
                    "name": sz["name"].to_numpy(),
                    "sz_code": sz["sz_code"].to_numpy(),
                    "pa_code": sz["pa_code"].to_numpy(),
                    "region": sz["region"].to_numpy(),
                    "land_geometry": sz.geometry.to_numpy(),
                },
                geometry=sz.geometry.to_numpy(),
                crs=epsg,
            )
            zones["land_area_m2"] = zones.geometry.area
        land_geoms = gpd.GeoSeries(zones["land_geometry"], crs=epsg)
        centroids = land_geoms.representative_point()
        zones["dist_coast_km"] = shapely.distance(centroids.to_numpy(), coast) / 1000.0
        zones["land_geometry"] = land_geoms
        path = (
            ctx.paths.grid(zs.radius_m)
            if zs.radius_m is not None
            else ctx.paths.interim / f"zones_{zs.name}.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        zones.to_parquet(path)
        write_provenance(
            path,
            stage="grid",
            stage_version=STAGE_VERSION,
            config_digest=cfg.grid.digest(),
            inputs=(local_input(ctx.paths.boundaries),),
        )
        ids = zones["zone_id"].astype(str).tolist()
        geoms = list(land_geoms)
        landsat_cov = coverage_on_grid(geoms, ids, grid)
        landsat_cov.save(ctx.paths.coverage(zs.name, "landsat"))
        for year in cfg.worldpop.years:
            wp_path = ctx.paths.worldpop(year)
            if not wp_path.exists():
                continue
            geoms_wgs = list(land_geoms.to_crs(epsg=4326))
            coverage_on_raster(geoms_wgs, ids, wp_path, 4326).save(
                ctx.paths.coverage(zs.name, f"worldpop{year}")
            )
        log.info("zone set %s: %d zones", zs.name, len(zones))


def load_zones(ctx: RunContext, name: str) -> gpd.GeoDataFrame:
    """Zone table of a zone set."""
    if name.startswith("r") and name[1:].isdigit():
        return gpd.read_parquet(ctx.paths.grid(int(name[1:])))
    return gpd.read_parquet(ctx.paths.interim / f"zones_{name}.parquet")


def load_coverage(ctx: RunContext, name: str, raster: str = "landsat") -> CoverageMatrix:
    """Coverage matrix of a zone set on the Landsat grid or a WorldPop grid (``worldpop2023``)."""
    return CoverageMatrix.load(ctx.paths.coverage(name, raster))


def zone_frame(ctx: RunContext, name: str) -> pd.DataFrame:
    """Zone attributes without geometry."""
    zones = load_zones(ctx, name)
    return pd.DataFrame(zones.drop(columns=["geometry", "land_geometry"]))


def landsat_grid_mask(ctx: RunContext) -> np.ndarray:
    """Land pixel mask on the analysis grid (pixel centre inside the land polygon)."""
    from sgheat.geo.aoi import land_mask  # noqa: PLC0415

    _, _, land = load_boundaries(ctx)
    return land_mask(land, analysis_grid(land, ctx.config.aoi))
