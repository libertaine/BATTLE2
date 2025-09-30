from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json


@dataclass
class AgentInfo:
    name: str
    display: str
    path: Path


class AgentCatalog:
    """Discovers available agents under <BATTLE_ROOT>/agents/*.

    Prefers metadata from agent.yaml (JSON subset allowed) with fields: {name, display}.
    Falls back to directory name if only agent.py exists.
    """

    def __init__(self, battle_root: Path) -> None:
        self.root = battle_root
        self._agents: List[AgentInfo] = []

    def refresh(self) -> None:
        base = self.root / "agents"
        agents: List[AgentInfo] = []
        if not base.exists():
            self._agents = []
            return
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            yaml_path = child / "agent.yaml"
            py_path = child / "agent.py"
            name = child.name
            display = name
            if yaml_path.exists():
                try:
                    # Support JSON superset for simplicity to avoid YAML dep
                    meta = json.loads(yaml_path.read_text())
                except Exception:
                    meta = {}
                name = str(meta.get("name", name))
                display = str(meta.get("display", display))
            elif not py_path.exists():
                # Not a valid agent container
                continue
            agents.append(AgentInfo(name=name, display=display, path=child))
        self._agents = agents

    def list_names(self) -> List[str]:
        return [a.name for a in self._agents]

    def get(self, name: str) -> Optional[AgentInfo]:
        for a in self._agents:
            if a.name == name:
                return a
        return None
