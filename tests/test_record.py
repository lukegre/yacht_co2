"""Reading a published record, and bringing one down as a campaign folder."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from yacht_co2.errors import ZenodoError
from yacht_co2.naming import output_name, parse_output_name
from yacht_co2.record import (
    PublishedRecord,
    download,
    import_record,
    read_record,
    resolve_reference,
    suggest_campaign_name,
)


class FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self.json_data = json_data
        self.content = content

    def json(self):
        return self.json_data

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSession:
    """Serve one record and the files it links to, counting what is asked for."""

    def __init__(self, record, files):
        self.record = record
        self.files = files
        self.calls = []
        self.headers = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        self.headers.append(kwargs.get("headers") or {})
        if url.endswith("/api/records/12345"):
            return FakeResponse(json_data=self.record)
        return FakeResponse(content=self.files[url])


def entry(name: str, content: bytes) -> tuple[str, dict]:
    """One file of a record, as Zenodo publishes it."""
    url = f"https://zenodo.org/api/records/12345/files/{name}/content"
    return url, {
        "key": name,
        "size": len(content),
        "checksum": f"md5:{hashlib.md5(content, usedforsecurity=False).hexdigest()}",
        "links": {"content": url},
    }


#: A record of a campaign taken all the way through: the logs it was measured
#: as, and the three products it was processed into.
PROCESSED_FILES = {
    "230724_001.log": b"@NAME,DATE\n",
    "yacht_co2-fastnet_race-2023_07_24-site.html": b"<html></html>",
    "yacht_co2-fastnet_race-2023_07_24-track.nc": b"CDF\x01",
    "yacht_co2-fastnet_race-2023_07_24-report.json": b'{"campaign": "Fastnet Race"}',
    "notes.md": b"# notes\n",
}


def fake_record(files: dict[str, bytes], **metadata) -> FakeSession:
    entries = []
    content = {}
    for name, payload in files.items():
        url, listed = entry(name, payload)
        entries.append(listed)
        content[url] = payload
    record = {
        "id": "12345",
        "pids": {"doi": {"identifier": "10.5281/zenodo.12345"}},
        "files": {"entries": entries},
        "metadata": {
            "title": "Surface ocean CO2 measurements during the Fastnet Race (2023-07-24)",
            **metadata,
        },
    }
    return FakeSession(record, content)


# -- what a reference names ---------------------------------------------


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("10.5281/zenodo.12345", ("https://zenodo.org", "12345")),
        ("doi:10.5281/zenodo.12345", ("https://zenodo.org", "12345")),
        ("https://doi.org/10.5281/zenodo.12345", ("https://zenodo.org", "12345")),
        ("https://zenodo.org/records/12345", ("https://zenodo.org", "12345")),
        ("https://zenodo.org/records/12345/", ("https://zenodo.org", "12345")),
        ("12345", ("https://zenodo.org", "12345")),
        ("10.5072/zenodo.99", ("https://sandbox.zenodo.org", "99")),
        ("https://sandbox.zenodo.org/records/99", ("https://sandbox.zenodo.org", "99")),
    ],
)
def test_the_four_ways_of_naming_a_record_all_name_the_same_one(reference, expected):
    assert resolve_reference(reference) == expected


@pytest.mark.parametrize(
    "reference",
    ["", "   ", "not a doi", "ftp://zenodo.org/records/1", "https://example.org/records/1"],
)
def test_something_that_is_not_a_record_is_refused(reference):
    with pytest.raises(ZenodoError):
        resolve_reference(reference)


# -- what a record holds ------------------------------------------------


def test_a_record_is_read_into_its_campaign_and_its_files():
    session = fake_record(
        PROCESSED_FILES,
        dates=[{"date": "2023-07-24", "type": {"id": "collected"}}],
        identifiers=[{"scheme": "other", "identifier": "2307_fastnet"}],
    )

    record = read_record("10.5281/zenodo.12345", session=session)

    assert record.doi == "10.5281/zenodo.12345"
    assert record.record_id == "12345"
    assert not record.is_sandbox
    # The campaign is recovered so that the folder names its files the way the
    # record already named them.
    assert record.campaign == "Fastnet Race"
    assert record.campaign_date == "2023-07-24"
    assert record.slug == "2307_fastnet"
    assert [file.key for file in record.products] == [
        "yacht_co2-fastnet_race-2023_07_24-report.json",
        "yacht_co2-fastnet_race-2023_07_24-site.html",
        "yacht_co2-fastnet_race-2023_07_24-track.nc",
    ]
    assert [file.key for file in record.logs] == ["230724_001.log"]
    # A file this package did not write is neither a product nor a log.
    assert [file.key for file in record.files if file.kind == "other"] == ["notes.md"]


def test_a_record_with_only_raw_logs_offers_no_products():
    session = fake_record({"230724_001.log": b"@NAME,DATE\n"})

    record = read_record("10.5281/zenodo.12345", session=session)

    assert record.products == ()
    assert [file.key for file in record.logs] == ["230724_001.log"]
    # Nothing in such a record says what the campaign is called, so nothing is
    # guessed: the interface asks instead.
    assert record.campaign == ""
    assert record.slug == "zenodo-12345"


def test_the_campaign_date_falls_back_to_the_one_named_in_the_products():
    """A record whose metadata omits the collected date still carries it."""
    session = fake_record(PROCESSED_FILES)

    record = read_record("10.5281/zenodo.12345", session=session)

    assert record.campaign_date == "2023-07-24"
    assert record.campaign == "Fastnet Race"


def test_a_recovered_campaign_name_slugs_back_to_the_name_it_came_from():
    """The recovered name has to reproduce the filenames it was read out of."""
    for campaign in ("Fastnet Race", "fastnet", "Rolex Middle Sea Race"):
        parsed = parse_output_name(output_name(campaign, "2023-07-24", "track", "nc"))
        assert parsed is not None
        recovered = suggest_campaign_name(parsed.campaign)
        assert output_name(recovered, "2023-07-24", "track", "nc") == output_name(
            campaign, "2023-07-24", "track", "nc"
        )


# -- bringing it down ---------------------------------------------------


def test_a_concept_doi_is_read_as_the_version_it_currently_names():
    """A concept DOI names every version of a record; Zenodo answers the latest."""
    session = fake_record(PROCESSED_FILES)
    session.record["id"] = "67890"

    record = read_record("10.5281/zenodo.12345", session=session)

    # The version actually read is what gets written down, so the DOI, the
    # files and the folder they land in all describe the same one.
    assert record.record_id == "67890"
    assert record.url == "https://zenodo.org/records/67890"


def test_the_record_is_asked_for_in_the_serialization_that_names_its_metadata():
    """Zenodo otherwise answers with a legacy shape that omits half of it."""
    session = fake_record(PROCESSED_FILES)

    read_record("10.5281/zenodo.12345", session=session)

    assert session.headers[0]["Accept"] == "application/vnd.inveniordm.v1+json"


def test_downloading_verifies_what_arrives_and_never_fetches_it_twice(tmp_path):
    session = fake_record(PROCESSED_FILES)
    record = read_record("10.5281/zenodo.12345", session=session)
    keys = [file.key for file in record.products]

    paths = download(record, keys, tmp_path, session=session)

    assert sorted(path.name for path in paths) == sorted(keys)
    assert (
        tmp_path / "yacht_co2-fastnet_race-2023_07_24-site.html"
    ).read_bytes() == b"<html></html>"
    before = len(session.calls)
    # A published record is immutable, so a file that still matches is kept.
    assert download(record, keys, tmp_path, session=session) == paths
    assert len(session.calls) == before


def test_a_file_that_does_not_match_its_published_checksum_is_refused(tmp_path):
    session = fake_record(PROCESSED_FILES)
    record = read_record("10.5281/zenodo.12345", session=session)
    key = "yacht_co2-fastnet_race-2023_07_24-track.nc"
    session.files[f"https://zenodo.org/api/records/12345/files/{key}/content"] = b"CDF\x02"

    with pytest.raises(ZenodoError, match="checksum"):
        download(record, [key], tmp_path, session=session)
    # Nothing half-downloaded is left where the file was going to be.
    assert list(tmp_path.iterdir()) == []


def test_a_record_cannot_name_a_file_outside_the_folder(tmp_path):
    record = PublishedRecord(
        reference="10.5281/zenodo.12345",
        origin="https://zenodo.org",
        record_id="12345",
        doi="10.5281/zenodo.12345",
        title="",
        campaign="",
        campaign_date="",
        slug="x",
    )
    with pytest.raises(ZenodoError, match="holds no file"):
        download(record, ["../escaped.nc"], tmp_path)


def test_importing_a_record_leaves_an_ordinary_campaign_folder(tmp_path):
    session = fake_record(PROCESSED_FILES)
    record = read_record("10.5281/zenodo.12345", session=session)
    folder = tmp_path / "2307_fastnet"

    import_record(
        record,
        folder,
        [file.key for file in record.products],
        campaign="Fastnet Race",
        campaign_date="2023-07-24",
        session=session,
    )

    document = yaml.safe_load((folder / "zenodo.yaml").read_text())
    assert document == {
        "campaign": "Fastnet Race",
        "campaign_date": "2023-07-24",
        "doi": "10.5281/zenodo.12345",
    }
    # The folder now describes itself the way the rest of the package reads it.
    from yacht_co2.workflow import campaign_status

    status = campaign_status(folder)
    assert status.doi == "10.5281/zenodo.12345"
    assert status.is_uploaded and status.is_processed
    assert status.site is not None and status.report is not None
    assert status.title == "Fastnet Race (2023-07-24)"


def test_importing_the_raw_logs_gives_a_folder_the_steps_can_process(tmp_path):
    session = fake_record({"230724_001.log": b"@NAME,DATE\n"})
    record = read_record("10.5281/zenodo.12345", session=session)
    folder = tmp_path / "2307_fastnet"

    import_record(
        record,
        folder,
        ["230724_001.log"],
        campaign="Fastnet Race",
        campaign_date="2023-07-24",
        session=session,
    )

    from yacht_co2.workflow import campaign_status

    status = campaign_status(folder)
    assert [path.name for path in status.logs] == ["230724_001.log"]
    assert status.is_uploaded and not status.is_processed
    # Which is exactly what the manifest step needs to name the record its
    # logs are read back from.
    from yacht_co2.manifest import build_manifest

    manifest = build_manifest(folder / "zenodo.yaml")
    document = yaml.safe_load(Path(manifest).read_text())
    assert document["inputs"]["repository"] == "10.5281/zenodo.12345"
    assert document["campaign"]["name"] == "Fastnet Race"


def test_a_folder_that_already_describes_itself_is_not_overwritten(tmp_path):
    session = fake_record(PROCESSED_FILES)
    record = read_record("10.5281/zenodo.12345", session=session)
    folder = tmp_path / "2307_fastnet"
    folder.mkdir()
    existing = "campaign: Something Else\ncampaign_date: 2019-01-01\ndoi: 10.5281/zenodo.999\n"
    (folder / "zenodo.yaml").write_text(existing, encoding="utf-8")

    import_record(
        record,
        folder,
        ["yacht_co2-fastnet_race-2023_07_24-site.html"],
        campaign="Fastnet Race",
        session=session,
    )

    # The download still happens; what the folder says about itself does not
    # get replaced by what this download guessed.
    assert (folder / "yacht_co2-fastnet_race-2023_07_24-site.html").is_file()
    assert (folder / "zenodo.yaml").read_text() == existing
