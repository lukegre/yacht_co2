"""Project-level defaults shared by every expedition in a repository.

A ``project.yaml`` beside ``data/`` carries the facts that belong to the project
rather than to one race, in one annotated block per consumer: ``platform`` for
vessel identity and instrument serials, ``zenodo`` for archival metadata. Files
are merged from the repository root downwards, so a nearer file refines a more
distant one, and a manifest or a folder's own configuration overrides both.

The merge and discovery helpers here are shared with :mod:`yacht_co2.zenodo` so
that both consumers resolve their defaults identically.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger

from .errors import ManifestError, YachtCO2Error

PROJECT_CONFIG_NAME = "project.yaml"
PROJECT_CONFIG_ENV = "YACHT_CO2_PROJECT_CONFIG"


def deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recursively merged copy; lists and scalar values are replaced."""
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def read_yaml(path: Path, *, error: type[YachtCO2Error] = ManifestError) -> dict[str, Any]:
    """Read a YAML mapping, raising ``error`` for the caller's domain.

    An empty file is an empty mapping, so a placeholder committed ahead of its
    content does not break a run.
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise error(f"could not read {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise error(f"{path.name} root must be a mapping: {path}")
    return loaded


def config_directories(start: str | Path | None = None) -> list[Path]:
    """List directories to search, lowest precedence first.

    The walk climbs from ``start`` towards the repository root and is returned
    root-first, so merging in order leaves the nearest file in control. A
    ``.git`` directory ends the climb, keeping the search inside the project.
    """
    start = Path(start or Path.cwd()).resolve()
    if start.is_file():
        start = start.parent
    ancestors = [start]
    for parent in start.parents:
        ancestors.append(parent)
        if (parent / ".git").exists():
            break
    return list(reversed(ancestors))


def _load_environment(directories: list[Path]) -> None:
    """Add ``.env`` values to the environment without overriding real exports."""
    for directory in (*directories, Path.cwd()):
        load_dotenv(directory / ".env", override=False)


def configured_config_path() -> Path | None:
    """Return the project configuration named by ``YACHT_CO2_PROJECT_CONFIG``.

    The variable may be exported or set in a ``.env`` file, and holds the path
    to a project configuration that need not be named ``project.yaml`` or live
    inside the repository. Being explicit, a path that does not exist is an
    error rather than a silent fallback to the search.
    """
    configured = os.environ.get(PROJECT_CONFIG_ENV, "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if not path.is_file():
        raise ManifestError(f"{PROJECT_CONFIG_ENV} does not point at a file: {path}")
    return path.resolve()


def config_paths(start: str | Path | None = None) -> list[Path]:
    """List the project configuration files that apply, lowest precedence first.

    A path set in ``YACHT_CO2_PROJECT_CONFIG`` ranks below the search so that a
    ``project.yaml`` inside the repository still refines it. Without it the
    search alone applies, which finds the one in the repository root.
    """
    directories = config_directories(start)
    _load_environment(directories)
    configured = configured_config_path()
    found = [directory / PROJECT_CONFIG_NAME for directory in directories]
    paths = [*([configured] if configured else []), *found]
    return [path for path in dict.fromkeys(paths) if path.is_file()]


def load_project_config(start: str | Path | None = None) -> dict[str, Any]:
    """Merge every ``project.yaml`` that applies to ``start``.

    Returns an empty mapping when no file exists; project defaults are optional
    and their absence must not stop a run.
    """
    resolved: dict[str, Any] = {}
    for candidate in config_paths(start):
        resolved = deep_merge(resolved, read_yaml(candidate))
        logger.debug("Merged project defaults from {}", candidate)
    return resolved


def block(config: Mapping[str, Any], name: str) -> dict[str, Any]:
    """Return one named block of a project configuration.

    Parameters
    ----------
    config:
        A loaded ``project.yaml``.
    name:
        Block to extract, such as ``platform`` or ``zenodo``.
    """
    value = config.get(name, {})
    if not isinstance(value, Mapping):
        raise ManifestError(f"{name} in {PROJECT_CONFIG_NAME} must be a mapping")
    return dict(value)


def load_platform(start: str | Path | None = None) -> dict[str, Any]:
    """Load the ``platform`` block of the applicable project defaults."""
    return block(load_project_config(start), "platform")
