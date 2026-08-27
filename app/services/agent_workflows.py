"""Qt-free parsing of ``bytefray agents validate``/``agents test`` output.

Phase 4b's Validate action and Phase 4c's Development Test action both run
their respective ``bytefray agents <subcommand>`` CLI out-of-process
(QProcess) rather than calling the underlying service function directly on
the GUI thread, because both execute arbitrary, unsandboxed, un-timed-out
user Python (``docs/specs/agent_designer_workflow.md`` Sec 5). Each CLI's
existing ``label: value`` stdout/stderr contract
(``docs/specs/agent_validation.md`` Sec 3.4, ``docs/specs/agent_test.md``
Sec 11) is already a small, fully enumerable, versioned-by-convention
surface -- Sec 10.2/Sec 11.2 of the Designer spec concluded that parsing it
is the smallest robust mechanism, in preference to inventing a second,
JSON-shaped worker protocol to carry the same handful of fields. This
module owns exactly that parsing and introduces no new diagnostic taxonomy
of its own: every ``stage``/``code`` value it surfaces is copied verbatim
from Phases 2/3's own ``RuntimeDiagnostic``-derived CLI output, and a
completed development test's authoritative ``winner``/``termination``/
``replay_path`` are read from the exact canonical ``result.json`` a real
match writes (via ``app.services.designer_workflows.read_match_presentation``),
never re-derived from CLI text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services.designer_workflows import MatchPresentation, read_match_presentation


@dataclass(frozen=True)
class ValidationPresentation:
    """Typed rendering of one completed ``bytefray agents validate`` run.

    ``is_tool_failure`` distinguishes "Bytefray could not complete
    validation" (worker/process failure, malformed output, or the
    ``validation_internal_error`` diagnostic code) from an ordinary agent
    validation failure -- the former is presented as "Validation could not
    be completed", never collapsed into the same red "Invalid" label an
    authoring problem gets.
    """

    agent_id: str
    valid: bool
    api_version: int | None = None
    dry_run_action: str | None = None
    stage: str | None = None
    code: str | None = None
    error: str | None = None
    detail: str | None = None
    is_tool_failure: bool = False
    raw_output: str = ""


def _parse_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ": " not in line:
            continue
        label, _, value = line.partition(": ")
        fields.setdefault(label.strip(), value.strip())
    return fields


def _tool_failure(agent_id: str, message: str, *, raw_output: str = "") -> ValidationPresentation:
    return ValidationPresentation(
        agent_id=agent_id,
        valid=False,
        error=message,
        is_tool_failure=True,
        raw_output=raw_output,
    )


def build_validation_presentation(
    exit_code: int, stdout: str, stderr: str, *, agent_id: str
) -> ValidationPresentation:
    """Build a typed presentation from one completed ``agents validate`` run.

    Malformed, missing, or unexpected-shaped output at any exit code is
    treated as a tool/internal failure -- never silently mis-rendered as an
    agent-authoring result -- matching the requirement that an opaque
    worker/process problem must stay visually and semantically distinct
    from a validation result the tool completed correctly.
    """

    if exit_code == 0:
        fields = _parse_lines(stdout)
        if (
            fields.get("status") != "valid"
            or "api_version" not in fields
            or "dry_run_action" not in fields
        ):
            return _tool_failure(
                agent_id,
                "Validation exited successfully but produced unexpected output.",
                raw_output=stdout + stderr,
            )
        try:
            api_version = int(fields["api_version"])
        except ValueError:
            return _tool_failure(
                agent_id,
                "Validation reported a non-numeric api_version.",
                raw_output=stdout + stderr,
            )
        return ValidationPresentation(
            agent_id=fields.get("agent", agent_id),
            valid=True,
            api_version=api_version,
            dry_run_action=fields["dry_run_action"],
        )

    if exit_code == 2:
        fields = _parse_lines(stderr)
        if fields.get("status") != "invalid" or not fields.get("stage") or not fields.get("code"):
            return _tool_failure(
                agent_id,
                "Validation reported a failure without a structured diagnostic.",
                raw_output=stdout + stderr,
            )
        code = fields["code"]
        is_internal = code == "validation_internal_error"
        return ValidationPresentation(
            agent_id=fields.get("agent", agent_id),
            valid=False,
            stage=fields.get("stage"),
            code=code,
            error=fields.get("error"),
            detail=fields.get("detail"),
            is_tool_failure=is_internal,
            raw_output=(stdout + stderr) if is_internal else "",
        )

    return _tool_failure(
        agent_id,
        f"Validation process exited unexpectedly (code {exit_code}).",
        raw_output=stdout + stderr,
    )


@dataclass(frozen=True)
class ForfeitDiagnostic:
    """One ``forfeit: <agent> stage=<stage> code=<code>`` line, parsed structurally."""

    agent: str
    stage: str
    code: str


@dataclass(frozen=True)
class DevelopmentTestPresentation:
    """Typed rendering of one completed ``bytefray agents test`` run.

    ``outcome`` distinguishes the three shapes ``docs/specs/agent_test.md``
    Sec 11 documents -- a completed match (``match`` carries the
    canonical, ``result.json``-derived winner/termination/replay path, and
    ``forfeits`` carries zero or more structured per-agent forfeits), a
    pre-tick-zero ``initialization_failed`` outcome for the tested agent or
    an explicit ``--opponent`` (still exit 0 -- an agent-development
    outcome, not a tool failure), or a ``tool_error`` (exit 2, or malformed/
    missing output at any exit code) that must never be confused with
    either agent-development outcome above. ``is_tool_failure`` is set only
    for the ``tool_error`` outcome.
    """

    agent_id: str
    outcome: Literal["completed", "initialization_failed", "tool_error"] = "completed"
    opponent: str | None = None
    seed: int | None = None
    ticks_run: int | None = None
    ticks_requested: int | None = None
    match: MatchPresentation | None = None
    summary_path: Path | None = None
    trace_path: Path | None = None
    forfeits: tuple[ForfeitDiagnostic, ...] = ()
    # The Ruleset the tool reports it actually ran under, copied verbatim
    # from ``agents test``'s own ``ruleset:`` output line -- authoritative
    # over whatever the GUI requested. Deliberately optional rather than
    # part of _COMPLETED_REQUIRED_FIELDS: a missing line renders as "not
    # reported" instead of downgrading a real completed match to a tool
    # failure.
    ruleset_id: str | None = None
    stage: str | None = None
    code: str | None = None
    error: str | None = None
    detail: str | None = None
    is_tool_failure: bool = False
    raw_output: str = ""


_FORFEIT_LINE = re.compile(r"^forfeit: (\S+) stage=(\S+) code=(\S+)$")

_COMPLETED_REQUIRED_FIELDS = (
    "agent",
    "opponent",
    "seed",
    "ticks",
    "winner",
    "termination",
    "result",
    "replay",
    "summary",
)
_INITIALIZATION_FAILURE_REQUIRED_FIELDS = ("agent", "stage", "code", "error")
_TOOL_ERROR_REQUIRED_FIELDS = ("agent", "stage", "code", "error")


def _parse_test_lines(text: str) -> tuple[dict[str, str], tuple[ForfeitDiagnostic, ...]]:
    """Parse ``label: value`` lines plus zero-or-more ``forfeit:`` lines.

    Unlike a plain ``label: value`` line, ``forfeit:`` can legitimately
    repeat (one per forfeited entrant), so it is collected into its own
    ordered sequence rather than folded into the single-value field dict.
    Any other line without a ``": "`` separator (blank lines, the trailing
    ``Run 'bytefray replay ...'`` hint) is ignored, exactly as harmless
    presentation text must be per Sec 22 of the Designer workflow spec.
    Only the first ``": "`` is used as the split point, so a Windows
    drive-letter path (``C:\\...``) in a value is never itself mistaken for
    a second label boundary, and duplicate labels keep their first value.
    """

    fields: dict[str, str] = {}
    forfeits: list[ForfeitDiagnostic] = []
    for line in text.splitlines():
        forfeit_match = _FORFEIT_LINE.match(line)
        if forfeit_match:
            agent, stage, code = forfeit_match.groups()
            forfeits.append(ForfeitDiagnostic(agent=agent, stage=stage, code=code))
            continue
        if ": " not in line:
            continue
        label, _, value = line.partition(": ")
        fields.setdefault(label.strip(), value.strip())
    return fields, tuple(forfeits)


def _test_tool_failure(
    agent_id: str, message: str, *, raw_output: str = ""
) -> DevelopmentTestPresentation:
    return DevelopmentTestPresentation(
        agent_id=agent_id,
        outcome="tool_error",
        error=message,
        is_tool_failure=True,
        raw_output=raw_output,
    )


def _build_completed_test(
    fields: dict[str, str],
    forfeits: tuple[ForfeitDiagnostic, ...],
    *,
    agent_id: str,
    raw_output: str,
) -> DevelopmentTestPresentation:
    missing = [name for name in _COMPLETED_REQUIRED_FIELDS if name not in fields]
    if missing:
        return _test_tool_failure(
            agent_id,
            f"Development test completed but output was missing: {', '.join(missing)}.",
            raw_output=raw_output,
        )

    run_text, sep, requested_text = fields["ticks"].partition("/")
    if not sep:
        return _test_tool_failure(
            agent_id,
            f"Development test reported a malformed ticks field: {fields['ticks']!r}.",
            raw_output=raw_output,
        )
    try:
        ticks_run = int(run_text)
        ticks_requested = int(requested_text)
        seed = int(fields["seed"])
    except ValueError:
        return _test_tool_failure(
            agent_id,
            "Development test reported non-numeric seed/ticks values.",
            raw_output=raw_output,
        )

    result_text = fields["result"]
    replay_text = fields["replay"]
    match: MatchPresentation | None = None
    if result_text and result_text != "none":
        try:
            match = read_match_presentation(Path(result_text))
        except (OSError, ValueError, KeyError):
            match = None
    if match is None:
        # Fall back to the parsed text itself -- used only as a
        # cross-check/fallback when the canonical result.json cannot be
        # read (e.g. it does not exist, as in most parser-only unit
        # tests), never as the primary source when it is available.
        match = MatchPresentation(
            winner=fields["winner"],
            termination_reason=fields["termination"],
            result_path=Path(result_text),
            replay_path=None if replay_text in ("", "none") else Path(replay_text),
        )

    summary_text = fields.get("summary")
    summary_path = None if not summary_text or summary_text == "none" else Path(summary_text)
    trace_text = fields.get("trace")
    trace_path = None if not trace_text or trace_text == "none" else Path(trace_text)

    return DevelopmentTestPresentation(
        agent_id=fields.get("agent", agent_id),
        outcome="completed",
        opponent=fields.get("opponent"),
        seed=seed,
        ticks_run=ticks_run,
        ticks_requested=ticks_requested,
        match=match,
        summary_path=summary_path,
        trace_path=trace_path,
        forfeits=forfeits,
        ruleset_id=fields.get("ruleset"),
    )


def _build_initialization_failure(
    fields: dict[str, str], *, agent_id: str, raw_output: str
) -> DevelopmentTestPresentation:
    missing = [name for name in _INITIALIZATION_FAILURE_REQUIRED_FIELDS if name not in fields]
    if missing:
        return _test_tool_failure(
            agent_id,
            f"Development test reported initialization_failed but output was missing: "
            f"{', '.join(missing)}.",
            raw_output=raw_output,
        )
    trace_text = fields.get("trace")
    trace_path = None if not trace_text or trace_text == "none" else Path(trace_text)
    return DevelopmentTestPresentation(
        agent_id=fields.get("agent", agent_id),
        outcome="initialization_failed",
        opponent=fields.get("opponent"),
        stage=fields["stage"],
        code=fields["code"],
        error=fields["error"],
        detail=fields.get("detail"),
        trace_path=trace_path,
    )


def _build_tool_error(
    fields: dict[str, str], *, agent_id: str, raw_output: str
) -> DevelopmentTestPresentation:
    missing = [name for name in _TOOL_ERROR_REQUIRED_FIELDS if name not in fields]
    if fields.get("status") != "error" or missing:
        return _test_tool_failure(
            agent_id,
            "Development test reported a failure without a structured diagnostic.",
            raw_output=raw_output,
        )
    return DevelopmentTestPresentation(
        agent_id=fields.get("agent", agent_id),
        outcome="tool_error",
        stage=fields.get("stage"),
        code=fields.get("code"),
        error=fields.get("error"),
        is_tool_failure=True,
        raw_output=raw_output,
    )


def build_development_test_presentation(
    exit_code: int, stdout: str, stderr: str, *, agent_id: str
) -> DevelopmentTestPresentation:
    """Build a typed presentation from one completed ``agents test`` run.

    Exit ``0`` covers two agent-development outcomes (a completed match,
    identified by ``winner:``/``termination:`` lines; or a pre-tick-zero
    ``status: initialization_failed``). Exit ``2`` is always a tool/
    infrastructure failure (``docs/specs/agent_test.md`` Sec 11.3 -- unlike
    ``agents validate``, ``agents test`` never uses its stderr shape for an
    agent-authoring result). Malformed, missing, or unexpected-shaped
    output at any exit code is treated as a tool failure rather than
    silently mis-rendered as one of the two real agent-development
    outcomes.
    """

    raw_output = stdout + stderr

    if exit_code == 0:
        fields, forfeits = _parse_test_lines(stdout)
        if fields.get("status") == "initialization_failed":
            return _build_initialization_failure(fields, agent_id=agent_id, raw_output=raw_output)
        if "winner" in fields and "termination" in fields:
            return _build_completed_test(fields, forfeits, agent_id=agent_id, raw_output=raw_output)
        return _test_tool_failure(
            agent_id,
            "Development test exited successfully but produced unexpected output.",
            raw_output=raw_output,
        )

    if exit_code == 2:
        fields, _ = _parse_test_lines(stderr)
        return _build_tool_error(fields, agent_id=agent_id, raw_output=raw_output)

    return _test_tool_failure(
        agent_id,
        f"Development test process exited unexpectedly (code {exit_code}).",
        raw_output=raw_output,
    )
