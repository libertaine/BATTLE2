# BATTLE2 Agent Authoring Guide

This guide describes the current implementation on the v0.3 foundation branch. BATTLE2 v0.2.0 remains the released baseline. Python-agent loading is new foundation work and is not yet connected to match execution.

## Choose an agent form

| Form | Current status | Execution path |
|---|---|---|
| Built-in | Supported | A known name is assembled into BATTLE VM bytecode. |
| Blob | Supported | `model.blob` bytes are loaded directly into the BATTLE VM. |
| Python | Loadable and validatable; not executable in matches | `agent.py` is imported and its factory result is checked against Agent API v1. |
| Redcode | Supported as a separate mode | A `.red` or `.load` warrior is passed to pMARS. |

These forms do not share one runtime. Built-ins and blobs use the native BATTLE VM. Redcode uses pMARS. Python runtime gameplay is not implemented yet.

## Agent directories and discovery

User agents live under the configured writable data root:

```text
agents/
  my_agent/
    agent.yaml
    agent.py       # Python form
    model.blob     # Blob form
```

The directory name is the current discovery ID and the name used to resolve an agent. A manifest can supply a display label, but it does not rename the directory key. `battle2 agents` lists discovered directories and initializes missing starter manifests first.

Manifests may contain JSON or YAML mappings. JSON is tried first; YAML requires the normal PyYAML runtime dependency. `defaults`, when present, must be a mapping.

## Built-in agents

The current built-in names are `runner`, `writer`, `bomber`, `flooder`, `spiral`, and `seeker`. A starter directory such as `agents/runner/` may contain only a manifest: because its directory name matches a built-in, `battle2 run --a-type runner ...` uses the built-in assembler.

Built-ins execute as mutable bytecode under the native VM rules in [RULES.md](RULES.md). Some current built-ins have implementation quirks documented there.

## Blob agents

A discovered directory containing `model.blob` is classified as a blob agent unless its manifest declares another `kind`. The file is loaded as raw BATTLE VM bytecode and starts at the slot's configured entry address.

```text
agents/
  my_blob/
    agent.yaml
    model.blob
```

A minimal manifest is:

```yaml
name: my_blob
display: My Blob Agent
```

The CLI also retains explicit blob flags and legacy environment-based blob configuration. Those compatibility inputs do not change the bytes' VM semantics.

## Python agents: current foundation contract

Python agents should use an explicit manifest:

```text
agents/
  example_agent/
    agent.yaml
    agent.py
```

`agent.yaml`:

```yaml
kind: python
api_version: 1
entrypoint: agent.py:create_agent
name: example_agent
display: Example Agent
version: 1.0.0
defaults: {}
```

`agent.py`:

```python
from battle_engine.agent_api import AgentAction, MatchContext, Observation


class ExampleAgent:
    def reset(self, context: MatchContext) -> None:
        self.agent_id = context.agent_id
        self.seed = context.seed

    def act(self, observation: Observation) -> AgentAction:
        # AgentAction has no gameplay fields yet.
        return AgentAction()


def create_agent() -> ExampleAgent:
    return ExampleAgent()
```

This example passes current discovery, import, factory, and structural validation. The engine does not call `reset()` or `act()` during a match yet.

### Manifest fields

| Field | Python-agent status | Meaning |
|---|---|---|
| `kind` | Recommended; inferred when `agent.py` exists | Must be `python` for this form. Accepted discovery kinds are `builtin`, `blob`, and `python`. |
| `api_version` | Required to load | Must be integer `1`. Missing or other values are rejected by the v1 loader. |
| `entrypoint` | Optional when `agent.py` exists | Uses `relative/path.py:factory_name`; discovery infers `agent.py:create_agent` for a Python directory with that file. |
| `name` | Optional metadata | Must be a non-empty string if supplied. The directory name remains the engine-controlled discovery ID. |
| `display` | Optional | Human-readable label; falls back to manifest `name`, then directory name. |
| `version` | Optional | Non-empty string. Loaded metadata uses `"0"` when omitted. |
| `defaults` | Optional | Mapping retained in `AgentSpec`; no Python gameplay parameter semantics exist yet. |

### Factory and instance requirements

The configured factory must:

1. Exist in the referenced Python file.
2. Be callable without arguments.
3. Return an object implementing `reset(context)` and `act(observation)` as methods.

Validation is structural. An agent does not need to inherit from a BATTLE2 base class. Each `load_python_agent()` call invokes the factory again and returns a fresh object. BATTLE2 supplies `LoadedPythonAgent.metadata`; user code does not control the resolved agent ID by attaching its own metadata attribute.

The loader uses a runtime-checkable protocol. It validates structural attribute presence, not signatures or returned actions. On current Python, an object with non-callable attributes named `reset` and `act` can satisfy that runtime check; authors must still implement real methods. Runtime calls are not implemented.

### Module and path handling

The source path is resolved relative to the agent directory. It must:

- remain inside that directory;
- refer to a `.py` file; and
- exist as a regular file.

The loader imports from the resolved path under a generated module name derived from that path. Two different directories may both contain `agent.py` without colliding in `sys.modules`.

### Validation failures

Expected failures include:

- malformed JSON/YAML or a non-mapping manifest;
- incorrectly typed `kind`, `api_version`, `name`, `version`, `entrypoint`, or `defaults`;
- unsupported or missing API version;
- an entry point that escapes the agent directory;
- a missing or non-`.py` source file;
- Python syntax errors or import-time exceptions;
- a missing/non-callable factory;
- a factory exception; or
- a returned object missing the required `reset` or `act` attributes.

The loader reports typed `AgentValidationError` subclasses. See [AGENT_API_V1.md](AGENT_API_V1.md) for the diagnostic codes.

### Legacy Python discovery

A directory containing `agent.py` but no `agent.yaml` is still discovered for v0.2 compatibility. It is inferred as `kind: python` with entry point `agent.py:create_agent`, but its API version is unknown. The Agent API v1 loader therefore rejects it until an explicit `api_version: 1` manifest is added.

Discovery does not imply match execution. The current CLI still requires a built-in implementation or blob for a native VM match.

## Redcode/pMARS warriors

Redcode uses a separate backend:

```bash
battle2 run --mode redcode94 --red-a warriors/a.red --red-b warriors/b.red
```

pMARS resolution and platform packaging are described in the installation documentation. Redcode does not use Agent API v1, `model.blob`, or the BATTLE VM instruction set.

## Current limitations / v0.3 work in progress

The following Python-agent behavior is **not yet implemented or finalized**:

- Python runtime execution;
- observation contents beyond the placeholder `tick` field;
- the action vocabulary (`AgentAction` is currently an empty marker);
- arena visibility;
- ownership visibility;
- action budgets;
- VM-equivalent action cost;
- Python-versus-VM scheduling and fairness;
- runtime exception and forfeit policy; and
- timeout containment.

Do not build an agent around assumed values for these items. The stable work in this slice is discovery, explicit API versioning, path-based loading, factory construction, fresh instances, engine-controlled identity, and typed validation.
