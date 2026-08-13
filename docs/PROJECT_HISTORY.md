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
