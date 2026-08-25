"""Frozen benchmark populations for the v3 research program (Phase 0C).

A *benchmark population* names an exact, immutable set of agent revisions.
It exists so a researcher can say "run the Phase-0 v2 benchmark population"
and have that phrase mean one specific thing forever, rather than "whatever
files happen to be under ``agents/`` today" -- the failure mode
docs/V3_PHASE0_RESEARCH_BASELINE.md Sec 3 exists to prevent.

Deliberately *not* a new identity mechanism. Every member is pinned by the
content-addressed ``agent_revision_id`` that
``battle_engine.agent_revisions`` already computes for provenance, plus the
same ``source_sha256``/``local_python_subset_fingerprint`` pair
``agent_evaluation.agent_identity``/``_post_execution_identity_drift``
already use as ground truth. This module adds a *manifest* over that
existing infrastructure and nothing else -- no registry, no signing, no
distribution surface.

The manifest is committed package data (``data/benchmarks/*.json``), so a
later repository edit to an agent's source changes what
:func:`verify_population` reports but can never silently change what the
benchmark *means*.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from battle_engine.agent_revisions import (
    agent_revision_fingerprint,
    agent_revision_id,
    local_python_subset_fingerprint,
    walk_agent_files,
)
from battle_engine.paths import get_resource_root

SCHEMA_NAME = "bytefray.benchmark_population"
SCHEMA_VERSION = 1

#: The v3 Phase 0 frozen Ruleset-v2 benchmark population.
V2_BASELINE_ID = "v2-baseline"


class BenchmarkPopulationError(ValueError):
    """A missing, malformed, or unsupported benchmark manifest."""

    code = "benchmark_population_invalid"


@dataclass(frozen=True)
class BenchmarkMember:
    """One pinned member of a benchmark population."""

    agent_id: str
    display: str
    catalog: str
    resource_dir: str
    runtime_kind: str
    agent_api_version: int
    agent_version: str | None
    entry_point: str | None
    agent_revision_id: str
    source_sha256: str
    local_python_subset_fingerprint: str | None
    files: tuple[str, ...]
    strategic_role: str
    behavior: str


@dataclass(frozen=True)
class BenchmarkPopulation:
    """A loaded, validated benchmark manifest."""

    benchmark_id: str
    description: str
    ruleset_id: str
    frozen_at_commit: str | None
    members: tuple[BenchmarkMember, ...]
    ecology_core: tuple[str, ...]
    ecology_core_note: str

    @property
    def agent_ids(self) -> tuple[str, ...]:
        return tuple(member.agent_id for member in self.members)

    def member(self, agent_id: str) -> BenchmarkMember:
        for candidate in self.members:
            if candidate.agent_id == agent_id:
                return candidate
        raise BenchmarkPopulationError(
            f"Agent {agent_id!r} is not a member of benchmark population "
            f"{self.benchmark_id!r}."
        )

    def ecology_core_members(self) -> tuple[BenchmarkMember, ...]:
        """The subset the Beta2 Phase 4 Sec 17 ecology rubric was scored on."""

        return tuple(self.member(agent_id) for agent_id in self.ecology_core)


@dataclass(frozen=True)
class MemberVerification:
    """One member's live-tree verification outcome."""

    agent_id: str
    matches: bool
    detail: str


def _benchmarks_resource_dir(resource_root: Path) -> Path:
    """Locate the packaged benchmark manifests.

    Mirrors ``reference_agents._reference_agents_resource_dir`` exactly --
    both an installed-wheel layout and a source checkout are supported,
    with the same explicit "checked these paths" error text.
    """

    candidates = (
        resource_root / "battle_engine" / "data" / "benchmarks",
        resource_root / "engine" / "src" / "battle_engine" / "data" / "benchmarks",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise BenchmarkPopulationError(
        f"Benchmark-population resource directory not found. Checked: {checked}"
    )


def _require(data: dict[str, Any], key: str, expected: type, path: Path) -> Any:
    if key not in data:
        raise BenchmarkPopulationError(f"{path}: missing required field {key!r}.")
    value = data[key]
    if not isinstance(value, expected):
        raise BenchmarkPopulationError(
            f"{path}: field {key!r} must be {expected.__name__}, got "
            f"{type(value).__name__}."
        )
    return value


def load_population(
    benchmark_id: str = V2_BASELINE_ID, *, resource_root: Path | None = None
) -> BenchmarkPopulation:
    """Load one committed benchmark manifest by id."""

    root = _benchmarks_resource_dir(resource_root or get_resource_root())
    path = root / f"{benchmark_id.replace('-', '_')}.json"
    if not path.is_file():
        raise BenchmarkPopulationError(
            f"Unknown benchmark population {benchmark_id!r}: {path} does not exist."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkPopulationError(f"{path}: malformed JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BenchmarkPopulationError(f"{path}: manifest must be a JSON object.")

    schema = _require(data, "schema", str, path)
    if schema != SCHEMA_NAME:
        raise BenchmarkPopulationError(
            f"{path}: unsupported schema {schema!r}; expected {SCHEMA_NAME!r}."
        )
    schema_version = _require(data, "schema_version", int, path)
    if schema_version != SCHEMA_VERSION:
        raise BenchmarkPopulationError(
            f"{path}: unsupported schema_version {schema_version}; expected {SCHEMA_VERSION}."
        )

    members = []
    for entry in _require(data, "members", list, path):
        if not isinstance(entry, dict):
            raise BenchmarkPopulationError(f"{path}: every 'members' entry must be an object.")
        members.append(
            BenchmarkMember(
                agent_id=str(entry["agent_id"]),
                display=str(entry["display"]),
                catalog=str(entry["catalog"]),
                resource_dir=str(entry["resource_dir"]),
                runtime_kind=str(entry["runtime_kind"]),
                agent_api_version=int(entry["agent_api_version"]),
                agent_version=entry.get("agent_version"),
                entry_point=entry.get("entry_point"),
                agent_revision_id=str(entry["agent_revision_id"]),
                source_sha256=str(entry["source_sha256"]),
                local_python_subset_fingerprint=entry.get("local_python_subset_fingerprint"),
                files=tuple(str(name) for name in entry.get("files", ())),
                strategic_role=str(entry["strategic_role"]),
                behavior=str(entry["behavior"]),
            )
        )
    if not members:
        raise BenchmarkPopulationError(f"{path}: benchmark population has no members.")

    return BenchmarkPopulation(
        benchmark_id=_require(data, "benchmark_id", str, path),
        description=_require(data, "description", str, path),
        ruleset_id=_require(data, "ruleset_id", str, path),
        frozen_at_commit=data.get("frozen_at_commit"),
        members=tuple(members),
        ecology_core=tuple(str(name) for name in data.get("ecology_core", ())),
        ecology_core_note=str(data.get("ecology_core_note", "")),
    )


def member_source_dir(member: BenchmarkMember, resource_root: Path | None = None) -> Path:
    """Resolve one member's live source directory in this checkout/install."""

    root = (resource_root or get_resource_root()).resolve()
    relative = Path(member.resource_dir)
    candidates = (root / relative, root / "engine" / "src" / relative)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise BenchmarkPopulationError(
        f"Benchmark member {member.agent_id!r} source directory not found. Checked: {checked}"
    )


def verify_member(
    member: BenchmarkMember, *, resource_root: Path | None = None
) -> MemberVerification:
    """Recompute one member's identity from the live tree and compare it to the pin.

    Recomputes through the *same* ``agent_revisions`` functions the
    evaluation harness's own drift detection uses, so a mismatch here means
    exactly what a mismatch there would mean: the source no longer is the
    revision the benchmark names.
    """

    try:
        agent_dir = member_source_dir(member, resource_root)
    except BenchmarkPopulationError as exc:
        return MemberVerification(member.agent_id, False, str(exc))

    fingerprint = agent_revision_fingerprint(agent_dir)
    if fingerprint is None:
        return MemberVerification(
            member.agent_id, False, f"No revision fingerprint computable for {agent_dir}."
        )
    actual_revision = agent_revision_id(fingerprint)
    if actual_revision != member.agent_revision_id:
        return MemberVerification(
            member.agent_id,
            False,
            f"agent_revision_id drift: pinned {member.agent_revision_id}, "
            f"live {actual_revision}.",
        )

    source_path = agent_dir / "agent.py"
    if not source_path.is_file():
        return MemberVerification(member.agent_id, False, f"Missing source file {source_path}.")
    actual_source = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual_source != member.source_sha256:
        return MemberVerification(
            member.agent_id,
            False,
            f"source_sha256 drift: pinned {member.source_sha256}, live {actual_source}.",
        )

    actual_subset = local_python_subset_fingerprint(walk_agent_files(agent_dir))
    if actual_subset != member.local_python_subset_fingerprint:
        return MemberVerification(
            member.agent_id,
            False,
            "local_python_subset_fingerprint drift: pinned "
            f"{member.local_python_subset_fingerprint}, live {actual_subset}.",
        )

    return MemberVerification(member.agent_id, True, f"matches {member.agent_revision_id}")


def verify_population(
    population: BenchmarkPopulation, *, resource_root: Path | None = None
) -> tuple[MemberVerification, ...]:
    """Verify every member against the live tree, in manifest order."""

    return tuple(
        verify_member(member, resource_root=resource_root) for member in population.members
    )


def stage_population(
    population: BenchmarkPopulation,
    data_root: Path,
    *,
    resource_root: Path | None = None,
    agent_ids: tuple[str, ...] | None = None,
) -> tuple[Path, ...]:
    """Copy benchmark members into ``data_root/agents`` so evaluation can discover them.

    ``bytefray agents evaluate`` resolves entrants through
    ``agents.resolve_agent`` against ``BYTEFRAY_ROOT/agents/``, and the four
    reference agents deliberately live only as package resources (see
    ``reference_agents``'s module docstring). Staging is therefore how a
    research corpus makes the population runnable -- the identical approach
    ``runs/research_v2_beta2_phase4/`` already used by hand.

    Copies file-by-file from the exact ``files`` list the manifest pins, so
    a staged catalog can never pick up an untracked extra file that would
    change the agent's revision identity.
    """

    members = (
        population.members
        if agent_ids is None
        else tuple(population.member(agent_id) for agent_id in agent_ids)
    )
    agents_dir = (data_root / "agents").resolve()
    agents_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for member in members:
        source_dir = member_source_dir(member, resource_root)
        target_dir = agents_dir / member.agent_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for relative in member.files:
            source = source_dir / relative
            target = target_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            staged.append(target)
    return tuple(staged)


__all__ = [
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "V2_BASELINE_ID",
    "BenchmarkMember",
    "BenchmarkPopulation",
    "BenchmarkPopulationError",
    "MemberVerification",
    "load_population",
    "member_source_dir",
    "stage_population",
    "verify_member",
    "verify_population",
]
