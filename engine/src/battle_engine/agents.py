from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

__all__ = [
    "AgentSpec",
    "discover_agents",
    "resolve_agent",
]


@dataclass
class AgentSpec:
    name: str
    display: str
    dir: Path
    blob: Path | None
    defaults: Dict[str, Any]


def _agents_root(root: Path) -> Path:
    return (root / "agents").resolve()


def _read_json_like(path: Path) -> Dict[str, Any]:
    """
    Parse agent.yaml as JSON (no YAML dependency).
    Allows:
      - // and # comments (stripped)
      - simple trailing comma cleanup
    """
    text = path.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        s = line.split("//", 1)[0]
        s = s.split("#", 1)[0]
        lines.append(s)
    cleansed = "\n".join(lines)
    cleansed = cleansed.replace(",}", "}").replace(", }", " }").replace(",]", "]").replace(", ]", " ]")
    data = json.loads(cleansed) if cleansed.strip() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _spec_from_dir(agent_dir: Path) -> AgentSpec | None:
    if not agent_dir.is_dir():
        return None
    name = agent_dir.name
    yaml_path = agent_dir / "agent.yaml"
    py_path = agent_dir / "agent.py"
    blob_path = agent_dir / "model.blob"

    display = name
    defaults: Dict[str, Any] = {}

    if yaml_path.exists():
        try:
            meta = _read_json_like(yaml_path)
        except Exception as e:
            raise SystemExit(f"Failed parsing {yaml_path}: {e}")
        display = str(meta.get("display") or meta.get("name") or name)
        if "defaults" in meta:
            if isinstance(meta["defaults"], dict):
                defaults = dict(meta["defaults"])
            else:
                raise SystemExit(f"'defaults' in {yaml_path} must be an object.")
    else:
        if not py_path.exists():
            # not a valid agent folder by our rules
            return None
        # agent.py exists; infer minimal metadata
        display = name
        defaults = {}

    blob = blob_path if blob_path.exists() else None
    return AgentSpec(name=name, display=display, dir=agent_dir, blob=blob, defaults=defaults)


def discover_agents(root: Path) -> Dict[str, AgentSpec]:
    base = _agents_root(root)
    if not base.exists():
        return {}
    specs: Dict[str, AgentSpec] = {}
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        spec = _spec_from_dir(child)
        if spec:
            specs[spec.name] = spec
    return specs


def resolve_agent(root: Path, name: str) -> AgentSpec:
    if not name or not name.strip():
        raise SystemExit("Agent name cannot be empty.")
    agent_dir = _agents_root(root) / name
    spec = _spec_from_dir(agent_dir)
    if spec is None:
        raise SystemExit(
            f"Unknown agent '{name}'. Expected a folder {agent_dir} with agent.yaml (JSON) or agent.py"
        )
    return spec
