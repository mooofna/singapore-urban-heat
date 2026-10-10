"""Flat-top hexagon grids with stable axial coordinates.

Geometry of a flat-top hexagon with circumradius ``R`` (equal to the edge length):

* vertices at angles 0, 60, ..., 300 degrees from the centre,
* width between opposite vertices ``2 R``, between opposite edges ``sqrt(3) R``,
* area ``3 sqrt(3) / 2 * R^2``.

Centres use axial coordinates ``(q, r)``: ``x = 1.5 R q`` and
``y = sqrt(3) R (r + q / 2)`` relative to a fixed origin, so a hexagon keeps its
identifier however the study area changes. The six neighbours of ``(q, r)`` are
``(q + dq, r + dr)`` for the offsets in :data:`NEIGHBOUR_OFFSETS`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import NDArray
from shapely.geometry.base import BaseGeometry

SQRT3 = math.sqrt(3.0)
NEIGHBOUR_OFFSETS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
)
IntArray = NDArray[np.int64]
# Vertex offsets at 0, 60, ..., 300 degrees in units of (R / 2, sqrt(3) R / 2).
_VERTEX_DX = np.array([2, 1, -1, -2, -1, 1], dtype=np.int64)
_VERTEX_DY = np.array([0, 1, 1, 0, -1, -1], dtype=np.int64)
FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class HexGridSpec:
    """A flat-top hexagon lattice in a projected CRS."""

    radius_m: float
    origin_x: float = 0.0
    origin_y: float = 0.0

    @property
    def area_m2(self) -> float:
        """Area of one hexagon."""
        return 1.5 * SQRT3 * self.radius_m**2

    @property
    def flat_width_m(self) -> float:
        """Distance between opposite edges."""
        return SQRT3 * self.radius_m

    def _to_xy(self, kx: IntArray, ky: IntArray) -> tuple[FloatArray, FloatArray]:
        # Points of the lattice spanned by half an edge horizontally and half a flat width
        # vertically. Integer multipliers make shared vertices of neighbours bit-identical.
        x = self.origin_x + self.radius_m * (np.asarray(kx, dtype=np.float64) / 2.0)
        y = self.origin_y + (SQRT3 * self.radius_m / 2.0) * np.asarray(ky, dtype=np.float64)
        return x, y

    def centres(self, q: IntArray, r: IntArray) -> tuple[FloatArray, FloatArray]:
        """Projected coordinates of the hexagon centres."""
        q = np.asarray(q, dtype=np.int64)
        r = np.asarray(r, dtype=np.int64)
        return self._to_xy(3 * q, 2 * r + q)

    def axial(self, x: FloatArray, y: FloatArray) -> tuple[IntArray, IntArray]:
        """Axial coordinates of the hexagons that contain the given points (cube rounding)."""
        px = (np.asarray(x, dtype=np.float64) - self.origin_x) / self.radius_m
        py = (np.asarray(y, dtype=np.float64) - self.origin_y) / self.radius_m
        qf = (2.0 / 3.0) * px
        rf = -px / 3.0 + (SQRT3 / 3.0) * py
        sf = -qf - rf
        q = np.rint(qf)
        r = np.rint(rf)
        s = np.rint(sf)
        dq, dr, ds = np.abs(q - qf), np.abs(r - rf), np.abs(s - sf)
        fix_q = (dq > dr) & (dq > ds)
        fix_r = ~fix_q & (dr > ds)
        q = np.where(fix_q, -r - s, q)
        r = np.where(fix_r, -q - s, r)
        return q.astype(np.int64), r.astype(np.int64)

    def polygons(self, q: IntArray, r: IntArray) -> NDArray[np.object_]:
        """Hexagon polygons for the given axial coordinates."""
        q = np.asarray(q, dtype=np.int64)[:, None]
        r = np.asarray(r, dtype=np.int64)[:, None]
        vx, vy = self._to_xy(3 * q + _VERTEX_DX[None, :], 2 * r + q + _VERTEX_DY[None, :])
        coords = np.stack([vx, vy], axis=-1)
        return np.asarray(shapely.polygons(coords), dtype=object)


def candidate_axial(
    spec: HexGridSpec, bounds: tuple[float, float, float, float]
) -> tuple[IntArray, IntArray]:
    """All axial coordinates whose hexagons can intersect the bounding box."""
    minx, miny, maxx, maxy = bounds
    pad = 2 * spec.radius_m
    q_lo = math.floor((minx - pad - spec.origin_x) / (1.5 * spec.radius_m))
    q_hi = math.ceil((maxx + pad - spec.origin_x) / (1.5 * spec.radius_m))
    qs: list[IntArray] = []
    rs: list[IntArray] = []
    for q in range(q_lo, q_hi + 1):
        r_lo = math.floor((miny - pad - spec.origin_y) / (SQRT3 * spec.radius_m) - q / 2.0)
        r_hi = math.ceil((maxy + pad - spec.origin_y) / (SQRT3 * spec.radius_m) - q / 2.0)
        r = np.arange(r_lo, r_hi + 1, dtype=np.int64)
        qs.append(np.full(r.shape, q, dtype=np.int64))
        rs.append(r)
    return np.concatenate(qs), np.concatenate(rs)


def build_grid(
    land: BaseGeometry,
    spec: HexGridSpec,
    min_land_frac: float,
    crs: str | int,
) -> gpd.GeoDataFrame:
    """Hexagons covering ``land`` with at least ``min_land_frac`` of their area on land.

    Returns one row per hexagon, sorted by ``(q, r)``, with columns ``zone_id``
    (``"r{R}:{q}:{r}"``), ``q``, ``r``, ``land_area_m2``, ``land_frac``, the full
    hexagon ``geometry`` and the land part ``land_geometry`` (WKB-free shapely objects).
    """
    q, r = candidate_axial(spec, land.bounds)
    hexes = spec.polygons(q, r)
    shapely.prepare(land)
    touching = shapely.intersects(land, hexes)
    q, r, hexes = q[touching], r[touching], hexes[touching]
    land_parts = shapely.intersection(hexes, land)
    land_area = shapely.area(land_parts)
    land_frac = land_area / spec.area_m2
    keep = land_frac >= min_land_frac
    frame = pd.DataFrame(
        {
            "zone_id": [
                f"r{round(spec.radius_m)}:{qq}:{rr}"
                for qq, rr in zip(q[keep], r[keep], strict=True)
            ],
            "q": q[keep],
            "r": r[keep],
            "land_area_m2": land_area[keep],
            "land_frac": land_frac[keep],
            "land_geometry": land_parts[keep],
        }
    )
    grid = gpd.GeoDataFrame(frame, geometry=list(hexes[keep]), crs=crs)
    return grid.sort_values(["q", "r"], kind="stable").reset_index(drop=True)


def adjacency(q: IntArray, r: IntArray) -> tuple[IntArray, IntArray]:
    """Edge-sharing neighbour pairs ``(focal, neighbour)`` as row indices into ``q`` and ``r``."""
    index = {(int(qq), int(rr)): i for i, (qq, rr) in enumerate(zip(q, r, strict=True))}
    focal: list[int] = []
    neighbour: list[int] = []
    for i, (qq, rr) in enumerate(zip(q, r, strict=True)):
        for dq, dr in NEIGHBOUR_OFFSETS:
            j = index.get((int(qq) + dq, int(rr) + dr))
            if j is not None:
                focal.append(i)
                neighbour.append(j)
    return np.asarray(focal, dtype=np.int64), np.asarray(neighbour, dtype=np.int64)
