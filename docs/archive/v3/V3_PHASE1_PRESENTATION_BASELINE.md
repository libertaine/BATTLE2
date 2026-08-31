# Bytefray v3.0 Phase 1 — Presentation Baseline & Branding Parity

Branch: `v3.0-development`. Status: complete, not merged, not tagged, not
published.

This phase executes the objective `V3_PHASE0_PRODUCT_SCOPE.md` §21
recommended: capture baseline visual evidence that did not previously
exist for the Replay Viewer's and Agent Designer's actual runtime states,
then close the Replay Viewer branding-parity gap the Phase 0 audit found
(Agent Designer has an identity header; the Replay Viewer had none). Both
are the two lowest-risk, zero-Ruleset-impact items from
`V3_PRODUCT_SCOPE.md`'s Phase 1 scope. The social-preview asset and the
Agent Designer panel-init exception-pattern audit — also named there —
are not addressed by this increment; see §6.

No Ruleset, Agent API, scoring, scheduler, capture, or reference-agent
behavior was touched. The only production code changed is presentation-
layer: one new decorative icon in the Pygame Replay Viewer's header band.

---

## 1. Method

Per this project's GUI-testing requirement, both apps were actually
launched and driven — not inferred from reading source, and not stubbed.

**Replay Viewer (Pygame).** Real replays were generated through the
production `NativeMatchService` boundary
(`battle_engine.agent_test.test_agents`, the same N-entrant path
Group Evaluation and the v3 research corpora both used), for 2, 3, and 5
Python starter entrants under `bytefray-rules-2` at the shipped default
(`arena_size=4096`, `ticks=400`). `PygameRenderer._redraw()` — the same
method the interactive viewer calls every frame — was then called directly
against those replays under `SDL_VIDEODRIVER=dummy`/`SDL_AUDIODRIVER=dummy`
and saved via `pygame.image.save()`. This driver pattern has direct
precedent in this repository: `docs/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md`
§ used the identical dummy-driver approach for visual QA.

**Agent Designer (PySide6).** The real `AgentDesigner` main window was
constructed and shown under the native Windows Qt platform (not the
`offscreen` platform plugin — an offscreen-platform attempt produced tofu
boxes instead of legible text on this environment, a font-rasterization
gap in that backend rather than anything about the app; the native
platform, available because this is a real Windows desktop rather than
headless CI, rendered correctly). A real Quick Match (Claimer vs. Hunter)
was launched by calling `btnRun.click()` — the exact signal a user's click
would emit — driving the genuine `QProcess` match-run path to completion,
polled via `QApplication.processEvents()`. Both the pre-run "ready" state
and the post-run log/result state were captured via `QWidget.grab()`.

Neither driver script is a product artifact; both were disposable,
run from a scratch directory outside the repository.

## 2. Baseline evidence captured

Six real, working captures, placed under
`docs/screenshots/v3-phase1-baseline/` — evidence that did not exist
before this phase:

| file | shows |
|---|---|
| `replay-viewer-2entrant-default.png` | Detailed (3-line) card mode, 2 entrants, default 640×672 window |
| `replay-viewer-2entrant-narrow.png` | The same match at the supported minimum window size (640×480) |
| `replay-viewer-3entrant-final.png` | Terminal state (`Tick 400/400 [PAUSED (end)]`), 3 entrants, territory-history graph populated |
| `replay-viewer-5entrant-compact.png` | Compact (2-line) card mode's 5-entrant, 3-column reflow |
| `agent-designer-ready.png` | The genuine empty/ready state (icon, "Ready to run a match", live matchup summary) |
| `agent-designer-live.png` | The genuine post-run log/result state from a real completed match |

All six confirm the HUD-separation and responsive-layout work the
README/CHANGELOG describe is real and working as documented — this was
previously undemonstrated by any committed evidence (Phase 0 §7).

## 3. Branding-parity fix

**Problem** (Phase 0 §7, finding 1): Agent Designer has a
`DesignerIdentityHeader` (icon + "Bytefray Agent Designer" + purpose line);
the Replay Viewer's top HUD band was pure text with no icon.

**Fix**: `client/src/battle_client/renderers/pygame_renderer.py` now loads
the shared branding icon (`battle_engine.paths.get_branding_icon_path()` —
the same asset and helper the Designer, and the Viewer's own taskbar/window
icon, already use) once per window configuration, scales it to 24×24, and
draws it at the left edge of the header band, vertically centered across
the band's two text lines. The header text's start x-offset and character
budget both shrink to make room, so nothing overlaps at any supported
window width (verified down to the 640px minimum, §2).

**Degrades exactly like the Designer's own pattern.** If the branding
asset is missing, or the load fails for any reason, `_load_header_icon`
returns `None` and the header renders exactly as it did before this phase
— icon-free text, unchanged position. This is verified, not merely
asserted: it is exactly what let a pre-existing test's incomplete `pygame`
module stub keep passing unmodified (§4).

No `hud_layout.py` geometry changed — that module's pure, pygame-free
band/rect calculations (and its own test suite) are untouched. The icon is
drawn entirely inside `pygame_renderer.py`'s existing drawing code, which
is where this project's own architectural rule
(`docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md`) places all presentation work.

## 4. Validation

| check | result |
|---|---|
| `client/tests/test_pygame_renderer.py` + `test_hud_layout.py` | 146 passed |
| Full `client/` suite | 292 passed |
| `ruff check client/src/battle_client/renderers/pygame_renderer.py` | All checks passed |
| `mypy client/src/battle_client` | Success, 12 source files |
| Real-render re-verification | All 4 Replay Viewer baseline images re-captured after the fix and re-inspected; icon renders correctly and text does not overlap at every captured window size, including the 640×480 minimum |
| Existing test compatibility | One pre-existing test's `pygame` stub lacked `transform`/`convert_alpha`; fixed by making icon loading tolerant of any failure (a purely decorative asset), not by editing the test |
| Ruleset/Agent API/scoring/scheduler/capture | untouched — confirmed no file outside `client/src/battle_client/renderers/pygame_renderer.py` and `docs/` changed |

## 5. Files changed

| file | change |
|---|---|
| `client/src/battle_client/renderers/pygame_renderer.py` | header-band branding icon: two new constants, `self._header_icon` state, `_load_header_icon()`, `_draw_top_band()` updated to draw it and reserve its width |
| `docs/screenshots/replay-viewer.png` | recaptured — the prior image predated this phase's icon addition and was stale, per this project's own precedent of recapturing an affected README screenshot when the source UI changes |
| `docs/screenshots/v3-phase1-baseline/*.png` | **new** — the six baseline images in §2 |
| `docs/V3_PHASE1_PRESENTATION_BASELINE.md` | **new** — this report |

## 6. Deferred, not addressed by this increment

Named in `V3_PRODUCT_SCOPE.md`'s fuller Phase 1 scope but not attempted
here, so a future increment (or this cycle's own continuation) has a clear
starting point:

* The long-deferred GitHub social-preview asset (`docs/ROADMAP.md`'s
  branding-gate section) — still unresolved.
* The audit of Agent Designer's broad `except Exception` panel-
  initialization pattern (three core tabs) — not investigated in this
  increment; the baseline screenshots in §2 did not exercise a
  panel-initialization failure path.

## 7. Phase 1 verdict

### **PRESENTATION BASELINE ESTABLISHED — BRANDING PARITY CLOSED**

Both HUD-mode/state evidence and Replay Viewer branding parity are done,
verified against the real running applications, and validated by this
project's existing test/Ruff/mypy gates with zero regressions. The
deferred items in §6 remain open Phase 1 candidates.

Nothing merged, tagged, or published.
