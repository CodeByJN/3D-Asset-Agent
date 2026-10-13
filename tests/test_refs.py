"""Reference import from web pages: parsing, full-size URLs, sections, GIF frame sheets, search. Offline."""
import json

from PIL import Image

from asset_agent import refs

PAGE = """
<h2>EPIC Auras [ ]</h2>
<table><tr><td><img alt="Glock" src="https://static.wikia.nocookie.net/sol/images/a/ab/Glock.gif/revision/latest/scale-to-width-down/150?cb=1" width="150" data-image-name="Glock.gif"></td>
<td>Glock: 1 in 170,000</td></tr></table>
<h2>TRANSCENDENT Auras [ ]</h2>
<ul class="gallery"><li><img alt="Equinox" src="data:image/gif;base64,AAA" width="150" data-image-name="Equinox Collection.gif"> EQUINOX</li>
<li><img alt="icon" src="https://x/icon.png" width="16" data-image-name="icon.png"></li></ul>
"""


def test_find_images_sections_lazy_and_icons():
    found = refs.find_images(PAGE, "sol")
    names = [f["name"] for f in found]
    assert names == ["Glock.gif", "Equinox Collection.gif"]  # 16px icon skipped
    glock, eq = found
    assert glock["url"] == "https://static.wikia.nocookie.net/sol/images/a/ab/Glock.gif/revision/latest"  # full size
    assert glock["rarity"] == 170000 and glock["section"] == "EPIC Auras"
    assert eq["url"].startswith("https://static.wikia.nocookie.net/sol/images/") and "Equinox_Collection.gif" in eq["url"]
    assert eq["section"] == "TRANSCENDENT Auras" and "EQUINOX" in eq["caption"]
    assert [f["name"] for f in refs.find_images(PAGE, "sol", "transcendent")] == ["Equinox Collection.gif"]


def test_gif_frames_sheet_and_search(tmp_path):
    frames = [Image.new("RGB", (40, 40), (i * 40, 0, 0)) for i in range(6)]
    gif = tmp_path / "Aura.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50)
    sheet = refs._frames_sheet(gif, tmp_path / "Aura.frames.png", n=4, tile=30)
    assert Image.open(sheet).size == (120, 30)
    (tmp_path / "index.json").write_text(json.dumps([
        {"name": "Aura.gif", "file": "Aura.gif", "section": "TRANSCENDENT Auras", "caption": "Equinox", "rarity": None},
        {"name": "B.gif", "file": "B.gif", "section": "EPIC Auras", "caption": "Glock", "rarity": 170000}]))
    assert [e["name"] for e in refs.search(tmp_path, "transcendent")] == ["Aura.gif"]
    assert refs.search(tmp_path, "")[0]["name"] == "B.gif"  # rarest first


def test_unuploaded_textures_travel_inline():
    """Textures we haven't uploaded go to Studio as pixels (an EditableImage there), not a stand-in."""
    import base64
    from asset_agent import vfx
    nodes = [{"class": "ParticleEmitter", "props": {"Texture": "texture://star4"}},
             {"class": "Plane", "props": {"Image": "texture://no_such_texture"}}]
    inline = {}
    out = vfx.resolve_textures(nodes, ids={}, inline=inline)
    assert out[0]["props"]["Texture"] == "texture://star4" and set(inline) == {"star4"}
    packed = base64.b64decode(inline["star4"]["az"])  # alpha only (white texture), transparent runs packed
    assert len(packed) < inline["star4"]["n"] ** 2 / 2
    assert out[1]["props"]["Image"] == vfx.STAND_IN  # nothing to send: built-in stand-in
    assert vfx.resolve_textures(nodes, ids={"star4": "rbxassetid://1"})[0]["props"]["Texture"] == "rbxassetid://1"
