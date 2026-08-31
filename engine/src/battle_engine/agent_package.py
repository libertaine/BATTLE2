"""Portable Bytefray agent package format (``docs/specs/agent_package.md``).

Exports one Bytefray agent revision into a single, self-describing,
inspectable-without-execution ``.bytefray-agent`` ZIP file; inspects such a
file without importing or executing any of its contents; and safely imports
one into a local installation's ``agents/`` catalog and revision store with
fail-closed validation and best-effort cleanup on placement failure.

Built entirely as a transport wrapper around one already-archived
:mod:`battle_engine.agent_revisions` revision -- see
``docs/specs/agent_package.md`` Sec 0 for why. This module never imports,
compiles, or executes packaged agent source. It parses ``package.json`` and
the wrapped revision manifest as JSON, and safely parses the extracted
``agent.yaml`` as JSON/YAML data solely to bind compatibility-critical
claims to the verified payload bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import struct
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from battle_engine.agent_api import (
    SUPPORTED_AGENT_API_VERSIONS,
    AgentManifestError,
    describe_supported_agent_api_versions,
)
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
_MAX_PACKAGE_JSON_SIZE = 1024 * 1024  # 1 MiB; the v1 manifest is ordinarily < 1 KiB
_MAX_PACKAGE_JSON_COMPRESSED_SIZE = _MAX_PACKAGE_JSON_SIZE + 64 * 1024
_MAX_AGENT_MANIFEST_SIZE = 1024 * 1024
_MAX_AGENT_MANIFEST_COMPRESSED_SIZE = _MAX_AGENT_MANIFEST_SIZE + 64 * 1024
_MAX_SINGLE_COMPRESSED_SIZE = _MAX_SINGLE_FILE_SIZE + 4 * 1024 * 1024
_MAX_TOTAL_COMPRESSED_SIZE = _MAX_TOTAL_SIZE + 8 * 1024 * 1024
_MAX_MEMBER_NAME_BYTES = 4096
_MAX_CENTRAL_DIRECTORY_SIZE = 32 * 1024 * 1024
# Compressed payload + bounded central-directory metadata + comparable local
# header/name overhead. This is deliberately checked before ZipFile parses
# and allocates the central-directory entry list.
_MAX_ARCHIVE_SIZE = (
    _MAX_TOTAL_COMPRESSED_SIZE + 2 * _MAX_CENTRAL_DIRECTORY_SIZE + 1024 * 1024
)

# Fixed ZIP metadata so repeated exports of the same content are
# byte-for-byte reproducible on one Python/zlib build (best-effort;
# agent_revision_id remains the authoritative logical identity -- Sec 4).
_FIXED_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)
_FIXED_FILE_MODE = 0o644

_PACKAGE_JSON_MEMBER = "package.json"
_REVISION_DIR_MEMBER = "revision"
_REVISION_EXCLUDED_NAMES = frozenset({".git", "__pycache__"})
_WINDOWS_DEVICE_BASENAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)

_EOCD_SIGNATURE = b"PK\x05\x06"
_CENTRAL_FILE_SIGNATURE = b"PK\x01\x02"
_EOCD_FIXED_SIZE = 22
_MAX_ZIP_COMMENT_SIZE = 0xFFFF
_CENTRAL_FILE_FIXED_SIZE = 46

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
# Bounded ZIP container preflight
# ---------------------------------------------------------------------------


def _find_eocd(handle: BinaryIO, archive_size: int) -> tuple[int, tuple[Any, ...]]:
    """Find a structurally complete non-ZIP64 EOCD from a bounded tail read."""

    tail_size = min(archive_size, _EOCD_FIXED_SIZE + _MAX_ZIP_COMMENT_SIZE)
    handle.seek(archive_size - tail_size)
    tail = handle.read(tail_size)
    position = tail.rfind(_EOCD_SIGNATURE)
    while position >= 0:
        if len(tail) - position >= _EOCD_FIXED_SIZE:
            record = tail[position : position + _EOCD_FIXED_SIZE]
            fields = struct.unpack("<4s4H2LH", record)
            comment_size = fields[7]
            if position + _EOCD_FIXED_SIZE + comment_size == len(tail):
                return archive_size - tail_size + position, fields
        position = tail.rfind(_EOCD_SIGNATURE, 0, position)
    raise PackageInvalidError("Could not locate a valid ZIP end-of-central-directory record.")


def _preflight_zip_container(handle: BinaryIO) -> None:
    """Bound central-directory allocation before constructing ZipFile.

    ZipFile eagerly materializes every central-directory record as a
    ZipInfo. The normal member-count validation therefore runs too late to
    protect a synchronous inspector from a million-entry/huge-name ZIP.
    This raw pass reads only the EOCD and fixed central headers, counts the
    actual records (not merely the forgeable EOCD count), and skips their
    already-bounded variable metadata without decoding filenames.
    """

    archive_size = os.fstat(handle.fileno()).st_size
    if archive_size > _MAX_ARCHIVE_SIZE:
        raise PackageInvalidError(
            f"Package archive exceeds the maximum allowed size "
            f"({archive_size} > {_MAX_ARCHIVE_SIZE} bytes)."
        )
    if archive_size < _EOCD_FIXED_SIZE:
        raise PackageInvalidError("Package is too small to contain a valid ZIP directory.")

    eocd_offset, fields = _find_eocd(handle, archive_size)
    (
        _signature,
        disk_number,
        central_disk,
        entries_on_disk,
        declared_entries,
        central_size,
        central_offset,
        _comment_size,
    ) = fields
    if disk_number != 0 or central_disk != 0 or entries_on_disk != declared_entries:
        raise PackageInvalidError("Multi-disk ZIP packages are not supported.")
    if (
        declared_entries == 0xFFFF
        or central_size == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
    ):
        # No valid package can require ZIP64 under the much smaller count and
        # byte limits above; rejecting it keeps this allocation guard simple.
        raise PackageInvalidError("ZIP64 package metadata is not supported by this format.")
    if declared_entries > _MAX_MEMBER_COUNT:
        raise PackageInvalidError(
            f"Package contains too many entries ({declared_entries} > {_MAX_MEMBER_COUNT})."
        )
    if central_size > _MAX_CENTRAL_DIRECTORY_SIZE:
        raise PackageInvalidError(
            "Package central directory exceeds the maximum allowed metadata size."
        )

    concatenated_prefix = eocd_offset - central_size - central_offset
    if concatenated_prefix < 0:
        raise PackageInvalidError("Package central-directory offsets are inconsistent.")
    central_start = central_offset + concatenated_prefix
    handle.seek(central_start)

    consumed = 0
    actual_entries = 0
    while consumed < central_size:
        header = handle.read(_CENTRAL_FILE_FIXED_SIZE)
        if len(header) != _CENTRAL_FILE_FIXED_SIZE:
            raise PackageInvalidError("Package central directory is truncated.")
        if header[:4] != _CENTRAL_FILE_SIGNATURE:
            raise PackageInvalidError("Package central directory contains an invalid record.")
        name_size = int.from_bytes(header[28:30], "little")
        extra_size = int.from_bytes(header[30:32], "little")
        comment_size = int.from_bytes(header[32:34], "little")
        if name_size > _MAX_MEMBER_NAME_BYTES:
            raise PackageInvalidError(
                f"Package member name exceeds {_MAX_MEMBER_NAME_BYTES} encoded bytes."
            )
        record_size = _CENTRAL_FILE_FIXED_SIZE + name_size + extra_size + comment_size
        if consumed + record_size > central_size:
            raise PackageInvalidError("Package central-directory record exceeds its boundary.")
        actual_entries += 1
        if actual_entries > _MAX_MEMBER_COUNT:
            raise PackageInvalidError(
                f"Package contains too many central-directory records "
                f"({actual_entries} > {_MAX_MEMBER_COUNT})."
            )
        handle.seek(record_size - _CENTRAL_FILE_FIXED_SIZE, os.SEEK_CUR)
        consumed += record_size

    if consumed != central_size or actual_entries != declared_entries:
        raise PackageInvalidError(
            "Package central-directory entry count or size is inconsistent."
        )
    handle.seek(0)


def _open_preflighted_archive(package_path: Path) -> BinaryIO:
    """Open one archive and preflight the same handle ZipFile will parse."""

    try:
        handle = package_path.open("rb")
    except OSError as exc:
        raise PackageInvalidError(f"Could not open package archive: {exc}") from exc
    try:
        _preflight_zip_container(handle)
    except AgentPackageError:
        handle.close()
        raise
    except Exception as exc:
        handle.close()
        raise PackageInvalidError(f"Could not preflight package archive: {exc}") from exc
    return handle


# ---------------------------------------------------------------------------
# Safe, generic ZIP extraction (docs/specs/agent_package.md Sec 7, Layer 1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ValidatedArchive:
    """Metadata-only validation result; constructing it reads no member bytes."""

    package_info: zipfile.ZipInfo
    extract_members: tuple[tuple[zipfile.ZipInfo, Path], ...]


def _validate_portable_member_name(name: str, *, is_dir: bool) -> str:
    """Return the slash-relative path after platform-neutral name checks."""

    path_name = name[:-1] if is_dir and name.endswith("/") else name
    if (
        not path_name
        or "\\" in path_name
        or any(not ch.isprintable() for ch in path_name)
    ):
        raise PackageUnsafePathError(f"Unsafe or malformed path in package: {name!r}")

    try:
        encoded_name = path_name.encode("utf-8")
    except UnicodeError as exc:
        raise PackageUnsafePathError(
            f"Package path cannot be represented portably as UTF-8: {name!r}"
        ) from exc
    if len(encoded_name) > _MAX_MEMBER_NAME_BYTES:
        raise PackageUnsafePathError(
            f"Package path exceeds {_MAX_MEMBER_NAME_BYTES} encoded bytes: {name!r}"
        )

    for component in path_name.split("/"):
        # Validate for every supported destination OS, not only the host
        # doing this inspection. On Windows, colons name ADS streams,
        # trailing dots/spaces alias other paths, and device basenames are
        # not ordinary files even when followed by an extension.
        device_stem = component.partition(".")[0].rstrip(" .").casefold()
        if (
            not component
            or component in {".", ".."}
            or ":" in component
            or component.endswith((".", " "))
            or device_stem in _WINDOWS_DEVICE_BASENAMES
        ):
            raise PackageUnsafePathError(
                f"Package path is not portable or safe to materialize: {name!r}"
            )
    return path_name


def _validate_payload_relative_name(relative_path: str) -> None:
    """Validate a source path including its eventual fixed archive prefix."""

    synthetic_member = (
        f"{_REVISION_DIR_MEMBER}/agent-revision_{'0' * 64}/files/{relative_path}"
    )
    _validate_portable_member_name(synthetic_member, is_dir=False)


def _validate_member_metadata(
    infos: list[zipfile.ZipInfo], dest_root: Path
) -> _ValidatedArchive:
    """Validate a complete member set before any member read or write.

    ``ZipFile.testzip()`` is intentionally not used: it decompresses every
    member before the resource limits below can reject an oversized archive.
    The later extraction/read pass naturally verifies CRCs while consuming
    the bytes, after this metadata-only pass has bounded the work.
    """

    dest_root = dest_root.resolve()
    if len(infos) > _MAX_MEMBER_COUNT:
        raise PackageInvalidError(
            f"Package contains too many entries ({len(infos)} > {_MAX_MEMBER_COUNT})."
        )

    package_infos: list[zipfile.ZipInfo] = []
    planned: list[tuple[zipfile.ZipInfo, Path]] = []
    seen_case_folded: dict[str, str] = {}
    file_paths: dict[str, str] = {}
    all_paths: list[tuple[Path, str]] = []
    total_size = 0
    total_compressed_size = 0

    for info in infos:
        name = info.filename
        is_dir = info.is_dir()
        path_name = _validate_portable_member_name(name, is_dir=is_dir)

        unix_mode = info.external_attr >> 16
        unix_type = stat.S_IFMT(unix_mode)
        if unix_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise PackageUnsafePathError(
                "Package contains a special Unix filesystem entry, which is never accepted: "
                f"{name!r}"
            )
        if (is_dir and unix_type == stat.S_IFREG) or (
            not is_dir and unix_type == stat.S_IFDIR
        ):
            raise PackageInvalidError(
                f"Package entry type metadata disagrees with its path form: {name!r}"
            )
        if info.flag_bits & 0x1:
            raise PackageInvalidError(
                f"Package contains an encrypted entry, which is not supported: {name!r}"
            )

        dest = contained_path(dest_root, path_name)
        if dest is None or dest == dest_root:
            raise PackageUnsafePathError(
                f"Unsafe path in package (escapes or names the extraction root): {name!r}"
            )

        # Validate directories too. Otherwise a directory/file pair with
        # the same normalized path, or duplicate package.json directory
        # entries, could escape the collision pass merely because the
        # directory itself is not written explicitly.
        key = str(dest).casefold()
        if key in seen_case_folded:
            raise PackageInvalidError(
                "Package contains duplicate or case-colliding paths: "
                f"{seen_case_folded[key]!r} and {name!r}"
            )
        seen_case_folded[key] = name
        all_paths.append((dest, name))

        if info.file_size < 0 or info.compress_size < 0:
            raise PackageInvalidError(f"Package entry has an invalid negative size: {name!r}")
        if info.compress_size > _MAX_SINGLE_COMPRESSED_SIZE:
            raise PackageInvalidError(
                f"A compressed entry in the package exceeds the maximum allowed size: {name!r}"
            )
        total_compressed_size += info.compress_size
        if total_compressed_size > _MAX_TOTAL_COMPRESSED_SIZE:
            raise PackageInvalidError(
                "Package's total compressed size exceeds the maximum allowed."
            )
        if is_dir:
            if info.file_size:
                raise PackageInvalidError(
                    f"Package directory entry unexpectedly contains data: {name!r}"
                )
            continue
        components = path_name.split("/")
        is_agent_manifest = (
            len(components) == 4
            and components[0] == _REVISION_DIR_MEMBER
            and components[2:] == ["files", "agent.yaml"]
        )
        if is_agent_manifest and info.file_size > _MAX_AGENT_MANIFEST_SIZE:
            raise PackageInvalidError(
                f"Packaged agent.yaml exceeds the maximum safely parsed size "
                f"({_MAX_AGENT_MANIFEST_SIZE} bytes)."
            )
        if (
            is_agent_manifest
            and info.compress_size > _MAX_AGENT_MANIFEST_COMPRESSED_SIZE
        ):
            raise PackageInvalidError(
                "Packaged agent.yaml's compressed data exceeds the maximum safely "
                f"parsed size ({_MAX_AGENT_MANIFEST_COMPRESSED_SIZE} bytes)."
            )
        if info.file_size > _MAX_SINGLE_FILE_SIZE:
            raise PackageInvalidError(
                f"A file in the package exceeds the maximum allowed size: {name!r}"
            )
        total_size += info.file_size
        if total_size > _MAX_TOTAL_SIZE:
            raise PackageInvalidError("Package's total uncompressed size exceeds the maximum allowed.")

        if name == _PACKAGE_JSON_MEMBER:
            package_infos.append(info)
        else:
            planned.append((info, dest))

        file_paths[key] = name

    # Reject a regular file that is an ancestor of another member. Without
    # this graph check, ``revision/x`` plus ``revision/x/y`` passes the
    # same-path collision map but later fails at mkdir after reads begin.
    for dest, name in all_paths:
        for parent in dest.parents:
            if parent == dest_root:
                break
            parent_key = str(parent).casefold()
            if parent_key in file_paths:
                raise PackageInvalidError(
                    "Package contains a file/directory ancestor collision: "
                    f"{file_paths[parent_key]!r} and {name!r}"
                )

    if len(package_infos) != 1:
        raise PackageInvalidError(
            f"Package must contain exactly one {_PACKAGE_JSON_MEMBER}; found {len(package_infos)}."
        )
    package_info = package_infos[0]
    if package_info.file_size > _MAX_PACKAGE_JSON_SIZE:
        raise PackageInvalidError(
            f"{_PACKAGE_JSON_MEMBER} exceeds the maximum allowed size "
            f"({_MAX_PACKAGE_JSON_SIZE} bytes)."
        )
    if package_info.compress_size > _MAX_PACKAGE_JSON_COMPRESSED_SIZE:
        raise PackageInvalidError(
            f"{_PACKAGE_JSON_MEMBER}'s compressed data exceeds the maximum allowed size "
            f"({_MAX_PACKAGE_JSON_COMPRESSED_SIZE} bytes)."
        )
    return _ValidatedArchive(package_info, tuple(planned))


def _validate_archive_metadata(zf: zipfile.ZipFile, dest_root: Path) -> _ValidatedArchive:
    """Validate the complete ZIP central directory without reading members."""

    return _validate_member_metadata(zf.infolist(), dest_root)


def _extract_validated_members(zf: zipfile.ZipFile, archive: _ValidatedArchive) -> None:
    """Extract a metadata-validated plan into its already-resolved temp paths."""

    for info, dest in archive.extract_members:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, dest.open("wb") as target:
                shutil.copyfileobj(source, target)
        except Exception as exc:
            raise PackageInvalidError(
                f"Could not read package entry {info.filename!r}: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# package.json reading/validation
# ---------------------------------------------------------------------------


def _read_package_json(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    try:
        raw = zf.read(info)
    except Exception as exc:
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
        if any(not ch.isprintable() for ch in value):
            raise PackageInvalidError(
                f"package.json field {name!r} contains control/non-printing characters."
            )

    _validate_target_agent_id(data["agent_id"])
    if not _valid_revision_id_shape(data["agent_revision_id"]):
        raise PackageInvalidError(
            "package.json field 'agent_revision_id' is not a valid "
            "content-addressed revision id."
        )

    for name in ("display_name", "agent_version", "entry_point", "exported_at", "bytefray_version"):
        value = data.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise PackageInvalidError(f"package.json field {name!r} must be a string or null.")
        if any(not ch.isprintable() for ch in value):
            raise PackageInvalidError(
                f"package.json field {name!r} contains control/non-printing characters."
            )

    api_version = data.get("agent_api_version")
    if api_version is not None and (isinstance(api_version, bool) or not isinstance(api_version, int)):
        raise PackageInvalidError("package.json field 'agent_api_version' must be an integer or null.")

    file_count = data.get("file_count")
    if not isinstance(file_count, int) or isinstance(file_count, bool) or file_count < 0:
        raise PackageInvalidError("package.json field 'file_count' must be a non-negative integer.")

    omitted_count = data.get("revision_omitted_count")
    if not isinstance(omitted_count, int) or isinstance(omitted_count, bool) or omitted_count < 0:
        raise PackageInvalidError(
            "package.json field 'revision_omitted_count' must be a non-negative integer."
        )

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
    if kind == "python" and api_version not in SUPPORTED_AGENT_API_VERSIONS:
        compatible = False
        notes.append(
            f"package requires unsupported Agent API v{api_version!r}; this "
            f"installation supports Agent API versions "
            f"{describe_supported_agent_api_versions()}."
        )

    return compatible, tuple(notes)


def _validate_target_agent_id(agent_id: str) -> None:
    if not AGENT_ID_PATTERN.match(agent_id) or len(agent_id) > MAX_AGENT_ID_LENGTH:
        raise PackageInvalidError(
            f"Invalid agent id {agent_id!r}: must match {AGENT_ID_PATTERN.pattern!r} "
            f"(max {MAX_AGENT_ID_LENGTH} characters)."
        )


def _verify_packaged_revision(store_root: Path, revision_id: str) -> bool:
    """Run revision verification without leaking malformed-payload exceptions."""

    try:
        return verify_revision(store_root, revision_id)
    except Exception as exc:
        raise PackageInvalidError(
            f"Packaged revision {revision_id!r} could not be verified safely: {exc}"
        ) from exc


def _validate_extracted_payload(
    store_root: Path, revision_id: str, data: dict[str, Any]
) -> None:
    """Bind package.json's factual claims to the verified revision bytes.

    Parsing ``agent.yaml`` through ``agent_spec_from_dir`` uses JSON/
    ``yaml.safe_load`` only; it never imports the packaged entry point.
    Without this cross-check, package.json could be edited independently of
    the content-addressed revision to disguise an Agent API incompatibility.
    """

    try:
        revision_manifest = read_revision_manifest(store_root, revision_id)
    except Exception as exc:
        raise PackageInvalidError(
            f"Packaged revision {revision_id!r} manifest could not be read safely: {exc}"
        ) from exc
    if revision_manifest is None:
        raise PackageIntegrityError(
            f"Packaged revision {revision_id!r} has no readable manifest."
        )

    raw_files = revision_manifest.get("files")
    raw_omitted = revision_manifest.get("omitted")
    recorded_complete = revision_manifest.get("complete")
    if not isinstance(raw_files, list) or not all(isinstance(item, str) for item in raw_files):
        raise PackageIntegrityError(f"Packaged revision {revision_id!r} has a malformed file list.")
    if not isinstance(raw_omitted, list) or not isinstance(recorded_complete, bool):
        raise PackageIntegrityError(
            f"Packaged revision {revision_id!r} has malformed completeness metadata."
        )

    mirrored = {
        "revision_complete": recorded_complete,
        "revision_omitted_count": len(raw_omitted),
        "file_count": len(raw_files),
    }
    for field_name, expected_value in mirrored.items():
        if data.get(field_name) != expected_value:
            raise PackageInvalidError(
                f"package.json field {field_name!r} disagrees with the verified revision "
                f"({data.get(field_name)!r} != {expected_value!r})."
            )

    files_dir = store_root / revision_id / "files"
    try:
        spec = agent_spec_from_dir(files_dir)
    except Exception as exc:
        raise PackageInvalidError(
            f"Packaged agent manifest could not be parsed safely: {exc}"
        ) from exc
    if spec is None:
        raise PackageInvalidError(
            "Packaged revision does not contain a discoverable agent.yaml or agent.py."
        )

    manifest = spec.manifest
    factual_fields = {
        "kind": spec.kind,
        "agent_version": spec.version,
        "entry_point": spec.entry_point,
        "agent_api_version": spec.api_version if spec.kind == "python" else None,
    }
    declared_display = manifest.get("display") or manifest.get("name")
    if declared_display is not None:
        factual_fields["display_name"] = str(declared_display)
    for factual_name, factual_value in factual_fields.items():
        if data.get(factual_name) != factual_value:
            raise PackageInvalidError(
                f"package.json field {factual_name!r} disagrees with the packaged agent manifest "
                f"({data.get(factual_name)!r} != {factual_value!r})."
            )


def _check_preflight_size(name: str, size: int, *, count: int, total: int) -> None:
    if count + 2 > _MAX_MEMBER_COUNT:
        raise PackageInvalidError(
            f"Agent source would produce too many package entries ({count + 2} > "
            f"{_MAX_MEMBER_COUNT})."
        )
    if name == "agent.yaml" and size > _MAX_AGENT_MANIFEST_SIZE:
        raise PackageInvalidError(
            f"Agent manifest exceeds the maximum safely parsed package size: {name!r}."
        )
    if size > _MAX_SINGLE_FILE_SIZE:
        raise PackageInvalidError(
            f"Agent source file exceeds the maximum package size: {name!r}."
        )
    if total > _MAX_TOTAL_SIZE:
        raise PackageInvalidError(
            "Agent source exceeds the package's maximum total uncompressed size."
        )


def _preflight_live_source(agent_dir: Path) -> None:
    """Bound ordinary source files from stat metadata before ``read_bytes``.

    Regular files and internally resolving file links (which the
    authoritative revision walk dereferences) are rejected before their
    contents are loaded into memory. Directory/external/broken links remain
    omissions and are never traversed.
    """

    base = agent_dir.resolve()
    stack = [base]
    count = 0
    total = 0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    while stack:
        directory = stack.pop()
        try:
            iterator = os.scandir(directory)
        except OSError:
            continue
        with iterator:
            for entry in iterator:
                if entry.name in _REVISION_EXCLUDED_NAMES:
                    continue
                child = Path(entry.path)
                relative = child.relative_to(base).as_posix()
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                is_link_like = entry.is_symlink() or bool(
                    getattr(metadata, "st_file_attributes", 0) & reparse_flag
                )
                if is_link_like:
                    # The authoritative revision walk dereferences an
                    # internally resolving file link, so its target must be
                    # bounded here too. Directory/external/broken links are
                    # omissions and are deliberately not traversed.
                    try:
                        resolved = child.resolve()
                        resolved.relative_to(base)
                        target_metadata = resolved.stat()
                    except (OSError, RuntimeError, ValueError):
                        continue
                    if not stat.S_ISREG(target_metadata.st_mode):
                        continue
                    _validate_payload_relative_name(relative)
                    count += 1
                    total += target_metadata.st_size
                    _check_preflight_size(
                        relative,
                        target_metadata.st_size,
                        count=count,
                        total=total,
                    )
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    stack.append(child)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                _validate_payload_relative_name(relative)
                count += 1
                total += metadata.st_size
                _check_preflight_size(relative, metadata.st_size, count=count, total=total)


def _validate_walk_payload(entries: tuple[Any, ...]) -> None:
    """Recheck actual frozen byte lengths after the metadata preflight."""

    total = 0
    for count, entry in enumerate(entries, start=1):
        _validate_payload_relative_name(entry.relative_path)
        size = len(entry.content)
        total += size
        _check_preflight_size(entry.relative_path, size, count=count, total=total)


def _valid_revision_id_shape(revision_id: str) -> bool:
    prefix = "agent-revision_"
    digest = revision_id.removeprefix(prefix)
    return (
        revision_id.startswith(prefix)
        and len(digest) == 64
        and all(ch in "0123456789abcdef" for ch in digest)
    )


def _preflight_stored_revision(store_root: Path, revision_id: str) -> dict[str, Any]:
    """Stat a historical snapshot before verification reads its payload bytes."""

    if not _valid_revision_id_shape(revision_id):
        raise PackageIntegrityError(f"Invalid revision id: {revision_id!r}.")
    snapshot_dir = store_root / revision_id
    manifest_path = snapshot_dir / "manifest.json"
    try:
        manifest_size = manifest_path.stat().st_size
    except OSError as exc:
        raise PackageIntegrityError(
            f"Revision {revision_id!r} has no readable manifest: {exc}"
        ) from exc
    if manifest_size > _MAX_SINGLE_FILE_SIZE:
        raise PackageInvalidError(
            f"Revision {revision_id!r}'s manifest exceeds the maximum package file size."
        )
    try:
        revision_manifest = read_revision_manifest(store_root, revision_id)
    except Exception as exc:
        raise PackageIntegrityError(
            f"Revision {revision_id!r} manifest could not be read safely: {exc}"
        ) from exc
    if revision_manifest is None:
        raise PackageIntegrityError(f"Revision {revision_id!r} has no readable manifest.")
    raw_files = revision_manifest.get("files")
    if not isinstance(raw_files, list) or not all(isinstance(item, str) for item in raw_files):
        raise PackageIntegrityError(f"Revision {revision_id!r} manifest is malformed.")

    files_dir = snapshot_dir / "files"
    total = manifest_size
    for count, relative_path in enumerate(raw_files, start=1):
        _validate_payload_relative_name(relative_path)
        source_path = contained_path(files_dir, relative_path)
        if source_path is None:
            raise PackageIntegrityError(
                f"Revision {revision_id!r} has an unsafe file path: {relative_path!r}."
            )
        try:
            size = source_path.stat().st_size
        except OSError as exc:
            raise PackageIntegrityError(
                f"Revision {revision_id!r} references an unreadable file: {relative_path!r}."
            ) from exc
        total += size
        _check_preflight_size(relative_path, size, count=count, total=total)
    return revision_manifest


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise PackageInvalidError(f"Could not read exported package {path}: {exc}") from exc
    return hasher.hexdigest()


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
    package_bytes = json.dumps(package_manifest, indent=2, sort_keys=True).encode("utf-8")
    revision_bytes = json.dumps(revision_manifest, indent=2, sort_keys=True).encode("utf-8")
    member_payloads = [
        (_PACKAGE_JSON_MEMBER, package_bytes),
        (f"{_REVISION_DIR_MEMBER}/{revision_id}/manifest.json", revision_bytes),
        *[
            (
                f"{_REVISION_DIR_MEMBER}/{revision_id}/files/{relative_path}",
                payload_by_relative_path[relative_path],
            )
            for relative_path in ordered_relative_paths
        ],
    ]
    synthetic_infos: list[zipfile.ZipInfo] = []
    for name, payload in member_payloads:
        info = zipfile.ZipInfo(name)
        info.file_size = len(payload)
        info.compress_size = len(payload)
        synthetic_infos.append(info)
    # Apply the reader's exact path/count/size rules before creating the
    # destination directory or opening the temporary output file.
    _validate_member_metadata(synthetic_infos, output_path.parent / ".package-layout-check")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.parent / f".tmp-{output_path.name}-{uuid.uuid4().hex}"
    try:
        with zipfile.ZipFile(temp_path, "w") as zf:
            _zip_write(zf, _PACKAGE_JSON_MEMBER, package_bytes)
            _zip_write(
                zf,
                f"{_REVISION_DIR_MEMBER}/{revision_id}/manifest.json",
                revision_bytes,
            )
            for relative_path in ordered_relative_paths:
                _zip_write(
                    zf,
                    f"{_REVISION_DIR_MEMBER}/{revision_id}/files/{relative_path}",
                    payload_by_relative_path[relative_path],
                )
        archive_size = temp_path.stat().st_size
        if archive_size > _MAX_ARCHIVE_SIZE:
            raise PackageInvalidError(
                f"Exported package exceeds the maximum allowed archive size "
                f"({archive_size} > {_MAX_ARCHIVE_SIZE} bytes)."
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
    _validate_target_agent_id(agent_id)
    store_root = agent_revisions_root(root)
    local_archive_error: str | None = None

    if revision_id is not None:
        revision_manifest = _preflight_stored_revision(store_root, revision_id)
        try:
            revision_verified = verify_revision(store_root, revision_id)
        except Exception as exc:
            raise PackageIntegrityError(
                f"Revision {revision_id!r} could not be verified safely: {exc}"
            ) from exc
        if not revision_verified:
            raise PackageIntegrityError(
                f"Refusing to export revision {revision_id!r} for agent {agent_id!r}: it is "
                "not present in this installation's revision store, or does not verify "
                "against its own stored copy."
            )
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
            try:
                payload_by_relative_path[relative_path] = source_path.read_bytes()
            except OSError as exc:
                raise PackageIntegrityError(
                    f"Revision {revision_id!r} file could not be read: {relative_path!r}."
                ) from exc
        try:
            spec_for_metadata = agent_spec_from_dir(files_dir)
        except Exception as exc:
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
        # Preflight first because resolve_agent itself safely parses
        # agent.yaml; the explicit manifest cap must therefore apply before
        # even that non-executing parse happens.
        try:
            agents_root = (root / "agents").resolve()
            live_agent_dir = (agents_root / agent_id).resolve()
            live_agent_dir.relative_to(agents_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise PackageInvalidError(
                f"Agent {agent_id!r} does not resolve safely within this installation."
            ) from exc
        _preflight_live_source(live_agent_dir)
        try:
            spec = resolve_agent(root, agent_id)
        except SystemExit as exc:
            raise PackageInvalidError(str(exc)) from exc
        except AgentManifestError as exc:
            raise PackageInvalidError(str(exc)) from exc
        if spec.kind not in SUPPORTED_KINDS:
            raise PackageUnsupportedKindError(
                f"Agent {agent_id!r} has kind={spec.kind!r}: a manifest-only built-in "
                "starter agent's behavior is supplied by this Bytefray installation "
                "itself, not by files in its own directory, so there is nothing "
                "portable to export. See docs/specs/agent_package.md Sec 2."
            )
        walk = walk_agent_files(spec.dir)
        _validate_walk_payload(walk.entries)
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
    manifest_meta = spec_for_metadata.manifest
    display_name = str(
        manifest_meta.get("display") or manifest_meta.get("name") or agent_id
    )
    package_manifest: dict[str, Any] = {
        "schema": PACKAGE_SCHEMA,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "exported_at": _utc_now_iso(),
        "bytefray_version": project_info.version,
        "agent_id": agent_id,
        "display_name": display_name,
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
    # The writer and reader share the same schema/field contract. Validate
    # the just-constructed manifest before creating the destination so a
    # malformed local display/version/entrypoint cannot produce a package
    # that this installation immediately refuses to inspect.
    _check_schema(package_manifest)
    _validate_package_fields(package_manifest)

    output_path = _resolve_output_path(agent_id, resolved_revision_id, output)
    try:
        _write_package_zip(
            output_path,
            package_manifest,
            revision_manifest,
            payload_by_relative_path,
            file_list,
        )
    except OSError as exc:
        raise PackageInvalidError(f"Could not write exported package {output_path}: {exc}") from exc
    package_sha256 = _sha256_file(output_path)

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

    Never imports, compiles, or executes packaged agent source.
    ``package.json`` and the wrapped revision manifest are parsed as JSON,
    and extracted ``agent.yaml`` is parsed as JSON/YAML data with safe-load
    semantics to verify compatibility facts. Never mutates the filesystem
    outside a private temporary directory that is removed before returning.
    """

    package_path = Path(package_path)
    try:
        with (
            _open_preflighted_archive(package_path) as archive_file,
            zipfile.ZipFile(archive_file) as zf,
            tempfile.TemporaryDirectory(prefix="bytefray-package-inspect-") as tmp,
        ):
            tmp_root = Path(tmp)
            archive = _validate_archive_metadata(zf, tmp_root)
            data = _read_package_json(zf, archive.package_info)
            _check_schema(data)
            _validate_package_fields(data)
            revision_id = data["agent_revision_id"]
            _extract_validated_members(zf, archive)
            store_root = tmp_root / _REVISION_DIR_MEMBER
            integrity_verified = _verify_packaged_revision(store_root, revision_id)
            if integrity_verified:
                _validate_extracted_payload(store_root, revision_id, data)
    except AgentPackageError as exc:
        return _invalid_inspection(package_path, str(exc))
    except Exception as exc:
        return _invalid_inspection(package_path, f"Could not read package archive: {exc}")

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
# import (fail-closed validation, guarded placement)
# ---------------------------------------------------------------------------


def import_package(
    package_path: Path | str,
    *,
    data_root: Path | None = None,
    as_agent_id: str | None = None,
) -> ImportResult:
    """Safely import one ``.bytefray-agent`` package with fail-closed gates.

    Phases (docs/specs/agent_package.md Sec 7): read + validate
    ``package.json`` -> safe-extract to a private temporary directory ->
    verify the wrapped revision's integrity (existing, unmodified
    ``verify_revision``) -> compatibility check -> collision check against
    the destination -> guarded placement (existing, unmodified
    ``restore_revision``) -> best-effort local revision-store population.
    Nothing is written to ``agents/`` unless every earlier phase succeeds;
    an existing agent at the destination is never overwritten. An ordinary
    placement I/O failure is reported and cleaned up on a best-effort basis;
    the error remains explicit if filesystem cleanup cannot remove all residue.
    """

    root = (data_root or get_data_root()).expanduser().resolve()
    package_path = Path(package_path)

    try:
        with (
            _open_preflighted_archive(package_path) as archive_file,
            zipfile.ZipFile(archive_file) as zf,
            tempfile.TemporaryDirectory(prefix="bytefray-package-import-") as tmp,
        ):
            tmp_root = Path(tmp)
            archive = _validate_archive_metadata(zf, tmp_root)
            data = _read_package_json(zf, archive.package_info)
            _check_schema(data)
            _validate_package_fields(data)

            target_agent_id = as_agent_id if as_agent_id is not None else data["agent_id"]
            _validate_target_agent_id(target_agent_id)
            revision_id = data["agent_revision_id"]

            agents_dir = root / "agents"
            target_dir = agents_dir / target_agent_id
            resolved_target = target_dir.resolve()
            try:
                resolved_target.relative_to(agents_dir.resolve())
            except ValueError as exc:
                raise PackageInvalidError(
                    f"Target agent id {target_agent_id!r} does not resolve within {agents_dir}."
                ) from exc

            _extract_validated_members(zf, archive)
            store_root = tmp_root / _REVISION_DIR_MEMBER
            if not _verify_packaged_revision(store_root, revision_id):
                raise PackageIntegrityError(
                    f"Package integrity check failed: revision {revision_id!r} does not verify "
                    "against its own packaged manifest/files. Refusing to import."
                )
            _validate_extracted_payload(store_root, revision_id, data)

            compatible, notes = _check_compatibility(data)
            if not compatible:
                raise PackageCompatibilityError(
                    "Package is not compatible with this Bytefray installation: "
                    + "; ".join(notes)
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
    except AgentPackageError:
        raise
    except Exception as exc:
        raise PackageInvalidError(f"Could not read package archive: {exc}") from exc

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
        mismatch = (
            f"Imported agent {target_agent_id!r} did not reproduce its declared revision "
            f"identity after placement (expected {revision_id!r}, got "
            f"{archival.agent_revision_id!r})."
        )
        try:
            shutil.rmtree(target_dir)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise PackageIntegrityError(
                f"{mismatch} Cleanup also failed ({exc}); files may remain at {target_dir}."
            ) from exc
        if target_dir.exists():
            raise PackageIntegrityError(
                f"{mismatch} Cleanup returned without removing {target_dir}; files may remain."
            )
        raise PackageIntegrityError(f"{mismatch} The imported target was removed.")

    return ImportResult(
        agent_id=target_agent_id,
        agent_revision_id=revision_id,
        target_dir=target_dir,
        already_present=False,
        local_archive_error=archival.error,
    )
