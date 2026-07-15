from __future__ import annotations

import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]


def load_api_module():
    path = ROOT / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("irodori_dashboard_plugin_api", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_request(path: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    })


class DashboardPluginTests(unittest.TestCase):
    def test_manifest_registers_native_dashboard_tab_and_api(self):
        manifest = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("irodori-tts", manifest["name"])
        self.assertEqual("/irodori-tts", manifest["tab"]["path"])
        self.assertEqual("dist/index.js", manifest["entry"])
        self.assertEqual("plugin_api.py", manifest["api"])

    def test_status_route_uses_existing_dashboard_service(self):
        api = load_api_module()
        expected = {"health": {"ok": True}, "recent": []}

        with mock.patch.object(api, "get_public_status", return_value=expected) as status:
            result = asyncio.run(api.status(make_request("/api/plugins/irodori-tts/status"), limit=12))

        self.assertEqual(expected, result)
        status.assert_called_once_with(limit=12)

    def test_status_events_streams_an_initial_sse_snapshot(self):
        api = load_api_module()
        expected = {"health": {"ok": True}, "recent": [{"request_id": "req-1"}]}

        async def first_event():
            request = make_request("/api/events/status")
            with mock.patch.object(api, "get_public_status", return_value=expected):
                response = await api.status_events(request, limit=12)
                chunk = await response.body_iterator.__anext__()
                await response.body_iterator.aclose()
                return response, chunk

        response, chunk = asyncio.run(first_event())

        self.assertEqual("text/event-stream; charset=utf-8", response.headers["content-type"])
        self.assertIn("event: status", chunk)
        self.assertIn('\"request_id\":\"req-1\"', chunk)

    def test_config_route_returns_editable_config_contract(self):
        api = load_api_module()
        store = mock.Mock()
        store.read_values.return_value = {"caption": "やさしい声"}
        store.revision.return_value = "rev-1"

        with mock.patch.object(api, "ConfigStore", return_value=store), mock.patch.object(
            api, "settings_schema", return_value={"fields": {}}
        ):
            result = asyncio.run(api.config())

        self.assertEqual("rev-1", result["data"]["revision"])
        self.assertEqual("やさしい声", result["data"]["values"]["caption"])

    def test_request_detail_rebases_legacy_audio_url_to_plugin_mount(self):
        api = load_api_module()
        detail = {
            "request_id": "req-1",
            "audio": {"audio_id": "audio-1", "url": "/api/audio/audio-1"},
        }

        with mock.patch.object(api, "get_request_detail", return_value=detail):
            result = asyncio.run(
                api.request_detail("req-1", make_request("/api/plugins/irodori-tts/requests/req-1"))
            )

        self.assertEqual(
            "/api/plugins/irodori-tts/audio/audio-1",
            result["audio"]["url"],
        )

    def test_request_detail_preserves_standalone_audio_mount(self):
        api = load_api_module()
        detail = {"audio": {"url": "/api/audio/audio-1"}}
        with mock.patch.object(api, "get_request_detail", return_value=detail):
            result = asyncio.run(api.request_detail("req-1", make_request("/api/requests/req-1")))
        self.assertEqual("/api/audio/audio-1", result["audio"]["url"])

    def test_playground_synthesis_does_not_save_history(self):
        api = load_api_module()

        def synthesize(_text, output_path, **_kwargs):
            output_path.write_bytes(b"audio")
            return {
                "status": "ok",
                "request_id": "playground-1",
                "audio_id": None,
                "url": None,
                "rewrite": {},
                "dictionary": {},
                "timing_ms": {},
            }

        with mock.patch.object(api, "synthesize_text", side_effect=synthesize) as synthesis:
            result = asyncio.run(api.playground_tts({"text": "テスト"}, make_request("/api/playground/tts")))

        self.assertTrue(result["ok"])
        self.assertFalse(synthesis.call_args.kwargs["save_history"])


if __name__ == "__main__":
    unittest.main()
