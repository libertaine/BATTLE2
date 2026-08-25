"""v3 Phase 0C/0I: frozen benchmark population, preset composition, comparability.

Phase 0's benchmark population must mean one fixed set of immutable agent
revisions forever (docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 3). These tests
defend that pin, the preset plumbing that lets a research corpus carry its
own conditions, and the comparability rule that keeps two differently
conditioned evaluations from being presented as cleanly comparable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_V2_ID,
    EvaluationRequest,
    EvaluationService,
)
from battle_engine.benchmarks import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    V2_BASELINE_ID,
    BenchmarkPopulationError,
    load_population,
    stage_population,
    verify_population,
)
from battle_engine.evaluation_history.comparison import align
from battle_engine.evaluation_history.discovery import adapt_any
from battle_engine.evaluation_presets import EvaluationPresetError, load_preset_file

# ---------------------------------------------------------------------------
# Frozen benchmark population (Phase 0C)
# ---------------------------------------------------------------------------


def test_v2_baseline_population_loads_with_the_expected_shape() -> None:
    population = load_population()
    assert population.benchmark_id == V2_BASELINE_ID
    assert population.ruleset_id == BYTEFRAY_RULESET_V2_ID
    # Five Python starters plus four v2 reference agents -- the nine
    # in-tree Python agents the architecture review counted.
    assert len(population.members) == 9
    assert set(population.agent_ids) == {
        "adaptive",
        "claimer",
        "hunter",
        "strider",
        "wanderer",
        "core_defender",
        "core_seeker",
        "core_tracker",
        "reactive_core_defender",
    }


def test_every_member_is_pinned_by_content_addressed_revision_identity() -> None:
    population = load_population()
    for member in population.members:
        assert member.agent_revision_id.startswith("agent-revision_")
        assert len(member.source_sha256) == 64
        assert member.runtime_kind == "python"
        assert member.agent_api_version == 1
        assert member.strategic_role
    # Every pin is distinct: no two members share a revision identity.
    assert len({member.agent_revision_id for member in population.members}) == 9


def test_population_still_matches_the_live_tree() -> None:
    """The pin is only useful if a drift is actually detectable.

    A failure here means an in-tree agent's source changed after Phase 0
    froze it -- which is a real finding about the baseline's validity, not
    a test to update casually. See docs/V3_PHASE0_RESEARCH_BASELINE.md
    Sec 3 before repinning.
    """

    population = load_population()
    failures = [check for check in verify_population(population) if not check.matches]
    assert not failures, "; ".join(f"{c.agent_id}: {c.detail}" for c in failures)


def test_ecology_core_is_the_beta2_phase4_six() -> None:
    """The Beta2 Phase 4 Sec 17 rubric was scored on exactly these six."""

    population = load_population()
    assert population.ecology_core == (
        "claimer",
        "hunter",
        "core_defender",
        "reactive_core_defender",
        "core_tracker",
        "core_seeker",
    )
    assert len(population.ecology_core_members()) == 6


def test_unknown_population_id_is_rejected() -> None:
    with pytest.raises(BenchmarkPopulationError, match="Unknown benchmark population"):
        load_population("no-such-population")


def test_manifest_declares_its_schema() -> None:
    population = load_population()
    assert SCHEMA_NAME == "bytefray.benchmark_population"
    assert SCHEMA_VERSION == 1
    assert population.frozen_at_commit


def test_staging_copies_exactly_the_pinned_files(tmp_path: Path) -> None:
    population = load_population()
    staged = stage_population(population, tmp_path, agent_ids=("claimer", "core_tracker"))
    assert len(staged) == 4  # two agents x (agent.py + agent.yaml)
    for agent_id in ("claimer", "core_tracker"):
        assert (tmp_path / "agents" / agent_id / "agent.py").is_file()
        assert (tmp_path / "agents" / agent_id / "agent.yaml").is_file()


def test_staged_population_is_discoverable_by_evaluation(tmp_path: Path) -> None:
    """Staging is what makes the frozen population actually runnable."""

    population = load_population()
    stage_population(population, tmp_path, agent_ids=("claimer", "core_tracker"))
    specs, evaluation_id = EvaluationService().preflight(
        candidate_id="claimer",
        opponent_ids=("core_tracker",),
        seeds=(1,),
        ticks=10,
        data_root=tmp_path,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
    )
    assert set(specs) == {"claimer", "core_tracker"}
    assert evaluation_id.startswith("evaluation-v2_")


# ---------------------------------------------------------------------------
# Preset composition and precedence (Phase 0I)
# ---------------------------------------------------------------------------


def _write_preset(path: Path, **fields) -> Path:
    payload = {"schema": "bytefray.evaluation_preset", "schema_version": 1}
    payload.update(fields)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_preset_carries_the_experimental_conditions(tmp_path: Path) -> None:
    path = _write_preset(
        tmp_path / "corpus.yaml",
        candidate="claimer",
        opponents=["core_tracker"],
        ticks=200,
        arena_size=1024,
        instr_per_tick=4,
    )
    preset = load_preset_file(path)
    assert preset.ticks == 200
    assert preset.arena_size == 1024
    assert preset.instr_per_tick == 4


def test_preset_omitting_conditions_leaves_them_unset(tmp_path: Path) -> None:
    """`None` must mean "not set by this preset", never a materialized default --
    otherwise a preset would silently pin conditions it never mentioned."""

    path = _write_preset(tmp_path / "plain.yaml", candidate="claimer", opponents=["hunter"])
    preset = load_preset_file(path)
    assert preset.arena_size is None
    assert preset.instr_per_tick is None


def test_preset_rejects_non_positive_conditions(tmp_path: Path) -> None:
    bad_arena = _write_preset(tmp_path / "a.yaml", arena_size=0)
    with pytest.raises(EvaluationPresetError, match="arena_size"):
        load_preset_file(bad_arena)
    bad_budget = _write_preset(tmp_path / "b.yaml", instr_per_tick=-1)
    with pytest.raises(EvaluationPresetError, match="instr_per_tick"):
        load_preset_file(bad_budget)


def test_preset_rejects_wrong_typed_conditions(tmp_path: Path) -> None:
    path = _write_preset(tmp_path / "c.yaml", arena_size="4096")
    with pytest.raises(EvaluationPresetError, match="arena_size"):
        load_preset_file(path)


def test_preset_conditions_round_trip_through_show_json(tmp_path: Path) -> None:
    from battle_engine.evaluation_presets import _preset_to_json

    path = _write_preset(tmp_path / "d.yaml", arena_size=2048, instr_per_tick=16)
    payload = _preset_to_json(load_preset_file(path))
    assert payload["arena_size"] == 2048
    assert payload["instr_per_tick"] == 16


# ---------------------------------------------------------------------------
# Comparability (Phase 0I)
# ---------------------------------------------------------------------------


def _write_python_agent(root: Path, name: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_text(
        """
from battle_engine.agent_api import ActionKind, AgentAction
class Agent:
    def reset(self, context): pass
    def act(self, observation): return AgentAction(ActionKind.NOP)
def create_agent(): return Agent()
""",
        encoding="utf-8",
    )


def _run(tmp_path: Path, name: str, **overrides) -> Path:
    request = EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / name,
        ticks=10,
        data_root=tmp_path,
        both_orientations=False,
        ruleset_id=BYTEFRAY_RULESET_V2_ID,
        **overrides,
    )
    EvaluationService().run(request)
    return request.output_dir / "evaluation.json"


def test_differing_arena_size_is_not_cleanly_comparable(tmp_path: Path) -> None:
    """Two evaluations whose arena differs describe different experiments.

    ``_condition_key`` keys on ``effective_conditions_fingerprint``, which
    already carries arena size -- so a differing arena must produce zero
    strictly-aligned rows and zero directly-comparable cells rather than
    silently aligning as if the two runs were the same experiment.

    The cells then fall through to ``_classify_unmatched``'s existing
    ``(opponent_id, seed)`` grouping, which reports the three same-slot
    placements per side as one *ambiguous duplicate group* rather than
    guessing a pairing. That routing is pre-existing, deliberate behavior
    (see that function's docstring); this test pins the comparability
    outcome, not the classification mechanism.
    """

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left = adapt_any(_run(tmp_path, "big"))
    right = adapt_any(_run(tmp_path, "small", arena_size=1024))

    comparison = align(left, right)
    assert comparison.rows == ()
    assert comparison.denominators.condition_intersection == 0
    assert comparison.denominators.directly_comparable == 0
    # Surfaced as unresolved, never quietly dropped.
    assert (
        comparison.denominators.ambiguous_duplicate_groups
        or comparison.unmatched_left
        or comparison.unmatched_right
    )


def test_identical_conditions_still_align(tmp_path: Path) -> None:
    """The comparability guard must not over-trigger: same conditions, same
    experiment, cells still align."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left = adapt_any(_run(tmp_path, "run-a", arena_size=1024))
    right = adapt_any(_run(tmp_path, "run-b", arena_size=1024))

    comparison = align(left, right)
    assert comparison.rows
    assert not comparison.unmatched_left
    assert not comparison.unmatched_right


def test_explicit_default_arena_aligns_with_an_omitted_one(tmp_path: Path) -> None:
    """Naming the default must not fragment comparability."""

    _write_python_agent(tmp_path, "candidate")
    _write_python_agent(tmp_path, "opponent")
    left = adapt_any(_run(tmp_path, "omitted"))
    right = adapt_any(_run(tmp_path, "explicit", arena_size=4096, instr_per_tick=8))

    comparison = align(left, right)
    assert comparison.rows
    assert not comparison.unmatched_left
