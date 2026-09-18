from __future__ import annotations

import pytest

from yacht_co2 import raw_import
from yacht_co2.errors import YachtCO2Error
from yacht_co2.raw_import import (
    RawLog,
    UploadLimits,
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


def test_direct_processing_uses_local_logs_without_writing_a_manifest(tmp_path, monkeypatch):
    folder = tmp_path / "race-2023-07"
    folder.mkdir()
    source = folder / "source.log"
    source.write_bytes(b"raw source")
    captured = {}

    class FakePipeline:
        def __init__(self, manifest):
            captured["manifest"] = manifest

        def run(self):
            return "processed"

    monkeypatch.setattr(raw_import, "Pipeline", FakePipeline)

    assert process_raw_logs_directly(folder, "Race", "2023-07") == "processed"
    manifest = captured["manifest"]
    assert manifest.inputs["logs"] == "./*.log"
    assert "repository" not in manifest.inputs
    assert manifest.campaign == {"id": "race-2023-07", "name": "Race", "date": "2023-07"}
    assert source.read_bytes() == b"raw source"
    assert not (folder / "manifest.yaml").exists()
