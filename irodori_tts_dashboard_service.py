#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from irodori_tts_config import dictionary_config, dictionary_path, hermes_home, provider_config, safe_config_view
from irodori_tts_dictionary import load_dictionary
from irodori_tts_history import list_history
from irodori_tts_request_history import list_request_history
from irodori_tts_metrics import DEFAULT_LOG, load_records, summarize

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_SERVER_LOG = "/tmp/irodori_server_debug.log"


def _health_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


def _fetch_health(base_url: str, timeout: float = 2.0) -> dict:
    try:
        with urllib.request.urlopen(_health_url(base_url), timeout=timeout) as resp:
            return {"ok": True, "status": resp.status, "body": resp.read().decode("utf-8", "replace")[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _listener_pids(base_url: str) -> list[int]:
    try:
        port = urlsplit(base_url).port or 8088
        result = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, timeout=2, check=False)
        return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]
    except Exception:
        return []


def _tail_file(path: str | Path, *, max_lines: int = 120, max_bytes: int = 40000) -> dict:
    p = Path(str(path)).expanduser()
    if not p.exists(): return {"available": False, "path": str(p), "exists": False, "lines": []}
    try:
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > max_bytes: f.seek(max(0, size - max_bytes))
            lines = f.read().decode("utf-8", "replace").splitlines()[-max_lines:]
        return {"available": True, "path": str(p), "exists": True, "size_bytes": size, "truncated": size > max_bytes, "lines": lines}
    except Exception as exc:
        return {"available": False, "path": str(p), "exists": True, "error": str(exc), "lines": []}


def _latest_debug() -> dict:
    files = sorted((hermes_home() / "logs" / "tts-rewrite").glob("irodori-rewrite-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files: return {"available": False}
    try: return {"available": True, "path": str(files[0]), "data": json.loads(files[0].read_text(encoding="utf-8"))}
    except Exception as exc: return {"available": False, "path": str(files[0]), "error": str(exc)}


def _recommendation(summary: dict) -> str:
    ratios = summary.get("ratios") or {}
    if not summary.get("ok_runs"): return "まだ成功した計測がありません。まず短いテスト音声を生成してください。"
    if float(ratios.get("rewrite") or 0) >= 0.40: return "LLM rewrite が大きめです。軽量な auxiliary.tts_script_rewrite model の比較候補です。"
    if float(ratios.get("irodori_request") or 0) >= 0.60: return "Irodori 生成時間が主因です。num_steps、chunking、MPS/prewarm 周りの調整候補です。"
    if float(ratios.get("server_start_or_health") or 0) >= 0.25: return "server health/start 待ちが目立ちます。Irodori server の常駐・preload を確認してください。"
    return "目立つ単独ボトルネックはありません。直近の slow run を個別確認してください。"


def get_public_status(limit: int = 20) -> dict:
    cfg = provider_config(); base_url = str(cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    records = load_records(DEFAULT_LOG, limit=limit); metrics = cfg.get("metrics") or {}; threshold = int(metrics.get("slow_threshold_ms") or 8000)
    for record in records:
        timing = record.get("timing_ms") or {}
        if "slow" not in record: record["slow"] = bool((timing.get("total") or 0) >= threshold)
        if record.get("slow") and not record.get("slow_reason"):
            fields = {key: timing.get(key) or 0 for key in ("rewrite", "irodori_request", "server_start_or_health", "write_output")}; record["slow_reason"] = max(fields, key=fields.get)
    health = _fetch_health(base_url); dictionary = load_dictionary(); entries = dictionary.get("entries") or []; summary = summarize(records)
    rewrite = cfg.get("rewrite") or {}; server_log = cfg.get("server_log") or DEFAULT_SERVER_LOG; recent = list(reversed(records[-limit:]))
    return {"now": time.strftime("%Y-%m-%d %H:%M:%S"), "base_url": base_url, "health": health, "listener_pids": _listener_pids(base_url), "slow_threshold_ms": threshold,
            "config": {"model": cfg.get("model"), "voice": cfg.get("voice"), "num_steps": cfg.get("num_steps"), "t_schedule_mode": cfg.get("t_schedule_mode"), "sway_coeff": cfg.get("sway_coeff"), "chunking_enabled": cfg.get("chunking_enabled"), "chunk_min_chars": cfg.get("chunk_min_chars"), "first_sentence_chunk_min_chars": cfg.get("first_sentence_chunk_min_chars"), "seed": cfg.get("seed"), "ref_embed": cfg.get("ref_embed"), "caption": cfg.get("caption"), "server_log": server_log, "rewrite_enabled": rewrite.get("enabled"), "rewrite_provider": rewrite.get("provider"), "rewrite_model": rewrite.get("model"), "dictionary_enabled": dictionary_config().get("enabled"), "dictionary_path": str(dictionary_path()), "dictionary_entries": len(entries)},
            "summary": summary, "recommendation": _recommendation(summary), "recent": recent, "latest_debug": _latest_debug(), "dictionary": {"path": str(dictionary_path()), "entries": entries}, "server_log": _tail_file(server_log)}


def get_config_view(provider_name: str = "irodori-local") -> dict:
    return safe_config_view(provider_name)

def get_recent_requests(limit: int = 30) -> dict:
    status = get_public_status(limit)
    text_by_request = {str(item.get("request_id") or ""): item for item in list_request_history(limit=50)}
    audio_by_request = {str(item.get("request_id") or ""): item for item in list_history(limit=50)}
    requests = []
    for record in status.get("recent", []):
        summary = dict(record)
        request_id = str(summary.get("request_id") or "")
        saved = text_by_request.get(request_id, {})
        legacy_audio = audio_by_request.get(request_id, {})
        original_text = saved.get("original_text")
        if original_text is None:
            original_text = summary.get("input")
        if original_text is None:
            original_text = legacy_audio.get("input_preview")
        summary["original_text"] = original_text
        summary.pop("input", None)
        summary.pop("speech_text", None)
        requests.append(summary)
    return {"requests": requests, "summary": status.get("summary", {})}


def _truncate(value, limit: int = 4000):
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def _request_detail(record: dict) -> dict:
    detail = {
        "request_id": record.get("request_id"),
        "ts": record.get("ts"),
        "status": record.get("status"),
        "original_text": _truncate(record.get("input")),
        "speech_text": _truncate(record.get("speech_text")),
        "rewrite": {
            "enabled": record.get("rewrite_enabled"),
            "changed": record.get("rewrite_changed"),
            "error": record.get("rewrite_error"),
            "provider": record.get("rewrite_provider"),
            "model": record.get("rewrite_model"),
        },
        "dictionary": {
            "enabled": record.get("dictionary_enabled"),
            "selected_count": record.get("dictionary_entries"),
            "applied": record.get("dictionary_applied"),
        },
        "timing_ms": record.get("timing_ms") if isinstance(record.get("timing_ms"), dict) else {},
        "output_bytes": record.get("output_bytes"),
        "error": record.get("error"),
    }
    for key in ("audio_id", "debug_path"):
        if record.get(key) is not None:
            detail[key] = record[key]
    return detail


def get_request_detail(request_id: str) -> dict:
    saved_text = next((item for item in list_request_history(limit=50) if str(item.get("request_id") or "") == str(request_id)), None)
    for record in load_records(DEFAULT_LOG, limit=1000):
        if str(record.get("request_id") or "") == str(request_id):
            detail = _request_detail(record)
            if saved_text:
                detail["original_text"] = saved_text.get("original_text")
                detail["speech_text"] = saved_text.get("speech_text")
            audio = next((item for item in list_history(limit=50) if str(item.get("request_id") or "") == str(request_id)), None)
            if audio:
                detail["audio"] = {
                    "audio_id": audio.get("audio_id"),
                    "url": audio.get("url"),
                    "format": audio.get("format"),
                    "bytes": audio.get("bytes"),
                    "created_at": audio.get("created_at"),
                    "status": audio.get("status"),
                    "input_preview": audio.get("input_preview"),
                    "speech_preview": audio.get("speech_preview"),
                }
                detail["audio_id"] = audio.get("audio_id")
            return detail
    return {}
