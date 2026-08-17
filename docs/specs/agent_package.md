# agent_package

**Modules (shipped in v1.2; qualification-hardened in v1.3):**
`engine/src/battle_engine/agent_package.py` (new,
self-contained domain module: package model, deterministic archive
writer/reader, integrity verification, safe extraction, export/import
orchestration); `engine/src/battle_engine/agent_package_cli.py` (new, thin
argparse wrapper, mirrors `agent_revisions_cli.py`); a small, additive,
non-breaking public export added to `engine/src/battle_engine/agents.py`
(`agent_spec_from_dir`, an existing-behavior alias of the private
`_spec_from_dir`) and to `engine/src/battle_engine/agent_revisions.py`
(factoring the manifest-dict shape `_write_snapshot` already builds into a
reusable, public `revision_manifest_payload()`, used identically by both
call sites so they cannot drift out of sync). In the original v1.2 change,
`command.py` also gained three dispatch entries (`export`, `import`,
`package`); v1.3 qualification subsequently hardens the existing domain,
CLI, Designer, documentation, tests, and Windows packaging surfaces.

**Purpose:** let a Bytefray user export an agent from one installation into
a single portable, inspectable file; transfer it by any ordinary means;
inspect it without executing any of its code; and import it into another
installation without losing the provenance/compatibility facts Bytefray
already knows about that agent — extending the guarantees the agent
revision store (`docs/specs/agent_revision.md`) already established
locally, across a machine boundary, rather than inventing a parallel
provenance system.

Status: design spec, written before implementation, per `CONTRIBUTING.md`'s
spec → issue → prompt → PR flow, produced during the v1.2 reconnaissance
pass described in `docs/ROADMAP.md`'s "After v1.0" section and
`docs/FUTURE_PLANS.md`'s "Agent packaging / sharing" (status: Candidate,
promoted to this Milestone). Baseline recorded for this pass:
branch `main`, HEAD `2c0071c` (post-`v1.1.0` `main` -- the tagged
`v1.1.0` release commit itself is `b50a499`, two commits back), working
tree clean, `python -m pytest -q` / `mypy engine/src/battle_engine` /
`mypy client/src/battle_client` / `ruff check .` all pass with zero
findings before any code in this spec is written.

## 0. Why this reuses the revision store instead of inventing a new one

Bytefray already has exactly the primitive a portable package needs to be
built on: `agent_revisions.py`'s content-addressed revision store. Its
existing guarantees, established and adversarially tested in v0.8
(`docs/specs/agent_revision.md`), map directly onto this feature's
requirements:

| This feature needs | Already provided by |
|---|---|
| A path-independent, platform-independent content identity for "this exact source" | `agent_revision_fingerprint`/`agent_revision_id` — proven relocation/rename-independent by `test_agent_revisions.py` |
| A deterministic, versioned hash covering every included file plus an honest account of anything that couldn't be captured | `walk_agent_files`/`_hash_walk_result`, `AgentFileWalkResult.complete`/`.omitted` |
| A provably-frozen snapshot, not a second, possibly-different read | `walk_agent_files` is called exactly once and reused for both identity and storage (§2.1/§4.2 of `agent_revision.md`) |
| Safe, contained extraction of trusted, content-addressed bytes to a caller-chosen directory, refusing a non-empty target without an explicit override, verifying integrity before writing anything | `restore_revision` |
| Fail-closed verification of a stored snapshot against its own claimed identity, including detecting a manifest hand-edited to under-report its own file list | `verify_revision`/`_verify_snapshot_dir` |

Building the package format as **a transport wrapper around one archived
revision**, rather than a second, parallel packaging-specific content
model, means the hardest, most adversarially-reviewed part of this feature
(content addressing, omission honesty, fail-closed verification, safe
restore) is not reimplemented — it is the exact, already-shipped,
already-tested v0.8 code, unmodified. This is the single governing design
decision behind everything below; §1–§12 work out its consequences.

## 1. What exactly is exported (§4 of the parent task)

**Decision: option C, made unambiguous by construction, not by convention.**
`bytefray agents export <agent-id>` always packages **one already-identified
agent revision** — never "whatever is currently in `agents/<id>/`" as an
implicit, unaddressed blob. Two ways to select which revision:

- **Default (no `--revision`):** export freezes the agent's *current*
  on-disk source into a revision first, exactly the way
  `EvaluationService`'s freeze step already does (`agent_revision.md` §4.2):
  call `walk_agent_files(agent_spec.dir)` **once**, derive the revision
  identity/manifest from that single walk, and best-effort persist it to
  the local `agent_revisions/` store via the existing
  `archive_agent_revision_from_walk`. The package is then built from that
  same in-memory walk result — never a second read of the live directory.
  This closes the exact race the parent task's §4 worries about ("a package
  described as revision X must actually contain revision X"): there is no
  window in which the packaged bytes and the declared identity could
  reflect two different reads, by the same single-read argument
  `agent_revision.md` §4.2 already establishes for evaluation freezing.
- **`--revision <revision-id>` (explicit):** export an already-archived
  historical revision from the local store instead of current live source.
  Requires the revision to already exist in this installation's
  `agent_revisions/` store and to `verify_revision` (fail closed on a
  corrupted/tampered local snapshot — refuse to export it). The packaged
  bytes come from the store's own `files/` directory, which is immutable
  and content-addressed by construction, so there is no live-directory race
  to worry about on this path either.

Either way, **the package's declared `agent_revision_id` and its actual
payload bytes are the same read, always** — there is no code path that
builds a package's metadata from one source and its payload from another.

`agent_dir` for both paths still comes from `resolve_agent(data_root,
agent_id)` (the ordinary discovery entry point) — export does not bypass
discovery or accept an arbitrary filesystem path. `resolve_agent` itself
raises a bare `SystemExit` for an unknown/invalid agent id — an existing,
established convention in this codebase's CLI-adjacent code (`cli.py`),
not something this feature changes — but that is not an acceptable
failure mode from a presentation-neutral domain function per `AGENTS.md`.
`export_agent` catches exactly that one `SystemExit` around exactly that
one call and re-raises it as `PackageInvalidError`, so every caller of
this module (CLI, tests, a future Designer integration) has one uniform,
typed-exception contract to handle, without touching `resolve_agent`
itself (out of this feature's module list, §Modules above).

## 2. Supported agent kinds (§18/§19 of the parent task)

Investigated directly against `agents.py`'s `_spec_from_dir` and
`starters.py`: an `AgentSpec.kind` is exactly one of `"python"`, `"blob"`,
or `"builtin"`, and `"builtin"` is a **real, currently-shipping** case, not
a hypothetical — the four native VM starter agents (`runner`, `writer`,
`seeker`, `spiral`) discover as `kind="builtin"` with **no `agent.py`, no
`model.blob` — only `agent.yaml`**. Their behavior is not implemented by
anything in their own directory: `cli.py`'s `_resolve_agent` resolves a
`builtin`-kind discovered agent purely by **matching its catalog directory
name against the hardcoded `SUPPORTED` built-in-program list** and calling
`build_agent(agent_name, ...)`, which constructs VM bytecode compiled
directly into `battle_engine` itself. Packaging one of these agents'
directories would produce a package containing only a `display`/
`description` manifest with **no portable payload whatsoever** — on the
receiving installation it would only ever work again by directory-name
coincidence with that installation's own compiled-in `SUPPORTED` list, not
because the package carried anything reproducible. That is not packaging;
it would be a package that silently lies about being self-describing.

**Decision:**

- `kind="python"` — **supported.** Self-contained: `agent.yaml` +
  `agent.py` (+ any local helper modules/data files the revision walk
  captures).
- `kind="blob"` — **supported.** Self-contained: `agent.yaml` +
  `model.blob`.
- `kind="builtin"` — **rejected at export time**, with a typed
  `PackageUnsupportedKindError` (`package_unsupported_kind`) explaining
  exactly the reason above: a manifest-only starter's implementation is
  supplied by the Bytefray installation itself, not present in the agent's
  own directory, and therefore has nothing meaningful to package. This is
  a deliberate, documented v1.2 boundary, not an oversight — see §19's
  framing in the parent task. A user who wants to "export" a VM starter's
  *behavior* has nothing to export; what they may legitimately want is a
  **blob** capturing one, which is out of scope for this milestone (no
  existing tool compiles a VM starter to `model.blob`) and is recorded in
  §20 (deferred work) rather than silently worked around here.

Import applies the identical kind check against the package's declared
`kind` (a package cannot claim `kind="builtin"` and be imported — this is
enforced on both ends, not just at export, so a hand-crafted or
third-party-authored package cannot smuggle one in either).

## 3. Package format

**Extension:** `.bytefray-agent`. A plain ZIP container — chosen after
checking for an existing repository convention and finding none closer
than "content-addressed directory tree" (the revision store itself, not
zipped) and "arbitrary directory" (a restore target) — ZIP is the standard
cross-platform, human-inspectable (`unzip -l`, any archive tool, or
Python's own `zipfile` module, no special tooling required), streamable
container, and every supported host platform's standard library can read
and write it without a third-party dependency (`pyproject.toml`'s core
install is PyYAML-only; ZIP support needs nothing added).

**Structure** — deliberately mirrors the revision store's own on-disk
layout, because it *is* one revision's stored shape, transported:

```text
<agent_id>-<fingerprint12>.bytefray-agent          (ZIP container)
├── package.json                                    bytefray.agent_package v1
└── revision/
    └── agent-revision_<hex64>/
        ├── manifest.json                            bytefray.agent_revision v1 (§4 of agent_revision.md)
        └── files/
            ├── agent.yaml
            ├── agent.py                              (or model.blob for kind=blob)
            └── ...                                    every other included file, original relative layout
```

`revision/agent-revision_<hex64>/manifest.json` is **byte-for-byte the
same manifest shape** `agent_revisions.py`'s `_write_snapshot` already
writes to the local store (same `schema`/`schema_version`/`files`/
`omitted`/`complete`/`fingerprint_version` fields) — built via the new
shared `revision_manifest_payload()` helper (§0), not a hand-duplicated
copy. This is what lets import treat the extracted `revision/` directory
as a throwaway, single-entry **revision store root** and call the
existing, unmodified `verify_revision`/`restore_revision` against it
directly (§7) — the package format is not a new thing `agent_package.py`
must learn to verify; it is the existing revision-store shape, wrapped.

**`package.json`** (new, `bytefray.agent_package` schema, this feature's
one genuinely new piece of wire shape):

```json
{
  "schema": "bytefray.agent_package",
  "schema_version": 1,
  "exported_at": "2026-08-14T18:00:00.000000Z",
  "bytefray_version": "1.2.0",
  "agent_id": "hunter",
  "display_name": "Hunter",
  "kind": "python",
  "agent_version": "1.0",
  "entry_point": "agent.py:create_agent",
  "agent_api_version": 1,
  "agent_revision_id": "agent-revision_8e1a...",
  "revision_complete": true,
  "revision_omitted_count": 0,
  "file_count": 2
}
```

Field provenance, since the parent task (§7) explicitly asks that
compatibility metadata not be claimed without a factual basis:

- `agent_id` — the discovered id on a live export, or the caller's explicit
  export label on the `--revision` path. A revision is deliberately
  path/name-independent and its `source_agent_id` is only a breadcrumb, so
  this field is a transport/default-destination label, not part of revision
  identity and not something the payload can authoritatively reconstruct.
  Import may replace it explicitly with `--as` (§8).
- `display_name`/`agent_version`/`entry_point`/`kind` — read directly from
  the `AgentSpec` already produced on the live path, or reconstructed by
  parsing the archived payload's own `agent.yaml` via
  `agent_spec_from_dir()` on the `--revision` path. Since v1.3,
  inspection/import perform that same safe manifest parse and reject a
  disagreeing outer declaration — **factual**, not inferred. The display
  cross-check applies when `agent.yaml` explicitly declares `display` or
  `name`; an undeclared display remains a transport label. That exception
  preserves legitimate v1.2 historical exports, whose old snapshot-directory
  fallback was the literal `files`, while the v1.3 writer now uses the caller's
  export agent id for that fallback.
- `agent_api_version` — the Python agent's own declared API version
  (`null`/absent for `kind="blob"`, which has no Agent API surface at all
  — modeled the same "not applicable, not merely unknown" way
  `COMPATIBILITY.md` already models a `redcode94` result's
  `ruleset_id: null`, §5 below). **Factual**, read from the manifest, not
  guessed.
- `agent_revision_id`/`revision_complete`/`revision_omitted_count`/
  `file_count` — mirror `revision/.../manifest.json`'s own fields. On read,
  the revision id is recomputed by `verify_revision` and the counts are
  independently checked against the verified manifest; they are not trusted
  merely because both JSON documents contain the same-looking value (§10).
- `exported_at`/`bytefray_version` — **informational timestamp/breadcrumb
  only**, exactly like the revision manifest's own `archived_at`/
  `source_agent_id` (`agent_revision.md` §3) — never treated as an
  identity or compatibility input by any check in this spec.
- **No `ruleset_id`, no "required Ruleset" field of any kind.** The parent
  task's §7 explicitly warns against claiming compatibility metadata
  Bytefray cannot prove: an Agent API v1 Python agent is not bound to one
  Ruleset the way a match/evaluation artifact is (Ruleset identity is a
  property of *a match*, not of *an agent* — `COMPATIBILITY.md`'s own axis
  table). Bytefray has exactly one Ruleset today
  (`bytefray-rules-1`), so this is presently moot in practice, but the
  package schema deliberately does not manufacture a claim the data does
  not support, so it never has to be walked back later. If a future
  Ruleset requires agent-level gameplay assumptions this format cannot yet
  express, that is new information for a future schema version to add
  honestly (§9), not something to guess at now.

## 4. Package/revision identity — one axis, not two

`package.json`'s `agent_revision_id` **is** the package's logical content
identity — not a new, separate "package identity" computed independently.
This directly answers the parent task's §8 questions:

- **Two exports of the exact same revision produce the same logical
  identity?** Yes, always — `agent_revision_id` is the same
  content-addressed value `agent_revisions.py` already guarantees is
  path/rename/host-independent.
- **Should the outer package have a separate digest?** Only as a
  **non-identity-bearing, informational** value: export prints the
  written `.bytefray-agent` file's own SHA-256 to the console (matching
  the parent task's §13 example output), the same way `agents revisions
  show` surfaces informational-only breadcrumbs — but this value is never
  written *inside* `package.json` (a file cannot durably contain its own
  hash without a fixed-point exclusion trick that buys nothing here) and
  is never compared against anything by `import`/`package show`. Only
  `agent_revision_id` is checked for compatibility/collision/integrity
  purposes anywhere in this feature.
- **Can two exports of the same revision be archive-byte-identical too?**
  **Partially, deliberately not fully — and the exact boundary matters.**
  Every `ZipInfo` gets a fixed `date_time` (`(1980, 1, 1, 0, 0, 0)`, the
  DOS-time floor ZIP itself supports) and fixed Unix permission bits in
  `external_attr` (`0o644` for every entry — nothing executable, nothing
  symlink-mode-tagged, §6), entries are written in one fixed order
  (`package.json`, then `revision/<id>/manifest.json`, then
  `revision/<id>/files/<relative_path>` for each path in the manifest's
  own already-sorted `files` list), and compression is fixed
  (`ZIP_DEFLATED`, default level). `export_agent`'s live-source path also
  reads back the revision's *durably persisted* store manifest
  (`agent_revisions/<id>/manifest.json`) rather than rebuilding one from
  the current walk, whenever the local store write succeeded — since
  `_write_snapshot` only ever writes `archived_at`/`source_agent_id` once
  per distinct content (content-addressed dedup short-circuits every
  later write of identical bytes, `agent_revision.md` §3), this means the
  packaged `revision/<id>/manifest.json` is **byte-identical** across
  repeated exports of unchanged content, carrying the true "first seen"
  timestamp rather than a fresh one stamped on every export call. The one
  field that legitimately, deliberately still varies between two
  independent export invocations of the same content is `package.json`'s
  own top-level `exported_at` — it records *when this export happened*,
  which is honestly a different fact each time, not an identity input.
  **Consequence:** the overall archive-file SHA-256 is *not* identical
  across two independent export calls, even for byte-for-byte unchanged
  source, because `package.json` itself legitimately differs. Only
  `agent_revision_id` — and, as a corollary, the packaged
  `revision/<id>/manifest.json` and every payload file — are the stable,
  cross-export-call identity; the outer archive-file SHA-256 is
  informational per-export metadata, never treated as a content identity
  by any check in this feature. Documentation and tests keep these facts
  (logical content identity vs. archive-file SHA-256 vs. one legitimately
  time-varying field) explicitly distinct everywhere, per the parent
  task's §22.

## 5. Compatibility model — factual, declared, and enforced are different things

Three distinct categories, named explicitly so `package.json`'s fields are
never read as stronger claims than they are:

1. **Factual identity/metadata** — `agent_revision_id`, `kind`, `entry_point`,
   `agent_api_version`, `agent_version`, and any explicitly declared display.
   The revision id is recomputed from packaged bytes;
   the other values are declared in `package.json` and, since v1.3
   qualification, cross-checked against the safely parsed packaged
   `agent.yaml`. A declaration that disagrees with its payload is invalid,
   not a compatibility loophole.
2. **Enforced compatibility** — checked by `import`/`package show`, and
   the *only* things that can fail an import on compatibility grounds:
   - `package.json`'s own `schema`/`schema_version` — unsupported version
     is a hard, honest `PackageSchemaUnsupportedError`
     (`package_schema_unsupported`), never a best-effort parse attempt.
   - `kind` — must be `python` or `blob` (§2); anything else, including an
     unrecognized future value, is rejected.
   - `agent_api_version` (when not `null`) — must equal the importing
     installation's own `battle_engine.agent_api.AGENT_API_VERSION`
     (currently `1`). A **higher** value than the local installation
     understands is rejected with a clear "this package requires a newer
     Bytefray" `PackageCompatibilityError`
     (`package_compatibility_failed`) — this is the concrete mechanism
     behind the parent task's §21 "future Agent API v2 package imported
     into v1.2 must be rejected honestly": v1.2 does not implement Agent
     API v2, but its `package.json`/`bytefray.agent_package` schema has
     no reason to change to reject one, since the version check is
     already a plain integer comparison against whatever
     `AGENT_API_VERSION` the *importing* build defines.
3. **Declared, not enforced** — `bytefray_version` (the *exporting*
   installation's own version string). Bytefray has no cross-version
   semver compatibility promise/policy to check this against (there is no
   "Bytefray N only reads packages from Bytefray ≤ N" rule anywhere in
   this codebase to enforce), so this field is surfaced by `package show`
   purely as a breadcrumb — explicitly labeled as such in both CLI output
   and this document, never used as an import gate. This is the same
   "informational, not authoritative" precedent `source_agent_id` already
   sets in the revision manifest (`agent_revision.md` §3).

No **inferred** compatibility category is needed for v1.2 — everything
checked is either directly factual or an exact, non-fuzzy version-integer
comparison. If a future format extension needs a genuinely inferred/
confidence-qualified compatibility fact (the parent task's §7 flags this as
a category to keep distinct), it should follow `battle_engine.rules`'
`RulesetProvenance`/`RulesetConfidence` precedent rather than
`evaluation_history`'s richer `FieldConfidence` vocabulary, for the same
dependency-direction reason `COMPATIBILITY.md` already documents (`rules`
sits far below `evaluation_history` in the dependency graph, and
`agent_package.py` — like `agent_revisions.py` — has no reason to depend
on it).

## 6. Security boundary — package validity ≠ agent trust ≠ runtime validation

Stated plainly, and enforced structurally, not just by convention:

- **Reading `package.json`, listing the archive's members, or verifying
  integrity never imports, executes, or even syntax-checks a single byte
  of agent Python source.** `package show`/`agents package show` opens the
  ZIP, reads JSON metadata and the packaged `agent.yaml` as data, and
  computes SHA-256 digests over raw bytes. Nothing under
  `revision/.../files/` is passed to `compile()`, `exec()`, `importlib`, or
  any subprocess. Parsing the manifest is necessary to verify that the
  outer package did not lie about kind/API/entry-point/version/display; it
  does not load the declared entry point.
- **A structurally valid, fully-verified package is not a trust
  statement about the code it contains.** A Bytefray package proves
  package structure/self-consistency and (via `agent_revision_id`) content
  identity. It does not authenticate who created or distributed it, and it
  does not, and cannot, prove the contained Python agent is
  safe or non-malicious — it is executable code, and Bytefray's existing
  Agent Lab worker-subprocess timeout (`docs/AGENT_LAB.md`) is
  development-time **hang containment**, not a security sandbox
  (`COMPATIBILITY.md`'s own "Experimental/unsupported boundaries" already
  states this about ordinary, non-packaged agents; packaging changes
  nothing about it). `import`'s CLI output and this document both use
  exactly this language — never "secure package," "trusted agent," or
  "sandboxed agent."
- **Import extracts files; it never runs anything.** `bytefray agents
  import` places the agent's files under `agents/<id>/` and returns.
  Running it is a subsequent, ordinary, already-existing, already-informed
  user action (`agents validate`/`agents test`/`agents evaluate`/`bytefray
  run`), governed by exactly the same trust decision a user already makes
  for any agent they did not write themselves — packaging does not lower
  that bar, and does not raise it either.

## 7. Archive extraction safety

Two independent layers, not one:

**Layer 1 — untrusted ZIP → trusted temporary revision-store root.** This
uses `_validate_member_metadata` followed by `_extract_validated_members`
(`agent_package.py`), because a ZIP
member's filename is attacker-controlled text with no existing containment
guarantee. Reuses `battle_engine.paths.contained_path` — already proven
(directly, via a REPL check performed during this spec's own reconnaissance
pass on this Windows development host, not merely assumed) to reject every
adversarial shape the parent task's §26 lists by construction, because it
resolves the *native* `Path` and checks full post-resolution containment
rather than pattern-matching strings: `../evil.py`, `../../outside`,
`C:\evil.py`, `C:/evil.py`, `\\server\share\evil.py`, `/absolute/path`,
`foo/../../evil`, and Windows-backslash-style traversal (`foo\..\..\evil`)
all resolve to `None` (rejected) when checked against a Windows host in
this same repository. Additional checks `contained_path` alone does not
cover, added explicitly in that metadata-first validation pass:

- **Any member name containing a literal backslash, NUL byte, or other
  control character is rejected outright**, before `contained_path` is
  even called — not because `contained_path` mishandles it (a backslash is
  simply an ordinary character on a POSIX host, so a member using one
  never actually escapes containment there), but because this exporter
  never produces one (every internal path is POSIX-relative,
  `Path.as_posix()`, exactly like the revision store itself), so any
  package containing one is either non-Bytefray-authored or adversarial,
  and accepting it would create host-OS-dependent behavior — a package
  that extracts one way on Linux and a different (if still safely
  contained) way on Windows — which this feature refuses to allow rather
  than merely tolerate. This is the concrete mechanism satisfying the
  parent task's explicit requirement to test "Windows-style paths even
  when running on Linux and vice versa."
- **Windows-ambiguous path components are rejected on every host**, not
  only when import happens to run on Windows: a literal colon (including an
  NTFS alternate-data-stream spelling such as `agent.py:payload`), a
  component ending in a dot or space, or a case-insensitive reserved device
  stem (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, including
  a suffix such as `NUL.txt`) is invalid. These spellings are ordinary
  filenames on some POSIX filesystems but alias, disappear, or address a
  different stream/device on Windows. Applying one portable policy at
  inspect/import time prevents the same archive from materializing
  differently by host; export applies the identical check and never emits
  such a member.
- **Duplicate/case-colliding normalized destination paths are rejected.**
  Every planned destination is casefolded and checked against every other
  planned destination in the same archive *before any file is written* —
  independent of the *host's* filesystem case sensitivity, since a package
  built on Linux (case-sensitive) might later be imported on Windows
  (case-insensitive by default), and a pair of entries safe to write on
  the machine that built the archive must not silently collide/overwrite
  on the machine that reads it.
- **A ZIP entry whose external attributes encode any special Unix type
  (symlink, FIFO, socket, character device, or block device) is rejected
  outright**, never extracted. Python's
  `zipfile` does not itself materialize a real OS symlink from such an
  entry (it writes the link-target *text* as ordinary file content), so
  this is not exploitable via this code path today — but relying on that
  implementation detail rather than checking explicitly would be exactly
  the kind of "safety by accident, not by contract" the parent task's §10
  warns against ("do not rely solely on `zipfile.extractall()` safety
  assumptions"). Checked and rejected before extraction, not merely
  tolerated because it happens to be inert.
- **Resource limits begin before `ZipFile` construction.** Python's ZIP
  reader eagerly allocates one `ZipInfo` object per central-directory
  record, so validating only the resulting table would still let a huge
  central directory stall or exhaust a synchronous inspector first. A raw,
  bounded scan of the same open file handle therefore checks the real EOCD
  and every fixed central record before handing it to `ZipFile`: at most
  585 MiB for the outer archive, 32 MiB for central-directory metadata,
  5,000 actual records, and 4,096 UTF-8 bytes per member name. The scan
  counts records rather than trusting forgeable EOCD count fields. Multi-disk
  and ZIP64 containers are rejected; neither is needed within the much
  smaller v1 count/size envelope emitted by Bytefray.
- **Member limits** are then checked over the complete `ZipInfo` table,
  including `package.json`, *before any member is read or decompressed*: at
  most 5,000 members, 256 MiB for any one uncompressed member, 512 MiB total
  uncompressed content, 260 MiB for one compressed member, and 520 MiB total
  compressed content. `package.json` has narrower 1 MiB uncompressed and
  1 MiB + 64 KiB compressed caps. The payload-root `agent.yaml`, which is
  safely parsed as YAML data during factual-metadata cross-checking, has the
  same 1 MiB / 1 MiB + 64 KiB bounds so an otherwise-allowed 256 MiB source
  file cannot turn that synchronous parse into a GUI stall. These are
  conservative, generous constants — an agent's own directory is source
  code plus at most one `model.blob`, not a dataset. Duplicate `package.json` entries,
  unsupported compression, malformed reads, or an archive whose declared
  sizes exceed a limit are rejected as typed package-invalid failures
  before payload decompression begins. `ZipFile.testzip()` is deliberately
  not the validation mechanism because it would decompress every member
  before those metadata limits could protect the caller.
- **File/directory ancestor collisions are rejected** alongside exact and
  case-folded duplicates: an archive cannot contain a regular file at
  `revision/x` and another member below `revision/x/...`, which would fail
  only after reads/writes began on some filesystems.
- **Validate-then-write, never interleaved**: every member is resolved,
  classified, and checked (containment, duplicates, size) in one pass
  first; only if every member in the archive passes does a second pass
  write any bytes — the same "resolve every pair before writing any of
  them" discipline `restore_revision` already established (§7.3 of
  `agent_revision.md`) for exactly the same reason (a failure discovered
  on file five must not leave files one through four already written).

**Export applies the same envelope.** Before it creates or replaces an
output archive, export accounts for `package.json`, the revision manifest,
and every payload member against the same archive/name/count/single/total
limits. The live-source preflight applies the `agent.yaml` cap before
discovery parses that manifest. An agent too large for this implementation to inspect/import is therefore
rejected with a typed error and no partial package, rather than producing an
archive Bytefray itself refuses to consume. This v1.3 qualification fix is
validation behavior only; it does not alter the schema-v1 member layout.

**Layer 2 — trusted temporary revision-store root → final agent
placement.** Once Layer 1 has safely materialized
`<tmp>/revision/agent-revision_<hex>/{manifest.json,files/}` on disk, that
directory *is* a one-entry revision store, and import treats it as one:
`verify_revision(<tmp>/revision, revision_id)` (existing, unmodified,
fail-closed) confirms the extracted bytes actually reconstruct the
declared identity. The package layer then cross-checks outer metadata and
revision counts against the verified manifest/payload. Finally,
`restore_revision(<tmp>/revision, revision_id, final_target_dir)` (existing,
unmodified) performs the actual placement, inheriting its pre-write
verification/containment checks and best-effort cleanup on ordinary I/O
failure — including the
pre-existing-destination-symlink defense (`test_restore_rejects_escape_
through_preexisting_destination_link`) that a Layer-1-only design would
have to reinvent. Final placement remains reuse of the revision service;
the v1.3 package-layer cross-check is a narrow validation bridge, not a
second restore implementation.

## 8. Import collision policy

Investigated against existing precedent before deciding: `agent_scaffold.
create_agent` (the only other "write a new `agents/<id>/` directory"
entry point in the codebase) refuses outright when the destination already
exists — no `--force`, no auto-rename. Import follows the identical,
already-established precedent:

- **Default: fail without mutation** if `agents/<agent-id>/` already
  exists, where `<agent-id>` is the package's own declared `agent_id`
  field and has different content. Nothing is written or overwritten. The
  existing directory is read only to recompute its revision fingerprint so
  the exact-revision no-op below can be distinguished from a real conflict.
- **`--as <agent-id>`**: import under an explicit, user-chosen id instead
  of the package's declared one. No auto-invented rename (e.g. no silent
  `hunter-2`) — the parent task's §11 explicitly asks not to invent this
  convention, and nothing in the existing codebase establishes one to be
  consistent with.
- **Identical-revision recognition**: if the target `agents/<agent-id>/`
  already exists **and** its current live content's own
  `agent_revision_fingerprint` equals the package's declared
  `agent_revision_id`, import reports this distinctly — "already present
  with this exact revision; nothing imported" — and exits `0`, not as an
  error. This is a true no-op (nothing to import that isn't already
  there byte-for-byte), not a collision requiring `--as`, and mirrors the
  store's own content-addressed dedup philosophy (`agent_revision.md`
  §1.2/§3) rather than treating "the same thing showed up twice" as a
  failure.
- **No overwrite flag in v1.2.** `--force`-overwriting existing,
  potentially hand-edited agent source is a materially more dangerous
  operation than anything else in this feature's core scope, has no
  existing-codebase precedent to be consistent with (not even
  `agent_scaffold`, which is a much smaller blast radius — an empty
  scaffold, not arbitrary existing user work), and is not required by any
  of the parent task's acceptance criteria (§31 asks only that existing
  agents are never *silently* overwritten — refusing overwrite entirely
  satisfies that more strongly, not less). Deferred explicitly (§20), not
  silently possible via an undocumented flag.

## 9. Historical/future compatibility

- **Older Bytefray reading a newer package**: `schema_version` gate is
  exact-equality-or-known-set, matching `evaluation_history`'s own
  `SUPPORTED_V2_VERSIONS`-style precedent (`agent_revision.md` §5.3) rather
  than `>=`/`<=` range logic — an unrecognized future `schema_version`
  fails clearly (`package_schema_unsupported`), never silently
  best-effort-parsed.
- **This (v1.2) Bytefray reading a v1 package**: the only version that
  exists at ship time; trivially supported.
- **A future Agent API v2 package**: structurally inspectable when its
  outer declaration agrees with its payload, but reported as incompatible
  against an Agent API v1 installation; import's compatibility check (§5)
  rejects it honestly rather than attempting to run it.
- **A future BFScript-generated package** (`docs/FUTURE_PLANS.md`'s DSL
  item): `package.json` is a plain, additive JSON object; a future schema
  version could add optional `compiler`/`source_language` fields the same
  way `agent_revisions.md`'s own manifest already reserves room for
  informational, non-identity-bearing metadata, without this milestone
  needing to design or implement any of it now. Not implemented, not
  stubbed out, simply not precluded.

## 10. Testing and validation criteria

- **Round trip**: export → `package show` → import (fresh, isolated data
  root) → `agents validate`/`agents test` against the imported agent →
  `agents revisions show` against the freshly-imported local revision →
  provenance matches the exporting installation's own `agent_revision_id`
  for byte-identical source.
- **Cross-machine simulation**: export under one temporary `BYTEFRAY_ROOT`,
  import under a second, disjoint temporary `BYTEFRAY_ROOT` (simulating a
  transfer without a second physical host) — `package.json` contains no
  substring matching either temporary root's own absolute path.
- **Tamper detection**: flip one byte inside `revision/.../files/agent.py`
  after export; `package show`/`import` both detect it
  (`PackageIntegrityError`, `package_integrity_failed`) via
  `verify_revision`, before any extraction to a final location.
- **Metadata/payload agreement**: alter only `package.json`'s kind, API,
  entry point, version, display, or revision counts; inspection/import must
  reject the mismatch before final placement even though the archived file
  bytes still satisfy their original revision id.
- **Metadata-first resource enforcement**: oversized/duplicate
  `package.json`, excessive member counts/sizes, and unsupported compression
  are normalized to typed invalid-package outcomes before payload
  decompression; inspection remains read-only and import leaves `agents/`
  unchanged.
- **Export envelope**: lower each resource limit under test and prove export
  refuses an over-limit source without creating a partial destination.
- **Every path from the parent task's §26 adversarial list**, built as a
  hand-crafted `.bytefray-agent` (a real ZIP with a malicious entry
  substituted in place of a legitimate payload path) — proven rejected by
  `import`, with no file written outside the intended temporary
  extraction root. The same host-independent test matrix covers ADS/colon,
  reserved-device, and trailing-dot/space components and proves export
  refuses to emit each portable-path violation.
- **Collision behavior**: import into a data root where `agents/<id>/`
  already exists — with different content (fails, untouched), with
  identical content (reports no-op, exit `0`, untouched), and with
  `--as` (succeeds under the new id, original untouched).
- **`kind="builtin"` rejection**: attempt to export one of the four native
  VM starters; assert the typed `package_unsupported_kind` failure and
  that no `.bytefray-agent` file is written.
- **`--revision` export path**: export an intentionally-stale historical
  revision (current live source has since changed) and confirm the
  packaged bytes match the *historical* revision, not current source.
- **Determinism**: two exports of the same unchanged revision, moments
  apart, produce identical `agent_revision_id` and identical packaged
  `revision/<id>/manifest.json`/payload bytes (always — §4), but
  deliberately *different* outer archive-file SHA-256, since
  `package.json`'s own `exported_at` legitimately differs per export call
  — asserted directly (two real exports, `agent_revision_id` equal,
  `package.json` differing only in `exported_at`, outer SHA-256 not
  equal) so this distinction stays proven, not just documented.
- Full existing suite (`engine/tests`, `client/tests`), both `mypy`
  invocations, and `ruff check .` all re-run clean after this feature
  lands, per `AGENTS.md`'s testing expectations — no existing test's
  behavior changes, since nothing existing is modified beyond the two
  small, additive, non-breaking exports named in the module list above.

## 11. CLI surface

Determined from existing convention (`command.py`'s `_agents()` dispatcher,
`agent_revisions_cli.py`'s `list`/`show`/`restore` sub-verb pattern) rather
than the parent task's illustrative examples verbatim:

```text
bytefray agents export <agent-id> [--output PATH] [--revision REVISION_ID] [--json]
bytefray agents package show <package-file> [--json]
bytefray agents import <package-file> [--as AGENT_ID] [--json]
```

`inspect-package` (one of the parent task's two suggested names) is
deliberately **not** used — `bytefray agents inspect <run-dir>` already
exists and means something unrelated (opening a development trace,
`agent_inspect.py`); a same-word-different-meaning command name one
dispatch level apart would be a genuine UX hazard this repository's
existing naming does not otherwise have. `package show`, grouped under a
new `package` namespace (parallel to the existing `revisions`/
`evaluations` namespaces), leaves room for a later `package validate` or
similar without a rename, and reads unambiguously next to `revisions show`.

`command.py`'s `_agents()` gains three new `argv[0]` branches
(`"export"`, `"import"`, `"package"`), each lazily importing
`agent_package_cli`, exactly matching every existing branch's lazy-import
style (kept for import-time cost and Qt-import-avoidance parity with the
rest of the dispatcher).

## 12. Non-goals (unchanged from the parent task; recorded here for the
record this document is scoped against)

No online registry, no upload, no search, no ratings/rankings, no
Elo/Glicko, no signing/PKI infrastructure, no dependency installation from
PyPI, no arbitrary Python environment capture, no container packaging, no
Ruleset v2 or Agent API v2 work, no BFScript implementation, no
distributed evaluation. This spec's `package.json` schema is deliberately
extensible enough that a future ecosystem feature could consume it without
a breaking change, but implementing any such feature is explicitly out of
this milestone.

## 13. Designer integration — shipped in v1.3.0

`docs/ROADMAP.md`'s v1.2.0 section named a GUI wrapper over the authoritative
`agent_package` functions as a later candidate; v1.3 ("Designer Workflow
Completion") is that slice. `app/views/agent_package.py` adds
`PackageDetailsDialog`, a reusable, read-only inspection dialog (identity,
integrity, compatibility, trust disclosure — the same field selection as
`bytefray agents package show`). It is used both by **Inspect Agent
Package…** and as the mandatory review step for **Import Agent Package…**.
`AgentDesigner` calls `export_agent`/`inspect_package`/`import_package`
directly: Qt does not invoke argparse and does not reimplement ZIP,
containment, compatibility, or placement logic.

**Export Agent…** and inspection run synchronously in-process. Resource
limits in §7 bound what the shared domain accepts, and mutating package
controls are guarded while the Designer's agent-executing subprocess slot is
busy (read-only inspection remains available). A
`QProcess` boundary is not needed for trust because the operations parse
metadata/read opaque bytes but never load or execute agent code. This is a
presentation wrapper over shared domain calls, not a claim that the domain
was left untouched: independent v1.3 qualification found and fixed the
metadata-first validation, payload-cross-check, and export-envelope defects
documented in §5–§7.

Import collision handling matches §8: different content fails without
mutation, and the Designer offers an explicit alternate id (the GUI
equivalent of `--as`) — never an automatic rename. The retry is iterative,
so any number of further occupied ids returns to the same prompt without
recursive stack growth; cancel remains a clean abort. An identical revision
is reported as a no-op. After success, catalog widgets store discovery ids
separately from display text, so refresh selects the exact imported id even
when a manifest's display name differs from its directory or duplicates
another display name. No restart is required.

All of these changes retain `bytefray.agent_package` schema version 1. The
additional checks reject packages that were already inconsistent with their
own verified payload; no JSON member or CLI JSON response gains a field.
