"""Direct, indirect and total effects of spatial lag models (LeSage and Pace 2009).

In a spatial lag model ``y = rho W y + X beta + W X theta + e`` a change in a
covariate at one zone moves the outcome there (direct effect) and, through the
spatial multiplier ``S = (I - rho W)^-1``, at every other zone (indirect effect).
With traces ``t_j = tr(W^j) / n``:

* average direct effect ``beta * sum_j rho^j t_j + theta * sum_j rho^j t_{j+1}``,
* average total effect ``(beta + theta) / (1 - rho)`` for row-standardised ``W``,
* indirect effect = total minus direct.

Traces of higher powers are estimated with Hutchinson's stochastic estimator;
standard errors come from Monte Carlo draws of the parameters from their
estimated sampling distribution.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def trace_powers(
    w: sp.sparray | sp.spmatrix,
    max_power: int = 100,
    n_vectors: int = 100,
    seed: int = 0,
) -> FloatArray:
    """``tr(W^j) / n`` for ``j = 0 .. max_power``.

    Powers 0 to 2 are exact; higher powers use Rademacher probe vectors.
    """
    wc = sp.csr_array(w)
    n = wc.shape[0]
    traces = np.zeros(max_power + 1)
    traces[0] = 1.0
    if max_power >= 1:
        traces[1] = float(wc.diagonal().sum()) / n
    if max_power >= 2:
        traces[2] = float(wc.multiply(wc.T).sum()) / n
    if max_power >= 3:
        rng = np.random.default_rng(seed)
        probes = rng.choice([-1.0, 1.0], size=(n, n_vectors))
        current = probes.copy()
        for _ in range(2):
            current = wc @ current
        for j in range(3, max_power + 1):
            current = wc @ current
            traces[j] = float(np.mean(np.sum(probes * current, axis=0))) / n
    return traces


@dataclass(frozen=True)
class Impact:
    """Average effects of one covariate with Monte Carlo standard errors."""

    name: str
    direct: float
    indirect: float
    total: float
    direct_se: float
    indirect_se: float
    total_se: float


def _point_impacts(
    beta: FloatArray, theta: FloatArray | None, rho: float, traces: FloatArray
) -> tuple[FloatArray, FloatArray]:
    powers = rho ** np.arange(len(traces))
    m0 = float(np.sum(powers * traces))
    if theta is None:
        direct = beta * m0
        total = beta / (1.0 - rho)
    else:
        m1 = float(np.sum(powers[:-1] * traces[1:]))
        direct = beta * m0 + theta * m1
        total = (beta + theta) / (1.0 - rho)
    return direct, total


def lag_impacts(
    names: list[str],
    beta: FloatArray,
    rho: float,
    traces: FloatArray,
    vcov: FloatArray,
    theta: FloatArray | None = None,
    draws: int = 2000,
    seed: int = 0,
) -> list[Impact]:
    """Impacts for each covariate of a spatial lag (or spatial Durbin) model.

    ``vcov`` is the covariance of the stacked parameter vector ``[beta, theta, rho]``
    (``theta`` omitted for the plain lag model), without the intercept.
    """
    k = len(beta)
    direct, total = _point_impacts(beta, theta, rho, traces)
    mean = np.concatenate([beta, theta if theta is not None else np.empty(0), [rho]])
    rng = np.random.default_rng(seed)
    sample = rng.multivariate_normal(mean, vcov, size=draws, method="eigh")
    sample = sample[np.abs(sample[:, -1]) < 1.0]
    d_draws = np.empty((len(sample), k))
    t_draws = np.empty((len(sample), k))
    for i, row in enumerate(sample):
        b = row[:k]
        th = row[k : 2 * k] if theta is not None else None
        d_draws[i], t_draws[i] = _point_impacts(b, th, float(row[-1]), traces)
    i_draws = t_draws - d_draws
    return [
        Impact(
            name=names[j],
            direct=float(direct[j]),
            indirect=float(total[j] - direct[j]),
            total=float(total[j]),
            direct_se=float(np.std(d_draws[:, j], ddof=1)),
            indirect_se=float(np.std(i_draws[:, j], ddof=1)),
            total_se=float(np.std(t_draws[:, j], ddof=1)),
        )
        for j in range(k)
    ]
