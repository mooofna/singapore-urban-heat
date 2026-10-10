"""Cross-sectional spatial regression of relative surface heat on urban form.

The specification search follows Anselin's classic rule: start from OLS, read the
Lagrange multiplier tests for an omitted spatial lag and for spatially
correlated errors, and fit the spatial lag (SAR), spatial error (SEM) and spatial
Durbin (SDM) models by maximum likelihood. Reporting rules that the course
version got wrong are enforced here:

* SAR fit is reported as ``pr2_e`` (squared correlation of y with the reduced-form
  prediction); the ``pr2`` that includes ``rho W y`` uses the observed outcome of
  the neighbours and is not comparable with OLS.
* SEM fit is the squared correlation of y with ``X beta``.
* Residual Moran's I uses ``u`` for OLS and SAR and ``e_filtered`` for SEM.
* SAR and SDM coefficients are not marginal effects; impacts are computed.
* Information criteria are only compared between models fitted to the same data.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import esda
import numpy as np
import spreg
from libpysal.weights import W
from numpy.typing import NDArray

from sgheat.stats.impacts import Impact, lag_impacts, trace_powers

FloatArray = NDArray[np.float64]
ModelKind = Literal["OLS", "SAR", "SEM", "SDM"]


def significance_stars(p: float) -> str:
    """Conventional stars: three below 0.001, two below 0.01, one below 0.05."""
    if not np.isfinite(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def variance_inflation(x: FloatArray) -> FloatArray:
    """Variance inflation factor of each column of ``x`` (no intercept column)."""
    corr = np.corrcoef(x, rowvar=False)
    return np.asarray(np.diag(np.linalg.inv(np.atleast_2d(corr))), dtype=np.float64)


@dataclass(frozen=True)
class Coefficient:
    """One estimated parameter."""

    name: str
    estimate: float
    std_error: float
    statistic: float
    p_value: float

    @property
    def stars(self) -> str:
        return significance_stars(self.p_value)


@dataclass(frozen=True)
class MoranResult:
    """Global Moran's I of a residual vector (analytic test under randomisation)."""

    i: float
    expected: float
    z: float
    p_value: float


@dataclass(frozen=True)
class LMTest:
    """A Lagrange multiplier test statistic."""

    name: str
    statistic: float
    p_value: float


@dataclass
class ModelResult:
    """Everything reported about one fitted model."""

    kind: ModelKind
    n: int
    k: int
    y_digest: str
    coefficients: list[Coefficient]
    log_likelihood: float
    aic: float
    schwarz: float
    fit_measure: float
    fit_label: str
    residual_moran: MoranResult
    residuals: FloatArray = field(repr=False)
    fitted: FloatArray = field(repr=False)
    spatial_parameter: Coefficient | None = None
    impacts: list[Impact] = field(default_factory=list)
    lm_tests: list[LMTest] = field(default_factory=list)
    extra: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready summary (residual vectors excluded)."""
        out = asdict(self)
        out.pop("residuals")
        out.pop("fitted")
        for c in out["coefficients"]:
            c["stars"] = significance_stars(c["p_value"])
        if out["spatial_parameter"] is not None:
            out["spatial_parameter"]["stars"] = significance_stars(
                out["spatial_parameter"]["p_value"]
            )
        return out


def _digest(y: FloatArray) -> str:
    return hashlib.sha256(np.ascontiguousarray(y, dtype=np.float64).tobytes()).hexdigest()[:16]


def _moran(resid: FloatArray, w: W) -> MoranResult:
    m = esda.Moran(np.asarray(resid, dtype=np.float64).reshape(-1), w, permutations=0)
    return MoranResult(
        i=float(m.I), expected=float(m.EI), z=float(m.z_rand), p_value=float(m.p_rand)
    )


def _coefficients(
    names: list[str], betas: FloatArray, se: FloatArray, stats: list[Any]
) -> list[Coefficient]:
    return [
        Coefficient(
            name=n,
            estimate=float(b),
            std_error=float(s),
            statistic=float(t[0]),
            p_value=float(t[1]),
        )
        for n, b, s, t in zip(names, betas.reshape(-1), se.reshape(-1), stats, strict=True)
    ]


def _check_design(x: FloatArray) -> None:
    if np.any(np.all(x == x[:1, :], axis=0)):
        msg = "design matrix contains a constant column; spreg adds the intercept itself"
        raise ValueError(msg)


def fit_ols(y: FloatArray, x: FloatArray, names: list[str], w: W) -> ModelResult:
    """OLS with spatial diagnostics (LM tests, Moran's I of residuals)."""
    _check_design(x)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = spreg.OLS(y.reshape(-1, 1), x, w=w, spat_diag=True, moran=True, name_x=names)
    lm = [
        LMTest(name, float(getattr(m, attr)[0]), float(getattr(m, attr)[1]))
        for name, attr in [
            ("LM error", "lm_error"),
            ("LM lag", "lm_lag"),
            ("Robust LM error", "rlm_error"),
            ("Robust LM lag", "rlm_lag"),
            ("LM SARMA", "lm_sarma"),
        ]
    ]
    return ModelResult(
        kind="OLS",
        n=int(m.n),
        k=int(m.k),
        y_digest=_digest(y),
        coefficients=_coefficients(["constant", *names], m.betas, m.std_err, m.t_stat),
        log_likelihood=float(m.logll),
        aic=float(m.aic),
        schwarz=float(m.schwarz),
        fit_measure=float(m.ar2),
        fit_label="adjusted R²",
        residual_moran=_moran(m.u, w),
        residuals=np.asarray(m.u, dtype=np.float64).reshape(-1),
        fitted=np.asarray(m.predy, dtype=np.float64).reshape(-1),
        lm_tests=lm,
        extra={
            "r2": float(m.r2),
            "condition_number": float(m.mulColli),
            "jarque_bera_p": float(m.jarque_bera["pvalue"]),
            "koenker_bassett_p": float(m.koenker_bassett["pvalue"]),
        },
    )


def fit_lag(
    y: FloatArray,
    x: FloatArray,
    names: list[str],
    w: W,
    *,
    durbin: bool = False,
    durbin_exclude: tuple[str, ...] = (),
    traces: FloatArray | None = None,
    impact_draws: int = 2000,
    seed: int = 0,
) -> ModelResult:
    """Spatial lag model (SAR) or, with ``durbin=True``, the spatial Durbin model (SDM).

    ``durbin_exclude`` names covariates that get no spatial lag in the SDM.
    """
    _check_design(x)
    k = len(names)
    lagged = [n not in durbin_exclude for n in names] if durbin else [False] * k
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        m = spreg.ML_Lag(
            y.reshape(-1, 1),
            x,
            w=w,
            method="LU",
            slx_lags=1 if durbin else 0,
            slx_vars=lagged if durbin else "All",
            spat_impacts=None,
            spat_diag=False,
            name_x=names,
        )
    betas = np.asarray(m.betas, dtype=np.float64).reshape(-1)
    se = np.asarray(m.std_err, dtype=np.float64).reshape(-1)
    lagged_names = [n for n, flag in zip(names, lagged, strict=True) if flag]
    coef_names = ["constant", *names] + [f"W {n}" for n in lagged_names]
    coefs = _coefficients(coef_names, betas[:-1], se[:-1], m.z_stat[:-1])
    rho = Coefficient(
        "rho", float(betas[-1]), float(se[-1]), float(m.z_stat[-1][0]), float(m.z_stat[-1][1])
    )
    if traces is None:
        traces = trace_powers(w.sparse, seed=seed)
    vm = np.asarray(m.vm, dtype=np.float64)
    theta = None
    # Covariance of [beta, theta (zeros for unlagged covariates), rho] without the intercept.
    beta_idx = list(range(1, 1 + k))
    theta_pos = {n: 1 + k + j for j, n in enumerate(lagged_names)}
    if durbin:
        theta = np.array([betas[theta_pos[n]] if n in theta_pos else 0.0 for n in names])
    order = beta_idx + ([theta_pos.get(n, -1) for n in names] if durbin else []) + [len(betas) - 1]
    dim = len(order)
    vcov = np.zeros((dim, dim))
    for a, ia in enumerate(order):
        for b, ib in enumerate(order):
            if ia >= 0 and ib >= 0:
                vcov[a, b] = vm[ia, ib]
    impacts = lag_impacts(
        names,
        beta=betas[1 : 1 + k],
        theta=theta,
        rho=float(betas[-1]),
        traces=traces,
        vcov=vcov,
        draws=impact_draws,
        seed=seed,
    )
    return ModelResult(
        kind="SDM" if durbin else "SAR",
        n=int(m.n),
        k=len(betas),
        y_digest=_digest(y),
        coefficients=coefs,
        log_likelihood=float(m.logll),
        aic=float(m.aic),
        schwarz=float(m.schwarz),
        fit_measure=float(m.pr2_e),
        fit_label="pseudo R² (reduced form)",
        residual_moran=_moran(m.u, w),
        residuals=np.asarray(m.u, dtype=np.float64).reshape(-1),
        fitted=np.asarray(m.predy_e, dtype=np.float64).reshape(-1),
        spatial_parameter=rho,
        impacts=impacts,
        extra={"pr2_with_lag": float(m.pr2)},
    )


def fit_error(y: FloatArray, x: FloatArray, names: list[str], w: W) -> ModelResult:
    """Spatial error model (SEM) by maximum likelihood."""
    _check_design(x)
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        m = spreg.ML_Error(y.reshape(-1, 1), x, w=w, method="LU", name_x=names)
    betas = np.asarray(m.betas, dtype=np.float64).reshape(-1)
    se = np.asarray(m.std_err, dtype=np.float64).reshape(-1)
    lam = Coefficient(
        "lambda", float(betas[-1]), float(se[-1]), float(m.z_stat[-1][0]), float(m.z_stat[-1][1])
    )
    return ModelResult(
        kind="SEM",
        n=int(m.n),
        k=len(betas),
        y_digest=_digest(y),
        coefficients=_coefficients(["constant", *names], betas[:-1], se[:-1], m.z_stat[:-1]),
        log_likelihood=float(m.logll),
        aic=float(m.aic),
        schwarz=float(m.schwarz),
        fit_measure=float(m.pr2),
        fit_label="pseudo R² (X beta)",
        residual_moran=_moran(m.e_filtered, w),
        residuals=np.asarray(m.e_filtered, dtype=np.float64).reshape(-1),
        fitted=np.asarray(m.predy, dtype=np.float64).reshape(-1),
        spatial_parameter=lam,
    )


@dataclass(frozen=True)
class LikelihoodRatio:
    """Likelihood ratio test of a restricted against a more general model."""

    restricted: ModelKind
    general: ModelKind
    statistic: float
    df: int
    p_value: float


def likelihood_ratio(restricted: ModelResult, general: ModelResult) -> LikelihoodRatio:
    """LR test; both models must be fitted to the same outcome vector."""
    from scipy import stats  # noqa: PLC0415

    ensure_comparable([restricted, general])
    df = general.k - restricted.k
    stat = 2.0 * (general.log_likelihood - restricted.log_likelihood)
    return LikelihoodRatio(
        restricted=restricted.kind,
        general=general.kind,
        statistic=float(stat),
        df=int(df),
        p_value=float(stats.chi2.sf(stat, df)),
    )


def ensure_comparable(models: list[ModelResult]) -> None:
    """Raise unless all models share the same observations and outcome."""
    keys = {(m.n, m.y_digest) for m in models}
    if len(keys) != 1:
        msg = "models were fitted to different data; information criteria are not comparable"
        raise ValueError(msg)


def lm_decision(ols: ModelResult, alpha: float = 0.05) -> str:
    """Anselin's rule on the (robust) LM tests: ``lag``, ``error``, ``both`` or ``none``."""
    tests = {t.name: t.p_value for t in ols.lm_tests}
    lag, err = tests["LM lag"] < alpha, tests["LM error"] < alpha
    if not lag and not err:
        return "none"
    if lag and not err:
        return "lag"
    if err and not lag:
        return "error"
    rlag, rerr = tests["Robust LM lag"] < alpha, tests["Robust LM error"] < alpha
    if rlag and not rerr:
        return "lag"
    if rerr and not rlag:
        return "error"
    return "both"
