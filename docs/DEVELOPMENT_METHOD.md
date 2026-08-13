# AI-Assisted Development

This document describes how AI tooling is used in Bytefray's own development
process. It is a methodology note for anyone curious how the project is
built — it is not a Bytefray feature, and nothing described here is required
to build, install, or run Bytefray, create or run agents, execute tests, use
Agent Designer, run CI, or produce a release.

Bytefray (formerly BATTLE2) began partly as an experiment in whether large
language models could contribute meaningfully to the creation of a real
software project. It has evolved into an exploration of AI-assisted,
human-directed software development. AI tools are used for implementation,
repository exploration, debugging, architecture critique, test generation,
documentation, code review, and independent second opinions.

Development is incremental and repository-driven. Goals and architecture are
established through human direction and AI-assisted analysis; coding agents
work against branches and the current source tree; failures are reproduced;
tests are run; and diffs are reviewed before changes are accepted. Different
tools and models may also be used independently to challenge implementations
or review one another's conclusions.

AI-generated code and review findings are treated as proposals, not
authority. Claims are checked against executable behavior, tests, the
current repository, and other reproducible evidence; findings that cannot be
confirmed are rejected. Human judgment remains responsible for project
direction, requirements, architecture, scope, tradeoffs, and deciding when a
change is ready to enter the project.

## Optional Local AI Development Assistance

Bytefray development may optionally use local [Ollama](https://ollama.com)
models for bounded secondary analysis — test-failure triage, focused
diff/code review, regression-test brainstorming, Windows/Linux portability
review, evidence review for ambiguous failures, and summarization of large
test/CI output. This is **developer tooling, not a Bytefray feature**:
local-model findings are advisory and non-authoritative, and are never a
substitute for tests, reproduction, source inspection, or release
validation. Ollama is not required to build, install, or run Bytefray,
create or run agents, execute tests, use Agent Designer, run CI, or
produce a release. See [tools/local_ai/README.md](../tools/local_ai/README.md)
for the full policy and current tooling status.
