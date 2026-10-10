"""Landsat scene discovery through the Microsoft Planetary Computer STAC API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import planetary_computer
import pystac
import pystac_client
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from sgheat.config import ScenesConfig

SGT = timedelta(hours=8)


@dataclass(frozen=True)
class SceneRecord:
    """Metadata of one Landsat Collection 2 Level-2 item."""

    item_id: str
    platform: str
    datetime_utc: datetime
    wrs_path: str
    wrs_row: str
    collection_category: str
    cloud_cover: float
    cloud_cover_land: float
    created: str
    proj_transform: tuple[float, ...]

    @property
    def datetime_sgt(self) -> datetime:
        return self.datetime_utc + SGT

    @classmethod
    def from_item(cls, item: pystac.Item) -> SceneRecord:
        """Extract the fields the pipeline needs from a STAC item."""
        p: dict[str, Any] = item.properties
        dt = item.datetime or datetime.fromisoformat(str(p["datetime"]))
        return cls(
            item_id=item.id,
            platform=str(p["platform"]),
            datetime_utc=dt.astimezone(UTC),
            wrs_path=str(p.get("landsat:wrs_path", "")),
            wrs_row=str(p.get("landsat:wrs_row", "")),
            collection_category=str(p.get("landsat:collection_category", "")),
            cloud_cover=float(p.get("eo:cloud_cover", float("nan"))),
            cloud_cover_land=float(p.get("landsat:cloud_cover_land", float("nan"))),
            created=str(p.get("created", "")),
            proj_transform=tuple(float(v) for v in p.get("proj:transform", ())),
        )


def open_catalog(cfg: ScenesConfig) -> pystac_client.Client:
    """STAC client that signs asset URLs with anonymous Planetary Computer tokens."""
    return pystac_client.Client.open(cfg.stac_url, modifier=planetary_computer.sign_inplace)


def search_scenes(
    cfg: ScenesConfig,
    footprint: BaseGeometry,
    start: date | None = None,
    end: date | None = None,
) -> list[pystac.Item]:
    """Items of the configured WRS-2 path/row that intersect ``footprint`` (WGS84)."""
    first = start or cfg.start
    last = end or cfg.end or (datetime.now(UTC).date() + timedelta(days=1))
    catalog = open_catalog(cfg)
    search = catalog.search(
        collections=[cfg.collection],
        intersects=mapping(footprint),
        datetime=f"{first.isoformat()}/{last.isoformat()}",
        query={
            "platform": {"in": list(cfg.platforms)},
            "landsat:wrs_path": {"eq": cfg.wrs_path},
            "landsat:wrs_row": {"eq": cfg.wrs_row},
            "landsat:collection_category": {"eq": cfg.collection_category},
            "landsat:cloud_cover_land": {"lte": cfg.max_cloud_cover_land},
        },
        sortby=[{"field": "properties.datetime", "direction": "asc"}],
    )
    return list(search.items())


def get_item(cfg: ScenesConfig, item_id: str) -> pystac.Item:
    """Fetch one item by id (asset URLs signed)."""
    item = open_catalog(cfg).get_collection(cfg.collection).get_item(item_id)
    if item is None:
        msg = f"STAC item {item_id} not found in {cfg.collection}"
        raise LookupError(msg)
    return item
