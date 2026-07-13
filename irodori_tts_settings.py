#!/usr/bin/env python3
"""Canonical, allowlisted settings and safe persistence for Irodori TTS."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import irodori_tts_config as _config

SCHEMA_VERSION = 1
_PROVIDER_PATH = ("tts", "providers", "irodori-local")

# This is the only client-editable surface.  Metadata is deliberately plain data
# so the future API/UI can serialize it without importing implementation details.
FIELD_SCHEMA = {
    "caption": {"path": "caption", "label": "声のキャプション", "description": "Irodori が目指す声の性質。", "type": "string", "max_length": 500, "apply": "next_request"},
    "ref_embed": {"path": "ref_embed", "label": "参照音声", "description": "登録済み voice asset から声質を選択します。", "type": "voice_asset", "apply": "next_request"},
    "seed": {"path": "seed", "label": "再現性", "description": "同じ条件で再現しやすくする固定値。", "type": "integer", "minimum": 0, "maximum": 2147483647, "apply": "next_request"},
    "num_steps": {"path": "num_steps", "label": "生成ステップ数", "description": "増やすと品質が上がる場合がありますが、生成時間も増えます。", "type": "integer", "minimum": 1, "maximum": 100, "apply": "next_request"},
    "t_schedule_mode": {"path": "t_schedule_mode", "label": "スケジュール方式", "description": "サンプリング時間の配分方式。", "type": "string", "max_length": 32, "enum": ["sway", "linear"], "apply": "next_request"},
    "sway_coeff": {"path": "sway_coeff", "label": "Sway 係数", "description": "Sway スケジュールの強さ。", "type": "number", "minimum": -10.0, "maximum": 10.0, "apply": "next_request"},
    "cfg_scale_text": {"path": "cfg_scale_text", "label": "テキスト追従度", "description": "入力テキストへの追従度。", "type": "number", "minimum": 0.0, "maximum": 20.0, "apply": "next_request"},
    "cfg_scale_caption": {"path": "cfg_scale_caption", "label": "キャプション追従度", "description": "声のキャプションへの追従度。", "type": "number", "minimum": 0.0, "maximum": 20.0, "apply": "next_request"},
    "cfg_scale_speaker": {"path": "cfg_scale_speaker", "label": "話者追従度", "description": "参照話者への追従度。", "type": "number", "minimum": 0.0, "maximum": 20.0, "apply": "next_request"},
    "chunking_enabled": {"path": "chunking_enabled", "label": "長文分割", "description": "長い文章を複数のチャンクに分けて生成します。", "type": "boolean", "apply": "next_request"},
    "chunk_min_chars": {"path": "chunk_min_chars", "label": "通常チャンクの最小文字数", "description": "通常チャンクの最小サイズ。", "type": "integer", "minimum": 1, "maximum": 10000, "apply": "next_request"},
    "first_sentence_chunk_min_chars": {"path": "first_sentence_chunk_min_chars", "label": "先頭チャンクの最小文字数", "description": "最初のチャンクの最小サイズ。", "type": "integer", "minimum": 1, "maximum": 10000, "apply": "next_request"},
    "rewrite.enabled": {"path": "rewrite.enabled", "label": "テキスト Rewrite", "description": "生成前に発音しやすい文章へ変換します。", "type": "boolean", "apply": "next_request"},
    "rewrite.model": {"path": "rewrite.model", "label": "Rewrite モデル", "description": "文章変換に使うモデル名。", "type": "string", "max_length": 200, "apply": "next_request"},
    "rewrite.fallback": {"path": "rewrite.fallback", "label": "Rewrite 失敗時", "description": "Rewrite に失敗した場合の処理。", "type": "string", "max_length": 32, "enum": ["original", "empty", "error"], "apply": "next_request"},
    "pronunciation_dictionary.enabled": {"path": "pronunciation_dictionary.enabled", "label": "発音辞書", "description": "登録した読み方を適用します。", "type": "boolean", "apply": "next_request"},
    "pronunciation_dictionary.max_prompt_entries": {"path": "pronunciation_dictionary.max_prompt_entries", "label": "辞書の最大適用数", "description": "Rewrite に渡す辞書項目の最大数。", "type": "integer", "minimum": 0, "maximum": 1000, "apply": "next_request"},
}

_READ_ONLY_KEYS = {"api_key", "token", "password", "secret", "credentials", "command", "path", "prompt", "server_workdir", "base_url", "model", "voice", "voices_dir"}
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ConfigStoreError(Exception):
    pass


class ConfigConflictError(ConfigStoreError):
    pass


def _yaml_module():
    module = _config.yaml
    if module is not None:
        return module
    loader = getattr(_config, "_load_yaml_module", None)
    module = loader() if callable(loader) else None
    if module is not None:
        return module
    default_hermes = Path("~/.hermes").expanduser()
    site_root = default_hermes / "hermes-agent" / "venv" / "lib"
    for site_packages in sorted(site_root.glob("python*/site-packages")):
        site_path = str(site_packages)
        if site_path not in os.sys.path:
            os.sys.path.insert(0, site_path)
        try:
            import yaml as yaml_module
            return yaml_module
        except Exception:
            continue
    return None


def schema() -> dict[str, Any]:
    fields = {}
    for key, value in FIELD_SCHEMA.items():
        metadata = dict(value)
        metadata["apply_scope"] = metadata.pop("apply")
        metadata["restart_required"] = metadata["apply_scope"] == "restart"
        fields[key] = metadata
    return {"schema_version": SCHEMA_VERSION, "fields": fields}


def _provider(root: dict[str, Any], create: bool = False) -> dict[str, Any]:
    tts = root.get("tts")
    providers = tts.get("providers") if isinstance(tts, dict) else None
    existing = providers.get("irodori-local") if isinstance(providers, dict) else None
    if isinstance(existing, dict):
        return existing
    if not create:
        return {}
    if tts is None:
        root["tts"] = tts = {}
    elif not isinstance(tts, dict):
        raise ConfigStoreError("config.yaml tts section must be a mapping.")
    if providers is None:
        tts["providers"] = providers = {}
    elif not isinstance(providers, dict):
        raise ConfigStoreError("config.yaml providers section must be a mapping.")
    if existing is not None:
        raise ConfigStoreError("config.yaml Irodori provider must be a mapping.")
    providers["irodori-local"] = {}
    return providers["irodori-local"]


def _get(provider: dict[str, Any], key: str) -> Any:
    value: Any = provider
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _set(provider: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    target = provider
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def read_values(root: dict[str, Any]) -> dict[str, Any]:
    provider = _provider(root)
    values = {key: _get(provider, meta["path"]) for key, meta in FIELD_SCHEMA.items()}
    if "ref_embed" in values:
        values["ref_embed"] = _voice_asset_id(values["ref_embed"], provider, _config.hermes_home())
    return values


def get_editable_values(root: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read only the canonical flat fields from a config mapping or disk."""
    if root is None:
        return ConfigStore().read_values()
    return read_values(root)


def validate_update(values: Any, *, provider: dict[str, Any] | None = None, home: Path | None = None) -> dict[str, list[dict[str, str]]]:
    return validate_values(values, provider=provider, home=home)




def _issue(bucket: list[dict[str, str]], field: str, message: str) -> None:
    bucket.append({"field": field, "message": message})


def _voice_roots(provider: dict[str, Any], home: Path) -> list[Path]:
    roots = []
    for key in ("voices_dir", "voice_dir", "voice_assets_dir", "voices_path"):
        candidate = provider.get(key)
        if isinstance(candidate, str) and candidate:
            roots.append(Path(candidate).expanduser())
    server_workdir = provider.get("server_workdir")
    if isinstance(server_workdir, str) and server_workdir:
        roots.append(Path(server_workdir).expanduser() / "voices")
    roots.extend((home / "tts" / "irodori" / "voices", home / "tts" / "voices", home / "voices"))
    return list(dict.fromkeys(path.resolve() for path in roots))


def _valid_voice_asset(value: Any, provider: dict[str, Any], home: Path) -> bool:
    if not isinstance(value, str) or not value or _CONTROL_RE.search(value):
        return False
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        for root in _voice_roots(provider, home):
            resolved = (root / candidate).resolve()
            if resolved.is_file() and resolved.is_relative_to(root):
                return True
        return False
    resolved = candidate.resolve()
    return any(resolved.is_file() and resolved.is_relative_to(root) for root in _voice_roots(provider, home))


def _voice_asset_id(value: Any, provider: dict[str, Any], home: Path) -> Any:
    if not isinstance(value, str) or not value:
        return value
    candidate = Path(value).expanduser().resolve()
    for root in _voice_roots(provider, home):
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            continue
    return value


def _voice_asset_path(value: Any, provider: dict[str, Any], home: Path) -> Any:
    if not isinstance(value, str) or not value:
        return value
    for root in _voice_roots(provider, home):
        candidate = (root / value).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return str(candidate)
    return value


def _configured_provider() -> dict[str, Any]:
    try:
        return _provider(ConfigStore()._load())
    except Exception:
        provider = _config.provider_config()
        return provider if isinstance(provider, dict) else {}


def list_voice_assets(provider: dict[str, Any] | None = None, home: Path | None = None) -> list[dict[str, str]]:
    """Return safe IDs for known voice files without exposing local paths."""
    home = home or _config.hermes_home()
    provider = provider if isinstance(provider, dict) else _configured_provider()
    allowed = {".safetensors", ".wav", ".flac", ".mp3", ".ogg", ".opus"}
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for root in _voice_roots(provider, home):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            try:
                relative = path.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            if relative in seen:
                continue
            seen.add(relative)
            result.append({"id": relative, "label": relative, "type": path.suffix.lower().lstrip(".")})
    return result


def validate_values(values: Any, *, provider: dict[str, Any] | None = None, home: Path | None = None) -> dict[str, list[dict[str, str]]]:
    result = {"errors": [], "warnings": [], "info": []}
    if not isinstance(values, dict):
        _issue(result["errors"], "*", "Settings must be a mapping.")
        return result
    provider = provider if isinstance(provider, dict) else _configured_provider()
    home = home or _config.hermes_home()
    for key, value in values.items():
        if key not in FIELD_SCHEMA:
            lower = str(key).lower()
            message = "Unknown or read-only setting." if lower in _READ_ONLY_KEYS or any(token in lower for token in _READ_ONLY_KEYS) else "Unknown setting."
            _issue(result["errors"], str(key), message)
            continue
        meta = FIELD_SCHEMA[key]
        kind = meta["type"]
        if isinstance(value, str) and _CONTROL_RE.search(value):
            _issue(result["errors"], key, "Control characters are not allowed.")
            continue
        if kind == "string":
            if not isinstance(value, str):
                _issue(result["errors"], key, "Expected a string.")
            elif "max_length" in meta and len(value) > meta["max_length"]:
                _issue(result["errors"], key, "Value exceeds the maximum length.")
            elif key.endswith("model") and ("/" in value or "\\" in value or any(char in value for char in ";|&$`<>")):
                _issue(result["errors"], key, "Model identifiers cannot contain paths or commands.")
        elif kind == "voice_asset":
            if not _valid_voice_asset(value, provider, home):
                _issue(result["errors"], key, "Reference voice must be an existing file under an Irodori voices directory.")
        elif kind == "boolean":
            if not isinstance(value, bool):
                _issue(result["errors"], key, "Expected a boolean.")
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                _issue(result["errors"], key, "Expected an integer.")
            elif not (meta["minimum"] <= value <= meta["maximum"]):
                _issue(result["errors"], key, "Value is outside the allowed range.")
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                _issue(result["errors"], key, "Expected a number.")
            elif not (meta["minimum"] <= value <= meta["maximum"]):
                _issue(result["errors"], key, "Value is outside the allowed range.")
        if "enum" in meta and value not in meta["enum"]:
            _issue(result["errors"], key, "Value is not an allowed option.")
    return result


def read_settings(path: Path | None = None) -> dict[str, Any]:
    store = ConfigStore(path=path)
    return {"schema_version": SCHEMA_VERSION, "values": store.read_values(), "revision": store.revision()}


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _config.hermes_home() / "config.yaml"
        self.lock_path = self.path.parent / (self.path.name + ".irodori.lock")
        self.backup_dir = _config.hermes_home() / "backups" / "irodori-config"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        yaml_module = _yaml_module()
        if yaml_module is None:
            raise ConfigStoreError("PyYAML is required to edit config.yaml.")
        try:
            data = yaml_module.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise ConfigStoreError("Unable to read config.yaml.") from exc
        if not isinstance(data, dict):
            raise ConfigStoreError("config.yaml root must be a mapping.")
        return data

    def read_values(self) -> dict[str, Any]:
        return read_values(self._load())

    def revision(self) -> str:
        if not self.path.exists():
            return "missing"
        stat = self.path.stat()
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return f"{stat.st_mtime_ns}:{stat.st_size}:{digest}"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 5
        fd = None
        while fd is None:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ConfigStoreError("Timed out acquiring config lock.")
                time.sleep(0.01)
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
            yield
        finally:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)

    def update(self, values: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        with self._lock():
            current_revision = self.revision()
            if expected_revision is not None and expected_revision != current_revision:
                raise ConfigConflictError("Configuration changed since it was read.")
            root = self._load()
            provider = _provider(root, create=True)
            validation = validate_values(values, provider=provider, home=_config.hermes_home())
            if validation["errors"]:
                return {"saved": False, "validation": validation, "revision": current_revision}
            for key, value in values.items():
                stored_value = value
                if key == "ref_embed":
                    stored_value = _voice_asset_path(value, provider, _config.hermes_home())
                _set(provider, FIELD_SCHEMA[key]["path"], stored_value)
            had_original = self.path.exists()
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup = self.backup_dir / f"config-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}.yaml"
            if had_original:
                backup.write_bytes(self.path.read_bytes())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            yaml_module = _yaml_module()
            if yaml_module is None:
                raise ConfigStoreError("PyYAML is required to edit config.yaml.")
            payload = yaml_module.safe_dump(root, sort_keys=False, allow_unicode=True)
            fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except Exception:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                raise
            reloaded = self._load()
            post_validation = validate_values(values, provider=_provider(reloaded), home=_config.hermes_home())
            if post_validation["errors"] or read_values(reloaded) != {**read_values(root), **{}}:
                raise ConfigStoreError("Saved configuration failed post-write validation.")
            return {"saved": True, "backup": str(backup) if had_original else None, "values": read_values(reloaded), "revision": self.revision(), "validation": {"errors": [], "warnings": [], "info": [{"field": key, "message": "Saved."} for key in values]}}
