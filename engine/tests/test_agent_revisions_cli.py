"""``bytefray agents revisions list|show|restore`` (docs/specs/agent_revision.md Sec 7).

Exercises the CLI surface over the content-addressed revision store:
discovery relevance filtering (recorded ``source_agent_id`` breadcrumb vs.
live-source match), malformed-sibling isolation, provenance display, and
restore security (containment, non-empty-target refusal, and refusing to
write a corrupted/tampered snapshot before any file is written).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from battle_engine.agent_revisions import agent_revisions_root, archive_agent_revision
from battle_engine.agent_revisions_cli import main as revisions_main


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _make_agent(root: Path, name: str = "sample") -> Path:
    agent_dir = root / name
    _write(agent_dir / "agent.yaml", "kind: python\napi_version: 1\n")
    _write(agent_dir / "agent.py", "def create_agent():\n    return None\n")
    return agent_dir


def _make_external_directory_link(link: Path, target: Path) -> None:
    """Same technique as ``test_agent_revisions.py``'s ``_make_directory_link``:
    a Windows NTFS junction (no elevation required) or a POSIX directory
    symlink, skipped if this environment permits neither.
    """

    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"Directory junction creation unavailable: {result.stderr.strip()}")
        return
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted in this environment.")


@pytest.fixture(autouse=True)
def _data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    return tmp_path


def _run(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str, str]:
    exit_code = revisions_main(args)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_empty_store_does_not_crash(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    exit_code, out, _ = _run(["list", "no-such-agent"], capsys)
    assert exit_code == 0
    assert "No preserved revisions" in out


def test_list_filters_by_recorded_source_agent_id(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    exit_code, out, _ = _run(["list", "agent-a"], capsys)
    assert exit_code == 0
    assert result.agent_revision_id in out

    exit_code, out, _ = _run(["list", "unrelated-agent"], capsys)
    assert exit_code == 0
    assert result.agent_revision_id not in out


def test_list_includes_revision_matching_live_source_despite_different_recorded_owner(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    """Content-addressed dedup (Sec 1.2/3): a revision's recorded
    ``source_agent_id`` names whichever agent happened to archive first --
    a *different*, byte-identical agent must still see it in its own
    ``list`` via a live-source fingerprint match, not just via the
    (non-authoritative) recorded breadcrumb.
    """

    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    _make_agent(agents_dir, "agent-b")  # byte-identical content
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    exit_code, out, _ = _run(["list", "agent-b"], capsys)
    assert exit_code == 0
    assert result.agent_revision_id in out
    assert "matches current live source" in out
    # The recorded breadcrumb is shown honestly as belonging to agent-a, not
    # silently rewritten to claim agent-b originally archived it.
    assert "source_agent_id='agent-a'" in out


def test_list_malformed_sibling_does_not_prevent_healthy_listing(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    # A malformed sibling revision directory: manifest.json is not valid JSON.
    malformed_dir = store / ("agent-revision_" + "f" * 64)
    malformed_dir.mkdir(parents=True)
    (malformed_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")

    exit_code, out, _ = _run(["list", "agent-a"], capsys)
    assert exit_code == 0
    assert result.agent_revision_id in out
    assert "1 unreadable/malformed sibling" in out


def test_list_incomplete_revision_shown_as_incomplete(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    agents_dir = _data_root / "agents"
    agent_dir = _make_agent(agents_dir, "agent-a")
    # An unreadable-omission-producing entry is awkward to construct
    # portably; a directory with an external-target symlink is covered
    # elsewhere (test_agent_revisions.py) -- here we just verify the CLI
    # renders whatever completeness the manifest already records, by
    # hand-writing an incomplete manifest onto an otherwise valid store
    # entry produced by a real archival call.
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_dir, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None
    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["complete"] = False
    manifest["omitted"] = [{"relative_path": "external.py", "reason": "external_target", "target": "../outside.py"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    exit_code, out, _ = _run(["list", "agent-a"], capsys)
    assert exit_code == 0
    assert "INCOMPLETE" in out


def test_list_json_output_is_well_formed(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")

    exit_code, out, _ = _run(["list", "agent-a", "--json"], capsys)
    assert exit_code == 0
    data = json.loads(out)
    assert data["agent_id"] == "agent-a"
    assert data["revisions"][0]["revision_id"] == result.agent_revision_id


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_unknown_revision_reports_error_without_crashing(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, _, err = _run(["show", "agent-revision_" + "0" * 64], capsys)
    assert exit_code == 2
    assert "no readable revision found" in err


def test_show_healthy_revision_reports_verified_true(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")

    exit_code, out, _ = _run(["show", result.agent_revision_id], capsys)
    assert exit_code == 0
    assert "verified" in out.lower()
    assert "complete: True" in out


def test_show_tampered_snapshot_reports_verified_false_not_a_crash(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    (store / result.agent_revision_id / "files" / "agent.py").write_bytes(b"tampered content")

    exit_code, out, _ = _run(["show", result.agent_revision_id], capsys)
    assert exit_code == 1
    assert "verified" in out.lower()
    assert "False" in out


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def test_restore_default_target_under_data_root(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")

    exit_code, _, _ = _run(["restore", result.agent_revision_id], capsys)
    assert exit_code == 0
    restored = _data_root / "agent_revisions_restored" / result.agent_revision_id
    assert (restored / "agent.py").is_file()
    assert (restored / "agent.py").read_bytes() == (agent_a / "agent.py").read_bytes()


def test_restore_refuses_nonempty_target_without_force(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")

    target = _data_root / "occupied"
    _write(target / "keep.txt", "do not clobber")

    exit_code, _, err = _run(["restore", result.agent_revision_id, "--to", str(target)], capsys)
    assert exit_code == 1
    assert "not empty" in err.lower()
    assert (target / "keep.txt").read_text(encoding="utf-8") == "do not clobber"


def test_restore_force_allows_overwrite(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")

    target = _data_root / "occupied"
    _write(target / "keep.txt", "still here")

    exit_code, _, _ = _run(["restore", result.agent_revision_id, "--to", str(target), "--force"], capsys)
    assert exit_code == 0
    assert (target / "agent.py").is_file()


def test_restore_incomplete_revision_warns_not_silently_partial(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    """A genuinely incomplete revision (a real external-target omission,
    not a hand-corrupted manifest -- which would instead fail the restore
    pre-verification check entirely, covered separately below) must still
    restore what *was* captured, with an explicit warning that the result
    is partial -- never silently presented as a complete restore.
    """

    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    outside_dir = _data_root / "outside"
    _write(outside_dir / "external.py", "external content")
    _make_external_directory_link(agent_a / "linked", outside_dir)

    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None
    assert result.complete is False

    exit_code, out, _ = _run(["restore", result.agent_revision_id], capsys)
    assert exit_code == 0
    assert "WARNING" in out
    assert "INCOMPLETE" in out


def test_restore_tampered_snapshot_fails_before_writing_any_file(
    _data_root: Path, capsys: pytest.CaptureFixture
) -> None:
    """A corrupted/tampered canonical snapshot must never be silently
    restored as trusted output (v0.8 audit requirement) -- the restore must
    fail, and the target directory must end up with nothing written to it.
    """

    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    (store / result.agent_revision_id / "files" / "agent.py").write_bytes(b"corrupted after archival")

    target = _data_root / "restore-target"
    exit_code, _, err = _run(["restore", result.agent_revision_id, "--to", str(target)], capsys)
    assert exit_code == 1
    assert "does not verify" in err.lower() or "corrupted" in err.lower()
    assert not target.exists() or not any(target.iterdir())


def test_restore_rejects_manifest_path_escape(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    agents_dir = _data_root / "agents"
    agent_a = _make_agent(agents_dir, "agent-a")
    store = agent_revisions_root(_data_root)
    result = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    assert result.agent_revision_id is not None

    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = ["../../escaped.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = _data_root / "restore-target"
    exit_code, _, _ = _run(["restore", result.agent_revision_id, "--to", str(target)], capsys)
    assert exit_code == 1
    assert not (_data_root / "escaped.py").exists()


def test_restore_unknown_revision_reports_error(_data_root: Path, capsys: pytest.CaptureFixture) -> None:
    exit_code, _, err = _run(["restore", "agent-revision_" + "0" * 64], capsys)
    assert exit_code == 2
    assert "no archived revision" in err.lower()
