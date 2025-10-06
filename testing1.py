# testing1.py
import sys, pathlib, pprint

# Make sure Python can find the source packages
sys.path[:0] = [r'engine/src', r'client/src']

from app.services.osutil import get_battle_root
from battle_engine.agents import discover_agents

root = pathlib.Path(get_battle_root())
print("root =", root)

items = discover_agents(root)
print(f"count = {len(items)}")

for i, x in enumerate(items, 1):
    print(f"\n== agent {i} ==")
    print("type:", type(x).__name__)
    print("attrs:", sorted(k for k in getattr(x, '__dict__', {}).keys() if not k.startswith('_')))
    d = getattr(x, "__dict__", {})
    if "meta" in d:
        print("meta:")
        pprint.pprint(d["meta"])
    if "path" in d:
        print("path:", d["path"])
