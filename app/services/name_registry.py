"""Store names for successfully generated hall tickets in a local JSON file."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = Path(
    os.environ.get("NAME_REGISTRY_PATH", _ROOT / "runtime-data" / "generated_names.json")
)
_WRITE_LOCK = threading.Lock()


async def record_generated_name(name: str) -> bool:
    """Persist generated names locally; serverless storage is not durable."""
    if os.environ.get("VERCEL") == "1":
        return False

    await asyncio.to_thread(_record_generated_name, name)
    return True


def _record_generated_name(name: str) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _WRITE_LOCK:
        records = []
        if _REGISTRY_PATH.exists():
            with _REGISTRY_PATH.open("r", encoding="utf-8") as registry_file:
                records = json.load(registry_file)
            if not isinstance(records, list):
                raise ValueError("Generated names registry must contain a JSON list.")

        records.append({
            "name": name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=_REGISTRY_PATH.parent,
                prefix=f"{_REGISTRY_PATH.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(records, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, _REGISTRY_PATH)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
