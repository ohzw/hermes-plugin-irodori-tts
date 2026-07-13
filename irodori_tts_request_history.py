#!/usr/bin/env python3
"""Bounded local text history for Irodori dashboard requests."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from irodori_tts_config import hermes_home

DEFAULT_MAX_ENTRIES = 50
_LOCK = threading.RLock()


def history_path() -> Path:
    return hermes_home() / "logs" / "tts-rewrite" / "request_history.jsonl"


def _read() -> list[dict]:
    path = history_path()
    if not path.is_file():
        return []
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(row, dict) and row.get("request_id"):
            rows.append(row)
    return rows


def _write(rows: list[dict]) -> None:
    target = history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def record_request_history(record: dict, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
    request_id = str(record.get("request_id") or "")
    if not request_id:
        return
    row = {
        "request_id": request_id,
        "ts": record.get("ts"),
        "status": record.get("status"),
        "original_text": record.get("input") if isinstance(record.get("input"), str) else "",
        "speech_text": record.get("speech_text") if isinstance(record.get("speech_text"), str) else "",
    }
    count = max(1, int(max_entries))
    with _LOCK:
        rows = [item for item in _read() if item.get("request_id") != request_id]
        rows.append(row)
        _write(rows[-count:])


def list_request_history(limit: int = DEFAULT_MAX_ENTRIES) -> list[dict]:
    count = max(0, min(int(limit), DEFAULT_MAX_ENTRIES))
    with _LOCK:
        return list(reversed(_read()))[:count]
