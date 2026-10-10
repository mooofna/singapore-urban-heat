"""Shared state of a pipeline run."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.logging import RichHandler

from sgheat.config import Config
from sgheat.paths import DataPaths


def setup_logging(verbose: bool = False) -> None:
    """Rich console logging for the CLI."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )
    for noisy in ("httpx", "httpcore", "rasterio", "urllib3", "pystac_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@dataclass(frozen=True)
class RunContext:
    """Config plus resolved paths, passed to every stage."""

    config: Config
    paths: DataPaths = field(init=False)
    force: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", DataPaths(self.config.paths.data_dir))
