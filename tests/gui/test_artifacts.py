"""Renku's allowlisted campaign-artifact downloads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.exceptions import HTTPException

from yacht_co2.gui import app, artifacts
from yacht_co2.naming import output_name


@pytest.fixture
def artifact_folder(tmp_path: Path) -> tuple[Path, Path]:
    """A completed campaign with each artifact named by the normal workflow."""
    root = tmp_path / "data"
    folder = root / "fastnet"
    folder.mkdir(parents=True)
    (folder / "zenodo.yaml").write_text(
        "campaign: Fastnet Race\ncampaign_date: 2023-07-24\n", encoding="utf-8"
    )
    for key, kind, extension in (
        ("site", "site", "html"),
        ("track", "track", "nc"),
        ("report", "report", "json"),
    ):
        (folder / output_name("Fastnet Race", "2023-07-24", kind, extension)).write_text(
            key, encoding="utf-8"
        )
    return root, folder


@pytest.mark.parametrize(
    ("key", "content_type", "suffix"),
    [
        ("site", "text/html", "-site.html"),
        ("track", "application/x-netcdf", "-track.nc"),
        ("report", "application/json", "-report.json"),
    ],
)
def test_resolver_allowlists_each_download_with_its_response_type(
    artifact_folder: tuple[Path, Path], key: str, content_type: str, suffix: str
):
    root, folder = artifact_folder

    path, found_type = artifacts.resolve_download(root, folder.name, key)

    assert path.name.endswith(suffix)
    assert found_type == content_type


@pytest.mark.parametrize("campaign, key", [("../fastnet", "site"), ("fastnet", "../site"), ("fastnet", "video")])
def test_resolver_refuses_unrecognised_or_path_like_requests(
    artifact_folder: tuple[Path, Path], campaign: str, key: str
):
    root, _ = artifact_folder

    with pytest.raises(ValueError, match="unknown campaign artifact"):
        artifacts.resolve_download(root, campaign, key)


def test_resolver_refuses_an_artifact_outside_the_selected_folder(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    outside = root / "private.html"
    outside.write_text("not a campaign artifact", encoding="utf-8")
    monkeypatch.setattr(artifacts, "campaign_status", lambda _: SimpleNamespace(site=outside))

    with pytest.raises(ValueError, match="unknown campaign artifact"):
        artifacts.resolve_download(root, folder.name, "site")


def test_download_route_sets_attachment_filename_and_type(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    monkeypatch.setattr(app, "read_settings", lambda: {"data_root": str(root)})

    response = app.artifact_download(folder.name, "report")

    assert response.media_type == "application/json"
    assert response.headers["content-disposition"].endswith('filename="yacht_co2-fastnet_race-2023_07_24-report.json"')


def test_download_route_returns_not_found_for_an_invalid_key(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    monkeypatch.setattr(app, "read_settings", lambda: {"data_root": str(root)})

    with pytest.raises(HTTPException) as error:
        app.artifact_download(folder.name, "../report")

    assert error.value.status_code == 404


def test_docker_mode_uses_browser_artifacts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(artifacts, "DOCKER_ENV", "/container-marker")
    monkeypatch.setattr(Path, "is_file", lambda path: str(path) == "/container-marker")
    monkeypatch.delenv(artifacts.RENKU_BASE_URL_PATH_ENV, raising=False)
    assert artifacts.use_browser_artifacts()


def test_renku_mode_uses_browser_artifacts_even_without_dockers_own_marker(
    monkeypatch: pytest.MonkeyPatch,
):
    """A RenkuLab session doesn't always leave Docker's marker file behind,

    but it still puts the server and the person looking at the browser on
    different machines, so xdg-open there would only affect a container
    nobody is looking at.
    """
    monkeypatch.setattr(artifacts, "DOCKER_ENV", "/container-marker")
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    monkeypatch.setenv(artifacts.RENKU_BASE_URL_PATH_ENV, "/sessions/example")
    assert artifacts.use_browser_artifacts()


def test_a_missing_opener_binary_uses_browser_artifacts(monkeypatch: pytest.MonkeyPatch):
    """Neither Docker's marker nor Renku's env var names every headless case,

    so a container lacking xdg-open (or the platform equivalent) falls back
    to the browser routes too.
    """
    monkeypatch.setattr(artifacts, "DOCKER_ENV", "/container-marker")
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    monkeypatch.delenv(artifacts.RENKU_BASE_URL_PATH_ENV, raising=False)
    monkeypatch.setattr(artifacts.shutil, "which", lambda name: None)
    assert artifacts.use_browser_artifacts()


def test_a_present_opener_binary_keeps_desktop_artifacts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(artifacts, "DOCKER_ENV", "/container-marker")
    monkeypatch.setattr(Path, "is_file", lambda path: False)
    monkeypatch.delenv(artifacts.RENKU_BASE_URL_PATH_ENV, raising=False)
    monkeypatch.setattr(artifacts.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert not artifacts.use_browser_artifacts()


def test_site_preview_route_is_inline_and_allowlisted(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    monkeypatch.setattr(app, "read_settings", lambda: {"data_root": str(root)})
    response = app.artifact_view(folder.name, "site")
    assert response.media_type == "text/html"
    assert "content-disposition" not in response.headers


def test_folder_download_contains_only_regular_files_and_sets_zip_filename(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    (folder / "nested").mkdir()
    (folder / "nested" / "notes.txt").write_text("notes", encoding="utf-8")
    outside = root / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (folder / "leak.txt").symlink_to(outside)
    monkeypatch.setattr(app, "read_settings", lambda: {"data_root": str(root)})

    response = app.campaign_folder_download(folder.name)
    try:
        import zipfile

        with zipfile.ZipFile(response.path) as archive:
            assert sorted(archive.namelist()) == [
                "nested/notes.txt",
                "yacht_co2-fastnet_race-2023_07_24-report.json",
                "yacht_co2-fastnet_race-2023_07_24-site.html",
                "yacht_co2-fastnet_race-2023_07_24-track.nc",
                "zenodo.yaml",
            ]
            assert archive.read("nested/notes.txt") == b"notes"
    finally:
        Path(response.path).unlink(missing_ok=True)
    assert response.media_type == "application/zip"
    assert response.headers["content-disposition"].endswith('filename="fastnet.zip"')


def test_folder_download_rejects_symlinked_campaign(
    artifact_folder: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    root, folder = artifact_folder
    alias = root / "alias"
    alias.symlink_to(folder, target_is_directory=True)
    monkeypatch.setattr(app, "read_settings", lambda: {"data_root": str(root)})

    with pytest.raises(HTTPException) as error:
        app.campaign_folder_download("alias")

    assert error.value.status_code == 404
