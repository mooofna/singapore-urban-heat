"""Cut the small offline fixture used by the tests and the CI pipeline run.

The fixture is a 6 km by 6 km window around Bishan and Toa Payoh: one real
Landsat 8 Level-2 scene (2018-05-24, USGS, public domain), the matching
WorldPop crop (CC BY 4.0) and the data.gov.sg layers clipped to the window
(Singapore Open Data Licence). Run once from the repository root after
``sgheat fetch`` with a config that points ``paths.local_l2_dir`` at the
unpacked Level-2 product::

    uv run python scripts/make_fixtures.py --config configs/local.toml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.windows import Window, from_bounds

from sgheat.config import load_config
from sgheat.paths import DataPaths

OUT = Path("tests/fixtures/sg_crop")
PRODUCT = "LC08_L2SP_125059_20180524_20200901_02_T1"
ITEM_ID = "LC08_L2SP_125059_20180524_02_T1"
# Window centre (UTM 48N) near Bishan-Ang Mo Kio Park, snapped to the Landsat lattice below.
CENTRE = (372_000.0, 150_500.0)
SIZE_PX = 200
BANDS = [
    "ST_B10",
    "QA_PIXEL",
    "SR_B3",
    "SR_B4",
    "SR_B5",
    "SR_B6",
    "ST_TRAD",
    "ST_URAD",
    "ST_DRAD",
    "ST_ATRAN",
    "ST_EMIS",
]


def crop_landsat(l2_dir: Path) -> tuple[float, float, float, float]:
    """Write the band crops and return the window bounds."""
    out = OUT / "landsat" / ITEM_ID
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(l2_dir / f"{PRODUCT}_ST_B10.TIF") as src:
        col = int((CENTRE[0] - src.transform.c) / 30) - SIZE_PX // 2
        row = int((src.transform.f - CENTRE[1]) / 30) - SIZE_PX // 2
        window = Window(col, row, SIZE_PX, SIZE_PX)
        transform = src.window_transform(window)
        bounds = rasterio.windows.bounds(window, src.transform)
    for band in BANDS:
        with rasterio.open(l2_dir / f"{PRODUCT}_{band}.TIF") as src:
            data = src.read(1, window=window)
            profile = src.profile | {
                "width": SIZE_PX,
                "height": SIZE_PX,
                "transform": transform,
                "compress": "deflate",
                "predictor": 2,
                "tiled": False,
                "blockxsize": None,
                "blockysize": None,
            }
            profile = {k: v for k, v in profile.items() if v is not None}
        with rasterio.open(out / f"{PRODUCT}_{band}.TIF", "w", **profile) as dst:
            dst.write(data, 1)
    return bounds


def write_item(bounds: tuple[float, float, float, float]) -> None:
    """A minimal STAC item whose assets point at the cropped bands."""
    folder = OUT / "landsat" / ITEM_ID
    key = {
        "ST_B10": "lwir11",
        "QA_PIXEL": "qa_pixel",
        "SR_B3": "green",
        "SR_B4": "red",
        "SR_B5": "nir08",
        "SR_B6": "swir16",
        "ST_TRAD": "trad",
        "ST_URAD": "urad",
        "ST_DRAD": "drad",
        "ST_ATRAN": "atran",
        "ST_EMIS": "emis",
    }
    box_wgs = gpd.GeoSeries([shapely.box(*bounds)], crs=32648).to_crs(4326).iloc[0]
    item = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": ITEM_ID,
        "geometry": shapely.geometry.mapping(box_wgs),
        "bbox": list(box_wgs.bounds),
        "properties": {
            "datetime": "2018-05-24T03:15:32.026827Z",
            "platform": "landsat-8",
            "landsat:wrs_path": "125",
            "landsat:wrs_row": "059",
            "landsat:collection_category": "T1",
            "eo:cloud_cover": 5.68,
            "landsat:cloud_cover_land": 9.93,
            "created": "2022-05-06T16:58:02.217941Z",
            "proj:transform": [30.0, 0.0, bounds[0], 0.0, -30.0, bounds[3]],
        },
        "assets": {key[b]: {"href": f"./{PRODUCT}_{b}.TIF", "type": "image/tiff"} for b in BANDS},
        "links": [],
    }
    (folder / "item.json").write_text(json.dumps(item, indent=2) + "\n")


def clip_static(
    paths: DataPaths, cfg_ids: dict[str, str], bounds: tuple[float, float, float, float]
) -> None:
    """Clip the data.gov.sg layers and WorldPop to the window."""
    box = shapely.box(*bounds)
    out = OUT / "raw" / "datagov"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("planning_areas", "subzones"):
        did = cfg_ids[name]
        src = next(paths.raw.joinpath("datagov").glob(f"{did}.geojson"))
        gdf = gpd.read_file(src).to_crs(32648)
        gdf = gdf[gdf.intersects(box)].copy()
        gdf["geometry"] = gdf.intersection(box)
        gdf.to_crs(4326).to_file(out / f"{did}.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
    fp_id = cfg_ids["hdb_footprints"]
    fps = gpd.read_file(next(paths.raw.joinpath("datagov").glob(f"{fp_id}.geojson"))).to_crs(32648)
    fps = fps.loc[fps.intersects(box), ["BLK_NO", "ST_COD", "POSTAL_COD", "geometry"]].copy()
    # Rotated bounding rectangles keep position, size and orientation, enough for tests.
    fps["geometry"] = shapely.oriented_envelope(fps.geometry.to_numpy())
    # FlatGeobuf keeps the fixture small; gpd.read_file reads it like the GeoJSON download.
    fps.to_crs(4326).to_file(out / f"{fp_id}.fgb", driver="FlatGeobuf")
    prop_id = cfg_ids["hdb_property"]
    props = pd.read_csv(
        next(paths.raw.joinpath("datagov").glob(f"{prop_id}.csv")), dtype={"blk_no": str}
    )
    bridge = pd.read_csv(paths.street_bridge, dtype=str)
    streets = set(bridge.loc[bridge["st_cod"].isin(fps["ST_COD"]), "street"].dropna())
    props[props["street"].isin(streets)].to_csv(out / f"{prop_id}.csv", index=False)
    wp_src = paths.worldpop(2023)
    wp_out = OUT / "raw" / "worldpop" / wp_src.name
    wp_out.parent.mkdir(parents=True, exist_ok=True)
    wgs = gpd.GeoSeries([box.buffer(500)], crs=32648).to_crs(4326).total_bounds
    with rasterio.open(wp_src) as src:
        win = from_bounds(*wgs, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=win)
        profile = src.profile | {
            "width": data.shape[1],
            "height": data.shape[0],
            "transform": src.window_transform(win),
            "compress": "deflate",
        }
    with rasterio.open(wp_out, "w", **profile) as dst:
        dst.write(data, 1)
    bridge_out = OUT / "reference" / "hdb_street_codes.csv"
    bridge_out.parent.mkdir(parents=True, exist_ok=True)
    bridge[bridge["st_cod"].isin(fps["ST_COD"])].to_csv(bridge_out, index=False)


def main() -> None:
    """Build the fixture."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    if cfg.paths.local_l2_dir is None:
        raise SystemExit("paths.local_l2_dir must point at the unpacked Level-2 product")
    bounds = crop_landsat(cfg.paths.local_l2_dir)
    write_item(bounds)
    ids = cfg.datagov.model_dump()
    clip_static(DataPaths(cfg.paths.data_dir), ids, bounds)
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"fixture written to {OUT} ({total / 1e6:.2f} MB), bounds {bounds}")
    print(np.round(bounds, 1))


if __name__ == "__main__":
    main()
