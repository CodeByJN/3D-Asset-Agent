from .base import GenResult, Generator, GeneratorError, generate
from .hf import HFSpaces, LocalHunyuan, local_status

BACKENDS = {"hf": HFSpaces, "local": LocalHunyuan}


def get(name: str = "auto") -> Generator:
    """auto: your GPU server (local or remote) when it is up, else the free hf Spaces."""
    if name == "auto":
        state = local_status()
        if state == "wrong key":
            raise GeneratorError("Hunyuan server rejected the key; run: asset-agent connect URL --key KEY")
        name = "local" if state == "ok" else "hf"
    if name not in BACKENDS:
        raise GeneratorError(f"unknown backend {name!r}; have auto, {', '.join(BACKENDS)}")
    return BACKENDS[name]()


__all__ = ["BACKENDS", "GenResult", "Generator", "GeneratorError", "generate", "get", "local_status"]
