# ✦ PromptMaker

**A local desktop studio for writing AI image prompts.** You can describe an idea in plain words, build a prompt from 800 presets, refine it in a chat with a local LLM, or score it. Each prompt is formatted for the image model you're targeting, such as FLUX.2, SDXL, Pony, Illustrious, Anima, MOSS-Image, Qwen-Image, Midjourney V7, GPT Image and more.

Everything runs on your own computer by default. The AI features are optional and work with [Ollama](https://ollama.com), LM Studio, llama.cpp, KoboldCpp, vLLM or any OpenAI-compatible server, plus optional cloud providers. Version 2 can also generate images through **ComfyUI** or **Forge / AUTOMATIC1111**, turn images back into prompts, compare prompts A/B, and import checkpoint-specific guidance from **Civitai**.

**Latest release:** [v2.0.0](https://github.com/Kisahime/promptmaker/releases/tag/v2.0.0) · [Changelog](CHANGELOG.md)

![Create page](docs/screenshots/create.png)

## Features

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
- **🩹 Friendly errors** *(2.0)*:
  - Models a provider can't load (e.g. `llama3.2-vision` on Ollama 0.30+) get a plain explanation, a one-click switch to another installed model, and a copyable `ollama pull` command. Unsupported or failed models are marked in the model pickers.
  - When Forge/A1111's API is off, the app shows the exact `--api` fix, and Test connection reports the WebUI variant and version.
- **Safe by design:** destructive buttons (Clear all, Delete, Uninstall) confirm **in place**: a red *Confirm (4s)* button with a countdown. Toasts appear top-right and never block clicks.
- A polished dark/light theme and a **Ctrl+K** quick bar from anywhere.

## Screenshots

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
| **Preset packs** | **Light theme** |
| ![Preset packs](docs/screenshots/packs.png) | ![Light theme](docs/screenshots/builder_light.png) |

**Civitai import (review before saving)**

![Civitai import](docs/screenshots/civitai.png)

*The images in the Gallery, A/B and Image to Prompt screenshots are abstract placeholders, not real model output. All screenshots use demo data and are regenerated with `QT_QPA_PLATFORM=offscreen python tools/screenshots.py`.*

## Install

You need **Python 3.10+** ([python.org](https://www.python.org/downloads/); on Windows, tick *"Add python.exe to PATH"*).

**Windows**
1. Download or clone this repo.
2. Double-click **`install.bat`**. It checks Python, creates a `.venv`, installs PySide6 and keyring, offers to make a desktop shortcut, and checks for Ollama.
3. Start the app with **`run.bat`** or the desktop shortcut. A short guided tour runs the first time.

**Upgrading from 1.x:** copy or `git pull` the new version over the old folder (your `data/` is kept), then run `install.bat` again to install the new dependencies.

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

The `data/` folder is git-ignored.

## Updates & privacy

When it starts, PromptMaker can ask the GitHub releases API whether a newer version exists. Nothing about you is sent, and you can switch this off in Settings. Apart from that, the app only goes online for the community index, Civitai imports you start, and any providers or backends you configure.

## Languages

English, Español and Deutsch. Choose one in **Settings → Language** and restart. The Spanish and German translations are **machine-translated**, and corrections are very welcome. Translations live in `promptmaker/i18n/<code>.json`, and any string without a translation falls back to English.

## Troubleshooting

**Forge / A1111: "HTTP 404 from /sdapi/v1/sd-models" or "API not enabled"**
The WebUI is running, but it was started without its API. PromptMaker detects this and shows the fix:
1. Close the Forge console window.
2. Open `webui-user.bat` in the Forge folder (e.g. `C:\AI\sd-webui-forge-classic\webui-user.bat`).
3. Change `set COMMANDLINE_ARGS=` to `set COMMANDLINE_ARGS=--api`, keeping any other flags after it, e.g. `--api --xformers`.
4. Start Forge again and click **Settings → Image generation → Test connection**. It should report e.g. *Connected · Forge Neo 2.31 · N checkpoint(s)*.

![Forge API dialog](docs/screenshots/forge_api.png)

**Ollama: `unknown model architecture: 'mllama'` / "error loading model" (HTTP 500)**
`llama3.2-vision` (architecture *mllama*) isn't supported on **Ollama 0.30+**, because the llama.cpp engine has no mllama support ([ollama/ollama#16547](https://github.com/ollama/ollama/issues/16547)). Re-pulling won't help. Use another vision model, e.g. `ollama pull qwen2.5vl` (or `qwen3-vl`, `gemma3`). PromptMaker marks such models in the picker and offers a one-click switch.

![Model error dialog](docs/screenshots/model_error.png)

**Ollama isn't reachable.** Start Ollama (the Create page has a **▶ Start Ollama** button) or check the URL in **Settings → AI provider**. The **⚡ Offline build** works without any AI.

**Civitai: "refused access (HTTP 401/403)" or missing sample-image data**
The model is NSFW or gated, or its images hide their generation data from anonymous requests. Add a Civitai API key (create one at civitai.com → *User account → API Keys*) in **Settings → Civitai**. It's stored in your OS keyring. Responses are cached for 24 h; use the ⟳ button in the import dialog to fetch again.

**Community page shows an error.** Check **Settings → Community gallery → Index URL** (the default is `community/index.json` on `main`). Downloads whose SHA-256 doesn't match are refused on purpose.

**API keys saved "in plain text".** No OS keyring was found. Run `install.bat` / `install.sh` again to install `keyring`, or keep `data/secrets.json` private.

**Nothing happens on Linux, or Qt errors.** Install the Qt runtime libraries (`libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3` on Debian/Ubuntu).

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip
python -m pytest -q
python -m pyflakes promptmaker tests
QT_QPA_PLATFORM=offscreen python main.py --smoke-test   # headless UI smoke test
```

Project layout: `promptmaker/app.py` (UI), `builder.py` (prompt formatting), `scoring.py`, `providers.py` (LLM providers), `ollama.py`, `imagegen.py` (ComfyUI / A1111), `gallery.py`, `community.py`, `abtest.py`, `keystore.py`, `paths.py`, `updates.py`, `i18n.py`, `library.py` (packs), `civitai.py` / `civitai_dialog.py`, `profiles.py`, `storage.py`, `theme.py`, `widgets.py`. All network code is tested against local mock servers (`tests/test_v2.py`, `tests/test_civitai.py`), so the tests don't need Ollama, ComfyUI or an internet connection.

## Contributing

Contributions are welcome, especially new preset packs and model profiles. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Sarah Gilford
