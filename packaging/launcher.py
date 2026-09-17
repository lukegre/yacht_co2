"""The script PyInstaller freezes into the application.

It is this short on purpose. A frozen application that draws a native window
starts a second copy of itself to draw it, and that copy re-runs this file from
the top before ``multiprocessing`` hands it its real task. Anything imported
here is therefore imported twice per launch, so the only import is the one that
stops the second copy: :func:`multiprocessing.freeze_support` consumes the
arguments that mark a spawned child and runs its task, and everything below it
belongs to the launch a person actually asked for.
"""

from __future__ import annotations

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from yacht_co2.desktop import main

    raise SystemExit(main())
