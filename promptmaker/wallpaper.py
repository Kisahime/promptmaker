"""5.2 Wallpaper mode: pick a screen size, get a ~1 MP base size in the screen's aspect, a hires-fix scale and a
final step (Forge upscaler or Lanczos resize + centre crop) so the saved image is exactly the screen size."""
import math
import os
import sys

PRESETS = [("1920×1080 (Full HD)", 1920, 1080), ("2560×1440 (QHD)", 2560, 1440), ("3840×2160 (4K)", 3840, 2160),
           ("2560×1080 (ultrawide)", 2560, 1080), ("3440×1440 (ultrawide)", 3440, 1440), ("1080×1920 (phone)", 1080, 1920)]

# family -> (size multiple, base megapixels). SD / Illustrious / Pony and Anima prefer 64 px buckets around 1 MP but
# accept any multiple of 8, so an exact-aspect size (1280×720 for 16:9) wins over a 64 bucket that would be cropped.
# FLUX / Qwen / HiDream / MOSS need multiples of 16 and are kept at ~1 MP so 8 GB cards cope.
FAMILY_GRID = {"Stable Diffusion": (8, 1.0), "Generic": (8, 1.0), "Anima": (8, 1.0), "FLUX": (16, 1.0),
               "Qwen": (16, 1.0), "HiDream": (16, 1.0), "MOSS": (16, 1.0)}
ASPECT_TOL = 0.001  # aspect errors under 0.1 % count as exact
CLOUD_FAMILIES = {"Midjourney", "OpenAI", "Google"}
MAX_HIRES = 2.0        # never ask the backend for more than ×2 in one hires pass
SAFE_HIRES = 1.5       # when more is needed (4K), hires ×1.5 then a final upscale – VRAM friendly on 8 GB
MP = 1024 * 1024


def grid_for(family):
    return FAMILY_GRID.get(family or "", (8, 1.0))


def base_size(tw, th, multiple=8, mp=1.0, lo=0.78, hi=1.12):
    """Base size (multiples of `multiple`) close to `mp` megapixels whose aspect best matches tw:th.
    Ties prefer a size the target is a clean ×0.05 multiple of (1920×1080 → 1280×720 ×1.5, no crop),
    then multiples of 64, then the size closest to `mp`."""
    tw, th = int(tw), int(th)
    if tw <= 0 or th <= 0:
        raise ValueError("Width and height must be positive")
    aspect = tw / th
    best = None
    for w in range(256, 4097, multiple):
        for h in (math.floor(w / aspect / multiple) * multiple, math.ceil(w / aspect / multiple) * multiple):
            if h < 256 or not lo * mp * MP <= w * h <= hi * mp * MP:
                continue
            err = abs(math.log((w / h) / aspect))
            clean = abs(tw / w * 20 - round(tw / w * 20)) < 1e-6 and abs(th / h * 20 - round(th / h * 20)) < 1e-6
            score = (0 if err < ASPECT_TOL else round(err, 4), not clean, (w % 64 > 0) + (h % 64 > 0), abs(math.log(w * h / (mp * MP))))
            if best is None or score < best[0]:
                best = (score, w, h)
    if best is None:  # extreme aspect: fall back to the nearest bucket with the long side capped
        s = math.sqrt(mp * MP / (tw * th))
        return (max(multiple, round(tw * s / multiple) * multiple), max(multiple, round(th * s / multiple) * multiple))
    return best[1], best[2]


def _up(w, h, s):
    """Size after a hires pass (rounded to 8 like the backends)."""
    return max(64, int(round(w * s / 8)) * 8), max(64, int(round(h * s / 8)) * 8)


def plan(tw, th, family="Stable Diffusion", max_hires=MAX_HIRES):
    """Everything needed to make an exact tw×th wallpaper:
    base (w,h), hires scale, size after hires, extra upscale factor (1 = none) and the final crop/resize."""
    tw, th = int(tw), int(th)
    if family in CLOUD_FAMILIES:
        raise ValueError(f"{family} is a cloud model – Wallpaper mode needs Forge or ComfyUI")
    mult, mp = grid_for(family)
    bw, bh = base_size(tw, th, mult, mp)
    need = max(tw / bw, th / bh)
    if need <= 1.0:
        hires = 1.0
    elif need <= max_hires + 1e-9:
        hires = math.ceil(need * 20 - 1e-9) / 20  # 0.05 steps, at or just over the target
        while min(a / b for a, b in zip(_up(bw, bh, hires), (tw, th))) < 1:
            hires = round(hires + 0.05, 2)
    else:
        hires = SAFE_HIRES
    hw, hh = _up(bw, bh, hires) if hires > 1 else (bw, bh)
    extra = max(tw / hw, th / hh)
    extra = 1.0 if extra <= 1.0 else math.ceil(extra * 20 - 1e-9) / 20
    ow, oh = (math.ceil(hw * extra), math.ceil(hh * extra)) if extra > 1 else (hw, hh)
    return {"target": (tw, th), "base": (bw, bh), "hires": hires, "after_hires": (hw, hh), "upscale": extra,
            "before_crop": (ow, oh), "crop": (ow - tw, oh - th), "family": family, "multiple": mult}


def describe(p):
    bw, bh = p["base"]; hw, hh = p["after_hires"]; tw, th = p["target"]
    s = f"{bw}×{bh}"
    if p["hires"] > 1:
        s += f" → hires ×{p['hires']:g} = {hw}×{hh}"
    if p["upscale"] > 1:
        s += f" → upscale ×{p['upscale']:g}"
    return s + f" → {tw}×{th}"


# ------------------------------------------------------------------ composition
SIDES = {"left": "right", "right": "left"}


def composition(side, fmt="tags"):
    """Icon-safe composition text for a model's prompt format (tags / hybrid / natural / json)."""
    if side not in ("left", "right", "center"):
        return ""
    if side == "center":
        tags = "wide shot, scenery, centered, symmetrical composition, negative space"
        nl = ("Wide landscape composition with the subject small in the centre of the frame, "
              "open uncluttered space on both sides.")
    else:
        other = SIDES[side]
        tags = f"wide shot, scenery, negative space, character on {side} side, empty {other} side"
        nl = (f"Wide landscape composition with the subject placed on the {side} third of the frame, "
              f"leaving the {other} side open and uncluttered with sky and scenery.")
    if fmt == "tags":
        return tags
    if fmt == "hybrid":
        return tags + ". " + nl
    return nl


def add_composition(prompt, side, fmt="tags"):
    """Append the composition text in the prompt's style. Hybrid (Anima): tags join the tag block, the sentence
    goes after any natural-language sentences."""
    prompt = (prompt or "").strip()
    extra = composition(side, fmt)
    if not extra or composition(side, "tags" if fmt != "natural" else "natural") in prompt:
        return prompt
    if fmt == "tags":
        return f"{prompt.rstrip(', ')}, {extra}" if prompt else extra
    if fmt == "hybrid":
        tags, nl = composition(side, "tags"), composition(side, "natural")
        head, dot, tail = prompt.partition(". ")
        if not prompt:
            return f"{tags}. {nl}"
        if dot:
            return f"{head.rstrip(', ')}, {tags}. {tail.strip()} {nl}"
        return f"{prompt.rstrip(', .')}, {tags}. {nl}"
    return f"{prompt} {extra}" if prompt else extra


# ------------------------------------------------------------------ final image
def fit_png(png, tw, th):
    """Scale to cover tw×th (Lanczos with OpenCV, else Qt smooth) and centre-crop to exactly tw×th. Returns PNG."""
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
        h, w = img.shape[:2]
        s = max(tw / w, th / h)
        nw, nh = max(tw, math.ceil(w * s)), max(th, math.ceil(h * s))
        if (nw, nh) != (w, h):
            img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4 if s > 1 else cv2.INTER_AREA)
        x, y = (nw - tw) // 2, (nh - th) // 2
        ok, buf = cv2.imencode(".png", img[y:y + th, x:x + tw])
        return buf.tobytes()
    except ImportError:
        pass
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage
    im = QImage(); im.loadFromData(png)
    im = im.scaled(tw, th, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    im = im.copy((im.width() - tw) // 2, (im.height() - th) // 2, tw, th)
    ba = QByteArray(); b = QBuffer(ba); b.open(QIODevice.WriteOnly); im.save(b, "PNG")
    return bytes(ba)


def wallpaper_dir(data_dir):
    d = os.path.join(data_dir, "Wallpapers")
    os.makedirs(d, exist_ok=True)
    return d


def save(png, data_dir, tw, th, seed=0):
    import time
    path = os.path.join(wallpaper_dir(data_dir), f"wallpaper_{tw}x{th}_{time.strftime('%Y%m%d_%H%M%S')}_{seed}.png")
    with open(path, "wb") as f:
        f.write(png)
    return path


def can_set_desktop():
    return sys.platform == "win32"


def set_desktop(path):
    """Windows only: set the desktop wallpaper (SPI_SETDESKWALLPAPER, saved to the profile and broadcast)."""
    if not can_set_desktop():
        raise OSError("Setting the desktop wallpaper is only supported on Windows")
    import ctypes
    ok = ctypes.windll.user32.SystemParametersInfoW(20, 0, os.path.abspath(path), 0x01 | 0x02)
    if not ok:
        raise OSError("Windows refused to set the wallpaper")
    return True
