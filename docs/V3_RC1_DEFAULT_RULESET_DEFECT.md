# Bytefray v3.0 — RC1 Default-Ruleset Defect: Fix and Qualification Input

This document records the correction of a release-candidate defect found
after `v3.0.0-rc1` was tagged and published: an omitted CLI `--ruleset`
resolved to Ruleset v1 everywhere in the engine, while Agent Designer's
Python workflows (since `v3.0.0-alpha2`) explicitly default to Ruleset v2.
A new user running apparently equivalent Python-agent matches through the
CLI and the Designer therefore received materially different gameplay —
the CLI's default game cannot terminate through Ruleset-v2 vulnerable-core
capture at all. This work implements the correction on `v3.0-development`
as an input to `v3.0.0-rc2`. **`v3.0.0-rc1` was not moved, retagged, or
rewritten**, and no RC2 was tagged or published by this task.

---

## 1. Initial state

Verified directly before any modification:

| Item | Value |
|---|---|
| Branch | `v3.0-development` |
| HEAD | `5995dfcb1137b8d75851407d33c1a0608638095f` — "docs: mark v3.0.0-rc1 published" |
| Working tree | clean (only the known `.pytest-cache-v141: Permission denied` directory-read warning, not a tree change) |
| `origin/v3.0-development` | `5995dfcb…` — identical to HEAD |
| `v3.0.0-rc1` tag | `ad5ff8a5366d9d900c28e54fe0d65b1f3ad73485` — one commit behind HEAD (the "mark ... published" doc commit landed after the tag, as expected; the tag itself was untouched throughout this task) |
| Package version (`pyproject.toml`) | `3.0.0rc1` |
| `ProjectInfo` | `agent_api_version=1`, `result_schema_version=1`, `replay_schema_version=3` |
| Ruleset identities | product: `bytefray-rules-1`, `bytefray-rules-2`; registered-but-non-product: `bytefray-rules-2-alpha1`, `bytefray-rules-2-alpha11`, `bytefray-rules-3-alpha1` |
| CLI `--ruleset` default (`bytefray run`, `agents test`, `agents evaluate`, `tournament`) | argparse `default=None`, resolving deep in the engine to `bytefray-rules-1` for every omitted invocation |
| Agent Designer default | `bytefray-rules-2` for Simple/Advanced direct matches, Agent Development tests, and pairwise evaluation (all already explicit, since `v3.0.0-alpha2`) |

No stash was used. No destructive git operation was performed.

## 2. Defect reproduction

Reproduced against the actual CLI, using shipped starter agents, before any
code change:

```
bytefray agents test raider --opponent claimer --seed 1 --ticks 400
```

- **Resolved Ruleset (before fix):** `bytefray-rules-1` (the `--ruleset`
  flag was omitted; `agent_test.py`'s CLI passed `args.ruleset` — `None` —
  straight through to `test_agent()`, whose own default resolves to the
  frozen `BYTEFRAY_RULESET_ID`).
- **Result/replay Ruleset identity:** `bytefray-rules-1`, persisted in both
  `result.json` and the replay header.
- **Core capture:** unavailable. Ruleset v1 has no vulnerable-core
  mechanic at all (`battle_engine.python_runtime`'s Vulnerable Core /
  Consistent Core Observability rules are gated on the Ruleset v2 identity
  specifically); the match can only end via `all_agents_dead`,
  `last_agent_standing` from ordinary elimination, or `tick_limit`.
- **Difference from Designer:** identical Raider-vs-Claimer matchup
  launched from Agent Development (which has sent an explicit
  `--ruleset bytefray-rules-2` since alpha2) resolves to Ruleset v2 and
  reaches a genuine core-capture termination for the same seed.

This is preserved as regression evidence by
`test_default_python_agents.py::test_cli_omitted_ruleset_python_match_reaches_core_capture`,
which reproduces the identical command (now producing the opposite,
corrected result) and by the (renamed, still-passing) pre-fix assertion
history visible in this branch's own commit for `test_agent_test.py`.

Independently, Agent Designer's Python workflows were confirmed to already
default explicitly to Ruleset v2 (`app/services/ruleset_options.py`'s
`DESIGNER_RULESET_OPTIONS`, `app/views/development.py`, `app/views/
evaluation.py`, `app/agent_designer.py`) — this defect was CLI-only.

## 3. Root cause

Two related but distinct layers both use `ruleset_id: str | None = None`
with "`None` → resolve to `BYTEFRAY_RULESET_ID`" as their deep, historical
default:

- `battle_engine.match_service.MatchRequest.ruleset_id` /
  `_resolve_ruleset_id` (used by `NativeMatchService.run` and artifact
  persistence).
- `battle_engine.agent_evaluation`'s `resolve_evaluation_ruleset_id` /
  `EvaluationRequest.resolved_rules_compatibility_id`.

These deep defaults are correct and load-bearing for every internal/
library/test/research caller that constructs a request directly — they
must never change, or every direct caller that intentionally omits a
Ruleset (numerous engine tests, `tools/` research scripts, presets) would
silently change meaning. The actual defect is one layer up: every
**product-facing CLI parser** (`cli.py`, `agent_test.py`,
`agent_evaluation.py`, `tournament_cli.py`) declared `--ruleset` with
`default=None` and then passed that raw, possibly-`None` value straight
into the request it built, with no CLI-level policy distinguishing "the
user omitted this" from "resolve it the way current product gameplay
should." Agent Designer's `v3.0.0-alpha2` fix solved this narrowly, one
GUI tab at a time, by always sending an explicit `--ruleset`; the CLI itself
was explicitly flagged as the "last remaining place" this was still
implicit (see `V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md` §21) and was
deferred, then re-confirmed as still-open and still non-blocking during RC1
qualification (`V3_RC1_QUALIFICATION.md` §23) — until later Ruleset
research established that the CLI's default game could not reach
core-capture termination at all, elevating it from a documentation gap to
an RC-qualification-relevant gameplay-divergence defect.

## 4. User-facing impact

A new user who launches an ordinary Python-agent match through the CLI
with no `--ruleset` gets Ruleset v1 (no vulnerable-core capture available),
while the same agents launched through Agent Designer get Ruleset v2 (core
capture available). Two front ends to the same product give materially
different games for the same nominal action, with no indication anything
was implicitly decided.

## 5. Resolution policy

A new shared, testable resolver,
`battle_engine.ruleset_policy.resolve_omitted_ruleset_id(requested_ruleset_id,
runtime_kinds)`:

```python
def resolve_omitted_ruleset_id(requested_ruleset_id, runtime_kinds):
    if requested_ruleset_id is not None:
        return requested_ruleset_id          # explicit choice: unchanged
    kinds = frozenset(runtime_kinds)
    if kinds and kinds <= {"python"}:
        return BYTEFRAY_RULESET_V2_ID        # Python-only: current gameplay
    return BYTEFRAY_RULESET_ID               # VM-only / mixed / unknown: v1
```

Design principles, matching the governing task's "most important
instruction":

- **Explicit selection is always authoritative and untouched.** The
  function's first branch is a straight pass-through; it never validates,
  corrects, or overrides an explicit `--ruleset`, including one a
  downstream runtime-compatibility check will go on to reject.
- **Omission is CLI interpretation only, resolved once, at the CLI
  boundary, before any request is constructed.** Each product CLI entry
  point calls this resolver with the entrant runtime kinds it already
  knows for that specific invocation, then threads the *resolved* string
  — never `None`, never an "auto" sentinel — into the
  `MatchRequest`/`EvaluationRequest`/`TournamentRequest` it builds. No
  artifact ever records anything but a real, concrete Ruleset id.
- **The deep engine/library defaults are completely untouched.**
  `MatchRequest.ruleset_id`'s own `None → BYTEFRAY_RULESET_ID` default and
  `resolve_evaluation_ruleset_id`'s identical behavior are unmodified byte
  for byte. Every direct/library caller that never goes through one of the
  four CLI `main()` functions below — every existing engine test, every
  `tools/` research script, every preset that already names a Ruleset —
  is completely unaffected. Internal callers that need v1 continue to get
  it by construction, without this fix silently reinterpreting their
  omission.
- **Mixed-runtime and VM-only omission are unaffected.** VM-only and mixed
  Python/VM kind sets both resolve to Ruleset v1 here, exactly the
  historical fallback; a mixed roster is additionally rejected by
  `NativeMatchService.run`'s pre-existing, Ruleset-independent homogeneous-
  composition guard (`UnsupportedMatchCompositionError`) before any Ruleset
  is even consulted, so this fix cannot change mixed-roster behavior.

## 6. CLI paths audited

| Entry point | Entrant kinds known at resolution time | Change |
|---|---|---|
| `bytefray run` (`cli.py::main`) | Computed per-slot via new `_requested_entrant_kind()` helper (mirrors `_resolve_agent`'s own precedence chain minus anything that needs a resolved start address, so it can run *before* `resolve_direct_match_starts`) | Omitted `--ruleset` now resolves via `resolve_omitted_ruleset_id`; used for both placement resolution and `MatchRequest.ruleset_id` |
| `bytefray agents test` (`agent_test.py::main`) | Always `{"python"}` (`_resolve_python_entrant` rejects non-Python for both slots) | Omitted `--ruleset` now resolves to v2; `test_agent()`'s own library default is untouched |
| `bytefray agents evaluate` (pairwise) (`agent_evaluation.py::main`) | Always `{"python"}` (`EvaluationService._validate` requires Python for candidate/baseline/every opponent) | Omitted `--ruleset` (after the existing CLI-arg → preset three-tier resolution) now resolves to v2; `resolve_evaluation_ruleset_id`'s own library default is untouched. `--group`'s existing "requires bytefray-rules-2" check is now satisfied by an omitted `--ruleset` instead of failing closed on it — pairwise and group no longer diverge merely because one historically passed an explicit Ruleset and the other inherited a stale default |
| `bytefray tournament` (`tournament_cli.py::main`) | `{entrant.kind for entrant in entrants}`, already resolved before request construction | Omitted `--ruleset` now resolves per-roster; `TournamentService`/`TournamentRequest`'s own library default is untouched |
| `bytefray run --mode redcode94` | N/A | **Unreachable** — this branch returns before any new resolution code executes; see §9 |
| `bytefray agents test` group mode (`test_agents()`) | N/A | Library-only; no CLI subcommand exists for it, so no CLI boundary to fix |
| Installed/frozen entry points (`bytefray`, `bytefray-cli`, `bytefray-agent-designer`, `bytefray-replay-viewer`) | — | All resolve to the same `battle_engine.command`/`battle_engine.cli`/`app.agent_designer` modules already audited; no separate parser exists |
| Public Python API mirroring CLI policy | — | None found beyond the four `main()` functions above; `app/services/ruleset_options.py`'s `best_designer_ruleset`/`ruleset_supports_runtime_kinds` are a separate, pre-existing Designer-facing concern (§7), not touched |

## 7. Designer paths audited

All confirmed to already send an explicit `--ruleset` on every launch
(established in `v3.0.0-alpha2`, re-verified here, unchanged by this fix):

- **Simple** (`app/views/simple.py`) and **Advanced**
  (`app/views/advanced.py`) direct matches: `ruleset_id=selected_ruleset_id(self.ruleset)`.
- **Agent Development** test (`app/views/development.py`,
  `app/agent_designer.py:1150`): `--ruleset` built from
  `self.development.selected_ruleset_id()`.
- **Pairwise Evaluate** (`app/views/evaluation.py`,
  `app/services/designer_workflows.py`): `--ruleset` sent explicitly using
  `request.resolved_rules_compatibility_id`.
- **Group Evaluate**: fixed `--ruleset bytefray-rules-2 --group`, unchanged
  (v2-only by construction).

No Designer code changed. Its own combo-box default (`DESIGNER_RULESET_OPTIONS`,
v2 listed first) was already the product's intended converged behavior;
this fix brings the CLI's *omitted-flag* behavior into alignment with it,
rather than the reverse.

## 8. VM compatibility

Verified directly (smoke matrix, §21 below, plus focused tests):

| Scenario | Result |
|---|---|
| All-VM, omitted `--ruleset` | `bytefray-rules-1` (unchanged) |
| All-VM, explicit `bytefray-rules-1` | `bytefray-rules-1` (unchanged) |
| All-VM, explicit `bytefray-rules-2` | existing clean rejection (`RulesetRuntimeUnsupportedError`, "Python entrants only") |
| Mixed Python/VM, omitted `--ruleset` | existing clean rejection (`UnsupportedMatchCompositionError`, "all VM entrants or all Python entrants") — Ruleset-independent, fires before Ruleset resolution matters |

No VM/blob workflow requires a new mandatory flag as collateral damage of
this fix.

## 9. Redcode/pMARS isolation

`cli.py`'s `--mode redcode94` branch returns before any of the new
resolution code executes (`_requested_entrant_kind`/`resolve_omitted_ruleset_id`
are called later in `main()`, strictly after the redcode94 branch's own
early `return 0`) — structurally unreachable, not merely untested. No
Redcode/pMARS text or artifact field was changed. Extended
`test_pmars.py::test_successful_pmars_match_writes_summary_but_no_replay`
with explicit assertions that `result.json`'s `ruleset_id` stays `None`
and `summary.json` never gains a `ruleset_id` key; `test_ruleset_persistence.py`'s
existing pre-fix coverage of the same guarantee is unmodified and still
passes.

## 10. Evaluation identity and resume

- The resolved Ruleset id remains part of canonical evaluation identity
  exactly as before (`EvaluationRequest.resolved_rules_compatibility_id`
  feeds `_evaluation_id`'s hash payload unchanged) — an evaluation whose
  CLI omission now resolves to v2 gets a genuinely different
  `evaluation_id` than the historical v1 one would have, which is the
  correct, intended effect of a real methodology change.
- **Resume/retry safety, verified structurally, not merely asserted:**
  because the resolved Ruleset participates in `evaluation_id`'s hash, a
  pre-fix v1 evaluation and a post-fix omitted-Ruleset (now v2) rerun of
  the nominally same command compute *different* `evaluation_id`s and
  therefore different state directories — `--retry-failed` against the new
  command can never find, and so can never touch or reinterpret, the old
  v1 evaluation's durable state. No implicit-v1 evaluation can be silently
  resumed as v2.
- Explicit historical artifacts are unaffected: an evaluation/preset that
  already names `bytefray-rules-1` explicitly resolves identically before
  and after this fix (`resolve_evaluation_ruleset_id`'s explicit-v1 branch
  is untouched).
- Workers remain execution-only; no schema bump was necessary
  (`IDENTITY_VERSION`/`SCHEMA_VERSION` and their v2 counterparts are all
  unchanged constants).
- Tournament resume has an equivalent, pre-existing safety net:
  `tournament_id` does not itself include `ruleset_id`, but
  `TournamentService.run`'s per-match `_resumed_result_mismatch` check
  recomputes each scheduled match's expected `canonical_match_id` from the
  *current* request's resolved Ruleset and compares it against the
  persisted result's own recorded `match_id`; a Ruleset change between runs
  is detected as `resumed_result_mismatch` (status `corrupted` without
  `--retry-failed`, or a clean fresh re-run under the new Ruleset with
  `--retry-failed`) rather than silently blended into standings. This
  mechanism is pre-existing and was not modified by this fix — it was only
  verified to still correctly cover the new scenario.
- **Verified live, not just by code inspection** (RC2 qualification pass,
  §21 below): a tournament was run explicitly under `bytefray-rules-1`
  (simulating a pre-fix artifact), then the identical nominal command was
  re-run with `--ruleset` omitted (now resolving to v2). The old match was
  correctly reported `status: corrupted`, `error_code:
  resumed_result_mismatch`, excluded from standings (0 played for both
  entrants) — never silently reinterpreted as a v2 result. `--retry-failed`
  then produced a clean, fresh `bytefray-rules-2` result for that match.

## 11. Tournament behavior

Audited separately, since `tournament_cli.py` has its own parser and does
not share `cli.py`'s per-slot resolution machinery. `_resolve_entrant`
already produces a `MatchEntrant` with `.kind` set before `TournamentRequest`
is constructed, so no chicken-and-egg problem existed here (unlike `bytefray
run`, tournament entrant placement spacing does not depend on the resolved
Ruleset). Policy: Python-only roster → v2 by default; VM-only roster → v1
by default; mixed → existing rejection (unaffected, same
`UnsupportedMatchCompositionError` as §8). New focused CLI-level tests
cover both defaults end-to-end (§17).

## 12. Documentation changes

- **`README.md`** — corrected the "Rulesets" section's claim that "The CLI
  retains its backward-compatible Ruleset-v1 default when `--ruleset` is
  omitted" to describe the new runtime-aware policy.
- **`CHANGELOG.md`** — added an `## [Unreleased]` entry (no existing
  `[Unreleased]` section existed above the tagged `[3.0.0-rc1]` entry, which
  was left untouched) describing the fix in the suggested wording.
- **`docs/V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md`** and
  **`docs/V3_RC1_QUALIFICATION.md`** — both are historical qualification
  records (the latter tied to the immutable `v3.0.0-rc1` tag) that
  explicitly discussed and deferred this exact CLI default as a known,
  non-blocking gap. Per this repository's standing research-integrity
  practice, neither was edited in place; each received a dated,
  clearly-labeled addendum recording that the deferred question was later
  resolved, and how, without altering either document's own original
  findings, evidence, or verdict.
- **CLI `--help` text** — `cli.py`, `agent_test.py`, `tournament_cli.py`,
  and `agent_evaluation.py`'s `--ruleset` help strings all previously
  stated a flat `(default: bytefray-rules-1)`; all four now describe the
  runtime-aware policy in the repository's own established wording style.
  Redcode is not described as using either default (it uses neither).
- **`evaluation_presets.py`** — the `evaluation-presets show` subcommand's
  "ruleset: (not set -- ordinary default: bytefray-rules-1)" and "seeds:
  (not set -- ... ordinary single-seed default)" lines were stale under the
  new policy (evaluation entrants are always Python) and were corrected.
- **`docs/COMPATIBILITY.md`**, **`docs/RULES.md`**, **`docs/RULES_V2.md`**,
  **`docs/AGENT_AUTHORING.md`**, and every `docs/V1_*`/`docs/V2_*`/other
  `docs/V3_PHASE*` historical report were audited (`grep` for
  omitted-Ruleset/default-Ruleset language) and found to describe either
  (a) the unchanged deep library-level `resolve_evaluation_ruleset_id`/
  `MatchRequest` default, which is still completely accurate, or (b)
  historical, point-in-time state that must not be rewritten. None
  required a correction beyond the two addenda above.

## 13. Regression tests

All new/updated tests below were run and pass (see §14).

**New, minimum-required coverage (governing task §17):**

| Scenario | Test |
|---|---|
| Python, omitted `--ruleset` → v2 | `test_cli_characterization.py::test_ruleset_flag_omitted_defaults_to_v2_for_python_entrants` |
| Python, explicit v1 → v1 | `test_cli_characterization.py::test_ruleset_flag_explicit_v1` (VM-agent coverage, pre-existing) and `test_agent_test.py::test_cli_ruleset_flag_explicit_v1_succeeds_and_prints_identity` (new, Python-agent coverage) |
| Python, explicit v2 → v2 | `test_cli_characterization.py::test_ruleset_flag_explicit_v2_python_succeeds` (pre-existing) |
| VM, omitted → v1 | `test_cli_characterization.py::test_ruleset_flag_omitted_defaults_to_v1_for_vm_entrants` (renamed from `..._defaults_to_v1` for clarity; behavior unchanged) |
| VM, explicit v1 | covered by the same test above and `test_ruleset_flag_explicit_v1` |
| VM, explicit v2 | `test_cli_characterization.py::test_ruleset_flag_explicit_v2_vm_fails_cleanly_with_no_artifacts` (pre-existing, unaffected) |
| Mixed runtimes | `test_cli_characterization.py::test_ruleset_flag_omitted_mixed_runtime_fails_cleanly` (new) |
| Redcode isolation | `test_pmars.py::test_successful_pmars_match_writes_summary_but_no_replay` (extended, §9) |
| `agents test` omitted → v2 | `test_agent_test.py::test_cli_ruleset_flag_omitted_defaults_to_v2` (renamed/rewritten from `..._defaults_to_v1`) |
| `agents evaluate` omitted → v2 | `test_agent_evaluation.py::test_cli_default_seed_is_standard_v2_seeds_when_ruleset_omitted`, `test_cli_dry_run_omitted_ruleset_defaults_to_v2_matrix`, `test_cli_json_full_run_omitted_ruleset_includes_capture_by_default` (all new) |
| `tournament` Python-only omitted → v2 / VM-only omitted → v1 | `test_tournament_service.py::test_cli_ruleset_omitted_defaults_to_v2_for_all_python_roster`, `..._defaults_to_v1_for_all_vm_roster` (new) |

**Gameplay-level regression proof (governing task §18):**
`test_default_python_agents.py::test_cli_omitted_ruleset_python_match_reaches_core_capture`
runs the real `agents test raider --opponent claimer --seed 1 --ticks 400`
CLI invocation with **no `--ruleset` at all**, then asserts on the
persisted `result.json`: `ruleset_id == "bytefray-rules-2"` **and** at
least one entrant's `termination_reason == "core_captured"` — mechanical
proof that omitted-Ruleset CLI gameplay now executes real Ruleset-v2
vulnerable-core semantics, not merely that a parser string changed. This
reproduces v3.0.0-alpha2's own documented capture evidence (raider
captures claimer's core at tick 182 of 400, seed 1) byte-for-byte, but via
a command that never names a Ruleset.

**Existing tests updated for the new default (all were asserting the old,
now-incorrect, v1-by-omission behavior; each was either pinned to an
explicit `--ruleset bytefray-rules-1` — where the test's real purpose is
unrelated to Ruleset defaulting — or rewritten to assert the corrected
v2-by-default behavior with a new sibling test added for the v1 case where
useful):** `test_agent_test.py` (1 renamed), `test_agent_evaluation.py` (2
pinned + 2 new siblings), `test_agent_evaluation_behavior.py` (1 pinned),
`test_agent_evaluation_orientation.py` (2 pinned), `test_agent_evaluation_parallel.py`
(1 pinned), `test_agent_evaluation_presets.py` (7 pinned via an explicit
`"ruleset": "bytefray-rules-1"` preset field). No test was weakened or
deleted; every pinned test keeps its full original assertion, made
explicit about the Ruleset it depends on instead of silently inheriting a
default that changed out from under it.

## 14. Full validation

| Gate | Result |
|---|---|
| Frozen benchmark population (`verify_population(load_population())`) | **9/9 match, 0 drift** — before and after (this fix touches no starter/reference agent source) |
| 11-starter product smoke matrix (§21 below) | **11/11 pairs resolved the expected Ruleset** (7 Python pairs → v2, 4 VM pairs → v1) |
| Focused Ruleset/CLI/evaluation/tournament/placement tests (`-k "evaluation or agent_test or cli or tournament or ruleset or placement"`) | **pass** (after fixing the ripple-effect test updates in §13; two spurious failures from an accidental concurrent-pytest `.pytest-tmp` collision during investigation were confirmed non-reproducible in isolation) |
| Full default suite (`pytest`, `-m "not gui"`, all three default testpaths: `_legacy/tests`, `engine/tests`, `client/tests`) | **2375 passed, 14 skipped, 2 deselected** (0 failed) |
| Explicit GUI suite (`pytest tests/ -m ""`, real PySide6 6.11.2) | **226 passed, 1 skipped** (0 failed) |
| ruff check . | **All checks passed** |
| mypy `engine/src/battle_engine` | **Success: no issues found in 86 source files** |
| mypy `client/src/battle_client` | **Success: no issues found in 12 source files** |

Windows-specific packaging tests (`engine/tests/test_windows_packaging_spec.py`)
are part of the default suite above (this box is Windows) and are included
in its 2375-passed count with no failures. No CI run was triggered by this
task; per repository precedent, both Linux and Windows are covered in
normal CI (`.github/workflows`), and this task's own execution happened
entirely on the documented Windows development environment (see
`CLAUDE.md`).

## 15. Frozen baseline

Before and after this change: **9/9 pinned members match, zero drift.**
`battle_engine/data/benchmarks/v2_baseline.json` was not opened for
writing at any point; this is a default-selection policy fix with no
starter/reference agent source change.

## 16. Compatibility

Unchanged by this fix:

```text
Software:         Bytefray 3.x
Ruleset v1:        bytefray-rules-1, semantics unchanged
Ruleset v2:        bytefray-rules-2, semantics unchanged
Agent API:         v1, unchanged
Result schema:     v1, unchanged
Replay schema:     v3, unchanged
Python entrants:    Ruleset v1 or Ruleset v2 (unchanged)
VM/blob entrants:   Ruleset v1 only (unchanged)
Redcode/pMARS:      external, no Bytefray Ruleset (unchanged)
Historical/alpha
  Ruleset artifacts: unchanged; not reachable from any product CLI choice
```

The only thing that changed is **which Ruleset a product CLI resolves to
when the user does not name one**, for the subset of invocations where
every entrant is Python.

## 17. RC impact

**Classification: RC defect — default product gameplay inconsistency**, as
anticipated by the governing task. No engine semantic defect exists;
explicit Ruleset selection worked correctly before this fix and is
unchanged by it. The defect was that a new CLI Python user received
materially different gameplay from a Designer user for the same nominal
action, with core capture entirely absent from the CLI's default game.

**This implementation fully resolves that inconsistency** for the
CLI-vs-Designer convergence question: an ordinary omitted-Ruleset
Python-agent match now resolves to Ruleset v2 through either front end.
VM/blob convenience, mixed-runtime rejection, Redcode/pMARS isolation,
evaluation/tournament resume safety, and every explicit-Ruleset code path
are all preserved exactly as they were.

## 18. RC2 recommendation

Version changes this correction would require, **not made by this task**:

| Axis | Current (RC1) | Expected at RC2 |
|---|---|---|
| Git tag | `v3.0.0-rc1` | `v3.0.0-rc2` |
| PEP 440 (`pyproject.toml`) | `3.0.0rc1` | `3.0.0rc2` |

Recommended RC2 qualification scope beyond a normal re-qualification pass:
re-confirm this fix's regression suite, re-run the frozen-population and
11-starter smoke matrix, and re-verify (as this task did) that Designer
behavior remains explicit and unregressed. No new feature, agent, or
gameplay mechanic is implicated.

---

## 19. Verdict

### DEFAULT-RULESET DEFECT FIXED — READY FOR RC2 QUALIFICATION

This document does not itself qualify `v3.0.0-rc2` — that requires a
separate, dedicated release-candidate qualification pass once (and if)
RC2 is authorized.

## 20. Commit

Committed locally on `v3.0-development` at `13798b4` ("fix: default Python
CLI gameplay to ruleset v2"), two commits ahead of the still-untouched
`v3.0.0-rc1` tag (`ad5ff8a5`). Per explicit authorization from the user,
the branch was then pushed to `origin` and a narrow, adversarial RC2
qualification pass (§21) was run against the exact pushed candidate
commit — the actions below happened after publication of this section's
original text, and are recorded here rather than by editing the verdict
above.

## 21. RC2 qualification pass (narrow, adversarial around this fix only)

Run against candidate `2e9ef51` (`docs: record the RC1 default-Ruleset-
defect fix's own commit hash`, HEAD of `v3.0-development` after push). No
feature work was added; this pass exists to prove the corrected default
policy did not disturb the otherwise-qualified RC1 product.

| Step | Result |
|---|---|
| Push `v3.0-development` to `origin` | Clean fast-forward, `5995dfc..2e9ef51` |
| CI on the exact candidate commit (GitHub Actions run [33278290827](https://github.com/libertaine/Bytefray/actions/runs/33278290827)) | **success**, all 6 jobs: `test-linux-core` (3.10, 3.11, 3.12, 3.13), `build-linux-wheel`, `build-windows-exe` |
| Windows build (`tools/build_win.ps1`) | Success — all four frozen apps (`bytefray`, `bytefray-cli`, `bytefray-agent-designer`, `bytefray-replay-viewer`) built; the script's own built-in GUI-import/startup smoke and `agents create` smoke both passed |
| Explicit omitted/explicit Ruleset matrix, run against the **frozen `bytefray.exe`** (not source) | **10/10 checks passed**: Python-only omitted → v2 (2 pairs), Python explicit v1 → v1, Python explicit v2 → v2, VM-only omitted → v1 (2 pairs), VM explicit v1 → v1, VM explicit v2 → clean rejection, mixed omitted → clean rejection, `agents test raider --opponent claimer --seed 1 --ticks 400` (no `--ruleset`) → `ruleset: bytefray-rules-2`, `termination: last_agent_standing` at tick 182/400 — the exact alpha2 capture evidence, reproduced from the packaged executable |
| Evaluation/tournament resume check, live (not just code inspection) | See §10's added bullet: a `bytefray-rules-1` tournament artifact, re-targeted by an omitted-`--ruleset` rerun (now v2), was correctly reported `corrupted`/`resumed_result_mismatch` and excluded from standings; `--retry-failed` then produced a clean fresh `bytefray-rules-2` result. No silent v1→v2 reinterpretation occurred |
| Windows installer build (`ISCC.exe tools/installer.iss`, Inno Setup 6) | Successful compile, `dist/installer/Bytefray-Setup-3.0.0-rc1.exe` (~102.8 MB, consistent size with prior builds); confirmed `raider`/`sentinel` present in all three qualifying frozen trees (`bytefray`, `bytefray-cli`, `bytefray-agent-designer`) |
| Installer live install/uninstall lifecycle (UAC-elevated) | **Not attempted** — same structural limitation this repository's own RC1/alpha1/alpha2 qualification records already disclosed across three prior releases (no interactive UAC approval available from this kind of session); this fix touches no packaging-relevant file (no new starter agent, no new data file, no spec change), so it carries no new risk on this axis beyond what RC1 already qualified |

**Local build-artifact note:** `dist/installer/Bytefray-Setup-3.0.0-rc1.exe`
was overwritten locally by this pass's installer build (version was not
bumped — see §18/§22). `dist/` is gitignored and this is a transient local
build directory only; the actual published `v3.0.0-rc1` GitHub Release
asset and its recorded SHA-256 (`V3_RC1_QUALIFICATION.md` §21) are
untouched.

**Version bump and tag/publish were deliberately not performed in this
pass** — both remain gated on a separate, explicit go-ahead (§22).

## 22. RC2 version/tag — awaiting go-ahead

Per §18's recommendation, `v3.0.0-rc2` / `3.0.0rc2` version-bump,
release-prep, tagging, and publication are the only remaining steps in
the user's own RC2 flow. None were performed by this pass. A separate,
explicit authorization is required before proceeding to that step.
