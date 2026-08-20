"""``bytefray-rules-2`` -- v2.0.0-beta1 permanent Ruleset identity tests.

Covers docs/V2_0_BETA1_PLAN.md's foundation checklist: the permanent
identity resolves through the same fail-closed dispatch seam as every other
Ruleset; it is registered under its own explicit key, never an alias of
``bytefray-rules-2-alpha11`` or any other identity; it carries the exact
same Vulnerable Core / Consistent Core Observability mechanics as alpha.11
(``CORE_SIZE = 8``, ``CORE_BEACON_BYTE = 0xCE``); persisted result/replay
artifacts record it correctly; canonical match identity is distinct from
v1, alpha1, and alpha11 for otherwise-identical inputs; and cross-Ruleset
resume/comparison both fail closed against it, exactly as they already do
for every other identity.

This file intentionally mirrors ``test_ruleset_v2_alpha11.py``'s own
fixtures and scenario shapes rather than reinventing them -- the permanent
identity's behavior is promoted, not redesigned, so its acceptance coverage
should look the same modulo the identity under test. See
``test_ruleset_v2_promotion_equivalence.py`` for the direct alpha11-vs-v2
matched-corpus equivalence proof.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_engine.agent_evaluation import EvaluationCell, _resumed_cell_mismatch
from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    canonical_match_id,
)
from battle_engine.python_runtime import (
    CORE_BEACON_BYTE,
    CORE_SIZE,
    core_addresses,
    core_seed_byte,
    has_observable_core,
    has_vulnerable_core,
)
from battle_engine.replay import (
    MatchConfiguration,
    ReplayHeader,
    TickSnapshot,
    iter_replay,
    write_replay,
)
from battle_engine.result_model import ReplayReference, ResultEnvelope, read_result
from battle_engine.rules import BYTEFRAY_RULESET_ID, normalize_ruleset_id
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ALPHA1_ID,
    BYTEFRAY_RULESET_V2_ALPHA11_ID,
    BYTEFRAY_RULESET_V2_ID,
    RULESET_V1,
    RULESET_V2,
    RULESET_V2_ALPHA1,
    RULESET_V2_ALPHA11,
    UnknownRulesetError,
    resolve_ruleset_policy,
)

V1 = BYTEFRAY_RULESET_ID
ALPHA1 = BYTEFRAY_RULESET_V2_ALPHA1_ID
ALPHA11 = BYTEFRAY_RULESET_V2_ALPHA11_ID
V2 = BYTEFRAY_RULESET_V2_ID


def _write_agent(agent_dir: Path, agent_id: str, source: bytes) -> None:
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


def _python_entrant(root: Path, agent_id: str, source: bytes, *, slot: str, start: int):
    from battle_engine.agents import resolve_agent

    agent_dir = root / "agents" / agent_id
    _write_agent(agent_dir, agent_id, source)
    return MatchEntrant.python(slot, agent_id, start, resolve_agent(root, agent_id))


NOP_SOURCE = b"""from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.NOP)

def create_agent():
    return Agent()
"""


def _scripted_writer_source(addresses: list[int], value: int = 0xAA) -> bytes:
    return (
        "from battle_engine.agent_api import ActionKind, AgentAction\n\n"
        f"ADDRESSES = {addresses!r}\n\n"
        "class Agent:\n"
        "    def reset(self, context):\n"
        "        self.index = 0\n\n"
        "    def act(self, observation):\n"
        "        if self.index < len(ADDRESSES):\n"
        "            addr = ADDRESSES[self.index]\n"
        "            self.index += 1\n"
        f"            return AgentAction(ActionKind.WRITE, addr, {value})\n"
        "        return AgentAction(ActionKind.NOP)\n\n"
        "def create_agent():\n"
        "    return Agent()\n"
    ).encode()


def _request(
    tmp_path: Path,
    entrants,
    *,
    ruleset_id: str | None,
    arena_size: int = 128,
    instr_per_tick: int = 8,
    max_ticks: int = 20,
    run_name: str = "run",
) -> MatchRequest:
    return MatchRequest(
        Config(arena_size=arena_size, instr_per_tick=instr_per_tick),
        entrants,
        max_ticks=max_ticks,
        replay_path=tmp_path / run_name / "replay.jsonl",
        verbose=False,
        ruleset_id=ruleset_id,
    )


def _final_arena(result, arena_size: int) -> dict[int, int]:
    arena: dict[int, int] = {}
    for record in iter_replay(result.replay_path):
        if not isinstance(record, TickSnapshot):
            continue
        for diff in record.memory_diffs:
            for offset, value in enumerate(diff.values):
                arena[(diff.address + offset) % arena_size] = value
    return arena


# ---------------------------------------------------------------------------
# Dispatch: resolves v1 / alpha1 / alpha11 / permanent v2, fails closed
# otherwise, and is not aliased to anything
# ---------------------------------------------------------------------------


def test_permanent_v2_resolves_explicitly() -> None:
    policy = resolve_ruleset_policy(V2)
    assert policy is RULESET_V2
    assert policy.ruleset_id == "bytefray-rules-2"


def test_all_four_identities_resolve_to_four_distinct_policy_objects() -> None:
    resolved = {
        V1: resolve_ruleset_policy(V1),
        ALPHA1: resolve_ruleset_policy(ALPHA1),
        ALPHA11: resolve_ruleset_policy(ALPHA11),
        V2: resolve_ruleset_policy(V2),
    }
    assert resolved[V1] is RULESET_V1
    assert resolved[ALPHA1] is RULESET_V2_ALPHA1
    assert resolved[ALPHA11] is RULESET_V2_ALPHA11
    assert resolved[V2] is RULESET_V2
    assert len({id(policy) for policy in resolved.values()}) == 4


def test_unknown_ruleset_ids_still_fail_closed_alongside_the_new_identity() -> None:
    import pytest

    for unknown in ("bytefray-rules-3", "bytefray-rules-2-alpha12", "BYTEFRAY-RULES-2", ""):
        with pytest.raises(UnknownRulesetError):
            resolve_ruleset_policy(unknown)


def test_permanent_v2_is_not_an_alias_of_alpha11_or_anything_else() -> None:
    """The alias table (``rules._RULESET_ALIASES``) governs historical
    artifact-identity normalization, not runtime dispatch, and must gain no
    entry for either direction of alpha11 <-> v2 (docs/V2_0_BETA1_PLAN.md's
    "No aliasing" section)."""

    assert normalize_ruleset_id(V2) == V2
    assert normalize_ruleset_id(ALPHA11) == ALPHA11
    assert normalize_ruleset_id(ALPHA11) != V2
    assert normalize_ruleset_id(V2) != ALPHA11
    assert resolve_ruleset_policy(V2) is not resolve_ruleset_policy(ALPHA11)


# ---------------------------------------------------------------------------
# Mechanic parity: permanent v2 carries alpha.11's exact semantics
# ---------------------------------------------------------------------------


def test_permanent_v2_has_vulnerable_core_and_observable_core() -> None:
    assert has_vulnerable_core(V2) is True
    assert has_observable_core(V2) is True


def test_permanent_v2_core_seed_byte_is_the_beacon() -> None:
    assert core_seed_byte(V2) == CORE_BEACON_BYTE == 0xCE


def test_permanent_v2_constants_match_the_frozen_beta1_decision() -> None:
    """docs/V2_0_BETA1_PLAN.md's fixed-constants decision: CORE_SIZE=8 and
    CORE_BEACON_BYTE=0xCE are Ruleset-v2 semantic constants, not per-match
    configuration -- pinned here as literal values, not just symbol
    equality, so an accidental redefinition upstream is caught too."""

    assert CORE_SIZE == 8
    assert CORE_BEACON_BYTE == 0xCE


def test_alpha1_and_v1_are_unaffected_by_the_new_identity() -> None:
    assert has_vulnerable_core(ALPHA1) is True
    assert has_observable_core(ALPHA1) is False
    assert has_vulnerable_core(V1) is False
    assert has_observable_core(V1) is False


def test_permanent_v2_core_footprint_matches_alpha11(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2, max_ticks=3)
    result = NativeMatchService().run(request)
    arena = _final_arena(result, 128)
    for address in core_addresses(20, 128):
        assert arena[address] == CORE_BEACON_BYTE
    for address in core_addresses(60, 128):
        assert arena[address] == CORE_BEACON_BYTE


def test_permanent_v2_ordinary_writes_still_capture_a_core(tmp_path) -> None:
    core = list(core_addresses(20, 128))
    entrants = (
        _python_entrant(tmp_path, "victim", NOP_SOURCE, slot="A", start=20),
        _python_entrant(
            tmp_path, "attacker", _scripted_writer_source(core), slot="B", start=60
        ),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2)
    result = NativeMatchService().run(request)
    victim = result.agents_by_id["A"]
    attacker = result.agents_by_id["B"]
    assert victim.alive is False
    assert victim.termination_reason == "core_captured"
    assert attacker.kills == 1
    assert result.winner == "B"


# ---------------------------------------------------------------------------
# Artifact identity: result, replay, canonical match id
# ---------------------------------------------------------------------------


def test_replay_and_result_record_the_permanent_v2_identity(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    request = _request(tmp_path, entrants, ruleset_id=V2, max_ticks=3)
    result = NativeMatchService().run(request)

    headers = [
        record for record in iter_replay(result.replay_path) if not isinstance(record, TickSnapshot)
    ]
    assert headers and headers[0].ruleset_id == V2
    assert result.result_path is not None
    assert read_result(result.result_path).ruleset_id == V2


def test_canonical_match_identity_differs_across_all_four_rulesets(tmp_path) -> None:
    entrants = (
        _python_entrant(tmp_path, "idle_a", NOP_SOURCE, slot="A", start=20),
        _python_entrant(tmp_path, "idle_b", NOP_SOURCE, slot="B", start=60),
    )
    ids = {
        ruleset: canonical_match_id(
            _request(tmp_path, entrants, ruleset_id=ruleset, max_ticks=3)
        )
        for ruleset in (None, ALPHA1, ALPHA11, V2)
    }
    assert len(set(ids.values())) == 4


# ---------------------------------------------------------------------------
# Cross-Ruleset resume/comparison fail closed against the new identity
# ---------------------------------------------------------------------------


def _cell(artifact_dir: Path) -> EvaluationCell:
    return EvaluationCell(
        schedule_id="sched_x",
        subject_role="candidate",
        subject_id="candidate",
        opponent_id="opponent",
        seed=5,
        artifact_dir=artifact_dir,
    )


def test_resume_fails_closed_when_recorded_ruleset_is_alpha11_but_expected_is_v2(tmp_path) -> None:
    """A resumed cell whose replay header carries the historical alpha11
    identity must never be silently accepted as a v2 cell, even though the
    two identities share their behavioral implementation."""

    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id=ALPHA11,
            )
        ],
    )
    digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    envelope = ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode="b2",
        winner="tie",
        termination_reason="tick_limit",
        ticks=2,
        entrants=tuple({"agent_id": slot} for slot in (TESTED_AGENT_SLOT, OPPONENT_SLOT)),
        reproducibility={"seed": 5},
        replay=ReplayReference("r", digest, "replay.jsonl"),
        ruleset_id=V2,
    )
    reason = _resumed_cell_mismatch(envelope, _cell(tmp_path), "match_x")
    assert reason is not None and "ruleset_id" in reason


def test_resume_accepts_a_matching_permanent_v2_pair(tmp_path) -> None:
    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id=V2,
            )
        ],
    )
    digest = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    envelope = ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode="b2",
        winner="tie",
        termination_reason="tick_limit",
        ticks=2,
        entrants=tuple({"agent_id": slot} for slot in (TESTED_AGENT_SLOT, OPPONENT_SLOT)),
        reproducibility={"seed": 5},
        replay=ReplayReference("r", digest, "replay.jsonl"),
        ruleset_id=V2,
    )
    assert _resumed_cell_mismatch(envelope, _cell(tmp_path), "match_x") is None


def test_evaluation_comparison_never_aligns_v2_cells_against_alpha11_cells() -> None:
    """``evaluation_history.comparison``'s existing ``rules_id``-keyed
    alignment refusal, exercised directly for the new identity pair -- the
    same generic mechanism that already refuses v1/alpha1/alpha11
    cross-comparison must refuse alpha11/v2 too, with no special-case code
    required."""

    from battle_engine.evaluation_history.comparison import align
    from test_evaluation_history_comparison import _cell as _comparison_cell
    from test_evaluation_history_comparison import _summary

    left = _summary(cells=(_comparison_cell(outcome="win"),), rules_id=ALPHA11)
    right = _summary(cells=(_comparison_cell(outcome="win"),), rules_id=V2)
    result = align(left, right)
    assert result.denominators.directly_comparable == 0
