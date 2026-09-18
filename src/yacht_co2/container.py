"""Start Yacht CO2 in a container with persistent, inspectable local state.

The normal ``yacht-co2 gui`` command is deliberately quiet about logging: it
is intended for an interactive checkout.  A service has no desktop console to
fall back to, so the image uses this small entry point to seed its writable
configuration and keep a file log alongside it before serving the GUI.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from .desktop import configure_logging, prepare_configuration
from .gui import launch

DATA_ROOT_ENV = "YACHT_CO2_DATA_ROOT"
HOST_ENV = "YACHT_CO2_HOST"
PORT_ENV = "YACHT_CO2_PORT"


def _port() -> int:
    """Read the service port with a clear error for an invalid environment."""
    value = os.environ.get(PORT_ENV, "8080")
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError(f"{PORT_ENV} must be an integer, not {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{PORT_ENV} must be between 1 and 65535, not {port}")
    return port


def main() -> None:
    """Seed writable configuration, create the service log, and serve the GUI."""
    configure_logging()
    prepare_configuration()
    data_root = Path(os.environ.get(DATA_ROOT_ENV, "/home/renku/work")).expanduser()
    host = os.environ.get(HOST_ENV, "0.0.0.0")
    logger.info("Starting container GUI on {}:{} with data in {}", host, _port(), data_root)
    launch(data_root=data_root, host=host, port=_port(), show=False)


if __name__ == "__main__":  # pragma: no cover - exercised by Docker smoke test
    main()
