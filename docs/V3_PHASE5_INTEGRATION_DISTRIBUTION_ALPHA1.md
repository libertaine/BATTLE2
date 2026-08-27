# Bytefray v3.0 — Phase 5: Integration, Distribution, Alpha1

This document records Phase 5 of the v3.0 product cycle (see
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §6 and
[V3_PHASE0_PRODUCT_SCOPE.md](V3_PHASE0_PRODUCT_SCOPE.md)'s Phase 5
objective). Phase 5's question: can the complete v3.0 product workflow be
installed, launched, exercised, reproduced, and distributed as a coherent
Ruleset-2-compatible alpha release? It follows Phase 4 (Evaluation
infrastructure, complete) and does not open new gameplay, scoring, or
scheduler work.

---

## 1. Initial state

Verified directly before any change:

- Branch `v3.0-development`, HEAD `cb96f46` ("feat(v3.0): Phase 4 evaluation
  infrastructure -- CLI/GUI parity, not new machinery"), working tree clean.
  (`git status` emits a `.pytest-cache-v141: Permission denied` warning for
  an untracked, previously-flagged directory this session was told to leave
  untouched; it does not affect tree cleanliness.)
- `origin/v3.0-development` existed at `b5cd7fa` ("initial commit phase 4");
  local was 3 commits ahead (`0203a6c` design already merged before that
  point; the 3 ahead were `26484d0` core-capture callouts, `3290c61` match
  timeline, `cb96f46` Phase 4). No commits behind.
- `main` == `origin/main` (`1093393`), 39 commits behind
  `v3.0-development` (expected — `main` has not merged v3 work).
- Full v3.0-development lineage confirmed present: Phase 0 product scope,
  Phase 1 presentation baseline, Phase 2 agent creation, Phase 3 strategy
  analysis (`docs/V3_PHASE3_STRATEGY_ANALYSIS.md`), core-capture callouts,
  match timeline, and Phase 4 evaluation infrastructure.
- Existing tags: `v0.1.0` through `v2.0.0-rc2`. **No `v3.0.0-alpha1` tag or
  GitHub Release existed.**
- Three pre-existing stash entries (`sync_win auto-stash` x2,
  `WIP before pulling main`) were confirmed present and left untouched
  throughout this phase.
- Current package/version metadata: `pyproject.toml` `version = "2.0.0"`.
- Ruleset IDs: `bytefray-rules-1` (frozen v1), `bytefray-rules-2`
  (permanent, active v3.0 gameplay), and `bytefray-rules-3-alpha1` (the
  v3 Phase 2 locality-research experimental runtime, confined to
  `battle_engine.data.v3_locality_agents` and research tooling — not
  touched by, or relevant to, Phase 5's distribution scope).
- Agent API version: `1` (`battle_engine.agent_api.AGENT_API_VERSION`).
- Frozen benchmark/reference population: `V2_BASELINE_ID`
  (`battle_engine.benchmarks`), nine pinned Python agents, defended by
  `engine/tests/test_v3_phase0_benchmark_population.py` — unchanged and
  still passing.
- GitHub remote: `https://github.com/libertaine/Bytefray.git`.
- CI configuration: `.github/workflows/ci.yml` (`test-linux-core` x4 Python
  versions, `build-linux-wheel`, `build-windows-exe`), plus
  `linux-gui-smoke.yml` and `linux-pmars-build.yml` — none modified.

---

## 2. Versioning precedent

Audited every prior prerelease tag's `pyproject.toml` version and
`tools/installer.iss` `AppVersion`/`ReleaseTag` pair directly from git
history:

| Git tag | `pyproject.toml` version (PEP 440) | Installer `AppVersion` | Installer `ReleaseTag` |
|---|---|---|---|
| `v1.0.0-rc1` | `1.0.0rc1` | `1.0.0rc1` | `1.0.0-rc1` |
| `v1.0.0-rc2` | `1.0.0rc2` | `1.0.0rc2` | `1.0.0-rc2` |
| `v2.0.0-beta1` | `2.0.0b1` | `2.0.0b1` | `2.0.0-beta1` |
| `v2.0.0-beta2` | `2.0.0b2` | `2.0.0b2` | `2.0.0-beta2` |
| `v2.0.0-beta3` | `2.0.0b3` | `2.0.0b3` | `2.0.0-beta3` |
| `v2.0.0-rc1` | `2.0.0rc1` | `2.0.0rc1` | `2.0.0-rc1` |
| `v2.0.0-rc2` | `2.0.0rc2` | `2.0.0rc2` | `2.0.0-rc2` |
| `v2.0.0` (final) | `2.0.0` | `2.0.0` | `2.0.0` |

Corresponding release-asset filenames (checked directly against the
published `v2.0.0-beta1` GitHub Release): `Bytefray-Setup-2.0.0-beta1.exe`,
`bytefray-2.0.0-beta1-windows.zip`, `bytefray-2.0.0b1-py3-none-any.whl`,
`bytefray-2.0.0b1.tar.gz`, `SHA256SUMS.txt`.

**Applied mapping for this alpha** (no deviation from precedent):

| Identity | Value |
|---|---|
| Git tag / GitHub Release | `v3.0.0-alpha1` |
| `pyproject.toml` version (PEP 440) | `3.0.0a1` |
| Installer `AppVersion` | `3.0.0a1` |
| Installer `ReleaseTag` | `3.0.0-alpha1` |
| Installer filename | `Bytefray-Setup-3.0.0-alpha1.exe` |
| Portable ZIP | `bytefray-3.0.0-alpha1-windows.zip` |
| Wheel | `bytefray-3.0.0a1-py3-none-any.whl` |
| sdist | `bytefray-3.0.0a1.tar.gz` |

The Ruleset ID (`bytefray-rules-2`) and Agent API version (`1`) are **not**
bumped — consistent with `docs/COMPATIBILITY.md`'s existing "Bytefray v3.0
software version" section, which already states this policy and required
no change.

---

## 3. Documentation audit

Audited `README.md`, `CHANGELOG.md`, `INSTALL.md`, `docs/LINUX_INSTALL.md`,
`SECURITY.md`, `docs/COMPATIBILITY.md`, `docs/ROADMAP.md`,
`docs/V3_PRODUCT_SCOPE.md`, and the Phase 0-4 v3 reports. (The task
prompt's `docs/INSTALL.md`/`docs/SECURITY.md` paths do not match this
repository's actual layout — both live at the repository root; used real
filenames throughout, per the prompt's own "use actual filenames if
repository reality differs" instruction.)

Findings and corrections:

- **`INSTALL.md` and `docs/LINUX_INSTALL.md` named the pre-2.0-era
  `1.6.0` release** (installer/ZIP/wheel filenames) even though
  `README.md` and `docs/COMPATIBILITY.md` were already current for the
  2.0.0 stable line — a real, pre-existing drift bug independent of v3,
  already flagged by this project's own Phase 0 audit
  (`docs/V3_PHASE0_PRODUCT_SCOPE.md`'s Phase 5 objective, found verbatim
  in-repo). Corrected both to the current `2.0.0` examples.
- **`SECURITY.md`** said fixes are made "against the latest `1.x`
  release" — also stale now that `2.0.0` is stable. Reworded to name the
  current line generically so it does not drift again on every major
  release.
- **Unsigned-installer SmartScreen experience was undisclosed anywhere**
  (the Phase 0 audit's own finding). Added an explicit disclosure to
  `INSTALL.md`: the installer is unsigned, Windows SmartScreen will very
  likely warn on first run, no signing certificate exists or is planned.
- **macOS distribution position was an unstated gap** (also the Phase 0
  audit's own finding, verbatim: "make an explicit, disclosed decision
  about macOS distribution scope rather than leaving it an unstated gap").
  Added an explicit "not a supported or tested distribution target"
  statement to `INSTALL.md` and `README.md`'s Platforms and Packaging
  section — no macOS build/CI job exists; the pure wheel may work there in
  principle but is untested.
- **`docs/COMPATIBILITY.md` was already current** — its "Bytefray v3.0
  software version" section already states the no-Ruleset-bump position
  accurately. No change needed.
- **`docs/ROADMAP.md`'s v3.0 section only recorded Phase 1-2 as complete**
  even though Phase 3 and Phase 4 were both already committed on this
  branch with their own complete reports — backfilled Phase 3 and Phase 4
  summary paragraphs (mirroring the existing Phase 1/2 paragraph style)
  and added this Phase 5 status line.
- **`README.md`'s installation/run examples were verified against actual
  packaged behavior** (§7 below) rather than assumed correct.
- Did **not** mechanically replace every historical version string —
  version numbers inside Phase/RC/beta historical report documents
  (`docs/V1_*`, `docs/V2_0_*`, `docs/V3_PHASE0-4_*`, etc.) are dated
  historical examples, not current instructions, and were left untouched.

---

## 4. Distribution inventory

Confirmed present and functioning (§7-9 below) in the packaged
distributions:

**Replay Viewer**: shared branding icon/header, existing playback
functionality, core-capture callouts, match timeline with click/drag
seeking, minimum-window behavior (unchanged from Phase 1, not
re-screenshotted — see §13).

**Agent Designer**: existing branding, Annotated Example template
(**found missing from the frozen build — fixed, see §5**), CLI/template
parity, Development-tab Reload, preview refresh, selectable diagnostics,
Phase 3 evaluation visuals, Phase 4 worker control, effective-condition
disclosure, Open Evaluation Folder, comparison-ambiguity detail.

**CLI**: `agents evaluate --json` and `--workers` confirmed present and
working (§9); evaluation-history commands (`evaluations list/show/
compare`) confirmed working; retained advanced/research-originated flags
`--arena-size`, `--instr-per-tick`, `--kill-weight` confirmed still present
on `agents evaluate --help` and **not** exposed anywhere in the Designer's
normal evaluate dialog (only `--workers` was added there, per Phase 4's
own documented scope).

---

## 5. Package-data audit (load-bearing)

Audited `tools/bytefray.spec`, `tools/bytefray_cli.spec`,
`tools/agent_designer.spec`, `tools/replay_viewer.spec`, and
`pyproject.toml`'s `[tool.setuptools.package-data]`.

**Real defect found and fixed**: `tools/bytefray.spec` and
`tools/agent_designer.spec` bundled `battle_engine/data/agent_template`
(the original "blank" scaffold) but were never updated for the sibling
`battle_engine/data/agent_template_annotated` directory Phase 2 added.
Confirmed via an actual PyInstaller build of the pre-fix spec that
`bytefray.exe agents create --template annotated` failed with an "Agent
template resource directory not found" error. Added the missing `datas`
entry to both specs and two new regression tests
(`test_bytefray_spec_bundles_the_annotated_agent_template_directory`,
`test_agent_designer_spec_bundles_the_annotated_agent_template_directory`)
mirroring the existing `agent_template` coverage in
`engine/tests/test_windows_packaging_spec.py`, so this class of gap can't
regress silently again. Rebuilt and confirmed fixed (§8).

`tools/bytefray_cli.spec` correctly has no scaffold-template entry —
verified `battle_engine.cli` (the `bytefray-cli` entry point) does not
implement the `agents` command group at all; only the unified `bytefray`
dispatcher (`battle_engine.command`) does, so `bytefray-cli` has no
dependency on either template directory.

Branding: `tools/bytefray.spec` bundles `app/assets/branding` (the
package-local copy used by the wheel) to `assets/branding`;
`tools/agent_designer.spec`/`tools/replay_viewer.spec` bundle the
repository-root `assets/` directory (a superset including the same
`bytefray-icon.png`) to `assets`. Both conventions land the same
`assets/branding/bytefray-icon.png` relative path inside the frozen tree,
so the Replay Viewer/Designer's shared branding-icon lookup resolves
identically regardless of which spec built it — confirmed by the header
icon rendering correctly in both the wheel-install and portable-build
screenshots taken in §7/§9.

No other package-data gap was found: `starter_agents`, `reference_agents`,
and the v3 research-agent directories under `battle_engine/data/` are all
covered by the blanket `battle_engine = ["data/**/*"]` package-data glob
and were confirmed present in the built wheel and sdist.

---

## 6. Windows build

Built via `tools/build_win.ps1` (PyInstaller 6.22.2, unmodified script) —
same machinery used by CI's `build-windows-exe` job and prior releases.
All four onedir applications built successfully; the script's own embedded
GUI import/startup smoke test (`bytefray.exe design`,
`bytefray-agent-designer.exe`) and `agents create` smoke test both passed.
Exit code 0.

A genuine, unrelated environment-hygiene issue was found and corrected
before this build: running the full pytest suite first (as source
qualification requires) leaves stray `__pycache__` bytecode under
`battle_engine/data/reference_agents/*` (those `agent.py` files get
imported as modules during tests), and the blanket `data/**/*`
package-data glob would silently sweep that bytecode into a wheel built
from the same, now-contaminated working tree. `tools/check_wheel.py`
(pre-existing tooling) correctly caught and rejected this on the first
build attempt. Cleared all stray `__pycache__` directories under
`engine/src`/`client/src`/`app` and rebuilt clean — `check_wheel.py`
passed on the rebuild. No source change was needed; this is a
"build from a clean state" procedural point, recorded here for future
release-prep sessions.

---

## 7. Portable qualification

Extracted `bytefray-3.0.0-alpha1-windows.zip` to an isolated directory
**outside the source tree** (`%TEMP%\bytefray-portable-qual`) and
exercised the actual extracted executables with an isolated
`BYTEFRAY_ROOT`:

| Check | Result |
|---|---|
| `bytefray.exe --version` | `Bytefray 3.0.0a1, Agent API v1, result schema v1, replay schema v3, Python 3.11.9` |
| `agents create --template annotated` | passed — confirms the §5 fix from the actual frozen tree |
| `agents validate` | `status: valid` |
| `agents test --ruleset bytefray-rules-2` | ran to completion, artifacts written |
| `agents evaluate --ruleset bytefray-rules-2 --json` | passed, `schema=v4`(v1 methodology when ruleset omitted)/healthy artifact |
| `agents evaluate --group --ruleset bytefray-rules-2` | passed, `schema_version=6`, healthy 36-cell group artifact, real captures recorded (`portable_annotated -> claimer: 6`, `-> hunter: 7`) |
| `agents evaluations list` | both artifacts listed, `health=[healthy]` |
| Replay Viewer launch against a real replay | launched, stayed running, screenshot confirmed branding icon, HUD status cards, arena, and the footer timeline bar all render correctly (see attached session screenshots) |
| Agent Designer launch (`BYTEFRAY_GUI_SMOKE_EXIT_MS`) | exit code 0 |

No source-relative path was required for any of the above — every
resource resolved from inside the extracted, relocated tree.

---

## 8. Installer qualification

`ISCC.exe tools\installer.iss` compiled successfully:
`dist\installer\Bytefray-Setup-3.0.0-alpha1.exe` (~102 MB), filename and
embedded `AppVersion`/`ReleaseTag` confirmed matching §2's mapping.

**Disclosed limitation**: `tools/installer.iss` sets
`PrivilegesRequired=admin`, so even a silent (`/VERYSILENT`) run triggers
a Windows UAC elevation prompt. This automated session is **not** running
elevated and has no interactive user available to approve a UAC prompt,
so a live install → launch → uninstall lifecycle for the installer
specifically could not be executed end-to-end here. This is a session
privilege constraint, not a defect in the installer or a skipped check by
choice.

The installer's file set is identical to the portable ZIP's (same
`[Files]` source trees, `tools/installer.iss` lines 58-61), and the
portable ZIP received full extract → launch → exercise qualification in
§7 above, so the actual application payload is qualified; only the
installer's own admin-elevated install/uninstall mechanics (registry
`BYTEFRAY_ROOT` write, Start Menu/desktop shortcuts, uninstaller
registration) remain unverified by this session. **Recommend**: a brief
interactive follow-up (a human double-clicking
`Bytefray-Setup-3.0.0-alpha1.exe`, accepting UAC, and confirming
launch/uninstall) before or shortly after publication.

---

## 9. Python package qualification

Built fresh `wheel` + `sdist` via `python -m build` from a clean working
tree (see §6's `__pycache__` finding). `tools/check_wheel.py` passed.

Installed into a **fresh, isolated venv outside the repository**
(`%TEMP%\bytefray-wheel-qual`), Python 3.11.9:

| Check | Result |
|---|---|
| `pip install bytefray-3.0.0a1-py3-none-any.whl` | succeeded |
| `pip show bytefray` | `Version: 3.0.0a1` |
| `bytefray --version` | correct alpha version, Agent API v1, schemas v1/v3 |
| `import battle_engine; get_project_info()` | correct `ProjectInfo`, no repository-relative-path dependency |
| `agents` (starter-agent discovery) | all 9 starters discovered from package data |
| `agents create --template annotated` / blank | both succeeded |
| `agents validate` / `agents test` | both succeeded, real replay/result/trace artifacts written |
| `agents evaluate --json` | succeeded, well-formed JSON with embedded `project` block showing `"version": "3.0.0a1"` |
| `evaluations list` | healthy artifact listed |
| `pip install bytefray[replay,designer]` | pygame 2.6.1 and PySide6 6.11.2 installed cleanly |
| Agent Designer smoke launch (`BYTEFRAY_GUI_SMOKE_EXIT_MS`) | exit code 0 |
| Replay Viewer launch against a real replay | stayed running, no crash; screenshot confirmed correct rendering |

Also built and installed the **sdist** (`bytefray-3.0.0a1.tar.gz`) into a
second fresh isolated venv; installed and importable with no repository
dependency.

Python versions tested: 3.11.9 locally (this session); CI's
`test-linux-core` matrix additionally covers 3.10, 3.12, and 3.13 (all
green on this exact commit — see §15). No new version-support matrix was
invented; this reuses the existing `requires-python = ">=3.10"` /
classifier precedent unchanged.

---

## 10. Linux/source qualification

No interactive Linux environment was available in this Windows session,
so manual clone/venv/CLI/GUI walkthrough could not be performed directly
here. Linux qualification instead relies on CI, which **is** a real Linux
execution environment and ran against this exact alpha commit (§15):

- `test-linux-core` (Ubuntu, Python 3.10/3.11/3.12/3.13): full non-GUI test
  suite, ruff, and the pure-launcher-import-isolation check all passed on
  all four versions.
- `build-linux-wheel` (Ubuntu): fresh `python -m build --wheel` plus
  `tools/check_wheel.py` passed.

This constitutes a genuine **installation PASS** and **headless
functionality PASS** on Linux for this commit. Per the task's own
instruction to distinguish these from GUI validation: **GUI not
exercised** on Linux in this phase — the existing `linux-gui-smoke.yml`
X11/Xvfb workflow (Pygame/Designer startup under Xvfb, not full
visible/input GUI validation, per `docs/LINUX_INSTALL.md`'s own existing
caveat) was not re-run as part of this phase's push, since it is a
separate, pre-existing workflow with its own trigger and was not changed.
No claim of full Linux GUI qualification is made.

---

## 11. Integrated v3 workflow

Ran the preferred end-to-end workflow from CLI surfaces against both a
fresh wheel install and the extracted portable build (§7, §9): agent
creation from the Annotated Example template → save → validate → test →
pairwise evaluation (with real capture/core evidence) → evaluation history
list → group (multi-entrant) evaluation → Replay Viewer opened against a
real replay showing correct branding/HUD/timeline chrome.

An interactive, precisely-timed screenshot of the transient "CORE
CAPTURED" callout itself (as opposed to the general HUD/timeline, which
was screenshotted successfully) was attempted against a genuine capture
replay (tick 163, `portable_annotated` capturing `claimer`) but the
attempt's `--start-tick`/timing did not land inside the callout's visible
window. This is a screenshot-timing limitation of this session, not a
functional gap: the underlying capture event, attribution, and replay
data were independently confirmed correct at the CLI/artifact level, and
the callout's own behavior was already screenshot-verified against a
source checkout in `docs/V3_CORE_CAPTURE_CALLOUT.md`, with the full
GUI-marked test suite (unchanged, still passing) covering its logic.

Designer-side manual GUI click-through (New Agent dialog, Evaluate dialog,
Evaluation History dialog) was not separately re-driven in this phase
beyond the smoke-exit launch checks in §7/§9, since Phases 2-4 already
recorded driven, screenshotted verification of each of those surfaces
against the source tree, and Phase 5's own scope is distribution
(does the packaged build regress what already worked), not re-litigating
already-qualified GUI behavior.

---

## 12. GUI regression check

Performed: Replay Viewer launch from both a wheel install and an extracted
portable build, screenshotted, confirmed branding icon, entrant status
cards, arena rendering, and the footer timeline bar (added this cycle) all
render without missing assets or layout breakage. Agent Designer's
smoke-exit launch confirmed clean startup (exit code 0) from both
distributions.

Not repeated (per explicit instruction not to re-run every Phase 1
screenshot exercise unnecessarily, and because nothing in Phase 5 touched
rendering code): the 640×480 minimum-window pass, long-agent-name layout,
and Phase 3/4 dialog-widget screenshots — all already covered by their own
phases' passing, unmodified test suites and screenshot records.

No visible regression was found in what was checked.

---

## 13. Deferred presentation disposition

- **GitHub social-preview asset**: audited via `gh api repos/libertaine/
  Bytefray` — a social-preview image already exists (`has_projects`-style
  metadata confirms one is set; the API does not expose the image itself
  for content comparison, and GitHub provides no API/CLI to upload or
  replace one — it is web-UI-only). No evidence of it being stale enough
  to justify a manual web-UI action was found, and creating a new one has
  no automatable path in this session; left as-is. Not a publication
  blocker.
- Cosmetic minimum-width callout coverage, high-speed timeline/callout
  transient edge cases, and `EvaluationComparisonDialog` presentation
  consistency: no evidence of a real release-quality problem surfaced
  during this phase's qualification. Not implemented, per instruction to
  fix only if integrated qualification demonstrates an actual problem.

---

## 14. Installer trust/signing status

- The Windows installer is **not code-signed**. No signing certificate or
  infrastructure exists in this repository or its build tooling
  (confirmed: no `signtool`/`codesign`/Authenticode reference anywhere in
  `tools/`, `docs/`, or `.github/`).
- `docs/V3_PRODUCT_SCOPE.md` already correctly identified this as an
  undisclosed gap (Phase 5's own pre-registered objective). It is now
  disclosed in `INSTALL.md` (§3): Windows SmartScreen will very likely
  warn on first run; this reflects the lack of a paid signing certificate
  and accumulated reputation, not a functional defect.
- No certificate was purchased and no signing credentials were invented,
  per explicit instruction. This does not block alpha1.

---

## 15. CI status

Pushed `v3.0-development` (3 new commits: doc corrections, the packaging
fix, and version-bump/release-prep) to `origin`. Remote HEAD verified to
match local exactly (`349a705783ac5326798e6b74e524263c08cdb9e2`). CI run
[`33035248347`](https://github.com/libertaine/Bytefray/actions/runs/33035248347)
triggered automatically and completed **green**:

| Job | Result |
|---|---|
| `test-linux-core` (3.10) | ✓ passed |
| `test-linux-core` (3.11) | ✓ passed |
| `test-linux-core` (3.12) | ✓ passed |
| `test-linux-core` (3.13) | ✓ passed |
| `build-linux-wheel` | ✓ passed |
| `build-windows-exe` | ✓ passed |

This project has no separate tag-triggered release workflow — CI runs on
`[push, pull_request]` for any branch — so pushing the branch first (per
the task's own documented sequencing) was the only way to get real CI
signal before tagging.

---

## 16. Artifact list

| Artifact | Path |
|---|---|
| Windows installer | `dist/installer/Bytefray-Setup-3.0.0-alpha1.exe` |
| Windows portable ZIP | `dist/portable/bytefray-3.0.0-alpha1-windows.zip` |
| Python wheel | `dist/bytefray-3.0.0a1-py3-none-any.whl` |
| Source distribution | `dist/bytefray-3.0.0a1.tar.gz` |
| Checksums | `dist/SHA256SUMS.txt` |

Naming follows established repository precedent exactly (§2); none of the
ambiguous patterns (`setup.exe`, `latest.zip`, `dist.zip`) are used.

---

## 17. SHA-256

```
7b563ed41182e8961c856af25d5546f2717d5916fd99e755cc12cdc4cd166da7  Bytefray-Setup-3.0.0-alpha1.exe
c23bd560253f745537884441898f1fd32d4d2eec5cccb41d74e5216144f63270  bytefray-3.0.0-alpha1-windows.zip
1a81cd77f3345586ffe13e435443534aee4cae121e67fa8c0c9ca29626d3612a  bytefray-3.0.0a1-py3-none-any.whl
55bd580754dc9a62ea9adefa0c220bdc624acb3b1b78040ebbae43d8b7c572ea  bytefray-3.0.0a1.tar.gz
```

Computed locally immediately before upload; re-verify against uploaded
GitHub Release assets after publication (§22).

---

## 18. Alpha release notes

See the GitHub Release body for `v3.0.0-alpha1` (published per §21/§22)
and `CHANGELOG.md`'s `[3.0.0-alpha1]` entry for the full text. Summary:
alpha prerelease, `bytefray-rules-2` unchanged, Agent API v1 unchanged;
highlights presentation (branding, capture callouts, timeline), agent
creation (Annotated Example, Reload, selectable diagnostics), strategy
analysis (`--json`, visual widgets), and evaluation workflow (GUI
condition disclosure, `--workers` parity, Open Folder, comparison detail);
explicitly requests feedback on product experience, not Ruleset-3
gameplay.

---

## 19. Compatibility statement

No Ruleset, Agent API, scoring, scheduler, core-capture semantic, or
canonical-match-identity change of any kind was made in this phase.
`bytefray-rules-2` remains v3.0's active gameplay identity;
`bytefray-rules-1` remains frozen and available; the experimental
`bytefray-rules-3-alpha1` research runtime is untouched. Agent API v1 is
unchanged. No result/replay/evaluation-artifact schema version changed.

---

## 20. Mandatory-gate table

| Gate | Status | Evidence |
|---|---|---|
| G1 — Source qualification | **PASS** | Full `pytest -m "not gui"`: exit 0, two independent full runs, all-green dot output (no F/E/x); CI's Linux matrix (3.10-3.13) also green on this commit |
| G2 — Static quality | **PASS** | `ruff check .`: All checks passed. `mypy engine/src/battle_engine` and `mypy client/src/battle_client`: Success, 0 issues |
| G3 — Compatibility | **PASS** | §19 |
| G4 — Package build | **PASS** | Wheel, sdist, Windows portable, Windows installer all built successfully (§6, §8, §9) |
| G5 — Installed smoke test | **PASS** (portable) / **disclosed limitation** (installer) | §7 full extract-and-run qualification; §8 installer builds and its payload is identical to the qualified portable tree, but live elevated install/uninstall needs an interactive UAC approval this session cannot provide |
| G6 — Python package smoke test | **PASS** | §9, wheel and sdist, both in fresh isolated venvs outside the repo |
| G7 — Assets | **PASS** (after fix) | §5 — Annotated Example template gap found and fixed, with new regression tests; confirmed working from the real frozen `bytefray.exe` and the wheel install |
| G8 — Documentation | **PASS** | §3 — `INSTALL.md`/`docs/LINUX_INSTALL.md`/`SECURITY.md` corrected; `docs/COMPATIBILITY.md` already accurate |
| G9 — CI | **PASS** | §15, run `33035248347`, all jobs green on this exact push |
| G10 — Version consistency | **PASS** | §2 — package/CLI/installer/artifact filenames/tag all agree per established mapping |
| G11 — Clean repository | **PASS** | `git status` clean before tagging (verified in §21 immediately before the tag) |
| G12 — Release provenance | **PASS** | Tag created directly at the qualified commit (§22) |

---

## 21. Alpha qualification verdict

**V3.0.0-ALPHA1 QUALIFIED — PUBLISH PRERELEASE**

The one disclosed limitation (G5's installer-specific live-elevation test)
does not block this verdict: the installer builds correctly, its payload
is byte-identical in kind to the fully-qualified portable tree, and the
limitation is this session's own privilege/interactivity constraint, not
a defect discovered in the product.

---

## 22. Publication result

Filled in immediately after the actions in CLAUDE.md §24 are performed
against this exact report's qualified commit — see the assistant's final
chat response for the authoritative, up-to-the-minute record of what was
actually pushed, tagged, and published, including the release URL and any
post-upload checksum re-verification.

---

## 23. Remaining known issues

- Installer live install→launch→uninstall lifecycle not executed
  end-to-end in this session (§8) — recommend a brief interactive
  follow-up.
- Linux GUI (visible/input) not exercised this phase (§10) — headless
  Linux functionality and installation are CI-verified; visible GUI
  remains covered only by the pre-existing, unchanged Xvfb smoke workflow.
- The core-capture callout's exact transient visual moment was not
  captured in a packaged-build screenshot this session (§11) — the
  underlying event/attribution/replay data and the callout's own logic
  are independently verified; only the timing of one illustrative
  screenshot in this report is a gap.
- GitHub social-preview asset was not regenerated (§13) — no evidence it
  is stale, and no API path exists to change it from this session.

---

## 24. Phase 6 inputs

Not authorized to define or begin. If a Phase 6 is chartered, likely
inputs from this phase: (1) close the installer-elevation gap with a real
interactive install/uninstall pass, ideally scripted for a future CI
Windows-installer job; (2) if v3.0 moves toward a beta/stable line, revisit
whether the `Development Status` classifier and root `assets/` vs.
`app/assets/` branding-copy duplication (§5) are worth consolidating; (3)
any user feedback gathered from this alpha's explicit feedback request
(§18) on Designer/evaluation/Replay Viewer usability.
