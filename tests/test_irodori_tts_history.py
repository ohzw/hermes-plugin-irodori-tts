#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import irodori_tts_history as history


class AudioHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_record_sanitizes_entry_and_resolves_by_id(self):
        entry = history.record_audio(b"audio", request_id="req-1", audio_format="mp3", input_text="i" * 300, speech_text="s" * 300)
        self.assertEqual(entry["bytes"], 5)
        self.assertEqual(entry["input_preview"], "i" * 240)
        self.assertEqual(entry["speech_preview"], "s" * 240)
        self.assertNotIn("path", entry)
        resolved = history.resolve_audio(entry["audio_id"])
        self.assertIsNotNone(resolved)
        path, content_type = resolved
        self.assertEqual(path.read_bytes(), b"audio")
        self.assertEqual(content_type, "audio/mpeg")
        self.assertIsNone(history.resolve_audio("../secret"))
        self.assertIsNone(history.resolve_audio("unknown"))

    def test_registry_never_returns_raw_path_and_retention_removes_oldest_by_count(self):
        with mock.patch.object(history, "_settings", return_value=(True, 2, 240)):
            first = history.record_audio(b"123", request_id="1")
            second = history.record_audio(b"456", request_id="2")
            third = history.record_audio(b"789", request_id="3")
        listed = history.list_history(20)
        self.assertEqual([item["request_id"] for item in listed], ["3", "2"])
        self.assertTrue(all("path" not in item for item in listed))
        self.assertIsNone(history.resolve_audio(first["audio_id"]))
        self.assertEqual(history.resolve_audio(second["audio_id"])[0].read_bytes(), b"456")
        raw = history.history_path().read_text(encoding="utf-8")
        self.assertTrue(all("path" in json.loads(line) for line in raw.splitlines()))
    def test_disabled_history_does_not_persist(self):
        with mock.patch.object(history, "_settings", return_value=(False, 50, 240)):
            entry = history.record_audio(b"audio", request_id="disabled")
            self.assertEqual(entry["status"], "disabled")
            self.assertIsNone(entry["audio_id"])
            self.assertEqual(history.list_history(20), [])
            self.assertFalse(history.audio_dir().exists())

    def test_dashboard_flat_settings_are_supported(self):
        Path(self.home, "config.yaml").write_text(
            "tts:\n  providers:\n    irodori-local:\n      dashboard:\n"
            "        audio_history_enabled: false\n"
            "        audio_history_max_entries: 12\n"
            "        preview_max_chars: 14\n",
            encoding="utf-8",
        )
        self.assertEqual(history.history_status(), {"enabled": False, "max_entries": 12, "preview_max_chars": 14})

    def test_pruning_to_recent_requests_removes_stale_audio(self):
        first = history.record_audio(b"one", request_id="req-1")
        second = history.record_audio(b"two", request_id="req-2")

        history.retain_request_audio({"req-2"})

        self.assertIsNone(history.resolve_audio(first["audio_id"]))
        self.assertEqual(history.resolve_audio(second["audio_id"])[0].read_bytes(), b"two")
        self.assertEqual([item["request_id"] for item in history.list_history(20)], ["req-2"])


if __name__ == "__main__":
    unittest.main()
