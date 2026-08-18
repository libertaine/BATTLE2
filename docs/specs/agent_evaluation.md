# agent_evaluation

**Module:** `engine/src/battle_engine/agent_evaluation.py` (new), with a
small, additive extension to `engine/src/battle_engine/agent_test.py` (an
optional `run_dir` parameter — see §6).
**Purpose:** `bytefray agents evaluate <candidate-id>` — a deterministic,
reproducible **controlled experiment**: does a candidate agent perform
better than an optional baseline, across an explicit opponent/seed matrix,
with per-cell results an author can drill into via the existing Agent Lab
tooling. This is the second half of v0.6's "Agent Evaluation Lab" theme;
see `ARCHITECTURE.md` for how it fits alongside the v0.4 authoring loop
(create → validate → test → inspect → modify → repeat) and v0.5's Agent
Lab (inspect → debug → modify → repeat). Evaluation adds the missing step
after "modify": **did it actually get better?**

Status: design spec, written before implementation, per `CONTRIBUTING.md`'s
spec → issue → prompt → PR flow. **Historical rationale only past v0.6** —
the shipped module has moved well beyond this document (schema/identity
now v4 as of v0.9, `agent_revisions` (v0.8), `evaluation_history` (v0.7),
entrant-orientation matrix axis + fixed-arena-alignment disclosure (v0.9),
evaluation presets (v1.6 Phase 3), derived statistical analysis (v1.6
Phase 4)). For current behavior see `docs/AGENT_LAB.md`'s "Evaluating a
candidate" section and `CHANGELOG.md`; this spec is retained for the
original v0.6 design reasoning, which mostly still holds even where the
wire shape has moved on. The `classify()` outcome-rank comparator this
spec designs (§11) is, unchanged, the exact same comparator
`docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md`'s paired statistical evidence
is built on — Phase 4 adds interpretation on top of it, never a second
concept of "improvement."

## 1. User problem

An agent author who has already built, validated, tested, and debugged an
agent (v0.4/v0.5) has no tool to answer:

- Is the current candidate better than the previous version?
- Against which opponents, and across which seeds?
- Is the apparent improvement consistent, or did it only beat one weak
  opponent on favorable seeds?
- Which opponents or seeds regressed?
- Which exact run deserves a closer look?
- Can the same experiment be re-run later, against the same matrix, to
  confirm a fix actually worked?

`bytefray tournament` answers "who won, what are the standings" for a
symmetric round-robin among peers. It does not answer "did *this specific*
candidate improve relative to *this specific* baseline, holding opponents
and seeds fixed" — the question this spec addresses.

## 2. Repository findings

Established by direct source reading (`engine/src/battle_engine`, `app/`,
`docs/`) before any design decision below was made.

1. **`NativeMatchService`** (`match_service.py`) is the one execution
   boundary for every native (non-pMARS) match — VM or Python, single
   match, tournament, or development test. It takes a `MatchRequest`
   (`Config`, entrant tuple, tick limit, replay path, optional
   `trace_path`/`agent_call_timeout`) and returns a `NativeMatchResult`,
   publishing canonical `replay.jsonl` (`battle2.replay` v3) and
   `result.json` (`battle2.result` v1) atomically. Every orchestration
   layer (tournament, `agents test`) calls this same boundary rather than
   re-implementing match execution.
2. **`TournamentService`** (`tournament_service.py`) is a headless
   orchestrator over `NativeMatchService`: deterministic round-robin
   scheduling (every entrant plays every other entrant once per round),
   per-match artifact directories under `matches/<label>/`, an atomically
   checkpointed `tournament.json` (`battle2.tournament` v1) supporting
   resume/retry, and standings derived from canonical `result.json`
   files. Resume re-validates a completed match's `result.json` against
   the *scheduled* match's expected entrant order/seed/`match_id` and the
   replay's digest before trusting it (`_resumed_result_mismatch`); a
   mismatch is recorded as `corrupted`, not silently re-run or silently
   trusted. Failure classification splits `REJECTED_DIAGNOSTIC_CODES`
   (non-retryable configuration/agent-loading problems — treated as
   `rejected`) from everything else (`failed`, presumed transient/
   infrastructure, retried by `--retry-failed`).
3. **`agent_test.test_agent()`** (`agent_test.py`) already implements,
   for exactly one (subject, opponent, seed) pair, everything an
   evaluation cell needs: resolve both entrants (requiring Python kind,
   raising a typed `AgentTestError` for an unknown/non-Python agent —
   §10.3 tool-failure semantics), build a two-slot `MatchRequest`
   (`TESTED_AGENT_SLOT="A"`, `OPPONENT_SLOT="B"`) with `Config(seed=seed)`
   and no overridable arena/quota/win-mode, run it through
   `NativeMatchService`, and distinguish three outcomes: a completed match
   (`DevelopmentTestOutcome`, covering win/loss/tie/forfeit — all
   evaluated-user-code outcomes), a pre-tick-zero initialization failure
   of *either* slot (`InitializationFailureOutcome`, also a fact about
   evaluated user code, not a tool failure), or a genuine tool/
   infrastructure failure (`AgentTestError`). This three-way split is
   **exactly** the per-cell outcome vocabulary an evaluation matrix needs
   (see §9) — it does not need to be reinvented.
4. `agent_test.py`'s match configuration is deliberately narrow: seed and
   tick count only. Arena size, action budget, win mode, and scoring
   weights are always `Config()` defaults; there is no CLI flag to
   override them. This means a bare `bytefray agents test <id> --opponent
   <id> --seed <n> --ticks <n>` invocation is a complete, byte-for-byte
   reproduction of any match `agent_test.test_agent()` can run.
5. **Agent Lab** (`agent_trace.py`, `agent_inspect.py`, `docs/AGENT_LAB.md`)
   already provides deterministic per-call tracing (`trace.jsonl`,
   `bytefray.agent_trace` v1) and inspection (`agents inspect`, `agents
   diverge`) *only* for runs produced by `agents test`/`agents validate`.
   Tracing is cheap (§13 of `docs/specs/agent_lab.md`: tens of
   milliseconds per 200-tick match); *supervision* (worker subprocess +
   timeout) is the expensive part (roughly 4-7x slower). Both are
   independently optional per `MatchRequest` (`trace_path`,
   `agent_call_timeout`, both `None` by default).
6. **Result identity** (`result_model.py`, `RESULT_SCHEMA.md`):
   `stable_id(prefix, value) = f"{prefix}_{sha256(canonical_json(value))[:24]}"`,
   `canonical_json` sorts keys. `match_id` hashes execution inputs only
   (seed, config, entrant content digests — never a filesystem path);
   `result_id` additionally hashes the outcome, with exception text
   stripped for identity purposes. This exact recipe is reused, not
   reinvented, for the evaluation's own identity (§8).
7. **Winner semantics** (`RESULT_SCHEMA.md`): `result.json`'s `winner` is
   always a non-null string; `"tie"` (`WINNER_TIE_SENTINEL`) means no
   single winner. A forfeit already resolves to a winner via
   `results.resolve_winner` — forfeits are not a separate "did not
   complete" bucket, they are baked into the same win/loss/tie outcome
   every other match uses.
8. **`battle_engine.agents.resolve_agent`** is the one agent-discovery
   entry point every orchestrator (`tournament_cli.py`, `agent_test.py`)
   already uses; it returns an `AgentSpec` with `kind`, `api_version`,
   `version`, `source_path`, `entry_point`. Source content digests
   (`hashlib.sha256(source_path.read_bytes())`) are already computed this
   same way in two places (`tournament_service._entrant_identity`,
   `match_service.canonical_match_id`), but each builds a differently
   *shaped* identity dict for a different purpose (a `MatchEntrant`-keyed
   tournament identity; a richer, slot/derived-seed-aware match identity)
   — forcing both into one shared function generic enough to serve a
   third, Python-`AgentSpec`-only evaluation identity would produce a
   more complex, multi-purpose function than any one caller actually
   needs, the premature-abstraction trap `CLAUDE.md` warns against. Only
   the true one-line common primitive (hash the source file's bytes, or
   `None` if it isn't a file) is worth sharing; see §8's revised scope.
9. **`battle_engine.project_info.get_project_info()`** already exposes
   package version, Agent API version, result/replay schema versions —
   exactly the "engine/runtime version" and "Agent API version" fields
   `docs/specs` asks a reproducibility artifact to record, with no new
   version-discovery code needed.
10. Every new schema introduced since the Bytefray rename
    (`bytefray.agent_trace` v1, in v0.5) uses the `bytefray.*` schema
    namespace, reserving `battle2.*` for the pre-rename canonical
    match/replay/result/tournament protocol identifiers (`AGENTS.md`'s
    compatibility section explicitly calls those four "stable protocol
    identifiers," retained under the old name deliberately).
    `battle2.tournament` predates this convention. A new, additive,
    optional artifact — never part of the canonical match/replay/result
    contract — follows the newer `bytefray.*` precedent, not the older
    `battle2.*` one.
11. Designer precedent (`app/views/development.py`,
    `app/views/tournament.py`, `app/services/agent_workflows.py`): every
    Designer action that runs arbitrary agent code goes out-of-process
    via `QProcess` and parses the CLI's own `label: value` stdout/stderr
    contract into a typed, Qt-free presentation dataclass — never a
    second JSON protocol, never agent code executed on the GUI thread.
    Read-only inspection of an already-written artifact (`TraceInspectorDialog`)
    runs in-process because it executes no agent code. The same two rules
    govern the evaluation Designer UX (§12).

## 3. Tournament vs. evaluation

**A tournament** asks "who won, what are the standings" among a
symmetric group of peers: every entrant plays every other entrant once per
round, using tournament-seed-derived per-pair seeds
(`derive_match_seed(seed, round, first, second)`), and the round-robin
schedule *is* the experiment design.

**An evaluation** asks "did *this* candidate improve relative to *this*
baseline" against a fixed, asymmetric, author-chosen matrix: the candidate
(and optionally a baseline) each play every opponent at every explicitly
chosen seed — opponents never play each other, and seeds are not derived,
they are the literal values the author chose (so a cell is directly
reproducible via `agents test --seed <that seed>`, see §2 finding 4).

These are genuinely different schedules, not a superficial UI
relabeling of the same one: forcing an evaluation through
`TournamentService`'s round-robin would either (a) add opponent-vs-opponent
and candidate-vs-baseline matches nobody asked for, inflating match count
and wasting wall time, or (b) require rewriting the round-robin scheduler
into something that no longer describes a round-robin, which is exactly
the anti-pattern this spec's guidance warns against ("avoid... distorting
tournament abstractions until they no longer describe tournaments").

## 4. Alternatives considered

**(a) Wrapper around `TournamentService`.** Construct a tournament
request containing the candidate, baseline, and opponents as entrants,
run it, then post-process standings into an evaluation report. Rejected:
the round-robin schedule cannot express "candidate and baseline each play
every opponent, but never each other, at explicit (not derived) seeds"
without either padding the matrix with unwanted matches or bypassing the
scheduler entirely — at which point nothing of `TournamentService` is
actually being reused except its persistence shape, which is cheap to
reproduce directly (§8).

**(b) Extend `TournamentService` with an "evaluation division" concept.**
Add opponent-exemption and explicit-seed-list options to the existing
scheduler. Rejected: this is the "distort tournament abstractions" trap
called out in §3 — `TournamentService`'s tests, resume semantics, and
`tournament.json` schema all assume a symmetric round-robin; bolting an
asymmetric, explicit-seed mode onto it would make `TournamentService`
itself harder to reason about for its existing, working use case, to
serve a second use case with genuinely different scheduling semantics.

**(c) New orchestration directly over `NativeMatchService`, reusing
`agent_test.test_agent()` as the per-cell executor, sibling to
`TournamentService` rather than wrapping it.** Chosen (§5). Reuses the
same execution boundary, the same identity recipe (`stable_id`/
`canonical_json`), the same atomic-JSON persistence pattern
(`write_json_atomic`), and the same resume-verification idea
(`_resumed_result_mismatch`) tournament already established — but with a
scheduler that actually matches the evaluation matrix's real shape, and,
critically, reuses `agent_test.test_agent()` itself (not just its
*pattern*) as the literal per-cell executor, so every evaluation cell is
executed by the exact same code path `agents test` uses standalone. This
means the "rerun this exact cell" story (§11) requires no bespoke
reproduction logic: the cell *is* an `agents test` invocation.

## 5. Chosen architecture

```
bytefray agents evaluate <candidate> [--baseline <id>]
    --opponents <id,id,...> [--seeds <n,n,...> | --seed-range <a:b>]
    [--ticks <n>] [--output <dir>] [--retry-failed] [--quiet] [--dry-run]
         |
         v
battle_engine.agent_evaluation.EvaluationService
         |  builds a deterministic EvaluationMatrix (subjects x opponents x seeds)
         |  for each cell: agent_test.test_agent(subject_id, opponent=opponent_id,
         |                                        seed=seed, ticks=ticks,
         |                                        run_dir=<evaluation>/matches/<cell-label>,
         |                                        trace=False, timeout=None)
         v
   <output>/evaluation.json  (bytefray.evaluation v1, atomically written)
   <output>/matches/<cell-label>/{replay.jsonl, result.json, summary.json}
```

`EvaluationService` is a new, headless, Qt-free class in
`battle_engine.agent_evaluation`, structurally parallel to
`TournamentService` (own request/result dataclasses, own scheduling
function, own atomic-checkpoint persistence) but with scheduling and
per-cell execution specific to the candidate/baseline-vs-opponents matrix
described in §3. It does not subclass or wrap `TournamentService`; it is a
sibling consumer of the same lower layers (`NativeMatchService` via
`agent_test.test_agent`, `result_model`'s identity/persistence helpers).

`agent_test.py` gains one small, additive change (§6: an optional
`run_dir` parameter) so `EvaluationService` can place each cell's
artifacts under its own `matches/` tree instead of `agent_test`'s default
`runs/agents_test/<agent-id>/<run-label>/` location, without duplicating
`test_agent`'s ~150 lines of resolve/run/classify logic.

Bulk evaluation runs **unsupervised and untraced** by default
(`timeout=None`, `trace=False` passed to every cell) — see §10 for why.

## 6. `agent_test.py` extension: optional `run_dir`

```python
def test_agent(
    agent_id: str,
    *,
    opponent: str | None = None,
    seed: int | None = None,
    ticks: int | None = None,
    timeout: float | None = None,
    trace: bool = True,
    data_root: Path | None = None,
    resource_root: Path | None = None,
    run_dir: Path | None = None,          # new, optional, default None
) -> DevelopmentTestOutcome | InitializationFailureOutcome:
```

When `run_dir` is `None` (every existing caller: the CLI, existing tests,
the Designer's out-of-process `agents test` invocation), behavior is
**byte-for-byte unchanged**: the function computes
`root / "runs" / "agents_test" / agent_id / _run_label(opponent_name)` and
creates it with `mkdir(parents=True, exist_ok=False)`, exactly as today.

When `run_dir` is provided (only `EvaluationService`, §5), it is used
directly instead of the computed default, with `mkdir(parents=True,
exist_ok=True)` — the caller (not `test_agent`) owns that directory's
lifecycle, including across evaluation resume, so a second call must not
fail merely because the directory already exists from a prior attempt.
This is the one behavioral branch the parameter introduces; it is
unreachable from any existing call site, so no existing test's behavior
changes. `test_agent`'s three-way outcome classification (completed /
initialization-failed / tool error) is otherwise untouched.

## 7. Evaluation domain model

```python
@dataclass(frozen=True)
class EvaluationRequest:
    candidate_id: str
    opponent_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    baseline_id: str | None = None
    ticks: int = agent_test.DEFAULT_TICKS   # 200, reused, not re-declared
    output_dir: Path
    resume: bool = True
    retry_failures: bool = False
    data_root: Path | None = None   # threaded to resolve_agent/test_agent, mirroring
                                      # test_agent's own optional data_root parameter
```

Both `opponent_ids` and `seeds` must be non-empty; `candidate_id` must
differ from `baseline_id` (comparing a subject against itself is not a
useful evaluation and is rejected up front, distinctly from tournament's
"entrant IDs must be unique" check, since candidate/baseline/opponents are
different *roles*, not one flat entrant list — an opponent may legally
equal the candidate itself, e.g. evaluating "does my agent beat a
same-code mirror," so only candidate==baseline is rejected).

```python
@dataclass(frozen=True)
class EvaluationCell:
    schedule_id: str
    subject_role: str        # "candidate" | "baseline"
    subject_id: str
    opponent_id: str
    seed: int
    artifact_dir: Path
    status: str               # "pending" | "completed" | "failed"
    outcome: str | None = None  # "win" | "loss" | "tie" |
                                  # "subject_init_failed" | "opponent_init_failed"
    match_id: str | None = None
    result_id: str | None = None
    ticks_run: int | None = None
    score_subject: float | None = None
    score_opponent: float | None = None
    territory_subject: float | None = None
    territory_opponent: float | None = None
    error_code: str | None = None
    error_message: str | None = None
```

### Matrix construction (deterministic)

```python
def build_matrix(request: EvaluationRequest) -> tuple[EvaluationCell, ...]:
    subjects = [("candidate", request.candidate_id)]
    if request.baseline_id is not None:
        subjects.append(("baseline", request.baseline_id))
    cells = []
    ordinal = 0
    for role, subject_id in subjects:              # candidate, then baseline
        for opponent_id in request.opponent_ids:    # request order
            for seed in request.seeds:               # request order
                ordinal += 1
                ...
    return tuple(cells)
```

Iteration order is `subject -> opponent -> seed`, always candidate before
baseline, opponents and seeds in the exact order the request supplies —
never re-sorted, never deduplicated silently (a repeated opponent id or
seed is preserved as two distinct cells; §9 documents this as intentional,
matching the "explicit deterministic seed selection" requirement over any
implicit ordering). For 1 candidate + 1 baseline, 4 opponents, 5 seeds,
this produces exactly `2 * 4 * 5 = 40` cells — `EvaluationService`
computes and prints this count before running anything (§13, §14).

Each cell's `schedule_id` is `stable_id("evaluation-cell", {...})` over
`(evaluation_id, role, subject_id, opponent_id, seed, ordinal)` — the shipped
code includes `ordinal` specifically so a repeated `(role, subject_id,
opponent_id, seed)` tuple, explicitly preserved as distinct cells, still
gets a distinct `schedule_id` rather than colliding in the resume-state
lookup (see the inline comment at `agent_evaluation.py`'s `build_matrix`;
corrected here per `docs/specs/evaluation_history.md` §19 — the description
below previously omitted `ordinal`). Its `artifact_dir`
is `<output_dir>/matches/{ordinal:04d}-{role}-{safe(subject_id)}-vs-{safe(opponent_id)}-seed{seed}/`
(`_safe_path_segment`, reused verbatim from `agent_test.py` — already
exactly this sanitization).

## 8. Identity and reproducibility

```python
def source_digest(source_path: Path | None) -> str | None:
    """Shared one-line primitive: hash an entry-point source file's bytes."""
    if source_path is None or not source_path.is_file():
        return None
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def agent_identity(spec: AgentSpec) -> dict[str, Any]:
    return {
        "agent_id": spec.name,
        "kind": spec.kind,
        "api_version": spec.api_version,
        "agent_version": spec.version,
        "entry_point": spec.entry_point,
        "source_sha256": source_digest(spec.source_path),
    }
```

`source_digest` is the one genuinely shared primitive underlying all
three existing content-digest call sites (`tournament_service.
_entrant_identity`, `match_service.canonical_match_id`, and this new
`agent_identity`) — each site still builds its own differently-shaped
identity dict for its own purpose (§2 finding 8 revises the original plan
to unify those dicts, which would have been a premature abstraction).
`agent_identity` itself is local to `agent_evaluation.py`: it is
Python-`AgentSpec`-only, has no notion of a match slot or derived seed,
and is not a fit for `tournament_service`/`match_service`'s VM-aware,
`MatchEntrant`-keyed identity dicts. No cross-module call-site changes are
made to `tournament_service.py`/`match_service.py` — their existing
identity code is left exactly as it already was and already tested.

`evaluation_id = stable_id("evaluation", {...})` hashes: candidate
identity, baseline identity (or `None`), opponent identities (list, in
request order), seeds (list, in request order), `ticks`, and
`get_project_info()`'s `agent_api_version` — so a candidate/opponent
source edit, a reordered opponent list, or an Agent API version bump
each produce a different `evaluation_id`, exactly mirroring why
`match_id` hashes content digests instead of paths (§2 finding 6).
`get_project_info()`'s full `ProjectInfo` (package version, Agent API
version, result/replay schema versions, Python version) is recorded
verbatim in `evaluation.json` for humans, but only `agent_api_version`
enters the identity hash — the package version string changes on every
release even when nothing evaluation-relevant changed, which would make
`evaluation_id` needlessly unstable across an upgrade that changed
nothing about how the evaluation itself would run (mirroring
`_identity_safe_diagnostic`'s reasoning in `match_service.py`: strip
what's true-but-irrelevant-to-identity before hashing, keep it for humans
elsewhere).

Because seeds are literal (§3), and because `agent_test.py`'s match
configuration cannot be overridden (§2 finding 4), **an evaluation cell's
reproduction command is always exactly**:

```bash
bytefray agents test <subject_id> --opponent <opponent_id> --seed <seed> --ticks <ticks>
```

No hidden config drift is possible between "what the evaluation ran" and
"what `agents test` reruns" — there is no configuration surface for them
to disagree about.

## 9. Failure semantics

Reusing `agent_test.test_agent()` per cell (§5) means the three-way
classification already exists; `EvaluationService` maps it onto
`EvaluationCell` as follows, matching §14's "agent failure/forfeit = valid
evaluation outcome; infrastructure/tool failure = evaluation execution
error" distinction against what the codebase actually implements (§2
findings 3, 7):

| `test_agent()` result | Cell `status` | Cell `outcome` |
|---|---|---|
| `DevelopmentTestOutcome`, subject wins | `completed` | `win` |
| `DevelopmentTestOutcome`, subject loses | `completed` | `loss` |
| `DevelopmentTestOutcome`, tie | `completed` | `tie` |
| `InitializationFailureOutcome`, subject's own init failed | `completed` | `subject_init_failed` |
| `InitializationFailureOutcome`, opponent's init failed | `completed` | `opponent_init_failed` |
| `AgentTestError` raised | `failed` | `None` (`error_code`/`error_message` set) |

A forfeit *during* a completed match is not a separate row here — it is
already folded into `win`/`loss`/`tie` via `resolve_winner` (§2 finding
7), identically to how `bytefray run`/`tournament` already treat it. Only
a pre-tick-zero initialization failure is distinguished from an ordinary
loss, because no match actually ran (there is no `result.json`/replay for
that cell) — collapsing it into `loss` would be misleading (§13's "never
imply more than the sample supports" principle applied to failure
semantics, not just win rates), and collapsing `subject_init_failed`
together with `opponent_init_failed` would hide *which* side's code
broke.

`opponent_init_failed` is deliberately **not** counted as a `win` for the
subject, even though the subject "survived" — no real match executed, so
no real win/loss determination via `resolve_winner` occurred (§2 finding
7 explicitly ties winner resolution to a real completed match). Fabricating
a win from a match that never ran would misrepresent what was actually
tested — exactly the kind of misleading comparison §10's reproducibility
requirement exists to prevent. Both init-failure outcomes are excluded
from win-rate denominators (§10) and from the candidate/baseline
comparator (§11) for the same reason: neither is a real, comparable match
result.

A `failed` cell (genuine `AgentTestError` — unknown/non-Python subject or
opponent, an internal tool error) is excluded from all aggregation and
surfaced prominently in the CLI/Designer summary; `--retry-failed` reruns
only `failed` cells on a subsequent invocation with the same `--output`,
mirroring `tournament`'s identical flag and semantics exactly (§2 finding
2). Unlike `TournamentService`, there is no separate `rejected`/`failed`
split here: `agent_test.test_agent()` already raises `AgentTestError` for
every tool-failure case uniformly (unknown/non-Python agent resolution
*and* internal errors alike), so there is only one non-`completed` status
to report, not two — introducing tournament's two-way split here would
manufacture a distinction the reused executor does not actually make.

Candidate/baseline/opponent **resolution** (kind, existence) is validated
once, up front, for every distinct agent id in the matrix, before any
cell runs (mirroring `TournamentService._validate` and
`agent_test._resolve_python_entrant`'s existing pattern) — an unknown or
non-Python id fails the whole `bytefray agents evaluate` invocation with
exit `2` immediately, rather than after burning time on partial matrix
execution (§16, §24: "show or calculate match count before execution"
implies validating first, too).

## 10. Trace strategy

Every cell runs with `trace=False, timeout=None` — bulk evaluation is
**untraced and unsupervised** by default, for two independent reasons
established directly by measurement already on record (§2 finding 5,
`docs/AGENT_LAB.md`'s "Performance tradeoff" table): supervision costs
roughly 4-7x wall time per match (unsupervised untraced ~121ms vs.
supervised+traced ~811ms on the reference benchmark), and a 40-cell
matrix at that multiplier is the difference between roughly 5 seconds and
roughly 32 seconds of otherwise-identical work — for a tool whose whole
purpose is being run repeatedly across development iterations. Tracing
alone is cheap, but there is no product reason to pay even that small
cost for the ~39 cells an author will never look at.

The intended workflow (§33 of the parent task, and directly matching
`docs/specs/agent_lab.md`'s own explicitly-preferred pattern, §2 finding 5)
is:

```
bytefray agents evaluate  ->  aggregate summary + per-cell table
        |
        v   author spots a regressed (opponent, seed) cell
        |
bytefray agents test <candidate> --opponent <opponent> --seed <seed> --ticks <ticks>
        |                          (identical inputs; trace on by default)
        v
bytefray agents inspect <printed-run-dir>     # or `agents diverge` against
                                                # a baseline's own agents-test run
```

`EvaluationService` never re-implements tracing, timeout supervision, or
inspection — it only ever prints the exact `agents test`/`agents inspect`
invocation for a selected cell (§12), because §8 already guarantees that
invocation reproduces the cell exactly. This is the whole "reuse Agent
Lab, don't build a second tracing system" requirement, satisfied by
construction rather than by a bridging adapter.

## 11. Metrics and comparison semantics

### Aggregation (always computed, per subject)

For each subject (`candidate`, and `baseline` if present), over its
`completed` cells with outcome in `{win, loss, tie}` (§9 excludes the two
init-failure outcomes from every aggregate below, and `failed` cells are
never aggregated):

- `matches_played`, `wins`, `losses`, `ties`
- `win_rate` — always reported as `"{wins}/{played} ({pct:.0f}%)"`, never
  a bare percentage (§13's "show the denominator" requirement)
- `score_total`, `score_avg` (subject's own canonical `score`)
- `score_differential_avg` (subject score minus opponent score, averaged
  over played cells)
- `ticks_avg`
- `territory_avg`, `territory_differential_avg` (subject's final
  territory percentage minus opponent's, from `NativeAgentResult.
  territory_pct_last` — already computed by `match_service`, not
  re-derived)
- counts of `subject_init_failed`, `opponent_init_failed`, and `failed`
  cells, reported alongside (never silently dropped from the summary,
  even though excluded from the rate/average denominators above)

Per-opponent and per-seed breakdowns are the same aggregation function
applied to the subset of a subject's cells matching that opponent (or
seed) — one function, two call sites, not two implementations (`docs/
specs`'s "avoid golden-JSON, prefer small precise assertions" principle
extends naturally to "avoid two aggregation implementations that could
independently drift").

### Comparison (only when `baseline_id` is set)

For every `(opponent_id, seed)` pair present in *both* the candidate's and
the baseline's cells with a real outcome (`win`/`loss`/`tie` on both
sides — a pair where either side has an init-failure outcome is excluded
from comparison entirely and listed separately as **inconclusive**,
because no fair comparison exists when one side never actually played a
match), compute a **deterministic outcome-rank delta**:

```python
_OUTCOME_RANK = {"loss": 0, "tie": 1, "win": 2}

def classify(candidate_outcome: str, baseline_outcome: str) -> str:
    delta = _OUTCOME_RANK[candidate_outcome] - _OUTCOME_RANK[baseline_outcome]
    if delta > 0:
        return "improved"
    if delta < 0:
        return "regressed"
    return "unchanged"
```

This is the **only** dimension used to label a cell `improved`/
`regressed`/`unchanged`. It is deterministic (a total order over three
values, always defined for any two of `{win, tie, loss}`), explainable
(it is exactly the same `win`/`loss`/`tie` outcome §9 already derives
from the canonical `winner` field — not a new metric), and testable.
**Score, score differential, and territory deltas are reported alongside
every classified cell as supporting, non-lossy data — they never
independently produce an `improved`/`regressed` label.** This is a direct
application of §13's explicit warning against calling something "improved"
merely because a numeric field increased, and against assuming an
unjustified `win/loss -> score -> territory -> ticks` hierarchy: rather
than picking a lexicographic ordering across four heterogeneous
dimensions (a real, defensible alternative — see "strongest argument"
below), this design collapses to the one dimension the game itself
already treats as authoritative (`winner`), and reports everything else
as data rather than verdict.

The evaluation summary surfaces, deterministically ordered by
`(opponent_id, seed)`:

- **Regressions**: every `(opponent, seed)` cell classified `regressed`,
  with both outcomes, both scores, and the printable `agents test`/
  `agents inspect` rerun commands for each side (§10).
- **Improvements**: the symmetric `improved` list.
- **Inconclusive**: cells excluded from comparison per above, with the
  reason (which side's subject/opponent failed to initialize).
- An overall count: `"{improved} improved, {regressed} regressed,
  {unchanged} unchanged, {inconclusive} inconclusive (of {total} matched
  cells)"` — never a single collapsed "better"/"worse" verdict for the
  whole evaluation (§13, §33's acceptance scenario asks for per-opponent
  and per-seed answers, not one number).

## 12. CLI

Follows the existing `bytefray agents <verb>` nested-dispatch pattern
(`command.py`'s `_agents()` — one more `if argv and argv[0] == "evaluate"`
branch, lazily importing `agent_evaluation.main`):

```
bytefray agents evaluate <candidate-id>
    --opponents <id>[,<id>...]
    [--baseline <id>]
    [--seeds <n>[,<n>...] | --seed-range <start:end>]
    [--ticks <n>]                  (default: agent_test.DEFAULT_TICKS, 200)
    [--output <dir>]               (default: <data-root>/runs/evaluations/<evaluation-id>)
    [--retry-failed]
    [--dry-run]
    [--quiet]
```

- `--opponents` is required, comma-separated (matches the illustrative
  `--opponents runner,seeker,spiral,writer` shape from the parent task;
  chosen over a repeated positional/flag because opponents are visually
  and semantically one list, and every other multi-value Bytefray flag
  that isn't already a `nargs="+"` positional — there is exactly one,
  `tournament`'s `agents` positional — uses this shape nowhere yet, so
  this establishes rather than breaks a convention).
- `--seeds` is a comma-separated explicit list; `--seed-range a:b` is an
  inclusive integer range expanded to individual seeds, sorted ascending;
  the two are mutually exclusive (`argparse` mutually-exclusive group).
  Neither given defaults to a single seed, `Config().seed` (1337) — the
  same conservative single-seed default `agent_test`/`bytefray run`
  already use, keeping an unadorned invocation's match count small and
  predictable (§24: "conservative defaults").
- `--dry-run` builds and prints the matrix (cell count, subjects,
  opponents, seeds, and the resolved `evaluation_id`) without running any
  match — the "clear match-count estimate... before execution"
  requirement (§16), satisfiable without a separate flag by *always*
  printing the count first in normal mode too, then continuing.
- Exit codes mirror `tournament`'s convention exactly: `0` when every
  scheduled cell reached `completed` (including `subject_init_failed`/
  `opponent_init_failed` outcomes — both are `completed`, §9); `1` when
  one or more cells are `failed`; `2` for an invalid request (unknown
  agent, non-Python agent, empty opponents/seeds, `candidate_id ==
  baseline_id`, or incompatible existing `--output` state).
- Human-readable output (non-`--quiet`): match count and cell breakdown
  before running; per-subject aggregate table; comparison
  regressions/improvements/inconclusive lists (only with `--baseline`);
  failed-cell list with codes/messages; the evaluation artifact path;
  and, for every regressed cell, the two-line `agents test`/`agents
  inspect` rerun hint (§10, §11) — directly answering §33 steps 8-11 of
  the acceptance scenario without the author hand-constructing those
  commands themselves.
- `--quiet` suppresses this presentation; `evaluation.json` remains the
  full machine-readable output, exactly mirroring `tournament
  --quiet`'s existing contract.

Resume: identical shape to `tournament` (§2 finding 2) — rerunning the
same request against an existing `--output` directory resumes `completed`
cells (after the same kind of mismatch verification §2 finding 2
describes, adapted to a two-entrant cell instead of tournament's N-entrant
match — §14 test list covers this directly) and only re-executes
`pending`/`failed` cells (or all `failed` ones, with `--retry-failed`). An
incompatible existing `--output` (different `evaluation_id`) exits `2`
with a controlled error, exactly like tournament's `TournamentConfigurationError`
path.

## 13. Designer UX

Extends the existing Agent Development tab area rather than adding a
fourth top-level tab (mirroring Agent Lab's own §2 finding 11 precedent
directly: `TraceInspectorDialog` extended the *existing* tab; a fresh
`EvaluationDialog` here is the closest available analogue to Agent Lab's
own choice, not a new pattern). A new **"Evaluate…"** button on the
Agent Development panel opens `EvaluationDialog` (`app/views/evaluation.py`,
new — structurally the `TournamentDialog` pattern, §2 finding 11: agent
multi-select via `QListWidget` with `ExtendedSelection`, a candidate combo
pre-populated from the currently-selected Development-tab agent, an
optional baseline combo, a seeds `QLineEdit` accepting the same
`--seeds`/`--seed-range` text the CLI accepts, parsed by the *same*
Qt-free `agent_evaluation` seed-parsing function the CLI uses (not a
second parser), and a `Run` button that shells out to `bytefray agents
evaluate ...` via the Designer's existing `QProcess`/single-active-process
machinery (§2 finding 11: arbitrary user agent code runs during
evaluation, so it is out-of-process, exactly like Validate/Test/
Tournament).

On completion, the Designer reads back `evaluation.json` directly (a
small, Qt-free `read_evaluation_presentation` helper in
`app/services/agent_workflows.py`, parallel to the existing
`read_tournament_presentation`/`read_match_presentation` helpers — reading
the canonical artifact, not re-parsing CLI stdout, exactly like
`agent_workflows.py`'s existing precedent for a completed test's
winner/replay path, §2 finding 11) and renders: the aggregate table, the
regressions/improvements list (baseline only), and a selectable cell list.
Selecting a regressed cell enables two buttons: **Test in Agent Lab**
(runs `bytefray agents test <subject> --opponent <opponent> --seed <seed>
--ticks <ticks>` out-of-process, then opens the existing
`TraceInspectorDialog` against the resulting run directory — reusing both
existing dialogs unmodified) and **Open Replay** (the existing
`open_pygame_client_direct` launcher against that cell's own
`replay.jsonl`, exactly like the Development tab's existing "Open Replay"
button, §2 finding 11).

Kept deliberately modest (explicit instruction, §18 of the parent task):
one dialog, one results table, two drill-down actions. No spreadsheet-like
generic table editor, no in-Designer chart rendering, no new visualization
framework.

## 14. Persistence and resume

`<output>/evaluation.json` (`bytefray.evaluation` v1) is written with the
existing `result_model.write_json_atomic` (temp-file-then-rename,
identical durability guarantee to `result.json`/`tournament.json`) after
every cell completes — not only at the end — so an interrupted evaluation
leaves a readable, resumable artifact reflecting every cell that finished
before interruption, exactly matching `TournamentService.run`'s per-match
checkpoint discipline (§2 finding 2).

Resumability is achieved by direct reuse of the tournament pattern (§2
finding 2), not a new checkpoint framework: on resume, a cell recorded
`completed` with a `result.json` present at its `artifact_dir` is trusted
only after verifying (a) the result's entrant order/ids match the
scheduled cell's `(subject_id, opponent_id)`, (b) its recorded seed
matches the scheduled seed, (c) its `match_id` matches
`canonical_match_id` recomputed from the scheduled inputs, and (d) its
replay digest verifies (`verify_replay_digest`) — any failure demotes the
cell to `corrupted` (a third cell status, alongside `completed`/`failed`,
reachable only via resume) rather than silently re-running or silently
trusting a foreign/stale artifact. A cell recorded `subject_init_failed`/
`opponent_init_failed` (§9) has no `result.json` to re-verify by
construction — it is trusted on resume by its recorded diagnostic alone,
since nothing more specific was ever produced to verify against, exactly
mirroring how `agent_test` itself has no re-verification step for an
initialization failure it already fully reported once.

No new resumability machinery beyond what `TournamentService` already
proved out is built for v0.6 — if a future evaluation feature needs
per-cell parallelism or checkpoint compaction, that is a separate,
later decision (§22/§23 of the parent task explicitly defer it).

## 15. Performance

Benchmarked directly on this checkout (representative matrix: 1
candidate, 1 baseline, 4 opponents, 5 seeds = 40 cells, `--ticks 200`,
Python-vs-Python, scaffold-template-derived agents), wall-clock, measured
after implementation — see the final report for concrete numbers rather
than a number chosen in advance (mirroring `docs/specs/agent_lab.md`'s
identical "measure, don't predict" commitment, §2 finding 5's table).
Recorded alongside: total matches, wall-clock duration, and
`evaluation.json` file size (expected to stay small — it references
per-cell artifacts by relative path rather than embedding replay/result
content, §16).

## 16. Compatibility

- No canonical schema (`battle2.replay`, `battle2.result`,
  `battle2.tournament`) changes. `bytefray.evaluation` is a new,
  independently versioned, additive artifact, following the
  `bytefray.agent_trace` precedent (§2 finding 10).
- `agent_test.py`'s one new parameter (`run_dir`, §6) is optional,
  defaults to `None`, and is unreachable from any existing call site — the
  full existing `agents test` CLI/library/Designer behavior is unchanged
  (existing tests for `agent_test.py` require no modification beyond
  additive coverage for the new parameter itself).
- `tournament_service.py`/`match_service.py` are not modified at all
  (§8 revises the original plan to unify identity-dict shapes across
  modules); their existing test suites are unaffected by construction,
  not merely "expected to still pass."
- No Agent API v1 change. No VM/Python match-composition change — every
  evaluation cell is a plain two-slot Python-vs-Python `agents test`
  match, subject to the exact same "Python entrants only" constraint
  `agents test` already documents and enforces (§17).
- All artifact references inside `evaluation.json` are relative to the
  evaluation directory itself (mirroring `ReplayReference.filename` being
  a bare filename, never absolute — `RESULT_SCHEMA.md`), so an evaluation
  directory can be copied or moved without embedding machine-specific
  absolute paths.

## 17. Python-only scope, stated honestly

Evaluation is **Python-agent-only in v0.6**, for the same reason `agents
test`/Agent Lab already are: the entire per-cell executor
(`agent_test.test_agent`) requires Python-kind entrants and raises a tool
failure for anything else (§2 finding 3). This is not a new limitation
introduced by this spec — it is the existing `agents test` boundary,
inherited unchanged because reusing that exact executor is the
architecture (§5). VM/blob agents can already be compared via `bytefray
tournament` today; extending evaluation to VM agents would require either
a second, VM-flavored per-cell executor (duplicating `agent_test`'s
resolve/run/classify logic for a runtime that has no Agent Lab tracing to
integrate with in the first place, since traces are Python-Agent-API-
boundary data only, §2 finding 5) or broadening `agents test` itself
beyond this spec's scope. Neither is undertaken here; this limitation is
recorded in user documentation (§19) rather than left implicit.

## 18. Tests

- `engine/tests/test_agent_evaluation.py` (new):
  - Matrix construction: exact cell count and order for 1/2 subjects x
    N opponents x M seeds; repeated opponent/seed preserved as distinct
    cells; candidate-equals-opponent permitted; candidate-equals-baseline
    rejected with a controlled error.
  - Seed parsing: `--seeds` list, `--seed-range` inclusive expansion,
    mutual exclusivity, default single-seed fallback.
  - `evaluation_id`/cell `schedule_id` determinism: identical request
    twice produces identical ids; a changed opponent order, seed order,
    or agent source content changes `evaluation_id`; package-version-only
    change (mocked `get_project_info`) does not.
  - Single-candidate evaluation (no baseline): aggregation counts,
    win-rate string formatting (`"n/m (p%)"`), score/territory averages
    against a small fixture matrix with known outcomes.
  - Paired candidate/baseline evaluation: `classify()` outcome-rank
    truth table (all nine `(candidate_outcome, baseline_outcome)`
    combinations over `{win, tie, loss}`); an `opponent_init_failed`/
    `subject_init_failed` cell on either side is excluded from
    comparison and appears in the inconclusive list, not silently
    dropped.
  - Failure aggregation: a fault-injection agent (matching the existing
    inline-source-fixture convention from `agent_lab.md`'s test list)
    that fails `reset()` produces `subject_init_failed`/
    `opponent_init_failed` depending on slot; an unknown/non-Python
    opponent id fails preflight validation (exit `2`) before any cell
    runs; an injected `AgentTestError` produces a `failed` cell excluded
    from aggregation.
  - Resume: a completed cell's `result.json` is trusted on rerun without
    re-executing; a tampered/foreign `result.json` at a cell's
    `artifact_dir` is demoted to `corrupted`, not silently trusted or
    silently re-run; `--retry-failed` re-executes only `failed` cells.
  - Artifact schema round-trip: write, read back, equal; an unsupported
    `schema_version` is rejected explicitly.
  - `run_dir` extension: `agent_test.test_agent(..., run_dir=...)` places
    artifacts at the given path with `exist_ok=True`; every existing
    `test_agent`/`agents test` test continues to pass unmodified
    (regression proof that the default path is untouched).
  - `source_digest`/`agent_identity`: a real source file hashes correctly;
    a missing/non-file `source_path` returns `None` rather than raising.
- CLI (`engine/tests/test_agent_evaluation_cli.py`, or folded into the
  above module): argument parsing (comma lists, seed range, mutually
  exclusive seed flags), `--dry-run` prints the matrix and runs nothing,
  exit codes for all three classes (`0`/`1`/`2`), and the printed
  regressed-cell rerun-command text is byte-for-byte a valid `agents
  test`/`agents inspect` invocation (parsed back and asserted, not just
  string-matched).
- Agent Lab integration: an evaluation run against two fixture agents
  with a known, injected divergence at a specific seed; assert the
  printed rerun command, when actually executed via `agent_test.
  test_agent`, reproduces the identical `match_id`/outcome the evaluation
  cell itself recorded — proving §8's reproducibility claim is true, not
  just documented.
- Designer (`gui`-marked, root `tests/`): `EvaluationDialog` opens with a
  populated candidate/opponent list, seed-text parsing shares the CLI's
  parser (assert no second implementation was created), `Run` builds the
  correct `bytefray agents evaluate` argument list, and `read_evaluation_
  presentation` correctly renders a fixture `evaluation.json` including
  the regressions list and inconclusive cells.
- Regression: full existing v0.4/v0.5 authoring-and-lab suite
  (`test_agent_test.py`, `test_agent_trace.py`, `test_agent_inspect.py`,
  `test_tournament_service.py`) continues to pass unmodified, proving the
  `run_dir`/`_agent_identity` extensions are additive (§16).

## 19. Documentation

`docs/AGENT_LAB.md` gains a short new section, "Evaluating a candidate,"
covering: what evaluation answers vs. what a tournament answers (§3), a
worked `bytefray agents evaluate` example, reading the aggregate/
comparison output, the Python-only limitation stated plainly (§17), and
the regression -> `agents test`/`agents inspect` workflow (§10) as the
direct continuation of the existing Agent Lab documentation's own
structure. `ARCHITECTURE.md` gains an "Agent Evaluation (v0.6)" section
in the same style as its existing "Agent Lab (v0.5.0)" section.
`CHANGELOG.md`'s `[Unreleased]` section records the new command and
artifact. No feature is documented before it is implemented and
validated.

## 20. Deferred / explicitly out of scope

- Elo/Glicko or any single opaque "strength" score (explicit parent-task
  constraint, and inconsistent with §11's outcome-rank-only comparator
  design).
- VM/blob agent evaluation (§17) — would need a second per-cell executor;
  not undertaken here.
- Repetitions/replicates beyond the explicit seed set — an author who
  wants more trials adds more seeds; a separate "repeat each seed N
  times" knob would produce statistically indistinguishable seeds unless
  they were re-derived per repetition, which reintroduces exactly the
  "seeds are not literal" problem §3 rejects tournament's derived-seed
  model for.
- Parallel cell execution — sequential only, matching §23 of the parent
  task; `TournamentService` itself is sequential today, so this is not
  even a capability being deliberately left behind, only one not being
  newly added.
- A general statistical-significance or confidence-interval layer over
  win rates — explicitly out of scope (§13's "avoid false precision").
- Distributed/cloud evaluation execution.
- A Designer results table with sorting/filtering/export beyond the
  modest cell list (§13, §18 of the parent task: "do not turn the
  Designer into a spreadsheet").
- Extending worker-subprocess tracing/supervision to be on-by-default for
  bulk evaluation (§10) — remains an explicit, printed, one-cell-at-a-time
  opt-in via `agents test`.

## Strongest argument against this design

The outcome-rank-only comparator (§11) is a defensible but genuinely
lossy simplification: two agents that both "win" against the same
opponent at the same seed are reported `unchanged` even if the candidate
won by a dramatically larger score/territory margin, and a candidate that
flips a `loss` into a narrow `tie` is reported `improved` identically to
one that flips a crushing `loss` into a dominant `win`. A reviewer could
reasonably argue that a documented lexicographic comparator
(`win/loss/tie`, then score differential, then territory differential, as
literally suggested as one option in the parent task) would capture more
of what an author actually cares about, at the cost of only slightly more
complexity than the rank table in §11.

This is not dismissed lightly, but the outcome-rank-only design is kept
for two reasons found directly in this codebase, not asserted in the
abstract: first, `winner` is the *only* one of the four candidate
dimensions (win/loss/tie, score, territory, ticks) the engine itself
already treats as authoritative for "who won" (`results.resolve_winner`
is the single implementation every match, tournament standing, and this
spec's own `outcome` field already defers to) — score and territory are
real, useful, *reported* metrics (§11), but nothing in `RESULT_SCHEMA.md`
or `scoring.py` establishes them as a secondary tiebreak *of winner
determination itself* the way a lexicographic comparator would implicitly
claim; inventing that ordering here would be evaluation-specific policy
riding on top of data the engine does not present as ordered that way.
Second, and more concretely: `win_mode` is itself configurable
(`survival`/`score`/`score_fallback`) and already determines how much
weight score carries in *deciding* the winner in the first place — a
lexicographic comparator that re-applies score as a tiebreak *after* the
engine's own win-mode-aware decision would double-count score under
`score`/`score_fallback` win modes specifically, silently changing
meaning depending on which win mode the evaluation happened to use. The
chosen design avoids that trap entirely by never re-deriving a verdict
the engine has not already committed to, and instead reports every other
dimension as transparent, non-lossy supporting data next to each
classified cell (§11) — an author loses nothing they could see in a
lexicographic report, they only lose an automatic "which is bigger" label
on dimensions this codebase does not itself treat as ordered.

## Completion criteria

- `bytefray agents evaluate` runs a deterministic candidate (optionally
  vs. baseline) matrix against explicit opponents/seeds, producing
  `evaluation.json` plus per-cell canonical match artifacts.
- Aggregate and per-opponent/per-seed breakdowns are computed with
  honest denominators (§11).
- A regressed cell's exact `agents test`/`agents inspect` rerun commands
  are printed and proven reproducible (§18's integration test).
- Resume/retry works via the same verified-trust pattern as
  `TournamentService` (§14).
- `agents test`, `agents validate`, `agents inspect`, `agents diverge`,
  `bytefray run`, `bytefray tournament`, and every existing test for all
  of the above are unmodified and passing (§16, §18).
- The Designer's Evaluate dialog completes the full acceptance scenario
  (parent task §33) end to end: run, inspect regression, jump to Agent
  Lab, rerun.
