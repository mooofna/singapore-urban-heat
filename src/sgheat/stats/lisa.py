"""Local indicators of spatial association (hot and cold spots)."""

from __future__ import annotations

from dataclasses import dataclass

import esda
import numpy as np
from libpysal.weights import W
from numpy.typing import NDArray
from scipy import stats

# Quadrant codes of esda: 1 high-high, 2 low-high, 3 low-low, 4 high-low.
CLUSTER_LABELS = {
    0: "not significant",
    1: "hot spot",
    2: "cold outlier",
    3: "cold spot",
    4: "hot outlier",
}


@dataclass(frozen=True)
class LisaResult:
    """Local Moran's I with permutation p-values and FDR-controlled cluster codes."""

    local_i: NDArray[np.float64]
    p_value: NDArray[np.float64]
    q_value: NDArray[np.float64]
    cluster: NDArray[np.int64]


def local_moran(
    values: NDArray[np.float64], w: W, permutations: int, seed: int, alpha: float = 0.05
) -> LisaResult:
    """Local Moran's I; a zone gets a cluster code when its FDR q-value is below ``alpha``."""
    lm = esda.Moran_Local(
        np.asarray(values, dtype=np.float64),
        w,
        permutations=permutations,
        seed=seed,
        alternative="two-sided",
        keep_simulations=False,
    )
    p = np.asarray(lm.p_sim, dtype=np.float64)
    q = stats.false_discovery_control(p, method="bh")
    cluster = np.where(q < alpha, np.asarray(lm.q, dtype=np.int64), 0)
    return LisaResult(
        local_i=np.asarray(lm.Is, dtype=np.float64), p_value=p, q_value=q, cluster=cluster
    )
