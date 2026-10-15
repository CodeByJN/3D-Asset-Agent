"""One long-lived headless Blender that keeps meshes loaded between calls (see bpy_session.py).

    s = BlenderSession()          # or session() for the shared one
    s.call("open", path="raw.glb", name="crate")
    s.call("inspect", name="crate")

Started on first use and again if it dies; a command that hangs past its timeout kills the process (the
next call starts a fresh one, with nothing loaded).
"""
import json
import queue
import subprocess
import threading
from pathlib import Path

from .blender import BlenderError, find_blender

SCRIPT = Path(__file__).with_name("bpy_session.py")
REPLY = "@@asset-agent@@ "


class BlenderSession:
    def __init__(self, timeout: float = 900):
        self.timeout = timeout
        self.proc = None
        self.lines: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.log: list[str] = []  # Blender's own output, for errors

    def _start(self):
        self.proc = subprocess.Popen(
            [find_blender(), "-b", "--factory-startup", "-noaudio", "-P", str(SCRIPT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, args=(self.proc, self.lines), daemon=True).start()
        self._read(120)  # the ready line

    def _pump(self, proc, lines):
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    def _read(self, timeout):
        while True:
            try:
                line = self.lines.get(timeout=timeout)
            except queue.Empty:
                self.close()
                raise BlenderError(f"Blender didn't answer within {timeout:.0f}s; restarted it (open meshes again)")
            if line is None:
                tail = " | ".join(self.log[-3:])
                self.proc = None
                raise BlenderError(f"Blender quit ({tail[:200]}); it restarts on the next call")
            if line.startswith(REPLY):
                return json.loads(line[len(REPLY):])
            self.log = (self.log + [line.strip()])[-50:]

    def call(self, cmd: str, timeout: float | None = None, **args):
        """Run one command; returns its result or raises BlenderError with Blender's message."""
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(json.dumps({"cmd": cmd, **args}) + "\n")
            self.proc.stdin.flush()
            reply = self._read(timeout or self.timeout)
        if not reply.get("ok"):
            raise BlenderError(reply.get("error", "failed"))
        return reply["result"]

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


_shared = None


def session() -> BlenderSession:
    global _shared
    if _shared is None:
        _shared = BlenderSession()
    return _shared
