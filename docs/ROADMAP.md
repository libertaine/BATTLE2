# Bytefray Roadmap

This document describes where Bytefray is headed after v0.9.0: the purpose
of v0.10.0, the criteria for declaring v1.0.0, and how the project decides
what belongs in each. It complements, rather than replaces,
[CHANGELOG.md](../CHANGELOG.md) (what actually shipped, release by release)
and the compact version table in [README.md](../README.md#roadmap). Ideas
that are deliberately **out of** the v1.0 scope — accessible authoring,
agent sharing, richer evaluation statistics, arena/combat research, and so
on — are catalogued separately in [FUTURE_PLANS.md](FUTURE_PLANS.md) so they
stay recorded without turning v1.0 into a checklist of every interesting
feature anyone has proposed.

## Terminology

Status words below are used consistently and are not interchangeable:

- **Planned** — scoped for a specific upcoming release.
- **Candidate** — has real merit and a plausible design, but no assigned
  release; likely to happen if usage or evidence justifies it.
- **Exploratory** — a design direction being thought through; not yet
  validated against evidence, and the shape described could change
  substantially or not happen at all.
- **Research** — requires investigation (data, prototypes, or both) before
  anyone could responsibly commit to a design.
- **Unscheduled** — real, retained, not actively planned.

None of these are promises. They describe how seriously an idea is being
held, not when — or whether — it ships.

## Where Bytefray is now

Bytefray has shipped through **v0.9.0** (see the version table in
[README.md](../README.md#roadmap) for the full milestone-by-milestone
history). v0.9's theme, **Orientation-Aware Evaluation**, closed a
structural first-mover bias present in every `bytefray agents evaluate`
matrix ever run: the candidate under evaluation always occupied the
always-first-acting physical slot, and a shipped starter agent's own source
comments already documented and exploited exactly that bias. Both entrant
orientations now run by default; `bytefray.evaluation` moved to schema/
identity v4; gameplay, scoring, winner resolution, and Python scheduling
order were byte-for-byte unchanged. v0.9's own release notes also disclose,
explicitly, that arena alignment is still fixed and that translation
robustness was investigated but not evaluated by that release — v0.10 picks
that up directly (below).

## v0.10.0 — Platform Stabilization / v1.0 Readiness

v0.10 is intentionally a stabilization release, not another broad feature
release. Its purpose is to answer one question: **is the existing Bytefray
platform ready to have its important contracts declared stable for the 1.x
series?** Concretely, that means:

### 1. Freeze the Bytefray 1.0 rules contract

Establish, formally, the default ruleset intended for v1.0 — explicit
semantics for scoring, scheduling, entrant orientation/order, arena
behavior, observation, mortality/termination, winner determination, and
supported agent-runtime behavior. `bytefray.evaluation` already has a
narrow, evaluation-scoped compatibility identifier
(`EVALUATION_RULES_COMPATIBILITY_ID`) that is bumped only for
scoring/winner-resolution/scheduling-order/seed-policy changes and is kept
deliberately separate from schema/identity versioning; v0.10 should decide
whether the *gameplay* ruleset itself needs an equivalent, first-class
compatibility identity of its own, so a future gameplay change (see
[FUTURE_PLANS.md](FUTURE_PLANS.md)'s combat-research section) can be
introduced honestly, without silently reinterpreting what an older
evaluation or replay actually measured.

### 2. Close remaining evaluation-methodology gaps

Review the evaluation system for any remaining structural dimensions that
could materially affect competitive results. One area is already scoped
from v0.9's own development work: **translation / placement robustness**
— whether fixed absolute arena alignment creates a structural bias
analogous to the entrant-orientation bias v0.9 closed. This was already
investigated during v0.9 development: a dedicated study found the
evidence for gameplay-rule impact mixed (no rule change was justified),
but confirmed that fixed-alignment claims about relative strategy strength
can be artifacts of translation phase, and that arena translation should
be treated as an evaluation variable going forward — the same shape of
conclusion that motivated entrant orientation. That study also found that
translation is directly usable for VM/native entrants today (arena
placement is already a first-class, identity-tracked field for them), but
is **not currently implementable for Python entrants** without new shared
runtime work: either a new Agent API surface exposing a per-match origin
(rejected as a primary mechanism, since it would only help agents written
to consult it, not the existing shipped roster), or a transparent,
engine-level per-match address remapping applied at the arena boundary
(bijective and content-preserving, but a real change to the runtime layer
every Python match shares, not an additive change local to the evaluation
feature). v0.10 does not need to repeat that investigation; it needs to
decide, informed by it, whether to build that runtime layer and wire
placement into `agents evaluate` the way orientation was wired in v0.9, or
to continue explicitly disclosing arena alignment as fixed and untested.
The goal is methodological honesty, not adding matrix dimensions merely
for completeness.

### 3. Define stable versus unstable interfaces

Document what Bytefray v1.x intends to preserve as stable contracts, and
what is explicitly *not* promised to remain stable. Candidates to inspect
(not assume) include the Agent API v1 contract, documented CLI behavior,
the persisted result schema (`battle2.result`), the replay schema
(`battle2.replay`), the evaluation schema/compatibility behavior
(`bytefray.evaluation`), agent revision/provenance identity, the rules
compatibility identifier(s) from item 1, and readability of historical
artifacts under future versions. A dedicated `docs/COMPATIBILITY.md` may be
worth creating as part of this work if it makes those contracts
substantially clearer than folding them into existing schema docs — that
decision, and the document itself, belongs to v0.10, not to this roadmap.

### 4. Clarify supported product boundaries

For v1.0, the core product should be coherent rather than claiming every
runtime has complete parity. The primary platform is the Python Agent API,
the native Bytefray simulation, replay, tracing/inspection, evaluation,
history/provenance/revisions, and the supported CLI/Designer workflows.
Redcode/pMARS interoperability remains part of Bytefray's story, but v1.0
should not be blocked on full Redcode authoring, evaluation, provenance, or
gameplay parity, none of which exist today.

### 5. Release qualification

A deliberate release-readiness validation pass across supported
environments and upgrade paths: clean Windows installer and portable
builds, Python wheel installation, supported Linux/headless installation,
existing data-root compatibility, reading historical replay/evaluation
artifacts, revision verification, deterministic reproduction, and
clean-install/upgrade/uninstall behavior where applicable. This is a
release-readiness objective, not a promise of a specific new automated test
suite.

### 6. Polish the first-user workflow

A new user should be able to move through
create → validate → test → inspect → modify → evaluate → compare → replay
without needing undocumented project-development knowledge, from either
the CLI or the Designer. This does not require full CLI/GUI parity.

## v1.0.0 — Stable Bytefray Platform

v1.0 is a **stability and maturity milestone**, not "every planned feature
implemented." The release criterion is approximately:

> A Bytefray agent written against the documented 1.0 Agent API can be
> developed, tested, evaluated, reproduced, versioned, and replayed using a
> documented stable ruleset, and its persisted artifacts remain
> intelligible throughout the Bytefray 1.x series.

The intended development model: v0.10 discovers and fixes anything that
would make a 1.0 stability declaration premature. If no major architectural
problem is uncovered, v1.0 follows directly, without another broad
pre-1.0 feature cycle — v1.0 itself should ideally contain little or no new
architecture compared with the stabilized v0.10 platform. A v0.11 feature
milestone is **not** created automatically after v1.0; what comes next is
drawn deliberately from [FUTURE_PLANS.md](FUTURE_PLANS.md) as usage and
evidence justify it, the same way milestones have been chosen throughout
Bytefray's history.

## After v1.0

Substantial work is intentionally kept out of the required v1.0 scope:
accessible agent-authoring (a small, deterministic DSL compiling to the
Agent API), agent packaging/sharing, richer evaluation and statistical
analysis, evaluation performance/scaling, and deeper simulation/combat
research (arena-size effects, multipronged/multi-process entrants,
replication, and any future ruleset that would require its own
compatibility identity separate from 1.0's). None of it is lost — see
[FUTURE_PLANS.md](FUTURE_PLANS.md) for the organized, maturity-labeled
catalogue.
