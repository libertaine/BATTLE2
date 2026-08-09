"""A hard external safety net for tests that exercise real hang containment.

Per the Agent Lab test-writing rule ("every hang test must have an
external safety timeout" -- see ``docs/specs/agent_lab.md`` §15/adversarial
review checklist): a bug in the timeout/worker-kill mechanism under test
must never be able to hang the whole test process forever. Uses stdlib
``faulthandler.dump_traceback_later(..., exit=True)`` rather than a new
dependency (``pytest-timeout`` is not currently a project dependency) --
if ``seconds`` elapses, the interpreter dumps every thread's traceback to
stderr and hard-exits, which fails the test run loudly instead of hanging
CI indefinitely.
"""

from __future__ import annotations

import contextlib
import faulthandler
import sys
from collections.abc import Iterator


@contextlib.contextmanager
def hang_safety_timeout(seconds: float) -> Iterator[None]:
    # sys.__stderr__, not sys.stderr: pytest's capsys/capfd fixtures
    # replace sys.stderr with a non-fd-backed object, and
    # dump_traceback_later needs a real file descriptor to write to.
    faulthandler.dump_traceback_later(seconds, exit=True, file=sys.__stderr__)
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()
