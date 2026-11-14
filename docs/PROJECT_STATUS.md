# Jobre — Project Status Ledger

**Last Updated:** `2026-11-14T15:25:00Z`  
**Overall Phase:** Production MVP Complete, Live-Verified & Running

---

## 1. Milestone Checklist

| Workstream | Status | Verification Evidence |
|---|---|---|
| **Monorepo, Config, Docker Compose & CI** | **COMPLETED** | `pyproject.toml`, `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml` |
| **PostgreSQL 17 Schema & Alembic Migrations** | **COMPLETED** | `0001_initial_schema` applied to `jobre` and `jobre_test` (12 domain tables + `GIN` FTS & `pg_trgm` indexes) |
| **78-Platform Catalog (58 ATS + 20 Job Boards)** | **COMPLETED** | `packages/connectors/catalog.py` seeded into `platforms` table (78 rows verified) |
| **Source Discovery & SSRF Guard** | **COMPLETED** | `packages/discovery/engine.py` + `packages/common/security.py` (blocks loopback, RFC1918, link-local, metadata IPs, non-HTTP schemes) |
| **Connector Engine (17 ATS + 5 Job Boards)** | **VERIFIED** | **22/22 implemented connectors verified live** (`428` normalized jobs across `27` live sources; gzip raw snapshots stored in `data/raw_snapshots/`) |
| **Normalization, Deduplication & Safe Lifecycle** | **VERIFIED** | 3 real cross-platform duplicate groups (`Niceboard` ↔ `BambooHR`/`Ashby`/`Greenhouse`) auto-linked; HTTP failure & multi-run closure verified |
| **Redis Priority Worker, Scheduler & Airflow DAGs** | **COMPLETED** | `apps/workers/` running live (`HIGH`/`NORMAL`/`LOW` + `DLQ`); Airflow DAGs in `orchestration/dags/jobre_ingestion_dag.py` |
| **Search Coordinator (OpenSearch + PG17 FTS)** | **VERIFIED** | Faceted full-text & trigram search + one-click rebuild verified |
| **FastAPI `/api/v1` Public + Admin API** | **RUNNING** | Live on `0.0.0.0:8000` (`/docs`, `/openapi.json`, `/metrics`, constant-time `X-Admin-Key` / `Bearer` auth) |
| **Next.js 14 Web UI (5 Public + 9 Admin Pages)** | **RUNNING** | Production build (`tsc --noEmit` + `next build` zero errors) live on `0.0.0.0:3000` proxying `/api/v1/*` |
| **Automated Test Suite (Unit + Integration + E2E)** | **PASSED** | `9 passed in 2.42s` against isolated `jobre_test` covering all 14 acceptance requirements |
| **Complete Documentation Suite (`docs/*.md`)** | **COMPLETED** | All 11 technical documents + `README.md` completed |

---

## 2. Live Connector Verification Summary

- **17 Live-Verified ATS Connectors (`VERIFIED`):**
  `ashby`, `bamboohr`, `breezy_hr`, `gem`, `greenhouse`, `jazzhr`, `lever`, `manatal`, `personio`, `pinpoint`, `polymer`, `recruitee`, `smartrecruiters`, `teamtailor`, `trakstar`, `workable`, `workday`.
- **5 Live-Verified Job-Board Connectors (`VERIFIED`):**
  `jobboard_io`, `jobboardly`, `niceboard`, `smartjobboard`, `wp_job_manager`.
- **56 Cataloged Pending Platforms (`NOT_IMPLEMENTED`):**
  Explicitly tracked in `platforms` with documented discovery patterns, expected extraction strategy, and real-world operational constraints (e.g., tenant-authenticated APIs, WAF/Cloudflare anti-bot challenges on Eightfold/Rippling/Wiley Madgex, or enterprise SSO portals). None are falsely marked `IMPLEMENTED` or `VERIFIED`.

---

## 3. Architectural Trade-offs & Operational Notes

- **Modular Monolith First:** Core domain logic lives in clean, framework-independent Python packages (`packages/*`) shared by FastAPI (`apps/api`) and async workers (`apps/workers`), avoiding premature microservice, Kafka, or Kubernetes overhead.
- **Dual-Backend Search Resilience:** In single-node or memory-constrained environments (< 2 GiB RAM), OpenSearch's JVM heap (~1 GiB+) is optional; `SearchCoordinator` automatically serves full-text ranked queries, trigram fuzzy matching, and facets from PostgreSQL 17 `GIN` indexes while immediately utilizing OpenSearch whenever `OPENSEARCH_ENABLED=true`.
