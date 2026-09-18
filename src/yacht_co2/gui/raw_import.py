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
    ) -> None:
        self.data_root = data_root
        self.start = start
        self.on_imported = on_imported
        self.files: list[RawLog] = []
        with ui.card().classes("w-full h-full").mark("raw-import-panel"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("upload_file").classes("text-primary")
                ui.label("Import raw logs").classes("font-medium")
            ui.label(
                "Upload OceanPack .log files, name the campaign, and create a local campaign "
                "folder. The source logs are kept unchanged."
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
                    label="Drop .log files here or choose files",
                    multiple=True,
                    auto_upload=True,
                    on_upload=self._received,
                )
                .props("accept=.log flat bordered hide-upload-btn")
                .classes("w-full rounded")
                .mark("raw-log-upload")
            )
            self.selected = ui.label("No files selected.").classes("text-xs text-gray-500")
            with ui.row().classes("gap-2 flex-wrap"):
                self.submit = ui.button("Import logs", icon="upload_file", on_click=self._import).mark(
                    "raw-import-submit"
                )
                ui.button("Clear files", on_click=self._clear).props("flat dense")
            ui.label(f"New campaigns are created under {self.data_root()}.").classes(
                "text-xs text-gray-500 break-all"
            )
        self.name.on_value_change(lambda _: self._update_submit())
        self.date.on_value_change(lambda _: self._update_submit())
        self._update_submit()

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
        self._update_submit()

    def _update_submit(self) -> None:
        """Keep the import action unavailable until its required inputs are valid."""
        try:
            normalise_campaign_id(str(self.name.value or ""), str(self.date.value or ""))
        except YachtCO2Error:
            ready = False
        else:
            ready = bool(self.files)
        self.submit.enable() if ready else self.submit.disable()

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
