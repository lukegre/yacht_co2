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

from importlib.util import find_spec

import pytest

from yacht_co2.project import PROJECT_CONFIG_ENV
from yacht_co2.userconfig import CONFIG_DIR_ENV

#: The graphical interface is tested through NiceGUI's simulated browser, whose
#: fixtures come from a plugin pytest only accepts in the root configuration.
#: It is an optional extra, so its tests are skipped where it is not installed.
_HAS_NICEGUI = find_spec("nicegui") is not None
pytest_plugins = ["nicegui.testing.user_plugin"] if _HAS_NICEGUI else []
# The whole directory, not its files: without the extra even its conftest
# and package marker fail to import.
collect_ignore = [] if _HAS_NICEGUI else ["gui"]


@pytest.fixture(autouse=True)
def _isolate_project_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv(PROJECT_CONFIG_ENV, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _isolate_user_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep the developer's own ``~/.config/yacht_co2`` out of the suite.

    Project resolution and ``build_manifest`` both read it, so a real one on
    the machine running the tests would change what they resolve. The directory
    is pointed at an empty place, which is the state of a fresh installation.
    """
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "user-config"))


@pytest.fixture(autouse=True)
def _plain_cli_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render the command line the same way wherever the suite runs.

    Typer draws its errors with Rich, which colours what it recognises -- and
    an option name inside a sentence is one of those things. A continuous
    integration runner sets ``FORCE_COLOR``, so the same message that reads
    ``pass --campaign and --campaign-date`` on a developer's machine arrives
    with escape codes between its words, and every assertion about the text
    fails somewhere that has nothing to do with what the text says. Colour is
    turned off and the width fixed so that a message is compared as written.
    """
    for variable in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    # Wide enough that a sentence is not folded mid-phrase; the tests that
    # compare a framed message normalise the whitespace anyway.
    monkeypatch.setenv("COLUMNS", "200")
