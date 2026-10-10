"""WorldPop population counts (CC BY 4.0).

Release R2025A provides constrained 100 m (3 arc-second) population counts for
every year from 2015 to 2030, so the population layer can match the period of
the surface temperature analysis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from sgheat.config import WorldPopConfig
from sgheat.io.http import download

CITATION = (
    "WorldPop (www.worldpop.org). Global 2015 to 2030 constrained population counts, "
    "release R2025A, 100 m resolution. University of Southampton. CC BY 4.0."
)


def url_for(cfg: WorldPopConfig, year: int) -> str:
    """Download URL of the Singapore raster for ``year``."""
    return cfg.url_template.format(year=year)


def fetch_year(
    http: httpx.Client, cfg: WorldPopConfig, year: int, dest: Path
) -> tuple[str, str, datetime]:
    """Download one year; returns URL, SHA-256 and retrieval time."""
    url = url_for(cfg, year)
    sha = download(http, url, dest)
    return url, sha, datetime.now(UTC)
