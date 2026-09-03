# Bytefray v4 RC Path — Phase 2: Stable Ruleset/API Promotion and Default Convergence

Branch: `v4-rc1-development`

Starting SHA: `e42f9fb67cb28f2ca343e7125eef4fae0a9c8b6e` (Phase 1's ending commit)
Ending SHA: `71b1a0d39963ef556215a8d8bf104b8fe5c32da0`

Authority for this phase's implementation decisions: the governing "Bytefray v4 RC Path —
Phase 2" task itself, plus [docs/research/v4/V4_RC1_PHASE1_EVALUATION_METHODOLOGY.md](V4_RC1_PHASE1_EVALUATION_METHODOLOGY.md)
and [docs/research/v4/V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md](V4_PRE_RC_GAMEPLAY_EVALUATION_RESEARCH.md),
both treated as ratified and frozen. Neither was contradicted by anything found while
implementing this phase.

This is a **compatibility-promotion phase**: it converts already-qualified v4 prerelease
contracts into permanent stable Bytefray 4.0 identities. It introduces no new mechanic, reopens
no reach/gameplay research, redesigns no evaluation methodology, and packages or publishes
nothing.

---

## A. Executive summary

| Gate | Result |
|---|---|
| Permanent stable Ruleset `bytefray-rules-4` introduced, gameplay-identical to `bytefray-rules-4-alpha2`? | **YES** |
| Release-blocking equivalence corpus (23 tests) passes with zero gameplay divergence? | **YES** |
| Agent API v2 declared the stable 4.x programming contract, with no field/action/semantic change? | **YES** |
| Replay schema 4 declared the stable v4 wire contract, with no shape change? | **YES** |
| Stable v4 evaluation (schema 7, `ruleset_v4_seeded_placements`) integrated under the new identity? | **YES** |
| Default `--ruleset` resolution converges to the stable identity across every product surface from one table? | **YES** |
| Historical `bytefray-rules-4-alpha1`/`bytefray-rules-4-alpha2` remain immutable (pinned canonical IDs, no aliasing)? | **YES** |
| Fail-closed compatibility audit (VM/blob and Agent API v1 rejected under stable v4; Agent API v2 accepted) proven at both the predicate and real-execution level? | **YES** |
| Any gameplay-observable behavioral difference found between alpha2 and stable v4? | **NO** |
| New gameplay mechanic, reach/scoring/termination change, or evaluation-methodology redesign introduced? | **NO** |
| Full suite / GUI suite / static checks clean at the final commit? | **YES** |
| RC1 merged, tagged, packaged, or published? | **NO** |

```text
PHASE 2 QUALIFIED — READY FOR RC PATH PHASE 3
```

---

## B. Starting state, verified

```text
git status --short          (empty)
git branch --show-current   v4-rc1-development
git rev-parse HEAD          e42f9fb67cb28f2ca343e7125eef4fae0a9c8b6e
```

`e42f9fb` is Phase 1's own ending commit — Phase 1's report and the pre-RC research report it
carries forward were both already present, byte-identical, and treated as ratified/frozen
authority for this phase. No repository state other than what Phase 1 left behind was found;
Phase 2 began from a clean tree with no rebase, merge, or branch change.

---

## C. Implementation

### C.1 New identity registration

`BYTEFRAY_RULESET_V4_ID = "bytefray-rules-4"` was added to `battle_engine.rules` alongside its
two alpha siblings, with a rationale comment recording that promotion never aliases identity —
mirroring the repository's own established precedent, `bytefray-rules-2-alpha11` →
`bytefray-rules-2` (Ruleset v2's own beta1 promotion, proven equivalent by
`engine/tests/test_ruleset_v2_promotion_equivalence.py`, which this phase's own equivalence
corpus follows the same shape as).

Its `RulesetPolicy` in `battle_engine.ruleset_policy` is copied field-for-field from
`RULESET_V4_ALPHA2`, not re-derived:

```python
RULESET_V4 = RulesetPolicy(
    ruleset_id=BYTEFRAY_RULESET_V4_ID,
    supported_runtime_kinds=frozenset({"python"}),
    supported_python_api_versions=frozenset({2}),
    scheduler_mode="chunked",
    scheduler_chunk_size=2,
    scheduler_rotate_start=True,
    core_placement="seeded",
    process_selection="round_robin",
)
```

registered in `_RULESET_POLICIES` and `PROCESS_RULESET_IDS`. `OMITTED_RULESET_CANDIDATES`
(§H below) now names the stable identity instead of alpha2.

### C.2 Why this is sufficient: the shared-implementation architecture

`bytefray-rules-4-alpha2`'s entire behavior is dispatched off `RulesetPolicy` field values, never
off the literal `ruleset_id` string:

- `battle_engine.process_runtime.ProcessMatchController` — the v4-family match executor —
  contains **zero** Ruleset-identity branching (confirmed by direct grep sweep of the module:
  no reference to any `BYTEFRAY_RULESET_V4_*` constant anywhere in it). It reads
  `scheduler_mode`/`scheduler_chunk_size`/`scheduler_rotate_start`/`process_selection` off the
  resolved policy object and nothing else.
- `battle_engine.scheduler.run_chunked_quota` is policy-parameterized, not identity-parameterized.
- `battle_engine.python_runtime`'s seeded-placement draw (`_placement_draw`) uses a **fixed**
  domain-separation string, `"bytefray-rules-4-alpha2:placement:"`, that is never parameterized by
  which of the three v4 identities is executing — confirmed by reading the function directly.
  Identical `(seed, arena_size, entrant_count)` inputs therefore already produce identical
  resolved addresses under all three identities; this phase changed only the docstrings
  explaining why that string must stay fixed, not the string itself or any placement behavior.

Given this, copying `RulesetPolicy`'s field values was expected to be *architecturally*
sufficient for full gameplay equivalence — §D proves this claim behaviorally rather than resting
on the architectural argument alone.

### C.3 Two non-policy-driven sets that needed a manual, explicit addition

Not everything is policy-driven. A systematic sweep (`grep -rln "BYTEFRAY_RULESET_V4_ALPHA1_ID"`
across `engine/src/battle_engine/` and `app/`, every hit manually audited) found two finite,
explicit sets that would have silently diverged in behavior had they been left alone:

- **`_CORE_PLACEMENT_GUARDED_RULESET_IDS`** (`battle_engine.match_service`) — controls which
  Rulesets reject overlapping entrant core placements. `bytefray-rules-4-alpha1` and
  `bytefray-rules-4-alpha2` are both in this set; `bytefray-rules-4` is now added, with the same
  guard the two alphas already get.
- **`DESIGNER_AUTO_TRACE_RULESET_IDS`** (`app.services.designer_workflows`) — controls which
  Rulesets get automatic spectator-trace recording in Designer matches. `bytefray-rules-4` is now
  added alongside both alphas.

Neither gap is automatically caught by copying `RulesetPolicy` fields; both were found by direct
code audit before they became a real behavioral divergence, not discovered as a test failure
afterward.

### C.4 Deliberately not touched

`battle_engine.python_runtime`'s `VULNERABLE_CORE_RULESET_IDS`/`OBSERVABLE_CORE_RULESET_IDS` were
inspected and deliberately **not** given the new identity: `bytefray-rules-4-alpha2` is already
correctly excluded from both (they are v1-family/`python_runtime`-only mechanics, unreachable for
the process-runtime family that all three v4 identities dispatch through), so adding
`bytefray-rules-4` there would have been a new, wrong divergence from alpha2's own behavior, not a
gap.

### C.5 Product entry-point wiring

`cli.py`, `agent_test.py`, `tournament_cli.py`, and `agent_evaluation.py`'s `--ruleset` argparse
`choices` lists were each extended with the new identity, with help text describing automatic
resolution to it. `agent_scaffold.py`'s generated-agent help text was updated to describe the
stable identity rather than alpha1. `app/services/ruleset_options.py` gained
`RULESET_V4_OPTION` and updated the Simple/Advanced/Evaluation option tuples (§H.3).

---

## D. Equivalence proof

### D.1 Corpus definition

`engine/tests/test_v4_stable_ruleset_equivalence.py`, **23 tests**, none of which existed before
this phase. Every test runs the *same* `MatchRequest` twice — once under
`bytefray-rules-4-alpha2`, once under `bytefray-rules-4` — with entrant starts independently
resolved by each run's own call into the same production placement seam
(`placement.resolve_direct_match_starts`), against real bundled v4 starter agents and the
governing task's own named adapted-Alpha2 reference agents:

| Dimension | Coverage |
|---|---|
| Entrant count | 2 (arena×seed grid), 3, 4 (including a multi-process agent) |
| Arena size | 256, 512, 1024 |
| Seed | 0, 1, 3, 7, 42 (grid) plus 0, 7 (hydra/nemesis pairing) |
| Agent archetypes | `v4_claimer`, `v4_scout`, `v4_local_defender`, `v4_defender_scout` (multi-process), `v4_concentrated_attacker`, `hydra_alpha2` (4 processes), `nemesis_alpha2` (3 processes, including a process named `disruptor`) |
| Termination coverage | decisive outcomes (organic mix across the grid/hydra-nemesis cells) and a deliberately forced `tick_limit` case |

Composition: 15 grid cells (3 arena sizes × 5 seeds) + 1 three-entrant case + 1 four-entrant
multi-process case + 4 hydra-vs-nemesis cells (2 arena sizes × 2 seeds) + 1 multi-process-vs-
single-process case + 1 forced-tick-limit case = **23**.

### D.2 Comparison discipline

Every `TickSnapshot` (covering process anchors, eligibility, action sequence, READ/WRITE/MOVE
results, disruption events, quota allocation/redistribution, and ownership/core state in one
record), the terminal `MatchResult`, and the `ReplayHeader` are compared as whole dataclass
sequences — never a hand-picked field subset — after nulling the four identity-bearing fields
(`replay_id`/`match_id`/`result_id`, and the header's own `ruleset_id`). Those same four fields
are then read back **unnulled** and asserted to legitimately *differ* between the two runs, so
the corpus cannot pass vacuously by comparing an artifact against a copy of itself.

### D.3 Comparator sensitivity, independently validated

A monkeypatch-based attempt to induce an artificial divergence (to prove the comparator would
catch one) did not reliably take effect across the import boundary and was abandoned. Sensitivity
was instead confirmed against a **real, already-understood divergence**: running the same
comparator logic against `bytefray-rules-4-alpha1` vs `bytefray-rules-4-alpha2` (which do
genuinely differ — fixed evenly-spaced placement vs seeded placement, and priority-order vs
round-robin process selection) correctly reports unequal tick sequences and unequal terminal
results. The comparator discriminates real differences; it is not vacuously permissive.

### D.4 Result

**All 23 tests pass. Zero gameplay-observable divergence was found between `bytefray-rules-4` and
`bytefray-rules-4-alpha2` anywhere in the corpus.** Every expected identity difference
(`match_id`/`result_id`/`replay_id`/header `ruleset_id`) was confirmed present in every case. No
finding in this phase required treating any behavioral difference as a "known limitation" —
none was found to require that framing.

---

## E. Agent API v2 stability declaration

No field, `ActionKindV2` member, declaration rule, or observation-contract semantic changed.
`docs/AGENT_API_V2.md`'s opening paragraph now declares the contract stable for the Bytefray 4.x
series rather than alpha-scoped, and is shared, unmodified, by all three registered v4 identities
— an agent written against it loads and runs identically whether the match resolves
`bytefray-rules-4`, `bytefray-rules-4-alpha2`, or `bytefray-rules-4-alpha1`. This is a
documentation-only promotion: nothing in `battle_engine`'s Agent API v2 implementation was
touched.

---

## F. Replay schema 4 stability declaration

No wire-shape change. `docs/REPLAY_SCHEMA.md`'s opening and "Schema 4 process state" section now
name all three v4 identities as schema-4 producers and describe the schema as the stable v4
replay contract rather than an alpha1-scoped one. `battle_engine.replay.SCHEMA_VERSION` and every
reader/writer path are unchanged.

---

## G. Stable evaluation integration

`_V4_METHODOLOGY_RULESET_IDS` (`battle_engine.agent_evaluation`) was extended from
`{bytefray-rules-4-alpha2}` to `{bytefray-rules-4-alpha2, bytefray-rules-4}`. This is the single
switch that puts the stable identity onto Phase 1's schema-7 `ruleset_v4_seeded_placements`
methodology, unmodified: pinned 512 arena, 8 deterministic placement samples, both orientations
paired over the same resolved seat geometry, `SCHEMA_VERSION_V4`/`IDENTITY_VERSION_V4` (7).

Verified with a real, non-dry-run execution (`agents evaluate v4_claimer --opponents v4_scout
--ruleset bytefray-rules-4 --seeds 1 --ticks 20`), not merely by code inspection:

```text
evaluation.json: arena_alignment_mode = "ruleset_v4_seeded_placements"
evaluation.json: schema_version = 7, identity_version = 7
```

Schedule cardinality (`16N`, N = opponent count) was independently reconfirmed for the stable
identity via `--dry-run --json` against one opponent: `matrix_size: 16` (8 seeds × 2
orientations).

### G.1 Evaluation compatibility matrix

| Gameplay Ruleset | `agents evaluate` supported? | Methodology | Schema / Identity version | Arena | Default seed set |
|---|---|---|---|---|---|
| `bytefray-rules-1` | yes | historical v1 (fixed placement) | 4 | `Config` default | historical default |
| `bytefray-rules-2` | yes (incl. `--group`) | `ruleset_v2_standard_placements` (or `..._group_standard_layouts`) | 5 (6 for `--group`) | `Config` default | 5-seed standard |
| `bytefray-rules-4-alpha1` | yes | `fixed` (v2-methodology shape, three standard placements) | 5 | `Config` default | 5-seed standard |
| `bytefray-rules-4-alpha2` | yes | `ruleset_v4_seeded_placements` | 7 | pinned 512 | 8-seed standard |
| `bytefray-rules-4` (stable) | yes, as of this phase | `ruleset_v4_seeded_placements` (identical to alpha2's) | 7 | pinned 512 | 8-seed standard |

`--group` remains exclusive to `bytefray-rules-2`, unaffected by this phase.

### G.2 A discovered, pre-existing, non-blocking display defect

While verifying G above, the human-readable console summary line (`"Arena alignment: ... --
translation robustness not evaluated"`, printed both by `--dry-run`/`--dry-run --json` and by
`_print_result` after a real completed run) was found to always report `fixed` for *any*
v4-methodology Ruleset, never `ruleset_v4_seeded_placements` — confirmed by direct real-run
reproduction:

```text
$ bytefray agents evaluate v4_claimer --opponents v4_scout --ruleset bytefray-rules-4 --seeds 1 --ticks 20
...
Arena alignment: fixed -- translation robustness not evaluated
```

despite the same run's persisted `evaluation.json` correctly recording
`ruleset_v4_seeded_placements`/schema 7 (§G above). Root cause: three call sites
(`agent_evaluation.py:4653`, `:4679`, `:5033`) call `resolved_arena_alignment_mode(request.
is_v2_methodology, request.group)`, omitting the function's third parameter,
`is_v4_methodology`, which defaults to `False` — unlike the real matrix-building call site
(`agent_evaluation.py:2977`), which passes all three arguments correctly and is why the persisted
artifact is unaffected.

This defect **predates Phase 2**: it was reproduced, unmodified, at this phase's own starting
commit `e42f9fb` against `bytefray-rules-4-alpha2` (present since Phase 1 introduced the v4
methodology), so it is not a regression this phase introduced, and it affects `bytefray-rules-4`
and `bytefray-rules-4-alpha2` identically — it is not a behavioral difference between them and
does not affect §D's equivalence claim. It changes no persisted artifact, comparison, or resume
behavior. Left unfixed here, consistent with this phase's explicit compatibility-promotion scope
(no code path this phase governs required touching `resolved_arena_alignment_mode`'s call sites
to complete the promotion); recommended as a Phase 3 audit item (§L.1).

---

## H. Default convergence

### H.1 The one resolution table

```python
OMITTED_RULESET_CANDIDATES: tuple[str, ...] = (
    BYTEFRAY_RULESET_V2_ID,   # "bytefray-rules-2"
    BYTEFRAY_RULESET_V4_ID,   # "bytefray-rules-4"  (was BYTEFRAY_RULESET_V4_ALPHA2_ID)
    BYTEFRAY_RULESET_ID,      # "bytefray-rules-1"
)
```

`battle_engine.ruleset_policy.resolve_omitted_ruleset_for_agents` is the single seam every
product entry point that accepts an omittable `--ruleset` resolves through — this table is the
entire mechanism, so changing one entry converges every caller simultaneously (the v3-era RC
defect this phase's task explicitly named — duplicated per-frontend resolution logic — has no
opportunity to recur here, since there is exactly one table and no caller re-implements it).

### H.2 Per-surface convergence, confirmed

| Surface | Omitted `--ruleset`, Agent API v2 roster | Omitted `--ruleset`, Agent API v1 roster | Omitted `--ruleset`, VM/blob roster |
|---|---|---|---|
| `bytefray run` | `bytefray-rules-4` | `bytefray-rules-2` | `bytefray-rules-1` |
| `bytefray agents test` | `bytefray-rules-4` | `bytefray-rules-2` | `bytefray-rules-1` |
| `bytefray agents evaluate` | `bytefray-rules-4` | `bytefray-rules-2` | n/a (Python-only) |
| `bytefray tournament` | `bytefray-rules-4` | `bytefray-rules-2` | `bytefray-rules-1` |

All four rows resolve from the single table in §H.1; none hardcodes a Ruleset identity of its
own. `agents evaluate`'s Agent API v2 row additionally now runs the schema-7 methodology (§G)
rather than being rejected, per Phase 1.

### H.3 Designer presentation

| Designer workflow | Offered Rulesets (product-preference order) |
|---|---|
| Simple Quick Match | `bytefray-rules-2`, `bytefray-rules-4` — current gameplay only |
| Advanced | `bytefray-rules-2`, `bytefray-rules-4`, `bytefray-rules-4-alpha2`, `bytefray-rules-4-alpha1`, `bytefray-rules-1` |
| Agent Development | same full catalog as Advanced |
| Evaluation | `bytefray-rules-2`, `bytefray-rules-4`, `bytefray-rules-4-alpha2`, `bytefray-rules-4-alpha1`, `bytefray-rules-1` |

Both alpha identities remain explicitly selectable everywhere except Simple, whose entire promise
— "the gameplay you get if you do not think about it" — now points at the permanent contract
instead of a prerelease preview, exactly as it pointed at alpha2 before alpha2's own promotion
work and at alpha1 before that.

---

## I. Historical preservation

`engine/tests/test_v4_historical_immutability.py`, **2 tests**, neither existing before this
phase:

- **Pinned canonical identity.** `v4_claimer` vs `v4_scout`, arena 512, seed 5, ticks 50 under
  each alpha produces the exact `match_id`/`result_id` computed on this repository before the
  stable identity's registration (`match_b53e76a536d65e9f35b9e560` /
  `result_4eac520d48af9cd1ae859365` for alpha1; `match_779a09b9950d0e4db27b5ddb` /
  `result_50d49c7732848a9541fc9a93` for alpha2) — any future change to canonical-ID derivation
  caused by a third policy sharing alpha2's field values would be caught immediately, not
  discovered later as a silent artifact reinterpretation.
- **Cross-Ruleset execution isolation.** Running alpha1, then a stable-v4 match, then alpha1
  again (identical inputs) reproduces the first alpha1 result exactly
  (`match_id`/`result_id`/`reproducibility` all equal) — proving no cross-Ruleset shared/global
  state (module-level caches, mutable registries, RNG state) leaks between a stable-v4 execution
  and a subsequent historical one.

Both tests pass. `rules._RULESET_ALIASES` gains no entry for any of the three v4 identities —
`bytefray-rules-4-alpha1` and `bytefray-rules-4-alpha2` are not aliased to `bytefray-rules-4` in
either direction; all three dispatch, hash, and persist as fully distinct identities.

Separately, `engine/tests/test_ruleset_agent_compatibility.py` was extended from 17 to **25**
tests (+8): the stable identity's fail-closed behavior (VM/blob rejected, Agent API v1 rejected,
Agent API v2 accepted) is now proven both at the metadata-predicate level
(`agent_supported_by_ruleset`) and at the real `NativeMatchService.run` execution boundary,
mirroring the coverage both alphas already had rather than trusting policy-field copying alone.

---

## J. Documentation and compatibility updates

Seven files changed, one new, committed as `71b1a0d`:

| File | Change |
|---|---|
| `docs/RULES_V4.md` | **New.** Stable-gameplay reference for `bytefray-rules-4`, structured like `docs/RULES_V2.md`; does not edit either frozen alpha design document. |
| `docs/COMPATIBILITY.md` | New "Ruleset v4" section (mirrors "Ruleset v2"'s structure); superseded-note on the alpha2 boundary section (original text left unedited); fixed a stale Simple-Quick-Match description; refreshed legacy compatibility matrix rows. |
| `docs/AGENT_API_V2.md` | Declares the contract stable for Bytefray 4.x (§E). |
| `docs/REPLAY_SCHEMA.md` | Declares schema 4 the stable v4 replay contract, naming all three producers (§F). |
| `docs/AGENT_AUTHORING.md` | Table/scaffold-instruction updates reflecting the stable identity as current. |
| `README.md` | "Bytefray v4 alpha" section renamed/rewritten to "Bytefray v4"; Rulesets table and omitted-Ruleset explanation updated. Top banner, alpha4 release framing, Downloads, and Project Status sections deliberately untouched — they describe actual published-release state, unaffected by unreleased dev-branch work. |
| `CHANGELOG.md` | New "v4.0.0-rc1 Phase 2" subsection under `[Unreleased]`. |

`docs/DOCUMENTATION_INVENTORY.md` was checked and deliberately left unedited — it is a
point-in-time historical audit snapshot, not a live registry.

### J.1 Compatibility matrix

| Ruleset ID | Agent API | Runtime support | Replay schema | Status |
|---|---|---|---|---|
| `bytefray-rules-1` | v1 | Python and VM/blob | 3 (or earlier, recovered) | Stable |
| `bytefray-rules-2` | v1 | Python only | 3 | Stable |
| `bytefray-rules-4-alpha1` | v2 | Python only | 4 | Historical, frozen |
| `bytefray-rules-4-alpha2` | v2 | Python only | 4 | Historical, frozen |
| `bytefray-rules-4` | v2 | Python only | 4 | **Stable (new, Phase 2)** |

---

## K. Qualification

All commands run on Windows 11 Pro 10.0.26120, Python 3.13.14, `.venv/` at the repository root.

### K.1 Qualification integrity protocol

```text
HEAD before docs commit:  e3c54b281ebe8d28f548ab51126362a752af68df
HEAD after docs commit:   71b1a0d39963ef556215a8d8bf104b8fe5c32da0
git status:                clean, both times
SHA-256 digests of the 7 documentation files: computed against the qualified working tree
  (uncommitted, parented on e3c54b2) immediately before the final full-suite/GUI-suite/static run;
  recomputed immediately after committing as 71b1a0d — identical, all 7, both times.
```

The code+test portion of this phase (commits `a475d87`/`f216623`/`2c18d8e`/`e3c54b2`) was
qualified clean (full suite, GUI suite, static checks) before the documentation pass began, per
this repository's standing integrity discipline. The run recorded below is the final,
authoritative one: it qualifies the exact byte content that became `71b1a0d`, not a
before-the-fact approximation of it.

### K.2 Static checks

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | **All checks passed** |
| Engine mypy | `mypy engine/src/battle_engine` | **Success, 101 source files** |
| Client mypy | `mypy client/src/battle_client` | **Success, 15 source files** |
| Whitespace | `git diff --check` | clean |

### K.3 Full repository suite

```text
pytest --junitxml=...
```

**2933 collected, 0 errors, 0 failures, 14 skipped**, in 419.5s.

### K.4 Designer GUI suite

```text
pytest -m gui --junitxml=...
```

**2 collected, 0 errors, 0 failures, 0 skipped**, in 6.3s.

### K.5 New test inventory

| File | Tests | New in this phase? |
|---|---|---|
| `engine/tests/test_v4_stable_ruleset_equivalence.py` | 23 | new file |
| `engine/tests/test_v4_historical_immutability.py` | 2 | new file |
| `engine/tests/test_ruleset_agent_compatibility.py` | 25 (was 17) | +8 |

Nine further files (`test_agent_evaluation_v4.py`, `test_agent_evaluation_v2.py`,
`test_agent_test.py`, `test_cli_characterization.py`, `test_designer_ruleset_options.py`,
`test_ruleset_policy.py`, `tests/test_agent_combo_runtime_labels.py`,
`tests/test_agent_designer_lifecycle.py`, `tests/test_designer_ruleset_compatibility.py`) had
existing expectations updated to reflect the new default (`bytefray-rules-4` instead of alpha2)
— assertions corrected to the new true behavior, never weakened.

### K.6 Performance sanity check

Fresh benchmark (not carried over from an earlier, no-longer-reproducible run): 15 matches each
under `bytefray-rules-4-alpha2` and `bytefray-rules-4`, identical `v4_claimer` vs `v4_scout`
roster, arena 512, 500-tick cap, seeds 0–14.

```text
alpha2: 2.665s for 15 matches (177.7 ms/match)
stable: 2.629s for 15 matches (175.3 ms/match)
ratio (stable/alpha2): 0.987
```

No slower execution path was created — expected, since both identities dispatch through the
identical shared implementation (§C.2). The 16N evaluation schedule cardinality is unchanged
(§G).

### K.7 Not performed, and not claimed

No Linux qualification was performed. No installer/build qualification was performed. Both
remain explicitly deferred to a later RC phase (§L).

---

## L. Remaining RC-path work

### L.1 Phase 3 — product/default/compatibility audit

- Cross-platform (Linux) reproduction of this phase's placement/identity/equivalence evidence.
- Fix the pre-existing, non-blocking console-summary display defect found in §G.2
  (`resolved_arena_alignment_mode`'s three under-parameterized call sites in
  `agent_evaluation.py`) — cosmetic only, does not affect any persisted artifact, but should not
  ship un-audited into an RC.
- A final sweep of remaining documentation/help text for any other stale "alpha is current"
  framing this phase's own sweep may not have exhaustively covered.
- General product-surface audit of the default-convergence and Designer-presentation changes
  under real interactive use, not only automated tests.

### L.2 Phase 4 — RC artifact qualification and publication decision

- Windows installer/build qualification (deferred per this phase's own scope, and per the
  governing task's explicit instruction not to package or publish RC1 yet).
- The actual merge/tag/publish decision for `v4.0.0-rc1`.

No new gameplay, mechanic, or evaluation-methodology work belongs in either list — both are
scoped to auditing and shipping the contracts this phase and Phase 1 already qualified, not to
reopening them.

---

## M. Final decision

```text
PHASE 2 QUALIFIED — READY FOR RC PATH PHASE 3
```
