"""Identical imports at the same time share one run (app/api/shared_runs.py)."""

import threading
import time

import pytest

from app.api.shared_runs import SharedRuns
from app.errors import ApiError


def wait_for(condition, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def in_thread(function) -> tuple[threading.Thread, list]:
    out: list = []

    def target() -> None:
        try:
            out.append(function())
        except Exception as error:  # noqa: BLE001 (handed to the test)
            out.append(error)

    thread = threading.Thread(target=target)
    thread.start()
    return thread, out


def slow_work(result):
    """Work that runs until released; counts its runs."""
    started, release, runs = threading.Event(), threading.Event(), []

    def work():
        runs.append(1)
        started.set()
        release.wait(5)
        if isinstance(result, Exception):
            raise result
        return result

    return work, started, release, runs


@pytest.mark.parametrize("result", ["the draft", ApiError(504, "extraction_timeout", "slow")])
def test_a_repeat_while_the_run_is_under_way_waits_and_gets_the_same_answer(result):
    shared = SharedRuns()
    work, started, release, runs = slow_work(result)
    first, first_out = in_thread(lambda: shared.run("same", work))
    assert started.wait(5)
    repeat, repeat_out = in_thread(lambda: shared.run("same", work))
    wait_for(lambda: shared.waiting() == 1)
    release.set()
    first.join(5)
    repeat.join(5)
    assert runs == [1]  # the work ran once
    assert first_out == repeat_out == [result]


def test_once_a_run_has_ended_the_same_request_runs_again():
    shared = SharedRuns()
    calls = []
    for _ in range(2):
        shared.run("same", lambda: calls.append(1))
    assert calls == [1, 1]  # a try after a timeout starts afresh


def test_different_requests_do_not_wait_for_each_other():
    shared = SharedRuns()
    work, started, release, _ = slow_work("first")
    first, _ = in_thread(lambda: shared.run("one text", work))
    assert started.wait(5)
    assert shared.run("another text", lambda: "second") == "second"  # while the first still runs
    release.set()
    first.join(5)
