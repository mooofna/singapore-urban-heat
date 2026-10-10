"""Land surface temperature from first principles, for teaching and validation.

The pipeline uses the USGS Level-2 surface temperature product. This module keeps
the textbook derivation that the original course project implemented and shows,
step by step, how close each simplification gets to the operational product:

1. Brightness temperature: TOA radiance of TIRS band 10 inverted with Planck's law.
2. Single-channel correction: brightness temperature corrected for an emissivity
   estimated from NDVI thresholds (Sobrino et al. 2004; Avdan and Jovanovska 2016).
   No atmospheric correction.
3. Radiative transfer inversion with the atmospheric terms that USGS ships in the
   Level-2 product (transmission, upwelled and downwelled radiance, ASTER GED based
   emissivity). This reproduces ``ST_B10`` up to quantisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]

# Second radiation constant h*c/k_B in m*K.
RHO_MK = 1.438777e-2
# Effective centre wavelength of TIRS band 10 in metres.
TIRS_B10_WAVELENGTH_M = 10.895e-6


@dataclass(frozen=True)
class ThermalConstants:
    """Calibration constants of TIRS band 10 from the scene metadata (MTL)."""

    k1: float
    k2: float


# Values from the Collection 2 MTL files (``K1_CONSTANT_BAND_10`` and ``K2_CONSTANT_BAND_10``).
THERMAL_CONSTANTS = {
    "landsat-8": ThermalConstants(k1=774.8853, k2=1321.0789),
    "landsat-9": ThermalConstants(k1=799.0284, k2=1329.2405),
}


def dn_to_radiance(dn: NDArray[Any], mult: float, add: float) -> FloatArray:
    """Level-1 digital numbers to TOA spectral radiance in W/(m^2 sr um); DN 0 is fill."""
    raw = np.asarray(dn)
    out = (raw.astype(np.float64) * mult + add).astype(np.float32)
    out[raw == 0] = np.nan
    return out


def brightness_temperature(radiance: FloatArray, constants: ThermalConstants) -> FloatArray:
    """Invert Planck's law: ``T = K2 / ln(K1 / L + 1)`` in kelvin."""
    rad = np.asarray(radiance, dtype=np.float64)
    out = np.full(rad.shape, np.nan)
    ok = np.isfinite(rad) & (rad > 0)
    out[ok] = constants.k2 / np.log(constants.k1 / rad[ok] + 1.0)
    return out.astype(np.float32)


def planck_radiance(temperature_k: FloatArray, constants: ThermalConstants) -> FloatArray:
    """Band-effective blackbody radiance ``L = K1 / (exp(K2 / T) - 1)``."""
    t = np.asarray(temperature_k, dtype=np.float64)
    return (constants.k1 / np.expm1(constants.k2 / t)).astype(np.float32)


def emissivity_ndvi_threshold(
    ndvi: FloatArray,
    ndvi_soil: float = 0.2,
    ndvi_vegetation: float = 0.5,
    water_emissivity: float = 0.991,
) -> FloatArray:
    """Surface emissivity from NDVI thresholds.

    The proportion of vegetation is ``Pv = ((NDVI - NDVI_s) / (NDVI_v - NDVI_s))^2``
    clipped to [0, 1], and emissivity is ``0.004 * Pv + 0.986``. Pixels with negative
    NDVI are treated as water. Fixed thresholds replace the scene minimum and
    maximum of the course version, which depended on sea and cloud pixels.
    """
    v = np.asarray(ndvi, dtype=np.float64)
    pv = np.clip((v - ndvi_soil) / (ndvi_vegetation - ndvi_soil), 0.0, 1.0) ** 2
    eps = 0.004 * pv + 0.986
    eps = np.where(v < 0, water_emissivity, eps)
    eps = np.where(np.isfinite(v), eps, np.nan)
    return eps.astype(np.float32)


def single_channel_lst(
    brightness_k: FloatArray,
    emissivity: FloatArray,
    wavelength_m: float = TIRS_B10_WAVELENGTH_M,
) -> FloatArray:
    """Emissivity-corrected temperature ``T / (1 + (lambda T / rho) ln eps)`` in kelvin."""
    t = np.asarray(brightness_k, dtype=np.float64)
    eps = np.asarray(emissivity, dtype=np.float64)
    return (t / (1.0 + (wavelength_m * t / RHO_MK) * np.log(eps))).astype(np.float32)


def radiative_transfer_lst(
    toa_radiance: FloatArray,
    upwelled: FloatArray,
    downwelled: FloatArray,
    transmission: FloatArray,
    emissivity: FloatArray,
    constants: ThermalConstants,
) -> FloatArray:
    """Invert ``L_toa = tau (eps L_s + (1 - eps) L_down) + L_up`` for the surface temperature."""
    l_toa = np.asarray(toa_radiance, dtype=np.float64)
    l_up = np.asarray(upwelled, dtype=np.float64)
    l_down = np.asarray(downwelled, dtype=np.float64)
    tau = np.asarray(transmission, dtype=np.float64)
    eps = np.asarray(emissivity, dtype=np.float64)
    surface = (l_toa - l_up - tau * (1.0 - eps) * l_down) / (tau * eps)
    return brightness_temperature(surface.astype(np.float32), constants)
