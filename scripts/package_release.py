"""Package the outputs of a pipeline run as data release assets.

Writes, below ``--out``: the per-scene statistics (``scenes.tar.gz``, needed by the
next incremental update), the web bundle (``web-bundle.tar.gz``), the scene catalog,
the analysis reports, ``MANIFEST.json`` with SHA-256 checksums, ``ATTRIBUTION.md``
and the release notes ``NOTES.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from sgheat.config import load_config
from sgheat.paths import DataPaths
from sgheat.provenance import git_state, package_version

REPORTS = (
    "temporal_report.json",
    "model_summary.json",
    "physics_report.json",
    "hdb_join_report.json",
    "update.json",
)
ATTRIBUTION = """# Attribution

Derived data in this release are licensed under CC BY 4.0 (Maurice Heide, singapore-urban-heat).
They are derived from:

* Landsat 8 and 9 Collection 2 Level-2 data courtesy of the U.S. Geological Survey (public domain),
  accessed through the Microsoft Planetary Computer.
* HDB Property Information, HDB Existing Building and URA Master Plan 2019 boundaries from data.gov.sg,
  licensed under the Singapore Open Data Licence version 1.0.
* WorldPop Global 2015 to 2030 constrained population counts, release R2025A
  (WorldPop, University of Southampton), licensed under CC BY 4.0.
"""


def sha256(path: Path) -> str:
    """Hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tar_dir(source: Path, dest: Path, arcname: str) -> None:
    """Gzip-compressed tarball of a directory."""
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(source, arcname=arcname)


def main() -> None:
    """Package the release."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    paths = DataPaths(cfg.paths.data_dir)
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    tar_dir(paths.scenes, out / "scenes.tar.gz", "scenes")
    with tarfile.open(out / "web-bundle.tar.gz", "w:gz") as tar:
        for item in sorted(cfg.paths.web_data_dir.iterdir()):
            tar.add(item, arcname=item.name)
    shutil.copy(paths.catalog, out / "scenes.csv")
    for name in REPORTS:
        if (paths.out / name).exists():
            shutil.copy(paths.out / name, out / name)
    for model in sorted(paths.out.glob("model_r*.json")):
        shutil.copy(model, out / model.name)
    (out / "ATTRIBUTION.md").write_text(ATTRIBUTION)

    summary = json.loads((cfg.paths.web_data_dir / "summary.json").read_text())
    update = (
        json.loads((paths.out / "update.json").read_text())
        if (paths.out / "update.json").exists()
        else {}
    )
    sha, _ = git_state()
    now = datetime.now(UTC)
    scenes = summary["scenes"]
    new = update.get("new_accepted", [])
    notes = [
        f"Data snapshot of {now:%d %B %Y}.",
        "",
        f"* {scenes['accepted']} usable Landsat scenes of {scenes['discovered']} discovered, "
        f"{scenes['first']} to {scenes['last']}.",
        f"* New usable scenes in this update: {len(new)}"
        + (f" ({', '.join(new)})." if 0 < len(new) <= 10 else "."),
        f"* Pipeline version {package_version()}, commit {sha or 'unknown'}.",
        "",
        "`scenes.tar.gz` holds the per-scene zone statistics that the next monthly update builds on; "
        "`web-bundle.tar.gz` is the data of the website. See ATTRIBUTION.md for sources and licences.",
    ]
    (out / "NOTES.md").write_text("\n".join(notes) + "\n")

    manifest = {
        "created_at": now.isoformat(timespec="seconds"),
        "sgheat_version": package_version(),
        "git_sha": sha,
        "files": {
            p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(out.iterdir())
        },
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    total = sum(p.stat().st_size for p in out.iterdir())
    print(f"packaged {len(manifest['files']) + 1} files, {total / 1e6:.1f} MB, in {out}")


if __name__ == "__main__":
    main()
