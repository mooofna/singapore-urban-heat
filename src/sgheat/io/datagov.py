"""Downloads from data.gov.sg (Singapore Open Data Licence v1.0).

The open API hands out short-lived signed URLs: ``initiate-download`` starts a
download and ``poll-download`` returns the URL once the file is ready. Without
an API key the service allows few downloads per minute, so calls are spaced.
Set ``DATAGOVSG_API_KEY`` to use a key.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from sgheat.io.http import client, download, get_json

OPEN_API = "https://api-open.data.gov.sg/v1/public/api/datasets"
METADATA_API = "https://api-production.data.gov.sg/v2/public/api/datasets"
_SUFFIX = {"CSV": ".csv", "GEOJSON": ".geojson"}


@dataclass(frozen=True)
class DatasetMetadata:
    """Subset of the data.gov.sg metadata recorded in provenance."""

    dataset_id: str
    name: str
    format: str
    last_updated_at: str
    licence: str = "Singapore Open Data Licence v1.0"

    @property
    def suffix(self) -> str:
        return _SUFFIX.get(self.format.upper(), "")


def api_client() -> httpx.Client:
    """Client with the optional API key header."""
    key = os.environ.get("DATAGOVSG_API_KEY")
    return client({"x-api-key": key} if key else None)


def metadata(http: httpx.Client, dataset_id: str) -> DatasetMetadata:
    """Name, format and last update time of a dataset."""
    payload = get_json(http, f"{METADATA_API}/{dataset_id}/metadata")["data"]
    return DatasetMetadata(
        dataset_id=dataset_id,
        name=str(payload.get("name", dataset_id)),
        format=str(payload.get("format", "")),
        last_updated_at=str(payload.get("lastUpdatedAt", "")),
    )


def _signed_url(http: httpx.Client, dataset_id: str, max_polls: int = 30) -> str:
    get_json(http, f"{OPEN_API}/{dataset_id}/initiate-download")
    for _ in range(max_polls):
        data = get_json(http, f"{OPEN_API}/{dataset_id}/poll-download").get("data", {})
        url = data.get("url")
        if url:
            return str(url)
        time.sleep(2.0)
    msg = f"data.gov.sg did not provide a download URL for {dataset_id}"
    raise TimeoutError(msg)


def fetch_dataset(
    http: httpx.Client, dataset_id: str, dest_without_suffix: Path
) -> tuple[Path, DatasetMetadata, str, datetime]:
    """Download a dataset; returns its path, metadata, SHA-256 and retrieval time."""
    meta = metadata(http, dataset_id)
    dest = dest_without_suffix.with_name(dest_without_suffix.name + meta.suffix)
    url = _signed_url(http, dataset_id)
    sha = download(http, url, dest)
    return dest, meta, sha, datetime.now(UTC)
