import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import irodori_tts_config as config


class ConfigTests(unittest.TestCase):
    def test_missing_config_and_default_dictionary_path(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            self.assertEqual(config.load_config(), {})
            self.assertEqual(config.dictionary_path(), Path("~/.hermes/tts/irodori_pronunciation_dictionary.json").expanduser())

    def test_provider_and_safe_view(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            Path(home, "config.yaml").write_text("tts:\n  providers:\n    irodori-local:\n      model: test\n      api_key: secret\n", encoding="utf-8")
            self.assertEqual(config.provider_config()["model"], "test")
            view = config.safe_config_view()
            self.assertNotIn("api_key", view)

    def test_audio_history_defaults_are_safe_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            view = config.safe_config_view()
            group = next(group for group in view["groups"] if group["id"] == "audio-history")
            values = {item["key"]: item["value"] for item in group["items"]}
            self.assertEqual(values["enabled"], True)
            self.assertEqual(values["max_entries"], 50)
            self.assertEqual(values["max_bytes"], 524288000)
            self.assertEqual(values["preview_max_chars"], 240)
            self.assertNotIn("~/.hermes/logs", repr(view))

    def test_audio_history_dashboard_flat_keys_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            Path(home, "config.yaml").write_text(
                "tts:\n  providers:\n    irodori-local:\n      dashboard:\n"
                "        audio_history_enabled: false\n"
                "        audio_history_max_entries: 12\n"
                "        audio_history_max_bytes: 13\n"
                "        preview_max_chars: 14\n",
                encoding="utf-8",
            )
            view = config.safe_config_view()
            group = next(group for group in view["groups"] if group["id"] == "audio-history")
            values = {item["key"]: item["value"] for item in group["items"]}
            self.assertEqual(values["enabled"], False)
            self.assertEqual(values["max_entries"], 12)
            self.assertEqual(values["max_bytes"], 13)
            self.assertEqual(values["preview_max_chars"], 14)

    def test_safe_view_is_grouped_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            Path(home, "config.yaml").write_text(
                "tts:\n  providers:\n    irodori-local:\n"
                "      model: test-model\n      api_key: do-not-show\n      token: do-not-show\n"
                "      rewrite:\n        enabled: true\n        model: rewrite-model\n"
                "      pronunciation_dictionary:\n        enabled: false\n",
                encoding="utf-8",
            )
            view = config.safe_config_view()
            self.assertEqual(
                [group["title"] for group in view["groups"]],
                ["Server / Health", "TTS Model / Voice", "Rewrite", "Pronunciation Dictionary",
                 "Chunking", "Sampling / Seed", "Metrics / Logs", "Audio History / Privacy", "Paths"],
            )
            items = [item for group in view["groups"] for item in group["items"]]
            self.assertTrue(all({"key", "label", "value", "source"} <= item.keys() for item in items))
            serialized = repr(view)
            self.assertNotIn("do-not-show", serialized)
            forbidden = {"api_key", "token", "authorization", "password", "secret", "credentials"}
            keys = []
            def collect_keys(value):
                if isinstance(value, dict):
                    keys.extend(str(key).lower() for key in value.keys())
                    for nested in value.values():
                        collect_keys(nested)
                elif isinstance(value, list):
                    for nested in value:
                        collect_keys(nested)
            collect_keys(view)
            self.assertTrue(forbidden.isdisjoint(keys), keys)


if __name__ == "__main__": unittest.main()
