#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from irodori_tts_config import dictionary_config, dictionary_path


def load_dictionary(provider_name: str = "irodori-local") -> dict:
    path = dictionary_path(provider_name)
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "entries": []}
    if isinstance(data, list):
        data = {"version": 1, "entries": data}
    if not isinstance(data, dict):
        data = {"version": 1, "entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def save_dictionary(data: dict, provider_name: str = "irodori-local") -> None:
    path = dictionary_path(provider_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_entry(raw: dict) -> dict:
    surface = str(raw.get("surface") or raw.get("term") or "").strip()
    reading = str(raw.get("reading") or raw.get("pronunciation") or "").strip()
    aliases = raw.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [x.strip() for x in aliases.split(",")]
    aliases = [str(x).strip() for x in aliases if str(x).strip()]
    match = str(raw.get("match") or "literal").strip().lower()
    if match not in {"literal", "word", "regex"}:
        match = "literal"
    mode = str(raw.get("mode") or "hint_and_replace").strip().lower()
    if mode not in {"hint", "replace", "hint_and_replace"}:
        mode = "hint_and_replace"
    return {"id": str(raw.get("id") or f"dict-{uuid.uuid4().hex[:10]}"), "surface": surface, "reading": reading,
            "aliases": aliases, "match": match, "case_sensitive": bool(raw.get("case_sensitive", False)),
            "mode": mode, "enabled": bool(raw.get("enabled", True)), "notes": str(raw.get("notes") or ""),
            "created_at": raw.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def _entry_patterns(entry: dict) -> list[str]:
    return [str(entry.get("surface") or "").strip(), *(str(value).strip() for value in (entry.get("aliases") or []) if str(value).strip())]


def _pattern_key(value: str) -> str:
    return " ".join(value.casefold().split())


class DictionaryValidationError(ValueError):
    def __init__(self, result: dict):
        super().__init__("dictionary validation failed")
        self.result = result


def _raise_on_validation(result: dict) -> None:
    if not result["ok"]:
        raise DictionaryValidationError(result)


def validate_entry(payload: dict, existing_entries: list[dict] | None = None, entry_id: str | None = None) -> dict:
    entry = normalize_entry(payload)
    entries = [normalize_entry(item) for item in (existing_entries or []) if isinstance(item, dict)]
    result = {"ok": True, "errors": [], "warnings": [], "info": []}
    if not entry["surface"]:
        result["errors"].append({"code": "required_surface", "field": "surface", "message": "surface is required"})
    if not entry["reading"]:
        result["errors"].append({"code": "required_reading", "field": "reading", "message": "reading is required"})
    if entry["match"] == "regex":
        for pattern in _entry_patterns(entry):
            try:
                re.compile(pattern)
            except re.error as exc:
                result["errors"].append({"code": "invalid_regex", "field": "surface", "message": str(exc)})
                break
    duplicate_count = sum(str(item.get("id")) == str(entry.get("id")) for item in entries)
    if (entry_id is None and duplicate_count) or (entry_id is not None and duplicate_count > 1):
        result["errors"].append({"code": "duplicate_id", "field": "id", "message": "id already exists"})
    surface_key = _pattern_key(entry["surface"])
    for item in entries:
        if entry_id and str(item.get("id")) == str(entry_id):
            continue
        other_key = _pattern_key(item.get("surface", ""))
        if surface_key and other_key:
            if surface_key == other_key:
                result["warnings"].append({"code": "duplicate_surface", "entry_id": item.get("id"), "message": "duplicate surface"})
            elif surface_key in other_key or other_key in surface_key:
                result["warnings"].append({"code": "near_duplicate_surface", "entry_id": item.get("id"), "message": "near-duplicate surface may change match ordering"})
            if item.get("enabled", True) is False and surface_key == other_key:
                result["warnings"].append({"code": "disabled_same_surface", "entry_id": item.get("id"), "message": "a disabled entry has the same surface"})
        if surface_key and any(surface_key == _pattern_key(alias) for alias in (item.get("aliases") or [])):
            result["warnings"].append({"code": "alias_surface_collision", "entry_id": item.get("id"), "message": "surface collides with another entry alias"})
        if any(_pattern_key(alias) == other_key for alias in (entry.get("aliases") or [])) and other_key:
            result["warnings"].append({"code": "alias_surface_collision", "entry_id": item.get("id"), "message": "alias collides with another entry surface"})
        if entry.get("enabled", True) and item.get("enabled", True) and surface_key and other_key and (surface_key in other_key or other_key in surface_key):
            result["warnings"].append({"code": "multiple_matches", "entry_id": item.get("id"), "message": "multiple enabled entries may match the same text; ordering matters"})
    if entry["surface"] and entry["surface"] == entry["reading"]:
        result["warnings"].append({"code": "surface_equals_reading", "message": "surface and reading are identical"})
    result["ok"] = not result["errors"]
    return result


def validate_dictionary_entry(payload: dict, provider_name: str = "irodori-local", entry_id: str | None = None) -> dict:
    data = load_dictionary(provider_name)
    return validate_entry(payload, data.get("entries") or [], entry_id=entry_id)


def add_entry(payload: dict, provider_name: str = "irodori-local") -> tuple[dict, list[dict]]:
    entry = normalize_entry(payload)
    data = load_dictionary(provider_name)
    validation = validate_entry(entry, data.get("entries") or [])
    _raise_on_validation(validation)
    data.setdefault("entries", []).append(entry)
    save_dictionary(data, provider_name)
    return entry, validation["warnings"]


def update_entry(entry_id: str, updates: dict, provider_name: str = "irodori-local") -> tuple[dict, list[dict]]:
    data = load_dictionary(provider_name)
    for index, entry in enumerate(data.setdefault("entries", [])):
        if str(entry.get("id")) == str(entry_id):
            updated = normalize_entry({**entry, **updates, "id": entry.get("id")})
            validation = validate_entry(updated, data["entries"], entry_id=entry_id)
            _raise_on_validation(validation)
            data["entries"][index] = updated
            save_dictionary(data, provider_name)
            return updated, validation["warnings"]
    raise KeyError(entry_id)



def delete_entry(entry_id: str, provider_name: str = "irodori-local") -> None:
    data = load_dictionary(provider_name)
    entries = data.setdefault("entries", [])
    data["entries"] = [e for e in entries if str(e.get("id")) != str(entry_id)]
    if len(data["entries"]) == len(entries):
        raise KeyError(entry_id)
    save_dictionary(data, provider_name)


def _patterns(entry: dict) -> list[str]:
    return [entry.get("surface", ""), *(entry.get("aliases") or [])]


def _matches(text: str, entry: dict) -> bool:
    flags = 0 if entry.get("case_sensitive") else re.IGNORECASE
    for pattern in _patterns(entry):
        try:
            if entry.get("match") == "regex" and re.search(pattern, text, flags): return True
            if entry.get("match") == "word" and re.search(r"(?<![A-Za-z0-9_])" + re.escape(pattern) + r"(?![A-Za-z0-9_])", text, flags): return True
            if entry.get("match", "literal") == "literal" and ((pattern in text) if entry.get("case_sensitive") else (pattern.casefold() in text.casefold())): return True
        except re.error:
            continue
    return False


def select_entries(provider_cfg: dict, original_text: str) -> list[dict]:
    cfg = provider_cfg.get("pronunciation_dictionary") or provider_cfg.get("dictionary") or {}
    if not isinstance(cfg, dict) or not cfg.get("enabled", False): return []
    entries = [normalize_entry(e) for e in (load_dictionary_entries(cfg) or []) if isinstance(e, dict) and e.get("enabled", True) and e.get("surface") and e.get("reading")]
    if cfg.get("only_if_present", True): entries = [e for e in entries if _matches(original_text, e)]
    return entries[:max(0, int(cfg.get("max_prompt_entries") or 40))]


def load_dictionary_entries(provider_cfg: dict) -> list[dict]:
    path = Path(str((provider_cfg.get("path") if isinstance(provider_cfg, dict) else None) or "~/.hermes/tts/irodori_pronunciation_dictionary.json")).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        return []
    return data.get("entries", []) if isinstance(data, dict) else data if isinstance(data, list) else []


def apply_entries(text: str, entries: list[dict]) -> tuple[str, list[dict]]:
    applied, result = [], text
    for entry in entries:
        if entry.get("mode") not in {"replace", "hint_and_replace"}: continue
        before = result; flags = 0 if entry.get("case_sensitive") else re.IGNORECASE
        for pattern in _patterns(entry):
            try:
                expr = pattern if entry.get("match") == "regex" else (r"(?<![A-Za-z0-9_])" + re.escape(pattern) + r"(?![A-Za-z0-9_])" if entry.get("match") == "word" else re.escape(pattern))
                result = re.sub(expr, entry["reading"], result, flags=flags)
            except re.error: continue
        if result != before: applied.append({"id": entry.get("id"), "surface": entry.get("surface"), "reading": entry.get("reading")})
    return result, applied


def prompt_block(entries: list[dict]) -> str:
    selected = [e for e in entries if e.get("mode") in {"hint", "hint_and_replace"}]
    if not selected: return ""
    lines = ["", "Pronunciation dictionary overrides:", "When these terms appear, these readings override the general rewrite rules."]
    for entry in selected:
        aliases = entry.get("aliases") or []
        label = entry["surface"] + (f" / aliases: {', '.join(aliases)}" if aliases else "")
        lines.append(f'- Read "{label}" as "{entry["reading"]}".')
    return "\n".join(lines)


def validate_dictionary(data: dict | None = None, provider_name: str = "irodori-local") -> dict:
    source = data if data is not None else load_dictionary(provider_name)
    entries = source.get("entries", []) if isinstance(source, dict) else []
    result = {"ok": True, "errors": [], "warnings": [], "info": []}
    normalized = [normalize_entry(item) for item in entries if isinstance(item, dict)]
    for index, entry in enumerate(normalized):
        current = validate_entry(entry, normalized, entry_id=entry.get("id"))
        for issue in current["errors"]:
            result["errors"].append({**issue, "entry_id": issue.get("entry_id", entry.get("id"))})
        for issue in current["warnings"]:
            result["warnings"].append({**issue, "entry_id": issue.get("entry_id", entry.get("id"))})
        if not entry.get("surface") or not entry.get("reading"):
            result["info"].append({"code": "entry_index", "entry_id": entry.get("id"), "message": f"entry index {index}"})
    result["ok"] = not result["errors"]
    return result


def preview_matches(text: str, provider_name: str = "irodori-local") -> dict:
    cfg = {"pronunciation_dictionary": dictionary_config(provider_name)}
    selected = select_entries(cfg, text); speech, applied = apply_entries(text, selected)
    return {"selected": selected, "applied": applied, "speech_text": speech}
