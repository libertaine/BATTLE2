# Headless Tournament Service

Phase 5 introduces `TournamentService`, a headless orchestration layer over
`NativeMatchService`. It accepts a `TournamentRequest`, creates a deterministic
round-robin schedule, runs each pair in its own artifact directory, reads the
canonical `battle2.result` v1 artifact, and derives standings.

Each of two or more entrants plays every other entrant once per configured
round. Request order defines stable pair order. Match seeds are derived with
SHA-256 from the tournament seed, round, and ordered entrant IDs. Standings
record played matches, wins, losses, ties, and cumulative canonical score.

The tournament root contains `tournament.json` using schema
`battle2.tournament` version 1. It is atomically checkpointed after every match.
With resume enabled, completed matches are loaded from their canonical
`result.json` instead of rerun. Failed and rejected matches are recorded and
excluded from standings; they remain terminal unless `retry_failures` is set.

Every match has a stable scheduled ID and a directory beneath `matches/` that
contains its replay, canonical result, and compatibility summary where produced.
The canonical match and result IDs are recorded in tournament state.

A division must be entirely VM or entirely Python. Mixed VM/Python divisions
are rejected before artifacts are created. Phase 6a exposes the service through
the supported headless CLI:

```bash
battle2 tournament runner writer seeker \
  --rounds 2 --seed 1337 --ticks 3000 --output runs/league
```

Discovered Python agents use the same syntax, but every entrant in one division
must resolve to Python. Built-ins and blob manifests form VM divisions. The CLI
uses the normal writable data root, starter initialization, and agent discovery;
it does not use `tournament/scripts/btctl.py`.

Rerunning the same request and output directory resumes completed canonical
results. `--retry-failed` reruns state entries recorded as failed or rejected.
An incompatible request using an existing state directory exits with a controlled
error. Without `--output`, artifacts default beneath
`<data-root>/runs/tournaments/<entrants>-seed-<seed>/`.

Normal output reports the tournament ID, completed/failed/rejected counts,
standings, and state path. `--quiet` suppresses terminal presentation; the
canonical `tournament.json` remains the machine-readable output. Exit status is
0 when every scheduled match completed, 1 when the service completed with one or
more recorded failed/rejected matches, and 2 for invalid requests, unsupported
composition, or incompatible state.

Each match directory contains canonical `result.json` and `replay.jsonl`, plus
the compatibility summary where applicable. Single-match `battle2 run` output
also names its canonical result and replay alongside `summary.json`.

The optional PySide6 Designer exposes a deliberately small launcher at
**Tools → Run Tournament…**. It selects two or more homogeneous entrants,
rounds, seed, and an output directory, then runs this same supported CLI in a
background process. Completion counts and standings are shown in the existing
log, and **Tools → Open Last Output Folder** opens the selected artifact root.
An existing compatible output directory resumes automatically.

There is no bracket visualization, parallel scheduler, elimination bracket,
rating system, custom tournament scoring UI, mixed-runtime division, or pMARS
tournament division. The older `tournament/scripts/btctl.py` remains a legacy
standalone workflow and is not the supported execution path.
