import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import irodori_tts_settings as settings


class SettingsTests(unittest.TestCase):
    def _config(self, home, text):
        Path(home, "config.yaml").write_text(text, encoding="utf-8")

    def test_successful_update_preserves_unknown_settings_and_reloads(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            self._config(home, "server:\n  secret: keep\ntts:\n  providers:\n    irodori-local:\n      model: keep-model\n      caption: old\n")
            store = settings.ConfigStore()
            result = store.update({"caption": "new", "num_steps": 12}, store.revision())
            self.assertTrue(result["saved"])
            self.assertEqual(store.read_values()["caption"], "new")
            self.assertEqual(store.read_values()["num_steps"], 12)
            text = Path(home, "config.yaml").read_text(encoding="utf-8")
            self.assertIn("secret: keep", text)
            self.assertIn("model: keep-model", text)

    def test_schema_and_unknown_read_only_secret_command_path_prompt_rejected(self):
        self.assertEqual(settings.schema()["schema_version"], 1)
        result = settings.validate_values({"api_key": "secret", "command": "rm -rf /", "path": "/tmp/x", "prompt": "x", "nope": 1})
        self.assertEqual({item["field"] for item in result["errors"]}, {"api_key", "command", "path", "prompt", "nope"})

    def test_range_type_enum_and_control_character_rejected(self):
        result = settings.validate_values({
            "num_steps": 0,
            "seed": -1,
            "t_schedule_mode": "shell",
            "caption": "bad\x00caption",
            "chunking_enabled": "true",
        })
        fields = {item["field"] for item in result["errors"]}
        self.assertEqual(fields, {"num_steps", "seed", "t_schedule_mode", "caption", "chunking_enabled"})

    def test_spoken_summary_policy_is_editable_and_validated(self):
        fields = settings.schema()["fields"]
        self.assertEqual(fields["rewrite.summary.enabled"]["apply_scope"], "next_request")
        self.assertEqual(fields["rewrite.summary.trigger_chars"]["minimum"], 1)
        self.assertEqual(fields["rewrite.summary.target_chars"]["maximum"], 4000)

        invalid = settings.validate_values({
            "rewrite.summary.enabled": "true",
            "rewrite.summary.trigger_chars": 0,
            "rewrite.summary.target_chars": 4001,
            "rewrite.summary.max_chars": 0,
            "rewrite.summary.max_input_chars": 0,
        })
        self.assertEqual(
            {item["field"] for item in invalid["errors"]},
            {
                "rewrite.summary.enabled",
                "rewrite.summary.trigger_chars",
                "rewrite.summary.target_chars",
                "rewrite.summary.max_chars",
                "rewrite.summary.max_input_chars",
            },
        )
        inconsistent = settings.validate_values({
            "rewrite.summary.target_chars": 500,
            "rewrite.summary.max_chars": 400,
        })
        self.assertEqual(
            {item["field"] for item in inconsistent["errors"]},
            {"rewrite.summary.max_chars"},
        )

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            self._config(home, "tts:\n  providers:\n    irodori-local:\n      rewrite:\n        enabled: true\n")
            store = settings.ConfigStore()
            defaults = store.read_values()
            self.assertTrue(defaults["rewrite.summary.enabled"])
            self.assertEqual(defaults["rewrite.summary.trigger_chars"], 1200)
            self.assertEqual(defaults["rewrite.summary.target_chars"], 350)
            self.assertEqual(defaults["rewrite.summary.max_chars"], 400)
            self.assertEqual(defaults["rewrite.summary.max_input_chars"], 16000)
            result = store.update({
                "rewrite.summary.enabled": True,
                "rewrite.summary.trigger_chars": 1200,
                "rewrite.summary.target_chars": 350,
                "rewrite.summary.max_chars": 400,
                "rewrite.summary.max_input_chars": 16000,
            })
            values = store.read_values()

        self.assertTrue(result["saved"])
        self.assertTrue(values["rewrite.summary.enabled"])
        self.assertEqual(values["rewrite.summary.target_chars"], 350)

    def test_known_voice_asset_is_allowed_but_arbitrary_path_is_not(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            voices = Path(home, "voices")
            voices.mkdir()
            asset = voices / "alto.safetensors"
            asset.write_bytes(b"asset")
            provider = {"voices_dir": str(voices)}
            self.assertFalse(settings.validate_values({"ref_embed": "/tmp/not-allowed"}, provider=provider, home=Path(home))["errors"] == [])
            self.assertFalse(settings.validate_values({"ref_embed": "alto.safetensors"}, provider=provider, home=Path(home))["errors"])

    def test_reference_audio_schema_and_import_use_a_managed_audio_file(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            voices = Path(home, "voices")
            provider = {"voices_dir": str(voices)}
            wav = b"RIFF\x04\x00\x00\x00WAVE"

            self.assertEqual(settings.schema()["fields"]["ref_wav"]["type"], "file")
            imported = settings.import_reference_audio("sample.wav", wav, provider=provider, home=Path(home))

            self.assertEqual(imported["id"], "sample.wav")
            self.assertEqual((voices / "sample.wav").read_bytes(), wav)
            self.assertFalse(settings.validate_values({"ref_wav": "sample.wav"}, provider=provider, home=Path(home))["errors"])

            with self.assertRaises(settings.VoiceAssetImportError):
                settings.import_reference_audio("../outside.wav", wav, provider=provider, home=Path(home))
            with self.assertRaises(settings.VoiceAssetImportError):
                settings.import_reference_audio("fake.wav", b"not-wave", provider=provider, home=Path(home))

    def test_voice_asset_id_is_public_but_config_keeps_resolved_path(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            voices = Path(home, "voices")
            voices.mkdir()
            asset = voices / "alto.safetensors"
            asset.write_bytes(b"asset")
            self._config(home, f"tts:\n  providers:\n    irodori-local:\n      voices_dir: {voices}\n")
            result = settings.ConfigStore().update({"ref_embed": "alto.safetensors"})
            self.assertTrue(result["saved"])
            self.assertEqual(settings.ConfigStore().read_values()["ref_embed"], "alto.safetensors")
            self.assertIn(str(asset), Path(home, "config.yaml").read_text(encoding="utf-8"))
            self.assertNotIn(str(asset), repr(settings.ConfigStore().read_values()))

    def test_stale_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            self._config(home, "tts:\n  providers:\n    irodori-local:\n      caption: old\n")
            store = settings.ConfigStore()
            revision = store.revision()
            Path(home, "config.yaml").write_text("tts:\n  providers:\n    irodori-local:\n      caption: changed\n", encoding="utf-8")
            with self.assertRaises(settings.ConfigConflictError):
                store.update({"caption": "new"}, revision)

    def test_backup_and_post_write_reload(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            self._config(home, "tts:\n  providers:\n    irodori-local:\n      caption: old\n")
            result = settings.ConfigStore().update({"caption": "new"})
            backups = list((Path(home) / "backups" / "irodori-config").glob("*.yaml"))
            self.assertTrue(result["saved"])
            self.assertEqual(len(backups), 1)
            self.assertIn("caption: old", backups[0].read_text(encoding="utf-8"))
            self.assertEqual(settings.ConfigStore().read_values()["caption"], "new")

    def test_atomic_failure_keeps_original_config(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HERMES_HOME": home}, clear=False):
            original = "tts:\n  providers:\n    irodori-local:\n      caption: old\n"
            self._config(home, original)
            with patch("irodori_tts_settings.os.replace", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    settings.ConfigStore().update({"caption": "new"})
            self.assertEqual(Path(home, "config.yaml").read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
