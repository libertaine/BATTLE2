# Installation Guide

## Windows (no Python required)
1. Download the latest `windows-exes` artifact from releases/CI.
2. Run `BattleAgentDesigner.exe`.
3. Optionally, run `BattleReplayViewer.exe` to view replays directly.

## Windows (development)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[replay,designer]"
battle2 design
