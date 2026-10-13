"""Side-by-side benchmark GIF: one row per task, native Claude vs the harness, each cell playing the
first result then the revision, with time and tokens under it. Reads frames/ and results.json."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
TASKS = [("palm_tree", "Palm tree"), ("ssj_aura", "Super Saiyan aura"), ("run_anim", "R15 run cycle\n(1/3 speed)")]
SIDES = [("native", "Claude (native)"), ("harness", "Claude + asset-agent")]
CELL, LABEL_W, HEAD_H, FOOT_H, PAD = 300, 178, 70, 56, 8
BG, INK, DIM = (18, 20, 26), (236, 238, 244), (150, 156, 170)
COLS = {"native": (232, 120, 90), "harness": (90, 200, 140)}


def font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def square(img):
    w, h = img.size
    s = min(w, h)
    return img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((CELL, CELL), Image.LANCZOS)


def frames(task, side, v, n, loop=False):
    d = HERE / "frames" / task / f"{side}_{v}"
    files = sorted(d.glob("f*.png")) if d.exists() else []
    if not files:
        blank = Image.new("RGB", (CELL, CELL), (40, 42, 50))
        ImageDraw.Draw(blank).text((CELL // 2, CELL // 2), "no output", fill=DIM, font=font(18), anchor="mm")
        return [blank] * n
    imgs = [square(Image.open(f).convert("RGB")) for f in files]
    if loop:  # play at the recorded rate (animations: same slow-motion for every clip)
        return [imgs[i % len(imgs)] for i in range(n)]
    return [imgs[i * len(imgs) // n] for i in range(n)]


def k(t):
    return f"{t / 1e6:.2f}M" if t >= 1e6 else f"{t / 1000:.0f}k" if t >= 1000 else str(t)


def foot(r):
    if not r:
        return "not run", ""
    c, v = r.get("create", {}), r.get("revise", {})
    line = lambda w, x: f"{w} {x['seconds']:.0f}s · {k(x['context_tokens'])} tok · {x['tool_calls']} calls"
    return line("make", c) if c else "not run", line("revise", v) if v else ""


def main(n=24):
    res = json.loads((HERE / "results.json").read_text())
    W = LABEL_W + len(SIDES) * (CELL + PAD) + PAD
    H = HEAD_H + len(TASKS) * (CELL + FOOT_H + PAD) + 34
    clips = {(t, s, v): frames(t, s, v, n, loop=t == "run_anim") for t, _ in TASKS for s, _ in SIDES for v in ("v1", "v2")}
    out = []
    for i in range(2 * n):
        v = "v1" if i < n else "v2"
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((PAD + 4, 12), "Benchmark", fill=INK, font=font(22, True))
        d.text((PAD + 4, 42), "first try" if v == "v1" else "after one revision", fill=DIM, font=font(15))
        for j, (s, name) in enumerate(SIDES):
            x = LABEL_W + j * (CELL + PAD)
            d.text((x + CELL // 2, 36), name, fill=COLS[s], font=font(19, True), anchor="mm")
        for r, (t, tname) in enumerate(TASKS):
            y = HEAD_H + r * (CELL + FOOT_H + PAD)
            d.multiline_text((PAD + 4, y + CELL // 2 - 34), tname, fill=INK, font=font(17, True))
            rev = json.loads((HERE / "tasks.json").read_text())[t]["revision"].split(":", 1)[1].split(".")[0].strip()
            d.multiline_text((PAD + 4, y + CELL // 2 + 14), "\n".join(_wrap(f"rev: {rev}", 21)), fill=DIM, font=font(12))
            for j, (s, _) in enumerate(SIDES):
                x = LABEL_W + j * (CELL + PAD)
                im.paste(clips[(t, s, v)][i % n], (x, y))
                d.text((x + 8, y + 6), v, fill=INK, font=font(14, True))
                a, b = foot(res.get(t, {}).get(s))
                d.text((x + 4, y + CELL + 6), a, fill=INK, font=font(14))
                d.text((x + 4, y + CELL + 28), b, fill=DIM, font=font(14))
        d.text((PAD + 4, H - 26), "tok = total tokens processed (input incl. cached + output). Same model and tools; "
               "the harness side adds asset-agent.", fill=DIM, font=font(12))
        out.append(im)
    path = HERE.parent / "docs" / "benchmark.gif"
    out[0].save(path, save_all=True, append_images=out[1:], duration=110, loop=0, optimize=True)
    return path


def _wrap(s, w):
    lines, cur = [], ""
    for word in s.split():
        if len(cur) + len(word) + 1 > w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur]


if __name__ == "__main__":
    print(main())
