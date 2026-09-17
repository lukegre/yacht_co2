"""Application, project, and manifest defaults, plus the Zenodo token.

Three things outlive any one campaign -- who the vessel and its crew are, how
observations are processed by default, and the credential that archives them --
and all three live in the user's own configuration directory rather than in a
checkout. This page is where someone who will never open a YAML file in an
editor changes them anyway.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from ..errors import YachtCO2Error
from ..manifest import packaged_defaults
from ..userconfig import (
    MANIFEST_DEFAULTS_NAME,
    PROJECT_NAME,
    SECRETS_NAME,
    SETTINGS_NAME,
    TOKEN_VARIABLES,
    config_dir,
    config_file,
    packaged_project_defaults,
    read_secrets,
    read_settings,
    seed_config_dir,
    write_settings,
    write_token,
)
from ..validation import validate_manifest_document, validate_project_document
from .components import DocumentEditor
from .folders import FolderPicker
from .opening import reveal

TOKEN_HELP = (
    "Create one at zenodo.org under Applications -> Personal access tokens, "
    "with the deposit:write and deposit:actions scopes."
)


class GuiDefaultsPanel:
    """Edit preferences belonging to the interface rather than a campaign."""

    def __init__(
        self,
        data_root: Path,
        on_data_root_changed: Callable[[Path], None] | None = None,
    ) -> None:
        self.data_root = Path(data_root).expanduser()
        self.on_data_root_changed = on_data_root_changed
        self.picker = FolderPicker(
            self.data_root,
            title="Default campaign folder",
        )

        with ui.column().classes("w-full gap-3"):
            ui.label(
                "The workbench opens this folder on each launch and looks for campaign "
                "folders inside it. You can still change it from the main screen."
            ).classes("text-sm text-gray-600")
            ui.label(str(config_file(SETTINGS_NAME))).classes("text-xs text-gray-500 break-all")
            with ui.card().classes("w-full"):
                ui.label("Default campaign folder").classes("font-medium")
                self.folder_label = ui.label(str(self.data_root)).classes(
                    "text-sm text-gray-600 break-all"
                )
                ui.button(
                    "Change folder",
                    icon="folder_open",
                    on_click=self._pick,
                ).props("flat dense").mark("change-gui-data-root")

    def _pick(self) -> None:
        self.picker.open_at(self.data_root, self._save)

    def _save(self, folder: Path) -> None:
        self.data_root = folder
        write_settings({**read_settings(), "data_root": str(folder)})
        self.folder_label.set_text(str(folder))
        if self.on_data_root_changed is not None:
            self.on_data_root_changed(folder)
        ui.notify("Saved GUI defaults.", type="positive")


class TokenPanel:
    """Store one Zenodo token per deployment, out of sight and out of the repo."""

    def __init__(self) -> None:
        with ui.column().classes("w-full gap-3"):
            ui.label(
                "The token is written to a private file beside these defaults, readable "
                "only by you. It is never written into a YAML file, an upload, or a log."
            ).classes("text-sm text-gray-600")
            ui.label(str(config_file(SECRETS_NAME))).classes("text-xs text-gray-500 break-all")
            self.inputs: dict[bool, ui.input] = {}
            self.states: dict[bool, ui.label] = {}
            for sandbox, heading in ((False, "Zenodo"), (True, "Zenodo Sandbox")):
                with ui.card().classes("w-full"):
                    ui.label(heading).classes("font-medium")
                    if sandbox:
                        ui.label(
                            "sandbox.zenodo.org is where the whole procedure is rehearsed; "
                            "its records are deleted periodically."
                        ).classes("text-xs text-gray-600")
                    self.states[sandbox] = ui.label().classes("text-xs")
                    with ui.row().classes("w-full items-center gap-2"):
                        self.inputs[sandbox] = (
                            ui.input(placeholder="paste the token here")
                            .props("type=password dense outlined")
                            .classes("grow")
                        )
                        ui.button(
                            "Save",
                            on_click=lambda sandbox=sandbox: self._save(sandbox),
                        ).props("unelevated dense")
                        ui.button(
                            "Forget",
                            on_click=lambda sandbox=sandbox: self._forget(sandbox),
                        ).props("flat dense")
            ui.label(TOKEN_HELP).classes("text-xs text-gray-500")
        self._refresh()

    def _refresh(self) -> None:
        """Say where each token is coming from, without ever showing it."""
        stored = read_secrets()
        for sandbox, label in self.states.items():
            variable = TOKEN_VARIABLES[sandbox]
            if os.environ.get(variable) and not stored.get(variable):
                label.set_text(f"Set in the environment as {variable}; that one is used.")
                label.classes(replace="text-xs text-gray-600")
            elif stored.get(variable):
                label.set_text("Stored. Paste a new one to replace it.")
                label.classes(replace="text-xs text-green-700")
            else:
                label.set_text("Not set. Archiving needs it.")
                label.classes(replace="text-xs text-amber-700")

    def _save(self, sandbox: bool) -> None:
        token = self.inputs[sandbox].value or ""
        if not token.strip():
            ui.notify("Paste a token first.", type="warning")
            return
        try:
            write_token(token, sandbox=sandbox)
        except YachtCO2Error as exc:
            ui.notify(str(exc), type="negative")
            return
        self.inputs[sandbox].set_value("")
        self._refresh()
        ui.notify("Token stored.", type="positive")

    def _forget(self, sandbox: bool) -> None:
        write_token("", sandbox=sandbox)
        self.inputs[sandbox].set_value("")
        self._refresh()
        ui.notify("Token removed.", type="info")


def settings_panels(
    *,
    data_root: Path | None = None,
    on_data_root_changed: Callable[[Path], None] | None = None,
    on_saved: Callable[[], None] | None = None,
) -> None:
    """Build the user-level settings panels inside the caller's container."""
    created = seed_config_dir()
    configured_root = Path(
        data_root or read_settings().get("data_root") or Path.home()
    ).expanduser()

    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Settings").classes("text-lg font-medium")
            ui.label(str(config_dir())).classes("text-xs text-gray-500 break-all")
        ui.button(
            "Show in file manager", icon="folder_open", on_click=lambda: reveal(config_dir())
        ).props("flat dense")

    if created:
        ui.label(
            "Started you off with a copy of each template: "
            + ", ".join(sorted(created))
            + ". Fill in the values marked with three dots."
        ).classes("text-sm text-blue-700")

    with ui.tabs().classes("w-full") as tabs:
        gui_tab = ui.tab("GUI")
        project_tab = ui.tab("Project")
        manifest_tab = ui.tab("Manifest")
        token_tab = ui.tab("Zenodo")
    with ui.tab_panels(tabs, value=gui_tab).classes("w-full"):
        with ui.tab_panel(gui_tab):
            GuiDefaultsPanel(configured_root, on_data_root_changed)
        with ui.tab_panel(project_tab):
            editor = DocumentEditor(
                config_file(PROJECT_NAME),
                lambda document: validate_project_document(document, source=PROJECT_NAME),
                marker="defaults-project",
                description=(
                    "Who the vessel is and how its records are credited. Every campaign "
                    "inherits this. A project.yaml inside a data repository still wins "
                    "over it, key by key."
                ),
                on_saved=on_saved,
            )
            ui.button(
                "Start again from the template",
                icon="restart_alt",
                on_click=lambda: editor.restore(packaged_project_defaults()),
            ).props("flat dense")
        with ui.tab_panel(manifest_tab):
            template = DocumentEditor(
                config_file(MANIFEST_DEFAULTS_NAME),
                lambda document: validate_manifest_document(document, config_dir()),
                marker="defaults-manifest",
                description=(
                    "The processing settings a new campaign starts from: phase codes, "
                    "QC ranges, which files are written. Changing them here changes "
                    "every manifest built afterwards, never one already written."
                ),
                on_saved=on_saved,
            )
            ui.button(
                "Start again from the template",
                icon="restart_alt",
                on_click=lambda: template.restore(packaged_defaults()),
            ).props("flat dense")
        with ui.tab_panel(token_tab):
            TokenPanel()
