import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from sgheat.physics import indices, lst_educational, qa, scaling


class TestQA:
    @pytest.mark.parametrize(
        ("code", "fill", "obscured", "water", "land"),
        [
            (1, True, False, False, False),  # fill
            (21824, False, False, False, True),  # clear land, low confidences
            (21952, False, False, True, False),  # clear water
            (22280, False, True, False, False),  # high-confidence cloud
            (23888, False, True, False, False),  # cloud shadow (bit 4) with low confidences
        ],
    )
    def test_canonical_codes(self, code, fill, obscured, water, land):
        m = qa.decode_qa_pixel(np.array([code], dtype=np.uint16))
        assert m.fill[0] == fill
        assert m.obscured[0] == obscured
        assert m.water[0] == water
        assert m.land[0] == land

    @given(st.integers(min_value=0, max_value=65535))
    def test_masks_partition_pixels(self, code):
        m = qa.decode_qa_pixel(np.array([code], dtype=np.uint16))
        # Every pixel is exactly one of fill, obscured, water, land.
        total = int(m.fill[0]) + int(m.obscured[0]) + int(m.water[0]) + int(m.land[0])
        assert total == 1
        assert m.observed[0] == (m.water[0] or m.land[0])

    @given(st.integers(min_value=0, max_value=65535), st.integers(min_value=0, max_value=15))
    def test_bit_set_matches_python(self, code, bit):
        assert qa.bit_set(np.array([code], dtype=np.uint16), bit)[0] == bool((code >> bit) & 1)

    def test_confidence(self):
        assert qa.confidence(np.array([22280], dtype=np.uint16), 8)[0] == 3


class TestScaling:
    def test_surface_temperature_known_value(self):
        k = scaling.surface_temperature_kelvin(np.array([44000, 0], dtype=np.uint16))
        assert k[0] == pytest.approx(44000 * 0.00341802 + 149.0, abs=1e-3)
        assert k[0] == pytest.approx(299.39288, abs=1e-3)
        assert np.isnan(k[1])

    def test_reflectance_range(self):
        r = scaling.surface_reflectance(np.array([7273, 43636, 7272, 43637, 0], dtype=np.uint16))
        assert r[0] == pytest.approx(0.0, abs=1e-4)
        assert r[1] == pytest.approx(1.0, abs=1e-4)
        assert np.isnan(r[2:]).all()

    def test_from_raster_bands(self):
        s = scaling.BandScaling.from_raster_bands(
            [{"scale": 0.00341802, "offset": 149, "nodata": 0, "unit": "kelvin"}]
        )
        assert s == scaling.SURFACE_TEMPERATURE

    def test_celsius(self):
        assert scaling.kelvin_to_celsius(np.array([273.15], dtype=np.float32))[0] == pytest.approx(
            0
        )


class TestIndices:
    def test_ndvi_values(self):
        red = np.array([0.1, 0.2, 0.0, np.nan], dtype=np.float32)
        nir = np.array([0.5, 0.2, 0.0, 0.3], dtype=np.float32)
        out = indices.ndvi(red, nir)
        assert out[0] == pytest.approx(0.4 / 0.6)
        assert out[1] == pytest.approx(0.0)
        assert np.isnan(out[2])  # zero denominator
        assert np.isnan(out[3])

    def test_dn_vs_reflectance_bias(self):
        # The course version computed NDVI on raw DN; the scaling offset biases that index.
        red_dn, nir_dn = np.array([8000.0]), np.array([20000.0])
        dn_ndvi = (nir_dn - red_dn) / (nir_dn + red_dn)
        sr = scaling.surface_reflectance(np.array([8000, 20000], dtype=np.uint16))
        sr_ndvi = indices.ndvi(sr[:1], sr[1:])
        assert dn_ndvi[0] == pytest.approx(0.4286, abs=1e-3)
        assert sr_ndvi[0] == pytest.approx(0.33 / 0.37, abs=1e-3)

    @given(st.floats(0.001, 1.0), st.floats(0.001, 1.0))
    def test_bounded(self, a, b):
        v = indices.normalized_difference(np.array([a], np.float32), np.array([b], np.float32))[0]
        assert -1.0 <= v <= 1.0


class TestEducationalLST:
    l8 = lst_educational.THERMAL_CONSTANTS["landsat-8"]

    def test_planck_round_trip(self):
        t = np.array([280.0, 300.0, 330.0], dtype=np.float32)
        rad = lst_educational.planck_radiance(t, self.l8)
        back = lst_educational.brightness_temperature(rad, self.l8)
        np.testing.assert_allclose(back, t, rtol=1e-5)

    def test_brightness_temperature_known(self):
        t = lst_educational.brightness_temperature(np.array([10.0], np.float32), self.l8)
        assert t[0] == pytest.approx(1321.0789 / np.log(774.8853 / 10.0 + 1.0), rel=1e-6)

    def test_emissivity_thresholds(self):
        eps = lst_educational.emissivity_ndvi_threshold(
            np.array([-0.2, 0.1, 0.5, 0.8, np.nan], np.float32)
        )
        np.testing.assert_allclose(eps[:4], [0.991, 0.986, 0.990, 0.990], atol=1e-6)
        assert np.isnan(eps[4])

    def test_blackbody_needs_no_correction(self):
        t = np.array([300.0], np.float32)
        assert lst_educational.single_channel_lst(t, np.array([1.0], np.float32))[
            0
        ] == pytest.approx(300.0)

    def test_emissivity_below_one_raises_temperature(self):
        t = np.array([300.0], np.float32)
        assert lst_educational.single_channel_lst(t, np.array([0.97], np.float32))[0] > 300.0

    def test_radiative_transfer_inverts_forward_model(self):
        rng = np.random.default_rng(0)
        ts = rng.uniform(290, 330, 200).astype(np.float32)
        eps = rng.uniform(0.95, 0.99, 200)
        tau = rng.uniform(0.5, 0.9, 200)
        l_up = rng.uniform(1.0, 3.0, 200)
        l_down = rng.uniform(2.0, 5.0, 200)
        l_s = lst_educational.planck_radiance(ts, self.l8).astype(np.float64)
        l_toa = tau * (eps * l_s + (1 - eps) * l_down) + l_up
        out = lst_educational.radiative_transfer_lst(
            l_toa.astype(np.float32), l_up, l_down, tau, eps, self.l8
        )
        np.testing.assert_allclose(out, ts, atol=1e-3)
