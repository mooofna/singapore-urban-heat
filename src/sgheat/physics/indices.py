"""Spectral indices computed on surface reflectance (never on raw digital numbers)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]


def normalized_difference(a: FloatArray, b: FloatArray) -> FloatArray:
    """``(a - b) / (a + b)``; NaN where an input is NaN or the denominator is not positive."""
    a64 = np.asarray(a, dtype=np.float64)
    b64 = np.asarray(b, dtype=np.float64)
    denom = a64 + b64
    out = np.full(np.broadcast_shapes(a64.shape, b64.shape), np.nan, dtype=np.float64)
    ok = np.isfinite(denom) & (denom > 0)
    np.divide(a64 - b64, denom, out=out, where=ok)
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def ndvi(red: FloatArray, nir: FloatArray) -> FloatArray:
    """Normalized Difference Vegetation Index (Landsat 8/9 bands 4 and 5)."""
    return normalized_difference(nir, red)


def mndwi(green: FloatArray, swir1: FloatArray) -> FloatArray:
    """Modified Normalized Difference Water Index (Xu 2006; Landsat 8/9 bands 3 and 6)."""
    return normalized_difference(green, swir1)
