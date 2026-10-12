"""GPU server: setup choices, serve command, key guard, connect and the auto backend. No GPU or Blender needed."""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from asset_agent import cli, config, generators, gpu
from asset_agent.generators import GeneratorError, HFSpaces, LocalHunyuan, local_status
from asset_agent.hy_serve import guard


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_AGENT_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.delenv("HUNYUAN_URL", raising=False)
    monkeypatch.delenv("HUNYUAN_KEY", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


def test_parse_gpu_and_choices():
    g = gpu.parse_gpu("NVIDIA GeForce GTX 1080 Ti, 11264, 6.1")
    assert (g.name, g.vram_gb, g.cap) == ("NVIDIA GeForce GTX 1080 Ti", 11.0, (6, 1))
    assert str(g) == "NVIDIA GeForce GTX 1080 Ti 11GB sm_61"
    assert gpu.parse_gpu("Old Card, 8192").cap is None
    assert gpu.torch_index((6, 1)) == "cu126" and gpu.torch_index((12, 0)) == "cu128" and gpu.torch_index(None) == "cu126"
    assert gpu.pick_model(11) == "full" and gpu.pick_model(8) == "mini"


def test_serve_cmd_flags(tmp_path):
    cmd = [str(x) for x in gpu.serve_cmd(tmp_path, "mini", "127.0.0.1", 8080, 11.0)]
    assert cmd[1].endswith("hy_serve.py") and "--disable_tex" in cmd and "--low_vram_mode" in cmd
    assert cmd[cmd.index("--subfolder") + 1] == "hunyuan3d-dit-v2-mini-turbo"
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1" and "--enable_flashvdm" in cmd
    big = [str(x) for x in gpu.serve_cmd(tmp_path, "full", "0.0.0.0", 9000, 24.0, flashvdm=False)]
    assert "--low_vram_mode" not in big and "--enable_flashvdm" not in big and "9000" in big


def test_serve_needs_setup_first():
    with pytest.raises(gpu.SetupError, match="asset-agent setup"):
        gpu.serve()


def asgi_call(app, scope):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        sent.append(msg)

    asyncio.run(app(scope, receive, send))
    return sent


async def ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"hi"})


def http(headers=(), query=b""):
    return {"type": "http", "headers": list(headers), "query_string": query}


def test_guard():
    app = guard(ok_app, "s3cret")
    assert asgi_call(app, http())[0]["status"] == 401
    assert asgi_call(app, http([(b"authorization", b"Bearer nope")]))[0]["status"] == 401
    assert asgi_call(app, http([(b"authorization", b"Bearer s3cret")]))[0]["status"] == 200
    assert asgi_call(app, http([(b"cookie", b"a=1; hy_key=s3cret")]))[0]["status"] == 200
    first = asgi_call(app, http(query=b"key=s3cret"))[0]  # browser link sets the cookie
    assert first["status"] == 200 and any(k == b"set-cookie" and b"hy_key=s3cret" in v for k, v in first["headers"])
    assert asgi_call(app, http(query=b"key=wrong"))[0]["status"] == 401
    assert asgi_call(app, {"type": "websocket", "headers": []})[0]["type"] == "websocket.close"
    assert asgi_call(app, {"type": "lifespan"})[0]["status"] == 200  # passes through


@pytest.fixture
def fake_server():
    """Stands in for `asset-agent serve --remote`: 200 with the right key, 401 otherwise."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.headers.get("Authorization") == "Bearer k1" else 401)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def closed_port_url():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def test_connect_and_auto_backend(fake_server):
    assert "offline" in cli.connect(closed_port_url(), None)
    assert isinstance(generators.get("auto"), HFSpaces) and not isinstance(generators.get("auto"), LocalHunyuan)

    assert "wrong key" in cli.connect(fake_server, "bad")
    with pytest.raises(GeneratorError, match="key"):
        generators.get("auto")

    assert cli.connect(fake_server.removeprefix("http://"), "k1").endswith(": ok")
    g = generators.get("auto")
    assert isinstance(g, LocalHunyuan) and g.shape_space == fake_server and g.key == "k1"
    assert config.load() == {"url": fake_server, "key": "k1"}


def test_env_overrides_config(fake_server, monkeypatch):
    config.save(url="http://nowhere:1", key="bad")
    monkeypatch.setenv("HUNYUAN_URL", fake_server)
    monkeypatch.setenv("HUNYUAN_KEY", "k1")
    assert local_status() == "ok"
    config.save(key=None)
    assert "key" not in config.load()


def test_status_runs():
    out = cli.status()
    assert "server:" in out and "auto ->" in out and str(Path(config.path())) in out
