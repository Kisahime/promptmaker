# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

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
