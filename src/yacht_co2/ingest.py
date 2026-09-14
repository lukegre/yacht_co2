"""OceanPack tagged-log ingestion."""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
import pandas as pd
import requests
import xarray as xr
from loguru import logger

from .errors import ParseError, ZenodoError
from .schema import QCFlag, attach_qc_metadata, validate_dataset

ZENODO_URL = "https://zenodo.org"
ZENODO_SANDBOX_URL = "https://sandbox.zenodo.org"
_ZENODO_DOI_RE = re.compile(r"^10\.(?P<prefix>5281|5072)/zenodo\.(?P<record>[^/?#]+)$", re.I)
_ZENODO_RECORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_name(value: str) -> str:
    value = value.strip().lower().replace("/", "_").replace(".", "_")
    return re.sub(r"[^a-z0-9_]+", "_", value).strip("_")


def _coordinate(values: pd.Series) -> pd.Series:
    """Convert signed degrees/minutes (DDMM.mmmm) to decimal degrees."""
    value = pd.to_numeric(values, errors="coerce")
    sign = np.sign(value)
    absolute = value.abs()
    degrees = np.floor(absolute / 100.0)
    minutes = absolute - degrees * 100.0
    result = sign * (degrees + minutes / 60.0)
    return result.where(minutes < 60.0)


def _read_tagged(path: Path) -> tuple[list[str], list[list[str]], list[int]]:
    header: list[str] | None = None
    records: list[list[str]] = []
    line_numbers: list[int] = []
    with path.open(encoding="latin-1", errors="strict", newline="") as stream:
        for number, line in enumerate(stream, 1):
            fields = line.rstrip("\r\n").split(",")
            tag = fields[0].lstrip("@").strip()
            if tag == "NAME":
                if header is not None and fields[1:] != header:
                    raise ParseError(f"{path}:{number}: schema changed within file")
                header = fields[1:]
            elif tag == "DATA":
                if header is None:
                    raise ParseError(f"{path}:{number}: @DATA appears before @NAME")
                row = fields[1:]
                if len(row) != len(header):
                    raise ParseError(
                        f"{path}:{number}: expected {len(header)} fields, found {len(row)}"
                    )
                records.append(row)
                line_numbers.append(number)
    if header is None:
        raise ParseError(f"{path}: no @NAME record")
    if not records:
        raise ParseError(f"{path}: no @DATA records")
    return header, records, line_numbers


def read_log_file(path: str | Path, *, timezone: str = "UTC") -> xr.Dataset:
    """Read one OceanPack log without dropping any data records.

    Parameters
    ----------
    path:
        File containing ``@NAME`` and ``@DATA`` tagged CSV records.
    timezone:
        IANA timezone used by the logger. Timestamps are converted to UTC and
        stored as timezone-naive ``datetime64[ns]`` values.
    """
    path = Path(path).resolve()
    logger.info("Reading log {}", path)
    header, rows, lines = _read_tagged(path)
    names = [
        "status" if item == "Status" else "sampling_phase" if item == "STATUS" else _safe_name(item)
        for item in header
    ]
    # The logger exposes two case-distinct status fields.
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        count = seen.get(name, 0)
        seen[name] = count + 1
        unique.append(name if count == 0 else f"{name}_{count + 1}")
    frame = pd.DataFrame(rows, columns=unique)

    if not {"date", "time"}.issubset(frame):
        raise ParseError(f"{path}: @NAME must include DATE and TIME")
    timestamp = pd.to_datetime(frame["date"] + " " + frame["time"], errors="coerce")
    if "frac" in frame:
        millis = pd.to_numeric(frame["frac"], errors="coerce").fillna(0)
        timestamp += pd.to_timedelta(millis, unit="ms")
    try:
        localized = timestamp.dt.tz_localize(timezone, nonexistent="NaT", ambiguous="NaT")
    except (TypeError, ValueError, KeyError) as exc:
        raise ParseError(f"invalid input timezone {timezone!r}: {exc}") from exc
    utc = localized.dt.tz_convert("UTC").dt.tz_localize(None)

    data: dict[str, tuple[str, np.ndarray]] = {}
    for name in unique:
        if name in {"date", "time"}:
            continue
        values = frame[name]
        numeric = pd.to_numeric(values, errors="coerce")
        nonempty = values.str.strip().ne("")
        if nonempty.any() and numeric[nonempty].notna().all():
            data[f"raw_{name}"] = ("time", numeric.to_numpy(dtype=float))
        else:
            data[f"raw_{name}"] = ("time", values.to_numpy(dtype=str))

    n = len(frame)
    latitude = frame.get("latitude", pd.Series(np.nan, index=frame.index))
    longitude = frame.get("longitude", pd.Series(np.nan, index=frame.index))
    qc = np.zeros(n, dtype="uint16")
    qc[pd.isna(utc).to_numpy()] |= int(QCFlag.INVALID_TIME)
    lat = _coordinate(latitude).to_numpy(dtype=float)
    lon = _coordinate(longitude).to_numpy(dtype=float)
    bad_position = (
        ~np.isfinite(lat)
        | ~np.isfinite(lon)
        | (np.abs(lat) > 90)
        | (np.abs(lon) > 180)
        | ((lat == 0) & (lon == 0))
    )
    qc[bad_position] |= int(QCFlag.INVALID_POSITION)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    data.update(
        lat=("time", lat),
        lon=("time", lon),
        source_file=("time", np.full(n, path.name, dtype=f"U{len(path.name)}")),
        source_line=("time", np.asarray(lines, dtype="int32")),
        qc_flag=("time", qc),
    )
    ds = xr.Dataset(data, coords={"time": utc.to_numpy(dtype="datetime64[ns]")})
    ds.lat.attrs.update(standard_name="latitude", units="degrees_north")
    ds.lon.attrs.update(standard_name="longitude", units="degrees_east")
    ds.source_file.attrs["description"] = "basename of immutable source log"
    ds.attrs.update(source_path=str(path), source_sha256=digest, processing_history="ingest")
    attach_qc_metadata(ds.qc_flag)
    logger.success("Read {} observations from {}", n, path.name)
    return ds


def _resolve_logs(source: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(source, (str, Path)):
        text = str(source)
        path = Path(text)
        if path.is_dir():
            paths = list(path.glob("*.log"))
        elif any(char in text for char in "*?["):
            paths = [Path(item) for item in glob.glob(text)]
        else:
            paths = [path]
    else:
        paths = [Path(item) for item in source]
    return sorted((path.resolve() for path in paths), key=lambda item: str(item))


def _zenodo_record(repository: str) -> tuple[str, str]:
    """Return the API origin and record id named by a Zenodo reference."""
    reference = repository.strip().rstrip("/")
    if not reference:
        raise ZenodoError("inputs.repository must name a Zenodo record")
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
    doi = _ZENODO_DOI_RE.fullmatch(reference.removeprefix("doi:"))
    if doi:
        origin = ZENODO_SANDBOX_URL if doi.group("prefix") == "5072" else ZENODO_URL
        record_id = doi.group("record")
        if not _ZENODO_RECORD_RE.fullmatch(record_id):
            raise ZenodoError(f"invalid Zenodo record id: {record_id!r}")
        return origin, record_id
    if _ZENODO_RECORD_RE.fullmatch(reference) and reference not in {".", ".."}:
        return ZENODO_URL, reference
    raise ZenodoError(f"invalid Zenodo repository reference: {repository}")


def _zenodo_file_matches(path: Path, entry: object) -> bool:
    """Check a cached file against the size and checksum published by Zenodo."""
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


def fetch_zenodo_logs(
    repository: str,
    pattern: str,
    cache_dir: str | Path,
    *,
    session: requests.Session | None = None,
) -> list[Path]:
    """Download the log files selected from a public Zenodo record.

    Downloads are kept under a record-specific cache directory and reused when
    their Zenodo-reported size and checksum still match. The returned list
    contains only files present in the current record, so removed remote files
    cannot leak into later campaign runs through the cache.
    """
    origin, record_id = _zenodo_record(repository)
    client = session or requests.Session()
    record_url = f"{origin}/api/records/{record_id}"
    logger.info("Reading Zenodo record {}", record_url)
    try:
        response = client.get(record_url, timeout=60)
        response.raise_for_status()
        record = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ZenodoError(f"could not read Zenodo repository {repository}: {exc}") from exc

    entries = record.get("files", {}).get("entries", {})
    if not isinstance(entries, dict):
        raise ZenodoError(f"Zenodo repository {repository} returned an invalid file listing")
    remote_pattern = pattern.removeprefix("./")
    selected = []
    for key, entry in entries.items():
        name = str(key)
        if fnmatch.fnmatch(name, remote_pattern) or fnmatch.fnmatch(
            Path(name).name, remote_pattern
        ):
            selected.append((name, entry))
    if not selected:
        raise FileNotFoundError(f"no Zenodo files match {pattern!r} in {repository}")

    destination = Path(cache_dir).resolve() / "zenodo" / record_id
    destination.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for key, entry in sorted(selected):
        if Path(key).name != key:
            raise ZenodoError(f"Zenodo log key must be a plain filename: {key!r}")
        target = destination / key
        size = entry.get("size") if isinstance(entry, dict) else None
        if _zenodo_file_matches(target, entry):
            logger.info("Using cached Zenodo file {}", target)
            paths.append(target)
            continue
        content_url = entry.get("links", {}).get("content") if isinstance(entry, dict) else None
        if not content_url:
            content_url = f"{record_url}/files/{key}/content"
        temporary = target.with_suffix(target.suffix + ".part")
        try:
            with client.get(str(content_url), stream=True, timeout=120) as download:
                download.raise_for_status()
                with temporary.open("wb") as stream:
                    for chunk in download.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            stream.write(chunk)
            if size is not None and temporary.stat().st_size != int(size):
                raise ZenodoError(
                    f"Zenodo file {key} has {temporary.stat().st_size} bytes; expected {size}"
                )
            if not _zenodo_file_matches(temporary, entry):
                raise ZenodoError(f"Zenodo file {key} failed checksum verification")
            temporary.replace(target)
        except ZenodoError:
            temporary.unlink(missing_ok=True)
            raise
        except (requests.RequestException, OSError) as exc:
            temporary.unlink(missing_ok=True)
            raise ZenodoError(f"could not download Zenodo file {key}: {exc}") from exc
        logger.info("Downloaded Zenodo file {}", target)
        paths.append(target)
    return paths


def _normalise_raw_object_variables(ds: xr.Dataset) -> list[str]:
    """Make raw fields with cross-file type drift safe for serialization.

    A field can be numeric in one log and contain a textual missing-value
    marker in another. Xarray represents the merged values as ``object``,
    which NetCDF cannot encode. Text is the lossless common representation;
    canonical numeric variables are derived separately during ingestion.
    """
    promoted: list[str] = []
    for name, variable in ds.data_vars.items():
        if not name.startswith("raw_") or variable.dtype.kind != "O":
            continue
        values = np.asarray(
            ["" if pd.isna(value) else str(value) for value in variable.values.ravel()],
            dtype=str,
        ).reshape(variable.shape)
        ds[name] = xr.DataArray(values, dims=variable.dims, attrs=variable.attrs)
        promoted.append(name)
    return promoted


def read_campaign(
    source: str | Path | Iterable[str | Path], *, timezone: str = "UTC"
) -> xr.Dataset:
    """Read and deterministically merge all logs in a campaign."""
    paths = _resolve_logs(source)
    if not paths:
        raise FileNotFoundError(f"no .log files found in {source}")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(missing[0])
    datasets = [read_log_file(path, timezone=timezone) for path in paths]
    merged = xr.concat(datasets, dim="time", join="outer", compat="no_conflicts")
    promoted = _normalise_raw_object_variables(merged)
    if promoted:
        logger.warning(
            "Preserving raw fields with inconsistent cross-file types as text: {}",
            ", ".join(promoted),
        )
    order = np.argsort(merged.time.values, kind="stable")
    merged = merged.isel(time=order)
    valid_time = ~pd.isna(merged.time.values)
    duplicates = int(pd.Index(merged.time.values[valid_time]).duplicated(keep=False).sum())
    merged.attrs.update(
        campaign_source=str(Path(paths[0]).parent),
        source_file_count=len(paths),
        duplicate_timestamp_rows=duplicates,
        processing_history="ingest; stable merge by UTC time, source path, source line",
    )
    # concat may widen integer QC; restore the contract.
    merged["qc_flag"] = merged.qc_flag.fillna(0).astype("uint16")
    attach_qc_metadata(merged.qc_flag)
    validate_dataset(merged)
    logger.success("Merged {} logs into {} observations", len(paths), merged.sizes["time"])
    return merged


read_expedition = read_campaign
