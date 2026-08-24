"""RC2 regression coverage for v2.0.0-rc1's release-blocking defect.

Ruleset-v2 direct matches using product defaults gave every entrant start
address 0, collapsing every entrant's ``CORE_SIZE``-wide vulnerable core
onto the same window and eliminating every entrant but the last-seeded one
before its first action (see the RC2 governing task's root-cause writeup).
This module exercises the full fix: ``battle_engine.placement``'s pure
resolution logic, ``NativeMatchService``'s engine-side fail-closed overlap
guard, the CLI's own default/explicit start handling, and -- the boundary
the RC1 audit found untested -- Agent Designer's production command builder
feeding a real match execution and a real result artifact.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import standard_layouts
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    OverlappingCoreError,
    canonical_match_id,
)
from battle_engine.placement import resolve_direct_match_starts, spread_seat_starts
from battle_engine.python_runtime import core_addresses
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
    TerminationReason,
)

from app.services import engine_commands
from app.services.osutil import DefaultPaths

ROOT = Path(__file__).resolve().parents[2]
V1 = BYTEFRAY_RULESET_ID
V2 = BYTEFRAY_RULESET_V2_ID
ALPHA1 = BYTEFRAY_RULESET_V2_ALPHA1_ID
ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID

NOP_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _write_agent(agent_dir: Path, agent_id: str, source: bytes = NOP_SOURCE) -> None:
    agent_dir.mkdir(parents=True)
    manifest = {
        "kind": "python",
        "api_version": 1,
        "entrypoint": "agent.py:create_agent",
        "name": agent_id,
        "display": agent_id.title(),
        "version": "1.0",
    }
    agent_dir.joinpath("agent.yaml").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    agent_dir.joinpath("agent.py").write_bytes(source)


def _python_entrant(root: Path, agent_id: str, *, slot: str, start: int) -> MatchEntrant:
    from battle_engine.agents import resolve_agent

    _write_agent(root / "agents" / agent_id, agent_id)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


def _request(
    tmp_path: Path,
    entrants: tuple[MatchEntrant, ...],
    *,
    ruleset_id: str | None,
    arena_size: int = 512,
    max_ticks: int = 20,
    run_name: str = "run",
) -> MatchRequest:
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=8),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / run_name / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )


# ---------------------------------------------------------------------------
# battle_engine.placement -- pure resolution logic
# ---------------------------------------------------------------------------


def test_v1_omitted_starts_default_to_zero() -> None:
    assert resolve_direct_match_starts(
        ruleset_id=None, arena_size=4096, entrant_count=2, supplied_starts=[None, None]
    ) == (0, 0)
    assert resolve_direct_match_starts(
        ruleset_id=V1, arena_size=4096, entrant_count=3, supplied_starts=[None, None, None]
    ) == (0, 0, 0)


def test_v1_explicit_starts_are_preserved() -> None:
    assert resolve_direct_match_starts(
        ruleset_id=V1, arena_size=4096, entrant_count=2, supplied_starts=[10, None]
    ) == (10, 0)


def test_v2_omitted_two_entrant_starts_default_to_spread_layout() -> None:
    assert resolve_direct_match_starts(
        ruleset_id=V2, arena_size=512, entrant_count=2, supplied_starts=[None, None]
    ) == (0, 256)


def test_v2_omitted_three_entrant_starts_match_standard_layouts_spread() -> None:
    resolved = resolve_direct_match_starts(
        ruleset_id=V2, arena_size=512, entrant_count=3, supplied_starts=[None, None, None]
    )
    assert resolved == standard_layouts(3, 512)[0].seat_starts
    assert len(set(resolved)) == 3


def test_v2_partial_explicit_preserves_explicit_and_derives_omitted() -> None:
    resolved = resolve_direct_match_starts(
        ruleset_id=V2, arena_size=512, entrant_count=2, supplied_starts=[100, None]
    )
    assert resolved == (100, 256)


def test_v2_explicit_overlapping_starts_pass_through_unrepaired() -> None:
    # resolve_direct_match_starts never silently moves an explicit start --
    # overlap rejection is NativeMatchService's job, not this function's.
    assert resolve_direct_match_starts(
        ruleset_id=V2, arena_size=512, entrant_count=2, supplied_starts=[0, 0]
    ) == (0, 0)


@pytest.mark.parametrize("alpha_id", [ALPHA1, ALPHA11])
def test_historical_alpha_identities_keep_v1_style_zero_defaults(alpha_id: str) -> None:
    assert resolve_direct_match_starts(
        ruleset_id=alpha_id, arena_size=512, entrant_count=2, supplied_starts=[None, None]
    ) == (0, 0)


def test_supplied_starts_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        resolve_direct_match_starts(
            ruleset_id=V2, arena_size=512, entrant_count=2, supplied_starts=[None]
        )


def test_spread_seat_starts_matches_standard_layouts_for_several_n() -> None:
    for n in (2, 3, 4, 5):
        assert spread_seat_starts(n, 4096) == standard_layouts(n, 4096)[0].seat_starts


def test_spread_seat_starts_requires_at_least_one_entrant() -> None:
    with pytest.raises(ValueError):
        spread_seat_starts(0, 512)


# ---------------------------------------------------------------------------
# NativeMatchService -- engine-side fail-closed overlap guard
# ---------------------------------------------------------------------------


def test_v2_zero_zero_starts_fail_closed_instead_of_eliminating_a(tmp_path: Path) -> None:
    root = tmp_path / "data"
    entrants = (
        _python_entrant(root, "nop_a", slot="A", start=0),
        _python_entrant(root, "nop_b", slot="B", start=0),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2)
    with pytest.raises(OverlappingCoreError) as excinfo:
        NativeMatchService().run(request)
    assert "A" in str(excinfo.value)
    assert "B" in str(excinfo.value)
    assert not request.replay_path.exists()
    assert not request.replay_path.with_name("result.json").exists()
    assert not request.replay_path.with_name("summary.json").exists()


def test_v2_partial_overlap_0_and_4_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    entrants = (
        _python_entrant(root, "nop_a", slot="A", start=0),
        _python_entrant(root, "nop_b", slot="B", start=4),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2)
    with pytest.raises(OverlappingCoreError):
        NativeMatchService().run(request)


def test_v2_modular_wraparound_overlap_fails_closed(tmp_path: Path) -> None:
    # CORE_SIZE=8: a core starting at 508 in a 512-cell arena wraps to
    # {508, 509, 510, 511, 0, 1, 2, 3} -- overlapping a core starting at 0.
    assert set(core_addresses(508, 512)) & set(core_addresses(0, 512)) == {0, 1, 2, 3}

    root = tmp_path / "data"
    entrants = (
        _python_entrant(root, "nop_a", slot="A", start=508),
        _python_entrant(root, "nop_b", slot="B", start=0),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2, arena_size=512)
    with pytest.raises(OverlappingCoreError):
        NativeMatchService().run(request)


def test_v2_non_overlapping_starts_run_a_real_multi_tick_match(tmp_path: Path) -> None:
    root = tmp_path / "data"
    entrants = (
        _python_entrant(root, "nop_a", slot="A", start=0),
        _python_entrant(root, "nop_b", slot="B", start=256),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2, arena_size=512, max_ticks=20)
    result = NativeMatchService().run(request)
    assert result.ticks_run == 20
    assert result.termination_reason == TerminationReason.TICK_LIMIT
    for agent in result.agents:
        assert agent.alive
        assert agent.termination_reason != "core_captured"


@pytest.mark.parametrize("alpha_id", [ALPHA1, ALPHA11])
def test_historical_alpha_identities_are_not_gated_by_the_v2_overlap_guard(
    tmp_path: Path, alpha_id: str
) -> None:
    # The RC2 guard is scoped to the permanent bytefray-rules-2 identity
    # only -- historical alpha identities keep their pre-existing, unguarded
    # degenerate-overlap execution semantics exactly as before this fix.
    root = tmp_path / "data"
    entrants = (
        _python_entrant(root, "nop_a", slot="A", start=0),
        _python_entrant(root, "nop_b", slot="B", start=0),
    )
    request = _request(tmp_path, entrants, ruleset_id=alpha_id, arena_size=512, max_ticks=5)
    result = NativeMatchService().run(request)  # must not raise
    assert result.ticks_run == 1


def test_canonical_identity_distinguishes_broken_from_corrected_v2_defaults(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    spec_a = _python_entrant(root, "nop_a", slot="A", start=0).python_spec
    spec_b = _python_entrant(root, "nop_b", slot="B", start=0).python_spec

    broken = _request(
        tmp_path,
        (
            MatchEntrant.python("A", "nop_a", 0, spec_a),
            MatchEntrant.python("B", "nop_b", 0, spec_b),
        ),
        ruleset_id=V2,
        run_name="broken",
    )
    corrected = _request(
        tmp_path,
        (
            MatchEntrant.python("A", "nop_a", 0, spec_a),
            MatchEntrant.python("B", "nop_b", 256, spec_b),
        ),
        ruleset_id=V2,
        run_name="corrected",
    )
    corrected_again = _request(
        tmp_path,
        (
            MatchEntrant.python("A", "nop_a", 0, spec_a),
            MatchEntrant.python("B", "nop_b", 256, spec_b),
        ),
        ruleset_id=V2,
        run_name="corrected-again",
    )

    assert canonical_match_id(broken) != canonical_match_id(corrected)
    assert canonical_match_id(corrected) == canonical_match_id(corrected_again)


# ---------------------------------------------------------------------------
# CLI -- default/explicit/overlapping start resolution
# ---------------------------------------------------------------------------


def _pythonpath() -> str:
    paths = [ROOT / "engine" / "src", ROOT / "client" / "src", ROOT]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        paths.append(Path(existing))
    return os.pathsep.join(map(str, paths))


def _run_cli(args: list[str], *, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=_pythonpath(), BYTEFRAY_ROOT=str(data_root))
    return subprocess.run(
        [sys.executable, "-m", "battle_engine.cli", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _seed_cli_agents(root: Path, *names: str) -> None:
    for name in names:
        _write_agent(root / "agents" / name, name)


def test_cli_default_v2_two_entrants_run_a_real_match(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(replay.with_name("result.json").read_text())
    assert envelope["ticks"] == 20
    assert envelope["ruleset_id"] == "bytefray-rules-2"
    for entrant in envelope["entrants"]:
        assert entrant["termination_reason"] != "core_captured"


def test_cli_default_v2_three_entrants_run_a_real_match(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b", "nop_c")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b", "--c-type", "nop_c",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(replay.with_name("result.json").read_text())
    assert envelope["ticks"] == 20
    for entrant in envelope["entrants"]:
        assert entrant["termination_reason"] != "core_captured"


def test_cli_default_v1_omitted_starts_remain_zero(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "5",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 0, result.stderr
    # Ruleset v1 has no core-capture mechanic, so historical 0/0 starts are
    # harmless -- the match simply runs to the tick limit, exactly as before
    # this fix.
    envelope = json.loads(replay.with_name("result.json").read_text())
    assert envelope["ticks"] == 5


def test_cli_explicit_v2_starts_are_preserved_exactly(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "5",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--a-start", "0", "--b-start", "256",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(replay.with_name("result.json").read_text())
    assert envelope["ticks"] == 5


def test_cli_explicit_overlapping_v2_starts_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--a-start", "0", "--b-start", "0",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 2
    assert "non-overlapping" in result.stderr
    assert not replay.exists()
    assert not replay.with_name("result.json").exists()


def test_cli_explicit_partial_overlap_v2_starts_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--a-start", "0", "--b-start", "4",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 2
    assert "non-overlapping" in result.stderr


def test_cli_explicit_modular_wraparound_v2_starts_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--a-start", "508", "--b-start", "0",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 2
    assert "non-overlapping" in result.stderr


def test_cli_partial_omission_v2_derives_omitted_seat_and_preserves_explicit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    _seed_cli_agents(root, "nop_a", "nop_b")
    replay = tmp_path / "out" / "replay.jsonl"
    # A explicit at 100 (off the spread grid); B omitted -> derived from
    # spread_seat_starts(2, 512) = (0, 256), so B resolves to 256 regardless
    # of A's explicit override, and the two do not overlap.
    result = _run_cli(
        [
            "--arena", "512", "--ticks", "20",
            "--a-type", "nop_a", "--b-type", "nop_b",
            "--a-start", "100",
            "--ruleset", "bytefray-rules-2",
            "--replay", str(replay), "--quiet",
        ],
        cwd=tmp_path,
        data_root=root,
    )
    assert result.returncode == 0, result.stderr
    envelope = json.loads(replay.with_name("result.json").read_text())
    assert envelope["ticks"] == 20


# ---------------------------------------------------------------------------
# Designer production builder -> real match (the critical E2E regression)
# ---------------------------------------------------------------------------


def test_designer_default_v2_configuration_produces_a_real_match(tmp_path: Path) -> None:
    """RunConfig -> build_engine_command -> actual generated CLI arguments ->
    real match execution -> actual result artifact.

    This is the boundary regression the RC1 audit found missing:
    Ruleset-v2 engine tests used safe starts manually, and Designer tests
    only checked the generated argument *strings*, so nothing ever executed
    the exact argument list Designer's Simple/Advanced tabs actually hand
    to the CLI. Neither tab ever sets a start address (``RunConfig`` has no
    start fields -- see ``app/services/engine_commands.py``), so this
    reproduces v2.0.0-rc1's release-blocking defect exactly if the CLI's
    own default-placement resolution regresses.
    """

    agents_root = tmp_path / "agents_data"
    _seed_cli_agents(agents_root, "nop_a", "nop_b")

    # ``paths.root`` mirrors what the real (non-frozen) app passes: the
    # actual repo checkout, used to build a real PYTHONPATH -- distinct
    # from ``BYTEFRAY_ROOT`` (the agent/data root), which this test points
    # at its own isolated, seeded directory below.
    paths = DefaultPaths(
        root=ROOT,
        replay_path=tmp_path / "out" / "replay.jsonl",
        summary_path=tmp_path / "out" / "summary.json",
    )
    config = engine_commands.RunConfig(
        a_type="nop_a",
        b_type="nop_b",
        ruleset_id=V2,
        arena=512,
        ticks=20,
    )
    command, env = engine_commands.build_engine_command(config, paths)
    assert not any(arg in ("--a-start", "--b-start", "--c-start") for arg in command)

    env = dict(env)
    env["BYTEFRAY_ROOT"] = str(agents_root)
    result = subprocess.run(
        command, cwd=tmp_path, env=env, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr

    envelope = json.loads(paths.replay_path.with_name("result.json").read_text())
    assert envelope["ruleset_id"] == "bytefray-rules-2"
    assert envelope["ticks"] == 20
    for entrant in envelope["entrants"]:
        assert entrant["termination_reason"] != "core_captured"


def test_designer_advanced_configuration_also_omits_start_flags(tmp_path: Path) -> None:
    """Advanced's per-agent-params RunConfig also relies entirely on the
    CLI's own default-placement resolution -- no Designer surface ever sets
    a start address (the RC2 task's GUI scope boundary)."""

    paths = DefaultPaths(
        root=ROOT,
        replay_path=tmp_path / "out" / "replay.jsonl",
        summary_path=tmp_path / "out" / "summary.json",
    )
    config = engine_commands.RunConfig(
        a_type="nop_a",
        b_type="nop_b",
        ruleset_id=V2,
        arena=512,
        ticks=20,
        a_params={"byte": 1},
        b_params={"byte": 2},
    )
    command, _env = engine_commands.build_engine_command(config, paths)
    assert not any(arg in ("--a-start", "--b-start", "--c-start") for arg in command)
