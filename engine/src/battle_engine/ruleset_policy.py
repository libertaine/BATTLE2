"""Executable Ruleset policy and fail-closed resolver.

``rules.py`` is the frozen, dependency-free record of Ruleset *identity*
(``BYTEFRAY_RULESET_ID`` and its historical-alias/provenance vocabulary),
deliberately kept free of anything executable so it can sit underneath the
runtime, artifact, and evaluation layers without risk of an import cycle
(see its own module docstring). This module is the next layer up: it pairs
that identity with the one piece of *executable* Ruleset-v1 semantics that
has, as of v1.5 Phase 2, a single shared implementation -- entrant
scheduling (``battle_engine.scheduler.run_sequential_quota``) -- and
provides one fail-closed resolver from a Ruleset ID string to its policy.

This is deliberately a thin seam, not a Ruleset framework. Exactly one
Ruleset exists (Ruleset v1); the resolver exists so runtime construction
has one obvious place to obtain Ruleset-owned scheduling semantics instead
of importing the scheduler directly, and so an unrecognized Ruleset ID
fails before any gameplay executes rather than silently running as v1.
Scoring, statistics, termination, and winner resolution are not yet
Ruleset-policy-owned -- see ``docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md``
for what remains outside this seam and why.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.scheduler import StateT, run_sequential_quota


@dataclass(frozen=True)
class RulesetPolicy:
    """One Ruleset's executable policy: identity plus its entrant scheduler.

    Immutable and intentionally narrow -- it exposes only what current
    runtime code actually routes through it (scheduling). It has no
    knowledge of ``"vm"``/``"python"`` runtime selection, persistence,
    replay/result schemas, or evaluation; those remain the concern of the
    callers that hold a ``RulesetPolicy``, not of the policy itself.
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


# The one Ruleset that exists. ``ruleset_id`` is exactly the frozen
# ``BYTEFRAY_RULESET_ID`` -- this module never mints its own identity.
RULESET_V1 = RulesetPolicy(ruleset_id=BYTEFRAY_RULESET_ID)


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
_RULESET_POLICIES: Mapping[str, RulesetPolicy] = {RULESET_V1.ruleset_id: RULESET_V1}


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
    "RULESET_V1",
    "RulesetPolicy",
    "UnknownRulesetError",
    "resolve_ruleset_policy",
]
