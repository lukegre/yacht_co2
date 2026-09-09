import json

import numpy as np
import pytest
import xarray as xr

from yacht_co2.manifest import load_manifest
from yacht_co2.report import render_markdown, summarise, write_report
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
        attrs={"schema_version": "1.0.0", "code_sha256": "abc", "expedition": "Fastnet 2023"},
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


def test_variable_inventory_omits_raw_columns():
    names = [item["name"] for item in summarise(dataset())["variables"]]

    assert names == ["pco2_seawater"]


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

    assert summary["expedition"]["vessel_name"] == "YOROSHIKU"
    assert "| vessel_name | YOROSHIKU |" in render_markdown(summary)


def test_manifest_overrides_a_platform_default(tmp_path):
    path = tmp_path / "expedition.yaml"
    path.write_text(
        "expedition:\n  name: Fastnet 2023\n  co2_sensor: LI7815\ninputs:\n  logs: '*.log'\n"
    )
    manifest = load_manifest(path)

    summary = summarise(
        dataset(),
        manifest=manifest,
        platform={"vessel_name": "YOROSHIKU", "co2_sensor": "LI850"},
    )

    assert summary["expedition"]["co2_sensor"] == "LI7815"
    assert summary["expedition"]["vessel_name"] == "YOROSHIKU"


def test_summary_is_json_serialisable_without_numpy_scalars():
    text = json.dumps(summarise(dataset()))

    assert "pco2_seawater" in text


def test_write_report_emits_both_renderings(tmp_path):
    summary = summarise(dataset())

    paths = write_report(summary, tmp_path)

    assert json.loads(paths["report_json"].read_text())["quality"]["good_records"] == 4
    markdown = paths["report_markdown"].read_text()
    assert markdown.startswith("# Fastnet 2023")
    assert "## Quality control" in markdown
    assert "physical_range" in markdown


def test_markdown_handles_a_clean_dataset_with_no_flags():
    ds = dataset()
    ds["qc_flag"] = ("time", np.zeros(ds.sizes["time"], dtype="uint16"))

    markdown = render_markdown(summarise(ds))

    assert "No QC flags were raised." in markdown


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
