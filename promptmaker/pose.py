"""Pose & composition sketcher logic: OpenPose-18 skeletons + subject boxes → composition tags, OpenPose image,
ControlNet payloads for Forge (alwayson_scripts) and ComfyUI (workflow patch). Coordinates are normalised 0..1."""
import copy
import json
import math

NAMES = ["nose", "neck", "r_shoulder", "r_elbow", "r_wrist", "l_shoulder", "l_elbow", "l_wrist", "r_hip", "r_knee",
         "r_ankle", "l_hip", "l_knee", "l_ankle", "r_eye", "l_eye", "r_ear", "l_ear"]
IDX = {n: i for i, n in enumerate(NAMES)}
# OpenPose COCO limb pairs and the standard colours ControlNet's openpose models were trained on
LIMBS = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11), (11, 12), (12, 13), (1, 0),
         (0, 14), (14, 16), (0, 15), (15, 17)]
COLORS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0),
          (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255),
          (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]

# person's right side appears on the image's left when facing the viewer
STANDING = [(.50, .14), (.50, .22), (.42, .23), (.39, .36), (.38, .48), (.58, .23), (.61, .36), (.62, .48), (.45, .50),
            (.45, .68), (.45, .86), (.55, .50), (.55, .68), (.55, .86), (.48, .12), (.52, .12), (.46, .13), (.54, .13)]


def _pose(changes):
    pts = [list(p) for p in STANDING]
    for name, xy in changes.items():
        pts[IDX[name]] = list(xy)
    return pts


PRESETS = {
    "Standing": _pose({}),
    "Arms up": _pose({"r_elbow": (.40, .12), "r_wrist": (.41, .03), "l_elbow": (.60, .12), "l_wrist": (.59, .03)}),
    "Waving": _pose({"l_elbow": (.66, .17), "l_wrist": (.68, .06)}),
    "T-pose": _pose({"r_elbow": (.31, .23), "r_wrist": (.20, .23), "l_elbow": (.69, .23), "l_wrist": (.80, .23)}),
    "Hands on hips": _pose({"r_elbow": (.34, .36), "r_wrist": (.44, .48), "l_elbow": (.66, .36), "l_wrist": (.56, .48)}),
    "Sitting": _pose({"r_hip": (.45, .55), "l_hip": (.55, .55), "r_knee": (.36, .56), "l_knee": (.46, .57),
                      "r_ankle": (.36, .78), "l_ankle": (.46, .79), "r_wrist": (.40, .55), "l_wrist": (.58, .55)}),
    "Walking": _pose({"r_knee": (.42, .68), "r_ankle": (.37, .85), "l_knee": (.58, .67), "l_ankle": (.62, .86),
                      "r_wrist": (.44, .47), "l_wrist": (.57, .46)}),
    "Kneeling": _pose({"r_hip": (.45, .56), "l_hip": (.55, .56), "r_knee": (.45, .80), "l_knee": (.56, .80),
                       "r_ankle": (.40, .82), "l_ankle": (.62, .82)}),
}


def new_figure(preset="Standing", dx=0.0, scale=1.0):
    pts = copy.deepcopy(PRESETS[preset])
    return {"points": [[min(1, max(0, .5 + (x - .5) * scale + dx)), min(1, max(0, .5 + (y - .5) * scale))] for x, y in pts]}


def _p(fig, name):
    return fig["points"][IDX[name]]


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def h_position(x):
    return "on the left" if x < 0.38 else "on the right" if x > 0.62 else "in the center"


def framing(fig):
    edge = 0.97
    cut = lambda n: _p(fig, n)[1] >= edge  # noqa: E731
    ys = [p[1] for p in fig["points"]]
    height = max(ys) - min(ys)
    if cut("r_hip") and cut("l_hip"):
        return "close-up portrait" if (cut("r_shoulder") or height > .9) else "upper body"
    if cut("r_knee") and cut("l_knee"):
        return "upper body"
    if cut("r_ankle") and cut("l_ankle"):
        return "cowboy shot"
    if height < 0.35:
        return "wide shot, full body"
    return "full body"


def describe_figure(fig):
    tags = []
    nose, neck = _p(fig, "nose"), _p(fig, "neck")
    rs, ls, rw, lw = _p(fig, "r_shoulder"), _p(fig, "l_shoulder"), _p(fig, "r_wrist"), _p(fig, "l_wrist")
    rh, lh, rk, lk = _p(fig, "r_hip"), _p(fig, "l_hip"), _p(fig, "r_knee"), _p(fig, "l_knee")
    ra, la = _p(fig, "r_ankle"), _p(fig, "l_ankle")
    torso = max(_dist(neck, [(rh[0] + lh[0]) / 2, (rh[1] + lh[1]) / 2]), 1e-3)
    sw = ls[0] - rs[0]
    # facing
    if abs(sw) < torso * 0.25:
        tags.append("from side")
    elif sw < 0:
        tags.append("from behind")
    else:
        tags.append("facing viewer")
    # legs
    hip_y, knee_y = (rh[1] + lh[1]) / 2, (rk[1] + lk[1]) / 2
    ankle_y = (ra[1] + la[1]) / 2
    if abs(knee_y - hip_y) < torso * 0.3 and ankle_y > knee_y + torso * 0.3:
        tags.append("sitting")
    elif abs(ankle_y - knee_y) < torso * 0.2 and knee_y > hip_y + torso * 0.5:
        tags.append("kneeling")
    elif abs(ra[0] - la[0]) > max(abs(rh[0] - lh[0]) * 2.2, torso * 0.45) or abs(rk[0] - lk[0]) > torso * 0.4:
        tags.append("walking" if abs(ra[1] - la[1]) < torso * 0.15 and abs(ra[0] - la[0]) < torso * 0.9 else "legs apart")
    else:
        tags.append("standing")
    # arms
    up = [w for w in (rw, lw) if w[1] < nose[1]]
    if len(up) == 2:
        tags.append("arms up")
    elif len(up) == 1:
        tags.append("hand up, waving")
    else:
        out = [w for w, s in ((rw, rs), (lw, ls)) if abs(w[1] - s[1]) < torso * 0.25 and _dist(w, s) > torso * 0.7]
        if len(out) == 2:
            tags.append("arms outstretched")
        elif all(_dist(w, h) < torso * 0.25 for w, h in ((rw, rh), (lw, lh))) and \
                _p(fig, "r_elbow")[0] < rs[0] - torso * 0.2 and _p(fig, "l_elbow")[0] > ls[0] + torso * 0.2:
            tags.append("hands on hips")
    # lean
    mid_hip_x = (rh[0] + lh[0]) / 2
    if abs(neck[0] - mid_hip_x) > torso * 0.35:
        tags.append("leaning to the side")
    return tags


def figure_center(fig):
    xs = [p[0] for p in fig["points"]]
    return (min(xs) + max(xs)) / 2


def describe_box(box):
    cx = box["x"] + box["w"] / 2
    area = box["w"] * box["h"]
    depth = "in the foreground" if box["y"] + box["h"] > .9 and area > .2 else "in the background" if area < .06 else ""
    return [t for t in (h_position(cx), depth) if t]


def composition(figures, boxes=(), profile=None):
    """{"tags": [...], "text": str} – text is comma tags or a sentence depending on the profile format."""
    fmt = (profile or {}).get("format", "tags")
    tags, sentences = [], []
    n = len(figures)
    if n == 1:
        tags.append("solo")
    elif n == 2:
        tags.append("2people")
    elif n > 2:
        tags.append("multiple people")
    if figures:
        biggest = max(figures, key=lambda f: max(p[1] for p in f["points"]) - min(p[1] for p in f["points"]))
        tags.append(framing(biggest))
    for i, f in enumerate(figures):
        d = describe_figure(f)
        pos = h_position(figure_center(f)) if n > 1 or abs(figure_center(f) - .5) > .12 else ""
        tags += d + ([f"person {pos}" if n > 1 else f"subject {pos}"] if pos else [])
        who = f"person {i + 1}" if n > 1 else "a person"
        sentences.append(f"{who} {pos + ' ' if pos else ''}" + ", ".join(d))
    for b in boxes:
        label = (b.get("label") or "subject").strip()
        where = describe_box(b)
        tags.append(f"{label} {' '.join(where)}".strip())
        sentences.append(f"{label} {' and '.join(where)}".strip())
    tags = list(dict.fromkeys(tags))
    if fmt in ("natural", "hybrid", "json"):
        frame = framing(max(figures, key=lambda f: max(p[1] for p in f["points"]) - min(p[1] for p in f["points"]))) \
            if figures else "wide shot"
        text = f"{frame[0].upper() + frame[1:]} composition: " + "; ".join(sentences) + "." if sentences else ""
    else:
        text = ", ".join(tags)
    return {"tags": tags, "text": text}


# ---------------------------------------------------------------- OpenPose rendering
def render_openpose(figures, width=768, height=1024):
    """Black canvas with coloured limbs/joints in the OpenPose style. Returns PNG bytes (needs QtGui)."""
    from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    img = QImage(width, height, QImage.Format_RGB32); img.fill(QColor(0, 0, 0))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    stick = max(2, int(min(width, height) / 128))
    for fig in figures:
        pts = [QPointF(x * width, y * height) for x, y in fig["points"]]
        for k, (a, b) in enumerate(LIMBS):
            c = QColor(*COLORS[k % len(COLORS)]); c.setAlphaF(0.6)
            p.setPen(QPen(c, stick * 2, Qt.SolidLine, Qt.RoundCap)); p.drawLine(pts[a], pts[b])
        p.setPen(Qt.NoPen)
        for k, pt in enumerate(pts):
            p.setBrush(QColor(*COLORS[k])); p.drawEllipse(pt, stick * 1.2, stick * 1.2)
    p.end()
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    return bytes(buf.data())


# ---------------------------------------------------------------- ControlNet
def forge_unit(image_b64, model="", weight=1.0):
    """One ControlNet unit for /sdapi/v1/txt2img alwayson_scripts (sd-webui-controlnet / Forge built-in)."""
    return {"enabled": True, "image": image_b64, "module": "None", "model": model or "None", "weight": float(weight),
            "resize_mode": "Crop and Resize", "control_mode": "Balanced", "pixel_perfect": True,
            "guidance_start": 0.0, "guidance_end": 1.0}


def add_forge_controlnet(payload, image_b64, model="", weight=1.0):
    payload.setdefault("alwayson_scripts", {})["controlnet"] = {"args": [forge_unit(image_b64, model, weight)]}
    return payload


def add_comfy_controlnet(workflow, image_name, model, strength=1.0):
    """Insert LoadImage → ControlNetLoader → ControlNetApplyAdvanced in front of every KSampler's conditioning.
    Returns a new workflow dict; raises ValueError if there is no KSampler to attach to."""
    wf = copy.deepcopy(workflow)
    samplers = [k for k, n in wf.items() if isinstance(n, dict) and n.get("class_type") in ("KSampler", "KSamplerAdvanced")]
    if not samplers:
        raise ValueError("This workflow has no KSampler node, so ControlNet can't be attached")
    ids = [int(k) for k in wf if str(k).isdigit()]
    nxt = max(ids or [0]) + 100
    img_id, cn_id = str(nxt), str(nxt + 1)
    wf[img_id] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf[cn_id] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": model}}
    for i, s in enumerate(samplers):
        ap = str(nxt + 2 + i)
        ins = wf[s]["inputs"]
        wf[ap] = {"class_type": "ControlNetApplyAdvanced",
                  "inputs": {"positive": ins["positive"], "negative": ins["negative"], "control_net": [cn_id, 0],
                             "image": [img_id, 0], "strength": float(strength), "start_percent": 0.0, "end_percent": 1.0}}
        ins["positive"], ins["negative"] = [ap, 0], [ap, 1]
    return wf


# ---------------------------------------------------------------- ControlNet model checks
# Base family a ControlNet was trained for, guessed from its file name. Order matters: specific before generic.
_CN_FAMILIES = [
    ("Anima", ("anima",)),
    ("FLUX", ("flux", "f1-", "_f1_", "xlabs", "instantx", "shakker")),
    ("SD3", ("sd3", "sd35", "sd3.5")),
    ("Qwen", ("qwen",)),
    ("SDXL", ("sdxl", "xl", "xinsir", "illustrious", "noob", "pony", "t2i-adapter-xl", "kohya_controllllite", "controllllite",
              "diffusers_xl", "thibaud_xl", "mistoline", "union")),
    ("SD1.5", ("sd15", "sd1.5", "sd_15", "v11p", "v11e", "v11f1", "control_v1", "control_sd15", "t2iadapter", "t2i-adapter")),
]


def cn_family(name, civitai_base=""):
    """'SD1.5' / 'SDXL' / 'FLUX' / 'SD3' / 'Qwen' / 'Anima', or '' if unknown. Civitai's baseModel wins if given."""
    if civitai_base:
        b = civitai_base.lower()
        for fam, keys in (("Anima", ("anima",)), ("FLUX", ("flux",)), ("SD3", ("sd 3",)), ("Qwen", ("qwen",)),
                          ("SDXL", ("sdxl", "pony", "illustrious", "noobai")), ("SD1.5", ("sd 1.",))):
            if any(k in b for k in keys):
                return fam
    n = (name or "").lower().split(" [")[0]
    for fam, keys in _CN_FAMILIES:
        if any(k in n for k in keys):
            return fam
    return ""


def profile_family(profile):
    """The ControlNet family a model profile needs, e.g. Illustrious → SDXL, Anima → Anima. '' = not a local model."""
    if not profile:
        return ""
    text = f"{profile.get('id', '')} {profile.get('name', '')} {profile.get('family', '')}".lower()
    for fam, keys in (("Anima", ("anima",)), ("FLUX", ("flux",)), ("SD3", ("stable diffusion 3", "sd3")),
                      ("Qwen", ("qwen",)), ("SDXL", ("xl", "pony", "illustrious", "noob")), ("SD1.5", ("1.5", "sd15"))):
        if any(k in text for k in keys):
            return fam
    return ""


def cn_compat_warning(cn_name, profile, civitai_base=""):
    """A user-facing warning if the ControlNet and the active model profile look like different architectures."""
    need, have = profile_family(profile), cn_family(cn_name, civitai_base)
    if need == "Anima" and have != "Anima":
        return (f"Anima isn't SD1.5/SDXL, so regular ControlNets don't work with it. Use an Anima ControlNet-LLLite model "
                f"(e.g. kohya-ss/Anima-LLLite on Hugging Face) – '{cn_name}' looks like "
                f"{have or 'an unknown type'}, so the pose will probably be ignored.")
    if need and have and need != have:
        return f"'{cn_name}' looks like a {have} ControlNet, but the active profile is {need}. The pose will probably be ignored."
    return ""


def resolve_cn_model(name, models):
    """Return the exact string Forge listed for `name` (case-insensitive, with or without the ' [hash]' suffix
    and file extension), or '' if it isn't in the list."""
    if not name:
        return ""
    if name in models:
        return name

    def key(s):
        s = s.split(" [")[0].strip().lower()
        for ext in (".safetensors", ".pth", ".ckpt", ".bin"):
            if s.endswith(ext):
                s = s[: -len(ext)]
        return s
    k = key(name)
    return next((m for m in models if key(m) == k), "")


def pick_default_cn(models, profile=None):
    """Best guess from Forge's list: a pose model of the right family, then any of the right family, then any pose."""
    fam = profile_family(profile)
    is_pose = lambda m: any(k in m.lower() for k in ("openpose", "pose", "dwpose"))
    for test in (lambda m: is_pose(m) and fam and cn_family(m) == fam, lambda m: fam and cn_family(m) == fam, is_pose):
        hit = next((m for m in models if test(m)), None)
        if hit:
            return hit
    return models[0] if models else ""


def controlnet_applied(info):
    """From the txt2img response 'info' (dict or JSON string): True if ControlNet is recorded in the generation
    parameters, False if it clearly isn't, None if the info doesn't tell us."""
    if isinstance(info, str):
        try:
            info = json.loads(info or "{}")
        except ValueError:
            return None
    if not isinstance(info, dict) or not info:
        return None
    extra = info.get("extra_generation_params")
    if isinstance(extra, dict) and any(str(k).lower().startswith(("controlnet", "controllllite")) for k in extra):
        return True
    texts = info.get("infotexts") or []
    if any("controlnet" in str(t).lower() or "controllllite" in str(t).lower() for t in texts):
        return True
    return False if (isinstance(extra, dict) or texts) else None
