# Bytefray v4.0.0-alpha1 Release Report

## 1. Research endpoint
97d67ee99c3e871a0cfe6046de1634cd2397af72

## 2. Original failed candidate
Record c7854ed948956e0e65c7452a34747c2626d84e9e failed because the research process runtime was not connected to the canonical user-invocable match path, leaving the product path incapable of invoking v4 mechanics.

## 3. Design freeze
5e5d6daab0ff333d11f8bcdc163870e4c79ac921

## 4. Remediation commits
* 5046a1d fix(v4): preserve historical compatibility boundaries
* 93506ed feat(v4): integrate API v2 process runtime
* 930e074 feat(v4): expose canonical process matches
* d633f66 build(v4): harden alpha distribution contracts
* 783dc9c fix(cli): bootstrap starters for direct matches

## 5. Historical identity repair
Historical v1–v3 identities and wire semantics were restored. Old goldens were restored, not re-blessed. Schema-4 changes are correctly isolated.

## 6. Canonical production path
NativeMatchService, CLI, and frozen products now natively route ytefray-rules-4-alpha1 through the canonical process runtime supporting API v2.

## 7. Agent API v2
API v2 defines the final contract: absolute READ/WRITE addresses, signed relative MOVE deltas, declare_processes() validation, and Stage 6 Minimal Temporal Contract observations.

## 8. Replay Schema 4
Production matches generate Schema 4 replays that correctly include process state arrays, independent anchors, and D=1 exact-anchor disruption markers.

## 9. Starter population
Five active starters (4_claimer, 4_concentrated_attacker, 4_local_defender, 4_scout, 4_defender_scout) successfully package and discover natively, with corrected absolute/relative addressing.

## 10. Ecology
360 canonical production cells. Zero execution failures. Anchors moved and disruption occurred organically.

## 11. Determinism
Repeated evaluation artifacts were byte-for-byte identical (144 replays/results byte-identical, 180 paired seat permutations). Outcome-stable with measurable placement/scheduler score sensitivity.

## 12. Tests
Final exact Windows result:
2417 passed
14 skipped
2 deselected
0 failed
Plus focused v4 results.

Linux result:
2413 passed
17 skipped
2 deselected
Plus zero-skip focused v4 results.

## 13. Static analysis
Mypy/Ruff/diff checks pass completely.

## 14. Performance
* ~2,186 ticks/s for 5,000-tick direct match
* ~6.58 MB Schema-4 replay
* ~8.45 cells/s for supervised ecology matrix

## 15. Packaging
Wheel and sdist successfully package all v4 starters and exclude .pyc/__pycache__ artifacts. Strict wheel checker passes.

## 16. Windows frozen artifacts
All four Windows portable products build successfully. The unified executable correctly reports v4.0.0-alpha1, discovers v4 starters, executes API-v2 matches, and emits schema 4 replays that the headless viewer correctly consumes.

## 17. Installer
The installer was generated from the final source using Inno Setup.

## 18. Linux final-wheel smoke
Passed. Wheel installed into a neutral Python environment successfully ran matches and generated Schema-4 replays.

## 19. Known alpha limitations
V4 gameplay is still in prerelease testing. Multi-process balance and disruption tuning may require adjustments. Dynamic spawning is deferred until future milestones.

## 20. Assets
Exact final names, sizes, hashes:
e8e1395467580cc48118af17d9c4418d03ce2304b089edda9e0bed4429e55cc9  Bytefray-Setup-4.0.0-alpha1.exe (82959364 bytes)
9206102ab9796c27cb35ec82b2a7c134228201c9a21bed1c1ba61d064a80b8e4  bytefray-4.0.0-alpha1-windows.zip (143246650 bytes)
4fa0acac89892d224e02e6c3cb3d9017c5b25c85de773cdcdc51da38a6d6554d  bytefray-4.0.0a1-py3-none-any.whl (788140 bytes)
412b19de800787b324397f13730df1bc416a48ec266205621f57b194994caae0  bytefray-4.0.0a1.tar.gz (763381 bytes)

## 21. Git state
The branch 4-research contains the complete canonical qualification. Head is at final commit with all tests and bootstrap corrections clean.

## 22. Final publication decision
# QUALIFIED FOR v4.0.0-alpha1 PUBLICATION
