import unittest
from unittest.mock import patch

from irodori_tts_dashboard_service import get_public_status, get_recent_requests, get_request_detail


class DashboardServiceTests(unittest.TestCase):
    @patch("irodori_tts_dashboard_service._listener_pids", return_value=[])
    @patch("irodori_tts_dashboard_service._fetch_health", return_value={"ok": False})
    @patch("irodori_tts_dashboard_service.load_records", return_value=[])
    def test_public_status_keeps_existing_top_level_shape(self, *_mocks):
        result = get_public_status(limit=5)
        for key in ("now", "health", "config", "summary", "recent", "dictionary", "server_log"):
            self.assertIn(key, result)

    @patch("irodori_tts_dashboard_service.get_public_status")
    def test_recent_requests_exposes_original_text_but_keeps_speech_text_in_detail(self, public_status):
        original = "一行目。\n二行目も省略せずに表示する。"
        public_status.return_value = {
            "recent": [{"request_id": "req-1", "input": original, "speech_text": "rewrite後"}],
            "summary": {},
        }

        result = get_recent_requests(limit=5)

        self.assertEqual(result["requests"][0]["original_text"], original)
        self.assertNotIn("input", result["requests"][0])
        self.assertNotIn("speech_text", result["requests"][0])

    @patch("irodori_tts_dashboard_service.get_public_status")
    def test_recent_requests_joins_text_from_bounded_request_history(self, public_status):
        public_status.return_value = {
            "recent": [{"request_id": "req-1", "status": "ok"}],
            "summary": {},
        }
        saved = [{"request_id": "req-1", "original_text": "保存された元の文言", "speech_text": "読み上げ文"}]
        with patch("irodori_tts_dashboard_service.list_request_history", return_value=saved, create=True):
            result = get_recent_requests(limit=5)

        self.assertEqual(result["requests"][0]["original_text"], "保存された元の文言")

    @patch("irodori_tts_dashboard_service.list_history")
    @patch("irodori_tts_dashboard_service.list_request_history", return_value=[])
    @patch("irodori_tts_dashboard_service.get_public_status")
    def test_recent_requests_falls_back_to_legacy_audio_preview(self, public_status, _text_history, audio_history):
        public_status.return_value = {"recent": [{"request_id": "req-legacy"}], "summary": {}}
        audio_history.return_value = [{"request_id": "req-legacy", "input_preview": "既存履歴のプレビュー"}]

        result = get_recent_requests(limit=5)

        self.assertEqual(result["requests"][0]["original_text"], "既存履歴のプレビュー")

    @patch("irodori_tts_dashboard_service.list_history", return_value=[])
    @patch("irodori_tts_dashboard_service.list_request_history")
    @patch("irodori_tts_dashboard_service.load_records")
    def test_request_detail_joins_original_and_speech_text_from_bounded_history(self, records, text_history, _audio):
        records.return_value = [{"request_id": "req-1", "status": "ok", "timing_ms": {}}]
        text_history.return_value = [{"request_id": "req-1", "original_text": "元の全文", "speech_text": "読み上げ全文"}]

        result = get_request_detail("req-1")

        self.assertEqual(result["original_text"], "元の全文")
        self.assertEqual(result["speech_text"], "読み上げ全文")


if __name__ == "__main__": unittest.main()
