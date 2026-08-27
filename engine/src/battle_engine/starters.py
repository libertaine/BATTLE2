"""Install bundled starter-agent manifests into the writable agent catalog."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from battle_engine.paths import get_data_root, get_resource_root

# The first four are native VM starters (manifest-only; resolved against
# the built-in VM programs in battle_engine.builtins by name -- see
# cli.py's SUPPORTED fallback). The remaining seven are Agent API v1 Python
# starters, each shipping its own agent.py implementing a distinct strategy
# against the restricted Python Agent API rather than native VM bytecode --
# see each agent.py's module docstring for its strategy and the reasoning
# behind it. ensure_starter_agents() treats both kinds identically:
# non-destructive copy-if-missing into the same writable agents/ catalog.
#
# Five of the Python starters (claimer, strider, hunter, wanderer,
# adaptive, added in v0.6.1) are expansion-family strategies and are also
# pinned members of the frozen v2 benchmark population -- their source is
# content-addressed in battle_engine/data/benchmarks/v2_baseline.json and
# must never be edited (see docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 3).
# raider and sentinel (added in v3.0.0-alpha2) are deliberately NOT
# benchmark members: they exist to demonstrate the Ruleset-v2 vulnerable-
# core mechanic itself -- attacking a core and defending one -- which no
# expansion starter exercises, and they stay freely maintainable precisely
# because they carry no benchmark identity.
STARTER_AGENT_NAMES = (
    "runner",
    "writer",
    "seeker",
    "spiral",
    "claimer",
    "strider",
    "hunter",
    "wanderer",
    "adaptive",
    "raider",
    "sentinel",
)


def _starter_resource_dir(resource_root: Path) -> Path:
    candidates = (
        resource_root / "battle_engine" / "data" / "starter_agents",
        resource_root / "engine" / "src" / "battle_engine" / "data" / "starter_agents",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Starter-agent resource directory not found. Checked: {checked}")


def _validate_starter(source_dir: Path, name: str) -> list[Path]:
    agent_dir = source_dir / name
    manifest = agent_dir / "agent.yaml"
    if not manifest.is_file():
        raise FileNotFoundError(f"Starter agent '{name}' is missing manifest: {manifest}")
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Starter agent '{name}' has malformed manifest {manifest}: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("name") != name:
        raise ValueError(
            f"Starter agent '{name}' manifest must be an object with name={name!r}: {manifest}"
        )
    files = sorted(path for path in agent_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Starter agent '{name}' contains no resource files: {agent_dir}")
    return files


def ensure_starter_agents(
    *,
    resource_root: Path | None = None,
    data_root: Path | None = None,
) -> list[Path]:
    """Copy missing starter files into the writable catalog and return created paths."""
    resources = (resource_root or get_resource_root()).expanduser().resolve()
    writable = (data_root or get_data_root()).expanduser().resolve()
    source_dir = _starter_resource_dir(resources)

    starter_files = {
        name: _validate_starter(source_dir, name) for name in STARTER_AGENT_NAMES
    }
    agents_dir = writable / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for name in STARTER_AGENT_NAMES:
        source_agent_dir = source_dir / name
        for source in starter_files[name]:
            relative = source.relative_to(source_agent_dir)
            destination = agents_dir / name / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with destination.open("xb") as output, source.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
            except FileExistsError:
                continue
            created.append(destination.resolve())
    return created
