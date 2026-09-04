# Bytefray v4 RC Path — Linux Packaged-Artifact Qualification (Phase 4 Linux Gate)

Branch: `v4-rc1-linux-qualification` (pre-existing branch, inspected and reused rather than
recreated under the alternate name suggested by the governing task; it already sat at the tip of
the prior Linux prequalification work)
Candidate source SHA under qualification: `356702621d0ad328ac27497235087f5bd67e7183`
Report-writing HEAD: `4bb369b1a074e7f81563ed15e7424c628520daff`

This is a **failed** packaged-artifact qualification. The exact RC1 wheel
(`bytefray-4.0.0rc1-py3-none-any.whl`) and sdist (`bytefray-4.0.0rc1.tar.gz`) that Windows Phase 4
reports as built and qualified from candidate `3567026` **were not found anywhere on this Linux
machine**. No install, CLI smoke, evaluation, determinism, GUI, or Replay Viewer testing was
performed, per the governing task's explicit instruction to stop at the hash gate rather than
install, rebuild, or substitute another artifact.

```text
LINUX PACKAGED QUALIFICATION FAILED — ARTIFACT HASH MISMATCH
```

---

## A. Executive gate

| Gate | Result |
|---|---|
| Exact wheel hash matches Windows | **FAIL** (file not present on this machine) |
| Exact sdist hash matches Windows | **FAIL** (file not present on this machine) |
| Clean wheel installation | NOT ATTEMPTED — blocked by hash gate |
| Wheel version/import isolation | NOT ATTEMPTED |
| Stable-v4 packaged CLI | NOT ATTEMPTED |
| API-v1 packaged compatibility | NOT ATTEMPTED |
| Historical Alpha2 explicit identity | NOT ATTEMPTED |
| Fail-closed compatibility | NOT ATTEMPTED |
| Stable-v4 packaged evaluation | NOT ATTEMPTED |
| Evaluation methodology display | NOT ATTEMPTED |
| 11 pinned placement vectors | NOT ATTEMPTED |
| Stable-v4/Alpha2 equivalence smoke | NOT ATTEMPTED |
| Native-Wayland Designer from wheel | NOT ATTEMPTED |
| Designer automatic trace | NOT ATTEMPTED |
| Replay Viewer from wheel | NOT ATTEMPTED |
| Perspective | NOT ATTEMPTED |
| Director | NOT ATTEMPTED |
| Fight Night | NOT ATTEMPTED |
| No-trace fallback | NOT ATTEMPTED |
| Multi-entrant packaged smoke | NOT ATTEMPTED |
| Artifact permissions usable | NOT ATTEMPTED |
| Clean sdist install | NOT ATTEMPTED |
| sdist runtime smoke | NOT ATTEMPTED |
| Original artifact hashes unchanged | N/A — no candidate-matching artifact was ever present to mutate |
| **RC blocker found** | **YES** |
| **RC1 may be published** | **NO** |

---

## B. Linux environment

```text
OS:        Ubuntu 26.04.1 LTS (Resolute Raccoon)
Kernel:    Linux 7.0.0-30-generic, x86_64 (rod-HP-Pavilion-Notebook)
Python:    3.11.9 (system python3; a dedicated clean venv was never reached)
git:       2.53.0
Session:   XDG_SESSION_TYPE=wayland, XDG_CURRENT_DESKTOP=ubuntu:GNOME
           DISPLAY=:0, WAYLAND_DISPLAY=wayland-0
           -> the same real native-Wayland desktop machine used for the prior Linux
              source-level prequalification (V4_RC1_LINUX_PREQUALIFICATION.md), confirming this
              is the correct machine for this gate. Qt's platformName() was not checked because
              no packaged environment was ever created to check it from.
```

No `pip`, venv, Qt, or SDL/Pygame backend evidence was collected — every step past the artifact
search is downstream of an artifact that does not exist on this machine.

---

## C. Candidate provenance

```text
candidate source SHA:            356702621d0ad328ac27497235087f5bd67e7183   (exists locally)
origin/v4-rc1-development HEAD:  a632c2cdbc0e96bc1360a82f2afbb97e5c00084a   (fetched)
```

### C.1 Verbatim provenance commands

```text
$ git fetch origin --tags
   8b039c7..b5e39ac  experiment/v4-quorum-agent -> origin/experiment/v4-quorum-agent

$ git rev-parse origin/v4-rc1-development
a632c2cdbc0e96bc1360a82f2afbb97e5c00084a
```

`git log --oneline --decorate -10 origin/v4-rc1-development`:

```text
a632c2c (origin/v4-rc1-development) docs(v4): record Phase 4 Windows RC1 packaging/build qualification report
3567026 fix(release): match pyproject.toml's RC1 version to installer.iss's ReleaseTag
afdb7d9 chore(release): prepare v4.0.0-rc1
3a41e7b docs(v4): record Linux prequalification report for Phase 3 candidate 01a1718
01a1718 (v4-rc1-development) docs(v4): record Phase 3 product coherence audit report
7c9780c fix(v4): correct stale alpha-default claims found in Phase 3's product-coherence audit
30f4218 fix(v4): thread is_v4_methodology through rendered evaluation summaries
b2000c4 docs(v4): record Phase 2 stable ruleset/API promotion report
71b1a0d docs(v4): document stable bytefray-rules-4 and fix stale alpha-only compatibility claims
e3c54b2 test(v4): pin alpha1/alpha2 canonical identity and cross-Ruleset isolation
```

`git diff 356702621d0ad328ac27497235087f5bd67e7183..origin/v4-rc1-development -- engine client app agents tools pyproject.toml installer.iss`
produced **no output** — confirmed product/release source is unchanged since the candidate SHA.
`git diff --stat` across all paths for the same range shows exactly one file:
`docs/research/v4/V4_RC1_PHASE4_RELEASE_QUALIFICATION.md` (+503), a documentation-only commit,
exactly as the governing task predicted.

This session's own branch (`v4-rc1-linux-qualification`, HEAD `4bb369b`) is a *sibling* of
`origin/v4-rc1-development`, not a descendant of it — it was cut from the Phase 3 tip (`01a1718`)
before `afdb7d9`/`3567026`/`a632c2c` were committed, so it does not itself contain the RC1
release-prep commits or the Phase 4 report. That is expected and does not affect this gate: the
governing task only requires this report to be committed on a Linux qualification branch, not for
that branch to be rebased onto `v4-rc1-development`.

---

## D. Artifact provenance — HARD HASH GATE

### D.1 Required identities

```text
wheel:  bytefray-4.0.0rc1-py3-none-any.whl
        e5ec9b0f37f359dc46eeba4bbeeb7d396d737e1ba80541220a74ba408bbed5e3

sdist:  bytefray-4.0.0rc1.tar.gz
        3ee5631f425338d4eca75ddbf48cd2b11374e928159b404c9cf15362592a3fb8
```

### D.2 Search performed

Searched, recursively, for both exact filenames and for any `bytefray-4.0.0rc1*` or `*bytefray*`
`.whl`/`.tar.gz` file:

```text
/home/rod/**                    (full home tree)
/tmp/**
/mnt, /media/$USER               (no mounts, no removable/network shares present)
/var/tmp, /srv, /opt
repo/dist/
```

No file named `bytefray-4.0.0rc1-py3-none-any.whl` or `bytefray-4.0.0rc1.tar.gz` exists anywhere
on this machine. The task's own suggested locations (`repo/dist/`, `~/Downloads/`, `~/tmp/`, "a
manually transferred RC1 artifact directory") were all checked explicitly:

- `repo/dist/` contains only `bytefray-3.0.0rc1-py3-none-any.whl` / `bytefray-3.0.0rc1.tar.gz`
  (v3, not v4 — an older RC cycle's build output).
- `~/Downloads/` contains no `bytefray-4.*` files at all (inspected in full; it holds unrelated
  personal files plus one old `Bytefray-2.0-development.zip` and an old `CHANGELOG.md`/`README.md`
  pair, none of which are the candidate RC1 wheel/sdist).
- `~/tmp/` does not exist.
- `~/bytefray-rc1-linux-qualification/` — the closest match to "a manually transferred RC1
  artifact directory" — exists and contains a full prior qualification working set (venvs,
  data dirs, `SHA256SUMS.txt`), but its wheel/sdist are `bytefray-1.0.0rc1-py3-none-any.whl` and
  `bytefray-1.0.0rc1.tar.gz` — an entirely different, much older release cycle (v1.0.0-rc1, which
  also shipped a Windows installer/portable ZIP per its `SHA256SUMS.txt`), not v4.0.0rc1.
- `/tmp/bytefray-build-out/` contains another copy of the v3.0.0rc1 wheel/sdist.

No Windows-to-Linux transfer of the actual v4.0.0rc1 candidate artifacts has occurred. This is
consistent with `V4_RC1_PHASE4_RELEASE_QUALIFICATION.md`'s own statement that its authoring
session "has no access to a Linux machine to perform [Linux packaged qualification]" — the
artifacts were built and hashed on Windows but the hand-off copy to this machine was never made.

### D.3 Hashes of every Bytefray wheel/sdist found on this machine

None of these are the required filename; none are qualification candidates. Recorded for the
record and to prove no substitution was made:

| Path | SHA-256 | Matches required? |
|---|---|---|
| `dist/bytefray-3.0.0rc1-py3-none-any.whl` | `76f1cf69a4a4844d680fe0c608c9602fa12d10b932b9cd749fe0eb3d4ea13727` | No (wrong version) |
| `dist/bytefray-3.0.0rc1.tar.gz` | `76c4b9a75945413bb1d6816e6d66d5544f677b3a4ff55bfc64a090865c17fc8f` | No (wrong version) |
| `/tmp/bytefray-build-out/bytefray-3.0.0rc1-py3-none-any.whl` | `2d166d7734801daf90963cd16440e21e7bc6f63dec96659d56958083ebb372bd` | No (wrong version) |
| `/tmp/bytefray-build-out/bytefray-3.0.0rc1.tar.gz` | `a612613d040b8f52c8021b265b7ead0a41824ba74278f17cd503bf0c33730569` | No (wrong version) |
| `~/bytefray-rc1-linux-qualification/bytefray-1.0.0rc1-py3-none-any.whl` | `e07705c8d8c6ca6693d718ecc41c6fdc5d97cb84d65a5e080ae298450e564348` | No (wrong version) |
| `~/bytefray-rc1-linux-qualification/bytefray-1.0.0rc1.tar.gz` | `564aba1fbd1cb06567d4073cf74d91d8224e0e59746cd5c3f5a699801b5923ec` | No (wrong version) |
| `~/.cache/pip/wheels/.../bytefray-1.0.0rc1-py3-none-any.whl` | `038adbec94bbb6f1ba8e8a8e63cf0a023deff59a21aa8f806d1ec44c0a81cb8e` | No (wrong version) |

The three v1.0.0rc1 hashes reproduce exactly what `~/bytefray-rc1-linux-qualification/SHA256SUMS.txt`
already recorded for that older cycle, confirming those files are self-consistent leftovers from a
prior, unrelated qualification round rather than anything mislabeled or tampered with.

**Per the governing task's Section 5 (HARD HASH GATE): no artifact was installed, no artifact was
rebuilt, and no locally-generated or wrong-version package was substituted. Qualification stopped
here.**

---

## E through M

Not attempted. Every downstream section (clean-room install, CLI smokes, evaluation, the 11 pinned
determinism vectors, Designer/Wayland GUI, Replay Viewer, trace/no-trace, multi-entrant, artifact
permissions, sdist install) requires the exact wheel and/or sdist bytes as the object under test.
None exist on this machine, so none of that evidence could be produced without violating the
governing task's explicit prohibition on installing an unverified artifact, rebuilding locally, or
substituting a different version.

---

## N. Defects/issues discovered

### N.1 — RC1 v4.0.0rc1 wheel/sdist were never transferred to the Linux qualification machine

```text
severity:                  RC blocker (process/logistics, not a product defect)
reproduction:              Exhaustive filesystem search (see §D.2) for bytefray-4.0.0rc1-py3-none-any.whl
                            and bytefray-4.0.0rc1.tar.gz on the designated real-desktop Linux
                            machine returns zero matches.
root cause/evidence:       V4_RC1_PHASE4_RELEASE_QUALIFICATION.md documents that the Windows
                            session built and qualified these exact artifacts but had no Linux
                            machine access to perform this gate itself, and the required
                            file transfer to this machine subsequently did not happen (or the
                            files were placed somewhere this search did not cover and no location
                            hint exists anywhere in the repo, Downloads, or prior staging
                            directories to find them).
RC impact:                  RC1 publication is blocked. This is precisely the "one remaining
                            gate" the governing task describes, and it cannot be satisfied without
                            the actual candidate bytes.
recommended disposition:    Transfer the exact bytes of bytefray-4.0.0rc1-py3-none-any.whl and
                            bytefray-4.0.0rc1.tar.gz (as built and hashed on Windows from
                            candidate 356702621d0ad328ac27497235087f5bd67e7183) to this Linux
                            machine — e.g. into repo/dist/ or the existing
                            ~/bytefray-rc1-linux-qualification/ staging directory — then re-run
                            this qualification task from Section 5 onward. Do not rebuild on
                            Linux and do not substitute the v3.0.0rc1 or v1.0.0rc1 files present
                            on this machine; neither is the RC1 v4 candidate.
```

No product-code, gameplay, Agent API, replay-schema, or evaluation-methodology defect was found
or investigated, because no such investigation was reachable from this gate.

---

## O. Source/artifact integrity

```text
git status --short (before):  ?? agents/Nemesis/agent.py-v1   (pre-existing, untracked, unrelated
                                — same file noted as pre-existing in the prior Linux
                                prequalification report; not created or touched by this session)
git status --short (after):   ?? agents/Nemesis/agent.py-v1   (unchanged)
git rev-parse HEAD (before/after): 4bb369b1a074e7f81563ed15e7424c628520daff (unchanged except for
                                     this report's own commit, added after this line was recorded)
```

No product/source file was modified, no artifact was installed, no artifact was rebuilt. The three
non-candidate wheel/sdist pairs found on the machine (§D.3) were only read (`sha256sum`), never
executed, installed, or modified.

---

## P. Publication recommendation

**Do not publish RC1.** The one remaining gate the governing task describes — qualifying the exact
Windows-built `bytefray-4.0.0rc1` wheel and sdist on a real Linux desktop — could not be attempted
because those artifacts are not present on this machine. This is not a product defect: Phase 3 and
the Phase 4 Windows report both qualify cleanly, and the earlier Linux *source-level*
prequalification (`V4_RC1_LINUX_PREQUALIFICATION.md`) already passed on this same real
native-Wayland machine. What is missing is purely the artifact hand-off. Once the exact
Windows-built wheel and sdist (matching the SHA-256 values in §D.1) are placed on this machine,
this qualification should be re-run in full from Section 5 onward; nothing in Sections 1-4 needs
to be repeated unless the environment or repository state has changed.

```text
LINUX PACKAGED QUALIFICATION FAILED — ARTIFACT HASH MISMATCH
LINUX PACKAGED QUALIFICATION FAILED — RC1 PUBLICATION REMAINS BLOCKED
```
