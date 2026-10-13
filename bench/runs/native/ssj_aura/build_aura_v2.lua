-- Super Saiyan Blue aura on an R15 rig: workspace.BenchAura_native_v2
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local old = workspace:FindFirstChild("BenchAura_native_v2")
if old then old:Destroy() end

local desc = Instance.new("HumanoidDescription")
desc.HeadColor = Color3.fromRGB(234, 184, 146)
desc.TorsoColor = Color3.fromRGB(240, 120, 20)
desc.LeftArmColor = Color3.fromRGB(234, 184, 146)
desc.RightArmColor = Color3.fromRGB(234, 184, 146)
desc.LeftLegColor = Color3.fromRGB(30, 50, 140)
desc.RightLegColor = Color3.fromRGB(30, 50, 140)
local char = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R15)
char.Name = "BenchAura_native_v2"
local hrp = char:WaitForChild("HumanoidRootPart")
hrp.Anchored = true
char:PivotTo(CFrame.new(-330, 150, 0) * CFrame.Angles(0, math.rad(180), 0))
char.Parent = workspace

local FIRE = "rbxasset://textures/particles/fire_main.dds"
local SPARK = "rbxasset://textures/particles/sparkles_main.dds"
local FSPARK = "rbxasset://textures/particles/fire_sparks_main.dds"

local function cs(list)
	local kps = {}
	for _, k in ipairs(list) do table.insert(kps, ColorSequenceKeypoint.new(k[1], k[2])) end
	return ColorSequence.new(kps)
end
local function ns(list)
	local kps = {}
	for _, k in ipairs(list) do table.insert(kps, NumberSequenceKeypoint.new(k[1], k[2], k[3] or 0)) end
	return NumberSequence.new(kps)
end

local WHITE = Color3.fromRGB(235, 250, 255)
local PALE = Color3.fromRGB(160, 230, 255)
local GOLD = Color3.fromRGB(40, 165, 255)
local AMBER = Color3.fromRGB(20, 70, 255)

local function emitter(parent, name, props)
	local e = Instance.new("ParticleEmitter")
	e.Name = name
	e.LightEmission = 1
	e.LightInfluence = 0
	e.LockedToPart = false
	for k, v in pairs(props) do e[k] = v end
	e.Parent = parent
	return e
end

local auraFolder = Instance.new("Folder")
auraFolder.Name = "SSJ_Aura"
auraFolder.Parent = char

-- Emitter volume around the body (box shape on an invisible shell part welded to the root)
local shell = Instance.new("Part")
shell.Name = "AuraShell"
shell.Size = Vector3.new(3.2, 5.6, 2.2)
shell.Transparency = 1
shell.CanCollide = false
shell.CanQuery = false
shell.CanTouch = false
shell.Massless = true
shell.Anchored = false
shell.CFrame = hrp.CFrame * CFrame.new(0, -0.2, 0)
shell.Parent = auraFolder
local w = Instance.new("WeldConstraint")
w.Part0 = hrp
w.Part1 = shell
w.Parent = shell

-- 1) Main flame body: big, tall, upward-licking golden flames
emitter(shell, "FlameBody", {
	Texture = FIRE,
	Shape = Enum.ParticleEmitterShape.Box,
	ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	EmissionDirection = Enum.NormalId.Top,
	Rate = 140,
	Lifetime = NumberRange.new(0.45, 0.8),
	Speed = NumberRange.new(4, 8),
	Acceleration = Vector3.new(0, 18, 0),
	SpreadAngle = Vector2.new(12, 12),
	Size = ns({ {0, 1.2, 0.3}, {0.35, 2.4, 0.4}, {1, 0.6} }),
	Squash = ns({ {0, -0.6}, {1, -1.2} }),
	Transparency = ns({ {0, 1}, {0.12, 0.4}, {0.6, 0.6}, {1, 1} }),
	Color = cs({ {0, PALE}, {0.2, GOLD}, {0.7, Color3.fromRGB(30, 120, 255)}, {1, AMBER} }),
	Rotation = NumberRange.new(-20, 20),
	RotSpeed = NumberRange.new(-40, 40),
	LightEmission = 0.75,
	ZOffset = -1,
})

-- 2) Aura spikes: long thin streaks shooting up (classic DBZ silhouette)
emitter(shell, "AuraSpikes", {
	Texture = FIRE,
	Shape = Enum.ParticleEmitterShape.Box,
	ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
	EmissionDirection = Enum.NormalId.Top,
	Orientation = Enum.ParticleOrientation.VelocityParallel,
	Rate = 70,
	Lifetime = NumberRange.new(0.25, 0.45),
	Speed = NumberRange.new(14, 22),
	SpreadAngle = Vector2.new(18, 18),
	Size = ns({ {0, 0.5}, {0.3, 0.9}, {1, 0.15} }),
	Squash = ns({ {0, -2.2}, {1, -2.8} }),
	Transparency = ns({ {0, 0.6}, {0.2, 0.15}, {1, 1} }),
	Color = cs({ {0, WHITE}, {0.3, PALE}, {1, GOLD} }),
	ZOffset = 0.5,
})

-- 3) Outer silhouette: large flame tongues from a wider shell
local shell2 = shell:Clone()
shell2.Name = "AuraShellOuter"
for _, c in ipairs(shell2:GetChildren()) do c:Destroy() end
shell2.Size = Vector3.new(4.6, 4.0, 3.4)
shell2.CFrame = hrp.CFrame * CFrame.new(0, -1.8, 0)
shell2.Parent = auraFolder
local w2 = Instance.new("WeldConstraint")
w2.Part0 = hrp
w2.Part1 = shell2
w2.Parent = shell2
emitter(shell2, "OuterFlames", {
	Texture = FIRE,
	Shape = Enum.ParticleEmitterShape.Box,
	ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	EmissionDirection = Enum.NormalId.Top,
	Rate = 70,
	Lifetime = NumberRange.new(0.6, 0.9),
	Speed = NumberRange.new(3, 6),
	Acceleration = Vector3.new(0, 16, 0),
	SpreadAngle = Vector2.new(6, 6),
	Size = ns({ {0, 1.4, 0.4}, {0.4, 2.6, 0.5}, {1, 0.6} }),
	Squash = ns({ {0, -1.0}, {1, -1.8} }),
	Transparency = ns({ {0, 1}, {0.2, 0.5}, {0.7, 0.7}, {1, 1} }),
	Color = cs({ {0, GOLD}, {0.5, Color3.fromRGB(30, 130, 255)}, {1, AMBER} }),
	RotSpeed = NumberRange.new(-30, 30),
	Rotation = NumberRange.new(-10, 10),
	LightEmission = 0.7,
	ZOffset = -2,
})
-- 4) Per-limb flame wisps hugging the body + inner white-hot core glow
local limbs = {"Head", "UpperTorso", "LowerTorso", "LeftUpperArm", "RightUpperArm", "LeftLowerArm",
	"RightLowerArm", "LeftHand", "RightHand", "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg"}
for _, n in ipairs(limbs) do
	local p = char:FindFirstChild(n)
	if p then
		emitter(p, "LimbFlame", {
			Texture = FIRE,
			Shape = Enum.ParticleEmitterShape.Box,
			ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
			EmissionDirection = Enum.NormalId.Top,
			Rate = (n == "Head" and 40) or 20,
			Lifetime = NumberRange.new(0.3, 0.5),
			Speed = NumberRange.new(2, 4),
			Acceleration = Vector3.new(0, 20, 0),
			Size = ns({ {0, 0.5}, {0.4, 0.9}, {1, 0.2} }),
			Squash = ns({ {0, -0.8}, {1, -1.4} }),
			Transparency = ns({ {0, 0.8}, {0.2, 0.3}, {1, 1} }),
			Color = cs({ {0, PALE}, {0.4, GOLD}, {1, AMBER} }),
			RotSpeed = NumberRange.new(-60, 60),
			ZOffset = 0.8,
		})
	end
end
emitter(char.UpperTorso, "CoreGlow", {
	Texture = SPARK,
	Rate = 12,
	Lifetime = NumberRange.new(0.4, 0.6),
	Speed = NumberRange.new(0, 0),
	Size = ns({ {0, 6}, {0.5, 7}, {1, 6} }),
	Transparency = ns({ {0, 1}, {0.3, 0.88}, {0.7, 0.88}, {1, 1} }),
	Color = cs({ {0, PALE}, {1, GOLD} }),
	ZOffset = -3,
	LockedToPart = true,
})

-- 5) Rising embers / energy motes
emitter(shell, "Embers", {
	Texture = FSPARK,
	Shape = Enum.ParticleEmitterShape.Box,
	ShapeStyle = Enum.ParticleEmitterShapeStyle.Volume,
	Rate = 45,
	Lifetime = NumberRange.new(0.6, 1.2),
	Speed = NumberRange.new(3, 7),
	SpreadAngle = Vector2.new(35, 35),
	EmissionDirection = Enum.NormalId.Top,
	Acceleration = Vector3.new(0, 10, 0),
	Size = ns({ {0, 0.25}, {1, 0.05} }),
	Transparency = ns({ {0, 0}, {0.8, 0.2}, {1, 1} }),
	Color = cs({ {0, WHITE}, {1, GOLD} }),
	Drag = 1,
	ZOffset = 1,
})

-- 6) Crackle: fast electric sparks popping off the body
emitter(shell, "CrackleSparks", {
	Texture = SPARK,
	Shape = Enum.ParticleEmitterShape.Box,
	ShapeStyle = Enum.ParticleEmitterShapeStyle.Surface,
	Rate = 30,
	Lifetime = NumberRange.new(0.06, 0.14),
	Speed = NumberRange.new(0, 1),
	Size = ns({ {0, 0.9}, {1, 0.2} }),
	Transparency = ns({ {0, 0}, {1, 0.6} }),
	Color = cs({ {0, Color3.fromRGB(235, 250, 255)}, {1, Color3.fromRGB(140, 210, 255)} }),
	Rotation = NumberRange.new(0, 360),
	ZOffset = 2,
})

-- Light + rim glow
local light = Instance.new("PointLight")
light.Color = Color3.fromRGB(90, 180, 255)
light.Brightness = 4
light.Range = 18
light.Shadows = false
light.Parent = shell
local hl = Instance.new("Highlight")
hl.Name = "SSJGlow"
hl.Adornee = char
hl.FillColor = Color3.fromRGB(80, 180, 255)
hl.FillTransparency = 0.82
hl.OutlineColor = Color3.fromRGB(150, 220, 255)
hl.OutlineTransparency = 0.15
hl.DepthMode = Enum.HighlightDepthMode.Occluded
hl.Parent = char

-- 7) Lightning arcs: jagged beam chains that re-randomise every few frames
local boltFolder = Instance.new("Folder")
boltFolder.Name = "Lightning"
boltFolder.Parent = auraFolder

local N_BOLTS, SEGS = 5, 7
for b = 1, N_BOLTS do
	local atts = {}
	for i = 0, SEGS do
		local a = Instance.new("Attachment")
		a.Name = ("Bolt%d_%d"):format(b, i)
		a.Parent = shell
		atts[i] = a
	end
	for i = 1, SEGS do
		for layer = 1, 2 do
			local beam = Instance.new("Beam")
			beam.Name = ("Bolt%d_seg%d_%s"):format(b, i, layer == 1 and "core" or "glow")
			beam.Attachment0 = atts[i - 1]
			beam.Attachment1 = atts[i]
			beam.FaceCamera = true
			beam.Segments = 1
			beam.LightEmission = 1
			beam.LightInfluence = 0
			beam.Width0 = layer == 1 and 0.06 or 0.35
			beam.Width1 = layer == 1 and 0.06 or 0.35
			beam.Texture = layer == 1 and "" or SPARK
			beam.Color = layer == 1 and ColorSequence.new(Color3.fromRGB(245, 252, 255))
				or ColorSequence.new(Color3.fromRGB(90, 160, 255))
			beam.Transparency = NumberSequence.new(layer == 1 and 0 or 0.45)
			beam.ZOffset = 3
			beam:SetAttribute("Bolt", b)
			beam.Parent = boltFolder
		end
	end
end

-- Animator source: shared by edit-mode preview and the runtime script
local ANIM = [[
local shell, folder = ...
local SEGS = 7
local half = shell.Size / 2
local rng = Random.new()
local function surfacePoint()
	local p = Vector3.new(rng:NextNumber(-1,1)*half.X, rng:NextNumber(-1,1)*half.Y, rng:NextNumber(-1,1)*half.Z)
	local ax = rng:NextInteger(1,3)
	local s = rng:NextNumber() < 0.5 and -1 or 1
	if ax == 1 then p = Vector3.new(s*half.X, p.Y, p.Z) elseif ax == 2 then p = Vector3.new(p.X, s*half.Y*0.9, p.Z) else p = Vector3.new(p.X, p.Y, s*half.Z) end
	return p * 0.95
end
local bolts = {}
for _, beam in ipairs(folder:GetChildren()) do
	local b = beam:GetAttribute("Bolt")
	bolts[b] = bolts[b] or {}
	table.insert(bolts[b], beam)
end
local function rebolt(b)
	local start = surfacePoint()
	local dir = Vector3.new(rng:NextNumber(-1,1), rng:NextNumber(-0.15,1.2), rng:NextNumber(-1,1)).Unit
	local len = rng:NextNumber(1.2, 2.6)
	local on = rng:NextNumber() < 0.6
	for i = 0, SEGS do
		local a = shell:FindFirstChild(("Bolt%d_%d"):format(b, i))
		local t = i / SEGS
		local jitter = (i == 0) and Vector3.zero or Vector3.new(rng:NextNumber(-1,1), rng:NextNumber(-1,1), rng:NextNumber(-1,1)) * 0.35 * (1 - t*0.3)
		if a then a.Position = start + dir * len * t + jitter end
	end
	for _, beam in ipairs(bolts[b]) do beam.Enabled = on end
end
local acc = {}
return function(dt)
	for b in pairs(bolts) do
		acc[b] = (acc[b] or 0) - dt
		if acc[b] <= 0 then
			acc[b] = rng:NextNumber(0.04, 0.12)
			rebolt(b)
		end
	end
end
]]

local sv = Instance.new("StringValue")
sv.Name = "LightningAnimSource"
sv.Value = ANIM
sv.Parent = auraFolder

local rt = Instance.new("Script")
rt.Name = "LightningAnimator"
rt.RunContext = Enum.RunContext.Client
rt.Source = [[
local folder = script.Parent
local shell = folder:WaitForChild("AuraShell")
local bolts = folder:WaitForChild("Lightning")
-- inline animator (loadstring is unavailable on the client)
]] .. "local make = function(...)\n" .. ANIM .. "\nend\nlocal tick = make(shell, bolts)\ngame:GetService('RunService').RenderStepped:Connect(tick)\n"
rt.Parent = auraFolder

-- Edit-mode preview so the arcs crackle in Studio without pressing Play
local ok, fn = pcall(function()
	local f = loadstring(ANIM)
	return f(shell, boltFolder)
end)
local editConn = "none"
if ok and fn then
	local conn
	-- Studio edit mode does not tick Rate emission, so drive emitters by hand until Play takes over
	local ems, accum = {}, {}
	for _, e in ipairs(char:GetDescendants()) do
		if e:IsA("ParticleEmitter") then table.insert(ems, e); accum[e] = 0 end
	end
	conn = RunService.Heartbeat:Connect(function(dt)
		if not boltFolder.Parent or not char.Parent then conn:Disconnect() return end
		fn(dt)
		if not RunService:IsRunning() then
			for _, e in ipairs(ems) do
				accum[e] += e.Rate * dt
				local n = math.floor(accum[e])
				if n > 0 then accum[e] -= n; e:Emit(n) end
			end
		end
	end)
	fn(0)
	editConn = "connected"
else
	editConn = "failed: " .. tostring(fn)
end

return char:GetFullName() .. " | edit anim: " .. editConn
