# Bytefray v4 RC Path — Linux Prequalification (Phase 3 Cross-Platform Handoff)

Branch tested: `v4-rc1-development`
Exact SHA tested: `01a1718658f46d161e5879e815682dd7562b141d` (short `01a1718`)
Qualification-report branch: `v4-rc1-linux-qualification` (created from the tested SHA; this
report is committed only here, per the governing task's instruction not to commit it to
`v4-rc1-development`)

This is an independent Linux/desktop cross-platform qualification of the exact commit the
Windows source qualification reported as `PHASE 3 QUALIFIED — READY FOR RC PATH PHASE 4`. It does
not redesign Bytefray, add gameplay features, or change compatibility contracts. No merge, tag,
publish, or RC1 creation was performed.

---

## A. Executive result

| Gate | Result |
|---|---|
| Exact Phase 3 SHA tested? | PASS |
| Full Linux suite | PASS (0 failures) |
| Stable-v4 deterministic placement | PASS |
| Alpha2 ↔ stable-v4 equivalence | PASS |
| CLI defaults | PASS |
| Stable-v4 evaluation | PASS |
| Real Agent Designer GUI | PASS |
| Real Replay Viewer GUI | PASS |
| Perspective/Director/Fight Night | PASS |
| Historical compatibility smoke | PASS |
| Multi-entrant smoke | PASS |
| RC-blocking Linux defect found? | NO |
| Ready for Phase 4? | YES |

---

## B. Environment

```text
OS:        Ubuntu 26.04.1 LTS (Resolute Raccoon)
Kernel:    Linux 7.0.0-30-generic, x86_64
Session:   XDG_SESSION_TYPE=wayland, XDG_CURRENT_DESKTOP=ubuntu:GNOME
           DISPLAY=:0 (XWayland available), WAYLAND_DISPLAY=wayland-0
           -> a real native-Wayland desktop session, not headless/offscreen/WSL
Python:    3.11.9 (.venv/ at repo root, pre-existing, reused per project convention)
pip:       26.2.1
git:       2.53.0
pytest:    9.1.1     ruff: 0.16.3     mypy: 2.3.1
PySide6:   6.11.1 (QApplication.platformName() == "wayland", confirmed live)
pygame:    2.6.1 (SDL 2.28.4)
PyYAML:    6.0.3
```

`docs/LINUX_INSTALL.md` states that CI only validates Pygame/Designer startup under X11/Xvfb and
that "native Wayland remains unvalidated." This session ran the real GUI workflow under **native
Wayland**, which is new coverage beyond both CI and the Windows Phase 3 report (which explicitly
could not drive a literal GUI session at all and fell back to service-layer testing).

---

## C. Repository provenance

```text
remote:               git@github.com:libertaine/Bytefray.git
branch:                v4-rc1-development
HEAD (local, before):  01a1718658f46d161e5879e815682dd7562b141d
origin/v4-rc1-development: 01a1718658f46d161e5879e815682dd7562b141d   (identical)
git status --short (before and after all testing): only the pre-existing, unrelated,
  untracked agents/Nemesis/agent.py-v1 (an old sibling of the tracked agent.py in the same
  directory; present before this qualification began; not part of the candidate tree)
```

The local checkout already resolved to the exact Phase 3 handoff commit; no fetch/switch was
required to reach it. `git log --oneline -10 origin/v4-rc1-development` confirmed the expected
Phase 1-3 commit history.

---

## D. Test-suite qualification

### D.1 Environment/bootstrap

The existing `.venv/` at the repo root (Python 3.11.9) already had an editable install with every
dev/GUI dependency (`ruff`, `mypy`, `pytest`, `pygame`, `PySide6`) present, per this repository's
own convention (`docs/LINUX_INSTALL.md`, `CONTRIBUTING.md`) of reusing a valid existing venv
rather than creating a second one. No `sudo pip` was used; no global Python state was touched.

One environment-only defect was found and fixed in this venv (see §K.1); the fix touched only
git-ignored local build metadata, never tracked source.

### D.2 Baseline static qualification

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check .` | All checks passed |
| Engine mypy | `mypy engine/src/battle_engine` | Success, 101 source files |
| Client mypy | `mypy client/src/battle_client` | Success, 15 source files |
| Whitespace | `git diff --check` | clean |

Identical to the Windows Phase 3 results.

### D.3 Full Linux test suite (authoritative command: `python -m pytest`, per AGENTS.md:49 /
CONTRIBUTING.md:73)

**Final, authoritative run** (after the environment fix in §K.1, on the unmodified candidate
tree):

```text
2931 passed, 5 skipped, 2 deselected, 0 failed, in 283.68s (0:04:43)
```

Total universe: 2938 (2931 + 5 + 2), reconciling exactly with every prior run in this session and
consistent with Windows Phase 3's 2936 (main suite) + 2 (GUI-marked, deselected by the default
`-m "not gui"`) = 2938. Windows reported 14 skips; Linux reports 5 — an expected, acceptable
platform-specific difference (see §K.2), not a forced match. **0 unexpected failures**, satisfying
the task's actual bar.

An earlier run using a bare `pytest` invocation (not the documented command) surfaced 5 apparent
failures; all 5 were root-caused, none is a Bytefray or Linux defect (§K.1, §K.2).

### D.4 Designer GUI suite (real display, not offscreen)

```text
python -m pytest -m gui tests/            -> 253 passed, 6 deselected, 0 failed  (27s)
python -m pytest -m gui                   -> 2 passed, 2936 deselected, 0 failed (client/tests pygame smoke; 4.6s)
```

Both ran against the real native-Wayland session (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`), not
`QT_QPA_PLATFORM=offscreen`. 253 reconciles as growth from Phase 1's own reported 251-test
baseline. This is strictly more GUI evidence than Windows Phase 3 achieved on Windows.

---

## E. Deterministic/cross-platform evidence

### E.1 Stable-v4 seeded placement (arenas 256/512/1024)

All 11 vectors pinned in `engine/tests/test_v4_alpha2_placement.py`
(`ALPHA2_PLACEMENT_VECTORS`) were independently reproduced bit-for-bit on Linux via a direct
`seeded_seat_starts(...)` call, spanning entrant counts 2/3/4/8, arenas 256/512/1024, and seeds
0/1/3/5/7/9/42:

```text
(2,256,0)->(82,219)  (2,256,1)->(24,162)  (2,512,0)->(209,63)  (2,512,1)->(380,263)
(2,512,7)->(324,167) (2,1024,0)->(238,503) (2,1024,42)->(721,912)
(3,256,0)->(135,54,200) (3,512,3)->(406,134,52)
(4,1024,5)->(127,790,983,725) (8,1024,9)->(336,266,686,962,854,166,53,599)
```

All matched exactly. The Phase 1 research report's own cross-validation vector
(`resolve_v4_seed_geometry(bytefray-rules-4-alpha2, 512, 3) == (495, 387)`) also reproduced
exactly, and — critically — `resolve_v4_seed_geometry(bytefray-rules-4, 512, 3)` returned the
**identical** `(495, 387)`, confirming stable v4 and alpha2 share identical placement geometry for
identical inputs on Linux, as the frozen contract requires.

The full suite's own `test_pinned_alpha2_placement_vectors`,
`test_pinned_seed_vectors_match_the_research_report`, and the full parametrized
determinism/invariant/firewall suite in `test_v4_alpha2_placement.py` all passed.

### E.2 Alpha2 ↔ stable-v4 equivalence

`engine/tests/test_v4_stable_ruleset_equivalence.py` (23 tests: 2/3/4-entrant grids across
arenas 256/512/1024 and 5 seeds, hydra/nemesis multi-process cells, a forced tick-limit case) —
**all pass**. `engine/tests/test_v4_historical_immutability.py` (2 tests) reconfirmed the pinned
canonical identities unchanged on Linux:

```text
alpha1: match_b53e76a536d65e9f35b9e560 / result_4eac520d48af9cd1ae859365
alpha2: match_779a09b9950d0e4db27b5ddb / result_50d49c7732848a9541fc9a93
```

`engine/tests/test_ruleset_agent_compatibility.py` (25 tests) — all pass.

### E.3 Cross-platform deterministic match corpus (generated this session)

Eight real `bytefray run` executions under `bytefray-rules-4`, covering 2-entrant matches at
arenas 256/512/1024 (seeds 1/7/42), a multi-process matchup (`hydra_alpha2` vs `nemesis_alpha2`,
arena 512 seed 7), and a forced short tick-limit case (5 ticks). Each case's resolved starts
matched the independently-computed seeded geometry exactly:

| case | arena | seed | resolved starts | winner | ticks | termination |
|---|---|---|---|---|---|---|
| c1 | 256 | 1 | (24, 162) | tie | 40 | tick_limit |
| c2 | 512 | 1 | (380, 263) | tie | 40 | tick_limit |
| c3 | 1024 | 1 | (967, 306) | tie | 40 | tick_limit |
| c4 | 512 | 7 | (324, 167) | tie | 40 | tick_limit |
| c5 | 512 | 42 | (485, 203) | tie | 60 | tick_limit |
| c6 (multi-process) | 512 | 7 | (324, 167) | A | 4 | last_agent_standing |
| c7 (forced tick-limit) | 512 | 3 | (495, 387) | tie | 5 | tick_limit |
| c8 (decisive score) | 512 | 1 | (380, 263) | B | 200 | tick_limit |

All `ruleset_id` fields recorded `bytefray-rules-4`; all `match_id`/`result_id` were unique
per-run identity-bearing values as expected.

---

## F. CLI qualification

All four cases run as real, live commands (not code inspection):

| Case | Command | Recorded ruleset | Result |
|---|---|---|---|
| API v2, omitted `--ruleset` | `bytefray run --a-type v4_claimer --b-type v4_scout ...` | `bytefray-rules-4` | PASS |
| API v1, omitted `--ruleset` | `bytefray run --a-type hunter --b-type raider ...` | `bytefray-rules-2` | PASS |
| Explicit alpha2 | `bytefray run ... --ruleset bytefray-rules-4-alpha2` | `bytefray-rules-4-alpha2` (preserved) | PASS |
| API v1 + `bytefray-rules-4` | `bytefray run --a-type hunter --b-type raider --ruleset bytefray-rules-4` | rejected pre-execution, exit 2, `ERROR: Ruleset 'bytefray-rules-4' does not support entrant metadata: A (python, Agent API 1), B (python, Agent API 1).`, no output artifacts written | PASS (fail-closed) |
| API v2 + `bytefray-rules-2` | `bytefray run --a-type v4_claimer --b-type v4_scout --ruleset bytefray-rules-2` | rejected pre-execution, exit 2, symmetric message, no output artifacts written | PASS (fail-closed) |

Additionally reconfirmed live: `agents evaluate --arena-size 1024` under the omitted (v4)
methodology is rejected pre-execution (`... is incompatible with the stable v4 evaluation
methodology, which is pinned to 512 cells ...`), matching Phase 3's own documented guard.

All results are identical in kind to the Windows Phase 3 CLI audit (§F of that report).

---

## G. Evaluation qualification

Reproduced Phase 3's own defect-fix verification command
(`agents evaluate v4_claimer --opponents v4_scout --seeds 1 --ticks 20`, omitted `--ruleset`) and
confirmed the human-readable console line still reads:

```text
Arena alignment: ruleset_v4_seeded_placements -- translation robustness not evaluated
```

(never `fixed`) — the Phase 3 F.6-adjacent fix holds on Linux.

A full default-seed run (`agents evaluate v4_claimer --opponents v4_scout --ticks 20`, omitted
`--ruleset` and `--seeds`) persisted an artifact with:

```text
schema_version: 7          identity_version: 7
rules_compatibility_id: bytefray-rules-4
arena_alignment_mode: ruleset_v4_seeded_placements
matrix_size: 16  (8 seeds x both orientations x 1 opponent = 16N, N=1)
effective arena_size: 512
```

`bytefray agents evaluations show` and `... --verify` both worked, reporting `health: healthy`,
`verified: True`, and correctly displaying `bytefray=4.0.0a4` in the recorded execution context
(post-fix, §K.1). A comparison of two compatible stable-v4 evaluations (`agents evaluations
compare`) correctly reported `comparable: 16`, `changed_condition: 0`, and correctly distinguished
the two different candidates.

### G.1 Evaluation failure-state integrity

A genuine failed-cell evaluation (`agents evaluate v4_claimer --opponents hunter --ruleset
bytefray-rules-4 --seeds 1 --ticks 20`, a real Agent-API-v1 opponent under stable v4) persisted:

```text
lifecycle_state: finished_with_failures
complete: False
```

with both cells `status: failed`, `error_code: ruleset_agent_unsupported`, and an honest
`failed cells:` console section naming the exact incompatibility. Linux does not produce
`finished`/`complete: true` for a failed evaluation — the Phase 1 F.6 remediation holds.

---

## H. GUI qualification

Both Agent Designer and Replay Viewer were driven for real on the live native-Wayland desktop
session (`QApplication.platformName() == "wayland"`), never `QT_QPA_PLATFORM=offscreen`.

**Automated evidence**: this repository's own `-m gui` regression suite (253 Designer tests + 2
pygame tests, §D.4) ran against the real display and passed completely.

**Interactive evidence** (this session, real widget interaction via `QTest.mouseClick` on the
actual running `AgentDesigner` window — genuine Qt event delivery through real production code,
not a mock): launched the real window, selected "Ruleset v4 — Current / Recommended (Agent API
v2)" from the real Ruleset combo box (confirming stable v4 is labeled current/recommended, not an
alpha), selected the real "V4 Claimer [Python]"/"V4 Scout [Python]" agents, clicked the real "Run
Match" button. This spawned a real `bytefray run` subprocess (600 ticks, arena 512) that completed
with `Winner: B; ruleset: bytefray-rules-4`, writing `result.json`/`replay.jsonl`/`summary.json`
to `runs/_designer/<timestamp>/` (the documented source-checkout data-root convention). The real
"Open Last Replay" button was then clicked, which spawned a real pygame Replay Viewer subprocess
with the sibling `trace.jsonl` auto-attached.

Screenshots were captured via Qt's own `QWidget.grab()` (no external screenshot tool needed — see
note below) at each step and show clean, unclipped rendering, correct labels, and no
missing-Qt-plugin diagnostics.

*Tooling note*: this machine's external screenshot tools were unusable for this task —
`gnome-screenshot` failed with a broken snap-linked `libpthread` symbol mismatch, and the
`org.freedesktop.portal.Screenshot` D-Bus interface requires interactive user consent unavailable
in this session. Both are machine/tooling issues, not Bytefray defects. `QWidget.grab()`
(self-capture, needing no compositor permission) was used instead and gave complete visual
evidence for every screenshot in this report.

---

## I. Replay/spectator qualification

Using the real Designer-produced stable-v4 match (`result.json`/`replay.jsonl`/`trace.jsonl` all
present):

| Check | Result |
|---|---|
| Broadcast replay | Works — header shows `Ruleset bytefray-rules-4 \| runtime python \| arena 512`, correct entrant panels/scores/territory, tick counter |
| `V` cycles Perspective Cam | Works — Broadcast -> Entrant A -> Entrant B, confirmed via on-screen header and hidden-opponent fields (`UNKNOWN`, `Score ?`) proving the knowledge boundary holds |
| Spectator Director (`G`) | Works — status bar shows `DIRECTOR CONTACT 3tps` |
| Fight Night (`N`) | Works — on-screen caption `FIGHT NIGHT · B KNOWS / T5 B · CONTACT` |
| Timeline/normal playback | Works — tick counter advances correctly frame to frame |
| Rendering exceptions/crashes | None; clean exit, `pygame.get_init() == False` after quit |
| Display backend | XWayland is present (`DISPLAY=:0`) but pygame/SDL's actual backend was not independently forced; no crash or fallback issue was observed either way |

### I.1 Replay without trace (§16)

A copy of the run directory with `trace.jsonl` deliberately removed (working from a copy; the
original evidence was not destroyed) was opened in Replay Viewer:

- Opens without error; Broadcast mode renders correctly.
- The header's `[V to switch]` perspective hint is correctly omitted (no trace, no perspective
  claim).
- Pressing `V` is a safe no-op — no crash, no fabricated Perspective data;
  `PerspectiveManager` is correctly never constructed (`None`) rather than exposing a
  half-initialized state.

---

## J. Historical compatibility

One real match executed under each of the five registered identities, arena 512 where
applicable, seed 5, 10 ticks:

| Ruleset | Recorded `ruleset_id` | Recorded replay `schema_version` |
|---|---|---|
| `bytefray-rules-1` (VM/blob) | `bytefray-rules-1` | 3 |
| `bytefray-rules-2` | `bytefray-rules-2` | 3 |
| `bytefray-rules-4-alpha1` | `bytefray-rules-4-alpha1` | 4 |
| `bytefray-rules-4-alpha2` | `bytefray-rules-4-alpha2` | 4 |
| `bytefray-rules-4` | `bytefray-rules-4` | 4 |

All five distinct and correct. Replay Viewer visually confirmed for both the oldest (VM/schema-3
grid-based rendering) and current (spatial-process rendering) artifact families — both render
correctly with no crash, each retaining its own recorded identity.

### J.1 Multi-entrant smoke

A real 3-entrant stable-v4 match (`v4_claimer`/`v4_scout`/`v4_local_defender`, arena 512, seed 3,
60 ticks) executed successfully: seeded placement valid (three non-overlapping starts), recorded
`ruleset_id: bytefray-rules-4`, and the replay opened and rendered all three entrants correctly in
Broadcast view.

---

## K. Linux-specific issues

### K.1 Stale local editable-install version metadata (Environment issue — fixed for this session, no source change)

```text
severity:        Low (environment-only; blocked one test until corrected)
reproduction:    importlib.metadata.version("bytefray") returned "4.0.0a3" while
                 pyproject.toml/tools/installer.iss both already declare "4.0.0-alpha4"/"4.0.0a4"
                 at the tested commit. Caused test_installer_versions_match_package_and_release_tag
                 to fail.
root cause:      Two separate stale, git-ignored local build-metadata artifacts left over from
                 before this checkout's pyproject.toml version bump (commit 010c3f6, the base of
                 the whole RC branch): .venv/lib/python3.11/site-packages/bytefray-4.0.0a3.dist-info
                 and a repo-root bytefray.egg-info/ directory (both timestamped identically, both
                 confirmed git-ignored and untracked). importlib.metadata resolved the stale
                 egg-info first.
candidate impact: None. pyproject.toml and tools/installer.iss already agree with each other at
                 the tested commit; only this one local venv's incidental build metadata was
                 stale.
fix:             `pip install -e . --no-deps --no-build-isolation` (regenerates dist-info) and
                 `rm -rf bytefray.egg-info` (stale duplicate). Both actions touched only
                 git-ignored local artifacts; `git status`/`git rev-parse HEAD` were identical
                 before and after.
disposition:     Not an RC blocker; not a candidate-tree change. No action needed beyond ensuring
                 a fresh venv/editable-install step is part of Phase 4's documented Linux
                 environment setup (already true per docs/LINUX_INSTALL.md).
```

### K.2 Bare `pytest` misses four `tools`-reexport tests (Self-corrected invocation error, not a defect)

```text
severity:        None (no code change; investigation-only)
reproduction:    Running bare `pytest ...` (the console-script entry point) instead of the
                 documented `python -m pytest` (AGENTS.md:49, CONTRIBUTING.md:73) fails
                 test_tool_wrapper_reexports_permanent_{aggregation,analyzer}_contract,
                 test_tool_wrapper_reexports_the_pair_analyzer_contract, and
                 test_tool_wrapper_reexports_projection_contract_and_cli_rejects_mismatch with
                 ImportError: cannot import name 'X' from 'tools' (unknown location).
root cause:      `python -m pytest` prepends the current working directory to sys.path (a
                 general Python `-m` behavior); the bare `pytest` console script does not. These
                 four tests import the real top-level tools/ package (a namespace package, no
                 __init__.py) by relying on the repo root being on sys.path. This is a property
                 of how pytest is invoked, not of the source tree, and is orthogonal to Linux vs.
                 Windows.
candidate impact: None once the documented command is used. Confirmed clean:
                 `python -m pytest engine/tests/test_spectator_aggregation.py::... (all 4)` -> 4 passed.
disposition:     Not a defect. Use the documented `python -m pytest` command (this session's
                 subsequent runs all did).
```

### K.3 Inconsistent sibling-artifact file permissions (Packaging/Phase 4 issue — non-blocking)

```text
severity:        Low
reproduction:    In any match output directory, `result.json` and `replay.jsonl` are created
                 mode 0600 while sibling `summary.json`/`trace.jsonl` are created mode 0644
                 (default umask). Confirmed via `ls -la` on real match-output directories
                 generated in this session (both Designer- and CLI-produced).
root cause:      `result.json`/`replay.jsonl` are written via `tempfile.mkstemp()` + atomic
                 rename (engine/src/battle_engine/match_service.py); Python's tempfile module
                 deliberately creates files at mode 0600 for security, and the atomic rename
                 preserves that mode rather than normalizing it to the process umask the way an
                 ordinary `open(path, "w")` (used for summary.json/trace.jsonl) would. This
                 permission-bit distinction is invisible on Windows/NTFS, which is presumably why
                 it was not previously reported.
candidate impact: None observed in this qualification -- every workflow exercised (CLI, Designer,
                 Replay Viewer, evaluation) read these files back successfully as the same OS
                 user. Would only matter for a multi-user/service-account packaging or install
                 scenario where a different principal needs to read a completed match's
                 result/replay.
disposition:     Packaging/Phase 4 issue. Recommend Phase 4 decide on a deliberate, consistent
                 file-permission policy for match-output artifacts (e.g. explicit os.chmod after
                 the atomic rename) rather than incidentally inheriting mkstemp's default. Not an
                 RC blocker.
```

No RC-blocking Linux defect was found. No product/source-tree code was ever modified.

---

## L. Source integrity

```text
Before all testing:  git status --short -> only pre-existing agents/Nemesis/agent.py-v1 (untracked)
                     git rev-parse HEAD -> 01a1718658f46d161e5879e815682dd7562b141d
After all testing:   git status --short -> identical (only the same pre-existing untracked file)
                     git rev-parse HEAD -> 01a1718658f46d161e5879e815682dd7562b141d   (unchanged)
```

No tracked file was added, modified, or removed by this qualification. All generated match/replay/
evaluation artifacts landed in git-ignored `runs/` directories or this session's own scratch
directory, exactly as expected. The two environment-metadata corrections (§K.1) touched only
git-ignored local build artifacts.

---

## M. Phase 4 recommendation

The exact Phase 3 candidate (`01a1718`) is qualified on a real native-Wayland Ubuntu 26.04 desktop
with zero RC-blocking defects. All frozen v4 contracts (stable Ruleset identity, Agent API v2,
replay schema 4, evaluation schema/identity 7, default-resolution table) reproduce identically to
the Windows Phase 3 source. GUI qualification here is stronger than Windows Phase 3's own (which
could not drive a literal GUI session at all): this session drove a real, visible, interactive
Agent Designer -> Simple match -> Replay Viewer workflow end-to-end on native Wayland, plus the
full existing 253-test Designer GUI regression suite, all against the real display.

The candidate can proceed into Phase 4 packaging/RC1 publication qualification.

```text
LINUX PREQUALIFICATION PASSED — READY FOR RC PATH PHASE 4
```
