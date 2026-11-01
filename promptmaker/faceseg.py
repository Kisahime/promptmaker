"""5.1 Face Swap – real face + hair segmentation for the swap mask (no torch: OpenCV + onnxruntime on the CPU).

  * faces:  OpenCV YuNet (photos, 230 KB ONNX, ships with OpenCV's FaceDetectorYN), then nagadomi's anime cascade;
  * photos: SegFormer face parsing (jonathandinu/face-parsing, CelebAMask-HQ 19 classes – skin, brows, eyes, ears,
            nose, lips, hair, hat, neck …, int8 ONNX ≈ 90 MB) run on a big crop around the chosen face;
  * anime:  skytnt anime-seg (ISNet, ≈ 175 MB ONNX) cuts the character from the background, then the head is kept:
            face + the hair-coloured pixels connected to it;
  * several people: every pixel is given to the nearest face (scaled by face size), so the mask never runs onto
    another person, and only the blob joined to the chosen face is kept – never the background.
Models download once into data/models on first use (with progress). Without onnxruntime or offline, callers fall
back to faceswap.auto_mask's shape + GrabCut method.
"""
import importlib.util
import os
import urllib.request

HF = "https://huggingface.co/"
SEG_MODELS = {
    "yunet": {"file": "face_detection_yunet_2023mar.onnx", "size": 232589,
              "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
              "label": "YuNet face detector"},
    "anime_face": {"file": "anime-face-yolov8n-v1.4.onnx", "size": 12102558,
                   "url": HF + "deepghs/anime_face_detection/resolve/main/face_detect_v1.4_n/model.onnx",
                   "label": "Anime face detector"},
    "face_parsing": {"file": "face-parsing-segformer-int8.onnx", "size": 89439678,
                     "url": HF + "jonathandinu/face-parsing/resolve/main/onnx/model_quantized.onnx",
                     "label": "Face parsing (photos)"},
    "anime_seg": {"file": "anime-seg-isnetis.onnx", "size": 176069933,
                  "url": HF + "skytnt/anime-seg/resolve/main/isnetis.onnx", "label": "Anime character cut-out"},
}
# CelebAMask-HQ labels used by the face-parsing model
FACE = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)        # skin, nose, glasses, eyes, brows, mouth, lips
EARS = (8, 9, 15)                              # ears + earrings
HAIR = (13, 14)                                # hair, hat
NECK = (16, 17)                                # necklace, neck
STYLES = ("Auto", "Photo", "Anime")


def available():
    return all(importlib.util.find_spec(m) is not None for m in ("onnxruntime", "cv2", "numpy"))


def model_path(name, cache_dir):
    return os.path.join(cache_dir or "", SEG_MODELS[name]["file"])


def have_model(name, cache_dir):
    p = model_path(name, cache_dir)
    return os.path.exists(p) and os.path.getsize(p) >= SEG_MODELS[name]["size"] * 0.95


def ensure_model(name, cache_dir, progress=None, timeout=30):
    """Path of a segmentation model, downloading it once (progress(label, done_bytes, total_bytes)). None on failure."""
    if not cache_dir:
        return None
    if have_model(name, cache_dir):
        return model_path(name, cache_dir)
    if os.environ.get("PROMPTMAKER_NO_MODEL_DOWNLOAD"):
        return None
    spec = SEG_MODELS[name]
    p = model_path(name, cache_dir); part = p + ".part"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "PromptMaker"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or spec["size"]); done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk); done += len(chunk)
                if progress:
                    progress(spec["label"], done, total)
        if os.path.getsize(part) < spec["size"] * 0.95:
            raise OSError("incomplete download")
        os.replace(part, p)
        return p
    except OSError:
        try:
            os.remove(part)
        except OSError:
            pass
        return None


_SESSIONS = {}


def _session(path):
    if path not in _SESSIONS:
        import onnxruntime as ort
        so = ort.SessionOptions(); so.log_severity_level = 3
        _SESSIONS[path] = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])  # CPU: leave the GPU to Forge
    return _SESSIONS[path]


# ------------------------------------------------------------------ faces
def yunet_faces(bgr, path, score=0.6):
    """[(x, y, w, h)] photo faces, largest first."""
    import cv2
    if not path or not hasattr(cv2, "FaceDetectorYN"):
        return []
    H, W = bgr.shape[:2]
    s = min(1.0, 1280 / max(H, W))
    img = cv2.resize(bgr, (int(W * s), int(H * s))) if s < 1 else bgr
    d = cv2.FaceDetectorYN.create(path, "", (img.shape[1], img.shape[0]), score)
    _n, found = d.detect(img)
    if found is None:
        return []
    out = [tuple(int(round(v / s)) for v in f[:4]) for f in found]
    out = [(max(0, x), max(0, y), w, h) for x, y, w, h in out if w > 8 and h > 8]
    return sorted(out, key=lambda b: -b[2] * b[3])


def anime_faces(bgr, path, score=0.31):
    """[(x, y, w, h)] anime faces, largest first (deepghs anime_face_detection v1.4, YOLOv8 n)."""
    import cv2
    import numpy as np
    if not path:
        return []
    H, W = bgr.shape[:2]
    r = 640 / max(H, W); nw, nh = max(1, int(W * r)), max(1, int(H * r))
    pad = np.full((640, 640, 3), 114, np.uint8); pad[:nh, :nw] = cv2.resize(bgr, (nw, nh))
    x = cv2.cvtColor(pad, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255
    out = _session(path).run(None, {_session(path).get_inputs()[0].name: x})[0][0].T
    out = out[out[:, 4] > score]
    boxes = [[float(cx - w / 2) / r, float(cy - h / 2) / r, float(w) / r, float(h) / r] for cx, cy, w, h, _s in out]
    keep = cv2.dnn.NMSBoxes(boxes, [float(v) for v in out[:, 4]], score, 0.45) if boxes else []
    res = [tuple(int(round(v)) for v in boxes[i]) for i in np.array(keep).flatten()]
    res = [(max(0, x), max(0, y), w, h) for x, y, w, h in res if w > 8 and h > 8]
    return sorted(res, key=lambda b: -b[2] * b[3])


def find_faces(bgr, cache_dir, style="Auto", progress=None):
    """(faces, style) – style becomes 'Photo' or 'Anime' when Auto. ([], style) when nothing is found."""
    if not available():
        return [], style
    if style in ("Auto", "Photo"):
        f = yunet_faces(bgr, ensure_model("yunet", cache_dir, progress))
        if f or style == "Photo":
            return f, "Photo"
    return anime_faces(bgr, ensure_model("anime_face", cache_dir, progress)), "Anime"


def pick_largest(faces):
    return 0 if faces else None


def face_at(faces, x, y):
    """Index of the face whose box holds (x, y) – else the nearest centre (None with no faces)."""
    if not faces:
        return None
    for i, (fx, fy, fw, fh) in enumerate(faces):
        if fx <= x <= fx + fw and fy <= y <= fy + fh:
            return i
    return min(range(len(faces)), key=lambda i: (faces[i][0] + faces[i][2] / 2 - x) ** 2 + (faces[i][1] + faces[i][3] / 2 - y) ** 2)


def owner_map(shape, faces, idx):
    """bool mask: pixels nearer (in face-size units) to faces[idx] than to any other face."""
    import numpy as np
    H, W = shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    def dist(f):
        x, y, w, h = f
        s = max(w, h)
        return ((xx - (x + w / 2)) / s) ** 2 + ((yy - (y + h / 2)) / s) ** 2
    mine = dist(faces[idx])
    keep = np.ones((H, W), bool)
    for j, f in enumerate(faces):
        if j != idx:
            keep &= mine <= dist(f)
    return keep


def _blob_with(mask, pt, bridge=0):
    """Only the connected blob of a 0/255 mask that touches pt (or the nearest blob). `bridge` px gaps (line art
    outlines between hair strands) still count as connected."""
    import cv2
    import numpy as np
    src = (mask > 0).astype(np.uint8)
    if bridge > 0:
        src = cv2.dilate(src, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * bridge + 1, 2 * bridge + 1)))
    n, lab = cv2.connectedComponents(src)
    if n <= 1:
        return mask
    x, y = int(min(max(pt[0], 0), mask.shape[1] - 1)), int(min(max(pt[1], 0), mask.shape[0] - 1))
    keep = lab[y, x]
    if not keep:
        ys, xs = np.nonzero(lab)
        k = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        keep = lab[ys[k], xs[k]]
    return np.where((lab == keep) & (mask > 0), 255, 0).astype(np.uint8)


def _fill_holes(mask):
    import cv2
    import numpy as np
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(mask)
    cv2.drawContours(out, cs, -1, 255, -1)
    return out


# ------------------------------------------------------------------ photo: face parsing
def head_crop(face, W, H, scale=3.2):
    """Square crop around a face, a bit lower than centre so long hair and the neck fit."""
    x, y, w, h = face
    side = int(max(w, h) * scale)
    cx, cy = x + w / 2, y + h / 2 + h * 0.35
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    return x0, y0, int(min(W, cx + side / 2)) - x0, int(min(H, cy + side / 2)) - y0


def parse_labels(bgr, face, path):
    """(labels HxW uint8 for the crop, crop box)."""
    import cv2
    import numpy as np
    H, W = bgr.shape[:2]
    x0, y0, cw, ch = head_crop(face, W, H)
    crop = bgr[y0:y0 + ch, x0:x0 + cw]
    rgb = cv2.cvtColor(cv2.resize(crop, (512, 512), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    rgb = (rgb - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
    logits = _session(path).run(None, {"pixel_values": rgb.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    up = np.stack([cv2.resize(c, (cw, ch), interpolation=cv2.INTER_LINEAR) for c in logits])
    return up.argmax(0).astype(np.uint8), (x0, y0, cw, ch)


def photo_mask(bgr, faces, idx, path, hair=True, neck=False):
    import numpy as np
    H, W = bgr.shape[:2]
    lab, (x0, y0, cw, ch) = parse_labels(bgr, faces[idx], path)
    classes = FACE + EARS + (HAIR if hair else ()) + (NECK if neck else ())
    part = np.isin(lab, classes).astype(np.uint8) * 255
    mask = np.zeros((H, W), np.uint8); mask[y0:y0 + ch, x0:x0 + cw] = part
    return _finish(mask, faces, idx)


def _finish(mask, faces, idx, bridge=0):
    import numpy as np
    x, y, w, h = faces[idx]
    if len(faces) > 1:
        mask = np.where(owner_map(mask.shape, faces, idx), mask, 0).astype(np.uint8)
    mask = _blob_with(mask, (x + w / 2, y + h / 2), bridge)
    return _fill_holes(mask)


# ------------------------------------------------------------------ anime: character cut-out + hair colour
def anime_person(bgr, path):
    """0-255 character mask (ISNet anime-seg)."""
    import cv2
    import numpy as np
    H, W = bgr.shape[:2]
    s = 1024 / max(H, W); nh, nw = int(H * s), int(W * s)
    pad = np.zeros((1024, 1024, 3), np.float32)
    ph, pw = (1024 - nh) // 2, (1024 - nw) // 2
    pad[ph:ph + nh, pw:pw + nw] = cv2.cvtColor(cv2.resize(bgr, (nw, nh)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    out = _session(path).run(None, {"img": pad.transpose(2, 0, 1)[None]})[0][0, 0]
    out = cv2.resize(out[ph:ph + nh, pw:pw + nw], (W, H))
    return (out > 0.5).astype(np.uint8) * 255


def anime_mask(bgr, faces, idx, path, hair=True, neck=False, person=None):
    import cv2
    import numpy as np
    H, W = bgr.shape[:2]
    x, y, w, h = faces[idx]
    person = anime_person(bgr, path) if person is None else person
    face = np.zeros((H, W), np.uint8)   # anime cascade boxes run brow → chin; the face oval adds the forehead
    cv2.ellipse(face, (int(x + w / 2), int(y + h * 0.5)), (int(w * 0.55), int(h * 0.62)), 0, 0, 360, 255, -1)
    mask = cv2.bitwise_and(face, person)
    if hair:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        band = np.zeros((H, W), bool)
        band[max(0, int(y - h * 0.45)):max(0, int(y - h * 0.05)), int(x + w * 0.2):int(x + w * 0.8)] = True
        band &= person > 0
        if band.sum() > 20:
            wt = np.array([0.35, 1.0, 1.0], np.float32)   # shading changes lightness far more than hue
            ref = np.median(lab[band], axis=0)
            spread = max(24.0, float(np.percentile(np.linalg.norm((lab[band] - ref) * wt, axis=1), 90)) * 1.5)
            near = (np.linalg.norm((lab - ref) * wt, axis=2) < spread) & (person > 0)
            box = np.zeros((H, W), bool)
            box[max(0, int(y - h * 1.6)):int(y + h * 4.0), max(0, int(x - w * 1.6)):int(x + w * 2.6)] = True
            box[int(y + h * 0.95):, int(x + w * 0.15):int(x + w * 0.85)] = False  # chest under the chin: collar, not hair
            hm = (near & box).astype(np.uint8) * 255
            hm = cv2.morphologyEx(hm, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            hm = cv2.morphologyEx(hm, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
            joined = _blob_with(cv2.bitwise_or(hm, face & person), (x + w / 2, y + h / 2), max(2, int(w * 0.02)))
            mask = cv2.bitwise_or(mask, joined)
        else:  # no clear hair colour – take the character above the chin around the head
            top = np.zeros((H, W), np.uint8)
            cv2.ellipse(top, (int(x + w / 2), int(y + h * 0.3)), (int(w * 1.2), int(h * 1.25)), 0, 0, 360, 255, -1)
            mask = cv2.bitwise_or(mask, cv2.bitwise_and(top, person))
    if neck:
        nk = np.zeros((H, W), np.uint8)
        cv2.rectangle(nk, (int(x + w * 0.25), int(y + h * 0.8)), (int(x + w * 0.75), int(y + h * 1.45)), 255, -1)
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        cheek = np.zeros((H, W), bool)
        cheek[int(y + h * 0.45):int(y + h * 0.7), int(x + w * 0.2):int(x + w * 0.8)] = True
        skin = np.median(lab[cheek & (person > 0)], axis=0) if (cheek & (person > 0)).any() else None
        if skin is not None:  # only skin-coloured pixels under the chin (shaded skin is darker, so L counts less)
            d = np.linalg.norm((lab - skin) * np.array([0.3, 1.0, 1.0], np.float32), axis=2)
            nk = np.where(d < 18, nk, 0).astype(np.uint8)
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(nk, person))
    return _finish(mask, faces, idx, max(2, int(w * 0.02)))


# ------------------------------------------------------------------ public
def segment(bgr, faces, idx, style, cache_dir, hair=True, neck=False, progress=None):
    """0/255 mask of the chosen person's face (+ hair, + neck), or None if the models can't be had."""
    if not available() or not faces or idx is None:
        return None
    if style == "Anime":
        p = ensure_model("anime_seg", cache_dir, progress)
        return anime_mask(bgr, faces, idx, p, hair, neck) if p else None
    p = ensure_model("face_parsing", cache_dir, progress)
    return photo_mask(bgr, faces, idx, p, hair, neck) if p else None
