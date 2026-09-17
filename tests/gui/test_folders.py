"""Picking a directory, which a browser cannot do on its own."""

from __future__ import annotations

from nicegui.testing import User

from yacht_co2.gui.folders import subdirectories
from yacht_co2.userconfig import read_settings, write_settings


def test_only_visible_directories_are_listed(tmp_path):
    (tmp_path / "2306_fastnet").mkdir()
    (tmp_path / "2212_rhum").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "notes.txt").write_text("not a folder", encoding="utf-8")

    assert [path.name for path in subdirectories(tmp_path)] == ["2212_rhum", "2306_fastnet"]


def test_a_folder_that_cannot_be_read_lists_as_empty(tmp_path):
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "inside").mkdir()
    closed.chmod(0o000)
    try:
        # Somewhere the person cannot go, which an empty listing already says.
        assert subdirectories(closed) == []
    finally:
        closed.chmod(0o700)


def test_a_folder_that_is_not_there_lists_as_empty(tmp_path):
    assert subdirectories(tmp_path / "nowhere") == []


async def test_the_picker_walks_into_a_folder_and_returns_it(user: User, tmp_path):
    """Choosing a data root, which is the first thing anyone has to do."""
    start = tmp_path / "start"
    voyages = start / "voyages"
    (voyages / "2306_fastnet").mkdir(parents=True)
    write_settings({"data_root": str(start)})

    await user.open("/")
    await user.should_see("No campaign folders here yet")
    user.find("Change folder").click()
    await user.should_see("Where your campaign folders live")

    user.find(marker="folder-voyages").click()
    await user.should_see("2306_fastnet")
    user.find("Use this folder").click()

    # The choice is remembered, so the next launch opens where this one left off.
    assert read_settings()["data_root"] == str(voyages)
    await user.should_see("2306_fastnet")


async def test_the_picker_can_be_left_without_changing_anything(user: User, tmp_path):
    write_settings({"data_root": str(tmp_path)})
    await user.open("/")
    user.find("Change folder").click()
    await user.should_see("Where your campaign folders live")
    user.find("Cancel").click()
    assert read_settings()["data_root"] == str(tmp_path)
