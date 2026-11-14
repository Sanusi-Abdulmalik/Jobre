# Jobre — REST API Reference (`/api/v1`)

Interactive OpenAPI 3.1 documentation is served automatically at `/docs` (Swagger UI) and `/openapi.json`.

---

## 1. Public Endpoints (Unauthenticated, Rate-Limited)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Component health for PostgreSQL, Redis queues, Search backend, and Raw Storage |
| `GET` | `/api/v1/stats` | Real-time index counts, platform breakdown, workplace distribution, and sync status |
| `GET` | `/api/v1/jobs/search` | Full-text + faceted search (`q`, `location`, `company`, `platform`, `workplace_type`, `employment_type`, `country_code`, `salary_min`, `posted_within_days`, `status`, `sort_by`, `page`, `page_size`) |
| `GET` | `/api/v1/jobs` | Paginated canonical job listing |
| `GET` | `/api/v1/jobs/{job_id}` | Full canonical job record with normalized compensation, description, provenance, and change history |
| `GET` | `/api/v1/jobs/{job_id}/sources` | All `source_jobs` provenance entries where the vacancy was observed |
| `GET` | `/api/v1/companies` | Paginated employer directory (`q`, `page`, `page_size`) |
| `GET` | `/api/v1/companies/{company_id}` | Employer profile, registered career sources, and indexed openings |
| `GET` | `/api/v1/sources` | Paginated public source directory (`platform_key`, `status`) |
| `GET` | `/api/v1/sources/{source_id}` | Source metadata and recent ingestion run history |
| `GET` | `/api/v1/platforms` | Catalog of all 78 tracked ATS and job-board platforms |
| `GET` | `/api/v1/platforms/coverage` | Complete 78-platform coverage report with verification evidence |
| `GET` | `/api/v1/platforms/coverage/export` | Export coverage matrix as CSV (`?format=csv`) or JSON (`?format=json`) |

---

## 2. Administrative Endpoints (Authenticated)

All `/api/v1/admin/*` routes require either:
- Header: `X-Admin-Key: <JOBRE_ADMIN_API_KEY>`
- Header: `Authorization: Bearer <JOBRE_ADMIN_API_KEY>`

Missing or invalid credentials return `401 Unauthorized` via constant-time `secrets.compare_digest` verification.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/auth/verify` | Validate admin credentials |
| `POST` | `/api/v1/admin/sources/discover` | Inspect a candidate URL for ATS/job-board platform & confidence score |
| `POST` | `/api/v1/admin/sources` | Register a source idempotently (optional `run_immediately: true`) |
| `POST` | `/api/v1/admin/sources/bulk` | Bulk register multiple URLs or structured source definitions |
| `POST` | `/api/v1/admin/sources/{source_id}/refresh` | Trigger immediate synchronous run or enqueue to Redis worker |
| `GET` | `/api/v1/admin/runs` | Paginated ingestion run ledger (`status`, `connector_id`, `source_id`) |
| `GET` | `/api/v1/admin/runs/{run_id}` | Detailed run diagnostics + raw gzip snapshot SHA-256 records |
| `GET` | `/api/v1/admin/connectors` | All 78 connectors with code registration & live health telemetry |
| `POST` | `/api/v1/admin/connectors/{connector_id}/test` | Execute a live non-destructive probe against a target URL |
| `GET` | `/api/v1/admin/coverage` | Operator coverage matrix |
| `GET` | `/api/v1/admin/duplicates` | Cross-source duplicate groups & candidate signal breakdowns |
| `POST` | `/api/v1/admin/duplicates/{group_id}/approve` | Approve a pending duplicate merge |
| `POST` | `/api/v1/admin/duplicates/{group_id}/reject` | Reject a candidate merge |
| `POST` | `/api/v1/admin/duplicates/{group_id}/unmerge` | Split merged `source_jobs` back into standalone canonical `Job` rows |
| `GET` | `/api/v1/admin/changes` | Audit log of field modifications and status transitions |
| `POST` | `/api/v1/admin/search/rebuild` | Reindex all canonical PostgreSQL jobs into the search projection |
| `POST` | `/api/v1/admin/scheduler/tick` | Enqueue all due active sources into Redis priority queues |
