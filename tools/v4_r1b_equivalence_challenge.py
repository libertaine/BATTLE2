"""v4 Research Experiment Driver: Process Equivalence Challenge (R1b).

Adversarial validation of the R1 multi-process conclusion.
Tests whether a monolithic Python control loop with a mailbox routing architecture
can faithfully replicate the strategic capability of a true multi-process entrant
under the exact same K=2 chunked scheduler.

This is exact deterministic differential testing, not a statistical study:
every role's logic here is a pure function of its observation and its own
local state, Config.seed is not consumed anywhere in process_runtime.py or
process_agents.py, and neither controller uses randomness. Each
(opponent, seat order) combination therefore has exactly one possible
outcome -- there is no seed dimension to sample over.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "engine" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "engine" / "src"))

from battle_engine.config import Config, Weights
from battle_engine.process_agents import (
    make_monolithic_triple_sim,
    make_single_process_claimer,
    make_single_process_defender,
    make_single_process_hunter,
    make_triple_process_def_scout_atk,
)
from battle_engine.process_runtime import (
    ProcessMatchController,
    ProcessModel,
)


def instrument_genuine(spec):
    traces = []
    pid_to_role = {"proc_def": "def", "proc_scout": "scout", "proc_atk": "atk"}
    for p in spec.processes:
        orig = p.logic
        pid = p.process_id
        role = pid_to_role[pid]
        def make_w(_role, _orig):
            def w(obs, state):
                action = _orig(obs, state)
                traces.append({
                    "tick": obs.tick,
                    "role": _role,
                    "obs_lak": str(obs.last_action_kind),
                    "obs_lao": obs.last_action_operand,
                    "obs_rr": obs.read_result,
                    "obs_ro": obs.read_owner,
                    "act_k": str(action.kind),
                    "act_o": action.operand,
                    "act_v": action.value,
                })
                return action
            return w
        p.logic = make_w(role, orig)
    return traces


def instrument_monolithic(spec):
    traces = []
    p = spec.processes[0]
    orig = p.logic
    def w(obs, state):
        action = orig(obs, state)
        traces.append({
            "tick": obs.tick,
            "role": state.get("prev", "unknown"), 
            "act_k": str(action.kind),
            "act_o": action.operand,
            "act_v": action.value,
        })
        return action
    p.logic = w
    return traces


def run_equivalence_test(opp_factory, ticks=100, focal_first=True) -> bool:
    # Config.seed is not consumed anywhere in process_runtime.py or
    # process_agents.py, and no role logic here uses randomness -- every run
    # of this experiment is fully deterministic given (opponent, seat order).
    # There is deliberately no seed parameter/loop: looping over seed values
    # would re-run the identical computation and could misleadingly read as
    # independent statistical samples. This is exact deterministic
    # differential testing, not a statistical comparison.
    cfg = lambda: Config(arena_size=4096, instr_per_tick=8,
                         win_mode="score_fallback",
                         weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64))

    # Run genuine
    g_spec = make_triple_process_def_scout_atk("A", alloc=(4, 2, 2))
    g_traces = instrument_genuine(g_spec)
    g_opp = opp_factory("B")
    g_entrants = [g_spec, g_opp] if focal_first else [g_opp, g_spec]
    cg = ProcessMatchController(cfg(), g_entrants, max_ticks=ticks, model=ProcessModel.MODEL_A_CURSOR)
    g_result = cg.run()

    # Run mailbox monolith
    m_spec = make_monolithic_triple_sim("A")
    m_traces = instrument_monolithic(m_spec)
    m_opp = opp_factory("B")
    m_entrants = [m_spec, m_opp] if focal_first else [m_opp, m_spec]
    cm = ProcessMatchController(cfg(), m_entrants, max_ticks=ticks, model=ProcessModel.MODEL_A_CURSOR)
    m_result = cm.run()

    if len(g_traces) != len(m_traces):
        return False

    for g, m in zip(g_traces, m_traces):
        if g["act_k"] != m["act_k"] or g["act_o"] != m["act_o"] or g["act_v"] != m["act_v"]:
            return False

    # Survival/termination equivalence: same winner/reason/tick count, and the
    # same per-agent alive outcome (not just implied by arena/score equality).
    if g_result["winner"] != m_result["winner"] or g_result["reason"] != m_result["reason"]:
        return False
    if g_result["ticks_run"] != m_result["ticks_run"]:
        return False
    g_alive = {st.agent_id: st.alive for st in cg.states}
    m_alive = {st.agent_id: st.alive for st in cm.states}
    if g_alive != m_alive:
        return False

    return (cg.vm.arena == cm.vm.arena and
            cg.vm.writer == cm.vm.writer and
            cg.score == cm.score)

def main() -> None:
    parser = argparse.ArgumentParser(description="v4 Research Tool: R1b Differential Equivalence Challenge")
    parser.add_argument("--output", type=Path, default=REPO / "runs" / "research_v4_r1b")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("R1b: EXACT DIFFERENTIAL EQUIVALENCE (MAILBOX MONOLITH)")
    print("=" * 80)
    
    opponents = [
        ("claimer", make_single_process_claimer),
        ("defender", make_single_process_defender),
        ("hunter", make_single_process_hunter),
    ]

    all_pass = True
    results = {}

    # Both entrant-list seat orders are exercised (focal-then-opponent and
    # opponent-then-focal) since seat/slot assignment determines core_base
    # placement and chunked-scheduler rotation offset -- a genuine
    # equivalence claim must not depend on which slot the focal entrant
    # happens to occupy. With only two entrants here (focal + one opponent
    # archetype at a time, never three at once), this is the full space of
    # seat orderings rather than a subset of the six permutations of three.
    for opp_name, opp_factory in opponents:
        print(f"\nTesting against {opp_name}...")
        for focal_first in (True, False):
            seat = "A,B" if focal_first else "B,A"
            ok = run_equivalence_test(opp_factory, ticks=50, focal_first=focal_first)
            print(f"  Seat [{seat}]: {'PASS' if ok else 'FAIL'}")
            if not ok:
                all_pass = False
            results[f"{opp_name}_{seat.replace(',', '')}"] = ok

    out_file = args.output / "r1b_equivalence_results.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    
    if all_pass:
        print("\nVERDICT: Mailbox monolith achieves EXACT differential equivalence.")
        print("Codex's rejection of Decision B is CONFIRMED.")
    else:
        print("\nVERDICT: Mailbox monolith FAILS exact equivalence.")
        
if __name__ == "__main__":
    main()
