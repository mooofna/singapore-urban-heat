"""Typed run configuration, loaded from TOML.

Every tunable number of the pipeline lives here so that a run is fully described
by its config file plus the pinned lockfile. ``Config.digest()`` gives a stable
hash that provenance sidecars record.
"""

from __future__ import annotations

import hashlib
import tomllib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def digest(self) -> str:
        """SHA-256 of the canonical JSON form of this section."""
        payload = self.model_dump_json(round_trip=True).encode()
        return hashlib.sha256(payload).hexdigest()


class PathsConfig(_Section):
    """Where data lives. Relative paths are resolved against the working directory."""

    data_dir: Path = Path("data")
    web_data_dir: Path = Path("web/static/data")
    # Optional local copy of the 2018-05-24 Level-2 scene (offline validation and fixtures).
    local_l2_dir: Path | None = None
    # Optional local copy of the matching Level-1 band 10 (educational LST comparison).
    local_l1_dir: Path | None = None
    # Optional legacy geocoded HDB table; only used to cross-check the street bridge.
    legacy_geocodes_csv: Path | None = None
    # Folder of Level-2 product folders used when ``scenes.source = "local"`` (offline runs, CI).
    local_scenes_dir: Path | None = None


class DataGovConfig(_Section):
    """data.gov.sg dataset identifiers (Singapore Open Data Licence)."""

    hdb_property: str = "d_17f5382f26140b1fdae0ba2ef6239d2f"
    hdb_footprints: str = "d_16b157c52ed637edd6ba1232e026258d"
    planning_areas: str = "d_4765db0e87b9c86336792efe8a1f7a66"
    subzones: str = "d_8594ae9ff96d0c708bc2af633048edfb"
    min_seconds_between_downloads: float = 6.0


class WorldPopConfig(_Section):
    """WorldPop R2025A constrained 100 m population counts (CC BY 4.0)."""

    url_template: str = (
        "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/{year}/SGP/v1/100m/"
        "constrained/sgp_pop_{year}_CN_100m_R2025A_v1.tif"
    )
    years: tuple[int, ...] = (2023,)


class AoiConfig(_Section):
    """Analysis grid. Landsat pixel edges in UTM 48N sit at 15 m modulo 30 m."""

    crs_epsg: int = 32648
    pixel_size_m: float = 30.0
    pixel_phase_m: float = 15.0
    buffer_m: float = 1000.0


class ScenesConfig(_Section):
    """Landsat scene discovery and screening."""

    # "stac" queries Planetary Computer; "local" reads product folders from paths.local_scenes_dir.
    source: Literal["stac", "local"] = "stac"
    stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    collection: str = "landsat-c2-l2"
    platforms: tuple[str, ...] = ("landsat-8", "landsat-9")
    wrs_path: str = "125"
    wrs_row: str = "059"
    collection_category: str = "T1"
    start: date = date(2013, 4, 11)
    end: date | None = None
    max_cloud_cover_land: float = Field(80.0, ge=0, le=100)
    # A scene is processed when at least this share of Singapore's land is clear.
    min_scene_clear_frac: float = Field(0.3, ge=0, le=1)
    # A zone value is kept when this share of its land is clear and enough pixels remain.
    min_zone_clear_frac: float = Field(0.7, ge=0, le=1)
    min_zone_pixels: float = Field(10.0, ge=1)
    # Monthly updates re-query this many days to catch late ingestion or reprocessing.
    recheck_days: int = 90


class GridConfig(_Section):
    """Flat-top hexagon grids. ``radius_m`` is the circumradius (equal to the edge length)."""

    radii_m: tuple[int, ...] = (200, 300, 400, 600)
    primary_radius_m: int = 200
    min_land_frac: float = Field(0.5, gt=0, le=1)

    @model_validator(mode="after")
    def _primary_in_radii(self) -> GridConfig:
        if self.primary_radius_m not in self.radii_m:
            msg = "primary_radius_m must be one of radii_m"
            raise ValueError(msg)
        return self


class TemporalConfig(_Section):
    """Compositing and trend settings."""

    min_obs: int = Field(5, ge=1)
    trend_min_obs: int = Field(20, ge=3)
    trend_min_years: float = Field(8.0, gt=0)
    polish_max_iter: int = Field(50, ge=1)
    polish_tol: float = Field(1e-4, gt=0)
    fdr_alpha: float = Field(0.05, gt=0, lt=1)


class ModelConfig(_Section):
    """Cross-sectional model of relative surface heat on urban form."""

    period_start: date = date(2021, 1, 1)
    period_end: date = date(2025, 12, 31)
    worldpop_year: int = 2023
    # HDB blocks completed after this year are excluded (construction sites during the period).
    hdb_completed_by: int = 2020
    # hdb_coverage is left out: it is collinear with hdb_far (VIF about 20 on the 200 m grid).
    variables: tuple[str, ...] = (
        "ndvi",
        "water_frac",
        "pop_density",
        "hdb_far",
        "hdb_commercial",
        "dist_coast_km",
    )
    # Spatially smooth covariates whose spatial lag would nearly duplicate them in the Durbin model.
    durbin_exclude: tuple[str, ...] = ("dist_coast_km",)
    impact_draws: int = Field(2000, ge=100)
    lisa_permutations: int = Field(9999, ge=99)
    seed: int = 20180524


class Config(_Section):
    """Full pipeline configuration."""

    paths: PathsConfig = PathsConfig()
    datagov: DataGovConfig = DataGovConfig()
    worldpop: WorldPopConfig = WorldPopConfig()
    aoi: AoiConfig = AoiConfig()
    scenes: ScenesConfig = ScenesConfig()
    grid: GridConfig = GridConfig()
    temporal: TemporalConfig = TemporalConfig()
    model: ModelConfig = ModelConfig()

    @model_validator(mode="after")
    def _local_scenes_need_folder(self) -> Config:
        if self.scenes.source == "local" and self.paths.local_scenes_dir is None:
            msg = 'scenes.source = "local" needs paths.local_scenes_dir'
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _worldpop_covers_model_year(self) -> Config:
        if self.model.worldpop_year not in self.worldpop.years:
            msg = "model.worldpop_year must be listed in worldpop.years"
            raise ValueError(msg)
        return self


def load_config(path: Path | None) -> Config:
    """Load a TOML config file; ``None`` returns the defaults."""
    if path is None:
        return Config()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return Config.model_validate(data)
