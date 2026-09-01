from __future__ import annotations

"""v4 alpha2 qualification: identity, artifacts, and the alpha1 firewall.

Where ``test_v4_alpha2_placement`` and ``test_v4_alpha2_scheduler`` cover the
two rule changes in isolation, this module covers what happens when a real
match runs under each Ruleset through ``NativeMatchService``: that alpha1 and
alpha2 are distinguishable identities, that alpha2 needs no schema bump, and
that introducing alpha2 leaves an alpha1 match bit-for-bit where it was.
"""

import hashlib
import json
from pathlib import Path

import pytest
from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import (
    MatchEntrant,
    MatchRequest,
    NativeMatchService,
    canonical_match_id,
)
from battle_engine.placement import seeded_seat_starts
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
)

ARENA = 256
SEED = 23
TICKS = 40

#: A two-process agent, so the round-robin selection rule has something to
#: rotate between, that also writes at an absolute address derived from the
#: alpha1 opposite-core assumption -- the exact behaviour alpha2 invalidates.
AGENT_SOURCE = '''
from battle_engine.agent_api import ActionKindV2, AgentAction, ProcessDeclaration


class SiegeAgent:
    def reset(self, context):
        self.arena_size = context.arena_size

    def declare_processes(self):
        return [
            ProcessDeclaration(id="siege", reach=self.arena_size // 2, share=0.5),
            ProcessDeclaration(id="guard", reach=8, share=0.5),
        ]

    def act(self, observation):
        if observation.self_process_id == "siege":
            target = observation.own_core_base + self.arena_size // 2
            return AgentAction(
                kind=ActionKindV2.WRITE,
                operand=target % self.arena_size,
                value=1,
            )
        return AgentAction(
            kind=ActionKindV2.WRITE, operand=observation.own_core_base, value=2
        )


def create_agent():
    return SiegeAgent()
'''

SINGLE_PROCESS_SOURCE = '''
from battle_engine.agent_api import ActionKindV2, AgentAction, ProcessDeclaration


class SoloAgent:
    def reset(self, context):
        self.arena_size = context.arena_size

    def declare_processes(self):
        return [ProcessDeclaration(id="solo", reach=8, share=1.0)]

    def act(self, observation):
        return AgentAction(
            kind=ActionKindV2.WRITE, operand=observation.own_core_base, value=3
        )


def create_agent():
    return SoloAgent()
'''


def _write_agent(root: Path, name: str, source: str) -> None:
    agent_dir = root / "agents" / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_dir.joinpath("agent.yaml").write_text(
        json.dumps(
            {
                "name": name,
                "display": name,
                "kind": "python",
                "api_version": 2,
                "entrypoint": "agent.py:create_agent",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    agent_dir.joinpath("agent.py").write_text(source, encoding="utf-8")


@pytest.fixture
def roster(tmp_path: Path) -> Path:
    _write_agent(tmp_path, "sieger", AGENT_SOURCE)
    _write_agent(tmp_path, "solo", SINGLE_PROCESS_SOURCE)
    return tmp_path


def _request(
    root: Path, replay_path: Path, ruleset_id: str, *, starts: tuple[int, int]
) -> MatchRequest:
    names = ("sieger", "solo")
    entrants = tuple(
        MatchEntrant.python(chr(ord("A") + slot), name, starts[slot], resolve_agent(root, name))
        for slot, name in enumerate(names)
    )
    return MatchRequest(
        config=Config(arena_size=ARENA, instr_per_tick=8, seed=SEED),
        entrants=entrants,
        max_ticks=TICKS,
        replay_path=replay_path,
        verbose=False,
        ruleset_id=ruleset_id,
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_alpha1_and_alpha2_are_distinct_match_identities(roster: Path) -> None:
    """Same agents, seed, arena, and seats must not collide across Rulesets.

    Ruleset identity is already a first-class axis of ``canonical_match_id``,
    so this holds even for the degenerate case where both Rulesets are handed
    the *same* explicit starts -- the semantic difference is real (round-robin
    selection) even when the placement difference has been suppressed.
    """

    alpha1 = _request(roster, roster / "a1" / "replay.jsonl", BYTEFRAY_RULESET_V4_ALPHA1_ID, starts=(0, 128))
    alpha2 = _request(roster, roster / "a2" / "replay.jsonl", BYTEFRAY_RULESET_V4_ALPHA2_ID, starts=(0, 128))
    assert canonical_match_id(alpha1) != canonical_match_id(alpha2)


def test_seeded_placement_is_reproducible_from_recorded_match_inputs(
    roster: Path,
) -> None:
    """Alpha2 placement must be recoverable from the artifact, not guessed.

    The resolved starts are what enter ``MatchRequest`` and therefore
    ``canonical_match_id``; recomputing them from the recorded seed, arena
    size, and seat count must give the same layout back.
    """

    starts = seeded_seat_starts(2, ARENA, SEED)
    request = _request(roster, roster / "run" / "replay.jsonl", BYTEFRAY_RULESET_V4_ALPHA2_ID, starts=starts)
    result = NativeMatchService().run(request)
    assert result.result_path is not None
    envelope = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert envelope["ruleset_id"] == BYTEFRAY_RULESET_V4_ALPHA2_ID
    reproducibility = envelope["reproducibility"]
    assert reproducibility["seed"] == SEED
    assert reproducibility["arena_size"] == ARENA
    assert seeded_seat_starts(2, reproducibility["arena_size"], reproducibility["seed"]) == starts


def test_alpha2_keeps_replay_schema_4(roster: Path) -> None:
    """A Ruleset change is not a schema change.

    Alpha2 records the identical process-runtime replay shape alpha1 does:
    seeded placement only changes a per-entrant ``start`` *value* that schema
    4 already carries, and round-robin only changes the order of records the
    schema already defines.
    """

    for ruleset_id in (BYTEFRAY_RULESET_V4_ALPHA1_ID, BYTEFRAY_RULESET_V4_ALPHA2_ID):
        replay_path = roster / ruleset_id / "replay.jsonl"
        request = _request(roster, replay_path, ruleset_id, starts=(0, 128))
        NativeMatchService().run(request)
        header = json.loads(replay_path.read_text(encoding="utf-8").splitlines()[0])
        assert header["schema_version"] == 4
        assert header["ruleset_id"] == ruleset_id


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_alpha2_executes_on_the_process_runtime(roster: Path) -> None:
    """Alpha2 must reach ``ProcessMatchController``, not the API-v1 runtime.

    The process runtime is what publishes per-process replay snapshots, so
    their presence is the observable proof of which runtime ran.
    """

    replay_path = roster / "proc" / "replay.jsonl"
    NativeMatchService().run(
        _request(roster, replay_path, BYTEFRAY_RULESET_V4_ALPHA2_ID, starts=(0, 128))
    )
    records = [
        json.loads(line) for line in replay_path.read_text(encoding="utf-8").splitlines()
    ]
    ticks = [record for record in records if record.get("record_type") == "tick"]
    assert ticks
    anchors = {
        (snapshot["entrant_id"], snapshot["process_id"])
        for record in ticks
        for snapshot in record.get("processes", ())
    }
    assert anchors == {("A", "siege"), ("A", "guard"), ("B", "solo")}


def test_alpha2_matches_are_deterministic(roster: Path) -> None:
    digests = []
    for run in range(2):
        replay_path = roster / f"det{run}" / "replay.jsonl"
        NativeMatchService().run(
            _request(
                roster,
                replay_path,
                BYTEFRAY_RULESET_V4_ALPHA2_ID,
                starts=seeded_seat_starts(2, ARENA, SEED),
            )
        )
        digests.append(hashlib.sha256(replay_path.read_bytes()).hexdigest())
    assert digests[0] == digests[1]


def test_alpha2_changes_the_match_a_multi_process_agent_plays(roster: Path) -> None:
    """The two rule changes must actually reach gameplay.

    Held at identical explicit starts so only the scheduler delta is in play,
    an entrant with two processes gets a different sequence of writes under
    alpha2 than under alpha1 -- proving round-robin is wired into the real
    match path and not only into the unit-level selection helper.
    """

    digests = {}
    for ruleset_id in (BYTEFRAY_RULESET_V4_ALPHA1_ID, BYTEFRAY_RULESET_V4_ALPHA2_ID):
        replay_path = roster / f"cmp-{ruleset_id}" / "replay.jsonl"
        NativeMatchService().run(_request(roster, replay_path, ruleset_id, starts=(0, 128)))
        body = "\n".join(replay_path.read_text(encoding="utf-8").splitlines()[1:])
        digests[ruleset_id] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digests[BYTEFRAY_RULESET_V4_ALPHA1_ID] != digests[BYTEFRAY_RULESET_V4_ALPHA2_ID]


# ---------------------------------------------------------------------------
# The alpha1 firewall
# ---------------------------------------------------------------------------


def test_running_alpha2_first_does_not_perturb_a_later_alpha1_match(
    roster: Path,
) -> None:
    """No shared mutable state leaks between the two Rulesets.

    The round-robin cursor is per-controller and placement is a pure
    function, so an alpha2 match executed first must leave a subsequent
    alpha1 match byte-identical to one run in a fresh process.
    """

    def run_alpha1(label: str) -> str:
        replay_path = roster / label / "replay.jsonl"
        NativeMatchService().run(
            _request(roster, replay_path, BYTEFRAY_RULESET_V4_ALPHA1_ID, starts=(0, 128))
        )
        body = "\n".join(replay_path.read_text(encoding="utf-8").splitlines()[1:])
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    clean = run_alpha1("firewall-clean")
    NativeMatchService().run(
        _request(
            roster,
            roster / "firewall-a2" / "replay.jsonl",
            BYTEFRAY_RULESET_V4_ALPHA2_ID,
            starts=seeded_seat_starts(2, ARENA, SEED),
        )
    )
    assert run_alpha1("firewall-after") == clean


def test_alpha1_still_places_omitted_starts_opposite_each_other() -> None:
    """Restated at this level because it is the assumption the entire alpha1
    agent corpus, and every alpha1 replay, was recorded under."""

    from battle_engine.placement import resolve_direct_match_starts

    assert resolve_direct_match_starts(
        ruleset_id=BYTEFRAY_RULESET_V4_ALPHA1_ID,
        arena_size=ARENA,
        entrant_count=2,
        supplied_starts=[None, None],
    ) == (0, ARENA // 2)
