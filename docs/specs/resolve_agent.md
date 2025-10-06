# resolve_agent
**Module:** engine/src/battle_engine/agents.py  
**Purpose:** Resolve an agent identifier (name/path/spec) into a validated `AgentSpec`.

## Signature
```python
from pathlib import Path
from typing import Union
def resolve_agent(root: Union[str, Path], ident: str) -> "AgentSpec":
