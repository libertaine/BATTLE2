# Bytefray v2.0.0-beta3 — Product Presentation & Workflow Plan

This is the working plan for `v2.0.0-beta3`, on
`v2.0-beta3-development`. The branch was created from `main` at
`c8d89d7e5859b7d7461afa71f8932bde34493643`, after the published
`v2.0.0-beta2` release. The Beta2 release branch and annotated tag both point
to `b580ad2de025443bcb3c55735bdc837fc668a825`.

**Release status: Phase 4 complete; Beta3 not released.** This document began
as the Phase-1 product audit and now records the completed Replay Viewer,
Agent Designer presentation, and multi-entrant product-integration phases. The
qualified Beta2 engine, evaluation methodology, artifacts, and user data remain
unchanged.

> Beta3 presents the qualified game and evaluation workflows more clearly.
> It does not redesign the game or its evidence model.

## 1. Mission and verified Beta2 baseline

Beta2 shipped Ruleset-v2 pairwise and multi-entrant evaluation, generic group
analysis, deep verification and comparison, self-play disclosure, and
deterministic resume across explicit v4/v5/v6 methodology identities. Those
capabilities are technically available, but the product surfaces do not yet
present them with equal clarity:

- the Replay Viewer is functionally strong and already separates its HUD from
  the arena, but the fixed bands and one-row entrant cards do not scale or
  resize as deliberately as the underlying N-entrant model;
- the Agent Designer opens as a conventional tabbed utility with a large blank
  output area and little first-launch guidance;
- Ruleset-v2 group evaluation is a CLI workflow. The Designer's evaluation
  dialog remains pairwise, and its history presentation uses pairwise labels
  even when reading group artifacts;
- packaging already carries useful Bytefray branding, but availability differs
  between source, wheel, standalone frozen GUI, and the unified frozen
  dispatcher.

Beta3 should therefore make a few conspicuous, durable presentation and
workflow improvements while consuming the existing authoritative replay and
evaluation models.

## 2. Product-presentation principles

1. **Preserve the battlefield.** Only information whose meaning depends on an
   arena position belongs over the arena.
2. **Make methodology visible before execution.** Ruleset, roster, layouts,
   seat coverage, seed coverage, and matrix size must be understandable before
   a potentially expensive evaluation starts.
3. **Use the product's vocabulary at the product boundary.** Stable persisted
   fields remain unchanged, while labels and explanations should use plain,
   context-appropriate language.
4. **Prefer responsive calculations over fixed screenshots.** Pure layout and
   presentation helpers should carry most acceptance coverage; display-backed
   tests remain small startup/interaction smokes.
5. **Use existing identity sparingly.** A restrained icon, title, hierarchy,
   and useful empty-state copy are sufficient. Branding must yield completely
   to live content.
6. **Remain readable without color.** Text labels, status words, shapes, and
   ordering remain authoritative; color is reinforcement.
7. **Do not create another truth layer.** UI models adapt canonical replay,
   result, and evaluation data. They do not reproduce Ruleset, winner, capture,
   identity, or comparison logic.

## 3. Audited current product state

### 3.1 Application and startup experience

Bytefray has two distinct GUI applications rather than a separate graphical
home/launcher: the PySide6 Agent Designer and the Pygame Replay Viewer. The
unified `bytefray` command dispatches to them through `bytefray design` and
`bytefray replay`; Windows also ships standalone executables.

The Agent Designer opens at 1000x720 with the native title
`Bytefray – Agent Designer`, a menu bar, and three top-level tabs: Simple,
Advanced, and Agent Development. Simple is the default. Its compact Quick
Match row sits above a large, read-only, initially blank text log. There is no
in-content hierarchy, welcome treatment, matchup summary, or prompt in that
space. Advanced opens four nested tabs; its Results view is likewise an empty
table and log until a run. Agent Development is better structured into named
groups and normally selects a starter Python agent, but its status areas remain
plain labels. The result is functional and keyboard-native, but the first
impression is generic and unfinished rather than intentionally sparse.

The standalone Replay Viewer is not a file-browsing application shell. It
requires a replay path; launching it without one produces argument help/error
rather than an open-file or welcome state. Once a replay is selected, the
Pygame window opens directly into playback. Adding a full library/home shell is
not necessary for Beta3; a small no-argument file-open path may be considered
only after the core presentation work if it remains low risk across source and
frozen builds.

### 3.2 Replay Viewer

The viewer is a standalone, resizable Pygame window. Tkinter is not involved.
`ReplaySession` owns reconstructed replay state,
`battle_client.analysis`/`replay_status` derive replay-domain facts, and
`PygameRenderer` presents them. This dependency direction is correct.

The proposed separation of non-spatial status from the battlefield is **already
implemented** by Beta1 Phase 4 in `battle_client.hud_layout` and
`PygameRenderer`:

- a top band contains two match/status header lines and one horizontal row of
  entrant cards;
- the arena occupies a separate middle rectangle;
- a bottom band contains playback status, event or selected-cell summary,
  keyboard help, and the territory history graph;
- ownership tint, recent-activity heat, write flashes, trails/markers,
  selected-cell highlight, and similar address-bound information remain over
  the arena.

No HUD panel currently covers the battlefield. Beta3 must refine this
architecture, not rebuild or reverse it.

Current strengths:

- the status loop and replay model are N-entrant rather than hard-coded to A/B;
- alive/dead/captured state, core state, score, territory, kills, winner, and
  termination are derived from authoritative replay status;
- keyboard playback, seek, speed, zoom/fit, trails, selection, and event seek
  are supported;
- the arena uses integer cell scaling and a preferred 960x600 viewport with a
  display-size cap;
- layout geometry, formatting, click mapping, and fake-drawing seams already
  have substantial non-display test coverage.

Current presentation limits:

- the top band is fixed at 100 pixels and gives every entrant one equal-width
  card in a single row. Two entrants read well; three and four progressively
  truncate; five or more also lose distinctive semantic colors after the four
  defined colors;
- resizing is nominally supported, but the resize handler snaps the actual
  window back to an arena-derived integer scale plus fixed bands. The user
  cannot retain an arbitrary wider aspect ratio for status space;
- card formatting drops detail and then truncates text instead of changing to
  a responsive card mode or grid;
- help is one long, always-visible line and is truncated on narrower windows;
- the fixed-width territory graph and its horizontal legend become crowded as
  entrant count increases;
- terminal state is a header line, not a clearly emphasized but non-blocking
  result state;
- the event/selection line only exposes one compact fact at a time.

### 3.3 Agent Designer and Ruleset-v2 integration

Simple and Advanced match setup still construct exactly two entrants through
`RunConfig.a_type`/`b_type`; neither exposes a Ruleset selector. The current
`Evaluate…` dialog exposes candidate, optional baseline, opponents, seeds,
ticks, pairwise entrant orientation, and output, but it does not expose
`--ruleset` or `--group`. Therefore the Designer cannot initiate the Beta2
group methodology.

The engine CLI does expose it truthfully: `--group` requires
`bytefray-rules-2`, fields the candidate and all opponents together as one
roster, enumerates standard layouts and seat assignments, rejects the
pairwise orientation flags, prints resolved matrix size before execution, and
uses entrant-symmetric group analysis. The mismatch is a product integration
gap, not an engine-model gap.

Evaluation History can discover the newer artifacts through the shared engine
adapter, but several Designer-only formatters remain pairwise: list rows say
`candidate=`, cell rows say `subject vs opponent` plus `orientation`, summary
text starts with candidate/opponents, and comparison UI says “per-opponent”.
For group/v6 artifacts those labels are confusing or semantically wrong even
though the underlying artifact is intact. Phase 4 must add group-aware
presentation branches; it must not reinterpret or rewrite stored fields.

### 3.4 CLI, help, and documentation

The CLI's group help and live output correctly distinguish a roster/seat-
assignment matrix from pairwise candidate/opponent orientation. It discloses
Ruleset, seeds, roster, layouts, seat assignments, cell count, fixed alignment,
and per-physical-instance self-play denominators. Evaluation-history CLI output
also has group-specific roster/layout/seat and analysis paths.

The main agent guide still introduces evaluation primarily as pairwise
candidate-versus-opponents work and says the Designer exposes the same options
as the CLI. That statement became incomplete after Beta2 because the Designer
does not expose Ruleset-v2 group mode. Beta2's dedicated methodology documents
are accurate, but the primary tutorial/README path should gain a short group
workflow and plain-language explanation in Phase 4.

### 3.5 Tests and test seams

The Replay Viewer has unusually good presentation seams already:

- `client/tests/test_hud_layout.py` covers pure sizing, formatting, card
  truncation, click regions, and 1–5 entrant layout cases;
- `client/tests/test_pygame_renderer.py` covers renderer helpers and drawing
  integration with fakes, without pixel-perfect screenshots;
- `client/tests/test_replay_status.py` covers N-entrant replay semantics;
- display-backed Linux tests exercise startup, a frame, and deterministic
  shutdown.

Missing coverage aligns with the presentation limits: responsive entrant-card
modes/grid decisions, 4+ entrant legibility rules, arbitrary resize retention,
compact help behavior, and emphasized end-state layout.

The Designer has extensive Qt-marked tests under `tests/` for lifecycle,
runtime labels, development workflows, evaluation/presets/history, packages,
and Linux startup. Headless service tests cover command construction. There is
no need for screenshot testing. New work should keep dialog decisions and text
adaptation in pure or GUI-independent helpers, with focused Qt tests for widget
state and accessibility labels.

## 4. Highest-value problems and priorities

| Improvement | User impact | Implementation risk | Architectural risk | Testing difficulty | Packaging impact | Beta3 necessity |
|---|---|---|---|---|---|---|
| Responsive Replay HUD/card layout for 2, 3, 4, and graceful 5+ entrants | HIGH | MEDIUM | LOW | LOW | LOW | HIGH |
| Preserve user-selected window aspect/size while fitting the arena | HIGH | MEDIUM | LOW | MEDIUM | LOW | HIGH |
| Compact discoverable help and stronger terminal-state presentation | MEDIUM | LOW | LOW | LOW | LOW | HIGH |
| Designer identity header and content-replacing empty state | HIGH | LOW | LOW | LOW | LOW if square icon is used | HIGH |
| Designer Ruleset-v2 group-evaluation configuration and matrix preview | HIGH | MEDIUM | LOW | MEDIUM | LOW | HIGH |
| Group-aware Designer history wording and rows | HIGH | MEDIUM | LOW | MEDIUM | LOW | HIGH |
| Primary-doc group tutorial and terminology cleanup | MEDIUM | LOW | LOW | LOW | NONE | HIGH |
| No-argument Replay Viewer file picker/home state | MEDIUM | MEDIUM | LOW | MEDIUM | MEDIUM | LOW |
| Designer direct Quick Match with 3+ entrants | MEDIUM | HIGH | MEDIUM | MEDIUM | LOW | LOW |
| New theme/design system, animations, or custom widget toolkit | LOW | HIGH | MEDIUM | HIGH | MEDIUM | NO |

The first six rows define Beta3. The no-argument viewer and direct N-entrant
Quick Match are optional only if the required phases finish with clear evidence
and without widening the architecture.

## 5. Replay Viewer target architecture (Phase 2 — complete)

Phase 2 implemented this architecture in the existing
`battle_client.hud_layout`/`PygameRenderer` seam. The resolved presentation
decisions are:

- **supported minimum:** 640x480; below-minimum OS sizes are still honored and
  render bounded/clipped rather than snapping, overlapping, or crashing;
- **HUD allocation:** at most 35% of window height and, at supported sizes,
  additionally bounded to preserve a 256-pixel useful arena viewport;
- **entrant layout:** two entrants use one detailed row; three/four use a
  detailed row when wide and a balanced two-row grid at minimum width;
  five-plus use a two-line compact multi-column roster whose columns increase
  when necessary to stay within the HUD cap;
- **non-color identity:** every card carries a recorded-order badge (`#1`,
  `#2`, …) beside the real agent id/name, so fifth and later entrants do not
  depend on the four-color palette;
- **resize:** ordinary resize preserves the requested outer dimensions,
  derives the remaining viewport, and centers the largest fitting integer-
  scaled arena; deliberate zoom/fit commands retain their window-sizing role;
- **help/end state:** compact help fits the normal footer and `?` temporarily
  replaces footer detail/graph with the full controls; authoritative terminal
  results receive a high-contrast `MATCH COMPLETE` winner/draw line without a
  modal or winner recomputation.

### 5.1 Structure

Retain the existing three-region Pygame renderer:

1. **Match band:** compact match identity/methodology and responsive entrant
   status collection.
2. **Arena viewport:** the largest possible fitted arena, free of non-spatial
   UI.
3. **Playback band:** timeline/tick/play state/speed, current event or selected
   cell, territory trend, and a short help affordance.

No Qt/Tkinter embedding, scene graph, or second playback controller is needed.
`ReplaySession`, analysis, and replay status remain authoritative.

### 5.2 Spatial versus non-spatial information

Keep on the arena only:

- ownership coloration/tint tied to cells;
- address-bound recent activity and write flashes;
- agent/core markers and trails tied to positions;
- selected-cell outline and other direct spatial selection feedback.

Keep in the bands:

- entrant name and stable text identifier;
- alive/dead/captured state;
- core summary, score, territory, kills;
- Ruleset/runtime/arena/entrant-count context;
- tick, playback state, speed, event summary, selected-cell details;
- winner and termination;
- territory history and general instructions.

### 5.3 Responsive entrant behavior

Extend the pure layout seam with an explicit detailed/compact card decision and
card grid:

- two entrants: detailed cards in one row;
- three entrants: one row when each card meets the detailed minimum width,
  otherwise a two-row grid;
- four entrants: one row only on sufficiently wide windows, otherwise a 2x2
  grid;
- five or more: a compact multi-column roster grid with name, text status,
  core, and score always retained; territory/kills become secondary detail;
- the number of columns is calculated from available width and a tested minimum
  card width, not hard-coded per window size;
- top-band height is derived from row count and card mode, subject to a tested
  maximum share of the usable display. If all facts cannot fit, secondary
  facts yield before identity or status; cards never silently disappear.

The existing four semantic colors remain useful, but 5+ entrants require a
deterministic marker/pattern or short text token in addition to color. Stable
text identity remains the primary distinction.

### 5.4 Resize, help, and end state

Window size and layout size must be distinct. A resize should preserve the
requested window dimensions within display/minimum constraints, compute the
band layout, and fit the arena into the remaining viewport at integer scale.
Zoom commands may deliberately change scale/window behavior; ordinary resize
must not snap back to a different aspect without explanation.

Replace the always-truncated shortcut sentence with a short visible hint such
as `Space play/pause · ? controls`; `?` opens a help panel in the playback band
or temporarily replaces nonessential footer content, not the arena. Existing
shortcuts remain supported.

At a terminal tick, promote winner/tie and termination into a high-contrast
header state while leaving the arena visible and seek controls active. Do not
use a modal or full-screen celebration.

### 5.5 Phase-2 acceptance

- deterministic layout tests cover representative wide/narrow windows with
  2, 3, 4, and at least 5 entrants;
- every entrant retains visible identity and text status;
- non-spatial content never intersects the arena rectangle;
- ordinary resize preserves the requested aspect/usable size and always fits
  the arena;
- help and terminal presentation are readable at the minimum supported window;
- existing replay seek, selection, spatial overlays, Ruleset-v1/v2 status, and
  headless operation remain unchanged;
- focused client tests, Ruff, client mypy, and the available host GUI smoke
  pass; Linux/Xvfb remains an environment-specific Phase-5 gate when Linux is
  available.

Phase-2 qualification passed 187 focused HUD/renderer/playback tests, 292
client tests, and the canonical full suite (1,897 passed, 14 skipped, 2
deselected). Repository-wide Ruff, engine/client mypy, and two display-backed
Pygame smokes passed on Windows. Linux/Xvfb and frozen/installer qualification
remain Phase-5 environment gates; no Linux result is inferred from Windows.

## 6. Agent Designer polish direction (Phase 3 — complete)

The smallest useful first-launch improvement is a restrained application
identity plus a real empty state, not a background watermark.

Immediately after launch, the Simple tab should show:

- a slim content header with the existing Bytefray square icon, “Agent
  Designer”, and one short purpose line;
- the existing Quick Match controls with clearer spacing and one visually
  primary Run action (while preserving tab order and native controls);
- in place of the blank log, an empty-state panel containing the icon at a
  modest size, `Ready to run a match`, a readable selected-matchup summary,
  and `Choose two compatible agents, then Run Match`;
- on the first real log line, the empty-state panel is replaced by the plain
  text log. The image is never behind live text and is not repeated in every
  nested tab.

The existing square icon is preferred because it is already the approved,
package-local runtime asset. The horizontal wordmark is not needed for this
change. Advanced Results may reuse the same empty/content state pattern with
context-specific copy, but the phase should not restyle every dialog or create
a design system.

Phase-3 acceptance:

- source, wheel, standalone frozen Designer, and unified `bytefray design`
  show the intended icon or degrade silently to text;
- initial purpose, current selection, and next action are understandable
  without running a match;
- live logs remain unobstructed, selectable, and high contrast;
- native keyboard navigation and existing lifecycle behavior remain intact;
- empty/content transition logic has focused helper/Qt coverage and GUI startup
  smokes pass.

Phase 3 retained the native tabbed shell and resolved the presentation as
follows:

- one compact header above the existing tabs uses the approved square icon via
  `get_branding_icon_path`, with real text remaining complete when the optional
  image cannot be loaded;
- Quick Match uses a labeled configuration grid and separate action row, with
  the unchanged `Run Match` action given restrained local emphasis;
- the Simple output area is a `QStackedWidget`-based ready/live view. Its ready
  copy is actual accessible UI text and never enters the `QPlainTextEdit`; the
  first meaningful `appendLog` call selects the genuine log page;
- the matchup summary uses the combo boxes' existing disambiguated presentation
  labels while selection and command construction remain authoritative by
  discovery id under `Qt.UserRole`; duplicate names and self-match therefore
  remain truthful;
- no user-facing Clear action was invented. The presentation seam exposes an
  explicit clear transition that restores the current ready state for callers,
  and focused tests cover ready -> selection -> live -> clear -> ready -> live.

Qualification passed 7 new presentation tests, 184 broader Qt tests, the
display-backed startup smoke, two real Designer match runs, and the canonical
headless suite (1,897 passed, 14 skipped, 2 deselected). Repository-wide Ruff,
engine/client mypy, resource-path tests, and diff checks passed on Windows. The
standalone/unified frozen builds, installer, wheel execution, and Linux/Xvfb
remain Phase-5 integrated environment gates; Phase 3 changed no resource helper,
asset, PyInstaller spec, installer, or package-data rule.

## 7. Multi-entrant product integration and wording (Phase 4)

### 7.1 Designer workflow

Add an explicit evaluation mode to `Evaluate…`:

- **Pairwise evaluation:** retain Candidate, optional Baseline, Opponents, and
  entrant-orientation controls;
- **Group evaluation (Ruleset v2):** label the persisted candidate role as
  **Focus agent**, label the combined selection **Roster**, explain that all
  selected entrants compete together, require at least three entrants, hide or
  disable Baseline with the existing engine reason, and replace orientation
  controls with the standard **seat assignments** explanation;
- expose Ruleset selection explicitly, selecting group mode resolves Ruleset 2
  and never silently falls back to pairwise;
- show a read-only matrix preview: entrants, standard layouts, seat
  assignments, seeds, and total matches. The preview should reuse exported
  engine planning facts or a shared read-only adapter, not reimplement
  factorial scheduling in Qt;
- build the existing canonical CLI request and let engine validation remain the
  final authority.

Do not expand Quick Match to arbitrary N as part of this required slice.
Simple may remain deliberately 1v1; Ruleset labeling can be added where needed
without pretending it is group evaluation.

### 7.2 Group-aware results and history

Branch presentation on the adapted artifact's recorded group/methodology fact:

- pairwise rows remain `Candidate`, `Opponent`, and `orientation`;
- group summaries use `Focus agent`, `Roster`, `Layout`, `Seat assignment`,
  `Winner/survivors`, and `physical entrant instances` where self-play makes
  the denominator important;
- a group cell must not be rendered as `subject vs opponent` or with the
  pairwise orientation sentinel;
- group comparison views should say `roster/layout/seat conditions` rather
  than `per-opponent`; unavailable or unsafe pairwise drill-down actions stay
  disabled with an explanation;
- persisted names such as `candidate_id`, `opponent_ids`, and legacy sentinels
  remain byte-for-byte unchanged.

### 7.3 Documentation

Add one primary-path example to README/Agent Lab showing:

```text
bytefray agents evaluate focus_agent --ruleset bytefray-rules-2 --group \
    --opponents roster_agent_b,roster_agent_c --seeds 1,2,3
```

Explain in plain language that all three entrants share each match, seat
assignments generalize pairwise order, standard layouts vary placement, matrix
growth is factorial, and self-play rates use physical entrant instances. Fix
the current claim that the Designer exposes all CLI evaluation options only
when the group workflow actually ships.

Phase-4 acceptance:

- a user can configure, preview, launch, resume, and inspect a Ruleset-v2 group
  evaluation from the Designer without manually translating pairwise terms;
- the emitted request is equivalent to the documented CLI request;
- N=3 and N=4 group artifacts render with group-aware history/results wording;
- self-play denominators are explicit and no logical outcome is invented;
- pairwise v4/v5 and group v6 artifacts remain readable and unchanged;
- focused service, Qt, engine presentation, and documentation tests pass.

Phase-4 source qualification passed 7 new canonical planner/execution tests,
5 new display-backed integration tests, the 191-test Qt corpus (the literal
`python3` Windows lifecycle case run separately from the 190-test batch), and
the canonical 1,904-test headless suite with 14 expected skips and 2 expected
deselections. Repository-wide Ruff and the required engine/client mypy checks
also passed. Wheel, frozen, portable, installer, and Linux/Xvfb qualification
remain Phase-5 gates as planned.

## 8. Packaging and resource decisions

Existing committed assets are:

- `assets/branding/bytefray-brand-sheet.png` — approved master sheet;
- `assets/branding/bytefray-icon.png` and `.ico` — generated application mark;
- `assets/branding/bytefray-logo-horizontal.png` — generated lockup;
- `app/assets/branding/bytefray-icon.png` — byte-identical wheel package-data
  copy.

The generation script documents the master/crop process and uses no external
runtime dependency. No separate third-party branding license or attribution is
present; these are repository-owned product assets governed with the project.

Source lookup prefers root `assets/branding`, then package-local
`app/assets/branding`. Setuptools includes `app/assets/**/*`, so the square icon
works from a wheel. The standalone Agent Designer and Replay Viewer PyInstaller
specs collect the root `assets` directory; the installer and standalone EXEs
also use the `.ico`. Portable ZIPs inherit those frozen trees.

Two concrete gaps must be handled deliberately:

1. the horizontal logo has no package-local copy, so a wheel-installed GUI
   cannot rely on it without extending the generation sync/package data;
2. the unified `tools/bytefray.spec` collects application modules but not the
   root branding directory, so `bytefray.exe design` can silently lack runtime
   branding even though the standalone Designer has it.

Phase 3 should use the existing square icon, add the branding directory to the
unified frozen data only if required, and extend frozen/wheel resource checks.
No new asset is needed for Beta3's required work. Any future asset must be
package-local or explicitly collected, resolved through the existing resource
helper, and tested in source, wheel, standalone frozen, portable, and installer
layouts.

## 9. Beta3 phase sequence

### Phase 1 — Product Presentation Audit & Beta3 Design

**Deliverable:** this audited, prioritized implementation plan and concise
roadmap update. **Acceptance:** real code/resources/tests inspected; decisions
answer the ten required design questions; Beta2 architecture untouched; docs
validate and commit on the Beta3 branch.

### Phase 2 — Replay Viewer HUD & Arena Presentation

**Status: complete. Deliverable:** responsive bands/cards, viewport-preserving
resize behavior, compact/expanded help, and terminal-state emphasis on the
existing renderer architecture. **Acceptance:** the Phase-2 criteria in §5.5
passed; Linux/Xvfb and final frozen packaging remain Phase-5 gates.

### Phase 3 — Agent Designer / Application Visual Polish

**Status: complete. Deliverable:** intentional first-launch hierarchy and
content-replacing empty states using existing branding. **Acceptance:** the
Phase-3 criteria in §6 passed in source/host qualification; canonical wheel,
frozen, installer, and Linux/Xvfb execution remain Phase-5 integrated gates.

### Phase 4 — Multi-Entrant Product Integration & Documentation

**Status: complete. Deliverable:** group-evaluation configuration/preview and group-aware
results/history/tutorial language. **Acceptance:** the Phase-4 criteria in
§7.3 are implemented together through the canonical planner, schema-v6 history
adapter, and capability-gated drill-down actions. Phase 5 owns integrated
packaging/environment qualification.

### Phase 5 — Integrated Beta3 Qualification & Release Decision

**Deliverable:** no new feature design; qualify source, isolated wheel, Windows
frozen/portable/installer GUI workflows, Replay Viewer 2/3/4+ entrant cases,
Designer empty/content lifecycle, pairwise and group evaluation/history, and
historical artifacts. Decide release readiness from evidence. Tagging,
publication, and release actions require a separate explicit authorization.

This five-phase sequence is proportionate; no additional phase is justified by
the current architecture.

## 10. Explicit non-goals and frozen boundaries

Beta3 does not change:

- Ruleset-v1 or Ruleset-v2 simulation semantics;
- scheduler behavior/order, action quotas, scoring, winner resolution, or core
  capture;
- strategic starter-agent behavior;
- Agent API v1;
- result/replay/evaluation artifact shapes;
- evaluation v4/v5/v6 identity, resume identity, group layouts, exhaustive seat
  permutations, comparison semantics, or self-play persistence semantics;
- the canonical replay-session/client dependency direction;
- historical Beta2 documents, branches, tags, or release artifacts.

Known Beta2 limitations—including opponent-order-sensitive group identity,
factorial scaling, withheld ambiguous capture timing, first-occurrence
self-play candidate outcomes, legacy group identity sentinels, large-N
sampling, and identity-payload centralization—remain deferred. Presentation
must disclose relevant limitations, not “fix” them through schema or identity
churn.

Also out of scope: a graphical launcher/library, a Pygame-to-Qt rewrite, a
custom theme framework, animated decoration, persistent watermark, full
accessibility redesign, direct N-entrant Quick Match, new gameplay telemetry,
and screenshot/pixel-perfect test infrastructure.

## 11. Risks and deferred decisions

- **Very small windows / large N:** dynamic HUD height can starve the arena.
  Define and test minimum dimensions plus compact-mode degradation before
  coding; never hide entrants silently.
- **Color exhaustion:** extending the palette alone will not solve 5+ entrant
  identification. Pair color with text tokens or deterministic marker shapes.
- **Resize compatibility:** existing zoom and fit shortcuts intentionally
  control integer scale. Separate their behavior from ordinary OS resize in
  tests before changing either.
- **Group history actions:** pairwise replay/Agent Lab drill-down assumes a
  subject/opponent coordinate. Disable unsafe actions until a real group-cell
  coordinate adapter exists; do not guess a seat.
- **Matrix size:** group preview must warn before execution but must derive its
  count from the engine planner. It must not become a second scheduler.
- **Unified frozen GUI resources:** the dispatcher packaging gap should be
  corrected and smoke-tested in Phase 3 if the identity header depends on it.
- **No-argument Replay Viewer:** a file picker could improve desktop launch but
  introduces toolkit/platform/frozen behavior. Reassess after Phase 2; it is
  not required for Beta3.

## 12. Phase-1 implementation decision

Phase 1 is documentation-only. The repository already has the pure Replay HUD
layout seam that a bounded foundation change might otherwise have introduced,
and the remaining work requires phase-specific acceptance tests and visual
decisions. Production changes here would provide little additional evidence
and would blur the Phase-2/Phase-3 boundaries.
