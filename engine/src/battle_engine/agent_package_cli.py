"""``bytefray agents export|import|package show`` (docs/specs/agent_package.md Sec 11).

Thin argparse wrapper over :mod:`battle_engine.agent_package` -- mirrors
:mod:`battle_engine.agent_revisions_cli`'s split between domain logic and
CLI presentation. No package validation/parsing logic lives here; this
module only builds argument namespaces, calls the domain functions, and
formats their results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from battle_engine.agent_package import (
    AgentPackageError,
    ExportResult,
    ImportResult,
    PackageInspection,
    export_agent,
    import_package,
    inspect_package,
)
from battle_engine.paths import get_data_root

__all__ = ["export_main", "import_main", "package_main"]


def _export_result_dict(result: ExportResult) -> dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "agent_revision_id": result.agent_revision_id,
        "complete": result.complete,
        "omitted_count": result.omitted_count,
        "file_count": result.file_count,
        "package_path": str(result.package_path),
        "package_sha256": result.package_sha256,
        "local_archive_error": result.local_archive_error,
    }


def _cmd_export(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser() if args.output else None
    try:
        result = export_agent(
            args.agent_id,
            data_root=get_data_root(),
            output=output,
            revision_id=args.revision,
        )
    except AgentPackageError as exc:
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_export_result_dict(result), indent=2, sort_keys=True))
        return 0

    print(f"Exported agent: {result.agent_id}")
    print(f"Revision: {result.agent_revision_id}")
    if not result.complete:
        print(f"WARNING: revision is INCOMPLETE ({result.omitted_count} omission(s)) -- see 'agents revisions show'.")
    print(f"Files: {result.file_count}")
    print(f"Package: {result.package_path}")
    print(f"SHA-256: {result.package_sha256}")
    if result.local_archive_error:
        print(f"NOTE: local revision-store archival did not succeed ({result.local_archive_error}); the package itself is unaffected.")
    return 0


def _inspection_dict(inspection: PackageInspection) -> dict[str, Any]:
    return {
        "package_path": str(inspection.package_path),
        "valid": inspection.valid,
        "error": inspection.error,
        "schema_version": inspection.schema_version,
        "agent_id": inspection.agent_id,
        "display_name": inspection.display_name,
        "kind": inspection.kind,
        "agent_version": inspection.agent_version,
        "entry_point": inspection.entry_point,
        "agent_api_version": inspection.agent_api_version,
        "agent_revision_id": inspection.agent_revision_id,
        "revision_complete": inspection.revision_complete,
        "revision_omitted_count": inspection.revision_omitted_count,
        "file_count": inspection.file_count,
        "exported_at": inspection.exported_at,
        "bytefray_version": inspection.bytefray_version,
        "integrity_verified": inspection.integrity_verified,
        "compatible": inspection.compatible,
        "compatibility_notes": list(inspection.compatibility_notes),
    }


def _print_inspection(inspection: PackageInspection) -> None:
    if not inspection.valid:
        print(f"package: {inspection.package_path}")
        print(f"valid: False ({inspection.error})")
        return
    print(f"package: {inspection.package_path}")
    print("valid: True")
    print(f"agent_id: {inspection.agent_id}")
    print(f"display_name: {inspection.display_name}")
    print(f"kind: {inspection.kind}")
    print(f"agent_version: {inspection.agent_version}")
    print(f"entry_point: {inspection.entry_point}")
    print(f"agent_api_version: {inspection.agent_api_version}")
    print(f"revision: {inspection.agent_revision_id}")
    completeness = "complete" if inspection.revision_complete else f"INCOMPLETE ({inspection.revision_omitted_count} omission(s))"
    print(f"revision completeness: {completeness}")
    print(f"file_count: {inspection.file_count}")
    print(f"exported_at: {inspection.exported_at}")
    print(f"bytefray_version (informational breadcrumb, not enforced): {inspection.bytefray_version}")
    print(f"integrity verified (recomputed live from packaged bytes): {inspection.integrity_verified}")
    print(f"importable on this installation: {inspection.compatible}")
    for note in inspection.compatibility_notes:
        print(f"  - {note}")
    print(
        "NOTE: this reports package structure/integrity/provenance only. It is not a "
        "safety or trust statement about the contained agent's code -- Python agents "
        "are executable code."
    )


def _cmd_package_show(args: argparse.Namespace) -> int:
    inspection = inspect_package(Path(args.package_file).expanduser())
    if args.json:
        print(json.dumps(_inspection_dict(inspection), indent=2, sort_keys=True))
    else:
        _print_inspection(inspection)
    if not inspection.valid:
        return 2
    return 0 if inspection.compatible else 1


def _import_result_dict(result: ImportResult) -> dict[str, Any]:
    return {
        "agent_id": result.agent_id,
        "agent_revision_id": result.agent_revision_id,
        "target_dir": str(result.target_dir),
        "already_present": result.already_present,
        "local_archive_error": result.local_archive_error,
    }


def _cmd_import(args: argparse.Namespace) -> int:
    try:
        result = import_package(
            Path(args.package_file).expanduser(),
            data_root=get_data_root(),
            as_agent_id=args.as_,
        )
    except AgentPackageError as exc:
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_import_result_dict(result), indent=2, sort_keys=True))
        return 0

    if result.already_present:
        print(f"Agent {result.agent_id!r} already present with this exact revision ({result.agent_revision_id}); nothing imported.")
        return 0

    print(f"Imported {result.agent_id} -> {result.target_dir}")
    print(f"Revision: {result.agent_revision_id}")
    print(
        "This is executable Python/blob agent code. Bytefray verified the package's "
        "structure, integrity, and provenance -- it did not, and cannot, verify that "
        "the agent's own logic is safe or trustworthy."
    )
    if result.local_archive_error:
        print(f"NOTE: local revision-store archival did not succeed ({result.local_archive_error}); the imported agent itself is unaffected.")
    print(f"Run 'bytefray agents validate {result.agent_id}' to try it.")
    return 0


def export_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bytefray agents export")
    parser.add_argument("agent_id")
    parser.add_argument("--output", default=None, help="output file or directory (default: current directory)")
    parser.add_argument("--revision", default=None, help="export an already-archived historical revision instead of current source")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return _cmd_export(args)


def import_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bytefray agents import")
    parser.add_argument("package_file")
    parser.add_argument("--as", dest="as_", default=None, help="import under an explicit agent id instead of the package's declared one")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return _cmd_import(args)


def package_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bytefray agents package")
    sub = parser.add_subparsers(dest="verb", required=True)
    show_parser = sub.add_parser("show", help="report a package's structure, provenance, integrity, and compatibility")
    show_parser.add_argument("package_file")
    show_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.verb == "show":
        return _cmd_package_show(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(export_main())
