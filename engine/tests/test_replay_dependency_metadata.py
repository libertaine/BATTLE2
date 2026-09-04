"""Regression coverage for the RC2 pygame-ce dependency migration.

``pygame`` (classic) and ``pygame-ce`` both provide the same importable
``pygame`` namespace, so a runtime ``import pygame`` check cannot tell them
apart -- only the *declared distribution dependency* can. These tests read
``pyproject.toml`` as text (the same convention
``test_installer_versions_match_package_and_release_tag`` in
``test_windows_packaging_spec.py`` already uses, rather than a TOML parser)
so they run unmodified on every supported interpreter without adding a
parsing dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_TEXT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _extra_block(name: str) -> str:
    match = re.search(rf"^{name} = \[(.*?)^\]", PYPROJECT_TEXT, re.MULTILINE | re.DOTALL)
    assert match is not None, f"[project.optional-dependencies] extra {name!r} not found"
    return match.group(1)


def test_replay_and_gui_extras_declare_pygame_ce() -> None:
    for extra in ("replay", "gui"):
        block = _extra_block(extra)
        assert re.search(r'"pygame-ce', block), (
            f"{extra!r} extra must declare pygame-ce (found: {block!r})"
        )


def test_replay_and_gui_extras_do_not_declare_classic_pygame() -> None:
    # A bare `"pygame` requirement string (not followed by `-ce`) would
    # reintroduce the classic-Pygame source-build-on-Linux problem this
    # migration exists to fix -- see docs/LINUX_INSTALL.md and the RC2
    # qualification record under docs/research/v4/.
    classic_pygame_requirement = re.compile(r'"pygame(?!-ce)')
    for extra in ("replay", "gui"):
        block = _extra_block(extra)
        assert not classic_pygame_requirement.search(block), (
            f"{extra!r} extra must not declare classic pygame (found: {block!r})"
        )
