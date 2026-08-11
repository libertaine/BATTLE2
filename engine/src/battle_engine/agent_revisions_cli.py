"""``bytefray agents revisions list|show|restore`` (docs/specs/agent_revision.md Sec 7).

The smallest coherent CLI over the content-addressed revision store in
``agent_revisions.py``: discover what's preserved for an agent, inspect one
revision's provenance, and restore it to an explicit target. Deliberately
does not add a revision-aware execution path -- ``restore`` writes plain
files to a directory and the existing ``agents test``/``agents evaluate``
commands operate on that directory like any other agent folder (Sec 7).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from battle_engine.agent_revisions import (
    RevisionNotFoundError,
    RevisionRestoreError,
    agent_revision_fingerprint,
    agent_revision_id,
    agent_revisions_root,
    list_revisions,
    read_manifest,
    restore_revision,
    verify_revision,
)
from battle_engine.paths import get_data_root

DEFAULT_RESTORE_SUBDIR = "agent_revisions_restored"


def _manifest_fields_well_formed(manifest: dict[str, Any]) -> bool:
    """Structural type-check for the manifest fields this CLI reads directly.

    ``read_manifest`` only guarantees the top-level parsed JSON is a dict
    -- it does not validate any individual field's type (deep structural
    validation, including cross-checking against the store's own
    ``files/`` directory, is ``_verify_snapshot_dir``'s job, reserved for
    the live verification step). A manifest that is syntactically valid
    JSON but has, say, ``"files": 5`` instead of a list must be treated
    the same as an unreadable manifest here -- never trusted enough to
    call ``len()``/iterate/slice on directly, which would otherwise crash
    this CLI outright and, for ``list``, take every *other*, healthy
    sibling revision down with it (v0.8 audit finding).
    """

    files = manifest.get("files")
    if files is not None and not isinstance(files, list):
        return False
    omitted = manifest.get("omitted")
    return omitted is None or (
        isinstance(omitted, list) and all(isinstance(item, dict) for item in omitted)
    )


def _safe_omitted_count(manifest: dict[str, Any]) -> int:
    omitted = manifest.get("omitted")
    return len(omitted) if isinstance(omitted, list) else 0


def _live_agent_revision_id(data_root: Path, agent_id: str) -> str | None:
    """The revision id the *current* on-disk agent directory would archive to.

    Live state only, never trusted as a historical fact (Sec 6) -- used
    purely to widen ``list``'s relevance filter beyond the store's
    recorded, non-authoritative ``source_agent_id`` (Sec 3: content-
    addressed dedup means a revision's first-writer breadcrumb can name a
    different catalog entry than every agent whose current content
    actually matches it). Returns ``None`` when the agent directory does
    not currently exist -- an agent deleted or renamed after archival must
    not make ``list`` crash or silently omit its still-preserved revisions.
    """

    agent_dir = data_root / "agents" / agent_id
    if not agent_dir.is_dir():
        return None
    fingerprint = agent_revision_fingerprint(agent_dir)
    return agent_revision_id(fingerprint) if fingerprint is not None else None


def _cmd_list(args: argparse.Namespace) -> int:
    data_root = get_data_root()
    store_root = agent_revisions_root(data_root)
    live_revision_id = _live_agent_revision_id(data_root, args.agent_id)

    rows: list[dict[str, Any]] = []
    unreadable = 0
    for revision_id in list_revisions(store_root):
        manifest = read_manifest(store_root, revision_id)
        if manifest is None or not _manifest_fields_well_formed(manifest):
            # A malformed sibling (unreadable/non-dict manifest.json, or
            # one whose fields are the wrong JSON type) must never prevent
            # listing the healthy revisions around it -- it simply cannot
            # be attributed to any agent, so it is silently excluded from
            # this agent-scoped listing (counted, not shown).
            unreadable += 1
            continue
        source_agent_id = manifest.get("source_agent_id")
        matches_source = source_agent_id == args.agent_id
        matches_live = live_revision_id is not None and revision_id == live_revision_id
        if not (matches_source or matches_live):
            continue
        rows.append(
            {
                "revision_id": revision_id,
                "source_agent_id": source_agent_id,
                "matches_current_live_source": matches_live,
                "complete": bool(manifest.get("complete")),
                "omitted_count": len(manifest.get("omitted") or []),
                "archived_at": manifest.get("archived_at"),
                "file_count": len(manifest.get("files") or []),
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "agent_id": args.agent_id,
                    "revisions": rows,
                    "unreadable_sibling_count": unreadable,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not rows:
        print(f"No preserved revisions found for agent {args.agent_id!r}.")
    for row in rows:
        breadcrumb = (
            "originally archived from this agent"
            if row["source_agent_id"] == args.agent_id
            else f"source_agent_id={row['source_agent_id']!r} (informational only)"
        )
        live_marker = "  [matches current live source]" if row["matches_current_live_source"] else ""
        completeness = "complete" if row["complete"] else f"INCOMPLETE ({row['omitted_count']} omission(s))"
        print(
            f"{row['revision_id']}  {completeness}  files={row['file_count']}  "
            f"archived_at={row['archived_at']}  {breadcrumb}{live_marker}"
        )
    if unreadable:
        print(f"({unreadable} unreadable/malformed sibling revision(s) in the store, ignored)")
    return 0


def _print_show(revision_id: str, manifest: dict[str, Any], *, verified: bool) -> None:
    print(f"revision_id: {revision_id}")
    print(f"fingerprint_version: {manifest.get('fingerprint_version')}")
    print(f"archived_at: {manifest.get('archived_at')}")
    print(
        "source_agent_id (informational breadcrumb only, not authoritative): "
        f"{manifest.get('source_agent_id')}"
    )
    complete = bool(manifest.get("complete"))
    print(f"complete: {complete}")
    files = manifest.get("files") or []
    print(f"included files: {len(files)}")
    for path in files[:20]:
        print(f"  + {path}")
    if len(files) > 20:
        print(f"  ... and {len(files) - 20} more")
    omitted = manifest.get("omitted") or []
    if omitted:
        print(f"omitted ({len(omitted)}) -- NOT preserved, evidence only:")
        for item in omitted:
            target = item.get("target")
            suffix = f" -> {target}" if target else ""
            print(f"  - {item.get('relative_path')}: {item.get('reason')}{suffix}")
    else:
        print("omitted: none")
    print(f"local snapshot verified (recomputed live from stored bytes): {verified}")
    if complete:
        print("reproducibility: revision-preserved candidate (complete=True; see docs/specs/agent_revision.md Sec 8)")
    else:
        print(
            "reproducibility: NOT revision-preserved -- this revision has omissions; "
            "restoring it reproduces less than the original tree (Sec 8)"
        )


def _cmd_show(args: argparse.Namespace) -> int:
    data_root = get_data_root()
    store_root = agent_revisions_root(data_root)
    manifest = read_manifest(store_root, args.revision_id)
    if manifest is None or not _manifest_fields_well_formed(manifest):
        print(
            f"ERROR: no readable revision found for {args.revision_id!r} under {store_root} "
            "(missing directory, missing manifest.json, malformed JSON, or a manifest field "
            "of the wrong type).",
            file=sys.stderr,
        )
        return 2

    verified = verify_revision(store_root, args.revision_id)
    if args.json:
        data = dict(manifest)
        data["verified"] = verified
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        _print_show(args.revision_id, manifest, verified=verified)
    return 0 if verified else 1


def _cmd_restore(args: argparse.Namespace) -> int:
    data_root = get_data_root()
    store_root = agent_revisions_root(data_root)

    # An explicitly-empty `--to ""` is a caller/scripting mistake (e.g. an
    # unset shell variable interpolated in), not "use the default" -- `""`
    # is not None, so falling through to Path("").resolve() would silently
    # restore into the current working directory instead. Reject it
    # outright rather than guessing what was meant.
    if args.to is not None and not args.to.strip():
        print("ERROR: --to must not be empty.", file=sys.stderr)
        return 2

    target_dir = (
        Path(args.to).expanduser().resolve()
        if args.to is not None
        else (data_root / DEFAULT_RESTORE_SUBDIR / args.revision_id)
    )

    manifest = read_manifest(store_root, args.revision_id)
    try:
        restore_revision(store_root, args.revision_id, target_dir, force=args.force)
    except RevisionNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except RevisionRestoreError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    complete = bool(manifest.get("complete")) if manifest else False
    print(f"Restored {args.revision_id} -> {target_dir}")
    if not complete:
        omitted_count = _safe_omitted_count(manifest) if manifest else 0
        print(
            f"WARNING: this revision is INCOMPLETE ({omitted_count} omission(s) recorded) -- "
            "the restored directory reproduces only the captured bytes, not the full "
            "original tree. Run 'bytefray agents revisions show "
            f"{args.revision_id}' to see what was omitted."
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bytefray agents revisions")
    sub = parser.add_subparsers(dest="verb", required=True)

    list_parser = sub.add_parser("list", help="list preserved revisions relevant to one agent")
    list_parser.add_argument("agent_id")
    list_parser.add_argument("--json", action="store_true")

    show_parser = sub.add_parser("show", help="show one revision's provenance and verify it locally")
    show_parser.add_argument("revision_id")
    show_parser.add_argument("--json", action="store_true")

    restore_parser = sub.add_parser("restore", help="restore a revision's preserved files to a directory")
    restore_parser.add_argument("revision_id")
    restore_parser.add_argument("--to", default=None, help="restore target directory (default: under the data root)")
    restore_parser.add_argument(
        "--force", action="store_true", help="allow restoring into a non-empty target directory"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verb == "list":
        return _cmd_list(args)
    if args.verb == "show":
        return _cmd_show(args)
    if args.verb == "restore":
        return _cmd_restore(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
