import hashlib
import json
from pathlib import Path

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
    assert header["schema_version"] == 1
    binding = json.loads(lines[-1])
    assert binding["record_type"] == "binding"
    assert binding["replay_sha256"] == sha_b

