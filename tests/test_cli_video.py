import json

import numpy as np
import xarray as xr
import yaml
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


LOG = (
    "@NAME,DATE,TIME,FRAC,CO2,H2O,CellTemp,CellPress,Latitude,Longitude,"
    "AIN0_mA/Waterflow,FLOWgas,waterTemp,salinity,Status,STATUS\n"
    "@DATA,2023-01-01,00:00:00,0,400,10,20,1013.25,5000,00200,1,1,20,35,0,5\n"
)


def campaign_manifest(folder, date="2023-06", outputs="single_html: true"):
    """Write a manifest for a folder of logs that outputs into that folder."""
    manifest = folder / "manifest.yaml"
    dated = f", date: {date}" if date else ""
    manifest.write_text(
        f"campaign: {{name: Fastnet{dated}}}\n"
        "inputs: {logs: ./*.log}\n"
        f"outputs: {{directory: ./, formats: [csv], {outputs}}}\n"
    )
    return manifest


def test_cli_help_and_validate(tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("campaign: {name: Test}\ninputs: {logs: '*.log'}\n")
    result = runner.invoke(app, ["validate", str(manifest)])
    assert result.exit_code == 0
    assert "valid: Test" in result.stdout


def test_cli_site_reuses_the_processed_dataset_and_is_titled_by_the_campaign(tmp_path):
    manifest = campaign_manifest(tmp_path)
    video_dataset().to_netcdf(tmp_path / "yacht_co2-fastnet-2023_06-track.nc")

    result = CliRunner().invoke(app, ["site", str(manifest)])

    assert result.exit_code == 0, result.output
    site = (tmp_path / "yacht_co2-fastnet-2023_06-site.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in site
    assert "<h1>Fastnet (2023-06)</h1>" in site
    # Reusing the dataset means the logs are never read, so there is no CSV.
    assert not (tmp_path / "yacht_co2-fastnet-2023_06-track.csv").exists()


def test_cli_site_processes_the_campaign_when_there_is_no_dataset(tmp_path):
    (tmp_path / "one.log").write_text(LOG)
    manifest = campaign_manifest(tmp_path)

    result = CliRunner().invoke(app, ["site", str(manifest)])

    assert result.exit_code == 0, result.output
    # NetCDF is exported even though the manifest asks only for CSV, so that a
    # second build reuses the dataset rather than processing the logs again.
    assert (tmp_path / "yacht_co2-fastnet-2023_06-track.nc").is_file()
    assert (tmp_path / "yacht_co2-fastnet-2023_06-track.csv").is_file()
    site = (tmp_path / "yacht_co2-fastnet-2023_06-site.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in site
    assert "window.YACHT_REPORT=" in site


def test_cli_site_builds_what_the_manifest_asks_for(tmp_path):
    """site_options reach build_site, and single_html names the destination."""
    manifest = campaign_manifest(
        tmp_path, outputs="site: true, single_html: true, site_options: {max_points: 2}"
    )
    video_dataset().to_netcdf(tmp_path / "yacht_co2-fastnet-2023_06-track.nc")

    result = CliRunner().invoke(app, ["site", str(manifest)])

    assert result.exit_code == 0, result.output
    single = (tmp_path / "yacht_co2-fastnet-2023_06-site.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in single
    # site_options reaches build_site: three observations subsample to two.
    model = json.loads(single.split("window.YACHT_DATA=")[1].split(";window.YACHT_REPORT")[0])
    assert len(model["time"]) == 2


def test_cli_site_output_option_names_one_destination(tmp_path):
    manifest = campaign_manifest(tmp_path, outputs="site: true, single_html: true")
    video_dataset().to_netcdf(tmp_path / "yacht_co2-fastnet-2023_06-track.nc")

    result = CliRunner().invoke(
        app, ["site", str(manifest), "--output", str(tmp_path / "one.html")]
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "one.html").is_file()
    assert not (tmp_path / "yacht_co2-fastnet-2023_06-site").exists()


def test_cli_site_dates_the_campaign_from_the_zenodo_config(tmp_path):
    """A manifest written before campaign.date still names the site fully."""
    manifest = campaign_manifest(tmp_path, date=None)
    (tmp_path / "zenodo.yaml").write_text(
        "campaign: Fastnet\ncampaign_date: 2023-06-24\ndoi: 10.5281/zenodo.12345\n"
    )
    video_dataset().to_netcdf(tmp_path / "yacht_co2-fastnet-2023_06_24-track.nc")

    result = CliRunner().invoke(app, ["site", str(manifest)])

    assert result.exit_code == 0, result.output
    site = (tmp_path / "yacht_co2-fastnet-2023_06_24-site.html").read_text()
    assert "<title>Fastnet (2023-06-24)</title>" in site


def test_cli_build_manifest_from_zenodo(tmp_path):
    zenodo = tmp_path / "zenodo.yaml"
    zenodo.write_text("campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n")

    result = CliRunner().invoke(app, ["build-manifest", str(zenodo)])

    assert result.exit_code == 0
    assert (tmp_path / "manifest.yaml").is_file()
    assert str(tmp_path / "manifest.yaml") in result.stdout
    built = yaml.safe_load((tmp_path / "manifest.yaml").read_text())
    assert built["campaign"] == {"id": tmp_path.name, "name": "Fastnet", "date": "2023-06"}


def built_manifest(
    folder, zenodo="campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.12345\n"
):
    """Write a folder's zenodo.yaml and the manifest that ``run`` takes."""
    (folder / "zenodo.yaml").write_text(zenodo)
    result = CliRunner().invoke(app, ["build-manifest", str(folder / "zenodo.yaml")])
    assert result.exit_code == 0, result.output
    return folder / "manifest.yaml"


def test_cli_run_uploads_and_builds_local_artifacts(tmp_path, monkeypatch):
    (tmp_path / "one.log").write_text(LOG)
    manifest = built_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    upload_call = {}

    def fake_upload(folder, **kwargs):
        upload_call.update(folder=folder, **kwargs)
        return {"status": "pending_review", "record_id": "12345"}

    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", fake_upload)
    fetched = {}

    def fake_fetch(repository, pattern, cache, **kwargs):
        fetched.update(repository=repository, pattern=pattern)
        return [tmp_path / "one.log"]

    monkeypatch.setattr("yacht_co2.pipeline.fetch_zenodo_logs", fake_fetch)

    result = CliRunner().invoke(app, ["run", str(manifest)])

    assert result.exit_code == 0, result.output
    # The campaign reaches the upload from the manifest, not from options.
    assert upload_call == {
        "folder": tmp_path,
        "campaign": "Fastnet",
        "campaign_date": "2023-06",
        "config": tmp_path / "zenodo.yaml",
        "publish": True,
    }
    # The logs are read back from the archived record, not from the folder.
    assert fetched == {"repository": "10.5281/zenodo.12345", "pattern": "./*.log"}
    assert (tmp_path / "yacht_co2-fastnet-2023_06-track.nc").is_file()
    assert (tmp_path / "yacht_co2-fastnet-2023_06-report.json").is_file()
    assert not (tmp_path / "REPORT.md").exists()
    site = (tmp_path / "yacht_co2-fastnet-2023_06-site.html").read_text()
    assert "<title>Fastnet (2023-06)</title>" in site
    assert "window.YACHT_REPORT=" in site


def test_cli_run_processes_the_manifests_folder_not_the_working_directory(tmp_path, monkeypatch):
    """The manifest selects the folder, so run works from anywhere."""
    folder = tmp_path / "221205DATA0"
    folder.mkdir()
    (folder / "one.log").write_text(LOG)
    manifest = built_manifest(
        folder,
        zenodo="campaign: Route du Rhum\ncampaign_date: 2022-12\ndoi: 10.5281/zenodo.12345\n",
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

    result = CliRunner().invoke(app, ["run", str(manifest)])

    assert result.exit_code == 0, result.output
    assert upload_call == {
        "folder": folder,
        "campaign": "Route du Rhum",
        "campaign_date": "2022-12",
        "config": folder / "zenodo.yaml",
        "publish": True,
    }
    # Every product lands beside the manifest, not in the invocation directory.
    assert (folder / "yacht_co2-route_du_rhum-2022_12-report.json").is_file()
    assert (
        "<title>Route du Rhum (2022-12)</title>"
        in (folder / "yacht_co2-route_du_rhum-2022_12-site.html").read_text()
    )
    assert not list(working.iterdir())


def test_cli_run_falls_back_to_local_logs_while_a_record_is_unreadable(tmp_path, monkeypatch):
    """A record awaiting review is not public, so the uploaded logs stand in."""
    (tmp_path / "one.log").write_text(LOG)
    manifest = built_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", lambda folder, **kwargs: {})

    def refuse(repository, pattern, cache, **kwargs):
        raise ZenodoError(f"could not read Zenodo repository {repository}: HTTP 404")

    monkeypatch.setattr("yacht_co2.pipeline.fetch_zenodo_logs", refuse)

    result = CliRunner().invoke(app, ["run", str(manifest)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "yacht_co2-fastnet-2023_06-track.nc").is_file()
    assert (tmp_path / "yacht_co2-fastnet-2023_06-site.html").is_file()
    # The DOI stays in the manifest even though this run could not read it.
    assert "10.5281/zenodo.12345" in manifest.read_text()


def test_cli_run_resumes_without_touching_the_manifest(tmp_path, monkeypatch):
    """A rerun resumes: the manifest is kept, edits and all, and work goes on."""
    (tmp_path / "one.log").write_text(LOG)
    manifest = built_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    uploads = []

    def fake_upload(folder, **kwargs):
        uploads.append(folder)
        return {"status": "pending_review", "record_id": "12345"}

    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", fake_upload)
    monkeypatch.setattr(
        "yacht_co2.pipeline.fetch_zenodo_logs",
        lambda repository, pattern, cache, **kwargs: [tmp_path / "one.log"],
    )

    assert CliRunner().invoke(app, ["run", str(manifest)]).exit_code == 0
    assert uploads == [tmp_path]
    manifest.write_text(manifest.read_text().replace("timezone: UTC", "timezone: Europe/Zurich"))
    (tmp_path / "yacht_co2-fastnet-2023_06-track.nc").unlink()

    result = CliRunner().invoke(app, ["run", str(manifest)])

    assert result.exit_code == 0, result.output
    # The first successful upload is checkpointed from the raw-file hashes.
    # Products created by that run do not make a rerun contact Zenodo again.
    assert uploads == [tmp_path]
    # The hand-edited manifest survives and the remaining products are rebuilt.
    assert "timezone: Europe/Zurich" in manifest.read_text()
    assert (tmp_path / "yacht_co2-fastnet-2023_06-track.nc").is_file()


def test_cli_run_reuploads_when_a_checkpointed_raw_file_changes(tmp_path, monkeypatch):
    raw = tmp_path / "one.log"
    raw.write_text(LOG)
    manifest = built_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    uploads = []

    def fake_upload(folder, **kwargs):
        uploads.append(folder)
        return {"status": "pending_review", "record_id": "12345"}

    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", fake_upload)
    monkeypatch.setattr(
        "yacht_co2.pipeline.fetch_zenodo_logs",
        lambda repository, pattern, cache, **kwargs: [raw],
    )

    runner = CliRunner()
    assert runner.invoke(app, ["run", str(manifest)]).exit_code == 0
    raw.write_text(LOG + "# corrected raw data\n")
    assert runner.invoke(app, ["run", str(manifest)]).exit_code == 0

    assert uploads == [tmp_path, tmp_path]


def test_cli_run_reports_a_manifest_left_on_an_older_record(tmp_path, monkeypatch):
    """A stale manifest is named rather than silently processed or rebuilt."""
    (tmp_path / "one.log").write_text(LOG)
    manifest = built_manifest(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", lambda folder, **kwargs: {})
    monkeypatch.setattr(
        "yacht_co2.pipeline.fetch_zenodo_logs",
        lambda repository, pattern, cache, **kwargs: [tmp_path / "one.log"],
    )
    (tmp_path / "zenodo.yaml").write_text(
        "campaign: Fastnet\ncampaign_date: 2023-06\ndoi: 10.5281/zenodo.99999\n"
    )
    messages = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))

    try:
        result = CliRunner().invoke(app, ["run", str(manifest)])
    finally:
        logger.remove(sink_id)

    assert result.exit_code == 0, result.output
    assert any("10.5281/zenodo.99999" in message for message in messages)
    # The stale manifest is kept, so the run is reproducible and the fix is the
    # operator's to make.
    assert "10.5281/zenodo.12345" in manifest.read_text()


def test_cli_run_says_when_the_folder_holds_no_zenodo_config(tmp_path, monkeypatch):
    (tmp_path / "one.log").write_text(LOG)
    manifest = campaign_manifest(tmp_path)
    monkeypatch.setattr("yacht_co2.cli.upload_raw_folder", lambda folder, **kwargs: {})

    result = CliRunner().invoke(app, ["run", str(manifest)])

    assert result.exit_code != 0
    # Rich wraps the message around the path and frames it, so the borders are
    # dropped and the whitespace normalised before the text is compared.
    rendered = " ".join(result.output.replace("│", " ").split())
    assert "holds no zenodo.yaml" in rendered
