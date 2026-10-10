from datetime import UTC, date, datetime

import numpy as np
import pytest

from sgheat.temporal import anomaly, seasons, trends


class TestMedianPolish:
    def test_recovers_planted_effects_with_missing_values(self):
        rng = np.random.default_rng(42)
        n_z, n_s = 300, 60
        alpha = rng.normal(0, 2.0, n_z)
        tau = rng.normal(0, 3.0, n_s)
        mu = 301.5
        noise = rng.normal(0, 0.1, (n_z, n_s))
        matrix = mu + alpha[:, None] + tau[None, :] + noise
        matrix[rng.random((n_z, n_s)) < 0.3] = np.nan
        fit = anomaly.median_polish(matrix)
        assert fit.converged
        # Effects are identified up to a constant; compare centred versions.
        np.testing.assert_allclose(
            fit.zone_effect - np.median(fit.zone_effect), alpha - np.median(alpha), atol=0.08
        )
        np.testing.assert_allclose(
            fit.scene_effect - np.median(fit.scene_effect), tau - np.median(tau), atol=0.08
        )
        recon = fit.overall + fit.zone_effect[:, None] + fit.scene_effect[None, :] + fit.residual
        np.testing.assert_allclose(
            recon[np.isfinite(matrix)], matrix[np.isfinite(matrix)], atol=1e-9
        )

    def test_robust_to_outlier_scene(self):
        rng = np.random.default_rng(0)
        alpha = rng.normal(0, 1, 50)
        matrix = 300 + alpha[:, None] + np.zeros((50, 20))
        matrix[:10, 3] -= 15.0  # cloud edge in one scene hits ten zones
        fit = anomaly.median_polish(matrix)
        np.testing.assert_allclose(
            fit.zone_effect - np.median(fit.zone_effect), alpha - np.median(alpha), atol=1e-6
        )

    def test_anomaly_shape_and_nan(self):
        m = np.array([[1.0, np.nan], [2.0, 3.0]])
        fit = anomaly.median_polish(m)
        a = fit.anomaly()
        assert a.shape == m.shape
        assert np.isnan(a[0, 1])


class TestSeasons:
    @pytest.mark.parametrize(
        ("day", "season"),
        [
            (date(2018, 1, 10), seasons.Season.NE_MONSOON),
            (date(2018, 3, 15), seasons.Season.NE_MONSOON),
            (date(2018, 3, 16), seasons.Season.INTER_MONSOON_1),
            (date(2018, 5, 24), seasons.Season.INTER_MONSOON_1),
            (date(2018, 7, 1), seasons.Season.SW_MONSOON),
            (date(2018, 10, 31), seasons.Season.INTER_MONSOON_2),
            (date(2018, 12, 1), seasons.Season.NE_MONSOON),
        ],
    )
    def test_season_of(self, day, season):
        assert seasons.season_of(day) == season

    def test_decimal_year(self):
        assert seasons.decimal_year(datetime(2020, 1, 1, tzinfo=UTC)) == 2020.0
        assert seasons.decimal_year(datetime(2020, 7, 2, tzinfo=UTC)) == pytest.approx(
            2020.5, abs=0.003
        )


class TestTrends:
    def test_recovers_slope_and_flags_significance(self):
        rng = np.random.default_rng(3)
        t = np.sort(rng.uniform(2013, 2026, 120))
        values = np.vstack(
            [
                0.05 * (t - 2013) + rng.normal(0, 0.3, t.size),  # +0.5 K per decade
                rng.normal(0, 0.3, t.size),  # no trend
                np.full(t.size, np.nan),  # never observed
            ]
        )
        res = trends.theil_sen_mann_kendall(t, values, min_obs=20, min_span_years=8)
        assert res.slope_per_decade[0] == pytest.approx(0.5, abs=0.15)
        assert res.slope_low[0] < res.slope_per_decade[0] < res.slope_high[0]
        assert res.q_value[0] < 0.01
        assert res.q_value[1] > 0.05
        assert np.isnan(res.slope_per_decade[2])
        assert res.n_obs[2] == 0

    def test_short_span_is_not_estimated(self):
        t = np.linspace(2020, 2023, 50)
        res = trends.theil_sen_mann_kendall(t, t[None, :] * 0.1, min_obs=20, min_span_years=8)
        assert np.isnan(res.slope_per_decade[0])
        assert res.span_years[0] == pytest.approx(3.0)
