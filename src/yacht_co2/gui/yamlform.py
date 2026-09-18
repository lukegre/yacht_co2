"""Editing a commented YAML document through a form, without losing the comments.

The templates this package ships are mostly comments, and for someone who has
never opened the documentation those comments *are* the documentation: they say
what a phase code is and why the LI-850 cell temperature is not the water
temperature. Saving with ``yaml.safe_dump`` would delete every one of them the
first time a form was used, so the documents are round-tripped through
``ruamel.yaml``, which keeps comments, key order and quoting as written.

:data:`MANIFEST_FIELDS` names the values worth a labelled control. Everything
else in the document is still editable as text, and is preserved untouched by
the form either way -- a form that only knows fifteen keys must not be able to
drop the sixteenth.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ..errors import ManifestError

MISSING = object()


def round_trip() -> YAML:
    """Return a YAML handler configured to preserve a document as written."""
    handler = YAML()
    handler.preserve_quotes = True
    # The templates indent lists under their key; matching that keeps a saved
    # document diff-clean against the one that shipped.
    handler.indent(mapping=2, sequence=4, offset=2)
    handler.width = 100
    return handler


def load_document(path: str | Path) -> Any:
    """Read a YAML document, keeping its comments and layout."""
    path = Path(path)
    try:
        loaded = round_trip().load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise ManifestError(f"could not read {path}: {exc}") from exc
    return loaded if loaded is not None else {}


def parse_document(text: str) -> Any:
    """Parse YAML typed into the interface, reporting what is wrong with it."""
    try:
        loaded = round_trip().load(text)
    except YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ManifestError("the document must be a mapping of sections")
    return loaded


def dump_text(document: Any) -> str:
    """Render a document back to YAML text."""
    stream = io.StringIO()
    round_trip().dump(document, stream)
    return stream.getvalue()


def save_document(document: Any, path: str | Path) -> Path:
    """Write a document back over itself, comments and all."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_text(document), encoding="utf-8")
    return path


def plain(value: Any) -> Any:
    """Return a round-tripped value as ordinary Python, for validation."""
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def read_path(document: Any, path: tuple[str, ...], default: Any = None) -> Any:
    """Read a nested value, returning ``default`` where the path stops."""
    current: Any = document
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def write_path(document: Any, path: tuple[str, ...], value: Any) -> None:
    """Write a nested value, creating the maps along the way.

    Writing :data:`MISSING` removes the key instead, which is how a control
    left blank says "leave this to the default" rather than "set this to
    nothing" -- an empty string in ``inputs.timezone`` is not a timezone.
    """
    current: Any = document
    for key in path[:-1]:
        existing = current.get(key)
        if not isinstance(existing, dict):
            current[key] = {}
        current = current[key]
    if value is MISSING:
        current.pop(path[-1], None)
    else:
        current[path[-1]] = value


@dataclass(frozen=True)
class Field:
    """One labelled control over one place in a YAML document."""

    path: tuple[str, ...]
    label: str
    kind: str = "text"
    help: str = ""
    options: tuple[Any, ...] = ()
    #: Shown when the document leaves the key out, so a control is never blank
    #: for a value the pipeline is in fact using.
    placeholder: str = ""

    @property
    def where(self) -> str:
        """The dotted location, as validation findings name it."""
        return ".".join(self.path)


#: The manifest values a person tunes per campaign, grouped as the page shows
#: them. Everything else stays reachable through the document's own text.
MANIFEST_GROUPS: tuple[tuple[str, tuple[Field, ...]], ...] = (
    (
        "Campaign",
        (
            Field(("campaign", "name"), "Name", help="Titles the page and names every file."),
            Field(("campaign", "date"), "Date", help="YYYY-MM-DD, YYYY-MM or YYYY."),
            Field(("campaign", "id"), "Identifier", help="Joins the record, folder and manifest."),
        ),
    ),
    (
        "Inputs",
        (
            Field(("inputs", "repository"), "Zenodo record", help="DOI the logs are read from."),
            Field(("inputs", "logs"), "Log files", placeholder="./*.log"),
            Field(("inputs", "timezone"), "Log timezone", placeholder="UTC"),
        ),
    ),
    (
        "Calibration",
        (
            Field(
                ("calibration", "method"),
                "Method",
                "select",
                "instrument trusts the logger; linear rescales against the standards.",
                ("instrument", "linear"),
            ),
            Field(("calibration", "input"), "Measured CO2 column", placeholder="co2"),
        ),
    ),
    (
        "Equilibrator",
        (
            Field(("equilibrator", "h2o"), "Water vapour column", placeholder="h2o"),
            Field(("equilibrator", "pressure"), "Pressure column", placeholder="cellpress"),
            Field(
                ("equilibrator", "water_temperature"),
                "Equilibrator water",
                help="Water at the membrane -- never the LI-850 cell temperature.",
                placeholder="watertemp",
            ),
            Field(("equilibrator", "sea_temperature"), "Sea temperature", placeholder="watertemp"),
        ),
    ),
    (
        "Quality control",
        (
            Field(("qc", "minimum_water_flow"), "Minimum water flow", "number"),
            Field(("qc", "minimum_gas_flow"), "Minimum gas flow", "number"),
            Field(("qc", "ranges", "co2"), "Plausible CO2", "range", "umol/mol"),
            Field(("qc", "ranges", "watertemp"), "Plausible temperature", "range", "degrees C"),
            Field(("qc", "ranges", "salinity"), "Plausible salinity", "range", "practical"),
        ),
    ),
    (
        "Outputs",
        (
            Field(
                ("outputs", "formats"),
                "Dataset formats",
                "choices",
                "NetCDF is the one every other artifact is built from.",
                ("netcdf", "zarr", "csv"),
            ),
            Field(("outputs", "directory"), "Written to", placeholder="./"),
            Field(
                ("outputs", "site"),
                "Build interactive page",
                "switch",
                "Create the browsable HTML campaign page after processing.",
            ),
            Field(
                ("outputs", "single_html"),
                "Make the page self-contained",
                "switch",
                "Embed its data and assets in one portable HTML file.",
            ),
        ),
    ),
)

MANIFEST_FIELDS: tuple[Field, ...] = tuple(
    field for _, fields in MANIFEST_GROUPS for field in fields
)


def parse_integers(text: str) -> list[int]:
    """Read a comma- or space-separated list of phase codes."""
    parts = [part for part in text.replace(",", " ").split() if part]
    try:
        return [int(part) for part in parts]
    except ValueError as exc:
        raise ManifestError(f"{text!r} is not a list of whole numbers") from exc


def format_integers(value: Any) -> str:
    """Render a list of phase codes for a text control."""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return "" if value is None else str(value)
