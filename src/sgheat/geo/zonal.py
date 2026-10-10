"""Zonal statistics through a precomputed sparse coverage matrix.

For a set of zones and a raster grid, ``C[z, p]`` is the fraction of pixel ``p``
covered by zone ``z`` (computed exactly by exactextract). Built once, the matrix
turns every per-scene statistic into a sparse matrix product:

* coverage-weighted mean of ``v`` over valid pixels ``m``: ``C (v m) / C m``,
* coverage-weighted sum (for counts such as population): ``C v``.

Sums are mass conserving: summed over zones that tile an area they equal the
raster total over that area. A zone with no valid pixel gets NaN, never 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from exactextract import exact_extract
from exactextract.raster import NumPyRasterSource
from numpy.typing import NDArray
from pyproj import CRS

from sgheat.geo.aoi import PixelGrid

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CoverageMatrix:
    """Sparse ``zones x pixels`` coverage fractions for one zone set on one raster grid."""

    matrix: sp.csr_array
    zone_ids: tuple[str, ...]
    raster_shape: tuple[int, int]

    @property
    def n_zones(self) -> int:
        return len(self.zone_ids)

    @classmethod
    def from_frame(
        cls, frame: pd.DataFrame, zone_ids: list[str], raster_shape: tuple[int, int]
    ) -> CoverageMatrix:
        """Assemble from exactextract output with list columns ``cell_id`` and ``coverage``."""
        rows: list[NDArray[np.int64]] = []
        cols: list[NDArray[np.int64]] = []
        vals: list[FloatArray] = []
        for i, (cells, cover) in enumerate(zip(frame["cell_id"], frame["coverage"], strict=True)):
            cells_arr = np.asarray(cells, dtype=np.int64)
            rows.append(np.full(cells_arr.shape, i, dtype=np.int64))
            cols.append(cells_arr)
            vals.append(np.asarray(cover, dtype=np.float64))
        n_pixels = raster_shape[0] * raster_shape[1]
        matrix = sp.csr_array(
            (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
            shape=(len(zone_ids), n_pixels),
        )
        matrix.sum_duplicates()
        return cls(matrix=matrix, zone_ids=tuple(zone_ids), raster_shape=raster_shape)

    def save(self, path: Path) -> None:
        """Write to a compressed ``.npz`` file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        m = self.matrix
        np.savez_compressed(
            path,
            data=m.data,
            indices=m.indices,
            indptr=m.indptr,
            shape=np.asarray(m.shape),
            raster_shape=np.asarray(self.raster_shape),
            zone_ids=np.asarray(self.zone_ids, dtype=object),
        )

    @classmethod
    def load(cls, path: Path) -> CoverageMatrix:
        """Read a matrix written by :meth:`save`."""
        with np.load(path, allow_pickle=True) as z:
            matrix = sp.csr_array(
                (z["data"], z["indices"], z["indptr"]), shape=tuple(int(s) for s in z["shape"])
            )
            raster_shape = (int(z["raster_shape"][0]), int(z["raster_shape"][1]))
            zone_ids = tuple(str(s) for s in z["zone_ids"])
        return cls(matrix=matrix, zone_ids=zone_ids, raster_shape=raster_shape)

    def _flat(self, array: NDArray[np.generic]) -> NDArray[np.generic]:
        if array.shape != self.raster_shape:
            msg = f"raster shape {array.shape} does not match coverage grid {self.raster_shape}"
            raise ValueError(msg)
        return array.reshape(-1)

    def weight(self, mask: NDArray[np.bool_] | None = None) -> FloatArray:
        """Covered pixel count per zone, optionally restricted to ``mask``."""
        if mask is None:
            return np.asarray(self.matrix.sum(axis=1), dtype=np.float64).reshape(-1)
        m = self._flat(mask).astype(np.float64)
        return np.asarray(self.matrix @ m, dtype=np.float64)

    def mean(
        self, values: NDArray[np.floating], mask: NDArray[np.bool_] | None = None
    ) -> tuple[FloatArray, FloatArray]:
        """Coverage-weighted mean over pixels where ``mask`` is true and ``values`` is finite.

        Returns ``(mean, weight)``; zones without valid pixels get NaN and weight 0.
        """
        v = self._flat(values).astype(np.float64)
        valid = np.isfinite(v)
        if mask is not None:
            valid &= self._flat(mask).astype(bool)
        w = valid.astype(np.float64)
        num = np.asarray(self.matrix @ np.where(valid, v, 0.0), dtype=np.float64)
        den = np.asarray(self.matrix @ w, dtype=np.float64)
        mean = np.full(den.shape, np.nan)
        np.divide(num, den, out=mean, where=den > 0)
        return mean, den

    def total(self, values: NDArray[np.floating]) -> FloatArray:
        """Coverage-weighted sum; NaN pixels contribute nothing, all-NaN zones get NaN."""
        v = self._flat(values).astype(np.float64)
        valid = np.isfinite(v)
        num = np.asarray(self.matrix @ np.where(valid, v, 0.0), dtype=np.float64)
        has_data = np.asarray(self.matrix @ valid.astype(np.float64), dtype=np.float64) > 0
        return np.where(has_data, num, np.nan)


def coverage_on_grid(
    geometries: list[object], zone_ids: list[str], grid: PixelGrid
) -> CoverageMatrix:
    """Coverage matrix of zone geometries (in the grid CRS) on an analysis pixel grid."""
    left, bottom, right, top = grid.bounds
    template = NumPyRasterSource(
        np.zeros(grid.shape, dtype=np.uint8),
        xmin=left,
        ymin=bottom,
        xmax=right,
        ymax=top,
        nodata=None,
        srs_wkt=CRS.from_epsg(grid.crs_epsg).to_wkt(),
    )
    return _extract(template, geometries, zone_ids, grid.shape, grid.crs_epsg)


def coverage_on_raster(
    geometries: list[object], zone_ids: list[str], raster_path: Path, crs_epsg: int
) -> CoverageMatrix:
    """Coverage matrix of zone geometries (in ``crs_epsg``) on the grid of a raster file."""
    import rasterio  # noqa: PLC0415  (rasterio import is heavy, keep it local)

    with rasterio.open(raster_path) as src:
        shape = (src.height, src.width)
        if src.crs is None or src.crs.to_epsg() != crs_epsg:
            msg = f"{raster_path} is not in EPSG:{crs_epsg}"
            raise ValueError(msg)
    return _extract(str(raster_path), geometries, zone_ids, shape, crs_epsg)


def _extract(
    raster: object,
    geometries: list[object],
    zone_ids: list[str],
    shape: tuple[int, int],
    crs_epsg: int,
) -> CoverageMatrix:
    import geopandas as gpd  # noqa: PLC0415

    zones = gpd.GeoDataFrame({"zone_id": zone_ids}, geometry=geometries, crs=crs_epsg)
    frame = exact_extract(
        raster, zones, ["cell_id", "coverage"], include_cols=["zone_id"], output="pandas"
    )
    frame = frame.set_index("zone_id").reindex(zone_ids)
    if frame["cell_id"].isna().any():
        missing = frame.index[frame["cell_id"].isna()].tolist()[:5]
        msg = f"zones without coverage on the raster grid, for example {missing}"
        raise ValueError(msg)
    return CoverageMatrix.from_frame(frame.reset_index(), zone_ids, shape)
