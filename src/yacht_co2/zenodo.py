"""Resumable uploads of raw expedition folders to the modern Zenodo API."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import typer
import yaml
from dotenv import load_dotenv
from loguru import logger

from .errors import ZenodoError

CONFIG_NAME = "zenodo.yaml"
STATE_NAME = ".zenodo-upload.json"
PRODUCTION_URL = "https://zenodo.org"
SANDBOX_URL = "https://sandbox.zenodo.org"
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


def _defaults() -> dict[str, Any]:
    resource = files("yacht_co2").joinpath("data/zenodo_defaults.yaml")
    loaded = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - protects a packaged invariant
        raise ZenodoError("packaged Zenodo defaults are invalid")
    return loaded


def load_zenodo_config(
    folder: str | Path,
    config: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Resolve packaged defaults, a folder/config YAML, then CLI overrides.

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
    resolved = _defaults()
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
    for key in ("resource_type", "license", "description", "language"):
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


def _checksums(path: Path) -> dict[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def _metadata(config: Mapping[str, Any], markdown_files: Sequence[Path]) -> dict[str, Any]:
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
        "creators": parse_creators(config["creators"]),
        "description": str(config["description"]),
        "rights": [{"id": config["license"]}],
        "languages": [{"id": config["language"]}],
        "subjects": [{"subject": keyword} for keyword in config.get("keywords", [])],
    }
    if notes:
        metadata["additional_descriptions"] = [
            {"description": notes, "type": {"id": "notes"}}
        ]
    return metadata


def _record_payload(config: Mapping[str, Any], markdown_files: Sequence[Path]) -> dict[str, Any]:
    embargo = config["embargo"]
    access: dict[str, Any] = {
        "record": "public",
        "files": "restricted" if embargo["enabled"] else "public",
    }
    if embargo["enabled"]:
        access["embargo"] = {"active": True, "until": embargo["until"]}
    return {"files": {"enabled": True}, "access": access, "metadata": _metadata(config, markdown_files)}


class ZenodoClient:
    """Small modern-Zenodo API client with bounded retries and streamed files."""

    def __init__(
        self,
        token: str,
        *,
        sandbox: bool = False,
        session: requests.Session | None = None,
        timeout: float = 60,
        retries: int = 3,
    ) -> None:
        if not token:
            raise ZenodoError("a Zenodo access token is required")
        self.token = token
        self.base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = max(1, retries)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        target = url if url.startswith("http") else f"{self.base_url}{url}"
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token}"
        body = kwargs.get("data")
        body_position = (
            body.tell()
            if body is not None and hasattr(body, "tell") and hasattr(body, "seek")
            else None
        )
        for attempt in range(self.retries):
            if attempt and body is not None and body_position is not None:
                body.seek(body_position)
            try:
                response = self.session.request(
                    method, target, headers=headers, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.retries:
                    message = str(exc).replace(self.token, "<redacted>")
                    raise ZenodoError(f"Zenodo request failed: {message}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code not in {429, 500, 502, 503, 504} or attempt + 1 == self.retries:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2**attempt
            except ValueError:
                delay = 2**attempt
            time.sleep(delay)
        if not response.ok:
            detail = response.text[:1000].replace(self.token, "<redacted>")
            raise ZenodoError(f"Zenodo API {method} {target}: HTTP {response.status_code}: {detail}")
        return response

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make an authenticated request and decode its JSON response."""
        response = self._request(method, url, **kwargs)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ZenodoError("Zenodo returned a non-JSON API response") from exc

    def create_draft(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(self.request_json("POST", "/api/records", json=dict(payload)))

    def get_draft(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}/draft"))

    def get_record(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}"))

    def get_review(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("GET", f"/api/records/{record_id}/draft/review"))

    def update_draft(self, record_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(
            self.request_json("PUT", f"/api/records/{record_id}/draft", json=dict(payload))
        )

    def reserve_doi(self, record: Mapping[str, Any]) -> dict[str, Any]:
        url = record.get("links", {}).get("reserve_doi")
        if not url:
            url = f"/api/records/{record['id']}/draft/pids/doi"
        return dict(self.request_json("POST", str(url)))

    def list_files(self, record_id: str) -> list[dict[str, Any]]:
        result = self.request_json("GET", f"/api/records/{record_id}/draft/files")
        if isinstance(result, list):
            return [dict(item) for item in result]
        return [dict(item) for item in result.get("entries", [])]

    def delete_file(self, record_id: str, key: str) -> None:
        encoded = quote(key, safe="")
        self._request("DELETE", f"/api/records/{record_id}/draft/files/{encoded}")

    def upload_file(self, record_id: str, path: Path) -> dict[str, Any]:
        initialized = self.request_json(
            "POST", f"/api/records/{record_id}/draft/files", json=[{"key": path.name}]
        )
        entry = initialized[0] if isinstance(initialized, list) else initialized["entries"][0]
        content_url = entry.get("links", {}).get("content")
        encoded = quote(path.name, safe="")
        content_url = content_url or f"/api/records/{record_id}/draft/files/{encoded}/content"
        with path.open("rb") as stream:
            self._request(
                "PUT",
                str(content_url),
                data=stream,
                headers={"Content-Type": "application/octet-stream"},
            )
        commit_url = entry.get("links", {}).get("commit")
        commit_url = commit_url or f"/api/records/{record_id}/draft/files/{encoded}/commit"
        return dict(self.request_json("POST", str(commit_url)))

    def create_new_version(self, record_id: str) -> dict[str, Any]:
        return dict(self.request_json("POST", f"/api/records/{record_id}/versions"))

    def set_review(self, record_id: str, community: str) -> dict[str, Any]:
        return dict(
            self.request_json(
                "PUT",
                f"/api/records/{record_id}/draft/review",
                json={"receiver": {"community": community}, "type": "community-submission"},
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
    doi = record.get("pids", {}).get("doi", {}).get("identifier")
    return str(doi) if doi else None


def _remote_checksum(entry: Mapping[str, Any]) -> str | None:
    checksum = entry.get("checksum")
    if isinstance(checksum, str):
        return checksum.removeprefix("md5:")
    if isinstance(checksum, Mapping):
        value = checksum.get("md5")
        return str(value).removeprefix("md5:") if value else None
    return None


def _review_is_pending(review: Mapping[str, Any]) -> bool:
    """Return whether an InvenioRDM review request is still awaiting a decision."""
    status = str(review.get("status") or "").lower()
    if status in {"submitted", "pending", "open"}:
        return True
    return bool(review) and review.get("is_closed") is False


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
    embargo: bool | None = None,
    embargo_until: str | date | None = None,
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
    embargo_overrides: dict[str, Any] = {}
    if embargo is not None:
        embargo_overrides["enabled"] = embargo
    if embargo_until is not None:
        embargo_overrides.update(enabled=True, until=str(embargo_until))
    if embargo_overrides:
        overrides["embargo"] = embargo_overrides

    if not config_path.exists():
        if config is not None:
            raise ZenodoError(f"configuration does not exist: {config_path}")
        if not title:
            raise ZenodoError("no zenodo.yaml found; --title is required")
        generate_zenodo_config(folder_path, title, overrides=overrides, today=today)
    resolved = load_zenodo_config(folder_path, config_path, overrides, today=today)
    selected = _selected_files(folder_path)
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
            "files": {name: {k: v for k, v in info.items() if k != "path"} for name, info in local.items()},
            "metadata": payload,
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
            logger.info("Resuming Zenodo draft {}", current_id)
            published = bool(record.get("is_published") or record.get("status") == "published")
        except ZenodoError as draft_error:
            try:
                record = client.get_record(current_id)
            except ZenodoError as published_error:
                raise draft_error from published_error
            published = True
        if not published:
            try:
                review = client.get_review(current_id)
            except ZenodoError:
                if state.get("status") == "pending_review":
                    logger.warning("Could not refresh pending Zenodo review {}; leaving it unchanged", current_id)
                    return state
                review = {}
            if _review_is_pending(review):
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
                logger.info("Zenodo record {} is pending community review", current_id)
                return state
        if published:
            if not new_version:
                raise ZenodoError("record is published; pass --new-version before uploading changes")
            record = client.create_new_version(current_id)
            logger.info("Created a new version draft from Zenodo record {}", current_id)
            if record.get("links", {}).get("latest_draft"):
                record = dict(client.request_json("GET", record["links"]["latest_draft"]))
    else:
        if new_version:
            raise ZenodoError("--new-version requires --record-id or an existing upload state")
        record = client.create_draft(payload)
        logger.info("Created Zenodo draft {}", record.get("id"))

    current_id = str(record["id"])
    if state.get("record_id") not in {None, current_id}:
        state.pop("reserved_doi", None)
        state.pop("files", None)
    state.update(
        {
            "record_id": current_id,
            "sandbox": use_sandbox,
            "status": "draft",
            "draft_url": record.get("links", {}).get("self_html"),
            "draft_api_url": record.get("links", {}).get("self"),
            "record_url": record.get("links", {}).get("record_html"),
        }
    )
    _save_state(folder_path, state)
    record = client.update_draft(current_id, payload)
    if not _extract_doi(record) and not state.get("reserved_doi"):
        reserved = client.reserve_doi(record)
        if reserved:
            record = reserved
        logger.info("Reserved a DOI for Zenodo draft {}", current_id)
    state["reserved_doi"] = _extract_doi(record) or state.get("reserved_doi")
    state["draft_url"] = record.get("links", {}).get("self_html", state.get("draft_url"))
    state["draft_api_url"] = record.get("links", {}).get(
        "self", state.get("draft_api_url")
    )
    state["record_url"] = record.get("links", {}).get(
        "record_html", state.get("record_url")
    )
    _save_state(folder_path, state)

    remote_entries = {str(item["key"]): item for item in client.list_files(current_id)}
    remote_only = sorted(set(remote_entries) - set(local))
    if prune:
        for name in remote_only:
            client.delete_file(current_id, name)
            logger.info("Pruned remote-only Zenodo file {}", name)
        remote_only = []
    for name, info in local.items():
        remote = remote_entries.get(name)
        if remote and _remote_checksum(remote) == info["md5"]:
            logger.debug("Skipping unchanged Zenodo file {}", name)
            continue
        if remote:
            client.delete_file(current_id, name)
            logger.info("Replacing changed Zenodo file {}", name)
        committed = client.upload_file(current_id, info["path"])
        committed_md5 = _remote_checksum(committed)
        if not committed_md5:
            refreshed = {
                str(item["key"]): item for item in client.list_files(current_id)
            }.get(name, {})
            committed_md5 = _remote_checksum(refreshed)
        if not committed_md5:
            raise ZenodoError(f"Zenodo did not return a checksum after uploading {name}")
        if committed_md5 and committed_md5 != info["md5"]:
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
    if publish:
        if remote_only:
            names = ", ".join(remote_only)
            raise ZenodoError(f"remote-only files block review submission: {names}; pass --prune")
        client.set_review(current_id, resolved["community"])
        review = client.submit_review(current_id)
        state["status"] = "pending_review"
        state["community"] = resolved["community"]
        state["review_url"] = review.get("links", {}).get(
            "self_html", state.get("review_url")
        )
        logger.success("Submitted Zenodo draft {} to {} for review", current_id, resolved["community"])
    _save_state(folder_path, state)
    return state


app = typer.Typer(add_completion=False, help="Upload a raw-data folder to a Zenodo draft.")


@app.command()
def zenodo_upload_cli(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    title: str | None = typer.Option(None, help="Dataset title; required when generating YAML."),
    config: Path | None = typer.Option(None, help="Use an alternative YAML configuration."),
    community: str | None = typer.Option(None, help="Override the target community slug."),
    publish: bool = typer.Option(False, help="Submit the draft for community review."),
    embargo: bool | None = typer.Option(None, "--embargo/--no-embargo"),
    embargo_until: str | None = typer.Option(None, help="Embargo end date (YYYY-MM-DD)."),
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
            embargo_until=embargo_until,
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
    elif result["status"] == "pending_review":
        typer.echo(f"submitted for review: {result.get('review_url') or result['record_id']}")
    else:
        typer.echo(f"draft: {result.get('draft_url') or result['record_id']}")
        typer.echo(f"reserved DOI: {result.get('reserved_doi') or 'pending'}")


if __name__ == "__main__":
    app()
