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
are rejected before artifacts are created. This phase provides a service API,
not a GUI manager, tournament-specific CLI, parallel scheduler, elimination
brackets, ratings, or pMARS tournament division.
