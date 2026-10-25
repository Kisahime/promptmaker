# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] – Unreleased

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
