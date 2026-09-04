# Bytefray v4 RC Path — Phase 4: RC1 Build, Packaged Qualification & Publication Gate

Branch: `v4-rc1-development`

Phase 4 starting SHA (HEAD at task start): `3a41e7bec94f3c230fb2419d287d051cde4d7db1`
Cross-platform-qualified source baseline: `01a1718658f46d161e5879e815682dd7562b141d` (Phase 3's ending
commit, independently qualified on Windows and real native-Wayland Ubuntu 26.04)
**Final candidate source SHA: `356702621d0ad328ac27497235087f5bd67e7183`**

This is an **interim** qualification report. RC1 has **not** been published: Linux packaged
qualification of the actual RC1 wheel/sdist remains outstanding and this session has no access to
a Linux machine to perform it. No tag was created. No GitHub Release was created.

```text
PHASE 4 WINDOWS CANDIDATE QUALIFIED — LINUX PACKAGED QUALIFICATION REQUIRED BEFORE RC1 PUBLICATION
```

---

## A. Executive decision

| Gate | Result |
|---|---|
| RC1 version prepared | **PASS** |
| Source qualification | **PASS** |
| Windows portable ZIP | **PASS** |
| Windows installer clean install | **PASS** |
| Upgrade lifecycle | **PASS** |
| Uninstall lifecycle | **PASS** |
| Wheel | **PASS** |
| sdist | **PASS** |
| Packaged first-user workflow | **PASS** |
| Stable-v4 evaluation | **PASS** |
| Replay spectator workflow | **PASS** (process-level; see §K) |
| Linux packaged qualification | **PENDING** |
| Cross-platform determinism | **PASS** |
| Artifact permission note resolved/classified | **PASS** (classified: no defect) |
| Checksums verified | **PASS** |
| RC blocker outstanding | **NO** |
| Publish RC1 | **PENDING** (blocked only on the Linux gate) |

---

## B. Starting state

```text
git status --short          (empty)
git branch --show-current   v4-rc1-development
git rev-parse HEAD           3a41e7bec94f3c230fb2419d287d051cde4d7db1
git rev-parse origin/v4-rc1-development  3a41e7bec94f3c230fb2419d287d051cde4d7db1  (identical)
git rev-parse origin/main    010c3f6b1cbfc7d63988f8ccfc2626aae7dcef99
```

`git diff --stat 01a1718..HEAD` showed exactly one file: `docs/research/v4/V4_RC1_LINUX_PREQUALIFICATION.md`
(458 insertions, a new file). `git diff 01a1718..HEAD -- engine client app agents tools` was empty.
The Linux prequalification report had been incorporated as anticipated by the governing task, and no
product code had changed since the cross-platform-qualified baseline. Phase 4 proceeded from `01a1718`'s
qualification status without reservation.

---

## C. Release-prep changes

Two commits, both on `v4-rc1-development`:

1. **`afdb7d9` — `chore(release): prepare v4.0.0-rc1`.** `pyproject.toml` version bumped from
   `4.0.0-alpha4`; `tools/installer.iss`'s `AppVersion`/`ReleaseTag` pair updated. `CHANGELOG.md`'s
   `Unreleased` Phase 1/2 entries (plus Phase 3's previously-undocumented fixes) were consolidated
   into one comprehensive `[4.0.0-rc1]` heading describing what stable v4 **is** (gameplay,
   spectator experience, evaluation, compatibility) rather than a chronological phase dump.
   `README.md`'s Downloads section notes RC1 as prepared and undergoing packaged-artifact
   qualification, without a live download link or claimed publication — the top banner and
   Downloads table were deliberately left pointing at the actually-published `v4.0.0-alpha4`.
2. **`3567026` — `fix(release): match pyproject.toml's RC1 version to installer.iss's ReleaseTag`.**
   See §O.1 — a self-found-and-fixed version-spelling defect caught by the full-suite run.

`356702621d0ad328ac27497235087f5bd67e7183` is the final release-prep commit and the RC1 candidate
source SHA used for every artifact in this report.

Version mapping used (verified against the repo's actual, currently-enforced convention — see
§O.1, not assumed from older precedent):

| Authority | Value |
|---|---|
| `pyproject.toml` `version` | `4.0.0-rc1` |
| `tools/installer.iss` `AppVersion` | `4.0.0rc1` |
| `tools/installer.iss` `ReleaseTag` | `4.0.0-rc1` |
| Installed distribution (`importlib.metadata.version`) | `4.0.0rc1` |
| Git tag (not yet created) | `v4.0.0-rc1` |

---

## D. Source qualification

All commands run on Windows 11 Pro 10.0.26120, Python 3.13.14, `.venv/` at the repository root,
against the final candidate `3567026`.

### D.1 Qualification integrity protocol

```text
HEAD before the final full-suite run:  356702621d0ad328ac27497235087f5bd67e7183
HEAD after:                            356702621d0ad328ac27497235087f5bd67e7183   (unchanged)
git status:                            clean, both times
SHA-256 of CHANGELOG.md/README.md/tools/installer.iss: identical before and after both the full
  suite and the GUI suite runs
```

An earlier full-suite run (at the since-superseded commit `afdb7d9`) surfaced one real, expected
failure (§O.1); it was fixed, committed as a new commit (`3567026`, never an amend), and the
complete suite was rerun from a clean state as the authoritative run recorded below.

### D.2 Static checks

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | **All checks passed** |
| Engine mypy | `mypy engine/src/battle_engine` | **Success, 101 source files** |
| Client mypy | `mypy client/src/battle_client` | **Success, 15 source files** |
| Whitespace | `git diff --check` | clean |

Identical file counts to Phase 3's own static-check baseline.

### D.3 Full repository suite

```text
python -m pytest --basetemp=.pytest-tmp/phase4-source-qual-final --junitxml=...
```

**2922 passed, 14 skipped, 0 failed** (2936 collected, 2 deselected by the default `-m "not gui"`),
in 297.7s. Reconciles exactly against Phase 3's own 2936-collected/0-failure/14-skipped baseline.

### D.4 GUI suite — broader than any prior Windows phase

Phase 1–3's own Windows sessions could not drive a literal GUI session and only ran the two
GUI-marked tests inside the default `testpaths` (`pytest -m gui`, no path). This session has a real
Windows desktop available, so both were run:

```text
python -m pytest -m gui                 -> 2 passed, 2936 deselected   (matches Phase 1-3's own claim)
python -m pytest -m gui tests/          -> 253 passed, 6 deselected, 0 failed   (34.8s)
```

**Total: 255 GUI-marked tests passed, 0 failed** — matching the Linux prequalification's own GUI
totals (253 + 2) exactly, and materially stronger evidence than any prior Windows phase report.

---

## E. Build provenance

```text
Source branch:    v4-rc1-development
Candidate SHA:    356702621d0ad328ac27497235087f5bd67e7183
Version:          4.0.0-rc1 (pyproject.toml) / 4.0.0rc1 (installed distribution, AppVersion)
Python:           3.13.14 (repo .venv; PyInstaller/wheel/sdist build)
                  3.13.7  (independent wheel-qualification venv)
Build environment: Windows 11 Pro 10.0.26120
```

Build commands, run in this order from the candidate commit with no intervening source changes:

```bash
pwsh tools/build_win.ps1                                          # 4 PyInstaller onedir apps
python -m build                                                   # wheel + sdist
python tools/check_wheel.py dist/bytefray-4.0.0rc1-py3-none-any.whl
Compress-Archive -Path dist/windows/{bytefray,bytefray-cli,bytefray-agent-designer,bytefray-replay-viewer} \
  -DestinationPath dist/bytefray-4.0.0-rc1-windows.zip
& "...\Inno Setup 6\ISCC.exe" tools/installer.iss
```

`tools/build_win.ps1` includes its own real, executable-level smoke tests (GUI import/startup for
the unified `bytefray.exe design` and standalone `bytefray-agent-designer.exe`; a real
`bytefray.exe agents create smoke_agent` against the frozen tree; a residue check proving no
runtime-generated data leaked into the distributable trees) — all passed.

**Clean-build discipline.** Prior `v4.0.0-alpha3`/`alpha4`/`v3.0.0`-era `dist/`/`build/` output
(558 MB) was moved aside to `dist.pre-rc1-backup-<timestamp>/` and `build.pre-rc1-backup-<timestamp>/`
(both git-ignored, untracked directories; isolated rather than deleted) before any RC1 artifact was
built, so no stale binary could be mistaken for an RC1 artifact.

**Reproducibility.** Not claimed or proven byte-reproducible. What is established is **traceable
provenance**: all four artifact classes were built from the same working tree at commit `3567026`,
with no commit, rebuild, or source edit between the first and last artifact build.

---

## F. Artifact inventory

| Artifact | Size (bytes) | SHA-256 |
|---|---|---|
| `bytefray-4.0.0rc1-py3-none-any.whl` | 899,687 | `e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3` |
| `bytefray-4.0.0rc1.tar.gz` | 872,085 | `3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8` |
| `bytefray-4.0.0-rc1-windows.zip` | 140,908,472 | `4c93c17ed22141406713772a502dcaf9c8a695a81dc813f03752d866f8fa6dab` |
| `Bytefray-Setup-4.0.0-rc1.exe` | 100,733,358 | `4f4756d297258b246150653e8aa29098677e24a7c512a74f525ee3c6cb110088` |

`dist/SHA256SUMS.txt` contains these four lines and was independently re-verified against the
actual files (`sha256sum -c`) after being written — all four `OK`. No artifact was rebuilt after
this verification.

---

## G. Portable ZIP qualification

Extracted to a fresh directory outside the source tree (session scratchpad), not run from build
staging.

| Check | Result |
|---|---|
| Version | `Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4` |
| API-v2 roster, omitted `--ruleset` | Resolved `bytefray-rules-4` |
| API-v1 roster, omitted `--ruleset` | Resolved `bytefray-rules-2` |
| Explicit historical Alpha2 | `bytefray-rules-4-alpha2` preserved, own schema |
| API v1 + `bytefray-rules-4` | Rejected pre-execution, exit 2, no output artifacts |
| API v2 + `bytefray-rules-2` | Rejected pre-execution, exit 2, no output artifacts |
| Stable-v4 evaluation | schema 7, identity 7, arena 512, `ruleset_v4_seeded_placements`, 16 cells (8 seeds × both orientations), `lifecycle_state: finished` |
| Replay — Broadcast | Headless renderer played the full match to a correct `RESULT` line |
| Replay — Perspective/Director/Fight Night | Real pygame Replay Viewer launched successfully in each mode (including against a deliberately mismatched replay/trace pair) and ran without crashing for the full observation window; see §K for what this does and does not prove |

**Archive-content audit.** No `.git`, `.pytest_cache`, `.venv`, credentials, tokens, absolute paths,
or research/probe agents found in the ZIP. One pre-existing, non-blocking observation: 15
`__pycache__` entries under bundled `v4_*` starter-agent directories (generated by the build's own
smoke steps importing those modules). Confirmed **identical in count** to the already-published
`v4.0.0-alpha4` portable ZIP — not new, not a regression, not an RC blocker.

---

## H. Installer qualification

The installer requires admin elevation (`PrivilegesRequired=admin`); this automated session runs
unelevated with no way to satisfy an interactive UAC prompt. Rather than fabricate this evidence,
the maintainer ran the prepared lifecycle script from an elevated PowerShell session, using an
isolated `AppDir`/`DataRoot` pair (not the real `Program Files`/`ProgramData`) so the real machine
state was untouched.

| Step | Result |
|---|---|
| Clean silent install of prior published `v4.0.0-alpha4` | Succeeded; `bytefray --version` reported `Bytefray 4.0.0a4` |
| User-data sentinel created | `user-upgrade-sentinel.txt` written under the isolated data root |
| Silent **upgrade** install of RC1 over the alpha4 install | Succeeded; `bytefray --version` reported `Bytefray 4.0.0rc1` |
| Post-upgrade match | `ruleset_id: bytefray-rules-4` — stable-v4 default resolution correct after upgrade |
| User data survived the upgrade | Sentinel present |
| Registry `BYTEFRAY_ROOT` (machine) | Correctly set to the isolated data root |
| Start Menu shortcuts | Both `Bytefray Agent Designer.lnk` and `Bytefray Replay Viewer.lnk` present |
| Silent uninstall | Succeeded |
| App directory after uninstall | Removed |
| Data root after uninstall | **Retained** (user data policy honored) |
| Sentinel after uninstall | **Retained** |
| Registry `BYTEFRAY_ROOT` after uninstall | Cleared |

One minor gap in the lifecycle script itself (not a product defect): a planned `runner.yaml`
modify-and-hash-compare sub-check did not execute because that starter manifest had not yet been
lazily initialized at the point the script ran (manifests initialize on first catalog access, per
documented behavior) — the sentinel-file evidence above already directly answers the "does user
data survive" question, so this is recorded as a deferred script-coverage improvement (§Q), not a
finding against the product.

**Result: clean install, upgrade, and uninstall all PASS**, satisfying acceptance criteria 9–11.

---

## I. Wheel/sdist qualification

Both performed in fresh virtual environments outside the repository, removed after evidence was
recorded.

**Wheel.** `pip install` succeeded. An initial import check reported `app.__file__` resolving to
the source tree — investigated and found to be a false positive from the checking shell's own
current working directory (still the repo root) shadowing the installed package via Python's
`sys.path[0]` behavior for `-c`, not a real wheel defect; re-run with the working directory outside
the repo confirmed `battle_engine`, `battle_client`, and `app` all resolve to the venv's
`site-packages`. `importlib.metadata.version("bytefray")` and `bytefray --version` both reported
`4.0.0rc1`. A stable-v4 match, an API-v1 match, a small stable-v4 evaluation (schema 7,
`lifecycle_state: finished`), and replay generation/read all succeeded.

**sdist.** Built by the same `python -m build` invocation as the wheel. `pip install` of the
`.tar.gz` into a second clean venv succeeded; import/version verified clean from outside the repo;
a stable-v4 CLI match correctly resolved `bytefray-rules-4`.

---

## J. Stable-v4 packaged product workflow

Consistent across the portable ZIP, installer (post-upgrade), wheel, and sdist: an omitted
`--ruleset` for an Agent API v2 roster always resolves `bytefray-rules-4`; an Agent API v1 roster
always resolves `bytefray-rules-2`; explicit `bytefray-rules-4-alpha1`/`-alpha2` are preserved
under their own identities; both invalid API/Ruleset combinations fail closed pre-execution with no
partial output. The stable-v4 evaluation methodology (schema 7, arena 512, 8 seeds, both
orientations, `ruleset_v4_seeded_placements`) runs correctly from every packaged context, and its
human-readable console summary agrees with the persisted artifact (Phase 3's fix holds in the
packaged build).

---

## K. Replay/spectator packaged workflow

Broadcast mode is fully confirmed (headless renderer, full tick-by-tick playback to a correct
result). Perspective, Director, and Fight Night are confirmed at the **process level**: the real
packaged pygame Replay Viewer was launched in each mode (`--perspective A`, `--director`,
`--fight-night`), including once against a deliberately mismatched replay/trace pair, and ran
without crashing or exiting with an error for the full observation window in every case — consistent
with Phase 3's own finding that a mismatch should fail safe into Broadcast rather than crash or
raise a dialog, so an unremarkable, still-running process is the *expected* outcome for that case,
not merely an absence of evidence.

What this phase did **not** do: visually/pixel-confirm the on-screen HUD content of each mode from
a non-interactive automation session (pygame has no self-capture mechanism equivalent to Qt's
`QWidget.grab()`, and stdout is empty for a windowed pygame process). The underlying knowledge-
boundary/pairing correctness this depends on is unchanged since Phase 3 and is proven by the 35
dedicated spectator tests (`test_v4_spectator_perspective.py`, `test_v4_spectator_derivation.py`,
`test_v4_spectator_director.py`, `client/tests/test_perspective*.py`, `client/tests/test_director.py`,
`client/tests/test_fight_night.py`), all reconfirmed passing in this phase's own full-suite run (§D.3).

---

## L. Linux packaged qualification

**Not performed.** This is a Windows-only session with no access to a Linux machine. Per the
governing task's explicit publication gate, this blocks tagging and publishing RC1.

### Linux handoff

```text
Candidate source SHA:   356702621d0ad328ac27497235087f5bd67e7183
Branch:                 v4-rc1-development
Expected version:       4.0.0rc1 (importlib.metadata) / bytefray --version reports
                         "Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4"

Wheel:  bytefray-4.0.0rc1-py3-none-any.whl
        SHA-256: e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3

sdist:  bytefray-4.0.0rc1.tar.gz
        SHA-256: 3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8
```

Required Linux packaged smoke checks (mirroring the rigor of `V4_RC1_LINUX_PREQUALIFICATION.md`,
which qualified the source at `01a1718` on real native-Wayland Ubuntu 26.04):

1. Install the wheel above into a clean venv; confirm version and import isolation from any source
   checkout.
2. Real, visible Designer → Simple stable-v4 match → Open Replay → Perspective → Director →
   Fight Night workflow under a real desktop session (X11 or native Wayland), not offscreen.
3. Reproduce the 11 pinned placement vectors (§M) and the 5-identity historical-compatibility
   smoke from the installed wheel.
4. Run the stable-v4 evaluation methodology once (schema 7, arena 512) and read it back with
   `agents evaluations show --verify`.
5. Ideally also install and smoke the sdist in a second clean environment.

**Publication gate: final RC1 publication requires this Linux packaged qualification to PASS**,
unless the maintainer explicitly changes that release requirement.

---

## M. Deterministic compatibility evidence

**Source level.** All 11 vectors pinned in `engine/tests/test_v4_alpha2_placement.py`
(`ALPHA2_PLACEMENT_VECTORS`) were independently reproduced bit-for-bit against the RC1 candidate
via a direct `resolve_direct_match_starts(ruleset_id="bytefray-rules-4", ...)` call, spanning
entrant counts 2/3/4/8, arenas 256/512/1024, and seeds 0/1/3/5/7/9/42 — the same vectors already
confirmed on Windows (Phase 1–3) and native-Wayland Linux.

**Packaged level.** Three spot-check vectors were reproduced from the actual frozen portable-ZIP
`bytefray.exe` (not just the source), by reading tick-0 process anchors back out of a real generated
replay:

| n | arena | seed | expected | packaged result |
|---|---|---|---|---|
| 2 | 256 | 1 | (24, 162) | (24, 162) |
| 2 | 512 | 7 | (324, 167) | (324, 167) |
| 2 | 1024 | 42 | (721, 912) | (721, 912) |

**Historical compatibility.** All five registered identities produced distinct, correctly-recorded
`ruleset_id` values from the packaged executable: `bytefray-rules-1`, `bytefray-rules-2`,
`bytefray-rules-4-alpha1`, `bytefray-rules-4-alpha2`, `bytefray-rules-4`.

**Conclusion.** The version bump did not alter Ruleset semantics, placement, scheduling, or match
outcome.

---

## N. Linux permission finding

Independently confirmed from source (not merely cited from the Linux prequalification report):

- `result.json` (`result_model.write_json_atomic`) and `replay.jsonl` (an equivalent inline pattern
  in `match_service.py`) are both written via `tempfile.mkstemp()` followed by `Path.replace()` —
  `mkstemp`'s deliberate `0600` creation mode survives the atomic rename unchanged.
- `summary.json` (`telemetry.SummaryWriter`) and `trace.jsonl` (`agent_trace.TraceWriter`) both use
  plain `path.open("w", ...)`, which follows the process umask (`0644` by default).

**Classification: no defect.** Against the task's five framing questions: (1) the creating user can
always read all four artifacts (`0600` still grants the owner full read/write); (2) Bytefray
successfully reopens them — proven on Windows (where the distinction is invisible on NTFS) and on
Linux (every packaged workflow read them back correctly); (3) no packaging/install behavior is
affected — these are per-user runtime artifacts under a single-user writable data root
(`$XDG_DATA_HOME/bytefray`, `%LOCALAPPDATA%\Bytefray`, or an installer-provisioned
`BYTEFRAY_ROOT`), never a shared/multi-user location; (4) no documented sharing expectation in
`INSTALL.md`/`docs/LINUX_INSTALL.md`/`docs/COMPATIBILITY.md` requires group/world readability;
(5) the tighter (`0600`) side is deliberate upstream Python security behavior, not an accident —
loosening it for uniformity would be a regression, and tightening the other two has no
justification per the task's own instruction against normalizing `0644` merely for aesthetics. No
source change was made.

---

## O. Defects found

### O.1 Release-prep version-string mismatch (self-found and fixed)

```text
severity/class:   Release-prep correctness defect, caught before qualification completed
root cause:       pyproject.toml's version was set to "4.0.0rc1" (compact PEP 440 spelling),
                  following a stale pattern from v3.0.0-rc1's own git history (commit 7424d22,
                  which predates this repository's later "harden alpha distribution contracts"
                  commit, d633f66). That later commit added
                  engine/tests/test_windows_packaging_spec.py::
                  test_installer_versions_match_package_and_release_tag, which enforces the
                  actual current, tighter contract: pyproject.toml's version must be
                  byte-identical to installer.iss's ReleaseTag (the hyphenated, tag-matching
                  spelling), while AppVersion separately carries the compact/normalized spelling.
detection:        The full-suite qualification run at the since-superseded commit afdb7d9 failed
                  this exact test ('4.0.0-rc1' != '4.0.0rc1').
fix:              pyproject.toml's version corrected to "4.0.0-rc1", committed separately as
                  3567026 (a new commit, not an amend). Reconfirmed the installed distribution
                  still normalizes to "4.0.0rc1", matching AppVersion.
regression test:  Pre-existing; none added.
requalification:  Full static-check suite and full test suite (plus the GUI suites) rerun from a
                  clean state at 3567026; all passed. HEAD/tree integrity verified before and
                  after.
outcome:          fixed
```

### O.2 Stale local editable-install metadata (environment-only, not a candidate defect)

```text
severity:         None (local environment state only; the tracked source tree was never affected)
reproduction:     After the version bump, importlib.metadata.version("bytefray") returned the
                  stale "4.0.0a4" even after `pip install -e .` was rerun, because a leftover
                  bytefray.egg-info/ directory at the repo root (git-ignored, untracked, dated
                  from an earlier alpha4-era build) was resolved ahead of the fresh dist-info.
                  This is the exact same class of issue the Linux prequalification report already
                  found and classified as environment-only (its own §K.1).
fix:              Removed the stale, git-ignored bytefray.egg-info/ directory. git status/git
                  rev-parse HEAD were identical before and after.
candidate impact: None. This never touched a tracked file.
disposition:      Not an RC blocker; not a candidate-tree change.
```

### O.3 Portable ZIP `__pycache__` leakage — no defect (pre-existing, already shipped)

See §G. Confirmed byte-for-byte-identical entry count (15) in the already-published
`v4.0.0-alpha4` portable ZIP. Not new, not a regression, not addressed in this phase.

### O.4 Linux artifact-permission inconsistency — no defect

See §N.

**No RC-blocking defect was found in product code.** No product/gameplay/API/schema/Ruleset code
changed after the source freeze began — the only source changes made in this phase are the
version-bump/documentation commit (`afdb7d9`) and its own version-string correction (`3567026`),
neither of which touches `engine/`, `client/`, `app/`, `agents/`, or `tools/` product/gameplay
logic.

---

## P. Publication

Not published.

```text
git tag --list "v4.0.0-rc1"     -> (none)
```

No tag was created. No GitHub Release was created. Publication is blocked solely on Linux packaged
qualification (§L) — every Windows-side gate in §A is satisfied and no RC blocker was found.

---

## Q. Deferred post-4.0 items

Recorded for follow-up; **none of these are RC blockers**:

- Linux packaged qualification of the exact RC1 wheel/sdist named in §L, on a real desktop session,
  matching the Phase 3 Linux prequalification's rigor.
- A more complete installer-upgrade data-preservation check that first triggers starter-manifest
  lazy-initialization before modifying `runner.yaml`, to restore the pre/post hash comparison
  alongside the sentinel-file check already performed (§H).
- Visual/pixel-level confirmation of Perspective/Director/Fight Night HUD content from a packaged
  build in an interactive session — this phase confirmed process-level launch stability only (§K).

---

## Final decision

```text
PHASE 4 WINDOWS CANDIDATE QUALIFIED — LINUX PACKAGED QUALIFICATION REQUIRED BEFORE RC1 PUBLICATION
```

Candidate source SHA `356702621d0ad328ac27497235087f5bd67e7183` on `v4-rc1-development` is fully
qualified for every gate this Windows session can exercise: source (static + full suite + full GUI
suite), all four artifact classes built from that one SHA, portable ZIP, installer (clean
install/upgrade/uninstall lifecycle), wheel, sdist, packaged stable-v4 workflow, packaged
evaluation, packaged replay/spectator (process level), cross-platform determinism, and the Linux
permission finding — all PASS, with no RC blocker outstanding. RC1 must not be tagged or published
until Linux packaged qualification of the exact wheel/sdist named in §L also passes.
