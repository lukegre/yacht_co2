"""Shared test fixtures.

``load_dotenv`` writes into ``os.environ`` for the life of the process, so a
test that exercises a ``.env`` leaks its values into every test that runs
afterwards. Clearing the project-configuration variable before each test keeps
configuration resolution deterministic whatever the test order.
"""

from __future__ import annotations

import pytest

from yacht_co2.project import PROJECT_CONFIG_ENV


@pytest.fixture(autouse=True)
def _isolate_project_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
