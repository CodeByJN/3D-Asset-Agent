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


def cash():
    """A green banknote (coloured: use Color white)."""
    w, h = N, N // 2
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    bill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(bill)
    d.rounded_rectangle((8, 8, w - 8, h - 8), 26, fill=(46, 150, 72, 255))
    d.rounded_rectangle((26, 26, w - 26, h - 26), 18, outline=(180, 240, 170, 255), width=6)
    d.ellipse((w / 2 - 62, h / 2 - 62, w / 2 + 62, h / 2 + 62), fill=(120, 205, 120, 255))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 120)
    except OSError:
        font = ImageFont.load_default()
    d.text((w / 2, h / 2 + 4), "$", font=font, anchor="mm", fill=(30, 105, 50, 255))
    img.alpha_composite(bill, (0, (N - h) // 2))
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "cash.png", optimize=True)


# ---------------------------------------------------------------- aura ornaments (drawn at 2x, downsampled)

def _canvas(w, h, k=2):
    img = Image.new("L", (w * k, h * k), 0)
    return img, ImageDraw.Draw(img), k


def _finish(img, w, h, name, glow=0.0, blur=8):
    """Downsample a 2x line drawing; optionally add a soft glow around the strokes."""
    a = np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255
    if glow:
        g = np.asarray(img.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255
        a = np.clip(a + g * glow, 0, 1)
    _save(a, name)


def _diamond(d, cx, cy, r, fill=255, width=0):
    pts = [(cx, cy - r), (cx + r * 0.62, cy), (cx, cy + r), (cx - r * 0.62, cy)]
    if width:
        d.polygon(pts, outline=fill, width=width)
    else:
        d.polygon(pts, fill=fill)


def crest():
    """Title-plate backdrop: a gothic pointed arch with a quatrefoil, flanked by long tapered rule lines."""
    W, H = 1024, 512
    img, d, k = _canvas(W, H)
    cx, top, base = W * k / 2, 40 * k, 470 * k
    for inset, width in ((0, 9), (26, 5)):           # outer and inner pointed arch
        aw, ah = (120 - inset) * k, (base - top - inset * 2 * k)
        pts = []
        for i in range(41):                            # left side: straight then curving to the point
            t = i / 40
            x = cx - aw + aw * (t ** 2.2)
            y = base - inset * k - ah * t
            pts.append((x, y))
        pts += [(2 * cx - x, y) for x, y in reversed(pts)]
        d.line(pts, fill=255, width=width * k // 2, joint="curve")
    d.line([(cx, top + 70 * k), (cx, base - 30 * k)], fill=255, width=4 * k)      # spine
    for r, cy in ((34, 255), (16, 255)):
        _diamond(d, cx, cy * k, r * k, width=5 * k if r > 20 else 0)
    for side in (-1, 1):                               # rule lines: thick near the arch, tapering out
        for dy, th in ((-14, 7), (14, 3)):
            y = H * k / 2 + dy * k + 40 * k
            x0, x1 = cx + side * 130 * k, cx + side * (W * k / 2 - 30 * k)
            steps = 30
            for i in range(steps):
                xa = x0 + (x1 - x0) * i / steps
                xb = x0 + (x1 - x0) * (i + 1) / steps
                d.line([(xa, y), (xb, y)], fill=255, width=max(1, int(th * k * (1 - i / steps) + 1)))
        _diamond(d, cx + side * (W * k / 2 - 18 * k), H * k / 2 + 40 * k, 12 * k)
    _finish(img, W, H, "crest", glow=0.9)


def crown_ring():
    """A crown of ribbed arrowhead spikes radiating from a ring, as seen from below (lay it flat overhead)."""
    S = 1024
    img, d, k = _canvas(S, S)
    c, n = S * k / 2, 18
    d.ellipse((c - 300 * k, c - 300 * k, c + 300 * k, c + 300 * k), outline=255, width=10 * k)
    d.ellipse((c - 270 * k, c - 270 * k, c + 270 * k, c + 270 * k), outline=255, width=3 * k)
    for i in range(n):
        a = 2 * math.pi * i / n
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        base_r, tip_r, half = 300 * k, 500 * k, 9 * k
        tip = (c + ux * tip_r, c + uy * tip_r)
        bl = (c + ux * base_r + px * half, c + uy * base_r + py * half)
        br = (c + ux * base_r - px * half, c + uy * base_r - py * half)
        barb = 0.62  # arrowhead: barbs flare out, then notch back in to the shaft
        bx, by = c + ux * (base_r + (tip_r - base_r) * barb), c + uy * (base_r + (tip_r - base_r) * barb)
        nx, ny = c + ux * (base_r + (tip_r - base_r) * (barb + 0.06)), c + uy * (base_r + (tip_r - base_r) * (barb + 0.06))
        d.polygon([bl, (bx + px * half, by + py * half), (bx + px * half * 4.2, by + py * half * 4.2),
                   (nx + px * half * 1.2, ny + py * half * 1.2), tip, (nx - px * half * 1.2, ny - py * half * 1.2),
                   (bx - px * half * 4.2, by - py * half * 4.2), (bx - px * half, by - py * half), br], fill=215)
        d.line([(c + ux * base_r, c + uy * base_r), tip], fill=255, width=4 * k)   # rib
    _finish(img, S, S, "crown_ring", glow=0.7)


def card_sigil(seed=4):
    """A big rotating sigil: dial ring with ticks, circuit traces, a card chip in the middle, diamonds."""
    S = 1024
    img, d, k = _canvas(S, S)
    c = S * k / 2
    rng = np.random.default_rng(seed)
    for r, w in ((490, 6), (468, 2), (330, 5), (300, 2), (150, 4)):
        d.ellipse((c - r * k, c - r * k, c + r * k, c + r * k), outline=255, width=w * k)
    for i in range(120):                               # dial ticks
        a = 2 * math.pi * i / 120
        r0 = 470 if i % 10 else 440
        d.line([(c + math.cos(a) * r0 * k, c + math.sin(a) * r0 * k), (c + math.cos(a) * 488 * k, c + math.sin(a) * 488 * k)],
               fill=255, width=(4 if i % 10 == 0 else 2) * k)
    for i in range(12):                                # diamonds on the outer band
        a = 2 * math.pi * i / 12
        _diamond(d, c + math.cos(a) * 400 * k, c + math.sin(a) * 400 * k, 18 * k)
    for i in range(24):                                # circuit traces between the rings
        a = 2 * math.pi * i / 24 + rng.uniform(-0.05, 0.05)
        r1, r2 = 155, rng.uniform(220, 300)
        x1, y1 = c + math.cos(a) * r1 * k, c + math.sin(a) * r1 * k
        x2, y2 = c + math.cos(a) * r2 * k, c + math.sin(a) * r2 * k
        bend = a + rng.choice([-0.12, 0.12])
        x3, y3 = c + math.cos(bend) * (r2 + 20) * k, c + math.sin(bend) * (r2 + 20) * k
        d.line([(x1, y1), (x2, y2), (x3, y3)], fill=255, width=3 * k)
        d.ellipse((x3 - 7 * k, y3 - 7 * k, x3 + 7 * k, y3 + 7 * k), fill=255)
    w, h = 120 * k, 92 * k                             # card chip
    d.rounded_rectangle((c - w / 2, c - h / 2, c + w / 2, c + h / 2), 16 * k, outline=255, width=6 * k)
    for f in (-1 / 3, 1 / 3):
        d.line([(c - w / 2, c + h * f), (c + w / 2, c + h * f)], fill=255, width=4 * k)
    d.line([(c, c - h / 2), (c, c + h / 2)], fill=255, width=4 * k)
    _finish(img, S, S, "card_sigil", glow=0.6, blur=6)


def rune_ring(seed=9):
    """A thin band of angular glyphs (made up, not any real script) for a counter-rotating ring."""
    S = 1024
    img, d, k = _canvas(S, S)
    c = S * k / 2
    rng = np.random.default_rng(seed)
    for r in (500, 430):
        d.ellipse((c - r * k, c - r * k, c + r * k, c + r * k), outline=255, width=3 * k)
    n = 36
    for i in range(n):
        a = 2 * math.pi * i / n
        ux, uy, px, py = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
        g = lambda u, v: (c + ux * (465 + u) * k + px * v * k, c + uy * (465 + u) * k + py * v * k)
        strokes = [[(-22, -10), (22, -10)], [(-22, 10), (22, 10)], [(-22, 0), (22, 0)], [(-22, -10), (22, 10)],
                   [(-22, 10), (22, -10)], [(0, -12), (0, 12)], [(-22, -12), (-22, 12)], [(22, -12), (22, 12)]]
        for j in rng.choice(len(strokes), size=3, replace=False):
            d.line([g(*strokes[j][0]), g(*strokes[j][1])], fill=255, width=4 * k)
    _finish(img, S, S, "rune_ring", glow=0.5, blur=5)


def card():
    """The black card: rounded black card, gold border, chip and star (coloured: use Color white)."""
    S, w, h = N, 460, 290
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 28, fill=(14, 14, 18, 255), outline=(232, 190, 90, 255), width=7)
    d.rounded_rectangle((44, 92, 124, 152), 10, fill=(232, 190, 90, 255))
    for x in (70, 98):
        d.line([(x, 92), (x, 152)], fill=(150, 110, 40, 255), width=3)
    d.line([(44, 122), (124, 122)], fill=(150, 110, 40, 255), width=3)
    sx, sy, r = w - 90, 92, 46
    pts = [(sx + math.cos(-math.pi / 2 + i * math.pi / 5) * (r if i % 2 == 0 else r * 0.42),
            sy + math.sin(-math.pi / 2 + i * math.pi / 5) * (r if i % 2 == 0 else r * 0.42)) for i in range(10)]
    d.polygon(pts, fill=(245, 205, 105, 255))
    for i in range(4):
        d.rounded_rectangle((44 + i * 92, 200, 44 + i * 92 + 70, 216), 4, fill=(90, 90, 100, 255))
    img.alpha_composite(c, ((S - w) // 2, (S - h) // 2))
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "card.png", optimize=True)


def star4():
    """Four-point star flare: thin bright spikes on a soft core (Transcendent-tier flashes)."""
    x, y, r, a = _grid()
    spikes = np.exp(-np.abs(y) / 0.012) * np.exp(-np.abs(x) / 0.55) + np.exp(-np.abs(x) / 0.012) * np.exp(-np.abs(y) / 0.55)
    diag = (np.exp(-np.abs(x - y) / 0.02) + np.exp(-np.abs(x + y) / 0.02)) * np.exp(-r / 0.25) * 0.35
    core = np.exp(-(r / 0.09) ** 2) + 0.45 * np.exp(-(r / 0.28) ** 2)
    _save(np.clip(spikes + diag + core, 0, 1) * _edge(r, 0.8), "star4")


def shards(seed=7):
    """Crystalline wings: long sharp light shards fanning out left and right from the centre."""
    rng = np.random.default_rng(seed)
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    for side in (-1, 1):
        for k in range(17):
            ang = math.radians(rng.uniform(-62, 62))
            L = N * 0.5 * rng.uniform(0.45, 1.0) * (1 - 0.35 * abs(ang) / 1.1)
            w = rng.uniform(0.012, 0.032) * N
            tip = (c + side * math.cos(ang) * L, c - math.sin(ang) * L)
            nx, ny = -math.sin(ang) * w, -math.cos(ang) * w
            d.polygon([(c + side * nx * 0.2, c + ny * 0.2), (c - side * nx * 0.2, c - ny * 0.2), tip], fill=int(rng.uniform(150, 255)))
    a = np.asarray(img.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    glow_a = np.asarray(img.filter(ImageFilter.GaussianBlur(10)), np.float32) / 255
    _, _, r, _ = _grid()
    _save(np.clip(a + 0.6 * glow_a, 0, 1) * _edge(r, 0.85), "shards")


def vortex(seed=5):
    """Swirling cloud disc seen from above, bright rim and calm eye (floor of an aura)."""
    x, y, r, a = _grid()
    n = _noise(N, seed)
    swirl = 0.5 + 0.5 * np.sin(a * 3 + r * 14 + n * 4)
    band = np.exp(-((r - 0.62) / 0.28) ** 2)
    eye = 1 - np.exp(-(r / 0.16) ** 2) * 0.85
    _save(np.clip(swirl * band * eye * (0.55 + 0.6 * n), 0, 1) * _edge(r, 0.8), "vortex")


def orb():
    """A shaded sphere with a bright rim (sun / moon orbs; tint it with the plane colour)."""
    x, y, r, _ = _grid()
    inside = r < 0.82
    shade = np.where(inside, 0.65 + 0.35 * np.sqrt(np.clip(1 - (r / 0.82) ** 2, 0, 1)), 0)
    rim = np.exp(-((r - 0.82) / 0.045) ** 2)
    halo = np.exp(-((r - 0.82) / 0.16) ** 2) * (r > 0.82) * 0.5
    _save(np.clip(shade + rim + halo, 0, 1) * _edge(r, 0.9), "orb")


def pillar():
    """A vertical beam of light, brightest at its core, fading at the ends."""
    x, y, r, _ = _grid()
    core = np.exp(-(x / 0.06) ** 2) + 0.55 * np.exp(-(x / 0.22) ** 2)
    ends = np.clip((1 - np.abs(y)) / 0.35, 0, 1) ** 1.5
    _save(np.clip(core, 0, 1) * ends, "pillar")


def crown_spikes(seed=2):
    """An arc of tall spikes (a crown of light behind the head)."""
    rng = np.random.default_rng(seed)
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    cx, base = N / 2, N * 0.78
    for k in range(9):
        t = (k - 4) / 4
        x0 = cx + t * N * 0.38
        h = N * (0.62 - 0.28 * abs(t)) * rng.uniform(0.9, 1.05)
        w = N * 0.05
        lean = t * N * 0.08
        d.polygon([(x0 - w, base - abs(t) * N * 0.12), (x0 + w, base - abs(t) * N * 0.12), (x0 + lean, base - h)], fill=255)
    d.ellipse((cx - N * 0.4, base - N * 0.06, cx + N * 0.4, base + N * 0.06), fill=200)
    a = np.asarray(img.filter(ImageFilter.GaussianBlur(1.5)), np.float32) / 255
    g = np.asarray(img.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
    _save(np.clip(a + 0.7 * g, 0, 1), "crown_spikes")


def streak():
    """A thin bright streak (light rays, shards flying off)."""
    x, y, r, _ = _grid()
    _save(np.exp(-(x / 0.05) ** 2) * np.clip(1 - np.abs(y), 0, 1) ** 1.2, "streak")


ALL = [glow, glow_hot, rays, ring, shockwave, sparkle, smoke, slash, bolts, coin, cash,
       crest, crown_ring, card_sigil, rune_ring, card, star4, shards, vortex, orb, pillar, crown_spikes, streak]

if __name__ == "__main__":
    for fn in ALL:
        fn()
        print(fn.__name__, (OUT / f"{fn.__name__}.png").stat().st_size // 1024, "KB")
