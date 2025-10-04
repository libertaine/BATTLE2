# engine/src/battle_engine/_entry.py
"""
Wrapper entry point so console_scripts can launch the existing CLI
without changing battle_engine.cli.
"""
import runpy
import sys


def main(argv=None) -> int:
    # Preserve argv behavior for argparse inside battle_engine.cli
    # If you want to pass argv explicitly, you can set sys.argv here.
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    # Execute the module as __main__ so existing top-level code runs unchanged
    runpy.run_module("battle_engine.cli", run_name="__main__")
    return 0
