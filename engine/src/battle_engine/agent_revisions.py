"""Content-addressed, Qt-free agent revision store.

Implements the canonical tree-walk/hash machinery and the revision-store
primitives from ``docs/specs/agent_revision.md``. One-directional
dependency only: ``agent_evaluation.py`` (Phase 3) imports from this
module to wire revision capture into evaluation freeze/planning; this
module never imports ``agent_evaluation``/``EvaluationService`` back.

Nothing in this module touches ``battle_engine.agent_api.local_source_
fingerprint`` or ``agent_identity()`` -- those remain exactly as they are
today (docs/specs/agent_revision.md Sec 1.1). ``local_python_subset_
fingerprint`` below reuses ``local_source_fingerprint``'s algorithm/version
constant to produce a value directly *comparable* to it from an
already-computed walk, without calling it or duplicating its own read.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from battle_engine.agent_api import LOCAL_SOURCE_FINGERPRINT_VERSION
from battle_engine.paths import contained_path

__all__ = [
    "AGENT_REVISION_FINGERPRINT_VERSION",
    "AgentFileEntry",
    "AgentFileWalkResult",
    "OmittedAgentPath",
    "RevisionArchivalResult",
    "RevisionNotFoundError",
    "RevisionRestoreError",
    "agent_revision_fingerprint",
    "agent_revision_id",
    "agent_revisions_root",
    "archive_agent_revision",
    "archive_agent_revision_from_walk",
    "list_revisions",
    "local_python_subset_fingerprint",
    "read_manifest",
    "restore_revision",
    "verify_revision",
    "walk_agent_files",
]

AGENT_REVISION_FINGERPRINT_VERSION = 1

_MANIFEST_SCHEMA = "bytefray.agent_revision"
_MANIFEST_SCHEMA_VERSION = 1

# Names that are never part of a revision, at any depth -- build/VCS
# artifacts, not agent source. Checked by name only (not by path), matching
# agent_api.local_source_fingerprint's existing __pycache__ precedent.
_EXCLUDED_DIR_NAMES = frozenset({"__pycache__", ".git"})

# Omission reasons. Every one of these means "this entry was found in the
# tree but its bytes are not, and will never be, part of the archived
# snapshot" -- see docs/specs/agent_revision.md's "external symlink"
# resolution for why this must always be reported, never silently dropped.
REASON_EXTERNAL_TARGET = "external_target"
REASON_INTERNAL_SYMLINKED_DIRECTORY = "internal_symlinked_directory"
REASON_UNREADABLE = "unreadable"
REASON_NOT_A_FILE = "not_a_file"
REASON_RESOLVE_ERROR = "resolve_error"


class RevisionNotFoundError(ValueError):
    """Raised by ``restore_revision`` when ``revision_id`` has no manifest."""


class RevisionRestoreError(ValueError):
    """Raised by ``restore_revision`` for an unsafe or invalid restore target."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AgentFileEntry:
    """One included file: its agent-relative POSIX path and raw bytes."""

    relative_path: str
    content: bytes


@dataclass(frozen=True)
class OmittedAgentPath:
    """One path found under an agent directory but not included in the walk.

    ``target`` is the raw text of a symlink/junction's own link (read via
    ``os.readlink`` -- inspecting the link itself, never following it to
    whatever it points at). It is ``None`` when the omission wasn't a
    link, or when the link's own text couldn't be read.
    """

    relative_path: str
    reason: str
    target: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"relative_path": self.relative_path, "reason": self.reason, "target": self.target}


@dataclass(frozen=True)
class AgentFileWalkResult:
    entries: tuple[AgentFileEntry, ...]
    omitted: tuple[OmittedAgentPath, ...]

    @property
    def complete(self) -> bool:
        """True only when nothing under the agent directory was omitted.

        Always derived from ``omitted`` -- never a separately persisted
        flag that could drift from the list it summarizes (see
        docs/specs/agent_revision.md Sec 6's reasoning against
        ``agent_revision_available`` for why this project doesn't persist
        redundant derived booleans).
        """

        return not self.omitted


def _read_link_target(path: Path) -> str | None:
    """Best-effort raw link text. Inspects the link itself; never follows it."""

    try:
        return os.readlink(path)
    except OSError:
        return None


def _is_reparse_point(path: Path) -> bool:
    """True for any Windows reparse point: an NTFS junction, a symlink, or
    any other/future reparse tag this process doesn't otherwise recognize.

    Deliberately **not** ``Path.is_junction()`` (added in Python 3.12 and
    therefore silently absent -- ``getattr(..., None)`` returning ``None``,
    never raising -- on this project's supported 3.10/3.11, where a
    junction was previously falling through as an ordinary directory and
    getting traversed like one). Detected instead via ``os.lstat``'s
    ``st_file_attributes`` bit, which the ``os`` module has exposed on
    Windows since Python 3.5 -- the same mechanism on every one of this
    project's supported interpreters (3.10-3.13), so there is no
    version-dependent branch left to regress. ``os.lstat`` inspects the
    entry itself without following it, so this is safe to call on a link
    that resolves to a cycle or to nothing at all.

    Deliberately conservative, not narrowed to "is this specifically a
    ``mklink /J`` junction": any reparse-tagged entry (a mount point, a
    cloud-placeholder file, a deduplicated file, a future reparse type this
    code has never heard of) is treated the same cautious way, since the
    contract that matters is "never silently walk a reparse point as an
    ordinary directory," not "only handle the one reproduction case."
    Always ``False`` on non-Windows platforms, where reparse points don't
    exist, and ``False`` (never raises) for any entry this process cannot
    stat.
    """

    if os.name != "nt":
        return False
    try:
        attributes = os.lstat(path).st_file_attributes  # type: ignore[attr-defined]
    except OSError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _is_link_like(path: Path) -> bool:
    """True for a symlink or any Windows reparse point (e.g. an NTFS junction).

    Deliberately checked explicitly rather than relied on implicitly via
    ``os.walk``'s ``followlinks`` -- that flag's own junction handling has
    historically been platform/version-inconsistent on Windows, and the
    walk below must never silently traverse a link-like directory in either
    direction (Sec 2 of docs/specs/agent_revision.md). ``Path.is_symlink()``
    covers POSIX symlinks (and is retained for that portability, even
    though NTFS symlinks are also reparse points ``_is_reparse_point``
    would catch); ``_is_reparse_point`` covers every Windows reparse-point
    shape, junctions included, independent of interpreter version.
    """

    try:
        if path.is_symlink():
            return True
    except OSError:
        pass
    return _is_reparse_point(path)


def _classify_and_resolve(child: Path, base: Path) -> tuple[Path | None, bool, str | None]:
    """Resolve ``child``; return ``(resolved_or_None, inside_base, error_reason)``."""

    try:
        resolved = child.resolve()
    except OSError:
        return None, False, REASON_RESOLVE_ERROR
    try:
        resolved.relative_to(base)
    except ValueError:
        return resolved, False, None
    return resolved, True, None


def _walk_dir(
    dir_path: Path,
    base: Path,
    entries: list[AgentFileEntry],
    omitted: list[OmittedAgentPath],
) -> None:
    try:
        children = sorted(dir_path.iterdir(), key=lambda p: p.name)
    except OSError:
        return

    for child in children:
        if child.name in _EXCLUDED_DIR_NAMES:
            continue
        relative = child.relative_to(base).as_posix()

        if _is_link_like(child):
            target = _read_link_target(child)
            resolved, inside, error_reason = _classify_and_resolve(child, base)
            if error_reason is not None:
                omitted.append(OmittedAgentPath(relative, error_reason, target))
                continue
            if child.is_dir():
                # Never traversed, regardless of whether it resolves inside
                # or outside agent_dir -- an internally-resolving directory
                # symlink is still not walked, deliberately, to avoid cycle
                # risk (a link to an ancestor) and unbounded external walks
                # without needing per-call cycle-tracking. See
                # docs/specs/agent_revision.md's "external symlink"
                # resolution notes for the full argument.
                reason = REASON_INTERNAL_SYMLINKED_DIRECTORY if inside else REASON_EXTERNAL_TARGET
                omitted.append(OmittedAgentPath(relative, reason, target))
                continue
            if not inside:
                omitted.append(OmittedAgentPath(relative, REASON_EXTERNAL_TARGET, target))
                continue
            assert resolved is not None
            if not resolved.is_file():
                omitted.append(OmittedAgentPath(relative, REASON_NOT_A_FILE, target))
                continue
            try:
                content = resolved.read_bytes()
            except OSError:
                omitted.append(OmittedAgentPath(relative, REASON_UNREADABLE, target))
                continue
            entries.append(AgentFileEntry(relative, content))
            continue

        if child.is_dir():
            _walk_dir(child, base, entries, omitted)
            continue
        if not child.is_file():
            omitted.append(OmittedAgentPath(relative, REASON_NOT_A_FILE, None))
            continue
        try:
            content = child.read_bytes()
        except OSError:
            omitted.append(OmittedAgentPath(relative, REASON_UNREADABLE, None))
            continue
        entries.append(AgentFileEntry(relative, content))


def walk_agent_files(agent_dir: Path | None) -> AgentFileWalkResult:
    """Deterministically walk every entry under ``agent_dir``.

    Returns both the included ``(relative_path, content)`` file entries and
    an explicit, honest account of every entry that was found but could not
    be included, with why (``OmittedAgentPath``). Canonical shared
    primitive: both ``agent_revision_fingerprint`` (identity) and
    ``archive_agent_revision`` (storage) call this exactly once and derive
    everything else from that single read -- see
    docs/specs/agent_revision.md Sec 4.2 for why that single-read property
    matters (it is what lets archival be provably tied to the fingerprint
    it's filed under, not a second, later, possibly-different read).

    Excludes ``__pycache__``/``.git`` directories entirely (never even
    reported as omitted -- they are deliberately not part of an agent's
    revision, not something Bytefray failed to include).

    A symlink/junction resolving *outside* ``agent_dir`` is never followed;
    it is recorded as ``OmittedAgentPath(reason=REASON_EXTERNAL_TARGET)``,
    including the link's own raw target text, never the bytes at that
    external destination. A symlink/junction to a *directory* is never
    traversed either way (inside or outside ``agent_dir``) -- always a
    single omission entry, never partially expanded. A symlink to a *file*
    resolving inside ``agent_dir`` is dereferenced: its target's bytes are
    read and included as an ordinary entry.

    Returns an empty result (no entries, no omissions) when ``agent_dir``
    is ``None``, absent, or not a directory.
    """

    if agent_dir is None or not agent_dir.is_dir():
        return AgentFileWalkResult((), ())
    base = agent_dir.resolve()
    entries: list[AgentFileEntry] = []
    omitted: list[OmittedAgentPath] = []
    _walk_dir(base, base, entries, omitted)
    entries.sort(key=lambda e: e.relative_path)
    omitted.sort(key=lambda o: o.relative_path)
    return AgentFileWalkResult(tuple(entries), tuple(omitted))


def _hash_walk_result(version: int, walk: AgentFileWalkResult) -> str:
    """Versioned, deterministic digest over both included and omitted entries.

    Omissions are hashed too (Sec 1.2/"external symlink" resolution of
    docs/specs/agent_revision.md): two trees differing only in which
    external target an unresolvable symlink points to are, correctly,
    different revisions -- "we couldn't preserve this" is itself part of
    what a revision *is*, not something that erases its identity.
    """

    hasher = hashlib.sha256()
    hasher.update(str(version).encode("ascii"))
    hasher.update(b"\0ENTRIES")
    for entry in walk.entries:  # already sorted by relative_path
        hasher.update(b"\0")
        hasher.update(entry.relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(entry.content).digest())
    hasher.update(b"\0OMITTED")
    for omission in walk.omitted:  # already sorted by relative_path
        hasher.update(b"\0")
        hasher.update(omission.relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(omission.reason.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update((omission.target or "").encode("utf-8", errors="surrogateescape"))
    return hasher.hexdigest()


def local_python_subset_fingerprint(walk: AgentFileWalkResult) -> str | None:
    """The ``.py``-suffixed subset of ``walk``, hashed identically to
    ``agent_api.local_source_fingerprint``.

    Lets a caller that already holds one ``walk_agent_files`` result (e.g.
    Phase 3's freeze-step archival, docs/specs/agent_revision.md Sec 4.2)
    derive a value directly comparable to ``agent_identity()``'s
    ``local_source_fingerprint`` *without* a second, independent read of
    the same files -- ``local_source_fingerprint`` itself is never called
    here, only its exact accumulation scheme (same version marker, same
    sorted ``\\0``-joined relative-path/content-sha256 pairs) reproduced
    over bytes already in memory from ``walk``.

    Returns ``None`` when ``walk`` has no ``.py`` entries, matching
    ``local_source_fingerprint``'s own "no local .py files" contract.

    Not a byte-for-byte guarantee against ``local_source_fingerprint`` for
    every possible input: the two walks' directory-symlink handling can
    differ for an agent directory that itself contains an internally-
    resolving symlinked subdirectory full of ``.py`` files (``walk_agent_
    files`` never traverses a directory symlink at all -- Sec 2.2 --
    whereas ``local_source_fingerprint``'s own ``rglob`` traversal is
    version-dependent for that same input, pre-Python-3.13). No shipped or
    bundled agent has such a directory; see Sec 4.2's note on this narrow,
    documented, fail-closed-not-silent residual case.
    """

    py_entries = tuple(e for e in walk.entries if e.relative_path.endswith(".py"))
    if not py_entries:
        return None
    hasher = hashlib.sha256()
    hasher.update(str(LOCAL_SOURCE_FINGERPRINT_VERSION).encode("ascii"))
    for entry in py_entries:  # walk.entries is already sorted; the subset stays sorted
        hasher.update(b"\0")
        hasher.update(entry.relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(entry.content).digest())
    return hasher.hexdigest()


def agent_revision_fingerprint(agent_dir: Path | None) -> str | None:
    """A versioned, deterministic content fingerprint over ``agent_dir``.

    Returns ``None`` only when ``agent_dir`` itself doesn't exist / isn't a
    directory. A directory that exists but whose entire relevant content is
    omitted still produces a real, reproducible fingerprint over its
    (empty) entries plus its (non-empty) omissions -- "nothing could be
    preserved" is part of a revision's identity, not something that erases
    it.
    """

    if agent_dir is None or not agent_dir.is_dir():
        return None
    walk = walk_agent_files(agent_dir)
    return _hash_walk_result(AGENT_REVISION_FINGERPRINT_VERSION, walk)


def agent_revision_id(fingerprint: str) -> str:
    """The storage/display ID for a fingerprint.

    Uses the *full* 64-character SHA-256 hex digest, not
    ``result_model.stable_id``'s truncated 24-character form -- this ID is
    used directly as a content-addressed storage directory name (Sec 1.3 of
    docs/specs/agent_revision.md), where a truncated collision would
    silently merge two different agents' bytes under one path.
    """

    return f"agent-revision_{fingerprint}"


_REVISION_ID_PATTERN = re.compile(r"^agent-revision_[0-9a-f]{64}$")


def _is_valid_revision_id(revision_id: str) -> bool:
    """Structural shape check for a caller-supplied ``revision_id`` used as
    a storage path component.

    Every entry point that joins a ``revision_id`` onto ``store_root``
    (``read_manifest``, ``verify_revision``, and transitively
    ``restore_revision``) must reject anything not matching this exact
    ``agent_revision_id()`` shape *before* that join -- ``pathlib``'s ``/``
    operator silently discards the left operand when the right one is
    absolute or drive-qualified (Windows), so an unvalidated
    ``revision_id`` sourced from untrusted persisted data (e.g. a
    hand-edited or copied evaluation artifact's ``agent_revisions`` field,
    consumed by ``evaluation_history.verification``) could otherwise
    resolve entirely outside the intended store -- including a UNC path
    reaching an attacker-controlled host. This is defense in depth beyond
    what the fingerprint-mismatch outcome alone would eventually report:
    without it, a malicious ``revision_id`` string is joined and read
    *before* being found not to match, which is already too late for a
    path that reaches outside `store_root` (v0.8 audit finding).
    """

    return bool(_REVISION_ID_PATTERN.fullmatch(revision_id))


def agent_revisions_root(data_root: Path) -> Path:
    return data_root / "agent_revisions"


@dataclass(frozen=True)
class RevisionArchivalResult:
    """The outcome of one ``archive_agent_revision`` call.

    ``agent_revision_id``/``complete``/``omitted`` describe what the
    revision *is* -- derived purely from the walk, independent of whether
    the store write below succeeded. ``archived``/``error`` describe what
    happened when *this call* tried to persist it -- purely informational,
    and deliberately never folded into ``agent_revision_id`` or any other
    identity value (docs/specs/agent_revision.md's "keep agent_revision_
    error informational and non-identity-bearing"): a store-write failure
    changes nothing about which revision this is, only whether Bytefray
    currently holds a durable copy of it.
    """

    agent_revision_id: str | None
    complete: bool
    omitted: tuple[OmittedAgentPath, ...]
    archived: bool
    error: str | None


def archive_agent_revision(
    agent_dir: Path | None, *, store_root: Path, source_agent_id: str | None = None
) -> RevisionArchivalResult:
    """Fingerprint and durably archive one agent revision from a single read pass.

    Convenience wrapper around ``walk_agent_files`` +
    ``archive_agent_revision_from_walk`` for a caller that has no other use
    for the intermediate walk. A caller that also needs to derive something
    else from the identical bytes (Phase 3's freeze-step cross-check,
    docs/specs/agent_revision.md Sec 4.2) should call ``walk_agent_files``
    itself once and use ``archive_agent_revision_from_walk`` directly,
    rather than walking the tree a second time here.
    """

    if agent_dir is None or not agent_dir.is_dir():
        return RevisionArchivalResult(None, True, (), False, "agent_directory_missing")
    walk = walk_agent_files(agent_dir)
    return archive_agent_revision_from_walk(
        walk, store_root=store_root, source_agent_id=source_agent_id
    )


def archive_agent_revision_from_walk(
    walk: AgentFileWalkResult, *, store_root: Path, source_agent_id: str | None = None
) -> RevisionArchivalResult:
    """Fingerprint and durably archive an already-computed ``walk_agent_files`` result.

    The fingerprint/ID are computed first, from the walk alone; the store
    write is attempted second and can fail independently without changing
    either -- see ``RevisionArchivalResult``. ``source_agent_id`` is purely
    informational (Sec 3 of docs/specs/agent_revision.md) and carries no
    identity or authorship guarantee: content-addressing means whichever
    call's write is the one that durably lands (in the single-writer case,
    simply the first; under concurrent archival of identical content from
    two different catalog ids, whichever ``os.replace`` happens to complete
    first) is the one whose ``source_agent_id`` this snapshot keeps, and
    later archival of the same content under a different id is always a
    no-op against an already-populated manifest. A caller must not read
    ``source_agent_id`` as a reliable record of "the very first agent that
    ever produced this content" -- only as a best-effort breadcrumb toward
    one catalog entry that once had it.
    """

    fingerprint = _hash_walk_result(AGENT_REVISION_FINGERPRINT_VERSION, walk)
    revision_id = agent_revision_id(fingerprint)

    try:
        _write_snapshot(store_root, revision_id, walk, source_agent_id)
        archived, error = True, None
    except OSError as exc:
        archived, error = False, f"snapshot_write_failed: {exc}"

    return RevisionArchivalResult(revision_id, walk.complete, walk.omitted, archived, error)


def _write_snapshot(
    store_root: Path, revision_id: str, walk: AgentFileWalkResult, source_agent_id: str | None
) -> None:
    """Atomically create ``store_root/revision_id/`` if it doesn't already exist.

    Content-addressed: if the final directory already has a manifest, the
    content it names is already known-identical (same ID implies same
    bytes), so the write is skipped entirely rather than redone.
    """

    final_dir = store_root / revision_id
    if (final_dir / "manifest.json").is_file():
        return

    store_root.mkdir(parents=True, exist_ok=True)
    temp_dir = store_root / f".tmp-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)
    try:
        files_dir = temp_dir / "files"
        files_dir.mkdir()
        for entry in walk.entries:
            # entry.relative_path always originates from walk_agent_files's
            # own base-relative traversal, never external input -- still
            # verified contained, as insurance (Sec 3's "defense in depth"
            # of docs/specs/agent_revision.md), via the same primitive
            # every other artifact-path containment check in this codebase
            # uses.
            dest = contained_path(files_dir, entry.relative_path)
            if dest is None:  # pragma: no cover - defensive; walk never produces this
                raise RevisionRestoreError(
                    f"Refusing to archive a path outside its own snapshot: {entry.relative_path!r}"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(entry.content)

        manifest: dict[str, Any] = {
            "schema": _MANIFEST_SCHEMA,
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "agent_revision_id": revision_id,
            "fingerprint_version": AGENT_REVISION_FINGERPRINT_VERSION,
            "archived_at": _utc_now_iso(),
            "source_agent_id": source_agent_id,
            "complete": walk.complete,
            "omitted": [o.to_dict() for o in walk.omitted],
            "files": [e.relative_path for e in walk.entries],
        }
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        # Never promote a snapshot that doesn't actually reconstruct the
        # revision it's about to be filed under -- a case-insensitive store
        # filesystem silently collapsing two distinct case-differing
        # relative paths onto one physical file (e.g. source ``A.txt`` and
        # ``a.txt``), or any other write that landed different bytes than
        # ``walk`` produced, must never result in ``archived=True``. Checked
        # against the temp directory itself, before ``os.replace`` makes it
        # visible under its canonical path, so a failed check leaves nothing
        # for a concurrent reader to observe as "this revision exists."
        if not _verify_snapshot_dir(temp_dir, revision_id):
            raise OSError(
                f"Refusing to archive {revision_id}: the written snapshot does not "
                "reconstruct the intended revision (e.g. a case-insensitive-store "
                "filename collision, or a file dropped/overwritten during write)."
            )

        try:
            os.replace(temp_dir, final_dir)
        except OSError:
            # A concurrent writer may have won the same content-addressed
            # path first; since the ID is a content address, that directory
            # already holds identical bytes, so this is success, not a
            # conflict.
            if (final_dir / "manifest.json").is_file():
                shutil.rmtree(temp_dir, ignore_errors=True)
                return
            raise
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _verify_snapshot_dir(snapshot_dir: Path, revision_id: str) -> bool:
    """Recompute a snapshot directory's fingerprint from its own written
    bytes and compare it against ``revision_id``.

    Shared by ``verify_revision`` (checking an already-promoted
    ``store_root/revision_id/``) and ``_write_snapshot`` (checking a
    ``.tmp-*`` directory *before* it is promoted) -- the same check, run at
    two different points in a snapshot's lifecycle, is what lets
    ``_write_snapshot`` refuse to ever promote (and therefore
    ``archive_agent_revision``/``archive_agent_revision_from_walk`` refuse
    to ever report ``archived=True`` for) a directory that doesn't actually
    reconstruct the revision it's filed under.

    Re-reads ``manifest.json`` from disk (rather than trusting an in-memory
    dict a caller already has) so this checks exactly what was durably
    written, including the JSON round-trip itself -- and reconstructs the
    exact walk-result shape the original fingerprint was computed over:
    file entries freshly read from the snapshot's own ``files/`` copy,
    combined with the omission list recorded in ``manifest.json`` (which
    cannot be re-derived from the store alone, since omitted content was
    never copied there by design).
    """

    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(manifest, dict):
        return False

    files_dir = snapshot_dir / "files"
    if not files_dir.is_dir():
        return False

    stored_walk = walk_agent_files(files_dir)
    if not stored_walk.complete:
        # The store's own copy should never itself contain a symlink or an
        # unreadable file -- archival never writes one. If it does now,
        # the store has been tampered with or corrupted after the fact.
        return False

    raw_omitted = manifest.get("omitted", ())
    if not isinstance(raw_omitted, list):
        return False
    try:
        omitted = tuple(
            OmittedAgentPath(item["relative_path"], item["reason"], item.get("target"))
            for item in raw_omitted
        )
    except (KeyError, TypeError):
        return False

    fingerprint_version = manifest.get("fingerprint_version", AGENT_REVISION_FINGERPRINT_VERSION)
    if not isinstance(fingerprint_version, int):
        return False

    reconstructed = AgentFileWalkResult(stored_walk.entries, omitted)

    # MINOR (Ultra review): ``complete`` must be derived from ``omitted``
    # and cross-checked against the manifest's persisted ``complete``
    # field, never trusted from either source alone -- a hand-edited or
    # corrupted manifest whose ``complete`` boolean disagrees with its own
    # ``omitted`` list is inconsistent store state, and previously nothing
    # here ever read ``complete`` at all, so tampering with it had no
    # effect on the verification outcome in either direction.
    recorded_complete = manifest.get("complete")
    if not isinstance(recorded_complete, bool) or recorded_complete != reconstructed.complete:
        return False

    # BLOCKER (v0.8 audit): the manifest's own ``files`` list -- the value
    # ``restore_revision`` actually trusts to decide what to copy -- was
    # never previously cross-checked against anything. The fingerprint
    # above is computed purely from ``files/``'s own directory contents, so
    # a manifest hand-edited to declare a *different* (e.g. truncated, even
    # emptied) ``files`` list than what ``files/`` actually contains still
    # recomputed the correct fingerprint and reported ``verified: True`` --
    # while ``restore_revision`` would then silently restore only the
    # manifest's (tampered, narrower) list, an undetected partial restore
    # presented as a verified success. Cross-checking here, once, closes
    # this for every caller of ``verify_revision``/``show``/``restore``
    # alike, rather than duplicating the check only inside restore.
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not all(isinstance(f, str) for f in raw_files):
        return False
    if sorted(raw_files) != sorted(entry.relative_path for entry in stored_walk.entries):
        return False

    recomputed = _hash_walk_result(fingerprint_version, reconstructed)
    return agent_revision_id(recomputed) == revision_id


def read_manifest(store_root: Path, revision_id: str) -> dict[str, Any] | None:
    if not _is_valid_revision_id(revision_id):
        return None
    manifest_path = store_root / revision_id / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def list_revisions(store_root: Path) -> tuple[str, ...]:
    if not store_root.is_dir():
        return ()
    names = []
    for child in store_root.iterdir():
        if not child.is_dir() or child.name.startswith(".tmp-"):
            continue
        if (child / "manifest.json").is_file():
            names.append(child.name)
    return tuple(sorted(names))


def verify_revision(store_root: Path, revision_id: str) -> bool:
    """Recompute a stored revision's fingerprint and compare it to its own name.

    Thin wrapper over ``_verify_snapshot_dir`` (the same check
    ``_write_snapshot`` already ran, at write time, before ever promoting
    this directory to its canonical path) -- see that function for what is
    actually reconstructed and compared. ``revision_id`` is validated
    against the exact content-address shape before being joined onto
    ``store_root`` (see ``_is_valid_revision_id``) -- a caller-supplied
    value that doesn't match (e.g. sourced from untrusted persisted
    ``agent_revisions`` data) is reported as simply not verified, never
    joined onto the store path at all.
    """

    if not _is_valid_revision_id(revision_id):
        return False
    return _verify_snapshot_dir(store_root / revision_id, revision_id)


def restore_revision(
    store_root: Path, revision_id: str, target_dir: Path, *, force: bool = False
) -> None:
    """Write a stored revision's files into ``target_dir``.

    Never writes to a non-empty ``target_dir`` without ``force=True``, and
    never targets a live ``agents/<id>/`` catalog directory implicitly --
    the caller chooses ``target_dir`` explicitly. Every write is resolved
    through ``battle_engine.paths.contained_path`` (both against the
    store's own ``files/`` directory and against ``target_dir``), so a
    hand-edited or corrupted ``manifest.json`` cannot escape either side.
    """

    manifest = read_manifest(store_root, revision_id)
    if manifest is None:
        raise RevisionNotFoundError(f"No archived revision found for {revision_id!r}.")

    # Fail closed *before* writing anything to a trusted restore target: a
    # snapshot that doesn't reconstruct/verify against its own directory
    # name (corrupted after promotion, hand-tampered, or a malformed
    # manifest) must never be silently restored as if it were the genuine
    # revision -- the same check `verify_revision`/`show` perform, run here
    # ahead of any file write rather than only offered as a separate,
    # skippable step.
    if not _verify_snapshot_dir(store_root / revision_id, revision_id):
        raise RevisionRestoreError(
            f"Refusing to restore {revision_id!r}: the stored snapshot does not verify "
            "against its own revision id (corrupted, tampered, or malformed). No files "
            "were written to the restore target."
        )

    files_dir = store_root / revision_id / "files"
    if target_dir.exists() and target_dir.is_dir() and any(target_dir.iterdir()) and not force:
        raise RevisionRestoreError(f"Target directory is not empty: {target_dir}")
    if target_dir.exists() and not target_dir.is_dir():
        raise RevisionRestoreError(f"Target path is not a directory: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)
    raw_files = manifest.get("files", ())
    if not isinstance(raw_files, list):
        raise RevisionRestoreError(f"Revision manifest for {revision_id!r} is malformed.")

    # Pass 1: resolve and validate every (source, dest) pair -- including
    # every containment check, on both the store side and the target side
    # -- before writing anything at all. Previously this was interleaved
    # with the write loop below, so a containment failure discovered on,
    # say, the third manifest entry would still have already written the
    # first two -- a partial write masquerading as a clean failure.
    pairs: list[tuple[Path, Path]] = []
    for relative_path in raw_files:
        if not isinstance(relative_path, str):
            raise RevisionRestoreError(f"Revision manifest for {revision_id!r} is malformed.")
        source = contained_path(files_dir, relative_path)
        if source is None or not source.is_file():
            raise RevisionRestoreError(
                f"Revision manifest for {revision_id!r} references a path outside "
                f"its own store or that no longer exists: {relative_path!r}"
            )
        dest = contained_path(target_dir, relative_path)
        if dest is None:
            raise RevisionRestoreError(
                f"Revision manifest for {revision_id!r} references a path that "
                f"would escape the restore target: {relative_path!r}"
            )
        pairs.append((source, dest))

    # Pass 2: write. An ordinary I/O failure partway through (disk full, a
    # locked file, a permissions error) must not surface as an uncaught
    # exception that leaves a silent, unflagged partial tree in
    # `target_dir` looking like nothing ran -- best-effort remove exactly
    # the files *this call* wrote (never anything that was already present
    # in `target_dir`, e.g. from an earlier `--force` restore) and raise a
    # typed, explicit error instead.
    written: list[Path] = []
    try:
        for source, dest in pairs:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            written.append(dest)
    except OSError as exc:
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RevisionRestoreError(
            f"Restoring {revision_id!r} to {target_dir} failed partway through ({exc}); "
            f"{len(written)} of {len(pairs)} file(s) were removed again on a best-effort "
            "basis. This is not a successful restore."
        ) from exc
