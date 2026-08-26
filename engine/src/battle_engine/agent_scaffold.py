"""``bytefray agents create <agent-id>`` — scaffold a Python agent.

Writes a static, byte-identical ``agent.yaml``/``agent.py`` pair (bundled
under one of :data:`TEMPLATE_DIRECTORIES`' resource directories, selected
by the ``template`` argument/``--template`` flag) into
``get_data_root()/agents/<agent-id>/``, using the same writable-root
resolver and exclusive-create discipline as :mod:`battle_engine.starters`,
but rejecting rather than skipping an existing destination.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from battle_engine.paths import get_data_root, get_resource_root

AGENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MAX_AGENT_ID_LENGTH = 64

TEMPLATE_FILES = ("agent.yaml", "agent.py")

# Phase 2 (v3.0 product cycle): a second, more heavily commented starting
# point alongside the original blank template, so a first-time user is not
# limited to an empty conceptual model. Deliberately its own fresh
# resource directory rather than an adaptation of a bundled starter agent
# -- docs/specs/agent_scaffold.md's own §8/§13 record that a starter's
# source and manifest (literal ``name``/``display`` fields, docstrings
# that cross-reference sibling starters by name) would misrepresent a
# newly scaffolded agent's identity if copied verbatim.
DEFAULT_TEMPLATE = "blank"
TEMPLATE_DIRECTORIES = {
    "blank": "agent_template",
    "annotated": "agent_template_annotated",
}

__all__ = [
    "DEFAULT_TEMPLATE",
    "TEMPLATE_DIRECTORIES",
    "AgentScaffoldError",
    "ScaffoldResult",
    "create_agent",
    "main",
    "template_resource_dir",
    "validate_agent_id",
    "validate_template",
]


class AgentScaffoldError(ValueError):
    """A user-correctable failure creating a scaffolded agent."""


@dataclass(frozen=True)
class ScaffoldResult:
    """Paths written by a successful :func:`create_agent` call."""

    agent_id: str
    manifest_path: Path
    source_path: Path


def validate_agent_id(agent_id: str) -> str:
    """Return ``agent_id`` unchanged if it satisfies the scaffold allow-list."""
    if not AGENT_ID_PATTERN.match(agent_id) or len(agent_id) > MAX_AGENT_ID_LENGTH:
        raise AgentScaffoldError(
            f"Invalid agent id {agent_id!r}: must match "
            f"{AGENT_ID_PATTERN.pattern!r} (max {MAX_AGENT_ID_LENGTH} characters)."
        )
    return agent_id


def validate_template(template: str) -> str:
    """Return ``template`` unchanged if it names a known scaffold template."""
    if template not in TEMPLATE_DIRECTORIES:
        known = ", ".join(sorted(TEMPLATE_DIRECTORIES))
        raise AgentScaffoldError(f"Unknown template {template!r}: expected one of {known}.")
    return template


def template_resource_dir(resource_root: Path, template: str = DEFAULT_TEMPLATE) -> Path:
    validate_template(template)
    dir_name = TEMPLATE_DIRECTORIES[template]
    candidates = (
        resource_root / "battle_engine" / "data" / dir_name,
        resource_root / "engine" / "src" / "battle_engine" / "data" / dir_name,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Agent template resource directory not found. Checked: {checked}")


def create_agent(
    agent_id: str,
    *,
    data_root: Path | None = None,
    resource_root: Path | None = None,
    template: str = DEFAULT_TEMPLATE,
) -> ScaffoldResult:
    """Create a new scaffolded Agent API v1 Python agent.

    Non-destructive: raises :class:`AgentScaffoldError` before touching the
    filesystem for an invalid ``agent_id`` or unknown ``template``, and
    before writing any template bytes if the destination already exists
    (directory or file). The two template files are written into a
    temporary sibling directory first and published with a single atomic
    rename, so a failure partway through writing never leaves a
    partially-created agent visible at the real path.

    ``template`` defaults to ``"blank"`` -- the original, sole template --
    so every pre-Phase-2 caller that omits it gets byte-identical output to
    before. See :data:`TEMPLATE_DIRECTORIES` for the full set.
    """
    validate_agent_id(agent_id)

    root = (data_root or get_data_root()).expanduser().resolve()
    resources = (resource_root or get_resource_root()).expanduser().resolve()
    template_dir = template_resource_dir(resources, template)

    agents_dir = root / "agents"
    destination = agents_dir / agent_id
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(agents_dir.resolve())
    except ValueError as exc:
        raise AgentScaffoldError(
            f"Agent id {agent_id!r} does not resolve within {agents_dir}."
        ) from exc

    agents_dir.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        raise AgentScaffoldError(
            f"An agent already exists at {destination}; it was not modified."
        )

    temp_dir = agents_dir / f".tmp-{agent_id}-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        for filename in TEMPLATE_FILES:
            source = template_dir / filename
            with (temp_dir / filename).open("xb") as output, source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    # Not wrapped in the cleanup above: on rename failure the fully-written
    # temp directory is left in place rather than silently deleted (no user
    # data lost), while the real destination is guaranteed never populated.
    os.rename(temp_dir, destination)

    return ScaffoldResult(
        agent_id=agent_id,
        manifest_path=destination / "agent.yaml",
        source_path=destination / "agent.py",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bytefray agents create",
        description="Create a minimal, immediately-discoverable Agent API v1 Python agent.",
    )
    parser.add_argument("agent_id", help="new agent's directory name, also its discovery id")
    parser.add_argument(
        "--template",
        choices=sorted(TEMPLATE_DIRECTORIES),
        default=DEFAULT_TEMPLATE,
        help=(
            "starting-point content: 'blank' (default, a minimal skeleton) or "
            "'annotated' (a commented example demonstrating READ-before-WRITE, "
            "arena wraparound, and the once-per-tick action budget)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = create_agent(args.agent_id, template=args.template)
    except (AgentScaffoldError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"agent: {result.agent_id}")
    print(f"manifest: {result.manifest_path}")
    print(f"source: {result.source_path}")
    print(f"Run 'bytefray run --a-type {result.agent_id} --b-type <opponent>' to try it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
