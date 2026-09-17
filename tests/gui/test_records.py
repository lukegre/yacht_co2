"""Opening a published record in the workbench instead of a folder of files."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui.testing import User

from yacht_co2.errors import ZenodoError
from yacht_co2.record import PublishedRecord, RecordFile
from yacht_co2.userconfig import write_settings

DOI = "10.5281/zenodo.12345"


def file(key: str, kind: str, size: int = 1024) -> RecordFile:
    return RecordFile(key=key, kind=kind, size=size, url=f"https://zenodo.org/{key}")


def record(*files: RecordFile, campaign: str = "Fastnet Race") -> PublishedRecord:
    return PublishedRecord(
        reference=DOI,
        origin="https://zenodo.org",
        record_id="12345",
        doi=DOI,
        title="Surface ocean CO2 during the Fastnet Race (2023-07-24)",
        campaign=campaign,
        campaign_date="2023-07-24",
        slug="2307_fastnet",
        files=files,
    )


PRODUCTS = (
    file("yacht_co2-fastnet_race-2023_07_24-site.html", "site", 2_500_000),
    file("yacht_co2-fastnet_race-2023_07_24-track.nc", "track", 8_000_000),
    file("yacht_co2-fastnet_race-2023_07_24-report.json", "report", 4_000),
)
LOGS = tuple(file(f"23072{index}_001.log", "log") for index in range(3))
MANIFEST = file("manifest.yaml", "other", 4_000)
OTHER = file("notes.md", "other", 2_000)


@pytest.fixture
def root(tmp_path):
    """An empty data root, so that only what is downloaded appears in it."""
    data = tmp_path / "data"
    data.mkdir()
    write_settings({"data_root": str(data)})
    return data


@pytest.fixture
def lookup(monkeypatch):
    """Answer a look-up with whatever the test wants the record to be."""

    def answer(result):
        def read(reference, **options):
            del options
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr("yacht_co2.gui.records.read_record", read)

    return answer


@pytest.fixture
def downloads(monkeypatch):
    """Write the files a download would have fetched, without fetching them."""
    asked: list[dict] = []

    def fake(record, destination, keys, **options):
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        asked.append({"folder": folder, "keys": list(keys), **options})
        written = []
        for key in keys:
            (folder / key).write_text("x", encoding="utf-8")
            written.append(folder / key)
        from yacht_co2.record import write_campaign_config

        write_campaign_config(
            folder,
            record,
            options.get("campaign") or record.campaign,
            options.get("campaign_date") or record.campaign_date,
        )
        return written

    monkeypatch.setattr("yacht_co2.gui.records.import_record", fake)
    return asked


async def test_a_record_says_what_it_holds_before_anything_is_downloaded(user: User, root, lookup):
    lookup(record(*PRODUCTS, *LOGS))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()

    await user.should_see("Surface ocean CO2 during the Fastnet Race (2023-07-24)")
    await user.should_see(DOI)
    # The products are named one by one, because they are what gets chosen.
    await user.should_see("yacht_co2-fastnet_race-2023_07_24-site.html")
    await user.should_see("interactive page")
    await user.should_see("8.0 MB")
    # The logs are the bulk of a record and are counted rather than listed.
    await user.should_see("3 raw logs")
    await user.should_see("Download the products (3)")
    await user.should_see("Download the raw logs (3)")
    # Nothing has been downloaded, so the data root is still empty.
    assert list(root.iterdir()) == []


async def test_a_reference_that_names_nothing_is_reported_where_it_was_typed(
    user: User, root, lookup
):
    lookup(ZenodoError("invalid Zenodo repository reference: nonsense"))
    await user.open("/")
    user.find(marker="record-reference").type("nonsense")
    user.find(marker="record-lookup").click()

    await user.should_see("invalid Zenodo repository reference: nonsense")
    await user.should_not_see("Download the products")


async def test_looking_up_nothing_asks_for_a_reference(user: User, root):
    await user.open("/")
    user.find(marker="record-lookup").click()
    await user.should_see("Give a DOI or a record URL first.")


async def test_the_campaign_is_offered_as_the_record_already_named_it(user: User, root, lookup):
    lookup(record(*PRODUCTS))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()

    await user.should_see(marker="record-campaign")
    assert user.find(marker="record-campaign").elements.pop().value == "Fastnet Race"
    assert user.find(marker="record-date").elements.pop().value == "2023-07-24"
    assert user.find(marker="record-folder").elements.pop().value == "2307_fastnet"


async def test_downloading_the_products_leaves_a_folder_that_can_be_looked_at(
    user: User, root, lookup, downloads
):
    lookup(record(*PRODUCTS, *LOGS, MANIFEST, OTHER))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()
    await user.should_see(marker="record-download-products")
    await user.should_see("manifest.yaml")
    await user.should_see("processing manifest")
    await user.should_see("1 other file")
    await user.should_see("Download the products (4)")
    user.find(marker="record-download-products").click()

    await user.should_see("Downloaded into", retries=50)
    # The processing manifest belongs with the products it describes, while
    # the raw logs remain a separate (and potentially much larger) download.
    assert downloads[0]["keys"] == [product.key for product in PRODUCTS] + [MANIFEST.key]
    assert downloads[0]["campaign"] == "Fastnet Race"
    folder = root / "2307_fastnet"
    assert (folder / "yacht_co2-fastnet_race-2023_07_24-site.html").is_file()
    assert (folder / "manifest.yaml").is_file()
    assert not (folder / "230720_001.log").exists()

    # The folder is now an ordinary campaign, listed and selected, and what it
    # holds is offered to be looked at.
    await user.should_see("2307_fastnet")
    await user.should_see("Interactive page")
    await user.should_see("Run report")


async def test_downloading_the_raw_logs_gives_a_campaign_ready_to_process(
    user: User, root, lookup, downloads
):
    lookup(record(*LOGS, campaign=""))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()
    await user.should_see(marker="record-download-logs")
    # Nothing in a logs-only record says what the campaign is called, so the
    # page asks rather than guessing.
    assert user.find(marker="record-campaign").elements.pop().value == ""
    user.find(marker="record-campaign").type("Fastnet Race")
    user.find(marker="record-download-logs").click()

    await user.should_see("Downloaded into", retries=50)
    assert downloads[0]["keys"] == [log.key for log in LOGS]
    folder = root / "2307_fastnet"
    assert sorted(path.name for path in folder.glob("*.log")) == [log.key for log in LOGS]
    # Its DOI is written down, so the step that follows can name the record the
    # logs are read back from.
    assert "10.5281/zenodo.12345" in (folder / "zenodo.yaml").read_text()
    await user.should_see("Build the manifest")


async def test_a_download_without_a_campaign_name_is_refused(user: User, root, lookup, downloads):
    lookup(record(*LOGS, campaign=""))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()
    await user.should_see(marker="record-download-logs")
    user.find(marker="record-download-logs").click()

    await user.should_see("A campaign name is needed")
    assert downloads == []


async def test_a_folder_name_that_is_a_path_is_refused(user: User, root, lookup, downloads):
    lookup(record(*PRODUCTS))
    await user.open("/")
    user.find(marker="record-reference").type(DOI)
    user.find(marker="record-lookup").click()
    await user.should_see(marker="record-folder")
    user.find(marker="record-folder").clear().type("../elsewhere")
    user.find(marker="record-download-products").click()

    await user.should_see("has to be a plain name, not a path")
    assert downloads == []
