# Contributing to PromptMaker

Thanks for helping out! Bug reports, preset packs, model profiles and code are all welcome.

## Quick start
1. Fork the repo and create a branch: `git checkout -b my-change`
2. Set up: `python -m venv .venv` then `pip install -r requirements-dev.txt`
3. Run checks before opening a PR:
   ```bash
   python -m pytest -q
   python -m pyflakes promptmaker tests
   QT_QPA_PLATFORM=offscreen python main.py --smoke-test
   ```
4. Open a pull request that explains what changed and why. Include screenshots for UI changes.

## Adding a model profile
- Add an entry to `promptmaker/profiles.json` (see the field list in the README).
- Include `sources` that link to official docs or model cards, and only add models you can verify exist.
- Provide a `resolutions` entry for every aspect ratio (`1:1 16:9 9:16 4:3 3:4 3:2 2:3 21:9 4:5`). The tests check this.

## Adding presets / packs
- Small additions can go into `packs/core.json`. Themed collections are better as a new pack file in `packs/`.
- Keep items short, visual and non-duplicated. Avoid living-artist names that could be sensitive. Never add NSFW content to the bundled packs.

## Code style
- Python 3.10+, standard library plus PySide6 only (no new runtime dependencies without discussion).
- Keep logic that doesn't need the UI in `builder.py`, `scoring.py`, `library.py` and `profiles.py`, with unit tests in `tests/`.
- Never commit `data/`, `.venv/` or `packs/custom.json`.
