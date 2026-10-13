local rig = workspace.TmpRunRig_h
local idx = tonumber(_G.KFI or 3)
local kf = game.ServerStorage.BenchRun_harness:GetKeyframes()[idx]
local joints = {}
for _, d in ipairs(rig:GetDescendants()) do
  if d:IsA("BasePart") then d.Anchored = true end
  if d:IsA("Motor6D") then joints[d.Part1.Name] = {d.Part0, d.C0, d.C1}
  elseif d:IsA("AnimationConstraint") and d.Attachment1 then
    joints[d.Attachment1.Parent.Name] = {d.Attachment0.Parent, d.Attachment0.CFrame, d.Attachment1.CFrame} end
end
local function walk(ps)
  for _, ch in ipairs(ps:GetChildren()) do
    if ch:IsA("Pose") then
      local j = joints[ch.Name]
      if j then rig[ch.Name].CFrame = j[1].CFrame * j[2] * ch.CFrame * j[3]:Inverse() end
      walk(ch)
    end
  end
end
walk(kf.HumanoidRootPart)
return "ok"
