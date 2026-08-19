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
from battle_engine.scheduler import StateT, run_sequential_quota


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
    runtime code actually routes through it (scheduling and the
    termination decision/reason). It has no knowledge of
    ``"vm"``/``"python"`` runtime selection, persistence, replay/result
    schemas, or evaluation; those remain the concern of the callers that
    hold a ``RulesetPolicy``, not of the policy itself.
    """

    ruleset_id: str

    def run_scheduler(
        self,
        states: Iterable[StateT],
        quota: int,
        execute_slot: Callable[[StateT, int], None],
    ) -> None:
        """Run this Ruleset's sequential-quota entrant scheduler.

        Ruleset v1 has exactly one scheduling rule
        (:func:`battle_engine.scheduler.run_sequential_quota`); this method
        is the seam through which VM, unsupervised Python, and supervised
        Python execution obtain it, in place of importing the scheduler
        module directly.
        """

        run_sequential_quota(states, quota, execute_slot)

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


class UnknownRulesetError(LookupError):
    """A Ruleset ID has no known policy.

    Raised by :func:`resolve_ruleset_policy` for any ID other than the
    current ``BYTEFRAY_RULESET_ID``. Deliberately fails closed: an
    unrecognized Ruleset ID -- including a plausible-looking future ID such
    as ``"bytefray-rules-2"`` -- must never silently resolve to Ruleset v1.
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
# ``bytefray-rules-2-alpha1`` is registered under its own explicit key,
# never aliased to or from ``bytefray-rules-1`` (``rules.py``'s
# ``_RULESET_ALIASES`` gets no entry for it either -- see that table's own
# docstring).
_RULESET_POLICIES: Mapping[str, RulesetPolicy] = {
    RULESET_V1.ruleset_id: RULESET_V1,
    RULESET_V2_ALPHA1.ruleset_id: RULESET_V2_ALPHA1,
}


def resolve_ruleset_policy(ruleset_id: str) -> RulesetPolicy:
    """Return the executable policy for ``ruleset_id``, or fail closed.

    Only the exact current ``BYTEFRAY_RULESET_ID`` resolves. Historical
    aliases, prefix matches, and "latest Ruleset" fallbacks are all
    deliberately unsupported here -- an unrecognized ``ruleset_id`` raises
    :class:`UnknownRulesetError` rather than executing as Ruleset v1.
    """

    try:
        return _RULESET_POLICIES[ruleset_id]
    except KeyError:
        raise UnknownRulesetError(ruleset_id) from None


__all__ = [
    "BYTEFRAY_RULESET_V2_ALPHA1_ID",
    "RULESET_V1",
    "RULESET_V2_ALPHA1",
    "RulesetPolicy",
    "TerminationDecision",
    "TerminationReason",
    "UnknownRulesetError",
    "resolve_ruleset_policy",
]
