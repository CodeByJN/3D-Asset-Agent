-- Builds a looping R15 run cycle KeyframeSequence in ServerStorage.BenchRun_native
local SS = game:GetService("ServerStorage")
local old = SS:FindFirstChild("BenchRun_native")
if old then old:Destroy() end

local kfs = Instance.new("KeyframeSequence")
kfs.Name = "BenchRun_native"
kfs.Loop = true
kfs.Priority = Enum.AnimationPriority.Movement

local LEN = 0.7
local N = 12
local pi = math.pi
local cos, sin = math.cos, math.sin
local A = CFrame.Angles

-- phase phi: right leg; 0 = right foot contact (leg forward)
local function legAngles(phi)
	local hip = 0.15 + 0.7 * cos(phi)
	local knee = -(0.95 + 0.75 * cos(phi - 1.3 * pi))
	local foot = -0.1 + 0.3 * cos(phi - 0.2 * pi)
	return hip, knee, foot
end

local function poseCFs(phi)
	local t = {}
	local y = 0.12 * cos(2 * (phi - 0.8 * pi)) - 0.05
	t.LowerTorso = CFrame.new(0, y, 0) * A(-0.14, 0.15 * cos(phi), 0)
	t.UpperTorso = A(-0.12 + 0.03 * cos(2 * phi), -0.3 * cos(phi), 0)
	t.Head = A(0.18, 0.15 * cos(phi), 0)

	local rh, rk, rf = legAngles(phi)
	local lh, lk, lf = legAngles(phi + pi)
	t.RightUpperLeg = A(rh, 0, 0.03)
	t.RightLowerLeg = A(rk, 0, 0)
	t.RightFoot = A(rf, 0, 0)
	t.LeftUpperLeg = A(lh, 0, -0.03)
	t.LeftLowerLeg = A(lk, 0, 0)
	t.LeftFoot = A(lf, 0, 0)

	-- arms swing opposite to same-side leg
	local la = 0.15 + 0.65 * cos(phi)
	local ra = 0.15 + 0.65 * cos(phi + pi)
	t.LeftUpperArm = A(la, 0, -0.12)
	t.RightUpperArm = A(ra, 0, 0.12)
	t.LeftLowerArm = A(1.35 + 0.25 * cos(phi), 0, 0)
	t.RightLowerArm = A(1.35 + 0.25 * cos(phi + pi), 0, 0)
	t.LeftHand = A(-0.1, 0, 0)
	t.RightHand = A(-0.1, 0, 0)
	return t
end

local tree = {
	HumanoidRootPart = { "LowerTorso" },
	LowerTorso = { "UpperTorso", "LeftUpperLeg", "RightUpperLeg" },
	UpperTorso = { "Head", "LeftUpperArm", "RightUpperArm" },
	LeftUpperArm = { "LeftLowerArm" }, LeftLowerArm = { "LeftHand" },
	RightUpperArm = { "RightLowerArm" }, RightLowerArm = { "RightHand" },
	LeftUpperLeg = { "LeftLowerLeg" }, LeftLowerLeg = { "LeftFoot" },
	RightUpperLeg = { "RightLowerLeg" }, RightLowerLeg = { "RightFoot" },
}

local function build(name, parent, cfs)
	local p = Instance.new("Pose")
	p.Name = name
	p.CFrame = cfs[name] or CFrame.new()
	p.Weight = 1
	p.EasingStyle = Enum.PoseEasingStyle.Linear
	p.EasingDirection = Enum.PoseEasingDirection.In
	p.Parent = parent
	for _, c in ipairs(tree[name] or {}) do build(c, p, cfs) end
end

for i = 0, N do
	local kf = Instance.new("Keyframe")
	kf.Time = LEN * i / N
	kf.Name = "Keyframe"
	build("HumanoidRootPart", kf, poseCFs(2 * pi * (i % N) / N))
	kf.Parent = kfs
end
kfs.Parent = SS

local kfsList = kfs:GetKeyframes()
local count = #kfsList
local poses = #kfs:GetDescendants() - count
return "ok keyframes=" .. count .. " len=" .. kfsList[count].Time .. " poses=" .. poses
