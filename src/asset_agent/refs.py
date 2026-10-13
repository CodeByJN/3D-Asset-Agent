"""Reference images from the web: a game's wiki page -> images + captions in a project's refs folder.

A wiki shows every character, item, VFX and animation of a game; those images are what new assets are checked
against (character/preview refs) and what a project's style is drawn from. Fandom pages are read through
their API (lazy-loaded images included) and every image is fetched at full size.

import_page(url, out_dir, only=None, limit=80) writes out_dir/index.json:
    [{name, file, frames (a still sheet of an animated GIF), caption, rarity, source}]
"""
import hashlib
import html as htmlmod
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "asset-agent/0.1 (reference image importer)"}


def _get(url: str, timeout: float = 40) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def page_html(url: str) -> tuple[str, str]:
    """(html, site) for a page; Fandom/MediaWiki pages through their parse API so lazy images are listed."""
    u = urllib.parse.urlparse(url)
    m = re.match(r"/wiki/(.+)", u.path)
    if m and ("fandom.com" in u.netloc or "wiki" in u.netloc):
        api = f"{u.scheme}://{u.netloc}/api.php?action=parse&page={m.group(1)}&prop=text&format=json&formatversion=2"
        return json.loads(_get(api))["parse"]["text"], u.netloc.split(".")[0]
    return _get(url).decode("utf-8", "replace"), u.netloc.split(".")[0]


def _full(src: str) -> str:
    """Full-size image URL (drop Fandom's scale-to-width step and cache buster)."""
    src = re.sub(r"/revision/latest/scale-to-[^/?]+/\d+", "/revision/latest", src)
    return src.split("?")[0]


def _fandom_url(site: str, name: str) -> str:
    """MediaWiki's image path for a file name: images/<h0>/<h0h1>/<name>."""
    n = name.replace(" ", "_")
    h = hashlib.md5(n.encode()).hexdigest()
    return f"https://static.wikia.nocookie.net/{site}/images/{h[0]}/{h[:2]}/{urllib.parse.quote(n)}/revision/latest"


def _text(fragment: str) -> str:
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def find_images(html: str, site: str, only: str | None = None, min_px: int = 48) -> list[dict]:
    """Images on the page with the text of their table row / gallery item as caption."""
    words = [w.lower() for w in (only or "").split() if w]
    out, seen = [], set()
    heads = [(h.start(), _text(h.group(0)).replace("[ ]", "").strip())
             for h in re.finditer(r"<h[234][^>]*>.*?</h[234]>", html, re.S)]
    for m in re.finditer(r"<img\b[^>]*>", html):
        tag = m.group(0)
        section = next((t for pos, t in reversed(heads) if pos < m.start()), "")  # e.g. "MYTHIC Auras"

        def attr(k):
            a = re.search(rf'\b{k}="([^"]*)"', tag)
            return htmlmod.unescape(a.group(1)) if a else None
        name = attr("data-image-name") or attr("alt") or ""
        w = attr("width")
        if not name or (w and w.isdigit() and int(w) < min_px) or name in seen:
            continue
        src = next((s for s in (attr("data-src"), attr("src")) if s and not s.startswith("data:")), None)
        url = _full(src) if src else (_fandom_url(site, name) if "." in name else None)
        if not url:
            continue
        start = max(html.rfind("<tr", 0, m.start()), html.rfind("<li", 0, m.start()), html.rfind("<figure", 0, m.start()))
        end_tags = [html.find(t, m.end()) for t in ("</tr>", "</li>", "</figure>")]
        end = min([e for e in end_tags if e > 0] or [m.end() + 400])
        caption = _text(html[start:end])[:220] if start >= 0 and end - start < 6000 else ""
        rarity = re.search(r"1 in ([\d,]+)", caption)
        item = {"name": name, "url": url, "section": section, "caption": caption,
                "rarity": int(rarity.group(1).replace(",", "")) if rarity else None}
        hay = (name + " " + section + " " + caption).lower()
        if words and not all(wd in hay for wd in words):
            continue
        seen.add(name)
        out.append(item)
    return out


def _frames_sheet(path: Path, out: Path, n: int = 6, tile: int = 150) -> Path | None:
    """A row of n frames from an animated GIF, so motion can be judged from one still image."""
    from PIL import Image, ImageSequence
    im = Image.open(path)
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    if len(frames) < 2:
        return None
    pick = [frames[int(i * (len(frames) - 1) / (n - 1))] for i in range(n)]
    sheet = Image.new("RGB", (tile * n, tile), (20, 20, 24))
    for i, f in enumerate(pick):
        f.thumbnail((tile, tile))
        sheet.paste(f, (i * tile + (tile - f.width) // 2, (tile - f.height) // 2))
    sheet.save(out)
    return out


def import_page(url: str, out_dir: Path, only: str | None = None, limit: int = 80) -> tuple[str, list[dict]]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html, site = page_html(url)
    found = find_images(html, site, only)
    idx_file = out_dir / "index.json"
    index = {e["name"]: e for e in (json.loads(idx_file.read_text()) if idx_file.exists() else [])}
    from concurrent.futures import ThreadPoolExecutor

    def fetch(item):
        f = out_dir / re.sub(r"[^\w.\-]+", "_", item["name"])
        try:
            if not f.exists():
                f.write_bytes(_get(item["url"]))
        except Exception:
            return item, None
        e = {**item, "file": f.name, "source": url}
        if f.suffix.lower() == ".gif":
            try:
                sheet = _frames_sheet(f, out_dir / (f.stem + ".frames.png"))
                if sheet:
                    e["frames"] = sheet.name
            except Exception:
                pass
        return item, e
    with ThreadPoolExecutor(8) as pool:  # wiki GIFs are big: fetch several at once
        results = list(pool.map(fetch, found[:limit]))
    failed = sum(1 for _, e in results if e is None)
    got = len(results) - failed
    for item, e in results:
        if e:
            index[item["name"]] = e
    idx_file.write_text(json.dumps(list(index.values()), indent=1))
    line = (f"{got} images from {url}" + (f" matching {only!r}" if only else "") +
            f" -> {out_dir.as_posix()} ({len(found)} on the page" + (f", {failed} failed" if failed else "") + ")")
    return line, [index[i["name"]] for i in found[:limit] if i["name"] in index]


def search(out_dir: Path, query: str = "", n: int = 20) -> list[dict]:
    """Imported references whose name or caption contain every word of query, rarest first."""
    entries = []
    for idx in Path(out_dir).rglob("index.json"):
        for e in json.loads(idx.read_text()):
            e["dir"] = idx.parent.as_posix()
            entries.append(e)
    words = [w.lower() for w in query.split()]
    hits = [e for e in entries
            if all(w in (e["name"] + " " + e.get("section", "") + " " + e.get("caption", "")).lower() for w in words)]
    return sorted(hits, key=lambda e: -(e.get("rarity") or 0))[:n]
