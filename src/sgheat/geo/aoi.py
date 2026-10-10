"""Study area: Singapore's land polygon and the analysis pixel grid."""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import shapely
from affine import Affine
from numpy.typing import NDArray
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry

from sgheat.config import AoiConfig


@dataclass(frozen=True)
class PixelGrid:
    """A north-up raster grid in a projected CRS."""

    transform: Affine
    width: int
    height: int
    crs_epsg: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform.c, self.transform.f
        return (
            left,
            top + self.transform.e * self.height,
            left + self.transform.a * self.width,
            top,
        )

    @property
    def pixel_area_m2(self) -> float:
        return abs(self.transform.a * self.transform.e)


def land_polygon(planning_areas: gpd.GeoDataFrame, crs_epsg: int) -> BaseGeometry:
    """Union of the Master Plan planning areas (no sea), repaired and projected."""
    projected = planning_areas.to_crs(epsg=crs_epsg)
    geom = shapely.make_valid(projected.geometry.union_all())
    return shapely.normalize(geom)


def snap_down(value: float, step: float, phase: float) -> float:
    """Largest ``phase + k * step`` that is not greater than ``value``."""
    return phase + math.floor((value - phase) / step) * step


def snap_up(value: float, step: float, phase: float) -> float:
    """Smallest ``phase + k * step`` that is not less than ``value``."""
    return phase + math.ceil((value - phase) / step) * step


def analysis_grid(land: BaseGeometry, cfg: AoiConfig) -> PixelGrid:
    """Pixel grid around ``land`` that shares the Landsat pixel lattice (no resampling)."""
    minx, miny, maxx, maxy = land.bounds
    step, phase = cfg.pixel_size_m, cfg.pixel_phase_m
    left = snap_down(minx - cfg.buffer_m, step, phase)
    bottom = snap_down(miny - cfg.buffer_m, step, phase)
    right = snap_up(maxx + cfg.buffer_m, step, phase)
    top = snap_up(maxy + cfg.buffer_m, step, phase)
    width = round((right - left) / step)
    height = round((top - bottom) / step)
    transform = Affine(step, 0.0, left, 0.0, -step, top)
    return PixelGrid(transform=transform, width=width, height=height, crs_epsg=cfg.crs_epsg)


def same_lattice(transform: Affine, grid: PixelGrid, tol: float = 1e-6) -> bool:
    """True when ``transform`` has the grid's pixel size and phase, so windows align exactly."""
    if not math.isclose(transform.a, grid.transform.a) or not math.isclose(
        transform.e, grid.transform.e
    ):
        return False
    dx = (transform.c - grid.transform.c) / grid.transform.a
    dy = (transform.f - grid.transform.f) / grid.transform.e
    return abs(dx - round(dx)) < tol and abs(dy - round(dy)) < tol


def land_mask(land: BaseGeometry, grid: PixelGrid) -> NDArray[np.bool_]:
    """Pixels whose centre lies on land."""
    mask = rasterize(
        [(land, 1)],
        out_shape=grid.shape,
        transform=grid.transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    return np.asarray(mask, dtype=bool)
