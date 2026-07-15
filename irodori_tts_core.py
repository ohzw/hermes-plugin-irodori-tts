#!/usr/bin/env python3
from __future__ import annotations

import datetime as _dt
import time
import uuid
import urllib.error
from pathlib import Path


def rewrite_preview(
    text: str,
    provider_name: str = "irodori-local",
    *,
    call_llm: bool = True,
    apply_dictionary: bool = True,
) -> dict:
    """Run the CLI rewrite/dictionary path without audio side effects."""
    from irodori_tts_config import provider_config
    from irodori_tts_request import _rewrite_text_if_enabled

    cfg = provider_config(provider_name)
    if not isinstance(cfg, dict):
        cfg = {}
    rewrite_cfg = cfg.get("rewrite") or {}
    dictionary_cfg = cfg.get("pronunciation_dictionary") or cfg.get("dictionary") or {}
    if not call_llm and isinstance(rewrite_cfg, dict):
        cfg = {**cfg, "rewrite": {**rewrite_cfg, "enabled": False}}
    if not apply_dictionary and isinstance(dictionary_cfg, dict):
        disabled_dictionary = {**dictionary_cfg, "enabled": False}
        cfg = {
            **cfg,
            "pronunciation_dictionary": disabled_dictionary,
            "dictionary": disabled_dictionary,
        }

    speech_text, meta = _rewrite_text_if_enabled(text, cfg)
    selected = [
        {
            "id": entry.get("id"),
            "surface": entry.get("surface"),
            "reading": entry.get("reading"),
            "mode": entry.get("mode"),
        }
        for entry in (meta.get("dictionary_selected") or [])
    ]
    rewrite = {
        "enabled": bool(meta.get("enabled")),
        "changed": bool(meta.get("changed")),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "error": meta.get("error"),
        "elapsed_ms": int(meta.get("elapsed_ms") or 0),
    }
    return {
        "input": text,
        "speech_text": speech_text,
        "rewrite": rewrite,
        "dictionary": {
            "enabled": bool(meta.get("dictionary_enabled")),
            "selected": selected,
            "selected_count": len(selected),
            "applied": meta.get("dictionary_applied") or [],
            "warnings": [],
        },
    }


def _history_record(request_id: str, provider_name: str, text: str, preview: dict, timing: dict, status: str, error: str | None, output_bytes: int, attempts: int) -> dict:
    rewrite = preview["rewrite"]
    dictionary = preview["dictionary"]
    speech_text = preview["speech_text"]
    return {
        "request_id": request_id,
        "ts": _dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "provider": provider_name,
        "input_chars": len(text),
        "speech_chars": len(speech_text),
        "rewrite_enabled": rewrite.get("enabled"),
        "rewrite_changed": rewrite.get("changed"),
        "rewrite_provider": rewrite.get("provider"),
        "rewrite_model": rewrite.get("model"),
        "rewrite_error": rewrite.get("error"),
        "dictionary_enabled": dictionary.get("enabled"),
        "dictionary_entries": dictionary.get("selected_count"),
        "dictionary_applied": dictionary.get("applied"),
        "timing_ms": timing,
        "attempts": attempts,
        "status": status,
        "error": error,
        "input": text,
        "speech_text": speech_text,
        "output_bytes": output_bytes,
    }


def synthesize_text(text: str, output_path: Path, provider_name: str = "irodori-local", *, output_format: str = "mp3", call_llm: bool = True, apply_dictionary: bool = True, save_history: bool = True) -> dict:
    """Run the same server request primitives as the command provider.

    The caller receives audio through its explicit output path; dashboard history
    persistence is a separate policy boundary.
    """
    from irodori_tts_config import provider_config
    from irodori_tts_request import _elapsed_ms, _is_restartable_error, _request_speech, _start_server, _write_metrics, build_speech_payload
    cfg = provider_config(provider_name); preview = rewrite_preview(text, provider_name, call_llm=call_llm, apply_dictionary=apply_dictionary)
    request_id = uuid.uuid4().hex
    base_url = str(cfg.get("base_url") or "http://127.0.0.1:8088/v1").rstrip("/")
    payload = build_speech_payload(cfg, preview["speech_text"], response_format=output_format)
    output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
    timing = {"rewrite": preview["rewrite"]["elapsed_ms"]}; started = time.perf_counter(); last_error = ""
    attempts = max(1, int(cfg.get("request_attempts", 2))); audio = b""
    attempts_used = 0
    for attempt in range(attempts):
        attempts_used = attempt + 1
        try:
            t = time.perf_counter(); _start_server(cfg, base_url); timing["server_start_or_health"] = _elapsed_ms(t)
            t = time.perf_counter(); audio = _request_speech(base_url, payload, cfg.get("api_key"), float(cfg.get("request_timeout", 300))); timing["irodori_request"] = _elapsed_ms(t)
            t = time.perf_counter(); output_path.write_bytes(audio); timing["write_output"] = _elapsed_ms(t); timing["total"] = int(timing.get("rewrite") or 0) + _elapsed_ms(started)
            history = {"audio_id": None, "url": None}
            if save_history:
                from irodori_tts_history import record_audio
                try:
                    history = record_audio(output_path, request_id=request_id, audio_format=output_format, input_text=text, speech_text=preview["speech_text"], provider_name=provider_name)
                except Exception:
                    pass
                _write_metrics(cfg, _history_record(request_id, provider_name, text, preview, timing, "ok", None, len(audio), attempts_used))
            return {"status": "ok", "request_id": request_id, "audio_id": history.get("audio_id"), "url": history.get("url"), "audio_bytes": len(audio), "output_path": str(output_path), "timing_ms": timing, "rewrite": preview["rewrite"], "dictionary": preview["dictionary"], "error": None}
        except urllib.error.HTTPError as exc:
            last_error = f"Irodori TTS HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}"
        except Exception as exc:
            last_error = f"Irodori TTS request failed: {exc!r}"
        if attempt + 1 < attempts and _is_restartable_error(last_error):
            continue
        break
    timing["total"] = int(timing.get("rewrite") or 0) + _elapsed_ms(started)
    if save_history:
        _write_metrics(cfg, _history_record(request_id, provider_name, text, preview, timing, "error", last_error, 0, attempts_used))
    return {"status": "error", "request_id": request_id, "audio_bytes": 0, "output_path": str(output_path), "timing_ms": timing, "rewrite": preview["rewrite"], "dictionary": preview["dictionary"], "error": last_error}
