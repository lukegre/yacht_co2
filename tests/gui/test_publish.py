"""Publishing the products, including when the record will not accept them yet."""

from __future__ import annotations

import json

import pytest
from loguru import logger
from nicegui.testing import User

from yacht_co2.gui.app import archive, upload_outcome
from yacht_co2.gui.yamlform import load_document, save_document, write_path
from yacht_co2.manifest import packaged_defaults
from yacht_co2.userconfig import write_settings


@pytest.fixture
def processed(tmp_path):
    """A campaign archived and processed, ready for its products to be added."""
    root = tmp_path / "data"
    folder = root / "2306_fastnet"
    folder.mkdir(parents=True)
    (folder / "230724_001.log").write_text("raw\n", encoding="utf-8")
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\n"
        "doi: 10.5281/zenodo.12345\nsubmitted: 2023-08-01\n",
        encoding="utf-8",
    )
    document = load_document(packaged_defaults())
    write_path(document, ("campaign",), {"id": "fastnet", "name": "Fastnet Race"})
    write_path(document, ("campaign", "date"), "2023-07-24")
    write_path(document, ("inputs", "repository"), "10.5281/zenodo.12345")
    save_document(document, folder / "manifest.yaml")
    for name in ("track.nc", "report.json", "site.html"):
        (folder / f"yacht_co2-fastnet_race-2023_07_24-{name}").write_text("x", encoding="utf-8")
    write_settings({"data_root": str(root)})
    return folder


def _upload_state(folder, status: str, **extra) -> None:
    (folder / ".zenodo-upload.json").write_text(
        json.dumps({"record_id": "12345", "status": status, **extra}), encoding="utf-8"
    )


def test_an_upload_that_archived_nothing_does_not_claim_otherwise():
    # upload_raw_folder completes perfectly for a record whose review is open;
    # it simply uploads nothing, which the page must not report as success.
    assert upload_outcome({"status": "pending_review"}) == (
        "Nothing uploaded: the record is still awaiting review.",
        "warning",
    )
    assert upload_outcome({"status": "dry-run", "files": {}}) == (
        "Checked. Nothing was uploaded.",
        "info",
    )
    assert upload_outcome({"status": "published"}) == ("Uploaded to Zenodo.", "positive")


def test_a_frozen_record_explains_itself_in_the_log(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "yacht_co2.gui.app.upload_raw_folder",
        lambda folder, **options: {
            "status": "pending_review",
            "record_id": "12345",
            "review_url": "https://zenodo.org/requests/abc",
        },
    )
    lines: list[str] = []
    handler = logger.add(lines.append, format="{message}", level="INFO")
    try:
        state = archive(tmp_path, publish=True, new_version=True)
    finally:
        logger.remove(handler)

    assert state["status"] == "pending_review"
    transcript = "\n".join(lines)
    assert "Nothing was uploaded" in transcript
    assert "files are frozen while its review is open" in transcript
    # It says what to do, which is nothing, rather than leaving a bare failure.
    assert "nothing to fix and nothing to retry" in transcript
    assert "https://zenodo.org/requests/abc" in transcript


async def test_the_step_says_it_is_waiting_instead_of_offering_a_dead_button(
    user: User, processed
):
    _upload_state(processed, "pending_review")
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Waiting for a curator to accept the raw data.")
    await user.should_see("cannot be added to it yet")
    await user.should_not_see("Publish a new version")


async def test_an_accepted_record_offers_the_upload(user: User, processed):
    _upload_state(processed, "published")
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Publish a new version")
    await user.should_not_see("Waiting for a curator to accept the raw data.")


async def test_publishing_reports_a_frozen_record_rather_than_success(
    user: User, processed, monkeypatch
):
    _upload_state(processed, "published")
    monkeypatch.setattr(
        "yacht_co2.gui.app.upload_raw_folder",
        lambda folder, **options: {"status": "pending_review", "record_id": "12345"},
    )
    await user.open("/")
    user.find(marker="campaign-2306_fastnet").click()
    await user.should_see("Publish a new version")
    user.find("Publish a new version").click()
    await user.should_see(
        "Nothing uploaded: the record is still awaiting review.", retries=50
    )
    await user.should_not_see("Publishing the products finished.")
