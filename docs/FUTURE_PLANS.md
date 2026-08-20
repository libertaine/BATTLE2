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
  are sufficient for it.

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

**Status: Research, except where the v2.0 alpha program (below) resolved a
specific item.** Preserved as a distinct area because these ideas could
change the nature of the game enough to require a new rules compatibility
identity, or a future ruleset entirely, separate from the ones `bytefray-rules-1`
and (as of v2.0.0-beta1) `bytefray-rules-2` freeze. **None of this is a
2.0 requirement** beyond what the beta1 plan
([V2_0_BETA1_PLAN.md](V2_0_BETA1_PLAN.md)) already scopes.

A first architecture/research pass over exactly these candidates —
advanced offensive mechanics, arena/field-size, multiple execution
processes, replication, and translation/placement — is recorded in
[V2_0_ALPHA_ARCHITECTURE.md](V2_0_ALPHA_ARCHITECTURE.md). The eleven-alpha
research program that followed it is now complete and closed (see
[V2_0_ALPHA_RESEARCH_SUMMARY.md](V2_0_ALPHA_RESEARCH_SUMMARY.md) and
`docs/ROADMAP.md`'s "v2.0 Alpha Research — Complete" section); it validated
exactly one of the candidates below — a Python-side vulnerable-core
mortality mechanic with owner-maintained core observability — into the
`bytefray-rules-2` beta candidate. The rest remain Research/Candidate items
below, each with its disposition updated to reflect what the alpha program
actually found rather than what it merely proposed to investigate.

### Core observability

**Status: validated, moving into Ruleset-v2 beta semantics — no longer
open research.** Alpha.10 found that seeding a core's cells at byte `0`
(indistinguishable from untouched arena) makes an undefended core invisible
to search while making a *defended* core the only kind findable — the wrong
incentive. Alpha.11 resolved this with an owner-maintained non-blank
invariant (`CORE_BEACON_BYTE`), validated across a 1,316-match corpus, and
it is now part of the beta1 semantic contract
([V2_0_BETA1_PLAN.md](V2_0_BETA1_PLAN.md)). Recorded here, rather than left buried
under "advanced offensive mechanics" below, because it is the single most
consequential finding the alpha program produced.

### Territory maintenance / memory decay

**Status: Research — retained for later consideration, not required for
Bytefray 2.0.** A deterministic decay/expiry/maintenance-cost mechanic for
claimed territory was designed as a *contingency* in alpha.11 (Resolution
B), gated on core observability (Resolution A) being mechanically sound but
insufficient on its own to resolve expansion's near-universal dominance.
Resolution A returned A-PASS, so the Resolution B gate never opened: **no
territory-maintenance or decay mechanic was designed, implemented,
parameterized, or executed anywhere in the alpha program**, because it
was not needed once core observability alone resolved the finding. This is
not unfinished mandatory v2 work — it is a contingency that a passing gate
correctly bypassed. The idea remains available for later research if future
evidence (post-beta1) reopens the question.

### Advanced offensive mechanics

**Status: Research**, with one clarification from the alpha program: 2.0
offense remains **emergent through ordinary `READ`/`WRITE`/ownership
behavior** under Agent API v1 — both of the alpha program's reference
attackers (Core Seeker, then the placement-agnostic Core Tracker) achieved
deliberate core capture using only the existing action vocabulary, with no
privileged information and no new engine-level action. The important design
principle stands unchanged: attack should preferably remain an **emergent
result of manipulating the simulated environment**, not an abstract
engine-decided `ATTACK opponent` command. An explicit `ATTACK` action
remains a later-research idea only; the alpha program found no concrete
need for one.

### Arena / field-size research

**Status: Research — unchanged, not a 2.0 blocker.** Further analysis of
arena size, rather than assuming the current default is universally
optimal — its interaction with match duration, observation/read rate,
write rate, process/execution count, entrant count, strategy type, and
information availability. A useful framing is **information density**:
what fraction of the arena can an entrant realistically observe or affect
during a match? Very small arenas likely favor immediate conflict; larger
arenas may make exploration, reconnaissance, uncertainty, prediction, and
coordinated deployment strategically relevant. Fog-of-war and other
environmental mechanics fall in the same research-only, not-a-2.0-blocker
category. Any change here should be evidence-driven, in the same spirit as
v0.9/v0.10's evaluation-methodology work.

### Multiple execution processes / multipronged agents

**Status: Research — explicitly distinct from validated multi-entrant
matches.** Future rules under which **one** competitive entrant operates
through multiple execution processes or deployed components across the
arena — conceptually a commander, scout, attacker/bomber, territory
claimer, and defender sharing entrant-level state while acting from
different positions. The design goal would be coordinated multipronged
strategy, not simply more raw execution throughput. This is not the same
question the alpha program answered: alpha.4/4.1/5/11 validated
**multi-entrant matches** (3+ independent entrants, each with their own
core, competing in one match) as a real, architecturally supported engine
capability with correct survivor-only winner semantics. Multiple execution
processes belonging to a *single* entrant is a different, still-open
research question this program did not address.

### Replication / deployment

**Status: Research — unchanged, and distinct from the item above.**
Whether entrants should be able to create additional execution centers
during a match: spawning a process elsewhere, copying/deploying code,
paying a resource/instruction cost to do so, exposing replicated processes
to destruction, limiting process counts, and trading immediate offense
against investment in expansion. Replication should create strategic
choices, not simply serve as a free multiplier. Not exercised or validated
by the v2.0 alpha program.

### Specialized sub-agents

**Status: Research — unchanged.** Potential future entrants built from
multiple role-specific components (scout, attacker, defender, claimer,
coordinator) rather than clones of one controller — enabling research into
communication, specialization, distributed planning, and coordinated
attacks. No implementation or API is defined for this yet.

### Agent API v2

**Status: Research — retained as later research only.** The v2.0 alpha
program found **no concrete need** for an Agent API v2: deliberate offense
(Core Seeker, then Core Tracker), reactive evidence-driven defense
(Reactive Core Defender), blind periodic defense (Core Defender), and
placement-agnostic reconnaissance were all implemented and validated
entirely within Agent API v1's existing `READ`/`WRITE`/`NOP`/`HALT`
vocabulary, `Observation`, and `MatchContext`. Ruleset-v2 beta1 retains
Agent API v1 as its supported Python contract. A DSL compiling to the Agent
API (see "Accessible agent-authoring language / DSL" above) should still
wait for an actual Agent API v2 effort before beginning, if one is ever
justified on its own separate grounds.

### Future rulesets

If any of the above materially alters gameplay, it belongs in a clearly
versioned future ruleset rather than a silent mutation of an existing one:

- **Ruleset v1** (`bytefray-rules-1`) — the stable Bytefray 1.0 game,
  frozen by v0.10 (see [ROADMAP.md](ROADMAP.md)).
- **Ruleset v2** (`bytefray-rules-2`) — the beta candidate emerging from
  the v2.0 alpha program (`v2.0.0-beta1`, see [ROADMAP.md](ROADMAP.md) and
  [V2_0_BETA1_PLAN.md](V2_0_BETA1_PLAN.md)), distinct from every historical alpha
  identity that preceded it.
- **Later ruleset(s)** — any future experimental multiprocessing/
  replication/advanced-combat variant, versioned separately from both of
  the above.

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
