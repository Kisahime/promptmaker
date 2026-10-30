"""5.0 Characters: a saved person with reference images, named outfits, linked LoRAs, trigger words and
per-target-model tag sets, inserted the same way into any prompt or region so they stay consistent.

Stored in the existing `characters` table; everything new lives in its JSON `extra` column, so 4.x Presets keep
working on the same rows (appearance / outfit / lora / ref_image stay the "default" values)."""
import base64
import json
import os
import re

from .presets import _parts, dedupe

EXTRA_DEFAULTS = {"outfits": [], "refs": [], "loras": [], "triggers": "", "tagsets": {}, "default_outfit": "",
                  "use_reference": False, "ref_weight": 0.7, "autotag": True}


def extra(char):
    """The 5.0 fields of a character row, with defaults filled in."""
    raw = (char or {}).get("extra") or "{}"
    try:
        d = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError):
        d = {}
    out = {k: (json.loads(json.dumps(v))) for k, v in EXTRA_DEFAULTS.items()}
    out.update({k: v for k, v in d.items() if k in EXTRA_DEFAULTS})
    return out


def outfits(char):
    """Named outfits; the legacy single `outfit` text appears as 'Default' when no outfits are saved."""
    ex = extra(char)
    outs = [o for o in ex["outfits"] if isinstance(o, dict) and o.get("name")]
    if not outs and (char or {}).get("outfit", "").strip():
        outs = [{"name": "Default", "tags": char["outfit"]}]
    return outs


def outfit_tags(char, outfit=None):
    outs = outfits(char)
    name = outfit if outfit is not None else extra(char).get("default_outfit", "")
    if name == "":
        return outs[0]["tags"] if outs else ""
    if name in (None, "none", "(none)"):
        return ""
    hit = next((o for o in outs if o["name"].lower() == str(name).lower()), None)
    return hit["tags"] if hit else (outs[0]["tags"] if outs else "")


def loras(char):
    """[(name, weight)] – the 5.0 list plus the legacy single LoRA field."""
    out = [(l.get("name", "").strip(), float(l.get("weight", 0.8) or 0.8)) for l in extra(char)["loras"] if isinstance(l, dict)]
    if char.get("lora") and char["lora"].strip() not in [n for n, _ in out]:
        out.insert(0, (char["lora"].strip(), float(char.get("lora_weight") or 0.8)))
    return [(n, w) for n, w in out if n]


def references(char):
    refs = [r for r in extra(char)["refs"] if r]
    if char.get("ref_image") and char["ref_image"] not in refs:
        refs.insert(0, char["ref_image"])
    return [r for r in refs if os.path.exists(r)]


def _target_key(profile):
    return ((profile or {}).get("id") or (profile or {}).get("name") or "").lower()


def tags_for(char, profile=None):
    """Appearance tags for the target model: its own tag set if one is saved for that model/family, else the default."""
    ts = {str(k).lower(): v for k, v in extra(char)["tagsets"].items() if str(v).strip()}
    p = profile or {}
    for key in (_target_key(p), (p.get("family") or "").lower(), (p.get("base") or "").lower()):
        if key and key in ts:
            return ts[key]
    return char.get("appearance", "")


def character_text(char, outfit=None, profile=None, with_lora=True, with_triggers=True):
    """The text that stands for this character + outfit in a prompt or a region."""
    ex = extra(char)
    parts = (_parts(ex["triggers"]) if with_triggers else []) + _parts(tags_for(char, profile)) + _parts(outfit_tags(char, outfit))
    parts = dedupe(parts)
    natural = (profile or {}).get("format") == "natural"
    if natural and parts:
        body = f"{char['name']}, " + ", ".join(parts)
    else:
        body = ", ".join(parts) or char.get("name", "")
    if with_lora:
        for n, w in loras(char):
            body += f", <lora:{n}:{w:g}>"
    return body


LORA_RE = re.compile(r"<lora:[^>]+>")


def insert(prompt, char, outfit=None, profile=None):
    """Put the character at the front of a prompt, once. Re-inserting replaces the previous text for that character
    (marked by its trigger/first tag) instead of piling it up. LoRA tags go at the end, deduplicated."""
    body = character_text(char, outfit, profile, with_lora=False)
    lo = [f"<lora:{n}:{w:g}>" for n, w in loras(char)]
    rest = [p for p in _parts(LORA_RE.sub("", prompt or ""))]
    mine = {p.lower() for p in _parts(body)}
    # drop previous tags of this character (any outfit) so swapping outfits is clean
    old = set()
    for o in outfits(char):
        old |= {t.lower() for t in _parts(o.get("tags"))}
    old |= {t.lower() for t in _parts(tags_for(char, profile)) + _parts(extra(char)["triggers"])}
    rest = [p for p in rest if p.lower() not in mine and p.lower() not in old]
    existing_lo = LORA_RE.findall(prompt or "")
    tail = dedupe(existing_lo + lo)
    return ", ".join([body] + rest) + ("" if not tail else " " + " ".join(tail))


def region(char, outfit=None, profile=None, x=0.0, y=0.0, w=0.5, h=1.0, weight=1.0):
    """A region dict (regions.py format) for this character, without LoRA tags (those go on the base prompt)."""
    return {"prompt": character_text(char, outfit, profile, with_lora=False), "x": x, "y": y, "w": w, "h": h,
            "weight": weight, "character": char.get("name", "")}


# ------------------------------------------------------------------ reference image (IP-Adapter) support
IPADAPTER_HINTS = ("ip-adapter", "ip_adapter", "ipadapter")


def ipadapter_models(controlnet_models):
    return [m for m in (controlnet_models or []) if any(h in m.lower() for h in IPADAPTER_HINTS)]


def detect_reference_support(backend):
    """('forge', model) when Forge/A1111 has an IP-Adapter ControlNet model, ('comfy', '') when ComfyUI has the
    IPAdapter nodes, else (None, reason). Never raises."""
    try:
        from .imagegen import A1111
        if isinstance(backend, A1111):
            ms = ipadapter_models(backend.controlnet_models())
            if ms:
                sdxl = [m for m in ms if "xl" in m.lower()]
                return "forge", (sdxl or ms)[0]
            return None, "no IP-Adapter ControlNet model in Forge"
        from .imagegen import _http
        info = _http(backend.url + "/object_info/IPAdapterUnifiedLoader", timeout=8)
        if isinstance(info, dict) and info:
            return "comfy", ""
        return None, "ComfyUI_IPAdapter_plus not installed"
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:120]


def forge_reference_unit(image_png, model, weight=0.7):
    from .pose import forge_unit
    u = forge_unit(base64.b64encode(image_png).decode(), model, weight)
    u["module"] = "InsightFace+CLIP-H (IPAdapter)" if "faceid" in model.lower() else "CLIP-ViT-H (IPAdapter)"
    u["control_mode"] = "Balanced"
    return u


def add_forge_reference(payload, image_png, model, weight=0.7):
    """Append an IP-Adapter unit next to any ControlNet unit already in the payload."""
    cn = payload.setdefault("alwayson_scripts", {}).setdefault("controlnet", {"args": []})
    cn["args"].append(forge_reference_unit(image_png, model, weight))
    return payload


def add_comfy_reference(workflow, image_name, weight=0.7, preset="PLUS (high strength)"):
    """IPAdapterUnifiedLoader + IPAdapter between the checkpoint's MODEL and every KSampler (ComfyUI_IPAdapter_plus)."""
    import copy
    wf = copy.deepcopy(workflow)
    samplers = [k for k, n in wf.items() if isinstance(n, dict) and n.get("class_type") in ("KSampler", "KSamplerAdvanced")]
    if not samplers:
        raise ValueError("This workflow has no KSampler node")
    nxt = max([int(k) for k in wf if str(k).isdigit()] or [0]) + 200
    model_src = wf[samplers[0]]["inputs"]["model"]
    li, ld, ap = str(nxt), str(nxt + 1), str(nxt + 2)
    wf[ld] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf[li] = {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": model_src, "preset": preset}}
    wf[ap] = {"class_type": "IPAdapter", "inputs": {"model": [li, 0], "ipadapter": [li, 1], "image": [ld, 0],
                                                    "weight": float(weight), "start_at": 0.0, "end_at": 1.0, "weight_type": "standard"}}
    for s in samplers:
        wf[s]["inputs"]["model"] = [ap, 0]
    return wf


# ------------------------------------------------------------------ auto-tagging gallery images (Ollama vision)
def tag_messages(image_png, chars):
    lines = []
    for c in chars:
        refs = tags_for(c) or c.get("appearance", "")
        lines.append(f"- {c['name']}: {refs}; outfits: " + "; ".join(o['tags'] for o in outfits(c)))
    return [{"role": "system", "content": "You identify recurring characters in images. You are given a list of known "
             "characters with their appearance tags. Reply only with JSON: {\"characters\": [names that clearly appear], "
             "\"outfit\": {name: outfit name or \"\"}}. Use exact names from the list; [] if none match."},
            {"role": "user", "content": "Known characters:\n" + "\n".join(lines) + "\n\nWho appears in this image?",
             "images": [base64.b64encode(image_png).decode()]}]


def parse_tags(text, chars):
    names = {c["name"].lower(): c["name"] for c in chars}
    try:
        m = re.search(r"\{.*\}", text or "", re.S)
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    found = d.get("characters") if isinstance(d, dict) else None
    if not isinstance(found, list):
        found = [n for k, n in names.items() if re.search(r"\b" + re.escape(k) + r"\b", (text or "").lower())]
    return [names[str(f).lower()] for f in found if str(f).lower() in names]


def from_prompt(prompt, chars):
    """Cheap tagging with no AI: a character is in the image if its trigger word (or a LoRA of its) is in the prompt."""
    p = (prompt or "").lower()
    hits = []
    for c in chars:
        trig = [t.lower() for t in _parts(extra(c)["triggers"])]
        los = [n.lower() for n, _ in loras(c)]
        if any(t and t in p for t in trig) or any(f"<lora:{n}:" in p for n in los):
            hits.append(c["name"])
    return hits
