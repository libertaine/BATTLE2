# Bytefray v3.0 Phase 2 — Agent Creation & Iteration Workflow

Branch: `v3.0-development`. Status: complete, not merged, not tagged, not
published.

## Scope

Set by explicit user direction narrowing `V3_PRODUCT_SCOPE.md`'s broader
Phase 2 objective to the highest-value Phase 0 findings, rather than
"improve Agent Designer" generally:

> Reduce the distance from opening Agent Designer to creating, modifying,
> running, and re-running a working agent, while preserving provenance and
> deterministic execution.

Six priorities, in the order given, each addressed below: (1) a
starter-based scaffold, (2) a Development-tab reload/refresh affordance,
(3) actionable error/validation feedback, (4) preserved Simple/Advanced/
Agent Development tab separation, (5) an audit of the broad panel-init
exception handling, (6) before/after workflow evidence.

**Explicitly out of scope, by the same direction**: strategy-analysis
presentation (evaluation-result interpretation) — that is Phase 3's
objective, not this one's, even where it would have been tempting to touch
while already inside `app/views/`.

No Ruleset, Agent API, scoring, scheduler, capture, or reference-agent
behavior was touched. No agent-revision/provenance behavior changed —
confirmed directly (§2): scaffolding creates no revision record regardless
of which template is chosen, exactly as before this phase.

---

## 1. Starter-based scaffold

**What the investigation found first.** A literal "copy an existing
starter's source" option was considered and rejected on evidence, not
preference: `docs/specs/agent_scaffold.md` §8/§13 already record that the
scaffold's original blank template was deliberately *not* an adaptation of
a starter, because starter files carry identity that would misrepresent a
newly scaffolded agent if copied verbatim — `agents/claimer/agent.yaml`
has literal `"name": "claimer"`/`"display": "Claimer (Starter)"` fields,
and `claimer/agent.py`'s docstring cross-references sibling starters by
name ("see Strider", "see Claimer's docstring"). Copying that content into
a differently-named agent would read as documentation about a different,
specific bundled agent, not as a generic starting point.

**What was built instead.** A second, self-contained template —
`--template annotated` (CLI) / "Annotated Example" (Designer) — alongside
the original `--template blank` (now the explicit default, byte-identical
to omitting the flag entirely). It lives in its own resource directory
(`engine/src/battle_engine/data/agent_template_annotated/`), is not a copy
or adaptation of any starter, and demonstrates the concepts a first
strategy usually needs — reading before writing, arena-address wraparound,
and the once-per-tick action budget — as inline comments at exactly the
point in the code where each concept matters. It was verified to actually
run: `bytefray agents validate`/`agents test` both pass against it,
including a real completed match against the internal reference opponent.

`battle_engine.agent_scaffold.create_agent(agent_id, *, ..., template=
"blank")` gained the one new keyword argument; every caller that omits it
gets exactly the prior behavior (proven by a byte-for-byte content test,
§7). `NewAgentDialog` gained a "Starting point" combo box, defaulting to
Blank, calling the identical `create_agent` function the CLI uses — no
duplicated scaffold logic in the GUI, matching the existing pattern the
Phase 4a spec established for this dialog.

## 2. Development-tab reload/refresh affordance

**What the investigation found first, and why it changed the fix.**
Validate and Test were never actually stale: both already launch a fresh
out-of-process CLI run that reads whatever is on disk at that moment,
independent of anything cached in the GUI. Only the **read-only source
preview** (`agent.py`/`agent.yaml` panes) could go stale after an external
edit, because it was loaded exactly once, on agent selection, with no
other trigger anywhere in the Designer (confirmed by grep: no
`QFileSystemWatcher`, no mtime check, no reload path existed before this
phase). So the real problem was never "Validate/Test act on stale code" —
it was "the Designer's own display of that code can silently disagree with
what Validate/Test just used," which is confusing in a different way:
it can make a correct validation/test result look like it ran against the
wrong file.

**Fix.** `AgentDevelopmentPanel.reloadSource()` re-reads both preview panes
from disk, extracted from the code `_on_combo_changed` already had. Three
places now call it:
* a new **Reload** button next to the source panes, for reviewing without
  running anything;
* **Validate** and **Test**, automatically, immediately before emitting
  their run signal — so the preview a user sees is always exactly what is
  about to be validated/tested, with no combo-box reselect needed as a
  workaround;
* `invalidateAgentState()` — the panel's existing "source changed
  elsewhere" hook (previously wired only to Evaluation History's Restore
  Files action) — which cleared stale validation/test *results* already,
  but, discovered in the same investigation, never refreshed the preview
  panes either. That gap is now closed too, as a direct consequence of
  reusing the same method rather than a separate fix.

## 3. Actionable error/validation feedback

**What the investigation found first.** A live test against deliberately
broken agents (a `SyntaxError` and a `RuntimeError` raised from `act()`)
showed the diagnostic text itself is already substantive — file path,
exception type, message, and line number for a syntax error
(`SyntaxError: expected ':' (agent.py, line 8)`). The gap was not
diagnostic *content*; it was that `statusLabel`/`testStatusLabel`
(Development tab) and `errorLabel` (New Agent dialog) are plain `QLabel`s
with no text-interaction flags set anywhere in the Designer (confirmed by
grep: zero matches for `TextInteractionFlag` in `app/`), so a user could
read a long error but never select or copy it — to paste into an editor's
"go to line", search it, or attach it to a bug report.

**Fix.** `Qt.TextInteractionFlag.TextSelectableByMouse |
TextSelectableByKeyboard` added to all three labels. No content, layout,
or color-coding change — the existing Stage/Code/Error/Detail structure
already carries the useful information; it just could not be copied out.

## 4. Tab separation preserved

Simple, Advanced, and Agent Development remain three independent tabs and
panel classes. Nothing in this phase merges, hides, or cross-links them —
the New Agent dialog and the reload/validate/test changes are entirely
internal to `AgentDevelopmentPanel`.

## 5. Panel-initialization exception audit

Investigated as directed, with `git log`/`git blame` evidence rather than
inference: the three `try/except Exception: QMessageBox...` blocks
wrapping Simple/Advanced/Agent Development panel construction in
`app/agent_designer.py` were **not** introduced to fix a documented crash.
The Simple/Advanced pair originated in commit `a942bae` (a full rewrite of
`agent_designer.py`) with an inline comment stating the rationale directly
at authorship time: *"Don't crash the whole app; show Simple tab and
inform the user."* The Agent Development block was added later in commit
`7b8d98f`, extending the same established pattern for consistency, again
with no bug-fix rationale in its commit message.

**Conclusion: legitimate defensive design, not a masked historical bug —
no change made.** Recorded here rather than silently closed, per this
project's own discipline of reporting a null finding as a complete result
rather than needing to justify a change to make the audit "worth doing."

## 6. Before/after evidence

Captured against the real running Agent Designer (native Qt platform, not
the `offscreen` plugin — Phase 1 already found `offscreen` renders
unreadable tofu-box text on this environment), driving genuine widget
clicks and a real `QProcess` validate run, under
`docs/screenshots/v3-phase2-baseline/`:

| file | shows |
|---|---|
| `new-agent-dialog-blank.png` | New Agent dialog, default "Blank" starting point |
| `new-agent-dialog-annotated.png` | Same dialog, "Annotated Example" selected |
| `development-tab-annotated-source.png` | The newly created annotated agent's commented source, and the new Reload button in place |
| `development-tab-before-reload.png` | After an external edit (a prepended marker line), before clicking Reload — the stale preview |
| `development-tab-after-reload.png` | The same state immediately after clicking Reload — the edit now visible |
| `development-tab-validation-failed.png` | A real validation failure (deliberate `SyntaxError`), full Stage/Code/Error/Detail text, reachable by clicking Validate alone (no manual reselect) because Validate now reloads first |

## Files changed

| file | change |
|---|---|
| `engine/src/battle_engine/agent_scaffold.py` | `template` parameter on `create_agent`/`template_resource_dir`; `TEMPLATE_DIRECTORIES`/`DEFAULT_TEMPLATE`/`validate_template`; `--template` CLI flag |
| `engine/src/battle_engine/data/agent_template_annotated/{agent.py,agent.yaml}` | **new** — the annotated template's own resource files |
| `app/views/development.py` | `NewAgentDialog` template combo; `AgentDevelopmentPanel.reloadSource()` + `btnReloadSource`; auto-reload wired into Validate/Test/`invalidateAgentState`; selectable-text flags on status/error labels |
| `docs/AGENT_AUTHORING.md` | documents `--template`, the Designer's Starting point picker, Reload, and selectable status text; corrects the now-stale "no template selection" line |
| `engine/tests/test_agent_scaffold.py` | **+8 tests** — template default/selection/validation, CLI flag, unknown-template rejection |
| `tests/test_agent_development_panel.py` | **+8 tests** — template picker defaults/selection, selectable labels, reload via button/Validate/Test/`invalidateAgentState` |
| `docs/screenshots/v3-phase2-baseline/*.png` | **new** — the six images in §6 |
| `docs/V3_PHASE2_AGENT_CREATION_WORKFLOW.md` | **new** — this report |

## Validation

| check | result |
|---|---|
| Default suite (`python -m pytest`, `testpaths` scope) | exit 0 |
| Root `tests/` directory, gui + non-gui (excluded from `testpaths`/default `addopts` — run explicitly) | exit 0, 1 pre-existing environmental skip (symlink creation, unrelated) |
| `engine/tests/test_agent_scaffold.py` | 41/41 passed (33 pre-existing + 8 new) |
| `tests/test_agent_development_panel.py` | 19/19 passed (11 pre-existing + 8 new) |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success, 84 source files |
| `mypy client/src/battle_client` | Success, 12 source files (unaffected by this phase; re-run for completeness) |
| `app/` (Designer/Qt) mypy | not part of this project's mypy gate — `pyproject.toml`'s `[tool.mypy] mypy_path` and CONTRIBUTING.md's canonical commands cover only `engine/src/battle_engine` and `client/src/battle_client`; confirmed pre-existing PySide6-stub-related errors exist there independent of this phase's changes |
| Annotated template runs for real | `agents validate`/`agents test` both pass; a real match against the reference opponent completes to the tick limit |
| Scaffolding creates no revision | confirmed by inspection — `agent_scaffold.py`/`agent_revisions.py` remain uncoupled; a revision still comes into existence only at first evaluation/packaging, regardless of `template` |
| Screenshots reflect real driven interaction | yes — a genuine `QProcess` validate run, real button clicks, real file edits between clicks |

## Phase 2 verdict

### **AGENT CREATION WORKFLOW IMPROVED — SCOPE HELD TO THE SIX STATED PRIORITIES**

All six priorities addressed: two implemented (scaffold template choice,
reload affordance), one implemented narrowly (selectable status text,
scoped to what the evidence showed was actually missing), one audited with
a documented null result (panel-init exceptions), one preserved by
construction (tab separation), and one delivered as real, driven evidence
(before/after screenshots). Strategy-analysis presentation was not
touched, per explicit direction, despite living in the same `app/views/`
area.

Nothing merged, tagged, or published.
