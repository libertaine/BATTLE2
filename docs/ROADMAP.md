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
in v1.4. See [the audit](archive/v1/V1_4_PLATFORM_INTEGRITY.md) and
[scaling report](archive/v1/V1_4_SCALING.md).

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

**Status: shipped.** `v1.5.0` is tagged and published. It rearranges
implementation behind the frozen Ruleset-v1 behavior: a Ruleset dispatch/
policy seam, clearer entrant identity versus execution-state separation, and
a scheduler abstraction. Under Ruleset v1 there is still exactly one
execution state per entrant, and the v1.4 equivalence corpus remained the
acceptance boundary throughout. No new gameplay, Agent API v2, multiprocess
entrant, replication, or resource semantics.

**Phase 1 (semantic reconstruction and invariant lock) is complete** on
`v1.5-development`: a full Ruleset-v1 semantic ownership map, tick-lifecycle
order, entrant-identity/execution-state field classification, deterministic-
identity dependency graph, golden-corpus coverage audit, and the durable v1.5
invariants later phases must preserve — see
[the Phase 1 baseline](archive/v1/V1_5_PHASE1_RULESET_V1_BASELINE.md). No architecture
changed in Phase 1; it added characterization coverage (Python-side scheduler
call-order tests, VM tick-lifecycle stage-order tests, and a supervised-vs-
unsupervised Python equivalence test) and is the acceptance boundary Phase 2's
Ruleset/policy dispatch work should qualify against, alongside the existing
v1.4 equivalence corpus.

**Phase 2 (scheduler abstraction) is complete** on `v1.5-development`: the
three duplicated Ruleset-v1 entrant scheduling loops (VM, unsupervised Python,
supervised Python) now share one implementation,
`battle_engine.scheduler.run_sequential_quota` — see
[the Phase 2 record](archive/v1/V1_5_PHASE2_SCHEDULER_ABSTRACTION.md). Tick lifecycle,
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
[the Phase 3 record](archive/v1/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md). VM, unsupervised
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
[the Phase 4 record](archive/v1/V1_5_PHASE4_TERMINATION_POLICY.md). Each runtime still
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
[the Phase 5 record](archive/v1/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md). All
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
see [the Phase 6 record](archive/v1/V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md). The
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

**Status: shipped.** `v1.6.0` is tagged and published. It adds bounded
local parallel evaluation, reusable evaluation presets, derived aggregate/
statistical analysis, and derived behavior-profile analytics, all fully
derived from existing evaluation artifacts with no change to Ruleset-v1,
Agent API v1, or any persisted schema. Phase 6's integrated qualification
(see below) found no release-blocking defect.

**Phase 0-1 (scale baseline) and Phase 2 (deterministic parallel
evaluation) are complete** on `v1.6-development` -- see
[V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md](archive/v1/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md)
and
[V1_6_PHASE2_PARALLEL_EVALUATION.md](archive/v1/V1_6_PHASE2_PARALLEL_EVALUATION.md).
`bytefray agents evaluate --workers N` dispatches independent evaluation
cells across a bounded pool of long-lived subprocess workers; worker count
never affects `evaluation_id` or any per-cell result, only wall-clock
throughput.

**Phase 3 (reusable, reproducible evaluation presets) is complete** -- see
[V1_6_PHASE3_EVALUATION_PRESETS.md](archive/v1/V1_6_PHASE3_EVALUATION_PRESETS.md).
`bytefray agents evaluate --preset <name>` and
`bytefray agents evaluation-presets list|show|validate` let a hand-authored
`bytefray.evaluation_preset` YAML file supply default opponent/seed/ticks/
orientation values for an evaluation, with any explicit CLI flag always
overriding it; a preset is purely an input-construction convenience and
never enters `evaluation_id`'s hash or changes what an evaluation means.

**Phase 4 (aggregate & statistical analysis) is complete** -- see
[V1_6_PHASE4_EVALUATION_ANALYSIS.md](archive/v1/V1_6_PHASE4_EVALUATION_ANALYSIS.md).
Wilson-interval win-rate estimates and an exact paired candidate-vs-baseline
significance test (over discordant paired conditions, with explicit
by-opponent/by-orientation breakdowns) are now available from `agents
evaluate`, `evaluations show`/`compare`, and the Designer -- fully derived
from already-canonical evaluation data, no schema change, no ranking system.

**Phase 5 (behavior profile analytics) is complete** -- see
[V1_6_PHASE5_BEHAVIOR_ANALYSIS.md](archive/v1/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md).
`agents evaluate`, `evaluations show`, and the Designer now show a
`behavior:` profile (survival, write activity, territory occupancy/
retention/spread, kill interaction) alongside Phase 4's outcome evidence,
kept structurally independent of it -- fully derived from each cell's
already-written `result.json`, no schema change, no clustering, no
composite score, no behavioral distance (deferred; see the phase record
for why).

**Phase 6 (integrated qualification) is complete** -- see
[V1_6_PHASE6_INTEGRATED_QUALIFICATION.md](archive/v1/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md).
No release-blocking defect was found; two non-blocking findings (a
pre-existing `evaluations compare` fallback-grouping precision gap, and an
`evaluations show` wording inconsistency for an all-inconclusive-pairs
edge case) were disclosed rather than fixed, per the qualification
charter's scope discipline, and are queued for a future maintenance pass
rather than v1.6.0 itself.

**Deferred beyond v1.6.0, not yet committed:** evidence may still justify
larger experimental matrices and local replay indexing, if real workloads
still warrant it, plus the specific deferrals Phase 5 recorded
(replay-derived territory trajectory, write-concentration metrics,
behavioral distance) -- deliberately out of scope for Phase 5, per its own
governing prompt. Evaluation methodology and artifact compatibility must
remain explicit throughout.

## v2.0 Alpha Research — Complete

**Status: closed.** `v2.0.0-alpha.1` through `v2.0.0-alpha.11` are complete
on `v2.0-development` (`main` unchanged throughout). The alpha program
answered the principal gameplay question a first architecture/research pass
([V2_0_ALPHA_ARCHITECTURE.md](archive/v2/V2_0_ALPHA_ARCHITECTURE.md)) opened: whether a
Python-side "vulnerable core" mortality mechanic can check unrestricted
territorial expansion — close to dominant under current scoring since
v0.6.1 (see the `[0.6.1]` CHANGELOG entry) — without collapsing ordinary
play or creating a new universal strategy. Candidate semantics validated;
alpha research is now closed. See
[V2_0_ALPHA_RESEARCH_SUMMARY.md](archive/v2/V2_0_ALPHA_RESEARCH_SUMMARY.md) for the
durable synthesis of all eleven experiments, and each `V2_0_ALPHA<N>_*.md`
document for its own uncorrected evidence record. No `alpha.12` was created;
no further broad gameplay research reopens under this alpha sequence.

Major decisions this program produced, carried into beta as the starting
semantic contract (see [V2_0_BETA1_PLAN.md](archive/v2/V2_0_BETA1_PLAN.md)):

- **Vulnerable Core** (`CORE_SIZE = 8`, owns-zero capture, once-per-tick
  post-action check): validated as the candidate mechanic for Ruleset v2.
- **Core observability** (`CORE_BEACON_BYTE = 0xCE`, owner-maintained
  non-blank invariant): adopted as the candidate semantic that resolves
  alpha.10's information-asymmetry finding.
- **Territory maintenance/decay**: tested only as a contingency gate
  (alpha.11 Resolution B) and **not needed** — Resolution A passed, so the
  gate never opened; no decay mechanic exists anywhere in the codebase.
- **Scoring**: unchanged from Ruleset v1 in every weight and formula.
- **Scheduler**: retained, sequential and order-sensitive; order is an
  accepted competitive factor, and evaluation methodology must balance it.
- **Agent API v1**: retained; no Agent API v2 was needed for offense,
  reactive defense, or placement-agnostic reconnaissance anywhere in the
  program.
- **Core Tracker**: the candidate offensive reference benchmark (the
  placement-agnostic successor to the historical, now-fixture-only Core
  Seeker).
- **Multi-entrant execution**: validated as a supported engine capability
  (900+ 3-entrant matches with zero infrastructure failures), not yet a
  required product workflow.
- **Survivor-only winner eligibility** (alpha.4.1): retained — a dead
  entrant cannot win while any entrant survives.
- **Old Core Seeker**: retained as a historical characterization fixture,
  not removed.
- **Ruleset v1** (`bytefray-rules-1`): remains frozen and untouched
  throughout.

## v2.0.0-beta1 — Ruleset v2 Integration

**Status: shipped.** `v2.0.0-beta1` is tagged and published as a GitHub
prerelease. Converts the evidence-backed `bytefray-rules-2-alpha11` candidate into a
supported, compatibility-honest product ruleset. See
[V2_0_BETA1_PLAN.md](archive/v2/V2_0_BETA1_PLAN.md) for the full scope. Purpose:

- freeze the candidate gameplay semantics validated by alpha.11;
- establish the permanent `bytefray-rules-2` compatibility identity,
  distinct from every historical alpha identity — no aliasing;
- preserve Ruleset v1 and every historical alpha Ruleset identity unchanged
  and executable;
- integrate Ruleset v2 into supported execution/product boundaries;
- perform the one reference-agent cleanup alpha.11 disclosed and deferred
  (Core Tracker's self-core false-positive);
- begin first visible v2 presentation integration only after the semantic
  foundation above is complete.

Phases 1 (semantic identity), 2 (product execution integration), 3 (replay
v2 semantics), 4 (Replay Viewer HUD separation), and 5 (integrated
qualification across Windows/Linux, source/wheel/frozen builds, and
v1/v2/VM-rejection execution) are all complete on
`v2.0-beta1-development` — see
[V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md](archive/v2/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md)
for the full qualification record and GO decision. Release preparation
qualified the wheel, source distribution, portable Windows build, and
Windows installer (full install/upgrade/uninstall lifecycle) against the
release-prep commit, and the `v2.0.0-beta1` tag/GitHub prerelease publish
the exact same commit. See the
[v2.0.0-beta1 release](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0-beta1)
for the published assets and notes. Next planned milestone: **v2.0.0-beta2
— Evaluation & Multi-Entrant Methodology** (see below).

## v2.0.0-beta2 — Evaluation & Multi-Entrant Methodology

**Status: shipped.** `v2.0.0-beta2` is tagged and published as a GitHub
prerelease. Purpose: Ruleset-v2 evaluation methodology
(order/placement/seed balancing
per alpha.11's own requirements), scheduler/order balancing tooling,
multi-entrant evaluation/productization decisions, and core/capture metrics
as first-class evaluation outputs. See
[V2_0_BETA2_PLAN.md](archive/v2/V2_0_BETA2_PLAN.md) for the phase breakdown.

**Phase 1 (Ruleset-v2 1v1 evaluation methodology) is complete** — see
[V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md](archive/v2/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md).
`agents evaluate` gains an explicit `--ruleset {bytefray-rules-1,
bytefray-rules-2}` selector; the historical v1 methodology is preserved
byte-for-byte when omitted. Permanent v2 methodology adds a standard,
mechanically-derived three-placement set, a standard five-seed default,
explicit scheduler-order disclosure, and capture/core evidence as a new
evaluation-output category kept structurally independent of win/loss/
score/behavior. Every gameplay-relevant dimension (Ruleset, order,
placement, seed, ticks) now enters canonical evaluation/schedule identity;
resume and comparison fail closed across any methodology change.

**Phase 2 (multi-entrant evaluation model) is complete** — see
[V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md](archive/v2/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md).
A generic entrant/seat/permutation/layout model replaces 1v1-only
vocabulary where a true seat model is needed, without touching Phase 1's
pairwise identity path. Real 3-entrant evaluation ships through the
existing `agents evaluate --group` flag (reusing `candidate_id`/
`--opponents`/`--ruleset`/`--seeds` unchanged); winner semantics are fully
reused from the engine's own already-N-generic `resolve_winner`, never
reinvented. A third additive schema/identity version (6) covers group
artifacts, leaving v1 (4) and Phase 1's pairwise v2 (5) unchanged. A
genuine Phase 1 defect (a false `planned_identity_inconsistent` health
report on every 1v1-v2 artifact, caused by a stale evaluation-history
rehash check) was found and fixed during this phase's own characterization.
Multi-entrant behavior/capture aggregate analysis remains explicitly
deferred to Phase 3.

**Phase 3 (multi-entrant analysis & strategic metrics) is complete** — see
[V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md](archive/v2/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md).
A new, entrant-symmetric analysis module (`evaluation_group_analysis.py`)
replaces the Phase 2 "deferred" placeholder in both the live CLI and
`evaluations show`: per-entrant outcome classification (winner/surviving-
non-winner/eliminated, never collapsed to a flat win/loss), score/
territory/kill metrics, capture attribution with a directed captor-to-
victim interaction matrix, and seat/layout/seed sensitivity — computed
with no candidate id as an input, so candidate-focused presentation is
provably a pure selection over an already-symmetric result. Two real
defects were found and fixed during this phase's own characterization: a
silently-fabricated "differential" for group cells (now `None`, never a
misleading number), and a capture-tick value that overstated when a
non-terminal capture happened at N >= 3 (now withheld rather than wrong,
with the underlying capture fact/attribution unaffected). Characterization
against three 3-entrant, 5-seed rosters directly re-examined Phase 2's own
"Core Tracker 2/54" finding, showing it reflected sample-size instability
rather than a fixed rate.

**Phase 4 (strategic characterization) is complete** — see
[V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md](archive/v2/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md).
An 11-roster, 990-cell pre-registered corpus pointed Phase 3's analysis
instrument at real strategic questions. Headline finding: Claimer's
Phase-3 100%-win-rate result was matchup-specific, not universal — its
win rate ranges 36.7%-100% depending on roster composition, collapsing
whenever dedicated search-based offense (Core Tracker/Core Seeker) is
present, the same counter-strategy alpha.10/alpha.11 already established.
A real, reproducible kingmaking-like effect (a passive defender inheriting
33-46% of wins from a fight it never joins) and a real pairwise-vs-group
divergence (Core Tracker beats Claimer and Hunter individually but not
together) were both found and explained. A real, consistent global seat
bias (~18pp across the corpus, plausibly last-write-wins-driven) was
disclosed but does not overwhelm strategic differences and is already
neutralized per-entrant by the existing exhaustive-permutation
methodology. No engine/scheduler/scoring/agent code was changed.
**Strategic assessment: proceed with documented concerns** — no Ruleset
revision recommended before Beta2 qualification.

**Phase 4.1 (pre-qualification review remediation) is complete** — see
[V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md](archive/v2/V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md).
It closes five high-severity review findings, restores historical v1
schedule resume identity, documents the deliberate non-zero-start Python
match-identity transition, makes group verification/comparison/self-play
presentation truthful, and leaves stored v4/v5/v6 identity generations
unchanged.

**Phase 5 (integrated qualification) is complete** on
`v2.0-beta2-development` — see
[V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md](archive/v2/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md).
Historical v1/v4, Ruleset-v2 pairwise/v5, and Ruleset-v2 group/v6
identity and resume passed; source-tree CLI/history and isolated-wheel
group workflows passed; N=3/N=4, self-play, verification, comparison, and
worker determinism passed; and the canonical qualification finished with
1,877 passed, 14 skipped, 2 deselected, clean Ruff, clean engine/client
mypy, and clean diff checks. No release blocker or strategic-corpus rerun
is required. Release preparation and publication qualified the wheel,
source distribution, portable Windows build, and Windows installer (full
install/upgrade/uninstall lifecycle) against release commit `b580ad2`; the
annotated `v2.0.0-beta2` tag and GitHub prerelease publish that exact commit.
See the
[v2.0.0-beta2 release](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0-beta2)
for the published assets and notes.

## v2.0.0-beta3 — Workflow & Compatibility Stabilization

**Status: shipped.** `v2.0.0-beta3` is tagged and published as a GitHub
prerelease. The
[Beta3 product-presentation plan](archive/v2/V2_0_BETA3_PLAN.md) audits the shipped
Replay Viewer, Agent Designer, multi-entrant workflows, test seams, and GUI
resource packaging. Phase 2 now ships responsive detailed/compact entrant HUD
layouts, centered integer arena scaling that preserves ordinary requested
window dimensions, compact discoverable help, and stronger authoritative
terminal-state presentation. Phase 3 adds a compact square-icon identity
header, clearer native Quick Match hierarchy, and a real content-replacing
ready/log state whose matchup text follows the current authoritative selections.
Phase 4 adds explicit Pairwise/Group evaluation modes, a canonical
Ruleset-v2 roster/layout/seat-assignment preview, group-aware live and history
presentation, and safe drill-down capabilities without changing methodology or
artifacts. Phase 5 qualified the exact `2.0.0b3` source, wheel, frozen,
portable, installer, Beta2 upgrade, and historical-artifact release candidate.
The annotated tag publishes qualified release commit `401431b`; all five live
release assets were independently downloaded and verified hash-identical. See
the [v2.0.0-beta3 release](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0-beta3)
for the published assets and notes. No gameplay, Agent API, schema, evaluation
identity, or methodology changed.

## v2.0.0-rc1 — Release Qualification

**Status: published qualification candidate.** `v2.0.0-rc1` was published as
a GitHub prerelease on August 24, 2026. RC1 freezes the exact integrated 2.0
product without new gameplay design: Ruleset-v2 direct Python play is the
recommended Designer default, Ruleset v1 remains the valid VM/blob and legacy
path, canonical Ruleset selection reaches result/replay artifacts, and Agent
Development adds read-only `agent.py`/`agent.yaml` inspection. The reorganized
README and current Windows screenshots present the same product.

The exact tagged commit `e4088d3f891d13a1668537dffa170427da475065`
passed 1,908/1,922 Windows headless tests (14 documented skips, two GUI tests
deselected), both separate GUI tests, and 1,917/1,922 Linux headless tests
(five documented skips, two GUI tests deselected), plus focused Designer,
Replay Viewer, historical-artifact, pairwise, and group workflows. Ruff and
both canonical mypy targets were clean. The wheel, source distribution,
portable Windows applications, frozen executables, and fresh/upgrade/uninstall
installer lifecycle all passed artifact-level smoke tests. Candidate and main
CI passed Python 3.10-3.13, Linux-wheel, and Windows frozen-build jobs; main also
passed the optional Linux Pygame/Designer GUI and reproducible Ubuntu pMARS
workflows. All five [published assets](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0-rc1)
were independently downloaded and verified hash-identical. No RC2 milestone is
pre-created; another candidate remains evidence-driven only.

Additional beta releases beyond beta3/rc1 are evidence-driven only and are
not pre-planned.

## v2.0.0-rc2 — Corrected Release Qualification

**Status: published qualification candidate.** `v2.0.0-rc2` was published as
a GitHub prerelease on August 24, 2026. RC2 exists solely to correct RC1's
release-blocking default-placement defect: an omitted-start Ruleset-v2 direct
match (the documented default CLI/README style, and every Designer
Simple/Advanced/Development-Test path, none of which ever set a start
address) collapsed every entrant's vulnerable core onto address 0, letting
the last entrant seeded eliminate every earlier entrant before its first
action. Omitted Ruleset-v2 starts now resolve to a deterministic,
non-overlapping per-seat layout; explicit starts are preserved exactly; and
the engine fails closed before execution if a resolved Ruleset-v2 placement
still overlaps. Ruleset-v1 default placement, Ruleset-v2 gameplay semantics,
the Agent API, all schemas, and evaluation methodology are unchanged. This is
corrective product integration work, not a new gameplay design.

The exact tagged commit `e30cddd47380b18ca3a7770054ba896126ab0f87` passed the
full automated suite (1,936 passed, 14 skipped, 2 deselected) plus 195
GUI/display-backed tests, Ruff, and both canonical mypy targets clean on
Windows. The documented default `bytefray run` command, Agent Designer's
default Quick Match (via its real `RunConfig` → `build_engine_command` →
subprocess path), Development Test, a 3-entrant omitted-start match, explicit
same-address and arena-wraparound overlap rejection, and the Ruleset-v1
omitted-start control were each re-run directly against this candidate --
against the source tree, the installed wheel, and the frozen Windows
executables alike -- and matched their expected corrected/unchanged behavior.
Candidate-branch and main CI passed the Python 3.10-3.13 core matrix, the
Linux wheel build, and the Windows frozen-build job; main also passed the
optional Linux Pygame/Designer GUI and reproducible Ubuntu pMARS workflows.
The wheel, source distribution, portable Windows applications, and installer
all passed artifact-level smoke tests, including a full privileged
fresh-install/upgrade/uninstall lifecycle (`tools/smoke_after_install.ps1
-Lifecycle`) run interactively: installed application smoke, an upgrade
install over the prior RC2 install, and uninstall with user-data preservation
all passed. All five
[published assets](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0-rc2)
were independently downloaded and verified hash-identical. RC3 is not
pre-planned; the expected next step is a short soak/real-use verification
period followed directly by `v2.0.0` final.

## v2.0.0 — Vulnerable Core

**Status: PUBLISHED.** `v2.0.0` was tagged and published as the stable
GitHub Release on August 24, 2026, promoting the qualified `v2.0.0-rc2`
candidate with no engine, UI, schema, or evaluation-methodology change.
Ruleset v2 (`bytefray-rules-2`) becomes a permanent, stable gameplay
identity alongside frozen Ruleset v1; status language across README,
`docs/RULES_V2.md`, and `docs/COMPATIBILITY.md` was updated from beta/RC to
stable, and package/installer version metadata was bumped to `2.0.0`.

The exact tagged commit `965d2f6bf756025a66240aa963681c2efa72130a` passed
the full automated suite (1,936 passed, 14 skipped, 2 deselected) plus 195
GUI/display-backed tests, Ruff, and both canonical mypy targets clean on
Windows — identical counts to the qualified RC2 candidate, confirming the
RC2→final delta was documentation/metadata only. The documented default
`bytefray run` command, a genuine 3-entrant omitted-start match, explicit
same-address/within-core/arena-wraparound overlap rejection, the Ruleset-v1
omitted-start control, Pairwise and Group evaluation, and Agent Designer/
Replay Viewer startup against a real v2 replay were each re-run directly
against this candidate. Candidate-branch and `main` CI passed the Python
3.10-3.13 core matrix, the Linux wheel build, the Windows frozen-build job,
the optional Linux Pygame/Designer GUI smoke, and the reproducible Ubuntu
pMARS workflow. The wheel, source distribution, and portable Windows ZIP
were each installed/extracted into a clean environment outside the source
tree and independently qualified. The full Windows installer lifecycle
passed, including a fresh install/reinstall/uninstall cycle, a real
RC2 → 2.0.0 upgrade in place, and a real v1.6.0 → 2.0.0 upgrade in place,
each preserving user-created agent data and correctly updating the reported
version. All five
[published assets](https://github.com/libertaine/Bytefray/releases/tag/v2.0.0)
were independently downloaded and verified hash-identical.

## v3 Ruleset Research — Closed

**Status: closed.** `v3-research-phase0` through `v3-research-closeout` are
complete on the `v3-research-closeout` branch lineage (`main` unchanged
throughout — the research branches were never merged). The program tested
whether the residual Ruleset-v2 strategic limitation Beta2 Phase 4
identified (dedicated search offense is the only effective counter to
blind expansion, in a narrow parameter region) could be resolved through
locality, offense/defense payoff rebalancing, or a new defensive-scoring
event. Its conclusion:

> **NO RULESET CHANGE CURRENTLY JUSTIFIED — V3 RESEARCH SHOULD CLOSE
> WITHOUT A NEW RULESET.**

Bounded locality was implemented behind an explicitly experimental,
non-stable Ruleset identity (`bytefray-rules-3-alpha1`) and rejected: it
made blind expansion the *dominant* core-capture mechanism instead of
checking it. Two successive defensive-scoring-event designs were
qualified against full-corpus evidence and both failed — the second
(a cross-tick "attack episode" event) came close, qualifying strongly at
the shipped default, but failed two robustness gates at a high, non-default
action budget for reasons independently diagnosed as a mixture of one
agent's implementation artifact and a genuine scheduler property. A
real, mechanically verified scheduler-topology effect was found and is
recorded as a research-methodology constraint, not a gameplay change.
`bytefray-rules-1` and `bytefray-rules-2` are unchanged by every phase of
this program; `AGENT_API_VERSION` was never bumped.

See [V3_RULESET_RESEARCH_SUMMARY.md](archive/v3/V3_RULESET_RESEARCH_SUMMARY.md) for
the navigable phase-by-phase index and
[V3_RESEARCH_CLOSEOUT.md](archive/v3/V3_RESEARCH_CLOSEOUT.md) for the full final
report.

## v3.0 — Product Development

**Status: PUBLISHED.** `v3.0.0` is the current stable release, merged to
`main`. Bytefray
v3.0 is a **product** release
cycle, not a gameplay-semantic one: it proceeds on `bytefray-rules-2`
unchanged and focuses on presentation, agent creation, strategy analysis,
evaluation infrastructure, and distribution quality. See
[V3_PRODUCT_SCOPE.md](archive/v3/V3_PRODUCT_SCOPE.md) for the full product thesis,
compatibility freeze, phase plan, and non-goals, and
[V3_PHASE0_PRODUCT_SCOPE.md](archive/v3/V3_PHASE0_PRODUCT_SCOPE.md) for this cycle's
Phase 0 scope-freeze report.

**Phase 1 (presentation baseline & Replay Viewer branding parity) is
complete** — see
[V3_PHASE1_PRESENTATION_BASELINE.md](archive/v3/V3_PHASE1_PRESENTATION_BASELINE.md).
A baseline screenshot set across the Replay Viewer's HUD modes (detailed,
compact/5-entrant, narrow-window, terminal state) and Agent Designer's
ready/live states was captured against the real running applications, and
the Replay Viewer's header band now carries the same branding icon Agent
Designer's identity header already did, degrading silently if the shared
asset is ever unavailable. No HUD semantic, Ruleset, Agent API, or scoring
change.

**Phase 2 (agent creation & iteration workflow) is complete** — see
[V3_PHASE2_AGENT_CREATION_WORKFLOW.md](archive/v3/V3_PHASE2_AGENT_CREATION_WORKFLOW.md).
Scope was narrowed by explicit direction to six concrete priorities: a
second, self-contained "Annotated Example" scaffold template alongside the
original blank one (`bytefray agents create --template annotated`, and the
identical choice in Agent Designer's New Agent dialog) — deliberately not
a copy of a bundled starter's source, since `docs/specs/agent_scaffold.md`
already recorded why that would misrepresent a new agent's identity; a
Development-tab Reload affordance, wired into a new button and
automatically into Validate/Test, closing a read-only-preview staleness
gap that Validate/Test's own results were never actually subject to;
selectable (copyable) status/error text; a documented, evidence-based null
finding that the Designer's three broad panel-initialization exception
handlers are original defensive design, not a masked historical bug; and
real, driven before/after screenshots. Strategy-analysis presentation was
explicitly held out of scope for Phase 3. No Ruleset, Agent API, scoring,
or provenance change.

**Phase 3 (strategy analysis) is complete** — see
[V3_PHASE3_STRATEGY_ANALYSIS.md](archive/v3/V3_PHASE3_STRATEGY_ANALYSIS.md). Directed
at four questions a user should be able to answer after an evaluation
without cross-referencing separate CLI/GUI text — who won and how
convincingly, what each agent actually did, why a matchup may have favored
one side, and where to inspect the evidence — this phase audited Bytefray's
existing analytics first, then structured and surfaced that data: a
`--json` mode for `agents evaluate`, visual win-rate/confidence-interval
and behavior-profile widgets wired into both the live-run results dialog
and the evaluation-history dialog, and two disclosed v1.6 Phase 6 defects
resolved along the way. Explicitly excluded, by direction: any Elo/Glicko
or composite rating, clustering, and AI-generated strategic text. No
Ruleset, Agent API, scoring, scheduler, or artifact-schema change.

**Phase 4 (evaluation infrastructure) is complete** — see
[V3_PHASE4_EVALUATION_INFRASTRUCTURE.md](archive/v3/V3_PHASE4_EVALUATION_INFRASTRUCTURE.md).
Closed a real GUI/CLI parity gap rather than adding new evaluation
machinery: `EvaluationHistoryDialog` gained the CLI's existing
non-default-condition disclosure (arena size, action budget, kill weight,
experimental locality reach) and an "Open Evaluation Folder" action; the
Designer's Evaluate dialog gained the CLI's already-shipped `--workers`
worker-pool control (confirmed identity-inert — `evaluation_id`/
`schedule_id` are unaffected by worker count); and one GUI comparison state
that previously told the user to leave the GUI and run `evaluations show
--json` to locate a `schedule_id` now discloses that detail in place. No
evaluation-artifact delete/prune/archive capability was added — none exists
in this layer, and Phase 4 did not add one. No Ruleset, Agent API, or
schema change.

**Phase 5 (integration & distribution) qualification is complete** — see
[V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md](archive/v3/V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md).
Proves the composed Phase 0-4 product installs, launches, and runs the full
create → validate → test → evaluate → replay workflow from packaged
Windows and Python-wheel distributions, not just a source checkout — fixing
a real, previously-shipped packaging gap along the way (`tools/bytefray.spec`
and `tools/agent_designer.spec` bundled the original "blank" agent-scaffold
template but never the Phase 2 "Annotated Example" template, so the frozen
Windows builds silently lacked it). No gameplay, Ruleset, Agent API, or
scoring change; `bytefray-rules-2` ships unchanged as v3.0's active Ruleset.

**`v3.0.0-alpha2` (strategy examples & Ruleset clarity) is published** — see
[V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md](archive/v3/V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md).
Scope came from a read-only post-alpha1 product-content audit, not from a
new phase. Two bundled starters (`raider`, `sentinel`) now demonstrate
Ruleset v2's Vulnerable Core mechanic, which no existing starter engaged
with at all, derived as independently maintained product copies of frozen
research reference agents rather than as edits or re-exposures of the
benchmark artifacts. The Agent Designer's Python workflows now state and
select the Ruleset they use — Agent Development tests and pairwise
evaluation both previously inherited the CLI's Ruleset-v1 default silently
and now default to `bytefray-rules-2` — and `bytefray agents` listing marks
each entry `[Python]`/`[VM]`. The audit's rejection of a dedicated
`VM / Redcode` Designer tab was re-verified and honored. No gameplay,
Ruleset, Agent API, or schema change; the frozen v2 benchmark population
verifies with zero drift before and after.

**Phase 6 (release candidate qualification) is complete; `v3.0.0-rc1` is
published** — see
[V3_RC1_QUALIFICATION.md](archive/v3/V3_RC1_QUALIFICATION.md). v3.0 is treated as
feature-complete as of this phase: qualification re-ran the full test
suites, Ruff, both canonical mypy targets, and the frozen-benchmark
verification (9/9, zero drift, before and after), re-verified Ruleset v1/v2/
VM/Redcode compatibility with no semantic change, and rebuilt and
re-qualified the Windows installer, Windows portable ZIP, wheel, and sdist
at the `3.0.0rc1` identity. No new agent, gameplay mechanic, Ruleset
control, replay feature, evaluation metric, or Designer tab was added. Two
known, previously-disclosed gaps remain and are recorded rather than
fabricated: the installer's admin-elevated install/uninstall lifecycle
still needs a session with interactive UAC approval, and Linux GUI
(visible/input) qualification remains unexercised beyond the existing
headless Linux CI and Xvfb startup-smoke workflow — neither is treated as a
release blocker, consistent with alpha1/alpha2 precedent. RC1 stays on
`v3.0-development`; per prior Bytefray release precedent, it is not merged
to `main` until final `v3.0.0`.

**`v3.0.0-rc2` is published** — see
[V3_RC1_DEFAULT_RULESET_DEFECT.md](archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md). Found
after RC1 was tagged: an omitted CLI `--ruleset` resolved to Ruleset v1 for
Python-only matches, while Agent Designer already defaulted to Ruleset v2 —
a new user got materially different gameplay (no vulnerable-core capture
available) from the same nominal CLI/GUI action. Corrected with a shared,
runtime-kind-aware resolver (`battle_engine.ruleset_policy.
resolve_omitted_ruleset_id`) that every product CLI entry point now calls;
explicit `--ruleset` selections, VM/blob convenience, mixed-runtime
rejection, Redcode/pMARS isolation, and evaluation/tournament resume safety
are all unchanged. No engine, gameplay-rules, or schema change. Full
default suite (2375 passed), GUI suite (226 passed), frozen benchmark (9/9,
zero drift), Ruff, and both canonical mypy gates all re-verified green; CI
green on the exact candidate commit; a frozen-executable Ruleset matrix and
a live evaluation/tournament resume-safety demonstration both passed. RC2
stayed on `v3.0-development`, not merged to `main`, until promoted below.

## v3.0.0 — Product and Presentation

**Status: PUBLISHED.** `v3.0.0` was tagged and published as the stable
GitHub Release on August 30, 2026, promoting the qualified `v3.0.0-rc2`
candidate to the stable 3.0 line with no engine, UI, schema, or
evaluation-methodology change since RC2 — a version/documentation-only
release. `bytefray-rules-2` becomes v3.0's permanent active gameplay
identity (unchanged since `v2.0.0`); Agent API v1, `bytefray-rules-1`/
VM-blob compatibility, and Redcode/pMARS external interoperability are all
unchanged.

The exact tagged commit `dbc38e79e1e9c1ac033d21cdb60f85edb8f042a1` passed CI
green (all six jobs: Python 3.10-3.13 core matrix, Linux wheel build,
Windows frozen-build) on `v3.0-development` before `v3.0-development` was
fast-forward merged into `main` at that identical commit — `main` had
received zero prior v3.0 commits, so the merge was a clean fast-forward
with no divergent history to reconcile. The wheel and sdist were rebuilt
and reinstalled into a clean venv (`bytefray --version` reports `Bytefray
3.0.0`) and validated with `tools/check_wheel.py`; the Windows frozen build
was rebuilt (`bytefray.exe --version` reports `3.0.0`) and re-passed the
full 10-check omitted/explicit Ruleset matrix against the frozen
executable, including the `raider`-vs-`claimer` core-capture reproduction;
the Windows installer and portable ZIP were rebuilt at `3.0.0`. All five
[published assets](https://github.com/libertaine/Bytefray/releases/tag/v3.0.0)
were independently downloaded and verified hash-identical to the locally
built artifacts. No RC2→3.0.0 software delta exists beyond version
metadata and documentation — RC2's own full qualification (default suite
2375 passed, GUI suite 226 passed, frozen benchmark 9/9 zero drift, Ruff
and both mypy gates clean) therefore applies unchanged to this release.

See [V3_RC1_QUALIFICATION.md](archive/v3/V3_RC1_QUALIFICATION.md) for the RC1
qualification record and [V3_RC1_DEFAULT_RULESET_DEFECT.md](archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md)
for the RC2 defect fix and its own qualification pass — together they
cover the full v3.0.0 release. `v3.0.0-alpha1`, `v3.0.0-alpha2`,
`v3.0.0-rc1`, and `v3.0.0-rc2` remain published, immutable prereleases;
none was moved, retagged, or rewritten by this promotion.

## v4.0 — Product Development

**v4.0.0-alpha1** (the spatial multi-process update) published August 31,
2026 — see [V4_0_0_ALPHA1_RELEASE_REPORT.md](releases/V4_0_0_ALPHA1_RELEASE_REPORT.md).

### v4.0.0-alpha2 — Seeded Placement & Process Fairness

**Published September 1, 2026.** Adds a second v4 Ruleset
identity, `bytefray-rules-4-alpha2`, differing from `bytefray-rules-4-alpha1`
in exactly two gameplay semantics that the Phase 4 controlled gameplay study
(~36,000 matches) identified as accidental rather than designed:
seed-derived minimum-separated core placement (replacing the fixed
evenly-spread seat layout) and round-robin intra-entrant process selection
(replacing earliest-declared-process priority). Agent API v2, replay schema
4, `Q=8`, core size, reach legality, the `K=2` rotating entrant scheduler,
disruption, and quota redistribution are all unchanged; `bytefray-rules-4-alpha1`
remains unchanged and explicitly selectable everywhere a Ruleset can be
named.

### v4.0.0-alpha3 — Spectator Intelligence, Perspective Cam, & Fight Night

**Status: QUALIFIED, release candidate.** Adds the complete v4 spectator
presentation pipeline across the replay viewer and CLI:

* **Perspective Cam**: First-person entrant perspective replay mode (`V`/`P`
  cycle, `1`–`9` direct selection) rendering only what an entrant has a basis
  to know under Agent API v2 (own core base, own process anchors with reach
  radii, anonymous CURRENT gold radar contacts, and anonymous STALE ghosted
  contacts with tick age).
* **Perspective-Safe HUD**: Persistent opponent cards redact lifecycle state
  to `UNKNOWN` and core/score/territory/kills to `?` placeholders during live
  viewing, revealing canonical values at the match terminal tick. Reactive
  core-capture callouts suppress opponent-vs-opponent eliminations.
* **Spectator Director**: Deterministic dynamic playback pacing (`G` toggle)
  cruising through quiet exploration ticks and decelerating/holding during
  key combat events.
* **Fight Night Presentation**: Compact factual event ribbon (`N` toggle) in
  the arena letterbox gutter with 2-, 3-, and 4-entrant layouts.
* **Non-Intrusive Design**: Pure fallback to Broadcast mode when no trace is
  supplied; $O(1)$ per-frame playback via `PerspectiveCursor`; canonical
  simulation rulesets and Agent API v2 remain 100% frozen.
* **Candidate Phase 9 (Future/Exploratory)**: Color Commentator commentary
  generation (independent research built on top of the qualified spectator
  foundation).

### v4.0.0-alpha4 — Designer Spectator Integration

Focused distribution follow-up to alpha3. The published alpha3 assets were
built before the Designer wiring landed, so Simple/Advanced v4 matches did
not yet produce the trace that Perspective Cam, Spectator Director, and
Fight Night depend on. Alpha4 corrects that: v4 matches launched from the
Designer's Simple or Advanced tabs now automatically record a sibling
`trace.jsonl`, and `bytefray run --trace PATH` is available for explicit CLI
recording. No gameplay Ruleset, Agent API, replay schema, or trace schema
identity changed; historical Ruleset v1/v2 Designer matches remain
replay-only.

## After v1.0

Substantial work is intentionally kept out of the required v1.0 scope:
accessible agent-authoring (a small, deterministic DSL compiling to the
Agent API), richer evaluation and statistical analysis, evaluation
performance/scaling, and deeper simulation/combat research (arena-size
effects, multipronged/multi-process entrants, replication, and any future
ruleset that would require its own compatibility identity separate from
1.0's). None of it is lost — see [FUTURE_PLANS.md](FUTURE_PLANS.md) for
the organized, maturity-labeled catalogue.
