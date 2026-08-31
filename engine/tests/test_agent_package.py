"""Portable agent package format (docs/specs/agent_package.md).

Exercises the transport wrapper around one already-archived
``agent_revisions`` revision: deterministic export, no-execution
inspection, and fail-closed import -- including an aggressive
adversarial pass over hand-crafted malicious archives (docs/specs/
agent_package.md Sec 10 / the parent task's Sec 26).
"""

from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from battle_engine.agent_api import SUPPORTED_AGENT_API_VERSIONS
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


def _make_python_agent(
    root: Path,
    name: str = "sample",
    *,
    version: str = "1.0",
    api_version: int = 2,
    display: str | None = "Sample Agent",
) -> Path:
    agent_dir = root / "agents" / name
    manifest = {
        "kind": "python",
        "api_version": api_version,
        "version": version,
        "entrypoint": "agent.py:create_agent",
    }
    if display is not None:
        manifest["display"] = display
    _write(
        agent_dir / "agent.yaml",
        json.dumps(manifest).encode(),
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


def _rewrite_package_json(source: Path, destination: Path, mutate) -> None:
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(destination, "w") as zout:
        for info in zin.infolist():
            payload = zin.read(info)
            if info.filename == "package.json":
                document = json.loads(payload)
                mutate(document)
                payload = json.dumps(document).encode("utf-8")
            zout.writestr(info.filename, payload)


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


def test_historical_export_without_explicit_display_uses_export_agent_id(
    data_root: Path, tmp_path: Path
) -> None:
    agent_dir = _make_python_agent(data_root, "plain_id", display=None)
    archived = archive_agent_revision(
        agent_dir,
        store_root=agent_revisions_root(data_root),
        source_agent_id="plain_id",
    )
    assert archived.agent_revision_id is not None

    result = export_agent(
        "plain_id",
        data_root=data_root,
        output=tmp_path,
        revision_id=archived.agent_revision_id,
    )

    inspection = inspect_package(result.package_path)
    assert inspection.valid is True
    assert inspection.display_name == "plain_id"  # never temp snapshot dirname "files"


def test_import_accepts_v1_legacy_historical_display_fallback(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    """v1.2 used snapshot dirname ``files`` when display was undeclared."""

    agent_dir = _make_python_agent(data_root, "legacy_plain", display=None)
    archived = archive_agent_revision(
        agent_dir,
        store_root=agent_revisions_root(data_root),
        source_agent_id="legacy_plain",
    )
    assert archived.agent_revision_id is not None
    result = export_agent(
        "legacy_plain",
        data_root=data_root,
        output=tmp_path / "new.bytefray-agent",
        revision_id=archived.agent_revision_id,
    )
    legacy = tmp_path / "legacy.bytefray-agent"
    _rewrite_package_json(
        result.package_path,
        legacy,
        lambda document: document.__setitem__("display_name", "files"),
    )

    inspection = inspect_package(legacy)
    assert inspection.valid is True
    assert inspection.display_name == "files"
    assert inspection.compatible is True
    imported = import_package(legacy, data_root=other_data_root)
    assert imported.agent_id == "legacy_plain"


def test_export_revision_flag_rejects_unknown_revision(data_root: Path, tmp_path: Path) -> None:
    _make_python_agent(data_root, "sample")
    with pytest.raises(PackageIntegrityError):
        export_agent(
            "sample",
            data_root=data_root,
            output=tmp_path,
            revision_id="agent-revision_" + "0" * 64,
        )


def test_export_preflights_large_live_file_before_reading_it(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    agent_dir = _make_python_agent(data_root, "huge_source")
    oversized = agent_dir / "agent.py"
    oversized.write_bytes(b"x" * 2048)
    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 1024)
    original_read_bytes = Path.read_bytes

    def _guarded_read_bytes(path: Path) -> bytes:
        if path == oversized:
            pytest.fail("oversized live source must be rejected from stat metadata")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)
    output = tmp_path / "must-not-exist.bytefray-agent"
    with pytest.raises(PackageInvalidError):
        export_agent("huge_source", data_root=data_root, output=output)
    assert not output.exists()


def test_export_caps_agent_manifest_before_safe_parse(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    agent_dir = _make_python_agent(data_root, "huge_manifest")
    manifest_path = agent_dir / "agent.yaml"
    manifest_path.write_bytes(b"x" * 2048)
    monkeypatch.setattr(agent_package_module, "_MAX_AGENT_MANIFEST_SIZE", 1024)
    original_read_text = Path.read_text

    def _guarded_read_text(path: Path, *args, **kwargs) -> str:
        if path == manifest_path:
            pytest.fail("oversized agent.yaml must be stat-bounded before safe parsing")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)
    output = tmp_path / "must-not-exist.bytefray-agent"
    with pytest.raises(PackageInvalidError, match="Agent manifest exceeds"):
        export_agent("huge_manifest", data_root=data_root, output=output)
    assert not output.exists()


def test_export_preflights_large_internal_file_symlink_before_reading_target(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    agent_dir = _make_python_agent(data_root, "linked_large")
    hidden_target = agent_dir / ".git" / "large.bin"
    _write(hidden_target, b"x" * 2048)
    link = agent_dir / "linked.bin"
    try:
        link.symlink_to(Path(".git") / "large.bin")
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable in this environment: {exc}")
    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 1024)
    original_read_bytes = Path.read_bytes

    def _guarded_read_bytes(path: Path) -> bytes:
        if path == hidden_target:
            pytest.fail("internal file-link target must be stat-bounded before dereference")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)
    with pytest.raises(PackageInvalidError):
        export_agent("linked_large", data_root=data_root, output=tmp_path)


def test_export_rejects_nonportable_live_payload_name_before_read(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("NTFS treats colon names as alternate data streams, not enumerable files")
    agent_dir = _make_python_agent(data_root, "portable_source")
    unsafe = agent_dir / "bad:ads"
    try:
        unsafe.write_bytes(b"must never be read")
    except OSError as exc:
        pytest.skip(f"host filesystem cannot create the adversarial filename: {exc}")
    original_read_bytes = Path.read_bytes

    def _guarded_read_bytes(path: Path) -> bytes:
        if path == unsafe:
            pytest.fail("nonportable source path must be rejected before read")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)
    with pytest.raises(PackageUnsafePathError):
        export_agent("portable_source", data_root=data_root, output=tmp_path)


def test_export_preflights_large_historical_file_before_verification_read(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    agent_dir = _make_python_agent(data_root, "historical_large")
    (agent_dir / "agent.py").write_bytes(b"x" * 2048)
    archived = archive_agent_revision(
        agent_dir,
        store_root=agent_revisions_root(data_root),
        source_agent_id="historical_large",
    )
    assert archived.agent_revision_id is not None
    stored_source = (
        agent_revisions_root(data_root)
        / archived.agent_revision_id
        / "files"
        / "agent.py"
    )
    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 1024)
    original_read_bytes = Path.read_bytes

    def _guarded_read_bytes(path: Path) -> bytes:
        if path == stored_source:
            pytest.fail("oversized historical source must be rejected from stat metadata")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)
    output = tmp_path / "must-not-exist.bytefray-agent"
    with pytest.raises(PackageInvalidError):
        export_agent(
            "historical_large",
            data_root=data_root,
            output=output,
            revision_id=archived.agent_revision_id,
        )
    assert not output.exists()


def test_historical_export_rejects_nonportable_payload_path_before_verification(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    agent_dir = _make_python_agent(data_root, "historical_path")
    archived = archive_agent_revision(
        agent_dir,
        store_root=agent_revisions_root(data_root),
        source_agent_id="historical_path",
    )
    assert archived.agent_revision_id is not None
    real_read_manifest = agent_package_module.read_revision_manifest

    def _unsafe_manifest(store_root: Path, revision_id: str):
        document = real_read_manifest(store_root, revision_id)
        assert document is not None
        document["files"] = ["bad:ads"]
        return document

    monkeypatch.setattr(agent_package_module, "read_revision_manifest", _unsafe_manifest)
    monkeypatch.setattr(
        agent_package_module,
        "verify_revision",
        lambda *_a, **_k: pytest.fail("nonportable path must fail before verification"),
    )

    with pytest.raises(PackageUnsafePathError):
        export_agent(
            "historical_path",
            data_root=data_root,
            output=tmp_path,
            revision_id=archived.agent_revision_id,
        )


def test_export_streams_package_digest_instead_of_reading_whole_archive(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_python_agent(data_root, "streamed_digest")
    original_read_bytes = Path.read_bytes

    def _guarded_read_bytes(path: Path) -> bytes:
        if path.suffix == ".bytefray-agent":
            pytest.fail("export digest must stream the package instead of Path.read_bytes")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _guarded_read_bytes)
    result = export_agent("streamed_digest", data_root=data_root, output=tmp_path)
    assert result.package_path.is_file()


def test_export_rejects_control_characters_in_constructed_manifest(
    data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "unsafe_display", display="friendly\nspoofed")
    output = tmp_path / "unsafe.bytefray-agent"

    with pytest.raises(PackageInvalidError, match="control/non-printing"):
        export_agent("unsafe_display", data_root=data_root, output=output)
    assert not output.exists()


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
    assert inspection.agent_api_version == 2
    assert inspection.agent_revision_id == result.agent_revision_id
    assert inspection.revision_complete is True
    assert inspection.file_count == 2
    assert inspection.integrity_verified is True
    assert inspection.compatible is True
    assert inspection.compatibility_notes == ()


def test_export_inspect_and_import_never_execute_packaged_python(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "agent-code-executed.txt"
    agent_dir = _make_python_agent(data_root, "side_effect")
    _write(
        agent_dir / "agent.py",
        (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
            "def create_agent():\n    return None\n"
        ).encode(),
    )

    result = export_agent("side_effect", data_root=data_root, output=tmp_path)
    inspection = inspect_package(result.package_path)
    imported = import_package(result.package_path, data_root=other_data_root)

    assert inspection.valid is True
    assert imported.agent_id == "side_effect"
    assert not marker.exists()


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
    assert "zip" in (inspection.error or "").lower()


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


def test_inspect_rejects_invalid_or_control_bearing_declared_agent_id(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "unsafe_id.bytefray-agent"
    _rewrite_package_json(
        result.package_path,
        archive,
        lambda document: document.__setitem__("agent_id", "hunter\nspoofed"),
    )

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "control/non-printing" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(archive, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_rejects_malformed_declared_revision_id_before_payload_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import battle_engine.agent_package as agent_package_module

    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "unsafe_revision_id.bytefray-agent"
    _rewrite_package_json(
        result.package_path,
        archive,
        lambda document: document.__setitem__("agent_revision_id", "../../outside"),
    )
    monkeypatch.setattr(
        agent_package_module,
        "_extract_validated_members",
        lambda *_a, **_k: pytest.fail("malformed revision id must fail before payload reads"),
    )

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "content-addressed revision id" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(archive, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_inspect_rejects_kind_that_disagrees_with_verified_payload(
    data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    archive = tmp_path / "declared_builtin.bytefray-agent"
    _rewrite_package_json(
        result.package_path,
        archive,
        lambda document: document.__setitem__("kind", "builtin"),
    )

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "disagrees" in (inspection.error or "")

    with pytest.raises(PackageInvalidError):
        import_package(archive, data_root=data_root, as_agent_id="whatever")


def test_inspect_reports_incompatible_agent_api_version(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter", api_version=999)
    result = export_agent("hunter", data_root=data_root, output=tmp_path)

    inspection = inspect_package(result.package_path)
    assert inspection.valid is True
    assert inspection.compatible is False
    assert any("Agent API v999" in note for note in inspection.compatibility_notes)

    with pytest.raises(PackageCompatibilityError):
        import_package(result.package_path, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_package_compatibility_shares_loader_authoritative_supported_versions() -> None:
    """B1 regression guard: the package gate must consume the loader's own
    supported-version set rather than a second, independently maintained
    list -- a future Agent API bump that only updates one of them must fail
    this test instead of silently reproducing the historical-version-
    rejection defect."""

    import battle_engine.agent_api as agent_api_module
    import battle_engine.agent_package as agent_package_module

    assert (
        agent_package_module.SUPPORTED_AGENT_API_VERSIONS
        is agent_api_module.SUPPORTED_AGENT_API_VERSIONS
    )


@pytest.mark.parametrize("api_version", sorted(SUPPORTED_AGENT_API_VERSIONS))
def test_export_inspect_import_round_trip_succeeds_for_every_supported_api_version(
    data_root: Path, other_data_root: Path, tmp_path: Path, api_version: int
) -> None:
    """B1: every historical/current supported Python Agent API version must
    export, inspect as compatible, and actually import -- not just the
    newest one."""

    _make_python_agent(data_root, "versioned", api_version=api_version)
    result = export_agent("versioned", data_root=data_root, output=tmp_path)

    inspection = inspect_package(result.package_path)
    assert inspection.valid is True
    assert inspection.agent_api_version == api_version
    assert inspection.compatible is True
    assert inspection.compatibility_notes == ()

    imported = import_package(result.package_path, data_root=other_data_root)
    assert imported.agent_id == "versioned"
    assert (other_data_root / "agents" / "versioned").is_dir()


def test_package_rejects_first_version_beyond_the_authoritative_supported_set(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    """B1: a genuinely unsupported future API version remains rejected, with
    a truthful message -- computed from the authoritative supported set
    rather than a hardcoded example version, so this stays correct across a
    future Agent API bump."""

    unsupported_version = max(SUPPORTED_AGENT_API_VERSIONS) + 1
    _make_python_agent(data_root, "future_agent", api_version=unsupported_version)
    result = export_agent("future_agent", data_root=data_root, output=tmp_path)

    inspection = inspect_package(result.package_path)
    assert inspection.valid is True
    assert inspection.compatible is False
    assert any(
        f"Agent API v{unsupported_version}" in note
        for note in inspection.compatibility_notes
    )
    # Truthful wording: an unsupported package is never described as if a
    # supported one "requires" something unavailable.
    assert any("unsupported" in note for note in inspection.compatibility_notes)

    with pytest.raises(PackageCompatibilityError):
        import_package(result.package_path, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_package_json_cannot_disguise_payload_api_compatibility(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "future_agent", api_version=999)
    result = export_agent("future_agent", data_root=data_root, output=tmp_path)
    disguised = tmp_path / "disguised.bytefray-agent"

    def _disguise(document: dict[str, object]) -> None:
        document["kind"] = "blob"
        document["agent_api_version"] = None
        document["entry_point"] = None

    _rewrite_package_json(result.package_path, disguised, _disguise)

    inspection = inspect_package(disguised)
    assert inspection.valid is False
    assert "disagrees" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(disguised, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_package_json_mirrored_revision_facts_must_match_payload(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    disguised = tmp_path / "wrong_count.bytefray-agent"
    _rewrite_package_json(
        result.package_path,
        disguised,
        lambda document: document.__setitem__("file_count", 999),
    )

    inspection = inspect_package(disguised)
    assert inspection.valid is False
    assert "file_count" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(disguised, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


def test_malformed_revision_metadata_verification_is_normalized(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    _make_python_agent(data_root, "hunter")
    result = export_agent("hunter", data_root=data_root, output=tmp_path)
    malformed = tmp_path / "malformed_revision_metadata.bytefray-agent"
    manifest_name = f"revision/{result.agent_revision_id}/manifest.json"
    with zipfile.ZipFile(result.package_path) as zin, zipfile.ZipFile(malformed, "w") as zout:
        for info in zin.infolist():
            payload = zin.read(info.filename)
            if info.filename == manifest_name:
                document = json.loads(payload)
                document["complete"] = False
                document["omitted"] = [
                    {
                        "relative_path": "ghost",
                        "reason": "external_target",
                        "target": "\ud800",
                    }
                ]
                payload = json.dumps(document).encode()
            zout.writestr(info.filename, payload)

    inspection = inspect_package(malformed)
    assert inspection.valid is False
    assert "could not be verified safely" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(malformed, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


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
    assert not (other_data_root / "agents").exists()


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
        with pytest.warns(UserWarning, match="Duplicate name"):
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


def test_import_reports_when_identity_mismatch_cleanup_fails(
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

    target_dir = other_data_root / "agents" / "hunter"
    real_rmtree = agent_package_module.shutil.rmtree

    def _failing_cleanup(path, *args, **kwargs):
        if Path(path) == target_dir:
            raise OSError("simulated locked file")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(agent_package_module, "archive_agent_revision", _lying_archive)
    monkeypatch.setattr(agent_package_module.shutil, "rmtree", _failing_cleanup)

    with pytest.raises(PackageIntegrityError, match="Cleanup also failed") as excinfo:
        import_package(export_result.package_path, data_root=other_data_root)

    assert "files may remain" in str(excinfo.value)
    assert target_dir.exists()


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


def test_metadata_limit_rejection_happens_before_any_member_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import battle_engine.agent_package as agent_package_module

    package_path, _ = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_PACKAGE_JSON_SIZE", 1)
    reads: list[str] = []

    def _unexpected_open(self, name, *args, **kwargs):
        reads.append(str(name))
        pytest.fail("metadata-invalid archive must not open a member")

    monkeypatch.setattr(zipfile.ZipFile, "open", _unexpected_open)
    inspection = inspect_package(package_path)
    assert inspection.valid is False
    with pytest.raises(PackageInvalidError):
        import_package(package_path, data_root=other_data_root)
    assert reads == []
    assert not (other_data_root / "agents").exists()


def test_raw_central_directory_preflight_counts_records_before_zipfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    archive = tmp_path / "forged_entry_count.bytefray-agent"
    with zipfile.ZipFile(archive, "w") as zout:
        for index in range(4):
            zout.writestr(f"empty-{index}", b"")
    raw = bytearray(archive.read_bytes())
    eocd = raw.rfind(b"PK\x05\x06")
    assert eocd >= 0
    # Lie in both EOCD count fields. A count-only check would accept this
    # and ZipFile would still eagerly allocate all four central records.
    raw[eocd + 8 : eocd + 10] = (1).to_bytes(2, "little")
    raw[eocd + 10 : eocd + 12] = (1).to_bytes(2, "little")
    archive.write_bytes(raw)

    monkeypatch.setattr(agent_package_module, "_MAX_MEMBER_COUNT", 3)
    monkeypatch.setattr(
        agent_package_module.zipfile,
        "ZipFile",
        lambda *_a, **_k: pytest.fail("central metadata must fail before ZipFile allocation"),
    )

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "central-directory records" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(archive, data_root=tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_raw_central_directory_preflight_caps_encoded_member_name_before_zipfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    archive = tmp_path / "huge_name.bytefray-agent"
    with zipfile.ZipFile(archive, "w") as zout:
        zout.writestr("x" * 64, b"")
    monkeypatch.setattr(agent_package_module, "_MAX_MEMBER_NAME_BYTES", 32)
    monkeypatch.setattr(
        agent_package_module.zipfile,
        "ZipFile",
        lambda *_a, **_k: pytest.fail("oversized name must fail before ZipFile allocation"),
    )

    inspection = inspect_package(archive)
    assert inspection.valid is False
    assert "member name exceeds" in (inspection.error or "")


def test_outer_archive_size_is_capped_before_zipfile(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import battle_engine.agent_package as agent_package_module

    package_path, _ = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_ARCHIVE_SIZE", 1)
    monkeypatch.setattr(
        agent_package_module.zipfile,
        "ZipFile",
        lambda *_a, **_k: pytest.fail("oversized archive must fail before ZipFile allocation"),
    )

    inspection = inspect_package(package_path)
    assert inspection.valid is False
    assert "archive exceeds" in (inspection.error or "")


def test_agent_manifest_limit_rejects_before_any_zip_member_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import battle_engine.agent_package as agent_package_module

    package_path, _ = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_AGENT_MANIFEST_SIZE", 1)
    monkeypatch.setattr(
        zipfile.ZipFile,
        "open",
        lambda *_a, **_k: pytest.fail("oversized agent.yaml must fail before member reads"),
    )

    inspection = inspect_package(package_path)
    assert inspection.valid is False
    assert "agent.yaml exceeds" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(package_path, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_package_json_compressed_size_is_bounded_before_manifest_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import battle_engine.agent_package as agent_package_module

    package_path, _ = _corpus(data_root, tmp_path)
    forged = tmp_path / "forged_package_json_compressed_size.bytefray-agent"
    raw = bytearray(package_path.read_bytes())
    central_header = raw.find(b"PK\x01\x02")
    assert central_header >= 0  # exporter writes package.json first
    forged_size = agent_package_module._MAX_PACKAGE_JSON_COMPRESSED_SIZE + 1
    raw[central_header + 20 : central_header + 24] = forged_size.to_bytes(4, "little")
    forged.write_bytes(raw)
    monkeypatch.setattr(
        zipfile.ZipFile,
        "open",
        lambda *_a, **_k: pytest.fail("oversized package.json must not be opened"),
    )

    inspection = inspect_package(forged)
    assert inspection.valid is False
    assert "package.json's compressed data" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(forged, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_compressed_size_limit_rejection_happens_before_member_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import battle_engine.agent_package as agent_package_module

    package_path, _ = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_TOTAL_COMPRESSED_SIZE", 1)
    monkeypatch.setattr(
        zipfile.ZipFile,
        "open",
        lambda *_a, **_k: pytest.fail("compressed-size rejection must not open a member"),
    )

    inspection = inspect_package(package_path)
    assert inspection.valid is False
    assert "compressed size" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(package_path, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_duplicate_package_json_rejected_before_any_member_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path, _ = _corpus(data_root, tmp_path)
    duplicate = tmp_path / "duplicate_package_json.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(duplicate, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        with pytest.warns(UserWarning, match="Duplicate name"):
            zout.writestr("package.json", b"{}")

    monkeypatch.setattr(
        zipfile.ZipFile,
        "open",
        lambda *_a, **_k: pytest.fail("duplicate package.json must be metadata-only failure"),
    )
    inspection = inspect_package(duplicate)
    assert inspection.valid is False
    with pytest.raises(PackageInvalidError):
        import_package(duplicate, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_file_directory_ancestor_collision_rejected_before_member_read(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path, revision_id = _corpus(data_root, tmp_path)
    collision = tmp_path / "ancestor_collision.bytefray-agent"
    prefix = f"revision/{revision_id}/files/collision"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(collision, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(prefix, b"regular file")
        zout.writestr(f"{prefix}/child.py", b"nested file")

    monkeypatch.setattr(
        zipfile.ZipFile,
        "open",
        lambda *_a, **_k: pytest.fail("ancestor collision must be metadata-only failure"),
    )
    inspection = inspect_package(collision)
    assert inspection.valid is False
    assert "ancestor collision" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(collision, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_unsupported_zip_compression_is_normalized_to_package_error(
    data_root: Path, other_data_root: Path, tmp_path: Path
) -> None:
    package_path, _ = _corpus(data_root, tmp_path)
    broken = tmp_path / "unsupported_compression.bytefray-agent"
    raw = bytearray(package_path.read_bytes())
    local_header = raw.find(b"PK\x03\x04")
    central_header = raw.find(b"PK\x01\x02")
    assert local_header >= 0 and central_header >= 0
    raw[local_header + 8 : local_header + 10] = (99).to_bytes(2, "little")
    raw[central_header + 10 : central_header + 12] = (99).to_bytes(2, "little")
    broken.write_bytes(raw)

    inspection = inspect_package(broken)
    assert inspection.valid is False
    assert "Could not read package.json" in (inspection.error or "")
    with pytest.raises(PackageInvalidError):
        import_package(broken, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


def test_inspection_and_import_do_not_eagerly_call_testzip(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path, _ = _corpus(data_root, tmp_path)
    monkeypatch.setattr(
        zipfile.ZipFile,
        "testzip",
        lambda *_a, **_k: pytest.fail("testzip eagerly decompresses the whole archive"),
    )

    assert inspect_package(package_path).valid is True
    assert import_package(package_path, data_root=other_data_root).agent_id == "hunter"


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "revision/placeholder/files/agent.py:stream",
        "revision/placeholder/files/trailing.",
        "revision/placeholder/files/trailing ",
        "revision/placeholder/files/CON",
        "revision/placeholder/files/CON .txt",
        "revision/placeholder/files/NUL.txt",
        "revision/placeholder/files/com1.py",
    ],
)
def test_import_rejects_windows_alias_paths_on_every_host(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / f"windows_alias_{abs(hash(unsafe_name))}.bytefray-agent"
    member_name = unsafe_name.replace("placeholder", revision_id)
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(member_name, b"unsafe")

    assert inspect_package(evil).valid is False
    with pytest.raises(PackageUnsafePathError):
        import_package(evil, data_root=other_data_root)
    assert not (other_data_root / "agents").exists()


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


@pytest.mark.parametrize(
    "special_mode",
    [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK],
)
def test_import_rejects_special_unix_mode_entry(
    data_root: Path,
    other_data_root: Path,
    tmp_path: Path,
    special_mode: int,
) -> None:
    package_path, revision_id = _corpus(data_root, tmp_path)
    evil = tmp_path / f"special_entry_{special_mode}.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        special_info = zipfile.ZipInfo(f"revision/{revision_id}/files/special.py")
        special_info.external_attr = (special_mode | 0o777) << 16
        zout.writestr(special_info, b"not an ordinary file")

    with pytest.raises(PackageUnsafePathError):
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

    package_path, revision_id = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 16)
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

    package_path, revision_id = _corpus(data_root, tmp_path)
    monkeypatch.setattr(agent_package_module, "_MAX_SINGLE_FILE_SIZE", 10_000)
    monkeypatch.setattr(agent_package_module, "_MAX_TOTAL_SIZE", 100)
    evil = tmp_path / "total_too_big.bytefray-agent"
    with zipfile.ZipFile(package_path) as zin, zipfile.ZipFile(evil, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
        zout.writestr(f"revision/{revision_id}/files/a.txt", b"x" * 60)
        zout.writestr(f"revision/{revision_id}/files/b.txt", b"y" * 60)

    with pytest.raises(PackageInvalidError):
        import_package(evil, data_root=other_data_root, as_agent_id="evil")
