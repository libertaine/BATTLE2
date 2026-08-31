# Canonical Result Contract

Bytefray v0.3 writes `result.json` using schema `battle2.result`, version 1. The
same high-level envelope represents VM, Python, and pMARS matches.

Required envelope fields are `result_id`, `match_id`, `mode`, `status`, `winner`,
`termination_reason`, `ticks`, `score`, `entrants`, `reproducibility`, `replay`,
and `backend`. Native results reference a replay by `replay_id`, SHA-256 digest,
and portable filename. pMARS results set `replay` to `null`.

## Ruleset identity

`ruleset_id` (v0.10 Phase 4) is an *additive* envelope field: the Bytefray
gameplay Ruleset identity (`battle_engine.rules.BYTEFRAY_RULESET_ID`, see
[RULES.md](RULES.md)) this match executed under. It is **required for
current native writers** — every VM or Python match produced by
`NativeMatchService`/`match_service._finalize_native_artifacts` sets it to the
exact resolved identity (`bytefray-rules-1`, `bytefray-rules-2`, or
`bytefray-rules-4-alpha1`) — but it is **not required for all historical
artifacts**.

**Present-as-`null` versus genuinely absent — these are two different
facts and this schema distinguishes them precisely:**

- `ResultEnvelope.as_dict()` (the one writer both native and pMARS paths
  use) always emits the `ruleset_id` key for *any* result written by the
  current codebase — the exact identity for a native match,
  literally **`"ruleset_id": null`** (key present, JSON `null`) for a
  `redcode94`/pMARS result, since Bytefray Ruleset v1 is not applicable to
  Redcode/pMARS execution (see [RULES.md](RULES.md)'s "Redcode/pMARS — not
  Ruleset v1") and `cli.py`'s pMARS path never passes a value for it. This
  is not a compatibility gap to close — it is the honest, permanent answer
  for that mode, chosen for one consistent writer behavior (the key is
  always present in current output) rather than a per-mode conditional
  key.
- A `battle2.result` v1 result written **before this field existed at
  all** (any pre-Phase-4 artifact, native or pMARS alike) has the key
  genuinely, structurally **absent** — there was no `ruleset_id` concept
  yet, not even a `null` placeholder.
- `read_result`'s `data.get("ruleset_id")` maps both cases to the
  identical Python value, `ResultEnvelope.ruleset_id is None` — the
  envelope itself does not, and need not, distinguish "explicitly declared
  not applicable" from "predates this concept." `resolve_result_ruleset`
  (below) recovers that distinction from `mode`, which is the field that
  actually carries it, not from whether the JSON key was present.

No `battle2.result` schema bump was required to add this field: every
released `read_result` implementation constructs its `ResultEnvelope` by
extracting named keys it already expects and has never rejected an
unrecognized key (verified directly, not merely inferred, against the
`v0.9.0`-tagged `result_model.py` in an isolated worktree — see
`docs/COMPATIBILITY.md`). `battle_engine.result_model.
resolve_result_ruleset(envelope)` gives the honest, confidence-qualified
answer regardless of which of the two `None` cases above produced it:
`"recorded"` when `ruleset_id` is a non-null string, `"recovered"`
`bytefray-rules-1` for a native (`mode: "b2"`) result with a `None` value
(the schema itself never existed before v0.3.0, and VM/Python gameplay
semantics are proven byte-for-byte unchanged across the entire
`battle2.result` v1 lifetime — see [RULES.md](RULES.md)), `"not_applicable"`
for any `redcode94` result with a `None` value (whether that `None` came
from an explicit current-writer `null` or a genuinely absent historical
key), or `"unknown"` for anything else.

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
  "ruleset_id": "bytefray-rules-1",
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
asserts a changed seed or changed agent bytecode changes it;
`test_canonical_match_id_changes_if_ruleset_identity_changes` (added with
this section) proves `ruleset_id` is a live input to the hash, not
decorative, by monkeypatching the canonical constant `canonical_match_id`
reads and confirming the computed id changes.

**`ruleset_id` is a first-class input to `match_id`'s hash payload,
sibling to `reproducibility`/`entrants` (v0.10 Phase 4) — never folded
into `reproducibility`, which is specifically about per-match
*configuration*, not gameplay identity (see
[RULES.md](RULES.md)'s "Configuration values are not Ruleset identity").**
Two otherwise-identical results could not legitimately share one identity
if they ran under different gameplay Rulesets, so this closes that latent
risk directly rather than deferring it. `result_id`/`replay_id` are not
separately updated to hash `ruleset_id` again — both already derive from
(embed) `match_id`, so they inherit this dependency transitively.

**This was a deliberate, one-time native-ID transition, not a silent
break.** Because exactly one Ruleset (`BYTEFRAY_RULESET_ID =
"bytefray-rules-1"`) existed at v0.10 Phase 4, this literal string was hashed
into every current match's identity where it previously was not —
meaning a v0.10 Phase 4+ build computes a **different** `match_id`/
`result_id`/`replay_id` than a pre-Phase-4 build would for byte-identical
execution inputs. Concretely:

- **Historical, already-persisted `match_id`/`result_id`/`replay_id`
  values are never rewritten** — reading an old artifact is completely
  unaffected; this only changes what a *fresh* run computes.
- **Re-running "the same match" under v0.10 Phase 4+ produces a new,
  different id** than an equivalent pre-Phase-4 run would have, even with
  identical seed/config/entrants. This is intentional: identity now
  encodes gameplay semantics, closing the risk that a future Ruleset v2
  match could otherwise collide under the same `match_id` as a Ruleset v1
  match with coincidentally identical configuration/entrants.
- **Resume consequence**: `tournament_service`/`agent_evaluation` resume
  verification recomputes the *expected* `match_id` fresh from current
  code and compares it against what a prior run's `result.json` actually
  recorded (`tournament_service._resumed_result_mismatch`/
  `agent_evaluation._resumed_cell_mismatch`). A `tournament.json`/
  `evaluation.json` left mid-run by a pre-Phase-4 build will therefore show
  every not-yet-verified completed match/cell as `resumed_result_mismatch`
  and get demoted to `corrupted` on the first v0.10 Phase 4+ resume —
  exactly the existing, safe, fail-closed behavior an unrelated
  `match_id` mismatch already produces, never a crash or silent
  acceptance. The operator's remedy is the same as for any other
  `corrupted` state: `--retry-failed`, or start fresh. This mirrors the
  precedent already established when `bytefray.evaluation` moved v1 → v2
  (a v0.6.1 evaluation directory was never implicitly resumed by an
  equivalent v0.7 invocation, because v2's identity payload was strictly
  richer) — see `ARCHITECTURE.md`'s "Evaluation History (v0.7)".

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
CLI path (`bytefray run`) has no equivalent exposure, because its entrant IDs
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
