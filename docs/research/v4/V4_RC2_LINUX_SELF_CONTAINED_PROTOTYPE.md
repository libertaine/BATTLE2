# Bytefray v4 RC2 — Phase 2: Linux Self-Contained PyInstaller Prototype

Branch: `v4-rc2-development`

Source SHA under test (unchanged throughout this phase): `a75b4c8e1b85356e8a5af6a27eaaf4ec8b8a919d`

This is the Linux packaging/frozen-build qualification record for RC2 Phase 2:
establishing a self-contained, PyInstaller-based Linux equivalent to the
existing Windows build workflow, and fixing a genuine cross-platform frozen
subprocess-relaunch defect discovered along the way. This session is a
**continuation** of an interrupted run: the qualification laptop (a
substantially lower-spec machine than the Windows development machine used for
Phase 1B) entered severe memory/swap pressure during PyInstaller builds and GUI
experimentation, and the previous session was stopped mid Phase 14
(relocation test) to avoid destabilizing the machine further. All expensive
work — the build venv, the four PyInstaller builds, the full native-dependency
scan, the frozen-artifact Quorum qualification, and the transport archive —
had already completed successfully before the interruption and was recovered
and reused rather than reproduced.

```text
PASS — self-contained Linux PyInstaller baseline recovered and qualified for RC2
```

---

## A. Executive decision

| Gate | Result |
|---|---|
| Recovered local source diff matches described Phase 2 work, no unrelated changes | **PASS** |
| Local HEAD / remote HEAD consistency | **PASS** — both `a75b4c8` |
| `agents/Nemesis/agent.py-v1` untouched pre-existing untracked file | **PASS** — present, unmodified |
| Clean Linux build venv (Python 3.14.4, pygame-ce, no classic pygame) | **PASS** (recovered, not recreated) |
| Four PyInstaller applications built, post-launcher-fix | **PASS** (recovered, not rebuilt) |
| Frozen executable resolution cross-platform bug found and fixed | **PASS** |
| Focused launcher regression tests | **PASS** (17 passed) |
| Focused packaging-spec regression tests | **PASS** (16 passed) |
| Native shared-library dependency spot-check (4 primary executables) | **PASS** — 0 unresolved |
| Relocation/extraction test outside the repository | **PASS** |
| System-Python/build-venv independence at runtime | **PASS** |
| `v4_quorum` validation from frozen artifact | **PASS** |
| Frozen Quorum match determinism vs. Phase 1B Windows reference | **PASS** — exact match once the original CLI flags were reproduced |
| Headless replay correctness | **PASS** |
| Archive executable-permission preservation | **PASS** |
| GUI qualification | **ENVIRONMENT-LIMITED** — see §I |
| glibc/build-host compatibility | **DOCUMENTED**, bounded — see §J |
| Second-distro qualification | **DEFERRED** — see §K |
| Packaging-format recommendation | **tar.gz for RC2; defer AppImage/Flatpak** — see §L |
| Lint/type-check regressions introduced | **NONE** (pre-existing spec-file and Quorum lint debt unchanged, see §N) |

---

## B. Recovery: starting state

This session began by verifying the interrupted session's state rather than
trusting its own account of what had happened:

```text
Local HEAD:            a75b4c8e1b85356e8a5af6a27eaaf4ec8b8a919d
origin/v4-rc2-development (after two git fetch origin): a75b4c8e1b85356e8a5af6a27eaaf4ec8b8a919d
```

Local and remote matched exactly — no unexpected remote advancement to
reconcile.

```text
Modified (git status --short):
  M engine/src/battle_engine/launchers.py
  M engine/tests/test_launchers.py
  M pyproject.toml
  M tools/bytefray.spec
  M tools/bytefray_cli.spec

Untracked:
  ?? agents/Nemesis/agent.py-v1   (pre-existing, confirmed untouched — see below)
  ?? tools/build_linux.sh
```

`agents/Nemesis/agent.py-v1` was left completely alone throughout this
session: it was never read, staged, or modified, and remains untracked at the
end exactly as found.

Memory/swap at the start of this recovery: **337 MiB free, 6.8 GiB used, 2.9
GiB/4.0 GiB swap used** — materially better than the ~160 MiB free that caused
the previous interruption, but still tight. Memory was rechecked before every
build- or test-adjacent operation in this session and never approached the
prior danger zone (it stayed in the 300–900 MiB free / ~6–7 GiB used band
throughout).

`git diff` was inspected file by file (§C) and confirmed coherent with the
task's own description of the interrupted work — no surprise unrelated
changes were present.

---

## C. Recovered source changes

### C.1 Frozen executable name resolution (the launcher bug)

`engine/src/battle_engine/launchers.py`'s `_packaged_executable()` built the
sibling-executable path a frozen process relaunches (used by `agents
validate`/`agents test` via `agent_worker.py`, tournament resume, and the
Designer's "Development Test"/replay launch) by unconditionally appending
`.exe`:

```python
filename = f"{name}.exe"
```

On a Linux PyInstaller onedir build, whose launcher binary has no extension at
all (`bytefray`, not `bytefray.exe`), every one of those relaunch paths would
fail with `FileNotFoundError: Packaged executable not found: bytefray.exe` —
**confirmed by reproducing it end to end against a real frozen
`dist/linux/bytefray` build** before the fix was applied.

The fix adds a small platform-aware helper:

```python
def _packaged_executable_filename(name: str) -> str:
    """Return the platform-appropriate filename PyInstaller gives ``name``.

    A Windows onedir build's launcher is ``<name>.exe``; every other
    platform's PyInstaller launcher (Linux, macOS) has no extension at all.
    """
    return f"{name}.exe" if sys.platform == "win32" else name
```

`_packaged_executable()` now calls this helper instead of hardcoding `.exe`.

`engine/tests/test_launchers.py` was updated to stop encoding the same
Windows-only assumption in its own fixtures (an `_EXE_SUFFIX` derived from the
*real* platform the suite is running on, so the existing frozen-mode tests
exercise whichever platform they actually run under), and a new,
platform-independent regression test was added that pins **both** branches
explicitly regardless of the host running the suite:

```python
def test_packaged_executable_filename_has_no_extension_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert launchers._packaged_executable_filename("bytefray") == "bytefray"

    monkeypatch.setattr(sys, "platform", "win32")
    assert launchers._packaged_executable_filename("bytefray") == "bytefray.exe"
```

### C.2 pMARS resources made Windows-conditional in the shared specs

`tools/bytefray.spec` and `tools/bytefray_cli.spec` (the two specs whose
onedir output the unified `bytefray`/`bytefray-cli` executables use) used to
unconditionally bundle `pmars/windows/pmars.exe` and its `COPYING` file. On
Linux there is no Linux `pmars` binary checked into the repository (the
redcode94 backend is built from a separately downloaded, license-verified
source archive by `tools/build_pmars_linux.sh` / the
`linux-pmars-build` CI workflow, and that result is not persisted), so
bundling the Windows binary would be dead weight — `battle_engine.pmars` only
ever looks under `pmars/windows` when `os.name == "nt"`. Both specs now guard
the pmars `datas` entries behind `sys.platform == "win32"`; a Linux build
still respects a user-supplied `PMARS_CMD`/`PATH` binary unchanged. No Linux
`.spec` duplicates were created — the four existing specs remain the single,
shared, cross-platform source of truth for both Windows and Linux builds, per
the task's intent.

### C.3 `tools/build_linux.sh`

A new canonical Linux build script mirrors `tools/build_win.ps1`'s structure:
creates/reuses a build venv (default `.venv`, overridable via
`BYTEFRAY_LINUX_BUILD_VENV` — this session used a dedicated
`.venv-rc2-linux-build`), installs the new `linux-build` extra, runs
PyInstaller for all four apps into `dist/linux/`, and runs the same class of
embedded smoke checks Windows already has: a unified-dispatcher branding
resource check, headless (`QT_QPA_PLATFORM=offscreen`) GUI import/startup
smokes for the Designer paths, an isolated-`BYTEFRAY_ROOT` `agents create`
resource smoke, and a final residue check proving no runtime-generated
`agents/` directory leaked into any distributable tree.

### C.4 `pyproject.toml`: `linux-build` extra

A `linux-build` extra (`pyinstaller>=6.6`) was added alongside the existing
`windows-build` extra, kept separate rather than folded together because
`windows-build`'s own `pefile` dependency parses Windows PE binaries only and
has no role in a Linux build.

**No engine, Agent API, ruleset, or gameplay code was touched.** This
diff is limited to packaging/build-tooling and the one genuine
cross-platform frozen-launcher defect.

---

## D. Recovered qualification environment

```text
Build venv:   .venv-rc2-linux-build (recovered, not recreated)
Python:       3.14.4 (/usr/bin/python3.14)
pygame-ce:    2.5.8
PyInstaller:  6.22.2
PySide6:      6.11.2
Classic pygame: absent
```

This venv predates and is unaffected by the launcher fix (the fix lives in
application source, not build tooling), so its qualification versions remain
valid evidence.

---

## E. Focused regression tests (Phase C)

Per the governing continuation task, the full ~3000-test suite and the full
GUI suite were **not** run on this laptop — only the tests covering the
changed code:

```text
.venv/bin/python -m pytest engine/tests/test_launchers.py -q
  -> 17 passed

.venv/bin/python -m pytest engine/tests/test_windows_packaging_spec.py -q
  -> 16 passed
```

`test_windows_packaging_spec.py` (despite its name — it predates the Linux
build and covers all four shared `.spec` files, not just Windows-specific
behavior) executes each spec file's `Analysis`/`EXE`/`COLLECT` calls under a
mocked PyInstaller shim and asserts onedir-layout invariants; this exercises
the exact `bytefray.spec`/`bytefray_cli.spec` files modified in §C.2 and
confirms the new `sys.platform` guard does not break spec execution or the
onedir-shape assertions.

Both runs were serial, single-process, with memory rechecked immediately
before each (see §B) and stayed well clear of the prior danger zone.

Broader regression qualification (the full default suite, the full GUI-marked
suite) is deferred to CI and/or the Windows development machine once this
branch is pushed, consistent with this laptop's known resource constraints.

---

## F. Recovered artifact validation (Phase B — no rebuild performed)

All artifact mtimes postdate the source fix, confirming the existing frozen
trees already contain the launcher remediation — **no PyInstaller rebuild was
performed or needed**:

```text
tools/bytefray.spec                          19:56:34
tools/bytefray_cli.spec                      19:56:43
engine/src/battle_engine/launchers.py        20:10:22
dist/linux/bytefray/bytefray                          20:12:19
dist/linux/bytefray-cli/bytefray-cli                  20:12:27
dist/linux/bytefray-agent-designer/...                20:12:48
dist/linux/bytefray-replay-viewer/...                 20:13:00
dist/bytefray-4.0.0-rc2-dev-linux-x86_64.tar.gz       20:19:24
```

(mtimes are local-clock timestamps from the interrupted session; ordering,
not absolute time, is what matters here.)

Lightweight spot-check of all four primary executables (not a repeat of the
already-completed full recursive `ldd` scan):

```text
file dist/linux/*/{bytefray,bytefray-cli,bytefray-agent-designer,bytefray-replay-viewer}
  -> ELF 64-bit LSB executable, x86-64, dynamically linked,
     interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 3.2.0, stripped
     (all four, identical BuildID prefix — built in the same PyInstaller run)

ldd <each> | grep -i "not found"
  -> (no output for any of the four — 0 unresolved required shared libraries)
```

---

## G. Relocation test (Phase 14)

**Environment note.** `/tmp` on this laptop is a 5.6 GiB `tmpfs` (RAM-backed)
already carrying roughly 2.9 GiB of unrelated, pre-existing scratch from
earlier RC1/v3 qualification work (old venvs and test output directories under
names like `bytefray-rc1-wheel-venv`, `bytefray-v3-rc-test`). Extracting the
194 MB archive there hit `tar: ... Cannot write: Disk quota exceeded`
partway through (the tmpfs filled up, not a disk-space problem on the real
filesystem) — itself a plausible contributor to the original session's memory
pressure, since tmpfs usage is backed by RAM/swap. Those pre-existing files
were left alone rather than deleted speculatively; instead, the relocation
test used `/var/tmp` (confirmed to be on the real 457 GB disk, 332 GB free,
not tmpfs) as the temporary extraction root:

```bash
mkdir -p /var/tmp/bytefray-linux-qualification
tar -xzf dist/bytefray-4.0.0-rc2-dev-linux-x86_64.tar.gz \
    -C /var/tmp/bytefray-linux-qualification
```

Extraction succeeded cleanly (exit 0), and executable permissions were
preserved on all four launchers post-extraction (`-rwxr-xr-x`).

With a fully stripped environment (`env -i`, `PATH=/usr/bin:/bin`, no
`.venv`/`.venv-rc2-linux-build` activated):

```text
./bytefray/bytefray --version
  -> Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4,
     Python 3.14.4
  -> exit 0
```

With an isolated `BYTEFRAY_ROOT` pointed at a fresh `/var/tmp` directory:

```text
bytefray agents
  -> lists all 17 starter + v4 agents (adaptive, claimer, ..., v4_quorum,
     v4_scout, ...) from the bundled agent-template/starter-agent resources
     -> exit 0

bytefray agents validate v4_quorum
  -> agent: v4_quorum / status: valid / api_version: 2 /
     dry_run_action: MOVE operand=64
  -> exit 0
```

`agents validate` specifically exercises the frozen subprocess-relaunch path
`_packaged_executable()` builds — this is a direct, positive confirmation of
the §C.1 fix working correctly from a relocated, extracted artifact outside
the repository, with no build venv active.

A fixed-seed Quorum smoke was then run, reproducing the exact CLI invocation
recorded for the Phase 1B Windows qualification
(`docs/research/v4/V4_RC2_WINDOWS_PYGAME_CE_PACKAGED_QUALIFICATION.md`, §J):

```text
bytefray run --a-type v4_quorum --b-type v4_defender_scout --seed 42 \
  --ticks 3000 --arena 512 --ruleset bytefray-rules-4 --replay <path> --quiet

-> winner: A, score: {'A': 16.0, 'B': 10.0}, ticks: 11,
   termination_reason: last_agent_standing
```

**This exactly matches the Windows Phase 1B reference result** (see §H for
the discrepancy this session found and resolved before reaching this exact
match). The generated replay was then played back through the frozen headless
renderer:

```text
bytefray-replay-viewer --replay <path> --renderer headless --tick-delay 0
  -> ticks 0..11 streamed correctly
  -> [0011] RESULT winner=A score={'A': 16.0, 'B': 10.0}
  -> exit 0
```

No repository-relative resource dependency was observed: every command above
ran with the working directory outside the repo, `BYTEFRAY_ROOT` pointed at an
isolated `/var/tmp` directory, and no repository path on `PATH` or in the
environment. `git status --short` in the repository was confirmed unchanged
before and after this entire phase. Both temporary directories
(`/var/tmp/bytefray-linux-qualification`,
`/var/tmp/bytefray-qualification-root`) were removed afterward.

---

## H. A determinism discrepancy found, investigated, and resolved

The first fixed-seed smoke in this session was run **without** reproducing
the Phase 1B Windows invocation's `--ticks 3000 --arena 512` flags (only
`--seed 42` and the two agent names were carried over from memory). That run
— and two further attempts under `--ruleset bytefray-rules-4-alpha1` and
`--ruleset bytefray-rules-4-alpha2` — all produced `winner: A`,
`termination_reason: last_agent_standing` (qualitatively consistent) but
**different** scores and tick counts (28 ticks/33–27, and 48 ticks/53–47)
than the recorded Windows reference (11 ticks/16–10). Rather than report
either a false exact-match or a false regression, the actual Phase 1B
invocation was located in
`V4_RC2_WINDOWS_PYGAME_CE_PACKAGED_QUALIFICATION.md`, §J, which specifies
`--ticks 3000 --arena 512 --ruleset bytefray-rules-4` — an explicit
`--arena 512` this session's first attempts omitted (defaulting instead to
`--arena 4096`). Reproducing the exact original flags (§G) yielded an exact
match on every field: winner, both scores, tick count, and termination
reason. **This was a reproduction-command gap in this session, not a
cross-platform determinism defect** — the underlying engine is fully
deterministic across platforms for a given, fully-specified invocation.

---

## I. GUI qualification status (environment-limited)

Consistent with the governing task's explicit instruction not to spend
machine resources on desktop automation, no new GUI automation was attempted
in this continuation session. The previous session's findings stand:

- Processes could launch and load their GUI libraries (pygame/SDL,
  Qt/PySide6), but tools launched from the coding/shell environment could not
  reliably get a real application window mapped by the compositor on this
  Wayland desktop; only tiny helper/internal windows appeared in X11
  inspection.
- Screenshot D-Bus access was denied.
- An earlier Phase 1 incident found that `xdotool`-style automation
  destabilized the XWayland helper; this and all similarly aggressive
  automation were avoided again in this continuation.

This is classified as an **automation/session access limitation**, not a
Bytefray-specific renderer defect — the same class of finding
`tools/build_linux.sh`'s own headless (`QT_QPA_PLATFORM=offscreen`) GUI
import/startup smoke (§C.3) is designed to work around for build-time
purposes. **Manual, real-desktop, on-screen verification of the Designer and
Replay Viewer GUIs on Linux remains an outstanding human qualification item**
— it is reported here rather than hidden or claimed as a false PASS.

---

## J. glibc compatibility analysis (Phase 15)

```text
ldd --version   -> ldd (Ubuntu GLIBC 2.43-2ubuntu2.3) 2.43
```

This prototype was built on Ubuntu 26.04, a very recent release. Inspecting
the versioned symbol requirements of the main launcher and the largest bundled
native libraries (not an exhaustive recursive symbol scan — a targeted check
of the launcher plus the libraries most likely to set the ceiling):

```text
dist/linux/bytefray/bytefray                    -> up to GLIBC_2.14
_internal/libpython3.14.so.1.0                  -> up to GLIBC_2.38
_internal/libstdc++.so.6                        -> up to GLIBC_2.38
_internal/libbz2.so.1.0                         -> up to GLIBC_2.4
_internal/liblzma.so.5                          -> up to GLIBC_2.34
```

**The binding constraint is GLIBC_2.38** (from the bundled CPython 3.14 and
libstdc++ builds), which post-dates Ubuntu 22.04 LTS (glibc 2.35) and Debian
12 "Bookworm" (glibc 2.36). A binary built on Ubuntu 26.04 should therefore
**not** be advertised as running on those still-widely-deployed baselines, or
on anything similarly old, even though PyInstaller has already eliminated the
need for a system Python interpreter.

**Architectural conclusion:** PyInstaller removes the runtime dependency on
system Python, but Linux glibc symbol-versioning compatibility remains bounded
by whatever glibc was present on the *build* host, not by anything
Bytefray-specific. This is the standard PyInstaller/Linux packaging
trade-off, not a defect introduced by this Phase.

**Recommended official Linux release-build baseline:** build on **Ubuntu
24.04 LTS** (glibc 2.39) going forward — an actively-supported LTS release
that is old enough to run on most currently-deployed desktops, then test the
resulting artifact on newer distributions (the inverse of what this
prototype did). Note that even a 24.04-built artifact would still require
glibc ≥ 2.39, which excludes 22.04/Debian 12; if broader compatibility than
that is desired for a future release, an even older baseline (e.g. Ubuntu
22.04 LTS or a manylinux-style base image) should be evaluated deliberately
against Bytefray's actual minimum-supported-distro policy, which does not yet
exist and is out of this phase's scope to set. The production build host was
**not** changed in this task.

---

## K. Second-distro qualification (Phase 16)

No second Linux machine or environment was available to this session, and per
the governing task, none was manufactured on this low-spec laptop (no VM, no
large container stack).

```text
Cross-distro execution remains a follow-up qualification.
```

A future run on Ubuntu 24.04 LTS (or whatever baseline §J's policy ultimately
selects) is sufficient to close this out.

---

## L. Packaging-format recommendation (Phase 17)

### PyInstaller onedir + tar.gz (what this prototype used)

Already proven end to end in this and the prior session: builds cleanly,
requires no additional tooling beyond PyInstaller (already used for Windows),
preserves the self-contained Python/runtime behavior that is the whole point
of this effort, is trivially inspectable/debuggable (`ls`/`ldd`/`file` all
work directly against the onedir tree, unlike a compressed single-file
format), archives as a completely ordinary GitHub release asset, and has zero
FUSE or runtime-mount dependency.

### AppImage

Single-file distribution is a real user-convenience win, and desktop
integration (`.desktop`/icon registration) is possible. Against that: AppImage
extraction/mounting depends on FUSE being available (not guaranteed on every
target system, including some sandboxed/server/WSL environments), it adds a
new build tool and packaging step on top of the already-qualified onedir tree
(effectively wrapping it, not replacing it), and it would need its own
qualification/maintenance burden (mount-vs-extract-and-run behavior, icon
theming, `.desktop` file correctness) that RC2 has not budgeted for.

### Flatpak

Offers the strongest desktop integration and sandboxing story, and a path to
distribution-store presence — but its manifest/runtime/permissions model is
substantial additional complexity for a game-adjacent CLI-and-GUI tool suite
whose actual current requirement is "run these four apps that already work as
onedir bundles." This is excessive for RC2's scope.

### Recommendation

**Ship and test the tar.gz onedir bundle for RC2.** It is already built,
qualified, and proven relocatable independent of the source checkout, build
venv, and system Python (§G). Defer AppImage until the basic Linux binary
distribution has broader distro qualification (§K) — wrapping an
already-working onedir tree in AppImage is a comparatively low-risk follow-up
once there is a real multi-distro compatibility baseline to build it against.
Flatpak is not recommended for consideration before RC2 ships.

---

## M. Archive

```text
File: dist/bytefray-4.0.0-rc2-dev-linux-x86_64.tar.gz
Size: 194,383,935 bytes (~185 MiB)
MD5:    b3328cf97535558d36f377dfd2f6ca1f
SHA256: 6d07f2e5c70c38c6a454ccc71881aa7ddf27f22784f7e2aae0a7488246fa81a7
```

Executable permissions (`-rwxr-xr-x`) on all four primary launchers were
confirmed preserved directly in the archive listing (`tar -tzv`) and again
after extraction in §G. The `dev` in the filename is intentional —
this is a development-status prototype archive, not a published RC2 release
asset, and remains a build artifact rather than source-controlled content
(not added to git).

---

## N. Lint/type checks (Phase 20)

Run only over the files this phase changed:

```text
mypy engine/src/battle_engine/launchers.py
  -> Success: no issues found in 1 source file

ruff check engine/src/battle_engine/launchers.py engine/tests/test_launchers.py
  -> no findings

ruff check tools/bytefray.spec tools/bytefray_cli.spec
  -> 6 findings each (UP009 encoding comment, I001 import order,
     4x F821 "undefined name" on Analysis/PYZ/EXE/COLLECT)
```

**All 6 findings per spec file are pre-existing**, confirmed by running ruff
against the unmodified `git show HEAD:tools/bytefray.spec` — the identical
finding set (same codes, same lines relative to the file) exists in the
version of the file before this phase's `sys.platform` conditional was added.
The `F821` findings in particular are an inherent, unfixable characteristic of
PyInstaller `.spec` files: `Analysis`/`PYZ`/`EXE`/`COLLECT` are names
PyInstaller injects into the exec environment when it runs a spec file, not
real imports, so no static linter can see where they come from. This phase's
diff did not introduce any new finding category or line; it is reported here
as pre-existing debt, not fixed, matching this phase's narrow scope (the same
treatment the Phase 1B report gave the pre-existing `v4_quorum` `RUF012`
findings, which were independently reconfirmed unchanged in this session).

---

## O. Files changed / commits

```text
M engine/src/battle_engine/launchers.py
M engine/tests/test_launchers.py
M pyproject.toml
M tools/bytefray.spec
M tools/bytefray_cli.spec
A tools/build_linux.sh
A docs/research/v4/V4_RC2_LINUX_SELF_CONTAINED_PROTOTYPE.md
```

`agents/Nemesis/agent.py-v1` (pre-existing, unrelated untracked file) and all
build outputs (`dist/`, `build/`, `.venv-rc2-linux-build/`) were confirmed
excluded from every commit via inspection of `git status`/`git diff --stat`
before staging.

---

## P. Final decision

Every gate this Linux continuation session could exercise passed: the
recovered source diff was confirmed coherent and limited to the described
Linux packaging work and the one genuine launcher defect; the existing
post-fix frozen artifacts were confirmed intact and were not rebuilt; focused
launcher and packaging-spec tests both passed cleanly; all four frozen
executables show zero unresolved required shared libraries; the archive
relocates and runs correctly outside the repository with no build-venv or
system-Python dependency; `v4_quorum` validates from the frozen artifact; and
a fixed-seed Quorum match, once run with the exact historical invocation,
reproduced the Phase 1B Windows result exactly (winner, both scores, tick
count, and termination reason), giving strong cross-platform determinism
evidence. The two gates not fully closed — on-screen GUI verification and
second-distro qualification — are reported honestly as environment-limited
and deferred, respectively, per the governing task's explicit instruction not
to convert limitations into false PASS claims.

```text
PASS — self-contained Linux PyInstaller baseline recovered and qualified for RC2
```

No engine, Agent API, or gameplay semantics changed. Nothing was published,
tagged, or merged to `main`.
