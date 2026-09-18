"""The five steps of the quick start, as a page.

Each step is the command the README names, with its arguments read from the
folder instead of typed: archive the raw logs, build a manifest, check it,
process the campaign, publish the products. What a step needs and whether it
has already been done are both read from the folder by
:func:`yacht_co2.workflow.campaign_status`, so the page opens on the first
thing left to do and a campaign can be picked up months later, or on another
machine, without anyone remembering where it got to.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from loguru import logger
from nicegui import app, run, ui
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse

from ..manifest import MANIFEST_NAME, build_manifest
from ..raw_import import ensure_campaign_config
from ..userconfig import read_settings, read_token, write_settings
from ..workflow import CampaignStatus, campaign_status, find_campaigns, run_campaign
from ..zenodo import CONFIG_NAME as ZENODO_CONFIG_NAME
from ..zenodo import upload_raw_folder
from .artifacts import (
    RENKU_BASE_URL_PATH_ENV,
    download_button,
    folder_download_button,
    resolve_download,
    use_browser_artifacts,
)
from .components import show_artifact, show_browser_artifact, show_json
from .folders import FolderPicker
from .jobs import RUNNER
from .manifestform import ManifestForm
from .raw_import import RawImportPanel
from .records import RecordPanel
from .settings import project_settings_findings, settings_panels

#: The kinds of notification the page raises, as Quasar names them.
Notification = Literal["positive", "negative", "warning", "info"]

#: Packaged alongside the module so it ships with the app regardless of cwd.
LOGO_PATH = Path(__file__).parent / "assets" / "yacht_logo.png"

STEPS = (
    "Archive the raw logs",
    "Build the processing manifest",
    "Check the processing settings",
    "Process the campaign",
    "Publish the products",
)


def archive(folder: Path, **options: Any) -> dict[str, Any]:
    """Upload to Zenodo and close the log with what the upload actually did.

    An upload does not fail when it cannot proceed: a record whose review is
    still open has frozen files, so :func:`upload_raw_folder` reports the
    pending review and returns having uploaded nothing. Read from a terminal
    that is plain enough, but a page that then said "finished" would be
    claiming something that did not happen -- so the conclusion is spelled out
    here, while the log is still being captured, and again in
    :func:`upload_outcome` for the notification.
    """
    state = upload_raw_folder(folder, **options)
    status = str(state.get("status") or "")
    record = state.get("record_id") or "this record"
    if status == "pending_review":
        logger.warning(
            "Nothing was uploaded. Zenodo record {} is still waiting for a curator to accept "
            "it, and a record's files are frozen while its review is open.",
            record,
        )
        logger.warning(
            "There is nothing to fix and nothing to retry: come back once the community has "
            "accepted the record, and this step will archive the products as a new version. "
            "The review is linked from {}.",
            state.get("review_url") or "your Zenodo dashboard",
        )
    elif status == "dry-run":
        logger.info(
            "Checked {} file(s) and the record's metadata. Nothing was uploaded, because this "
            "was a check.",
            len(state.get("files") or {}),
        )
    return state


def upload_outcome(result: Any) -> tuple[str, Notification]:
    """Turn an upload's result into the one line the page shows about it."""
    status = str((result or {}).get("status") or "")
    if status == "pending_review":
        return ("Nothing uploaded: the record is still awaiting review.", "warning")
    if status == "dry-run":
        return ("Checked. Nothing was uploaded.", "info")
    return ("Uploaded to Zenodo.", "positive")


def build_local_manifest(folder: Path, campaign: str, campaign_date: str) -> Path:
    """Persist local campaign identity, then build its ordinary manifest."""
    config = folder / ZENODO_CONFIG_NAME
    created = not config.exists()
    config = ensure_campaign_config(folder, campaign, campaign_date)
    try:
        return build_manifest(config)
    except Exception:
        if created:
            config.unlink(missing_ok=True)
        raise


class Workbench:
    """One browser tab, showing one campaign folder at a time."""

    def __init__(self) -> None:
        self.zenodo_tokens: dict[str, str] = {}
        settings = read_settings()
        self.data_root = Path(settings.get("data_root") or Path.home()).expanduser()
        self.folder: Path | None = None
        self.status: CampaignStatus | None = None
        self._shown = 0
        self._sequence = 0
        # Built on first use: it lists a directory to show itself, which is
        # wasted work on a page whose data root is already right.
        self.picker: FolderPicker | None = None

        self._build_header()
        self._project_warning_banner()
        # NiceGUI's content column pads/insets everything below the header by
        # default; strip that so the banner is flush and full-bleed, then
        # restore the same spacing on our own wrapper below.
        ui.query(".nicegui-content").classes("p-0 gap-0")
        with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
            with ui.column().classes("w-full gap-1"):
                ui.label("Add campaign data").classes("text-lg font-medium")
                ui.label(
                    "Upload raw instrument logs or import an existing published record."
                ).classes("text-sm text-gray-600")
            with (
                ui.row()
                .classes("w-full gap-4 items-stretch flex-wrap")
                .mark("landing-upload-row")
            ):
                with ui.column().classes("grow basis-0 min-w-80"):
                    RawImportPanel(
                        data_root=lambda: self.data_root,
                        start=self._start_later,
                        on_imported=self._select,
                    )
                with ui.column().classes("grow basis-0 min-w-80"):
                    RecordPanel(
                        data_root=lambda: self.data_root,
                        start=self._start_later,
                        on_imported=self._select,
                    )
            self._chooser()
            self._steps()
        self._build_log()
        ui.timer(0.3, self._pump)

    # -- chrome ---------------------------------------------------------

    def _build_header(self) -> None:
        # Two columns of equal height (items-stretch overrides NiceGUI's
        # default flex-start, which would otherwise let them size to their
        # own content): a fixed-width logo plate, then everything else.
        # Padding lives on the second column so the first is free for the
        # logo to fill.
        with ui.header().classes("items-stretch p-0 gap-0 shadow-md"):
            with ui.element("div").classes(
                "shrink-0 bg-white flex items-center justify-center"
            ).style("width: 251.07px"):
                ui.image(LOGO_PATH).classes("h-full w-full").props("fit=contain")
            with ui.row().classes("grow items-center px-6 py-3"):
                ui.label("From sailboat CO₂ logs to a citable record").classes(
                    "grow text-left pl-4 opacity-90"
                ).style("font-family: Inter, sans-serif; font-size: 16px; font-weight: 400")
                with ui.row().classes("items-center gap-2"):
                    self._zenodo_status()
                    self._settings_menu()

    def _settings_menu(self) -> None:
        """Show the settings cog. Project problems are announced by the banner."""
        (
            ui.button(icon="settings", color=None, on_click=self._open_settings)
            .props("flat round aria-label='Settings'")
            .classes("text-white")
            .mark("settings-menu")
            .tooltip("Settings")
        )

    @ui.refreshable_method
    def _project_warning_banner(self) -> None:
        """Announce project.yaml problems in one line under the header.

        A banner says what a badge on the cog could not: it is readable without
        hovering, and it cannot sit on top of the cog's click target.
        """
        findings = project_settings_findings()
        if not findings:
            return

        summary = f"{len(findings)} item{'s' if len(findings) > 1 else ''} need attention"
        with (
            ui.row()
            .classes(
                "w-full items-center gap-2 px-6 py-2 cursor-pointer "
                "bg-amber-100 text-amber-900 border-b border-amber-300 "
                "text-sm whitespace-nowrap overflow-hidden"
            )
            .props("role=button tabindex=0 aria-label='project.yaml needs attention'")
            .on("click", self._open_settings)
            .mark("project-settings-warning")
        ):
            ui.icon("warning").classes("text-amber-700 shrink-0")
            ui.label("project.yaml needs attention").classes("font-medium shrink-0")
            ui.label(f"— {summary}").classes("truncate opacity-80")
            ui.label("· fix in Settings → Project").classes("shrink-0 opacity-70")
            self._settings_warning_tooltip(findings)

    @staticmethod
    def _settings_warning_tooltip(findings: list[Any]) -> None:
        """Spell out the problems on hover, so the banner can stay one line high."""
        with (
            ui.tooltip()
            .classes(
                "max-w-md rounded-lg border border-amber-300 bg-slate-900 p-3 text-slate-50 shadow-xl"
            )
            .mark("project-settings-tooltip")
        ):
            with ui.column().classes("gap-2"):
                for finding in findings:
                    with ui.column().classes("gap-0"):
                        ui.label(finding.where).classes("font-mono text-xs text-amber-200")
                        ui.label(finding.message).classes("text-xs text-slate-200")

    @ui.refreshable_method
    def _zenodo_status(self) -> None:
        """Show when this browser session is able to archive to Zenodo."""
        session_token = self.zenodo_tokens.get("ZENODO_ACCESS_TOKEN")
        if read_token(session_token=session_token):
            (
                ui.button("Zenodo ready", icon="cloud_done", color="positive")
                .props("unelevated dense no-caps")
                .mark("zenodo-status")
                .tooltip("A Zenodo token is available for archiving")
            )

    def _open_settings(self) -> None:
        with ui.dialog().props("full-width") as dialog, ui.card().classes("w-full"):
            with ui.column().classes("w-full gap-3"):
                settings_panels(
                    data_root=self.data_root,
                    on_data_root_changed=self._apply_root,
                    on_saved=self.refresh,
                    session_tokens=self.zenodo_tokens,
                )
                ui.button("Close", on_click=dialog.close).props("flat")
        # Opening Settings may have created the editable project.yaml from its
        # deliberately incomplete template, so update the header immediately.
        self._project_warning_banner.refresh()
        dialog.open()

    def _build_log(self) -> None:
        with ui.footer().classes("bg-gray-900 text-gray-100 p-0"):
            with (
                ui.expansion("Progress logs", icon="terminal", value=False)
                .classes("w-full text-gray-100")
                .mark("progress-log")
            ) as self.log_panel:
                self.log = ui.log(max_lines=2000).classes(
                    "w-full h-40 bg-gray-900 text-gray-100 text-xs font-mono"
                ).mark("progress-terminal")

    def _pump(self) -> None:
        """Copy whatever the running step has logged into the page."""
        state = RUNNER.state
        if state.sequence != self._sequence:
            self._sequence = state.sequence
            self._shown = 0
            self.log.clear()
        lines = state.lines
        if len(lines) > self._shown:
            for line in lines[self._shown : len(lines)]:
                self.log.push(line.rstrip())
            self._shown = len(lines)

    # -- choosing a campaign --------------------------------------------

    @ui.refreshable_method
    def _chooser(self) -> None:
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label("Campaign folders").classes("font-medium")
                    ui.label(str(self.data_root)).classes("text-xs text-gray-500 break-all")
                with ui.row().classes("gap-2"):
                    ui.button("Refresh", icon="refresh", on_click=self.refresh).props("flat dense")
                    ui.button("Change folder", icon="folder_open", on_click=self._pick_root).props(
                        "flat dense"
                    )

            found = find_campaigns(self.data_root)
            if not found:
                ui.label(
                    "No campaign folders here yet. A campaign folder is one holding the "
                    "raw .log files straight off the instrument."
                ).classes("text-sm text-gray-600")
                return
            with ui.list().props("separator").classes("w-full"):
                for status in found:
                    self._campaign_row(status)

    def _campaign_row(self, status: CampaignStatus) -> None:
        selected = self.folder == status.folder
        with (
            ui.item(on_click=lambda status=status: self._select(status.folder))
            .classes("rounded " + ("bg-blue-50" if selected else ""))
            .mark(f"campaign-{status.folder.name}")
        ):
            with ui.item_section().props("avatar"):
                ui.icon("check_circle" if status.is_processed else "folder").classes(
                    "text-green-600" if status.is_processed else "text-gray-500"
                )
            with ui.item_section():
                ui.label(status.title).classes("text-sm font-medium")
                ui.label(status.folder.name).classes("text-xs text-gray-500")
            with ui.item_section().props("side"):
                with ui.row().classes("gap-1 flex-wrap items-center justify-end"):
                    for label, done in (
                        (f"{len(status.logs)} logs", status.has_logs),
                        ("archived", status.is_uploaded),
                        ("manifest", status.has_manifest),
                        ("processed", status.is_processed),
                    ):
                        # A filled badge in the default palette pairs a blue
                        # background with the text-color override, which is
                        # too low-contrast to read; outlining it uses the
                        # same colour for text and border on a plain
                        # background instead.
                        ui.badge(
                            label,
                            color="#4579ae" if done else "grey",
                            outline=not done,
                        ).classes("text-xs")
                    (
                        ui.button(icon="folder_open", color=None)
                        .props("flat round dense aria-label='Show folder contents'")
                        .classes("text-gray-500")
                        .mark(f"show-folder-{status.folder.name}")
                        .tooltip("Show folder contents")
                        .on(
                            "click",
                            lambda status=status: self._show_folder_contents(status.folder),
                            js_handler="event => { event.stopPropagation(); emit(); }",
                        )
                    )

    def _show_folder_contents(self, folder: Path) -> None:
        """List one campaign directory without handing it to the host desktop."""
        try:
            entries = sorted(folder.iterdir(), key=lambda path: (path.is_file(), path.name.lower()))
            error = ""
        except OSError as exc:
            entries = []
            error = f"Could not read this folder: {exc}"

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl").mark(
            "campaign-files-dialog"
        ):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label("Folder contents").classes("text-lg font-medium")
                    ui.label(folder.name).classes("text-sm font-medium")
                    ui.label(str(folder)).classes("text-xs text-gray-500 break-all")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round aria-label=Close"
                )
            if error:
                ui.label(error).classes("text-sm text-red-600")
            elif not entries:
                ui.label("This folder is empty.").classes("text-sm text-gray-600")
            else:
                with ui.list().props("dense separator").classes("w-full border rounded"):
                    for entry in entries:
                        with ui.item():
                            with ui.item_section().props("avatar"):
                                ui.icon("folder" if entry.is_dir() else "insert_drive_file").classes(
                                    "text-gray-500"
                                )
                            with ui.item_section():
                                ui.item_label(entry.name).classes("text-sm break-all")
            with ui.row().classes("w-full items-center justify-between"):
                ui.button("Close", on_click=dialog.close).props("flat")
                folder_download_button(folder.name, marker=f"download-folder-{folder.name}")
        dialog.open()

    def _pick_root(self) -> None:
        if self.picker is None:
            self.picker = FolderPicker(self.data_root, title="Where your campaign folders live")
        self.picker.open_at(self.data_root, self._set_root)

    def _set_root(self, folder: Path) -> None:
        write_settings({**read_settings(), "data_root": str(folder)})
        self._apply_root(folder)

    def _apply_root(self, folder: Path) -> None:
        """Use an already-persisted data root in this browser tab."""
        self.data_root = folder
        self.folder = None
        self.refresh()

    def _select(self, folder: Path) -> None:
        self.folder = folder
        self.refresh()

    def refresh(self) -> None:
        """Re-read the selected folder and rebuild everything that describes it."""
        self.status = campaign_status(self.folder) if self.folder else None
        self._zenodo_status.refresh()
        self._project_warning_banner.refresh()
        self._chooser.refresh()
        self._steps.refresh()

    # -- running a step -------------------------------------------------

    async def _start(
        self,
        name: str,
        work: Callable[[], Any],
        *,
        outcome: Callable[[Any], tuple[str, Notification]] | None = None,
        then: Callable[[Any], None] | None = None,
    ) -> None:
        """Run one step on a worker thread, then show what it left behind.

        ``outcome`` reads the step's own result, because a step that finished
        is not the same as a step that did something: an upload into a record
        awaiting review completes perfectly and archives nothing. ``then`` is
        handed that same result once the step has succeeded, for whatever
        started it to show what it now has.
        """
        if RUNNER.busy:
            ui.notify("Another step is still running.", type="warning")
            return
        self.log_panel.set_value(True)
        state = await run.io_bound(RUNNER.execute, name, work)
        self.refresh()
        # A cancelled worker returns nothing, which happens when the tab is
        # closed mid-step; there is then nobody to notify.
        if state is None:
            return
        if state.error:
            ui.notify(f"{name} failed. See the progress log.", type="negative", timeout=8000)
            return
        message, kind = (
            outcome(state.result)
            if outcome is not None
            else (f"{name} finished.", cast(Notification, "positive"))
        )
        ui.notify(message, type=kind, timeout=8000 if kind == "warning" else None)
        if then is not None:
            then(state.result)

    # -- the five steps -------------------------------------------------

    @ui.refreshable_method
    def _steps(self) -> None:
        if self.status is None:
            return
        status = self.status
        first = self._first_unfinished()
        builders = (
            ("archive", self._step_archive),
            ("manifest", self._step_manifest),
            ("settings", self._step_settings),
            ("process", self._step_process),
            ("publish", self._step_publish),
        )
        with ui.stepper(value=STEPS[first]).props("vertical flat header-nav").classes("w-full"):
            for index, (marker, builder) in enumerate(builders):
                with (
                    ui.step(STEPS[index])
                    .props(self._step_status(marker, status))
                    .mark(f"step-{marker}")
                ):
                    builder(status)

    @staticmethod
    def _step_status(marker: str, status: CampaignStatus) -> str:
        """Return the icon state for one step from facts, never its position.

        The open step is merely where the user is looking.  It does not say
        whether any other step was completed; in particular, an archive the
        user deliberately skipped must not acquire a completion tick just
        because a later manifest exists.
        """
        if marker == "archive":
            if status.archive_skipped:
                return "icon=skip_next"
            return "done" if status.is_uploaded else ""
        if marker == "manifest":
            return "done" if status.has_manifest else ""
        if marker in {"settings", "process"}:
            # Processing is the durable evidence that the reviewed settings
            # were used; there is intentionally no separate settings state.
            return "done" if status.is_processed else ""
        return ""

    def _first_unfinished(self) -> int:
        """Open the stepper on the first step this folder has not been through."""
        status = self.status
        assert status is not None
        # A folder downloaded from a published record has the products before
        # it has a manifest, and someone who downloaded them came to look at
        # them: that is the last step's business rather than the second's.
        if status.is_processed:
            return 4
        if status.has_manifest:
            return 2
        if status.is_uploaded:
            return 1
        return 0

    def _step_archive(self, status: CampaignStatus) -> None:
        ui.label(
            "The raw logs are archived first, so what gets published is provably what "
            "was processed. Zenodo reserves a DOI and sends the draft to your community "
            "for review; it becomes public when a curator accepts it."
        ).classes("text-sm text-gray-600")

        if status.is_uploaded:
            self._done(f"Archived as {status.doi}")
            if status.submitted:
                ui.label(f"Submitted for review on {status.submitted}.").classes(
                    "text-sm text-gray-600"
                )
            return

        if not status.has_logs:
            self._blocked("This folder holds no .log files to archive.")
            return

        sandbox = ui.switch("Rehearse on sandbox.zenodo.org").props("dense")
        name = (
            ui.input("Campaign name", value=status.campaign, placeholder="Fastnet Race")
            .props("dense outlined")
            .classes("w-full max-w-md")
        )
        date = (
            ui.input("Campaign date", value=status.campaign_date, placeholder="2023-07-24")
            .props('dense outlined hint="YYYY-MM-DD, YYYY-MM or YYYY"')
            .classes("w-full max-w-md")
        )
        ui.label(f"{len(status.logs)} log files will be uploaded.").classes("text-sm text-gray-600")
        token_note = ui.label().classes("text-sm")

        def upload(dry_run: bool) -> None:
            variable = "ZENODO_SANDBOX_ACCESS_TOKEN" if sandbox.value else "ZENODO_ACCESS_TOKEN"
            session_token = self.zenodo_tokens.get(variable)
            if not read_token(sandbox=bool(sandbox.value), session_token=session_token) and not dry_run:
                token_note.set_text(
                    "Zenodo uploads are unavailable. Add a Renku secret or paste a token under Settings."
                )
                token_note.classes(replace="text-sm text-red-600")
                return
            if not (name.value or "").strip() or not (date.value or "").strip():
                token_note.set_text("A campaign name and date are needed to name the record.")
                token_note.classes(replace="text-sm text-red-600")
                return
            folder = status.folder
            self._start_later(
                "Archiving the raw logs",
                lambda: archive(
                    folder,
                    campaign=name.value.strip(),
                    campaign_date=date.value.strip(),
                    publish=not dry_run,
                    dry_run=dry_run,
                    sandbox=bool(sandbox.value),
                    token=session_token,
                ),
                outcome=upload_outcome,
            )

        with ui.row().classes("gap-2"):
            ui.button("Check without uploading", on_click=lambda: upload(True)).props("flat")
            ui.button("Archive on Zenodo", icon="cloud_upload", on_click=lambda: upload(False))

            def skip_archive() -> None:
                campaign = str(name.value or "").strip()
                campaign_date = str(date.value or "").strip()
                if not campaign or not campaign_date:
                    token_note.set_text(
                        "A campaign name and date are needed to build the local manifest."
                    )
                    token_note.classes(replace="text-sm text-red-600")
                    return
                self._start_later(
                    "Building a local manifest",
                    lambda: build_local_manifest(status.folder, campaign, campaign_date),
                )

            ui.button(
                "Skip archiving",
                icon="skip_next",
                on_click=skip_archive,
            ).props("flat").mark("skip-archive")

    def _step_manifest(self, status: CampaignStatus) -> None:
        ui.label(
            "The manifest says how this campaign is processed. It starts from your "
            "processing defaults and takes the campaign's name and date from its import "
            "details. If the raw logs were archived, it also names their Zenodo record."
        ).classes("text-sm text-gray-600")

        if status.has_manifest:
            self._done(f"{MANIFEST_NAME} is written.")
            return
        if status.zenodo_config is None:
            self._blocked(f"Archive the folder first; it has no {ZENODO_CONFIG_NAME}.")
            return
        config = status.zenodo_config
        ui.button(
            "Build the manifest",
            icon="description",
            on_click=lambda: self._start("Building the manifest", lambda: build_manifest(config)),
        )

    def _step_settings(self, status: CampaignStatus) -> None:
        ui.label(
            "Check these before processing. They are the choices that decide what the "
            "numbers mean: which phases are seawater, what counts as a plausible value, "
            "and which files are written."
        ).classes("text-sm text-gray-600")
        if status.manifest is None:
            self._blocked("Build the manifest first.")
            return
        ManifestForm(status.manifest, on_saved=self.refresh)

    def _step_process(self, status: CampaignStatus) -> None:
        ui.label(
            "Reads the logs back from the archived record, applies quality control, "
            "calibrates and converts to fCO2, then writes the dataset, the run report "
            "and the interactive page. Nothing already built is rebuilt."
        ).classes("text-sm text-gray-600")

        if status.manifest is None:
            self._blocked("Build the manifest first.")
            return
        if status.manifest_error:
            self._blocked(status.manifest_error)
            return

        self._artifacts(status)
        manifest = status.manifest
        ui.button(
            "Process the campaign" if not status.is_processed else "Process again",
            icon="play_arrow",
            on_click=lambda: self._start("Processing the campaign", lambda: run_campaign(manifest)),
        )

    def _step_publish(self, status: CampaignStatus) -> None:
        if not status.is_processed:
            ui.label(
                "Adds the processed dataset, report and page to the record as a new version. "
                "The previous version's files are imported, so nothing is uploaded twice."
            ).classes("text-sm text-gray-600")
            self._blocked("Process the campaign first.")
            return
        if status.zenodo_config is None:
            ui.label(
                "Adds the processed dataset, report and page to the record as a new version. "
                "The previous version's files are imported, so nothing is uploaded twice."
            ).classes("text-sm text-gray-600")
            self._blocked(f"This folder has no {ZENODO_CONFIG_NAME}.")
            return

        self._artifacts(status)

        if status.is_uploaded and status.review_is_pending:
            # A record's files are frozen while its review is open, so this
            # step would complete without archiving anything. Better to say so
            # than to let it look as though it worked.
            self._waiting(
                "Waiting for a curator to accept the raw data.",
                "A Zenodo record's files are frozen while its review is open, so the products "
                "cannot be added to it yet. Nothing is wrong and nothing needs retrying: come "
                "back once the community has accepted the record, and this step will archive "
                "them as a new version.",
            )
            return

        folder, config = status.folder, status.zenodo_config
        products = tuple(
            path for path in (status.track, status.report, status.site) if path is not None
        )

        if not status.is_uploaded:
            ui.label(
                "The raw logs have not been archived. You can publish just the processed "
                "dataset, report and page as their own Zenodo record."
            ).classes("text-sm text-gray-600")

            def publish_products(dry_run: bool) -> None:
                self._start_later(
                    "Publishing the processed data",
                    lambda: archive(
                        folder,
                        config=config,
                        files=products,
                        publish=True,
                        new_version=False,
                        dry_run=dry_run,
                    ),
                    outcome=upload_outcome,
                )

            with ui.row().classes("gap-2"):
                ui.button("Check processed data", on_click=lambda: publish_products(True)).props("flat")
                ui.button(
                    "Publish processed data", icon="cloud_upload", on_click=lambda: publish_products(False)
                )
            return

        ui.label(
            "Adds the processed dataset, report and page to the record as a new version. "
            "The previous version's files are imported, so nothing is uploaded twice."
        ).classes("text-sm text-gray-600")

        def publish(dry_run: bool) -> None:
            self._start_later(
                "Publishing the products",
                lambda: archive(
                    folder,
                    config=config,
                    publish=True,
                    new_version=True,
                    dry_run=dry_run,
                ),
                outcome=upload_outcome,
            )

        with ui.row().classes("gap-2"):
            ui.button("Check without uploading", on_click=lambda: publish(True)).props("flat")
            ui.button("Publish a new version", icon="cloud_upload", on_click=lambda: publish(False))

    # -- shared step furniture ------------------------------------------

    def _start_later(
        self,
        name: str,
        work: Callable[[], Any],
        *,
        outcome: Callable[[Any], tuple[str, Notification]] | None = None,
        then: Callable[[Any], None] | None = None,
    ) -> None:
        """Start a step from a synchronous handler."""
        ui.timer(0, lambda: self._start(name, work, outcome=outcome, then=then), once=True)

    def _done(self, message: str) -> None:
        with ui.row().classes("items-center gap-2"):
            ui.icon("check_circle").classes("text-[#4579ae]")
            ui.label(message).classes("text-sm")

    def _blocked(self, message: str) -> None:
        with ui.row().classes("items-center gap-2"):
            ui.icon("info").classes("text-gray-500")
            ui.label(message).classes("text-sm text-gray-600")

    def _waiting(self, headline: str, detail: str) -> None:
        """Say that a step is waiting on someone else, and that that is fine."""
        with ui.card().classes("w-full bg-amber-50 border border-amber-200"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("hourglass_top").classes("text-amber-700")
                ui.label(headline).classes("text-sm font-medium text-amber-900")
            ui.label(detail).classes("text-sm text-amber-900")

    def _artifacts(self, status: CampaignStatus) -> None:
        """Show whatever this campaign has already produced.

        Docker has no host desktop, so it previews and downloads through safe
        browser routes. A non-container installation can hand files to its
        own browser or file manager, including from the packaged native UI.
        """
        built = [
            ("site", "Interactive page", status.site, "public"),
            ("track", "Dataset (NetCDF)", status.track, "dataset"),
            ("report", "Run report", status.report, "description"),
        ]
        built = [entry for entry in built if entry[2] is not None]
        if not built:
            return
        with ui.row().classes("gap-2 flex-wrap"):
            for key, label, path, icon in built:
                assert path is not None
                if use_browser_artifacts():
                    if key == "site":
                        ui.button(
                            label,
                            icon=icon,
                            on_click=lambda campaign=status.folder.name: show_browser_artifact(
                                campaign, "site"
                            ),
                        ).props("flat dense").mark(f"download-{key}")
                    elif key == "report":
                        ui.button(label, icon=icon, on_click=lambda path=path: show_json(path)).props(
                            "flat dense"
                        ).mark(f"download-{key}")
                    else:
                        download_button(label, status.folder.name, key, marker=f"download-{key}")
                else:
                    ui.button(
                        label,
                        icon=icon,
                        on_click=lambda path=path: show_artifact(path),
                    ).props("flat dense")


def workbench() -> None:
    """The one page: choose a campaign folder, then work down the steps."""
    # Quasar's default primary (#5898d4) recolors every element that reads
    # --q-primary -- the header, "primary"-colored buttons, text-primary
    # icons -- in one call. Per-page rather than app.colors() because this
    # is the app's only page and the simulated browser resets the app.
    ui.colors(primary="rgb(0, 110, 88)")
    Workbench()


def register_pages() -> None:
    """Attach this interface's routes to the NiceGUI application.

    Registering explicitly rather than on import means the routes can be
    attached again after the application is reset, which is what the simulated
    browser does between tests. Call it once per application.
    """
    ui.page("/")(workbench)


#: The window the packaged application opens at, wide enough for the two
#: columns the workbench lays its steps out in.
WINDOW_SIZE = (1180, 860)

@app.get("/artifacts/{campaign}/{artifact_key}")
def artifact_download(campaign: str, artifact_key: str) -> FileResponse:
    """Download one public campaign artifact, never an arbitrary server file."""
    settings = read_settings()
    data_root = Path(settings.get("data_root") or Path.home())
    try:
        path, content_type = resolve_download(data_root, campaign, artifact_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Campaign artifact not found") from exc
    return FileResponse(path, media_type=content_type, filename=path.name)


@app.get("/artifacts/{campaign}/{artifact_key}/view")
def artifact_view(campaign: str, artifact_key: str) -> FileResponse:
    """Serve the allowlisted site artifact inline for browser previews."""
    if artifact_key != "site":
        raise HTTPException(status_code=404, detail="Campaign artifact not found")
    settings = read_settings()
    data_root = Path(settings.get("data_root") or Path.home())
    try:
        path, content_type = resolve_download(data_root, campaign, artifact_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Campaign artifact not found") from exc
    return FileResponse(path, media_type=content_type, content_disposition_type="inline")


def _folder_zip(data_root: Path, campaign: str) -> Path:
    """Create a ZIP of a campaign folder, excluding symlinks and escapes."""
    if not campaign or Path(campaign).name != campaign:
        raise ValueError("unknown campaign folder")
    root = data_root.expanduser().resolve()
    candidate = root / campaign
    if candidate.is_symlink():
        raise ValueError("unknown campaign folder")
    folder = candidate.resolve()
    if folder.parent != root or not folder.is_dir():
        raise ValueError("unknown campaign folder")
    temporary = tempfile.NamedTemporaryFile(prefix="yacht-co2-", suffix=".zip", delete=False)
    temporary_path = Path(temporary.name)
    try:
        with temporary, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(folder):
                    continue
                archive.write(resolved, resolved.relative_to(folder).as_posix())
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


@app.get("/campaign-folders/{campaign}")
def campaign_folder_download(campaign: str) -> FileResponse:
    """Download a campaign folder without exposing arbitrary filesystem paths."""
    settings = read_settings()
    data_root = Path(settings.get("data_root") or Path.home())
    try:
        path = _folder_zip(data_root, campaign)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=404, detail="Campaign folder not found") from exc
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{campaign}.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


def launch(
    *,
    data_root: Path | None = None,
    host: str = "127.0.0.1",
    port: int | None = 8080,
    root_path: str | None = None,
    show: bool = True,
    reload: bool = False,
    native: bool = False,
) -> None:
    """Serve the interface on this machine and, unless told not to, open it.

    ``native`` draws the pages in a window of their own rather than in a
    browser tab, which is what the packaged application does: the server is the
    same, and still listens on this machine alone, but the person running it
    never sees a URL. It needs ``pywebview``; without it NiceGUI exits, so the
    caller is expected to have checked -- :func:`yacht_co2.desktop.can_open_a_window`
    is that check.

    ``port`` of ``None`` lets NiceGUI find a free one, which is what a
    double-clicked application wants: it has no way to report that 8080 was
    taken, and nothing needs to know the number.

    ``root_path`` defaults to Renku's generated session path when the
    ``RENKU_BASE_URL_PATH`` environment variable is present. This keeps static
    assets and websocket connections behind Renku's reverse proxy.
    """
    if data_root is not None:
        write_settings({**read_settings(), "data_root": str(Path(data_root).resolve())})
    register_pages()
    effective_root_path = (
        root_path if root_path is not None else os.environ.get(RENKU_BASE_URL_PATH_ENV, "")
    )
    # ui.run blocks until the server stops, so opening the browser is left to
    # it rather than done afterwards, when nobody would be there to see it.
    ui.run(
        host=host,
        port=port,
        root_path=effective_root_path,
        title="yacht-co2",
        favicon="⛵",
        # A native window is the showing, so asking for a browser too would
        # open the same page twice.
        show=show and not native,
        native=native,
        window_size=WINDOW_SIZE if native else None,
        reload=reload,
        uvicorn_logging_level="warning",
        show_welcome_message=False,
    )
