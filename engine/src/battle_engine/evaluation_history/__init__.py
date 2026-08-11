"""Qt-free evaluation history: v1/v2 adaptation, discovery, and comparison.

See docs/specs/evaluation_history.md. This package depends only on
``battle_engine.{agent_evaluation,agents,config,paths,project_info,
result_model,replay}`` and must never import Qt/pygame/Designer code
(``test_evaluation_history_headless_imports`` enforces this).
"""

from __future__ import annotations

from .comparison import (
    AlignedComparison,
    BaselineContext,
    ComparisonDenominators,
    ComparisonRow,
    align,
)
from .discovery import (
    AmbiguousSelectorError,
    ArtifactListing,
    DiscoveredEvaluation,
    adapt_any,
    default_roots,
    discover,
    resolve_selector,
)
from .models import (
    AdaptedCell,
    ArtifactLocation,
    ArtifactPathEscapeError,
    ArtifactReadError,
    ConfidenceValue,
    EvaluationSummary,
    FieldConfidence,
    HealthCode,
    HealthReport,
    RevisionVerificationStatus,
    SchemaSupport,
    resolve_contained_path,
)
from .v1_adapter import adapt_v1
from .v2_adapter import adapt_v2
from .verification import CellVerificationOutcome, SummaryVerification, verify_cell, verify_summary

__all__ = [
    "AdaptedCell",
    "AlignedComparison",
    "AmbiguousSelectorError",
    "ArtifactListing",
    "ArtifactLocation",
    "ArtifactPathEscapeError",
    "ArtifactReadError",
    "BaselineContext",
    "CellVerificationOutcome",
    "ComparisonDenominators",
    "ComparisonRow",
    "ConfidenceValue",
    "DiscoveredEvaluation",
    "EvaluationSummary",
    "FieldConfidence",
    "HealthCode",
    "HealthReport",
    "RevisionVerificationStatus",
    "SchemaSupport",
    "SummaryVerification",
    "adapt_any",
    "adapt_v1",
    "adapt_v2",
    "align",
    "default_roots",
    "discover",
    "resolve_contained_path",
    "resolve_selector",
    "verify_cell",
    "verify_summary",
]
