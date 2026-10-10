"""Decoding of the Landsat 8/9 Collection 2 ``QA_PIXEL`` band.

Bit layout (USGS Landsat 8-9 OLI/TIRS Collection 2 Level 2 Science Product Guide):

====  ==========================
bit   meaning
====  ==========================
0     fill
1     dilated cloud
2     cirrus
3     cloud
4     cloud shadow
5     snow
6     clear (no cloud, no dilated cloud)
7     water
8-9   cloud confidence
10-11 cloud shadow confidence
12-13 snow/ice confidence
14-15 cirrus confidence
====  ==========================
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from numpy.typing import NDArray

BoolArray = NDArray[np.bool_]


class QABit(IntEnum):
    """Single-bit flags of ``QA_PIXEL``."""

    FILL = 0
    DILATED_CLOUD = 1
    CIRRUS = 2
    CLOUD = 3
    CLOUD_SHADOW = 4
    SNOW = 5
    CLEAR = 6
    WATER = 7


def bit_set(qa: NDArray[np.integer], bit: int) -> BoolArray:
    """Boolean array that is true where ``bit`` is set in ``qa``."""
    bits = (np.asarray(qa).astype(np.uint16) >> np.uint16(bit)) & np.uint16(1)
    return np.asarray(bits == 1, dtype=np.bool_)


def confidence(qa: NDArray[np.integer], low_bit: int) -> NDArray[np.uint8]:
    """Two-bit confidence field starting at ``low_bit`` (0 none, 1 low, 2 medium, 3 high)."""
    return ((np.asarray(qa).astype(np.uint16) >> np.uint16(low_bit)) & np.uint16(0b11)).astype(
        np.uint8
    )


@dataclass(frozen=True)
class QAMasks:
    """Masks derived from ``QA_PIXEL``.

    Attributes:
        fill: no data.
        obscured: cloud, dilated cloud, cirrus, cloud shadow or snow.
        observed: not fill and not obscured, so the surface is visible.
        water: observed and flagged as water.
        land: observed and not water; surface temperature is averaged over these pixels.
    """

    fill: BoolArray
    obscured: BoolArray
    observed: BoolArray
    water: BoolArray
    land: BoolArray


def decode_qa_pixel(qa: NDArray[np.integer]) -> QAMasks:
    """Split a ``QA_PIXEL`` array into the masks the pipeline uses."""
    fill = bit_set(qa, QABit.FILL)
    obscured = (
        bit_set(qa, QABit.DILATED_CLOUD)
        | bit_set(qa, QABit.CIRRUS)
        | bit_set(qa, QABit.CLOUD)
        | bit_set(qa, QABit.CLOUD_SHADOW)
        | bit_set(qa, QABit.SNOW)
    ) & ~fill
    observed = ~fill & ~obscured
    water = observed & bit_set(qa, QABit.WATER)
    land = observed & ~water
    return QAMasks(fill=fill, obscured=obscured, observed=observed, water=water, land=land)
