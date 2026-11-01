"""5.1 Face Swap Auto-blend (OpenCV + numpy only): blend a swapped face into the ORIGINAL target.

Order (see FaceSwapPage): generate → harmonise (optional 2nd low-denoise inpaint, no IP-Adapter) → colour match →
grain / sharpness match → seam blend onto the original at its full resolution. Pixels outside the mask are copied
from the original unchanged, so only the face + hair region ever changes."""

DEFAULTS = {"on": True, "colour": True, "colour_strength": 0.8, "seam": True, "seam_mode": "Laplacian",
            "harmonise": True, "harmonise_denoise": 0.25, "grain": True, "grain_strength": 1.0}


def _np():
    import numpy as np
    return np


def decode(png, flags=None):
    import cv2
    np = _np()
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR if flags is None else flags)
    if img is None:
        raise ValueError("Couldn't read the image")
    return img


def encode(img):
    import cv2
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Couldn't encode the image")
    return buf.tobytes()


def mask_f(mask_png, w, h):
    """Float 0..1 mask at w×h (a PNG with alpha uses the alpha, else grey)."""
    import cv2
    np = _np()
    m = decode(mask_png, cv2.IMREAD_UNCHANGED)
    if m.ndim == 3:
        m = m[:, :, 3] if m.shape[2] == 4 and m[:, :, 3].min() < 255 else cv2.cvtColor(m[:, :, :3], cv2.COLOR_BGR2GRAY)
    if m.shape[:2] != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    return m.astype(np.float32) / 255.0


def face_box(mask, face=None):
    """(x, y, w, h) of the face: the given box, else the mask's bounding box."""
    np = _np()
    if face:
        return tuple(int(v) for v in face[:4])
    ys, xs = np.nonzero(mask > 0.5)
    if not len(xs):
        h, w = mask.shape[:2]
        return 0, 0, w, h
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def scale_box(box, sx, sy):
    x, y, w, h = box
    return int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))


def skin_region(bgr, mask, face=None, tol=22.0):
    """Bool map of skin inside the mask: pixels close (LAB chroma + some L) to the median colour of the centre of
    the face box. Hair, eyes, lips and background fall out; works for photos and anime without a model."""
    import cv2
    np = _np()
    H, W = bgr.shape[:2]
    x, y, w, h = face_box(mask, face)
    cx0, cx1 = max(0, x + w // 4), min(W, x + 3 * w // 4)
    cy0, cy1 = max(0, y + h // 3), min(H, y + 3 * h // 4)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    inside = mask > 0.5
    core = np.zeros_like(inside); core[cy0:cy1, cx0:cx1] = True
    core &= inside
    if core.sum() < 16:
        return inside
    ref = np.median(lab[core], axis=0)
    d = np.linalg.norm((lab - ref) * np.array([0.35, 1.0, 1.0], np.float32), axis=2)
    skin = inside & (d < tol)
    return skin if skin.sum() >= 16 else core


def colour_match(result, target, mask, face=None, strength=0.8):
    """Reinhard LAB transfer: the new face's skin gets the mean / std of the ORIGINAL target's skin.
    Applied to the whole masked region (hair keeps its relative colour), weighted by the soft mask × strength."""
    import cv2
    np = _np()
    if strength <= 0:
        return result
    src_skin = skin_region(result, mask, face)
    ref_skin = skin_region(target, mask, face)
    if src_skin.sum() < 16 or ref_skin.sum() < 16:
        return result
    lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB).astype(np.float32)
    tlab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)
    sm, ss = lab[src_skin].mean(0), lab[src_skin].std(0) + 1e-3
    tm, ts = tlab[ref_skin].mean(0), tlab[ref_skin].std(0) + 1e-3
    ratio = np.clip(ts / ss, 0.5, 2.0)
    moved = np.clip((lab - sm) * ratio + tm, 0, 255).astype(np.uint8)
    moved = cv2.cvtColor(moved, cv2.COLOR_LAB2BGR).astype(np.float32)
    a = (np.clip(mask, 0, 1) * float(min(1.0, strength)))[:, :, None]
    return np.clip(result * (1 - a) + moved * a, 0, 255).astype(np.uint8)


def ring(mask, face=None, frac=0.15):
    """Bool ring around the mask, ~frac × head size wide."""
    import cv2
    np = _np()
    x, y, w, h = face_box(mask, face)
    r = max(3, int(frac * max(w, h)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    inside = (mask > 0.05).astype(np.uint8)
    return (cv2.dilate(inside, k) > 0) & (inside == 0)


def grown(mask, face=None, frac=0.15, feather=None):
    """Float mask grown by a ring of ~frac × head size, feathered (the harmonise pass's mask)."""
    import cv2
    np = _np()
    x, y, w, h = face_box(mask, face)
    r = max(3, int(frac * max(w, h)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    g = cv2.dilate((mask > 0.05).astype(np.uint8) * 255, k)
    f = int(feather if feather is not None else max(1, r // 2)) * 2 + 1
    return cv2.GaussianBlur(g, (f, f), 0).astype(np.float32) / 255.0


def noise_stats(bgr, region):
    """(noise std, sharpness) in a region: std of the luma high-pass (image − 3×3 blur) and the Laplacian variance."""
    import cv2
    np = _np()
    y = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = y - cv2.GaussianBlur(y, (0, 0), 1.0)
    lap = cv2.Laplacian(y, cv2.CV_32F)
    if region.sum() < 16:
        return 0.0, 0.0
    return float(hp[region].std()), float(lap[region].var())


def grain_match(result, target, mask, face=None, strength=1.0, seed=0):
    """Make the swapped region as noisy / soft as the original around the face: slight blur or unsharp mask when
    the sharpness differs, then luma grain with the missing high-pass energy."""
    import cv2
    np = _np()
    if strength <= 0:
        return result
    rg = ring(mask, face)
    inside = mask > 0.5
    t_noise, t_sharp = noise_stats(target, rg)
    r_noise, r_sharp = noise_stats(result, inside)
    if rg.sum() < 16 or inside.sum() < 16:
        return result
    out = result.astype(np.float32)
    if r_sharp > 0 and t_sharp > 0:
        ratio = t_sharp / r_sharp
        if ratio < 0.6:     # original is softer: blur the face a little
            out = cv2.GaussianBlur(out, (0, 0), float(np.clip(0.6 * (1 / ratio) ** 0.5 - 0.3, 0.3, 2.0)) * strength)
        elif ratio > 1.6:   # original is crisper: unsharp mask
            amt = float(np.clip((ratio ** 0.5 - 1) * 0.5, 0, 1.0)) * strength
            out = cv2.addWeighted(out, 1 + amt, cv2.GaussianBlur(out, (0, 0), 1.0), -amt, 0)
    tmp = np.clip(out, 0, 255).astype(np.uint8)
    r_noise, _ = noise_stats(tmp, inside)
    hp_gain = 1.0
    need = (t_noise ** 2 - r_noise ** 2)
    if need > 0:
        sigma = float(np.sqrt(need) / max(hp_gain, 1e-3) ** 0.5) * float(min(1.0, strength))
        rng = np.random.default_rng(seed)
        n = rng.normal(0, sigma, out.shape[:2]).astype(np.float32)
        out = out + n[:, :, None]
    a = np.clip(mask, 0, 1)[:, :, None]
    return np.clip(result * (1 - a) + out * a, 0, 255).astype(np.uint8)


def calibrate_grain(result, target, mask, face=None, strength=1.0, seed=0, rounds=3):
    """grain_match, re-measured and corrected a few times so the noise level lands on the target's."""
    np = _np()
    out = grain_match(result, target, mask, face, strength, seed)
    inside, rg = mask > 0.5, ring(mask, face)
    t_noise = noise_stats(target, rg)[0]
    for i in range(rounds):
        cur = noise_stats(out, inside)[0]
        if t_noise <= 0 or cur <= 0 or abs(cur - t_noise) / t_noise < 0.08 or cur > t_noise:
            break
        out = grain_match(out, target, mask, face, strength, seed + i + 1)
    return out.astype(np.uint8)


def _pyr_blend(a, b, m, levels=5):
    import cv2
    np = _np()
    h, w = a.shape[:2]
    levels = max(1, min(levels, int(np.log2(max(2, min(h, w)))) - 2))
    ga, gb, gm = [a.astype(np.float32)], [b.astype(np.float32)], [m.astype(np.float32)]
    for _ in range(levels):
        ga.append(cv2.pyrDown(ga[-1])); gb.append(cv2.pyrDown(gb[-1])); gm.append(cv2.pyrDown(gm[-1]))
    out = None
    for i in range(levels, -1, -1):
        if i == levels:
            la, lb = ga[i], gb[i]
        else:
            size = (ga[i].shape[1], ga[i].shape[0])
            la = ga[i] - cv2.pyrUp(ga[i + 1], dstsize=size)
            lb = gb[i] - cv2.pyrUp(gb[i + 1], dstsize=size)
        mm = gm[i][:, :, None]
        lev = la * mm + lb * (1 - mm)
        out = lev if out is None else cv2.pyrUp(out, dstsize=(lev.shape[1], lev.shape[0])) + lev
    return out


def seam_blend(result, target, mask, mode="Laplacian"):
    """Composite `result` (any size – it is resized to the target) onto the ORIGINAL target with the soft mask.
    Laplacian pyramid or Poisson (cv2.seamlessClone) inside; outside the mask the original pixels are copied
    exactly. Output = the target's size."""
    import cv2
    np = _np()
    H, W = target.shape[:2]
    if result.shape[:2] != (H, W):
        result = cv2.resize(result, (W, H), interpolation=cv2.INTER_LANCZOS4 if result.shape[0] < H else cv2.INTER_AREA)
    if mask.shape[:2] != (H, W):
        mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_LINEAR)
    m = np.clip(mask, 0, 1).astype(np.float32)
    if mode == "Off":
        out = result * m[:, :, None] + target * (1 - m[:, :, None])
    elif mode.startswith("Poisson"):
        hard = (m > 0.5).astype(np.uint8) * 255
        ys, xs = np.nonzero(hard)
        out = target.astype(np.float32)
        if len(xs) and xs.min() > 0 and ys.min() > 0 and xs.max() < W - 1 and ys.max() < H - 1:
            centre = (int((xs.min() + xs.max() + 1) // 2), int((ys.min() + ys.max() + 1) // 2))
            flag = cv2.MIXED_CLONE if "mixed" in mode.lower() else cv2.NORMAL_CLONE
            try:
                cloned = cv2.seamlessClone(result, target, hard, centre, flag).astype(np.float32)
                out = cloned * m[:, :, None] + target * (1 - m[:, :, None])
            except cv2.error:
                out = _pyr_blend(result, target, m)
        else:  # touches the border – seamlessClone can't, use the pyramid
            out = _pyr_blend(result, target, m)
    else:
        out = _pyr_blend(result, target, m)
    out = np.clip(out, 0, 255).astype(np.uint8)
    keep = m <= 0.0
    out[keep] = target[keep]   # unmasked pixels: exactly the original
    return out


def blend(result_png, target_png, mask_png, face=None, opts=None):
    """Run colour match → grain match → seam blend. `result_png` may be the ~1 MP render; the output has the
    original target's size. face = (x, y, w, h) in target pixels or None (the mask's box)."""
    import cv2
    o = dict(DEFAULTS); o.update(opts or {})
    target = decode(target_png)
    H, W = target.shape[:2]
    res = decode(result_png)
    if res.shape[:2] != (H, W):
        res = cv2.resize(res, (W, H), interpolation=cv2.INTER_LANCZOS4 if res.shape[0] < H else cv2.INTER_AREA)
    m = mask_f(mask_png, W, H)
    if not o.get("on", True):
        return encode(seam_blend(res, target, m, "Off"))
    if o.get("colour"):
        res = colour_match(res, target, m, face, float(o.get("colour_strength", 0.8)))
    if o.get("grain"):
        res = calibrate_grain(res, target, m, face, float(o.get("grain_strength", 1.0)))
    return encode(seam_blend(res, target, m, o.get("seam_mode", "Laplacian") if o.get("seam") else "Off"))


def harmonise_mask_png(mask_png, w, h, face=None, frac=0.15):
    """The harmonise pass's mask at the render size: the swap mask grown by a ~15 % head-size ring."""
    np = _np()
    m = mask_f(mask_png, w, h)
    return encode((grown(m, face, frac) * 255).astype(np.uint8))
