
Project to determine feasibility of using LLM to assist me in creation of a project.


````markdown
# BATTLE2

**BATTLE2** is a Python-based framework and simulation engine for Core War–style AI competitions. It supports:

- Native Python agents  
- Precompiled binary “blob” agents  
- Integration with pMARS (Redcode) for interop  
- Replay viewing and agent design tools  

This project is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/libertaine/BATTLE2?label=latest%20release)](https://github.com/libertaine/BATTLE2/releases)
[![Changelog](https://img.shields.io/badge/Changelog-view-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


---

## 🔧 Quick Start

### Clone & Install (dev mode)

```bash
git clone https://github.com/libertaine/BATTLE2.git
cd BATTLE2
python -m venv venv
source venv/bin/activate     # or `.\venv\Scripts\activate` on Windows
pip install -e .             # engine, headless replay, and agent discovery
pip install -e ".[replay]"  # optional Pygame replay viewer
pip install -e ".[designer]" # optional PySide6 designer
````

> If you don’t need GUI tools, you can install just the core with:
>
> ```bash
> pip install -e .
> ```

---

## 📦 Downloads

**Latest Release:** [v0.1.0 (Pre-release)](https://github.com/libertaine/BATTLE2/releases/tag/v0.1.0)

Choose one of the options below:

| Type | File | Description |
|------|------|--------------|
| 🧰 **Installer** | [BATTLE2-Setup-0.1.0.exe](https://github.com/libertaine/BATTLE2/releases/download/v0.1.0/BATTLE2-Setup-0.1.0.exe) | Installs under `C:\Program Files\BATTLE2` (recommended) |
| 💼 **Portable ZIP** | [BATTLE2-portable.zip](https://github.com/libertaine/BATTLE2/releases/download/v0.1.0/BATTLE2-portable.zip) | Unpack and run from any folder (no installation) |

---

### Default Install Paths
| Component | Location |
|------------|-----------|
| Binaries | `C:\Program Files\BATTLE2\bin\` |
| Data root | `%ProgramData%\BATTLE2\` |
| Replays | `%ProgramData%\BATTLE2\runs\_loose\` |
| Agents | `%ProgramData%\BATTLE2\resources\agents\` |

Environment variable `BATTLE2_ROOT` is automatically set to the data root during installation.
The legacy `BATTLE_ROOT` name remains supported when `BATTLE2_ROOT` is unset. If
both are defined, `BATTLE2_ROOT` takes precedence.

> **Note for Linux/macOS Users:** Install paths and commands may differ. Use `sudo apt install pmars` (or equivalent) for Redcode support.

### CLI Usage

```bash
battle2 --help
battle2 run --help
```

Key options:

* `--ticks N`: number of simulation cycles
* `--arena SIZE`: memory arena size
* `--a-type NAME` / `--b-type NAME`: select discovered or built-in agents
* `--list-agents`: show available agents
* `--mode redcode94`: engage pMARS mode (requires `--red-a` and `--red-b`)
* Other flags control agent selection, instruction quotas, weighting, etc.

Primary commands are:

```bash
battle2 run       # execute a match
battle2 replay    # consume an existing replay
battle2 design    # launch the optional PySide6 designer
battle2 agents    # list discovered agents
```

The v0.1 command names `battle-cli`, `match-runner`, and
`battle-agent-designer` remain compatibility wrappers throughout v0.2. Module
execution is also available:

```bash
python -m battle_engine --help
```

---

## 🧠 Agent Formats & Execution Modes

### Supported Agent Formats

| Type    | File         | Execution Path            | Notes                                    |
| ------- | ------------ | ------------------------- | ---------------------------------------- |
| Python  | `agent.py`   | Discovered as source      | Execution is not wired into the v0.1 CLI |
| Blob    | `model.blob` | Loaded directly by engine | Faster, minimal runtime                  |
| Redcode | `.red/.asm`  | Via pMARS integration     | Compatible with existing Core War agents |

* A directory containing **Python** source is discoverable, but native v0.1 CLI
  matches require a blob or built-in implementation.
* Use **blob** when you want to ship just the low-level compiled version.
* The **Redcode** mode allows interop with legacy Core War agents (via pMARS). Use `--mode redcode94`.

### Agent Discovery Structure

Under the `agents/` directory:

```
agents/
  my_agent/
    agent.yaml
    agent.py
    model.blob  # optional
  ...
```

The `agent.yaml` defines metadata (name, display name, required blobs, dependencies). If `model.blob` exists, it will be preferred in binary execution.

Use:

```bash
battle2 agents
```

to see all discovered agents.

---

## 🎮 GUI Tools (optional)

### Tools

| Executable | Role | Tech |
|-----------|------|------|
| battle-agent-designer.exe | Configure & run matches, open replays | PySide6 (Qt) |
| match_runner.exe          | Live match visualizer (grid/ticks)     | Pygame |
| battle-replay-viewer.exe  | View and analyze match replays         | Pygame |



---

## ⚙ Integration with pMARS (Redcode mode)

BATTLE2 supports pMARS (Redcode) for interoperability:

```bash
battle2 run --mode redcode94 --red-a path/to/A.red --red-b path/to/B.red --ticks 800
```

* The backend spawns `pmars` with appropriate flags to evaluate the match.
* The output includes a `summary.json` indicating winner, return code, and parameters.
* You need to install `pmars` binaries (bundled or via your system). The license of pMARS must be respected (typically GPLv2). See `third_party_licenses/` in this repo for full details.

---

## 🧪 First-Run Example

1. Clone & install (see **Quick Start** above).

2. View available agents:

   ```bash
   battle2 agents
   ```

3. Run a match with default agents:

   ```bash
   battle2 run --ticks 500 --arena 2048 --a-type my_agent --b-type other_agent
   ```

4. Optional: launch viewer to inspect results:

   ```bash
   battle2 replay --replay path/to/replay.jsonl --renderer pygame
   ```

---

## 🚀 Packaging for Windows

The root package exposes the primary `battle2` dispatcher and retains legacy
commands through `battle_engine.legacy` compatibility wrappers.
For Windows packaging, two approaches are viable:

* **PyInstaller + Inno Setup**

  * Build executables for `battle-cli`, `battle-agent-designer`, and `replay-viewer`
  * Use Inno Setup script (`.iss`) to bundle binaries, agents folder, pmars, etc.
  * Add Start Menu shortcuts, add to PATH optionally

* **MSI via WiX Toolset**

  * More control (repair, feature sets), suitable for enterprise use
  * You can author features/components for `bin/`, `agents/`, `pmars/`

In both cases, rely on the `console_scripts` wrappers and package metadata from `pyproject.toml`.

---

## 🧷 Developer Notes & Contribution

* The project uses a **multi-root source layout**:

  * `engine/src/` (battle engine core)
  * `client/src/` (GUI / client tooling)

* Packaging via `pyproject.toml` uses `tool.setuptools.packages.find` to detect both roots.

* Keep asset/dataset files in package directories (e.g. `warriors/`, `data/`) so they get included in installs.

* CI installs the project with its test/build extras, runs the complete suite,
  and builds the existing Windows executables.

If you are migrating from the prior version, check the following:

* Your old agent files must be relocated under `agents/` with a matching directory structure
* `.env` has been removed; use environment variables or CLI options instead
* The wrapper ensures existing CLI logic carries forward unchanged

Contributions welcome — open a PR or issue. Thanks for checking out BATTLE2!

```

## 🧰 Development / Build from Source

Developers can build and test BATTLE2 directly from source.
Requires **Python 3.10 or newer** and a current pip.

```bash
# 1️⃣ Clone the repository
git clone https://github.com/libertaine/BATTLE2.git
cd BATTLE2

# 2️⃣ Create and activate a virtual environment
py -3.10 -m venv .venv        # any supported Python 3.10+
.venv\Scripts\activate        # Windows PowerShell
# or
source .venv/bin/activate     # Linux / macOS

# 3️⃣ Install dependencies
pip install -U pip setuptools wheel
pip install -e ".[dev,replay,designer]"

# 4️⃣ Run the engine or GUI directly
python -m app.match_runner     # Pygame match window
python -m app.agent_designer   # PySide6 designer GUI
python -m battle_engine --help

# 5️⃣ (Optional) Build executables
pyinstaller -y --clean --name battle-cli --console ^
  --paths engine\src --collect-all battle_engine -m battle_engine.cli

pyinstaller -y --clean --name match_runner --windowed ^
  app\match_runner.py

pyinstaller -y --clean --name battle-agent-designer --windowed ^
  app\agent_designer.py
```

> 💡 *Note:* For Windows packaging, use **Inno Setup 6** and compile
> `tools\installer.iss` to create `BATTLE2-Setup-x.y.z.exe`.
> This installer copies executables to `C:\Program Files\BATTLE2`
> and shared data to `%ProgramData%\BATTLE2`.

The legacy executable helper scripts use Python 3.11 as the reproducible release
build interpreter. This does not change the package runtime requirement of
Python 3.10 or newer; CI validates the minimum version on Python 3.10.

---

### Directory Overview

```
BATTLE2/
├── app/
│   ├── agent_designer.py      # PySide6 GUI
│   ├── match_runner.py        # Pygame visualizer
│   └── main.py                # GUI entry and window setup
├── engine/
│   └── src/battle_engine/     # Simulation core & CLI
├── client/
│   └── src/battle_client/     # Renderer and interface code
├── tools/
│   ├── build_executables.ps1  # Build helper script
│   ├── installer.iss          # Inno Setup installer definition
│   └── smoke_after_install.ps1
├── examples/                  # Sample agents and match configs
├── agents/                    # Agent definitions and binaries
├── warriors/                  # Sample Redcode (.red) files
├── pmars/                     # pMARS binaries for Redcode interop
├── LICENSE
├── README.md
└── pyproject.toml
```

---

### 🧪 Quick Validation

To verify a successful build and installation:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_after_install.ps1 -AppDir "C:\Program Files\BATTLE2"
```

This runs a minimal smoke test of all installed executables to ensure:

* `battle-cli.exe` runs headless matches
* `match_runner.exe` opens the Pygame window
* `battle-agent-designer.exe` opens the Qt interface

---

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and upcoming features.
