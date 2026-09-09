import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from yacht_co2.errors import ZenodoError
from yacht_co2.zenodo import (
    CONFIG_NAME,
    STATE_NAME,
    ZenodoClient,
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
    assert people[0]["identifiers"] == [
        {"scheme": "orcid", "identifier": "0000-0001-6071-1857"}
    ]


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


def test_generate_config_dates_and_folder_precedence(tmp_path):
    path = generate_zenodo_config(
        tmp_path,
        "Raw data",
        overrides={"community": "generated"},
        today=date(2024, 2, 29),
    )
    generated = yaml.safe_load(path.read_text())
    assert generated["publication_date"] == "2024-02-29"
    assert generated["embargo"]["until"] == "2025-02-28"
    assert generated["creators"] == ["Gregor, Luke, 0000-0001-6071-1857"]

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


def test_embargo_controls_and_invalid_dates(tmp_path):
    (tmp_path / CONFIG_NAME).write_text("title: Test\nembargo: {enabled: false}\n")
    assert load_zenodo_config(tmp_path)["embargo"]["until"] is None
    enabled = load_zenodo_config(
        tmp_path, overrides={"embargo": {"enabled": True, "until": "2027-01-01"}}
    )
    assert enabled["embargo"] == {"enabled": True, "months": 12, "until": "2027-01-01"}
    with pytest.raises(ZenodoError, match="invalid embargo"):
        load_zenodo_config(
            tmp_path, overrides={"embargo": {"enabled": True, "until": "soon"}}
        )


class FakeClient:
    def __init__(self, remote=None):
        self.remote = dict(remote or {})
        self.calls = []
        self.payload = None
        self.pending = False

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
        return self._record()

    def get_draft(self, record_id):
        self.calls.append(("get", record_id))
        return self._record(record_id)

    def get_record(self, record_id):
        self.calls.append(("get_record", record_id))
        return {**self._record(record_id), "status": "published"}

    def get_review(self, record_id):
        self.calls.append(("get_review", record_id))
        return {"status": "submitted"} if self.pending else {}

    def update_draft(self, record_id, payload):
        self.calls.append(("update", record_id))
        self.payload = payload
        return self._record(record_id)

    def reserve_doi(self, record):
        self.calls.append(("doi", record["id"]))
        return {
            **self._record(record["id"]),
            "pids": {"doi": {"identifier": "10.5281/zenodo.12345"}},
        }

    def list_files(self, record_id):
        self.calls.append(("list", record_id))
        return [{"key": key, "checksum": f"md5:{checksum}"} for key, checksum in self.remote.items()]

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

    def request_json(self, method, path):
        raise AssertionError(f"unexpected raw request: {method} {path}")


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

    result = upload_raw_folder(
        tmp_path, title="Raw voyage", dry_run=True, today=date(2025, 3, 2)
    )
    assert set(result["files"]) == {"README.md", "data.log"}
    assert (tmp_path / CONFIG_NAME).exists()
    assert not (tmp_path / STATE_NAME).exists()
    notes = result["metadata"]["metadata"]["additional_descriptions"][0]["description"]
    assert "&lt;script&gt;" in notes and "<script>" not in notes


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
    assert fake.calls == [("get", "abc12-def34"), ("get_review", "abc12-def34")]


def test_published_record_requires_and_creates_new_version(tmp_path):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")

    class PublishedClient(FakeClient):
        def get_draft(self, record_id):
            raise ZenodoError("HTTP 404")

        def create_new_version(self, record_id):
            self.calls.append(("new_version", record_id))
            return self._record("new12-draft")

    fake = PublishedClient()
    with pytest.raises(ZenodoError, match="--new-version"):
        upload_raw_folder(tmp_path, client=fake, record_id="published")
    result = upload_raw_folder(
        tmp_path, client=fake, record_id="published", new_version=True
    )
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


def test_token_is_loaded_from_folder_dotenv_without_overriding_exports(tmp_path, monkeypatch):
    _write_config(tmp_path)
    (tmp_path / "data.log").write_text("data")
    (tmp_path / ".env").write_text("ZENODO_ACCESS_TOKEN=folder-token\n")
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
    assert captured == {"token": "folder-token", "sandbox": False}


class StubResponse:
    ok = False
    status_code = 401
    content = b""
    headers = {}

    def __init__(self, text):
        self.text = text


class StubSession:
    def __init__(self, token):
        self.token = token
        self.headers = None

    def request(self, method, url, headers, timeout, **kwargs):
        self.headers = headers
        return StubResponse(f"bad token {self.token}")


def test_client_uses_bearer_auth_sandbox_and_redacts_token():
    token = "very-secret-token"
    session = StubSession(token)
    client = ZenodoClient(token, sandbox=True, session=session, retries=1)
    with pytest.raises(ZenodoError) as error:
        client.request_json("GET", "/api/records/test")
    assert session.headers["Authorization"] == f"Bearer {token}"
    assert "sandbox.zenodo.org" in str(error.value)
    assert token not in str(error.value)


def test_client_rewinds_stream_when_retrying(monkeypatch):
    class Response:
        content = b""
        headers = {}
        text = ""

        def __init__(self, status_code):
            self.status_code = status_code
            self.ok = status_code < 400

    class RetrySession:
        def __init__(self):
            self.bodies = []
            self.responses = [Response(503), Response(200)]

        def request(self, method, url, headers, timeout, **kwargs):
            self.bodies.append(kwargs["data"].read())
            return self.responses.pop(0)

    session = RetrySession()
    monkeypatch.setattr("yacht_co2.zenodo.time.sleep", lambda _: None)
    client = ZenodoClient("token", session=session, retries=2)
    client._request("PUT", "/api/upload", data=BytesIO(b"streamed payload"))
    assert session.bodies == [b"streamed payload", b"streamed payload"]


def test_direct_cli_requires_title_then_generates_config(tmp_path):
    runner = CliRunner()
    missing = runner.invoke(app, [str(tmp_path), "--dry-run"])
    assert missing.exit_code != 0
    assert "--title is required" in missing.output
    valid = runner.invoke(app, [str(tmp_path), "--title", "Raw voyage", "--dry-run"])
    assert valid.exit_code == 0
    assert "dry run valid" in valid.output
    assert (tmp_path / CONFIG_NAME).exists()
