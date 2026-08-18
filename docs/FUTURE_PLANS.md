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

**Status: Delivered in part (v1.6 Phase 4); remainder Candidate, with one
Exploratory sub-item.**

- ~~Richer aggregate evaluation analysis and confidence/statistical
  summaries.~~ Delivered in v1.6.0 Phase 4: Wilson score intervals on
  observed win rates and an exact paired candidate-vs-baseline
  significance test (exact sign test / exact McNemar test) over discordant
  paired conditions, with by-opponent/by-orientation breakdowns -- see
  [V1_6_PHASE4_EVALUATION_ANALYSIS.md](V1_6_PHASE4_EVALUATION_ANALYSIS.md).
- Ranking systems such as Elo/Glicko or similar.
- Benchmark/reference agent populations.
- Improved comparative visualization.

Ranking systems in particular should not be treated as a v1.0 requirement;
Phase 4 explicitly does not introduce one (no Elo/Glicko/TrueSkill/global
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
evaluation-methodology work.

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
