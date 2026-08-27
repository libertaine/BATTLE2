# Bytefray v3.0.0-alpha2 — Strategy Examples and Ruleset Clarity

Qualification record for the second v3.0 alpha prerelease. This alpha is
deliberately small: it productizes exactly two strategy lessons from the
closed v3 research program, and makes the Agent Designer state which
Ruleset it is actually using. `bytefray-rules-2` gameplay, Agent API v1,
and every persisted artifact schema are unchanged.

Its scope came from a read-only post-alpha1 product-content audit, which
found (a) that no bundled starter agent engaged with Ruleset v2's defining
Vulnerable Core mechanic at all, and (b) that the real Ruleset ambiguity in
the Designer was in the Python development/evaluation workflows, not in VM
presentation. The audit explicitly rejected adding a `VM / Redcode` tab;
that rejection is honored here and re-justified in §11.

---

## 1. Initial state

Verified before any modification:

| Item | Value |
|---|---|
| Branch | `v3.0-development` |
| HEAD | `43d52f264e1284e2c540790697da13371bdb02b6` — *docs: mark v3.0.0-alpha1 published* |
| Working tree | clean |
| `origin/v3.0-development` | `43d52f26…` — identical to HEAD |
| `v3.0.0-alpha1` tag target | `1c9b035fdf847198513a976b634a0d252866b93a` |
| Package version | `3.0.0a1` |
| Ruleset identities | product: `bytefray-rules-1`, `bytefray-rules-2`; non-product research identities registered for artifact reproducibility only: `bytefray-rules-2-alpha1`, `bytefray-rules-2-alpha11`, `bytefray-rules-3-alpha1` |
| Agent API | v1 |
| Stashes | 3, untouched |

No stash was created or applied at any point. The known
`.pytest-cache-v141` permission warning was observed and ignored; it is a
directory-read warning from git, not a working-tree change.

## 2. Frozen-population verification

`battle_engine/data/benchmarks/v2_baseline.json` pins nine agents by
whole-directory content-addressed revision, `source_sha256`, and
`local_python_subset_fingerprint`. Because the fingerprint covers the entire
agent directory, even a docstring or manifest edit constitutes drift.

`verify_population(load_population())`:

| Run | Members | Drift |
|---|---|---|
| **Before** any change | 9 | **0** |
| **After** all changes | 9 | **0** |

Every pinned member — `adaptive`, `claimer`, `hunter`, `strider`,
`wanderer`, `core_defender`, `core_seeker`, `core_tracker`,
`reactive_core_defender` — matched its pin in both runs. No frozen agent
directory was opened for writing at any point in this alpha.

`engine/tests/test_v3_phase0_benchmark_population.py::test_population_still_matches_the_live_tree`
passes, and a new test
(`test_vulnerable_core_starters_are_not_frozen_benchmark_members`) asserts
that the two new starters never acquire a pin, so they stay maintainable.

## 3. Raider derivation

**Source**: `battle_engine/data/reference_agents/core_tracker` (frozen,
unmodified). **Destination**:
`battle_engine/data/starter_agents/raider/`.

`core_tracker` was chosen over `core_seeker` for the reason the audit
identified: `core_seeker` carries a documented stale/echo-read defect (it
re-observes an uncleared `Observation.last_read` and so mistakes one hit
for two), which is the single most common Agent API v1 correctness mistake
and must not be taught as a product example. `core_tracker` fixes that
structurally with a `_pending_read_addr` marker consumed exactly once, and
Raider's docstring now teaches that pattern explicitly.

Behavior is preserved deliberately — scan → coarse-to-fine probe → assault
burst, with the same `SCAN_EVERY`, `PROBE_OFFSETS`, `CONFIRM_MIN_HITS`, and
`ASSAULT_*` values — so what ships is the researched behavior, not a
re-tuned guess.

Independent product identity:

| Field | Value |
|---|---|
| Manifest `name` | `raider` |
| `display` | `Raider (Starter)` |
| Class | `RaiderAgent` (not `CoreTrackerAgent`) |
| Signature byte | `0x7A` (fresh; no collision) |
| Docstring | Rewritten for a product audience in the existing starter house style: strategy → Agent API behavior demonstrated → state tracked → what to change. ~250 lines of research provenance prose replaced. |

The file carries a brief provenance note stating it is independently
maintained and is *not* the benchmark artifact, and imports nothing from
the reference directory at runtime.

## 4. Sentinel derivation

**Source**: `battle_engine/data/reference_agents/core_defender` (frozen,
unmodified). **Destination**:
`battle_engine/data/starter_agents/sentinel/`.

`core_defender` was chosen over `reactive_core_defender` per the audit:
it is shorter (~90 lines vs ~200), easier to understand, measured better in
the audit's own diagnostic matrix, and does not teach a strategy the
project's own research failed to validate — the v3 closeout established
that the reactive defender does not reliably outperform this simpler blind
timer. Sentinel's docstring says so directly and invites the reader to
measure a reactive variant themselves rather than assume it is better.

| Field | Value |
|---|---|
| Manifest `name` | `sentinel` |
| `display` | `Sentinel (Starter)` |
| Class | `SentinelAgent` (not `CoreDefenderAgent`) |
| Signature byte | `0x5D` (fresh; no collision) |
| `expand_stride` | `139` (distinct from `core_defender`'s `131`) |

Same provenance note as Raider.

### Frozen Claimer documentation, repaired without editing Claimer

The frozen `claimer/agent.py:13` docstring has always instructed the reader
to run:

```
bytefray agents evaluate strider --baseline claimer --opponents hunter,sentinel --seeds 1,2,3,4,5
```

Before this alpha that command failed — `ERROR: Unknown agent 'sentinel'`.
Claimer is a pinned benchmark member and cannot be edited, so adding the
agent was the only available repair. Re-run verbatim after this change, the
command completes and writes a normal evaluation artifact. This is retained
as a regression check.

## 5. Starter registration

`battle_engine/starters.py`'s `STARTER_AGENT_NAMES` gained `raider` and
`sentinel` (now eleven entries: four VM, seven Python). Its comment block
was updated to record which Python starters are benchmark-pinned and which
two deliberately are not, and why.

`ensure_starter_agents()` is unchanged: non-destructive copy-if-missing into
the writable `agents/` catalog. Verified behavior:

- a fresh data root receives all eleven;
- an existing catalog keeps its current files and gains only the two
  missing directories;
- user-modified agents are never overwritten;
- repeated initialization is idempotent.

These properties are covered by the existing generic
`engine/tests/test_starter_agents.py` suite, which is driven by
`STARTER_AGENT_NAMES` rather than a hardcoded list and therefore extended to
the new agents automatically.

## 6. Ruleset-clarity changes

`app/services/ruleset_options.py`:

- The Ruleset v1 option label changed from `Ruleset v1 — Legacy / VM
  compatibility` to `Ruleset v1 — Compatibility (Python and VM/blob)`. The
  previous wording understated the truth in one direction: a Python agent
  runs unmodified under either identity. What is genuinely exclusive is the
  other direction — only v1 executes VM/blob entrants.
- `RULESET_DESCRIPTION` (combo tooltip / accessible description) now states
  the rule in both directions.
- A new shared `VM_RULESET_EXPLANATION` constant replaces the literal
  `"Ruleset v1 is required for VM/blob matches."`, adding the converse.

Neither string mentions Redcode — see §11.

## 7. Agent Development behavior

**Audited before changing.** `AgentDesigner._on_test_agent` built
`agents test <id> --opponent … --seed … --ticks … --timeout …` and passed
no `--ruleset` at all. `bytefray agents test`'s own default is `None`,
which resolves to the backward-compatible `bytefray-rules-1`. So every
Designer development test silently ran under Ruleset v1 while the
Simple/Advanced match tabs beside it defaulted to v2.

Implemented:

- A Ruleset combo in the Development Test group, built from the same
  `populate_ruleset_combo` infrastructure Simple/Advanced use, so the
  vocabulary matches.
- **Defaults to `bytefray-rules-2`.** This is an intentional GUI-default
  behavior change, documented in `CHANGELOG.md`.
- Ruleset v1 remains selectable for Python compatibility testing. No
  entrant-kind gating is applied to this selector because the tab already
  filters to `kind == "python"` agents, which are valid under both
  identities.
- The selection is passed explicitly to the backend on every run — never
  inherited.
- The in-flight status names the Ruleset (`Testing <agent> vs <opponent>
  under bytefray-rules-2…`), and the completed result reports
  `Ruleset: <id>` taken from the tool's own `ruleset:` output line, not
  echoed from the GUI request. `DevelopmentTestPresentation` gained an
  optional `ruleset_id` field for this; it is deliberately not a required
  field, so absent output renders "not reported" rather than downgrading a
  real completed match to a tool failure.

**The CLI's own default is unchanged**, as scoped.

## 8. Pairwise-evaluation behavior

**Audited before changing.** `build_designer_evaluation_plan` set
`ruleset_id = BYTEFRAY_RULESET_V2_ID if mode == GROUP else None`, and the
pairwise launch path (`build_designer_evaluate_command`) passed no
`--ruleset`. Group mode announced v2; pairwise silently inherited v1.

The identity/resume question was checked directly rather than assumed.
`resolve_evaluation_ruleset_id` maps both `None` and the explicit v1
identity to the same `rules_compatibility_id`, "byte-identical in every
downstream hash payload". Therefore:

- selecting **v1** produces exactly today's `evaluation_id` — no existing
  evaluation's identity or resume behavior moves;
- selecting **v2** produces a genuinely different evaluation, which is
  correct and is what group mode already does.

This is a real methodology choice, not a destabilization, so the selector
was safe to add. Implemented:

- A pairwise Ruleset combo in `EvaluationDialog`, **defaulting to
  `bytefray-rules-2`**. Group mode continues to show its fixed
  "required for group evaluation" statement and remains v2-only.
- `--ruleset` is now always sent explicitly for pairwise, using
  `request.resolved_rules_compatibility_id` — the same value the plan was
  validated and identity-hashed with. This matters because the Designer
  names each run's output directory after `evaluation_id`; a command that
  resolved a different Ruleset than the plan would write into a directory
  named for an evaluation it was not running.
- **Preset interaction, handled deliberately.** An explicit CLI
  `--ruleset` outranks a preset's own `ruleset` field
  (`agent_evaluation.py`: `if ruleset_id is None and preset is not None`).
  Now that the Designer always sends one, a preset's Ruleset would have
  been silently overridden. `_on_preset_selected` therefore adopts a
  preset's Ruleset into the selector, exactly as it already adopts the
  preset's seeds/ticks/orientation "for display — never binding, always
  overridable". A preset that names no Ruleset leaves the user's selection
  alone, since there is no preset intention to preserve.

`build_designer_evaluation_plan` and `build_designer_evaluate_command` both
take `ruleset_id` as an optional keyword defaulting to `None`, so every
existing caller — including dialog doubles in the test suite that predate
the selector — is byte-for-byte unaffected. `AgentDesigner` reads it through
a defensive `getattr`, matching the established `mode`/`workers` pattern.

## 9. CLI runtime-kind disclosure

`bytefray agents` listing now marks each entry `[Python]` or `[VM]` and
prints a two-line legend. The label comes from a new
`battle_engine.agents.agent_runtime_label(spec)`, which uses the same
two-value bracketed vocabulary the Designer's
`decorate_agent_display` already uses, so the CLI and GUI can never
describe the same agent differently. A test asserts that equivalence
directly, and another asserts the label means exactly "may execute under
Ruleset v2" per `RULESET_V2.supported_runtime_kinds`.

No persisted schema changed: the listing has no JSON form, and no artifact
records a runtime label.

**Incidental defect found and fixed during frozen-build validation.** The
listing's "no blob" placeholder was an em-dash, which the source build
renders correctly but the frozen `bytefray.exe` renders as a replacement
character in the same shell — a real, previously shipped defect visible in
the exact output this alpha set out to clarify. It is now ASCII `none`,
matching the CLI's own existing vocabulary for an absent path
(`agents test` prints `result: none` / `replay: none`). A regression test
asserts the whole listing is ASCII.

## 10. VM compatibility regression

Verified in the real Agent Designer with native Windows Qt:

- selecting `Runner (Starter) [VM]` as Agent A auto-repairs Agent B to a
  compatible VM entrant (`Seeker (Starter) [VM]`);
- the Ruleset combo switches to `Ruleset v1 — Compatibility (Python and
  VM/blob)` and disables the v2 entry;
- the contextual explanation reads "VM/blob agents run under Ruleset v1
  only. Ruleset v2 gameplay is Python-agent only."

Engine-level enforcement is unchanged and re-confirmed from the CLI:

| Request | Result |
|---|---|
| all-VM under `bytefray-rules-2` | rejected: *Ruleset 'bytefray-rules-2' currently supports Python entrants only … Use 'bytefray-rules-1' for VM entrants.* |
| mixed Python+VM | rejected: *Native matches must contain either all VM entrants or all Python entrants* |
| all-VM under `bytefray-rules-1` | runs |

Evidence: `docs/screenshots/v3-alpha2/02-simple-vm-forces-ruleset-v1.png`.

## 11. Redcode/pMARS wording

No product or UI text assigns Redcode a Bytefray Ruleset. The Ruleset
strings in §6 deliberately mention only Python and VM/blob entrants, and a
test asserts the CLI listing legend contains neither "Redcode" nor "pMARS".

`README.md`'s Redcode section gained the accurate statement that
Redcode/pMARS matches run in an external pMARS process and use no Bytefray
ruleset, producing a normalized summary rather than a native replay,
cross-referencing `docs/RULES.md`'s "Redcode/pMARS — not Ruleset v1".

**No `VM / Redcode` tab was added**, and the audit's rejection was
re-checked against current repository reality rather than taken on trust:

- `grep -rni "pmars\|redcode\|warrior" app/` still returns nothing — such a
  tab would ship with an empty half;
- Redcode is not Ruleset v1, so any label pairing them would teach the
  exact falsehood this alpha exists to prevent;
- VM agents still have no authoring workflow to move — their only Designer
  presence is selection inside the Simple/Advanced match combos, which is
  structurally shared with the Python match path;
- the measured ambiguity was in the Python workflows, and §7–§8 address it.

The Designer's top-level tabs remain exactly `Simple`, `Advanced`,
`Agent Development`, asserted during GUI validation.

## 12. Packaging

Both agents live under the existing `starter_agents/` directory, which is
already covered by every distribution channel. Verified rather than assumed:

| Channel | Result |
|---|---|
| Wheel (`data/**/*` package-data) | `battle_engine/data/starter_agents/{raider,sentinel}/{agent.py,agent.yaml}` present |
| sdist | both directories present |
| PyInstaller `tools/bytefray.spec` | real build performed; both present in `_internal/battle_engine/data/starter_agents/` |
| `tools/bytefray_cli.spec`, `tools/agent_designer.spec` | spec `datas` verified to bundle the whole `starter_agents` directory |
| Installer (`tools/installer.iss`) | recurses the PyInstaller dist trees, so it inherits the above with no change |

No new data-directory special case was introduced.

Phase 5 found a real defect of exactly this shape (source-tree presence ≠
frozen presence). The new regression test
`test_every_registered_starter_reaches_the_frozen_tree` closes it
generically for all three specs: it asserts that **every**
`STARTER_AGENT_NAMES` entry exists inside the bundled directory, so a future
starter cannot be registered without also being packaged.

The frozen `bytefray.exe` was exercised directly: `agents` listing shows
both new starters correctly labeled, `agents validate raider` and
`agents validate sentinel` both report `status: valid`, and
`agents test raider --opponent claimer --ruleset bytefray-rules-2` runs a
complete match.

## 13. Replay/integration evidence

A genuine Ruleset-v2 core capture was produced **by the frozen executable**:

```
agent: raider   opponent: claimer   ruleset: bytefray-rules-2   seed: 1
ticks: 182/400  winner: raider      termination: last_agent_standing
```

The replay's header records `ruleset_id: bytefray-rules-2` (replay schema
v3). Against that replay, the shipped v3 features compose correctly:

| Feature | Evidence |
|---|---|
| Core-capture callout | `core_captures_at_tick` returns `CoreCaptureAttribution(victim='B', killer='A')` at tick 182; `format_core_capture_callout_lines` renders `('CORE CAPTURED', 'raider eliminated claimer')` |
| Timeline marker | exactly one marker tick: `[182]` |
| Timeline seeking | `seek(182) → 182`, `seek(0) → 0`, `seek(90) → 90`, `seek(182) → 182` |
| Entrant status | B: `captured=True capture_tick=182 intact=0/8`; A: `alive=True intact=4/8` |
| Frozen headless renderer | prints `[0182] KILL victim=B killer=A` then `RESULT winner=A` |

Visually confirmed in the packaged Replay Viewer
(`docs/screenshots/v3-alpha2/05-replay-viewer-core-captured.png`): the
"CORE CAPTURED / raider eliminated claimer" box, `CAPTURED @ T182 by A |
Core 0/8` on the victim, `Tick 182/182 [PAUSED (end)]`, and
`T182 kill: B by A` on the timeline.

The screenshot also shows the strategic lesson plainly: Raider wins holding
**16.7%** of the arena against Claimer's **32.0%**, and with a *lower*
score (1202 vs 2051). Taking a core wins outright regardless of territory.
No Replay Viewer code was modified.

### Bounded behavioral validation

Small, deterministic diagnostics under default Ruleset-2 conditions
(arena 4096, 400 ticks) — product classification, not a research phase:

| Agent | vs | Reads | Writes | Own-core writes | Longest contiguous run | Result |
|---|---|---:|---:|---:|---:|---|
| raider | claimer | 625 | 831 | 0.4% | 16 | capture @ 182 |
| raider | hunter | 768 | 1560 | 0.4% | 16 | capture @ 291 |
| raider | wanderer | 88 | 176 | 0.6% | 16 | capture @ 33 |
| raider | sentinel | 1078 | 2122 | 0.1% | 16 | no capture, tick limit |
| sentinel | claimer | 0 | 3200 | **25.2%** | 2 | tick limit |
| sentinel | hunter | 0 | 3200 | **25.2%** | 2 | tick limit |
| sentinel | raider | 0 | 832 | **25.1%** | 1 | tick limit |
| sentinel | adaptive | 0 | 3200 | **25.2%** | 2 | tick limit |

Raider spends real budget searching and commits bursts of exactly
`ASSAULT_ACTIONS = 16` contiguous writes. Sentinel spends exactly the
intended ~25% of its actions on its own eight-cell core and issues zero
`READ`s, confirming it is the blind timer it documents itself to be.

Both behaviors are now asserted as tests
(`test_raider_searches_with_reads_and_commits_contiguous_bursts`,
`test_sentinel_spends_a_quarter_of_its_actions_on_its_own_core`) against the
real development trace, with a deliberately wide 15–35% band so the tests
pin the *strategy* rather than an exact tuning constant.

## 14. Tests

Added or extended:

| Area | Coverage |
|---|---|
| Starters | `DEFAULT_PYTHON_AGENT_NAMES` grew 5 → 7; the all-pairs behavioral matrix grew from 20 to 42 cells. Both new agents: discovery as `kind: python` with a v1 entrypoint, clean validation, completed match vs the reference opponent, completed matches vs every sibling. |
| New-starter specifics | not benchmark members; run under Ruleset v2 and report it; product identities (own `name`/`display`/class, provenance note present); **all seven starter signature bytes unique**; the two documented behaviors above. |
| Packaging | every registered starter reaches the frozen tree, for all three specs. |
| Agent Development | Ruleset control defaults to v2; `--ruleset` sent explicitly; effective Ruleset shown in flight and in the result; v1 explicitly selectable and honored. |
| Pairwise evaluation | omitted Ruleset preserves historical `evaluation_id`; v2 is a distinct identity; the planned Ruleset reaches the launched argv; group stays v2-only; the non-plan builder stays argument-identical when unset; preset Ruleset surfaced; preset without a Ruleset leaves selection alone; end-to-end propagation through `AgentDesigner`. |
| CLI listing | Python/VM labels correct per agent; legend states the rule both ways and never mentions Redcode/pMARS; label vocabulary matches the Designer's; label agrees with the engine's own Ruleset-v2 restriction; output is pure ASCII. |
| Existing | `tests/test_agent_combo_runtime_labels.py` updated to the new explanation copy, asserted against the shared constant rather than a duplicated literal. |

Results:

| Suite | Result |
|---|---|
| Full default suite (`pytest`, `-m "not gui"`) | **2334 passed, 14 skipped, 2 deselected** before the final additions; re-run green after |
| GUI suite (`pytest tests/ -m ""`) | **221 passed, 1 skipped** |
| `engine/tests/test_default_python_agents.py` | 38 passed |
| `engine/tests/test_windows_packaging_spec.py` | 15 passed |
| Ruff (`ruff check .`) | **All checks passed** |
| mypy `engine/src/battle_engine` | **Success: no issues found in 86 source files** |
| mypy `client/src/battle_client` | **Success: no issues found in 12 source files** |

`app/` is not a canonical mypy gate (`pyproject.toml` names only the two src
roots; CI runs ruff + pytest). It was checked anyway and reports **65
errors both at clean HEAD and after these changes** — verified by running
mypy in a throwaway git worktree at `43d52f2`. This alpha adds no new mypy
findings; the pre-existing `app/` debt is unchanged and out of scope.

## 15. CI

See §19 — recorded at publication time.

## 16. Compatibility

Unchanged by this alpha:

```text
Ruleset:        bytefray-rules-2, unchanged
                bytefray-rules-1, unchanged
Agent API:      v1, unchanged
Result schema:  v1, unchanged
Replay schema:  v3, unchanged
Existing agents: remain valid; no manifest or entrypoint contract changed
VM/blob:        unchanged, Ruleset-v1-only
Redcode/pMARS:  unchanged, external, no Bytefray Ruleset
```

The one intentional behavior change is a **GUI default**: Agent Designer
development tests and pairwise evaluations now default to
`bytefray-rules-2` instead of silently inheriting the CLI's v1 default.
Ruleset v1 remains explicitly selectable in both. No CLI default changed.
No evaluation identity moves: `None` and explicit v1 resolve identically.

## 17. Alpha2 gates

| Gate | Result |
|---|---|
| G1 — Frozen benchmark integrity | **PASS** — 9/9 match, zero drift, before and after |
| G2 — Starter functionality | **PASS** — install, discover, validate, and run normally in source and frozen builds |
| G3 — Ruleset clarity | **PASS** — Agent Development shows and sends an explicit Ruleset, defaulting to v2 |
| G4 — Evaluation clarity | **PASS** — pairwise selector added, defaults to v2, propagates explicitly; group unchanged |
| G5 — VM compatibility | **PASS** — VM selection still forces and explains Ruleset v1; engine rejections unchanged |
| G6 — Redcode accuracy | **PASS** — no text assigns Redcode a Ruleset; asserted by test |
| G7 — Packaging | **PASS** — both starters present in wheel, sdist, and a real frozen build; generic regression test added |
| G8 — Full tests | **PASS** — default suite and GUI suite green |
| G9 — Static gates | **PASS** — Ruff clean; both canonical mypy gates clean |
| G10 — End-to-end replay | **PASS** — frozen-exe-produced core capture visible in the packaged Replay Viewer with callout, marker, and seeking |
| G11 — CI | see §19 |
| G12 — Clean tree / version consistency | see §19 |

## 18. Verdict

Recorded at publication time — see §19.

## 19. Publication result

Recorded at publication time.

## 20. Deferred maintenance findings

Recorded here rather than fixed, to keep this alpha scoped. None affects
qualification.

1. **Repo-root `agents/` contains committed developer scratch.** Four VM
   manifests (`bomber`, `chatgpt_hunter`, `claude_agent`, `replicator`)
   reference `model.blob` files that are gitignored, so those agents are
   broken on a fresh clone. `agents/example/agent.yaml` declares
   `name: runner`, mismatching its own directory. `agents/tester2` is a
   byte-identical copy of the blank scaffold. This directory is user data
   discovered at runtime and is not shipped, so none of it reaches a
   packaged product.
2. **"Reference agent" is overloaded three ways** — the four v2-alpha
   Python agents in `battle_engine.reference_agents`; the VM built-ins in
   `battle_engine.builtins` (which is what `engine/tests/test_reference_agents.py`
   actually covers); and `agent_test.REFERENCE_OPPONENT_NAME`, the blank
   scaffold. New product vocabulary should keep avoiding the word.
3. **The four Python reference agents remain invisible to users.**
   `reference_agent_spec`/`REFERENCE_AGENT_NAMES` have no production call
   site outside tests, and `reference_agents/` is absent from all three
   PyInstaller specs. That is correct for frozen research content, and
   Raider/Sentinel now cover the product need, but the asymmetry between
   wheel (present) and frozen builds (absent) is worth an explicit decision
   someday.
4. **`--start-tick` opens the Replay Viewer paused.** Reasonable UX, but
   undocumented in `--help`, which describes only `--paused` as affecting
   the initial play state.

## 21. Phase 6 inputs

- Alpha2's two GUI default changes (development test, pairwise evaluation)
  are the main thing worth user feedback before RC; both are reversible in
  one line if feedback is negative.
- The CLI's Ruleset-v1 default is now the last remaining place where
  Bytefray silently picks the non-current gameplay ruleset. Changing it is
  a breaking CLI change and was deliberately excluded here; Phase 6 should
  make an explicit, documented decision rather than leaving it implicit.
- The generic packaging regression test added in §12 should be the model
  for any future bundled-data directory.
- Deferred findings 1–4 above are candidate RC-cycle cleanups, none
  release-blocking.
