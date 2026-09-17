"""The application someone opens by double-clicking it.

Everything here is about the difference between a terminal and no terminal:
where the narration goes when there is no console to read it in, whether the
pages get a window of their own or the default browser, and what a first launch
has to write before the interface has anything to show. The packaged bundle
itself is checked by ``packaging/smoke.py``, which needs a bundle to check.
"""

from __future__ import annotations

import sys

import pytest

from yacht_co2 import desktop
from yacht_co2.userconfig import MANIFEST_DEFAULTS_NAME, PROJECT_NAME, config_dir


@pytest.fixture(autouse=True)
def _restore_logging():
    """Put loguru back as the rest of the suite expects to find it.

    Configuring the log is half of what this module tests, and loguru's
    handlers are process-wide: left in place, a sink pointing into a deleted
    temporary directory would follow the suite into every test after it.
    """
    from loguru import logger

    yield
    logger.remove()
    logger.add(sys.stderr)


def test_a_windowed_process_is_given_streams_it_can_write_to(monkeypatch):
    """Windows hands a console-less application ``None`` for both."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    desktop.repair_standard_streams()

    for stream in (sys.stdout, sys.stderr):
        assert stream is not None
        stream.write("this would otherwise have raised")


def test_working_streams_are_left_alone(monkeypatch):
    class Stream:
        pass

    stdout, stderr = Stream(), Stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    desktop.repair_standard_streams()

    assert sys.stdout is stdout
    assert sys.stderr is stderr


def test_the_log_goes_to_a_file_beside_the_configuration(monkeypatch):
    from loguru import logger

    destination = desktop.configure_logging()

    assert destination.parent.parent == config_dir()
    logger.info("something worth keeping")
    logger.complete()
    assert "something worth keeping" in destination.read_text(encoding="utf-8")


def test_a_first_launch_writes_the_documents_the_settings_panel_edits():
    created = desktop.prepare_configuration()

    assert set(created) == {PROJECT_NAME, MANIFEST_DEFAULTS_NAME}
    assert all(path.is_file() for path in created.values())


def test_a_second_launch_does_not_overwrite_what_was_edited():
    desktop.prepare_configuration()
    edited = config_dir() / PROJECT_NAME
    edited.write_text("# mine\n", encoding="utf-8")

    assert desktop.prepare_configuration() == {}
    assert edited.read_text(encoding="utf-8") == "# mine\n"


def test_the_environment_can_ask_for_a_browser_instead_of_a_window(monkeypatch):
    monkeypatch.setenv(desktop.BROWSER_ENVIRONMENT_VARIABLE, "1")
    assert desktop.can_open_a_window() is False


def test_a_machine_without_pywebview_uses_its_browser(monkeypatch):
    monkeypatch.delenv(desktop.BROWSER_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setitem(sys.modules, "webview", None)
    # A module set to None in sys.modules is how Python reports one that cannot
    # be imported, which is the state of the Linux bundle.
    assert desktop.can_open_a_window() is False


def test_linux_without_a_display_uses_its_browser(monkeypatch):
    monkeypatch.delenv(desktop.BROWSER_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert desktop.can_open_a_window() is False


@pytest.mark.parametrize(
    ("windowed", "expected_port"),
    [
        # In a window there is no address bar to report a busy port in, so
        # NiceGUI is left to find one.
        (True, None),
        (False, 8080),
    ],
)
def test_the_launch_matches_how_the_pages_will_be_shown(monkeypatch, windowed, expected_port):
    recorded: dict[str, object] = {}
    monkeypatch.setattr(desktop, "can_open_a_window", lambda: windowed)
    monkeypatch.setattr("yacht_co2.gui.app.launch", lambda **options: recorded.update(options))

    assert desktop.main() == 0
    assert recorded == {"port": expected_port, "show": not windowed, "native": windowed}


def test_a_failure_before_the_first_page_is_reported_rather_than_raised(monkeypatch):
    """Nothing can be shown in the interface if the interface never opens."""

    def explode(**_options: object) -> None:
        raise RuntimeError("the window would not open")

    monkeypatch.setattr(desktop, "can_open_a_window", lambda: False)
    monkeypatch.setattr("yacht_co2.gui.app.launch", explode)

    assert desktop.main() == 1
    assert "the window would not open" in desktop.log_file().read_text(encoding="utf-8")
