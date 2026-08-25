"""v3 research Phase 2 -- bounded locality through the evaluation harness.

The runtime-level checks live in ``test_v3_phase2_locality_runtime.py``.
This module covers the harness: that a locality evaluation is identity-
bearing on its reach, that reach is disclosed in the persisted artifact and
is comparability-gating, that serial and parallel execution agree, that
resume is safe, and -- the load-bearing negative -- that none of it moves a
single byte of a non-locality evaluation's identity or artifacts.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    EvaluationConfigurationError,
    EvaluationRequest,
    EvaluationService,
    effective_conditions_for,
    effective_conditions_payload,
    is_ruleset_v2_methodology,
)
from battle_engine.python_runtime import DEFAULT_LOCALITY_REACH
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V2_ID,
    BYTEFRAY_RULESET_V3_ALPHA1_ID,
)

LOCALITY = BYTEFRAY_RULESET_V3_ALPHA1_ID
V2 = BYTEFRAY_RULESET_V2_ID

LOCAL_SWEEPER = """from battle_engine.agent_api import ActionKind, AgentAction


class Agent:
    def reset(self, context):
        self.reach = context.locality_reach or 1
        self.offset = 0

    def act(self, observation):
        if self.offset >= self.reach:
            self.offset = 0
            return AgentAction(ActionKind.MOVE, self.reach)
        offset = self.offset
        self.offset += 1
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.SIGNATURE)


def create_agent():
    return Agent()
"""

LOCAL_CAMPER = """from battle_engine.agent_api import ActionKind, AgentAction


class Agent:
    def reset(self, context):
        self.reach = context.locality_reach or 1
        self.offset = -self.reach

    def act(self, observation):
        offset = self.offset
        self.offset += 1
        if self.offset > self.reach:
            self.offset = -self.reach
        return AgentAction(ActionKind.LOCAL_WRITE, offset, self.SIGNATURE)


def create_agent():
    return Agent()
"""


def _install(root: Path, agent_id: str, source: str, signature: int) -> None:
    agent_dir = root / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    body = source.replace("self.SIGNATURE", hex(signature))
    agent_dir.joinpath("agent.py").write_text(body, encoding="utf-8")
    agent_dir.joinpath("agent.yaml").write_text(
        json.dumps(
            {
                "name": agent_id,
                "display": agent_id.title(),
                "kind": "python",
                "api_version": 1,
                "entrypoint": "agent.py:create_agent",
                "version": "0.1.0",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def catalog(tmp_path: Path) -> Path:
    _install(tmp_path, "sweeper", LOCAL_SWEEPER, 0x71)
    _install(tmp_path, "camper", LOCAL_CAMPER, 0x72)
    _install(tmp_path, "sweeper2", LOCAL_SWEEPER, 0x73)
    return tmp_path


def _request(catalog: Path, output: str, **overrides) -> EvaluationRequest:
    defaults: dict[str, object] = {
        "candidate_id": "sweeper",
        "opponent_ids": ("camper",),
        "seeds": (1,),
        "output_dir": catalog / output,
        "ticks": 20,
        "data_root": catalog,
        "ruleset_id": LOCALITY,
        "locality_reach": 16,
        "arena_size": 512,
        "instr_per_tick": 4,
        "both_orientations": False,
    }
    defaults.update(overrides)
    return EvaluationRequest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Methodology and validation
# ---------------------------------------------------------------------------


def test_locality_uses_the_v2_evaluation_methodology_so_the_control_is_comparable() -> None:
    """The experiment's whole design is "addressing changes, nothing else".
    That requires the identical standard placements/layouts/seed set/capture
    evidence the Ruleset-v2 control runs under."""

    assert is_ruleset_v2_methodology(LOCALITY)
    assert is_ruleset_v2_methodology(V2)
    assert not is_ruleset_v2_methodology(BYTEFRAY_RULESET_ID)
    assert not is_ruleset_v2_methodology("bytefray-rules-2-alpha11")


def test_a_reach_without_the_locality_ruleset_is_rejected_rather_than_ignored(
    catalog,
) -> None:
    with pytest.raises(EvaluationConfigurationError, match="--locality-reach requires"):
        EvaluationService()._validate(_request(catalog, "out", ruleset_id=V2))


def test_a_non_positive_reach_is_rejected(catalog) -> None:
    with pytest.raises(EvaluationConfigurationError, match="positive --locality-reach"):
        EvaluationService()._validate(_request(catalog, "out", locality_reach=0))


def test_an_unregistered_ruleset_is_still_rejected(catalog) -> None:
    with pytest.raises(EvaluationConfigurationError, match="Unsupported evaluation"):
        EvaluationService()._validate(
            _request(catalog, "out", ruleset_id="bytefray-rules-3", locality_reach=None)
        )


def test_an_omitted_reach_under_locality_resolves_to_the_documented_default(
    catalog,
) -> None:
    request = _request(catalog, "out", locality_reach=None)
    assert request.resolved_locality_reach == DEFAULT_LOCALITY_REACH


def test_resolved_reach_is_none_for_every_non_locality_request(catalog) -> None:
    for ruleset_id in (None, BYTEFRAY_RULESET_ID, V2):
        request = _request(catalog, "out", ruleset_id=ruleset_id, locality_reach=None)
        assert request.resolved_locality_reach is None


# ---------------------------------------------------------------------------
# Conditions payload: additive under locality, byte-identical without it
# ---------------------------------------------------------------------------


def test_the_conditions_payload_is_byte_identical_without_locality() -> None:
    conditions = effective_conditions_for(400, 1)
    assert effective_conditions_payload(conditions, None) == asdict(conditions)
    assert effective_conditions_payload(conditions) == asdict(conditions)


def test_the_conditions_payload_gains_exactly_one_key_under_locality() -> None:
    conditions = effective_conditions_for(400, 1)
    plain = asdict(conditions)
    with_reach = effective_conditions_payload(conditions, 32)
    assert set(with_reach) - set(plain) == {"locality_reach"}
    assert with_reach["locality_reach"] == 32
    assert {k: v for k, v in with_reach.items() if k != "locality_reach"} == plain


def test_effective_conditions_itself_gained_no_field() -> None:
    """Reach lives in the *payload*, never on the dataclass: a new dataclass
    field would put ``locality_reach: null`` into every historical
    evaluation's conditions and change every evaluation_id ever computed."""

    assert "locality_reach" not in effective_conditions_for(400, 1).__dataclass_fields__


# ---------------------------------------------------------------------------
# Evaluation identity
# ---------------------------------------------------------------------------


def _evaluation_id(service: EvaluationService, request: EvaluationRequest) -> str:
    specs = service._validate(request)
    from battle_engine.agent_evaluation import agent_identity

    identities = {agent_id: agent_identity(spec) for agent_id, spec in specs.items()}
    return service._evaluation_id(request, identities, service._effective_conditions(request))


def test_changing_reach_changes_the_evaluation_identity(catalog) -> None:
    service = EvaluationService()
    assert _evaluation_id(service, _request(catalog, "a", locality_reach=8)) != _evaluation_id(
        service, _request(catalog, "b", locality_reach=32)
    )


def test_an_explicit_default_reach_and_an_omitted_one_share_one_identity(catalog) -> None:
    service = EvaluationService()
    assert _evaluation_id(
        service, _request(catalog, "a", locality_reach=DEFAULT_LOCALITY_REACH)
    ) == _evaluation_id(service, _request(catalog, "b", locality_reach=None))


def test_a_locality_evaluation_never_collides_with_its_ruleset_v2_control(catalog) -> None:
    service = EvaluationService()
    locality = _evaluation_id(service, _request(catalog, "a"))
    control = _evaluation_id(
        service, _request(catalog, "b", ruleset_id=V2, locality_reach=None)
    )
    assert locality != control


def test_a_ruleset_v2_evaluation_identity_is_untouched_by_phase_2(catalog) -> None:
    """The regression that would matter most: Phase 2 must not have moved any
    pre-existing evaluation's id. A v2 request's hashed conditions payload is
    exactly ``asdict(conditions)``, as it has always been."""

    request = _request(catalog, "out", ruleset_id=V2, locality_reach=None)
    conditions = EvaluationService()._effective_conditions(request)
    assert effective_conditions_payload(
        conditions, request.resolved_locality_reach
    ) == asdict(conditions)


# ---------------------------------------------------------------------------
# End-to-end execution, determinism, and disclosure
# ---------------------------------------------------------------------------


def _run(catalog: Path, output: str, **overrides):
    return EvaluationService().run(_request(catalog, output, **overrides))


def _cell_fingerprints(result) -> list[tuple]:
    return [
        (cell.subject_id, cell.opponent_id, cell.seed, cell.match_id, cell.outcome)
        for cell in result.cells
    ]


def test_a_locality_evaluation_runs_and_records_its_reach(catalog) -> None:
    result = _run(catalog, "run")
    assert result.cells
    assert all(cell.status == "completed" for cell in result.cells)
    state = json.loads((catalog / "run" / "evaluation.json").read_text())
    assert state["rules_compatibility_id"] == LOCALITY
    assert state["effective_conditions"]["locality_reach"] == 16


def test_repeated_identical_locality_evaluations_reproduce_exactly(catalog) -> None:
    first = _run(catalog, "first")
    second = _run(catalog, "second")
    assert first.evaluation_id == second.evaluation_id
    assert _cell_fingerprints(first) == _cell_fingerprints(second)


def test_serial_and_parallel_locality_execution_agree(catalog) -> None:
    serial = _run(catalog, "serial", workers=1, seeds=(1, 2))
    parallel = _run(catalog, "parallel", workers=3, seeds=(1, 2))
    assert serial.evaluation_id == parallel.evaluation_id
    assert _cell_fingerprints(serial) == _cell_fingerprints(parallel)


def test_resuming_a_completed_locality_evaluation_changes_nothing(catalog) -> None:
    first = _run(catalog, "resume", seeds=(1, 2))
    again = _run(catalog, "resume", seeds=(1, 2), resume=True)
    assert again.evaluation_id == first.evaluation_id
    assert _cell_fingerprints(again) == _cell_fingerprints(first)
    assert not [cell for cell in again.cells if cell.status == "corrupted"]


def test_a_group_locality_evaluation_runs_under_the_v2_layout_methodology(catalog) -> None:
    result = EvaluationService().run(
        _request(
            catalog,
            "group",
            opponent_ids=("camper", "sweeper2"),
            group=True,
        )
    )
    assert result.cells
    assert all(cell.status == "completed" for cell in result.cells)
    assert all(cell.is_group for cell in result.cells)
    state = json.loads((catalog / "group" / "evaluation.json").read_text())
    assert state["group"] is True
    assert state["effective_conditions"]["locality_reach"] == 16


def test_locality_telemetry_reaches_each_cells_result_json(catalog) -> None:
    """Phase 2N's spatial measurements are read from ``result.json`` by the
    research tooling rather than by widening any evaluation record -- the same
    approach Phase 1 used for ``cpu_total``."""

    result = _run(catalog, "telemetry")
    cell = result.cells[0]
    envelope = json.loads((Path(cell.artifact_dir) / "result.json").read_text())
    for entrant in envelope["entrants"]:
        locality = entrant["metadata"]["locality"]
        assert locality["local_writes"] > 0
        assert locality["reach_misses"] == 0
        assert isinstance(locality["encounter_ticks"], int)


def test_the_experimental_condition_is_disclosed_in_human_readable_output(
    catalog, capsys
) -> None:
    from battle_engine.agent_evaluation import _print_experimental_conditions

    _print_experimental_conditions(_request(catalog, "out"))
    out = capsys.readouterr().out
    assert "locality reach: 16" in out
    assert "EXPERIMENTAL" in out


def test_nothing_is_disclosed_for_an_ordinary_default_evaluation(catalog, capsys) -> None:
    from battle_engine.agent_evaluation import _print_experimental_conditions

    _print_experimental_conditions(
        _request(
            catalog,
            "out",
            ruleset_id=V2,
            locality_reach=None,
            arena_size=None,
            instr_per_tick=None,
        )
    )
    assert capsys.readouterr().out == ""


def test_the_product_cli_does_not_advertise_the_experimental_ruleset(capsys) -> None:
    """``agents evaluate --ruleset`` exposes exactly the two product-facing
    identities. A research identity that is explicitly not a stable contract
    has no business appearing in a shipped command's ``--help``; the Phase 2
    driver constructs its ``EvaluationRequest`` directly instead."""

    from battle_engine.agent_evaluation import main as evaluate_main

    with pytest.raises(SystemExit):
        evaluate_main(["--help"])
    out = capsys.readouterr().out
    assert LOCALITY not in out
    assert "--locality-reach" not in out
