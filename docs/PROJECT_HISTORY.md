# Project History: BATTLE2 → Bytefray

This project was previously named **BATTLE2**. It started as a minimal
headless Core War-inspired engine plus a Pygame match runner and Qt agent
designer, then grew a dedicated agent-authoring and evaluation toolchain one
milestone at a time before being rebranded Bytefray at v0.3.0. For the full
milestone-by-milestone history, see the version table in
[README.md](../README.md#roadmap), the forward-looking
[Roadmap](ROADMAP.md), and [CHANGELOG.md](../CHANGELOG.md) for what actually
shipped release by release.

## What changed at the rename

The public CLI is now `bytefray`; the legacy `battle2` command remains
available as a deprecated compatibility alias and prints a short deprecation
notice when used. Internal Python package names (`battle_engine`,
`battle_client`) and the `battle2.*` artifact schema identifiers
(`battle2.result`, `battle2.replay`) are retained unchanged for
compatibility — they are stable protocol identifiers, not user-facing
branding, and are not expected to be renamed to match Bytefray branding.

`BYTEFRAY_ROOT` is the preferred environment variable for choosing a
writable data root explicitly; the legacy `BATTLE2_ROOT` and `BATTLE_ROOT`
variables remain supported as deprecated fallbacks, in that precedence
order. See [docs/COMPATIBILITY.md](COMPATIBILITY.md) for the full
compatibility reference across the Ruleset, Agent API, schema, and
methodology axes.

## Post-1.0 repository cleanup

After v1.0.0 shipped, a maintenance pass removed development-era residue
that had accumulated across the BATTLE2 → Bytefray evolution: ~132MB of
accidentally-committed PyInstaller build output and generated runtime data,
personal IDE state, one-off debug scripts, duplicate/stale packaging
metadata (including a stale `app/pyproject.toml`), superseded pre-v0.3
build tooling (`tools/build_executables*.ps1`, `tools/match_runner.spec`),
and an unreferenced `sdk/` directory of early-migration examples that
included an accidental duplicate result bundle. None of this changed
documented runtime behavior or compatibility contracts. See `CHANGELOG.md`
and the repository's git history around that time for the full accounting.
