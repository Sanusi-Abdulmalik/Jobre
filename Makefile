.PHONY: help install migrate seed verify-coverage rebuild-index test dev-api dev-worker dev-web backup-db

PYTHON ?= python3

help:
	@echo "Jobre — Universal Job Board Indexer"
	@echo "  make install          Install Python & Node dependencies"
	@echo "  make migrate          Run Alembic database migrations"
	@echo "  make seed             Seed 78 required ATS & Job Board platforms"
	@echo "  make verify-coverage  Execute live connector verification & record evidence"
	@echo "  make rebuild-index    Rebuild search index from PostgreSQL source of truth"
	@echo "  make test             Execute full unit, integration & acceptance test suite"
	@echo "  make dev-api          Start FastAPI server on 0.0.0.0:8000"
	@echo "  make dev-worker       Start background ingestion worker & scheduler"
	@echo "  make dev-web          Start Next.js frontend on 0.0.0.0:3000"

install:
	pip install -e ".[dev]"
	cd apps/web && npm install

migrate:
	PYTHONPATH=.:apps/api alembic -c apps/api/alembic.ini upgrade head

seed:
	PYTHONPATH=.:apps/api $(PYTHON) scripts/seed_platforms.py

verify-coverage:
	PYTHONPATH=.:apps/api $(PYTHON) scripts/verify_coverage.py

rebuild-index:
	PYTHONPATH=.:apps/api $(PYTHON) scripts/rebuild_search_index.py

test:
	PYTHONPATH=.:apps/api pytest -v

dev-api:
	PYTHONPATH=.:apps/api uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port 8000 --reload

dev-worker:
	PYTHONPATH=.:apps/api $(PYTHON) -m apps.workers.main

dev-web:
	cd apps/web && npm run dev -- --hostname 0.0.0.0 --port 3000

backup-db:
	pg_dump -h 127.0.0.1 -p 5432 -U jobre -d jobre > data/backups/jobre_latest.sql
