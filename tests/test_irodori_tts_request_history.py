import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import irodori_tts_request_history as history
import irodori_tts_request as request


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
                    }, max_entries=3)
                rows = history.list_request_history(limit=10)

        self.assertEqual([row["request_id"] for row in rows], ["req-3", "req-2", "req-1"])
        self.assertEqual(rows[0]["original_text"], "元の文言 3\n全文")
        self.assertEqual(rows[0]["speech_text"], "読み上げ文 3")
        self.assertEqual(rows[1]["status"], "error")

    def test_metrics_writer_always_records_dashboard_history_before_redacting_text(self):
        expected = {"request_id": "req-1", "input": "元の文言", "speech_text": "読み上げ文"}
        with tempfile.TemporaryDirectory() as tmp, patch.object(request, "record_request_history", create=True) as record_history:
            record = dict(expected)
            request._write_metrics({"metrics": {"enabled": True, "include_text": False, "log_path": str(Path(tmp) / "metrics.jsonl")}}, record)

        self.assertEqual(record_history.call_args.args[0], expected)
        self.assertNotIn("input", record)
        self.assertNotIn("speech_text", record)


if __name__ == "__main__": unittest.main()
