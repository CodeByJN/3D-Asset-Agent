--!nocheck
-- Asset Agent Review: a Studio panel for grading the asset on the review stage (workspace.AssetAgentReview).
-- It talks to the asset-agent MCP server's review window on 127.0.0.1; the address (with its token) is
-- the stage's ReviewURL attribute, set each time Claude calls review(). Installed into Studio's local
-- Plugins folder by `python -m asset_agent studio-plugin` (or on the first review); the source of truth
-- is src/asset_agent/studio_plugin.lua in the 3D-Asset-Agent repo.
local HS = game:GetService("HttpService")

local C = {
	bg = Color3.fromRGB(20, 26, 44), field = Color3.fromRGB(11, 13, 22), line = Color3.fromRGB(40, 49, 83),
	fg = Color3.fromRGB(238, 241, 251), muted = Color3.fromRGB(148, 160, 196), accent = Color3.fromRGB(255, 200, 61),
	ink = Color3.fromRGB(29, 22, 0), good = Color3.fromRGB(60, 207, 142), bad = Color3.fromRGB(255, 107, 107),
	info = Color3.fromRGB(108, 182, 255),
}

local toolbar = plugin:CreateToolbar("Asset Agent")
local button = toolbar:CreateButton("AssetAgentReview", "Grade the asset on the review stage", "", "Review")
button.ClickableWhenViewportHidden = true
local dock = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, false, false, 340, 620, 300, 480)
local made, w = pcall(function() return plugin:CreateDockWidgetPluginGuiAsync("AssetAgentReview", dock) end)
if not made then w = plugin:CreateDockWidgetPluginGui("AssetAgentReview", dock) end  -- older Studio
w.Title = "Asset Review"
button.Click:Connect(function() w.Enabled = not w.Enabled end)
w:GetPropertyChangedSignal("Enabled"):Connect(function() button:SetActive(w.Enabled) end)

local function new(class, props, parent)
	local i = Instance.new(class)
	for k, v in props do i[k] = v end
	i.Parent = parent
	return i
end
local function round(p, r) new("UICorner", { CornerRadius = UDim.new(0, r or 7) }, p) end
local function stroke(p, color) new("UIStroke", { Color = color or C.line, ApplyStrokeMode = Enum.ApplyStrokeMode.Border }, p) end

local root = new("ScrollingFrame", { Size = UDim2.fromScale(1, 1), BackgroundColor3 = C.bg, BorderSizePixel = 0,
	CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.Y, ScrollBarThickness = 6 }, w)
new("UIPadding", { PaddingLeft = UDim.new(0, 14), PaddingRight = UDim.new(0, 14), PaddingTop = UDim.new(0, 14),
	PaddingBottom = UDim.new(0, 14) }, root)
new("UIListLayout", { Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder }, root)
local order = 0
local function label(props)
	order += 1
	return new("TextLabel", { LayoutOrder = order, BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 0),
		AutomaticSize = Enum.AutomaticSize.Y, TextWrapped = true, TextXAlignment = Enum.TextXAlignment.Left,
		Font = props.Font or Enum.Font.Gotham, TextSize = props.TextSize or 13, TextColor3 = props.TextColor3 or C.fg,
		Text = props.Text or "", RichText = false }, root)
end
local function heading(text) return label({ Text = string.upper(text), Font = Enum.Font.Code, TextSize = 11, TextColor3 = C.muted }) end

local title = label({ Text = "Asset Review", Font = Enum.Font.GothamBlack, TextSize = 24 })
local badge = label({ Text = "", Font = Enum.Font.Code, TextSize = 12, TextColor3 = C.accent })
local stats = label({ Text = "", Font = Enum.Font.Code, TextSize = 11, TextColor3 = C.muted })

heading("Rating")
order += 1
local starRow = new("Frame", { LayoutOrder = order, BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 30) }, root)
new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 3) }, starRow)
local stars = {}
local score = label({ Text = "", Font = Enum.Font.GothamBlack, TextSize = 20, TextColor3 = C.accent })

local function box(placeholder)
	order += 1
	local b = new("TextBox", { LayoutOrder = order, Size = UDim2.new(1, 0, 0, 74), BackgroundColor3 = C.field,
		TextColor3 = C.fg, PlaceholderColor3 = C.muted, PlaceholderText = placeholder, Text = "", Font = Enum.Font.Gotham,
		TextSize = 13, MultiLine = true, TextWrapped = true, ClearTextOnFocus = false,
		TextXAlignment = Enum.TextXAlignment.Left, TextYAlignment = Enum.TextYAlignment.Top }, root)
	round(b) stroke(b)
	new("UIPadding", { PaddingLeft = UDim.new(0, 8), PaddingRight = UDim.new(0, 8), PaddingTop = UDim.new(0, 6) }, b)
	return b
end
heading("Pros")
local pros = box("What works: shape, colours, particles...")
heading("Cons")
local cons = box("What to fix in the next version...")
local status = label({ Text = "", TextColor3 = C.muted })

order += 1
local row = new("Frame", { LayoutOrder = order, BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 38) }, root)
new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 6) }, row)
local function action(text, bg, ink)
	local b = new("TextButton", { Size = UDim2.new(1 / 3, -4, 1, 0), BackgroundColor3 = bg, TextColor3 = ink, Text = text,
		Font = Enum.Font.GothamBold, TextSize = 14, AutoButtonColor = true }, row)
	round(b, 8)
	return b
end
local back = action("Back", C.field, C.fg)
local place = action("Place", C.good, Color3.fromRGB(4, 20, 12))
local nextB = action("Next", C.accent, C.ink)
label({ Text = "Back / Next \u{203A} step through your reviews; the stage shows that version.", Font = Enum.Font.Code,
	TextSize = 10, TextColor3 = C.muted })

-- state: the same rules as the browser page (review.html)
local items, idx, follow, busy = {}, 0, true, false
local drafts, shownKey = {}, ""

local function item() return items[idx] end
local function open(it) return it ~= nil and it.decision == nil and it.current and not it.placing end
local function draft()
	local it = item()
	if not it then return { stars = 0, pros = "", cons = "" } end
	drafts[it.id] = drafts[it.id] or { stars = 0, pros = "", cons = "" }
	return drafts[it.id]
end

local function paintStars(n)
	for s, b in stars do
		b.BackgroundColor3 = s <= n and C.accent or C.field
		b.TextColor3 = s <= n and C.ink or C.muted
	end
	score.Text = n > 0 and (n .. "/10") or ""
end
for s = 1, 10 do
	local b = new("TextButton", { Size = UDim2.new(0.1, -3, 1, 0), Text = tostring(s), Font = Enum.Font.GothamBold,
		TextSize = 13, BackgroundColor3 = C.field, TextColor3 = C.muted, AutoButtonColor = true }, starRow)
	round(b, 6) stroke(b)
	b.Activated:Connect(function()
		if open(item()) then draft().stars = s paintStars(s) end
	end)
	stars[s] = b
end
pros:GetPropertyChangedSignal("Text"):Connect(function() if open(item()) then draft().pros = pros.Text end end)
cons:GetPropertyChangedSignal("Text"):Connect(function() if open(item()) then draft().cons = cons.Text end end)

local function setStatus(text, color) status.Text = text status.TextColor3 = color or C.muted end

local function request(method, path, body)
	local st = workspace:FindFirstChild("AssetAgentReview")
	local url = st and st:GetAttribute("ReviewURL")
	if not url or url == "" then return nil, "No review stage yet: ask Claude to review an asset." end
	local base, token = string.match(url, "^(https?://[^/]+)/%?t=(.+)$")
	if not base then return nil, "The stage has a bad ReviewURL." end
	local req = { Url = base .. path .. "?t=" .. token, Method = method }
	if body then
		req.Headers = { ["Content-Type"] = "application/json" }
		req.Body = HS:JSONEncode(body)
	end
	local ok, res = pcall(function() return HS:RequestAsync(req) end)
	if not ok then return nil, "Can't reach the harness (is Claude's asset-agent running?): " .. tostring(res) end
	if res.StatusCode == 401 then return nil, "The harness restarted: ask Claude to review again." end
	local okj, data = pcall(function() return HS:JSONDecode(res.Body) end)
	if not okj then return nil, "Bad reply from the harness (" .. res.StatusCode .. ")." end
	return data, nil
end

local function splitNote(n)
	n = n or ""
	return string.match(n, "pros: (.-); cons: ") or string.match(n, "pros: (.*)$") or "", string.match(n, "cons: (.*)$") or ""
end

local function render(force)
	local it = item()
	back.Active = not busy and idx > 1
	back.AutoButtonColor = back.Active
	back.TextTransparency = back.Active and 0 or 0.6
	if not it then
		title.Text = "Asset Review" badge.Text = "" stats.Text = ""
		setStatus("Nothing to review yet. When Claude calls review(), the asset appears on a stage above the map.")
		return
	end
	local pending = open(it)
	place.Active = not busy and pending
	place.TextTransparency = place.Active and 0 or 0.6
	nextB.Active = not busy and (pending or idx < #items)
	nextB.TextTransparency = nextB.Active and 0 or 0.6
	nextB.Text = pending and "Next" or "Next \u{203A}"
	local key = it.id .. ":" .. HS:JSONEncode({ it.decision, it.current, it.placing, it.error })
	if key == shownKey and not force then return end
	shownKey = key
	title.Text = it.name .. "  v" .. it.v .. "   (" .. idx .. "/" .. #items .. ")"
	stats.Text = it.line or ""
	stats.TextColor3 = string.find(it.line or "", "FAIL", 1, true) and C.bad or C.muted
	local d = it.decision
	if d then
		badge.Text = d.action == "place" and "PLACED IN STUDIO" or "SENT FOR A NEW VERSION"
		badge.TextColor3 = d.action == "place" and C.good or C.info
		local p, c = splitNote(d.note)
		pros.Text, cons.Text = p, c
		paintStars(d.stars or 0)
	elseif it.placing then
		badge.Text = "PLACING IN STUDIO..." badge.TextColor3 = C.good
	elseif not it.current then
		badge.Text = "OLDER VERSION, NOT REVIEWED" badge.TextColor3 = C.muted
		pros.Text, cons.Text = "", "" paintStars(0)
	else
		badge.Text = "WAITING FOR YOUR REVIEW" badge.TextColor3 = C.accent
		local dr = draft() pros.Text, cons.Text = dr.pros, dr.cons paintStars(dr.stars)
	end
	pros.TextEditable, cons.TextEditable = pending, pending
	if it.error then setStatus(it.error, C.bad)
	elseif it.placing then setStatus("Placing in Studio: uploading if the model changed...")
	elseif d and d.action == "next" and it.current then setStatus("Rating sent. Claude is making the next version; it appears on the stage when it's ready.", C.info)
	elseif d and d.result and d.result ~= "" then setStatus(d.result, C.good)
	else setStatus("") end
end

local function show(it)  -- put that version on the stage (the harness rebuilds it)
	if it then task.spawn(request, "POST", "/show", { id = it.id }) end
end

local function poll()
	local data, err = request("GET", "/state")
	if not data then
		items, idx = {}, 0
		render(true)
		if err then setStatus(err, C.muted) end
		return
	end
	local before, was = #items, item() and item().id
	items = data.items or {}
	if idx == 0 or (follow and #items ~= before) then
		idx = #items
		for i = #items, 1, -1 do if open(items[i]) then idx = i break end end
		if #items > before and open(item()) then w.Enabled = true end  -- a new version to grade: show the panel
	else
		idx = #items
		for i, x in items do if x.id == was then idx = i end end
	end
	render((item() and item().id) ~= was)
end

local function send(act)
	local it, d = item(), draft()
	if act == "next" and d.stars == 0 then setStatus("Pick 1-10 stars first so the next version knows what to fix.", C.bad) return end
	busy = true render(true)
	setStatus(act == "place" and "Placing in Studio..." or "Sending...")
	local res, err = request("POST", "/decide", { id = it.id, action = act, stars = d.stars > 0 and d.stars or nil,
		pros = d.pros, cons = d.cons })
	busy, follow = false, true
	if not res then setStatus(err, C.bad) return end
	if not res.ok then setStatus(res.error or "refused", C.bad) return end
	poll()
	render(true)
end

back.Activated:Connect(function()
	if busy or idx <= 1 then return end
	idx -= 1 follow = false
	render(true) show(item())
end)
nextB.Activated:Connect(function()
	if busy then return end
	if open(item()) then return send("next") end
	if idx < #items then
		idx += 1 follow = idx == #items
		render(true) show(item())
	end
end)
place.Activated:Connect(function() if not busy and open(item()) then send("place") end end)

render(true)
task.spawn(function()
	while true do
		if w.Enabled or workspace:FindFirstChild("AssetAgentReview") then pcall(poll) end
		task.wait(1)
	end
end)
