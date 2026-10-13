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
 if x.u2 then return UDim2.new(x.u2[1],x.u2[2],x.u2[3],x.u2[4]) end
 if x.font then return Font.new('rbxasset://fonts/families/'..x.font..'.json',x.weight and Enum.FontWeight[x.weight] or Enum.FontWeight.Regular,x.italic and Enum.FontStyle.Italic or Enum.FontStyle.Normal) end
 if x.v3 then return Vector3.new(x.v3[1],x.v3[2],x.v3[3]) end
 if x.cf then local c=x.cf return CFrame.new(c[1],c[2],c[3])*CFrame.fromOrientation(math.rad(c[4]),math.rad(c[5]),math.rad(c[6])) end
 if x.enum then local a,b=string.match(x.enum,'([^.]+)%.(.+)') return Enum[a][b] end
 return x
end
"""

# Animates parts tagged with an AssetAgentAnim attribute (JSON: spin deg/s about the plane normal, orbit
# {radius, speed deg/s, phase, y}, bob {amp, period}, pulse {amp, period}) relative to their parent part,
# every frame. Returns a function(model, tag|nil, alive()) that connects to Heartbeat.
ANIMATE = r"""
local RS,HS=game:GetService('RunService'),game:GetService('HttpService')
return function(model,tag,alive)
 local items={}
 for _,p in model:GetDescendants() do
  local a=p:GetAttribute('AssetAgentAnim')
  if a and p:IsA('BasePart') and (tag==nil or p:GetAttribute('AssetAgentVFX')==tag) then
   table.insert(items,{p=p,a=HS:JSONDecode(a),base=p:GetAttribute('AssetAgentBase') or CFrame.new(),size=p.Size})
  end
 end
 local t0=os.clock() local conn
 conn=RS.Heartbeat:Connect(function()
  if not alive() then conn:Disconnect() return end
  local t=os.clock()-t0
  for _,it in items do
   local a,anchor=it.a,it.p.Parent
   if anchor and anchor:IsA('BasePart') then
    local cf=it.base
    if a.orbit then local o=a.orbit
     cf=CFrame.Angles(0,math.rad((o.phase or 0)+(o.speed or 30)*t),0)*CFrame.new(o.radius or 3,o.y or 0,0)*it.base.Rotation end
    if a.bob then cf=CFrame.new(0,a.bob.amp*math.sin(2*math.pi*t/a.bob.period),0)*cf end
    if a.spin then cf=cf*CFrame.Angles(0,0,math.rad(a.spin*t)) end
    it.p.CFrame=anchor.CFrame*cf
    if a.pulse then local k=1+a.pulse.amp*math.sin(2*math.pi*t/a.pulse.period) it.p.Size=it.size*Vector3.new(k,k,1) end
   end
  end
 end)
 return #items
end
"""

BUILD = DECODE + "local animate=(function()" + ANIMATE + "end)()\nlocal ANIMATE_SRC=" + "[==[" + ANIMATE + "]==]\n" + r"""
local HS,TS=game:GetService('HttpService'),game:GetService('TweenService')
-- textures we haven't uploaded arrive as pixels and become EditableImages (kept in _G so they stay alive)
_G.AssetAgentTex=_G.AssetAgentTex or {}
local TEXDATA={}
local function setTextures(t) for k,v in t do TEXDATA[k]=v end end
local B64D={} for i=1,64 do B64D[string.byte('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',i)]=i-1 end
local function unb64(s,len)
 local out=buffer.create(len) local o=0
 for i=1,#s,4 do
  local a,b,c,d=B64D[string.byte(s,i)],B64D[string.byte(s,i+1)],B64D[string.byte(s,i+2)] or 0,B64D[string.byte(s,i+3)] or 0
  local v=a*262144+b*4096+c*64+d
  if o<len then buffer.writeu8(out,o,bit32.rshift(v,16)) end
  if o+1<len then buffer.writeu8(out,o+1,bit32.band(bit32.rshift(v,8),255)) end
  if o+2<len then buffer.writeu8(out,o+2,bit32.band(v,255)) end
  o+=3
 end
 return out
end
local function tex(name)
 local d=TEXDATA[name] if not d then return nil end
 local data=d.az or d.rgbaz
 local key=name..'@'..d.n..'#'..#data
 if _G.AssetAgentTex[key] then return _G.AssetAgentTex[key] end
 local n=d.n local raw=unb64(data,math.floor(#data*3/4)) local len=buffer.len(raw)
 local buf=buffer.create(n*n*4)
 for i=0,n*n-1 do buffer.writeu32(buf,i*4,0x00FFFFFF) end  -- white, fully transparent
 local o,p=0,0  -- read position, pixel
 local step=d.az and 1 or 4
 while o<len and p<n*n do
  local a=buffer.readu8(raw,o)
  if a==0 then p+=buffer.readu8(raw,o+1) o+=2
  else
   if step==1 then buffer.writeu8(buf,p*4+3,a)
   else buffer.writeu8(buf,p*4,buffer.readu8(raw,o+1)) buffer.writeu8(buf,p*4+1,buffer.readu8(raw,o+2))
    buffer.writeu8(buf,p*4+2,buffer.readu8(raw,o+3)) buffer.writeu8(buf,p*4+3,a) end
   o+=step p+=1
  end
 end
 local img=game:GetService('AssetService'):CreateEditableImage({Size=Vector2.new(n,n)})
 img:WritePixelsBuffer(Vector2.zero,img.Size,buf)
 local c=Content.fromObject(img) _G.AssetAgentTex[key]=c _G.AssetAgentTex[key..'#img']=img
 return c
end
local function build(H,tag,nodes)
 local made,refs,all,anims={}, {}, {}, false
 local model=H.Parent and H.Parent:IsA('Model') and H.Parent or H
 local function anchorFor(nd,parent)
  if nd.attach then return model:FindFirstChild(nd.attach,true) or H end
  return parent
 end
 local function plane(nd,parent)  -- a flat image: thin invisible part, image on both faces, unlit and bright
  local pr=nd.props or {} local sz=pr.Size and pr.Size.v2 or {4,4}
  local p=Instance.new('Part') p.Name=nd.name or 'Plane' p.Size=Vector3.new(sz[1],sz[2],0.05) p.Transparency=1
  for _,face in {Enum.NormalId.Front,Enum.NormalId.Back} do
   local g=Instance.new('SurfaceGui') g.Face=face g.LightInfluence=0 g.Brightness=pr.Brightness or 2
   g.SizingMode=Enum.SurfaceGuiSizingMode.PixelsPerStud g.PixelsPerStud=math.min(64,1000/math.max(sz[1],sz[2])) g.Parent=p  -- big canvases don't render
   local im=Instance.new('ImageLabel') im.Size=UDim2.fromScale(1,1) im.BackgroundTransparency=1
   local tc=type(pr.Image)=='string' and pr.Image:sub(1,10)=='texture://' and tex(pr.Image:sub(11))
   if tc then im.ImageContent=tc else im.Image=pr.Image or '' end im.ImageColor3=pr.Color and V(pr.Color) or Color3.new(1,1,1)
   im.ImageTransparency=pr.Transparency or 0 im.Parent=g
  end
  return p
 end
 local function mk(nd,parent,path)
  local i
  parent=anchorFor(nd,parent)
  if nd.class=='Plane' then i=plane(nd,parent)
  elseif nd.class=='MeshPart' and nd.props and nd.props.MeshId then
   i=game:GetService('AssetService'):CreateMeshPartAsync(nd.props.MeshId)
  else i=Instance.new(nd.class) end
  i.Name=nd.name or nd.class
  for k,v in (nd.class=='Plane' and {CFrame=(nd.props or {}).CFrame} or nd.props or {}) do
   if k=='MeshId' and i:IsA('MeshPart') then
   elseif type(v)=='table' and v.ref then table.insert(refs,{i,k,v.ref})
   elseif k=='CFrame' and i:IsA('BasePart') then i.CFrame=(parent:IsA('BasePart') and parent or H).CFrame*V(v)
    i:SetAttribute('AssetAgentBase',V(v))
   elseif type(v)=='string' and v:sub(1,10)=='texture://' then
    local c=tex(v:sub(11)) if c then if k=='Image' then i.ImageContent=c else i.TextureContent=c end end
   else i[k]=V(v) end
  end
  for k,v in (nd.attrs or {}) do i:SetAttribute(k,V(v)) end
  if nd.tween then i:SetAttribute('AssetAgentTween',HS:JSONEncode(nd.tween)) end
  if nd.anim then i:SetAttribute('AssetAgentAnim',HS:JSONEncode(nd.anim)) anims=true end
  if i:IsA('BasePart') then i.Anchored=true i.CanCollide=false i.CanQuery=false i.CanTouch=false end
  i:SetAttribute('AssetAgentVFX',tag)
  made[path]=i table.insert(all,i)
  for _,c in (nd.children or {}) do mk(c,i,path..'/'..(c.name or c.class)) end
  i.Parent=parent
 end
 for _,nd in nodes do mk(nd,H,nd.name or nd.class) end
 for _,r in refs do r[1][r[2]]=made[r[3]] end
 if anims then  -- in game: a client script plays the animation for each player
  local sc=Instance.new('Script') sc.Name='AssetAgentAnimator' sc.RunContext=Enum.RunContext.Client
  sc:SetAttribute('AssetAgentVFX',tag)
  pcall(function() sc.Source='local animate=(function()'..ANIMATE_SRC..'end)()\nanimate(script.Parent.Parent and script.Parent.Parent:IsA("Model") and script.Parent.Parent or script.Parent,'..string.format('%q',tag)..',function() return script.Parent~=nil end)' end)
  sc.Parent=H table.insert(all,sc)
 end
 return all
end
local SLOW=1 -- >1 plays effects in slow motion (for recording): particle TimeScale 1/SLOW, timings x SLOW
local function play(list)
 for _,i in list do
  if i:IsA('ParticleEmitter') then i.TimeScale=1/SLOW end
  local n=i:GetAttribute('EmitCount')
  if n and i:IsA('ParticleEmitter') then task.delay((i:GetAttribute('EmitDelay') or 0)*SLOW,function() i:Emit(n) end) end
  local tw=i:GetAttribute('AssetAgentTween')
  if tw then
   local t=HS:JSONDecode(tw) local goal={}
   for k,v in t.props do goal[k]=V(v) end
   local start={} for k in goal do start[k]=i[k] end
   task.delay((t.delay or 0)*SLOW,function()
    for k,v in start do i[k]=v end
    TS:Create(i,TweenInfo.new((t.time or 0.5)*SLOW,Enum.EasingStyle[t.style or 'Quad'],Enum.EasingDirection.Out),goal):Play()
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
