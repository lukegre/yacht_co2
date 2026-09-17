"""Reading a published Zenodo record, and bringing one down to a folder.

A campaign need not start on the machine that measured it. Once a campaign has
been archived, its DOI names everything there is to know about it: the raw logs
it was measured as, and -- once it has been through the pipeline -- the
dataset, the run report and the interactive page it was processed into. Given
the DOI, this module says what a record holds and copies the wanted parts of it
into an ordinary campaign folder, so that from there on nothing has to know
whether a campaign was measured here or downloaded.

Every download is checked against the size and checksum Zenodo publishes, and a
file already on disk that still matches is left where it is: a published record
is immutable, so nothing in it is ever worth fetching twice.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
import yaml
from loguru import logger

from .errors import ZenodoError
from .naming import ARTIFACT_KINDS, field_slug, parse_output_name

# Shared with the upload client so both consumers read one Zenodo listing
# shape, whichever serialization the record happens to use.
from .zenodo import (
    COLLECTED_DATE_TYPE,
    CONFIG_NAME,
    INVENIO_ACCEPT,
    SLUG_SCHEME,
    _file_entries,
)

ZENODO_URL = "https://zenodo.org"
ZENODO_SANDBOX_URL = "https://sandbox.zenodo.org"
_ZENODO_DOI_RE = re.compile(r"^10\.(?P<prefix>5281|5072)/zenodo\.(?P<record>[^/?#]+)$", re.I)
_ZENODO_RECORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: What a file in a record is to this package. The first four are the products
#: of a pipeline run, ``product`` is one of its environmental inputs, ``log`` is
#: a raw instrument log, and ``other`` is everything a reader added themselves.
PRODUCT_KINDS = frozenset(ARTIFACT_KINDS)


def resolve_reference(repository: str) -> tuple[str, str]:
    """Return the API origin and record id named by a Zenodo reference.

    A DOI, a ``doi.org`` link, a record URL on either Zenodo or its sandbox,
    and a bare record id all name the same thing, and someone copying a
    reference out of a paper, a browser or a manifest has one of the four.
    """
    reference = repository.strip().rstrip("/")
    if not reference:
        raise ZenodoError("no Zenodo record given")
    # ``doi:10.5281/zenodo.1`` is a DOI written as a URI, and urlparse reads
    # its ``doi:`` as a scheme -- which would have it turned away as a URL
    # naming a host that cannot be fetched from.
    if reference[:4].lower() == "doi:":
        reference = reference[4:].strip()
    parsed = urlparse(reference)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"}:
            raise ZenodoError(f"unsupported Zenodo repository URL: {repository}")
        host = parsed.netloc.lower()
        if host == "doi.org":
            reference = unquote(parsed.path.lstrip("/"))
        elif host in {"zenodo.org", "www.zenodo.org", "sandbox.zenodo.org"}:
            match = re.search(r"/(?:api/)?records/([^/]+)$", parsed.path.rstrip("/"))
            if not match:
                raise ZenodoError(f"Zenodo repository URL has no record id: {repository}")
            origin = ZENODO_SANDBOX_URL if host.startswith("sandbox.") else ZENODO_URL
            record_id = unquote(match.group(1))
            if not _ZENODO_RECORD_RE.fullmatch(record_id) or record_id in {".", ".."}:
                raise ZenodoError(f"invalid Zenodo record id: {record_id!r}")
            return origin, record_id
        else:
            raise ZenodoError(f"repository is not a Zenodo URL: {repository}")
    doi = _ZENODO_DOI_RE.fullmatch(reference)
    if doi:
        origin = ZENODO_SANDBOX_URL if doi.group("prefix") == "5072" else ZENODO_URL
        record_id = doi.group("record")
        if not _ZENODO_RECORD_RE.fullmatch(record_id):
            raise ZenodoError(f"invalid Zenodo record id: {record_id!r}")
        return origin, record_id
    if _ZENODO_RECORD_RE.fullmatch(reference) and reference not in {".", ".."}:
        return ZENODO_URL, reference
    raise ZenodoError(f"invalid Zenodo repository reference: {repository}")


def file_matches(path: Path, entry: object) -> bool:
    """Check a file on disk against the size and checksum published by Zenodo."""
    if not path.is_file() or not isinstance(entry, dict):
        return False
    size = entry.get("size")
    if size is not None and path.stat().st_size != int(size):
        return False
    checksum = str(entry.get("checksum") or "")
    if not checksum:
        return size is not None
    algorithm, separator, expected = checksum.partition(":")
    if not separator or algorithm.lower() not in {"md5", "sha256"}:
        return False
    digest = hashlib.new(algorithm.lower(), usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.lower()


def read_record_json(
    reference: str, *, session: requests.Session | None = None
) -> tuple[str, str, dict[str, Any]]:
    """Fetch the record ``reference`` names, as Zenodo serves it.

    The returned id is the record's own, which is not always the one that was
    asked for: a concept DOI names every version of a record at once, and
    Zenodo answers it with the latest. Reading that id back is what keeps the
    DOI written down, the files downloaded and the directory they are cached in
    all describing the same one version.
    """
    origin, asked_for = resolve_reference(reference)
    client = session or requests.Session()
    record_url = f"{origin}/api/records/{asked_for}"
    logger.info("Reading Zenodo record {}", record_url)
    try:
        # Without this header Zenodo answers with its legacy deposit
        # serialization, which names the metadata fields differently and omits
        # ``pids`` altogether -- so the campaign would be unreadable for
        # reasons that have nothing to do with the record.
        response = client.get(record_url, headers={"Accept": INVENIO_ACCEPT}, timeout=60)
        response.raise_for_status()
        record = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ZenodoError(f"could not read Zenodo repository {reference}: {exc}") from exc
    if not isinstance(record, Mapping):
        raise ZenodoError(f"Zenodo repository {reference} did not return a record")
    listing = record.get("files")
    if listing is not None and not isinstance(listing, (Mapping, Sequence)):
        raise ZenodoError(f"Zenodo repository {reference} returned an invalid file listing")
    served = str(record.get("id") or "").strip()
    record_id = served if _ZENODO_RECORD_RE.fullmatch(served) else asked_for
    if record_id != asked_for:
        logger.info("Zenodo record {} is the current version of {}", record_id, asked_for)
    return origin, record_id, dict(record)


def download_entry(
    client: requests.Session, url: str, key: str, entry: Mapping[str, Any], target: Path
) -> Path:
    """Download one file of a record to ``target``, verifying what arrives.

    A file whose size and checksum already match is left alone. Everything else
    is written beside its destination first and moved into place only once it
    has been checked, so an interrupted download can never be mistaken for the
    file it was going to become.
    """
    if file_matches(target, dict(entry)):
        logger.info("Using cached Zenodo file {}", target)
        return target
    size = entry.get("size")
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with client.get(url, stream=True, timeout=120) as download:
            download.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        if size is not None and temporary.stat().st_size != int(size):
            raise ZenodoError(
                f"Zenodo file {key} has {temporary.stat().st_size} bytes; expected {size}"
            )
        if not file_matches(temporary, dict(entry)):
            raise ZenodoError(f"Zenodo file {key} failed checksum verification")
        temporary.replace(target)
    except ZenodoError:
        temporary.unlink(missing_ok=True)
        raise
    except (requests.RequestException, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise ZenodoError(f"could not download Zenodo file {key}: {exc}") from exc
    logger.info("Downloaded Zenodo file {}", target)
    return target


@dataclass(frozen=True)
class RecordFile:
    """One file of a published record, and what this package makes of it."""

    key: str
    kind: str
    size: int
    url: str
    entry: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_product(self) -> bool:
        """True for something a pipeline run wrote, rather than something it read."""
        return self.kind in PRODUCT_KINDS

    @property
    def is_log(self) -> bool:
        return self.kind == "log"


@dataclass(frozen=True)
class PublishedRecord:
    """What a Zenodo record holds, read through this package's conventions."""

    reference: str
    origin: str
    record_id: str
    doi: str
    title: str
    campaign: str
    campaign_date: str
    slug: str
    files: tuple[RecordFile, ...] = ()

    @property
    def url(self) -> str:
        return f"{self.origin}/records/{self.record_id}"

    @property
    def is_sandbox(self) -> bool:
        return self.origin == ZENODO_SANDBOX_URL

    @property
    def products(self) -> tuple[RecordFile, ...]:
        """The page, dataset, report and video a run of the pipeline wrote."""
        return tuple(file for file in self.files if file.is_product)

    @property
    def logs(self) -> tuple[RecordFile, ...]:
        """The raw instrument logs the campaign was measured as."""
        return tuple(file for file in self.files if file.is_log)


def _classify(key: str) -> str:
    """Say what one file of a record is, from its name alone."""
    parsed = parse_output_name(key)
    if parsed is not None:
        if parsed.kind in PRODUCT_KINDS:
            return parsed.kind
        if parsed.kind.startswith("product-"):
            return "product"
    return "log" if key.lower().endswith(".log") else "other"


def _entry_file(entry: Mapping[str, Any], record_url: str) -> RecordFile | None:
    key = str(entry.get("key") or "")
    if not key:
        return None
    links = entry.get("links")
    url = links.get("content") if isinstance(links, Mapping) else None
    try:
        size = int(entry.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return RecordFile(
        key=key,
        kind=_classify(key),
        size=size,
        url=str(url or f"{record_url}/files/{key}/content"),
        entry=dict(entry),
    )


def _collected_date(metadata: Mapping[str, Any]) -> str:
    """Read back the campaign date the upload declared as the record's own.

    It is written as an EDTF ``collected`` date precisely so that it survives
    the round trip through Zenodo, where the title would otherwise be the only
    place the campaign period is written down.
    """
    dates = metadata.get("dates")
    if not isinstance(dates, Sequence):
        return ""
    for entry in dates:
        if not isinstance(entry, Mapping):
            continue
        kind = entry.get("type")
        identifier = kind.get("id") if isinstance(kind, Mapping) else kind
        if str(identifier or "").strip().lower() == COLLECTED_DATE_TYPE:
            return str(entry.get("date") or "").strip()
    return ""


def _record_slug(metadata: Mapping[str, Any]) -> str:
    """Read back the folder slug the upload carried as an alternate identifier.

    It is the only stable join key between a published record, the folder it
    was uploaded from, and the manifest that processed it, which makes it the
    right name for the folder a reader downloads it back into.
    """
    identifiers = metadata.get("identifiers")
    if not isinstance(identifiers, Sequence):
        return ""
    for entry in identifiers:
        if not isinstance(entry, Mapping):
            continue
        scheme = str(entry.get("scheme") or "").strip().lower()
        value = str(entry.get("identifier") or "").strip()
        if scheme == SLUG_SCHEME and value and not any(c.isspace() for c in value):
            return value
    return ""


def suggest_campaign_name(slug: str) -> str:
    """Guess the campaign name a slug was made from.

    Slugging is lossy, so this is a suggestion and nothing more -- but it is a
    suggestion that slugs back to what it came from, which is what decides
    whether a downloaded folder's products are found under their own names.
    Anyone who knows better says so; the interface asks.
    """
    guessed = slug.replace("_", " ").strip().title()
    return guessed if field_slug(guessed) == slug else ""


def read_record(reference: str, *, session: requests.Session | None = None) -> PublishedRecord:
    """Describe the Zenodo record ``reference`` names.

    The campaign a record belongs to is read from the record's own metadata
    where it was declared there, and otherwise from the names of the products
    it holds, which carry the campaign and its date by construction.
    """
    origin, record_id, record = read_record_json(reference, session=session)
    record_url = f"{origin}/api/records/{record_id}"
    files = tuple(
        found
        for found in (
            _entry_file(entry, record_url) for entry in _file_entries(record.get("files"))
        )
        if found is not None
    )
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}

    # A product name carries the campaign and date the pipeline slugged into
    # it, which is the only place they appear when the record's metadata was
    # written by something other than this package.
    named = next(
        (parsed for parsed in map(parse_output_name, (f.key for f in files)) if parsed is not None),
        None,
    )
    pids = record.get("pids")
    doi = pids.get("doi", {}).get("identifier") if isinstance(pids, Mapping) else None
    return PublishedRecord(
        reference=reference,
        origin=origin,
        record_id=record_id,
        doi=str(doi or record.get("doi") or "").strip(),
        title=str(metadata.get("title") or "").strip(),
        campaign=suggest_campaign_name(named.campaign) if named else "",
        campaign_date=_collected_date(metadata) or (named.iso_date if named else ""),
        slug=_record_slug(metadata) or f"zenodo-{record_id}",
        files=tuple(sorted(files, key=lambda item: item.key)),
    )


def download(
    record: PublishedRecord,
    keys: Iterable[str],
    destination: str | Path,
    *,
    session: requests.Session | None = None,
) -> list[Path]:
    """Download the named files of ``record`` into ``destination``."""
    folder = Path(destination).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    available = {file.key: file for file in record.files}
    client = session or requests.Session()
    paths: list[Path] = []
    for key in keys:
        found = available.get(key)
        if found is None:
            raise ZenodoError(f"Zenodo record {record.record_id} holds no file {key!r}")
        if Path(key).name != key:
            raise ZenodoError(f"Zenodo file key must be a plain filename: {key!r}")
        paths.append(download_entry(client, found.url, key, found.entry, folder / key))
    return paths


def write_campaign_config(
    folder: Path, record: PublishedRecord, campaign: str, campaign_date: str
) -> Path | None:
    """Describe a downloaded record to the rest of the package, once.

    The folder needs a ``zenodo.yaml`` before anything else will treat it as a
    campaign: it is where the DOI the logs are read back from comes from, and
    where the campaign and date that name every artifact are declared. An
    existing one is left exactly as it is -- it belongs to a campaign that
    already knows its own identity, and overwriting it would replace what
    someone configured with what this download guessed.
    """
    destination = folder / CONFIG_NAME
    if destination.exists():
        logger.info("Left the existing {} alone; it already describes this folder", destination)
        return None
    document = {
        "campaign": campaign,
        "campaign_date": campaign_date,
        "doi": record.doi,
    }
    destination.write_text(
        yaml.safe_dump(
            {key: value for key, value in document.items() if value},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    logger.success("Wrote {}", destination)
    return destination


def import_record(
    record: PublishedRecord,
    destination: str | Path,
    keys: Iterable[str],
    *,
    campaign: str = "",
    campaign_date: str = "",
    session: requests.Session | None = None,
) -> list[Path]:
    """Download part of a record into a folder and make that folder a campaign.

    What arrives is an ordinary campaign folder: the same five steps apply to
    it, the same manifest describes it, and its products are found under the
    same names -- which is why the campaign and its date are written down
    rather than left to be inferred from the files.
    """
    folder = Path(destination).resolve()
    paths = download(record, keys, folder, session=session)
    write_campaign_config(
        folder,
        record,
        campaign or record.campaign,
        campaign_date or record.campaign_date,
    )
    logger.success(
        "Downloaded {} file(s) from {} into {}", len(paths), record.doi or record.url, folder
    )
    return paths
