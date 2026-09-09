"""Resumable Zenodo uploads built on the modern InvenioRDM records API.

Zenodo exposes two incompatible APIs: the legacy ``/api/deposit/depositions``
shim and the InvenioRDM-native ``/api/records`` API. Only the latter supports
DOI reservation on drafts, embargoed access, and community review, so this
module speaks the records API exclusively and never mixes the two.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
import re
import time
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import IO, Any
from urllib.parse import quote

import requests
import typer
import yaml
from dotenv import load_dotenv
from loguru import logger

from .errors import ZenodoError

CONFIG_NAME = "zenodo.yaml"
DEFAULTS_NAME = ".env.zenodo"
STATE_NAME = ".zenodo-upload.json"
PRODUCTION_URL = "https://zenodo.org"
SANDBOX_URL = "https://sandbox.zenodo.org"
NOTES_DESCRIPTION_TYPE = "other"
# Without this header Zenodo answers the records API with its *legacy* deposit
# serialization, which reports the DOI as a flat ``doi`` field and omits
# ``pids``, ``access``, and ``is_published`` entirely.
INVENIO_ACCEPT = "application/vnd.inveniordm.v1+json"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
PROGRESS_STEP = 0.25
PROGRESS_MIN_BYTES = 8 * 1024 * 1024
_ORCID_RE = re.compile(r"^(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-[\dX]{4})$", re.I)


def _deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recursively merged copy; lists and scalar values are replaced."""
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _add_months(value: date, months: int) -> date:
    """Add calendar months, clamping the day at the end of short months."""
    import calendar

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _valid_orcid(identifier: str) -> bool:
    """Validate an ORCID using the ISO 7064 MOD 11-2 checksum."""
    digits = identifier.replace("-", "")
    total = 0
    for character in digits[:15]:
        total = (total + int(character)) * 2
    remainder = (12 - total % 11) % 11
    expected = "X" if remainder == 10 else str(remainder)
    return digits[-1].upper() == expected


def parse_creators(entries: Sequence[str]) -> list[dict[str, Any]]:
    """Parse ordered ``last name, first name, ORCID`` creator strings.

    ORCID URLs and bare identifiers are accepted. The result uses Zenodo's
    structured ``person_or_org`` representation and preserves input order.

    Parameters
    ----------
    entries
        Ordered creator strings from the YAML configuration.

    Returns
    -------
    list of dict
        Creators ready for the modern Zenodo records API.
    """
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ZenodoError("creators must be an ordered YAML list")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, raw in enumerate(entries, start=1):
        if not isinstance(raw, str):
            raise ZenodoError(f"creator {position}: expected 'last name, first name, ORCID'")
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
            raise ZenodoError(f"creator {position}: expected 'last name, first name, ORCID'")
        match = _ORCID_RE.fullmatch(parts[2])
        if not match:
            raise ZenodoError(f"creator {position}: malformed ORCID {parts[2]!r}")
        orcid = match.group(1).upper()
        if not _valid_orcid(orcid):
            raise ZenodoError(f"creator {position}: invalid ORCID checksum for {orcid}")
        if orcid in seen:
            raise ZenodoError(f"creator {position}: duplicate ORCID {orcid}")
        seen.add(orcid)
        family_name, given_name = parts[:2]
        parsed.append(
            {
                "person_or_org": {
                    "type": "personal",
                    "name": f"{family_name}, {given_name}",
                    "given_name": given_name,
                    "family_name": family_name,
                    "identifiers": [{"scheme": "orcid", "identifier": orcid}],
                }
            }
        )
    if not parsed:
        raise ZenodoError("creators must contain at least one entry")
    return parsed


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ZenodoError(f"could not read {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ZenodoError(f"configuration root must be a mapping: {path}")
    return loaded


def _defaults(folder: Path, config_path: Path) -> dict[str, Any]:
    """Read shared defaults from the nearest ``.env.zenodo``.

    The file is YAML despite its name. Every copy found is merged, from the
    invocation directory through to the data folder, so a folder can override
    single keys without restating the whole file.
    """
    candidates = list(
        dict.fromkeys(
            [
                Path.cwd() / DEFAULTS_NAME,
                config_path.parent / DEFAULTS_NAME,
                folder / DEFAULTS_NAME,
            ]
        )
    )
    resolved: dict[str, Any] = {}
    found = False
    for candidate in candidates:
        if candidate.is_file():
            resolved = _deep_merge(resolved, _read_yaml(candidate))
            found = True
    if not found:
        searched = ", ".join(str(candidate.parent) for candidate in candidates)
        raise ZenodoError(f"no {DEFAULTS_NAME} defaults found; looked in {searched}")
    return resolved


def load_zenodo_config(
    folder: str | Path,
    config: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Resolve ``.env.zenodo`` defaults, a folder/config YAML, then CLI overrides.

    Parameters
    ----------
    folder
        Raw-data directory. Its default configuration is ``zenodo.yaml``.
    config
        Optional alternative YAML path.
    overrides
        Non-``None`` values supplied by a caller such as the CLI.
    today
        Date injection used for deterministic configuration generation/tests.
    """
    folder_path = Path(folder).resolve()
    config_path = Path(config).resolve() if config is not None else folder_path / CONFIG_NAME
    resolved = _defaults(folder_path, config_path)
    if config_path.exists():
        if not config_path.is_file():
            raise ZenodoError(f"configuration is not a file: {config_path}")
        resolved = _deep_merge(resolved, _read_yaml(config_path))
    if overrides:
        clean = {key: value for key, value in overrides.items() if value is not None}
        resolved = _deep_merge(resolved, clean)

    current = today or date.today()
    publication = resolved.get("publication_date") or current.isoformat()
    try:
        publication_date = date.fromisoformat(str(publication))
    except ValueError as exc:
        raise ZenodoError(f"invalid publication_date: {publication!r}") from exc
    resolved["publication_date"] = publication_date.isoformat()

    embargo = resolved.get("embargo")
    if not isinstance(embargo, dict):
        raise ZenodoError("embargo must be a mapping")
    embargo = dict(embargo)
    embargo["enabled"] = bool(embargo.get("enabled", True))
    try:
        months = int(embargo.get("months", 12))
    except (TypeError, ValueError) as exc:
        raise ZenodoError("embargo.months must be an integer") from exc
    if months < 0:
        raise ZenodoError("embargo.months cannot be negative")
    embargo["months"] = months
    if embargo["enabled"]:
        until = embargo.get("until") or _add_months(publication_date, months).isoformat()
        try:
            until_date = date.fromisoformat(str(until))
        except ValueError as exc:
            raise ZenodoError(f"invalid embargo end date: {until!r}") from exc
        if until_date < publication_date:
            raise ZenodoError("embargo end date cannot precede publication_date")
        embargo["until"] = until_date.isoformat()
    else:
        embargo["until"] = None
    resolved["embargo"] = embargo

    if not str(resolved.get("title") or "").strip():
        raise ZenodoError("title is required (pass --title when creating zenodo.yaml)")
    resolved["title"] = str(resolved["title"]).strip()
    if not str(resolved.get("community") or "").strip():
        raise ZenodoError("community is required")
    resolved["community"] = str(resolved["community"]).strip()
    parse_creators(resolved.get("creators", []))
    keywords = resolved.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords):
        raise ZenodoError("keywords must be a YAML list of strings")
    for key in ("resource_type", "license", "description", "language", "publisher"):
        if not isinstance(resolved.get(key), str) or not resolved[key].strip():
            raise ZenodoError(f"{key} must be a non-empty string")
    return resolved


def generate_zenodo_config(
    folder: str | Path,
    title: str,
    *,
    overrides: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> Path:
    """Generate ``FOLDER/zenodo.yaml`` containing all resolved metadata."""
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        raise ZenodoError(f"folder does not exist or is not a directory: {folder_path}")
    destination = folder_path / CONFIG_NAME
    if destination.exists():
        raise ZenodoError(f"configuration already exists: {destination}")
    supplied = dict(overrides or {})
    supplied["title"] = title
    resolved = load_zenodo_config(folder_path, overrides=supplied, today=today)
    destination.write_text(
        yaml.safe_dump(resolved, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return destination


def _selected_files(folder: Path) -> list[Path]:
    """Select uploadable top-level regular files in stable name order."""
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and not path.name.startswith(".")
            and path.name != CONFIG_NAME
        ),
        key=lambda path: path.name,
    )


def _subfolders(folder: Path) -> list[Path]:
    """List the visible directories that a flat Zenodo upload leaves behind."""
    return sorted(
        (path for path in folder.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name,
    )


def _warn_about_subfolders(folder: Path) -> list[str]:
    """Warn that subdirectories cannot be uploaded, and return their names.

    A Zenodo record's files are a flat namespace of unique keys with no
    directory concept, so a nested tree cannot be represented at all. Packing
    each subfolder into a single archive file is the only way to include it.
    """
    names = [f"{path.name}/" for path in _subfolders(folder)]
    if names:
        logger.warning(
            "Zenodo records cannot contain directories, so {} subfolder(s) of {} will NOT "
            "be uploaded: {}",
            len(names),
            folder.name,
            ", ".join(names),
        )
        logger.warning(
            "Pack a subfolder into a single archive (for example a .zip beside the other "
            "files in {}) if its contents have to be archived.",
            folder.name,
        )
    return names


def _checksums(path: Path) -> dict[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def _metadata(config: Mapping[str, Any], markdown_files: Sequence[Path]) -> dict[str, Any]:
    """Build record metadata in Zenodo's InvenioRDM schema.

    Free-form notes and the contents of any local markdown files are escaped and
    carried in ``additional_descriptions`` because the records API has no
    equivalent of the legacy flat ``notes`` field.
    """
    notes = str(config.get("notes") or "").strip()
    rendered = []
    for path in markdown_files:
        content = html.escape(path.read_text(encoding="utf-8", errors="replace"))
        rendered.append(f"<h3>{html.escape(path.name)}</h3><pre>{content}</pre>")
    if rendered:
        notes = "\n".join(part for part in (notes, *rendered) if part)
    metadata: dict[str, Any] = {
        "title": config["title"],
        "publication_date": config["publication_date"],
        "resource_type": {"id": config["resource_type"]},
        # DataCite requires a publisher before Zenodo will register the DOI.
        "publisher": config["publisher"],
        "creators": parse_creators(config["creators"]),
        "description": str(config["description"]),
        "rights": [{"id": config["license"]}],
        "languages": [{"id": config["language"]}],
        "subjects": [{"subject": keyword} for keyword in config.get("keywords", [])],
    }
    if notes:
        metadata["additional_descriptions"] = [
            {"description": notes, "type": {"id": NOTES_DESCRIPTION_TYPE}}
        ]
    return metadata


def _record_payload(config: Mapping[str, Any], markdown_files: Sequence[Path]) -> dict[str, Any]:
    """Build the full draft payload: files, access/embargo, DOI intent, metadata."""
    embargo = config["embargo"]
    access: dict[str, Any] = {
        "record": "public",
        "files": "restricted" if embargo["enabled"] else "public",
    }
    if embargo["enabled"]:
        access["embargo"] = {
            "active": True,
            "until": embargo["until"],
            "reason": "Author embargo pending publication.",
        }
    else:
        access["embargo"] = {"active": False, "until": None, "reason": None}
    return {
        "files": {"enabled": True},
        "access": access,
        "pids": {"doi": {"provider": "datacite"}},
        "metadata": _metadata(config, markdown_files),
    }


def _with_pids(payload: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """Echo a draft's current ``pids`` back into an update payload.

    ``PUT /api/records/{id}/draft`` replaces the whole resource, so an update
    that omits ``pids`` can drop a DOI that has already been reserved while the
    reservation itself survives server-side, leaving the draft unpublishable.
    """
    merged = dict(payload)
    existing = record.get("pids")
    if isinstance(existing, Mapping) and existing.get("doi"):
        merged["pids"] = dict(existing)
    return merged


class _ProgressReader:
    """Size-preserving file wrapper that logs progress and survives retries.

    ``__len__`` is required so that :mod:`requests` sets ``Content-Length``
    rather than falling back to chunked transfer encoding, which Zenodo's
    upload endpoint rejects.
    """

    def __init__(self, stream: IO[bytes], total: int, name: str) -> None:
        self._stream = stream
        self._total = total
        self._name = name
        self._sent = 0
        self._threshold = PROGRESS_STEP

    def __len__(self) -> int:
        return self._total

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        self._sent += len(chunk)
        if self._total >= PROGRESS_MIN_BYTES and self._sent >= self._threshold * self._total:
            logger.info("Uploading {} … {:.0%}", self._name, self._sent / self._total)
            while self._threshold * self._total <= self._sent:
                self._threshold += PROGRESS_STEP
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        self._sent = 0
        self._threshold = PROGRESS_STEP
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()


def _file_entries(payload: Any) -> list[dict[str, Any]]:
    """Normalise a files listing into a list of entries carrying their ``key``.

    Zenodo returns ``entries`` as a list, but some InvenioRDM versions key it by
    filename; both shapes are accepted here so the caller never has to care.
    """
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        raw: Any = payload
    elif isinstance(payload, Mapping):
        raw = payload.get("entries", [])
    else:
        return []
    if isinstance(raw, Mapping):
        return [{"key": name, **value} for name, value in raw.items() if isinstance(value, Mapping)]
    return [dict(item) for item in raw if isinstance(item, Mapping)]


class ZenodoClient:
    """Zenodo records-API client with bounded retries and streamed uploads.

    The access token is sent only as an ``Authorization`` header, never as a
    query parameter, and is redacted from every error message this class raises.
    """

    def __init__(
        self,
        token: str,
        *,
        sandbox: bool = False,
        session: requests.Session | None = None,
        timeout: float = 60.0,
        retries: int = 4,
    ) -> None:
        if not token:
            raise ZenodoError("a Zenodo access token is required")
        self.token = token
        self.base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = max(1, retries)
        self._community_ids: dict[str, str] = {}

    # -- transport ---------------------------------------------------------

    def _redact(self, text: str) -> str:
        return text.replace(self.token, "<redacted>")

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base_url}{path}"

    @staticmethod
    def _detail(response: requests.Response) -> str:
        """Summarise an InvenioRDM error body, including per-field messages."""
        try:
            body = response.json()
        except ValueError:
            return response.text[:500].strip()
        if not isinstance(body, Mapping):
            return str(body)[:500]
        summary = str(body.get("message") or response.reason or "").strip()
        problems = []
        for item in body.get("errors") or []:
            if not isinstance(item, Mapping):
                continue
            messages = item.get("messages") or item.get("message") or []
            if isinstance(messages, str):
                messages = [messages]
            problems.append(
                f"{item.get('field', '?')}: {'; '.join(str(part) for part in messages)}"
            )
        return f"{summary} ({' | '.join(problems)})" if problems else summary

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        try:
            delay = float(retry_after) if retry_after else 2**attempt
        except ValueError:
            delay = 2**attempt
        time.sleep(min(delay, 60) + random.uniform(0, 0.5))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Issue an authenticated request, retrying transient failures."""
        url = self._url(path)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": INVENIO_ACCEPT,
            **kwargs.pop("headers", {}),
        }
        body = kwargs.get("data")
        # A streamed body must be rewound before each retry, or the second
        # attempt would upload only the bytes the first attempt did not send.
        seekable = body if hasattr(body, "seek") and hasattr(body, "tell") else None
        rewind = seekable.tell() if seekable is not None else 0
        for attempt in range(self.retries):
            if attempt and seekable is not None:
                seekable.seek(rewind)
            try:
                response = self.session.request(
                    method, url, headers=headers, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.retries:
                    raise ZenodoError(
                        f"Zenodo {method} {path} failed: {self._redact(str(exc))}"
                    ) from exc
                self._backoff(attempt)
                continue
            if response.status_code in RETRY_STATUS and attempt + 1 < self.retries:
                logger.debug(
                    "Retrying Zenodo {} {} after HTTP {}", method, path, response.status_code
                )
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            if not response.ok:
                raise ZenodoError(
                    f"Zenodo {method} {path}: HTTP {response.status_code}: "
                    f"{self._redact(self._detail(response))}"
                )
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining and remaining.isdigit() and int(remaining) < 10:
                logger.warning("Zenodo rate limit nearly exhausted ({} left)", remaining)
            return response
        raise ZenodoError(f"Zenodo {method} {path}: retries exhausted")

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request and decode its JSON response."""
        response = self._request(method, path, **kwargs)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ZenodoError(f"Zenodo {method} {path} returned a non-JSON response") from exc

    # -- records -----------------------------------------------------------

    def create_draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(self.request_json("POST", "/api/records", json=dict(payload)))

    def get_draft(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}/draft"))

    def get_record(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}"))

    def update_draft(self, record_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(self.request_json("PUT", f"/api/records/{record_id}/draft", json=dict(payload)))

    def reserve_doi(self, record: Mapping[str, Any]) -> dict[str, Any]:
        url = record.get("links", {}).get("reserve_doi")
        return dict(
            self.request_json("POST", str(url or f"/api/records/{record['id']}/draft/pids/doi"))
        )

    def create_new_version(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("POST", f"/api/records/{record_id}/versions"))

    def import_files(self, record_id: str) -> list[dict[str, Any]]:
        """Link the previous version's files into a freshly created draft."""
        result = self.request_json("POST", f"/api/records/{record_id}/draft/actions/files-import")
        return _file_entries(result)

    # -- files -------------------------------------------------------------

    def list_files(self, record_id: str) -> list[dict[str, Any]]:
        return _file_entries(self.request_json("GET", f"/api/records/{record_id}/draft/files"))

    def delete_file(self, record_id: str, key: str) -> None:
        self._request("DELETE", f"/api/records/{record_id}/draft/files/{quote(key, safe='')}")

    def _try_initialise(self, record_id: str, key: str) -> dict[str, Any] | None:
        """Register ``key``, returning ``None`` when it is already registered.

        A duplicate key is reported either as a 4xx or as a per-entry error
        inside an otherwise successful response, so both shapes are treated as
        "this key needs clearing first".
        """
        try:
            created = self.request_json(
                "POST", f"/api/records/{record_id}/draft/files", json=[{"key": key}]
            )
        except ZenodoError as exc:
            if "HTTP 400" not in str(exc) and "HTTP 409" not in str(exc):
                raise
            return None
        if isinstance(created, Mapping) and created.get("errors"):
            return None
        for entry in _file_entries(created):
            if entry.get("key") == key:
                return entry
        return None

    def _initialise_file(self, record_id: str, key: str) -> dict[str, Any]:
        """Register a file key, clearing a stale entry left by a failed upload."""
        entry = self._try_initialise(record_id, key)
        if entry is not None:
            return entry
        logger.info("Clearing an incomplete Zenodo upload of {}", key)
        self.delete_file(record_id, key)
        retried = self._try_initialise(record_id, key)
        if retried is None:
            raise ZenodoError(f"Zenodo would not accept a new upload of {key!r}")
        return retried

    def upload_file(self, record_id: str, path: Path) -> dict[str, Any]:
        """Run the three-step records-API upload: initialise, stream, commit."""
        entry = self._initialise_file(record_id, path.name)
        links = entry.get("links", {}) if isinstance(entry.get("links"), Mapping) else {}
        encoded = quote(path.name, safe="")
        base = f"/api/records/{record_id}/draft/files/{encoded}"
        with path.open("rb") as stream:
            self._request(
                "PUT",
                str(links.get("content") or f"{base}/content"),
                data=_ProgressReader(stream, path.stat().st_size, path.name),
                headers={"Content-Type": "application/octet-stream"},
            )
        committed = self.request_json("POST", str(links.get("commit") or f"{base}/commit"))
        return dict(committed) if isinstance(committed, Mapping) else {"key": path.name}

    # -- communities and review -------------------------------------------

    def community_id(self, community: str) -> str:
        """Resolve a community slug to the UUID that review requests require."""
        if community in self._community_ids:
            return self._community_ids[community]
        result = self.request_json("GET", f"/api/communities/{quote(community, safe='')}")
        identifier = result.get("id") if isinstance(result, Mapping) else None
        if not identifier:
            raise ZenodoError(f"Zenodo community {community!r} did not return an ID")
        self._community_ids[community] = str(identifier)
        return str(identifier)

    def get_review(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}/draft/review"))

    def set_review(self, record_id: str, community: str) -> dict[str, Any]:
        return dict(
            self.request_json(
                "PUT",
                f"/api/records/{record_id}/draft/review",
                json={
                    "receiver": {"community": self.community_id(community)},
                    "type": "community-submission",
                },
            )
        )

    def submit_review(self, record_id: str) -> dict[str, Any]:
        return dict(
            self.request_json(
                "POST",
                f"/api/records/{record_id}/draft/actions/submit-review",
                json={
                    "payload": {
                        "content": "Submitted by yacht-co2 for community review.",
                        "format": "html",
                    }
                },
            )
        )


def _load_state(folder: Path) -> dict[str, Any]:
    path = folder / STATE_NAME
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ZenodoError(f"invalid upload state {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ZenodoError(f"invalid upload state {path}: root must be an object")
    return value


def _save_state(folder: Path, state: Mapping[str, Any]) -> None:
    path = folder / STATE_NAME
    temporary = folder / f"{STATE_NAME}.tmp"
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _extract_doi(record: Mapping[str, Any]) -> str | None:
    """Read a DOI from either Zenodo serialization.

    The records API reports ``pids.doi.identifier``; the legacy deposit
    serialization Zenodo falls back to reports a flat ``doi``.
    """
    pids = record.get("pids")
    doi = pids.get("doi", {}).get("identifier") if isinstance(pids, Mapping) else None
    return str(doi or record.get("doi") or "") or None


def _remote_checksum(entry: Mapping[str, Any]) -> str | None:
    checksum = entry.get("checksum")
    if isinstance(checksum, str):
        return checksum.removeprefix("md5:")
    if isinstance(checksum, Mapping):
        value = checksum.get("md5")
        return str(value).removeprefix("md5:") if value else None
    return None


def _classify_files(
    remote_entries: Mapping[str, Mapping[str, Any]], local: Mapping[str, Mapping[str, Any]]
) -> dict[str, list[str]]:
    """Split local and remote file listings into an upload plan.

    Membership and MD5 equality decide the four buckets, so the same
    classification can be reported before uploading and reused to explain a
    draft whose files are frozen by a pending review.
    """
    plan: dict[str, list[str]] = {"new": [], "changed": [], "unchanged": []}
    for name, info in local.items():
        remote = remote_entries.get(name)
        if remote is None:
            plan["new"].append(name)
        elif _remote_checksum(remote) == info["md5"]:
            plan["unchanged"].append(name)
        else:
            plan["changed"].append(name)
    plan["remote_only"] = sorted(set(remote_entries) - set(local))
    return plan


def _log_file_plan(record_id: str, plan: Mapping[str, Sequence[str]]) -> None:
    """Report, before any transfer starts, what the upload is about to do."""
    logger.info(
        "Zenodo draft {} file plan: {} new, {} changed, {} unchanged, {} remote-only",
        record_id,
        len(plan["new"]),
        len(plan["changed"]),
        len(plan["unchanged"]),
        len(plan["remote_only"]),
    )


def _stamp_config(config_path: Path, doi: str | None, submitted: str | None = None) -> None:
    """Record the DOI, and the submission date once review is under way, in the YAML.

    This makes ``zenodo.yaml`` the durable record of what a folder produced:
    ``doi`` appears as soon as one is reserved, and ``submitted`` marks the
    folder as handed over to its community.
    """
    if not config_path.is_file():
        return
    document = _read_yaml(config_path)
    updated = dict(document)
    if doi:
        updated["doi"] = doi
    if submitted:
        updated["submitted"] = submitted
    if updated == document:
        return
    config_path.write_text(
        yaml.safe_dump(updated, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    logger.info("Recorded DOI {} in {}", doi, config_path.name)


def _notes_of(source: Mapping[str, Any]) -> str:
    """Return the notes carried by a payload or a record, for change detection."""
    metadata = source.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    entries = metadata.get("additional_descriptions") or []
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return ""
    return "\n".join(
        str(entry.get("description", "")) for entry in entries if isinstance(entry, Mapping)
    )


def _is_missing(error: ZenodoError) -> bool:
    """Return whether an error reports a record that Zenodo does not have."""
    return "HTTP 404" in str(error)


def _is_published(record: Mapping[str, Any]) -> bool:
    """Detect a published record in either Zenodo serialization."""
    if record.get("is_published") is not None:
        return bool(record["is_published"])
    return (
        bool(record.get("submitted"))
        or record.get("status") == "published"
        or record.get("state") == "done"
    )


def _review_is_pending(review: Mapping[str, Any]) -> bool:
    """Return whether a review request is actually awaiting a curator decision.

    A request that has only been *attached* to a draft has status ``created``
    with ``is_open`` false: it still needs submitting, so it is not pending.
    """
    if not review:
        return False
    status = str(review.get("status") or "").lower()
    if status:
        return status in {"submitted", "pending", "open"}
    return bool(review.get("is_open"))


def _record_links(record: Mapping[str, Any]) -> dict[str, Any]:
    links = record.get("links")
    return dict(links) if isinstance(links, Mapping) else {}


def _load_zenodo_environment(folder: Path, config_path: Path) -> None:
    """Add nearby ``.env`` values to ``os.environ`` without overriding exports.

    Folder-specific values take precedence over an alternative configuration
    directory and the invocation directory. Values are loaded only immediately
    before credentials are needed and are never logged.
    """
    candidates = [folder / ".env", config_path.parent / ".env", Path.cwd() / ".env"]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            load_dotenv(resolved, override=False)
            seen.add(resolved)


def upload_raw_folder(
    folder: str | Path,
    *,
    title: str | None = None,
    config: str | Path | None = None,
    community: str | None = None,
    publish: bool = False,
    embargo: str | date | None = None,
    sandbox: bool = False,
    new_version: bool = False,
    record_id: str | int | None = None,
    prune: bool = False,
    dry_run: bool = False,
    client: ZenodoClient | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Create or resume a Zenodo draft for top-level files in ``folder``.

    State is written to ``.zenodo-upload.json`` after every durable remote step.
    With ``publish=True`` the draft is submitted to its configured community for
    review; Zenodo publishes only when a curator accepts it.

    Files are public unless ``embargo`` supplies a ``YYYY-MM-DD`` release date,
    in which case they stay restricted until then.
    """
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        raise ZenodoError(f"folder does not exist or is not a directory: {folder_path}")
    config_path = Path(config).resolve() if config is not None else folder_path / CONFIG_NAME
    overrides: dict[str, Any] = {
        "title": title,
        "community": community,
        # ``--sandbox`` enables the sandbox; omitting it must not disable a
        # sandbox explicitly selected in an existing YAML file.
        "sandbox": True if sandbox else None,
    }
    if embargo is not None:
        overrides["embargo"] = {"enabled": True, "until": str(embargo)}

    if not config_path.exists():
        if config is not None:
            raise ZenodoError(f"configuration does not exist: {config_path}")
        if not title:
            raise ZenodoError("no zenodo.yaml found; --title is required")
        generate_zenodo_config(folder_path, title, overrides=overrides, today=today)
    resolved = load_zenodo_config(folder_path, config_path, overrides, today=today)
    stamp_date = (today or date.today()).isoformat()
    selected = _selected_files(folder_path)
    skipped_folders = _warn_about_subfolders(folder_path)
    logger.info("Checksumming {} top-level file(s) in {}", len(selected), folder_path)
    local: dict[str, dict[str, Any]] = {
        path.name: {"path": path, **_checksums(path)} for path in selected
    }
    markdown = [path for path in selected if path.suffix.lower() in {".md", ".markdown"}]
    payload = _record_payload(resolved, markdown)
    if dry_run:
        logger.success("Validated Zenodo metadata and {} local files", len(local))
        return {
            "status": "dry-run",
            "config": str(config_path),
            "files": {
                name: {key: value for key, value in info.items() if key != "path"}
                for name, info in local.items()
            },
            "metadata": payload,
            "skipped_folders": skipped_folders,
        }

    use_sandbox = bool(resolved.get("sandbox", sandbox))
    if client is None:
        _load_zenodo_environment(folder_path, config_path)
        variable = "ZENODO_SANDBOX_ACCESS_TOKEN" if use_sandbox else "ZENODO_ACCESS_TOKEN"
        token = os.environ.get(variable)
        if not token:
            raise ZenodoError(f"{variable} is required")
        client = ZenodoClient(token, sandbox=use_sandbox)

    state = _load_state(folder_path)
    if state and "sandbox" in state and bool(state["sandbox"]) != use_sandbox and not record_id:
        raise ZenodoError(
            "upload state belongs to a different Zenodo environment; pass --record-id "
            "or restore the matching sandbox setting"
        )
    current_id = str(record_id or state.get("record_id") or "")
    record: dict[str, Any]
    if current_id:
        try:
            record = client.get_draft(current_id)
            source = "--record-id" if record_id else STATE_NAME
            logger.info("Resuming Zenodo draft {} (from {})", current_id, source)
            published = _is_published(record)
        except ZenodoError as draft_error:
            try:
                record = client.get_record(current_id)
            except ZenodoError as published_error:
                if _is_missing(draft_error) and _is_missing(published_error):
                    raise ZenodoError(
                        f"Zenodo record {current_id} no longer exists. Sandbox records are "
                        f"purged periodically; delete {folder_path / STATE_NAME} to start a "
                        "new draft, or pass --record-id to resume a different record."
                    ) from published_error
                raise draft_error from published_error
            published = True
        if not published:
            try:
                review = client.get_review(current_id)
            except ZenodoError:
                if state.get("status") == "pending_review":
                    logger.warning(
                        "Could not refresh pending Zenodo review {}; leaving it unchanged",
                        current_id,
                    )
                    return state
                review = {}
            if _review_is_pending(review):
                try:
                    frozen = _classify_files(
                        {str(item["key"]): item for item in client.list_files(current_id)}, local
                    )
                except ZenodoError as exc:
                    logger.debug("Could not list files on Zenodo draft {}: {}", current_id, exc)
                    frozen = None
                if frozen and (frozen["new"] or frozen["changed"]):
                    logger.warning(
                        "Zenodo record {} is awaiting community review, so its files are "
                        "frozen: {} new and {} changed local file(s) will NOT be uploaded ({})",
                        current_id,
                        len(frozen["new"]),
                        len(frozen["changed"]),
                        ", ".join(frozen["new"] + frozen["changed"]),
                    )
                    logger.warning(
                        "Wait for the curator's decision, then rerun with --new-version to "
                        "archive the changed files as a new version."
                    )
                if _notes_of(payload) != _notes_of(record):
                    record = client.update_draft(current_id, _with_pids(payload, record))
                    logger.success(
                        "Updated the notes on Zenodo draft {}; its review stays pending",
                        current_id,
                    )
                state.update(
                    {
                        "record_id": current_id,
                        "sandbox": use_sandbox,
                        "status": "pending_review",
                        "community": resolved["community"],
                        "review_url": review.get("links", {}).get(
                            "self_html", state.get("review_url")
                        ),
                    }
                )
                _save_state(folder_path, state)
                _stamp_config(config_path, state.get("reserved_doi"), stamp_date)
                logger.info("Zenodo record {} is pending community review", current_id)
                return state
        if published:
            if not new_version:
                raise ZenodoError(
                    "record is published; pass --new-version before uploading changes"
                )
            logger.info("Zenodo record {} is published; creating a new version draft", current_id)
            record = client.create_new_version(current_id)
            logger.info(
                "Created new version draft {} from Zenodo record {}", record.get("id"), current_id
            )
            try:
                imported = client.import_files(str(record["id"]))
                logger.info(
                    "Imported {} file(s) from version {} into draft {}",
                    len(imported),
                    current_id,
                    record.get("id"),
                )
            except ZenodoError as exc:
                logger.debug("No files imported into the new version draft: {}", exc)
    else:
        if new_version:
            raise ZenodoError("--new-version requires --record-id or an existing upload state")
        record = client.create_draft(payload)
        logger.info("Created Zenodo draft {}", record.get("id"))

    current_id = str(record["id"])
    if state.get("record_id") not in {None, current_id}:
        state.pop("reserved_doi", None)
        state.pop("files", None)
    links = _record_links(record)
    state.update(
        {
            "record_id": current_id,
            "sandbox": use_sandbox,
            "status": "draft",
            "draft_url": links.get("self_html") or links.get("html"),
            "draft_api_url": links.get("self"),
            "record_url": links.get("record_html") or links.get("html"),
        }
    )
    _save_state(folder_path, state)
    record = client.update_draft(current_id, _with_pids(payload, record))
    # The draft itself is the only authority on whether a DOI exists: a cached
    # ``reserved_doi`` can outlive the record it was minted for, and a draft
    # carrying ``pids.doi.provider`` without an identifier fails review
    # submission with "pids.doi.value.identifier: Missing data".
    if not _extract_doi(record):
        reserved = client.reserve_doi(record)
        refreshed = client.get_draft(current_id)
        refreshed_doi = _extract_doi(refreshed) or _extract_doi(reserved)
        record = refreshed
        if refreshed_doi:
            record.setdefault("pids", {}).setdefault("doi", {})["identifier"] = refreshed_doi
        logger.info("Reserved DOI {} for Zenodo draft {}", refreshed_doi, current_id)
    links = _record_links(record)
    state["reserved_doi"] = _extract_doi(record)
    state["draft_url"] = links.get("self_html") or links.get("html") or state.get("draft_url")
    state["draft_api_url"] = links.get("self") or state.get("draft_api_url")
    state["record_url"] = links.get("record_html") or state.get("record_url")
    _save_state(folder_path, state)

    remote_entries = {str(item["key"]): item for item in client.list_files(current_id)}
    plan = _classify_files(remote_entries, local)
    _log_file_plan(current_id, plan)
    remote_only = plan["remote_only"]
    if prune:
        for name in remote_only:
            client.delete_file(current_id, name)
            logger.info("Pruned remote-only Zenodo file {}", name)
        remote_only = []
    elif remote_only:
        logger.warning(
            "{} file(s) exist only in Zenodo draft {} and are left untouched: {}; pass --prune "
            "to delete them",
            len(remote_only),
            current_id,
            ", ".join(remote_only),
        )
    pending = plan["new"] + plan["changed"]
    started = 0
    for name, info in local.items():
        remote = remote_entries.get(name)
        if remote and _remote_checksum(remote) == info["md5"]:
            logger.debug("Skipping unchanged Zenodo file {}", name)
            continue
        started += 1
        logger.info(
            "Zenodo upload {}/{}: {} ({})",
            started,
            len(pending),
            name,
            "replacing changed file" if remote else "new file",
        )
        if remote:
            client.delete_file(current_id, name)
        committed = client.upload_file(current_id, info["path"])
        committed_md5 = _remote_checksum(committed)
        if not committed_md5:
            refreshed = {str(item["key"]): item for item in client.list_files(current_id)}.get(
                name, {}
            )
            committed_md5 = _remote_checksum(refreshed)
        if not committed_md5:
            raise ZenodoError(f"Zenodo did not return a checksum after uploading {name}")
        if committed_md5 != info["md5"]:
            raise ZenodoError(f"checksum verification failed after uploading {name}")
        logger.success("Uploaded and verified Zenodo file {}", name)
        state.setdefault("files", {})[name] = {
            "md5": info["md5"],
            "sha256": info["sha256"],
            "size": info["path"].stat().st_size,
        }
        _save_state(folder_path, state)

    state["files"] = {
        name: {
            "md5": info["md5"],
            "sha256": info["sha256"],
            "size": info["path"].stat().st_size,
        }
        for name, info in local.items()
    }
    state["remote_only_files"] = remote_only
    state["skipped_folders"] = skipped_folders
    logger.success(
        "Zenodo draft {} now holds {} file(s): {} uploaded this run, {} already present",
        current_id,
        len(local),
        len(pending),
        len(plan["unchanged"]),
    )
    if publish:
        if remote_only:
            names = ", ".join(remote_only)
            raise ZenodoError(f"remote-only files block review submission: {names}; pass --prune")
        if not state.get("reserved_doi"):
            raise ZenodoError(
                f"Zenodo draft {current_id} has no reserved DOI, which review submission "
                "requires; rerun without --publish to reserve one"
            )
        client.set_review(current_id, resolved["community"])
        review = client.submit_review(current_id)
        state["status"] = "pending_review"
        state["community"] = resolved["community"]
        state["review_url"] = review.get("links", {}).get("self_html", state.get("review_url"))
        logger.success(
            "Submitted Zenodo draft {} to {} for review", current_id, resolved["community"]
        )
    _save_state(folder_path, state)
    _stamp_config(
        config_path,
        state.get("reserved_doi"),
        stamp_date if state["status"] == "pending_review" else None,
    )
    return state


app = typer.Typer(add_completion=False, help="Upload a raw-data folder to a Zenodo draft.")


@app.command()
def zenodo_upload_cli(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    title: str | None = typer.Option(None, help="Dataset title; required when generating YAML."),
    config: Path | None = typer.Option(None, help="Use an alternative YAML configuration."),
    community: str | None = typer.Option(None, help="Override the target community slug."),
    publish: bool = typer.Option(
        True, "--publish/--no-publish", help="Submit the draft for community review."
    ),
    embargo: str | None = typer.Option(
        None,
        "--embargo",
        metavar="YYYY-MM-DD",
        help="Restrict files until this date; omit to publish them immediately.",
    ),
    sandbox: bool = typer.Option(False, help="Use sandbox.zenodo.org and its token."),
    new_version: bool = typer.Option(False, help="Create a draft version of a published record."),
    record_id: str | None = typer.Option(None, help="Resume or version this Zenodo record ID."),
    prune: bool = typer.Option(False, help="Delete files that exist only in the remote draft."),
    dry_run: bool = typer.Option(False, help="Validate locally without making API calls."),
) -> None:
    """Create, resume, or submit a raw-folder Zenodo draft."""
    try:
        result = upload_raw_folder(
            folder,
            title=title,
            config=config,
            community=community,
            publish=publish,
            embargo=embargo,
            sandbox=sandbox,
            new_version=new_version,
            record_id=record_id,
            prune=prune,
            dry_run=dry_run,
        )
    except ZenodoError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if result["status"] == "dry-run":
        typer.echo(f"dry run valid: {result['config']}")
        typer.echo("files: " + ", ".join(result["files"]))
        if result["skipped_folders"]:
            typer.echo("skipped subfolders: " + ", ".join(result["skipped_folders"]))
    elif result["status"] == "pending_review":
        typer.echo(f"submitted for review: {result.get('review_url') or result['record_id']}")
    else:
        typer.echo(f"draft: {result.get('draft_url') or result['record_id']}")
        typer.echo(f"reserved DOI: {result.get('reserved_doi') or 'pending'}")


if __name__ == "__main__":
    app()
