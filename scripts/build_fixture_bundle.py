"""Run the offline fixture pipeline and copy its web bundle to ``web/static/data``.

Used by CI to test the web app without network access, and locally to develop
the frontend against small data::

    uv run python scripts/build_fixture_bundle.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.fixture_pipeline import prepare, run_all

from sgheat.stages.context import setup_logging

TARGET = Path("web/static/data")


def main() -> None:
    """Build the bundle."""
    setup_logging()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = prepare(Path(tmp))
        run_all(ctx)
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.copytree(ctx.config.paths.web_data_dir, TARGET)
    print(f"fixture bundle written to {TARGET}")


if __name__ == "__main__":
    main()
