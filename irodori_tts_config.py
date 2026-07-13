#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _load_yaml_module():
    try:
        import yaml as yaml_module
        return yaml_module
    except Exception:
        pass
    hermes = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    site_root = hermes / "hermes-agent" / "venv" / "lib"
    for site_packages in sorted(site_root.glob("python*/site-packages")):
        site_path = str(site_packages)
        if site_path not in sys.path:
            sys.path.insert(0, site_path)
        try:
            import yaml as yaml_module
            return yaml_module
        except Exception:
            continue
    return None


yaml = _load_yaml_module()

_DEFAULT_DICTIONARY_PATH = "~/.hermes/tts/irodori_pronunciation_dictionary.json"


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def load_config() -> dict:
    path = hermes_home() / "config.yaml"
    if yaml is None or not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def provider_config(provider_name: str = "irodori-local") -> dict:
    cfg = load_config()
    tts = cfg.get("tts") or {}
    providers = tts.get("providers") or {}
    provider = providers.get(provider_name) or tts.get(provider_name) or {}
    return provider if isinstance(provider, dict) else {}


def dictionary_config(provider_name: str = "irodori-local") -> dict:
    provider = provider_config(provider_name)
    cfg = provider.get("pronunciation_dictionary") or provider.get("dictionary") or {}
    return cfg if isinstance(cfg, dict) else {}


def dictionary_path(provider_name: str = "irodori-local") -> Path:
    cfg = dictionary_config(provider_name)
    return Path(str(cfg.get("path") or _DEFAULT_DICTIONARY_PATH)).expanduser()


def _item(key: str, label: str, value: Any, *, source: str = "config", help_text: str = "") -> dict:
    item = {"key": key, "label": label, "value": value, "source": source}
    if help_text:
        item["help"] = help_text
    return item


def _group(group_id: str, title: str, items: list[dict]) -> dict:
    return {"id": group_id, "title": title, "items": items}


def safe_config_view(provider_name: str = "irodori-local") -> dict:
    """Return the explicitly allowlisted, read-only provider configuration view.

    This intentionally does not recursively serialize provider_config(). Any new
    config field must be opted into here, which prevents credentials, tokens,
    environment-backed values, commands, and prompts from reaching the dashboard.
    """
    provider = provider_config(provider_name)
    rewrite = provider.get("rewrite") if isinstance(provider.get("rewrite"), dict) else {}
    dictionary = dictionary_config(provider_name)
    metrics = provider.get("metrics") if isinstance(provider.get("metrics"), dict) else {}
    audio_history = provider.get("audio_history") if isinstance(provider.get("audio_history"), dict) else {}
    dashboard = provider.get("dashboard") if isinstance(provider.get("dashboard"), dict) else {}
    if not audio_history and isinstance(dashboard.get("audio_history"), dict):
        audio_history = dashboard["audio_history"]

    def audio_history_value(nested_key: str, flat_key: str, default: Any) -> Any:
        if nested_key in audio_history:
            return audio_history.get(nested_key)
        if flat_key in provider:
            return provider.get(flat_key)
        if flat_key in dashboard:
            return dashboard.get(flat_key)
        return default
    audio_history_max_bytes = audio_history.get("max_bytes", audio_history.get("max_total_bytes"))
    if audio_history_max_bytes is None:
        audio_history_max_bytes = provider.get("audio_history_max_bytes", dashboard.get("audio_history_max_bytes", 524288000))

    dictionary_file = dictionary_path(provider_name)
    warnings = []
    if not dictionary_file.exists():
        warnings.append("Pronunciation dictionary path does not exist.")
    if dictionary.get("enabled") is False:
        warnings.append("Pronunciation dictionary is disabled.")
    groups = [
        _group("server-health", "Server / Health", [
            _item("provider_name", "Provider", provider_name, help_text="Configured TTS provider."),
            _item("type", "Type", provider.get("type"), help_text="Provider integration type."),
            _item("base_url", "Base URL", provider.get("base_url"), help_text="Local Irodori-compatible API endpoint."),
            _item("timeout", "Provider timeout (s)", provider.get("timeout"), help_text="Maximum command-provider duration."),
            _item("request_timeout", "Request timeout (s)", provider.get("request_timeout"), help_text="Maximum individual request duration."),
            _item("auto_start_server", "Auto-start server", provider.get("auto_start_server"), help_text="Start the local server when it is unavailable."),
            _item("restart_on_error", "Restart on error", provider.get("restart_on_error"), help_text="Retry after a restartable server error."),
            _item("request_attempts", "Request attempts", provider.get("request_attempts"), help_text="Maximum request attempts."),
        ]),
        _group("tts-model-voice", "TTS Model / Voice", [
            _item("model", "Model", provider.get("model")),
            _item("voice", "Voice", provider.get("voice")),
            _item("output_format", "Output format", provider.get("output_format")),
            _item("voice_compatible", "Voice compatible", provider.get("voice_compatible")),
            _item("max_text_length", "Maximum text length", provider.get("max_text_length")),
            _item("caption", "Voice caption", provider.get("caption"), help_text="Description passed to the voice model."),
        ]),
        _group("rewrite", "Rewrite", [
            _item("enabled", "Enabled", rewrite.get("enabled")),
            _item("task", "Task", rewrite.get("task")),
            _item("provider", "Provider", rewrite.get("provider")),
            _item("model", "Model", rewrite.get("model")),
            _item("timeout", "Timeout (s)", rewrite.get("timeout")),
            _item("max_input_chars", "Maximum input characters", rewrite.get("max_input_chars")),
            _item("max_output_chars", "Maximum output characters", rewrite.get("max_output_chars")),
            _item("max_tokens", "Maximum tokens", rewrite.get("max_tokens")),
            _item("temperature", "Temperature", rewrite.get("temperature")),
            _item("fallback", "Fallback", rewrite.get("fallback")),
            _item("debug_save", "Debug save", rewrite.get("debug_save")),
        ]),
        _group("pronunciation-dictionary", "Pronunciation Dictionary", [
            _item("enabled", "Enabled", dictionary.get("enabled")),
            _item("path", "Dictionary path", str(dictionary_file), source="config/default", help_text="Resolved local dictionary file."),
            _item("path_exists", "Path exists", dictionary_file.exists(), source="runtime"),
            _item("apply_to_prompt", "Prompt hints", dictionary.get("apply_to_prompt"), help_text="Apply dictionary readings before rewrite."),
            _item("apply_post_rewrite", "Post-rewrite replacement", dictionary.get("apply_post_rewrite"), help_text="Apply dictionary readings after rewrite."),
            _item("only_if_present", "Only if present", dictionary.get("only_if_present")),
            _item("max_prompt_entries", "Maximum prompt entries", dictionary.get("max_prompt_entries")),
        ]),
        _group("chunking", "Chunking", [
            _item("chunking_enabled", "Enabled", provider.get("chunking_enabled")),
            _item("chunk_min_chars", "Minimum chunk characters", provider.get("chunk_min_chars")),
            _item("first_sentence_chunk_min_chars", "First sentence minimum", provider.get("first_sentence_chunk_min_chars")),
        ]),
        _group("sampling-seed", "Sampling / Seed", [
            _item("num_steps", "Number of steps", provider.get("num_steps")),
            _item("t_schedule_mode", "Schedule mode", provider.get("t_schedule_mode")),
            _item("sway_coeff", "Sway coefficient", provider.get("sway_coeff")),
            _item("cfg_scale_text", "Text CFG scale", provider.get("cfg_scale_text")),
            _item("cfg_scale_caption", "Caption CFG scale", provider.get("cfg_scale_caption")),
            _item("cfg_scale_speaker", "Speaker CFG scale", provider.get("cfg_scale_speaker")),
            _item("seed", "Seed", provider.get("seed"), help_text="Fixed seed when deterministic output is desired."),
        ]),
        _group("metrics-logs", "Metrics / Logs", [
            _item("enabled", "Metrics enabled", metrics.get("enabled"), help_text="Write timing records."),
            _item("slow_threshold_ms", "Slow threshold (ms)", metrics.get("slow_threshold_ms")),
            _item("server_log", "Server log", provider.get("server_log"), source="config/default"),
            _item("debug_save", "Rewrite debug save", rewrite.get("debug_save")),
        ]),
        _group("audio-history", "Audio History / Privacy", [
            _item("enabled", "Audio history enabled", audio_history_value("enabled", "audio_history_enabled", True), help_text="Generated audio is stored locally for dashboard history; disable via Hermes config."),
            _item("max_entries", "Maximum entries", audio_history_value("max_entries", "audio_history_max_entries", 50)),
            _item("max_bytes", "Maximum bytes", audio_history_max_bytes),
            _item("preview_max_chars", "Preview characters", audio_history_value("preview_max_chars", "preview_max_chars", 240)),
            _item("storage_note", "Storage", "Generated audio and capped previews are stored locally.", source="runtime", help_text="Stored under the Hermes logs directory; no local path is exposed here. Disable via config; this dashboard does not edit config."),
        ]),
        _group("paths", "Paths", [
            _item("dictionary_path", "Dictionary", str(dictionary_file), source="config/default"),
            _item("ref_embed", "Reference embedding", provider.get("ref_embed")),
            _item("server_workdir", "Server working directory", provider.get("server_workdir")),
            _item("rewrite_debug_dir", "Rewrite debug directory", rewrite.get("debug_dir")),
        ]),
    ]
    return {"groups": groups, "warnings": warnings}
