from __future__ import annotations

from decimal import Decimal
import pytest

from packages.common.security import (
    SSRFSafetyError,
    canonicalize_url,
    validate_public_url,
)
from packages.connectors.catalog import PLATFORM_CATALOG
from packages.deduplication.engine import (
    CandidateJobSnapshot,
    DeduplicationOutcome,
    evaluate_duplicate_candidate,
)
from packages.lifecycle.engine import (
    compute_field_diffs,
    evaluate_missing_job_transition,
)
from packages.normalization.engine import (
    normalize_employment_type,
    normalize_job_record,
    normalize_workplace_type,
    parse_location,
    parse_salary,
)


def test_catalog_has_all_78_required_platforms():
    ats = [p for p in PLATFORM_CATALOG if p.category == "ATS"]
    jbs = [p for p in PLATFORM_CATALOG if p.category == "JOB_BOARD"]
    assert len(ats) == 58
    assert len(jbs) == 20
    assert len(PLATFORM_CATALOG) == 78
    assert len({p.connector_key for p in PLATFORM_CATALOG}) == 78
    for spec in PLATFORM_CATALOG:
        assert spec.initial_status != "VERIFIED"


def test_normalization_accuracy_and_null_preservation():
    assert normalize_employment_type("Full-Time Regular") == "FULL_TIME"
    assert normalize_employment_type("Part time (20h/wk)") == "PART_TIME"
    assert normalize_employment_type("12-month Freelance / Contractor") == "CONTRACT"
    assert normalize_employment_type("Summer 2027 Intern") == "INTERNSHIP"
    assert normalize_employment_type(None) == "UNKNOWN"

    assert normalize_workplace_type("Fully Remote", location_raw="United States") == "REMOTE"
    assert normalize_workplace_type(None, location_raw="Hybrid - New York, NY") == "HYBRID"
    assert normalize_workplace_type("On-site", location_raw="Austin, TX") == "ON_SITE"
    assert normalize_workplace_type(None) == "UNKNOWN"

    loc = parse_location("San Francisco, CA, United States")
    assert loc.city == "San Francisco"
    assert loc.region == "California"
    assert loc.country_code == "US"

    sal = parse_salary("$145k - $185k per year")
    assert sal.salary_min == Decimal("145000")
    assert sal.salary_max == Decimal("185000")
    assert sal.salary_currency == "USD"
    assert sal.salary_period == "YEAR"

    norm = normalize_job_record(
        external_job_id="req-101",
        title="Backend Systems Engineer",
        company_name="Acme Cloud Inc.",
        source_job_url=canonicalize_url("https://boards.greenhouse.io/acme/jobs/101?utm_source=linkedin") or "",
        application_url=canonicalize_url("https://boards.greenhouse.io/acme/jobs/101?utm_medium=cpc"),
        description_html_or_text="<p>Build distributed systems.</p><script>alert(1)</script>",
    )
    assert norm.salary_min is None
    assert norm.salary_max is None
    assert norm.salary_currency is None
    assert norm.location_raw is None
    assert norm.original_posted_at is None
    assert "alert(1)" not in norm.description_text
    assert "utm_source" not in norm.source_job_url


def test_deduplication_never_merges_by_title_alone():
    incoming = normalize_job_record(
        external_job_id="gh-555",
        title="Senior Software Engineer",
        company_name="Cloudflare",
        location_raw="Austin, TX, United States",
        source_job_url="https://boards.greenhouse.io/cloudflare/jobs/555",
        application_url="https://boards.greenhouse.io/cloudflare/jobs/555",
        description_html_or_text="<p>Build edge networking services in Rust and Go across global PoPs.</p>",
    )

    diff_company = CandidateJobSnapshot(
        job_id="job-diff-co",
        company_id="co-linear",
        normalized_company_name="linear",
        title="Senior Software Engineer",
        normalized_title="senior software engineer",
        location_raw="Austin, TX, United States",
        city="Austin",
        region="Texas",
        country_code="US",
        workplace_type="HYBRID",
        primary_source_url="https://jobs.ashbyhq.com/linear/999",
        primary_application_url="https://jobs.ashbyhq.com/linear/999",
        description_text="Build edge networking services in Rust and Go across global PoPs.",
        known_external_ids=["999"],
        known_application_urls=["https://jobs.ashbyhq.com/linear/999"],
    )

    diff_city = CandidateJobSnapshot(
        job_id="job-diff-city",
        company_id="co-cloudflare",
        normalized_company_name="cloudflare",
        title="Senior Software Engineer",
        normalized_title="senior software engineer",
        location_raw="Berlin, Germany",
        city="Berlin",
        region=None,
        country_code="DE",
        workplace_type="ON_SITE",
        primary_source_url="https://boards.greenhouse.io/cloudflare/jobs/777",
        primary_application_url="https://boards.greenhouse.io/cloudflare/jobs/777",
        description_text="Different Berlin team role.",
        known_external_ids=["777"],
        known_application_urls=["https://boards.greenhouse.io/cloudflare/jobs/777"],
    )

    res = evaluate_duplicate_candidate(incoming, [diff_company, diff_city])
    assert res.outcome == DeduplicationOutcome.DISTINCT

    same_job_syndicated = CandidateJobSnapshot(
        job_id="job-canonical-555",
        company_id="co-cloudflare",
        normalized_company_name="cloudflare",
        title="Senior Software Engineer",
        normalized_title="senior software engineer",
        location_raw="Austin, TX",
        city="Austin",
        region="Texas",
        country_code="US",
        workplace_type="HYBRID",
        primary_source_url="https://jobs.exitfive.com/jobs/cf-555",
        primary_application_url="https://job-boards.greenhouse.io/cloudflare/jobs/555",
        description_text="Build edge networking services in Rust and Go across global PoPs.",
        known_external_ids=["cf-555"],
        known_application_urls=["https://job-boards.greenhouse.io/cloudflare/jobs/555"],
    )
    merged = evaluate_duplicate_candidate(incoming, [same_job_syndicated])
    assert merged.outcome == DeduplicationOutcome.AUTO_MERGE
    assert merged.matched_job_id == "job-canonical-555"


def test_ssrf_blocks_private_and_loopback_targets():
    for bad in [
        "http://127.0.0.1:8000/admin",
        "http://localhost/jobs",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/careers",
        "file:///etc/passwd",
    ]:
        with pytest.raises(SSRFSafetyError):
            validate_public_url(bad, resolve_dns=False)

    clean = canonicalize_url("https://boards.greenhouse.io/cloudflare/?utm_source=twitter")
    assert clean == "https://boards.greenhouse.io/cloudflare"


def test_safe_closure_state_machine_unit():
    tr_err = evaluate_missing_job_transition(
        current_status="ACTIVE",
        previous_missing_runs=0,
        run_succeeded=False,
        is_complete_snapshot=False,
    )
    assert tr_err.new_status == "ACTIVE"
    assert tr_err.status_changed is False

    tr1 = evaluate_missing_job_transition(
        current_status="ACTIVE",
        previous_missing_runs=0,
        run_succeeded=True,
        is_complete_snapshot=True,
        closure_threshold=2,
    )
    assert tr1.new_status == "POSSIBLY_CLOSED"
    assert tr1.status_changed is True

    tr2 = evaluate_missing_job_transition(
        current_status="POSSIBLY_CLOSED",
        previous_missing_runs=1,
        run_succeeded=True,
        is_complete_snapshot=True,
        closure_threshold=2,
    )
    assert tr2.new_status == "CLOSED"
    assert tr2.status_changed is True

    updated_norm = normalize_job_record(
        external_job_id="1",
        title="Staff Engineer",
        company_name="Acme",
        source_job_url="https://example.com/1",
        description_html_or_text="Role description",
        salary_raw="$180,000 per year",
    )
    diffs = compute_field_diffs({"title": "Senior Engineer", "salary_min": 140000}, updated_norm)
    diff_names = {d.field_name for d in diffs}
    assert "title" in diff_names and "salary_min" in diff_names
