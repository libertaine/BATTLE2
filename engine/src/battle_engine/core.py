# core.py — Milestone-6+ with territory scoring + win-mode + GAME OVER summary
from __future__ import annotations
import json, random
from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple, List, Optional
from collections import Counter

# ----- ISA -----
NOP, MOV, ADD, LOAD, STORE, JMP, JZ, HALT = range(8)
MOVP, ADDP, LOADI, STOREI = 8, 9, 10, 11


# ----- Config -----
@dataclass
class Weights:
    alive: int = 1
    kill: int = 5
    territory: int = 1
    territory_bucket: int = 64


@dataclass
class Config:
    arena_size: int = 4096
    instr_per_tick: int = 8
    seed: int = 1337
    win_mode: str = "score_fallback"
    weights: Weights = field(default_factory=Weights)

    @staticmethod
    def from_dict(d: Dict) -> "Config":
        w = d.get("weights", {})
        return Config(
            arena_size=int(d.get("arena_size", 4096)),
            instr_per_tick=int(d.get("instr_per_tick", 8)),
            seed=int(d.get("seed", 1337)),
            win_mode=str(d.get("win_mode", "score_fallback")),
            weights=Weights(
                alive=int(w.get("alive", 1)),
                kill=int(w.get("kill", 5)),
                territory=int(w.get("territory", 1)),
                territory_bucket=int(w.get("territory_bucket", 64)),
            ),
        )


# ----- Telemetry -----
class JSONLSink:
    def __init__(self, path: str = "replay.jsonl"):
        self._f = open(path, "w", buffering=1)

    def emit(self, record: Dict) -> None:
        self._f.write(json.dumps(record, separators=(",", ":")) + "\n")

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass


# ----- Agent -----
@dataclass
class Agent:
    agent_id: str
    pc: int
    alive: bool = True
    regs: Dict[str, int] = field(default_factory=lambda: {"A": 0, "Z": 0, "P": 0})
    cpu_used: int = 0
    mem_writes: int = 0
    region: Tuple[int, int] = (0, 0)


# ----- VM -----
class VM:
    def __init__(self, arena_size: int):
        self.arena = bytearray([NOP] * arena_size)
        self.writer: List[Optional[str]] = [None] * arena_size
        self.tick_diffs: List[Tuple[int, int, Optional[str]]] = []

    def clear_tick_diffs(self):
        self.tick_diffs.clear()

    def _rd32(self, pos: int) -> int:
        m = len(self.arena)
        p = pos % m
        return (
            self.arena[p]
            | (self.arena[(p + 1) % m] << 8)
            | (self.arena[(p + 2) % m] << 16)
            | (self.arena[(p + 3) % m] << 24)
        )

    def _wr8(self, pos: int, val: int, owner: Optional[str]) -> None:
        m = len(self.arena)
        i = pos % m
        self.arena[i] = val & 0xFF
        self.writer[i] = owner
        if (
            self.tick_diffs
            and self.tick_diffs[-1][0] + self.tick_diffs[-1][1] == i
            and self.tick_diffs[-1][2] == owner
        ):
            a, l, o = self.tick_diffs[-1]
            self.tick_diffs[-1] = (a, l + 1, o)
        else:
            self.tick_diffs.append((i, 1, owner))

    def load_code(
        self, start: int, code: bytes, owner: Optional[str]
    ) -> Tuple[int, int]:
        m = len(self.arena)
        s = start % m
        for i, b in enumerate(code):
            self.arena[(s + i) % m] = b
            self.writer[(s + i) % m] = owner
        e = (s + max(1, len(code)) - 1) % m
        return s, e

    def step(self, agent: Agent) -> None:
        if not agent.alive:
            return
        m = len(self.arena)
        ip = agent.pc % m
        op = self.arena[ip]
        rd32 = self._rd32
        r = agent.regs
        if op == NOP:
            agent.pc = (ip + 1) % m
        elif op == HALT:
            agent.alive = False
        elif op == MOV:
            r["A"] = rd32(ip + 1) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == ADD:
            r["A"] = (r["A"] + (rd32(ip + 1) & 0xFFFFFFFF)) & 0xFFFFFFFF
            r["Z"] = 1 if r["A"] == 0 else 0
            agent.pc = (ip + 5) % m
        elif op == LOAD:
            addr = rd32(ip + 1) % m
            r["A"] = self.arena[addr]
            r["Z"] = 1 if r["A"] == 0 else 0
            agent.pc = (ip + 5) % m
        elif op == STORE:
            addr = rd32(ip + 1) % m
            self._wr8(addr, r["A"], owner=agent.agent_id)
            agent.mem_writes += 1
            agent.pc = (ip + 5) % m
        elif op == JMP:
            agent.pc = rd32(ip + 1) % m
        elif op == JZ:
            addr = rd32(ip + 1) % m
            agent.pc = addr if r.get("Z", 0) == 1 else (ip + 5) % m
        elif op == MOVP:
            r["P"] = rd32(ip + 1) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == ADDP:
            r["P"] = (r["P"] + (rd32(ip + 1) & 0xFFFFFFFF)) & 0xFFFFFFFF
            agent.pc = (ip + 5) % m
        elif op == LOADI:
            addr = r["P"] % m
            r["A"] = self.arena[addr]
            r["Z"] = 1 if r["A"] == 0 else 0
            agent.pc = (ip + 1) % m
        elif op == STOREI:
            addr = r["P"] % m
            self._wr8(addr, r["A"], owner=agent.agent_id)
            agent.mem_writes += 1
            agent.pc = (ip + 1) % m
        else:
            agent.alive = False


# ----- Assembler helper -----
def enc(op: int, imm: int | None = None) -> bytes:
    if imm is None:
        return bytes([op])
    v = imm & 0xFFFFFFFF
    return bytes([op, v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


# ----- Kernel -----
class Kernel:
    def __init__(
        self,
        cfg: Config,
        sink: Optional[JSONLSink] = None,
        renderer: Optional[object] = None,
    ):
        self.cfg = cfg
        self.vm = VM(cfg.arena_size)
        self.instr_per_tick = cfg.instr_per_tick
        self.agents: List[Agent] = []
        self.tick = 0
        self.sink = sink or JSONLSink("replay.jsonl")
        self.renderer = renderer
        self.score: Dict[str, int] = {}
        self._alive_prev: Dict[str, bool] = {}
        self.stats = {}
        self.rng = random.Random(cfg.seed)

    def spawn(self, agent_id: str, entry: int, code: bytes) -> None:
        s, e = self.vm.load_code(entry, code, owner=agent_id)
        a = Agent(agent_id=agent_id, pc=s, region=(s, e))
        self.agents.append(a)
        self.score.setdefault(agent_id, 0)
        self._alive_prev[agent_id] = a.alive
        self.stats[agent_id] = {
            "alive_ticks": 0,
            "total_cpu": 0,
            "total_mem_writes": 0,
            "kills": 0,
            "deaths": 0,
            "territory_max": 0,
            "territory_sum": 0,
            "territory_last": 0,
        }

    def _snapshot(self, events: List[Dict]) -> Dict:
        return {
            "tick": self.tick,
            "agents": [
                {
                    "id": a.agent_id,
                    "pc": a.pc,
                    "alive": a.alive,
                    "cpu_used": a.cpu_used,
                    "mem_writes": a.mem_writes,
                    "region": [a.region[0], a.region[1]],
                }
                for a in self.agents
            ],
            "score": dict(self.score),
            "events": events,
            "memory_diffs": [
                {"addr": addr, "len": ln, "owner": owner}
                for (addr, ln, owner) in self.vm.tick_diffs
            ],
        }

    def _apply_territory_scoring(self) -> None:
        if self.cfg.weights.territory <= 0:
            return
        own = Counter(self.vm.writer)
        for a in self.agents:
            cells = own.get(a.agent_id, 0)
            buckets = cells // max(1, self.cfg.weights.territory_bucket)
            if buckets:
                self.score[a.agent_id] = (
                    self.score.get(a.agent_id, 0) + buckets * self.cfg.weights.territory
                )

    def run(self, max_ticks: int = 10000, verbose: bool = True) -> str:
        header = {"tick": 0, "ver": 6, "config": asdict(self.cfg)}
        self.sink.emit(header)
        if self.renderer:
            self.renderer.on_init(self)

        for t in range(1, max_ticks + 1):
            self.tick = t
            self.vm.clear_tick_diffs()
            events: List[Dict] = []

            # step agents
            for a in self.agents:
                if not a.alive:
                    continue
                a.cpu_used = 0
                for _ in range(self.instr_per_tick):
                    if not a.alive:
                        break
                    self.vm.step(a)
                    a.cpu_used += 1

            # update stats
            for a in self.agents:
                if a.alive:
                    self.stats[a.agent_id]["alive_ticks"] += 1
                self.stats[a.agent_id]["total_cpu"] += a.cpu_used
                self.stats[a.agent_id]["total_mem_writes"] = a.mem_writes

            own_counts = Counter(self.vm.writer)
            for a in self.agents:
                cells = own_counts.get(a.agent_id, 0)
                st = self.stats[a.agent_id]
                st["territory_last"] = cells
                st["territory_sum"] += cells
                if cells > st["territory_max"]:
                    st["territory_max"] = cells

            # alive scoring
            for a in self.agents:
                if a.alive:
                    self.score[a.agent_id] = (
                        self.score.get(a.agent_id, 0) + self.cfg.weights.alive
                    )

            # territory scoring
            self._apply_territory_scoring()

            # kill attribution
            for a in self.agents:
                was_alive = self._alive_prev.get(a.agent_id, True)
                if was_alive and not a.alive:
                    killer = self.vm.writer[a.pc % len(self.vm.arena)]
                    if killer and killer != a.agent_id:
                        self.score[killer] = (
                            self.score.get(killer, 0) + self.cfg.weights.kill
                        )
                        self.stats[killer]["kills"] += 1
                        self.stats[a.agent_id]["deaths"] += 1
                        events.append(
                            {"type": "kill", "victim": a.agent_id, "by": killer}
                        )
                    else:
                        self.stats[a.agent_id]["deaths"] += 1
                        events.append({"type": "death", "victim": a.agent_id})

            # telemetry + render
            snap = self._snapshot(events)
            self.sink.emit(snap)
            if self.renderer:
                owners = self.vm.writer
                self.renderer.on_tick(
                    t, {**snap, "config": asdict(self.cfg), "__owners__": owners}
                )

            if verbose and (t % 50 == 0 or t < 10):
                alive_ids = [x.agent_id for x in self.agents if x.alive]
                print(f"[T{t:05d}] alive={alive_ids} score={self.score}")

            for a in self.agents:
                self._alive_prev[a.agent_id] = a.alive
            if sum(1 for a in self.agents if a.alive) <= 1:
                break

        if hasattr(self.sink, "close"):
            self.sink.close()
        if self.renderer:
            self.renderer.on_close()

        # resolve winner
        alive = [a.agent_id for a in self.agents if a.alive]
        mode = (self.cfg.win_mode or "score_fallback").lower()
        winner = ""
        if len(alive) == 1:
            winner = alive[0]
        elif mode == "survival":
            winner = ""
        else:
            if self.score:
                top = sorted(self.score.items(), key=lambda kv: (-kv[1], kv[0]))
                if len(top) == 1 or top[0][1] > top[1][1]:
                    winner = top[0][0]

        # summary
        ticks_run = self.tick
        arena = self.cfg.arena_size
        summ_agents = []
        for a in self.agents:
            st = self.stats[a.agent_id]
            avg_terr = st["territory_sum"] / max(1, ticks_run)
            summ_agents.append(
                {
                    "id": a.agent_id,
                    "alive": a.alive,
                    "score": self.score.get(a.agent_id, 0),
                    "alive_ticks": st["alive_ticks"],
                    "kills": st["kills"],
                    "deaths": st["deaths"],
                    "cpu_total": st["total_cpu"],
                    "mem_writes": st["total_mem_writes"],
                    "territory_last": st["territory_last"],
                    "territory_max": st["territory_max"],
                    "territory_avg": avg_terr,
                    "territory_pct_last": (
                        st["territory_last"] * 100.0 / arena if arena else 0.0
                    ),
                    "territory_pct_max": (
                        st["territory_max"] * 100.0 / arena if arena else 0.0
                    ),
                    "territory_pct_avg": avg_terr * 100.0 / arena if arena else 0.0,
                }
            )
        summary = {
            "winner": winner,
            "win_mode": mode,
            "ticks": ticks_run,
            "arena_size": arena,
            "config": asdict(self.cfg),
            "score": dict(self.score),
            "agents": sorted(summ_agents, key=lambda x: (-x["score"], x["id"])),
        }
        try:
            with open("summary.json", "w") as f:
                json.dump(summary, f, indent=2)
        except Exception:
            pass
        if self.renderer and hasattr(self.renderer, "on_game_over"):
            try:
                self.renderer.on_game_over(summary)
            except Exception:
                pass
        return winner
