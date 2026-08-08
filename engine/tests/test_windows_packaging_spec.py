"""Regression coverage for PyInstaller data bundling in ``tools/battle2.spec``.

``battle2.exe`` is the only shipped executable that reaches
``battle_engine.command._agents`` (``bytefray agents create``/``validate``/
``test``) -- ``battle-cli``/``battle-agent-designer``/``battle-replay-viewer``
dispatch elsewhere and have no dependency on
``battle_engine/data/agent_template``. This module directly executes
``tools/battle2.spec``'s real source (the same file PyInstaller itself
``exec``s to build ``battle2.exe``) with PyInstaller's build-time globals
(``Analysis``/``PYZ``/``EXE``/``COLLECT``, plus the ``collect_submodules``
import) stubbed out, so this test asserts the spec's actual ``datas`` list
contains the scaffold template directory without requiring the optional,
``windows-build``-extra ``pyinstaller`` package to be installed and without
invoking a real, multi-second PyInstaller build. This is intentionally the
narrowest check that still exercises the spec file's real logic rather than
a re-description of it; the strongest possible verification -- a real
frozen ``battle2.exe`` actually running ``agents create`` -- is a manual/CI
concern covered by ``tools/build_win.ps1``'s smoke test, not this suite
(see that script and ``docs/specs/agent_scaffold.md``).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BATTLE2_SPEC = ROOT / "tools" / "battle2.spec"


def _exec_spec_datas(
    spec_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, str]]:
    """Execute one PyInstaller ``.spec`` file's real source; return its ``datas``.

    Mirrors how PyInstaller itself runs a ``.spec`` file: ``Analysis``,
    ``PYZ``, ``EXE``, and ``COLLECT`` are bare names PyInstaller injects into
    the exec namespace with no import statement in the real spec file; they
    are stubbed here as harmless no-op recorders instead of the real,
    heavyweight build classes. ``PyInstaller.utils.hooks.collect_submodules``
    *is* a real import in the spec file, so a fake module is registered in
    ``sys.modules`` for the duration of the call, letting this test run with
    no actual ``pyinstaller`` install present (e.g. the headless
    ``test-linux-core`` CI job, which installs only the ``dev`` extra).
    """

    fake_hooks = types.ModuleType("PyInstaller.utils.hooks")
    fake_hooks.collect_submodules = lambda name: []  # type: ignore[attr-defined]
    fake_utils = types.ModuleType("PyInstaller.utils")
    fake_utils.hooks = fake_hooks  # type: ignore[attr-defined]
    fake_pyinstaller = types.ModuleType("PyInstaller")
    fake_pyinstaller.utils = fake_utils  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PyInstaller", fake_pyinstaller)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", fake_hooks)

    class _BuildStub:
        """Callable stand-in for Analysis/PYZ/EXE/COLLECT.

        Calling it or accessing any attribute on the result (e.g. a real
        `Analysis(...)` instance's `.pure`/`.scripts`/`.binaries`/`.datas`,
        each read by the later PYZ/EXE/COLLECT calls in a real spec file)
        always returns the same stub, so the spec's chain of
        `a = Analysis(...); pyz = PYZ(a.pure); exe = EXE(pyz, a.scripts, ...)`
        runs to completion without needing real PyInstaller build classes.
        """

        def __call__(self, *args: object, **kwargs: object) -> "_BuildStub":
            return self

        def __getattr__(self, name: str) -> "_BuildStub":
            return self

    stub = _BuildStub()
    namespace: dict[str, object] = {
        "__file__": str(spec_path),
        "__name__": "__pyinstaller_spec__",
        "Analysis": stub,
        "PYZ": stub,
        "EXE": stub,
        "COLLECT": stub,
    }
    # The spec computes `project_root = os.path.abspath(".")`, exactly as
    # PyInstaller itself runs it (cwd is the invocation directory, normally
    # the repository root per tools/build_win.ps1's `Set-Location $RepoRoot`).
    monkeypatch.chdir(ROOT)
    code = compile(spec_path.read_text(encoding="utf-8"), str(spec_path), "exec")
    exec(code, namespace)
    return list(namespace["datas"])  # type: ignore[arg-type]


def test_battle2_spec_bundles_the_agent_template_directory(monkeypatch):
    """Regression test for a real, previously-shipped packaging defect.

    ``tools/battle2.spec`` bundled ``battle_engine/data/starter_agents`` but
    had no equivalent entry for the sibling ``battle_engine/data/
    agent_template`` directory ``bytefray agents create`` depends on, so the
    resource was silently absent from ``battle2.exe``'s frozen ``_MEIPASS``
    extraction directory even though source checkouts and installed wheels
    both already had it -- confirmed by an actual PyInstaller build of
    ``battle2.exe`` before this fix, which reproduced
    ``agent_scaffold.template_resource_dir``'s "Agent template resource
    directory not found" error end to end against the real frozen exe.
    """

    datas = _exec_spec_datas(BATTLE2_SPEC, monkeypatch)
    template_entries = [
        entry for entry in datas if entry[1] == "battle_engine/data/agent_template"
    ]
    assert template_entries, (
        "tools/battle2.spec's `datas` must bundle "
        "battle_engine/data/agent_template (needed by `bytefray agents "
        "create` in the frozen build); found only: "
        f"{[entry[1] for entry in datas]}"
    )
    source_dir = Path(template_entries[0][0])
    assert source_dir.is_dir()
    assert {"agent.yaml", "agent.py"} <= {path.name for path in source_dir.iterdir()}


def test_battle2_spec_still_bundles_starter_agents(monkeypatch):
    """Confirms adding the agent_template entry did not disturb starter_agents."""

    datas = _exec_spec_datas(BATTLE2_SPEC, monkeypatch)
    assert any(entry[1] == "battle_engine/data/starter_agents" for entry in datas)
