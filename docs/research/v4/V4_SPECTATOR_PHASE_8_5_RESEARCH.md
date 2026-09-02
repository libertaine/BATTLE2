# Bytefray v4 Spectator Research Phase 8.5 — Perspective HUD Coherence and Alpha Release Gate

## Verdict

**PASS.**

Phase 8 closed with one disclosed, pre-existing inconsistency (§11.1/§28.1 of
its own research document): in Perspective mode the arena, Director pacing,
and Fight Night ribbon all respect the selected entrant's knowledge
boundary, but the persistent top-band entrant cards kept showing every
entrant's canonical core, territory, score and kills unchanged — a leak
inherited from Phase 5/6, never introduced or widened by Fight Night, but
never closed either. Phase 8.5 closes it.

Reading the renderer before designing anything (per the brief's own
instruction) surfaced a second, more severe leak the brief's own prose did
not name explicitly: the v3.0 "core capture" callout — a reactive banner in
the same top HUD band — named **both** a capture's victim and its killer for
*any* entrant's capture, in *every* view mode, regardless of Perspective
selection. Because it is reactive (it appears at the exact moment a hidden
fact becomes true) rather than merely ambient, this is a stronger channel
than the cards ever were, and it is fixed here too.

| Area | Classification |
|---|---|
| HUD/card field inventory and data-source matrix | **BUILT** |
| Public-vs-perspective-vs-omniscient classification | **ESTABLISHED** |
| `entrant_card_known` policy (Broadcast / own / terminal / hidden) | **IMPLEMENTED AND QUALIFIED** |
| Entrant-card text redaction (`known=` threaded through formatting) | **IMPLEMENTED AND QUALIFIED** |
| Card status-color redaction (no leak through styling) | **IMPLEMENTED AND QUALIFIED** |
| Core-capture callout Perspective gating (`_perspective_safe_captures`) | **FOUND, IMPLEMENTED, AND QUALIFIED** |
| Broadcast-card backward compatibility | **CONFIRMED UNCHANGED** |
| Fight Night / Director policy | **CONFIRMED UNTOUCHED** |
| Hidden core/territory/score/kills regression (real match) | **IMPLEMENTED AND QUALIFIED** |
| Co-location / READ-owner card-layer non-association | **IMPLEMENTED AND QUALIFIED** |
| Terminal/lifecycle reveal policy | **IMPLEMENTED AND QUALIFIED** |
| 2 / 3 / 4-entrant layout, long names, 640×480 | **QUALIFIED** |
| Real Windows pygame visual qualification | **QUALIFIED (14 screenshots)** |
| Simulation / replay / trace isolation | **CONFIRMED (presentation-only diff)** |
| Full repository suite | **PASS (2832 passed, 14 skipped, 2 deselected)** |
| **Phase 8.5 overall** | **PASS** |

---

## 1. Baseline

| Fact | Value |
|---|---|
| Repository | `D:\Projects\BATTLE2` |
| Starting branch | `v4-spectator-phase8-development` |
| Starting `HEAD` | `99f4531ead21077d1f04c26e094d4ce5418705a9` (matched the phase brief's expected starting `HEAD` exactly) |
| `origin/main` | `4aa8ac3a4cc0deccfdd6c5b94136933b315335be` |
| Initial `git status` | clean (aside from the pre-existing unreadable `.pytest-cache-v141`, unchanged from every prior phase) |
| Development branch | `v4-spectator-phase8-5-development` (hyphenated rather than a literal decimal, matching every prior phase branch's plain-hyphen convention; created from `99f4531`) |
| Implementation commit | `9f3f35b87a5373ab4e1fe8bd409f7ae4b5cc3f75` |

Thirteen peer Claude Code sessions were present on the machine at session
start (`ListAgents`). `git worktree list` showed exactly one worktree at
this repository path (`D:/Projects/BATTLE2`, on `v4-spectator-phase8-
development`, the expected starting branch) plus one unrelated worktree at
a different path (`D:/Projects/Bytefray-v1-rc1`) — no second writable agent
on this tree. A 10-minute recursive scan for any file modified more
recently than session start returned empty, establishing tree stability
before any edit. No unexplained external write occurred at any point;
`HEAD`, `git status --short`, and every critical-file hash were re-verified
identical immediately before and after the full-suite qualification run
(§20).

`docs/research/v4/V4_SPECTATOR_PHASE_{4,5,6,7,8}_RESEARCH.md` and
`docs/specs/v4_spectator_perspective.md` were read in full before any design
decision, along with the current renderer/HUD/data-model source
(`replay_status.py`, `hud_layout.py`, `perspective.py`, `fight_night.py`,
`pygame_renderer.py`) — reading the renderer directly, not the prior
phases' prose alone, is what surfaced the capture-callout finding (§4.2).

**One workflow deviation, disclosed rather than hidden**: implementation
work began directly on `v4-spectator-phase8-development` before the Phase
8.5 branch was created, in violation of the brief's own §3 ordering
("confirm branch... create the Phase 8.5 branch... before editing"). This
was caught before any commit: `git branch --show-current` at that point
still showed `HEAD` at `99f4531` (unchanged) with the new work only in the
uncommitted working tree, so `git checkout -b v4-spectator-phase8-5-
development` recovered the correct state losslessly — the branch was
created *with* the in-progress edits already in the working tree, and
`git status --short` immediately after the checkout showed the identical
uncommitted diff, confirming nothing was lost or duplicated. No commit was
made on the wrong branch at any point.

---

## 2. HUD/card field inventory

Every field the top-band entrant card shows, from `battle_client.
replay_status.EntrantReplayStatus` (Phase-3 status model, `hud_layout.
format_entrant_card_lines`/`format_entrant_status_line`/
`format_entrant_stats_line`) and the separate v3.0 core-capture callout
(`pygame_renderer.core_captures_at_tick`/`CoreCaptureAttribution`):

| Field | Visual location | Source object | Source property | Canonical vs. perspective-derived | Reactive? |
|---|---|---|---|---|---|
| Display name | Card line 1 (identity) | `EntrantReplayStatus` | `.name` | Canonical (replay header) | No |
| Ordinal badge (`#1`…) | Card line 1 | caller-supplied | recorded roster order | Canonical, presentation-only | No |
| Agent id | Card line 1 | `EntrantReplayStatus` | `.agent_id` | Canonical | No |
| Palette color | Card line 1 (text color) | `AGENT_COLORS` | keyed by `agent_id` | Canonical, static | No |
| Alive/Dead/Captured | Card line 2 | `EntrantReplayStatus` | `.alive`, `.core.captured`, `.death_tick` | Canonical | Yes (updates every tick) |
| Killer attribution | Card line 2 | `EntrantReplayStatus` | `.killer_id` | Canonical | Yes |
| Core intact/total | Card line 2 | `EntrantReplayStatus` | `.core.intact_cells`/`.total_cells` | Canonical | Yes |
| Score | Card line 3 | `EntrantReplayStatus` | `.score` | Canonical | Yes |
| Territory cells/% | Card line 3 | `EntrantReplayStatus` | `.territory_cells`/`.territory_percentage` | Canonical | Yes |
| Kills so far | Card line 3 | `EntrantReplayStatus` | `.kills_so_far` | Canonical | Yes |
| **Capture callout** victim | Top-band overlay banner | `CoreCaptureAttribution` | `.victim` | Canonical (`KillDeathEvent`) | **Yes — reactive, tick-triggered** |
| **Capture callout** killer | Top-band overlay banner | `CoreCaptureAttribution` | `.killer` | Canonical | **Yes — reactive, tick-triggered** |

Every canonical field is computed from `session.current_state` (the whole
replay's ground truth) with **zero** awareness of Perspective mode —
`EntrantReplayStatus`/`get_entrant_statuses` never import or reference
`battle_client.perspective` at all (confirmed by inspection: `replay_status.
py`'s only non-stdlib imports are `battle_engine.python_runtime`,
`battle_engine.replay`, and `battle_client.analysis`/`session`). This is by
design and stays that way (§7) — the fix does not touch this file.

---

## 3. Data-source matrix

| HUD field | Broadcast source | Perspective-safe source | Allowed in Perspective? | Action |
|---|---|---|---|---|
| Selected entrant's own name/id/color/ordinal | `EntrantReplayStatus` | Same | Yes | Keep |
| Opponent name/id/color/ordinal | `EntrantReplayStatus` | Same (public roster, §5) | Yes | Keep |
| Selected entrant's own alive/core/score/territory/kills | `EntrantReplayStatus` | Same (own facts, §7) | Yes | Keep |
| Opponent alive/dead/captured, live | `EntrantReplayStatus` | **none** (`AGENT_ELIMINATED` is omniscient-only unconditionally, Phase 7 §2) | No, until terminal | Hide → `UNKNOWN` |
| Opponent core intact count, live | `EntrantReplayStatus` | **none** (`CORE_CELL_LOST` omniscient-only) | No, until terminal | Hide → `Core ?/N` |
| Opponent score, live | `EntrantReplayStatus` | **none** — no semantic event exists for score at all | No, until terminal | Hide → `Score ?` |
| Opponent territory, live | `EntrantReplayStatus` | **none** — same | No, until terminal | Hide → `Territory ?` |
| Opponent kills, live | `EntrantReplayStatus` | **none** — derived from `KillDeathEvent`, omniscient | No, until terminal | Hide → `Kills ?` |
| Any of the above, at/after `result_ticks` | `EntrantReplayStatus` | Same (terminal exception, §9) | Yes | Keep |
| Capture-callout victim, selected entrant is victim | `CoreCaptureAttribution.victim` | Trivial self-knowledge | Yes | Keep |
| Capture-callout killer, selected entrant is victim | `CoreCaptureAttribution.killer` | **none** (anonymous-contact model, spec §6) | No | Strip to `None` |
| Capture-callout, selected entrant is neither victim nor at terminal | `CoreCaptureAttribution` | **none** | No | Suppress entirely |

No policy decision above was made without first identifying the exact
factual source, per the brief's §6 instruction: every "No, until terminal"
row was checked against Phase 3's `SpectatorEventKind` visibility table
(Phase 7 §2's own restatement of it) rather than assumed.

---

## 4. Public facts vs. entrant knowledge vs. omniscient truth

### 4.1 Public spectator/match metadata (kept everywhere, both modes)

Ruleset label, runtime kind, arena size, entrant count, match tick,
terminal winner/termination reason (once `result_ticks` is reached),
**participant name/id/color/ordinal** — the established Phase 4–8 policy
(brief §8): a Perspective viewer may already know who is in the match even
while on-arena contact identity stays anonymous. None of this changed.

### 4.2 Entrant-qualified knowledge

Delivered via `ObservationV2`/`PerspectiveState`: own core base/size, own
process anchor/reach, current/stale anonymous contacts, READ history. The
selected entrant's own card is treated as belonging to this category by
extension — see §7 for why `alive`/`score`/`territory`/`kills`, which have
no literal field in `PerspectiveState`, are still shown for the *selected*
entrant's own card.

### 4.3 Omniscient canonical truth

Everything else on the card for an *opponent*: alive/dead/captured state,
core intact count, score, territory, kills, and (the callout's own
addition) capture attribution. All eight of `HOSTILE_WRITE`,
`FIRST_HOSTILE_WRITE`, `CORE_CELL_LOST`, `PROCESS_DISRUPTED`,
`AGENT_ELIMINATED`, `AGENT_FORFEITED`, `MATCH_ENDED`, `VICTORY` are
`_OMNISCIENT_ONLY` (Phase 7 §2); score/territory/kills have **no semantic
event at all**, omniscient or otherwise — they are pure replay bookkeeping
Phase 3 never modeled as entrant-knowable in the first place.

---

## 5. Opponent-name policy

**Kept.** Per §4.1 and the brief's own §8 guidance, participant names/ids
are public match metadata under the established Phase 4–8 policy — hiding
them would make Perspective mode austere for no informational-boundary
reason, since match participation is already public. The prohibition is
strictly **association** (can a viewer join a named card to an anonymous
on-arena contact?), which §12 covers: nothing added or changed here creates
that link.

---

## 6. Score policy

Audited directly (brief §9):

- **Not** entrant-safe: `PerspectiveState` has no score field, and no
  `SpectatorEventKind` carries it — there is no semantic event for "your
  score changed," so it cannot leak *individual increments*, but the
  *running total* still silently encodes hidden combat activity (a rising
  opponent score is itself evidence something happened off-screen).
- Score is not currently documented anywhere as intentionally public match
  information analogous to the ruleset or terminal result.
- **Decision: hide for opponents while live, reveal at the terminal tick**
  — the same policy as every other omniscient field, for consistency and
  because there is no qualified alternative value to substitute (brief
  §10's "prefer the least misleading presentation" — a placeholder is less
  misleading than a frozen or synthetic number).

---

## 7. Core/territory policy

Confirmed the **strongest leak**, exactly as the brief predicted (§10): an
opponent's live core-intact count and territory were shown unchanged in
Perspective mode, continuously updating from canonical truth with zero
gating. Neither has any entrant-safe substitute in `PerspectiveState` (which
models only the *selected* entrant's own core base/size sample, never an
opponent's). **Decision: hide for opponents while live** (`Core ?/N`,
`Territory ?`), matching score. `N` (the core's fixed size, 8) is kept
visible in the placeholder — it is a Ruleset-wide constant identical for
every entrant, never a secret, only the *intact count* is.

### 7.1 Selected entrant's own card is exempt

`PerspectiveState` was never designed to carry the selected entrant's own
`alive`/`score`/`territory`/`kills` (Phase 4–6 modeled only what the engine
delivers that the entrant would not otherwise trivially know). Rather than
read this as "even the entrant's own card must be redacted, since the
dataclass has no field for it," Phase 8.5 treats an entrant's own life/core/
score/territory/kills as facts *about itself*, not omniscient spying on an
opponent — the entrant is a first-person party to what happens to it,
regardless of whether the engine's message-passing model happens to encode
that as a distinct `ObservationV2` field. `entrant_card_known` therefore
returns `True` unconditionally whenever `status.agent_id ==
selected_entrant_id`, and the real-match regression (§13) confirms A's own
card stays fully detailed at every tick, live and terminal alike.

---

## 8. Selected-entrant card policy

**Full canonical detail, unchanged from Broadcast**, per §7.1. This is
Policy-A-equivalent to Fight Night's own §11 decision: the selected
entrant's own domain is never redacted from itself.

## 9. Opponent-card policy

**Hidden while live, revealed at the terminal tick.** Implemented as one
pure function, `hud_layout.entrant_card_known(status, *, selected_entrant_id,
is_terminal)`:

```python
if selected_entrant_id is None:      # Broadcast
    return True
if status.agent_id == selected_entrant_id:   # own card
    return True
return is_terminal                    # everyone else, gated on match-over
```

`is_terminal` reuses `SpectatorDerivation.result_ticks` — the exact same
match-over boundary the Director's `TERMINAL_HOLD` override (Phase 7 §3)
and Fight Night's result card (Phase 8 §12) already compute — rather than
inventing a second terminal concept. The renderer computes it once per
frame in `PygameRenderer._perspective_card_knowledge_basis`, reading the
real `PerspectiveManager`'s `.mode`/`.derivation.result_ticks`.

## 10. Broadcast-card policy

**Unchanged.** `entrant_card_known` returns `True` unconditionally whenever
`selected_entrant_id is None` (the value `_perspective_card_knowledge_basis`
always returns for Broadcast/no-perspective), so no Broadcast code path is
touched by the new `known=` parameter's default (`True`) anywhere. Every
pre-existing `format_entrant_*` test in `test_hud_layout.py` and every
pre-existing renderer test in `test_pygame_renderer.py` continues to pass
unmodified (only one, a hand-built `MockPerspectiveManager` missing the new
`.derivation` attribute the wiring reads, needed a one-line mock update —
the same class of pre-existing-mock-gap Phase 7/8 each hit once, §17.1).

## 11. Rejected policy alternative

**Policy B — omniscient cards remain broadcast chrome even in Perspective
mode — rejected**, for the reason Phase 8 §11.1 already flagged this
inconsistency for and the brief's own §12 anticipates: it is what Phase 8.5
exists to fix, and retaining it would leave Phase 9 Color Commentator with
exactly the awkward "HUD says one thing, commentary in the same voice must
say another" exception §31/§32 name as the hard release blocker. No
"unmistakably labeled, visually separated omniscient panel" alternative was
built either — a single behavior (redact, with a labeled `UNKNOWN`) is
simpler, cheaper, and was already the brief's own preferred target (§11).

---

## 12. The capture-callout finding (beyond the brief's named leak)

Reading `pygame_renderer.py` before designing anything (per the brief's own
instruction, and mirroring exactly how Phase 8 §9's own reading of the same
file changed *its* scope) surfaced that the v3.0 "core capture" callout —
`_advance_capture_callout`/`core_captures_at_tick`/
`format_core_capture_callout_lines` — is **not** gated by Perspective mode
at all. It fires for *any* entrant's core capture, in *every* view mode, and
its `CoreCaptureAttribution` names **both** victim and killer — a
structurally stronger leak than the cards, since `FightNightEvent.subject`
is a single optional id that makes `A ATTACKS B` unconstructible (Phase 8
§13), while this callout has always had room for exactly that pair.

Because it is **reactive** (Phase 8 §11's own distinction: "a ribbon entry
is reactive — it appears at the exact moment something happens... a far
stronger channel"), leaving it unfixed would have left Phase 8.5 half-done:
even a Perspective viewer whose *cards* correctly show `UNKNOWN` would still
see a banner announcing "Entrant B eliminated by Entrant A" the instant it
happened, on any of the four omniscient-only capture facts (victim/killer
identity, the fact of elimination itself, and the tick it occurred).

**Decision, implemented as `pygame_renderer._perspective_safe_captures`**:

- Broadcast, or at/after the terminal tick: unchanged (matches
  `entrant_card_known`'s own two "always known" cases).
- Live Perspective, selected entrant is the capture's *victim*: shown, but
  with `killer` stripped to `None` — the entrant trivially knows its own
  core was captured, but the attacker's identity is never delivered through
  the qualified anonymous-contact model (spec §6), so naming one would
  associate a named entrant with the victim's own anonymous-contact history
  exactly as §13 forbids.
- Live Perspective, selected entrant is anyone else — **including the
  capture's own attacker** — suppressed entirely, with **no exception**.
  `AGENT_ELIMINATED` is omniscient-only unconditionally (Phase 7 §2); this
  callout does not invent a narrower rule than the Director and Fight Night
  already settled on. §14's visual qualification confirms this is the most
  illustrative case: entrant A, who personally captured B's core at tick 3
  of a 90-tick match, sees **no callout at all** for its own kill.

Filtering happens in `_advance_capture_callout` *before* a capture is ever
appended to the callout queue — the same "filter before assembly" discipline
Fight Night's ribbon already uses (Phase 8 §11), so a hidden capture is
never queued, drawn, and then hidden; it is simply never a candidate.

---

## 13. Hidden core/territory/score regression (mandatory, §38)

`client/tests/test_perspective_card_knowledge.py::
test_real_match_hidden_opponent_core_loss_never_reaches_a_perspective_card`
drives the full real pipeline: a genuine `NativeMatchService` match (the
EXECUTIONER/SLEEPER fixture, reused verbatim from Phase 7's own
`test_v4_spectator_director.py`, which already proved this exact match
produces a real core-strip-to-elimination) → `analyze_pair` → a real
`PerspectiveManager` → the card presentation model → the real
`PygameRenderer._perspective_card_knowledge_basis` wiring.

Precondition proven from the real artifact, not assumed: the match's
`AGENT_ELIMINATED` event(s) all carry `visible_to == ()`. A live tick is
then *discovered* (not hard-coded) where B's real canonical core is damaged
but B is still alive (`0 < intact_cells < 8`), and the test asserts:

- **Broadcast**, that tick: the real damaged core count and real score
  appear in the formatted card lines, unchanged.
- **Perspective A**, same tick, via the renderer's own
  `_perspective_card_knowledge_basis`: `known` is `False`; the exact real
  intact-cell count and exact real score string are asserted **absent**
  from every formatted line, and `"UNKNOWN"` is asserted present.
- **A's own card**, same tick: `entrant_card_known` returns `True` —
  unaffected.
- **Terminal tick** (`result_ticks`): the same opponent card reverts to full
  canonical detail, matching Broadcast — the terminal exception, proven on
  the real artifact rather than only at the pure-function level.

This is the HUD-layer equivalent of Phase 7 §13's Director regression and
Phase 8's Fight Night ribbon regression, closing the gap those two phases
left open for the card layer.

---

## 14. Co-location and READ-owner regression

Not re-derived at the arena/contact layer (unchanged, untouched — see §16),
but proven at the card layer, which is the layer that changed:
`test_hidden_fields_are_identical_regardless_of_the_real_underlying_values`
constructs two entrants with deliberately very different real canonical
state (one alive with a full core and a high score, one captured with an
empty core and zero score) and asserts their **redacted** status/stats
lines are byte-identical — only the public identity line may ever differ.
Because redaction is now a static function of `(is this the selected
entrant, is the match over)` alone, with **zero** dependency on any
per-entrant reactive state, there is no remaining channel through which a
Perspective viewer could use hidden-state *differences* between two
opponent cards to tell them apart — the card-layer half of the anonymity
property Phase 8 already qualified for the arena and ribbon.

Visually confirmed at 4-entrant scale (`4p_J`, §17.1): three simultaneously-
redacted opponent cards (B, C, D — one captured by the selected entrant
itself, one captured by a third party, one untouched) render **identically**
(`UNKNOWN | Core ?/8` / `Score ? | Territory ? | Kills ?`) despite wildly
different real underlying states.

READ-owner separation was never a card-layer concern in the first place —
`EntrantReplayStatus`/the card formatters never read `ReadKnowledge.owner`
or anything from `PerspectiveState` at all — so there was nothing to
regress here; recorded for completeness per the brief's checklist rather
than left unaddressed.

---

## 15. Terminal/lifecycle policy

Reused Phase 7/8's already-qualified boundary rather than reopening engine
semantics (brief §18's explicit instruction): the whole match being over
(`tick >= SpectatorDerivation.result_ticks`) is the one and only condition
under which an opponent card or the capture callout may show real values it
would otherwise hide. This mirrors:

- The Director's `TERMINAL_HOLD` override (Phase 7 §3): `MATCH_ENDED`/
  `VICTORY` are omniscient-only forever, but the terminal hold uses
  `result_ticks` directly, a match-level fact, never a per-entrant-filtered
  event.
- Fight Night's result card (Phase 8 §12): built from plan-level metadata,
  never a filtered event, for the identical reason — once the match is over
  there is no more hidden gameplay to protect.

No new lifecycle nuance was introduced. `AGENT_ELIMINATED` (a *specific*
entrant's death while a larger match may continue) remains excluded from
every Perspective-mode presentation surface until the terminal tick,
exactly as Phase 7/8 already established.

---

## 16. Renderer architecture

Kept semantic logic out of the pygame renderer as instructed (brief §19):

```text
real PerspectiveManager (mode, derivation.result_ticks)
              ↓
_perspective_card_knowledge_basis   (renderer, one small per-frame lookup)
              ↓
entrant_card_known                  (hud_layout.py, pure, no pygame)
              ↓
format_entrant_*_line(..., known=)  (hud_layout.py, pure, no pygame)
              ↓
_draw_entrant_card                  (renderer: color choice + blit only)
```

`_perspective_card_knowledge_basis` itself makes no policy decision beyond
"which entrant is selected, and has the match ended" — two lookups, no
interpretation — and hands both facts to the same pure `entrant_card_known`
function `test_hud_layout.py` exercises directly. The capture-callout fix
follows the identical shape: `_perspective_safe_captures` is a pure,
independently-testable function that the renderer calls once, before
queuing, never inline inside drawing code. No `if perspective: hide_x`
conditional was scattered through `_draw_entrant_card`/`_draw_top_band`; the
only new conditional there is the single `if not known: status_color = ...`
color choice, which is presentation (*how* to draw an already-decided fact),
not policy (*whether* to show it).

**Arena, Director, and Fight Night are untouched.** Confirmed both by
inspection (the diff touches exactly `hud_layout.py` and
`pygame_renderer.py`) and by hash (§20): `spectator_director.py`,
`director.py`, `spectator_fight_night.py`, and `fight_night.py` all hash
identically to Phase 8's own recorded values.

---

## 17. Visual qualification (real Windows pygame)

14 screenshots captured driving the real `PygameRenderer` (real SDL 2.28.4,
real Windows video driver — `pygame 2.6.1 (SDL 2.28.4, Python 3.13.14)`,
not the dummy driver) via a `PygameRenderer` subclass whose `_loop` is
replaced by a scripted sequence, calling the same `_redraw` the real event
loop calls every frame — mirroring Phase 7/8's own disclosed methodology
exactly ("`run()`'s own production setup path with only the blocking event
loop replaced by a scripted sequence").

### 17.1 Mandatory disclosure cases

| # | Case | Result |
|---|---|---|
| `2p_A` | Broadcast, 2-entrant, mid-fight (tick 1/2) | B's real damaged state shown plainly: `Alive \| Core 7/8`, `Score 1 \| Territory 7 (10.9%)`. |
| `2p_B` | **Perspective A, same match/tick** | A's own card unchanged (`Alive \| Core 8/8`). **B's card: `UNKNOWN \| Core ?/8`, `Score ? \| Territory ? \| Kills ?`.** Arena shows only an anonymous `CONTACT` ring, no color tying it to B's card. The mandatory hidden-core/score/territory case, visually confirmed. |
| `2p_C` | Perspective A, terminal tick (2/2) | B's card reverts to full detail — `CAPTURED @ T2 by A \| Core 0/8`, `Score 1 \| Territory 0 (0.0%)` — matching Broadcast exactly. The terminal exception, visually confirmed. |
| `2p_D` | Broadcast, stepped tick-by-tick through the elimination | `CORE CAPTURED` callout banner: `Entrant A eliminated Entrant B — CAPTURED @ T2 by A`. Broadcast baseline, unaffected. |
| `4p_I` | Broadcast, 4-entrant, live double-capture at tick 3 of 90 | Callout shows both simultaneous captures with full attribution (`B` by `A`, `D` by `C`); both cards show full detail. |
| `4p_J` | **Perspective A, identical match/tick — A itself captured B** | **No callout banner at all.** All three opponent cards (B, C, D) read `UNKNOWN \| Core ?/8` / `Score ? \| Territory ? \| Kills ?`, byte-identical to each other despite very different real states. A's own card: `Alive \| Core 8/8`, `Score 8 \| Territory 16 (4.0%) \| Kills 1` — A even sees its own kill count, since that is a fact about A, not a spied-on opponent fact. **The "no exception even for the attacker" policy, visually confirmed on a genuinely live (tick 3 of 90) capture, not merely a terminal one.** |

`4p_J` is the single most important screenshot in this qualification: it is
the one case where a naive fix ("hide the victim's identity, but the
attacker surely gets to know its own kill") would have failed, and where the
real render proves the stricter policy actually holds.

### 17.2 Entrant-count and layout checklist

| # | Case | Result |
|---|---|---|
| `3p_K` | Perspective A, 3 entrants, default window | Card grid reflows to 2 rows as usual (unaffected by Phase 8.5); B and C both redacted identically. |
| `4p_F` / `4p_G` | Broadcast vs. Perspective A, 4 entrants, default window | Direct before/after pair at the same tick — B/C/D redacted only in the Perspective view. |
| `4p_H` | **Perspective A + Director ON + Fight Night ON, 4 entrants, 640×480** | All four cards fit with no overlap or clipping; the long entrant name (`RECURSIVE PERIMETER DENIAL CONSTRUCT…`) truncates correctly; footer shows `DIRECTOR CRUISE 18tps`; Fight Night ribbon reads `FIGHT NIGHT · A KNOWS` in the letterbox gutter, arena unobstructed — the full combined-feature, minimum-resolution case (brief §29/§30/§44), unaffected by the card remediation's own geometry (none was changed). |

Screenshots are retained in the session's scratch directory as
qualification evidence, not committed, matching Phase 6/7/8's own
convention.

---

## 18. Performance

`entrant_card_known` and `_perspective_safe_captures` are both `O(1)`
comparisons against already-resolved values (an id equality check, an
integer comparison) — no loop, no new derivation, no per-tick history walk.
`_perspective_card_knowledge_basis` is two attribute reads and one integer
comparison. All three run at most once per entrant per frame (four times a
frame in the worst supported case), which is immeasurably below the
per-frame costs Phase 7/8 already measured and qualified as negligible
(Director warm lookup 0.00008 ms, Fight Night warm `state_at_tick` 0.001337
ms) — no dedicated micro-benchmark was added, since there is no loop or
allocation here for one to meaningfully measure; the existing full 2832-test
suite (§20, including every pre-existing performance-sensitive path) ran in
303.5 s, statistically indistinguishable from Phase 8's own 300.55 s on the
same suite shape.

## 19. Memory

No new cache, container, or retained per-tick structure was introduced.
`entrant_card_known`/`_perspective_safe_captures` allocate nothing beyond
their own return values (a `bool`, or a filtered tuple already sized by the
input). No eviction policy is needed and none was added, per the brief's own
instruction not to add one without measured need.

---

## 20. Qualification integrity

| Check | Before full suite | After full suite |
|---|---|---|
| `HEAD` | `9f3f35b87a5373ab4e1fe8bd409f7ae4b5cc3f75` | `9f3f35b87a5373ab4e1fe8bd409f7ae4b5cc3f75` (unchanged) |
| `git status --short` | clean | clean (unchanged) |
| SHA-256 of 12 critical files | recorded | **identical** |

```text
922d6289d46f08d31fd1115543597dbc0b88cb86c886abb757e5af2ef3a5fe3a  client/src/battle_client/hud_layout.py
6add2a31c03d45202f1ebf69d713eb804da41a4054b82611e0fd328d965977bc  client/src/battle_client/renderers/pygame_renderer.py
ff9ad9af3af77f438926511317cfe57211c63d25ec306a0df2fb3c34fae22e1a  client/src/battle_client/perspective.py
68d34ecc1bafef7f5ddcdffd4d594f7d9f0c25968a2d77726298c73745c69fbe  client/src/battle_client/fight_night.py
1ef7c43c56a3e54c0179f45bf4855f5d66b63eb657ae841657e9834823e48f17  client/src/battle_client/director.py
e45228c01598588dd216e2d1f7659d284a67c03550152bdda71ed279dd0b4b30  client/src/battle_client/replay_status.py
2878c805fe2e93c4898785472cb610ba52f507d0b7fc236869dc28c89ee39eda  client/src/battle_client/player.py
5927754122906b05aa79e43a1290216f752146d30319f52fc0aca0891349573b  client/src/battle_client/cli.py
978bc346111af6a23d25dc364e223e778cc639ef905d2abf3d7702b115e5ce11  engine/src/battle_engine/spectator_derivation.py
7d32ef4f9e70d3f94450104f4f55b0c53643bd92e97468fac8146a5ce4f58d97  engine/src/battle_engine/spectator_perspective.py
c62e6c7a5af098bf9f6ce9c4418994d0cba8515b6e31b4a804b0f43c9cd59b87  engine/src/battle_engine/spectator_director.py
1bd143b5528177edf178f579dc6f0e361029e09c152b8b8c07b03540feffc788  engine/src/battle_engine/spectator_fight_night.py
```

Every file **except** `hud_layout.py` and `pygame_renderer.py` matches Phase
8's own recorded hash exactly, byte-for-byte, independently confirming the
diff touches only the two files it is supposed to.

### 20.1 Simulation/replay/trace isolation

No simulation, replay, or trace code was touched — the diff is entirely
within `hud_layout.py` (pure text/geometry formatting) and
`pygame_renderer.py` (drawing/color choice + the two new pure gating
functions). `NativeMatchService`, `battle_engine.replay`, and
`battle_engine.spectator_*` modules are untouched, confirmed both by the
hash table above (every engine file listed is byte-identical to Phase 8)
and by `git diff --stat` showing zero engine files changed.

### 20.2 Static qualification

```text
ruff check .                   -> All checks passed! (plus the pre-existing,
                                  unrelated .pytest-cache-v141 access warning)
mypy engine/src/battle_engine  -> Success: no issues found in 101 source files
mypy client/src/battle_client  -> Success: no issues found in 15 source files
git diff --check               -> clean
```

File counts are **unchanged** from Phase 8 on both sides (101 engine, 15
client) — no new module was added to either package; the new client
functions live in the two existing files they extend.

---

## 21. Tests

| Suite | Count |
|---|---:|
| `client/tests/test_hud_layout.py` (new, Phase 8.5) | **14 passed** |
| `client/tests/test_perspective_card_knowledge.py` (new file, Phase 8.5) | **12 passed** |
| **Phase 8.5 focused total** | **26 passed** |
| Phase 1–8 regression gate (Phase 8's exact file set, extended with the new Phase 8.5 file) | **496 passed** |
| `client/tests/` (full) | **458 passed** (0 skipped, 2 deselected) |
| `engine/tests/` (full, isolation) | **2372 passed, 14 skipped** |
| **True full repository suite** | **2832 passed, 14 skipped, 2 deselected**, 303.5 s |

### 21.1 Arithmetic reconciliation

Phase 8 closed at 2806 passed / 14 skipped / 2 deselected. Phase 8.5 added
**14** new tests to `test_hud_layout.py` and **12** to the new
`test_perspective_card_knowledge.py` (both counted directly via `git diff
99f4531 HEAD -- <file> | grep -c '^+def test_'`, not estimated):
**2806 + 14 + 12 = 2832** — exact match, no unexplained residual.

Per-suite reconciliation, matching Phase 8's own reported split exactly:
`engine/tests/` is **byte-identical to Phase 8's own figure** (2372 passed,
14 skipped — zero engine files changed, §20.1), `client/tests/` is
432 + 26 = **458**, and the remaining 2 of the full suite's 2832 come from
`_legacy/tests` (432 + 2372 + 2 = 2806 was Phase 8's own reconciliation of
the same three-suite split; 458 + 2372 + 2 = 2832 here).

### 21.3 Coverage against the brief's §36 checklist

Every named item has at least one focused test: Broadcast canonical card
unchanged (`test_broadcast_shows_every_capture_unchanged` +
`known=True` default across every pre-existing test); Perspective
selected-entrant card (`test_entrant_card_known_true_for_the_selected_
entrants_own_card`); Perspective opponent hidden field
(`test_entrant_card_known_false_for_an_opponent_before_the_terminal_tick`,
`test_status_line_hidden_*`, `test_stats_line_hidden_*`); hidden core/
territory change suppression (the real-match regression, §13); hidden score
change suppression (same test); public participant-name behavior
(`format_entrant_card_lines`'s identity line is never passed `known=`);
public terminal result behavior (`test_entrant_card_known_true_for_an_
opponent_at_the_terminal_tick`); co-location non-association
(`test_hidden_fields_are_identical_regardless_of_the_real_underlying_
values`); Perspective mode switching
(`test_knowledge_basis_is_none_false_in_broadcast_mode` /
`test_knowledge_basis_reports_selected_entrant_and_liveness`); 2/3/4-entrant
card model (§17.2, plus `test_entrant_card_known_across_a_four_entrant_
roster`).

---

## 22. Historical regression gates

Phase 1–8 focused files, run together with the two new Phase 8.5 files, in
one sequential invocation (`--basetemp=.pytest-tmp/phase85_gate`):

```text
engine/tests/test_spectator_analyzer.py
engine/tests/test_spectator_aggregation.py
engine/tests/test_agent_trace.py
engine/tests/test_v4_trace_equivalence.py
engine/tests/test_v4_spectator_derivation.py
engine/tests/test_v4_spectator_perspective.py
engine/tests/test_v4_spectator_director.py
engine/tests/test_v4_spectator_multi_entrant.py
engine/tests/test_v4_spectator_fight_night.py
client/tests/test_perspective.py
client/tests/test_pygame_renderer.py
client/tests/test_playback_controller.py
client/tests/test_hud_layout.py
client/tests/test_director.py
client/tests/test_fight_night.py
client/tests/test_perspective_card_knowledge.py
```

**496 passed, 0 failed, 0 errors, 0 skipped**, 17.3 s. Phase 4 Perspective
semantics, Phase 5 geometry/disclosure, Phase 6 real STALE/READ renderer
paths, Phase 7 timing disclosure, and Phase 8 Fight Night hidden-event/co-
location policy all re-confirmed intact.

---

---

## 23. Hostile self-review (brief Part M)

| Question | Answer |
|---|---|
| Can Perspective mode still show canonical opponent core state? | **No**, live. Redacted to `Core ?/N`; real-match regression (§13) confirms the exact real intact-cell count is absent from the formatted text. Reappears only at the terminal tick, by design. |
| Can Perspective mode still show hidden opponent territory? | **No**, live. Same mechanism, same test. |
| Can Perspective mode still show hidden score changes? | **No**, live — hidden entirely rather than shown-and-frozen (a frozen stale number was rejected as more misleading than a placeholder, brief §10). |
| Can participant name/color be linked to anonymous contact identity? | **No.** Names/colors are unchanged (they were already public, §5) and arena contacts remain uncolored neutral rings (Phase 8's own established behavior, untouched); §17.1's `2p_B`/`4p_J` screenshots show a `CONTACT` marker with no color tying it to any card. |
| Can co-location be disambiguated through card behavior? | **No.** Every opponent card's hidden fields are now a pure function of `(is this the selected entrant, is the match over)` — proven identical for two entrants with very different real state (§14). |
| Can READ owner identify a spatial contact? | **No** — never was a card-layer concern; `EntrantReplayStatus`/the formatters never read `ReadKnowledge` at all. |
| Can hidden events trigger card flashes or reactive styling? | **No.** Cards carry no reactive state of their own (redaction is static per-frame, not event-triggered), and the one genuinely reactive HUD element that *did* trigger on hidden events — the capture callout — is the finding fixed in §12; `4p_J` visually confirms zero callout on a live, selected-entrant-caused capture. |
| Does terminal/public metadata follow a documented policy? | **Yes** — §9/§15, reusing the Director/Fight Night terminal boundary rather than inventing a new one. |
| Does selected entrant still receive useful own information? | **Yes** — unconditionally, §7.1/§8; every Perspective screenshot in §17 shows entrant A's own card fully detailed. |
| Does Broadcast remain unchanged? | **Yes** — §10, confirmed by every pre-existing test passing unmodified plus the `known=True` default touching zero Broadcast code paths. |
| Does Fight Night remain entrant-safe? | **Yes** — `fight_night.py`/`spectator_fight_night.py` hash identically to Phase 8 (§20); untouched. |
| Does Director remain entrant-safe? | **Yes** — `director.py`/`spectator_director.py` hash identically to Phase 8; untouched. |
| Does seeking change card contents at the same tick? | **No** — `entrant_card_known` takes no tick-history argument at all, only the current tick's own `is_terminal` boolean; the real-match regression seeks freely (forward search, then a direct jump to `result_ticks`) and gets the same answer either way, by construction rather than by testing every path. |
| Does switching modes leave stale canonical values behind? | **No** — every frame recomputes `known` fresh from `_perspective_card_knowledge_basis`; there is no cached "last known" value anywhere to go stale. |
| Does 4-entrant Perspective fit at 640×480? | **Yes** — `4p_H`, combined with Director and Fight Night both on, long name included. |
| Do long names genuinely fit? | **Yes** — same screenshot; truncation behavior is entirely `hud_layout.truncate_with_ellipsis`, unmodified by this phase. |
| Is renderer logic presentation-only? | **Yes** — §16; the renderer's only new conditional chooses a color for an already-decided fact. |
| Did any semantic rule migrate into pygame code? | **No** — both new predicates (`entrant_card_known`, `_perspective_safe_captures`) are plain pure functions, independently unit-tested without pygame. `_perspective_safe_captures` lives in `pygame_renderer.py` only because its sibling `core_captures_at_tick`/`CoreCaptureAttribution` already did (a pre-existing v3.0 pattern, not one Phase 8.5 introduced) — it imports nothing from `pygame` itself. |
| Can Phase 9 commentary now use one coherent information policy? | **Yes** — §25. |
| Was the exact committed code the exact code qualified? | **Yes** — §20: `HEAD` and every critical-file hash were identical immediately before and after the full-suite run. |

---

## 24. Remaining limitations

Disclosed plainly rather than omitted, carried forward from Phase 8 where
still accurate:

1. **The header still spoils the match result from tick 0** (Phase 8
   limitation #2, unchanged, out of scope here — it affects Broadcast
   identically to Perspective, so it is not a Perspective-boundary
   asymmetry, and fixing it was explicitly not this phase's mandate).
2. **The Director/Perspective debug overlays still overlap at narrow
   widths** (Phase 8 limitation #3, `F3`-gated diagnostics only, unrelated
   to this phase's surfaces).
3. **The capture callout's own suppression was discovered by reading the
   renderer, not named in the original brief** — disclosed prominently in
   §12 rather than fixed quietly; a reviewer relying on the brief's literal
   text alone (top-band *cards*) could have missed it.
4. **Killed-by-unattributed-forfeit wording is unaffected**: an opponent's
   forfeit (no `killer_id`) already rendered without attribution before this
   phase, so `entrant_card_known`'s hiding of the whole life-state field
   subsumes it without special-casing, but it was not separately stress-
   tested with a real forfeit fixture (only a real core capture).
5. **Terminal-tick reveal is all-or-nothing per card, not per-field**: once
   `is_terminal`, an opponent card shows *every* field at once (life, core,
   score, territory, kills) rather than, say, revealing lifecycle state
   slightly before numeric stats. This matches how Broadcast has always
   presented the terminal state and was not questioned further.
6. **No dedicated `--perspective` HUD documentation exists outside this
   document and the CLI's own help/in-viewer panel** — matching the
   restraint Phase 7/8 each judged sufficient at this feature scale.

None are classified as blocking.

---

## 25. Color Commentator readiness

**GO.**

Phase 8's own §29 "GO WITH PREREQUISITES" named exactly one hard
prerequisite before commentary work should begin: *"Resolve limitation 1
(omniscient cards in Perspective mode) first. A commentator speaking in an
entrant's voice beside a HUD showing that entrant's opponents' core state
would be incoherent, and the fix belongs below the commentary layer."* That
prerequisite is resolved by this phase. The brief's own §32 hard-gate
question —

> In Perspective mode, can a user learn hidden opponent combat state merely
> by looking at persistent HUD elements?

— now has the expected answer, **NO**, apart from the explicitly classified
public match facts (§4.1), demonstrated both by unit/integration test (§13,
§14) and by real-render screenshot (§17.1's `4p_J`).

Phase 9 now inherits one coherent, machine-enforceable information policy
across every spectator surface:

- qualified semantic events with an explicit `visible_to` audience (Phase
  3);
- entrant-safe `PerspectiveState` (Phases 4–6);
- deterministic `DirectorPlan` (Phase 7);
- `FightNightPlan`/`FightNightState` (Phase 8);
- **entrant-card `known`/redaction and capture-callout gating (Phase 8.5)**.

A commentator speaking in entrant A's voice can now sit beside A's own HUD
without contradiction: every surface on screen — arena, cards, ribbon,
Director pacing, capture callout — agrees on exactly what A has a basis to
know at that tick.

---

## 26. Release-readiness assessment

**PUBLISH NEXT V4 ALPHA.**

| Dimension | Assessment |
|---|---|
| Perspective Cam | Qualified Phases 4–6; unmodified this phase — the full Phase 1–8 historical file set (§22) passes unchanged. |
| Dynamic Director pacing | Qualified Phase 7; untouched and hash-identical this phase. |
| Fight Night presentation | Qualified Phase 8; untouched and hash-identical this phase. |
| Perspective HUD coherence | **Newly qualified this phase** — the one item Phase 8 itself flagged as the strongest remaining Phase-9 blocker is closed, with real-match and real-render evidence, not merely inspection. |
| Windows visual quality | 14 real-SDL screenshots across 2/3/4 entrants, the documented 640×480 minimum, long names, and every disclosure case named in the brief plus the capture-callout finding. |
| Ordinary replay compatibility | Broadcast, Perspective-unavailable, and no-trace paths are all unaffected — `known=True` is the default everywhere the new parameter isn't explicitly threaded, and `_perspective_card_knowledge_basis` degrades to `(None, False)` (nothing hidden) whenever no `PerspectiveManager` exists. |
| Simulation/replay/trace identity | Confirmed unchanged — zero engine files touched, confirmed by hash (§20). |

v4's spectator HUD no longer has a documented, self-acknowledged
inconsistency between what the arena/Director/Fight Night show and what the
persistent cards show. The next alpha ships with the same Phase 8 feature
set, now internally coherent rather than "coherent except for one disclosed
exception."

---

## 27. Recommended Phase 9

**Color Commentator, on the terms Phase 8 §29 and this document's §25
already establish.** No further HUD-coherence prerequisite work is
outstanding. The two small cosmetic items disclosed above (§24.1/§24.2, both
carried forward unchanged from Phase 8) remain reasonable small-scope
candidates to fold into Phase 9's own pass if convenient, but block nothing.

---

## Guiding principle, re-affirmed

Phase 8's own closing words were: *"A hidden opponent fact is still a leak
if it appears only as a number in a card."* Reading the renderer directly,
rather than only the brief's prose, found that the same principle applied
one layer further than the brief's own examples reached — a reactive
banner, not just an ambient number. Both are closed the same way: not by
special-casing pygame drawing code, but by asking, once, in one small pure
function, whether the selected entrant has a basis to know the fact at all.

