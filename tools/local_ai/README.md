# Optional Local AI Development Assistance (Ollama)

This directory documents **optional** developer tooling for using local
[Ollama](https://ollama.com) models as a secondary, non-authoritative
assistant during Bytefray development. It has no runtime relationship to
Bytefray itself.

> **Ollama is not required** to build, install, run, test, package, or
> release Bytefray, to use Agent Designer, or to run CI. Nothing in the
> engine, CLI, or GUI imports or depends on anything in this directory.
> See [Boundaries](#boundaries) below.

## Purpose

Local Ollama models can act as inexpensive secondary development workers
for bounded, well-scoped tasks. They are intended to reduce unnecessary use
of remote/paid reasoning resources for repetitive or independently
verifiable work — not to replace the judgment of the human contributor or
the primary AI-assisted development workflow described in the README's
[AI-Assisted Development](../../README.md#ai-assisted-development) section.

**Local models are not authoritative reviewers.** Every finding they
produce is a proposal to be checked, exactly like any other AI-generated
suggestion in this project — see [Authority and verification
policy](#authority-and-verification-policy).

## Recommended task categories

These are conceptual task profiles, not a rigid taxonomy. Each has a
currently preferred default model based on the small local benchmark
described in [Stage 1 benchmark history](#stage-1-benchmark-history) —
these defaults are **current locally benchmarked preferences, not
permanent Bytefray requirements**, and may change as models, Ollama,
hardware, or Bytefray itself evolve.

### Review

Use for:

- narrow code/diff review
- implementation-vs-requirement comparison
- cross-platform (Windows/Linux) review
- provenance/evaluation review
- identifying the smallest safe correction

Current tested default: `qwen2.5-coder:14b`

### Triage

Use for:

- pytest failures
- tracebacks
- CI failures
- reproduction output
- narrowing likely failure mechanisms

Current tested default: `qwen2.5-coder:14b`

### Evidence

Use when the important question is: **what does the supplied evidence
actually prove?**

Useful for:

- intermittent CI failures
- ambiguous regressions
- provenance claims
- stale metadata
- conflicting observations
- deciding whether a defect is actually established

Current tested default: `gpt-oss:20b`

### Summarize

Use for:

- large pytest output
- logs
- repeated failures
- bulk condensation before deeper review

Current tested default: `qwen2.5-coder:7b`

### Tests

Use for:

- adversarial regression-test ideas
- boundary cases
- negative controls
- Windows/Linux variants
- protecting an invariant rather than merely reproducing a bug

Current tested default: `qwen2.5-coder:14b`

## Authority and verification policy

Local-model findings are **advisory and non-authoritative**. Before a
local-model finding may justify any of the following:

- production-code changes
- removal or weakening of tests
- retries around a failing test
- security-boundary changes
- path-containment changes
- provenance/evaluation identity changes
- determinism changes
- replay-semantic changes
- documented behavior changes
- release decisions

the finding **must be independently verified through appropriate direct
evidence**. Verification may include:

- reproducing the defect
- inspecting the relevant source
- creating a regression test
- comparing behavior against documented requirements
- running the appropriate targeted/full test suite
- cross-platform reproduction where relevant

Three rules apply explicitly:

> A test failure that disappears on rerun is not, by itself, evidence that
> the test is flaky or that CI caused the failure.

> A test that exposes a production defect is not a `TEST_DEFECT` merely
> because the failure originated in a test.

> If evidence cannot establish a reliable cause, the correct local-model
> conclusion is `INSUFFICIENT_EVIDENCE`.

Do not recommend retrying away unexplained failures.

## Stage 1 benchmark history

Local model selection was based on a small Bytefray-specific benchmark,
not model size alone. The benchmark tested:

- straightforward defect diagnosis
- Linux filesystem/symlink behavior
- filesystem containment reasoning
- stale-version metadata reasoning
- CLI-entry behavior
- expected/non-defect controls
- frozen-source/provenance drift
- ambiguous CI-failure restraint

Approximate initial local results (a small, repository-specific benchmark
run — not a universal or scientific model ranking):

- **`qwen2.5-coder:7b`** — very fast; useful for simpler analysis and
  summarization; weaker classification/evidence discipline.
- **`qwen2.5-coder:14b`** — best overall balance; strong defect
  classification; strong smallest-safe-correction reasoning; correctly
  handled difficult provenance and insufficient-evidence cases; preferred
  general local reviewer.
- **`gpt-oss:20b`** — particularly good evidence restraint; useful as an
  ambiguity/evidence referee; substantially more verbose.
- **`qwen3-coder:30b`** — strong on clearly demonstrated defects; weaker on
  ambiguous-failure restraint in this benchmark; not currently preferred
  over the 14B model for general review.

**The important conclusion:** larger model size did not automatically
produce better Bytefray review behavior, so model selection should
continue to be benchmark-driven rather than assumed from parameter count.

## Local tooling structure

```
tools/
  local_ai/
    README.md                    # this file
    Invoke-BytefrayLocalAI.ps1   # the harness
    prompts/
      common.txt
      review.txt
      triage.txt
      evidence.txt
      summarize.txt
      tests.txt
```

**Status: integrated.** `Invoke-BytefrayLocalAI.ps1` is the working,
locally tested PowerShell harness for driving the task categories above
against a local Ollama instance, copied in unmodified from its tested
source. The `prompts/` files are the exact tested prompt set the harness
was benchmarked with — the same content `-InitializePrompts` writes for a
fresh prompt directory. `-InitializePrompts` never overwrites an existing
prompt file, so a contributor's local edits to a prompt are preserved
across reruns.

Usage:

```powershell
# One-time (or after deleting a prompt file you want regenerated):
.\tools\local_ai\Invoke-BytefrayLocalAI.ps1 -InitializePrompts

# Examples:
.\tools\local_ai\Invoke-BytefrayLocalAI.ps1 -Task Review -InputFile .\review.diff
.\tools\local_ai\Invoke-BytefrayLocalAI.ps1 -Task Evidence -Text "failure details"
git diff | .\tools\local_ai\Invoke-BytefrayLocalAI.ps1 -Task Review
```

Requires a locally running Ollama instance (`http://localhost:11434` by
default) with the relevant model pulled; pass `-PullMissingModel` to pull
it automatically, or `-Model` to override a profile's default. None of
this is required for any normal Bytefray command — see
[Boundaries](#boundaries).

### Windows PowerShell 5.1 compatibility note

The harness reads prompt/input text as plain .NET strings rather than via
`Get-Content -Raw`, which on Windows PowerShell 5.1 can retain extended
properties that break `ConvertTo-Json` at high depth:

```powershell
[System.IO.File]::ReadAllText($path)
```

It also serializes each request/response at only the JSON depth actually
required (`-Depth 5` for the outbound request and metadata, `-Depth 10`
for the raw Ollama response), rather than an arbitrarily high default
depth.

## Generated artifacts

Local Ollama result artifacts should not normally be committed. If the
local tooling writes to `tools/local_ai/local-ai-results/` (or an
equivalent generated-results directory), that path is `.gitignore`d.
Generated reports may contain supplied source excerpts, diffs, logs, test
output, local machine metadata, and model responses — treat them as local
development artifacts unless explicitly selected for a reproducible
research/test fixture.

## Future-development workflow

Future Bytefray development prompts may instruct an agent to use this
local Ollama tooling where available. Recommended workflow:

```
direct repository evidence/tests
         |
         v
local bounded secondary review
         |
         v
independently verify findings
         |
         +--> clear/reproducible -> proceed normally
         |
         +--> ambiguous/high-risk -> deeper review
```

Useful delegation targets include large test-output summarization, several
independent small diff reviews, test-case generation, portability checks,
and first-pass failure triage.

**Local AI should not be used to manufacture consensus.** Running multiple
local models that repeat the same unsupported assumption does not
constitute independent verification.

## Development-report expectations

When local-AI delegation was meaningfully used for a development task,
future development/release reports should disclose it, for example:

```
Local Ollama assistance:
- qwen2.5-coder:14b reviewed the Linux path-handling diff.
- It raised three potential issues.
- Two were reproduced and corrected.
- One was rejected after direct source/test verification.
- No local-model finding was accepted without independent verification.
```

The purpose is to determine whether local-model delegation is actually
useful over time. This reporting is not required when Ollama was not used.

## Boundaries

This tooling and its documentation:

- do not modify Bytefray's version, tags, or releases
- do not change game rules, VM semantics, agent behavior, evaluation
  provenance, or replay behavior
- do not make Ollama, any model, GPU support, or local-AI tooling a
  package dependency of Bytefray
- do not make Ollama a CI requirement
- do not download models automatically as part of any normal Bytefray
  command
- do not send Bytefray source to external (non-local) AI services
- are not a user-facing Bytefray feature

A local model's output is never a substitute for tests, reproduction,
source inspection, or release validation.
