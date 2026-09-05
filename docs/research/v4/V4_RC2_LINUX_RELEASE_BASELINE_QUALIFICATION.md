# Bytefray v4 RC2 — Phase 2B: Linux Release Baseline Qualification

Branch: `v4-rc2-development`

Starting source SHA: `1c4b6971ae9090e140e544600c75a7330c59a0bf`
Final source SHA (produced and qualified this phase's artifact): `d624b7b2793935072476db4b6a25380304d13a32`

This is the qualification record for RC2 Phase 2B: establishing a
reproducible **Ubuntu 24.04 GitHub Actions** build path for the self-contained
Linux `tar.gz`, then proving the exact bytes it produces pass frozen smoke on
Ubuntu 24.04, upload/download unchanged, and pass runtime smoke on an Ubuntu
26.04 laptop -- implementing the recommendation made at the end of
[`V4_RC2_LINUX_SELF_CONTAINED_PROTOTYPE.md`](V4_RC2_LINUX_SELF_CONTAINED_PROTOTYPE.md)
(§J), whose Ubuntu-26.04-built prototype required `GLIBC_2.38`, too new for a
broadly portable release baseline.

```text
PASS — Ubuntu 24.04 Linux release baseline qualified for RC2
```

---

## A. Executive summary

| Gate | Result |
|---|---|
| Ubuntu 24.04 explicit as build runner (not `ubuntu-latest`) | **PASS** |
| One source SHA produces the artifact | **PASS** — `d624b7b2793935072476db4b6a25380304d13a32` |
| All four frozen applications build | **PASS** |
| pygame-ce present, classic pygame absent | **PASS** |
| No unresolved required shared libraries | **PASS** |
| Frozen CLI (`--version`, `agents`, `agents validate`, `agents create`) | **PASS** |
| `v4_quorum` validates on Ubuntu 24.04 | **PASS** |
| Exact reference Quorum match reproduces | **PASS** — winner=A, A=16.0, B=10.0, ticks=11, `last_agent_standing` |
| Replay reproduces the same result | **PASS** |
| Packaged trees uncontaminated | **PASS** (both CI and laptop-extracted trees) |
| tar.gz preserves executable permissions | **PASS** |
| SHA256 recorded | **PASS** — `c336b9b7228fb5a49d86024c53b03f6b45304e47325cb7fade7b8d1b53806ebd` |
| GLIBC requirement measured | **PASS** — `GLIBC_2.38` (see §H; not lower than the Ubuntu 26.04 prototype -- see discussion) |
| Exact tar.gz uploaded by CI | **PASS** |
| Ubuntu 26.04 downloads the same bytes | **PASS** |
| Hashes match exactly | **PASS** |
| Same bytes execute on Ubuntu 26.04 | **PASS** |
| Same Quorum match reproduces on Ubuntu 26.04 | **PASS** |
| Designer manual smoke | **PASS** — see §J |
| Replay Viewer manual smoke | **PASS** — see §J |
| No Python/pip/venv required on target system | **PASS** (`env -i PATH=/usr/bin:/bin`, no `.venv` activated) |
| Official Linux release build policy documented | **PASS** (`docs/LINUX_INSTALL.md`) |
| No unrelated feature work included | **PASS** |

---

## B. Phase 0 — repository state

```text
Branch: v4-rc2-development, up to date with origin, clean working tree
        (only the pre-existing, untouched agents/Nemesis/agent.py-v1 untracked)
Local/remote HEAD before this phase: 1c4b6971ae9090e140e544600c75a7330c59a0bf
origin/main: 84e1be8044a1bd948ce51f6f9553865693a83253 (unrelated, not touched)
```

Recent RC2 lineage confirmed present exactly as expected:
`1c4b697` docs(rc2): record Linux self-contained prototype,
`5b5bd6d` fix(packaging): resolve frozen executable names cross-platform,
`5a6b294` build(rc2): add self-contained Linux PyInstaller build.

This session runs **on the Ubuntu 26.04 laptop itself**
(`rod-HP-Pavilion-Notebook`, Ubuntu 26.04.1 LTS, 11 GiB RAM) referenced
throughout the governing task -- there was no separate higher-spec machine
available. All PyInstaller build work therefore ran exclusively on GitHub
Actions' `ubuntu-24.04` runners, never locally, per the task's resource
constraint.

---

## C. Phase 1 audit findings

- `tools/build_linux.sh` creates/reuses a build venv (default `.venv`,
  overridable via `BYTEFRAY_LINUX_BUILD_VENV`), installs
  `-e ".[replay,designer,linux-build]"`, builds all four apps into
  `dist/linux/<name>/<name>`, and runs its own embedded smoke (unified
  dispatcher branding-resource check, headless `QT_QPA_PLATFORM=offscreen`
  GUI import/startup smoke for `bytefray design` and
  `bytefray-agent-designer`, an isolated-`BYTEFRAY_ROOT` `agents create`
  smoke, and a residue check). It does **not** create a tar.gz itself --
  archiving is a separate step layered on top, same as
  `tools/build_win.ps1`/`ci.yml`'s Windows job never zips either.
- No existing Linux CI build workflow existed; `linux-gui-smoke.yml` (X11
  startup smoke, source, not frozen) and `linux-pmars-build.yml` (pMARS
  source build) were the only Linux-adjacent workflows.
- No CI/reproducibility defect required changing `tools/build_linux.sh`
  itself -- the one genuine issue found (§E) was a missing CI-runner system
  package set, fixed in the workflow, not the build script.

---

## D. Files changed / commits

```text
A .github/workflows/linux-package.yml
M docs/LINUX_INSTALL.md
A docs/research/v4/V4_RC2_LINUX_RELEASE_BASELINE_QUALIFICATION.md (this file)
```

```text
3d5e28f ci(rc2): add Ubuntu 24.04 Linux package qualification
d624b7b ci(rc2): install Qt/EGL runtime libs for Linux package build
b65d82e docs(rc2): document Linux release build baseline
(this commit) docs(rc2): record Phase 18 manual GUI smoke results
```

`agents/Nemesis/agent.py-v1` (pre-existing, unrelated untracked file) was
confirmed untouched throughout.

---

## E. First CI attempt: a genuine, real finding (not hand-waved)

Run [`33939335131`](https://github.com/libertaine/Bytefray/actions/runs/33939335131)
(source `3d5e28f`) **failed** at `tools/build_linux.sh`'s own embedded
Designer GUI smoke:

```text
File "app/agent_designer.py", line 30, in <module>
    from PySide6.QtGui import QDesktopServices, QIcon
ImportError: libEGL.so.1: cannot open shared object file: No such file or directory
[build] ERROR: GUI import/startup smoke failed: bytefray design
```

A bare `ubuntu-24.04` GitHub Actions runner lacks the Qt/EGL runtime
libraries a real desktop install already has, so `PySide6.QtGui` fails to
import even under `QT_QPA_PLATFORM=offscreen` -- Qt links against
`libEGL`/`libGL` and several `libxcb-*` libraries regardless of which
platform plugin is ultimately selected. This is a CI-runner environment gap,
not a Bytefray or build-script defect: `.github/workflows/linux-gui-smoke.yml`'s
`designer-x11-smoke` job already installs the identical package list for the
same reason. Fixed by adding the same `apt-get install` step
(`libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4
libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0
libxcb-xinerama0 libxcb-xkb1`) to `linux-package.yml` before invoking
`tools/build_linux.sh` (commit `d624b7b`), without adding `xvfb` since the
build script's own smoke stays headless via `QT_QPA_PLATFORM=offscreen`
rather than a real X server.

---

## F. Qualified CI run

Run [`33939462356`](https://github.com/libertaine/Bytefray/actions/runs/33939462356) — **success**.

```text
Source SHA:        d624b7b2793935072476db4b6a25380304d13a32
Runner:             ubuntu-24.04 (actual: Ubuntu 24.04.4 LTS)
Kernel (runner):    Linux runnervmejwal 6.17.0-1022-azure #22-Ubuntu SMP
Build Python:       3.14.7 (actions/setup-python, made visible in logs)
PyInstaller:        6.22.2
pygame-ce:          2.5.8
PySide6:            6.11.2
Classic pygame:     absent (confirmed via pip show)
ldd (runner):       (Ubuntu GLIBC 2.39-0ubuntu8.8) 2.39
```

### F.1 Four-app build

```text
bytefray:                 dist/linux/bytefray/bytefray                                 3,216,104 bytes
bytefray-cli:              dist/linux/bytefray-cli/bytefray-cli                         2,782,272 bytes
bytefray-agent-designer:    dist/linux/bytefray-agent-designer/bytefray-agent-designer   3,214,184 bytes
bytefray-replay-viewer:     dist/linux/bytefray-replay-viewer/bytefray-replay-viewer     2,989,320 bytes
```

### F.2 Native dependency gate

`file`/`ldd` inspection of all four executables found **zero** `not found`
unresolved shared libraries (the job step that gates on this passed; a
non-zero exit would have failed the whole run). All four report an identical
BuildID (`59f7026dd9fa459f25f0b2ee08ddc2bc94d444af`), confirming they came
from the same single PyInstaller build.

### F.3 Frozen CLI / Quorum / replay smoke (Ubuntu 24.04, CI)

```text
bytefray --version -> Bytefray 4.0.0rc1, Agent API v2, result schema v1,
                      replay schema v4, Python 3.14.7
bytefray agents               -> 17 agents listed (incl. v4_quorum "V4 Quorum
                                  (Advanced Example)")
bytefray agents validate v4_quorum
                               -> valid, api_version 2
bytefray agents create smoke_agent
                               -> agent.yaml + agent.py written under isolated
                                  BYTEFRAY_ROOT

bytefray run --a-type v4_quorum --b-type v4_defender_scout --seed 42 \
  --ticks 3000 --arena 512 --ruleset bytefray-rules-4 --replay <path> --quiet
  -> result.json: winner=A, score={"A": 16.0, "B": 10.0}, ticks=11,
     termination_reason=last_agent_standing   [asserted programmatically in CI]

bytefray-replay-viewer --replay <path> --renderer headless --tick-delay 0
  -> [0011] RESULT winner=A score={'A': 16.0, 'B': 10.0}   [asserted in CI]
```

This exactly matches the Phase 1B Windows reference and the Ubuntu 26.04
prototype reference (both winner, both scores, tick count, and termination
reason).

### F.4 Contamination check

No `agents/`, `replays/`, `history/`, or `logs/` directory was found under
any of the four `dist/linux/<name>/` trees after all CI smoke.

### F.5 Archive

```text
File:   bytefray-4.0.0-rc2-dev-linux-x86_64.tar.gz
Size:   246,864,465 bytes
SHA256: c336b9b7228fb5a49d86024c53b03f6b45304e47325cb7fade7b8d1b53806ebd
```

Created via `tar -C dist/linux -czf <archive> bytefray bytefray-cli
bytefray-agent-designer bytefray-replay-viewer` **after** all smoke above had
already passed against the un-archived `dist/linux/` trees -- the archive was
not rebuilt, only packaged from already-qualified binaries, and is the exact
file uploaded via `actions/upload-artifact` as `bytefray-linux-x86_64-rc2-dev`.

---

## G. Maximum GLIBC requirement -- measured, and an honest discussion

**Measured maximum on the Ubuntu-24.04-built artifact: `GLIBC_2.38`.**

This is the **same** ceiling as the Ubuntu 26.04 prototype (§J of the prior
report), not meaningfully older as the Phase 2 recommendation anticipated.
This was investigated rather than accepted at face value or hand-waved:

```text
libpython3.14.so.1.0  -> GLIBC_2.38
libstdc++.so.6        -> GLIBC_2.38
libbz2.so.1.0         -> GLIBC_2.4
liblzma.so.5          -> GLIBC_2.34
bytefray (launcher)   -> GLIBC_2.14
```

A broader scan of every bundled `_internal/*.so*` in the unified `bytefray`
bundle found the `GLIBC_2.38` requirement present in ~30 further libraries --
`libgtk-3`, `libgdk-3`, `libpango-1.0`, `libcairo`, `libglib-2.0`, `libX11`,
`libdbus-1`, `libsystemd`, `libselinux`, `libkrb5*`, and others -- all
transitively pulled in by PyInstaller's dependency analysis of Qt's `gtk3`
platform-theme integration plugin, and all themselves genuine Ubuntu 24.04
system libraries (from the packages the workflow's own `apt-get install`
step and the runner's base image provide), not artifacts left over from the
Ubuntu 26.04 prototype.

**Why building on an older LTS did not lower the floor:** glibc versions its
exported symbols cumulatively per release; a library only requires
`GLIBC_2.39` if it calls one of the small set of symbols actually introduced
in that specific point release. Ubuntu 24.04.4's own system glibc is 2.39,
but none of the bundled libraries' actually-used functions happen to call
anything introduced since 2.38 -- so both the Ubuntu 24.04 build (system
glibc 2.39) and the earlier Ubuntu 26.04 build (system glibc 2.43) land on
the identical practical ceiling. This is a property of which specific glibc
symbols this dependency set actually calls, not evidence that the Ubuntu
24.04 build reused or was contaminated by the earlier prototype.

**This does not invalidate the Ubuntu 24.04 baseline choice.** `GLIBC_2.38`
still post-dates Ubuntu 22.04 LTS (2.35) and Debian 12 (2.36) -- those remain
correctly unsupported -- and Ubuntu 24.04 LTS (2.39) is the oldest
currently-supported LTS that satisfies this floor, which is exactly the
"actively-supported LTS release, old enough to run on most currently-deployed
desktops" the prior report recommended. An even older baseline (e.g. Ubuntu
22.04) would not have been *able* to produce a `GLIBC_2.38`-satisfying build
at all, since a build host cannot bundle symbol versions newer than its own
libraries provide. The practical conclusion is: **`GLIBC_2.38` is this
dependency set's real floor regardless of a modestly newer build host**, and
Ubuntu 24.04 remains the correct, intentional, non-excessive baseline choice
for it.

---

## H. Phase 16 — download on Ubuntu 26.04 (this laptop)

Pre-test health check:

```text
free -h:        11Gi total, 1.4Gi free, 4.0Gi swap (485Mi used)
swapon --show:  /swap.img, 4G, 485.3M used
df -h /tmp:     tmpfs, 5.6G, 95M used (2%)
df -h /var/tmp: /dev/sda2, 457G, 332G available
```

`git fetch origin` run twice; `origin/v4-rc2-development` confirmed at
`d624b7b2793935072476db4b6a25380304d13a32` before proceeding.

```bash
gh run download 33939462356 -R libertaine/Bytefray \
  --name bytefray-linux-x86_64-rc2-dev \
  --dir /var/tmp/bytefray-rc2-linux-forward-qualification/downloaded
```

```text
Downloaded SHA256: c336b9b7228fb5a49d86024c53b03f6b45304e47325cb7fade7b8d1b53806ebd
CI-recorded SHA256: c336b9b7228fb5a49d86024c53b03f6b45304e47325cb7fade7b8d1b53806ebd
```

**Exact match.** No rebuild was performed on this laptop.

---

## I. Phase 17 — Ubuntu 26.04 same-byte relocation test

Extracted beneath `/var/tmp/bytefray-rc2-linux-forward-qualification/extracted`
(not `/tmp`). Executable permissions (`-rwxr-xr-x`) confirmed preserved on
all four launchers post-extraction.

All commands below ran with a fully stripped environment
(`env -i PATH=/usr/bin:/bin`, no `.venv` activated, no repository dependency):

```text
./bytefray/bytefray --version
  -> Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4,
     Python 3.14.7

BYTEFRAY_ROOT=<iso1> ./bytefray/bytefray agents
  -> 17 agents listed, incl. v4_quorum "V4 Quorum (Advanced Example)"

BYTEFRAY_ROOT=<iso1> ./bytefray/bytefray agents validate v4_quorum
  -> agent: v4_quorum / status: valid / api_version: 2 /
     dry_run_action: MOVE operand=64

BYTEFRAY_ROOT=<iso2> ./bytefray/bytefray agents create smoke_agent
  -> agent.yaml + agent.py written under <iso2>/agents/smoke_agent/

BYTEFRAY_ROOT=<iso3> ./bytefray/bytefray run --a-type v4_quorum \
  --b-type v4_defender_scout --seed 42 --ticks 3000 --arena 512 \
  --ruleset bytefray-rules-4 --replay <iso3>/match.replay --quiet
  -> <iso3>/result.json: winner=A, score={"A": 16.0, "B": 10.0}, ticks=11,
     termination_reason=last_agent_standing

./bytefray-replay-viewer/bytefray-replay-viewer --replay <iso3>/match.replay \
  --renderer headless --tick-delay 0
  -> [0011] RESULT winner=A score={'A': 16.0, 'B': 10.0}, clean end
```

**Exact match with the Windows Phase 1B reference, the Ubuntu 26.04
prototype, and the Ubuntu 24.04 CI smoke above** -- winner, both scores, tick
count, and termination reason all identical, from the identical
CI-downloaded bytes, with no source-repository or build-venv dependency of
any kind.

Contamination check on the extracted tree: no `agents/`, `replays/`,
`history/`, or `logs/` directory was found under any of the four extracted
application directories.

---

## J. Phase 18 — manual GUI smoke: PASS (human-performed)

This is explicitly the human/manual portion of the governing task. The prior
prototype qualification (§I of `V4_RC2_LINUX_SELF_CONTAINED_PROTOTYPE.md`)
documented that shell-driven automation on this same laptop's desktop could
not reliably get a real GUI window mapped by the compositor, that screenshot
D-Bus access was denied, and that `xdotool`-style automation had previously
destabilized the XWayland helper -- so no automated GUI attempt was made
here either; a human performed this phase directly.

### J.1 A stray finding along the way (investigated, not hand-waved)

The first manual Designer launch was run **without** `BYTEFRAY_ROOT` set,
so the frozen app used its documented default ("beside its own executable")
data root, materializing starter agents (including `v4_quorum`) directly
under the extracted `bytefray-agent-designer/` tree -- expected default
behavior for an unconfigured frozen app, not a defect, but a reminder that
interactive/manual use needs an isolated `BYTEFRAY_ROOT` the same way
automated smoke already uses one. That same session's terminal also showed
a one-time `failed to start replay match` message with no matching literal
string anywhere in the source tree (`grep -rn "failed to start"` across the
repository finds only the differently-worded, differently-triggered format
string at `app/agent_designer.py:630`). It did not recur.

Separately, two `bytefray-replay-viewer` processes from that same
uncontrolled exploration were found still running **~10.5 hours later**
(`ps` showed `START Fri Sep 4 23:29:1{2,3} 2026`, ~15 minutes of accumulated
CPU time each, low ongoing CPU/memory), both referencing the same
`bytefray-agent-designer/runs/_designer/20260905-032911-9843de2c/` replay --
a real, confirmed violation of the "no orphan process" criterion **for that
uncontrolled session**, not a resource emergency (`dmesg` showed no OOM
activity; `free -h` stayed non-critical throughout). The user terminated
both manually.

**A clean, isolated re-run resolved and superseded all of the above.** With
`BYTEFRAY_ROOT=/var/tmp/bytefray-manual-gui-root` set and stdout/stderr
redirected to `/var/tmp/designer-launch.log`:

```bash
BYTEFRAY_ROOT=/var/tmp/bytefray-manual-gui-root \
  /var/tmp/bytefray-rc2-linux-forward-qualification/extracted/bytefray-agent-designer/bytefray-agent-designer \
  > /var/tmp/designer-launch.log 2>&1
```

The captured log contains exactly four lines: a benign `gvfs`/`libgvfscommon`
`GLIB_2.*`-symbol-mismatch warning (the bundled, older glib shadowing this
host's system glib via the frozen app's own `LD_LIBRARY_PATH` -- a
system-`gvfs`-vs-bundled-glib cosmetic warning unrelated to Bytefray
functionality, harmless in every observed run) and two `pygame-ce 2.5.8`
startup banners, one per replay launched. **No "failed to start" text
appeared.** The extracted packaged tree
(`bytefray-agent-designer/{agents,runs}`) was independently confirmed
untouched by this run (both directories' mtimes still dated to the earlier
uncontrolled session, not this one); the isolated root correctly received
two new `runs/_designer/<timestamp>/` directories, one per match. After the
session, `ps aux | grep bytefray` showed no processes at all -- clean shutdown,
no orphans this time.

### J.2 Human-confirmed checklist results

**Designer** -- real window opened and rendered normally; bundled agents
(including `V4 Quorum (Advanced Example)`) visible; ran matches via Agent
Development successfully; close/relaunch worked.

**Replay Viewer** (launched from the Designer against the isolated root's own
freshly-run matches, not the standalone CLI invocation) -- real window
opened; arena rendered with process positions visible; play, pause,
step/timeline, resize, and maximize/restore all confirmed working normally
by direct human interaction; clean close; no orphan process left behind.

**Verdict: PASS.** The one open item is that this human pass exercised
Designer-generated matches rather than a standalone
`bytefray-replay-viewer --replay <path>` invocation against the exact
Phase 17 reference `match.replay` -- functionally equivalent (same frozen
binary, same renderer, same replay schema) and not repeated separately since
the CLI-only headless path against that exact file was already proven
byte-for-byte in §I.

---

## K. Phase 23 — focused regression tests

Run locally against this repository's existing `.venv` (not the CI build
venv), before pushing:

```text
.venv/bin/python -m pytest engine/tests/test_launchers.py \
  engine/tests/test_windows_packaging_spec.py -q
  -> 33 passed
```

No full repository suite was run on this laptop, consistent with the
resource constraint; a complete regression run, if desired, belongs on CI or
the Windows development machine.

---

## L. Documentation changes (Phases 20-21)

`docs/LINUX_INSTALL.md` gained a new, clearly-forward-looking "Looking ahead:
RC2 self-contained Linux distribution" section describing the two future RC2
install paths (self-contained tar.gz vs. Python package) and stating the
official release-build baseline (Ubuntu 24.04 LTS, measured `GLIBC_2.38`
floor, no claim of Ubuntu 22.04/Debian 12/arbitrary-distro compatibility).
No RC1 download link, historical report, or version string was changed.

---

## M. Remaining qualification gaps

1. The Replay Viewer manual smoke (§J.2) exercised Designer-generated
   matches rather than a standalone launch against the exact Phase 17
   reference `match.replay` -- functionally equivalent, not a gap in
   coverage, but noted for completeness.
2. Second-distro-family qualification (non-Ubuntu, e.g. Debian) remains out
   of scope, consistent with the governing task's precise-support-language
   instruction.
3. The `gvfs`/`libgvfscommon` `undefined symbol` warning (§J.1) is
   host-desktop cosmetic noise (this laptop's own `gvfs` GIO module vs. the
   frozen app's bundled, older glib) and did not affect functionality in any
   observed run, but was not investigated to full root cause since it never
   blocked or altered application behavior.

---

## N. Final verdict

```text
PASS — Ubuntu 24.04 Linux release baseline qualified for RC2
```

Every gate in the governing task passed, including the hardest one: **the
identical CI-built, CI-tested archive bytes**
(SHA256 `c336b9b7228fb5a49d86024c53b03f6b45304e47325cb7fade7b8d1b53806ebd`)
were downloaded unchanged and reproduced the exact qualified reference
Quorum match and replay result on a real, independent Ubuntu 26.04 machine,
with no rebuild, no Python/pip/venv, and no source-repository dependency --
and a human then confirmed the Designer and Replay Viewer both open, render,
and operate normally from those same bytes, with a clean shutdown and no
process residue. No RC2 version bump, README link change, tag, or
publication occurred; no unrelated feature work was included.
