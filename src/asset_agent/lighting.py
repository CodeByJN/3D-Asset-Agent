"""Lighting presets for the open Studio place: the "shader pack" look (warm sun, soft shadows,
atmospheric haze, bloom, god rays, graded colour, clouds) that makes glow and VFX read well.

studio("lighting:shader_night") applies one; studio("lighting") lists them. Values use the tagged JSON
of luau.py ({"c3": [r,g,b]} etc.). Effects we add are tagged AssetAgentLighting and replaced each time.
"""
from . import luau


def _c(r, g, b):
    return {"c3": [r / 255, g / 255, b / 255]}


PRESETS = {
    "shader_dusk": {
        "use": "golden hour, like a Minecraft shader pack: low warm sun, long soft shadows, haze, god rays, bloom",
        "lighting": {"Technology": {"enum": "Technology.Future"}, "ClockTime": 17.6, "GeographicLatitude": 35,
                     "Brightness": 3.2, "ExposureCompensation": 0.15, "EnvironmentDiffuseScale": 1,
                     "EnvironmentSpecularScale": 1, "ShadowSoftness": 0.25, "GlobalShadows": True,
                     "Ambient": _c(40, 34, 48), "OutdoorAmbient": _c(120, 104, 120)},
        "atmosphere": {"Density": 0.36, "Offset": 0.2, "Color": _c(230, 186, 160), "Decay": _c(120, 74, 92),
                       "Glare": 0.6, "Haze": 2.2},
        "bloom": {"Intensity": 0.9, "Size": 36, "Threshold": 1.05},
        "sunrays": {"Intensity": 0.14, "Spread": 0.75},
        "grade": {"Brightness": 0.02, "Contrast": 0.18, "Saturation": 0.22, "TintColor": _c(255, 238, 222)},
        "clouds": {"Cover": 0.55, "Density": 0.55, "Color": _c(255, 214, 190)},
    },
    "shader_night": {
        "use": "moonlit shader night: deep blue haze, soft moon shadows, strong bloom: glowing VFX pop the most",
        "lighting": {"Technology": {"enum": "Technology.Future"}, "ClockTime": 0.4, "GeographicLatitude": 25,
                     "Brightness": 2.2, "ExposureCompensation": 0.2, "EnvironmentDiffuseScale": 0.8,
                     "EnvironmentSpecularScale": 1, "ShadowSoftness": 0.3, "GlobalShadows": True,
                     "Ambient": _c(18, 20, 38), "OutdoorAmbient": _c(44, 50, 84)},
        "atmosphere": {"Density": 0.4, "Offset": 0.1, "Color": _c(104, 120, 170), "Decay": _c(40, 44, 90),
                       "Glare": 0.15, "Haze": 1.4},
        "bloom": {"Intensity": 1.3, "Size": 40, "Threshold": 0.9},
        "sunrays": {"Intensity": 0.06, "Spread": 0.6},
        "grade": {"Brightness": 0.0, "Contrast": 0.22, "Saturation": 0.18, "TintColor": _c(222, 232, 255)},
        "clouds": {"Cover": 0.45, "Density": 0.5, "Color": _c(120, 130, 170)},
    },
    "shader_day": {
        "use": "bright shader noon: crisp sun, saturated colours, light haze, gentle bloom",
        "lighting": {"Technology": {"enum": "Technology.Future"}, "ClockTime": 13, "GeographicLatitude": 40,
                     "Brightness": 3, "ExposureCompensation": 0, "EnvironmentDiffuseScale": 1,
                     "EnvironmentSpecularScale": 1, "ShadowSoftness": 0.15, "GlobalShadows": True,
                     "Ambient": _c(50, 50, 60), "OutdoorAmbient": _c(128, 128, 140)},
        "atmosphere": {"Density": 0.3, "Offset": 0.25, "Color": _c(199, 210, 230), "Decay": _c(106, 130, 170),
                       "Glare": 0.2, "Haze": 1.2},
        "bloom": {"Intensity": 0.6, "Size": 28, "Threshold": 1.4},
        "sunrays": {"Intensity": 0.08, "Spread": 0.6},
        "grade": {"Brightness": 0.02, "Contrast": 0.12, "Saturation": 0.25, "TintColor": _c(255, 252, 245)},
        "clouds": {"Cover": 0.5, "Density": 0.6, "Color": _c(255, 255, 255)},
    },
}


def catalog() -> str:
    return "\n".join(f"lighting:{n} {p['use']}" for n, p in PRESETS.items())


def script(name: str) -> str:
    """Luau that applies a lighting preset to the open place and returns a one-line status."""
    if name not in PRESETS:
        raise KeyError(f"no lighting preset {name!r}: {', '.join(PRESETS)}")
    return luau.DECODE + f"""local HS=game:GetService('HttpService')
local P=HS:JSONDecode({luau.data(PRESETS[name])})
local L=game:GetService('Lighting')
local function set(i,props) for k,v in props do pcall(function() i[k]=V(v) end) end end
set(L,P.lighting)
-- ours are replaced; the place's own effects are switched off (an Atmosphere is kept in a folder) so they don't stack
local stash=L:FindFirstChild('AssetAgentStash') or Instance.new('Folder') stash.Name='AssetAgentStash' stash.Parent=L
for _,d in L:GetChildren() do
 if d:GetAttribute('AssetAgentLighting') then d:Destroy()
 elseif d:IsA('PostEffect') then d.Enabled=false
 elseif d:IsA('Atmosphere') then d.Parent=stash end
end
local labBloom=workspace.CurrentCamera:FindFirstChild('AssetAgentLabBloom') if labBloom then labBloom:Destroy() end
local function add(cls,props) local i=Instance.new(cls) set(i,props) i:SetAttribute('AssetAgentLighting',{luau.data(name)}) i.Parent=L return i end
add('Atmosphere',P.atmosphere) add('BloomEffect',P.bloom) add('SunRaysEffect',P.sunrays) add('ColorCorrectionEffect',P.grade)
local T=workspace:FindFirstChildOfClass('Terrain')
if T then local c=T:FindFirstChildOfClass('Clouds') or Instance.new('Clouds') set(c,P.clouds) c.Parent=T end
return 'lighting {name}: '..L.ClockTime..'h, atmosphere, bloom, sun rays, colour grade, clouds'"""
