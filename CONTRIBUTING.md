# Contributing

Thanks for your interest. Issues, questions and pull requests are welcome.

## Setup

```bash
uv sync                      # Python 3.12 or newer
uv run pre-commit install    # ruff, mypy, gitleaks and the house style check on every commit
cd web && npm ci             # Node 24 for the website
```

## Checks

```bash
uv run pytest                                  # unit and offline end-to-end tests
uv run pytest -m network -o addopts=""         # contracts with the external APIs
uv run mypy && uv run ruff check src tests scripts
uv run python scripts/build_fixture_bundle.py  # small offline data bundle for the website
cd web && npm run check && npm test && npx playwright test
```

## Conventions

* Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, ...); release-please builds the changelog from them.
* Code is typed (`mypy --strict`) and tested; new statistics come with a test on synthetic data with known parameters.
* Prose uses "to" for ranges and commas for lists; the style check rejects em dashes, en dashes and middle dots.
* Every number in the README comes from `results/summary.json` (`scripts/readme_results.py`).
* Never commit notebooks, PDFs, credentials or downloaded data; the pre-commit hooks block them.
