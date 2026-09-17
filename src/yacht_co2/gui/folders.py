"""Choosing a directory on this machine.

A browser cannot give a server a real path: a file input hands over content and
a name, never a location, and the pipeline needs the location -- it reads a
whole folder of logs and writes its products back beside them. The server
therefore lists its own filesystem and the page picks from that, which works
because the server is this machine.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nicegui import ui


def subdirectories(folder: Path) -> list[Path]:
    """List the directories inside ``folder``, hidden ones left out.

    An unreadable folder lists as empty rather than raising: it is somewhere
    the person cannot go, which the empty listing already says.
    """
    try:
        found = [path for path in folder.iterdir() if path.is_dir()]
    except OSError:
        return []
    return sorted(
        (path for path in found if not path.name.startswith(".")),
        key=lambda path: path.name.lower(),
    )


class FolderPicker(ui.dialog):
    """Walk the filesystem and return one directory."""

    def __init__(self, start: Path, *, title: str = "Choose a folder") -> None:
        super().__init__()
        self.current = Path(start).expanduser().resolve()
        if not self.current.is_dir():
            self.current = Path.home()
        self._on_choose: Callable[[Path], None] | None = None

        with self, ui.card().classes("w-[36rem] max-w-full"):
            ui.label(title).classes("text-lg font-medium")
            self.breadcrumb = ui.label().classes("text-xs text-gray-500 break-all")
            with ui.scroll_area().classes("h-80 w-full border rounded"):
                self.listing = ui.list().props("dense").classes("w-full")
            with ui.row().classes("w-full justify-end items-center"):
                ui.button("Cancel", on_click=self.close).props("flat")
                ui.button("Use this folder", on_click=self._choose).props("unelevated")
        self._refresh()

    def open_at(self, folder: Path, on_choose: Callable[[Path], None]) -> None:
        """Show the picker at ``folder`` and call ``on_choose`` with the answer."""
        self._on_choose = on_choose
        candidate = Path(folder).expanduser()
        self.current = candidate.resolve() if candidate.is_dir() else Path.home()
        self._refresh()
        self.open()

    def _navigate(self, folder: Path) -> None:
        self.current = folder
        self._refresh()

    def _choose(self) -> None:
        self.close()
        if self._on_choose is not None:
            self._on_choose(self.current)

    def _refresh(self) -> None:
        self.breadcrumb.set_text(str(self.current))
        self.listing.clear()
        with self.listing:
            if self.current.parent != self.current:
                self._row("arrow_upward", "..", self.current.parent)
            children = subdirectories(self.current)
            if not children:
                ui.item_label("No folders here.").classes("text-sm text-gray-500 p-2")
            for child in children:
                self._row("folder", child.name, child)

    def _row(self, icon: str, label: str, destination: Path) -> None:
        """One directory, as a list item so that it is clickable in its own right."""
        with ui.item(on_click=lambda destination=destination: self._navigate(destination)).mark(
            f"folder-{label}"
        ):
            with ui.item_section().props("avatar"):
                ui.icon(icon).classes("text-gray-500")
            with ui.item_section():
                ui.item_label(label).classes("text-sm")
