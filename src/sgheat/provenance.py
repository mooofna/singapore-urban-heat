"""Provenance sidecars: every artifact records what produced it and from which inputs.

A sidecar ``<artifact>.prov.json`` stores the artifact hash, the stage and its
algorithm version, the config digest, the git commit and the inputs with their
hashes and upstream versions. Stages use :func:`is_fresh` to skip work whose
inputs and settings have not changed.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SIDECAR_SUFFIX = ".prov.json"
_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def package_version() -> str:
    """Installed version of sgheat, or ``0+unknown`` when running from a bare checkout."""
    try:
        return version("sgheat")
    except PackageNotFoundError:
        return "0+unknown"


def git_state(cwd: Path | None = None) -> tuple[str | None, bool]:
    """Current commit SHA and whether the worktree has uncommitted changes."""
    env_sha = os.environ.get("GITHUB_SHA")
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return env_sha, False
    return sha, dirty


class InputRef(BaseModel):
    """One input of an artifact: a local file or a remote resource."""

    model_config = ConfigDict(frozen=True)

    uri: str
    sha256: str | None = None
    retrieved_at: datetime | None = None
    upstream_version: str | None = None


class Provenance(BaseModel):
    """Contents of a provenance sidecar."""

    model_config = ConfigDict(frozen=True)

    artifact: str
    sha256: str
    stage: str
    stage_version: int
    config_digest: str
    inputs: tuple[InputRef, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sgheat_version: str = Field(default_factory=package_version)
    git_sha: str | None = None
    git_dirty: bool = False
    python: str = Field(default_factory=lambda: sys.version.split()[0])
    platform: str = Field(default_factory=platform.platform)
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


def sidecar_path(artifact: Path) -> Path:
    """Path of the sidecar that belongs to ``artifact``."""
    return artifact.with_name(artifact.name + SIDECAR_SUFFIX)


def write_provenance(
    artifact: Path,
    *,
    stage: str,
    stage_version: int,
    config_digest: str,
    inputs: tuple[InputRef, ...] = (),
    extra: dict[str, str | int | float | bool | None] | None = None,
) -> Provenance:
    """Hash ``artifact`` and write its sidecar next to it."""
    sha, dirty = git_state()
    prov = Provenance(
        artifact=artifact.name,
        sha256=sha256_file(artifact),
        stage=stage,
        stage_version=stage_version,
        config_digest=config_digest,
        inputs=inputs,
        git_sha=sha,
        git_dirty=dirty,
        extra=extra or {},
    )
    sidecar_path(artifact).write_text(prov.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return prov


def read_provenance(artifact: Path) -> Provenance | None:
    """Read the sidecar of ``artifact`` if it exists."""
    path = sidecar_path(artifact)
    if not path.exists():
        return None
    return Provenance.model_validate_json(path.read_text(encoding="utf-8"))


def local_input(path: Path, upstream_version: str | None = None) -> InputRef:
    """Describe a local input file by its hash."""
    return InputRef(uri=str(path), sha256=sha256_file(path), upstream_version=upstream_version)


def is_fresh(
    artifact: Path,
    *,
    stage_version: int,
    config_digest: str,
    inputs: tuple[InputRef, ...] = (),
) -> bool:
    """True when ``artifact`` exists, is intact and was built from the same settings and inputs."""
    if not artifact.exists():
        return False
    prov = read_provenance(artifact)
    if prov is None or prov.stage_version != stage_version or prov.config_digest != config_digest:
        return False
    expected = {(i.uri, i.sha256) for i in inputs}
    recorded = {(i.uri, i.sha256) for i in prov.inputs}
    if expected != recorded:
        return False
    return prov.sha256 == sha256_file(artifact)
