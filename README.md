
# BATTLE2

**BATTLE2** is a Python-based framework and simulation engine for Core War–style AI competitions. It supports:

- Python agent discovery, Agent API v1 validation, and experimental Python-vs-Python matches
- Precompiled binary “blob” agents  
- Integration with pMARS (Redcode) for interop  
- Replay viewing and agent design tools  

This project is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/libertaine/BATTLE2?label=latest%20release)](https://github.com/libertaine/BATTLE2/releases)
[![Changelog](https://img.shields.io/badge/Changelog-view-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## AI-Assisted Development

BATTLE2 began partly as an experiment in whether large language models could contribute meaningfully to the creation of a real software project. It has evolved into an exploration of AI-assisted, human-directed software development. AI tools are used for implementation, repository exploration, debugging, architecture critique, test generation, documentation, code review, and independent second opinions.

Development is incremental and repository-driven. Goals and architecture are established through human direction and AI-assisted analysis; coding agents work against branches and the current source tree; failures are reproduced; tests are run; and diffs are reviewed before changes are accepted. Different tools and models may also be used independently to challenge implementations or review one another's conclusions.

AI-generated code and review findings are treated as proposals, not authority. Claims are checked against executable behavior, tests, the current repository, and other reproducible evidence; findings that cannot be confirmed are rejected. Human judgment remains responsible for project direction, requirements, architecture, scope, tradeoffs, and deciding when a change is ready to enter the project.


---

## Documentation

- [Agent Authoring Guide](docs/AGENT_AUTHORING.md)
- [Agent API v1 Technical Contract](docs/AGENT_API_V1.md)
- [Current Native VM Rules Reference](docs/RULES.md)
- [Canonical Result Schema](docs/RESULT_SCHEMA.md)
- [Replay Schema](docs/REPLAY_SCHEMA.md)

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
```

> If you don’t need GUI tools, you can install just the core with:
>
> ```bash
> pip install -e .
> ```

---

## 📦 Downloads

**Current release:** [BATTLE2 v0.2.0](https://github.com/libertaine/BATTLE2/releases/tag/v0.2.0).
The v0.1 downloads are historical and have been superseded.

Choose one of the options below:

| Type | File | Description |
|------|------|--------------|
| 🧰 **Windows installer** | [BATTLE2-Setup-0.2.0.exe](https://github.com/libertaine/BATTLE2/releases/download/v0.2.0/BATTLE2-Setup-0.2.0.exe) | Installs under `C:\Program Files\BATTLE2` |
| 💼 **Portable Windows applications** | [BATTLE2-0.2.0-windows-exes.zip](https://github.com/libertaine/BATTLE2/releases/download/v0.2.0/BATTLE2-0.2.0-windows-exes.zip) | Complete onedir layouts for all five executables |
| 🐍 **Python wheel** | [battle2-0.2.0-py3-none-any.whl](https://github.com/libertaine/BATTLE2/releases/download/v0.2.0/battle2-0.2.0-py3-none-any.whl) | Pure Python 3.10–3.13 package; does not contain pMARS |
| 🔐 **Checksums** | [SHA256SUMS.txt](https://github.com/libertaine/BATTLE2/releases/download/v0.2.0/SHA256SUMS.txt) | SHA-256 values for release assets |

---

### Default Install Paths
| Component | Location |
|------------|-----------|
| Binaries | `C:\Program Files\BATTLE2\bin\<application>\` |
| Data root | `%ProgramData%\BATTLE2\` |
| Replays | `%ProgramData%\BATTLE2\runs\_loose\` |
| Agents | `%ProgramData%\BATTLE2\agents\` |

A regular Windows wheel installation instead defaults to
`%LOCALAPPDATA%\BATTLE2`. Explicit `BATTLE2_ROOT`, then legacy `BATTLE_ROOT`,
take precedence. Frozen installer/portable behavior and recognized source or
editable checkouts retain their documented roots before the installed-platform
default is considered.

Environment variable `BATTLE2_ROOT` is automatically set to the data root during installation.
The legacy `BATTLE_ROOT` name remains supported when `BATTLE2_ROOT` is unset. If
both are defined, `BATTLE2_ROOT` takes precedence.
This writable data root is separate from bundled read-only application
resources; PyInstaller's temporary `_MEIPASS` directory is never used for
replays, logs, generated files, or user configuration.
The installer deliberately does not modify `PATH`; console applications remain
available at `bin\battle2\battle2.exe` and `bin\battle-cli\battle-cli.exe`.
Uninstall removes installed programs and shortcuts but retains `%ProgramData%\BATTLE2`.
Remove that directory manually only when its agents, replays, logs, and settings
are no longer needed.

> **Linux:** The v0.2 wheel is headless-first. See
> [Linux wheel installation](docs/LINUX_INSTALL.md) for virtual-environment,
> XDG data, starter-agent, optional GUI, and current pMARS guidance.

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
| Python  | `agent.py`   | Agent API v1 Python-only runtime | Experimental; mixed VM/Python matches are not implemented |
| Blob    | `model.blob` | Loaded directly by engine | Faster, minimal runtime                  |
| Redcode | `.red/.asm`  | Via pMARS integration     | Compatible with existing Core War agents |

* A directory containing **Python** source is discoverable, validated, and can
  execute against another Python agent through the experimental v0.3 runtime.
  Mixed Python/VM matches remain unsupported.
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

Fresh desktop and portable installations initialize four clearly labeled
starter agents in the writable `agents/` directory: Runner, Writer, Seeker, and
Spiral. Their canonical manifests are bundled as read-only package resources.
Initialization copies only missing files and never overwrites custom or edited
agent files.

---

## 🎮 GUI Tools (optional)

### Tools

| Executable | Role | Tech |
|-----------|------|------|
| battle-agent-designer.exe | Configure & run matches, open replays | PySide6 (Qt) |
| match-runner.exe          | Live match visualizer (grid/ticks)     | Pygame |
| battle-replay-viewer.exe  | View and analyze match replays         | Pygame |



---

## ⚙ Integration with pMARS (Redcode mode)

BATTLE2 supports pMARS (Redcode) for interoperability:

```bash
battle2 run --mode redcode94 --red-a path/to/A.red --red-b path/to/B.red --ticks 800
```

* The backend resolves pMARS in this order: non-empty `PMARS_CMD`, platform
  resources, the configured BATTLE2 data/application layout, then `PATH`.
  Windows considers its bundled `pmars/windows` resources and `pmars.exe`;
  Linux considers only executable `pmars` files in `pmars`, `bin`, or `PATH`
  and never selects the repository's Windows PE files. `PMARS_CMD` denotes one
  executable path (including paths with spaces), not a shell command with fixed
  arguments. An invalid explicit value is reported without silent fallback.
* The backend invokes pMARS without a shell. Missing executables, timeouts,
  nonzero exits, and unparseable results are failures and do not write a success
  summary.
* The output includes a `summary.json` indicating winner, return code, and parameters.
* The `battle2` and `battle-cli` Windows frozen applications bundle
  `pmars/windows/pmars.exe` with its `COPYING` file. The pure Python wheel never
  contains pMARS. pMARS source
  is GPL-2.0-or-later; see `third_party_licenses/` for the verified GNU GPL
  version 2 license text.
  The Linux wheel contains no pMARS executable or source. A pinned experimental
  console-only build procedure is documented in `tools/pmars/README.md`.

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

  * Build five onedir applications: `battle2`, `battle-cli`, `match-runner`,
    `battle-agent-designer`, and `battle-replay-viewer`.
  * Use the Inno Setup script to install those applications. Bundled pMARS is
    present only inside the two CLI application resource trees; starter agents
    are initialized into writable user data from packaged manifests.
  * The unified `battle2.exe design` and standalone Designer are exercised by
    deterministic frozen startup smoke during the Windows build.
  * Add Start Menu shortcuts without modifying `PATH`.

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

## 🧰 Development / Build from Source

Developers can build and test BATTLE2 directly from source.
Requires **Python 3.10 through 3.13** and a current pip. CI tests all four
supported Python versions.

```bash
# 1️⃣ Clone the repository
git clone https://github.com/libertaine/BATTLE2.git
cd BATTLE2

# 2️⃣ Create and activate a virtual environment
py -3.10 -m venv .venv        # any supported Python 3.10 through 3.13
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

pyinstaller -y --clean --name match-runner --windowed ^
  app\match_runner.py

pyinstaller -y --clean --name battle-agent-designer --windowed ^
  app\agent_designer.py
```

> 💡 *Note:* For Windows packaging, use **Inno Setup 6** and compile
> `tools\installer.iss` to create `BATTLE2-Setup-x.y.z.exe`.
> This installer preserves the five PyInstaller application directories beneath
> `C:\Program Files\BATTLE2\bin` and uses `%ProgramData%\BATTLE2` for writable
> shared data. It requires administrative installation and supports Windows
> AMD64/x64; it does not claim ARM64 support.

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
* `match-runner.exe` opens the Pygame window
* `battle-agent-designer.exe` opens the Qt interface

---

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and upcoming features.
