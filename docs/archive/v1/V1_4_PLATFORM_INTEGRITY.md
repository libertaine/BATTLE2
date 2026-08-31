# v1.4 platform-integrity audit

This is the durable scope record for the v1.4 development line. The governing
constraint is: identical Ruleset-v1 inputs retain identical Ruleset-v1
observable behavior.

## Naming classification

Current product surfaces use Bytefray exclusively: commands, frozen
executables, PyInstaller layouts, installer shortcuts and environment state,
data-directory defaults, smoke tests, and active user/developer documentation.
The obsolete command aliases and predecessor root variables are intentionally
not compatibility surfaces. Active Designer code also uses the neutral
`data_root` name rather than carrying predecessor-era `battle_root` terminology.

The following are deliberately unchanged:

- `battle2.result`, `battle2.replay`, and `battle2.tournament`: persisted wire
  protocol identifiers;
- `battle2-python-v1`: the frozen Agent API v1 RNG-derivation salt;
- `battle2-tournament-v1`: the frozen tournament match-identity salt;
- `battle_engine` and `battle_client`: stable descriptive Python package names;
- old release notes, migration specs, and project history that truthfully
  describe historical releases.

The retained top-level historical tournament utility still uses its original
`BATTLE_AGENTS_JSON` handoff to its retained `_legacy/agents_tooling` fixture;
its characterization test pins that historical pairing. It is not read by the
current Bytefray CLI or Designer.

Those strings must not be cosmetically renamed: doing so would invalidate
artifacts, deterministic identities, imports, or historical evidence.

## Dead-code evidence

The audit removed four individual modules after repository imports, entry
points, runtime discovery, tests, build specifications, and packaging showed
no caller:

- `app/main.py`;
- `app/match_runner.py`;
- `client/src/battle_client/renderers/pygame_canvas.py`;
- `battle_engine.legacy`.

The top-level `_legacy/` tree was retained. It is not an active runtime path,
but its characterization tests and historical tournament tooling still use it,
so deleting it would discard evidence rather than merely remove unreachable
implementation. It remains excluded from active-source linting and should be
revisited only with a fixture-preservation plan.

## Ruleset-v1 equivalence corpus

`engine/tests/test_ruleset_v1_equivalence.py` covers default and non-default
arenas, representative built-in VM strategies, wrapped/overlapping loads and
writes, kill/death and territory behavior, packaged Python starter agents,
Agent API v1 deterministic RNG, normal halt, controlled forfeit, representative
seeds/tick limits, and ordinary two- and existing three-entrant execution.

It pins match/result identity, winner, termination, ticks, score, per-agent
state/statistics, final arena and ownership fingerprints, and normalized
canonical replay content. Replay newlines alone are normalized because Python
text-mode output uses the host line ending; no replay record content is
normalized or omitted. Direct semantic assertions accompany the aggregate
snapshot digest. The corpus passed unchanged before and after incremental
ownership accounting.

## Current multi-entrant boundary

`NativeMatchService` already accepts any non-empty homogeneous entrant tuple
with unique IDs. VM and Python controllers, result/replay serialization,
scoring, statistics, termination, and winner resolution already handle three
entrants; direct qualification now proves deterministic execution, ordered
identity, all-entrant artifacts, and order-sensitive match identity. This is
qualification of existing Ruleset-v1 behavior, not new N-way methodology.
Tournament and evaluation scheduling remain intentionally pairwise.

## Ownership boundary

Before v1.4, scoring and statistics independently constructed a full
`Counter(ownership)` every tick. All supported ownership mutations already
converged through `VM._wr8`, so that boundary now maintains an authoritative
`owner -> cell count` map while preserving the full writer array and replay
diffs. Direct invariant tests recompute counts after unowned/owned transitions,
same-owner writes, owner replacement, wrapped addresses, overlapping loads,
and Python writes. See [the scaling report](V1_4_SCALING.md) for
measurements and the replay-index deferral decision.
