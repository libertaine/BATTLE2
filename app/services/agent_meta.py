from __future__ import annotations
from pathlib import Path
from typing import Dict, Any

def read_agent_meta(agent_dir: Path) -> Dict[str, Any]:
    """Read agents/*/agent.yaml as JSON first, fallback to YAML (requires PyYAML)."""
    cfg = agent_dir / "agent.yaml"
    if not cfg.is_file():
        return {}
    text = cfg.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    # Try JSON first
    import json
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Fallback to YAML if available
        try:
            import yaml  # pip install pyyaml
        except Exception:
            return {}
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
