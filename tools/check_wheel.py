"""Validate the release-critical contents of a Bytefray wheel."""

from __future__ import annotations

import argparse
import configparser
import io
import zipfile
from pathlib import Path

EXPECTED_FILES = {
    "app/__init__.py",
    "battle_client/__init__.py",
    "battle_engine/__init__.py",
    "battle_engine/data/starter_agents/runner/agent.yaml",
    "battle_engine/data/starter_agents/seeker/agent.yaml",
    "battle_engine/data/starter_agents/spiral/agent.yaml",
    "battle_engine/data/starter_agents/writer/agent.yaml",
    # Python (Agent API v1) starter agents added in v0.6.1 -- each ships
    # both a manifest and a source file, unlike the manifest-only native
    # VM starters above.
    "battle_engine/data/starter_agents/claimer/agent.yaml",
    "battle_engine/data/starter_agents/claimer/agent.py",
    "battle_engine/data/starter_agents/strider/agent.yaml",
    "battle_engine/data/starter_agents/strider/agent.py",
    "battle_engine/data/starter_agents/hunter/agent.yaml",
    "battle_engine/data/starter_agents/hunter/agent.py",
    "battle_engine/data/starter_agents/wanderer/agent.yaml",
    "battle_engine/data/starter_agents/wanderer/agent.py",
    "battle_engine/data/starter_agents/adaptive/agent.yaml",
    "battle_engine/data/starter_agents/adaptive/agent.py",
    # Agent API v2 / Ruleset v4 alpha1 starter population.
    "battle_engine/data/starter_agents/v4_claimer/agent.yaml",
    "battle_engine/data/starter_agents/v4_claimer/agent.py",
    "battle_engine/data/starter_agents/v4_concentrated_attacker/agent.yaml",
    "battle_engine/data/starter_agents/v4_concentrated_attacker/agent.py",
    "battle_engine/data/starter_agents/v4_defender_scout/agent.yaml",
    "battle_engine/data/starter_agents/v4_defender_scout/agent.py",
    "battle_engine/data/starter_agents/v4_local_defender/agent.yaml",
    "battle_engine/data/starter_agents/v4_local_defender/agent.py",
    "battle_engine/data/starter_agents/v4_scout/agent.yaml",
    "battle_engine/data/starter_agents/v4_scout/agent.py",
    "battle_engine/data/agent_template/agent.yaml",
    "battle_engine/data/agent_template/agent.py",
}
EXPECTED_SCRIPTS = {
    "bytefray",
    "bytefray-cli",
    "bytefray-agent-designer",
    "bytefray-replay-viewer",
}
ALLOWED_PMARS_PATHS = {"battle_engine/pmars.py"}


def validate_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing_files = sorted(EXPECTED_FILES - names)
        if missing_files:
            raise ValueError(f"Wheel is missing expected files: {missing_files}")

        unexpected_pmars = sorted(
            name
            for name in names
            if "pmars" in name.casefold() and name not in ALLOWED_PMARS_PATHS
        )
        if unexpected_pmars:
            raise ValueError(
                "Wheel unexpectedly contains pMARS distribution material: "
                f"{unexpected_pmars}"
            )

        stray_bytecode = sorted(
            name for name in names if "__pycache__" in name or name.endswith(".pyc")
        )
        if stray_bytecode:
            raise ValueError(
                f"Wheel unexpectedly contains compiled bytecode/cache: {stray_bytecode}"
            )

        entry_points_name = next(
            (name for name in names if name.endswith(".dist-info/entry_points.txt")),
            None,
        )
        if entry_points_name is None:
            raise ValueError("Wheel is missing dist-info/entry_points.txt")
        parser = configparser.ConfigParser()
        parser.read_file(io.StringIO(archive.read(entry_points_name).decode("utf-8")))
        scripts = set(parser["console_scripts"])
        missing_scripts = sorted(EXPECTED_SCRIPTS - scripts)
        if missing_scripts:
            raise ValueError(f"Wheel is missing console scripts: {missing_scripts}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    arguments = parser.parse_args()
    validate_wheel(arguments.wheel)
    print(f"Validated wheel contents: {arguments.wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
