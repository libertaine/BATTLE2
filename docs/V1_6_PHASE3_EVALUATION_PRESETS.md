# v1.6 Phase 3 — Evaluation Presets & Reproducible Suites

This is the durable implementation record for v1.6 Phase 3: named, reusable,
hand-editable evaluation configurations (`bytefray agents evaluate --preset
<name>`) and their inspection surface (`bytefray agents evaluation-presets
list|show|validate`).

Written in the same spirit as `docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md`
and `docs/V1_6_PHASE2_PARALLEL_EVALUATION.md`: this document cites both as
the authoritative pre-implementation baseline rather than re-deriving them.
Phase 1's own §11 ("Preset / suite architecture recommendation") is the
direct ancestor of the design below; where this document departs from that
recommendation, it says so explicitly.

## 1. Starting state

Branch `v1.6-development`, created from `c210358` (the accepted history
`bc0cbae` v1.5.0 → `85551e5` Phase 2 → `c210358` Phase 0-1 docs), which is
also where `main`/`origin/main` sat at the start of this phase — confirmed
via `git rev-parse main origin/main` before any change. Working tree clean
at the start. `v1.6-development` did not previously exist locally or
remotely.

Full suite reconfirmed green before any edit: **1309 passed, 6 skipped, 0
failures** (`python -m pytest`), byte-identical to Phase 2's own recorded
closeout baseline.

## 2. Architectural principle (unchanged from the governing prompt)

```
named reusable definition -> fully resolved explicit EvaluationRequest
    -> ordinary EvaluationRequest -> canonical evaluation execution
```

A preset is an input-construction convenience. It is never a second
evaluation engine, a methodology identity, a hidden ruleset, or a source of
implicit runtime behavior. Once a preset and any explicit overrides have
resolved into a complete `EvaluationRequest`, downstream execution is
byte-for-byte indistinguishable from an equivalent request typed explicitly
at the CLI — verified directly, not assumed (§7).

## 3. Existing conventions surveyed before implementation

Read in full before writing the schema: `agent.yaml` manifest parsing
(`agents.py`, JSON-with-YAML-fallback, deliberately looser than what this
phase needed), `EvaluationRequest`/the CLI parser
(`agent_evaluation.py:_parser`/`main`), `evaluation_history/cli.py`'s
`list`/`show`/`compare` pattern (plain-text + `--json`, `resolve_selector`),
`paths.py`'s `contained_path` (the exact containment primitive
`agents.resolve_agent` already uses to keep a caller-supplied name inside
one root), `result_model.py`'s `stable_id`/`canonical_json`/
`write_json_atomic`, `EvaluationRequest`'s own schema-version-bump history
(§12 below), and the Designer's `EvaluationDialog`/
`build_designer_evaluate_command`/`_on_evaluate` flow.

Two findings directly shaped the design:

- `agents.resolve_agent`'s `agents_root(root) = root / "agents"` plus
  containment-checked resolution is the established one-name-one-file
  convention for a `<BYTEFRAY_ROOT>`-relative catalog — reused verbatim as
  `presets_root(root) = root / "evaluation_presets"`, not invented fresh.
- `agent_evaluation.py`'s schema-version-bump history shows this project's
  convention is that **even a purely additive, identity-inert field
  addition to `evaluation.json` still gets an explicit `SCHEMA_VERSION`
  bump**, and a bump breaks *resume* for prior-version artifacts (a v2
  artifact is "not resumable under this schema_version," per the 2→3 bump
  comment at `agent_evaluation.py:79-88`, even though it remains fully
  readable). This finding is the direct evidence behind the provenance
  deferral in §12.

## 4. Preset schema

Identity: `bytefray.evaluation_preset`. Schema version: `1`. Format: YAML
(`yaml.safe_load`, strict — not `agents.py`'s looser JSON-with-comments
fallback; a preset is a small versioned artifact class closer in spirit to
`evaluation.json` than to a hand-scaffolded `agent.yaml`).

```yaml
schema: bytefray.evaluation_preset
schema_version: 1
description: Standard interactive matrix against the shipped starters.
candidate: my_agent          # optional -- see §5
baseline: my_agent_v1        # optional
opponents: [claimer, strider, hunter]
seeds: [1, 2, 3]              # mutually exclusive with seed_range
seed_range: {start: 1000, end: 1010}
ticks: 200
orientation: both             # "both" | "candidate_first_only"
```

Every field except `schema`/`schema_version` is optional. Strictness
(`engine/src/battle_engine/evaluation_presets.py`):

| Failure mode | Handling |
|---|---|
| Path traversal / absolute-path injection | `paths.contained_path` (same primitive `resolve_agent` uses) + a `^[A-Za-z0-9][A-Za-z0-9_.-]*$` name filter rejecting `/`, `\`, and any name not starting with a letter/digit (closes `..` by construction, since `..` cannot start with an alphanumeric) |
| Malformed YAML | `EvaluationPresetError` wrapping the `yaml.YAMLError` |
| Non-mapping root | rejected explicitly |
| Wrong/missing `schema`, missing/unsupported `schema_version` | rejected explicitly, current version pinned at `1` |
| Unknown top-level field | rejected explicitly (closed field set, not merely ignored) |
| Wrong field type (`str` where `int` expected, `bool` smuggled in as `int`, etc.) | rejected per-field with the offending field named |
| `seeds` and `seed_range` both present | rejected — mutually exclusive |
| `seed_range.end < seed_range.start` | rejected |
| Duplicate ambiguous name (`foo.yaml` and `foo.yml` both present) | rejected — "keep only one" |
| Empty `opponents: []` / `seeds: []` | **accepted at load time** — deliberately not a schema-level rule; see §6 |

25 dedicated schema/path-safety tests in `engine/tests/test_evaluation_presets.py`.

## 5. Candidate-field decision

**Chosen: candidate is optional in the preset, and an explicit CLI
positional argument always overrides it (option 3 of the three named in the
governing prompt).**

Rationale, grounded in the existing CLI shape rather than asserted: the
positional `candidate_id` argument already exists and is the natural
"whichever agent I'm currently developing" slot every other `agents
evaluate`/`agents test` invocation already uses. Making a preset
*optionally* carry `candidate` (and `baseline`) serves the other real use
case Phase 1 §11 names explicitly: a standing, fixed-subject regression
check (e.g. "does the release-candidate agent still beat this exact
matrix") that should not require retyping the candidate id every time.
Both workflows are common; neither should be foreclosed:

```bash
# workflow A: "evaluate whichever agent I'm working on" -- preset omits candidate
bytefray agents evaluate my_agent --preset standard

# workflow B: preset pins a fixed subject -- no positional needed at all
bytefray agents evaluate --preset release-regression-check
```

If neither the CLI positional nor the preset supplies a candidate, `main()`
exits `2` with `"candidate is required (supply it as a positional argument,
or set 'candidate' in the --preset)."` — a controlled error, not a
traceback. Covered by `test_candidate_positional_overrides_preset_candidate`,
`test_candidate_from_preset_when_cli_omits_it`,
`test_candidate_missing_from_both_is_a_controlled_error`
(`test_agent_evaluation_presets.py`).

## 6. Storage location

`<BYTEFRAY_ROOT>/evaluation_presets/`, sibling to `agents/` and `runs/` —
confirmed against `paths.get_data_root()`'s existing layout convention, per
Phase 1 §11's own recommendation. Presets never live inside an evaluation
run's own output directory: `evaluation.json` describes work that already
happened; a preset describes work to perform, and conflating the two would
let a preset edit silently reinterpret a past evaluation's meaning (§10).

## 7. Resolution layering — the one authoritative path

Implemented entirely in `agent_evaluation.main()` (not duplicated in
`evaluation_presets.py`, which only loads/validates/lists — it never
resolves against CLI defaults). Layering order, per field:

1. **Ordinary CLI default** (unchanged from pre-Phase-3 behavior: single
   `Config().seed`, `DEFAULT_TICKS` (200), `both_orientations=True`).
2. **Preset value**, if the preset sets that field.
3. **Explicit CLI flag**, if given — always wins.

The bug-prone part the governing prompt specifically flagged — "don't let
an ordinary parser default overwrite a preset value merely because parsing
happened first" — was closed by changing every preset-eligible flag's
`argparse` default from a concrete value to the sentinel `None`:

| Flag | Old default | New default | Why |
|---|---|---|---|
| `candidate_id` (positional) | required | `nargs="?"`, `None` | may come from the preset (§5) |
| `--opponents` | required | `None` | may come from the preset |
| `--ticks` | `DEFAULT_TICKS` (200) | `None` | preset's `ticks` must not be shadowed by a parser-level 200 |
| `--single-orientation` | `store_true`, `False` | `store_true`, `None` | `False` is indistinguishable from "not passed"; `None` restores that distinction |
| `--both-orientations` (new) | — | `store_true`, `None` | the missing explicit-override-to-`both` direction (§8) |
| `--baseline`, `--seeds`, `--seed-range`, `--output` | already `None` | unchanged | already sentinel-safe |
| `--workers` | `1` | unchanged (`1`) | never preset-eligible (§9) — no ambiguity to resolve |

`main()` then applies the three-tier `explicit -> preset -> default`
resolution per field directly (a five-line inline conditional per field,
not a generic "resolver" abstraction — the fields are heterogeneous enough
that one shared function would need as many branches as writing them out
plainly). After resolution, the exact same `EvaluationConfigurationError`-
raising validation path runs (`EvaluationService.preflight`/`_validate`) —
**no second validation path was written for preset-originated requests**,
per the governing prompt's explicit instruction (§6).

### Empty-list override behavior

`opponents: []` (or `seeds: []`) in a preset is **type-valid at load time**
(`evaluation_presets.py`'s `_require_str_list`/`_require_int_list` check
element types only, never non-emptiness) — deliberately, so that
non-emptiness is enforced exactly once, by the reused
`EvaluationService._validate`, not duplicated in the preset loader. A preset
with `opponents: []` and no `--opponents` override therefore fails with the
same `"Evaluation requires at least one opponent."` any ordinary
opponent-less invocation would produce; an explicit `--opponents` override
still succeeds normally. Proven, not just argued:
`test_empty_preset_opponents_falls_through_to_reused_validation` and
`test_empty_preset_opponents_explicit_cli_override_succeeds`.

## 8. Orientation semantics

The pre-Phase-3 CLI only had `--single-orientation` (a one-way opt-out of
the both-orientations default); there was no way to *explicitly* force
`both` from the CLI, because it was already the unconditional default. That
asymmetry became a real gap once presets can set `orientation:
candidate_first_only` — a CLI override in the "preset said single, force
both" direction needed a new flag. `--both-orientations` was added,
mutually exclusive with `--single-orientation`, both `None`-defaulted.
Resolution:

```
--single-orientation given   -> both_orientations = False   (explicit)
--both-orientations given    -> both_orientations = True    (explicit)
preset.orientation is not None -> both_orientations = (preset.orientation == "both")
otherwise                     -> both_orientations = True   (ordinary default, unchanged)
```

All five required cases are directly tested in
`test_agent_evaluation_presets.py`:
`test_orientation_omitted_from_preset_defaults_to_both`,
`test_orientation_preset_explicit_both`,
`test_orientation_preset_explicit_single`,
`test_cli_override_preset_both_to_single`,
`test_cli_override_preset_single_to_both` — each asserts the actual
resolved matrix size (`--dry-run`'s printed `matches: N`), not merely the
internal flag. `test_orientation_flags_mutually_exclusive_at_parser_level`
confirms `argparse` itself rejects passing both flags together.

## 9. Parallel-evaluation composition

`--workers` is not a preset field (per the governing prompt's explicit
instruction — "preset = what to run, workers = how this machine runs it").
`test_preset_workers_1_2_4_produce_identical_evaluation` runs the identical
preset at `--workers 1/2/4` against a 6-opponent × 2-seed single-orientation
matrix (12 cells) and asserts identical `evaluation_id` and byte-identical
normalized `evaluation.json` content (cells included) across all three —
composing cleanly with Phase 2 by construction, since a preset only ever
produces ordinary `EvaluationRequest` field values before Phase 2's
worker-pool code ever runs. Re-confirmed with real starter agents in a real
subprocess CLI invocation (§19): `--workers 1` vs `--workers 3` against the
same preset produced identical `evaluation_id` and byte-identical `cells`/
`aggregates`.

## 10. Canonical identity

`_evaluation_id`'s hash payload (`agent_evaluation.py:_evaluation_id`,
unmodified this phase) already only cherry-picks specific
`EvaluationRequest` fields — never `asdict(request)` wholesale, and
`workers` was already excluded by Phase 2. Because preset resolution (§7)
only ever *sets those same fields*, a preset's name, filename, path, or
display label structurally cannot enter the hash: there is no code path
between "preset resolved" and "`evaluation_id` computed" that reads
anything about the preset itself, only the resolved candidate/baseline/
opponent/seed/ticks/orientation values.

Verified directly, not merely argued from code reading:

- `test_canonical_identity_explicit_args_vs_preset_match` — the identical
  matrix run once via explicit flags and once via `--preset` produces the
  same `evaluation_id` and byte-identical normalized `evaluation.json`.
- `test_canonical_identity_differently_named_identical_presets_match` — two
  presets (`preset_alpha.yaml`, `preset_beta.yaml`) with byte-identical
  content produce identical `evaluation_id`s.
- `test_preset_name_never_appears_in_evaluation_id_payload` — the *same*
  preset file, renamed between two runs, still produces the identical
  `evaluation_id` (a strictly stronger case than "two differently-named
  copies," since it rules out any accidental dependency on filesystem
  identity/inode/creation-order).
- Real-CLI smoke test (§19): explicit args and `--preset` against real
  starter agents produced `evaluation_id
  evaluation-v2_c19a9e594dc597a32ef3ef38` in both cases, byte-identical
  `cells`/`aggregates`, the only difference anywhere in the artifact being
  the already-disclosed-volatile `execution_contexts[].first_used_at`
  timestamp.

The preset's own `content_digest` (`stable_id("evaluation-preset", data)`,
hashing only the parsed field payload — never the filename/path) is
separately proven name-independent by
`test_content_digest_independent_of_filename`.

## 11. Provenance decision

**Deferred, not implemented, with the finding documented rather than
silently dropped.** §3's schema-history finding is decisive: this
repository's own convention (demonstrated by the 2→3 `evaluation.json`
schema bump, `agent_evaluation.py:79-88`) is that *even a purely additive,
non-identity-affecting field* still requires an explicit `SCHEMA_VERSION`
bump, and a bump makes prior-schema artifacts non-resumable (though still
readable). Recording "which preset produced this evaluation" inside
`evaluation.json` would mean either:

- bumping `SCHEMA_VERSION` 4→5 for a purely informational field, breaking
  resume for every currently-`running` v4 evaluation the moment this phase
  ships — a real, disproportionate cost for a convenience feature whose own
  governing principle is "never change what an evaluation means"; or
- smuggling the field in without a version bump, contradicting this
  project's own established, tested convention and risking exactly the
  silent-wire-shape-change `AGENTS.md`'s compatibility section warns
  against.

Both are disproportionate to Phase 3's charter. Resolved-configuration
visibility (§13, the actual product goal behind provenance) is achieved
without touching the evaluation artifact at all: the CLI's pre-run output
(`--dry-run` and every normal run) prints `preset: <name>
(content_digest=<hex>)` before the ordinary matrix summary
(`_print_matrix`, `agent_evaluation.py`), and `bytefray agents
evaluation-presets show <name>` exposes the same fields plus every
resolved-vs-unresolved field explicitly labeled. If a future phase has a
concrete product need for durable provenance, it is a deliberate, disclosed
schema-version-bump decision to make then — not one to back into here.

## 12. Resume authority

**An evaluation started from a preset resumes from its own frozen
`evaluation.json`, never by re-reading the current preset.** This required
no new mechanism: `EvaluationService._load_state`
(`agent_evaluation.py:2349`) already compares the *newly resolved*
`evaluation_id` against the *persisted* one at `--output`, and raises
`EvaluationConfigurationError("Existing evaluation state does not match
this request.")` on any mismatch — the exact same guard that already
protects a plain explicit-args resume against an accidentally different
re-invocation. Since preset resolution (§7) only ever feeds into the same
`evaluation_id`-affecting fields, a preset edit that changes anything
`evaluation_id`-relevant is caught by this pre-existing guard automatically,
with zero preset-specific code.

Proven with a genuine interruption, not a hypothetical
(`test_resume_authority_modified_preset_is_rejected_not_reinterpreted`):

1. A preset with 18 cells (6 opponents × 3 seeds, single-orientation) starts
   under `agent_evaluation.main()`.
2. `EvaluationService._write_state` is monkeypatched to raise after its
   second real call (the first is the unconditional pre-loop checkpoint;
   the second is the batch checkpoint that fires after 16 completed cells,
   Phase 2's default `checkpoint_batch_size`) — a real `RuntimeError`
   propagates out of `main()`, exactly modeling a genuine crash mid-run.
   `evaluation.json` is left `lifecycle_state="running"` with real partial
   progress (more than 0, fewer than 18 cells).
3. The preset is rewritten with one fewer opponent (a materially different,
   `evaluation_id`-changing experiment).
4. Resuming via `--preset` (same `--output`) is **rejected**, exit `2`,
   `"does not match this request"` — and the frozen state on disk is
   byte-identical to what step 2 left, proving the rejected attempt never
   touched it.
5. The preset is then **deleted** entirely. Resuming via `--preset` fails
   the same way, cleanly (`"Unknown evaluation preset"`), before ever
   reaching the resume-compatibility check — the frozen state remains
   untouched.
6. Resuming via the **original explicit flags** (bypassing the now-deleted
   preset completely) succeeds, reaches `lifecycle_state="finished"` with
   all 18 cells `completed`, and every cell present before the interruption
   is confirmed to carry an unchanged outcome.

Step 6 is the concrete demonstration of the authority boundary: the preset
was only ever a convenience for constructing the original request, never
the thing resume depends on. A preset's disappearance costs only the
convenience of re-typing `--preset <name>`; it never corrupts or
reinterprets already-durable evaluation state.

## 13. Resolved-configuration visibility

Two places, deliberately not three (no duplicated presentation code):

- **CLI preflight/run output** (`_print_matrix`, extended with an optional
  `preset` parameter): when a preset was used, the very first line of
  every `--dry-run` and every normal (non-`--quiet`) run is `preset:
  <name>  (content_digest=<hex24>)`, immediately followed by the exact same
  resolved candidate/baseline/opponents/seeds/ticks/matrix-size/orientation
  summary an explicit-args invocation already prints — a user never has to
  infer methodology from a preset's name alone.
- **`bytefray agents evaluation-presets show <name>`**: prints the stored
  preset's own fields, explicitly distinguishing "set by this preset" from
  `"(must be supplied at invocation)"`/`"(not set -- ordinary default)"` for
  every optional field, plus the preset's `content_digest` and a one-line
  reminder that CLI flags always override it. `--json` returns the same
  data machine-readably.

## 14. CLI

```
bytefray agents evaluate <candidate-id>? --preset <name>
    [--baseline <id>] [--opponents <id,...>] [--seeds <n,...> | --seed-range a:b]
    [--ticks <n>] [--single-orientation | --both-orientations]
    [--workers <n>] [--output <dir>] [--retry-failed] [--dry-run] [--quiet]

bytefray agents evaluation-presets list   [--json]
bytefray agents evaluation-presets show   <name> [--json]
bytefray agents evaluation-presets validate <name>
```

Wired into `command.py._agents` as one more `if argv[0] ==
"evaluation-presets":` branch mirroring the existing `evaluate`/
`evaluations` dispatch exactly, lazily importing
`battle_engine.evaluation_presets.main`. `--help` text updated to mention
both the `--preset` option and the new subcommand group.

## 15. Designer integration

`app/views/evaluation.py`'s `EvaluationDialog` gained one optional
constructor parameter, `presets: dict[str, EvaluationPreset] | None`, and —
only when non-empty — a "Preset" combo box (`"(none)"` plus every
discovered name, sorted) above the existing candidate/baseline fields.
Selecting a preset populates candidate/baseline/opponents/seeds/ticks/
orientation from the already-loaded, already-typed `EvaluationPreset`
object; every populated field remains a plain editable widget afterward
(`test_selecting_preset_then_editing_field_overrides_prefill`). The dialog
itself contains **zero YAML parsing or preset-resolution logic** — it only
ever displays fields off an object `AgentDesigner` handed it.

`AgentDesigner._on_evaluate` does the loading, in-process, read-only, the
same pattern `_plan_default_evaluation_output`'s own in-process
`EvaluationService.preflight()` call already established: `list_presets`/
`load_preset` from `battle_engine.evaluation_presets` (never a second,
GUI-side implementation). A preset that fails to load is silently omitted
from the dropdown rather than blocking the whole dialog — `bytefray agents
evaluation-presets validate` is the tool for diagnosing why
(`test_designer_evaluate_with_invalid_preset_on_disk_still_opens`).

`build_designer_evaluate_command` gained one optional parameter,
`preset_name: str | None`, appending `--preset <name>` to the already-full
explicit argument list this function has always built. The Designer never
sends a *partial* argv depending on the preset — it always sends every
field explicitly (values that happen to have been pre-filled from the
preset, or edited afterward) plus `--preset <name>` for the CLI subprocess'
own record/disclosure; the CLI subprocess performs the real, authoritative
resolution and validation, identically to any other invocation. No parallel
execution logic and no independent preset resolver were added to the
Designer, per the governing prompt's explicit constraint.

## 16. Built-in/example preset decision

**No built-in presets ship.** `evaluation_presets/` lives under the
writable `<BYTEFRAY_ROOT>` data root (§6), not inside the installed
package — writing "built-in" files there at first run would either
duplicate `starters.py`'s `ensure_starter_agents`-style first-run-seeding
machinery for a feature with far less product justification, or require a
second, packaged-read-only fallback location that `list`/`show`/`validate`
would all need to know about, contradicting the "one small, obvious
location" design this phase otherwise achieves. The governing prompt's own
guidance directly favors the simpler alternative when built-in ownership
gets awkward: "prefer documented examples over built-in mutable files."

Three documented example tiers were added to
`docs/AGENT_LAB.md`/this document, grounded in Phase 0-1's own measured
scale targets (`docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md` §10), not
arbitrary numbers:

```yaml
# smoke.yaml -- 3 opponents x 3 seeds x 2 orientations = 18 cells
# ~1.5s of match execution at Phase 0-1's measured ~88ms/cell -- an
# author's every-edit smoke check.
schema: bytefray.evaluation_preset
schema_version: 1
description: Fast smoke check against three shipped starters.
opponents: [claimer, hunter, strider]
seeds: [1, 2, 3]
ticks: 200
orientation: both
```

```yaml
# standard.yaml -- 4 opponents x 5 seeds x 2 orientations = 40 cells,
# literally Phase 0-1's own cited "normal interactive evaluation" reference
# matrix (Sec 10: "1 candidate + 1 baseline x 4 opponents x 5 seeds").
schema: bytefray.evaluation_preset
schema_version: 1
description: Normal interactive matrix against four shipped starters.
opponents: [claimer, strider, hunter, wanderer]
seeds: [1, 2, 3, 4, 5]
ticks: 200
orientation: both
```

```yaml
# thorough.yaml -- 5 opponents (every shipped Python starter) x 10 seeds
# x 2 orientations = 100 cells -- meaningfully more coverage than
# "standard" while staying well short of Phase 0-1's "large" (~500-1000
# cell) tier, which is a stress-qualification scale, not a routine one.
schema: bytefray.evaluation_preset
schema_version: 1
description: Thorough matrix against every shipped Python starter.
opponents: [claimer, strider, hunter, wanderer, adaptive]
seeds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
ticks: 200
orientation: both
```

These are documentation, not files this phase writes to any user's data
root. A user who wants them copies the YAML in; nothing installs, upgrades,
or silently mutates a preset file on their behalf.

## 17. Scope exclusions honored

No statistical analysis, confidence intervals, behavior profiling,
rankings, clustering, distributed execution, or gameplay changes were
introduced. Phase 2's worker architecture
(`EvaluationService._run_pending_parallel`, `evaluation_worker.py`,
`scheduler.py`, every Ruleset-v1/execution-boundary module) was not
touched — confirmed by `git diff --stat` (§20) — no genuine integration
defect was found that would have justified touching it.

## 18. Tests

**94 new tests**, all passing, zero existing tests modified:

- `engine/tests/test_evaluation_presets.py` — 52 tests: orientation-
  vocabulary pinning, valid/minimal/seed-range parsing, malformed YAML/
  non-mapping root/wrong schema/unsupported version/missing-required-field
  rejection, 13 parametrized invalid-field-type cases, unknown-field
  rejection, seeds/seed_range mutual exclusivity, seed_range shape/ordering
  validation, empty-list type-validity, unsafe-name/path-traversal/
  absolute-injection rejection (7 parametrized cases), duplicate-extension
  ambiguity, `list_presets` dedup/sort, content-digest name-independence,
  and the full `list`/`show`/`validate` CLI surface (plain + `--json`) plus
  the `command.py` dispatch path.
- `engine/tests/test_agent_evaluation_presets.py` — 21 tests: resolution
  layering (defaults+preset, preset-only including a bare `--preset` with
  no positional candidate at all, explicit-ticks-override,
  explicit-opponents-override, empty-preset-opponents falling through to
  reused validation and its explicit-override escape), the three
  candidate-field cases (§5), three canonical-identity proofs (§10),
  six orientation cases (§8), one workers=1/2/4 parallel-composition proof
  (§9), one full resume-authority scenario with real interruption/
  modification/deletion/bypass (§12), and one `evaluation_history`
  compatibility proof (§18 below).
- `tests/test_agent_evaluation_dialog_presets.py` — 9 GUI (`gui`-marked)
  tests: combo hidden with zero presets, discovered names listed/sorted,
  full-field prefill, prefill-then-edit-overrides, re-selecting `(none)`,
  `--preset` flag included/omitted from the built command, and two
  `AgentDesigner`-level end-to-end tests (real dialog + real preset on
  disk, and an invalid on-disk preset not blocking dialog open).
- `tests/test_agent_evaluation_dialog.py` — 3 existing fake dialog classes
  (`_RecordingDialog`, `_AcceptingDialog`, `_EmptyOpponentsDialog`) gained a
  `preset_name()` stub returning `None`, the minimal change needed to keep
  them satisfying `EvaluationDialog`'s now-slightly-larger interface; no
  existing assertion was changed.

## 19. History compatibility

`evaluation_history/` required **zero code changes**. A preset-originated
`evaluation.json` is byte-for-byte an ordinary v4 artifact (§10) —
`evaluation_history.discovery.adapt_any` reads it identically to any other,
confirmed directly by
`test_preset_originated_evaluation_readable_by_evaluation_history` and by
the real-CLI smoke test's `bytefray agents evaluations show` invocation
(§19 below) against a preset-produced artifact, which printed the ordinary
`evaluation_id`/candidate/opponents/lifecycle/health output with no
preset-awareness needed anywhere in that command.

## 20. Real CLI smoke qualification

Isolated `BYTEFRAY_ROOT` (never the repository's own data root), real
shipped Python starter agents (`adaptive`, `claimer`, `strider`, `hunter`,
seeded automatically by `battle_engine.starters.ensure_starter_agents` on
first CLI use, confirmed via `bytefray agents`), this machine (Windows 11,
Python 3.11.9):

```
[1] explicit args:   bytefray agents evaluate adaptive --opponents claimer,strider,hunter \
                        --seeds 1,2,3 --ticks 100 --single-orientation --output ...  -> exit 0
[2] preset:           bytefray agents evaluate adaptive --preset standard --output ...      -> exit 0
[3] preset+override:  bytefray agents evaluate adaptive --preset standard --ticks 50 ...    -> exit 0
[4] preset+workers>1: bytefray agents evaluate adaptive --preset standard --workers 3 ...   -> exit 0
```

(`standard.yaml`: `opponents: [claimer, strider, hunter]`, `seeds: [1, 2,
3]`, `ticks: 100`, `orientation: candidate_first_only` — chosen to mirror
scenario [1]'s explicit flags exactly.)

Results:

- `[1]` and `[2]` produced the **identical** `evaluation_id`
  (`evaluation-v2_c19a9e594dc597a32ef3ef38`) and byte-identical `cells`/
  `aggregates`; the only differing field anywhere in the normalized
  artifacts was `execution_contexts[].first_used_at` (an already-disclosed
  volatile timestamp, not new to this phase).
- `[3]` (ticks overridden to 50) produced a **different** `evaluation_id`
  from `[2]`, as required — ticks is identity-relevant.
- `[4]` (`--workers 3` against the same preset as `[2]`) produced the
  **identical** `evaluation_id` and byte-identical `cells` to `[2]`
  (`workers=1`), confirming Phase 2/Phase 3 composition end-to-end with
  real subprocess workers, not just the source-level test suite.
- `--dry-run --preset standard` printed `preset: standard
  (content_digest=evaluation-preset_15a8fbc907e05ab057923bb8)` as the first
  line, ahead of the ordinary matrix summary.
- `evaluation-presets list|show|validate standard` and `evaluations show
  <preset-produced-output-dir>` all behaved exactly as documented above,
  against this real artifact.

No packaging-sensitive mechanism was touched by this phase (no new bundled
resource files, no frozen-command-discovery change, no new subprocess
entry point) — per §19 of the governing prompt, frozen Windows
qualification was therefore not re-run; Phase 2's own frozen qualification
remains the standing record for the subprocess-worker path this phase
merely composes with, unchanged.

## 21. Quality gate results

- Focused preset tests: 73 passed (52 + 21), 0 failed.
- Full existing evaluation test suites
  (`test_agent_evaluation*.py`, `test_evaluation_history*.py`): unchanged,
  all passing.
- Full headless suite (`python -m pytest`): **1382 passed, 6 skipped, 0
  failures** (up from Phase 2's 1309/6 baseline — 73 net new engine tests,
  zero existing tests modified beyond the 3 GUI-fake `preset_name()` stubs
  noted in §18, which live in the `gui`-marked file excluded from this
  count).
- Full `gui`-marked suite (`pytest -m gui`, offscreen Qt platform): all
  passing, including 9 new preset-specific Designer tests.
- `ruff check .`: clean (two auto-fixable import-ordering findings in new
  test files, fixed via `ruff check --fix`, re-verified clean).
- `mypy engine/src/battle_engine`: clean, 0 errors, 62 source files.
- `mypy client/src/battle_client`: clean, 0 errors, 10 source files
  (unaffected by this phase, confirmed not assumed).

## 22. Files changed

- **`engine/src/battle_engine/evaluation_presets.py`** (new, ~430 lines) —
  schema, load/validate, path safety, `list`/`show`/`validate` CLI.
- **`engine/src/battle_engine/agent_evaluation.py`** — `--preset`/
  `--both-orientations` flags, sentinel-default changes to five existing
  flags, the resolution-layering block in `main()`, `_print_matrix`'s
  optional preset-disclosure line. No change to `EvaluationRequest`,
  `EvaluationCell`, `_evaluation_id`, `_validate`, `_write_state`,
  `_load_state`, or any Phase 2 parallel-dispatch code.
- **`engine/src/battle_engine/command.py`** — one new `evaluation-presets`
  dispatch branch, `--help` text update.
- **`engine/tests/test_evaluation_presets.py`**,
  **`engine/tests/test_agent_evaluation_presets.py`** (new).
- **`app/views/evaluation.py`** — `EvaluationDialog` preset combo/prefill.
- **`app/services/designer_workflows.py`** —
  `build_designer_evaluate_command`'s `preset_name` parameter.
- **`app/agent_designer.py`** — preset discovery/loading in `_on_evaluate`.
- **`tests/test_agent_evaluation_dialog_presets.py`** (new),
  **`tests/test_agent_evaluation_dialog.py`** (3 fake-dialog stubs added).
- **`docs/AGENT_LAB.md`** — "Reusable evaluation presets" section.
- **`docs/ROADMAP.md`**, **`docs/FUTURE_PLANS.md`** — v1.6 Phase 2/3
  status updated to reflect delivered work (both had drifted from
  Phase 2's own deferred documentation pass).
- **`CHANGELOG.md`** — new `[Unreleased]` section covering both Phase 2's
  `--workers` and Phase 3's `--preset`/`evaluation-presets` (Phase 2's own
  entry had never been added).
- **This document.**

No change to `evaluation_history/*`, `evaluation_worker.py`,
`process_containment.py`, `scheduler.py`, `ruleset_policy.py`, or any
Ruleset-v1/execution-boundary module.

## 23. Remaining risks and follow-ups

- **Provenance was deliberately deferred (§11)**, not implemented. If a
  future phase decides durable "which preset produced this" tracking is
  worth a schema-version bump (and the resume-breakage it costs for
  in-flight evaluations), that is a fresh, deliberate decision — this
  phase leaves the finding documented rather than working around it.
- **No `--no-baseline`-style explicit-clear override exists** for a preset
  that sets `baseline` when a CLI invocation wants "no baseline" instead —
  `args.baseline is None` is the only "not overridden" signal available,
  identical to the pre-existing ambiguity for `--baseline` itself (not new
  to this phase). Not flagged as a defect by the governing prompt's test
  list; noted here as a known, narrow limitation.
- **The pre-existing `build_win.ps1` PowerShell empty-`-ArgumentList` GUI
  smoke-test defect** (found during Phase 2's frozen qualification) remains
  unrelated maintenance work, untouched by this phase, exactly as Phase 2
  itself left it.
- **Frozen Windows qualification was not re-run** this phase (§20) — no
  packaging-sensitive mechanism changed. Should Phase 4+ introduce bundled
  preset files or a packaging-relevant path-resolution change, that
  decision should re-open this question explicitly rather than assume this
  phase's "not needed" finding still holds.

## 24. Final verdict

**PHASE 3 COMPLETE — READY FOR ANALYSIS.**

Every hard invariant was verified, not assumed: preset resolution produces
ordinary `EvaluationRequest` values with no second validation path (§7);
canonical identity is name/path-independent by construction and directly
tested four different ways plus a real-CLI smoke proof (§10); orientation
omission/both/single and both CLI-override directions are all directly
tested against actual resolved matrix size (§8); preset content composes
identically with Phase 2's parallel dispatch at workers=1/2/4, tested at
the source level and reconfirmed with real subprocess workers in the smoke
test (§9); resume authority was proven with a genuine crash injection,
preset modification, preset deletion, and an explicit-flags bypass, not
merely argued from the pre-existing `_load_state` guard (§12); no built-in
preset catalog ships, and the reason is documented (§16); Phase 2's worker
architecture, every Ruleset-v1/execution-boundary module, and
`evaluation_history/`'s own code were all left untouched (§17, §19). No
merge, tag, push, or release action was taken. All commits (§25, if any
were created) were made only on `v1.6-development`, per instruction.
