from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from battle_engine.agents import discover_agents_in


@dataclass
class AgentRow:
    name: str
    path: str
    blob_path: Optional[str]
    meta: Dict[str, Any]


class AgentCatalog:
    """Designer adapter over the canonical engine-side agent discovery model."""

    def __init__(self, battle_root: Path):
        self.battle_root = Path(battle_root)

    def agents_dir(self) -> Path:
        # Allow override via env (useful in tests), else <root>/agents
        override = os.getenv("BATTLE_AGENTS_DIR")
        return Path(override) if override else (self.battle_root / "agents")

    def list_agents(self) -> List[AgentRow]:
        base = self.agents_dir()
        specs = discover_agents_in(base)
        rows: List[AgentRow] = []
        for spec in specs.values():
            meta = dict(spec.manifest)
            declared_blob = meta.get("blob_path")
            blob_path = (
                str(spec.blob)
                if spec.blob is not None
                else declared_blob
                if isinstance(declared_blob, str) and declared_blob
                else None
            )
            meta.setdefault("name", spec.name)
            meta.setdefault("display", spec.display)
            meta.setdefault("kind", spec.kind)
            if spec.api_version is not None:
                meta.setdefault("api_version", spec.api_version)
            if spec.version is not None:
                meta.setdefault("version", spec.version)
            if spec.entry_point is not None:
                meta.setdefault("entrypoint", spec.entry_point)
            rows.append(
                AgentRow(
                    name=spec.display,
                    path=str(spec.dir),
                    blob_path=blob_path,
                    meta=meta,
                )
            )
        return rows
