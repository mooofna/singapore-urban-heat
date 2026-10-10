"""How much each simplification of the textbook LST derivation costs.

For a few clear scenes the three educational estimators are compared with the
USGS ``ST_B10`` product over clear land pixels:

* ``brightness``: TOA brightness temperature (no emissivity, no atmosphere),
* ``single_channel``: plus NDVI-threshold emissivity (the course version, but on
  surface reflectance with fixed thresholds),
* ``radiative_transfer``: full inversion with the USGS atmospheric terms.

If a local Level-1 band 10 is configured, its radiance is also checked against
the Level-2 ``ST_TRAD`` band that the estimators use.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from sgheat.io import landsat, stac
from sgheat.physics import lst_educational as edu
from sgheat.physics.indices import ndvi
from sgheat.physics.qa import decode_qa_pixel
from sgheat.physics.scaling import (
    ST_RADIANCE,
    ST_UNITLESS,
    apply_scaling,
    surface_reflectance,
    surface_temperature_kelvin,
)
from sgheat.stages.context import RunContext
from sgheat.stages.grid import landsat_grid_mask, pixel_grid
from sgheat.stages.scenes import load_catalog

log = logging.getLogger(__name__)
PHYSICS_ASSETS = ("lwir11", "qa_pixel", "red", "nir08", "trad", "urad", "drad", "atran", "emis")
REFERENCE_SCENE = "LC08_L2SP_125059_20180524_02_T1"
SAMPLE_SIZE = 3000


def _errors(estimate: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    diff = estimate - truth
    return {
        "bias_k": float(np.mean(diff)),
        "mae_k": float(np.mean(np.abs(diff))),
        "rmse_k": float(np.sqrt(np.mean(diff**2))),
        "p95_abs_k": float(np.percentile(np.abs(diff), 95)),
    }


def compare(
    raw: dict[str, np.ndarray], land: np.ndarray, platform: str, seed: int = 0
) -> dict[str, Any]:
    """Estimator errors against ``ST_B10`` over clear land pixels."""
    masks = decode_qa_pixel(raw["qa_pixel"].astype(np.uint16))
    st = surface_temperature_kelvin(raw["lwir11"])
    trad = apply_scaling(raw["trad"], ST_RADIANCE)
    urad = apply_scaling(raw["urad"], ST_RADIANCE)
    drad = apply_scaling(raw["drad"], ST_RADIANCE)
    atran = apply_scaling(raw["atran"], ST_UNITLESS)
    emis = apply_scaling(raw["emis"], ST_UNITLESS)
    nd = ndvi(surface_reflectance(raw["red"]), surface_reflectance(raw["nir08"]))
    k = edu.THERMAL_CONSTANTS[platform]
    bt = edu.brightness_temperature(trad, k)
    sc = edu.single_channel_lst(bt, edu.emissivity_ndvi_threshold(nd))
    rt = edu.radiative_transfer_lst(trad, urad, drad, atran, emis, k)
    valid = masks.land & land
    for arr in (st, bt, sc, rt):
        valid &= np.isfinite(arr)
    truth = st[valid].astype(np.float64)
    out: dict[str, Any] = {"n_pixels": int(valid.sum()), "st_mean_c": float(truth.mean() - 273.15)}
    for name, est in (("brightness", bt), ("single_channel", sc), ("radiative_transfer", rt)):
        out[name] = _errors(est[valid].astype(np.float64), truth)
    rng = np.random.default_rng(seed)
    idx = rng.choice(truth.size, size=min(SAMPLE_SIZE, truth.size), replace=False)
    out["sample"] = {
        "st_c": np.round(truth[idx] - 273.15, 2).tolist(),
        "single_channel_c": np.round(sc[valid][idx].astype(np.float64) - 273.15, 2).tolist(),
        "brightness_c": np.round(bt[valid][idx].astype(np.float64) - 273.15, 2).tolist(),
    }
    out["atmosphere"] = {
        "transmission_mean": float(np.nanmean(atran[valid])),
        "upwelled_mean": float(np.nanmean(urad[valid])),
    }
    return out


def _mtl_value(mtl: Path, key: str) -> float:
    match = re.search(rf"{key}\s*=\s*([-\d.E+]+)", mtl.read_text())
    if match is None:
        msg = f"{key} not in {mtl}"
        raise KeyError(msg)
    return float(match.group(1))


def level1_check(ctx: RunContext, raw_trad: np.ndarray) -> dict[str, float] | None:
    """Compare a local Level-1 band 10 radiance with ``ST_TRAD`` of the same scene."""
    folder = ctx.config.paths.local_l1_dir
    if folder is None:
        return None
    b10 = next(folder.glob("LC08_L1TP_125059_20180524_*_B10.TIF"), None)
    mtl = next(folder.glob("LC08_L1TP_125059_20180524_*_MTL.txt"), None)
    if b10 is None or mtl is None:
        return None
    dn = landsat.read_window(str(b10), pixel_grid(ctx), fill_value=0)
    radiance = edu.dn_to_radiance(
        dn, _mtl_value(mtl, "RADIANCE_MULT_BAND_10"), _mtl_value(mtl, "RADIANCE_ADD_BAND_10")
    )
    trad = apply_scaling(raw_trad, ST_RADIANCE)
    ok = np.isfinite(radiance) & np.isfinite(trad)
    diff = radiance[ok] - trad[ok]
    return {
        "n_pixels": int(ok.sum()),
        "max_abs_diff": float(np.max(np.abs(diff))),
        "mean_diff": float(np.mean(diff)),
    }


def run(ctx: RunContext, n_scenes: int = 6) -> None:
    """Physics report for the reference scene plus the clearest scenes of other seasons."""
    grid = pixel_grid(ctx)
    land = landsat_grid_mask(ctx)
    catalog = load_catalog(ctx)
    acc = catalog[catalog["status"] == "accepted"].sort_values("sg_clear_frac", ascending=False)
    chosen = [REFERENCE_SCENE] + [
        i for i in acc.drop_duplicates("season")["item_id"].tolist() if i != REFERENCE_SCENE
    ]
    chosen += [i for i in acc["item_id"].tolist() if i not in chosen]
    chosen = chosen[:n_scenes]
    results = []
    l1 = None
    for item_id in chosen:
        local = ctx.config.paths.local_l2_dir
        if item_id == REFERENCE_SCENE and local is not None and local.exists():
            hrefs = landsat.local_hrefs(
                local, "LC08_L2SP_125059_20180524_20200901_02_T1", PHYSICS_ASSETS
            )
            source = "local USGS Level-2 product"
        else:
            hrefs = landsat.item_hrefs(stac.get_item(ctx.config.scenes, item_id), PHYSICS_ASSETS)
            source = "Planetary Computer"
        raw = landsat.read_assets(hrefs, grid)
        platform = "landsat-9" if item_id.startswith("LC09") else "landsat-8"
        res = compare(raw, land, platform)
        res.update(item_id=item_id, platform=platform, source=source)
        row = catalog.loc[catalog["item_id"] == item_id]
        res["date_sgt"] = str(row["date_sgt"].iloc[0]) if len(row) else None
        res["season"] = str(row["season"].iloc[0]) if len(row) else None
        if item_id == REFERENCE_SCENE:
            l1 = level1_check(ctx, raw["trad"])
        results.append(res)
        log.info(
            "%s: RMSE brightness %.2f K, single channel %.2f K, radiative transfer %.3f K",
            item_id,
            res["brightness"]["rmse_k"],
            res["single_channel"]["rmse_k"],
            res["radiative_transfer"]["rmse_k"],
        )
    report = {"scenes": results, "level1_vs_trad": l1}
    ctx.paths.physics_report.parent.mkdir(parents=True, exist_ok=True)
    ctx.paths.physics_report.write_text(json.dumps(report) + "\n")
