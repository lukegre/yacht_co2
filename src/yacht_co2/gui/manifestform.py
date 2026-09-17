"""The campaign manifest as a form, over the document it will be saved back to.

Step three of the procedure is "edit the manifest accordingly", which for
someone who does not open YAML files means labelled controls. Every control
writes into the loaded document rather than into a structure of its own, so the
sections this form does not know about -- ``products``, ``atmosphere``,
``site_options`` -- survive a save untouched, along with every comment.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

from nicegui import ui

from ..errors import YachtCO2Error
from ..validation import errors, validate_manifest_document
from .components import findings_panel
from .yamlform import (
    MANIFEST_GROUPS,
    MISSING,
    Field,
    dump_text,
    format_integers,
    load_document,
    parse_document,
    parse_integers,
    plain,
    read_path,
    save_document,
    write_path,
)


def _hint(field: Field) -> str:
    """Render a field's explanation as a Quasar hint attribute."""
    text = field.help or f"manifest key {field.where}"
    return f'hint="{escape(text, quote=True)}"'


class ManifestForm:
    """Edit the values a campaign is tuned by, and the document behind them."""

    def __init__(self, path: Path, *, on_saved: Callable[[], None] | None = None) -> None:
        self.path = Path(path)
        self.on_saved = on_saved
        self.document: Any = {}
        self.controls: dict[tuple[str, ...], Any] = {}

        with ui.column().classes("w-full gap-3"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(str(self.path)).classes("text-xs text-gray-500 break-all")
                with ui.row().classes("gap-2"):
                    ui.button("Reload", icon="refresh", on_click=self.reload).props("flat dense")
                    self.save_button = (
                        ui.button("Save", icon="save", on_click=self.save)
                        .props("unelevated dense")
                        .mark("save-campaign-manifest")
                    )
            with ui.tabs().classes("w-full") as tabs:
                form_tab = ui.tab("Settings")
                text_tab = ui.tab("The file itself")
            with ui.tab_panels(tabs, value=form_tab).classes("w-full"):
                with ui.tab_panel(form_tab):
                    self._build_form()
                with ui.tab_panel(text_tab):
                    ui.label(
                        "Everything in the manifest, including the sections the form above "
                        "does not cover. Edits here are saved with the rest."
                    ).classes("text-sm text-gray-600")
                    self.editor = (
                        ui.codemirror(
                            language="YAML", line_wrapping=True, on_change=self._absorb_text
                        )
                        .classes("h-96 w-full border rounded")
                        .mark("editor-campaign-manifest")
                    )
            self.findings = ui.column().classes("w-full gap-1")
        self.reload()

    def _build_form(self) -> None:
        for heading, fields in MANIFEST_GROUPS:
            with ui.expansion(heading, value=heading in {"Campaign", "Inputs"}).classes(
                "w-full border rounded"
            ):
                with ui.grid(columns=2).classes("w-full gap-3 p-2"):
                    for field in fields:
                        self.controls[field.path] = self._control(field)

    def _control(self, field: Field) -> Any:
        """Build the one control that suits this field's kind.

        Each is marked with the manifest key it edits, which is what validation
        findings name it by and what a test reaches for.
        """
        mark = f"field-{field.where}"
        if field.kind == "switch":
            return ui.switch(field.label).tooltip(field.help or field.where).mark(mark)
        if field.kind == "select":
            return (
                ui.select(list(field.options), label=field.label)
                .props(f"dense outlined {_hint(field)}")
                .classes("w-full")
                .mark(mark)
            )
        if field.kind == "choices":
            return (
                ui.select(list(field.options), label=field.label, multiple=True)
                .props(f"dense outlined use-chips {_hint(field)}")
                .classes("w-full")
                .mark(mark)
            )
        if field.kind == "number":
            return (
                ui.number(label=field.label)
                .props(f"dense outlined {_hint(field)}")
                .classes("w-full")
                .mark(mark)
            )
        if field.kind == "range":
            with ui.column().classes("w-full gap-0"):
                ui.label(field.label).classes("text-xs text-gray-600")
                with ui.row().classes("w-full gap-2 no-wrap"):
                    low = (
                        ui.number(label="lowest")
                        .props("dense outlined")
                        .classes("grow")
                        .mark(f"{mark}-low")
                    )
                    high = (
                        ui.number(label="highest")
                        .props("dense outlined")
                        .classes("grow")
                        .mark(f"{mark}-high")
                    )
                if field.help:
                    ui.label(field.help).classes("text-xs text-gray-500")
            return (low, high)
        # Both plain text and a list of phase codes are typed into a text box;
        # the codes are parsed on the way back into the document.
        return (
            ui.input(label=field.label, placeholder=field.placeholder)
            .props(f"dense outlined {_hint(field)}")
            .classes("w-full")
            .mark(mark)
        )

    def reload(self) -> None:
        """Read the manifest from disk into every control and the text view."""
        self.document = load_document(self.path) if self.path.is_file() else {}
        for field in (field for _, fields in MANIFEST_GROUPS for field in fields):
            self._show(field, read_path(self.document, field.path))
        self.editor.set_value(dump_text(self.document))
        self._check()

    def _show(self, field: Field, value: Any) -> None:
        """Put one document value into its control."""
        control = self.controls[field.path]
        if field.kind == "range":
            low, high = control
            pair = list(value) if isinstance(value, (list, tuple)) else [None, None]
            pair = (pair + [None, None])[:2]
            low.set_value(pair[0])
            high.set_value(pair[1])
        elif field.kind == "switch":
            control.set_value(bool(value))
        elif field.kind == "choices":
            control.set_value([str(item) for item in value] if isinstance(value, list) else [])
        elif field.kind == "number":
            control.set_value(value if isinstance(value, (int, float)) else None)
        elif field.kind == "integers":
            control.set_value(format_integers(value))
        elif field.kind == "select":
            control.set_value(str(value) if value is not None else None)
        else:
            control.set_value("" if value is None else str(value))

    def _collect(self) -> None:
        """Write every control back into the document.

        A control left empty removes its key rather than storing a blank, so
        the manifest keeps saying "use the default" instead of claiming a
        timezone of ``''``.
        """
        for field in (field for _, fields in MANIFEST_GROUPS for field in fields):
            control = self.controls[field.path]
            if field.kind == "range":
                low, high = control
                if low.value is None or high.value is None:
                    write_path(self.document, field.path, MISSING)
                else:
                    write_path(self.document, field.path, [low.value, high.value])
            elif field.kind == "switch":
                write_path(self.document, field.path, bool(control.value))
            elif field.kind == "choices":
                write_path(self.document, field.path, list(control.value or []))
            elif field.kind == "number":
                write_path(
                    self.document,
                    field.path,
                    MISSING if control.value is None else control.value,
                )
            elif field.kind == "integers":
                codes = parse_integers(control.value or "")
                write_path(self.document, field.path, codes if codes else MISSING)
            else:
                text = (control.value or "").strip()
                write_path(self.document, field.path, text or MISSING)

    def _absorb_text(self, _event: Any) -> None:
        """Take the text view as the document when it is edited directly."""
        try:
            self.document = parse_document(self.editor.value)
        except YachtCO2Error:
            # Half-typed YAML is the normal state of a text box; the findings
            # panel says so and saving is blocked until it parses.
            self._report_broken()
            return
        for field in (field for _, fields in MANIFEST_GROUPS for field in fields):
            self._show(field, read_path(self.document, field.path))
        self._check()

    def _report_broken(self) -> None:
        self.findings.clear()
        with self.findings:
            with ui.row().classes("items-center gap-2"):
                ui.icon("error").classes("text-red-600")
                ui.label("The file does not parse as YAML yet.").classes("text-sm text-red-600")
        self.save_button.disable()

    def _check(self) -> list:
        found = validate_manifest_document(plain(self.document), self.path)
        self.findings.clear()
        with self.findings:
            findings_panel(found, clean="This manifest is ready to run.")
        (self.save_button.disable if errors(found) else self.save_button.enable)()
        return found

    def save(self) -> None:
        """Fold the controls into the document and write it back."""
        try:
            self._collect()
        except YachtCO2Error as exc:
            ui.notify(str(exc), type="negative")
            return
        self.editor.set_value(dump_text(self.document))
        if errors(self._check()):
            ui.notify("Fix the errors below before saving.", type="negative")
            return
        save_document(self.document, self.path)
        ui.notify(f"Saved {self.path.name}", type="positive")
        if self.on_saved is not None:
            self.on_saved()
