# Bytefray v3.0 Phase 0 — Product Baseline & Scope Freeze

Branch: `v3.0-development`, cut from `v3-research-closeout` at `4362fe4`.
Status: scope/documentation phase complete, not merged, not tagged, not
published. No production code was changed by this phase.

This phase establishes the v3.0 product scope and compatibility baseline,
and ensures the completed v3 Ruleset research is preserved, discoverable,
historically accurate, and clearly separated from shipped gameplay
semantics. It implements no feature, changes no Ruleset/API/scoring/
scheduler/capture/reference-agent behavior, and begins no release
packaging.

---

## 1. Initial repository state

Verified directly before any mutation, not assumed from this task's own
prompt:

| ref | value |
|---|---|
| starting branch | `v3-research-closeout` |
| HEAD | `4362fe4a57c470bceb0054669a5e73c7998d5ad9` ("docs(v3): record the final v3 research-closeout findings") |
| working tree | clean (one unrelated `.pytest-cache-v141/` permission warning from `git status`, not a tracked-file issue) |
| `main` | `1093393b401aabda243ed89b7c44fa91938477b5` |
| `origin/main` | `1093393` — identical, no unpushed divergence |
| `v2.0.0` tag | annotated, targets `965d2f6`; confirmed an ancestor of `main` |
| all historical release tags (`v0.1.0` … `v2.0.0-rc2`) | present, intact, unmodified |
| `v3-research-phase0` … `v3-research-phase7`, `v3-research-closeout` | all present at their previously recorded commits; untouched by this phase |
| `main` vs `v3-research-closeout` relationship | `main` is a strict git ancestor of `v3-research-closeout` (`git merge-base --is-ancestor` confirms) — 31 commits of pure research work sit ahead of `main` with **zero divergence**; no research branch has been merged into `main` |
| `docs/ROADMAP.md`/`FUTURE_PLANS.md`/`COMPATIBILITY.md`/`README.md`/`CHANGELOG.md` | byte-identical between `main` and `v3-research-closeout` before this phase (empty `git diff`) — research work never touched product documentation |
| frozen `v2-baseline` benchmark population | **16/16 focused tests pass** (`engine/tests/test_v3_phase0_benchmark_population.py -q`), including live-tree revision verification of all 9 members — independently re-confirmed, not merely cited from a report |
| current Ruleset IDs | `BYTEFRAY_RULESET_ID = "bytefray-rules-1"`, `BYTEFRAY_RULESET_V2_ID = "bytefray-rules-2"` — both unchanged between `main` and `v3-research-closeout`; one new, explicitly non-stable, non-product-facing identity exists (`bytefray-rules-3-alpha1`, Phase 2's locality mechanic), never exposed on any product CLI's `--ruleset` choices |
| current Agent API version | `AGENT_API_VERSION == 1` on both `main` and `v3-research-closeout`, unchanged |
| pre-existing stash entries | three, all predating this program (`sync_win auto-stash` ×2, a `feature/pygame-window-fit` WIP) — verified still present and untouched |
| package version | `pyproject.toml`: `version = "2.0.0"` — not bumped by this phase |

**No experimental research branch has been merged unintentionally.** `main`
carries no v3 commit of any kind.

## 2. Research-history audit

An independent audit (a dedicated review agent, read-only, no edits) diffed
every `engine/src/battle_engine/*.py` file that differs between `main` and
`v3-research-closeout` — 15 files plus one new module (`benchmarks.py`) —
line by line, and separately grepped both branches for
`BYTEFRAY_RULESET_ID` and `AGENT_API_VERSION`. Findings:

* Every behavioral difference from `main` is gated on either (a) a new
  optional parameter/field whose default (`None`/`False`) reproduces the
  prior hardcoded value or code path exactly, or (b) membership in a
  Ruleset-id set that now additionally contains the new, non-product-facing
  `bytefray-rules-3-alpha1` identity — never reachable from any existing
  CLI/default call path.
* `BYTEFRAY_RULESET_ID` (`"bytefray-rules-1"`) and `AGENT_API_VERSION`
  (`1`) are byte-identical on both branches.
* **No compatibility concerns were found.** The audit's overall verdict:
  "safe to treat `v3-research-closeout`'s `engine/src` state as
  behavior-identical to `main` for default/existing agents and matches."

This directly informed the branch-base decision in §3 below and the
compatibility freeze in §6.

## 3. Ruleset research preservation status

All ten v3 research reports (Phase 0 through the closeout) are present,
uncorrected, and were read in full for this audit — not sampled or
reconstructed from memory. See §4 for the resulting inventory.

**Branch-base decision.** The governing task's default preference is to
branch v3.0 product work from `main`, "not from a research branch, unless
repository history proves another base is required." Repository history
does prove that here: the ten v3 research reports and every supporting
tool/test/benchmark-manifest exist **only** on the `v3-research-closeout`
branch lineage — `main` has none of them (§1). Branching v3.0-development
from `main` would have made every link this document and
`V3_PRODUCT_SCOPE.md` make into the research record a dead link, directly
undermining Phase 0's own preservation/discoverability goal.

Three facts make `v3-research-closeout` a safe base rather than a
compromise:

1. `main` is a strict ancestor with zero divergence (§1) — there is no
   product-side change on `main` this branch choice could lose or conflict
   with.
2. The independent audit (§2) confirms the accumulated engine changes are
   behavior-identical to `main` for every existing Ruleset/agent/match.
3. This mirrors the repository's own v2 precedent: the eleven-phase v2.0
   alpha research program ran directly on `v2.0-development`, and every
   subsequent beta/RC product branch (`v2.0-beta1-development`, etc.)
   descends from that same history rather than restarting from a
   pre-research `main` — see `docs/ROADMAP.md`'s "v2.0 Alpha Research —
   Complete" section.

`v3.0-development` was therefore created from `v3-research-closeout` at
`4362fe4` (§1), not from `main`.

## 4. Software-version vs Ruleset distinction

Already documented as a general policy in
[COMPATIBILITY.md](COMPATIBILITY.md)'s independent-axes table (project
version, Agent API version, Ruleset identity, artifact schema versions,
evaluation methodology, agent revision identity, source fingerprint
versions, agent package format — each independent, a change to one never
implying a change to another). This phase adds one confirming paragraph to
`COMPATIBILITY.md` rather than duplicating the existing policy (see §17),
and states it explicitly for v3.0 in
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §2:

```text
software version:   Bytefray 3.x
active gameplay:    bytefray-rules-2
Agent API:          v1
```

## 5. v3.0 product thesis

> **Bytefray v3.0 improves how users create agents, run experiments,
> understand matches, analyze strategies, and install/use the software,
> while preserving Ruleset-2 gameplay compatibility.**

See [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §1. This is the prompt's
own working statement; repository evidence (the workstream audits in
§§7–11 below) supports it without needing refinement.

## 6. Compatibility freeze

Confirmed unchanged, by direct verification rather than assertion (§1–§2):

```text
Ruleset:              bytefray-rules-2 unchanged
Agent API:             v1 unchanged
Existing agents:       remain executable where currently valid
Historical replays/results: remain readable
Canonical identities:  no semantic break
Evaluation schema:     no gratuitous break
Reference agents:      behavior unchanged
Scoring:               unchanged
Scheduler:              unchanged
Core capture:           unchanged
```

Full statement in [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §7.

---

## 7. Workstream 1 — Presentation

Audited by a dedicated read-only review of the Replay Viewer
(`client/src/battle_client/pygame_renderer.py`, `hud_layout.py`), Agent
Designer (`app/agent_designer.py`, `app/widgets/designer_presentation.py`),
branding assets, and `docs/screenshots/`.

**Current state.** The HUD-separation and responsive-layout work the
README/CHANGELOG claim (Beta1 Phase 4, Beta3) is real: non-overlapping
HUD/arena/footer bands, a documented minimum viewer size, and text
truncation with an explicit priority hierarchy for 5+-entrant compact mode.
Agent Designer has a branding header
(`DesignerIdentityHeader`) and a genuine empty/ready state that only
switches to a log view once real output arrives.

**Problems found.**
1. No branding/identity band in the Replay Viewer itself — only Agent
   Designer has one.
2. The GitHub social-preview image was explicitly deferred at the v1.0
   branding gate and is still unresolved.
3. Only two static screenshots exist as baseline evidence, neither showing
   the compact/5+-entrant HUD mode, narrow-window behavior, or the
   empty/ready states actually operating.
4. Three of Agent Designer's core tabs wrap their own panel construction in
   broad `except Exception` handlers with `QMessageBox` fallbacks — evidence
   of historically fragile panel initialization, not merely defensive
   style.
5. Quick Match's grid-size/tick inputs are fixed combo presets with no
   freeform entry; any other value requires the Advanced tab.

**Likely Phase 1 scope**: baseline screenshot/recording capture across HUD
modes before further work; Replay Viewer branding parity; resolve the
deferred social-preview asset; audit (not necessarily rewrite) the
broad-exception panel-init pattern. See
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 1.

## 8. Workstream 2 — Agent creation

Audited: Agent Designer's Simple/Advanced/Development tabs, `bytefray
agents create/validate/test`, `docs/AGENT_AUTHORING.md`,
`docs/specs/agent_scaffold.md`, `docs/specs/agent_validation.md`.

**Current state.** A complete create → validate → test → replay → modify
loop exists in both CLI and GUI. Scaffolding writes one fixed minimal
template with no template choice. Designer source viewing is deliberately
read-only (a documented v2.0 decision); editing happens externally via
"Open Agent Folder." Validation/testing run supervised with a timeout —
explicitly disclosed as hang containment, not a security sandbox.

**Problems found.**
1. The external-editor round trip has no file-watching or reload signal —
   the Designer cannot tell whether the user changed anything between
   Validate/Test clicks.
2. No template/strategy starting-point choice in CLI or GUI scaffolding —
   `NewAgentDialog` is a single agent-id field; a user's only path to a
   non-trivial starting point is manually copying a bundled starter agent.
3. Understanding what to write into `act()` requires reading
   `AGENT_AUTHORING.md`'s runtime-model section separately; nothing in the
   Designer surfaces this contextually.
4. Presets are entirely hand-authored YAML — no CLI or GUI command
   generates one from a running configuration.

**Likely Phase 2 scope**: a starter-based scaffold option; a
watched-file/reload affordance; contextual in-app API guidance; a
preset-authoring workflow — while preserving deterministic behavior and
provenance and not removing the read-only/external-editor model. See
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 2.

## 9. Workstream 3 — Strategy analysis

Audited: `agent_evaluation.py`'s CLI print functions, `EvaluationResultsDialog`
(`app/views/evaluation.py`), `evaluation_group_analysis.py`.

**Current state.** The underlying analytics are already rich and shipped
(v1.6 Phases 4–5, Beta2 Phase 3): Wilson-interval win rates, an exact
paired significance test, behavior profiles, and — for Ruleset v2 —
capture/core evidence with a directed captor→victim interaction matrix.
Presentation of all of this is entirely plain text in both CLI and GUI; the
GUI is a `QLabel`/`QPlainTextEdit` re-rendering of the same text a CLI user
reads, not a differently (visually) presented view.

**Problems found.**
1. No visualization anywhere — `FUTURE_PLANS.md` still lists "improved
   comparative visualization" as an open, never-started item.
2. The captor→victim interaction matrix prints as a flat text list, even
   for larger rosters.
3. Evidence and behavior are deliberately structurally independent (by
   design), which means a user has to manually correlate two un-linked text
   blocks to answer "why did X beat Y."
4. Two presentation defects disclosed but left open at v1.6 Phase 6
   qualification (a compare-fallback grouping-precision gap, a
   show-wording inconsistency) remain unresolved.
5. No structured (`--json`) output mode on `agents evaluate` — only the
   written `evaluation.json` artifact itself is structured.

**Likely Phase 3 scope**: a genuinely visual GUI presentation of the
already-computed evidence; a correlated "why did X win" view; resolving the
two disclosed defects; a structured CLI output mode — without introducing
any new unsupported composite rating. See
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 3.

## 10. Workstream 4 — Evaluation infrastructure

Audited: `agents evaluate`'s full CLI surface, `EvaluationDialog`,
`evaluation_history/cli.py`, `pyproject.toml`'s packaged-data
configuration, `runs/` layout on a real evaluation artifact.

**Current state.** Presets, bounded parallelism (`--workers`), resume, and
history (`evaluations list/show/compare`) are mature, product-facing CLI
surfaces. Research-only `tools/v3_*.py` scripts are confirmed **not**
shipped in the product wheel (`pyproject.toml`'s packaged-data glob covers
only `battle_engine/data/**/*` and `app/assets|images|sounds/**/*`) and
their output directories are never scanned by the product's evaluation
history browser — already properly isolated.

**Problems found.**
1. No CLI/GUI parity on `--workers` or other evaluation controls — zero
   references to worker count anywhere under `app/`; every Designer-launched
   evaluation runs single-worker with default experimental-condition
   values.
2. The v3-research-motivated CLI flags (`--arena-size`, `--instr-per-tick`,
   `--kill-weight`) each cite a v3 research report directly in their own
   `--help` text, yet live permanently on the general-purpose,
   product-facing `agents evaluate` command.
3. No artifact-lifecycle command — `evaluations` offers only
   `list`/`show`/`compare`, no delete/prune/archive, despite a real,
   already-exercised 2,000-cell evaluation scale (v1.6 Phase 2's own stress
   test) that produces thousands of small files and tens of megabytes on
   disk.
4. No structured CLI output mode (shared with Workstream 3's finding).

**Likely Phase 4 scope**: bring CLI-only evaluation controls into the
Designer; separate the research-motivated flags from the general product
surface (without breaking reproducibility of evaluations that already use
them — they are already identity-bearing); an evaluation-artifact
management command. See [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 4.

## 11. Workstream 5 — Distribution

Audited: `tools/installer.iss`, `tools/build_win.ps1`, `tools/*.spec`,
`INSTALL.md`, `docs/LINUX_INSTALL.md`, `SECURITY.md`, `pyproject.toml`'s
version metadata, recent `CHANGELOG.md` release-qualification entries.

**Current state.** Release qualification is unusually rigorous per release
(full install/upgrade/uninstall lifecycle, hash verification of every
published asset, cross-platform CI, documented every release since RC1).
Four PyInstaller onedir applications are packaged consistently; version
metadata is consistent at the code level (`pyproject.toml`,
`tools/installer.iss`, release asset naming all agree on `2.0.0`).

**Problems found.**
1. `INSTALL.md` and `docs/LINUX_INSTALL.md` both still show `v1.6.0`-era
   filenames/examples throughout, despite hedging with "see README.md for
   the current release" — every concrete copy-pasteable command names a
   stale version.
2. `SECURITY.md` still states "security fixes are made against the latest
   `1.x` release," predating the 2.0.0 line.
3. No code signing anywhere in the release pipeline, combined with an
   admin-elevated installer — a plausible Windows SmartScreen/antivirus
   experience for new users that is nowhere disclosed (unlike the portable-
   ZIP data-root caveat, which is proactively disclosed).
4. Windows-only elevated packaging; Linux ships wheel-only (already
   disclosed); macOS has no packaged distribution path and no stated
   position on one.
5. No disclosed release-artifact size figures despite four Qt/Pygame-bundled
   onedir applications.

**Likely Phase 5 scope**: synchronize the three stale-version documents;
investigate and disclose the installer-trust experience; evaluate a
portable-first onboarding path; make an explicit, disclosed macOS scope
decision — without a packaging-format rewrite unless this investigation
justifies one. See [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 5.

---

## 12. Candidate prioritization table

Evidence-grounded candidates from §§7–11 only — no speculative wishlist
items.

| Candidate improvement | Workstream | User benefit | Evidence/problem | Ruleset impact | API impact | Compat. risk | Effort | v3.0 priority |
|---|---|---|---|---|---|---|---|---|
| Baseline screenshot/recording set across HUD modes | Presentation | Grounds all future presentation work in evidence | Only 2 static screenshots exist; no compact/5+-entrant/narrow-window evidence | None | None | None | Low | **High** |
| Replay Viewer branding parity | Presentation | Visual consistency with Designer | Designer has a branding header; Viewer has none | None | None | None | Low–Med | Medium |
| Resolve deferred social-preview asset | Presentation | Better first impression outside the product | Deferred since the v1.0 branding gate | None | None | None | Low | Low |
| Audit broad `except Exception` panel-init pattern | Presentation | Understand/reduce historical fragility | 3 of 3 core Designer tabs wrapped defensively | None | None | None | Low (audit) | Medium |
| Starter-based "start from example" scaffold | Agent creation | Lower domain-knowledge floor for a first agent | `NewAgentDialog`/`agents create` offer only a blank template | None | None | None | Medium | **High** |
| Watched-file/reload affordance in Development tab | Agent creation | Faster iteration | Fully manual external-editor round trip, no reload signal | None | None | None | Medium | **High** |
| Contextual in-app Agent API guidance | Agent creation | Lower domain-knowledge floor | `act()` semantics only documented externally | None | None | None | Med–High | Medium |
| Preset-authoring workflow | Agent creation / Eval infra | Faster iteration on repeated evaluations | Presets are entirely hand-authored, no generate/save-as path | None | None | None | Medium | Medium |
| Visual GUI presentation of evidence/behavior/capture | Strategy analysis | Users understand *why* one agent won | GUI is a text re-rendering of CLI text; visualization still an open item in `FUTURE_PLANS.md` | None | None | None | High | **High** |
| Correlated "why did X win" view | Strategy analysis | Same as above, unified | Evidence/behavior/capture are three un-linked blocks today | None | None | None (must preserve structural independence) | High | Medium |
| Resolve two disclosed v1.6 Phase 6 presentation defects | Strategy analysis | Correctness/trust | Explicitly queued from qualification, still open | None | None | None | Low | Medium |
| Structured (`--json`) CLI output mode | Strategy analysis / Eval infra | Automation/tooling | No `--json` flag on `agents evaluate` | None | None | None | Low–Med | Medium |
| CLI/GUI parity on `--workers` etc. | Evaluation infra | Large evaluations usable from the GUI | Zero worker-count references anywhere under `app/` | None | None | None | Medium | **High** |
| Separate research-motivated flags from product CLI surface | Evaluation infra | Clearer product help surface | `--arena-size`/`--instr-per-tick`/`--kill-weight` cite v3 research docs in their own `--help` | None | None | Low (must preserve reproducibility of evaluations using them) | Medium | Medium |
| Evaluation-artifact management command | Evaluation infra | Large-run usability | Real 2,000-cell-scale runs produce thousands of files, tens of MB, no lifecycle command | None | None | Low (prune is destructive; needs confirmation) | Medium | Medium |
| Sync `INSTALL.md`/`LINUX_INSTALL.md`/`SECURITY.md` versions | Distribution | Accurate onboarding docs | All three name a pre-2.0 release | None | None | None | Low | **High** |
| Investigate/disclose installer-trust experience | Distribution | Informed trust posture | No code signing, admin-elevated installer, undisclosed | None | None | None | Low (investigate) | Medium |
| Evaluate portable-first onboarding path | Distribution | Less first-install friction | Installer requires elevation; portable ZIP already exists as an alternative | None | None | None | Medium | Low–Med |
| Explicit macOS distribution-scope decision | Distribution | Clear, disclosed platform boundary | Absent from README's Platforms section, no stated position | None | None | None | Low (decision) | Low |

Full ranking rationale — user visibility, user friction, strategic
usefulness, compatibility risk, implementation risk, evidence, release
coherence — follows [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md)'s own phase
sequencing (§6 there), which reflects this table.

## 13. v3.0 phased plan

See [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §6 for the full six-phase
plan (Presentation → Agent creation → Strategy analysis → Evaluation
infrastructure → Distribution → Release candidate), each with objective,
user-visible benefit, probable files, dependencies, exclusions, validation
requirements, and confirmed Ruleset-neutrality.

## 14. Non-goals

See [V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §5 for the full list. None
of the twelve non-goals listed there is contradicted by anything found in
this audit.

## 15. Deferred Ruleset research

See [V3_RULESET_RESEARCH_SUMMARY.md](V3_RULESET_RESEARCH_SUMMARY.md) §7 and
the new "Agent lifecycle: mutation, evolution, and replication economics"
and "Execution-trace / intent semantics" sections added to
[FUTURE_PLANS.md](FUTURE_PLANS.md) by this phase (§17 below). Framed
explicitly as candidates requiring separate hypothesis-driven
qualification — no mechanics designed, no `bytefray-rules-3` promised.

## 16. Research-artifact disposition

Classified per the governing task's four categories. Nothing was deleted;
this is an audit, not a cleanup.

**A. Permanent research infrastructure** (kept — supports reproducibility
and future research):
* `engine/src/battle_engine/benchmarks.py` — the frozen-population
  manifest loader/verifier/stager. Not imported by any product code path
  (confirmed by the §2 audit), so it is inert for the shipped product but
  reusable by any future research program.
* `engine/tests/test_v3_phase*.py`, `test_v3_closeout.py` — beyond
  documenting Phase N's own findings, these actively protect the
  compatibility freeze going forward (e.g., asserting Ruleset v1/v2 stay
  byte-identical to a stray locality parameter).
* `data/benchmarks/v2_baseline.json`, `v2_baseline_corpus.json` — the
  frozen population and its reproduced Beta2 control, referenced by every
  subsequent phase's own numbers.

**B. Historical experiment tooling** (kept — a published/committed report
depends on it):
* `tools/v3_phase0_baseline_corpus.py` through `tools/v3_closeout_*.py`
  (21 scripts) — each phase report's own tables are reproducible only by
  rerunning these against the exact committed corpora.
* `data/benchmarks/v3_phase1_arena_action_grid.json`,
  `v3_phase2_locality.json`, `v3_phase2_locality_corpus.json`,
  `v3_phase5a_defensive_event_gates.json`,
  `v3_phase6_active_defense_gates.json` — predeclared gate/corpus
  definitions each report's verdict was scored against.
* The `bytefray-rules-3-alpha1` locality-mechanic implementation across
  `agent_api.py`/`python_runtime.py`/`supervised_runtime.py`/
  `ruleset_policy.py`/`match_service.py`/`placement.py`/`replay.py`/
  `telemetry.py` — substantial, production-quality engine code
  implementing a **rejected** mechanic. It is kept, not because it is
  reusable, but because Phase 2's published report is reproducible only if
  it exists and because this project's research-integrity rule is "do not
  delete historical research tooling simply because the hypothesis
  failed." A future, separately-gated decision — not this Phase 0 — would
  be required to remove it.

**C. Potentially reusable product infrastructure** (not automatically
promoted):
* The `--arena-size`/`--instr-per-tick`/`--kill-weight` CLI flags on
  `agents evaluate` — unlike everything else in this section, these are
  **already live, callable, product-facing CLI surface today**, not a
  research-only artifact. They were added for v3 research and still cite
  v3 research reports in their own `--help` text. Whether they belong on
  the general product command, on a separate research-tooling surface, or
  removed from product `--help` entirely is exactly Workstream 4's finding
  (§10) and Phase 4's objective (`V3_PRODUCT_SCOPE.md`) — not decided here.

**D. Disposable probe/artifact** (research-only, must not appear in normal
discovery):
* `data/v3_locality_agents/*` (six agents backing Phase 2, all sharing no
  agent id with the v2 population).
* `data/v3_closeout_agents/turtle_core_refresher/` (explicitly labelled
  "research probe only" in its own manifest).
* `data/v3_phase7_agents/core_tracker_offset/` (a disposable one-line
  control variant of the real `core_tracker`).

**Discovery-isolation check (confirmed, not assumed).** Normal agent
discovery (`discover_agents`/`resolve_agent`) scans only
`<data_root>/agents/`, populated exclusively by `ensure_starter_agents`
(the nine starter names) and whatever the user creates. Reference agents
are, by `reference_agents.py`'s own documented design, "never copied into
the user's writable `agents/` catalog and never discoverable via
`resolve_agent`/`discover_agents`." All three Category-D directories live
under separate `data/v3_*_agents/` paths, outside both
`data/reference_agents/` and the starter set, and are staged only by
explicit research-driver file copies — never by `ensure_starter_agents` or
any product code path. **No additional exclusion work was required**; the
existing directory convention already satisfies the governing task's
requirement.

## 17. Documentation changes

| file | change |
|---|---|
| `docs/V3_RULESET_RESEARCH_SUMMARY.md` | **new** — navigable phase index; discoverability was weak (nothing in README/ROADMAP/COMPATIBILITY pointed at the closeout before this phase), so a dedicated index was created rather than relying on `V3_RESEARCH_CLOSEOUT.md` alone, per the governing task's own "if discoverability is weak, create a concise permanent index" instruction |
| `docs/V3_PRODUCT_SCOPE.md` | **new** — v3.0 thesis, workstreams, non-goals, phase plan, compatibility contract, Ruleset-reopen gate, success criteria |
| `docs/V3_PHASE0_PRODUCT_SCOPE.md` | **new** — this report |
| `docs/ROADMAP.md` | added "v3 Ruleset Research — Closed" and "v3.0 — Product Development" sections, between the shipped `v2.0.0` entry and the pre-existing "After v1.0" section |
| `docs/FUTURE_PLANS.md` | added v3-closure notes to every relevant existing subsection (territory maintenance, advanced offense, arena/field-size, multiple execution processes, replication, specialized sub-agents, Agent API v2, future rulesets); added two new subsections, "Agent lifecycle: mutation, evolution, and replication economics" and "Execution-trace / intent semantics," covering the governing task's requested deferred-research items that had no prior home |
| `docs/COMPATIBILITY.md` | added one short forward-pointer section ("Bytefray v3.0 software version") rather than duplicating the existing, already-thorough independent-axes policy |

**No historical substantive research report was edited.** `V3_RESEARCH_CLOSEOUT.md` and every `V3_PHASE*.md` report are untouched by this phase — confirmed by `git diff` showing no changes to any file under that name.

## 18. Risks

* **Branch-base choice** (§3) carries the accumulated v3 research code
  into the product branch's ancestry rather than a clean `main` fork. Risk
  is mitigated by the independent behavior-preservation audit (§2) and by
  the Category-D discovery-isolation check (§16); the residual risk is
  purely one of tree size/surface area, not of behavior.
* **Category-C flags** (`--arena-size`/`--instr-per-tick`/`--kill-weight`)
  are live product CLI surface with research-report citations in their own
  help text today. Until Phase 4 resolves this, a product user reading
  `agents evaluate --help` sees research-motivated language. No behavior
  risk; a discoverability/clarity risk only.
* **No large-scale GUI regression run was performed in this phase** — Phase
  0 is documentation/audit-only per its own scope; the presentation/agent-
  creation/strategy-analysis findings in §§7–10 are static-analysis
  findings (file reading), not live-GUI-tested claims. Phase 1–4's own
  validation requirements (in `V3_PRODUCT_SCOPE.md`) call for live GUI
  walkthroughs before those findings become implementation decisions.

## 19. Validation

| check | result |
|---|---|
| `main`/`origin/main` in sync | confirmed, `1093393` on both |
| `v2.0.0` tag intact, ancestor of `main` | confirmed |
| No research branch merged into `main` | confirmed — `main` carries zero v3 commits |
| Pre-existing stash entries untouched | confirmed — three, all pre-dating this program |
| Frozen `v2-baseline` population | **16/16** focused tests pass, including live revision verification |
| `BYTEFRAY_RULESET_ID` / `AGENT_API_VERSION` unchanged | confirmed by direct grep on both branches |
| `engine/src` behavior-preservation | confirmed by independent line-by-line diff audit (§2) — no compatibility concern found |
| Research-agent discovery isolation | confirmed — no code change was needed; existing directory convention already isolates every Category-D artifact |
| Historical research reports unedited | confirmed — no `V3_PHASE*.md`/`V3_RESEARCH_CLOSEOUT.md` file was touched |
| Product docs (`ROADMAP`/`FUTURE_PLANS`/`COMPATIBILITY`) updated consistently | confirmed — cross-links resolve to files created or already present in this phase |
| No Ruleset/API/schema/scoring/scheduler/capture change | confirmed — no `engine/src` file was modified by this phase; only `docs/*.md` files were written |

This phase made **no production-code change**, so the full test
suite/Ruff/mypy gate the governing task requires only for code changes was
not re-run beyond the targeted benchmark-population verification above.

## 20. Phase 0 verdict

### **V3.0 PRODUCT SCOPE APPROVED — READY FOR PHASE 1**

## 21. Recommended Phase 1 objective

Not implemented here, per the governing task's instruction. Recommended
objective, drawn directly from §7's audit and
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) Phase 1: capture a baseline
screenshot/recording set across the Replay Viewer's HUD modes (default,
compact/5+-entrant, narrow-window) and Agent Designer's empty/ready/live
states — evidence that does not currently exist — then close the Replay
Viewer branding-parity gap against Agent Designer's existing identity
header. Both are low-effort, zero-Ruleset-risk, and establish the evidence
base every later presentation decision in this cycle should be measured
against.
