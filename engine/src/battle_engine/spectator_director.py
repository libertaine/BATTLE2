"""Deterministic spectator playback pacing ("Director") over derived events.

Phase 7 research infrastructure, not a public spectator API. This module
answers a narrower question than :mod:`battle_engine.spectator_derivation`:
given a stream of already-qualified factual events, *when should the viewer
be shown a tick, and how long should the viewer remain on it* -- never *what
happened* or *what an entrant knows*. It consumes a
:class:`~battle_engine.spectator_derivation.SpectatorDerivation` that the
caller has already produced (via :func:`battle_engine.spectator_derivation.
analyze_pair` or equivalent); it never re-verifies a pair or re-derives
events itself, so building a Director plan costs nothing beyond one pass over
an already-computed event tuple.

Two information domains
------------------------
A :class:`DirectorMode` selects which events the Director's decision state
machine is even allowed to see:

- ``BROADCAST`` uses the full derivation event stream, including the eight
  omniscient-only kinds (see ``_OMNISCIENT_ONLY`` in
  :mod:`battle_engine.spectator_derivation`) that no entrant is ever told
  about.
- ``PERSPECTIVE`` (bound to one entrant) uses **only** the subset of that
  same stream whose ``visible_to`` already names that entrant. This reuses
  Phase 3's own audience computation rather than inventing a second one:
  ``visible_to`` already encodes exactly what the v4 engine told that
  entrant (its own detections, its own hostile reads, its own process
  moves), and never includes an omniscient-only fact. Filtering the input
  *before* the pacing state machine ever runs -- rather than computing a
  Broadcast decision first and relabelling it -- is what makes a Perspective
  Director's timing provably incapable of reacting to a hidden fact: the
  fact is never in the list it iterates over.

The one deliberate exception is match termination. ``MATCH_ENDED``/
``VICTORY`` are always omniscient-only (Phase 3's own finding), so they can
never appear in a Perspective stream -- but by the time the *whole match* has
ended there is no more hidden gameplay left to protect, and the existing,
already-qualified renderer already shows the terminal banner identically in
Broadcast and every Perspective mode (Phase 6, Sec. 11 item 09). The Director
therefore schedules its terminal hold from
:attr:`~battle_engine.spectator_derivation.SpectatorDerivation.result_ticks`
-- a match-level fact on the derivation itself, not a per-entrant-filtered
event -- so both modes end on the same tick with the same hold, without the
Perspective state machine ever having to read an omniscient event kind.

What this module deliberately does not do
------------------------------------------
It does not touch wall-clock time. A :class:`DirectorPlan` is a pure
function of ``(derivation, mode, entrant_id, config)`` -- the same inputs
always produce byte-identical decisions, and nothing about *how long a hold
actually waits in real seconds* lives here (that is
``battle_client.director.PlaybackDirectorRuntime``'s job, deliberately kept
on the client side because it consumes an injectable clock). It never looks
past the tick it is deciding: every tracker used to choose a tick's state is
updated using only events at or before that tick, so a decision at tick N is
never a function of anything that happens at tick N+1 or later -- the sole
exception, again, is the terminal-hold override, which uses
``result_ticks``, a fact already known for the *entire* match before tick 1
(the match either already happened or is being analyzed after the fact), and
which only ever changes the decision made *at* the terminal tick itself, not
any earlier one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from battle_engine.spectator_derivation import (
    SpectatorDerivation,
    SpectatorEvent,
    SpectatorEventKind,
    SpectatorPairError,
    analyze_pair,
)

DIRECTOR_SCHEMA = "bytefray.spectator_director"
DIRECTOR_SCHEMA_VERSION = 1


class DirectorError(ValueError):
    """A Director plan cannot be built from the given inputs."""


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class DirectorMode(str, Enum):
    """Which information domain a Director plan is allowed to consume."""

    BROADCAST = "broadcast"
    PERSPECTIVE = "perspective"


class DirectorPacingState(str, Enum):
    """The minimum pacing-state vocabulary the event corpus supports.

    Chosen over the ``BUILD_UP``/``SUSPENSE``/``BRAWL``/``IMPACT_HOLD``/
    ``NORMAL`` alternative because it names the causal role of each state
    (what triggers it, what it decays into) rather than a mood, which keeps
    the state machine's transition table self-documenting. See
    ``docs/research/v4/V4_SPECTATOR_PHASE_7_RESEARCH.md`` for the corpus
    evidence and the states considered and rejected.
    """

    CRUISE = "CRUISE"
    CONTACT = "CONTACT"
    ENGAGEMENT = "ENGAGEMENT"
    IMPACT_HOLD = "IMPACT_HOLD"
    RECOVERY = "RECOVERY"


class EventSignificance(Enum):
    """A small ordered priority tier over the Phase 3 event vocabulary."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    MAJOR = 4


class DirectorReason(str, Enum):
    """Factual, enumerable cause for a decision. Never free-text prose."""

    NO_SIGNIFICANT_ACTIVITY = "NO_SIGNIFICANT_ACTIVITY"
    CONTACT_SIGNAL = "CONTACT_SIGNAL"
    ENGAGEMENT_SIGNAL = "ENGAGEMENT_SIGNAL"
    SUSTAINED_CONTACT = "SUSTAINED_CONTACT"
    SUSTAINED_ENGAGEMENT = "SUSTAINED_ENGAGEMENT"
    MAJOR_EVENT_HOLD = "MAJOR_EVENT_HOLD"
    TERMINAL_HOLD = "TERMINAL_HOLD"
    RECOVERY_RAMP = "RECOVERY_RAMP"


#: Starting-hypothesis significance tiers (Phase 7 brief Sec. 14), validated
#: against the real corpus in the Phase 7 research document. Kept as a
#: module-level mapping (not baked into the enum) so :class:`DirectorConfig`
#: can override individual entries for research tuning without subclassing.
DEFAULT_SIGNIFICANCE: Mapping[SpectatorEventKind, EventSignificance] = {
    SpectatorEventKind.AGENT_ELIMINATED: EventSignificance.MAJOR,
    SpectatorEventKind.AGENT_FORFEITED: EventSignificance.MAJOR,
    SpectatorEventKind.VICTORY: EventSignificance.MAJOR,
    SpectatorEventKind.MATCH_ENDED: EventSignificance.MAJOR,
    SpectatorEventKind.PROCESS_DISRUPTED: EventSignificance.HIGH,
    SpectatorEventKind.CORE_CELL_LOST: EventSignificance.HIGH,
    SpectatorEventKind.FIRST_HOSTILE_WRITE: EventSignificance.HIGH,
    SpectatorEventKind.DETECTION_GAINED: EventSignificance.MEDIUM,
    SpectatorEventKind.FIRST_HOSTILE_READ: EventSignificance.MEDIUM,
    SpectatorEventKind.HOSTILE_WRITE: EventSignificance.MEDIUM,
    SpectatorEventKind.HOSTILE_READ: EventSignificance.LOW,
    SpectatorEventKind.DETECTION_LOST: EventSignificance.LOW,
    SpectatorEventKind.EFFECTIVE_MOVE: EventSignificance.LOW,
}


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DirectorConfig:
    """Research-tunable pacing parameters. See Phase 7 research doc Sec. 15.

    Rates are expressed in ticks-per-second (matching the unit the phase
    brief's own rate research uses); the runtime layer converts a rate to a
    ``PlaybackController.tick_interval`` (seconds-per-tick) by inversion.
    """

    cruise_rate_tps: float = 18.0
    contact_rate_tps: float = 3.0
    engagement_rate_tps: float = 6.0
    recovery_rate_tps: float = 10.0
    sustained_rate_tps: float = 12.0
    impact_hold_ms: int = 900
    contact_lookback_ticks: int = 8
    engagement_lookback_ticks: int = 6
    recovery_ticks: int = 5
    sustain_ticks_before_fatigue: int = 10
    significance_overrides: tuple[tuple[SpectatorEventKind, EventSignificance], ...] = ()

    def significance_for(self, kind: SpectatorEventKind) -> EventSignificance:
        for override_kind, override_significance in self.significance_overrides:
            if override_kind is kind:
                return override_significance
        return DEFAULT_SIGNIFICANCE.get(kind, EventSignificance.NONE)

    def fingerprint(self) -> tuple[object, ...]:
        """A stable, wall-clock-free identity for this configuration."""

        overrides = tuple(
            sorted(
                ((kind.value, sig.value) for kind, sig in self.significance_overrides)
            )
        )
        return (
            self.cruise_rate_tps,
            self.contact_rate_tps,
            self.engagement_rate_tps,
            self.recovery_rate_tps,
            self.sustained_rate_tps,
            self.impact_hold_ms,
            self.contact_lookback_ticks,
            self.engagement_lookback_ticks,
            self.recovery_ticks,
            self.sustain_ticks_before_fatigue,
            overrides,
        )


DEFAULT_DIRECTOR_CONFIG = DirectorConfig()


# --------------------------------------------------------------------------
# Decision model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DirectorDecision:
    """One tick's pacing decision, with enough evidence to audit it.

    ``source_events`` names the ``(tick, sequence)`` identities (see
    :class:`~battle_engine.spectator_derivation.SpectatorEvent`) of the
    event(s) that most recently justified the current state -- even during a
    lookback/recovery tail where no new qualifying event occurred at this
    exact tick, so a reviewer can always answer "why is playback still slow
    here" without re-deriving the state machine by hand.
    """

    tick: int
    state: DirectorPacingState
    rate_tps: float
    hold_ms: int
    reason: DirectorReason
    source_events: tuple[tuple[int, int], ...]
    visibility_basis: str
    boundary: bool


@dataclass(frozen=True)
class DirectorPlan:
    """A deterministic, dense per-tick pacing plan for one match/mode/entrant."""

    mode: DirectorMode
    entrant_id: str | None
    visibility_basis: str
    match_id: str
    replay_sha256: str
    config_fingerprint: tuple[object, ...]
    first_tick: int
    last_tick: int
    decisions: tuple[DirectorDecision, ...]

    def decision_for_tick(self, tick: int) -> DirectorDecision:
        if tick <= self.first_tick:
            return self.decisions[0]
        if tick >= self.last_tick:
            return self.decisions[-1]
        return self.decisions[tick - self.first_tick]

    def plan_fingerprint(self) -> str:
        """A stable identity hash excluding any wall-clock state.

        Two plans built from the same replay/trace pair, mode, entrant, and
        config produce the same fingerprint regardless of process, hash
        seed, or the traversal path used to request decisions (Phase 7 brief
        Sec. 28/35).
        """

        import hashlib

        payload = json.dumps(
            {
                "schema": DIRECTOR_SCHEMA,
                "schema_version": DIRECTOR_SCHEMA_VERSION,
                "mode": self.mode.value,
                "entrant_id": self.entrant_id,
                "visibility_basis": self.visibility_basis,
                "match_id": self.match_id,
                "replay_sha256": self.replay_sha256,
                "config_fingerprint": self.config_fingerprint,
                "decisions": [
                    (
                        decision.tick,
                        decision.state.value,
                        decision.rate_tps,
                        decision.hold_ms,
                        decision.reason.value,
                        list(decision.source_events),
                        decision.boundary,
                    )
                    for decision in self.decisions
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# Plan construction
# --------------------------------------------------------------------------


def _visible_stream(
    derivation: SpectatorDerivation, mode: DirectorMode, entrant_id: str | None
) -> tuple[SpectatorEvent, ...]:
    if mode is DirectorMode.BROADCAST:
        return derivation.events
    return tuple(event for event in derivation.events if entrant_id in event.visible_to)


def build_director_plan(
    derivation: SpectatorDerivation,
    *,
    mode: DirectorMode,
    entrant_id: str | None = None,
    config: DirectorConfig = DEFAULT_DIRECTOR_CONFIG,
) -> DirectorPlan:
    """Build a deterministic pacing plan from an already-derived event stream.

    Raises :class:`DirectorError` for an invalid mode/entrant combination.
    Never re-runs :func:`~battle_engine.spectator_derivation.verify_pair` or
    :func:`~battle_engine.spectator_derivation.derive_events` -- the caller
    is expected to have already produced ``derivation`` once and to reuse it
    across Broadcast and every entrant's Perspective plan.
    """

    if mode is DirectorMode.PERSPECTIVE:
        if entrant_id is None:
            raise DirectorError("perspective mode requires an entrant_id")
        if entrant_id not in derivation.binding.entrant_identities:
            raise DirectorError(
                f"entrant {entrant_id!r} is not named by this derivation's binding"
            )
        visibility_basis = f"perspective:{entrant_id}"
    else:
        if entrant_id is not None:
            raise DirectorError("broadcast mode does not accept an entrant_id")
        visibility_basis = "broadcast"

    stream = _visible_stream(derivation, mode, entrant_id)

    events_by_tick: dict[int, list[SpectatorEvent]] = {}
    for event in stream:
        events_by_tick.setdefault(event.tick, []).append(event)

    decisions: list[DirectorDecision] = []
    last_medium_tick: int | None = None
    last_medium_events: tuple[tuple[int, int], ...] = ()
    last_high_tick: int | None = None
    last_high_events: tuple[tuple[int, int], ...] = ()
    last_elevated_tick: int | None = None
    elevated_streak_start: int | None = None

    for tick in range(derivation.first_tick, derivation.last_tick + 1):
        events_here = events_by_tick.get(tick, ())
        major_events = tuple(
            (e.tick, e.sequence)
            for e in events_here
            if config.significance_for(e.kind) is EventSignificance.MAJOR
        )
        high_events = tuple(
            (e.tick, e.sequence)
            for e in events_here
            if config.significance_for(e.kind) is EventSignificance.HIGH
        )
        medium_events = tuple(
            (e.tick, e.sequence)
            for e in events_here
            if config.significance_for(e.kind) is EventSignificance.MEDIUM
        )

        if high_events:
            last_high_tick, last_high_events = tick, high_events
        if medium_events:
            last_medium_tick, last_medium_events = tick, medium_events

        if major_events:
            state = DirectorPacingState.IMPACT_HOLD
            rate = config.recovery_rate_tps
            hold_ms = config.impact_hold_ms
            reason = DirectorReason.MAJOR_EVENT_HOLD
            source = major_events
            last_elevated_tick = tick
        elif last_high_tick is not None and tick - last_high_tick <= config.engagement_lookback_ticks:
            state = DirectorPacingState.ENGAGEMENT
            rate = config.engagement_rate_tps
            hold_ms = 0
            reason = DirectorReason.ENGAGEMENT_SIGNAL
            source = last_high_events
            last_elevated_tick = tick
        elif last_medium_tick is not None and tick - last_medium_tick <= config.contact_lookback_ticks:
            state = DirectorPacingState.CONTACT
            rate = config.contact_rate_tps
            hold_ms = 0
            reason = DirectorReason.CONTACT_SIGNAL
            source = last_medium_events
            last_elevated_tick = tick
        elif last_elevated_tick is not None and tick - last_elevated_tick <= config.recovery_ticks:
            state = DirectorPacingState.RECOVERY
            rate = config.recovery_rate_tps
            hold_ms = 0
            reason = DirectorReason.RECOVERY_RAMP
            source = last_high_events or last_medium_events
        else:
            state = DirectorPacingState.CRUISE
            rate = config.cruise_rate_tps
            hold_ms = 0
            reason = DirectorReason.NO_SIGNIFICANT_ACTIVITY
            source = ()

        # Sustained-activity fatigue: repeated MEDIUM/HIGH events across many
        # consecutive ticks (a long detection-oscillation duel, an ongoing
        # pin-down) must not keep the match at CONTACT's or ENGAGEMENT's slow
        # rate indefinitely -- corpus measurement (Phase 7 research doc Sec.
        # 16) showed a match spending 96% of its length continuously
        # re-triggering CONTACT inflated total playback to ~6x flat duration,
        # exactly the "five-minute slog" the phase brief warns against. Once
        # a state has held continuously (through CONTACT/ENGAGEMENT/
        # IMPACT_HOLD, without dropping to RECOVERY or CRUISE) for more than
        # `sustain_ticks_before_fatigue` ticks, a still-elevated CONTACT or
        # ENGAGEMENT tick ramps to `sustained_rate_tps` -- still visibly
        # slower than CRUISE (this is still real, ongoing action) but no
        # longer compounding into an ever-longer runtime for a fact the
        # viewer has already been shown many times over.
        if state in (DirectorPacingState.CONTACT, DirectorPacingState.ENGAGEMENT):
            if elevated_streak_start is None:
                elevated_streak_start = tick
            elif tick - elevated_streak_start >= config.sustain_ticks_before_fatigue:
                rate = config.sustained_rate_tps
                reason = (
                    DirectorReason.SUSTAINED_CONTACT
                    if state is DirectorPacingState.CONTACT
                    else DirectorReason.SUSTAINED_ENGAGEMENT
                )
        elif state is DirectorPacingState.IMPACT_HOLD:
            if elevated_streak_start is None:
                elevated_streak_start = tick
        else:
            elevated_streak_start = None

        decisions.append(
            DirectorDecision(
                tick=tick,
                state=state,
                rate_tps=rate,
                hold_ms=hold_ms,
                reason=reason,
                source_events=source,
                visibility_basis=visibility_basis,
                boundary=False,
            )
        )

    # Terminal override: a mode-independent hold at the match's own result
    # tick, driven by derivation-level metadata rather than any (possibly
    # omniscient-only, possibly absent-from-Perspective's-stream) event.
    if decisions and derivation.first_tick <= derivation.result_ticks <= derivation.last_tick:
        terminal_index = derivation.result_ticks - derivation.first_tick
        terminal = decisions[terminal_index]
        if terminal.state is not DirectorPacingState.IMPACT_HOLD:
            decisions[terminal_index] = DirectorDecision(
                tick=terminal.tick,
                state=DirectorPacingState.IMPACT_HOLD,
                rate_tps=config.recovery_rate_tps,
                hold_ms=config.impact_hold_ms,
                reason=DirectorReason.TERMINAL_HOLD,
                source_events=(),
                visibility_basis=visibility_basis,
                boundary=False,
            )

    # Boundary flags: mark ticks whose (state, rate, hold) differ from the
    # immediately preceding tick, so --explain output (and any diagnostic
    # overlay) can show only the moments pacing actually changed.
    finalized: list[DirectorDecision] = []
    previous: DirectorDecision | None = None
    for decision in decisions:
        is_boundary = previous is None or (
            decision.state != previous.state
            or decision.rate_tps != previous.rate_tps
            or decision.hold_ms != previous.hold_ms
        )
        if is_boundary != decision.boundary:
            decision = DirectorDecision(
                tick=decision.tick,
                state=decision.state,
                rate_tps=decision.rate_tps,
                hold_ms=decision.hold_ms,
                reason=decision.reason,
                source_events=decision.source_events,
                visibility_basis=decision.visibility_basis,
                boundary=is_boundary,
            )
        finalized.append(decision)
        previous = decision

    return DirectorPlan(
        mode=mode,
        entrant_id=entrant_id,
        visibility_basis=visibility_basis,
        match_id=derivation.binding.match_id,
        replay_sha256=derivation.binding.replay_sha256,
        config_fingerprint=config.fingerprint(),
        first_tick=derivation.first_tick,
        last_tick=derivation.last_tick,
        decisions=tuple(finalized),
    )


def build_director_plan_from_pair(
    replay_path: str | Path,
    trace_path: str | Path,
    *,
    mode: DirectorMode,
    entrant_id: str | None = None,
    config: DirectorConfig = DEFAULT_DIRECTOR_CONFIG,
) -> DirectorPlan:
    """Convenience one-call entry point mirroring ``analyze_pair``.

    Prefer :func:`build_director_plan` with an already-computed
    :class:`~battle_engine.spectator_derivation.SpectatorDerivation` when a
    caller (such as a client-side manager) already holds one -- this
    function exists for the standalone research CLI, which has nothing to
    share the derivation with.
    """

    derivation = analyze_pair(replay_path, trace_path)
    return build_director_plan(derivation, mode=mode, entrant_id=entrant_id, config=config)


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def decision_to_dict(decision: DirectorDecision) -> dict[str, object]:
    return {
        "tick": decision.tick,
        "state": decision.state.value,
        "rate_tps": decision.rate_tps,
        "hold_ms": decision.hold_ms,
        "reason": decision.reason.value,
        "source_events": [list(pair) for pair in decision.source_events],
        "visibility_basis": decision.visibility_basis,
        "boundary": decision.boundary,
    }


def plan_records(plan: DirectorPlan) -> tuple[dict[str, object], ...]:
    header = {
        "schema": DIRECTOR_SCHEMA,
        "schema_version": DIRECTOR_SCHEMA_VERSION,
        "record": "header",
        "mode": plan.mode.value,
        "entrant_id": plan.entrant_id,
        "visibility_basis": plan.visibility_basis,
        "match_id": plan.match_id,
        "replay_sha256": plan.replay_sha256,
        "first_tick": plan.first_tick,
        "last_tick": plan.last_tick,
    }
    body = tuple(
        {"record": "decision", **decision_to_dict(decision)} for decision in plan.decisions
    )
    result = {
        "record": "result",
        "plan_fingerprint": plan.plan_fingerprint(),
        "decision_count": len(plan.decisions),
        "boundary_count": sum(1 for d in plan.decisions if d.boundary),
    }
    return (header, *body, result)


def serialize_plan(plan: DirectorPlan) -> str:
    lines = [
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        for record in plan_records(plan)
    ]
    return "\n".join(lines) + "\n"


def explain_plan(plan: DirectorPlan) -> str:
    """A human-readable, boundary-only walkthrough (Phase 7 brief Sec. 9)."""

    lines: list[str] = [
        f"mode:      {plan.visibility_basis}",
        f"match:     {plan.match_id}",
        f"ticks:     {plan.first_tick}..{plan.last_tick}",
        "",
    ]
    for decision in plan.decisions:
        if not decision.boundary:
            continue
        lines.append(f"tick {decision.tick}")
        lines.append(f"  state:  {decision.state.value}")
        if decision.hold_ms:
            lines.append(f"  hold:   {decision.hold_ms} ms")
        else:
            lines.append(f"  rate:   {decision.rate_tps:g} TPS")
        lines.append(f"  reason: {decision.reason.value}")
        if decision.source_events:
            events_str = ", ".join(f"({t},{s})" for t, s in decision.source_events)
            lines.append(f"  source: {events_str}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spectator_director",
        description=(
            "Build a deterministic spectator playback-pacing plan from a validated "
            "v4 replay/trace pair, in either Broadcast or one entrant's Perspective "
            "information domain."
        ),
    )
    parser.add_argument("replay", help="canonical battle2.replay Schema 4 JSONL file")
    parser.add_argument("trace", help="bytefray.agent_trace schema-2 JSONL file")
    parser.add_argument(
        "--mode", choices=["broadcast", "perspective"], default="broadcast"
    )
    parser.add_argument(
        "--entrant", default=None, help="entrant id (required for --mode perspective)"
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the human-readable boundary-only walkthrough instead of JSONL",
    )
    parser.add_argument("--cruise-rate", type=float, default=DEFAULT_DIRECTOR_CONFIG.cruise_rate_tps)
    parser.add_argument("--contact-rate", type=float, default=DEFAULT_DIRECTOR_CONFIG.contact_rate_tps)
    parser.add_argument(
        "--engagement-rate", type=float, default=DEFAULT_DIRECTOR_CONFIG.engagement_rate_tps
    )
    parser.add_argument(
        "--recovery-rate", type=float, default=DEFAULT_DIRECTOR_CONFIG.recovery_rate_tps
    )
    parser.add_argument(
        "--impact-hold-ms", type=int, default=DEFAULT_DIRECTOR_CONFIG.impact_hold_ms
    )
    parser.add_argument(
        "--contact-lookback", type=int, default=DEFAULT_DIRECTOR_CONFIG.contact_lookback_ticks
    )
    parser.add_argument(
        "--engagement-lookback",
        type=int,
        default=DEFAULT_DIRECTOR_CONFIG.engagement_lookback_ticks,
    )
    parser.add_argument(
        "--recovery-ticks", type=int, default=DEFAULT_DIRECTOR_CONFIG.recovery_ticks
    )
    arguments = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    mode = DirectorMode.PERSPECTIVE if arguments.mode == "perspective" else DirectorMode.BROADCAST
    if mode is DirectorMode.PERSPECTIVE and arguments.entrant is None:
        parser.error("--mode perspective requires --entrant")

    config = DirectorConfig(
        cruise_rate_tps=arguments.cruise_rate,
        contact_rate_tps=arguments.contact_rate,
        engagement_rate_tps=arguments.engagement_rate,
        recovery_rate_tps=arguments.recovery_rate,
        impact_hold_ms=arguments.impact_hold_ms,
        contact_lookback_ticks=arguments.contact_lookback,
        engagement_lookback_ticks=arguments.engagement_lookback,
        recovery_ticks=arguments.recovery_ticks,
    )

    try:
        derivation = analyze_pair(arguments.replay, arguments.trace)
        plan = build_director_plan(
            derivation, mode=mode, entrant_id=arguments.entrant, config=config
        )
    except (SpectatorPairError, DirectorError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(explain_plan(plan) if arguments.explain else serialize_plan(plan))
    return 0


__all__ = [
    "DEFAULT_DIRECTOR_CONFIG",
    "DEFAULT_SIGNIFICANCE",
    "DIRECTOR_SCHEMA",
    "DIRECTOR_SCHEMA_VERSION",
    "DirectorConfig",
    "DirectorDecision",
    "DirectorError",
    "DirectorMode",
    "DirectorPacingState",
    "DirectorPlan",
    "DirectorReason",
    "EventSignificance",
    "build_director_plan",
    "build_director_plan_from_pair",
    "decision_to_dict",
    "explain_plan",
    "main",
    "plan_records",
    "serialize_plan",
]


if __name__ == "__main__":
    raise SystemExit(main())
