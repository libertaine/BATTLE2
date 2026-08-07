from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from battle_engine.agent_api import AgentManifestError

__all__ = [
    "AgentSpec",
    "discover_agents",
    "discover_agents_in",
    "resolve_agent",
]


@dataclass
class AgentSpec:
    name: str
    display: str
    dir: Path
    blob: Path | None
    defaults: Dict[str, Any]
    kind: str = "builtin"
    api_version: int | None = None
    version: str | None = None
    source_path: Path | None = None
    entry_point: str | None = None
    manifest: Dict[str, Any] = field(default_factory=dict)


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
    cleansed = "\n".join(lines).strip()
    cleansed = (
        cleansed.replace(",}", "}").replace(", }", " }").replace(",]", "]").replace(", ]", " ]")
    )

    if not cleansed:
        return {}

    # 1) Try JSON (original behavior)
    try:
        data = json.loads(cleansed)
    except json.JSONDecodeError:
        # 2) Fallback: YAML if available
        try:
            import importlib

            yaml = importlib.import_module("yaml")
        except Exception:
            raise ValueError(
                f"{path} is not valid JSON. Convert to JSON, or 'pip install pyyaml' to allow YAML."
            )
        data = yaml.safe_load(cleansed) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain an object/map.")
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
    meta: Dict[str, Any] = {}

    if yaml_path.exists():
        try:
            meta = _read_json_like(yaml_path)
        except Exception as e:
            raise AgentManifestError(f"Failed parsing {yaml_path}: {e}", path=yaml_path) from e
        display = str(meta.get("display") or meta.get("name") or name)
        if "defaults" in meta:
            if isinstance(meta["defaults"], dict):
                defaults = dict(meta["defaults"])
            else:
                raise AgentManifestError(
                    f"'defaults' in {yaml_path} must be an object.", path=yaml_path
                )
    else:
        if not py_path.exists():
            # not a valid agent folder by our rules
            return None
        # agent.py exists; infer minimal metadata
        display = name
        defaults = {}

    declared_name = meta.get("name")
    if declared_name is not None and (
        not isinstance(declared_name, str) or not declared_name.strip()
    ):
        raise AgentManifestError(
            f"'name' in {yaml_path} must be a non-empty string.", path=yaml_path
        )
    api_value = meta.get("api_version")
    if api_value is not None and (isinstance(api_value, bool) or not isinstance(api_value, int)):
        raise AgentManifestError(
            f"'api_version' in {yaml_path} must be an integer.", path=yaml_path
        )
    version_value = meta.get("version")
    if version_value is not None and (
        not isinstance(version_value, str) or not version_value.strip()
    ):
        raise AgentManifestError(
            f"'version' in {yaml_path} must be a non-empty string.", path=yaml_path
        )
    entry_value = meta.get("entrypoint")
    if entry_value is not None and (not isinstance(entry_value, str) or not entry_value.strip()):
        raise AgentManifestError(
            f"'entrypoint' in {yaml_path} must be a non-empty string.", path=yaml_path
        )

    blob = blob_path if blob_path.exists() else None
    kind_value = meta.get("kind")
    if kind_value is None:
        kind = "python" if py_path.exists() else "blob" if blob is not None else "builtin"
    elif not isinstance(kind_value, str) or kind_value not in {"builtin", "blob", "python"}:
        raise AgentManifestError(
            f"'kind' in {yaml_path} must be one of: builtin, blob, python.", path=yaml_path
        )
    else:
        kind = kind_value

    entry_point = (
        str(entry_value)
        if entry_value is not None
        else ("agent.py:create_agent" if kind == "python" and py_path.exists() else None)
    )
    source_path = None
    if kind == "python" and entry_point:
        module_value = entry_point.partition(":")[0]
        source_path = (agent_dir / module_value).resolve() if module_value else None

    return AgentSpec(
        name=name,
        display=display,
        dir=agent_dir,
        blob=blob,
        defaults=defaults,
        kind=kind,
        api_version=api_value,
        version=version_value,
        source_path=source_path,
        entry_point=entry_point,
        manifest=dict(meta),
    )


def discover_agents(root: Path) -> Dict[str, AgentSpec]:
    return discover_agents_in(_agents_root(root))


def discover_agents_in(base: Path) -> Dict[str, AgentSpec]:
    """Discover agents in an explicit directory, for UI/test path overrides."""

    base = base.resolve()
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
