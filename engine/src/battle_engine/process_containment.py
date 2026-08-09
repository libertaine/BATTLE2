"""Best-effort child-dies-with-parent containment for worker subprocesses.

Windows has no equivalent of POSIX's parent-death signal: a killed or
crashed parent process does not cascade-terminate any subprocess it
spawned unless it explicitly opts in. This matters specifically for
Agent Lab's worker subprocesses (``docs/specs/agent_lab.md`` §6): if the
parent (for example, the Designer's ``QProcess`` wrapping ``bytefray
agents test``, force-killed via ``_dispose_process``'s unconditional
``kill()``) dies while a worker is genuinely stuck inside a hung
``act()``/``reset()`` call, the worker cannot notice on its own -- it is
not blocked on I/O waiting for the next command, it is stuck in the
agent's own tight loop -- so the EOF-on-closed-stdin recovery this
module's sibling relies on for the *cooperative* case never gets a
chance to run, and the worker would otherwise survive as a permanent
orphan process on the user's machine. This was confirmed empirically
during Agent Lab development: killing the QProcess running a supervised
``bytefray agents test`` while its worker was mid-hang left the worker
process running indefinitely.

**Windows**: the parent creates a Job Object with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and assigns the worker process to
it immediately after spawning. Windows itself closes every handle a
terminated or crashed process held, including the job handle; once the
last handle to a kill-on-close job closes, the OS force-terminates every
process still assigned to it -- unconditionally, regardless of what that
process is doing. No cooperation from the worker is required, which is
exactly the property a CPU-bound infinite loop needs.

**POSIX (Linux)**: the worker calls ``prctl(PR_SET_PDEATHSIG, SIGKILL)``
on its own behalf immediately at startup, asking the kernel to deliver
``SIGKILL`` when its parent thread exits for any reason. This has a
well-known race: if the parent dies in the window between the worker
process being created and the worker actually reaching its own
``prctl()`` call, the signal was armed too late to ever fire, and the
worker would silently become a permanent orphan despite believing it set
up containment successfully. :func:`die_with_parent` closes this window
with the standard mitigation: capture the parent's pid before calling
``prctl()``, then re-check it immediately after. A changed pid means the
original parent already exited during that window (this process was
reparented, typically to init) -- ``die_with_parent`` self-terminates
immediately in that case rather than trusting a signal that cannot
arrive.

Both mechanisms are best-effort and never raise: containment failing to
establish does not prevent Bytefray from working, it only means this one
adversarial edge case (parent force-killed mid-hang) is not covered on
that platform/environment. Neither claims to defend against anything
other than accidental orphaning -- see ``docs/specs/agent_lab.md`` §17.
"""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Any


class ChildLifetimeBinding:
    """An opaque handle whose lifetime must be kept for the child's guarantee to hold.

    Do nothing with it beyond keeping a reference until the child no
    longer needs to be tied to this parent, then call :meth:`close`.
    Letting it go out of scope early would trigger the kill-on-close
    semantics immediately.
    """

    def close(self) -> None:  # pragma: no cover - overridden by real bindings
        raise NotImplementedError


class _NullBinding(ChildLifetimeBinding):
    def close(self) -> None:
        pass


class _WindowsJobHandle(ChildLifetimeBinding):
    def __init__(self, kernel32: Any, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle = handle

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = 0

    def __del__(self) -> None:  # pragma: no cover - GC timing dependent
        self.close()


def bind_child_to_parent_lifetime(process: Any) -> ChildLifetimeBinding:
    """Best-effort: ensure ``process`` is killed if this parent process dies.

    Always returns a :class:`ChildLifetimeBinding` (never ``None``, never
    raises) so callers have one uniform object to hold and eventually
    close; on platforms/failures where containment could not be
    established, the returned binding's :meth:`close` is simply a no-op.
    """

    if sys.platform != "win32":
        return _NullBinding()
    return _bind_windows_job_object(process)


def _bind_windows_job_object(process: Any) -> ChildLifetimeBinding:
    process_handle = getattr(process, "_handle", None)
    if process_handle is None:
        return _NullBinding()

    try:
        from ctypes import wintypes

        # ctypes.WinDLL only exists in typeshed's win32-conditional stubs, so
        # this line reports attr-defined under `mypy engine/src/battle_engine`
        # on any non-Windows host even though this function itself is never
        # reached there (the caller's `sys.platform != "win32"` guard above).
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

        job_object_extended_limit_information = 9
        job_object_limit_kill_on_job_close = 0x00002000

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JobObjectBasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JobObjectExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JobObjectBasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            return _NullBinding()

        info = JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = job_object_limit_kill_on_job_close
        if not kernel32.SetInformationJobObject(
            job_handle,
            job_object_extended_limit_information,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(job_handle)
            return _NullBinding()

        # subprocess.Popen exposes the raw Win32 process HANDLE via the
        # undocumented `_handle` attribute -- there is no public stdlib API
        # for this; it is the same handle CPython's own subprocess
        # internals use, and the standard technique for Job Object
        # assignment without adding a pywin32 dependency.
        if not kernel32.AssignProcessToJobObject(job_handle, int(process_handle)):
            kernel32.CloseHandle(job_handle)
            return _NullBinding()

        return _WindowsJobHandle(kernel32, job_handle)
    except (OSError, AttributeError, ValueError):
        return _NullBinding()


def die_with_parent() -> None:
    """Best-effort POSIX: ask the kernel to SIGKILL this process if its parent dies.

    Called by the worker itself (not the parent) at startup. A no-op on
    Windows (handled by the parent-side Job Object instead) and on any
    POSIX platform without ``prctl`` (e.g. macOS, which this project does
    not target for headless/worker use) -- never raises.

    Closes the ``prctl`` registration race documented above: if the
    parent already died in the window before this call, ``os.getppid()``
    changes (this process is reparented) as an immediate, synchronous side
    effect of that -- checking it right after ``prctl()`` returns is
    enough to detect a signal that was armed too late and self-terminate
    instead of trusting one that will never arrive.
    """

    if sys.platform == "win32":
        return
    try:
        original_ppid = os.getppid()
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        pr_set_pdeathsig = 1
        sigkill = 9
        libc.prctl(pr_set_pdeathsig, sigkill, 0, 0, 0)
        if os.getppid() != original_ppid:
            os.kill(os.getpid(), sigkill)
    except OSError:
        pass


__all__ = [
    "ChildLifetimeBinding",
    "bind_child_to_parent_lifetime",
    "die_with_parent",
]
