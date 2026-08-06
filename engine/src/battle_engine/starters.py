"""Install bundled starter-agent manifests into the writable agent catalog."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from battle_engine.paths import get_data_root, get_resource_root

STARTER_AGENT_NAMES = ("runner", "writer", "seeker", "spiral")


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
