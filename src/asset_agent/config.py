"""User settings in ~/.asset-agent/config.json (ASSET_AGENT_CONFIG overrides the path). Env vars win."""
import json
import os
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8080"


def path() -> Path:
    return Path(os.environ.get("ASSET_AGENT_CONFIG") or Path.home() / ".asset-agent" / "config.json")


def load() -> dict:
    p = path()
    return json.loads(p.read_text()) if p.exists() else {}


def save(**kv) -> dict:
    """Set keys; a None value removes the key."""
    c = load()
    for k, v in kv.items():
        if v is None:
            c.pop(k, None)
        else:
            c[k] = v
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, indent=1))
    if os.name != "nt":
        p.chmod(0o600)  # holds the server key
    return c


def hunyuan_url() -> str:
    return (os.environ.get("HUNYUAN_URL") or load().get("url") or DEFAULT_URL).rstrip("/")


def hunyuan_key() -> str | None:
    return os.environ.get("HUNYUAN_KEY") or load().get("key")
