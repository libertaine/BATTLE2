Role: senior Python engineer. Task: create or adjust focused pytest tests to reproduce and then validate a fix. Keep scope minimal.

Context:
- Repo targets Python 3.11 on Win/Linux.
- No new runtime deps. Use stdlib + pytest only.
- Deterministic behavior required (seed RNGs, fixed temp paths).

Provide:
1) A failing unit test (or small test file) that reproduces the bug exactly.
2) The minimal code change to make the test pass (if asked).
3) Any golden snapshot updates (if present).
4) Notes on edge cases and why they’re covered.

Template:
- A short problem statement (1–2 sentences).
- The test code (pytest), path: `tests/test_<module>_<area>.py`
- If needed, fixtures under `tests/conftest.py` (keep tiny).
- Commands to run locally:
