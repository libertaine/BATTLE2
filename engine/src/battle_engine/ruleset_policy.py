"""Executable Ruleset policy and fail-closed resolver.

``rules.py`` is the frozen, dependency-free record of Ruleset *identity*
(``BYTEFRAY_RULESET_ID`` and its historical-alias/provenance vocabulary),
deliberately kept free of anything executable so it can sit underneath the
runtime, artifact, and evaluation layers without risk of an import cycle
(see its own module docstring). This module is the next layer up: it pairs
that identity with the *executable* Ruleset-v1 semantics that, as of v1.5
Phase 4, have a single shared implementation -- entrant scheduling
(``battle_engine.scheduler.run_sequential_quota``) and match termination
decision/reason (``RulesetPolicy.resolve_termination``) -- and provides one
fail-closed resolver from a Ruleset ID string to its policy.

This is deliberately a thin seam, not a Ruleset framework. Exactly one
Ruleset exists (Ruleset v1); the resolver exists so runtime construction
has one obvious place to obtain Ruleset-owned scheduling/termination
semantics instead of duplicating them per runtime, and so an unrecognized
Ruleset ID fails before any gameplay executes rather than silently running
as v1. Scoring, statistics, and winner resolution are not yet
Ruleset-policy-owned -- see ``docs/V1_5_PHASE4_TERMINATION_POLICY.md`` for
what remains outside this seam and why.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.scheduler import StateT, run_chunked_quota


class TerminationReason(str, Enum):

    """Why a completed Ruleset-v1 match stopped.

    A ``str`` subclass so its ``.value`` -- the persisted/serialized form
    used in ``result.json`` and the golden corpus -- is exactly its member
    name's lowercase spelling; this representation predates Phase 4 and is
    unchanged by it (see ``docs/V1_5_PHASE4_TERMINATION_POLICY.md``'s
    "Reason representation").
    """

    LAST_AGENT_STANDING = "last_agent_standing"
    ALL_AGENTS_DEAD = "all_agents_dead"
    TICK_LIMIT = "tick_limit"


@dataclass(frozen=True)
class TerminationDecision:
    """Whether a Ruleset-v1 match has ended, and why.

    ``reason`` is ``None`` exactly when ``terminated`` is ``False`` -- the
    match should continue and there is nothing to report yet.
    """

    terminated: bool
    reason: TerminationReason | None


@dataclass(frozen=True)
class RulesetPolicy:
    """One Ruleset's executable policy: identity, scheduler, and termination.

    Immutable and intentionally narrow -- it exposes only what current
    runtime code actually routes through it (scheduling, the termination
    decision/reason, and -- as of Beta1 Phase 2 -- which entrant runtime
    kinds this Ruleset supports executing). It has no knowledge of
    persistence, replay/result schemas, or evaluation; those remain the
    concern of the callers that hold a ``RulesetPolicy``, not of the policy
    itself.

    ``supported_runtime_kinds``: ``None`` (the default) means this Ruleset
    imposes no restriction -- every runtime kind
    :class:`~battle_engine.match_service.NativeMatchService` already accepts
    ("vm", "python") may execute under it, exactly as before this field
    existed. A non-``None`` frozenset is this Ruleset's exhaustive supported
    set; see :meth:`unsupported_runtime_kinds`. Only the permanent
    ``bytefray-rules-2`` sets this (Python-only) -- Ruleset v1 and every
    historical alpha identity remain unrestricted, preserving their exact
    existing VM/Python behavior (including alpha's inert-on-VM dispatch).
    """

    ruleset_id: str
    supported_runtime_kinds: frozenset[str] | None = None
    scheduler_mode: str = "sequential"
    scheduler_chunk_size: int | None = None
    scheduler_rotate_start: bool = False

    def unsupported_runtime_kinds(self, kinds: Iterable[str]) -> frozenset[str]:
        """Return which of ``kinds`` this Ruleset does not support executing.

        The authoritative Ruleset/runtime-kind compatibility check (Beta1
        Phase 2): callers -- currently only
        :class:`~battle_engine.match_service.NativeMatchService` -- pass the
        resolved entrant runtime-kind set for one match request and reject
        before any entrant executes if this returns non-empty. Returns an
        empty ``frozenset`` whenever :attr:`supported_runtime_kinds` is
        ``None`` (no restriction) or every requested kind is already
        supported.
        """

        if self.supported_runtime_kinds is None:
            return frozenset()
        return frozenset(kinds) - self.supported_runtime_kinds

    def run_scheduler(
        self,
        states: Iterable[StateT],
        quota: int,
        execute_slot: Callable[[StateT, int], None],
        *,
        tick: int = 1,
    ) -> None:
        """Run this Ruleset's entrant scheduler.

        Dispatches to :func:`battle_engine.scheduler.run_chunked_quota`.
        """

        chunk_size = quota if self.scheduler_mode == "sequential" else (self.scheduler_chunk_size or 1)
        run_chunked_quota(
            states,
            quota,
            execute_slot,
            chunk_size=chunk_size,
            rotate_start=self.scheduler_rotate_start,
            tick=tick,
        )



    def resolve_termination(
        self,
        *,
        alive_count: int,
        tick: int,
        max_ticks: int,
    ) -> TerminationDecision:
        """Decide whether a Ruleset-v1 match has ended, and why.

        Ruleset v1's termination rule, identical across VM, unsupervised
        Python, and supervised Python: no entrants alive ends the match as
        :attr:`TerminationReason.ALL_AGENTS_DEAD`; exactly one alive ends it
        as :attr:`TerminationReason.LAST_AGENT_STANDING`; otherwise reaching
        the configured tick limit ends it as
        :attr:`TerminationReason.TICK_LIMIT`. Alive-count-based conditions
        take precedence over the tick limit -- a match that reaches the
        limit with zero or one entrant alive is reported as
        ``ALL_AGENTS_DEAD``/``LAST_AGENT_STANDING``, never ``TICK_LIMIT``.

        This is the whole of Ruleset-v1's termination semantic: it takes no
        runtime-kind, entrant-state, or lifecycle information beyond these
        three integers, and is called both mid-match (to decide whether a
        runtime should keep ticking, using only ``.terminated``) and once a
        match has already stopped (to obtain the final ``.reason``) -- see
        ``docs/V1_5_PHASE4_TERMINATION_POLICY.md`` for exactly where each
        runtime calls this.
        """

        if alive_count == 0:
            return TerminationDecision(True, TerminationReason.ALL_AGENTS_DEAD)
        if alive_count == 1:
            return TerminationDecision(True, TerminationReason.LAST_AGENT_STANDING)
        if tick >= max_ticks:
            return TerminationDecision(True, TerminationReason.TICK_LIMIT)
        return TerminationDecision(False, None)


# The frozen Ruleset. ``ruleset_id`` is exactly ``BYTEFRAY_RULESET_ID`` --
# this module never mints its own identity for it.
RULESET_V1 = RulesetPolicy(ruleset_id=BYTEFRAY_RULESET_ID)


# v2.0.0-alpha.1's experimental identity (see
# docs/V2_0_ALPHA_ARCHITECTURE.md Sec 6/7). Spelled ``-alpha1``, never a
# bare ``bytefray-rules-2``: the mechanic's exact shape is a hypothesis
# under test, not a matured contract, and this module must never let an
# unproven experimental guess masquerade as a durable compatibility
# promise (docs/RULES.md's bump policy).
#
# Scheduling and termination are *identical* to Ruleset v1 -- neither
# ``run_scheduler`` nor ``resolve_termination`` reads ``self.ruleset_id``,
# so this is a second, distinctly-identified ``RulesetPolicy`` instance
# reusing the exact same shared implementation, not a subclass or a copy.
# The vulnerable-core mechanic itself lives entirely in
# ``battle_engine.python_runtime`` (Python-only, gated on this exact
# ``ruleset_id`` value) -- this policy object carries no knowledge of it.
BYTEFRAY_RULESET_V2_ALPHA1_ID = "bytefray-rules-2-alpha1"
RULESET_V2_ALPHA1 = RulesetPolicy(ruleset_id=BYTEFRAY_RULESET_V2_ALPHA1_ID)


# v2.0.0-alpha.11's experimental identity (see
# docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md). Adds *Consistent
# Core Observability* on top of alpha.1's Vulnerable Core: a core cell owned
# by its own living entrant is never blank, so a core has a rules-defined,
# ordinary-``READ``-visible footprint whether or not its owner ever chooses
# to defend it (alpha.10 Sec 37 found the opposite -- defending was what made
# a core detectable, which is the wrong incentive).
#
# A *separate* identity, not a mutation of ``bytefray-rules-2-alpha1``:
# alpha.1--alpha.10 matches using the same agents, seed, and placement can
# behave differently under this rule, so reusing the alpha1 identity would
# silently reinterpret ten alphas' worth of persisted artifacts. alpha1
# stays executable with byte-identical historical semantics.
#
# Scheduling and termination are again *identical* to Ruleset v1 -- neither
# ``run_scheduler`` nor ``resolve_termination`` reads ``self.ruleset_id``.
# The observability mechanic itself lives entirely in
# ``battle_engine.python_runtime`` (Python-only, gated on this exact
# ``ruleset_id`` value); this policy object carries no knowledge of it.
BYTEFRAY_RULESET_V2_ALPHA11_ID = "bytefray-rules-2-alpha11"
RULESET_V2_ALPHA11 = RulesetPolicy(ruleset_id=BYTEFRAY_RULESET_V2_ALPHA11_ID)


# v2.0.0-beta1's permanent identity (see docs/V2_0_BETA1_PLAN.md and
# docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md Sec 25-26). The alpha
# program validated "Vulnerable Core" plus "Consistent Core Observability"
# as a beta-ready candidate under the experimental identity
# ``bytefray-rules-2-alpha11``; beta1 promotes that evidence-backed
# semantic into a real, permanent compatibility identity.
#
# Deliberately its own explicit key, never an alias of
# ``bytefray-rules-2-alpha11``: ``rules._RULESET_ALIASES`` gets no entry for
# it, and this table does not collapse the two together. Historical alpha11
# artifacts must remain distinctly, honestly identified as alpha11 --
# reusing that identity here would silently reinterpret ten alphas' worth of
# experimental evidence as a permanent product contract, and would let a
# future evaluation accidentally align an experimental run against a
# permanent one under one canonical match identity. The two share their
# behavioral implementation in ``battle_engine.python_runtime`` (the
# semantics are intentionally identical at promotion time -- see the beta1
# promotion-equivalence corpus, ``engine/tests/test_ruleset_v2_promotion_equivalence.py``)
# but are registered, dispatched, and persisted as separate identities.
#
# Scheduling and termination are again *identical* to Ruleset v1 -- neither
# ``run_scheduler`` nor ``resolve_termination`` reads ``self.ruleset_id``.
#
# Beta1 Phase 2 gives this identity -- and only this identity -- a runtime-
# kind restriction: ``supported_runtime_kinds={"python"}``. Permanent
# Ruleset-v2 gameplay depends on Python-runtime Vulnerable Core semantics
# that have no VM implementation; unlike ``bytefray-rules-2-alpha1``/
# ``-alpha11`` (which keep dispatching successfully but inertly on a VM
# entrant, their exact pre-existing historical behavior, deliberately
# preserved), a VM entrant requested under this permanent identity is
# rejected by ``NativeMatchService`` before any entrant executes -- see
# ``docs/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md``. This is an execution
# compatibility boundary, not a gameplay change: the frozen semantics this
# policy's ``run_scheduler``/``resolve_termination`` expose are untouched.
BYTEFRAY_RULESET_V2_ID = "bytefray-rules-2"
RULESET_V2 = RulesetPolicy(
    ruleset_id=BYTEFRAY_RULESET_V2_ID, supported_runtime_kinds=frozenset({"python"})
)


# v3 research Phase 2's experimental bounded-locality identity (see
# docs/V3_PHASE2_LOCALITY_FEASIBILITY.md). Spelled ``-alpha1``, exactly
# like ``bytefray-rules-2-alpha1``/``-alpha11`` before it and for the same
# reason: the mechanic is a hypothesis under test, not a matured contract.
# This is deliberately NOT ``bytefray-rules-3`` -- no stable Ruleset 3
# exists, and this module must never let a research prototype masquerade
# as a durable compatibility promise (docs/RULES.md's bump policy).
#
# Gameplay under this identity is Ruleset v2's -- vulnerable core,
# observable core beacon, identical scheduling and termination -- plus one
# experimental change: a Python entrant occupies a single *execution
# locus* in the arena and may only read/write within a bounded reach of
# it, moving that locus with an action like any other. The mechanic itself
# lives entirely in ``battle_engine.python_runtime`` (Python-only, gated
# on this exact ``ruleset_id`` value); this policy object carries no
# knowledge of it, exactly as it carries none of the vulnerable-core rule.
#
# Python-only (``supported_runtime_kinds={"python"}``), mirroring
# ``bytefray-rules-2``: locality has no VM/Redcode implementation and is
# not being given one -- see the Phase 2 report's Python-only scope
# statement. A VM entrant requested under this identity is rejected by
# ``NativeMatchService`` before any entrant executes.
BYTEFRAY_RULESET_V3_ALPHA1_ID = "bytefray-rules-3-alpha1"
RULESET_V3_ALPHA1 = RulesetPolicy(
    ruleset_id=BYTEFRAY_RULESET_V3_ALPHA1_ID,
    supported_runtime_kinds=frozenset({"python"}),
)


# v4 research: experimental fine-grained interleaved scheduling identity.
# Evaluates round-robin interleaved execution against block-sequential execution
# under identical Ruleset v2 core/observable semantics.
BYTEFRAY_RULESET_V4_ALPHA1_ID = "bytefray-rules-4-alpha1"
RULESET_V4_ALPHA1 = RulesetPolicy(
    ruleset_id=BYTEFRAY_RULESET_V4_ALPHA1_ID,
    supported_runtime_kinds=frozenset({"python"}),
    scheduler_mode="interleaved",
)


class UnknownRulesetError(LookupError):
    """A Ruleset ID has no known policy.

    Raised by :func:`resolve_ruleset_policy` for any ID not present in
    :data:`_RULESET_POLICIES`. Deliberately fails closed: an unrecognized
    Ruleset ID -- including a plausible-looking but unregistered future
    identity -- must never silently resolve to Ruleset v1.
    """

    def __init__(self, ruleset_id: str):
        super().__init__(f"Unknown Ruleset ID: {ruleset_id!r}")
        self.ruleset_id = ruleset_id


# A finite, explicit table -- not a naming-convention check -- for the same
# reason ``rules._RULESET_ALIASES`` is finite (see that module's docstring).
# This table is deliberately *not* the same table: it governs which Ruleset
# ID a runtime may currently *execute* under, which is a different question
# from which ID a persisted artifact may be *attributed* to. A historical
# artifact identity alias is not evidence that runtime dispatch should
# execute the aliased ID as today's Ruleset v1 -- see
# ``docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md``'s "Resolver design".
#
# ``bytefray-rules-2-alpha1``, ``bytefray-rules-2-alpha11``,
# ``bytefray-rules-2``, and ``bytefray-rules-3-alpha1`` are each registered
# under their own explicit key, never aliased to or from
# ``bytefray-rules-1`` or each other (``rules.py``'s
# ``_RULESET_ALIASES`` gets no entry for any of them either -- see that
# table's own docstring).
_RULESET_POLICIES: Mapping[str, RulesetPolicy] = {
    RULESET_V1.ruleset_id: RULESET_V1,
    RULESET_V2_ALPHA1.ruleset_id: RULESET_V2_ALPHA1,
    RULESET_V2_ALPHA11.ruleset_id: RULESET_V2_ALPHA11,
    RULESET_V2.ruleset_id: RULESET_V2,
    RULESET_V3_ALPHA1.ruleset_id: RULESET_V3_ALPHA1,
    RULESET_V4_ALPHA1.ruleset_id: RULESET_V4_ALPHA1,
}



def resolve_ruleset_policy(ruleset_id: str) -> RulesetPolicy:
    """Return the executable policy for ``ruleset_id``, or fail closed.

    Only the exact, explicitly registered identities in
    :data:`_RULESET_POLICIES` resolve. Historical aliases, prefix matches,
    and "latest Ruleset" fallbacks are all deliberately unsupported here --
    an unrecognized ``ruleset_id`` raises :class:`UnknownRulesetError`
    rather than executing as Ruleset v1 or any other registered identity.
    """

    try:
        return _RULESET_POLICIES[ruleset_id]
    except KeyError:
        raise UnknownRulesetError(ruleset_id) from None


# Which entrant runtime kinds :func:`resolve_omitted_ruleset_id` treats as
# "Python-only". A closed, explicit set -- not "everything except vm" --
# matching this module's own preference for finite tables over open-ended
# checks (see ``_RULESET_POLICIES``'s docstring).
_PYTHON_ONLY_KINDS: frozenset[str] = frozenset({"python"})


def resolve_omitted_ruleset_id(
    requested_ruleset_id: str | None, runtime_kinds: Iterable[str]
) -> str:
    """Resolve one product-facing CLI/API entry point's optional ``--ruleset``.

    This is the RC1 default-Ruleset-defect fix: the seam a user-facing
    caller (``bytefray run``, ``bytefray agents test``, ``bytefray agents
    evaluate``, ``bytefray tournament``) calls, with the entrant runtime
    kinds it already knows for *this* request, to turn a caller's omitted
    ``--ruleset`` into the same current-gameplay identity Agent Designer has
    used since v3.0.0-alpha2 (see ``app/services/ruleset_options.py``),
    instead of the historical Ruleset-v1 identity every native execution
    path fell back to before this fix.

    ``requested_ruleset_id`` is ``None`` for "the caller omitted --ruleset"
    and any other value for "the caller explicitly selected this Ruleset".
    An explicit selection is always returned unchanged -- this function
    never validates, corrects, or overrides one, including a selection that
    a downstream runtime-compatibility check (
    :meth:`RulesetPolicy.unsupported_runtime_kinds`, raised as
    ``RulesetRuntimeUnsupportedError``) will go on to reject as
    incompatible with ``runtime_kinds``. Only an omitted Ruleset is ever
    resolved here.

    ``runtime_kinds`` is the resolved entrant ``kind`` set for this
    specific request (``MatchEntrant.kind`` values: ``"python"``/``"vm"``,
    or an evaluation/tournament roster's equivalent). An omitted Ruleset
    resolves to :data:`BYTEFRAY_RULESET_V2_ID` exactly when every requested
    entrant is Python (a non-empty subset of :data:`_PYTHON_ONLY_KINDS`);
    every other case -- VM-only, mixed Python/VM, or an empty/unknown kind
    set -- resolves to the frozen :data:`~battle_engine.rules.
    BYTEFRAY_RULESET_ID` (Ruleset v1), exactly the historical omitted
    default. A mixed Python/VM roster therefore still resolves to Ruleset
    v1 here (v1 imposes no runtime-kind restriction, so it always executes
    a mixed roster); this function never itself raises for an incompatible
    composition -- that stays ``NativeMatchService``'s job, unchanged, and
    is only reachable from an *explicit* incompatible selection, never from
    an omitted one.

    Callers that construct their own ``MatchRequest``/``EvaluationRequest``/
    ``TournamentRequest`` directly (existing tests, research tools in
    ``tools/``, and any other library caller that never goes through one of
    the product CLIs above) are completely unaffected: none of those types'
    own ``ruleset_id: str | None = None`` defaults change meaning by this
    function existing. Only a CLI entry point that explicitly calls this
    function, and then threads its return value into the request it
    constructs, sees the new omitted-Ruleset behavior -- see each CLI
    module's own ``main()`` for where that happens.
    """

    if requested_ruleset_id is not None:
        return requested_ruleset_id
    kinds = frozenset(runtime_kinds)
    if kinds and kinds <= _PYTHON_ONLY_KINDS:
        return BYTEFRAY_RULESET_V2_ID
    return BYTEFRAY_RULESET_ID


__all__ = [
    "BYTEFRAY_RULESET_V2_ALPHA1_ID",
    "BYTEFRAY_RULESET_V2_ALPHA11_ID",
    "BYTEFRAY_RULESET_V2_ID",
    "BYTEFRAY_RULESET_V3_ALPHA1_ID",
    "BYTEFRAY_RULESET_V4_ALPHA1_ID",
    "RULESET_V1",
    "RULESET_V2",
    "RULESET_V2_ALPHA1",
    "RULESET_V2_ALPHA11",
    "RULESET_V3_ALPHA1",
    "RULESET_V4_ALPHA1",
    "RulesetPolicy",
    "TerminationDecision",
    "TerminationReason",
    "UnknownRulesetError",
    "resolve_omitted_ruleset_id",
    "resolve_ruleset_policy",
]

