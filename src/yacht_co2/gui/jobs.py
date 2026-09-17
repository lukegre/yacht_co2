"""Running one slow step without freezing the page, and showing its log.

Archiving and processing take minutes, and the person watching has no terminal
to read. Each step therefore runs on a worker thread while a loguru sink copies
everything the package says into the step's own transcript -- so the browser
shows the same narration the command line does, as it happens.

Only one step runs at a time, process-wide. Two runs over one folder would race
over the same files, and the log sink is global, so a second run's output would
appear under the first one's heading. The transcript is kept rather than
consumed, so a second browser tab showing the same run sees all of it and not
whatever arrived after it opened.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ..errors import YachtCO2Error

LOG_FORMAT = "{time:HH:mm:ss} {level: <7} {message}"


@dataclass
class JobState:
    """One step, its transcript, and how it ended."""

    sequence: int = 0
    name: str = ""
    running: bool = False
    finished: bool = False
    error: str = ""
    result: Any = None
    #: Appended to from the worker thread and only ever read elsewhere, so a
    #: reader sees a prefix of the truth and never a torn line.
    lines: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.finished and not self.error

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        if not self.finished:
            return "idle"
        return "failed" if self.error else "done"


class JobRunner:
    """Run one blocking step at a time, capturing what it logs."""

    def __init__(self) -> None:
        self.state = JobState()
        self._sequence = itertools.count(1)
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self.state.running

    def execute(self, name: str, work: Callable[[], Any]) -> JobState:
        """Run ``work`` here and now, recording what it logged and returned.

        This blocks, and is meant to be handed to a worker thread by the page.
        A failure is recorded rather than raised: the page has to keep working
        so that the person can read what went wrong and try again.
        """
        if not self._lock.acquire(blocking=False):
            raise YachtCO2Error("another step is already running; wait for it to finish")
        state = JobState(sequence=next(self._sequence), name=name, running=True)
        self.state = state
        handler = logger.add(
            state.lines.append,
            format=LOG_FORMAT,
            level="INFO",
            colorize=False,
            backtrace=False,
            diagnose=False,
        )
        try:
            state.result = work()
        except YachtCO2Error as exc:
            # A domain error is an answer, not a crash: it says what is wrong
            # with the data or the configuration, which is what to show.
            state.error = str(exc)
            logger.error("{}", exc)
        except Exception as exc:  # noqa: BLE001 - the page must survive anything
            state.error = f"{type(exc).__name__}: {exc}"
            logger.opt(exception=True).error("{} failed unexpectedly", name)
        finally:
            logger.remove(handler)
            state.running = False
            state.finished = True
            self._lock.release()
        return state


#: One runner for the process, because one folder is processed at a time.
RUNNER = JobRunner()
