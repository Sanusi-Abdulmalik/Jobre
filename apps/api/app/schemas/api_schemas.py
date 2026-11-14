from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DiscoverSourceRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048, description="Company website, career page, or job board URL")


class CreateSourceRequest(BaseModel):
    source_url: str = Field(..., min_length=4, max_length=2048)
    source_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    platform_key: str | None = Field(default=None, max_length=80)
    board_token: str | None = Field(default=None, max_length=255)
    priority: str = Field(default="NORMAL")
    run_immediately: bool = Field(default=False)
    max_jobs: int | None = Field(default=40, ge=1, le=500)


class BulkImportSourcesRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=200)
    priority: str = Field(default="NORMAL")


class RefreshSourceRequest(BaseModel):
    execute_inline: bool = Field(default=True, description="Execute immediately and return run result, or enqueue to worker")
    max_jobs: int | None = Field(default=50, ge=1, le=500)
    record_verification: bool = Field(default=True)


class TestConnectorRequest(BaseModel):
    source_url: str | None = Field(default=None, max_length=2048)
    company_name: str = Field(default="Connector Test Org", max_length=255)
    board_token: str | None = Field(default=None, max_length=255)


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
