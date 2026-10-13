local SS = game:GetService("ServerStorage")
local old = SS:FindFirstChild("BenchRun_harness_v2")
if old then old:Destroy() end
local ks = Instance.new("KeyframeSequence")
ks.Name = "BenchRun_harness_v2"
ks.Loop = true
ks.Priority = Enum.AnimationPriority.Movement
local T, N = 0.6, 8
local sin, cos, pi = math.sin, math.cos, math.pi
local function A(x, y, z) return CFrame.Angles(x or 0, y or 0, z or 0) end
local function leg(p)
  local thigh = 0.25 + 0.95 * sin(p)
  local knee = -(1.0 + 0.9 * cos(p - 0.3))
  local foot = -0.25 * cos(p) + 0.1
  return thigh, knee, foot
end
for i = 0, N do
  local t = i * T / N
  local p = 2 * pi * (i % N) / N
  local kf = Instance.new("Keyframe"); kf.Time = t; kf.Parent = ks
  local function pose(name, cf, parent)
    local ps = Instance.new("Pose"); ps.Name = name; ps.CFrame = cf
    ps.EasingStyle = Enum.PoseEasingStyle.Cubic; ps.EasingDirection = Enum.PoseEasingDirection.InOut
    ps.Parent = parent; return ps
  end
  local hrp = pose("HumanoidRootPart", CFrame.new(), kf)
  local lt = pose("LowerTorso", CFrame.new(0, 0.15 * cos(2 * p) - 0.1, 0) * A(-0.22, 0.15 * sin(p), 0), hrp)
  local ut = pose("UpperTorso", A(-0.2, -0.3 * sin(p), 0), lt)
  pose("Head", A(0.35, 0.12 * sin(p), 0), ut)
  -- arms opposite to legs
  local function arm(side, ph, zs)
    local ua = pose(side .. "UpperArm", A(-1.35 * sin(ph) + 0.15, 0, zs * 0.12), ut)
    local la = pose(side .. "LowerArm", A(1.4 + 0.35 * sin(ph), 0, 0), ua)
    pose(side .. "Hand", A(0.1, 0, 0), la)
  end
  arm("Right", p, 1); arm("Left", p + pi, -1)
  local function legs(side, ph)
    local th, kn, ft = leg(ph)
    local ul = pose(side .. "UpperLeg", A(th, 0, 0), lt)
    local ll = pose(side .. "LowerLeg", A(kn, 0, 0), ul)
    pose(side .. "Foot", A(ft, 0, 0), ll)
  end
  legs("Right", p); legs("Left", p + pi)
end
ks.Parent = SS
local n = #ks:GetKeyframes()
return "ok " .. ks:GetFullName() .. " kfs=" .. n .. " len=" .. ks:GetKeyframes()[n].Time
