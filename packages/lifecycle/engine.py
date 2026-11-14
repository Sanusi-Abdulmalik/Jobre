from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from packages.normalization.engine import NormalizedJobInput


class JobStatus(StrEnum):
    ACTIVE = "ACTIVE"
    POSSIBLY_CLOSED = "POSSIBLY_CLOSED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


TRACKED_JOB_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "title"),
    ("description_text", "description_text"),
    ("location_raw", "location_raw"),
    ("salary_min", "salary_min"),
    ("salary_max", "salary_max"),
    ("salary_currency", "salary_currency"),
    ("employment_type", "employment_type"),
    ("workplace_type", "workplace_type"),
    ("primary_application_url", "application_url"),
)


@dataclass
class FieldDiff:
    field_name: str
    old_value: str | None
    new_value: str | None


@dataclass
class TransitionResult:
    new_status: str
    new_missing_runs: int
    status_changed: bool
    reason: str


def _stringify(val: Any) -> str | None:
    if val is None or val == "":
        return None
    s = str(val).strip()
    return s[:2000] if s else None


def compute_field_diffs(
    existing_fields: dict[str, Any],
    incoming: NormalizedJobInput,
) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for db_col, incoming_attr in TRACKED_JOB_FIELDS:
        old_raw = existing_fields.get(db_col)
        new_raw = getattr(incoming, incoming_attr, None)

        if db_col in ("salary_min", "salary_max") and old_raw is not None and new_raw is not None:
            try:
                if float(old_raw) == float(new_raw):
                    continue
            except (TypeError, ValueError):
                pass

        old_s = _stringify(old_raw)
        new_s = _stringify(new_raw)
        if old_s != new_s:
            # Do not wipe enriched salary if a secondary source simply omitted salary
            if db_col in ("salary_min", "salary_max", "salary_currency") and old_s is not None and new_s is None:
                continue
            diffs.append(FieldDiff(field_name=db_col, old_value=old_s, new_value=new_s))
    return diffs


def evaluate_missing_job_transition(
    *,
    current_status: str,
    previous_missing_runs: int,
    run_succeeded: bool,
    is_complete_snapshot: bool,
    other_active_sources_count: int = 0,
    closure_threshold: int = 2,
) -> TransitionResult:
    """
    CRITICAL CLOSURE RULE:
    Never transition jobs toward closure when an ingestion run failed, timed out,
    was rate-limited, or produced an incomplete snapshot.
    """
    if not run_succeeded or not is_complete_snapshot:
        return TransitionResult(
            new_status=current_status,
            new_missing_runs=previous_missing_runs,
            status_changed=False,
            reason="run_incomplete_or_failed_no_closure",
        )

    next_missing = previous_missing_runs + 1

    # If another verified active source still advertises this canonical job, keep canonical job ACTIVE
    if other_active_sources_count > 0:
        return TransitionResult(
            new_status=JobStatus.ACTIVE.value,
            new_missing_runs=next_missing,
            status_changed=(current_status != JobStatus.ACTIVE.value),
            reason="still_active_on_secondary_source",
        )

    if next_missing >= max(1, closure_threshold):
        target = JobStatus.CLOSED.value
        return TransitionResult(
            new_status=target,
            new_missing_runs=next_missing,
            status_changed=(current_status != target),
            reason=f"absent_across_{next_missing}_successful_snapshots",
        )

    target = JobStatus.POSSIBLY_CLOSED.value
    return TransitionResult(
        new_status=target,
        new_missing_runs=next_missing,
        status_changed=(current_status != target),
        reason="absent_in_single_successful_snapshot",
    )
