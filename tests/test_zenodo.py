import json
from datetime import date
from pathlib import Path

import pytest
import requests
import yaml
from loguru import logger
from typer.testing import CliRunner

from yacht_co2.errors import ZenodoError
from yacht_co2.zenodo import (
    CONFIG_NAME,
    DEFAULTS_BLOCK,
    DEFAULTS_NAME,
    STATE_NAME,
    ZenodoClient,
    _file_entries,
    _notes_of,
    _with_pids,
    app,
    generate_zenodo_config,
    load_zenodo_config,
    parse_creators,
    upload_raw_folder,
)


def test_parse_creators_preserves_order_trims_and_normalizes_urls():
    result = parse_creators(
        [
            "  Gregor, Luke , https://orcid.org/0000-0001-6071-1857  ",
            "Smith, Jane, 0000-0002-1825-0097",
        ]
    )
    people = [creator["person_or_org"] for creator in result]
    assert [person["name"] for person in people] == ["Gregor, Luke", "Smith, Jane"]
    assert people[0]["identifiers"] == [{"scheme": "orcid", "identifier": "0000-0001-6071-1857"}]


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        (["Gregor, Luke"], "creator 1"),
        (["Gregor, , 0000-0001-6071-1857"], "creator 1"),
        (["Gregor, Luke, 0000-0001-6071-1858"], "checksum"),
        (
            [
                "Gregor, Luke, 0000-0001-6071-1857",
                "Other, Person, https://orcid.org/0000-0001-6071-1857",
            ],
            "creator 2: duplicate",
        ),
    ],
)
def test_parse_creators_rejects_malformed_entries(entries, message):
    with pytest.raises(ZenodoError, match=message):
        parse_creators(entries)


def test_generate_config_keeps_only_folder_facts_and_folder_precedence(tmp_path):
    path = generate_zenodo_config(
        tmp_path,
        "Raw data",
        overrides={"community": "generated"},
        today=date(2024, 2, 29),
    )
    generated = yaml.safe_load(path.read_text())
    # Shared metadata stays inherited instead of being restated per folder.
    assert generated == {"community": "generated", "title": "Raw data"}
    resolved = load_zenodo_config(tmp_path, today=date(2024, 2, 29))
    assert resolved["publication_date"] == "2024-02-29"
    assert resolved["embargo"]["enabled"] is False
    assert resolved["creators"] == ["Gregor, Luke, 0000-0001-6071-1857"]

    generated.update(
        {
            "community": "folder",
            "creators": ["Smith, Jane, 0000-0002-1825-0097"],
        }
    )
    path.write_text(yaml.safe_dump(generated, sort_keys=False))
    loaded = load_zenodo_config(tmp_path, overrides={"community": "cli"})
    assert loaded["community"] == "cli"
    assert loaded["creators"] == ["Smith, Jane, 0000-0002-1825-0097"]


def write_defaults(directory, mapping):
    """Write project defaults, which live in the ``zenodo`` block."""
    (directory / DEFAULTS_NAME).write_text(yaml.safe_dump({DEFAULTS_BLOCK: mapping}))


def test_defaults_come_from_the_nearest_project_file(tmp_path, monkeypatch):
    """A folder's own defaults outrank the ones in the invocation directory."""
    working = tmp_path / "cwd"
    working.mkdir()
    write_defaults(
        working,
        {
            "creators": ["Smith, Jane, 0000-0002-1825-0097"],
            "community": "from-cwd",
            "resource_type": "dataset",
            "license": "cc-by-4.0",
            "publisher": "Zenodo",
            "description": "d",
            "language": "eng",
            "keywords": [],
            "embargo": {"enabled": False},
        },
    )
    monkeypatch.chdir(working)

    folder = tmp_path / "voyage"
    folder.mkdir()
    (folder / CONFIG_NAME).write_text("title: Test\n")
    assert load_zenodo_config(folder)["community"] == "from-cwd"

    write_defaults(folder, {"community": "from-folder"})
    assert load_zenodo_config(folder)["community"] == "from-folder"


def test_missing_defaults_names_the_directories_searched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    with pytest.raises(ZenodoError, match=f"no '{DEFAULTS_BLOCK}' block"):
        load_zenodo_config(folder)


def test_a_project_file_without_a_zenodo_block_is_not_defaults(tmp_path, monkeypatch):
    """A platform-only project.yaml must not masquerade as zenodo defaults."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    (tmp_path / DEFAULTS_NAME).write_text(yaml.safe_dump({"platform": {"vessel_name": "Y"}}))

    with pytest.raises(ZenodoError, match=f"no '{DEFAULTS_BLOCK}' block"):
        load_zenodo_config(folder)


def test_the_superseded_standalone_file_is_still_read(tmp_path, monkeypatch):
    """Projects that have not merged their configuration keep working."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    (tmp_path / "zenodo_project.yaml").write_text(yaml.safe_dump(PROJECT_DEFAULTS))
    (folder / CONFIG_NAME).write_text("title: Test\n")

    assert load_zenodo_config(folder)["community"] == "vendee-globe-co2"


def test_the_zenodo_block_outranks_a_standalone_file_beside_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    (tmp_path / "zenodo_project.yaml").write_text(yaml.safe_dump(PROJECT_DEFAULTS))
    write_defaults(tmp_path, {"community": "from-project-block"})
    (folder / CONFIG_NAME).write_text("title: Test\n")

    assert load_zenodo_config(folder)["community"] == "from-project-block"


def test_the_vessel_is_inherited_from_the_platform_block(tmp_path, monkeypatch):
    """The boat is named once, under platform, and reused by title_template."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    defaults = {key: value for key, value in PROJECT_DEFAULTS.items() if key != "vessel"}
    (tmp_path / DEFAULTS_NAME).write_text(
        yaml.safe_dump({"platform": {"vessel_name": "Yoroshiku"}, DEFAULTS_BLOCK: defaults})
    )
    (folder / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet Race", "campaign_date": "2023-07-24"})
    )

    assert "on board Yoroshiku during" in load_zenodo_config(folder)["title"]


def test_platform_vessel_may_use_either_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    defaults = {key: value for key, value in PROJECT_DEFAULTS.items() if key != "vessel"}
    (tmp_path / DEFAULTS_NAME).write_text(
        yaml.safe_dump({"platform": {"vessel": "Fleur"}, DEFAULTS_BLOCK: defaults})
    )
    (folder / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet Race", "campaign_date": "2023-07-24"})
    )

    assert "on board Fleur during" in load_zenodo_config(folder)["title"]


def test_an_explicit_zenodo_vessel_outranks_the_platform_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    (tmp_path / DEFAULTS_NAME).write_text(
        yaml.safe_dump(
            {
                "platform": {"vessel_name": "Reported name"},
                DEFAULTS_BLOCK: {**PROJECT_DEFAULTS, "vessel": "Archived name"},
            }
        )
    )
    (folder / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet Race", "campaign_date": "2023-07-24"})
    )

    assert "on board Archived name during" in load_zenodo_config(folder)["title"]


def test_a_non_mapping_zenodo_block_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "voyage"
    folder.mkdir()
    (tmp_path / DEFAULTS_NAME).write_text(yaml.safe_dump({DEFAULTS_BLOCK: "cc-by-4.0"}))

    with pytest.raises(ZenodoError, match=f"{DEFAULTS_BLOCK} must be a mapping"):
        load_zenodo_config(folder)


def test_enabled_embargo_without_a_date_clamps_to_the_end_of_a_short_month(tmp_path):
    (tmp_path / CONFIG_NAME).write_text("title: Test\nembargo: {enabled: true}\n")
    resolved = load_zenodo_config(tmp_path, today=date(2024, 2, 29))
    assert resolved["embargo"]["until"] == "2025-02-28"


def test_embargo_controls_and_invalid_dates(tmp_path):
    (tmp_path / CONFIG_NAME).write_text("title: Test\nembargo: {enabled: false}\n")
    assert load_zenodo_config(tmp_path)["embargo"]["until"] is None
    enabled = load_zenodo_config(
        tmp_path, overrides={"embargo": {"enabled": True, "until": "2027-01-01"}}
    )
    assert enabled["embargo"] == {"enabled": True, "months": 12, "until": "2027-01-01"}
    with pytest.raises(ZenodoError, match="invalid embargo"):
        load_zenodo_config(tmp_path, overrides={"embargo": {"enabled": True, "until": "soon"}})


class FakeClient:
    def __init__(self, remote=None):
        self.remote = dict(remote or {})
        self.calls = []
        self.payload = None
        self.pending = False
        self.metadata = {}

    @staticmethod
    def _record(record_id="abc12-def34"):
        return {
            "id": record_id,
            "status": "draft",
            "links": {"self_html": f"https://zenodo.test/uploads/{record_id}"},
        }

    def create_draft(self, payload):
        self.calls.append(("create",))
        self.payload = payload
        self.metadata = dict(payload.get("metadata", {}))
        return self._record()

    def get_draft(self, record_id):
        self.calls.append(("get", record_id))
        return {**self._record(record_id), "metadata": dict(self.metadata)}

    def get_record(self, record_id):
        self.calls.append(("get_record", record_id))
        return {**self._record(record_id), "status": "published"}

    def get_review(self, record_id):
        self.calls.append(("get_review", record_id))
        return {"status": "submitted"} if self.pending else {}

    def update_draft(self, record_id, payload):
        self.calls.append(("update", record_id))
        self.payload = payload
        self.metadata = dict(payload.get("metadata", {}))
        return {**self._record(record_id), "metadata": dict(self.metadata)}

    def reserve_doi(self, record):
        self.calls.append(("doi", record["id"]))
        return {
            **self._record(record["id"]),
            "pids": {"doi": {"identifier": "10.5281/zenodo.12345"}},
        }

    def create_new_version(self, record_id):
        self.calls.append(("new_version", record_id))
        return self._record()

    def import_files(self, record_id):
        self.calls.append(("import_files", record_id))
        return []

    def list_files(self, record_id):
        self.calls.append(("list", record_id))
        return [
            {"key": key, "checksum": f"md5:{checksum}"} for key, checksum in self.remote.items()
        ]

    def delete_draft(self, record_id):
        self.calls.append(("delete_draft", record_id))

    def delete_file(self, record_id, key):
        self.calls.append(("delete", key))
        self.remote.pop(key)

    def upload_file(self, record_id, path):
        import hashlib

        checksum = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
        self.calls.append(("upload", path.name))
        self.remote[path.name] = checksum
        return {"key": path.name, "checksum": f"md5:{checksum}"}

    def set_review(self, record_id, community):
        self.calls.append(("set_review", community))
        return {}

    def submit_review(self, record_id):
        self.calls.append(("submit_review", record_id))
        self.pending = True
        return {"links": {"self_html": "https://zenodo.test/requests/1"}}

    def publish_draft(self, record_id):
        self.calls.append(("publish_draft", record_id))
        return {
            **self._record(record_id),
            "status": "published",
            "links": {"self_html": f"https://zenodo.test/records/{record_id}"},
        }

    def request_json(self, method, path):
        raise AssertionError(f"unexpected raw request: {method} {path}")


PROJECT_DEFAULTS = {
    "creators": ["Gregor, Luke, 0000-0001-6071-1857"],
    "community": "vendee-globe-co2",
    "resource_type": "dataset",
    "license": "cc-by-4.0",
    "publisher": "Zenodo",
    "description": "Raw underway carbon dioxide observations.",
    "language": "eng",
    "keywords": [],
    "embargo": {"enabled": False},
    "vessel": "YOROSHIKU (Oliver Heer)",
}


@pytest.fixture(autouse=True)
def project_defaults(tmp_path_factory, monkeypatch):
    """Give every test the shared project defaults, in a directory of its own.

    They are planted in the invocation directory — the lowest-precedence
    location — so a test can still override them, or chdir elsewhere to prove
    that no defaults were found.
    """
    directory = tmp_path_factory.mktemp("project")
    write_defaults(directory, PROJECT_DEFAULTS)
    monkeypatch.chdir(directory)
    return directory


@pytest.fixture
def logs():
    """Collect loguru messages emitted during a test."""
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]), level="DEBUG")
    yield messages
    logger.remove(sink_id)


def _write_config(folder: Path, **values):
    config = {
        "title": "Raw voyage",
        "embargo": {"enabled": False},
        **values,
    }
    (folder / CONFIG_NAME).write_text(yaml.safe_dump(config, sort_keys=False))


def test_dry_run_generates_yaml_selects_files_and_escapes_markdown(tmp_path):
    (tmp_path / "data.log").write_text("measurement")
    (tmp_path / "README.md").write_text("# Read <script>alert(1)</script>")
    (tmp_path / ".secret").write_text("ignore")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "ignored.txt").write_text("ignore")
    (tmp_path / "link").symlink_to(tmp_path / "data.log")

    result = upload_raw_folder(tmp_path, title="Raw voyage", dry_run=True, today=date(2025, 3, 2))
    assert set(result["files"]) == {"README.md", "data.log"}
    assert (tmp_path / CONFIG_NAME).exists()
    assert not (tmp_path / STATE_NAME).exists()
    metadata = result["metadata"]["metadata"]
    notes = metadata["additional_descriptions"][0]["description"]
    assert "&lt;script&gt;" in notes and "<script>" not in notes
    assert metadata["additional_descriptions"][0]["type"] == {"id": "other"}
    person = metadata["creators"][0]["person_or_org"]
    assert person["name"] == "Gregor, Luke"
    assert person["identifiers"] == [{"scheme": "orcid", "identifier": "0000-0001-6071-1857"}]


def test_upload_resumes_skips_unchanged_replaces_changed_and_persists_state(tmp_path):
    _write_config(tmp_path)
    unchanged = tmp_path / "a.log"
    unchanged.write_text("same")
    changed = tmp_path / "b.log"
    changed.write_text("new")
    import hashlib

    fake = FakeClient(
        {
            "a.log": hashlib.md5(b"same", usedforsecurity=False).hexdigest(),
            "b.log": hashlib.md5(b"old", usedforsecurity=False).hexdigest(),
        }
    )
    result = upload_raw_folder(tmp_path, client=fake)
    assert ("upload", "a.log") not in fake.calls
    assert ("delete", "b.log") in fake.calls
    assert ("upload", "b.log") in fake.calls
    state = json.loads((tmp_path / STATE_NAME).read_text())
    assert state["record_id"] == "abc12-def34"
    assert state["reserved_doi"] == "10.5281/zenodo.12345"
    assert "token" not in json.dumps(state).lower()
    assert result["status"] == "draft"

    fake.calls.clear()
    upload_raw_folder(tmp_path, client=fake)
    assert fake.calls[0] == ("get", "abc12-def34")
    assert not any(call[0] == "upload" for call in fake.calls)


def test_reserved_doi_is_refreshed_when_action_response_omits_it(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class RefreshingClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.reserved = False

        def reserve_doi(self, record):
            self.reserved = True
            return {"id": record["id"]}

        def get_draft(self, record_id):
            record = self._record(record_id)
            if self.reserved:
                record["pids"] = {"doi": {"identifier": "10.5281/zenodo.54321"}}
            return record

    result = upload_raw_folder(tmp_path, client=RefreshingClient())
    assert result["reserved_doi"] == "10.5281/zenodo.54321"


def test_stale_state_doi_does_not_suppress_reservation(tmp_path):
    """A draft carrying no DOI must be reserved one even if state claims otherwise.

    Zenodo rejects review submission with "pids.doi.value.identifier: Missing
    data" when the draft only declares a DOI provider, so a ``reserved_doi``
    left over from an earlier record must never gate the reservation call.
    """
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / STATE_NAME).write_text(
        json.dumps(
            {
                "record_id": "abc12-def34",
                "sandbox": False,
                "status": "draft",
                "reserved_doi": "10.5281/zenodo.599544",
            }
        )
    )

    fake = FakeClient()
    result = upload_raw_folder(tmp_path, client=fake)
    assert ("doi", "abc12-def34") in fake.calls
    assert result["reserved_doi"] == "10.5281/zenodo.12345"


def test_review_submission_requires_a_reserved_doi(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class DoiLessClient(FakeClient):
        def reserve_doi(self, record):
            self.calls.append(("doi", record["id"]))
            return {"id": record["id"], "pids": {"doi": {"provider": "datacite"}}}

    fake = DoiLessClient()
    with pytest.raises(ZenodoError, match="no reserved DOI"):
        upload_raw_folder(tmp_path, client=fake, publish=True)
    assert not any(call[0] == "submit_review" for call in fake.calls)


def test_embargo_flag_sets_the_release_date_and_restricts_files(tmp_path):
    (tmp_path / "data.log").write_text("data")
    (tmp_path / CONFIG_NAME).write_text(yaml.safe_dump({"title": "Raw voyage"}))

    public = upload_raw_folder(tmp_path, dry_run=True)["metadata"]["access"]
    assert public["files"] == "public"
    assert public["embargo"]["active"] is False

    embargoed = upload_raw_folder(tmp_path, dry_run=True, embargo="2027-03-01")["metadata"]
    assert embargoed["access"]["files"] == "restricted"
    assert embargoed["access"]["embargo"] == {
        "active": True,
        "until": "2027-03-01",
        "reason": "Author embargo pending publication.",
    }


def test_pending_review_updates_changed_notes_only(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "META.md").write_text("first notes")

    fake = FakeClient()
    upload_raw_folder(tmp_path, client=fake, publish=True)
    assert fake.pending

    # Resuming with unchanged notes must not touch the draft.
    fake.calls.clear()
    upload_raw_folder(tmp_path, client=fake, publish=True)
    assert not any(call[0] == "update" for call in fake.calls)

    # Changing the notes must push them, while leaving the review pending.
    (tmp_path / "META.md").write_text("revised notes")
    fake.calls.clear()
    result = upload_raw_folder(tmp_path, client=fake, publish=True)
    assert ("update", "abc12-def34") in fake.calls
    assert "revised notes" in _notes_of(fake.payload)
    assert result["status"] == "pending_review"
    assert not any(call[0] == "submit_review" for call in fake.calls)


def test_cli_publishes_by_default_and_honours_no_publish(tmp_path, monkeypatch):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    seen = {}

    def fake_upload(folder, **kwargs):
        seen.update(kwargs)
        return {"status": "draft", "record_id": "1", "reserved_doi": "10.5072/zenodo.1"}

    monkeypatch.setattr("yacht_co2.zenodo.upload_raw_folder", fake_upload)
    runner = CliRunner()
    assert runner.invoke(app, [str(tmp_path)]).exit_code == 0
    assert seen["publish"] is True
    assert seen["embargo"] is None

    assert (
        runner.invoke(app, [str(tmp_path), "--no-publish", "--embargo", "2027-03-01"]).exit_code
        == 0
    )
    assert seen["publish"] is False
    assert seen["embargo"] == "2027-03-01"


@pytest.mark.parametrize(
    ("review", "pending"),
    [
        ({"status": "created", "is_closed": False, "is_open": False}, False),
        ({"status": "submitted", "is_closed": False, "is_open": True}, True),
        ({"status": "accepted", "is_closed": True, "is_open": False}, False),
        ({}, False),
    ],
)
def test_only_a_submitted_review_counts_as_pending(tmp_path, review, pending):
    """An attached-but-unsubmitted request must not look like a submitted one."""
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class ReviewingClient(FakeClient):
        def get_review(self, record_id):
            self.calls.append(("get_review", record_id))
            return review

    fake = ReviewingClient()
    (tmp_path / STATE_NAME).write_text(
        json.dumps({"record_id": "abc12-def34", "sandbox": False, "status": "draft"})
    )
    result = upload_raw_folder(tmp_path, client=fake, publish=True)
    submitted = any(call[0] == "submit_review" for call in fake.calls)
    assert submitted is not pending
    assert result["status"] == "pending_review"


def test_doi_and_submission_are_stamped_into_the_yaml(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    fake = FakeClient()

    upload_raw_folder(tmp_path, client=fake, publish=False, today=date(2025, 6, 1))
    stamped = yaml.safe_load((tmp_path / CONFIG_NAME).read_text())
    assert stamped["doi"] == "10.5281/zenodo.12345"
    assert "submitted" not in stamped

    upload_raw_folder(tmp_path, client=fake, publish=True, today=date(2025, 6, 1))
    stamped = yaml.safe_load((tmp_path / CONFIG_NAME).read_text())
    assert stamped["doi"] == "10.5281/zenodo.12345"
    assert stamped["submitted"] == "2025-06-01"
    assert stamped["title"] == "Raw voyage"


def test_vanished_record_reports_how_to_recover(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / STATE_NAME).write_text(
        json.dumps({"record_id": "599544", "sandbox": False, "status": "draft"})
    )

    class MissingClient(FakeClient):
        def get_draft(self, record_id):
            raise ZenodoError(f"Zenodo GET /api/records/{record_id}/draft: HTTP 404: gone")

        def get_record(self, record_id):
            raise ZenodoError(f"Zenodo GET /api/records/{record_id}: HTTP 404: gone")

    with pytest.raises(ZenodoError, match="no longer exists") as error:
        upload_raw_folder(tmp_path, client=MissingClient())
    assert STATE_NAME in str(error.value)


def test_unreadable_draft_is_discarded_and_versioned_again(tmp_path):
    """A draft Zenodo can no longer serialize is deleted and branched afresh.

    Such a draft answers every read with HTTP 500 and blocks new versions of
    its concept, so the only way forward is to discard it and version the
    parent again.
    """
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / STATE_NAME).write_text(
        json.dumps(
            {
                "record_id": "broken",
                "parent_record_id": "published",
                "sandbox": False,
                "status": "draft",
            }
        )
    )

    class BrokenDraftClient(FakeClient):
        def get_draft(self, record_id):
            if record_id == "broken":
                raise ZenodoError("Zenodo GET /api/records/broken/draft: HTTP 500: internal error")
            return super().get_draft(record_id)

        def get_record(self, record_id):
            if record_id == "broken":
                raise ZenodoError("Zenodo GET /api/records/broken: HTTP 404: not registered")
            return super().get_record(record_id)

        def create_new_version(self, record_id):
            self.calls.append(("new_version", record_id))
            return self._record("fresh-draft")

    fake = BrokenDraftClient()
    result = upload_raw_folder(tmp_path, client=fake)

    assert ("delete_draft", "broken") in fake.calls
    # Versioning the parent needs no --new-version: the draft this run meant to
    # write to no longer exists.
    assert ("new_version", "published") in fake.calls
    assert result["record_id"] == "fresh-draft"
    assert ("upload", "data.log") in fake.calls
    state = json.loads((tmp_path / STATE_NAME).read_text())
    assert "parent_record_id" not in state or state["parent_record_id"] == "published"


def test_a_new_version_draft_records_its_parent(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class PublishedClient(FakeClient):
        def get_draft(self, record_id):
            if record_id == "published":
                raise ZenodoError("HTTP 404")
            return super().get_draft(record_id)

    upload_raw_folder(tmp_path, client=PublishedClient(), record_id="published", new_version=True)
    state = json.loads((tmp_path / STATE_NAME).read_text())
    assert state["parent_record_id"] == "published"


def test_a_new_version_is_published_instead_of_sent_for_review(tmp_path):
    """Zenodo rejects a review request for a new version of a published record."""
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class PublishedClient(FakeClient):
        def get_draft(self, record_id):
            if record_id == "published":
                raise ZenodoError("HTTP 404")
            return super().get_draft(record_id)

    fake = PublishedClient()
    result = upload_raw_folder(
        tmp_path,
        client=fake,
        record_id="published",
        new_version=True,
        publish=True,
        today=date(2025, 6, 1),
    )

    assert not any(call[0] in {"set_review", "submit_review"} for call in fake.calls)
    assert ("publish_draft", "abc12-def34") in fake.calls
    assert result["status"] == "published"
    assert result["record_url"] == "https://zenodo.test/records/abc12-def34"
    assert yaml.safe_load((tmp_path / "zenodo.yaml").read_text())["submitted"] == "2025-06-01"


def test_a_resumed_versioned_draft_is_published_from_its_version_index(tmp_path):
    """A draft that knows its own version index needs no remembered parent."""
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class VersionedClient(FakeClient):
        @staticmethod
        def _record(record_id="abc12-def34"):
            return {**FakeClient._record(record_id), "versions": {"index": 3}}

    fake = VersionedClient()
    result = upload_raw_folder(tmp_path, client=fake, publish=True)

    assert not any(call[0] == "submit_review" for call in fake.calls)
    assert result["status"] == "published"


def test_remote_only_blocks_review_or_is_pruned(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "local.log").write_text("data")
    fake = FakeClient({"old.log": "0" * 32})
    with pytest.raises(ZenodoError, match="remote-only files block"):
        upload_raw_folder(tmp_path, client=fake, publish=True)
    assert not any(call[0] == "set_review" for call in fake.calls)

    result = upload_raw_folder(tmp_path, client=fake, publish=True, prune=True)
    assert ("delete", "old.log") in fake.calls
    assert ("set_review", "vendee-globe-co2") in fake.calls
    assert result["status"] == "pending_review"

    fake.calls.clear()
    assert upload_raw_folder(tmp_path, client=fake, publish=True)["status"] == "pending_review"
    # A pending resume also lists the remote files so it can warn about any
    # local change the frozen draft cannot accept.
    assert fake.calls == [
        ("get", "abc12-def34"),
        ("get_review", "abc12-def34"),
        ("list", "abc12-def34"),
    ]


def test_published_record_requires_and_creates_new_version(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class PublishedClient(FakeClient):
        def get_draft(self, record_id):
            if record_id == "published":
                raise ZenodoError("HTTP 404")
            return super().get_draft(record_id)

        def create_new_version(self, record_id):
            self.calls.append(("new_version", record_id))
            return self._record("new12-draft")

    fake = PublishedClient()
    with pytest.raises(ZenodoError, match="--new-version"):
        upload_raw_folder(tmp_path, client=fake, record_id="published")
    result = upload_raw_folder(tmp_path, client=fake, record_id="published", new_version=True)
    assert ("new_version", "published") in fake.calls
    assert result["record_id"] == "new12-draft"


def test_sandbox_uses_dedicated_environment_token(tmp_path, monkeypatch):
    _write_config(tmp_path, sandbox=True)
    (tmp_path / "data.log").write_text("data")
    fake = FakeClient()
    captured = {}

    def client_factory(token, *, sandbox):
        captured.update(token=token, sandbox=sandbox)
        return fake

    monkeypatch.setenv("ZENODO_SANDBOX_ACCESS_TOKEN", "sandbox-token")
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("yacht_co2.zenodo.ZenodoClient", client_factory)
    upload_raw_folder(tmp_path)
    assert captured == {"token": "sandbox-token", "sandbox": True}


def test_token_is_loaded_from_user_config_dotenv_without_overriding_exports(tmp_path, monkeypatch):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    from yacht_co2.userconfig import config_dir

    config_dir().mkdir()
    (config_dir() / ".env").write_text("ZENODO_ACCESS_TOKEN=config-token\n")
    fake = FakeClient()
    captured = {}

    def client_factory(token, *, sandbox):
        captured.update(token=token, sandbox=sandbox)
        return fake

    monkeypatch.setenv("ZENODO_ACCESS_TOKEN", "exported-token")
    monkeypatch.setattr("yacht_co2.zenodo.ZenodoClient", client_factory)
    upload_raw_folder(tmp_path)
    assert captured == {"token": "exported-token", "sandbox": False}

    (tmp_path / STATE_NAME).unlink()
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN")
    upload_raw_folder(tmp_path)
    assert captured == {"token": "config-token", "sandbox": False}


class FakeResponse:
    """Minimal stand-in for ``requests.Response`` used by the fake session."""

    def __init__(self, status_code=200, *, json_data=None, text=None, headers=None, content=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self.reason = "OK" if self.ok else "ERROR"
        self.headers = dict(headers or {})
        self._json = json_data
        if content is not None:
            self.content = content
        elif json_data is not None:
            self.content = b"{...}"
        else:
            self.content = b""
        self.text = text if text is not None else (json.dumps(json_data) if json_data else "")

    def json(self):
        if self._json is None:
            raise ValueError("response has no JSON body")
        return self._json


class FakeSession:
    """Records every request and replays queued responses in order."""

    def __init__(self, responses):
        self.calls: list[dict] = []
        self._responses = list(responses)

    def request(self, method, url, **kwargs):
        data = kwargs.get("data")
        body = data.read() if hasattr(data, "read") else data
        self.calls.append({"method": method, "url": url, "body": body, **kwargs})
        return self._responses.pop(0)


def test_client_hits_expected_records_api_urls_with_bearer_auth_only():
    token = "tok-urls"  # noqa: S105
    base = "https://zenodo.org"
    session = FakeSession(
        [
            FakeResponse(200, json_data={"id": "rec1"}),  # create_draft
            FakeResponse(200, json_data={"id": "rec1"}),  # get_draft
            FakeResponse(200, json_data={"id": "rec1"}),  # get_record
            FakeResponse(200, json_data={"id": "rec1"}),  # update_draft
            FakeResponse(200, json_data={"id": "rec2"}),  # create_new_version
            FakeResponse(200, json_data={"entries": []}),  # import_files
            FakeResponse(200, json_data={"entries": []}),  # list_files
            FakeResponse(204, content=b""),  # delete_file
            FakeResponse(200, json_data={"status": "open"}),  # get_review
            FakeResponse(200, json_data={"status": "submitted"}),  # submit_review
        ]
    )
    client = ZenodoClient(token, session=session)

    client.create_draft({"metadata": {"title": "x"}})
    client.get_draft("rec1")
    client.get_record("rec1")
    client.update_draft("rec1", {"metadata": {"title": "y"}})
    client.create_new_version("rec1")
    client.import_files("rec2")
    client.list_files("rec1")
    client.delete_file("rec1", "a b/c.csv")
    client.get_review("rec1")
    client.submit_review("rec1")

    calls = session.calls
    assert (calls[0]["method"], calls[0]["url"]) == ("POST", f"{base}/api/records")
    assert (calls[1]["method"], calls[1]["url"]) == ("GET", f"{base}/api/records/rec1/draft")
    assert (calls[2]["method"], calls[2]["url"]) == ("GET", f"{base}/api/records/rec1")
    assert (calls[3]["method"], calls[3]["url"]) == ("PUT", f"{base}/api/records/rec1/draft")
    assert (calls[4]["method"], calls[4]["url"]) == ("POST", f"{base}/api/records/rec1/versions")
    assert (calls[5]["method"], calls[5]["url"]) == (
        "POST",
        f"{base}/api/records/rec2/draft/actions/files-import",
    )
    assert (calls[6]["method"], calls[6]["url"]) == ("GET", f"{base}/api/records/rec1/draft/files")
    assert (calls[7]["method"], calls[7]["url"]) == (
        "DELETE",
        f"{base}/api/records/rec1/draft/files/a%20b%2Fc.csv",
    )
    assert (calls[8]["method"], calls[8]["url"]) == ("GET", f"{base}/api/records/rec1/draft/review")
    assert (calls[9]["method"], calls[9]["url"]) == (
        "POST",
        f"{base}/api/records/rec1/draft/actions/submit-review",
    )
    for call in calls:
        assert call["headers"]["Authorization"] == f"Bearer {token}"
        assert token not in call["url"]


def test_sandbox_flag_selects_sandbox_base_url():
    assert ZenodoClient("tok", sandbox=True, session=FakeSession([])).base_url == (
        "https://sandbox.zenodo.org"
    )
    assert ZenodoClient("tok", sandbox=False, session=FakeSession([])).base_url == (
        "https://zenodo.org"
    )


def test_error_response_and_transport_exception_both_redact_token(monkeypatch):
    token = "super-secret-token"  # noqa: S105
    monkeypatch.setattr("yacht_co2.zenodo.time.sleep", lambda *a, **k: None)

    error_session = FakeSession(
        [FakeResponse(400, json_data={"message": f"token {token} rejected"})]
    )
    client = ZenodoClient(token, session=error_session, retries=1)
    with pytest.raises(ZenodoError) as excinfo:
        client.get_record("rec1")
    assert token not in str(excinfo.value)
    assert "<redacted>" in str(excinfo.value)

    class RaisingSession:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, **kwargs):
            self.calls += 1
            raise requests.RequestException(f"connection reset for token {token}")

    raising_session = RaisingSession()
    client2 = ZenodoClient(token, session=raising_session, retries=1)
    with pytest.raises(ZenodoError) as excinfo2:
        client2.get_record("rec1")
    assert token not in str(excinfo2.value)
    assert raising_session.calls == 1


def test_retry_after_429_then_success_issues_exactly_two_requests(monkeypatch):
    monkeypatch.setattr("yacht_co2.zenodo.time.sleep", lambda *a, **k: None)
    session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(200, json_data={"ok": True}),
        ]
    )
    client = ZenodoClient("tok", session=session)
    assert client.get_record("rec1") == {"ok": True}
    assert len(session.calls) == 2


def test_persistent_500_raises_after_exactly_retries_attempts(monkeypatch):
    monkeypatch.setattr("yacht_co2.zenodo.time.sleep", lambda *a, **k: None)
    session = FakeSession([FakeResponse(500) for _ in range(3)])
    client = ZenodoClient("tok", session=session, retries=3)
    with pytest.raises(ZenodoError):
        client.get_record("rec1")
    assert len(session.calls) == 3


def test_404_is_not_retried(monkeypatch):
    monkeypatch.setattr("yacht_co2.zenodo.time.sleep", lambda *a, **k: None)
    session = FakeSession([FakeResponse(404, json_data={"message": "not found"})])
    client = ZenodoClient("tok", session=session)
    with pytest.raises(ZenodoError):
        client.get_record("rec1")
    assert len(session.calls) == 1


def test_error_detail_reports_both_field_and_message():
    body = {
        "status": 400,
        "message": "Validation error.",
        "errors": [{"field": "metadata.title", "messages": ["Missing data."]}],
    }
    session = FakeSession([FakeResponse(400, json_data=body)])
    client = ZenodoClient("tok", session=session)
    with pytest.raises(ZenodoError) as excinfo:
        client.create_draft({"metadata": {}})
    assert "metadata.title" in str(excinfo.value)
    assert "Missing data." in str(excinfo.value)


def test_upload_file_prefers_response_links_over_constructed_urls(tmp_path):
    path = tmp_path / "file.bin"
    payload_bytes = b"hello zenodo" * 10
    path.write_bytes(payload_bytes)

    session = FakeSession(
        [
            FakeResponse(
                200,
                json_data={
                    "entries": [
                        {
                            "key": "file.bin",
                            "links": {
                                "content": "https://zenodo.org/custom/content",
                                "commit": "https://zenodo.org/custom/commit",
                            },
                        }
                    ]
                },
            ),
            FakeResponse(200, content=b""),
            FakeResponse(200, json_data={"key": "file.bin", "checksum": "md5:abc123"}),
        ]
    )
    client = ZenodoClient("tok", session=session)
    committed = client.upload_file("rec1", path)

    assert committed == {"key": "file.bin", "checksum": "md5:abc123"}
    init_call, put_call, commit_call = session.calls
    assert init_call["method"] == "POST"
    assert init_call["json"] == [{"key": "file.bin"}]
    assert put_call["method"] == "PUT"
    assert put_call["url"] == "https://zenodo.org/custom/content"
    assert put_call["headers"]["Content-Type"] == "application/octet-stream"
    assert put_call["body"] == payload_bytes
    assert commit_call["method"] == "POST"
    assert commit_call["url"] == "https://zenodo.org/custom/commit"


def test_upload_file_falls_back_to_constructed_urls_when_links_missing(tmp_path):
    path = tmp_path / "plain.bin"
    path.write_bytes(b"plain content")

    session = FakeSession(
        [
            FakeResponse(200, json_data={"entries": [{"key": "plain.bin"}]}),
            FakeResponse(200, content=b""),
            FakeResponse(200, json_data={"key": "plain.bin", "checksum": "md5:def456"}),
        ]
    )
    client = ZenodoClient("tok", session=session)
    committed = client.upload_file("rec1", path)

    base = "https://zenodo.org/api/records/rec1/draft/files/plain.bin"
    assert session.calls[1]["url"] == f"{base}/content"
    assert session.calls[2]["url"] == f"{base}/commit"
    assert committed["checksum"] == "md5:def456"


@pytest.mark.parametrize(
    "first_response",
    [
        FakeResponse(400, json_data={"message": "duplicate key"}),
        FakeResponse(
            200,
            json_data={"entries": [], "errors": [{"field": "key", "messages": ["exists"]}]},
        ),
    ],
    ids=["http-400", "soft-error-list"],
)
def test_upload_file_recovers_from_duplicate_or_stale_key(tmp_path, first_response):
    path = tmp_path / "dup.bin"
    path.write_bytes(b"dup content")

    session = FakeSession(
        [
            first_response,
            FakeResponse(204, content=b""),  # delete stale key
            FakeResponse(200, json_data={"entries": [{"key": "dup.bin"}]}),  # re-initialise
            FakeResponse(200, content=b""),  # put content
            FakeResponse(200, json_data={"key": "dup.bin", "checksum": "md5:feedface"}),
        ]
    )
    client = ZenodoClient("tok", session=session)
    committed = client.upload_file("rec1", path)

    methods = [call["method"] for call in session.calls]
    assert methods == ["POST", "DELETE", "POST", "PUT", "POST"]
    assert session.calls[1]["url"].endswith("/draft/files/dup.bin")
    assert committed["checksum"] == "md5:feedface"


def test_file_entries_normalises_list_dict_and_bare_list_shapes():
    assert _file_entries({"entries": [{"key": "a"}, {"key": "b"}]}) == [
        {"key": "a"},
        {"key": "b"},
    ]
    keyed = _file_entries({"entries": {"a.txt": {"size": 1}, "b.txt": {"size": 2}}})
    assert {entry["key"]: entry["size"] for entry in keyed} == {"a.txt": 1, "b.txt": 2}
    assert _file_entries([{"key": "c"}]) == [{"key": "c"}]
    assert _file_entries(None) == []


def test_set_review_resolves_community_slug_once_and_caches_it():
    session = FakeSession(
        [
            FakeResponse(200, json_data={"id": "uuid-1234", "slug": "some-slug"}),
            FakeResponse(200, json_data={"status": "created"}),
            FakeResponse(200, json_data={"status": "created"}),
        ]
    )
    client = ZenodoClient("tok", session=session)

    client.set_review("rec1", "some-slug")
    client.set_review("rec1", "some-slug")

    gets = [call for call in session.calls if call["method"] == "GET"]
    puts = [call for call in session.calls if call["method"] == "PUT"]
    assert len(gets) == 1
    assert gets[0]["url"] == "https://zenodo.org/api/communities/some-slug"
    assert len(puts) == 2
    for put in puts:
        assert put["url"] == "https://zenodo.org/api/records/rec1/draft/review"
        assert put["json"] == {
            "receiver": {"community": "uuid-1234"},
            "type": "community-submission",
        }


def test_with_pids_preserves_reserved_doi_only_when_present():
    # The real payload always carries the DOI intent a new draft is created
    # with, so the update must decide what to do with it rather than inherit it.
    payload = {"metadata": {"title": "x"}, "pids": {"doi": {"provider": "datacite"}}}
    with_doi = _with_pids(payload, {"pids": {"doi": {"identifier": "10.5281/zenodo.1"}}})
    assert with_doi["pids"] == {"doi": {"identifier": "10.5281/zenodo.1"}}

    intent = _with_pids(payload, {"pids": {"doi": {"provider": "datacite"}}})
    assert intent["pids"] == {"doi": {"provider": "datacite"}}

    # A new version draft carries no DOI. Echoing the intent back at one makes
    # Zenodo answer HTTP 500 and leaves the draft unreadable for good, so the
    # update must send nothing and let the explicit reservation mint the DOI.
    without_doi = _with_pids(payload, {"pids": {}})
    assert without_doi["pids"] == {}

    no_pids_at_all = _with_pids(payload, {})
    assert no_pids_at_all["pids"] == {}

    # The caller's payload is never mutated, so one payload serves every draft.
    assert payload["pids"] == {"doi": {"provider": "datacite"}}


def test_direct_cli_requires_a_name_then_generates_config(tmp_path):
    runner = CliRunner()
    missing = runner.invoke(app, [str(tmp_path), "--dry-run"])
    assert missing.exit_code != 0
    assert "--campaign and --campaign-date" in missing.output
    valid = runner.invoke(app, [str(tmp_path), "--title", "Raw voyage", "--dry-run"])
    assert valid.exit_code == 0
    assert "dry run valid" in valid.output
    assert (tmp_path / CONFIG_NAME).exists()


def test_subfolders_are_reported_as_unuploadable(tmp_path, logs):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / "casts").mkdir()
    (tmp_path / "casts" / "cast01.cnv").write_text("nested")
    (tmp_path / "photos").mkdir()
    (tmp_path / ".hidden").mkdir()

    result = upload_raw_folder(tmp_path, dry_run=True)
    assert result["skipped_folders"] == ["casts/", "photos/"]
    assert set(result["files"]) == {"data.log"}
    warning = next(line for line in logs if "cannot contain directories" in line)
    assert "casts/, photos/" in warning
    assert any("Pack a subfolder into a single archive" in line for line in logs)

    fake = FakeClient()
    state = upload_raw_folder(tmp_path, client=fake, publish=False)
    assert state["skipped_folders"] == ["casts/", "photos/"]
    assert [call for call in fake.calls if call[0] == "upload"] == [("upload", "data.log")]


def test_cli_dry_run_lists_skipped_subfolders(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / "casts").mkdir()

    output = CliRunner().invoke(app, [str(tmp_path), "--dry-run"])
    assert output.exit_code == 0, output.output
    assert "skipped subfolders: casts/" in output.output


def test_pending_review_warns_that_new_files_are_frozen(tmp_path, logs):
    _write_config(tmp_path)
    (tmp_path / "a.log").write_text("first")

    fake = FakeClient()
    upload_raw_folder(tmp_path, client=fake, publish=True)
    assert fake.pending

    (tmp_path / "b.log").write_text("added later")
    (tmp_path / "a.log").write_text("edited later")
    logs.clear()
    fake.calls.clear()
    result = upload_raw_folder(tmp_path, client=fake, publish=True)

    assert result["status"] == "pending_review"
    assert not any(call[0] == "upload" for call in fake.calls)
    frozen = next(line for line in logs if "files are frozen" in line)
    assert "1 new and 1 changed" in frozen
    assert "b.log, a.log" in frozen
    assert any("--new-version" in line for line in logs)


def test_upload_logs_the_file_plan_and_per_file_progress(tmp_path, logs):
    import hashlib

    _write_config(tmp_path)
    (tmp_path / "a.log").write_text("same")
    (tmp_path / "b.log").write_text("new")
    fake = FakeClient(
        {
            "a.log": hashlib.md5(b"same", usedforsecurity=False).hexdigest(),
            "b.log": hashlib.md5(b"old", usedforsecurity=False).hexdigest(),
            "gone.log": "0" * 32,
        }
    )

    upload_raw_folder(tmp_path, client=fake, publish=False)

    assert any("file plan: 0 new, 1 changed, 1 unchanged, 1 remote-only" in line for line in logs)
    assert any("exist only in Zenodo draft" in line and "gone.log" in line for line in logs)
    assert any("Zenodo upload 1/1: b.log (replacing changed file)" in line for line in logs)
    assert any(
        "now holds 2 file(s): 1 uploaded this run, 1 already present" in line for line in logs
    )


def test_title_is_generated_from_the_campaign_and_slugged_by_folder_name(tmp_path):
    folder = tmp_path / "2023-07-24_oliver-heer_fastnet"
    folder.mkdir()
    (folder / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet Race", "campaign_date": "2023-07-24"})
    )

    resolved = load_zenodo_config(folder)
    assert resolved["title"] == (
        "Surface ocean CO2 measurements on board YOROSHIKU (Oliver Heer) during the "
        "Fastnet Race (2023-07-24)"
    )
    assert resolved["slug"] == "2023-07-24_oliver-heer_fastnet"

    metadata = upload_raw_folder(folder, dry_run=True)["metadata"]["metadata"]
    assert metadata["title"] == resolved["title"]
    assert metadata["identifiers"] == [
        {"scheme": "other", "identifier": "2023-07-24_oliver-heer_fastnet"}
    ]
    assert metadata["dates"] == [
        {
            "date": "2023-07-24",
            "type": {"id": "collected"},
            "description": "Campaign date",
        }
    ]


def test_campaign_date_accepts_year_and_month_precision(tmp_path):
    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Route du Rhum", "campaign_date": "2022-11"})
    )
    assert load_zenodo_config(tmp_path)["title"].endswith("during the Route du Rhum (2022-11)")

    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Vendee Globe", "campaign_date": "2024"})
    )
    assert load_zenodo_config(tmp_path)["title"].endswith("during the Vendee Globe (2024)")

    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet", "campaign_date": "24 July 2023"})
    )
    with pytest.raises(ZenodoError, match="invalid campaign_date"):
        load_zenodo_config(tmp_path)


def test_a_title_cannot_be_combined_with_a_campaign(tmp_path):
    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump(
            {"title": "Hand written", "campaign": "Fastnet Race", "campaign_date": "2023-07-24"}
        )
    )
    with pytest.raises(ZenodoError, match="title cannot be combined with campaign"):
        load_zenodo_config(tmp_path)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "campaign and campaign_date required"),
        ({"campaign": "Fastnet Race"}, "campaign_date required"),
        ({"campaign_date": "2023-07-24"}, "campaign required"),
    ],
)
def test_campaign_and_campaign_date_are_both_required(tmp_path, config, message):
    (tmp_path / CONFIG_NAME).write_text(yaml.safe_dump(config) if config else "{}\n")
    with pytest.raises(ZenodoError, match=message):
        load_zenodo_config(tmp_path)


def test_title_template_is_overridable_and_validated(tmp_path):
    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump(
            {
                "campaign": "Fastnet Race",
                "campaign_date": "2023-07-24",
                "title_template": "{campaign} {year} from {vessel} [{slug}]",
            }
        )
    )
    assert load_zenodo_config(tmp_path)["title"] == (
        f"Fastnet Race 2023 from YOROSHIKU (Oliver Heer) [{tmp_path.name}]"
    )

    (tmp_path / CONFIG_NAME).write_text(
        yaml.safe_dump(
            {
                "campaign": "Fastnet Race",
                "campaign_date": "2023-07-24",
                "title_template": "{campaign} on {skipper}",
            }
        )
    )
    with pytest.raises(ZenodoError, match="unknown field\\(s\\) skipper"):
        load_zenodo_config(tmp_path)


def test_defaults_are_inherited_from_a_parent_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    folder = project / "data" / "2023-07-24_oliver-heer_fastnet"
    folder.mkdir(parents=True)
    write_defaults(project, {**PROJECT_DEFAULTS, "community": "from-project", "vessel": "Fleur"})
    (folder / CONFIG_NAME).write_text(
        yaml.safe_dump({"campaign": "Fastnet Race", "campaign_date": "2023-07-24"})
    )
    # An unrelated working directory must not be needed to find them.
    monkeypatch.chdir(tmp_path)

    resolved = load_zenodo_config(folder)
    assert resolved["community"] == "from-project"
    assert "on board Fleur during the Fastnet Race" in resolved["title"]


def test_the_legacy_defaults_filename_still_works(tmp_path, monkeypatch):
    project = tmp_path / "project"
    folder = project / "voyage"
    folder.mkdir(parents=True)
    (project / ".env.zenodo").write_text(
        yaml.safe_dump({**PROJECT_DEFAULTS, "community": "from-legacy"})
    )
    (folder / CONFIG_NAME).write_text(yaml.safe_dump({"title": "Raw voyage"}))
    monkeypatch.chdir(tmp_path)

    assert load_zenodo_config(folder)["community"] == "from-legacy"


def test_a_generated_config_keeps_the_campaign_not_the_rendered_title(tmp_path):
    folder = tmp_path / "2023-07-24_oliver-heer_fastnet"
    folder.mkdir()

    path = generate_zenodo_config(
        folder, overrides={"campaign": "Fastnet Race", "campaign_date": "2023-07-24"}
    )
    generated = yaml.safe_load(path.read_text())
    assert generated["campaign"] == "Fastnet Race"
    assert generated["campaign_date"] == "2023-07-24"
    # A persisted title would collide with the campaign on the next run.
    assert "title" not in generated
    assert "Fastnet Race (2023-07-24)" in load_zenodo_config(folder)["title"]
