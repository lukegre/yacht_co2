"""Handing a file to the desktop the server is running on.

The pages may be drawn in a native window rather than a browser tab, and a
native window has no tabs, no downloads folder and no ``window.open``: a link
that opens a second tab simply does nothing there. The server, though, is the
same machine as the desktop, so anything the page wants shown can be shown by
asking the desktop directly -- which is what this module is.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nicegui import ui


def open_file(path: Path) -> None:
    """Open a path with whatever the desktop uses for its kind.

    An HTML page lands in the default browser, which is where an interactive
    page belongs however the workbench itself is being drawn.
    """
    command = {
        "darwin": ["open", str(path)],
        "win32": ["explorer", str(path)],
    }.get(sys.platform, ["xdg-open", str(path)])
    _run(command, path)


def reveal(path: Path) -> None:
    """Show a path in the desktop's own file manager.

    For a file this selects it in its folder rather than opening it, which is
    what "where is it?" means for a dataset no browser can display.
    """
    if path.is_file():
        command = {
            "darwin": ["open", "-R", str(path)],
            "win32": ["explorer", f"/select,{path}"],
        }.get(sys.platform, ["xdg-open", str(path.parent)])
    else:
        command = {
            "darwin": ["open", str(path)],
            "win32": ["explorer", str(path)],
        }.get(sys.platform, ["xdg-open", str(path)])
    _run(command, path)


def _run(command: list[str], path: Path) -> None:
    try:
        subprocess.Popen(command)  # noqa: S603 - a fixed command over a local path
    except OSError as exc:
        ui.notify(f"Could not open {path}: {exc}", type="warning")
