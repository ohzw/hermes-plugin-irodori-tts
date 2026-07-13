"""Standalone localhost dashboard server and lifecycle management."""
from __future__ import annotations

import argparse
import fcntl
import hmac
import ipaddress
import json
import os
import secrets
import signal
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from irodori_tts_config import hermes_home, provider_config

PLUGIN_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9120
ROUTES = {"workspace", "overview", "history", "dictionary", "diagnostics"}


def dashboard_config() -> dict[str, Any]:
    raw = provider_config().get("dashboard")
    config = raw if isinstance(raw, dict) else {}
    host = str(config.get("host") or DEFAULT_HOST).strip().lower()
    if host == "localhost":
        host = DEFAULT_HOST
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("Dashboard host must be a loopback address")
    except ValueError as exc:
        if "loopback" in str(exc):
            raise
        raise ValueError("Dashboard host must be localhost or a loopback IP address") from exc
    try:
        port = int(config.get("port", DEFAULT_PORT))
    except (TypeError, ValueError) as exc:
        raise ValueError("Dashboard port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Dashboard port must be between 1 and 65535")
    return {"host": host, "port": port}


def dashboard_url(config: dict[str, Any] | None = None) -> str:
    current = config or dashboard_config()
    host = str(current["host"])
    display_host = f"[{host}]" if ":" in host else host
    return f"http://{display_host}:{current['port']}/workspace"


def runtime_dir() -> Path:
    return hermes_home() / "run" / "irodori-tts"


def state_path() -> Path:
    return runtime_dir() / "dashboard.json"


def lock_path() -> Path:
    return runtime_dir() / "dashboard.lock"


@contextmanager
def _lifecycle_lock():
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def log_path() -> Path:
    return hermes_home() / "logs" / "irodori-dashboard.log"


def static_dir() -> Path:
    return PLUGIN_ROOT / "standalone" / "dist"


def _write_state(state: dict[str, Any]) -> None:
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, target)


def _read_state() -> dict[str, Any] | None:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _clear_state() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass


def _pid_exists(pid: int) -> bool:
    if pid <= 1 or pid > 2_147_483_647:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    return True


def _is_owned_process(pid: int) -> bool:
    if not _pid_exists(pid):
        return False
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        arguments = shlex.split(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    script = str(Path(__file__).resolve())
    return result.returncode == 0 and script in arguments and "serve" in arguments


def _state_identity(state: dict[str, Any]) -> tuple[int, str, dict[str, Any]] | None:
    try:
        pid = int(state["pid"])
        token = str(state["token"])
        host = str(state["host"])
        port = int(state["port"])
        if pid <= 1 or pid > 2_147_483_647:
            return None
        if not token or not ipaddress.ip_address(host).is_loopback or not 1 <= port <= 65535:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return pid, token, {"host": host, "port": port}


def _port_open(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _instance_pid(bound: dict[str, Any], token: str) -> int | None:
    base = dashboard_url(bound).removesuffix("/workspace")
    request = urllib.request.Request(
        f"{base}/__control/status",
        headers={"X-Irodori-Instance": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
            pid = int(payload.get("pid", 0)) if isinstance(payload, dict) else 0
            return pid if 1 < pid <= 2_147_483_647 else None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None


def _dashboard_status_unlocked() -> dict[str, Any]:
    configured = dashboard_config()
    configured_url = dashboard_url(configured)
    state = _read_state()
    identity = _state_identity(state) if state else None
    if identity is None:
        if state:
            _clear_state()
        return {"running": False, "url": configured_url, "pid": None}
    pid, token, bound = identity
    if not _is_owned_process(pid) or _instance_pid(bound, token) != pid:
        _clear_state()
        return {"running": False, "url": configured_url, "pid": None}
    return {
        "running": True,
        "url": dashboard_url(bound),
        "pid": pid,
        "config_mismatch": bound != configured,
    }


def dashboard_status() -> dict[str, Any]:
    with _lifecycle_lock():
        return _dashboard_status_unlocked()


def _wait_ready(url: str, process: subprocess.Popen[Any], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard process exited with status {process.returncode}; see {log_path()}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Dashboard did not become ready within {timeout:g}s; see {log_path()}")


def start_dashboard() -> dict[str, Any]:
    with _lifecycle_lock():
        current = _dashboard_status_unlocked()
        if current["running"]:
            return current
        config = dashboard_config()
        if _port_open(config["host"], config["port"]):
            raise RuntimeError(f"Dashboard port {config['host']}:{config['port']} is already in use")
        assets = static_dir()
        if not (assets / "index.html").is_file():
            raise RuntimeError("Standalone dashboard assets are missing; run `npm run build` in dashboard-ui")
        log = log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        child_env = os.environ.copy()
        child_env["IRODORI_DASHBOARD_INSTANCE_TOKEN"] = token
        with log.open("ab") as stream:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "serve",
                    "--host",
                    config["host"],
                    "--port",
                    str(config["port"]),
                ],
                cwd=PLUGIN_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=child_env,
            )
        url = dashboard_url(config)
        state = {"pid": process.pid, "token": token, "host": config["host"], "port": config["port"]}
        try:
            _write_state(state)
            _wait_ready(url, process)
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            _clear_state()
            raise
        return {"running": True, "url": url, "pid": process.pid, "config_mismatch": False}


def _request_self_stop(bound: dict[str, Any], token: str) -> None:
    base = dashboard_url(bound).removesuffix("/workspace")
    request = urllib.request.Request(
        f"{base}/__control/stop",
        method="POST",
        headers={"X-Irodori-Instance": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 202:
                raise RuntimeError(f"Dashboard refused stop request with status {response.status}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Dashboard did not accept its authenticated stop request") from exc


def stop_dashboard(timeout: float = 5.0) -> dict[str, Any]:
    with _lifecycle_lock():
        configured_url = dashboard_url()
        state = _read_state()
        identity = _state_identity(state) if state else None
        if identity is None:
            if state:
                _clear_state()
            return {"running": False, "url": configured_url, "pid": None}
        pid, token, bound = identity
        if not _is_owned_process(pid) or _instance_pid(bound, token) != pid:
            _clear_state()
            return {"running": False, "url": configured_url, "pid": None}
        _request_self_stop(bound, token)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and _is_owned_process(pid):
            time.sleep(0.1)
        if _is_owned_process(pid):
            raise RuntimeError("Dashboard did not stop after its authenticated shutdown request")
        _clear_state()
        return {"running": False, "url": configured_url, "pid": None}


def open_dashboard(*, start: bool = True) -> dict[str, Any]:
    current = start_dashboard() if start else dashboard_status()
    if not current["running"]:
        raise RuntimeError("Irodori Dashboard is not running")
    webbrowser.open(current["url"])
    return current


def create_app(*, static_dir: Path | None = None, instance_token: str | None = None) -> FastAPI:
    from dashboard.plugin_api import router

    assets = Path(static_dir) if static_dir is not None else globals()["static_dir"]()
    index = assets / "index.html"
    app = FastAPI(title="Irodori TTS Dashboard", docs_url=None, redoc_url=None)
    app.include_router(router, prefix="/api")
    asset_dir = assets / "assets"
    if asset_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=asset_dir), name="assets")

    @app.get("/__control/status", include_in_schema=False)
    async def control_status(request: Request):
        supplied = request.headers.get("x-irodori-instance", "")
        if not instance_token or not hmac.compare_digest(supplied, instance_token):
            raise HTTPException(status_code=404, detail="not found")
        return {"pid": os.getpid()}

    @app.post("/__control/stop", status_code=202, include_in_schema=False)
    async def control_stop(request: Request):
        supplied = request.headers.get("x-irodori-instance", "")
        if not instance_token or not hmac.compare_digest(supplied, instance_token):
            raise HTTPException(status_code=404, detail="not found")
        threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
        return {"stopping": True}

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/workspace")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        if not index.is_file():
            raise HTTPException(status_code=503, detail="standalone dashboard assets are missing")
        return FileResponse(index)

    return app


def _serve(host: str, port: int, instance_token: str) -> None:
    import uvicorn

    uvicorn.run(create_app(instance_token=instance_token), host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve")
    serve.add_argument("--host", required=True)
    serve.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)
    if args.command == "serve":
        host = str(args.host)
        port = int(args.port)
        # Apply the same loopback validation used for persisted configuration.
        if host == "localhost":
            host = DEFAULT_HOST
        if not ipaddress.ip_address(host).is_loopback:
            parser.error("--host must be a loopback address")
        if not 1 <= port <= 65535:
            parser.error("--port must be between 1 and 65535")
        instance_token = os.environ.get("IRODORI_DASHBOARD_INSTANCE_TOKEN", "")
        if not instance_token:
            parser.error("missing dashboard instance token")
        _serve(host, port, instance_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
