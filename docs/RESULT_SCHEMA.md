# Canonical Result Contract

Bytefray v0.3 writes `result.json` using schema `battle2.result`, version 1. The
same high-level envelope represents VM, Python, and pMARS matches.

Required envelope fields are `result_id`, `match_id`, `mode`, `status`, `winner`,
`termination_reason`, `ticks`, `score`, `entrants`, `reproducibility`, `replay`,
and `backend`. Native results reference a replay by `replay_id`, SHA-256 digest,
and portable filename. pMARS results set `replay` to `null`.

Native entrant records include identity, final state, score, statistics,
termination reason, optional structured diagnostic, and execution metadata.
Python metadata includes API version, agent version, derived seed, request slot,
and source digest. VM metadata includes entry address and bytecode digest.

## Identity recipe

`match_id` and `result_id` are both `stable_id(prefix, value)` --
`f"{prefix}_{sha256(canonical_json(value)).hexdigest()[:24]}"`, where
`canonical_json` is `json.dumps(value, sort_keys=True, separators=(",", ":"))`.
Sorted keys make the digest independent of dict-construction order; list
order is never left to incidental iteration (entrant order always comes from
the caller-supplied, positionally-ordered entrant tuple).

`match_id` is hashed from execution inputs only, never from outcome:

```text
{
  "mode": "b2",
  "reproducibility": {
    "seed", "arena_size", "tick_limit", "action_budget", "win_mode",
    "weights", "entrant_order"
  },
  "entrants": [
    {"agent_id", "name", "metadata"}   # metadata: content digests + slot/API
                                        # version info, never a filesystem path
    ...
  ],
}
```

Two matches run against byte-identical agent content and configuration always
get the same `match_id`, regardless of the absolute path either checkout used
-- entrant `metadata` carries content digests (`code_sha256` for VM,
`source_sha256` for Python), never a path. `engine/tests/test_replay_reconstruction.py`
pins this directly: `test_match_id_is_stable_across_different_absolute_checkout_paths`
runs the identical logical match from two different directory trees and
asserts equal `match_id`s; `test_match_id_changes_with_meaningful_config_or_code_changes`
asserts a changed seed or changed agent bytecode changes it.

`result_id` additionally covers the outcome (`winner`, `termination_reason`,
`ticks`, `score`, and full per-entrant `entrants` records including
statistics and diagnostics) -- but **excludes** raw exception message text
from that hash. A `diagnostic.message` field is built from `str(exception)`
and can embed nondeterministic content (a default object `repr()` carries an
`id()`-based memory address, for instance); including it in the identity hash
would make `result_id` unstable across two otherwise-identical reruns of a
match that happens to hit the same agent failure. The full message remains in
`result.json`'s `entrants[].diagnostic.message` for humans to read -- only the
hash input for `result_id` strips it, via `match_service._identity_safe_diagnostic`.
`test_result_id_is_stable_despite_nondeterministic_exception_text` proves this:
it runs the same failing match twice, confirms the two runs' exception
messages really do differ (proving the nondeterminism is real, not assumed),
and confirms `result_id` is identical anyway.

The result stores the digest of the completed replay; the replay header
stores both IDs. The replay does not contain its own digest because that
would be self-referential. Because the canonical writer serializes through
the same `write_replay`/`serialize_record` path any reader uses (sorted keys,
stable separators), the stored digest is verifiable, not just descriptive --
see `battle_engine.result_model.verify_replay_digest` /
`verify_result_replay`, and [REPLAY_SCHEMA.md](REPLAY_SCHEMA.md#digest-verification).

## Winner representation

`result.json`'s `winner` field is a required, non-null string. When there is
no single winner, it is the literal value `"tie"`
(`results.WINNER_TIE_SENTINEL`) rather than `null`, for compatibility with
existing consumers that already treat `winner` as always a string (including
the v0.2 `summary.json` adapter). `"tie"` is a **reserved entrant identifier**:
`TournamentService` rejects any entrant whose ID case-insensitively equals
`"tie"` before scheduling a single match, so it can never collide with a real
winner value (see `tournament_service._validate`). The native single-match
CLI path (`battle2 run`) has no equivalent exposure, because its entrant IDs
are always the fixed slots `"A"`/`"B"`/`"C"`, never a user- or manifest-supplied
name.

The canonical **replay's** terminal result record uses `null` instead of
`"tie"` for its `winner` field -- that field was not previously populated at
all (see REPLAY_SCHEMA.md's "Terminal result record"), so introducing it with
the cleaner, unambiguous `null` convention is not a compatibility break the
way changing `result.json`'s already-typed, already-consumed `winner: str`
field would be. `NativeMatchResult.winner` and `result.json`'s `winner` keep
the pre-existing `"tie"` string in all cases.

`results.resolve_winner` is the single implementation of winner resolution,
shared by the VM (`core.Kernel.run`) and Python (`python_runtime`) paths.
`match_service._effective_winner` is only a thin, non-recomputing mapper from
`resolve_winner`'s `""` ("no winner") to the display sentinel.

## Termination vocabulary

Native match-level termination uses one shared, closed enum
(`python_runtime.TerminationReason`, despite the module name -- it is reused
by the VM path too): `last_agent_standing`, `all_agents_dead`, `tick_limit`.
Per-entrant termination is a separate, deliberately smaller vocabulary:
`normal_halt` or `forfeit`, populated only for Python entrants (`null` for
every VM entrant -- the native VM scheduler does not track a per-agent
termination reason at this granularity; see REPLAY_SCHEMA.md's runtime-kind
table). pMARS results set `termination_reason` to the backend-specific value
`"backend_completed"`, which is intentionally **not** part of the native
enum -- pMARS is architecturally separate, and forcing a false equivalence
between "the native scheduler determined a stopping condition" and "the
pMARS subprocess exited" would misrepresent what's actually known about a
pMARS match's ending.

## Digest integrity

`read_result` does not verify the replay it references -- reading a
`result.json` never requires its replay to exist or match, so historical
results remain readable even if a replay was pruned or moved. Call
`battle_engine.result_model.verify_replay_digest` (or `verify_result_replay`)
explicitly at a canonical-artifact boundary (for example, before a Phase 7
tool builds an index over a directory of results) to confirm a replay is
present, readable, and byte-identical to what `result.json` recorded.
Verification raises `ReplayIntegrityError` with a stable `.code`
(`replay_reference_missing`, `replay_file_missing`, `replay_file_unreadable`,
`replay_digest_mismatch`) rather than a bare exception.

`summary.json` remains the v0.2 compatibility adapter for existing consumers.
New integrations should consume `result.json`.
