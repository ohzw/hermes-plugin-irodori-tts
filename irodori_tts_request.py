#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import uuid
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import urllib.error
import urllib.request

from irodori_tts_request_history import list_request_history, record_request_history

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def _load_provider_config(provider_name: str) -> dict:
    from irodori_tts_config import provider_config
    return provider_config(provider_name)


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _optional_float(value):
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value):
    if value in (None, ""):
        return None
    return int(value)


def _health_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


def _is_healthy(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(_health_url(base_url), timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _start_server(cfg: dict, base_url: str) -> None:
    if not _coerce_bool(cfg.get("auto_start_server"), True):
        return
    if _is_healthy(base_url):
        return

    command = str(
        cfg.get("server_command")
        or "uv run --no-sync python -m irodori_openai_tts --host 127.0.0.1 --port 8088"
    )
    workdir = Path(
        str(cfg.get("server_workdir") or "~/Documents/Github/Irodori-TTS-Server")
    ).expanduser()
    log_path = Path(str(cfg.get("server_log") or "/tmp/irodori_server_debug.log")).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("ab") as log:
        subprocess.Popen(
            shlex.split(command),
            cwd=str(workdir),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.time() + float(cfg.get("server_startup_timeout", 90))
    while time.time() < deadline:
        if _is_healthy(base_url):
            return
        time.sleep(1.0)
    raise SystemExit(f"Irodori TTS server did not become healthy: {_health_url(base_url)}")


def _kill_listeners(base_url: str) -> None:
    parts = urlsplit(base_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        proc = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            capture_output=True,
            timeout=5,
        )
        pids = [int(line) for line in proc.stdout.splitlines() if line.strip().isdigit()]
    except Exception:
        pids = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        time.sleep(2.0)
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _request_speech(base_url: str, payload: dict, api_key: str | None, timeout: float) -> bytes:
    req = urllib.request.Request(
        f"{base_url}/audio/speech",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


_DEFAULT_REWRITE_PROMPT = """You prepare assistant replies for Irodori-TTS, a Japanese-only expressive TTS model.

Rewrite the input into a natural Japanese speech script that is easy for Irodori-TTS to pronounce.

Rules:
- Preserve the meaning, factual content, nuance, and tone. Do not add new information.
- Convert English words, acronyms, product names, and technical terms into natural Japanese or katakana readings when that improves pronunciation.
- Keep Japanese text natural; do not over-explain.
- You may add a small number of fitting emoji when they help Irodori-TTS express emotion, but do not make the script noisy or childish.
- Remove Markdown syntax that should not be spoken.
- Omit or summarize URLs, long file paths, code blocks, tables, logs, and raw commands unless they are essential to the spoken answer.
- Output only the rewritten speech script. No preface, no notes, no Markdown fence.
"""


def _get_nested(data: dict, *keys: str) -> dict:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key) or {}
    return cur if isinstance(cur, dict) else {}


def _load_full_config() -> dict:
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    config_path = hermes_home / "config.yaml"
    if yaml is None or not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _render_rewrite_prompt(rewrite_cfg: dict) -> str:
    prompt_file = rewrite_cfg.get("prompt_file")
    if prompt_file:
        path = Path(str(prompt_file)).expanduser()
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    prompt = str(rewrite_cfg.get("prompt") or "").strip()
    return prompt or _DEFAULT_REWRITE_PROMPT


def _pronunciation_dictionary_config(provider_cfg: dict) -> dict:
    cfg = provider_cfg.get("pronunciation_dictionary") or provider_cfg.get("dictionary") or {}
    return cfg if isinstance(cfg, dict) else {}


def _pronunciation_dictionary_path(provider_cfg: dict) -> Path:
    from irodori_tts_config import dictionary_path
    cfg = _pronunciation_dictionary_config(provider_cfg)
    return Path(str(cfg.get("path") or dictionary_path())).expanduser()

def _load_pronunciation_dictionary(provider_cfg: dict) -> list[dict]:
    from irodori_tts_dictionary import load_dictionary_entries
    cfg = _pronunciation_dictionary_config(provider_cfg)
    if not _coerce_bool(cfg.get("enabled"), False):
        return []
    return [entry for entry in load_dictionary_entries(cfg) if isinstance(entry, dict)]


def _entry_patterns(entry: dict) -> list[str]:
    return [entry["surface"], *entry.get("aliases", [])]


def _entry_matches_text(text: str, entry: dict) -> bool:
    flags = 0 if entry.get("case_sensitive") else re.IGNORECASE
    for pattern in _entry_patterns(entry):
        try:
            if entry.get("match") == "regex" and re.search(pattern, text, flags): return True
            if entry.get("match") == "word" and re.search(r"(?<![A-Za-z0-9_])" + re.escape(pattern) + r"(?![A-Za-z0-9_])", text, flags): return True
            if entry.get("match", "literal") == "literal" and ((pattern in text) if entry.get("case_sensitive") else (pattern.casefold() in text.casefold())): return True
        except re.error:
            continue
    return False


def _select_dictionary_entries(provider_cfg: dict, original_text: str) -> list[dict]:
    cfg = _pronunciation_dictionary_config(provider_cfg)
    entries = _load_pronunciation_dictionary(provider_cfg)
    if not entries:
        return []
    if _coerce_bool(cfg.get("only_if_present"), True):
        entries = [entry for entry in entries if _entry_matches_text(original_text, entry)]
    limit = _optional_int(cfg.get("max_prompt_entries")) or 40
    return entries[: max(0, limit)]


def _dictionary_prompt_block(entries: list[dict]) -> str:
    prompt_entries = [e for e in entries if e.get("mode") in {"hint", "hint_and_replace"}]
    if not prompt_entries:
        return ""
    lines = [
        "",
        "Pronunciation dictionary overrides:",
        "When these terms appear, these readings override the general rewrite rules.",
    ]
    for entry in prompt_entries:
        aliases = entry.get("aliases") or []
        label = entry["surface"] + (f" / aliases: {', '.join(aliases)}" if aliases else "")
        lines.append(f'- Read "{label}" as "{entry["reading"]}".')
    return "\n".join(lines)


def _apply_pronunciation_dictionary(text: str, entries: list[dict]) -> tuple[str, list[dict]]:
    applied: list[dict] = []
    result = text
    for entry in entries:
        if entry.get("mode") not in {"replace", "hint_and_replace"}:
            continue
        before = result
        flags = 0 if entry.get("case_sensitive") else re.IGNORECASE
        for pattern in _entry_patterns(entry):
            try:
                if entry.get("match") == "regex":
                    result = re.sub(pattern, entry["reading"], result, flags=flags)
                elif entry.get("match") == "word":
                    regex = r"(?<![A-Za-z0-9_])" + re.escape(pattern) + r"(?![A-Za-z0-9_])"
                    result = re.sub(regex, entry["reading"], result, flags=flags)
                else:
                    result = re.sub(re.escape(pattern), entry["reading"], result, flags=flags)
            except re.error:
                continue
        if result != before:
            applied.append({"id": entry.get("id"), "surface": entry.get("surface"), "reading": entry.get("reading")})
    return result, applied


def _strip_rewrite_output(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    # Accept either plain text or a simple JSON object from stricter models.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            for key in ("speech_text", "text", "script", "rewritten_text"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    text = val.strip()
                    break
    except Exception:
        pass
    fence = re.fullmatch(r"```(?:\w+)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    return text.strip().strip('"').strip()


def _debug_save_rewrite(rewrite_cfg: dict, record: dict) -> str | None:
    if not _coerce_bool(rewrite_cfg.get("debug_save"), False):
        return None
    debug_dir = Path(str(rewrite_cfg.get("debug_dir") or "~/.hermes/logs/tts-rewrite")).expanduser()
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = debug_dir / f"irodori-rewrite-{stamp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _rewrite_text_if_enabled(text: str, provider_cfg: dict) -> tuple[str, dict]:
    rewrite_cfg = provider_cfg.get("rewrite") or {}
    dict_cfg = _pronunciation_dictionary_config(provider_cfg)
    dict_entries = _select_dictionary_entries(provider_cfg, text)
    apply_dict_to_prompt = _coerce_bool(dict_cfg.get("apply_to_prompt"), True)
    apply_dict_post = _coerce_bool(dict_cfg.get("apply_post_rewrite"), True)
    meta = {
        "enabled": bool(isinstance(rewrite_cfg, dict) and _coerce_bool(rewrite_cfg.get("enabled"), False)),
        "provider": rewrite_cfg.get("provider") if isinstance(rewrite_cfg, dict) else None,
        "model": rewrite_cfg.get("model") if isinstance(rewrite_cfg, dict) else None,
        "task": rewrite_cfg.get("task") if isinstance(rewrite_cfg, dict) else None,
        "changed": False,
        "error": None,
        "dictionary_enabled": _coerce_bool(dict_cfg.get("enabled"), False),
        "dictionary_entries": len(dict_entries),
        "dictionary_selected": dict_entries,
        "dictionary_applied": [],
    }
    t0 = time.perf_counter()
    try:
        if not isinstance(rewrite_cfg, dict) or not _coerce_bool(rewrite_cfg.get("enabled"), False):
            spoken = text
            applied: list[dict] = []
            if apply_dict_post and dict_entries:
                spoken, applied = _apply_pronunciation_dictionary(spoken, dict_entries)
            meta.update({"changed": spoken != text, "speech_chars": len(spoken), "dictionary_applied": applied})
            return spoken, {**meta, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}

        original = text
        if not original.strip():
            return original, {**meta, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}

        max_input_chars = _optional_int(rewrite_cfg.get("max_input_chars")) or 4000
        max_output_chars = _optional_int(rewrite_cfg.get("max_output_chars")) or max_input_chars
        fallback = str(rewrite_cfg.get("fallback") or "original").strip().lower()
        prompt = _render_rewrite_prompt(rewrite_cfg)
        if apply_dict_to_prompt and dict_entries:
            prompt += _dictionary_prompt_block(dict_entries)
        task = str(rewrite_cfg.get("task") or "tts_script_rewrite")
        meta["task"] = task

        hermes_agent_dir = Path(str(rewrite_cfg.get("hermes_agent_dir") or "~/.hermes/hermes-agent")).expanduser()
        if hermes_agent_dir.exists() and str(hermes_agent_dir) not in sys.path:
            sys.path.insert(0, str(hermes_agent_dir))

        record = {
            "input": original,
            "provider": rewrite_cfg.get("provider"),
            "model": rewrite_cfg.get("model"),
            "task": task,
            "dictionary_entries": [
                {"id": e.get("id"), "surface": e.get("surface"), "reading": e.get("reading"), "mode": e.get("mode")}
                for e in dict_entries
            ],
        }
        try:
            from agent.auxiliary_client import call_llm, extract_content_or_reasoning

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": original[:max_input_chars]},
            ]
            response = call_llm(
                task=task,
                provider=rewrite_cfg.get("provider") or None,
                model=rewrite_cfg.get("model") or None,
                base_url=rewrite_cfg.get("base_url") or None,
                api_key=rewrite_cfg.get("api_key") or None,
                api_mode=rewrite_cfg.get("api_mode") or None,
                messages=messages,
                temperature=_optional_float(rewrite_cfg.get("temperature")),
                max_tokens=_optional_int(rewrite_cfg.get("max_tokens")) or 1200,
                timeout=_optional_float(rewrite_cfg.get("timeout")) or None,
                extra_body=rewrite_cfg.get("extra_body") if isinstance(rewrite_cfg.get("extra_body"), dict) else None,
            )
            rewritten = _strip_rewrite_output(extract_content_or_reasoning(response))
            if not rewritten:
                raise RuntimeError("rewrite model returned empty text")
            dictionary_applied: list[dict] = []
            if apply_dict_post and dict_entries:
                rewritten, dictionary_applied = _apply_pronunciation_dictionary(rewritten, dict_entries)
            if len(rewritten) > max_output_chars:
                rewritten = rewritten[:max_output_chars].rstrip()
            changed = rewritten != original
            meta.update({
                "changed": changed,
                "speech_chars": len(rewritten),
                "dictionary_applied": dictionary_applied,
            })
            debug_path = _debug_save_rewrite(rewrite_cfg, record)
            if debug_path:
                meta["debug_path"] = debug_path
            return rewritten, {**meta, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
        except Exception as exc:
            meta["error"] = str(exc)
            debug_path = _debug_save_rewrite(rewrite_cfg, record)
            if debug_path:
                meta["debug_path"] = debug_path
            if fallback == "empty":
                return "", {**meta, "speech_chars": 0, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
            if fallback == "error":
                raise
            fallback_text = original
            dictionary_applied: list[dict] = []
            if apply_dict_post and dict_entries:
                fallback_text, dictionary_applied = _apply_pronunciation_dictionary(fallback_text, dict_entries)
            meta.update({"changed": fallback_text != original, "dictionary_applied": dictionary_applied})
            return fallback_text, {**meta, "speech_chars": len(fallback_text), "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
    except Exception:
        meta["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        raise


def _is_restartable_error(text: str) -> bool:
    lowered = text.lower()
    return (
        "broken pipe" in lowered
        or "connection refused" in lowered
        or "connection reset" in lowered
        or "remote end closed" in lowered
        or "timed out" in lowered
    )


def _elapsed_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def build_speech_payload(
    cfg: dict,
    text: str,
    *,
    model: str | None = None,
    voice: str | None = None,
    response_format: str | None = None,
    speed: object = None,
) -> dict:
    """Build the OpenAI-compatible Irodori speech payload from provider config.

    Keep this shared between the Hermes command-provider CLI path and the
    dashboard Playground path so user-facing Irodori settings are applied
    consistently.
    """
    model_value = model or str(cfg.get("model") or "irodori-tts")
    voice_value = voice or str(cfg.get("voice") or "none")
    response_format_value = response_format or str(cfg.get("output_format") or "mp3")
    speed_value = _optional_float(speed if speed not in (None, "") else cfg.get("speed")) or 1.0
    irodori = {
        "chunking_enabled": _coerce_bool(cfg.get("chunking_enabled"), True),
    }
    optional_map = {
        "caption": cfg.get("caption"),
        "ref_wav": cfg.get("ref_wav"),
        "ref_embed": cfg.get("ref_embed"),
        "num_steps": _optional_int(cfg.get("num_steps")),
        "t_schedule_mode": cfg.get("t_schedule_mode"),
        "sway_coeff": _optional_float(cfg.get("sway_coeff")),
        "cfg_scale_text": _optional_float(cfg.get("cfg_scale_text")),
        "cfg_scale_caption": _optional_float(cfg.get("cfg_scale_caption")),
        "cfg_scale_speaker": _optional_float(cfg.get("cfg_scale_speaker")),
        "chunk_min_chars": _optional_int(cfg.get("chunk_min_chars")),
        "first_sentence_chunk_min_chars": _optional_int(cfg.get("first_sentence_chunk_min_chars")),
        "max_caption_len": _optional_int(cfg.get("max_caption_len")),
        "seed": _optional_int(cfg.get("seed")),
    }
    for key, value in optional_map.items():
        if value not in (None, ""):
            irodori[key] = value
    return {
        "model": model_value,
        "input": text,
        "voice": voice_value,
        "response_format": response_format_value,
        "speed": speed_value,
        "irodori": irodori,
    }


def _metrics_config(cfg: dict) -> dict:
    metrics = cfg.get("metrics") or {}
    return metrics if isinstance(metrics, dict) else {}


def _write_metrics(cfg: dict, record: dict) -> None:
    from irodori_tts_history import history_status, list_history, retain_request_audio
    from irodori_tts_metrics import load_records
    metrics = _metrics_config(cfg)
    metrics_enabled = _coerce_bool(metrics.get("enabled"), True)
    log_path = Path(str(metrics.get("log_path") or "~/.hermes/logs/tts-rewrite/timings.jsonl")).expanduser()
    max_entries = min(int(history_status().get("max_entries") or 50), 50)
    if metrics_enabled and not list_request_history(limit=1):
        audio_by_request = {
            str(item.get("request_id") or ""): item
            for item in list_history(limit=max_entries)
        }
        for legacy in load_records(log_path, limit=max_entries - 1):
            request_id = str(legacy.get("request_id") or "")
            if not request_id:
                continue
            migrated = dict(legacy)
            audio = audio_by_request.get(request_id, {})
            migrated["input"] = migrated.get("input") or audio.get("input_preview") or ""
            migrated["speech_text"] = migrated.get("speech_text") or audio.get("speech_preview") or ""
            record_request_history(migrated, max_entries=max_entries)
    record_request_history(dict(record), max_entries=max_entries)
    retained_ids = {
        str(item.get("request_id"))
        for item in list_request_history(limit=max_entries)
        if item.get("request_id")
    }
    retain_request_audio(retained_ids)
    if not metrics_enabled:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    include_text = _coerce_bool(metrics.get("include_text"), False)
    if not include_text:
        record.pop("input", None)
        record.pop("speech_text", None)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _slow_reason(timing_ms: dict) -> str | None:
    total = timing_ms.get("total") or 0
    if total <= 0:
        return None
    candidates = {
        "rewrite": timing_ms.get("rewrite") or 0,
        "irodori_request": timing_ms.get("irodori_request") or 0,
        "server_start_or_health": timing_ms.get("server_start_or_health") or 0,
        "write_output": timing_ms.get("write_output") or 0,
    }
    return max(candidates, key=candidates.get)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes command-provider bridge for Irodori-TTS-Server")
    parser.add_argument("--provider-name", default="irodori-local")
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--format", default="mp3")
    parser.add_argument("--voice", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--speed", default="")
    args = parser.parse_args()

    cfg = _load_provider_config(args.provider_name)
    total_t0 = time.perf_counter()
    request_id = uuid.uuid4().hex
    original_text = Path(args.input_path).read_text(encoding="utf-8")
    from irodori_tts_core import rewrite_preview
    preview = rewrite_preview(original_text, args.provider_name)
    text = preview["speech_text"]
    rewrite_meta = {
        **preview["rewrite"],
        "dictionary_enabled": preview["dictionary"]["enabled"],
        "dictionary_entries": preview["dictionary"].get("selected_count", len(preview["dictionary"]["selected"])),
        "dictionary_applied": preview["dictionary"]["applied"],
    }
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_url = str(cfg.get("base_url") or "http://127.0.0.1:8088/v1").rstrip("/")
    model = args.model or str(cfg.get("model") or "irodori-tts")
    voice = args.voice or str(cfg.get("voice") or "none")
    response_format = args.format or str(cfg.get("output_format") or "mp3")
    speed = _optional_float(args.speed or cfg.get("speed")) or 1.0

    payload = build_speech_payload(
        cfg,
        text,
        model=args.model,
        voice=args.voice,
        response_format=args.format,
        speed=args.speed,
    )

    api_key = cfg.get("api_key")
    timeout = float(cfg.get("request_timeout", 300))
    attempts = max(1, int(cfg.get("request_attempts", 2)))
    restart_on_error = _coerce_bool(cfg.get("restart_on_error"), True)

    last_error = ""
    audio = b""
    timing_ms = {"rewrite": int(rewrite_meta.get("elapsed_ms") or 0)}
    status = "error"
    attempts_used = 0
    for attempt in range(1, attempts + 1):
        attempts_used = attempt
        try:
            t = time.perf_counter()
            _start_server(cfg, base_url)
            timing_ms["server_start_or_health"] = _elapsed_ms(t)

            t = time.perf_counter()
            audio = _request_speech(base_url, payload, api_key, timeout)
            timing_ms["irodori_request"] = _elapsed_ms(t)

            t = time.perf_counter()
            output_path.write_bytes(audio)
            try:
                from irodori_tts_history import record_audio
                record_audio(output_path, request_id=request_id, audio_format=response_format, input_text=original_text, speech_text=text, provider_name=args.provider_name)
            except Exception:
                pass
            timing_ms["write_output"] = _elapsed_ms(t)
            status = "ok"
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"Irodori TTS HTTP {exc.code}: {detail}"
        except Exception as exc:
            last_error = f"Irodori TTS request failed: {exc!r}"

        if attempt >= attempts or not restart_on_error or not _is_restartable_error(last_error):
            timing_ms["total"] = _elapsed_ms(total_t0)
            _write_metrics(cfg, {
                "request_id": request_id,
                "ts": _dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                **({"debug_path": rewrite_meta["debug_path"]} if rewrite_meta.get("debug_path") else {}),
                "provider": args.provider_name,
                "base_url": base_url,
                "model": model,
                "voice": voice,
                "response_format": response_format,
                "input_chars": len(original_text),
                "speech_chars": len(text),
                "rewrite_enabled": rewrite_meta.get("enabled"),
                "rewrite_changed": rewrite_meta.get("changed"),
                "rewrite_provider": rewrite_meta.get("provider"),
                "rewrite_model": rewrite_meta.get("model"),
                "dictionary_enabled": rewrite_meta.get("dictionary_enabled"),
                "dictionary_entries": rewrite_meta.get("dictionary_entries"),
                "dictionary_applied": rewrite_meta.get("dictionary_applied"),
                "rewrite_error": rewrite_meta.get("error"),
                "timing_ms": timing_ms,
                "attempts": attempts_used,
                "status": status,
                "error": last_error,
                "input": original_text,
                "speech_text": text,
                "output_bytes": output_path.stat().st_size if output_path.exists() else 0,
            })
            raise SystemExit(last_error)

        print(f"{last_error}; restarting Irodori server and retrying", file=os.sys.stderr)
        _kill_listeners(base_url)
        t = time.perf_counter()
        _start_server(cfg, base_url)
        timing_ms["restart"] = _elapsed_ms(t)

    if not output_path.exists() or output_path.stat().st_size <= 0:
        last_error = f"Irodori TTS produced no output at {output_path}"
        timing_ms["total"] = _elapsed_ms(total_t0)
        _write_metrics(cfg, {
            "request_id": request_id,
            "ts": _dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
            **({"debug_path": rewrite_meta["debug_path"]} if rewrite_meta.get("debug_path") else {}),
            "provider": args.provider_name,
            "base_url": base_url,
            "model": model,
            "voice": voice,
            "response_format": response_format,
            "input_chars": len(original_text),
            "speech_chars": len(text),
            "rewrite_enabled": rewrite_meta.get("enabled"),
            "rewrite_changed": rewrite_meta.get("changed"),
            "rewrite_provider": rewrite_meta.get("provider"),
            "rewrite_model": rewrite_meta.get("model"),
            "dictionary_enabled": rewrite_meta.get("dictionary_enabled"),
            "dictionary_entries": rewrite_meta.get("dictionary_entries"),
            "dictionary_applied": rewrite_meta.get("dictionary_applied"),
            "rewrite_error": rewrite_meta.get("error"),
            "timing_ms": timing_ms,
            "attempts": attempts_used,
            "status": "error",
            "error": last_error,
            "input": original_text,
            "speech_text": text,
            "output_bytes": 0,
        })
        raise SystemExit(last_error)

    timing_ms["total"] = _elapsed_ms(total_t0)
    threshold = _optional_int(_metrics_config(cfg).get("slow_threshold_ms")) or 8000
    slow = timing_ms["total"] >= threshold
    _write_metrics(cfg, {
        "request_id": request_id,
        "ts": _dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        **({"debug_path": rewrite_meta["debug_path"]} if rewrite_meta.get("debug_path") else {}),
        "provider": args.provider_name,
        "base_url": base_url,
        "model": model,
        "voice": voice,
        "response_format": response_format,
        "input_chars": len(original_text),
        "speech_chars": len(text),
        "rewrite_enabled": rewrite_meta.get("enabled"),
        "rewrite_changed": rewrite_meta.get("changed"),
        "rewrite_provider": rewrite_meta.get("provider"),
        "rewrite_model": rewrite_meta.get("model"),
        "dictionary_enabled": rewrite_meta.get("dictionary_enabled"),
        "dictionary_entries": rewrite_meta.get("dictionary_entries"),
        "dictionary_applied": rewrite_meta.get("dictionary_applied"),
        "rewrite_error": rewrite_meta.get("error"),
        "timing_ms": timing_ms,
        "attempts": attempts_used,
        "status": status,
        "slow": slow,
        "slow_reason": _slow_reason(timing_ms) if slow else None,
        "error": None,
        "input": original_text,
        "speech_text": text,
        "output_bytes": output_path.stat().st_size,
    })


if __name__ == "__main__":
    main()
