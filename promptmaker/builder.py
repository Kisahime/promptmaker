"""Profile-aware prompt building (pure logic, no UI)."""
import csv
import io
import json
import random
import re

from .library import CATEGORY_ORDER, LEGACY, PLACEHOLDERS

ARTIST_RE = re.compile(r"^(?:inspired by|in the style of)\s+", re.I)


def norm_sel(sel):
    out = {}
    for c, v in (sel or {}).items():
        c = LEGACY.get(c, c)
        vals = [v] if isinstance(v, str) else list(v or [])
        vals = [x.strip() for x in vals if x and x.strip() and x != "(none)"]
        if vals:
            out[c] = vals
    return out


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def _tagify(item, cat, profile):
    t = item.lower()
    if cat == "Artist influence":
        name = ARTIST_RE.sub("", t)
        name = re.sub(r"\s+cinematography$", "", name)
        return ("@" + name) if profile.get("family") == "Anima" else ("by " + name)
    t = re.sub(r"^(a|an|the)\s+", "", t)
    if not profile.get("underscores", False):
        t = t.replace("_", " ") if not t.startswith("score_") else t
    return t


def _weight(text, profile, w=1.2):
    if profile.get("weighting") == "parens":
        return f"({text}:{min(w, profile.get('weight_max', 1.5))})"
    return text


def _natural(sel, extra):
    g = lambda c: sel.get(c, [])
    s1 = " ".join(g("Subject") + g("Action / pose") + g("Setting") + g("Time & weather"))
    sentences = []
    if s1:
        sentences.append(_cap(s1))
    style = ", ".join(g("Style") + g("Art movement") + g("Artist influence"))
    if style:
        sentences.append(_cap(style))
    look = ", ".join(g("Lighting") + g("Camera") + g("Composition"))
    if look:
        sentences.append(_cap(look))
    tone = []
    if g("Mood"):
        tone.append(", ".join(g("Mood")) + " mood")
    tone += g("Color palette") + g("Detail / quality")
    if tone:
        sentences.append(_cap(", ".join(tone)))
    if extra:
        sentences.append(_cap(extra.strip().rstrip(".")))
    return ". ".join(sentences) + ("." if sentences else "")


def _tags(sel, extra, profile, emphasis):
    tags = [t.strip() for t in profile.get("quality_prefix", "").split(",") if t.strip()]
    for cat in CATEGORY_ORDER:
        for i, item in enumerate(sel.get(cat, [])):
            t = _tagify(item, cat, profile)
            if emphasis and cat == "Subject" and i == 0:
                t = _weight(t, profile)
            if t not in tags:
                tags.append(t)
    if extra:
        tags.append(extra.strip())
    return ", ".join(tags)


def _hybrid(sel, extra, profile, emphasis):
    tag_cats = ["Style", "Art movement", "Artist influence", "Detail / quality"]
    tsel = {c: v for c, v in sel.items() if c in tag_cats}
    tags = _tags(tsel, "", profile, False)
    nsel = {c: v for c, v in sel.items() if c not in tag_cats}
    prose = _natural(nsel, extra)
    if emphasis and sel.get("Subject"):
        tags += ", " + _weight(_tagify(sel["Subject"][0], "Subject", profile), profile)
    return (tags + ". " + prose).strip(". ") if prose else tags


def _json(sel, extra):
    g = lambda c: sel.get(c, [])
    d = {"scene": " ".join(g("Setting") + g("Time & weather")) or None,
         "subjects": [{"description": s, "action": " ".join(g("Action / pose")) or None} for s in g("Subject")],
         "style": ", ".join(g("Style") + g("Art movement") + g("Artist influence")) or None,
         "color_palette": g("Color palette") or None, "lighting": ", ".join(g("Lighting")) or None,
         "mood": ", ".join(g("Mood")) or None, "composition": ", ".join(g("Composition")) or None,
         "camera": {"angle_lens": ", ".join(g("Camera"))} if g("Camera") else None,
         "details": ", ".join(g("Detail / quality") + ([extra] if extra else [])) or None}
    for s in d["subjects"]:
        if not s["action"]:
            s.pop("action")
    return json.dumps({k: v for k, v in d.items() if v}, indent=2, ensure_ascii=False)


def build(sel, profile, extra="", negative="", aspect="1:1", emphasis=False, mj=None):
    """Return dict(prompt, negative, settings, notes)."""
    sel = norm_sel(sel)
    extra = (extra or "").strip()
    fmt = profile.get("format", "natural")
    if fmt == "tags":
        prompt = _tags(sel, extra, profile, emphasis)
    elif fmt == "hybrid":
        prompt = _hybrid(sel, extra, profile, emphasis)
    elif fmt == "json":
        prompt = _json(sel, extra)
    else:
        prompt = _natural(sel, extra)
        if emphasis and sel.get("Subject") and profile.get("weighting") == "parens":
            prompt = prompt.replace(sel["Subject"][0], _weight(sel["Subject"][0], profile), 1)
    negative = (negative or "").strip()
    notes = []
    neg_out = ""
    mode = profile.get("negative", "optional")
    if negative:
        if mode in ("supported", "optional"):
            neg_out = negative
        elif mode == "limited":
            neg_out = negative
            notes.append("This model mostly ignores negative prompts – exclusions work better written into the prompt.")
        elif mode == "param_no":
            pass
        else:
            if profile.get("family") in ("OpenAI", "Google"):
                prompt += " Avoid: " + negative + "."
            else:
                notes.append("This model has no negative prompt – it was left out. Describe what you want instead.")
    if profile.get("param_style") == "midjourney":
        mj = dict(profile.get("params", {}), **(mj or {}))
        p = prompt.rstrip(".")
        p += f" --ar {aspect}" if aspect else ""
        if mj.get("stylize") not in (None, 100):
            p += f" --stylize {int(mj['stylize'])}"
        if mj.get("chaos"):
            p += f" --chaos {int(mj['chaos'])}"
        if mj.get("exp"):
            p += f" --exp {int(mj['exp'])}"
        if mj.get("raw"):
            p += " --raw"
        if mj.get("draft"):
            p += " --draft"
        if negative:
            p += " --no " + negative
        prompt = p + " --v 7"
        settings = ""
    else:
        res = profile.get("resolutions", {}).get(aspect, "")
        settings = (f"Size {res} ({aspect})" if res else f"Aspect {aspect}") + \
            (" · " + profile["settings"] if profile.get("settings") else "")
    return {"prompt": prompt, "negative": neg_out, "settings": settings, "notes": notes}


def as_text(res):
    out = res["prompt"]
    if res.get("negative"):
        out += "\n\nNegative prompt: " + res["negative"]
    if res.get("settings"):
        out += "\n\n" + res["settings"]
    return out


def randomize(sel, categories, items_by_cat, rng=None):
    rng = rng or random
    new = dict(norm_sel(sel))
    for cat in categories:
        if items_by_cat.get(cat):
            new[cat] = [rng.choice(items_by_cat[cat])]
    return new


def fill_template(template, values, items_by_cat, rng=None):
    rng = rng or random
    values = {k.lower(): v for k, v in (values or {}).items() if v}

    def rep(m):
        key = m.group(1).lower()
        if key in values:
            v = values[key]
            return ", ".join(v) if isinstance(v, list) else v
        cat = PLACEHOLDERS.get(key)
        if cat and items_by_cat.get(cat):
            return rng.choice(items_by_cat[cat])
        return m.group(0)
    return re.sub(r"\{(\w+)\}", rep, template)


def batch_variations(sel, categories, n, items_by_cat, profile, build_kwargs=None, seed=None):
    rng = random.Random(seed)
    build_kwargs = build_kwargs or {}
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 20:
        tries += 1
        p = build(randomize(sel, categories, items_by_cat, rng), profile, **build_kwargs)["prompt"]
        if p not in seen:
            seen.add(p); out.append(p)
    return out


def export_txt(prompts):
    return "\n\n".join(prompts) + "\n"


def export_csv(prompts):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "prompt"])
    for i, p in enumerate(prompts, 1):
        w.writerow([i, p])
    return buf.getvalue()


def parse_ai_list(text):
    items = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line).strip().strip('"')
        if len(line) > 15:
            items.append(line)
    return items


def extract_prompt(text):
    m = re.findall(r"<prompt>(.*?)</prompt>", text, re.S | re.I)
    return m[-1].strip() if m else None


def parse_json_loose(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("No JSON object in reply")
    return json.loads(m.group(0))


def analysis_to_selection(data, known_cats):
    lower = {c.lower(): c for c in known_cats}
    lower.update({"action": "Action / pose", "color": "Color palette", "colour palette": "Color palette",
                  "artist": "Artist influence", "detail": "Detail / quality", "time": "Time & weather",
                  "movement": "Art movement", "quality": "Detail / quality"})
    sel = {}
    for k, v in (data or {}).items():
        cat = lower.get(str(k).lower().strip())
        if not cat:
            continue
        vals = [v] if isinstance(v, str) else [str(x) for x in (v or []) if x]
        vals = [x.strip() for x in vals if x.strip()]
        if vals:
            sel[cat] = vals
    return sel
