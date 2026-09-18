"""Per-user defaults, stored outside any repository.

A campaign may be processed by someone who never opens this checkout, so the
defaults they are expected to change cannot live inside it. One directory --
the platform's standard per-user configuration directory holds a copy of each
document a run reads before it reads any data:

``gui.yaml``
    interface preferences, including the folder opened on launch.
``project.yaml``
    vessel, instrument and archival identity, shared by every campaign.
``manifest.yaml``
    the processing template a new campaign's manifest starts from, the same
    document as the packaged ``templates/manifest.yaml``.

The Zenodo token lives here too, in a ``.env`` readable only by its owner,
because both YAML files above are meant to be shared and one of them is
normally committed.

Everything here ranks *below* the repository. A ``project.yaml`` found by the
search in :mod:`yacht_co2.project` still refines it and
``YACHT_CO2_PROJECT_CONFIG`` still outranks it, so writing a user configuration
never changes what an existing checkout already does.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from .errors import YachtCO2Error

CONFIG_DIR_ENV = "YACHT_CO2_CONFIG_DIR"
"""Location of shared, potentially read-only installation defaults."""

USER_CONFIG_DIR_ENV = "YACHT_CO2_USER_CONFIG_DIR"
"""Location for writable per-user settings, credentials, and logs."""

RENKU_SHARED_CONFIG_DIR = Path("/home/renku/.config/yacht_co2")
RENKU_USER_CONFIG_DIR = Path("/home/renku/work/.config/yacht_co2")
SECRETS_DIRECTORY = Path("/secrets")
APP_DIRECTORY = "yacht_co2"
PROJECT_NAME = "project.yaml"
MANIFEST_DEFAULTS_NAME = "manifest.yaml"
SECRETS_NAME = ".env"
SETTINGS_NAME = "gui.yaml"

#: Environment variable holding the token for each Zenodo deployment.
TOKEN_VARIABLES = {
    False: "ZENODO_ACCESS_TOKEN",
    True: "ZENODO_SANDBOX_ACCESS_TOKEN",
}


def resolve_config_dir(
    os_name: str,
    environ: Mapping[str, str],
    home: Path,
    *,
    sys_platform: str | None = None,
) -> Path:
    """Work out where this platform keeps a user's configuration.

    The platform is an argument rather than something read here, because
    ``pathlib`` binds its own flavour to ``os.name``: a test that patched the
    real one would be unable to build a path at all. Windows uses ``%APPDATA%``,
    macOS uses ``~/Library/Application Support``, and Linux follows XDG.

    ``sys_platform`` is explicit for the same reason as ``os_name`` and remains
    optional for callers which only need to exercise the Windows/Linux split.
    """
    override = environ.get(CONFIG_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os_name == "nt":
        base = environ.get("APPDATA", "").strip()
        return (Path(base) if base else home / "AppData" / "Roaming") / APP_DIRECTORY
    if sys_platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIRECTORY
    base = environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(base).expanduser() if base else home / ".config") / APP_DIRECTORY


def shared_config_dir() -> Path:
    """Return installation defaults, which may be a read-only connector.

    ``YACHT_CO2_CONFIG_DIR`` remains the explicit shared-defaults override.
    Renku mounts its published connector at this location.  Callers must never
    create or edit files here; :func:`config_dir` is the writable counterpart.
    """
    return resolve_config_dir(os.name, os.environ, Path.home(), sys_platform=sys.platform)


def config_dir() -> Path:
    """Return the writable per-user configuration directory.

    ``YACHT_CO2_USER_CONFIG_DIR`` separates writable state from shared
    installation defaults.  The historic ``YACHT_CO2_CONFIG_DIR`` continues
    to work as a single-directory override unless the writable variable is
    also supplied.  The Renku image supplies the latter; the fallback protects
    an interactive Renku session whose connector is mounted read-only.
    """
    override = os.environ.get(USER_CONFIG_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get("RENKU_BASE_URL_PATH") and shared_config_dir() == RENKU_SHARED_CONFIG_DIR:
        return RENKU_USER_CONFIG_DIR
    return shared_config_dir()


def config_file(name: str) -> Path:
    """Return the path one of this user's configuration files would have."""
    return config_dir() / name


def existing_config_file(name: str) -> Path | None:
    """Return one of this user's configuration files, or ``None`` if unwritten.

    Absence is the normal state -- the package works without any user
    configuration at all -- so it is reported rather than raised.
    """
    path = config_file(name)
    return path if path.is_file() else None


def user_project_config() -> Path | None:
    """Return this user's ``project.yaml``, if they have written one."""
    return existing_config_file(PROJECT_NAME)


def shared_project_config() -> Path | None:
    """Return the installation's read-only ``project.yaml``, if present."""
    path = shared_config_dir() / PROJECT_NAME
    return path if path.is_file() else None


def user_manifest_defaults() -> Path | None:
    """Return this user's manifest template, if they have written one."""
    return existing_config_file(MANIFEST_DEFAULTS_NAME)


def shared_manifest_defaults() -> Path | None:
    """Return an installation manifest template without ever writing beside it."""
    path = shared_config_dir() / MANIFEST_DEFAULTS_NAME
    return path if path.is_file() else None


def ensure_config_dir() -> Path:
    """Create the configuration directory, readable only by its owner."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        # The token lives here, so the directory is closed even though each
        # secret file is closed in its own right.
        directory.chmod(0o700)
    return directory


def seed_config_dir() -> dict[str, Path]:
    """Write the templates this user has not written themselves.

    Returns the files created, so a first launch can say what it put where.
    An existing file is never touched: these are the documents the user edits,
    and re-seeding one would throw their edits away.
    """
    from .manifest import packaged_defaults  # imported late: manifest reads this module

    directory = ensure_config_dir()
    sources = {
        # A deployment connector is the installation's authoritative starting
        # point.  Copy it into writable state on first launch rather than
        # silently replacing its vessel/processing choices with package
        # examples.  It remains safe when shared and writable directories are
        # the same: an existing destination is skipped below.
        PROJECT_NAME: shared_project_config() or packaged_project_defaults(),
        MANIFEST_DEFAULTS_NAME: shared_manifest_defaults() or packaged_defaults(),
    }
    created: dict[str, Path] = {}
    for name, source in sources.items():
        destination = directory / name
        if destination.exists():
            continue
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        created[name] = destination
        logger.info("Seeded {} from {}", destination, source)
    return created


def packaged_project_defaults() -> Path:
    """Return the annotated ``project.yaml`` that ships inside the package."""
    from importlib import resources

    from .manifest import TEMPLATES_DIRECTORY

    resource = resources.files(__package__).joinpath(TEMPLATES_DIRECTORY, PROJECT_NAME)
    with resources.as_file(resource) as path:
        return path


def read_settings() -> dict[str, Any]:
    """Read the interface's own preferences, such as where the data lives."""
    path = existing_config_file(SETTINGS_NAME)
    if path is None:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Ignoring unreadable {}: {}", path, exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_settings(settings: dict[str, Any]) -> Path:
    """Store the interface's own preferences."""
    ensure_config_dir()
    path = config_file(SETTINGS_NAME)
    path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return path


def _read_env_file(path: Path) -> dict[str, str]:
    """Read simple ``KEY=value`` entries without executing untrusted content."""
    secrets: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Ignoring unreadable secrets file {}: {}", path, exc)
        return {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in TOKEN_VARIABLES.values():
            secrets[key] = value.strip().strip("'\"")
    return secrets


def read_secrets() -> dict[str, str]:
    """Parse this user's ``.env`` into a mapping, ignoring anything malformed."""
    path = existing_config_file(SECRETS_NAME)
    if path is None:
        return {}
    return _read_env_file(path)


def read_renku_secrets(directory: Path = SECRETS_DIRECTORY) -> dict[str, str]:
    """Read approved Zenodo entries from ``/secrets/*.env`` without sourcing.

    A Renku secret is a mounted file, not a shell script.  Only direct files
    with the documented ``.env`` suffix are considered, and only Zenodo token
    keys are returned.  Later filenames do not override an earlier token.
    """
    if not directory.is_dir():
        return {}
    values: dict[str, str] = {}
    try:
        files = sorted(path for path in directory.glob("*.env") if path.is_file())
    except OSError as exc:
        logger.warning("Could not inspect Renku secrets directory {}: {}", directory, exc)
        return {}
    for path in files:
        for key, value in _read_env_file(path).items():
            values.setdefault(key, value)
    return values


def read_token(
    *,
    sandbox: bool = False,
    session_token: str | None = None,
    environment_token: str | None = None,
) -> str:
    """Resolve a Zenodo credential for one deployment.

    Precedence is a token supplied by the current GUI session, an inherited
    environment variable, a mounted Renku ``/secrets/*.env`` file, then this
    user's writable configuration ``.env``.  Mounted files are parsed as data,
    never executed or passed to a shell.
    """
    variable = TOKEN_VARIABLES[bool(sandbox)]
    inherited = os.environ.get(variable) if environment_token is None else environment_token
    return (
        session_token
        or inherited
        or read_renku_secrets().get(variable)
        or read_secrets().get(variable)
        or ""
    ).strip()


def write_token(token: str, *, sandbox: bool = False) -> Path:
    """Store one Zenodo token, readable only by its owner.

    The whole file is rewritten from the values already in it, so storing the
    sandbox token leaves the production one alone. An empty token deletes its
    entry rather than storing a blank that would look like a configured one.
    """
    variable = TOKEN_VARIABLES[bool(sandbox)]
    token = token.strip()
    if any(character in token for character in "\r\n"):
        raise YachtCO2Error("a Zenodo token cannot contain a line break")

    ensure_config_dir()
    secrets = read_secrets()
    if token:
        secrets[variable] = token
    else:
        secrets.pop(variable, None)

    path = config_file(SECRETS_NAME)
    body = "".join(f"{key}={value}\n" for key, value in sorted(secrets.items()))
    path.write_text(
        "# Written by yacht-co2. Keep this file private: it is not configuration,\n"
        "# and nothing here belongs in a repository or a Zenodo record.\n" + body,
        encoding="utf-8",
    )
    if os.name != "nt":
        path.chmod(0o600)
    # The token itself is never logged, here or anywhere else.
    logger.info("Stored the {} token in {}", "sandbox" if sandbox else "Zenodo", path)
    return path
