"""
Apache Airflow DAGs for Jobre batch scheduling, search reconciliation, and stale-lock recovery.
Deploy into an Airflow 2.9+ environment with JOBRE_API_URL and JOBRE_ADMIN_API_KEY configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:  # Allows importing/linting without full Airflow runtime installed locally
    DAG = None  # type: ignore
    PythonOperator = None  # type: ignore

import httpx


def _trigger_admin_endpoint(path: str) -> dict:
    base_url = os.environ.get("JOBRE_API_URL", "http://api:8000")
    api_key = os.environ.get("JOBRE_ADMIN_API_KEY", "")
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{base_url}/api/v1{path}",
            headers={"X-Admin-Key": api_key},
        )
        resp.raise_for_status()
        return resp.json()


if DAG is not None:
    default_args = {
        "owner": "jobre-platform",
        "depends_on_past": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    with DAG(
        dag_id="jobre_staggered_source_refresh",
        default_args=default_args,
        description="Enqueue staggered source refreshes across priority tiers",
        schedule="*/15 * * * *",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["jobre", "ingestion"],
    ) as ingestion_dag:
        PythonOperator(
            task_id="enqueue_due_sources",
            python_callable=lambda: _trigger_admin_endpoint("/admin/scheduler/tick"),
        )

    with DAG(
        dag_id="jobre_search_index_reconciliation",
        default_args=default_args,
        description="Nightly reconciliation of derived OpenSearch index from PostgreSQL source of truth",
        schedule="0 3 * * *",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["jobre", "search", "reconciliation"],
    ) as reconciliation_dag:
        PythonOperator(
            task_id="rebuild_search_projection",
            python_callable=lambda: _trigger_admin_endpoint("/admin/search/rebuild"),
        )
