"""Identical imports at the same time share one run.

An import can take a minute (the local model). If the same request comes again while the first is
still running (the page was reloaded, or a second tab sent it), the repeat does not start a second
generation on the model or save a second draft: it waits for the first run and gets its result,
the same draft or the same error. Different requests run as usual.
"""

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class _Run:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
        self.waiters = 0  # repeats waiting for this run


class SharedRuns:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, _Run] = {}

    def run(self, key: str, work: Callable[[], T]) -> T:
        """work(), unless a run with this key is under way: then that run's result (or its error)."""
        with self._lock:
            run = self._runs.get(key)
            repeat = run is not None
            if run is None:
                run = self._runs[key] = _Run()
            else:
                run.waiters += 1
        if repeat:
            run.done.wait()
            if run.error is not None:
                raise run.error
            return run.result
        try:
            run.result = work()
            return run.result
        except BaseException as error:
            run.error = error
            raise
        finally:
            with self._lock:
                del self._runs[key]
            run.done.set()

    def waiting(self) -> int:
        """How many repeats are waiting for a run (for tests)."""
        with self._lock:
            return sum(run.waiters for run in self._runs.values())
