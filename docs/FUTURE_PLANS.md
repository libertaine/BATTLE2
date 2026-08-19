# Bytefray Future Plans

This document catalogues ideas that have been deliberately kept **out of
the required v1.0 scope** (see [ROADMAP.md](ROADMAP.md) for why, and for
what v0.10 and v1.0 themselves cover). They are preserved here, organized
by area, so they are not lost — while being labeled honestly by maturity so
none of them reads as a promise.

Status words, used consistently throughout this document:

- **Candidate** — real merit and a plausible design, no assigned release;
  likely if usage or evidence justifies it.
- **Exploratory** — a design direction being thought through; not yet
  validated, and the shape described could change substantially.
- **Research** — requires investigation before anyone could responsibly
  commit to a design.
- **Unscheduled** — real, retained, not actively planned.

---

## Accessible agent-authoring language / DSL

**Status: deferred to the Agent API v2 era.**

A small, Bytefray-specific strategy language for users who don't want to
begin by writing Agent API Python directly. The intent is a **deterministic
domain-specific language**, not ambiguous natural-language programming.

Conceptual pipeline:

```
BFScript (or similar DSL)
  → parser / AST
  → validated intermediate representation
  → Python Agent API backend
  → potentially a native VM/blob backend, where semantics permit
```

Principles this would need to hold to, if pursued:

- Suitable for beginning users; constrained and deterministic.
- Generated Python must be inspectable, not a black box.
- Useful as a teaching path *into* Agent API programming, not a permanent
  substitute for it.
- The compiler must reject unsupported target semantics rather than
  silently changing behavior.
- Generated artifacts should retain provenance: source language, compiler
  version, source hash, target/API version, and generated-revision
  identity — following the same honesty precedent Bytefray's agent
  revision store already established for hand-written agents.
- Possible future `compile`/`explain` commands.

Do not begin this DSL against Agent API v1 when its long-term target may change
materially under Agent API v2. Reconsider it only with the v2 API/rules work,
so the language does not freeze accidental 1.x constraints or require an
immediate compatibility migration.

---

## Agent packaging / sharing

**Status: shipped (v1.2.0)** — see
`docs/ROADMAP.md`'s v1.2.0 section and `docs/specs/agent_package.md` for
the full design. `bytefray agents export`/`agents package show`/`agents
import` package one agent revision into a portable `.bytefray-agent` file,
built as a transport wrapper around the content-addressed agent-revision
store this section originally anticipated using. The `package.json`
manifest carries factual identity (revision id, kind, entry point, Agent
API version) and enforced compatibility (schema version, Agent API
version), deliberately never a claimed Ruleset-compatibility field — an
Agent API v1 Python agent is not bound to one Ruleset the way a match/
evaluation artifact is.

Retained here as a pointer, not duplicated: this status update exists so
this document doesn't go stale the way a similar entry under "Richer GUI
access to evaluation/history/provenance" below did after v1.1 shipped it.
Deferred, ecosystem-facing follow-ups this milestone deliberately did not
attempt (see `docs/specs/agent_package.md`'s own deferred-work section)
remain open only if ecosystem demand appears: package signing/PKI, an online
registry/discovery service, and DSL-compiler provenance metadata once a DSL
(see above) actually ships. Do not build registry or PKI infrastructure to
fill a release milestone without users/packages that require it.

---

## Richer evaluation / statistical analysis

**Status: Delivered in part (v1.6 Phase 4 and Phase 5); remainder
Candidate, with one Exploratory sub-item.**

- ~~Richer aggregate evaluation analysis and confidence/statistical
  summaries.~~ Delivered in v1.6.0 Phase 4: Wilson score intervals on
  observed win rates and an exact paired candidate-vs-baseline
  significance test (exact sign test / exact McNemar test) over discordant
  paired conditions, with by-opponent/by-orientation breakdowns -- see
  [V1_6_PHASE4_EVALUATION_ANALYSIS.md](V1_6_PHASE4_EVALUATION_ANALYSIS.md).
- ~~Behavior profiling.~~ Delivered in v1.6.0 Phase 5: a derived
  `behavior:` profile (survival, write activity, territory occupancy/
  retention/spread, kill interaction), overall and split by orientation/
  opponent, kept structurally independent of outcome -- see
  [V1_6_PHASE5_BEHAVIOR_ANALYSIS.md](V1_6_PHASE5_BEHAVIOR_ANALYSIS.md).
  Deliberately narrower than a full behavioral-similarity system: no
  clustering, no archetype naming, no composite "strategy score," and no
  combined behavioral-distance scalar (per-dimension deltas only) --
  Phase 5 stopped there because a defensible cross-dimension weighting
  was not found, not because of a time constraint. Replay-derived
  territory-trajectory metrics (early expansion rate, peak timing,
  contraction) were evaluated and explicitly deferred for a concrete
  architecture-boundary reason (the incremental reconstruction they need
  lives in `battle_client`, which `battle_engine` must never depend on) --
  a future phase implementing them belongs in `battle_client`/Designer,
  not `battle_engine`.
- Ranking systems such as Elo/Glicko or similar.
- Benchmark/reference agent populations.
- Improved comparative visualization.
- Clustering agents into behavioral archetypes -- Phase 5's profile
  vectors would make this technically easy, but it was explicitly not
  attempted; any future work here needs its own validation against a
  known-strategy fixture set, not an assumption that Phase 5's dimensions
  are sufficient for it. "Behavioral ecology / emergent-strategy
  measurement" under "Strategic Complexity & Open-Endedness" below widens
  this same idea to a fuller candidate metric set (expansion rate, process
  count/mortality, movement, opponent-contact frequency, recovery after
  damage, resource efficiency) and an explicit archetype vocabulary
  (expanders, fortresses, raiders, parasites, scout-heavy, resilient,
  burst attackers) to eventually validate against -- not duplicated in
  full here.

Ranking systems in particular should not be treated as a v1.0 requirement;
neither Phase 4 nor Phase 5 introduces one (no Elo/Glicko/TrueSkill/global
rating -- comparison stays scoped to explicit evaluation conditions).

Reusable, named **evaluation presets** (`bytefray agents evaluate --preset
<name>`, a hand-authored `bytefray.evaluation_preset` YAML file supplying
default opponent/seed/ticks/orientation values) shipped in v1.6.0 Phase 3
-- see
[V1_6_PHASE3_EVALUATION_PRESETS.md](V1_6_PHASE3_EVALUATION_PRESETS.md).
Deliberately scoped as an input-construction convenience only: no built-in
preset catalog, no behavior profiling or benchmark/reference-population
semantics -- those remain open items above, to be reconsidered with
evidence in hand rather than assumed.

---

## Evaluation performance and scaling

**Status: partially delivered in v1.6, remainder evidence-gated.**

- **Parallel evaluation** -- delivered in v1.6.0 Phase 2 (bounded local
  subprocess-worker pool via `--workers N`; see
  [V1_6_PHASE2_PARALLEL_EVALUATION.md](V1_6_PHASE2_PARALLEL_EVALUATION.md)).
- **Large evaluation matrices** -- exercised up to 2,000 cells in Phase 2's
  own stress qualification; no architectural blocker found at that scale.

Remaining scaling features, not prerequisites for platform stability:

- Distributed evaluation
- More efficient artifact processing
- Larger experimental populations beyond what Phase 2 already stress-tested

---

## Future simulation / combat research

**Status: Research.** Preserved as a distinct area because these ideas
could change the nature of the game enough to require a new rules
compatibility identity, or a future ruleset entirely, separate from the
one v0.10 freezes for 1.0. **None of this is a v1.0 requirement.**

A first architecture/research pass over exactly these candidates —
advanced offensive mechanics, arena/field-size, multiple execution
processes, replication, and translation/placement — is recorded in
[V2_0_ALPHA_ARCHITECTURE.md](V2_0_ALPHA_ARCHITECTURE.md), including which
v1.5 seams are real extension points versus internal cleanup, and a
recommended first experiment (a Python-side core-vulnerability mortality
mechanic). It changes no status below to "Candidate" or "Planned" — the
recommendation is unimplemented and unvalidated by an actual experimental
run.

### Advanced offensive mechanics

Continued exploration of how "attack" should evolve. The important design
principle: attack should preferably remain an **emergent result of
manipulating the simulated environment**, not an abstract engine-decided
`ATTACK opponent` command. Any richer offensive mechanic should make more
interesting player/agent strategy possible without replacing that strategy
with a high-level engine action.

### Arena / field-size research

Further analysis of arena size, rather than assuming the current default
is universally optimal — its interaction with match duration, observation/
read rate, write rate, process/execution count, entrant count, strategy
type, and information availability. A useful framing is **information
density**: what fraction of the arena can an entrant realistically observe
or affect during a match? Very small arenas likely favor immediate
conflict; larger arenas may make exploration, reconnaissance, uncertainty,
prediction, and coordinated deployment strategically relevant. Any change
here should be evidence-driven, in the same spirit as v0.9/v0.10's
evaluation-methodology work. "Partial observability / fog of war" and
"Reconnaissance dynamics" under "Strategic Complexity & Open-Endedness"
below develop the information-availability side of this question further;
not duplicated in full here.

### Multiple execution processes / multipronged agents

Future rules under which one competitive entrant operates through multiple
execution processes or deployed components across the arena — conceptually
a commander, scout, attacker/bomber, territory claimer, and defender
sharing entrant-level state while acting from different positions. The
design goal would be coordinated multipronged strategy, not simply more
raw execution throughput — closer to controlling several pieces on a board
than acting from one effective location.

### Replication / deployment

Whether entrants should be able to create additional execution centers
during a match: spawning a process elsewhere, copying/deploying code,
paying a resource/instruction cost to do so, exposing replicated processes
to destruction, limiting process counts, and trading immediate offense
against investment in expansion. Replication should create strategic
choices, not simply serve as a free multiplier.

### Specialized sub-agents

Potential future entrants built from multiple role-specific components
(scout, attacker, defender, claimer, coordinator) rather than clones of one
controller — enabling research into communication, specialization,
distributed planning, and coordinated attacks. No implementation or API is
defined for this yet.

### Future rulesets

If any of the above materially alters gameplay, it belongs in a clearly
versioned future ruleset rather than a silent mutation of the 1.0 rules:

- **Ruleset v1** — the stable Bytefray 1.0 game, frozen by v0.10 (see
  [ROADMAP.md](ROADMAP.md)).
- **Later ruleset(s)** — experimental multiprocessing/replication/
  advanced-combat variants, versioned separately.

Historical evaluations must remain interpretable according to the rules
under which they were produced — this is the same honesty principle
`EVALUATION_RULES_COMPATIBILITY_ID` already applies at evaluation scope,
generalized to gameplay itself.

---

## Strategic Complexity & Open-Endedness

**Status: Research.** `V2_0_ALPHA_ARCHITECTURE.md`'s own §2 finding (from
v0.6.1, see `CHANGELOG.md`) is that unrestricted "claim as much of the
arena as fast as possible, and never stop" play is close to dominant under
current scoring, with no viable defensive counter-strategy. This section
collects research candidates for mechanics that could make simple,
globally-dominant strategies harder to discover, while preserving what
already makes Bytefray useful as a strategy-research platform:
deterministic evaluation, rules a human can read and reason about, exact
reproducibility, and independence from any one AI/ML framework. These are
research candidates for a *possible* future experimental ruleset, in the
spirit of the `bytefray-rules-2-alpha1` Vulnerable Core experiment
(`V2_0_ALPHA1_EVALUATION.md`) — narrow, falsifiable, additive-identity, and
measured against the existing starter roster before any wider claim is
made — not promises about the canonical Bytefray ruleset, and not made
committed release requirements merely by being recorded here.

The following are the strongest candidates for an eventual experimental
ruleset or dedicated v2.x research pass:

### Partial observability / fog of war

`RULES.md`'s "Observation and information boundaries" already restricts
*direct* state inspection, but both runtimes permit `READ`/`LOAD` of any
arena address at any time ("Arbitrary READ/WRITE"), so an entrant with
budget to spend effectively has unconditional global information today.
Research candidate: limit what an entrant can observe without spending an
action on it — a radius-limited field of view, a local-neighborhood-only
read, memory of previously observed but potentially stale cells, or
configurable visibility rules.

> Does reducing global information meaningfully increase strategic depth
> and reduce the effectiveness of simple, globally-optimized strategies?

**High-interest.** Not a commitment to changing the canonical ruleset.

### Reconnaissance dynamics

A companion question to observability: should information cost something?
Candidate mechanisms include explicit scanning, temporary expanded
visibility, low-cost scout behavior, or reconnaissance actions that
compete with execution/write budget for the same resource. Deliberately
**do not assume a new VM opcode is required** — document and try an
engine/ruleset-level experiment using the existing `READ` vocabulary
first (informally prefigured by `bytefray-rules-2-alpha1`'s Core Seeker
reference agent, which spends part of its budget scanning for
concentrated foreign ownership before committing to an attack, per
`V2_0_ALPHA_ARCHITECTURE.md` §6); a permanent instruction-set expansion
needs its own separate justification.

**High-interest.**

### Agent-wide execution / memory bandwidth budgets

If "Multiple execution processes / multipronged agents" above is ever
pursued, a related and independently useful question is whether resource
limits should apply across an agent's *complete* process tree rather than
treating each spawned process as separately-funded capacity — a total
instructions-per-frame ceiling, a total writes-per-frame ceiling, or
another shared, configurable budget. Research questions should cover
whether this produces useful tradeoffs among a single strong process, a
swarm, scouts, defenders, and dormant reserves, and specifically whether
it makes process proliferation a meaningful strategic cost rather than a
free multiplier — directly relevant to the risk `V2_0_ALPHA_ARCHITECTURE.md`
§5 already names for candidate (C): "replication that isn't cost-bounded
becomes a free multiplier by construction."

**High-interest.** Depends on multi-process entrant semantics existing at
all — see "Multiple execution processes / multipronged agents" above; not
a standalone mechanic on its own.

### Memory decay / territory maintenance

Investigate deterministic decay or reset of arena cells that are not
actively maintained — for example, resetting ownership after N untouched
ticks, with configurable thresholds, possibly limited to certain cell
states. Prefer deterministic decay over any probabilistic form. Research
questions: does decay reduce static defensive dominance, encourage
movement and territory maintenance, weaken early-game snowballing, and
create a meaningful maintenance cost?

**High-interest.**

### Seeded environmental noise / memory corruption

Investigate controlled environmental faults — memory corruption, read/
write errors, instruction faults, or hazardous arena zones. Any stochastic
behavior here must preserve Bytefray's existing reproducibility guarantee:
**the same agents, the same Ruleset identity, the same orientation, and
the same seed must still produce the same match**, exactly as `RULES.md`'s
"Seed as a gameplay concept" and the VM/Python determinism clauses already
require for everything else in the engine. Prefer seeded pseudo-random
behavior and explicit environmental configuration over anything
undeclared. Fixed hazard zones may be more strategically interesting than
uniform global corruption, since they add geography and a risk/reward
tradeoff rather than a uniform tax.

**Medium-high / experimental.**

### Behavioral ecology / emergent-strategy measurement

Not a gameplay mechanic — an evaluation/research objective, and one
Bytefray is already partway toward: v1.6 Phase 5's `behavior:` profile
(`V1_6_PHASE5_BEHAVIOR_ANALYSIS.md`) already derives survival, write
activity, territory occupancy/retention/spread, and kill-interaction rates
per cell (see "Clustering agents into behavioral archetypes" under
"Richer evaluation / statistical analysis" above, which this widens).
Future evaluation could characterize agents using a fuller metric set —
expansion rate, process count, process mortality, write intensity,
movement, opponent-contact frequency, recovery after damage, and resource
efficiency, alongside Phase 5's existing dimensions — in service of
identifying naturally occurring strategy classes (expanders, fortresses,
raiders, parasites, scout-heavy agents, resilient/recovery-focused agents,
burst attackers) from measurement, rather than hard-coding archetypes into
the engine. Any of the mechanics above would make this measurement more
informative, not less: a wider behavioral spread is itself a plausible
success signal for any of them, the same way `territory_retention` already
served that role for `bytefray-rules-2-alpha1`
(`V1_6_PHASE5_BEHAVIOR_ANALYSIS.md` §14.1/§14.4).

**High research value.**

The following are potentially valuable architecture studies, not yet
feature commitments — each needs its own research pass before a design is
chosen:

### Arena topology abstraction

Investigate whether arena semantics can eventually separate from the
current flat `pos % arena_size` addressing (`V2_0_ALPHA_ARCHITECTURE.md`
§2) enough to support toroidal layouts, irregular graphs, or layered
graphs — alongside the current linear/grid layout — behind something like
a `neighbors(cell) -> cells` interface. Not to be implemented now; the
primary research question is whether topology can become configurable
without destabilizing addressing, movement, replay, serialization,
visualization, agent assumptions, evaluation identity, or rules
compatibility.

**Medium / architecture study.** Graph-based or layered topology should be
investigated before literal 3D geometry — see "3D memory arenas" below.

### Multi-agent / team semantics

Investigate what genuinely distinct cooperating agents, squads, or
independently controlled subagents would mean for Bytefray, without
conflating today's internal processes/threads with separately rewarded
agents. `EntrantIdentity` (`V2_0_ALPHA_ARCHITECTURE.md` §3) is a clean
value object other identity concepts could follow the shape of, but it
does not itself define what an independently meaningful team member is.
Credit-assignment research (below) should wait until that definition
exists.

**Medium / deferred architecture study.**

### Population evaluation API

Consider whether `bytefray.evaluation`'s existing infrastructure (`agents
evaluate`, presets, Phase 2 parallel workers) should eventually support
efficient large-population experimentation — reproducible batch matches,
tournament pools, configurable opponent populations, machine-readable
metrics, deterministic evaluation identities — while keeping the engine
independent of any specific machine-learning framework. Related to, but
distinct from, "Evaluation performance and scaling" above.

**Medium-high enabling infrastructure.**

The following are interesting, but should **not** become core Bytefray
engine responsibilities unless future evidence strongly justifies moving
that boundary — explicitly external research integrations:

```text
Bytefray engine
    ↓
evaluation API
    ↓
external research/training harness
    ↓
RL / evolutionary / self-play system
```

Bytefray's job in this picture is reproducible evaluation primitives;
everything below stays in an external harness built on top of them.

### Population-based self-play / MARL

Evolving or training agents against changing opponent populations.
Bytefray should expose reproducible evaluation primitives; external tools
should handle training. Bytefray should not become a PyTorch/JAX/RL
framework.

**External research — not core Bytefray.**

### Credit assignment for subagents

Only becomes well-posed once genuine multi-agent/team semantics (above)
exist; assigning rewards to individual Bytefray processes today would risk
turning an implementation detail into gameplay semantics.

**External/deferred research — depends on multi-agent semantics.**

### Automated agent synthesis / genetic evolution

Genetic programming, evolutionary search, novelty search, MAP-Elites, or
other quality-diversity algorithms, consuming Bytefray's evaluation
results and reproducibility guarantees while the evolutionary system
itself stays external.

**External research — high experimental interest, not core engine.**

### LLM-guided mutation operators

A candidate-population → Bytefray evaluation → fitness/behavioral metrics
→ LLM-guided mutation → new candidates loop, testing whether repeated
selection can produce novel strategies that were not explicitly
hand-designed. Do not add LLM APIs, model dependencies, inference
runtimes, API keys, or provider-specific code to the Bytefray engine for
this.

**External research — interesting but out of core scope.**

### Open-ended evolution / MAP-Elites ecology

Quality-diversity search over Bytefray's behavioral metrics (v1.6 Phase 5
and the wider set above) to find multiple viable ecological niches rather
than optimizing win rate alone. Scientifically interesting; belongs in an
external experiment harness built on top of Bytefray's evaluation API.

**External research — long-term.**

Not every topology experiment has equal priority:

### 3D memory arenas

Literal 3D arena geometry currently appears to offer relatively little
additional research value compared with the generic graph/topology
abstraction above, while introducing substantially greater visualization,
replay, usability, and implementation complexity. Not removed from
consideration, but deprioritized behind graph/layered topology research.

**Low — defer indefinitely unless future research justifies it.**

### Interactions with existing v2.x work

These additions complement, rather than displace, the existing v2.x
direction (Reactive Core Defender / strategic-agent research, GUI/display
polish, Replay Viewer HUD separation, Agent Designer presentation
improvements, field-size/engine-performance research, and ongoing
ruleset/strategy-balance investigation). Some likely interactions worth
keeping in mind as that work continues:

- shared execution/write budgets across a process tree may materially
  affect Reactive Core Defender-style strategic-agent research, if or when
  multi-process entrants exist;
- partial observability would change how defender/reconnaissance
  strategies are evaluated, including any future successors to
  `bytefray-rules-2-alpha1`'s Core Defender/Core Seeker reference agents;
- larger arenas (see "Arena / field-size research" above) likely make
  reconnaissance and information cost more strategically important, not
  less;
- behavioral-ecology metrics may improve interpretation of future balance
  studies the same way `territory_retention` already did for the
  Vulnerable Core evaluation.

---

## Other future items

**Status: mixed — see each item.**

- **Redcode/pMARS authoring and evaluation improvements** (maintenance-only
  in 1.x unless concrete demand justifies more).
  Redcode/pMARS interoperability is not cancelled; Python-side authoring,
  evaluation, provenance, and the ruleset itself are expected to mature
  first (see [ROADMAP.md](ROADMAP.md)'s v0.10 product-boundary item).
- **Improved Designer functionality** (Candidate).
- **Richer GUI access to evaluation/history/provenance** — **status:
  substantially addressed.** `docs/ROADMAP.md`'s shipped v1.1.0
  section covers the Evaluation History browser, two-run comparison, and
  revision/provenance inspection; its shipped v1.3.0 section records
  comparison-row drill-down and Designer revision restore.
  The broad item is not duplicated here. It remains as a pointer because
  evaluation-history indexing and further comparison/drill-down refinement
  are still smaller-grained candidates rather than fully closed.
- **Additional starter/reference agents** (Candidate).
- **Agent ecosystem/sharing** — see "Agent packaging / sharing" above;
  not duplicated here.
- **Future rules experimentation** — see "Future simulation / combat
  research" above; not duplicated here.

Existing roadmap ideas are retained here where still justified, and
rewritten or removed only when they clearly conflict with the current
v0.10/v1.0 direction described in [ROADMAP.md](ROADMAP.md).
