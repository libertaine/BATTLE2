"""Package-safe project metadata shared by user interfaces."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from battle_engine.agent_api import AGENT_API_VERSION
from battle_engine.replay import SCHEMA_VERSION as REPLAY_SCHEMA_VERSION
from battle_engine.result_model import SCHEMA_VERSION as RESULT_SCHEMA_VERSION

PROJECT_URL = "https://github.com/libertaine/BATTLE2"
LICENSE_NAME = "MIT"


@dataclass(frozen=True)
class ProjectInfo:
    version: str
    agent_api_version: int
    result_schema_version: int
    replay_schema_version: int
    python_version: str
    project_url: str = PROJECT_URL
    license_name: str = LICENSE_NAME


def get_project_info() -> ProjectInfo:
    try:
        package_version = version("battle2")
    except PackageNotFoundError:
        package_version = "development checkout"
    return ProjectInfo(
        version=package_version,
        agent_api_version=AGENT_API_VERSION,
        result_schema_version=RESULT_SCHEMA_VERSION,
        replay_schema_version=REPLAY_SCHEMA_VERSION,
        python_version=platform.python_version(),
    )
