"""Public loading and Phase 3a runtime contract for BATTLE2 Python agents."""

from __future__ import annotations

import hashlib
import importlib.util
import random
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, runtime_checkable

AGENT_API_VERSION = 1


class AgentValidationError(ValueError):
    """Base class for diagnostics safe to present through CLI and GUI surfaces."""

    code = "agent_validation_failed"

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


class AgentManifestError(AgentValidationError):
    code = "agent_manifest_invalid"


class UnsupportedAgentAPIVersionError(AgentValidationError):
    code = "agent_api_version_unsupported"


class AgentSourceError(AgentValidationError):
    code = "agent_source_invalid"


class AgentImportError(AgentValidationError):
    code = "agent_import_failed"


class AgentFactoryError(AgentValidationError):
    code = "agent_factory_failed"


class AgentContractError(AgentValidationError):
    code = "agent_contract_invalid"


@dataclass(frozen=True)
class AgentMetadata:
    """Engine-controlled identity associated with one loaded agent instance."""

    agent_id: str
    name: str
    version: str
    api_version: int = AGENT_API_VERSION


@dataclass(frozen=True)
class MatchContext:
    """Engine-controlled immutable match context supplied once at reset."""

    agent_id: str
    seed: int
    arena_size: int
    tick_limit: int
    action_budget: int
    rng: random.Random


@dataclass(frozen=True)
class Observation:
    """Restricted immutable state visible before one Python-agent action."""

    tick: int
    agent_id: str
    pc: int
    register_a: int
    register_p: int
    zero_flag: bool
    last_read: int | None
    alive: bool


class ActionKind(str, Enum):
    """Versioned Phase 3a battlefield-operation vocabulary."""

    NOP = "nop"
    SET_A = "set_a"
    ADD_A = "add_a"
    READ = "read"
    WRITE = "write"
    SET_P = "set_p"
    ADD_P = "add_p"
    JUMP = "jump"
    JUMP_IF_ZERO = "jump_if_zero"
    HALT = "halt"


@dataclass(frozen=True)
class AgentAction:
    """Exactly one validated battlefield operation returned by ``act``."""

    kind: ActionKind
    operand: int | None = None
    value: int | None = None


@runtime_checkable
class AgentV1(Protocol):
    """Structural lifecycle required from an Agent API v1 factory result."""

    def reset(self, context: MatchContext) -> None: ...

    def act(self, observation: Observation) -> AgentAction: ...


@dataclass(frozen=True)
class LoadedPythonAgent:
    """A fresh validated instance paired with engine-controlled metadata."""

    metadata: AgentMetadata
    instance: AgentV1
    source_path: Path
    entry_point: str


def parse_entry_point(value: str, *, agent_dir: Path) -> tuple[Path, str]:
    """Resolve ``relative/path.py:factory`` without allowing directory escape."""

    module_value, separator, factory_name = value.partition(":")
    if not separator or not module_value.strip() or not factory_name.strip():
        raise AgentSourceError(
            "Python agent entrypoint must use 'relative/path.py:factory' syntax.",
            path=agent_dir,
        )
    if not factory_name.isidentifier():
        raise AgentSourceError(
            f"Python agent factory name is not a valid identifier: {factory_name!r}.",
            path=agent_dir,
        )

    base = agent_dir.resolve()
    source = (base / module_value).resolve()
    try:
        source.relative_to(base)
    except ValueError as exc:
        raise AgentSourceError(
            f"Python agent entrypoint escapes its agent directory: {module_value!r}.",
            path=source,
        ) from exc
    if source.suffix.lower() != ".py":
        raise AgentSourceError(
            f"Python agent entrypoint must reference a .py file: {module_value!r}.",
            path=source,
        )
    return source, factory_name


def _module_name(source_path: Path) -> str:
    digest = hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()[:24]
    return f"_battle2_agent_{digest}"


def _import_source(source_path: Path) -> ModuleType:
    module_name = _module_name(source_path)
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise AgentImportError(
            f"Could not create an import specification for Python agent source: {source_path}",
            path=source_path,
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise AgentImportError(
            f"Failed importing Python agent source {source_path}: {type(exc).__name__}: {exc}",
            path=source_path,
        ) from exc
    return module


def load_python_agent(agent_spec: Any) -> LoadedPythonAgent:
    """Import, construct, and structurally validate one fresh Python agent."""

    if getattr(agent_spec, "kind", None) != "python":
        raise AgentContractError(
            f"Agent {getattr(agent_spec, 'name', '<unknown>')!r} is not a Python agent.",
            path=getattr(agent_spec, "dir", None),
        )
    api_version = getattr(agent_spec, "api_version", None)
    if api_version != AGENT_API_VERSION:
        raise UnsupportedAgentAPIVersionError(
            f"Python agent {agent_spec.name!r} declares API version {api_version!r}; "
            f"BATTLE2 supports version {AGENT_API_VERSION}.",
            path=agent_spec.dir,
        )
    entry_point = getattr(agent_spec, "entry_point", None)
    if not entry_point:
        raise AgentSourceError(
            f"Python agent {agent_spec.name!r} does not declare an entrypoint.",
            path=agent_spec.dir,
        )
    source_path, factory_name = parse_entry_point(entry_point, agent_dir=agent_spec.dir)
    if not source_path.is_file():
        raise AgentSourceError(
            f"Python agent source file was not found: {source_path}", path=source_path
        )

    module = _import_source(source_path)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise AgentFactoryError(
            f"Python agent entrypoint {entry_point!r} does not expose a callable "
            f"factory named {factory_name!r}.",
            path=source_path,
        )
    try:
        instance = factory()
    except BaseException as exc:
        raise AgentFactoryError(
            f"Python agent factory {entry_point!r} failed: {type(exc).__name__}: {exc}",
            path=source_path,
        ) from exc
    missing = [
        name for name in ("reset", "act") if not callable(getattr(instance, name, None))
    ]
    if missing or not isinstance(instance, AgentV1):
        detail = ", ".join(missing) or "AgentV1 lifecycle methods"
        raise AgentContractError(
            f"Python agent factory {entry_point!r} returned {type(instance).__name__}; "
            f"missing callable {detail}.",
            path=source_path,
        )

    metadata = AgentMetadata(
        agent_id=agent_spec.name,
        name=agent_spec.display,
        version=agent_spec.version or "0",
        api_version=api_version,
    )
    return LoadedPythonAgent(metadata, instance, source_path, entry_point)


__all__ = [
    "AGENT_API_VERSION",
    "ActionKind",
    "AgentAction",
    "AgentContractError",
    "AgentFactoryError",
    "AgentImportError",
    "AgentManifestError",
    "AgentMetadata",
    "AgentSourceError",
    "AgentV1",
    "AgentValidationError",
    "LoadedPythonAgent",
    "MatchContext",
    "Observation",
    "UnsupportedAgentAPIVersionError",
    "load_python_agent",
    "parse_entry_point",
]
