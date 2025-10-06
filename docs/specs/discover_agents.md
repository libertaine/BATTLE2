# discover_agents
Module: engine/src/battle_engine/agents.py  
Purpose: Scan `agents/` and return `{name: AgentSpec}`.

Signature:
```python
def discover_agents(root: Union[str, Path]) -> Dict[str, AgentSpec]:
