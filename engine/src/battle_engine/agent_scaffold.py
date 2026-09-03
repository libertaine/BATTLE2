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

from battle_engine.agent_api import SUPPORTED_AGENT_API_VERSIONS
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

# The Agent API generation a scaffold produces when the author does not ask
# for one. Deliberately pinned to 1 rather than tracking
# ``agent_api.AGENT_API_VERSION``: ``bytefray agents create <id>`` has always
# produced an Agent API v1 agent, and repointing an established command's
# default at a newer generation would silently change the meaning of every
# existing script and instruction that uses it. Agent API v2 is reachable by
# asking for it explicitly (``--api-version 2``); which *Ruleset* such an
# agent then runs under is derived automatically from the manifest it
# declares (``ruleset_policy.resolve_omitted_ruleset_for_agents``), so
# choosing a newer default here would buy nothing anyway.
DEFAULT_API_VERSION = 1

# One template set per supported Agent API generation. Keyed by the same
# ``api_version`` value a manifest declares, so the scaffold cannot offer an
# API version the loader would refuse to run: ``validate_api_version``
# derives its accepted values from ``SUPPORTED_AGENT_API_VERSIONS`` (the
# authoritative set introduced by the Phase 1 packaging remediation) and
# ``test_scaffold_templates_cover_every_supported_api_version`` fails loudly
# if a future generation is added to that set without a template here.
TEMPLATE_DIRECTORIES_BY_API_VERSION: dict[int, dict[str, str]] = {
    1: TEMPLATE_DIRECTORIES,
    2: {
        "blank": "agent_template_v2",
        "annotated": "agent_template_v2_annotated",
    },
}

__all__ = [
    "DEFAULT_API_VERSION",
    "DEFAULT_TEMPLATE",
    "TEMPLATE_DIRECTORIES",
    "TEMPLATE_DIRECTORIES_BY_API_VERSION",
    "AgentScaffoldError",
    "ScaffoldResult",
    "create_agent",
    "main",
    "template_resource_dir",
    "validate_agent_id",
    "validate_api_version",
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


def validate_api_version(api_version: int) -> int:
    """Return ``api_version`` unchanged if this installation can scaffold it.

    Accepts exactly the generations that are both supported by the loader
    (:data:`~battle_engine.agent_api.SUPPORTED_AGENT_API_VERSIONS`) and have
    a bundled template set, so the scaffold can never emit a manifest
    ``load_python_agent`` would reject.
    """
    if api_version not in scaffold_api_versions():
        known = ", ".join(str(version) for version in sorted(scaffold_api_versions()))
        raise AgentScaffoldError(
            f"Unsupported Agent API version {api_version!r}: expected one of {known}."
        )
    return api_version


def scaffold_api_versions() -> frozenset[int]:
    """The Agent API generations ``bytefray agents create`` can produce."""
    return frozenset(TEMPLATE_DIRECTORIES_BY_API_VERSION) & SUPPORTED_AGENT_API_VERSIONS


def validate_template(template: str, api_version: int = DEFAULT_API_VERSION) -> str:
    """Return ``template`` unchanged if it names a known scaffold template."""
    directories = TEMPLATE_DIRECTORIES_BY_API_VERSION.get(api_version, TEMPLATE_DIRECTORIES)
    if template not in directories:
        known = ", ".join(sorted(directories))
        raise AgentScaffoldError(f"Unknown template {template!r}: expected one of {known}.")
    return template


def template_resource_dir(
    resource_root: Path,
    template: str = DEFAULT_TEMPLATE,
    *,
    api_version: int = DEFAULT_API_VERSION,
) -> Path:
    """Locate one bundled template directory.

    ``api_version`` is keyword-only and defaults to
    :data:`DEFAULT_API_VERSION`, so every pre-existing positional caller --
    notably ``agent_test._reference_opponent_spec``, which loads the Agent
    API v1 blank template as its internal reference opponent -- keeps
    resolving exactly the directory it resolved before.
    """
    validate_api_version(api_version)
    validate_template(template, api_version)
    dir_name = TEMPLATE_DIRECTORIES_BY_API_VERSION[api_version][template]
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
    api_version: int = DEFAULT_API_VERSION,
) -> ScaffoldResult:
    """Create a new scaffolded Python agent for one Agent API generation.

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

    ``api_version`` selects the Agent API generation to scaffold and
    defaults to :data:`DEFAULT_API_VERSION` (v1), so every caller that omits
    it -- including Agent Designer's New Agent dialog -- also gets
    byte-identical output to before. Pass ``2`` for a process agent that
    runs under the stable ``bytefray-rules-4`` (v4.0.0-rc1 Phase 2) by
    default, or explicitly under ``bytefray-rules-4-alpha1``/``-alpha2`` to
    reproduce a historical prerelease match.
    """
    validate_agent_id(agent_id)
    validate_api_version(api_version)

    root = (data_root or get_data_root()).expanduser().resolve()
    resources = (resource_root or get_resource_root()).expanduser().resolve()
    template_dir = template_resource_dir(resources, template, api_version=api_version)

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
        description="Create a minimal, immediately-discoverable Python agent.",
    )
    parser.add_argument("agent_id", help="new agent's directory name, also its discovery id")
    parser.add_argument(
        "--api-version",
        dest="api_version",
        type=int,
        choices=sorted(scaffold_api_versions()),
        default=DEFAULT_API_VERSION,
        help=(
            f"Agent API generation to scaffold (default: {DEFAULT_API_VERSION}). "
            "1 is the historical single-actor API and runs under "
            "bytefray-rules-2; 2 is the process API (reset, declare_processes, "
            "act) and runs under the stable bytefray-rules-4. The Ruleset is "
            "selected automatically from the created agent's manifest."
        ),
    )
    parser.add_argument(
        "--template",
        choices=sorted(TEMPLATE_DIRECTORIES),
        default=DEFAULT_TEMPLATE,
        help=(
            "starting-point content: 'blank' (default, a minimal skeleton) or "
            "'annotated' (a commented example). Both are available for every "
            "--api-version."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = create_agent(
            args.agent_id, template=args.template, api_version=args.api_version
        )
    except (AgentScaffoldError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"agent: {result.agent_id}")
    print(f"api_version: {args.api_version}")
    print(f"manifest: {result.manifest_path}")
    print(f"source: {result.source_path}")
    print(f"Run 'bytefray run --a-type {result.agent_id} --b-type <opponent>' to try it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
