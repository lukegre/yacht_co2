"""Defaults kept with the user rather than with a checkout."""

from __future__ import annotations

import pytest
import yaml

from yacht_co2.errors import YachtCO2Error
from yacht_co2.manifest import build_manifest, default_template, packaged_defaults
from yacht_co2.project import config_paths
from yacht_co2.userconfig import (
    CONFIG_DIR_ENV,
    MANIFEST_DEFAULTS_NAME,
    PROJECT_NAME,
    SECRETS_NAME,
    config_dir,
    config_file,
    read_token,
    resolve_config_dir,
    seed_config_dir,
    write_token,
)


def test_unix_keeps_its_defaults_under_dot_config(tmp_path):
    home = tmp_path / "home"
    assert resolve_config_dir("posix", {}, home) == home / ".config" / "yacht_co2"
    assert (
        resolve_config_dir("posix", {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, home)
        == tmp_path / "xdg" / "yacht_co2"
    )


def test_macos_uses_application_support(tmp_path):
    home = tmp_path / "home"
    assert (
        resolve_config_dir("posix", {}, home, sys_platform="darwin")
        == home / "Library" / "Application Support" / "yacht_co2"
    )


def test_windows_keeps_its_defaults_where_windows_keeps_them(tmp_path):
    home = tmp_path / "home"
    assert resolve_config_dir("nt", {}, home) == home / "AppData" / "Roaming" / "yacht_co2"
    roaming = tmp_path / "AppData" / "Roaming"
    assert resolve_config_dir("nt", {"APPDATA": str(roaming)}, home) == roaming / "yacht_co2"


def test_the_environment_overrides_the_platform_location(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    located = resolve_config_dir("posix", {CONFIG_DIR_ENV: str(elsewhere)}, tmp_path)
    assert located == elsewhere.resolve()
    # The real one is what every other test in the suite is pointed at.
    assert config_dir() == elsewhere.parent.resolve() / "user-config"


def test_seeding_writes_both_templates_once(tmp_path):
    created = seed_config_dir()
    assert set(created) == {PROJECT_NAME, MANIFEST_DEFAULTS_NAME}
    edited = config_file(MANIFEST_DEFAULTS_NAME)
    edited.write_text("campaign: {}\n", encoding="utf-8")

    # A second launch must not overwrite what the user has since changed.
    assert seed_config_dir() == {}
    assert edited.read_text(encoding="utf-8") == "campaign: {}\n"


def test_the_seeded_manifest_template_keeps_its_comments():
    seed_config_dir()
    seeded = config_file(MANIFEST_DEFAULTS_NAME).read_text(encoding="utf-8")
    assert "# Flags rather than filters" in seeded
    assert seeded == packaged_defaults().read_text(encoding="utf-8")


def test_a_user_project_config_ranks_below_the_repository(tmp_path):
    seed_config_dir()
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    (repository / PROJECT_NAME).write_text("platform: {vessel_name: Local}\n", encoding="utf-8")

    resolved = config_paths(repository)
    assert resolved == [config_file(PROJECT_NAME), repository / PROJECT_NAME]


def test_a_new_manifest_starts_from_the_users_own_template(tmp_path):
    seed_config_dir()
    template = config_file(MANIFEST_DEFAULTS_NAME)
    document = yaml.safe_load(template.read_text(encoding="utf-8"))
    document["qc"]["minimum_water_flow"] = 0.75
    template.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    assert default_template() == template

    folder = tmp_path / "2306_fastnet"
    folder.mkdir()
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\ndoi: 10.5281/zenodo.1\n",
        encoding="utf-8",
    )
    built = yaml.safe_load(build_manifest(folder / "zenodo.yaml").read_text(encoding="utf-8"))
    assert built["qc"]["minimum_water_flow"] == 0.75


def test_a_token_is_stored_privately_and_read_back(monkeypatch):
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ZENODO_SANDBOX_ACCESS_TOKEN", raising=False)

    write_token("secret-production")
    write_token("secret-sandbox", sandbox=True)
    assert read_token() == "secret-production"
    assert read_token(sandbox=True) == "secret-sandbox"

    path = config_file(SECRETS_NAME)
    assert path.stat().st_mode & 0o077 == 0
    # Storing one deployment's token must not disturb the other's.
    write_token("", sandbox=True)
    assert read_token() == "secret-production"
    assert read_token(sandbox=True) == ""


def test_an_exported_token_wins_over_a_stored_one(monkeypatch):
    write_token("stored")
    monkeypatch.setenv("ZENODO_ACCESS_TOKEN", "exported")
    assert read_token() == "exported"


def test_a_token_cannot_smuggle_a_second_line_into_the_file():
    with pytest.raises(YachtCO2Error, match="line break"):
        write_token("real\nZENODO_SANDBOX_ACCESS_TOKEN=forged")
