"""Reading Landsat Level-2 bands for the analysis grid.

The analysis grid shares the Landsat pixel lattice, so a scene is read with an
integer pixel window from each Cloud Optimized GeoTIFF (only the needed byte
ranges travel over the network) and never resampled. Pixels outside the scene
footprint are filled with the band's nodata value.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pystac
import rasterio
from numpy.typing import NDArray
from rasterio.windows import Window

from sgheat.geo.aoi import PixelGrid, same_lattice

# STAC asset keys of the Planetary Computer ``landsat-c2-l2`` collection and the
# corresponding file suffixes of a USGS Level-2 product folder.
ASSET_SUFFIX = {
    "lwir11": "ST_B10",
    "qa_pixel": "QA_PIXEL",
    "red": "SR_B4",
    "nir08": "SR_B5",
    "green": "SR_B3",
    "swir16": "SR_B6",
    "trad": "ST_TRAD",
    "urad": "ST_URAD",
    "drad": "ST_DRAD",
    "atran": "ST_ATRAN",
    "emis": "ST_EMIS",
    "cdist": "ST_CDIST",
}
ANALYSIS_ASSETS = ("lwir11", "qa_pixel", "red", "nir08", "green", "swir16")
NODATA = {"qa_pixel": 1}  # QA fill pixels carry bit 0; every other analysis band uses 0
DEFAULT_NODATA = 0
AUX_NODATA = -9999

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF,.tif,.tiff",
}


class LatticeMismatchError(ValueError):
    """A raster does not share the analysis pixel lattice and would need resampling."""


def _fill_value(asset: str) -> int:
    if asset in ("trad", "urad", "drad", "atran", "emis", "cdist"):
        return AUX_NODATA
    return NODATA.get(asset, DEFAULT_NODATA)


def read_window(href: str, grid: PixelGrid, fill_value: int) -> NDArray[np.generic]:
    """Read band 1 of ``href`` over ``grid`` without resampling."""
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        if src.crs is None or src.crs.to_epsg() != grid.crs_epsg:
            msg = f"{href} is not in EPSG:{grid.crs_epsg}"
            raise LatticeMismatchError(msg)
        if not same_lattice(src.transform, grid):
            msg = f"{href} is not on the analysis pixel lattice"
            raise LatticeMismatchError(msg)
        col_off = round((grid.transform.c - src.transform.c) / src.transform.a)
        row_off = round((grid.transform.f - src.transform.f) / src.transform.e)
        window = Window(col_off, row_off, grid.width, grid.height)
        return np.asarray(src.read(1, window=window, boundless=True, fill_value=fill_value))


def read_assets(
    hrefs: Mapping[str, str], grid: PixelGrid, max_workers: int = 6
) -> dict[str, NDArray[np.generic]]:
    """Read several assets in parallel (GDAL releases the GIL during network reads)."""
    keys = list(hrefs)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        arrays = pool.map(lambda k: read_window(hrefs[k], grid, _fill_value(k)), keys)
        return dict(zip(keys, arrays, strict=True))


def item_hrefs(item: pystac.Item, assets: tuple[str, ...] = ANALYSIS_ASSETS) -> dict[str, str]:
    """Signed asset URLs of a STAC item."""
    return {a: item.assets[a].href for a in assets}


def local_hrefs(
    folder: Path, product_id: str, assets: tuple[str, ...] = ANALYSIS_ASSETS
) -> dict[str, str]:
    """Paths of the bands in a USGS Level-2 product folder (``<product_id>_<SUFFIX>.TIF``)."""
    out = {}
    for a in assets:
        path = folder / f"{product_id}_{ASSET_SUFFIX[a]}.TIF"
        if not path.exists():
            msg = f"missing {path}"
            raise FileNotFoundError(msg)
        out[a] = str(path)
    return out
