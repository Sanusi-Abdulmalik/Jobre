from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlparse

from rapidfuzz import fuzz

from packages.common.security import canonicalize_url
from packages.normalization.engine import NormalizedJobInput


class DeduplicationOutcome(StrEnum):
    DISTINCT = "DISTINCT"
    PENDING_REVIEW = "PENDING_REVIEW"
    AUTO_MERGE = "AUTO_MERGE"


SENIORITY_CONFLICT_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"intern", "internship"}),
    frozenset({"junior", "jr", "entry", "associate", "grad", "graduate"}),
    frozenset({"senior", "sr"}),
    frozenset({"staff", "principal", "distinguished", "architect"}),
    frozenset({"manager", "director", "vp", "head", "chief"}),
)

ROLE_SPECIALIZATION_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"frontend", "front"}),
    frozenset({"backend", "back"}),
    frozenset({"ios"}),
    frozenset({"android"}),
    frozenset({"devops", "sre"}),
    frozenset({"qa", "sdet"}),
)

ATS_REQ_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"greenhouse\.io/[^/]+/jobs/(\d+)", re.I)),
    ("greenhouse_q", re.compile(r"[?&]gh_jid=(\d+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)),
    ("ashby", re.compile(r"ashbyhq\.com/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/[^/]+/j/([A-Z0-9]{8,12})", re.I)),
    ("workday", re.compile(r"myworkdayjobs\.com/.+_(JR\d+|R-?\d+|\d{4}-\d+)", re.I)),
    ("pinpoint", re.compile(r"pinpointhq\.com/postings/([0-9a-f-]{16,36})", re.I)),
    ("gem", re.compile(r"jobs\.gem\.com/[^/]+/([0-9a-f-]{20,36})", re.I)),
    ("bamboohr", re.compile(r"([a-z0-9-]+)\.bamboohr\.com/careers/(\d+)", re.I)),
)


@dataclass
class CandidateJobSnapshot:
    job_id: str
    company_id: str
    normalized_company_name: str
    title: str
    normalized_title: str
    description_text: str
    location_raw: str | None
    city: str | None
    region: str | None
    country_code: str | None
    workplace_type: str
    primary_application_url: str | None
    primary_source_url: str | None
    known_external_ids: list[str]
    known_application_urls: list[str]
    original_posted_at: datetime | None = None


@dataclass
class DeduplicationDecision:
    outcome: DeduplicationOutcome
    matched_job_id: str | None
    score: float
    reason: str
    signals: dict[str, Any]


def extract_ats_requisition_token(url: str | None) -> str | None:
    if not url:
        return None
    for prefix, pattern in ATS_REQ_PATTERNS:
        m = pattern.search(url)
        if m:
            norm_prefix = "greenhouse" if prefix.startswith("greenhouse") else prefix
            token_val = ":".join(g.lower() for g in m.groups() if g)
            return f"{norm_prefix}:{token_val}"
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "gh_jid" in qs and qs["gh_jid"]:
        return f"greenhouse:{qs['gh_jid'][0].lower()}"
    return None


def _is_deep_job_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    segments = [s for s in (parsed.path or "").split("/") if s]
    if len(segments) >= 2:
        last = segments[-1].lower()
        if last not in ("jobs", "careers", "apply", "openings", "positions", "search"):
            return True
    if any(k in (parsed.query or "").lower() for k in ("gh_jid=", "jobid=", "jid=", "reqid=")):
        return True
    return False


def _has_group_conflict(tokens_a: set[str], tokens_b: set[str], groups: tuple[frozenset[str], ...]) -> bool:
    matched_a = {idx for idx, g in enumerate(groups) if tokens_a & g}
    matched_b = {idx for idx, g in enumerate(groups) if tokens_b & g}
    if matched_a and matched_b and matched_a != matched_b:
        return True
    # One explicitly intern/junior/manager while the other has none
    exclusive_indices = {0, 4} if groups is SENIORITY_CONFLICT_GROUPS else set()
    for idx in exclusive_indices:
        if (idx in matched_a) != (idx in matched_b):
            return True
    return False


def _description_jaccard(desc_a: str, desc_b: str) -> float:
    words_a = re.findall(r"[a-z0-9]{3,}", (desc_a or "").lower()[:5000])
    words_b = re.findall(r"[a-z0-9]{3,}", (desc_b or "").lower()[:5000])
    if len(words_a) < 8 or len(words_b) < 8:
        if not words_a or not words_b:
            return 0.0
        return fuzz.token_set_ratio(" ".join(words_a), " ".join(words_b)) / 100.0

    set_a = set(words_a)
    set_b = set(words_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    word_jaccard = len(set_a & set_b) / union

    bigrams_a = {f"{words_a[i]}_{words_a[i+1]}" for i in range(len(words_a) - 1)}
    bigrams_b = {f"{words_b[i]}_{words_b[i+1]}" for i in range(len(words_b) - 1)}
    bg_union = len(bigrams_a | bigrams_b)
    bg_jaccard = (len(bigrams_a & bigrams_b) / bg_union) if bg_union else word_jaccard
    return round(0.55 * word_jaccard + 0.45 * bg_jaccard, 4)


def _location_compatibility(incoming: NormalizedJobInput, existing: CandidateJobSnapshot) -> tuple[float, bool]:
    """Return (location_score 0..1, has_hard_conflict)."""
    city_a = (incoming.city or "").lower().strip()
    city_b = (existing.city or "").lower().strip()
    cc_a = (incoming.country_code or "").upper().strip()
    cc_b = (existing.country_code or "").upper().strip()

    if city_a and city_b:
        if city_a == city_b:
            return 1.0, False
        sim = fuzz.ratio(city_a, city_b) / 100.0
        if sim >= 0.90:
            return sim, False
        # Distinct cities -> hard conflict!
        return 0.0, True

    if cc_a and cc_b and cc_a != cc_b:
        return 0.0, True

    if incoming.workplace_type == "REMOTE" and existing.workplace_type == "REMOTE":
        if cc_a and cc_b:
            return (1.0, False) if cc_a == cc_b else (0.0, True)
        return 0.92, False

    raw_a = (incoming.location_raw or "").lower().strip()
    raw_b = (existing.location_raw or "").lower().strip()
    if raw_a and raw_b:
        if raw_a == raw_b:
            return 1.0, False
        sim = fuzz.token_set_ratio(raw_a, raw_b) / 100.0
        return sim, sim < 0.45

    return 0.65, False


def score_pair(
    incoming: NormalizedJobInput,
    existing: CandidateJobSnapshot,
) -> tuple[float, str, dict[str, Any]]:
    inc_app = canonicalize_url(incoming.application_url)
    inc_src = canonicalize_url(incoming.source_job_url)
    existing_urls = {
        canonicalize_url(u)
        for u in ([existing.primary_application_url, existing.primary_source_url] + existing.known_application_urls)
        if u
    }

    company_sim = (
        1.0
        if incoming.normalized_company_name == existing.normalized_company_name
        else fuzz.token_sort_ratio(incoming.normalized_company_name, existing.normalized_company_name) / 100.0
    )

    # 1. Exact deep application URL match
    app_url_match = bool(inc_app and _is_deep_job_url(inc_app) and inc_app in existing_urls)
    src_url_match = bool(inc_src and _is_deep_job_url(inc_src) and inc_src in existing_urls)

    # 2. ATS Requisition Token match
    inc_tokens = {
        t for t in (extract_ats_requisition_token(incoming.application_url), extract_ats_requisition_token(incoming.source_job_url)) if t
    }
    ext_tokens = {
        t
        for u in ([existing.primary_application_url, existing.primary_source_url] + existing.known_application_urls)
        for t in [extract_ats_requisition_token(u)]
        if t
    }
    ats_token_match = bool(inc_tokens & ext_tokens)

    tokens_a = set(incoming.normalized_title.split())
    tokens_b = set(existing.normalized_title.split())
    seniority_conflict = _has_group_conflict(tokens_a, tokens_b, SENIORITY_CONFLICT_GROUPS)
    role_conflict = _has_group_conflict(tokens_a, tokens_b, ROLE_SPECIALIZATION_GROUPS)

    title_sim = fuzz.token_sort_ratio(incoming.normalized_title, existing.normalized_title) / 100.0
    loc_sim, loc_conflict = _location_compatibility(incoming, existing)
    desc_sim = _description_jaccard(incoming.description_text, existing.description_text)

    signals = {
        "app_url_match": app_url_match or src_url_match,
        "ats_token_match": ats_token_match,
        "company_similarity": round(company_sim, 4),
        "title_similarity": round(title_sim, 4),
        "location_similarity": round(loc_sim, 4),
        "location_conflict": loc_conflict,
        "description_similarity": round(desc_sim, 4),
        "seniority_conflict": seniority_conflict,
        "role_conflict": role_conflict,
    }

    if (app_url_match or src_url_match) and not loc_conflict and not seniority_conflict:
        return 0.98, "exact_application_url_match", signals

    if ats_token_match and company_sim >= 0.80 and not seniority_conflict:
        return 0.96, "ats_requisition_id_match", signals

    # Guardrail: Never merge different companies, conflicting seniorities, conflicting tracks, or conflicting cities
    if company_sim < 0.85 or seniority_conflict or role_conflict or loc_conflict:
        return round(min(0.45, 0.3 * company_sim + 0.3 * title_sim), 4), "guardrail_distinct", signals

    # Guardrail: Never auto-merge based on title similarity alone!
    if title_sim < 0.82:
        return round(0.40 * title_sim + 0.30 * desc_sim + 0.30 * company_sim, 4), "low_title_similarity", signals

    weighted = (
        0.22 * company_sim
        + 0.30 * title_sim
        + 0.20 * loc_sim
        + 0.28 * desc_sim
    )

    # Require substantive description similarity for high-confidence composite merge
    if desc_sim < 0.72:
        capped = min(weighted, 0.82)
        return round(capped, 4), "composite_needs_description_verification", signals

    return round(weighted, 4), "composite_multi_signal_match", signals


def evaluate_duplicate_candidate(
    incoming: NormalizedJobInput,
    candidates: list[CandidateJobSnapshot],
    *,
    auto_merge_threshold: float = 0.88,
    review_threshold: float = 0.68,
) -> DeduplicationDecision:
    best_score = 0.0
    best_reason = "no_candidates"
    best_signals: dict[str, Any] = {}
    best_job_id: str | None = None

    for cand in candidates:
        score, reason, signals = score_pair(incoming, cand)
        if score > best_score:
            best_score = score
            best_reason = reason
            best_signals = signals
            best_job_id = cand.job_id

    if best_job_id and best_score >= auto_merge_threshold:
        return DeduplicationDecision(
            outcome=DeduplicationOutcome.AUTO_MERGE,
            matched_job_id=best_job_id,
            score=best_score,
            reason=best_reason,
            signals=best_signals,
        )
    if best_job_id and best_score >= review_threshold:
        return DeduplicationDecision(
            outcome=DeduplicationOutcome.PENDING_REVIEW,
            matched_job_id=best_job_id,
            score=best_score,
            reason=best_reason,
            signals=best_signals,
        )
    return DeduplicationDecision(
        outcome=DeduplicationOutcome.DISTINCT,
        matched_job_id=None,
        score=best_score,
        reason=best_reason,
        signals=best_signals,
    )
