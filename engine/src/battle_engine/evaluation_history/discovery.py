"""Artifact discovery: default/explicit roots, one bad sibling never aborts (Sec 13)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from battle_engine.agent_evaluation import SCHEMA_NAME as V2_SCHEMA_NAME
from battle_engine.paths import get_data_root

from .models import (
    ArtifactLocation,
    ArtifactReadError,
    EvaluationSummary,
    HealthCode,
    HealthReport,
    file_modified_at,
)
from .v1_adapter import V1_SCHEMA_NAME, adapt_v1_data
from .v2_adapter import SUPPORTED_V2_VERSIONS, adapt_v2_data


class AmbiguousSelectorError(ValueError):
    """An evaluation-id selector matched more than one on-disk location (Sec 15)."""


@dataclass(frozen=True)
class DiscoveredEvaluation:
    location: ArtifactLocation
    evaluation_id: str | None
    summary: EvaluationSummary | None
    health: HealthReport

    def to_json(self) -> dict:
        return {
            "location": self.location.to_json(),
            "evaluation_id": self.evaluation_id,
            "summary": self.summary.to_json() if self.summary is not None else None,
            "health": self.health.to_json(),
        }


@dataclass(frozen=True)
class ArtifactListing:
    entries: tuple[DiscoveredEvaluation, ...]
    duplicate_identity_groups: tuple[tuple[str, tuple[Path, ...]], ...]


def default_roots() -> tuple[Path, ...]:
    return (get_data_root() / "runs" / "evaluations",)


def adapt_any(path: Path) -> EvaluationSummary:
    """Read a v1 or v2 ``evaluation.json`` by inspecting its schema fields.

    Both schemas currently share the same ``schema`` name
    (``bytefray.evaluation``); the version discriminates. Raises
    ``ArtifactReadError`` for anything that doesn't parse or validate --
    callers (here, ``discover``) are responsible for turning that into a
    safely reported entry rather than letting it propagate.

    Reads and JSON-parses the artifact exactly once -- the parsed object is
    dispatched straight to ``adapt_v1_data``/``adapt_v2_data`` rather than
    handing the version-specific adapter a bare path it would have to read
    and parse a second time.
    """

    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArtifactReadError(f"{path}: could not be read: {exc}", code=HealthCode.MALFORMED_JSON) from exc
    except ValueError as exc:
        raise ArtifactReadError(f"{path}: malformed JSON: {exc}", code=HealthCode.MALFORMED_JSON) from exc

    # H2: valid JSON whose root is not an object (a list, string, number,
    # etc.) parses without error but has no `.get()` to inspect a schema
    # field on -- must become a typed, isolated diagnostic here, never an
    # uncaught AttributeError that would abort sibling discovery.
    if not isinstance(raw, dict):
        raise ArtifactReadError(
            f"{path}: JSON root is a {type(raw).__name__}, not an object",
            code=HealthCode.INVALID_JSON_ROOT,
        )

    if raw.get("schema") not in (V1_SCHEMA_NAME, V2_SCHEMA_NAME):
        raise ArtifactReadError(
            f"{path}: schema {raw.get('schema')!r} is not a bytefray.evaluation artifact",
            code=HealthCode.WRONG_SCHEMA,
        )
    version = raw.get("schema_version")
    if version in SUPPORTED_V2_VERSIONS:
        return adapt_v2_data(raw, path)
    if version == 1:
        return adapt_v1_data(raw, path)
    raise ArtifactReadError(
        f"{path}: unsupported schema_version {version!r}", code=HealthCode.UNSUPPORTED_VERSION
    )


def _resolve_evaluation_json(candidate: Path) -> Path | None:
    candidate = Path(candidate)
    if candidate.is_file():
        return candidate
    if candidate.is_dir() and (candidate / "evaluation.json").is_file():
        return candidate / "evaluation.json"
    return None


def _one_level_scan(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir()):
        candidate = child / "evaluation.json"
        if candidate.is_file():
            found.append(candidate)
    return found


def discover(
    *, roots: Sequence[Path] = (), artifacts: Sequence[Path] = ()
) -> ArtifactListing:
    """Shallow-health discovery across default/explicit roots and explicit paths.

    Never recurses into arbitrary subdirectories beyond one level below a
    root, and never raises for a single malformed/unsupported sibling --
    every failure mode becomes a ``DiscoveredEvaluation`` with
    ``summary=None`` (Sec 13).
    """

    paths: list[Path] = []
    if not roots and not artifacts:
        roots = default_roots()
    for root in roots:
        paths.extend(_one_level_scan(Path(root)))
    for artifact in artifacts:
        resolved = _resolve_evaluation_json(Path(artifact))
        if resolved is not None:
            paths.append(resolved)
        else:
            paths.append(Path(artifact))  # reported as unreadable below

    # Stable de-duplication in case an explicit path also falls under a scanned root.
    seen_paths: set[Path] = set()
    ordered_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        ordered_paths.append(path)

    entries: list[DiscoveredEvaluation] = []
    by_evaluation_id: dict[str, list[Path]] = {}
    for path in ordered_paths:
        resolved_path = path.resolve() if path.exists() else Path(path).resolve()
        try:
            mtime = file_modified_at(resolved_path) if resolved_path.is_file() else ""
        except OSError:
            mtime = ""
        location = ArtifactLocation(
            evaluation_json_path=resolved_path, directory=resolved_path.parent, file_modified_at=mtime
        )
        try:
            summary = adapt_any(resolved_path)
        except ArtifactReadError as exc:
            entries.append(
                DiscoveredEvaluation(
                    location=location,
                    evaluation_id=None,
                    summary=None,
                    health=HealthReport(codes=(exc.code,), detail=(str(exc),), verified=False),
                )
            )
            continue
        entries.append(
            DiscoveredEvaluation(
                location=location,
                evaluation_id=summary.evaluation_id,
                summary=summary,
                health=summary.health,
            )
        )
        by_evaluation_id.setdefault(summary.evaluation_id, []).append(resolved_path)

    duplicate_groups = tuple(
        (evaluation_id, tuple(paths_))
        for evaluation_id, paths_ in sorted(by_evaluation_id.items())
        if len(paths_) > 1
    )
    if duplicate_groups:
        flagged_ids = {evaluation_id for evaluation_id, _ in duplicate_groups}
        entries = [
            (
                DiscoveredEvaluation(
                    location=entry.location,
                    evaluation_id=entry.evaluation_id,
                    summary=entry.summary,
                    health=HealthReport(
                        codes=entry.health.codes + (HealthCode.DUPLICATE_IDENTITY_LOCATION,),
                        detail=entry.health.detail + ("evaluation_id also found at another location",),
                        verified=entry.health.verified,
                    ),
                )
                if entry.evaluation_id in flagged_ids
                else entry
            )
            for entry in entries
        ]

    return ArtifactListing(entries=tuple(entries), duplicate_identity_groups=duplicate_groups)


def resolve_selector(selector: str, *, roots: Sequence[Path] = ()) -> Path:
    """Resolve a CLI selector to one ``evaluation.json`` path (Sec 15).

    Accepts an existing file/directory path directly; otherwise looks it up
    as an ``evaluation_id`` against discovered roots, raising
    ``AmbiguousSelectorError`` when more than one location matches and
    ``FileNotFoundError`` when none do.
    """

    direct = _resolve_evaluation_json(Path(selector))
    if direct is not None:
        return direct.resolve()

    listing = discover(roots=roots)
    matches = [
        entry.location.evaluation_json_path
        for entry in listing.entries
        if entry.evaluation_id == selector
    ]
    if not matches:
        raise FileNotFoundError(f"No evaluation found matching {selector!r}.")
    if len(matches) > 1:
        raise AmbiguousSelectorError(
            f"{selector!r} matches {len(matches)} locations; use a path-qualified selector: "
            + ", ".join(str(m) for m in matches)
        )
    return matches[0]


__all__ = [
    "AmbiguousSelectorError",
    "ArtifactListing",
    "DiscoveredEvaluation",
    "adapt_any",
    "default_roots",
    "discover",
    "resolve_selector",
]
