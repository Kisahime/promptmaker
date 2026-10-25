"""Tiny i18n layer: English source strings are keys; translations live in i18n/<code>.json."""
import json
import os

DIR = os.path.join(os.path.dirname(__file__), "i18n")
LANGUAGES = {"en": "English"}
_current = {}
_code = "en"


def available():
    langs = dict(LANGUAGES)
    if os.path.isdir(DIR):
        for fn in sorted(os.listdir(DIR)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(DIR, fn), encoding="utf-8") as f:
                        meta = json.load(f).get("_meta", {})
                    langs[fn[:-5]] = meta.get("name", fn[:-5]) + (" (machine-translated)" if meta.get("machine_translated") else "")
                except (OSError, ValueError):
                    pass
    return langs


def set_language(code):
    global _current, _code
    _code, _current = code, {}
    if code != "en":
        try:
            with open(os.path.join(DIR, code + ".json"), encoding="utf-8") as f:
                _current = json.load(f).get("strings", {})
        except (OSError, ValueError):
            _code = "en"
    return _code


def language():
    return _code


def tr(text):
    if not _current or not isinstance(text, str):
        return text
    return _current.get(text, text)
