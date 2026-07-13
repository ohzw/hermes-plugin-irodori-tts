"""Hermes plugin registration for the local Irodori TTS integration."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from agent.tts_provider import TTSProvider

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from irodori_tts_config import hermes_home, provider_config
from irodori_tts_core import synthesize_text
from irodori_tts_dashboard_service import get_public_status


PROVIDER_NAME = "irodori-local"


class IrodoriTTSProvider(TTSProvider):
    """Expose the existing Irodori synthesis pipeline through Hermes' TTS seam."""

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Irodori TTS (Local)"

    @property
    def voice_compatible(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[dict[str, Any]]:
        cfg = provider_config(PROVIDER_NAME)
        model = str(cfg.get("model") or "irodori-tts")
        return [{"id": model, "display": model, "languages": ["ja"]}]

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "local",
            "tag": "Japanese expressive TTS via Irodori-TTS-Server",
            "env_vars": [],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: str | None = None,
        model: str | None = None,
        speed: float | None = None,
        format: str = "mp3",
        **extra: Any,
    ) -> str:
        del voice, model, speed, extra
        result = synthesize_text(
            text,
            Path(output_path),
            provider_name=PROVIDER_NAME,
            output_format=format,
        )
        if result.get("status") != "ok":
            raise RuntimeError(str(result.get("error") or "Irodori TTS synthesis failed"))
        return str(result.get("output_path") or output_path)


def configure_plugin(
    config_path: Path | None = None,
    *,
    server_workdir: Path | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Select the plugin provider and migrate a legacy command-provider entry.

    User-owned Irodori settings are preserved. Only the command-provider marker
    and its install-specific command path are removed so Hermes can dispatch to
    the Python provider registered by this plugin.
    """

    path = Path(config_path) if config_path else hermes_home() / "config.yaml"
    root: dict[str, Any] = {}
    existed = path.exists()
    if existed:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Hermes config root must be a mapping")
        root = loaded

    tts = root.setdefault("tts", {})
    if not isinstance(tts, dict):
        raise ValueError("Hermes tts config must be a mapping")
    providers = tts.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("Hermes tts.providers config must be a mapping")
    provider = providers.setdefault(PROVIDER_NAME, {})
    if not isinstance(provider, dict):
        raise ValueError(f"Hermes provider {PROVIDER_NAME!r} must be a mapping")

    before = yaml.safe_dump(root, sort_keys=False, allow_unicode=True)
    provider.pop("type", None)
    provider.pop("command", None)
    if server_workdir is not None:
        provider["server_workdir"] = str(Path(server_workdir).expanduser())
    if base_url is not None:
        provider["base_url"] = base_url.rstrip("/")
    tts["provider"] = PROVIDER_NAME
    after = yaml.safe_dump(root, sort_keys=False, allow_unicode=True)
    changed = before != after or not path.exists()

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup = path.with_suffix(path.suffix + ".irodori-backup")
            if not backup.exists():
                shutil.copy2(path, backup)
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    return {"changed": changed, "config_path": str(path), "provider": PROVIDER_NAME}


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="irodori_command")
    setup = subcommands.add_parser("setup", help="Activate the Irodori Python TTS provider")
    setup.add_argument(
        "--server-workdir",
        type=Path,
        help="Path to an Irodori-TTS-Server checkout",
    )
    setup.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible Irodori endpoint (default: preserve current config)",
    )
    subcommands.add_parser("status", help="Show Irodori TTS status")
    dashboard = subcommands.add_parser("dashboard", help="Manage the standalone Irodori dashboard")
    dashboard_commands = dashboard.add_subparsers(dest="dashboard_command")
    dashboard_commands.add_parser("start", help="Start the dashboard in the background")
    dashboard_commands.add_parser("open", help="Start if needed and open the dashboard")
    dashboard_commands.add_parser("status", help="Show dashboard process status")
    dashboard_commands.add_parser("stop", help="Stop the dashboard process")


def _run_cli(args: argparse.Namespace) -> None:
    command = getattr(args, "irodori_command", None)
    if command == "setup":
        result = configure_plugin(
            server_workdir=getattr(args, "server_workdir", None),
            base_url=getattr(args, "base_url", None),
        )
        action = "updated" if result["changed"] else "already configured"
        print(f"Irodori TTS {action}: {result['config_path']}")
        print("Restart Hermes so the provider change takes effect.")
        return
    if command == "status":
        status = get_public_status(limit=5)
        print(yaml.safe_dump(status, sort_keys=False, allow_unicode=True).rstrip())
        return
    if command == "dashboard":
        from irodori_tts_dashboard_server import (
            dashboard_status,
            open_dashboard,
            start_dashboard,
            stop_dashboard,
        )

        action = getattr(args, "dashboard_command", None) or "open"
        if action == "start":
            result = start_dashboard()
        elif action == "stop":
            result = stop_dashboard()
        elif action == "status":
            result = dashboard_status()
        else:
            result = open_dashboard(start=True)
        print(yaml.safe_dump(result, sort_keys=False, allow_unicode=True).rstrip())
        return
    print("Usage: hermes irodori <setup|status|dashboard>")


def register(ctx: Any) -> None:
    ctx.register_tts_provider(IrodoriTTSProvider())
    ctx.register_cli_command(
        name="irodori",
        help="Configure and inspect the Irodori TTS plugin",
        setup_fn=_setup_cli,
        handler_fn=_run_cli,
    )
