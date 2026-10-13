local Players = game:GetService("Players")
local kfs = game:GetService("ServerStorage").BenchRun_native_v2
for _, m in ipairs(workspace:GetChildren()) do
	if m.Name:match("^BenchTmpRig") then m:Destroy() end
end
local frames = { 1, 3, 4, 5 }
local n = 0
for idx, fi in ipairs(frames) do
	local rig = Players:CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), Enum.HumanoidRigType.R15)
	rig.Name = "BenchTmpRig" .. idx
	rig.Parent = workspace
	for _, p in ipairs(rig:GetDescendants()) do if p:IsA("BasePart") then p.Anchored = true end end
	-- face -X so camera at -Z sees side profile (running toward screen left)
	rig.HumanoidRootPart.CFrame = CFrame.new(500 + (idx - 1) * 5, 300, 0) * CFrame.Angles(0, math.pi / 2, 0)
	local joints = {}
	for _, j in ipairs(rig:GetDescendants()) do
		if j:IsA("AnimationConstraint") and j.Attachment1 then joints[j.Attachment1.Parent] = j
		elseif j:IsA("Motor6D") then joints[j.Part1] = j end
	end
	local kf = kfs:GetKeyframes()[fi]
	local function walk(pose)
		for _, c in ipairs(pose:GetChildren()) do
			local part = rig:FindFirstChild(c.Name)
			local j = part and joints[part]
			if j then
				local p0, c0, c1
				if j:IsA("Motor6D") then p0, c0, c1 = j.Part0, j.C0, j.C1
				else p0, c0, c1 = j.Attachment0.Parent, j.Attachment0.CFrame, j.Attachment1.CFrame end
				part.CFrame = p0.CFrame * c0 * c.CFrame * c1:Inverse()
				n += 1
			end
			walk(c)
		end
	end
	walk(kf.HumanoidRootPart)
end
return n
