# Bytefray v2.0 Alpha Research — Summary and Closeout

This is the durable synthesis of the eleven-alpha v2.0 gameplay-research
sequence (`v2.0.0-alpha.1` through `v2.0.0-alpha.11`), all conducted on the
`v2.0-development` branch without touching `main`. It exists so a future
reader can understand *what the alpha program collectively established*
without reading eleven individual experiment reports end to end. It
interprets; it does not replace or rewrite them. Each alpha's own document
(`docs/V2_0_ALPHA<N>_*.md`) remains the authoritative, uncorrected evidence
record for that experiment, including its own historical terminology and
identities (`bytefray-rules-2-alpha1`, `bytefray-rules-2-alpha11`).

Every alpha held `main` unchanged at `5593d287f95a24996bb3b105befbc625a00795db`
and left `origin/v2.0-development`'s unrelated commit `151866c` untouched —
that divergence is still present and still deliberately unreconciled.

## Alpha.1 — Vulnerable Core feasibility

Implemented the first Python-runtime-only mortality mechanic:
`bytefray-rules-2-alpha1`. A `CORE_SIZE = 8` contiguous cell window,
anchored at `entrant.start`, is seeded as sole-owned at match
initialization; an entrant is core-captured when it owns zero of its own
core cells, checked once per tick after that tick's actions and before
scoring. Two new reference agents were built to exercise it: **Core
Defender** (blind periodic refresh) and **Core Seeker** (scan-then-commit
search).

A 420-match matrix (7 agents × 5 seeds × 2 Rulesets) found real, bounded,
attributable core capture — 7.6% of alpha-condition matches — but every
single capture was caused by Core Seeker specifically; ordinary blind
expansion (Claimer, Hunter, and the rest) neither captured a core nor was
threatened by one, because a coprime blind sweep cannot reliably cover one
fixed 8-cell window within the match's action budget. Core Defender's blind
refresh never won a single match and lost every matchup against Core
Seeker. **Ordinary writes can create deliberate core mortality, but only
under a deliberately targeted search strategy** — the first offensive
benchmark was established, but unrestricted expansion was not yet checked
by the mechanic itself.

## Alpha.2 — Reactive defense

Built **Reactive Core Defender**: a content-based (`READ`-then-compare
against its own signature) SIGN/PATROL/ALERT design using only ordinary
Agent API v1 actions, with no privileged information about any opponent.

Across a 560-match matrix, it survived Core Seeker in every vulnerable-
orientation match (0/10 core-captured, versus the blind defender's 5/10) at
a cost within a few percent of blind defense, while remaining globally
non-competitive against unrestricted expansion (0/70 wins either way). This
established that **Agent API v1 can express meaningful, evidence-driven
reactive defense** — no new API surface was needed to make defense react to
detected intrusion rather than merely cycle on a fixed clock. It also
surfaced, without yet explaining, a fixed-schedule orientation artifact in
Core Seeker's own scan geometry that later alphas (6–8) would characterize
and then generalize past.

## Alpha.3 — 1v1 scoring sensitivity

A measurement-only pass (no mechanic or weight change) over the existing
three-weight scoring model (`alive`, `kill`, `territory`), using alpha.1/2's
matches as its evidentiary base. Found, algebraically and empirically, that
`territory` is the *only* weight with any leverage over any 1v1 outcome in
this population — `alive` and `kill` are mathematically dormant under
`resolve_winner`'s single-survivor rule whenever a match is strictly
two-entrant. No reweighting of the existing model could bring Reactive Core
Defender to score parity with Core Seeker. **Existing score-weight changes
cannot solve the ecology problem structurally** in a 1v1 format; the two
directions this left open were a multi-entrant evaluation format (where a
death mid-match, with others surviving, might finally give `alive`/`kill`
something to act on) or scrutiny of `resolve_winner`'s survival-first rule
itself.

## Alpha.4 — Multi-entrant feasibility

Asked whether moving to 3+ entrants naturally activates the scoring terms
alpha.3 proved dormant in 1v1. Confirmed the native match/scoring/scheduler
stack is **already substantially N-entrant-generic** with zero production
changes required, and that elimination-with-continuation produces genuine
third-party strategic interactions. The scoring-relevance half of the
question was left open, not falsified, on a deliberately small 12-match
sample (0/12 cases where `alive`/`kill` changed the outcome, with both
observed captures happening late) — too small to distinguish a real ceiling
from an artifact of that sample's timing.

## Alpha.4.1 — Winner-semantics hardening

A targeted correctness fix, not a research alpha: enforced, as the natural
N-entrant extension of the 1v1 rule already in place, that **an entrant
that is dead at the end of a match cannot win regardless of accumulated
score, while any entrant survives**. No new Ruleset identity; folded
directly into `battle_engine.results.resolve_winner`, the one authoritative
implementation both runtimes share.

## Alpha.5 — Multi-entrant scoring activation

A larger (2.5× alpha.4's scale), capture-timing-engineered 3-way matrix,
now measuring outcomes restricted to the survivor subset per alpha.4.1's
corrected semantics. Found a **closed-form proof that `alive` can never
have scoring leverage** under the current termination rule, at any sample
size or agent selection — not merely "not yet demonstrated," but
structurally closed. `kill` remained technically activatable in principle
but showed no positive signal at the scale tested. Combined with alpha.3,
this closed the score-reweighting direction entirely: **the alive term
remains structurally dormant among surviving tick-limit entrants, and kill
score alone is insufficient to create a meaningful ecology** — the
scoring-model lever was fully exhausted by this point in the program.

## Alpha.6 — Core Seeker scan-timing characterization

A mechanistic characterization pass (no production change) that decoded
exactly why Core Seeker's captures clustered around ticks 159–168 in the
3-way matrix. Found Core Seeker's actual behavior to be a **fixed absolute
schedule with an echo-lock** confirmation shortcut, not the general,
adaptive search the informal narrative up to that point had assumed. The
historical seat-B-only capture pattern was traced directly to this fixed
schedule rather than to any inherent property of Vulnerable Core. Core
Seeker was downgraded, from this point forward, to a **narrow, deterministic
characterization fixture** rather than evidence of general offensive
capability — a status it retains permanently (see below).

## Alpha.7 — Spatial/start-position characterization

A controlled placement experiment: using alpha.6's validated model of Core
Seeker's scan geometry, this alpha *predicted* — before running any
match — which core placements should be reachable, unreachable (COLD), or
mixed, then executed only those pre-registered placements. Predictions held
exactly: COLD placements were provably unreachable by Core Seeker (0/9
matches, zero partial covering-assault windows). This confirmed the
historical seat-B vulnerability was a **placement artifact of one fixed
convention**, not a property of Vulnerable Core itself — the mechanic
generalizes across placement once a genuinely capable searcher is used. It
also surfaced, incidentally, that **ordinary blind writes can capture a
core through pure ownership overlap** in mixed-placement conditions,
independent of any deliberate search.

## Alpha.8 — Placement-agnostic core offense benchmark

Designed, built, and validated **Core Tracker**: a coarse-to-fine search
reference agent whose scan geometry is a function of the match seed, not of
a fixed absolute schedule, using only ordinary Agent API v1 `READ`/`WRITE`
and no opponent-position privilege whatsoever. It succeeded against exactly
the COLD placements Core Seeker could never reach, establishing the first
genuinely **placement-agnostic offensive benchmark** in the program — and,
as an unplanned finding, exposed Reactive Core Defender losing in the
*control* placement condition for the first time anywhere in the series,
directly motivating alpha.9.

## Alpha.9 — Defense robustness under generalized offense

Asked whether Reactive Core Defender's advantage over blind defense
(established in alpha.2 against Core Seeker specifically) generalizes
against a more capable, less-predictable attacker. Found that **scheduler
order can flip contested capture outcomes** in roughly 40% of matched
offense-vs-defense cells, and that **reactive defense is not automatically
superior to blind defense** once faced with a genuinely general attacker —
the earlier apparent advantage was partly an artifact of Core Seeker's own
narrow, late, delay-dominated timing. No defender agent was redesigned in
response; this finding was carried forward as evidence, feeding directly
into alpha.11's explicit decision to retain and disclose capture-check
timing as a strategic property rather than "fix" it in isolation.

## Alpha.10 — Strategic ecology validation

The originally planned conclusion of the alpha sequence: a large (981-match)
matrix testing whether the individually-validated mechanics — expansion,
generalized offense (Core Tracker), and defense — interact as a
strategically meaningful ecology together, not merely one at a time. The
mechanics each worked in isolation, but **pure territorial expansion
remained close to a universal solution** across the matrix (ecology verdict
"C" — not resolved). The root cause was traced to an information
asymmetry: because a core's cells are seeded at byte `0`, indistinguishable
from untouched arena, an entrant that never touches its own core is
permanently invisible to any content-based search, while an entrant that
*defends* its core becomes findable precisely because defending requires
writing to it. This was the wrong incentive in the most direct possible
sense, and became the single unresolved gameplay question handed forward to
alpha.11.

## Alpha.11 — Ruleset-v2 Candidate Resolution

Resolved alpha.10's information-asymmetry finding directly. **Resolution
A** introduced persistent core observability: cores are seeded with the
public constant `CORE_BEACON_BYTE = 0xCE` instead of `0`, and at the end of
every tick, any cell of a living entrant's own core that entrant still owns
and that has gone blank (`0x00`) is restored to the beacon — never
repairing attacker damage, never restoring ownership, never overwriting an
owner's own non-zero content. This new experimental identity,
`bytefray-rules-2-alpha11`, was deliberately **not** aliased to
`bytefray-rules-2-alpha1`.

A matched, 1,316-match two-Ruleset resolution corpus showed expansion's
near-universal dominance materially resolved (`claimer`'s 1v1 win rate fell
from 98.4% to 60.9%, combined from 90.1% to 58.1%) with **no new dominant
strategy replacing it** — the highest aggregate win rate anywhere was 60.9%
(1v1) / 58.1% (combined), against alpha.10's 98.4% / 84.7%. Offense gained
real but non-universal leverage (Core Tracker's combined win rate rose from
2.6% to 13.1%, still the weakest of the five agents); defense gained a
measurable positive marginal value and was no longer uniquely penalized for
defending (defender combined win rate roughly doubled). **Resolution A
returned A-PASS**, so **Resolution B (deterministic territory maintenance)
was correctly never entered** — no decay or maintenance mechanic was
designed, implemented, parameterized, or executed anywhere in this alpha.
**Resolution C returned GO** for a separate v2 beta-planning phase, with the
resulting candidate semantics recorded in `docs/V2_0_RULESET_V2_CANDIDATE.md`
under the still-experimental `bytefray-rules-2-alpha11` identity — deliberately
not yet promoted to a permanent `bytefray-rules-2` identity, which alpha.11
explicitly left as a beta-planning decision.

## What the alpha program did not resolve, and correctly left open

Alpha.11 §26 records these explicitly, and this summary does not repeat
their evidence, only their disposition: whether `CORE_SIZE`/
`CORE_BEACON_BYTE` should ever become Ruleset-versioned parameters (beta1
freezes them as fixed constants — see `docs/V2_0_BETA1_PLAN.md`); Core
Tracker's ~21-action self-core false-positive inefficiency (beta1 cleans
this up as reference-agent maintenance, not rebalancing — see
`docs/V2_0_BETA1_PLAN.md`); scheduler-order sensitivity in contested cells
(accepted as strategy, with an evaluation-methodology obligation for beta);
the seed-methodology widening that a search-based agent's presence now
requires; pre-existing seat/orientation confounds from alpha.5–alpha.10,
orthogonal to alpha.11's own finding; and multi-entrant product workflow,
architecturally proven but not yet exposed by any product surface.

## Alpha research disposition: CLOSED.

Alpha.1 through alpha.11 form a complete, evidence-backed research
sequence: they established that deliberate core mortality is achievable
under ordinary Agent API v1 play, that reactive defense is expressible and
meaningfully different from blind defense, that the existing scoring model
has no further reweighting leverage to give, that the engine is genuinely
multi-entrant capable, that a placement-agnostic offense benchmark
generalizes where a placement-fixed one does not, that scheduler order is a
real and disclosed competitive factor rather than a bug, and — the
program's central resolution — that persistent core observability resolves
expansion's near-universal dominance without creating a new one. No further
`alpha.12` will be created, and no further broad gameplay research reopens
under this alpha sequence. The alpha program's evidence is now treated as
closed history: the eleven documents above remain the authoritative record
of what was tried, measured, and found, and are not rewritten by beta work.

Any later experimental gameplay direction — a different core geometry, a
territory-maintenance mechanic, Agent API v2, multiprocess/replicated
entrants, or any other idea catalogued in `docs/FUTURE_PLANS.md` — belongs
to **post-2.0 v2.x research**, or to a **future, explicitly versioned
Ruleset experiment**, not to an extension of this alpha sequence. Beta work
beginning now (`docs/V2_0_BETA1_PLAN.md`) converts the evidence-backed
`bytefray-rules-2-alpha11` candidate into the permanent, compatibility-honest
`bytefray-rules-2` identity — it does not reopen the questions this program
already closed.
