"""Turtle Core Refresher -- v3 research-closeout disposable probe.

**research probe only. non-gate benchmark agent. not part of frozen
v2-baseline.** Never registered in any ``BenchmarkPopulation`` manifest,
never pinned by content-addressed revision, never substituted into
``v2_baseline_corpus.json`` or any other frozen benchmark. Exists only to
answer the v3 research-closeout task's Sec 6 question: does an entrant
that primarily or exclusively refreshes its own core maximize the
Phase 6 active-defense event (``tools/v3_phase6_defense_episode.py``,
unmodified) despite possessing little or no reactive defensive
intelligence?

This instantiates the Phase 5 design proposal's declared-but-never-run
E8 turtle-control probe
(``docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md`` Sec 5B.3: "A
deliberately passive/immobile probe agent (analogous to Phase 2's
``local_camper``) must not become competitive at any tested
``w_defense``") against the Phase 6 active-defense event rather than
against Phase 5B's abandoned ``w_defense`` scoring experiment, which was
never implemented and requires a scoring Ruleset that does not exist.
Phase 2's own ``local_camper`` was a locality-Ruleset-specific stationary
control built from ``MOVE``/``LOCAL_WRITE`` actions that do not exist
under ``bytefray-rules-2``; this probe is the smallest disposable
Ruleset-v2-native equivalent: a maximally passive own-core writer.

Strategy, deliberately as simple as possible: every action rewrites one
of this agent's own ``CORE_SIZE_HINT`` core cells, cycling through all of
them in a fixed round-robin, starting again at cell 0 once the cycle
completes. There is no expansion phase, no ``READ``, no branching on
``observation``, and no state beyond the anchor and the cycling index --
strictly less reactive intelligence than either frozen defense reference
agent (``core_defender`` still spends 3 of every 4 actions expanding;
``reactive_core_defender`` additionally inspects and reacts to evidence
of damage). If this probe fires the Phase 6 event as strongly as, or more
strongly than, either frozen defender, that is evidence the event
rewards *any* sufficiently frequent own-core rewrite rather than
responsive defense specifically.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

CORE_SIZE_HINT = 8  # public ruleset knowledge (bytefray-rules-2's CORE_SIZE)


class TurtleCoreRefresherAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0xEE
        self.core_start: int | None = None
        self.refresh_index = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.core_start is None:
            # First call, before this agent has ever moved its own pc:
            # observation.pc is exactly this entrant's original spawn
            # address (core_defender/agent.py's identical technique).
            self.core_start = observation.pc % self.arena_size

        address = (self.core_start + self.refresh_index) % self.arena_size
        self.refresh_index = (self.refresh_index + 1) % CORE_SIZE_HINT
        return AgentAction(ActionKind.WRITE, address, self.signature)


def create_agent() -> TurtleCoreRefresherAgent:
    return TurtleCoreRefresherAgent()
