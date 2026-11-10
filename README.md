<p align="center"><img src="promptmaker/assets/icon_256.png" width="96" alt="PromptMaker icon"></p>

# PromptMaker

**A local desktop studio for writing AI image prompts.** You can describe an idea in plain words, build a prompt from 800 presets, refine it in a chat with a local LLM, or score it. Each prompt is formatted for the image model you're targeting, such as FLUX.2, SDXL, Pony, Illustrious, Anima, MOSS-Image, Qwen-Image, Midjourney V7, GPT Image and more.

Everything runs on your own computer by default. The AI features are optional and work with [Ollama](https://ollama.com), LM Studio, llama.cpp, KoboldCpp, vLLM or any OpenAI-compatible server, plus optional cloud providers. **Version 6.0** expands the Video maker's animation: pick which local **Wan2GP model preset** animates your scenes, add one optional **creative LoRA** with its own strength, set **project defaults with per-scene overrides**, and get a **preflight** that names missing files before a job starts and never downloads anything. **Version 5.3** added the **Video maker**: an idea or story (plus an optional song) becomes AI-planned scenes, stills, Wan2GP clips and a finished MP4, all locally. **Version 5.2** added **Wallpaper mode**: exact-size desktop and phone wallpapers with icon-safe composition. **Version 5.1** added **Face Swap**: generate new images with a source face and hair, or swap a face into an existing picture with a segmentation auto-mask and Auto-blend. **Version 5.0** added Characters, Storyboards & comics, Live sketch, optional LoRA training and automatic vision-model routing. Version 4 added wildcards and dynamic prompts, inpainting and regional prompts, library export/import with optional private GitHub gist sync, and prompt writing for video models (Wan, LTX-Video, HunyuanVideo). Version 3 added a first-run setup wizard, an automatic generate → check → refine loop, a LoRA manager, reusable characters and styles, and a pose sketcher with ControlNet. It can also generate images through **ComfyUI** or **Forge / AUTOMATIC1111**, turn images back into prompts, compare prompts A/B, and import checkpoint-specific guidance from **Civitai**.

**Latest release:** [v6.5.0](https://github.com/Kisahime/promptmaker/releases/tag/v6.5.0) · [Changelog](CHANGELOG.md)

![Create page](docs/screenshots/create.png)

## Features

- **🖥 Wallpaper mode** *(5.2, Tools)*: pick your screen – 1920×1080, 2560×1440, 3840×2160, 2560×1080 / 3440×1440 ultrawide, 1080×1920 phone or a custom size – and the app works out the sizes for your target model. It renders at about 1 MP in the screen's shape (1920×1080 → **1280×720 with hires fix ×1.5**), never asks for more than ×2 in one hires pass (4K = hires ×1.5, then Forge's upscaler ×2) so 8 GB cards cope, then Lanczos-resizes and centre-crops to the exact pixel size. See [Wallpaper mode](#wallpaper-mode).
- **🛍 Civitai Model browser** *(5.2, Library)*: search and filter Civitai models, see versions, files and the creator's settings, and download into your Forge / ComfyUI folders with resume and SHA256 checks. NSFW is off by default. See [Civitai Model browser](#civitai-model-browser).
- **🎭 Face Swap** *(5.1, Tools)*: our take on Fooocus' FaceSwap, using IP-Adapter Plus Face SDXL (weight 0.75, stop at 0.9 by default). Take the source face from a file, your last image, or a Character's reference image (Characters have a **🎭 Face Swap** button); it is cropped with an adjustable **hair margin** so the whole head and hair are used.
  - **Generate with face**: a new image from your prompt wearing the source face and hair.
  - **Swap into an existing image**: **Auto-mask face + hair** follows the real outline with segmentation models (YuNet / anime YOLO face detection, SegFormer face parsing for photos, anime-seg for anime). Every face is numbered; **👆 Pick face** chooses another person in group pictures. **Include hair** / **Include neck**, Style (Auto / Photo / Anime), Grow, Feather and a brush / eraser for touch-ups. The head is redrawn at SDXL's native resolution, like ADetailer.
  - **Auto-blend** (on by default, each step optional): a **harmonise pass** (light extra inpaint without the face model), **colour match** of skin tone, **grain / sharpness match**, and **seam blend** (Laplacian or Poisson) onto the original at full size; pixels outside the mask stay unchanged. **Show before** compares with the original.
  - Works with Forge (ControlNet IP-Adapter) and ComfyUI (ComfyUI_IPAdapter_plus). SDXL / Illustrious / Pony checkpoints only. See [Face Swap setup](#face-swap-setup).

  ![Face Swap: swap into an existing image](docs/screenshots/faceswap.png)
  *Swap into an existing image: the segmentation auto-mask on Vermeer's* Girl with a Pearl Earring *with the Auto-blend options, and a source face from a NASA crew portrait (both public domain).*
- **👁 Vision-model routing** *(5.0)*: everything that sends images (Image to Prompt, auto-caption, Auto-refine, gallery tagging) checks the model's capabilities through Ollama and only uses a real vision model, with a vision model picker on the LoRA page.
- **👤 Characters** *(5.0)*: save a person once with reference images, several named outfits, linked LoRAs + weights, trigger words and per-target-model tag sets. Insert a character + outfit into Create, Refine, a new region or the clipboard (the **👤 Character** buttons on Create and Inpaint & Regions do the same); swapping the outfit replaces the old one instead of piling tags up. With **Use as reference (IP-Adapter)** ticked, the first reference image is sent along when Forge has an IP-Adapter ControlNet model or ComfyUI has ComfyUI_IPAdapter_plus – otherwise it is skipped. New Gallery images are tagged with the characters whose trigger word / LoRA is in the prompt, and (opt-in) by the local Ollama vision model in the background.
- **📖 Storyboard & comics** *(5.0)*: write a short story, tick the cast, and the AI plans N panels (shot, characters, action, setting, dialogue, caption) using your Characters for consistency. Generate one panel or all of them through the normal queue, then lay out the page: grid templates (1–6 panels, manga), page sizes, fonts, editable speech bubbles and captions, drag Gallery thumbnails onto panels. Export PNG (one per page) or PDF, and save / open the storyboard as a `.pmstory` project file.
- **✏ Live sketch** *(5.0, Studio)*: draw rough shapes and colours; ~0.8 s after each stroke a fast low-step img2img (Lightning/Turbo-friendly presets, small resolution) regenerates the result beside the canvas. Uses a ControlNet scribble model instead when Forge/ComfyUI has one. Save the result, send it to Inpaint, or to Image to Prompt.
- **🎓 LoRA training** *(5.0, optional)*: pick 15–50 Gallery or folder images, caption them from their prompts or with the Ollama vision model, edit captions, choose an SDXL / Illustrious base checkpoint and a VRAM preset, and train with [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) run as a separate process (progress, log, cancel). The finished LoRA is copied to Forge's `models/Lora` and linked to the chosen Character. See [LoRA training](#lora-training-optional).
- **🏠 Home** *(4.1)*: a dashboard with your target model and linked checkpoint, Forge / Ollama status, recent images and quick-start buttons.
- **🗂 Gallery** *(4.1)*: justified rows that keep aspect ratios, hover preview, full-screen viewer (←/→, Esc), and right-click actions: *Inpaint this*, *Use as reference*, *Regenerate with hires*, *Upscale…*. Drag a thumbnail onto the inpaint canvas.
- **⤢ Upscale** *(4.1)*: Forge img2img at 1.5× with denoise 0.3 (same prompt and seed), or *Pure upscale* via Forge Extras / ComfyUI `ImageScaleBy`.
- **Queue & status** *(4.1)*: the top bar shows *Forge · active checkpoint* or *Offline* (click for settings); ☰ opens the queue to reorder or cancel jobs. Forge and ComfyUI show a live preview while they generate (ComfyUI: start it with `--preview-method auto`).
- **Look & feel** *(4.1.5)*: a slim icon rail with sections (Home, Studio, Characters, Gallery, Tools, Library, Settings), a top bar with status and queue, four themes with accent colours in Settings → Appearance, and short page fades.
- **✨ Create:** type an idea like *"an anime girl wearing an outfit in a setting"* and get finished prompts for your target model. You also get a separate negative prompt (where the model supports one) and recommended settings. A creativity slider controls how much it invents, and it can give 1–5 options with live streaming. **⚡ Offline build** works without AI.
- **🎨 Builder:** 13 categories and about 800 grouped presets as clickable chips, with global search, locks, randomise/surprise and your own custom chips. A live, model-aware preview and quick score update as you go.
- **💬 Refine:** chat with a local LLM about your prompt. Apply its suggestions in one click, with full version history and revert.
- **🔍 Analyse:** paste any prompt and break it into categories (offline or with AI), then load it into the Builder.
- **📊 Score:** a rubric covering clarity, specificity, composition, style coherence and model fit. There's an instant offline heuristic with concrete fixes, plus an optional AI deep review.
- **📋 Templates** with `{subject}`-style placeholders, **🔁 Batch** variations exported to .txt/.csv, searchable **🕘 History**, and **⭐ Favourites**.
- **📦 Preset packs:** import, export, enable or disable JSON packs. 5 starter packs are included.
- **🎯 Model profiles:** an editable JSON file that controls format, negative prompts, weighting, length, parameters and resolutions for each model.
- **🖼 Image generation** *(2.0)*: send any prompt to **ComfyUI** (API workflows with placeholders; SDXL and FLUX workflows included) or **Forge / AUTOMATIC1111**. It has a queue with progress and cancel, and a **Gallery** with thumbnails, full metadata, reuse prompt, same seed again and delete.
- **👁 Image to Prompt** *(2.0)*: drop, paste or open an image. A local vision model (Ollama vision models are detected automatically, or LM Studio / OpenAI-compatible) describes it as a prompt for your target model. Then send it to the Builder, Refine, Score or Generate.
- **⚖ A/B Test** *(2.0)*: compare two prompts side by side, with heuristic and AI scores and highlighted differences. With a backend connected, it renders both with the same seed. Pick a winner and it goes to History.
- **🎯 Civitai import** *(2.0)*: paste a Civitai model link (civitai.com, civitai.red …) or ID. PromptMaker reads the creator's recommended quality tags, negative prompt and settings, lets you review and edit them, and saves a profile that **inherits** from the matching base profile (Anima, Illustrious, Pony, SDXL …). It also has **⟳ Refresh from Civitai**. See [Civitai checkpoint profiles](#civitai-checkpoint-profiles).
- **🌐 Community** *(2.0)*: browse, install, update and uninstall packs and model profiles from the community index. Every download is checked with SHA-256.
- **🔌 Providers** *(2.0)*: Ollama, LM Studio, llama.cpp, KoboldCpp, vLLM, any OpenAI-compatible URL, and optional OpenAI, Anthropic, Google Gemini and OpenRouter. All AI features stream from the provider you choose.
- **⚙ Settings, tour and languages** *(2.0)*: a settings page, a first-run guided tour, an optional update check, portable or AppData data, and English / Español / Deutsch (the translations are machine-made).
- **🧭 Setup wizard** *(3.0)*: on first launch (and any time from the top bar or Settings) it checks whether Ollama is installed and running, lists your models, and downloads a recommended text model (`llama3.2`) and vision model (`qwen2.5vl`) with a progress bar. It also looks for Forge/A1111 (and tells you if `--api` is missing) and ComfyUI on their default ports, and saves what it finds.
- **🔄 Auto-refine** *(3.0)*: generate an image with Forge or ComfyUI, let a vision model score it against your idea (0–100, with what's missing or wrong), have the local AI rewrite the prompt, and repeat for N iterations or until a target score. Every iteration is shown with its image and review. Stop at any time and **Keep best**.
- **🧩 LoRAs** *(3.0)*: scans your models folder (Forge layout by default: `models\Lora`, `models\LyCORIS`, `embeddings`), hashes each file (SHA256 / AutoV2) and looks it up on Civitai for its name, trigger words, base model and preview. Results are cached. Filter by compatibility with the target model profile and insert `<lora:name:weight>` plus trigger words in one click.
- **👤 Presets** *(3.0)*: save **characters** (name, appearance tags, outfit, optional LoRA and weight, reference image) and **styles** (tags plus extra negative). Tick several to combine them in any prompt, and Batch can keep them fixed on every variation so a character stays consistent.
- **🧍 Pose** *(3.0)*: a canvas with draggable OpenPose-style skeletons (8 starter poses) and boxes for other subjects. It turns the sketch into composition tags (framing, pose, facing, positions) in the target model's style, exports an OpenPose PNG, and can generate with **ControlNet** via Forge's `alwayson_scripts` or by adding a ControlNet node to your ComfyUI workflow. Pick the ControlNet model from a dropdown filled from Forge; the page warns if it doesn't match your checkpoint (Anima needs an Anima ControlNet-LLLite model) and tells you whether the pose was actually applied.
- **🗂 Checkpoint picker** *(3.0)*: choose the Forge/ComfyUI checkpoint in Settings, on the Pose page or on the Auto-refine page. All three are the same setting.
- **🎲 Wildcards** *(4.0)*: write `__hair__` to pick a random line from `wildcards/hair.txt`, `{a|b|c}` to pick one option, `{2::a|b}` for weights, `{2$$a|b|c}` or `{1-3$$ and $$a|b|c}` to pick several. Folders (`__people/job__`), globs (`__places/*__`), YAML packs and nesting all work, using the same syntax as **sd-dynamic-prompts**. Results are seeded, so the same seed always gives the same prompt. Preview one expansion or a batch of N different variations, keep your ticked characters and styles fixed while everything else changes, and queue one image per variation. The page also creates, edits and deletes wildcard files, imports a folder or a Civitai zip pack (including zips inside zips), and has the local AI **write a new list** from a description such as "50 fantasy locations". Wildcards in prompts sent to Forge or ComfyUI are expanded with the image's seed, wherever the prompt comes from.
- **🖌 Inpaint & Regions** *(4.0)*: open an image (or take the last generated one), paint a mask and send it to **img2img inpaint**, with denoise, mask blur, *whole picture / only masked* and padding. Or draw boxes that each get their own prompt (**regional prompting**). ComfyUI needs nothing extra (`ConditioningSetArea` + `ConditioningCombine`). Forge has no built-in regional prompting, so PromptMaker uses the free **Forge Couple** extension when it's installed. If it isn't, the page says which extension to install, and you can send everything as one prompt with position words instead. The page uses the same checkpoint picker as Settings, Pose and Auto-refine.
- **🎬 Video** *(4.0)*: prompt writing for **Wan 2.2 / 2.1**, **LTX-Video** and **HunyuanVideo**. Fill in the subject, action and scene, and pick a camera move (14 presets: push in, orbit, tracking, FPV drone …), a motion preset, the shot size, lighting and style. The duration shows the frame count each model accepts (4n+1 or 8n+1 at its fps). **Build** writes the prompt offline in the structure that model prefers. **Write with AI** has your local LLM write it to the model's own prompting guide. You also get a word-count/camera check, the model's default negative prompt (where it has one), and saved video prompts. To render a whole video, use the **🎞 Video maker** *(5.3)*.
- **🎞 Video maker** *(5.3)*: idea or story (+ optional song and lyrics) → AI scene plan → a still per scene → Wan2GP clips for ticked scenes, slow zoom / pan for the rest → one MP4 with captions, crossfades and your song. Characters with fixed descriptions, seeds and an optional face lock (SDXL / Illustrious / Pony). *(6.0)*: choose the Wan2GP model preset, one optional creative LoRA, and per-scene animation overrides. See [Video maker](#video-maker).
- **Backend auto-detect** *(5.3)*: switches to the Forge or ComfyUI that is running at startup.
- **☁ Library sync** *(4.0)*: export everything (history, favourites, templates, versions, characters, styles, video prompts, LoRA metadata, wildcards, model profiles and settings) as one `.zip` or `.json`, and import it with **merge** or **replace**. When the same name has different content you choose *keep mine*, *take theirs* or *keep both*. Optional **private GitHub gist** sync with your own token (kept in the OS keyring) can push, pull or sync, deciding by last-modified time and asking you on a conflict. **API keys and tokens are never exported.**
- **🔍 Hires fix** *(4.0)*: switch on Forge/A1111's hires fix in **Settings → Image generation**, with the upscale factor, upscaler (loaded from your Forge), hires steps and denoise. It applies to every image PromptMaker generates (except inpaint).
- **🧹 Frees VRAM for images** *(4.0)*: right before each image goes to Forge or ComfyUI, PromptMaker tells Ollama to unload its text and vision models so the image model gets the GPU memory. On by default; you can turn it off in Settings → Image generation.
- **📐 Size picker** *(4.0)*: Auto-refine and Inpaint & Regions have their own image-size choice (square, wide, landscape, portrait, tall, SD1.5). *Model default* uses the profile's aspect ratio.
- **🎨 App icon** *(3.0)*: PromptMaker has its own icon on the window, taskbar and desktop shortcut.
- **🩹 Friendly errors** *(2.0)*:
  - Models a provider can't load (e.g. `llama3.2-vision` on Ollama 0.30+) get a plain explanation, a one-click switch to another installed model, and a copyable `ollama pull` command. Unsupported or failed models are marked in the model pickers.
  - When Forge/A1111's API is off, the app shows the exact `--api` fix, and Test connection reports the WebUI variant and version.
- **Safe by design:** destructive buttons (Clear all, Delete, Uninstall) confirm **in place**: a red *Confirm (4s)* button with a countdown. Toasts appear top-right and never block clicks.
- Four themes – sleek Graphite dark/light (default) plus cute Pastel and Pastel dusk – with accent colours (Ctrl+T toggles light/dark) and a **Ctrl+K** command palette from anywhere.

## Screenshots

| Characters *(5.0)* | Storyboard *(5.0)* |
|---|---|
| ![Characters](docs/screenshots/characters.png) | ![Storyboard](docs/screenshots/storyboard.png) |
| **Live sketch** *(5.0)* | **LoRA training** *(5.0)* |
| ![Live sketch](docs/screenshots/live_sketch.png) | ![LoRA training](docs/screenshots/lora_training.png) |

| Home *(4.1)* | Gallery *(4.1)* |
|---|---|
| ![Home](docs/screenshots/home.png) | ![Gallery](docs/screenshots/gallery.png) |
| **Queue** *(4.1)* | **Expanded rail** *(4.1.5)* |
| ![Queue](docs/screenshots/queue.png) | ![Expanded rail](docs/screenshots/sidebar_expanded.png) |

| Wildcards *(4.0)* | Inpaint & Regions *(4.0)* |
|---|---|
| ![Wildcards](docs/screenshots/wildcards.png) | ![Inpaint & Regions](docs/screenshots/inpaint.png) |
| **Video prompts** *(4.0)* | **Library sync** *(4.0)* |
| ![Video prompts](docs/screenshots/video.png) | ![Library sync](docs/screenshots/sync.png) |

| Setup wizard *(3.0)* | Auto-refine *(3.0)* |
|---|---|
| ![Setup wizard](docs/screenshots/setup.png) | ![Auto-refine](docs/screenshots/autorefine.png) |
| **LoRAs** *(3.0)* | **Presets** *(3.0)* |
| ![LoRAs](docs/screenshots/loras.png) | ![Presets](docs/screenshots/presets.png) |
| **Pose** *(3.0)* | **App icon** *(3.0)* |
| ![Pose](docs/screenshots/pose.png) | <img src="docs/screenshots/icon.png" width="128" alt="App icon"> |

| Builder | Refine (chat) |
|---|---|
| ![Builder](docs/screenshots/builder.png) | ![Refine (chat)](docs/screenshots/refine.png) |
| **Analyse** | **Score** |
| ![Analyse](docs/screenshots/analyse.png) | ![Score](docs/screenshots/score.png) |
| **Image to Prompt (unsupported models marked)** | **A/B Test** |
| ![Image to Prompt (unsupported models marked)](docs/screenshots/img2prompt.png) | ![A/B Test](docs/screenshots/abtest.png) |
| **Gallery** | **History (in-place confirm)** |
| ![Gallery](docs/screenshots/gallery.png) | ![History (in-place confirm)](docs/screenshots/history.png) |
| **Templates** | **Batch** |
| ![Templates](docs/screenshots/templates.png) | ![Batch](docs/screenshots/batch.png) |
| **Model profiles (Civitai-imported profile)** | **Community** |
| ![Model profiles (Civitai-imported profile)](docs/screenshots/profiles.png) | ![Community](docs/screenshots/community.png) |
| **Settings** | **Guided tour** |
| ![Settings](docs/screenshots/settings.png) | ![Guided tour](docs/screenshots/tour.png) |
| **Preset packs** | **Pastel theme** *(4.1.5)* |
| ![Preset packs](docs/screenshots/packs.png) | ![Pastel theme](docs/screenshots/pastel_home.png) |

**Civitai import (review before saving)**

![Civitai import](docs/screenshots/civitai.png)

*The images in the Gallery, A/B, Auto-refine, LoRAs and Image to Prompt screenshots are abstract placeholders, not real model output. All screenshots use demo data and are regenerated with `QT_QPA_PLATFORM=offscreen python tools/screenshots.py`.*

## Install

You need **Python 3.10+** ([python.org](https://www.python.org/downloads/); on Windows, tick *"Add python.exe to PATH"*).

**Windows**
1. Download or clone this repo.
2. Double-click **`install.bat`**. It checks Python, creates a `.venv`, installs PySide6 and keyring, offers to make a desktop shortcut, and checks for Ollama.
3. Start the app with **`run.bat`** or the desktop shortcut. A short guided tour runs the first time.

**Upgrading:** copy or `git pull` the new version over the old folder (your `data/` is kept), then run `install.bat` again. That installs new dependencies (5.1 adds `opencv-python-headless` and `onnxruntime` for Face Swap masks) and recreates the desktop shortcut. Your database is upgraded automatically on first start; history, favourites, templates, characters and settings are kept. Making a copy of `data/` first doesn't hurt.

### Requirements at a glance

- **Ollama** (optional, for AI features) with a text model (`ollama pull llama3.2`) and a **vision model** (`ollama pull qwen2.5vl`) for Image to Prompt, captions, Auto-refine and gallery tagging. The setup wizard can download both.
- **Forge** (or ComfyUI) for images. Forge must run with the API on: `set COMMANDLINE_ARGS=--api` in `webui-user.bat`.
- **Face Swap**: the face model, see [Face Swap setup](#face-swap-setup). *(6.5)* Tick **Remove background** to cut out just the head and set it on a plain White, Grey or Black fill, so the source photo's background doesn't leak into the swap.
- **Live sketch** (optional): for scribble mode, put [xinsir/controlnet-scribble-sdxl-1.0](https://huggingface.co/xinsir/controlnet-scribble-sdxl-1.0) in Forge's `models\ControlNet` folder; without it Live sketch uses fast img2img.
- **LoRA training** (optional): git and an NVIDIA GPU, see [LoRA training](#lora-training-optional).
- **Video maker** (optional): **ffmpeg** for the MP4 (PATH, Pinokio's `ffmpeg-env`, or Wan2GP's `ffmpeg_bins`), and [Wan2GP](https://github.com/deepbeepmeep/Wan2GP) only for animated scenes. See [Video maker](#video-maker).

**macOS / Linux** (should work, but is less tested)
```bash
./install.sh
./run.sh
```

There's no installer package and nothing system-wide. Everything stays in the folder, and you uninstall by deleting it.

## AI providers (optional)

Choose a provider in **⚙ Settings → AI provider**, then click **Test connection** and **Use this provider**. The model list in the top bar comes from that provider.

| Provider | Default URL | Notes |
|---|---|---|
| Ollama | `http://localhost:11434` | `ollama pull llama3.2`. For Image to Prompt, pull a vision model such as `llava`, `qwen2.5vl` or `gemma3`. |
| LM Studio | `http://localhost:1234/v1` | Start the local server in LM Studio. |
| llama.cpp server | `http://localhost:8080/v1` | `llama-server -m model.gguf` |
| KoboldCpp | `http://localhost:5001/v1` | |
| vLLM | `http://localhost:8000/v1` | |
| OpenAI-compatible (custom) | anything | Any `/v1/chat/completions` server. |
| OpenAI · Anthropic · Google Gemini · OpenRouter | cloud | Needs an API key. **Your prompts and images are sent to that company** and may cost money. |

**API keys** are stored in your OS keyring (Windows Credential Manager, macOS Keychain or Secret Service) through the `keyring` package. If no keyring is available, they go in `data/secrets.json` as **plain text**, and the app warns you when that happens. Local providers don't need a key.

If Ollama is installed but not running, the **Create** page has a **▶ Start Ollama** button. With a local provider, nothing leaves your machine.

## Image generation (optional)

PromptMaker doesn't include an image model. It sends prompts to a backend you already run:

- **ComfyUI** (default `http://127.0.0.1:8188`). PromptMaker uses ComfyUI's API: it queues a workflow, shows progress, and saves the result. Two API-format workflows are included in `promptmaker/workflows/`: **SDXL txt2img** and **FLUX txt2img** (the FLUX one expects an all-in-one checkpoint such as `flux1-dev-fp8.safetensors`). To use your own workflow, export it from ComfyUI with *Workflow → Export (API)*, replace values with placeholders, and drop it into `data/workflows/`. The placeholders are `{{prompt}}`, `{{negative}}`, `{{width}}`, `{{height}}`, `{{seed}}`, `{{steps}}`, `{{cfg}}`, `{{checkpoint}}`, `{{sampler}}` and `{{scheduler}}`. An optional `"_meta": {"name": …, "defaults": {…}}` key sets the display name and default values.
- **Forge / Forge Classic / Forge Neo / reForge / AUTOMATIC1111** (default `http://127.0.0.1:7860`). The API must be switched on: in `webui-user.bat` set `set COMMANDLINE_ARGS=--api` (plus any other flags), then restart the WebUI. If it's off, Test connection tells you exactly that. PromptMaker uses `/sdapi/v1/txt2img` and polls `/sdapi/v1/progress`.

**ControlNet (Pose page).** On Forge/A1111 the OpenPose image is sent as a ControlNet unit in `alwayson_scripts` (Forge has ControlNet built in; on AUTOMATIC1111 install *sd-webui-controlnet*). The ⟳ button lists models from `/controlnet/model_list`. On ComfyUI the image is uploaded with `/upload/image`, and `LoadImage → ControlNetLoader → ControlNetApplyAdvanced` nodes are added in front of each KSampler in your workflow. Put an OpenPose ControlNet model (for SDXL, e.g. *xinsir openpose*) in ComfyUI's `models/controlnet` folder.

**Inpaint (Inpaint & Regions page).** Forge/A1111: `/sdapi/v1/img2img` with `init_images`, `mask` (white = repaint), `denoising_strength`, `mask_blur`, `inpaint_full_res` (*Only masked*) and `inpaint_full_res_padding`. Nothing to install. ComfyUI: the picture is uploaded with the mask in its alpha channel, and `LoadImage → VAEEncode → GrowMask → SetLatentNoiseMask` replaces the empty latent in your workflow, with the KSampler's denoise set from the page.

**Regional prompts.** ComfyUI: one `CLIPTextEncode → ConditioningSetArea` per box, combined with your main prompt by `ConditioningCombine`, which is all built in. Forge has no built-in regional prompting, so install **Forge Couple**: in Forge go to *Extensions → Install from URL* and enter `https://github.com/Haoming02/sd-forge-couple`, then restart. PromptMaker detects it through `/sdapi/v1/scripts` (**🔎 Check support**) and sends the boxes in its *Advanced* mode, with the main prompt as a full-image background whose strength you set as *Base weight* (default 0.2). **Repeat main prompt in every region** (on by default) also adds the main prompt to each box. Put the shared scene and the count (`2girls, sitting on a beach`) in the main prompt and only each character's own details in their box. For two characters, two side-by-side boxes on a wide canvas (e.g. 1344×768) work best. Without it you get that message, and can choose **Send as one prompt instead** (for example `(a cat) on the left, (a dog) on the right`).

**Wildcards when generating.** `__name__` and `{a|b}` in any prompt you generate are expanded with the image's seed before it's sent, so Forge and ComfyUI don't need the Dynamic Prompts extension. Turn this off on the Wildcards page if you'd rather let the extension do it. A lone `{tag}` without `|` is left alone.

**Per-target-model image settings** *(4.1)*. Besides the checkpoint, each target model remembers its aspect/size (Create's *Aspect*), steps, CFG, sampler and scheduler (saved with **Save** in Settings while that model is selected). Switching target model restores them; values you never set fall back to the profile / global settings. They're stored in `profile_image_settings` and travel with Library sync.

**Upscale and hires from the Gallery** *(4.1)*. Right-click an image → *Upscale…*: choose the factor (1.5×), upscaler and denoise (0.3 keeps the picture and adds detail). Tick *Pure upscale* for a plain resize through Forge's Extras tab. ComfyUI does Pure upscale only. *Regenerate with hires* reruns the same prompt, seed and settings with hires fix on. Results land in the Gallery with the source image noted in their sidecar.

**Checkpoint follows the target model** *(4.0.1)*. Whatever checkpoint you pick (in Settings, Pose, Auto-refine or Inpaint & Regions) is remembered for the current **Target model**, and switching target model switches the checkpoint in every picker. Settings shows *Linked to: <profile>*; clear the box (**Backend default**) to unlink. With no link, Civitai-imported profiles are matched automatically against your backend's checkpoint list (file name, then name, e.g. *Nova Cross AM v3.0* → `novaCrossAM_v30.safetensors`), but only when exactly one checkpoint fits; otherwise the current one is kept. Links are stored in settings and travel with Library sync.

**Sampler and scheduler** *(4.0.1)*. Settings → Image generation has **Sampler** and **Scheduler** pickers next to Steps/CFG. Press ⟳ to load the lists from Forge/A1111 (`/sdapi/v1/samplers`, `/sdapi/v1/schedulers`) or ComfyUI (`KSampler`'s options), or type a name. **Profile default** keeps the model profile's own choice; anything else overrides it for every page. Forge gets the separate `scheduler` field; ComfyUI workflows get `{{sampler}}` / `{{scheduler}}`.

**Hires fix (Forge/A1111).** Tick **Hires fix** in Settings → Image generation and press **Save**. PromptMaker sends `enable_hr` with your scale, upscaler, hires steps and denoise (0.3–0.5 keeps the picture; 1.5× Latent with denoise 0.4 is a good start), and tells Forge Neo to reuse the same VAE and text encoders for the second pass.

**ADetailer (Forge, or ComfyUI with the Impact Pack)** *(6.5)*. With the [ADetailer](https://github.com/Bing-su/adetailer) extension in Forge, or [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) + [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) in ComfyUI (install both with ComfyUI Manager), tick **ADetailer** in Settings -> Image generation and press the reload button to load your detector models. Pick a **Preset** (*Face*, *Face + hands*, *Full body*) or set the passes yourself: pass 1 defaults to `face_yolov8s.pt` (denoise 0.4, confidence 0.3), and its optional prompt is used only for the detailed area (empty = the main prompt). Tick **Second pass** to add e.g. `hand_yolov8n.pt`. On ComfyUI each pass becomes an UltralyticsDetectorProvider + FaceDetailer after the VAE decode. The **ADetailer** tick in the top bar is the same switch. It applies to every image except Face Swap, and the Video maker's *ADetailer faces* tick uses the same passes. The controls are greyed out when the backend has no ADetailer / FaceDetailer.

**Freeing VRAM.** With Ollama as the AI provider, PromptMaker unloads every loaded Ollama model (`keep_alive: 0`) before each image. In Auto-refine the vision model reloads after each image, so each round takes a few seconds longer.

Set the backend, URL, workflow, checkpoint, steps and CFG in **Settings → Image generation**, then use the **🖼 Generate** buttons on Create, Builder, Image to Prompt, A/B Test and Gallery. Width and height come from the target model profile's aspect ratio. Images go to `data/gallery/` as PNG files, each with a `.json` sidecar holding the prompt, negative prompt, seed, profile and settings.

## Video maker

Tools → **Video maker** turns an idea or story into a short video on your own PC:

1. Write the idea (and optionally pick a song – its length is read automatically – and paste the lyrics, one line per scene; `[mm:ss]` timestamps are used when present). Press **🧠 Plan scenes with AI**.
2. Edit the scenes: prompt, motion, caption, seconds, camera move and who is in it; tick **Animate** for the scenes that should really move.
3. **🖼 Make stills** (Forge or ComfyUI, your current target model; optional ADetailer on Forge), **🎞 Animate ticked** (Wan2GP), **🎬 Build video** (ffmpeg) – or **▶ Run all**.

![Video maker](docs/screenshots/video_maker.png)

**Requirements**

- **ffmpeg** for the Ken Burns zooms, captions, crossfades and the final MP4 (found on PATH, in Pinokio's `ffmpeg-env` or Wan2GP's `ffmpeg_bins`; or set the path in the page's **Tools** card).
- **[Wan2GP](https://github.com/deepbeepmeep/Wan2GP)** (e.g. the Pinokio install at `C:\pinokio\api\wan.git\app` with its `venv`) – only for animated scenes. By default it runs headless with FastWan 5B image-to-video (1280×704, 121 frames ≈ 5 s, 3 steps – about 2 minutes per clip on an 8 GB GPU). Without it, every scene gets a slow zoom or pan.
- Before Wan2GP starts, PromptMaker frees the GPU: Forge unloads its checkpoint, ComfyUI unloads its models. An out-of-memory clip is retried once; the full Wan2GP log is kept in `data/videos/<name>/wan/<scene>/wan2gp.log` and the real error is shown on the page.

**Animation models & LoRA** *(6.0)*

- **Model presets**: the **Model** list in the Tools card is read from your own Wan2GP install. Each preset shows separately whether its definition exists, whether its files are on disk, and whether it has been tested. **FastWan 5B image-to-video stays the default** (1280×704, 3 steps, guidance 1, flow shift 3). Other presets keep their own resolution, steps, guidance and flow shift instead of copying FastWan's. When you switch models, settings that don't fit the new one are reset and an amber note says what changed.
- **Frames follow each scene's length** (its seconds × the model's frame rate, rounded to the frame counts the model accepts).
- **Optional creative LoRA**: pick one LoRA (or **None**) and a constant **Strength**. Choosing None never switches off an acceleration adapter that a model needs (such as FastWan's). The file's own metadata is checked against the selected model where it has any; a folder name is not treated as proof, and there is no guaranteed safe strength range.
- **Project defaults and per-scene overrides**: the Tools card sets the project's animation defaults. In the scene editor, tick **Override animation for this scene** to give one scene its own model, frames, steps, guidance or LoRA; other scenes keep inheriting the defaults. Each finished clip records the model, settings, adapters and still it used, so resuming or redoing later uses that recording instead of silently picking up changed defaults. Projects from 5.3 are upgraded on open and keep their stills and clips.
- **Offline preflight**: before Wan2GP starts, missing model files, missing LoRA files and incompatible choices (for example a model that can't take a start image) are named and the job stops. Jobs run with Wan2GP's `--offline` switch, so **nothing is downloaded, installed or upgraded**; a Wan2GP install whose own source doesn't support `--offline` is refused rather than run without it. On a failure or cancel, finished clips are kept and the page says what to do next.
- **Limits**: not every model fits in 8 GB of VRAM, and PromptMaker doesn't predict memory use. A file check is not a full guarantee that a job will run. Start/end frames, native continuation and camera-control models are not included yet. Verified on an 8 GB GPU with FastWan 5B.

**Characters & face lock**

Add characters on the page (or **↙ Import from Characters**) with a fixed description, a seed and optionally a reference face, and tick who is in each scene. The description is added to every still word for word, and the main character's seed is reused unless the scene sets its own.

With a reference face, the main character's face is locked with IP-Adapter Plus Face (the Face Swap setup). **Face lock only works with SDXL / Illustrious / Pony checkpoints** – with Anima, MOSS, FLUX, Qwen and other models the reference face is ignored and an amber warning says so; descriptions and seeds still apply. Only one face per scene is locked.

![Characters with the face lock warning](docs/screenshots/video_characters.png)

Projects live in `data/videos/<name>/` (with their stills, clips and character references) and resume where they stopped; **⟳ Redo still / Redo clip** remakes one scene.

## Backend auto-detect

**Start Forge / Start ComfyUI** *(6.5)*. Settings -> Image generation shows **▶ Start Forge** and **▶ Start ComfyUI** when PromptMaker finds their launchers (`webui-user.bat` for Forge, `run_nvidia_gpu.bat` for the ComfyUI portable build; other locations under **Launcher paths**). The backend opens in its own console window, and PromptMaker switches to it as soon as its API answers (up to 5 minutes; Forge needs `--api` in `COMMANDLINE_ARGS`). It won't start a second copy of something that's already running, and asks first when the other backend is running, since both together can run out of VRAM on an 8 GB card.

At startup PromptMaker checks in the background which image backend is running – Forge / A1111 at its URL or ports 7860–7862, ComfyUI at its URL or 8188 / 8000 / 8189 – and switches to it with a short notice, reusing the target model you last used with that backend. A running current backend is kept; when nothing runs, nothing changes. Turn it off or press **🔎 Detect now** in Settings → Image generation.

![Settings – auto-detect](docs/screenshots/settings_autodetect.png)

## Wallpaper mode

**Tools → Wallpaper.** Choose the screen, write (or **↙ Use Refine prompt**) a scene and press **🖼 Make wallpaper**. The plan line shows every step, e.g. `1280×720 → hires ×1.5 = 1920×1080 → 1920×1080`.

| Screen | SDXL / Illustrious / Pony / Anima | FLUX / Qwen / MOSS / HiDream |
|---|---|---|
| 1920×1080 | 1280×720, hires ×1.5 | 1280×720, hires ×1.5 |
| 2560×1440 | 1280×720, hires ×2 | 1280×720, hires ×2 |
| 3840×2160 | 1280×720, hires ×1.5, upscale ×2 | 1280×720, hires ×1.5, upscale ×2 |
| 2560×1080 | 1536×648, hires ×1.7, crop | 1632×688, hires ×1.6, crop |
| 3440×1440 | 1528×640, hires ×1.5, upscale ×1.55, crop | 1568×656, hires ×1.5, upscale ×1.5, crop |
| 1080×1920 | 720×1280, hires ×1.5 | 720×1280, hires ×1.5 |

- **Composition** keeps your desktop icons off the subject: *Subject on the right / left / centre* adds wording in your model's style – tags for SDXL (`wide shot, scenery, negative space, character on right side, empty left side`), a sentence for natural-language models, both for Anima.
- **Hires denoise** (0.35 by default) and the hires upscaler / steps from the inspector are used. **Final step**: on Forge, sizes over ×2 use Forge's upscaler (your hires upscaler if it's a model such as 4x-UltraSharp, else R-ESRGAN 4x+); ComfyUI and *Lanczos resize only* resize locally.
- Results are saved to `data/Wallpapers` (untick to skip) and can go to the Gallery. On Windows, **🖥 Set as desktop wallpaper** applies it straight away.

## MOSS Image on ComfyUI

*(5.2)* Choose **Settings → Image generation → Workflow → `moss_txt2img`**. Put the model in `models\diffusion_models` (e.g. `moss_image_sft_int8_convrot.safetensors` or a MOSS mix), `qwen3.5_9b_w4a8_gptq.safetensors` in `models\text_encoders` and `flux2-vae_small.safetensors` in `models\vae` (all from [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image)), and update ComfyUI. The model picker then lists your diffusion models; the text encoder and VAE are found automatically. Defaults: 25 steps, CFG 3.5, euler / simple, 1024×1024, negative `worst quality, bad anatomy, watermark, jpeg artifact`. **Skip layer guidance** is off by default because it can overblow anime styles; tick it for crisper photoreal. Hires fix and Wallpaper mode work as usual, and choosing a MOSS target model suggests this workflow.

## Face Swap setup

1. Download [ip-adapter-plus-face_sdxl_vit-h.safetensors](https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors) and put it in Forge's `models\ControlNet` folder (e.g. `C:\AI\sd-webui-forge-classic\models\ControlNet`), then restart Forge. On ComfyUI, install ComfyUI_IPAdapter_plus and its models.
2. Start Forge with `--api`. The first face generation is slower because Forge downloads the CLIP ViT-H image encoder itself.
3. In PromptMaker go to **Tools → Face Swap → ⟳ Check models**. It finds the model, shows download links and folders for anything missing, and warns about Forge settings that cause problems.
4. Use an **SDXL / Illustrious / Pony** checkpoint. Face features don't work with Anima, Flux or other non-SDXL models.

**8 GB graphics cards:** if Forge logs `Expected all tensors to be on the same device … cuda:0 … cpu` and the face is ignored, close Forge and set `set COMMANDLINE_ARGS=--api --disable-smart-memory` in `webui-user.bat` (if it still fails, try `--api --highvram`).

**Auto-mask models** download on first use into `data/models`, with progress in the status line: about 100 MB the first time you mask a photo, and about 175 MB more for the first anime image. If the status says *shape*, the download failed (or OpenCV / onnxruntime is missing) and a simpler head-shape mask is used instead.

**Tips for swapping into an image:** describe only the face, hair and the picture's style and lighting in the prompt (e.g. `photo of an adult woman, black hair with bangs, soft daylight, sharp focus`). If the face looks pasted on, lower Denoise to 0.6–0.7; if it doesn't look enough like the source, raise Weight to 0.85–0.9. If skin colour looks off, lower Colour strength; if you can still see an edge, switch Seam blend to Poisson.

## Civitai Model browser

**Library → Model browser** searches Civitai without leaving PromptMaker. Type a search, pick a type, base model, sort and period, and click a card to see its versions, files, description, trained words and the creator's settings.

- **NSFW is off by default.** When it's off, PromptMaker asks Civitai for SFW models only and never loads a preview rated above PG. Tick **Show NSFW** to change that.
- **⬇ Download** saves the chosen file straight into the right folder for your backend, such as Forge `models\Stable-diffusion` / `models\Lora` or ComfyUI `checkpoints` / `diffusion_models` / `loras` / `vae`. MOSS, Anima, FLUX and Qwen files that hold only the diffusion model go to ComfyUI `diffusion_models`. You can pick another folder.
- Downloads run in the background and can be cancelled. Download again to resume from where it stopped. Every file is checked against Civitai's SHA256.
- Many downloads need you to be signed in: add a Civitai API key in **Settings → Civitai** (civitai.com/user/account → API Keys). It is stored in your OS keyring when one is available. The same card has the host (civitai.com or civitai.red) and your Forge / ComfyUI folders.
- After a download, **Refresh models** reloads your backend's model list and **Create model profile** makes a `civitai_<versionId>` profile with the creator's settings, the right sampler / scheduler and, for MOSS, the `moss_txt2img` workflow.

## Civitai checkpoint profiles

Many checkpoints and LoRAs on Civitai list their own quality tags, negative prompt and settings. In **🎯 Model profiles**, click **🌐 Import from Civitai…** and paste:

- a model link from civitai.com, civitai.red or another civitai.* domain (they share the same IDs and API);
- a model ID (`2087823`), a version ID (`v3338156`), or an AIR (`urn:air:…:civitai:2087823@3338156`).

PromptMaker uses Civitai's public REST API: `/api/v1/model-versions/{id}`, `/api/v1/models/{id}` and `/api/v1/images?modelVersionId=…`.

1. **Parse the description.** It reads the creator's *positive / negative prompts*, *steps*, *CFG*, *sampler*, *clip skip* and *resolution* from the model and version description.
2. **Mine sample images.** It looks at the generation data on the most-reacted sample images and keeps tags that appear in at least 40% of them. Settings come from the most common or median values. This is used to fill anything the description doesn't give.
3. **Review.** You see everything before saving: name, which built-in profile to inherit from (picked from the base model, e.g. Anima, Illustrious, Pony or SDXL), prefix, negative, steps, CFG, sampler, clip skip, resolution and trained words.
4. **Save.** A new profile is created with `"inherits": "<base>"`, so format, weighting, length and resolutions come from the base and only the checkpoint-specific fields are overridden. The source URL and version are stored under `"civitai"`.

The profile is then used everywhere: the Builder prefix and negative prompt, the Create/Refine AI system prompt, Score model-fit, and image generation. Generation uses the profile's steps, CFG, sampler/scheduler and clip skip (clip skip applies to Forge/A1111 only). LoRA trigger words (`trainedWords`) are stored and added to the prefix. **⟳ Refresh from Civitai** fetches the latest data again for the same profile.

An **API key is optional.** Add one in Settings → Civitai if a model is NSFW or gated; it's stored in the OS keyring. Responses are cached for 24 h in `data/cache/civitai/`, requests are spaced out, and HTTP 429 (rate limit) is retried politely.

*Caveats:* Civitai's API and description formats aren't guaranteed. Descriptions are free-form HTML, so always check the review screen. Many sample images don't include generation data when fetched without a key. Respect each model's licence and [Civitai's Terms of Service](https://civitai.com/content/tos). PromptMaker only reads public metadata and never downloads model files.

## Community packs & profiles

The **🌐 Community** page reads [`community/index.json`](community/index.json) from this repository. Install, update and uninstall take one click, and each file's SHA-256 is checked before it's installed. Community packs are saved in `data/packs/`, and community profiles are merged into `data/profiles.json`. You can point the app at another index (`https://` or `file://`) in Settings. To share your own pack or profile, see [CONTRIBUTING.md](CONTRIBUTING.md#sharing-a-pack-or-profile-community-gallery).

## Model profiles

| Profile | Format | Negative prompt | Weighting | Length |
|---|---|---|---|---|
| Generic (any model) | natural | optional | none | 15–75 words |
| FLUX.2 (pro / max / dev / klein) | natural | unsupported | none | 30–200 words |
| FLUX.2 – JSON structured | json | unsupported | none | 20–300 words |
| FLUX.1 [dev / schnell / pro] | natural | unsupported | none | 30–150 words |
| FLUX.1 Kontext (image editing) | natural | unsupported | none | 8–80 words |
| Stable Diffusion XL 1.0 | tags | supported | parens | 10–75 words |
| Stable Diffusion 3.5 (Large / Medium) | natural | supported | none | 20–200 words |
| Pony Diffusion V6 XL (tags) | tags | supported | parens | 10–75 words |
| Illustrious XL / NoobAI (Danbooru tags) | tags | supported | parens | 10–75 words |
| Anima (CircleStone Labs, anime) | hybrid | supported | parens | 25–180 words |
| MOSS-Image (OpenMOSS, 5B) | natural | supported | none | 30–400 words |
| Qwen-Image (incl. 2512) | natural | limited | none | 30–250 words |
| HiDream-I1 (Full / Dev / Fast) | natural | limited | none | 20–150 words |
| Midjourney V7 | natural | param_no | mj | 10–60 words |
| OpenAI GPT Image 2 / 2.5 | natural | unsupported | none | 20–250 words |
| Google Imagen 4 (Fast / Standard / Ultra) | natural | unsupported | none | 15–200 words |

More profiles can be added from the **🌐 Community** page (e.g. *SDXL-Lightning*) or imported from **Civitai** (checkpoint-specific profiles that inherit from one of the above).

Each profile lists its sources in the app (**🎯 Model profiles**). Profiles live in `data/profiles.json`, which is created on first run. You can edit them there or in the app, or add your own. New built-in profiles are merged in automatically on update.

**Fields:** `format` natural/tags/hybrid/json · `negative` supported/optional/limited/unsupported/param_no · `weighting` parens/mj/none · `quality_prefix` · `negative_default` · `length` [min, max] · `resolutions` {aspect: "WxH"} · `settings` · `param_style` midjourney/settings/none · `ai_guidance` (sent to the LLM) · `tips` · `sources` · `inherits` (id of a parent profile; only the fields you set are overridden) · `gen` (steps / cfg / sampler / scheduler / clip_skip used when generating) · `civitai` (source model, version and trained words).

## Preset packs

Packs are JSON files in `packs/`:
```json
{"name": "My pack", "description": "…", "version": "1.0",
 "categories": {"Style": {"Group name": ["item 1", "item 2"]}}}
```
Use **📦 Packs → Import / Export** to share them. Packs in `packs/` are the bundled, read-only ones. Packs you import and chips you add yourself are saved in `data/packs/` (`custom.json`). If you're upgrading from 1.x, an old `packs/custom.json` is moved there automatically.

## LoRA training (optional)

PromptMaker does not train anything itself and ships no training code. **LoRA training → ⬇ Install trainer…** shows the exact commands and asks before running them:

1. `git clone -b sd3 https://github.com/kohya-ss/sd-scripts tools/sd-scripts` (inside the PromptMaker folder)
2. `python -m venv tools/sd-scripts/venv`, then PyTorch (CUDA 12.4 wheels), `requirements.txt`, `bitsandbytes` and `xformers` into that venv – about 6 GB.

You need git and an NVIDIA GPU (8 GB works with the *8 GB* preset; 16 GB+ recommended). You can also point the *sd-scripts* field at an existing install. A run writes its dataset (`img/<repeats>_<trigger>/` with one `.txt` caption per image) and output under `data/training/<name>/`, then copies `<name>.safetensors` to `<Forge>/models/Lora`. Keep Forge idle while training – both need the GPU.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+K | Command palette: pages, actions (insert character, new storyboard, …) or an idea to write a prompt for |
| Ctrl+Enter | Create (Create page) / send (Refine chat) |
| Ctrl+Shift+C | Copy the Builder prompt |
| Ctrl+T | Toggle dark/light theme |

## Your data

History, templates, favourites, versions and settings are stored in `data/promptmaker.db` (SQLite). Profiles, your packs, the gallery and any plain-text key file also live in the data folder.

- **Portable mode** (the default) keeps everything in `data/` next to the app, so you can copy the whole folder anywhere.
- Turn portable mode off in **Settings** to use `%APPDATA%\PromptMaker` on Windows (`~/.local/share/PromptMaker` or `~/Library/Application Support/PromptMaker` elsewhere). Your data is copied over the first time and the change takes effect after a restart. The choice is remembered by a `use_appdata.flag` file next to the app.

Wildcard files live in `data/wildcards/` (`.txt`, one entry per line, `#` for comments; or `.yaml`). Subfolders become `__folder/name__`. You can also drop sd-dynamic-prompts packs straight in.

**Library sync** (*☁ Library sync* page): **Export .zip** keeps wildcards as normal files, and **.json** is a single file. Machine-specific settings (folder paths, the gist ID, setup results) and anything that looks like a secret are left out, and API keys are never read at all, because they live in the keyring or `secrets.json`. For gist sync, create a token at <https://github.com/settings/tokens>: a classic token with the **gist** scope, or a fine-grained one with *Gists: read & write*. Paste it and press **Save token**; it's stored like your API keys. The first push creates a **private** (secret) gist. On another computer, paste the same token and the gist ID, then press **Sync**. Sync compares last-modified times with the last successful sync. If only one side changed, it pushes or pulls. If both did, you choose **Keep this computer**, **Keep the gist** or **Merge both**.

The `data/` folder is git-ignored.

## Updates & privacy

When it starts, PromptMaker can ask the GitHub releases API whether a newer version exists. Nothing about you is sent, and you can switch this off in Settings. Apart from that, the app only goes online for the community index, Civitai imports you start, and any providers or backends you configure.

## Languages

English, Español and Deutsch. Choose one in **Settings → Language** and restart. The Spanish and German translations are **machine-translated**, and corrections are very welcome. Translations live in `promptmaker/i18n/<code>.json`, and any string without a translation falls back to English.

## Troubleshooting

**ComfyUI: no live preview, only "Step n/N"**
ComfyUI only sends preview images when it is started with a preview method. Open `run_nvidia_gpu.bat` in your ComfyUI portable folder and add `--preview-method auto` to the end of the `python … main.py` line (e.g. `.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --preview-method auto`), then restart ComfyUI. `auto` uses the TAESD decoders in `models/vae_approx` when present.

To stop ComfyUI opening a browser tab on start, also add `--disable-auto-launch` to that line. For Forge, turn off *Settings → System → Automatically open webui in browser on startup* and make sure `COMMANDLINE_ARGS` in `webui-user.bat` has no `--autolaunch`.

**Forge / A1111: "HTTP 404 from /sdapi/v1/sd-models" or "API not enabled"**
The WebUI is running, but it was started without its API. PromptMaker detects this and shows the fix:
1. Close the Forge console window.
2. Open `webui-user.bat` in the Forge folder (e.g. `C:\AI\sd-webui-forge-classic\webui-user.bat`).
3. Change `set COMMANDLINE_ARGS=` to `set COMMANDLINE_ARGS=--api`, keeping any other flags after it, e.g. `--api --xformers`.
4. Start Forge again and click **Settings → Image generation → Test connection**. It should report e.g. *Connected · Forge Neo 2.31 · N checkpoint(s)*.

![Forge API dialog](docs/screenshots/forge_api.png)

**Grey/blank images after switching between Anima and SDXL**
Anima needs extra modules in Forge's **VAE / Text Encoder** box (`qwen_image_vae` + `qwen_3_06b_base`). If they stay selected when you switch to an SDXL/Illustrious/Pony/SD1.5 checkpoint, Forge outputs flat grey images. Since 4.0.1 PromptMaker sets the right modules with every Forge image automatically (none for SD-family checkpoints, the Qwen VAE + text encoder for Anima). A profile can override this with `"forge_modules": ["file1.safetensors", ...]` in `data/profiles.json`. Manual fix on older versions: clear Forge's **VAE / Text Encoder** box (or restart Forge).

**Ollama: `unknown model architecture: 'mllama'` / "error loading model" (HTTP 500)**
`llama3.2-vision` (architecture *mllama*) isn't supported on **Ollama 0.30+**, because the llama.cpp engine has no mllama support ([ollama/ollama#16547](https://github.com/ollama/ollama/issues/16547)). Re-pulling won't help. Use another vision model, e.g. `ollama pull qwen2.5vl` (or `qwen3-vl`, `gemma3`). PromptMaker marks such models in the picker and offers a one-click switch.

![Model error dialog](docs/screenshots/model_error.png)

**Face Swap: the face is ignored / tensor device error in Forge.** See the 8 GB tip in [Face Swap setup](#face-swap-setup) (`--disable-smart-memory`). Also check you use an SDXL-family checkpoint and that ⟳ Check models finds the face model.

**Pose / ControlNet with Anima: errors or the pose is ignored**
Anima isn't SD or SDXL based, so ordinary SD 1.5/SDXL OpenPose ControlNets don't work with it. Use an Anima **ControlNet-LLLite** model: download `anima-lllite-pose-1.safetensors` from [kohya-ss/Anima-LLLite](https://huggingface.co/kohya-ss/Anima-LLLite), put it in your Forge `models/ControlNet` folder (e.g. `C:\AI\sd-webui-forge-classic\models\ControlNet`) and restart Forge. It needs a **Forge Neo** build with Anima LLLite support (added May 2026); if the model doesn't appear in the Pose page's ControlNet dropdown, update Forge. It's a fairly soft pose guide. If the dropdown is empty, no ControlNet models are installed and PromptMaker won't send a pose.

**Forge uses the wrong checkpoint**
If the Checkpoint box is empty, PromptMaker doesn't name one and Forge uses whatever it last loaded. Pick a checkpoint in **Settings → Image generation → Checkpoint**, or on the **Pose** or **Auto-refine** page (⟳ reloads the list). It's one shared setting, so changing it in any of the three changes it everywhere.

**Ollama isn't reachable.** Start Ollama (the Create page has a **▶ Start Ollama** button) or check the URL in **Settings → AI provider**. The **⚡ Offline build** works without any AI.

**Civitai: "refused access (HTTP 401/403)" or missing sample-image data**
The model is NSFW or gated, or its images hide their generation data from anonymous requests. Add a Civitai API key (create one at civitai.com → *User account → API Keys*) in **Settings → Civitai**. It's stored in your OS keyring. Responses are cached for 24 h; use the ⟳ button in the import dialog to fetch again.

**Community page shows an error.** Check **Settings → Community gallery → Index URL** (the default is `community/index.json` on `main`). Downloads whose SHA-256 doesn't match are refused on purpose.

**API keys saved "in plain text".** No OS keyring was found. Run `install.bat` / `install.sh` again to install `keyring`, or keep `data/secrets.json` private.

**Regions: "Regional prompts on Forge need the free Forge Couple extension".** Forge (including Forge Neo) has no regional prompting built in. Install *sd-forge-couple* (see [Image generation](#image-generation-optional)), restart Forge and press **🔎 Check support**. If Forge Couple reports *"Image must contain weights on all pixels"*, raise **Base weight** above 0. Forge Couple and sd-dynamic-prompts can clash, but PromptMaker expands wildcards itself, so you can disable Dynamic Prompts.

**Inpaint changes the whole picture / nothing changes.** Lower **Denoise** (0.4–0.6 keeps more of the original) and use *Only masked* for small areas. For big changes, raise it to 0.8–1.0 and set *Masked content* to *latent noise*. On ComfyUI, inpainting works best with an inpaint checkpoint, though normal ones work at lower denoise.

**Wildcard shows up as `__name__` in the result.** There's no file with that name. The Wildcards page lists unknown names under **Try it**. Names are case-insensitive and folders use `/` (`__people/job__`).

**Gist sync: 401 / 403 / 404.** 401 means the token is wrong or expired. 403 means it lacks the *gist* scope (or *Gists: read & write* on a fine-grained token). 404 means the gist ID is wrong, or the token belongs to another account. Clear the Gist box to create a new one on the next push.

**Regions: only one character appears.** Keep **Repeat main prompt in every region** ticked, put the count (`2girls`) in the main prompt, use a wide size from the **Size** picker, make the boxes side by side, and give each character clearly different details (hair colour, outfit). Delete any box that covers the whole canvas.

**Hires fix: `TypeError: 'NoneType' object is not iterable` in Forge's `modules_change`.** This came from PromptMaker versions before 4.0.0's final build; update. 4.0.0 sends `hr_additional_modules`, which Forge Neo needs.

**Nothing happens on Linux, or Qt errors.** Install the Qt runtime libraries (`libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3` on Debian/Ubuntu).

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip
python -m pytest -q
python -m pyflakes promptmaker tests
QT_QPA_PLATFORM=offscreen python main.py --smoke-test   # headless UI smoke test
```

Project layout: `promptmaker/app.py` (UI), `builder.py` (prompt formatting), `scoring.py`, `providers.py` (LLM providers), `ollama.py`, `imagegen.py` (ComfyUI / A1111), `gallery.py`, `community.py`, `abtest.py`, `keystore.py`, `paths.py`, `updates.py`, `i18n.py`, `library.py` (packs), `civitai.py` / `civitai_dialog.py`, `firstrun.py` (setup wizard), `autorefine.py`, `loras.py`, `presets.py`, `pose.py` / `posecanvas.py`, `faceswap.py` / `faceswapui.py` (Face Swap), `faceseg.py` (auto-mask), `faceblend.py` (Auto-blend), `profiles.py`, `storage.py`, `theme.py`, `widgets.py`. All network code is tested against local mock servers (`tests/test_v2.py`, `tests/test_civitai.py`, `tests/test_v3.py`), so the tests don't need Ollama, ComfyUI or an internet connection.

## Contributing

Contributions are welcome, especially new preset packs and model profiles. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Sarah Gilford
