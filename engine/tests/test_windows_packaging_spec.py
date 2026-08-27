"""Regression coverage for PyInstaller data bundling and onedir layout in the
shipped ``.spec`` files.

``bytefray.exe`` (``tools/bytefray.spec``) is the shipped executable that
reaches ``battle_engine.command._agents`` (``bytefray agents create``/
``validate``/``test``) via the CLI -- ``bytefray-cli``/``bytefray-replay-viewer``
dispatch elsewhere and have no dependency on
``battle_engine/data/agent_template``. ``bytefray-agent-designer.exe``
(``tools/agent_designer.spec``) also depends on this same resource directory
because Phase 4a of ``docs/specs/agent_designer_workflow.md`` calls
``battle_engine.agent_scaffold.create_agent`` directly, in-process, from the
Designer's own "New Agent" workflow -- so the frozen Designer executable
needs the identical bundled resource ``bytefray.exe`` already needed, not
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

The module also covers a v1.3 finding (docs/specs "Area E" investigation):
``tools/agent_designer.spec``/``tools/replay_viewer.spec`` previously built
their ``EXE`` with every binary/data file baked in (no ``exclude_binaries``,
``COLLECT(exe, name=...)`` with nothing further) instead of the onedir
"thin launcher + loose files" shape ``tools/bytefray.spec``/
``tools/bytefray_cli.spec`` already used and ``tools/installer.iss``/the
portable ZIP layout both assume for all four applications --
``test_spec_builds_onedir_layout_not_a_fat_exe`` pins the fixed shape.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BYTEFRAY_SPEC = ROOT / "tools" / "bytefray.spec"
BYTEFRAY_CLI_SPEC = ROOT / "tools" / "bytefray_cli.spec"
AGENT_DESIGNER_SPEC = ROOT / "tools" / "agent_designer.spec"
REPLAY_VIEWER_SPEC = ROOT / "tools" / "replay_viewer.spec"
ALL_SPECS = (BYTEFRAY_SPEC, BYTEFRAY_CLI_SPEC, AGENT_DESIGNER_SPEC, REPLAY_VIEWER_SPEC)
BUILD_WIN_SCRIPT = ROOT / "tools" / "build_win.ps1"


class _BuildStub:
    """Callable stand-in for Analysis/PYZ/EXE/COLLECT.

    Calling it or accessing any attribute on the result (e.g. a real
    `Analysis(...)` instance's `.pure`/`.scripts`/`.binaries`/`.datas`,
    each read by the later PYZ/EXE/COLLECT calls in a real spec file)
    always returns the same stub, so the spec's chain of
    `a = Analysis(...); pyz = PYZ(a.pure); exe = EXE(pyz, a.scripts, ...)`
    runs to completion without needing real PyInstaller build classes.
    """

    def __call__(self, *args: object, **kwargs: object) -> _BuildStub:
        return self

    def __getattr__(self, name: str) -> _BuildStub:
        return self


def _install_fake_pyinstaller(
    monkeypatch: pytest.MonkeyPatch,
    *,
    analysis: object,
    pyz: object,
    exe: object,
    collect: object,
) -> None:
    """Install the fake ``PyInstaller`` module tree every spec file imports from.

    Shared by every test in this module so ``Analysis``/``PYZ``/``EXE``/
    ``COLLECT`` can each be swapped independently -- some tests only care
    about ``datas`` (any harmless no-op stub is fine, see ``_BuildStub``),
    others need to capture the exact arguments a real PyInstaller build
    would pass to ``EXE``/``COLLECT`` (see ``_exec_spec_calls``).
    """

    fake_hooks = types.ModuleType("PyInstaller.utils.hooks")
    fake_hooks.collect_submodules = lambda name: []  # type: ignore[attr-defined]
    fake_utils = types.ModuleType("PyInstaller.utils")
    fake_utils.hooks = fake_hooks  # type: ignore[attr-defined]
    fake_build_main = types.ModuleType("PyInstaller.building.build_main")
    fake_build_main.Analysis = analysis  # type: ignore[attr-defined]
    fake_build_main.PYZ = pyz  # type: ignore[attr-defined]
    fake_api = types.ModuleType("PyInstaller.building.api")
    fake_api.EXE = exe  # type: ignore[attr-defined]
    fake_api.COLLECT = collect  # type: ignore[attr-defined]
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


def _exec_spec(
    spec_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    analysis: object,
    pyz: object,
    exe: object,
    collect: object,
) -> dict[str, Any]:
    """Execute one PyInstaller ``.spec`` file's real source; return its namespace.

    Mirrors how PyInstaller itself runs a ``.spec`` file: ``Analysis``,
    ``PYZ``, ``EXE``, and ``COLLECT`` are bare names PyInstaller injects into
    the exec namespace with no import statement in most spec files (e.g.
    ``tools/bytefray.spec``); ``tools/agent_designer.spec``/
    ``tools/replay_viewer.spec`` instead import the same four names
    explicitly (``from PyInstaller.building.build_main import Analysis,
    PYZ`` / ``from PyInstaller.building.api import EXE, COLLECT``), so both
    styles are exercised by installing the fakes both as bare namespace
    entries and as the real import targets. Faking all of these lets this
    test run with no actual ``pyinstaller`` install present (e.g. the
    headless ``test-linux-core`` CI job, which installs only the ``dev``
    extra).
    """

    _install_fake_pyinstaller(monkeypatch, analysis=analysis, pyz=pyz, exe=exe, collect=collect)
    namespace: dict[str, object] = {
        "__file__": str(spec_path),
        "__name__": "__pyinstaller_spec__",
        "Analysis": analysis,
        "PYZ": pyz,
        "EXE": exe,
        "COLLECT": collect,
    }
    # The spec computes `project_root = os.path.abspath(".")`, exactly as
    # PyInstaller itself runs it (cwd is the invocation directory, normally
    # the repository root per tools/build_win.ps1's `Set-Location $RepoRoot`).
    monkeypatch.chdir(ROOT)
    code = compile(spec_path.read_text(encoding="utf-8"), str(spec_path), "exec")
    exec(code, namespace)  # noqa: S102 -- introspecting our own trusted .spec file, test-only
    return namespace


def _exec_spec_datas(spec_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    stub = _BuildStub()
    namespace = _exec_spec(spec_path, monkeypatch, analysis=stub, pyz=stub, exe=stub, collect=stub)
    return list(namespace["datas"])  # type: ignore[arg-type]


def test_bytefray_spec_bundles_the_agent_template_directory(monkeypatch):
    """Regression test for a real, previously-shipped packaging defect.

    ``tools/bytefray.spec`` bundled ``battle_engine/data/starter_agents`` but
    had no equivalent entry for the sibling ``battle_engine/data/
    agent_template`` directory ``bytefray agents create`` depends on, so the
    resource was silently absent from ``bytefray.exe``'s frozen ``_MEIPASS``
    extraction directory even though source checkouts and installed wheels
    both already had it -- confirmed by an actual PyInstaller build of
    ``bytefray.exe`` before this fix, which reproduced
    ``agent_scaffold.template_resource_dir``'s "Agent template resource
    directory not found" error end to end against the real frozen exe.
    """

    datas = _exec_spec_datas(BYTEFRAY_SPEC, monkeypatch)
    template_entries = [
        entry for entry in datas if entry[1] == "battle_engine/data/agent_template"
    ]
    assert template_entries, (
        "tools/bytefray.spec's `datas` must bundle "
        "battle_engine/data/agent_template (needed by `bytefray agents "
        "create` in the frozen build); found only: "
        f"{[entry[1] for entry in datas]}"
    )
    source_dir = Path(template_entries[0][0])
    assert source_dir.is_dir()
    assert {"agent.yaml", "agent.py"} <= {path.name for path in source_dir.iterdir()}


def test_bytefray_spec_bundles_the_annotated_agent_template_directory(monkeypatch):
    """Regression test for a Phase 5 packaging gap in the same class as above.

    Phase 2 added a second scaffold template, ``battle_engine/data/
    agent_template_annotated`` (``bytefray agents create --template
    annotated``, and the matching Agent Designer New Agent choice), but
    ``tools/bytefray.spec`` was never updated alongside ``agent_template``'s
    entry, so the Annotated Example template was silently absent from
    ``bytefray.exe``'s frozen build even though the source checkout and
    installed wheel both already had it -- the identical class of defect
    ``test_bytefray_spec_bundles_the_agent_template_directory`` above already
    guards for the original "blank" template.
    """

    datas = _exec_spec_datas(BYTEFRAY_SPEC, monkeypatch)
    template_entries = [
        entry for entry in datas if entry[1] == "battle_engine/data/agent_template_annotated"
    ]
    assert template_entries, (
        "tools/bytefray.spec's `datas` must bundle "
        "battle_engine/data/agent_template_annotated (needed by `bytefray "
        "agents create --template annotated` in the frozen build); found "
        f"only: {[entry[1] for entry in datas]}"
    )
    source_dir = Path(template_entries[0][0])
    assert source_dir.is_dir()
    assert {"agent.yaml", "agent.py"} <= {path.name for path in source_dir.iterdir()}


def test_bytefray_spec_still_bundles_starter_agents(monkeypatch):
    """Confirms adding the agent_template entry did not disturb starter_agents."""

    datas = _exec_spec_datas(BYTEFRAY_SPEC, monkeypatch)
    assert any(entry[1] == "battle_engine/data/starter_agents" for entry in datas)


def test_bytefray_spec_bundles_designer_branding_icon(monkeypatch):
    """The unified ``bytefray.exe design`` path must retain Beta3 branding."""

    datas = _exec_spec_datas(BYTEFRAY_SPEC, monkeypatch)
    branding_entries = [entry for entry in datas if entry[1] == "assets/branding"]
    assert branding_entries, (
        "tools/bytefray.spec's `datas` must bundle the package-local "
        "branding directory used by the Beta3 Designer identity header"
    )
    source_dir = Path(branding_entries[0][0])
    assert source_dir.is_dir()
    assert (source_dir / "bytefray-icon.png").is_file()


def test_agent_designer_spec_bundles_the_agent_template_directory(monkeypatch):
    """Regression test for the Phase 4a packaging blocker (agent_designer_workflow.md Sec 17.3).

    Phase 4a's "New Agent" workflow calls
    ``battle_engine.agent_scaffold.create_agent`` directly, in-process, from
    inside the Designer's own executable -- there is no subprocess
    boundary for scaffolding (Sec 5 of the spec). Before this fix,
    ``tools/agent_designer.spec`` bundled ``battle_engine/data/
    starter_agents`` but had no equivalent entry for the sibling
    ``battle_engine/data/agent_template`` directory, so a frozen
    ``bytefray-agent-designer.exe`` would fail "New Agent" with a
    ``FileNotFoundError`` from ``template_resource_dir`` -- the identical
    class of bug already fixed for ``bytefray.exe`` above.
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


def test_agent_designer_spec_bundles_the_annotated_agent_template_directory(monkeypatch):
    """Regression test for the Designer half of the Phase 5 annotated-template gap.

    Same defect class as ``test_bytefray_spec_bundles_the_annotated_agent_
    template_directory`` above: ``tools/agent_designer.spec`` bundled the
    original ``agent_template`` directory but not the sibling
    ``agent_template_annotated`` directory the Designer's New Agent dialog's
    "Annotated Example" choice depends on, so a frozen
    ``bytefray-agent-designer.exe`` would fail that choice with a
    ``FileNotFoundError`` from ``template_resource_dir`` even though the
    "blank" template already worked.
    """

    datas = _exec_spec_datas(AGENT_DESIGNER_SPEC, monkeypatch)
    template_entries = [
        entry for entry in datas if entry[1] == "battle_engine/data/agent_template_annotated"
    ]
    assert template_entries, (
        "tools/agent_designer.spec's `datas` must bundle "
        "battle_engine/data/agent_template_annotated (needed by the "
        "Designer's New Agent 'Annotated Example' choice in the frozen "
        f"build); found only: {[entry[1] for entry in datas]}"
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


class _RecordingAnalysis:
    """Fake ``Analysis`` whose attributes are distinguishable sentinels.

    Lets a test assert *which* attributes a spec's ``EXE``/``COLLECT`` calls
    actually reference, without needing a real PyInstaller build -- e.g.
    proving ``COLLECT`` receives ``a.binaries`` (the onedir "loose files
    beside the launcher" shape) rather than only ``exe`` (the onefile-style
    "everything baked into one binary" shape a spec falls back to if it
    omits ``exclude_binaries=True``/``a.binaries`` from its ``EXE``/
    ``COLLECT`` calls).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.pure = "ANALYSIS.pure"
        self.scripts = "ANALYSIS.scripts"
        self.binaries = "ANALYSIS.binaries"
        self.datas = "ANALYSIS.datas"
        self.zipped_data = "ANALYSIS.zipped_data"
        self.zipfiles = "ANALYSIS.zipfiles"


def _exec_spec_calls(spec_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Execute a spec file, recording the exact args passed to ``EXE``/``COLLECT``."""

    calls: dict[str, Any] = {}

    def _pyz(*args: object, **kwargs: object) -> str:
        return "PYZ_RESULT"

    def _exe(*args: object, **kwargs: object) -> str:
        calls["exe_args"] = args
        calls["exe_kwargs"] = kwargs
        return "EXE_RESULT"

    def _collect(*args: object, **kwargs: object) -> str:
        calls["collect_args"] = args
        calls["collect_kwargs"] = kwargs
        return "COLLECT_RESULT"

    _exec_spec(
        spec_path,
        monkeypatch,
        analysis=_RecordingAnalysis,
        pyz=_pyz,
        exe=_exe,
        collect=_collect,
    )
    return calls


@pytest.mark.parametrize("spec_path", ALL_SPECS, ids=lambda p: p.stem)
def test_spec_builds_onedir_layout_not_a_fat_exe(spec_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for a real, previously-shipped packaging inconsistency (v1.3 Area E).

    ``tools/agent_designer.spec``/``tools/replay_viewer.spec`` used to call
    ``EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, ...)`` with no
    ``exclude_binaries=True`` and then ``COLLECT(exe, name=...)`` with no
    further arguments -- baking every dependency into one large,
    self-contained ``EXE`` first and only wrapping *that* in a onedir
    folder, unlike ``tools/bytefray.spec``/``tools/bytefray_cli.spec``, which
    build a thin launcher ``EXE`` (``exclude_binaries=True``) and let
    ``COLLECT`` place binaries/data as loose files beside it -- the actual
    onedir layout ``ARCHITECTURE.md`` and ``tools/installer.iss`` both
    assume for all four applications. This proves, for every one of the
    four shipped specs, that ``EXE`` is called with
    ``exclude_binaries=True`` and that ``COLLECT`` receives the Analysis
    object's own ``binaries``/``datas`` (not just the bare ``exe`` result),
    without requiring a real, multi-second PyInstaller build.
    """

    calls = _exec_spec_calls(spec_path, monkeypatch)
    assert calls["exe_kwargs"].get("exclude_binaries") is True, (
        f"{spec_path.name}: EXE(...) must be called with exclude_binaries=True "
        "for a onedir (thin-launcher) build, matching tools/bytefray.spec's "
        f"pattern; got kwargs={calls['exe_kwargs']}"
    )
    collect_args = calls["collect_args"]
    assert "ANALYSIS.binaries" in collect_args, (
        f"{spec_path.name}: COLLECT(...) must receive the Analysis object's "
        "own .binaries so loose DLLs/data sit beside the launcher exe, not "
        f"baked into it; got args={collect_args}"
    )
    assert "ANALYSIS.datas" in collect_args, (
        f"{spec_path.name}: COLLECT(...) must receive the Analysis object's "
        f"own .datas; got args={collect_args}"
    )


def test_windows_build_waits_for_gui_smokes_and_requires_temp_cleanup() -> None:
    """Pin the Windows-only synchronization needed by the frozen GUI smoke.

    A GUI-subsystem executable launched with PowerShell's call operator
    returns control before the process exits. That made the standalone
    Designer smoke read a stale ``$LASTEXITCODE`` and race cleanup of its
    isolated data root. The canonical Windows build is the behavioral test;
    this cross-platform source check ensures the build script keeps the
    required wait/exit-code and fail-closed cleanup primitives in place.
    """

    source = BUILD_WIN_SCRIPT.read_text(encoding="utf-8")
    gui_start = source.index("$PreviousSmokeExit")
    gui_end = source.index("# Exercise 'bytefray agents create'", gui_start)
    gui_block = source[gui_start:gui_end]

    assert "& $Smoke.Path" not in gui_block
    assert "Start-Process @StartProcessArgs" in gui_block
    assert "FilePath    = $Smoke.Path" in gui_block
    assert "Wait        = $true" in gui_block
    assert "PassThru    = $true" in gui_block
    assert "$SmokeProcess.ExitCode" in gui_block
    assert "[Guid]::NewGuid()" in gui_block
    assert "} finally {" in gui_block
    assert "$env:BYTEFRAY_ROOT = $PreviousGuiSmokeRoot" in gui_block
    assert "Remove-Item Env:BYTEFRAY_ROOT" in gui_block
    assert "BATTLE2_ROOT" not in source
    assert "BATTLE_ROOT" not in source
    assert "Remove-Item -LiteralPath $GuiSmokeRoot -Recurse -Force -ErrorAction Stop" in gui_block
    assert "if (Test-Path -LiteralPath $GuiSmokeRoot)" in gui_block

    create_start = gui_end
    create_end = source.index("# Final proof", create_start)
    create_block = source[create_start:create_end]
    assert "Remove-Item -LiteralPath $SmokeRoot -Recurse -Force -ErrorAction Stop" in create_block
    assert "if (Test-Path -LiteralPath $SmokeRoot)" in create_block
