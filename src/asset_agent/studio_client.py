"""Talk to Roblox Studio's built-in MCP server directly (as an MCP client), so long Luau scripts
and screenshots go between this server and Studio without passing through the chat.

Studio must be open with Assistant > ... > Manage MCP Servers > "Enable Studio as MCP server".
Argument names are read from Studio's own tool schemas, so small API changes don't break us.
"""
import asyncio
import base64
import json
import os
import re
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class StudioError(RuntimeError):
    pass


def launcher() -> StdioServerParameters:
    if os.environ.get("ASSET_AGENT_STUDIO_MCP"):
        return StdioServerParameters(command=os.environ["ASSET_AGENT_STUDIO_MCP"])
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox"
    exes = sorted(root.glob("Versions/*/StudioMCP.exe"), key=lambda p: p.stat().st_mtime)
    if exes:  # newest Studio's proxy (Roblox's mcp.bat does the same, noisily)
        return StdioServerParameters(command=str(exes[-1]))
    if (root / "mcp.bat").exists():
        return StdioServerParameters(command="cmd.exe", args=["/c", str(root / "mcp.bat")])
    raise StudioError("Roblox Studio MCP not found: open Studio > Assistant > ... > Manage MCP Servers > "
                      "Enable Studio as MCP server")


def _text(res) -> str:
    return "\n".join(b.text for b in getattr(res, "content", []) if getattr(b, "type", "") == "text")


def _images(res) -> list[bytes]:
    return [base64.b64decode(b.data) for b in getattr(res, "content", []) if getattr(b, "type", "") == "image"]


class Studio:
    """One connection for a batch of calls: `async with Studio() as s: await s.luau(code)`."""

    def __init__(self, timeout: float = 120):
        self.timeout = timeout
        self.tools: dict[str, dict] = {}
        self.studio_id = None

    async def __aenter__(self):
        self._cm = stdio_client(launcher())
        read, write = await self._cm.__aenter__()
        self._sess_cm = ClientSession(read, write)
        self.s = await self._sess_cm.__aenter__()
        await asyncio.wait_for(self.s.initialize(), 30)
        self.tools = {t.name: getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                      for t in (await self.s.list_tools()).tools}
        return self

    async def _studio(self):
        """The connected Studio's id, looked up on first use."""
        if self.studio_id is None and "list_roblox_studios" in self.tools:
            for _ in range(20):  # Studio registers with a fresh proxy a second or two after it starts
                text = _text(await self.s.call_tool("list_roblox_studios", {}))
                if '"studios":[]' not in text.replace(" ", ""):
                    break
                await asyncio.sleep(0.5)
            self.studio_id = self._pick_studio(text)
        return self.studio_id

    async def __aexit__(self, *exc):
        await self._sess_cm.__aexit__(*exc)
        await self._cm.__aexit__(*exc)

    @staticmethod
    def _pick_studio(text: str):
        """First studio id in list_roblox_studios output (JSON or text)."""
        try:
            d = json.loads(text)
            items = d if isinstance(d, list) else d.get("studios") or d.get("instances") or [d]
            # a Studio with a place open has a name; a bare start page doesn't
            items = sorted(items, key=lambda it: not (isinstance(it, dict) and it.get("name")))
            for it in items:
                for k in ("studio_id", "studioId", "id"):
                    if isinstance(it, dict) and it.get(k) is not None:
                        return it[k]
        except (ValueError, AttributeError):
            pass
        m = re.search(r"(?:studio_?id|id)\W+([\w-]+)", text, re.I)
        if not m:
            raise StudioError(f"no Studio is connected ({' '.join(text.split())[:150]}): open a place in Studio")
        return m.group(1)

    def _args(self, tool: str, **kw) -> dict:
        props = self.tools.get(tool, {}).get("properties", {})
        return {k: v for k, v in kw.items() if k in props}

    async def call(self, tool: str, **kw):
        if tool not in self.tools:
            raise StudioError(f"Studio MCP has no {tool}; it has {', '.join(self.tools)}")
        if "studio_id" in self.tools[tool].get("properties", {}) and "studio_id" not in kw:
            kw["studio_id"] = await self._studio()
        res = await asyncio.wait_for(self.s.call_tool(tool, kw), self.timeout)
        if getattr(res, "is_error", None) or getattr(res, "isError", None):
            raise StudioError(f"{tool}: {' '.join(_text(res).split())[:250]}")
        return res

    async def luau(self, code: str, datamodel: str = "Edit") -> str:
        props = self.tools.get("execute_luau", {}).get("properties", {})
        code_key = next((k for k in ("code", "source", "script", "luau") if k in props),
                        next((k for k, v in props.items() if v.get("type") == "string"
                              and k not in ("studio_id", "datamodel_type")), "code"))
        args = self._args("execute_luau", datamodel_type=datamodel)
        args[code_key] = code.lstrip("﻿")  # a byte-order mark (PowerShell-saved files) hangs Studio
        return _text(await self.call("execute_luau", **args))

    async def capture(self, out: Path, camera=None, look_at=None) -> Path:
        """Viewport screenshot to `out`. camera/look_at: [x,y,z] (argument names from the schema)."""
        props = self.tools.get("screen_capture", {}).get("properties", {})
        self._captures = getattr(self, "_captures", 0) + 1
        args = self._args("screen_capture", capture_id=f"ScreenCapture_{self._captures}")
        for want, val in (("camera", camera), ("look", look_at)):
            if val is None:
                continue
            key = next((k for k in props if want in k.lower()), None)
            if key:
                args[key] = _vec_arg(props[key], val)
        res = await self.call("screen_capture", **args)
        imgs = _images(res)
        if not imgs:
            raise StudioError(f"screen_capture returned no image: {' '.join(_text(res).split())[:200]}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(imgs[0])
        return out


def _vec_arg(schema: dict, v):
    """A vector in whatever shape the schema asks for: [x,y,z], {x,y,z} or 'x,y,z'."""
    t = schema.get("type")
    if t == "object":
        return dict(zip("xyz", v))
    if t == "string":
        return ",".join(f"{x:g}" for x in v)
    return list(v)


def run(fn):
    """Run `async fn(studio)` on a fresh connection and return its result."""
    async def main():
        async with Studio() as s:
            return await fn(s)
    return asyncio.run(main())


def describe() -> str:
    """Studio MCP tools and their argument names (for debugging)."""
    async def fn(s):
        return "\n".join(f"{n}({', '.join(sch.get('properties', {}))})" for n, sch in s.tools.items()) + \
            f"\nstudio_id={s.studio_id}"
    return run(fn)
