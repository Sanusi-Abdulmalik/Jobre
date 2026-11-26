# Jobre — Universal Job Discovery, Aggregation, Indexing & Monitoring Platform

> **One index. Every opportunity.**  
> Repository: `Sanusi-Abdulmalik/jobre`

Jobre is a production-oriented universal job discovery, ingestion, normalization, cross-source deduplication, lifecycle monitoring, and full-text search platform engineered to monitor 10,000+ career portals and independent job boards across **78 cataloged platforms** (**58 Applicant Tracking Systems** + **20 Job-Board Software Engines**).

---

## Live Verified Snapshot (November 14, 2026)

| Metric | Live Verified Value |
|---|---|
| **Required Platforms Cataloged** | **78** (58 ATS + 20 Job Boards) |
| **Live-Verified Connectors (`VERIFIED`)** | **22** (17 ATS + 5 Job Boards — verified against live public sources with retained raw snapshots) |
| **Cataloged Pending Connectors (`NOT_IMPLEMENTED`)** | **56** (explicitly tracked with auth/WAF/tenant constraints; never falsely marked verified) |
| **Active Monitored Sources** | **27** real employer ATS portals & independent job boards |
| **Real Normalized Jobs Indexed** | **428** (`ACTIVE`, zero synthetic listings in production DB) |
| **Real Cross-Platform Duplicate Merges** | **3** (`Niceboard` ↔ `BambooHR`, `Niceboard` ↔ `Ashby`, `Niceboard` ↔ `Greenhouse`) |

See [`docs/coverage-matrix.md`](docs/coverage-matrix.md) and [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for full run-level cryptographic verification evidence.

---

## Core Engineering Guarantees

1. **Strict Verification Integrity:** A platform transitions to `VERIFIED` **only** when its connector executes against a live supported public source, stores gzip-compressed raw payload snapshots (`data/raw_snapshots/`), normalizes valid job records into PostgreSQL, and writes a `coverage_evidence` audit row.
2. **Raw Payload Preservation:** Raw JSON/XML/RSS/HTML job payloads and SHA-256 hashes are persisted (`raw_job_records`) **before** normalization so normalization can always be replayed without re-scraping.
3. **Multi-Signal Cross-Source Deduplication:** Links identical openings syndicated across company ATS boards and external job boards using canonical application URLs, ATS requisition tokens (`greenhouse`, `ashby`, `lever`, `workday`, `bamboohr`, `smartrecruiters`, `pinpoint`, `gem`), employer similarity, normalized title, location compatibility, seniority/role conflict guards, and description Jaccard similarity. **Jobs are never merged by title similarity alone.** Supports manual review (`approve` / `reject`) and full `unmerge`.
4. **Safe Multi-Run Closure Policy:** Transient HTTP 5xx/429 errors, timeouts, maintenance redirects (e.g., Workday maintenance windows), or bounded pagination crawls (`is_complete=False`) **never** close active jobs or delete sources. Jobs transition `ACTIVE` → `POSSIBLY_CLOSED` → `CLOSED` only after consecutive verified complete snapshots omit them across all linked sources.
5. **Rebuildable Search Architecture:** PostgreSQL 17 is the single source of truth. Search runs through `SearchCoordinator` (`packages/search/engine.py`), supporting **OpenSearch 2.x** (`jobre_jobs_v1`) when provisioned and seamlessly operating over **PostgreSQL 17 `GIN` Full-Text Search + `pg_trgm`** when OpenSearch is absent or recovering, with one-command full index rebuild (`scripts/rebuild_search_index.py`).

---

## Monorepo Structure

```text
jobre/
├── apps/
│   ├── api/                 # FastAPI v1 REST API, SQLAlchemy 2.0 async ORM, Alembic migrations
│   ├── web/                 # Next.js 14 + React 18 + TypeScript + Tailwind CSS (Public + 9 Admin pages)
│   └── workers/             # Redis priority queue (HIGH/NORMAL/LOW + DLQ) & staggered scheduler
├── packages/
│   ├── common/              # Config, JSON logging, Prometheus metrics, SSRF guard, rate-limited HTTP, raw store
│   ├── connectors/          # BaseConnector, 78-platform catalog, registry, 17 ATS + 5 Job-Board connectors
│   ├── discovery/           # Multi-pass URL/redirect/HTML/link ATS & job-board discovery engine
│   ├── normalization/       # Employment/workplace enums, location & salary parsers, HTML sanitizer
│   ├── deduplication/       # Multi-signal cross-source scorer & conflict detector
│   ├── lifecycle/           # Field-level diff tracker & safe multi-run closure state machine
│   └── search/              # OpenSearch 2.x driver + PostgreSQL 17 FTS/trigram fallback & rebuilder
├── orchestration/dags/      # Apache Airflow DAGs (staggered refresh & nightly search reconciliation)
├── infrastructure/          # PostgreSQL init SQL, OpenSearch index mappings, Prometheus scrape config
├── scripts/                 # Operational CLIs (seed, discover, import, run_connector, verify_coverage, rebuild)
├── tests/                   # Unit, integration, queue/scheduler, security, and live E2E acceptance suite
└── docs/                    # Architecture, schema, API, connectors, coverage matrix, ops, security, cost
```

---

## Quick Start

### Option A: Local Native Stack (PostgreSQL 17 + Redis 7.4+ + FastAPI + Next.js)

```bash
# 1. Configure environment
cp .env.example .env

# 2. Apply database migrations
cd apps/api && alembic upgrade head && cd ../..

# 3. Seed all 78 platforms & execute live verification across 27 real sources
PYTHONPATH=.:apps/api python3 scripts/seed_platforms.py
PYTHONPATH=.:apps/api python3 scripts/verify_coverage.py

# 4. Start API server (port 8000), background worker, and web UI (port 3000)
PYTHONPATH=.:apps/api uvicorn app.main:app --host 0.0.0.0 --port 8000 &
PYTHONPATH=.:apps/api python3 -m apps.workers.main &
cd apps/web && npm install && npm run build && npm run start
```

### Option B: Full Container Stack (Docker Compose)

```bash
docker compose up --build -d
```

Starts PostgreSQL 17, Redis 7, OpenSearch 2.17, a one-shot Alembic migration job, the FastAPI API, the async worker (which also runs the staggered scheduler), Next.js, Prometheus, Grafana, and a MinIO service scaffold that is not yet connected to raw storage. The current raw snapshot implementation writes to the local shared volume; MinIO/S3 storage is not yet wired into the application.

---

## Running the Test Suite

Tests run against an isolated `jobre_test` database so production state in `jobre` is never touched:

```bash
PYTHONPATH=.:apps/api pytest -v
```

---

## Documentation Index

- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — Engineering progress ledger & verified milestones
- [`docs/coverage-matrix.md`](docs/coverage-matrix.md) — Auto-generated 78-platform evidence matrix
- [`docs/architecture.md`](docs/architecture.md) — Modular monolith & data pipeline architecture
- [`docs/database-schema.md`](docs/database-schema.md) — 12-table PostgreSQL 17 relational schema & indexes
- [`docs/api.md`](docs/api.md) — Public & authenticated `/api/v1` REST API reference
- [`docs/connectors.md`](docs/connectors.md) — Connector SDK, lifecycle states, and platform notes
- [`docs/deployment.md`](docs/deployment.md) — Local, Docker Compose, and cloud production deployment
- [`docs/operations.md`](docs/operations.md) — Scheduling, monitoring, DLQ recovery, and runbooks
- [`docs/security.md`](docs/security.md) — Admin authentication, SSRF defense, rate limiting, compliance
- [`docs/testing.md`](docs/testing.md) — 14 acceptance test scenarios & verification methodology
- [`docs/cost-estimation.md`](docs/cost-estimation.md) — Infrastructure sizing & monthly cost model at 10k+ sources
