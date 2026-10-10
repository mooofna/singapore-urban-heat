"""Command line interface: ``sgheat <stage>``."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from sgheat.config import load_config
from sgheat.stages.context import RunContext, setup_logging

app = typer.Typer(
    name="sgheat",
    help="Surface urban heat in Singapore from every clear Landsat 8 and 9 scene since 2013.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
scenes_app = typer.Typer(help="Landsat scene discovery and processing.", no_args_is_help=True)
app.add_typer(scenes_app, name="scenes")

ConfigOpt = Annotated[
    Path | None, typer.Option("--config", "-c", help="TOML config file.", exists=True)
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")]


def _ctx(config: Path | None, verbose: bool, force: bool = False) -> RunContext:
    setup_logging(verbose)
    return RunContext(load_config(config), force=force)


@app.command()
def fetch(
    config: ConfigOpt = None,
    refresh: Annotated[bool, typer.Option(help="Download again even if present.")] = False,
    verbose: VerboseOpt = False,
) -> None:
    """Download data.gov.sg datasets and WorldPop rasters."""
    from sgheat.stages import static  # noqa: PLC0415

    static.fetch(_ctx(config, verbose), refresh=refresh)


@app.command()
def boundaries(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Planning areas, subzones and the land polygon."""
    from sgheat.stages import static  # noqa: PLC0415

    static.boundaries(_ctx(config, verbose))


@app.command()
def buildings(
    config: ConfigOpt = None,
    rebuild_bridge: Annotated[bool, typer.Option(help="Rebuild the street code bridge.")] = False,
    verbose: VerboseOpt = False,
) -> None:
    """Join HDB property records to building footprints."""
    from sgheat.stages import static  # noqa: PLC0415

    static.buildings(_ctx(config, verbose), rebuild_bridge=rebuild_bridge)


@app.command()
def grid(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Hexagon grids, area zone sets and coverage matrices."""
    from sgheat.stages import grid as grid_stage  # noqa: PLC0415

    grid_stage.build_zones(_ctx(config, verbose))


@scenes_app.command("discover")
def scenes_discover(
    config: ConfigOpt = None,
    since: Annotated[
        str | None, typer.Option(help="Only search from this date (YYYY-MM-DD).")
    ] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Find Landsat items on the STAC API and add them to the catalog."""
    from sgheat.stages import scenes  # noqa: PLC0415

    scenes.discover(_ctx(config, verbose), since=date.fromisoformat(since) if since else None)


@scenes_app.command("process")
def scenes_process(
    config: ConfigOpt = None,
    item: Annotated[list[str] | None, typer.Option(help="Process only these item ids.")] = None,
    workers: Annotated[int, typer.Option(help="Scenes processed in parallel.")] = 3,
    limit: Annotated[int | None, typer.Option(help="Process at most this many scenes.")] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Screen pending scenes and compute zone statistics."""
    from sgheat.stages import scenes  # noqa: PLC0415

    scenes.process(_ctx(config, verbose), item_ids=item, workers=workers, limit=limit)


@app.command()
def temporal(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Composites, trends and hot spots from all accepted scenes."""
    from sgheat.stages import temporal as temporal_stage  # noqa: PLC0415

    temporal_stage.run(_ctx(config, verbose))


@app.command()
def features(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Urban form covariates per zone."""
    from sgheat.stages import features as features_stage  # noqa: PLC0415

    features_stage.run(_ctx(config, verbose))


@app.command()
def model(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Fit OLS, spatial lag, spatial error and spatial Durbin models."""
    from sgheat.stages import model as model_stage  # noqa: PLC0415

    model_stage.run(_ctx(config, verbose))


@app.command()
def physics(
    config: ConfigOpt = None,
    scenes: Annotated[int, typer.Option(help="Number of scenes to compare.")] = 6,
    verbose: VerboseOpt = False,
) -> None:
    """Compare textbook LST estimators with the USGS surface temperature product."""
    from sgheat.stages import physics as physics_stage  # noqa: PLC0415

    physics_stage.run(_ctx(config, verbose), n_scenes=scenes)


@app.command()
def export(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Write the static data bundle for the web explorer."""
    from sgheat.export import web  # noqa: PLC0415

    web.run(_ctx(config, verbose))


@app.command()
def validate(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Check the invariants of all artifacts."""
    from sgheat.stages import validate as validate_stage  # noqa: PLC0415

    validate_stage.run(_ctx(config, verbose))


@app.command()
def run(
    config: ConfigOpt = None,
    fetch: Annotated[bool, typer.Option(help="Download static inputs first.")] = True,
    workers: Annotated[int, typer.Option(help="Scenes processed in parallel.")] = 4,
    verbose: VerboseOpt = False,
) -> None:
    """Run the whole pipeline: downloads, scenes, analysis, web bundle, validation."""
    from sgheat.stages import pipeline  # noqa: PLC0415

    pipeline.run(_ctx(config, verbose), fetch=fetch, workers=workers)


@app.command()
def update(
    config: ConfigOpt = None,
    workers: Annotated[int, typer.Option(help="Scenes processed in parallel.")] = 4,
    verbose: VerboseOpt = False,
) -> None:
    """Incremental update: new scenes only, analysis rerun if anything changed."""
    from sgheat.stages import pipeline  # noqa: PLC0415

    pipeline.update(_ctx(config, verbose), workers=workers)


def main() -> None:
    """Entry point of the ``sgheat`` console script."""
    app()


if __name__ == "__main__":
    main()
