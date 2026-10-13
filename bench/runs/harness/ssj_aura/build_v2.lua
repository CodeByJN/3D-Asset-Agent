-- Super Saiyan aura on an R15 character: BenchAura_harness
local Players = game:GetService("Players")
local rei = workspace.AssetAgentPacks.Pack_Rei
local function src(...)
	local o = rei
	for _, n in { ... } do o = o:FindFirstChild(n) assert(o, n) end
	return o
end

local old = workspace:FindFirstChild("BenchAura_harness_v2")
if old then old:Destroy() end

local desc = Instance.new("HumanoidDescription")
desc.HeadColor = Color3.fromRGB(234, 184, 146)
desc.TorsoColor = Color3.fromRGB(255, 120, 20)
desc.LeftArmColor = Color3.fromRGB(234, 184, 146)
desc.RightArmColor = Color3.fromRGB(234, 184, 146)
desc.LeftLegColor = Color3.fromRGB(255, 120, 20)
desc.RightLegColor = Color3.fromRGB(255, 120, 20)
local char = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R15)
char.Name = "BenchAura_harness_v2"
char.Parent = workspace
local hrp = char:WaitForChild("HumanoidRootPart")
for _, p in char:GetDescendants() do
	if p:IsA("BasePart") then p.Anchored = (p == hrp) end
end
char:PivotTo(CFrame.new(-330, 150, 60) * CFrame.Angles(0, math.rad(180), 0))
-- a floating pose: arms slightly out
local function pose(motorName, cf)
	for _, m in char:GetDescendants() do
		if m:IsA("Motor6D") and m.Name == motorName then m.Transform = cf end
	end
end
pose("LeftShoulder", CFrame.Angles(0, 0, math.rad(-20)))
pose("RightShoulder", CFrame.Angles(0, 0, math.rad(20)))

local folder = Instance.new("Folder")
folder.Name = "SSJAura"
folder.Parent = char

local function NS(...) local t = {} for i, v in { ... } do t[i] = NumberSequenceKeypoint.new(v[1], v[2], v[3] or 0) end return NumberSequence.new(t) end
local function CS(...) local t = {} for i, v in { ... } do t[i] = ColorSequenceKeypoint.new(v[1], v[2]) end return ColorSequence.new(t) end
local WHITE = Color3.fromRGB(235, 250, 255)
local PALE = Color3.fromRGB(170, 235, 255)
local GOLD = Color3.fromRGB(40, 170, 255)
local DEEP = Color3.fromRGB(20, 110, 255)
local ORANGE = Color3.fromRGB(30, 60, 230)
local goldRamp = CS({0, GOLD}, {0.5, DEEP}, {1, ORANGE})

-- invisible host volume around the body (flames emit from its volume)
local function host(name, size, offset)
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.Transparency = 1
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.Massless = true
	p.CFrame = hrp.CFrame * offset
	p.Parent = folder
	local w = Instance.new("WeldConstraint")
	w.Part0 = hrp
	w.Part1 = p
	w.Parent = p
	return p
end
local body = host("AuraBody", Vector3.new(4.0, 5.4, 2.4), CFrame.new(0, -0.4, 0))
local feet = host("AuraFeet", Vector3.new(4, 0.2, 4), CFrame.new(0, -3.0, 0))

local function clone(from, parent, props)
	local e = from:Clone()
	for k, v in props do e[k] = v end
	e.Parent = parent
	return e
end

-- 1. Core flame body: dense flipbook fire licking upward from the whole body volume
local fire = src("BASE", "01 - FLAMES", "D - ROARING FLAMES", "FIRE")
clone(fire, body, {
	Name = "FlameCore", Color = goldRamp, Rate = 140, Lifetime = NumberRange.new(0.45, 0.75),
	Speed = NumberRange.new(5, 9), SpreadAngle = Vector2.new(8, 8), EmissionDirection = Enum.NormalId.Top,
	Acceleration = Vector3.new(0, 6, 0), Size = NS({0, 1.6}, {0.4, 2.0, 0.3}, {1, 0}),
	Transparency = NS({0, 1}, {0.12, 0.25}, {0.55, 0.55}, {0.8, 1}, {1, 1}), LightEmission = 0.9, LightInfluence = 0,
	Brightness = 1.2, ZOffset = -0.5, Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	LockedToPart = false, Drag = 1, Rotation = NumberRange.new(-10, 10), RotSpeed = NumberRange.new(-20, 20),
})
-- 2. Flame spikes: tall pointed tongues shooting up, the signature DBZ silhouette
local spikes = src("BASE", "01 - FLAMES", "F - RAGING PILLAR", "SPIKES")
clone(spikes, body, {
	Name = "FlameSpikes", Color = CS({0, PALE}, {0.3, GOLD}, {1, ORANGE}), Rate = 55,
	Lifetime = NumberRange.new(0.3, 0.55), Speed = NumberRange.new(12, 20), SpreadAngle = Vector2.new(12, 12),
	EmissionDirection = Enum.NormalId.Top, Size = NS({0, 1.6, 0.4}, {0.5, 1.2}, {1, 0}),
	Transparency = NS({0, 1}, {0.15, 0.25}, {1, 1}), LightEmission = 0.8, LightInfluence = 0, Brightness = 1.5,
	Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume, LockedToPart = false,
	Acceleration = Vector3.new(0, 10, 0), ZOffset = 0.5,
})
-- 2b. Flame wall: streaking tongues rising off a shell hugging the silhouette
local shell = host("AuraShell", Vector3.new(4.4, 4.6, 2.8), CFrame.new(0, -0.8, 0))
clone(spikes, shell, {
	Name = "FlameWall", Color = CS({0, GOLD}, {0.5, DEEP}, {1, ORANGE}), Rate = 160,
	Lifetime = NumberRange.new(0.35, 0.6), Speed = NumberRange.new(9, 15), SpreadAngle = Vector2.new(6, 6),
	EmissionDirection = Enum.NormalId.Top, Size = NS({0, 1.3, 0.3}, {0.4, 1.1}, {1, 0}),
	Transparency = NS({0, 1}, {0.15, 0.35}, {0.7, 0.55}, {1, 1}), LightEmission = 1, LightInfluence = 0, Brightness = 1.4,
	Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume, LockedToPart = false,
	Acceleration = Vector3.new(0, 14, 0), Drag = 0.5, ZOffset = 0, Orientation = Enum.ParticleOrientation.VelocityParallel,
	Squash = NS({0, -0.4}, {1, -0.4}),
})
clone(fire, shell, {
	Name = "FlameLicks", Color = CS({0, GOLD}, {0.6, DEEP}, {1, ORANGE}), Rate = 70,
	Lifetime = NumberRange.new(0.35, 0.6), Speed = NumberRange.new(6, 10), SpreadAngle = Vector2.new(5, 5),
	EmissionDirection = Enum.NormalId.Top, Size = NS({0, 1.4}, {0.5, 1.8}, {1, 0}),
	Transparency = NS({0, 1}, {0.15, 0.35}, {0.55, 0.6}, {0.8, 1}, {1, 1}), LightEmission = 1, LightInfluence = 0,
	Brightness = 1.2, Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	LockedToPart = false, Acceleration = Vector3.new(0, 8, 0), ZOffset = -0.3,
})
-- 3. Outer egg-shaped glow (soft halo the flames sit in)
local glow = src("BASE", "01 - FLAMES", "D - ROARING FLAMES", "GLOW")
clone(glow, body, {
	Name = "AuraHalo", Color = CS({0, PALE}, {1, DEEP}), Rate = 30, Lifetime = NumberRange.new(0.5, 0.8),
	Speed = NumberRange.new(2, 4), EmissionDirection = Enum.NormalId.Top, Size = NS({0, 7}, {1, 9}),
	Transparency = NS({0, 1}, {0.2, 0.93}, {1, 1}), LightEmission = 1, LightInfluence = 0, Brightness = 1,
	Shape = Enum.ParticleEmitterShape.Box, LockedToPart = true, ZOffset = -1,
})
-- 4. Hot inner glow hugging the silhouette
clone(glow, body, {
	Name = "InnerGlow", Color = CS({0, GOLD}, {1, DEEP}), Rate = 40, Lifetime = NumberRange.new(0.3, 0.5),
	Speed = NumberRange.new(0.5, 1.5), EmissionDirection = Enum.NormalId.Top, Size = NS({0, 2.5}, {1, 3.2}),
	Transparency = NS({0, 1}, {0.2, 0.92}, {1, 1}), LightEmission = 1, LightInfluence = 0, Brightness = 1,
	Shape = Enum.ParticleEmitterShape.Box, LockedToPart = true, ZOffset = 0.5,
})
-- 5. Rising golden motes / specks
local specks = src("BASE", "01 - FLAMES", "D - ROARING FLAMES", "SPECKS")
clone(specks, body, {
	Name = "RisingMotes", Color = CS({0, WHITE}, {1, GOLD}), Rate = 60, Lifetime = NumberRange.new(0.6, 1.1),
	Speed = NumberRange.new(10, 18), SpreadAngle = Vector2.new(20, 20), EmissionDirection = Enum.NormalId.Top,
	Size = NS({0, 0.18}, {1, 0}), LightEmission = 1, LightInfluence = 0, Brightness = 2,
	Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume, LockedToPart = false,
	Orientation = Enum.ParticleOrientation.VelocityParallel, Squash = NS({0, -1.5}, {1, -1.5}),
})

-- 6. Crackling electricity: flipbook arcs flickering across the body
local elec = src("BASE", "03 - ELECTRICAL", "D - ELECTRICITY 04", "ELECTRIC")
clone(elec, body, {
	Name = "Crackle", Color = CS({0, Color3.fromRGB(255, 255, 255)}, {1, Color3.fromRGB(220, 245, 255)}), Rate = 14,
	Lifetime = NumberRange.new(0.18, 0.3), Size = NS({0, 2.4}, {1, 2.8}), LightEmission = 1, LightInfluence = 0,
	Brightness = 3, Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	LockedToPart = true, Rotation = NumberRange.new(0, 360), ZOffset = 2,
	Transparency = NS({0, 0}, {0.8, 0}, {1, 1}),
})
local bolt = src("BASE", "03 - ELECTRICAL", "G - LIGHTNING BOLT 01", "MIDDLE", "ELECTRIC")
clone(bolt, body, {
	Name = "Arcs", Color = CS({0, Color3.fromRGB(255, 255, 255)}, {1, Color3.fromRGB(210, 240, 255)}), Rate = 6,
	Lifetime = NumberRange.new(0.15, 0.25), Size = NS({0, 3.2}, {1, 3.2}), LightEmission = 1, LightInfluence = 0,
	Brightness = 3, Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	LockedToPart = true, Rotation = NumberRange.new(-180, 180), ZOffset = 2,
	Orientation = Enum.ParticleOrientation.FacingCamera,
})
local sparks = src("BASE", "08 - MISC", "J - ELECTRIC ORB", "Sparks")
clone(sparks, body, {
	Name = "Sparks", Color = CS({0, Color3.fromRGB(255, 255, 255)}, {1, PALE}), Rate = 18,
	Lifetime = NumberRange.new(0.1, 0.18), Size = NS({0, 1.3}, {1, 1.5}), LightEmission = 1, LightInfluence = 0,
	Brightness = 3, Shape = Enum.ParticleEmitterShape.Box, ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	LockedToPart = true, Rotation = NumberRange.new(0, 360), ZOffset = 2,
})

-- 7. Ground: flame skirt and pressure ring at the feet
local floor = src("BASE", "01 - FLAMES", "E - FLOOR FLAMES", "FLAMES")
clone(floor, feet, {
	Name = "FootFlames", Color = goldRamp, Rate = 40, Lifetime = NumberRange.new(0.4, 0.7),
	Speed = NumberRange.new(3, 6), EmissionDirection = Enum.NormalId.Top, Size = NS({0, 2.5}, {1, 0.5}),
	LightEmission = 0.8, LightInfluence = 0, Brightness = 1.2, Shape = Enum.ParticleEmitterShape.Box,
	LockedToPart = false, Transparency = NS({0, 1}, {0.15, 0.35}, {1, 1}),
})
local ringAtt = Instance.new("Attachment")
ringAtt.Name = "RingAtt"
ringAtt.Parent = feet
local ring = Instance.new("ParticleEmitter")
ring.Name = "PressureRing"
ring.Texture = "rbxassetid://1084955488" -- ring/bubble
ring.Orientation = Enum.ParticleOrientation.VelocityPerpendicular
ring.EmissionDirection = Enum.NormalId.Top
ring.Speed = NumberRange.new(0.01)
ring.Rate = 2.5
ring.Lifetime = NumberRange.new(0.7)
ring.Size = NS({0, 2}, {1, 9})
ring.Transparency = NS({0, 0.6}, {1, 1})
ring.Color = CS({0, GOLD}, {1, DEEP})
ring.LightEmission = 1
ring.LightInfluence = 0
ring.Brightness = 1.5
ring.LockedToPart = true
ring.Parent = ringAtt

-- 8. Light, rim highlight
local light = Instance.new("PointLight")
light.Name = "AuraLight"
light.Color = GOLD
light.Brightness = 2
light.Range = 18
light.Shadows = false
light.Parent = body
local hl = Instance.new("Highlight")
hl.Name = "SSJRim"
hl.FillColor = Color3.fromRGB(90, 190, 255)
hl.FillTransparency = 0.96
hl.OutlineColor = Color3.fromRGB(160, 230, 255)
hl.OutlineTransparency = 0.35
hl.DepthMode = Enum.HighlightDepthMode.Occluded
hl.Adornee = char
hl.Parent = folder

-- 8b. Golden spiky Super Saiyan hair (wedge spikes welded to the head)
local head = char:FindFirstChild("Head")
local hair = Instance.new("Model")
hair.Name = "SSJHair"
hair.Parent = folder
local function spike(pos, dir, len, w)
	local d = dir.Unit
	local right = d:Cross(Vector3.new(0, 0, 1))
	if right.Magnitude < 0.01 then right = Vector3.new(1, 0, 0) end
	right = right.Unit
	local back = right:Cross(d).Unit
	local p = Instance.new("Part")
	p.Name = "Spike"
	p.Size = Vector3.new(w, len, w)
	p.Material = Enum.Material.Neon
	p.Color = Color3.fromRGB(60, 190, 255)
	p.CanCollide = false
	p.CanQuery = false
	p.Massless = true
	p.CastShadow = false
	local m = Instance.new("SpecialMesh")
	m.MeshType = Enum.MeshType.FileMesh
	m.MeshId = "rbxassetid://1033714" -- cone
	m.Scale = Vector3.new(w * 0.8, len, w * 0.8)
	m.Parent = p
	p.CFrame = head.CFrame * CFrame.fromMatrix(pos + d * len * 0.4, right, d, back)
	p.Parent = hair
	local wc = Instance.new("WeldConstraint")
	wc.Part0 = head
	wc.Part1 = p
	wc.Parent = p
end
local cap = Instance.new("Part")
cap.Name = "HairCap"
cap.Shape = Enum.PartType.Ball
cap.Size = Vector3.new(1.3, 0.75, 1.3)
cap.Material = Enum.Material.Neon
cap.Color = Color3.fromRGB(50, 175, 255)
cap.CanCollide = false
cap.Massless = true
cap.CFrame = head.CFrame * CFrame.new(0, 0.45, 0.12)
cap.Parent = hair
local cw = Instance.new("WeldConstraint") cw.Part0 = head cw.Part1 = cap cw.Parent = cap
-- head space: +Y up, +X right, +Z back (face is -Z). Spikes flare up, back and out.
local V = Vector3.new
local spikes = {
	{V(0, 0.6, 0.1), V(0, 1, 0.35), 2.3, 0.6},
	{V(0.3, 0.55, 0.05), V(0.55, 1, 0.3), 2.0, 0.55},
	{V(-0.3, 0.55, 0.05), V(-0.55, 1, 0.3), 2.0, 0.55},
	{V(0.5, 0.35, 0.1), V(1, 0.6, 0.25), 1.6, 0.5},
	{V(-0.5, 0.35, 0.1), V(-1, 0.6, 0.25), 1.6, 0.5},
	{V(0.25, 0.45, 0.4), V(0.4, 0.7, 1), 1.8, 0.55},
	{V(-0.25, 0.45, 0.4), V(-0.4, 0.7, 1), 1.8, 0.55},
	{V(0, 0.3, 0.55), V(0, 0.3, 1), 1.2, 0.55},
	{V(0.55, 0.1, 0.2), V(1, 0.15, 0.3), 0.8, 0.4},
	{V(-0.55, 0.1, 0.2), V(-1, 0.15, 0.3), 0.8, 0.4},
	{V(0.12, 0.55, -0.45), V(0.15, 0.7, -0.6), 0.75, 0.35}, -- front bangs
	{V(-0.2, 0.5, -0.45), V(-0.35, 0.6, -0.55), 0.65, 0.3},
}
for _, s in spikes do spike(s[1], s[2], s[3], s[4]) end

-- 9. Runtime pulse: aura surges and crackle bursts
local s = Instance.new("Script")
s.Name = "AuraPulse"
s.Source = [[
local folder = script.Parent
local body = folder:WaitForChild("AuraBody")
local light = body:WaitForChild("AuraLight")
local core = body:WaitForChild("FlameCore")
local spikes = body:WaitForChild("FlameSpikes")
local crackle = body:WaitForChild("Crackle")
local arcs = body:WaitForChild("Arcs")
local hl = folder:WaitForChild("SSJRim")
local t = 0
while true do
	local dt = task.wait()
	t += dt
	local surge = 0.5 + 0.5 * math.sin(t * 7) * math.sin(t * 2.3)
	light.Brightness = 1.5 + surge * 1.5 + math.random() * 0.4
	core.Rate = 120 + surge * 60
	spikes.Rate = 55 + surge * 40
	hl.FillTransparency = 0.97 - surge * 0.05
	if math.random() < dt * 2.2 then
		crackle:Emit(math.random(2, 4))
		arcs:Emit(math.random(1, 2))
		light.Brightness = 5
	end
end
]]
s.Parent = folder

return char:GetFullName() .. " at " .. tostring(hrp.Position)
