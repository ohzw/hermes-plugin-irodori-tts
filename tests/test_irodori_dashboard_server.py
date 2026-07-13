from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from fastapi.testclient import TestClient

import irodori_tts_dashboard_server as server


class DashboardConfigTests(unittest.TestCase):
    def test_defaults_and_configured_port(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            self.assertEqual(
                {"host": "127.0.0.1", "port": 9120},
                server.dashboard_config(),
            )
            Path(tmp, "config.yaml").write_text(
                "tts:\n  providers:\n    irodori-local:\n      dashboard:\n        host: localhost\n        port: 9234\n",
                encoding="utf-8",
            )
            self.assertEqual(
                {"host": "127.0.0.1", "port": 9234},
                server.dashboard_config(),
            )

    def test_ipv6_loopback_url_is_bracketed(self):
        self.assertEqual(
            "http://[::1]:9120/workspace",
            server.dashboard_url({"host": "::1", "port": 9120}),
        )

    def test_non_loopback_host_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            Path(tmp, "config.yaml").write_text(
                "tts:\n  providers:\n    irodori-local:\n      dashboard:\n        host: 0.0.0.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "loopback"):
                server.dashboard_config()


class DashboardAppTests(unittest.TestCase):
    def test_routes_serve_spa_and_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp)
            (static / "index.html").write_text("<div>standalone</div>", encoding="utf-8")
            app = server.create_app(static_dir=static)
            client = TestClient(app)

            self.assertEqual(307, client.get("/", follow_redirects=False).status_code)
            self.assertEqual("/workspace", client.get("/", follow_redirects=False).headers["location"])
            for path in ["/workspace", "/overview", "/history", "/dictionary", "/diagnostics", "/unknown"]:
                response = client.get(path)
                self.assertEqual(200, response.status_code, path)
                self.assertIn("standalone", response.text)
            self.assertNotEqual(200, client.get("/api/not-real").status_code)

    def test_control_stop_requires_instance_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp)
            (static / "index.html").write_text("ok", encoding="utf-8")
            timer = mock.Mock()
            with mock.patch.object(server.threading, "Timer", return_value=timer):
                client = TestClient(server.create_app(static_dir=static, instance_token="secret"))
                self.assertEqual(404, client.get("/__control/status").status_code)
                status = client.get("/__control/status", headers={"X-Irodori-Instance": "secret"})
                self.assertEqual(os.getpid(), status.json()["pid"])
                self.assertEqual(404, client.post("/__control/stop").status_code)
                self.assertEqual(
                    202,
                    client.post("/__control/stop", headers={"X-Irodori-Instance": "secret"}).status_code,
                )
            timer.start.assert_called_once()


class DashboardLifecycleTests(unittest.TestCase):
    def test_status_removes_stale_state(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            state_path = server.state_path()
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({"pid": 999999, "url": "http://127.0.0.1:9120/workspace"}))

            status = server.dashboard_status()

            self.assertFalse(status["running"])
            self.assertFalse(state_path.exists())

    def test_status_rejects_out_of_range_pid(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            state_path = server.state_path()
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({
                "pid": 10**100,
                "token": "secret",
                "host": "127.0.0.1",
                "port": 9120,
            }))
            self.assertFalse(server.dashboard_status()["running"])
            self.assertFalse(state_path.exists())

    def test_start_terminates_child_if_state_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            assets = Path(tmp) / "assets"
            assets.mkdir()
            (assets / "index.html").write_text("ok", encoding="utf-8")
            process = mock.Mock(pid=42)
            process.poll.return_value = None
            with mock.patch.object(server, "_dashboard_status_unlocked", return_value={"running": False}), mock.patch.object(
                server, "dashboard_config", return_value={"host": "127.0.0.1", "port": 9120}
            ), mock.patch.object(server, "_port_open", return_value=False), mock.patch.object(
                server, "static_dir", return_value=assets
            ), mock.patch.object(server.subprocess, "Popen", return_value=process), mock.patch.object(
                server, "_write_state", side_effect=OSError("disk full")
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    server.start_dashboard()
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=2)

    def test_stop_never_signals_unowned_process(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            state_path = server.state_path()
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({
                "pid": 42,
                "token": "secret",
                "host": "127.0.0.1",
                "port": 9120,
            }))
            with mock.patch.object(server, "_pid_exists", return_value=True), mock.patch.object(
                server, "_is_owned_process", return_value=False
            ), mock.patch.object(os, "kill") as kill:
                result = server.stop_dashboard()

            self.assertFalse(result["running"])
            kill.assert_not_called()
            self.assertFalse(state_path.exists())

    def test_status_derives_url_from_validated_bound_address(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"HERMES_HOME": tmp}):
            state_path = server.state_path()
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({
                "pid": 42,
                "token": "secret",
                "host": "127.0.0.1",
                "port": 9120,
                "url": "https://example.invalid/",
            }))
            with mock.patch.object(server, "_is_owned_process", return_value=True), mock.patch.object(
                server, "_instance_pid", return_value=42
            ):
                status = server.dashboard_status()
            self.assertEqual("http://127.0.0.1:9120/workspace", status["url"])


if __name__ == "__main__":
    unittest.main()
