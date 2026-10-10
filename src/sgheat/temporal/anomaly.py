"""Separating where it is hot from when it was hot.

Surface temperature at zone ``h`` in scene ``s`` is decomposed as

    L(h, s) = mu + alpha(h) + tau(s) + e(h, s)

by Tukey's median polish on the incomplete zone-by-scene matrix (clouds hide
different zones in different scenes). ``alpha`` is the relative surface heat of
a zone, comparable across zones even when they were observed on different days;
``tau`` absorbs the island-wide level of each scene (season, weather, sensor).
Medians make the fit robust to residual cloud edges and odd scenes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class TwoWayFit:
    """Result of a two-way median polish."""

    overall: float
    zone_effect: FloatArray  # alpha(h)
    scene_effect: FloatArray  # tau(s)
    residual: FloatArray  # e(h, s), NaN where L was missing
    iterations: int
    converged: bool

    def anomaly(self) -> FloatArray:
        """``L - mu - tau(s)``: the zone's departure from the scene level, per scene."""
        return self.zone_effect[:, None] + self.residual


def _nanmedian_or_zero(values: FloatArray, axis: int) -> FloatArray:
    counts = np.sum(np.isfinite(values), axis=axis)
    out = np.zeros(counts.shape, dtype=np.float64)
    has = counts > 0
    if axis == 1:
        out[has] = np.nanmedian(values[has, :], axis=1)
    else:
        out[has] = np.nanmedian(values[:, has], axis=0)
    return out


def median_polish(matrix: FloatArray, max_iter: int = 50, tol: float = 1e-4) -> TwoWayFit:
    """Tukey median polish of a zones-by-scenes matrix with missing values (NaN).

    Stops when the largest change of any effect in an iteration falls below ``tol``.
    """
    resid = np.array(matrix, dtype=np.float64, copy=True)
    n_zones, n_scenes = resid.shape
    overall = 0.0
    rows = np.zeros(n_zones)
    cols = np.zeros(n_scenes)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007
        row_med = _nanmedian_or_zero(resid, axis=1)
        resid -= row_med[:, None]
        rows += row_med
        col_shift = float(np.median(cols)) if n_scenes else 0.0
        cols -= col_shift
        overall += col_shift

        col_med = _nanmedian_or_zero(resid, axis=0)
        resid -= col_med[None, :]
        cols += col_med
        row_shift = float(np.median(rows)) if n_zones else 0.0
        rows -= row_shift
        overall += row_shift

        change = max(
            float(np.max(np.abs(row_med), initial=0.0)),
            float(np.max(np.abs(col_med), initial=0.0)),
        )
        if change < tol:
            converged = True
            break
    return TwoWayFit(
        overall=overall,
        zone_effect=rows,
        scene_effect=cols,
        residual=resid,
        iterations=iterations,
        converged=converged,
    )


def scene_median_anomaly(matrix: FloatArray) -> FloatArray:
    """Simpler cross-check: each value minus the median over zones of its scene."""
    med = np.nanmedian(matrix, axis=0)
    return np.asarray(matrix - med[None, :], dtype=np.float64)
