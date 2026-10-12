# Run shape generation on your own GPU

With no setup, `make_asset` uses free Hugging Face Spaces, which have a daily limit. If you have an NVIDIA GPU with **6 GB+ of VRAM**, you can run Hunyuan3D-2 yourself: generation is unlimited and private.

The GPU can be in the machine you work on, or **in another machine** (a desktop at home serving a laptop, say).

We only use Hunyuan for **shape**. Our pipeline does the texturing, so Hunyuan's texture model and its CUDA build are skipped.

`backend="auto"` (the default) uses your GPU server when it's reachable, and falls back to the free Spaces when it isn't.

## 1. Install the harness (every machine)
Needs git, [uv](https://docs.astral.sh/uv/) and Blender 5.0. The GPU machine doesn't need Blender if it only serves.
```
git clone https://github.com/CodeByJN/3D-Asset-Agent
cd 3D-Asset-Agent
uv sync --python 3.12
uv run asset-agent status
```
`status` shows what's installed and which backend `auto` will use. If Blender isn't found, set `BLENDER_EXE`.

## 2. Install Hunyuan3D-2 (the GPU machine)
```
uv run asset-agent setup
```
This takes a few minutes. It:
- reads your GPU with `nvidia-smi`
- clones Hunyuan3D-2 into `~/.asset-agent/Hunyuan3D-2` in its own Python 3.10 environment
- installs PyTorch wheels that match the card: `cu126` for 10-series (Pascal) through 40-series, `cu128` for 50-series
- checks that PyTorch can see the GPU
- picks the model: `full` with 10 GB+ of VRAM, otherwise `mini`. Override with `--model mini|full`.

It's safe to re-run.

Before starting, stop anything else holding VRAM, such as a local LLM. Check with `nvidia-smi`.

## 3a. Same machine
```
uv run asset-agent serve
```
Leave it running and work as usual; `auto` picks it up. It only listens on this machine and needs no key.

## 3b. GPU on another machine
On the **GPU machine**:
```
uv run asset-agent serve --remote
```
This prints a key and one `connect` line per address. A key is created on the first run and reused after that.

On the **machine you work on**, run the line it printed:
```
uv run asset-agent connect http://192.168.1.50:8080 --key <key>
```
- It saves the address and key to `~/.asset-agent/config.json` and prints `ok`.
- The MCP server and `make_asset` then use it automatically.
- To check it from a browser: `http://<address>:8080/?key=<key>`

**Firewall on the GPU machine:** allow TCP 8080 from your home network only.
- Windows: `New-NetFirewallRule -DisplayName "asset-agent 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private`, as Administrator, with the network set to Private.
- Linux with ufw: `sudo ufw allow from 192.168.0.0/16 to any port 8080 proto tcp`

**Away from home:** install [Tailscale](https://tailscale.com) (free) on both machines and sign in to the same account. `serve --remote` then also prints a `100.x.y.z` address, which works from anywhere. Don't forward port 8080 on your router: Tailscale is private and needs no open ports.

## Day to day
- GPU machine: `uv run asset-agent serve --remote` and leave it running. `Ctrl+C` stops it and frees the GPU.
- Your machine: work as usual. If the server is down, `auto` falls back to the free Spaces, and `status` tells you which one it's using.
- Text prompts still make their reference image on the free FLUX Space. To stay fully offline, pass `image=` instead.

## Troubleshooting
- **`Error(s) in loading state_dict for SingleImageEncoder`:** `transformers` is too new. Re-run `asset-agent setup`, which pins it below 5.18.
- **`--enable_flashvdm` errors:** run `asset-agent serve --no-flashvdm`.
- **Out of memory:** something else is using VRAM, or try `--model mini`.
- **`wrong key`:** run `connect` again with the key printed by `serve --remote`.
- **`offline`:** the server isn't running, the address is wrong, or the firewall is blocking it.
- **10-series cards:** keep a driver that still supports them. They're slow at the half-precision maths Hunyuan uses, so expect slower shapes than on newer cards.

## Test checklist (write down the numbers)
- [ ] `asset-agent setup` finishes and prints `torch sees <your GPU>`.
- [ ] `asset-agent serve`: VRAM use while generating, and seconds per shape, for `mini` vs `full`.
- [ ] From the laptop, `asset-agent connect …` prints `ok` and `status` shows `auto -> local`.
- [ ] `make_asset` prints `gen local …s | ok tris=…` and the preview looks right.
- [ ] **Roblox Studio:** import `assets/<name>/export/<name>.fbx` and `.glb` with the 3D Importer. Check the size in studs, that the texture shows, that there are no triangle warnings, and which format imports better.
