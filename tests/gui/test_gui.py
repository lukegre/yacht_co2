"""The page builds, reads a folder correctly, and says what it cannot do yet."""

from __future__ import annotations

import pytest
import yaml
from nicegui.testing import User

from yacht_co2.gui.yamlform import load_document, save_document, write_path
from yacht_co2.manifest import packaged_defaults
from yacht_co2.userconfig import write_settings


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
    await user.should_see("yacht-co2")
    await user.should_see("Campaign folders")
    await user.should_see("2306_fastnet")
    # No folder is chosen yet, so there are no steps to show.
    await user.should_not_see(marker="step-archive")


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
