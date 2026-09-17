"""The defaults page: seeding, editing, and the token."""

from __future__ import annotations

import pytest
from nicegui.testing import User

from yacht_co2.userconfig import (
    MANIFEST_DEFAULTS_NAME,
    PROJECT_NAME,
    config_file,
    write_settings,
    write_token,
)


@pytest.fixture(autouse=True)
def _a_data_root(tmp_path):
    write_settings({"data_root": str(tmp_path)})


async def test_opening_the_defaults_seeds_both_templates(user: User):
    assert not config_file(PROJECT_NAME).exists()
    await user.open("/")
    user.find("Defaults").click()
    await user.should_see("Shared defaults")
    await user.should_see("Started you off with a copy of each template")
    assert config_file(PROJECT_NAME).is_file()
    assert config_file(MANIFEST_DEFAULTS_NAME).is_file()


async def test_the_seeded_project_file_says_what_is_still_missing(user: User):
    await user.open("/")
    user.find("Defaults").click()
    # The template ships without creators on purpose, so that an unedited copy
    # cannot archive a record under a placeholder name.
    await user.should_see("zenodo.creators")
    await user.should_see("creators must contain at least one entry")


async def test_a_missing_token_is_reported_without_ever_showing_one(user: User, monkeypatch):
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ZENODO_SANDBOX_ACCESS_TOKEN", raising=False)
    write_token("a-real-looking-token")

    await user.open("/")
    user.find("Defaults").click()
    user.find("Zenodo token").click()
    await user.should_see("Stored. Paste a new one to replace it.")
    await user.should_see("Not set. Archiving needs it.")
    await user.should_not_see("a-real-looking-token")


async def test_an_exported_token_is_named_as_the_one_in_use(user: User, monkeypatch):
    monkeypatch.setenv("ZENODO_ACCESS_TOKEN", "from-the-shell")
    await user.open("/")
    user.find("Defaults").click()
    user.find("Zenodo token").click()
    await user.should_see("Set in the environment as ZENODO_ACCESS_TOKEN; that one is used.")


def _one(user: User, marker: str):
    """The single element carrying ``marker``, which is how the panels differ."""
    found = user.find(marker=marker).elements
    assert len(found) == 1, f"expected one {marker}, found {len(found)}"
    return next(iter(found))


async def test_saving_an_edited_project_file_writes_it_back(user: User):
    await user.open("/")
    user.find("Defaults").click()
    await user.should_see("Shared defaults")

    _one(user, "editor-defaults-project").set_value(
        "platform:\n  vessel_name: Yoroshiku\n"
        "zenodo:\n  creators:\n  - Gregor, Luke, 0000-0001-6071-1857\n"
        "  publisher: Zenodo\n"
    )
    await user.should_see(f"{PROJECT_NAME} is valid.")
    user.find(marker="save-defaults-project").click()
    await user.should_see("Saved project.yaml")

    written = config_file(PROJECT_NAME).read_text(encoding="utf-8")
    assert "vessel_name: Yoroshiku" in written


async def test_a_document_that_would_break_a_run_cannot_be_saved(user: User):
    await user.open("/")
    user.find("Defaults").click()
    await user.should_see("Shared defaults")

    _one(user, "editor-defaults-project").set_value("platform: not-a-mapping\n")
    await user.should_see("must be a mapping, not str")
    # The save button is disabled rather than the error being raised later.
    assert _one(user, "save-defaults-project").enabled is False
