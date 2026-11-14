from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Company, Platform, Source
from packages.common.security import canonicalize_url, extract_canonical_domain, validate_public_url
from packages.discovery.engine import SourceDiscoveryEngine, SourceDiscoveryResult
from packages.normalization.engine import normalize_company_name


PRIORITY_REFRESH_MINUTES = {
    "HIGH": 120,
    "NORMAL": 360,
    "LOW": 1440,
}


async def get_or_create_company(
    session: AsyncSession,
    company_name: str,
    website_url: str | None = None,
) -> Company:
    disp_name, norm_name = normalize_company_name(company_name)
    existing = (
        await session.execute(select(Company).where(Company.normalized_name == norm_name))
    ).scalar_one_or_none()
    if existing:
        if website_url and not existing.website_url:
            existing.website_url = website_url
        return existing

    comp = Company(
        name=disp_name,
        normalized_name=norm_name,
        website_url=website_url,
    )
    session.add(comp)
    await session.flush()
    return comp


async def register_source(
    session: AsyncSession,
    *,
    source_url: str,
    source_name: str | None = None,
    company_name: str | None = None,
    platform_key: str | None = None,
    board_token: str | None = None,
    priority: str = "NORMAL",
    source_config: dict[str, Any] | None = None,
    is_test_fixture: bool = False,
    allow_private_urls: bool = False,
    auto_discover: bool = True,
) -> tuple[Source, bool, SourceDiscoveryResult | None]:
    """
    Validate, identify, and idempotently register a career page or job board source.
    Returns (source, created_new, discovery_result).
    """
    validate_public_url(
        source_url,
        allow_private=allow_private_urls,
        resolve_dns=not is_test_fixture and not allow_private_urls,
    )

    discovery_res: SourceDiscoveryResult | None = None
    if auto_discover and not platform_key:
        engine = SourceDiscoveryEngine(allow_private_urls=allow_private_urls)
        discovery_res = await engine.discover_url(
            source_url,
            probe_network=not is_test_fixture,
        )

    effective_url = (
        discovery_res.canonical_source_url
        if (discovery_res and discovery_res.detected and discovery_res.canonical_source_url)
        else source_url.strip()
    )
    canonical_src = canonicalize_url(effective_url) or effective_url

    # Prevent duplicate source registration
    existing = (
        await session.execute(
            select(Source)
            .where(Source.source_url == canonical_src)
            .options(selectinload(Source.company), selectinload(Source.platform))
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False, discovery_res

    resolved_key = platform_key or (discovery_res.platform_key if discovery_res else None)
    platform_row: Platform | None = None
    if resolved_key:
        platform_row = (
            await session.execute(select(Platform).where(Platform.connector_key == resolved_key))
        ).scalar_one_or_none()

    resolved_company_name = (
        company_name
        or (discovery_res.company_name if discovery_res else None)
        or extract_canonical_domain(canonical_src).split(".")[0].title()
    )
    company_row = await get_or_create_company(session, resolved_company_name)

    prio = priority.upper() if priority.upper() in PRIORITY_REFRESH_MINUTES else "NORMAL"
    interval = PRIORITY_REFRESH_MINUTES[prio]

    src_type = (
        discovery_res.source_type
        if discovery_res
        else ("INDEPENDENT_JOB_BOARD" if (platform_row and platform_row.category == "JOB_BOARD") else "ATS_HOSTED_BOARD")
    )
    disc_method = discovery_res.discovery_method if discovery_res else ("MANUAL" if platform_key else "DIRECT")
    disc_conf = discovery_res.confidence if discovery_res else 1.0
    resolved_token = board_token or (discovery_res.board_token if discovery_res else None)

    final_name = source_name or (
        f"{company_row.name} ({platform_row.name})" if platform_row else f"{company_row.name} Careers"
    )

    src = Source(
        company_id=company_row.id,
        platform_id=platform_row.id if platform_row else None,
        source_name=final_name,
        source_url=canonical_src,
        board_token=resolved_token,
        canonical_domain=extract_canonical_domain(canonical_src),
        source_type=src_type,
        status="ACTIVE" if platform_row else "PENDING_VALIDATION",
        priority=prio,
        refresh_interval_minutes=interval,
        discovery_method=disc_method,
        discovery_confidence=disc_conf,
        source_config=source_config or {},
        is_test_fixture=is_test_fixture,
        next_sync_at=datetime.now(timezone.utc),
    )
    session.add(src)
    await session.commit()

    reloaded = (
        await session.execute(
            select(Source)
            .where(Source.id == src.id)
            .options(selectinload(Source.company), selectinload(Source.platform))
        )
    ).scalar_one()
    return reloaded, True, discovery_res
