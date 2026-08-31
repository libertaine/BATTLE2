"""Viper -- an asymmetric phase-switching infiltrator, Agent API v2.

Two declared processes split the fixed per-tick Q=8 budget:

    ``raider``   (reach 10, share 0.75) -- expansion, detection, and the
                 permanent kill-lock assault once a target is acquired.
    ``sentinel`` (reach 8,  share 0.25) -- stays home and reactively
                 defends Viper's own vulnerable core.

``raider`` runs two phases:

    Phase "expand" -- claims ground by writing every cell within its
        current reach (``fill_index`` cycling ``0..self_reach-1``), then
        ``MOVE``s onward by ``EXPANSION_STRIDE`` (nudged to stay coprime
        with ``arena_size``, exactly like the original design's Phase 0)
        once a stop is fully claimed. Every call also gets
        ``visible_enemy_anchor_addresses`` for free -- Agent API v2
        detection is automatic and current-only (docs/AGENT_API_V2.md
        Sec "Observation"), so there is no active v1-style READ scan to
        run: the instant any enemy process comes within ``raider``'s
        reach, this is Phase 1's "probe" already satisfied.
    Phase "assault" -- entered the moment expand ever sees a non-empty
        ``visible_enemy_anchor_addresses``, and never left again. Every
        process starts co-located with its own entrant's fixed core
        (docs/V4_ALPHA1_DESIGN.md Sec 4), so a first sighting is a strong
        proxy for the opponent's core location even after that process
        later moves away -- ``raider`` commits to an ``ASSAULT_WINDOW``-cell
        band centred on that first sighted address and cycles ``WRITE``
        across it forever, moving only enough to keep the current target
        cell in reach. "Until elimination" is realized as "forever, on the
        one location acquired": v4 alpha1's Agent API gives no elimination
        signal (docs/AGENT_API_V2.md's WRITE Information Boundary -- a
        WRITE reports only whether it legally applied, never whether it
        disrupted or killed anything), so there is no stopping condition to
        check even if Viper wanted one, and no way to re-verify or
        re-triangulate the target once its own process has wandered off --
        this is a real, undefended bet, exactly the honest trade-off
        docs/AGENT_AUTHORING.md's Raider/Sentinel already each document.

``sentinel`` never moves (it starts exactly on Viper's own core, per the
same co-location rule) and spends its whole budget on the Interrupt:
reactive core defense. Each call it either consumes the previous cell's
verdict or issues a fresh one:

    one action READs the next of the ``CORE_SIZE_HINT`` core cells in
    rotation; the very next ``sentinel`` call checks
    ``observation.previous_read_owner`` for that exact address and, only if
    it names some entrant other than Viper itself, spends that call
    repairing it with a ``WRITE`` before resuming the rotation. An
    unattacked core costs one READ per rotation step and nothing else; a
    contested cell is repaired the very next time ``sentinel`` is scheduled
    after the check that found it, not on a fixed timer.

Why Agent API v2 / Ruleset v4 alpha1 (``bytefray-rules-4-alpha1``), and what
that costs relative to an Agent API v1 design: v4 alpha1's Python-runtime
process loop reuses the exact same core-capture kill rule Ruleset v2
defined (``battle_engine.process_runtime`` calls
``python_runtime.apply_core_capture`` every tick, unconditionally), so
"vulnerable core" and "kill-lock until elimination" are still real, live
mechanics here -- but the *Agent API* built around v4 alpha1 is a genuinely
different observation/action model, not a compatible superset of v1:
``READ``/``WRITE`` stay absolute-address but are bounded by a movable
process's ``self_reach`` instead of being valid anywhere in the arena, so
"probing" is achieved by moving into range rather than by reading distant
cells; ownership is reported directly as ``previous_read_owner`` instead of
inferred from a raw byte and a remembered signature; and enemy detection is
an automatic engine service (``visible_enemy_anchor_addresses``) rather than
something Viper has to go looking for. v1 and v2 entrants cannot appear in
the same match (docs/AGENT_AUTHORING.md), so this version cannot be
development-tested against the Agent API v1 ``claimer`` starter -- use a v2
opponent instead, e.g.::

    bytefray agents validate viper
    bytefray agents test viper --opponent v4_claimer --ruleset bytefray-rules-4-alpha1

(``--ruleset`` must be explicit: an omitted ``--ruleset`` resolves to the
permanent ``bytefray-rules-2`` for an all-Python roster, which is the v1
Ruleset this version no longer targets.)

Not a claim of optimal strategy: permanently committing to the first
sighted address means Viper cannot recover from ever mis-timing that first
sighting (an enemy glimpsed mid-sweep, far from its actual core, locks in a
band that may never be revisited), and ``sentinel``'s reactive checks cost
real ``raider`` budget indirectly, since total entrant throughput is capped
at Q=8 regardless of process count -- the same honest trade-offs an Agent
API v1 version of this design would document, now re-derived for a
different contract.
"""

from __future__ import annotations

import math

from battle_engine.agent_api import (
    ActionKindV2,
    AgentAction,
    MatchContextV2,
    ObservationV2,
    ProcessDeclaration,
)

CORE_SIZE_HINT = 8  # own_core_size is fixed at 8 under bytefray-rules-4-alpha1 today

EXPANSION_STRIDE = 13  # Phase 0: default coprime MOVE stride
ASSAULT_WINDOW = 16  # width of the Phase 2 kill-lock band (> CORE_SIZE_HINT)

RAIDER_REACH = 10
RAIDER_SHARE = 0.75
SENTINEL_REACH = 8  # >= CORE_SIZE_HINT so every own-core cell is always in reach
SENTINEL_SHARE = 0.25


def _coprime_stride(base: int, modulus: int, *, max_value: int = 64) -> int:
    """Smallest odd value >= ``base`` (capped at ``max_value``) coprime with ``modulus``.

    Capped rather than unbounded because the result is used as a ``MOVE``
    operand, which the engine clamps to ``[-64, 64]`` regardless
    (docs/AGENT_API_V2.md) -- searching past that clamp could silently pick
    a stride the engine would truncate to something else entirely.
    """

    if modulus <= 1:
        return min(base, max_value)
    stride = base if base % 2 else base + 1
    while stride <= max_value and math.gcd(stride, modulus) != 1:
        stride += 2
    return min(stride, max_value)


class ViperAgent:
    def reset(self, context: MatchContextV2) -> None:
        self.rng = context.rng
        self.arena_size = context.arena_size
        self.agent_id = context.agent_id
        self.signature = 0x76

        self.expand_stride = _coprime_stride(EXPANSION_STRIDE, context.arena_size)
        self.fill_index = 0

        self.phase = "expand"
        self.assault_window_start: int | None = None
        self.assault_cursor = 0

        self.defend_index = 0
        self._pending_defense_addr: int | None = None

    def declare_processes(self) -> list[ProcessDeclaration]:
        return [
            ProcessDeclaration(id="raider", reach=RAIDER_REACH, share=RAIDER_SHARE),
            ProcessDeclaration(id="sentinel", reach=SENTINEL_REACH, share=SENTINEL_SHARE),
        ]

    def act(self, observation: ObservationV2) -> AgentAction:
        if observation.self_process_id == "sentinel":
            return self._act_sentinel(observation)
        return self._act_raider(observation)

    # -- raider: expansion, detection, assault ----------------------------------

    def _act_raider(self, observation: ObservationV2) -> AgentAction:
        if self.phase == "expand":
            if observation.visible_enemy_anchor_addresses:
                return self._begin_assault(
                    observation, observation.visible_enemy_anchor_addresses[0]
                )
            return self._expand_step(observation)
        return self._assault_step(observation)

    def _expand_step(self, observation: ObservationV2) -> AgentAction:
        if self.fill_index < observation.self_reach:
            address = (observation.self_anchor + self.fill_index) % self.arena_size
            self.fill_index += 1
            return AgentAction(ActionKindV2.WRITE, address, self.signature)
        self.fill_index = 0
        return AgentAction(ActionKindV2.MOVE, self.expand_stride)

    def _begin_assault(self, observation: ObservationV2, hit_addr: int) -> AgentAction:
        self.phase = "assault"
        self.assault_window_start = (hit_addr - ASSAULT_WINDOW // 2) % self.arena_size
        self.assault_cursor = 0
        return self._assault_step(observation)

    def _assault_step(self, observation: ObservationV2) -> AgentAction:
        assert self.assault_window_start is not None
        target = (self.assault_window_start + self.assault_cursor) % self.arena_size
        diff = self._shortest_delta(target, observation.self_anchor)
        if abs(diff) <= observation.self_reach:
            self.assault_cursor = (self.assault_cursor + 1) % ASSAULT_WINDOW
            return AgentAction(ActionKindV2.WRITE, target, self.signature)
        move = max(-64, min(64, diff))
        return AgentAction(ActionKindV2.MOVE, move)

    # -- sentinel: reactive home-core defense ------------------------------------

    def _act_sentinel(self, observation: ObservationV2) -> AgentAction:
        if self._pending_defense_addr is not None:
            address = self._pending_defense_addr
            self._pending_defense_addr = None
            owner = observation.previous_read_owner
            if owner is not None and owner != self.agent_id:
                return AgentAction(ActionKindV2.WRITE, address, self.signature)

        address = (observation.own_core_base + self.defend_index) % self.arena_size
        self.defend_index = (self.defend_index + 1) % CORE_SIZE_HINT
        self._pending_defense_addr = address
        return AgentAction(ActionKindV2.READ, address)

    # -- shared --------------------------------------------------------------------

    def _shortest_delta(self, target: int, anchor: int) -> int:
        diff = target - anchor
        half = self.arena_size // 2
        if diff > half:
            diff -= self.arena_size
        elif diff < -half:
            diff += self.arena_size
        return diff


def create_agent() -> ViperAgent:
    return ViperAgent()
