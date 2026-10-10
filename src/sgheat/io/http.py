"""HTTP downloads with retries, atomic writes and checksums."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sgheat.provenance import package_version

USER_AGENT = f"sgheat/{package_version()} (+https://github.com/mooofna/singapore-urban-heat)"
TIMEOUT = httpx.Timeout(60.0, connect=20.0)
_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


def client(headers: dict[str, str] | None = None) -> httpx.Client:
    """An ``httpx`` client with the project user agent and generous timeouts."""
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    return httpx.Client(headers=merged, timeout=TIMEOUT, follow_redirects=True)


def _raise_for_retryable(response: httpx.Response) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
def get_json(http: httpx.Client, url: str, **params: Any) -> Any:
    """GET a JSON document, retrying on transport errors, 429 and 5xx."""
    response = http.get(url, params=params or None)
    _raise_for_retryable(response)
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
def download(http: httpx.Client, url: str, dest: Path) -> str:
    """Stream ``url`` to ``dest`` atomically and return the SHA-256 of the content."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.")
    try:
        with os.fdopen(fd, "wb") as fh, http.stream("GET", url) as response:
            _raise_for_retryable(response)
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_size=1 << 20):
                fh.write(chunk)
                digest.update(chunk)
        Path(tmp_name).replace(dest)
        dest.chmod(0o644)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return digest.hexdigest()
