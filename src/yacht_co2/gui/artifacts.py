"""Safe browser downloads for the small, user-facing campaign artifacts."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from nicegui import ui

from ..workflow import campaign_status

RENKU_BASE_URL_PATH_ENV = "RENKU_BASE_URL_PATH"
DOCKER_ENV = "/.dockerenv"

# These are deliberately keys rather than paths supplied by a browser.  The
# values also keep the response metadata next to the allowlist it protects.
ARTIFACTS: Mapping[str, tuple[str, str]] = {
    "site": ("site", "text/html"),
    "track": ("track", "application/x-netcdf"),
    "report": ("report", "application/json"),
}


def is_docker() -> bool:
    """Return whether the GUI is running in Docker's standard container marker."""
    return Path(DOCKER_ENV).is_file()


def use_browser_artifacts() -> bool:
    """Use HTTP artifact actions wherever there is no desktop to hand a file to.

    Docker's container marker and Renku's reverse-proxy environment variable
    both mean the server and the person looking at the browser are different
    machines, so ``xdg-open`` (or its platform equivalent) would only affect a
    container nobody is looking at. A container can lack a desktop without
    leaving either mark behind, though, so this also checks for the opener
    binary itself rather than trying to name every such environment.
    """
    if is_docker() or os.environ.get(RENKU_BASE_URL_PATH_ENV):
        return True
    opener = {"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open")
    return shutil.which(opener) is None


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


def preview_url(campaign: str) -> str:
    """Return the inline HTML preview route for a campaign's site artifact."""
    base_path = os.environ.get(RENKU_BASE_URL_PATH_ENV, "").rstrip("/")
    return f"{base_path}/artifacts/{quote(campaign, safe='')}/site/view"


def folder_download_url(campaign: str) -> str:
    """Return the browser URL for downloading one campaign folder as a ZIP."""
    base_path = os.environ.get(RENKU_BASE_URL_PATH_ENV, "").rstrip("/")
    return f"{base_path}/campaign-folders/{quote(campaign, safe='')}"


def folder_download_button(campaign: str, *, marker: str | None = None) -> None:
    """Draw a link-like button for a safe campaign-folder ZIP download."""
    button = ui.button("Download folder", icon="download").props(
        f"flat dense type=a href={folder_download_url(campaign)}"
    )
    if marker:
        button.mark(marker)


def download_button(label: str, campaign: str, artifact_key: str, *, marker: str | None = None) -> None:
    """Draw a link-like button whose response forces a browser download."""
    button = ui.button(
        f"Download {label}", icon="download"
    ).props(f"flat dense type=a href={download_url(campaign, artifact_key)}")
    if marker:
        button.mark(marker)
