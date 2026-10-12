# Home PC setup and test plan (Threadripper 1950X, 50 GB RAM, GTX 1080 Ti 11 GB)

The goal is to run Hunyuan3D-2 shape generation on your own GPU, so generation is free and unlimited. We only need **shape** from it. Our pipeline does the texturing (project or flat style), so you can skip Hunyuan's heavy texture model and its custom CUDA build.

## 1. Harness (same as the laptop)
1. Install git, [uv](https://docs.astral.sh/uv/), Blender 5.0 and the GitHub CLI.
2. Clone the repo:
   ```
   git clone https://github.com/CodeByJN/3D-Asset-Agent
   cd 3D-Asset-Agent
   uv sync --python 3.12
   uv run --python 3.12 pytest -q
   ```
   - All tests should pass in about a minute. That proves Blender, the pipeline and the MCP server work.
   - If Blender isn't at `C:\Program Files\Blender Foundation\Blender 5.0\blender.exe`, set `BLENDER_EXE`.
   - The `UV_*` paths in `.mcp.json` and `CLAUDE.md` are only needed for the Claude desktop app. Adjust them if your username differs.
3. Quick free test, which needs no GPU:
   ```
   uv run --python 3.12 python -c "from asset_agent import make_asset; print(make_asset('assets/chest', prompt='a wooden treasure chest, low poly'))"
   ```

## 2. Local Hunyuan3D-2 (shape only)
The 1080 Ti is a Pascal card (sm_61). Two things to know before you start:
- **Driver.** NVIDIA has been ending Pascal support in its newest driver and CUDA releases. Use a driver that still lists the 1080 Ti and **CUDA 12.6 PyTorch wheels** (`cu126`), not cu128 or newer.
- **Speed.** Pascal is very slow at half precision (fp16), which Hunyuan uses. Expect generation to be slower than on newer cards. That's the main thing this test will tell us.

Steps:
1. Clone and create an environment:
   ```
   git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2
   cd Hunyuan3D-2
   uv venv --python 3.10
   .venv\Scripts\activate
   ```
2. Install PyTorch, the requirements and the package:
   ```
   uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
   uv pip install -r requirements.txt
   uv pip install -e .
   ```
3. Check the GPU works. This should print `True` and `(6, 1)`:
   ```
   python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_capability())"
   ```
4. Start the app with the small "mini" model, which needs roughly 5–6 GB of VRAM for shape:
   ```
   python gradio_app.py --model_path tencent/Hunyuan3D-2mini --subfolder hunyuan3d-dit-v2-mini-turbo --enable_flashvdm --low_vram_mode --port 8080
   ```
   - Flag names can change between versions. Run `python gradio_app.py --help` if one is rejected.
   - It may warn that texture generation is unavailable. That's fine, because we don't use it.
   - If `--enable_flashvdm` errors on Pascal, drop it.
   - If the mini model works well, also try the full `tencent/Hunyuan3D-2` model (subfolder `hunyuan3d-dit-v2-0-turbo`). It may still fit in 11 GB for shape.
5. Open http://127.0.0.1:8080 and generate one shape by hand from an image to confirm it works.

## 3. Point the harness at it
In the 3D-Asset-Agent folder:
```
set HUNYUAN_URL=http://127.0.0.1:8080
uv run --python 3.12 python -c "from asset_agent import make_asset; print(make_asset('assets/chest_local', prompt='a wooden treasure chest, low poly', backend='local'))"
```
- Text prompts still make their image on the free FLUX Space. To stay fully offline, pass `image=r'C:\path\to\picture.png'` instead.
- To use the home GPU from the laptop: start Hunyuan with `--host 0.0.0.0` and set `HUNYUAN_URL=http://<home-pc-ip>:8080`.

## 4. Test checklist (write down the numbers)
- [ ] `pytest` passes.
- [ ] `make_asset` with `backend='hf'` works (free Spaces).
- [ ] Local Hunyuan: VRAM use (Task Manager → GPU), **seconds per shape**, mini model vs full model.
- [ ] `make_asset` with `backend='local'` gives `ok tris=…` and the preview looks right.
- [ ] **Roblox Studio:** import `assets/<name>/export/<name>.fbx` and `.glb` with the 3D Importer. Check:
  - size in studs (we export metres)
  - the texture shows up
  - no triangle warnings
  - which file format imports better
- [ ] **Claude Code MCP:** open the repo in Claude Code and ask for an asset. The `asset-agent` tools should appear (`make_asset`, `revise`, `preview`, …).
