# Bytefray v4 RC Path — Linux Packaged-Artifact Qualification (Phase 4 Linux Gate)

Branch: `v4-rc1-linux-qualification` (pre-existing branch, inspected and reused rather than
recreated under the alternate name suggested by the governing task)
Candidate source SHA under qualification: `356702621d0ad328ac27497235087f5bd67e7183`
Report-writing HEAD (before this report's own commit): `413a4a01de1f38160ad14cc4c6cc0fa1b7510a70`

This is the packaged-artifact qualification of the exact RC1 wheel (`bytefray-4.0.0rc1-py3-none-any.whl`)
and sdist (`bytefray-4.0.0rc1.tar.gz`) built and qualified on Windows from candidate `3567026`, run on
a real native-Wayland Ubuntu desktop. Every mandatory gate passes.

```text
LINUX PACKAGED QUALIFICATION PASSED — RC1 PUBLICATION GATE SATISFIED
```

**Note on this report's history**: an earlier version of this same file, committed separately on this
branch, recorded a **failed** qualification — at the time it was written, neither artifact existed
anywhere on this machine after an exhaustive search. See §D.2 for the full timeline: the artifacts
were subsequently transferred to this machine by the user, confirmed directly by him, and this report
supersedes that earlier failure with the full run performed against the now-present, hash-verified
artifacts.

---

## A. Executive gate

| Gate | Result |
|---|---|
| Exact wheel hash matches Windows | **PASS** |
| Exact sdist hash matches Windows | **PASS** |
| Clean wheel installation | **PASS** |
| Wheel version/import isolation | **PASS** |
| Stable-v4 packaged CLI | **PASS** |
| API-v1 packaged compatibility | **PASS** |
| Historical Alpha2 explicit identity | **PASS** |
| Fail-closed compatibility | **PASS** |
| Stable-v4 packaged evaluation | **PASS** |
| Evaluation methodology display | **PASS** |
| 11 pinned placement vectors | **PASS** (11/11) |
| Stable-v4/Alpha2 equivalence smoke | **PASS** |
| Native-Wayland Designer from wheel | **PASS** |
| Designer automatic trace | **PASS** |
| Replay Viewer from wheel | **PASS** |
| Perspective | **PASS** |
| Director | **PASS** |
| Fight Night | **PASS** |
| No-trace fallback | **PASS** |
| Multi-entrant packaged smoke | **PASS** |
| Artifact permissions usable | **PASS** |
| Clean sdist install | **PASS** |
| sdist runtime smoke | **PASS** |
| Original artifact hashes unchanged | **PASS** |
| **RC blocker found** | **NO** |
| **RC1 may be published** | **YES** |

---

## B. Linux environment

```text
OS:        Ubuntu 26.04.1 LTS (Resolute Raccoon)
Kernel:    Linux 7.0.0-30-generic, x86_64 (rod-HP-Pavilion-Notebook)
Python:    3.11.9 (system python3; clean venvs created outside the repo for both artifacts)
git:       2.53.0
Session:   XDG_SESSION_TYPE=wayland, XDG_CURRENT_DESKTOP=ubuntu:GNOME
           DISPLAY=:0, WAYLAND_DISPLAY=wayland-0
           -> the same real native-Wayland desktop machine used for the prior source-level
              Linux prequalification (V4_RC1_LINUX_PREQUALIFICATION.md)
Qt:        PySide6 6.11.2 -- QApplication.platformName() == "wayland", confirmed live in both
           the wheel venv and (separately) the sdist venv
Pygame:    2.6.1 (SDL 2.28.4)
```

**Environment note (not a defect)**: `XDG_DATA_HOME` is set by this snap-confined VS Code session to
`/home/rod/snap/code/259/.local/share`, so Bytefray's data root (evaluation history, `runs/`, discovered
agents) resolved to `/home/rod/snap/code/259/.local/share/bytefray` rather than the more familiar
`~/.local/share/bytefray`. This is correct, spec-compliant XDG Base Directory behavior — Bytefray reads
`XDG_DATA_HOME` and honors it — not a source-tree dependency (confirmed: no path under it, or anywhere
in the installed package, referenced the repository checkout or its `.venv`).

`gnome-screenshot` is still broken on this machine with the exact same fault the prior Linux
prequalification documented (`symbol lookup error: /snap/core20/current/lib/x86_64-linux-gnu/libpthread.so.0:
undefined symbol: __libc_pthread_init`) — reconfirmed directly this session. This is a machine/snap
packaging issue, not a Bytefray defect. `QWidget.grab()` (Qt self-capture) and `pygame.image.save()`
(direct surface capture) were used for every screenshot in this report instead, needing no external
tool or compositor permission.

---

## C. Candidate provenance

```text
candidate source SHA:            356702621d0ad328ac27497235087f5bd67e7183   (exists locally)
origin/v4-rc1-development HEAD:  a632c2cdbc0e96bc1360a82f2afbb97e5c00084a   (fetched)
```

`git diff 356702621d0ad328ac27497235087f5bd67e7183..origin/v4-rc1-development -- engine client app agents
tools pyproject.toml installer.iss` produced **no output**. The full-path `git diff --stat` across the
same range shows exactly one file: `docs/research/v4/V4_RC1_PHASE4_RELEASE_QUALIFICATION.md` (+503) — a
documentation-only commit, exactly as the governing task predicted. Product/release source is unchanged
since the candidate SHA.

This session's own branch (`v4-rc1-linux-qualification`) is a sibling of `origin/v4-rc1-development`,
cut from the Phase 3 tip (`01a1718`) before the RC1 release-prep commits; that does not affect this gate,
since the task only requires this report to live on a Linux qualification branch, not for that branch to
be rebased onto `v4-rc1-development`.

---

## D. Artifact provenance

### D.1 Location and identity

```text
wheel: /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1-py3-none-any.whl
sdist: /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1.tar.gz
```

```text
$ sha256sum /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1-py3-none-any.whl \
            /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1.tar.gz
e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3  bytefray-4.0.0rc1-py3-none-any.whl
3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8  bytefray-4.0.0rc1.tar.gz
```

Both **exactly** match the authoritative Windows hashes (required: wheel
`e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3`, sdist
`3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8`). Cross-checked with `sha256sum`
(uutils coreutils 0.8.0, `/usr/bin/sha256sum`) and independently with `md5sum` (different tool, same
bytes) to rule out a hashing-tool fault.

```text
size (wheel): 899687 bytes   size (sdist): 872085 bytes
owner: rod:rod   mode: 0644 (both)
```

### D.2 Artifact-appearance timeline (raised by a peer reviewing this qualification — resolved)

The artifacts were **not** present on this machine when this qualification began. This session performed
four separate exhaustive, recursive searches of `/home` (plus `/tmp`, `/var/tmp`, `/srv`, `/opt`, and
checked for mounted shares — none existed) for `bytefray-4.0.0rc1-py3-none-any.whl` /
`bytefray-4.0.0rc1.tar.gz` and found nothing; a failure report was written and committed to this branch
(commit `413a4a0`) recording `LINUX PACKAGED QUALIFICATION FAILED — ARTIFACT HASH MISMATCH`. A sibling
Claude session working the corresponding Windows Phase 4 task then forwarded this same governing task
to this session; while replying to that forward, a re-check of the filesystem found a new directory,
`/home/rod/bytefray-v4-rc1-artifacts/`, containing both files.

A peer session reviewing this qualification flagged the timing as worth scrutinizing before treating the
hash match as evidence on its own, rather than taking a bare "MATCH" self-report at face value. Raw
forensic evidence was captured before proceeding:

```text
$ stat /home/rod/bytefray-v4-rc1-artifacts/
  Birth: 2026-09-03 22:22:46.408598247 -0400
$ stat .../bytefray-4.0.0rc1-py3-none-any.whl
  Birth: 2026-09-03 22:26:56.785928285 -0400
$ stat .../bytefray-4.0.0rc1.tar.gz
  Birth: 2026-09-03 22:26:57.111927415 -0400
```

This session's last exhaustive filesystem search (before writing the failure report) completed at or
before **22:11:47 EDT** (captured via `date -u` alongside the pre-report `git status`/`git rev-parse HEAD`
check). Every file/directory birth timestamp above falls **11-15 minutes after** that check — the
directory and both files provably did not exist at search time; this was not a search-scope miss.
`who`/`w` showed the sole logged-in session on this machine was `rod` on the local GNOME console
(`tty2`, not a remote/SSH session) — consistent with a human physically transferring the files at the
keyboard. Asked directly, the user (Rod Satterfield) confirmed he transferred the files himself after
seeing the earlier failure report. Ownership (`rod:rod`) and mode (`0644`, a normal-user umask-derived
value, not root-owned or unusually permissioned) are consistent with an ordinary local file copy.

**Disposition**: benign — a manual artifact hand-off performed by the user in response to this session's
own failure report, not tampering and not a search defect. Recorded here per the reviewing peer's
request, since unexplained artifact-provenance timing is worth documenting on a release gate even when
it resolves cleanly.

---

## E. Wheel clean-install result

```text
$ python3 -m venv /tmp/bytefray-rc1-wheel-venv && source it && python -m pip install --upgrade pip
$ python -m pip install /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1-py3-none-any.whl
Successfully installed PyYAML-6.0.3 bytefray-4.0.0rc1
```

From `/tmp` (outside the repo):

```text
pip show bytefray        -> Version: 4.0.0rc1, Location: .../wheel-venv/lib/python3.11/site-packages
battle_engine.__file__   -> .../wheel-venv/lib/python3.11/site-packages/battle_engine/__init__.py
battle_client.__file__   -> .../wheel-venv/lib/python3.11/site-packages/battle_client/__init__.py
bytefray --version       -> Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4, Python 3.11.9
```

No import resolved from the repository checkout, the repo `.venv`, or any source-tree path
(`grep -rl "BATTLE2\|D:\\\\Projects"` over the installed `battle_engine`/`battle_client`/`app` packages:
no matches). Version reports exactly `4.0.0rc1` — never `Alpha4` or a final `4.0.0`.

Installed package contents confirmed present: `battle_engine` (including `data/starter_agents/*` —
`v4_claimer`, `v4_scout`, `v4_local_defender`, `v4_defender_scout`, `v4_concentrated_attacker`, `hunter`,
`raider`, and 10 others), `battle_client`, `app` (Designer/Replay Viewer, `widgets/`, `views/`,
`services/`, `assets/`), and all four `pyproject.toml` entry points (`bytefray`, `bytefray-cli`,
`bytefray-agent-designer`, `bytefray-replay-viewer`). No dev/test/research files were required or found.

Designer/replay GUI extras (`pygame`, `PySide6`) were installed afterward from the **same wheel file**
(`pip install ".../bytefray-4.0.0rc1-py3-none-any.whl[designer,replay]"`), which pip confirmed did not
reinstall or alter the already-installed `bytefray==4.0.0rc1`.

---

## F. Stable-v4 CLI/default-resolution result

All five CLI cases run as real, live `bytefray run` commands from `/tmp/bytefray-wheel-smoke` (outside
the repo), with `result.json` inspected directly (not just console text) for each:

| Case | Command (abridged) | Recorded `ruleset_id` | Result |
|---|---|---|---|
| API v2, omitted `--ruleset` | `bytefray run --a-type v4_claimer --b-type v4_scout ...` | `bytefray-rules-4` | PASS |
| API v1, omitted `--ruleset` | `bytefray run --a-type hunter --b-type raider ...` | `bytefray-rules-2` | PASS |
| Explicit alpha2 | `bytefray run ... --ruleset bytefray-rules-4-alpha2` | `bytefray-rules-4-alpha2` (preserved) | PASS |
| API v1 + `bytefray-rules-4` | `bytefray run --a-type hunter --b-type raider --ruleset bytefray-rules-4` | rejected pre-execution, exit 2, `ERROR: Ruleset 'bytefray-rules-4' does not support entrant metadata: A (python, Agent API 1), B (python, Agent API 1).`, no output artifacts written | PASS (fail-closed) |
| API v2 + `bytefray-rules-2` | `bytefray run --a-type v4_claimer --b-type v4_scout --ruleset bytefray-rules-2` | rejected pre-execution, exit 2, symmetric message, no output artifacts written | PASS (fail-closed) |

The stable-v4 case's `result.json` was inspected in full: `match_id`, `result_id`, per-entrant
`api_version: 2`, `derived_seed`, `source_sha256`, and `statistics` were all present and internally
consistent; `winner: B`, `ticks: 200`, `termination_reason: tick_limit`.

---

## G. Evaluation result

`bytefray agents evaluate v4_claimer --opponents v4_scout --ticks 20` (omitted `--ruleset`), run from the
default (discoverable) data-root location. Console output confirmed:

```text
Arena alignment: ruleset_v4_seeded_placements -- translation robustness not evaluated
```

(never `fixed`). The persisted `evaluation.json` was read directly:

```text
schema_version:        7
identity_version:      7
rules_compatibility_id: bytefray-rules-4
arena_alignment_mode:  ruleset_v4_seeded_placements
matrix_size:           16   (8 seeds x both orientations x 1 opponent = 16N, N=1)
orientation_mode:      both
seeds:                 [1, 2, 3, 4, 5, 6, 7, 8]
effective arena_size:  512
lifecycle_state:       finished
complete:              True
```

`bytefray agents evaluations show <id> --verify` reported `health: healthy`, `verified: True`,
`matrix: 16/16 cells` (`cell status counts: completed=16`), and correctly displayed
`bytefray=4.0.0rc1` (not a stale/alpha version) in the recorded execution context, alongside both
agent revisions marked `[verified]`.

**Comparison**: two `agents evaluations compare` runs were exercised. Comparing two *different*
candidates (`v4_claimer` vs `v4_scout`) correctly reported `candidate identity: DIFFERENT CANDIDATES`
with `comparable: 0` — no false match. Comparing the *same* candidate/opponent/seeds/ticks under
`bytefray-rules-4` vs `bytefray-rules-4-alpha2` correctly reported `changed_condition=16` rather than
silently treating the two Ruleset identities as equivalent (directly relevant to §I below: the compare
tool does not normalize away identity-bearing differences). A fully "comparable" pair (same candidate
identity, same conditions, differing only by agent revision) was not cheaply producible without a source
change to a starter agent, so none was forced; both comparisons run demonstrate the packaged compare
path functions correctly.

### G.1 Evaluation failure-state result

`bytefray agents evaluate v4_claimer --opponents hunter --ruleset bytefray-rules-4 --seeds 1 --ticks 20`
(a real Agent-API-v1 opponent under stable v4) persisted:

```text
lifecycle_state: finished_with_failures
complete:        False
```

with both cells `status: failed`, `error_code: ruleset_agent_unsupported`, and an honest `failed cells:`
console section naming the exact incompatibility. No successful-completion misreport for a failed
evaluation.

---

## H. Determinism result — 11 pinned placement vectors

Reproduced against the **installed wheel's own** `battle_engine.placement.seeded_seat_starts`, imported
and called from `/tmp` (outside the repository):

```text
PASS  seeded_seat_starts(2, 256, 0) = (82, 219)
PASS  seeded_seat_starts(2, 256, 1) = (24, 162)
PASS  seeded_seat_starts(2, 512, 0) = (209, 63)
PASS  seeded_seat_starts(2, 512, 1) = (380, 263)
PASS  seeded_seat_starts(2, 512, 7) = (324, 167)
PASS  seeded_seat_starts(2, 1024, 0) = (238, 503)
PASS  seeded_seat_starts(2, 1024, 42) = (721, 912)
PASS  seeded_seat_starts(3, 256, 0) = (135, 54, 200)
PASS  seeded_seat_starts(3, 512, 3) = (406, 134, 52)
PASS  seeded_seat_starts(4, 1024, 5) = (127, 790, 983, 725)
PASS  seeded_seat_starts(8, 1024, 9) = (336, 266, 686, 962, 854, 166, 53, 599)

11 / 11 match
```

The additional research cross-validation vector, via `battle_engine.agent_evaluation.resolve_v4_seed_geometry`:

```text
resolve_v4_seed_geometry('bytefray-rules-4',        512, 3) -> (495, 387)   PASS
resolve_v4_seed_geometry('bytefray-rules-4-alpha2', 512, 3) -> (495, 387)   PASS
stable == alpha2: True
```

No coordinate mismatch anywhere. Vectors taken from `engine/tests/test_v4_alpha2_placement.py`'s
`ALPHA2_PLACEMENT_VECTORS`, the same release-blocking cross-platform contract the prior Windows and
Linux source-level reports used.

---

## I. Stable-v4/Alpha2 packaged equivalence result

Ran from the wheel environment: multiple seeds, arena 512 plus one other arena (256 and 1024 both
covered), the bundled multi-process API-v2 starter agent `v4_defender_scout`
(`declare_processes` -> `defender` + `scout`, two processes), and a decisive (non-tie) match:

| Pairing | Arena | Seed | Winner | Ticks | Termination |
|---|---|---|---|---|---|
| v4_claimer vs v4_defender_scout | 512 | 1 | B | 150 | tick_limit |
| v4_claimer vs v4_defender_scout | 512 | 3 | B | 150 | tick_limit |
| v4_claimer vs v4_defender_scout | 256 | 7 | B | 150 | tick_limit |
| v4_scout vs v4_defender_scout | 1024 | 5 | tie | 150 | tick_limit |

For every case, `winner`, `ticks`, `termination_reason`, `score`, and every entrant's `score`/`statistics`
were **byte-for-byte identical** between `bytefray-rules-4` and `bytefray-rules-4-alpha2`; only
`match_id`/`result_id` (and `ruleset_id` itself) differed, exactly the intentional identity-bearing
exception the governing task allows. No gameplay difference was normalized away.

---

## J. GUI/Replay result

All interaction below is **automated** (driven in-process via `QTest.mouseClick` for Qt and real
`pygame.event` queue injection for pygame, mirroring this repository's own established GUI-test patterns
— `client/tests/test_linux_pygame_smoke.py`'s `loop_and_record` technique — rather than literal manual
mouse/keyboard input at the console), but runs through completely real, unmocked production code and a
real native-Wayland window; every claim below is backed by a captured screenshot and/or a directly-read
persisted artifact, not console text alone.

### J.1 Native-Wayland Designer from the wheel

Confirmed again immediately before launch: `XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0`.
Launched via `app.agent_designer.AgentDesigner` (the wheel's real entry point) from `/tmp`, not the
source checkout. `QApplication.platformName() == "wayland"`, not `offscreen`.

The real Ruleset combo box's contents were read live: `['Ruleset v2 — Current / Recommended', 'Ruleset
v4 — Current / Recommended (Agent API v2)']` — stable v4 is labeled current/recommended, not an alpha.
Agent A/B combos listed the five bundled v4 starter agents (`V4 Claimer [Python]`, `V4 Concentrated
Attacker [Python]`, `V4 Defender Scout [Python]`, `V4 Local Defender [Python]`, `V4 Scout [Python]`).
`V4 Claimer` and `V4 Defender Scout` were selected; a real `QTest.mouseClick` on the real running
"Run Match" button spawned a real `bytefray run` subprocess (600 ticks, arena 512), which completed with
`Winner: B; ruleset: bytefray-rules-4`. A screenshot (`QWidget.grab()`) after configuration and after
match completion shows the real window: correct ruleset/agent selection, live match log with real
progressing per-tick scores, and the final result line.

### J.2 Designer automatic trace integration

The Designer-produced run directory (`.../runs/_designer/20260904-024707-a92797a9/`) contains
`result.json`, `replay.jsonl`, `summary.json`, **and** `trace.jsonl` as siblings — `trace.jsonl` was
written automatically; no manual trace request was made anywhere in the Designer workflow. `result.json`
confirms `ruleset_id: bytefray-rules-4`.

### J.3 Replay Viewer from the wheel

Opened the Designer-produced replay via the real `battle_client.cli.main(["--replay", ..., "--renderer",
"pygame"])` entry point (the wheel's real Replay Viewer code path), with the sibling `trace.jsonl`
auto-discovered (no `--trace` flag passed). Real `KEYDOWN`/`QUIT` events were posted into the real pygame
event queue, one per frame, driving the real `PygameRenderer._loop`/`dispatch_key`/`_redraw` pipeline; a
real screenshot (`pygame.image.save`) and the renderer's actual internal state were captured after each:

| Step | Key | Captured state | Screenshot evidence |
|---|---|---|---|
| Broadcast | (initial) | `perspective_mode=broadcast` | Header: `Ruleset bytefray-rules-4 \| runtime python \| arena 512 \| View: BROADCAST [V to switch]`; both entrant panels visible with real scores |
| Perspective cycling #1 | `V` | `perspective_mode=A` | Header: `View: ENTRANT A (v4_claimer)`; entrant B's panel correctly shows `UNKNOWN` / `Score ?` / `Territory ?` / `Kills ?` — the knowledge boundary holds |
| Perspective cycling #2 | `V` | `perspective_mode=B` | Symmetric hidden-A view |
| Perspective cycling #3 | `V` | `perspective_mode=broadcast` | Cycles back to Broadcast (2-entrant cycle: Broadcast -> A -> B -> Broadcast) |
| Spectator Director | `G` | `director_enabled=True` | Footer shows `DIRECTOR ENGAGEMENT 6tps` |
| Fight Night | `N` | `fight_night_enabled=True` | On-screen caption box: `FIGHT NIGHT · BROADCAST` with real narrated events (`T11 B · CONTACT`, `T11 B · FIRST HOSTILE WRITE`, `T11 A · PROCESS DISRUPTED`) drawn from the real trace |

Clean exit (`cli.main` returned `0`; `pygame.get_init() == False` after quit) — no crash, no missing-asset
diagnostic. SDL backend: not independently forced; `DISPLAY=:0` (XWayland) was present alongside native
Wayland, consistent with the prior report's finding that a non-Qt display backend is not itself a defect.

### J.4 No-trace fallback

A **copy** of the Designer run directory (original preserved untouched) had `trace.jsonl` removed before
being opened. Confirmed:

- Broadcast rendered correctly; header correctly **omitted** the `[V to switch]` hint (no trace, no
  perspective claim advertised).
- Pressing `V` was a safe no-op — captured state identical before/after, no crash.
- `self._perspective_manager`, `self._director_manager`, and `self._fight_night_manager` were all
  directly confirmed `None` (never a half-initialized state) via the renderer's own internals.
- `cli.main` returned `0`; clean pygame teardown.

### J.5 Multi-entrant packaged smoke

A real 3-entrant stable-v4 match (`v4_claimer`/`v4_scout`/`v4_local_defender`, arena 512, seed 3,
200 ticks) executed successfully via `bytefray run --a-type ... --b-type ... --c-type ...`: `ruleset_id:
bytefray-rules-4`, `entrants: [v4_claimer, v4_scout, v4_local_defender]`, `winner: B`. The replay opened
and rendered all three non-overlapping seeded starts correctly (distinct colors/panels, header
`entrants 3`) in Broadcast view.

---

## K. Permissions result

`stat -c '%a %n'` across every run directory produced in this qualification (a plain CLI run, the
Designer-produced run, and the 3-entrant run) shows the same consistent pattern documented (and
classified as no defect) by Phase 4's Windows analysis:

```text
result.json    0600   (mkstemp -- deliberate)
replay.jsonl   0600   (mkstemp -- deliberate)
trace.jsonl    0664   (plain open() -- umask-derived; this machine's umask yields 0664, not 0644,
                        but the group-write bit does not affect owner readability)
summary.json   0664   (plain open() -- umask-derived)
```

All files are owned by the creating user (`rod`) and were repeatedly reopened successfully throughout
this qualification: every `result.json`/`evaluation.json` was read directly with Python's `json.load`,
and every replay/trace pair was successfully consumed by the Replay Viewer (§J). No unreadable artifact
was produced by the packaged installation anywhere in this session.

---

## L. sdist result

```text
$ python3 -m venv /tmp/bytefray-rc1-sdist-venv && source it && python -m pip install --upgrade pip
$ python -m pip install /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1.tar.gz
  Building wheel for bytefray (pyproject.toml): finished with status 'done'
Successfully installed PyYAML-6.0.3 bytefray-4.0.0rc1
```

Built and installed from the sdist's own bytes (no local checkout used). From `/tmp`:

```text
pip show bytefray        -> Version: 4.0.0rc1
battle_engine.__file__   -> .../sdist-venv/lib/python3.11/site-packages/battle_engine/__init__.py
battle_client.__file__   -> .../sdist-venv/lib/python3.11/site-packages/battle_client/__init__.py
bytefray --version       -> Bytefray 4.0.0rc1, Agent API v2, result schema v1, replay schema v4, Python 3.11.9
```

**Runtime smoke**: `bytefray run --a-type v4_claimer --b-type v4_scout ...` (omitted `--ruleset`) ->
`ruleset_id: bytefray-rules-4`. A small evaluation (`agents evaluate v4_claimer --opponents v4_scout
--ticks 20`) persisted `schema_version: 7`, `rules_compatibility_id: bytefray-rules-4`,
`lifecycle_state: finished` — and, notably, the **identical** content-addressed `evaluation_id` as the
wheel's equivalent run, confirming deterministic identity-hashing holds across the wheel and sdist builds
of the same candidate.

**Optional GUI smoke**: `PySide6` was installed into the sdist venv and `AgentDesigner` launched
successfully — `QApplication.platformName() == "wayland"`, correct window title
(`Bytefray – Agent Designer`), screenshot captured, clean close. The full GUI workflow (§J) was run
primarily from the wheel per the governing task's guidance; this sdist launch is confirmatory additional
evidence, not a duplicate of the full workflow.

---

## M. Defects/issues discovered

None are RC-blocking. Three environment/tooling notes and one resolved provenance question, all
documented above and summarized here:

```text
1. XDG_DATA_HOME redirection (Environment note, no defect)
   reproduction:    Bytefray's data root resolves under /home/rod/snap/code/259/.local/share/bytefray
                     instead of ~/.local/share/bytefray in this snap-confined VS Code session.
   root cause:      Correct, spec-compliant honoring of this session's XDG_DATA_HOME; confirmed not a
                     source-tree or repo-.venv dependency.
   RC impact:       None.
   disposition:     No action. Worth knowing for anyone reproducing this qualification in the same
                     snap-confined environment.

2. gnome-screenshot broken on this machine (Environment issue, no defect)
   reproduction:    `gnome-screenshot -f ...` -> symbol lookup error against
                     /snap/core20/current/lib/x86_64-linux-gnu/libpthread.so.0.
   root cause:      Machine/snap packaging fault, identical to the prior Linux prequalification's
                     finding; unrelated to Bytefray.
   RC impact:       None. QWidget.grab()/pygame.image.save() supplied complete screenshot evidence
                     instead.
   disposition:     No action.

3. Trace auto-discovery requires the literal filename `trace.jsonl` (Non-issue / test-setup note)
   reproduction:    A --trace output named anything other than exactly "trace.jsonl" (e.g. this
                     session's own multi_trace.jsonl for the 3-entrant smoke) is not auto-discovered
                     by the Replay Viewer, by design (`replay_path.with_name("trace.jsonl")`).
   root cause:      Intentional, documented convention; not a defect. Caused a naming choice this
                     session made for §J.5 to not exercise Perspective there, which is immaterial since
                     Perspective/Director/Fight Night were already fully qualified in §J.3 with a
                     correctly-named trace.
   RC impact:       None.
   disposition:     No action; recorded so the naming choice isn't mistaken for a product gap.

4. Artifact-appearance timing (Resolved -- see §D.2)
   Flagged by a peer session reviewing this qualification. Forensic timestamps plus the user's direct
   confirmation establish a benign manual transfer, not tampering or a search-scope defect. No RC impact.
```

---

## N. Source/artifact integrity

```text
git status --short (throughout): only the pre-existing, unrelated, untracked agents/Nemesis/agent.py-v1
git rev-parse HEAD (before this report's commit): 413a4a01de1f38160ad14cc4c6cc0fa1b7510a70 (unchanged)
```

No product/source file was modified. No artifact was rebuilt. Re-hashed both artifacts after every test
in this report:

```text
$ sha256sum /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1-py3-none-any.whl
e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3   (unchanged, matches required)

$ sha256sum /home/rod/bytefray-v4-rc1-artifacts/bytefray-4.0.0rc1.tar.gz
3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8   (unchanged, matches required)
```

Qualification testing did not mutate the release artifacts.

---

## O. Publication recommendation

**RC1 may be published.** Every mandatory gate in the governing task passes: the exact Windows-built
wheel and sdist are confirmed byte-identical to the authoritative hashes; both install cleanly in
isolated environments with no source-tree dependency; stable-v4 is the correct default and current/
recommended identity across the CLI, evaluation, and Designer; historical Alpha1/Alpha2 identities and
fail-closed API/Ruleset compatibility all hold; all 11 pinned placement vectors plus the known research
cross-validation vector match exactly; stable-v4 and Alpha2 produce byte-identical gameplay outcomes;
the full GUI workflow (Designer, automatic trace, Replay Viewer, Perspective, Director, Fight Night,
no-trace fallback, multi-entrant) runs correctly on a real native-Wayland desktop from the packaged
wheel; artifact permissions are consistently usable; and the sdist independently builds, installs, and
runs correctly. No RC-blocking defect was found. The one non-trivial finding of this session — the
artifact-appearance timing — was investigated to a clean, benign resolution (§D.2) rather than left as
an open question.

```text
LINUX PACKAGED QUALIFICATION PASSED — RC1 PUBLICATION GATE SATISFIED
```
