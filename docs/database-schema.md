# Jobre — Database Schema Reference

Jobre uses **PostgreSQL 17** managed via **SQLAlchemy 2.0 (async)** and **Alembic** (`apps/api/alembic/versions/0001_initial_schema.py`). Extensions enabled: `pg_trgm`, `unaccent`.

---

## Core Domain Tables (12 Tables)

### 1. `platforms`
Catalog of all **78 required platforms** (58 `ATS` + 20 `JOB_BOARD`).
- **Key Columns:** `id` (UUID PK), `name` (unique), `category` (`ATS` | `JOB_BOARD`), `connector_key` (unique), `implementation_status` (`NOT_IMPLEMENTED`, `IN_DEVELOPMENT`, `IMPLEMENTED`, `TESTED`, `VERIFIED`, `DEGRADED`, `DISABLED`), `discovery_method`, `extraction_method`, `auth_requirements`, `pagination_support`, `rate_limit_rpm`, `known_limitations`.

### 2. `companies`
Canonical employer entities.
- **Key Columns:** `id` (UUID PK), `name`, `normalized_name` (unique, indexed), `canonical_domain` (indexed), `website_url`, `description`.

### 3. `sources`
Registered employer career portals and independent job boards.
- **Key Columns:** `id` (UUID PK), `company_id` (FK → `companies`), `platform_id` (FK → `platforms`), `source_name`, `source_url` (unique), `board_token`, `canonical_domain`, `source_type`, `status` (`ACTIVE`, `DEGRADED`, `PAUSED`, `DISABLED`), `priority` (`HIGH`, `NORMAL`, `LOW`), `refresh_interval_minutes`, `discovery_method`, `discovery_confidence`, `source_config` (JSON), `sync_lock_until`, `consecutive_failures`, `last_checked_at`, `last_successful_sync_at`, `next_sync_at`.

### 4. `jobs`
Canonical normalized job opportunities.
- **Key Columns:** `id` (UUID PK), `canonical_job_key` (unique), `company_id` (FK → `companies`), `title`, `normalized_title`, `department`, `description` (sanitized HTML), `description_text` (plain text), `location_raw`, `city`, `region`, `country`, `country_code`, `salary_raw`, `salary_min` (`NUMERIC(14,2)`), `salary_max` (`NUMERIC(14,2)`), `salary_currency`, `salary_period`, `employment_type`, `employment_type_raw`, `workplace_type`, `workplace_type_raw`, `primary_source_url`, `primary_application_url`, `original_posted_at`, `first_seen_at`, `last_seen_at`, `last_checked_at`, `last_modified_at`, `closed_at`, `status` (`ACTIVE`, `POSSIBLY_CLOSED`, `CLOSED`, `EXPIRED`, `UNKNOWN`), `is_synthetic`, `content_hash`.
- **Search Indexes:**
  - `ix_jobs_fts_vector`: `GIN` functional index over `to_tsvector('english', coalesce(title,'') || ' ' || coalesce(department,'') || ' ' || coalesce(location_raw,'') || ' ' || coalesce(description_text,''))`
  - `ix_jobs_title_trgm`: `GIN (title gin_trgm_ops)`
  - Composite B-tree indexes on `(status, first_seen_at)`, `(company_id, status)`, `(country_code, workplace_type, status)`, and `(employment_type, status)`.

### 5. `source_jobs`
Many-to-many provenance join linking each `Source` posting to its canonical `Job`.
- **Unique Constraint:** `(source_id, external_job_id)`
- **Key Columns:** `job_id` (FK → `jobs`), `source_id` (FK → `sources`), `external_job_id`, `source_job_url`, `application_url`, `raw_payload_hash`, `match_score`, `match_reason`, `is_active_on_source`, `missing_runs_count`, `first_seen_at`, `last_seen_at`, `last_checked_at`.

### 6. `raw_job_records`
Immutable audit pointers to compressed raw job snapshots captured prior to normalization.
- **Key Columns:** `id`, `ingestion_run_id` (FK), `source_id` (FK), `external_job_id`, `payload_hash` (SHA-256), `storage_path` (`.json.gz`), `raw_preview` (JSON), `captured_at`.

### 7. `ingestion_runs`
Execution telemetry for every manual, scheduled, or verification sync.
- **Key Columns:** `id`, `source_id`, `connector_id`, `trigger_type`, `status` (`RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `SKIPPED`), `is_complete_snapshot`, `http_status`, `started_at`, `completed_at`, `duration_ms`, `jobs_discovered`, `jobs_processed`, `jobs_created`, `jobs_updated`, `jobs_deduplicated`, `jobs_missing`, `jobs_closed`, `raw_snapshot_Archive_path`, `error_summary`.

### 8. `job_changes`
Field-level diff and lifecycle transition log.
- **Key Columns:** `id`, `job_id`, `ingestion_run_id`, `change_type` (`FIELD_MODIFIED`, `STATUS_TRANSITION`, `REOPENED`, `UNMERGED`), `field_name`, `old_value`, `new_value`, `changed_fields` (JSON), `previous_hash`, `new_hash`, `detected_at`.

### 9. `duplicate_groups` & 10. `duplicate_candidates`
Cross-source deduplication audit and operator review queue (`AUTO_MERGED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `UNMERGED`).

### 11. `connector_health` & 12. `coverage_evidence`
Real-time per-platform health counters (`average_response_time_ms`, `failed_requests`, `consecutive_failures`) and immutable verification proofs (`verification_run_id`, `example_source_url`, `sample_job_title`, `raw_snapshot_path`).
