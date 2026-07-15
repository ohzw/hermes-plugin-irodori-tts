import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from irodori_tts_core import rewrite_preview, synthesize_text


class CoreTests(unittest.TestCase):
    def test_rewrite_preview_preserves_input_and_shape_without_llm(self):
        with patch("irodori_tts_config.provider_config", return_value={"rewrite": {"enabled": True}}):
            result = rewrite_preview("hello", call_llm=False)
        self.assertEqual(result["input"], "hello")
        self.assertEqual(result["speech_text"], "hello")
        self.assertIn("rewrite", result)
        self.assertIn("dictionary", result)


    def test_no_llm_still_matches_and_applies_dictionary(self):
        with tempfile.TemporaryDirectory() as tmp:
            dictionary_path = Path(tmp) / "dictionary.json"
            dictionary_path.write_text(json.dumps({
                "version": 1,
                "entries": [{
                    "id": "github",
                    "surface": "GitHub",
                    "reading": "ギットハブ",
                    "mode": "replace",
                    "enabled": True,
                }],
            }), encoding="utf-8")
            config = {
                "rewrite": {"enabled": True},
                "pronunciation_dictionary": {
                    "enabled": True,
                    "path": str(dictionary_path),
                    "only_if_present": True,
                },
            }
            with patch("irodori_tts_config.provider_config", return_value=config):
                result = rewrite_preview("GitHub", call_llm=False)
        self.assertEqual(result["speech_text"], "ギットハブ")
        self.assertEqual(result["dictionary"]["selected_count"], 1)
        self.assertEqual(result["dictionary"]["selected"][0]["id"], "github")
        self.assertEqual(result["dictionary"]["applied"][0]["reading"], "ギットハブ")

    def test_dictionary_can_be_disabled_for_preview(self):
        config = {
            "rewrite": {"enabled": False},
            "pronunciation_dictionary": {"enabled": True},
        }
        with patch("irodori_tts_config.provider_config", return_value=config):
            result = rewrite_preview("GitHub", call_llm=False, apply_dictionary=False)
        self.assertFalse(result["dictionary"]["enabled"])
        self.assertEqual(result["dictionary"]["selected"], [])

    def test_synthesize_text_sends_provider_irodori_options(self):
        config = {
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "irodori-tts",
            "voice": "none",
            "speed": "1.25",
            "request_timeout": 1,
            "request_attempts": 1,
            "caption": "明るい声",
            "ref_embed": "/tmp/voice.safetensors",
            "num_steps": "8",
            "t_schedule_mode": "sway",
            "sway_coeff": "-1",
            "cfg_scale_text": "3",
            "cfg_scale_caption": "4.5",
            "cfg_scale_speaker": "5",
            "chunking_enabled": "false",
            "chunk_min_chars": "80",
            "first_sentence_chunk_min_chars": "81",
            "max_caption_len": "120",
            "seed": "1234",
        }
        captured = {}

        def fake_request(base_url, payload, api_key, timeout):
            captured["base_url"] = base_url
            captured["payload"] = payload
            return b"audio"

        with tempfile.TemporaryDirectory() as tmp, \
             patch("irodori_tts_config.provider_config", return_value=config), \
             patch("irodori_tts_core.rewrite_preview", return_value={
                 "speech_text": "読み上げ本文",
                 "rewrite": {"elapsed_ms": 0, "enabled": False, "changed": False, "provider": None, "model": None, "error": None},
                 "dictionary": {"enabled": False, "selected": [], "selected_count": 0, "applied": [], "warnings": []},
             }), \
             patch("irodori_tts_request._start_server"), \
             patch("irodori_tts_request._request_speech", side_effect=fake_request), \
             patch("irodori_tts_history.record_audio") as record_audio:
            result = synthesize_text(
                "input",
                Path(tmp) / "out.mp3",
                call_llm=False,
                output_format="mp3",
                save_history=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["audio_id"])
        self.assertIsNone(result["url"])
        record_audio.assert_not_called()
        payload = captured["payload"]
        self.assertEqual(payload["input"], "読み上げ本文")
        self.assertEqual(payload["speed"], 1.25)
        self.assertEqual(payload["response_format"], "mp3")
        self.assertEqual(payload["irodori"], {
            "chunking_enabled": False,
            "caption": "明るい声",
            "ref_embed": "/tmp/voice.safetensors",
            "num_steps": 8,
            "t_schedule_mode": "sway",
            "sway_coeff": -1.0,
            "cfg_scale_text": 3.0,
            "cfg_scale_caption": 4.5,
            "cfg_scale_speaker": 5.0,
            "chunk_min_chars": 80,
            "first_sentence_chunk_min_chars": 81,
            "max_caption_len": 120,
            "seed": 1234,
        })

    def test_normal_synthesis_saves_request_and_audio_history(self):
        preview = {
            "speech_text": "読み上げ本文",
            "rewrite": {"elapsed_ms": 30, "enabled": True, "changed": True, "provider": "test", "model": "test", "error": None},
            "dictionary": {"enabled": False, "selected": [], "selected_count": 0, "applied": [], "warnings": []},
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch("irodori_tts_config.provider_config", return_value={"request_attempts": 1}), \
             patch("irodori_tts_core.rewrite_preview", return_value=preview), \
             patch("irodori_tts_request._start_server"), \
             patch("irodori_tts_request._request_speech", return_value=b"audio"), \
             patch("irodori_tts_history.record_audio", return_value={"audio_id": "audio-1", "url": "/api/audio/audio-1"}) as record_audio, \
             patch("irodori_tts_request._elapsed_ms", side_effect=[2, 100, 1, 104]), \
             patch("irodori_tts_request._write_metrics") as write_metrics:
            result = synthesize_text("input", Path(tmp) / "out.mp3")

        self.assertEqual(result["audio_id"], "audio-1")
        record_audio.assert_called_once()
        self.assertEqual(write_metrics.call_args.args[1]["status"], "ok")
        self.assertEqual(write_metrics.call_args.args[1]["input"], "input")
        self.assertEqual(write_metrics.call_args.args[1]["attempts"], 1)
        self.assertEqual(write_metrics.call_args.args[1]["timing_ms"]["total"], 134)

if __name__ == "__main__": unittest.main()
