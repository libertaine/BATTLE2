# Bytefray Agent Designer (PySide6)

The Agent Designer is Bytefray's desktop workflow for running matches,
developing Python agents, inspecting canonical artifacts, and opening the
Pygame replay viewer. It delegates simulation, agent validation/testing,
evaluation history, revisions, and package operations to the authoritative
`battle_engine` services.

## Main UI

- **Simple** tab: choose two homogeneous agents, run/stop a match, inspect the
  result, and open its replay.
- **Advanced** tab: configure matches and per-agent parameters, browse replays,
  and inspect canonical result artifacts.
- **Agent Development** tab: create, validate, and development-test Agent API v1
  Python agents; inspect traces/replays; run evaluations; and export
  `.bytefray-agent` packages.
- **Tools** menu: run tournaments, browse/compare evaluation history, inspect or
  import agent packages, and open the latest output directory.

Long-running or agent-code-executing work is launched out of process. Read-only
history/revision inspection and bounded package/scaffold filesystem operations
run in process. Canonical result, replay, trace, evaluation, revision, and
package formats remain owned by `battle_engine`.

## Run from a source checkout

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[replay,designer]"
bytefray-agent-designer
```

Without installing the console entry point:

```bash
python -m app.agent_designer
```

`BYTEFRAY_ROOT` selects the writable data root; see `INSTALL.md` for default
and portable-install behavior. Agents are discovered under
`<data-root>/agents/<agent-id>/` from their `agent.yaml` manifests. The
directory/discovery id and human-readable display name may differ.

The authoritative interactive release checklist is
[`docs/MANUAL_SMOKE_TESTS.md`](../docs/MANUAL_SMOKE_TESTS.md); GUI-marked pytest
coverage complements that checklist but is not a human walkthrough.
