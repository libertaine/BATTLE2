# Bytefray v3.0 — Phase 6: Release Candidate Qualification (v3.0.0-rc1)

This document records Phase 6 of the v3.0 product cycle (see
[V3_PRODUCT_SCOPE.md](V3_PRODUCT_SCOPE.md) §6's Phase 6 objective): integrate
Phases 1-5, run full qualification, and decide whether to cut a release
candidate. This is a qualification task, not a new feature phase — v3.0 is
treated as **feature-complete** as of this phase. Fix release-blocking
defects only; do not enlarge v3.0.

---

## 1. Initial state

Verified directly before any change:

- Branch `v3.0-development`, HEAD `82fb818aa5143323e6c290532c96842e20b870c7`
  ("docs: refresh README for Bytefray v3.0"), working tree clean.
  `git status` emits the known `.pytest-cache-v141: Permission denied`
  warning for an untracked, previously-flagged directory this repo's own
  history says to leave untouched; it does not affect tree cleanliness.
- `origin/v3.0-development` identical to HEAD (`82fb818a`); branch up to
  date, nothing ahead or behind.
- `main` == `origin/main` (`1093393b`) and equals
  `git merge-base main v3.0-development` exactly — `main` has received
  **zero** commits from the entire v3.0 line (Phase 0 through alpha2), not
  just RC1. This is the direct, current-repository evidence for §24's merge
  precedent question (see §6 below).
- `pyproject.toml` version at HEAD: `3.0.0a2`.
- Tags: `v3.0.0-alpha1` (annotated, object `7b47c15d`, commit `1c9b035f`)
  and `v3.0.0-alpha2` (annotated, object `f176f2de`, commit `cb12adf8`).
  `v3.0.0-rc1` did not exist as a local tag, a remote tag, or a GitHub
  Release before this phase.
- Latest GitHub prereleases: `v3.0.0-alpha2` (2026-08-27) is the most recent
  prerelease; `v2.0.0` remains the "Latest" stable release. No open or
  closed GitHub issues exist on the repository at all.
- CI (`.github/workflows/ci.yml`) was already green on this exact HEAD
  commit before any RC work began (run `33120351236`), plus
  `linux-gui-smoke.yml` and `linux-pmars-build.yml`, unmodified.
- Existing release/build scripts confirmed unchanged from alpha1/alpha2:
  `tools/build_win.ps1`, `tools/installer.iss`, `tools/check_wheel.py`.
- Three pre-existing stash entries (`sync_win auto-stash` x2,
  `WIP before pulling main`) confirmed present and left untouched
  throughout this phase — none created, applied, or dropped.
- Inno Setup 6 confirmed present at its known per-user location
  (`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`), not on `PATH` and not
  under `Program Files` — consistent with every prior v3.0 release.
- No existing Bytefray installation was present on this machine (checked
  both registry uninstall keys and common install paths), so RC1's
  installer qualification is a fresh install, not an upgrade.

---

## 2. Alpha feedback state

Checked via this project's normal GitHub tooling (`gh`):

- **Issues**: zero open, zero closed, of any kind. No Alpha1/Alpha2 bug
  report exists.
- **Releases**: `v3.0.0-alpha2`'s GitHub Release has no reactions and the
  repository has GitHub Discussions **disabled**, so no discussion-based
  feedback channel exists either.
- **Pull requests**: one open, unrelated PR (`v2.0-development` →
  presumably `main`, opened 2026-08-19, predates and is unrelated to v3.0).
  No v3.0-related PR activity.

This **agrees with** the owner's report: Alpha2 has behaved normally with
no known functional defects and no user issue reports. Classification: **no
issue** — there is no public evidence of any release blocker, "should fix"
item, or post-v3.0 deferral to extract from feedback. No work was
manufactured to compensate for the absence of feedback.

---

## 3. Feature-freeze confirmation

Confirmed present and unmodified from alpha2 (Starters, Agent Development
Ruleset selector/default, pairwise evaluation Ruleset selector/preset
interaction, CLI runtime-kind disclosure, Replay Viewer timeline/core-capture
callout, evaluation visuals/worker control/folder access, README
stable/prerelease disclosure and screenshots) by direct verification:
`bytefray agents` lists all eleven starters including `raider`/`sentinel`
with correct `[Python]`/`[VM]` labels (§8); the frozen v2 benchmark
population is unchanged and matches (§4); the full regression suite,
including every test added across Phases 1-5 and alpha1/alpha2, passes
(§7). No item from CLAUDE.md's task §3 list was reimplemented merely
because it was listed; each was verified against current repository
reality rather than assumed. No new agent, gameplay mechanic, Ruleset
control, replay feature, evaluation metric, Designer tab, or Redcode UI was
added in this phase (see §4 below for the two defects that **were** fixed,
which are qualification bug fixes, not feature work).

---

## 4. RC defects found and fixed

RC qualification is not merely re-confirmation — exercising the frozen
Windows executables directly (as opposed to a source `python` invocation)
surfaced a real, previously-shipped defect class, found and fixed:

**Frozen-console non-ASCII rendering.** Alpha2 (§9 of
[V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md](V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md))
already found and fixed one instance of this defect class (an em dash in the
`bytefray agents` listing's "no blob" placeholder rendered as a replacement
character `�` in the frozen `bytefray.exe`'s console, even though the exact
same source ran correctly under plain `python`). RC1 qualification exercised
CLI paths alpha2 did not specifically re-check and found **two more
instances of the identical defect class**:

1. `engine/src/battle_engine/agent_evaluation.py`'s `methodology_lines()` —
   the `agents evaluate --group` summary's "Entrant orientation: ..." and
   "Arena alignment: ..." lines each contained an em dash. Reproduced live:
   `bytefray-3.0.0-rc1-windows.zip`'s frozen `bytefray.exe` printed `�`
   where the source build printed `—`, confirmed by running the identical
   command through both the frozen executable and `.venv`'s `python.exe` in
   the same console.
2. `client/src/battle_client/cli.py`'s replay-CLI argparse `description`
   contained an em dash, reproducing identically in
   `bytefray-replay-viewer.exe --help`.

Both were **verified as genuine frozen-build defects, not console/pipe
artifacts of this qualification session** — the same string rendered
correctly from a source Python invocation in the identical PowerShell
console. This directly affects release quality: any user running
`bytefray agents evaluate --group` or `bytefray replay --help` from the
distributed installer/portable build sees garbled output.

**Fix**: replaced both em dashes with the ASCII `--` convention this
codebase's own source comments already use throughout for the same
rhetorical purpose (e.g. `agent_evaluation.py`'s own docstrings). Also
audited `hud_layout.py`'s two em-dash-containing strings (`MATCH COMPLETE —
...` and the Replay Viewer's on-screen header band) and
`app/agent_designer.py`'s Qt window title (`Bytefray – Agent Designer`) —
these render through Pygame's font engine and Qt's window-chrome layer
respectively, neither of which goes through the Windows console code page,
and confirmed via the Designer/Replay Viewer GUI smoke launches in §9/§11
that they are unaffected; left unchanged, since "fix only what qualification
demonstrates is broken" governs here exactly as it did in alpha2.

**Regression coverage added**, mirroring alpha2's own precedent
(`test_cli_agent_listing.py`'s ASCII assertion) so this class of gap cannot
regress silently in either fixed location again:

- `engine/tests/test_agent_evaluation_orientation.py::test_methodology_lines_are_pure_ascii`
- `client/tests/test_headless_characterization.py::test_help_text_is_pure_ascii`

No other RC-stage source change was made. The frozen v2 benchmark
population was re-verified with zero drift both immediately before and
immediately after this fix (§5).

---

## 5. Frozen baseline

`verify_population(load_population())` against
`battle_engine/data/benchmarks/v2_baseline.json`'s nine pinned members:

| Run | Members | Drift |
|---|---|---|
| **Before** any RC-stage change | 9 | **0** |
| **After** the §4 fix | 9 | **0** |
| **Immediately before tagging** | 9 | **0** |

All nine (`adaptive`, `claimer`, `hunter`, `strider`, `wanderer`,
`core_defender`, `core_seeker`, `core_tracker`, `reactive_core_defender`)
matched their pin every time. No frozen agent directory was opened for
writing at any point in this phase.

---

## 6. Repository-hygiene disposition

Re-audited the alpha2-deferred findings (repo-root `agents/` scratch: four
VM manifests with gitignored `*.blob` files, `agents/example` declaring
`name: runner` mismatching its directory, `agents/tester2` a byte-identical
blank-scaffold copy) and the unreferenced pre-v3 README screenshots
(`docs/screenshots/agent-designer.png`, `replay-viewer.png`).

**Answer to the governing question**: no, none of this ships, affects
normal discovery, confuses a fresh clone's packaged product, breaks tests,
or lowers RC release quality. `agents/` is repository-root user data
discovered only at runtime by a local install, not packaged by any wheel,
sdist, or PyInstaller spec (confirmed again by the §... package-data audit
below); its `*.blob` references are gitignored, so a genuine fresh clone
never sees the broken manifests at all. The two old screenshots are inert,
unpackaged files with no README reference. **Disposition: deferred to
post-v3.0 maintenance**, unchanged from alpha2's own disposition — no new
evidence emerged to change that answer, and no cleanup was performed.

**Merge-to-`main` precedent** (§24 of the governing task): `main` has
received zero commits from the entire v3.0-development line so far
(§1) — alpha1 and alpha2 were both published without merging to `main`.
RC1 follows the same precedent: it stays on `v3.0-development`; `main` is
reserved for the final `v3.0.0` promotion, matching this repository's
established v2.0 pattern (`v2.0-final-development` was the branch merged to
`main` at `v2.0.0` final, not at any beta/rc stage).

---

## 7. Version mapping

Audited directly from git history (`v1.0.0-rc1`/`rc2`, every `v2.0.0-betaN`,
`v2.0.0-rc1`/`rc2`, `v2.0.0` final, and this cycle's own `alpha1`/`alpha2`):
every prerelease uses PEP 440 spelling in `pyproject.toml`/installer
`AppVersion` and hyphenated spelling in the Git tag/installer
`ReleaseTag`/artifact filenames. `v2.0.0-rc1` specifically used
`pyproject.toml` version `2.0.0rc1` — direct precedent for the "rc1" PEP 440
suffix spelling (no dot before `rc`, matching Python's own PEP 440 rule).

Applied mapping for this RC (no deviation from precedent):

| Identity | Value |
|---|---|
| Git tag / GitHub Release | `v3.0.0-rc1` |
| `pyproject.toml` version (PEP 440) | `3.0.0rc1` |
| Installer `AppVersion` | `3.0.0rc1` |
| Installer `ReleaseTag` | `3.0.0-rc1` |
| Installer filename | `Bytefray-Setup-3.0.0-rc1.exe` |
| Portable ZIP | `bytefray-3.0.0-rc1-windows.zip` |
| Wheel | `bytefray-3.0.0rc1-py3-none-any.whl` |
| sdist | `bytefray-3.0.0rc1.tar.gz` |

Ruleset ID (`bytefray-rules-2`) and Agent API version (`1`) are **not**
bumped, per `docs/COMPATIBILITY.md`'s existing policy — no change required.

---

## 8. Source qualification

All commands run from a clean tree, canonically (no competing pytest
sessions), before and after the §4 fix; totals below are the final,
post-fix numbers:

| Check | Result |
|---|---|
| Frozen benchmark verification | 9/9, 0 drift (before and after) |
| Default suite (`python -m pytest`) | **2366 passed, 14 skipped, 2 deselected** |
| GUI suite (`pytest tests/ -m ""`) | **226 passed, 1 skipped** |
| `ruff check .` | All checks passed |
| `mypy engine/src/battle_engine` | Success: no issues found in 86 source files |
| `mypy client/src/battle_client` | Success: no issues found in 12 source files |

(Default-suite growth from alpha2's `2334 passed`/`2364 passed` reflects
tests added since, plus the two new regression tests from §4.) No failure
was dismissed as flaky; none occurred. The known
`.pytest-cache-v141: Permission denied` directory-read warning was observed
and is unrelated to test outcomes (see `docs/WINDOWS_DEV_NOTES.md`).

---

## 9. Ruleset/API compatibility

Verified directly against the built RC1 artifacts and CLI, not merely by
trusting the (also-passing) test suite:

| Check | Result |
|---|---|
| All-VM entrants under `bytefray-rules-2` | rejected: *"Ruleset 'bytefray-rules-2' currently supports Python entrants only (requested runtime kind(s): vm). Use 'bytefray-rules-1' for VM entrants."* |
| Mixed Python+VM entrants | rejected: *"Native matches must contain either all VM entrants or all Python entrants; received: python, vm."* |
| All-VM entrants under `bytefray-rules-1` | runs |
| `raider` vs `sentinel` under `bytefray-rules-2` | runs to completion |
| `raider` vs `claimer`, seed 1, `bytefray-rules-2` | reproduces alpha2's exact recorded result byte-for-byte: `ticks: 182/200, winner: raider, termination: last_agent_standing` — confirmed identically from the source tree, the rebuilt frozen portable `.exe`, and a wheel-installed venv |
| `bytefray agents` listing | all 11 starters present, `[Python]`/`[VM]` labels correct, legend present, pure ASCII, no "Redcode"/"pMARS" mention |
| `engine/tests/test_pmars.py` (Redcode/pMARS interoperability) | 19 passed, 2 skipped (platform-specific paths), using the repository's own bundled `pmars/windows/pmars.exe` |

No semantic behavior changed during RC preparation — every result above is
identical to alpha2's own documented behavior. `bytefray-rules-1`,
VM/blob compatibility, and Redcode/pMARS external interoperability are all
confirmed unchanged.

---

## 10. Windows portable

Built via `tools/build_win.ps1` (unmodified) from a pycache-cleaned tree,
twice (once before, once after the §4 fix — the pre-fix build was discarded
and rebuilt). Final build: all four onedir applications built successfully,
the script's own embedded GUI-import/startup and `agents create` smoke
tests passed, exit code 0. Packaged into
`dist/portable/bytefray-3.0.0-rc1-windows.zip` (fresh RC1 build; alpha2's
portable artifact was not reused).

Extracted to an isolated directory outside the repository
(`%TEMP%\bytefray-rc1-portable-qual`) with an isolated `BYTEFRAY_ROOT` and
exercised directly:

| Check | Result |
|---|---|
| `bytefray.exe --version` | `Bytefray 3.0.0rc1, Agent API v1, result schema v1, replay schema v3, Python 3.11.9` |
| `agents` listing | all 11 starters, correct runtime labels |
| `agents create --template annotated` | succeeded |
| `agents validate` | `status: valid` |
| `agents test raider --opponent claimer --ruleset bytefray-rules-2 --seed 1` | reproduced the tick-182 capture exactly |
| `agents evaluate --group` | ran; confirmed the §4 fix live (ASCII `--`, not `�`) |
| Agent Designer smoke launch (`BYTEFRAY_GUI_SMOKE_EXIT_MS`) | exit code 0 |

No source-relative path was required for any check; every resource
resolved from inside the extracted, relocated tree.

---

## 11. Windows installer

`ISCC.exe tools\installer.iss` compiled successfully from the fixed,
rebuilt `dist\windows` trees:
`dist\installer\Bytefray-Setup-3.0.0-rc1.exe` (~101 MB). Verified directly:
filename matches `ReleaseTag`; `(Get-Item ...).VersionInfo.ProductVersion`
reads `3.0.0rc1`, matching `AppVersion` exactly.

**Interactive lifecycle**: not exercised end-to-end in this automated
session. `tools/installer.iss` sets `PrivilegesRequired=admin`, so even a
silent (`/VERYSILENT`) run triggers a UAC elevation prompt; this session has
no interactive user available to approve one. This is the identical,
previously-disclosed session privilege constraint noted in both
alpha1 (§8) and alpha2 — not a new gap and not a defect in the installer.
No existing Bytefray installation was present on this machine to test an
upgrade path (§1), so the applicable workflow would be a fresh install in
any case.

The installer's `[Files]` payload is the same `dist\windows` trees the
portable ZIP packages (`tools/installer.iss` lines 58-61), and the portable
ZIP received full extract-and-run qualification in §10, so the installed
application payload itself is qualified; only the installer's own
admin-elevated mechanics (registry write, Start Menu/desktop shortcuts,
uninstaller registration) remain unverified by this session.

**Prepared for a human follow-up**, exact commands:

```powershell
# Install (will prompt for UAC approval):
Start-Process "D:\Projects\BATTLE2\dist\installer\Bytefray-Setup-3.0.0-rc1.exe"

# After install, verify and launch:
& "$env:ProgramFiles\Bytefray\bin\bytefray\bytefray.exe" --version
& "$env:ProgramFiles\Bytefray\bin\bytefray-agent-designer\bytefray-agent-designer.exe"

# Uninstall from Settings > Apps, or:
& "$env:ProgramFiles\Bytefray\unins000.exe"
```

If this is performed, re-run `bytefray --version` after uninstall completes
to confirm no leftover `BYTEFRAY_ROOT` registry key or Start Menu/desktop
shortcut survives, per `tools/installer.iss`'s uninstall section.

---

## 12. Python package

Built fresh `wheel` and `sdist` (`python -m build`) from the fixed, clean
tree — alpha2's artifacts were not reused. `tools/check_wheel.py` passed
against the built wheel (no stray `__pycache__` contamination).

Installed into two separate fresh, isolated venvs outside the repository:

| Check | Wheel venv | sdist venv |
|---|---|---|
| `pip install` | succeeded | succeeded |
| `pip show bytefray` | `Version: 3.0.0rc1` | `Version: 3.0.0rc1` |
| `bytefray --version` | correct RC1 identity, Agent API v1, schemas v1/v3 | correct RC1 identity |
| `battle_engine.project_info.get_project_info()` | correct `ProjectInfo`, no repo-relative-path dependency | not re-checked (same package) |
| `agents` (starter discovery) | all 11 starters | not re-checked |
| `agents create --template annotated` / validate / test | all succeeded, reproduced the tick-182 capture | not re-checked |
| `agents evaluate --group` | ran, healthy | not re-checked |
| `pip install pygame PySide6` (GUI extras) | pygame 2.6.1, PySide6 6.11.2 installed cleanly | n/a |
| Agent Designer smoke launch | exit code 0 | n/a |
| Replay Viewer launch against a real replay | launched, stayed running, cleanly terminated | n/a |

Python version tested locally: 3.11.9. CI's `test-linux-core` matrix
additionally covers 3.10, 3.12, 3.13 (§15).

---

## 13. Linux qualification

No interactive Linux/Ubuntu environment was available in this session. A
remote-sandbox attempt was made specifically to close alpha1/alpha2's
disclosed Linux-GUI gap; the sandbox that was actually provisioned reported
itself as Windows (MSYS2/Git Bash), not Linux, with no `Xvfb`, no X server,
and no Linux package manager — so no real Linux GUI screenshot pass was
achievable this phase either. Reported plainly rather than fabricated.

Per the task's own required exact statement:

```text
Linux source/package qualification: PASS
Linux GUI RC qualification: NOT EXERCISED
```

The **PASS** rests on CI, a real Linux execution environment, run against
the exact RC1 candidate commit (§15): `test-linux-core` (Ubuntu, Python
3.10/3.11/3.12/3.13 — full non-GUI suite, ruff, wheel-import isolation) and
`build-linux-wheel` (fresh `python -m build --wheel` + `check_wheel.py`).
The pre-existing `linux-gui-smoke.yml` Xvfb workflow (startup-only, not
full visible/input validation) was not re-run as part of this push, since
it is unmodified and has its own trigger — identical treatment to alpha1
and alpha2. **This is not treated as an RC blocker**: it is an unchanged,
twice-previously-disclosed limitation, not a regression, and gate G9 (§18)
only requires the status be explicitly recorded, which it is here.

---

## 14. Integrated product workflow

Ran the full preferred workflow against the rebuilt RC1 portable and wheel
distributions (§10, §12): agent creation from the Annotated Example
template → validate → development test under explicit Ruleset v2 → Raider
vs Claimer producing a real, reproducible core capture at tick 182 →
pairwise evaluation (Raider vs Claimer/Hunter/Sentinel, JSON output) →
group (multi-entrant) evaluation (Raider + Claimer + Hunter + Sentinel,
360 healthy cells, correct capture attribution) → `evaluations list` →
Agent Designer smoke launch → Replay Viewer launch against the real
tick-182 capture replay. No capture was fabricated: the tick-182 capture is
the same deterministic result alpha2's own report recorded for this exact
agent/opponent/seed/ruleset combination, reproduced identically from three
independent artifacts (source tree, frozen portable `.exe`, wheel install)
in this phase.

---

## 15. Package-data audit

Confirmed directly against the rebuilt frozen trees (not assumed from
alpha2): `dist/windows/bytefray/_internal/battle_engine/data/starter_agents/`
and `dist/windows/bytefray-agent-designer/_internal/battle_engine/data/starter_agents/`
both contain all eleven starters including `raider` and `sentinel`;
`battle_engine/data/agent_template_annotated/` is present in the `bytefray`
frozen tree; `assets/branding/` (icon, ICO, logo, brand sheet) is present in
the `bytefray`, `bytefray-agent-designer`, and `bytefray-replay-viewer`
frozen trees. The existing generic regression tests
(`test_every_registered_starter_reaches_the_frozen_tree`,
`test_bytefray_spec_bundles_the_annotated_agent_template_directory`, and
siblings in `engine/tests/test_windows_packaging_spec.py`) all pass as part
of §8's full suite run. No new bundled-data gap was found.

---

## 16. CI

Required CI was confirmed green on this cycle's starting commit
(`82fb818`, before any RC-stage change) as a baseline. After the §4 fix and
the three RC-stage commits were pushed, CI run
[`33134652215`](https://github.com/libertaine/Bytefray/actions/runs/33134652215)
ran against the exact candidate commit `6a11fff` and completed **green**,
all six jobs:

| Job | Result |
|---|---|
| `test-linux-core (3.10)` | success |
| `test-linux-core (3.11)` | success |
| `test-linux-core (3.12)` | success |
| `test-linux-core (3.13)` | success |
| `build-linux-wheel` | success |
| `build-windows-exe` | success |

---

## 17. Artifacts

| Artifact | Path |
|---|---|
| Windows installer | `dist/installer/Bytefray-Setup-3.0.0-rc1.exe` |
| Windows portable ZIP | `dist/portable/bytefray-3.0.0-rc1-windows.zip` |
| Python wheel | `dist/bytefray-3.0.0rc1-py3-none-any.whl` |
| Source distribution | `dist/bytefray-3.0.0rc1.tar.gz` |
| Checksums | `dist/SHA256SUMS.txt` |

Naming follows established repository precedent exactly (§7).

---

## 18. SHA-256

```
2b5464ac74bf95588aa8e716fbd61dac25ae883e880d153347cb1f4b3c32e821  Bytefray-Setup-3.0.0-rc1.exe
ac07668bb2106aa6493144f44373db20667ca66760a5f9a3d0754d214718afa7  bytefray-3.0.0-rc1-windows.zip
3e6684cc41f7467280267431ef1c13302828a09f3b797a14887865e4e11ddea2  bytefray-3.0.0rc1-py3-none-any.whl
bb83c82684d745af6f7f781ee9b53a508ebb052a08bb0ee89d49158a79a13a9e  bytefray-3.0.0rc1.tar.gz
```

Computed locally immediately before upload; re-verified against uploaded
GitHub Release assets after publication (§22).

---

## 19. Known limitations

- Installer live install→launch→uninstall lifecycle not executed
  end-to-end in this automated session (§11) — identical, previously
  twice-disclosed session privilege constraint, not a product defect.
  Exact follow-up commands are recorded in §11.
- Linux GUI (visible/input) qualification remains unexercised this phase
  too (§13) — a remote-sandbox attempt was made and reported an
  environment that could not provide it; headless Linux functionality and
  installation remain CI-verified on every push.
- The two frozen-console em-dash defects (§4) were found and fixed in the
  two CLI code paths RC1's own qualification walk happened to exercise
  (`agents evaluate --group`, `bytefray replay --help`). A full sweep of
  every `argparse`/print string in `engine/src/battle_engine` and
  `client/src/battle_client` was performed and found no further instances;
  `app/`'s GUI-rendered text was audited and confirmed unaffected by this
  defect class (different rendering pipeline — see §4), so it was not
  swept for the same fix.

---

## 20. RC gates

| Gate | Status | Evidence |
|---|---|---|
| G1 — Alpha feedback | **PASS** | §2 — no unresolved known issue |
| G2 — Frozen baseline | **PASS** | §5 — 9/9, zero drift throughout |
| G3 — Source tests | **PASS** | §8 |
| G4 — Static validation | **PASS** | §8 — Ruff and both mypy targets clean |
| G5 — Ruleset/API compatibility | **PASS** | §9 — no unintended change; byte-identical reproduction of alpha2's own recorded result |
| G6 — Windows portable | **PASS** | §10 — fresh RC1 build, full extract-and-run qualification |
| G7 — Windows installer | **PASS (disclosed limitation)** | §11 — build/version/payload verified; interactive UAC lifecycle needs a human session, exact commands prepared |
| G8 — Python packages | **PASS** | §12 — wheel and sdist, fresh isolated venvs |
| G9 — Linux | **PASS (GUI explicitly recorded as not exercised)** | §13 |
| G10 — Product workflow | **PASS** | §14 |
| G11 — Assets/package data | **PASS** | §15 |
| G12 — Version consistency | **PASS** | §7, confirmed in built artifacts |
| G13 — CI | **PASS** | required CI green on the exact tagged commit — see §21 |
| G14 — Clean tree | **PASS** | verified immediately before tagging, §21 |
| G15 — Release provenance | **PASS** | tag points at the exact qualified, CI-green commit, §21/§22 |

---

## 20a. Verdict

### V3.0.0-RC1 QUALIFIED — PUBLISH RELEASE CANDIDATE

All fifteen gates pass. The two disclosed limitations (installer
interactive UAC lifecycle, Linux GUI visible/input qualification) are
unchanged, previously twice-disclosed session-environment constraints, not
product defects or regressions, and neither gate's own wording requires
them exercised to pass (G7: "verified... with any limitation explicitly
assessed"; G9: "GUI status explicitly recorded"). The one genuine defect
class discovered during qualification (§4) was fixed and re-verified
end to end before this verdict was reached.

---

## 21. CI and tagging record

Three commits were pushed to `v3.0-development` for this phase:
`572406e` (fix), `7424d22` (release-prep), `6a11fff` (this qualification
report). Remote HEAD verified to match local exactly
(`6a11fffa987e153d957969fd6394c0596cfe6fcc`) immediately before tagging;
working tree confirmed clean at that point. CI run `33134652215` (§16)
completed green on that exact commit. The annotated tag `v3.0.0-rc1` was
created directly at `6a11fff` (`git tag -a v3.0.0-rc1 ... 6a11fff`) and
pushed; `gh api repos/libertaine/Bytefray/git/tags/<tag-object-sha>`
confirmed the tag object's `object.sha` is `6a11fff`, independent of the
release API's cosmetic `targetCommitish` field.

---

## 22. Publication result

Published as a GitHub **prerelease** (`isDraft: false`, `isPrerelease:
true`), not merged to `main` — `main` remains untouched by any v3.0 commit,
consistent with §6's precedent finding.

| Item | Value |
|---|---|
| Tag | `v3.0.0-rc1` (annotated) |
| Tagged commit | `6a11fffa987e153d957969fd6394c0596cfe6fcc` — the exact CI-verified commit |
| Release URL | <https://github.com/libertaine/Bytefray/releases/tag/v3.0.0-rc1> |
| Fix commit | `572406e` — the two frozen-console ASCII defects (§4) |
| Release-prep commit | `7424d22` — version bump, CHANGELOG, ROADMAP, README |
| Qualification-report commit | `6a11fff` — this document |
| Branch | `v3.0-development`, pushed |

Artifacts uploaded — the same four classes alpha1/alpha2 shipped, plus
checksums:

| Asset | SHA-256 |
|---|---|
| `Bytefray-Setup-3.0.0-rc1.exe` | `2b5464ac74bf95588aa8e716fbd61dac25ae883e880d153347cb1f4b3c32e821` |
| `bytefray-3.0.0-rc1-windows.zip` | `ac07668bb2106aa6493144f44373db20667ca66760a5f9a3d0754d214718afa7` |
| `bytefray-3.0.0rc1-py3-none-any.whl` | `3e6684cc41f7467280267431ef1c13302828a09f3b797a14887865e4e11ddea2` |
| `bytefray-3.0.0rc1.tar.gz` | `bb83c82684d745af6f7f781ee9b53a508ebb052a08bb0ee89d49158a79a13a9e` |
| `SHA256SUMS.txt` | (index of the above) |

Every uploaded asset was re-downloaded from the published release
(`gh release download v3.0.0-rc1`) and its digest recomputed; all four
match the locally built values exactly (§18).

A follow-up commit (`docs: mark v3.0.0-rc1 published`) updates
`README.md`'s Downloads section and top current-release line with live
download links, and `docs/ROADMAP.md`'s status line, from "qualified and
pending publication" to "published" — the same post-publication pattern
alpha1 (`43d52f2`) and alpha2 (`300d5e4`) both used, so the tagged commit
itself never claims a publication that had not yet happened.

---

## 23. Phase 6 / final v3.0.0 inputs

- The em-dash frozen-console defect class (§4) was found twice now in two
  different releases (alpha2, RC1) by exercising CLI paths qualification
  happened to walk, each time in a spot the previous fix did not cover. A
  full, deliberate sweep was performed this time (§19) and found nothing
  further, but a project-wide `isascii()` regression test over *every*
  printed CLI string (rather than one assertion per discovered instance)
  would close this class of gap generically instead of reactively — a
  reasonable candidate for post-RC1 (not RC1 itself, to avoid scope creep
  into a broad refactor at qualification time).
- The installer's live UAC install/uninstall lifecycle remains
  unautomatable from this kind of session across three consecutive
  releases (alpha1, alpha2, RC1). If a future release cycle wants this
  closed permanently, alpha1's own §24 suggestion stands: script it for a
  dedicated interactive or self-hosted-runner CI job.
- Real Linux GUI qualification remains unexercised across the same three
  releases for the same structural reason (no Ubuntu GUI environment
  reachable from this kind of session, including the remote-sandbox path
  attempted this phase). A GitHub Actions job that takes real Xvfb
  screenshots (rather than only a startup-exit-code smoke check) is the
  most concrete way to close this without requiring an interactive human
  pass every release.
- Alpha2's own Phase 6 inputs (the CLI's remaining Ruleset-v1-by-default
  behavior, deferred repository-hygiene findings 1-4) were re-reviewed and
  found still accurate and still non-blocking; they remain open questions
  for whenever the project next revisits them, not RC1 or final v3.0.0
  work.

---

### Addendum (2026-08-29) — the CLI's Ruleset-v1-by-default behavior was an RC defect

This document classified the CLI's own `--ruleset` omission (still
resolving to Ruleset v1) as non-blocking and deferred it (§23 above,
inherited from alpha2's own §21). Later Ruleset research established that
this is materially more than a documentation gap: independent execution of
the shipped starter agents showed a Ruleset-v1 game launched by omitting
`--ruleset` **cannot terminate through vulnerable-core capture at all**,
while the Agent Designer's converged v2 default can. A new user running
apparently equivalent Python-agent matches through the CLI and the Designer
therefore received materially different gameplay — a genuine RC1 default-
product-gameplay-inconsistency defect, not merely an implicit CLI default
worth documenting someday.

This was corrected on `v3.0-development` as an input to `v3.0.0-rc2`,
without moving the `v3.0.0-rc1` tag or editing this qualification record's
own findings above. See
[V3_RC1_DEFAULT_RULESET_DEFECT.md](V3_RC1_DEFAULT_RULESET_DEFECT.md) for
the reproduction, root cause, fix, and regression evidence. This addendum
invalidates one inference in §23's closing discussion (that the deferred
CLI default was non-blocking) — it does not invalidate any of this
document's own RC1 qualification evidence or gate results, which describe
what was verified about v3.0.0-rc1 as tagged and remain accurate.
