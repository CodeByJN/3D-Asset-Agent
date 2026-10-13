local old = workspace:FindFirstChild("TmpRunRig_h"); if old then old:Destroy() end
local rig = game:GetService("Players"):CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), Enum.HumanoidRigType.R15)
rig.Name = "TmpRunRig_h"; rig.Parent = workspace
rig:PivotTo(CFrame.new(500, 300, 0)); rig.HumanoidRootPart.Anchored = true
return "rig"
