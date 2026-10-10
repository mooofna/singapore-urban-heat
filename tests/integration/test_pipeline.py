import json

import numpy as np
import pandas as pd
import pytest

from sgheat.stages.grid import load_zones
from sgheat.stages.scenes import load_catalog
from tests.fixture_pipeline import DATES, TREND_K_PER_YEAR, prepare, run_all


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    root = tmp_path_factory.mktemp("pipeline")
    ctx = prepare(root)
    run_all(ctx)
    return ctx


@pytest.mark.slow
def test_every_scene_is_accounted_for(ran):
    catalog = load_catalog(ran)
    assert len(catalog) == len(DATES)
    assert set(catalog["status"]) <= {"accepted", "rejected"}
    assert (catalog["status"] == "accepted").sum() >= 8


@pytest.mark.slow
def test_planted_trend_is_recovered(ran):
    zones = load_zones(ran, "r200")
    temporal = pd.read_parquet(ran.paths.temporal("r200")).merge(
        pd.DataFrame(zones[["zone_id"]]).assign(
            cx=zones.geometry.centroid.x, cy=zones.geometry.centroid.y
        ),
        on="zone_id",
    )
    # Planted square: pixel rows and columns 20 to 80; window top-left corner (368985, 153525).
    inside = temporal["cx"].between(368985 + 25 * 30, 368985 + 75 * 30) & temporal["cy"].between(
        153525 - 75 * 30, 153525 - 25 * 30
    )
    outside = ~temporal["cx"].between(368985 + 10 * 30, 368985 + 90 * 30) | ~temporal["cy"].between(
        153525 - 90 * 30, 153525 - 10 * 30
    )
    slope_in = temporal.loc[inside, "trend_k_per_decade"].median()
    slope_out = temporal.loc[outside, "trend_k_per_decade"].median()
    # The anomaly is relative to the scene level, so the planted square warms relative to the rest.
    assert slope_in - slope_out == pytest.approx(TREND_K_PER_YEAR * 10, rel=0.25)
    assert (temporal.loc[inside, "trend_q"] < 0.05).mean() > 0.8


@pytest.mark.slow
def test_population_is_conserved(ran):
    pa = pd.read_parquet(ran.paths.features("pa"))["population"].sum()
    sz = pd.read_parquet(ran.paths.features("sz"))["population"].sum()
    # Planning areas and subzones are clipped to the window independently, hence 1e-4.
    assert pa == pytest.approx(sz, rel=1e-4)


@pytest.mark.slow
def test_models_and_bundle(ran):
    report = json.loads(ran.paths.model("r200").read_text())
    assert {m["kind"] for m in report["models"]} == {"OLS", "SAR", "SEM", "SDM"}
    assert report["n"] > 100
    web_dir = ran.config.paths.web_data_dir
    manifest = json.loads((web_dir / "manifest.json").read_text())
    assert manifest["primary_zone_set"] == "r200"
    cols = json.loads((web_dir / "zones" / "r200.json").read_text())
    n = len(cols["id"])
    assert all(
        len(v) == n for k, v in cols.items() if (isinstance(v, list) and k != "pa") or k == "pa"
    )
    accepted = load_catalog(ran).query("status == 'accepted'")["item_id"]
    for item in accepted:
        raw = (web_dir / "scenes" / "r200" / f"{item}.bin").read_bytes()
        assert len(raw) == 2 * 2 * n  # two int16 layers


@pytest.mark.slow
def test_physics_on_real_crop(ran):
    report = json.loads(ran.paths.physics_report.read_text())
    ref = report["scenes"][0]
    assert abs(ref["radiative_transfer"]["bias_k"]) < 0.3
    assert ref["single_channel"]["bias_k"] < -5  # no atmospheric correction underestimates LST
    assert np.isfinite(ref["atmosphere"]["transmission_mean"])
