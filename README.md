Code and documentation are heavily produced by ChatGPT. 
Mainly a test to see the capabilities or using LLM as a tool to develop a project.


# BATTLE — Engine + Client (Draft README)

## Overview

**BATTLE** is a grid-based competitive simulation.

* The **engine** runs matches and writes results (no UI).
* The **client** is **presentation-only**: it loads engine outputs (JSONL replay + JSON summary) and renders them via pluggable renderers (headless, pygame, future web).

**Design principles**

* Client never owns simulation or scoring — it only **visualizes**.
* Clean separation: `engine/` vs `client/`.
* Modular renderers behind a stable `AbstractRenderer` interface.
* Zero third-party deps for headless; optional **pygame** for 2D visuals.

---

## Repository Layout

```
~/Projects/BATTLE2/
  engine/
    src/
      battle_engine/              # Engine package (NO client changes here)
  client/
    src/
      battle_client/              # Client package
        __init__.py
        cli.py                    # Entry point: replay player / renderer chooser
        utils.py                  # JSONL iterators, summary helpers, pacing, etc.
        renderers/
          __init__.py
          base.py                 # AbstractRenderer (setup/on_event/teardown)
          headless.py             # Text/logging renderer
          pygame_renderer.py      # 2D arena visual (windowed/resizable)
  sdk/
    tooling/                      # SDK/tooling (out of scope for client)
  tournament/
    scripts/
      make_demo_replay.py         # Helper to generate demo replays (optional)
  runs/
    _loose/                       # Local, untracked outputs (replays/summaries)
```

> Tip: keep real engine outputs under `runs/_loose/` and **git-ignore** that directory.

---

## Engine Outputs the Client Consumes

* **Replay** (`replay.jsonl`) — one JSON event per line:

  ```json
  {"type":"spawn","tick":1,"who":"A","pos":[8,8]}
  {"type":"move","tick":2,"who":"A","from":[8,8],"to":[9,8]}
  {"type":"territory","tick":5,"who":"A","cells":[[9,8],[10,8],[9,9],[10,9]]}
  ```

  Supported event keys:

  * `spawn`, `move`, `death|die`
  * `territory|claim` with `cells: [[x,y], ...]`
  * Optional `tick` frames with `positions: {"A":[x,y],...}` and/or `writes|claims: [[x,y],...]`
* **Summary** (`summary.json`) — match metadata:

  ```json
  {
    "version": 1,
    "seed": 42,
    "ticks": 400,
    "params": { "arena": 64, "ticks": 400, "win_mode": "score_fallback" },
    "agents": { "A": "seeker", "B": "runner" }
  }
  ```

  The client reads `arena` from either top level or `params.arena`.

---

## Install & Run

### Prereqs

* **Python 3.13**
* **VSCode** (optional)
* **pygame** (optional; only for the pygame renderer)

### Create venv and install (Windows PowerShell)

```powershell
cd C:\Users\<you>\Projects\BATTLE2
py -3.13 -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install pygame    # optional (headless renderer needs no extra deps)
```

### Create venv and install (Linux/macOS)

```bash
cd ~/Projects/BATTLE2
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install pygame    # optional
```

### Set `PYTHONPATH` and run

**Windows**

```powershell
$env:PYTHONPATH = "engine\src;client\src"
python -m battle_client.cli --replay "runs\_loose\replay.jsonl" --renderer headless
python -m battle_client.cli --replay "runs\_loose\replay.jsonl" --renderer pygame --tick-delay 0.02
```

**Linux/macOS**

```bash
export PYTHONPATH="engine/src:client/src"
python -m battle_client.cli --replay runs/_loose/replay.jsonl --renderer headless
python -m battle_client.cli --replay runs/_loose/replay.jsonl --renderer pygame --tick-delay 0.02
```

> If you need a quick demo replay:
>
> ```powershell
> .\.venv\Scripts\python.exe tournament\scripts\make_demo_replay.py --arena 64 --ticks 400 --out runs\_loose
> ```

---

## Client CLI

```
python -m battle_client.cli --replay <PATH> [--renderer headless|pygame] [--tick-delay <seconds>]
```

* `--replay` (required): path to `replay.jsonl`
* `--renderer`: `headless` (default) or `pygame`
* `--tick-delay`: optional pacing (e.g., `0.02`) to slow playback

---

## Renderer Interface & Implementations

### AbstractRenderer (`renderers/base.py`)

```python
class AbstractRenderer(ABC):
    def setup(self, metadata: Optional[dict]) -> None: ...
    @abstractmethod
    def on_event(self, event: dict) -> None: ...
    def teardown(self) -> None: ...
```

### Headless (`renderers/headless.py`)

* Prints structured lines per event.
* Good for grep/diff and verifying event shapes.

### Pygame (`renderers/pygame_renderer.py`)

* Windowed, **resizable** grid.
* Shows:

  * **Ownership tint** per cell (by agent)
  * **Processing flashes** where writes occurred
  * **Agent markers** + optional trails
  * **HUD** (tick, % complete, elapsed, event count, scale)
* Controls:

  * `Esc`/`Q` = quit
  * `Space` = pause/resume
  * `N` = step one event when paused
  * `+` / `-` = change scale
  * `T` = toggle trails
  * `0` = auto-fit window to current monitor

---

## Development Notes

* **Target Python:** 3.13
* **Third-party deps:** none (headless) / `pygame` (optional)
* **Engine isolation:** client may import engine **readers/decoders** only (e.g., JSONL helpers) — no simulation logic in client.
* **Module path:** set `PYTHONPATH` to include both `engine/src` and `client/src`.

### VSCode (recommended)

* Add a workspace setting for `python.analysis.extraPaths` to include `engine/src` and `client/src`, or rely on `PYTHONPATH`.

### Git hygiene

* Ignore generated runs:

  ```
  # .gitignore
  runs/_loose/
  ```
* Normalize Python line endings (optional):

  ```
  # .gitattributes
  *.py text eol=lf
  ```

### Branch workflow (short)

```powershell
git switch main
git pull origin main
git switch -c feature/<topic>
# edit & commit
git push -u origin HEAD
# open PR to main and merge
```

---

## Troubleshooting

* **Window “too big” / spans monitors**
  Pygame renderer opens **windowed/resizable** and clamps scale to ~90% of the current display. Press `0` to re-fit.

* **No visuals (only grid)**
  Your replay may not contain drawable events (positions/writes).
  Run headless to inspect:

  ```powershell
  python -m battle_client.cli --replay "runs\_loose\replay.jsonl" --renderer headless --tick-delay 0.01
  ```

  Ensure events include `spawn/move` and/or `territory|claim` with `cells`, or `tick` with `positions`/`writes`.

* **Replay not found**
  Check the path and quote Windows backslashes:

  ```powershell
  python -m battle_client.cli --replay "C:\Users\<you>\Projects\BATTLE2\runs\_loose\replay.jsonl" --renderer headless
  ```

* **Pygame not available**
  Install into your venv:

  ```powershell
  .\.venv\Scripts\python.exe -m pip install pygame
  ```

* **Can’t activate venv PowerShell script**
  Use `activate.bat`:

  ```powershell
  .\.venv\Scripts\activate.bat
  ```

  or temporarily allow scripts:

  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  .\.venv\Scripts\Activate.ps1
  ```

---

## Extending the Client

* Add a new renderer in `client/src/battle_client/renderers/`, subclass `AbstractRenderer`, register it in `cli.py`.
* For a future **web** renderer:

  * Serve static `index.html` + `app.js`, stream replay via a simple SSE endpoint (stdlib `http.server`).
  * Keep engine untouched.

---

## Roadmap (suggested)

* Pygame: zoom/pan, tooltips on hover, screenshots, FPS/timing overlay.
* Web renderer: HTML5 Canvas, timeline scrubber, export images/MP4.
* Tournament viewer: batch playback with summaries.

---

## License

TBD by project owner.

---

## Acknowledgements

* Python 3.13
* Pygame (optional)
