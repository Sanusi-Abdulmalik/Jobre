# Jobre — Deployment Guide

## 1. Environment Variables (`.env`)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL 17 DSN | `postgresql+psycopg://jobre@127.0.0.1:5432/jobre` |
| `REDIS_URL` | Redis connection URL for worker priority queues | `redis://127.0.0.1:6379/0` |
| `OPENSEARCH_ENABLED` | Enable OpenSearch 2.x dual-write & search driver | `false` (`true` in Docker Compose) |
| `OPENSEARCH_URL` | OpenSearch cluster endpoint | `http://127.0.0.1:9200` |
| `RAW_STORAGE_BACKEND` | Currently supported: `local` (gzip filesystem). S3/MinIO configuration is reserved but not implemented. | `local` |
| `RAW_STORAGE_PATH` | Directory for `.json.gz` raw connector snapshots | `./data/raw_snapshots` |
| `JOBRE_ADMIN_API_KEY` | Secret key protecting all `/api/v1/admin/*` endpoints | *(Must be rotated in production)* |
| `INTERNAL_API_URL` | FastAPI origin baked into the Next.js rewrite configuration at build time | `http://127.0.0.1:8000`

---

## 2. Full Container Stack (`docker-compose.yml`)

```bash
cp .env.example .env
# Edit JOBRE_ADMIN_API_KEY and database credentials in .env
docker compose up --build -d
```

Services provisioned:
- `postgres`: PostgreSQL 17 with `pg_trgm` and `unaccent` initialized via `infrastructure/postgres/init.sql`
- `redis`: Redis 7 with AOF persistence
- `opensearch`: OpenSearch 2.17 single-node (`jobre_jobs_v1` mapping in `infrastructure/opensearch/mappings.json`)
- `migrate`: one-shot Alembic migration before the API and worker start
- `minio`: S3-compatible service scaffold (started by Compose but not currently used by the local-only raw snapshot store)
- `api`: FastAPI (`uvicorn app.main:app --host 0.0.0.0 --port 8000`)
- `worker`: Async ingestion worker (`python -m apps.workers.main`)
- `web`: Next.js 14 production server (`0.0.0.0:3000`); its `INTERNAL_API_URL` must be supplied as a build argument because rewrites are generated during `next build`
- `prometheus`: Scrapes `/metrics` from `api` (`infrastructure/monitoring/prometheus.yml`)

---

## 3. Production Cloud Topology

- **Compute:** 2× stateless `api` + `web` containers behind an HTTPS load balancer (ALB / Cloudflare / Caddy), plus 2–4 horizontally scaled `worker` containers consuming Redis queues.
- **Database:** Managed PostgreSQL 17 (RDS / Cloud SQL / Neon) with daily PITR backups and connection pooling.
- **Object Storage (future integration):** AWS S3 / Cloudflare R2 lifecycle policies can be added after a remote object-store adapter is implemented; the current application writes snapshots to local filesystem storage.
