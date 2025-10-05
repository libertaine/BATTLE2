import sys, inspect
sys.path.append(r"D:\Projects\BATTLE2\client\src")
import battle_client.renderers.pygame_renderer as r
print("module:", r.__file__)
print("has main():", hasattr(r, "main"))
if hasattr(r, "main"):
    print("main signature:", inspect.signature(r.main))
    # Try a dry-run: import only (don’t run UI)
