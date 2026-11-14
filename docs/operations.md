# Jobre — Operations & SRE Runbook

## 1. Scheduling & Refresh Cadence

Jobre assigns refresh intervals by source priority (`apps/workers/scheduler/refresh_scheduler.py`):
- **`HIGH` Priority:** Every `120` minutes (high-velocity employers & flagship boards)
- **`NORMAL` Priority:** Every `360` minutes (6 hours)
- **`LOW` Priority:** Every `720` minutes (12 hours)

Deterministic per-source jitter spreads due refreshes evenly across time windows to avoid synchronized request spikes. Apache Airflow DAGs (`orchestration/dags/jobre_ingestion_dag.py`) provide enterprise orchestration for staggered scheduling (`jobre_staggered_source_refresh`) and nightly index reconciliation (`jobre_search_index_reconciliation`).

---

## 2. Common Operational Playbooks

### A. Inspecting or Replaying a Failed Source Run
1. Query failed runs:
   ```bash
   curl -H "X-Admin-Key: $JOBRE_ADMIN_API_KEY" "http://127.0.0.1:8000/api/v1/admin/runs?status=FAILED"
   ```
2. Verify that **zero** active jobs were closed during the failed run (`jobs_closed == 0`).
3. Probe the upstream connector directly:
   ```bash
   PYTHONPATH=.:apps/api python3 scripts/run_connector.py <source_id_or_key> --max-jobs 10
   ```

### B. Draining / Inspecting the Dead-Letter Queue (DLQ)
Tasks that fail all worker retry attempts are pushed to `jobre:queue:dlq` with error context and timestamp:
```bash
redis-cli LRANGE jobre:queue:dlq 0 20
```

### C. Rebuilding the Search Projection from PostgreSQL
If OpenSearch is upgraded, wiped, or newly enabled:
```bash
PYTHONPATH=.:apps/api python3 scripts/rebuild_search_index.py
# Or via Admin API:
curl -X POST -H "X-Admin-Key: $JOBRE_ADMIN_API_KEY" http://127.0.0.1:8000/api/v1/admin/search/rebuild
```

### D. Resolving False-Positive or Pending Cross-Source Duplicates
Operators review candidate pairs in `/admin/duplicates` and can:
- Approve a `PENDING_REVIEW` candidate (`POST /api/v1/admin/duplicates/{id}/approve`)
- Reject a candidate (`POST /api/v1/admin/duplicates/{id}/reject`)
- **Unmerge** an `AUTO_MERGED` or `APPROVED` group (`POST /api/v1/admin/duplicates/{id}/unmerge`), which splits secondary `source_jobs` back into standalone canonical `jobs` and logs an `UNMERGED` `JobChange` audit entry.
