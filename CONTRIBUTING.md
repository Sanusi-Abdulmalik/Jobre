# Contributing to Jobre

Thank you for contributing to **Jobre — Universal Job Board Indexer**.

## Engineering Standards

1. **Evidence Over Claims**: Never mark a platform `VERIFIED` unless its connector has been executed against a real live source powered by that platform, produced valid normalized job records, stored raw snapshot evidence, and recorded a verification entry in `coverage_evidence`.
2. **Responsible Collection**: Prefer official public APIs, RSS/XML feeds, and structured JSON-LD over HTML scraping. Respect per-domain rate limits, identify requests with `JobreBot/1.0`, and never bypass CAPTCHAs, authentication gates, or private endpoints.
3. **Safe Job Closure**: Never mark jobs `CLOSED` on failed, rate-limited, maintenance-redirected, or incomplete ingestion runs.
4. **Cross-Source Provenance**: Deduplication must preserve every `source_jobs` record and support clean unmerging.
5. **Testing**: Every new connector or normalization rule must include unit tests with recorded fixtures under `tests/fixtures/`.

## Pull Request Checklist

- [ ] `make migrate` applies cleanly on PostgreSQL 17.
- [ ] `make test` passes with zero regressions.
- [ ] New connectors implement `BaseConnector` (`discover`, `fetch_jobs`, `normalize`, `health_check`) and register in `packages/connectors/registry.py`.
- [ ] `docs/PROJECT_STATUS.md` and `docs/coverage-matrix.md` are updated accurately.
