"""Bridge between HDB street codes and street names.

The two HDB datasets share no key. *HDB Property Information* lists blocks by
block number and (abbreviated) street name; *HDB Existing Building* has
footprints with block number, postal code and an internal street code
(``ST_COD``). The bridge maps every street code to a street name with two
kinds of evidence:

1. Spatial votes (preferred): geocoded property records that fall inside a
   footprint with the same block number vote for that footprint's street code.
2. Block sets: the set of block numbers under a street code is compared with the
   set under each street name (Jaccard index). Small sets are ambiguous, since
   many streets have a block 1 to 4, so this evidence is accepted only for sets
   of at least ``min_blocks`` with a clear margin over the runner-up.

Codes supported by neither are left unresolved and reported.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd


def normalise_block(values: pd.Series) -> pd.Series:
    """Upper-case, stripped block numbers as strings."""
    return values.astype("string").str.strip().str.upper()


def normalise_street(values: pd.Series) -> pd.Series:
    """Upper-case street names with single spaces."""
    return values.astype("string").str.upper().str.replace(r"\s+", " ", regex=True).str.strip()


@dataclass(frozen=True)
class BridgeSettings:
    """Acceptance thresholds for block-set evidence."""

    min_jaccard: float = 0.5
    min_margin: float = 0.2
    min_blocks: int = 3


def block_set_matches(footprints: pd.DataFrame, properties: pd.DataFrame) -> pd.DataFrame:
    """Best and second-best street name for each street code by Jaccard index of block sets."""
    code_sets = footprints.groupby("st_cod")["blk_no"].apply(set)
    street_sets = properties.groupby("street")["blk_no"].apply(set)
    block_to_streets: dict[str, set[str]] = defaultdict(set)
    for street, blocks in street_sets.items():
        for b in blocks:
            block_to_streets[b].add(str(street))
    rows = []
    for code, blocks in code_sets.items():
        overlap: dict[str, int] = defaultdict(int)
        for b in blocks:
            for s in block_to_streets.get(b, ()):
                overlap[s] += 1
        scored = sorted(
            ((n / len(blocks | street_sets[s]), s) for s, n in overlap.items()),
            key=lambda t: (-t[0], t[1]),
        )
        best_j, best_s = scored[0] if scored else (0.0, None)
        second_j = scored[1][0] if len(scored) > 1 else 0.0
        rows.append(
            {
                "st_cod": code,
                "block_street": best_s,
                "jaccard": best_j,
                "jaccard_runner_up": second_j,
                "n_blocks_code": len(blocks),
            }
        )
    return pd.DataFrame(rows)


def spatial_votes(footprints: gpd.GeoDataFrame, geocoded: gpd.GeoDataFrame) -> pd.DataFrame:
    """Street name with the most votes per street code from geocoded points inside footprints."""
    joined = gpd.sjoin(
        geocoded[["blk_no", "street", "geometry"]],
        footprints[["blk_no", "st_cod", "geometry"]],
        predicate="within",
        lsuffix="pt",
        rsuffix="fp",
    )
    joined = joined[joined["blk_no_pt"] == joined["blk_no_fp"]]
    votes = joined.groupby(["st_cod", "street"]).size().rename("votes").reset_index()
    total = votes.groupby("st_cod")["votes"].transform("sum")
    votes["vote_share"] = votes["votes"] / total
    best = votes.sort_values(["st_cod", "votes", "street"], ascending=[True, False, True])
    best = best.drop_duplicates("st_cod")
    best = best.rename(columns={"street": "spatial_street"})
    return pd.DataFrame(best[["st_cod", "spatial_street", "votes", "vote_share"]])


def build_bridge(
    footprints: pd.DataFrame,
    properties: pd.DataFrame,
    spatial: pd.DataFrame | None = None,
    settings: BridgeSettings | None = None,
) -> pd.DataFrame:
    """Street code to street name table with the evidence behind each row.

    ``method`` is ``spatial`` (votes, agreeing or not with block sets),
    ``block_sets`` (block-set evidence only) or ``unresolved``.
    """
    s = settings or BridgeSettings()
    table = block_set_matches(footprints, properties)
    if spatial is not None and len(spatial):
        table = table.merge(spatial, on="st_cod", how="left")
    else:
        table["spatial_street"] = pd.NA
        table["votes"] = 0
        table["vote_share"] = float("nan")
    table["votes"] = table["votes"].fillna(0).astype(int)
    block_ok = (
        (table["jaccard"] >= s.min_jaccard)
        & (table["jaccard"] - table["jaccard_runner_up"] >= s.min_margin)
        & (table["n_blocks_code"] >= s.min_blocks)
    )
    has_spatial = table["spatial_street"].notna()
    table["street"] = table["spatial_street"].where(
        has_spatial, table["block_street"].where(block_ok)
    )
    table["method"] = "unresolved"
    table.loc[block_ok, "method"] = "block_sets"
    table.loc[has_spatial, "method"] = "spatial"
    table["agrees_with_block_sets"] = has_spatial & (
        table["spatial_street"] == table["block_street"]
    )
    cols = [
        "st_cod",
        "street",
        "method",
        "votes",
        "vote_share",
        "block_street",
        "jaccard",
        "jaccard_runner_up",
        "n_blocks_code",
        "agrees_with_block_sets",
    ]
    return table[cols].sort_values("st_cod").reset_index(drop=True)
