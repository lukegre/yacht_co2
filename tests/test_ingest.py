import hashlib
from pathlib import Path

import numpy as np
import pytest

from yacht_co2.errors import ParseError
from yacht_co2.ingest import fetch_zenodo_logs, read_campaign, read_log_file

HEADER = "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"


class FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self.json_data = json_data
        self.content = content

    def json(self):
        return self.json_data

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSession:
    def __init__(self, record, files):
        self.record = record
        self.files = files
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/api/records/12345"):
            return FakeResponse(json_data=self.record)
        return FakeResponse(content=self.files[url])


def write_log(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "".join(rows), encoding="latin-1")
    return path


def test_read_preserves_raw_and_converts_coordinates(tmp_path):
    path = write_log(
        tmp_path / "a.log",
        ["@DATA,2023-01-01,12:00:00,0500,400,10,20,1013.25,5119.2,-0940.3,1,1,18,35,0x1,5\n"],
    )
    ds = read_log_file(path)
    assert ds.sizes["time"] == 1
    assert ds.raw_co2.item() == 400
    assert ds.raw_sampling_phase.item() == 5
    assert ds.time.values[0] == np.datetime64("2023-01-01T12:00:00.500")
    assert ds.lat.item() == pytest.approx(51 + 19.2 / 60)
    assert ds.lon.item() == pytest.approx(-(9 + 40.3 / 60))


def test_malformed_row_raises(tmp_path):
    path = write_log(tmp_path / "bad.log", ["@DATA,2023-01-01,12:00:00\n"])
    with pytest.raises(ParseError, match="expected"):
        read_log_file(path)


def test_merge_is_deterministic_and_reports_duplicates(tmp_path):
    row = "@DATA,2023-01-01,12:00:00,0,400,10,20,1013,5000,00100,1,1,18,35,0,5\n"
    write_log(tmp_path / "b.log", [row])
    write_log(tmp_path / "a.log", [row])
    ds = read_campaign(tmp_path)
    assert list(ds.source_file.values) == ["a.log", "b.log"]
    assert ds.attrs["duplicate_timestamp_rows"] == 2


def test_merge_promotes_inconsistent_raw_fields_to_serializable_text(tmp_path):
    numeric = "@DATA,2023-01-01,12:00:00,0,400,10,20,1013,5000,00100,1,1,18,35,0,5\n"
    invalid = "@DATA,2023-01-02,12:00:00,0,400,10,20,1013,/,/,1,1,18,35,0,5\n"
    write_log(tmp_path / "numeric.log", [numeric])
    write_log(tmp_path / "invalid.log", [invalid])

    ds = read_campaign(tmp_path)

    assert ds.raw_latitude.dtype.kind == "U"
    assert ds.raw_latitude.sel(time="2023-01-02").item() == "/"
    ds.to_netcdf(tmp_path / "merged.nc", engine="h5netcdf")


def test_fetch_zenodo_logs_selects_and_caches_record_files(tmp_path):
    content = (
        HEADER + "@DATA,2023-01-01,12:00:00,0,400,10,20,1013,5000,00100,1,1,18,35,0,5\n"
    ).encode("latin-1")
    url = "https://zenodo.org/api/records/12345/files/a.log/content"
    record = {
        "files": {
            "entries": {
                "a.log": {
                    "size": len(content),
                    "checksum": f"md5:{hashlib.md5(content, usedforsecurity=False).hexdigest()}",
                    "links": {"content": url},
                },
                "notes.txt": {"size": 1, "links": {"content": "unused"}},
            }
        }
    }
    session = FakeSession(record, {url: content})

    paths = fetch_zenodo_logs("10.5281/zenodo.12345", "./*.log", tmp_path, session=session)
    assert [path.name for path in paths] == ["a.log"]
    assert paths[0].read_bytes() == content
    assert paths[0].parent == tmp_path / "zenodo" / "12345"

    assert (
        fetch_zenodo_logs("https://zenodo.org/records/12345", "*.log", tmp_path, session=session)
        == paths
    )
    assert [url for url, _ in session.calls].count(url) == 1


def test_fetch_zenodo_logs_reads_a_published_record_listing(tmp_path):
    """A published record serves ``files`` as a list, not nested in ``entries``."""
    content = (
        HEADER + "@DATA,2023-01-01,12:00:00,0,400,10,20,1013,5000,00100,1,1,18,35,0,5\n"
    ).encode("latin-1")
    url = "https://zenodo.org/api/records/12345/files/a.log/content"
    record = {
        "files": [
            {
                "key": "a.log",
                "size": len(content),
                "checksum": f"md5:{hashlib.md5(content, usedforsecurity=False).hexdigest()}",
                # A published entry names its content under ``self``, so the
                # caller falls back to the conventional content URL.
                "links": {"self": url},
            },
            {"key": "notes.txt", "size": 1, "links": {"self": "unused"}},
        ]
    }
    session = FakeSession(record, {url: content})

    paths = fetch_zenodo_logs("10.5281/zenodo.12345", "./*.log", tmp_path, session=session)

    assert [path.name for path in paths] == ["a.log"]
    assert paths[0].read_bytes() == content


def test_fetch_zenodo_logs_rejects_unsafe_record_id(tmp_path):
    from yacht_co2.errors import ZenodoError

    with pytest.raises(ZenodoError, match="invalid Zenodo record id"):
        fetch_zenodo_logs("https://zenodo.org/records/%2E%2E", "*.log", tmp_path)


def test_real_fastnet_count():
    path = Path(__file__).parents[1] / "data" / "2306_fastnet"
    if not path.exists():
        pytest.skip("repository data not present")
    ds = read_campaign(path)
    assert ds.sizes["time"] == 7983
    assert float(ds.lat.min()) == pytest.approx(48.698, abs=0.001)
    assert float(ds.lon.min()) == pytest.approx(-9.673, abs=0.001)
