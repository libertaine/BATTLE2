# Agent API v1 Technical Contract

This document describes `battle_engine.agent_api` as currently implemented. It is a loading and validation contract, not a completed gameplay API.

Status labels used below:

- **CURRENT**: implemented and tested now.
- **PROVISIONAL**: present in the API but intentionally incomplete.
- **NOT YET IMPLEMENTED**: no match-runtime behavior exists.

## Version constant

```python
AGENT_API_VERSION = 1
```

**CURRENT.** A Python `AgentSpec` must have `api_version == 1` to load. A missing version is not silently treated as version 1.

## Public types

### `AgentMetadata`

```python
@dataclass(frozen=True)
class AgentMetadata:
    agent_id: str
    name: str
    version: str
    api_version: int = AGENT_API_VERSION
```

**CURRENT.** The loader creates this immutable value from the resolved `AgentSpec`:

- `agent_id` is the agent directory/discovery name.
- `name` is the resolved display label.
- `version` is the manifest version or `"0"` when absent.
- `api_version` is the validated integer API version.

This is engine-controlled metadata. Metadata attributes supplied by the returned agent instance do not replace it.

### `MatchContext`

```python
@dataclass(frozen=True)
class MatchContext:
    agent_id: str
    seed: int
```

**PROVISIONAL.** The immutable type and these two fields exist. The engine does not construct it for Python agents or call `reset()` during matches yet. Additional context may be required when runtime execution is designed.

### `Observation`

```python
@dataclass(frozen=True)
class Observation:
    tick: int
```

**PROVISIONAL.** This is only a minimal immutable envelope for structural typing. It does not promise arena bytes, ownership, scores, agent states, visibility, or timing semantics. No match code produces it.

### `AgentAction`

```python
@dataclass(frozen=True)
class AgentAction:
    pass
```

**PROVISIONAL.** It is an empty marker. No read, write, movement, VM-operation, cost, or scheduling semantics exist.

### `AgentV1`

```python
@runtime_checkable
class AgentV1(Protocol):
    def reset(self, context: MatchContext) -> None: ...
    def act(self, observation: Observation) -> AgentAction: ...
```

**CURRENT for structural validation; NOT YET IMPLEMENTED for execution.** The factory result must expose attributes named `reset` and `act`. Because validation uses a runtime-checkable structural protocol, inheritance is unnecessary.

Runtime protocol checking confirms structural attribute presence. It does not inspect annotations, enforce the exact Python signature, call either method, or validate an `AgentAction` return value in this foundation slice. On the current runtime, non-callable attributes with those names can pass `isinstance(instance, AgentV1)`; real methods are an authoring requirement but are not completely enforced by the loader yet.

### `LoadedPythonAgent`

```python
@dataclass(frozen=True)
class LoadedPythonAgent:
    metadata: AgentMetadata
    instance: AgentV1
    source_path: Path
    entry_point: str
```

**CURRENT.** This immutable wrapper pairs engine-controlled identity with a fresh validated factory result and its resolved source information.

## Manifest-to-`AgentSpec` mapping

A normal explicit Python manifest is:

```yaml
kind: python
api_version: 1
entrypoint: agent.py:create_agent
name: example_agent
display: Example Agent
version: 1.0.0
defaults: {}
```

Discovery stores `kind`, `api_version`, `version`, resolved `source_path`, `entry_point`, `defaults`, and the original manifest mapping on `AgentSpec`.

The current discovery ID is the directory name. Manifest `name` contributes to display fallback and is validated, but does not replace that ID.

When an `agent.py` exists without an explicit entry point, discovery infers `agent.py:create_agent`. This supports legacy discovery; it does not infer API version 1.

## Loading algorithm

`load_python_agent(spec)` performs these steps:

1. Require `spec.kind == "python"`.
2. Require `spec.api_version == AGENT_API_VERSION`.
3. Require an entry point.
4. Parse `relative/path.py:factory`.
5. Resolve the path against `spec.dir`.
6. Reject paths outside the agent directory.
7. Require a `.py` suffix and existing file.
8. Generate a private module name from the SHA-256 digest of the resolved path.
9. Import that file using `importlib.util.spec_from_file_location`.
10. Resolve and call the named zero-argument factory.
11. Structurally check the result against `AgentV1` (`reset` and `act` attributes).
12. Return `LoadedPythonAgent` with engine-controlled metadata.

Each call creates a new module object, executes the module, and calls the factory. Each successful call therefore produces a fresh agent instance. The generated module name is path-specific, preventing two separate `agent.py` files from sharing the ordinary global name `agent`.

An import that fails is removed from `sys.modules`. A successful imported module remains registered under its generated private name and may be replaced by a later load from the same path.

## Entry-point restrictions

The entry point must contain exactly the information represented by:

```text
relative/path.py:factory_name
```

The implementation splits on the first colon. The factory portion must be a valid Python identifier. The resolved source must remain beneath the agent directory and end in `.py`.

Absolute paths and `..` paths that resolve outside the directory are rejected. Package/module dotted notation such as `package.module:create_agent` is not the current format.

## Validation errors

All loader/discovery validation errors derive from `AgentValidationError`, which derives from `ValueError`. Each instance may carry a `path` attribute.

| Exception | `code` | Current use |
|---|---|---|
| `AgentValidationError` | `agent_validation_failed` | Base diagnostic type. |
| `AgentManifestError` | `agent_manifest_invalid` | Manifest parsing or field validation. |
| `UnsupportedAgentAPIVersionError` | `agent_api_version_unsupported` | Missing or unsupported Python API version. |
| `AgentSourceError` | `agent_source_invalid` | Entry-point syntax, path containment, suffix, or missing source. |
| `AgentImportError` | `agent_import_failed` | Syntax and import-time failures. |
| `AgentFactoryError` | `agent_factory_failed` | Missing/non-callable factory or factory exception. |
| `AgentContractError` | `agent_contract_invalid` | Non-Python spec or result missing lifecycle methods. |

Messages include the relevant agent, entry point, source path, and original exception type where applicable. They are intended to be safe for CLI and GUI presentation; callers may also branch on exception class or `code`.

## Relationship to `NativeMatchService`

`NativeMatchService` currently accepts resolved `MatchEntrant` values containing VM bytecode. It does not accept `LoadedPythonAgent`, call `reset()` or `act()`, or define Python scheduling. The two foundation pieces are intentionally separate until gameplay and fairness rules are decided.

## Compatibility promise during v0.3

The following behavior is intentional and is the part authors may reasonably rely on during v0.3 development:

- explicit API version checking;
- `relative/path.py:factory` entry points;
- containment of source paths within an agent directory;
- path-derived private module names;
- zero-argument factory construction;
- a fresh object for every load;
- structural `reset`/`act` validation;
- engine-controlled `LoadedPythonAgent.metadata`; and
- typed diagnostics.

Gameplay semantics remain pre-1.0 design work. Do not assume that the placeholder fields of `MatchContext`, `Observation`, or `AgentAction` are complete or final. In particular, their existence does not promise arena visibility, ownership visibility, action budgets, VM cost equivalence, mixed scheduling, exception forfeits, or timeout behavior.
