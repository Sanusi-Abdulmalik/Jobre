# Jobre — Connector Engine & Developer Guide

## 1. The `BaseConnector` Contract

Every connector in `packages/connectors/` inherits from `BaseConnector` (`packages/connectors/base.py`) and implements four methods:

1. `async def discover(self, source_url: str) -> DiscoveryProbeResult`
   - Detects whether `source_url` belongs to this platform, extracts any `board_token` (e.g., `cloudflare` for Greenhouse, `salesforce|wd12|External_Career_Site` for Workday), and returns a `confidence` score (`0.0–1.0`) plus human-readable `evidence`.
2. `async def fetch_jobs(self, source: ConnectorSourceConfig, cursor: str | None = None) -> FetchBatchResult`
   - Fetches one page or complete feed using `self.http` (`JobreHttpClient`), returning `RawJobPayload` items, `next_cursor`, `http_status`, and **`is_complete`** (`False` whenever `max_jobs` truncates pagination so safe closure detection never closes uncrawled listings).
3. `def normalize(self, raw_job: dict[str, Any], source: ConnectorSourceConfig) -> NormalizedJobInput`
   - Maps raw platform fields into `normalize_job_record(...)`, preserving original raw strings alongside canonical enums and leaving absent fields strictly `None`.
4. `async def health_check(self, source: ConnectorSourceConfig | None = None) -> ConnectorHealthResult`
   - Executes a lightweight public readiness probe.

---

## 2. Explicit Connector Lifecycle States

- `NOT_IMPLEMENTED`: Platform is cataloged in `PLATFORM_CATALOG` with URL/HTML signatures and documented constraints, but no active extractor class is registered yet.
- `IN_DEVELOPMENT` / `IMPLEMENTED` / `TESTED`: Connector code exists in `CONNECTOR_CLASSES` (`packages/connectors/registry.py`).
- `VERIFIED`: Transitioned **automatically in PostgreSQL** only after a live ingestion run succeeds with `jobs_discovered > 0`, persists gzip raw snapshots, creates normalized `jobs`, and records a `coverage_evidence` row.
- `DEGRADED` / `DISABLED`: Automatic or operator-controlled state when consecutive upstream errors occur.

---

## 3. Adding a New Connector (Step-by-Step)

1. Create `packages/connectors/ats/<key>.py` or `packages/connectors/jobboards/<key>.py` subclassing `BaseConnector`.
2. Register `<key>: MyConnector` in `CONNECTOR_CLASSES` inside `packages/connectors/registry.py`.
3. Update `initial_status="IMPLEMENTED"` on the matching `PlatformSpec` in `packages/connectors/catalog.py`.
4. Add at least one real public source to `data/seed/verified_sources.json` and run:
   ```bash
   PYTHONPATH=.:apps/api python3 scripts/import_sources.py
   PYTHONPATH=.:apps/api python3 scripts/run_connector.py <key>
   ```
5. Verify normalized jobs, raw `.json.gz` snapshots, and `VERIFIED` state in `/api/v1/platforms/coverage`.
