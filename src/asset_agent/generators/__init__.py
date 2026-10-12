from .base import GenResult, Generator, GeneratorError, generate
from .hf import HFSpaces

BACKENDS = {"hf": HFSpaces}


def get(name: str) -> Generator:
    if name not in BACKENDS:
        raise GeneratorError(f"unknown backend {name!r}; have {', '.join(BACKENDS)}")
    return BACKENDS[name]()


__all__ = ["BACKENDS", "GenResult", "Generator", "GeneratorError", "generate", "get"]
