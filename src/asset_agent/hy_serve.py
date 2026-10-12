"""Launch Hunyuan3D-2's gradio_app.py, requiring a key when HUNYUAN_KEY is set.

Runs inside Hunyuan's own venv (Python 3.10), so it imports nothing from asset_agent.
Run it with Hunyuan's folder as the working directory; arguments go to gradio_app.py.
Clients send 'Authorization: Bearer <key>'. A browser opens http://host:port/?key=<key> once and gets a cookie.
"""
import hmac
import os
import runpy
import sys
from urllib.parse import parse_qs

COOKIE = b"hy_key"


def guard(app, key: str):
    """ASGI wrapper: reject requests without the key."""
    want = key.encode()

    def allowed(scope) -> bool:
        h = dict(scope.get("headers") or [])
        auth = h.get(b"authorization", b"")
        if auth.startswith(b"Bearer ") and hmac.compare_digest(auth[7:], want):
            return True
        for part in h.get(b"cookie", b"").split(b";"):
            name, _, value = part.strip().partition(b"=")
            if name == COOKIE and hmac.compare_digest(value, want):
                return True
        return False

    async def asgi(scope, receive, send):
        if scope["type"] not in ("http", "websocket") or allowed(scope):
            return await app(scope, receive, send)
        q = parse_qs(scope.get("query_string", b"").decode()).get("key", [""])[0].encode()
        if scope["type"] == "http" and hmac.compare_digest(q, want):
            async def send_with_cookie(msg):
                if msg["type"] == "http.response.start":
                    cookie = COOKIE + b"=" + want + b"; HttpOnly; SameSite=Strict; Path=/"
                    msg = {**msg, "headers": [*msg.get("headers", []), (b"set-cookie", cookie)]}
                await send(msg)
            return await app(scope, receive, send_with_cookie)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"asset-agent: missing or wrong key\n"})

    return asgi


def main():
    key = os.environ.get("HUNYUAN_KEY")
    if key:
        import uvicorn
        run = uvicorn.run
        uvicorn.run = lambda app, *a, **k: run(guard(app, key), *a, **k)
    sys.path[0] = os.getcwd()  # Hunyuan's folder, not ours
    sys.argv = ["gradio_app.py", *sys.argv[1:]]
    runpy.run_path("gradio_app.py", run_name="__main__")


if __name__ == "__main__":
    main()
