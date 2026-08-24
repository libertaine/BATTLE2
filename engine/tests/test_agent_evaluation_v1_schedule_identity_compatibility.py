"""H5 (Beta2 Phase 4.1 pre-qualification review remediation): cross-version
compatibility golden coverage for ``agent_evaluation.build_matrix``'s
``schedule_id`` payload.

The independent review found that Beta2 added ``"placement_id"``
unconditionally to the per-cell ``schedule_id`` hash payload
(``build_matrix``). Even though every v1 (pre-Ruleset-v2-methodology) cell's
``placement_id`` value is the constant ``"fixed"``, adding the *key* itself
changes the hash relative to a payload that never had it -- "every v1 cell
shares the same value" does not make an added dict key a no-op for a hash
function. This silently changed every v1 ``schedule_id`` relative to a
pre-Beta2 artifact resumed under this build (``evaluation_id``/
``condition_fingerprint`` were unaffected, since neither's payload
construction has this defect), so a legacy v1 artifact lost schedule-id
resume continuity on resume and re-executed its entire matrix.

The test below is a genuine cross-version golden test: its expected values
are independently reconstructed from the pre-Beta2 historical recipe at
commit ``2076576`` (``v2.0.0-beta1`` published -- inspect with ``git show
2076576:engine/src/battle_engine/agent_evaluation.py``), never produced by
calling this build's own (previously buggy) ``EvaluationService._evaluation_id``
/``build_matrix`` schedule-id construction. It is safe to reuse
``battle_engine.result_model.stable_id``, ``agent_evaluation.agent_identity``,
and ``agent_evaluation.effective_conditions_for`` directly -- ``git diff
2076576 HEAD`` confirms all three are byte-for-byte unchanged since that
commit, so they are shared low-level primitives, not "the identity helper
under test."
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from battle_engine.agent_evaluation import (
    BYTEFRAY_RULESET_V2_ID,
    CANDIDATE,
    EVALUATION_ARENA_ALIGNMENT_MODE,
    EVALUATION_RULES_COMPATIBILITY_ID,
    IDENTITY_VERSION,
    ORIENTATION_CANDIDATE_FIRST,
    ORIENTATION_MODE_CANDIDATE_FIRST_ONLY,
    EvaluationRequest,
    EvaluationService,
    agent_identity,
    effective_conditions_for,
)
from battle_engine.agents import resolve_agent
from battle_engine.result_model import stable_id

AGENT_SOURCE = (
    "from battle_engine.agent_api import ActionKind, AgentAction\n"
    "class Agent:\n"
    "    def reset(self, context): pass\n"
    "    def act(self, observation): return AgentAction(ActionKind.NOP)\n"
    "def create_agent(): return Agent()\n"
)

# Fixed historical fixture bytes. The pinned identities below were generated
# from this CRLF representation, so write_bytes() is intentional: replacing it
# with platform-native text writing would make the golden test OS-dependent.
AGENT_SOURCE_BYTES = AGENT_SOURCE.replace("\n", "\r\n").encode("utf-8")

# Pinned literals: computed once against the fixed AGENT_SOURCE_BYTES below
# (deterministic -- source_sha256/local_source_fingerprint are content
# hashes of AGENT_SOURCE itself) and against the historical recipe
# reconstructed from commit 2076576. A future change to any key in the v1
# schedule_id/evaluation_id/condition_fingerprint hash payload -- even an
# "innocuous" additive one -- will change these values and fail this test.
EXPECTED_SOURCE_SHA256 = "61e672a4f18f5ccbd9e5ae7f9239aac50af5844067d9e1a668dc92914a4787fa"
EXPECTED_LOCAL_SOURCE_FINGERPRINT = "23d307f18affa230311e6d52c1f8852fe209a85c5fcc02a598d947af348357df"
EXPECTED_EVALUATION_ID = "evaluation-v2_0677e78d27642c3c6f8fa62f"
EXPECTED_SCHEDULE_ID = "evaluation-cell_08c9393822c99186c03001ef"
EXPECTED_CONDITION_FINGERPRINT = "evaluation-condition_3fba859dabbcf03c7cb6048a"


def _write_agent(root: Path, name: str) -> None:
    directory = root / "agents" / name
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text(
        json.dumps(
            {"kind": "python", "api_version": 1, "entrypoint": "agent.py:create_agent", "version": "1.0"}
        ),
        encoding="utf-8",
    )
    (directory / "agent.py").write_bytes(AGENT_SOURCE_BYTES)


def _v1_request(tmp_path: Path) -> EvaluationRequest:
    return EvaluationRequest(
        candidate_id="candidate",
        opponent_ids=("opponent",),
        seeds=(1,),
        output_dir=tmp_path / "eval-out",
        ticks=5,
        data_root=tmp_path,
        both_orientations=False,
    )


def test_v1_identity_matches_pre_beta2_historical_recipe(tmp_path: Path) -> None:
    """The highest-value regression in this remediation: a fixed synthetic
    v1 evaluation request's real, production-computed ``evaluation_id``,
    ``schedule_id``, and ``condition_fingerprint`` must equal literal values
    independently reconstructed from the pre-Beta2 (commit ``2076576``)
    historical payload shapes -- not merely equal each other, and not
    computed by calling the code under test."""

    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")

    assert (tmp_path / "agents" / "candidate" / "agent.py").read_bytes() == AGENT_SOURCE_BYTES

    candidate_spec = resolve_agent(tmp_path, "candidate")
    opponent_spec = resolve_agent(tmp_path, "opponent")
    candidate_identity = agent_identity(candidate_spec)
    opponent_identity = agent_identity(opponent_spec)

    # Sanity: the fixed AGENT_SOURCE bytes must hash exactly as pinned --
    # if this fails, every other pinned literal below is meaningless (the
    # fixture itself drifted, not the code under test).
    assert candidate_identity["source_sha256"] == EXPECTED_SOURCE_SHA256
    assert candidate_identity["local_source_fingerprint"] == EXPECTED_LOCAL_SOURCE_FINGERPRINT

    conditions = effective_conditions_for(ticks=5, agent_api_version=1)
    conditions_dict = asdict(conditions)

    # Pre-Beta2 EvaluationService._evaluation_id payload shape (2076576),
    # reconstructed by hand -- never by calling this build's own
    # _evaluation_id.
    evaluation_id_payload = {
        "identity_version": IDENTITY_VERSION,
        "candidate": candidate_identity,
        "baseline": None,
        "opponents": [opponent_identity],
        "seeds": [1],
        "ticks": 5,
        "effective_conditions": conditions_dict,
        "rules_compatibility_id": EVALUATION_RULES_COMPATIBILITY_ID,
        "orientation_mode": ORIENTATION_MODE_CANDIDATE_FIRST_ONLY,
        "arena_alignment_mode": EVALUATION_ARENA_ALIGNMENT_MODE,
    }
    expected_evaluation_id = stable_id("evaluation-v2", evaluation_id_payload)
    assert expected_evaluation_id == EXPECTED_EVALUATION_ID

    conditions_fingerprint = stable_id("evaluation-conditions", conditions_dict)

    # Pre-Beta2 build_matrix schedule_id payload shape (2076576): exactly
    # {evaluation_id, role, subject_id, opponent_id, seed, orientation,
    # ordinal} -- deliberately no "placement_id" key, which is what Beta2
    # incorrectly added unconditionally (this is the defect under test).
    schedule_id_payload = {
        "evaluation_id": expected_evaluation_id,
        "role": CANDIDATE,
        "subject_id": "candidate",
        "opponent_id": "opponent",
        "seed": 1,
        "orientation": ORIENTATION_CANDIDATE_FIRST,
        "ordinal": 1,
    }
    expected_schedule_id = stable_id("evaluation-cell", schedule_id_payload)
    assert expected_schedule_id == EXPECTED_SCHEDULE_ID

    # Pre-Beta2 build_matrix condition_fingerprint payload shape (2076576)
    # -- unaffected by the defect (never had a "placement" key for v1), but
    # pinned here too since HIGH-5 asks for all three identities.
    condition_fp_payload = {
        "opponent": opponent_identity,
        "seed": 1,
        "effective_conditions": conditions_fingerprint,
        "rules_compatibility_id": EVALUATION_RULES_COMPATIBILITY_ID,
        "condition_occurrence_index": 0,
        "orientation": ORIENTATION_CANDIDATE_FIRST,
        "arena_alignment_mode": EVALUATION_ARENA_ALIGNMENT_MODE,
    }
    expected_condition_fingerprint = stable_id("evaluation-condition", condition_fp_payload)
    assert expected_condition_fingerprint == EXPECTED_CONDITION_FINGERPRINT

    # Now the real production path -- this IS the code under test.
    result = EvaluationService().run(_v1_request(tmp_path))
    state = json.loads(result.state_path.read_text(encoding="utf-8"))

    assert state["evaluation_id"] == EXPECTED_EVALUATION_ID
    assert state["cells"][0]["schedule_id"] == EXPECTED_SCHEDULE_ID
    assert state["cells"][0]["condition_fingerprint"] == EXPECTED_CONDITION_FINGERPRINT


def test_legacy_shaped_v1_schedule_id_resumes_completed_cell(tmp_path: Path) -> None:
    """A cell whose ``schedule_id`` is exactly the pinned historical value
    (proven above to be what this build now produces, and what a genuine
    pre-Beta2 artifact always produced) resumes/reuses correctly rather
    than being silently missed and re-executed -- the concrete consequence
    HIGH-5 was about. Pre-fix, the freshly recomputed matrix cell's
    schedule_id would not have matched EXPECTED_SCHEDULE_ID at all (it
    included the extra "placement_id" key), so resume's `prior_cells.get
    (cell.schedule_id)` lookup would have missed entirely and re-run the
    whole matrix."""

    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")
    request = _v1_request(tmp_path)
    service = EvaluationService()

    first = service.run(request)
    assert first.cells[0].schedule_id == EXPECTED_SCHEDULE_ID
    assert first.cells[0].status == "completed"
    first_match_id = first.cells[0].match_id
    first_result_id = first.cells[0].result_id

    second = service.run(request)
    assert second.evaluation_id == first.evaluation_id
    assert second.cells[0].schedule_id == EXPECTED_SCHEDULE_ID
    assert second.cells[0].status == "completed"
    # Reused, not re-executed: the exact same canonical result identity.
    assert second.cells[0].match_id == first_match_id
    assert second.cells[0].result_id == first_result_id


def test_v5_placement_genuinely_participates_in_pairwise_schedule_identity(tmp_path: Path) -> None:
    """Restoring v1's historical schedule_id shape must not silently make
    `placement_id` inert for Ruleset-v2 (v5) pairwise cells -- it must
    still genuinely change the hash there, exactly as the `condition_
    fingerprint` "placement" sub-key already does (`if placement is not
    None`)."""

    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opponent")
    result = EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate",
            opponent_ids=("opponent",),
            seeds=(1,),
            output_dir=tmp_path / "eval-out",
            ticks=5,
            data_root=tmp_path,
            both_orientations=False,
            ruleset_id=BYTEFRAY_RULESET_V2_ID,
        )
    )
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    cells = state["cells"]
    assert len(cells) == 3  # three standard placements, one orientation

    first_cell = cells[0]
    base_payload = {
        "evaluation_id": state["evaluation_id"],
        "role": CANDIDATE,
        "subject_id": "candidate",
        "opponent_id": "opponent",
        "seed": 1,
        "orientation": first_cell["orientation"],
        "ordinal": first_cell["matrix_ordinal"],
    }
    with_placement_id = stable_id(
        "evaluation-cell", dict(base_payload, placement_id=first_cell["placement_id"])
    )
    without_placement_id = stable_id("evaluation-cell", dict(base_payload))

    assert first_cell["schedule_id"] == with_placement_id
    assert first_cell["schedule_id"] != without_placement_id

    # And every placement really does get its own distinct schedule_id.
    assert len({cell["schedule_id"] for cell in cells}) == 3


def test_v6_group_schedule_identity_payload_shape_unchanged(tmp_path: Path) -> None:
    """The group (v6) schedule_id payload construction lives in a wholly
    separate code path (`_build_group_matrix`) that this fix does not
    touch -- confirm its shape ({evaluation_id, role, roster, seat_agent_ids,
    seed, layout_id, ordinal}) still reproduces exactly, guarding against
    accidental drift from this remediation."""

    _write_agent(tmp_path, "candidate")
    _write_agent(tmp_path, "opp_a")
    _write_agent(tmp_path, "opp_b")
    result = EvaluationService().run(
        EvaluationRequest(
            candidate_id="candidate",
            opponent_ids=("opp_a", "opp_b"),
            seeds=(1,),
            output_dir=tmp_path / "eval-out",
            ticks=5,
            data_root=tmp_path,
            both_orientations=False,
            ruleset_id=BYTEFRAY_RULESET_V2_ID,
            group=True,
        )
    )
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    first_cell = state["cells"][0]

    recomputed = stable_id(
        "evaluation-cell",
        {
            "evaluation_id": state["evaluation_id"],
            "role": CANDIDATE,
            "roster": sorted(state["roster_agent_ids"]),
            "seat_agent_ids": first_cell["seat_agent_ids"],
            "seed": 1,
            "layout_id": first_cell["layout_id"],
            "ordinal": first_cell["matrix_ordinal"],
        },
    )
    assert recomputed == first_cell["schedule_id"]
