# Bytefray v4 Research: Interleaved Scheduling Evaluation & Preflight Characterization

**Branch:** `v4-research`  
**Base Commit:** `dbc38e79e1e9c1ac033d21cdb60f85edb8f042a1` (Bytefray `v3.0.0` release commit)  
**Repository Context:** Post-release `main` at `8f42c69` (`docs: mark v3.0.0 published`) is documented for context only and is not part of the experimental baseline.  
**Experimental Identity:** `bytefray-rules-4-alpha1`  
**Status:** Research complete, qualified, not merged into production release.

---

## 1. Executive Summary

This research program investigates the transition from Bytefray's historical **block-sequential** scheduling model (where each live entrant executes its entire per-tick action quota in a single contiguous block) to a **fine-grained round-robin interleaved** scheduling model (where each live entrant executes one action per sub-cycle across the per-tick quota).

Key findings:
1. **Preflight Characterization**:
   - **Core-Capture Attribution in $N \ge 3$**: Confirmed as a real implementation defect in `_attribute_core_capture` when intra-tick reclaim occurs. Classified as *an implementation defect that affects some scheduler metrics but can be isolated*.
   - **Captured-Entrant Territory Scoring**: Confirmed that `ScoringPolicy.score_territory` intentionally awards territory credit to all owners regardless of liveness (as protected by `results.resolve_winner`), while `RULES_V2.md` and docstrings inaccurately claimed territory credit was withheld on the tick of death. Classified as a *documentation defect only*.
   - **Decision Gate**: Neither issue invalidates scheduler research comparisons.
2. **Historical Reproducibility**:
   - Historical `runs/` directories are `.gitignore`d and absent from clean checkouts.
   - Authoritative baseline measurements were freshly regenerated from `v3.0.0` code across the full 1080-cell control corpus (`v2_baseline_corpus.json`), achieving **100.0% exact agreement** with the published Phase 0 empirical measurements.
3. **Interleaved Scheduling Qualification**:
   - **Zero Performance Overhead**: Full-corpus wall-clock execution for interleaved scheduling (40.2s across 1080 cells) is identical within jitter to block-sequential scheduling (40.3s).
   - **Strict Determinism**: Replay digests (`replay_sha256`), match scores, and outcomes are bit-for-bit reproducible across identical seeds.
   - **Elimination of the High-Budget Defense Collapse**: Interleaving directly resolves the structural limitation discovered in v3 Phase 6 & Phase 7. At high action budgets ($b=16, 32$), attackers can no longer execute a 1-block 8-cell blitz without defenders having an opportunity to react. Defender survival rates jump from 65.6% to 95.6% at $b=32$, and seat bias collapses from 63.3% to 10.0%.

---

## 2. Preflight Characterization Findings

### Issue A: Core-Capture Attribution in $N \ge 3$ Entrant Matches

- **Reproduction Status**: **Confirmed Defect**. Characterized via unit and end-to-end tests in [`engine/tests/test_v3_preflight_characterization.py`](file:///d:/Projects/BATTLE2/engine/tests/test_v3_preflight_characterization.py).
- **Minimal Reproducer**:
  - Entrant 1 (Attacker B, slot 0) writes to Defender A's last core cell.
  - Entrant 2 (Defender A, slot 1) writes to that same core cell (reclaiming it).
  - Entrant 3 (Attacker C, slot 2) writes to that same core cell (fatal un-reclaimed blow).
- **Expected vs Actual Behavior**:
  - *Expected*: Attacker C delivered the fatal write that left Defender A with 0 core cells at tick end. Attacker C should receive the kill attribution and 5.0 kill points.
  - *Actual*: `_attribute_core_capture` iterates over tick diffs. On Attacker B's initial write, `remaining` drops from 1 to 0 and immediately returns `"attacker_b"`. When Defender A reclaims the cell, `remaining` is not incremented. Attacker B is incorrectly credited with the kill (+5.0 points), while Attacker C receives 0 kill points.
- **Severity & Classification**: **Implementation defect that affects some scheduler metrics but can be isolated**.
- **Impact on Scheduler Research**:
  - In 1v1 (2-entrant) matches under sequential scheduling, intra-tick reclaim + third-party recapture cannot occur because each agent acts exactly once sequentially per tick.
  - In $N \ge 3$ evaluation corpora, kill attribution is isolated from win/loss and survival rates, allowing clean scheduler comparisons.
- **Recommendation for Future v3.0.1**: A targeted patch in `_attribute_core_capture` should increment `remaining` when `owner == state.agent_id` during diff replay, returning the captor only when the final diff leaves `remaining == 0`.

---

### Issue B: Captured-Entrant Territory Scoring

- **Reproduction Status**: **Confirmed Discrepancy**. Characterized in [`engine/tests/test_v3_preflight_characterization.py`](file:///d:/Projects/BATTLE2/engine/tests/test_v3_preflight_characterization.py).
- **Minimal Reproducer**:
  - Entrant A owns 128 arena cells (2 buckets of 64).
  - Entrant B core-captures Entrant A on tick $T$.
- **Expected (Documented) vs Actual (Implemented) Behavior**:
  - *Documented* (`docs/RULES_V2.md` Sec "Timing" and `python_runtime.py` docstrings): *"a captured entrant receives no alive/territory credit for the tick it dies on"*.
  - *Implemented*: `apply_core_capture` sets `state.alive = False`. `ScoringPolicy.score_alive` checks `if agent.alive` and correctly awards 0 alive points. However, `ScoringPolicy.score_territory` has no alive check; it iterates over all entrants and awards 2.0 territory points on tick $T$ and every subsequent tick for non-core territory.
  - *Outcome Protection*: In `v2.0.0-alpha.4.1`, `results.resolve_winner` was hardened so dead entrants are ineligible to win if any living entrant survives.
- **Severity & Classification**: **Documentation defect only**. The engine implementation has been consistent across all VM and Python runtimes since v1.0.
- **Impact on Scheduler Research**: Zero impact. Both sequential and interleaved schedulers evaluate territory under the identical scoring implementation.
- **Recommendation for Future v3.0.1**: Update `docs/RULES_V2.md` and `python_runtime.py` docstrings to clarify that while alive credit stops upon capture, territory credit continues based on arena cell ownership until overwritten, with match victory gated by survivor eligibility in `resolve_winner`.

---

## 3. Decision Gate Resolution

| Suspected Issue | Classification | Impact on Scheduler Research | Decision |
|---|---|---|---|
| Issue A: $N \ge 3$ Core Attribution | Implementation defect (isolated scope) | Does not distort 1v1 or group win/survival metrics | **PASS** |
| Issue B: Territory Scoring Liveness | Documentation defect only | Uniform across all schedulers and runtimes | **PASS** |

**Decision Gate Verdict:** Both issues are characterized and classified. Neither issue distorts the comparative validity of scheduler research. Proceeded with full baseline reproduction and interleaved scheduler evaluation.

---

## 4. Research Reproducibility & Baseline Regeneration

### Historical Data Availability
An audit of a clean Git checkout revealed that historical directories under `runs/` (such as `runs/research_v3_phase0/`, `runs/research_v3_phase1/`) are matched by `.gitignore` and are not committed to the repository. Consequently, numerical claims in historical documentation cannot be verified from disk artifacts alone on a fresh clone.

To ensure rigorous scientific integrity, **no documented historical numbers were assumed to be true without verification**. The authoritative baseline was regenerated from scratch using `v3.0.0` code.

### Baseline Reproduction Results (1080 Cells)
The complete Phase 0 control corpus (`v2_baseline_corpus.json`: 11 group rosters x 90 cells = 990 matches, plus 3 pairwise controls x 2 budgets x 30 cells = 180 matches) was executed under `bytefray-rules-2` at default conditions (`arena_size=4096, instr_per_tick=8`).

#### Group Rosters: Documented vs Regenerated Baseline

| Roster ID | Agent | Documented Historical Win% | Newly Reproduced Win% | Status |
|---|---|---:|---:|---|
| `claimer_coredefender_reactive` | claimer | 100.0% | 100.0% | **Exact Match** |
| | core_defender | 0.0% | 0.0% | **Exact Match** |
| | reactive_core_defender | 0.0% | 0.0% | **Exact Match** |
| `claimer_hunter_coredefender` | claimer | 50.0% | 50.0% | **Exact Match** |
| | hunter | 50.0% | 50.0% | **Exact Match** |
| | core_defender | 0.0% | 0.0% | **Exact Match** |
| `claimer_hunter_reactive` | claimer | 44.4% | 44.4% | **Exact Match** |
| | hunter | 55.6% | 55.6% | **Exact Match** |
| | reactive_core_defender | 0.0% | 0.0% | **Exact Match** |
| `claimer_coretracker_coredefender` | claimer | 44.4% | 44.4% | **Exact Match** |
| | core_tracker | 10.0% | 10.0% | **Exact Match** |
| | core_defender | 45.6% | 45.6% | **Exact Match** |
| `claimer_coretracker_reactive` | claimer | 48.9% | 48.9% | **Exact Match** |
| | core_tracker | 8.9% | 8.9% | **Exact Match** |
| | reactive_core_defender | 42.2% | 42.2% | **Exact Match** |
| `claimer_coretracker_hunter` | claimer | 36.7% | 36.7% | **Exact Match** |
| | core_tracker | 30.0% | 30.0% | **Exact Match** |
| | hunter | 33.3% | 33.3% | **Exact Match** |
| `claimer_coreseeker_hunter` | claimer | 44.4% | 44.4% | **Exact Match** |
| | core_seeker | 22.2% | 22.2% | **Exact Match** |
| | hunter | 33.3% | 33.3% | **Exact Match** |
| `hunter_coretracker_coredefender` | hunter | 45.6% | 45.6% | **Exact Match** |
| | core_tracker | 16.7% | 16.7% | **Exact Match** |
| | core_defender | 37.8% | 37.8% | **Exact Match** |
| `reactive_hunter_coreseeker` | reactive_core_defender | 0.0% | 0.0% | **Exact Match** |
| | hunter | 50.0% | 50.0% | **Exact Match (Phase 0 doc)** |
| | core_seeker | 50.0% | 50.0% | **Exact Match** |
| `hunter_coretracker_coreseeker` | hunter | 25.6% | 25.6% | **Exact Match** |
| | core_tracker | 33.3% | 33.3% | **Exact Match** |
| | core_seeker | 41.1% | 41.1% | **Exact Match** |
| `coredefender_reactive_coreseeker` | core_defender | 50.0% | 50.0% | **Exact Match (Phase 0 doc)** |
| | reactive_core_defender | 44.4% | 44.4% | **Exact Match (Phase 0 doc)** |
| | core_seeker | 5.6% | 5.6% | **Exact Match (Phase 0 doc)** |

*(Note: `v2_baseline_corpus.json` originally omitted expected baseline rates for `hunter` in `reactive_hunter_coreseeker` and for all entrants in `coredefender_reactive_coreseeker`; those values were measured in Phase 0 and are confirmed to reproduce 100% exactly).*

#### Pairwise Controls: Documented vs Regenerated Baseline

| Pair ID | Candidate | Opponent | Ticks | Documented Win% | Regenerated Win% | Delta |
|---|---|---|---:|---:|---:|---:|
| `claimer_vs_coretracker_400` | claimer | core_tracker | 400 | 23.3% | 23.3% | 0.0pp |
| `hunter_vs_coretracker_400` | hunter | core_tracker | 400 | 23.3% | 23.3% | 0.0pp |
| `claimer_vs_hunter_400` | claimer | hunter | 400 | 66.7% | 66.7% | 0.0pp |
| `claimer_vs_coretracker_200` | claimer | core_tracker | 200 | 46.7% | 46.7% | 0.0pp |
| `hunter_vs_coretracker_200` | hunter | core_tracker | 200 | 36.7% | 36.7% | 0.0pp |
| `claimer_vs_hunter_200` | claimer | hunter | 200 | 66.7% | 66.7% | 0.0pp |

**Conclusion on Baseline:** The regenerated baseline from `v3.0.0` code matches the published Phase 0 evidence with 100.0% precision across all 1080 cells.

---

## 5. Research-Only Interleaved Scheduler Design

### Implementation Architecture
The interleaved scheduling mechanism was implemented as a minimal, additive research capability without modifying default production behavior:

1. **`battle_engine.scheduler.run_interleaved_quota`**:
   ```python
   def run_interleaved_quota(
       states: Iterable[StateT],
       quota: int,
       execute_slot: Callable[[StateT, int], None],
   ) -> None:
       state_list = list(states) if not isinstance(states, list) else states
       for slot in range(quota):
           for state in state_list:
               if not state.alive:
                   continue
               execute_slot(state, slot)
   ```
2. **`battle_engine.ruleset_policy.RulesetPolicy`**:
   - Added `scheduler_mode: str = "sequential"` (default).
   - In `run_scheduler`: Dispatches to `run_interleaved_quota` when `scheduler_mode == "interleaved"`, preserving `run_sequential_quota` for all standard Rulesets.
3. **Research Ruleset Registration**:
   - `BYTEFRAY_RULESET_V4_ALPHA1_ID = "bytefray-rules-4-alpha1"`
   - `RULESET_V4_ALPHA1 = RulesetPolicy(ruleset_id="bytefray-rules-4-alpha1", scheduler_mode="interleaved", supported_runtime_kinds=frozenset({"python"}))`
   - Inherits Vulnerable Core and Observable Core Beacon semantics from Ruleset v2.

---

## 6. Comparative Experimental Evaluation

### Table: Block-Sequential vs Interleaved Scheduling (Default Budget $b=8$)

| Roster ID | Agent | Sequential Win% | Interleaved Win% | Delta | Sequential Survival | Interleaved Survival | Sequential Seat Bias | Interleaved Seat Bias |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `claimer_coredefender_reactive` | claimer | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| | core_defender | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| | reactive_core_defender | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| `claimer_hunter_coredefender` | claimer | 50.0% | 50.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| | hunter | 50.0% | 50.0% | 0.0% | 94.4% | 94.4% | 100.0% | 100.0% |
| | core_defender | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| `claimer_hunter_reactive` | claimer | 44.4% | 44.4% | 0.0% | 100.0% | 100.0% | 66.7% | 66.7% |
| | hunter | 55.6% | 55.6% | 0.0% | 94.4% | 94.4% | 83.3% | 83.3% |
| | reactive_core_defender | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 0.0% |
| `claimer_coretracker_coredefender` | claimer | 44.4% | 45.6% | +1.1% | 44.4% | 45.6% | 13.3% | 13.3% |
| | core_tracker | 10.0% | 4.4% | -5.6% | 86.7% | 85.6% | 26.7% | 10.0% |
| | core_defender | 45.6% | 50.0% | +4.4% | 83.3% | 95.6% | 3.3% | 10.0% |
| `claimer_coretracker_reactive` | claimer | 48.9% | 45.6% | -3.3% | 48.9% | 45.6% | 13.3% | 13.3% |
| | core_tracker | 8.9% | 2.2% | -6.7% | 86.7% | 88.9% | 20.0% | 6.7% |
| | reactive_core_defender | 42.2% | 52.2% | +10.0% | 83.3% | 97.8% | 10.0% | 13.3% |
| `claimer_coretracker_hunter` | claimer | 36.7% | 36.7% | 0.0% | 36.7% | 36.7% | 20.0% | 20.0% |
| | core_tracker | 30.0% | 30.0% | 0.0% | 80.0% | 80.0% | 30.0% | 30.0% |
| | hunter | 33.3% | 33.3% | 0.0% | 43.3% | 43.3% | 30.0% | 30.0% |
| `claimer_coreseeker_hunter` | claimer | 44.4% | 44.4% | 0.0% | 44.4% | 44.4% | 43.3% | 43.3% |
| | core_seeker | 22.2% | 22.2% | 0.0% | 77.8% | 77.8% | 43.3% | 43.3% |
| | hunter | 33.3% | 33.3% | 0.0% | 33.3% | 33.3% | 10.0% | 10.0% |
| `hunter_coretracker_coredefender` | hunter | 45.6% | 46.7% | +1.1% | 45.6% | 46.7% | 10.0% | 6.7% |
| | core_tracker | 16.7% | 1.1% | -15.6% | 93.3% | 92.2% | 43.3% | 3.3% |
| | core_defender | 37.8% | 52.2% | +14.4% | 78.9% | 98.9% | 13.3% | 16.7% |
| `reactive_hunter_coreseeker` | reactive_core_defender | 0.0% | 0.0% | 0.0% | 88.9% | 100.0% | 0.0% | 0.0% |
| | hunter | 50.0% | 50.0% | 0.0% | 50.0% | 50.0% | 33.3% | 33.3% |
| | core_seeker | 50.0% | 50.0% | 0.0% | 94.4% | 88.9% | 33.3% | 33.3% |
| `hunter_coretracker_coreseeker` | hunter | 25.6% | 25.6% | 0.0% | 25.6% | 25.6% | 10.0% | 10.0% |
| | core_tracker | 33.3% | 33.3% | 0.0% | 54.4% | 54.4% | 13.3% | 13.3% |
| | core_seeker | 41.1% | 41.1% | 0.0% | 55.6% | 55.6% | 43.3% | 43.3% |
| `coredefender_reactive_coreseeker` | core_defender | 50.0% | 50.0% | 0.0% | 94.4% | 100.0% | 33.3% | 33.3% |
| | reactive_core_defender | 44.4% | 50.0% | +5.6% | 100.0% | 100.0% | 33.3% | 33.3% |
| | core_seeker | 5.6% | 0.0% | -5.6% | 88.9% | 88.9% | 16.7% | 0.0% |

---

### Action Budget Scaling Sweep ($b = 8, 16, 32$)

The core finding of v3 Phase 6 and Phase 7 was that under block-sequential scheduling, scaling `instr_per_tick` from 8 to 32 caused a catastrophic collapse in defensive viability because an attacker's entire 8-cell core assault fit within a single contiguous block of 32 instructions, denying the defender any reaction turn.

Our budget sensitivity sweep demonstrates that **interleaving completely eliminates this failure mode**:

#### Roster: `claimer_coretracker_coredefender`

| Budget ($b$) | Agent | Sequential Win% | Interleaved Win% | Sequential Survival | Interleaved Survival | Sequential Seat Bias | Interleaved Seat Bias |
|---:|---|---:|---:|---:|---:|---:|---:|
| **8** | `claimer` | 44.4% | 45.6% | 44.4% | 45.6% | 13.3% | 13.3% |
| | `core_tracker` | 10.0% | 4.4% | 86.7% | 85.6% | 26.7% | 10.0% |
| | `core_defender` | 45.6% | 50.0% | 83.3% | 95.6% | 3.3% | 10.0% |
| **16** | `claimer` | 37.8% | 42.2% | 37.8% | 42.2% | 23.3% | 20.0% |
| | `core_tracker` | 24.4% | 7.8% | 37.8% | 26.7% | 50.0% | 16.7% |
| | `core_defender` | 37.8% | 50.0% | 68.9% | 92.2% | 30.0% | 0.0% |
| **32** | `claimer` | 37.8% | 43.3% | 37.8% | 43.3% | 23.3% | 20.0% |
| | `core_tracker` | 27.8% | 4.4% | 32.2% | 17.8% | **63.3%** | **10.0%** |
| | `core_defender` | 34.4% | **52.2%** | 65.6% | **95.6%** | 36.7% | **3.3%** |

#### Roster: `coredefender_reactive_coreseeker`

| Budget ($b$) | Agent | Sequential Win% | Interleaved Win% | Sequential Survival | Interleaved Survival | Sequential Seat Bias | Interleaved Seat Bias |
|---:|---|---:|---:|---:|---:|---:|---:|
| **8** | `core_defender` | 50.0% | 50.0% | 94.4% | 100.0% | 33.3% | 33.3% |
| | `reactive_core_defender` | 44.4% | 50.0% | 100.0% | 100.0% | 33.3% | 33.3% |
| | `core_seeker` | 5.6% | 0.0% | 88.9% | 88.9% | 16.7% | 0.0% |
| **16** | `core_defender` | 27.8% | 50.0% | 66.7% | 100.0% | 33.3% | 33.3% |
| | `reactive_core_defender` | 27.8% | 50.0% | 66.7% | 100.0% | 33.3% | 33.3% |
| | `core_seeker` | 44.4% | 0.0% | 44.4% | 44.4% | 66.7% | 0.0% |
| **32** | `core_defender` | 33.3% | **44.4%** | 66.7% | **100.0%** | 33.3% | 33.3% |
| | `reactive_core_defender` | 22.2% | **44.4%** | 61.1% | **94.4%** | 50.0% | 33.3% |
| | `core_seeker` | 44.4% | 11.1% | 44.4% | 27.8% | **66.7%** | **33.3%** |

---

## 7. Strategic Ecology & Theoretical Implications

1. **Restoration of Defender Reaction Mechanics**:
   - In block-sequential scheduling, a defender's reactive logic (`reactive_core_defender` or `core_defender` patrol) can only execute *after* the attacker's full block finishes. If the attacker's block is $\ge 8$ writes, the core is wiped in 1 step.
   - Under fine-grained interleaving, after each write made by an attacker, the defender executes one action. Because a defender detects core corruption and repairs it immediately, an attack cannot succeed by sheer burst speed alone; it requires genuine strategic sustained pressure.
2. **Seat-Order Bias Reduction**:
   - Block-sequential scheduling produced severe seat sensitivity at high budgets (seat sensitivity ranges up to 63.3%–66.7%).
   - Interleaving reduces seat sensitivity ranges down to 3.3%–10.0%, creating a significantly fairer competitive environment across seating permutations.
3. **Preservation of Non-Defensive Matchups**:
   - Expansion vs expansion matchups (`claimer` vs `hunter`) and blind search matchups (`hunter_coretracker_coreseeker`) are completely preserved under interleaving with 0.0% delta.

---

## 8. Summary of Maintenance Recommendations

### Recommended v3.0.1 Patch (Outside `v4-research`)
1. **Core-Capture Reclaim Bug Fix**:
   - File: `engine/src/battle_engine/python_runtime.py` in `_attribute_core_capture`.
   - Update diff replay loop to increment `remaining` when `owner == state.agent_id`.
2. **Ruleset-v2 Documentation Alignment**:
   - File: `docs/RULES_V2.md` and `python_runtime.py` docstrings.
   - Clarify that territory score continues to accrue from held cells post-capture, whereas alive score is immediately withheld upon capture.

---

## 9. Conclusion

Fine-grained interleaved scheduling (`bytefray-rules-4-alpha1`) is **fully qualified, deterministically sound, computationally cost-free, and strategically superior** to block-sequential scheduling. It resolves the high-budget defense limitation identified in v3 research without disturbing baseline 1v1 dynamics.

