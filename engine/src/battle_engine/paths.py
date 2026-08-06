"""Shared application resource and writable data-root resolution."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def normalize_root(value: str | os.PathLike[str]) -> Path:
    """Return an absolute, user-expanded path without requiring it to exist."""
    return Path(value).expanduser().resolve()


def configured_data_root(environ: Mapping[str, str] | None = None) -> Path | None:
    """Resolve the explicit writable root, preferring the v0.2 variable."""
    values = os.environ if environ is None else environ
    for name in ("BATTLE2_ROOT", "BATTLE_ROOT"):
        value = values.get(name, "").strip()
        if value:
            return normalize_root(value)
    return None


def _source_checkout_root() -> Path | None:
    # .../engine/src/battle_engine/paths.py -> repository root at parents[3].
    module_path = Path(__file__).resolve()
    candidates = [module_path.parents[3], *module_path.parents]
    for candidate in candidates:
        if (candidate / "engine").is_dir() and (candidate / "client").is_dir():
            return candidate.resolve()
    return None


def is_frozen_application() -> bool:
    """Return whether the current process is a frozen application."""
    return bool(getattr(sys, "frozen", False))


def _linux_data_root(environ: Mapping[str, str]) -> Path:
    """Return the XDG data directory used by a regular Linux installation."""
    xdg_data_home = environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return normalize_root(Path(xdg_data_home) / "battle2")

    configured_home = environ.get("HOME", "").strip()
    home = normalize_root(configured_home) if configured_home else Path.home().resolve()
    return home / ".local" / "share" / "battle2"


def get_resource_root() -> Path:
    """Return the read-only application resource root for the current context."""
    if is_frozen_application():
        extraction_root = getattr(sys, "_MEIPASS", None)
        if extraction_root:
            return normalize_root(extraction_root)
        return normalize_root(Path(sys.executable).parent)

    checkout_root = _source_checkout_root()
    if checkout_root is not None:
        return checkout_root

    # In a regular wheel, the installed packages share a site-packages parent.
    return Path(__file__).resolve().parent.parent


def get_data_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the writable root for agents, replays, logs, and user config."""
    values = os.environ if environ is None else environ
    configured = configured_data_root(values)
    if configured is not None:
        return configured

    if is_frozen_application():
        # Portable builds remain self-contained. Installed builds set
        # BATTLE2_ROOT to their writable ProgramData location.
        return normalize_root(Path(sys.executable).parent)

    checkout_root = _source_checkout_root()
    if checkout_root is not None:
        return checkout_root

    if sys.platform.startswith("linux"):
        return _linux_data_root(values)
    return Path.cwd().resolve()


# Compatibility name retained for v0.1 callers that treated "battle root" as
# the writable agent/run root.
def get_battle_root() -> Path:
    return get_data_root()
