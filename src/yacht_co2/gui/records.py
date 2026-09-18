"""Working from a published record rather than from files on this machine.

Everything a campaign is made of ends up on Zenodo: the raw logs it was
measured as, and the dataset, report and page it was processed into. Someone
holding the DOI therefore has enough to look at that campaign, or to process it
again, without ever having had the instrument's files -- which is what this
panel is for. What it brings down lands in an ordinary campaign folder, so the
five steps apply to it afterwards exactly as they do to a folder off the
instrument.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from nicegui import run, ui

from ..errors import YachtCO2Error
from ..manifest import MANIFEST_NAME
from ..record import PublishedRecord, RecordFile, import_record, read_record
from ..workflow import campaign_status
from .artifacts import download_button, use_browser_artifacts
from .components import show_artifact

#: What each kind of file in a record is called on the page.
KIND_LABELS = {
    "site": "interactive page",
    "track": "dataset",
    "report": "run report",
    "video": "video",
    "product": "environmental product",
}

#: The icon each kind is drawn with, matching the ones the steps already use.
KIND_ICONS = {
    "site": "public",
    "track": "dataset",
    "report": "description",
    "video": "movie",
    "product": "layers",
}


class StartStep(Protocol):
    """Hand a slow step to whatever runs them one at a time and shows its log.

    Downloading a record is that kind of step -- minutes of it, narrated into
    the progress log -- so the panel does not run it itself; it asks the page
    that owns the runner, and is called back with what the step returned.
    """

    def __call__(
        self,
        name: str,
        work: Callable[[], Any],
        *,
        then: Callable[[Any], None] | None = None,
    ) -> None: ...


def human_size(size: int) -> str:
    """Say a file's size the way someone deciding whether to wait for it reads it.

    In thousands rather than in units of 1024, because that is what the record
    it came from says, and what the desktop it lands on will say about it.
    """
    value = float(size)
    for unit in ("B", "kB", "MB"):
        if value < 1000:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"


class RecordPanel:
    """Look up a published record and bring the wanted parts of it down."""

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
        self.record: PublishedRecord | None = None
        self.campaign: ui.input | None = None
        self.date: ui.input | None = None
        self.folder: ui.input | None = None
        self.outcome: ui.column | None = None

        with ui.card().classes("w-full h-full").mark("record-panel"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("cloud_download").classes("text-primary")
                ui.label("Open a published record").classes("font-medium")
            with ui.column().classes("w-full gap-3"):
                ui.label(
                    "Import a campaign from Zenodo by entering its DOI or record URL. "
                    "Choose its published products or download its raw logs into a local "
                    "campaign folder."
                ).classes("text-sm text-gray-600")
                with ui.row().classes("w-full items-center gap-2"):
                    self.reference = (
                        ui.input("Zenodo DOI or record URL", placeholder="10.5281/zenodo.12345")
                        .props("dense outlined")
                        .classes("grow")
                        .mark("record-reference")
                    )
                    self.lookup = (
                        ui.button("Look up", icon="search", on_click=self._look_up)
                        .props("unelevated")
                        .mark("record-lookup")
                    )
                self.message = ui.label().classes("text-sm text-gray-600")
                self.details = ui.column().classes("w-full gap-3")

    # -- reading the record ---------------------------------------------

    async def _look_up(self) -> None:
        """Read the record and describe it, without downloading anything yet."""
        reference = (self.reference.value or "").strip()
        self.details.clear()
        self.record = None
        if not reference:
            self._say("Give a DOI or a record URL first.", bad=True)
            return
        self._say("Reading the record...")
        self.lookup.disable()
        try:
            record = await run.io_bound(read_record, reference)
        except YachtCO2Error as exc:
            # A DOI that names nothing, or names something that is not a Zenodo
            # record, is a typo far more often than a fault: it is reported
            # where it was typed rather than as a failed step.
            self._say(str(exc), bad=True)
            return
        finally:
            self.lookup.enable()
        if record is None:
            # The tab was closed while the record was being read, so there is
            # nobody left to describe it to.
            return
        self.record = record
        self._say("")
        self._describe(record)

    def _say(self, message: str, *, bad: bool = False) -> None:
        self.message.set_text(message)
        self.message.classes(replace="text-sm " + ("text-red-600" if bad else "text-gray-600"))

    # -- describing it --------------------------------------------------

    def _describe(self, record: PublishedRecord) -> None:
        with self.details:
            with ui.column().classes("gap-0"):
                ui.label(record.title or f"Record {record.record_id}").classes(
                    "text-sm font-medium"
                )
                origin = " (sandbox)" if record.is_sandbox else ""
                ui.label(f"{record.doi or record.url}{origin}").classes(
                    "text-xs text-gray-500 break-all"
                )
            if not record.files:
                ui.label("This record holds no files.").classes("text-sm text-gray-600")
                return
            self._listing(record)
            self._identity(record)
            self._actions(record)
            self.outcome = ui.column().classes("w-full gap-2")

    def _listing(self, record: PublishedRecord) -> None:
        """Show products and their manifest by name, and count the bulk files."""
        manifests = tuple(file for file in record.files if file.key == MANIFEST_NAME)
        others = tuple(
            file
            for file in record.files
            if not file.is_product and not file.is_log and file.key != MANIFEST_NAME
        )
        with ui.list().props("dense separator").classes("w-full border rounded"):
            for file in record.products:
                self._row(
                    file.key,
                    KIND_LABELS.get(file.kind, file.kind),
                    file.size,
                    KIND_ICONS.get(file.kind, "insert_drive_file"),
                )
            for file in manifests:
                self._row(file.key, "processing manifest", file.size, "tune")
            # The raw logs are the bulk of a record and are never picked over
            # one at a time, so they are counted rather than listed.
            for group, noun, icon in (
                (record.logs, "raw log", "receipt_long"),
                (others, "other file", "insert_drive_file"),
            ):
                if group:
                    plural = "" if len(group) == 1 else "s"
                    self._row(
                        f"{len(group)} {noun}{plural}",
                        "",
                        sum(file.size for file in group),
                        icon,
                    )

    def _row(self, title: str, subtitle: str, size: int, icon: str) -> None:
        with ui.item():
            with ui.item_section().props("avatar"):
                ui.icon(icon).classes("text-gray-500")
            with ui.item_section():
                ui.item_label(title).classes("text-sm break-all")
                if subtitle:
                    ui.item_label(subtitle).classes("text-xs text-gray-500")
            with ui.item_section().props("side"):
                ui.label(human_size(size)).classes("text-xs text-gray-500")

    def _identity(self, record: PublishedRecord) -> None:
        """Ask for the campaign the folder will be named after.

        Every file a campaign folder holds is named from the campaign and its
        date, so a downloaded folder that disagrees with the record would not
        find the very files it just downloaded. Both are read back from the
        record where it says what they are; where it does not, they are asked
        for, because only the person knows.
        """
        ui.label(
            "The campaign and its date name every file in the folder, so they have to "
            "match the ones the record was published under. They are read back from the "
            "record where it says; correct them where it does not."
        ).classes("text-sm text-gray-600")
        with ui.row().classes("w-full gap-2 flex-wrap items-start"):
            self.campaign = (
                ui.input("Campaign name", value=record.campaign, placeholder="Fastnet Race")
                .props("dense outlined")
                .classes("grow")
                .mark("record-campaign")
            )
            self.date = (
                ui.input("Campaign date", value=record.campaign_date, placeholder="2023-07-24")
                .props('dense outlined hint="YYYY-MM-DD, YYYY-MM or YYYY"')
                .classes("grow")
                .mark("record-date")
            )
        self.folder = (
            ui.input("Folder name", value=record.slug)
            .props("dense outlined")
            .classes("w-full")
            .mark("record-folder")
        )
        ui.label(f"It will be created under {self.data_root()}.").classes(
            "text-xs text-gray-500 break-all"
        )

    def _actions(self, record: PublishedRecord) -> None:
        product_files = tuple(
            file for file in record.files if file.is_product or file.key == MANIFEST_NAME
        )
        if not record.products and not record.logs:
            ui.label(
                "This record holds neither this package's products nor raw logs, so "
                "there is nothing here to open."
            ).classes("text-sm text-gray-600")
            return
        with ui.row().classes("gap-2 flex-wrap"):
            if record.products:
                ui.button(
                    f"Download the products ({len(product_files)})",
                    icon="download",
                    on_click=lambda: self._download(product_files, "products"),
                ).props("unelevated").mark("record-download-products")
            if record.logs:
                ui.button(
                    f"Download the raw logs ({len(record.logs)})",
                    icon="download",
                    on_click=lambda: self._download(record.logs, "raw logs"),
                ).props("flat" if record.products else "unelevated").mark("record-download-logs")

    # -- bringing it down -----------------------------------------------

    def _download(self, files: Sequence[RecordFile], what: str) -> None:
        record = self.record
        if record is None or not files:
            return
        campaign = (self.campaign.value or "").strip() if self.campaign else ""
        date = (self.date.value or "").strip() if self.date else ""
        name = (self.folder.value or "").strip() if self.folder else ""
        if not campaign:
            self._say("A campaign name is needed: it names every file in the folder.", bad=True)
            return
        if not name or Path(name).name != name or name.startswith("."):
            self._say("The folder name has to be a plain name, not a path.", bad=True)
            return
        self._say("")
        destination = self.data_root() / name
        keys = [file.key for file in files]
        products = {file.key for file in record.products}
        self.start(
            f"Downloading the {what}",
            lambda: import_record(record, destination, keys, campaign=campaign, campaign_date=date),
            then=lambda paths: self._downloaded(destination, paths, products),
        )

    def _downloaded(self, folder: Path, paths: Any, products: set[str]) -> None:
        """Say where the files landed, and offer to show the ones worth seeing."""
        self.on_imported(folder)
        if self.outcome is None:
            return
        self.outcome.clear()
        downloaded = [Path(path) for path in paths or []]
        with self.outcome, ui.card().classes("w-full bg-green-50 border border-green-200"):
            ui.label(f"Downloaded into {folder}").classes(
                "text-sm font-medium text-green-900 break-all"
            )
            shown = [path for path in downloaded if path.name in products]
            if shown:
                with ui.row().classes("gap-2 flex-wrap"):
                    if use_browser_artifacts():
                        status = campaign_status(folder)
                        for key, label, path in (
                            ("site", "Interactive page", status.site),
                            ("track", "Dataset (NetCDF)", status.track),
                            ("report", "Run report", status.report),
                        ):
                            if path is not None:
                                download_button(label, folder.name, key)
                    else:
                        for path in shown:
                            ui.button(
                                path.name,
                                icon="visibility",
                                on_click=lambda path=path: show_artifact(path),
                            ).props("flat dense").classes("normal-case")
            else:
                ui.label(
                    "The folder is now listed above, ready for the steps to be run over it."
                ).classes("text-sm text-green-900")
