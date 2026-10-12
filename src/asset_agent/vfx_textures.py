"""Procedural HD particle textures, ours to ship: white shapes on transparent (colour comes from
each emitter's Color), except `coin`. Run as a module to (re)write library/vfx/textures/*.png.

Flipbooks are 4x4 grids (1024 px, 256 px frames) for ParticleFlipbookLayout.Grid4x4.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parents[2] / "library" / "vfx" / "textures"
N = 512


def _grid(n=N):
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    x, y = (x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1
    return x, y, np.hypot(x, y), np.arctan2(y, x)


def _save(alpha, name, rgb=None):
    a = np.clip(alpha, 0, 1)
    img = np.zeros(a.shape + (4,), np.uint8)
    img[..., :3] = 255 if rgb is None else rgb
    img[..., 3] = (a * 255 + 0.5).astype(np.uint8)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, "RGBA").save(OUT / f"{name}.png", optimize=True)


def _edge(r, start=0.9):
    """1 inside, smoothly 0 at the texture edge (no hard square cut-off)."""
    return np.clip((1 - r) / (1 - start), 0, 1) ** 2


def glow():
    x, y, r, _ = _grid()
    _save(np.exp(-(r / 0.42) ** 2) * _edge(r, 0.75), "glow")


def glow_hot():
    x, y, r, _ = _grid()
    _save((0.65 * np.exp(-(r / 0.12) ** 2) + 0.5 * np.exp(-(r / 0.45) ** 2)) * _edge(r, 0.75), "glow_hot")


def rays(seed=3, spokes=22):
    x, y, r, t = _grid()
    rng = np.random.default_rng(seed)
    a = np.zeros_like(r)
    for _ in range(spokes):
        ang, w, length = rng.uniform(-math.pi, math.pi), rng.uniform(0.015, 0.05), rng.uniform(0.55, 0.98)
        d = np.angle(np.exp(1j * (t - ang)))
        a = np.maximum(a, np.exp(-(d / w) ** 2) * np.clip(1 - r / length, 0, 1) ** 1.5 * rng.uniform(0.55, 1))
    _save(np.maximum(a, 0.8 * np.exp(-(r / 0.12) ** 2)) * _edge(r), "rays")


def ring():
    x, y, r, _ = _grid()
    _save(np.exp(-((r - 0.78) / 0.035) ** 2) + 0.25 * np.exp(-((r - 0.74) / 0.12) ** 2) * (r < 0.8), "ring")


def shockwave():
    x, y, r, _ = _grid()
    inner = np.clip((r - 0.35) / 0.5, 0, 1) ** 2.2  # soft inside, bright leading edge
    _save(inner * np.exp(-((r - 0.85) / 0.09) ** 2 * (r > 0.85)) * _edge(r, 0.93), "shockwave")


def sparkle():
    x, y, r, _ = _grid()
    arm = lambda u, v: np.exp(-(np.abs(u) / 0.55) ** 1.3) * np.exp(-(v / (0.018 + 0.02 * np.abs(u))) ** 2)
    diag = lambda u, v: arm((u + v) / 1.4142, (u - v) / 1.4142)
    a = np.maximum(np.maximum(arm(x, y), arm(y, x)), 0.35 * np.maximum(diag(x, y), diag(y, x)))
    _save(np.maximum(a, np.exp(-(r / 0.09) ** 2)) * _edge(r), "sparkle")


def _noise(n, seed, octaves=5):
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n), np.float32)
    for o in range(octaves):
        k = 4 * 2 ** o
        g = Image.fromarray((rng.random((k, k)) * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)
        out += np.asarray(g, np.float32) / 255 / 2 ** o
    return out / sum(1 / 2 ** o for o in range(octaves))


def smoke(seed=11):
    x, y, r, _ = _grid()
    n = _noise(N, seed)
    _save(np.clip((n - 0.32) * 2.2, 0, 1) * np.exp(-(r / 0.62) ** 2) * _edge(r, 0.8), "smoke")


def slash():
    """A crescent arc, thick and bright in the middle, tapering to points."""
    x, y, r, t = _grid()
    span = (t > -2.3) & (t < 0.6)
    u = np.clip((t + 2.3) / 2.9, 0, 1)                      # 0..1 along the arc
    taper = np.clip(np.sin(u * math.pi), 0, 1) ** 0.8
    thick = 0.02 + 0.09 * taper
    d = (r - 0.7) / thick
    core = np.exp(-d ** 2) * taper
    trail = np.exp(-((r - 0.62) / (0.06 + 0.12 * taper)) ** 2) * taper * 0.35 * (r < 0.7)
    _save((core + trail) * span * _edge(r, 0.92), "slash")


def _bolt(draw, rng, start, ang, length, width, depth=0):
    pts, (x, y) = [start], start
    steps = 14
    for i in range(steps):
        ang += rng.normal(0, 0.28)  # jagged but heading outward
        x, y = x + math.cos(ang) * length / steps, y + math.sin(ang) * length / steps
        pts.append((x, y))
        if depth < 2 and rng.random() < 0.14:
            _bolt(draw, rng, (x, y), ang + rng.choice([-1, 1]) * rng.uniform(0.4, 1.0), length * 0.45, max(1, width * 0.55), depth + 1)
    draw.line(pts, fill=255, width=max(1, int(width)), joint="curve")


def bolts(seed=21):
    """4x4 flipbook of crackling lightning from the centre outward (one fresh pattern per frame)."""
    rng = np.random.default_rng(seed)
    f, sheet = 256, Image.new("L", (1024, 1024), 0)
    for i in range(16):
        core = Image.new("L", (f * 2, f * 2), 0)   # draw at 2x, downsample for clean edges
        d = ImageDraw.Draw(core)
        for _ in range(rng.integers(2, 4)):
            _bolt(d, rng, (f, f), rng.uniform(-math.pi, math.pi), f * rng.uniform(0.85, 0.98), 9)
        glow_l = core.filter(ImageFilter.GaussianBlur(14))
        a = np.clip(np.asarray(core, np.float32) / 255 + np.asarray(glow_l, np.float32) / 255 * 2.2, 0, 1)
        frame = Image.fromarray((a * 255).astype(np.uint8)).resize((f, f), Image.LANCZOS)
        sheet.paste(frame, ((i % 4) * f, (i // 4) * f))
    _save(np.asarray(sheet, np.float32) / 255, "bolts")


def coin():
    """A gold coin with a $ (coloured: use Color white)."""
    s = N
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((24, 24, s - 24, s - 24), fill=(214, 150, 22, 255))
    d.ellipse((44, 44, s - 44, s - 44), fill=(255, 205, 64, 255))
    d.ellipse((70, 70, s - 70, s - 70), fill=(255, 222, 110, 255))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 300)
    except OSError:
        font = ImageFont.load_default()
    d.text((s / 2, s / 2 + 8), "$", font=font, anchor="mm", fill=(196, 128, 8, 255))
    shine = Image.new("RGBA", (s, s), (0, 0, 0, 0))  # drawn on its own layer: ImageDraw replaces, it doesn't blend
    ImageDraw.Draw(shine).ellipse((120, 92, 230, 150), fill=(255, 250, 225, 150))
    img.alpha_composite(shine.filter(ImageFilter.GaussianBlur(6)))
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "coin.png", optimize=True)


ALL = [glow, glow_hot, rays, ring, shockwave, sparkle, smoke, slash, bolts, coin]

if __name__ == "__main__":
    for fn in ALL:
        fn()
        print(fn.__name__, (OUT / f"{fn.__name__}.png").stat().st_size // 1024, "KB")
