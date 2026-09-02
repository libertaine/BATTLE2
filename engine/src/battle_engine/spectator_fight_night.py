"""Deterministic "Fight Night" spectator presentation facts over derived events.

Phase 8 research infrastructure, not a public spectator API. This module
answers a third, narrower question than its two siblings. Where
:mod:`battle_engine.spectator_derivation` answers *what happened* and
:mod:`battle_engine.spectator_director` answers *when to show a tick*, this
module answers only *which already-qualified facts are worth putting on
screen right now, and what restrained label do they carry* -- never *what
happened*, never *what an entrant knows*, and never *what it meant*.

It derives nothing. Every :class:`FightNightEvent` restates one
:class:`~battle_engine.spectator_derivation.SpectatorEvent` that the Phase 3
derivation already produced, keeps that event's ``(tick, sequence)`` identity
so any entry can be audited back to its source record, and adds exactly two
presentation decisions on top: a fixed label string, and which single entrant
the entry is *about*.

Two information domains
------------------------
:class:`FightNightMode` selects which events may be presented at all, using
the identical mechanism :mod:`battle_engine.spectator_director` uses for
pacing:

- ``BROADCAST`` presents the full derivation event stream.
- ``PERSPECTIVE`` (bound to one entrant) presents **only** the subset whose
  ``visible_to`` already names that entrant.

The filter runs *before* the ribbon is assembled, not after -- so a hidden
fact is never in the list the ribbon is built from, rather than being in it
and skipped. This matters more here than it does for pacing: a ribbon entry
appearing at the exact moment a hidden event occurs is a strictly louder
disclosure than a pacing change, and the Phase 7 research document's own
timing-disclosure argument applies unchanged (see
``docs/research/v4/V4_SPECTATOR_PHASE_8_RESEARCH.md`` Sec. 7).

The one deliberate exception is match termination, carried forward from the
Director for the same reason: ``MATCH_ENDED``/``VICTORY`` are omniscient-only
and can never reach a Perspective stream, but by the time the whole match is
over there is no hidden gameplay left to protect, and the already-qualified
renderer shows the same terminal banner in every mode (Phase 6 Sec. 11 item
09). The result card is therefore built from plan-level metadata
(``winner``/``termination_reason``/``result_ticks``), never from a
per-entrant-filtered event.

Never names a second party
--------------------------
Every ribbon entry names at most **one** entrant -- its ``subject``. This is
a hard rule, not a default: it is what keeps the ribbon from asserting a
relationship the artifacts do not support. "A ATTACKS B" is never
constructible here, an anonymous spatial contact is never joined to an
entrant identity, and a ``HOSTILE_READ``'s cell owner never becomes an
opponent identity (the Phase 4 spec's Sec. 6/9 READ-owner separation,
carried into presentation).

Flood control
-------------
The event stream is not evenly paced: one Phase 8 corpus match derived 504
``HOSTILE_WRITE`` and 178 ``PROCESS_DISRUPTED`` events across 90 ticks. A
ribbon that showed each of them would be noise, so two bounded rules apply,
both purely structural: only kinds in :data:`RIBBON_LABELS` are eligible at
all (ordinary ``HOSTILE_WRITE``/``HOSTILE_READ``/``DETECTION_LOST``/
``EFFECTIVE_MOVE`` are excluded outright), and a repeat of the same
``(label, subject)`` pair inside ``repeat_cooldown_ticks`` is suppressed.
Neither rule weighs, ranks, or interprets an event.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from battle_engine.spectator_derivation import (
    SpectatorDerivation,
    SpectatorEvent,
    SpectatorEventKind,
)

FIGHT_NIGHT_SCHEMA = "bytefray.spectator_fight_night"
FIGHT_NIGHT_SCHEMA_VERSION = 1


class FightNightError(ValueError):
    """A Fight Night plan cannot be built from the given inputs."""


class FightNightMode(str, Enum):
    """Which information domain a Fight Night plan is allowed to present."""

    BROADCAST = "broadcast"
    PERSPECTIVE = "perspective"


class SubjectRole(str, Enum):
    """Which side of a source event the ribbon entry is *about*.

    Made explicit per kind rather than inferred from a generic
    "targets else actors" rule, because the two families genuinely differ:
    a detection is about the entrant that gained it, while a core-cell loss
    is about the entrant that lost the cell. Getting this backwards would
    silently mislabel every entry of an entire kind.
    """

    ACTOR = "actor"
    TARGET = "target"
    NONE = "none"


#: The complete ribbon vocabulary: source kind -> (label, whose entry it is).
#: A kind absent from this mapping is never presented, which is how ordinary
#: high-volume traffic (``HOSTILE_WRITE``, ``HOSTILE_READ``,
#: ``DETECTION_LOST``, ``EFFECTIVE_MOVE``) is excluded -- by omission from one
#: reviewable table, not by a scoring heuristic somewhere in a renderer.
#:
#: Labels restate the qualified event name rather than dramatize it. In
#: particular ``DETECTION_GAINED`` becomes the deliberately unattributed
#: "CONTACT": the v4 engine hands an observer occupied enemy *addresses* and
#: never says whose they are, so naming a counterparty here would invent
#: knowledge (see ``docs/specs/v4_spectator_perspective.md`` Sec. 6).
RIBBON_LABELS: Mapping[SpectatorEventKind, tuple[str, SubjectRole]] = {
    SpectatorEventKind.DETECTION_GAINED: ("CONTACT", SubjectRole.ACTOR),
    SpectatorEventKind.FIRST_HOSTILE_READ: ("FIRST HOSTILE READ", SubjectRole.ACTOR),
    SpectatorEventKind.FIRST_HOSTILE_WRITE: ("FIRST HOSTILE WRITE", SubjectRole.ACTOR),
    SpectatorEventKind.CORE_CELL_LOST: ("CORE CELL LOST", SubjectRole.TARGET),
    SpectatorEventKind.PROCESS_DISRUPTED: ("PROCESS DISRUPTED", SubjectRole.TARGET),
    SpectatorEventKind.AGENT_ELIMINATED: ("ELIMINATED", SubjectRole.TARGET),
    SpectatorEventKind.AGENT_FORFEITED: ("FORFEITED", SubjectRole.TARGET),
    SpectatorEventKind.VICTORY: ("VICTORY", SubjectRole.ACTOR),
    SpectatorEventKind.MATCH_ENDED: ("MATCH ENDED", SubjectRole.NONE),
}

#: Kinds that always bypass the repeat cooldown. These are one-shot lifecycle
#: facts -- an entrant is eliminated once -- so a cooldown could only ever
#: suppress a genuinely distinct entrant's entry that happened to land inside
#: another's cooldown window, never an actual repeat.
_NEVER_SUPPRESSED = frozenset(
    {
        SpectatorEventKind.AGENT_ELIMINATED,
        SpectatorEventKind.AGENT_FORFEITED,
        SpectatorEventKind.VICTORY,
        SpectatorEventKind.MATCH_ENDED,
    }
)


@dataclass(frozen=True)
class FightNightConfig:
    """Research-tunable presentation parameters."""

    #: How many ribbon entries are visible at once. Four fits the documented
    #: 640x480 minimum's overlay budget; see the Phase 8 research document.
    ribbon_size: int = 4
    #: A repeat of the same ``(label, subject)`` within this many ticks is
    #: suppressed. Set above the Director's ``contact_lookback_ticks`` (8) so
    #: a burst that keeps the Director in one pacing state also reads as one
    #: ribbon entry rather than many.
    repeat_cooldown_ticks: int = 12

    def fingerprint(self) -> tuple[object, ...]:
        return (self.ribbon_size, self.repeat_cooldown_ticks)


DEFAULT_FIGHT_NIGHT_CONFIG = FightNightConfig()


@dataclass(frozen=True)
class FightNightEvent:
    """One presentation-ready ribbon entry.

    ``tick``/``sequence`` are the *source* event's own identity in
    :attr:`~battle_engine.spectator_derivation.SpectatorDerivation.events`,
    retained so any on-screen entry can be audited back to the exact derived
    record that produced it. ``subject`` names at most one entrant, never two
    (see this module's docstring).
    """

    tick: int
    sequence: int
    label: str
    subject: str | None
    source_kind: SpectatorEventKind


@dataclass(frozen=True)
class FightNightPlan:
    """A deterministic presentation plan for one match/mode/entrant.

    ``ribbon_entries`` is the whole match's ordered entry list and
    ``ribbon_cursor`` is a dense per-tick prefix count into it, so
    :meth:`ribbon_at_tick` is a pure slice -- the ribbon at tick N depends on
    N alone and never on how playback arrived there (Phase 8 brief Sec. 43).
    """

    mode: FightNightMode
    entrant_id: str | None
    visibility_basis: str
    match_id: str
    replay_sha256: str
    config_fingerprint: tuple[object, ...]
    first_tick: int
    last_tick: int
    result_ticks: int
    entrants: tuple[str, ...]
    winner: str | None
    termination_reason: str | None
    ribbon_entries: tuple[FightNightEvent, ...]
    ribbon_cursor: tuple[int, ...]
    ribbon_size: int

    def _cursor_for(self, tick: int) -> int:
        if not self.ribbon_cursor:
            return 0
        if tick <= self.first_tick:
            return self.ribbon_cursor[0]
        if tick >= self.last_tick:
            return self.ribbon_cursor[-1]
        return self.ribbon_cursor[tick - self.first_tick]

    def ribbon_at_tick(self, tick: int) -> tuple[FightNightEvent, ...]:
        """The up-to-``ribbon_size`` most recent entries at ticks <= ``tick``.

        Oldest first, so a renderer can draw top-to-bottom and let the newest
        entry sit closest to the action without reversing anything itself.
        """

        end = self._cursor_for(tick)
        return self.ribbon_entries[max(0, end - self.ribbon_size) : end]

    def is_result_tick(self, tick: int) -> bool:
        """Whether ``tick`` is at or past the match's own result tick."""

        return tick >= self.result_ticks

    def plan_fingerprint(self) -> str:
        """A stable identity hash excluding any wall-clock state."""

        import hashlib

        payload = json.dumps(
            {
                "schema": FIGHT_NIGHT_SCHEMA,
                "schema_version": FIGHT_NIGHT_SCHEMA_VERSION,
                "mode": self.mode.value,
                "entrant_id": self.entrant_id,
                "visibility_basis": self.visibility_basis,
                "match_id": self.match_id,
                "replay_sha256": self.replay_sha256,
                "config_fingerprint": self.config_fingerprint,
                "winner": self.winner,
                "termination_reason": self.termination_reason,
                "entrants": list(self.entrants),
                "entries": [
                    (e.tick, e.sequence, e.label, e.subject, e.source_kind.value)
                    for e in self.ribbon_entries
                ],
                "cursor": list(self.ribbon_cursor),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def _visible_stream(
    derivation: SpectatorDerivation, mode: FightNightMode, entrant_id: str | None
) -> tuple[SpectatorEvent, ...]:
    if mode is FightNightMode.BROADCAST:
        return derivation.events
    return tuple(event for event in derivation.events if entrant_id in event.visible_to)


def _subject(event: SpectatorEvent, role: SubjectRole) -> str | None:
    if role is SubjectRole.ACTOR:
        return event.actors[0] if event.actors else None
    if role is SubjectRole.TARGET:
        return event.targets[0] if event.targets else None
    return None


def build_fight_night_plan(
    derivation: SpectatorDerivation,
    *,
    mode: FightNightMode,
    entrant_id: str | None = None,
    config: FightNightConfig = DEFAULT_FIGHT_NIGHT_CONFIG,
) -> FightNightPlan:
    """Build a deterministic presentation plan from an already-derived stream.

    Raises :class:`FightNightError` for an invalid mode/entrant combination.
    Never re-verifies a pair or re-derives events -- the caller is expected to
    hold one ``SpectatorDerivation`` and reuse it across Broadcast, every
    entrant's Perspective, and the Director (Phase 7 Sec. 16's shared-analysis
    rule, carried forward unchanged).
    """

    if mode is FightNightMode.PERSPECTIVE:
        if entrant_id is None:
            raise FightNightError("perspective mode requires an entrant_id")
        if entrant_id not in derivation.binding.entrant_identities:
            raise FightNightError(
                f"entrant {entrant_id!r} is not named by this derivation's binding"
            )
        visibility_basis = f"perspective:{entrant_id}"
    else:
        if entrant_id is not None:
            raise FightNightError("broadcast mode does not accept an entrant_id")
        visibility_basis = "broadcast"

    stream = _visible_stream(derivation, mode, entrant_id)

    entries: list[FightNightEvent] = []
    last_emitted: dict[tuple[str, str | None], int] = {}
    for event in stream:
        labelled = RIBBON_LABELS.get(event.kind)
        if labelled is None:
            continue
        label, role = labelled
        subject = _subject(event, role)
        key = (label, subject)
        if event.kind not in _NEVER_SUPPRESSED:
            previous = last_emitted.get(key)
            if previous is not None and event.tick - previous < config.repeat_cooldown_ticks:
                continue
        last_emitted[key] = event.tick
        entries.append(
            FightNightEvent(
                tick=event.tick,
                sequence=event.sequence,
                label=label,
                subject=subject,
                source_kind=event.kind,
            )
        )

    # Dense per-tick prefix count. Built in one forward pass over the already
    # tick-ordered entry list, so the cursor cannot disagree with the entries.
    cursor: list[int] = []
    index = 0
    for tick in range(derivation.first_tick, derivation.last_tick + 1):
        while index < len(entries) and entries[index].tick <= tick:
            index += 1
        cursor.append(index)

    return FightNightPlan(
        mode=mode,
        entrant_id=entrant_id,
        visibility_basis=visibility_basis,
        match_id=derivation.binding.match_id,
        replay_sha256=derivation.binding.replay_sha256,
        config_fingerprint=config.fingerprint(),
        first_tick=derivation.first_tick,
        last_tick=derivation.last_tick,
        result_ticks=derivation.result_ticks,
        entrants=tuple(derivation.binding.entrant_identities),
        winner=derivation.winner,
        termination_reason=derivation.termination_reason,
        ribbon_entries=tuple(entries),
        ribbon_cursor=tuple(cursor),
        ribbon_size=config.ribbon_size,
    )


__all__ = [
    "DEFAULT_FIGHT_NIGHT_CONFIG",
    "FIGHT_NIGHT_SCHEMA",
    "FIGHT_NIGHT_SCHEMA_VERSION",
    "RIBBON_LABELS",
    "FightNightConfig",
    "FightNightError",
    "FightNightEvent",
    "FightNightMode",
    "FightNightPlan",
    "SubjectRole",
    "build_fight_night_plan",
]
