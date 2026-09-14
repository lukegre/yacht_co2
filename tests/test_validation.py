from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from yacht_co2.cli import app
from yacht_co2.errors import ManifestError
from yacht_co2.manifest import load_manifest
from yacht_co2.project import PROJECT_CONFIG_ENV, PROJECT_CONFIG_NAME, config_paths
from yacht_co2.validation import (
    errors,
    validate_manifest_document,
    validate_project_document,
)

VALID_MANIFEST = {
    "campaign": {"name": "Fastnet 2023"},
    "inputs": {"logs": "*.log"},
    "calibration": {"method": "instrument"},
    "qc": {"analysis_phases": [5], "ranges": {"co2": [100, 1000]}},
    "outputs": {"formats": ["netcdf", "csv"], "site": True},
}


def write_manifest(folder: Path, **overrides) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.yaml"
    path.write_text(yaml.safe_dump({**VALID_MANIFEST, **overrides}))
    (folder / "a.log").write_text("log")
    return path


def messages(findings, severity=None):
    return [
        f"{finding.where}: {finding.message}"
        for finding in findings
        if severity is None or finding.severity == severity
    ]


def test_a_valid_manifest_reports_nothing(tmp_path):
    assert validate_manifest_document(VALID_MANIFEST, write_manifest(tmp_path)) == []


def test_every_manifest_problem_is_reported_at_once(tmp_path):
    path = write_manifest(
        tmp_path,
        calibration={"method": "instrumnt"},
        qc={"minimum_water_flow": "0.1", "ranges": {"co2": [1000, 100], "salinity": [0]}},
        outputs={"formats": "netcdf", "site": "yes-please"},
    )
    findings = validate_manifest_document(yaml.safe_load(path.read_text()), path)

    assert messages(findings, "error") == [
        "calibration.method: 'instrumnt' is not one of instrument, linear",
        "qc.minimum_water_flow: must be a number, not str",
        "qc.ranges.co2: minimum 1000 is not below maximum 100",
        "qc.ranges.salinity: must be a [minimum, maximum] pair of numbers",
        "outputs.site: must be true or false, not str",
        "outputs.formats: must be a list, such as [netcdf, csv]",
    ]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"equilibratr": {"h2o": "h2o"}}, "manifest.equilibratr"),
        ({"flux": {"formulation": "wanninkhof2014"}}, "flux.formulation"),
        ({"qc": {"analysis_phase": [5]}}, "qc.analysis_phase"),
    ],
)
def test_a_key_nothing_reads_is_a_warning_not_an_error(tmp_path, overrides, expected):
    path = write_manifest(tmp_path, **overrides)
    findings = validate_manifest_document(yaml.safe_load(path.read_text()), path)

    assert errors(findings) == []
    assert messages(findings, "warning") == [
        f"{expected}: is not read by anything; check the spelling"
    ]


def test_a_log_glob_matching_nothing_is_a_warning(tmp_path):
    path = write_manifest(tmp_path, inputs={"logs": "elsewhere/*.log"})
    findings = validate_manifest_document(yaml.safe_load(path.read_text()), path)

    assert errors(findings) == []
    assert "inputs.logs: matches no files: elsewhere/*.log" in messages(findings)


def test_remote_log_glob_is_not_checked_on_the_local_filesystem(tmp_path):
    path = write_manifest(
        tmp_path,
        inputs={"repository": "10.5281/zenodo.12345", "logs": "remote/*.log"},
    )
    findings = validate_manifest_document(yaml.safe_load(path.read_text()), path)

    assert errors(findings) == []
    assert not any(finding.where == "inputs.logs" for finding in findings)


def test_load_manifest_refuses_a_document_with_errors(tmp_path):
    path = write_manifest(tmp_path, calibration={"method": "instrumnt"}, products="none")
    with pytest.raises(ManifestError) as error:
        load_manifest(path)

    assert "calibration.method" in str(error.value)
    assert "products: must be a list" in str(error.value)


def test_load_manifest_accepts_a_document_with_only_warnings(tmp_path):
    path = write_manifest(tmp_path, flux={"formulation": "wanninkhof2014"})
    assert load_manifest(path).name == "Fastnet 2023"


def test_project_blocks_and_zenodo_fields_are_checked():
    findings = validate_project_document(
        {
            "platfrom": {"vessel_name": "Boat"},
            "zenodo": {
                "creators": ["Gregor, Luke"],
                "keywords": "carbon",
                "title_template": "{campaign} with {skipper}",
                "campaign": "Fastnet Race",
            },
        }
    )

    assert messages(findings, "error") == [
        "zenodo.creators: creator 1: expected 'last name, first name, ORCID'",
        "zenodo.keywords: must be a list of strings",
        "zenodo.title_template: uses unknown field(s) skipper; "
        "available: campaign, campaign_date, slug, vessel, year",
    ]
    assert messages(findings, "warning") == [
        "project.yaml.platfrom: is not read by anything; check the spelling",
        "zenodo.campaign: belongs to a single data folder; here it would name every record alike",
    ]


def test_a_platform_without_a_vessel_is_a_warning():
    findings = validate_project_document({"platform": {"co2_sensor": "LI850"}})
    assert messages(findings, "warning") == [
        "platform.vessel_name: is unset, so reports and titles have no vessel"
    ]


def test_the_project_config_location_can_be_set_in_the_environment(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    elsewhere = tmp_path / "shared" / "defaults.yaml"
    elsewhere.parent.mkdir()
    elsewhere.write_text(yaml.safe_dump({"platform": {"vessel_name": "Shared"}}))
    folder = tmp_path / "data" / "voyage"
    folder.mkdir(parents=True)
    monkeypatch.setenv(PROJECT_CONFIG_ENV, str(elsewhere))

    assert config_paths(folder) == [elsewhere.resolve()]

    # A project.yaml in the repository still refines the configured default.
    root = tmp_path / PROJECT_CONFIG_NAME
    root.write_text(yaml.safe_dump({"platform": {"vessel_name": "Local"}}))
    assert config_paths(folder) == [elsewhere.resolve(), root.resolve()]


def test_the_configured_location_is_read_from_a_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    elsewhere = tmp_path / "defaults.yaml"
    elsewhere.write_text(yaml.safe_dump({"platform": {"vessel_name": "Shared"}}))
    (tmp_path / ".env").write_text(f"{PROJECT_CONFIG_ENV}={elsewhere}\n")
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    assert config_paths(tmp_path) == [elsewhere.resolve()]


def test_a_configured_location_that_does_not_exist_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv(PROJECT_CONFIG_ENV, str(tmp_path / "missing.yaml"))
    with pytest.raises(ManifestError, match=f"{PROJECT_CONFIG_ENV} does not point at a file"):
        config_paths(tmp_path)


def test_cli_validate_exits_non_zero_only_for_errors(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / PROJECT_CONFIG_NAME).write_text(
        yaml.safe_dump({"platform": {"vessel_name": "Boat"}})
    )
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    warned = runner.invoke(
        app, ["validate", str(write_manifest(tmp_path, flux={"formulation": "x"}))]
    )
    assert warned.exit_code == 0
    assert "warning: flux.formulation" in warned.output
    assert "valid: Fastnet 2023" in warned.output

    broken = write_manifest(tmp_path / "broken", calibration={"method": "nope"})
    failed = runner.invoke(app, ["validate", str(broken)])
    assert failed.exit_code == 1
    assert "error: calibration.method" in failed.output


def test_cli_validate_checks_the_project_config_without_a_manifest(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / PROJECT_CONFIG_NAME).write_text(
        yaml.safe_dump({"zenodo": {"keywords": "carbon"}, "platform": {"vessel_name": "Boat"}})
    )
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "zenodo.keywords: must be a list of strings" in result.output
