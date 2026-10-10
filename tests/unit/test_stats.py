import numpy as np
import pytest

from sgheat.stats import impacts, lisa, models, weights


def hex_patch(n: int = 30):
    q, r = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    return q.ravel().astype(np.int64), r.ravel().astype(np.int64)


@pytest.fixture(scope="module")
def lattice():
    q, r = hex_patch()
    graph = weights.hex_graph(q, r)
    return q, r, graph, weights.to_w(graph)


def simulate(w, rng, rho=0.0, lam=0.0, beta=(1.0, 2.0, -1.0)):
    n = w.n
    dense = w.sparse.toarray()
    x = rng.normal(size=(n, 2))
    eps = rng.normal(size=n)
    if lam:
        eps = np.linalg.solve(np.eye(n) - lam * dense, eps)
    xb = beta[0] + x @ np.asarray(beta[1:])
    y = np.linalg.solve(np.eye(n) - rho * dense, xb + eps)
    return y, x, dense


class TestWeights:
    def test_row_standardised_and_symmetric_structure(self, lattice):
        _, _, _, w = lattice
        s = w.sparse
        np.testing.assert_allclose(np.asarray(s.sum(axis=1)).ravel(), 1.0)
        assert ((s > 0) != (s.T > 0)).nnz == 0
        assert max(w.cardinalities.values()) == 6

    def test_isolates_and_components(self):
        q = np.array([0, 1, 10, 20, 21], dtype=np.int64)
        r = np.array([0, 0, 10, 0, 0], dtype=np.int64)
        graph = weights.hex_graph(q, r)
        assert set(graph.isolates) == {2}
        labels = weights.component_labels(q, r)
        assert len(set(labels.tolist())) == 3
        mask = weights.largest_component(q, r)
        assert mask.sum() == 2


class TestImpacts:
    def test_trace_estimates(self, lattice):
        _, _, _, w = lattice
        dense = w.sparse.toarray()
        tr = impacts.trace_powers(w.sparse, max_power=6, n_vectors=400)
        for j in range(7):
            exact = np.trace(np.linalg.matrix_power(dense, j)) / w.n
            assert tr[j] == pytest.approx(exact, abs=0.01)

    def test_point_impacts_match_dense_inverse(self, lattice):
        _, _, _, w = lattice
        dense = w.sparse.toarray()
        rho, beta = 0.6, np.array([2.0, -1.0])
        s = np.linalg.inv(np.eye(w.n) - rho * dense)
        tr = impacts.trace_powers(w.sparse, max_power=80, n_vectors=200)
        res = impacts.lag_impacts(["a", "b"], beta, rho, tr, vcov=np.eye(3) * 1e-8, draws=200)
        for imp, b in zip(res, beta, strict=True):
            assert imp.direct == pytest.approx(b * np.trace(s) / w.n, rel=0.01)
            assert imp.total == pytest.approx(b / (1 - rho), rel=1e-9)
            assert imp.indirect == pytest.approx(imp.total - imp.direct)


class TestModels:
    def test_stars(self):
        assert models.significance_stars(0.0005) == "***"
        assert models.significance_stars(0.005) == "**"
        assert models.significance_stars(0.05) == ""
        assert models.significance_stars(0.0499) == "*"
        assert models.significance_stars(float("nan")) == ""

    def test_vif(self):
        rng = np.random.default_rng(0)
        a = rng.normal(size=500)
        x = np.column_stack([a, a + rng.normal(scale=0.1, size=500), rng.normal(size=500)])
        vif = models.variance_inflation(x)
        assert vif[0] > 50
        assert vif[2] < 1.1

    def test_constant_column_rejected(self, lattice):
        _, _, _, w = lattice
        x = np.column_stack([np.ones(w.n), np.arange(w.n)])
        with pytest.raises(ValueError, match="constant column"):
            models.fit_ols(np.arange(w.n, dtype=float), x, ["c", "x"], w)

    def test_sar_process(self, lattice):
        _, _, _, w = lattice
        y, x, _ = simulate(w, np.random.default_rng(1), rho=0.6)
        ols = models.fit_ols(y, x, ["a", "b"], w)
        assert models.lm_decision(ols) in ("lag", "both")
        sar = models.fit_lag(y, x, ["a", "b"], w, impact_draws=300)
        assert sar.spatial_parameter.estimate == pytest.approx(0.6, abs=0.08)
        assert sar.coefficients[1].estimate == pytest.approx(2.0, abs=0.15)
        total = sar.impacts[0].total
        assert total == pytest.approx(
            sar.coefficients[1].estimate / (1 - sar.spatial_parameter.estimate), rel=1e-6
        )
        assert sar.impacts[0].direct > sar.coefficients[1].estimate  # feedback makes direct > beta
        assert abs(sar.residual_moran.i) < 0.05
        lr = models.likelihood_ratio(ols, sar)
        assert lr.df == 1
        assert lr.p_value < 1e-6

    def test_sem_filtered_residuals(self, lattice):
        _, _, _, w = lattice
        y, x, _ = simulate(w, np.random.default_rng(2), lam=0.7)
        ols = models.fit_ols(y, x, ["a", "b"], w)
        sem = models.fit_error(y, x, ["a", "b"], w)
        assert ols.residual_moran.i > 0.2
        assert abs(sem.residual_moran.i) < 0.05
        assert sem.spatial_parameter.estimate == pytest.approx(0.7, abs=0.1)

    def test_sdm_runs(self, lattice):
        _, _, _, w = lattice
        y, x, _ = simulate(w, np.random.default_rng(3), rho=0.4)
        sdm = models.fit_lag(y, x, ["a", "b"], w, durbin=True, impact_draws=200)
        assert sdm.kind == "SDM"
        assert len(sdm.coefficients) == 5
        assert len(sdm.impacts) == 2
        d = sdm.to_dict()
        assert "residuals" not in d
        assert d["coefficients"][0]["name"] == "constant"

    def test_comparability_guard(self, lattice):
        _, _, _, w = lattice
        rng = np.random.default_rng(4)
        y, x, _ = simulate(w, rng)
        a = models.fit_ols(y, x, ["a", "b"], w)
        b = models.fit_ols(y + 1, x, ["a", "b"], w)
        with pytest.raises(ValueError, match="different data"):
            models.ensure_comparable([a, b])


class TestLisa:
    def test_planted_hot_spot(self, lattice):
        q, r, _, w = lattice
        rng = np.random.default_rng(5)
        values = rng.normal(size=w.n)
        hot = (q < 8) & (r < 8)
        values[hot] += 4.0
        res = lisa.local_moran(values, w, permutations=9999, seed=1)
        assert (res.cluster[hot] == 1).mean() > 0.7
        assert (res.cluster[~hot] == 1).mean() < 0.05
