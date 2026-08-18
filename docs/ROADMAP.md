# Bytefray Roadmap

This document records Bytefray's shipped milestones and the current boundary
from v1.4 through future 2.x gameplay research. It
complements, rather than replaces,
[CHANGELOG.md](../CHANGELOG.md) (what actually shipped, release by release)
and the compact version table in [README.md](../README.md#roadmap). Ideas
that are deliberately **out of** the v1.0 scope — accessible authoring,
agent sharing, richer evaluation statistics, arena/combat research, and so
on — are catalogued separately in [FUTURE_PLANS.md](FUTURE_PLANS.md) so they
stay recorded without turning v1.0 into a checklist of every interesting
feature anyone has proposed.

## Terminology

Status words below are used consistently and are not interchangeable:

- **Planned** — scoped for a specific upcoming release.
- **Candidate** — has real merit and a plausible design, but no assigned
  release; likely to happen if usage or evidence justifies it.
- **Exploratory** — a design direction being thought through; not yet
  validated against evidence, and the shape described could change
  substantially or not happen at all.
- **Research** — requires investigation (data, prototypes, or both) before
  anyone could responsibly commit to a design.
- **Unscheduled** — real, retained, not actively planned.

None of these are promises. They describe how seriously an idea is being
held, not when — or whether — it ships.

## Where Bytefray is now

**Bytefray has shipped `v1.0.0`** (see the version table in
[README.md](../README.md#roadmap) for the full milestone-by-milestone
history). v0.10's theme, **Platform Stabilization / v1.0 Readiness**,
answered the question below (all six numbered items are closed): the
Bytefray 1.0 gameplay Ruleset is frozen as `bytefray-rules-1`, the entrant-
orientation-vs-translation evaluation-methodology question is decided
(fixed arena alignment, translation deliberately deferred), the stable
Agent API v1 contract and compatibility model are documented, Ruleset
identity is now persisted directly into native result/replay artifacts and
folded into canonical match identity, and release qualification
(Windows/Linux/wheel install paths, upgrade/uninstall behavior,
first-user workflow) is complete. No gameplay, Agent API, or evaluation
schema change shipped beyond what is recorded as closed below.

The required pre-1.0 branding/visual-integration gate (see below) landed
across `v1.0.0-rc1`/`v1.0.0-rc2`, and RC-level qualification — full
installer lifecycle qualification, portable ZIP and wheel qualification, a
full RC-version test pass, and a final pre-tag sweep that repaired seven
pre-existing stale-test-debt GUI failures — completed against `v1.0.0-rc2`
before `v1.0.0` itself was tagged and published. No gameplay, Agent API,
Ruleset, or evaluation-schema change shipped between `v1.0.0-rc2` and the
final `v1.0.0` tag.

## v0.10.0 — Platform Stabilization / v1.0 Readiness

v0.10 is intentionally a stabilization release, not another broad feature
release. Its purpose is to answer one question: **is the existing Bytefray
platform ready to have its important contracts declared stable for the 1.x
series?** Concretely, that means:

### 1. Freeze the Bytefray 1.0 rules contract — closed

**Decided in v0.10 Phase 2** (see `docs/RULES.md`): `bytefray-rules-1`
(`battle_engine.rules.BYTEFRAY_RULESET_ID`) is now the first-class,
explicit gameplay-semantics compatibility identity — scoring, scheduling,
entrant orientation/order, arena behavior, observation, mortality/
termination, and winner determination — separate from schema/identity
versioning and from `bytefray.evaluation`'s narrower
`EVALUATION_RULES_COMPATIBILITY_ID`, which is now a derived alias of it
rather than an independently maintained value. A future gameplay change
can bump this identity honestly, without silently reinterpreting what an
older evaluation or replay actually measured.

### 2. Close remaining evaluation-methodology gaps — closed

**Decided in v0.10 Phase 3** (see `docs/COMPATIBILITY.md` and
`docs/RULES.md`): the standard Bytefray 1.0 evaluation contract is
orientation-aware and fixed-arena-alignment, and does **not** claim
translation/placement robustness. This was v0.9's one open
evaluation-methodology question — **translation / placement robustness**,
whether fixed absolute arena alignment creates a structural bias analogous
to the entrant-orientation bias v0.9 closed. v0.9's own dedicated study
found the evidence for gameplay-rule impact mixed (no rule change was
justified), confirmed that fixed-alignment claims about relative strategy
strength can be artifacts of translation phase, and found translation
directly usable for VM/native entrants today but **not implementable for
Python entrants** without new shared runtime work: either a new Agent API
surface exposing a per-match origin, or a transparent, engine-level
per-match address remapping applied at the arena boundary. Phase 3
independently re-verified both findings against the current (now Ruleset
v1/Agent API v1-frozen) source and ran a fresh, independent VM-entrant
study using the production placement mechanism (`MatchEntrant.start`),
which corroborated that relative placement is a real, sometimes large
effect (3 of 4 tested VM matchups flipped winner across placements) while
confirming no path to Python translation exists that avoids either an
incompatible Agent API v1 change (now explicitly off the table, Phase 2)
or the same substantial, separately-scoped runtime engineering v0.9 named
and declined to undertake inline. **Disposition: fixed alignment is the
standard 1.0 methodology; translation remains a documented, deliberately
deferred future capability** — `arena_alignment_mode` already exists as
its extension point, and no evaluation, Ruleset, or Agent API code changed
to reach this decision. See
`runs/research_v0.10/PHASE3_EVALUATION_METHODOLOGY.md` for the full
evidence trail (ignored research, not committed) and
`docs/COMPATIBILITY.md`'s "Experimental/unsupported boundaries" for the
durable, committed statement of what this means for
1.0.

### 3. Define stable versus unstable interfaces — closed

`docs/COMPATIBILITY.md` now documents Bytefray's independent compatibility
axes (project version, Agent API version, Ruleset identity, artifact schema
versions, evaluation methodology, agent revision identity, source
fingerprint versions) with a worked change-impact table, alongside a fully
frozen `docs/AGENT_API_V1.md` (including the literal deterministic
entrant-seed derivation algorithm, pinned by golden-vector regression
tests). The persisted result/replay schemas, `bytefray.evaluation`, agent
revision/provenance identity, and the rules-compatibility identifier from
item 1 are all covered.

### 4. Clarify supported product boundaries — closed

`docs/COMPATIBILITY.md`'s "Experimental/unsupported boundaries" section
names what v1.0's core product actually is — the Python Agent API, the
native Bytefray simulation, replay, tracing/inspection, evaluation,
history/provenance/revisions, and the supported CLI/Designer workflows —
and states plainly that Redcode/pMARS interoperability remains part of
Bytefray's story without blocking v1.0 on full Redcode authoring,
evaluation, provenance, or gameplay parity, none of which exist today.

### 5. Release qualification — closed

v0.10 Phase 5 ran a full release-readiness validation pass: clean Windows
installer and portable builds, Python wheel installation across Python
3.10–3.13, supported Linux/headless installation, existing data-root
compatibility, reading historical replay/evaluation artifacts, revision
verification, deterministic reproduction, and the full
install/upgrade/uninstall lifecycle (including preservation of modified
user data and restoration of prior machine environment values). The v0.10.0
release itself repeated the relevant parts of this pass against the final,
version-bumped build before tagging.

### 6. Polish the first-user workflow — closed

v0.10 Phase 5 fixed the concrete gaps found while walking
create → validate → test → inspect → modify → evaluate → compare → replay
from a clean install: added top-level `bytefray --version` (previously
missing entirely, with unrecognized arguments silently swallowed instead of
erroring), corrected `agents test`'s printed replay-inspection command to
one the CLI actually accepts, and fixed a writable-data-root
false-positive that misdirected a wheel install nested under an unrelated
Bytefray checkout to that checkout's own developer catalog instead of the
documented installed-platform default.

## Required pre-1.0 gate: branding/visual release integration

**Final Bytefray v1.0 must not ship before a dedicated branding/presentation
milestone lands.** This was identified as a required gate during v0.10
Phase 5 (release qualification) and is deliberately **not** part of v0.10
itself — v0.10 is a stabilization release with no branding-implementation
work in its scope. It is recorded here so the roadmap cannot be read as
"v0.10 stabilization complete → proceed straight to v1.0."

The gate covers, narrowly:

- production application/executable icons (the four PyInstaller
  applications (now `bytefray`, `bytefray-cli`, `bytefray-agent-designer`,
  and `bytefray-replay-viewer`) — **done**;
- Windows executable icon resources (`tools/*.spec`) — **done**;
- installer icon/branding (`tools/installer.iss`) — **done**
  (`SetupIconFile`/`UninstallDisplayIcon`; live installer-lifecycle smoke
  under an elevated session is still open, see below);
- the Agent Designer and Replay Viewer application icons specifically
  (`QApplication.setWindowIcon` / `pygame.display.set_icon`, resolved via
  `battle_engine.paths.get_branding_icon_path`) — **done**;
- a horizontal/project logo asset — **done** (in the README header);
- README/GitHub-page imagery and approximately two representative product
  screenshots — **done** (Agent Designer and Replay Viewer, under
  `docs/screenshots/`);
- repository/GitHub visual assets: badges — already present and unchanged;
  a dedicated social-preview image — **considered and deliberately
  deferred**. GitHub's automatic fallback preview is adequate for now, and
  a 1280×640 preview needs its own composition (the horizontal logo's
  3.7:1 aspect doesn't fill that canvas cleanly) plus a manual upload
  through repository Settings that no git-tracked change can perform —
  narrow enough to pick up later rather than block this gate on it;
- any other narrowly-justified release-facing visual integration — none
  identified.

The visual-asset and integration work above is functionally complete as of
`v1.0-rc1-branding`, and both `v1.0.0-rc1` and `v1.0.0-rc2` were published
(RC2 closed a small, UX-only correction found during real RC1 use: Agent
Designer's match selectors now surface an agent's runtime kind before the
existing mixed-VM/Python restriction would reject an invalid pairing,
rather than only after). Neither RC reopened the branding gate above or
changed the underlying mixed-runtime restriction itself — only its
presentation. RC-level qualification that was always out of this gate's
narrow scope — full installer lifecycle qualification, portable ZIP and
wheel qualification, a full RC-version test pass, and a final pre-tag
sweep that repaired seven pre-existing stale-test-debt GUI failures (see
the `pre-v1.0-gui-test-cleanup` merge) — completed against `v1.0.0-rc2`
before `v1.0.0` was tagged. **This gate is closed.**

**Recommended sequencing:** `v0.10.0` → `v1.0.0-rc1` (branding integration
happens here) → `v1.0.0`, rather than inserting a separate numbered
`v0.11.0` branding release. Rationale: branding is release-facing polish
for the 1.0 declaration, not a new capability in the sense every prior
minor version (0.1 through 0.10) has been — bundling it into the release
candidate keeps that convention intact, and an RC's own purpose is to be
what v1.0 will actually look and feel like, which is weaker if the RC ships
without the branding real users will see. It also avoids a full extra
tag/build/publish/changelog cycle for content that is presentation, not
architecture. If branding integration turns out to be larger or riskier
than expected once scoped, revisit this and consider a dedicated `v0.11.0`
instead — the RC can iterate (`-rc2`, `-rc3`, ...) either way before
`v1.0.0` is tagged.

## v1.0.0 — Stable Bytefray Platform

**Status: shipped.** `v1.0.0` is tagged and published; the criterion below
is recorded as the durable definition of what that declaration means for
the 1.x series, not a forward-looking aspiration.

v1.0 is a **stability and maturity milestone**, not "every planned feature
implemented." The release criterion is approximately:

> A Bytefray agent written against the documented 1.0 Agent API can be
> developed, tested, evaluated, reproduced, versioned, and replayed using a
> documented stable ruleset, and its persisted artifacts remain
> intelligible throughout the Bytefray 1.x series.

The intended development model: v0.10 discovers and fixes anything that
would make a 1.0 stability declaration premature. If no major architectural
problem is uncovered, v1.0 follows directly, without another broad
pre-1.0 feature cycle — v1.0 itself should ideally contain little or no new
architecture compared with the stabilized v0.10 platform, aside from the
required branding/visual integration gate above. A v0.11 feature
milestone is **not** created automatically after v1.0; what comes next is
drawn deliberately from [FUTURE_PLANS.md](FUTURE_PLANS.md) as usage and
evidence justify it, the same way milestones have been chosen throughout
Bytefray's history.

## v1.1.0 — Evaluation Insight & Designer Polish

**Status: shipped.** `v1.1.0` is tagged and published. Unlike
every milestone above, v1.1 is not a new capability so much as it is
*surfacing* one: `bytefray.evaluation`'s history/comparison layer
(`battle_engine.evaluation_history`, v0.7) and the agent-revision provenance
store (`battle_engine.agent_revisions`, v0.8) were already complete,
Qt-free, and fully tested — only ever reachable through the CLI
(`bytefray agents evaluations list/show/compare`, `bytefray agents
revisions list/show/restore`). Both feature specs recorded the Designer-side
gap explicitly rather than leaving it implicit (`docs/specs/
evaluation_history.md` §17, `docs/specs/agent_revision.md` §9). v1.1 closes
it:

- an **Evaluation History** browser in Agent Designer (**Tools → Evaluation
  History…**): discover, inspect, and optionally deep-verify past
  `agents evaluate` runs, including legacy schema-v1 artifacts, without
  leaving the GUI or reconstructing state from raw JSON;
- **comparability-first two-run comparison**: candidate/baseline/rules/
  methodology identity are checked and disclosed *before* any per-opponent
  improved/regressed/unchanged/inconclusive verdict is shown, so differing
  experimental conditions are never presented as a clean performance delta;
- **revision/provenance inspection**, including a capability the CLI itself
  doesn't have: a live check of whether an evaluation's archived agent
  revision still matches that agent's *current* on-disk source, or has
  drifted since the evaluation was run.

No Ruleset, Agent API, evaluation/result/replay-schema, or evaluation-
methodology change — this is additive Designer-layer code consuming
already-stable, already-versioned artifacts, verified directly (no
`engine/src`/`client/src` file was touched). Deliberately deferred out of
this slice: replay/Agent-Lab drill-down from a comparison row, revision
*restore* from the GUI (the store/restore primitives are read cleanly but
never written to), cross-evaluation trend charts, and any evaluation-history
indexing (the existing on-demand-scan performance profile, ~1.86s at 1,000
artifacts, was re-confirmed adequate and is not blocking). See
`CHANGELOG.md`'s Unreleased entry for the file-level summary.

## v1.2.0 — Portable Agent Packaging & Sharing

**Status: shipped.** `v1.2.0` is tagged and published.
`docs/FUTURE_PLANS.md`'s "Agent packaging / sharing" (Candidate) promoted
to this milestone: a Bytefray user can export an agent from one
installation into a self-describing portable `.bytefray-agent` file,
transfer it by any ordinary means, inspect it on the receiving end without
executing any of its code, and import it into another installation
without losing the provenance/compatibility information Bytefray already
knows about that agent. Not a centralized registry — the foundational
package format and local import/export workflow a future ecosystem could
build on.

Built entirely as a transport wrapper around one already-archived
`battle_engine.agent_revisions` revision (the content-addressed store
introduced in v0.8, `docs/specs/agent_revision.md`) rather than a second,
parallel packaging-specific content model — see
`docs/specs/agent_package.md` for the full design, including why this was
the right foundation and what packaging exposed that had previously only
ever mattered on one machine (the manifest-only `kind=builtin` starter
agents, whose "source" is actually supplied by the installation itself,
not their own directory — cleanly excluded from export rather than
producing a package that lies about being self-describing).

- `bytefray agents export`/`agents package show`/`agents import` — see
  `CHANGELOG.md`'s `[1.2.0]` entry for the full command reference.
- Introduces exactly one new, independent compatibility axis
  (`bytefray.agent_package` schema/version, currently 1) — no Ruleset,
  Agent API, or artifact-schema change; see `docs/COMPATIBILITY.md`.
- Adversarially tested against path traversal, absolute/UNC/Windows-
  drive-qualified paths, duplicate/case-colliding paths, symlink-mode ZIP
  entries, tampering, truncated/extra payload files, and oversized
  archives (`engine/tests/test_agent_package.py`), and qualified with a
  genuine (not simulated) cross-platform round trip: a package exported on
  Windows was imported, loaded, validated, and re-exported on real Linux,
  and the reverse, producing byte-identical `agent_revision_id` at every
  step.
- Deliberately out of scope for this milestone, per
  `docs/specs/agent_package.md`: an online registry, package signing/PKI,
  dependency installation from PyPI, arbitrary Python environment capture,
  container packaging, and any Designer/GUI integration (the engine/CLI
  workflow is this milestone's release-defining capability; a thin GUI
  wrapper over the same authoritative `agent_package` functions remains a
  well-justified, low-risk candidate for a later slice, following the same
  precedent v1.1 set for evaluation history/revision provenance).

## v1.3.0 — Designer Workflow Completion

**Status: shipped.** `v1.3.0` is tagged and published. Implementation,
independent technical qualification, and the user-completed manual GUI
qualification passed. The installer, four-application portable Windows build,
wheel, source archive, and published SHA-256 values were verified with embedded
1.3.0 identity. An install/uninstall lifecycle run was not performed on the
development workstation and was not a release blocker because the frozen
applications were already qualified and the installer compiled successfully;
that stronger state-mutating check belongs in Windows Sandbox or another
disposable Windows environment. Where
v1.1 surfaced evaluation history/revision provenance into Agent Designer and
v1.2 shipped a CLI-only portable agent-package format, v1.3 finishes
connecting Agent Designer to those already-shipped 1.x engine capabilities
so a normal user manages agents, packages, revisions, evaluations, replays,
and Agent Lab without repeatedly dropping to the CLI — plus a small set of
Windows packaging/build-qualification fixes found during that work. Not a
new gameplay or protocol release: the user-facing workflows primarily reuse
stable v1.1/v1.2 services. Independent qualification also required narrow
correctness hardening in `agent_package` and internal, non-serialized
comparison-row references; describing the entire milestone as an unmodified
thin layer would therefore be inaccurate.

- **Agent package integration in Designer**: "Export Agent…" (Agent
  Development tab), "Import Agent Package…" and "Inspect Agent Package…"
  (Tools menu) wrap the exact, authoritative v1.2 `battle_engine.
  agent_package` functions (`export_agent`/`inspect_package`/
  `import_package`) with no reimplemented validation, ZIP extraction, or
  compatibility logic. Selecting/inspecting a package never executes its
  code; import validates before placement, reports best-effort cleanup
  limitations honestly, and preserves the CLI's collision
  semantics (fail without mutation on genuinely different content,
  iterative explicit alternate-id retry, no-op on an identical revision,
  never an automatic rename). Refresh/selection uses the exact imported
  discovery id even when display names differ or collide, and package
  mutation is guarded while an agent-executing process is active.
- **Package qualification hardening**: the shared domain now bounds the raw
  archive/central directory before `ZipFile` allocation, then validates all
  ZIP metadata and compressed/uncompressed resource limits (including a
  narrow safely parsed `agent.yaml` cap) before decompression; rejects non-portable member names (including Windows
  ADS/device/trailing-dot-or-space hazards), special Unix entries, and
  duplicate/case/ancestor collisions on both read and export; cross-checks
  `package.json`'s compatibility and
  identity metadata against the verified
  archived payload, applies the same limits before export, and normalizes
  malformed compression/read failures to typed package errors. Inspection
  may parse manifest YAML as data but never imports, compiles, or executes
  packaged agent code. This changes validation only; schema-v1 package bytes
  and compatibility identity remain unchanged.
- **Evaluation-comparison-row drill-down**: "Test in Agent Lab"/"Open
  Replay" from a two-run comparison row, deferred explicitly by both
  `docs/specs/evaluation_history.md` §17 and v1.1's own changelog entry.
  Reuses the existing handlers/plumbing; internal left/right schedule ids
  resolve the exact orientation-specific cells without entering comparison
  JSON. The selected cell's own ticks, orientation, and artifact are carried
  through; changed-condition pairs require an explicit side choice, while
  ambiguous groups remain non-actionable. Side labels are neutral **Left
  (selected)**/**Right (comparison)** because picker order is not chronology.
- **Revision restore from Designer**: `RevisionBrowserDialog` gains an
  explicit **"Restore Files…"** action calling `agent_revisions.
  restore_revision`, the one capability `docs/specs/agent_revision.md` §9's
  v1.1 note left CLI-only. It keeps the CLI's safe separate default target
  and non-empty-target force gate, states that force leaves unrelated files
  in place, and requires an extra confirmation for any target inside or
  aliasing into the live `agents/` catalog. Restore is disabled while a
  Designer-owned subprocess is active, including for the remainder of a
  History session that launches an Agent Lab run. A successful live restore refreshes
  the catalog and invalidates stale validation/test evidence.
- **CLI/Designer presentation consistency**: `bytefray agents evaluations
  compare`'s human-readable output now discloses `ambiguous_duplicate_groups`,
  matching what the v1.1 Designer already showed. Its JSON contract is
  unchanged.
- **Windows packaging fixes**: `tools/agent_designer.spec`/`tools/
  replay_viewer.spec` now build the same onedir (thin-launcher-plus-loose-files)
  shape as `tools/bytefray.spec`/`tools/bytefray_cli.spec`, correcting a real,
  previously-shipped inconsistency (both specs previously baked every
  dependency into one fat `EXE` first). `tools/build_win.ps1`'s GUI smoke
  test now isolates its own `BYTEFRAY_ROOT`, waits for GUI-subsystem
  processes with `Start-Process -Wait -PassThru`, checks their actual exit
  codes, and fails closed if smoke roots cannot be removed. Build
  qualification also rejects runtime-generated `agents/` data inside any
  distributable application tree.

No Ruleset, Agent API, evaluation/result/replay-schema, agent-package-schema,
or agent-revision-identity change — see `docs/COMPATIBILITY.md`. See
`CHANGELOG.md`'s `[1.3.0]` entry for the full file-level summary.

## v1.4.0 — Platform Integrity & Scaling

**Status: shipped.** `v1.4.0` is tagged and published. This milestone cleans
and measures the stable 1.x platform without changing `bytefray-rules-1`:

- retire obsolete predecessor product/command/executable/data-root naming
  while preserving stable protocol identifiers and genuine history;
- remove only evidence-backed dead implementation and retain useful historical
  fixtures;
- establish a compact VM/Python Ruleset-v1 golden equivalence corpus before
  engine optimization;
- maintain authoritative ownership counts at the existing VM write boundary,
  eliminating duplicate full-arena territory scans in scoring/statistics;
- publish reproducible, non-CI scaling measurements and make replay-index work
  evidence-driven;
- qualify the already-existing homogeneous three-entrant VM/Python path without
  expanding pairwise tournament/evaluation methodology.

No Ruleset, Agent API, RNG, scheduler semantics, evaluation methodology,
artifact interpretation, package/revision identity, or gameplay change belongs
in v1.4. See [the audit](V1_4_PLATFORM_INTEGRITY.md) and
[scaling report](performance/V1_4_SCALING.md).

The headless-suite total changed from 1241 to 1240 because 13 retired
predecessor-compatibility tests were removed while 12 new integrity and
Ruleset-v1 equivalence tests were added: a deliberate net reduction of one,
not a coverage regression. Release qualification re-ran the golden corpus
after the 1.4.0 identity bump and confirmed unchanged gameplay, identity,
state, statistics, and normalized replay content.

## v1.4.1 — Designer Agent-Selection Fix

**Status: shipped.** `v1.4.1` is tagged and published. This narrow patch fixes Simple and Advanced Designer
match launch when a selected agent's canonical discovery ID differs from its
display name. The shared combo contract remains ID-authoritative; Designer now
resolves that ID to the exact catalog row and accepts a display-name fallback
only when it is unambiguous. Realistic GUI coverage protects starter-shaped
IDs/displays, duplicate display names, and self-match through match-command
construction. No Ruleset, Agent API, replay/result/evaluation schema, package
schema, evaluation methodology, or gameplay behavior changed.

## v1.5.0 — Architecture Evolution Readiness

**Status: planned direction only.** v1.5 may rearrange implementation behind
the frozen Ruleset-v1 behavior: a Ruleset dispatch/policy seam, clearer entrant
identity versus execution-state separation, and a scheduler abstraction. Under
Ruleset v1 there must still be exactly one execution state per entrant, and the
v1.4 equivalence corpus remains the acceptance boundary. No new gameplay,
Agent API v2, multiprocess entrant, replication, or resource semantics.

**Phase 1 (semantic reconstruction and invariant lock) is complete** on
`v1.5-development`: a full Ruleset-v1 semantic ownership map, tick-lifecycle
order, entrant-identity/execution-state field classification, deterministic-
identity dependency graph, golden-corpus coverage audit, and the durable v1.5
invariants later phases must preserve — see
[the Phase 1 baseline](V1_5_PHASE1_RULESET_V1_BASELINE.md). No architecture
changed in Phase 1; it added characterization coverage (Python-side scheduler
call-order tests, VM tick-lifecycle stage-order tests, and a supervised-vs-
unsupervised Python equivalence test) and is the acceptance boundary Phase 2's
Ruleset/policy dispatch work should qualify against, alongside the existing
v1.4 equivalence corpus.

**Phase 2 (scheduler abstraction) is complete** on `v1.5-development`: the
three duplicated Ruleset-v1 entrant scheduling loops (VM, unsupervised Python,
supervised Python) now share one implementation,
`battle_engine.scheduler.run_sequential_quota` — see
[the Phase 2 record](V1_5_PHASE2_SCHEDULER_ABSTRACTION.md). Tick lifecycle,
scoring, statistics, replay, VM-only kill attribution, termination resolution,
and every deterministic identity are unchanged; the v1.4/v1.5 Ruleset-v1
equivalence corpus shows zero golden differences. No Ruleset dispatch/registry
was introduced. This narrows what remains for a future Ruleset/policy-dispatch
phase to the dispatch seam and entrant-identity/execution-state separation
themselves, now sitting behind one shared scheduling implementation instead of
three.

**Phase 3 (Ruleset policy/dispatch seam) is complete** on `v1.5-development`:
a new `battle_engine.ruleset_policy` module pairs the frozen Ruleset-v1
identity with the Phase 2 shared scheduler behind one fail-closed resolver,
`resolve_ruleset_policy` — see
[the Phase 3 record](V1_5_PHASE3_RULESET_POLICY_DISPATCH.md). VM, unsupervised
Python, and supervised Python entrant scheduling now obtain
`run_sequential_quota` through that resolved policy instead of importing the
scheduler directly; runtime-kind (VM/Python) selection remains entirely
outside Ruleset policy. Only `bytefray-rules-1` resolves — any other Ruleset
ID, including the historical `evaluation-rules-1` artifact-provenance alias,
fails closed rather than silently executing as Ruleset v1. Scoring,
statistics, termination resolution, and winner resolution remain outside the
policy seam; the v1.4/v1.5 Ruleset-v1 equivalence corpus shows zero golden
differences.

**Phase 4 (termination policy centralization) is complete** on
`v1.5-development`: the three previously duplicated Ruleset-v1 match
termination decision/reason computations (VM, unsupervised Python,
supervised Python) now delegate to one implementation,
`RulesetPolicy.resolve_termination`, reached through the same Phase 3
dispatch seam already used for scheduling — see
[the Phase 4 record](V1_5_PHASE4_TERMINATION_POLICY.md). Each runtime still
decides *when* to check termination, at exactly the same tick-lifecycle
position as before; the policy only decides *what the answer is*, from
alive count, current tick, and the configured tick limit. Termination
precedence (alive-count-based reasons before the tick limit), exact reason
values/spelling, HALT/forfeit-only-affects-liveness semantics, and winner
resolution's runtime-specific ordering relative to termination are all
unchanged. Scoring, statistics, and winner resolution remain outside the
policy seam; the v1.4/v1.5 Ruleset-v1 equivalence corpus shows zero golden
differences.

**Phase 5 (entrant identity and execution-state separation) is complete**
on `v1.5-development`: a new `battle_engine.entrant_identity.
EntrantIdentity` type gives `match_service.MatchEntrant`, VM `agent_state.
Agent`, and `python_runtime.PythonEntrantState` one authoritative identity
object each, instead of independently storing `agent_id`/`name` as flat
fields duplicable within a class -- see
[the Phase 5 record](V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md). All
three classes keep their original names, public constructor signatures, and
read call sites unchanged via read-only `agent_id`/`name` compatibility
properties; `supervised_runtime.py`, `match.py`, `core.py`, `vm.py`,
`scoring.py`, `statistics.py`, and `telemetry.py` required zero source
changes. VM and Python execution states remain intentionally distinct
rather than unified behind a shared abstraction, Ruleset v1 continues to
create exactly one execution state per resolved entrant, and no persisted
schema, deterministic identity, entrant ordering, Python seed derivation,
or gameplay semantic changed; the v1.4/v1.5 Ruleset-v1 equivalence corpus
shows zero golden differences.

**Phase 6 (integrated architecture-equivalence qualification) is
complete** on `v1.5-development`: a qualification, not a refactor pass --
see [the Phase 6 record](V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md). The
combined result of Phases 2-5 was directly verified equivalent to v1.4.1
Ruleset-v1 behavior, including running the golden corpus against the
actual v1.4.1 source tree (not merely against an unedited test file) and
confirming zero source diff since v1.4.1 in `vm.py`, `scoring.py`,
`statistics.py`, and `rules.py`. A repository-wide architecture-bypass
search found no independent scheduler/termination implementation, no
uncontrolled Ruleset resolution path, and no duplicated entrant-identity
storage. Native runtime qualification exercised real VM, unsupervised
Python, and supervised Python matches (2 and 3 entrants, non-default
scheduler quota) through both the CLI and a freshly built/installed wheel
in an isolated venv. The only production change this phase made was
correcting one stale comment; no test was added, changed, or removed. The
v1.5 architecture is qualified and frozen for release preparation.

## v1.6.0 — Evaluation Scale & Analysis

**Status: planned direction only.** Evidence may justify deterministic parallel
evaluation, presets/suites, richer aggregate and statistical analysis,
behavioral comparison/profiling, larger experimental matrices, and local replay
indexing if real workloads still warrant it. Evaluation methodology and
artifact compatibility must remain explicit; parallelism may change throughput,
never cell identity or results.

## v2.x — Gameplay and Rules Research

**Status: research boundary, not a Ruleset-v2 design commitment.** New gameplay
semantics begin no earlier than 2.x. Candidate research includes multi-unit or
multiprocess entrants, replication/deployment, unit communication, explicit
destructibility or richer attack mechanics, larger-field gameplay, new
scheduler/resource semantics, Agent API v2, and a separately identified
Ruleset v2. Which ideas belong in 2.0 versus later 2.x releases will be decided
only when evidence and an explicit compatibility design exist.

## After v1.0

Substantial work is intentionally kept out of the required v1.0 scope:
accessible agent-authoring (a small, deterministic DSL compiling to the
Agent API), richer evaluation and statistical analysis, evaluation
performance/scaling, and deeper simulation/combat research (arena-size
effects, multipronged/multi-process entrants, replication, and any future
ruleset that would require its own compatibility identity separate from
1.0's). None of it is lost — see [FUTURE_PLANS.md](FUTURE_PLANS.md) for
the organized, maturity-labeled catalogue.
