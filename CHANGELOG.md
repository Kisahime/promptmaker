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

### Changed
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
