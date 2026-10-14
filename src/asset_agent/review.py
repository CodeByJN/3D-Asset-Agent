"""Review window: every new asset or animation version opens in a local 3D viewer before it goes to Studio.

The user orbits it (animations play on their character, effects play around it), rates it with stars,
writes pros, cons and notes, and presses
  Regenerate  - record the rating and send it back, so Claude makes a new version from the notes,
  Looks good  - record the rating and keep it as it is,
  Place       - record the rating and put it in the open Studio place.
The arrows step through earlier reviews.
review.wait() blocks the review tool until one of those, so the decision comes back as one line
and Claude never needs a preview image to judge the model.

A small HTTP server on 127.0.0.1 runs inside the MCP process; the URL carries a random token so
other local pages can't post decisions. The queue lives in <home>/_review/queue.json.
"""
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PAGE = Path(__file__).with_name("review.html")
TOKEN = secrets.token_urlsafe(16)
hooks = {}  # rate(name, stars, note) -> line and place(name) -> line, set by the MCP server

_cv = threading.Condition()
_board = None
_httpd = None


class Board:
    """The review queue for one assets folder."""

    def __init__(self, home: Path):
        self.home = Path(home)
        self.file = self.home / "_review" / "queue.json"
        self.items = json.loads(self.file.read_text())["items"] if self.file.exists() else []
        self.polled = 0.0  # last time an open page asked for the state

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps({"items": self.items}, indent=1))

    def latest(self, name: str) -> dict | None:
        return next((i for i in reversed(self.items) if i["name"] == name), None)

    def get(self, item_id: int) -> dict | None:
        return next((i for i in self.items if i["id"] == item_id), None)


def board(home) -> Board:
    global _board
    with _cv:
        if _board is None or _board.home != Path(home):
            _board = Board(home)
        return _board


def url() -> str:
    """Start the server if it isn't running; return the page's address."""
    global _httpd
    with _cv:
        if _httpd is None:
            port = int(os.environ.get("ASSET_AGENT_REVIEW_PORT", 8765))
            try:
                _httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            except OSError:  # the port is taken (another session): any free one
                _httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            _httpd.daemon_threads = True
            threading.Thread(target=_httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{_httpd.server_address[1]}/?t={TOKEN}"


def add(home, name: str, v: int, glb: Path | None, line: str, kind: str = "model", fx: dict | None = None,
        anim: dict | None = None) -> str:
    """Queue version v of an asset for review (once; again after its review went back to Claude, so
    reviewing an unchanged version asks the user again). fx: its effects (vfx.resolve), which the
    page plays around the model. anim: an animation's playback (anim.playback + rig), kind "animation".
    Returns the page's address."""
    b = board(home)
    with _cv:
        last = b.latest(name)
        if not (last and last["v"] == v and not (last["decision"] or {}).get("delivered")):
            b.items.append({"id": max((i["id"] for i in b.items), default=0) + 1, "name": name, "v": v,
                            "kind": kind, "glb": str(glb) if glb and Path(glb).exists() else None,
                            "line": line, "added": time.time(), "decision": None, "fx": fx or {},
                            "anim": anim})
            b.save()
            _cv.notify_all()
    return url()


def note(pros: str = "", cons: str = "", notes: str = "") -> str:
    parts = [f"{k}: {' '.join(v.split())}" for k, v in (("pros", pros), ("cons", cons), ("notes", notes)) if v.strip()]
    return "; ".join(p for p in parts if p)


def decide(home, item_id: int, action: str, stars: int | None = None, pros: str = "", cons: str = "",
           background: bool = False, notes: str = "") -> dict:
    """What the buttons do: regenerate (action "next": rate, then Claude makes a new version from the
    notes), keep (rate it, no changes) or place (rate it and put it in Studio). Returns {ok, line} or {ok: False, error}. background: Place
    (building it in Studio, or an upload) runs on its own thread; the item shows `placing`, then its decision or
    `error`, so the page never waits on a long request."""
    b = board(home)
    with _cv:
        item = b.get(item_id)
        if item is None:
            return {"ok": False, "error": "no such item"}
        if item["decision"]:
            return {"ok": False, "error": f"already {item['decision']['action']}"}
        if item.get("placing"):
            return {"ok": False, "error": "already placing it in Studio"}
        if b.latest(item["name"]) is not item:
            return {"ok": False, "error": f"this is an older version: roll {item['name']} back to v{item['v']} first"}
    if action not in ("next", "keep", "place"):
        return {"ok": False, "error": f"unknown action {action!r}"}
    if action in ("next", "keep") and not stars:
        return {"ok": False, "error": "rate it with the stars first"}
    if stars is not None and not 1 <= int(stars) <= 10:
        return {"ok": False, "error": "stars must be 1-10"}
    stars = int(stars) if stars else None
    if action == "place" and background:
        with _cv:
            item["placing"], item["error"] = True, None
        threading.Thread(target=_apply, args=(b, item, action, stars, note(pros, cons, notes)), daemon=True).start()
        return {"ok": True, "line": "placing in Studio", "pending": True}
    return _apply(b, item, action, stars, note(pros, cons, notes))


def _apply(b: Board, item: dict, action: str, stars: int | None, text: str) -> dict:
    lines = []
    try:
        if stars and item.get("rated") != [stars, text]:  # not twice when Place failed, then Next
            lines.append(hooks["rate"](item["name"], stars, text))
            item["rated"] = [stars, text]
        if action == "place":
            lines.append(hooks["place"](item["name"]))
    except Exception as e:  # e.g. Studio not open: the rating stays, the item stays open
        msg = f"{type(e).__name__}: {' '.join(str(e).split())}"[:300]
        with _cv:
            item["placing"], item["error"] = False, " | ".join([*lines, msg])
            b.save()
        return {"ok": False, "error": msg, "lines": lines}
    with _cv:
        item["placing"], item["error"] = False, None
        item["decision"] = {"action": action, "stars": stars, "note": text, "result": " | ".join(lines),
                            "at": time.time(), "delivered": False}
        b.save()
        _cv.notify_all()
    return {"ok": True, "line": " | ".join(lines)}


def _answer(item: dict) -> str:
    d = item["decision"]
    d["delivered"] = True
    who = f"{item['name']} v{item['v']}"
    rated = f"{d['stars']}/10" if d["stars"] else "no rating"
    said = f" ({d['note']})" if d["note"] else ""
    if d["action"] == "place":
        return f"placed {who} in Studio, {rated}{said} | {d['result']}"
    if d["action"] == "keep":
        return f"kept {who} as it is, {rated}{said}: no new version wanted (the rating is recorded)."
    return (f"next: {who} rated {rated}{said}. Revise it from the note (the rating is recorded), "
            f"then call review({item['name']!r}) again.")


def wait(home, name: str, timeout: float | None = None, open_page: bool = True) -> str:
    """Block until the user presses Regenerate, Looks good or Place on the newest version of `name`."""
    b = board(home)
    timeout = float(os.environ.get("ASSET_AGENT_REVIEW_WAIT", 600)) if timeout is None else timeout
    page = url()
    with _cv:
        item = b.latest(name)
        if item is None:
            return f"nothing queued for {name}: make, build or revise it first"
        if not item["decision"] and open_page and time.time() - b.polled > 5:  # no page open: open one
            threading.Thread(target=webbrowser.open, args=(page,), daemon=True).start()
        end = time.time() + timeout
        while not item["decision"]:
            left = end - time.time()
            if left <= 0:
                return f"still waiting for the review of {name} v{item['v']} at {page}; call review again"
            _cv.wait(left)
            item = b.latest(name)  # a newer version may have arrived meanwhile
        out = _answer(item)
        b.save()
        return out


def state(b: Board) -> dict:
    b.polled = time.time()
    latest = {}
    for i in b.items:
        latest[i["name"]] = i["id"]
    return {"items": [{k: v for k, v in i.items() if k not in ("glb", "rated", "fx", "anim")} |
                      {"has_glb": bool(i["glb"]), "has_fx": bool(i.get("fx")), "has_anim": bool(i.get("anim")), "current": latest[i["name"]] == i["id"]}
                      for i in b.items]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # stdout is the MCP channel: never print there
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj).encode())

    def _authed(self, q) -> bool:
        given = self.headers.get("X-Review-Token") or q.get("t", [""])[0]
        if secrets.compare_digest(given, TOKEN):
            return True
        self._send(401, b"asset-agent review: missing or wrong token (open the newest review link)\n", "text/plain")
        return False

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if not self._authed(q):
            return
        if u.path == "/":
            return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if _board is None:
            return self._json(200, {"items": []})
        if u.path == "/state":
            with _cv:
                return self._json(200, state(_board))
        if u.path.startswith("/glb/"):
            with _cv:
                item = _board.get(int(u.path[5:])) if u.path[5:].isdigit() else None
            if item and item["glb"] and Path(item["glb"]).exists():
                return self._send(200, Path(item["glb"]).read_bytes(), "model/gltf-binary")
            return self._send(404, b"no model", "text/plain")
        if u.path.startswith("/anim/"):
            with _cv:
                item = _board.get(int(u.path[6:])) if u.path[6:].isdigit() else None
            return self._json(200, (item or {}).get("anim") or {})
        if u.path.startswith("/fx/"):
            with _cv:
                item = _board.get(int(u.path[4:])) if u.path[4:].isdigit() else None
            return self._json(200, (item or {}).get("fx") or {})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if not self._authed(parse_qs(u.query)):
            return
        if u.path != "/decide" or _board is None:
            return self._send(404, b"not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            res = decide(_board.home, int(body["id"]), body.get("action", ""), body.get("stars") or None,
                         body.get("pros", ""), body.get("cons", ""), background=True, notes=body.get("notes", ""))
        except (ValueError, KeyError) as e:
            res = {"ok": False, "error": f"bad request: {e}"}
        self._json(200 if res["ok"] else 409, res)
