"""Shared application resource and writable data-root resolution."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath


def normalize_root(value: str | os.PathLike[str]) -> Path:
    """Return an absolute, user-expanded path without requiring it to exist."""
    return Path(value).expanduser().resolve()


def configured_data_root(environ: Mapping[str, str] | None = None) -> Path | None:
    """Resolve the explicit writable root.

    ``BYTEFRAY_ROOT`` is the preferred, current variable. ``BATTLE2_ROOT`` and
    ``BATTLE_ROOT`` remain supported, deprecated compatibility aliases from
    the project's prior name, checked in that order when ``BYTEFRAY_ROOT`` is
    unset.
    """
    values = os.environ if environ is None else environ
    for name in ("BYTEFRAY_ROOT", "BATTLE2_ROOT", "BATTLE_ROOT"):
        value = values.get(name, "").strip()
        if value:
            return normalize_root(value)
    return None


def _source_checkout_root() -> Path | None:
    """Return the repository root iff this module is running from its own
    known source-tree position, ``.../engine/src/battle_engine/paths.py``
    (parents[3] is the repository root) -- covering both a plain source
    checkout and a ``pip install -e .`` editable install, both of which
    resolve ``__file__`` to that literal path rather than a copy.

    Deliberately checks only that fixed structural suffix, not an unbounded
    walk up every ancestor directory: a normal (non-editable) wheel install
    copies this file into ``site-packages/battle_engine/paths.py``, and an
    ancestor-name search (looking for *any* directory above the module that
    happens to contain sibling ``engine/`` and ``client/`` subdirectories)
    would misidentify that installed copy as a source checkout whenever the
    installing virtualenv happens to be created underneath an unrelated
    checkout that contains its own ``engine/``/``client/`` directories --
    confirmed by installing the built wheel into a venv nested under this
    very repository, which silently redirected the writable data root to
    the repository's own ``agents/`` directory instead of the documented
    installed-platform default.
    """
    module_path = Path(__file__).resolve()
    if module_path.parts[-4:-1] != ("engine", "src", "battle_engine"):
        return None
    candidate = module_path.parents[3]
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


def _windows_data_root(environ: Mapping[str, str]) -> Path:
    """Return the per-user data directory used by a regular Windows installation."""
    local_app_data = environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return normalize_root(Path(local_app_data) / "BATTLE2")

    configured_home = environ.get("USERPROFILE", "").strip()
    home = normalize_root(configured_home) if configured_home else Path.home().resolve()
    return home / "AppData" / "Local" / "BATTLE2"


def installed_data_root(
    environ: Mapping[str, str], *, platform: str | None = None
) -> Path:
    """Return the platform default for a regular, non-editable installation."""
    platform_name = sys.platform if platform is None else platform
    if platform_name.startswith("linux"):
        return _linux_data_root(environ)
    if platform_name == "win32":
        return _windows_data_root(environ)
    return Path.cwd().resolve()


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


def get_branding_icon_path(filename: str = "bytefray-icon.png") -> Path | None:
    """Return the packaged Bytefray branding icon for the current run
    context, or ``None`` if it cannot be found.

    Checked in order under :func:`get_resource_root`:

    1. ``assets/branding/<filename>`` -- the canonical tree. Present
       directly in a source checkout, and bundled wholesale into frozen
       PyInstaller GUI builds (both GUI specs already collect the
       repository-root ``assets/`` directory).
    2. ``app/assets/branding/<filename>`` -- a synced runtime copy that
       exists only because a wheel install can only expose package-data
       files that live inside an installed package directory, not the
       repository-root ``assets/`` tree. ``tools/generate_brand_assets.ps1``
       writes both copies from the same source crop, so they cannot drift.

    Callers must treat ``None`` as a normal, silent case (skip the icon)
    rather than an error -- this deliberately never raises, so a missing or
    unbundled icon never blocks unrelated GUI or headless operation.
    """
    root = get_resource_root()
    for candidate in (
        root / "assets" / "branding" / filename,
        root / "app" / "assets" / "branding" / filename,
    ):
        if candidate.is_file():
            return candidate
    return None


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

    return installed_data_root(values)


# Compatibility name retained for v0.1 callers that treated "battle root" as
# the writable agent/run root.
def get_battle_root() -> Path:
    return get_data_root()


def contained_path(base_dir: Path, relative: str | os.PathLike[str]) -> Path | None:
    """Resolve ``relative`` beneath ``base_dir``, or ``None`` if it escapes.

    Refuses ``../`` traversal, absolute paths (Windows drive-qualified or
    POSIX-rooted), and symlink escapes -- anything whose fully resolved
    location does not fall under ``base_dir``'s own fully resolved location
    returns ``None`` rather than being silently treated as contained.
    ``Path.resolve()`` also normalizes case/drive on Windows, so containment
    is checked post-resolution, not via string prefix comparison. A moved
    ``base_dir`` (with its contents moved alongside it) still resolves
    correctly, since containment is computed against ``base_dir`` as passed
    at call time, never a path baked into any artifact.
    """

    raw = os.fspath(relative)
    if Path(raw).is_absolute() or PureWindowsPath(raw).drive:
        return None

    base_resolved = Path(base_dir).resolve()
    candidate = Path(base_dir) / Path(raw)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return resolved
