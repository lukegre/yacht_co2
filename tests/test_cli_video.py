import numpy as np
import xarray as xr
from loguru import logger
from typer.testing import CliRunner

from yacht_co2.cli import app
from yacht_co2.video import render_video


def video_dataset():
    time = np.array(["2023-01-01T00", "2023-01-01T01", "2023-01-01T02"], dtype="datetime64[ns]")
    return xr.Dataset(
        {
            "lat": ("time", [50.0, 50.1, 50.2]),
            "lon": ("time", [-5.0, -4.9, -4.8]),
            "pco2_seawater": ("time", [400.0, 405.0, 410.0]),
            "source_file": ("time", ["a", "a", "a"]),
            "qc_flag": ("time", np.zeros(3, dtype="uint16")),
        },
        coords={"time": time},
    )


def test_video_is_h264_and_has_expected_frames(tmp_path):
    path = render_video(video_dataset(), tmp_path / "test.mp4", fps=2)
    assert path.exists() and path.stat().st_size > 1000


def test_cli_help_validate_and_site(tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("campaign: {name: Test}\ninputs: {logs: '*.log'}\n")
    result = runner.invoke(app, ["validate", str(manifest)])
    assert result.exit_code == 0
    assert "valid: Test" in result.stdout
    source = tmp_path / "track.nc"
    video_dataset().to_netcdf(source)
    result = runner.invoke(app, ["site", str(source), "--output", str(tmp_path / "site")])
    assert result.exit_code == 0


def test_cli_build_manifest_from_zenodo(tmp_path):
    zenodo = tmp_path / "zenodo.yaml"
    zenodo.write_text(
        "campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n"
    )

    result = CliRunner().invoke(app, ["build-manifest", str(zenodo)])

    assert result.exit_code == 0
    assert (tmp_path / "manifest.yaml").is_file()
    assert str(tmp_path / "manifest.yaml") in result.stdout


def test_cli_pipeline_uploads_and_builds_local_artifacts(tmp_path, monkeypatch):
    (tmp_path / "one.log").write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    monkeypatch.chdir(tmp_path)
    upload_call = {}

    def fake_upload(folder, **kwargs):
        upload_call.update(folder=folder, **kwargs)
        (folder / "zenodo.yaml").write_text(
            "campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n"
        )
        return {"status": "pending_review", "record_id": "12345"}

    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", fake_upload)

    result = CliRunner().invoke(
        app,
        ["pipeline", "--campaign", "Fastnet", "--campaign-date", "2023-06"],
    )

    assert result.exit_code == 0, result.output
    assert upload_call == {
        "folder": tmp_path,
        "campaign": "Fastnet",
        "campaign_date": "2023-06",
        "publish": True,
    }
    assert (tmp_path / "manifest.yaml").is_file()
    assert (tmp_path / "track.csv").is_file()
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "REPORT.md").is_file()
    site = (tmp_path / "fastnet-2023-06.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in site
    assert "window.YACHT_REPORT=" in site


def test_cli_process_reports_the_resolved_output_path(tmp_path, monkeypatch):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "one.log").write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    manifest = campaign / "manifest.yaml"
    manifest.write_text(
        "campaign: {name: Test}\n"
        "inputs: {logs: '*.log', timezone: UTC}\n"
        "calibration: {method: instrument}\n"
        "qc: {analysis_phases: [5]}\n"
    )
    invocation_dir = tmp_path / "invocation"
    invocation_dir.mkdir()
    monkeypatch.chdir(invocation_dir)

    messages = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))
    try:
        result = CliRunner().invoke(app, ["process", str(manifest)])
    finally:
        logger.remove(sink_id)

    output = invocation_dir / "processed.nc"
    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert str(output) in result.output
    assert f"Saved processed dataset to {output}" in messages


def test_cli_report_labels_each_output_file(tmp_path):
    source = tmp_path / "processed.nc"
    video_dataset().to_netcdf(source)
    output = tmp_path / "report"

    result = CliRunner().invoke(app, ["report", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert f"JSON report: {output / 'report.json'}" in result.stdout
    assert f"Markdown report: {output / 'REPORT.md'}" in result.stdout
