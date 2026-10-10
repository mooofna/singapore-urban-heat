"""Offline end-to-end run on the fixture window, shared by the tests and CI.

The fixture holds one real scene (2018-05-24). Ten synthetic scenes spread over
2014 to 2025 are derived from it: each gets an island-wide offset, pixel
noise, random cloud discs and, inside a planted square, a warming trend of
0.5 K per year. The pipeline must recover the trend and the stages must run
exactly as they do on the full data.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

import numpy as np
import rasterio

from sgheat.config import Config, GridConfig, ModelConfig, PathsConfig, ScenesConfig, TemporalConfig
from sgheat.stages import pipeline, scenes
from sgheat.stages.context import RunContext

FIXTURE = Path(__file__).parent / "fixtures" / "sg_crop"
BASE_ITEM = "LC08_L2SP_125059_20180524_02_T1"
PRODUCT = "LC08_L2SP_125059_20180524_20200901_02_T1"
DATES = [
    date(2014, 2, 3),
    date(2015, 4, 8),
    date(2016, 7, 11),
    date(2017, 10, 2),
    date(2018, 5, 24),
    date(2019, 1, 20),
    date(2020, 6, 9),
    date(2021, 11, 14),
    date(2023, 3, 1),
    date(2025, 8, 19),
]
TREND_K_PER_YEAR = 0.5
# Planted warming square in pixel rows and columns of the 200 x 200 crop.
TREND_ROWS = slice(20, 80)
TREND_COLS = slice(20, 80)
CLOUD_QA = 22280  # high-confidence cloud


def synthetic_scenes(dest: Path, seed: int = 7) -> list[str]:
    """Write the synthetic scene folders (STAC item plus bands) and return their ids."""
    rng = np.random.default_rng(seed)
    base = FIXTURE / "landsat" / BASE_ITEM
    item_template = json.loads((base / "item.json").read_text())
    with rasterio.open(base / f"{PRODUCT}_ST_B10.TIF") as src:
        st = src.read(1).astype(np.float64)
        st_profile = src.profile
    with rasterio.open(base / f"{PRODUCT}_QA_PIXEL.TIF") as src:
        qa = src.read(1)
        qa_profile = src.profile
    ids = []
    yy, xx = np.mgrid[0 : st.shape[0], 0 : st.shape[1]]
    for d in DATES:
        platform = "landsat-9" if d.year >= 2022 and d.month % 2 == 1 else "landsat-8"
        prefix = "LC09" if platform == "landsat-9" else "LC08"
        item_id = f"{prefix}_L2SP_125059_{d:%Y%m%d}_02_T1"
        folder = dest / item_id
        folder.mkdir(parents=True, exist_ok=True)
        for band in base.glob("*.TIF"):
            shutil.copy(band, folder / band.name)
        offset_k = rng.normal(0, 2.0)
        noise = rng.normal(0, 0.3, st.shape)
        years = (d - date(2014, 1, 1)).days / 365.25
        trend = np.zeros(st.shape)
        trend[TREND_ROWS, TREND_COLS] = TREND_K_PER_YEAR * years
        valid = st > 0
        new_st = np.where(valid, st + (offset_k + noise + trend) / 0.00341802, 0)
        new_qa = qa.copy()
        for _ in range(rng.integers(1, 4)):
            cy, cx, rad = rng.integers(0, 200), rng.integers(0, 200), rng.integers(8, 25)
            new_qa[(yy - cy) ** 2 + (xx - cx) ** 2 < rad**2] = CLOUD_QA
        with rasterio.open(folder / f"{PRODUCT}_ST_B10.TIF", "w", **st_profile) as dst:
            dst.write(np.clip(new_st, 0, 65535).astype(np.uint16), 1)
        with rasterio.open(folder / f"{PRODUCT}_QA_PIXEL.TIF", "w", **qa_profile) as dst:
            dst.write(new_qa, 1)
        item = json.loads(json.dumps(item_template))
        item["id"] = item_id
        stamp = datetime(d.year, d.month, d.day, 3, 16, 0)
        item["properties"]["datetime"] = stamp.isoformat() + "Z"
        item["properties"]["platform"] = platform
        (folder / "item.json").write_text(json.dumps(item))
        ids.append(item_id)
    return ids


def fixture_config(root: Path) -> Config:
    """Configuration of the offline run below ``root``."""
    return Config(
        paths=PathsConfig(
            data_dir=root / "data",
            web_data_dir=root / "web",
            local_scenes_dir=root / "scenes",
            local_l2_dir=FIXTURE / "landsat" / BASE_ITEM,
        ),
        scenes=ScenesConfig(source="local"),
        grid=GridConfig(radii_m=(200, 400), primary_radius_m=200),
        temporal=TemporalConfig(min_obs=3, trend_min_obs=6, trend_min_years=5.0),
        model=ModelConfig(
            period_start=date(2013, 1, 1),
            period_end=date(2026, 12, 31),
            impact_draws=200,
            lisa_permutations=999,
        ),
    )


def prepare(root: Path) -> RunContext:
    """Copy the fixture inputs and write the synthetic scenes."""
    ctx = RunContext(fixture_config(root))
    shutil.copytree(FIXTURE / "raw", ctx.paths.raw, dirs_exist_ok=True)
    shutil.copytree(FIXTURE / "reference", ctx.paths.reference, dirs_exist_ok=True)
    synthetic_scenes(root / "scenes")
    return ctx


def run_all(ctx: RunContext) -> None:
    """Every stage in order, as ``sgheat run`` does (without downloads)."""
    pipeline.prepare_static(ctx, fetch=False)
    scenes.discover(ctx)
    scenes.process(ctx, workers=2)
    pipeline.analyse(ctx, physics_scenes=1)
