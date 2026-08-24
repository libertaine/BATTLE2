"""Read-only source loading for the Agent Designer.

This module deliberately reads only the two approved files beneath an
authoritatively discovered ``AgentRow.path``. It never parses, imports,
compiles, executes, or writes agent content.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.agent_catalog import AgentRow

SOURCE_FILENAMES = ("agent.py", "agent.yaml")


@dataclass(frozen=True)
class AgentSourceView:
    python_text: str
    manifest_text: str


def _load_source_file(agent_dir: Path, filename: str) -> str:
    path = agent_dir / filename
    if not path.is_file():
        return f"{filename} is not available for this agent."
    try:
        resolved_dir = agent_dir.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if resolved_path.parent != resolved_dir:
            return f"Unable to read {filename}: source path leaves the agent directory."
        return resolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return f"Unable to read {filename}: {exc}"


def load_agent_source(
    row: AgentRow | None, *, agents_root: Path | None = None
) -> AgentSourceView:
    """Load approved current source files from the row's exact discovered path."""
    if row is None:
        message = "No Python agent selected."
        return AgentSourceView(message, message)
    agent_dir = Path(row.path)
    if agents_root is not None:
        try:
            agent_dir.resolve(strict=True).relative_to(agents_root.resolve(strict=True))
        except (OSError, ValueError):
            message = "discovered path leaves the agent catalog."
            return AgentSourceView(
                f"Unable to read agent.py: {message}",
                f"Unable to read agent.yaml: {message}",
            )
    if not agent_dir.is_dir():
        message = "agent directory is not available."
        return AgentSourceView(
            f"Unable to read agent.py: {message}",
            f"Unable to read agent.yaml: {message}",
        )
    return AgentSourceView(
        python_text=_load_source_file(agent_dir, SOURCE_FILENAMES[0]),
        manifest_text=_load_source_file(agent_dir, SOURCE_FILENAMES[1]),
    )
