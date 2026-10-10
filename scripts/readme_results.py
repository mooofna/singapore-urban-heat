"""Keep the README's numbers tied to committed result files.

``freeze`` copies the headline numbers of a pipeline run into ``results/summary.json``
(committed). ``render`` writes the findings block of README.md from that file, between
the ``results:start`` and ``results:end`` markers. ``check`` fails when the README
block differs from what ``render`` would write, so every number in it is traceable.

    uv run python scripts/readme_results.py freeze --config configs/local.toml
    uv run python scripts/readme_results.py render
    uv run python scripts/readme_results.py check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sgheat.config import load_config
from sgheat.paths import DataPaths

SUMMARY = Path("results/summary.json")
README = Path("README.md")
START, END = "<!-- results:start -->", "<!-- results:end -->"
MINUS = "−"


def signed(x: float, digits: int = 1) -> str:
    """Number with an explicit sign and a true minus."""
    text = f"{abs(x):.{digits}f}"
    return f"+{text}" if x > 0 else (f"{MINUS}{text}" if x < 0 else text)


def freeze(config: Path | None) -> None:
    """Collect the headline numbers of the current run."""
    cfg = load_config(config)
    paths = DataPaths(cfg.paths.data_dir)
    web = json.loads((cfg.paths.web_data_dir / "summary.json").read_text())
    temporal = json.loads((paths.out / "temporal_report.json").read_text())
    primary = web["zones"]["primary"]
    model = json.loads(paths.model(primary).read_text())
    physics = json.loads(paths.physics_report.read_text())
    best = next(m for m in model["models"] if m["kind"] == model["lowest_aic"])
    sd = {v["name"]: v["sd"] for v in model["variables"]}
    impacts = {
        i["name"]: {
            "direct": i["direct"],
            "total": i["total"],
            "direct_se": i["direct_se"],
            "total_se": i["total_se"],
            "sd": sd[i["name"]],
        }
        for i in best["impacts"]
    }
    single = [s["single_channel"]["bias_k"] for s in physics["scenes"]]
    out = {
        **web,
        "island_level_c": temporal[primary]["overall_level_c"],
        "median_clear_observations": temporal[primary]["median_n_obs"],
        "model_detail": {
            "grid": primary,
            "kind": best["kind"],
            "n": model["n"],
            "fit_label": best["fit_label"],
            "fit": best["fit_measure"],
            "residual_moran_i": best["residual_moran"]["i"],
            "residual_moran_p": best["residual_moran"]["p_value"],
            "impacts": impacts,
        },
        "physics_range": {
            "n_scenes": len(single),
            "single_channel_bias_min_k": min(single),
            "single_channel_bias_max_k": max(single),
            "reference_date": physics["scenes"][0]["date_sgt"],
        },
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {SUMMARY}")


def block(s: dict[str, Any]) -> str:
    """Markdown findings block."""
    sc, rh, tr, md, ph = (
        s["scenes"],
        s["relative_heat"],
        s["trends"],
        s["model_detail"],
        s["physics"],
    )
    imp = md["impacts"]
    hot = ", ".join(f"{p['name']} ({signed(p['alpha_k'])} K)" for p in rh["hottest_planning_areas"])
    cool = ", ".join(
        f"{p['name']} ({signed(p['alpha_k'])} K)" for p in rh["coolest_planning_areas"]
    )
    pr = s["physics_range"]
    lines = [
        f"* **{sc['accepted']} usable scenes** out of {sc['discovered']} Landsat 8 and 9 acquisitions "
        f"({sc['first']} to {sc['last']}); a hexagon of the 200 m grid is clear in a median of "
        f"{s['median_clear_observations']:.0f} of them.",
        f"* On a clear late morning the ground averages about **{s['island_level_c']:.1f} °C**. The hottest "
        f"tenth of the island is at least {rh['p90_k']:.1f} K above the island level, the coolest tenth at least "
        f"{abs(rh['p10_k']):.1f} K below it.",
        f"* The greenest tenth of hexagons is {abs(rh['greenest_decile_k']):.1f} K cooler than the island level "
        f"(median), the least green tenth {rh['least_green_decile_k']:.1f} K warmer.",
        f"* Hottest planning areas: {hot}. Coolest: {cool}.",
        f"* {tr['warming_significant']} hexagons warmed and {tr['cooling_significant']} cooled significantly "
        f"relative to the island since 2013 (of {tr['zones_tested']:,} tested, false discovery rate 5%), "
        "for example where Tengah new town replaced forest.",
        f"* In the {md['kind']} on {md['n']:,} hexagons, one standard deviation more NDVI "
        f"({imp['ndvi']['sd']:.2f}) goes with {signed(imp['ndvi']['direct'], 2)} K locally and "
        f"{signed(imp['ndvi']['total'], 2)} K including spillover to neighbours; more HDB floor area per land "
        f"area ({imp['hdb_far']['sd']:.2f} per standard deviation) with {signed(imp['hdb_far']['direct'], 2)} K, "
        f"and denser population ({imp['pop_density']['sd']:.1f} thousand per km²) with "
        f"{signed(imp['pop_density']['direct'], 2)} K. Residual Moran's I is {signed(md['residual_moran_i'], 3)}.",
        f"* Skipping the atmospheric correction, as the original course version did, biases surface temperature by "
        f"{signed(pr['single_channel_bias_max_k'])} to {signed(pr['single_channel_bias_min_k'])} K across "
        f"{pr['n_scenes']} test scenes ({signed(ph['single_channel_bias_k'])} K on {pr['reference_date']}).",
    ]
    return "\n".join(lines)


def rendered_readme() -> str:
    """README text with a freshly rendered findings block."""
    text = README.read_text()
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    summary = json.loads(SUMMARY.read_text())
    return f"{head}{START}\n{block(summary)}\n{END}{tail}"


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["freeze", "render", "check"])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.config)
        return 0
    new = rendered_readme()
    if args.command == "render":
        README.write_text(new)
        print("README findings rendered")
        return 0
    if new != README.read_text():
        print(
            "README findings are out of date; run: uv run python scripts/readme_results.py render"
        )
        return 1
    print("README findings match results/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
