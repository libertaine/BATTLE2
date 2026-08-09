"""Regression coverage for PyInstaller data bundling in the shipped ``.spec`` files.

``battle2.exe`` (``tools/battle2.spec``) is the shipped executable that
reaches ``battle_engine.command._agents`` (``bytefray agents create``/
``validate``/``test``) via the CLI -- ``battle-cli``/``battle-replay-viewer``
dispatch elsewhere and have no dependency on
``battle_engine/data/agent_template``. ``battle-agent-designer.exe``
(``tools/agent_designer.spec``) also depends on this same resource directory
because Phase 4a of ``docs/specs/agent_designer_workflow.md`` calls
``battle_engine.agent_scaffold.create_agent`` directly, in-process, from the
Designer's own "New Agent" workflow -- so the frozen Designer executable
needs the identical bundled resource ``battle2.exe`` already needed, not
just the CLI-facing one. This module directly executes each spec file's
real source (the same file PyInstaller itself ``exec``s to build the
executable) with PyInstaller's build-time globals (``Analysis``/``PYZ``/
``EXE``/``COLLECT``, plus the ``collect_submodules`` import) stubbed out, so
these tests assert each spec's actual ``datas`` list contains the scaffold
template directory without requiring the optional, ``windows-build``-extra
``pyinstaller`` package to be installed and without invoking a real,
multi-second PyInstaller build. This is intentionally the narrowest check
that still exercises the spec files' real logic rather than a
re-description of it; the strongest possible verification -- a real frozen
executable actually running ``agents create`` / "New Agent" -- is a
manual/CI concern covered by ``tools/build_win.ps1``'s smoke test, not this
suite (see that script and ``docs/specs/agent_scaffold.md``).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BATTLE2_SPEC = ROOT / "tools" / "battle2.spec"
AGENT_DESIGNER_SPEC = ROOT / "tools" / "agent_designer.spec"


def _exec_spec_datas(
    spec_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, str]]:
    """Execute one PyInstaller ``.spec`` file's real source; return its ``datas``.

    Mirrors how PyInstaller itself runs a ``.spec`` file: ``Analysis``,
    ``PYZ``, ``EXE``, and ``COLLECT`` are bare names PyInstaller injects into
    the exec namespace with no import statement in most spec files (e.g.
    ``tools/battle2.spec``); they are stubbed here as harmless no-op
    recorders instead of the real, heavyweight build classes.
    ``tools/agent_designer.spec`` instead imports the same four names
    explicitly (``from PyInstaller.building.build_main import Analysis,
    PYZ`` / ``from PyInstaller.building.api import EXE, COLLECT``), so those
    two submodules are faked too, alongside
    ``PyInstaller.utils.hooks.collect_submodules`` (a real import in every
    spec file here). Faking all of these lets this test run with no actual
    ``pyinstaller`` install present (e.g. the headless ``test-linux-core``
    CI job, which installs only the ``dev`` extra).
    """

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

    fake_hooks = types.ModuleType("PyInstaller.utils.hooks")
    fake_hooks.collect_submodules = lambda name: []  # type: ignore[attr-defined]
    fake_utils = types.ModuleType("PyInstaller.utils")
    fake_utils.hooks = fake_hooks  # type: ignore[attr-defined]
    fake_build_main = types.ModuleType("PyInstaller.building.build_main")
    fake_build_main.Analysis = stub  # type: ignore[attr-defined]
    fake_build_main.PYZ = stub  # type: ignore[attr-defined]
    fake_api = types.ModuleType("PyInstaller.building.api")
    fake_api.EXE = stub  # type: ignore[attr-defined]
    fake_api.COLLECT = stub  # type: ignore[attr-defined]
    fake_building = types.ModuleType("PyInstaller.building")
    fake_building.build_main = fake_build_main  # type: ignore[attr-defined]
    fake_building.api = fake_api  # type: ignore[attr-defined]
    fake_pyinstaller = types.ModuleType("PyInstaller")
    fake_pyinstaller.utils = fake_utils  # type: ignore[attr-defined]
    fake_pyinstaller.building = fake_building  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PyInstaller", fake_pyinstaller)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", fake_hooks)
    monkeypatch.setitem(sys.modules, "PyInstaller.building", fake_building)
    monkeypatch.setitem(sys.modules, "PyInstaller.building.build_main", fake_build_main)
    monkeypatch.setitem(sys.modules, "PyInstaller.building.api", fake_api)

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


def test_agent_designer_spec_bundles_the_agent_template_directory(monkeypatch):
    """Regression test for the Phase 4a packaging blocker (agent_designer_workflow.md Sec 17.3).

    Phase 4a's "New Agent" workflow calls
    ``battle_engine.agent_scaffold.create_agent`` directly, in-process, from
    inside the Designer's own executable -- there is no subprocess
    boundary for scaffolding (Sec 5 of the spec). Before this fix,
    ``tools/agent_designer.spec`` bundled ``battle_engine/data/
    starter_agents`` but had no equivalent entry for the sibling
    ``battle_engine/data/agent_template`` directory, so a frozen
    ``battle-agent-designer.exe`` would fail "New Agent" with a
    ``FileNotFoundError`` from ``template_resource_dir`` -- the identical
    class of bug already fixed for ``battle2.exe`` above.
    """

    datas = _exec_spec_datas(AGENT_DESIGNER_SPEC, monkeypatch)
    template_entries = [
        entry for entry in datas if entry[1] == "battle_engine/data/agent_template"
    ]
    assert template_entries, (
        "tools/agent_designer.spec's `datas` must bundle "
        "battle_engine/data/agent_template (needed by the Designer's "
        "in-process 'New Agent' workflow in the frozen build); found only: "
        f"{[entry[1] for entry in datas]}"
    )
    source_dir = Path(template_entries[0][0])
    assert source_dir.is_dir()
    assert {"agent.yaml", "agent.py"} <= {path.name for path in source_dir.iterdir()}


def test_agent_designer_spec_still_bundles_starter_agents(monkeypatch):
    """Confirms adding the agent_template entry did not disturb starter_agents.

    (The spec's ``assets`` entry is conditional on an ``assets/`` directory
    existing at the repository root, which is not guaranteed in every
    checkout, so it is not asserted here -- ``battle_engine/data/
    starter_agents`` always exists in-tree and is the meaningful regression
    to guard.)
    """

    datas = _exec_spec_datas(AGENT_DESIGNER_SPEC, monkeypatch)
    entries = {entry[1] for entry in datas}
    assert "battle_engine/data/starter_agents" in entries
