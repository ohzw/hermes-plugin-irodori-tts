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


def make_request(path: str, *, body: bytes = b"") -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    }, receive)


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

    def test_config_update_returns_schema_for_the_next_workspace_render(self):
        api = load_api_module()
        store = mock.Mock()
        store.update.return_value = {
            "saved": True,
            "values": {"ref_wav": "sample.wav"},
            "revision": "rev-2",
            "validation": {"warnings": []},
        }
        expected_schema = {"fields": {"ref_wav": {"type": "reference_audio"}}}

        with mock.patch.object(api, "ConfigStore", return_value=store), mock.patch.object(
            api, "settings_schema", return_value=expected_schema
        ):
            result = api._config_update({"revision": "rev-1", "values": {"ref_wav": "sample.wav"}})

        self.assertEqual(result["data"]["schema"], expected_schema)

    def test_voice_asset_import_accepts_raw_file_content_and_returns_the_new_asset(self):
        api = load_api_module()
        imported = {"id": "sample.wav", "label": "sample.wav", "type": "wav"}
        request = make_request("/api/config/voice-assets/import", body=b"wave-data")

        with mock.patch.object(api, "import_voice_asset", return_value=imported) as importer:
            result = asyncio.run(api.voice_asset_import(request, kind="reference_audio", filename="sample.wav"))

        self.assertEqual(result["data"]["asset"], imported)
        importer.assert_called_once_with("sample.wav", b"wave-data", "reference_audio")

    def test_voice_asset_import_stops_reading_when_the_limit_is_exceeded(self):
        api = load_api_module()
        request = make_request("/api/config/voice-assets/import", body=b"12345")

        with mock.patch.object(api, "_MAX_VOICE_ASSET_BYTES", 4), mock.patch.object(api, "import_voice_asset") as importer:
            with self.assertRaises(api.HTTPException) as raised:
                asyncio.run(api.voice_asset_import(request, kind="reference_audio", filename="sample.wav"))

        self.assertEqual(raised.exception.status_code, 413)
        importer.assert_not_called()

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
