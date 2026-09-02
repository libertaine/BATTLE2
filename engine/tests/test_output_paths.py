from __future__ import annotations

from pathlib import Path

import pytest
from battle_engine import cli, match_service


def _match_arguments(replay: str | Path | None = None) -> list[str]:
    arguments = [
        "--ticks", "2",
        "--arena", "128",
        "--a-type", "writer",
        "--b-type", "runner",
        "--b-start", "64",
        "--quiet",
    ]
    if replay is not None:
        arguments.extend(("--replay", str(replay)))
    return arguments


def test_default_replay_and_summary_use_the_data_root(monkeypatch, tmp_path):
    data_root = tmp_path / "xdg data" / "bytefray"
    working = tmp_path / "unrelated working directory"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setattr(cli, "get_data_root", lambda: data_root)

    assert cli.main(_match_arguments()) == 0

    replay = data_root / "runs" / "_loose" / "replay.jsonl"
    assert replay.is_file()
    assert replay.with_name("summary.json").is_file()
    assert not (working / "replay.jsonl").exists()
    assert not (working / "summary.json").exists()


def test_explicit_relative_replay_remains_relative_to_working_directory(
    monkeypatch, tmp_path
):
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setattr(cli, "get_data_root", lambda: tmp_path / "data")

    assert cli.main(_match_arguments(Path("chosen") / "relative.jsonl")) == 0

    replay = working / "chosen" / "relative.jsonl"
    assert replay.is_file()
    assert replay.with_name("summary.json").is_file()
    assert not (working / "summary.json").exists()


def test_explicit_absolute_replay_keeps_canonical_summary_beside_it(
    monkeypatch, tmp_path
):
    working = tmp_path / "working"
    replay = tmp_path / "absolute output" / "match.jsonl"
    working.mkdir()
    monkeypatch.chdir(working)

    assert cli.main(_match_arguments(replay)) == 0

    assert replay.is_file()
    assert replay.with_name("summary.json").is_file()
    assert not (working / "summary.json").exists()


def test_controlled_match_failure_removes_replay_and_stale_summary(
    monkeypatch, tmp_path
):
    replay = tmp_path / "failed" / "replay.jsonl"
    summary = replay.with_name("summary.json")
    replay.parent.mkdir()
    replay.write_text("old replay\n", encoding="utf-8")
    summary.write_text("old summary\n", encoding="utf-8")

    def fail_run(self, max_ticks=10000, verbose=True):
        del self, max_ticks, verbose
        raise RuntimeError("controlled match failure")

    monkeypatch.setattr(match_service.Kernel, "run", fail_run)

    with pytest.raises(RuntimeError, match="controlled match failure"):
        cli.main(_match_arguments(replay))

    assert not replay.exists()
    assert not summary.exists()


def _capture_match_request(monkeypatch):
    """Intercept the ``MatchRequest`` the CLI builds without running a match."""
    captured: dict[str, object] = {}

    def capture_run(self, request):
        del self
        captured["request"] = request
        raise RuntimeError("stop before executing the match")

    monkeypatch.setattr(match_service.NativeMatchService, "run", capture_run)
    return captured


def test_trace_flag_omitted_leaves_match_request_trace_path_none(
    monkeypatch, tmp_path
):
    captured = _capture_match_request(monkeypatch)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="stop before executing the match"):
        cli.main(_match_arguments(tmp_path / "replay.jsonl"))

    assert captured["request"].trace_path is None


def test_explicit_relative_trace_path_resolves_relative_to_working_directory(
    monkeypatch, tmp_path
):
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    captured = _capture_match_request(monkeypatch)

    arguments = _match_arguments(working / "replay.jsonl") + [
        "--trace",
        str(Path("chosen") / "relative-trace.jsonl"),
    ]
    with pytest.raises(RuntimeError, match="stop before executing the match"):
        cli.main(arguments)

    assert captured["request"].trace_path == working / "chosen" / "relative-trace.jsonl"


def test_explicit_absolute_trace_path_remains_absolute(monkeypatch, tmp_path):
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    captured = _capture_match_request(monkeypatch)

    trace = tmp_path / "absolute output" / "trace.jsonl"
    arguments = _match_arguments(working / "replay.jsonl") + ["--trace", str(trace)]
    with pytest.raises(RuntimeError, match="stop before executing the match"):
        cli.main(arguments)

    assert captured["request"].trace_path == trace
