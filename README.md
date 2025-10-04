
Project to determine feasibility of using LLM to assist me in creation of a project.

# BATTLE

BATTLE is an experimental battle engine and client framework for running,
visualizing, and analyzing agent-based competitions. It supports configurable
rulesets, round-robin tournaments, replay capture, and multiple rendering backends.

---

## Features

- **Battle Engine**
  - Configurable core size, arena, and tick count
  - Multiple scoring modes (`survival`, `score`, `score_fallback`)
  - Supports multiple agents with round-robin elimination
  - Replay export to JSON for analysis or replay

- **Agents**
  - Built-in sample agents (`runner`, `writer`, `bomber`, `flooder`, `spiral`, `seeker`)
  - Extensible YAML + code definition system for custom agents
  - Blob/model support for advanced agents

- **Visualization**
  - CLI text output
  - Optional Pygame renderer for real-time grid display
  - Replay viewer executable (Windows builds available with PyInstaller)

- **Cross-Platform**
  - Tested on Linux (Ubuntu) and Windows 10/11
  - Python 3.11 recommended

---

## Installation

### Prerequisites
- Python 3.11+
- `pip install -r requirements.txt`
- Optional: `pygame` for live visualization

### Clone
```bash
git clone https://github.com/<your-org>/BATTLE.git
cd BATTLE
````

---

## Usage

### Run a Simple Match

```bash
python -m battle_engine.cli --arena 512 --ticks 200 \
  --a-type runner --b-type bomber
```

### With Pygame Renderer

```bash
python -m battle_engine.cli --pygame --arena 512 --ticks 200 \
  --a-type runner --b-type seeker
```

### Replay Viewer (Windows example)

```powershell
.\dist\windows\BattleReplayViewer.exe
```

### Example Tournament

```bash
python tools/tournament.py --rounds 5 --arena 2048 --ticks 80000
```

---

## Project Structure

```
BATTLE/
├── engine/               # Core battle engine
│   └── src/battle_engine/
├── agents/               # Agent definitions & blobs
├── runs/                 # Saved run logs and summaries
├── tools/                # Utilities (replay viewer, agent designer, tournament runner)
├── dist/                 # Built executables (Windows/Linux)
└── README.md             # This file
```

---

## Development

### Testing

```bash
./tools/smoke_test.sh
```

Runs a set of quick validation battles across agents.

### Adding a New Agent

1. Create an `agents/<name>/agent.yaml`
2. Add optional model blob under `agents/<name>/`
3. Update engine registry if needed

### Packaging (Windows Example)

```powershell
pyinstaller --noconfirm --clean `
  --workpath build\windows `
  --distpath  dist\windows `
  tools\agent_designer.spec
```

---

## Roadmap

* [ ] Expand agent library
* [ ] Add networked multiplayer mode
* [ ] Web-based replay viewer
* [ ] Configurable AI training hooks
* [ ] CI smoke test integration



### Battle Agent Designer

The **Battle Agent Designer** is a graphical utility for creating and editing agent configurations. It allows quick setup of agent metadata (`name`, `display`, parameters, blob paths) without manually editing YAML files.

#### Status

* Currently in **beta**
* Core functionality: create/edit agent YAML files, assign blobs, validate config
* Built with Python + PyQt (packaged via PyInstaller for Windows)
* Linux runs directly with Python environment

#### Run from Source

```bash
# Linux / macOS
python tools/agent_designer.py
```

```powershell
# Windows (with virtualenv active)
python .\tools\agent_designer.py
```

#### Run Packaged Executable (Windows)

```powershell
.\dist\windows\BattleReplayViewer.exe
.\dist\windows\BattleAgentDesigner.exe
```

#### Workflow

1. Launch the designer
2. Fill in **agent name**, **display label**, and optional blob/model path
3. Save, which generates or updates `agents/<agent>/agent.yaml`
4. Use new agent directly in battles:

   ```bash
   python -m battle_engine.cli --a-type <agent> --b-type runner
   ```


## License

GPLv3 — see [LICENSE](LICENSE).

