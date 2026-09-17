import json

import numpy as np
import pytest
import xarray as xr
from loguru import logger

from yacht_co2.manifest import load_manifest
from yacht_co2.report import summarise, write_report
from yacht_co2.schema import QCFlag


def dataset(n=6):
    time = np.array(
        ["2023-07-24T00:00", "2023-07-24T00:01", "2023-07-24T00:02"]
        + ["2023-07-24T01:00", "2023-07-24T01:01", "2023-07-24T01:02"],
        dtype="datetime64[ns]",
    )[:n]
    flags = np.zeros(n, dtype="uint16")
    flags[1] |= int(QCFlag.PHYSICAL_RANGE)
    flags[1] |= int(QCFlag.FLOW)
    flags[2] |= int(QCFlag.INVALID_POSITION)
    lat = np.full(n, 50.0)
    lon = np.full(n, -5.0)
    lat[2] = np.nan
    lon[2] = np.nan
    pco2 = np.full(n, 400.0)
    return xr.Dataset(
        {
            "lat": ("time", lat),
            "lon": ("time", lon),
            "source_file": ("time", ["a.log", "a.log", "a.log", "b.log", "b.log", "b.log"][:n]),
            "qc_flag": ("time", flags),
            "pco2_seawater": ("time", pco2),
            "raw_co2": ("time", np.full(n, 390.0)),
        },
        coords={"time": time},
        attrs={"schema_version": "1.0.0", "code_sha256": "abc", "campaign": "Fastnet 2023"},
    )


def test_summary_captures_extent_files_and_gap_statistics():
    summary = summarise(dataset())
    temporal = summary["temporal"]

    assert temporal["start"] == "2023-07-24T00:00:00"
    assert temporal["end"] == "2023-07-24T01:02:00"
    assert temporal["records"] == 6
    # One 58-minute gap between the two bursts; the 1-minute steps are not gaps.
    assert temporal["gap_count"] == 1
    assert temporal["gap_minutes"] == pytest.approx(58.0)
    assert temporal["coverage_percent"] == pytest.approx(6.5, abs=0.1)
    assert temporal["median_interval_seconds"] == pytest.approx(60.0)
    assert summary["files"] == [
        {"name": "a.log", "records": 3},
        {"name": "b.log", "records": 3},
    ]


def test_bounding_box_excludes_positions_flagged_invalid():
    ds = dataset()
    ds["lat"] = ("time", np.where(np.isnan(ds.lat.values), 89.0, ds.lat.values))
    ds["lon"] = ("time", np.where(np.isnan(ds.lon.values), 179.0, ds.lon.values))

    spatial = summarise(ds)["spatial"]

    assert spatial["positions"] == 5
    assert spatial["latitude_max"] == 50.0
    assert spatial["longitude_max"] == -5.0


def test_qc_counts_are_per_bit_and_may_overlap():
    quality = summarise(dataset())["quality"]

    assert quality["total_records"] == 6
    assert quality["good_records"] == 4
    assert quality["flagged_records"] == 2
    assert quality["flag_counts"] == {"invalid_position": 1, "flow": 1, "physical_range": 1}
    # Flags overlap on one record, so the per-bit counts exceed flagged_records.
    assert sum(quality["flag_counts"].values()) > quality["flagged_records"]


def _manifest_with_phases(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        "campaign:\n  name: Fastnet 2023\ninputs:\n  logs: '*.log'\nphases:\n  analysis: [5]\n"
    )
    return path


def test_variable_inventory_omits_raw_columns():
    names = [item["name"] for item in summarise(dataset())["variables"]]

    assert names == ["pco2_seawater"]


def test_variable_inventory_keeps_temperature_and_salinity():
    """They are logged raw, but they are the seawater state fCO2 is derived at."""
    ds = dataset()
    ds["raw_watertemp"] = ("time", np.full(6, 14.0), {"units": "degC"})
    ds["raw_salinity"] = ("time", np.full(6, 35.0))

    entries = {item["name"]: item for item in summarise(ds)["variables"]}

    assert set(entries) == {"pco2_seawater", "raw_watertemp", "raw_salinity"}
    assert entries["raw_watertemp"]["units"] == "degC"
    assert entries["raw_salinity"]["mean"] == 35.0
    # Other instrument diagnostics stay out of the summary.
    assert "raw_co2" not in entries


def test_phase_tally_counts_every_sampling_phase():
    """Flag counts say how much QC excluded; the tally says what it was."""
    ds = dataset()
    ds["raw_sampling_phase"] = ("time", np.array([5.0, 5.0, 5.0, 5.0, 2.0, np.nan]))

    phases = summarise(ds)["phases"]

    assert [item["code"] for item in phases] == [None, 2, 5]
    assert [item["records"] for item in phases] == [1, 1, 4]
    # Records 1 and 2 are flagged for range, flow and position, not for phase.
    assert [item["good_records"] for item in phases] == [1, 1, 2]
    assert phases[-1]["percent"] == pytest.approx(66.7)
    # Without a manifest naming the roles, a phase is numbered, not lumped.
    assert [item["label"] for item in phases] == ["Unrecorded", "Phase 2", "Phase 5"]


def test_phase_tally_reports_mean_co2_per_phase():
    """A zero phase reading near zero is what says the calibration ran."""
    ds = dataset()
    ds["raw_sampling_phase"] = ("time", np.array([5.0, 5.0, 5.0, 5.0, 2.0, 2.0]))
    ds["raw_co2"] = ("time", np.array([400.0, 410.0, 390.0, 400.0, 1.0, 3.0]), {"units": "ppm"})

    zero, seawater = summarise(ds)["phases"]

    assert zero["code"] == 2
    assert zero["co2_variable"] == "raw_co2"
    assert zero["co2_units"] == "ppm"
    assert zero["co2_mean"] == 2.0
    assert zero["co2_records"] == 2
    assert seawater["co2_mean"] == 400.0
    assert seawater["co2_std"] == pytest.approx(7.07, abs=0.01)


def test_phase_co2_mean_ignores_qc_flags_and_missing_readings():
    """QC flags a zero phase for being out of seawater range, which is the point."""
    ds = dataset()
    ds["raw_sampling_phase"] = ("time", np.full(6, 2.0))
    # Every record in this phase is flagged, and one was never measured.
    ds["qc_flag"] = ("time", np.full(6, int(QCFlag.PHYSICAL_RANGE), dtype="uint16"))
    ds["raw_co2"] = ("time", np.array([2.0, 4.0, np.nan, 2.0, 4.0, 2.0]))

    phase = summarise(ds)["phases"][0]

    assert phase["good_records"] == 0
    assert phase["co2_records"] == 5
    assert phase["co2_mean"] == 2.8


def test_phase_tally_reports_no_co2_when_the_track_holds_none():
    ds = dataset().drop_vars("raw_co2")
    ds["raw_sampling_phase"] = ("time", np.full(6, 5.0))

    phase = summarise(ds)["phases"][0]

    assert phase["co2_variable"] is None
    assert phase["co2_mean"] is None


def test_phase_tally_takes_its_names_from_the_manifest(tmp_path):
    ds = dataset()
    ds["raw_sampling_phase"] = ("time", np.full(6, 5.0))
    manifest = load_manifest(_manifest_with_phases(tmp_path))

    labels = [item["label"] for item in summarise(ds, manifest=manifest)["phases"]]

    assert labels == ["Seawater"]


def test_phase_tally_is_absent_when_the_logs_held_no_phase():
    assert summarise(dataset())["phases"] == []


def test_variable_ranges_exclude_qc_flagged_records():
    ds = dataset()
    values = ds.pco2_seawater.values.copy()
    values[1] = 9999.0  # already flagged physical_range
    ds["pco2_seawater"] = ("time", values)

    entry = summarise(ds)["variables"][0]

    assert entry["valid"] == 6
    assert entry["good"] == 4
    assert entry["max"] == 400.0


def test_platform_defaults_fill_the_identity_table():
    summary = summarise(dataset(), platform={"vessel_name": "YOROSHIKU", "co2_sensor": "LI850"})

    assert summary["campaign"]["vessel_name"] == "YOROSHIKU"
    assert summary["campaign"]["co2_sensor"] == "LI850"


def test_manifest_overrides_a_platform_default(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        "campaign:\n  name: Fastnet 2023\n  co2_sensor: LI7815\ninputs:\n  logs: '*.log'\n"
    )
    manifest = load_manifest(path)

    summary = summarise(
        dataset(),
        manifest=manifest,
        platform={"vessel_name": "YOROSHIKU", "co2_sensor": "LI850"},
    )

    assert summary["campaign"]["co2_sensor"] == "LI7815"
    assert summary["campaign"]["vessel_name"] == "YOROSHIKU"


def test_summary_is_json_serialisable_without_numpy_scalars():
    text = json.dumps(summarise(dataset()))

    assert "pco2_seawater" in text


def test_write_report_writes_the_json_report(tmp_path):
    summary = summarise(dataset())

    messages = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))
    try:
        paths = write_report(summary, tmp_path)
    finally:
        logger.remove(sink_id)

    assert json.loads(paths["report_json"].read_text())["quality"]["good_records"] == 4
    assert messages == [f"Wrote JSON report to {tmp_path / 'report.json'}"]
    # The report is data, so nothing renders it to Markdown any more.
    assert set(paths) == {"report_json"}
    assert not (tmp_path / "REPORT.md").exists()


def test_empty_track_summarises_without_raising():
    empty = xr.Dataset(
        {
            "lat": ("time", np.array([], dtype=float)),
            "lon": ("time", np.array([], dtype=float)),
            "source_file": ("time", np.array([], dtype=str)),
            "qc_flag": ("time", np.array([], dtype="uint16")),
        },
        coords={"time": np.array([], dtype="datetime64[ns]")},
    )

    summary = summarise(empty)

    assert summary["temporal"]["records"] == 0
    assert summary["spatial"]["positions"] == 0
    assert summary["quality"]["good_percent"] is None
