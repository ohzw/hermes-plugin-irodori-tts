#!/usr/bin/env python3
"""Safe, file-backed audio history for the Irodori dashboard."""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import BinaryIO

from irodori_tts_config import hermes_home, provider_config

DEFAULT_MAX_ENTRIES = 50
DEFAULT_PREVIEW_MAX_CHARS = 240
KNOWN_FORMATS = {
    "mp3": (".mp3", "audio/mpeg"),
    "ogg": (".ogg", "audio/ogg"),
    "opus": (".opus", "audio/opus"),
    "wav": (".wav", "audio/wav"),
    "flac": (".flac", "audio/flac"),
}
_LOCK = threading.RLock()


def audio_dir() -> Path:
    return hermes_home() / "logs" / "tts-rewrite" / "audio"


def history_path() -> Path:
    return hermes_home() / "logs" / "tts-rewrite" / "audio_history.jsonl"


def _settings(provider_name: str = "irodori-local") -> tuple[bool, int, int]:
    provider = provider_config(provider_name)
    nested = provider.get("audio_history") if isinstance(provider.get("audio_history"), dict) else None
    dashboard = provider.get("dashboard") if isinstance(provider.get("dashboard"), dict) else {}
    if nested is None and isinstance(dashboard.get("audio_history"), dict):
        nested = dashboard["audio_history"]
    cfg = nested or {}

    def integer(value: object, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed >= 0 else default
        except (TypeError, ValueError):
            return default

    def setting(nested_name: str, flat_name: str, default: object) -> object:
        if nested_name in cfg:
            return cfg.get(nested_name)
        if flat_name in provider:
            return provider.get(flat_name)
        if flat_name in dashboard:
            return dashboard.get(flat_name)
        return default

    enabled = setting("enabled", "audio_history_enabled", True)
    return (
        enabled is not False,
        integer(setting("max_entries", "audio_history_max_entries", DEFAULT_MAX_ENTRIES), DEFAULT_MAX_ENTRIES),
        integer(setting("preview_max_chars", "preview_max_chars", DEFAULT_PREVIEW_MAX_CHARS), DEFAULT_PREVIEW_MAX_CHARS),
    )


def history_status(provider_name: str = "irodori-local") -> dict:
    enabled, max_entries, preview_max_chars = _settings(provider_name)
    return {"enabled": enabled, "max_entries": max_entries, "preview_max_chars": preview_max_chars}


def _preview(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return text[:limit]


def _format_info(audio_format: str) -> tuple[str, str]:
    fmt = str(audio_format or "").lower().lstrip(".")
    if fmt not in KNOWN_FORMATS:
        raise ValueError("unsupported audio format")
    return fmt, KNOWN_FORMATS[fmt][0]


def _read_entries() -> list[dict]:
    path = history_path()
    if not path.is_file():
        return []
    entries = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(item, dict) and isinstance(item.get("audio_id"), str):
            entries.append(item)
    return entries


def _write_entries(entries: list[dict]) -> None:
    target = history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in entries), encoding="utf-8")
    os.replace(temp, target)


def _sanitize(entry: dict) -> dict:
    return {key: value for key, value in entry.items() if key != "path"}


def list_history(limit: int = 20, provider_name: str = "irodori-local") -> list[dict]:
    enabled, _, _ = _settings(provider_name)
    if not enabled:
        return []
    try:
        count = max(0, min(int(limit), DEFAULT_MAX_ENTRIES))
    except (TypeError, ValueError):
        count = 20
    with _LOCK:
        entries = list(reversed(_read_entries()))[:count]
        return [_sanitize(item) for item in entries]


def resolve_audio(audio_id: str) -> tuple[Path, str] | None:
    enabled, _, _ = _settings()
    if not enabled:
        return None
    if not isinstance(audio_id, str) or not audio_id or "/" in audio_id or "\\" in audio_id or audio_id in {".", ".."}:
        return None
    with _LOCK:
        entry = next((item for item in _read_entries() if item.get("audio_id") == audio_id and item.get("status") == "ok"), None)
    if not entry or not isinstance(entry.get("path"), str):
        return None
    candidate = Path(entry["path"]).resolve()
    root = audio_dir().resolve()
    if root not in candidate.parents or candidate.suffix.lower() not in {info[0] for info in KNOWN_FORMATS.values()}:
        return None
    fmt = str(entry.get("format") or "").lower().lstrip(".")
    if fmt not in KNOWN_FORMATS or candidate.suffix.lower() != KNOWN_FORMATS[fmt][0] or not candidate.is_file():
        return None
    return candidate, KNOWN_FORMATS[fmt][1]


def record_audio(source: Path | str | bytes | bytearray | BinaryIO, *, request_id: str = "", audio_format: str = "mp3", input_text: str = "", speech_text: str = "", status: str = "ok", provider_name: str = "irodori-local") -> dict:
    fmt, suffix = _format_info(audio_format)
    if status != "ok":
        raise ValueError("only successful audio can be stored")
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        data = source_path.read_bytes()
    elif isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        data = source.read()
    if not data:
        raise ValueError("audio is empty")
    enabled, max_entries, preview_limit = _settings(provider_name)
    if not enabled:
        return {"status": "disabled", "audio_id": None, "url": None, "format": fmt, "bytes": len(data), "input_preview": _preview(input_text, preview_limit), "speech_preview": _preview(speech_text, preview_limit)}
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")
    audio_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12]
    target_dir = audio_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{audio_id}{suffix}"
    entry = {"audio_id": audio_id, "request_id": str(request_id or ""), "created_at": now, "path": str(target), "url": f"/api/audio/{audio_id}", "format": fmt, "bytes": len(data), "input_preview": _preview(input_text, preview_limit), "speech_preview": _preview(speech_text, preview_limit), "status": "ok"}
    with _LOCK:
        target.write_bytes(data)
        entries = _read_entries() + [entry]
        while len(entries) > max_entries:
            removed = entries.pop(0)
            old = Path(str(removed.get("path") or ""))
            if old.is_file() and audio_dir().resolve() in old.resolve().parents:
                try:
                    old.unlink()
                except OSError:
                    pass
        _write_entries(entries)
    return _sanitize(entry)


def retain_request_audio(request_ids: set[str], provider_name: str = "irodori-local") -> None:
    enabled, _, _ = _settings(provider_name)
    if not enabled:
        return
    retained_ids = {str(request_id) for request_id in request_ids if request_id}
    with _LOCK:
        entries = _read_entries()
        retained = []
        for entry in entries:
            if str(entry.get("request_id") or "") in retained_ids:
                retained.append(entry)
                continue
            old = Path(str(entry.get("path") or ""))
            if old.is_file() and audio_dir().resolve() in old.resolve().parents:
                try:
                    old.unlink()
                except OSError:
                    pass
        _write_entries(retained)
