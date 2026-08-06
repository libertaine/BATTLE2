"""Validate the release-critical contents of a BATTLE2 wheel."""

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
}
EXPECTED_SCRIPTS = {
    "battle2",
    "battle-agent-designer",
    "battle-cli",
    "match-runner",
}


def validate_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing_files = sorted(EXPECTED_FILES - names)
        if missing_files:
            raise ValueError(f"Wheel is missing expected files: {missing_files}")

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
