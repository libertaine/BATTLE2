"""Public loading and Phase 3a runtime contract for Bytefray Python agents."""

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

AGENT_API_VERSION = 2

# The authoritative set of Python Agent API generations this installation's
# loader/runtime can actually execute. Every other compatibility gate over a
# Python agent's declared ``api_version`` (currently just
# ``agent_package._check_compatibility``) must consume this exact set rather
# than maintaining its own hand-written list or comparing against
# ``AGENT_API_VERSION`` (the *newest* generation, not the full supported
# range) -- see the Phase 1 B1 remediation this set exists to anchor.
SUPPORTED_AGENT_API_VERSIONS = frozenset({1, 2})


def describe_supported_agent_api_versions() -> str:
    """Render :data:`SUPPORTED_AGENT_API_VERSIONS` for a user-facing message."""

    ordered = sorted(SUPPORTED_AGENT_API_VERSIONS)
    if len(ordered) == 1:
        return str(ordered[0])
    return ", ".join(str(version) for version in ordered[:-1]) + f" and {ordered[-1]}"


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
    # v3 research Phase 2 (experimental, ``bytefray-rules-3-alpha1`` only):
    # the bounded reach ``R`` this match's locality semantics enforce, so a
    # locality-aware agent can compute which displacements are legal instead
    # of discovering them by wasting actions. ``None`` under every Ruleset
    # with a stable identity. Additive and optional, exactly like
    # ``Observation.locus``; ``AGENT_API_VERSION`` is not bumped for it.
    locality_reach: int | None = None


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
    # v3 research Phase 2 (experimental, ``bytefray-rules-3-alpha1`` only):
    # this entrant's single arena execution locus -- the address its
    # bounded reach is centred on. ``None`` under every non-locality
    # Ruleset, which is every Ruleset with a stable identity, so no Agent
    # API v1 agent's behavior can change: the field did not exist for them
    # and carries no value for them now. Deliberately a *new* field rather
    # than a reinterpretation of ``pc``: ``pc`` is not an execution
    # location under any Ruleset (it is moved only by ``JUMP`` and is read
    # by no addressing path), and Phase 2 keeps it that way so a locality
    # experiment cannot be confused with a redefinition of an Agent API v1
    # observation field. See ``battle_engine.python_runtime``'s locality
    # section.
    locus: int | None = None


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

    # -- experimental, v3 research Phase 2 only ---------------------------
    #
    # Three additive members that are *not* part of the Agent API v1
    # contract documented in docs/AGENT_API_V1.md and are not usable under
    # any Ruleset with a stable identity. ``python_runtime.validate_action``
    # accepts them only under ``bytefray-rules-3-alpha1`` and rejects them
    # as invalid actions everywhere else, exactly as it already rejects any
    # unrecognized action; symmetrically, that Ruleset rejects the absolute
    # ``READ``/``WRITE`` above, so the v1 spelling of an absolute-address
    # operation never silently acquires relative meaning.
    #
    # ``AGENT_API_VERSION`` is deliberately NOT bumped for these: an agent
    # that never emits them observes and behaves exactly as before, and
    # Phase 2's job is to *measure* what incompatibility locality actually
    # requires, not to pre-declare an Agent API v2 from a guess.
    MOVE = "move"
    LOCAL_READ = "local_read"
    LOCAL_WRITE = "local_write"


@dataclass(frozen=True)
class AgentAction:
    """Exactly one validated battlefield operation returned by ``act``."""

    kind: ActionKind | ActionKindV2
    operand: int | None = None
    value: int | None = None


@runtime_checkable
class AgentV1(Protocol):
    """Structural lifecycle required from an Agent API v1 factory result."""

    def reset(self, context: MatchContext) -> None: ...

    def act(self, observation: Observation) -> AgentAction: ...


@dataclass(frozen=True)
class MatchContextV2:
    """Engine-controlled immutable match context supplied once at reset."""

    agent_id: str
    seed: int
    arena_size: int
    tick_limit: int
    rng: random.Random


@dataclass(frozen=True)
class ObservationV2:
    current_tick: int
    last_callback_tick: int
    previous_action_tick: int
    self_process_id: str
    self_anchor: int
    self_reach: int
    own_core_base: int
    own_core_size: int
    visible_enemy_anchor_addresses: tuple[int, ...]
    previous_action_applied: bool
    previous_read_value: int | None
    previous_read_owner: str | None


class ActionKindV2(str, Enum):
    READ = "read"
    WRITE = "write"
    MOVE = "move"


@dataclass(frozen=True)
class ProcessDeclaration:
    id: str
    reach: int
    share: float


@runtime_checkable
class AgentV2(Protocol):
    def reset(self, context: MatchContextV2) -> None: ...
    def declare_processes(self) -> list[ProcessDeclaration]: ...
    def act(self, observation: ObservationV2) -> AgentAction: ...


@dataclass(frozen=True)
class LoadedPythonAgent:
    """A fresh validated instance paired with engine-controlled metadata."""

    metadata: AgentMetadata
    instance: AgentV1 | AgentV2
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
    return f"_bytefray_agent_{digest}"


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
    # Agent source files are one-shot dynamic imports under a per-path
    # hashed module name (see _module_name) -- never re-imported, so a
    # bytecode cache buys nothing. Without suppressing it, every load
    # writes a __pycache__/*.pyc next to the source: harmless for a
    # user's own agents/<id>/ directory, but the bundled reference
    # opponent's agent.py (see agent_test._reference_opponent_spec)
    # lives inside the installed battle_engine package itself, so this
    # would otherwise leave stray bytecode in a source checkout and in
    # tools/check_wheel.py's release wheel on every ordinary use of
    # `agents test`/`validate`.
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:
        sys.modules.pop(module_name, None)
        raise AgentImportError(
            f"Failed importing Python agent source {source_path}: {type(exc).__name__}: {exc}",
            path=source_path,
        ) from exc
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


LOCAL_SOURCE_FINGERPRINT_VERSION = 1


def local_source_fingerprint(agent_dir: Path | None) -> str | None:
    """A versioned, deterministic fingerprint of every ``.py`` file local to
    one agent's own directory.

    A single entry-point file's digest alone only covers that one file; an
    imported local helper or nested local package living elsewhere in the
    same agent directory can change an agent's actual behavior while the
    entry point's own digest stays identical. This closes that gap by
    hashing every ``*.py`` file under ``agent_dir``, deterministically
    ordered by POSIX-style relative path so the result is stable across
    platforms and directory-listing order.

    Explicitly scoped and nothing more:

    * never walks outside ``agent_dir`` (a symlinked file/directory that
      resolves outside it is skipped, not followed);
    * never descends into ``__pycache__``;
    * never touches installed packages, system Python, or anything outside
      this one directory -- this is not general provenance.

    Returns ``None`` if ``agent_dir`` is absent, not a directory, or
    contains no local ``.py`` files to hash (e.g. a non-Python agent).
    """

    if agent_dir is None or not agent_dir.is_dir():
        return None
    base = agent_dir.resolve()
    entries: list[tuple[str, bytes]] = []
    for candidate in base.rglob("*.py"):
        if "__pycache__" in candidate.parts:
            continue
        try:
            resolved = candidate.resolve()
            resolved.relative_to(base)
        except (OSError, ValueError):
            continue  # a symlink escaping agent_dir -- never followed
        if not resolved.is_file():
            continue
        try:
            content = resolved.read_bytes()
        except OSError:
            continue
        entries.append((candidate.relative_to(base).as_posix(), content))
    if not entries:
        return None
    entries.sort(key=lambda item: item[0])
    hasher = hashlib.sha256()
    hasher.update(str(LOCAL_SOURCE_FINGERPRINT_VERSION).encode("ascii"))
    for relative_path, content in entries:
        hasher.update(b"\0")
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(content).digest())
    return hasher.hexdigest()


def load_python_agent(agent_spec: Any) -> LoadedPythonAgent:
    """Import, construct, and structurally validate one fresh Python agent."""

    if getattr(agent_spec, "kind", None) != "python":
        raise AgentContractError(
            f"Agent {getattr(agent_spec, 'name', '<unknown>')!r} is not a Python agent.",
            path=getattr(agent_spec, "dir", None),
        )
    api_version = getattr(agent_spec, "api_version", None)
    if api_version not in SUPPORTED_AGENT_API_VERSIONS:
        raise UnsupportedAgentAPIVersionError(
            f"Python agent {agent_spec.name!r} declares API version {api_version!r}; "
            f"Bytefray supports versions {describe_supported_agent_api_versions()}.",
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
    protocol: type[AgentV1 | AgentV2]
    required_methods: tuple[str, ...]
    if api_version == 2:
        protocol = AgentV2
        required_methods = ("reset", "declare_processes", "act")
    else:
        protocol = AgentV1
        required_methods = ("reset", "act")
    missing = [
        name for name in required_methods if not callable(getattr(instance, name, None))
    ]
    if missing or not isinstance(instance, protocol):
        detail = ", ".join(missing) or f"AgentV{api_version} lifecycle methods"
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
    "LOCAL_SOURCE_FINGERPRINT_VERSION",
    "SUPPORTED_AGENT_API_VERSIONS",
    "ActionKind",
    "ActionKindV2",
    "AgentAction",
    "AgentContractError",
    "AgentFactoryError",
    "AgentImportError",
    "AgentManifestError",
    "AgentMetadata",
    "AgentSourceError",
    "AgentV1",
    "AgentV2",
    "AgentValidationError",
    "LoadedPythonAgent",
    "MatchContext",
    "MatchContextV2",
    "Observation",
    "ObservationV2",
    "ProcessDeclaration",
    "UnsupportedAgentAPIVersionError",
    "describe_supported_agent_api_versions",
    "load_python_agent",
    "local_source_fingerprint",
    "parse_entry_point",
]
