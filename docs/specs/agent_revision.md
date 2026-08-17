# agent_revision

**Modules:** `engine/src/battle_engine/agent_revisions.py` (self-contained
module: canonical tree-walk/hash machinery, fingerprint, content-addressed
store, restore — see §2.1 for why this does **not** touch `agent_api.py`,
a revision from the original draft of this spec); narrow additive changes
to `engine/src/battle_engine/agent_evaluation.py` (freeze-step integration
and artifact serialization only, §9 Phase 3); `evaluation_history/{models,
v2_adapter,verification,cli}.py` (§9 Phase 4); `agent_revisions_cli.py`,
new (§9 Phase 5). All implemented — see §9 for what each phase delivered.

**Purpose:** give a Bytefray agent's exact revision a durable identity that
survives the live source changing — close the gap
`docs/specs/evaluation_history.md` §20 explicitly deferred ("no revision
store, no embedded source snapshots, no generic provenance system") and
v0.7.0's own recorded "Known Limitations" (`CHANGELOG.md`: source
fingerprints are identification-only, no historical copy is kept).

Status: design spec, written before implementation, per `CONTRIBUTING.md`'s
spec → issue → prompt → PR flow. This document covers the full intended
shape of the feature; §9 marks which parts are implemented in which phase.
**Phases 2–6 (§9) are all implemented**: `agent_revisions.py`,
`agent_evaluation.py`'s freeze-step integration, the
`evaluation_history` domain/CLI extensions (§5.4/§7.2), and
`agent_revisions_cli.py` (§7's `list`/`show`/`restore`), covering the full
spec below except where §9/§10 note a deliberate v0.8 boundary (revision
`diff`, GUI). Revised three times: once before any code existed (§0), once
during Phase 2 implementation (§2.1, §3.1), and once during the Phase 3
review pass that completed Phases 4–6 (this revision) — each is called out
at the point it changes, not silently.

Working branch: `v0.8-development` (not a new `v0.8-agent-provenance`
branch — see the audit report for why; nothing about this spec depends on
the branch name).

## 0. Revision history of this spec

This is a revised design, not a first draft. The prior draft (presented for
review, not committed) proposed: (a) a revision-ID hash over five fields
(`agent_revision_fingerprint`, `entry_point`, `api_version`, `agent_version`,
`kind`), (b) snapshotting lazily "on first cell execution," and (c) a
persisted `agent_revision_available: bool` field. Reviewer feedback rejected
all three as under-justified or actively risky; this spec replaces them with,
respectively: §1's single-input content address, §4's freeze-time archival
with a provable consistency check, and §6's decision to drop `available`
entirely. Every one of those changes is argued for at the point it's
introduced below, not merely asserted.

## 1. Revision identity

### 1.1 What a revision fingerprint covers

`agent_revision_fingerprint(agent_dir)` (new, `agent_revisions.py`) hashes
every included file under one agent's directory — see §2 for the exact
inclusion/exclusion contract. It is deliberately a **different, wider**
value than the existing `agent_api.local_source_fingerprint()`
(`.py` files only, used by drift detection — §7 of
`evaluation_history.md`). The two are not merged and neither replaces the
other:

- `local_source_fingerprint` stays exactly as it is today: the value
  `agent_identity()` hashes into `evaluation_id` and the value drift
  detection's three-way invariant compares. **Not touched by this spec.**
- `agent_revision_fingerprint` is a new, separate value used only for
  revision archival/addressing. It is never substituted into
  `agent_identity()`, `evaluation_id`, or drift detection.

Keeping these separate is a deliberate continuation of the project's
existing three-way split (agent identity / execution-environment identity /
evaluation-rules identity, `evaluation_history.md` §1) — revision identity
is a fourth, independent axis, not a wider replacement for the first one.

### 1.2 Revision-ID inputs — justified, not merely asserted

```python
AGENT_REVISION_FINGERPRINT_VERSION = 1

def agent_revision_fingerprint(agent_dir: Path | None) -> str | None: ...

def agent_revision_id(fingerprint: str) -> str:
    return f"agent-revision_{fingerprint}"
```

The ID is a function of **exactly one input**: the versioned whole-tree
content fingerprint. Compared with the rejected first draft
(`{fingerprint, entry_point, api_version, agent_version, kind}`), each
dropped field is dropped for a specific, checkable reason:

- **`entry_point`, `api_version`, `agent_version`** are themselves values
  declared inside the agent's manifest file (`agent.yaml`/`agent.json`).
  Since §2's inclusion contract covers the manifest file itself (unlike
  `local_source_fingerprint`, which does not), any change to any of these
  three values necessarily changes the manifest file's bytes, which
  necessarily changes `agent_revision_fingerprint`. Hashing them a second
  time, separately, hashes information the fingerprint already contains —
  it cannot distinguish two revisions the fingerprint doesn't already
  distinguish, and cannot fail to distinguish two revisions the fingerprint
  does.
- **`kind`** (`python`/`blob`/`builtin`) is either declared in the manifest
  (same argument as above) or inferred from *which files exist*
  (`agents.py`'s `_spec_from_dir`: `kind = "python" if py_path.exists()
  else "blob" if blob is not None else "builtin"`) — and "which files
  exist" is exactly what the whole-tree file walk that produces the
  fingerprint already observes. A `kind` change without a fingerprint
  change is not possible.
- **`agent_id`** (the catalog directory name) is deliberately *not* an
  input. A revision fingerprint is content-addressed the same way a git
  blob or `local_source_fingerprint` region hash is: identical bytes
  produce the identical ID regardless of which catalog directory they were
  read from. This is not a loss of information — `agent_revision_id` is
  never stored or interpreted on its own; it is always recorded as a field
  *inside* an already agent_id-keyed structure (`planned_identities`,
  §5), exactly the way a git blob hash is always found via a tree entry
  that separately records the path, never floating free of its context. The
  payoff is real, not theoretical: two agents that are intentionally kept
  as byte-identical copies (a common authoring pattern — freezing a
  baseline by copying a candidate's directory) archive to the *same* stored
  revision, and a candidate later reverted to match an old baseline
  re-uses that baseline's existing snapshot instead of writing a duplicate.

The fingerprint algorithm itself carries its own version marker
(`AGENT_REVISION_FINGERPRINT_VERSION`, hashed first, exactly like
`LOCAL_SOURCE_FINGERPRINT_VERSION` already does for
`local_source_fingerprint`) so a future change to what's included/excluded
(§2) produces IDs in a distinguishably different space rather than silently
colliding with or shadowing an old one. Because of this, `agent_revision_id`
itself needs no separate version marker in its own hash — the fingerprint
it wraps already carries one.

### 1.3 Storage-key width: full digest, not truncated

Every other `stable_id`-produced identifier in this codebase
(`evaluation_id`, `context_id`, `condition_fingerprint`, …) truncates to 24
hex characters (96 bits) — adequate for a *label*, where a collision would
merely misattribute a display string. `agent_revision_id` is different: it
is used directly as a **storage directory name** in a content-addressed
store (§3), where a collision would silently merge two different agents'
bytes under one path. `agent_revision_fingerprint`/`agent_revision_id`
therefore use the **full 64-character SHA-256 hex digest**, not
`result_model.stable_id`'s truncated form — this is why §1.2 defines
`agent_revision_id` as a plain f-string prefix over the fingerprint rather
than calling `stable_id()` a second time (which would truncate a hash of a
hash, adding indirection without adding safety).

### 1.4 Deliberately excluded from `evaluation_id`'s hash

`agent_revision_id` is **never** folded into `agent_evaluation.py`'s
`_evaluation_id()` payload. Three independent reasons, not one:

1. **It would be a real `IDENTITY_VERSION` bump**, not a cosmetic one —
   `agent_revision_fingerprint` covers strictly more than what
   `agent_identity()` already hashes (manifest fields such as `display`/
   `defaults`, `model.blob`, any other local data file — see §2). Folding
   it in would change what "the same evaluation" means for every existing
   and future evaluation, which is exactly the kind of "silently changing
   wire meaning" `AGENTS.md`'s compatibility rules require to be an
   explicit, justified version bump — not a side effect of an unrelated
   provenance feature.
2. **It would re-couple axes v0.7 deliberately kept separate.** Revision
   identity, evaluation-plan identity, and drift-detection scope are three
   different concerns (§1.1). Folding revision identity into the plan hash
   collapses two of them back into one, for no benefit this spec's actual
   goal (durable archival/inspection/restoration) requires.
3. **It would desynchronize from drift detection.** Drift detection's
   three-way invariant (`evaluation_history.md` §7) is scoped to
   `local_source_fingerprint`/`source_sha256`/`entry_point`/`api_version`/
   `agent_version` — not to the wider revision-fingerprint scope. If
   `evaluation_id` depended on the wider fingerprint but mid-run drift
   detection did not check it, a manifest-only edit (e.g. `agent.yaml`'s
   `display` field) could change what a *future* invocation's
   `evaluation_id` would be while never being caught as drift *within* a
   currently-running evaluation — a confusing split between "what changes
   identity" and "what's actually policed" inside a single feature.

`agent_revision_id` is recorded as additive, non-hashed metadata alongside
the existing hashed identity fields — the same *pattern*
`effective_conditions_fingerprint` already uses (recorded alongside the
hashed payload, reproducible from other recorded fields), even though the
fields it's derived from differ.

### 1.5 What an incomplete revision ID actually identifies

**Clarified explicitly here because reviewer feedback on Phase 2 found the
prior text under-specified this: an `agent_revision_id` always identifies
something real and deterministic, but *what* it identifies differs
materially depending on `AgentFileWalkResult.complete`.**

- **When `complete = True`** (`omitted` is empty): `agent_revision_id`
  identifies the complete set of bytes Bytefray captured — every included
  file's content, in full. This is the only case in which the ID can be
  said to identify *the revision itself* in the ordinary sense: everything
  §2 says should be captured, was.
- **When `complete = False`**: `agent_revision_id` identifies **captured
  content plus omission evidence** — the bytes of every file that *could*
  be included, combined with a explicit, hashed record of what could not
  be (each omission's relative path, reason, and the link's own raw target
  text where available, §2.2). It does **not** identify "the agent's
  complete external execution state." An omitted external symlink target's
  actual bytes are never part of what the ID names, were never read, and
  are not recoverable from the store under any circumstance — the ID
  proves *that* something was excluded and *what it pointed at*, not what
  that target contained or how it behaved.

This distinction is not cosmetic. It is why §8 gates the
"revision-preserved"/"source-reproducible" reproducibility terms strictly
on `complete = True`: an incomplete revision ID is still a legitimate,
useful, deterministic identity for comparison and deduplication purposes
(two incomplete archivals with the same captured content *and* the same
omission evidence really are the same revision; a change to either the
included bytes or which paths were omitted, or where an omitted symlink
now points, correctly produces a different ID) — but it must never be
presented as identifying, or standing in for, a complete, restorable
snapshot of everything that participated in producing an execution result.
`restore_revision` (§7.3) makes this concrete: it writes back exactly the
manifest's `files` list and nothing else, so restoring an incomplete
revision silently reproduces less than the original tree — the omitted
content was never captured to restore in the first place. A future caller
(CLI, evaluation history — §9 Phase 4/5) surfacing a revision to a human
must show `complete`/`omitted` alongside the ID, never the ID alone, for
exactly this reason.

## 2. File inclusion/exclusion contract

Precise, and deliberately not configurable — no `.gitignore`-style pattern
language, no per-agent opt-out. A silently-narrowed revision that omits
files would not actually reproduce the agent; that's a correctness/honesty
problem (`AGENTS.md`'s "fail closed when evidence is insufficient"), not a
convenience worth adding.

**Included:** every regular file, found by recursively walking `agent_dir`,
**except** the exclusions below. This explicitly includes files
`local_source_fingerprint` does not cover today — confirmed against the
actual repository catalog (`agents/bomber/model.blob`,
`agents/chatgpt_hunter/{model.blob,chatgpt_hunter.blob,model.meta.json}`,
and every agent's own `agent.yaml`/`agent.json` manifest).

**Excluded**, by directory name, checked against every path component:

- `__pycache__` — build artifact, matches `local_source_fingerprint`'s
  existing exclusion.
- `.git` — version-control metadata an author's own tooling may have left
  inside an agent directory; not agent source, and unbounded in size.

No extension filter, no size limit. Including every extension (not just
`.py`/`.yaml`) is the entire point of this fingerprint versus the existing
narrower one (§1.1); a size limit would silently produce an incomplete
snapshot. Storage cost for a large `model.blob` that changes on every edit
is a real, accepted cost — documented in §8 as a known limitation, not
solved by silent exclusion.

**Ordering:** POSIX-style relative path (`Path.as_posix()`), lexicographic
sort — identical convention to `local_source_fingerprint`, for the same
reason (stable across platforms and directory-listing order).

### 2.1 Module placement — deliberately *not* shared with `agent_api.py`

The original draft of this spec proposed extracting `local_source_
fingerprint`'s walk/hash logic into `agent_api.py` and rebuilding it on top
of the same shared primitive this feature uses. **That plan changed during
Phase 2 implementation, before any of `agent_api.py` was touched, for a
concrete correctness reason found while implementing, not a style
preference:**

`local_source_fingerprint`'s existing walk uses `Path.rglob("*.py")`.
Whether `rglob`'s `**`-style traversal follows a symlinked *directory* by
default is itself version-dependent in CPython — the `recurse_symlinks`
parameter that makes this an explicit, stable choice was only added in
Python 3.13. On every earlier supported version (this project supports
3.10–3.13), `local_source_fingerprint`'s output for an agent with an
internally-resolving symlinked subdirectory full of `.py` files is
**already, today, independent of this feature — potentially inconsistent
across the Python versions Bytefray supports.** Rebuilding it on top of
this spec's new walker (§2's rule: a directory symlink/junction is *never*
traversed, regardless of Python version — see below) would have been a
real, silent behavior change to `local_source_fingerprint`'s output for
that input shape on pre-3.13 interpreters — exactly what §1.1 promises
this feature will not do to it, and exactly the kind of change that would
require an `IDENTITY_VERSION` bump under `AGENTS.md`'s compatibility rules
if it ever did affect a real evaluation's identity.

Given that risk, `agent_api.py` is **not modified by this feature at all**.
`local_source_fingerprint` keeps its own existing implementation,
unmodified, version-quirks and all — completely out of scope for this
spec to fix. `agent_revisions.py` is fully self-contained: its own walk
primitive (`walk_agent_files`, below) and its own hash primitive
(`_hash_walk_result`) are written once, new, in this module, and used by
both `agent_revision_fingerprint` (identity) and `archive_agent_revision`
(storage) — which is the "shared machinery" property that actually
matters (one walk, reused for both purposes, is what makes §4.2's
provably-frozen-snapshot argument work), just scoped to this module rather
than shared with `agent_api.py`.

### 2.2 Symlinks/junctions — the omission-tracking contract

An unresolvable or deliberately-unwalked entry is never silently dropped.
`walk_agent_files` returns both the included entries and an explicit
`omitted: tuple[OmittedAgentPath, ...]` — each carrying a `relative_path`,
a `reason`, and (when available) the link's own raw target text (read via
`os.readlink`, which inspects the link itself without following it to
whatever it points at — the external destination's *bytes* are never
read). `AgentFileWalkResult.complete` is `True` only when `omitted` is
empty; it is a `@property`, never a separately stored flag, so it can
never independently disagree with the list it summarizes.

- A symlink/junction to a **file**, resolving *outside* `agent_dir`: never
  followed. Recorded as `OmittedAgentPath(reason=REASON_EXTERNAL_TARGET)`.
  This is the case named explicitly in this phase's review instruction —
  Bytefray must never claim a revision is fully preserved while knowingly
  omitting an execution-relevant external target, and now it structurally
  cannot: `complete` is `False` whenever this fires, and the fingerprint
  itself changes based on *which* external target is referenced (below),
  so two revisions differing only in an unpreservable external dependency
  are never mistaken for the same revision.
- A symlink/junction to a **file**, resolving *inside* `agent_dir`: **is**
  dereferenced — its target's actual bytes are read and included as an
  ordinary entry under the symlink's own relative path. The snapshot store
  never contains a symlink and `restore_revision` never creates one — this
  closes an entire class of restore-side risk (§7.3) by construction: since
  nothing `restore_revision` ever writes is a symlink/junction, there is
  nothing to escape through on that side.
- A symlink/junction to a **directory** — *whether it resolves inside or
  outside `agent_dir`* — is **never traversed**, in either case. This is a
  deliberate simplification found necessary during implementation, beyond
  what the original draft specified for files: dereferencing an
  internally-resolving directory symlink safely requires cycle detection
  (a link to one of its own ancestor directories would otherwise recurse
  forever), and an externally-resolving one risks an unbounded walk of
  whatever it points at before any per-file containment check would even
  run. Both risks are avoided by never traversing a directory symlink at
  all: it becomes exactly one `OmittedAgentPath` entry (`reason=
  REASON_INTERNAL_SYMLINKED_DIRECTORY` if it resolves inside `agent_dir`,
  `REASON_EXTERNAL_TARGET` if outside), and the walk continues past it
  without descending. If the same content is also reachable through a real
  (non-symlinked) path elsewhere in the tree, that real path is still
  walked and included normally — nothing is lost for content that has a
  genuine, non-symlinked location inside `agent_dir`.
- `REASON_UNREADABLE` (content read failed after passing every other
  check), `REASON_NOT_A_FILE` (resolves to neither a file nor a directory —
  a broken link, a device file, or a race), and `REASON_RESOLVE_ERROR`
  (`Path.resolve()` itself raised `OSError`, e.g. an intermediate
  permission failure) round out the omission reasons for non-link entries
  and link-resolution failures respectively — every one of these was, in
  `local_source_fingerprint`'s existing code, a silently swallowed
  `continue`. For a fingerprinting-only primitive that's an acceptable,
  narrow drift-detection tradeoff (§1.1); for a primitive whose entire
  purpose is a durable, inspectable archive, silently dropping any of them
  would be the same honesty failure as the external-symlink case, so all
  of them are reported, not just that one.

**Omissions are part of the fingerprint, not just diagnostic output.**
`_hash_walk_result` hashes an `ENTRIES` block (content-based, as before)
followed by an `OMITTED` block (`relative_path`, `reason`, and `target`
text for each omission, sorted). Two trees differing only in which
external target an unresolvable symlink points to are, correctly,
different revisions — "we couldn't fully preserve this" is part of what a
revision *is*, not something that erases its identity. This is why
`agent_revision_fingerprint` never returns `None` for a directory that
exists but has nothing includable — it still returns a real, reproducible
digest over its (possibly empty) entries plus its (non-empty) omissions;
`None` is reserved strictly for "`agent_dir` itself doesn't exist."

## 3. Storage

Content-addressed, under the existing writable data root
(`battle_engine.paths.get_data_root()`), no new root-resolution concept:

```text
<data_root>/agent_revisions/
    agent-revision_<full-sha256-hex>/
        files/
            agent.yaml
            agent.py
            ...                      # every included file, original relative layout
        manifest.json                # bytefray.agent_revision v1
```

`manifest.json`:

```json
{
  "schema": "bytefray.agent_revision",
  "schema_version": 1,
  "agent_revision_id": "agent-revision_<hex64>",
  "fingerprint_version": 1,
  "archived_at": "2026-08-10T18:00:00.000000Z",
  "source_agent_id": "claimer",
  "complete": true,
  "omitted": [],
  "files": ["agent.py", "agent.yaml"]
}
```

(As implemented in Phase 2: `source_agent_id` is an optional parameter on
`archive_agent_revision`, `None` when the caller doesn't supply one; the
`omitted` array holds `{relative_path, reason, target}` objects, §2.2 —
required for `verify_revision` to reconstruct the exact original
fingerprint, since omitted content was, by design, never copied into the
store to begin with.)

`source_agent_id` and `archived_at` are informational only (which catalog
directory happened to produce this content, and when it was first seen) —
never part of the identity, never trusted as "the" agent this content
belongs to (the same content can legitimately be archived under a different
`source_agent_id` later, per §1.2's dedup argument; the first writer's
`source_agent_id` is kept, never overwritten, since content-addressed dedup
means a second archival of identical content is a no-op).

No directory sharding (no git-style two-character prefix split). v0.7 §16
already established the precedent of not adding structure (an index) until
measurement demonstrates it's needed; revision counts are dedup-capped by
construction (only genuinely distinct content produces a new directory) and
are expected to be small even for an actively-edited agent. Documented here
as a deliberate, revisitable choice, not an oversight.

**Atomicity.** Write to a sibling temp directory
(`agent_revisions/.tmp-<uuid4>/`) fully, including `manifest.json`, then
`os.replace` the temp directory onto the final `agent-revision_<hex>/`
path. If the final path already exists (a concurrent writer, or the same
content archived on an earlier run), the write is redundant by
construction — content-addressing guarantees the existing directory
already holds identical bytes — so the temp directory is discarded
(best-effort cleanup) rather than treated as a conflict. This mirrors
`result_model.write_json_atomic`'s temp-then-rename discipline, extended
from one file to a directory tree.

**Containment.** Every path written under `files/` is verified contained
beneath that revision's own directory before being written (reusing the
resolve-then-`relative_to` discipline `paths.contained_path` and
`local_source_fingerprint` both already use) — defense in depth even
though the source here is Bytefray's own archival walk, not untrusted
external input; cheap insurance against a future caller reusing this
primitive with less-trusted input.

## 4. Freeze-time integration — provably the frozen revision

### 4.1 The problem with a naive "snapshot on first use"

An earlier version of this design proposed archiving lazily, when a cell
using that agent first actually executes. That is wrong for exactly the
reason `evaluation_history.md` §7 spends several paragraphs establishing
for drift detection: a read that happens *later* than the freeze point can
observe different bytes than the freeze point itself did, with nothing
tying the two together. "The tree present when the first cell executes" is
not "the revision frozen by evaluation planning" — it's a second,
independent, later read of a possibly-different tree.

### 4.2 What actually happens: archival inside the freeze step itself

**Implemented in Phase 3 (§9, done) — this subsection describes the design
as implemented.** `EvaluationService.run()` already has exactly one moment
where every subject's identity is frozen, once, before anything else
happens (`agent_evaluation.py`, current line ~1059):

```python
planned_identities = {agent_id: agent_identity(spec) for agent_id, spec in specs.items()}
```

Revision archival must happen **immediately after this line, before
`evaluation_id`/`matrix`/any checkpoint write** — not deferred to cell
execution. Phase 2 (§9) already delivers the primitives this needs:
`agent_revisions.walk_agent_files(spec.dir)` performs the single directory
walk (§2.2), and its `AgentFileWalkResult.entries` includes every
`.py`-suffixed file's already-read content, from which a caller can derive
a value directly comparable to `agent_identity()`'s
`local_source_fingerprint` (same version marker, same sorted-`\0`-joined
accumulation `local_source_fingerprint` itself uses — reusing that
algorithm on the `.py` subset of an *already-completed* walk, not issuing
a second, independent read of the same files under a different code path).

The one design point genuinely left open for Phase 3, rather than
prematurely fixed here: `archive_agent_revision` (Phase 2) performs its
own internal call to `walk_agent_files`. Phase 3's integration needs that
walk's `.py`-subset content for the cross-check *before* deciding whether
archival should even be attempted (§4.3 — a mismatch must abort before any
store write). Whether Phase 3 calls `walk_agent_files` once itself and
passes the result into a lower-level archive-from-walk function (avoiding
`archive_agent_revision`'s internal re-walk), or accepts a second walk as
an acceptable cost at this single freeze-time call site, is a Phase 3
implementation decision — flagged here so it isn't silently improvised
mid-integration, not resolved by this phase.

Conceptually, whichever shape Phase 3 takes: **if the cross-check
fingerprint and the plan's own recorded `local_source_fingerprint` match,
the archival walk's bytes and the plan's own recorded fingerprint agree on
every `.py` file's content, checked as close in time to the freeze as this
process can get; if they disagree, the tree visibly changed between those
two adjacent reads, and the evaluation must not proceed under a plan that
no longer matches what's about to be archived (or executed).**

This is deliberately **not** presented as closing every conceivable race —
`evaluation_history.md` §7 already documents, and does not claim to close,
a narrower residual window for the existing drift checks (a durable
edit-then-revert timed precisely between two reads). The same honest
framing applies here: this check narrows the window to "between two reads
inside one freeze step, milliseconds apart, before any cell has run,"
proves the archived snapshot corresponds to that freeze step's own
recorded identity, and does not claim more.

### 4.3 Fail-closed only for the mismatch case, not for plain I/O failure

Two distinct failure classes, deliberately handled differently:

- **Fingerprint mismatch** (§4.2's comparison fails): the plan and the
  archive provably disagree. This is a fail-closed condition —
  `EvaluationConfigurationError` is raised, the whole `run()` call aborts
  before `evaluation_id` is computed, before `build_matrix`, before any
  checkpoint is written. No `evaluation.json` is created or modified. This
  matches existing preflight-failure behavior (`_validate`'s own errors)
  rather than inventing a new lifecycle state — nothing has been
  persisted yet for there to be a lifecycle state of.
- **Plain I/O failure** (a file couldn't be read during the walk, or the
  snapshot couldn't be written to `agent_revisions/` — disk full,
  permissions): non-fatal to the evaluation. `archive_agent_revision`
  catches the failure, and `RevisionArchivalResult.archived=False` /
  `error="<typed reason>"` is recorded (§5) rather than raised. Archival
  is new, additive infrastructure; a filesystem hiccup in it must not take
  down the evaluation feature that already works today. What must not
  happen is silently claiming a snapshot exists when it doesn't — §5
  covers exactly how that's recorded honestly instead.

### 4.4 Scope: this does not change drift detection

Nothing above modifies `_execute_cell`, the pre-check, the post-check, or
the three-way invariant. Revision archival is a parallel, additive
mechanism that runs once at freeze time and is never consulted by drift
detection. This is a deliberate scope boundary, not an omission — folding
it in would mean touching the exact TOCTOU-hardened code path the v0.7
closure passes spent two adversarial-review rounds getting right, for a
concern (durable archival) that doesn't need it.

## 5. Integration with evaluation artifacts

### 5.1 Where the fields live — revised during implementation

**This subsection was revised after Phase 3 implementation found the
original design below actively wrong, not merely imprecise: it broke an
existing, tested v0.7 invariant. Recorded here for the same reason §0
records the pre-implementation revision — so the mistake and its fix are
both on the record, not silently corrected.**

The original text proposed adding `agent_revision_id`/`agent_revision_error`
directly inside each rendered entry of `planned_identities.{candidate,
baseline,opponents[]}`, reasoning that this reused the existing structure
instead of adding sibling top-level fields. Implementing it exactly that
way broke `test_persisted_planned_identity_rehashes_to_the_recorded_
evaluation_id` and two sibling tests — the existing, load-bearing "B1"
invariant (`evaluation_history.md` §7's closure-pass language) that
recomputing `evaluation_id` from `planned_identities` **as persisted in
the artifact itself** must reproduce the stored value exactly. A reader
doing that recompute — which is precisely what those tests, and by
extension any future consumer relying on the same documented contract,
legitimately do — would rehash the two new keys right along with
everything else, since they were sitting inside the same object, and get
a different value than the one actually stored.

The fix: `agent_revision_id`/`agent_revision_error` live in a **wholly
separate, sibling top-level field**, `agent_revisions`, structured the
same role-keyed way (`candidate`/`baseline`/`opponents`) but carrying only
the two revision fields — no `agent_id`, no identity fields, nothing
`planned_identities` already has:

```json
"planned_identities": {
  "candidate": {
    "agent_id": "claimer", "kind": "python", "api_version": 1,
    "agent_version": "1.0", "entry_point": "agent.py:create_agent",
    "source_sha256": "...", "local_source_fingerprint": "..."
  },
  "baseline": null,
  "opponents": [ "...unchanged from v2, byte-for-byte..." ]
},
"agent_revisions": {
  "candidate": {
    "agent_revision_id": "agent-revision_<hex64>",
    "agent_revision_error": null
  },
  "baseline": null,
  "opponents": [ "...one entry per ordered occurrence, same positions as planned_identities.opponents..." ]
}
```

`planned_identities` is therefore **byte-for-byte identical** to what a
pre-Phase-3 (v2) artifact would have written for the same inputs — not
merely "unchanged in spirit," but literally the same object, written
twice with zero transformation. `agent_revisions.opponents[i]` corresponds
to `planned_identities.opponents[i]`/`request.opponent_ids[i]` by
position, the same ordered-list convention already used throughout this
codebase (e.g. `_evaluation_id`'s own `identities[opponent_id] for
opponent_id in request.opponent_ids`) — it carries no `agent_id` of its
own to correlate by, deliberately, so it can never be mistaken for
something safe to merge back into `planned_identities`.

`agent_revision_error` is `null` when archival succeeded (or the agent has
no eligible files at all, e.g. a hypothetical non-Python/non-blob agent
with nothing to archive); a short, typed string
(`"snapshot_write_failed: <reason>"`) when
`RevisionArchivalResult.archived` was `False` for that agent in *this*
evaluation run. It is a historical fact about what happened when this
evaluation executed, not a live claim about the store's current state
(§6 explains why that distinction matters).

### 5.2 The structural safeguard against contaminating `evaluation_id`

`agent_identity()` itself is **not modified** — it returns exactly what it
returns today. `planned_identities` (the dict `_evaluation_id()` hashes,
per §1.4) is likewise never mutated to carry revision fields, and — per
5.1's revision — is not even copied or reshaped to carry them; the exact
same dict object is used both to compute `evaluation_id` and to populate
`planned_identities` in the written JSON. Revision fields are rendered
into a completely separate object (`agent_revisions_payload`) that is
written under its own top-level key. This is a structural guarantee, not
a convention to remember: there is no code path by which a revision field
can reach `evaluation_id`'s hash input, or even reach the same JSON
sub-object a future reader might reasonably choose to rehash, because the
two are different keys in the artifact from the start.

### 5.3 Schema version

Additive new fields on the wire shape → `SCHEMA_VERSION` (currently 2) →
**3**, per `AGENTS.md`'s "bump the version and update the schema doc rather
than silently changing wire shape in place." `IDENTITY_VERSION` stays
**3**, unchanged — by §1.4, nothing about what `evaluation_id` hashes has
changed. v1 and v2 artifacts remain fully readable and are never mutated;
a v1/v2 artifact simply has no `agent_revisions` field, which
`evaluation_history`'s adapters represent as
`ConfidenceValue(None, FieldConfidence.UNKNOWN)` — the existing pattern for
every other legacy-absent field, not a new one (implemented in a later
phase — see §5.4's clarified boundary).

A v2 artifact is not *resumable* under `SCHEMA_VERSION == 3` code
(`_load_state`'s pre-existing `schema_version` gate rejects the mismatch)
— the same "old artifact needs a fresh evaluation" pattern v1 → v2 already
established, unchanged behavior, not a new restriction this phase adds.

**One compatibility fix was required in Phase 3, not deferred to Phase
4.** Discovered by the full regression suite, not anticipated by the
original plan: `evaluation_history/discovery.py`'s schema-version routing
and `v2_adapter.py`'s `SUPPORTED_V2_VERSIONS` both gated on the literal
`2`. Since `SCHEMA_VERSION` bumping to 3 means every evaluation run under
this phase's code now *writes* schema_version 3, leaving that gate
untouched would have made `bytefray agents evaluations list/show/compare`
— already-shipped, working v0.7 functionality — report
`HealthCode.UNSUPPORTED_VERSION` for every fresh evaluation, an outright
regression, not a deferred feature. The fix widens both gates to accept
`(2, 3)` and nothing else: no new field is exposed, `AdaptedCell`/
`EvaluationSummary` gain no revision-aware members, `--verify` is
unchanged. `agent_revisions` is read by nothing in `evaluation_history` yet
— it is simply no longer a reason to reject the whole artifact. This is
the narrowest fix that avoids the regression without doing any of the
actual Phase 4 work described in §5.4.

### 5.4 `evaluation_history` / CLI — done (§9 Phase 4)

Beyond §5.3's compatibility floor: `evaluation_history/models.py`'s
`AdaptedCell` gained `opponent_agent_revision_id`/
`opponent_agent_revision_error: ConfidenceValue` (per-cell, positionally
correlated against `agent_revisions.opponents` the same way
`opponent_identity` already correlates against
`planned_identities.opponents`) and `opponent_revision_verification:
RevisionVerificationStatus`; `EvaluationSummary` gained the equivalent
`candidate_*`/`baseline_*` fields, computed once per role like
`candidate_identity`/`baseline_identity` already are, since a role's
revision id does not vary per cell the way an opponent's does. `--verify`
gains the deep check described in §7.2. `bytefray agents evaluations show`
prints the revision ID (and archive error, and verification status once
`--verify` populated it) next to each role when present, in an `agent
revisions:` block. As anticipated, none of this touches `comparison.py`'s
alignment logic (§1.4 already keeps revision identity out of anything
comparison keys on).

## 6. Why there is no persisted `agent_revision_available`

The earlier draft proposed a persisted boolean asserting whether a
snapshot is available. Rejected: "available" is a fact about the **live
state of the revision store's filesystem**, checked at
`agent_revisions/<id>/` right now — not a fact about the evaluation's own
plan. It can become false immediately after being recorded true (someone
deletes `agent_revisions/`, a disk is cleaned up, a directory is copied to
a machine without the store) or become true after being recorded false
(archival retried later, a backup restored). Persisting it bakes a
snapshot-in-time claim about external, independently-mutable state into an
artifact this project otherwise treats as artifact-authoritative — exactly
the failure mode v0.7 already guards against elsewhere (`file_modified_at`
is never substituted for a real timestamp; a stored `aggregates`/
`comparison` block is never trusted over recomputing from `cells`).

**Availability must always be checked live**, by `bytefray agents
revisions show <id>` (§7.1) attempting to read the store, never inferred
from anything written into `evaluation.json`. What *is* legitimately a
one-time historical fact, and is kept (§5.1), is `agent_revision_error`:
whether the archival **attempt** made during this specific evaluation run
succeeded — that's immutable after the fact (it already happened, in the
past, during this run) in a way that "is a copy present on disk right now"
is not.

## 7. CLI — done (§9 Phase 5, `agent_revisions_cli.py`)

```text
bytefray agents revisions list <agent-id>
bytefray agents revisions show <revision-id>
bytefray agents revisions restore <revision-id> [--to <dir>] [--force]
```

No `diff`, no `test --revision`, no Designer UI in v0.8 — the smallest
coherent set per the parent task's §8. Rerunning a historical revision is
achieved *compositionally*: `restore` writes the snapshot to an explicit
target, and the user runs the existing `bytefray agents test`/`agents
evaluate` against that restored copy like any other agent directory — no
new, parallel execution path to keep in sync with the real one (proven by
`engine/tests/test_agent_revision_lifecycle.py`, which restores into
`agents/` and then runs `agents validate` against the restored id). This
mirrors v0.7's own precedent of deferring Designer history UI when the
domain/CLI layer is substantial enough on its own
(`evaluation_history.md` §17). Wired into `bytefray`'s existing `agents`
dispatcher (`command.py`) alongside `evaluations`/`inspect`/`diverge`.

### 7.1 `show`

Reads `manifest.json`, recomputes `agent_revision_fingerprint` live from
`files/` (via §2.1's shared walk/hash primitives), and reports
`verified: bool` — `True` only when the recomputed fingerprint matches the
directory name. This is the live availability/integrity check §6 requires
instead of a persisted boolean; a `False` result (or the directory being
absent/malformed entirely) is reported as a typed diagnostic, not a crash
— matching `evaluation_history`'s existing "malformed artifact never
aborts discovery of siblings" discipline, scoped here to one revision.

### 7.2 `--verify` integration — done (evaluation_history)

`evaluation_history/verification.py`'s `verify_summary` (not `verify_cell`
directly, since a role's revision id is checked once, not once per cell —
see §5.4) checks, for the candidate/baseline and each distinct opponent
revision id referenced by any cell, whether that revision's stored
fingerprint still matches its own directory name (the same check `show`
performs) via `RevisionVerificationStatus`: `NOT_CHECKED` (no recorded id,
or `--verify` not requested), `NOT_AVAILABLE` (recorded id, no matching
local snapshot — degrades to skipped, never a hard failure, exactly as
originally specified here), `INVALID` (a snapshot is present but fails to
verify — corrupted/tampered/malformed; this **is** a hard failure,
surfaced through `SummaryVerification.revision_issues` and
`all_eligible_verified`), or `VERIFIED`. Never falls back to live agent
source under any circumstance.

### 7.3 `restore`

Never writes to `agents/<id>/` implicitly. Default target (no `--to`):
`<data_root>/agent_revisions_restored/<revision-id>/`. An explicit `--to
<dir>` that already exists and is non-empty is refused unless `--force`.
`--force` permits writing/overwriting the manifest's own file paths; it does
not delete unrelated target files or reconcile the directory to an exact
snapshot. It creates no backup: if a later I/O error follows a matching-file
overwrite, best-effort cleanup cannot reconstruct the former bytes and may
leave the forced target partially changed.
Every write is resolved through the same contained-path discipline as
storage writes (§3) — restoring is "trusted store → filesystem," but the
same discipline applies as insurance against a hand-edited or corrupted
`manifest.json`, and also against a pre-existing symlink/junction inside
an already-populated (`--force`) target directory that a restored path
would otherwise traverse through and write outside the target (verified
directly against a real destination-side junction, not just a corrupted
manifest, in `test_restore_rejects_escape_through_preexisting_destination_
link`). Nothing restored is ever a symlink (§2's dereference rule), so
there is no restore-*source*-side symlink-escape surface to defend against.

**Added during Phase 5:** `restore_revision` now also refuses to write
*anything* to the target when the canonical snapshot itself does not
verify (the same fingerprint-reconstruction check `verify_revision`/`show`
run, called before the write loop rather than only offered as a separate,
skippable step) — a corrupted, tampered, or hand-edited canonical snapshot
fails restoration closed instead of silently reproducing untrustworthy
bytes into a target the caller is about to treat as trusted.

## 8. Reproducibility contract

Three explicit, independently-limited terms — never "reproducible"
unqualified:

- **revision-preserved** — requires `complete = True` (§1.5: no omissions).
  Only then are the archived snapshot's bytes proven, by fingerprint, to be
  the *entire* set of files `agent_revision_id` covers, and (§4) to be what
  evaluation planning actually froze. **An incomplete revision (`complete =
  False`) must never be described as "revision-preserved."** See §1.5 for
  what an incomplete revision ID identifies instead, and why that is a
  materially weaker claim than preservation.
- **source-reproducible** — likewise requires `complete = True`. A restored
  revision (§7.3) can be run through the ordinary `agents test`/`agents
  evaluate` boundary and will present the identical source to the loader
  *only if nothing was omitted* — `restore_revision` writes back exactly
  the captured `files` list and nothing else, so a restored incomplete
  revision silently reproduces less than the original tree (§1.5). Even
  when `complete = True`, this says nothing about outcome determinism
  beyond what v0.7 already guarantees for a live agent.
- **environment-compatible** — the *current* environment's
  `ExecutionContext` is compatible with the historical one recorded for a
  given evaluation, reusing `comparison.py`'s existing
  `_contexts_compatible` check rather than inventing a second notion of
  compatibility. Independent of completeness — an environment can be
  compatible for a revision that was never fully captured, and vice versa.

External dependencies, interpreter version, OS, and anything outside an
agent's own directory remain explicitly out of scope — exactly the
boundary `evaluation_history.md`'s "External imports/dependencies
limitation" section already draws for drift detection. A revision-store
snapshot does not change that boundary; it preserves what was always
inside it.

**Known storage-cost limitation** (documented, not solved here): a
`model.blob` or other large local data file that changes on every edit
produces one full extra copy per distinct revision, since content-addressed
dedup only helps when bytes repeat. No cleanup/garbage-collection command
exists in v0.8 — left as a follow-up if usage ever demonstrates it's
needed, matching v0.7 §16's own precedent for not building infrastructure
ahead of measured need.

## 9. Implementation phases

1. **This spec.** (initial deliverable, revised twice — §0)
2. **Engine primitive — done.** `engine/src/battle_engine/agent_revisions.py`:
   `walk_agent_files`/`AgentFileWalkResult`/`OmittedAgentPath` (§2.2's
   canonical tree-walk, entirely self-contained per §2.1 — `agent_api.py`
   is untouched), `agent_revision_fingerprint`/`agent_revision_id` (§1),
   `archive_agent_revision`/`RevisionArchivalResult`/`_write_snapshot`
   (§3), `read_manifest`/`list_revisions`/`verify_revision`/
   `restore_revision` (§7.1/§7.3). Qt-free, headless-importable, no
   dependency on `agent_evaluation.py`. Tested by
   `engine/tests/test_agent_revisions.py` (§10). `RevisionArchivalResult`
   as actually implemented: `agent_revision_id: str | None`,
   `complete: bool`, `omitted: tuple[OmittedAgentPath, ...]`,
   `archived: bool`, `error: str | None` — no `local_python_fingerprint`
   field, since that cross-check is meaningless without a frozen plan to
   compare against, and belongs to Phase 3 (§4.2) instead.
3. **`EvaluationService` integration — done.** §4's freeze-step archival
   and fail-closed check (`EvaluationService._resolve_revision_results`,
   called after `prior` is loaded, before `matrix`/any checkpoint/any cell
   execution); §5's serialization-boundary rendering into the
   `agent_revisions` sibling field (revised mid-implementation — §5.1);
   `SCHEMA_VERSION` → 3. `agent_revisions.py` gained
   `archive_agent_revision_from_walk`/`local_python_subset_fingerprint`
   (both absent from the original Phase 2 description) specifically to let
   this phase's freeze step derive the cross-check fingerprint and the
   archive write from one shared walk, per §4.2. Also required — found by
   the full regression suite, not anticipated by the original plan — a
   narrow `evaluation_history` compatibility fix (§5.3): without it, every
   fresh evaluation would have been unreadable by the already-shipped
   `list`/`show`/`compare` commands. Tested by
   `engine/tests/test_agent_evaluation_revision_capture.py` (§10.2).
4. **`evaluation_history` integration — done** (beyond §5.3's compatibility
   floor). `evaluation_history/models.py` gained `RevisionVerificationStatus`
   (`NOT_CHECKED`/`NOT_AVAILABLE`/`INVALID`/`VERIFIED` — §7.2's four
   deliberately distinct outcomes) and, mirroring where
   `candidate_identity`/`baseline_identity`/`opponent_identity` already
   live: `EvaluationSummary.candidate_agent_revision_id`/
   `candidate_agent_revision_error`/`baseline_agent_revision_id`/
   `baseline_agent_revision_error`/`candidate_revision_verification`/
   `baseline_revision_verification` (computed once per role, like the
   identity fields), and `AdaptedCell.opponent_agent_revision_id`/
   `opponent_agent_revision_error`/`opponent_revision_verification`
   (per-cell, positionally correlated against `agent_revisions.opponents`
   exactly the way `opponent_identity` already correlates against
   `planned_identities.opponents`). `v2_adapter.py` reads the new
   `agent_revisions` sibling field the same defensive way it already reads
   `planned_identities` — a non-dict/missing entry, or a field of the wrong
   type, degrades that one field to `UNKNOWN`, never raises, and never
   affects a sibling role/opponent's fields. `v1_adapter.py` is untouched
   (v1 never had this concept; every revision field on a v1-adapted summary
   defaults to `UNKNOWN` via the dataclass defaults). `verification.py`'s
   `verify_summary` gained a `data_root: Path | None = None` parameter
   (live `get_data_root()` by default, §6) and now also returns local
   revision-store evidence: for the candidate/baseline (once) and for each
   distinct opponent revision id referenced by any cell (cached, not
   recomputed per cell), it checks — never against live agent source, only
   the store — whether a snapshot directory exists at all (`NOT_AVAILABLE`
   if not: a copied/relocated artifact or a cleaned-up store is never
   reported as corruption) and, if so, whether it verifies
   (`verify_revision`; `INVALID` if not — this is the one outcome that
   counts as a verification failure). `SummaryVerification` gained
   `revision_issues: tuple[str, ...]`, and `all_eligible_verified` now also
   requires it to be empty. `evaluation_history/cli.py`'s `show`/`compare
   --verify` surface `revision_issues` in `verify_error` the same way a
   failed cell already is, and `show` prints a `agent revisions:` block
   naming each role's revision id (or `unknown`), archive error if any, and
   verification status once `--verify` populated it.
5. **CLI — done.** `agent_revisions_cli.py`:
   `bytefray agents revisions list <agent-id>` (relevance = recorded
   `source_agent_id` match **or** a live fingerprint match against the
   agent's *current* on-disk content, since dedup means `source_agent_id`
   can legitimately name a different catalog entry than every agent whose
   content matches — §1.2; malformed sibling manifests are counted and
   skipped, never fatal to the listing); `show <revision-id>` (manifest
   fields, omission list, live `verify_revision` result, `--json`);
   `restore <revision-id> [--to <dir>] [--force]` (default target
   `<data_root>/agent_revisions_restored/<revision-id>/` per §7.3, an
   incomplete revision's restore prints an explicit `WARNING`, never a bare
   success line). Wired into `command.py`'s existing `_agents` dispatcher
   (`bytefray agents revisions ...`) the same way `evaluations`/`inspect`/
   `diverge` already are. **One correctness gap found and fixed while
   implementing `restore`, not merely offered as a CLI-level guard:**
   `agent_revisions.restore_revision` itself (not just the CLI) now calls
   the same `_verify_snapshot_dir` check `verify_revision`/`show` use,
   *before* writing any file to the restore target — a corrupted, tampered,
   or hand-edited canonical snapshot now fails restoration closed, with
   nothing written, rather than silently reproducing untrustworthy bytes
   into a target the caller is about to treat as trusted (§7.3's "malformed
   snapshot must fail before writing trusted output" requirement).
6. **Docs/tests/hardening — done (this pass).** This document; see
   `ARCHITECTURE.md`, `CHANGELOG.md` `[Unreleased]`, and
   `engine/tests/{test_agent_revisions.py,test_agent_revisions_cli.py,
   test_evaluation_history_revisions.py,test_agent_revision_lifecycle.py,
   test_agent_evaluation_revision_capture.py}` for the corresponding
   adversarial test pass (§10.3).

Designer UI is not a phase — deferred, matching v0.7's own precedent
(`evaluation_history.md` §17).

**Landed in v1.1** (`docs/ROADMAP.md`'s "Evaluation Insight & Designer
Polish"), as part of the same Evaluation History browser
`evaluation_history.md` §17 records: `RevisionBrowserDialog`
(`app/views/evaluation_history.py`), reachable from a selected evaluation's
"Show Revision…" button, is a read-only inspector over one revision's
manifest — files, omissions, `complete`, and a live `verify_revision`
result, mirroring `bytefray agents revisions show`'s own field selection.
It also does something the CLI's `show` does not: given the role's own
evaluation-time agent id (candidate/baseline/opponent), it live-compares the
archived revision against that agent's *current* on-disk content and reports
one of "matches the current source," "changed since this evaluation was
run," or "this agent id no longer exists" — closing the "does this still
match current source" question this document's own introduction and §8
raise, using only the existing `agent_revision_fingerprint`/
`agent_revision_id` primitives (no new engine code). **GUI revision
`restore` remains explicitly deferred** — the Designer only ever reads the
store; writing to it (restoring a snapshot to a target directory) stays a
CLI-only operation (`bytefray agents revisions restore`) for this milestone.

**Implemented and release-prepared for v1.3.0** (`docs/ROADMAP.md`'s
"Designer Workflow Completion").
`RevisionBrowserDialog` gains an explicit **"Restore Files…"** action, opening a
new `RestoreRevisionDialog` (`app/views/evaluation_history.py`) that shows
the archived revision's completeness and the same live current-source-drift
check `RevisionBrowserDialog` already computes, then a target-directory
field (pre-filled with the identical default `bytefray agents revisions
restore` uses, `<data_root>/agent_revisions_restored/<revision_id>/`) and an
unchecked `--force`-equivalent option allowing writes into a non-empty
target. Confirming calls the authoritative `agent_revisions.restore_revision`
directly — no Qt-side reimplementation of restore containment or fail-closed
snapshot verification.

The wording is deliberately **files**, not directory replacement. With the
non-empty-target option enabled, matching archived paths are overwritten but
unrelated files already in the target remain; restore does not delete them
or promise that the resulting tree is an exact snapshot. Without that option
a non-empty target remains a failure before writes. The separate default
target is never an existing `agents/<id>/` directory, so an ordinary restore
cannot overwrite live agent source by accident.

A user may still type a target inside the live `<data_root>/agents/` catalog,
as with CLI `--to`, but the Designer recognizes the catalog root, an agent
directory or descendant, and lexical/resolved aliases into that catalog. It
requires an additional confirmation naming the affected agent where that is
unambiguous (otherwise treating the whole catalog as affected) and stating
the overwrite/retain semantics. Restore is disabled while a Designer-owned
subprocess is active, including for the remainder of a still-open History
session after it launches an Agent Lab run, although read-only history/revision
browsing remains available. After a successful live-target restore it
automatically refreshes discovery, keeps that exact agent id selected, and
invalidates any displayed validation/test/replay/trace evidence derived from
the pre-restore source. The user must validate/test the restored files
again. A restore outside the live catalog does not claim to change the
catalog. This closes the one deferral this section names above; no revision
identity or manifest schema changed.

## 10. Testing and validation criteria

### 10.1 Phase 2 — done (`engine/tests/test_agent_revisions.py`)

- `agent_revision_fingerprint` determinism: identical tree → identical
  fingerprint across repeated calls and across a relocated/renamed
  directory (fingerprint must not depend on the absolute path or name).
- Fingerprint changes when any included file's content changes; does not
  change when only file *mtimes* change (content-only hashing).
- Manifest-only edit (`agent.yaml`'s `display`) changes
  `agent_revision_fingerprint` — grounds §1.4's argument for why this must
  stay out of `evaluation_id`; the other half of that claim (that it does
  **not** change `evaluation_id`) can only be asserted once Phase 3 exists
  to compute one.
- `__pycache__` and `.git` are excluded entirely (not even reported as
  omitted); a file outside those directories with any other name/extension
  is included (`model.blob`, `model.meta.json`, dotfiles).
- A file-symlink resolving outside `agent_dir` is reported as
  `OmittedAgentPath(reason=REASON_EXTERNAL_TARGET)`, never silently
  dropped and never read; one resolving inside is dereferenced and its
  target bytes are both hashed and archived (never written to the store as
  a symlink). Proven both via real symlinks where the sandbox allows
  (`pytest.skip` otherwise — needs Developer Mode/admin on Windows) and,
  independent of that OS privilege, via a monkeypatch-based test that
  exercises `_walk_dir`'s branch logic directly.
- A directory symlink/junction is never traversed either way (inside or
  outside `agent_dir`) — exactly one omission entry, and (for the internal
  case) the same content reached via its real, non-symlinked path is still
  included and not duplicated under the symlinked path. Proven with a real
  Windows NTFS junction (`mklink /J`, which needs no special privilege,
  unlike a symbolic link) so this runs for real without elevation.
- Completeness/fingerprint both reflect omissions: a tree with an omission
  fingerprints differently from an otherwise-identical tree without one.
- Two distinct agent directories with byte-identical included content
  dedup to one stored revision (§1.2's dedup claim, directly asserted by
  inspecting the store, not just the returned ID); `source_agent_id`
  records the first writer and is not overwritten by the second.
- Snapshot store write is atomic: an interrupted write (simulated via a
  monkeypatched `Path.write_bytes` failure) never leaves the final
  `agent-revision_<hex>/` path visible, only a discardable temp directory.
- A store-write failure (`archived=False`) does not change
  `agent_revision_id`/`complete` versus a successful archival of identical
  content elsewhere — §6's "error is informational and non-identity-bearing"
  directly asserted, not merely argued.
- `verify_revision` detects a tampered stored file (`False`), and correctly
  reconstructs and verifies a revision that has recorded omissions (the
  store's own copy alone is not enough — verification must combine it with
  the manifest's `omitted` list, §7.1).
- `restore_revision` round-trips: restoring a snapshot and re-fingerprinting
  the restored copy equals the original fingerprint; refuses a non-empty
  target without `force=True`; rejects a hand-corrupted manifest
  referencing a `..`-relative, sibling-store-escaping, or Windows
  drive-qualified/UNC path, on both the store side and the target side.
- `list_revisions` ignores in-progress `.tmp-*` directories.
- `agent_revisions.py` headless-import test (no Qt/pygame), mirroring
  `evaluation_history`'s own.

### 10.2 Phase 3 — done (`engine/tests/test_agent_evaluation_revision_capture.py`)

- Revision capture and planned identity describe the same source read:
  the archival walk's `.py`-subset fingerprint equals the frozen plan's
  own `local_source_fingerprint`, and the archived revision independently
  verifies (`verify_revision`) against the live store.
- Opponent revisions are captured too, and duplicate opponent occurrences
  (the same opponent listed twice in one request) share one revision ID
  at both positions.
- §4.2's mismatch case, via real filesystem mutation (not a mocked return
  value): a candidate source edit injected between `agent_identity()`'s
  read and the archival walk's read aborts `EvaluationService.run()` with
  `EvaluationConfigurationError`, proven for both a minimal one-opponent
  matrix and a larger multi-opponent/multi-seed one. `evaluation.json` is
  never written at all (asserted by its absence, not just the raised
  exception), and `EvaluationService._execute_cell` is asserted to have
  been called zero times (a monkeypatch spy, not an inference from "no
  file was written") — direct proof no cell executed.
- Resume/retry retains the originally planned revision ID: a manifest-only
  edit after a finished evaluation (changes `agent_revision_fingerprint`,
  confirmed by recomputing it fresh, but not `local_source_fingerprint`/
  `evaluation_id`) does not change the resumed artifact's recorded
  `agent_revision_id` for either the candidate or an opponent (the latter
  exercising the positional `opponent_ids`/`agent_revisions.opponents`
  correlation specifically).
- Revision-store write failure is recorded, never silently substituted:
  a blocked `agent_revisions/` path still lets the evaluation finish, with
  `agent_revision_error` non-null and `agent_revision_id` equal to what a
  working store would have computed for the identical source — and
  `evaluation_id` itself is asserted byte-identical between a working-store
  run and a broken-store run of the same inputs.
- `planned_identities` carries no revision fields at all (§5.1/5.2's
  structural safeguard, asserted directly on the written JSON, not just
  inferred from `evaluation_id` matching) — `agent_revisions` is a
  separate top-level key.
- A v2-shaped artifact (schema_version 2, no `agent_revisions` key —
  the exact shape a pre-Phase-3 build wrote) fails resume via the existing,
  pre-Phase-3 `_load_state` schema gate with its documented message, not a
  new `KeyError` from the revision-lookup code; `_prior_revision_by_
  agent_id` is separately given direct unit coverage for a missing/
  malformed `agent_revisions` key, since `_load_state`'s own gate makes
  that branch unreachable through `run()` itself today.
- Full existing suite (`engine/tests`, `client/tests`) re-run after every
  change in this phase — two pre-existing tests needed updating (hardcoded
  `schema_version == 2` literals, now comparing against the `SCHEMA_VERSION`
  constant instead so they don't go stale on the next legitimate bump), and
  `evaluation_history`'s `SUPPORTED_V2_VERSIONS` needed widening (§5.3) —
  no other regressions.

### 10.3 Phases 4–6 — done

`engine/tests/test_evaluation_history_revisions.py`:

- v1 artifacts and v2-shaped artifacts (schema_version 2, genuinely no
  `agent_revisions` key) read every revision field as `UNKNOWN`, never a
  guessed or false `RECORDED` value.
- v3 artifacts expose `RECORDED` candidate/baseline/opponent revision ids
  and archive errors.
- A malformed `agent_revisions.candidate` entry (wrong type entirely)
  degrades only that role to `UNKNOWN` — baseline and opponent fields,
  read from different keys, are unaffected; same for a malformed opponent
  entry's `agent_revision_id` (wrong JSON type) leaving candidate/baseline
  untouched.
- Duplicate/self-play opponent occurrences (same opponent id at more than
  one matrix position) resolve to the one shared revision id
  unambiguously, never `None`/split across positions.
- `verify_summary` without `data_root` never touches revision evidence
  until called (`NOT_CHECKED` on plain `adapt_any` output); with a
  `data_root` pointing at the real store, candidate/baseline/opponent all
  report `VERIFIED` and `revision_issues` is empty; pointed at an empty
  store, all report `NOT_AVAILABLE` — not a crash, not treated as
  corruption, and the *cell's* own match/replay verification is
  unaffected (independent evidence dimensions); with a tampered stored
  file, the affected role reports `INVALID`, `revision_issues` is
  non-empty, and `all_eligible_verified` is `False`.
- Editing the live agent after evaluation does not change what deep
  verification reports (`VERIFIED` still, from the untouched store
  snapshot) — direct proof against a live-source fallback.

`engine/tests/test_agent_revisions_cli.py`:

- `list` on an empty store / unknown agent does not crash; filters by
  recorded `source_agent_id`; additionally surfaces a revision whose
  *current live* content matches even when its recorded `source_agent_id`
  names a different agent (content-addressed dedup, §1.2); a malformed
  sibling revision (unparseable `manifest.json`) is counted and skipped,
  never prevents listing its healthy siblings; an incomplete revision is
  rendered as `INCOMPLETE`; `--json` output round-trips.
- `show` on an unknown revision reports a typed error, not a crash; a
  healthy revision reports `verified: True`; a tampered stored file
  reports `verified: False` (exit 1), still without crashing.
- `restore` writes to the documented default target when `--to` is
  omitted; refuses a non-empty target without `--force` and writes
  nothing; `--force` allows matching-file overwrite while retaining
  unrelated target files; an incomplete revision's restore
  prints an explicit `WARNING`, never a bare success line; a tampered
  canonical snapshot fails restoration *before* any file is written to the
  target (the target ends up empty/absent, not partially populated); a
  hand-corrupted manifest path escape (`../../escaped.py`) is refused with
  nothing written outside the target; an unknown revision id reports a
  typed error.

`engine/tests/test_agent_revisions.py` (additional Phase 6 coverage found
by re-checking §12's checklist against actual test coverage, not merely
assumed covered): a broken/dangling internal symlink is reported
`REASON_NOT_A_FILE` (skipped on this Windows sandbox without
symlink privilege, exactly like the other real-symlink tests); an
unreadable file (monkeypatched `Path.read_bytes` failure, since Windows
permission semantics can't reliably construct this without admin rights)
is reported `REASON_UNREADABLE`, not silently dropped; a `--force` restore
into a target directory that already contains a symlink/junction at a path
the manifest also wants to write is refused rather than writing through it
to whatever the pre-existing link points at (distinct from every other
restore-security test here, which attacks via a corrupted *manifest*
rather than a pre-existing *destination* entry).

`engine/tests/test_agent_revision_lifecycle.py`: one full
evaluate → edit-live-source → inspect-history → restore → verify-restored
round trip, plus running `bytefray agents validate` against the restored
copy to prove existing agent tooling operates on it without a second,
revision-aware execution path (§7's compositional restore design).

Full headless `python -m pytest` (`engine/tests` + `client/tests`), both
`mypy` invocations, and Ruff scoped to every file this feature touches all
pass — met for Phases 2 through 6 as delivered. See the v0.8 audit final
report for exact pass/skip counts and the independent adversarial review
disposition.
