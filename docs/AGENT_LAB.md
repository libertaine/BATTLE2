# Agent Lab

Agent Lab is the second half of the agent-authoring feedback loop. Where
[AGENT_AUTHORING.md](AGENT_AUTHORING.md) covers **create → validate →
test**, this document covers **inspect → debug → modify → repeat**: seeing
exactly what your agent saw and decided at each call, finding where two
runs first behaved differently, and containing a callback that never
returns instead of hanging the tool. See
[docs/specs/agent_lab.md](specs/agent_lab.md) for the full design
rationale and architecture if you need it; this document is the
user-facing reference.

## Mental model

Every native match already writes a canonical `replay.jsonl` — what
actually happened in the arena, tick by tick. `bytefray agents
test`/`agents validate` additionally write an optional `trace.jsonl` —
what your agent was *shown* and what it *decided* at each `reset()`/
`act()` call that produced that replay.

```
replay.jsonl  -- match state: arena bytes, ownership, score, events
trace.jsonl   -- Agent API decisions: Observation in, AgentAction out (or a failure)
```

They answer different questions. "Did I win, and when did I lose
territory?" is a replay question — use `bytefray replay`. "Why did my
agent write to that address on tick 37?" or "why was my action rejected?"
is a trace question — use `bytefray agents inspect`. Neither replaces the
other, and reading a trace never re-runs your agent's code.

## The commands

| Command | Question it answers | Runs agent code? |
|---|---|---|
| `agents validate` | Can the agent satisfy one Agent API lifecycle call? | Yes (one `reset`/`act`) |
| `agents test` | Can the agent play a short real match, and what happened? | Yes (a full development match) |
| `agents inspect <run-dir>` | What did this run's agent see/decide? | No — reads `trace.jsonl` only |
| `agents diverge <run-a> <run-b>` | Where did two runs first disagree? | No — reads two `trace.jsonl` files only |

`inspect`/`diverge` never execute agent code, need no timeout, and take a
plain filesystem path — either a run directory (they look for
`trace.jsonl` inside it) or a direct path to a trace file.

## Inspecting one run

```bash
# Summary: schema, seed, tick range, decision/reset counts, failures
bytefray agents inspect runs/agents_test/my_agent/<run-label>
```

```text
trace: <data_root>/runs/agents_test/my_agent/<run-label>/trace.jsonl
schema: bytefray.agent_trace v1
match_seed: 1337
supervised: True
agent_call_timeout: 5
agents: A=my_agent, B=reference
ticks: 1-117
decisions: 936
resets: 2
failures: 0
```

```bash
# What both agents decided on exactly tick 37
bytefray agents inspect runs/agents_test/my_agent/<run-label> --tick 37

# Just my_agent's decisions in a window around tick 37
bytefray agents inspect runs/agents_test/my_agent/<run-label> --around 37 --window 5 --agent A

# Only records carrying a failure diagnostic
bytefray agents inspect runs/agents_test/my_agent/<run-label> --failures
```

A decision record shows the full `Observation` the agent received, and
either the `AgentAction` it returned or the diagnostic that explains why
it didn't:

```text
tick: 37
agent: A
action_slot: 2
wall_time_ms: 0.412
  observation.pc: 123
  observation.register_a: 1
  observation.register_p: 4
  observation.zero_flag: False
  observation.last_read: 99
  observation.alive: True
  action: write operand=250 value=165
```

**Tick meaning is unambiguous by construction**: a decision record's
`tick` is exactly the tick the observation was produced for — the same
integer the canonical replay's tick uses for the *result* of that
decision. A decision at tick 37 describes what the agent decided while
`replay.jsonl`'s tick-37 snapshot was being produced; the snapshot itself
already reflects that decision's effects (a successful `WRITE`'s byte
change, or a forfeit event for a failed call).

## Comparing two runs

After changing agent code, run `agents test` again and compare the new
run against the old one:

```bash
bytefray agents diverge \
  runs/agents_test/my_agent/2024-01-01T000000-vs-reference \
  runs/agents_test/my_agent/2024-01-02T000000-vs-reference
```

No divergence:

```text
status: identical
trace_a: .../2024-01-01.../trace.jsonl
trace_b: .../2024-01-02.../trace.jsonl
No divergence found: every matched decision agrees.
```

First disagreement:

```text
status: diverged
trace_a: .../trace.jsonl
trace_b: .../trace.jsonl
tick: 12
agent: A
reason: action/diagnostic differ
--- trace a ---
tick: 12
...
  action: write operand=250 value=165
--- trace b ---
tick: 12
...
  action: write operand=250 value=200
```

**What counts as a divergence**: only the `action`/`diagnostic` at a
matched `(tick, agent, action_slot)` key. `wall_time_ms` and header
metadata (agent display names, seed, timeout) are never compared, so two
runs that made the identical decisions are never reported as diverged
merely because one happened to run faster or was invoked with a
differently-named opponent. A decision present in one trace but missing
from the other at the same key (including one trace simply being shorter)
is itself reported as a divergence — never silently ignored — at the
first tick/agent where that happens.

## Timeout semantics

`--timeout SECONDS` (default `5.0`, valid range `0.1`–`300.0`) applies
uniformly to worker startup + agent load, `reset()`, and *each individual*
`act()` call — one number, not four. When a call exceeds it:

| Stage | Diagnostic | Effect |
|---|---|---|
| load | `agent_load_timeout` | Match never starts (initialization failure) |
| reset | `agent_reset_timeout` | Match never starts (initialization failure) |
| act | `agent_action_timeout` | That entrant forfeits; the match continues with the survivor |

A worker that crashes or exits unexpectedly is reported as
`agent_worker_exited`; a response that can't be parsed is
`agent_worker_protocol_error`. All five reuse the same structured
diagnostic shape (`code`/`stage`/`message`) every other Agent API failure
already uses — there is no separate error vocabulary to learn.

`agents test`/`agents validate` are supervised by default at their CLI
entry points (5-second timeout); `bytefray run`/`bytefray tournament`
remain completely unsupervised and untimed, exactly as before Agent Lab
existed — nothing about normal match/tournament execution changed.

## Security boundary

**Agent Lab's worker isolation is development-time hang containment, not
a security sandbox.** Supervised agent code runs with the same OS-level
privileges as Bytefray itself: it can read/write files, open network
connections, spawn further processes, and consume unbounded CPU/memory up
to the timeout. The only guarantee is that Bytefray's own tooling stops
*waiting* for a stalled call and reports which phase stalled. There is no
protection against deliberately hostile code anywhere in this design —
**run only agents you trust**, supervised or not.

## Performance tradeoff

Supervised execution spawns one worker subprocess per Python entrant and
adds an IPC round trip to every `load`/`reset`/`act` call. Measured on a
200-tick, `instr_per_tick=8`, Python-vs-Python development match on this
checkout (best of 3):

| Mode | Wall time (best of 3) |
|---|---|
| unsupervised, untraced (`bytefray run`'s own code path) | ~121 ms |
| unsupervised, traced (`trace_path` set, no timeout) | ~196 ms |
| supervised, traced (default 5.0s timeout, no timeouts hit) | ~811 ms |

Tracing alone is cheap (a few dozen extra milliseconds for a whole
200-tick match) — leaving it on by default (as `agents test`/`agents
validate` do) costs little. Supervision's per-call IPC round trip is the
dominant cost, an order of magnitude slower than the unsupervised path —
this is the accepted, documented tradeoff for being able to name which
phase hung rather than only reporting "the match didn't finish." A
development loop calling `agents test` a handful of times while iterating
on one agent stays well under a second either way; it is not intended for
tight inner-loop use at tournament scale (`bytefray run`/`tournament`
never pay this cost — see "Timeout semantics" above).

## Troubleshooting

**"No trace.jsonl found under directory"** — the run was made with
`--no-trace`, or the path doesn't point at an `agents test`/`agents
validate` run directory. Point `agents inspect`/`diverge` at the exact
directory the failing command printed, or at the `trace.jsonl` file
directly.

**A trace file fails to parse** — `agents inspect`/`diverge` exit `2`
with `code: trace_format_invalid` and an exact `file:line` location. A
trace is only ever malformed if something outside Bytefray's own writer
touched it (hand-edited, copied mid-write, or from an incompatible
schema version) — the writer itself flushes one complete JSON line per
record, never a torn partial write under a normal process kill (see
`battle_engine.agent_trace.TraceWriter`'s docstring for exactly what is
and isn't guaranteed).

**"Could not read trace: unsupported trace schema version"** — the trace
was written by a newer/older Bytefray than the one reading it. Trace
files are not intended to outlive the Bytefray version that wrote them
across a schema bump; re-run `agents test`/`agents validate` to produce a
fresh one.

**A supervised run is much slower than I expected** — see "Performance
tradeoff" above; this is expected for the supervised path. If you don't
need hang containment for this particular run, `--timeout` still defaults
to on for the CLI, so there is currently no `--no-timeout` escape hatch
short of calling the library functions (`test_agent`/`validate_agent`)
directly with `timeout=None`, which is what `bytefray run`/`tournament`
already do.

**My agent's `input()` call raised `EOFError` under a supervised run** —
expected and intentional: a supervised worker's protocol messages travel
over the same stdin/stdout pipes an ordinary Python process would expose
to `input()`/`print()`. The worker redirects agent-visible `stdout` to
`stderr` and agent-visible `stdin` to an empty, already-at-EOF stream
before any agent code runs, specifically so agent I/O can never desync
the protocol — `print()` for debug output is safe (it lands on stderr,
visible in the worker's captured crash context on a later failure), but
an agent should not depend on reading interactively from stdin in either
supervised or unsupervised mode.

## Evaluating a candidate

Validating, testing, and debugging an agent (above, and
[AGENT_AUTHORING.md](AGENT_AUTHORING.md)) tell you whether it works. They
don't tell you whether it's *getting better*. That's what `bytefray
agents evaluate` answers: run a candidate (and, optionally, a baseline to
compare against) against an explicit set of opponents and seeds, and see
where it won, lost, and — if you gave it a baseline — where it improved
or regressed. See [docs/specs/agent_evaluation.md](specs/agent_evaluation.md)
for the full design rationale.

### Evaluation vs. tournament

`bytefray tournament` answers "who won, what are the standings" for a
symmetric group of peers — every entrant plays every other entrant once
per round. `bytefray agents evaluate` answers a different question: "did
*this* candidate improve relative to *this* baseline," against an
asymmetric, author-chosen matrix — the candidate (and baseline) each play
every listed opponent at every explicit seed; opponents never play each
other. If you want standings among a group of peers, use `tournament`. If
you're iterating on one agent and want to know whether your last change
helped, use `agents evaluate`.

### Running an evaluation

```bash
bytefray agents evaluate my_agent \
    --opponents opponent_a,opponent_b \
    --seeds 1,2,3,4,5 \
    --ticks 200
```

This prints the resolved match count before running anything:

```text
candidate: my_agent
baseline: none
opponents: opponent_a, opponent_b
seeds: 1, 2, 3, 4, 5
ticks: 200
subjects: 1  opponents: 2  seeds: 5
matches: 20
Entrant orientation: both
Arena alignment: fixed — translation robustness not evaluated
```

Note **20** matches, not 10: since v0.9, every `(opponent, seed)` pair runs
under **both entrant orientations** by default — see "Entrant orientation"
below. Add `--dry-run` to see this and stop without running a single match.
Compare against a previous version of your agent (kept under a different
discovery id) with `--baseline`:

```bash
bytefray agents evaluate my_agent_v2 \
    --baseline my_agent_v1 \
    --opponents opponent_a,opponent_b \
    --seeds 1,2,3,4,5
```

Seeds can also be given as an inclusive range instead of a list:
`--seed-range 1000:1010`. Every seed you specify is used exactly as
given — an evaluation cell's match seed is never re-derived from a parent
seed the way tournament match seeds are, so a cell is always directly
reproducible (see "Inspecting a regression" below).

### Entrant orientation

Python matches execute in fixed slot order — one entrant completes its
whole action quota before the other begins, every tick — and every
`agents evaluate` cell used to give the candidate that always-first-acting
slot unconditionally, with no way to test the reverse. That's not just a
theoretical asymmetry: the shipped `adaptive` starter agent's own source
comments document and exploit it, deliberately avoiding contested cells
because "that opponent's writes land *after* this agent's within every
tick... so it continuously wins any cell both of them touch."

Since v0.9, `agents evaluate` runs **both entrant orientations** by
default for every `(opponent, seed)` pair: `candidate_first` (today's
historical behavior) and `opponent_first` (the identical, unmodified
executor, called with the two roles swapped) — this is why the matrix
above resolved to 20 matches, not 10. Each orientation is a fully
independent cell with its own `schedule_id`, artifact directory, and
result/replay pair — never averaged together — but every result is still
reported from the *evaluation* role's perspective (subject vs. opponent),
never from whichever physical slot happened to execute first.

Pass `--single-orientation` to restore the exact legacy `candidate_first`
-only methodology and matrix size. Its output — CLI and Designer alike —
is labeled explicitly:

```text
Entrant orientation: candidate-first only — does not generalize across entrant order
Arena alignment: fixed — translation robustness not evaluated
```

Both modes also print the second line above unconditionally: every v0.9
evaluation, regardless of entrant orientation coverage, places both
entrants at the same fixed arena alignment. Running both orientations
makes an evaluation **entrant-order-fair**, not translation-robust —
arena address translation is separate research work
(`runs/research_v0.9/` — not shipped in v0.9) and is not evaluated by this
tool.

### Reading the results

Without `--baseline`, you get one aggregate per subject — pooled across
both orientations — followed by the per-orientation breakdown whenever
both ran:

```text
[candidate] my_agent
  win rate: 14/20 (70%)
  wins=14 losses=4 ties=2 played=20
  score_avg=42.1 score_differential_avg=6.3 ticks_avg=198
  territory_avg=54.20% territory_differential_avg=8.40%
  candidate_first: 8/10 (80%)   opponent_first: 6/10 (60%)
```

Win rate is always shown with its raw counts (`7/10`), never a bare
percentage — a small sample is still a small sample no matter how it's
formatted. With `--baseline`, you additionally get a per-cell comparison:

```text
comparison: 2 improved, 1 regressed, 6 unchanged, 1 inconclusive (of 20 matched cells)
regressions:
  opponent=opponent_b seed=4 orientation=opponent_first
    candidate: loss  baseline: tie
    rerun candidate: bytefray agents test opponent_b --opponent my_agent_v2 --seed 4 --ticks 200
    rerun baseline:  bytefray agents test opponent_b --opponent my_agent_v1 --seed 4 --ticks 200
```

`improved`/`regressed`/`unchanged` come from one deterministic rule: the
candidate's and baseline's own `win`/`tie`/`loss` outcome at the same
`(opponent, seed, orientation)` cell, ranked `win > tie > loss`. Nothing
else — not score, not territory — ever flips this classification; those
are reported alongside every cell as supporting data, never as a hidden
tiebreaker. A cell where either side failed to initialize (a fact about
that side's own code, not a real match) is reported separately as
**inconclusive**, not silently folded into "unchanged." Orientation joins
the comparison key too: a candidate's `candidate_first` cell is never
compared against a baseline's `opponent_first` cell for the "same" nominal
matchup. Notice the printed rerun command for an `opponent_first` row: it
reproduces the cell byte for byte, with the opponent (not the subject) in
the always-first-acting slot, matching exactly how that cell actually ran.

### Inspecting a regression

Every regressed (or otherwise interesting) cell comes with the exact
command to reproduce it, because an evaluation cell's inputs (candidate,
opponent, seed, ticks) are the *entire* input `agents test` needs —
there's no separate match-configuration surface for the two to disagree
about:

```bash
bytefray agents test my_agent_v2 --opponent opponent_b --seed 4 --ticks 200
bytefray agents inspect <printed-run-dir>
```

(For a `candidate_first` cell, as here; an `opponent_first` cell's printed
rerun command has the opponent and candidate positions swapped, as shown
above.) This is the same `agents test`/`agents inspect` loop described
earlier in this document — evaluation doesn't add a second tracing
mechanism.
Bulk evaluation itself always runs **untraced and unsupervised**
(no `trace.jsonl`, no timeout) because tracing/supervision cost real wall
time per match and most of a matrix's cells are never the ones you need
to look at closely; rerunning the one cell you care about through
`agents test` gets you a full trace at negligible extra cost.

### Resuming and retrying

Rerunning the identical `bytefray agents evaluate` command against the
same `--output` directory resumes: every already-completed cell is
trusted (after verifying its recorded seed/entrants/`match_id` and replay
digest, exactly like `tournament`'s resume behavior) rather than rerun.
`--retry-failed` reruns only cells that recorded a genuine tool/
infrastructure failure — an agent's own loss, forfeit, or initialization
failure is a valid evaluation outcome and is never retried implicitly.

### Limitations

Evaluation is Python-agent-only in v0.6 — it reuses `agents test` as its
per-cell executor, and `agents test` requires Python-kind agents. VM/blob
agents can already be compared with `bytefray tournament`.

Both-orientations coverage (v0.9) makes an evaluation entrant-order-fair;
it does not make it arena-alignment-robust. Every v0.9 evaluation still
places every entrant at the same, single, fixed arena alignment —
translation sensitivity (whether a candidate's apparent strength depends
on *where* in the arena it starts) is not evaluated by this tool. Don't
read a both-orientations result as "fully unbiased" or "fully robust" —
it discloses exactly what it covers, no more.

### In the Designer

The Agent Development tab's **Evaluate…** button opens the same
configuration options as the CLI — including the "Run both entrant
orientations (recommended)" checkbox (checked by default; unchecking it is
equivalent to the CLI's `--single-orientation`) — then shows results in a
table with the same aggregate/comparison data described above, including
each row's entrant orientation and the same methodology disclosure text.
Selecting a cell enables **Test Candidate in Agent Lab** (reruns that exact
cell through `agents test` and opens the Trace Inspector on it) and **Open
Replay**.

### Evaluation history (v0.7)

Every `bytefray agents evaluate` run since v0.7 writes `bytefray.evaluation`
**v2**: the same artifact shape described above, plus a readable planned
identity for the candidate/baseline/every opponent occurrence, the full
effective match configuration (arena size, action budget, win mode,
weights, tick limit), a narrow `rules_compatibility_id` (bumped only when
scoring/winner-resolution/scheduling semantics that affect comparability
actually change), `created_at`/`updated_at`/`finished_at` lifecycle
timestamps, and explicit duplicate-occurrence coordinates. `evaluation_id`
remains a deterministic plan identity, never a run-occurrence ID or a
location/time/outcome — but the v2 payload is richer than v1's, so a v2 id
is never mistaken for a v1 id (`evaluation-v2_...` vs. `evaluation_...`).
v1 artifacts from before v0.7 remain fully readable and are never rewritten.

If the candidate's, baseline's, or an opponent's source changes mid-run
(rare, but possible if you edit an agent while a large matrix is still
executing), the evaluation stops at the first detected drift rather than
silently mixing revisions: the artifact is marked
`lifecycle_state: "aborted"`, `abort_reason: "source_drift"`, every cell
completed before the drift is preserved, and a fresh evaluation is required
to continue (which happens automatically, since the changed source now
produces a different `evaluation_id`/output path anyway).

New history commands read any past evaluation without rerunning it:

```bash
bytefray agents evaluations list                          # every discovered evaluation
bytefray agents evaluations show <evaluation-id-or-path>   # one evaluation in detail
bytefray agents evaluations show <selector> --verify       # + deep replay/result verification
bytefray agents evaluations compare <left> <right>         # right relative to left
```

`compare` never uses the stored candidate-vs-baseline verdicts as its
primary signal; it independently aligns the two evaluations' candidate
cells by shared condition (opponent identity, seed, configuration, rules
compatibility, arena alignment, entrant orientation, duplicate occurrence —
deliberately excluding candidate identity, since that's the thing being
compared) and reports
`improved`/`regressed`/`unchanged`/`inconclusive` with honest denominators,
same as a single evaluation's own comparison table. A candidate whose
*logical id* changed between the two evaluations is reported as "different
candidates," not silently treated as a revision of the same one. See
`docs/specs/evaluation_history.md` for the full identity, lifecycle,
drift, and comparison semantics, including v1's honest limitations (v1
never persisted enough to recover genuine executable identity for
historical opponents/candidates, so `evaluations compare` against a v1
artifact reports those dimensions as unknown rather than guessing).

### Agent revisions (v0.8)

Since v0.8, every `bytefray agents evaluate` run durably archives the exact
source of the candidate, baseline (if any), and every opponent — not just
their identity, an actual byte-for-byte copy — at the moment the plan
freezes, before any cell executes. This closes a real gap `evaluations
show`'s planned identity alone couldn't: identity tells you *whether* a
historical evaluation's source matches something, but not what that source
*was* once you've since edited or deleted the live agent.

```bash
bytefray agents revisions list <agent-id>              # every preserved revision relevant to this agent
bytefray agents revisions show <revision-id>            # provenance, omissions, local verification
bytefray agents revisions restore <revision-id> --to <dir>   # write the preserved files to <dir>
```

`evaluations show <selector>` prints each role's revision id next to its
identity; `--verify` also checks that the local store's copy of each
referenced revision still verifies, distinguishing "not available on this
machine" (never treated as corruption — a copied evaluation directory
without its original revision store, or a store that's since been cleaned
up, is expected to read this way) from "invalid" (a snapshot is present but
its bytes don't reconstruct the fingerprint it's filed under — this *is*
a verification failure).

Restoring composes with the rest of the toolchain rather than adding a new
one: `restore` just writes plain files to a directory (never implicitly
into `agents/<id>/`, and never overwriting a non-empty target without
`--force`), and the existing `agents validate`/`agents test`/`agents
evaluate` commands work on that directory exactly like any other agent
folder. A revision is `complete` only when nothing under the agent's
directory had to be omitted (an external symlink target, an unreadable
file); an incomplete revision still has a real, useful identity for
deduplication and comparison, but `restore` reproduces only what was
actually captured, and says so. See `docs/specs/agent_revision.md` for the
full identity/storage/verification design, including exactly what a
revision does and does not preserve.

### Orientation-aware evaluation and fixed arena alignment (v0.9)

Since v0.9, `bytefray agents evaluate` runs both entrant orientations by
default (see "Entrant orientation" above) — `bytefray.evaluation` bumps to
**schema v4**/**identity v4** to carry this: each cell gains
`orientation`/`orientation_index`, and each evaluation gains
`orientation_mode` (`"both"` | `"candidate_first_only"`) and
`arena_alignment_mode` (`"fixed"`, v0.9's only value). Both are threaded
through identity and cross-evaluation comparison the same way
`rules_compatibility_id` already is; `rules_compatibility_id` itself is
unaffected — this is an evaluation-methodology change, not a change to
scoring, winner resolution, or scheduling. v1/v2/v3 artifacts remain fully
readable and are never rewritten: `evaluations show`/`compare` recover
every historical cell's orientation as `candidate_first` and every
historical evaluation's arena alignment as `fixed` — both are certain
historical facts (no prior version of this tool could have produced
anything else), reported as *recovered*, not *unknown*, and not silently
guessed either.
