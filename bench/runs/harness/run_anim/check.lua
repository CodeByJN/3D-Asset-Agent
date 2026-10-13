local old = workspace:FindFirstChild("TmpRunRig_h"); if old then old:Destroy() end
local rig = game:GetService("Players"):CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), Enum.HumanoidRigType.R15)
rig.Name = "TmpRunRig_h"; rig.Parent = workspace
rig:PivotTo(CFrame.new(500, 300, 0)); rig.HumanoidRootPart.Anchored = true
local kf = game.ServerStorage.BenchRun_harness:GetKeyframes()[3] -- t=0.2, right leg forward
local joints = {}
for _, d in ipairs(rig:GetDescendants()) do
  if d:IsA("Motor6D") then joints[d.Part1.Name] = d
  elseif d:IsA("AnimationConstraint") and d.Attachment1 then joints[d.Attachment1.Parent.Name] = d end
end
local c = 0
for _, ps in ipairs(kf:GetDescendants()) do
  if ps:IsA("Pose") and joints[ps.Name] then joints[ps.Name].Transform = ps.CFrame; c += 1 end
end
return "posed " .. c
