# Changelog

This changelog records notable user- and developer-visible changes to Bytefray.

## [4.0.0-alpha1] - 2026-08-31

### Bytefray 4.0 Alpha 1 — The Spatial Multi-Process Update

This is an alpha release of Bytefray's new spatial multi-process model.
It concludes the R0-R6 research phase and introduces sweeping changes to gameplay mechanics.
Old agents and legacy rulesets are fundamentally incompatible with these mechanics.

* **Multi-Process Spatial Entrants**: Agents can now declare fixed rosters of multiple independent processes.
* **Local Reach and Movement**: `MOVE` is now a primary action. `READ` and `WRITE` are restricted to a local `reach` radius around the acting process's anchor.
* **Deterministic Chunked Scheduler**: The scheduler now executes chunked turns (`K=2`) with a deterministic rotating start based on original seat order.
* **Temporary Anchor Disruption**: A legal enemy `WRITE` to a process's exact anchor location causes temporary disruption (`D=1`), suppressing its remaining callbacks in that tick and recovering at the next tick.
* **Fair Quota Redistribution**: Quota from disrupted processes is redistributed fairly to surviving eligible processes, conserving the $Q=8$ entrant total.
* **Local Process Detection**: Entrants automatically detect exact locations of live enemy processes within any friendly process's `reach`.
* **Agent API v2**: The `Observation` contract is redesigned around minimal temporal provenance, removing legacy VM registers and explicit hit-confirmation to preserve fog-of-war.
* **Process-Aware Replay & Tooling**: `battle2.replay` schema bumped to v4, adding `ProcessState` visualization support.
* **New v4 Starter Agents**: Added `v4_claimer`, `v4_concentrated_attacker`, `v4_local_defender`, `v4_scout`, and `v4_defender_scout`; historical starters remain packaged for Ruleset-v1/v2 compatibility.

**Note**: This is an alpha release. We explicitly solicit feedback on whether spatial processes are understandable, positioning feels meaningful, and if the $Q=8$ disruption tradeoff feels fair.

## [3.0.0] - 2026-08-30

### Bytefray 3.0 — stable release

Promotes the qualified `v3.0.0-rc2` candidate to the stable 3.0 line with no
engine, UI, schema, or evaluation-methodology change since RC2 — this entry
is a version/documentation-only release, not new development. `bytefray-rules-2`
remains v3.0's unchanged active gameplay identity, Agent API v1 is unchanged,
`bytefray-rules-1`/VM-blob compatibility is unchanged, and Redcode/pMARS
remains retained external interoperability outside the Bytefray Ruleset
system. This entry summarizes the whole v3.0 release (alpha1 + alpha2 +
RC1 + RC2 combined). See
[V3_RC1_QUALIFICATION.md](docs/archive/v3/V3_RC1_QUALIFICATION.md) and
[V3_RC1_DEFAULT_RULESET_DEFECT.md](docs/archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md)
for the full qualification and defect-fix records, and
[V3_RULESET_RESEARCH_SUMMARY.md](docs/archive/v3/V3_RULESET_RESEARCH_SUMMARY.md) for
the closed research program behind the "no Ruleset-3" decision.

- **Agent creation** — a second "Annotated Example" scaffold alongside the
  original blank template (CLI and Agent Designer both), a Development-tab
  Reload affordance wired into Validate/Test, selectable/copyable
  diagnostics text, and two new bundled Python starters, **Raider** and
  **Sentinel**, that demonstrate deliberate Vulnerable-Core offense and
  defense (growing the Python starter set from five to seven).
- **Replay Viewer** — shared Bytefray branding, a whole-match timeline with
  click/drag seeking, and an in-HUD "CORE CAPTURED" callout naming the
  victim and captor.
- **Strategy analysis** — visual win-rate/confidence-interval bars,
  core-capture rate bars, an 11-dimension behavior-profile panel, and a
  `--json` structured evaluation output mode.
- **Evaluation workflow** — a GUI worker-count control, non-default-condition
  disclosure in evaluation history, one-click access to an evaluation's
  output folder, and explicit Ruleset selection for both Agent Development
  tests and pairwise evaluation (both default to `bytefray-rules-2`; Ruleset
  v1 remains selectable for Python compatibility testing).
- **CLI** — `bytefray agents` marks each discovered agent `[Python]` or
  `[VM]` with a short legend, so runtime-kind/Ruleset compatibility is
  visible without cross-referencing documentation. An omitted `--ruleset`
  (`bytefray run`, `agents test`, `agents evaluate`, `tournament`) now
  resolves to `bytefray-rules-2` for Python-only matches and
  `bytefray-rules-1` for VM/blob-only matches, matching Agent Designer's
  own default and fixing the CLI/GUI gameplay divergence RC1 shipped with
  (see the RC2 entry below).
- **Distribution** — a qualified Windows installer and portable build, wheel
  and sdist, a fixed frozen-build packaging gap (the "Annotated Example"
  template and both new starters are confirmed present in every packaged
  distribution), and corrected/expanded installation documentation.
- **Compatibility** — no change to `bytefray-rules-2` gameplay, Agent API v1,
  result/replay schemas, or scoring/scheduler/core-capture semantics.
  `bytefray-rules-1` and VM/blob entrants remain fully supported.
  Redcode/pMARS remains a separate, external interoperability path that uses
  no Bytefray Ruleset.

See `docs/ROADMAP.md`'s `v3.0.0-alpha1` through `v3.0.0-rc2` sections for
the full phase-by-phase development record.

## [3.0.0-rc2] - 2026-08-29

### Bytefray 3.0 — release candidate 2

The second **release candidate** for Bytefray v3.0, fixing one defect found
in RC1 after it was tagged and published: `bytefray-rules-2` remains v3.0's
unchanged active gameplay identity, Agent API v1 is unchanged, and
`bytefray-rules-1`/VM-blob compatibility is unchanged. No new product
feature was added; see
[V3_RC1_DEFAULT_RULESET_DEFECT.md](docs/archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md)
for the full defect record and fix.

### Fixed

- **CLI/GUI default-Ruleset divergence (RC1 defect).** Changed omitted
  Ruleset resolution for new CLI gameplay: Python-only matches (`bytefray
  run`, `agents test`, `agents evaluate`, `tournament`) now default to
  Ruleset v2, matching Agent Designer's current gameplay default;
  VM/blob-only matches continue to default to Ruleset v1, and a mixed
  Python/VM request without an explicit `--ruleset` keeps its existing
  Ruleset-v1 default and incompatibility behavior. Explicit `--ruleset`
  selections are unchanged. This fixes materially different CLI/GUI
  behavior around vulnerable-core capture: a new user running an ordinary
  Python-agent match through the CLI with no `--ruleset` previously got a
  Ruleset-v1 game (no core-capture termination available) while the same
  agents through Agent Designer got Ruleset v2; both now converge. This is
  a default-selection policy correction, not an engine or gameplay-rules
  change -- `bytefray-rules-1` and `bytefray-rules-2` semantics are both
  unchanged, and a historical evaluation/tournament artifact that recorded
  an omitted-Ruleset run under v1 still means v1. See
  [V3_RC1_DEFAULT_RULESET_DEFECT.md](docs/archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md).

## [3.0.0-rc1] - 2026-08-27

### Bytefray 3.0 — release candidate 1

The first **release candidate** for Bytefray v3.0. `bytefray-rules-2` remains
v3.0's unchanged active gameplay identity, Agent API v1 is unchanged, and
`bytefray-rules-1`/VM-blob compatibility is unchanged; Redcode/pMARS remains
retained external interoperability outside the Bytefray Ruleset system.
Bytefray v3.0 is now treated as **feature-complete**: this entry summarizes
the whole v3.0 release (alpha1 + alpha2 combined), not just what changed
since alpha2. See
[V3_RC1_QUALIFICATION.md](docs/archive/v3/V3_RC1_QUALIFICATION.md) for the full RC1
qualification record and [V3_RULESET_RESEARCH_SUMMARY.md](docs/archive/v3/V3_RULESET_RESEARCH_SUMMARY.md)
for the closed research program behind the "no Ruleset-3" decision.

- **Agent creation** — a second "Annotated Example" scaffold alongside the
  original blank template (CLI and Agent Designer both), a Development-tab
  Reload affordance wired into Validate/Test, selectable/copyable
  diagnostics text, and two new bundled Python starters, **Raider** and
  **Sentinel**, that demonstrate deliberate Vulnerable-Core offense and
  defense (growing the Python starter set from five to seven).
- **Replay Viewer** — shared Bytefray branding, a whole-match timeline with
  click/drag seeking, and an in-HUD "CORE CAPTURED" callout naming the
  victim and captor.
- **Strategy analysis** — visual win-rate/confidence-interval bars,
  core-capture rate bars, an 11-dimension behavior-profile panel, and a
  `--json` structured evaluation output mode.
- **Evaluation workflow** — a GUI worker-count control, non-default-condition
  disclosure in evaluation history, one-click access to an evaluation's
  output folder, and explicit Ruleset selection for both Agent Development
  tests and pairwise evaluation (both now default to `bytefray-rules-2`;
  Ruleset v1 remains selectable for Python compatibility testing; the CLI's
  own default is unchanged).
- **CLI** — `bytefray agents` now marks each discovered agent `[Python]` or
  `[VM]` with a short legend, so runtime-kind/Ruleset compatibility is
  visible without cross-referencing documentation.
- **Distribution** — a qualified Windows installer and portable build, wheel
  and sdist, a fixed frozen-build packaging gap (the "Annotated Example"
  template and both new starters are confirmed present in every packaged
  distribution), and corrected/expanded installation documentation
  (unsigned-installer SmartScreen disclosure, macOS distribution position,
  current-version examples).
- **Compatibility** — no change to `bytefray-rules-2` gameplay, Agent API v1,
  result/replay schemas, or scoring/scheduler/core-capture semantics.
  `bytefray-rules-1` and VM/blob entrants remain fully supported.
  Redcode/pMARS remains a separate, external interoperability path that uses
  no Bytefray Ruleset.

## [3.0.0-alpha2] - 2026-08-27

### Strategy examples and Ruleset clarity

A small second **alpha prerelease**. `bytefray-rules-2` gameplay is
unchanged, Agent API v1 is unchanged, and every existing compatible agent
remains valid. See
[V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md](docs/archive/v3/V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md)
for this alpha's qualification record.

- **New starter strategies** — two bundled Python starters demonstrate
  Ruleset v2's defining Vulnerable Core mechanic, which none of the five
  existing territorial starters engage with at all:
  - **Raider** actively searches for a vulnerable enemy core with `READ`,
    confirms the location before committing, and then attacks it. It also
    demonstrates the structural fix for the most common Agent API v1
    correctness mistake: recording the address a `READ` is waiting on so
    `Observation.last_read` is consumed exactly once rather than re-read
    stale.
  - **Sentinel** deliberately spends one action in every four re-securing
    its own core instead of expanding, making the cost of defending
    measurable.

  Neither is an optimal strategy, and both typically hold less territory
  than the pure expansion starters — that trade-off is the lesson. Both are
  independently maintained product agents derived from frozen research
  reference agents, not copies of the benchmark artifacts themselves, and
  neither is a benchmark member.
- **Ruleset clarity** — the Agent Designer now states, and lets you choose,
  the Ruleset it actually uses:
  - Agent Development's development tests gained an explicit Ruleset
    control, **now defaulting to `bytefray-rules-2`**. Previously this path
    passed no `--ruleset` at all and silently inherited the CLI's
    backward-compatible Ruleset-v1 default while the Simple/Advanced match
    tabs beside it defaulted to v2. The completed-test result reports the
    Ruleset the tool itself ran under. Ruleset v1 remains selectable for
    Python compatibility testing. **This is an intentional GUI-default
    behavior change**; the CLI's own default is unchanged.
  - Pairwise evaluation gained the same explicit control, also defaulting
    to `bytefray-rules-2`, and always sends `--ruleset` explicitly rather
    than inheriting a default. A preset that names its own Ruleset is
    surfaced into the selector rather than silently overridden. Group
    evaluation remains Ruleset-v2-only, unchanged. No existing evaluation's
    identity or resume behavior moves.
  - `bytefray agents` listing now marks each entry `[Python]` or `[VM]`,
    the same vocabulary the Designer's match selectors already use, with a
    short legend stating which Rulesets each runtime kind can use. No
    persisted schema changed.
  - Ruleset descriptions now state the compatibility rule in both
    directions: Ruleset v2 runs Python agents only; Ruleset v1 also runs
    Python agents and is the only Bytefray ruleset that runs VM/blob
    agents. The Ruleset v1 option is labeled "Compatibility (Python and
    VM/blob)" rather than "Legacy / VM compatibility", which understated
    its Python support.
- **Fixed** — the `bytefray agents` listing used a non-ASCII placeholder for
  "no blob", which the frozen Windows executable rendered as a replacement
  character where the source build did not. It is now ASCII `none`.
- **VM/blob compatibility** is unchanged and remains Ruleset-v1-only.
  **Redcode/pMARS** remains external interoperability that uses no Bytefray
  Ruleset at all — no product or UI text assigns it one, and no Designer
  VM/Redcode tab was added.

## [3.0.0-alpha1] - 2026-08-26

### Bytefray 3.0 — first alpha prerelease

This is an **alpha prerelease**, not a stable release. Bytefray v3.0 is a
product cycle, not a gameplay cycle: it ships `bytefray-rules-2` unchanged
(the closed v3 Ruleset research program found no evidence justifying a
gameplay-semantic change — see
[V3_RULESET_RESEARCH_SUMMARY.md](docs/archive/v3/V3_RULESET_RESEARCH_SUMMARY.md)) and
focuses on presentation, agent creation, strategy analysis, evaluation
infrastructure, and distribution quality. See
[V3_PRODUCT_SCOPE.md](docs/archive/v3/V3_PRODUCT_SCOPE.md) for the full product thesis
and [V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md](docs/archive/v3/V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md)
for this alpha's integration/distribution qualification record.

- **Presentation** — the Replay Viewer's header band carries shared
  Bytefray branding; a restrained "CORE CAPTURED" callout appears in the
  top HUD band during normal forward playback when a core-capture event
  occurs, naming the victim (and captor, when attributable), then
  disappears automatically; and a whole-match timeline with click/drag
  seeking sits in the footer band alongside existing playback controls. No
  Ruleset, scoring, scheduler, Agent API, or replay-schema change.
- **Agent creation** — a second, self-contained "Annotated Example"
  scaffold template (`bytefray agents create --template annotated`, and the
  matching Agent Designer New Agent choice) alongside the original blank
  template; a Development-tab Reload affordance wired into Validate/Test;
  and selectable/copyable status and error text.
- **Strategy analysis** — a `--json` mode for `agents evaluate`; visual
  win-rate/confidence-interval and behavior-profile widgets in both the
  live-run results dialog and the evaluation-history dialog; and two
  disclosed v1.6 Phase 6 evaluation-comparison defects resolved. Evidence
  presentation only — no Elo/Glicko, composite rating, clustering, or
  AI-generated strategic text.
- **Evaluation infrastructure** — `EvaluationHistoryDialog` gained the
  CLI's existing non-default-condition disclosure and an "Open Evaluation
  Folder" action; the Designer's Evaluate dialog gained the CLI's
  already-shipped `--workers` worker-pool control (confirmed
  identity-inert); and a GUI comparison-ambiguity state now discloses the
  detail in place instead of directing the user back to the CLI.
- **Distribution** — fixed a real, previously-shipped packaging gap where
  `tools/bytefray.spec` and `tools/agent_designer.spec` bundled the
  original "blank" agent-scaffold template but never the Annotated Example
  template added above, so the frozen Windows builds silently lacked it;
  corrected stale `1.6.0`-era filenames/version references in
  [INSTALL.md](INSTALL.md), [docs/LINUX_INSTALL.md](docs/LINUX_INSTALL.md),
  and [SECURITY.md](SECURITY.md) that had drifted from the already-current
  `2.0.0` line; and qualified the Windows portable/installer, Python
  wheel/sdist, and integrated create → validate → test → evaluate → replay
  workflow against the packaged product, not only a source checkout.

### Compatibility

- **Ruleset v2** (`bytefray-rules-2`) ships unchanged as v3.0's active
  gameplay identity, alongside frozen Ruleset v1.
- **Agent API v1 is unchanged** — there is no Agent API v2 in this release;
  every existing compatible agent continues to run unmodified.
- No result/replay/evaluation artifact schema change. Historical artifacts
  of every prior version remain readable.

### Scope boundaries

This alpha is a distribution/integration checkpoint on top of Phases 1-4,
not a new development phase — see
[V3_PRODUCT_SCOPE.md](docs/archive/v3/V3_PRODUCT_SCOPE.md) §5 for the full v3.0
non-goals list (no new Ruleset, no Agent API v2, no scheduler rewrite, no
new scoring/rating system, among others). Feedback is explicitly sought on
product experience — agent-creation clarity, evaluation-result
understandability, and Replay Viewer usability — not on Ruleset-3 gameplay,
which remains on hold.

## [2.0.0] - 2026-08-24

### Bytefray 2.0 — stable release

Promotes the qualified `v2.0.0-rc2` candidate to the stable 2.0 line with no
engine, UI, schema, or evaluation-methodology change since RC2 — this entry
is a version/documentation-only release, not new development.

- **Ruleset v2** (`bytefray-rules-2`) is now a permanent, stable gameplay
  identity alongside frozen Ruleset v1 (`bytefray-rules-1`): a small
  vulnerable core per entrant enables decisive captures instead of relying
  only on territory scores at the tick limit, with owner-maintained core
  observability and RC2's corrected deterministic, non-overlapping
  omitted-start placement (fails closed on any resolved overlap, including
  arena wraparound).
- **Multi-entrant execution and evaluation**: real 3+-entrant native matches,
  Designer Group Evaluation with canonical roster/layout/seat-assignment
  preview, per-entrant outcome/capture/behavior analysis, and Pairwise
  evaluation's Wilson-interval/significance/behavior-profile analytics — all
  fully derived from existing canonical evaluation artifacts, no ranking
  system or schema redesign.
- **Agent Designer**: explicit Ruleset selection on Simple/Advanced direct
  matches and Development Test (Python-vs-Python defaults to v2; VM/blob
  selections fall back to v1), read-only `agent.py`/`agent.yaml` source
  inspection, and Group Evaluation integration alongside the already-shipped
  evaluation history, revision provenance, and package import/export
  workflows.
- **Replay Viewer**: responsive detailed/compact entrant HUD layouts,
  centered integer arena scaling, and group-aware presentation for
  multi-entrant Ruleset-v2 replays.
- **Compatibility retained throughout**: Agent API v1, all persisted result/
  replay/evaluation/package schemas, canonical match identity rules,
  evaluation methodology, and scheduler/winner/scoring semantics are
  unchanged from the 1.x line, and full Ruleset-v1/VM/blob execution remains
  supported; historical 1.x and 2.0 alpha/beta/RC artifacts remain readable
  and are not reinterpreted.

See `docs/ROADMAP.md`'s `v2.0.0-beta1` through `v2.0.0-rc2` sections for the
full phase-by-phase development record, and `docs/RULES_V2.md` for the
complete Ruleset v2 gameplay reference.

## [2.0.0-rc2] - 2026-08-24

### Fixed omitted-start Ruleset-v2 default placement (RC1 release blocker)

- `bytefray run` (and, transitively, Agent Designer's Simple/Advanced direct
  matches and Development Test, none of which ever set a start address)
  previously defaulted every omitted `--a-start`/`--b-start`/`--c-start` to
  the literal integer `0`. Under the permanent Ruleset-v2 identity, every
  entrant's vulnerable core is anchored at its own start address, so every
  omitted-start default match collapsed all entrants' cores onto the same
  window and the last entrant seeded eliminated every earlier entrant before
  its first action. `bytefray agents test` / Designer's Development Test had
  the identical independent default and defect.
- Omitted starts under the permanent Ruleset-v2 identity now resolve to a
  deterministic, non-overlapping per-seat layout instead. An explicitly
  supplied start (including an explicit `0`) is always preserved exactly as
  given, never adjusted.
- The engine now fails closed: `NativeMatchService.run` rejects any resolved
  Ruleset-v2 placement whose entrant cores overlap (including ordinary arena
  wraparound) before any entrant executes or any replay/result artifact is
  written, for every caller — CLI, Designer, and direct `MatchRequest`
  construction alike.
- Ruleset-v1's historical omitted-start default (`0`) is unchanged, as are
  Ruleset-v2 gameplay semantics, the Agent API, all schemas, and evaluation
  methodology. RC2's corrected default v2 match identity intentionally
  differs from RC1's broken one-tick default; RC1's historical artifacts
  remain readable and are not reinterpreted.
- Also removes stale "Beta3" wording from the Agent Designer's read-only
  source-viewer hint/tooltip and recaptures the affected README screenshot.

RC2 corrects an RC1 default-path integration defect discovered during RC1's
release audit — it is not a new development cycle or gameplay redesign.

## [2.0.0-rc1] - 2026-08-24

### Bytefray 2.0 release-candidate freeze

- Freezes the integrated 2.0 candidate: Ruleset-v2 vulnerable-core gameplay,
  multi-entrant matches and evaluation, responsive Replay Viewer presentation,
  and complete Agent Designer authoring/evaluation workflows.
- Ruleset-v2 gameplay semantics, Agent API v1, result/replay/evaluation/package
  schemas, revision and canonical match identities, and evaluation methodology
  are unchanged from the qualified beta program.

### Post-Beta3 workflow completion

- Simple and Advanced Designer matches now expose explicit Ruleset selection.
  Compatible Python-vs-Python direct matches recommend/default to Ruleset v2;
  VM/blob selections clearly fall back to the valid Ruleset-v1 path. The
  canonical `ruleset_id` is passed explicitly to the engine and persisted in
  result/replay artifacts.
- Agent Development now displays the selected Python agent's `agent.py` and
  `agent.yaml` in a fail-closed, read-only viewer, clears stale source when the
  selection changes, and retains external editing through **Open Folder**.
- README onboarding was reorganized around the current product, with refreshed
  Windows Agent Designer and Ruleset-v2 multi-entrant Replay Viewer screenshots.

### Qualification stabilization

- The source-viewer symlink-containment regression now skips consistently when
  non-privileged Windows cannot create a test symlink, matching the existing
  cross-platform containment-test policy without weakening production checks.

## [2.0.0-beta3] - 2026-08-24

### Replay Viewer presentation

- The entrant HUD now adapts across pairwise, 3/4-entrant, and compact 5+
  entrant replays with stable non-color badges and readable roster cards.
- Ordinary window resizing preserves the outer window dimensions while the
  arena retains integer scaling; compact/expanded help and authoritative
  terminal-state presentation make playback state clearer.

### Agent Designer presentation

- A Bytefray identity header, clearer Quick Match hierarchy, and real
  content-replacing ready/live output states make startup and match progress
  easier to understand.
- Existing square-icon resources and accessible text/status cues are reused;
  the interface degrades safely when optional branding is unavailable.

### Multi-entrant workflow integration

- Agent Designer evaluation now offers explicit Pairwise and Ruleset-v2 Group
  modes. Group mode selects a Focus agent plus 3+ entrant roster and previews
  the exact canonical seeds, layouts, distinct seat assignments, and cells.
- Live results, Evaluation History, and comparison drill-down now classify
  schema-v6 group artifacts from their persisted methodology fact and use
  roster/layout/seat-assignment terminology, including physical-instance
  self-play denominators.
- Canonical group replays remain actionable. Pairwise-only Agent Lab reruns are
  disabled for group cells with an explicit explanation. Pairwise v4/v5 and
  group v6 artifact/schema/identity behavior is unchanged.
- The cross-platform historical v1 identity fixture is now byte-stable under
  both LF and CRLF checkouts; pinned identity values and production behavior
  are unchanged.

## [2.0.0-beta2] - 2026-08-23

### Integrated qualification

- Qualified the combined v1/v4, Ruleset-v2 pairwise/v5, and Ruleset-v2
  group/v6 evaluation surfaces for `v2.0.0-beta2` release preparation;
  no schema/identity bump or production behavior change was needed.
- Re-established all five Phase 4.1 high-severity regression gates,
  historical v1 golden/resume compatibility, N=3/N=4 verification and
  analysis, self-play disclosure, group comparison content protection,
  interruption resume, and worker determinism.
- Exercised real source-tree v1, v2 pairwise, and 18-cell v2 group CLI
  workflows through evaluation discovery/show/JSON/deep verification and
  identical-run comparison; invalid group/methodology combinations fail
  explicitly with exit 2.
- Validated source and isolated-package workflows outside the checkout,
  including an installed 18-cell group evaluation and deep verification.
- Final qualification: 1,893 collected; 1,877 passed; 14 skipped; 2
  deselected; zero failures/errors; Ruff clean; mypy clean for 73 engine
  and 12 client files; diff checks clean. No release blocker remains and
  Phase 4's strategic corpus does not require rerunning.
- Release decision: **qualified for v2.0.0-beta2 release**.
  See
  [docs/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md](docs/archive/v2/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md).

### Verification and compatibility hardening

- Deep verification now supports healthy N-entrant group cells (including
  candidates outside seat A and N=4) while retaining pairwise checks.
- Self-play group artifacts no longer fabricate a pairwise opponent
  identity or report false condition-fingerprint inconsistency.
- Multi-death group analysis withholds victim capture timing unless the
  aggregate evidence proves the victim died at the trusted terminal event.
- Historical v1 evaluation `schedule_id` values are restored exactly;
  Ruleset-v2 pairwise placement and group layout/seat identity remain
  significant and unchanged.
- Group comparison now permits candidate implementation changes but refuses
  strict alignment when a non-candidate roster member's content identity
  changed.
- Duplicate/self-play group presentation discloses per-physical-instance
  denominators and suppresses the ambiguous first-seat legacy candidate
  outcome aggregate. Group mode now rejects pairwise-only orientation
  switches.
- Non-zero Python entrant starts remain canonical-match-identity inputs;
  the documented pre-Beta2 tournament resume consequence is a fail-closed
  `resumed_result_mismatch` followed by retry/re-execution.

### Ruleset-v2 pairwise evaluation methodology

`bytefray agents evaluate` gains an explicit `--ruleset {bytefray-rules-1,
bytefray-rules-2}` selector. Omitted (or explicit `bytefray-rules-1`) runs
the historical v1 evaluation methodology completely unchanged, including
every evaluation/schedule identity ever computed. `bytefray-rules-2`
activates a new, balanced 1v1 methodology:

- a standard, mechanically-derived three-condition placement set
  (`opposed`, `quarter`, `opposed-shifted`), expressed as fractions of
  arena size rather than hand-picked coordinates;
- a standard five-seed default (`1, 2, 3, 4, 5`), overridable like any
  other seed selection;
- explicit scheduler-order ("both entrant orientations") disclosure,
  distinct from placement;
- capture/core interaction as a new evaluation-output category
  (`battle_engine.evaluation_capture`) -- captures caused/suffered,
  capture rate, capture tick, killer attribution -- kept structurally
  independent of win/loss/score/behavior, never a combined "performance
  score."

Every gameplay-relevant condition (Ruleset, scheduler order, placement,
seed, ticks) now enters canonical evaluation/schedule identity; resume and
cross-evaluation comparison fail closed across any methodology change.
Additive, request-methodology-resolved schema/identity version 5 is used
only for `bytefray-rules-2` evaluations; every v1 evaluation keeps schema/
identity version 4 exactly as before. See
[docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md](docs/archive/v2/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md)
for the full design record.

### Multi-entrant evaluation

`bytefray agents evaluate` gains `--group`: fields the candidate together
with every `--opponents` entry as one N-entrant roster per cell (standard
layouts x exhaustive seat permutations), instead of Phase 1's pairwise
one-cell-per-opponent matrix. Requires `--ruleset bytefray-rules-2` and at
least two `--opponents`; every non-`--group` evaluation is byte-for-byte
unaffected. Reuses the engine's own already-N-entrant-generic winner
resolution unchanged -- no new winner-resolution logic was written. Uses a
third additive schema/identity version (6), leaving v1 (4) and pairwise v2
(5) unchanged. Group artifacts feed the symmetric analysis described
below rather than misleading pairwise per-opponent metrics.

Also fixes a Phase 1 defect discovered during this phase's own
characterization: `evaluations show`/`list`/`compare`'s artifact-health
self-consistency check falsely reported `planned_identity_inconsistent`/
`condition_fingerprint_inconsistent` on every `bytefray-rules-2`
1v1 evaluation artifact (a stale independent rehash that never matched
Phase 1's own identity payload) -- a verification bug only; no persisted
`evaluation_id`/`schedule_id`/`match_id` was ever wrong or rewritten. See
[docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md](docs/archive/v2/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md)
for the full design record.

### Symmetric group strategic analysis

Replaces Phase 2's "deferred" multi-entrant analysis placeholder with a
new, entrant-symmetric analysis module (`battle_engine.
evaluation_group_analysis`), in both the live CLI (`bytefray agents
evaluate --group`) and `evaluations show`:

- per-entrant outcome classification -- winner, surviving non-winner, and
  eliminated are three distinct states, never collapsed into one "loss"
  bucket the way the existing candidate-oriented outcome field does;
- score, territory, and kill/death metrics for every roster entrant, not
  only the designated candidate;
- capture attribution generalized to N entrants, plus a new directed
  captor-to-victim interaction matrix, disclosing unattributable captures
  honestly rather than guessing;
- seat, layout, and seed sensitivity per entrant, with a transparent
  winner-rate/survival-rate range measure (never an opaque composite
  score);
- computed with no candidate id as an input -- candidate-focused
  presentation is a pure selection over an already-symmetric result, so
  changing which entrant is "the candidate" never changes any entrant's
  own numbers.

Also fixes two real defects found during this phase's own
characterization: `agents evaluate --group`'s aggregate summary was
silently computing a "differential" for group cells as if the (nonexistent
single) opponent's score/territory were zero -- now correctly `None` for
a group scope, never a misleading number (pairwise evaluations are
unaffected). Capture-tick values were reported as the match's own final
tick unconditionally, which only reflects a specific capture's real tick
when that capture ended the match -- at 3+ entrants a capture very often
does not end the match, so the tick is now withheld rather than wrong
whenever it cannot be trusted; the capture's occurrence and attribution
are unaffected. See
[docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md](docs/archive/v2/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md)
for the full design record, including a direct re-examination of Phase 2's
own "Core Tracker" win-rate finding against a larger sample.

### Strategic characterization

- An 11-roster, 990-cell pre-registered corpus found that Claimer's earlier
  apparent dominance is strongly roster-dependent rather than universal;
  dedicated search offense remains an effective counter-strategy.
- A reproducible kingmaking-like effect and pairwise-versus-group
  divergence demonstrate why group win rate is not a complete strategic
  descriptor.
- A real global seat bias was measured, while exhaustive permutation keeps
  each entrant's aggregate exposure balanced across seats.
- No Ruleset, scheduler, scoring, or strategic-agent behavior was changed.
  The release assessment remains `PROCEED WITH DOCUMENTED CONCERNS`, not a
  claim that multi-entrant strategy is solved or fully balanced.

### Compatibility and beta limitations

- Methodology identity domains are explicit and unchanged: historical v1
  uses schema/identity v4, Ruleset-v2 pairwise uses v5, and Ruleset-v2 group
  uses v6. Historical v1 schedule identity was restored exactly; no schema
  bump occurred during review remediation or integrated qualification.
- Canonical Python match identity now includes non-zero entrant start
  positions. Historical non-zero-start match/result/replay IDs can differ,
  and an old tournament resumed across this boundary can fail closed with
  `resumed_result_mismatch` and require retry/re-execution. Historical
  zero-start identity remains compatible.
- Self-play execution and raw physical-seat evidence are supported, while
  the stored candidate `EvaluationCell.outcome` retains first-occurrence
  semantics; presentation discloses multiplicity and per-instance rates.
- Group evaluation identity can depend on opponent CLI ordering; exhaustive
  seat permutations scale factorially; legacy pairwise sentinels remain in
  group effective conditions; and aggregate-only capture timing stays
  conservative when the exact death tick cannot be proven.
- Large-N sampling/rotation, central identity-payload construction, and
  currently insignificant O(n²) unattributed-interaction processing remain
  future work rather than beta release blockers.

## [2.0.0-beta1] - 2026-08-20

### Ruleset v2 (Vulnerable Core)

Introduces `bytefray-rules-2`, a second, permanently registered gameplay
identity alongside the frozen `bytefray-rules-1`, resolving the eleven-
experiment `v2.0.0-alpha.1`-`alpha.11` research program:

- Each entrant now has a **Vulnerable Core**: a fixed-size, contiguous
  region anchored at its own start address. An entrant dies the moment it
  owns zero of its own core cells, checked once per tick after that tick's
  action blocks and before scoring, with capture attribution from the final
  ownership-removing write when unambiguous.
- Core cells are **observably seeded** with a public beacon byte
  (`CORE_BEACON_BYTE = 0xCE`) instead of blank, and a living entrant's own
  core is maintained back to blank whenever damaged -- reachable only
  through an ordinary `READ`, with no privileged Agent API metadata.
  Maintenance never restores ownership or repairs beacon damage on a
  captured core.
- Territory, scoring, scheduling, and capture-timing formulas are otherwise
  byte-identical to Ruleset v1; none were retuned for this beta.
- **Agent API v1 is retained unchanged** -- there is no Agent API v2 in this
  release.
- Ruleset-v2 gameplay is **Python-runtime supported only**. Requesting a VM
  entrant under `bytefray-rules-2` fails closed before execution, with no
  partial run/replay/result artifact written; the native VM path is
  unaffected and continues to run `bytefray-rules-1`.
- Core Tracker (the Ruleset-v2 reference offense benchmark) gained a
  minimal self-knowledge filter so it no longer wastes actions probing and
  assaulting its own already-owned core beacon; no other reference agent or
  constant changed.

See [docs/RULES_V2.md](docs/RULES_V2.md) and
[docs/V2_0_BETA1_PLAN.md](docs/archive/v2/V2_0_BETA1_PLAN.md) for the full semantic
contract, and
[docs/V2_0_ALPHA_RESEARCH_SUMMARY.md](docs/archive/v2/V2_0_ALPHA_RESEARCH_SUMMARY.md)
for the closed research program this beta promotes.

### Compatibility

- Ruleset v1 remains available and unchanged, and stays the **default**
  Ruleset for every command when `--ruleset` is omitted during this beta
  transition.
- The historical alpha identities (`bytefray-rules-2-alpha1`,
  `bytefray-rules-2-alpha11`) remain independently executable with their
  own exact historical semantics -- `bytefray-rules-2` is registered under
  its own key and is never aliased to or from them.
- Every result and replay persists its exact originating Ruleset identity;
  historical v1 and alpha artifacts remain fully readable. The replay
  schema is unchanged (still `battle2.replay` v3).
- `agents evaluate` remains implicitly Ruleset-v1-only in this beta; no
  `--ruleset` flag is exposed there.

### CLI / product execution

- `--ruleset {bytefray-rules-1,bytefray-rules-2}` is now explicit CLI
  surface on `bytefray run`, `agents test`, and `tournament`, defaulting to
  `bytefray-rules-1` when omitted.
- An authoritative, fail-closed runtime-kind check rejects any VM entrant
  requested under `bytefray-rules-2` before execution begins, with a clear
  error and zero artifacts written; `bytefray-rules-1` and the historical
  alpha identities keep their exact prior VM behavior.

### Replay / Replay Viewer

- Replay sessions now derive per-entrant alive/dead status and, under
  Ruleset v2, core integrity/capture/attribution directly from the
  canonical replay's reconstructed ownership -- never from arena byte
  content -- with no replay schema change.
- The interactive Replay Viewer's window is now tiled into a top HUD band
  (match header plus one status card per entrant), an unobstructed middle
  arena band, and a bottom footer band (playback controls, a compact
  status/event message, and the territory-history graph). Ruleset v1 shows
  no core field; Ruleset v2 shows core integrity, capture, and attribution
  alongside score/territory/kills. The card row supports two- and
  three-entrant matches.

### Scope boundaries

Beta1 does **not** yet include full Ruleset-v2 evaluation methodology
(order/placement/seed balancing), a Designer Ruleset-v2 workflow, VM
Ruleset-v2 gameplay parity, or a fully productized 3-way evaluation/CLI
workflow. These are planned for later betas -- see
[docs/V2_0_BETA1_PLAN.md](docs/archive/v2/V2_0_BETA1_PLAN.md#8-boundaries-to-later-betarc-releases).

Two disclosed, non-blocking items carry forward from qualification and are
not addressed in this beta: a pre-existing, cosmetic packaging gap in the
unified CLI dispatcher's runtime taskbar-icon lookup (predates Beta1); and
omitting `--a-start`/`--b-start` under `--ruleset bytefray-rules-2` can
produce a confusing but mechanically correct immediate unattributed core
capture, since core placement is start-address-sensitive. See
[docs/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md](docs/archive/v2/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md)
for the full qualification record.

## [1.6.0] - 2026-08-18

### Evaluation Scale & Analysis

- `bytefray agents evaluate --workers N`: bounded local parallel evaluation
  across independent evaluation cells, via a pool of long-lived worker
  subprocesses. Worker count never affects `evaluation_id` or any per-cell
  result, only wall-clock throughput; default remains `1` (serial). See
  [docs/V1_6_PHASE2_PARALLEL_EVALUATION.md](docs/archive/v1/V1_6_PHASE2_PARALLEL_EVALUATION.md).
- `bytefray agents evaluate --preset <name>` and `bytefray agents
  evaluation-presets list|show|validate`: reusable, hand-editable
  `bytefray.evaluation_preset` YAML files supplying default candidate/
  baseline/opponents/seeds/ticks/orientation values for an evaluation, with
  any explicit CLI flag always overriding the preset. A preset is purely an
  input-construction convenience -- it never affects `evaluation_id` or any
  per-cell result, and an in-progress evaluation always resumes from its own
  frozen `evaluation.json`, never from a preset's current (possibly since
  edited or deleted) content. The Designer's Evaluate dialog gained a
  matching preset selector that pre-fills the same fields. See
  [docs/V1_6_PHASE3_EVALUATION_PRESETS.md](docs/archive/v1/V1_6_PHASE3_EVALUATION_PRESETS.md).
- Derived aggregate/statistical analysis for `bytefray agents evaluate`,
  `evaluations show`, `evaluations compare`, and the Designer's evaluation
  results dialog: Wilson score intervals on observed win rates, and an
  exact paired candidate-vs-baseline significance test (the exact sign
  test / exact McNemar test) over discordant paired conditions, with
  always-visible sample counts and explicit by-opponent/by-orientation
  breakdowns so a pooled number can never hide an opponent- or
  orientation-specific effect. Fully derived from already-canonical
  evaluation cells -- no `evaluation.json` schema change, no new runtime
  dependency, and works on any existing valid v1/v2 evaluation artifact
  without re-running it. See
  [docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md](docs/archive/v1/V1_6_PHASE4_EVALUATION_ANALYSIS.md).
- Derived behavior-profile analytics for `bytefray agents evaluate`,
  `evaluations show` (add `--no-behavior` to skip it), and the Designer's
  evaluation results dialog: survival, write activity, territory
  occupancy/retention/spread, and kill interaction, computed overall and
  split by orientation/opponent, from each cell's own already-written
  `result.json` -- no `evaluation.json` schema change, no new runtime
  dependency. Deliberately kept structurally independent of Phase 4's
  outcome evidence (never reads `outcome`/score fields) and deliberately
  narrow: no clustering, no archetype naming, no composite score, no
  combined behavioral-distance scalar. See
  [docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md](docs/archive/v1/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md).

### Compatibility

This release changes no Ruleset ID, Ruleset-v1 semantics, Agent API v1
contract, or replay/result/evaluation/package schema; every existing v1-v4
`evaluation.json` artifact remains readable. Worker count and evaluation
preset name/path are both confirmed identity-neutral -- `evaluation_id` and
every per-cell result are unaffected, verified at 60/540/2,000-cell scale
across serial and parallel execution, interrupt/resume, and source-drift
abort. No new runtime dependency. Independently qualified on Windows
(source and frozen build), Linux (WSL2 Ubuntu), and Python 3.10-3.13; see
[docs/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md](docs/archive/v1/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md)
for the full qualification record, including two disclosed non-blocking
findings deferred to future maintenance (neither is a wrong calculation or
a release blocker).

## [1.5.0] - 2026-08-18

### Architecture Evolution Readiness

- Added a fail-closed, executable Ruleset-v1 policy/dispatch seam
  (`battle_engine.ruleset_policy`) that pairs the frozen Ruleset-v1 identity
  with a shared scheduler; only `bytefray-rules-1` resolves, and any other
  Ruleset ID fails closed instead of silently executing as Ruleset v1.
- Centralized the three previously duplicated VM/unsupervised-Python/
  supervised-Python entrant scheduling loops behind one shared sequential-
  quota scheduler.
- Centralized the three previously duplicated Ruleset-v1 match-termination
  decision/reason computations behind one implementation, reached through
  the same dispatch seam used for scheduling.
- Separated entrant identity from resolved match inputs and mutable
  execution state with a new `EntrantIdentity` type, while keeping VM and
  Python execution states intentionally distinct and preserving exactly one
  execution state per entrant.
- Added extensive semantic-characterization and architecture-equivalence
  qualification: the combined result was directly verified equivalent to
  v1.4.1 Ruleset-v1 behavior, including running the golden corpus against
  the actual v1.4.1 source tree and confirming zero source diff since
  v1.4.1 in `vm.py`, `scoring.py`, `statistics.py`, and `rules.py`.

### Compatibility

This release changes no Ruleset ID, Ruleset-v1 semantics, Agent API v1
contract, or replay/result/evaluation/package schema. There is no new
gameplay, no mixed VM/Python execution, and no multi-state entrant. Every
persisted deterministic identity and the v1.4/v1.5 Ruleset-v1 equivalence
corpus were confirmed unchanged throughout.

## [1.4.1] - 2026-08-17

### Fixed

- Fixed Agent Designer Simple and Advanced match launch when an agent's
  display name differs from its canonical discovery ID. Real starter agents
  such as `adaptive` / `Adaptive (Starter)` could be selected correctly in
  the combo box but fail during Designer-side catalog resolution before the
  existing match engine was launched.
- Added end-to-end GUI regression coverage across the combo, `RunConfig`,
  Designer handler, catalog-row resolution, and generated match command using
  realistic starter identity shapes, duplicate display names, and self-match.
  Discovery IDs are authoritative; a legacy display-name fallback is accepted
  only when it identifies exactly one row.

This patch changes no Ruleset, Agent API, replay/result/evaluation schema,
package schema, evaluation methodology, or gameplay behavior.

## [1.4.0] - 2026-08-16

### Platform Integrity & Scaling

- Retired obsolete predecessor command aliases, executable/build names,
  environment-variable fallbacks, filesystem defaults, and active branding;
  stable `battle2.result`/`battle2.replay`/`battle2.tournament` wire names and
  deterministic identity salts remain intentionally unchanged.
- Removed four individually verified unreachable modules while retaining the
  tested top-level `_legacy/` migration fixture.
- Added a compact Ruleset-v1 golden corpus for default/non-default, VM/Python,
  two-/three-entrant, starter, overlap/wrap, RNG, halt, forfeit, territory, and
  kill/death behavior.
- Replaced duplicate full-arena territory recounts with authoritative counts at
  the existing VM write boundary. Golden match/result IDs, outcomes, state,
  statistics, ownership/memory fingerprints, and normalized canonical replay
  content remain unchanged.
- Added a reproducible non-CI scaling benchmark and recorded before/after and
  replay measurements in `docs/performance/V1_4_SCALING.md`. Current backward
  seek performance did not justify checkpoint/index complexity.
- Qualified existing homogeneous three-entrant VM/Python execution without
  changing pairwise tournament/evaluation methodology or gameplay semantics.
- Defined the v1.4 integrity/scaling, v1.5 architecture-readiness, v1.6
  evaluation-scale, and v2.x gameplay-research boundaries.
- Reconciled the headless-suite count change: 13 retired predecessor-
  compatibility tests were removed and 12 new integrity/equivalence tests
  were added, producing the expected net reduction of one test (1241 to
  1240), not a coverage regression.
- Release qualification re-ran the Ruleset-v1 golden corpus after the 1.4.0
  identity bump and confirmed unchanged gameplay, match/result identity,
  final state, statistics, and normalized canonical replay content.

## [1.3.0] - 2026-08-16

Implementation and release qualification for Bytefray v1.3.0's **Designer
Workflow Completion** theme: connects Agent Designer to mature v1.1/v1.2 engine
capabilities that were previously CLI-only, plus the narrow domain and
Windows-build correctness fixes found by independent qualification. Manual GUI
qualification was completed by the user after the technical audit and passed.
No gameplay, Agent API, Ruleset, evaluation/result/replay-schema,
agent-package-schema, or agent-revision-identity change. See
`docs/ROADMAP.md`'s v1.3.0 section for full scope disposition.

### Agent Designer

- Added Agent Development tab **"Export Agent…"**: packages the selected
  discovery id through `battle_engine.agent_package.export_agent`
  (in-process and synchronous, but disabled while another Designer process
  is active). Export parses metadata and reads opaque payload bytes; it
  never imports or executes agent code. Reports agent id, revision id, file
  count, package path, and package SHA-256, matching `bytefray agents
  export`'s own output text.
- Added Tools menu **"Inspect Agent Package…"**: read-only, execution-free
  package inspection (`battle_engine.agent_package.inspect_package`) via a
  new, reusable `PackageDetailsDialog` (`app/views/agent_package.py`)
  showing identity, integrity (recomputed live from packaged bytes),
  compatibility, and an explicit Python/blob-agent trust disclosure
  ("self-consistency does not authenticate the package author or make the
  contained code safe"). Selecting a package for inspection never imports, executes,
  compiles, or syntax-checks agent source; only archive/JSON/YAML metadata
  and opaque payload bytes are inspected.
- Added Tools menu **"Import Agent Package…"**: file picker → the same
  `PackageDetailsDialog` (with an "Import…" action gated on the package
  being both structurally valid and compatible with this installation) →
  on explicit confirmation, the authoritative, fail-closed
  `battle_engine.agent_package.import_package`. A destination-id collision
  with genuinely different content is never silently overwritten; the
  Designer offers an explicit, iterative alternate-id retry (the GUI
  equivalent of the CLI's `--as`), never an automatic rename. Repeated
  collisions do not recurse. A no-op (identical-revision) import is
  reported as such, not as an error. A successful import refreshes the
  Designer's agent catalog and selects the exact imported discovery id,
  including when display names differ from ids or are duplicated, with no
  restart required. Mutating package actions share the Designer's busy guard
  and do not change source while an agent-executing subprocess is active;
  read-only inspection remains available.
- Hardened the authoritative package domain during qualification. It now
  bounds the raw archive and central directory before `ZipFile` allocates
  its member table, then validates that complete table (including
  `package.json` and the safely parsed `agent.yaml`) and
  member/name/count/compressed-and-uncompressed-size limits before decompression; normalizes
  malformed/unsupported-compression failures to typed package errors;
  rejects Windows ADS/reserved-device/trailing-dot-or-space path components
  and special Unix filesystem entries portably on every host (and never
  exports them), plus duplicate/case/ancestor collisions;
  cross-checks declared kind/API/entry-point/version/display and revision
  counts against the verified packaged payload metadata; and applies the
  same resource limits before export creates an archive. These are
  validation corrections inside the existing schema-v1 contract, not a
  package wire-format change, and none executes packaged code.
- **Evaluation History → comparison-row drill-down** (`EvaluationComparisonDialog`,
  `app/views/evaluation_history.py`): "Test in Agent Lab"/"Open Replay" are
  now available from a two-run comparison, not only from a single
  evaluation's own cell list -- the capability both `docs/specs/
  evaluation_history.md` §17 and v1.1's own changelog entry explicitly
  deferred. Reuses `EvaluationHistoryDialog`'s exact existing signals and
  `AgentDesigner` handlers -- no second execution/replay-launch path.
  Actions are enabled only when a selection uniquely identifies a real
  underlying match. Direct rows carry exact, internal left/right schedule
  references (not serialized by `ComparisonRow.to_json()`), preventing
  candidate-first/opponent-first cells with the same nominal coordinates
  from resolving to the wrong artifact. The neutral Side labels are **Left
  (selected)** and **Right (comparison)**; a direct row defaults right, an
  unmatched cell offers its one real side, a changed-condition pair
  requires an explicit side choice, and an ambiguous duplicate group is
  never actionable. Agent Lab reruns preserve the chosen cell's ticks and
  entrant orientation (including role-swapping `opponent_first`); replay
  opening uses that exact artifact. Historical reruns still execute the
  currently installed source, disclosed in the dialog, not an archived
  revision implicitly.
- **Agent revision restore from Designer** (`RestoreRevisionDialog`, new,
  in `app/views/evaluation_history.py`): `RevisionBrowserDialog` gains an
  explicit **"Restore Files…"** action calling the authoritative
  `agent_revisions.restore_revision` -- the one capability `docs/specs/
  agent_revision.md` §9's v1.1 note left CLI-only. The safe default target
  remains `<data_root>/agent_revisions_restored/<revision_id>/`; a non-empty
  target still requires the explicit force option. Force overwrites matching
  paths but does **not** delete unrelated files, so the UI does not call it
  directory replacement. Any target inside (or aliasing into) this
  installation's live `agents/` catalog requires an additional explicit
  confirmation, and restore is disabled while a Designer-owned subprocess
  is active. Launching Agent Lab from the still-open History dialog also
  disables restore for that dialog session. On a successful live restore
  the Designer refreshes the catalog, preserves the
  restored id selection, and invalidates stale validation/test evidence.
  The dialog also shows completeness and current-source drift before the
  user confirms.
- CLI/Designer consistency fix: `bytefray agents evaluations compare`'s
  human-readable output now discloses `ambiguous_duplicate_groups` (already
  shown by the v1.1 Designer; the CLI's own `_print_compare` had this
  identical count in `--json` output only). The JSON shape and all other
  CLI behavior are unchanged.

### Windows packaging

- Fixed a real onedir/onefile packaging inconsistency: `tools/agent_designer.spec`
  and `tools/replay_viewer.spec` built their `EXE` with every binary/data
  file baked in (no `exclude_binaries=True`, `COLLECT(exe, name=...)` with
  nothing further) instead of the thin-launcher-plus-loose-files onedir
  shape `tools/battle2.spec`/`tools/battle_cli.spec` already used and
  `tools/installer.iss`/the portable ZIP layout both assume for all four
  applications. Both specs now build the identical onedir shape as their
  two siblings. Pinned by a new parametrized regression test
  (`engine/tests/test_windows_packaging_spec.py::test_spec_builds_onedir_layout_not_a_fat_exe`)
  across all four specs, without requiring a real PyInstaller build.
- Fixed `tools/build_win.ps1`'s GUI import/startup smoke test leaving
  runtime-generated `agents/` data inside `dist\windows\battle2\` and
  `dist\windows\battle-agent-designer\`: `AgentDesigner.__init__` eagerly
  calls `ensure_starter_agents()`, and a frozen portable app with no
  `BYTEFRAY_ROOT` set defaults to writing beside its own executable --
  contaminating the exact tree the installer and portable ZIP both package
  verbatim. The GUI smoke block now isolates its own temporary
  `BYTEFRAY_ROOT`, the same way the adjacent `agents create` smoke block
  already did. It also launches GUI-subsystem executables with
  `Start-Process -Wait -PassThru` so qualification checks their real exit
  codes instead of a stale `$LASTEXITCODE`, and cleanup now fails closed if
  either temporary root remains. The build script finally asserts that no
  `agents\` directory exists under any of the four distributable application
  trees -- a concrete regression guard, not just a fixed instance.

### Documentation

- Corrected `docs/ROADMAP.md`'s v1.1.0 section, stale since that release
  was tagged: it still read "Status: implemented on main, pending release
  qualification/tag" despite `v1.1.0` having shipped. Added the v1.3.0
  section describing this milestone's scope.

## [1.2.0] - 2026-08-16

Implementation and release qualification for the proposed v1.2 theme,
**Portable Agent Packaging & Sharing** (see `docs/ROADMAP.md`/
`docs/FUTURE_PLANS.md`'s "Agent packaging / sharing"). Extends Bytefray's
existing content-addressed agent-revision provenance
(`docs/specs/agent_revision.md`, v0.8) across a machine
boundary rather than inventing a parallel provenance system: an agent
package is a transport wrapper around one already-archived revision. No
gameplay, Agent API, Ruleset, or evaluation/result/replay-schema change;
this introduces exactly one new, independent compatibility axis
(`bytefray.agent_package` schema, currently version 1) — see
`docs/COMPATIBILITY.md`.

### Agent CLI

- Added `bytefray agents export <agent-id> [--output PATH] [--revision ID]
  [--json]`: packages one Python (`kind=python`) or blob (`kind=blob`)
  agent into a single, portable `<agent>-<revision>.bytefray-agent` ZIP
  file. With no `--revision`, freezes the agent's current on-disk source
  into a revision first (reusing `agent_revisions.archive_agent_revision_
  from_walk`, one read for both identity and packaged payload); with
  `--revision`, packages an already-archived historical revision instead.
  Manifest-only `kind=builtin` starter agents (the four native VM
  starters) are rejected with a typed `package_unsupported_kind` error —
  their behavior is supplied by the Bytefray installation itself, not by
  anything in their own directory, so there is nothing portable to export.
- Added `bytefray agents package show <package-file> [--json]`: reports a
  package's structure, declared identity, wrapped revision provenance,
  live-recomputed integrity, and import compatibility on this
  installation, **without importing or executing a single byte of the
  packaged agent's code** — package validity, integrity, and agent trust
  are three explicitly distinct things (see the module docstring and
  `docs/specs/agent_package.md` Sec 6).
- Added `bytefray agents import <package-file> [--as AGENT_ID] [--json]`:
  safely imports a package with fail-closed pre-write gates — full structural/schema/
  integrity/compatibility validation and safe extraction to a private
  temporary directory happen before anything is written to `agents/`.
  Fails without mutation if the destination agent id already exists with
  different content; reports a non-mutating no-op if it already exists
  with the exact same revision; `--as` imports under an explicit
  different id. An imported agent becomes an ordinary Bytefray agent —
  its revision is also seeded into the importing installation's own
  `agent_revisions` store, so `agents revisions show`/`agents evaluate`
  work on it immediately, and provenance verification continues to work
  identically to a never-transferred agent.
- New modules: `engine/src/battle_engine/agent_package.py` (package
  model, deterministic archive writer/reader, safe extraction, export/
  import orchestration — presentation-neutral, Qt-free, no execution of
  packaged code) and `engine/src/battle_engine/agent_package_cli.py`
  (thin argparse wrapper). Two small, additive, non-breaking exports on
  existing modules: `battle_engine.agents.agent_spec_from_dir` and
  `battle_engine.agent_revisions.revision_manifest_payload`.
- Archive extraction is defended against path traversal (`../`, absolute
  and Windows drive-qualified paths, UNC paths, Windows-backslash-style
  traversal checked even on non-Windows hosts), duplicate/case-colliding
  paths, symlink-mode ZIP entries, and oversized/excessive archives —
  reusing `battle_engine.paths.contained_path` rather than trusting
  `zipfile.extractall()`'s own safety assumptions. See
  `docs/specs/agent_package.md` Sec 7 and its adversarial test suite
  (`engine/tests/test_agent_package.py`).
- Genuinely cross-platform, not merely path-independent within one host:
  a package exported on Windows was imported, loaded, validated, and
  re-exported on real Linux (and the reverse), producing byte-identical
  `agent_revision_id` at every step.

## [1.1.0] - 2026-08-14

Implementation and release qualification for the proposed v1.1 theme,
**Evaluation Insight & Designer Polish** (see `docs/ROADMAP.md`/
`docs/FUTURE_PLANS.md`'s "Richer GUI access to evaluation/history/
provenance"). No gameplay, Agent API, Ruleset, or evaluation/result/replay
schema change; no `engine/src`/`client/src` file was touched.

### Agent Designer

- Added an **Evaluation History** browser (**Tools → Evaluation History…**):
  the Designer can now list, inspect, deep-verify, and compare past
  `agents evaluate` runs (including legacy v1 artifacts) without leaving the
  GUI, and inspect the durable agent-revision provenance (files, omissions,
  live verification, and whether the archived revision still matches an
  agent's *current* on-disk source) behind a candidate/baseline/opponent
  role. This is the Designer history UI both `docs/specs/evaluation_history.md`
  (Sec 17) and `docs/specs/agent_revision.md` (Sec 9) explicitly deferred
  when the underlying `battle_engine.evaluation_history`/
  `battle_engine.agent_revisions` engine layers shipped in v0.7/v0.8 — this
  slice surfaces that already-shipped, already-tested capability rather than
  adding new engine behavior. Cell drill-down ("Test in Agent Lab"/"Open
  Replay") reuses the exact handlers `EvaluationResultsDialog` already uses;
  no new execution or replay-launch path was added. New, presentation-only
  files: `app/services/evaluation_history_workflows.py`,
  `app/views/evaluation_history.py`.
- Release-qualification polish, found via an interactive session against the
  real (non-offscreen) Qt backend rather than assertions alone: a comparison
  whose cells all fell into duplicate (opponent, seed) groups previously
  rendered as an uninformative wall of zero counts with no visible signal
  that detail was available — the summary now discloses the
  `ambiguous_duplicate_groups` count directly; the deep-`Verify` outcome is
  now also shown as an always-visible status line instead of only as the
  last line of a long, scrollable detail block; history/comparison list rows
  now carry a full-text tooltip for what a long single-line summary
  truncates at typical window widths; and the "Compare With…" picker no
  longer offers an unreadable/malformed sibling as a comparison target.

## [1.0.1] - 2026-08-13

Patch release. No gameplay, Agent API, Ruleset, or evaluation-schema
change — this is a maintenance release consisting of one user-visible bug
fix plus repository/build cleanup.

- **Fix:** the Agent Designer Advanced tab's per-agent JSON parameter
  editors were validated locally and then silently discarded before ever
  reaching the agents they configure. `app/agent_designer.py`'s
  `_on_advanced_run` now exports each agent's params on the child
  process's environment, and `engine/src/battle_engine/cli.py`'s
  `_resolve_agent` now merges that environment JSON over the shared CLI
  defaults for both discovered and built-in agents, instead of parsing it
  for discovered agents only and discarding the result.
- Removed confirmed-dead repository debris: personal debug scripts,
  stale IDE state, ~132MB of committed build output, `requirements-*.txt`
  duplicates of `pyproject.toml`'s extras, and the unreferenced `sdk/`
  tree (135 files, including a byte-identical duplicate of already-dead
  `_legacy/agents_tooling/` code and an accidental duplicate example
  bundle).
- Consolidated packaging/tooling: removed `sync.sh` (source of prior
  `update: <timestamp>` commit spam) and the hardcoded `start.ps1`;
  rewrote `sync_win.ps1` to install via `pip install -e ".[...]"`.
- Established a Ruff-clean baseline (`docs/RUFF_DEBT.md` records the
  applied fixes, project-wide rule exclusions, and per-line exceptions
  with rationale) and added `ruff check .` to CI so it doesn't
  silently reaccumulate.
- Contributor/security/documentation cleanup: `CONTRIBUTING.md` rewritten
  as an external-contributor guide, `SECURITY.md` added, and stale
  references fixed across `AGENTS.md`/`README.md`.

## [1.0.0] - 2026-08-13

Bytefray's first stable release. `v1.0.0` promotes `v1.0.0-rc2` to general
availability: no gameplay, Agent API, Ruleset, or evaluation-schema change
is included beyond what `v1.0.0-rc1`/`v1.0.0-rc2` already shipped (branding/
visual-release integration and the Agent Designer runtime-kind
match-selector correction, respectively). The only change since RC2 is a
pre-tag, test-only cleanup: seven GUI tests carried a stale assumption from
before Bytefray shipped Python starter agents (that the Agent Development
combo starts empty with nothing selected); they now identify agents by
discovery id and real catalog state instead of count or position, so they
keep holding as the starter catalog grows. No production code changed. See
[docs/ROADMAP.md](docs/ROADMAP.md#v100--stable-bytefray-platform) for the
release criterion this milestone satisfies.

## [1.0.0-rc2] - 2026-08-13

Bytefray v1.0.0's second release candidate. This closes an Agent Designer
UX gap surfaced during RC1 qualification: match selectors now show each
agent's runtime kind and disable incompatible opponents before a match is
attempted, rather than only after `validate_homogeneous` rejects it at
run time. No gameplay, Agent API, Ruleset, or evaluation-schema change is
included. Final `v1.0.0` follows once RC2 qualification is complete.

### Agent Designer

- Agent Designer now displays each agent's runtime kind (`[Python]`/`[VM]`)
  in the Simple and Advanced tabs' match selectors, so the existing
  mixed-VM/Python-execution restriction is visible before a match is
  attempted instead of only after it is rejected.
- Incompatible VM/Python opponents remain visible in the Agent B selector
  but are disabled once Agent A is selected, and an Agent B selection that
  becomes incompatible when Agent A changes is repaired automatically to
  the nearest compatible choice.
- Backend homogeneous-runtime validation (`validate_homogeneous`) is
  unchanged and remains the authoritative check for both tabs.

## [1.0.0-rc1] - 2026-08-13

Bytefray v1.0.0's first release candidate. This closes the required pre-1.0
branding/visual-integration gate identified during v0.10 qualification (see
[docs/ROADMAP.md](docs/ROADMAP.md#required-pre-10-gate-brandingvisual-release-integration))
on top of the already-stabilized v0.10.0 platform; no gameplay, Agent API,
Ruleset, or evaluation-schema change is included. Final `v1.0.0` follows once
RC1 qualification is complete.

### Branding / presentation

- Added production Bytefray visual assets (`assets/branding/`): icon,
  horizontal logo, and the source brand sheet.
- Wired the production icon into all four PyInstaller executables
  (`battle2`, `battle-cli`, `battle-agent-designer`,
  `battle-replay-viewer`) and the Windows installer
  (`SetupIconFile`/`UninstallDisplayIcon`).
- Added a runtime window icon to Agent Designer
  (`QApplication.setWindowIcon`) and Replay Viewer
  (`pygame.display.set_icon`), resolved through a new
  `battle_engine.paths.get_branding_icon_path()` helper that works from a
  source checkout, a frozen build, and a wheel install alike.
- Added the horizontal logo and two representative product screenshots
  (Agent Designer, Replay Viewer) to the README.

## [0.10.0] - 2026-08-12

v0.10's theme: **Platform Stabilization / v1.0 Readiness**. This is a
stabilization release, not a feature release: it freezes the Bytefray 1.0
gameplay Ruleset contract (`bytefray-rules-1`), closes the entrant-
orientation-vs-translation evaluation-methodology question left open by
v0.9, documents the compatibility model and the stable Agent API v1
surface, persists Ruleset identity directly into every native result/
replay artifact, hardens canonical match identity, and completes release
qualification — including first-user workflow and packaging/install
correctness fixes surfaced during that qualification pass.

### Documentation

- Closed v0.10's evaluation-methodology question (Phase 3): the standard
  Bytefray 1.0 `agents evaluate` contract is orientation-aware with a
  single, fixed arena alignment, and explicitly does not claim translation/
  placement robustness. This is a deliberate, evidence-informed deferral,
  not an oversight — re-verified against the now-frozen Ruleset v1/Agent
  API v1 contracts that Python arena translation cannot be implemented
  without either an incompatible Agent API v1 change (out of bounds) or
  substantial new shared Python-runtime engineering that remains its own,
  separately scoped future effort. A fresh, independent VM-entrant study
  (using the existing production `MatchEntrant.start` placement mechanism,
  not a research hack) corroborated v0.9's finding that relative placement
  can materially change match outcomes (3 of 4 tested matchups flipped
  winner across placements), reinforcing that the deferral is a scope
  limitation, not a claim that placement doesn't matter. No engine,
  Ruleset, Agent API, or evaluation schema code changed as a result.
  `docs/ROADMAP.md` and `docs/COMPATIBILITY.md` updated accordingly.

### Added

- Native `result.json`/`replay.jsonl` now persist Bytefray Ruleset identity
  directly (v0.10 Phase 4: Artifact Compatibility & Ruleset Persistence).
  Every current native VM or Python match writes `ruleset_id:
  "bytefray-rules-1"` into both the result envelope and the canonical
  replay header — one discriminator per match, following the exact
  precedent `runtime_kind` already set. Both fields are additive: no
  `battle2.result`/`battle2.replay` schema bump was required, verified
  directly (not merely inferred) by running the `v0.9.0`-tagged readers
  against a synthetic artifact carrying the new field in an isolated
  worktree. `redcode94`/pMARS results never claim Bytefray Ruleset v1.
  `battle_engine.result_model.resolve_result_ruleset`/`battle_engine.
  replay.resolve_replay_ruleset` give a confidence-qualified answer
  (`recorded`/`recovered`/`unknown`/`not_applicable`) for artifacts written
  before this field existed, informed by a fresh git-history audit proving
  Python-vs-Python native gameplay semantics — scheduling order, action
  execution, READ/WRITE addressing, mortality, forfeit handling, scoring
  and winner-resolution integration — were byte-for-byte unchanged for the
  Python runtime's entire existence (v0.3.0 onward, the same range already
  proven for the VM). `ruleset_id` is also now a first-class input to
  `match_id`'s identity hash (`match_service.canonical_match_id`), so two
  otherwise-identical matches can never collide under one `match_id` if
  they ran under different declared gameplay semantics; `result_id`/
  `replay_id` inherit this transitively. **This is a deliberate, one-time
  native-ID transition**: a v0.10 Phase 4+ build computes a different
  `match_id`/`result_id`/`replay_id` than a pre-Phase-4 build would for
  byte-identical inputs, since exactly one Ruleset's literal value is now
  hashed in where previously nothing was. Historical stored IDs are never
  rewritten; a `tournament.json`/`evaluation.json` left mid-run by an older
  build will show its prior completed matches/cells as
  `resumed_result_mismatch`/`corrupted` on the first Phase-4+ resume — the
  same safe, fail-closed behavior any other `match_id` mismatch already
  produces (`--retry-failed` or a fresh run recovers it), mirroring the
  precedent already set when `bytefray.evaluation` moved v1 → v2's
  strictly richer identity payload. See `docs/RESULT_SCHEMA.md`'s
  "Identity recipe" for the full rationale and pinned tests. A resumed
  tournament match or evaluation cell whose result and replay disagree on
  `ruleset_id` is now demoted to `corrupted`, the same treatment an
  existing `match_id`/`result_id` disagreement already receives.
  `bytefray.evaluation`'s historical
  `"evaluation-rules-1"` value is now explicitly normalized (a small,
  finite alias table, `battle_engine.rules.normalize_ruleset_id`) to align
  with a fresh `"bytefray-rules-1"` evaluation for cross-evaluation
  comparison, without rewriting the historical artifact's own recorded
  value. `battle2.tournament` deliberately gains no Ruleset field —
  tournament-level compatibility derives from constituent match artifacts.
  See `docs/COMPATIBILITY.md`'s "Legacy compatibility matrix" for the full
  artifact/version/runtime table.
- `battle_engine.rules.BYTEFRAY_RULESET_ID = "bytefray-rules-1"` — a new,
  first-class gameplay-semantics compatibility identity (v0.10 Phase 2:
  Freeze Ruleset v1), documented in full as `docs/RULES.md`, a rewritten
  **Ruleset v1 reference** distinguishing Ruleset semantics from
  configuration values, Agent API semantics, evaluation methodology, and
  implementation details, plus a bump policy for future gameplay changes.
  `bytefray.evaluation`'s `EVALUATION_RULES_COMPATIBILITY_ID` is now a
  derived alias of `BYTEFRAY_RULESET_ID` rather than an independently
  maintained second rules counter — its value, wire field name
  (`rules_compatibility_id`), and comparison behavior are unchanged, and
  historical `"evaluation-rules-1"` artifacts are documented as an honest
  historical alias, never silently reinterpreted as containing the new
  spelling. New `docs/COMPATIBILITY.md` names the independent compatibility
  axes (project version, Agent API version, Ruleset identity, artifact
  schema versions, evaluation methodology, agent revision identity, source
  fingerprint versions) and gives a worked change-impact table for which
  axis a given change actually requires.
- `docs/AGENT_API_V1.md` now documents the exact, literal deterministic
  entrant-seed derivation algorithm (UTF-8 material string, NUL-separated
  fields, SHA-256, first 16 digest bytes, big-endian integer) as a frozen
  Agent API v1 invariant — an incompatible change to it requires
  `AGENT_API_VERSION = 2`, not a separate RNG compatibility identifier.
  New golden-vector regression tests
  (`test_derive_agent_seed_golden_vectors`) pin literal expected integers
  for fixed inputs so accidental formula drift is caught immediately.

### Fixed

- Corrected `docs/REPLAY_SCHEMA.md`'s stale claim that `battle2.replay` v3
  "has never appeared in a tagged release" — it has shipped, in its
  already-extended form, in every tagged release since `v0.3.0`. The
  narrower point the note was actually making (no tagged release ever
  depended on the brief pre-extension record shape) is preserved.
- Resolved a stable-vs-experimental documentation contradiction: several
  docs (README, `docs/AGENT_AUTHORING.md`) described the entire homogeneous
  Python-vs-Python runtime as "experimental," while `docs/ROADMAP.md`
  already treats Agent API v1 and the core Python runtime as stability
  candidates for 1.0. Docs now say what is actually still
  unsupported/experimental (mixed VM/Python matches, security sandboxing,
  hard callback containment outside `agents test`/`validate`, replication,
  corruptible Python-core designs — see `docs/COMPATIBILITY.md`) rather
  than labeling the whole platform experimental.
- `docs/AGENT_API_V1.md` no longer describes the shipped (v0.5.0) Agent Lab
  supervised-worker timeout containment as "(unreleased) Agent Lab work."
- v0.10 Phase 5 (release qualification): `bytefray agents test` printed
  `Run 'bytefray replay <path>' to inspect it.` — a command the parser
  itself rejects, since `bytefray replay` requires `--replay PATH` and has
  no positional form. Reproduced against the packaged wheel and fixed at
  the source (`agent_test.py`), across every doc/spec carrying the same
  guidance text (`docs/AGENT_AUTHORING.md`, `docs/MANUAL_SMOKE_TESTS.md`,
  `docs/specs/agent_test.md`), and in the tests that had pinned the buggy
  string.
- v0.10 Phase 5: `battle_engine.paths._source_checkout_root()` walked every
  ancestor directory of its own installed location looking for sibling
  `engine/`/`client/` folders, so installing the built (non-editable) wheel
  into a virtualenv nested anywhere underneath an unrelated Bytefray
  checkout silently redirected the writable data root to that checkout
  instead of the documented installed-platform default (XDG data home /
  `%LOCALAPPDATA%`) — reproduced by installing the wheel under this
  repository's own tree, which surfaced the developer's own `agents/`
  catalog instead of a clean starter set. Detection is now based solely on
  the module's own fixed source-tree position
  (`.../engine/src/battle_engine/paths.py`), which correctly covers a real
  checkout and a `pip install -e .` editable install without an unbounded,
  coincidence-prone ancestor search.
- v0.10 Phase 5: `bytefray`/`battle2` had no `--version`/project-info CLI
  surface at all — an unrecognized top-level argument (including
  `--version`) silently fell through to a full help dump with exit `0`
  instead of an error. Added `--version` (formatted from
  `battle_engine.project_info.get_project_info()`) to the top-level parser,
  and an unrecognized top-level argument now reports a normal
  `unrecognized arguments` error with exit `2` instead of being silently
  swallowed; a bare `bytefray` with no arguments is unaffected.

### Documentation

- Documented and integrated optional, non-authoritative local
  Ollama-assisted development tooling under `tools/local_ai/`
  (`README.md` policy doc, `Invoke-BytefrayLocalAI.ps1` harness, and its
  tested prompt set) and linked it from the README's AI-Assisted
  Development section and roadmap. Developer tooling only — Ollama is not
  a Bytefray dependency, CI requirement, or user-facing feature.
- Added `docs/ROADMAP.md` (v0.10.0's stabilization scope and v1.0.0's
  release criterion) and `docs/FUTURE_PLANS.md` (a maturity-labeled
  catalogue of post-1.0 ideas: accessible agent-authoring DSL, agent
  packaging/sharing, richer evaluation/statistics, evaluation performance/
  scaling, and future simulation/combat research), and updated the
  README's roadmap table and future-work paragraph to point at them
  instead of carrying an open-ended "Future / unscheduled" list inline.
  Corrected `INSTALL.md`'s stale v0.6.0 download references to the
  current v0.9.0 release.
- v0.10 Phase 5 (release qualification): corrected `docs/LINUX_INSTALL.md`,
  which was still titled and exampled for the `v0.3.0` release (including a
  literal `bytefray-0.3.0-py3-none-any.whl` install command that no longer
  matches any current release asset), to track the current release the way
  `INSTALL.md` already does. Lightly reworded the same currency-confusion
  in README's Linux callout. Added a portable-applications section to
  `INSTALL.md` documenting that the four portable executables are
  self-contained and do not share one agents/replays catalog unless
  `BYTEFRAY_ROOT` is set explicitly (each defaults to its own directory —
  intentional, existing, tested behavior; this was previously undocumented
  for the portable distribution specifically, unlike the installed case
  where the installer sets a shared machine-level `BYTEFRAY_ROOT`
  automatically). Recorded the required pre-1.0 branding/visual-integration
  gate in `docs/ROADMAP.md` and the README roadmap table so v1.0 cannot be
  read as an automatic next step after v0.10 stabilization.
- v0.10 release preparation: investigated a reported garbled character
  (`ù`) in the packaged replay client's `--help` description text. The
  source (`client/src/battle_client/cli.py`) contains a correct UTF-8 em
  dash; confirmed byte-for-byte and confirmed rendering correctly in a
  native Windows console regardless of active code page (Python 3.6+'s
  `PEP 528` console handling writes Unicode directly through the Win32
  console API there). The garbled character only appears when output is
  captured through a non-native-console path (redirected output, a
  pseudo-terminal) where that direct-Unicode path isn't available and
  Python falls back to encoding through the legacy ANSI code page — a
  terminal/log-rendering artifact of that fallback, not a source or
  packaging defect. No source change made.

## [0.9.0] - 2026-08-11

v0.9's evaluation-methodology theme: **Orientation-Aware Evaluation**.
`bytefray agents evaluate` gave the candidate an always-first-acting
physical slot in every match it ever ran — a shipped starter agent
(`adaptive`) already documents and exploits exactly this structural
first-mover bias. Both entrant orientations are now evaluated by default.

### Added

- `bytefray agents evaluate` now runs **both entrant orientations** by
  default for every `(opponent, seed)` pair: `candidate_first` (today's
  historical behavior) and the new `opponent_first` (the same unmodified
  executor, called with roles swapped) — **matrices roughly double in
  size** by default. Each orientation is a fully independent
  `EvaluationCell`: its own `schedule_id`, artifact directory, result/replay
  pair, status, and resume/retry lifecycle — never averaged together.
  Results stay expressed from the subject/opponent evaluation-role
  perspective even when the physical match roles are swapped.
- `--single-orientation` restores the exact legacy `candidate_first`-only
  methodology and matrix size — its output (CLI and Designer) is labeled
  explicitly: "does not generalize across entrant order."
- Every evaluation now discloses `Arena alignment: fixed — translation
  robustness not evaluated`, whether both orientations ran or not. Both
  entrant orientations exercise the same, single arena alignment; running
  both orientations makes the evaluation orientation-fair, **not**
  translation-robust — arena address translation remains unimplemented
  runtime work (Phase 4/5 research, tracked separately) and is not
  evaluated by this release.
- `bytefray.evaluation` bumps to **schema v4** / **identity v4**: cells gain
  `orientation`/`orientation_index`; evaluations gain `orientation_mode`
  (`"both"` | `"candidate_first_only"`) and `arena_alignment_mode`
  (`"fixed"`, v0.9's only value) — both new evaluation-wide fields, threaded
  through identity/comparison the same way `rules_compatibility_id` already
  is. `EVALUATION_RULES_COMPATIBILITY_ID` is **unchanged**: this is an
  evaluation-methodology/coverage change, not a gameplay-rules change.
  Gameplay, scoring, winner resolution, and Python scheduling order are
  byte-for-byte unmodified.
- `bytefray agents evaluations show` prints entrant-orientation and
  arena-alignment methodology alongside `rules_compatibility_id`, plus a
  per-orientation win-rate breakdown. Cross-evaluation comparison folds
  orientation into its alignment key: a legacy (pre-v0.9) artifact's cells
  are recovered as `candidate_first` with certainty (never `unknown`) and
  align only against a new evaluation's `candidate_first` half; the new
  `opponent_first` cells have no legacy counterpart and surface as
  unmatched, never silently folded into an improved/regressed verdict.
- Agent Designer's Evaluate dialog gains one checkbox, "Run both entrant
  orientations (recommended)" (checked by default); unchecking it passes
  the CLI-equivalent `--single-orientation`. Results presentation shows the
  same methodology disclosure and per-cell orientation the CLI does.

### Fixed

- Resuming an `agents evaluate` run whose `opponent_first` cells had
  already completed — including the ordinary case of simply re-running the
  identical command a second time against an existing `--output`, with
  nothing missing or failed — could falsely demote those cells to
  `corrupted` (`resumed_result_mismatch`) even though nothing about the
  match had changed. The resume-verification helper that recomputes each
  cell's expected match id built its entrant list in a different order
  than a real `opponent_first` match execution actually uses, which
  produces a genuinely different id (match identity is sensitive to
  entrant position, not just which agent occupies which slot).

### Known Limitations

- Arena translation/alignment is not implemented in v0.9. Both-orientations
  coverage makes an evaluation entrant-order-fair; it says nothing about
  sensitivity to arena placement, which remains untested by this tool.

## [0.8.1] - 2026-08-11

Patch release correcting Linux/POSIX symlink-cycle handling in the v0.8
agent revision system.

### Fixed

- Agent revision walking now treats filesystem symlink-resolution cycles as
  `REASON_RESOLVE_ERROR` omissions instead of allowing `Path.resolve()` to
  raise an uncaught `RuntimeError` during evaluation.
- Added regression coverage for cyclic symlinks through both revision
  walking and evaluation execution.

## [0.8.0] - 2026-08-11

v0.8.0's theme is **Agent Revision & Provenance**: an agent's exact source
at the moment an evaluation freezes its plan now gets a durable, content-
addressed copy, closing v0.7's own recorded "Known Limitations" gap (source
fingerprints identified a revision but kept no historical copy of it).

### Added

- `battle_engine.agent_revisions` — a new, self-contained, Qt-free
  content-addressed revision store: a canonical tree-walk that includes
  every regular file under an agent directory (not just `.py`), dereferences
  internal file symlinks, never traverses a directory symlink/junction, and
  explicitly records every omission (external target, broken link,
  unreadable file) instead of silently dropping it; a versioned,
  full-digest content fingerprint over that walk covering both included
  bytes and omission evidence; and an atomic, dedup-by-construction store
  under `<data_root>/agent_revisions/` whose written bytes are verified
  against the intended fingerprint *before* a snapshot is ever promoted to
  its canonical path.
- `bytefray agents evaluate` now archives every distinct candidate/
  baseline/opponent's revision at freeze time (before `evaluation_id`/any
  checkpoint/any cell execution), with a same-freeze-step cross-check that
  aborts the whole run (no artifact written) if the source changed between
  the plan's own identity read and the archival read. `bytefray.evaluation`
  bumps to **schema v3**, adding an `agent_revisions` field wholly separate
  from `planned_identities` — `evaluation_id`/`IDENTITY_VERSION` are
  unaffected, and v1/v2 artifacts remain fully readable and unmutated. A
  revision-store write failure is recorded on the artifact and never takes
  down the evaluation itself.
- `bytefray agents evaluations show`/`show --verify`/`compare --verify` now
  surface each role's revision id, archive error, and (with `--verify`)
  local-store verification status — distinguishing "not available" (no
  local snapshot; never treated as corruption) from "invalid" (a present
  snapshot that fails to verify) from "verified," and never consulting live
  agent source.
- `bytefray agents revisions list <agent-id>|show <revision-id>|restore
  <revision-id> [--to <dir>] [--force]` — the minimal CLI for discovering,
  inspecting, and restoring preserved revisions. `restore` composes with
  existing `agents test`/`agents evaluate`/`agents validate` rather than
  adding a second execution path; it refuses to overwrite a non-empty
  target without `--force`, refuses any path escape (`..`, absolute,
  Windows drive-relative, UNC, or through a pre-existing destination
  symlink/junction), and refuses to write anything at all if the canonical
  snapshot itself fails to verify.

### Fixed

- `restore_revision` now verifies a canonical snapshot's fingerprint
  *before* writing any file to a restore target, not only after — a
  corrupted, tampered, or hand-edited snapshot now fails restoration
  closed instead of silently reproducing untrustworthy bytes into a
  target the caller is about to treat as trusted.

### Deferred

Explicitly out of scope for v0.8.0: revision `diff`, a revision-aware
`test --revision` (use `restore` + existing `agents test`), Designer
revision-management UI, revision-store garbage collection/lifecycle
management, and VM/Redcode revision parity.

### Known Limitations

- A revision only covers an agent's own directory; external imports/
  dependencies outside it remain out of scope, exactly as for source-drift
  detection.
- No storage-cost bound: a large local data file (e.g. `model.blob`) that
  changes on every edit produces one full extra copy per distinct
  revision. No cleanup/garbage-collection command exists yet.
- A revision-preserved/source-reproducible claim requires `complete: true`
  (no omissions); an incomplete revision still has a real, dedup-safe
  identity, but restoring it reproduces less than the original tree.

## [0.7.0] - 2026-08-10

v0.7.0's theme is **Evaluation History**: past `bytefray agents evaluate`
runs become a first-class, queryable record instead of a one-off artifact
you have to locate and read by hand.

### Added

- `bytefray agents evaluations list|show|compare` — a new, Qt-free
  `battle_engine.evaluation_history` package discovers, adapts (v1 and
  v2), and compares past evaluation artifacts without rerunning anything.
  Discovery is artifact-authoritative on-demand scanning (no side database
  to fall out of sync), supports custom roots and explicit paths, and
  emits both human-readable and `--json` output. `compare` aligns two
  evaluations' candidate cells by shared condition (opponent identity
  including local-source fingerprint, seed, execution conditions, rules
  identity, and duplicate-occurrence index) — excluding candidate identity,
  which is the variable actually being compared — treating the newer
  evaluation's candidate as the change under test against a stable
  baseline test condition. An opponent, config, runtime-context, or rules
  change on either side downgrades the affected pair to `inconclusive`
  rather than producing an unqualified verdict; the candidate's own change
  is never used as the primary historical verdict. Duplicate cell
  multiplicity is preserved rather than collapsed, ambiguous duplicate
  groups are reported explicitly instead of guess-paired, and
  `show --verify`/`compare --verify` add deep replay/result integrity
  checks — including reproducibility-anomaly detection — for the selected
  artifact(s) only. See `docs/specs/evaluation_history.md` and
  `docs/AGENT_LAB.md`'s new "Evaluation history (v0.7)" section.
- `bytefray.evaluation` **v2**: `bytefray agents evaluate` now writes
  planned resolved identities (candidate/baseline/every opponent
  occurrence), readable effective execution conditions (full `Config`, not
  just seed), an evaluation plan identity, a narrow evaluation
  rules-compatibility identifier, `created_at`/`updated_at`/`finished_at`
  lifecycle timestamps with an atomic first-checkpoint-before-first-cell
  guarantee, per-cell execution provenance (execution contexts) that
  survives no-op resume, and explicit duplicate-occurrence coordinates.
  `evaluation_id` remains a deterministic plan identity in a distinct
  space from v1's (`evaluation-v2_...` vs. `evaluation_...`); v1 artifacts
  remain fully readable and are never rewritten. A source/identity change
  detected before or during a cell now stops the matrix
  (`lifecycle_state: "aborted"`, `abort_reason: "source_drift"`) instead
  of silently mixing agent revisions within one evaluation.
- Designer: the Evaluate dialog now passes agent discovery ids (not
  display names) to `bytefray agents evaluate`, and each plan's output
  directory now defaults to that plan's own content-addressed path instead
  of one fixed `designer-evaluation` directory every plan collided on.

### Fixed

- Closed a frozen-plan TOCTOU window and a resume-erasure defect where
  retrying a checkpointed evaluation could overwrite durable per-cell
  identity/provenance data instead of leaving completed cells alone.
- Local (agent-directory) Python source is now fingerprinted with a
  versioned scheme applied consistently to both the candidate and every
  opponent occurrence, and reconciled three ways — the identity resolved
  at plan time, the identity frozen for the executing worker, and a final
  fingerprint taken after execution — closing a lazy-import drift window
  where an edit made after planning but read during execution could go
  undetected.
- Execution-context comparison (runtime/interpreter identity recorded per
  cell) is fail-closed: an unknown or unrecoverable context is treated as
  "not proven equivalent," never as a silent pass, before a comparison
  pair is allowed a controlled `unchanged`/`improved`/`regressed` verdict.
- `compare --verify`/`show --verify` now gate the reported verdict and the
  top-level `deep_verified` flag on cells actually, individually
  verifying — a `--verify` run whose evidence fails to verify can no
  longer leave an ordinary verdict or non-zero comparable count standing
  for the affected pair.
- Malformed or partially-written v2 evaluation artifacts are isolated per
  artifact during discovery instead of aborting or contaminating an
  entire `list`/`compare` run; nested artifact/result/replay path
  references are containment-checked before being read.
- v1 artifacts recover duplicate-occurrence identity from all usable
  cells rather than bailing out on the first ambiguity, and identity
  version compatibility between v1 and v2 artifacts is handled
  explicitly rather than by coincidence.
- Designer: `Validate`/`Test` now resolve agents by discovery id rather
  than display name, matching the Evaluate dialog fix above.

### Deferred

Explicitly out of scope for v0.7.0 (tracked separately, not silently
implied by anything above): immutable agent revision storage, a
run-instance ledger, Elo/rankings or other cross-evaluation statistics,
VM/Redcode evaluation parity, a Designer History UI, and any
rules/scoring model redesign.

### Known Limitations

- Bytefray fingerprints agent-local Python source only; imports/
  dependencies outside the agent's own directory are not covered by
  source-drift detection.
- A narrow transient edit-and-restore timing race remains possible: an
  edit made and reverted within the same fingerprinting window can escape
  detection.

## [0.6.1] - 2026-08-09

v0.6.1's theme is **Default Agent Build-Out**: v0.6.1 doesn't change
architecture — it makes the first-run experience worth having. Before
this release, the only Python (Agent API v1) agent behavior a new user
ever saw was the `agents create` scaffold/reference agent, a single fixed
byte written to a random address in a small slice of the arena; two
copies of it playing each other are decided almost entirely by which one
happens to move second within a tick, not by strategy. See
ARCHITECTURE.md's new "Default Agent Build-Out (v0.6.1)" section for the
full design rationale, including the empirical findings (via `bytefray
agents evaluate` against the engine's actual scoring mechanics) that
shaped every shipped agent's final design, one prototype (a bounded
"patrol and defend" agent) that was tuned repeatedly and ultimately not
shipped because it could not be made competitive, and an open question
this work surfaced about the scoring model itself (see "Known
Limitations" below) that is explicitly out of scope for this release.

### Added

- Five new bundled Python (Agent API v1) starter agents — `claimer`,
  `strider`, `hunter`, `wanderer`, `adaptive` — added to
  `battle_engine.starters.STARTER_AGENT_NAMES` alongside the existing
  four native VM starters, discovered and initialized into the writable
  `agents/` catalog by the same non-destructive `ensure_starter_agents()`
  mechanism (no new discovery, catalog, or packaging concept). Each
  demonstrates a distinct, readable strategy against the restricted
  Python Agent API — disciplined territorial sweeping (Claimer), early
  wide-area dispersal followed by dense fill-in (Hunter), periodic
  rolling defense of recently-claimed ground (Strider), seed-randomized
  sweep order (Wanderer), and a phase-based hybrid using the engine's
  PC/JUMP actions as an explicit state machine (Adaptive) — and includes
  a module docstring explaining its strategy, the state it tracks, what's
  reasonable to change, and what earlier, less successful (or
  structurally broken) versions tried and why. Development-matrix and
  held-out-seed evaluation (`bytefray agents evaluate`) shows real
  matchup texture rather than one dominant agent: Claimer and Hunter both
  win roughly three-quarters of their matches (Hunter loses only to
  Claimer), Strider sits close to even, Wanderer wins about a quarter,
  and Adaptive — deliberately the weakest, see "Known Limitations" below
  — is shipped for its PC/JUMP demonstration value rather than its win
  rate.
- A README "Try the bundled agents" section describing each agent,
  compelling example matchups, an `agents evaluate` example comparing
  Claimer against Strider (Claimer's sibling, built around one added
  idea — periodic rolling defense — whose payoff turns out to depend on
  the opponent, a deliberate demonstration of measuring rather than
  assuming), and how to inspect a match in Agent Lab.
  `docs/AGENT_AUTHORING.md` gained a "Learning from the bundled agents"
  section pointing authors at the new agents' source as worked examples,
  since there is no separate "start from example" scaffold option —
  copying a bundled agent's directory is the mechanism.
- `engine/tests/test_default_python_agents.py`: structural coverage for
  the new roster (clean discovery, successful validation, successful
  match completion against the reference opponent, and a behavioral
  smoke matrix of every shipped agent against every other), asserting
  only that matches complete without infrastructure failure, never that
  a particular agent wins a particular seed.

### Fixed

- `engine/tests/test_starter_agents.py`'s starter-file-count assertions
  were hard-coded to the single-file (`agent.yaml`-only) shape every
  native VM starter happens to have; generalized to compute the expected
  file set from each starter's actual source directory, since the new
  Python starters are the first to ship more than one file (`agent.yaml`
  and `agent.py`).

### Known Limitations

- Building this roster surfaced a scoring-model question worth recording
  for a future release, not acted on here: under the current Python
  Agent API scoring rules (`ScoringPolicy.score_territory` accrues every
  tick an entrant owns a cell; there is no combat, only overwrite-based
  denial), unrestricted "claim as much of the arena as fast as possible,
  and never stop" strategies appear to be close to dominant. Every
  attempt in this release to trade raw expansion for something else —
  reading before writing, patrolling and defending a bounded region,
  pausing to specialize into distinct phases — measured worse against an
  opponent that simply never stops expanding, because such an opponent
  eventually sweeps through nearly the whole arena and, in `bytefray
  agents evaluate`'s fixed subject-then-opponent tick order, wins any
  cell it reaches after the subject already claimed it. This is almost
  certainly why the one bounded prototype (see above) could not be made
  competitive at any size, and why Adaptive — the one shipped agent that
  still pauses expansion, to demonstrate `PC`/`JUMP` as a phase
  state machine — is deliberately the weakest of the five. Changing the
  scoring model is out of scope for this release (and would be a
  significant scope increase); this is recorded here as a design
  observation for whoever next considers richer Python match modes or
  scoring variants.

## [0.6.0] - 2026-08-09

v0.6's primary theme is **Agent Evaluation**: once an agent works and can
be debugged (v0.4/v0.5), how does an author tell whether it is actually
getting better? See `docs/specs/agent_evaluation.md` for the full design
rationale and `docs/AGENT_LAB.md`'s new "Evaluating a candidate" section
for the user-facing reference.

### Added

- `bytefray agents evaluate <candidate-id> --opponents <id,id,...>
  [--baseline <id>] [--seeds <n,n,...> | --seed-range <a:b>] [--ticks <n>]
  [--output <dir>] [--retry-failed] [--dry-run] [--quiet]`: a
  deterministic evaluation matrix -- the candidate (and optional
  baseline) each play every listed opponent at every explicit seed --
  built directly over `NativeMatchService` and executed one cell at a
  time via the exact `agents test` boundary (`agent_test.test_agent`,
  now with an additive, optional `run_dir` parameter), so every cell is
  byte-for-byte reproducible as a plain `agents test` invocation.
  Produces `bytefray.evaluation` v1 (`evaluation.json`), an additive
  artifact that references (never duplicates) each cell's canonical
  `replay.jsonl`/`result.json`. Supports resume (identical to
  `tournament`'s verified-trust pattern) and `--retry-failed`.
- Per-cell outcome classification distinguishes a real completed match
  (`win`/`loss`/`tie`, forfeits already folded in via the existing
  `winner` field) from a pre-tick-zero initialization failure of either
  side (`subject_init_failed`/`opponent_init_failed`, both valid
  evaluation outcomes, neither a tool failure) from a genuine
  infrastructure/tool failure (`failed`, excluded from all aggregation).
- A deterministic candidate-vs-baseline comparator classifies each
  matched `(opponent, seed)` cell as `improved`/`regressed`/`unchanged`
  using only the engine's own `win`/`tie`/`loss` outcome rank -- never a
  score- or territory-derived "better" verdict -- with score/territory
  reported alongside as supporting, non-lossy data. Win rates are always
  shown with their raw counts (`"n/m (p%)"`), never a bare percentage.
- Designer: an "Evaluate…" button on the existing Agent Development tab
  opens a modest configuration dialog and, on completion, a read-only
  results dialog (aggregate summary, comparison/cell list, and two
  drill-down actions -- rerun the selected cell in Agent Lab, or open
  its replay) -- no new top-level tab, reusing the existing
  `TraceInspectorDialog`/replay launcher unmodified.
- Evaluation is Python-agent-only in v0.6, inheriting `agents test`'s
  existing Python-only boundary rather than introducing a second,
  VM-flavored executor; documented explicitly, not left implicit.

### Fixed

- A repeated opponent or seed in an evaluation matrix (duplicate cells,
  an explicitly supported matrix shape) could be misidentified as the
  same cell: resuming an interrupted evaluation could misclassify a
  legitimately never-run duplicate as corrupted, a candidate/baseline
  comparison could undercount or silently drop duplicate cells, and the
  Designer's results dialog could open the wrong duplicate's replay when
  selecting between them. Duplicate cells now carry a distinct identity
  throughout scheduling, resume, comparison, and the Designer's
  drill-down.

## [0.5.1] - 2026-08-09

Patch release: Linux virtual-environment compatibility for Agent Lab
supervised workers, plus dynamic-agent packaging hygiene.

### Fixed

- Linux supervised Agent Lab workers (`agents test`/`agents validate`) now
  preserve the active virtual environment's interpreter identity instead of
  resolving `sys.executable`'s symlink chain to the base interpreter it was
  created from. The previous resolution walked past a standard Linux venv's
  `bin/python` symlink to a base interpreter lacking the venv's
  site-packages, so every supervised worker subprocess failed with
  `No module named battle_engine`.
- Dynamic Python agent imports no longer leave `__pycache__`/`.pyc` files
  beside agent source -- including the bundled reference opponent under
  `battle_engine/data/...` -- preventing source-checkout pollution and
  wheel/sdist packaging contamination.
- Linux type checking no longer reports the Windows-only
  `ctypes.WinDLL` access as an `attr-defined` error.

## [0.5.0] - 2026-08-09

v0.5's primary theme is **Agent Lab**: v0.4 closed the
create → validate → test → inspect → modify → repeat loop's first half;
v0.5 attacks the second half -- understanding *why* an agent behaved the
way it did, and containing an agent that never returns. See
`docs/specs/agent_lab.md` for the full design rationale and
[docs/AGENT_LAB.md](docs/AGENT_LAB.md) for the user-facing reference.

### Added

- `bytefray.agent_trace` v1: a new, separate, versioned JSONL artifact
  recording each Python entrant's `reset()`/`act()` call boundary data
  (Observation, AgentAction, diagnostic, wall time) -- independent of and
  never folded into `battle2.replay`/`battle2.result`.
- Supervised worker-subprocess execution: `agents test`/`agents
  validate` can now run a Python entrant's `load`/`reset`/`act` calls
  through one whole-match-lifetime worker subprocess per entrant, with a
  configurable per-call timeout (`--timeout`, default 5s). A stalled call
  is reported with a new diagnostic (`agent_load_timeout`,
  `agent_reset_timeout`, `agent_action_timeout`, `agent_worker_exited`,
  `agent_worker_protocol_error`) and the entrant is forfeited (or, for a
  load/reset stall, the match never starts) exactly as an equivalent
  in-process exception already was -- the match continues with any
  surviving entrant. Development-time hang containment only, not a
  security sandbox. `bytefray run`/tournament are unaffected: both new
  `MatchRequest` fields default to off.
- `bytefray agents inspect <run>` / `bytefray agents diverge <a> <b>`:
  headless CLI inspection of a development trace (summary, one tick's
  decisions, decisions around a tick, failures only) and first-divergence
  comparison between two traces. Executes no agent code.
- Designer: an "Inspect Trace" button and Timeout(s) option in the
  existing Agent Development tab, backed by a new, modest
  `TraceInspectorDialog` (tick/agent navigation, no source editor, no
  general debugger).
- `runs/agents_test/<agent-id>/<run-label>/` gains an optional
  `trace.jsonl` sibling alongside the existing `replay.jsonl`/
  `result.json`/`summary.json` -- additive only, on by default.

### Fixed

- A worker subprocess stuck inside a hung `act()`/`reset()` could
  survive indefinitely as an orphan process if its immediate parent was
  itself abruptly killed (e.g. the Designer's `_dispose_process()`
  killing a supervised `agents test` mid-hang) -- the worker has no
  opportunity to notice its parent died via the cooperative EOF path
  while stuck in the agent's own tight loop. Fixed with OS-level
  containment (`battle_engine.process_containment`): a Windows Job
  Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` on the parent side,
  `prctl(PR_SET_PDEATHSIG, SIGKILL)` on POSIX.
- A supervised agent calling `input()` during `reset()`/`act()` could read
  from the same underlying pipe the parent's worker-protocol request loop
  was using, silently stealing the next protocol request line and
  permanently desynchronizing the wire protocol. Agent-visible `sys.stdin`
  is now rebound to a closed/empty stream before any agent code runs
  (mirroring the existing `sys.stdout` -> `sys.stderr` redirection), so
  `input()` now raises an immediate `EOFError` instead.
- Closed a race in the POSIX `PR_SET_PDEATHSIG` registration where a
  parent that died before the worker reached its own `prctl()` call could
  leave the signal armed too late to ever fire; `die_with_parent()` now
  captures the parent pid immediately before registering and
  self-terminates if it changed right after.
- The hidden `agents _worker` verb now rejects unexpected arguments
  instead of silently blocking on stdin.
- `battle-cli.exe`, `battle-agent-designer.exe`, and
  `battle-replay-viewer.exe` could fail to discover or parse any
  `agent.yaml` at all (`... is not valid JSON. Convert to JSON, or 'pip
  install pyyaml' to allow YAML.`) because PyYAML's import was dynamic
  and therefore invisible to PyInstaller's static analysis; only
  `battle2.exe` happened to bundle it, by accident, via an unrelated
  unused module. PyYAML is now imported statically wherever agent
  manifests are parsed, so all four frozen executables bundle it
  reliably.
- The Designer's Run/Tournament/Validate/Test child processes could look
  for agents in a different directory than the one the Designer itself
  used, in a portable (no-installer) checkout: the child environment
  relied on inheriting `BYTEFRAY_ROOT`/`BATTLE2_ROOT`/`BATTLE_ROOT` from
  the OS environment, which only matches the Designer's own resolved
  root when that root came from an explicit env var (true after a normal
  install, not in a portable extraction). All five child-process launches
  now explicitly set `BYTEFRAY_ROOT` to the Designer's own resolved data
  root.

## [0.4.0] - 2026-08-08

v0.4's primary theme is **Agent Authoring & Development Feedback Loop**:
tightening the loop an agent author works in, from writing an agent to
seeing how it performs. The supported user journey, available from both
the CLI and the Designer GUI, is
create → validate → test → inspect → modify → repeat.

### Added

- Added `bytefray agents create <agent-id>`, scaffolding a minimal Agent
  API v1 Python agent from a bundled template resource into the writable
  data root (Phase 1).
- Added `bytefray agents validate <agent-id>`, a single-tick dry run
  (discover, load, `reset()`, one `act()`) reusing the production
  loader/action-validator and reporting a stable stage/code diagnostic on
  failure, with no runtime timeout or sandbox (Phase 2).
- Added `bytefray agents test <agent-id> [--opponent <id>] [--seed <n>]
  [--ticks <n>]`, a short (200-tick default) real match run through the
  exact `NativeMatchService` boundary against an internal reference Python
  opponent or another discovered agent, writing the same canonical
  `replay.jsonl`/`result.json`/`summary.json` artifacts any other native
  match writes under `runs/agents_test/<agent-id>/<run-label>/`. A tested
  agent's own forfeit, death, loss, or pre-tick-zero initialization
  failure -- and an explicit `--opponent`'s own initialization failure --
  are all successfully-evaluated development tests (exit `0`); only the
  internal reference opponent failing to initialize, or an unknown/
  non-Python agent/opponent, is a tool failure (exit `2`) (Phase 3).
- Added an **Agent Development** tab to the PySide6 Agent Designer,
  bringing the same create → validate → test → replay loop into the GUI:
  `New Agent` (a direct, in-process scaffold call), out-of-process
  `Validate` and `Test` (with Opponent/Seed/Ticks options) sharing the
  Designer's existing `QProcess`/single-active-process machinery, typed
  completed/initialization-failed/tool-failure presentation read from the
  same canonical CLI output and `result.json` the CLI itself produces, and
  an `Open Replay` action independent of the Simple/Advanced tabs' own
  "Open Last Replay" (Phase 4a-4c; see
  `docs/specs/agent_designer_workflow.md`).

### Changed

- Extracted the replay-domain facts `PygameRenderer` already computed
  (territory ownership/history, match event collection/query,
  selected-arena-cell state) out of
  `client/src/battle_client/renderers/pygame_renderer.py` and into a new,
  Pygame-free `client/src/battle_client/analysis.py`, then migrated the
  renderer to consume it, removing the private duplicate implementations.
  The one deliberate behavior change: the renderer-local "recently
  changed" flag on a selected cell moved from a field on the domain
  `SelectedCellInfo` dataclass to an explicit keyword parameter on the
  renderer's own `format_inspector_lines`, since it reflects UI
  observation history, not a replay fact (Phase 5; see
  `docs/specs/replay_analysis.md`). Pygame viewer behavior is unchanged.
- Rewrote `ARCHITECTURE.md` to describe the current `NativeMatchService`-
  centered architecture (canonical `battle2.replay` v3 writing, the
  `bytefray run`/`tournament` routing to it, the `battle_client` replay-
  consumption boundary, and the actual `app.agent_designer`/
  `app.replay_viewer` entry points) instead of the superseded v0.2
  document.
- Confirmed `app/match_runner.py` is not part of the shipped Windows
  executable set: `tools/build_win.ps1` (the script CI's `build-windows-exe`
  job actually runs) and `tools/installer.iss` build/package only
  `battle2`, `battle-cli`, `battle-agent-designer`, and
  `battle-replay-viewer`. No build artifact or configuration change was
  needed as a result. `tools/match_runner.spec` and the match-runner build
  steps in `tools/build_executables.ps1`/`tools/build_executables_windows.ps1`
  are pre-v0.3 leftovers not invoked by CI or by `build_win.ps1`; they are
  left as-is pending a human decision on whether to remove them (see
  ARCHITECTURE.md's Packaging section).

### Fixed

- Corrected `app/README.md` and `README.md`'s directory overview, which
  described `app/main.py` as the Agent Designer's entry point or an
  alternate way to launch it. Neither `app/agent_designer.py` nor
  `app/replay_viewer.py` imports `app/main.py`; the supported entry
  points are `battle-agent-designer`/`bytefray design` (`app.agent_designer`)
  and `battle-replay-viewer` (`app.replay_viewer`).

## [0.3.0] - 2026-08-08

### Added

- Added a `runtime_kind` discriminator to the canonical replay header so a
  reader can tell whether `pc`/`region`/`cpu_used` mean the VM's real fetch
  address/code footprint/instruction count or the Python runtime's
  agent-opaque controller bookkeeping/callback count, instead of leaving
  that distinction implicit.
- Added byte-level `values` to canonical memory-diff records (previously only
  address/length/owner), and an explicit tick-zero initial-state record
  capturing each entrant's starting registers and (for VM matches) its
  loaded code -- together these make engine-observable arena content and
  per-entrant controller state reconstructable from a canonical replay alone,
  without rerunning any agent.
- Added `battle_engine.result_model.verify_replay_digest` and
  `verify_result_replay` for explicit, opt-in replay integrity verification
  against a result's recorded SHA-256 digest, raising a typed
  `ReplayIntegrityError` with a stable `.code` on mismatch, missing, or
  unreadable files.
- Added `engine/tests/test_replay_reconstruction.py`, including an
  independently-derived-ground-truth end-to-end test proving canonical VM and
  Python replays reconstruct live match state, plus coverage for digest
  verification, `result_id` stability under nondeterministic exception text,
  and `match_id` path-independence/change-sensitivity.
- Added Agent API v1 for Python agents, including versioned manifests, explicit
  entry points and factories, fresh-instance construction, engine-controlled
  metadata, and validation of callable `reset()` and `act()` lifecycle methods.
- Added collision-resistant module loading so Python agents with the same source
  filename can be imported independently.
- Added `NativeMatchService` with typed match requests, entrants, and results as
  the canonical boundary for native matches; the CLI now acts as an adapter over
  this service while retaining VM behavior and compatibility output.
- Added deterministic Python-vs-Python native matches with restricted immutable
  observations, a versioned single-action vocabulary, independent per-agent RNG
  streams, and the existing instruction quota reused as the action budget.
- Added sequential entrant-order execution for Python agents, including circular
  arena reads and writes, ownership tracking, `HALT`, structured forfeits, and
  replay records using the existing schema.
- Added focused Agent API, native-service, reference-agent, scheduler, and Python
  runtime coverage, including deterministic execution and failure behavior.
- Added Agent API, agent-authoring, and native-rules documentation.
- Added structured Python runtime diagnostics, internal match and entrant
  termination reasons, and internal source-digest and derived-seed metadata.
- Added `battle2.result` schema v1 and `battle2.replay` schema v3 with stable
  match/result IDs, replay digests, and reproducibility metadata.
- Added a resumable headless round-robin tournament service with deterministic
  seeds, canonical-result standings, and per-match artifact directories.
- Added the supported `battle2 tournament` headless workflow with canonical
  agent resolution, resume/retry controls, standings output, and stable exits.
- Added a minimal Designer tournament launcher and About surface using shared,
  package-safe runtime and schema metadata.
- Added `ReplaySession`, a replay-analysis foundation providing deterministic
  forward/backward seek and incremental state reconstruction from canonical
  replay records, independent of any renderer.
- Added an interactive Pygame replay viewer with play/pause/step/restart/jump
  and adjustable playback speed, a runtime-aware HUD distinguishing VM and
  Python match state, and a clickable event timeline with click-to-seek
  navigation.
- Added territory analysis: per-tick owned-cell count/percentage summaries, a
  selected-cell inspector, a precomputed territory-history trend graph, and a
  recent-activity (recently-changed-cell) heatmap overlay, all derived solely
  from existing replay/session state.
- Stabilized the Windows development and test baseline for the interactive
  viewer and its analysis overlays.

### Changed

- Renamed the project from BATTLE2 to Bytefray. The canonical public CLI is
  now `bytefray`; the `battle2` command remains a deprecated compatibility
  alias throughout the v0.3 transition, dispatching to the identical
  implementation with the same behavior and exit codes while printing a
  one-line deprecation notice. `BYTEFRAY_ROOT` is now the preferred
  writable-data-root environment variable, with the legacy `BATTLE2_ROOT`
  and `BATTLE_ROOT` variables retained as deprecated fallbacks in that
  order. Internal Python package names (`battle_engine`, `battle_client`)
  and the `battle2.*` artifact schema identifiers (`battle2.result`,
  `battle2.replay`) are intentionally unchanged, as they are stable
  protocol identifiers rather than product branding.
- The canonical native-replay writer (`match_service._finalize_native_artifacts`)
  now builds and serializes the same typed `battle_engine.replay` dataclasses
  any reader consumes, instead of hand-building a second, independently
  maintained dict-based representation; writer and reader can no longer drift
  from each other by construction. `serialize_record` now always sorts JSON
  keys, so re-serializing a parsed record reproduces byte-identical output.
- The canonical replay's terminal result record now carries genuine final
  per-entrant state (previously always an empty `agents` list) and uses
  `null` for "no single winner" instead of leaving the field unpopulated;
  `result.json`'s `winner` field keeps its existing non-null `"tie"`
  convention unchanged for compatibility.
- Consolidated winner resolution into one implementation
  (`results.resolve_winner`, now typed against a small structural protocol
  instead of the VM's concrete `Agent` class, removing a suppressed type
  error); `match_service._effective_winner` is now only a thin, non-recomputing
  mapper to the display sentinel rather than a second implementation of the
  same win-mode rules.
- `result_id`'s identity hash now excludes raw exception-message text (which
  can embed nondeterministic content such as a default object `repr`'s
  memory address) so two otherwise-identical reruns of a match that hits the
  same agent failure get the same `result_id`. The full message is unchanged
  everywhere it is displayed to a human.
- `TournamentService` now rejects the entrant ID `"tie"` (case-insensitively)
  before scheduling, reserving it from collision with the canonical
  "no winner" sentinel.
- Characterized the native VM scheduler explicitly: living entrants consume
  their quota in spawn order, and an earlier entrant can affect a later entrant
  during the same tick.
- Characterized the Runner, Writer, Bomber, Flooder, Seeker, and Spiral reference
  agents and corrected the documented Flooder and Spiral behavior.
- Updated the README to describe current Python-agent execution accurately and
  to document the project's AI-assisted, human-directed development method.
- Updated tournament tooling for the current `battle2` CLI, lazy and portable
  build-tool discovery, source-checkout execution, and a platform-neutral roster.
- Restored targeted pull-request and main-branch GUI and pMARS validation while
  keeping display-dependent tests outside ordinary headless pytest discovery.
- Made Python module reload behavior explicit: every entrant load executes a
  fresh private module and constructs a fresh instance.
- Unified VM, Python, and pMARS outcomes behind one canonical result envelope;
  pMARS records use `replay: null`, while `summary.json` remains compatible.
- Updated `battle2 run` terminal output to identify canonical `result.json` and
  replay artifacts alongside the compatibility summary.
- Routed Designer match completion through canonical result/replay artifacts,
  with explicit homogeneous-runtime preflight and concise result presentation.

### Removed

- Removed the v0.1 `match-runner` console-script entry point and its Windows
  build/installer artifact; it called a `PygameRenderer` API removed in
  Phase 7a and had no maintained functionality. Use `bytefray replay
  --renderer pygame` or `battle-replay-viewer.exe` instead.

### Fixed

- Kept native intermediate replays private until canonical v3 serialization
  succeeds, with failed publication removing replay, result, summary, and
  temporary artifacts.
- Bound resumed tournament results to the expected canonical match identity
  and replay-header IDs, retried newly detected corruption immediately when
  requested, and surfaced corrupted counts in CLI and Designer status.
- Allowed `KeyboardInterrupt` and `SystemExit` from Python-agent callbacks to
  propagate through `NativeMatchService` while retaining artifact cleanup.
- Fixed the canonical replay's terminal result record always recording an
  empty final-agent list regardless of what actually happened in the match.
- Fixed `VM.load_code` bypassing the same write-tracking path every other
  arena write uses, which meant an entrant's initial loaded code was
  invisible to replay memory diffs (including at reconstruction time).
- Fixed a stale "Tournament execution has not yet been rebuilt on
  `NativeMatchService`" limitation note that no longer matched the code
  (`TournamentService` has called `NativeMatchService.run()` directly since
  Phase 5) or `docs/TOURNAMENTS.md`.
- Corrected Seeker branch targets so its scan and attack paths remain on valid
  instruction boundaries.
- Reset per-tick CPU usage for every entrant, preventing a dead entrant's final
  tick usage from being added repeatedly to cumulative statistics.
- Removed obsolete tournament CLI arguments and machine-specific paths that
  prevented the tournament controller from working with current source trees.
- Prevented rejected or failed Python matches from leaving stale success
  artifacts, and published completed Python replays atomically.

### Known Limitations

- Python native execution currently supports Python-vs-Python matches only;
  mixed VM/Python matches are rejected explicitly.
- Python source and controller logic are not stored in, or corruptible through,
  arena memory.
- Python agents are trusted in-process code. Hard timeouts and process isolation
  for non-returning callbacks are not implemented; operator abort exceptions
  propagate, but they cannot interrupt a callback that never returns control.
- Canonical replay reconstruction requires a linear scan of memory diffs from
  tick 0; there is no snapshot/checkpoint shortcut for seeking directly to a
  late tick in a long match.
- Individual RNG draws inside agent code are not logged in the replay; only
  each entrant's derived seed is captured. Reproducing an agent's exact
  intermediate reasoning (not just its recorded actions) requires
  re-executing its source against that seed.
- A truncated or corrupted mid-stream replay still fails the whole read at
  the point of corruption rather than offering a partial-recovery mode.

## [0.2.0] - 2026-08-06

### Added

- Added the unified `battle2` dispatcher with `run`, `replay`, `design`, and
  `agents` commands, plus `python -m battle_engine` support.
- Added a canonical replay schema and compatibility reader, deterministic replay
  presentation lifecycle, and extracted VM, scheduling, scoring, statistics,
  results, and telemetry components behind the existing public interfaces.
- Added Python wheel packaging for Python 3.10 through 3.13 with optional replay
  and Designer dependencies kept out of the headless core installation.
- Added writable platform data roots: XDG data directories for installed Linux
  wheels, `%LOCALAPPDATA%\BATTLE2` for installed Windows wheels, and explicit
  `BATTLE2_ROOT` with legacy `BATTLE_ROOT` fallback.
- Added non-destructive initialization of the Runner, Writer, Seeker, and Spiral
  starter-agent catalog in the writable data root.
- Added headless Linux CI and wheel-content validation, optional Linux GUI smoke
  tests, Windows executable builds, and release smoke validation.
- Added reproducible, checksum-pinned tooling and provenance documentation for
  building a console-only Linux pMARS 0.9.5 executable.

### Changed

- Retained the v0.1 `battle-cli`, `match-runner`, and `battle-agent-designer`
  commands as compatibility wrappers while making `battle2` the primary CLI.
- Separated writable runtime data from packaged read-only resources and kept
  source, editable, installed-wheel, frozen-installer, and portable path behavior
  explicit across Windows and Linux.
- Made GUI imports optional and lazy so core commands, wheel checks, and headless
  Linux use do not require Pygame or PySide6.
- Hardened pMARS discovery and execution: explicit overrides, platform-aware
  lookup, shell-free invocation, normalized failures, and validation of runtime
  and wheel contents.
- Defined the release policy that Windows CLI applications bundle pMARS and its
  license, while the platform-neutral Python wheel and Linux wheel do not.
- Updated the Windows installer and portable distribution to build five onedir
  applications, including the unified dispatcher and replay viewer.

### Fixed

- Corrected installed-platform data-root selection and canonical match-output
  paths across Windows and Linux.
- Fixed unified Windows bundle packaging and launch behavior for the Agent
  Designer and its packaged sibling applications.
- Fixed Linux pMARS discovery so stale artifacts and Windows PE resources are not
  selected as Linux executables.
- Strengthened pMARS dependency, runtime, and release validation.
- Removed generated `egg-info` metadata and obsolete empty pMARS license
  placeholders from version control.

### Known Limitations

- The v0.2 Python wheel is headless-first; GUI tools require optional dependencies.
- Linux distributions do not bundle pMARS. Users must supply a compatible native
  executable or build one using the documented experimental tooling.
- Python agent source can be discovered in v0.2, but native matches still require
  a built-in or blob implementation.

## [0.1.0] - 2025-10-05

### Added

- Added the first public Windows build with an Inno Setup installer and portable
  archive.
- Added the headless `battle-cli` engine, Pygame `match-runner`, and Qt-based
  `battle-agent-designer`.
- Established the initial release and staging process.

### Known Limitations

- The starter-agent selection was limited.
- A replay viewer was not included.
- Several Designer controls and replay-playback behaviors were incomplete.
