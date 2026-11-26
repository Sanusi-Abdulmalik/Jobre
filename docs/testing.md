# Jobre — Testing & Verification Guide

## 1. Isolated Test Environment

All automated tests run against a dedicated PostgreSQL 17 database (`jobre_test`) and isolated snapshot directory (`tests/conftest.py`), ensuring that test runs **never** pollute production statistics or job records in `jobre`.

Run the entire suite:
```bash
PYTHONPATH=.:apps/api pytest -v
```

---

## 2. Mapping to the 14 Acceptance Requirements

The table below maps 14 acceptance requirements to the current automated checks. These are requirements/scenarios, not 14 separate pytest functions; the current archive contains 9 test functions across the four test modules.

| # | Acceptance Requirement | Test Module & Function | Verified Outcome |
|---:|---|---|---|
| **1** | **Source Discovery** | `tests/e2e/test_acceptance_suite.py` (`test_coverage_matrix_integrity_and_e2e_live_ats_and_jobboard_flow`) | Detects platform, board token, confidence >= 0.90, and prevents duplicate source registration |
| **2** | **Live ATS Ingestion** | `tests/e2e/test_acceptance_suite.py` + `scripts/verify_coverage.py` | Live extraction across 17 ATS platforms with gzip raw snapshots + normalized PostgreSQL jobs |
| **3** | **Live Job Board Ingestion** | `tests/e2e/test_acceptance_suite.py` + `scripts/verify_coverage.py` | Live extraction across 5 Job-Board platforms (`Niceboard`, `WP Job Manager`, `JobBoard.io`, `SmartJobBoard`, `Jobboardly`) |
| **4** | **Normalization Accuracy** | `tests/unit/test_core_engines.py::test_normalization_accuracy_and_null_preservation` | Employment/workplace enums, US/global location parsing, salary parsing, XSS stripping, and strict `None` preservation |
| **5** | **Deduplication & Unmerge** | `tests/unit/test_core_engines.py::test_deduplication_never_merges_by_title_alone` & `tests/integration/test_pipeline_and_lifecycle.py` | Multi-signal cross-source merge, title-only/city-conflict non-merge, and full `unmerge_duplicate_group` |
| **6** | **Change Detection** | `tests/integration/test_pipeline_and_lifecycle.py` | Detects updated title/salary/content hash and writes `FIELD_MODIFIED` `JobChange` diffs |
| **7** | **Safe Closure Detection** | `tests/unit/test_core_engines.py::test_safe_closure_state_machine_unit` & `tests/integration/test_pipeline_and_lifecycle.py` | `ACTIVE` → `POSSIBLY_CLOSED` (miss 1) → `CLOSED` (miss 2) with `STATUS_TRANSITION` audit log |
| **8** | **Failure Safety** | `tests/integration/test_pipeline_and_lifecycle.py` | Simulated HTTP 500 marks run `FAILED`, increments `consecutive_failures`, keeps source intact, and closes **0** jobs |
| **9** | **Search Functionality** | `tests/integration/test_pipeline_and_lifecycle.py` & `tests/e2e/test_acceptance_suite.py` | Keyword, workplace, salary floor, facets, sorting, and pagination verified |
| **10** | **Index Recovery** | `tests/integration/test_pipeline_and_lifecycle.py` | `SearchCoordinator.rebuild_index` reconstructs search documents from PostgreSQL |
| **11** | **API Contract** | `tests/e2e/test_acceptance_suite.py` | OpenAPI `/openapi.json` + `/jobs/search`, `/jobs/{id}`, `/jobs/{id}/sources`, `/platforms/coverage/export` |
| **12** | **Admin Security & SSRF** | `tests/e2e/test_acceptance_suite.py::test_admin_security_and_ssrf_protection` & `test_ssrf_blocks_private_and_loopback_targets` | `401` on all unauthenticated `/admin/*` routes; `400` on `127.0.0.1`/private/metadata SSRF URLs |
| **13** | **Coverage Matrix Integrity** | `tests/unit/test_core_engines.py::test_catalog_has_all_78_required_platforms` & `tests/e2e/test_acceptance_suite.py` | 58 ATS + 20 Job Boards = 78 platforms; `0` `VERIFIED` before live runs; transitions only after verified live extraction |
| **14** | **End-to-End Flow** | `tests/e2e/test_acceptance_suite.py` + Live Next.js (`:3000`) & FastAPI (`:8000`) | Full Discover → Ingest → Normalize → Deduplicate → Search →Provenance → Coverage flow |
