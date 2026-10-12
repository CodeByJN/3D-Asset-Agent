"""Generator interface and cache, with a fake offline backend."""
import pytest

from asset_agent.generators import GenResult, Generator, GeneratorError, generate


class Fake(Generator):
    name = "fake"

    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail

    def submit(self, prompt=None, image=None, **opts):
        self.calls += 1
        return "job1"

    def poll(self, job):
        return f"error: {self.fail}" if self.fail else "done"

    def download(self, job, dest):
        (dest / "mesh.glb").write_bytes(b"glb")
        (dest / "image.png").write_bytes(b"png")
        return GenResult(dest / "mesh.glb", dest / "image.png", False, {"faces": 3})


def test_cache_hits_never_call_backend_twice(tmp_path):
    g = Fake()
    r1 = generate(g, prompt="chest", cache=tmp_path, seed=1)
    r2 = generate(g, prompt="chest", cache=tmp_path, seed=1)
    assert g.calls == 1 and r2.meta["cached"] and r2.mesh.read_bytes() == b"glb"
    assert "cached" in r2.summary() and r1.image.exists()
    generate(g, prompt="chest", cache=tmp_path, seed=2)  # different request -> new call
    assert g.calls == 2


def test_errors_are_one_line_and_not_cached(tmp_path):
    with pytest.raises(GeneratorError, match="quota"):
        generate(Fake(fail="AppError: GPU quota exceeded"), prompt="x", cache=tmp_path)
    assert not any(tmp_path.iterdir())
    with pytest.raises(GeneratorError):
        generate(Fake(), cache=tmp_path)
