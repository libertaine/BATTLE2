# Bytefray Roadmap

This document describes where Bytefray is headed after v0.10.0: the
criteria for declaring v1.0.0, the required pre-1.0 branding/visual-
integration gate, and how the project decides what belongs in each. It
complements, rather than replaces,
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

Bytefray has shipped through **v0.10.0** (see the version table in
[README.md](../README.md#roadmap) for the full milestone-by-milestone
history). v0.10's theme, **Platform Stabilization / v1.0 Readiness**,
answered the question below (all six numbered items are closed): the
Bytefray 1.0 gameplay Ruleset is frozen as `bytefray-rules-1`, the entrant-
orientation-vs-translation evaluation-methodology question is decided
(fixed arena alignment, translation deliberately deferred), the stable
Agent API v1 contract and compatibility model are documented, Ruleset
identity is now persisted directly into native result/replay artifacts and
folded into canonical match identity, and release qualification
(Windows/Linux/wheel install paths, upgrade/uninstall behavior,
first-user workflow) is complete. No gameplay, Agent API, or evaluation
schema change shipped beyond what is recorded as closed below.

**Next milestone: `v1.0.0-rc1`.** The required pre-1.0 branding/visual-
integration gate (see below) is mandatory work for that release candidate,
alongside RC-level qualification; final `v1.0.0` remains blocked until both
are complete.

## v0.10.0 — Platform Stabilization / v1.0 Readiness

v0.10 is intentionally a stabilization release, not another broad feature
release. Its purpose is to answer one question: **is the existing Bytefray
platform ready to have its important contracts declared stable for the 1.x
series?** Concretely, that means:

### 1. Freeze the Bytefray 1.0 rules contract — closed

**Decided in v0.10 Phase 2** (see `docs/RULES.md`): `bytefray-rules-1`
(`battle_engine.rules.BYTEFRAY_RULESET_ID`) is now the first-class,
explicit gameplay-semantics compatibility identity — scoring, scheduling,
entrant orientation/order, arena behavior, observation, mortality/
termination, and winner determination — separate from schema/identity
versioning and from `bytefray.evaluation`'s narrower
`EVALUATION_RULES_COMPATIBILITY_ID`, which is now a derived alias of it
rather than an independently maintained value. A future gameplay change
can bump this identity honestly, without silently reinterpreting what an
older evaluation or replay actually measured.

### 2. Close remaining evaluation-methodology gaps — closed

**Decided in v0.10 Phase 3** (see `docs/COMPATIBILITY.md` and
`docs/RULES.md`): the standard Bytefray 1.0 evaluation contract is
orientation-aware and fixed-arena-alignment, and does **not** claim
translation/placement robustness. This was v0.9's one open
evaluation-methodology question — **translation / placement robustness**,
whether fixed absolute arena alignment creates a structural bias analogous
to the entrant-orientation bias v0.9 closed. v0.9's own dedicated study
found the evidence for gameplay-rule impact mixed (no rule change was
justified), confirmed that fixed-alignment claims about relative strategy
strength can be artifacts of translation phase, and found translation
directly usable for VM/native entrants today but **not implementable for
Python entrants** without new shared runtime work: either a new Agent API
surface exposing a per-match origin, or a transparent, engine-level
per-match address remapping applied at the arena boundary. Phase 3
independently re-verified both findings against the current (now Ruleset
v1/Agent API v1-frozen) source and ran a fresh, independent VM-entrant
study using the production placement mechanism (`MatchEntrant.start`),
which corroborated that relative placement is a real, sometimes large
effect (3 of 4 tested VM matchups flipped winner across placements) while
confirming no path to Python translation exists that avoids either an
incompatible Agent API v1 change (now explicitly off the table, Phase 2)
or the same substantial, separately-scoped runtime engineering v0.9 named
and declined to undertake inline. **Disposition: fixed alignment is the
standard 1.0 methodology; translation remains a documented, deliberately
deferred future capability** — `arena_alignment_mode` already exists as
its extension point, and no evaluation, Ruleset, or Agent API code changed
to reach this decision. See
`runs/research_v0.10/PHASE3_EVALUATION_METHODOLOGY.md` for the full
evidence trail (ignored research, not committed) and
`docs/COMPATIBILITY.md`'s "Experimental/unsupported boundaries" for the
durable, committed statement of what this means for
1.0.

### 3. Define stable versus unstable interfaces — closed

`docs/COMPATIBILITY.md` now documents Bytefray's independent compatibility
axes (project version, Agent API version, Ruleset identity, artifact schema
versions, evaluation methodology, agent revision identity, source
fingerprint versions) with a worked change-impact table, alongside a fully
frozen `docs/AGENT_API_V1.md` (including the literal deterministic
entrant-seed derivation algorithm, pinned by golden-vector regression
tests). The persisted result/replay schemas, `bytefray.evaluation`, agent
revision/provenance identity, and the rules-compatibility identifier from
item 1 are all covered.

### 4. Clarify supported product boundaries — closed

`docs/COMPATIBILITY.md`'s "Experimental/unsupported boundaries" section
names what v1.0's core product actually is — the Python Agent API, the
native Bytefray simulation, replay, tracing/inspection, evaluation,
history/provenance/revisions, and the supported CLI/Designer workflows —
and states plainly that Redcode/pMARS interoperability remains part of
Bytefray's story without blocking v1.0 on full Redcode authoring,
evaluation, provenance, or gameplay parity, none of which exist today.

### 5. Release qualification — closed

v0.10 Phase 5 ran a full release-readiness validation pass: clean Windows
installer and portable builds, Python wheel installation across Python
3.10–3.13, supported Linux/headless installation, existing data-root
compatibility, reading historical replay/evaluation artifacts, revision
verification, deterministic reproduction, and the full
install/upgrade/uninstall lifecycle (including preservation of modified
user data and restoration of prior machine environment values). The v0.10.0
release itself repeated the relevant parts of this pass against the final,
version-bumped build before tagging.

### 6. Polish the first-user workflow — closed

v0.10 Phase 5 fixed the concrete gaps found while walking
create → validate → test → inspect → modify → evaluate → compare → replay
from a clean install: added top-level `bytefray --version` (previously
missing entirely, with unrecognized arguments silently swallowed instead of
erroring), corrected `agents test`'s printed replay-inspection command to
one the CLI actually accepts, and fixed a writable-data-root
false-positive that misdirected a wheel install nested under an unrelated
Bytefray checkout to that checkout's own developer catalog instead of the
documented installed-platform default.

## Required pre-1.0 gate: branding/visual release integration

**Final Bytefray v1.0 must not ship before a dedicated branding/presentation
milestone lands.** This was identified as a required gate during v0.10
Phase 5 (release qualification) and is deliberately **not** part of v0.10
itself — v0.10 is a stabilization release with no branding-implementation
work in its scope. It is recorded here so the roadmap cannot be read as
"v0.10 stabilization complete → proceed straight to v1.0."

The gate covers, narrowly:

- production application/executable icons (the four PyInstaller
  applications: `battle2`, `battle-cli`, `battle-agent-designer`,
  `battle-replay-viewer`);
- Windows executable icon resources (`tools/*.spec`);
- installer icon/branding (`tools/installer.iss`);
- the Agent Designer/application icon specifically;
- repository/GitHub visual assets (social preview, badges as applicable);
- a horizontal/project logo asset;
- README/GitHub-page imagery;
- approximately two representative product screenshots; and
- any other narrowly-justified release-facing visual integration.

None of this is implemented yet; a production brand sheet exists outside
the repository for a later phase to use. Until that milestone lands, treat
any plan to tag `v1.0.0` as blocked, regardless of how ready the underlying
platform (Agent API, Ruleset, schemas, CLI, packaging) otherwise is.

**Recommended sequencing:** `v0.10.0` → `v1.0.0-rc1` (branding integration
happens here) → `v1.0.0`, rather than inserting a separate numbered
`v0.11.0` branding release. Rationale: branding is release-facing polish
for the 1.0 declaration, not a new capability in the sense every prior
minor version (0.1 through 0.10) has been — bundling it into the release
candidate keeps that convention intact, and an RC's own purpose is to be
what v1.0 will actually look and feel like, which is weaker if the RC ships
without the branding real users will see. It also avoids a full extra
tag/build/publish/changelog cycle for content that is presentation, not
architecture. If branding integration turns out to be larger or riskier
than expected once scoped, revisit this and consider a dedicated `v0.11.0`
instead — the RC can iterate (`-rc2`, `-rc3`, ...) either way before
`v1.0.0` is tagged.

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
architecture compared with the stabilized v0.10 platform, aside from the
required branding/visual integration gate above. A v0.11 feature
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
