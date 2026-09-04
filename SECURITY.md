# Security Policy

## Supported release line

Bytefray follows a single active release line — there are no older
maintained major versions receiving separate fixes; security fixes are made
against that line's current state. See [CHANGELOG.md](CHANGELOG.md) for
release history. As of this writing, that line is in the `4.x` prerelease
series, currently `4.0.0-rc1` — a release candidate, not yet a final stable
release; the most recent stable release remains `3.0.0`. See
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for what the current line's
Ruleset, Agent API, and schema contracts do and do not guarantee as stable
while v4.0 remains a release candidate.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for a suspected security
vulnerability. Instead, report it privately:

- Preferred: open a [GitHub private security advisory](https://github.com/libertaine/Bytefray/security/advisories/new)
  for this repository.
- If that isn't available to you, contact the maintainer directly through
  their GitHub profile ([@libertaine](https://github.com/libertaine)) and
  ask for a private channel to share details.

Please include reproduction steps, the affected version/commit, and your
platform. We ask that you avoid public disclosure (issues, PRs, forums,
social media) until a fix has been released or a reasonable disclosure
timeline has been agreed with the maintainer.

## Security-sensitive areas

**Bytefray executes user-authored code as ordinary code, not as untrusted
input inside a hostile-code sandbox.** This is true for both supported
agent formats:

- **Python agents** (Agent API v1 and Agent API v2) run in-process or in a
  worker subprocess with the same OS-level privileges and filesystem/network
  access as the process running Bytefray. Agent API v2 (used by Ruleset
  `bytefray-rules-4-alpha1`) changes the Python programming contract, not
  the execution/isolation model — the same non-sandboxed guarantees below
  apply identically to both API generations. The optional worker-subprocess
  timeout used by `bytefray agents validate`/`test` and Agent Lab (see
  [docs/AGENT_LAB.md](docs/AGENT_LAB.md)) exists to contain accidental
  non-returning `reset()`/`act()` calls during agent development — it is
  **development-time hang containment, not a security boundary**, and it is
  not used on every execution path (`bytefray run` and headless tournaments
  do not run through it).
- **Redcode (`.red`/`.asm`) agents** are executed via an external pMARS
  process. Bytefray does not modify or sandbox pMARS itself beyond invoking
  it as a subprocess without a shell.

**Do not run agents you do not trust, or run them only in an environment
(dedicated user account, container, VM, or similar) whose blast radius you
have already accepted.** Bytefray is a simulation/competition platform, not
a code-execution security product, and no claim of stronger isolation
should be inferred from any feature name ("containment," "worker," etc.)
used elsewhere in the documentation.

Areas that *are* explicitly defended, and are the right place to report a
regression against, without implying a sandbox:

- **Path/artifact containment** — agent-revision archival and other
  filesystem-writing paths validate that resolved paths stay within their
  intended root and reject or record (rather than silently follow)
  unexpected symlinks, junctions, or reparse points.
- **Artifact validation** — replay, result, and evaluation-history files
  read back by Bytefray are schema-validated; malformed or unexpected
  artifacts are rejected (fail-closed) rather than trusted and executed.
- **pMARS invocation** — the pMARS backend is invoked with an explicit
  executable path and argument list, never through a shell, and rejects an
  invalid explicit `PMARS_CMD` rather than silently falling back.

If you find a way to escape these specific boundaries (e.g., writing outside
an intended data root via a crafted agent-revision archive, or getting a
malformed artifact to execute code during validation rather than being
rejected), that is a vulnerability worth a private report. A Python agent
using its ordinary, documented ability to read/write files or make network
calls is expected behavior, not a vulnerability, given the model above.
