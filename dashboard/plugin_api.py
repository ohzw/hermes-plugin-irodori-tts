"""FastAPI routes for the Hermes Irodori TTS dashboard extension."""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from irodori_tts_config import dictionary_path  # noqa: E402
from irodori_tts_core import rewrite_preview, synthesize_text  # noqa: E402
from irodori_tts_dashboard_service import (  # noqa: E402
    get_config_view,
    get_public_status,
    get_recent_requests,
    get_request_detail,
)
from irodori_tts_dictionary import (  # noqa: E402
    DictionaryValidationError,
    add_entry,
    delete_entry,
    load_dictionary,
    update_entry,
    validate_dictionary,
    validate_dictionary_entry,
)
from irodori_tts_history import history_status, list_history, resolve_audio  # noqa: E402
from irodori_tts_metrics import DEFAULT_LOG  # noqa: E402
from irodori_tts_settings import (  # noqa: E402
    ConfigConflictError,
    ConfigStore,
    ConfigStoreError,
    list_voice_assets,
    schema as settings_schema,
    validate_values,
)

router = APIRouter()
_PLAYGROUND_LOCK = threading.Lock()
_FORMATS = {
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "wav": "audio/wav",
    "flac": "audio/flac",
}


def _audio_prefix(request: Request) -> str:
    return "/api/plugins/irodori-tts/audio/" if request.url.path.startswith("/api/plugins/") else "/api/audio/"


def _rebase_audio_urls(value: Any, prefix: str) -> Any:
    """Map stored legacy audio URLs to the active API mount."""
    if isinstance(value, dict):
        return {key: _rebase_audio_urls(item, prefix) for key, item in value.items()}
    if isinstance(value, list):
        return [_rebase_audio_urls(item, prefix) for item in value]
    if isinstance(value, str) and value.startswith("/api/audio/"):
        audio_id = value.removeprefix("/api/audio/")
        return f"{prefix}{audio_id}"
    return value


def _config_payload() -> dict[str, Any]:
    store = ConfigStore()
    return {
        "schema": settings_schema(),
        "values": store.read_values(),
        "revision": store.revision(),
        "apply_status": "applied",
    }


def _config_update(payload: dict[str, Any], *, validate_only: bool = False) -> dict[str, Any]:
    values = payload.get("values")
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")
    if validate_only:
        result = validate_values(values)
        if result["errors"]:
            raise HTTPException(status_code=400, detail=result)
        return {"ok": True, "data": result, "warnings": result["warnings"], "error": None}
    try:
        result = ConfigStore().update(values, payload.get("revision"))
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not result.get("saved"):
        raise HTTPException(status_code=400, detail=result.get("validation") or {})
    result["apply_status"] = "applied"
    return {
        "ok": True,
        "data": result,
        "warnings": (result.get("validation") or {}).get("warnings", []),
        "error": None,
    }


def _dashboard_action(name: str) -> dict[str, Any]:
    from irodori_tts_dashboard_server import dashboard_status, start_dashboard, stop_dashboard

    actions = {"status": dashboard_status, "start": start_dashboard, "stop": stop_dashboard}
    try:
        return actions[name]()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/dashboard/status")
async def standalone_dashboard_status():
    return await run_in_threadpool(_dashboard_action, "status")


@router.post("/dashboard/start")
async def standalone_dashboard_start():
    return await run_in_threadpool(_dashboard_action, "start")


@router.post("/dashboard/stop")
async def standalone_dashboard_stop():
    return await run_in_threadpool(_dashboard_action, "stop")


@router.get("/status")
async def status(request: Request, limit: int = 30):
    return _rebase_audio_urls(get_public_status(limit=limit), _audio_prefix(request))


def _metrics_revision() -> tuple[int, int] | None:
    try:
        stat = DEFAULT_LOG.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


@router.get("/events/status")
async def status_events(request: Request, limit: int = 30):
    async def events():
        previous: tuple[int, int] | None | object = object()
        last_snapshot = 0.0
        while True:
            revision = _metrics_revision()
            now = time.monotonic()
            if revision != previous or now - last_snapshot >= 15:
                snapshot = await run_in_threadpool(get_public_status, limit=limit)
                snapshot = _rebase_audio_urls(snapshot, _audio_prefix(request))
                payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                yield f"event: status\ndata: {payload}\n\n"
                previous = revision
                last_snapshot = now
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/config")
async def config():
    return {"ok": True, "data": _config_payload(), "warnings": [], "error": None}


@router.patch("/config")
async def update_config(payload: dict[str, Any]):
    return _config_update(payload)


@router.post("/config/validate")
async def validate_config(payload: dict[str, Any]):
    return _config_update(payload, validate_only=True)


@router.get("/config/view")
async def config_view():
    return get_config_view()


@router.get("/config/voice-assets")
async def voice_assets():
    return {"ok": True, "data": {"assets": list_voice_assets()}, "warnings": [], "error": None}


@router.get("/requests")
async def requests(request: Request, limit: int = 50):
    return _rebase_audio_urls(get_recent_requests(limit=limit), _audio_prefix(request))


@router.get("/requests/{request_id}")
async def request_detail(request_id: str, request: Request):
    detail = get_request_detail(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="request not found")
    return _rebase_audio_urls(detail, _audio_prefix(request))


@router.get("/audio-history")
async def audio_history(request: Request, limit: int = 50):
    current = history_status()
    warning = None
    if not current["enabled"]:
        warning = "Audio history is disabled in Hermes config; generated audio is not persisted."
    return {
        "ok": True,
        "data": _rebase_audio_urls(list_history(limit), _audio_prefix(request)) if current["enabled"] else [],
        "warnings": [warning] if warning else [],
        "disabled": not current["enabled"],
        "error": None,
    }


@router.get("/audio/{audio_id}")
async def audio(audio_id: str):
    resolved = resolve_audio(audio_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="audio not found")
    path, content_type = resolved
    return Response(content=path.read_bytes(), media_type=content_type)


@router.get("/dictionary")
async def dictionary():
    data = load_dictionary()
    return {"path": str(dictionary_path()), "entries": data.get("entries") or []}


@router.post("/dictionary/validate")
async def dictionary_validate(payload: dict[str, Any]):
    if isinstance(payload.get("dictionary"), dict):
        result = validate_dictionary(payload["dictionary"])
    else:
        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else payload
        entry_id = str(payload.get("id") or entry.get("id") or "") or None
        result = validate_dictionary_entry(entry, entry_id=entry_id)
    return {"ok": True, "data": result, "warnings": result["warnings"], "error": None}


@router.post("/dictionary/add")
async def dictionary_add(payload: dict[str, Any]):
    try:
        entry, warnings = add_entry(payload)
    except DictionaryValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.result) from exc
    return {"ok": True, "entry": entry, "warnings": warnings}


@router.post("/dictionary/update")
async def dictionary_update(payload: dict[str, Any]):
    entry_id = str(payload.get("id") or "")
    if not entry_id:
        raise HTTPException(status_code=400, detail="id is required")
    try:
        entry, warnings = update_entry(entry_id, payload)
    except DictionaryValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.result) from exc
    return {"ok": True, "entry": entry, "warnings": warnings}


@router.post("/dictionary/delete")
async def dictionary_delete(payload: dict[str, Any]):
    entry_id = str(payload.get("id") or "")
    if not entry_id:
        raise HTTPException(status_code=400, detail="id is required")
    delete_entry(entry_id)
    return {"ok": True}


@router.post("/playground/rewrite-preview")
async def playground_rewrite(payload: dict[str, Any]):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    preview = rewrite_preview(
        text,
        call_llm=bool(payload.get("call_llm", False)),
        apply_dictionary=bool(payload.get("apply_dictionary", True)),
    )
    return {"ok": True, "data": preview, "warnings": preview["dictionary"]["warnings"], "error": None}


@router.post("/playground/tts")
async def playground_tts(payload: dict[str, Any], request: Request):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    output_format = str(payload.get("format") or "mp3").lower()
    if output_format not in _FORMATS:
        raise HTTPException(status_code=400, detail="unsupported audio format")
    if not _PLAYGROUND_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="another TTS generation is already in progress")

    temp_dir: Path | None = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="irodori-dashboard-"))
        output_path = temp_dir / f"audio.{output_format}"
        result = synthesize_text(
            text,
            output_path,
            output_format=output_format,
            call_llm=bool(payload.get("call_llm", False)),
            apply_dictionary=bool(payload.get("apply_dictionary", True)),
            save_history=False,
        )
        if result.get("status") != "ok" or not output_path.is_file():
            raise HTTPException(status_code=502, detail=result.get("error") or "TTS generation failed")
        audio_bytes = output_path.read_bytes()
        data = {
            "request_id": result["request_id"],
            "audio_id": result.get("audio_id"),
            "url": result.get("url"),
            "rewrite": result["rewrite"],
            "dictionary": result["dictionary"],
            "timing_ms": result["timing_ms"],
            "bytes": len(audio_bytes),
            "format": output_format,
            "data_url": f"data:{_FORMATS[output_format]};base64,{base64.b64encode(audio_bytes).decode('ascii')}",
        }
        return {"ok": True, "data": _rebase_audio_urls(data, _audio_prefix(request)), "warnings": [], "error": None}
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
        _PLAYGROUND_LOCK.release()
