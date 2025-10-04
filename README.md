
Project to determine feasibility of using LLM to assist me in creation of a project.

Here’s a cleaned-up, more complete **README.md** draft. It reflects your wrapper entry point, MIT license, PMARS mode, agent formats, usage examples, and packaging notes. You can drop this in replacing the old one (adjust sections to match your file layout exactly).

---

````markdown
# BATTLE2

**BATTLE2** is a Python-based framework and simulation engine for Core War–style AI competitions. It supports:

- Native Python agents  
- Precompiled binary “blob” agents  
- Integration with pMARS (Redcode) for interop  
- Replay viewing and agent design tools  

This project is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## 🔧 Quick Start

### Clone & Install (dev mode)

```bash
git clone https://github.com/libertaine/BATTLE2.git
cd BATTLE2
python -m venv venv
source venv/bin/activate     # or `.\venv\Scripts\activate` on Windows
pip install -e .[gui]        # gui extra includes pygame
````

> If you don’t need GUI tools, you can install just the core with:
>
> ```bash
> pip install -e .
> ```

### CLI Usage

```bash
battle-cli --help
```

Key options:

* `--ticks N`: number of simulation cycles
* `--arena SIZE`: memory arena size
* `--list-agents`: show available agents
* `--mode redcode94`: engage pMARS mode (requires `--red-a` and `--red-b`)
* Other flags control agent selection, instruction quotas, weighting, etc.

You can also run:

```bash
python -m battle_engine.cli --help
```

---

## 🧠 Agent Formats & Execution Modes

### Supported Agent Formats

| Type    | File         | Execution Path            | Notes                                    |
| ------- | ------------ | ------------------------- | ---------------------------------------- |
| Python  | `agent.py`   | Interpreted at runtime    | Use Python logic & host APIs             |
| Blob    | `model.blob` | Loaded directly by engine | Faster, minimal runtime                  |
| Redcode | `.red/.asm`  | Via pMARS integration     | Compatible with existing Core War agents |

* The **Python** format is great for experimentation and rapid prototyping.
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
battle-cli --list-agents
```

to see all discovered agents.

---

## 🎮 GUI Tools (optional)

* **Agent Designer**: `battle-agent-designer`
* **Replay Viewer**: `battle-replay-viewer`

They are simple stubs now (pygame windows), but ready for extension. If you didn’t install the `gui` extras, you’ll get a friendly error about missing `pygame`.

---

## ⚙ Integration with pMARS (Redcode mode)

BATTLE2 supports pMARS (Redcode) for interoperability:

```bash
battle-cli --mode redcode94 --red-a path/to/A.red --red-b path/to/B.red --ticks 800
```

* The backend spawns `pmars` with appropriate flags to evaluate the match.
* The output includes a `summary.json` indicating winner, return code, and parameters.
* You need to install `pmars` binaries (bundled or via your system). The license of pMARS must be respected (typically GPLv2). See `third_party_licenses/` in this repo for full details.

---

## 🧪 First-Run Example

1. Clone & install (see **Quick Start** above).

2. View available agents:

   ```bash
   battle-cli --list-agents
   ```

3. Run a match with default agents:

   ```bash
   battle-cli --ticks 500 --arena 2048 --a-agent my_agent --b-agent other_agent
   ```

4. Optional: launch viewer to inspect results:

   ```bash
   battle-replay-viewer path/to/replay.json
   ```

---

## 🚀 Packaging for Windows

We use a wrapper entry point (`battle_engine._entry:main`) to surface `battle-cli` without modifying `cli.py` directly.
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

* CI (GitHub Actions) should at least run `battle-cli --help`, build tests, and optionally GUI smoke tests.

If you are migrating from the prior version, check the following:

* Your old agent files must be relocated under `agents/` with a matching directory structure
* `.env` has been removed; use environment variables or CLI options instead
* The wrapper ensures existing CLI logic carries forward unchanged

Contributions welcome — open a PR or issue. Thanks for checking out BATTLE2!

```

---

Let me know if you want a trimmed or extended version (with diagrams, more examples, or deeper dev notes). I can also diff this against your existing README to highlight what needs replacing.
::contentReference[oaicite:0]{index=0}
```
