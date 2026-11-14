# Jobre — Deployment Guide

## 1. Environment Variables (`.env`)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL 17 DSN | `postgresql+asyncpg://jobre@127.0.0.1:5432/jobre` |
| `REDIS_URL` | Redis connection URL for worker priority queues | `redis://127.0.0.1:6379/0` |
| `OPENSEARCH_ENABLED` | Enable OpenSearch 2.x dual-write & search driver | `false` (`true` in Docker Compose) |
| `OPENSEARCH_URL` | OpenSearch cluster endpoint | `http://127.0.0.1:9200` |
| `JOBRE_RAW_STORAGE_BACKEND` | `local` (gzip filesystem) or `s3` (MinIO/AWS S3) | `local` |
| `JOBRE_RAW_STORAGE_PATH` | Directory for `.json.gz` raw connector snapshots | `/home/user/jobre/data/raw_snapshots` |
| `JOBRE_ADMIN_API_KEY` | Secret key protecting all `/api/v1/admin/*` endpoints | *(Must be rotated in production)* |
| `INTERNAL_API_URL` | Upstream FastAPI URL used by Next.js `/api/v1/*` rewrites | `http://127.0.0.1:8000` |

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
- `minio`: S3-compatible object storage for raw snapshots
- `api`: FastAPI (`uvicorn app.main:app --host 0.0.0.0 --port 8000`)
- `worker`: Async ingestion worker (`python -m apps.workers.main`)
- `web`: Next.js 14 standalone production server (`0.0.0.0:3000`)
- `prometheus`: Scrapes `/metrics` from `api` (`infrastructure/monitoring/prometheus.yml`)

---

## 3. Production Cloud Topology

- **Compute:** 2× stateless `api` + `web` containers behind an HTTPS load balancer (ALB / Cloudflare / Caddy), plus 2–4 horizontally scaled `worker` containers consuming Redis queues.
- **Database:** Managed PostgreSQL 17 (RDS / Cloud SQL / Neon) with daily PITR backups and connection pooling.
- **Object Storage:** AWS S3 / Cloudflare R2 lifecycle policy transitioning raw `.json.gz` snapshots > 90 days to Glacier/Infrequent Access.
