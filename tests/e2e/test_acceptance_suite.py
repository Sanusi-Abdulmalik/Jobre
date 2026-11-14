from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_admin_security_and_ssrf_protection(api_client):
    # Acceptance Test 12: Admin Security & SSRF
    unauth_endpoints = [
        ("GET", "/api/v1/admin/auth/verify"),
        ("GET", "/api/v1/admin/runs"),
        ("GET", "/api/v1/admin/connectors"),
        ("GET", "/api/v1/admin/coverage"),
        ("GET", "/api/v1/admin/duplicates"),
        ("GET", "/api/v1/admin/changes"),
        ("POST", "/api/v1/admin/sources"),
        ("POST", "/api/v1/admin/search/rebuild"),
    ]
    for method, path in unauth_endpoints:
        r = await api_client.request(method, path)
        assert r.status_code == 401, f"Expected 401 on {method} {path}, got {r.status_code}"

    # Wrong key rejected
    r_bad = await api_client.get(
        "/api/v1/admin/auth/verify", headers={"X-Admin-Key": "wrong-key"}
    )
    assert r_bad.status_code == 401

    # Valid X-Admin-Key and Bearer token accepted
    headers = {"X-Admin-Key": "test-admin-secret-key"}
    r_ok = await api_client.get("/api/v1/admin/auth/verify", headers=headers)
    assert r_ok.status_code == 200
    assert r_ok.json()["authenticated"] is True

    r_bearer = await api_client.get(
        "/api/v1/admin/auth/verify",
        headers={"Authorization": "Bearer test-admin-secret-key"},
    )
    assert r_bearer.status_code == 200

    # SSRF blocked on admin discovery & source creation
    r_ssrf = await api_client.post(
        "/api/v1/admin/sources/discover",
        headers=headers,
        json={"url": "http://127.0.0.1:5432/internal"},
    )
    assert r_ssrf.status_code == 400


@pytest.mark.asyncio
async def test_coverage_matrix_integrity_and_e2e_live_ats_and_jobboard_flow(api_client):
    # Acceptance Tests 1, 2, 3, 11, 13, 14 (Real Live End-to-End Flow!)
    headers = {"X-Admin-Key": "test-admin-secret-key"}

    # Before running any live source in clean test DB: ZERO platforms may claim VERIFIED!
    cov_initial = (await api_client.get("/api/v1/platforms/coverage")).json()
    assert cov_initial["total_required_platforms"] == 78
    assert cov_initial["status_summary"].get("VERIFIED", 0) == 0

    # OpenAPI schema check (Test 11)
    openapi = await api_client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/api/v1/jobs/search" in openapi.json()["paths"]

    # Step 1 (Test 1): Discover live Ashby URL & live Niceboard URL
    disc_ashby = await api_client.post(
        "/api/v1/admin/sources/discover",
        headers=headers,
        json={"url": "https://jobs.ashbyhq.com/tldr.tech"},
    )
    assert disc_ashby.status_code == 200
    assert disc_ashby.json()["platform_key"] == "ashby"
    assert disc_ashby.json()["confidence"] >= 0.9

    # Step 2 (Test 2 — Live ATS Ingestion): Register & immediately ingest live Ashby board
    create_ats = await api_client.post(
        "/api/v1/admin/sources",
        headers=headers,
        json={
            "source_url": "https://jobs.ashbyhq.com/tldr.tech",
            "company_name": "TLDR",
            "run_immediately": True,
            "max_jobs": 5,
        },
    )
    assert create_ats.status_code == 200
    ats_body = create_ats.json()
    assert ats_body["initial_run"]["status"] == "SUCCEEDED"
    assert ats_body["initial_run"]["jobs_discovered"] >= 1

    # Step 3 (Test 3 — Live Job Board Ingestion): Register & ingest live Niceboard job board
    create_jb = await api_client.post(
        "/api/v1/admin/sources",
        headers=headers,
        json={
            "source_url": "https://jobs.exitfive.com",
            "company_name": "Exit Five",
            "platform_key": "niceboard",
            "run_immediately": True,
            "max_jobs": 8,
        },
    )
    assert create_jb.status_code == 200
    assert create_jb.json()["initial_run"]["status"] == "SUCCEEDED"
    assert create_jb.json()["initial_run"]["jobs_discovered"] >= 1

    # Step 4 (Tests 9, 11, 14): Search & inspect via Public REST API
    search_res = await api_client.get("/api/v1/jobs/search?page=1&page_size=10")
    assert search_res.status_code == 200
    s_json = search_res.json()
    assert s_json["total"] >= 2
    first_job_id = s_json["items"][0]["id"]

    detail_res = await api_client.get(f"/api/v1/jobs/{first_job_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == first_job_id

    prov_res = await api_client.get(f"/api/v1/jobs/{first_job_id}/sources")
    assert prov_res.status_code == 200
    assert len(prov_res.json()["sources"]) >= 1

    # Step 5 (Test 13): Coverage Matrix Integrity — ONLY ashby and niceboard transitioned to VERIFIED!
    cov_after = (await api_client.get("/api/v1/platforms/coverage")).json()
    assert cov_after["status_summary"].get("VERIFIED") == 2

    csv_export = await api_client.get("/api/v1/platforms/coverage/export?format=csv")
    assert csv_export.status_code == 200
    assert "Greenhouse" in csv_export.text
    assert "Niceboard" in csv_export.text
