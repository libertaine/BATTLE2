# Bytefray Compatibility Reference

This is a concise policy/reference document, not a duplicate of every
schema specification: it names the independent compatibility axes Bytefray
maintains, says what is a stable-candidate contract for the 1.x series
versus explicitly unsupported/experimental, and gives a worked table for
deciding which axis a given change actually requires bumping. For the full
wire-level detail behind each axis, follow the links below rather than
expecting this document to repeat them.

## Stable-candidate contracts for 1.x

The following are candidates for a stable-contract declaration at 1.0 —
see `docs/ROADMAP.md` for the release criterion this feeds into:

- **Ruleset v1** (`bytefray-rules-1`) — the gameplay semantics described in
  [RULES.md](RULES.md).
- **Agent API v1** — the Python loading/lifecycle/`Observation`/
  `AgentAction` contract and its frozen deterministic RNG derivation,
  described in [AGENT_API_V1.md](AGENT_API_V1.md).
- **Result and replay current schemas** — `battle2.result` v1 and
  `battle2.replay` v3, described in [RESULT_SCHEMA.md](RESULT_SCHEMA.md)
  and [REPLAY_SCHEMA.md](REPLAY_SCHEMA.md).
- **Evaluation current schema/history behavior** — `bytefray.evaluation`
  v4/identity v4 and the `evaluations list/show/compare` history behavior
  described in `docs/specs/evaluation_history.md`.
- **Agent revision identity/verification behavior** — the content-
  addressed revision store described in `docs/specs/agent_revision.md`.
- **Canonical CLI surfaces where explicitly supported** — `bytefray run`,
  `bytefray tournament`, `bytefray replay`, `bytefray agents
  create/validate/test/evaluate/inspect/diverge/revisions/evaluations`,
  and their documented flags (README.md, `docs/AGENT_LAB.md`,
  `docs/TOURNAMENTS.md`).

## Separate compatibility axes

These axes are independent and must not be conflated — a change to one
does not imply, and should not silently piggyback on, a change to another:

| Axis | What it identifies | Where it lives |
|---|---|---|
| Project/package version | The installable release (e.g. `0.10.0`). | `pyproject.toml` / `ProjectInfo.version`. |
| Agent API version | The Python agent programming contract, including RNG derivation. | `battle_engine.agent_api.AGENT_API_VERSION`. |
| Ruleset identity | The gameplay rules of the game itself. | `battle_engine.rules.BYTEFRAY_RULESET_ID`. |
| Artifact schema versions | Wire shape of persisted artifacts. | `battle_engine.replay.SCHEMA_VERSION` (`battle2.replay`), `battle_engine.result_model` (`battle2.result`), `battle_engine.agent_evaluation.SCHEMA_VERSION`/`IDENTITY_VERSION` (`bytefray.evaluation`), `battle_engine.agent_trace` (`bytefray.agent_trace`). |
| Evaluation methodology fields | How `agents evaluate` measures agents (orientation coverage, arena-alignment disclosure), not gameplay itself. | `bytefray.evaluation`'s `orientation_mode`/`arena_alignment_mode` fields. |
| Agent revision identity | Content-addressed identity of one archived copy of an agent's source. | `battle_engine.agent_revisions`. |
| Source fingerprint versions | Deterministic hash-scope versioning for drift detection. | `battle_engine.agent_api.LOCAL_SOURCE_FINGERPRINT_VERSION`, `battle_engine.agent_revisions`' own fingerprint version. |

A gameplay-semantic change bumps exactly the Ruleset identity. A Python
programming-contract change (including an incompatible RNG-derivation
change) bumps exactly the Agent API version. A wire-shape change bumps
exactly the relevant schema version. None of these three should ever
require bumping either of the other two on its own — see the table below
for worked examples, including cases where a change legitimately requires
more than one axis at once.

## Ruleset identity

```python
BYTEFRAY_RULESET_ID = "bytefray-rules-1"
```

defined in `battle_engine.rules`. See [RULES.md](RULES.md) for the full
Ruleset v1 contract and its bump policy.

## Historical alias: evaluation-rules-1 ↔ bytefray-rules-1

`bytefray.evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` (wire field
`rules_compatibility_id`, introduced in v0.7.0 as the literal string
`"evaluation-rules-1"`) is, as of v0.10 Phase 2, a derived alias of
`BYTEFRAY_RULESET_ID`:

```python
EVALUATION_RULES_COMPATIBILITY_ID = BYTEFRAY_RULESET_ID
```

This is justified by direct inspection of the gameplay-semantic source
history — see [RULES.md](RULES.md)'s "Historical relationship to
evaluation-rules-1" section for the git-history evidence — which shows the
gameplay semantics `"evaluation-rules-1"` was always narrowly scoped to
(scoring, winner resolution, Python scheduling order, derived-seed policy)
have been unchanged for the value's entire existence.

This alias does **not** rewrite history. An `evaluation.json` artifact
persisted before this alias existed still literally contains the string
`"evaluation-rules-1"` in its `rules_compatibility_id` field; it never
contained, and readers must never pretend it contained, the string
`"bytefray-rules-1"`. Historical wire field names (`rules_compatibility_id`)
are unchanged, and comparison behavior between two artifacts' recorded
values is unchanged — only how the *current* value is computed changed,
from an independently maintained literal to a derived one. The practical
effect going forward: a gameplay-semantic change requires exactly one
Ruleset bump, not a Ruleset bump plus a separate hand-maintained
evaluation-rules bump.

## Experimental/unsupported boundaries

The following are explicitly **not** part of the 1.x stability promise,
regardless of how mature adjacent functionality is:

- **Mixed VM/Python matches** — rejected outright; not implemented.
- **Security sandboxing of Python agent code** — the Agent Lab
  worker-subprocess timeout (`docs/AGENT_LAB.md`) is development-time hang
  **containment**, not a security sandbox; agent code runs with the same
  OS privileges as its host process.
- **Hard callback containment on every execution path** — only
  `bytefray agents test`/`agents validate` run supervised by default;
  `bytefray run`/`tournament` still run Python entrants in-process with no
  hard timeout.
- **Replication / corruptible Python-core designs** — research-stage
  ideas tracked in [FUTURE_PLANS.md](FUTURE_PLANS.md), not implemented.
- **Redcode/pMARS authoring, evaluation, and gameplay parity with the
  native engine** — pMARS interoperability continues, but does not use
  Bytefray Ruleset v1, Agent API v1, or the canonical replay schema; see
  [RULES.md](RULES.md)'s "Redcode/pMARS — not Ruleset v1".
- **Arena translation/placement robustness in evaluation** — arena
  alignment is currently fixed and disclosed as untested by
  `agents evaluate`; see `docs/ROADMAP.md`.
- **Future rulesets** (advanced offensive mechanics, arena-size research,
  multipronged agents, replication) — anything in that category would
  require a Ruleset identity beyond `bytefray-rules-1`, tracked in
  [FUTURE_PLANS.md](FUTURE_PLANS.md), and is explicitly not part of
  Ruleset v1.

## Compatibility-change impact table

| Change | Ruleset bump | Agent API bump | Schema bump | Methodology change |
| --- | ---: | ---: | ---: | ---: |
| Territory scoring formula | yes | no | no | no |
| Default territory weight | no | no | no | no |
| Arena-size default | no | no | no | no |
| Ownership semantics | yes | maybe, only if API exposure changes | no | no |
| Kill attribution | yes | no | no | no |
| Python RNG derivation | no | yes | no | no |
| Existing `ActionKind` redefined | possibly yes | yes | maybe | no |
| Candidate-first → both orientations | no | no | no | yes |
| Fixed alignment → translation suite | normally no | only if API semantics change | maybe, only if wire shape changes | yes |
| Replay optional telemetry field | no | no | normally no (additive) | no |
| Revision-store sharding | no | no | no | no |

Use this table as a starting heuristic, not a substitute for judgment —
verify a specific change's actual effect against [RULES.md](RULES.md),
[AGENT_API_V1.md](AGENT_API_V1.md), and the relevant schema document
before deciding which axis to bump.
