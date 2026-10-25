"""Per-model target profiles (editable JSON)."""
import json
import os
import shutil

BUNDLED = os.path.join(os.path.dirname(__file__), "profiles.json")
ASPECTS = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "4:5"]
DEFAULTS = dict(format="natural", negative="optional", weighting="none", weight_max=1.5, quality_prefix="",
                negative_default="", length=[15, 120], params={}, param_style="none", resolutions={},
                settings="", ai_guidance="", tips=[], sources=[], family="Other")


def ensure_user_file(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy(BUNDLED, path)
    else:  # add any new bundled profiles the user doesn't have yet
        try:
            user = json.load(open(path, encoding="utf-8"))
            ids = {p.get("id") for p in user.get("profiles", [])}
            new = [p for p in json.load(open(BUNDLED, encoding="utf-8"))["profiles"] if p["id"] not in ids]
            if new:
                user["profiles"].extend(new)
                json.dump(user, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        except (OSError, ValueError, KeyError):
            pass
    return path


def load(path=BUNDLED):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = {p["id"]: p for p in data.get("profiles", []) if "id" in p and "name" in p}
    out = {}
    for pid, p in raw.items():
        out[pid] = resolve(p, raw)
    if not out:
        raise ValueError("No valid profiles found")
    return out


def resolve(p, raw, _seen=None):
    """Apply defaults and "inherits": child fields override the parent profile's (one level or a chain)."""
    seen = _seen or set()
    full = dict(DEFAULTS)
    parent = p.get("inherits")
    if parent and parent in raw and parent not in seen and parent != p.get("id"):
        seen.add(p.get("id"))
        full.update({k: v for k, v in resolve(raw[parent], raw, seen).items() if k not in ("id", "name", "inherits")})
    full.update(p)
    return full


def raw_profile(path, pid):
    try:
        for p in json.load(open(path, encoding="utf-8")).get("profiles", []):
            if p.get("id") == pid:
                return p
    except (OSError, ValueError):
        pass
    return None


def save_profile(path, profile):
    data = json.load(open(path, encoding="utf-8"))
    lst = data.setdefault("profiles", [])
    for i, p in enumerate(lst):
        if p.get("id") == profile["id"]:
            lst[i] = profile
            break
    else:
        lst.append(profile)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def resolution(profile, aspect):
    return profile.get("resolutions", {}).get(aspect, "")
