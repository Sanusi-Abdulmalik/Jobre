from __future__ import annotations

from prometheus_client import Counter, Histogram

INGESTION_RUNS_TOTAL = Counter(
    "jobre_ingestion_runs_total",
    "Total number of source ingestion runs executed",
    ["connector", "status"],
)

JOBS_PROCESSED_TOTAL = Counter(
    "jobre_jobs_processed_total",
    "Total job records processed during ingestion",
    ["connector", "outcome"],
)

CONNECTOR_HTTP_REQUESTS_TOTAL = Counter(
    "jobre_connector_http_requests_total",
    "Total outbound HTTP requests made by connectors",
    ["domain", "status_code"],
)

CONNECTOR_LATENCY_SECONDS = Histogram(
    "jobre_connector_request_latency_seconds",
    "Latency of outbound connector HTTP requests in seconds",
    ["domain"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0),
)

SEARCH_LATENCY_SECONDS = Histogram(
    "jobre_search_latency_seconds",
    "Latency of job search queries in seconds",
    ["backend"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

DEDUP_DECISIONS_TOTAL = Counter(
    "jobre_dedup_decisions_total",
    "Deduplication outcomes across ingested listings",
    ["decision"],
)
