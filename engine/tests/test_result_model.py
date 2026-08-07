from __future__ import annotations

import hashlib
import json

from battle_engine.result_model import (
    ReplayReference,
    ResultEnvelope,
    read_result,
    stable_id,
    write_json_atomic,
)


def test_battle2_result_v1_round_trip_and_stable_ids(tmp_path):
    identity = {"mode": "b2", "seed": 7, "entrants": ["A", "B"]}
    match_id = stable_id("match", identity)
    envelope = ResultEnvelope(
        result_id=stable_id("result", {"match_id": match_id, "winner": "A"}),
        match_id=match_id,
        mode="b2",
        winner="A",
        termination_reason="last_agent_standing",
        ticks=4,
        score={"A": 5, "B": 0},
        replay=ReplayReference(match_id, "a" * 64, "replay.jsonl"),
    )
    path = tmp_path / "result.json"
    write_json_atomic(path, envelope.as_dict())

    assert read_result(path) == envelope
    assert stable_id("match", identity) == match_id
    assert json.loads(path.read_text())["schema"] == "battle2.result"


def test_result_replay_digest_detects_content_change(tmp_path):
    replay = tmp_path / "replay.jsonl"
    replay.write_bytes(b"first\n")
    first = hashlib.sha256(replay.read_bytes()).hexdigest()
    replay.write_bytes(b"second\n")
    assert hashlib.sha256(replay.read_bytes()).hexdigest() != first
