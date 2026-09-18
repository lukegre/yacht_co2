"""Safe browser downloads for the small, user-facing campaign artifacts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from nicegui import ui

from ..workflow import campaign_status

RENKU_BASE_URL_PATH_ENV = "RENKU_BASE_URL_PATH"

# These are deliberately keys rather than paths supplied by a browser.  The
# values also keep the response metadata next to the allowlist it protects.
ARTIFACTS: Mapping[str, tuple[str, str]] = {
    "site": ("site", "text/html"),
    "track": ("track", "application/x-netcdf"),
    "report": ("report", "application/json"),
}


def is_renku() -> bool:
    """Whether this server is running behind Renku's session proxy."""
    return bool(os.environ.get(RENKU_BASE_URL_PATH_ENV))


def resolve_download(data_root: Path, campaign: str, artifact_key: str) -> tuple[Path, str]:
    """Resolve one allowlisted artifact in an immediate campaign folder.

    Invalid requests, including an artifact which has not been produced yet,
    raise :class:`ValueError`. Resolving both the root and candidate before
    comparing them prevents ``..`` and symlink escapes.
    """
    definition = ARTIFACTS.get(artifact_key)
    if definition is None or not campaign or Path(campaign).name != campaign:
        raise ValueError("unknown campaign artifact")
    root = Path(data_root).expanduser().resolve()
    folder = (root / campaign).resolve()
    if folder.parent != root or not folder.is_dir():
        raise ValueError("unknown campaign artifact")
    field, content_type = definition
    path = getattr(campaign_status(folder), field)
    if path is None or not path.is_file() or path.is_symlink():
        raise ValueError("unknown campaign artifact")
    resolved = path.resolve()
    if not resolved.is_relative_to(folder):
        raise ValueError("unknown campaign artifact")
    return resolved, content_type


def download_url(campaign: str, artifact_key: str) -> str:
    """Return the route for an already-safe campaign folder name and key.

    Renku's reverse proxy only forwards requests below its generated session
    path, so browser links need that same prefix which ``ui.run`` receives.
    """
    base_path = os.environ.get(RENKU_BASE_URL_PATH_ENV, "").rstrip("/")
    return f"{base_path}/artifacts/{quote(campaign, safe='')}/{quote(artifact_key, safe='')}"


def download_button(label: str, campaign: str, artifact_key: str, *, marker: str | None = None) -> None:
    """Draw a link-like button whose response forces a browser download."""
    button = ui.button(
        f"Download {label}", icon="download"
    ).props(f"flat dense type=a href={download_url(campaign, artifact_key)}")
    if marker:
        button.mark(marker)
