# Bytefray v2.0.0-beta1 Phase 2 — Product Execution Integration

This document records Beta1 Phase 2: making the permanent `bytefray-rules-2`
identity safely and deliberately usable through supported direct
product-execution workflows, with an authoritative Python-only runtime
boundary and no silent reinterpretation of existing Ruleset-v1 commands.
Phase 1 (`docs/V2_0_BETA1_PLAN.md`) froze the gameplay semantics; this phase
does not touch them. It is about *who is allowed to select which Ruleset,
through which CLI surface, and what happens when a requested Ruleset cannot
execute the entrants it was given* — execution/product integration, not
evaluation methodology, GUI work, or gameplay redesign.

## 1. Starting repository state

Verified before any change:

- branch `v2.0-beta1-development`, HEAD `58047a0b45361a0ab64471e672cf094a020ffa13`
  (Phase 1's final commit — `docs(v2.0-beta1): document Ruleset v2
  compatibility and beta plan`);
- `main` at `5593d287f95a24996bb3b105befbc625a00795db`, unchanged;
- `v2.0-development` at `ad67a0fe0778fdc40c804618e8ec5ea8ea9cf7d3`, unchanged;
- `origin/v2.0-development` at `151866c6d862fec4facb78596204861b26889b61`,
  confirmed **not** an ancestor of local HEAD (`git merge-base
  --is-ancestor` returned false) — untouched, unreconciled, as required;
- working tree clean (`git status --porcelain` empty).

## 2. Verified baseline

Because HEAD at Phase 2's start was exactly Phase 1's final commit, Phase
1's recorded baseline is legitimately the Phase 2 starting baseline — no
commit separates them. This was re-confirmed independently rather than
assumed: Phase 2's changes were `git stash`-ed mid-session and the full
suite was re-run against the untouched Phase-1 tree before restoring the
stash.

| Check | Result |
|---|---|
| `python -m pytest` (full) | **1628 passed, 6 skipped, 2 deselected, 0 failed** (199.07s) |
| `ruff check engine client` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 70 source files |
| `mypy client/src/battle_client` | Success: no issues found in 10 source files |

This exactly matches the committed Phase-1 baseline recorded in the
governing prompt, confirming no drift occurred between Phase 1's commit and
Phase 2's start.

## 3. Execution architecture map

```text
user input
  -> argparse (cli.py / agent_test.py / tournament_cli.py / agent_evaluation.py)
  -> agent discovery (battle_engine.agents.resolve_agent / builtins.SUPPORTED)
  -> runtime-kind resolution (per entrant: AgentSpec.kind "python" -> MatchEntrant.python(...);
     "builtin"/"blob" -> MatchEntrant(..., kind="vm") default)
  -> MatchRequest(entrants=..., ruleset_id=...)
  -> NativeMatchService.run(request)
       1. homogeneity check (all-VM or all-Python; UnsupportedMatchCompositionError)
       2. ruleset_policy = resolve_ruleset_policy(request.ruleset_id or BYTEFRAY_RULESET_ID)
       3. [Phase 2, new] ruleset_policy.unsupported_runtime_kinds(kinds) check
          -> RulesetRuntimeUnsupportedError if non-empty
       4. dispatch: _run_python_match(...) or _run_vm_match(...)
  -> result.json / replay.jsonl (_finalize_native_artifacts)
```

Four direct product workflows share this exact pipeline, all converging on
`NativeMatchService.run` as the one seam where entrant runtime kinds and the
resolved Ruleset policy are simultaneously in scope:

- `bytefray run` (`battle_engine.cli`) — direct single match, VM or Python,
  built-in/blob/discovered agents;
- `bytefray agents test` (`battle_engine.agent_test`) — Python-only
  development match, reused verbatim by `agents evaluate`'s per-cell
  executor and by Agent Lab;
- `bytefray tournament` (`battle_engine.tournament_service`) — homogeneous
  round-robin over the same `NativeMatchService`;
- `bytefray agents evaluate` (`battle_engine.agent_evaluation`) — calls
  `agent_test.test_agent(...)` per cell, never `MatchRequest` directly.

Agent Lab and Designer (`app/`) do not call any of this in-process at all —
every Designer match-launch/Agent-Lab-test action shells out to the exact
same CLI entry points above via `battle_engine.launchers.build_match_command`
/ `build_agents_command` and a `QProcess`/`Popen` subprocess. There is no
separate GUI-side match-construction code path to audit independently.

## 4. `MatchRequest` call-site audit

| Call site | File:line (pre-Phase-2) | Workflow | Ruleset exposure before Phase 2 |
|---|---|---|---|
| `cli.py::main` | `cli.py:661-668` | `bytefray run` (also what Designer's Run Match shells out to) | Not passed at all — always v1 |
| `agent_test.py::_test_agent` | `agent_test.py:372-384` | `bytefray agents test` (also Agent Lab's Test/rerun-in-Agent-Lab, and `agents evaluate`'s per-cell executor) | Plumbed as a `ruleset_id` kwarg on `test_agent()`, but `main()` never set it and no `--ruleset` flag existed |
| `tournament_service.py::TournamentService.run` (×2: resume-recompute and live-execute) | `tournament_service.py:242-248`, `305-311` | `bytefray tournament` | Not passed — `TournamentRequest` had no `ruleset_id` field at all |
| `agent_evaluation.py` (identity-preview helper only, not the executor) | `agent_evaluation.py:455-463` | Internal, not user-reachable | Hardcoded, irrelevant to product surfaces |

No `MatchRequest` construction exists anywhere under `client/src` or `app/`
— confirmed by repository-wide search.

## 5. Support matrix

| Runtime | Ruleset v1 | Permanent v2 | alpha1 / alpha11 |
|---|---|---|---|
| VM | supported, unchanged | **rejected** before execution (new, Phase 2) | dispatches successfully, mechanic inert (unchanged) |
| Python | supported, unchanged | supported | supported, unchanged |
| Mixed VM+Python | rejected (pre-existing `UnsupportedMatchCompositionError`, Ruleset-independent) | same pre-existing rejection fires first | same pre-existing rejection fires first |
| N-Python (3+) | supported (engine-generic) | supported (engine-generic) | supported (engine-generic) |

## 6. Authoritative validation seam

Implemented at `battle_engine.ruleset_policy.RulesetPolicy`:

```python
supported_runtime_kinds: frozenset[str] | None = None   # new field

def unsupported_runtime_kinds(self, kinds: Iterable[str]) -> frozenset[str]:
    if self.supported_runtime_kinds is None:
        return frozenset()
    return frozenset(kinds) - self.supported_runtime_kinds

RULESET_V2 = RulesetPolicy(
    ruleset_id=BYTEFRAY_RULESET_V2_ID, supported_runtime_kinds=frozenset({"python"})
)
```

`RULESET_V1`, `RULESET_V2_ALPHA1`, and `RULESET_V2_ALPHA11` all keep
`supported_runtime_kinds=None` (unrestricted) — their VM behavior is
byte-for-byte unchanged.

Invoked once, in `NativeMatchService.run` (`match_service.py`), immediately
after `ruleset_policy` is resolved and before either runtime is dispatched:

```python
ruleset_policy = resolve_ruleset_policy(_resolve_ruleset_id(request))
unsupported_kinds = ruleset_policy.unsupported_runtime_kinds(kinds)
if unsupported_kinds:
    raise RulesetRuntimeUnsupportedError(ruleset_policy.ruleset_id, unsupported_kinds)
```

**Rationale for this seam over the alternatives considered:**

- *CLI-only preflight* was rejected as the sole check — it would need
  duplicating across `cli.py`/`agent_test.py`/`tournament_cli.py` and would
  not protect any future caller (Designer in-process integration,
  evaluation v2 methodology in beta2) that bypasses the CLI.
- *`MatchRequest.__post_init__` validation* was rejected — a frozen
  dataclass's constructor has no clean way to reject "kind X is
  incompatible with Ruleset Y" without importing `ruleset_policy` into
  `match_service`'s dataclass definitions in a way that couples request
  *construction* to Ruleset *resolution* order (a `MatchRequest` can
  legitimately be constructed before its Ruleset is validated, e.g. for
  `canonical_match_id`'s identity-preview use in `agent_evaluation.py`).
- *`NativeMatchService.run`, after `kinds`/`ruleset_policy` are both
  already resolved* is the one point every production caller already
  passes through unconditionally, where both facts are already local
  variables, and where zero entrant execution or artifact I/O has occurred
  yet (`_run_python_match`/`_run_vm_match` are not called until after this
  check passes). This is also exactly where the pre-existing
  `UnsupportedMatchCompositionError` (mixed-runtime) check already lives,
  keeping both "is this composition legal at all" checks co-located.

The CLI still preflights via argparse `choices=` (rejecting an unregistered
Ruleset ID before it's even parsed into a string), but that is UX
convenience layered *above* this authoritative seam, never a substitute for
it — a direct Python caller bypassing the CLI entirely still gets the same
rejection from `NativeMatchService.run`.

## 7. Rejection semantics

`RulesetRuntimeUnsupportedError(ValueError)` (`match_service.py`, alongside
`UnsupportedMatchCompositionError`):

- `.ruleset_id`, `.unsupported_kinds` (sorted tuple), `.diagnostic`
  (`RuntimeDiagnostic(code="ruleset_runtime_unsupported", stage="configuration", ...)`);
- message: `Ruleset 'bytefray-rules-2' currently supports Python entrants
  only (requested runtime kind(s): vm). Use 'bytefray-rules-1' for VM
  entrants.`;
- raised before `_run_python_match`/`_run_vm_match`, before
  `replay_path.parent.mkdir(...)`, before any temp file is created —
  verified by `test_v2_vm_rejection_writes_no_replay_or_result` (asserts
  the run directory itself never comes into existence) and
  `test_v2_vm_rejection_executes_zero_instructions` (monkeypatches
  `match_service.Kernel` to raise `AssertionError` if constructed, proving
  zero VM instantiation).

**Ordering relative to the pre-existing mixed-runtime restriction**, chosen
deliberately: the homogeneity check (`kinds <= {"vm","python"} and
len(kinds)==1`) runs *first*, unconditionally, regardless of Ruleset. A
mixed VM+Python request under `bytefray-rules-2` therefore raises
`UnsupportedMatchCompositionError` ("Mixed VM/Python matches are not
supported") — the exact same message it would raise under v1 — never the
Ruleset-specific error. Only an *already-homogeneous* VM-only or Python-only
composition reaches the Ruleset-runtime check. This means the two
restrictions are structurally distinguishable by construction: a user never
sees `bytefray-rules-2` mentioned in a mixed-composition error, and never
sees "mixed VM/Python" mentioned in a Ruleset-v2-Python-only error. See
`test_v2_rejects_python_vs_vm_as_mixed_composition_not_ruleset_error` /
`test_v2_rejects_vm_vs_python_as_mixed_composition_not_ruleset_error`.

## 8. CLI commands changed

`--ruleset {bytefray-rules-1,bytefray-rules-2}` added to:

- `bytefray run` (`cli.py`);
- `bytefray agents test` (`agent_test.py`);
- `bytefray tournament` (`tournament_cli.py`).

All three use `argparse`'s `choices=` — an unrecognized value is rejected by
argparse itself (`invalid choice: ...`, exit 2) before any product code
runs; no prefix/case-insensitive/alias matching exists. Historical alpha
identities (`bytefray-rules-2-alpha1`, `bytefray-rules-2-alpha11`) are not
in the `choices=` list and so cannot be selected through any product CLI —
they remain reachable only through direct Python API calls (tests,
internal tooling), exactly as the governing task requires ("the public beta
product need not advertise alpha identities").

**Deliberately not changed:** `bytefray agents evaluate` — see §18.

## 9. `--ruleset` behavior

Default (omitted): `None` passed through to `MatchRequest`/`TournamentRequest`
/`test_agent()`, which already resolve `None` to `BYTEFRAY_RULESET_ID`
("bytefray-rules-1") exactly as before this phase.

## 10. Phase-2 default policy

**Ruleset v1 remains the default when `--ruleset` is omitted**, for every
command this phase touched. This is recorded as a deliberate beta-transition
compatibility policy, not the final 2.0 default: existing scripts and CI
invocations that never pass `--ruleset` continue producing identical
gameplay to before this phase; GUI/evaluation surfaces do not yet uniformly
support v2; the final 2.0 default is a decision for a later phase once every
primary product surface supports both Rulesets coherently.

## 11. v1 behavior

Byte-for-byte unchanged: `RULESET_V1.supported_runtime_kinds is None`, so
`unsupported_runtime_kinds` always returns an empty set for it — the new
check is a no-op for every v1 request, VM or Python. Confirmed by the full
regression suite (§16) and by `test_v1_vm_matches_still_execute_normally`
/`test_v1_python_matches_still_execute_normally`.

## 12. Permanent-v2 Python behavior

`bytefray-rules-2` with 2 or more Python entrants executes exactly as
before — same Vulnerable Core / Consistent Core Observability mechanics,
same artifact identity, same `canonical_match_id` hashing. The new check
never fires for an all-Python request (`unsupported_runtime_kinds({"python"})
== frozenset()`).

## 13. VM rejection behavior

See §7. Typed, pre-execution, no partial artifacts, distinguishable from
the mixed-composition error.

## 14. Mixed-runtime behavior

Unchanged from before Phase 2 for every Ruleset — see §7's ordering
discussion. `bytefray tournament`'s own separate, pre-existing per-tournament
homogeneity check (`TournamentService._validate`, checking the *entire
entrant roster* is single-kind before scheduling anything) is also
unaffected; it answers "is this tournament's own roster viable at all",
which is orthogonal to per-match Ruleset compatibility.

## 15. `agents test` workflow

Audited in full (`agent_test.py::_resolve_python_entrant`,
`_test_agent`). Both slots are *unconditionally* required to be `kind ==
"python"` — a non-Python agent is rejected with `agent_kind_unsupported`
before either entrant is even resolved into a `MatchEntrant`, **regardless
of which Ruleset was requested**. This means:

- `agents test` structurally can never construct a VM `MatchEntrant`, so
  `RulesetRuntimeUnsupportedError` can never actually be raised through this
  command today — the pre-existing, Ruleset-independent
  `agent_kind_unsupported` tool error already covers "VM involved + v2
  fails clearly and before match execution" for this specific workflow (see
  `test_non_python_tested_agent_rejected_even_with_explicit_v2`).
- Exception handling for `RulesetRuntimeUnsupportedError` was still added
  to `_test_agent`'s `except` chain (mirroring
  `UnsupportedMatchCompositionError`'s handling) for defense in depth, so a
  future change that loosens the Python-only requirement here would still
  fail closed with a clear tool error rather than an unwrapped
  `agent_test_internal_error`.
- `--ruleset` was added to the parser and threaded through `test_agent()`'s
  pre-existing `ruleset_id` kwarg (unused by `main()` before this phase).
- `DevelopmentTestOutcome` gained a `ruleset_id: str` field (defaulting to
  `BYTEFRAY_RULESET_ID`) so both the printed CLI output (`ruleset: ...`
  line) and any programmatic caller can see which identity actually ran,
  without re-deriving it.

## 16. Persisted v2 artifact identity

Confirmed end-to-end (source tree, §20, and installed wheel, §21):
`result.json`'s `ruleset_id` field and the replay header's `ruleset_id`
both read `"bytefray-rules-2"` for a v2 match, `"bytefray-rules-1"` for a
default/explicit-v1 match — no new plumbing was required, since
`ruleset_id` was already generic through `_finalize_native_artifacts`/
`canonical_match_id` since Phase 1/alpha.1.

## 17. Replay/inspection workflow

`agents test`'s printed hint (`Run 'bytefray replay --replay <path>' to
inspect it.`) was verified unchanged and still correct: `bytefray replay`
(`battle_client.cli`) takes no Ruleset argument at all — it reads
`ruleset_id` directly from the replay header it's pointed at. A v2-produced
replay was manually inspected via `bytefray replay --renderer headless`
(source tree) and played back its tick-by-tick scores/winner correctly with
no Ruleset re-specification required (§20). This preserves the exact
historical first-user fix `docs/ROADMAP.md`'s v0.10 Phase 5 entry
describes, and the governing task's explicit "do not regress it" instruction.

## 18. Evaluation deferral

`bytefray agents evaluate` (`agent_evaluation.py`) has **no** `--ruleset`
flag and was **not** given one. Its CLI parser was audited
(`agent_evaluation.py:2535-2620`) and confirmed to expose no Ruleset
selection surface today; `EVALUATION_RULES_COMPATIBILITY_ID =
BYTEFRAY_RULESET_ID` remains a hardcoded alias, and its per-cell executor
(`test_agent(...)`, reused from `agents test`) is called without ever
passing `ruleset_id=`, so every cell it runs resolves to
`"bytefray-rules-1"` unconditionally. Per the governing task's Phase 2G
("If the CLI does not expose Ruleset choice today: leave it v1"), no code
change was needed — only verification, added as
`test_evaluation_cells_always_execute_under_ruleset_v1` (asserts every
cell's own persisted `result.json` carries `ruleset_id ==
"bytefray-rules-1"`, not just the evaluation-level field) and
`test_evaluate_cli_has_no_ruleset_selection_flag` (asserts `--ruleset` is
absent from `--help`).

## 19. Designer/Agent Lab deferral

Audited fully (`app/agent_designer.py`, `app/services/engine.py`,
`app/services/engine_commands.py`, `app/services/designer_workflows.py`,
`battle_engine.launchers`). Confirmed:

- zero occurrences of "ruleset"/"Ruleset" anywhere under `app/`;
- every Designer match-launch and Agent-Lab-test action builds a CLI
  argument list and shells out via `QProcess`/`Popen` to the exact CLI
  entry points audited above — never an in-process `MatchRequest`/
  `NativeMatchService` call;
- none of those argument-list builders emit `--ruleset`, so every Designer/
  Agent-Lab-initiated match implicitly resolves to the CLI's own default
  (`bytefray-rules-1`) with **zero Designer code changes required**;
- the generic subprocess result-handling path (`EngineRunner.finished`
  signal, carrying only a return code plus combined stdout/stderr) already
  displays whatever text any CLI error prints — a
  `RulesetRuntimeUnsupportedError`'s clean `ERROR: ...` message (should a
  future Designer control ever pass `--ruleset bytefray-rules-2` with a VM
  agent) would render exactly like any other existing CLI error already
  does today, with no unhandled GUI traceback. No defensive Designer-side
  code was needed to reach this guarantee.

No Designer/Agent Lab source file was modified in this phase.

## 20. Source CLI smoke

All commands run from `engine/src`/`client/src` on `PYTHONPATH`, against a
fresh `BYTEFRAY_ROOT`:

```text
$ python -m battle_engine.cli --help
  ...shows --ruleset {bytefray-rules-1,bytefray-rules-2}...

$ python -m battle_engine.cli --a-type writer --b-type runner --ticks 5 --replay <path> --quiet
  exit=0; result.json ruleset_id == "bytefray-rules-1"

$ python -m battle_engine.cli --a-type alpha_py --b-type beta_py --ruleset bytefray-rules-2 --ticks 10 --replay <path> --quiet
  exit=0; result.json ruleset_id == "bytefray-rules-2"; winner recorded

$ python -m battle_engine.cli --a-type writer --b-type runner --ruleset bytefray-rules-2 --ticks 5 --replay <path> --quiet
  exit=2; stderr: "Ruleset 'bytefray-rules-2' currently supports Python entrants
  only (requested runtime kind(s): vm). Use 'bytefray-rules-1' for VM entrants."
  no replay/result/run-directory created at all

$ python -m battle_engine agents test alpha_py --opponent beta_py --ruleset bytefray-rules-2 --ticks 10
  exit=0; prints "ruleset: bytefray-rules-2"; prints a working
  "Run 'bytefray replay --replay <path>' to inspect it." hint

$ python -m battle_client.cli --replay <the v2 replay above> --renderer headless
  plays back tick-by-tick scores and the recorded winner correctly,
  no Ruleset argument needed

$ python -m battle_engine tournament writer runner --ruleset bytefray-rules-2 --ticks 5 --output <dir> --quiet
  exit=1 (non-completed match); tournament.json's one scheduled match
  recorded status="rejected", error_code="ruleset_runtime_unsupported";
  no matches/ subdirectory created at all
```

## 21. Wheel smoke

Built the current wheel with the repository's normal process
(`python -m build --wheel`), producing `bytefray-1.6.0-py3-none-any.whl`
(no version bump — out of scope for this phase). Installed into a fresh,
isolated venv with only the core (PyYAML-only, headless) extra, matching
`docs/LINUX_INSTALL.md`'s documented minimum. From the installed package,
not the source tree:

- `bytefray --version` → `Bytefray 1.6.0, Agent API v1, result schema v1,
  replay schema v3, Python 3.11.9`;
- `--help` correctly lists `--ruleset {bytefray-rules-1,bytefray-rules-2}`;
- v1-default match: exit 0, `result.json` `ruleset_id ==
  "bytefray-rules-1"`;
- explicit `--ruleset bytefray-rules-2` with two Python agents: exit 0,
  `result.json` `ruleset_id == "bytefray-rules-2"`, winner recorded;
- explicit `--ruleset bytefray-rules-2` with two VM built-ins (`writer`
  vs `runner`): exit 2, the same actionable error message as the source
  tree, zero artifacts written.

The wheel was not published; the isolated venv and build output were
deleted after the smoke pass. No installer/frozen-build qualification was
performed (explicitly out of scope for this phase).

## 22. Regression qualification

| Check | Result |
|---|---|
| New Phase-2 focused tests | 36 (see §23) |
| Full `python -m pytest` | **1664 passed, 6 skipped, 2 deselected, 0 failed** (206.34s) |
| Reconciliation | 1628 (§2 baseline) + 36 new = 1664 — exact, no unexplained delta |
| `ruff check engine client` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 70 source files |
| `mypy client/src/battle_client` | Success: no issues found in 10 source files |
| `git diff --check` | clean |
| Ruleset-v1 golden/equivalence (`test_ruleset_v1_equivalence.py`) | passing, unmodified |
| Permanent-v2 promotion equivalence (`test_ruleset_v2_promotion_equivalence.py`) | passing, unmodified — v2 Python match semantics untouched by this phase |
| Core Tracker (`test_v2_alpha8_core_tracker.py`) | passing, unmodified |
| alpha1 / alpha11 (`test_ruleset_v2_alpha1.py` / `test_ruleset_v2_alpha11.py`) | passing, unmodified, **plus** new coverage proving their VM dispatch-then-inert behavior is unchanged by this phase's new restriction |

Permanent-v2 Python match semantics were not touched by this phase (no
edit to `battle_engine.python_runtime`'s Vulnerable Core/observability
code, no edit to scoring/scheduling/termination) — the promotion-equivalence
corpus passing unmodified is the direct proof that Phase 2's dispatch/CLI
work did not alter accepted Python-match behavior.

## 23. New Phase-2 tests (36)

- `engine/tests/test_ruleset_v2_runtime_compatibility.py` (17 new): policy
  data-level checks, v2 accept/reject matrix (2-way and 3-way, VM/VM,
  VM/Python, Python/VM, mixed-vs-Ruleset error distinction), mutation
  safety (no replay/result/run-directory, zero VM instantiation), v1/alpha1/
  alpha11 unchanged-VM-behavior confirmation.
- `engine/tests/test_cli_characterization.py` (+6): `bytefray run`
  `--ruleset` default/explicit-v1/explicit-v2-Python/explicit-v2-VM-
  rejection/unknown-value/help-content.
- `engine/tests/test_agent_test.py` (+7): `test_agent()`/CLI `--ruleset`
  default/explicit-v2-artifact-identity/non-Python-agent-still-rejected-
  under-v2/CLI default/CLI explicit-v2/CLI unknown-value/CLI help-content.
- `engine/tests/test_tournament_service.py` (+4): `TournamentRequest`
  `ruleset_id` default/v2-VM-per-match-rejection-with-no-artifacts/CLI
  help-content/CLI unknown-value.
- `engine/tests/test_agent_evaluation_v2.py` (+2): every evaluation cell's
  own match artifact still records `bytefray-rules-1`; `--help` has no
  `--ruleset` flag.

## 24. Remaining Beta1 Phase-3 boundary

Explicitly not started by this phase (per `docs/V2_0_BETA1_PLAN.md` §7):
Replay v2 semantics (core status/capture events surfaced in replay-derived
data), HUD/status-model preparation. No replay schema, telemetry, or
Replay Viewer code was touched here.

---

# Support summary

- **v1** — VM and Python, fully unchanged.
- **Permanent v2** — Python entrants only, enforced authoritatively and
  fail-closed at `NativeMatchService.run`, before any execution or artifact
  write; VM entrants are rejected with a typed, actionable error.
- **alpha1 / alpha11** — historical, unrestricted, VM dispatch remains
  successful-but-inert exactly as before this phase; not advertised as
  ordinary product choices.
- **Mixed VM/Python** — rejected by the pre-existing, Ruleset-independent
  composition check, distinguishable by wording from the new Ruleset-v2
  restriction.
- **`agents evaluate`** — remains implicitly, exclusively v1; no accidental
  v2 evaluation is possible since no Ruleset selection surface exists.
- **Designer/Agent Lab** — unaffected, defaults to v1 through the CLI's own
  default, no code changes required.
