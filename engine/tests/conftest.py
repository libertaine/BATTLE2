"""Test the packaged engine, not the compatibility module in ``_legacy``."""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ENGINE_SRC))

# pytest.ini exposes _legacy/core.py as top-level ``core``.  Characterization
# tests use the supported package name and intentionally leave that shim alone.
