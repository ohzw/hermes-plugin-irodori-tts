from __future__ import annotations

import argparse
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_plugin_module():
    spec = importlib.util.spec_from_file_location(
        "hermes_irodori_plugin",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeContext:
    def __init__(self):
        self.providers = []
        self.cli_commands = []

    def register_tts_provider(self, provider):
        self.providers.append(provider)

    def register_cli_command(self, **kwargs):
        self.cli_commands.append(kwargs)


class PluginIntegrationTests(unittest.TestCase):
    def test_plugin_loads_when_its_directory_is_not_the_working_directory(self):
        original_cwd = Path.cwd()
        original_path = list(sys.path)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                sys.path[:] = [item for item in sys.path if Path(item or original_cwd) != ROOT]
                plugin = load_plugin_module()
            finally:
                os.chdir(original_cwd)
                sys.path[:] = original_path

        self.assertEqual("irodori-local", plugin.IrodoriTTSProvider().name)

    def test_register_exposes_tts_provider_and_cli(self):
        plugin = load_plugin_module()
        ctx = FakeContext()

        plugin.register(ctx)

        self.assertEqual(["irodori-local"], [p.name for p in ctx.providers])
        self.assertEqual(["irodori"], [c["name"] for c in ctx.cli_commands])

    def test_dashboard_cli_exposes_lifecycle_subcommands(self):
        plugin = load_plugin_module()
        parser = argparse.ArgumentParser()
        plugin._setup_cli(parser)
        for action in ("start", "open", "status", "stop"):
            args = parser.parse_args(["dashboard", action])
            self.assertEqual("dashboard", args.irodori_command)
            self.assertEqual(action, args.dashboard_command)

        output = io.StringIO()
        with mock.patch(
            "irodori_tts_dashboard_server.dashboard_status",
            return_value={"running": False, "url": "http://127.0.0.1:9120/workspace", "pid": None},
        ), redirect_stdout(output):
            plugin._run_cli(parser.parse_args(["dashboard", "status"]))
        self.assertIn("running: false", output.getvalue())

    def test_provider_delegates_to_shared_synthesis_module(self):
        plugin = load_plugin_module()
        provider = plugin.IrodoriTTSProvider()
        expected = {
            "status": "ok",
            "output_path": "/tmp/result.mp3",
            "error": None,
        }

        with mock.patch.object(plugin, "synthesize_text", return_value=expected) as synthesize:
            result = provider.synthesize(
                "こんにちは",
                "/tmp/result.mp3",
                voice="voice-a",
                model="irodori-tts",
                speed=1.0,
                format="mp3",
            )

        self.assertEqual("/tmp/result.mp3", result)
        synthesize.assert_called_once_with(
            "こんにちは",
            Path("/tmp/result.mp3"),
            provider_name="irodori-local",
            output_format="mp3",
        )

    def test_provider_raises_when_synthesis_fails(self):
        plugin = load_plugin_module()
        provider = plugin.IrodoriTTSProvider()

        with mock.patch.object(
            plugin,
            "synthesize_text",
            return_value={"status": "error", "error": "server unavailable"},
        ):
            with self.assertRaisesRegex(RuntimeError, "server unavailable"):
                provider.synthesize("こんにちは", "/tmp/result.mp3")

    def test_setup_migrates_command_provider_without_losing_user_settings(self):
        plugin = load_plugin_module()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                "tts:\n"
                "  provider: edge\n"
                "  providers:\n"
                "    irodori-local:\n"
                "      type: command\n"
                "      command: /old/irodori_tts_request.py --input {input_path}\n"
                "      caption: やさしい声\n"
                "      num_steps: 8\n",
                encoding="utf-8",
            )

            result = plugin.configure_plugin(config_path)
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            backup = config_path.with_suffix(config_path.suffix + ".irodori-backup")
            backup_exists = backup.exists()
            backup_text = backup.read_text(encoding="utf-8") if backup_exists else ""

        provider = config["tts"]["providers"]["irodori-local"]
        self.assertTrue(result["changed"])
        self.assertEqual("irodori-local", config["tts"]["provider"])
        self.assertNotIn("type", provider)
        self.assertNotIn("command", provider)
        self.assertEqual("やさしい声", provider["caption"])
        self.assertEqual(8, provider["num_steps"])
        self.assertTrue(backup_exists)
        self.assertIn("type: command", backup_text)

    def test_setup_accepts_portable_server_location_and_base_url(self):
        plugin = load_plugin_module()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            server_path = Path(tmp) / "Irodori-TTS-Server"

            plugin.configure_plugin(
                config_path,
                server_workdir=server_path,
                base_url="http://127.0.0.1:9000/v1",
            )
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        provider = config["tts"]["providers"]["irodori-local"]
        self.assertEqual(str(server_path), provider["server_workdir"])
        self.assertEqual("http://127.0.0.1:9000/v1", provider["base_url"])


if __name__ == "__main__":
    unittest.main()
