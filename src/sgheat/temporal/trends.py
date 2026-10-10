"""Per-zone trends of relative surface heat.

The slope is the Theil-Sen estimator (median of pairwise slopes), robust to the
irregular, cloud-dependent sampling of Landsat. Significance comes from the
Mann-Kendall test (Kendall's tau between time and value), and p-values are
corrected across zones with the Benjamini-Hochberg false discovery rate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import stats

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class TrendResult:
    """Per-zone trend estimates; NaN where the series is too short."""

    slope_per_decade: FloatArray
    slope_low: FloatArray
    slope_high: FloatArray
    p_value: FloatArray
    q_value: FloatArray
    n_obs: NDArray[np.int64]
    span_years: FloatArray


def theil_sen_mann_kendall(
    t: FloatArray,
    values: FloatArray,
    min_obs: int,
    min_span_years: float,
    alpha: float = 0.05,
) -> TrendResult:
    """Trend of each row of ``values`` (zones x scenes) against decimal years ``t``.

    Rows with fewer than ``min_obs`` finite values or spanning less than
    ``min_span_years`` get NaN. ``slope_low``/``slope_high`` are the confidence
    bounds at level ``1 - alpha`` returned by :func:`scipy.stats.theilslopes`.
    """
    n_zones = values.shape[0]
    slope = np.full(n_zones, np.nan)
    low = np.full(n_zones, np.nan)
    high = np.full(n_zones, np.nan)
    pval = np.full(n_zones, np.nan)
    n_obs = np.zeros(n_zones, dtype=np.int64)
    span = np.zeros(n_zones)
    for i in range(n_zones):
        ok = np.isfinite(values[i])
        n_obs[i] = int(ok.sum())
        if n_obs[i] < 2:
            continue
        ti, yi = t[ok], values[i, ok]
        span[i] = float(ti.max() - ti.min())
        if n_obs[i] < min_obs or span[i] < min_span_years:
            continue
        res = stats.theilslopes(yi, ti, alpha=1 - alpha)
        slope[i], low[i], high[i] = res.slope * 10, res.low_slope * 10, res.high_slope * 10
        pval[i] = stats.kendalltau(ti, yi).pvalue
    qval = np.full(n_zones, np.nan)
    tested = np.isfinite(pval)
    if tested.any():
        qval[tested] = stats.false_discovery_control(pval[tested], method="bh")
    return TrendResult(
        slope_per_decade=slope,
        slope_low=low,
        slope_high=high,
        p_value=pval,
        q_value=qval,
        n_obs=n_obs,
        span_years=span,
    )
