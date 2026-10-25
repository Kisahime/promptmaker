"""Prompt scoring: fast offline heuristic + rubric definition shared with the AI scorer."""
import re

RUBRIC = ["Clarity", "Specificity", "Composition", "Style coherence", "Model fit"]
VAGUE = {"nice", "beautiful", "cool", "awesome", "good", "stuff", "thing", "things", "amazing", "pretty",
         "great", "very", "really", "some", "interesting"}
COMPOSITION_WORDS = ["shot", "angle", "close-up", "closeup", "view", "lens", "foreground", "background",
                     "framing", "frame", "centered", "composition", "rule of thirds", "symmetr", "portrait",
                     "wide", "depth of field", "bokeh", "perspective", "full body", "upper body", "cowboy shot",
                     "from above", "from below", "left", "right", "behind", "in front"]
CONFLICTS = [("photorealistic", "anime"), ("photorealistic", "cartoon"), ("photo", "watercolor"),
             ("pixel art", "photorealistic"), ("black and white", "vibrant colors"), ("monochrome", "rainbow"),
             ("minimalist", "maximalist"), ("midday", "night"), ("noon", "midnight"), ("sunset", "midnight"),
             ("sunrise", "sunset"), ("low poly", "hyperrealistic"), ("pastel", "neon"), ("cheerful", "ominous"),
             ("joyful", "melancholic"), ("serene", "chaotic")]
FILLER = ["masterpiece", "8k", "4k", "best quality", "trending on artstation", "ultra hd", "award-winning"]
PHOTO_WORDS = ["photorealistic", "photograph", "photography", "photo", "dslr", "realistic skin", "raw photo"]


def _has(text, term):
    return re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text) is not None


def _clamp(x):
    return max(0, min(10, round(x)))


def heuristic_score(prompt, profile, items_by_cat=None):
    items_by_cat = items_by_cat or {}
    full = prompt or ""
    body = re.split(r"\s--\w", full)[0]
    low = body.lower()
    words = re.findall(r"[\w'@-]+", low)
    n = len(words)
    fixes, crit = [], {}
    lo, hi = profile.get("length", [15, 120])

    # Clarity
    c, why = 10, []
    if n < lo:
        c -= 4 if n < lo / 2 else 2; why.append(f"short ({n} words, aim for {lo}–{hi})")
        fixes.append(f"Add more concrete description – {profile['name']} works best with about {lo}–{hi} words.")
    elif n > hi:
        c -= 3; why.append(f"long ({n} words)")
        fixes.append(f"Trim to under ~{hi} words; extra words dilute the important ones.")
    vague = sorted({w for w in words if w in VAGUE})
    if vague:
        c -= min(3, len(vague)); why.append("vague words: " + ", ".join(vague))
        fixes.append("Replace vague words (" + ", ".join(vague) + ") with specific visual details.")
    dupes = sorted({w for w in words if len(w) > 4 and words.count(w) > 2})
    if dupes:
        c -= 1; why.append("repetition: " + ", ".join(dupes[:3]))
    crit["Clarity"] = (_clamp(c), "; ".join(why) or "clear and readable")

    # Specificity: how many categories are covered
    covered = [cat for cat, items in items_by_cat.items() if any(_has(low, i.lower()) for i in items if len(i) > 3)]
    adjectives = len([w for w in words if w.endswith(("ed", "ous", "ful", "ic", "ive", "y")) and len(w) > 4])
    s = 2 + 1.2 * len(covered) + min(3, adjectives / 3) + (1 if re.search(r"\d", low) else 0)
    missing = [k for k in ["Setting", "Style", "Lighting", "Camera", "Mood"] if k not in covered]
    if missing and s < 9:
        fixes.append("Be more specific about: " + ", ".join(m.lower() for m in missing[:3]) + ".")
    crit["Specificity"] = (_clamp(s), f"covers {len(covered)} categories" + (f", missing {', '.join(missing[:3])}" if missing else ""))

    # Composition
    hits = [w for w in COMPOSITION_WORDS if w in low]
    co = 3 + 2 * len(hits)
    if not hits:
        fixes.append("Say how the image is framed (e.g. 'low angle wide shot, subject on the left third').")
    crit["Composition"] = (_clamp(co), ", ".join(hits[:4]) or "no framing or camera cues")

    # Style coherence
    conflicts = [(a, b) for a, b in CONFLICTS if _has(low, a) and _has(low, b)]
    styles = [i for i in items_by_cat.get("Style", []) + items_by_cat.get("Art movement", []) if _has(low, i.lower())]
    sc = 10 - 3 * len(conflicts) - max(0, len(styles) - 3) - (2 if not styles and profile.get("format") != "json" else 0)
    for a, b in conflicts:
        fixes.append(f"'{a}' and '{b}' pull in different directions – pick one.")
    if len(styles) > 3:
        fixes.append(f"{len(styles)} different styles mixed – keep 1–2 for a coherent look.")
    if not styles:
        fixes.append("Name a style or medium (e.g. 'oil painting', 'cinematic still').")
    crit["Style coherence"] = (_clamp(sc), ("conflicts: " + "; ".join(f"{a}/{b}" for a, b in conflicts)) if conflicts
                               else f"{len(styles)} style term(s)")

    # Model fit
    m, why = 10, []
    fmt = profile.get("format")
    weighted = bool(re.search(r"\([^()]+:\d(\.\d+)?\)", full))
    commas, periods = body.count(","), len(re.findall(r"[.!?](\s|$)", body))
    if weighted and profile.get("weighting") != "parens":
        m -= 3; why.append("weighting syntax not supported")
        fixes.append(f"{profile['name']} ignores (term:1.2) weighting – remove it and put key words first.")
    if "--" in full and profile.get("param_style") != "midjourney":
        m -= 3; why.append("Midjourney --params on a non-MJ model")
        fixes.append("Remove --parameters; set size/settings in your tool instead.")
    if profile.get("param_style") == "midjourney" and "--ar" not in full:
        m -= 1; fixes.append("Add an aspect ratio, e.g. --ar 16:9.")
    if fmt == "tags" and periods > 1 and commas < n / 6:
        m -= 3; why.append("prose where tags expected")
        fixes.append("This model prefers comma-separated tags rather than sentences.")
    if fmt == "natural" and commas > 6 and periods == 0 and n > 15:
        m -= 3; why.append("tag list where prose expected")
        fixes.append(f"{profile['name']} understands natural language – rewrite the tag list as 1–3 descriptive sentences.")
    if fmt == "hybrid" and periods == 0:
        m -= 2; fixes.append("Add at least two natural-language sentences after the tags.")
    prefix = [t.strip() for t in profile.get("quality_prefix", "").split(",") if t.strip()]
    if prefix and not low.startswith(prefix[0].lower()):
        m -= 2; why.append("missing quality prefix")
        fixes.append(f"Start with the recommended prefix: '{profile['quality_prefix']}'.")
    if fmt in ("natural", "json") and not prefix:
        filler = [f for f in FILLER if _has(low, f)]
        if filler:
            m -= 1; why.append("filler tags")
            fixes.append("Quality filler (" + ", ".join(filler) + ") does little for this model – describe real detail instead.")
    if profile.get("family") == "Anima" and any(_has(low, w) for w in PHOTO_WORDS):
        m -= 3; fixes.append("Anima is an anime/illustration model – photorealism is outside its range.")
    if "Negative prompt:" in full and profile.get("negative") in ("unsupported", "param_no"):
        m -= 2; fixes.append("This model has no separate negative prompt.")
    crit["Model fit"] = (_clamp(m), "; ".join(why) or f"fits {profile['name']}")

    total = sum(v[0] for v in crit.values()) * 2
    return {"total": total, "criteria": crit, "fixes": list(dict.fromkeys(fixes))[:8], "words": n}


def grade(total):
    return "Excellent" if total >= 85 else "Good" if total >= 70 else "Fair" if total >= 50 else "Needs work"
