# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [4.0.0] – 2026-10-29
### Added
- **Wildcards** page (`promptmaker/wildcards.py`): sd-dynamic-prompts-compatible syntax. `__name__` (`.txt` one entry per line, sub-folders, globs such as `__places/*__`, and `.yaml` packs flattened to `__file/key__` and `__key__`), `{a|b|c}`, weights `{2::a|b}`, multi-pick `{2$$a|b|c}`, ranges and custom separators `{1-3$$ and $$a|b}`, and nested and recursive expansion with a loop guard. Seeded with `random.Random(seed)`, so results are reproducible. Preview, a batch of N unique variations, unknown-wildcard warnings, "Keep ticked characters & styles", and one image queued per variation. The manager creates, edits and deletes files, and imports a folder, a single file or a Civitai `.zip` (handling a `wildcards/` prefix, zips inside zips, and `__MACOSX` junk) with keep / overwrite / keep-both. **✨ Generate** has Ollama (or any provider) write a list from a description.
- Wildcards are expanded in `make_job()` with the image seed, so every page (Generate, Batch, Pose, Auto-refine, Inpaint …) supports them. This can be switched off. A lone `{tag}` is never touched.
- **Inpaint & Regions** page (`promptmaker/regions.py`, `promptmaker/inpaintcanvas.py`): a mask brush, eraser, invert, clear, "mask the selected region", open an image or take the last generated one, or a blank canvas at the profile size. Forge/A1111 inpaint goes through `/sdapi/v1/img2img` (denoise, mask blur, whole picture / only masked, padding, masked content). ComfyUI inpaint uses `LoadImage` (with the mask as alpha) → `VAEEncode` → `GrowMask` → `SetLatentNoiseMask`.
- **Regional prompts:** draggable, resizable boxes, each with its own prompt and weight. ComfyUI uses `ConditioningSetArea` + `ConditioningCombine` in front of every KSampler. Forge uses **Forge Couple** (Advanced mode, detected via `/sdapi/v1/scripts`), with the main prompt as a full-image background line. Without it, a message names the extension and offers "Send as one prompt instead" with position words. The page has the shared checkpoint picker.
- **Video** page (`promptmaker/video.py`): profiles for Wan 2.2, Wan 2.1, LTX-Video and HunyuanVideo (fps, valid frame counts 4n+1 / 8n+1, sizes, negative support, word range, prompting guide), 14 camera moves, 10 motion presets and 12 shot sizes. An offline structured builder in each model's preferred order, an AI writer, length and camera checks, default negatives, "Use ticked character", and saved video prompts. Prompt writing only.
- **Library sync** page (`promptmaker/sync.py`): export/import of history, favourites, templates, versions, characters, styles, video prompts, LoRA metadata, wildcards, model profiles and settings as `.zip` or `.json`. Merge or replace; same-name conflicts can keep mine, take theirs or keep both; content duplicates are skipped. Optional private GitHub gist push / pull / sync with last-modified conflict detection and a Keep this computer / Keep the gist / Merge both choice. The token is stored in the KeyStore. API keys are never exported: the KeyStore isn't read, and secret-looking settings names and values (`sk-…`, `ghp_…` …) are removed.
- `imagegen`: `Job.inpaint`, `Job.regions`, `A1111.regional_support()` and `ComfyUI.regional_support()`; Forge switches to `/sdapi/v1/img2img` for inpaint jobs.
- **Hires fix** for Forge/A1111 (Settings → Image generation): on/off, upscale factor, an upscaler list loaded from Forge (latent modes plus installed upscalers), hires steps and denoise. Applied to every txt2img job (Generate, Batch, Auto-refine, Pose, Regions) and skipped for inpaint. Sends `hr_additional_modules: ["Use same choices"]`, which Forge Neo requires.
- **Free VRAM for images:** Ollama's loaded text and vision models are unloaded (`keep_alive: 0`) right before each image is sent to Forge or ComfyUI, so the image model gets the GPU memory. On by default when the AI provider is Ollama; there's a checkbox in Settings → Image generation.
- **Size picker** on Auto-refine and Inpaint & Regions: Model default, 1024², 1344×768, 1216×832, 1152×896, 832×1216, 896×1152, 768×1344, and SD1.5 sizes. The choice is remembered for each page.
- Regions: **Repeat main prompt in every region** (on by default) puts the shared scene and count tags (e.g. `2girls, beach`) on every Forge Couple line, which is what makes multi-character splits work, including on Anima. The default base weight is now 0.2.
- 36 new tests (`tests/test_v4.py`, plus a size-picker UI test) using local mock servers for Forge, ComfyUI, the GitHub gist API and Ollama.

### Changed
- Database schema version 4: a migration adds the `video_prompts` and `sync_log` tables. v2 and v3 databases upgrade automatically.
- The tour covers the four new pages. There are new screenshots (`wildcards`, `inpaint`, `video`, `sync`), and the README has sections on inpaint, regions, wildcards, sync, and troubleshooting.
- Two v3 tests no longer pin the version number or schema version exactly.

### Fixed
- **Generate with regions** always said "Forge Couple not found". Qt's `clicked(False)` was passed in as the regional mode; the same issue affected **Open image…** and sync **Import…**.

## [3.0.0] – 2026-10-29
### Added
- **Setup wizard** (`promptmaker/firstrun.py`): opens on first launch, and from the sidebar (🧭 Setup wizard) or Settings. Checks whether Ollama is installed and running, its version and models, and pulls `llama3.2` and `qwen2.5vl` through `/api/pull` with a progress bar and Stop. Detects Forge/A1111 (`/sdapi/v1`, with the `--api` hint) and ComfyUI on their default ports, saves the results to settings, and picks an image backend if none is set.
- **Auto-refine** page (`promptmaker/autorefine.py`): generate → vision-model judgement (JSON score 0–100 with matches / missing / wrong / advice) → AI rewrite, for N iterations or until a score threshold. Uses the same seed on every iteration for a fair comparison. Each iteration is listed with a thumbnail and saved to the Gallery and History. Stop at any time; **Keep best** sends the best prompt to Refine and Favourites.
- **LoRAs** page (`promptmaker/loras.py`): scans `models/Lora`, `models/LyCORIS` and `embeddings` (Forge layout, folder configurable), hashes files (SHA256, AutoV2 = first 10 hex chars), looks them up via Civitai `/model-versions/by-hash/{hash}` for name, trigger words, base model and preview, and caches hashes (by path, size and mtime) and lookups in `data/cache/loras.json`. Filters by compatibility with the target profile (follows `inherits`; SDXL/Pony/Illustrious count as one family unless "Exact base model only" is ticked) and inserts `<lora:name:weight>` plus trigger words, or embeddings as `(name:weight)`.
- **Presets** page (`promptmaker/presets.py`): characters (name, appearance, outfit, optional LoRA and weight, reference image, notes) and styles (tags, extra negative) stored in SQLite. Tick several to combine; duplicates are removed. Batch has a "Keep ticked characters & styles" option so every variation keeps the same character.
- **Pose** page (`promptmaker/pose.py`, `promptmaker/posecanvas.py`): draggable OpenPose-18 skeletons with 8 starter poses (Standing, Arms up, Waving, T-pose, Hands on hips, Sitting, Walking, Kneeling) and labelled subject boxes. Produces composition tags (solo / 2people, framing, facing, pose, left/center/right, foreground/background) as tags or a sentence depending on the profile format. Exports an OpenPose PNG in the standard colours, and **Generate with ControlNet** sends it as a Forge/A1111 `alwayson_scripts.controlnet` unit, or uploads it to ComfyUI and patches the workflow with `ControlNetApplyAdvanced`.
- `imagegen`: `Job.controlnet`, `A1111.controlnet_models()`, `ComfyUI.upload_image()` and `ComfyUI.controlnet_models()`.
- 33 new tests (`tests/test_v3.py`), all against local mock servers or fake clients.

### Changed
- Database schema version 3: a numbered migration adds the `characters` and `styles` tables. v2 databases upgrade automatically and keep their data.
- `MainWindow.make_job()` now builds image jobs for every page (Generate, A/B, Auto-refine, Pose).
- The tour covers Auto-refine and Pose. German and Spanish strings were added for the new pages (machine-translated).
- Screenshots for the five new pages plus the app icon; `tools/screenshots.py` fills them with demo data.
- **App icon:** a purple rounded square with a sparkle and prompt lines (`promptmaker/assets/icon.svg`, `.ico`, `icon_256.png`, plus a simplified small-size variant). Used for the window, taskbar and the desktop shortcut created by `install.bat`.

### Fixed
- **Forge ControlNet `KeyError: 'none'` / `KeyError: 0`:** the preprocessor is now sent as `None` (capital N), which Forge's ControlNet requires. The follow-on `process_before_every_sampling` / `postprocess_batch_list` errors are gone.
- **Pose → ControlNet model:** a ControlNet model dropdown filled from Forge (exact names). Nothing is sent when no ControlNet models are installed, the page warns when the model doesn't match the checkpoint's architecture, and it reports when Forge didn't record ControlNet in the result.
- **Anima pose support:** Anima is recognised as needing an Anima **ControlNet-LLLite** model (e.g. kohya-ss `anima-lllite-pose-1.safetensors`); SD/SDXL ControlNets are flagged as incompatible.
- **Checkpoint picker:** the Settings box is wider, shows the full name without the `[hash]`, has a working dropdown arrow, loads the list on demand and saves on change. Pose and Auto-refine have their own picker, shared with Settings.

### Docs
- (Carried over from after 2.0.0) Docs: README refreshed for 2.0 (new Troubleshooting section, full screenshot set including Analyse, Templates, Batch, History and the Civitai review screen). `tools/screenshots.py` now uses fresh demo data in a temp folder and never touches the network.

## [2.0.0] – 2026-10-25

### Added
- **Image generation:** ComfyUI (API workflows with `{{placeholder}}` injection; SDXL and FLUX workflows included; custom workflows from `data/workflows/`) and Forge / AUTOMATIC1111 (`/sdapi/v1/txt2img`). Connection test, queue, progress and cancel.
- **Gallery** (`data/gallery/`): thumbnails, full view, metadata sidecars, reuse prompt, same seed again, open folder and delete.
- **Image to Prompt:** drop, paste or open an image. Ollama vision models are detected, and LM Studio / OpenAI-compatible vision models are supported. Output follows the target model profile and can go to the Builder, Refine, Score or Generate.
- **Provider abstraction:** Ollama, LM Studio, llama.cpp, KoboldCpp, vLLM, custom OpenAI-compatible, and optional OpenAI, Anthropic, Google Gemini and OpenRouter, all with streaming. API keys are kept in the OS keyring, with a clearly warned plain-text fallback.
- **A/B Test:** side-by-side heuristic and AI scores, diff highlighting, same-seed renders and a winner saved to History.
- **Community gallery:** `community/index.json` with install, update and uninstall and SHA-256 verification, seeded with the starter packs and an SDXL-Lightning profile. Contribution guide added.
- **Settings page**, **first-run guided tour**, optional **update check** (GitHub releases), **portable vs AppData** data location, and **i18n** (English plus machine-translated Español and Deutsch).
- Tests for providers, image backends, the gallery, community, updates, paths, the keystore, A/B and i18n, all run against local mock servers.

- **Friendly "model can't load" handling.** Ollama errors such as `unknown model architecture: 'mllama'`, `error loading model` or "llama-server process has terminated" (for example, `llama3.2-vision` on newer Ollama builds) now show a clear message instead of a raw HTTP 500. It explains that the model can't run on this Ollama version and that re-pulling won't help, and suggests another model or updating Ollama. One-click actions switch to another installed model (vision: qwen2.5vl, then gemma3, llava…) or copy `ollama pull qwen2.5vl`. Models that failed are remembered, shown in red with a tooltip in the model pickers, and sorted last. The mark is cleared once the model works again. The same handling covers chat models.

- **Ollama version check:** PromptMaker reads `/api/version`. On Ollama 0.30+, Llama 3.2 Vision models (architecture `mllama`) are marked as unsupported in the vision model picker (red, sorted last, never auto-selected), with the tooltip "Not supported on Ollama 0.30+ (llama.cpp engine has no mllama support, see ollama/ollama#16547)". The friendly load-error message explains the same thing and points to qwen2.5vl / qwen3-vl.

- **Civitai import** (Model profiles → 🌐 Import from Civitai…) works with civitai.com, civitai.red or any civitai.* link, a model or version ID, or an AIR. Using the public REST API (`/models`, `/model-versions`, `/images`), it reads the creator's recommended positive/negative prompts and settings (steps, CFG, sampler, clip skip, resolution) from the description. It also mines sample-image generation data by tag frequency. A review screen lets you edit everything before saving a profile that **inherits** from the matching base profile (Anima, Illustrious, Pony, SDXL…) with the source URL and version recorded. The profile feeds the Builder, the AI system prompt, Score model-fit and image generation (steps, CFG, sampler, scheduler, clip skip). LoRA trained words are stored. Also adds **⟳ Refresh from Civitai**, an optional API key in the keyring, a 24 h response cache and HTTP 429 back-off.
- Profiles support `"inherits": "<profile id>"`.

- **Forge / A1111 connection diagnostics.** If the WebUI is running but `/sdapi/v1` returns 404, PromptMaker now checks `/openapi.json` and `/internal/sysinfo` to tell an "API not enabled" install (started without `--api`) apart from ComfyUI or SwarmUI on that port. It then shows the exact fix, with the path to `webui-user.bat` and a **Copy `set COMMANDLINE_ARGS=--api`** button. This happens both on Test connection and when generating. Test connection now also reports the variant and version (Forge Neo / Forge Classic / Forge / reForge / AUTOMATIC1111).

### Fixed
- Forge/A1111: a checkpoint override no longer discards the clip-skip override (both go into `override_settings`).
- Toasts no longer cover the buttons beneath them. They now appear top-right, away from the bottom action rows, and let clicks pass through (`WA_TransparentForMouseEvents`). Before this fix, the History "Clear all" confirmation toast covered the button it asked you to click again.
- Two-click confirmations now happen on the button itself instead of in a toast. The first click turns it into a red "Confirm clear (4s)" button with a live countdown, a second click runs the action, and it reverts on its own after 4 s. This applies to History "Clear all", and the same confirmation is now required for every 🗑 Delete button (templates, history item, favourites, packs, gallery) and for Community "Uninstall".

- Dialogs and message boxes now use the app's dark background; before, their labels were unreadable.
- Closing the window now waits for background workers to finish, so a running request can no longer crash the app when it exits (a Windows `0xC0000409` crash). The test suite also shuts Qt down cleanly.

### Changed
- The vision model preference order now puts `qwen2.5vl` first, and the "no vision model" hint suggests `ollama pull qwen2.5vl`.
- User and imported packs now live in `data/packs/`, and the bundled `packs/` folder is read-only. An existing `packs/custom.json` is migrated automatically.
- `keyring` added to the requirements (optional at runtime).

## [1.0.0] – 2026-10-25
First public release.

### Added
- **Create** page: turn a plain idea into finished prompts for the selected model, with a creativity slider, 1–5 options, streaming, a separate negative prompt and recommended settings. Includes an offline preset-based fallback and a one-click "Start Ollama" button.
- **Ctrl+K** quick idea bar.
- **Builder** with 13 categories, about 800 grouped presets as chips, global search, locks, randomise, custom chips and a live model-aware preview with a quick score.
- **Refine** chat with a local LLM (Ollama): apply suggestions, quick actions, version history and revert.
- **Analyse:** break a prompt into categories (offline or AI) and load it into the Builder.
- **Score:** a 5-part rubric with an offline heuristic and an optional AI review.
- Templates with placeholders, batch variations (.txt/.csv export), searchable history and favourites.
- Preset packs (import/export/enable/disable) with 5 starter packs.
- 16 editable model profiles: FLUX.2 (+JSON), FLUX.1, FLUX.1 Kontext, SDXL, SD 3.5, Pony V6, Illustrious/NoobAI, Anima, MOSS-Image, Qwen-Image, HiDream-I1, Midjourney V7, GPT Image 2/2.5, Imagen 4, and Generic.
- Dark/light custom theme, toasts, and `install.bat` / `run.bat` (plus `install.sh` / `run.sh`).

[Unreleased]: https://github.com/Kisahime/promptmaker/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/Kisahime/promptmaker/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/Kisahime/promptmaker/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/Kisahime/promptmaker/releases/tag/v1.0.0
