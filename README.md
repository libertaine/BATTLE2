
Project to determine feasibility of using LLM to assist me in creation of a project.


BATTLE2 is an experimental **agent battle engine**.  
It provides a simulation environment where agents compete on a grid, writing values, claiming territory, and surviving against one another.  

Agents can be **built-in** (e.g. `runner`, `writer`, `bomber`, `flooder`, `spiral`, `seeker`) or **custom** (discovered dynamically from the `agents/` directory).

---

## Project Layout

```

BATTLE2/
├── engine/
│   └── src/battle_engine/
│       ├── cli.py          # Command-line interface (entry point)
│       ├── core.py         # Engine kernel and simulation logic
│       ├── renderers.py    # Pygame and other renderers
│       └── agents.py       # Agent discovery/resolution helpers
├── agents/
│   └── <agent_name>/       # Custom agent definitions
│       ├── agent.yaml      # Optional JSON/YAML-like config
│       ├── agent.py        # Agent code (optional if using blobs)
│       └── model.blob      # Optional default binary model file
├── runs/
│   └── ...                 # Saved replays and summaries
└── README.md               # This file

````

---

## Installation

Requirements:
- Python **3.10+**
- [Pygame](https://www.pygame.org/) (for visual rendering)

Set up a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
````

---

## Usage

Run a simple match between built-in agents:

```bash
python3 -m battle_engine.cli --a-type runner --b-type writer --ticks 50
```

List discovered agents:

```bash
python3 -m battle_engine.cli --list-agents
```

Run with a third agent:

```bash
python3 -m battle_engine.cli --a-type runner --b-type writer --c-type bomber
```

Control simulation size and duration:

```bash
python3 -m battle_engine.cli --arena 512 --ticks 200
```

---

## Replays and Summaries

Each run produces:

* `replay.jsonl` — line-delimited JSON log of every tick (`alive`, `score`, etc.)
* `summary.json` — concise match metadata:

  ```json
  {
    "version": 1,
    "ticks": 200,
    "winner": "A",
    "A_score": 38,
    "B_score": 70,
    "params": { "arena": 512, "ticks": 200, "win_mode": "score" },
    "agents": { "A": "runner", "B": "writer" }
  }
  ```

---

## Custom Agents

Place agents under `agents/<name>/`.
Each agent may include:

* `agent.yaml` (JSON superset)

  ```json
  {
    "name": "replicator",
    "display": "Replicator Agent",
    "defaults": { "aggression": 0.4 }
  }
  ```

* `agent.py` (Python logic, optional if using blobs)

  ```python
  # agents/replicator/agent.py
  #
  # Example stub agent that moves randomly.
  # The engine will import and use `Agent` at runtime.

  import random

  class Agent:
      def __init__(self, config=None):
          self.config = config or {}
          self.aggression = self.config.get("aggression", 0.5)

      def step(self, state):
          """
          Called once per tick.
          - state: dictionary with current simulation info
          Returns an action dict, e.g.:
              {"move": (dx, dy), "write": byte_value}
          """
          dx, dy = random.choice([(0,1),(1,0),(0,-1),(-1,0)])
          return {
              "move": (dx, dy),
              "write": random.randint(0, 255),
          }
  ```

* `model.blob` (binary model artifact, optional)

### Parameter overrides

* Defaults come from `agent.yaml`
* Override per side via env JSON:

```bash
export BATTLE_AGENT_A_PARAMS_JSON='{"blob_path":"agents/replicator/model.blob","aggression":0.7}'
python3 -m battle_engine.cli --a-type replicator --b-type runner --ticks 50
```

* Explicit CLI flags (`--a-blob`) override both defaults and env.

---

## Development

Typical workflow:

```bash
# Start from main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/my-feature

# Work, commit, push
git add .
git commit -m "Implement new agent type"
git push origin feature/my-feature

# Merge back to main when ready
git checkout main
git pull origin main
git merge --no-ff feature/my-feature
git push origin main
```

---

## License

This project is open source under the GPLv3 license.

