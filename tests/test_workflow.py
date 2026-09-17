"""Reading how far a campaign folder has already been taken."""

from __future__ import annotations

import yaml

from yacht_co2.manifest import packaged_defaults
from yacht_co2.workflow import campaign_status, find_campaigns


def _campaign(folder, *, logs=1, archived=False, manifest=False, processed=False):
    """Build a folder in one of the states the procedure leaves behind."""
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(logs):
        (folder / f"23072{index}_000.log").write_text("raw\n", encoding="utf-8")
    if archived or manifest:
        document = {"campaign": "Fastnet Race", "campaign_date": "2023-07-24"}
        if archived:
            document |= {"doi": "10.5281/zenodo.12345", "submitted": "2023-08-01"}
        (folder / "zenodo.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    if manifest:
        document = yaml.safe_load(packaged_defaults().read_text(encoding="utf-8"))
        document["campaign"] = {
            "id": "fastnet",
            "name": "Fastnet Race",
            "date": "2023-07-24",
        }
        document["inputs"]["repository"] = "10.5281/zenodo.12345"
        (folder / "manifest.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )
    if processed:
        (folder / "yacht_co2-fastnet_race-2023_07_24-track.nc").write_bytes(b"")
        (folder / "yacht_co2-fastnet_race-2023_07_24-report.json").write_text("{}")
        (folder / "yacht_co2-fastnet_race-2023_07_24-site.html").write_text("<html></html>")
    return folder


def test_an_untouched_folder_has_only_its_logs(tmp_path):
    status = campaign_status(_campaign(tmp_path / "2306_fastnet", logs=3))
    assert len(status.logs) == 3
    assert not status.is_uploaded
    assert not status.has_manifest
    assert not status.is_processed
    # With nothing naming the campaign, the folder names itself.
    assert status.title == "2306_fastnet"


def test_an_archived_folder_reports_its_record(tmp_path):
    status = campaign_status(_campaign(tmp_path / "2306_fastnet", archived=True))
    assert status.is_uploaded
    assert status.is_published
    assert status.doi == "10.5281/zenodo.12345"
    assert status.title == "Fastnet Race (2023-07-24)"


def test_a_finished_folder_names_every_artifact(tmp_path):
    folder = _campaign(
        tmp_path / "2306_fastnet", archived=True, manifest=True, processed=True
    )
    status = campaign_status(folder)
    assert status.is_processed
    assert status.track == folder / "yacht_co2-fastnet_race-2023_07_24-track.nc"
    assert status.report == folder / "yacht_co2-fastnet_race-2023_07_24-report.json"
    assert status.site == folder / "yacht_co2-fastnet_race-2023_07_24-site.html"


def test_a_broken_manifest_is_reported_rather_than_raised(tmp_path):
    folder = _campaign(tmp_path / "2306_fastnet", archived=True)
    (folder / "manifest.yaml").write_text("campaign: {name: Fastnet}\n", encoding="utf-8")
    status = campaign_status(folder)
    assert status.has_manifest
    assert "inputs" in status.manifest_error
    assert not status.is_processed


def test_only_folders_holding_a_campaign_are_listed(tmp_path):
    root = tmp_path / "data"
    _campaign(root / "2306_fastnet")
    _campaign(root / "2307_rhum", archived=True, manifest=True)
    (root / "notes").mkdir()
    (root / ".hidden").mkdir()
    (root / "notes" / "readme.txt").write_text("not a campaign", encoding="utf-8")

    found = [status.folder.name for status in find_campaigns(root)]
    assert found == ["2306_fastnet", "2307_rhum"]


def test_a_missing_data_root_lists_nothing(tmp_path):
    assert find_campaigns(tmp_path / "nowhere") == []
