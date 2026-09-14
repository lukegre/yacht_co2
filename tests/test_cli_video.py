import numpy as np
import xarray as xr
from loguru import logger
from typer.testing import CliRunner

from yacht_co2.cli import app
from yacht_co2.errors import ZenodoError
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
    zenodo.write_text("campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n")

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
    fetched = {}

    def fake_fetch(repository, pattern, cache, **kwargs):
        fetched.update(repository=repository, pattern=pattern)
        return [tmp_path / "one.log"]

    monkeypatch.setattr("yacht_co2.pipeline.fetch_zenodo_logs", fake_fetch)

    result = CliRunner().invoke(
        app,
        ["pipeline", "--campaign", "Fastnet", "--campaign-date", "2023-06"],
    )

    assert result.exit_code == 0, result.output
    assert upload_call == {
        "folder": tmp_path,
        "campaign": "Fastnet",
        "campaign_date": "2023-06",
        "config": None,
        "publish": True,
    }
    # The logs are read back from the archived record, not from the folder.
    assert fetched == {"repository": "10.5281/zenodo.12345", "pattern": "./*.log"}
    assert (tmp_path / "manifest.yaml").is_file()
    assert (tmp_path / "track.csv").is_file()
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "REPORT.md").is_file()
    site = (tmp_path / "fastnet-2023-06.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in site
    assert "window.YACHT_REPORT=" in site


def test_cli_pipeline_takes_its_campaign_from_a_config_elsewhere(tmp_path, monkeypatch):
    """``--config`` selects the folder and names the campaign without options."""
    folder = tmp_path / "221205DATA0"
    folder.mkdir()
    (folder / "one.log").write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    config = folder / "zenodo.yaml"
    config.write_text(
        "campaign: Route du Rhum\ncampaign_date: 2022-12\ndoi: 10.5281/zenodo.12345\n"
    )
    working = tmp_path / "elsewhere"
    working.mkdir()
    monkeypatch.chdir(working)
    upload_call = {}

    def fake_upload(folder, **kwargs):
        upload_call.update(folder=folder, **kwargs)
        return {"status": "pending_review", "record_id": "12345"}

    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", fake_upload)
    monkeypatch.setattr(
        "yacht_co2.pipeline.fetch_zenodo_logs",
        lambda repository, pattern, cache, **kwargs: [folder / "one.log"],
    )

    result = CliRunner().invoke(app, ["pipeline", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert upload_call == {
        "folder": folder,
        "campaign": None,
        "campaign_date": None,
        "config": config,
        "publish": True,
    }
    # Every product lands beside the configuration, not in the invocation
    # directory, and is named from the campaign the file declares.
    assert (folder / "manifest.yaml").is_file()
    assert (folder / "REPORT.md").is_file()
    assert (
        "<title>Route du Rhum (2022-12)</title>"
        in (folder / "route-du-rhum-2022-12.html").read_text()
    )
    assert not list(working.iterdir())


def test_cli_pipeline_falls_back_to_local_logs_while_a_record_is_unreadable(tmp_path, monkeypatch):
    """A record awaiting review is not public, so the uploaded logs stand in."""
    (tmp_path / "one.log").write_text(
        "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
        "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
        "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
    )
    (tmp_path / "zenodo.yaml").write_text(
        "campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", lambda folder, **kwargs: {})

    def refuse(repository, pattern, cache, **kwargs):
        raise ZenodoError(f"could not read Zenodo repository {repository}: HTTP 404")

    monkeypatch.setattr("yacht_co2.pipeline.fetch_zenodo_logs", refuse)

    result = CliRunner().invoke(app, ["pipeline"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "track.csv").is_file()
    assert (tmp_path / "fastnet-2023-06.html").is_file()
    # The DOI stays in the manifest even though this run could not read it.
    assert "10.5281/zenodo.12345" in (tmp_path / "manifest.yaml").read_text()


def test_cli_pipeline_says_when_a_config_does_not_name_the_campaign(tmp_path, monkeypatch):
    config = tmp_path / "zenodo.yaml"
    config.write_text("doi: 10.5281/zenodo.12345\n")
    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", lambda folder, **kwargs: {})

    result = CliRunner().invoke(app, ["pipeline", "--config", str(config)])

    assert result.exit_code != 0
    # Rich wraps the message around the path and frames it, so the borders are
    # dropped and the whitespace normalised before the text is compared.
    rendered = " ".join(result.output.replace("\u2502", " ").split())
    assert "does not name the campaign" in rendered
    assert "pass --campaign and --campaign-date" in rendered


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
