from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from battle_engine.agent_api import local_source_fingerprint
from battle_engine.agent_revisions import (
    AGENT_REVISION_FINGERPRINT_VERSION,
    REASON_EXTERNAL_TARGET,
    REASON_INTERNAL_SYMLINKED_DIRECTORY,
    REASON_NOT_A_FILE,
    REASON_UNREADABLE,
    AgentFileEntry,
    AgentFileWalkResult,
    RevisionNotFoundError,
    RevisionRestoreError,
    agent_revision_fingerprint,
    agent_revision_id,
    archive_agent_revision,
    archive_agent_revision_from_walk,
    list_revisions,
    local_python_subset_fingerprint,
    read_manifest,
    restore_revision,
    verify_revision,
    walk_agent_files,
)


def _write(path: Path, content: str = "x") -> None:
    # write_bytes, not write_text -- write_text's default newline
    # translation turns "\n" into "\r\n" on Windows, which would make
    # exact-byte-content assertions below platform-dependent.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _make_agent(root: Path, name: str = "sample") -> Path:
    agent_dir = root / name
    _write(agent_dir / "agent.yaml", "kind: python\napi_version: 1\n")
    _write(agent_dir / "agent.py", "def create_agent():\n    return None\n")
    return agent_dir


def _symlink(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted in this environment.")


def _make_directory_link(link: Path, target: Path) -> None:
    """A directory-to-directory link, preferring a Windows junction.

    Windows NTFS directory junctions (unlike symbolic links) require no
    special privilege/Developer Mode, so this exercises the real
    ``_is_link_like``/``os.readlink`` behavior on stock Windows dev
    machines -- including the ``is_symlink() is False`` /
    ``is_junction() is True`` case ``_is_link_like`` exists specifically to
    catch. POSIX falls back to an ordinary directory symlink.
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


# ---------------------------------------------------------------------------
# Fingerprint determinism / sensitivity
# ---------------------------------------------------------------------------


def test_fingerprint_deterministic_repeated_calls(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path)
    first = agent_revision_fingerprint(agent_dir)
    second = agent_revision_fingerprint(agent_dir)
    assert first is not None
    assert first == second


def test_fingerprint_stable_across_relocated_directory(tmp_path: Path) -> None:
    original = _make_agent(tmp_path / "here", "sample")
    moved_root = tmp_path / "elsewhere" / "nested"
    moved_root.mkdir(parents=True)
    relocated = moved_root / "sample-renamed"
    original.rename(relocated)

    # Recompute the original's fingerprint from a freshly-built identical
    # tree at a different absolute path/name and compare.
    rebuilt = _make_agent(tmp_path / "rebuilt-elsewhere", "different-name")
    assert agent_revision_fingerprint(relocated) == agent_revision_fingerprint(rebuilt)


def test_fingerprint_changes_on_content_change(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path)
    before = agent_revision_fingerprint(agent_dir)
    _write(agent_dir / "agent.py", "def create_agent():\n    return 'changed'\n")
    after = agent_revision_fingerprint(agent_dir)
    assert before != after


def test_fingerprint_unaffected_by_mtime_only_change(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path)
    before = agent_revision_fingerprint(agent_dir)
    target = agent_dir / "agent.py"
    new_time = time.time() + 120
    os.utime(target, (new_time, new_time))
    after = agent_revision_fingerprint(agent_dir)
    assert before == after


def test_manifest_only_edit_changes_fingerprint(tmp_path: Path) -> None:
    """A manifest-only edit (display/defaults) must change the wider
    revision fingerprint even though it would not change
    agent_api.local_source_fingerprint (Sec 1.1/1.4 of
    docs/specs/agent_revision.md -- grounds why the two fingerprints must
    stay independent)."""

    agent_dir = _make_agent(tmp_path)
    before = agent_revision_fingerprint(agent_dir)
    _write(agent_dir / "agent.yaml", "kind: python\napi_version: 1\ndisplay: Renamed\n")
    after = agent_revision_fingerprint(agent_dir)
    assert before != after


def test_missing_agent_dir_returns_none(tmp_path: Path) -> None:
    assert agent_revision_fingerprint(tmp_path / "does-not-exist") is None
    walk = walk_agent_files(tmp_path / "does-not-exist")
    assert walk.entries == ()
    assert walk.omitted == ()
    assert walk.complete is True


# ---------------------------------------------------------------------------
# Inclusion/exclusion contract
# ---------------------------------------------------------------------------


def test_pycache_and_git_are_invisible_not_merely_omitted(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path)
    _write(agent_dir / "__pycache__" / "agent.cpython-313.pyc", "binary-ish")
    _write(agent_dir / ".git" / "HEAD", "ref: refs/heads/main")
    _write(agent_dir / ".git" / "objects" / "aa" / "bbbb", "blob")

    walk = walk_agent_files(agent_dir)
    paths = {e.relative_path for e in walk.entries}
    omitted_paths = {o.relative_path for o in walk.omitted}
    assert not any(p.startswith("__pycache__") for p in paths | omitted_paths)
    assert not any(p.startswith(".git") for p in paths | omitted_paths)
    assert walk.complete is True


def test_non_python_files_are_included(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path)
    _write(agent_dir / "model.blob", "binary-ish-content")
    _write(agent_dir / "model.meta.json", '{"trained": true}')
    _write(agent_dir / ".hidden-config", "secret=not-really")

    walk = walk_agent_files(agent_dir)
    paths = {e.relative_path for e in walk.entries}
    assert "model.blob" in paths
    assert "model.meta.json" in paths
    assert ".hidden-config" in paths


# ---------------------------------------------------------------------------
# Symlink handling -- the core of this phase's explicit requirement
# ---------------------------------------------------------------------------


def test_external_file_symlink_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    outside = tmp_path / "outside.py"
    _write(outside, "SECRET = 1\n")
    link = agent_dir / "helper.py"
    _symlink(link, outside)

    walk = walk_agent_files(agent_dir)
    assert walk.complete is False
    assert "helper.py" not in {e.relative_path for e in walk.entries}
    omission = next(o for o in walk.omitted if o.relative_path == "helper.py")
    assert omission.reason == REASON_EXTERNAL_TARGET
    assert omission.target is not None
    assert "SECRET" not in "".join(e.content.decode("utf-8", "ignore") for e in walk.entries)


def test_internal_file_symlink_is_dereferenced_and_included(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "real_helper.py", "VALUE = 42\n")
    link = agent_dir / "helper.py"
    _symlink(link, agent_dir / "real_helper.py")

    walk = walk_agent_files(agent_dir)
    assert walk.complete is True
    entry = next(e for e in walk.entries if e.relative_path == "helper.py")
    assert entry.content == b"VALUE = 42\n"


def test_walk_dir_branch_logic_for_simulated_file_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise ``_walk_dir``'s file-link branch (dereference-if-inside,
    omit-if-outside) without depending on OS symlink-creation privilege --
    which the two real-symlink tests above need and which this sandbox does
    not grant (``os.symlink`` raises ``WinError 1314`` here without
    Developer Mode/admin). ``_is_link_like``/``_read_link_target`` are
    monkeypatched to treat two ordinary files as if they were links, so the
    real branch logic in ``agent_revisions._walk_dir`` runs unmodified;
    only *how a path is discovered to be link-like* is faked, not what the
    walker then does about it. The real-symlink tests remain the
    end-to-end check wherever the environment permits (CI/Linux, or a
    Windows box with Developer Mode enabled)."""

    import battle_engine.agent_revisions as revisions_module

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "looks_internal.py", "INTERNAL = 1\n")
    outside_dir = tmp_path / "outside"
    _write(outside_dir / "looks_external.py", "EXTERNAL = 1\n")
    # A real file standing in for "the walker believes this path is a link
    # whose target is the outside file" -- its own content is irrelevant,
    # since an external target must never have its bytes read.
    _write(agent_dir / "looks_external.py", "should never be read as content\n")

    real_is_link_like = revisions_module._is_link_like
    real_classify = revisions_module._classify_and_resolve

    def fake_is_link_like(path: Path) -> bool:
        if path.name in ("looks_internal.py", "looks_external.py"):
            return True
        return real_is_link_like(path)

    def fake_read_link_target(path: Path) -> str | None:
        if path.name == "looks_internal.py":
            return str(agent_dir / "real_internal_target.py")
        if path.name == "looks_external.py":
            return str(outside_dir / "looks_external.py")
        return None

    def fake_classify(child: Path, base: Path):  # type: ignore[no-untyped-def]
        if child.name == "looks_internal.py":
            return (agent_dir / "real_internal_target.py").resolve(), True, None
        if child.name == "looks_external.py":
            return (outside_dir / "looks_external.py").resolve(), False, None
        return real_classify(child, base)

    _write(agent_dir / "real_internal_target.py", "INTERNAL_TARGET = 1\n")

    monkeypatch.setattr(revisions_module, "_is_link_like", fake_is_link_like)
    monkeypatch.setattr(revisions_module, "_read_link_target", fake_read_link_target)
    monkeypatch.setattr(revisions_module, "_classify_and_resolve", fake_classify)

    walk = revisions_module.walk_agent_files(agent_dir)

    assert walk.complete is False
    internal_entry = next((e for e in walk.entries if e.relative_path == "looks_internal.py"), None)
    assert internal_entry is not None
    assert internal_entry.content == b"INTERNAL_TARGET = 1\n"

    external_omission = next(o for o in walk.omitted if o.relative_path == "looks_external.py")
    assert external_omission.reason == revisions_module.REASON_EXTERNAL_TARGET
    assert external_omission.target == str(outside_dir / "looks_external.py")
    assert not any(
        e.relative_path == "looks_external.py" and e.content == b"EXTERNAL = 1\n"
        for e in walk.entries
    )


def test_broken_symlink_is_reported_not_a_file(tmp_path: Path) -> None:
    """A dangling symlink resolving *inside* ``agent_dir`` to a target that
    does not exist -- neither a file nor a directory -- must be reported
    with ``REASON_NOT_A_FILE`` (v0.8 audit checklist's "broken link"), not
    silently dropped or mistaken for a legitimate internal dereference."""

    agent_dir = _make_agent(tmp_path / "agent")
    link = agent_dir / "broken.py"
    _symlink(link, agent_dir / "does_not_exist.py")

    walk = walk_agent_files(agent_dir)
    assert walk.complete is False
    omission = next(o for o in walk.omitted if o.relative_path == "broken.py")
    assert omission.reason == REASON_NOT_A_FILE


def test_unreadable_file_is_reported_not_silently_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file this process cannot read (permission denied, a transient I/O
    error) must be reported with ``REASON_UNREADABLE``, never silently
    excluded from ``omitted`` the way ``local_source_fingerprint``'s own
    walk today swallows the same condition (Sec 2.2). Windows permission
    semantics don't reliably let a test construct a real permission-denied
    file without administrative privilege, so this monkeypatches
    ``Path.read_bytes`` to fail for one specific file -- the walker's own
    branch logic (catch, classify, record) still runs unmodified."""

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "locked.py", "LOCKED = 1\n")

    original_read_bytes = Path.read_bytes

    def flaky_read_bytes(self: Path) -> bytes:  # type: ignore[override]
        if self.name == "locked.py":
            raise OSError("simulated permission denied")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    walk = walk_agent_files(agent_dir)
    assert walk.complete is False
    omission = next(o for o in walk.omitted if o.relative_path == "locked.py")
    assert omission.reason == REASON_UNREADABLE
    assert "locked.py" not in {e.relative_path for e in walk.entries}


def test_external_directory_symlink_is_one_omission_never_traversed(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    outside_dir = tmp_path / "outside_dir"
    _write(outside_dir / "secret1.py", "A = 1\n")
    _write(outside_dir / "secret2.py", "B = 2\n")
    link = agent_dir / "linked_dir"
    _make_directory_link(link, outside_dir)

    walk = walk_agent_files(agent_dir)
    assert walk.complete is False
    omitted_paths = [o.relative_path for o in walk.omitted]
    assert omitted_paths == ["linked_dir"]
    assert walk.omitted[0].reason == REASON_EXTERNAL_TARGET
    assert not any(e.relative_path.startswith("linked_dir/") for e in walk.entries)


def test_internal_directory_symlink_is_omitted_but_real_path_still_included(
    tmp_path: Path,
) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    real_subdir = agent_dir / "real_subdir"
    _write(real_subdir / "inner.py", "C = 3\n")
    link = agent_dir / "linked_subdir"
    _make_directory_link(link, real_subdir)

    walk = walk_agent_files(agent_dir)
    omission = next(o for o in walk.omitted if o.relative_path == "linked_subdir")
    assert omission.reason == REASON_INTERNAL_SYMLINKED_DIRECTORY
    # The real, non-symlinked path into the same content is still included.
    assert any(e.relative_path == "real_subdir/inner.py" for e in walk.entries)
    # It is not duplicated under the symlinked path.
    assert not any(e.relative_path.startswith("linked_subdir/") for e in walk.entries)


# ---------------------------------------------------------------------------
# Windows reparse-point (junction) hardening -- Ultra review BLOCKER 1
# ---------------------------------------------------------------------------


def test_junction_detected_without_path_is_junction_attribute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the Ultra-review BLOCKER: the previous
    implementation detected a junction via ``getattr(path, "is_junction",
    None)``, an attribute Python only added in 3.12. On 3.10/3.11 that
    getattr silently returned ``None`` (never raised), so a junction fell
    through as an ordinary directory and was traversed like one -- external
    content behind it could enter the walk/archive. The fix (``os.lstat``'s
    ``st_file_attributes`` reparse-point bit) does not reference
    ``Path.is_junction`` at all, so removing that attribute from
    ``pathlib.Path`` for this test -- exactly its state on every pre-3.12
    interpreter -- must not change detection outcome one bit."""

    if sys.platform != "win32":
        pytest.skip("Windows-only: exercises real NTFS junction detection.")
    monkeypatch.delattr(Path, "is_junction", raising=False)

    agent_dir = _make_agent(tmp_path / "agent")
    outside_dir = tmp_path / "outside_dir"
    _write(outside_dir / "secret.py", "SECRET = 1\n")
    link = agent_dir / "linked_dir"
    _make_directory_link(link, outside_dir)

    walk = walk_agent_files(agent_dir)

    assert walk.complete is False
    omitted_paths = [o.relative_path for o in walk.omitted]
    assert omitted_paths == ["linked_dir"]
    assert walk.omitted[0].reason == REASON_EXTERNAL_TARGET
    assert not any(e.relative_path.startswith("linked_dir/") for e in walk.entries)
    assert "SECRET" not in "".join(e.content.decode("utf-8", "ignore") for e in walk.entries)


def test_self_referential_junction_at_agent_root_cannot_recurse(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    loop = agent_dir / "self_loop"
    _make_directory_link(loop, agent_dir)

    walk = walk_agent_files(agent_dir)  # must return, not recurse without bound

    omission = next(o for o in walk.omitted if o.relative_path == "self_loop")
    assert omission.reason == REASON_INTERNAL_SYMLINKED_DIRECTORY
    assert not any(e.relative_path.startswith("self_loop/") for e in walk.entries)
    assert walk.complete is False


def test_ancestor_junction_cannot_recurse(tmp_path: Path) -> None:
    """A junction nested a few levels down that points back at one of its
    own ancestor directories -- never traversed either, for the same
    reason a direct self-loop isn't: dereferencing it would require cycle
    detection this walker deliberately avoids needing by never descending
    into *any* directory symlink/junction (Sec 2.2 of
    docs/specs/agent_revision.md)."""

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "top.py", "TOP = 1\n")
    nested = agent_dir / "level1" / "level2"
    _write(nested / "inner.py", "INNER = 1\n")
    loop = nested / "loop_to_root"
    _make_directory_link(loop, agent_dir)

    walk = walk_agent_files(agent_dir)

    omission = next(
        o for o in walk.omitted if o.relative_path == "level1/level2/loop_to_root"
    )
    assert omission.reason == REASON_INTERNAL_SYMLINKED_DIRECTORY
    assert sum(1 for o in walk.omitted if o.relative_path.endswith("loop_to_root")) == 1
    assert not any(e.relative_path.startswith("level1/level2/loop_to_root/") for e in walk.entries)
    paths = {e.relative_path for e in walk.entries}
    assert paths == {"agent.yaml", "agent.py", "top.py", "level1/level2/inner.py"}


def test_archive_never_stores_external_junction_content(tmp_path: Path) -> None:
    """Non-Python external content reached only through an external
    junction/symlink must never enter the revision store -- neither as a
    file with that name, nor as bytes hiding inside some other stored
    file."""

    agent_dir = _make_agent(tmp_path / "agent")
    outside_dir = tmp_path / "outside_dir"
    _write(outside_dir / "secret_agent.py", "SECRET_PAYLOAD = 'do-not-leak'\n")
    link = agent_dir / "linked_dir"
    _make_directory_link(link, outside_dir)
    store = tmp_path / "store"

    result = archive_agent_revision(agent_dir, store_root=store)

    assert result.archived is True
    assert result.complete is False
    assert result.agent_revision_id is not None
    files_dir = store / result.agent_revision_id / "files"
    stored_files = [p for p in files_dir.rglob("*") if p.is_file()]
    assert not any(p.name == "secret_agent.py" for p in stored_files)
    assert "linked_dir" not in {p.name for p in files_dir.iterdir()}
    assert not any(b"SECRET_PAYLOAD" in p.read_bytes() for p in stored_files)

    manifest = read_manifest(store, result.agent_revision_id)
    assert manifest is not None
    omission = next(o for o in manifest["omitted"] if o["relative_path"] == "linked_dir")
    assert omission["reason"] == REASON_EXTERNAL_TARGET


def test_completeness_and_fingerprint_reflect_omissions(tmp_path: Path) -> None:
    plain = _make_agent(tmp_path / "plain")
    fp_plain = agent_revision_fingerprint(plain)

    with_external_link = _make_agent(tmp_path / "with-link")
    outside = tmp_path / "some_target.py"
    _write(outside, "Z = 1\n")
    _symlink(with_external_link / "helper.py", outside)
    fp_with_link = agent_revision_fingerprint(with_external_link)

    assert fp_plain != fp_with_link

    walk = walk_agent_files(with_external_link)
    assert walk.complete is False


# ---------------------------------------------------------------------------
# Revision ID
# ---------------------------------------------------------------------------


def test_agent_revision_id_uses_full_digest_and_stable_prefix() -> None:
    fingerprint = "a" * 64
    revision_id = agent_revision_id(fingerprint)
    assert revision_id == f"agent-revision_{fingerprint}"
    assert len(revision_id.split("_", 1)[1]) == 64


# ---------------------------------------------------------------------------
# Archival / storage
# ---------------------------------------------------------------------------


def test_archive_writes_snapshot_readable_via_manifest(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"

    result = archive_agent_revision(agent_dir, store_root=store)

    assert result.archived is True
    assert result.error is None
    assert result.agent_revision_id is not None
    manifest = read_manifest(store, result.agent_revision_id)
    assert manifest is not None
    assert manifest["schema"] == "bytefray.agent_revision"
    assert manifest["fingerprint_version"] == AGENT_REVISION_FINGERPRINT_VERSION
    assert set(manifest["files"]) == {"agent.yaml", "agent.py"}
    assert verify_revision(store, result.agent_revision_id) is True


def test_archive_records_source_agent_id_informationally_only(tmp_path: Path) -> None:
    store = tmp_path / "store"
    agent_a = _make_agent(tmp_path / "a", "agent-a")
    agent_b = _make_agent(tmp_path / "b", "agent-b")  # byte-identical content

    first = archive_agent_revision(agent_a, store_root=store, source_agent_id="agent-a")
    second = archive_agent_revision(agent_b, store_root=store, source_agent_id="agent-b")

    assert first.agent_revision_id == second.agent_revision_id
    manifest = read_manifest(store, first.agent_revision_id)
    assert manifest is not None
    # First writer wins -- source_agent_id is informational, not identity,
    # and a later archival of identical content under a different catalog
    # id does not overwrite it (Sec 3 of docs/specs/agent_revision.md).
    assert manifest["source_agent_id"] == "agent-a"


def test_archive_agent_revision_from_walk_matches_archive_agent_revision(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store_a = tmp_path / "store-a"
    store_b = tmp_path / "store-b"

    via_convenience = archive_agent_revision(agent_dir, store_root=store_a)
    walk = walk_agent_files(agent_dir)
    via_walk = archive_agent_revision_from_walk(walk, store_root=store_b)

    assert via_convenience.agent_revision_id == via_walk.agent_revision_id
    assert via_convenience.complete == via_walk.complete
    assert verify_revision(store_b, via_walk.agent_revision_id) is True


def test_local_python_subset_fingerprint_matches_local_source_fingerprint(
    tmp_path: Path,
) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "helper.py", "HELPER = 1\n")
    _write(agent_dir / "model.blob", "not python, must not affect either value")

    walk = walk_agent_files(agent_dir)
    subset = local_python_subset_fingerprint(walk)
    direct = local_source_fingerprint(agent_dir)

    assert subset is not None
    assert subset == direct


def test_local_python_subset_fingerprint_none_when_no_py_files(tmp_path: Path) -> None:
    agent_dir = tmp_path / "blob-only"
    _write(agent_dir / "model.blob", "no python here")
    walk = walk_agent_files(agent_dir)
    assert local_python_subset_fingerprint(walk) is None
    assert local_source_fingerprint(agent_dir) is None


def test_local_python_subset_fingerprint_changes_with_py_content(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    before = local_python_subset_fingerprint(walk_agent_files(agent_dir))
    _write(agent_dir / "agent.py", "def create_agent():\n    return 'changed'\n")
    after = local_python_subset_fingerprint(walk_agent_files(agent_dir))
    assert before != after
    assert after == local_source_fingerprint(agent_dir)


def test_archive_dedups_identical_content_from_different_directories(tmp_path: Path) -> None:
    store = tmp_path / "store"
    agent_a = _make_agent(tmp_path / "a", "agent-a")
    agent_b = _make_agent(tmp_path / "b", "agent-b")  # byte-identical content

    result_a = archive_agent_revision(agent_a, store_root=store)
    result_b = archive_agent_revision(agent_b, store_root=store)

    assert result_a.agent_revision_id == result_b.agent_revision_id
    assert list_revisions(store) == (result_a.agent_revision_id,)


def test_archive_snapshot_is_atomic_on_interrupted_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "second.py", "SECOND = 1\n")
    store = tmp_path / "store"

    original_write_bytes = Path.write_bytes
    call_count = {"n": 0}

    def flaky_write_bytes(self: Path, data: bytes) -> int:  # type: ignore[override]
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated disk failure")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)

    result = archive_agent_revision(agent_dir, store_root=store)

    assert result.archived is False
    assert result.error is not None
    assert result.agent_revision_id is not None
    # No partially-written final directory is ever visible.
    assert not (store / result.agent_revision_id).exists()
    # Only a (possibly leftover) temp dir may remain -- never the real path.
    remaining = [p.name for p in store.iterdir()] if store.is_dir() else []
    assert all(name.startswith(".tmp-") for name in remaining)


# ---------------------------------------------------------------------------
# Archive success must prove durable store integrity -- Ultra review BLOCKER 2
# ---------------------------------------------------------------------------


def _store_is_case_insensitive(probe_dir: Path) -> bool:
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "probe.txt").write_bytes(b"x")
    return (probe_dir / "PROBE.TXT").is_file()


def test_archive_refuses_case_insensitive_collision_never_reports_archived_true(
    tmp_path: Path,
) -> None:
    """A source read can legitimately produce two distinct entries whose
    relative paths differ only by case (e.g. a tree copied from a
    case-sensitive filesystem, or a symlink dereferenced under a name that
    differs in case from a real file elsewhere in the tree). Writing both
    to a case-insensitive store filesystem physically collapses them onto
    one file -- silently, with no ``OSError`` from the write itself -- so
    ``_write_snapshot`` must catch this by verifying the written snapshot
    reconstructs the intended fingerprint *before* promoting it, never by
    trusting that the write loop merely ran to completion without
    raising."""

    if not _store_is_case_insensitive(tmp_path / "case-probe"):
        pytest.skip("Store filesystem is case-sensitive; this collision cannot occur here.")

    store = tmp_path / "store"
    walk = AgentFileWalkResult(
        entries=(
            AgentFileEntry("A.txt", b"upper-case-content"),
            AgentFileEntry("a.txt", b"lower-case-content-differs"),
        ),
        omitted=(),
    )

    result = archive_agent_revision_from_walk(walk, store_root=store)

    assert result.archived is False
    assert result.error is not None
    assert result.agent_revision_id is not None
    # The canonical path is never promoted to -- a reader must never see a
    # revision directory whose stored bytes don't match its own name.
    assert not (store / result.agent_revision_id).exists()
    remaining = [p.name for p in store.iterdir()] if store.is_dir() else []
    assert all(name.startswith(".tmp-") for name in remaining)


def test_archive_dropped_or_overwritten_file_never_reports_archived_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Platform-independent counterpart to the case-collision test above:
    even when nothing raises during the write loop, a file whose stored
    bytes silently end up different from what ``walk`` recorded (dropped,
    overwritten, or corrupted in place) must be caught by the pre-promote
    verification, never allowed to reach ``archived=True``."""

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "second.py", "SECOND = 1\n")
    store = tmp_path / "store"

    original_write_bytes = Path.write_bytes

    def corrupting_write_bytes(self: Path, data: bytes) -> int:  # type: ignore[override]
        if self.name == "second.py":
            data = b"silently-corrupted-content-not-what-the-walk-recorded"
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", corrupting_write_bytes)

    result = archive_agent_revision(agent_dir, store_root=store)

    assert result.archived is False
    assert result.error is not None
    assert result.agent_revision_id is not None
    assert not (store / result.agent_revision_id).exists()
    remaining = [p.name for p in store.iterdir()] if store.is_dir() else []
    assert all(name.startswith(".tmp-") for name in remaining)


def test_archive_store_write_failure_is_non_fatal_and_non_identity_bearing(
    tmp_path: Path,
) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    working_store = tmp_path / "working-store"
    good = archive_agent_revision(agent_dir, store_root=working_store)
    assert good.archived is True

    # Point store_root at a path that cannot be a directory (a file sitting
    # where the store root would need to be created) to force a write
    # failure without relying on platform-specific permission semantics.
    blocked_root = tmp_path / "blocked-root"
    blocked_root.write_text("not a directory", encoding="utf-8")
    broken_store = blocked_root / "agent_revisions"

    broken = archive_agent_revision(agent_dir, store_root=broken_store)

    assert broken.archived is False
    assert broken.error is not None
    # Identity is unaffected by the store-write failure.
    assert broken.agent_revision_id == good.agent_revision_id
    assert broken.complete == good.complete


def test_archive_missing_agent_dir_is_reported_without_crashing(tmp_path: Path) -> None:
    result = archive_agent_revision(tmp_path / "nowhere", store_root=tmp_path / "store")
    assert result.agent_revision_id is None
    assert result.archived is False
    assert result.error == "agent_directory_missing"


def test_verify_revision_detects_tampering(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    stored_file = store / result.agent_revision_id / "files" / "agent.py"
    stored_file.write_text("def create_agent():\n    return 'tampered'\n", encoding="utf-8")

    assert verify_revision(store, result.agent_revision_id) is False


def test_verify_revision_missing_revision_is_false(tmp_path: Path) -> None:
    assert verify_revision(tmp_path / "store", "agent-revision_" + "0" * 64) is False


def test_verify_revision_accounts_for_recorded_omissions(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    outside = tmp_path / "outside.py"
    _write(outside, "OUT = 1\n")
    _symlink(agent_dir / "helper.py", outside)
    store = tmp_path / "store"

    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None
    assert result.complete is False
    assert verify_revision(store, result.agent_revision_id) is True


def test_verify_revision_detects_manifest_complete_inconsistent_with_omitted(
    tmp_path: Path,
) -> None:
    """MINOR (Ultra review): ``complete`` must be derived from/checked
    against ``omitted``, not trusted from the manifest alone. Previously
    ``verify_revision`` never read the manifest's ``complete`` field at
    all, so a hand-edited manifest claiming a ``complete`` value
    inconsistent with its own ``omitted`` list was never caught -- this
    locks in that it now is."""

    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None
    assert result.complete is True
    assert verify_revision(store, result.agent_revision_id) is True

    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["omitted"] == []
    manifest["complete"] = False  # disagrees with the (empty) omitted list
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_revision(store, result.agent_revision_id) is False


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def test_restore_round_trip_matches_original_fingerprint(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "model.blob", "binary-content")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    restore_target = tmp_path / "restored"
    restore_revision(store, result.agent_revision_id, restore_target)

    restored_fingerprint = agent_revision_fingerprint(restore_target)
    original_fingerprint = agent_revision_fingerprint(agent_dir)
    assert restored_fingerprint == original_fingerprint


def test_restore_refuses_nonempty_target_without_force(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    target = tmp_path / "occupied"
    _write(target / "preexisting.txt", "do not clobber")

    with pytest.raises(RevisionRestoreError):
        restore_revision(store, result.agent_revision_id, target)

    assert (target / "preexisting.txt").read_text(encoding="utf-8") == "do not clobber"


def test_restore_force_allows_nonempty_target(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    target = tmp_path / "occupied"
    _write(target / "preexisting.txt", "still here")

    restore_revision(store, result.agent_revision_id, target, force=True)

    assert (target / "agent.py").is_file()


def test_restore_unknown_revision_raises(tmp_path: Path) -> None:
    with pytest.raises(RevisionNotFoundError):
        restore_revision(tmp_path / "store", "agent-revision_" + "0" * 64, tmp_path / "target")


def test_restore_rejects_manifest_path_escaping_target(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = ["../../escaped.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restore-target"
    with pytest.raises(RevisionRestoreError):
        restore_revision(store, result.agent_revision_id, target)
    assert not (tmp_path / "escaped.py").exists()


def test_restore_rejects_manifest_path_escaping_store(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = ["../sibling-revision-file.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restore-target"
    with pytest.raises(RevisionRestoreError):
        restore_revision(store, result.agent_revision_id, target)


def test_restore_rejects_windows_drive_and_unc_manifest_paths(tmp_path: Path) -> None:
    agent_dir = _make_agent(tmp_path / "agent")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    manifest_path = store / result.agent_revision_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [r"C:\Windows\System32\evil.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restore-target"
    with pytest.raises(RevisionRestoreError):
        restore_revision(store, result.agent_revision_id, target)


def test_restore_rejects_escape_through_preexisting_destination_link(tmp_path: Path) -> None:
    """A `--force` restore into a non-empty target whose caller already
    populated it with a symlink/junction at a path the manifest also wants
    to write must never follow that link out of the target directory --
    "no junction/reparse-point escape through the destination" (v0.8 audit
    requirement), distinct from every other restore test here, which
    attacks via a corrupted *manifest* rather than a pre-existing
    *destination* entry. Uses the same real-Windows-junction/POSIX-symlink
    technique as the walker's own directory-symlink tests.
    """

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "sub" / "inner.py", "INNER = 1\n")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    target = tmp_path / "restore-target"
    outside = tmp_path / "outside-escape"
    outside.mkdir()
    target.mkdir()
    # "sub" already exists in the target as a link out of the target tree,
    # before restore ever runs -- the manifest itself is untouched/honest;
    # only the destination is attacker-controlled.
    _make_directory_link(target / "sub", outside)

    with pytest.raises(RevisionRestoreError):
        restore_revision(store, result.agent_revision_id, target, force=True)

    assert not (outside / "inner.py").exists()


def test_restore_partial_write_failure_leaves_no_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the mid-restore I/O failure case (v0.8 audit): an
    ordinary ``OSError`` partway through ``restore_revision``'s write loop --
    disk full, a locked file, a transient permission error -- must never
    leave `target_dir` holding a subset of the revision's files that looks
    like a smaller-but-valid restore. Every file this call itself wrote
    before the failure is rolled back, and the caller sees a typed
    ``RevisionRestoreError`` naming exactly how many files were written and
    removed again, never an uncaught ``OSError`` or a silent partial tree."""

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "aaa.py", "AAA = 1\n")
    _write(agent_dir / "bbb.py", "BBB = 1\n")
    _write(agent_dir / "ccc.py", "CCC = 1\n")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None
    assert result.complete is True

    original_write_bytes = Path.write_bytes
    call_count = {"n": 0}

    def flaky_write_bytes(self: Path, data: bytes) -> int:  # type: ignore[override]
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OSError("simulated disk failure mid-restore")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)

    target = tmp_path / "restore-target"
    with pytest.raises(RevisionRestoreError, match="failed partway"):
        restore_revision(store, result.agent_revision_id, target)

    # The files written before the simulated failure must not survive: a
    # mid-restore I/O failure must never leave a partially-successful target
    # that looks like a smaller, valid revision.
    restored_files = [p for p in target.rglob("*") if p.is_file()] if target.exists() else []
    assert restored_files == []

    # Recovery: once the transient failure is gone, restoring into the same
    # (still-empty) target from scratch succeeds completely -- the earlier
    # failed attempt left nothing behind to conflict with a retry.
    monkeypatch.undo()
    restore_revision(store, result.agent_revision_id, target)
    assert sorted(p.name for p in target.iterdir()) == [
        "aaa.py",
        "agent.py",
        "agent.yaml",
        "bbb.py",
        "ccc.py",
    ]


def test_restore_partial_write_failure_preserves_preexisting_files_under_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same mid-restore rollback as above, but into a non-empty
    ``--force`` target: a file that existed before this restore call started
    must never be touched by the failure-path rollback -- only the files
    *this call* wrote get removed again, matching ``restore_revision``'s own
    documented contract ("never anything that was already present in
    `target_dir`, e.g. from an earlier `--force` restore")."""

    agent_dir = _make_agent(tmp_path / "agent")
    _write(agent_dir / "aaa.py", "AAA = 1\n")
    store = tmp_path / "store"
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    target = tmp_path / "restore-target"
    _write(target / "preexisting.txt", "leave me alone")

    original_write_bytes = Path.write_bytes
    call_count = {"n": 0}

    def flaky_write_bytes(self: Path, data: bytes) -> int:  # type: ignore[override]
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated disk failure mid-restore")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)

    with pytest.raises(RevisionRestoreError, match="failed partway"):
        restore_revision(store, result.agent_revision_id, target, force=True)

    remaining = sorted(p.name for p in target.iterdir())
    assert remaining == ["preexisting.txt"]
    assert (target / "preexisting.txt").read_text(encoding="utf-8") == "leave me alone"


# ---------------------------------------------------------------------------
# list_revisions
# ---------------------------------------------------------------------------


def test_list_revisions_ignores_temp_directories(tmp_path: Path) -> None:
    store = tmp_path / "store"
    agent_dir = _make_agent(tmp_path / "agent")
    result = archive_agent_revision(agent_dir, store_root=store)
    assert result.agent_revision_id is not None

    (store / ".tmp-leftover").mkdir(parents=True)

    assert list_revisions(store) == (result.agent_revision_id,)


def test_list_revisions_empty_store(tmp_path: Path) -> None:
    assert list_revisions(tmp_path / "does-not-exist") == ()


# ---------------------------------------------------------------------------
# Headless import
# ---------------------------------------------------------------------------


def test_headless_import_never_pulls_in_qt_or_pygame() -> None:
    before = {name for name in sys.modules if "PySide6" in name or name == "pygame"}
    for name in list(sys.modules):
        if "battle_engine.agent_revisions" in name:
            del sys.modules[name]
    import battle_engine.agent_revisions  # noqa: F401

    after = {name for name in sys.modules if "PySide6" in name or name == "pygame"}
    assert after == before
