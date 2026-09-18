"""The page builds, reads a folder correctly, and says what it cannot do yet."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml
from nicegui import ui
from nicegui.testing import User

from yacht_co2.gui import app, artifacts, components
from yacht_co2.gui.yamlform import load_document, save_document, write_path
from yacht_co2.manifest import packaged_defaults
from yacht_co2.userconfig import write_settings


def test_launch_uses_the_renku_proxy_path(monkeypatch):
    options = {}
    monkeypatch.setenv(app.RENKU_BASE_URL_PATH_ENV, "/sessions/example")
    monkeypatch.setattr(app, "register_pages", lambda: None)
    monkeypatch.setattr(app.ui, "run", lambda **kwargs: options.update(kwargs))

    app.launch(host="0.0.0.0", show=False)

    assert options["host"] == "0.0.0.0"
    assert options["port"] == 8080
    assert options["root_path"] == "/sessions/example"


@pytest.fixture
def campaigns(tmp_path):
    """A data root holding one untouched campaign folder."""
    root = tmp_path / "data"
    folder = root / "2306_fastnet"
    folder.mkdir(parents=True)
    (folder / "230724_001.log").write_text("raw\n", encoding="utf-8")
    write_settings({"data_root": str(root)})
    return root


async def test_the_page_lists_the_campaign_folders_it_finds(user: User, campaigns):
    await user.open("/")
    await user.should_see("Yacht CO2")
    await user.should_see("Open a published record")
    await user.should_see("Import raw logs")
    await user.should_see("Campaign folders")
    await user.should_see("2306_fastnet")
    await user.should_not_see("Process raw logs directly")
    # No folder is chosen yet, so there are no steps to show.
    await user.should_not_see(marker="step-archive")


async def test_a_campaign_folders_contents_are_shown_in_a_dialog(user: User, campaigns):
    await user.open("/")
    user.find(marker="show-folder-2306_fastnet").click()

    await user.should_see("230724_001.log")
    await user.should_see("Folder contents")
    await user.should_see("Download folder")


async def test_import_logs_starts_disabled_until_identity_and_a_file_exist(user: User, campaigns):
    await user.open("/")

    submit = _one(user, "raw-import-submit")
    assert submit._props["disable"] is True
    user.find(marker="raw-import-name").type("New campaign")
    user.find(marker="raw-import-date").type("2023-07")
    assert submit._props["disable"] is True

    upload = _one(user, "raw-log-upload")
    await upload.handle_uploads([ui.upload.SmallFileUpload("raw.log", "text/plain", b"raw")])
    await asyncio.sleep(0.05)
    assert submit.enabled is True

    user.find("Clear files").click()
    assert submit.enabled is False


async def test_upload_choices_use_matching_cards_in_the_first_row(user: User, campaigns):
    await user.open("/")

    raw = _one(user, "raw-import-panel")
    record = _one(user, "record-panel")
    assert raw.tag == record.tag
    assert set(raw._classes) == set(record._classes)
    raw_column = raw._parent_slot().parent
    record_column = record._parent_slot().parent
    assert raw_column._parent_slot().parent is record_column._parent_slot().parent
    assert "landing-upload-row" in raw_column._parent_slot().parent._markers


async def test_header_shows_a_green_zenodo_status_when_a_token_is_available(
    user: User, campaigns, monkeypatch
):
    monkeypatch.setattr(app, "read_token", lambda **_kwargs: "secret")

    await user.open("/")

    status = _one(user, "zenodo-status")
    assert status._props["color"] == "positive"
    await user.should_see("Zenodo ready")


async def test_header_omits_zenodo_status_without_a_token(user: User, campaigns, monkeypatch):
    monkeypatch.setattr(app, "read_token", lambda **_kwargs: "")

    await user.open("/")

    await user.should_not_see(marker="zenodo-status")


async def test_progress_is_collapsed_by_default(user: User, campaigns):
    await user.open("/")
    progress = _one(user, "progress-log")
    assert progress.value is False


async def test_choosing_a_campaign_shows_every_step(user: User, campaigns):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    for step in ("archive", "manifest", "settings", "process", "publish"):
        await user.should_see(marker=f"step-{step}")


async def test_a_step_says_which_earlier_step_it_is_waiting_for(user: User, campaigns):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    # Nothing has been archived, so the manifest cannot name a record. The page
    # says which earlier step is missing rather than failing once it is run.
    await user.should_see("Archive the folder first")
    await user.should_see("Build the manifest first")


async def test_skipping_archive_builds_a_persisted_local_manifest(user: User, campaigns):
    folder = campaigns / "2306_fastnet"
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\n",
        encoding="utf-8",
    )
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()

    await user.should_see(marker="skip-archive")
    user.find(marker="skip-archive").click()
    await user.should_see("Building a local manifest finished.", retries=50)

    document = yaml.safe_load((folder / "manifest.yaml").read_text(encoding="utf-8"))
    assert document["campaign"] == {
        "id": "2306_fastnet",
        "name": "Fastnet Race",
        "date": "2023-07-24",
    }
    assert document["inputs"]["logs"] == "./*.log"
    assert "repository" not in document["inputs"]

    archive_step = _one(user, "step-archive")
    manifest_step = _one(user, "step-manifest")
    assert archive_step._props.get("done") is not True
    assert archive_step._props["icon"] == "skip_next"
    assert manifest_step._props["done"] is True


async def test_an_empty_data_root_says_what_a_campaign_folder_is(user: User, tmp_path):
    write_settings({"data_root": str(tmp_path)})
    await user.open("/")
    await user.should_see("No campaign folders here yet")


@pytest.fixture
def finished(tmp_path):
    """A data root holding one campaign taken all the way through."""
    root = tmp_path / "data"
    folder = root / "2306_fastnet"
    folder.mkdir(parents=True)
    (folder / "230724_001.log").write_text("raw\n", encoding="utf-8")
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\n"
        "doi: 10.5281/zenodo.12345\nsubmitted: 2023-08-01\n",
        encoding="utf-8",
    )
    # Built the way build-manifest builds one, comments and all, because
    # keeping those comments through a save is the thing being tested.
    document = load_document(packaged_defaults())
    write_path(document, ("campaign",), {"id": "fastnet", "name": "Fastnet Race"})
    write_path(document, ("campaign", "date"), "2023-07-24")
    write_path(document, ("inputs", "repository"), "10.5281/zenodo.12345")
    save_document(document, folder / "manifest.yaml")
    for name in ("track.nc", "report.json", "site.html"):
        (folder / f"yacht_co2-fastnet_race-2023_07_24-{name}").write_text("x", encoding="utf-8")
    write_settings({"data_root": str(root)})
    return folder


async def test_a_finished_campaign_offers_what_it_produced(user: User, finished):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Interactive page")
    await user.should_see("Dataset (NetCDF)")
    await user.should_see("Run report")
    # Already archived and already processed, so neither step offers to redo it.
    await user.should_see("Archived as 10.5281/zenodo.12345")
    await user.should_see("Process again")


async def test_what_a_campaign_produced_is_opened_by_the_desktop(user: User, finished, monkeypatch):
    """Not by a second browser tab: a native window has none to open."""
    monkeypatch.setattr(artifacts, "is_docker", lambda: False)
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(
        components, "open_file", lambda path: opened.append(("open", Path(path).name))
    )
    monkeypatch.setattr(
        components, "reveal", lambda path: opened.append(("reveal", Path(path).name))
    )

    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Interactive page")
    user.find("Interactive page").click()
    user.find("Dataset (NetCDF)").click()
    assert opened == [
        ("open", "yacht_co2-fastnet_race-2023_07_24-site.html"),
        ("reveal", "yacht_co2-fastnet_race-2023_07_24-track.nc"),
    ]
    # The report is JSON, so it is read in the page rather than handed to
    # whichever editor claims the extension.
    user.find("Run report").click()
    await user.should_see("yacht_co2-fastnet_race-2023_07_24-report.json")


async def test_docker_uses_browser_actions_for_completed_campaign_artifacts(
    user: User, finished, monkeypatch
):
    """A container uses browser routes, while Renku only prefixes their URLs."""
    monkeypatch.setattr(artifacts, "is_docker", lambda: True)
    monkeypatch.setenv(app.RENKU_BASE_URL_PATH_ENV, "/sessions/example")
    opened: list[Path] = []
    monkeypatch.setattr(components, "open_file", opened.append)
    monkeypatch.setattr(components, "reveal", opened.append)

    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Process again")
    user.find(marker="download-site").click()
    await user.should_see(marker="site-preview-frame")
    frame = _one(user, "site-preview-frame")
    assert "title" not in frame._props
    assert "max-w-7xl" in frame._parent_slot().parent._classes
    track = user.find(marker="download-track").elements
    assert track
    assert {button._props["href"] for button in track} == {
        "/sessions/example/artifacts/2306_fastnet/track"
    }
    user.find(marker="download-report").click()
    await user.should_see("Download report")
    assert opened == []


async def test_docker_keeps_the_right_key_when_only_one_artifact_exists(
    user: User, finished, monkeypatch
):
    """Filtering absent artifacts does not shift the NetCDF route onto the site key."""
    for path in finished.glob("*site.html"):
        path.unlink()
    for path in finished.glob("*report.json"):
        path.unlink()
    monkeypatch.setattr(artifacts, "is_docker", lambda: True)
    monkeypatch.setenv(app.RENKU_BASE_URL_PATH_ENV, "/sessions/example")

    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()

    await user.should_see("Download Dataset (NetCDF)")
    assert {button._props["href"] for button in user.find(marker="download-track").elements} == {
        "/sessions/example/artifacts/2306_fastnet/track"
    }
    await user.should_not_see(marker="download-site")
    await user.should_not_see(marker="download-report")


async def test_the_manifest_form_shows_the_campaigns_own_settings(user: User, finished):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    # Step three is the one the README tells the operator to check by hand.
    await user.should_see("Check these before processing")
    await user.should_see("Sampling phases")
    await user.should_see("Quality control")
    # Warnings are shown where they can still be acted on: the packaged
    # template carries flux.formulation, which nothing reads.
    await user.should_see("flux.formulation")
    await user.should_see("is not read by anything; check the spelling")


def _one(user: User, marker: str):
    """The single element carrying ``marker``."""
    found = user.find(marker=marker).elements
    assert len(found) == 1, f"expected one {marker}, found {len(found)}"
    return next(iter(found))


async def test_the_form_saves_an_edit_without_losing_the_comments(user: User, finished):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Check these before processing")

    _one(user, "field-qc.minimum_water_flow").set_value(0.75)
    _one(user, "field-phases.analysis").set_value("5, 6")
    user.find(marker="save-campaign-manifest").click()
    await user.should_see("Saved manifest.yaml")

    written = (finished / "manifest.yaml").read_text(encoding="utf-8")
    document = yaml.safe_load(written)
    assert document["qc"]["minimum_water_flow"] == 0.75
    assert document["phases"]["analysis"] == [5, 6]
    # The sections the form knows nothing about are left exactly as they were.
    assert document["atmosphere"]["time_tolerance"] == "7D"
    assert document["outputs"]["video_options"]["fps"] == 12
    # And the comments, which are the only explanation of what these mean.
    assert "# Flags rather than filters" in written
    assert "LI-850 CellTemp" in written
    assert "phase in which seawater is measured" in written


async def test_the_form_adds_a_sampling_phase_and_offers_it_for_settling_time(
    user: User, finished
):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Check these before processing")

    _one(user, "new-phase-name").set_value("span")
    _one(user, "new-phase-codes").set_value("1, 15")
    user.find(marker="add-phase").click()

    phase = _one(user, "field-phases.span")
    assert phase.value == "1, 15"
    dropdown = _one(user, "phase-lag-role")
    labels = {
        option.get("label", option) if isinstance(option, dict) else option
        for option in dropdown._props["options"]
    }
    assert "span" in labels

    dropdown.set_value("span")
    _one(user, "phase-lag-seconds").set_value(90)
    user.find(marker="add-phase-lag").click()
    assert _one(user, "field-qc.phase_transition_lag.span").value == 90

    user.find(marker="save-campaign-manifest").click()
    await user.should_see("Saved manifest.yaml")
    document = yaml.safe_load((finished / "manifest.yaml").read_text(encoding="utf-8"))
    assert document["phases"]["span"] == [1, 15]
    assert document["qc"]["phase_transition_lag"]["span"] == 90


async def test_quality_control_fields_align_and_video_is_not_an_output_toggle(user: User, finished):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Check these before processing")

    number_shell = _one(user, "field-qc.minimum_water_flow")._parent_slot().parent
    range_row = _one(user, "field-qc.ranges.co2-low")._parent_slot().parent
    range_shell = range_row._parent_slot().parent
    assert {"w-full", "gap-1", "self-start"}.issubset(number_shell._classes)
    assert {"w-full", "gap-1", "self-start"}.issubset(range_shell._classes)
    await user.should_not_see(marker="field-outputs.video")


async def test_an_emptied_control_leaves_the_key_out_rather_than_blanking_it(user: User, finished):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Check these before processing")

    _one(user, "field-inputs.timezone").set_value("")
    user.find(marker="save-campaign-manifest").click()
    await user.should_see("Saved manifest.yaml")

    document = yaml.safe_load((finished / "manifest.yaml").read_text(encoding="utf-8"))
    assert "timezone" not in document["inputs"]


@pytest.fixture
def archived(tmp_path):
    """A campaign that has been archived but not yet given a manifest."""
    root = tmp_path / "data"
    folder = root / "2306_fastnet"
    folder.mkdir(parents=True)
    (folder / "230724_001.log").write_text("raw\n", encoding="utf-8")
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\ndoi: 10.5281/zenodo.12345\n",
        encoding="utf-8",
    )
    write_settings({"data_root": str(root)})
    return folder


async def test_building_the_manifest_takes_the_campaign_from_the_archive(user: User, archived):
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Build the manifest")

    user.find("Build the manifest").click()
    await user.should_see("Building the manifest finished.", retries=50)

    document = yaml.safe_load((archived / "manifest.yaml").read_text(encoding="utf-8"))
    assert document["campaign"] == {
        "id": "2306_fastnet",
        "name": "Fastnet Race",
        "date": "2023-07-24",
    }
    assert document["inputs"]["repository"] == "10.5281/zenodo.12345"
    # The page has re-read the folder, so the next step is now the open one.
    await user.should_see("manifest.yaml is written.")
