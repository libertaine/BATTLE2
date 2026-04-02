import importlib.util
import os
import sys
from pathlib import Path

# Assuming you have a base class for type-hinting/consistency
# from .base import BaseAgent


def resolve_agent(agent_id):
    """
    High-level resolver:
    1. Checks if it's a built-in agent name.
    2. Checks if it's a path to a .py file or a directory containing agent.py.
    3. Checks if it's a pre-assembled binary/blob.
    """
    # 1. Check BATTLE2_ROOT for local agent folders
    root = os.environ.get("BATTLE2_ROOT", os.getcwd())
    agent_path = Path(root) / "agents" / agent_id

    # Handle Directory vs File path
    if agent_path.is_dir():
        py_file = agent_path / "agent.py"
    else:
        py_file = Path(agent_id)  # Direct path passed via CLI

    if py_file.exists() and py_file.suffix == ".py":
        return load_python_agent(py_file)

    # 2. Fallback: Built-in agents (Placeholder for your existing logic)
    # return get_builtin_agent(agent_id)

    raise ValueError(
        f"Could not resolve agent: {agent_id}. No agent.py found at {py_file}"
    )


def load_python_agent(path):
    """
    Dynamically imports a .py file and returns an executable agent instance.
    """
    module_name = f"agent_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {path}")

    module = importlib.util.module_from_spec(spec)
    # Add the agent's directory to sys.path so it can import local helpers
    sys.path.insert(0, str(path.parent))

    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    # Contract: The agent.py MUST define a class named 'Agent' or a 'create_agent' function
    if hasattr(module, "Agent"):
        return module.Agent()
    elif hasattr(module, "create_agent"):
        return module.create_agent()

    raise AttributeError(
        f"Agent script {path} missing 'Agent' class or 'create_agent' function."
    )


def list_available_agents():
    """
    Scans the agents directory for discoverable Python agents.
    """
    root = os.environ.get("BATTLE2_ROOT", os.getcwd())
    agents_dir = Path(root) / "agents"

    found = []
    if agents_dir.exists():
        for item in agents_dir.iterdir():
            if item.is_dir() and (item / "agent.py").exists():
                found.append(item.name)
    return found
