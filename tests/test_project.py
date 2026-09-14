import pytest

from yacht_co2.errors import ManifestError
from yacht_co2.project import PROJECT_CONFIG_NAME, load_platform, load_project_config


def repository(tmp_path):
    (tmp_path / ".git").mkdir(parents=True)
    return tmp_path


def write(directory, **platform):
    directory.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"  {key}: {value}" for key, value in platform.items())
    (directory / PROJECT_CONFIG_NAME).write_text(f"platform:\n{body}\n")


def test_defaults_are_found_from_a_nested_data_folder(tmp_path):
    root = repository(tmp_path)
    write(root, vessel_name="YOROSHIKU", co2_sensor="LI850")
    nested = root / "data" / "2306_fastnet"
    nested.mkdir(parents=True)

    assert load_platform(nested) == {"vessel_name": "YOROSHIKU", "co2_sensor": "LI850"}


def test_a_nearer_file_refines_a_more_distant_one(tmp_path):
    root = repository(tmp_path)
    write(root, vessel_name="YOROSHIKU", co2_sensor="LI850")
    nested = root / "data" / "2306_fastnet"
    write(nested, co2_sensor="LI7815")

    platform = load_platform(nested)

    assert platform == {"vessel_name": "YOROSHIKU", "co2_sensor": "LI7815"}


def test_search_stops_at_the_repository_root(tmp_path):
    outside = tmp_path / "outside"
    write(outside, vessel_name="SHOULD NOT BE SEEN")
    root = repository(outside / "repo")
    nested = root / "data"
    nested.mkdir(parents=True)

    assert load_platform(nested) == {}


def test_a_file_path_is_resolved_against_its_directory(tmp_path):
    root = repository(tmp_path)
    write(root, vessel_name="YOROSHIKU")
    manifest = root / "manifest.yaml"
    manifest.write_text("campaign: {}\n")

    assert load_platform(manifest) == {"vessel_name": "YOROSHIKU"}


def test_missing_defaults_are_not_an_error(tmp_path):
    root = repository(tmp_path)

    assert load_project_config(root) == {}
    assert load_platform(root) == {}


def test_an_empty_file_is_treated_as_no_defaults(tmp_path):
    root = repository(tmp_path)
    (root / PROJECT_CONFIG_NAME).write_text("")

    assert load_project_config(root) == {}


def test_a_non_mapping_platform_is_rejected(tmp_path):
    root = repository(tmp_path)
    (root / PROJECT_CONFIG_NAME).write_text("platform: LI850\n")

    with pytest.raises(ManifestError, match="must be a mapping"):
        load_platform(root)


def test_a_non_mapping_root_is_rejected(tmp_path):
    root = repository(tmp_path)
    (root / PROJECT_CONFIG_NAME).write_text("- vessel\n")

    with pytest.raises(ManifestError, match="root must be a mapping"):
        load_project_config(root)
