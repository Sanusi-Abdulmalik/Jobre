from packages.deduplication.engine import (
    CandidateJobSnapshot,
    DeduplicationDecision,
    DeduplicationOutcome,
    evaluate_duplicate_candidate,
    extract_ats_requisition_token,
)

__all__ = [
    "CandidateJobSnapshot",
    "DeduplicationDecision",
    "DeduplicationOutcome",
    "evaluate_duplicate_candidate",
    "extract_ats_requisition_token",
]
