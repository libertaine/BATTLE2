import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engine" / "src"
if ENGINE_SRC.exists():
    sys.path.insert(0, str(ENGINE_SRC))

from app.main import main  # <-- import main, not entrypoint

if __name__ == "__main__":
    # If app.main.main parses sys.argv, provide the mode flag
    sys.argv = [sys.argv[0], "--mode", "designer"]
    raise SystemExit(main())
