# Bytefray v4 Phase 5 — Alpha2 Productization and Release Qualification

Product branch: `v4-alpha2-development` (off `main`@`855f7379e1309ec60760d960fff54e7da9648e59`)
Research input: [V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md](V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md)
Contract produced: [V4_ALPHA2_DESIGN.md](V4_ALPHA2_DESIGN.md)

---

## A. Starting state

| | |
|---|---|
| `main` | `855f7379e1309ec60760d960fff54e7da9648e59` |
| `origin/main` | `855f7379e1309ec60760d960fff54e7da9648e59` (synchronized) |
| Phase 4 branch | `v4-alpha2-gameplay-research` @ `c0c04bfaa737d648c94bca05247ab95cec4b0f34`, **unchanged**, not merged |
| Phase 4 unique commits | `b57f265`, `bcc16ea`, `d390c9f`, `c0c04bf` |
| Phase 5 branch | `v4-alpha2-development`, created from `main` |
| Unrelated local state | `release_notes.txt` (untracked, untouched) |
| Known environment issue | `.pytest-cache-v141/` permission denial, unchanged |

The Phase 4 research corpus at
`D:\Projects\Bytefray-research\v4-alpha2-phase4-20260831-214252\` was verified
read-only against its own `SHA256_MANIFEST.txt`: **60 of 60 files OK, 0
failures.** It was not modified or regenerated.

---

## B. Research-change disposition

Every file changed by the four Phase 4 commits, classified and resolved.

| Phase 4 change | Class | Disposition | Reason |
|---|---|---|---|
| `match_service.py` — five `MatchRequest` override fields | **D** | **Removed** (never ported) | Research-only knobs; see the field table below |
| `match_service.py` — `declared_reach` + `telemetry` in `NativeAgentResult.metadata` | **D** | **Removed** | Not replay-invisible: this metadata reaches the schema-4 replay header, so every alpha1 replay recorded on the research branch differs from one recorded on `main` for identical inputs. Keeping it would have broken the alpha1 byte-identity firewall |
| `process_runtime.py` — `core_size` / `reach_cap` / `process_spread_radius` / `process_order_overrides` constructor params | **D** | **Removed** | Same as the request fields they thread from |
| `process_runtime.py` — `_process_spread_offset` | **D** | **Removed** | Phase 4 §F1 measured the effect as too small to adopt; nothing in alpha2 uses it |
| `process_runtime.py` — round-robin selection branch | **A** | **Reimplemented** | Product behaviour required for alpha2, but re-expressed as a Ruleset policy field and extracted into a documented `_select_active_process`, not carried over as an inline `if mode == ...` |
| `python_runtime.py` — `core_size` params on `core_addresses` / `apply_core_capture` | **D** | **Removed** | Alpha2 keeps core size 8; the parameter existed only for the rejected core-size experiment |
| `test_v4_alpha2_research_seams.py` | **D** | **Removed** | Tests for surfaces that no longer exist. Replaced by three alpha2 modules testing the shipped semantics |
| `tools/v4_alpha2_gameplay_study.py` | **C** | **Left on the research branch** | Its conditions are the removed `MatchRequest` fields; porting it would have re-imported them. Phase 5 has its own harness (§G) |
| `tools/v4_alpha2_research_agents/disperser/` | **E** | **Not carried forward** | Phase 4 answered its question (dispersion does not defend against an overwrite race, 0 wins in 2,560 matches). No remaining role |
| `tools/v4_alpha2_research_agents/local_hunter/` | **E** | **Ported, research-only** | Retained as the minimal agent that reproduces the disruption-lock situation on demand. Behaviour byte-identical; kept out of `agents/` |
| `docs/V4_ALPHA2_PHASE4_GAMEPLAY_STUDY.md` | **C** | **Cherry-picked** (`-x`) | The evidence base the alpha2 contract cites. A provenance note was added at its head; no finding, number, or claim altered |

### The five research `MatchRequest` fields

| Field | Purpose | Production module touched | Reachable from a product path? | Changes deterministic identity? | Alpha2 needs it? | Class | Decision |
|---|---|---|---|---|---|---|---|
| `core_size` | Core-width experiment | `match_service`, `process_runtime`, `python_runtime` | No — no CLI parser, GUI, evaluation, or tournament path set it | Yes when set (different core geometry) | No — alpha2 keeps 8 | **D** | **REMOVE** |
| `reach_cap` | Reach-cap experiment | `match_service`, `process_runtime` | No | Yes when set | No — alpha2 keeps uncapped reach | **D** | **REMOVE** |
| `process_spread_radius` | Initial-deployment spread | `match_service`, `process_runtime` | No | Yes when set | No — §F1 found the effect too small | **D** | **REMOVE** |
| `process_order_overrides` | Declaration-order permutation | `match_service`, `process_runtime` | No | Yes when set | No — round-robin removes the lever the field was built to measure | **D** | **REMOVE** |
| `process_selection_mode` | Round-robin prototype | `match_service`, `process_runtime` | No | Yes when set | The *semantic* is needed; the *field* is not | **A** (semantic) / **D** (field) | **REMOVE the field**, promote the semantic to `RulesetPolicy.process_selection` |

None was retained, including as a private test seam. Alpha2's semantics are
stated by the Ruleset, so a test that wants alpha2 behaviour selects the
alpha2 policy — which is also what a user does. A hidden per-match switch
would have been a second, untested way to reach the same behaviour.

**Verified**: `MatchRequest`'s field list on this branch is identical to
`main`'s. No new public constructor parameter exists.

---

## C. The Alpha2 Ruleset

| Axis | Alpha1 | Alpha2 | Differs? |
|---|---|---|---|
| Ruleset ID | `bytefray-rules-4-alpha1` | `bytefray-rules-4-alpha2` | **yes** |
| Agent API | v2 | v2 | no |
| Replay schema | 4 | 4 | no |
| Result schema | current | current | no |
| Runtime kinds | Python only | Python only | no |
| `Q` | 8 | 8 | no |
| Core size | 8 | 8 | no |
| Reach legality | `[1, arena-1]`, uncapped, free | same | no |
| **Core placement** | evenly-spread seats from address 0 | **seed-derived, min 64-cell separation** | **yes** |
| **Process selection** | declared-list priority scan | **round-robin** | **yes** |
| Entrant scheduling | `K=2` chunked, rotating start | same | no |
| Disruption | trigger, `D=1`, co-location blast, auto-expiry | same | no |
| Quota allocation / redistribution | largest remainder, stable-ID ties | same | no |
| Visibility contract | current-only local detection | same | no |
| Initial process co-location | yes | yes | no |

---

## D. Placement implementation

* **Algorithm** — seat-ordered rejection sampling. Seat *i* draws candidates
  until one is at least `separation` cells (circular) from every already
  placed seat.
* **Seed derivation** — SHA-256 counter stream over
  `"bytefray-rules-4-alpha2:placement:{seed}:{arena}:{count}:{sep}:{seat}:{attempt}"`,
  first 8 bytes big-endian modulo the arena. Deliberately not `random`: only
  `random.random()`'s sequence is documented stable across Python versions,
  and cross-version determinism is a release requirement here.
* **Minimum separation** — 64 cells, exactly the Phase 4 condition's value,
  clamped to `arena_size // entrant_count` when the arena cannot fit it. The
  clamp only loosens.
* **Collision handling** — bounded to 64 draws per seat; on exhaustion the
  **whole layout** falls back to the alpha1 spread layout, keeping the result
  internally consistent and the function total.
* **Multi-entrant** — defined for any seat count by the same seat-ordered
  sampling. Verified for 2, 3, 4, and 8 seats across three arena sizes and 64
  seeds: all in bounds, all distinct, all at or above the effective
  separation.
* **Where it resolves** — `placement.resolve_direct_match_starts`, so resolved
  starts enter `MatchRequest` → `canonical_match_id` → artifacts. Explicit
  starts are still honoured unchanged.

**Deterministic vectors** (pinned in `engine/tests/test_v4_alpha2_placement.py`,
release-blocking cross-platform contract):

| seats, arena, seed | starts |
|---|---|
| 2, 256, 0 | (82, 219) |
| 2, 256, 1 | (24, 162) |
| 2, 512, 0 | (209, 63) |
| 2, 512, 1 | (380, 263) |
| 2, 512, 7 | (324, 167) |
| 2, 1024, 0 | (238, 503) |
| 2, 1024, 42 | (721, 912) |
| 3, 256, 0 | (135, 54, 200) |
| 3, 512, 3 | (406, 134, 52) |
| 4, 1024, 5 | (127, 790, 983, 725) |
| 8, 1024, 9 | (336, 266, 686, 962, 854, 166, 53, 599) |

**Windows/Linux equivalence** — all eleven vectors reproduce exactly on
Ubuntu (WSL2, Python 3.12.3) and Windows (Python 3.11.9). Placement is also
invariant under `PYTHONHASHSEED` (asserted in-suite by spawning child
interpreters with three different values).

**Ecology-scale check** — across the 10,560-match alpha2 corpus the minimum
observed separation is exactly **64** and the maximum **507**; 96 distinct
start pairs for 96 distinct (seed, arena) combinations.

---

## E. Scheduler implementation

`ProcessMatchController._select_active_process`, selected by
`RulesetPolicy.process_selection`.

* **Round-robin semantics** — scan from a per-entrant cursor; select the first
  eligible process still under its effective allocation.
* **Cursor** — 0 at construction; advanced to `(selected + 1) % count` **only**
  on a successful selection, so a slot that selects nothing never costs a
  process its turn. **Match-scoped: it does not reset at a tick boundary**, so
  rotation continues across ticks and no process gets a systematic first-slot
  advantage from being declared first.
* **Disruption** — a disrupted process is absent from the allocation, so it is
  passed over without consuming a turn and rejoins at its own list position.
* **Redistribution** — entirely upstream and unchanged; selection only hands
  the resulting larger allocations out in rotation.
* **Declaration-order sensitivity** — under alpha2, permuting a three-process
  declaration list leaves every process's slot count unchanged, including
  across a mid-tick disruption; only the rotation phase moves. Under alpha1
  the same scenario gives the earliest-declared process every freed slot and
  a still-eligible sibling **zero** actions despite never exhausting its own
  share.

The ecology corroborates this at scale: **seat delta collapses** under
alpha2 (Nemesis +10.0% → +0.3%, `nemesis_alpha2` +11.7% → −0.1%, Local
Hunter +6.7% → +0.9%).

---

## F. Historical Alpha1 integrity

The strongest available evidence, run **after** every Phase 5 change:

> An alpha1 CLI match (`v4_claimer` vs `v4_scout`, arena 256, seed 42, starts
> 0/128, 1000 ticks) produces a **byte-identical `replay.jsonl`** *and*
> **byte-identical `result.json`** to the same match run in a clean git
> worktree at `main@855f7379`.
>
> * `replay.jsonl` SHA-256 `0dcb7426aed4cc12528a7972d940061a21058e64e91ea6a7fe51d0e0a9cd58dc`
> * `result.json` SHA-256 `ba9801f5a5b2232d8767e66952027b32fae5cc195150eab755ff5d418a3b8f7c`

In-suite firewall coverage:

* every pre-alpha2 Ruleset keeps its exact historical placement, including
  when the new `seed` argument it ignores is supplied;
* alpha1's per-tick process call order is pinned literally;
* running an alpha2 match first leaves a subsequent alpha1 match
  byte-identical, proving no shared mutable state leaks between them;
* alpha1's `RulesetPolicy` spells out `core_placement="seat_spread"` and
  `process_selection="priority"` explicitly, and a test asserts every other
  policy axis is identical between the two alphas.

**No Alpha1 fixture, golden, or deterministic vector was altered or
re-blessed.** The tests that were updated are default-Ruleset-selection and
Designer-offering expectations — behaviour Phase 5 deliberately changes — and
each is listed in its commit message.

---

## G. Product integration

| Surface | Behaviour | Verified |
|---|---|---|
| `bytefray run` | alpha2 in `--ruleset` choices; omitted + API v2 → alpha2; seeded placement for omitted starts | end-to-end, replay anchors (495, 387) for arena 512 seed 3 |
| `agents test` | alpha2 in choices; omitted + API v2 → alpha2; API-v2 reference opponent now selected for **any** process Ruleset, not only alpha1 | ran under omitted, explicit alpha1, explicit alpha2 |
| `tournament` | alpha2 in choices; omitted + API v2 → alpha2; **each pairing re-placed from its own derived match seed** | 3-agent tournament: three pairings, three different layouts, all separations ≥ 64; re-run recognised all three as completed, so resume-path `canonical_match_id` matches |
| Agent Designer — Simple | current gameplay only: v2 + alpha2 | GUI suite |
| Agent Designer — Advanced / Development | both v4 alphas, alpha2 preferred, alpha1 retained | GUI suite |
| Agent Designer — Evaluation | alpha1 only among the v4 alphas | GUI suite |
| `agents evaluate` | **rejects alpha2**, fail-closed at the argparse layer | `invalid choice: 'bytefray-rules-4-alpha2'` |
| `NativeMatchService` | alpha2 dispatches to the process runtime; overlap guard extended to alpha2 | integration suite |

The Designer evaluation exclusion is a defect this phase found and fixed:
adding alpha2 to the shared designer option list had put it in the Evaluation
dialog, where selecting it would have produced an engine rejection.

**Deliberate decision on evaluation.** `agents evaluate` does not accept
alpha2. Its placement conditions are an explicit, disclosed methodology axis;
running them under alpha2 would produce artifacts labelled alpha2 that
actually ran alpha1's fixed opposite placement — the exact distortion alpha2
removes. Adopting alpha2 there needs a methodology decision this Ruleset
change does not supply.

---

## H. Alpha2-adapted agents

| | `hydra_alpha2` | `nemesis_alpha2` |
|---|---|---|
| Purpose | Can an agent that acquires its target through the observation contract still play Hydra's game under alpha2? | Same question for Nemesis, whose siege spends half the entrant quota |
| Canonical ID | `hydra_alpha2` v1.0.0 | `nemesis_alpha2` v1.0.0 |
| `agent.py` SHA-256 | `329111f6aea21971e064fe16cd4febe2abba15a1b400187b307d01fd41d32644` | `b4c03cd41c6c9fddc7f71e444089b8ef208b6b1b1d8cf2c6cdb60fe04dd49cc8` |
| Differs from historical | Target acquisition only. Roles, shares, reach, and offset cycles are carried over unchanged | Same |
| Public API v2 only? | Yes — `visible_enemy_anchor_addresses`, `READ` + `previous_read_owner`, `MatchContextV2.arena_size`. No engine internals, research seams, match metadata, or replay access | Yes |

The historical `hydra` and `Nemesis` are **unchanged** (`git status` clean for
both), and their alpha2 results were recorded before any adaptation existed.

`local_hunter` is retained as a research probe at
`tools/v4_alpha2_ecology_agents/`, behaviour byte-identical to Phase 4's copy
(only its docstring gained a Phase 5 preamble). Disperser is not carried
forward: Phase 4 answered its question.

---

## I. Ecology results

**Study**: 21,120 matches. 11 agents, 55 pairs, arenas 256/512/1024, seeds
0–31, both seat orientations, 1000-tick budget — an identical matrix under
each Ruleset, so every difference below is the Ruleset.

Corpus: `D:\Projects\Bytefray-research\v4-alpha2-phase5-20260901-073044\`,
46-file SHA-256 manifest, all verifying.

### Headline (Phase 5L)

| Metric | Alpha1 | Alpha2 |
|---|---:|---:|
| Matches | 10,560 | 10,560 |
| Median match ticks | 198.0 | 1000.0 |
| Mean match ticks | 486.9 | 736.5 |
| Tick-limit rate | 46.3% | 70.7% |
| Draw rate | 26.2% | 49.9% |
| Contact rate | 100.0% | 99.6% |
| Mutual-contact rate | 20.9% | 21.1% |

### Win rates (n = 1,920 per agent)

| Agent | Alpha1 | Alpha2 | Δ |
|---|---:|---:|---:|
| Nemesis (historical) | 95.0% | 15.2% | **−79.8** |
| hydra (historical) | 83.9% | 17.4% | **−66.5** |
| `nemesis_alpha2` | 75.8% | 74.3% | −1.5 |
| `hydra_alpha2` | 63.0% | 69.0% | **+6.0** |
| viper | 18.3% | 34.6% | +16.3 |
| v4_claimer | 30.0% | 18.3% | −11.7 |
| v4_scout | 16.7% | 13.3% | −3.4 |
| local_hunter | 13.3% | 13.7% | +0.4 |
| v4_concentrated_attacker | 10.0% | 9.8% | −0.2 |
| v4_defender_scout | 0.0% | 10.0% | **+10.0** |
| v4_local_defender | 0.0% | 0.0% | 0.0 |

### The decisiveness question, decomposed

The aggregate draw rate doubles. Decomposing it by matchup class shows why,
and the answer inverts the naive reading:

| Matchup class | n | Alpha1 draw | Alpha2 draw | Alpha1 median ticks | Alpha2 median ticks |
|---|---:|---:|---:|---:|---:|
| **adapted vs adapted** | 192 | 41.7% | **0.0%** | 545 | **6** |
| ≥ 1 adapted agent | 3,648 | 9.5% | 23.7% | 8 | 14 |
| historical roster only | 6,912 | 35.0% | **63.7%** | 1000 | 1000 |
| short-reach agents only | 2,880 | 60.0% | 62.0% | 1000 | 1000 |

* **Every one of the 192 adapted-vs-adapted matches resolved under alpha2**
  (0% draws, 0% tick limit, median 6 ticks). The same pairing drew 41.7% of
  the time under alpha1.
* The rise in aggregate draws comes **entirely from the historical roster**,
  whose agents cannot find an opponent they can no longer compute.
* Short-reach-only matchups draw ~60% under **both** Rulesets: an unchanged,
  pre-existing v4 property, not something alpha2 introduced.

### Search and contact

* `hydra_alpha2` wins **more by real elimination** under alpha2 (1,064
  `last_agent_standing` wins) than under alpha1 (864) — its search-based
  targeting is more effective against unpredictable placement than its
  formula-free self was against opponents who could still exploit placement.
* Historical `hydra`'s kills collapse 1,547 → 188; historical `Nemesis`'s
  1,824 → 145.
* Mutual contact is unchanged (20.9% → 21.1%). Among short-reach-only
  matchups it is 3.4% (median tick 7 when achieved) — an honest limitation
  recorded in §K.
* Movement rises for historical `hydra` (18.7 → 37.4 mean MOVEs; unique
  anchors 19.7 → 37.9) because its rover keeps searching when its siege has
  nothing valid to hit.

### Seat effect

Seat advantage largely disappears: Nemesis +10.0% → +0.3%, `nemesis_alpha2`
+11.7% → −0.1%, hydra +8.6% → +3.6%, Local Hunter +6.7% → +0.9%. The single
exception is `hydra_alpha2` (+6.0% → +8.0%).

---

## J. Disruption-lock assessment

**Classification: a meaningful archetype weakness — not release-blocking, and
not introduced or worsened by alpha2.**

An entrant counts as *locked* when it was fully disrupted for an unbroken half
of a match of at least 50 ticks.

| | Alpha1 | Alpha2 |
|---|---:|---:|
| Assessable matches (≥ 50 ticks) | 5,541 | 8,279 |
| Matches with a locked entrant | 2,880 | 4,261 |
| **Rate** | **52.0%** | **51.5%** |

The rate is **flat**. The absolute count rises only because alpha2 produces
more matches long enough to assess at all.

Who is locked, and what happens to them:

| Agent | Alpha1 locked | Alpha2 locked | Alpha2 outcome when locked |
|---|---:|---:|---|
| v4_claimer | 45.0% | 51.0% | 979 lost, 0 drew |
| v4_local_defender | 40.0% | 46.9% | 0 lost, **900 drew** |
| v4_concentrated_attacker | 35.0% | 37.1% | 228 lost, 485 drew |
| v4_scout | 15.0% | 22.2% | 55 lost, 371 drew |
| local_hunter | 15.0% | 21.4% | 41 lost, 369 drew |
| `nemesis_alpha2` | 0.0% | 4.5% | 0 lost, 65 drew, 22 won |
| `hydra_alpha2` | 0.0% | 1.2% | 0 lost, 22 drew, 1 won |

The phenomenon concentrates on **single-process, low-reach, passive
archetypes** — exactly the class Phase 4 predicted — and mostly produces
**draws**, i.e. the stalemate Phase 4 described, not elimination. Agents that
actually play alpha2 are barely affected (1.2% and 4.5%), and when locked
still sometimes win.

This does not meet the bar for stopping the candidate, and per the governing
instruction no disruption immunity, cooldown, or resource mechanic was added.

---

## K. Honest limitations of the alpha2 candidate

Recorded because they are real and should shape the next phase, not because
they block this one.

1. **Reach buys information for free.** `visible_enemy_anchor_addresses`
   reports every enemy anchor within *any* friendly process's reach, so an
   agent declaring `arena_size // 2` reach detects the whole arena at tick 0
   at zero cost — which is why the aggregate median first-contact tick is 0
   under both Rulesets. Seeded placement therefore does not force search on a
   global-reach agent; it forces search on agents that *chose* to be local.
   Alpha2 converts a placement exploit into a reach-vs-information trade-off
   rather than eliminating free information. This is the most likely subject
   of a future phase.
2. **Short-reach agents mostly never meet.** Among matchups where both sides
   are short-reach, mutual contact occurs in 3.4% of matches. This is
   essentially unchanged from alpha1 (those matchups draw ~60% under both),
   so alpha2 neither causes nor fixes it.
3. **The historical roster is not competitive under alpha2**, by design. Any
   ecology summary that pools historical and adapted agents will understate
   alpha2's decisiveness; §I decomposes rather than pools for this reason.

---

## L. Qualification

| Check | Command | Result |
|---|---|---|
| Focused alpha2 placement | `pytest engine/tests/test_v4_alpha2_placement.py` | 67 passed |
| Focused alpha2 scheduler | `pytest engine/tests/test_v4_alpha2_scheduler.py` | 18 passed |
| Focused alpha2 integration | `pytest engine/tests/test_v4_alpha2_integration.py` | 8 passed |
| Ruleset policy | `pytest engine/tests/test_ruleset_policy.py` | 49 passed |
| Windows headless suite | `python -m pytest` | **2623 passed, 14 skipped, 2 deselected** in 290s |
| Designer GUI suite | `pytest -q -m gui tests/` | 242 passed, 6 deselected |
| Ruff | `ruff check .` | All checks passed |
| Engine mypy | `mypy engine/src/battle_engine` | Success, 95 files |
| Client mypy | `mypy client/src/battle_client` | Success, 12 files |
| Whitespace | `git diff --check` | clean |
| Linux full suite | `pytest` on Ubuntu (WSL2, Python 3.12.3) | **2620 passed, 17 skipped, 2 deselected** |
| Cross-platform vectors | 11 placement vectors | identical on both platforms |
| Cross-platform matches | 6 matches (2 alpha1, 4 alpha2) | identical placement, `match_id`, `result_id`, outcome, and replay bytes after newline normalisation |

Windows and Linux collect the same 2,639 tests; the 2623/14 vs 2620/17
split is the platform-conditional skips (Windows packaging tests skip on
Linux and vice versa).

**Linux environment note.** Two `test_v4_production_integration.py` tests fail
on Linux unless `PYTHONPATH` is exported, because supervised worker
*subprocesses* cannot inherit pytest's rootdir insertion in a venv that has
not installed the package. Both failures reproduce identically on a clean
worktree at `main@855f7379`, so they are environmental, not a Phase 5 defect.
With `PYTHONPATH` exported the full suite passes.

### Cross-platform match identity

| Ruleset | arena | seed | starts | `match_id` | replay (LF-normalised) |
|---|---:|---:|---|---|---|
| alpha1 | 256 | 1 | (0, 128) | `match_f57f997aa7…` | `b1f922698f07e2ba…` |
| alpha1 | 512 | 42 | (0, 256) | `match_4dde801930…` | `29c172bcc08b1fb8…` |
| alpha2 | 256 | 1 | (24, 162) | `match_ac970afc91…` | `4a409340d9c7a757…` |
| alpha2 | 512 | 42 | (485, 203) | `match_7fc8ce4076…` | `d40c9a908b167df0…` |
| alpha2 | 1024 | 7 | (649, 103) | `match_4887832c13…` | `eafd0bdee128a878…` |
| alpha2 | 512 | 12345 | (510, 255) | `match_bbdb879b94…` | `b4e17f2f1490e39c…` |

Raw replay bytes differ between platforms only by line endings — Windows text
mode writes CRLF — which is a pre-existing property affecting every Ruleset
equally, not an alpha2 behaviour.

### Determinism at ecology scale

The alpha2 condition was executed twice for 1,180 of its cells: once by the
original single worker and again by the seed-partitioned shards. The merge
compared all 1,180 duplicates on winner, ticks, and termination reason and
found **0 conflicts**.

### Performance (Phase 5S)

| Measure | Alpha1 | Alpha2 |
|---|---:|---:|
| Match, identical starts, arena 512, 1000 ticks (median of 12) | 721.4 ms | 603.4 ms |
| Placement, per layout | 0.69 µs | 7.52 µs |

Seeded placement costs 6.8 µs more per layout — 0.0009% of one match. The
match-throughput row is not a like-for-like comparison (round-robin changes
the match, so the two are not doing identical work), but it rules out a
regression: alpha2 is not slower. No optimisation was undertaken.

---

## M. Git state

```text
Phase 5 branch      v4-alpha2-development (12 commits off main@855f7379)
Working tree        clean apart from the pre-existing untracked release_notes.txt
Research branch     v4-alpha2-gameplay-research @ c0c04bf — UNCHANGED
main / origin/main  855f7379 — UNCHANGED
Pushed              nothing (no remote contains HEAD)
Merged              nothing
Tagged              nothing
```

No Phase 4 raw dataset or probe artifact is in the product tree. The only
reference to a research path anywhere in the repository is the Phase 4
report citing its own corpus location.

---

## N. Release decision

Against the fifteen qualification criteria:

1. Alpha1 historical behaviour intact — byte-identical replay **and** result vs `main`. ✅
2. Alpha2 placement deterministic and cross-platform stable — 11 pinned vectors, both platforms, hash-seed independent. ✅
3. Alpha2 removes closed-form opponent-core knowledge — the formula is wrong for at least 63 of 64 seeds with varying miss distance; historical Nemesis falls 95.0% → 15.2%. ✅
4. Scheduler removes declaration-order sensitivity — permutation-invariant slot counts; seat delta collapses across the roster. ✅
5. API-v2 agents remain compatible — every roster agent loaded and ran under both Rulesets. ✅
6. Replay schema 4 sufficient — both Rulesets record schema 4; placement is reproducible from recorded inputs alone. ✅
7. Adapted agents demonstrate viable search/contact gameplay — `hydra_alpha2` 69.0%, 1,064 wins by elimination, more than its own alpha1 figure. ✅
8. No newly dominant pathological strategy — the top two are adapted agents at 74.3% / 69.0%, far below alpha1's 95.0% / 83.9%, and they beat each other decisively (0% draws, median 6 ticks). ✅
9. Disruption lock not release-blocking — rate flat at 52.0% → 51.5%, concentrated on passive single-process archetypes, mostly producing draws. ✅
10. Full Windows qualification passes. ✅
11. Linux qualification passes — 2620 passed, 17 skipped. ✅
12. Static checks pass — ruff, both mypy invocations, `git diff --check`. ✅
13. Documentation complete — contract, compatibility boundary, README, CHANGELOG, AGENTS.md, this report. ✅
14. Research-only production knobs explicitly resolved — all five removed; `MatchRequest` identical to `main`. ✅
15. No Phase 4 dataset or probe artifact leaked into the product. ✅

```text
QUALIFIED FOR v4.0.0-alpha2
```

Not published, tagged, merged, or pushed.
