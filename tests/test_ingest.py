from pathlib import Path

import numpy as np
import pytest

from yacht_co2.errors import ParseError
from yacht_co2.ingest import read_expedition, read_log_file

HEADER = "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"


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
    ds = read_expedition(tmp_path)
    assert list(ds.source_file.values) == ["a.log", "b.log"]
    assert ds.attrs["duplicate_timestamp_rows"] == 2


def test_real_fastnet_count():
    path = Path(__file__).parents[1] / "data" / "2306_fastnet"
    if not path.exists():
        pytest.skip("repository data not present")
    ds = read_expedition(path)
    assert ds.sizes["time"] == 7983
    assert float(ds.lat.min()) == pytest.approx(48.698, abs=0.001)
    assert float(ds.lon.min()) == pytest.approx(-9.673, abs=0.001)
