from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest
from battle_engine import process_containment

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object behavior")


def test_die_with_parent_is_noop_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_containment.sys, "platform", "win32")
    # Must not raise, and must not touch ctypes/os at all (Job Object
    # containment is entirely parent-side on Windows -- see
    # bind_child_to_parent_lifetime).
    process_containment.die_with_parent()


def test_die_with_parent_self_kills_on_reparent_race(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression coverage for the ``prctl(PR_SET_PDEATHSIG)`` registration
    race (continuation-phase item 14): if the parent already died in the
    window before this process reaches its own ``prctl()`` call, the
    signal was armed too late to ever fire. ``die_with_parent`` must
    notice its own ppid changed immediately after ``prctl()`` and
    self-terminate rather than silently trusting a signal that can no
    longer arrive.
    """

    monkeypatch.setattr(process_containment.sys, "platform", "linux")

    ppid_values = iter([111, 222])  # before prctl(), after prctl() -- changed => race hit
    monkeypatch.setattr(process_containment.os, "getppid", lambda: next(ppid_values))

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(process_containment.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(
        process_containment.ctypes, "CDLL", lambda *a, **k: SimpleNamespace(prctl=lambda *args: 0)
    )

    process_containment.die_with_parent()

    assert killed == [(process_containment.os.getpid(), 9)]


def test_die_with_parent_does_not_self_kill_without_race(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_containment.sys, "platform", "linux")
    monkeypatch.setattr(process_containment.os, "getppid", lambda: 111)  # unchanged both times

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(process_containment.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(
        process_containment.ctypes, "CDLL", lambda *a, **k: SimpleNamespace(prctl=lambda *args: 0)
    )

    process_containment.die_with_parent()

    assert killed == []


def test_die_with_parent_never_raises_on_prctl_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_containment.sys, "platform", "linux")

    def _raise(*args, **kwargs):
        raise OSError("no libc here")

    monkeypatch.setattr(process_containment.ctypes, "CDLL", _raise)

    process_containment.die_with_parent()  # must not raise


def test_bind_child_to_parent_lifetime_is_null_binding_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_containment.sys, "platform", "linux")
    binding = process_containment.bind_child_to_parent_lifetime(object())
    binding.close()  # no-op, must not raise
    binding.close()  # idempotent


@WINDOWS_ONLY
def test_bind_child_to_parent_lifetime_without_handle_is_null_binding() -> None:
    binding = process_containment.bind_child_to_parent_lifetime(object())
    binding.close()  # must not raise even though there was never a real process


@WINDOWS_ONLY
def test_bind_child_to_parent_lifetime_returns_working_binding() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        binding = process_containment.bind_child_to_parent_lifetime(proc)
        binding.close()
        binding.close()  # idempotent -- must not raise or double-free
    finally:
        proc.kill()
        proc.wait(timeout=10)
