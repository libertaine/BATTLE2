"""Qt-free tests for the Designer's `agents validate`/`agents test` output parsers.

``app/services/agent_workflows.py`` has no PySide6 import, so it is tested
here alongside its sibling ``app.services.designer_workflows`` coverage
(``engine/tests/test_designer_workflows.py``), not under the ``gui``-marked
suite. These tests feed the parsers literal example text matching
``docs/specs/agent_validation.md`` Sec 3.4's and ``docs/specs/agent_test.md``
Sec 11's documented CLI contracts, proving the Designer's parsers and each
CLI's actual output shape agree.
"""

from __future__ import annotations

import json

from app.services.agent_workflows import (
    DevelopmentTestPresentation,
    ForfeitDiagnostic,
    ValidationPresentation,
    build_development_test_presentation,
    build_validation_presentation,
)


def test_valid_result_parses_api_version_and_dry_run_action():
    stdout = (
        "agent: my_agent\n"
        "status: valid\n"
        "api_version: 1\n"
        "dry_run_action: WRITE operand=173 value=165\n"
    )

    presentation = build_validation_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation == ValidationPresentation(
        agent_id="my_agent",
        valid=True,
        api_version=1,
        dry_run_action="WRITE operand=173 value=165",
    )
    assert presentation.is_tool_failure is False


def test_valid_result_with_no_operand_action():
    stdout = "agent: halts\nstatus: valid\napi_version: 1\ndry_run_action: HALT\n"

    presentation = build_validation_presentation(0, stdout, "", agent_id="halts")

    assert presentation.valid is True
    assert presentation.dry_run_action == "HALT"


def test_invalid_result_parses_stage_code_error_and_detail():
    stderr = (
        "agent: broken_reset\n"
        "status: invalid\n"
        "stage: reset\n"
        "code: agent_reset_failed\n"
        "error: Python agent broken_reset reset failed: RuntimeError: boom\n"
        "detail: RuntimeError\n"
    )

    presentation = build_validation_presentation(2, "", stderr, agent_id="broken_reset")

    assert presentation == ValidationPresentation(
        agent_id="broken_reset",
        valid=False,
        stage="reset",
        code="agent_reset_failed",
        error="Python agent broken_reset reset failed: RuntimeError: boom",
        detail="RuntimeError",
    )
    assert presentation.is_tool_failure is False


def test_invalid_result_without_optional_detail_line():
    stderr = (
        "agent: unknown_agent\n"
        "status: invalid\n"
        "stage: discovery\n"
        "code: agent_unknown\n"
        "error: Unknown agent 'unknown_agent'.\n"
    )

    presentation = build_validation_presentation(2, "", stderr, agent_id="unknown_agent")

    assert presentation.valid is False
    assert presentation.stage == "discovery"
    assert presentation.code == "agent_unknown"
    assert presentation.detail is None
    assert presentation.is_tool_failure is False


def test_validation_internal_error_code_is_surfaced_as_tool_failure():
    stderr = (
        "agent: my_agent\n"
        "status: invalid\n"
        "stage: internal\n"
        "code: validation_internal_error\n"
        "error: Something unexpected happened inside the validator.\n"
    )

    presentation = build_validation_presentation(2, "", stderr, agent_id="my_agent")

    assert presentation.is_tool_failure is True
    assert presentation.code == "validation_internal_error"
    assert presentation.raw_output  # kept for troubleshooting


def test_malformed_success_output_is_a_tool_failure_not_a_valid_result():
    presentation = build_validation_presentation(0, "not the expected shape\n", "", agent_id="x")

    assert presentation.is_tool_failure is True
    assert presentation.valid is False
    assert "unexpected output" in (presentation.error or "")


def test_missing_output_on_success_exit_is_a_tool_failure():
    presentation = build_validation_presentation(0, "", "", agent_id="x")

    assert presentation.is_tool_failure is True


def test_malformed_failure_output_is_a_tool_failure():
    presentation = build_validation_presentation(2, "", "garbage on stderr\n", agent_id="x")

    assert presentation.is_tool_failure is True
    assert presentation.stage is None


def test_non_numeric_api_version_is_a_tool_failure():
    stdout = "agent: x\nstatus: valid\napi_version: not-a-number\ndry_run_action: HALT\n"

    presentation = build_validation_presentation(0, stdout, "", agent_id="x")

    assert presentation.is_tool_failure is True


def test_unexpected_exit_code_is_a_tool_failure_with_raw_output_preserved():
    presentation = build_validation_presentation(
        1, "partial stdout\n", "partial stderr\n", agent_id="x"
    )

    assert presentation.is_tool_failure is True
    assert "exited unexpectedly" in (presentation.error or "")
    assert "partial stdout" in presentation.raw_output
    assert "partial stderr" in presentation.raw_output


def test_no_output_at_all_on_unexpected_exit_is_a_tool_failure():
    presentation = build_validation_presentation(-9, "", "", agent_id="x")

    assert presentation.is_tool_failure is True


# ---------------------------------------------------------------------------
# ``agents test`` output parser (Phase 4c)
# ---------------------------------------------------------------------------


def _write_result_json(path, *, winner, termination_reason, replay_filename="replay.jsonl"):
    path.write_text(
        json.dumps(
            {
                "schema": "battle2.result",
                "schema_version": 1,
                "result_id": "result_1",
                "match_id": "match_1",
                "mode": "native",
                "winner": winner,
                "termination_reason": termination_reason,
                "ticks": 117,
                "replay": {
                    "replay_id": "replay_1",
                    "sha256": "abc",
                    "filename": replay_filename,
                },
            }
        ),
        encoding="utf-8",
    )


def test_completed_match_reuses_real_result_json_for_authoritative_fields(tmp_path):
    """Proves reuse: winner/termination/replay come from `read_match_presentation`."""
    result_path = tmp_path / "result.json"
    replay_path = tmp_path / "replay.jsonl"
    replay_path.write_text("{}", encoding="utf-8")
    _write_result_json(result_path, winner="my_agent", termination_reason="last_agent_standing")

    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 117/200\n"
        "winner: my_agent\n"
        "termination: last_agent_standing\n"
        f"result: {result_path}\n"
        f"replay: {replay_path}\n"
        f"summary: {tmp_path / 'summary.json'}\n"
        "\n"
        f"Run 'bytefray replay --replay {replay_path}' to inspect it.\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "completed"
    assert presentation.agent_id == "my_agent"
    assert presentation.opponent == "reference"
    assert presentation.seed == 1337
    assert presentation.ticks_run == 117
    assert presentation.ticks_requested == 200
    assert presentation.match is not None
    assert presentation.match.winner == "my_agent"
    assert presentation.match.termination_reason == "last_agent_standing"
    assert presentation.match.replay_path == replay_path
    assert presentation.forfeits == ()
    assert presentation.is_tool_failure is False


def test_completed_match_tie_and_termination_values_are_parsed_via_fallback():
    stdout = (
        "agent: my_agent\n"
        "opponent: other_agent\n"
        "seed: 42\n"
        "ticks: 200/200\n"
        "winner: tie\n"
        "termination: tick_limit\n"
        "result: /does/not/exist/result.json\n"
        "replay: /does/not/exist/replay.jsonl\n"
        "summary: /does/not/exist/summary.json\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "completed"
    assert presentation.match is not None
    assert presentation.match.winner == "tie"
    assert presentation.match.termination_reason == "tick_limit"


def test_completed_match_with_one_forfeit_line():
    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 50/200\n"
        "winner: reference\n"
        "termination: last_agent_standing\n"
        "forfeit: my_agent stage=action code=agent_action_invalid\n"
        "result: /r/result.json\n"
        "replay: /r/replay.jsonl\n"
        "summary: /r/summary.json\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "completed"
    assert presentation.forfeits == (
        ForfeitDiagnostic(agent="my_agent", stage="action", code="agent_action_invalid"),
    )


def test_completed_match_with_multiple_forfeit_lines_in_order():
    stdout = (
        "agent: my_agent\n"
        "opponent: other_agent\n"
        "seed: 1337\n"
        "ticks: 200/200\n"
        "winner: tie\n"
        "termination: all_agents_dead\n"
        "forfeit: my_agent stage=action code=agent_action_invalid\n"
        "forfeit: other_agent stage=action code=agent_action_failed\n"
        "result: /r/result.json\n"
        "replay: /r/replay.jsonl\n"
        "summary: /r/summary.json\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.forfeits == (
        ForfeitDiagnostic(agent="my_agent", stage="action", code="agent_action_invalid"),
        ForfeitDiagnostic(agent="other_agent", stage="action", code="agent_action_failed"),
    )


def test_tested_agent_initialization_failure():
    stdout = (
        "agent: my_agent\n"
        "status: initialization_failed\n"
        "stage: reset\n"
        "code: agent_reset_failed\n"
        "error: Python agent my_agent reset failed: RuntimeError: boom\n"
        "detail: RuntimeError\n"
        "result: none\n"
        "replay: none\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation == DevelopmentTestPresentation(
        agent_id="my_agent",
        outcome="initialization_failed",
        opponent=None,
        stage="reset",
        code="agent_reset_failed",
        error="Python agent my_agent reset failed: RuntimeError: boom",
        detail="RuntimeError",
    )
    assert presentation.match is None


def test_explicit_opponent_initialization_failure_names_the_opponent():
    stdout = (
        "agent: my_agent\n"
        "opponent: other_python_agent\n"
        "status: initialization_failed\n"
        "stage: reset\n"
        "code: agent_reset_failed\n"
        "error: Python agent other_python_agent reset failed: RuntimeError: boom\n"
        "detail: RuntimeError\n"
        "result: none\n"
        "replay: none\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "initialization_failed"
    assert presentation.opponent == "other_python_agent"
    assert presentation.error == (
        "Python agent other_python_agent reset failed: RuntimeError: boom"
    )


def test_initialization_failure_without_optional_detail_line():
    stdout = (
        "agent: my_agent\n"
        "status: initialization_failed\n"
        "stage: load\n"
        "code: agent_import_failed\n"
        "error: Failed importing Python agent source.\n"
        "result: none\n"
        "replay: none\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "initialization_failed"
    assert presentation.detail is None


def test_malformed_ticks_field_is_a_tool_failure():
    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: not-a-fraction\n"
        "winner: my_agent\n"
        "termination: last_agent_standing\n"
        "result: /r/result.json\n"
        "replay: /r/replay.jsonl\n"
        "summary: /r/summary.json\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True


def test_missing_required_labels_on_completed_shape_is_a_tool_failure():
    stdout = (
        "agent: my_agent\n"
        "winner: my_agent\n"
        "termination: last_agent_standing\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True


def test_missing_required_labels_on_initialization_failure_is_a_tool_failure():
    stdout = "agent: my_agent\nstatus: initialization_failed\nresult: none\nreplay: none\n"

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True


def test_duplicate_labels_keep_the_first_value():
    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "opponent: second_value_ignored\n"
        "seed: 1337\n"
        "ticks: 200/200\n"
        "winner: my_agent\n"
        "termination: tick_limit\n"
        "result: /r/result.json\n"
        "replay: /r/replay.jsonl\n"
        "summary: /r/summary.json\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.opponent == "reference"


def test_windows_drive_letter_paths_are_preserved_exactly():
    result_path = r"C:\Users\dev\data\runs\agents_test\my_agent\run\result.json"
    replay_path = r"C:\Users\dev\data\runs\agents_test\my_agent\run\replay.jsonl"
    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 200/200\n"
        "winner: my_agent\n"
        "termination: tick_limit\n"
        f"result: {result_path}\n"
        f"replay: {replay_path}\n"
        r"summary: C:\Users\dev\data\runs\agents_test\my_agent\run\summary.json"
        "\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "completed"
    assert presentation.match is not None
    assert str(presentation.match.result_path) == result_path
    assert str(presentation.match.replay_path) == replay_path


def test_replay_hint_line_is_ignored_not_treated_as_structured_data():
    stdout = (
        "agent: my_agent\n"
        "opponent: reference\n"
        "seed: 1337\n"
        "ticks: 200/200\n"
        "winner: my_agent\n"
        "termination: tick_limit\n"
        "result: /r/result.json\n"
        "replay: /r/replay.jsonl\n"
        "summary: /r/summary.json\n"
        "\n"
        "Run 'bytefray replay --replay /r/replay.jsonl' to inspect it.\n"
    )

    presentation = build_development_test_presentation(0, stdout, "", agent_id="my_agent")

    assert presentation.outcome == "completed"


def test_unexpected_exit_code_is_a_tool_failure():
    presentation = build_development_test_presentation(
        1, "partial stdout\n", "partial stderr\n", agent_id="my_agent"
    )

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True
    assert "exited unexpectedly" in (presentation.error or "")
    assert "partial stdout" in presentation.raw_output
    assert "partial stderr" in presentation.raw_output


def test_internal_tool_error_stderr_shape_at_exit_2():
    stderr = (
        "agent: my_agent\n"
        "status: error\n"
        "stage: internal\n"
        "code: agent_test_internal_error\n"
        "error: Internal reference opponent failed to initialize.\n"
    )

    presentation = build_development_test_presentation(2, "", stderr, agent_id="my_agent")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True
    assert presentation.stage == "internal"
    assert presentation.code == "agent_test_internal_error"
    assert presentation.error == "Internal reference opponent failed to initialize."


def test_exit_2_without_structured_diagnostic_is_still_a_tool_failure():
    presentation = build_development_test_presentation(2, "", "unstructured crash text\n", agent_id="x")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True


def test_exit_0_with_neither_completed_nor_initialization_shape_is_a_tool_failure():
    presentation = build_development_test_presentation(0, "nonsense output\n", "", agent_id="x")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True


def test_no_output_at_all_on_success_exit_is_a_tool_failure():
    presentation = build_development_test_presentation(0, "", "", agent_id="x")

    assert presentation.outcome == "tool_error"
    assert presentation.is_tool_failure is True
