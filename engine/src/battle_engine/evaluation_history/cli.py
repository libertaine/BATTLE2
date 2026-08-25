"""``bytefray agents evaluations list|show|compare`` (Sec 15)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from battle_engine.agent_evaluation import (
    ORIENTATION_MODE_CANDIDATE_FIRST_ONLY,
    is_ruleset_v2_methodology,
    methodology_lines,
    resolved_arena_alignment_mode,
)
from battle_engine.config import Config
from battle_engine.evaluation_analysis import EvidenceState, paired_evidence_from_verdicts
from battle_engine.evaluation_behavior import BehaviorProfile, analyze_behavior
from battle_engine.evaluation_capture import analyze_capture
from battle_engine.evaluation_group_analysis import analyze_group

from .behavior_adapter import cell_refs_for_behavior
from .comparison import align
from .discovery import AmbiguousSelectorError, adapt_any, discover, resolve_selector
from .group_adapter import group_cell_refs
from .models import ArtifactReadError, FieldConfidence
from .verification import verify_summary


def _print_list_row(entry, verbose: bool = False) -> None:
    summary = entry.summary
    codes = ",".join(code.value for code in entry.health.codes) or "unknown"
    if summary is None:
        print(f"UNREADABLE  {entry.location.evaluation_json_path}  [{codes}]")
        return
    created = summary.created_at.value or f"(file mtime {entry.location.file_modified_at})"
    print(
        f"{summary.evaluation_id}  schema=v{summary.schema.schema_version}  "
        f"candidate={summary.candidate_id}  baseline={summary.baseline_id or 'none'}  "
        f"created={created}  lifecycle={summary.lifecycle_state.value}  health=[{codes}]  "
        f"cells={len(summary.cells)}/{summary.matrix_size}  path={entry.location.evaluation_json_path}"
    )


def _cmd_list(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    artifacts = [Path(a) for a in (args.artifact or [])]
    listing = discover(roots=roots, artifacts=artifacts)
    if args.json:
        print(
            json.dumps(
                {
                    "entries": [entry.to_json() for entry in listing.entries],
                    "duplicate_identity_groups": [
                        {"evaluation_id": eid, "paths": [str(p) for p in paths]}
                        for eid, paths in listing.duplicate_identity_groups
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not listing.entries:
            print("No evaluations found.")
        for entry in listing.entries:
            _print_list_row(entry)
        if listing.duplicate_identity_groups:
            print("duplicate evaluation_id locations:")
            for evaluation_id, paths in listing.duplicate_identity_groups:
                print(f"  {evaluation_id}: {', '.join(str(p) for p in paths)}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    try:
        path = resolve_selector(args.selector, roots=roots)
    except AmbiguousSelectorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        summary = adapt_any(path)
    except ArtifactReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    verified = False
    verify_error: str | None = None
    if args.verify:
        summary, verification = verify_summary(summary)
        verified = verification.all_eligible_verified
        if verification.failed:
            first = verification.failed[0]
            verify_error = f"{first.schedule_id}: {first.error}"
        elif verification.revision_issues:
            verify_error = verification.revision_issues[0]
        elif verification.eligible_count == 0:
            verify_error = "no eligible (completed/scored) cells to verify"

    # v1.6 Phase 5 (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md Sec 18/24): computed
    # only here, explicitly, per selected artifact -- never inside
    # adapt_any/discover, so `evaluations list` never pays a per-cell
    # result.json read merely to enumerate artifacts. On by default (one
    # small JSON read per scored cell is affordable for ordinary/large
    # evaluations, measured ~5-6ms/cell); `--no-behavior` skips it for
    # scripted/automation use against stress-scale (thousands-of-cells)
    # artifacts where that per-cell cost adds up to several seconds.
    # v2.0.0-beta2 Phase 2: evaluation_behavior/evaluation_capture's Tier-2
    # readers resolve the subject's physical match slot via a cell's
    # `orientation` (a 2-value candidate_first/opponent_first axis) --
    # meaningless for a group cell, whose subject occupies whichever seat
    # `seat_agent_ids` says, not a fixed slot "A". Computing either here
    # for a group artifact would silently read the WRONG seat's result.json
    # entry for any cell where the subject isn't literally in seat "A".
    # Deferred explicitly, mirroring agent_evaluation._print_result's
    # identical live-run guard -- see docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_
    # EVALUATION.md's "analysis compatibility" section.
    is_group = summary.group.value is True
    behavior = (
        analyze_behavior(summary.candidate_id, summary.baseline_id, cell_refs_for_behavior(summary))
        if not args.no_behavior and not is_group
        else None
    )
    # v2.0.0-beta2 Phase 1: capture/core evidence is a Ruleset-v2-only
    # concept (Sec Capture) -- computed only when this artifact's own
    # recorded rules_compatibility_id resolves to v2, never for a v1
    # artifact (whose entrants never carry a "core_captured" termination
    # reason anyway, but there is no reason to pay the read for a
    # methodology that never varies it).
    rules_id = summary.rules_compatibility_id.value
    capture = (
        analyze_capture(summary.candidate_id, summary.baseline_id, cell_refs_for_behavior(summary))
        if not args.no_behavior
        and not is_group
        and isinstance(rules_id, str)
        and is_ruleset_v2_methodology(rules_id)
        else None
    )
    # v2.0.0-beta2 Phase 3: the group-analysis counterpart to behavior/
    # capture above -- same opt-in-real-I/O discipline (`--no-behavior`
    # skips it too, since it is the identical cost class: one result.json
    # read per scored cell), computed only for a group artifact (never for
    # a pairwise one, which `evaluation_group_analysis` has no concept of).
    group_analysis = (
        analyze_group(summary.roster_agent_ids.value or (), group_cell_refs(summary))
        if not args.no_behavior and is_group
        else None
    )

    if args.json:
        data = summary.to_json()
        data["verified"] = verified
        data["verify_error"] = verify_error
        data["behavior"] = behavior.to_json() if behavior is not None else None
        data["capture"] = capture.to_json() if capture is not None else None
        data["group_analysis"] = group_analysis.to_json() if group_analysis is not None else None
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_show(
            summary,
            verified=verified if args.verify else None,
            verify_error=verify_error,
            behavior=behavior,
            capture=capture,
            group_analysis=group_analysis,
        )

    if args.verify and not verified:
        return 1
    return 0


def _print_experimental_conditions(summary) -> None:
    """v3 Phase 0D/0E/Phase 2: disclose non-default or experimental conditions.

    These became controllable experimental variables in Phase 0
    (docs/V3_PHASE0_RESEARCH_BASELINE.md), so an artifact read back without
    them cannot be told apart from a default-conditions one -- exactly the
    "omission would be misleading" case. Mirrors the live `agents evaluate`
    CLI's own conditional disclosure: nothing is printed at defaults, so
    every historical artifact's `show` output is unchanged.

    Reads the artifact's own recorded `effective_conditions`, never a
    recomputed default, and stays silent when that field is UNKNOWN rather
    than implying a value the artifact never recorded.
    """

    if summary.effective_conditions.confidence == FieldConfidence.UNKNOWN:
        return
    conditions = summary.effective_conditions.value
    if not isinstance(conditions, dict):
        return
    defaults = Config()
    arena_size = conditions.get("arena_size")
    action_budget = conditions.get("action_budget")
    confidence = summary.effective_conditions.confidence.value
    if isinstance(arena_size, int) and arena_size != defaults.arena_size:
        print(f"arena size: {arena_size} (non-default) ({confidence})")
    if isinstance(action_budget, int) and action_budget != defaults.instr_per_tick:
        print(f"action budget/tick: {action_budget} (non-default) ({confidence})")
    # v3 Phase 3: `weights` has always been a recorded key of
    # `effective_conditions`; only its `kill` entry becomes variable here.
    weights = conditions.get("weights")
    if isinstance(weights, dict):
        kill_weight = weights.get("kill")
        if isinstance(kill_weight, (int, float)) and kill_weight != defaults.weights.kill:
            print(f"kill weight: {kill_weight} (non-default) ({confidence})")
    # v3 Phase 2: recorded only by an experimental bounded-locality
    # evaluation, so its mere presence is the disclosure -- there is no
    # "default" reach to compare against, and no non-locality artifact
    # carries the key at all.
    locality_reach = conditions.get("locality_reach")
    if isinstance(locality_reach, int):
        print(
            f"locality reach: {locality_reach} (EXPERIMENTAL bounded locality) "
            f"({confidence})"
        )


def _print_show(
    summary, *, verified: bool | None, verify_error: str | None, behavior=None, capture=None, group_analysis=None
) -> None:
    print(f"evaluation_id: {summary.evaluation_id}")
    print(f"schema: {summary.schema.schema} v{summary.schema.schema_version}")
    print(f"path: {summary.location.evaluation_json_path}")
    print(f"candidate: {summary.candidate_id}  baseline: {summary.baseline_id or 'none'}")
    print(f"opponents: {', '.join(summary.opponent_ids)}")
    print(f"seeds: {', '.join(str(s) for s in summary.seeds)}  ticks: {summary.ticks}")
    _print_experimental_conditions(summary)
    print(
        f"lifecycle: {summary.lifecycle_state.value} ({summary.lifecycle_state.confidence.value})  "
        f"created_at: {summary.created_at.value or 'unknown'}  "
        f"finished_at: {summary.finished_at.value or 'unknown'}"
    )
    print(
        f"rules_compatibility_id: {summary.rules_compatibility_id.value or 'unknown'} "
        f"({summary.rules_compatibility_id.confidence.value})"
    )
    # v0.9 Phase 6 (Phase 5 spec Sec O.2/AA.5): same shared methodology
    # lines the live `agents evaluate` CLI prints, alongside each field's
    # own recorded/recovered confidence so a reader can tell a fresh
    # schema-4 evaluation's disclosure from a pre-v0.9 artifact's certain
    # recovery.
    orientation_mode_value = summary.orientation_mode.value or ORIENTATION_MODE_CANDIDATE_FIRST_ONLY
    arena_alignment_value = summary.arena_alignment_mode.value or resolved_arena_alignment_mode(False)
    # v2.0.0-beta2 Phase 2 (design-audit finding): the 2-value "Entrant
    # orientation: both/candidate-first only" line describes 1v1
    # methodology's own axis -- meaningless, and potentially misleading,
    # for a group artifact, whose scheduler-order axis is the N!-seat
    # permutation instead (already disclosed separately, above).
    orientation_line, alignment_line = methodology_lines(
        orientation_mode_value, arena_alignment_mode=arena_alignment_value
    )
    if summary.group.value is not True:
        print(orientation_line)
    print(alignment_line)
    print(
        f"  orientation_mode: {orientation_mode_value} ({summary.orientation_mode.confidence.value})  "
        f"arena_alignment_mode: {summary.arena_alignment_mode.value or 'unknown'} "
        f"({summary.arena_alignment_mode.confidence.value})"
    )
    if summary.group.value is True:
        # v2.0.0-beta2 Phase 2 (Sec Show): roster/layout/seat-assignment
        # disclosure for a multi-entrant artifact -- derived from the
        # cells themselves, mirroring the placement disclosure below's own
        # "never re-stated as a separate drift-prone field" discipline.
        roster_values = summary.roster_agent_ids.value or ()
        layout_values = sorted({cell.layout_id.value for cell in summary.cells if cell.layout_id.value})
        seat_values = {tuple(cell.seat_agent_ids.value) for cell in summary.cells if cell.seat_agent_ids.value}
        print(f"roster: {', '.join(roster_values)} ({len(roster_values)} entrants)")
        print(f"layouts: {', '.join(layout_values)} ({len(layout_values)})")
        print(f"seat assignments: {len(seat_values)}")
    else:
        # v2.0.0-beta2 Phase 1 (Sec Show): the distinct placement ids
        # actually observed across this artifact's own cells -- derived
        # from the cells themselves, never re-stated as a separate stored
        # summary field, so it can never drift from what the cells
        # actually recorded.
        placement_values = sorted(
            {cell.placement.value for cell in summary.cells if cell.placement.value is not None}
        )
        if placement_values:
            print(f"placements: {', '.join(placement_values)} ({len(placement_values)})")
    codes = ", ".join(code.value for code in summary.health.codes) or "unknown"
    print(f"health: {codes}")
    for detail in summary.health.detail:
        print(f"  - {detail}")
    print(f"matrix: {len(summary.cells)}/{summary.matrix_size} cells")
    status_counts: dict[str, int] = {}
    for cell in summary.cells:
        status_counts[cell.status] = status_counts.get(cell.status, 0) + 1
    print("cell status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
    # v0.9 Phase 6 (Sec O.2/K.2): pooled ("all") row per subject, plus a
    # per-orientation win-rate breakdown line when the recomputed cells
    # actually cover more than one orientation.
    for aggregate in summary.aggregates_recomputed:
        if aggregate.orientation_scope != "all":
            continue
        roster_values = summary.roster_agent_ids.value or ()
        if summary.group.value is True and roster_values.count(aggregate.subject_id) > 1:
            print(f"[{aggregate.subject_role}] {aggregate.subject_id}")
            print(
                "    legacy candidate outcome aggregate: suppressed because this logical "
                "agent occupies multiple physical seats"
            )
            continue
        print(f"[{aggregate.subject_role}] {aggregate.subject_id}  win_rate={aggregate.win_rate_display}")
        candidate_first = next(
            (
                a
                for a in summary.aggregates_recomputed
                if a.subject_role == aggregate.subject_role
                and a.subject_id == aggregate.subject_id
                and a.orientation_scope == "candidate_first"
            ),
            None,
        )
        opponent_first = next(
            (
                a
                for a in summary.aggregates_recomputed
                if a.subject_role == aggregate.subject_role
                and a.subject_id == aggregate.subject_id
                and a.orientation_scope == "opponent_first"
            ),
            None,
        )
        if opponent_first is not None and opponent_first.matches_played > 0:
            print(
                f"    candidate_first: {candidate_first.win_rate_display if candidate_first else 'n/a'}   "
                f"opponent_first: {opponent_first.win_rate_display}"
            )
    _print_analysis(summary)
    if behavior is not None:
        _print_behavior(behavior)
    if capture is not None:
        _print_capture_history(capture)
    if group_analysis is not None:
        _print_group_analysis_history(summary.candidate_id, group_analysis)
    _print_execution_contexts(summary)
    _print_agent_revisions(summary)
    if verified is not None:
        print(f"verified: {verified}" + (f"  ({verify_error})" if verify_error else ""))


def _rate_estimate_line(label: str, estimate) -> str:
    interval = estimate.win_interval
    pct = 100.0 * (estimate.observed_win_rate or 0.0)
    if interval is None:
        return f"  {label}: {estimate.wins}/{estimate.matches_played} (insufficient data)"
    return (
        f"  {label}: {estimate.wins}/{estimate.matches_played} ({pct:.0f}%)  "
        f"{round(interval.confidence_level * 100)}% CI "
        f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]"
    )


def _paired_evidence_line(entry) -> str:
    if entry.state == EvidenceState.NO_MATCHED_CONDITIONS:
        return "no matched conditions"
    if entry.state == EvidenceState.NO_DISCORDANT_PAIRS:
        return f"{entry.paired_count} matched, no discordant pairs -- interval/exact test not meaningful"
    interval = entry.better_interval
    assert interval is not None and entry.exact_p_value is not None
    return (
        f"better {entry.improved}/{entry.discordant} discordant "
        f"({100.0 * (entry.better_proportion_of_discordant or 0.0):.0f}%)  "
        f"{round(interval.confidence_level * 100)}% CI "
        f"[{100.0 * interval.lower:.0f}%, {100.0 * interval.upper:.0f}%]  "
        f"exact two-sided p={entry.exact_p_value:.3g}"
    )


def _print_analysis(summary) -> None:
    """v1.6 Phase 4 (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md Sec 13): the
    full by-opponent/by-orientation breakdown -- deeper detail than the
    live ``agents evaluate`` CLI's concise ``evidence:`` block (Sec 12),
    appropriate here since ``evaluations show`` is already the "drill
    deeper" workflow. Derived entirely from ``EvaluationSummary.analysis``
    (Sec 11) -- no statistics computed in this presentation function.
    """

    analysis = summary.analysis
    if analysis is None:
        return
    print("analysis:")
    print(_rate_estimate_line(f"candidate overall ({analysis.candidate_id})", analysis.candidate_overall))
    if analysis.baseline_overall is not None:
        print(_rate_estimate_line(f"baseline overall ({analysis.baseline_id})", analysis.baseline_overall))
    paired = analysis.overall_paired
    if paired is None:
        return
    print(f"  paired overall: {_paired_evidence_line(paired)}")
    print(f"  opponent consistency: {analysis.opponent_consistency}")
    for entry in analysis.by_opponent:
        print(f"    opponent={entry.scope_label}: {_paired_evidence_line(entry)}")
    print(f"  orientation consistency: {analysis.orientation_consistency}")
    for entry in analysis.by_orientation:
        print(f"    orientation={entry.scope_label}: {_paired_evidence_line(entry)}")


def _fmt_fraction_pct(value: float | None) -> str:
    return f"{100.0 * value:.0f}%" if value is not None else "n/a"


def _fmt_percent(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "n/a"


def _fmt_rate(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _behavior_profile_line(label: str, profile: BehaviorProfile) -> str:
    if profile.sample_count == 0:
        return f"  {label}: insufficient data (0 scored cells)"
    survival = profile.dimension("survival_fraction")
    writes = profile.dimension("writes_per_tick")
    last = profile.dimension("territory_last_pct")
    peak = profile.dimension("territory_max_pct")
    avg = profile.dimension("territory_avg_pct")
    retention = profile.dimension("territory_retention")
    kills = profile.dimension("kills_per_match")
    deaths = profile.dimension("deaths_per_match")
    return (
        f"  {label}: survival={_fmt_fraction_pct(survival.mean)} (n={survival.n})  "
        f"writes/tick={_fmt_rate(writes.mean)}  "
        f"territory[last={_fmt_percent(last.mean)} peak={_fmt_percent(peak.mean)} "
        f"avg={_fmt_percent(avg.mean)} retention={_fmt_fraction_pct(retention.mean)}]  "
        f"kills={_fmt_rate(kills.mean)}/match deaths={_fmt_rate(deaths.mean)}/match"
    )


def _fmt_capture_pct(value: float | None) -> str:
    return f"{100.0 * value:.0f}%" if value is not None else "n/a"


def _print_capture_aggregate(label: str, aggregate) -> None:
    print(f"  {label}: caused={aggregate.captures_caused}/{aggregate.available_count} "
          f"({_fmt_capture_pct(aggregate.capture_rate_caused)})  "
          f"suffered={aggregate.captures_suffered}/{aggregate.available_count} "
          f"({_fmt_capture_pct(aggregate.capture_rate_suffered)})  "
          f"survival={_fmt_capture_pct(aggregate.survival_rate)}")
    if aggregate.capture_ticks:
        print(f"    capture tick: mean={aggregate.mean_capture_tick:.1f} median={aggregate.median_capture_tick:.1f}")


def _print_capture_history(capture) -> None:
    """v2.0.0-beta2 Phase 1 (Sec Show): capture/core evidence, kept in its
    own section -- never merged into ``analysis:``/``behavior:`` above
    (Phase 1M: capture is distinct from both win/loss and behavior).
    """

    print("capture/core evidence:")
    _print_capture_aggregate(f"candidate ({capture.candidate_id})", capture.candidate_overall)
    if capture.baseline_overall is not None:
        _print_capture_aggregate(f"baseline ({capture.baseline_id})", capture.baseline_overall)


def _fmt_group_rate(stat) -> str:
    if stat.trials == 0:
        return "n/a"
    return f"{stat.successes}/{stat.trials} ({100.0 * (stat.rate or 0.0):.0f}%)"


def _print_entrant_summary_row(label: str, summary) -> None:
    print(f"  {label}:")
    print(
        f"    winner: {_fmt_group_rate(summary.winner)}   survival: {_fmt_group_rate(summary.survival)}   "
        f"eliminated: {_fmt_group_rate(summary.elimination)}"
    )
    if summary.score.n:
        print(f"    score: mean={summary.score.mean:.2f} (n={summary.score.n})")
    if summary.capture_suffered.trials or summary.capture_caused.trials:
        print(
            f"    captured: {_fmt_group_rate(summary.capture_suffered)}   "
            f"caused: {_fmt_group_rate(summary.capture_caused)}"
        )


def _print_group_analysis_history(candidate_id: str, analysis) -> None:
    """v2.0.0-beta2 Phase 3 (Sec 24): the ``evaluations show`` counterpart
    to ``agent_evaluation._print_group_analysis`` -- unlike the live-run
    CLI's candidate-focused presentation, this is the "drill deeper"
    workflow, so every roster entrant's own summary is shown (mirrors
    ``_print_analysis``/``_print_behavior``'s identical "show everything
    here" precedent), not only the candidate's.
    """

    print("group analysis:")
    print(f"  cells analyzed: {analysis.available_cells}/{analysis.cells_analyzed}")
    candidate_multiplicity = analysis.roster_multiplicity.get(candidate_id, 0)
    if candidate_multiplicity > 1:
        print(
            "  candidate logical outcome: ambiguous in legacy cell summaries; "
            f"{candidate_multiplicity} physical candidate instances occupy each cell"
        )
        print("  rates below use physical entrant instances as their denominator")
    print("  entrant summary:")
    for entrant in analysis.entrant_summaries:
        marker = " (candidate)" if entrant.agent_id == candidate_id else ""
        if analysis.roster_multiplicity.get(entrant.agent_id, 0) > 1:
            marker += " [per physical entrant instance]"
        _print_entrant_summary_row(f"{entrant.agent_id}{marker}", entrant)
    for seat_view in analysis.seat_sensitivity:
        if seat_view.winner_rate_range is None:
            continue
        by_seat = ", ".join(f"{s.scope_label}={_fmt_group_rate(s.winner)}" for s in seat_view.by_seat)
        print(
            f"  seat sensitivity [{seat_view.agent_id}]: {by_seat}  "
            f"(winner-rate range {100.0 * seat_view.winner_rate_range:.0f} pp)"
        )
    for layout_view in analysis.layout_sensitivity:
        if layout_view.winner_rate_range is None:
            continue
        by_layout = ", ".join(f"{s.scope_label}={_fmt_group_rate(s.winner)}" for s in layout_view.by_layout)
        print(
            f"  layout sensitivity [{layout_view.agent_id}]: {by_layout}  "
            f"(winner-rate range {100.0 * layout_view.winner_rate_range:.0f} pp)"
        )
    matrix = analysis.interaction_matrix
    if matrix.pairs or matrix.unattributed_captures:
        print("  captures (captor -> victim):")
        for pair in matrix.pairs:
            print(
                f"    {pair.captor_agent_id} -> {pair.victim_agent_id}: {pair.count} "
                f"({100.0 * (pair.rate or 0.0):.0f}%)"
            )
        if matrix.unattributed_captures:
            print(f"    unattributed: {matrix.unattributed_captures}")


def _print_behavior(behavior) -> None:
    """v1.6 Phase 5 (docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md Sec 18): the full
    by-opponent/by-orientation behavior breakdown, appropriate here since
    ``evaluations show`` is already the "drill deeper" workflow (mirrors
    ``_print_analysis``'s own precedent, Sec 13). Derived entirely from an
    already-computed ``evaluation_behavior.BehaviorAnalysis`` -- no
    behavioral measurement happens in this presentation function. Kept in
    a section of its own, never merged into ``analysis:`` above --
    behavior (how the candidate played) and analysis (whether it won) stay
    conceptually and visually separate (Sec 6/26 of the design doc).
    """

    print("behavior:")
    print(_behavior_profile_line(f"candidate overall ({behavior.candidate_id})", behavior.candidate_overall))
    if behavior.baseline_overall is not None:
        print(_behavior_profile_line(f"baseline overall ({behavior.baseline_id})", behavior.baseline_overall))
    if behavior.candidate_vs_baseline_largest:
        print(
            "  largest candidate-vs-baseline differences: "
            + ", ".join(behavior.candidate_vs_baseline_largest)
        )
    orientation_labels = {"candidate_first": "candidate_first", "opponent_first": "opponent_first"}
    print("  candidate by orientation:")
    for profile in behavior.candidate_by_orientation:
        print(_behavior_profile_line(f"  {orientation_labels.get(profile.scope_label, profile.scope_label)}", profile))
    if behavior.candidate_by_opponent:
        print("  candidate by opponent:")
        for profile in behavior.candidate_by_opponent:
            print(_behavior_profile_line(f"  {profile.scope_label}", profile))


def _print_agent_revisions(summary) -> None:
    """Sec 5.4/7.2: durable revision provenance next to each role, when
    present -- ``unknown`` (v1/v2 artifacts, or a v3 artifact that never
    recorded one for this role) is shown explicitly, never silently
    omitted. Verification status (``[invalid]``/``[not_available]``/
    ``[verified]``) is only shown once ``--verify`` has actually populated
    it; plain ``show`` never claims local-store evidence it didn't check.
    """

    def _line(label: str, revision_id_cv, error_cv, status) -> None:
        if not revision_id_cv.value:
            print(f"  {label}: unknown")
            return
        line = f"  {label}: {revision_id_cv.value}"
        if error_cv.value:
            line += f"  ARCHIVE ERROR: {error_cv.value}"
        if status.value != "not_checked":
            line += f"  [{status.value}]"
        print(line)

    print("agent revisions:")
    _line(
        "candidate",
        summary.candidate_agent_revision_id,
        summary.candidate_agent_revision_error,
        summary.candidate_revision_verification,
    )
    if summary.baseline_id is not None:
        _line(
            "baseline",
            summary.baseline_agent_revision_id,
            summary.baseline_agent_revision_error,
            summary.baseline_revision_verification,
        )
    seen_opponents = {}
    for cell in summary.cells:
        if cell.opponent_id not in seen_opponents:
            seen_opponents[cell.opponent_id] = cell
    for opponent_id, cell in seen_opponents.items():
        _line(
            f"opponent:{opponent_id}",
            cell.opponent_agent_revision_id,
            cell.opponent_agent_revision_error,
            cell.opponent_revision_verification,
        )


def _print_execution_contexts(summary) -> None:
    """H2: surface execution provenance -- which runtime(s) actually ran the
    matrix, and whether cells are split across more than one."""

    if not summary.execution_contexts:
        print("execution contexts: none recorded (legacy/v1 artifact)")
        return
    used_ids = {
        cell.execution_context_id.value
        for cell in summary.cells
        if cell.execution_context_id.value is not None
    }
    print(f"execution contexts: {len(summary.execution_contexts)} recorded, {len(used_ids)} used by cells")
    for context in summary.execution_contexts:
        marker = "*" if context.get("context_id") in used_ids else " "
        print(
            f"  {marker} {context.get('context_id')}: bytefray={context.get('bytefray_version')} "
            f"python={context.get('python_version')} agent_api={context.get('agent_api_version')} "
            f"rules={context.get('rules_compatibility_id')}"
        )
    if len(used_ids) > 1:
        print("  MIXED EXECUTION CONTEXTS: this evaluation's cells did not all run under the same runtime.")


def _verify_side(summary):
    """Deep-verify one side of a comparison; returns (summary, error-or-None).

    Shared by both sides of ``compare --verify`` -- the same "no vacuous
    verified=true for zero eligible cells" rule ``show --verify`` applies
    (B3/Sec 15).
    """

    summary, verification = verify_summary(summary)
    if verification.failed:
        first = verification.failed[0]
        return summary, f"{first.schedule_id}: {first.error}"
    if verification.revision_issues:
        return summary, verification.revision_issues[0]
    if verification.eligible_count == 0:
        return summary, "no eligible (completed/scored) cells to verify"
    return summary, None


def _cmd_compare(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.root or [])]
    try:
        left_path = resolve_selector(args.left, roots=roots)
        right_path = resolve_selector(args.right, roots=roots)
    except (AmbiguousSelectorError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        left = adapt_any(left_path)
        right = adapt_any(right_path)
    except ArtifactReadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    left_verify_error: str | None = None
    right_verify_error: str | None = None
    if args.verify:
        left, left_verify_error = _verify_side(left)
        right, right_verify_error = _verify_side(right)

    result = align(left, right, deep_verified=bool(args.verify))
    # B3: `align()`'s own `deep_verified` reflects "--verify was requested"
    # (which is also what drives its internal per-pair verified-evidence
    # gating, independent of whether some *other* cell elsewhere failed to
    # verify) -- but the claim surfaced to a caller/consumer here must be
    # narrower: true only when verification was requested *and* actually
    # succeeded on both sides. A side that failed (or had zero eligible
    # cells) must never be reported as deep-verified.
    fully_verified = bool(args.verify) and left_verify_error is None and right_verify_error is None

    # v1.6 Phase 4 (docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md Sec 13):
    # deliberately shallower than `show`'s per-opponent/per-orientation
    # breakdown -- `compare` operates across two independently-evaluated
    # artifacts, over only the already-aligned `result.rows`, using the
    # identical "improved"/"regressed"/"unchanged"/"inconclusive"
    # vocabulary `ComparisonRow.verdict` already produces (`comparison.py`'s
    # `verdict()` is documented as the same mapping as
    # `agent_evaluation.classify`). Every already-disclosed
    # `unmatched_left`/`unmatched_right`/`changed_condition`/
    # `ambiguous_duplicate_groups` limitation is unchanged by this.
    evidence = paired_evidence_from_verdicts("compare", [row.verdict for row in result.rows])

    if args.json:
        data = result.to_json()
        data["deep_verified"] = fully_verified
        data["left_verify_error"] = left_verify_error
        data["right_verify_error"] = right_verify_error
        data["statistical_evidence"] = evidence.to_json()
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_compare(left, right, result, left_verify_error, right_verify_error, fully_verified)
        print(f"statistical evidence: {_paired_evidence_line(evidence)}")

    if args.verify and (left_verify_error is not None or right_verify_error is not None):
        return 1
    if result.denominators.directly_comparable == 0 and not result.rows:
        return 1
    return 0


def _print_compare(
    left, right, result, left_verify_error=None, right_verify_error=None, fully_verified=None
) -> None:
    print(f"orientation: {result.orientation}")
    print(f"left:  {left.evaluation_id}  candidate={left.candidate_id}")
    print(f"right: {right.evaluation_id}  candidate={right.candidate_id}")
    if fully_verified is None:
        fully_verified = result.deep_verified and left_verify_error is None and right_verify_error is None
    if fully_verified:
        print("evidence: deep-verified (--verify)")
    elif result.deep_verified:
        # B3: --verify was requested but failed on at least one side --
        # never claim "deep-verified" for this comparison's evidence.
        print(
            "evidence: NOT deep-verified -- verification failed"
            + ("" if left_verify_error is None else f"  LEFT FAILED: {left_verify_error}")
            + ("" if right_verify_error is None else f"  RIGHT FAILED: {right_verify_error}")
        )
    else:
        print(
            "evidence: NOT deep-verified -- read and recomputed from each artifact's own "
            "recorded fields only; pass --verify to cross-check nested result/replay artifacts"
        )
    if result.candidate_changed:
        print("candidate identity: DIFFERENT CANDIDATES (logical id changed)")
    elif result.candidate_diff:
        print(f"candidate identity changed: {result.candidate_diff}")
    else:
        print("candidate identity: unchanged (or unknown on one side)")
    baseline = result.baseline_context
    print(f"baseline: {baseline.identity_status}")
    if baseline.control_anomaly:
        print("  ANOMALY: identical baseline produced different outcomes under identical conditions")
    d = result.denominators
    print(
        f"comparable: {d.directly_comparable}  improved={d.improved} regressed={d.regressed} "
        f"unchanged={d.unchanged} inconclusive={d.inconclusive}"
    )
    print(
        f"unmatched: left={d.unmatched_left} right={d.unmatched_right}  "
        f"changed_condition={d.changed_condition}  "
        f"ambiguous_duplicate_groups={d.ambiguous_duplicate_groups}  "
        f"corrupt_or_missing={d.corrupt_or_missing}"
    )
    if result.reproducibility_anomalies:
        print("REPRODUCIBILITY ANOMALIES (deep-verified identical candidate, differing outcome):")
        for row in result.reproducibility_anomalies:
            print(f"  opponent={row.opponent_id} seed={row.seed} left={row.left_outcome} right={row.right_outcome}")
    for row in result.rows:
        if row.verdict in ("improved", "regressed"):
            print(f"  {row.verdict}: opponent={row.opponent_id} seed={row.seed} left={row.left_outcome} right={row.right_outcome}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bytefray agents evaluations")
    sub = parser.add_subparsers(dest="verb", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--root", action="append", default=None)
    list_parser.add_argument("--artifact", action="append", default=None)
    list_parser.add_argument("--json", action="store_true")

    show_parser = sub.add_parser("show")
    show_parser.add_argument("selector")
    show_parser.add_argument("--root", action="append", default=None)
    show_parser.add_argument("--verify", action="store_true")
    show_parser.add_argument("--json", action="store_true")
    show_parser.add_argument(
        "--no-behavior",
        action="store_true",
        help=(
            "skip the v1.6 Phase 5 behavior-profile section (on by default) -- "
            "each scored cell's own result.json is read once (~5-6ms/cell "
            "measured), which adds up on a stress-scale (thousands-of-cells) "
            "artifact; never affects 'evaluations list', which never reads "
            "per-cell result.json regardless of this flag."
        ),
    )

    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("left")
    compare_parser.add_argument("right")
    compare_parser.add_argument("--root", action="append", default=None)
    compare_parser.add_argument("--verify", action="store_true")
    compare_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verb == "list":
        return _cmd_list(args)
    if args.verb == "show":
        return _cmd_show(args)
    if args.verb == "compare":
        return _cmd_compare(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
