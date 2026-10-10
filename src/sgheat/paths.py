"""Canonical locations of every artifact the pipeline reads or writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    """Directory layout below ``data_dir``.

    ``raw`` holds untouched downloads, ``interim`` reusable intermediate tables,
    ``scenes`` one small table per processed Landsat scene, and ``out`` the
    analysis results that feed the web export.
    """

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def interim(self) -> Path:
        return self.root / "interim"

    @property
    def scenes(self) -> Path:
        return self.root / "scenes"

    @property
    def out(self) -> Path:
        return self.root / "out"

    @property
    def reference(self) -> Path:
        return self.root / "reference"

    @property
    def catalog_dir(self) -> Path:
        return self.root / "catalog"

    # Raw downloads
    def datagov(self, dataset_id: str, suffix: str) -> Path:
        return self.raw / "datagov" / f"{dataset_id}{suffix}"

    def worldpop(self, year: int) -> Path:
        return self.raw / "worldpop" / f"sgp_pop_{year}_CN_100m_R2025A_v1.tif"

    # Interim artifacts
    @property
    def boundaries(self) -> Path:
        return self.interim / "boundaries.gpkg"

    @property
    def hdb_blocks(self) -> Path:
        return self.interim / "hdb_blocks.parquet"

    @property
    def street_bridge(self) -> Path:
        return self.reference / "hdb_street_codes.csv"

    def grid(self, radius_m: int) -> Path:
        return self.interim / f"grid_r{radius_m}.parquet"

    def coverage(self, zone_set: str, raster: str) -> Path:
        return self.interim / "coverage" / f"{zone_set}__{raster}.npz"

    @property
    def landmask(self) -> Path:
        return self.interim / "landmask.npz"

    # Scenes
    @property
    def catalog(self) -> Path:
        return self.catalog_dir / "scenes.csv"

    def scene_stats(self, item_id: str) -> Path:
        return self.scenes / f"{item_id}.parquet"

    @property
    def scene_zone_stats(self) -> Path:
        return self.interim / "scene_zone_stats.parquet"

    # Results
    def temporal(self, zone_set: str) -> Path:
        return self.out / f"temporal_{zone_set}.parquet"

    def features(self, zone_set: str) -> Path:
        return self.out / f"features_{zone_set}.parquet"

    def model(self, zone_set: str) -> Path:
        return self.out / f"model_{zone_set}.json"

    def model_zones(self, zone_set: str) -> Path:
        return self.out / f"model_zones_{zone_set}.parquet"

    @property
    def physics_report(self) -> Path:
        return self.out / "physics_report.json"


def zone_set_name(radius_m: int) -> str:
    """Name of the hexagon zone set with the given circumradius."""
    return f"r{radius_m}"
