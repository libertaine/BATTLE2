"""v2.0.0-alpha experimental reference agents (Core Defender, Core Seeker,
Reactive Core Defender, Core Tracker).

Loaded directly from bundled package resources under
``battle_engine/data/reference_agents/<name>/`` -- the same
manifest-plus-``agent.py`` shape every starter agent uses, and the same
"loaded from a resource, never copied into the user's writable ``agents/``
catalog and never discoverable via ``resolve_agent``/``discover_agents``"
pattern ``agent_test._reference_opponent_spec`` already established for the
internal ``reference`` opponent (see that function's own docstring).

Deliberately kept out of ``battle_engine.starters.STARTER_AGENT_NAMES``:
these agents exist to exercise Vulnerable-Core-family Rulesets
(``bytefray-rules-2-alpha1``, ``bytefray-rules-2-alpha11``, and, as of
v2.0.0-beta1, the permanent ``bytefray-rules-2`` -- see
``docs/V2_0_ALPHA_ARCHITECTURE.md`` and ``docs/V2_0_BETA1_PLAN.md``), not to
join Bytefray's permanent default roster shown to every ``bytefray agents
create``/Designer user regardless of which Ruleset they run.
``reactive_core_defender`` (added for alpha.2,
docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md) is a distinct agent alongside the
original ``core_defender``, not a replacement for it, so the two remain
directly comparable in the same evaluation matrix. ``core_tracker`` (added
for alpha.8, docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md) is likewise a
distinct, additive sibling of the original ``core_seeker`` -- a
placement-agnostic offense benchmark, not a mutation of the
historical-control attacker, so both stay directly comparable in the same
evaluation matrix.

Beta1 role (docs/V2_0_BETA1_PLAN.md): ``core_tracker`` is Ruleset-v2's
reference *offense benchmark*, not a claim of canonical optimal attack
strategy. ``claimer``, ``hunter``, ``core_defender``, and
``reactive_core_defender`` remain important regression/reference
strategies. The historical ``core_seeker`` remains a characterization
fixture (its fixed, placement-dependent scan schedule is the documented
subject of docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md/
docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md, not a benchmark to keep
improving) and is retained, not removed.
"""

from __future__ import annotations

from pathlib import Path

from battle_engine.agents import AgentSpec
from battle_engine.paths import get_resource_root

REFERENCE_AGENT_NAMES = ("core_defender", "core_seeker", "reactive_core_defender", "core_tracker")


def _reference_agents_resource_dir(resource_root: Path) -> Path:
    candidates = (
        resource_root / "battle_engine" / "data" / "reference_agents",
        resource_root / "engine" / "src" / "battle_engine" / "data" / "reference_agents",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        f"v2.0.0-alpha.1 reference-agent resource directory not found. Checked: {checked}"
    )


def reference_agent_spec(name: str, resource_root: Path | None = None) -> AgentSpec:
    """Build an :class:`~battle_engine.agents.AgentSpec` for one bundled
    v2.0.0-alpha reference agent (one of ``REFERENCE_AGENT_NAMES``), loaded
    directly from its packaged resource directory exactly like
    ``agent_test._reference_opponent_spec`` builds the internal
    ``reference`` opponent's spec.
    """

    if name not in REFERENCE_AGENT_NAMES:
        raise ValueError(
            f"Unknown v2.0.0-alpha.1 reference agent {name!r}; expected one of "
            f"{REFERENCE_AGENT_NAMES!r}."
        )
    agents_dir = _reference_agents_resource_dir(resource_root or get_resource_root())
    agent_dir = agents_dir / name
    return AgentSpec(
        name=name,
        display=name.replace("_", " ").title(),
        dir=agent_dir,
        blob=None,
        defaults={},
        kind="python",
        api_version=1,
        version="0.1.0",
        source_path=(agent_dir / "agent.py").resolve(),
        entry_point="agent.py:create_agent",
        manifest={
            "kind": "python",
            "api_version": 1,
            "entrypoint": "agent.py:create_agent",
            "version": "0.1.0",
        },
    )


__all__ = ["REFERENCE_AGENT_NAMES", "reference_agent_spec"]
