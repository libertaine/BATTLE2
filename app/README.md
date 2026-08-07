## README.md
```markdown
# Battle Agent Designer (PySide6)

A small PySide6 desktop app that lets you pick agents, run the supported **headless engine** workflow, inspect its canonical result/replay artifacts, and open the **Pygame** renderer to view the replay.

## Features
- **Simple / Advanced** modes with a toolbar toggle.
- Simple mode: quick agent pickers, grid/tick presets, live log, Run/Stop/Open.
- Advanced mode tabs: Match Setup, Agent Params (per-agent JSON), Replay Browser, Results (shows canonical result status).
- **File-only workflow**: engine writes `runs/_loose/result.json` and `replay.jsonl`, plus compatibility `summary.json`.
- VM-vs-VM and Python-vs-Python matches; mixed runtime selections are rejected.
- Minimal homogeneous round-robin launcher under **Tools → Run Tournament…**.
- Runtime/API/schema details under **Help → About Bytefray**.
- Cross‑platform: sets `PYTHONPATH` using `:` (POSIX) / `;` (Windows).

## Requirements
- Python 3.10+
- Existing repo layout at `<BATTLE_ROOT>`:
  - `engine/src/battle_engine/cli.py`
  - `client/src/battle_client/cli.py` (module entry `python -m battle_client.cli`)

## How to run
```bash
# From <BATTLE_ROOT>
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .

# Optional: set BATTLE_ROOT explicitly
# export BATTLE_ROOT=$(pwd)  # Windows PowerShell: $env:BATTLE_ROOT=(Get-Location).Path

battle-agent-designer
```

If you prefer running without installing:
```bash
python -m app.main
```

### Agent discovery
Place agents under `<BATTLE_ROOT>/agents/<agent_name>/`. The app will scan `agent.yaml` (JSON allowed) for `name` and `display`. If missing, it falls back to `agents/<name>/agent.py`.

### Notes
- Engine params are passed via CLI; optional per-agent JSON is exported to env vars `BATTLE_AGENT_A_PARAMS_JSON` and `BATTLE_AGENT_B_PARAMS_JSON` if present.
- **Open Last Replay** launches: `python -m battle_client.cli --replay <replay.jsonl> --renderer pygame --tick-delay 0.02` with proper `PYTHONPATH`.

## Acceptance tests (manual)
1. **Mode toggle**: Click toolbar **Simple/Advanced** — panels switch; window size stays stable.
2. **Run (Simple)**: Use defaults, click **Run Match**. After engine exits, **Results** tab shows `winner` and other fields; **Open Last Replay** becomes enabled and opens Pygame.
3. **Invalid Agent Params**: In **Advanced → Agent Params**, insert broken JSON and click **Validate JSON** — a clear error dialog is shown and run is blocked unless fixed/cleared.
4. **Windows/Linux PYTHONPATH**: Verify environment uses `;` on Windows and `:` on Linux/macOS (manual check in code or by printing `PYTHONPATH` in engine).
```

---
