from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

from packages.common.config import get_settings
from packages.common.security import sha256_hex


class RawSnapshotStore:
    """Stores compressed raw connector payloads so original source evidence is never lost."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.base_path = Path(base_path or settings.raw_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_snapshot(
        self,
        *,
        connector_key: str,
        run_id: str,
        external_job_id: str,
        payload: dict[str, Any] | list[Any] | str,
    ) -> tuple[str, str]:
        """Persist gzip-compressed raw job snapshot. Returns (storage_location, content_hash)."""
        if isinstance(payload, str):
            raw_bytes = payload.encode("utf-8")
        else:
            raw_bytes = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)

        content_hash = sha256_hex(raw_bytes)
        day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe_ext = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(external_job_id))[:64]
        target_dir = self.base_path / connector_key / day_str
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{run_id[:8]}_{safe_ext}_{content_hash[:12]}.json.gz"
        full_path = target_dir / filename
        with gzip.open(full_path, "wb", compresslevel=6) as fh:
            fh.write(raw_bytes)

        rel_location = f"file://{full_path}"
        return rel_location, content_hash

    def load_snapshot(self, storage_location: str) -> bytes:
        path_str = storage_location.removeprefix("file://")
        with gzip.open(path_str, "rb") as fh:
            return fh.read()
