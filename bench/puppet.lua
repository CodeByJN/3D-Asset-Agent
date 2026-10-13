-- Benchmark helper: play a KeyframeSequence on a standard R15 puppet in Edit mode by doing the
-- forward kinematics ourselves (anchored parts, joint offsets kept as attributes).
local KFS_PATH = __KFS__
local sun = game:GetService('Lighting'):GetSunDirection() * Vector3.new(1, 0, 1)
local HOME = CFrame.lookAt(Vector3.new(400, 300, 400), Vector3.new(400, 300, 400) + (sun.Magnitude > 0.01 and sun.Unit or Vector3.zAxis))
local HS = game:GetService('HttpService')

local function find(path)
	local i = game
	for seg in string.gmatch(path, '[^.]+') do
		if i == game then i = (seg == 'workspace') and workspace or game:GetService(seg) else i = i:FindFirstChild(seg) end
		if not i then return nil end
	end
	return i
end

local function puppet() return workspace:FindFirstChild('BenchPuppet') end

local function desc()
	local d = Instance.new('HumanoidDescription')
	d.HeadColor, d.LeftArmColor, d.RightArmColor = Color3.fromRGB(245, 205, 150), Color3.fromRGB(245, 205, 150), Color3.fromRGB(245, 205, 150)
	d.TorsoColor = Color3.fromRGB(60, 120, 220)
	d.LeftLegColor, d.RightLegColor = Color3.fromRGB(70, 70, 80), Color3.fromRGB(70, 70, 80)
	return d
end

function setup()
	local kfs = find(KFS_PATH)
	assert(kfs and kfs:IsA('KeyframeSequence'), 'no KeyframeSequence at ' .. KFS_PATH)
	local m = puppet()
	if not m then
		m = game:GetService('Players'):CreateHumanoidModelFromDescription(desc(), Enum.HumanoidRigType.R15)
		m.Name = 'BenchPuppet'
		m.Parent = workspace
		m:PivotTo(HOME)
		-- R15 joints are Motor6Ds on older rigs and AnimationConstraints on new ones
		local joints = {}
		for _, j in m:GetDescendants() do
			if j:IsA('Motor6D') and j.Part0 and j.Part1 then
				table.insert(joints, {j, j.Part0, j.Part1, j.C0, j.C1})
			elseif j:IsA('AnimationConstraint') and j.Attachment0 and j.Attachment1 then
				table.insert(joints, {j, j.Attachment0.Parent, j.Attachment1.Parent, j.Attachment0.CFrame, j.Attachment1.CFrame})
			end
		end
		for _, j in joints do
			j[3]:SetAttribute('BenchParent', j[2].Name)
			j[3]:SetAttribute('BenchC0', j[4])
			j[3]:SetAttribute('BenchC1', j[5])
		end
		for _, p in m:GetDescendants() do
			if p:IsA('BasePart') then p.Anchored = true end
			if p:IsA('Constraint') or p:IsA('JointInstance') then p:Destroy() end
		end
	end
	local len = 0
	for _, k in kfs:GetChildren() do if k:IsA('Keyframe') then len = math.max(len, k.Time) end end
	local root = m.HumanoidRootPart.CFrame
	local look = root.Position + Vector3.new(0, -0.3, 0)
	local cam = look + root.RightVector * 10 + root.LookVector * 3 + Vector3.new(0, 1, 0)
	return HS:JSONEncode({length = len, cam = {cam.X, cam.Y, cam.Z}, look = {look.X, look.Y, look.Z}})
end

-- per part name: sorted list of {time, CFrame}
local function tracks(kfs)
	local out = {}
	for _, k in kfs:GetChildren() do
		if k:IsA('Keyframe') then
			for _, p in k:GetDescendants() do
				if p:IsA('Pose') then
					out[p.Name] = out[p.Name] or {}
					table.insert(out[p.Name], {k.Time, p.CFrame})
				end
			end
		end
	end
	for _, l in out do table.sort(l, function(a, b) return a[1] < b[1] end) end
	return out
end

local function sample(l, t)
	if #l == 1 or t <= l[1][1] then return l[1][2] end
	for i = 2, #l do
		if t <= l[i][1] then
			local a, b = l[i - 1], l[i]
			local span = b[1] - a[1]
			return span > 0 and a[2]:Lerp(b[2], (t - a[1]) / span) or b[2]
		end
	end
	return l[#l][2]
end

function pose(t)
	local m = puppet()
	local tr = tracks(find(KFS_PATH))
	local done = {HumanoidRootPart = m.HumanoidRootPart.CFrame}
	local parts = {}
	for _, p in m:GetDescendants() do if p:IsA('BasePart') and p:GetAttribute('BenchParent') then table.insert(parts, p) end end
	local left = #parts
	while left > 0 do
		local progressed = false
		for _, p in parts do
			local par = p:GetAttribute('BenchParent')
			if not done[p.Name] and done[par] then
				local x = tr[p.Name] and sample(tr[p.Name], t) or CFrame.identity
				local cf = done[par] * p:GetAttribute('BenchC0') * x * p:GetAttribute('BenchC1'):Inverse()
				p.CFrame = cf
				done[p.Name] = cf
				left -= 1
				progressed = true
			end
		end
		if not progressed then break end
	end
	return 'ok'
end

function cleanup()
	local m = puppet()
	if m then m:Destroy() end
	return 'ok'
end
