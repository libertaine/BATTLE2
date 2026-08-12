"""v0.10 Phase 4: persisted Ruleset identity on native result/replay artifacts.

Covers the additive ``ruleset_id`` field on ``battle2.result``/
``battle2.replay``, the honest recovery policy for artifacts written before
it existed (``resolve_result_ruleset``/``resolve_replay_ruleset``), and the
cross-artifact consistency check that a resumed cell's result and its own
replay header cannot silently disagree about which Ruleset produced them.
See docs/RULES.md, docs/COMPATIBILITY.md, docs/RESULT_SCHEMA.md, and
docs/REPLAY_SCHEMA.md for the documented policy this pins.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_engine.agent_evaluation import EvaluationCell, _resumed_cell_mismatch
from battle_engine.agent_test import OPPONENT_SLOT, TESTED_AGENT_SLOT
from battle_engine.agents import resolve_agent
from battle_engine.builtins import build_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.replay import (
    MatchConfiguration,
    ReplayHeader,
    deserialize_record,
    iter_replay,
    resolve_replay_ruleset,
    serialize_record,
    write_replay,
)
from battle_engine.result_model import (
    ReplayReference,
    ResultEnvelope,
    read_result,
    resolve_result_ruleset,
    write_json_atomic,
)
from battle_engine.rules import BYTEFRAY_RULESET_ID, RulesetProvenance

FIXTURES = Path(__file__).parent / "fixtures" / "replay"


# ---------------------------------------------------------------------------
# resolve_result_ruleset
# ---------------------------------------------------------------------------


def _envelope(*, mode: str, ruleset_id: str | None) -> ResultEnvelope:
    return ResultEnvelope(
        result_id="result_x",
        match_id="match_x",
        mode=mode,
        winner="A",
        termination_reason="last_agent_standing",
        ticks=1,
        ruleset_id=ruleset_id,
    )


def test_resolve_result_ruleset_recorded_when_present():
    envelope = _envelope(mode="b2", ruleset_id=BYTEFRAY_RULESET_ID)
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")


def test_resolve_result_ruleset_recovered_for_native_missing_field():
    """A pre-Phase-4 native (``mode: "b2"``) result -- VM or Python alike,
    per docs/RULES.md's proven source stability across the entire
    battle2.result v1 lifetime -- recovers as bytefray-rules-1.
    """

    envelope = _envelope(mode="b2", ruleset_id=None)
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recovered")


def test_resolve_result_ruleset_not_applicable_for_redcode():
    envelope = _envelope(mode="redcode94", ruleset_id=None)
    assert resolve_result_ruleset(envelope) == RulesetProvenance(None, "not_applicable")


def test_resolve_result_ruleset_never_stamps_redcode_even_if_field_were_present():
    """Defensive: even a hypothetically corrupted/foreign redcode94 result
    that somehow carries a ``ruleset_id`` is reported as exactly what it
    recorded (``recorded``), never silently promoted or demoted -- but a
    genuine pMARS writer (cli.py) never passes a real value for this field,
    only ever the default ``None`` (see the "absent vs null" tests below).
    """

    envelope = _envelope(mode="redcode94", ruleset_id=BYTEFRAY_RULESET_ID)
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")


def test_redcode_result_as_dict_carries_ruleset_id_key_with_null_value():
    """v0.10 Phase 4: ``ResultEnvelope.as_dict()`` is the one writer both the
    native and pMARS paths use (cli.py's redcode94 path never passes a
    ``ruleset_id`` value, so it defaults to ``None``) -- it always emits the
    ``ruleset_id`` *key*, so a current pMARS result.json has the JSON
    literal ``"ruleset_id": null``, never a wholly missing key. Only a
    result written before this field existed at all lacks the key
    structurally -- see ``test_result_missing_ruleset_id_key_entirely_still_reads``.
    """

    payload = _envelope(mode="redcode94", ruleset_id=None).as_dict()
    assert "ruleset_id" in payload
    assert payload["ruleset_id"] is None
    assert json.dumps(payload)  # confirms it serializes as JSON null, not an error


def test_redcode_result_missing_ruleset_id_key_entirely_still_resolves_not_applicable(tmp_path):
    """The genuinely-historical-absence case for a pMARS result (pre-Phase-4,
    key never existed) must resolve identically to the current writer's
    explicit ``null`` -- both are ``ResultEnvelope.ruleset_id is None``, and
    ``mode``, not key presence, is what actually carries "not applicable".
    """

    payload = _envelope(mode="redcode94", ruleset_id=None).as_dict()
    del payload["ruleset_id"]
    path = tmp_path / "result.json"
    write_json_atomic(path, payload)
    envelope = read_result(path)
    assert envelope.ruleset_id is None
    assert resolve_result_ruleset(envelope) == RulesetProvenance(None, "not_applicable")


def test_resolve_result_ruleset_unknown_for_unrecognized_mode():
    envelope = _envelope(mode="mystery", ruleset_id=None)
    assert resolve_result_ruleset(envelope) == RulesetProvenance(None, "unknown")


def test_result_envelope_round_trips_ruleset_id(tmp_path):
    envelope = _envelope(mode="b2", ruleset_id=BYTEFRAY_RULESET_ID)
    path = tmp_path / "result.json"
    write_json_atomic(path, envelope.as_dict())
    assert json.loads(path.read_text())["ruleset_id"] == BYTEFRAY_RULESET_ID
    assert read_result(path) == envelope


def test_result_missing_ruleset_id_key_entirely_still_reads(tmp_path):
    """A result.json written by any pre-Phase-4 Bytefray build has no
    ``ruleset_id`` key at all (not even ``null``) -- confirms the reader
    treats a wholly absent key the same as an explicit ``null``.
    """

    payload = _envelope(mode="b2", ruleset_id=None).as_dict()
    del payload["ruleset_id"]
    path = tmp_path / "result.json"
    write_json_atomic(path, payload)
    envelope = read_result(path)
    assert envelope.ruleset_id is None
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recovered")


# ---------------------------------------------------------------------------
# resolve_replay_ruleset
# ---------------------------------------------------------------------------


def test_resolve_replay_ruleset_recorded_when_present():
    header = ReplayHeader(MatchConfiguration(64), ruleset_id=BYTEFRAY_RULESET_ID, schema_version=3)
    assert resolve_replay_ruleset(header) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")


def test_resolve_replay_ruleset_recovered_for_v3_missing_field():
    header = ReplayHeader(MatchConfiguration(64), schema_version=3)
    assert resolve_replay_ruleset(header) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recovered")


def test_resolve_replay_ruleset_unknown_for_schema_version_2():
    header = ReplayHeader(MatchConfiguration(64), schema_version=2)
    assert resolve_replay_ruleset(header) == RulesetProvenance(None, "unknown")


def test_resolve_replay_ruleset_unknown_for_hypothetical_future_schema_version():
    """The recovery check is deliberately exact equality (``== 3``), never
    ``>=`` -- a hypothetical future schema version 4 header missing
    ``ruleset_id`` must not be silently auto-recovered as bytefray-rules-1
    just because ``4 >= 3``. Whether that future version's shape falls
    inside the proven-stable window is a fact to establish (and this
    function to update) deliberately when that version is introduced.
    """

    header = ReplayHeader(MatchConfiguration(64), schema_version=4)
    assert resolve_replay_ruleset(header) == RulesetProvenance(None, "unknown")


def test_resolve_replay_ruleset_unknown_for_genuine_v01_and_v02_fixtures():
    """Real historical fixtures (see docs/REPLAY_SCHEMA.md's "Supported
    input shapes"): an unversioned v0.1 header and a genuine v0.2.0-era
    canonical header both adapt to internal ``schema_version == 2`` and
    must remain UNKNOWN -- v0.2.0 predates the v0.3.0 "Bytefray Rename &
    Native Core" rewrite that docs/RULES.md's source-stability evidence
    actually covers (confirmed by inspecting the v0.2.0 tag's own
    ``replay.py``, whose own SCHEMA_VERSION is genuinely 2), so recovering
    Ruleset v1 for either shape would be a guess, not evidence.
    """

    for filename in ("v01_header.json", "v02_header.json"):
        record = deserialize_record((FIXTURES / filename).read_text(encoding="utf-8"))
        assert isinstance(record, ReplayHeader)
        assert resolve_replay_ruleset(record) == RulesetProvenance(None, "unknown")


def test_replay_header_round_trips_ruleset_id():
    header = ReplayHeader(
        MatchConfiguration(64, 4, 1),
        {"A": "writer"},
        match_id="match_1",
        result_id="result_1",
        runtime_kind="vm",
        ruleset_id=BYTEFRAY_RULESET_ID,
    )
    assert deserialize_record(serialize_record(header)) == header


# ---------------------------------------------------------------------------
# End-to-end native writer coverage (VM and Python)
# ---------------------------------------------------------------------------


def test_native_vm_match_records_ruleset_id_in_result_and_replay(tmp_path):
    config = Config(arena_size=128, instr_per_tick=4, seed=7)
    entrants = (
        MatchEntrant("A", "writer", 0, build_agent("writer", 0, offset=48, byte=0x11)),
        MatchEntrant("B", "runner", 64, build_agent("runner", 64)),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(config=config, entrants=entrants, max_ticks=20, replay_path=replay_path, verbose=False)
    )

    envelope = read_result(result.result_path)
    assert envelope.ruleset_id == BYTEFRAY_RULESET_ID
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")

    header = next(record for record in iter_replay(result.replay_path) if isinstance(record, ReplayHeader))
    assert header.ruleset_id == BYTEFRAY_RULESET_ID
    assert header.runtime_kind == "vm"
    assert resolve_replay_ruleset(header) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")


_PASSIVE_PYTHON_SOURCE = """
from battle_engine.agent_api import ActionKind, AgentAction

class Agent:
    def reset(self, context):
        pass

    def act(self, observation):
        return AgentAction(ActionKind.HALT)

def create_agent():
    return Agent()
"""


def _python_spec(root: Path, name: str):
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "name": name,
                "display": name.title(),
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(_PASSIVE_PYTHON_SOURCE, encoding="utf-8")
    return resolve_agent(root, name)


def test_native_python_match_records_ruleset_id_in_result_and_replay(tmp_path):
    config = Config(arena_size=128, instr_per_tick=4, seed=11)
    entrants = (
        MatchEntrant.python("A", "alpha", 0, _python_spec(tmp_path, "alpha")),
        MatchEntrant.python("B", "beta", 32, _python_spec(tmp_path, "beta")),
    )
    replay_path = tmp_path / "replay.jsonl"
    result = NativeMatchService().run(
        MatchRequest(config=config, entrants=entrants, max_ticks=5, replay_path=replay_path, verbose=False)
    )

    envelope = read_result(result.result_path)
    assert envelope.ruleset_id == BYTEFRAY_RULESET_ID
    assert resolve_result_ruleset(envelope) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")

    header = next(record for record in iter_replay(result.replay_path) if isinstance(record, ReplayHeader))
    assert header.ruleset_id == BYTEFRAY_RULESET_ID
    assert header.runtime_kind == "python"
    assert resolve_replay_ruleset(header) == RulesetProvenance(BYTEFRAY_RULESET_ID, "recorded")


# ---------------------------------------------------------------------------
# Cross-artifact consistency: evaluation resume (agent_evaluation._resumed_cell_mismatch)
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


def test_resumed_cell_mismatch_detects_ruleset_id_divergence(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id=BYTEFRAY_RULESET_ID,
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
        ruleset_id="corrupted-ruleset-id",
    )
    reason = _resumed_cell_mismatch(envelope, _cell(tmp_path), "match_x")
    assert reason is not None and "ruleset_id" in reason


def test_resumed_cell_mismatch_accepts_matching_ruleset_id(tmp_path):
    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [
            ReplayHeader(
                MatchConfiguration(64),
                match_id="match_x",
                result_id="result_x",
                ruleset_id=BYTEFRAY_RULESET_ID,
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
        ruleset_id=BYTEFRAY_RULESET_ID,
    )
    assert _resumed_cell_mismatch(envelope, _cell(tmp_path), "match_x") is None


def test_resumed_cell_mismatch_accepts_historical_pair_both_missing(tmp_path):
    """Two pre-Phase-4 artifacts (neither carries ``ruleset_id`` at all)
    must not be flagged as contradicting each other merely for both being
    silent -- ``None == None`` is consistency, not evidence of conflict.
    """

    replay_path = tmp_path / "replay.jsonl"
    write_replay(
        replay_path,
        [ReplayHeader(MatchConfiguration(64), match_id="match_x", result_id="result_x")],
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
    )
    assert _resumed_cell_mismatch(envelope, _cell(tmp_path), "match_x") is None
