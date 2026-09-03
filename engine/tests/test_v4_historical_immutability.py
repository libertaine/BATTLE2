"""bytefray-rules-4-alpha1/alpha2 remain byte-identical after the stable
identity is introduced (v4.0.0-rc1 Phase 2, task Sec 12).

Placement-vector and process-selection immutability for both alphas is
already covered exhaustively by ``test_v4_alpha2_placement.py``
(``test_pinned_alpha2_placement_vectors``,
``test_alpha1_placement_is_the_historical_opposite_pair``,
``test_every_pre_alpha2_ruleset_keeps_its_exact_historical_placement``) and
by the round-robin/priority process-selection suites -- all part of the
full repository suite this phase's qualification run confirms unchanged.
This file adds the two concerns those suites do not cover: that each
alpha's own *canonical match/result identity* is unchanged now that a third
Ruleset shares their exact policy field values, and that running a stable-
v4 match between two alpha matches never mutates state that would change
either alpha's result.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from battle_engine.agents import resolve_agent
from battle_engine.config import Config
from battle_engine.match_service import MatchEntrant, MatchRequest, NativeMatchService
from battle_engine.placement import resolve_direct_match_starts
from battle_engine.replay import ReplayHeader, iter_replay
from battle_engine.ruleset_policy import (
    BYTEFRAY_RULESET_V4_ALPHA1_ID,
    BYTEFRAY_RULESET_V4_ALPHA2_ID,
    BYTEFRAY_RULESET_V4_ID,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTER_SOURCE_DIRS = (
    REPO_ROOT / "agents",
    REPO_ROOT / "engine" / "src" / "battle_engine" / "data" / "starter_agents",
)


def _bootstrap_agent(tmp_path: Path, name: str) -> None:
    dest = tmp_path / "agents" / name
    if dest.exists():
        return
    for source_root in STARTER_SOURCE_DIRS:
        source = source_root / name
        if source.is_dir():
            shutil.copytree(source, dest)
            return
    raise FileNotFoundError(f"no source found for agent {name!r}")


def _run(tmp_path: Path, ruleset_id: str, seed: int, label: str) -> ReplayHeader:
    names = ("v4_claimer", "v4_scout")
    for name in names:
        _bootstrap_agent(tmp_path, name)
    specs = tuple(resolve_agent(tmp_path, name) for name in names)
    starts = resolve_direct_match_starts(
        ruleset_id=ruleset_id,
        arena_size=512,
        entrant_count=2,
        supplied_starts=[None, None],
        seed=seed,
    )
    entrants = tuple(
        MatchEntrant.python(chr(ord("A") + i), name, starts[i], spec)
        for i, (name, spec) in enumerate(zip(names, specs, strict=True))
    )
    run_dir = tmp_path / "runs" / label
    run_dir.mkdir(parents=True)
    replay_path = run_dir / "replay.jsonl"
    request = MatchRequest(
        config=Config(seed=seed, arena_size=512, instr_per_tick=8),
        entrants=entrants,
        max_ticks=50,
        replay_path=replay_path,
        verbose=False,
        ruleset_id=ruleset_id,
    )
    NativeMatchService().run(request)
    return next(r for r in iter_replay(replay_path) if isinstance(r, ReplayHeader))


def test_alpha1_and_alpha2_canonical_ids_are_pinned(tmp_path: Path):
    """v4_claimer vs v4_scout, arena 512, seed 5, ticks 50 -- pinned exactly
    as it was computed on this repository before the stable identity's
    registration, so any change to canonical-id derivation caused by
    registering a third policy sharing alpha2's field values is caught
    immediately rather than discovered later as a silent artifact
    reinterpretation."""

    alpha1 = _run(tmp_path, BYTEFRAY_RULESET_V4_ALPHA1_ID, seed=5, label="pin-a1")
    alpha2 = _run(tmp_path, BYTEFRAY_RULESET_V4_ALPHA2_ID, seed=5, label="pin-a2")

    assert alpha1.match_id == "match_b53e76a536d65e9f35b9e560"
    assert alpha1.result_id == "result_4eac520d48af9cd1ae859365"
    assert alpha2.match_id == "match_779a09b9950d0e4db27b5ddb"
    assert alpha2.result_id == "result_50d49c7732848a9541fc9a93"
    # The two alphas' ids differ from each other (already established, but
    # cheap to reconfirm here alongside the pinned values above).
    assert alpha1.match_id != alpha2.match_id


def test_stable_v4_execution_does_not_mutate_state_a_subsequent_alpha_match_reads(
    tmp_path: Path,
):
    """Runs alpha1, then a stable-v4 match, then alpha1 again (identical
    inputs) -- the second alpha1 run must reproduce the first exactly.
    Proves no cross-Ruleset shared/global state (module-level caches,
    mutable registries, RNG state) leaks between a stable-v4 execution and
    a subsequent historical one."""

    first = _run(tmp_path, BYTEFRAY_RULESET_V4_ALPHA1_ID, seed=9, label="interleave-first")
    _run(tmp_path, BYTEFRAY_RULESET_V4_ID, seed=9, label="interleave-stable")
    second = _run(tmp_path, BYTEFRAY_RULESET_V4_ALPHA1_ID, seed=9, label="interleave-second")

    assert first.match_id == second.match_id
    assert first.result_id == second.result_id
    assert first.reproducibility == second.reproducibility
