"""Inpainting and regional prompts for Forge/A1111 and ComfyUI.

Inpaint: a base image plus a white-on-black mask go to /sdapi/v1/img2img (Forge) or to a
LoadImage → VAEEncode → SetLatentNoiseMask chain (ComfyUI).

Regions: rectangles (normalised 0–1) each with their own prompt.
  * Forge/A1111: needs a regional-prompt extension – Forge has none built in. We use **Forge Couple**
    (sd-forge-couple, "Advanced" mode) when /sdapi/v1/scripts lists it; otherwise the caller gets a clear
    message and can fall back to a single prompt with position words.
  * ComfyUI: built in – CLIPTextEncode → ConditioningSetArea per region, merged with ConditioningCombine.
"""
import copy

FORGE_COUPLE = "forge couple"
FORGE_COUPLE_URL = "https://github.com/Haoming02/sd-forge-couple"
NEEDS_EXTENSION = ("Regional prompts on Forge need the free Forge Couple extension (sd-forge-couple). Install it from "
                   "Forge → Extensions → Install from URL: " + FORGE_COUPLE_URL + " , then restart Forge. "
                   "ComfyUI needs nothing extra.")
INPAINT_AREAS = {"Whole picture": False, "Only masked": True}
FILL_MODES = ["fill", "original", "latent noise", "latent nothing"]


# ---------------------------------------------------------------- regions model
def clamp_region(r):
    x, y = min(max(float(r.get("x", 0)), 0.0), 1.0), min(max(float(r.get("y", 0)), 0.0), 1.0)
    w, h = min(max(float(r.get("w", 1)), 0.01), 1.0 - x), min(max(float(r.get("h", 1)), 0.01), 1.0 - y)
    return {"prompt": (r.get("prompt") or "").strip(), "x": x, "y": y, "w": max(w, 0.01), "h": max(h, 0.01),
            "weight": float(r.get("weight", 1.0) or 1.0)}


def valid_regions(regions):
    return [clamp_region(r) for r in regions or [] if (r.get("prompt") or "").strip()]


def _side(c, lo="left", hi="right"):
    return lo if c < 0.38 else hi if c > 0.62 else "center"


def position_words(r):
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    v = {"left": "top", "right": "bottom", "center": "middle"}[_side(cy)]
    hpos = _side(cx)
    if v == "middle":
        return "center" if hpos == "center" else f"on the {hpos}"
    return f"{v}" if hpos == "center" else f"{v} {hpos}"


def plain_prompt(base, regions):
    """Fallback without any regional support: one prompt with 'on the left: …' hints."""
    parts = [base.strip()] if base and base.strip() else []
    parts += [f"({r['prompt']}) {position_words(r)}" for r in valid_regions(regions)]
    return ", ".join(parts)


# ---------------------------------------------------------------- Forge / A1111
def detect_forge_regional(scripts):
    """scripts = GET /sdapi/v1/scripts. Returns the supported script name or ''."""
    names = [str(n).lower() for n in (scripts or {}).get("txt2img") or []]
    return FORGE_COUPLE if FORGE_COUPLE in names else ""


def forge_couple(payload, base, regions, base_weight=0.2, repeat_base=True):
    """Advanced mode: line 1 = global prompt over the whole image (so every pixel has weight), then one line per region."""
    regs = valid_regions(regions)
    if not regs:
        raise ValueError("Add at least one region with a prompt")
    b = (base or "").replace("\n", " ").strip()
    # Attention couple works much better when every region line carries the shared scene/count tags
    # (e.g. "2girls, beach"); otherwise each region is read as a full single-subject image.
    lines = [b or "high quality"] + [(f"{b}, " if (repeat_base and b) else "") + r["prompt"].replace("\n", " ") for r in regs]
    mapping = [[0.0, 1.0, 0.0, 1.0, float(base_weight)]] + \
        [[round(r["x"], 4), round(r["x"] + r["w"], 4), round(r["y"], 4), round(r["y"] + r["h"], 4), r["weight"]] for r in regs]
    payload["prompt"] = "\n".join(lines)
    payload.setdefault("alwayson_scripts", {})[FORGE_COUPLE] = {
        "args": [True, True, "Advanced", "\n", None, None, None, mapping, "{ }", False, True, None, None, None, None, None, None]}
    return payload


def forge_inpaint(payload, image_b64, mask_b64, denoise=0.75, mask_blur=4, only_masked=True, padding=32, fill="original"):
    payload.update({"init_images": [image_b64], "mask": mask_b64, "denoising_strength": float(denoise),
                    "mask_blur": int(mask_blur), "inpainting_fill": FILL_MODES.index(fill) if fill in FILL_MODES else 1,
                    "inpaint_full_res": bool(only_masked), "inpaint_full_res_padding": int(padding),
                    "inpainting_mask_invert": 0, "resize_mode": 0})
    return payload


# ---------------------------------------------------------------- ComfyUI
def _new_ids(wf, n):
    ids = [int(k) for k in wf if str(k).isdigit()]
    start = max(ids or [0]) + 200
    return [str(start + i) for i in range(n)]


def _samplers(wf):
    s = [k for k, n in wf.items() if isinstance(n, dict) and n.get("class_type") in ("KSampler", "KSamplerAdvanced")]
    if not s:
        raise ValueError("This workflow has no KSampler node")
    return s


def _clip_source(wf, sampler):
    """Find the CLIP output feeding the sampler's positive CLIPTextEncode (walks through simple conditioning nodes)."""
    ref, seen = wf[sampler]["inputs"].get("positive"), set()
    while isinstance(ref, list) and ref[0] not in seen:
        seen.add(ref[0]); node = wf.get(ref[0], {})
        ins = node.get("inputs", {})
        if "clip" in ins:
            return ins["clip"]
        ref = ins.get("conditioning") or ins.get("positive") or ins.get("conditioning_1")
    for n in wf.values():
        if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode":
            return n["inputs"]["clip"]
    raise ValueError("Couldn't find the CLIP text encoder in this workflow")


def _px(v, total):
    return max(0, min(int(round(v * total / 8.0)) * 8, total))


def add_comfy_regions(workflow, regions, width, height):
    wf = copy.deepcopy(workflow)
    regs = valid_regions(regions)
    if not regs:
        raise ValueError("Add at least one region with a prompt")
    for s in _samplers(wf):
        clip = _clip_source(wf, s)
        ins = wf[s]["inputs"]
        cond = ins["positive"]
        ids = _new_ids(wf, 3 * len(regs))
        for i, r in enumerate(regs):
            enc, area, comb = ids[3 * i:3 * i + 3]
            wf[enc] = {"class_type": "CLIPTextEncode", "inputs": {"text": r["prompt"], "clip": clip}}
            wf[area] = {"class_type": "ConditioningSetArea",
                        "inputs": {"conditioning": [enc, 0], "width": max(64, _px(r["w"], width)), "height": max(64, _px(r["h"], height)),
                                   "x": _px(r["x"], width), "y": _px(r["y"], height), "strength": float(r["weight"])}}
            wf[comb] = {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": cond, "conditioning_2": [area, 0]}}
            cond = [comb, 0]
        ins["positive"] = cond
    return wf


def add_comfy_inpaint(workflow, image_name, denoise=0.75, grow=6):
    """Replace the empty latent with the uploaded image (its alpha channel is the mask: transparent = repaint)."""
    wf = copy.deepcopy(workflow)
    samplers = _samplers(wf)
    vae = next((n["inputs"]["vae"] for n in wf.values() if isinstance(n, dict) and n.get("class_type") == "VAEDecode"), None)
    if not vae:
        raise ValueError("This workflow has no VAEDecode node, so inpainting can't find the VAE")
    load, enc, grow_id, noise = _new_ids(wf, 4)
    wf[load] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf[enc] = {"class_type": "VAEEncode", "inputs": {"pixels": [load, 0], "vae": vae}}
    wf[grow_id] = {"class_type": "GrowMask", "inputs": {"mask": [load, 1], "expand": int(grow), "tapered_corners": True}}
    wf[noise] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": [enc, 0], "mask": [grow_id, 0]}}
    for s in samplers:
        wf[s]["inputs"]["latent_image"] = [noise, 0]
        if "denoise" in wf[s]["inputs"]:
            wf[s]["inputs"]["denoise"] = float(denoise)
    return wf


# ---------------------------------------------------------------- image helpers (Qt, no QApplication needed)
def _qimage(png):
    from PySide6.QtGui import QImage
    img = QImage.fromData(png)
    if img.isNull():
        raise ValueError("Couldn't read the image")
    return img


def _png(img):
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    return bytes(buf.data())


def comfy_masked_png(image_png, mask_png):
    """RGBA PNG for ComfyUI's LoadImage: alpha 0 where the mask is white (LoadImage's MASK = 1 - alpha)."""
    from PySide6.QtGui import QImage, QPainter
    img = _qimage(image_png).convertToFormat(QImage.Format_ARGB32)
    mask = _qimage(mask_png).scaled(img.width(), img.height()).convertToFormat(QImage.Format_Grayscale8)
    alpha = QImage(mask.constBits(), mask.width(), mask.height(), mask.bytesPerLine(), QImage.Format_Alpha8).copy()
    p = QPainter(img); p.setCompositionMode(QPainter.CompositionMode_DestinationOut); p.drawImage(0, 0, alpha); p.end()
    return _png(img)


def mask_coverage(mask_png):
    """Fraction of white pixels (sampled), 0..1 – used to refuse an empty mask."""
    from PySide6.QtGui import QColor
    m = _qimage(mask_png)
    step = max(1, min(m.width(), m.height()) // 64)
    tot = hit = 0
    for y in range(0, m.height(), step):
        for x in range(0, m.width(), step):
            tot += 1; hit += QColor(m.pixel(x, y)).red() > 127
    return hit / max(tot, 1)
