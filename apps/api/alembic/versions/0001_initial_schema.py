"""Initial Jobre normalized PostgreSQL schema with FTS & trigram indexes.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-11-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        op.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")

    from app.core.database import Base
    import app.models.entities  # noqa: F401

    Base.metadata.create_all(bind=bind)

    if is_pg:
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_jobs_fts_vector ON jobs
            USING GIN (
                (
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(location_raw, '')), 'B') ||
                    setweight(to_tsvector('english', coalesce(department, '')), 'C') ||
                    setweight(to_tsvector('english', coalesce(left(description_text, 12000), '')), 'D')
                )
            );
            """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_jobs_title_trgm ON jobs USING GIN (title gin_trgm_ops);"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_companies_name_trgm ON companies USING GIN (name gin_trgm_ops);"
        )


def downgrade() -> None:
    from app.core.database import Base
    import app.models.entities  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
