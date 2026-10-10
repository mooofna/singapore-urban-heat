"""Static inputs: downloads, boundaries and HDB blocks."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from sgheat.buildings import hdb, streets
from sgheat.geo.aoi import land_polygon
from sgheat.io import datagov, worldpop
from sgheat.io.http import client
from sgheat.provenance import InputRef, local_input, read_provenance, write_provenance
from sgheat.stages.context import RunContext

log = logging.getLogger(__name__)
STAGE_VERSION = 1


def _datagov_path(ctx: RunContext, dataset_id: str) -> Path | None:
    folder = ctx.paths.raw / "datagov"
    matches = sorted(folder.glob(f"{dataset_id}.*")) if folder.exists() else []
    matches = [m for m in matches if not m.name.endswith(".prov.json")]
    return matches[0] if matches else None


def datagov_file(ctx: RunContext, dataset_id: str) -> Path:
    """Path of a downloaded data.gov.sg dataset."""
    path = _datagov_path(ctx, dataset_id)
    if path is None:
        msg = f"dataset {dataset_id} not downloaded yet; run `sgheat fetch`"
        raise FileNotFoundError(msg)
    return path


def fetch(ctx: RunContext, refresh: bool = False) -> None:
    """Download missing data.gov.sg datasets and WorldPop rasters (all with ``refresh``)."""
    cfg = ctx.config
    ids = [
        cfg.datagov.hdb_property,
        cfg.datagov.hdb_footprints,
        cfg.datagov.planning_areas,
        cfg.datagov.subzones,
    ]
    with datagov.api_client() as http:
        for i, dataset_id in enumerate(ids):
            if _datagov_path(ctx, dataset_id) is not None and not refresh:
                log.info("data.gov.sg %s already present", dataset_id)
                continue
            if i:
                time.sleep(cfg.datagov.min_seconds_between_downloads)
            path, meta, sha, when = datagov.fetch_dataset(
                http, dataset_id, ctx.paths.raw / "datagov" / dataset_id
            )
            write_provenance(
                path,
                stage="fetch",
                stage_version=STAGE_VERSION,
                config_digest=cfg.datagov.digest(),
                inputs=(
                    InputRef(
                        uri=f"https://data.gov.sg/datasets/{dataset_id}/view",
                        sha256=sha,
                        retrieved_at=when,
                        upstream_version=meta.last_updated_at,
                    ),
                ),
                extra={"name": meta.name, "licence": meta.licence},
            )
            log.info("downloaded %s (%s, updated %s)", meta.name, path.name, meta.last_updated_at)
    with client() as http:
        for year in cfg.worldpop.years:
            dest = ctx.paths.worldpop(year)
            if dest.exists() and not refresh:
                log.info("WorldPop %d already present", year)
                continue
            url, sha, when = worldpop.fetch_year(http, cfg.worldpop, year, dest)
            write_provenance(
                dest,
                stage="fetch",
                stage_version=STAGE_VERSION,
                config_digest=cfg.worldpop.digest(),
                inputs=(
                    InputRef(uri=url, sha256=sha, retrieved_at=when, upstream_version="R2025A"),
                ),
                extra={"licence": "CC BY 4.0"},
            )
            log.info("downloaded WorldPop %d", year)


def _upstream(ctx: RunContext, dataset_id: str) -> InputRef:
    path = datagov_file(ctx, dataset_id)
    prov = read_provenance(path)
    version = prov.inputs[0].upstream_version if prov and prov.inputs else None
    return local_input(path, upstream_version=version)


def boundaries(ctx: RunContext) -> None:
    """Planning areas, subzones and the land polygon in the analysis CRS."""
    cfg = ctx.config
    epsg = cfg.aoi.crs_epsg
    pa = gpd.read_file(datagov_file(ctx, cfg.datagov.planning_areas)).to_crs(epsg=epsg)
    sz = gpd.read_file(datagov_file(ctx, cfg.datagov.subzones)).to_crs(epsg=epsg)
    pa = pa.rename(columns={"PLN_AREA_C": "pa_code", "PLN_AREA_N": "pa_name", "REGION_N": "region"})
    sz = sz.rename(
        columns={
            "SUBZONE_C": "sz_code",
            "SUBZONE_N": "sz_name",
            "PLN_AREA_C": "pa_code",
            "PLN_AREA_N": "pa_name",
            "REGION_N": "region",
        }
    )
    pa = pa[["pa_code", "pa_name", "region", "geometry"]].copy()
    sz = sz[["sz_code", "sz_name", "pa_code", "pa_name", "region", "geometry"]].copy()
    for frame in (pa, sz):
        frame["geometry"] = frame.geometry.make_valid()
        frame["name"] = frame.iloc[:, 1].str.title()
    land = gpd.GeoDataFrame({"name": ["Singapore"]}, geometry=[land_polygon(pa, epsg)], crs=epsg)
    out = ctx.paths.boundaries
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    pa.to_file(out, layer="planning_areas", driver="GPKG")
    sz.to_file(out, layer="subzones", driver="GPKG")
    land.to_file(out, layer="land", driver="GPKG")
    write_provenance(
        out,
        stage="boundaries",
        stage_version=STAGE_VERSION,
        config_digest=cfg.aoi.digest(),
        inputs=(_upstream(ctx, cfg.datagov.planning_areas), _upstream(ctx, cfg.datagov.subzones)),
    )
    log.info(
        "boundaries: %d planning areas, %d subzones, land area %.1f km²",
        len(pa),
        len(sz),
        land.area.iloc[0] / 1e6,
    )


def load_boundaries(ctx: RunContext) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, shapely.Geometry]:
    """Planning areas, subzones and land polygon written by :func:`boundaries`."""
    path = ctx.paths.boundaries
    pa = gpd.read_file(path, layer="planning_areas")
    sz = gpd.read_file(path, layer="subzones")
    land = gpd.read_file(path, layer="land").geometry.iloc[0]
    return pa, sz, land


def build_street_bridge(ctx: RunContext) -> pd.DataFrame:
    """Rebuild the street code bridge (needs the legacy geocoded table for spatial votes)."""
    cfg = ctx.config
    props = hdb.load_properties(
        pd.read_csv(datagov_file(ctx, cfg.datagov.hdb_property), dtype={"blk_no": str})
    )
    fps = hdb.load_footprints(
        gpd.read_file(datagov_file(ctx, cfg.datagov.hdb_footprints)), cfg.aoi.crs_epsg
    )
    spatial = None
    legacy = cfg.paths.legacy_geocodes_csv
    if legacy is not None and legacy.exists():
        g = pd.read_csv(legacy, dtype={"blk_no": str})
        g["blk_no"] = streets.normalise_block(g["blk_no"])
        g["street"] = streets.normalise_street(g["street"])
        pts = gpd.GeoDataFrame(
            g[["blk_no", "street"]],
            geometry=gpd.points_from_xy(g["LONGITUDE"], g["LATITUDE"]),
            crs=4326,
        ).to_crs(epsg=cfg.aoi.crs_epsg)
        spatial = streets.spatial_votes(fps, pts)
        log.info("spatial votes from %d legacy geocodes", len(g))
    else:
        log.warning("no legacy geocodes configured; bridge relies on block sets only")
    bridge = streets.build_bridge(fps, props, spatial)
    path = ctx.paths.street_bridge
    path.parent.mkdir(parents=True, exist_ok=True)
    bridge.to_csv(path, index=False, float_format="%.4f")
    log.info("street bridge: %s", bridge["method"].value_counts().to_dict())
    return bridge


def buildings(ctx: RunContext, rebuild_bridge: bool = False) -> None:
    """Join HDB property records to footprints and write the block table."""
    cfg = ctx.config
    if rebuild_bridge or not ctx.paths.street_bridge.exists():
        bridge = build_street_bridge(ctx)
    else:
        bridge = pd.read_csv(ctx.paths.street_bridge, dtype={"st_cod": str, "street": str})
    props = hdb.load_properties(
        pd.read_csv(datagov_file(ctx, cfg.datagov.hdb_property), dtype={"blk_no": str})
    )
    fps = hdb.load_footprints(
        gpd.read_file(datagov_file(ctx, cfg.datagov.hdb_footprints)), cfg.aoi.crs_epsg
    )
    blocks, unmatched, report = hdb.join_blocks(props, fps, bridge)
    blocks["footprint_area_m2"] = blocks.geometry.area
    out = ctx.paths.hdb_blocks
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks.to_parquet(out)
    write_provenance(
        out,
        stage="buildings",
        stage_version=STAGE_VERSION,
        config_digest=cfg.datagov.digest(),
        inputs=(
            _upstream(ctx, cfg.datagov.hdb_property),
            _upstream(ctx, cfg.datagov.hdb_footprints),
            local_input(ctx.paths.street_bridge),
        ),
        extra={
            "match_rate": report.match_rate,
            "residential_match_rate": report.residential_match_rate,
        },
    )
    summary = {
        **asdict(report),
        "match_rate": report.match_rate,
        "residential_match_rate": report.residential_match_rate,
    }
    report_path = ctx.paths.out / "hdb_join_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    unmatched.to_csv(ctx.paths.out / "hdb_unmatched.csv", index=False)
    log.info(
        "HDB blocks: %d of %d records matched (%.1f%%), residential %.1f%%",
        report.n_matched,
        report.n_properties,
        100 * report.match_rate,
        100 * report.residential_match_rate,
    )
