# replay_session

**Module:** `client/src/battle_client/session.py`
**Purpose:** A renderer-independent `ReplaySession` abstraction that loads an
existing replay into memory and exposes it as a navigable, in-memory cursor
over reconstructed engine state, for headless replay analysis and as the
foundation the merged `PlaybackController`/`PygameRenderer` interactive
playback already builds on.

> **Note on provenance.** This document is written retroactively, at explicit
> direction, to document `ReplaySession` behavior that was already
> implemented and merged ahead of a spec, out of step with
> `CONTRIBUTING.md`'s spec → issue → prompt → implementation flow. Two
> commits are covered:
>
> - `74dcfa6`, "Phase 7a slice 1 — ReplaySession replay-analysis foundation":
>   the `load` / `current_state` / `step_forward` / `restart` foundation.
> - `671d852`, "Phase 7a Slices 2-3 — deterministic seek + interactive Pygame
>   viewer": adds, to `ReplaySession` itself, `seek(tick)`, strict
>   tick-monotonicity validation at `load` time (which **replaces** slice 1's
>   original "tolerate duplicate/out-of-order ticks" behavior — see §10),
>   `current_tick`/`final_tick`/`recorded_ticks` accessors, a `runtime_kind`
>   field on `ReplayState`, and read-only (`MappingProxyType`) `agents`/
>   `score` mappings.
>
> This document now specifies the **full merged `ReplaySession` contract**
> from both commits — that is the tested, implemented behavior, and is
> treated here as the current contract rather than as slice-1-only history.
> Commit `671d852` *also* added a `PlaybackController` (in
> `battle_client.player`) and a rewritten `PygameRenderer` with keyboard
> controls, plus the CLI wiring (`battle_client.cli`) that drives the
> interactive Pygame path through `ReplaySession` + `PlaybackController`.
> Those are consumers *of* `ReplaySession`, not part of its own contract, and
> remain **out of scope for this document** — they fall inside the
> "renderer-specific behavior" and "UI controls" non-goals below, and are
> covered separately by `docs/MANUAL_SMOKE_TESTS.md`'s "Bytefray interactive
> Pygame replay viewer keyboard controls (Phase 7a)" section rather than
> retroactively specified here.

## 1. Purpose and non-goals

**Purpose.** Provide a single class, `ReplaySession`, that:

- loads a complete replay file into memory once via the existing
  `battle_engine.replay.iter_replay` reader;
- reconstructs engine-observable state (arena bytes, memory ownership,
  per-entrant `AgentState`, score) at each recorded tick, using the same
  diff-application procedure documented in `docs/REPLAY_SCHEMA.md`'s "Memory
  reconstruction" section;
- exposes that state through an explicit, steppable, seekable cursor,
  without depending on Pygame, PySide6, or any other renderer/UI concern;
- gives playback-control and headless-analysis work a stable,
  renderer-independent foundation to build on — already used by the merged
  `PlaybackController`/`PygameRenderer` interactive viewer (see the
  provenance note above), and reusable by any future headless-analysis
  consumer.

**Non-goals for `ReplaySession` itself:**

- Streaming replay playback (no wall-clock pacing, no timers, no `sleep`,
  inside `ReplaySession` itself — wall-clock pacing is `PlaybackController`'s
  job, layered on top; see the provenance note).
- Checkpoints or an indexed/on-disk replay format.
- A new replay schema version — `ReplaySession` is a pure reader-side
  consumer of the existing `battle2.replay` wire format.
- Any renderer-specific behavior (Pygame, PySide6, or otherwise) or UI
  controls (keyboard handling, playback speed, window scale, etc.) — those
  live in `PlaybackController`/`PygameRenderer`/`battle_client.cli`, already
  merged as consumers of `ReplaySession` but documented elsewhere, not here.
- Single-step *backward* navigation as a distinct primitive from `seek`.
  `restart()` remains the only unconditional "back to the start" primitive;
  stepping backward by one tick is `seek(current_tick - 1)`, not a separate
  method. See §8–§9.
- Opportunistic cleanup or refactoring of `battle_engine.replay`,
  `battle_client.player`, or any other existing module.

## 2. Proposed module/location

`client/src/battle_client/session.py`, in the `battle_client` package
alongside `battle_client.player` (the existing streaming `ReplayPlayer`) and
`battle_client.utils`. `ReplaySession` is additive: it does not replace or
modify `ReplayPlayer`, `iter_replay`, or any renderer module. It sits above
`battle_engine.replay` (the parser/model layer) exactly as `ReplayPlayer`
does, as an alternative, non-streaming consumer of the same reader.

Rationale for `client/` rather than `engine/`: `ReplaySession` is a replay
*consumption* concern (like `ReplayPlayer`), not part of the engine's
match-execution or telemetry-writing surface. `client/` already owns "read an
existing replay and present it" responsibilities, per `ARCHITECTURE.md`'s
description of `battle_client`.

## 3. Public API

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from battle_engine.replay import AgentState, EngineEvent, RuntimeKind


class ReplaySessionError(ValueError):
    """A replay could not be loaded into, or navigated within, a session."""


@dataclass(frozen=True)
class ReplayState:
    """Reconstructed engine-observable state at one tick."""
    tick: int
    arena: bytes
    owners: tuple[str | None, ...]
    agents: Mapping[str, AgentState]
    score: Mapping[str, int | float]
    runtime_kind: RuntimeKind | None


class ReplaySession:
    def __init__(self) -> None: ...

    def load(self, path: str | Path) -> None: ...

    @property
    def loaded(self) -> bool: ...

    @property
    def current_state(self) -> ReplayState: ...

    @property
    def current_tick(self) -> int: ...

    @property
    def final_tick(self) -> int | None: ...

    @property
    def recorded_ticks(self) -> tuple[int, ...]: ...

    @property
    def at_end(self) -> bool: ...

    @property
    def winner(self) -> str | None: ...

    @property
    def termination_reason(self) -> str | None: ...

    @property
    def runtime_kind(self) -> RuntimeKind | None: ...

    def events_at_tick(self, tick: int) -> tuple[EngineEvent, ...]: ...

    def step_forward(self) -> ReplayState: ...

    def seek(self, tick: int) -> ReplayState: ...

    def restart(self) -> ReplayState: ...
```

`ReplaySession` also exposes `header: ReplayHeader | None` and
`result: MatchResult | None` as public attributes (not properties), set by
`load` and readable directly — mirroring how `ReplayHeader`/`MatchResult` are
already public dataclasses in `battle_engine.replay`, with no need for an
accessor method.

`ReplayState.agents` and `ReplayState.score` are read-only
(`MappingProxyType`) views over a private copy: mutating them raises
`TypeError`, and even a successful in-place mutation of `arena`/`owners`
(already-immutable `bytes`/`tuple`) cannot affect the session's own internal
state or any later `step_forward`/`seek`/`restart` result, since every field
is copied out of the session on access (see §14).

`RuntimeKind`, `AgentState`, and `EngineEvent` are re-used unchanged from
`battle_engine.replay`; this module defines no new schema types.

## 4. Session construction/loading behavior

- `ReplaySession()` takes no arguments and starts unloaded (`loaded is
  False`; every state-accessing property/method raises `ReplaySessionError`
  until a successful `load`).
- `load(path)` reads **every** record from `path` in one pass via
  `iter_replay(path)`, partitioning records into at most one `ReplayHeader`,
  zero or more `TickSnapshot`s (in file order), and at most one `MatchResult`.
- Each `TickSnapshot`'s `tick` number must be **strictly greater** than the
  tick number before it in file order; a duplicate or out-of-order tick is
  rejected with `ReplaySessionError` (see §10). Gaps between
  strictly-increasing tick numbers are allowed.
- A **second** header or result record in the same file is rejected with
  `ReplaySessionError` (a replay has exactly one header and at most one
  terminal result by construction of the writer; more than one indicates a
  corrupt or hand-edited file).
- A **missing** header is rejected with `ReplaySessionError` — `arena_size`
  and other header-derived state are required to reconstruct anything, so a
  header-less replay cannot be loaded at all (see §13).
- A **missing** result record is *not* an error (see §7): `result` is left
  `None`, and `winner`/`termination_reason` read as `None`.
- On success, the session's cursor is positioned at the first tick (tick 0 if
  present, else the synthesized empty state — see §7).
- On any failure (a raised `ReplayFormatError` from the reader, or a
  `ReplaySessionError` raised by `load` itself), **no partial state is
  installed**: an already-loaded session is left exactly as it was before the
  failed `load` call. New session state is only assigned after the full read
  and validation succeed.
- `load` may be called more than once on the same `ReplaySession` instance
  (to load a different replay); each successful call fully replaces the
  previous session state.

## 5. What constitutes a replay position

A position is a **tick number** (a non-negative integer, taken from the
recorded `TickSnapshot.tick` values, or `0` for the synthesized empty-replay
case). The session does not track position as a byte offset, record index,
or wall-clock time — only as the tick number of the most recently applied
`TickSnapshot`. `current_tick` exposes this number directly (without
constructing a full `ReplayState`); `final_tick` exposes the last recorded
tick number (or `None` for a header-only replay); `recorded_ticks` exposes
every recorded tick number, in increasing order, for a caller (e.g. a
playback controller) that needs to navigate to the previous/next *recorded*
tick of a possibly-sparse legacy replay without guessing a number and
catching `ReplaySessionError` from `seek`.

`current_state` derives a full `ReplayState` for the current position by
composing:

- `tick`: the current tick number;
- `arena`: reconstructed bytes, produced by applying every `memory_diffs`
  entry's `values` (in tick order, from tick 0 through the current tick,
  wrapping addresses `% arena_size`) onto an all-zero `arena_size` buffer,
  per the existing documented reconstruction procedure;
- `owners`: reconstructed per-address ownership, using `owner`/`address`/
  `length` even when a diff's `values` is empty (legacy input — see §11);
- `agents`: the most recently seen `AgentState` per agent ID, from every tick
  applied so far, exposed as a read-only `MappingProxyType` view;
- `score`: the score mapping from the *most recently applied* tick only (not
  merged across ticks — score is a per-tick snapshot in the schema, not a
  diff), also exposed as a read-only `MappingProxyType` view;
- `runtime_kind`: the header's `RuntimeKind` (`"vm"` or `"python"`), so a
  consumer can tell whether `AgentState.pc`/`region`/`cpu_used` mean the
  VM's real fetch address/code footprint/instruction count, or the Python
  runtime's controller bookkeeping/degenerate marker/callback count, without
  a separate call back into the session — see the runtime-kind semantics
  table in `docs/REPLAY_SCHEMA.md`.

## 6. Current-position semantics

Internally, the session buffers all `TickSnapshot`s in file order
(`self._ticks: tuple[TickSnapshot, ...]`) and tracks a cursor as an **index**
into that tuple (`self._cursor: int`, `-1` before any tick is applied). The
current tick *number* (as opposed to index) is `self._ticks[cursor].tick` if
`cursor >= 0`, else `0`.

This index/number distinction matters because recorded tick numbers are not
required to be *contiguous* (see §11) even though `load` now requires them
to be strictly increasing (see §10): the cursor advances through the
buffered list in **file order**, one element at a time for `step_forward`,
or directly to a target index for `seek` — it is a position in "the replay
as recorded," not an assumption that every integer tick number is present.

`current_state` is a pure accessor: reading it never advances or otherwise
mutates the cursor, and calling it repeatedly without an intervening
`step_forward`/`seek`/`restart`/`load` returns an equal `ReplayState` each
time.

## 7. Behavior before the first record and after the final record

- **Before the first tick record:** there is no "before tick 0" position
  reachable through the public API — `load` always positions the cursor at
  the first tick immediately (or the synthesized empty state), so a caller
  never observes a session with a header loaded but no current state.
- **Header-only replay (no tick records at all):** `current_state` returns a
  *synthesized* tick-0 state: `tick=0`, an all-zero `arena_size`-byte arena,
  all-`None` owners, empty `agents`, empty `score`. `at_end` is `True`
  immediately. This is a defined, non-error state (see §12), not a special
  sentinel value.
- **After the final tick record:** `at_end` becomes `True` once the cursor
  reaches the last buffered tick (whether it got there via `step_forward` or
  `seek`). Calling `step_forward()` again raises `ReplaySessionError`
  ("already at the final tick") rather than wrapping, raising
  `StopIteration`, or silently no-op'ing. `current_state` continues to
  return the final tick's state indefinitely until `restart()`, `seek()` to
  an earlier tick, or a new `load()`.
- The terminal `MatchResult` record, if present, is **never** treated as an
  extra navigable tick — `winner`/`termination_reason` are separate
  properties, not reachable via `step_forward`/`seek`/`current_state.tick`.
  `seek()` to a tick number past `final_tick` raises `ReplaySessionError`
  rather than landing on the result record.

## 8. Forward and backward navigation semantics

`ReplaySession` provides three navigation operations:

- **`step_forward()`** — advances the cursor by exactly one buffered
  element (applying only that tick's diffs on top of the existing
  reconstructed state) and returns the resulting `ReplayState`. Raises
  `ReplaySessionError` if already `at_end`. This is the only "one step at a
  time" primitive; there is no "step forward N ticks."
- **`seek(tick)`** — moves the cursor directly to the exact recorded tick
  `tick` and returns the resulting `ReplayState`. A forward seek (`tick` at
  or after the current one) applies only the intervening ticks' diffs on top
  of the existing state; a backward seek resets to the canonical tick-0
  state and replays forward to `tick`. Either way, the resulting state is
  fully determined by `tick` alone, never by the cursor's prior history (see
  the determinism tests in `test_replay_session.py`). Raises
  `ReplaySessionError` if the replay has no tick records, if `tick` is
  outside the replay's recorded range (below the first recorded tick or
  above the last), or if `tick` falls in a gap between two recorded ticks —
  possible only for a sparse legacy replay, since canonical replays record
  every integer tick with no gaps (see §11). No state is fabricated for an
  unrecorded tick. `seek` is also this slice's single-step-*backward*
  primitive: `seek(current_tick - 1)` moves back exactly one recorded tick.
- **`restart()`** — unconditionally resets the cursor to the replay's first
  position (re-deriving state from an all-zero arena and reapplying tick 0's
  diffs if a tick 0 exists, or returning the synthesized empty state
  otherwise) and returns the resulting `ReplayState`. Equivalent to
  `seek(recorded_ticks[0])` for a non-empty replay, except it is also
  defined (as a no-op) for a header-only replay with no tick records at all,
  where `seek` would raise (see §12).

There is no `step_backward()` — `seek` and `restart()` together cover both
directions.

## 9. Tick-based navigation requirements

Navigation is available in both forms: `step_forward()`/`restart()` are
index-based (advance one buffered record, or reset to the first), while
`seek(tick)` is tick-number-based — it accepts a target tick number
directly and requires it to name a recorded tick (see §8). `events_at_tick
(tick)` is also tick-number-based but is a *lookup*, not a navigation
operation — it does not move the cursor (see §14).

## 10. Treatment of duplicate and out-of-order tick values

Duplicate tick numbers (two or more `TickSnapshot` records sharing the same
`tick`) and out-of-order tick numbers (a tick number not strictly greater
than the one recorded before it) are **rejected at `load` time**, not
tolerated:

- `load` requires each `TickSnapshot`'s `tick` to be strictly greater than
  the tick number immediately before it in file order. The first violation
  encountered raises `ReplaySessionError` (message: `"tick {tick} is not
  strictly greater than the preceding recorded tick {prev} (duplicate or
  out-of-order ticks are rejected)"`), and — per §4 — leaves any
  previously-loaded session state untouched.
- This is deliberately **strict**, not merely "sorted and deduplicated on
  read": a hand-edited or malformed-but-parseable replay with a duplicate or
  decreasing tick number is treated as corrupt/hand-edited input, the same
  category of failure as a missing header, and `load` fails outright rather
  than silently reordering or dropping records.
- The reason is `seek(tick)` (§8): once tick numbers can be looked up and
  jumped to directly, each tick number must identify exactly one
  deterministic state for `seek` to be well-defined. Tolerating duplicates
  or out-of-order ticks would make "the state at tick N" ambiguous (which of
  two same-numbered records? the file-order one, or the highest-index one?)
  in a way a direct `seek(N)` cannot resolve the way `step_forward`'s
  visit-every-record-in-file-order semantics previously could.
- Because tick numbers are validated as strictly increasing at `load` time,
  `events_at_tick(tick)`'s `{tick_number: index}` lookup table is always
  one-to-one — there is no "last duplicate wins" behavior to document, since
  duplicates cannot reach the buffered list at all.

Gaps between strictly-increasing tick numbers are **not** rejected — see
§11 for the distinction between "strictly increasing" (required) and
"contiguous" (not required).

## 11. Treatment of non-contiguous (sparse) tick numbers

Unlike duplicate/out-of-order ticks (§10), *gaps* between recorded tick
numbers are tolerated, not rejected, provided the file-order sequence is
still strictly increasing:

- Canonical replays produced by `match.py`/`python_runtime.py` publish every
  integer tick from 0 through the match's actual final tick with no gaps —
  confirmed empirically by `test_seek_every_tick_of_a_real_vm_replay_
  succeeds`, which seeks to every tick of a real VM replay and asserts none
  are missing.
- Legacy v0.1/v0.2 replays may legitimately record only a sparse subset of
  ticks (e.g. only ticks with an event); `load` does not require
  contiguity, only strict monotonicity.
- `recorded_ticks` exposes exactly which tick numbers were recorded, in
  increasing order, so a caller can distinguish "this tick number is simply
  absent from a sparse replay" from "this tick number is out of range."
- `seek(tick)` to a tick number that falls in a gap between two recorded
  ticks raises `ReplaySessionError` (message mentions "not recorded in this
  replay") rather than fabricating interpolated state; `seek` to a tick
  number that *is* recorded works identically whether or not the replay is
  sparse (see `test_sparse_ticks_seek_to_recorded_tick_succeeds` and
  `test_sparse_ticks_seek_into_a_gap_raises_rather_than_fabricating_state`).
- `step_forward` is unaffected by sparseness either way: it always advances
  to the *next buffered record*, whatever tick number that record happens
  to carry, so a gap in tick numbers never causes a skipped or repeated
  step.

## 12. Empty replay behavior

"Empty" is interpreted as **header-only, zero tick records** (a replay with
zero records at all is impossible — `load` requires a header). Behavior:

- `current_state` returns the synthesized tick-0 state described in §7.
- `at_end` is `True`.
- `step_forward()` raises `ReplaySessionError`.
- `seek(tick)` raises `ReplaySessionError` ("no tick records to seek
  within") for any `tick`, since there is no recorded tick to seek to.
- `restart()` is a **defined no-op** — it returns a `ReplayState` equal to
  the current one, not an error — since there is nothing to reset away from.
- `winner`/`termination_reason` reflect whatever `MatchResult` (if any) was
  present, independent of there being zero ticks.

## 13. Malformed/truncated replay behavior

`ReplaySession` adds **no new error-handling behavior** on top of the
existing reader for malformed/truncated input — it deliberately preserves
the fail-fast behavior `docs/REPLAY_SCHEMA.md` already documents ("Known
limitations carried forward": a truncated/corrupted replay fails the whole
read at the point of corruption via `ReplayFormatError`, not a
partial-recovery mode):

- Any exception `iter_replay` raises while `load` is consuming it (in
  practice, `battle_engine.replay.ReplayFormatError`, already carrying
  file/line context) propagates **unchanged** out of `load` — it is not
  caught, wrapped, or translated into `ReplaySessionError`.
- `ReplaySessionError` is reserved for failures `ReplaySession` itself
  detects that are *structurally* valid JSONL but semantically incomplete or
  inconsistent for this abstraction's needs: no header record, more than
  one header record, more than one result record, or a duplicate/
  out-of-order tick number (§10).
- Per §4, a failed `load` (of either exception kind) never corrupts a
  previously-loaded session's state.

## 14. Cursor mutation vs. return values

Every navigation/loading method both **mutates cursor state and returns a
value**, with one exception:

| Method | Mutates session state? | Return value |
|---|---|---|
| `load(path)` | Yes — replaces `header`, `result`, buffered ticks, and resets the cursor | `None` |
| `step_forward()` | Yes — advances the cursor by one | `ReplayState` (the new current state) |
| `seek(tick)` | Yes — moves the cursor to the exact recorded `tick` | `ReplayState` (the new current state) |
| `restart()` | Yes — resets the cursor to the first position | `ReplayState` (the new current state) |
| `current_state` (property) | No | `ReplayState` (a fresh snapshot copy, not a live view) |
| `events_at_tick(tick)` | No | `tuple[EngineEvent, ...]` (a lookup, not a step) |
| `winner`, `termination_reason`, `runtime_kind`, `at_end`, `loaded`, `current_tick`, `final_tick`, `recorded_ticks` (properties) | No | scalar/`None`/`tuple` |

`current_state` returning a **snapshot copy** (not a reference into live
internal buffers) is intentional: mutating a `ReplayState` returned earlier
must never affect the session's own internal reconstruction state or any
later `step_forward`/`seek`/`restart` result. `ReplayState.agents`/`score`
being read-only `MappingProxyType` views (§3) means even an in-place
mutation attempt on the returned mapping raises `TypeError` rather than
silently succeeding and then failing to propagate.

## 15. Complexity/memory expectations for this first implementation

- **Memory:** O(total replay size) — every `TickSnapshot` (and its
  `memory_diffs`/`agents`/`events`) is retained in memory for the lifetime of
  the loaded session, plus one `arena_size`-byte arena buffer and one
  `arena_size`-entry ownership list. This is an explicit, intentional
  buffering choice for this phase (see non-goals) — there is no eviction,
  paging, or on-disk spill.
- **`load` time:** O(number of records) — one linear pass through
  `iter_replay`, each record handled in O(1) plus O(diff length) for the
  ownership/tick-index bookkeeping it performs.
- **`step_forward` time:** O(size of the *next* tick's diffs) — it applies
  only the incoming tick's `memory_diffs`/`agents`/`score`, not a rescan from
  tick 0 (i.e. state carries forward incrementally rather than being
  recomputed each call).
- **`restart` time:** O(size of tick 0's diffs) (or O(1) for a
  header-only/empty replay) — it resets to an all-zero arena and reapplies
  only the first tick, not a "replay everything since load" operation.
- **`seek` time:** O(size of the diffs strictly between the current tick and
  the target tick) for a forward seek (only the intervening ticks are
  applied on top of existing state); O(size of tick 0's diffs through the
  target tick) for a backward seek (it resets to an all-zero arena and
  replays forward, the same as `restart` followed by however many
  `step_forward`-equivalent applications are needed). Either direction, the
  resulting state depends only on the target tick, never on how the cursor
  got there — there is no per-tick snapshot cache; full buffering plus
  incremental replay from the nearest known state (tick 0, for a backward
  seek) is simple, correct, and fast enough at this scale without one.
- **Sizing rationale:** appropriate for the replay sizes this repository
  currently produces (v0.3-scale matches: a few thousand ticks, a few KB
  arena) — not validated here against significantly larger hypothetical
  replays, which is exactly why streaming/checkpointing is called out as a
  later-phase, not this-phase, concern.

## 16. Required unit/characterization tests

Location: `client/tests/test_replay_session.py` (co-located with the other
`battle_client` test modules; no `gui` marker, since `ReplaySession` has no
display dependency). At minimum, covering:

**Loading and header/runtime exposure**
- Loading a real v3 replay produced by `NativeMatchService` exposes `header`
  and `runtime_kind` (`"vm"`).
- Terminal `winner`/`termination_reason`/final `score` agree with the
  sibling `result.json` for the same match.
- Loading a legacy v0.1 native-format replay and a legacy v0.2 replay both
  succeed and expose header/tick data through the same API.
- `runtime_kind` is exposed for both a VM replay and a Python replay, on
  both the session and `current_state.runtime_kind`.

**`current_state` / `step_forward` / `restart` correctness**
- After `load`, `current_state.tick == 0` (or the first recorded tick) and
  reflects only that tick's diffs (not a later tick's).
- `step_forward()` applies only the *next* tick's diff on top of existing
  state (a byte written at an earlier tick remains; only the newly-written
  address changes).
- Repeated `step_forward()` reaches the final tick and sets `at_end`.
- `step_forward()` past the final tick raises `ReplaySessionError`
  (message mentions "final tick").
- `restart()` after stepping returns to the initial state and clears
  `at_end`.

**`seek` correctness**
- A forward seek applies only the intervening ticks' diffs.
- A backward seek resets and replays forward to the target tick.
- Seeking to the current tick is a no-op (`seek(t) == current_state` when
  already at `t`).
- Seeking to tick 0 and to the final tick both work, the latter setting
  `at_end`.
- Seeking below or above the replay's recorded range raises
  `ReplaySessionError` (message mentions "outside the replay's recorded
  range").
- Seeking on a replay with no tick records raises `ReplaySessionError`
  (message mentions "no tick records to seek within").
- Seeking after `step_forward()` calls reaches the state a direct seek from
  a fresh session would reach (mixed navigation is still correct).
- Seeking every tick of a real VM replay in order succeeds (canonical
  replays have no tick gaps).
- The reconstructed state at a given tick is identical regardless of the
  cursor's prior history — reached via `seek` alone, via `seek` then
  `seek` again, via `restart()` then `seek`, or via a completely fresh
  session's `seek` — establishing that `seek`'s result is a pure function
  of the target tick.
- `seek` on a sparse legacy replay reaches a recorded tick correctly, and
  raises (message mentions "not recorded in this replay") rather than
  fabricating state for a tick number that falls in a gap.
- `seek` works on legacy v0.1 and v0.2 replays, including reconstructing
  ownership (but not arena byte values, which legacy diffs never captured).
- `current_tick`/`final_tick` are correct before and after a `seek`;
  `final_tick` is stable regardless of cursor position.
- `recorded_ticks` is contiguous (`(0, 1, ..., final_tick)`) for a canonical
  replay and reflects gaps for a sparse legacy replay.
- `at_end` is correct across `seek`, `restart`, and `step_forward` in
  combination, including that `step_forward()` past a `seek`-reached final
  tick still raises.
- The terminal `MatchResult` is never reachable as an extra tick: seeking to
  `final_tick + 1` raises the same "outside the replay's recorded range"
  error as any other out-of-range seek.

**Events**
- `events_at_tick(tick)` returns the recorded events for that tick,
  including for a tick with no events (`()`), and raises
  `ReplaySessionError` (message mentions "no tick") for an unrecorded tick
  number.
- `events_at_tick` after a `seek` still returns the correct recorded events,
  and still raises for an unrecorded tick number.

**Malformed/truncated/structurally-incomplete input**
- A malformed JSON line raises `ReplayFormatError` (not swallowed).
- A failed `load` does not corrupt a previously successfully loaded
  session's current state.
- A replay with no header record raises `ReplaySessionError` (message
  mentions "no header").
- A replay with no result record loads successfully; `winner` and
  `termination_reason` are `None`; tick stepping is unaffected.

**Empty replay**
- A header-only replay (no ticks) is `at_end` immediately, exposes the
  synthesized all-zero tick-0 state, `step_forward()` raises, and
  `restart()` is a defined no-op returning an equal state.

**Duplicate and out-of-order ticks (rejected at `load`)**
- Two `TickSnapshot`s sharing the same `tick` number are rejected by
  `load()` with `ReplaySessionError` (message mentions "not strictly
  greater").
- A `TickSnapshot` whose `tick` is numerically less than the tick recorded
  immediately before it is rejected by `load()` with the same error.

**Sparse (non-contiguous) legacy ticks**
- Gaps between strictly-increasing tick numbers load successfully, and
  `seek` to a recorded tick within a gapped sequence succeeds while `seek`
  into the gap itself raises.

**Read-only state mappings**
- `ReplayState.agents` and `.score` both raise `TypeError` on item
  assignment; `owners` (a `tuple`) and `arena` (`bytes`) likewise reject
  mutation, since both are already-immutable types.
- A failed mutation attempt (caught) never corrupts subsequent stepping —
  the session's next `step_forward()` still produces the correct state.

Reference: `client/tests/test_replay_session.py` (commits `74dcfa6` and
`671d852` combined) already implements this list; the tests are not being
rewritten by this spec, only documented by it.

## 17. Explicitly deferred capabilities for later Phase 7 work

Genuinely deferred — not implemented by either merged commit, and still out
of scope for `ReplaySession` itself:

- Streaming/on-disk-indexed replay support, or any checkpoint format.
- A `battle2.replay` schema version bump.
- Any playback pacing/timing (wall-clock play/pause/speed) *built into
  `ReplaySession` itself* — `ReplaySession` remains a synchronous,
  deterministic state-navigation model with no `sleep`/timer of its own.
  (A `PlaybackController` providing wall-clock pacing on top of
  `ReplaySession` is already merged as a separate class in
  `battle_client.player` — see the provenance note — but that class, and
  its own contract, are not specified by this document.)
- A new headless-analysis CLI/report tool consuming `ReplaySession` (the
  existing CLI wiring added by `671d852` only drives the interactive Pygame
  path via `PlaybackController`/`PygameRenderer`, not a headless report).

No longer deferred (implemented and tested as of `671d852`, and documented
above rather than listed here): `seek(tick)`; strict tick-monotonicity
validation at `load` time; the `recorded_ticks`/`current_tick`/`final_tick`
accessor surface; the `runtime_kind` field on `ReplayState`; read-only
(`MappingProxyType`) `agents`/`score` mappings.

## Design decisions and ambiguities for review

1. **Resolved: this document now covers both merged commits' `ReplaySession`
   changes.** Commit `671d852` ("Phase 7a Slices 2-3") added
   `ReplaySession.seek`, strict tick-monotonicity validation on `load`
   (duplicates and out-of-order ticks are *rejected*, not tolerated — see
   §10), a `recorded_ticks`/`current_tick`/`final_tick` accessor surface, a
   `runtime_kind` field on `ReplayState` itself, and read-only
   (`MappingProxyType`) `agents`/`score` mappings. All of that is now
   specified in the sections above as the current contract. The same
   commit *also* added — separately — a `PlaybackController` plus a
   rewritten `PygameRenderer` with keyboard controls, and CLI wiring
   (`battle_client.cli`) for the interactive Pygame path; that renderer/UI
   portion remains outside this document's scope (§1's non-goals) and is
   documented instead by `docs/MANUAL_SMOKE_TESTS.md`'s "Bytefray
   interactive Pygame replay viewer keyboard controls (Phase 7a)" section.
2. **Resolved: strict tick-number ordering, not tolerance, is the contract.**
   The original slice-1 draft of this document treated non-monotonic ticks
   as a "genuine ambiguity" left open for confirmation. `671d852` resolved
   it: `load` now requires strictly increasing tick numbers (§10), because
   `seek(tick)` requires each tick number to identify exactly one
   deterministic state. This is no longer an open question — it is the
   tested, merged behavior.
3. **Resolved: `events_at_tick`'s tick-number index is one-to-one, not
   "last duplicate wins."** Because duplicate tick numbers are now rejected
   at `load` time (§10), the `{tick_number: index}` lookup table built by
   `load` can never contain a duplicate key — the "which duplicate wins"
   question the original draft raised no longer applies.
4. **Still open: whether `header`/`result` being plain public attributes
   (rather than read-only properties) is acceptable API surface.** This is
   worth a second opinion — everything else on `ReplaySession` is a
   property or method: the two plain attributes are the exception,
   inherited as-is from the original implementation and unchanged by
   `671d852`.
