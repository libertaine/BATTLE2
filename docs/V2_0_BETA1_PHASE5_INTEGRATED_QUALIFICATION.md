# Bytefray v2.0.0-beta1 Phase 5 — Integrated Qualification

This document records Beta1 Phase 5: a qualification gate over the complete
Beta1 feature set (Phases 1–4) as one integrated product slice. It is not an
implementation phase — its job is to prove that the Beta1 already built is
internally coherent, backward-compatible, packageable, and honest about what
it supports, and to return a GO / QUALIFIED GO / NO-GO recommendation for a
separate `2.0.0-beta1` release-preparation task. See
[V2_0_BETA1_PLAN.md](V2_0_BETA1_PLAN.md),
[V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md](V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md),
[V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md](V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md),
and [V2_0_BETA1_PHASE4_REPLAY_HUD.md](V2_0_BETA1_PHASE4_REPLAY_HUD.md) for
the phases this qualifies.

## 1. Starting repository state (independently verified)

- Branch `v2.0-beta1-development`, HEAD `ea37f3cfedc3121e8bd574918e4a282572ce9fa3`
  — matches the governing task's expected HEAD exactly.
- `main` at `5593d287f95a24996bb3b105befbc625a00795db` — unchanged, and
  `git merge-base main HEAD` resolves to this same commit (an ancestor of
  the beta1 lineage, as expected).
- `v2.0-development` at `ad67a0fe0778fdc40c804618e8ec5ea8ea9cf7d3` —
  unchanged; `git merge-base v2.0-development HEAD` resolves to this same
  commit, confirming beta1 branched cleanly from the alpha-closeout point.
- `origin/v2.0-development` at `151866c6d862fec4facb78596204861b26889b61` —
  `git merge-base --is-ancestor 151866c HEAD` returns false: confirmed
  **not** an ancestor of the local beta1 lineage, untouched, unreconciled.
- Working tree: clean (`git status --porcelain` empty) at start and at
  every checkpoint during qualification.
- 12 commits between `ad67a0f` and `HEAD` (`bad448c` … `ea37f3c`), matching
  exactly the Phase 1–4 commit list the governing task named.

## 2. Re-measured Phase-5 starting baseline

Measured independently via a JUnit-XML summary (Windows terminal capture of
`pytest -q`'s final text summary line is a known display artifact — see
Phase 3/4's own reports — the JUnit counts and process exit code are
authoritative):

| Check | Result |
|---|---|
| `python -m pytest` (full, non-concurrent) | **1731 passed, 6 skipped, 0 failed** (1737 collected, 204.5s) |
| `ruff check engine client` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 70 source files |
| `mypy client/src/battle_client` | Success: no issues found in 12 source files |
| `git diff --check` | clean |

This is an **exact match** to the governing task's claimed Phase-4 final
baseline (1731/6/0) — no drift between the last Phase-4 commit and the
start of Phase 5.

## 3. Acceptance matrix (frozen before qualification)

Per capability layer, the specific claims that must hold for a GO. All were
subsequently checked; results are in §§5–9 below.

| Layer | Claim | Verified |
|---|---|---|
| Phase 1 (Ruleset foundation) | `bytefray-rules-2` resolves explicitly; v1/alpha1/alpha11 remain distinct; no aliasing | ✅ §5 |
| Phase 1 | `CORE_SIZE=8`, `CORE_BEACON_BYTE=0xCE`; Agent API v1 retained; territory/scoring/scheduler/capture unchanged | ✅ §5, §7 |
| Phase 1 | alpha11→v2 Python semantics equivalent after identity normalization | ✅ §5 |
| Phase 2 (product execution) | CLI can explicitly select v1/v2; omitted Ruleset stays v1; v2 accepts Python, rejects VM pre-execution, no partial artifacts | ✅ §6, §7 |
| Phase 2 | evaluation remains v1-only | ✅ §11 |
| Phase 3 (replay semantics) | schema stays replay v3; v2 core integrity from canonical ownership; capture/death attribution correct; v1 gets no fabricated core; N-entrant generic | ✅ §8, §12 |
| Phase 4 (replay presentation) | HUD consumes Phase-3 model with no duplicated gameplay logic; arena/HUD/footer separated; v1 clean; v2 status visible; 2-/3-entrant valid; default arena viewport `960×600`; renderer works headlessly | ✅ §9 |

## 4. Integrated diff audit (`ad67a0f`..`HEAD`)

12 commits reviewed via commit log, full diff, and `git diff --stat`
(37 files changed, +6772/−467). Every changed production file was read in
full diff form and classified:

| Capability | Files |
|---|---|
| Ruleset foundation | `engine/src/battle_engine/ruleset_policy.py`, `engine/src/battle_engine/python_runtime.py` (identity registration/core-mechanic membership sets only) |
| Runtime compatibility | `engine/src/battle_engine/match_service.py` (`RulesetRuntimeUnsupportedError`, the authoritative pre-execution check) |
| CLI product selection | `engine/src/battle_engine/cli.py`, `agent_test.py`, `tournament_cli.py`, `tournament_service.py` |
| Replay model | `client/src/battle_client/replay_status.py` (new), `client/src/battle_client/session.py` (one additive method) |
| HUD/presentation | `client/src/battle_client/hud_layout.py` (new), `client/src/battle_client/renderers/pygame_renderer.py` |
| Reference-agent cleanup | `engine/src/battle_engine/data/reference_agents/core_tracker/agent.py`, `engine/src/battle_engine/reference_agents.py` |
| Documentation/tests | `docs/*`, `AGENTS.md`, all `*_test*.py`/`test_*.py` changes |

**Findings:**

- **Accidental alpha-only assumptions**: none found. `VULNERABLE_CORE_RULESET_IDS`/`OBSERVABLE_CORE_RULESET_IDS` are finite, explicit `frozenset`s that were correctly extended (never pattern-matched) to include `BYTEFRAY_RULESET_V2_ID` alongside the pre-existing alpha entries.
- **Duplicated Ruleset IDs / stale alpha11 defaults**: none. `bytefray-rules-2` is registered under its own key in `ruleset_policy._RULESET_POLICIES`; `rules._RULESET_ALIASES` gains no entry for any of the three v2-family identities (confirmed by direct diff read, §5).
- **Hardcoded Ruleset v1 where v2 should be selectable**: none in the touched CLI surfaces — `--ruleset` was added to `run`/`agents test`/`tournament`, defaulting to `None` → v1, exactly as documented. `agents evaluate` was deliberately left with no `--ruleset` flag (§11), which is the correct disposition, not an oversight (verified by test and by direct parser inspection).
- **Product paths accidentally defaulting to v2**: none found anywhere in the diff or in the running product (every default-omitted `--ruleset` smoke in §7/§9/§10 recorded `bytefray-rules-1`).
- **VM paths that could bypass runtime validation**: none — `RulesetPolicy.unsupported_runtime_kinds` is checked once, in `NativeMatchService.run`, the single seam every production caller passes through (confirmed by direct diff read of `match_service.py`).
- **Two-entrant assumptions in new HUD/status code**: none — `get_entrant_statuses`/`calculate_layout`/`format_entrant_card_lines` all iterate over the replay's own recorded entrant list/count with no positional slot assumption (confirmed by diff read and by the live 3-entrant screenshots in §9).
- **Gameplay semantics in the renderer**: none — grep-confirmed (per Phase 4's own §8) that `pygame_renderer.py`/`hud_layout.py` import no `battle_engine.python_runtime` core-mechanics symbols; every Ruleset-specific fact flows through `battle_client.replay_status`.
- **Stale docs calling v2 hypothetical, or claiming VM support**: one found — see §17.
- **Accidental changes on `v2.0-development`**: none — that branch's tip (`ad67a0f`) is untouched; all 12 commits are on `v2.0-beta1-development` only.

## 5. Ruleset identity qualification

Re-qualified `bytefray-rules-1`, `bytefray-rules-2-alpha1`,
`bytefray-rules-2-alpha11`, and `bytefray-rules-2` via direct source read of
`ruleset_policy.py`/`python_runtime.py` plus the full pass of
`engine/tests/test_ruleset_v2.py`, `test_ruleset_v2_alpha1.py`,
`test_ruleset_v2_alpha11.py`, and
`test_ruleset_v2_promotion_equivalence.py` (all passing, unmodified this
phase, part of §2's 1731).

- All four identities are registered under distinct, explicit keys in
  `_RULESET_POLICIES`; `rules._RULESET_ALIASES` has no entry for any of the
  three v2-family identities — confirmed directly in the diff (§4) and by
  `resolve_ruleset_policy` raising `UnknownRulesetError` for anything not in
  that finite table.
- `canonical_match_id` hashes `ruleset_id` as a sibling input to
  `reproducibility`/`entrants` — confirmed by source read; no new plumbing
  needed since this was already generic (v0.10 Phase 4 heritage).
- `CORE_SIZE = 8`, `CORE_BEACON_BYTE = 0xCE` — confirmed directly in
  `engine/src/battle_engine/python_runtime.py:70,106`.
- Agent API v1 unaffected — no `AGENT_API_VERSION` change anywhere in the
  Beta1 diff; territory/scoring/scheduler/capture-timing formulas
  byte-identical to Ruleset v1 except for the additive core-capture check
  (confirmed by diff read of `python_runtime.py`, which shows only Ruleset
  *identity-membership* sets changing, not any scoring/scheduling logic).
- **alpha11 → v2 semantic equivalence**:
  `test_ruleset_v2_promotion_equivalence.py`'s corpus (Claimer vs Core
  Tracker, Hunter vs Core Tracker, Core Tracker vs Core Defender, Core
  Tracker vs Reactive Core Defender, a 3-entrant match, a wraparound core, a
  deterministic capture and non-capture case, and multiple seeds for Core
  Tracker) runs both identities on byte-identical inputs and asserts winner,
  every per-agent statistic, final arena content, final ownership, and every
  replay event are identical except for the identity fields expected to
  differ. This passed unmodified as part of §2's full run — **no unexpected
  differences**.

## 6. v1 regression wall

Full v1 golden-equivalence and characterization suites
(`test_ruleset_v1_equivalence.py` and friends) passed unmodified as part of
§2's 1731. Independently re-verified via live CLI (not just unit tests, per
the governing task's "do not assume unit tests substitute for the user
journey"):

- Direct CLI default (`bytefray run` with no `--ruleset`): `ruleset_id:
  "bytefray-rules-1"` recorded, VM match completes normally.
- `agents test` default: `--help` shows `--ruleset` defaulting to v1;
  omitted, resolves to v1 (per `test_agent_test.py`, passing).
- v1 replay load + headless playback: exact tick-by-tick score/winner
  reproduction (§10).
- v1 Replay Viewer HUD: no `Core` field on either entrant card, confirmed
  visually (§9).
- Historical persisted-result/replay reading: `resolve_result_ruleset`/
  `resolve_replay_ruleset`'s confidence-qualified compatibility matrix is
  untouched by this Beta1 diff (zero lines changed in `result_model.py`/the
  relevant sections of `replay.py`).

**No v1 gameplay diff was found or introduced.**

## 7. v2 execution qualification (native service + CLI)

Exercised real permanent-v2 Python matches directly through
`NativeMatchService` (bypassing subprocess overhead) and through the CLI,
using Claimer, Hunter, Core Tracker, Core Defender, and Reactive Core
Defender:

- **Native service, 2-entrant, no capture**: Claimer vs Hunter, distinct
  non-overlapping starts, 80 ticks — both alive at end, `Core 6-8/8`, no
  capture, `ruleset_id="bytefray-rules-2"` recorded correctly in both
  `result.json` and the replay header.
- **Native service, 2-entrant, attributed capture**: Core Tracker vs Core
  Defender (seed 3, arena 512, close starts) — Core Tracker core-captured at
  tick 112, `killer_id="B"` (Core Defender), `termination_reason=
  "core_captured"`, `Core 0/8`; Core Defender survives at `Core 8/8`. Cross-
  checked independently against the engine's own recorded
  `TerminationReason.LAST_AGENT_STANDING` result and against the Phase-3
  status model's own derivation (`battle_client.replay_status.
  get_entrant_statuses`) — both agree.
- **Native service, 3-entrant**: Core Tracker / Core Defender / Reactive
  Core Defender, widely spaced starts, 60 ticks — all three alive, one minor
  core scratch (`7/8`) on Core Tracker, correct per-entrant statuses in
  recorded order (not alphabetical/score-sorted).
- **CLI, `bytefray run`**: v2 explicit Python match (Claimer vs Hunter),
  exit 0, correct `ruleset_id`; v2 VM rejection (writer vs runner), exit 2,
  the exact documented error text, **no run directory created at all**
  (`ls` on the target path fails).
- **`agents test`**: audited (unchanged by this phase); `--ruleset` present
  and defaults to v1, per `test_agent_test.py`.
- **`bytefray tournament`**: `--ruleset` present (source read + `--help`
  grep), per-match rejection wired through `TournamentRequest.ruleset_id`;
  covered by `test_tournament_service.py`'s new cases (passing).
- **Wraparound core / multiple seeds**: covered by the promotion-equivalence
  corpus (§5) and `test_ruleset_v2.py`'s dedicated wraparound cases, all
  passing.

Result identity, replay identity, core initialization, observable-beacon
semantics, mortality, and winner eligibility all matched expectations in
every scenario above, cross-checked between the engine's own result and the
independently-derived Phase-3 status model.

## 8. VM / unsupported-runtime qualification

`engine/tests/test_ruleset_v2_runtime_compatibility.py` (part of §2's 1731)
directly covers: v2 rejects VM/VM, three-way all-VM, Python/VM and VM/Python
(distinguished from the pre-existing mixed-composition error by message
text), zero replay/result/run-directory creation on rejection, and — via
monkeypatching `Kernel` to raise on construction — **zero VM instruction
execution**. v1 VM matches and both historical alpha identities' VM-dispatch
behavior are separately confirmed unchanged in the same file.

Independently re-verified live at the CLI (§7): `bytefray run --ruleset
bytefray-rules-2` with two VM built-ins exits 2 with the documented message,
and the target replay directory never comes into existence (not merely
empty — absent, confirmed by a failing `ls`). No silent v1 fallback, no
silently-inert v2 core behavior, no partial artifact, at either the service
level or the CLI level.

## 9. HUD qualification (real rendering, SDL dummy driver)

This session has no attached interactive display. Per the governing task's
guidance, the strongest available path was used: `SDL_VIDEODRIVER=dummy` /
`SDL_AUDIODRIVER=dummy` with a genuine Pygame (real `Surface`/font
rasterization/`pygame.draw`), rendering actual `PygameRenderer._redraw()`
frames for real, engine-executed replays (not synthetic fixtures) and
saving them as PNGs, then visually inspecting each one.

| Scenario | Window | Observed |
|---|---|---|
| v1 (writer vs runner, tick 0) | 512×672 | `Ruleset bytefray-rules-1 \| runtime vm`; both cards show `Alive`, **no `Core` field**; arena unobstructed |
| v2 healthy/damaged (Claimer vs Hunter, tick 40/80) | 512×672 | `Ruleset bytefray-rules-2 \| runtime python`; `Core 7/8` and `Core 8/8` on separate cards, score/territory on their own line below life/core |
| v2 partial damage, still alive (Core Tracker vs Core Defender, tick 60/112) | 896×608 | `Core 1/8`, still green/`Alive` — damaged-but-alive is visually distinct from captured |
| v2 captured + attributed (same match, final tick 112) | 896×608 | Header shows `Winner: B  Termination: last_agent_standing`; captured card reads `CAPTURED @ T112 by B \| Core 0/8` in amber; footer shows `T112 kill: A by B`; territory tint visibly dominated by the winner (60.4% vs 39.6%, matching the printed numbers) |
| v2 three-entrant (Core Tracker / Core Defender / Reactive Core Defender, tick 40/60) | 512×672 | three non-overlapping, equal-width cards, all correctly labeled and colored, arena fully visible below |
| v2 three-entrant, narrow window | 460×520 | cards still non-overlapping; third card's name/line ellipsis-truncated as documented; footer controls truncated; territory graph still present (right at the 460px visibility threshold) |
| v1, larger window | 1200×760 | everything scales up cleanly, full controls text visible, graph panel present, no overlap |

**No visual defect found** in any scenario: no overlap between header,
cards, arena, and footer at any tested size; v1 shows no fabricated core
field; v2's damaged-but-alive vs captured states are visually and textually
distinct; capture attribution renders correctly; three-entrant layout has no
two-slot assumption. This independently reproduces Phase 4's own
self-reported qualification (§9's screenshots are of freshly-generated,
real-match replays, not Phase 4's original captures).

## 10. Replay integrated qualification

Fresh deterministic replays were generated for v1, v2 healthy, v2 damaged,
v2 captured (attributed), and v2 three-entrant (§7), each loaded via the
normal `ReplaySession`/`get_entrant_statuses` path and cross-checked against
the engine's own `NativeMatchResult`:

- Core integrity is derived from `ReplayState.owners` (reconstructed
  ownership), never from arena byte content — confirmed both by direct
  source read (§5, `python_runtime.py`'s `apply_core_capture`/
  `maintain_core_beacons` vs. `replay_status._core_status`) and by the
  passing `test_byte_content_does_not_determine_integrity` family in
  `client/tests/test_replay_status.py`.
- Attribution (`killer_id`) matched the engine's own recorded event in every
  live scenario tested (§7's Core Tracker vs Core Defender capture:
  `killer_id="B"`, matching the engine's own `TerminationReason` and the
  footer's rendered `T112 kill: A by B`).
- v1 replays received `core=None` in every case — no fabricated core.
- Historical alpha1/alpha11 interpretability is covered by
  `test_ruleset_v2_alpha1.py`/`test_ruleset_v2_alpha11.py` and
  `test_replay_status.py`'s alpha-specific integration tests, all passing
  unmodified.
- N-entrant genericity confirmed live (§7, §9's three-entrant case): status
  order matches recorded spawn order, not alphabetical or score order.

## 11. Evaluation boundary qualification

Audited `agent_evaluation.py`'s CLI parser (source read) and
`test_agent_evaluation_v2.py` (passing, part of §2): `agents evaluate` has
**no** `--ruleset` flag; `EVALUATION_RULES_COMPATIBILITY_ID =
BYTEFRAY_RULESET_ID` remains hardcoded; every evaluation cell's own
`result.json` records `ruleset_id == "bytefray-rules-1"` unconditionally,
verified per-cell, not merely at the evaluation-summary level. There is no
reachable path today where `bytefray-rules-2` is evaluated under the old
single-placement/single-order methodology. No code change was needed or
made — Beta1 correctly left this v1-only.

## 12. Designer / Agent Lab boundary

`grep -rn "ruleset" -i app/` returns **zero matches** — confirmed at current
HEAD, not merely at Phase 2's audit time (no source drift since). The
Windows frozen-build smoke (§14) independently exercised both `bytefray.exe
design` and the standalone `bytefray-agent-designer.exe`, each completing a
real startup/import cycle against an isolated data root with exit code 0 —
live confirmation the Designer still starts normally and defaults to v1
with zero Designer-side code changes required, exactly as Phase 2 recorded.

## 13. Reference-agent qualification

Claimer, Hunter, Core Defender, and Reactive Core Defender were exercised
live in §7's real matches. Core Tracker was exercised as both the offense
benchmark (capture case) and a healthy participant (3-entrant case);
`engine/tests/test_v2_alpha8_core_tracker.py`'s "self-core filtering"
section (part of §2's 1731) directly confirms: the agent's own core never
triggers a probe/assault, an external region carrying the identical beacon
byte just outside its own core still does, wraparound is respected, and
every pre-existing alpha.8/alpha.11 behavioral expectation continues to
pass unchanged. The historical Core Seeker fixture
(`test_ruleset_v2_alpha1.py` era coverage) is untouched and still passes.
No reference-agent behavior was tuned or rebalanced in this phase.

## 14. Performance / scale sanity

Not a broad research pass — bounded checks only, per the governing task.

**Match execution** (`NativeMatchService.run`, Core Tracker vs Core
Defender, arena 2048, 200 ticks, two alternating-order runs each):

| Ruleset | Time (2 runs) |
|---|---|
| v1 | 0.065s, 0.062s |
| alpha11 | 0.069s, 0.069s |
| permanent v2 | 0.072s, 0.069s |

Permanent v2 remains within noise of alpha11 (expected — they share their
behavioral implementation), and both are ~10% slower than v1 (expected —
the added core-capture check/beacon maintenance is the only extra work).
**No regression.**

**Core maintenance**: `maintain_core_beacons(self.states, self.vm)` has
exactly one call site in `python_runtime.py` (line 1096), inside the
per-tick loop, called once per tick after that tick's action blocks and
`apply_core_capture`, before scoring — confirmed by direct source read, not
inferred.

**Replay/HUD performance**: confirmed by source read (`replay_status.py`'s
own documented O(entrants×8) core-integrity bound, O(1)-relative-to-replay-
length anchor derivation) and live observation — the SDL-dummy render loop
in §9 called `get_entrant_statuses` once per rendered frame with a
precomputed `match_events` cache, exactly as `_draw_top_band` does in the
real renderer; no whole-replay rebuild or whole-arena HUD scan was observed
or is present in the reviewed code.

**Three-entrant sanity**: §7's and §9's 3-entrant matches (60 ticks, three
Python entrants) completed with no scaling pathology, elevated error rate,
or unexpected slowdown.

## 15. Wheel / source-distribution qualification

Built via the repository's normal process (`python -m build --wheel`),
producing `bytefray-1.6.0-py3-none-any.whl` (no version bump, correctly
out of scope). `tools/check_wheel.py` passed. Directly confirmed via
`zipfile -l` that both new Beta1 client modules
(`battle_client/hud_layout.py`, `battle_client/replay_status.py`) and the
updated engine modules (`ruleset_policy.py`, `python_runtime.py`, the
updated `core_tracker/agent.py`) are present in the wheel.

Installed into a fresh, isolated venv (core-only, then GUI extras added),
**executed from a working directory outside the repository** (to rule out
`sys.path` picking up the source tree's own top-level `app/` package by
accident — an initial check from inside the repo checkout did exactly that
and was caught and corrected before being trusted):

- `bytefray --version` → `Bytefray 1.6.0, Agent API v1, result schema v1,
  replay schema v3, Python 3.11.9`.
- `--help` correctly lists `--ruleset {bytefray-rules-1,bytefray-rules-2}`.
- v1-default match: exit 0, `ruleset_id == "bytefray-rules-1"`.
- Explicit v2 Python match (Claimer vs Hunter): exit 0, `ruleset_id ==
  "bytefray-rules-2"`, winner recorded.
- Explicit v2 VM match (writer vs runner): exit 2, identical error message
  to the source tree, **zero artifacts written**.
- `bytefray replay --renderer headless` against the installed v2 replay:
  correct tick-by-tick playback.
- Replay Viewer path: `battle_client.hud_layout`/`replay_status`/
  `renderers.pygame_renderer` all imported from the installed
  `site-packages` location (confirmed via `__file__`); a real frame was
  rendered end-to-end through the installed package's own
  `PygameRenderer._redraw()` under the SDL dummy driver and saved as a PNG.
- `app.replay_viewer`/`app.agent_designer` also confirmed importing from
  `site-packages`, not the source tree, once the working-directory
  shadowing issue above was corrected.

The wheel/venv were not published; build output was left on disk locally
(gitignored, not committed) for inspection rather than deleted.

sdist was not separately built — the CI process (`ci.yml`) also does not
build one; only the wheel is built and inspected there, and this
qualification followed that same normal process rather than inventing a
new one.

## 16. Windows frozen-build qualification

Toolchain present (`pyinstaller 6.22.2`, `pefile 2024.8.26`, `pygame
2.6.1`, `PySide6`) and prior project convention (`tools/build_win.ps1`,
CI's `build-windows-exe` job) makes this practical, so the full frozen
build was run via the repository's own `tools/build_win.ps1` (unmodified),
which builds all four executables and runs its own built-in GUI
import/startup smoke and `agents create` smoke against isolated data
roots, plus a residue check that no runtime data leaked into the
distributable trees. **Result: success, exit 0**, all four executables
produced:

- `dist/windows/bytefray/bytefray.exe`
- `dist/windows/bytefray-cli/bytefray-cli.exe`
- `dist/windows/bytefray-agent-designer/bytefray-agent-designer.exe`
- `dist/windows/bytefray-replay-viewer/bytefray-replay-viewer.exe`

Additional Beta1-specific checks performed directly against the frozen
executables (beyond the build script's own generic smoke):

- `bytefray.exe run` — v1 default (exit 0), explicit v2 Python match (exit
  0, correct ruleset), explicit v2 VM rejection (exit 2, identical message,
  **no artifacts written**, confirmed by a failing `ls` on the target
  directory).
- `bytefray-replay-viewer.exe <path> --renderer headless` against the
  frozen-produced v2 replay — correct tick-by-tick playback, exit 0.
- `warn-replay_viewer.txt` (PyInstaller's own missing-module report):
  grepped for `battle_client`/`hud_layout`/`replay_status` —
  **zero matches**; the 63 warnings present are all standard PyInstaller
  optional-stdlib-import noise, unrelated to Beta1.
- `.spec` files use `collect_submodules("battle_client")`, which
  enumerates every submodule (including the two new Beta1 modules)
  programmatically at build time — confirmed by source read, and the
  absence of any missing-module warning for either is the direct empirical
  proof this worked.
- Branding icons: the two dedicated GUI apps
  (`bytefray-agent-designer.exe`, `bytefray-replay-viewer.exe`) both bundle
  `_internal/assets/branding/bytefray-icon.{ico,png}` correctly (confirmed
  by direct file listing) — this is pre-existing, unmodified-by-Beta1
  behavior, not a new regression.
- One **pre-existing, non-Beta1** packaging observation: `tools/bytefray.spec`
  (the unified CLI dispatcher, which also exposes a `design`/`--pygame`
  sub-launch path) does not bundle the `assets/` tree the way the two
  dedicated GUI specs do, so `get_branding_icon_path()`'s runtime
  taskbar-icon lookup would return `None` for that one sub-launch path
  specifically (the function is documented to handle this gracefully — it
  never raises). This file is untouched by the Beta1 diff (`ad67a0f`..`HEAD`
  does not include `tools/bytefray.spec`) and is therefore **not a Beta1
  regression**; disclosed here as a pre-existing, non-blocking, cosmetic
  packaging gap outside this phase's scope to fix.

## 17. Installer disposition

Inspected, not built or run. No Inno Setup toolchain (`iscc`) is installed
in this environment, and per the governing task's explicit instruction not
to perform destructive install/upgrade/uninstall lifecycle work without a
disposable sandbox, none was attempted. Beta1's own diff does not touch
`tools/installer.iss` or any installer-related file, and no Beta1 phase
plan calls for shipping an installer as part of this beta.

**Disposition: requires separate beta1 release-prep qualification.** This
matches the governing task's explicit allowance (full installer lifecycle
qualification is not automatically required at this gate) — the eventual
RC must still receive full installer lifecycle qualification.

## 18. Linux qualification (WSL2 Ubuntu)

A configured, running WSL2 Ubuntu environment was available
(`wsl -d Ubuntu`, Python 3.12.3) and was used for a meaningful smoke,
consistent with the precedent already recorded in `CHANGELOG.md`'s 1.6.0
entry ("Independently qualified on ... Linux (WSL2 Ubuntu)"):

- Fresh isolated venv, `pip install -e ".[dev]"` — clean install.
- Full headless suite (`python -m pytest`, matching `pytest.ini`'s own
  default `-m "not gui"`): **exit 0**, zero `F`/`E` markers anywhere in the
  progress output across all 1737 collected items (the same known
  Windows/WSL terminal-capture artifact suppressed the final numeric
  summary line, but the process exit code and the complete absence of any
  failure/error marker are conclusive).
- `bytefray --version` and CLI help.
- v1 default CLI match: exit 0.
- Explicit v2 Python CLI match: exit 0, correct `ruleset_id`.
- v2 VM rejection: exit 2, identical error text, no artifacts written.
- `battle_client.replay_status` imports cleanly.
- Headless replay inspection of the Linux-produced v2 replay: correct
  tick-by-tick playback.

**No Linux-specific defect found.** This is not a publication blocker —
Beta1 is not being pushed or tagged in this task, and CI already validates
Linux per-Python-version on every push; this smoke is confirmatory, not a
substitute for that.

## 19. Documentation consistency audit

Audited README.md, ROADMAP.md, RULES.md, RULES_V2.md, COMPATIBILITY.md,
V2_0_BETA1_PLAN.md, the Phase 2/3/4 reports, FUTURE_PLANS.md, and
CHANGELOG.md for the specific contradiction classes the governing task
named (v2 called hypothetical, alpha research called open, VM support
claimed, Agent API v2 implied, territory decay implied, Beta1 phases
mismarked, Replay Viewer layout stale, multi-entrant called productized,
evaluation v2 called available).

**One contradiction found and fixed**: `README.md`'s roadmap table (the
compact version-history table under "## Roadmap") still carried a
pre-alpha-era row — `"2.x | Gameplay / Rules Research | Research boundary
— ... a separately identified Ruleset v2; no detailed design commitment
yet."` — factually superseded by the now-closed eleven-experiment alpha
program and the concrete, tested, CLI-integrated `bytefray-rules-2`
semantics this phase just re-qualified. Fixed with a narrowly-scoped edit
(new `2.0 | Ruleset v2 (Vulnerable Core) | In development ...` row
preceding the now-renamed `2.x | Further Gameplay / Rules Research` row for
what genuinely remains open), pointing to `docs/ROADMAP.md` for detail,
consistent with the table's own existing pattern for other in-progress/
completed milestones. This is the only change in this file. No other
documentation contradiction of the named classes was found: `ROADMAP.md`,
`RULES.md`, `RULES_V2.md`, `COMPATIBILITY.md`, `FUTURE_PLANS.md`, and all
four Beta1 phase reports already correctly describe alpha research as
closed, v2 as a real beta candidate identity (not hypothetical), the
Python-only VM boundary accurately, no Agent API v2, no territory decay for
2.0, and the Phase 1–4 statuses accurately. `CHANGELOG.md`'s current
`[Unreleased]`/top section is `1.6.0` (already released) — no premature
Beta1 release-notes section exists, correctly deferred to the release-prep
task per the governing task's own instruction.

## 20. Defects found and fixes made

| # | Finding | Classification | Action |
|---|---|---|---|
| 1 | `README.md` roadmap table's `2.x` row was factually stale (called Ruleset v2 an undesigned research boundary after the alpha program closed and beta1 integrated it) | Documentation contradiction (Phase 5S mandate) | Fixed — see §19 |
| 2 | `tools/bytefray.spec`'s unified dispatcher build does not bundle `assets/branding/` the way the two dedicated GUI specs do, so its `design`/`--pygame` sub-launch path's runtime window has no taskbar icon | Pre-existing (not touched by Beta1's `ad67a0f`..`HEAD` diff), cosmetic-only, handled gracefully by existing code (never raises) | Disclosed, not fixed (out of this phase's scope — not a Beta1 regression) |
| 3 | The obvious first `bytefray run --a-type <python> --b-type <python> --ruleset bytefray-rules-2` command a new user might type omits `--a-start`/`--b-start`, both defaulting to `0`; under v2 this produces overlapping cores and an immediate, correctly-computed but confusing unattributed tick-1 capture | Non-blocker (gameplay is *correct* per §3 of `V2_0_RULESET_V2_CANDIDATE.md`, which explicitly assigns non-overlapping placement to the caller/evaluation, not the Ruleset; the `--a-start`/`--b-start=0` default itself predates Beta1 and is unchanged by it) | Disclosed, not fixed — a wording/UX polish item, not a gameplay or compatibility defect |

**No release-blocking defect was found.** No scope-changing defect (one
that would require a gameplay, identity, schema, scheduler, scoring, or
Agent API change) was found.

## 21. Deferred non-blockers

- Finding #2 and #3 above.
- Frozen-build Designer/Replay-Viewer interactive keyboard-control smoke
  (`docs/MANUAL_SMOKE_TESTS.md`'s existing checklist) remains a human,
  desktop-attached task, unchanged in scope by Beta1 and not re-run here —
  this session has no interactive display, and the governing task's HUD
  qualification instructions explicitly accept the SDL-dummy path as the
  strongest available substitute (§9), which was used.
- Full installer lifecycle qualification (§17) — explicitly deferred to
  release-prep, per the governing task's own allowance.

## 22. Full regression results (reconciliation)

| Check | Result |
|---|---|
| Full `python -m pytest` (Windows, non-concurrent) | **1731 passed, 6 skipped, 0 failed** (1737 collected, 204.5s) — identical to the Phase-5 starting baseline (§2); zero test files were added or modified in Phase 5 (only qualification documentation and the one README fix) |
| `ruff check engine client` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 70 source files |
| `mypy client/src/battle_client` | Success: no issues found in 12 source files |
| `git diff --check` | clean |
| Linux headless suite (WSL2 Ubuntu, Python 3.12.3) | exit 0, no failure/error markers, 1737 collected |
| Wheel build/install smoke | clean (§15) |
| Frozen build smoke | clean (§16) |

Since Phase 5 made no engine/client source changes (only documentation),
the test count is **unchanged** from the re-measured starting baseline —
this is the expected, correct outcome for a qualification phase that found
no code-level defect.

## 23. GO / NO-GO decision

# GO for a separate `2.0.0-beta1` release-preparation and publication task.

All release-readiness criteria hold:

- **Gameplay**: permanent-v2 Python semantics match the frozen alpha11
  candidate exactly (promotion-equivalence corpus, §5); v1 is unchanged
  (§6); no unexplained alpha11 promotion drift.
- **Compatibility**: all four Ruleset identities resolve distinctly with no
  aliasing (§5); unsupported v2 runtimes fail closed with no partial
  artifact (§8); historical artifacts remain interpretable (§10);
  evaluation stays v1-only with no accidental v2 exposure (§11).
- **Product execution**: source CLI, installed-wheel CLI, and
  frozen-executable CLI all agree (§15, §16); legacy v1 default is
  preserved; explicit v2 works; invalid v2 fails cleanly at every layer
  tested (service, source CLI, installed wheel, frozen exe, and on Linux).
- **Replay**: canonical replay state is correct and derived from ownership,
  never byte content (§10); v2 core status is correct including
  attribution; v1 status is unchanged; schema is unchanged (replay v3
  throughout).
- **Presentation**: HUD is functional and defect-free across v1, v2
  healthy/damaged/captured, and 2-/3-entrant layouts at multiple window
  sizes (§9); arena stays unobstructed; no resize/layout defect found.
- **Quality**: full test suite clean on Windows and Linux; Ruff clean;
  mypy clean on both packages; wheel and frozen-build paths both sound; no
  known release-blocking defect (§20).

## 24. Exact remaining release-prep gates

1. **Version/release metadata**: bump `pyproject.toml`'s version, decide
   the `2.0.0-beta1` version string/tag policy, and write the actual
   CHANGELOG `[Unreleased]`/`2.0.0-beta1` section — deliberately not done
   in this qualification phase.
2. **Installer lifecycle qualification** (§17) — build/install/upgrade/
   uninstall qualification in a disposable sandbox, using an Inno Setup
   toolchain not present in this environment.
3. **ROADMAP.md "shipped" update** — explicitly deferred; do not mark
   `2.0.0-beta1` as released until the release-prep task actually
   publishes it.
4. **Interactive desktop smoke** (`docs/MANUAL_SMOKE_TESTS.md`'s existing
   human checklist) — the SDL-dummy path used here (§9) is the strongest
   available *automated* substitute, not a replacement for a human at a
   real keyboard/display, which remains good practice before a tagged
   release.
5. Merge/tag/publish/push and origin-history reconciliation — explicitly
   out of scope for both this phase and the recommended next task's early
   steps; handle deliberately and separately when release-prep actually
   publishes.

## 25. Recommended next prompt

A separate, explicitly scoped **`2.0.0-beta1` Release Preparation,
Merge/Tag/Build/Publish** task — not another Beta1 feature or
qualification phase.
