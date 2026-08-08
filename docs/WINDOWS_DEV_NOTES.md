# Windows Development Notes

Notes specific to developing Bytefray on Windows, where behavior otherwise
matches [CONTRIBUTING.md](../CONTRIBUTING.md) and the root
[README.md](../README.md) quick start.

## Running tests

Just run:

```
python -m pytest
```

No extra flags are required. `pytest.ini` points both pytest's cache
(`cache_dir`) and its `tmp_path` base (`--basetemp` in `addopts`) at
repo-local, git-ignored directories (`.pytest-cache/`, `.pytest-tmp/`)
instead of the OS defaults (`.pytest_cache/` in the repo root, and
`%TEMP%\pytest-of-<user>` / `$TMPDIR/pytest-of-<user>` for `tmp_path`).

This was added after a Windows checkout was found where both OS-default
locations had been left behind by a different tool/account with an ACL that
excluded the normal interactive user entirely -- `pytest` failed outright
with `PermissionError: [WinError 5] Access is denied`, and even `icacls`/
`Get-Acl` couldn't read the offending directories' permissions to diagnose
them further. Rather than take ownership of or delete directories a
different account created (not warranted for a one-off local conflict),
pointing pytest at fresh, repo-owned paths sidesteps the conflict
entirely, is portable to Linux (CI runners are ephemeral, so this has no
effect there beyond the cache/temp directories moving), and requires no
per-developer setup.

If `python -m pytest` still fails with a permission error on temp/cache
paths on some other machine, the same class of problem (a stale directory
with the wrong owner/ACL) is the first thing to check -- not a Bytefray
bug.

## Running mypy

```
mypy engine/src/battle_engine
mypy client/src/battle_client
```

`pyproject.toml`'s `[tool.mypy]` section sets `mypy_path` to both
`engine/src` and `client/src`, so these resolve `battle_engine.*` /
`battle_client.*` imports across the two src-layout package roots without
needing a manually-exported `MYPYPATH` environment variable in your shell.

This matters more on Windows than Linux: a Windows `pip install -e .`
observed here produced a PEP 660 hook-based editable install (a generated
`__editable__...finder.py` registered as an import hook), which mypy's
static import resolution does not execute -- so without `mypy_path`,
checking a `client/` file standalone failed with
`Cannot find implementation or library stub for module named
"battle_engine.replay"` even though the package imports fine at runtime.

`app/match_runner.py` is dead source: it calls `PygameRenderer.setup()`/
`.update()`/`.on_complete()`/`.teardown()`, methods that no longer exist
since Phase 7a Slice 3 stopped `PygameRenderer` being an `AbstractRenderer`
subclass. Its `match-runner` console-script entry point was removed in v0.3
(the maintained interactive viewer is `bytefray replay --renderer pygame` /
`battle-replay-viewer.exe`), which also removed the only import of the
module from `battle_engine.legacy` -- so `mypy engine/src/battle_engine` no
longer traverses into it and its dead-API errors do not need tracking
against the engine's mypy baseline.
