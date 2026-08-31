"""Generate comparative summary tables from comparison.json."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
comp = json.loads((REPO / "runs" / "research_v4_scheduler" / "comparison.json").read_text(encoding="utf-8"))
base = comp["baseline_seq"]
inter = comp["candidate_inter"]
sweep = comp.get("budget_sweep", {})

# Load corpus definition to check documented historical rates
corpus_path = REPO / "engine" / "src" / "battle_engine" / "data" / "benchmarks" / "v2_baseline_corpus.json"
corpus = json.loads(corpus_path.read_text(encoding="utf-8"))

print("=========================================================================================")
print("TABLE 1: DOCUMENTED HISTORICAL (V2-BETA2/PHASE0) VS NEWLY REPRODUCED BASELINE (V3.0.0)")
print("=========================================================================================")
print(f"{'Roster ID':<36} | {'Agent':<22} | {'Doc Rate':<10} | {'Repro Rate':<10} | {'Status'}")
print("-" * 95)
for entry in corpus["group"]["rosters"]:
    r_id = entry["id"]
    doc_rates = entry.get("beta2_win_rates", {})
    repro = base["rosters"][r_id]["entrants"]
    for agent in entry["roster"]:
        dr = doc_rates.get(agent, 0.0) * 100
        rr = repro[agent]["win_rate"] * 100
        match = "EXACT MATCH" if abs(dr - rr) < 0.2 else f"DIFF: {rr-dr:+.1f}%"
        print(f"{r_id:<36} | {agent:<22} | {dr:9.1f}% | {rr:9.1f}% | {match}")

print("\n=========================================================================================")
print("TABLE 2: BLOCK-SEQUENTIAL VS FINE-GRAINED INTERLEAVED SCHEDULING (BUDGET=8)")
print("=========================================================================================")
header = f"{'Roster ID':<34} | {'Agent':<20} | {'Seq Win':<8} | {'Int Win':<8} | {'Delta':<7} | {'Seq Surv':<8} | {'Int Surv':<8} | {'Seq Seat':<8} | {'Int Seat':<8}"
print(header)
print("-" * len(header))
for r_id in base["rosters"]:
    r_base = base["rosters"][r_id]
    r_inter = inter["rosters"][r_id]
    for agent in r_base["roster"]:
        bw = r_base["entrants"][agent]["win_rate"] * 100
        iw = r_inter["entrants"][agent]["win_rate"] * 100
        bs = r_base["entrants"][agent]["survival"] * 100
        is_ = r_inter["entrants"][agent]["survival"] * 100
        bsb = r_base["seat_sensitivity"].get(agent, 0.0) * 100
        isb = r_inter["seat_sensitivity"].get(agent, 0.0) * 100
        print(f"{r_id:<34} | {agent:<20} | {bw:7.1f}% | {iw:7.1f}% | {iw-bw:+6.1f}% | {bs:7.1f}% | {is_:7.1f}% | {bsb:7.1f}% | {isb:7.1f}%")

print("\n=========================================================================================")
print("TABLE 3: PAIRWISE CONTROLS (SEQUENTIAL VS INTERLEAVED)")
print("=========================================================================================")
p_header = f"{'Pair ID':<30} | {'Candidate':<15} | {'Opponent':<15} | {'Seq Cand':<9} | {'Int Cand':<9} | {'Delta':<7} | {'Seq CandFirst':<14} | {'Int CandFirst':<14}"
print(p_header)
print("-" * len(p_header))
for p_id in base["pairwise"]:
    pb = base["pairwise"][p_id]
    pi = inter["pairwise"][p_id]
    cand = pb["candidate"]
    opp = pb["opponent"]
    bw = pb["win_rates"][cand] * 100
    iw = pi["win_rates"][cand] * 100
    b_cf = pb["candidate_first_wins"]
    i_cf = pi["candidate_first_wins"]
    print(f"{p_id:<30} | {cand:<15} | {opp:<15} | {bw:8.1f}% | {iw:8.1f}% | {iw-bw:+6.1f}% | {b_cf:>2}/15          | {i_cf:>2}/15")

print("\n=========================================================================================")
print("TABLE 4: BUDGET SENSITIVITY SWEEP (b=8, 16, 32)")
print("=========================================================================================")
s_header = f"{'Roster':<32} | {'Budget':<6} | {'Agent':<20} | {'Seq Win':<8} | {'Int Win':<8} | {'Seq Surv':<8} | {'Int Surv':<8} | {'Seq Seat':<8} | {'Int Seat':<8}"
print(s_header)
print("-" * len(s_header))

swept_rosters = [
    "hunter_coretracker_coreseeker",
    "claimer_coretracker_coredefender",
    "claimer_coredefender_reactive",
    "coredefender_reactive_coreseeker",
]

for b in [8, 16, 32]:
    for r_id in swept_rosters:
        k_seq = f"b{b}_seq_{r_id}"
        k_int = f"b{b}_inter_{r_id}"
        if k_seq in sweep and k_int in sweep:
            d_seq = sweep[k_seq]
            d_int = sweep[k_int]
            agents = list(d_seq["entrants"].keys())
            for agent in agents:
                bw = d_seq["entrants"][agent]["win_rate"] * 100
                iw = d_int["entrants"][agent]["win_rate"] * 100
                bs = d_seq["entrants"][agent]["survival"] * 100
                is_ = d_int["entrants"][agent]["survival"] * 100
                bsb = d_seq["seat_sensitivity"].get(agent, 0.0) * 100
                isb = d_int["seat_sensitivity"].get(agent, 0.0) * 100
                print(f"{r_id:<32} | {b:<6} | {agent:<20} | {bw:7.1f}% | {iw:7.1f}% | {bs:7.1f}% | {is_:7.1f}% | {bsb:7.1f}% | {isb:7.1f}%")

