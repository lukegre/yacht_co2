"""The defaults page: what every campaign inherits, and the Zenodo token.

Three things outlive any one campaign -- who the vessel and its crew are, how
observations are processed by default, and the credential that archives them --
and all three live in the user's own configuration directory rather than in a
checkout. This page is where someone who will never open a YAML file in an
editor changes them anyway.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from nicegui import ui

from ..errors import YachtCO2Error
from ..manifest import packaged_defaults
from ..userconfig import (
    MANIFEST_DEFAULTS_NAME,
    PROJECT_NAME,
    SECRETS_NAME,
    TOKEN_VARIABLES,
    config_dir,
    config_file,
    packaged_project_defaults,
    read_secrets,
    seed_config_dir,
    write_token,
)
from ..validation import validate_manifest_document, validate_project_document
from .components import DocumentEditor

TOKEN_HELP = (
    "Create one at zenodo.org under Applications -> Personal access tokens, "
    "with the deposit:write and deposit:actions scopes."
)


def reveal(path: Path) -> None:
    """Show a path in the desktop's own file manager.

    The server is this machine, so it can do what the browser cannot: put the
    configuration directory in front of someone who would not otherwise know
    where to find it.
    """
    command = {
        "darwin": ["open", str(path)],
        "win32": ["explorer", str(path)],
    }.get(sys.platform, ["xdg-open", str(path)])
    try:
        subprocess.Popen(command)  # noqa: S603 - a fixed command over a local path
    except OSError as exc:
        ui.notify(f"Could not open {path}: {exc}", type="warning")


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


def settings_panels(on_saved=None) -> None:
    """Build the three defaults panels inside the caller's container."""
    created = seed_config_dir()

    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Shared defaults").classes("text-lg font-medium")
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
        project_tab = ui.tab("Vessel and archive")
        manifest_tab = ui.tab("Processing defaults")
        token_tab = ui.tab("Zenodo token")
    with ui.tab_panels(tabs, value=project_tab).classes("w-full"):
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
