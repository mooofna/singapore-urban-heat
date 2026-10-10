"""Conversion of Landsat Collection 2 Level-2 digital numbers to physical units."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]

# Valid DN range of Collection 2 surface reflectance (USGS Level-2 product guide).
SR_VALID_DN = (7273, 43636)


@dataclass(frozen=True)
class BandScaling:
    """Linear scaling ``value = dn * scale + offset`` with a nodata DN."""

    scale: float
    offset: float = 0.0
    nodata: float | None = None

    @classmethod
    def from_raster_bands(cls, raster_bands: list[Mapping[str, Any]]) -> BandScaling:
        """Build from the STAC ``raster:bands`` entry of an asset."""
        band = raster_bands[0]
        return cls(
            scale=float(band.get("scale", 1.0)),
            offset=float(band.get("offset", 0.0)),
            nodata=None if band.get("nodata") is None else float(band["nodata"]),
        )


# Constants published for every Collection 2 Level-2 item (checked against STAC metadata in tests).
SURFACE_TEMPERATURE = BandScaling(scale=0.00341802, offset=149.0, nodata=0)
SURFACE_REFLECTANCE = BandScaling(scale=2.75e-5, offset=-0.2, nodata=0)
# Intermediate surface temperature bands used by the educational radiative transfer inversion.
ST_RADIANCE = BandScaling(scale=0.001, offset=0.0, nodata=-9999)  # TRAD, URAD, DRAD
ST_UNITLESS = BandScaling(scale=0.0001, offset=0.0, nodata=-9999)  # ATRAN, EMIS, EMSD


def apply_scaling(
    dn: NDArray[Any],
    scaling: BandScaling,
    valid_range: tuple[float, float] | None = None,
) -> FloatArray:
    """Scale ``dn`` to physical units; nodata and out-of-range values become NaN."""
    raw = np.asarray(dn)
    out = (raw.astype(np.float64) * scaling.scale + scaling.offset).astype(np.float32)
    invalid = np.zeros(raw.shape, dtype=bool)
    if scaling.nodata is not None:
        invalid |= raw == scaling.nodata
    if valid_range is not None:
        invalid |= (raw < valid_range[0]) | (raw > valid_range[1])
    out[invalid] = np.nan
    return out


def surface_temperature_kelvin(dn: NDArray[Any]) -> FloatArray:
    """``ST_B10`` digital numbers to surface temperature in kelvin."""
    return apply_scaling(dn, SURFACE_TEMPERATURE)


def surface_reflectance(dn: NDArray[Any]) -> FloatArray:
    """``SR_B*`` digital numbers to unitless surface reflectance."""
    return apply_scaling(dn, SURFACE_REFLECTANCE, valid_range=SR_VALID_DN)


def kelvin_to_celsius(kelvin: FloatArray) -> FloatArray:
    """Convert kelvin to degrees Celsius."""
    return (kelvin - np.float32(273.15)).astype(np.float32)
