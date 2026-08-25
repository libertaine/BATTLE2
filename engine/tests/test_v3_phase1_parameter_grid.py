"""v3 Phase 1: the committed arena x action-budget parameter grid.

The grid definition
(``battle_engine/data/benchmarks/v3_phase1_arena_action_grid.json``) is the
artifact that makes "rerun the Phase 1 experiment" reproducible from the
repository alone, exactly as ``v2_baseline_corpus.json`` does for the Phase
0 control. These tests defend the properties the Phase 1 report's
conclusions actually rest on:

* every condition is *runnable* -- past the evaluation service's own arena
  lower bound, and a power of two so the experiment studies arena size
  rather than accidentally studying ``wanderer``'s coprime-stride
  assumption (docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 12);
* every roster and pair names a Phase 0 corpus entry, so a Phase 1 cell
  differs from its Phase 0 control cell in arena size and action budget
  and in nothing else;
* the declared constant-density diagonals really are constant-density,
  because separating a density effect from a scale effect is the whole
  design;
* the grid was declared before interpretation and carries a stopping
  criterion (Phase 1P).

No gameplay, Ruleset, Agent API or schema behaviour is exercised here --
there is none to exercise. Phase 1 changed no production semantics.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_V2_ID,
    EvaluationConfigurationError,
    EvaluationService,
    standard_layouts,
    standard_placements,
)
from battle_engine.benchmarks import V2_BASELINE_ID, load_population, stage_population
from battle_engine.config import Config
from battle_engine.paths import get_resource_root
from battle_engine.python_runtime import CORE_SIZE

GRID_FILENAME = "v3_phase1_arena_action_grid.json"
CORPUS_FILENAME = "v2_baseline_corpus.json"


def _benchmarks_dir() -> Path:
    root = get_resource_root()
    for candidate in (
        root / "battle_engine" / "data" / "benchmarks",
        root / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
    ):
        if candidate.is_dir():
            return candidate
    pytest.fail(f"benchmark resource directory not found under {root}")


def _load(filename: str) -> dict[str, Any]:
    return json.loads((_benchmarks_dir() / filename).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grid() -> dict[str, Any]:
    return _load(GRID_FILENAME)


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return _load(CORPUS_FILENAME)


@pytest.fixture(scope="module")
def staged_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A data root holding the frozen population, staged the way the Phase
    1 driver stages it -- ``preflight`` resolves every entrant against a
    data root, so validating the grid needs the same population the grid
    is declared against, not whatever happens to be in the developer's."""

    root = tmp_path_factory.mktemp("v3-phase1-population")
    stage_population(load_population(), root)
    return root


def _conditions(grid: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (stage_name, condition)
        for stage_name, stage in grid["stages"].items()
        for condition in stage["conditions"]
    ]


# ---------------------------------------------------------------------------
# Shape and provenance
# ---------------------------------------------------------------------------


def test_grid_declares_its_schema_population_and_ruleset(grid: dict[str, Any]) -> None:
    assert grid["schema"] == "bytefray.parameter_grid"
    assert grid["schema_version"] == 1
    assert grid["grid_id"] == "v3-phase1-arena-action"
    # The grid varies conditions only; what a roster *is* stays declared
    # exactly once, by the Phase 0 population and corpus.
    assert grid["benchmark_id"] == V2_BASELINE_ID
    assert grid["corpus_id"] == "v2-baseline-corpus"
    assert grid["ruleset_id"] == BYTEFRAY_RULESET_V2_ID


def test_both_stages_are_declared(grid: dict[str, Any]) -> None:
    assert set(grid["stages"]) == {"pilot", "main"}


def test_every_roster_and_pair_names_a_phase0_corpus_entry(
    grid: dict[str, Any], corpus: dict[str, Any]
) -> None:
    roster_ids = {entry["id"] for entry in corpus["group"]["rosters"]}
    pair_ids = {entry["id"] for entry in corpus["pairwise"]["pairs"]}
    for stage_name, stage in grid["stages"].items():
        assert set(stage["rosters"]) <= roster_ids, stage_name
        assert set(stage["pairs"]) <= pair_ids, stage_name


def test_main_stage_uses_every_corpus_roster(
    grid: dict[str, Any], corpus: dict[str, Any]
) -> None:
    """Sec 17 criterion 1 enumerates the leader of each tested roster, so a
    sampled subset could not be scored against the rubric verbatim."""

    roster_ids = [entry["id"] for entry in corpus["group"]["rosters"]]
    assert grid["stages"]["main"]["rosters"] == roster_ids


def test_every_grid_agent_belongs_to_the_frozen_population(
    grid: dict[str, Any], corpus: dict[str, Any]
) -> None:
    population = set(load_population().agent_ids)
    rosters = {entry["id"]: entry for entry in corpus["group"]["rosters"]}
    pairs = {entry["id"]: entry for entry in corpus["pairwise"]["pairs"]}
    for stage in grid["stages"].values():
        for roster_id in stage["rosters"]:
            assert set(rosters[roster_id]["roster"]) <= population
        for pair_id in stage["pairs"]:
            pair = pairs[pair_id]
            assert {pair["candidate"], pair["opponent"]} <= population


# ---------------------------------------------------------------------------
# Every condition is runnable
# ---------------------------------------------------------------------------


def test_condition_ids_are_unique_within_each_stage(grid: dict[str, Any]) -> None:
    for stage_name, stage in grid["stages"].items():
        ids = [condition["id"] for condition in stage["conditions"]]
        assert len(ids) == len(set(ids)), stage_name


def test_condition_ids_encode_their_own_parameters(grid: dict[str, Any]) -> None:
    for _stage, condition in _conditions(grid):
        assert condition["id"] == f"a{condition['arena_size']}_b{condition['instr_per_tick']}"


def test_every_arena_size_is_a_power_of_two(grid: dict[str, Any]) -> None:
    """Phase 0 Sec 12: ``wanderer`` picks an odd stride to stay coprime with
    a power-of-two arena. Keeping every arena a power of two means the
    experiment studies a game parameter, not that implementation
    assumption."""

    for _stage, condition in _conditions(grid):
        arena = condition["arena_size"]
        assert arena > 0 and arena & (arena - 1) == 0, condition["id"]


def test_every_arena_size_clears_the_standard_layout_overlap_bound(
    grid: dict[str, Any], corpus: dict[str, Any]
) -> None:
    rosters = {entry["id"]: entry for entry in corpus["group"]["rosters"]}
    for stage_name, stage in grid["stages"].items():
        widest = max(len(rosters[r]["roster"]) for r in stage["rosters"])
        minimum = 2 * widest * (CORE_SIZE + 1)
        for condition in stage["conditions"]:
            assert condition["arena_size"] >= minimum, (stage_name, condition["id"])


def test_standard_layouts_stay_non_overlapping_at_every_condition(
    grid: dict[str, Any], corpus: dict[str, Any]
) -> None:
    """The bound above is the documented rule; this checks the actual
    derived seat starts, which is what a match really uses."""

    rosters = {entry["id"]: entry for entry in corpus["group"]["rosters"]}
    for stage_name, stage in grid["stages"].items():
        for condition in stage["conditions"]:
            arena = condition["arena_size"]
            for roster_id in stage["rosters"]:
                count = len(rosters[roster_id]["roster"])
                for layout in standard_layouts(count, arena):
                    starts = sorted(start % arena for start in layout.seat_starts)
                    assert len(set(starts)) == count, (stage_name, condition["id"], roster_id)
                    gaps = [
                        (starts[(i + 1) % count] - starts[i]) % arena for i in range(count)
                    ]
                    assert min(gaps) > CORE_SIZE, (
                        stage_name,
                        condition["id"],
                        roster_id,
                        layout.layout_id,
                    )


def test_standard_placements_stay_non_overlapping_at_every_condition(
    grid: dict[str, Any]
) -> None:
    for _stage, condition in _conditions(grid):
        arena = condition["arena_size"]
        for placement in standard_placements(arena):
            gap = (placement.opponent_start - placement.subject_start) % arena
            assert min(gap, arena - gap) > CORE_SIZE, (condition["id"], placement.placement_id)


def test_every_action_budget_is_positive(grid: dict[str, Any]) -> None:
    for _stage, condition in _conditions(grid):
        assert condition["instr_per_tick"] >= 1, condition["id"]


def test_the_evaluation_service_accepts_every_declared_condition(
    grid: dict[str, Any], corpus: dict[str, Any], staged_root: Path
) -> None:
    """The grid is only reproducible if the production validator agrees.

    ``preflight`` runs the same ``_validate`` an ordinary ``bytefray agents
    evaluate`` invocation does, without executing any match.
    """

    rosters = {entry["id"]: entry for entry in corpus["group"]["rosters"]}
    service = EvaluationService()
    for stage in grid["stages"].values():
        for condition in stage["conditions"]:
            for roster_id in stage["rosters"]:
                roster = rosters[roster_id]["roster"]
                service.preflight(
                    candidate_id=roster[0],
                    opponent_ids=tuple(roster[1:]),
                    seeds=tuple(stage["seeds"]),
                    ticks=stage["ticks"],
                    data_root=staged_root,
                    ruleset_id=BYTEFRAY_RULESET_V2_ID,
                    group=True,
                    arena_size=condition["arena_size"],
                    instr_per_tick=condition["instr_per_tick"],
                )


def test_an_arena_below_the_bound_is_still_rejected(staged_root: Path) -> None:
    """The grid stays inside a real fence, not a decorative one."""

    service = EvaluationService()
    with pytest.raises(EvaluationConfigurationError, match="too small"):
        service.preflight(
            candidate_id="claimer",
            opponent_ids=("core_tracker", "core_defender"),
            seeds=(1,),
            ticks=400,
            data_root=staged_root,
            ruleset_id=BYTEFRAY_RULESET_V2_ID,
            group=True,
            arena_size=32,
            instr_per_tick=8,
        )


# ---------------------------------------------------------------------------
# The design's own claims about itself
# ---------------------------------------------------------------------------


def _sweeps(condition: dict[str, Any], ticks: int) -> float:
    return (condition["instr_per_tick"] * ticks) / condition["arena_size"]


def test_the_default_condition_is_present_and_is_the_ruleset_default(
    grid: dict[str, Any]
) -> None:
    main = grid["stages"]["main"]
    defaults = [c for c in main["conditions"] if c.get("is_default")]
    assert len(defaults) == 1
    condition = defaults[0]
    assert condition["arena_size"] == Config().arena_size
    assert condition["instr_per_tick"] == Config().instr_per_tick


def test_recorded_configured_density_matches_its_own_formula(grid: dict[str, Any]) -> None:
    main = grid["stages"]["main"]
    for condition in main["conditions"]:
        assert math.isclose(
            condition["configured_sweeps_per_entrant"], _sweeps(condition, main["ticks"])
        ), condition["id"]


def test_declared_constant_density_diagonals_really_are_constant_density(
    grid: dict[str, Any]
) -> None:
    """The design separates a density effect from a scale effect by holding
    S fixed while arena size moves; that only works if the diagonals are
    genuinely iso-density."""

    main = grid["stages"]["main"]
    by_id = {c["id"]: c for c in main["conditions"]}
    assert main["constant_density_diagonals"], "the main grid must declare its diagonals"
    for label, condition_ids in main["constant_density_diagonals"].items():
        assert len(condition_ids) >= 2, label
        sweeps = {_sweeps(by_id[cid], main["ticks"]) for cid in condition_ids}
        assert len(sweeps) == 1, (label, sweeps)
        arenas = {by_id[cid]["arena_size"] for cid in condition_ids}
        assert len(arenas) == len(condition_ids), label


def test_the_default_density_diagonal_spans_the_widest_arena_range(
    grid: dict[str, Any]
) -> None:
    """The scale-invariance test only bites if the iso-density diagonal
    through the *default* condition is the one that spans the most arena
    scale."""

    main = grid["stages"]["main"]
    by_id = {c["id"]: c for c in main["conditions"]}
    default = next(c for c in main["conditions"] if c.get("is_default"))
    containing = [
        ids
        for ids in main["constant_density_diagonals"].values()
        if default["id"] in ids
    ]
    assert len(containing) == 1
    arenas = [by_id[cid]["arena_size"] for cid in containing[0]]
    assert max(arenas) / min(arenas) >= 64


def test_the_main_grid_spans_a_wide_density_range(grid: dict[str, Any]) -> None:
    main = grid["stages"]["main"]
    sweeps = [_sweeps(c, main["ticks"]) for c in main["conditions"]]
    assert min(sweeps) < 0.05
    assert max(sweeps) > 25.0


def test_the_main_grid_records_a_stopping_criterion_declared_up_front(
    grid: dict[str, Any]
) -> None:
    """Phase 1P: the explored region is fixed before the run, so the phase
    cannot be extended afterwards until a preferred result appears."""

    main = grid["stages"]["main"]
    assert main["declared_before_interpretation"] is True
    assert main["stopping_criterion"].strip()
    arenas = {c["arena_size"] for c in main["conditions"]}
    budgets = {c["instr_per_tick"] for c in main["conditions"]}
    assert f"[{min(arenas)}, {max(arenas)}]" in main["stopping_criterion"]
    assert f"[{min(budgets)}, {max(budgets)}]" in main["stopping_criterion"]


def test_every_axis_value_carries_a_recorded_rationale(grid: dict[str, Any]) -> None:
    main = grid["stages"]["main"]
    for key in ("tick_rationale", "seed_rationale", "roster_rationale", "pair_rationale"):
        assert main[key].strip(), key
    for condition in main["conditions"]:
        assert condition["arena_rationale"].strip(), condition["id"]
        assert condition["budget_rationale"].strip(), condition["id"]


def test_the_grid_holds_ticks_and_seeds_constant_across_conditions(
    grid: dict[str, Any]
) -> None:
    """Arena size and action budget are the only variables. If a condition
    could also carry its own tick limit or seed set, a difference between
    two conditions would no longer be attributable to the two variables
    under test."""

    for stage in grid["stages"].values():
        assert isinstance(stage["ticks"], int)
        assert stage["seeds"]
        for condition in stage["conditions"]:
            assert set(condition) <= {
                "id",
                "arena_size",
                "instr_per_tick",
                "configured_sweeps_per_entrant",
                "is_default",
                "arena_rationale",
                "budget_rationale",
                "probe",
            }


def test_at_least_three_seeds_so_seed_sensitivity_is_measurable(
    grid: dict[str, Any]
) -> None:
    assert len(grid["stages"]["main"]["seeds"]) >= 3
