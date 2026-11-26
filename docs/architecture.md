# Jobre — System Architecture

## 1. Architectural Philosophy

Jobre follows a **Modular Monolith + Async Worker** architecture designed for high throughput, operational simplicity, and strict data provenance. PostgreSQL provides the durable system of record; the current Redis list consumer is best-effort and does not yet provide crash-safe task delivery:

1. **PostgreSQL 17 is the Canonical System of Record.** Every platform, company, source, raw payload pointer, normalized job, source-to-job provenance link, duplicate group, field diff, ingestion run, connector health state, and verification evidence record is stored transactionally in PostgreSQL.
2. **Derived & Rebuildable Search Index.** Search is served via `SearchCoordinator` (`packages/search/engine.py`), which writes to **OpenSearch 2.x** when enabled and seamlessly falls back to **PostgreSQL 17 Full-Text Search (`tsvector` + `GIN`) and `pg_trgm`** if OpenSearch is disabled or temporarily unreachable. A complete search index can be reconstructed from PostgreSQL at any time (`POST /api/v1/admin/search/rebuild` or `scripts/rebuild_search_index.py`).
3. **Raw-First Ingestion.** Connectors never mutate canonical jobs directly. Every run writes compressed raw snapshots (`gzip` JSON in the local filesystem store) and `raw_job_records` SHA-256 digests **before** normalization runs. S3/MinIO settings and the Compose service are scaffolding only; remote object storage is not implemented yet.

---

## 2. End-to-End Data Flow

```text
[Candidate URL / Seed List]
         │
         ▼
┌─────────────────────────┐
│ Source Discovery Engine │  1. SSRF & scheme validation (validate_public_url)
│ (packages/discovery)    │  2. URL regex & redirect chain inspection
└───────────┬─────────────┘  3. HTML signature & embedded ATS link detection
            │
            ▼
┌─────────────────────────┐
│ Staggered Scheduler &   │  - Priority tiers: HIGH (2h), NORMAL (6h), LOW (12h)
│ Redis Priority Queue    │  - Deterministic jitter prevents thundering herds
│ (apps/workers)          │  - Per-source DB lease lock (sync_lock_until)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Connector Engine        │  - Per-host token-bucket rate limiter
│ (packages/connectors)   │  - Retry w/ exponential backoff on 429/5xx/timeouts
│ 17 ATS + 5 Job Boards   │  - Maintenance redirect interception (e.g. Workday)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Raw Snapshot Store      │  - Gzip-compressed payloads + SHA-256 hash
│ + Normalization Engine  │  - Canonical enums, parsed location & salary,
└───────────┬─────────────┘    Bleach-sanitized HTML, strict null preservation
            │
            ▼
┌─────────────────────────┐
│ Cross-Source Dedup &    │  - Exact deep URL & ATS requisition token matching
│ Safe Lifecycle Engine   │  - Weighted multi-signal scoring + conflict guards
└───────────┬─────────────┘  - Field-level diffs (job_changes) & multi-run closure
            │
            ▼
┌─────────────────────────────────────────────────────┐
│ PostgreSQL 17 (Truth)  ───►  OpenSearch / PG17 FTS  │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
        FastAPI (/api/v1) ◄───► Next.js 14 Web & Admin UI
```

---

## 3. Why Not Kafka, Kubernetes, or Headless Browsers by Default?

- **Redis Priority Lists vs. Kafka:** Redis `BLPOP` queues (`HIGH`/`NORMAL`/`LOW` + `DLQ`) provide simple priority dispatch. However, `BLPOP` removes a task before processing, so a worker crash can lose that task; the current implementation is not crash-safe until acknowledgement and pending-task recovery are added. Source lease acquisition also needs an atomic database update before concurrent worker scaling can be considered safe.
- **Public Structured Feeds vs. Playwright:** All 22 verified connectors extract structured JSON, XML, RSS, or server-rendered JSON-LD over lightweight async HTTP (`httpx`), achieving 300ms–3s run times per source without headless Chromium memory spikes or anti-bot evasion.
