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

## Sharing a pack or profile (community gallery)
The in-app **🌐 Community** page reads `community/index.json`. To publish something:

1. Add your file:
   - a pack goes in `community/packs/<your-pack>.json`, using the pack format from the README;
   - a profile goes in `community/profiles/<name>.json` as `{"profiles": [ {…profile…} ]}`, with every aspect ratio in `resolutions` and real `sources`.
2. Work out its hash: `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" community/packs/your-pack.json`
3. Add an entry under `"packs"` or `"profiles"` in `community/index.json`:
   ```json
   {"id": "your-pack", "name": "Your pack", "author": "you", "description": "…",
    "version": "1.0", "url": "packs/your-pack.json", "sha256": "<hash>"}
   ```
   `url` is relative to `index.json`, or an absolute `https://` URL. When you update the file, bump `version` and the `sha256` too, and users will see "update available".
4. Run `python -m pytest -q`. The tests check that every hash in the index matches its file.
5. Open a pull request. The same content rules apply: SFW, no duplicates, and no sensitive living-artist names.

## Translations
Strings live in `promptmaker/i18n/<code>.json` (`{"_meta": {"name": …, "machine_translated": true|false}, "strings": {"English": "Translated"}}`). Fixes to the machine translations are very welcome. When a human has checked a file, set `machine_translated` to `false`.

## Code style
- Python 3.10+, standard library plus PySide6 (and the optional `keyring`). No new runtime dependencies without discussion; network code uses `urllib`.
- Keep logic that doesn't need the UI in `builder.py`, `scoring.py`, `library.py` and `profiles.py`, with unit tests in `tests/`.
- Test network code against a local mock server (see `tests/test_v2.py`), never real services.
- Never commit `data/`, `.venv/` or `packs/custom.json`.
