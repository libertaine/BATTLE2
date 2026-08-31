# Bytefray Documentation Inventory and Classification

This document records the comprehensive documentation inventory and classification
performed as part of the Bytefray documentation reorganization.

## Summary Counts

| Classification | Count | Description |
|---|---|---|
| `KEEP_CURRENT` | 39 | Current authoritative/operational documentation or normative specifications |
| `KEEP_ACTIVE_RESEARCH` | 4 | Active Bytefray v4 research reports and experimental evidence |
| `ARCHIVE_V1` | 15 | Historical v0.x / v1.x engineering records and qualification reports |
| `ARCHIVE_V2` | 28 | Historical v2.x research, characterization, and beta qualification reports |
| `ARCHIVE_V3` | 23 | Historical v3.x research baseline, payoff studies, and qualification reports |
| `REMOVE_SUPERSEDED` | 0 | Historical records fully superseded by final reports or changelogs |
| `REMOVE_DUPLICATE` | 1 | Redundant, empty placeholder, or duplicate files |
| `REVIEW_MANUALLY` | 0 | Genuinely ambiguous items left untouched for manual review |
| **Total** | **110** | **Total documentation files evaluated** |

---

## Detailed Inventory

| Original Path | Classification | Destination / Action | Reason / Historical Value |
|---|---|---|---|
| `AGENTS.md` | `KEEP_CURRENT` | `AGENTS.md` | Authoritative tool-agnostic development guidance for coding agents |
| `ARCHITECTURE.md` | `KEEP_CURRENT` | `ARCHITECTURE.md` | Current system component map and architectural boundaries |
| `CHANGELOG.md` | `KEEP_CURRENT` | `CHANGELOG.md` | Authoritative project version history and release logs |
| `CLAUDE.md` | `KEEP_CURRENT` | `CLAUDE.md` | Claude tool pointer deferring to AGENTS.md |
| `CONTRIBUTING.md` | `KEEP_CURRENT` | `CONTRIBUTING.md` | Current contribution workflow and guidelines |
| `INSTALL.md` | `KEEP_CURRENT` | `INSTALL.md` | Current multi-platform installation and environment documentation |
| `README.md` | `KEEP_CURRENT` | `README.md` | Primary product documentation and navigation root |
| `SECURITY.md` | `KEEP_CURRENT` | `SECURITY.md` | Project security and vulnerability reporting policy |
| `V4_PROCESS_SEMANTICS_RESEARCH.md` | `REMOVE_DUPLICATE` | `<deleted>` | 0-byte empty file; authoritative copy exists at docs/research/v4/V4_PROCESS_SEMANTICS_RESEARCH.md |
| `V4_SCHEDULER_RESEARCH.md` | `KEEP_ACTIVE_RESEARCH` | `docs/research/v4/V4_SCHEDULER_RESEARCH.md` | Authoritative v4 scheduler grain and rotation research report |
| `docs/AGENT_API_V1.md` | `KEEP_CURRENT` | `docs/AGENT_API_V1.md` | Normative technical contract for Agent API v1 |
| `docs/AGENT_AUTHORING.md` | `KEEP_CURRENT` | `docs/AGENT_AUTHORING.md` | Current agent authoring and scaffolding guide |
| `docs/AGENT_LAB.md` | `KEEP_CURRENT` | `docs/AGENT_LAB.md` | Current Agent Lab debugging, tracing, and containment guide |
| `docs/COMPATIBILITY.md` | `KEEP_CURRENT` | `docs/COMPATIBILITY.md` | Current compatibility axes and stability contracts |
| `docs/DEVELOPMENT_METHOD.md` | `KEEP_CURRENT` | `docs/DEVELOPMENT_METHOD.md` | Current AI-assisted development method reference |
| `docs/FUTURE_PLANS.md` | `KEEP_CURRENT` | `docs/FUTURE_PLANS.md` | Current product roadmap and future architectural ideas |
| `docs/LINUX_INSTALL.md` | `KEEP_CURRENT` | `docs/LINUX_INSTALL.md` | Current headless-first Linux installation guide |
| `docs/MANUAL_SMOKE_TESTS.md` | `KEEP_CURRENT` | `docs/MANUAL_SMOKE_TESTS.md` | Current manual UI and replay smoke test procedures |
| `docs/PROJECT_HISTORY.md` | `KEEP_CURRENT` | `docs/PROJECT_HISTORY.md` | Current high-level historical narrative of project development |
| `docs/REPLAY_SCHEMA.md` | `KEEP_CURRENT` | `docs/REPLAY_SCHEMA.md` | Normative schema specification for battle2.replay |
| `docs/RESULT_SCHEMA.md` | `KEEP_CURRENT` | `docs/RESULT_SCHEMA.md` | Normative schema specification for battle2.result |
| `docs/ROADMAP.md` | `KEEP_CURRENT` | `docs/ROADMAP.md` | Current release roadmap and milestone tracking |
| `docs/RUFF_DEBT.md` | `KEEP_CURRENT` | `docs/RUFF_DEBT.md` | Current linter debt documentation and exception policy |
| `docs/RULES.md` | `KEEP_CURRENT` | `docs/RULES.md` | Normative specification for Bytefray Ruleset v1 |
| `docs/RULES_V2.md` | `KEEP_CURRENT` | `docs/RULES_V2.md` | Normative specification for Bytefray Ruleset v2 |
| `docs/TOURNAMENTS.md` | `KEEP_CURRENT` | `docs/TOURNAMENTS.md` | Current headless tournament runner and service guide |
| `docs/WINDOWS_DEV_NOTES.md` | `KEEP_CURRENT` | `docs/WINDOWS_DEV_NOTES.md` | Current Windows development quirks and testing notes |
| `docs/specs/agent_designer_workflow.md` | `KEEP_CURRENT` | `docs/specs/agent_designer_workflow.md` | Normative feature specification for agent_designer_workflow |
| `docs/specs/agent_evaluation.md` | `KEEP_CURRENT` | `docs/specs/agent_evaluation.md` | Normative feature specification for agent_evaluation |
| `docs/specs/agent_lab.md` | `KEEP_CURRENT` | `docs/specs/agent_lab.md` | Normative feature specification for agent_lab |
| `docs/specs/agent_package.md` | `KEEP_CURRENT` | `docs/specs/agent_package.md` | Normative feature specification for agent_package |
| `docs/specs/agent_revision.md` | `KEEP_CURRENT` | `docs/specs/agent_revision.md` | Normative feature specification for agent_revision |
| `docs/specs/agent_scaffold.md` | `KEEP_CURRENT` | `docs/specs/agent_scaffold.md` | Normative feature specification for agent_scaffold |
| `docs/specs/agent_test.md` | `KEEP_CURRENT` | `docs/specs/agent_test.md` | Normative feature specification for agent_test |
| `docs/specs/agent_validation.md` | `KEEP_CURRENT` | `docs/specs/agent_validation.md` | Normative feature specification for agent_validation |
| `docs/specs/discover_agents.md` | `KEEP_CURRENT` | `docs/specs/discover_agents.md` | Normative feature specification for discover_agents |
| `docs/specs/evaluation_history.md` | `KEEP_CURRENT` | `docs/specs/evaluation_history.md` | Normative feature specification for evaluation_history |
| `docs/specs/replay_analysis.md` | `KEEP_CURRENT` | `docs/specs/replay_analysis.md` | Normative feature specification for replay_analysis |
| `docs/specs/replay_session.md` | `KEEP_CURRENT` | `docs/specs/replay_session.md` | Normative feature specification for replay_session |
| `docs/specs/resolve_agent.md` | `KEEP_CURRENT` | `docs/specs/resolve_agent.md` | Normative feature specification for resolve_agent |
| `docs/specs/run_match_pmars.md` | `KEEP_CURRENT` | `docs/specs/run_match_pmars.md` | Normative feature specification for run_match_pmars |
| `docs/research/v4/V4_DYNAMIC_PROCESS_ECONOMICS_RESEARCH.md` | `KEEP_ACTIVE_RESEARCH` | `docs/research/v4/V4_DYNAMIC_PROCESS_ECONOMICS_RESEARCH.md` | Active v4 R2 dynamic process economy and capacity research report |
| `docs/research/v4/V4_PROCESS_EQUIVALENCE_RESEARCH.md` | `KEEP_ACTIVE_RESEARCH` | `docs/research/v4/V4_PROCESS_EQUIVALENCE_RESEARCH.md` | Active v4 R1b multi-process monolithic equivalence challenge report |
| `docs/research/v4/V4_PROCESS_SEMANTICS_RESEARCH.md` | `KEEP_ACTIVE_RESEARCH` | `docs/research/v4/V4_PROCESS_SEMANTICS_RESEARCH.md` | Active v4 R1 process semantics and action cursor investigation report |
| `docs/V0_2_MIGRATION.md` | `ARCHIVE_V1` | `docs/archive/v1/V0_2_MIGRATION.md` | Historical migration guide from pre-v0.2 schema to v0.2 |
| `docs/V1_4_PLATFORM_INTEGRITY.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_4_PLATFORM_INTEGRITY.md` | Historical v1.4 platform integrity audit and command-wrapper retirement rationale |
| `docs/performance/V1_4_SCALING.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_4_SCALING.md` | Historical v1.4 arena operation performance benchmarks and scaling analysis |
| `docs/V1_5_PHASE1_RULESET_V1_BASELINE.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE1_RULESET_V1_BASELINE.md` | Historical v1 engineering record: Baseline characterization of Ruleset v1 execution |
| `docs/V1_5_PHASE2_SCHEDULER_ABSTRACTION.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE2_SCHEDULER_ABSTRACTION.md` | Historical v1 engineering record: Design rationale for extracting scheduler abstraction from core VM |
| `docs/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE3_RULESET_POLICY_DISPATCH.md` | Historical v1 engineering record: Architectural separation of ruleset policies from engine core |
| `docs/V1_5_PHASE4_TERMINATION_POLICY.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE4_TERMINATION_POLICY.md` | Historical v1 engineering record: Design and extraction of match termination policy logic |
| `docs/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE5_ENTRANT_IDENTITY_EXECUTION_STATE.md` | Historical v1 engineering record: Architecture of entrant identity and execution state isolation |
| `docs/V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_5_PHASE6_ARCHITECTURE_EQUIVALENCE.md` | Historical v1 engineering record: Equivalence qualification proving refactored engine matches legacy baseline |
| `docs/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE1_EVALUATION_SCALE_BASELINE.md` | Historical v1 engineering record: Initial evaluation harness scaling characterization and benchmark baseline |
| `docs/V1_6_PHASE2_PARALLEL_EVALUATION.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE2_PARALLEL_EVALUATION.md` | Historical v1 engineering record: Multi-process parallel evaluation architecture and speedup benchmarks |
| `docs/V1_6_PHASE3_EVALUATION_PRESETS.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE3_EVALUATION_PRESETS.md` | Historical v1 engineering record: Design of evaluation preset configurations and roster matchmaking |
| `docs/V1_6_PHASE4_EVALUATION_ANALYSIS.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE4_EVALUATION_ANALYSIS.md` | Historical v1 engineering record: Statistical analysis methodology and evaluation metrics implementation |
| `docs/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE5_BEHAVIOR_ANALYSIS.md` | Historical v1 engineering record: Agent behavioral telemetry profiling and cluster analysis method |
| `docs/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md` | `ARCHIVE_V1` | `docs/archive/v1/V1_6_PHASE6_INTEGRATED_QUALIFICATION.md` | Historical v1 engineering record: Final v1.6 integrated qualification gate and stability verification |
| `docs/V2_0_ALPHA_ARCHITECTURE.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA_ARCHITECTURE.md` | Historical v2 engineering record: Initial architecture proposal for Ruleset v2 multi-entrant arena |
| `docs/V2_0_ALPHA_RESEARCH_SUMMARY.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA_RESEARCH_SUMMARY.md` | Historical v2 engineering record: Executive summary of Alpha 1 through Alpha 11 gameplay research findings |
| `docs/V2_0_ALPHA1_EVALUATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA1_EVALUATION.md` | Historical v2 engineering record: Alpha 1 evaluation methodology and baseline agent ecology |
| `docs/V2_0_ALPHA2_REACTIVE_DEFENSE.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA2_REACTIVE_DEFENSE.md` | Historical v2 engineering record: Reactive defense characterization and core protection mechanics |
| `docs/V2_0_ALPHA3_SCORING_SENSITIVITY.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA3_SCORING_SENSITIVITY.md` | Historical v2 engineering record: Sensitivity analysis of territory and kill scoring weights |
| `docs/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA4_MULTI_ENTRANT_FEASIBILITY.md` | Historical v2 engineering record: Multi-entrant (N>=3) arena scaling and collision feasibility |
| `docs/V2_0_ALPHA4_1_WINNER_SEMANTICS.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA4_1_WINNER_SEMANTICS.md` | Historical v2 engineering record: Winner determination semantics under multi-agent survival conditions |
| `docs/V2_0_ALPHA5_MULTI_ENTRANT_SCORING_ACTIVATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA5_MULTI_ENTRANT_SCORING_ACTIVATION.md` | Historical v2 engineering record: Scoring activation thresholds in N-entrant matches |
| `docs/V2_0_ALPHA6_CORE_SEEKER_TIMING.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA6_CORE_SEEKER_TIMING.md` | Historical v2 engineering record: Timing dynamics of core-seeking offensive strategies |
| `docs/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA7_SPATIAL_CHARACTERIZATION.md` | Historical v2 engineering record: Spatial territory capture and density characterization |
| `docs/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA8_PLACEMENT_AGNOSTIC_OFFENSE.md` | Historical v2 engineering record: Placement-agnostic offensive capability across arena topologies |
| `docs/V2_0_ALPHA9_DEFENSE_ROBUSTNESS.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA9_DEFENSE_ROBUSTNESS.md` | Historical v2 engineering record: Defensive robustness against coordinated multi-entrant threats |
| `docs/V2_0_ALPHA10_STRATEGIC_ECOLOGY.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA10_STRATEGIC_ECOLOGY.md` | Historical v2 engineering record: Strategic diversity and meta-stability in multi-agent ecologies |
| `docs/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_ALPHA11_RULESET_V2_CANDIDATE_RESOLUTION.md` | Historical v2 engineering record: Resolution of Ruleset v2 candidate mechanics into formal spec |
| `docs/V2_0_RULESET_V2_CANDIDATE.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_RULESET_V2_CANDIDATE.md` | Historical v2 engineering record: Historical pre-beta candidate specification for Ruleset v2 |
| `docs/V2_0_BETA1_PLAN.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA1_PLAN.md` | Historical v2 engineering record: Phase plan for v2.0.0-beta1 productization and replay format |
| `docs/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA1_PHASE2_PRODUCT_EXECUTION.md` | Historical v2 engineering record: Beta1 execution engine integration and command dispatch |
| `docs/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA1_PHASE3_REPLAY_SEMANTICS.md` | Historical v2 engineering record: Beta1 replay event logging and telemetry schema design |
| `docs/V2_0_BETA1_PHASE4_REPLAY_HUD.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA1_PHASE4_REPLAY_HUD.md` | Historical v2 engineering record: Pygame replay viewer HUD and visualization architecture |
| `docs/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA1_PHASE5_INTEGRATED_QUALIFICATION.md` | Historical v2 engineering record: Beta1 qualification gate verifying replay determinism and UI parity |
| `docs/V2_0_BETA2_PLAN.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PLAN.md` | Historical v2 engineering record: Phase plan for v2.0.0-beta2 multi-entrant evaluation system |
| `docs/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE1_EVALUATION_METHODOLOGY.md` | Historical v2 engineering record: Beta2 pairwise and round-robin evaluation methodology |
| `docs/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE2_MULTI_ENTRANT_EVALUATION.md` | Historical v2 engineering record: Beta2 multi-entrant evaluation harness and scoring aggregation |
| `docs/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE3_MULTI_ENTRANT_ANALYSIS.md` | Historical v2 engineering record: Statistical analysis of multi-entrant tournament data |
| `docs/V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE4_1_PRE_QUALIFICATION_REMEDIATION.md` | Historical v2 engineering record: Remediation of edge-case scoring defects prior to Beta2 release |
| `docs/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE4_STRATEGIC_CHARACTERIZATION.md` | Historical v2 engineering record: Strategic characterization of Beta2 agent balance and diversity |
| `docs/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA2_PHASE5_INTEGRATED_QUALIFICATION.md` | Historical v2 engineering record: Beta2 qualification gate and test suite verification |
| `docs/V2_0_BETA3_PLAN.md` | `ARCHIVE_V2` | `docs/archive/v2/V2_0_BETA3_PLAN.md` | Historical v2 engineering record: Phase plan for v2.0.0-beta3 presentation and authoring workflow |
| `docs/V3_PRODUCT_SCOPE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PRODUCT_SCOPE.md` | Historical v3 engineering record: Product scope, thesis, and compatibility freeze for v3.0 release |
| `docs/V3_MATCH_TIMELINE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_MATCH_TIMELINE.md` | Historical v3 engineering record: Design of discrete match timeline and milestone event stream |
| `docs/V3_CORE_CAPTURE_CALLOUT.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_CORE_CAPTURE_CALLOUT.md` | Historical v3 engineering record: Replay callout system architecture for core capture events |
| `docs/V3_PHASE0_PRODUCT_SCOPE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE0_PRODUCT_SCOPE.md` | Historical v3 engineering record: Phase 0 product baseline and scope freeze audit |
| `docs/V3_PHASE0_RESEARCH_BASELINE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE0_RESEARCH_BASELINE.md` | Historical v3 engineering record: Research baseline, experimental tooling, and characterization setup for v3 |
| `docs/V3_PHASE1_ARENA_ACTION_DENSITY.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE1_ARENA_ACTION_DENSITY.md` | Historical v3 engineering record: Phase 1 arena size vs instruction budget action-density characterization |
| `docs/V3_PHASE1_PRESENTATION_BASELINE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE1_PRESENTATION_BASELINE.md` | Historical v3 engineering record: Presentation baseline and Bytefray branding parity verification |
| `docs/V3_PHASE2_AGENT_CREATION_WORKFLOW.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE2_AGENT_CREATION_WORKFLOW.md` | Historical v3 engineering record: Agent creation scaffolding and iteration workflow in Agent Designer |
| `docs/V3_PHASE2_LOCALITY_FEASIBILITY.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE2_LOCALITY_FEASIBILITY.md` | Historical v3 engineering record: Bounded-locality feasibility research (falsified negative result) |
| `docs/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE3_OFFENSE_PAYOFF_CHARACTERIZATION.md` | Historical v3 engineering record: Phase 3 offense payoff economics and write-efficiency characterization |
| `docs/V3_PHASE3_STRATEGY_ANALYSIS.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE3_STRATEGY_ANALYSIS.md` | Historical v3 engineering record: Strategy analysis and defect resolution for strategic evaluation |
| `docs/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE4_DEFENSE_PAYOFF_CHARACTERIZATION.md` | Historical v3 engineering record: Phase 4 defense payoff economics and core recovery characterization |
| `docs/V3_PHASE4_EVALUATION_INFRASTRUCTURE.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE4_EVALUATION_INFRASTRUCTURE.md` | Historical v3 engineering record: Evaluation infrastructure performance and memory optimization |
| `docs/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE5_DEFENSIVE_EVENT_DESIGN_PROPOSAL.md` | Historical v3 engineering record: Design proposal for active defensive interrupt events |
| `docs/V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE5_INTEGRATION_DISTRIBUTION_ALPHA1.md` | Historical v3 engineering record: Integration and distribution packaging qualification for v3.0-alpha1 |
| `docs/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE5A_DEFENSIVE_EVENT_QUALIFICATION.md` | Historical v3 engineering record: Qualification report falsifying selective defensive-event proposal |
| `docs/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE6_ACTIVE_DEFENSIVE_INTERVENTION_QUALIFICATION.md` | Historical v3 engineering record: Qualification of active defensive intervention mechanics |
| `docs/V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_PHASE7_HIGH_BUDGET_CONFOUND_ISOLATION.md` | Historical v3 engineering record: Isolation of high instruction-budget confounds in defensive events |
| `docs/V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_ALPHA2_STRATEGY_EXAMPLES_RULESET_CLARITY.md` | Historical v3 engineering record: Alpha 2 strategy examples and ruleset clarity improvements |
| `docs/V3_RC1_DEFAULT_RULESET_DEFECT.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_RC1_DEFAULT_RULESET_DEFECT.md` | Historical v3 engineering record: Root-cause analysis and remediation of RC1 default ruleset defect |
| `docs/V3_RC1_QUALIFICATION.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_RC1_QUALIFICATION.md` | Historical v3 engineering record: Release Candidate 1 full qualification report across platforms |
| `docs/V3_RULESET_RESEARCH_SUMMARY.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_RULESET_RESEARCH_SUMMARY.md` | Historical v3 engineering record: Comprehensive index and summary of v3 ruleset research program |
| `docs/V3_RESEARCH_CLOSEOUT.md` | `ARCHIVE_V3` | `docs/archive/v3/V3_RESEARCH_CLOSEOUT.md` | Historical v3 engineering record: Final research closeout documenting all v3 empirical findings |
