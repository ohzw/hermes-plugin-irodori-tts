import tempfile
import unittest
import os
import json
from pathlib import Path
from unittest.mock import patch

import irodori_tts_request_history as history
import irodori_tts_request as request
import irodori_tts_history as audio_history


class RequestHistoryTests(unittest.TestCase):
    def test_records_full_text_and_keeps_only_newest_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request_history.jsonl"
            with patch.object(history, "history_path", return_value=path):
                for index in range(4):
                    history.record_request_history({
                        "request_id": f"req-{index}",
                        "ts": f"2026-07-12T10:0{index}:00Z",
                        "status": "ok" if index != 2 else "error",
                        "input": f"元の文言 {index}\n全文",
                        "speech_text": f"読み上げ文 {index}",
                        "timing_ms": {"total": index * 100},
                        "rewrite_error": "rewrite failed" if index == 2 else None,
                    }, max_entries=3)
                rows = history.list_request_history(limit=10)

        self.assertEqual([row["request_id"] for row in rows], ["req-3", "req-2", "req-1"])
        self.assertEqual(rows[0]["original_text"], "元の文言 3\n全文")
        self.assertEqual(rows[0]["speech_text"], "読み上げ文 3")
        self.assertEqual(rows[1]["status"], "error")
        self.assertEqual(rows[1]["timing_ms"], {"total": 200})
        self.assertEqual(rows[1]["rewrite_error"], "rewrite failed")

    def test_metrics_writer_always_records_dashboard_history_before_redacting_text(self):
        expected = {"request_id": "req-1", "input": "元の文言", "speech_text": "読み上げ文"}
        recent = [{"request_id": "req-1"}, {"request_id": "req-old"}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(request, "record_request_history", create=True) as record_history, \
             patch.object(request, "list_request_history", return_value=recent, create=True), \
             patch("irodori_tts_history.retain_request_audio") as retain_audio:
            record = dict(expected)
            request._write_metrics({"metrics": {"enabled": True, "include_text": False, "log_path": str(Path(tmp) / "metrics.jsonl")}}, record)

        self.assertEqual(record_history.call_args.args[0], expected)
        retain_audio.assert_called_once_with({"req-1", "req-old"})
        self.assertNotIn("input", record)
        self.assertNotIn("speech_text", record)

    def test_latest_fifty_requests_prune_audio_even_when_failure_has_no_audio(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HERMES_HOME": tmp}):
            first_audio_id = None
            for index in range(51):
                status = "error" if index == 50 else "ok"
                if status == "ok":
                    saved = audio_history.record_audio(b"audio", request_id=f"req-{index}")
                    if index == 0:
                        first_audio_id = saved["audio_id"]
                request._write_metrics(
                    {"metrics": {"enabled": False}},
                    {
                        "request_id": f"req-{index}",
                        "status": status,
                        "input": f"input {index}",
                        "speech_text": f"speech {index}" if status == "ok" else "",
                    },
                )

            requests = history.list_request_history(limit=50)
            audio = audio_history.list_history(limit=50)

        self.assertEqual(len(requests), 50)
        self.assertEqual(requests[0]["request_id"], "req-50")
        self.assertEqual(requests[-1]["request_id"], "req-1")
        self.assertEqual(len(audio), 49)
        self.assertNotIn("req-0", {item["request_id"] for item in audio})
        self.assertIsNotNone(first_audio_id)

    def test_first_new_request_migrates_legacy_metrics_before_pruning_audio(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HERMES_HOME": tmp}):
            metrics_path = Path(tmp) / "timings.jsonl"
            metrics_path.write_text(
                json.dumps({"request_id": "legacy-1", "status": "ok", "timing_ms": {"total": 100}}) + "\n",
                encoding="utf-8",
            )
            legacy_audio = audio_history.record_audio(
                b"legacy",
                request_id="legacy-1",
                input_text="以前の入力",
                speech_text="以前の読み上げ",
            )

            request._write_metrics(
                {"metrics": {"enabled": True, "include_text": False, "log_path": str(metrics_path)}},
                {"request_id": "new-1", "status": "error", "input": "新しい入力", "speech_text": ""},
            )

            requests = history.list_request_history(limit=50)
            retained_audio = audio_history.resolve_audio(legacy_audio["audio_id"])

        self.assertEqual([item["request_id"] for item in requests], ["new-1", "legacy-1"])
        self.assertEqual(requests[1]["original_text"], "以前の入力")
        self.assertIsNotNone(retained_audio)


if __name__ == "__main__": unittest.main()
