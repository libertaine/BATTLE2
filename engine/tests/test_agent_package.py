"""Portable agent package format (docs/specs/agent_package.md).

Exercises the transport wrapper around one already-archived
``agent_revisions`` revision: deterministic export, no-execution
inspection, and transactional import -- including an aggressive
adversarial pass over hand-crafted malicious archives (docs/specs/
agent_package.md Sec 10 / the parent task's Sec 26).
"""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest
from battle_engine.agent_package import (
    PACKAGE_SCHEMA_VERSION,
    AgentPackageError,
    ExportResult,
    ImportResult,
    PackageCompatibilityError,
    PackageImportConflictError,
    PackageIntegrityError,
    PackageInvalidError,
    PackageSchemaUnsupportedError,
    PackageUnsafePathError,
    PackageUnsupportedKindError,
    export_agent,
    import_package,
    inspect_package,
)
from battle_engine.agent_revisions import (
    agent_revision_fingerprint,
    agent_revision_id,
    agent_revisions_root,
    archive_agent_revision,
    list_revisions,
    verify_revision,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: bytes) -> None:
    # write_bytes, not write_text -- avoids Windows newline translation so
    # exact-byte-content assertions below stay platform-independent.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_python_agent(root: Path, name: str = "sample", *, version: str = "1.0") -> Path:
    agent_dir = root / "agents" / name
    _write(
        agent_dir / "agent.yaml",
        f'{{"kind": "python", "api_version": 1, "version": "{version}", '
        f'"display": "Sample Agent", "entrypoint": "agent.py:create_agent"}}'.encode(),
    )
    _write(agent_dir / "agent.py", b"def create_agent():\n    return None\n")
    return agent_dir


def _make_blob_agent(root: Path, name: str = "sample_blob") -> Path:
    agent_dir = root / "agents" / name
    _write(agent_dir / "agent.yaml", b'{"display": "Sample Blob Agent"}')
    _write(agent_dir / "model.blob", b"\x00\x01\x02\xff\xfe compiled bytecode")
    return agent_dir


def _make_builtin_agent(root: Path, name: str = "runner_like") -> Path:
    agent_dir = root / "agents" / name
    _write(agent_dir / "agent.yaml", b'{"display": "Manifest-only starter"}')
    return agent_dir


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "install_a"
    root.mkdir()
    return root


@pytest.fixture
def other_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "install_b"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# Export: kind support
# ---------------------------------------------------------------------------


def test_export_python_agent_succeeds(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    result = export_agent("hunter", data_root=data_root, output=output_dir)

    assert isinstance(result, ExportResult)
    assert result.agent_id == "hunter"
    assert result.agent_revision_id.startswith("agent-revision_")
    assert result.complete is True
    assert result.omitted_count == 0
    assert result.file_count == 2
    assert result.package_path.is_file()
    assert result.package_path.suffix == ".bytefray-agent"
    assert result.package_path.name.startswith("hunter-")


def test_export_blob_agent_succeeds(data_root: Path, tmp_path: Path) -> None:
    _make_blob_agent(data_root, "blobby")
    result = export_agent("blobby", data_root=data_root, output=tmp_path)
    assert result.file_count == 2
    inspection = inspect_package(result.package_path)
    assert inspection.kind == "blob"
    assert inspection.agent_api_version is None  # not applicable for blob kind
    assert inspection.compatible is True


def test_export_rejects_builtin_kind_and_writes_nothing(data_root: Path, tmp_path: Path) -> None:
    _make_builtin_agent(data_root, "runner_like")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    with pytest.raises(PackageUnsupportedKindError) as excinfo:
        export_agent("runner_like", data_root=data_root, output=output_dir)
    assert excinfo.value.code == "package_unsupported_kind"
    assert list(output_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# Export: revision selection (current vs. --revision)
# ---------------------------------------------------------------------------


def test_export_revision_flag_packages_historical_not_current_source(
    data_root: Path, tmp_path: Path
) -> None:
    agent_dir = _make_python_agent(data_root, "drifting")
    store_root = agent_revisions_root(data_root)
    old_result = archive_agent_revision(agent_dir, store_root=store_root, source_agent_id="drifting")
    assert old_result.agent_revision_id is not None

    # Mutate live source after archiving the historical revision.
    _write(agent_dir / "agent.py", b"def create_agent():\n    return 'changed'\n")

    result = export_agent(
        "drifting", data_root=data_root, output=tmp_path, revision_id=old_result.agent_revision_id
    )
    assert result.agent_revision_id == old_result.agent_revision_id

    with zipfile.ZipFile(result.package_path) as zf:
        payload = zf.read(f"revision/{old_result.agent_revision_id}/files/agent.py")
    assert b"changed" not in payload
    assert b"return None" in payload


def test_export_revision_flag_rejects_unknown_revision(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "sample")
    with pytest.raises(PackageIntegrityError):
        export_agent(
            "sample",
            data_root=data_root,
            output=tmp_path,
            revision_id="agent-revision_" + "0" * 64,
        )


# ---------------------------------------------------------------------------
# Determinism / provenance honesty
# ---------------------------------------------------------------------------


def test_repeated_export_stable_revision_manifest_varying_exported_at(
    data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")

    r1 = export_agent("hunter", data_root=data_root, output=tmp_path / "r1.bytefray-agent")
    r2 = export_agent("hunter", data_root=data_root, output=tmp_path / "r2.bytefray-agent")

    assert r1.agent_revision_id == r2.agent_revision_id
    # Outer archive bytes legitimately differ (package.json's exported_at
    # is a fresh timestamp each call) -- never treated as a content
    # identity anywhere in this feature (Sec 4).
    assert r1.package_sha256 != r2.package_sha256

    with zipfile.ZipFile(r1.package_path) as z1, zipfile.ZipFile(r2.package_path) as z2:
        manifest_name = f"revision/{r1.agent_revision_id}/manifest.json"
        assert z1.read(manifest_name) == z2.read(manifest_name)
        for relative in ("files/agent.py", "files/agent.yaml"):
            assert z1.read(f"revision/{r1.agent_revision_id}/{relative}") == z2.read(
                f"revision/{r1.agent_revision_id}/{relative}"
            )
        pkg1 = json.loads(z1.read("package.json"))
        pkg2 = json.loads(z2.read("package.json"))
    assert pkg1["exported_at"] != pkg2["exported_at"]
    pkg1.pop("exported_at")
    pkg2.pop("exported_at")
    assert pkg1 == pkg2


def test_package_json_never_contains_exporter_absolute_paths(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    with zipfile.ZipFile(result.package_path) as zf:
        raw = zf.read("package.json").decode("utf-8")
    assert str(data_root) not in raw
    assert str(tmp_path) not in raw


# ---------------------------------------------------------------------------
# Inspection (no execution, read-only)
# ---------------------------------------------------------------------------


def test_inspect_valid_package_reports_full_provenance(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter", version="2.5")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    inspection = inspect_package(result.package_path)
    assert inspection.valid is True
    assert inspection.error is None
    assert inspection.schema_version == PACKAGE_SCHEMA_VERSION
    assert inspection.agent_id == "hunter"
    assert inspection.kind == "python"
    assert inspection.agent_version == "2.5"
    assert inspection.agent_api_version == 1
    assert inspection.agent_revision_id == result.agent_revision_id
    assert inspection.revision_complete is True
    assert inspection.file_count == 2
    assert inspection.integrity_verified is True
    assert inspection.compatible is True
    assert inspection.compatibility_notes == ()


def test_inspect_never_writes_outside_temp_and_leaves_no_residue(
    data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    before = {p for p in tmp_path.rglob("*")}

    inspect_package(result.package_path)

    after = {p for p in tmp_path.rglob("*")}
    assert after == before  # no residue left behind by inspection


def test_inspect_rejects_not_a_zip(tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_package.bytefray-agent"
    bogus.write_bytes(b"this is not a zip file")
    inspection = inspect_package(bogus)
    assert inspection.valid is False
    assert "ZIP" in (inspection.error or "")


def test_inspect_rejects_missing_package_json(tmp_path: Path) -> None:
    archive = tmp_path / "no_manifest.bytefray-agent"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hi")
    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "package.json" in (inspection.error or "")


def test_inspect_rejects_malformed_package_json(tmp_path: Path) -> None:
    archive = tmp_path / "bad_json.bytefray-agent"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("package.json", "{not valid json")
    inspection = inspect_package(archive)
    assert inspection.valid is False


def test_inspect_rejects_wrong_schema_name(tmp_path: Path) -> None:
    archive = tmp_path / "wrong_schema.bytefray-agent"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("package.json", json.dumps({"schema": "not.a.bytefray.package", "schema_version": 1}))
    inspection = inspect_package(archive)
    assert inspection.valid is False


def test_inspect_rejects_unsupported_schema_version(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "future_schema.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(archive, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "package.json":
                doc = json.loads(data)
                doc["schema_version"] = PACKAGE_SCHEMA_VERSION + 1
                data = json.dumps(doc).encode("utf-8")
            zout.writestr(info.filename, data)

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "schema_version" in (inspection.error or "")

    with pytest.raises(PackageSchemaUnsupportedError):
        import_package(archive, data_root=data_root, as_agent_id="whatever")


def test_inspect_reports_incompatible_declared_builtin_kind(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "declared_builtin.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(archive, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "package.json":
                doc = json.loads(data)
                doc["kind"] = "builtin"
                data = json.dumps(doc).encode("utf-8")
            zout.writestr(info.filename, data)

    inspection = inspect_package(archive)
    assert inspection.valid is True
    assert inspection.compatible is False
    assert any("kind" in note for note in inspection.compatibility_notes)

    with pytest.raises(PackageCompatibilityError):
        import_package(archive, data_root=data_root, as_agent_id="whatever")


def test_inspect_reports_incompatible_agent_api_version(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "future_api.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(archive, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "package.json":
                doc = json.loads(data)
                doc["agent_api_version"] = 999
                data = json.dumps(doc).encode("utf-8")
            zout.writestr(info.filename, data)

    inspection = inspect_package(archive)
    assert inspection.compatible is False

    with pytest.raises(PackageCompatibilityError):
        import_package(archive, data_root=data_root, as_agent_id="whatever")


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


def test_tamper_detected_by_inspect_and_import(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    tampered = tmp_path / "tampered.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(tampered, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith("agent.py") and "files/" in info.filename:
                data = data[:-1] + bytes([data[-1] ^ 0xFF])
            zout.writestr(info.filename, data)

    inspection = inspect_package(tampered)
    assert inspection.valid is True
    assert inspection.integrity_verified is False
    assert inspection.compatible is False

    with pytest.raises(PackageIntegrityError):
        import_package(tampered, data_root=other_data_root)
    assert not (other_data_root / "agents" / "hunter").exists()


def test_missing_declared_payload_file_fails_integrity(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    truncated = tmp_path / "truncated.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(truncated, "w") as zout:
        for info in zin.infolist():
            if info.filename.endswith("agent.py") and "files/" in info.filename:
                continue  # drop a declared payload file entirely
            zout.writestr(info.filename, zin.read(info.filename))

    with pytest.raises(PackageIntegrityError):
        import_package(truncated, data_root=other_data_root)
    assert not (other_data_root / "agents" / "hunter").exists()


def test_undeclared_extra_payload_file_fails_integrity(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    extra = tmp_path / "extra_payload.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(extra, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(f"revision/{result.agent_revision_id}/files/sneaky_extra.py", b"print('surprise')")

    with pytest.raises(PackageIntegrityError):
        import_package(extra, data_root=other_data_root)
    assert not (other_data_root / "agents" / "hunter").exists()


def test_duplicate_manifest_entry_rejected(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    dup = tmp_path / "dup_manifest.bytefray-agent"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(dup, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        manifest_name = f"revision/{result.agent_revision_id}/manifest.json"
        zout.writestr(manifest_name, zin.read(manifest_name))  # duplicate entry, same name

    with pytest.raises(PackageInvalidError):
        import_package(dup, data_root=other_data_root)
    assert not (other_data_root / "agents" / "hunter").exists()


# ---------------------------------------------------------------------------
# Import: happy path, provenance integration
# ---------------------------------------------------------------------------


def test_import_round_trip_preserves_provenance(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    agent_dir = _make_python_agent(data_root, "hunter")
    original_bytes = {
        p.name: p.read_bytes() for p in agent_dir.iterdir() if p.is_file()
    }
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    import_result = import_package(export_result.package_path, data_root=other_data_root)

    assert isinstance(import_result, ImportResult)
    assert import_result.agent_id == "hunter"
    assert import_result.agent_revision_id == export_result.agent_revision_id
    assert import_result.already_present is False

    target_dir = other_data_root / "agents" / "hunter"
    assert target_dir.is_dir()
    for name, content in original_bytes.items():
        assert (target_dir / name).read_bytes() == content

    # Provenance survives transfer: the local store now has this revision,
    # and it verifies, and it matches the freshly placed live source.
    store_root = agent_revisions_root(other_data_root)
    assert export_result.agent_revision_id in list_revisions(store_root)
    assert verify_revision(store_root, export_result.agent_revision_id)
    live_fingerprint = agent_revision_fingerprint(target_dir)
    assert agent_revision_id(live_fingerprint) == export_result.agent_revision_id


def test_import_with_as_uses_explicit_agent_id(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    import_result = import_package(export_result.package_path, data_root=other_data_root, as_agent_id="hunter_renamed")

    assert import_result.agent_id == "hunter_renamed"
    assert (other_data_root / "agents" / "hunter_renamed").is_dir()
    assert not (other_data_root / "agents" / "hunter").exists()


@pytest.mark.parametrize("bad_id", ["", "..", "../escape", "a/b", "a\\b", "a" * 100, ".hidden"])
def test_import_rejects_invalid_target_agent_id(data_root: Path, other_data_root: Path, tmp_path: Path, bad_id: str) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    with pytest.raises(AgentPackageError):
        import_package(export_result.package_path, data_root=other_data_root, as_agent_id=bad_id)
    # Rejected before any directory is created under the destination root.
    assert not (other_data_root / "agents").exists()


# ---------------------------------------------------------------------------
# Import: collision policy
# ---------------------------------------------------------------------------


def test_import_collision_different_content_fails_without_mutation(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    existing_dir = _make_python_agent(other_data_root, "hunter", version="9.9")
    existing_bytes = (existing_dir / "agent.py").read_bytes()

    with pytest.raises(PackageImportConflictError):
        import_package(export_result.package_path, data_root=other_data_root)

    assert (existing_dir / "agent.py").read_bytes() == existing_bytes  # untouched


def test_import_collision_identical_content_is_noop(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    first = import_package(export_result.package_path, data_root=other_data_root)
    assert first.already_present is False

    second = import_package(export_result.package_path, data_root=other_data_root)
    assert second.already_present is True
    assert second.agent_revision_id == export_result.agent_revision_id


# ---------------------------------------------------------------------------
# Import: fail-closed provenance mismatch vs. non-fatal store I/O failure
# ---------------------------------------------------------------------------


def test_import_rolls_back_on_post_placement_identity_mismatch(
    data_root: Path, other_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    import battle_engine.agent_package as agent_package_module
    from battle_engine.agent_revisions import RevisionArchivalResult

    real_archive = agent_package_module.archive_agent_revision

    def _lying_archive(target_dir, *, store_root, source_agent_id):
        real = real_archive(target_dir, store_root=store_root, source_agent_id=source_agent_id)
        return RevisionArchivalResult(
            agent_revision_id="agent-revision_" + "f" * 64,
            complete=real.complete,
            omitted=real.omitted,
            archived=real.archived,
            error=real.error,
        )

    monkeypatch.setattr(agent_package_module, "archive_agent_revision", _lying_archive)

    with pytest.raises(PackageIntegrityError):
        import_package(export_result.package_path, data_root=other_data_root)

    assert not (other_data_root / "agents" / "hunter").exists()


def test_import_survives_non_fatal_local_store_write_failure(
    data_root: Path, other_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)

    import battle_engine.agent_package as agent_package_module
    from battle_engine.agent_revisions import RevisionArchivalResult

    real_archive = agent_package_module.archive_agent_revision

    def _failing_store_write(target_dir, *, store_root, source_agent_id):
        real = real_archive(target_dir, store_root=store_root, source_agent_id=source_agent_id)
        return RevisionArchivalResult(
            agent_revision_id=real.agent_revision_id,
            complete=real.complete,
            omitted=real.omitted,
            archived=False,
            error="snapshot_write_failed: simulated",
        )

    monkeypatch.setattr(agent_package_module, "archive_agent_revision", _failing_store_write)

    result = import_package(export_result.package_path, data_root=other_data_root)
    assert result.local_archive_error is not None
    assert (other_data_root / "agents" / "hunter").is_dir()  # agent itself still placed


# ---------------------------------------------------------------------------
# Cross-installation / path-independence
# ---------------------------------------------------------------------------


def test_export_import_across_disjoint_data_roots_is_path_independent(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    export_result = export_agent("hunter", data_root=data_root, output=tmp_path)
    import_result = import_package(export_result.package_path, data_root=other_data_root)
    assert import_result.agent_revision_id == export_result.agent_revision_id

    # Re-export from the *importing* installation and confirm identical
    # logical identity -- proves the revision genuinely round-tripped
    # rather than merely being copied opaquely.
    reexport = export_agent("hunter", data_root=other_data_root, output=tmp_path / "reexport")
    assert reexport.agent_revision_id == export_result.agent_revision_id


# ---------------------------------------------------------------------------
# Adversarial archive-safety pass (parent task Sec 26)
# ---------------------------------------------------------------------------


def _corpus(data_root: Path, tmp_path: Path) -> tuple[Path, str]:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    return result.package_path, result.agent_revision_id


MALICIOUS_TOP_LEVEL_NAMES = [
    "../evil.py",
    "../../outside/evil.py",
    "C:\\evil.py",
    "C:/evil.py",
    "\\\\server\\share\\evil.py",
    "/absolute/path/evil.py",
    "foo/../../evil.py",
]


@pytest.mark.parametrize("malicious_name", MALICIOUS_TOP_LEVEL_NAMES)
def test_import_rejects_malicious_top_level_paths(
    data_root: Path, other_data_root: Path, tmp_path: Path, malicious_name: str
) -> None:
    package_path, _ = _corpus(data_root, tmp_path)
    evil = tmp_path / f"evil_{abs(hash(malicious_name))}.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(malicious_name, b"EVIL PAYLOAD")

    with pytest.raises((PackageUnsafePathError, PackageInvalidError)):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")

    # Nothing escaped anywhere near the real destination tree.
    assert not (other_data_root / "agents").exists() or list((other_data_root / "agents").iterdir()) == []
    assert not (tmp_path.parent / "evil.py").exists()
    assert not (data_root.parent / "evil.py").exists()


def test_import_rejects_case_colliding_duplicate_paths(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / "case_collision.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(f"revision/{revision_id}/files/AGENT.PY", b"case collision payload")

    with pytest.raises(PackageInvalidError):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")


def test_import_rejects_symlink_mode_entry(data_root: Path, other_data_root: Path, tmp_path: Path) -> None:
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / "symlink_entry.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        link_info = zipfile.ZipInfo(f"revision/{revision_id}/files/sneaky_link.py")
        link_info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zout.writestr(link_info, "/etc/passwd")

    with pytest.raises((PackageUnsafePathError, PackageIntegrityError)):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")


def test_import_tolerates_harmless_unrelated_extra_member(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    """An extra member entirely outside package.json/revision/ is inert:
    extracted into the disposable temp dir and never consulted -- proven
    here as a deliberate, safe leniency rather than an untested gap."""

    package_path, _ = _corpus(data_root, tmp_path)
    harmless = tmp_path / "harmless_extra.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(harmless, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr("README.txt", b"this is not part of the revision at all")

    result = import_package(harmless, data_root=other_data_root)
    assert (other_data_root / "agents" / "hunter").is_dir()
    assert not (other_data_root / "agents" / "hunter" / "README.txt").exists()
    assert result.already_present is False


def test_import_rejects_excessive_member_count(
    data_root: Path, other_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    monkeypatch.setattr(agent_package_module, "_MAX_MEMBER_COUNT", 5)
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / "too_many_members.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        for i in range(10):
            zout.writestr(f"revision/{revision_id}/files/junk_{i}.txt", b"x")

    with pytest.raises(PackageInvalidError):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")


def test_import_rejects_oversized_single_file(
    data_root: Path, other_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 16)
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / "oversized.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(f"revision/{revision_id}/files/huge.txt", b"x" * 1000)

    with pytest.raises(PackageInvalidError):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")


def test_import_rejects_excessive_total_size(
    data_root: Path, other_data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 10_000)
    monkeypatch.setattr(agent_package_module, "_MAX_TOTAL_SIZE", 100)
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / "total_too_big.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(f"revision/{revision_id}/files/a.txt", b"x" * 60)
        zout.writestr(f"revision/{revision_id}/files/b.txt", b"y" * 60)

    with pytest.raises(PackageInvalidError):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")
