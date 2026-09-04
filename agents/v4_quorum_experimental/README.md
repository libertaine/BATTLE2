# V4 Quorum (Experimental)

`v4_quorum_experimental` is a deliberately complicated Agent API v2 entrant built to push the public Bytefray v4 contract rather than serve as a beginner starter.

It is intentionally kept outside the normal release path. The experiment asks two questions:

1. How much coordinated behavior can a user build using only the public Agent API v2 surface?
2. Can another user take an existing v4 example, copy it into the normal `agents/<id>/` layout, modify it, validate it, and put it into real matches without needing engine-specific hooks?

## What Quorum stresses

Quorum declares six fixed processes sharing the entrant-wide Q=8 action budget:

| Process | Reach | Share | Purpose |
| --- | ---: | ---: | --- |
| `oracle` | arena / 2 | 0.125 | Global sensor/sniper and ownership probe |
| `breaker` | 48 | 0.250 | Primary mobile assault and core siege |
| `guardian` | 12 | 0.250 | Own-core READ/repair loop and local interception |
| `flank_left` | 32 | 0.125 | Left-side mobile bracket |
| `flank_right` | 32 | 0.125 | Right-side mobile bracket |
| `reserve` | 24 | 0.125 | Adaptive defense/offense reinforcement |

The implementation exercises:

- independent process movement after mandatory initial co-location;
- unequal deterministic quota shares;
- entrant-shared current visibility;
- shared Python state across process callbacks;
- remembered contacts and target confidence;
- delayed `READ` feedback tracked separately per process;
- `previous_read_owner` as weak enemy-location evidence;
- own-core ownership inspection and repair;
- callback timing fields to infer that a process missed one or more ticks;
- adaptive reserve behavior after pressure or inferred disruption;
- deterministic use of `MatchContextV2.rng`;
- absolute READ/WRITE addressing versus relative MOVE;
- legal use of one very large-reach process while forcing the remaining roles to move physically;
- per-tick de-duplication so several roles do not blindly spend every slot on the same visible anchor.

No replay access, engine introspection, research-only flags, filesystem state, networking, or hidden match metadata is used.

## Deliberate weaknesses

This is an experiment, not a claim of optimal play.

- The `oracle` deliberately tests the current zero-cost uncapped-reach rule. If one large-reach process proves overwhelmingly valuable, that is useful gameplay evidence.
- The guardian can spend two of eight entrant actions inspecting/repairing the core. That defense has a measurable opportunity cost.
- Early visible enemy anchors are treated as strong evidence of an enemy start/core location because every process begins co-located at its entrant core. A sufficiently fast-moving opponent can make later sightings less useful.
- Contact memory can become stale. Local roles therefore verify reach before writing and move toward remembered targets instead of emitting illegal writes.
- The target-confidence model is intentionally understandable rather than mathematically sophisticated. It is meant to be modified.

## Copy it like a user would

Copy the whole directory to a new discovery ID under the writable Bytefray data root:

```text
agents/
  my_quorum/
    agent.yaml
    agent.py
```

Change the manifest `name`, `display`, `description`, and `version`, then start modifying `agent.py`. The public lifecycle remains:

```python
reset(context)
declare_processes()
act(observation)
```

Useful first experiments are changing only one dimension at a time:

- `oracle` reach;
- guardian/breaker shares;
- number of processes;
- flank standoff distance;
- how long early sightings retain core confidence;
- reserve pressure duration;
- guardian scan frequency versus blind defensive writes.

## Validate and test

From a Bytefray environment containing the agent:

```bash
bytefray agents validate v4_quorum_experimental
bytefray agents test v4_quorum_experimental --opponent v4_defender_scout --seed 1337 --ticks 200
```

Then inspect the generated development trace and replay using the paths printed by `agents test`:

```bash
bytefray agents inspect <run-dir>
bytefray replay --replay <replay-path>
```

For a longer direct match:

```bash
bytefray run --a-type v4_quorum_experimental --b-type hydra_alpha2 --ticks 1000
```

Because the manifest declares Agent API v2, an omitted ruleset resolves to the permanent `bytefray-rules-4` contract. Use an explicit alpha identity only when intentionally reproducing historical alpha behavior.

## What to watch in the replay

A useful replay should make the six roles visibly distinguishable:

- initial dispersion away from the entrant core;
- oracle disruption of detected enemy anchors;
- breaker closing on remembered target territory;
- flankers approaching from different sides rather than stacking;
- guardian staying near home and repeatedly reasserting core ownership;
- reserve returning home when pressure/recovery alarms fire.

If those behaviors are difficult to recognize in the replay even when they are happening correctly, that is also useful product feedback: sophisticated v4 agents may need better process-role visualization or trace/replay correlation.

## Experiment success criteria

Quorum succeeds as an experiment even if it loses matches. Useful outcomes include:

- it validates and runs entirely through the public v4 API;
- the replay clearly shows coordinated spatial roles;
- changing one policy produces understandable behavioral changes;
- Agent Lab makes the shared-state decisions diagnosable;
- a user can copy the directory and create a variant without touching Bytefray source;
- or, conversely, the exercise exposes a public-authoring or visualization gap that should be improved in a later release.
