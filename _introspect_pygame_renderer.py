import sys, inspect, types
sys.path.append(r"D:\Projects\BATTLE2\client\src")
import battle_client.renderers.pygame_renderer as r

print("module:", r.__file__)

funcs = [(n, obj) for n, obj in r.__dict__.items() if isinstance(obj, types.FunctionType) and not n.startswith("_")]
classes = [(n, obj) for n, obj in r.__dict__.items() if isinstance(obj, type) and obj.__module__ == r.__name__ and not n.startswith("_")]

print("\nFunctions:")
for n, f in funcs:
    try:
        print(f"  - {n}{inspect.signature(f)}")
    except Exception:
        print(f"  - {n}(...)")

print("\nClasses:")
for n, c in classes:
    methods = [m for m, v in c.__dict__.items() if callable(v) and not m.startswith("_")]
    try:
        sig = inspect.signature(c.__init__)
    except Exception:
        sig = "(...)"
    print(f"  - {n}{sig}  methods={methods}")
