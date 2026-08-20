# Bytefray v2.0.0-alpha.11 — Ruleset-v2 Candidate Resolution

Not another exploratory alpha. Alpha.1–alpha.10 completed the planned
research sequence and handed forward exactly one unresolved gameplay
problem (`docs/V2_0_ALPHA10_STRATEGIC_ECOLOGY.md` §29/§38/§39):

> Blind territorial expansion remains close to a universal solution even
> though offense, defense, vulnerable-core mortality, multi-entrant play,
> placement variation, and reconnaissance all work individually.

This alpha exists to resolve that, or to say clearly that it cannot be
resolved with the mechanics available. It has three gates: **Resolution A**
(consistent core observability), **Resolution B** (deterministic territory
maintenance — a contingency that only runs if A is sound but insufficient),
and **Resolution C** (Ruleset-v2 candidate synthesis and a beta GO/NO-GO).

**Outcome: Resolution A returned A-PASS. Resolution B was therefore not
entered — no territory-maintenance or decay mechanic was designed,
implemented, parameterised, or executed anywhere in this alpha. Resolution
C returns GO for the separate v2 beta-planning phase.**

Branched from the verified alpha.10 baseline, commit `37f9bc6` on
`v2.0-development` (`main` unchanged at
`5593d287f95a24996bb3b105befbc625a00795db` throughout).

---

## 1. Verified starting state (Phase 0)

- Branch `v2.0-development`; HEAD at start `37f9bc6` ("docs(v2.0-alpha):
  validate strategic ecology (alpha.10)"); working tree clean; `main` at
  `5593d287…`, unchanged.
- `origin/v2.0-development` still points at the unrelated commit `151866c`
  (local ahead 10 / behind 1). Not merged, rebased, cherry-picked, reset, or
  otherwise reconciled anywhere in this alpha, and nothing was pushed.
- Regression baseline measured directly on this machine before any alpha.11
  file existed: full `pytest` → **1556 passed, 6 skipped, 2 deselected, 0
  failed** (1562 selected). `ruff check engine client`: clean. `mypy
  engine/src/battle_engine`: clean, **70** source files. `mypy
  client/src/battle_client`: clean, **10** source files. Identical to
  alpha.9's and alpha.10's own freshly-measured figures — no drift.
- One measurement note, recorded because it cost a re-run: `pytest.ini`
  already sets `-q` in `addopts`, so invoking `python -m pytest -q` yields
  `-qq` and **suppresses the final summary line entirely**. The plain
  `python -m pytest` invocation AGENTS.md documents is the one that reports
  counts. A stale `.pytest-tmp/` also produced the `FileExistsError` class of
  failure `docs/WINDOWS_DEV_NOTES.md` already characterises; clearing it
  resolved it, and `pytest.ini`'s repo-local cache/temp paths were not
  touched.
- Read in full before any design work: `docs/V2_0_ALPHA_ARCHITECTURE.md`,
  `docs/V2_0_ALPHA10_STRATEGIC_ECOLOGY.md`, `docs/RULES.md`,
  `docs/COMPATIBILITY.md`, `docs/AGENT_API_V1.md`, plus the alpha.1–alpha.9
  findings as summarised by the governing task. Read directly from source,
  not inferred: `python_runtime.py`'s `seed_core_ownership`/
  `apply_core_capture`/`_attribute_core_capture`/`_snapshot_core_owners`,
  `ruleset_policy.py`, `rules.py`, `vm.py`'s `_wr8`, `match_service.py`'s
  `MatchRequest`/`_resolve_ruleset_id`/`canonical_match_id`, and all of
  `core_tracker`, `core_defender`, `reactive_core_defender`, `claimer`.

## 2. Phase A1 — the information problem, stated exactly

What an ordinary Agent API v1 entrant can know today, verified against
source rather than documentation:

| Information | Available? | Mechanism |
|---|---|---|
| Arena **byte contents** | yes, one byte at a time | `READ` → `Observation.last_read` on the *next* `act()` |
| Arena **ownership** (`vm.writer`) | **no** | engine-internal; `Observation` has no ownership field |
| **Own** identity / **own** core anchor | yes | `Observation.agent_id`; first `act()`'s `observation.pc` *is* `entrant.start` |
| **Opponent** identity, position, core coordinates | **no** | nothing in `Observation`/`MatchContext` names another entrant |
| Score, territory counts, `tick_diffs`, `ownership_counts` | **no** | engine-internal |
| Public Ruleset knowledge (`CORE_SIZE == 8`, arena wrap, scoring shape) | yes | published; all three core-aware reference agents already hardcode `8` on this basis |

**The defect.** Under `bytefray-rules-2-alpha1`, `seed_core_ownership`
establishes a core's initial ownership by writing the byte value **`0`** —
byte-for-byte identical to untouched arena (`docs/RULES.md`: "The arena
starts filled with byte `0`"). Ownership is unreadable, so *content* is the
only channel through which a core can be observed at all. Verified against
`core_tracker/agent.py`'s `_looks_foreign` (`value is not None and value != 0
and value != self.signature`):

* an entrant that never writes into its own core is **literally invisible**
  to every non-privileged searcher, permanently;
* an entrant that **defends** its core becomes detectable *precisely
  because it defended*.

That is alpha.10 §37's falsified-H2 mechanism restated as a rules defect,
and it is the wrong incentive in the most direct possible sense: blind
expansion bought invisibility for free, and vigilance was informationally
self-punishing. Alpha.10 measured the consequence directly — 0% capture rate
against `claimer`/`hunter`, 12–28% against the two defenders.

**Design goal, binding:** make a core's existence and location *inferable
through ordinary arena interaction*. Hand no attacker privileged
coordinates, ownership access, opponent identity, or any new `Observation`
field. Core Tracker must gain **no** privileged information; discovery must
still cost `READ` actions.

## 3. Phase A2 — four designs evaluated (pre-registered)

Written to
`runs/v2_0_alpha11_ruleset_candidate_resolution/resolution_a/design_options.md`
**before** any implementation, test, or match, and not rewritten afterwards.

**Option A — initial core beacon.** Seed core cells with a deterministic
public non-zero byte instead of `0`. Smallest possible change (one
constant), perfect ordinary-API compatibility, zero per-tick cost, marker
*is* ordinary arena content rather than a second layer. **Fatal gap:** the
owner can erase it. Eight `WRITE`s of value `0` into its own core — 0.5% of
a 1,600-action budget — restore full invisibility *while keeping ownership*.
A "hider" agent re-creates the exact exploit alpha.11 exists to close, at
negligible cost. Seeding alone therefore does not satisfy the Phase A3
invariant.

**Option B — persistent core-visible cell state.** `READ` of a core cell
returns a marker regardless of stored content, or a parallel "core layer" is
exposed. **Rejected.** It special-cases `READ` and creates a second arena
layer, abandoning the principle that strategy emerges from ordinary memory
manipulation; it also breaks `READ`'s round-tripping, which both defenders'
`READ`-then-compare repair logic depends on. Highest privileged-behaviour
risk, worst to explain in RULES.md, worst for artifact interpretation.

**Option C — rules-maintained core marker (full restoration).**
**Rejected as specified.** Restoration that ignores ownership reverts
attacker damage and makes cores effectively indestructible — a direct Phase
A7 violation. Restoration scoped to owner-owned cells avoids that, but *full
content* restoration still overwrites the owner's own meaningful bytes:
`reactive_core_defender` reads its own core cells and compares against its
own `0xC7`, so normalising them to a beacon would make every patrol read
look like damage and drive it into permanent false repair — silently
redesigning a reference defender, which the governing task forbids.

**Option D — owner-maintained core beacon. SELECTED.** Option A plus the
minimum part of Option C required to make the invariant hold under
adversarial play, and no more:

1. **Seed** — at match initialisation, core cells are seeded with the public
   constant `CORE_BEACON_BYTE` instead of `0`.
2. **Non-blank maintenance** — at the end of every tick, for every *living*
   entrant, any cell of its own core that **it still owns** and whose content
   is `0x00` is rewritten to `CORE_BEACON_BYTE`, attributed to that same
   owner.

In one sentence: **a core cell owned by its own living entrant is never
blank.**

Why this scoping is load-bearing, not incidental:

* **Only owner-owned cells are touched** → an attacker's write is never
  reverted, no ownership is ever restored, `vm.ownership_counts` never
  changes, and `apply_core_capture` is untouched. Observability confers zero
  invulnerability (Phase A7).
* **Only `0x00` is repaired** → `core_defender`'s `0xD3` and
  `reactive_core_defender`'s `0xC7` core signatures survive intact and their
  repair logic works exactly as designed. No defender is redesigned.
* **`0x00` is the only way to hide** → any non-zero content is observable, so
  repairing `0x00` closes the entire hiding surface.
* Cost is `O(entrants × CORE_SIZE)` = ≤ 24 comparisons/tick, no allocation,
  no arena scan; maintenance writes route through `VM._wr8` like every other
  write, so they appear in that tick's `memory_diffs` and replays
  reconstruct exactly.

Design comparison table (ordinary-API compatibility, determinism,
complexity, interaction with normal writes, attackability, defensive
strategy, replay transparency, artifact interpretation,
emergent-environment philosophy, ease of explanation, privileged-behaviour
risk) is in `design_options.md`. Selection was made on mechanical grounds
only — no win rate existed when the file was written.

**Beacon byte: `CORE_BEACON_BYTE = 0xCE`.** Non-zero (a zero beacon is the
defect), and distinct from every signature used by any bundled starter or
reference agent — `0x99` adaptive, `0xC1` claimer, `0xE3` hunter, `0xC2`
strider, `0x2C` wanderer, `0xD3` core_defender, `0x5E` core_seeker, `0xA5`
core_tracker, `0xC7` reactive_core_defender — so no agent is blinded to
beacons by its own `value != self.signature` self-filter, and no agent's
ordinary territory is mistaken for a core. It is public Ruleset knowledge on
exactly the same footing `CORE_SIZE` already occupies, and deliberately not
keyed to any reference agent: **no agent needs to recognise this particular
value to benefit**, because every existing content-based searcher keys on
"non-zero and not mine", which any non-zero beacon satisfies. Pinned by
test.

## 4. Phase A3 — the observability invariant

> **Consistent Core Observability.** Under the alpha.11 Ruleset, every cell
> of a living entrant's core that is currently owned by that entrant holds a
> non-zero byte at every tick boundary — established at match
> initialisation as the public constant `CORE_BEACON_BYTE`, and
> re-established at the end of any tick in which the owner has blanked one of
> its own still-owned core cells. This footprint exists **independently of
> whether that entrant chooses to defend, refresh, patrol, or write to its
> own core at all.** Discovering the footprint still requires ordinary Agent
> API v1 `READ` actions against addresses the searcher chose itself; no
> entrant is ever told another entrant's identity, position, or core
> coordinates.

Explicit non-implications, pre-registered and confirmed by the results
below:

* It does **not** mean every attacker instantly knows every core address.
  Core Tracker's coverage ceiling is unchanged (~13% of a 4096-cell arena
  within a 1,600-action budget); measured detection was 60–65% per match,
  first covering assault at mean tick ~84 of 200, and 40% of
  attacker-vs-expander cells produced no assault at all.
* It does **not** make cores harder to kill — maintenance touches only cells
  the owner already owns.
* It does **not** require any agent to know the beacon value, and no agent
  was changed.

## 5. Phase A4 — experimental Ruleset identity (hard acceptance requirement)

New identity **`bytefray-rules-2-alpha11`**, following the existing
`bytefray-rules-2-alpha1` convention exactly after auditing it:

- `ruleset_policy._RULESET_POLICIES` gains one explicit key. The table stays
  finite and fail-closed — no prefix match, no "latest Ruleset" fallback.
  `resolve_ruleset_policy` raises `UnknownRulesetError` for
  `"bytefray-rules-2"`, `"bytefray-rules-2-alpha12"`,
  `"bytefray-rules-2-alpha1x"`, `"BYTEFRAY-RULES-2-ALPHA11"`, and `""`
  (each pinned by test).
- `rules._RULESET_ALIASES` gets **no** entry — `normalize_ruleset_id` returns
  both alpha identities unchanged.
- No new plumbing was required: `MatchRequest.ruleset_id` →
  `_resolve_ruleset_id` → `resolve_ruleset_policy` (dispatch) /
  `canonical_match_id` (identity hash) / `_finalize_native_artifacts`
  (persisted `ruleset_id` on replay header and result envelope) already
  existed from alpha.1 and is reused unchanged, so the dispatched, hashed,
  and persisted identity cannot drift apart.
- `bytefray-rules-1` remains frozen. `bytefray-rules-2-alpha1` remains
  executable with byte-identical historical semantics.
- Canonical match identity differs across all three identities for otherwise
  identical inputs (pinned by test): `ruleset_id` is already a first-class
  component of `canonical_match_id`'s hash payload, so old alpha1 and new
  alpha11 matches can never be conflated under one `match_id`/`result_id`.
- `agent_evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` is untouched and
  still derives from `BYTEFRAY_RULESET_ID`; `evaluation_history`'s comparison
  alignment already refuses to align cells across differing `rules_id`, so
  resume/comparison continues to fail closed across Ruleset incompatibility
  with no change.

## 6. Phase A5/A6 — initialization and marker semantics, unambiguously

| Question | Answer |
|---|---|
| When is observable core state created? | At controller construction, in `seed_core_ownership`, before any `reset()`/`act()` — the same moment alpha.1 already seeded ownership. |
| Does it modify byte content? | Yes — and *only* content. Cells hold `0xCE` instead of `0x00`. |
| Does it modify ownership? | No. Identical to alpha.1: the owner owns all `CORE_SIZE` cells. |
| Included in initial replay state? | Yes — tick-zero `memory_diffs`, exactly as alpha.1's `0`-valued seeding already is. |
| Does it affect initial territory score? | **No.** Ownership counts are identical, so `territory_last`/`score` are byte-identical between alpha1 and alpha11 for a match where nothing else differs (pinned by test). |
| Can entrants overwrite it? | Yes, by ordinary `WRITE`. Nothing about a core cell is access-controlled. |
| Can an opponent overwrite it? | Yes — that is exactly how capture works, unchanged. |
| Can the owner accidentally erase it? | It can overwrite the *beacon byte* with its own content freely (defenders do). It cannot make a self-owned core cell blank: end-of-tick maintenance restores `0x00` → `0xCE`. |
| Does it wrap at arena boundaries? | Yes — `core_addresses` is unchanged and uses the ordinary `pos % arena_size` wrap (pinned: core at `arena-3` covers `125,126,127,0,1,2,3,4`). |
| Overlapping cores? | Unchanged from alpha.1. Later-constructed entrants seed over earlier ones; an entrant left owning zero core cells is captured with no attributable killer, exactly as `_attribute_core_capture` already documents. Maintenance cannot alter this: it never changes ownership. |
| After entrant death? | Maintenance skips non-living entrants. A dead entrant's core keeps whatever content and ownership it ended with, permanently (pinned by test). |
| Is the byte public Ruleset knowledge? | Yes, documented here and in `docs/V2_0_RULESET_V2_CANDIDATE.md`. Not keyed to any agent. |

Ruleset-v1 preservation (Phase A5): a v1 Python match performs **no** core
seeding, **no** beacon, **no** maintenance, **no** capture, and still
publishes an empty tick-zero `memory_diffs` — pinned by a dedicated test, in
addition to the pre-existing `test_ruleset_v1_equivalence.py` golden corpus,
which passes unchanged. Historical alpha1 preservation: a full alpha1
capture scenario still captures on exactly tick 4 with exactly the same
attribution, and `CORE_BEACON_BYTE` appears nowhere in an alpha1 arena.

## 7. Phase A7 — observability is not invulnerability

Pinned directly by test, not argued:

- ordinary writes still capture a core under alpha11, with kill attribution
  and `core_captured` termination unchanged;
- maintenance never reverts an attacker's write — with seven of eight cells
  taken, all seven keep the attacker's byte *and* the attacker's ownership
  tick after tick for the rest of the match;
- maintenance never restores ownership or territory — the victim's
  `territory_last` stays at 1, not 8;
- maintenance stops the moment the owner dies;
- no cell is ever indestructible, and neither defender's behaviour changes.

## 8. Phase A8 — Core Tracker compatibility: no agent change

`core_tracker` was run **unchanged**, and no agent was modified anywhere in
this alpha (`git diff` over the reference-agent and starter trees is empty).
The question Phase A8 poses — *does a consistent ordinary-content footprint
naturally make its existing coarse-to-fine search more effective against
undefended expanders?* — is answered affirmatively and mechanically:

- Core Tracker's `_looks_foreign` already accepts any non-zero,
  non-own-signature byte. The beacon satisfies it by ordinary accident of
  being non-zero. There is no beacon-specific code anywhere in any agent.
- Its `CONFIRM_MIN_HITS = 2` rule with `PROBE_OFFSETS = (-8,-4,4,8)` is
  *already* shaped to distinguish a compact region from an isolated speck.
  For a hit anywhere in an 8-cell contiguous core, exactly one of the ±4
  probes lands inside the same core, so confirmation succeeds; `claimer`'s
  stride-101 sweep produces isolated singletons, so confirmation correctly
  fails. The discriminator that already existed now has something true to
  discriminate.
- Its `ASSAULT_WINDOW = 16` centred on the refined anchor covers all eight
  cells whenever the anchor lands inside the core, which is why confirmed
  detection converts to capture at essentially 100% against an *undefended*
  core and only 22.5%/12.5% against a *defended* one.

This is the strongest available form of the evidence: the improvement comes
entirely from the Ruleset, with the attacker's source held byte-for-byte
fixed.

## 9. Phase A10/A11 — matched comparison design

Pre-registered in
`runs/v2_0_alpha11_ruleset_candidate_resolution/resolution_a/matrix_config.json`
before execution. Alpha.10's 981-match matrix was **not** rerun; this is a
matched two-Ruleset resolution test at **650 matches per Ruleset**,
deliberately smaller than alpha.10's single-Ruleset corpus.

Frozen throughout, confirmed unchanged: `CORE_SIZE = 8`, arena 4096,
`instr_per_tick = 8`, 200-tick budget, scoring and weights, `win_mode
score_fallback`, survivor winner eligibility (`results.resolve_winner`,
reused directly), the scheduler, capture-check timing, the capture rule
itself, Agent API v1, and all six agents' source.

Placements reused byte-for-byte from alpha.7/9/10:

| Condition | A | B | C |
|---|---:|---:|---:|
| `control` | 0 | 1365 | 2730 |
| `hot` | 282 | 1846 | 3411 |
| `cold` | 83 | 1281 | 2635 |
| `heldout_even_eighths` | 512 | 1536 | 2560 |

- **1v1**: the nine load-bearing matchups, seats A/C (seat B unused, matching
  alpha.10 §11 so the corpora are comparable), both scheduler orders (list
  order is scheduling order; each agent's own `(slot, address)` never moves),
  all four placements. Cells containing `core_tracker` use the full 5-seed
  set (alpha.10 §33: single-seed is demonstrably insufficient); every other
  cell is exactly reproducible and runs once at seed 1 to avoid
  pseudo-replication. **200 matches per Ruleset, 400 total.**
- **3-way**: five trios (offense + defender + expander ×4, plus
  two-expanders + offense), all six permutations, three placements
  (`control`/`hot`/`cold`), 5 seeds. **450 per Ruleset, 900 total.**
- **Supplementary** (added after the primary matrix, disclosed as such, for
  Phase A16 only): `core_defender` vs `reactive_core_defender`, 4 placements
  × 2 orders × 1 seed × 2 Rulesets = 16 matches.

**Exact match count: 1,300 primary (400 1v1 + 900 3-way) + 16
supplementary = 1,316. Zero infrastructure failures.** Wall time 13.23 s
(1v1) + 45.60 s (3-way).

Harness: `trace_match_v11.py` in the same directory — a new,
Ruleset-parameterised harness rather than an edit of alpha.9's
`trace_match_v9.py`, which hardcodes the alpha1 identity and the
zero-content seed at its own call sites; editing it in place would have
silently changed alpha.9's and alpha.10's reproducibility. It drives the real
production pieces (`VM`, `apply_action`, `seed_core_ownership`,
`apply_core_capture`, `maintain_core_beacons`, `core_seed_byte`,
`has_vulnerable_core`/`has_observable_core`, `resolve_ruleset_policy`,
`ScoringPolicy`, `StatisticsCollector`, `resolve_winner`) in
`PythonEntrantController.run`'s exact ordering. No per-action trace is
persisted — traces are consumed in-process into one bounded summary per
match.

## 10. Phase A12/A13 — detectability parity: the central measurement

Restricted to the 1v1 cells where an offense-capable entrant is actually
present (an agent's unrestricted rate is diluted by matches against
opponents that never attack anything, which differs per agent and would
understate parity). 40 matched matches per agent per Ruleset.

| | foreign core **read** rate | **covering assault** rate | **capture** rate | mean min core ownership |
|---|---:|---:|---:|---:|
| **alpha1** `claimer` | 0.625 | **0.000** | **0.000** | 7.00 |
| **alpha1** `hunter` | 0.600 | **0.100** | **0.000** | 6.53 |
| **alpha1** `core_defender` | 0.650 | **0.650** | 0.275 | 2.90 |
| **alpha1** `reactive_core_defender` | 0.650 | **0.650** | 0.125 | 3.25 |
| **alpha11** `claimer` | 0.625 | **0.600** | 0.600 | 2.83 |
| **alpha11** `hunter` | 0.600 | **0.575** | 0.550 | 3.00 |
| **alpha11** `core_defender` | 0.650 | **0.650** | 0.225 | 3.12 |
| **alpha11** `reactive_core_defender` | 0.650 | **0.650** | 0.125 | 3.25 |

Three things this table establishes, and they are the core of the alpha:

1. **The attacker's search coverage is identical under both Rulesets.** The
   foreign-core-*read* rate is unchanged for every agent (0.600–0.650), as it
   must be: `core_tracker`'s scan schedule depends on its RNG anchor and
   stride, not on content. Nothing about search *behaviour* changed.
2. **What the search finds changed completely, and only for the previously
   invisible.** Covering-assault rate went `0.000 → 0.600` (claimer) and
   `0.100 → 0.575` (hunter), while the two defenders stayed at exactly
   `0.650`. The gross informational asymmetry — defenders 0.650 vs expanders
   0.000/0.100 — collapses to a near-uniform 0.575–0.650. Core discoverability
   is now primarily a **Ruleset property**, not a consequence of the owner's
   own strategy. That is Phase A13's requirement, met. The residual ~0.05–0.075
   gap is attributable to expansion matches *ending earlier* on capture (fewer
   remaining ticks in which a further assault could begin), not to
   strategy-dependent visibility.
3. **Defense now has a measurable, positive marginal value.** At essentially
   equal detectability, an undefended core converts assault into capture at
   ~100% (claimer 0.600/0.600, hunter 0.550/0.575) while a defended one
   converts at 35% (`core_defender` 0.225/0.650) or 19%
   (`reactive_core_defender` 0.125/0.650). Alpha.10 §37 falsified H2
   ("defense reduces capture risk") because defending was what made you
   findable; under alpha.11 the intended relationship holds instead.

The same pattern holds in the 3-way corpus (270/180 matches per agent per
Ruleset): covering-assault rate goes from (claimer 0.156, hunter 0.244,
defenders 0.467/0.494) to (claimer 0.489, hunter 0.481, defenders
0.544/0.556), with capture rates of 0.393/0.363 for the expanders against
0.106/0.122 for the defenders.

Detection timing did not collapse: mean first covering assault is tick
**85.8** (claimer) / **83.7** (hunter) / **80.4**–**81.8** (defenders) out of
200, and mean capture tick is 84.5–98.6. Nothing is found instantly.

## 11. Phase A14 — expansion vs offense

| 1v1 matchup | alpha1 | alpha11 |
|---|---|---|
| `claimer` vs `core_tracker` (40) | claimer **100%**, capture 0% | claimer 40% / core_tracker 60%, capture **60%** |
| `hunter` vs `core_tracker` (40) | hunter **100%**, capture 0% | hunter 45% / core_tracker 55%, capture **55%** |

Alpha.10's central failure — *expansion won 100% of relevant 1v1 cells* — is
resolved. And the mechanism is exactly the intended one, cleanly separable:
in the 40 `claimer` vs `core_tracker` alpha11 cells, **claimer won all 16
matches in which it was not captured, and core_tracker won all 24 in which
it was.** The entire matchup reduces to "did the attacker's search find the
core in time" — a genuine strategic question with a real action cost — rather
than to a foregone territorial conclusion.

Both of Phase A14's strong-positive markers are met: real captures across
**all four** placements (14/14/15/17 in 1v1, i.e. uniformly, where alpha1's
16 captures were concentrated 2/4/4/6), some expansion-vs-offense outcomes
changing, offense paying a real search cost (§14), and expansion remaining
competitive rather than eliminated.

## 12. Phase A16 — offense vs defense, and expansion vs defense

| 1v1 matchup | alpha1 | alpha11 |
|---|---|---|
| `core_tracker` vs `core_defender` (40) | defender 72.5%, capture 27.5% | defender 77.5%, capture 22.5% |
| `core_tracker` vs `reactive_core_defender` (40) | reactive 87.5%, capture 12.5% | reactive 87.5%, capture 12.5% |
| `claimer`/`hunter` vs either defender (8 each) | expansion 100%, capture 0% | expansion 100%, capture 0% |
| `claimer` vs `hunter` (8) | claimer 87.5% | claimer 87.5% (unchanged) |
| `core_defender` vs `reactive_core_defender` (8, supplementary) | blind 75% / reactive 25%, 0 captures | **identical**: blind 75% / reactive 25%, 0 captures |

Defense is not weakened anywhere — if anything `core_defender` is marginally
*better* off (capture 27.5% → 22.5%), because the attacker now has many more
plausible targets competing for the same fixed search budget. Reactive's
advantage over blind against a real attacker is preserved exactly (12.5% vs
22.5% capture rate). The defender-vs-defender head-to-head and the
expansion-vs-defender matchups are **bit-identical** across the two
Rulesets, which is the expected result and a useful negative control: in
matchups where nobody searches, an observability rule changes nothing. No
defensive agent was redesigned.

## 13. Phase A17 — 3-way ecology subset

| Trio (90 matches each) | alpha1 win rates | alpha11 win rates | capture rate |
|---|---|---|---|
| `claimer`+`core_tracker`+`core_defender` | claimer 93.3 / cd 6.7 / ct 0 | claimer 62.2 / cd **33.3** / ct 4.4 | 20.0% → **46.7%** |
| `claimer`+`core_tracker`+`reactive` | claimer 93.3 / rx 6.7 / ct 0 | claimer 60.0 / rx **37.8** / ct 2.2 | 16.7% → **52.2%** |
| `hunter`+`core_tracker`+`core_defender` | hunter 84.4 / cd 15.6 / ct 0 | hunter 61.1 / cd **37.8** / ct 1.1 | 26.7% → **45.6%** |
| `hunter`+`core_tracker`+`reactive` | hunter 85.6 / rx 14.4 / ct 0 | hunter 63.3 / rx **33.3** / ct 3.3 | 27.8% → **43.3%** |
| `claimer`+`hunter`+`core_tracker` | claimer 77.8 / hunter 20.0 / ct 0 | claimer 50.0 / hunter 36.7 / ct **11.1** | 11.1% → **62.2%** |

Capture-victim breakdown (the direct measure of who the search now finds):

| Trio | alpha1 victims | alpha11 victims |
|---|---|---|
| claimer+ct+core_defender | core_defender 12, claimer 6 | **claimer 34**, core_defender 12 |
| claimer+ct+reactive | reactive 9, claimer 6 | **claimer 36**, reactive 13 |
| hunter+ct+core_defender | hunter 14, core_defender 10 | **hunter 35**, core_defender 7 |
| hunter+ct+reactive | hunter 13, reactive 12 | **hunter 33**, reactive 9 |
| claimer+hunter+ct | hunter 8, claimer 2 | **claimer 36, hunter 30** |

The answer to Phase A17's question — *does observability reduce expansion's
near-universal dominance without merely handing all wins to offense?* — is
yes, unambiguously, and the biggest beneficiary is **defense**, not offense:
defenders go from 6.7–15.6% to 33.3–37.8% of these trios, while
`core_tracker` itself rises only from 0% to 1.1–11.1%. That is the
economically coherent outcome — universal observability helps most the
strategy that is actually equipped to respond to being found.

## 14. Phase A15 — overcorrection checks, each measured

| Failure mode | Measured | Verdict |
|---|---|---|
| Core Tracker dominates essentially everything | combined win rate **13.1%** (from 2.6%); still the weakest of the five agents; 1v1 37.5%; 3-way 1.1–11.1% | not triggered |
| Every core trivially discovered immediately | detection 60–65% per attacker-present match; mean first covering assault tick ~84/200; **40% of attacker-vs-expander cells produce no assault at all** | not triggered |
| Defense becomes useless | defender combined win rate **rose** 20.8→40.3% and 22.9→42.0%; 1v1 vs offense unchanged-to-better | not triggered |
| Capture rates approach inevitability | 1v1 match capture rate 8% → **30%**; 3-way 20.4% → **50%** | not triggered |
| Reconnaissance ceases to be meaningful | Core Tracker information fraction **0.320 → 0.318** (unchanged); it is precisely what decides the matchup now | not triggered |
| Marker recognition replaces search strategy | **no agent was changed**; no agent contains beacon-specific code; the improvement comes from the Ruleset alone | not triggered |
| Ordinary expansion becomes nonviable | `claimer` and `hunter` remain the **top two** win rates in both 1v1 (60.9/54.7%) and combined (58.1/53.9%); they still beat both defenders 100% | not triggered |

## 15. Phase A12 — action and territory economics

Aggregated over the whole 1,300-match corpus.

| Agent | expansion fraction | information fraction | own-core fraction | opponent-core fraction |
|---|---:|---:|---:|---:|
| `claimer` (a1 / a11) | 0.995 / 0.995 | 0.000 / 0.000 | 0.002 / 0.002 | 0.003 / 0.003 |
| `hunter` | 0.994 / 0.994 | 0.000 / 0.000 | 0.002 / 0.002 | 0.004 / 0.004 |
| `core_tracker` | 0.674 / 0.671 | **0.320 / 0.318** | 0.002 / 0.004 | 0.004 / 0.006 |
| `core_defender` | 0.747 / 0.747 | 0.000 / 0.000 | 0.251 / 0.251 | 0.002 / 0.002 |
| `reactive_core_defender` | 0.724 / 0.727 | 0.262 / 0.260 | 0.012 / 0.011 | 0.002 / 0.002 |

Every agent's action economics is essentially **identical** across the two
Rulesets. This is important: alpha.11 changes *what information the same
spend buys*, not the price of anything. Expansion still spends ~99.5% of its
budget claiming territory; offense still pays ~32% of its budget for search;
`core_defender`'s 25.1% matches its documented `REFRESH_EVERY = 4` cadence
exactly. The difference in outcomes is therefore attributable to information,
not to a re-tuned action economy.

| Agent | mean final territory (a1 → a11) | mean final score (a1 → a11) |
|---|---:|---:|
| `claimer` | 1190.8 → 910.6 | 2195.4 → 1681.7 |
| `hunter` | 1156.0 → 939.0 | 2145.5 → 1734.4 |
| `core_defender` | 822.9 → **867.2** | 1555.7 → **1600.9** |
| `reactive_core_defender` | 812.9 → **852.1** | 1527.6 → **1567.9** |
| `core_tracker` | 756.1 → 750.0 | 1400.3 → 1340.5 |

Expansion's mean territory falls ~24% (it dies earlier in a substantial
fraction of matches); the defenders' *rises* slightly (they survive
alongside a captured expander more often). The 40–55% territorial gap
alpha.10 §24 measured between expansion and everything else narrows to
roughly 5–10%.

## 16. Captures

| | alpha1 | alpha11 |
|---|---|---|
| 1v1 match capture rate | 8.0% (16/200) | **30.0%** (60/200) |
| 1v1 victims | core_defender 11, reactive 5 | **claimer 24, hunter 22**, core_defender 9, reactive 5 |
| 1v1 captures by placement | control 4, hot 6, cold 2, heldout 4 | control 14, hot 17, cold 14, heldout 15 |
| 1v1 capture tick mean / median / range | 92.3 / 93.5 / 5–194 | 86.6 / 76.5 / 5–197 |
| 3-way match capture rate | 20.4% (92/450) | **50.0%** (225/450) |
| 3-way capture events | 92 | 245 |
| Killer attribution | 100% `core_tracker` | 100% `core_tracker` |

Every capture in both corpora is credited to `core_tracker` — the only
offense-capable entrant present — so all captures are deliberate and none are
incidental, reproducing alpha.10 §26 at this alpha's own scale. Note the
placement distribution: alpha1's captures were concentrated (2–6 per
condition), alpha11's are uniform (14–17). Observability makes capture
*less* placement-dependent, extending alpha.7/8/10's decoupling one step
further.

## 17. Phase A18 sensitivity analysis — order, placement, seed

Raw per-cell flip rates rise substantially under alpha11:

| Sensitivity (1v1) | alpha1 | alpha11 |
|---|---:|---:|
| scheduler order, global | 17.0% | 35.0% |
| … expansion vs offense | **0%** | 50.0% |
| … offense vs defense | 40.0% | 35.0% |
| … expansion vs defense | 0% | 0% |
| placement, global | 18.0% | 56.0% |
| … expansion vs offense | **0%** | 95.0% |
| seed, global | 21.9% | 68.8% |
| … expansion vs offense | **0%** | 93.8% |
| 3-way permutation, global | 36.0% | 84.0% |

Read naively this looks like scheduler/placement dominance. It is not, and
the distinction matters enough to test directly. Alpha.10 §14/§22/§31 already
established the correct reading — *order sensitivity concentrates where a
matchup is otherwise closely contested, not where one strategy already
dominates* — and every one of alpha11's increases is inside the cells that
**stopped being structurally determined**. A cell whose outcome is 50/50 is
sensitive to everything by construction; alpha1's 0% figures in
expansion-vs-offense were not robustness, they were foregone conclusions.

The governing task's actual dominance test is whether order/placement
*systematically* predicts outcomes. Measured on the 80 alpha11
expansion-vs-offense cells:

| Varying | `core_tracker` win rate |
|---|---|
| placement `control` / `hot` / `cold` / `heldout` | 0.500 / 0.600 / 0.600 / 0.600 |
| scheduler order `as_listed` / `reversed` | 0.525 / 0.625 |
| `core_tracker` scheduled **first** / **second** | 0.625 / 0.525 |
| seed 1 / 2 / 3 / 4 / 5 | 0.750 / 0.625 / 0.625 / **0.250** / 0.625 |

No placement confers a systematic advantage (spread of 10 points on n=20
subsamples, and no condition is even directionally special). Scheduling first
is worth ~10 points on n=40 — real but not decisive, and far from
"predicts outcomes as well as or better than strategy". **Seed is the
dominant driver (25%–75%)**, which is precisely the intended semantic:
whether the attacker's own RNG-anchored search happens to cover the target
within budget. That is genuine search variance — alpha.10 §33's "useful
diversity, manageable variance" case — now extended to a matchup that used to
have no variance because it had no contest.

**Scheduler classification: Moderate, unchanged from alpha.10** — and
notably the offense-vs-defense class, which alpha.10 flagged at 40%,
*improved* slightly to 35% here. Placement classification: **Low-to-Moderate
and now more uniform**, since capture is distributed evenly across all four
conditions where alpha1 concentrated it. Seed: a single-seed methodology is
now insufficient for *two* matchup classes rather than one — a concrete
tightening of alpha.10 §33's recommendation.

## 18. Phase A18 — Resolution-A verdict

**A-PASS.** All six pre-registered pass conditions are met and none of the
seven overcorrection conditions triggered:

1. Undefended expansion cores are legitimately discoverable — covering
   assault 0.000/0.100 → 0.600/0.575, real captures across all four
   placements.
2. Offense gains real but non-universal leverage — `core_tracker` 1v1 10% →
   37.5%, combined 2.6% → 13.1%, still the weakest of the five.
3. Pure expansion is no longer near-universal — `claimer` 1v1 98.4% → 60.9%,
   combined 90.1% → 58.1%, 3-way trio share 77.8–93.3% → 50.0–63.3%. Nothing
   in the corpus exceeds a 60.9% win rate.
4. Defense remains meaningful and is no longer uniquely penalised — defender
   combined win rate roughly doubled; same detectability as expanders, 3–5×
   lower capture rate.
5. Scheduler order and placement are not dominant (§17), measured
   systematically rather than inferred from flip rates.
6. Reconnaissance retains its action cost — information fraction unchanged at
   ~0.32, and 40% of attacker-vs-expander cells still yield no assault.

Per Phase A18's explicit instruction, **Resolution B was not implemented**.
No territory-maintenance or decay mechanic exists anywhere in this alpha.

## 19. Resolution B — not entered

Phase B1's entry condition (`A-QUALIFIED`) was not met. No maintenance
designs were selected, no threshold was derived or pre-registered, no
`bytefray-rules-2-alpha12`-style identity was minted, no ownership-expiry
bookkeeping was added, and no B-phase matrix ran. Items 35–42 of the
governing report list are therefore not-applicable by gate, not omitted.

## 20. Performance

Resolution A adds one bounded end-of-tick pass. Measured in isolation:
`maintain_core_beacons` costs **7.42 µs per call** with three living
entrants and `CORE_SIZE = 8` — 24 comparisons, no allocation, no arena scan
— i.e. **1.48 ms per 200-tick match** against a ~90–100 ms match, about
1.5%. Interleaved end-to-end wall-clock sampling on this (busy) machine put
the difference between 1.8% and 7.9% depending on the estimator, which is
measurement noise around the 1.48 ms of actual added work. Ruleset v1 and
`bytefray-rules-2-alpha1` execution paths are gated and therefore
byte-identically unaffected. Not a material regression, and not used as a
decision criterion.

## 21. Artifact compatibility qualification

- Historical **v1** artifacts remain readable and interpretable — no schema
  version moved, `resolve_result_ruleset`/`resolve_replay_ruleset` are
  untouched, and `test_ruleset_persistence.py`/`test_ruleset_v1_equivalence.py`
  pass unchanged.
- Historical **alpha1** artifacts remain correctly labelled and are never
  reinterpreted under alpha.11 semantics: the two identities are separate
  keys in `_RULESET_POLICIES`, neither aliases the other in
  `rules._RULESET_ALIASES`, and an alpha1 match still produces
  byte-identical behaviour (pinned by test, including the absence of
  `CORE_BEACON_BYTE` anywhere in an alpha1 arena).
- New **alpha11** artifacts persist `"bytefray-rules-2-alpha11"` in both the
  replay header and the result envelope (pinned by test).
- **Canonical match identity differs** across v1 / alpha1 / alpha11 for
  otherwise identical inputs (pinned by test), so no `match_id`/`result_id`
  can conflate two different gameplay semantics.
- **Resume/comparison fails closed**: `agent_evaluation`'s header/envelope
  `ruleset_id` cross-check and `evaluation_history`'s `rules_id`-keyed
  condition alignment are both unchanged and both already refuse to mix
  Rulesets.
- **Replay reproduces correct semantics per identity**: every alpha.11
  state change — beacon seeding and every maintenance write — is published as
  an ordinary `memory_diffs` entry in the tick it occurred (pinned by test),
  so a replay of an alpha11 match reconstructs alpha11 arena content exactly,
  and a replay of an alpha1 match reconstructs alpha1 content exactly. No
  hidden, replay-only semantics were introduced.
- No schema version bumped anywhere. No new `termination_reason` value; the
  existing additive `"core_captured"` is reused.

## 22. Regression qualification

| Check | Result |
|---|---|
| New `engine/tests/test_ruleset_v2_alpha11.py` | **36 / 36 passed** |
| Alpha-focused suites (`test_ruleset_v2_alpha1`, `test_ruleset_policy`, `test_ruleset_v1_equivalence`, `test_ruleset_persistence`, `test_v2_alpha1_reference_agents`, `test_v2_alpha2_reactive_defender`, `test_v2_alpha4_1_winner_semantics`, `test_v2_alpha4_multi_entrant`, `test_v2_alpha8_core_tracker`) | **132 / 132 passed**, unchanged |
| Ruleset-v1 golden equivalence | passed, values unchanged (no golden value refreshed) |
| Full `pytest` (verified alpha.11 starting baseline) | 1556 passed, 6 skipped, 2 deselected, 0 failed (1562 selected) |
| Full `pytest` (alpha.11 applied) | **1592 passed, 6 skipped, 2 deselected, 0 failed** (1598 selected) |
| Baseline reconciliation | +36 selected, +36 passed — exactly the 36 new alpha.11 tests, nothing else moved in either direction |
| Ruff (`engine client`) | clean |
| mypy (`engine/src/battle_engine`) | clean, 70 files (unchanged count) |
| mypy (`client/src/battle_client`) | clean, 10 files (unchanged count) |
| `git diff --check` | clean |
| `git diff -- client/src app` | empty |
| Agent source diff (starters + reference agents) | empty |

## 23. Research artifacts

`runs/v2_0_alpha11_ruleset_candidate_resolution/` (gitignored under the
existing `runs/` precedent, consistent with every prior alpha):

```
resolution_a/design_options.md                    pre-registered A1-A3 design record
resolution_a/matrix_config.json                   pre-registered matrix + gates
resolution_a/raw_results.json                     1,300 bounded per-match summaries
resolution_a/analysis_summary.json                all derived analyses
resolution_a/supplementary_defense_vs_defense.json  16-match A16 subset
candidate/decision_summary.json                   A-PASS record + gate checks
trace_match_v11.py                                Ruleset-parameterised harness
run_resolution_a.py                               matrix driver
analyze_resolution_a.py                           pure post-processing
```

`resolution_b/` does not exist — Resolution B never ran.

The two pre-registration files were written and frozen before any
implementation, test, or match existed, and were not rewritten after results
came in.

## 24. Documentation

This document, plus the pre-beta candidate specification
`docs/V2_0_RULESET_V2_CANDIDATE.md` (Resolution C). `docs/ROADMAP.md`,
`docs/FUTURE_PLANS.md`, `README.md`, `CHANGELOG.md`, and the project version
were **not** modified, per Phase C8 — the next user-directed phase handles
beta planning; alpha.11 supplies evidence only.

## 25. Beta readiness — GO

**GO** for beginning the separate v2 beta-planning phase.

- Expansion dominance is materially resolved (§11/§13/§18) and no new
  universal strategy replaced it (§14): the maximum win rate anywhere in the
  corpus is 60.9%, against alpha.10's 98.4%/84.7%.
- Core observability is coherent, minimal, deterministic, replay-transparent,
  and requires no Agent API change and no agent change.
- Territory maintenance was correctly **not** adopted — the gate did not open,
  and stacking a second mechanic on a working one was explicitly out of scope.
- Offense retains cost (~32% of budget), defense retains cost (25% / 26%),
  expansion remains viable and still the strongest single role.
- Scheduler sensitivity is understood and explicitly accepted as strategy
  (§17, and see the candidate document's capture-check decision), with the
  evaluation-balancing obligation that entails.
- Placement requirements are understood and became *less* severe.
- Artifact identity is correct and v1 / alpha1 both remain preserved and
  executable.

## 26. Unresolved issues for beta (not before beta)

1. **`CORE_BEACON_BYTE` and `CORE_SIZE` are fixed module constants.** Both are
   public Ruleset knowledge and neither is configurable. Whether a beta should
   make either a Ruleset-versioned parameter is a beta-1 decision; making them
   per-match configuration would create a Ruleset-identity question this alpha
   deliberately did not open.
2. **Self-core false positives.** Under alpha11 an attacker whose scan crosses
   its *own* core sees its own beacon as "foreign" and may spend ~21 actions
   probing and assaulting itself. This is harmless (writing your own signature
   over your own cell preserves ownership; no self-capture is possible) and
   symmetric across entrants, but it is a real, disclosed, ~1.3%-of-budget
   inefficiency that a beta reference agent could trivially avoid by
   remembering its own `observation.pc`. Not fixed here because Phase A8
   requires preferring no agent change.
3. **Scheduler-order sensitivity in contested cells** remains real (35% 1v1,
   84% 3-way permutation). It is now accepted as strategy rather than
   deferred as unknown, but the closed-form condition for when order flips an
   outcome (alpha.9's original open question) is still not derived, and
   evaluation must balance order rather than sample it once.
4. **Seed methodology must widen.** Single-seed comparison is now
   demonstrably insufficient for both offense-vs-defense *and*
   offense-vs-expansion. Any beta evaluation involving a search-based agent
   needs a genuine seed set.
5. **Seat/orientation confounds inherited from alpha.5–alpha.10** (seat C's
   general territorial advantage; the A/C-only 1v1 seat convention) remain
   open and orthogonal to this alpha's finding.
6. **Multi-entrant product workflow.** 3+ entrant execution is architecturally
   proven across 900 more matches here, but no product surface exposes it; the
   candidate document classifies it as supported engine capability, not
   required product workflow.
7. **The experimental Ruleset is still experimental.** `bytefray-rules-2` was
   deliberately not claimed; the promotion conditions are listed in the
   candidate document.
