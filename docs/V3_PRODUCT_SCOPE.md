# Bytefray v3.0 — Product Scope

This document defines the v3.0 product cycle's thesis, compatibility
freeze, phase plan, and non-goals. It links to, rather than duplicates,
the v3 Ruleset research record — see
[V3_RULESET_RESEARCH_SUMMARY.md](V3_RULESET_RESEARCH_SUMMARY.md) and
[V3_RESEARCH_CLOSEOUT.md](V3_RESEARCH_CLOSEOUT.md) for that evidence. See
[V3_PHASE0_PRODUCT_SCOPE.md](V3_PHASE0_PRODUCT_SCOPE.md) for the audit and
verification work that produced this scope.

## 1. v3.0 thesis

> **Bytefray v3.0 improves how users create agents, run experiments,
> understand matches, analyze strategies, and install/use the software,
> while preserving Ruleset-2 gameplay compatibility.**

Gameplay semantics are not an active v3.0 workstream. `bytefray-rules-2`
ships unchanged; `bytefray-rules-3` does not exist and is not created by
this cycle.

## 2. Ruleset compatibility position

```text
software version:   Bytefray 3.x
active gameplay:    bytefray-rules-2
Agent API:          v1
```

A Bytefray 3.x software release does not require `bytefray-rules-3`.
Ruleset identity is tied to match semantics, not to marketing/version
numbering — see [COMPATIBILITY.md](COMPATIBILITY.md)'s independent-axes
table, which already states this policy generally; this document only
confirms it applies to v3.0.

## 3. Research-closeout relationship

The v3 Ruleset research program (eight phases plus a closeout) is complete
and its evidence is preserved and indexed — see
[V3_RULESET_RESEARCH_SUMMARY.md](V3_RULESET_RESEARCH_SUMMARY.md). Its
conclusion, **no Ruleset change currently justified**, is why v3.0 is a
product cycle rather than a gameplay cycle. The research is not reopened by
this document; §8 below defines the only process by which it could be.

## 4. Five product workstreams

1. **Presentation / visual experience** — Replay Viewer, Agent Designer,
   branding, first-launch impression.
2. **Agent creation** — the Agent Designer create → validate → test →
   evaluate loop, and its CLI equivalent.
3. **Strategy analysis** — presentation of already-computed evaluation
   evidence (win rates, behavior profiles, capture attribution).
4. **Evaluation infrastructure** — the evaluation CLI/GUI workflow, presets,
   parallelism, history, artifact management.
5. **Distribution / installation / release quality** — packaging,
   installer, documentation accuracy, release qualification.

See [V3_PHASE0_PRODUCT_SCOPE.md](V3_PHASE0_PRODUCT_SCOPE.md) §§7–11 for the
current-state audit of each, and §12 there for the candidate
prioritization table.

## 5. Non-goals for the current cycle

* No new Ruleset merely for version-number symmetry.
* No `ATTACK`/`DEFEND` action.
* No locality (rejected by v3 Phase 2).
* No replication or sub-agents.
* No mutation or evolution mechanics.
* No scheduler rewrite.
* No defensive scoring event (rejected by v3 Phase 5A and Phase 6).
* No new core model.
* No Agent API v2.
* No BFScript/DSL unless independently justified.
* No distributed evaluation unless evidence requires it.
* No speculative rating system (Elo/Glicko/clustering/composite score).

These may be revisited later; none is a current v3.0 product commitment.

## 6. Phase plan

### Phase 0 — Product baseline & scope freeze
This phase. See [V3_PHASE0_PRODUCT_SCOPE.md](V3_PHASE0_PRODUCT_SCOPE.md).

### Phase 1 — Presentation / Replay Viewer

**Status: baseline capture and branding parity complete** — see
[V3_PHASE1_PRESENTATION_BASELINE.md](V3_PHASE1_PRESENTATION_BASELINE.md).
The social-preview asset and panel-init audit items below remain open.

* **Objective**: close the concrete presentation gaps the Phase 0 audit
  found — Replay Viewer branding parity with Agent Designer, a baseline
  screenshot/recording set across HUD modes (compact, 5+-entrant, narrow
  window) that does not currently exist, resolution of the long-deferred
  GitHub social-preview asset, and an audit of the defensive
  `except Exception` panel-initialization pattern in Agent Designer.
* **User-visible benefit**: consistent branding, an accurate visual
  baseline for future presentation work, a better first impression outside
  the product itself.
* **Probable files/components**: `client/src/battle_client/pygame_renderer.py`,
  `client/src/battle_client/hud_layout.py`, `app/widgets/designer_presentation.py`,
  `assets/branding/`, `docs/screenshots/`.
* **Dependencies**: none beyond Phase 0.
* **Exclusions**: no HUD *semantic* change — core integrity, capture, and
  score display logic are unchanged; no engine change.
* **Validation**: manual GUI walkthrough per this project's GUI-testing
  requirement, refreshed screenshots.
* **Ruleset-neutral**: yes.

### Phase 2 — Agent Designer / agent creation workflow

**Status: complete, scope narrowed by explicit direction** — see
[V3_PHASE2_AGENT_CREATION_WORKFLOW.md](V3_PHASE2_AGENT_CREATION_WORKFLOW.md).
Delivered: a second scaffold template (not a starter copy — see that
report §1 for why), a Development-tab Reload affordance wired into
Validate/Test, selectable status/error text, and a documented null finding
on the panel-init exception audit. Contextual in-app Agent API guidance
(the fourth candidate below) was not separately built — the annotated
template's inline comments serve that purpose for a first agent instead;
a dedicated help system remains open if evidence later shows the template
alone is insufficient.

* **Objective**: a starter-based "start from example" scaffold option (CLI
  and GUI both currently offer only a blank template), a watched-file or
  explicit-reload affordance for the Development tab's external-editor
  round trip, contextual in-app guidance for the Agent API concepts a
  first agent requires, and a preset-authoring workflow (presets are
  currently entirely hand-authored).
* **User-visible benefit**: faster create → test → iterate loop, lower
  domain-knowledge floor for a first agent, while preserving deterministic
  behavior and provenance.
* **Probable files/components**: `app/views/development.py`,
  `engine/src/battle_engine/agents.py`,
  `engine/src/battle_engine/evaluation_presets.py`,
  `docs/AGENT_AUTHORING.md`.
* **Dependencies**: none beyond Phase 0; independent of Phase 1.
* **Exclusions**: no change to validation/timeout containment semantics; no
  removal of the external-editor path (Designer source viewing stays
  read-only per its documented v2.0 decision); no Agent API change.
* **Validation**: GUI walkthrough of the full create → validate → test →
  evaluate loop; regression tests for any new scaffold path.
* **Ruleset-neutral**: yes.

### Phase 3 — Strategy analysis

**Status: complete** — see
[V3_PHASE3_STRATEGY_ANALYSIS.md](V3_PHASE3_STRATEGY_ANALYSIS.md). Delivered:
visual win-rate/behavior/capture/interaction-matrix widgets in both
`EvaluationResultsDialog` and `EvaluationHistoryDialog` (the latter
previously the thinnest of the four presentation surfaces despite being the
"drill deeper" workflow), a `--json` mode on `agents evaluate`, and both
disclosed v1.6 Phase 6 presentation defects resolved. `EvaluationComparisonDialog`
was left unchanged — scoped out, not opportunistically touched; a candidate
for a future pass.

* **Objective**: a genuinely visual (not merely re-labeled text) GUI
  presentation of win-rate confidence intervals, behavior-profile
  dimensions, and the capture/interaction matrix; a correlated "why did X
  win" view spanning evidence, behavior, and capture; resolution of the two
  presentation defects disclosed but left open at v1.6 Phase 6
  qualification; a structured (JSON) CLI output mode.
* **User-visible benefit**: users can understand key reasons for a matchup
  outcome without manually cross-referencing separate text blocks.
* **Probable files/components**: `app/views/evaluation.py`,
  `engine/src/battle_engine/agent_evaluation.py`,
  `engine/src/battle_engine/evaluation_group_analysis.py`,
  `engine/src/battle_engine/evaluation_history/cli.py`.
* **Dependencies**: none.
* **Exclusions**: no new composite/opaque rating — evidence and behavior
  stay structurally independent, per this project's existing evidence-based
  caution against unsupported global ratings, unjustified Elo/Glicko, and
  clustering without demonstrated value (see
  [FUTURE_PLANS.md](FUTURE_PLANS.md)'s "Richer evaluation / statistical
  analysis" section).
* **Validation**: presentation reads already-canonical artifacts with no
  re-execution; no `evaluation_id`/schema change.
* **Ruleset-neutral**: yes.

### Phase 4 — Evaluation infrastructure
* **Objective**: CLI/GUI parity (bring `--workers` and other CLI-only
  evaluation controls into the Designer's evaluation dialog), separate the
  v3-research-motivated CLI flags (`--arena-size`/`--instr-per-tick`/
  `--kill-weight`, each of which currently cites a v3 research report in
  its own `--help` text) from the general product-facing `agents evaluate`
  surface, and an evaluation-artifact management/lifecycle command (list
  with size, prune, or archive) for large runs.
* **User-visible benefit**: large evaluations easier to start/resume/
  inspect from the GUI; a less research-cluttered CLI help surface for
  ordinary product use; large-run disk usage becomes manageable rather than
  requiring OS-level file tools.
* **Probable files/components**: `app/views/evaluation.py`,
  `engine/src/battle_engine/agent_evaluation.py`,
  `engine/src/battle_engine/evaluation_history/cli.py`.
* **Dependencies**: none; benefits from Phase 3's structured-output work if
  sequenced after it, but does not require it.
* **Exclusions**: no evaluation identity or schema change; any relocation
  of the research-motivated flags must preserve bit-for-bit reproducibility
  of already-run evaluations that use them (they are already
  identity-bearing, per `docs/V3_PHASE0_RESEARCH_BASELINE.md` §5 and
  `docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md` §5); any prune/archive
  command must never delete without explicit confirmation and must never
  corrupt the canonical identity of a retained artifact.
* **Validation**: existing evaluation artifacts remain loadable and
  identity-stable before and after.
* **Ruleset-neutral**: yes.

### Phase 5 — Integration, distribution, qualification
* **Objective**: synchronize the stale version references in `INSTALL.md`,
  `docs/LINUX_INSTALL.md`, and `SECURITY.md` (all three still name a
  pre-2.0 release while `pyproject.toml` is accurate); investigate and
  disclose the unsigned-installer Windows SmartScreen/antivirus experience
  a new user is likely to hit (currently undisclosed anywhere, unlike the
  portable-ZIP data-root caveat which already is); evaluate whether a
  portable-first/non-admin onboarding path would reduce first-install
  friction; make an explicit, disclosed decision about macOS distribution
  scope rather than leaving it an unstated gap.
* **User-visible benefit**: accurate onboarding documentation; an informed
  (not accidental) trust/friction posture for new users; a clear, disclosed
  platform-support boundary.
* **Probable files/components**: `INSTALL.md`, `docs/LINUX_INSTALL.md`,
  `SECURITY.md`, `tools/installer.iss`, `tools/build_win.ps1`.
* **Dependencies**: benefits from Phases 1–4 landing first so packaging
  reflects the settled product, but is not strictly blocked by them.
* **Exclusions**: no packaging-format rewrite unless evidence from this
  phase's own investigation justifies one.
* **Validation**: full install/upgrade/uninstall lifecycle re-qualification,
  per this project's existing release-qualification precedent.
* **Ruleset-neutral**: yes.

### Phase 6 — Release candidate / final release decision
* **Objective**: integrate Phases 1–5, run full qualification (test suite,
  Ruff, mypy, GUI smoke, install lifecycle), and decide whether to cut an
  RC or add another phase.
* **User-visible benefit**: a shippable, qualified v3.0.
* **Probable files/components**: `CHANGELOG.md`, `pyproject.toml` (version
  bump — deferred to this phase per this repository's established
  precedent of not bumping version metadata until release preparation).
* **Dependencies**: Phases 1–5.
* **Exclusions**: no new feature work in this phase; qualification only.
* **Validation**: this project's existing release-qualification playbook
  (see recent `CHANGELOG.md` RC entries for the pattern).
* **Ruleset-neutral**: yes.

## 7. Compatibility contract

Unless a later approved decision says otherwise:

```text
Ruleset:
    bytefray-rules-2 unchanged

Agent API:
    v1 unchanged

Existing agents:
    remain executable where currently valid

Historical replays/results:
    remain readable

Canonical identities:
    no semantic break

Evaluation schema:
    no gratuitous break

Reference agents:
    behavior unchanged

Scoring:
    unchanged

Scheduler:
    unchanged

Core capture:
    unchanged
```

If a product feature later requires changing one of these, that is a
separate, explicitly gated design decision — not a side effect of UX work.

## 8. Ruleset-reopen gate

A Ruleset-research question may be reopened only if at least one of these
occurs:

* real user gameplay exposes a reproducible strategic limitation;
* new agent designs demonstrate an unhandled capability gap;
* a product feature requires semantic engine support;
* a separately approved research hypothesis is compelling enough to test.

Any such work starts as a new research program, following the same
hypothesis → minimal experiment → evidence → decision → architecture →
implementation discipline the v2 alpha and v3 programs both used. It does
not enter v3.0 implementation by default, and does not promise
`bytefray-rules-3` as its outcome. See
[V3_RULESET_RESEARCH_SUMMARY.md](V3_RULESET_RESEARCH_SUMMARY.md) §7 for the
currently open ideas a reopened program might draw from.

## 9. Success criteria

### Presentation
* Cleaner, evidence-baselined first-launch experience.
* Replay Viewer branding parity with Agent Designer.
* Responsive layout maintained at supported window sizes (already largely
  true; verified rather than assumed by Phase 1).

### Agent creation
* Fewer manual round trips from create → test → evaluate.
* A non-blank starting point available without hand-copying a starter
  agent.
* Preserved reproducibility/provenance throughout.

### Strategy analysis
* A user can identify the key reason(s) a matchup outcome occurred without
  manually cross-referencing separate CLI/GUI text blocks.
* No new unsupported composite score introduced to get there.

### Evaluation infrastructure
* Every CLI evaluation control available from the Designer, or a disclosed
  reason it is not.
* Large evaluation artifacts (thousands of files, tens of megabytes —
  already an exercised real-world scale) are manageable without OS-level
  tools.

### Distribution
* `INSTALL.md`/`docs/LINUX_INSTALL.md`/`SECURITY.md` name the actual
  current release.
* The installer-trust experience (SmartScreen/AV) is disclosed, whether or
  not it is changed.
* A macOS distribution position is stated, whether "not supported" or
  planned.

No arbitrary numeric UX target is set without a concrete measurement
method behind it.

## 10. Deferred future Ruleset research

See [V3_RULESET_RESEARCH_SUMMARY.md](V3_RULESET_RESEARCH_SUMMARY.md) §7 and
[FUTURE_PLANS.md](FUTURE_PLANS.md)'s "Future simulation / combat research"
section for the full, deliberately non-committal catalogue — including the
new "Agent lifecycle: mutation, evolution, and replication economics" and
"Execution-trace / intent semantics" candidates this Phase 0 cycle added.
None of it is a v3.0 commitment; each item requires its own
hypothesis-driven research program under §8's gate before any design work
begins.
