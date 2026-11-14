from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    website_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    sources: Mapped[list["Source"]] = relationship("Source", back_populates="company")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="company")


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # ATS | JOB_BOARD
    connector_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    implementation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_IMPLEMENTED", index=True)
    discovery_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    pagination_support: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    known_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    documentation_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    sources: Mapped[list["Source"]] = relationship("Source", back_populates="platform")
    evidence_records: Mapped[list["CoverageEvidence"]] = relationship("CoverageEvidence", back_populates="platform")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_status_next_sync", "status", "next_sync_at"),
        Index("ix_sources_platform_status", "platform_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    platform_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("platforms.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    board_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ATS_HOSTED_BOARD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=360)
    discovery_method: Mapped[str] = mapped_column(String(64), nullable=False, default="MANUAL")
    discovery_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_test_fixture: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    sync_lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    company: Mapped["Company | None"] = relationship("Company", back_populates="sources")
    platform: Mapped["Platform | None"] = relationship("Platform", back_populates="sources")
    source_jobs: Mapped[list["SourceJob"]] = relationship("SourceJob", back_populates="source", cascade="all, delete-orphan")
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship("IngestionRun", back_populates="source", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_first_seen", "status", "first_seen_at"),
        Index("ix_jobs_company_status", "company_id", "status"),
        Index("ix_jobs_country_workplace_status", "country_code", "workplace_type", "status"),
        Index("ix_jobs_employment_status", "employment_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    canonical_job_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(180), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    salary_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(24), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", index=True)
    employment_type_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workplace_type: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", index=True)
    workplace_type_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    primary_application_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missing_consecutive_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    search_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="jobs")
    source_jobs: Mapped[list["SourceJob"]] = relationship("SourceJob", back_populates="job", cascade="all, delete-orphan")
    changes: Mapped[list["JobChange"]] = relationship("JobChange", back_populates="job", cascade="all, delete-orphan")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_source_started", "source_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING", index=True)
    is_complete_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_deduplicated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_missing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    source: Mapped["Source"] = relationship("Source", back_populates="ingestion_runs")
    raw_records: Mapped[list["RawJobRecord"]] = relationship("RawJobRecord", back_populates="ingestion_run", cascade="all, delete-orphan")


class RawJobRecord(Base):
    __tablename__ = "raw_job_records"
    __table_args__ = (
        Index("ix_raw_job_records_source_ext", "source_id", "external_job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    ingestion_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    external_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_location: Mapped[str] = mapped_column(String(1024), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="STORED")

    ingestion_run: Mapped["IngestionRun"] = relationship("IngestionRun", back_populates="raw_records")


class SourceJob(Base):
    __tablename__ = "source_jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "external_job_id", name="uq_source_jobs_source_extid"),
        Index("ix_source_jobs_job_status", "job_id", "source_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    external_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_job_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    application_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("raw_job_records.id", ondelete="SET NULL"), nullable=True)
    title_at_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    location_at_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    salary_at_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    match_reason: Mapped[str] = mapped_column(String(120), nullable=False, default="primary_source")
    missing_runs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="source_jobs")
    source: Mapped["Source"] = relationship("Source", back_populates="source_jobs")


class JobChange(Base):
    __tablename__ = "job_changes"
    __table_args__ = (
        Index("ix_job_changes_job_detected", "job_id", "detected_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    ingestion_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="FIELD_MODIFIED")
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    job: Mapped["Job"] = relationship("Job", back_populates="changes")


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    canonical_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO_MERGED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    candidates: Mapped[list["DuplicateCandidate"]] = relationship("DuplicateCandidate", back_populates="group", cascade="all, delete-orphan")


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    duplicate_group_id: Mapped[str] = mapped_column(String(36), ForeignKey("duplicate_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    matching_signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO_LINKED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    group: Mapped["DuplicateGroup"] = relationship("DuplicateGroup", back_populates="candidates")


class ConnectorHealth(Base):
    __tablename__ = "connector_health"
    __table_args__ = (
        UniqueConstraint("platform_id", "source_id", name="uq_connector_health_platform_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform_id: Mapped[str] = mapped_column(String(36), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True, index=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNCHECKED", index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_response_time: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CoverageEvidence(Base):
    __tablename__ = "coverage_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    platform_id: Mapped[str] = mapped_column(String(36), ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    verification_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="LIVE_INGESTION_SNAPSHOT")
    evidence_location: Mapped[str] = mapped_column(String(1024), nullable=False)
    sample_job_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    extracted_job_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="VERIFIED")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    platform: Mapped["Platform"] = relationship("Platform", back_populates="evidence_records")
