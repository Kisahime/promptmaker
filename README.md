<p align="center"><img src="promptmaker/assets/icon_256.png" width="96" alt="PromptMaker icon"></p>

# PromptMaker

**A local desktop studio for writing AI image prompts.** You can describe an idea in plain words, build a prompt from 800 presets, refine it in a chat with a local LLM, or score it. Each prompt is formatted for the image model you're targeting, such as FLUX.2, SDXL, Pony, Illustrious, Anima, MOSS-Image, Qwen-Image, Midjourney V7, GPT Image and more.

Everything runs on your own computer by default. The AI features are optional and work with [Ollama](https://ollama.com), LM Studio, llama.cpp, KoboldCpp, vLLM or any OpenAI-compatible server, plus optional cloud providers. Version 4 adds wildcards and dynamic prompts, inpainting and regional prompts, library export/import with optional private GitHub gist sync, and prompt writing for video models (Wan, LTX-Video, HunyuanVideo). Version 3 added a first-run setup wizard, an automatic generate → check → refine loop, a LoRA manager, reusable characters and styles, and a pose sketcher with ControlNet. It can also generate images through **ComfyUI** or **Forge / AUTOMATIC1111**, turn images back into prompts, compare prompts A/B, and import checkpoint-specific guidance from **Civitai**.

**Latest release:** [v4.0.0](https://github.com/Kisahime/promptmaker/releases/tag/v4.0.0) · [Changelog](CHANGELOG.md)

![Create page](docs/screenshots/create.png)

## Features

- **🏠 Home** *(4.1)*: a dashboard with your target model and linked checkpoint, Forge / Ollama status, recent images and quick-start buttons.
- **🗂 Gallery** *(4.1)*: justified rows that keep aspect ratios, hover preview, full-screen viewer (←/→, Esc), and right-click actions: *Inpaint this*, *Use as reference*, *Regenerate with hires*, *Upscale…*. Drag a thumbnail onto the inpaint canvas.
- **⤢ Upscale** *(4.1)*: Forge img2img at 1.5× with denoise 0.3 (same prompt and seed), or *Pure upscale* via Forge Extras / ComfyUI `ImageScaleBy`.
- **Queue & status** *(4.1)*: the sidebar dot shows *Forge · active checkpoint* or *Offline* (click for settings); ☰ opens the queue to reorder or cancel jobs. Forge and ComfyUI show a live preview while they generate (ComfyUI: start it with `--preview-method auto`).
- **Look & feel** *(4.1)*: accent colours (purple, teal, pink, orange) in Settings → General, a collapsible icon-only sidebar («), and short page fades.
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
- **🧭 Setup wizard** *(3.0)*: on first launch (and any time from the sidebar or Settings) it checks whether Ollama is installed and running, lists your models, and downloads a recommended text model (`llama3.2`) and vision model (`qwen2.5vl`) with a progress bar. It also looks for Forge/A1111 (and tells you if `--api` is missing) and ComfyUI on their default ports, and saves what it finds.
- **🔄 Auto-refine** *(3.0)*: generate an image with Forge or ComfyUI, let a vision model score it against your idea (0–100, with what's missing or wrong), have the local AI rewrite the prompt, and repeat for N iterations or until a target score. Every iteration is shown with its image and review. Stop at any time and **Keep best**.
- **🧩 LoRAs** *(3.0)*: scans your models folder (Forge layout by default: `models\Lora`, `models\LyCORIS`, `embeddings`), hashes each file (SHA256 / AutoV2) and looks it up on Civitai for its name, trigger words, base model and preview. Results are cached. Filter by compatibility with the target model profile and insert `<lora:name:weight>` plus trigger words in one click.
- **👤 Presets** *(3.0)*: save **characters** (name, appearance tags, outfit, optional LoRA and weight, reference image) and **styles** (tags plus extra negative). Tick several to combine them in any prompt, and Batch can keep them fixed on every variation so a character stays consistent.
- **🧍 Pose** *(3.0)*: a canvas with draggable OpenPose-style skeletons (8 starter poses) and boxes for other subjects. It turns the sketch into composition tags (framing, pose, facing, positions) in the target model's style, exports an OpenPose PNG, and can generate with **ControlNet** via Forge's `alwayson_scripts` or by adding a ControlNet node to your ComfyUI workflow. Pick the ControlNet model from a dropdown filled from Forge; the page warns if it doesn't match your checkpoint (Anima needs an Anima ControlNet-LLLite model) and tells you whether the pose was actually applied.
- **🗂 Checkpoint picker** *(3.0)*: choose the Forge/ComfyUI checkpoint in Settings, on the Pose page or on the Auto-refine page. All three are the same setting.
- **🎲 Wildcards** *(4.0)*: write `__hair__` to pick a random line from `wildcards/hair.txt`, `{a|b|c}` to pick one option, `{2::a|b}` for weights, `{2$$a|b|c}` or `{1-3$$ and $$a|b|c}` to pick several. Folders (`__people/job__`), globs (`__places/*__`), YAML packs and nesting all work, using the same syntax as **sd-dynamic-prompts**. Results are seeded, so the same seed always gives the same prompt. Preview one expansion or a batch of N different variations, keep your ticked characters and styles fixed while everything else changes, and queue one image per variation. The page also creates, edits and deletes wildcard files, imports a folder or a Civitai zip pack (including zips inside zips), and has the local AI **write a new list** from a description such as "50 fantasy locations". Wildcards in prompts sent to Forge or ComfyUI are expanded with the image's seed, wherever the prompt comes from.
- **🖌 Inpaint & Regions** *(4.0)*: open an image (or take the last generated one), paint a mask and send it to **img2img inpaint**, with denoise, mask blur, *whole picture / only masked* and padding. Or draw boxes that each get their own prompt (**regional prompting**). ComfyUI needs nothing extra (`ConditioningSetArea` + `ConditioningCombine`). Forge has no built-in regional prompting, so PromptMaker uses the free **Forge Couple** extension when it's installed. If it isn't, the page says which extension to install, and you can send everything as one prompt with position words instead. The page uses the same checkpoint picker as Settings, Pose and Auto-refine.
- **🎬 Video** *(4.0)*: prompt writing for **Wan 2.2 / 2.1**, **LTX-Video** and **HunyuanVideo**. Fill in the subject, action and scene, and pick a camera move (14 presets: push in, orbit, tracking, FPV drone …), a motion preset, the shot size, lighting and style. The duration shows the frame count each model accepts (4n+1 or 8n+1 at its fps). **Build** writes the prompt offline in the structure that model prefers. **Write with AI** has your local LLM write it to the model's own prompting guide. You also get a word-count/camera check, the model's default negative prompt (where it has one), and saved video prompts. PromptMaker doesn't render video.
- **☁ Library sync** *(4.0)*: export everything (history, favourites, templates, versions, characters, styles, video prompts, LoRA metadata, wildcards, model profiles and settings) as one `.zip` or `.json`, and import it with **merge** or **replace**. When the same name has different content you choose *keep mine*, *take theirs* or *keep both*. Optional **private GitHub gist** sync with your own token (kept in the OS keyring) can push, pull or sync, deciding by last-modified time and asking you on a conflict. **API keys and tokens are never exported.**
- **🔍 Hires fix** *(4.0)*: switch on Forge/A1111's hires fix in **Settings → Image generation**, with the upscale factor, upscaler (loaded from your Forge), hires steps and denoise. It applies to every image PromptMaker generates (except inpaint).
- **🧹 Frees VRAM for images** *(4.0)*: right before each image goes to Forge or ComfyUI, PromptMaker tells Ollama to unload its text and vision models so the image model gets the GPU memory. On by default; you can turn it off in Settings → Image generation.
- **📐 Size picker** *(4.0)*: Auto-refine and Inpaint & Regions have their own image-size choice (square, wide, landscape, portrait, tall, SD1.5). *Model default* uses the profile's aspect ratio.
- **🎨 App icon** *(3.0)*: PromptMaker has its own icon on the window, taskbar and desktop shortcut.
- **🩹 Friendly errors** *(2.0)*:
  - Models a provider can't load (e.g. `llama3.2-vision` on Ollama 0.30+) get a plain explanation, a one-click switch to another installed model, and a copyable `ollama pull` command. Unsupported or failed models are marked in the model pickers.
  - When Forge/A1111's API is off, the app shows the exact `--api` fix, and Test connection reports the WebUI variant and version.
- **Safe by design:** destructive buttons (Clear all, Delete, Uninstall) confirm **in place**: a red *Confirm (4s)* button with a countdown. Toasts appear top-right and never block clicks.
- Four themes – sleek Graphite dark/light (default) plus cute Pastel and Pastel dusk – with accent colours (Ctrl+T toggles light/dark) and a **Ctrl+K** quick bar from anywhere.

## Screenshots

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

**Upgrading from 2.x (or 1.x):** copy or `git pull` the new version over the old folder (your `data/` is kept), then run `install.bat` again. That installs any new dependencies and recreates the desktop shortcut with the new icon. Your database is upgraded automatically the first time 3.0 starts (schema v3 adds the `characters` and `styles` tables); history, favourites, templates and settings are kept. Making a copy of `data/` first doesn't hurt.

**macOS / Linux** (should work, but is less tested)
```bash
./install.sh
./run.sh
```

There's no installer package and nothing system-wide. Everything stays in the folder, and you uninstall by deleting it.

## AI providers (optional)

Choose a provider in **⚙ Settings → AI provider**, then click **Test connection** and **Use this provider**. The model list in the sidebar comes from that provider.

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

**Freeing VRAM.** With Ollama as the AI provider, PromptMaker unloads every loaded Ollama model (`keep_alive: 0`) before each image. In Auto-refine the vision model reloads after each image, so each round takes a few seconds longer.

Set the backend, URL, workflow, checkpoint, steps and CFG in **Settings → Image generation**, then use the **🖼 Generate** buttons on Create, Builder, Image to Prompt, A/B Test and Gallery. Width and height come from the target model profile's aspect ratio. Images go to `data/gallery/` as PNG files, each with a `.json` sidecar holding the prompt, negative prompt, seed, profile and settings.

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

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+K | Quick idea bar (from anywhere) |
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

Project layout: `promptmaker/app.py` (UI), `builder.py` (prompt formatting), `scoring.py`, `providers.py` (LLM providers), `ollama.py`, `imagegen.py` (ComfyUI / A1111), `gallery.py`, `community.py`, `abtest.py`, `keystore.py`, `paths.py`, `updates.py`, `i18n.py`, `library.py` (packs), `civitai.py` / `civitai_dialog.py`, `firstrun.py` (setup wizard), `autorefine.py`, `loras.py`, `presets.py`, `pose.py` / `posecanvas.py`, `profiles.py`, `storage.py`, `theme.py`, `widgets.py`. All network code is tested against local mock servers (`tests/test_v2.py`, `tests/test_civitai.py`, `tests/test_v3.py`), so the tests don't need Ollama, ComfyUI or an internet connection.

## Contributing

Contributions are welcome, especially new preset packs and model profiles. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Sarah Gilford
