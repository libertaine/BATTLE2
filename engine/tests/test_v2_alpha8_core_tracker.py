"""``core_tracker`` -- v2.0.0-alpha.8 placement-agnostic offense benchmark
acceptance tests.

Covers the governing v2.0.0-alpha.8 task's Phase 26 checklist: proves this
new reference agent (a) satisfies the ordinary Agent API v1 contract with
no privileged information, (b) structurally avoids the stale-``last_read``
echo-lock defect alpha.6 (docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md Sec 4)
found in the *existing*, unmodified ``core_seeker``, (c) only commits an
assault after genuinely separate confirming evidence, never from an
isolated hit, (d) locates and fully covers a compact foreign region
wherever it is placed, including across an arena wraparound, (e) is not
permanently derailed by an irrelevant decoy, and (f) does not hardcode any
of alpha.7's historical placement-condition addresses.

Also covers the v2.0.0-beta1 self-core-filtering revision
(docs/V2_0_BETA1_PLAN.md): this agent's own core, which always carries a
non-zero beacon under core-observability maintenance, must never be
mistaken for a foreign one, while a genuinely foreign region -- including
one carrying the identical beacon byte, just outside this agent's own
core -- must still be found exactly as before.

Two complementary styles, matching this repository's own established
precedent for reference/starter agents:

* Direct state-machine tests instantiate the real, unmodified agent through
  the real ``load_python_agent``/``Agent API v1`` loader (never a bypass)
  and drive it with hand-crafted ``Observation`` sequences against a small
  in-memory "arena" dict -- the same technique this file's docstring-level
  scenarios (isolated cell, compact region, wraparound, decoy) need
  fully deterministic, single-action-granularity control over that the
  full ``NativeMatchService`` integration style below cannot easily give.
* End-to-end ``NativeMatchService`` tests (mirroring
  ``test_v2_alpha1_reference_agents.py``'s own pattern for ``core_seeker``)
  prove this agent actually loads, runs a full match without forfeiting,
  and can locate and capture a real opponent's core end to end.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

from battle_engine.agent_api import (
    ActionKind,
    AgentAction,
    LoadedPythonAgent,
    MatchContext,
    Observation,
    load_python_agent,
)
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.reference_agents import reference_agent_spec
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ALPHA1_ID

ALPHA = BYTEFRAY_RULESET_V2_ALPHA1_ID

# alpha.7's own four pre-registered placement conditions
# (docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md Sec 8) -- every
# *distinctive* (multi-digit, not otherwise generic) address from every
# condition, checked in test_source_does_not_hardcode_alpha7_addresses
# below to prove none of them leaked into this new agent as a magic value.
# Deliberately excludes plain "0": it is control seat A, but it is also an
# ordinary, unavoidable default/anchor literal in virtually any address
# arithmetic (e.g. "the arena's first address"), so its presence proves
# nothing about placement-convention overfitting one way or the other.
ALPHA7_PLACEMENT_ADDRESSES = {
    1365, 2730,  # control (seat A, address 0, excluded -- see above)
    83, 1281, 2635,  # cold
    282, 1846, 3411,  # hot
    600, 2011, 3251,  # mixed
    2048,  # legacy alpha.1/alpha.2 1v1 convention
}


def _load() -> LoadedPythonAgent:
    return load_python_agent(reference_agent_spec("core_tracker"))


def _context(seed: int, arena_size: int = 4096) -> MatchContext:
    return MatchContext(
        agent_id="A",
        seed=seed,
        arena_size=arena_size,
        tick_limit=200,
        action_budget=8,
        rng=random.Random(seed),
    )


def _observation(*, pc: int, last_read: int | None) -> Observation:
    return Observation(
        tick=1,
        agent_id="A",
        pc=pc,
        register_a=0,
        register_p=0,
        zero_flag=False,
        last_read=last_read,
        alive=True,
    )


def _drive(instance, memory: dict[int, int], *, pc: int, steps: int) -> list[dict]:
    """Feed ``instance.act()`` ``steps`` times against a simulated arena.

    ``memory`` models ground-truth arena content (default ``0`` for any
    address never written), exactly like the real VM: a ``READ`` returns
    ``memory.get(address, 0)``; a ``WRITE`` updates ``memory[address]`` and
    -- exactly as ``python_runtime.apply_action`` really behaves (confirmed
    by direct reading, see this module's own docstring) -- never touches
    ``last_read``, which is only ever set by a ``READ``. Returns one dict
    per step: ``{"mode_before": ..., "action": ...}``, where
    ``mode_before`` is ``instance.mode`` as it was *before* this action was
    decided (i.e. which mode issued it) -- what most fixture assertions
    below actually need (e.g. "which addresses did the *assault* state
    write to").
    """

    last_read: int | None = None
    trace: list[dict] = []
    for _ in range(steps):
        mode_before = instance.mode
        observation = _observation(pc=pc, last_read=last_read)
        action = instance.act(observation)
        trace.append({"mode_before": mode_before, "action": action})
        if action.kind is ActionKind.READ:
            last_read = memory.get(action.operand, 0)
        elif action.kind is ActionKind.WRITE:
            memory[action.operand] = action.value
    return trace


def _modes(trace: list[dict]) -> set[str]:
    return {t["mode_before"] for t in trace}


def _writes_from(trace: list[dict], mode: str) -> set[int]:
    return {t["action"].operand for t in trace if t["mode_before"] == mode and t["action"].kind is ActionKind.WRITE}


# ---------------------------------------------------------------------------
# Ordinary Agent API v1 lifecycle / registration
# ---------------------------------------------------------------------------


def test_core_tracker_satisfies_the_agent_api_v1_contract() -> None:
    loaded = _load()
    assert loaded.metadata.agent_id == "core_tracker"
    assert loaded.metadata.api_version == 1


def test_core_tracker_is_registered_alongside_the_other_reference_agents() -> None:
    from battle_engine.reference_agents import REFERENCE_AGENT_NAMES

    assert "core_tracker" in REFERENCE_AGENT_NAMES
    assert "core_seeker" in REFERENCE_AGENT_NAMES  # the historical control stays available


def test_core_tracker_is_not_part_of_the_general_starter_roster() -> None:
    from battle_engine.starters import STARTER_AGENT_NAMES

    assert "core_tracker" not in STARTER_AGENT_NAMES


def test_observation_carries_no_opponent_state_the_agent_could_read() -> None:
    """Structural guarantee: even if this agent wanted opponent state, the
    Agent API v1 ``Observation`` it is handed has no field to read it
    from -- the same guarantee every other reference agent in this
    package already documents and relies on."""

    v1_fields = {
        "tick",
        "agent_id",
        "pc",
        "register_a",
        "register_p",
        "zero_flag",
        "last_read",
        "alive",
    }
    # v3 research Phase 2 adds exactly one additive, optional field, and it
    # describes *this* entrant's own execution locus -- never another
    # entrant's anything. It is `None` under every Ruleset with a stable
    # identity, so a v1/v2 agent observes exactly what it always did.
    experimental_fields = {"locus"}
    fields = {f.name for f in Observation.__dataclass_fields__.values()}
    assert fields == v1_fields | experimental_fields
    assert Observation.__dataclass_fields__["locus"].default is None


def test_source_does_not_hardcode_alpha7_placement_addresses() -> None:
    """Phase 9's placement-independence requirement, checked directly
    against source: none of alpha.7's four pre-registered condition
    addresses (or the legacy alpha.1/alpha.2 1v1 convention) may appear as
    a literal in this agent's implementation. Comma-grouped numbers (e.g.
    "1,600-action") are normalized first so a written-out large number
    never produces a false positive on an embedded substring."""

    source_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "battle_engine"
        / "data"
        / "reference_agents"
        / "core_tracker"
        / "agent.py"
    )
    text = re.sub(r"(?<=\d),(?=\d)", "", source_path.read_text(encoding="utf-8"))
    found = {n for n in ALPHA7_PLACEMENT_ADDRESSES if re.search(rf"(?<!\d){n}(?!\d)", text)}
    assert not found, f"historical placement addresses leaked into source: {found}"


# ---------------------------------------------------------------------------
# Avoiding the stale-last_read echo-lock defect (alpha.6 Sec 4 / Phase 8)
# ---------------------------------------------------------------------------


def test_a_scan_hit_alone_does_not_trigger_an_assault() -> None:
    """A single foreign-looking byte, with nothing foreign nearby, must
    never be enough on its own -- unlike core_seeker's own echo-lock
    (alpha.6 Sec 4), which fires from exactly this evidence within 1-2
    actions because it re-reads the same stale ``last_read`` against
    itself."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 2000  # deterministic scenario anchor
    memory = {2000: 0x77}  # one isolated foreign byte, no neighbors at all
    trace = _drive(instance, memory, pc=0, steps=60)
    assert "assault" not in _modes(trace)
    assert instance.mode == "scan"


def test_last_read_is_ignored_unless_a_read_is_actually_pending() -> None:
    """The exact mechanism alpha.6 Sec 4 found broken in the *existing*,
    unmodified core_seeker: ``observation.last_read`` is never cleared
    between actions in the real production runtime (confirmed by direct
    reading, see this module's own docstring), so an implementation that
    checks it on every action -- not just the one immediately following a
    ``READ`` it issued -- will treat stale leftover content as fresh
    evidence. This agent's very first two calls have never issued any
    ``READ`` at all (``actions_taken`` only reaches ``SCAN_EVERY`` on the
    third), so *any* value supplied for ``last_read`` on them is
    necessarily unrelated to anything this agent actually requested --
    proving the gate is "was a read pending", not "does last_read look
    foreign"."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    foreign_looking_but_never_actually_read = 0x77

    action1 = instance.act(_observation(pc=0, last_read=foreign_looking_but_never_actually_read))
    assert action1.kind is ActionKind.WRITE  # an ordinary expand write, not a probe entry
    assert instance.mode == "scan"

    action2 = instance.act(_observation(pc=0, last_read=foreign_looking_but_never_actually_read))
    assert action2.kind is ActionKind.WRITE
    assert instance.mode == "scan"


def test_assault_burst_ignores_last_read_entirely() -> None:
    """Once committed, assault mode issues only WRITEs -- no READ is ever
    pending during it, so whatever ``last_read`` a caller supplies must
    have zero effect on the fixed-length burst or the state it returns to."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 3000
    region = set(range(3000, 3008))  # a compact CORE_SIZE_HINT-wide region
    memory = {addr: 0x77 for addr in region}
    _drive(instance, memory, pc=0, steps=8)
    assert instance.mode == "assault"

    remaining = instance.assault_remaining
    actions: list[AgentAction] = []
    for _ in range(remaining):
        actions.append(instance.act(_observation(pc=0, last_read=0x99)))
    assert all(a.kind is ActionKind.WRITE for a in actions)
    assert instance.mode == "scan"  # returned cleanly, no spurious re-trigger


# ---------------------------------------------------------------------------
# Confirmation / clustering behavior (Phase 10 synthetic fixtures)
# ---------------------------------------------------------------------------


def test_compact_foreign_region_triggers_a_fully_covering_assault() -> None:
    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 3000
    region = set(range(3000, 3008))
    memory = {addr: 0x77 for addr in region}
    trace = _drive(instance, memory, pc=0, steps=40)
    assault_writes = _writes_from(trace, "assault")
    assert assault_writes  # an assault actually happened
    assert region.issubset(assault_writes)


def test_compact_foreign_region_is_found_when_moved_elsewhere() -> None:
    """Same fixture, different address -- nothing about detection depends
    on where the region happens to sit."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 55
    region = set(range(55, 63))
    memory = {addr: 0x77 for addr in region}
    trace = _drive(instance, memory, pc=0, steps=40)
    assault_writes = _writes_from(trace, "assault")
    assert assault_writes
    assert region.issubset(assault_writes)


def test_compact_foreign_region_wrapping_the_arena_end_is_covered() -> None:
    arena_size = 64
    instance = _load().instance
    instance.reset(_context(seed=1, arena_size=arena_size))
    instance.scan_cursor = 60
    region = {(60 + i) % arena_size for i in range(8)}  # wraps past address 63 to 0..3
    assert min(region) == 0 and max(region) == 63  # confirms the wrap actually occurs
    memory = {addr: 0x77 for addr in region}
    # Own spawn (pc) deliberately kept clear of the region itself: this
    # agent's own ordinary expansion writes elsewhere in the arena, and
    # picking a spawn inside the region under test would let this agent's
    # own first couple of expand WRITEs overwrite the fixture's foreign
    # content with its own signature before scanning ever reaches it --
    # a self-inflicted collision specific to this fixture, not a property
    # worth encoding into the fixture itself.
    trace = _drive(instance, memory, pc=16, steps=40)
    assault_writes = _writes_from(trace, "assault")
    assert assault_writes
    assert region.issubset(assault_writes)


def test_decoy_then_true_region_is_not_permanently_trapped() -> None:
    """A single isolated decoy byte, found first, must not derail this
    agent from later finding a genuine compact region elsewhere -- proving
    search resumes after a failed (abandoned) candidate, not just after a
    completed assault."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 1000
    memory = {1000: 0x77}  # decoy: isolated, confirms nothing nearby
    decoy_trace = _drive(instance, memory, pc=0, steps=20)
    assert "assault" not in _modes(decoy_trace)
    assert instance.mode == "scan"

    instance.scan_cursor = 2500  # steer the still-running agent onto a real region
    region = set(range(2500, 2508))
    for addr in region:
        memory[addr] = 0x77
    true_trace = _drive(instance, memory, pc=0, steps=40)
    assault_writes = _writes_from(true_trace, "assault")
    assert assault_writes
    assert region.issubset(assault_writes)


def test_search_resumes_after_a_completed_assault() -> None:
    """After a full assault burst finishes, ordinary scan/expand activity
    must continue -- this agent must not get stuck in a terminal state."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    instance.scan_cursor = 3000
    region = set(range(3000, 3008))
    memory = {addr: 0x77 for addr in region}
    first = _drive(instance, memory, pc=0, steps=40)
    assert _writes_from(first, "assault")
    assert instance.mode == "scan"

    more = _drive(instance, memory, pc=0, steps=20)
    assert len(more) == 20  # kept acting normally
    assert any(t["action"].kind is ActionKind.WRITE for t in more)


# ---------------------------------------------------------------------------
# Self-core filtering (v2.0.0-beta1 revision -- docs/V2_0_BETA1_PLAN.md)
# ---------------------------------------------------------------------------


def test_own_core_beacon_never_triggers_a_probe() -> None:
    """The exact false positive alpha.11 disclosed and left unfixed for
    experimental validity (docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md
    Sec 26 item 2): a scan hit landing inside this agent's own core, carrying
    the public core-observability beacon, must never be treated as foreign."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    own_start = 3000
    instance.scan_cursor = own_start  # lands exactly on the agent's own core
    memory = {addr: 0xCE for addr in range(own_start, own_start + 8)}  # CORE_BEACON_BYTE
    trace = _drive(instance, memory, pc=own_start, steps=60)
    assert "probe" not in _modes(trace)
    assert "assault" not in _modes(trace)
    assert instance.mode == "scan"


def test_own_core_with_own_signature_never_triggers_a_probe() -> None:
    """Same guarantee if this agent has already signed its own core with its
    own signature byte rather than leaving the engine's beacon in place --
    already excluded by the pre-existing ``value != self.signature`` check,
    confirmed here alongside the new address-based filter."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    own_start = 3000
    instance.scan_cursor = own_start
    memory = {addr: instance.signature for addr in range(own_start, own_start + 8)}
    trace = _drive(instance, memory, pc=own_start, steps=60)
    assert "probe" not in _modes(trace)
    assert instance.mode == "scan"


def test_foreign_core_just_outside_the_own_core_boundary_still_triggers() -> None:
    """The filter is scoped exactly to ``CORE_SIZE_HINT`` cells -- a
    genuinely foreign compact region immediately adjacent to this agent's
    own core boundary must still be found, proving the fix is a narrow
    self-filter, not a general "ignore anything near my spawn" suppression."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    own_start = 3000  # own core: 3000..3007
    foreign_start = 3008  # immediately adjacent, outside the own-core window
    instance.scan_cursor = foreign_start
    memory = {addr: 0x77 for addr in range(foreign_start, foreign_start + 8)}
    trace = _drive(instance, memory, pc=own_start, steps=40)
    assault_writes = _writes_from(trace, "assault")
    assert assault_writes
    assert set(range(foreign_start, foreign_start + 8)).issubset(assault_writes)


def test_identical_beacon_content_outside_own_core_still_triggers() -> None:
    """External evidence: exactly the same byte value (the public beacon) is
    still legitimate evidence when it is not inside this agent's own core --
    the filter checks the *address*, never the *value*, so it grants no
    privileged recognition of the beacon value itself."""

    instance = _load().instance
    instance.reset(_context(seed=1))
    own_start = 100  # own core: 100..107, far from the foreign region below
    foreign_start = 3000
    instance.scan_cursor = foreign_start
    memory = {addr: 0xCE for addr in range(foreign_start, foreign_start + 8)}
    trace = _drive(instance, memory, pc=own_start, steps=40)
    assault_writes = _writes_from(trace, "assault")
    assert assault_writes
    assert set(range(foreign_start, foreign_start + 8)).issubset(assault_writes)


def test_own_core_filter_wraps_across_the_arena_end() -> None:
    """Placement generality: the self-filter must use the same ordinary
    arena wrap every other address computation in this agent already uses,
    not just the unwrapped case."""

    arena_size = 64
    instance = _load().instance
    instance.reset(_context(seed=1, arena_size=arena_size))
    own_start = 60  # own core wraps: 60,61,62,63,0,1,2,3
    instance.scan_cursor = 62  # inside the wrapped own-core region
    memory = {(60 + i) % arena_size: 0xCE for i in range(8)}
    trace = _drive(instance, memory, pc=own_start, steps=40)
    assert "probe" not in _modes(trace)
    assert instance.mode == "scan"


# ---------------------------------------------------------------------------
# Placement/spawn independence (Phase 9)
# ---------------------------------------------------------------------------


def test_scan_geometry_is_independent_of_own_spawn_position() -> None:
    """This agent's scan cursor/stride are seeded purely from
    ``MatchContext.rng`` at ``reset`` time, deliberately never from
    ``observation.pc`` -- unlike ``expand_cursor``, which legitimately
    does depend on this agent's own spawn (Phase 9's own "equivalent
    search pattern modulo whatever legitimately depends on own position"
    wording)."""

    a1 = _load().instance
    a2 = _load().instance
    a1.reset(_context(seed=7))
    a2.reset(_context(seed=7))
    assert a1.scan_cursor == a2.scan_cursor
    assert a1.scan_stride == a2.scan_stride

    for _ in range(10):
        a1.act(_observation(pc=111, last_read=None))
        a2.act(_observation(pc=3987, last_read=None))
    assert a1.scan_cursor == a2.scan_cursor  # search geometry unaffected by own spawn
    assert a1.expand_cursor != a2.expand_cursor  # expansion legitimately does depend on it


def test_different_seeds_scan_materially_different_regions() -> None:
    """The whole point of anchoring the scan cursor to ``context.rng``
    (docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md's design section):
    unlike core_seeker's own scan sequence (a pure function of
    ``arena_size`` alone, identical in every match forever), this agent's
    reachable set is also a function of the match seed."""

    def scan_addresses(seed: int) -> list[int]:
        instance = _load().instance
        instance.reset(_context(seed=seed))
        addrs = []
        last_read = None
        for _ in range(300):
            action = instance.act(_observation(pc=0, last_read=last_read))
            if action.kind is ActionKind.READ:
                addrs.append(action.operand)
            last_read = None  # never foreign; stay in pure scan/expand cadence
        return addrs

    seq_a = scan_addresses(1)
    seq_b = scan_addresses(2)
    assert seq_a[0] != seq_b[0]  # different starting cursor
    assert seq_a != seq_b


def test_deterministic_given_identical_seed_and_input_sequence() -> None:
    a1 = _load().instance
    a2 = _load().instance
    a1.reset(_context(seed=42))
    a2.reset(_context(seed=42))
    memory1: dict[int, int] = {}
    memory2: dict[int, int] = {}
    trace1 = _drive(a1, memory1, pc=500, steps=200)
    trace2 = _drive(a2, memory2, pc=500, steps=200)
    assert [t["action"] for t in trace1] == [t["action"] for t in trace2]


# ---------------------------------------------------------------------------
# End-to-end: real matches through NativeMatchService
# ---------------------------------------------------------------------------


def test_core_tracker_runs_a_full_match_without_forfeiting_under_the_alpha_ruleset(tmp_path: Path) -> None:
    tracker = reference_agent_spec("core_tracker")
    entrants = (
        MatchEntrant.python("A", "A", 0, tracker),
        MatchEntrant.python("B", "B", 2048, tracker),
    )
    request = MatchRequest(
        Config(arena_size=4096),
        entrants,
        max_ticks=200,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=ALPHA,
    )
    result = NativeMatchService().run(request)
    for agent in result.agents:
        assert agent.diagnostic is None


def test_core_tracker_can_locate_and_capture_core_defenders_core(tmp_path: Path) -> None:
    """Not a guarantee for every seed/orientation (this is a research
    benchmark agent, not a solved strategy) -- but, exactly like
    ``core_seeker``'s own acceptance test, at least one seed must show
    real end-to-end capture behavior at these addresses, or the mechanic
    is not doing what it was designed to do."""

    defender = reference_agent_spec("core_defender")
    tracker = reference_agent_spec("core_tracker")
    captured = False
    for seed in range(1, 17):
        entrants = (
            MatchEntrant.python("A", "core_defender", 0, defender),
            MatchEntrant.python("B", "core_tracker", 2048, tracker),
        )
        request = MatchRequest(
            Config(arena_size=4096, seed=seed),
            entrants,
            max_ticks=200,
            replay_path=tmp_path / f"run-{seed}" / "replay.jsonl",
            verbose=False,
            ruleset_id=ALPHA,
        )
        result = NativeMatchService().run(request)
        if result.agents_by_id["A"].termination_reason == "core_captured":
            captured = True
            assert result.agents_by_id["B"].kills == 1
            break
    assert captured, "core_tracker never captured core_defender's core across 16 seeds"


def test_core_tracker_also_runs_cleanly_under_ruleset_v1(tmp_path: Path) -> None:
    """An ordinary Agent API v1 Python agent -- nothing about it requires
    the alpha ruleset to function; under v1 there is simply no core to
    capture."""

    tracker = reference_agent_spec("core_tracker")
    entrants = (
        MatchEntrant.python("A", "A", 0, tracker),
        MatchEntrant.python("B", "B", 2048, tracker),
    )
    request = MatchRequest(
        Config(arena_size=4096),
        entrants,
        max_ticks=50,
        replay_path=tmp_path / "run" / "replay.jsonl",
        verbose=False,
        ruleset_id=None,
    )
    result = NativeMatchService().run(request)
    assert result.termination_reason.value in {"tick_limit", "last_agent_standing", "all_agents_dead"}
    for agent in result.agents:
        assert agent.diagnostic is None
        assert agent.termination_reason != "core_captured"
    from battle_engine.replay import ReplayHeader, iter_replay

    header_ruleset_id = None
    for record in iter_replay(result.replay_path):
        if isinstance(record, ReplayHeader):
            header_ruleset_id = record.ruleset_id
            break
    assert header_ruleset_id == BYTEFRAY_RULESET_ID
