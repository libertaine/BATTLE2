"""Portable Bytefray agent package format (``docs/specs/agent_package.md``).

Exports one Bytefray agent revision into a single, self-describing,
inspectable-without-execution ``.bytefray-agent`` ZIP file; inspects such a
file without importing or executing any of its contents; and safely,
transactionally imports one into a local installation's ``agents/``
catalog and revision store.

Built entirely as a transport wrapper around one already-archived
:mod:`battle_engine.agent_revisions` revision -- see
``docs/specs/agent_package.md`` Sec 0 for why. This module never imports
or executes packaged agent source; ``package.json``/the wrapped revision
manifest are the only bytes ever parsed as anything other than opaque
file content.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from battle_engine.agent_api import AGENT_API_VERSION, AgentManifestError
from battle_engine.agent_revisions import (
    RevisionNotFoundError,
    RevisionRestoreError,
    agent_revision_fingerprint,
    agent_revision_id,
    agent_revisions_root,
    archive_agent_revision,
    archive_agent_revision_from_walk,
    restore_revision,
    revision_manifest_payload,
    verify_revision,
    walk_agent_files,
)
from battle_engine.agent_revisions import (
    read_manifest as read_revision_manifest,
)
from battle_engine.agent_scaffold import AGENT_ID_PATTERN, MAX_AGENT_ID_LENGTH
from battle_engine.agents import agent_spec_from_dir, resolve_agent
from battle_engine.paths import contained_path, get_data_root
from battle_engine.project_info import get_project_info

__all__ = [
    "PACKAGE_EXTENSION",
    "PACKAGE_SCHEMA",
    "PACKAGE_SCHEMA_VERSION",
    "SUPPORTED_KINDS",
    "AgentPackageError",
    "ExportResult",
    "ImportResult",
    "PackageCompatibilityError",
    "PackageImportConflictError",
    "PackageInspection",
    "PackageIntegrityError",
    "PackageInvalidError",
    "PackageSchemaUnsupportedError",
    "PackageUnsafePathError",
    "PackageUnsupportedKindError",
    "export_agent",
    "import_package",
    "inspect_package",
]

PACKAGE_SCHEMA = "bytefray.agent_package"
PACKAGE_SCHEMA_VERSION = 1
PACKAGE_EXTENSION = ".bytefray-agent"

# kind="builtin" is deliberately excluded -- see docs/specs/agent_package.md
# Sec 2: a manifest-only starter's behavior is supplied by the Bytefray
# installation itself, not by anything in its own directory, so there is
# nothing portable to package.
SUPPORTED_KINDS = ("python", "blob")

# Conservative, generous resource limits against pathological archives
# (docs/specs/agent_package.md Sec 7 / parent task Sec 26). An agent
# directory is source code plus at most one model.blob, not a dataset.
_MAX_MEMBER_COUNT = 5000
_MAX_SINGLE_FILE_SIZE = 256 * 1024 * 1024  # 256 MiB
_MAX_TOTAL_SIZE = 512 * 1024 * 1024  # 512 MiB

# Fixed ZIP metadata so repeated exports of the same content are
# byte-for-byte reproducible on one Python/zlib build (best-effort;
# agent_revision_id remains the authoritative logical identity -- Sec 4).
_FIXED_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)
_FIXED_FILE_MODE = 0o644

_CONTROL_CHARS = frozenset(chr(c) for c in range(0x20))
_PACKAGE_JSON_MEMBER = "package.json"
_REVISION_DIR_MEMBER = "revision"


class AgentPackageError(ValueError):
    """Base class for diagnostics safe to present through CLI surfaces."""

    code = "agent_package_error"


class PackageUnsupportedKindError(AgentPackageError):
    code = "package_unsupported_kind"


class PackageInvalidError(AgentPackageError):
    code = "package_invalid"


class PackageSchemaUnsupportedError(AgentPackageError):
    code = "package_schema_unsupported"


class PackageIntegrityError(AgentPackageError):
    code = "package_integrity_failed"


class PackageCompatibilityError(AgentPackageError):
    code = "package_compatibility_failed"


class PackageUnsafePathError(AgentPackageError):
    code = "package_path_unsafe"


class PackageImportConflictError(AgentPackageError):
    code = "package_import_conflict"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a successful :func:`export_agent` call."""

    agent_id: str
    agent_revision_id: str
    complete: bool
    omitted_count: int
    file_count: int
    package_path: Path
    package_sha256: str
    local_archive_error: str | None


@dataclass(frozen=True)
class PackageInspection:
    """No-execution report over one ``.bytefray-agent`` file.

    ``valid=False`` means the archive/schema itself could not be read or
    parsed -- every other field is ``None``/empty in that case.
    ``valid=True`` but ``compatible=False`` means the package is
    well-formed and its integrity was checked, but this installation
    cannot import it (unsupported kind, or a required Agent API version it
    does not provide).
    """

    package_path: Path
    valid: bool
    error: str | None
    schema_version: int | None = None
    agent_id: str | None = None
    display_name: str | None = None
    kind: str | None = None
    agent_version: str | None = None
    entry_point: str | None = None
    agent_api_version: int | None = None
    agent_revision_id: str | None = None
    revision_complete: bool | None = None
    revision_omitted_count: int | None = None
    file_count: int | None = None
    exported_at: str | None = None
    bytefray_version: str | None = None
    integrity_verified: bool | None = None
    compatible: bool | None = None
    compatibility_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ImportResult:
    """Outcome of a successful :func:`import_package` call."""

    agent_id: str
    agent_revision_id: str
    target_dir: Path
    already_present: bool
    local_archive_error: str | None = None


# ---------------------------------------------------------------------------
# Safe, generic ZIP extraction (docs/specs/agent_package.md Sec 7, Layer 1)
# ---------------------------------------------------------------------------


def _safe_extract_members(
    zf: zipfile.ZipFile, dest_root: Path, *, skip: frozenset[str] = frozenset()
) -> None:
    """Safely extract every member of ``zf`` (except ``skip``) under ``dest_root``.

    Generic and package-format-agnostic: knows nothing about
    ``bytefray.agent_package``/``bytefray.agent_revision`` shapes. Every
    member name is treated as untrusted text. Validates every member
    before writing any of them (docs/specs/agent_package.md Sec 7).
    """

    dest_root = dest_root.resolve()
    infos = [info for info in zf.infolist() if info.filename not in skip]
    if len(infos) > _MAX_MEMBER_COUNT:
        raise PackageInvalidError(
            f"Package contains too many entries ({len(infos)} > {_MAX_MEMBER_COUNT})."
        )

    planned: list[tuple[zipfile.ZipInfo, Path]] = []
    seen_case_folded: dict[str, str] = {}
    total_size = 0
    for info in infos:
        name = info.filename
        if name.endswith("/"):
            continue  # directory entry; parents are created on demand below

        # This exporter never produces a name containing a backslash --
        # every internal path is POSIX-relative. Accepting one would make
        # extraction safety depend on which host OS interprets the name
        # (backslash is a path separator on Windows, an ordinary character
        # on POSIX) -- rejected outright rather than tolerated either way.
        # Also reject NUL/control characters and empty names outright.
        if not name or "\\" in name or any(ch in _CONTROL_CHARS for ch in name):
            raise PackageUnsafePathError(f"Unsafe or malformed path in package: {name!r}")

        # A ZIP entry can declare a Unix symlink mode in its external
        # attributes. zipfile does not itself materialize a real OS
        # symlink from this today, but relying on that implementation
        # detail rather than checking explicitly is exactly the
        # "zipfile.extractall() safety by accident" this feature must not
        # depend on (docs/specs/agent_package.md Sec 7).
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise PackageUnsafePathError(
                f"Package contains a symlink entry, which is never accepted: {name!r}"
            )

        dest = contained_path(dest_root, name)
        if dest is None:
            raise PackageUnsafePathError(
                f"Unsafe path in package (escapes the extraction root): {name!r}"
            )

        # Case-folded regardless of the host filesystem's own case
        # sensitivity: a package built on a case-sensitive host must not
        # silently collide when later imported on a case-insensitive one.
        key = str(dest).casefold()
        if key in seen_case_folded:
            raise PackageInvalidError(
                "Package contains duplicate or case-colliding paths: "
                f"{seen_case_folded[key]!r} and {name!r}"
            )
        seen_case_folded[key] = name

        if info.file_size > _MAX_SINGLE_FILE_SIZE:
            raise PackageInvalidError(
                f"A file in the package exceeds the maximum allowed size: {name!r}"
            )
        total_size += info.file_size
        if total_size > _MAX_TOTAL_SIZE:
            raise PackageInvalidError("Package's total uncompressed size exceeds the maximum allowed.")
        planned.append((info, dest))

    # Write only after every member has passed every check above --
    # matches restore_revision's own "validate every pair before writing
    # any of them" discipline (agent_revision.md Sec 7.3).
    for info, dest in planned:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as source, dest.open("wb") as target:
            shutil.copyfileobj(source, target)


# ---------------------------------------------------------------------------
# package.json reading/validation
# ---------------------------------------------------------------------------


def _read_package_json(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        info = zf.getinfo(_PACKAGE_JSON_MEMBER)
    except KeyError as exc:
        raise PackageInvalidError("Package is missing package.json.") from exc
    try:
        raw = zf.read(info)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackageInvalidError(f"Could not read package.json: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PackageInvalidError(f"package.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PackageInvalidError("package.json must contain a JSON object.")
    return data


def _check_schema(data: dict[str, Any]) -> None:
    if data.get("schema") != PACKAGE_SCHEMA:
        raise PackageInvalidError(
            f"Not a Bytefray agent package (unexpected schema {data.get('schema')!r})."
        )
    version = data.get("schema_version")
    if version != PACKAGE_SCHEMA_VERSION:
        raise PackageSchemaUnsupportedError(
            f"Unsupported {PACKAGE_SCHEMA} schema_version {version!r}; this Bytefray "
            f"installation supports version {PACKAGE_SCHEMA_VERSION}."
        )


def _validate_package_fields(data: dict[str, Any]) -> None:
    for name in ("agent_id", "kind", "agent_revision_id"):
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise PackageInvalidError(f"package.json field {name!r} must be a non-empty string.")

    api_version = data.get("agent_api_version")
    if api_version is not None and (isinstance(api_version, bool) or not isinstance(api_version, int)):
        raise PackageInvalidError("package.json field 'agent_api_version' must be an integer or null.")

    file_count = data.get("file_count")
    if not isinstance(file_count, int) or isinstance(file_count, bool) or file_count < 0:
        raise PackageInvalidError("package.json field 'file_count' must be a non-negative integer.")

    if not isinstance(data.get("revision_complete"), bool):
        raise PackageInvalidError("package.json field 'revision_complete' must be a boolean.")


def _check_compatibility(data: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Enforced compatibility only -- see docs/specs/agent_package.md Sec 5.

    Never mutates, never touches the filesystem; a pure function of the
    already-parsed ``package.json`` dict.
    """

    notes: list[str] = []
    compatible = True

    kind = data.get("kind")
    if kind not in SUPPORTED_KINDS:
        compatible = False
        notes.append(
            f"kind {kind!r} is not an importable package kind "
            f"(supported: {', '.join(SUPPORTED_KINDS)})."
        )

    api_version = data.get("agent_api_version")
    if kind == "python" and api_version != AGENT_API_VERSION:
        compatible = False
        notes.append(
            f"package requires Agent API v{api_version!r}; this installation "
            f"provides Agent API v{AGENT_API_VERSION}."
        )

    return compatible, tuple(notes)


def _validate_target_agent_id(agent_id: str) -> None:
    if not AGENT_ID_PATTERN.match(agent_id) or len(agent_id) > MAX_AGENT_ID_LENGTH:
        raise PackageInvalidError(
            f"Invalid agent id {agent_id!r}: must match {AGENT_ID_PATTERN.pattern!r} "
            f"(max {MAX_AGENT_ID_LENGTH} characters)."
        )


# ---------------------------------------------------------------------------
# Deterministic archive writer
# ---------------------------------------------------------------------------


def _zip_write(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_FIXED_ZIP_DATETIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (_FIXED_FILE_MODE & 0xFFFF) << 16
    zf.writestr(info, data)


def _write_package_zip(
    output_path: Path,
    package_manifest: dict[str, Any],
    revision_manifest: dict[str, Any],
    payload_by_relative_path: dict[str, bytes],
    ordered_relative_paths: list[str],
) -> None:
    revision_id = package_manifest["agent_revision_id"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.parent / f".tmp-{output_path.name}-{uuid.uuid4().hex}"
    try:
        with zipfile.ZipFile(temp_path, "w") as zf:
            _zip_write(
                zf, _PACKAGE_JSON_MEMBER, json.dumps(package_manifest, indent=2, sort_keys=True).encode("utf-8")
            )
            _zip_write(
                zf,
                f"{_REVISION_DIR_MEMBER}/{revision_id}/manifest.json",
                json.dumps(revision_manifest, indent=2, sort_keys=True).encode("utf-8"),
            )
            for relative_path in ordered_relative_paths:
                _zip_write(
                    zf,
                    f"{_REVISION_DIR_MEMBER}/{revision_id}/files/{relative_path}",
                    payload_by_relative_path[relative_path],
                )
        temp_path.replace(output_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _resolve_output_path(agent_id: str, revision_id: str, output: Path | None) -> Path:
    short = revision_id.removeprefix("agent-revision_")[:12]
    default_name = f"{agent_id}-{short}{PACKAGE_EXTENSION}"
    if output is None:
        return (Path.cwd() / default_name).resolve()
    output = Path(output).expanduser()
    if output.exists() and output.is_dir():
        return (output / default_name).resolve()
    return output.resolve()


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def export_agent(
    agent_id: str,
    *,
    data_root: Path | None = None,
    output: Path | None = None,
    revision_id: str | None = None,
) -> ExportResult:
    """Package one agent into a single ``.bytefray-agent`` file.

    With no ``revision_id``, freezes the agent's *current* on-disk source
    into a revision first (a single ``walk_agent_files`` read, reused for
    both identity and packaged payload -- docs/specs/agent_package.md
    Sec 1), the same way ``EvaluationService``'s freeze step already does.
    With an explicit ``revision_id``, packages that already-archived,
    already-verified historical revision instead, regardless of what
    ``agents/<agent_id>/`` currently contains.

    Raises :class:`PackageUnsupportedKindError` for a ``kind="builtin"``
    manifest-only starter agent (Sec 2) -- there is nothing portable in
    its own directory to package.
    """

    root = (data_root or get_data_root()).expanduser().resolve()
    store_root = agent_revisions_root(root)
    local_archive_error: str | None = None

    if revision_id is not None:
        if not verify_revision(store_root, revision_id):
            raise PackageIntegrityError(
                f"Refusing to export revision {revision_id!r} for agent {agent_id!r}: it is "
                "not present in this installation's revision store, or does not verify "
                "against its own stored copy."
            )
        revision_manifest = read_revision_manifest(store_root, revision_id)
        if revision_manifest is None:
            raise PackageIntegrityError(f"Revision {revision_id!r} has no readable manifest.")
        resolved_revision_id = revision_id
        files_dir = store_root / revision_id / "files"
        raw_files = revision_manifest.get("files")
        if not isinstance(raw_files, list) or not all(isinstance(f, str) for f in raw_files):
            raise PackageIntegrityError(f"Revision {revision_id!r} manifest is malformed.")
        payload_by_relative_path: dict[str, bytes] = {}
        for relative_path in raw_files:
            source_path = contained_path(files_dir, relative_path)
            if source_path is None or not source_path.is_file():
                raise PackageIntegrityError(
                    f"Revision {revision_id!r} manifest references a missing file: {relative_path!r}."
                )
            payload_by_relative_path[relative_path] = source_path.read_bytes()
        try:
            spec_for_metadata = agent_spec_from_dir(files_dir)
        except AgentManifestError as exc:
            raise PackageInvalidError(
                f"Revision {revision_id!r}'s archived manifest could not be parsed: {exc}"
            ) from exc
    else:
        # resolve_agent raises a bare SystemExit for an unknown/invalid
        # agent id -- an established convention for this codebase's
        # CLI-adjacent code (cli.py), but not an acceptable failure mode
        # from a presentation-neutral domain function (AGENTS.md's "Use
        # presentation-neutral domain/service functions that are easy to
        # test"). Translated to this module's own typed exception here,
        # at the one call site that crosses that boundary, rather than
        # touching resolve_agent itself (out of scope for this feature).
        try:
            spec = resolve_agent(root, agent_id)
        except SystemExit as exc:
            raise PackageInvalidError(str(exc)) from exc
        if spec.kind not in SUPPORTED_KINDS:
            raise PackageUnsupportedKindError(
                f"Agent {agent_id!r} has kind={spec.kind!r}: a manifest-only built-in "
                "starter agent's behavior is supplied by this Bytefray installation "
                "itself, not by files in its own directory, so there is nothing "
                "portable to export. See docs/specs/agent_package.md Sec 2."
            )
        walk = walk_agent_files(spec.dir)
        archival = archive_agent_revision_from_walk(walk, store_root=store_root, source_agent_id=agent_id)
        if archival.agent_revision_id is None:
            raise PackageInvalidError(f"Agent {agent_id!r} has no directory to export.")
        resolved_revision_id = archival.agent_revision_id
        local_archive_error = archival.error
        # Prefer the durably persisted manifest over a freshly rebuilt one:
        # _write_snapshot only ever writes archived_at/source_agent_id once
        # per distinct content (content-addressed dedup short-circuits a
        # second write), so reading it back preserves the true "first
        # seen" breadcrumb -- e.g. from an earlier `agents evaluate` run --
        # instead of this call stamping a fresh, misleading timestamp on
        # every repeated export of unchanged content. Only falls back to
        # rebuilding from the walk when the store write itself didn't
        # succeed (archival.archived is False, agent_revision.md Sec 4.3's
        # non-fatal I/O-failure case), since there is then nothing durable
        # to read back. Never affects agent_revision_id either way --
        # archived_at/source_agent_id are not hash inputs (Sec 1.2/Sec 3 of
        # docs/specs/agent_revision.md).
        stored_manifest = read_revision_manifest(store_root, resolved_revision_id) if archival.archived else None
        revision_manifest = (
            stored_manifest
            if stored_manifest is not None
            else revision_manifest_payload(resolved_revision_id, walk, agent_id)
        )
        payload_by_relative_path = {entry.relative_path: entry.content for entry in walk.entries}
        spec_for_metadata = spec

    if spec_for_metadata is None or spec_for_metadata.kind not in SUPPORTED_KINDS:
        raise PackageUnsupportedKindError(
            f"Agent {agent_id!r} (kind={getattr(spec_for_metadata, 'kind', None)!r}) cannot be "
            "packaged: only kind=python and kind=blob agents are supported export targets. "
            "See docs/specs/agent_package.md Sec 2."
        )

    file_list: list[str] = sorted(payload_by_relative_path)
    project_info = get_project_info()
    package_manifest: dict[str, Any] = {
        "schema": PACKAGE_SCHEMA,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "exported_at": _utc_now_iso(),
        "bytefray_version": project_info.version,
        "agent_id": agent_id,
        "display_name": spec_for_metadata.display,
        "kind": spec_for_metadata.kind,
        "agent_version": spec_for_metadata.version,
        "entry_point": spec_for_metadata.entry_point,
        "agent_api_version": (
            spec_for_metadata.api_version if spec_for_metadata.kind == "python" else None
        ),
        "agent_revision_id": resolved_revision_id,
        "revision_complete": bool(revision_manifest.get("complete")),
        "revision_omitted_count": len(revision_manifest.get("omitted") or []),
        "file_count": len(file_list),
    }

    output_path = _resolve_output_path(agent_id, resolved_revision_id, output)
    _write_package_zip(output_path, package_manifest, revision_manifest, payload_by_relative_path, file_list)
    package_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

    return ExportResult(
        agent_id=agent_id,
        agent_revision_id=resolved_revision_id,
        complete=bool(revision_manifest.get("complete")),
        omitted_count=len(revision_manifest.get("omitted") or []),
        file_count=len(file_list),
        package_path=output_path,
        package_sha256=package_sha256,
        local_archive_error=local_archive_error,
    )


# ---------------------------------------------------------------------------
# inspect (no-execution, read-only)
# ---------------------------------------------------------------------------


def _invalid_inspection(package_path: Path, error: str) -> PackageInspection:
    return PackageInspection(package_path=package_path, valid=False, error=error)


def inspect_package(package_path: Path | str) -> PackageInspection:
    """Report everything learnable about a package without executing anything.

    Never imports, compiles, or executes any packaged agent source; only
    ``package.json`` and the wrapped revision manifest are ever parsed as
    anything other than opaque bytes. Never mutates the filesystem outside
    a private temporary directory that is removed before returning.
    """

    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path) as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                return _invalid_inspection(package_path, f"Corrupt entry in archive: {bad_member}")

            try:
                data = _read_package_json(zf)
                _check_schema(data)
                _validate_package_fields(data)
            except AgentPackageError as exc:
                return _invalid_inspection(package_path, str(exc))

            revision_id = data["agent_revision_id"]
            with tempfile.TemporaryDirectory(prefix="bytefray-package-inspect-") as tmp:
                tmp_root = Path(tmp)
                try:
                    _safe_extract_members(zf, tmp_root, skip=frozenset({_PACKAGE_JSON_MEMBER}))
                except AgentPackageError as exc:
                    return _invalid_inspection(package_path, str(exc))
                store_root = tmp_root / _REVISION_DIR_MEMBER
                integrity_verified = verify_revision(store_root, revision_id)
    except zipfile.BadZipFile as exc:
        return _invalid_inspection(package_path, f"Not a valid ZIP archive: {exc}")
    except OSError as exc:
        return _invalid_inspection(package_path, f"Could not read package: {exc}")

    compatible, notes = _check_compatibility(data)
    if not integrity_verified:
        notes = (*notes, "packaged revision failed integrity verification.")

    return PackageInspection(
        package_path=package_path,
        valid=True,
        error=None,
        schema_version=data.get("schema_version"),
        agent_id=data.get("agent_id"),
        display_name=data.get("display_name"),
        kind=data.get("kind"),
        agent_version=data.get("agent_version"),
        entry_point=data.get("entry_point"),
        agent_api_version=data.get("agent_api_version"),
        agent_revision_id=revision_id,
        revision_complete=data.get("revision_complete"),
        revision_omitted_count=data.get("revision_omitted_count"),
        file_count=data.get("file_count"),
        exported_at=data.get("exported_at"),
        bytefray_version=data.get("bytefray_version"),
        integrity_verified=integrity_verified,
        compatible=compatible and integrity_verified,
        compatibility_notes=notes,
    )


# ---------------------------------------------------------------------------
# import (transactional)
# ---------------------------------------------------------------------------


def import_package(
    package_path: Path | str,
    *,
    data_root: Path | None = None,
    as_agent_id: str | None = None,
) -> ImportResult:
    """Safely, transactionally import one ``.bytefray-agent`` package.

    Phases (docs/specs/agent_package.md Sec 7): read + validate
    ``package.json`` -> safe-extract to a private temporary directory ->
    verify the wrapped revision's integrity (existing, unmodified
    ``verify_revision``) -> compatibility check -> collision check against
    the destination -> atomic placement (existing, unmodified
    ``restore_revision``) -> best-effort local revision-store population.
    Nothing is written to ``agents/`` unless every earlier phase succeeds;
    an existing agent at the destination is never overwritten.
    """

    root = (data_root or get_data_root()).expanduser().resolve()
    package_path = Path(package_path)

    with zipfile.ZipFile(package_path) as zf:
        bad_member = zf.testzip()
        if bad_member is not None:
            raise PackageInvalidError(f"Corrupt entry in archive: {bad_member}")

        data = _read_package_json(zf)
        _check_schema(data)
        _validate_package_fields(data)

        compatible, notes = _check_compatibility(data)
        if not compatible:
            raise PackageCompatibilityError(
                "Package is not compatible with this Bytefray installation: " + "; ".join(notes)
            )

        target_agent_id = as_agent_id if as_agent_id is not None else data["agent_id"]
        _validate_target_agent_id(target_agent_id)
        revision_id = data["agent_revision_id"]

        agents_dir = root / "agents"
        target_dir = agents_dir / target_agent_id
        resolved_target = target_dir.resolve()
        agents_dir.mkdir(parents=True, exist_ok=True)
        try:
            resolved_target.relative_to(agents_dir.resolve())
        except ValueError as exc:
            raise PackageInvalidError(
                f"Target agent id {target_agent_id!r} does not resolve within {agents_dir}."
            ) from exc

        with tempfile.TemporaryDirectory(prefix="bytefray-package-import-") as tmp:
            tmp_root = Path(tmp)
            _safe_extract_members(zf, tmp_root, skip=frozenset({_PACKAGE_JSON_MEMBER}))
            store_root = tmp_root / _REVISION_DIR_MEMBER
            if not verify_revision(store_root, revision_id):
                raise PackageIntegrityError(
                    f"Package integrity check failed: revision {revision_id!r} does not verify "
                    "against its own packaged manifest/files. Refusing to import."
                )

            if target_dir.exists():
                live_fingerprint = agent_revision_fingerprint(target_dir)
                live_revision_id = (
                    agent_revision_id(live_fingerprint) if live_fingerprint is not None else None
                )
                if live_revision_id == revision_id:
                    return ImportResult(
                        agent_id=target_agent_id,
                        agent_revision_id=revision_id,
                        target_dir=target_dir,
                        already_present=True,
                    )
                raise PackageImportConflictError(
                    f"An agent already exists at {target_dir} with different content. Refusing "
                    "to overwrite it. Re-run with --as to import under a different agent id."
                )

            try:
                restore_revision(store_root, revision_id, target_dir, force=False)
            except RevisionNotFoundError as exc:
                raise PackageIntegrityError(str(exc)) from exc
            except RevisionRestoreError as exc:
                raise PackageIntegrityError(str(exc)) from exc

    # Best-effort local provenance population: re-walk the files this call
    # itself just placed (trusted, just verified -- not a second read of
    # anything externally supplied) and seed the local revision store, so
    # `agents revisions show`/`agents evaluate` work immediately for the
    # freshly imported agent. A store-write I/O failure here is
    # non-fatal (agent_revision.md Sec 4.3's "plain I/O failure" category);
    # a fingerprint *mismatch* is not, and is fail-closed with rollback,
    # since the agent has already been placed but no longer verifiably
    # matches what was just imported.
    local_store_root = agent_revisions_root(root)
    archival = archive_agent_revision(target_dir, store_root=local_store_root, source_agent_id=target_agent_id)
    if archival.agent_revision_id != revision_id:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise PackageIntegrityError(
            f"Imported agent {target_agent_id!r} did not reproduce its declared revision "
            f"identity after placement (expected {revision_id!r}, got "
            f"{archival.agent_revision_id!r}); the partially imported agent has been removed."
        )

    return ImportResult(
        agent_id=target_agent_id,
        agent_revision_id=revision_id,
        target_dir=target_dir,
        already_present=False,
        local_archive_error=archival.error,
    )
