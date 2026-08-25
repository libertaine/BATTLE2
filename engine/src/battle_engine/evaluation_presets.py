"""``bytefray agents evaluation-presets list|show|validate`` (v1.6 Phase 3).

A preset is a small, versioned, hand-editable YAML artifact
(``bytefray.evaluation_preset`` v1) that supplies default values for a
``bytefray agents evaluate`` invocation. The governing architectural
principle (see ``docs/V1_6_PHASE3_EVALUATION_PRESETS.md``):

    named reusable definition -> fully resolved explicit EvaluationRequest
    -> ordinary EvaluationRequest -> canonical evaluation execution

A preset is purely an input-construction convenience. It is never a second
evaluation engine, never a methodology identity, and never enters
``evaluation_id``'s hash payload -- once resolved into a concrete
``EvaluationRequest`` (``agent_evaluation.main``'s job, the one
authoritative resolution path), an evaluation started from a preset is
indistinguishable from one typed out explicitly at the CLI.

This module is deliberately one-way: it depends only on ``battle_engine.
paths``/``battle_engine.result_model`` (path-safety and content-fingerprint
primitives already established for agents/results), never on
``battle_engine.agent_evaluation`` -- ``agent_evaluation`` imports *this*
module for ``--preset`` support, so the reverse import would be circular.
The two ``ORIENTATION_*`` constants below are therefore plain string
literals pinned equal to ``agent_evaluation``'s own
``ORIENTATION_MODE_BOTH``/``ORIENTATION_MODE_CANDIDATE_FIRST_ONLY`` by a
cross-module test, not imported.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from battle_engine.paths import contained_path, get_data_root
from battle_engine.result_model import stable_id

SCHEMA_NAME = "bytefray.evaluation_preset"
SCHEMA_VERSION = 1

# Mirrors battle_engine.agent_evaluation.ORIENTATION_MODE_BOTH /
# ORIENTATION_MODE_CANDIDATE_FIRST_ONLY exactly -- see module docstring for
# why these are duplicated literals rather than an import.
ORIENTATION_BOTH = "both"
ORIENTATION_CANDIDATE_FIRST_ONLY = "candidate_first_only"
_VALID_ORIENTATIONS = (ORIENTATION_BOTH, ORIENTATION_CANDIDATE_FIRST_ONLY)

_PRESET_EXTENSIONS = (".yaml", ".yml")

_ALLOWED_FIELDS = {
    "schema",
    "schema_version",
    "description",
    "candidate",
    "baseline",
    "opponents",
    "seeds",
    "seed_range",
    "ticks",
    "orientation",
    "ruleset",
    # v3 Phase 0 (docs/V3_PHASE0_RESEARCH_BASELINE.md): the two controlled
    # experimental variables, settable by a preset exactly like `ticks`.
    # A preset is the natural home for a research condition -- it is how
    # the Phase-0 baseline corpus pins its own conditions reproducibly.
    "arena_size",
    "instr_per_tick",
}
_REQUIRED_FIELDS = {"schema", "schema_version"}

# v2.0.0-beta2 Phase 1: mirrors battle_engine.agent_evaluation's own
# --ruleset choices exactly (see that module's docstring for why these are
# duplicated literals rather than an import -- this module must stay
# import-independent of agent_evaluation).
_VALID_RULESETS = ("bytefray-rules-1", "bytefray-rules-2")

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class EvaluationPresetError(ValueError):
    """An invalid preset selector, malformed preset file, or unsupported schema."""

    code = "evaluation_preset_invalid"


@dataclass(frozen=True)
class EvaluationPreset:
    """A loaded, validated preset -- a *partial* set of evaluation inputs.

    Every field is optional (``None`` when the preset does not specify it)
    except ``name``/``path``/``content_digest``/``raw``. Resolution against
    ordinary defaults and explicit CLI overrides happens in
    ``agent_evaluation.main``, not here (Sec 6 of the governing spec: one
    authoritative resolution path, not a second one duplicated in this
    module).
    """

    name: str
    path: Path
    description: str | None
    candidate_id: str | None
    baseline_id: str | None
    opponent_ids: tuple[str, ...] | None
    seeds: tuple[int, ...] | None
    seed_range: tuple[int, int] | None
    ticks: int | None
    # v3 Phase 0: `None` means "not set by this preset", falling back to the
    # ordinary default unless overridden by an explicit CLI flag -- the
    # identical contract as every field above.
    arena_size: int | None
    instr_per_tick: int | None
    orientation: str | None
    # v2.0.0-beta2 Phase 1: the same optional Ruleset selector `agents
    # evaluate --ruleset` accepts, resolved the identical way -- `None`
    # (not set by this preset) falls back to the ordinary default (v1,
    # unchanged) unless overridden by an explicit CLI --ruleset.
    ruleset_id: str | None
    content_digest: str
    raw: dict[str, Any]


def presets_root(root: Path) -> Path:
    return (root / "evaluation_presets").resolve()


def _validate_name(name: str) -> str:
    if not name or not name.strip():
        raise EvaluationPresetError("Preset name cannot be empty.")
    if "/" in name or "\\" in name:
        raise EvaluationPresetError(f"Preset name {name!r} must not contain a path separator.")
    if not _NAME_PATTERN.match(name):
        raise EvaluationPresetError(
            f"Preset name {name!r} must start with a letter or digit and contain only "
            "letters, digits, '_', '-', or '.'."
        )
    return name


def resolve_preset_path(root: Path, name: str) -> Path:
    """Resolve ``name`` to exactly one ``evaluation_presets/<name>.y[a]ml`` file.

    Reuses :func:`battle_engine.paths.contained_path` for the same
    containment guarantee ``agents.resolve_agent`` already relies on -- no
    ``..`` traversal, no absolute-path/drive injection, no symlink escape
    out of the presets root.
    """

    _validate_name(name)
    base = presets_root(root)
    candidates = []
    for ext in _PRESET_EXTENSIONS:
        candidate = contained_path(base, f"{name}{ext}")
        if candidate is not None and candidate.is_file():
            candidates.append(candidate)
    if not candidates:
        raise EvaluationPresetError(
            f"Unknown evaluation preset {name!r}. Expected {base / (name + '.yaml')}."
        )
    if len(candidates) > 1:
        raise EvaluationPresetError(
            f"Ambiguous evaluation preset {name!r}: more than one file matches "
            f"({', '.join(str(c) for c in candidates)}). Keep only one."
        )
    return candidates[0]


def list_presets(root: Path) -> tuple[str, ...]:
    """Return every discoverable preset name, sorted, deduplicated across extensions."""

    base = presets_root(root)
    if not base.is_dir():
        return ()
    names: set[str] = set()
    for child in base.iterdir():
        if child.is_file() and child.suffix in _PRESET_EXTENSIONS:
            names.add(child.stem)
    return tuple(sorted(names))


def _require_type(value: Any, expected: type, field: str, path: Path) -> None:
    if expected is int and isinstance(value, bool):
        raise EvaluationPresetError(f"{path}: {field!r} must be an integer.")
    if not isinstance(value, expected):
        raise EvaluationPresetError(f"{path}: {field!r} must be a {expected.__name__}.")


def _require_str_list(value: Any, field: str, path: Path) -> tuple[str, ...]:
    # Deliberately allows an empty list here -- this is a *type* check only.
    # Whether an empty opponents/seeds list makes for a runnable evaluation
    # is a business rule the reused EvaluationRequest validation path
    # (EvaluationService._validate) already enforces after resolution; this
    # module must not duplicate or pre-empt that rule (Sec 6 of the
    # governing spec: no separate validation path for preset-originated
    # requests).
    if not isinstance(value, list):
        raise EvaluationPresetError(f"{path}: {field!r} must be a list of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise EvaluationPresetError(f"{path}: {field!r} entries must be non-empty strings.")
        result.append(item)
    return tuple(result)


def _require_int_list(value: Any, field: str, path: Path) -> tuple[int, ...]:
    # See _require_str_list -- empty is a type-valid list here by design.
    if not isinstance(value, list):
        raise EvaluationPresetError(f"{path}: {field!r} must be a list of integers.")
    result: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise EvaluationPresetError(f"{path}: {field!r} entries must be integers.")
        result.append(item)
    return tuple(result)


def load_preset(root: Path, name: str) -> EvaluationPreset:
    """Resolve ``name`` under ``root``'s presets directory and load it."""

    path = resolve_preset_path(root, name)
    return load_preset_file(path, name=name)


def load_preset_file(path: Path, *, name: str | None = None) -> EvaluationPreset:
    """Load and strictly validate one preset file directly, independent of
    name-based lookup -- used by :func:`load_preset` and by ``validate``/
    ``show`` when a caller already has a resolved path.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvaluationPresetError(f"{path}: cannot be read ({exc}).") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EvaluationPresetError(f"{path}: malformed YAML ({exc}).") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise EvaluationPresetError(f"{path}: must contain a YAML mapping/object at the top level.")

    unknown = set(data) - _ALLOWED_FIELDS
    if unknown:
        raise EvaluationPresetError(
            f"{path}: unknown field(s) {sorted(unknown)!r}; allowed fields are "
            f"{sorted(_ALLOWED_FIELDS)!r}."
        )
    missing = _REQUIRED_FIELDS - set(data)
    if missing:
        raise EvaluationPresetError(f"{path}: missing required field(s) {sorted(missing)!r}.")

    if data.get("schema") != SCHEMA_NAME:
        raise EvaluationPresetError(
            f"{path}: 'schema' must be {SCHEMA_NAME!r}, got {data.get('schema')!r}."
        )
    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise EvaluationPresetError(
            f"{path}: unsupported schema_version {schema_version!r} (expected {SCHEMA_VERSION})."
        )

    description = data.get("description")
    if description is not None:
        _require_type(description, str, "description", path)

    candidate_id = data.get("candidate")
    if candidate_id is not None:
        _require_type(candidate_id, str, "candidate", path)
        if not candidate_id.strip():
            raise EvaluationPresetError(f"{path}: 'candidate' must not be empty.")

    baseline_id = data.get("baseline")
    if baseline_id is not None:
        _require_type(baseline_id, str, "baseline", path)
        if not baseline_id.strip():
            raise EvaluationPresetError(f"{path}: 'baseline' must not be empty.")

    opponent_ids = None
    if "opponents" in data:
        opponent_ids = _require_str_list(data["opponents"], "opponents", path)

    seeds = None
    if "seeds" in data:
        seeds = _require_int_list(data["seeds"], "seeds", path)

    seed_range = None
    if "seed_range" in data:
        raw_range = data["seed_range"]
        if not isinstance(raw_range, dict) or set(raw_range) != {"start", "end"}:
            raise EvaluationPresetError(
                f"{path}: 'seed_range' must be a mapping with exactly 'start' and 'end'."
            )
        start, end = raw_range["start"], raw_range["end"]
        _require_type(start, int, "seed_range.start", path)
        _require_type(end, int, "seed_range.end", path)
        if end < start:
            raise EvaluationPresetError(f"{path}: 'seed_range.end' must be >= 'seed_range.start'.")
        seed_range = (start, end)

    if seeds is not None and seed_range is not None:
        raise EvaluationPresetError(f"{path}: 'seeds' and 'seed_range' are mutually exclusive.")

    ticks = data.get("ticks")
    if ticks is not None:
        _require_type(ticks, int, "ticks", path)
        if ticks <= 0:
            raise EvaluationPresetError(f"{path}: 'ticks' must be greater than zero.")

    arena_size = data.get("arena_size")
    if arena_size is not None:
        _require_type(arena_size, int, "arena_size", path)
        if arena_size <= 0:
            raise EvaluationPresetError(f"{path}: 'arena_size' must be greater than zero.")

    instr_per_tick = data.get("instr_per_tick")
    if instr_per_tick is not None:
        _require_type(instr_per_tick, int, "instr_per_tick", path)
        if instr_per_tick <= 0:
            raise EvaluationPresetError(f"{path}: 'instr_per_tick' must be greater than zero.")

    orientation = data.get("orientation")
    if orientation is not None:
        _require_type(orientation, str, "orientation", path)
        if orientation not in _VALID_ORIENTATIONS:
            raise EvaluationPresetError(
                f"{path}: 'orientation' must be one of {_VALID_ORIENTATIONS!r}, got {orientation!r}."
            )

    ruleset_id = data.get("ruleset")
    if ruleset_id is not None:
        _require_type(ruleset_id, str, "ruleset", path)
        if ruleset_id not in _VALID_RULESETS:
            raise EvaluationPresetError(
                f"{path}: 'ruleset' must be one of {_VALID_RULESETS!r}, got {ruleset_id!r}."
            )

    # Content fingerprint: the parsed field payload only -- never filename,
    # path, or directory. Two presets with different names/paths but
    # byte-identical fields produce the same digest (Sec 7 of the governing
    # spec: preset provenance/naming must never affect canonical identity).
    content_digest = stable_id("evaluation-preset", data)

    return EvaluationPreset(
        name=name if name is not None else path.stem,
        path=path,
        description=description,
        candidate_id=candidate_id,
        baseline_id=baseline_id,
        opponent_ids=opponent_ids,
        seeds=seeds,
        seed_range=seed_range,
        ticks=ticks,
        arena_size=arena_size,
        instr_per_tick=instr_per_tick,
        orientation=orientation,
        ruleset_id=ruleset_id,
        content_digest=content_digest,
        raw=data,
    )


# ---------------------------------------------------------------------------
# CLI: list / show / validate
# ---------------------------------------------------------------------------


def _preset_to_json(preset: EvaluationPreset) -> dict[str, Any]:
    return {
        "name": preset.name,
        "path": str(preset.path),
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "description": preset.description,
        "candidate": preset.candidate_id,
        "baseline": preset.baseline_id,
        "opponents": list(preset.opponent_ids) if preset.opponent_ids is not None else None,
        "seeds": list(preset.seeds) if preset.seeds is not None else None,
        "seed_range": (
            {"start": preset.seed_range[0], "end": preset.seed_range[1]}
            if preset.seed_range is not None
            else None
        ),
        "ticks": preset.ticks,
        "arena_size": preset.arena_size,
        "instr_per_tick": preset.instr_per_tick,
        "orientation": preset.orientation,
        "ruleset": preset.ruleset_id,
        "content_digest": preset.content_digest,
    }


def _cmd_list(args: argparse.Namespace) -> int:
    root = get_data_root()
    names = list_presets(root)
    if args.json:
        print(json.dumps({"presets": list(names)}, indent=2, sort_keys=True))
        return 0
    if not names:
        print(f"No evaluation presets found in {presets_root(root)}.")
        return 0
    for name in names:
        try:
            preset = load_preset(root, name)
        except EvaluationPresetError as exc:
            print(f"{name}  INVALID: {exc}")
            continue
        print(f"{name}  {preset.description or ''}".rstrip())
    return 0


def _print_show(preset: EvaluationPreset) -> None:
    print(f"name: {preset.name}")
    print(f"path: {preset.path}")
    print(f"schema: {SCHEMA_NAME} v{SCHEMA_VERSION}")
    print(f"content_digest: {preset.content_digest}")
    if preset.description:
        print(f"description: {preset.description}")
    print(f"candidate: {preset.candidate_id or '(must be supplied at invocation)'}")
    print(f"baseline: {preset.baseline_id or 'none'}")
    print(
        "opponents: "
        + (", ".join(preset.opponent_ids) if preset.opponent_ids else "(must be supplied at invocation)")
    )
    if preset.seeds is not None:
        print(f"seeds: {', '.join(str(s) for s in preset.seeds)}")
    elif preset.seed_range is not None:
        print(f"seed_range: {preset.seed_range[0]}:{preset.seed_range[1]}")
    else:
        print("seeds: (not set by this preset -- explicit override, or the ordinary single-seed default)")
    print(f"ticks: {preset.ticks if preset.ticks is not None else '(not set -- ordinary default)'}")
    _unset = "(not set -- ordinary default)"
    print(f"arena_size: {preset.arena_size if preset.arena_size is not None else _unset}")
    print(
        "instr_per_tick: "
        f"{preset.instr_per_tick if preset.instr_per_tick is not None else _unset}"
    )
    print(f"orientation: {preset.orientation or '(not set -- ordinary default: both)'}")
    print(f"ruleset: {preset.ruleset_id or '(not set -- ordinary default: bytefray-rules-1)'}")
    print(
        "This preset supplies a partial EvaluationRequest: any field it does not set falls "
        "back to the ordinary CLI default, and any explicit CLI flag always overrides it. It "
        "never affects evaluation_id or any per-cell result -- see 'bytefray agents evaluate "
        "--preset " + preset.name + "' for the fully resolved configuration."
    )


def _cmd_show(args: argparse.Namespace) -> int:
    root = get_data_root()
    try:
        preset = load_preset(root, args.name)
    except EvaluationPresetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(_preset_to_json(preset), indent=2, sort_keys=True))
    else:
        _print_show(preset)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = get_data_root()
    try:
        preset = load_preset(root, args.name)
    except EvaluationPresetError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {preset.name} ({preset.path}) is a valid {SCHEMA_NAME} v{SCHEMA_VERSION} preset.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bytefray agents evaluation-presets")
    sub = parser.add_subparsers(dest="verb", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")

    show_parser = sub.add_parser("show")
    show_parser.add_argument("name")
    show_parser.add_argument("--json", action="store_true")

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("name")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verb == "list":
        return _cmd_list(args)
    if args.verb == "show":
        return _cmd_show(args)
    if args.verb == "validate":
        return _cmd_validate(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ORIENTATION_BOTH",
    "ORIENTATION_CANDIDATE_FIRST_ONLY",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "EvaluationPreset",
    "EvaluationPresetError",
    "list_presets",
    "load_preset",
    "load_preset_file",
    "main",
    "presets_root",
    "resolve_preset_path",
]
