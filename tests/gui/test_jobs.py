"""Running one slow step, and telling the page what it said."""

from __future__ import annotations

import threading

import pytest
from loguru import logger

from yacht_co2.errors import ManifestError, YachtCO2Error
from yacht_co2.gui.jobs import JobRunner


def test_a_step_keeps_what_it_logged_and_what_it_returned():
    runner = JobRunner()

    def work() -> str:
        logger.info("Reading {} logs", 3)
        logger.success("Done")
        return "the dataset"

    state = runner.execute("Processing", work)
    assert state.succeeded
    assert state.result == "the dataset"
    assert state.status == "done"
    assert any("Reading 3 logs" in line for line in state.lines)


def test_a_domain_failure_is_an_answer_rather_than_a_crash():
    runner = JobRunner()

    def work() -> None:
        raise ManifestError("inputs: is required and must contain logs")

    state = runner.execute("Processing", work)
    assert not state.succeeded
    assert state.status == "failed"
    assert state.error == "inputs: is required and must contain logs"
    # The page has to keep working, so the message is recorded, not raised.
    assert any("must contain logs" in line for line in state.lines)


def test_an_unexpected_failure_is_named_rather_than_swallowed():
    runner = JobRunner()
    state = runner.execute("Processing", lambda: 1 / 0)
    assert state.error.startswith("ZeroDivisionError:")
    assert not runner.busy


def test_the_log_sink_is_removed_however_the_step_ends():
    runner = JobRunner()
    first = runner.execute("First", lambda: logger.info("inside"))
    logger.info("outside, after the step")
    assert not any("outside" in line for line in first.lines)

    runner.execute("Second", lambda: None)
    # Each step gets its own transcript rather than appending to the last one.
    assert runner.state.sequence == 2
    assert runner.state.lines == []


def test_only_one_step_runs_at_a_time():
    runner = JobRunner()
    started = threading.Event()
    release = threading.Event()

    def slow() -> None:
        started.set()
        release.wait(timeout=5)

    worker = threading.Thread(target=runner.execute, args=("Slow", slow))
    worker.start()
    try:
        assert started.wait(timeout=5)
        with pytest.raises(YachtCO2Error, match="already running"):
            runner.execute("Second", lambda: None)
    finally:
        release.set()
        worker.join(timeout=5)

    # The lock is released, so the next step may start.
    assert runner.execute("Third", lambda: None).succeeded
