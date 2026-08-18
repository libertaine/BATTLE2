"""Mutable runtime state for an agent executing in the BATTLE VM."""

from __future__ import annotations

from dataclasses import dataclass, field

from battle_engine.entrant_identity import EntrantIdentity


@dataclass(init=False)
class Agent:
    """VM execution state for one entrant.

    References the entrant's :class:`~battle_engine.entrant_identity.
    EntrantIdentity` rather than storing ``agent_id`` as an independent
    field -- see ``docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md``.
    ``agent_id`` remains a read-only compatibility property so the many
    ownership/writer-tracking/scoring/statistics/kill-attribution/replay
    call sites that read ``agent.agent_id`` are unaffected.

    The VM has never tracked a separate entrant display name on this class
    (only ``match_service.MatchEntrant``/``NativeAgentResult`` do) -- unlike
    :class:`~battle_engine.python_runtime.PythonEntrantState`, whose
    identity carries a real ``name`` from construction. ``identity.name``
    here mirrors ``agent_id``, preserving that existing asymmetry rather
    than fabricating a display name this class never had access to.
    """

    identity: EntrantIdentity
    pc: int
    alive: bool = True
    regs: dict[str, int] = field(default_factory=lambda: {"A": 0, "Z": 0, "P": 0})
    cpu_used: int = 0
    mem_writes: int = 0
    region: tuple[int, int] = (0, 0)

    def __init__(
        self,
        agent_id: str,
        pc: int,
        alive: bool = True,
        regs: dict[str, int] | None = None,
        cpu_used: int = 0,
        mem_writes: int = 0,
        region: tuple[int, int] = (0, 0),
    ) -> None:
        self.identity = EntrantIdentity(agent_id=agent_id, name=agent_id)
        self.pc = pc
        self.alive = alive
        self.regs = {"A": 0, "Z": 0, "P": 0} if regs is None else regs
        self.cpu_used = cpu_used
        self.mem_writes = mem_writes
        self.region = region

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id
