# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [5.0.0] - 2026-10-31

### Added
- **Characters** (new *Characters* section on the rail): full characters built on the existing character presets, with reference images, multiple named outfits, several LoRAs with weights, trigger words and tag sets per target model. Insert a character + outfit into Create, Refine, a new region or the clipboard, also from the new **👤 Character** buttons on Create and Inpaint & Regions and the command palette. Re-inserting swaps the outfit cleanly and never duplicates LoRA tags.
- **Character reference images (IP-Adapter)**: optional per character. It is used only when the backend supports it (Forge: an IP-Adapter ControlNet model; ComfyUI: ComfyUI_IPAdapter_plus). Otherwise it is skipped, and *Check reference support* says why.
- **Gallery character tags**: new images record which characters appear, from trigger words / LoRAs in the prompt (always) and, if you opt in, from the local Ollama vision model in the background.
- **Storyboard & comics**: an AI panel plan from a short story using your Characters, per-panel or *Generate all* through the queue, a page layout editor (8 grid templates, 4 page sizes, fonts, editable speech bubbles and captions, drag Gallery images onto panels), PNG / PDF export and `.pmstory` project files.
- **Live sketch** (Studio): a paint canvas with a debounced, low-step img2img result beside it (Lightning/Turbo, Balanced and Quality presets), or ControlNet scribble when a scribble model is installed. Send the result to the Gallery, Inpaint or Image to Prompt.
- **LoRA training (optional)**: dataset picker (15–50 images), captions from prompts or the vision model, VRAM presets, kohya-ss/sd-scripts run as a separate process with progress, log and cancel. The output goes to Forge's `models/Lora` and is linked to a Character. *Install trainer* clones sd-scripts into `tools/sd-scripts` with its own venv, only after you confirm.
- **Vision-model routing**: every feature that sends images (Image to Prompt, auto-caption, Auto-refine, gallery tagging) checks the model's capabilities through Ollama `/api/show` and only uses a real vision model. A vision model picker on the LoRA page; captioning stops on the first failure with a clear message instead of repeating HTTP 400s.
- Home quick-start tiles and command-palette entries for the new pages.

### Changed
- The trainer installer runs each step in the right folder, is resumable (marker file `.promptmaker_installed`) and forces UTF-8 for sd-scripts.
- The rail has a seventh section, **Characters** (Characters, Storyboard, LoRA training). Studio gains a **Live sketch** tab.
- Database schema 5: characters get an `extra` column for the new fields. 4.x character presets are kept as they are and still work on the Presets page.

## [4.1.5] - 2026-10-30

### Added
- **Command palette (Ctrl+K, or the search box in the top bar):** jump to any page, open the queue, run the setup wizard, show or hide the inspector, or switch theme. Anything else you type still writes a prompt from your idea, as the old quick bar did.
- **Studio workspace:** Create, Builder, Refine, Batch and Templates share one workspace. The prompt editor sits in the centre, with a collapsible **Generation inspector** on the right (backend, checkpoint, steps, CFG, sampler, scheduler and hires fix, all live) and a **filmstrip** of recent results along the bottom. Click a result to open it in the viewer.
- **Theme picker** in Settings → Appearance with four themes: **Graphite dark** (new default), **Graphite light**, **Pastel** and **Pastel dusk** (the cute pastel look, with bundled Nunito font, gradients, pill controls and sparkle headers). Each theme family has its own accent set: Violet, Blue, Teal, Pink and Orange for Graphite, and Lavender, Sakura pink, Mint, Baby blue and Peach for Pastel. Ctrl+T switches between light and dark within the current family.
- **Home dashboard stat cards**: counts for images, prompts, favourites and characters.

### Changed
- **New layout.** The long sidebar is now a **slim icon rail** with six sections: Home, Studio, Gallery, Tools, Library and Settings. It expands to show labels, and its choice is remembered. Each section shows its pages as tabs, and each section remembers the last page you used.
- **A top bar** now holds the search / command palette, image-backend status and queue, target model, AI model and status, the inspector toggle, the setup wizard and the light/dark switch. These used to be crammed into the sidebar footer, so the collapsed sidebar no longer cuts off buttons.
- **Settings is a two-pane page:** a category list (Appearance, General, AI provider, Image generation, Civitai, Community gallery) on the left and one page per category on the right. Image generation settings move into the Studio inspector while you're in the Studio, and come back to Settings when you open it.
- **New default look:** clean graphite neutrals with one vivid accent, consistent radius, type and spacing tokens, and refined controls. All styling comes from `theme.py`.
- **Create page:** the action buttons wrap instead of clipping, and Generate is now a primary button next to Copy.
- The README screenshot script captures Create correctly (it used to capture Home) and now also captures light and Pastel shots.
- All pages, features and shortcuts are unchanged and reachable: Ctrl+K, Ctrl+T, Ctrl+Shift+C and every page via the rail, its tabs or the palette.

### Fixed
- A/B Test generation no longer crashes with an overflow on large random seeds.
- Duplicate page titles removed; "&" now displays correctly in sub-tab labels.
- Pages scroll instead of clipping on small windows (e.g. Pastel dusk Create at 1440x900); the inspector auto-hides below 1360px wide (toggle still shows it).
- Gallery queue strip only appears while jobs are queued or running.

## [4.1.0] - 2026-10-30

### Added
- **🏠 Home dashboard** (new first page): target model and its linked checkpoint, Forge / Ollama status, recent images, and quick-start buttons (Create, Builder, Generate last prompt, Auto-refine, Inpaint, Gallery).
- **Gallery actions**: right-click or the detail-pane buttons for *Inpaint this* (opens Inpaint & Regions with the image and its prompt), *Use as reference* (Image to Prompt), *Regenerate with hires* (same prompt, seed and settings with hires fix on) and *Upscale…*. Drag a thumbnail onto the inpaint canvas to load it.
- **One-click Upscale**: Forge img2img at 1.5× (factor, upscaler and denoise 0.3 adjustable; same prompt and seed) or *Pure upscale* through Forge's Extras (`/sdapi/v1/extra-single-image`). ComfyUI supports Pure upscale (`ImageScaleBy`). The result is saved to the Gallery with `source_image` in its sidecar.
- **Backend status** in the sidebar: 🟢 *Forge · active checkpoint* / 🔴 *Offline* / *Loading…*, checked every 10 s in the background (one request at a time, `/sdapi/v1/options` or ComfyUI `/system_stats`). Click it for Settings; ☰ opens the queue.
- **Queue view**: pending and running jobs with size and origin page, ▲/▼ reorder, cancel selected, cancel all and progress for the running job. Opens from the sidebar ☰, the Gallery's *Manage queue* button or a double-click on the queue list.
- **Per-target-model image settings**: each target model also remembers aspect/size, steps, CFG, sampler and scheduler (`profile_image_settings`, included in Library sync), restored when you switch. Settings shows *Linked to: model · checkpoint · 16:9 · 30 steps · …*.
- **Live generation preview** from Forge's `/sdapi/v1/progress` `current_image`, shown in the Gallery queue area and on the Auto-refine page (Settings toggle). ComfyUI previews come over its websocket (see below).
- **Look & feel**: justified gallery rows that keep each image's aspect ratio, a hover preview, a full-screen viewer (←/→, Esc); accent colour picker (purple, teal, pink, orange) for dark and light themes; collapsible icon-only sidebar (remembered); 150 ms page fade (can be switched off); loading placeholders for checkpoint pickers and LoRA scans.
- **Live preview and exact step progress** over ComfyUI's websocket (`/ws?clientId=…`, same client id as `/prompt`; built-in client, no new dependency). Preview frames need ComfyUI started with `--preview-method auto` (or `taesd`); without it you still get *Step n/N* progress.
- **Hires fix on ComfyUI**: `LatentUpscaleBy` + a second KSampler pass with your hires scale, denoise and steps (the Settings checkbox is now just *Hires fix*; the upscaler list stays Forge-only).

### Fixed
- Full-screen viewer "zoom-in" while browsing: each new picture enlarged the image label, which grew the window, which scaled the next picture bigger. The viewer now always fits the image to the window (aspect kept, centred), switches instantly with ←/→ or the mouse wheel, and hides the gallery hover preview.
- ComfyUI: sampler/scheduler names saved from a Forge list (e.g. `DPM++ 2M` / `Karras`) are converted to ComfyUI names (`dpmpp_2m` / `karras`) instead of failing workflow validation.
- Sidebar status for ComfyUI read "ComfyUI · ComfyUI 0.43.0"; now "ComfyUI · v0.43.0".
- Tests: windows are destroyed after each test (full suite ~9.6 min → ~1 min).

## [4.0.1] - 2026-10-30

### Added
- The image checkpoint now follows the **Target model**: the checkpoint you pick in any picker is remembered per target model (`profile_checkpoints` setting, included in Library sync) and restored when you switch. Civitai-imported profiles without a link are auto-matched to a backend checkpoint by file name or normalised name, only when the match is unique. Settings shows "Linked to: …"; choosing Backend default unlinks.
- **Sampler** and **Scheduler** pickers in Settings → Image generation, with ⟳ to load the lists from Forge/A1111 or ComfyUI (built-in scheduler list as a fallback). "Profile default" keeps the profile's choice; anything else overrides it on every page. Forge/A1111 payloads now include `scheduler`.

### Fixed
- Forge Neo: grey/blank images after switching from an Anima checkpoint to SDXL. Anima's VAE and text encoder stayed selected in Forge's VAE / Text Encoder box. PromptMaker now sends `forge_additional_modules` with every Forge image that names a checkpoint: none for SD1.5/SDXL/Illustrious/Pony, `qwen_image_vae` + `qwen_3_06b` for Anima (found via `/sdapi/v1/sd-modules`). Other architectures (FLUX, Qwen…) and plain AUTOMATIC1111 are left untouched.
- Checkpoint lists could stay empty (even after ⟳ / Test connection) when a background request's result was dropped before it reached the window. Workers are now kept until their result is delivered, and ⟳ always reloads.
- New optional profile field `forge_modules` (list of module file names) overrides the automatic choice.

## [4.0.0] - 2026-10-29

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
