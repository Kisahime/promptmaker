"""5.1 Face Swap – our take on Fooocus' "FaceSwap" image prompt.

How Fooocus does it (modules/flags.py, extras/face_crop.py, modules/async_worker.py, modules/config.py):
  * model: ip-adapter-plus-face_sdxl_vit-h + the CLIP ViT-H image encoder (plus Fooocus' own negative IP embedding);
  * the source image is face-aligned first (facexlib RetinaFace, 5 landmarks warped onto the FFHQ 512 template),
    then resized to 224×224 for CLIP – so the adapter sees one big, centred face;
  * defaults: stop at 0.9, weight 0.75 (plain Image Prompt is 0.5 / 0.6);
  * it does NOT mask anything itself – for swapping into an existing picture you inpaint, and the inpaint mask
    decides what is redrawn.

What we add: a source crop with a configurable hair margin (the FFHQ crop cuts most of the hair off), and an
automatic face + hair mask on the target (face detector → head ellipse sized for the hair length → optional
GrabCut edge refine → grow → feather) that can be fixed with a brush before inpainting.
Pure helpers here (numpy/OpenCV optional); the page lives in v5ui.FaceSwapPage.
"""
import base64
import copy
import os
import urllib.request

STOP_AT, WEIGHT = 0.9, 0.75        # Fooocus flags.default_parameters[cn_ip_face]
DENOISE = 0.8                      # SDXL without Fooocus' inpaint patch needs < 1.0 to keep the head shape/pose
HAIR_MARGIN = 2.2                  # source crop side = face box × this (Fooocus' FFHQ crop ≈ 1.6, mostly no hair)
HAIR_LENGTHS = {"Short": 0.15, "Medium": 0.55, "Long": 1.1}   # how far the mask runs below the chin at the sides
MODES = ("generate", "swap")

# ------------------------------------------------------------------ models
HF = "https://huggingface.co/h94/IP-Adapter/resolve/main/"
MODELS = {
    "plus_face": {"file": "ip-adapter-plus-face_sdxl_vit-h.safetensors", "url": HF + "sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors",
                  "label": "IP-Adapter Plus Face SDXL (what Fooocus uses)"},
    "faceid_v2": {"file": "ip-adapter-faceid-plusv2_sdxl.bin",
                  "url": "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin",
                  "label": "IP-Adapter FaceID Plus v2 SDXL (optional, needs insightface)"},
    "clip_h": {"file": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors", "url": HF + "models/image_encoder/model.safetensors",
               "label": "CLIP ViT-H image encoder (ComfyUI only – Forge downloads its own)"},
}
FORGE_MODULE = {"plus_face": "CLIP-ViT-H (IPAdapter)", "plus": "CLIP-ViT-H (IPAdapter)", "faceid_v2": "InsightFace+CLIP-H (IPAdapter)"}
COMFY_PRESET = {"plus_face": "PLUS FACE (portraits)", "faceid_v2": "FACEID PLUS V2", "plus": "PLUS (high strength)"}
UNSUPPORTED_FAMILIES = ("anima", "flux", "sd3", "wan", "hunyuan", "qwen", "chroma", "lumina")


def classify(name):
    """'plus_face' | 'faceid_v2' | 'faceid' | 'plus' | 'other' | '' for a ControlNet/IP-Adapter file name."""
    n = (name or "").lower().replace("_", "-")
    if not any(h in n for h in ("ip-adapter", "ipadapter")):
        return ""
    if "faceid" in n:
        return "faceid_v2" if "plusv2" in n or "plus-v2" in n else "faceid"
    if "plus-face" in n or "plusface" in n or "full-face" in n:
        return "plus_face"
    if "plus" in n:
        return "plus"
    return "other"


def is_sdxl(name):
    n = (name or "").lower()
    return "xl" in n or "sdxl" in n


def pick_model(models):
    """Best face adapter from a list of model names: (name, kind) – Plus Face SDXL first, like Fooocus."""
    order = ("plus_face", "faceid_v2", "plus", "faceid", "other")
    found = [(m, classify(m)) for m in (models or []) if classify(m)]
    for want in order:
        for sd in (True, False):
            for m, k in found:
                if k == want and is_sdxl(m) == sd:
                    return m, k
    return "", ""


def family_warning(profile):
    fam = ((profile or {}).get("family") or (profile or {}).get("id") or (profile or {}).get("name") or "").lower()
    if any(f in fam for f in UNSUPPORTED_FAMILIES):
        return ("Face Swap needs an SDXL / Illustrious / Pony checkpoint – the SDXL face IP-Adapter doesn't work with "
                "Anima, Flux or other non-SDXL models. Switch the target model first.")
    return ""


def install_help(backend_kind, forge_dir=r"C:\AI\sd-webui-forge-classic", comfy_dir=r"ComfyUI"):
    """Plain-text install steps for the missing face models."""
    m = MODELS
    if backend_kind == "comfy":
        return ("ComfyUI needs the ComfyUI_IPAdapter_plus custom node (Manager → search 'IPAdapter plus') and:\n"
                f"• {m['plus_face']['url']}\n   → {comfy_dir}\\models\\ipadapter\\{m['plus_face']['file']}\n"
                f"• {m['clip_h']['url']}\n   → {comfy_dir}\\models\\clip_vision\\{m['clip_h']['file']}  (rename it to exactly this)\n"
                "Restart ComfyUI, then press ⟳ Check models.")
    return ("Forge needs the face IP-Adapter in its ControlNet folder:\n"
            f"• {m['plus_face']['url']}\n   → {forge_dir}\\models\\ControlNet\\{m['plus_face']['file']}\n"
            "Restart Forge, then press ⟳ Check models. The CLIP-H image encoder is downloaded by Forge itself the "
            "first time (about 2.5 GB, so the first swap is slow).\n"
            f"Optional, stronger likeness on realistic faces: {m['faceid_v2']['url']} → models\\ControlNet, plus "
            "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors "
            "→ models\\Lora (needs insightface in Forge's venv).")


def detect(backend):
    """{'kind': 'forge'|'comfy'|None, 'model', 'type', 'models', 'problem'} – never raises."""
    out = {"kind": None, "model": "", "type": "", "models": [], "problem": ""}
    if backend is None:
        out["problem"] = "No image backend – set up Forge or ComfyUI in Settings."
        return out
    try:
        from .imagegen import A1111, _http
        if isinstance(backend, A1111):
            ms = [m for m in backend.controlnet_models() if classify(m)]
            out.update(kind="forge", models=ms)
            out["model"], out["type"] = pick_model(ms)
            if not ms:
                out["problem"] = "No IP-Adapter model in Forge's models\\ControlNet folder."
            elif out["type"] not in ("plus_face", "faceid_v2"):
                out["problem"] = "Only a general IP-Adapter was found – faces work much better with Plus Face."
            return out
        out["kind"] = "comfy"
        info = _http(backend.url + "/object_info/IPAdapterModelLoader", timeout=8)
        if not (isinstance(info, dict) and info):
            out["problem"] = "ComfyUI_IPAdapter_plus is not installed."
            return out
        try:
            files = info["IPAdapterModelLoader"]["input"]["required"]["ipadapter_file"][0]
        except (KeyError, IndexError, TypeError):
            files = []
        out["models"] = [f for f in files if classify(f)]
        out["model"], out["type"] = pick_model(out["models"])
        if out["type"] not in ("plus_face", "faceid_v2"):
            out["problem"] = "No ip-adapter-plus-face_sdxl_vit-h model in ComfyUI\\models\\ipadapter."
        return out
    except Exception as e:  # noqa: BLE001
        out["problem"] = str(e)[:160]
        return out


# ------------------------------------------------------------------ backend payloads
def forge_unit(face_png, model, weight=WEIGHT, stop_at=STOP_AT, kind=""):
    kind = kind or classify(model)
    return {"enabled": True, "image": base64.b64encode(face_png).decode(), "module": FORGE_MODULE.get(kind, "CLIP-ViT-H (IPAdapter)"),
            "model": model, "weight": float(weight), "resize_mode": "Crop and Resize", "control_mode": "Balanced",
            "pixel_perfect": False, "processor_res": 512, "guidance_start": 0.0, "guidance_end": float(stop_at)}


def add_forge_face(payload, face_png, model, weight=WEIGHT, stop_at=STOP_AT, kind=""):
    cn = payload.setdefault("alwayson_scripts", {}).setdefault("controlnet", {"args": []})
    cn["args"].append(forge_unit(face_png, model, weight, stop_at, kind))
    return payload


def add_comfy_face(workflow, image_name, weight=WEIGHT, stop_at=STOP_AT, kind="plus_face"):
    """IPAdapterUnifiedLoader (face preset) + IPAdapter (end_at = stop_at) in front of every KSampler."""
    wf = copy.deepcopy(workflow)
    samplers = [k for k, n in wf.items() if isinstance(n, dict) and n.get("class_type") in ("KSampler", "KSamplerAdvanced")]
    if not samplers:
        raise ValueError("This workflow has no KSampler node")
    nxt = max([int(k) for k in wf if str(k).isdigit()] or [0]) + 300
    li, ld, ap = str(nxt), str(nxt + 1), str(nxt + 2)
    src = wf[samplers[0]]["inputs"]["model"]
    faceid = kind == "faceid_v2"
    wf[ld] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf[li] = {"class_type": "IPAdapterUnifiedLoaderFaceID" if faceid else "IPAdapterUnifiedLoader",
              "inputs": {"model": src, "preset": COMFY_PRESET.get(kind, "PLUS FACE (portraits)")}}
    if faceid:
        wf[li]["inputs"].update(lora_strength=0.6, provider="CPU")
        wf[ap] = {"class_type": "IPAdapterFaceID", "inputs": {"model": [li, 0], "ipadapter": [li, 1], "image": [ld, 0],
                  "weight": float(weight), "weight_faceidv2": float(weight), "weight_type": "linear", "combine_embeds": "concat",
                  "start_at": 0.0, "end_at": float(stop_at), "embeds_scaling": "V only"}}
    else:
        wf[ap] = {"class_type": "IPAdapter", "inputs": {"model": [li, 0], "ipadapter": [li, 1], "image": [ld, 0],
                  "weight": float(weight), "start_at": 0.0, "end_at": float(stop_at), "weight_type": "standard"}}
    for s in samplers:
        wf[s]["inputs"]["model"] = [ap, 0]
    return wf


def apply_to_job(job, face_png, model, kind, weight=WEIGHT, stop_at=STOP_AT, target_png=None, mask_png=None, denoise=DENOISE,
                 feather=0, padding=96):
    """Turn a made job into a Face Swap job. Generate mode: just the face unit. Swap mode: inpaint + face unit."""
    job.faceswap = {"image": face_png, "model": model, "kind": kind, "weight": float(weight), "stop_at": float(stop_at)}
    job.reference = None  # the character's own reference would double up – Face Swap's unit replaces it
    if target_png and mask_png:
        from .imagegen import png_size
        w, h = png_size(target_png)
        job.width, job.height = (w // 8) * 8 or job.width, (h // 8) * 8 or job.height
        job.inpaint = {"image": target_png, "mask": mask_png, "denoise": float(denoise), "mask_blur": int(max(0, feather) // 2) or 4,
                       "only_masked": True, "padding": int(padding), "fill": "original"}
        job.hires = None
    job.tag = job.tag or "faceswap"
    return job


# ------------------------------------------------------------------ face detection
ANIME_CASCADE_URL = "https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/master/lbpcascade_animeface.xml"


def cv2_available():
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in ("cv2", "numpy"))


def _decode(png):
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Couldn't read the image")
    return img


def _encode(img):
    import cv2
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Couldn't encode PNG")
    return buf.tobytes()


def anime_cascade(cache_dir):
    """Path of nagadomi's anime face cascade, downloaded once into the data folder (None if offline)."""
    if not cache_dir:
        return None
    p = os.path.join(cache_dir, "lbpcascade_animeface.xml")
    if not os.path.exists(p):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with urllib.request.urlopen(ANIME_CASCADE_URL, timeout=20) as r:
                data = r.read()
            if b"<opencv_storage>" not in data:
                return None
            with open(p, "wb") as f:
                f.write(data)
        except OSError:
            return None
    return p


def detect_faces(png, cache_dir=None):
    """Face boxes [(x, y, w, h)] largest first – anime cascade, then the photo cascades. [] without OpenCV."""
    if not cv2_available():
        return []
    import cv2
    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 dropped the cascades – needs opencv-python-headless<5
        return []
    img = _decode(png)
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    side = min(img.shape[:2])
    mn = max(24, side // 12)
    haar = getattr(getattr(cv2, "data", None), "haarcascades", "")
    paths = [anime_cascade(cache_dir)] + [os.path.join(haar, n) for n in
                                          ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        cc = cv2.CascadeClassifier(p)
        if cc.empty():
            continue
        found = cc.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(mn, mn))
        if len(found):
            return sorted([tuple(int(v) for v in f) for f in found], key=lambda b: -b[2] * b[3])
    return []


def parse_vision_box(text, w, h):
    """Box from a vision model reply: JSON bbox_2d [x1,y1,x2,y2] (pixels, or 0-1 / 0-1000 normalised)."""
    import re
    m = re.search(r"\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", text or "")
    if not m:
        return None
    x1, y1, x2, y2 = (float(v) for v in m.groups())
    if max(x1, y1, x2, y2) <= 1.0:
        x1, x2, y1, y2 = x1 * w, x2 * w, y1 * h, y2 * h
    elif max(x2, y2) <= 1000 and (x2 > w or y2 > h):
        x1, x2, y1, y2 = x1 * w / 1000, x2 * w / 1000, y1 * h / 1000, y2 * h / 1000
    x1, x2 = sorted((max(0, x1), min(w, x2))); y1, y2 = sorted((max(0, y1), min(h, y2)))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return int(x1), int(y1), int(x2 - x1), int(y2 - y1)


def vision_messages(png):
    return [{"role": "user", "content": "Find the main person's face (forehead to chin, ear to ear, not the hair). "
             "Reply only with JSON: {\"bbox_2d\": [x1, y1, x2, y2]} in pixel coordinates of this image.",
             "images": [base64.b64encode(png).decode()]}]


# ------------------------------------------------------------------ source face crop (face + hair)
def crop_box(face, img_w, img_h, margin=HAIR_MARGIN):
    """Square crop around a face box that keeps the hair: centred a bit above the face (hair sits on top)."""
    x, y, w, h = face
    side = int(max(w, h) * margin)
    cx, cy = x + w / 2, y + h / 2 - h * 0.18 * (margin / HAIR_MARGIN)
    return int(cx - side / 2), int(cy - side / 2), side, side


def crop_face(png, face=None, margin=HAIR_MARGIN, size=512, cache_dir=None):
    """(png, box) – the face + hair square the IP-Adapter sees. Out-of-frame parts are padded with Fooocus' grey."""
    from PySide6.QtGui import QColor, QImage, QPainter
    from .regions import _png, _qimage
    img = _qimage(png)
    if face is None:
        faces = detect_faces(png, cache_dir)
        face = faces[0] if faces else None
    if face is None:  # no face found – use the centre square (the user can pick a closer image)
        s = min(img.width(), img.height())
        box = ((img.width() - s) // 2, 0 if img.height() > img.width() else (img.height() - s) // 2, s, s)
    else:
        box = crop_box(face, img.width(), img.height(), margin)
    out = QImage(box[2], box[3], QImage.Format_RGB32); out.fill(QColor(135, 133, 132))
    p = QPainter(out); p.drawImage(0, 0, img, box[0], box[1], box[2], box[3]); p.end()
    return _png(out.scaled(size, size)), box


# ------------------------------------------------------------------ target mask (face + hair)
def head_shapes(face, img_w, img_h, hair="Medium"):
    """Two ellipses + an optional hair curtain (x, y, w, h) in image pixels covering face, hair and its fall."""
    x, y, w, h = face
    cx = x + w / 2
    head_w, top = w * 1.75, y - h * 0.8
    bottom = y + h * 1.12
    shapes = [("ellipse", cx - head_w / 2, top, head_w, bottom - top)]
    drop = HAIR_LENGTHS.get(hair, 0.55) * h
    if drop > 0:
        cw = w * 1.65
        shapes.append(("rounded", cx - cw / 2, y + h * 0.3, cw, h * 0.8 + drop))
    return shapes


def auto_mask(png, face, hair="Medium", grow=16, feather=12, refine=True):
    """White-on-black PNG mask of face + hair. OpenCV: GrabCut edge refine, dilate (grow) and blur (feather);
    without OpenCV it falls back to the drawn shapes grown by `grow` (Forge's mask blur does the feather)."""
    from .regions import _qimage
    img = _qimage(png)
    W, H = img.width(), img.height()
    shapes = head_shapes(face, W, H, hair)
    if not cv2_available():
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter
        from .regions import _png
        m = QImage(W, H, QImage.Format_RGB32); m.fill(QColor(0, 0, 0))
        p = QPainter(m); p.setRenderHint(QPainter.Antialiasing); p.setPen(QColor(255, 255, 255)); p.setBrush(QColor(255, 255, 255))
        for kind, sx, sy, sw, sh in shapes:
            r = QRectF(sx - grow, sy - grow, sw + 2 * grow, sh + 2 * grow)
            p.drawEllipse(r) if kind == "ellipse" else p.drawRoundedRect(r, sw / 3, sw / 3)
        p.end()
        return _png(m)
    import cv2
    import numpy as np
    bgr = _decode(png)
    rough = np.zeros((H, W), np.uint8)
    for kind, sx, sy, sw, sh in shapes:
        if kind == "ellipse":
            cv2.ellipse(rough, (int(sx + sw / 2), int(sy + sh / 2)), (int(sw / 2), int(sh / 2)), 0, 0, 360, 255, -1)
        else:
            r = int(sw / 3)
            cv2.rectangle(rough, (int(sx), int(sy + r)), (int(sx + sw), int(sy + sh)), 255, -1)
            cv2.rectangle(rough, (int(sx + r), int(sy)), (int(sx + sw - r), int(sy + sh)), 255, -1)
            for ex in (sx + r, sx + sw - r):
                cv2.circle(rough, (int(ex), int(sy + r)), r, 255, -1)
    mask = rough
    if refine:
        try:
            x, y, w, h = face
            gc = np.full((H, W), cv2.GC_BGD, np.uint8)
            outer = cv2.dilate(rough, np.ones((3, 3), np.uint8), iterations=max(4, int(w * 0.25)))
            gc[outer > 0] = cv2.GC_PR_BGD
            gc[rough > 0] = cv2.GC_PR_FGD
            core = np.zeros((H, W), np.uint8)
            cv2.ellipse(core, (int(x + w / 2), int(y + h * 0.55)), (int(w * 0.38), int(h * 0.45)), 0, 0, 360, 255, -1)
            gc[core > 0] = cv2.GC_FGD
            bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
            cv2.grabCut(bgr, gc, None, bg, fg, 4, cv2.GC_INIT_WITH_MASK)
            seg = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
            seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            # keep the blob that holds the face, fill holes, and never lose the face core
            n, lab = cv2.connectedComponents(seg)
            if n > 1:
                cy, cx = int(y + h / 2), int(x + w / 2)
                keep = lab[min(cy, H - 1), min(cx, W - 1)]
                if keep:
                    seg = np.where(lab == keep, 255, 0).astype(np.uint8)
            seg = cv2.bitwise_or(seg, core)
            if seg.sum() > rough.sum() * 0.35:  # GrabCut sane – otherwise keep the rough shape
                mask = seg
        except cv2.error:
            mask = rough
    if grow > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(grow) + 1, 2 * int(grow) + 1))
        mask = cv2.dilate(mask, k)
    elif grow < 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (-2 * int(grow) + 1, -2 * int(grow) + 1))
        mask = cv2.erode(mask, k)
    if feather > 0:
        f = int(feather) * 2 + 1
        mask = cv2.GaussianBlur(mask, (f, f), 0)
    return _encode(mask)


def mask_to_alpha(mask_png):
    """QImage (ARGB32_Premultiplied, white with alpha = mask) for InpaintCanvas.mask."""
    from PySide6.QtGui import QColor, QImage, QPainter
    from .regions import _qimage
    m = _qimage(mask_png).convertToFormat(QImage.Format_Grayscale8)
    alpha = QImage(m.constBits(), m.width(), m.height(), m.bytesPerLine(), QImage.Format_Alpha8).copy()
    out = QImage(m.width(), m.height(), QImage.Format_ARGB32_Premultiplied); out.fill(QColor(255, 255, 255))
    p = QPainter(out); p.setCompositionMode(QPainter.CompositionMode_DestinationIn); p.drawImage(0, 0, alpha); p.end()
    return out
