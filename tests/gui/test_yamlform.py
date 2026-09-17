"""Editing a commented document through a form, without losing the comments."""

from __future__ import annotations

import pytest
import yaml

from yacht_co2.errors import ManifestError
from yacht_co2.gui.yamlform import (
    MISSING,
    dump_text,
    load_document,
    parse_document,
    parse_integers,
    plain,
    read_path,
    write_path,
)
from yacht_co2.manifest import packaged_defaults


def test_editing_a_value_keeps_every_comment_around_it():
    document = load_document(packaged_defaults())
    write_path(document, ("qc", "minimum_water_flow"), 0.75)
    text = dump_text(document)

    assert "minimum_water_flow: 0.75" in text
    # The comments are the only explanation a person has of these values, so
    # saving a form must not be what deletes them.
    assert "# Flags rather than filters" in text
    assert "LI-850 CellTemp" in text
    assert "yacht_co2-fastnet_race-2023_07_24-track.nc" in text


def test_a_form_save_leaves_the_sections_it_does_not_know_about(tmp_path):
    source = tmp_path / "manifest.yaml"
    source.write_text(
        "inputs:\n  logs: ./*.log\nproducts:\n- name: era5   # fetched grid\n  provider: era5\n",
        encoding="utf-8",
    )
    document = load_document(source)
    write_path(document, ("inputs", "timezone"), "UTC")
    text = dump_text(document)

    assert yaml.safe_load(text)["products"] == [{"name": "era5", "provider": "era5"}]
    assert "# fetched grid" in text


def test_an_emptied_control_removes_its_key_rather_than_blanking_it():
    document = parse_document("inputs:\n  timezone: UTC\n")
    write_path(document, ("inputs", "timezone"), MISSING)
    assert plain(document) == {"inputs": {}}


def test_writing_into_a_section_that_is_not_there_yet():
    document = parse_document("campaign:\n  name: Fastnet\n")
    write_path(document, ("qc", "ranges", "co2"), [100, 1000])
    assert plain(document)["qc"] == {"ranges": {"co2": [100, 1000]}}


def test_reading_past_the_end_of_a_path_gives_the_default():
    document = parse_document("campaign:\n  name: Fastnet\n")
    assert read_path(document, ("campaign", "name")) == "Fastnet"
    assert read_path(document, ("campaign", "date")) is None
    assert read_path(document, ("outputs", "formats"), []) == []


def test_phase_codes_are_read_from_what_a_person_would_type():
    assert parse_integers("5") == [5]
    assert parse_integers("2, 4 5") == [2, 4, 5]
    assert parse_integers("") == []
    with pytest.raises(ManifestError, match="whole numbers"):
        parse_integers("five")


def test_a_document_that_is_not_a_mapping_is_refused():
    with pytest.raises(ManifestError, match="mapping of sections"):
        parse_document("- just\n- a list\n")
    with pytest.raises(ManifestError, match="invalid YAML"):
        parse_document("campaign: [unclosed\n")
