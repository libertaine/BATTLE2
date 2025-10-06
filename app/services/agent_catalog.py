from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import os

from app.services.agent_meta import read_agent_meta

@dataclass
class AgentRow:
    name: str
    path: str
    blob_path: Optional[str]
    meta: Dict[str, Any]

class AgentCatalog:
    """Very small catalog that lists agents/* subfolders and reads agent.yaml."""
    def __init__(self, battle_root: Path):
        self.battle_root = Path(battle_root)

    def agents_dir(self) -> Path:
        # Allow override via env (useful in tests), else <root>/agents
        override = os.getenv("BATTLE_AGENTS_DIR")
        return Path(override) if override else (self.battle_root / "agents")

    def list_agents(self) -> List[AgentRow]:
        base = self.agents_dir()
        rows: List[AgentRow] = []
        if not base.is_dir():
            return rows
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            meta = read_agent_meta(d)
            folder = d.name
            # Prefer display, then name, then folder name
            label = meta.get("display") or meta.get("name") or folder
            blob = meta.get("blob_path")
            rows.append(AgentRow(name=label, path=str(d), blob_path=blob, meta=meta))
        return rows
