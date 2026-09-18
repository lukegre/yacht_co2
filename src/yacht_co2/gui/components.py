"""Pieces the pages share: showing a product, findings, and a validated editor."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from nicegui import ui

from ..errors import YachtCO2Error
from ..validation import Finding, errors
from .artifacts import download_url, preview_url
from .opening import open_file, reveal
from .yamlform import dump_text, load_document, parse_document, plain, save_document

SEVERITY_ICON = {"error": "error", "warning": "warning"}
SEVERITY_CLASS = {"error": "text-red-600", "warning": "text-amber-600"}


def show_artifact(path: Path) -> None:
    """Put one of a campaign's products in front of the person, by its kind.

    The three products are looked at in three different ways. A page is one
    self-contained file and belongs in a browser, however the workbench itself
    is being drawn. A report is JSON, which the desktop would hand to whichever
    editor claims the extension -- or to nothing at all -- so it is read here.
    A dataset is neither: no browser displays it, so showing it means saying
    where it is.
    """
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        open_file(path)
    elif suffix == ".json":
        show_json(path)
    else:
        reveal(path)


def show_json(path: Path) -> None:
    """Read a JSON file in the workbench itself, rather than handing it away."""
    try:
        text = path.read_text()
    except OSError as exc:
        ui.notify(f"Could not read {path}: {exc}", type="warning")
        return
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        ui.label(path.name).classes("font-medium")
        ui.code(text, language="json").classes("w-full max-h-[60vh] overflow-auto text-xs")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Download report", icon="download").props(
                f"flat dense type=a href={download_url(path.parent.name, 'report')}"
            )
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


def show_browser_artifact(campaign: str, artifact_key: str) -> None:
    """Present an artifact through the browser-safe HTTP actions."""
    if artifact_key == "site":
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-7xl"):
            (
                ui.element("iframe")
                .props(f'src="{preview_url(campaign)}"')
                .classes("w-full h-[70vh] border-0")
                .mark("site-preview-frame")
            )
            ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()


def findings_panel(findings: list[Finding], *, clean: str = "No problems found.") -> None:
    """List validation findings worst first, inside the caller's container."""
    if not findings:
        with ui.row().classes("items-center gap-2"):
            ui.icon("check_circle").classes("text-[#4579ae]")
            ui.label(clean).classes("text-sm text-gray-600")
        return
    for finding in sorted(findings, key=lambda item: item.severity != "error"):
        with ui.row().classes("items-start gap-2"):
            ui.icon(SEVERITY_ICON.get(finding.severity, "info")).classes(
                SEVERITY_CLASS.get(finding.severity, "text-gray-600")
            )
            with ui.column().classes("gap-0"):
                ui.label(finding.where).classes("text-sm font-medium")
                ui.label(finding.message).classes("text-xs text-gray-600")


class DocumentEditor:
    """Edit one YAML file as text, refusing to save a document that is broken.

    Editing the text rather than a form is what keeps the templates' comments:
    they are the only explanation a person has of what a phase code or a
    settling time means, and rewriting the file around a form would delete
    them. Validation runs on every keystroke, so the document says what is
    wrong with it while it is being written and not after it is saved.
    """

    def __init__(
        self,
        path: Path,
        validate: Callable[[Any], list[Finding]],
        *,
        marker: str,
        description: str = "",
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.validate = validate
        self.on_saved = on_saved

        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(str(self.path)).classes("text-xs text-gray-500 break-all")
                with ui.row().classes("gap-2"):
                    ui.button("Reload", icon="refresh", on_click=self.reload).props("flat dense")
                    self.save_button = (
                        ui.button("Save", icon="save", on_click=self.save)
                        .props("unelevated dense")
                        .mark(f"save-{marker}")
                    )
            if description:
                ui.label(description).classes("text-sm text-gray-600")
            self.editor = (
                ui.codemirror(
                    language="YAML", line_wrapping=True, on_change=lambda _: self._check()
                )
                .classes("h-96 w-full border rounded")
                .mark(f"editor-{marker}")
            )
            self.findings = ui.column().classes("w-full gap-1")
        self.reload()

    def reload(self) -> None:
        """Read the file back from disk, discarding anything unsaved."""
        if self.path.is_file():
            self.editor.set_value(self.path.read_text(encoding="utf-8"))
        else:
            self.editor.set_value("")
        self._check()

    def _check(self) -> list[Finding]:
        """Validate what is in the editor and show the result."""
        self.findings.clear()
        try:
            document = parse_document(self.editor.value)
        except YachtCO2Error as exc:
            with self.findings:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("error").classes("text-red-600")
                    ui.label(str(exc)).classes("text-sm text-red-600")
            self.save_button.disable()
            return [Finding("error", str(self.path.name), str(exc))]

        found = self.validate(plain(document))
        with self.findings:
            findings_panel(found, clean=f"{self.path.name} is valid.")
        # A warning is a key nothing reads, which is worth saving and fixing
        # later; an error would stop a run, so it stops the save instead.
        (self.save_button.disable if errors(found) else self.save_button.enable)()
        return found

    def save(self) -> None:
        """Write the editor's text back to the file, once it validates."""
        found = self._check()
        if errors(found):
            ui.notify("Fix the errors above before saving.", type="negative")
            return
        try:
            document = parse_document(self.editor.value)
            save_document(document, self.path)
        except YachtCO2Error as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.notify(f"Saved {self.path.name}", type="positive")
        if self.on_saved is not None:
            self.on_saved()

    def restore(self, template: Path) -> None:
        """Replace the editor's text with a template, without saving it."""
        self.editor.set_value(load_template(template))
        self._check()
        ui.notify("Loaded the packaged template; review it, then save.", type="info")


def load_template(path: Path) -> str:
    """Read a packaged template, normalised through the round-tripper."""
    return dump_text(load_document(path))
