# Canonical Result Contract

BATTLE2 v0.3 writes `result.json` using schema `battle2.result`, version 1. The
same high-level envelope represents VM, Python, and pMARS matches.

Required envelope fields are `result_id`, `match_id`, `mode`, `status`, `winner`,
`termination_reason`, `ticks`, `score`, `entrants`, `reproducibility`, `replay`,
and `backend`. Native results reference a replay by `replay_id`, SHA-256 digest,
and portable filename. pMARS results set `replay` to `null`.

Native entrant records include identity, final state, score, statistics,
termination reason, optional structured diagnostic, and execution metadata.
Python metadata includes API version, agent version, derived seed, request slot,
and source digest. VM metadata includes entry address and bytecode digest.

`match_id` is deterministically derived from execution inputs and entrant
identity. `result_id` additionally covers the outcome. The result stores the
digest of the completed replay; the replay header stores both IDs. The replay
does not contain its own digest because that would be self-referential.

`summary.json` remains the v0.2 compatibility adapter for existing consumers.
New integrations should consume `result.json`.
