from __future__ import annotations

import pytest
import yaml

from yacht_co2 import raw_import
from yacht_co2.errors import YachtCO2Error
from yacht_co2.manifest import load_manifest
from yacht_co2.raw_import import (
    RawLog,
    UploadLimits,
    ensure_campaign_config,
    import_raw_logs,
    normalise_campaign_id,
    process_raw_logs_directly,
)


def test_normalise_campaign_id_has_a_stable_safe_form():
    assert normalise_campaign_id(" Fastnet--Race! ", "2023-07-24") == "fastnet__race-2023-07-24"
    assert normalise_campaign_id("A / B", "2023-07") == "a___b-2023-07"


@pytest.mark.parametrize("name,date", [("", "2023-07"), ("!!!", "2023-07"), ("race", "2023"), ("race", "2023-13"), ("race", "2023-02-31")])
def test_normalise_campaign_id_rejects_missing_or_invalid_parts(name, date):
    with pytest.raises(YachtCO2Error):
        normalise_campaign_id(name, date)


def test_import_stages_files_and_never_overwrites_a_campaign(tmp_path):
    root = tmp_path / "data"
    imported = import_raw_logs(
        root,
        "Fastnet Race",
        "2023-07-24",
        [RawLog("one.log", b"one"), RawLog("two.LOG", b"two")],
    )

    assert imported == root / "fastnet_race-2023-07-24"
    assert (imported / "one.log").read_bytes() == b"one"
    archive_config = yaml.safe_load((imported / "zenodo.yaml").read_text(encoding="utf-8"))
    assert archive_config == {
        "campaign": "Fastnet Race",
        "campaign_date": "2023-07-24",
    }
    with pytest.raises(YachtCO2Error, match="already exists"):
        import_raw_logs(root, "Fastnet Race", "2023-07-24", [RawLog("new.log", b"new")])
    assert not (imported / "new.log").exists()


def test_import_preserves_an_existing_empty_campaign_folder(tmp_path):
    existing = tmp_path / "race-2023-07"
    existing.mkdir()

    with pytest.raises(YachtCO2Error, match="already exists"):
        import_raw_logs(tmp_path, "Race", "2023-07", [RawLog("new.log", b"new")])

    assert existing.is_dir()
    assert list(existing.iterdir()) == []


def test_ensure_campaign_config_writes_metadata_and_preserves_existing_config(tmp_path):
    folder = tmp_path / "legacy"

    config = ensure_campaign_config(folder, "Défi Azimut", "2022-09")

    assert yaml.safe_load(config.read_text(encoding="utf-8")) == {
        "campaign": "Défi Azimut",
        "campaign_date": "2022-09",
    }
    config.write_text("campaign: Edited\ndoi: 10.5281/zenodo.123\n", encoding="utf-8")
    assert ensure_campaign_config(folder, "Other", "2024-01") == config
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == {
        "campaign": "Edited",
        "doi": "10.5281/zenodo.123",
    }


@pytest.mark.parametrize("filename", ["../outside.log", "nested/file.log", "nested\\file.log", "report.txt", ".log"])
def test_import_rejects_unsafe_or_non_log_names_without_creating_a_folder(tmp_path, filename):
    with pytest.raises(YachtCO2Error):
        import_raw_logs(tmp_path, "Race", "2023-07", [RawLog(filename, b"raw")])
    assert list(tmp_path.iterdir()) == []


def test_import_rejects_duplicates_and_limits_before_writing(tmp_path):
    files = [RawLog("same.log", b"a"), RawLog("same.log", b"b")]
    with pytest.raises(YachtCO2Error, match="distinct"):
        import_raw_logs(tmp_path, "Race", "2023-07", files)
    with pytest.raises(YachtCO2Error, match="At most 1"):
        import_raw_logs(tmp_path, "Race", "2023-07", files, limits=UploadLimits(max_files=1))
    with pytest.raises(YachtCO2Error, match="limit"):
        import_raw_logs(
            tmp_path,
            "Race",
            "2023-07",
            [RawLog("one.log", b"12")],
            limits=UploadLimits(max_total_bytes=1),
        )
    assert list(tmp_path.iterdir()) == []


def test_direct_processing_writes_a_manifest_that_uses_local_logs(tmp_path, monkeypatch):
    folder = tmp_path / "race-2023-07"
    folder.mkdir()
    source = folder / "source.log"
    source.write_bytes(b"raw source")
    captured = {}

    def fake_run(manifest):
        captured["manifest"] = manifest
        return "processed"

    monkeypatch.setattr(raw_import, "run_campaign", fake_run)

    assert process_raw_logs_directly(folder, "Race", "2023-07") == "processed"
    manifest_path = folder / "manifest.yaml"
    assert captured["manifest"] == manifest_path
    manifest = load_manifest(manifest_path)
    assert manifest.inputs["logs"] == "./*.log"
    assert "repository" not in manifest.inputs
    assert manifest.campaign == {"id": "race-2023-07", "name": "Race", "date": "2023-07"}
    assert source.read_bytes() == b"raw source"
    assert manifest.path == manifest_path
    written = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert written["campaign"] == {
        "id": "race-2023-07",
        "name": "Race",
        "date": "2023-07",
    }
    assert written["inputs"]["logs"] == "./*.log"
    assert "repository" not in written["inputs"]
