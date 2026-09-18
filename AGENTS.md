# Repository Guidelines

## Project Structure & Module Organization

The Python package lives in `src/yacht_co2/`. Core processing is organized by
concern: ingestion (`ingest.py`), scientific transformations (`science.py` and
`qc.py`), orchestration (`pipeline.py`), exports, and the Typer CLI (`cli.py`).
The NiceGUI interface is under `src/yacht_co2/gui/`; packaged YAML defaults are
in `src/yacht_co2/templates/`. Put tests in `tests/`, mirroring package areas;
GUI tests belong in `tests/gui/`. Keep example manifests in `examples/` and
release-building code in `packaging/`.

## Branches
- `main`: for local deployment
- `renkulab`: for deployment on renkulab. Has slightly different features with a Docker default paths set for Renku


## Build, Test, and Development Commands

Use `uv` with Python 3.11 or later:

```bash
uv sync --extra gui                         # install development and GUI dependencies
uv run yacht-co2 validate examples/fastnet.yaml  # validate a campaign manifest
uv run yacht-co2 gui                        # run the local browser UI
uv run ruff check . && uv run mypy          # lint and type-check
uv run pytest --cov=yacht_co2 --cov-branch  # run the test suite with coverage
```

CI uses `uv sync --locked --extra gui` and enforces 85% branch coverage. Build
the desktop app with `uv sync --extra desktop --group build`, then
`uv run python packaging/build.py`; use `packaging/smoke.py` to exercise it.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, type hints for public
interfaces, `snake_case` functions/modules, `PascalCase` classes, and concise
docstrings on public types or non-obvious behavior. Ruff targets Python 3.11,
uses a 100-character line length, and checks error, import, upgrade, and bugbear
rules. Prefer small, focused modules and retain raw observations; represent data
quality through QC flags rather than destructive filtering.

## Testing Guidelines

Write pytest tests named `test_<behavior>` in the matching test module. Use
pytest fixtures and `pytest.approx` for numerical scientific assertions. GUI
tests are async via NiceGUI and require the `gui` extra. Run focused tests with,
for example, `uv run pytest tests/test_science.py` before the full coverage run.

## Commit & Pull Request Guidelines

Recent history favors concise Conventional Commit-style subjects, such as
`feat(gui): add folder action` and `fix(ci): surface curl failures`. Use an
imperative summary; keep unrelated changes separate. PRs should explain the
user-visible or scientific impact, link the relevant issue when available, list
validation commands run, and include screenshots for GUI or generated-site
changes. Never commit Zenodo tokens or local `.env` values.
