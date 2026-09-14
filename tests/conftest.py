"""Shared test fixtures.

Configuration resolution reads the environment, and two routes let the
developer's own workspace leak into a test. ``load_dotenv`` writes into
``os.environ`` for the life of the process, so a test that exercises a ``.env``
leaks its values into every test that runs afterwards. Resolution also reads a
``.env`` beside the invocation directory, which is the real repository when the
suite is run from a checkout, so clearing the variable beforehand is not enough
on its own. Clearing it and running each test from its own directory keeps
resolution deterministic whatever the test order and wherever pytest is invoked.
"""

from __future__ import annotations

import pytest

from yacht_co2.project import PROJECT_CONFIG_ENV


@pytest.fixture(autouse=True)
def _isolate_project_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
