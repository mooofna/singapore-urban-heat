"""HDB blocks with footprints and attributes."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from sgheat.buildings.streets import normalise_block, normalise_street

FLAG_COLUMNS = (
    "residential",
    "commercial",
    "market_hawker",
    "miscellaneous",
    "multistorey_carpark",
    "precinct_pavilion",
)
RENTAL_COLUMNS = ("1room_rental", "2room_rental", "3room_rental", "other_room_rental")


def load_properties(frame: pd.DataFrame) -> pd.DataFrame:
    """Typed and normalised *HDB Property Information* table."""
    out = frame.copy()
    out["blk_no"] = normalise_block(out["blk_no"])
    out["street"] = normalise_street(out["street"])
    for col in FLAG_COLUMNS:
        out[col] = out[col].astype("string").str.upper().eq("Y")
    int_cols = ["max_floor_lvl", "year_completed", "total_dwelling_units", *RENTAL_COLUMNS]
    for col in int_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    if out.duplicated(["blk_no", "street"]).any():
        msg = "HDB Property Information has duplicate (blk_no, street) rows"
        raise ValueError(msg)
    return out


def load_footprints(frame: gpd.GeoDataFrame, crs_epsg: int) -> gpd.GeoDataFrame:
    """Footprints with normalised keys, projected to the analysis CRS."""
    cols = {"BLK_NO": "blk_no", "ST_COD": "st_cod", "POSTAL_COD": "postal_code"}
    out = frame.rename(columns=cols)[[*cols.values(), "geometry"]].copy()
    out["blk_no"] = normalise_block(out["blk_no"])
    out["st_cod"] = out["st_cod"].astype("string").str.strip().str.upper()
    out["postal_code"] = out["postal_code"].astype("string").str.strip()
    out = out.to_crs(epsg=crs_epsg)
    out["geometry"] = out.geometry.make_valid()
    return out


@dataclass(frozen=True)
class JoinReport:
    """How completely property records were matched to footprints."""

    n_properties: int
    n_footprints: int
    n_matched: int
    n_unmatched_properties: int
    n_residential: int
    n_residential_matched: int
    n_bridge_codes: int
    n_bridge_unresolved: int

    @property
    def match_rate(self) -> float:
        return self.n_matched / self.n_properties if self.n_properties else float("nan")

    @property
    def residential_match_rate(self) -> float:
        return (
            self.n_residential_matched / self.n_residential if self.n_residential else float("nan")
        )


def join_blocks(
    properties: pd.DataFrame, footprints: gpd.GeoDataFrame, bridge: pd.DataFrame
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, JoinReport]:
    """Attach each property record to its footprint via the street code bridge.

    Returns the matched blocks (footprint geometry plus property attributes), the
    unmatched property records, and a report.
    """
    resolved = bridge.dropna(subset=["street"])[["st_cod", "street"]]
    keyed = footprints.merge(resolved, on="st_cod", how="inner")
    merged = keyed.merge(properties, on=["blk_no", "street"], how="inner", validate="one_to_one")
    blocks = gpd.GeoDataFrame(merged, geometry="geometry", crs=footprints.crs)
    matched_keys = set(zip(blocks["blk_no"], blocks["street"], strict=True))
    is_matched = [
        (b, s) in matched_keys
        for b, s in zip(properties["blk_no"], properties["street"], strict=True)
    ]
    unmatched = properties.loc[[not m for m in is_matched]].copy()
    report = JoinReport(
        n_properties=len(properties),
        n_footprints=len(footprints),
        n_matched=len(blocks),
        n_unmatched_properties=len(unmatched),
        n_residential=int(properties["residential"].sum()),
        n_residential_matched=int(blocks["residential"].sum()),
        n_bridge_codes=len(bridge),
        n_bridge_unresolved=int((bridge["method"] == "unresolved").sum()),
    )
    return blocks, unmatched, report
