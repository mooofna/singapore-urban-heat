"""Contracts with external services. Run with ``pytest -m network -o addopts=""``."""

from datetime import date

import httpx
import pytest
import shapely

from sgheat.config import Config
from sgheat.io import datagov, stac, worldpop
from sgheat.physics.scaling import SURFACE_REFLECTANCE, SURFACE_TEMPERATURE, BandScaling

pytestmark = pytest.mark.network
CFG = Config()
SINGAPORE = shapely.box(103.6, 1.16, 104.09, 1.48)


def test_stac_returns_the_reference_scene_with_expected_assets():
    items = stac.search_scenes(
        CFG.scenes, SINGAPORE, start=date(2018, 5, 20), end=date(2018, 5, 30)
    )
    ids = [i.id for i in items]
    assert "LC08_L2SP_125059_20180524_02_T1" in ids
    item = items[ids.index("LC08_L2SP_125059_20180524_02_T1")]
    for asset in (
        "lwir11",
        "qa_pixel",
        "red",
        "nir08",
        "green",
        "swir16",
        "trad",
        "urad",
        "drad",
        "atran",
        "emis",
    ):
        assert asset in item.assets
    st = BandScaling.from_raster_bands(item.assets["lwir11"].extra_fields["raster:bands"])
    sr = BandScaling.from_raster_bands(item.assets["red"].extra_fields["raster:bands"])
    assert st == SURFACE_TEMPERATURE
    assert sr == SURFACE_REFLECTANCE
    assert item.properties["proj:code"] == "EPSG:32648"


@pytest.mark.parametrize(
    "dataset_id",
    [
        CFG.datagov.hdb_property,
        CFG.datagov.hdb_footprints,
        CFG.datagov.planning_areas,
        CFG.datagov.subzones,
    ],
)
def test_datagov_metadata(dataset_id):
    with datagov.api_client() as http:
        meta = datagov.metadata(http, dataset_id)
    assert meta.format.upper() in {"CSV", "GEOJSON"}
    assert meta.last_updated_at


def test_worldpop_raster_exists():
    url = worldpop.url_for(CFG.worldpop, CFG.model.worldpop_year)
    response = httpx.head(url, follow_redirects=True, timeout=60)
    assert response.status_code == 200
