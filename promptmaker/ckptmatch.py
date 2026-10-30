"""Match a target-model profile to one of the backend's checkpoints (4.0.1).

Only Civitai-imported profiles are auto-matched (built-in profiles like "Illustrious XL" are families, not files).
Returns a checkpoint only on a confident, unique match; otherwise None.
"""
import difflib
import os
import re


def strip_hash(name):
    return re.sub(r"\s*\[[0-9a-fA-F]{6,}\]\s*$", "", (name or "").strip())


def norm(text):
    text = strip_hash(text or "")
    text = os.path.basename(text.replace("\\", "/"))
    text = re.sub(r"\.(safetensors|ckpt|pt|pth|gguf|bin)$", "", text, flags=re.I)
    text = re.sub(r"\(civitai\)", "", text, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _digits(s):
    return re.sub(r"[^0-9]", "", s)  # never fuzzy-match across versions (v20 vs v30)


def queries(profile):
    c = profile.get("civitai") or {}
    if not c:
        return [], []
    files = [c["file_name"]] if c.get("file_name") else []
    names = []
    full = f"{c.get('model_name') or ''} {c.get('version_name') or ''}".strip()
    for n in (full, profile.get("name", ""), c.get("model_name") or ""):
        if norm(n) and len(norm(n)) >= 5 and norm(n) not in names:
            names.append(norm(n))
    return [norm(f) for f in files if norm(f)], names


def match(profile, checkpoints, threshold=0.88):
    files, names = queries(profile)
    cks = [(c, norm(c)) for c in checkpoints or [] if norm(c)]
    if not cks or not (files or names):
        return None
    for f in files:  # 1. exact file name
        hits = [c for c, n in cks if n == f]
        if len(hits) == 1:
            return hits[0]
    for q in names:  # 2. exact normalised name, 3. containment, 4. high similarity — each must be unique
        for test in (lambda n: n == q,
                     lambda n: (q in n or n in q) and min(len(n), len(q)) >= 5,
                     lambda n: _digits(n) == _digits(q) and difflib.SequenceMatcher(None, q, n).ratio() >= threshold):
            hits = [c for c, n in cks if test(n)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                break  # ambiguous at this level: try the next (more specific earlier) query, never guess
    return None
