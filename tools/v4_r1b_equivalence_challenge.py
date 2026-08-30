"""v4 Research Experiment Driver: Process Equivalence Challenge (R1b).

Adversarial validation of the R1 multi-process conclusion.
Tests whether a monolithic Python control loop with a mailbox routing architecture
can faithfully replicate the strategic capability of a true multi-process entrant
under the exact same K=2 chunked scheduler.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any

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


def run_equivalence_test(opp_factory, ticks=100, seed=42) -> bool:
    cfg = lambda: Config(arena_size=4096, instr_per_tick=8, seed=seed,
                         win_mode="score_fallback",
                         weights=Weights(alive=1.0, kill=5.0, territory=1.0, territory_bucket=64))

    # Run genuine
    g_spec = make_triple_process_def_scout_atk("A", alloc=(4, 2, 2))
    g_traces = instrument_genuine(g_spec)
    cg = ProcessMatchController(cfg(), [g_spec, opp_factory("B")], max_ticks=ticks, model=ProcessModel.MODEL_A_CURSOR)
    cg.run()

    # Run mailbox monolith
    m_spec = make_monolithic_triple_sim("A")
    m_traces = instrument_monolithic(m_spec)
    cm = ProcessMatchController(cfg(), [m_spec, opp_factory("B")], max_ticks=ticks, model=ProcessModel.MODEL_A_CURSOR)
    cm.run()

    if len(g_traces) != len(m_traces):
        return False
    
    for g, m in zip(g_traces, m_traces):
        if g["act_k"] != m["act_k"] or g["act_o"] != m["act_o"] or g["act_v"] != m["act_v"]:
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
    
    for opp_name, opp_factory in opponents:
        print(f"\nTesting against {opp_name}...")
        for seed in [0, 42, 99]:
            ok = run_equivalence_test(opp_factory, ticks=50, seed=seed)
            if ok:
                print(f"  Seed {seed:3}: PASS")
            else:
                print(f"  Seed {seed:3}: FAIL")
            if not ok:
                all_pass = False
            results[f"{opp_name}_s{seed}"] = ok

    out_file = args.output / "r1b_equivalence_results.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    
    if all_pass:
        print("\nVERDICT: Mailbox monolith achieves EXACT differential equivalence.")
        print("Codex's rejection of Decision B is CONFIRMED.")
    else:
        print("\nVERDICT: Mailbox monolith FAILS exact equivalence.")
        
if __name__ == "__main__":
    main()
