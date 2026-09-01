import hashlib
import json
from pathlib import Path

import pytest
from battle_engine.agent_trace import (
    TRACE_SCHEMA_VERSION_V2,
    TraceFormatError,
    read_trace,
    read_trace_v2,
)
from battle_engine.agents import resolve_agent
from battle_engine.config import Config, Weights
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.ruleset_policy import RULESET_V4_ALPHA1


def _write_agent(tmp_path: Path, name: str, source: str) -> None:
    agent_dir = tmp_path / "agents" / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "agent.py").write_text(source)
    (agent_dir / "agent.yaml").write_text(f"name: {name}\ndescription: Test agent\nversion: '1.0'\napi_version: 2\n")


def test_v4_trace_is_strictly_observational(tmp_path: Path) -> None:
    agent_a_code = '''
from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, ActionKindV2, MatchContextV2, ProcessDeclaration
class TracedAgentA:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="p1", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.tick = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        self.tick += 1
        return AgentAction(ActionKindV2.MOVE, 1)
def create_agent() -> AgentV2:
    return TracedAgentA()
'''

    agent_b_code = '''
from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, ActionKindV2, MatchContextV2, ProcessDeclaration
class ErrorAgentB:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="p1", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        self.tick = 0
    def act(self, obs: ObservationV2) -> AgentAction:
        if obs.current_tick == 3:
            raise ValueError("Intentional crash")
        return AgentAction(ActionKindV2.READ, 5)
def create_agent() -> AgentV2:
    return ErrorAgentB()
'''

    config = Config(seed=42, arena_size=100, instr_per_tick=8, win_mode="capture", weights=Weights())

    _write_agent(tmp_path, "agent_a", agent_a_code)
    _write_agent(tmp_path, "agent_b", agent_b_code)

    spec_a = resolve_agent(tmp_path, "agent_a")
    spec_b = resolve_agent(tmp_path, "agent_b")

    # Run A (Trace Disabled)
    replay_a_path = tmp_path / "run_a.jsonl"
    req_a = MatchRequest(
        config=config,
        entrants=(
            MatchEntrant.python("A", "Agent A", 0, spec_a),
            MatchEntrant.python("B", "Agent B", 50, spec_b),
        ),
        max_ticks=10,
        replay_path=replay_a_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    svc = NativeMatchService()
    result_a = svc.run(req_a)

    # Run B (Trace Enabled)
    replay_b_path = tmp_path / "run_b.jsonl"
    trace_path = tmp_path / "trace.jsonl"
    req_b = MatchRequest(
        config=config,
        entrants=(
            MatchEntrant.python("A", "Agent A", 0, spec_a),
            MatchEntrant.python("B", "Agent B", 50, spec_b),
        ),
        max_ticks=10,
        replay_path=replay_b_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    result_b = svc.run(req_b)

    assert result_a.winner == result_b.winner
    assert result_a.termination_reason == result_b.termination_reason
    
    sha_a = hashlib.sha256(replay_a_path.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(replay_b_path.read_bytes()).hexdigest()
    assert sha_a == sha_b

    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().split('\n')
    assert len(lines) > 2
    header = json.loads(lines[0])
    # V4/API-v2 matches must declare schema_version 2 -- reusing the v1
    # header's default of 1 here would make read_trace_v2() (which requires
    # exactly 2) unable to parse the trace it just wrote, and would prevent
    # v1 readers from rejecting it per docs/specs/v4_api_v2_trace.md §10.
    assert header["schema_version"] == TRACE_SCHEMA_VERSION_V2
    binding = json.loads(lines[-1])
    assert binding["record_type"] == "binding"
    assert binding["replay_sha256"] == sha_b

    # The trace must also be readable through the real v2 parser, not just
    # by hand-parsing raw JSONL -- this is what an analyzer/replay viewer
    # actually uses.
    document = read_trace_v2(trace_path)
    assert document.header.schema_version == TRACE_SCHEMA_VERSION_V2
    assert document.declarations
    assert document.decisions
    assert document.binding is not None
    assert document.binding.replay_sha256 == sha_b
    assert document.binding.match_id
    assert document.binding.entrant_identities == ("A", "B")

    # A v1 reader must reject a v2 trace outright at the header, rather than
    # silently misinterpreting v2-only record types as v1 decisions.
    with pytest.raises(TraceFormatError):
        read_trace(trace_path)


def test_v4_trace_v2_captures_normalized_address_for_applied_read_and_write(tmp_path: Path) -> None:
    """A successful READ/WRITE must record the effective address it hit.

    ``normalized_address`` previously stayed ``None`` for every applied READ
    and WRITE (only MOVE set it), so the trace could not answer "what
    address did this READ/WRITE actually touch" for the two action kinds
    where that question matters most.
    """

    writer_code = '''
from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, ActionKindV2, MatchContextV2, ProcessDeclaration
class WriterAgent:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="p1", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.WRITE, 5, 42)
def create_agent() -> AgentV2:
    return WriterAgent()
'''
    reader_code = '''
from battle_engine.agent_api import AgentV2, ObservationV2, AgentAction, ActionKindV2, MatchContextV2, ProcessDeclaration
class ReaderAgent:
    api_version = 2
    def declare_processes(self):
        return [ProcessDeclaration(id="p1", reach=10, share=1.0)]
    def reset(self, context: MatchContextV2):
        pass
    def act(self, obs: ObservationV2) -> AgentAction:
        return AgentAction(ActionKindV2.READ, 45)
def create_agent() -> AgentV2:
    return ReaderAgent()
'''

    config = Config(seed=7, arena_size=100, instr_per_tick=8, win_mode="capture", weights=Weights())

    _write_agent(tmp_path, "writer", writer_code)
    _write_agent(tmp_path, "reader", reader_code)

    spec_w = resolve_agent(tmp_path, "writer")
    spec_r = resolve_agent(tmp_path, "reader")

    replay_path = tmp_path / "replay.jsonl"
    trace_path = tmp_path / "trace.jsonl"
    request = MatchRequest(
        config=config,
        entrants=(
            MatchEntrant.python("W", "Writer", 0, spec_w),
            MatchEntrant.python("R", "Reader", 50, spec_r),
        ),
        max_ticks=3,
        replay_path=replay_path,
        trace_path=trace_path,
        ruleset_id=RULESET_V4_ALPHA1.ruleset_id,
    )
    NativeMatchService().run(request)

    document = read_trace_v2(trace_path)
    applied_writes = [
        d for d in document.decisions
        if d.action is not None and d.action.kind == "write" and d.applied_result is not None
        and d.applied_result.status == "APPLIED"
    ]
    applied_reads = [
        d for d in document.decisions
        if d.action is not None and d.action.kind == "read" and d.applied_result is not None
        and d.applied_result.status == "APPLIED"
    ]
    assert applied_writes, "expected at least one applied WRITE decision"
    assert applied_reads, "expected at least one applied READ decision"
    assert all(d.applied_result.normalized_address == 5 for d in applied_writes)  # type: ignore[union-attr]
    assert all(d.applied_result.normalized_address == 45 for d in applied_reads)  # type: ignore[union-attr]
    assert all(d.applied_result.read_value is not None for d in applied_reads)  # type: ignore[union-attr]

