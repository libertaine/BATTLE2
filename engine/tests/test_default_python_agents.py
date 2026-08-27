"""Coverage for the bundled default Python (Agent API v1) starter agents.

Claimer, Strider, Hunter, Wanderer, and Adaptive (v0.6.1) plus Raider and
Sentinel (v3.0.0-alpha2) are shipped as starter agents
(``battle_engine.starters.STARTER_AGENT_NAMES``) alongside the existing
native VM starters. This module checks the structural properties every
shipped agent is required to have -- clean discovery, successful
validation, and successful match completion against a variety of
opponents and seeds -- without asserting any particular agent always wins
a particular seed (see AGENTS.md: prefer structural correctness over
encoding incidental game outcomes).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import EvaluationRequest, EvaluationService
from battle_engine.agent_test import DevelopmentTestOutcome
from battle_engine.agent_test import test_agent as run_development_test
from battle_engine.agent_validation import ValidationResult, validate_agent
from battle_engine.agents import discover_agents
from battle_engine.benchmarks import load_population
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID
from battle_engine.starters import STARTER_AGENT_NAMES, ensure_starter_agents

DEFAULT_PYTHON_AGENT_NAMES = (
    "claimer",
    "strider",
    "hunter",
    "wanderer",
    "adaptive",
    "raider",
    "sentinel",
)

#: The v3.0.0-alpha2 additions. Deliberately NOT members of the frozen v2
#: benchmark population (``battle_engine/data/benchmarks/v2_baseline.json``)
#: -- they exist to demonstrate the Ruleset-v2 vulnerable-core mechanic,
#: which no expansion-family starter exercises, and staying out of the
#: benchmark is what keeps them freely maintainable.
VULNERABLE_CORE_STARTER_NAMES = ("raider", "sentinel")


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    return tmp_path


def _tested_agent_actions(
    data_root: Path, name: str, *, opponent: str, seed: int, ticks: int
) -> tuple[list[tuple[str, int]], int]:
    """Every ``(kind, address)`` the tested agent chose, plus its spawn ``pc``.

    Read from the development trace the tool itself writes, so these tests
    observe the agent's real decisions under a real Ruleset-v2 match rather
    than re-implementing its logic. The tested agent always occupies slot
    ``A`` (see ``agent_test``), so the opponent's decisions are filtered
    out.

    The spawn ``pc`` from the first recorded decision is the entrant's own
    core anchor -- the same value ``core_defender``/``sentinel``/``raider``
    each capture on their own first ``act()`` call. It must be read here
    rather than inferred from the first action's address: Sentinel's first
    action is an *expand* write at ``core_start + CORE_SIZE``, not a core
    write, so inferring from it would shift the whole core window.
    """

    outcome = run_development_test(
        name,
        opponent=opponent,
        data_root=data_root,
        resource_root=_resource_root(),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seed=seed,
        ticks=ticks,
        trace=True,
    )
    assert isinstance(outcome, DevelopmentTestOutcome)
    assert outcome.trace_path is not None
    actions: list[tuple[str, int]] = []
    spawn_pc: int | None = None
    for line in outcome.trace_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("record_type") != "decision" or record.get("agent_id") != "A":
            continue
        if spawn_pc is None:
            spawn_pc = record["observation"]["pc"]
        action = record["action"]
        actions.append((action["kind"], action["operand"]))
    assert actions, "development trace recorded no decisions for the tested agent"
    assert spawn_pc is not None
    return actions, spawn_pc


def _own_core_write_share(
    data_root: Path, name: str, *, opponent: str, seed: int, ticks: int
) -> tuple[int, int, int]:
    """``(writes inside own core, total writes, reads)`` for one match."""

    actions, spawn_pc = _tested_agent_actions(
        data_root, name, opponent=opponent, seed=seed, ticks=ticks
    )
    arena = 4096  # the shipped default this development test runs under
    core_size = 8  # bytefray-rules-2's fixed CORE_SIZE
    core_start = spawn_pc % arena
    core_writes = total_writes = reads = 0
    for kind, address in actions:
        if kind == "read":
            reads += 1
        elif kind == "write":
            total_writes += 1
            if (address - core_start) % arena < core_size:
                core_writes += 1
    return core_writes, total_writes, reads


def _longest_contiguous_write_run(
    data_root: Path, name: str, *, opponent: str, seed: int, ticks: int
) -> int:
    """The longest run of consecutive ascending-address writes."""

    actions, _spawn_pc = _tested_agent_actions(
        data_root, name, opponent=opponent, seed=seed, ticks=ticks
    )
    arena = 4096
    longest = run = 0
    previous: int | None = None
    for kind, address in actions:
        if kind != "write":
            previous = None
            run = 0
            continue
        if previous is not None and address == (previous + 1) % arena:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        previous = address
    return longest


def test_default_python_agent_names_are_starter_agents() -> None:
    for name in DEFAULT_PYTHON_AGENT_NAMES:
        assert name in STARTER_AGENT_NAMES


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_discovers_as_python_kind_with_v1_entrypoint(data_root: Path, name: str) -> None:
    specs = discover_agents(data_root)
    spec = specs[name]
    assert spec.kind == "python"
    assert spec.api_version == 1
    assert spec.entry_point == "agent.py:create_agent"
    assert spec.source_path is not None and spec.source_path.is_file()


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_validates_cleanly(data_root: Path, name: str) -> None:
    result = validate_agent(name, data_root=data_root)
    assert isinstance(result, ValidationResult)
    assert result.agent_id == name
    assert result.api_version == 1


@pytest.mark.parametrize("name", DEFAULT_PYTHON_AGENT_NAMES)
def test_completes_a_development_match_against_the_reference_opponent(
    data_root: Path, name: str
) -> None:
    outcome = run_development_test(
        name,
        data_root=data_root,
        resource_root=_resource_root(),
        seed=1337,
        ticks=60,
        trace=False,
    )
    assert isinstance(outcome, DevelopmentTestOutcome)
    match_result = outcome.match_result
    assert match_result.ticks_run == 60
    tested_agent = match_result.agents_by_id["A"]
    assert tested_agent.diagnostic is None, (
        f"{name} recorded a forfeit diagnostic against the reference opponent: "
        f"{tested_agent.diagnostic}"
    )


@pytest.mark.parametrize("subject", DEFAULT_PYTHON_AGENT_NAMES)
def test_completes_matches_against_every_other_default_agent(
    data_root: Path, subject: str
) -> None:
    """Behavioral smoke: each agent plays every sibling default agent across
    a few seeds and every cell must complete -- no infrastructure failures,
    no initialization failures, no unhandled exceptions. Outcomes
    themselves (win/loss/tie) are intentionally not asserted."""

    opponents = [name for name in DEFAULT_PYTHON_AGENT_NAMES if name != subject]
    request = EvaluationRequest(
        candidate_id=subject,
        baseline_id=None,
        opponent_ids=tuple(opponents),
        seeds=(1, 2, 3),
        ticks=60,
        output_dir=data_root / "runs" / "agents_evaluate" / subject,
        data_root=data_root,
    )
    result = EvaluationService().run(request)
    for cell in result.cells:
        assert cell.status == "completed", (
            f"{subject} vs {cell.opponent_id} seed={cell.seed} did not complete: "
            f"status={cell.status} error={cell.error_code}:{cell.error_message}"
        )
        assert cell.outcome in ("win", "loss", "tie")


# ---------------------------------------------------------------------------
# v3.0.0-alpha2 vulnerable-core starters (raider, sentinel)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", VULNERABLE_CORE_STARTER_NAMES)
def test_vulnerable_core_starters_are_not_frozen_benchmark_members(name: str) -> None:
    """They must stay maintainable, so they must never acquire a pin.

    Every member of the v2 baseline is content-addressed by whole-directory
    fingerprint, so a pinned agent cannot have so much as a docstring typo
    corrected without invalidating the v3 research program's own baseline.
    Raider and Sentinel are deliberately outside that set.
    """

    population = load_population()
    assert name not in {member.agent_id for member in population.members}


@pytest.mark.parametrize("name", VULNERABLE_CORE_STARTER_NAMES)
def test_vulnerable_core_starters_run_under_ruleset_v2(data_root: Path, name: str) -> None:
    """Ruleset v2 is the gameplay these two exist to demonstrate."""

    outcome = run_development_test(
        name,
        opponent="claimer",
        data_root=data_root,
        resource_root=_resource_root(),
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        seed=1,
        ticks=120,
        trace=False,
    )
    assert isinstance(outcome, DevelopmentTestOutcome)
    assert outcome.ruleset_id == BYTEFRAY_RULESET_V2_ID
    assert outcome.match_result.agents_by_id["A"].diagnostic is None


def test_starter_signature_bytes_are_unique() -> None:
    """No two bundled Python starters may claim with the same byte.

    Two agents sharing a signature cannot tell each other's cells apart --
    every read-before-write starter would mistake the other's ground for
    its own, and Raider would never treat a same-signature core as foreign.
    """

    resource_dir = (
        _resource_root() / "engine" / "src" / "battle_engine" / "data" / "starter_agents"
    )
    signatures: dict[int, str] = {}
    for name in DEFAULT_PYTHON_AGENT_NAMES:
        source = (resource_dir / name / "agent.py").read_text(encoding="utf-8")
        found = re.findall(r"self\.signature = (0x[0-9A-Fa-f]+)", source)
        assert len(found) == 1, f"{name} must declare exactly one signature byte, found {found}"
        value = int(found[0], 16)
        assert value not in signatures, (
            f"{name} reuses signature {found[0]} already used by {signatures[value]}"
        )
        signatures[value] = name


@pytest.mark.parametrize(
    ("name", "display"),
    (("raider", "Raider (Starter)"), ("sentinel", "Sentinel (Starter)")),
)
def test_vulnerable_core_starters_have_product_identities(
    data_root: Path, name: str, display: str
) -> None:
    """Their own identity, never the reference agent's they were derived from."""

    spec = discover_agents(data_root)[name]
    assert spec.name == name
    assert spec.display == display
    source = spec.source_path.read_text(encoding="utf-8")
    # The provenance note must be present, and must not claim to *be* the
    # frozen artifact.
    assert "independently maintained" in source
    for ancestor in ("core_tracker", "core_defender"):
        assert f"class {ancestor.title().replace('_', '')}Agent" not in source


def test_sentinel_spends_a_quarter_of_its_actions_on_its_own_core(data_root: Path) -> None:
    """The lesson Sentinel exists to teach, asserted as a real behavior.

    Deliberately a wide band (15-35%) around the 25% ``REFRESH_EVERY = 4``
    implies: this pins the *strategy* (a meaningful, non-trivial share of
    budget goes to core maintenance) without encoding an exact tuning value
    a future revision might legitimately change.
    """

    core_writes, total_writes, reads = _own_core_write_share(
        data_root, "sentinel", opponent="claimer", seed=1, ticks=200
    )
    assert total_writes > 0
    share = core_writes / total_writes
    assert 0.15 <= share <= 0.35, f"sentinel own-core write share was {share:.3f}"
    assert reads == 0, "sentinel is a blind timer by design and must issue no READs"


def test_raider_searches_with_reads_and_commits_contiguous_bursts(data_root: Path) -> None:
    """The lesson Raider exists to teach, asserted as a real behavior.

    A pure expansion agent issues no ``READ``s and never writes a long
    contiguous run; Raider must do both -- searching costs budget, and a
    confirmed target gets a deliberate burst rather than a single write.
    """

    _core_writes, total_writes, reads = _own_core_write_share(
        data_root, "raider", opponent="claimer", seed=1, ticks=200
    )
    assert reads > 0, "raider must spend budget searching"
    assert total_writes > 0
    longest = _longest_contiguous_write_run(
        data_root, "raider", opponent="claimer", seed=1, ticks=200
    )
    assert longest >= 8, f"raider's longest contiguous write run was {longest}"
