"""Landing-page controls for creating a campaign from local ``.log`` files."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from nicegui import ui

from ..errors import YachtCO2Error
from ..raw_import import RawLog, import_raw_logs, normalise_campaign_id, upload_limits
from ..userconfig import read_settings


class StartStep(Protocol):
    def __call__(self, name: str, work: Callable[[], Any], *, then: Callable[[Any], None] | None = None) -> None: ...


class RawImportPanel:
    """Collect browser files and create a new campaign only when all are valid."""

    def __init__(
        self,
        *,
        data_root: Callable[[], Path],
        start: StartStep,
        on_imported: Callable[[Path], None],
        process_directly: Callable[[Path, str, str], None],
    ) -> None:
        self.data_root = data_root
        self.start = start
        self.on_imported = on_imported
        self.process_directly = process_directly
        self.files: list[RawLog] = []
        self.imported_folder: Path | None = None
        with ui.card().classes("w-full h-full"):
            ui.label("Import raw logs").classes("font-medium")
            ui.label(
                "Drop OceanPack .log files here, name the campaign, and create a new folder. "
                "The uploaded source logs are kept unchanged."
            ).classes("text-sm text-gray-600")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                self.name = ui.input("Campaign name", placeholder="Fastnet Race").props(
                    "dense outlined"
                ).classes("grow").mark("raw-import-name")
                self.date = ui.input("Campaign date", placeholder="2023-07-24").props(
                    "dense outlined hint='YYYY-MM or YYYY-MM-DD'"
                ).classes("grow").mark("raw-import-date")
            self.upload = (
                ui.upload(
                    label="Drop .log files or choose files",
                    multiple=True,
                    auto_upload=True,
                    on_upload=self._received,
                )
                .props("accept=.log")
                .classes("w-full")
                .mark("raw-log-upload")
            )
            self.selected = ui.label("No files selected.").classes("text-xs text-gray-500")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("Import logs", icon="upload_file", on_click=self._import).mark(
                    "raw-import-submit"
                )
                self.direct = ui.button(
                    "Process raw logs directly",
                    icon="play_arrow",
                    on_click=self._process_directly,
                ).props("flat").mark("raw-import-process-direct")
                self.direct.disable()
                ui.button("Clear files", on_click=self._clear).props("flat dense")
            ui.label(f"New campaigns are created under {self.data_root()}.").classes(
                "text-xs text-gray-500 break-all"
            )

    async def _received(self, event: Any) -> None:
        """Keep bytes in memory until the explicit all-or-nothing import action."""
        try:
            content = await event.file.read()
            self.files.append(RawLog(str(event.file.name), content))
            self._selection()
        except Exception as exc:
            ui.notify(f"Could not read uploaded file: {exc}", type="negative")

    def _selection(self) -> None:
        total = sum(len(file.content) for file in self.files)
        self.selected.set_text(f"{len(self.files)} selected file(s), {total:,} bytes.")

    def _clear(self) -> None:
        self.files.clear()
        self.upload.reset()
        self._selection()

    def _import(self) -> None:
        name, date = str(self.name.value or ""), str(self.date.value or "")
        try:
            normalise_campaign_id(name, date)
        except YachtCO2Error as exc:
            ui.notify(str(exc), type="negative")
            return

        def imported(folder: Path) -> None:
            self.imported_folder = folder
            self.direct.enable()
            self._clear()
            self.on_imported(folder)
            ui.notify(f"Imported logs into {folder.name}.", type="positive")

        self.start(
            "Importing raw logs",
            lambda: import_raw_logs(
                self.data_root(), name, date, self.files, limits=upload_limits(read_settings())
            ),
            then=imported,
        )

    def _process_directly(self) -> None:
        folder = self.imported_folder
        if folder is None:
            ui.notify("Import logs first.", type="warning")
            return
        self.process_directly(folder, str(self.name.value or ""), str(self.date.value or ""))
