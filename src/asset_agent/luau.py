"""Luau run in Roblox Studio (through its MCP execute_luau) to build and read VFX.

Effects travel as tagged JSON (see vfx.py) inside a long-bracket string; one fixed interpreter
(BUILD) turns them into instances, and SERIALIZE turns instances in a place back into JSON, so a
Creator Store effect can be imported, recoloured, rescaled and rebuilt anywhere.
"""
import json

# Tagged JSON -> Roblox values, and instance trees -> instances under a host part.
DECODE = r"""
local function V(x)
 if type(x)~='table' then return x end
 if x.c3 then return Color3.new(x.c3[1],x.c3[2],x.c3[3]) end
 if x.cs then local k={} for _,p in x.cs do table.insert(k,ColorSequenceKeypoint.new(p[1],Color3.new(p[2],p[3],p[4]))) end return ColorSequence.new(k) end
 if x.ns then local k={} for _,p in x.ns do table.insert(k,NumberSequenceKeypoint.new(p[1],p[2],p[3] or 0)) end return NumberSequence.new(k) end
 if x.nr then return NumberRange.new(x.nr[1],x.nr[2]) end
 if x.v2 then return Vector2.new(x.v2[1],x.v2[2]) end
 if x.v3 then return Vector3.new(x.v3[1],x.v3[2],x.v3[3]) end
 if x.cf then local c=x.cf return CFrame.new(c[1],c[2],c[3])*CFrame.fromOrientation(math.rad(c[4]),math.rad(c[5]),math.rad(c[6])) end
 if x.enum then local a,b=string.match(x.enum,'([^.]+)%.(.+)') return Enum[a][b] end
 return x
end
"""

BUILD = DECODE + r"""
local HS,TS=game:GetService('HttpService'),game:GetService('TweenService')
local function build(H,tag,nodes)
 local made,refs,all={}, {}, {}
 local function mk(nd,parent,path)
  local i
  if nd.class=='MeshPart' and nd.props and nd.props.MeshId then
   i=game:GetService('AssetService'):CreateMeshPartAsync(nd.props.MeshId)
  else i=Instance.new(nd.class) end
  i.Name=nd.name or nd.class
  for k,v in (nd.props or {}) do
   if k=='MeshId' and i:IsA('MeshPart') then
   elseif type(v)=='table' and v.ref then table.insert(refs,{i,k,v.ref})
   elseif k=='CFrame' and i:IsA('BasePart') then i.CFrame=H.CFrame*V(v)
   else i[k]=V(v) end
  end
  for k,v in (nd.attrs or {}) do i:SetAttribute(k,V(v)) end
  if nd.tween then i:SetAttribute('AssetAgentTween',HS:JSONEncode(nd.tween)) end
  if i:IsA('BasePart') then i.Anchored=true i.CanCollide=false i.CanQuery=false i.CanTouch=false end
  i:SetAttribute('AssetAgentVFX',tag)
  made[path]=i table.insert(all,i)
  for _,c in (nd.children or {}) do mk(c,i,path..'/'..(c.name or c.class)) end
  i.Parent=parent
 end
 for _,nd in nodes do mk(nd,H,nd.name or nd.class) end
 for _,r in refs do r[1][r[2]]=made[r[3]] end
 return all
end
local function play(list)
 for _,i in list do
  local n=i:GetAttribute('EmitCount')
  if n and i:IsA('ParticleEmitter') then task.delay(i:GetAttribute('EmitDelay') or 0,function() i:Emit(n) end) end
  local tw=i:GetAttribute('AssetAgentTween')
  if tw then
   local t=HS:JSONDecode(tw) local goal={}
   for k,v in t.props do goal[k]=V(v) end
   local start={} for k in goal do start[k]=i[k] end
   task.delay(t.delay or 0,function()
    for k,v in start do i[k]=v end
    TS:Create(i,TweenInfo.new(t.time or 0.5,Enum.EasingStyle[t.style or 'Quad'],Enum.EasingDirection.Out),goal):Play()
   end)
  end
 end
end
"""

# Instance tree -> tagged JSON. Properties equal to a fresh instance's defaults are left out.
SERIALIZE = r"""
local HS=game:GetService('HttpService')
local PROPS={
 ParticleEmitter={'Acceleration','Brightness','Color','Drag','EmissionDirection','Enabled','FlipbookFramerate','FlipbookLayout','FlipbookMode','FlipbookStartRandom','Lifetime','LightEmission','LightInfluence','LockedToPart','Orientation','Rate','RotSpeed','Rotation','Shape','ShapeInOut','ShapePartial','ShapeStyle','Size','Speed','SpreadAngle','Squash','Texture','TimeScale','Transparency','VelocityInheritance','WindAffectsDrag','ZOffset'},
 Beam={'Attachment0','Attachment1','Brightness','Color','CurveSize0','CurveSize1','Enabled','FaceCamera','LightEmission','LightInfluence','Segments','Texture','TextureLength','TextureMode','TextureSpeed','Transparency','Width0','Width1','ZOffset'},
 Trail={'Attachment0','Attachment1','Brightness','Color','Enabled','FaceCamera','Lifetime','LightEmission','LightInfluence','MaxLength','MinLength','Texture','TextureLength','TextureMode','Transparency','WidthScale'},
 Attachment={'CFrame'},
 PointLight={'Brightness','Color','Enabled','Range','Shadows'},
 SpotLight={'Angle','Brightness','Color','Enabled','Face','Range','Shadows'},
 SurfaceLight={'Angle','Brightness','Color','Enabled','Face','Range','Shadows'},
 Part={'CFrame','CastShadow','Color','Material','Reflectance','Shape','Size','Transparency'},
 MeshPart={'CFrame','CastShadow','Color','Material','MeshId','Reflectance','Size','TextureID','Transparency'},
 SpecialMesh={'MeshId','MeshType','Offset','Scale','TextureId','VertexColor'},
 Decal={'Color3','Face','Texture','Transparency'},
}
local function r(x) return math.floor(x*1000+0.5)/1000 end
local ROOT,ORIGIN
local function pathOf(i) local p={} while i and i~=ROOT do table.insert(p,1,i.Name) i=i.Parent end return table.concat(p,'/') end
local function E(v)
 local t=typeof(v)
 if t=='number' then return r(v)
 elseif t=='Color3' then return {c3={r(v.R),r(v.G),r(v.B)}}
 elseif t=='ColorSequence' then local o={} for _,k in v.Keypoints do table.insert(o,{r(k.Time),r(k.Value.R),r(k.Value.G),r(k.Value.B)}) end return {cs=o}
 elseif t=='NumberSequence' then local o={} for _,k in v.Keypoints do table.insert(o,{r(k.Time),r(k.Value),r(k.Envelope)}) end return {ns=o}
 elseif t=='NumberRange' then return {nr={r(v.Min),r(v.Max)}}
 elseif t=='Vector2' then return {v2={r(v.X),r(v.Y)}}
 elseif t=='Vector3' then return {v3={r(v.X),r(v.Y),r(v.Z)}}
 elseif t=='CFrame' then local a,b,c=v:ToOrientation() return {cf={r(v.X),r(v.Y),r(v.Z),r(math.deg(a)),r(math.deg(b)),r(math.deg(c))}}
 elseif t=='EnumItem' then return {enum=tostring(v):sub(6)}
 elseif t=='Instance' then return {ref=pathOf(v)}
 end
 return v
end
local DEF,stats={}, {scripts=0}
local function node(i)
 local list=PROPS[i.ClassName]
 if not list then
  if i:IsA('LuaSourceContainer') then stats.scripts+=1 end
  return nil
 end
 DEF[i.ClassName]=DEF[i.ClassName] or Instance.new(i.ClassName)
 local d,props=DEF[i.ClassName],{}
 for _,p in list do
  local ok,v=pcall(function() return i[p] end)
  if ok and v~=nil then
   if p=='CFrame' and i:IsA('BasePart') then v=ORIGIN:ToObjectSpace(v) end
   local ev=E(v)
   local okd,dv=pcall(function() return d[p] end)
   if not okd or HS:JSONEncode(ev)~=HS:JSONEncode(E(dv)) or p=='Size' or p=='CFrame' then props[p]=ev end
  end
 end
 local attrs=nil
 for k,v in i:GetAttributes() do attrs=attrs or {} attrs[k]=E(v) end
 stats[i.ClassName]=(stats[i.ClassName] or 0)+1
 return {class=i.ClassName,name=i.Name,props=props,attrs=attrs,children=nil}
end
local function walk(i)
 local out={}
 for _,c in i:GetChildren() do
  local n=node(c)
  if n then local k=walk(c) if #k>0 then n.children=k end table.insert(out,n)
  else for _,x in walk(c) do table.insert(out,x) end end
 end
 return out
end
local function serialize(root)
 stats={scripts=0}
 ROOT=root
 ORIGIN=root:IsA('BasePart') and root.CFrame or (root:IsA('Model') and root:GetPivot()) or CFrame.new()
 local nodes
 if root:IsA('Attachment') or root:IsA('ParticleEmitter') or root:IsA('Beam') or root:IsA('Trail') then
  ROOT=root.Parent local n=node(root) local k=walk(root) if #k>0 then n.children=k end nodes={n}
 else nodes=walk(root) end
 local host=root:IsA('BasePart') and {size=E(root.Size),shape=E(root:IsA('Part') and root.Shape or nil)} or nil
 return HS:JSONEncode({name=root.Name,class=root.ClassName,nodes=nodes,stats=stats,host=host})
end
"""


def data(obj) -> str:
    """JSON in a Luau long-bracket string literal."""
    s = json.dumps(obj, separators=(",", ":"))
    level = 1
    while f"]{'=' * level}]" in s:
        level += 1
    eq = "=" * level
    return f"[{eq}[{s}]{eq}]"
