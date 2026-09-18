from __future__ import annotations

import pytest

from yacht_co2 import container


def test_port_uses_default_and_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(container.PORT_ENV, raising=False)
    assert container._port() == 8080

    monkeypatch.setenv(container.PORT_ENV, "zero")
    with pytest.raises(ValueError, match="must be an integer"):
        container._port()

    monkeypatch.setenv(container.PORT_ENV, "65536")
    with pytest.raises(ValueError, match="between 1 and 65535"):
        container._port()


def test_main_seeds_logs_and_launches_without_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    launched: dict[str, object] = {}
    monkeypatch.setenv(container.DATA_ROOT_ENV, str(tmp_path / "data"))
    monkeypatch.setenv(container.HOST_ENV, "127.0.0.2")
    monkeypatch.setenv(container.PORT_ENV, "9123")
    monkeypatch.setattr(container, "configure_logging", lambda: tmp_path / "desktop.log")
    monkeypatch.setattr(container, "prepare_configuration", lambda: {})
    monkeypatch.setattr(container, "launch", lambda **kwargs: launched.update(kwargs))

    container.main()

    assert launched == {
        "data_root": tmp_path / "data",
        "host": "127.0.0.2",
        "port": 9123,
        "show": False,
    }
