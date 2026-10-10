"""Whole-pipeline orchestration: a full run and the incremental monthly update."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from sgheat.export import web
from sgheat.stages import features, grid, model, physics, scenes, static, temporal, validate
from sgheat.stages.context import RunContext

log = logging.getLogger(__name__)


def prepare_static(ctx: RunContext, fetch: bool = True) -> None:
    """Downloads, boundaries, HDB blocks and zone sets."""
    if fetch:
        static.fetch(ctx)
    static.boundaries(ctx)
    static.buildings(ctx)
    grid.build_zones(ctx)


def analyse(ctx: RunContext, physics_scenes: int = 6) -> None:
    """Everything downstream of the per-scene statistics."""
    temporal.run(ctx)
    features.run(ctx)
    model.run(ctx)
    physics.run(ctx, n_scenes=physics_scenes)
    web.run(ctx)
    validate.run(ctx)


def run(ctx: RunContext, fetch: bool = True, workers: int = 4) -> None:
    """Full pipeline from downloads to the validated web bundle."""
    prepare_static(ctx, fetch=fetch)
    scenes.discover(ctx)
    scenes.process(ctx, workers=workers)
    analyse(ctx)


def update(ctx: RunContext, workers: int = 4) -> bool:
    """Incremental run for the scheduled workflow; returns whether new scenes were accepted.

    Expects static inputs, zone sets and the statistics of earlier scenes to be in
    place (restored from the previous data release). Writes ``changed=true|false``
    to ``$GITHUB_OUTPUT`` when running in GitHub Actions.
    """
    before = set(scenes.load_catalog(ctx).query("status == 'accepted'")["item_id"])
    scenes.discover(ctx)
    catalog = scenes.process(ctx, workers=workers)
    after = set(catalog.query("status == 'accepted'")["item_id"])
    new = sorted(after - before)
    bundle_missing = not (ctx.config.paths.web_data_dir / "manifest.json").exists()
    changed = bool(new) or bundle_missing
    if changed:
        analyse(ctx)
    summary = {"new_accepted": new, "n_accepted": len(after), "changed": changed}
    ctx.paths.out.mkdir(parents=True, exist_ok=True)
    (ctx.paths.out / "update.json").write_text(json.dumps(summary, indent=2) + "\n")
    log.info("update: %d new accepted scenes, changed=%s", len(new), changed)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with Path(gh_out).open("a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
            fh.write(f"new_scenes={len(new)}\n")
    return changed
