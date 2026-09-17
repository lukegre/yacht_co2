"""Start the application that was just built, and check that it is alive.

A frozen bundle fails in a way an ordinary test cannot see. Everything imports
in the checkout the tests run against; what breaks is a module PyInstaller did
not know to include, or a data file it left behind, and neither shows up until
something runs the bundle itself. So this runs it -- the real executable, out
of ``dist/`` -- waits for the server inside it to answer, and fails the build if
it does not.

The window is not opened: a build machine has no display, and the interesting
half is the import graph, which is the same either way.

    uv run python packaging/smoke.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
NAME = "yacht-co2"

#: The port the application serves on when it is not drawing its own window.
PORT = 8080

#: Generous, because the first launch builds matplotlib's font cache and a
#: cold build machine reads 200 MB off a disk it has never touched.
TIMEOUT = 180.0


def executable() -> Path:
    """Return the built executable for this platform."""
    candidates = [
        DIST / f"{NAME}.app" / "Contents" / "MacOS" / NAME,
        DIST / NAME / f"{NAME}.exe",
        DIST / NAME / NAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"Nothing to test: none of {[str(c) for c in candidates]} exists.")


def wait_for_server(process: subprocess.Popen[bytes]) -> str:
    """Return the page the application serves, or raise once patience runs out."""
    deadline = time.monotonic() + TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(
                f"The application exited on its own, with status {process.returncode}."
            )
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1.0)
    raise SystemExit(f"Nothing answered on port {PORT} within {TIMEOUT:.0f}s: {last_error}")


def main() -> int:
    application = executable()
    print(f"starting {application}")

    with tempfile.TemporaryDirectory() as scratch:
        configuration = Path(scratch) / "config"
        environment = {
            **os.environ,
            # Kept away from whatever this machine's real configuration is, so
            # the check also proves a first launch works from nothing.
            "YACHT_CO2_CONFIG_DIR": str(configuration),
            # No display here, and nothing to look at if there were.
            "YACHT_CO2_DESKTOP_BROWSER": "1",
            # ... so nothing should try to open one either.
            "BROWSER": "true" if sys.platform != "win32" else "",
        }
        process = subprocess.Popen([str(application)], env=environment)
        try:
            page = wait_for_server(process)
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()

            log = configuration / "logs" / "desktop.log"
            if log.is_file():
                print("--- the application's log ---")
                print(log.read_text(encoding="utf-8", errors="replace"))

        if "<title>yacht-co2</title>" not in page:
            raise SystemExit("The application answered, but not with its own page.")
        for name in ("project.yaml", "manifest.yaml"):
            if not (configuration / name).is_file():
                raise SystemExit(f"A first launch did not seed {name}.")

    print("The application starts, seeds its configuration and serves its page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
