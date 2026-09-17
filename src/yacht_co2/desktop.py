"""The application someone opens by double-clicking it.

Everything the interface does is already in :mod:`yacht_co2.gui`; this module
is only what changes when there is no terminal in front of it. A frozen build
has nowhere to print, no working directory worth speaking of and no shell to
read an error out of, so three things are settled here before the first page is
served:

* the standard streams, which Windows hands a windowed process as ``None`` and
  which anything that logs will otherwise fall over;
* the log, which goes to a file next to the user's configuration instead of a
  console nobody can see, and which is the only place a crash can be read;
* the two configuration templates, seeded on first launch so that the settings
  panel opens on a document rather than on nothing.

It is deliberately thin, and imports the interface late: the multiprocessing
child that draws the native window re-runs this module, and it should not pay
for NiceGUI, xarray and matplotlib to do it.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

#: Kept for a fortnight, which covers a campaign and the week of questions
#: after it, and rotated so a long run cannot fill a laptop.
LOG_ROTATION = "5 MB"
LOG_RETENTION = "14 days"
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} {level: <8} {name}:{line} {message}"

#: Set to anything non-empty to serve the pages to the default browser instead
#: of drawing a window. The escape hatch for a machine whose webview is broken.
BROWSER_ENVIRONMENT_VARIABLE = "YACHT_CO2_DESKTOP_BROWSER"


def running_frozen() -> bool:
    """Say whether this is the packaged application rather than a checkout."""
    return bool(getattr(sys, "frozen", False))


def repair_standard_streams() -> None:
    """Give this process a ``stdout`` and ``stderr`` it can write to.

    A Windows application built without a console has neither, and Python sets
    both to ``None``. Every logging handler, every stray ``print`` and uvicorn's
    own startup banner then raise ``AttributeError`` somewhere too deep to
    catch. Pointing them at the null device costs nothing and means the failure
    cannot happen; the log is a file either way.
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def log_directory() -> Path:
    """Return the folder holding the application's own log."""
    from .userconfig import config_dir

    return config_dir() / "logs"


def log_file() -> Path:
    """Return the file this launch writes its log to."""
    return log_directory() / "desktop.log"


def configure_logging() -> Path:
    """Send the package's narration to a file, and return where it went.

    The default handler writes to ``stderr``, which in a packaged application
    is the null device this module just opened. It is removed rather than left
    in place so that nothing is quietly discarded: one file holds the whole
    story, and it is the file the README tells people to send on.

    The sink is synchronous on purpose. Buffering the writes would be faster
    and would lose the last few lines whenever the process dies badly -- which
    is exactly when this file is the only thing left to read.
    """
    from loguru import logger

    destination = log_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        destination,
        format=LOG_FORMAT,
        level="INFO",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        enqueue=False,
        backtrace=True,
        diagnose=False,
    )
    return destination


def can_open_a_window() -> bool:
    """Say whether this machine can draw the interface in a window of its own.

    macOS and Windows can: pywebview binds to WebKit and to WebView2, both of
    which are part of the system and both of which are packaged with the
    application. Linux cannot, at least not portably -- its binding is
    GTK/WebKit2, a system library whose version differs per distribution and
    which is not frozen into the bundle -- so the Linux application serves its
    pages to the default browser instead. Absent pywebview entirely, so does
    every other platform.
    """
    if os.environ.get(BROWSER_ENVIRONMENT_VARIABLE, "").strip():
        return False
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def prepare_configuration() -> dict[str, Path]:
    """Write the documents a first launch expects to find, and say which.

    Seeding is the one thing the packaged application must do that a checkout
    does not: someone who has never opened a terminal has no ``project.yaml``
    to point the settings panel at, and an empty panel reads as a broken one.
    An existing file is left exactly as it is.
    """
    from loguru import logger

    from .userconfig import seed_config_dir

    created = seed_config_dir()
    for name, path in created.items():
        logger.info("First launch: wrote {} to {}", name, path)
    return created


def main() -> int:
    """Open the interface and stay open until its window is closed.

    Returns a process exit status, so a failure before the first page is served
    -- the one kind of failure the interface cannot report itself -- leaves
    something behind for a terminal, and the whole traceback in the log.
    """
    # First, and before anything imports a library: in a frozen build the
    # window is drawn by a spawned copy of this very executable, and this is
    # the call that lets that copy run its own task instead of opening a second
    # application. It does nothing in the parent, or outside a frozen build.
    multiprocessing.freeze_support()
    repair_standard_streams()

    if running_frozen():
        # Nothing here draws a figure, but matplotlib picks a backend on import
        # and an interactive one would want a toolkit the bundle does not carry.
        os.environ.setdefault("MPLBACKEND", "Agg")

    destination = configure_logging()
    from loguru import logger

    logger.info(
        "yacht-co2 desktop starting ({}), logging to {}",
        "packaged" if running_frozen() else "checkout",
        destination,
    )

    try:
        prepare_configuration()
        from .gui.app import launch

        native = can_open_a_window()
        logger.info("Opening {}.", "a window" if native else "the default browser")
        # In a window there is no address bar to report a busy port in, so the
        # port is left to NiceGUI to find.
        launch(port=None if native else 8080, show=not native, native=native)
    except Exception:
        logger.opt(exception=True).critical("The application could not start.")
        return 1
    logger.info("yacht-co2 desktop closed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the packaged build
    raise SystemExit(main())
