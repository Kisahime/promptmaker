"""Tests for 5.1 Face Swap Auto-blend (synthetic images only)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
from promptmaker import faceblend as fb, faceswap as fs, imagegen  # noqa: E402
import test_v5  # noqa: E402

_app, _wait = test_v5._app, test_v5._wait
win, srv = test_v5.win, test_v5.srv

W, H = 900, 1200          # "large photo" – bigger than the ~1 MP render
FACE = (330, 380, 240, 300)


def _target(noise=6.0, skin=(150, 175, 220), seed=1):
    rng = np.random.default_rng(seed)
    img = np.zeros((H, W, 3), np.float32); img[:] = (200, 190, 170)
    img[:, :, 0] += np.linspace(0, 30, W)[None, :]
    cv2.ellipse(img, (450, 470), (150, 200), 0, 0, 360, (40, 50, 70), -1)        # hair
    cv2.ellipse(img, (450, 540), (115, 150), 0, 0, 360, skin, -1)             # face skin
    img += rng.normal(0, noise, (H, W))[:, :, None]
    return np.clip(img, 0, 255).astype(np.uint8)


def _mask():
    m = np.zeros((H, W), np.uint8)
    cv2.ellipse(m, (450, 480), (165, 215), 0, 0, 360, 255, -1)
    return cv2.GaussianBlur(m, (25, 25), 0)


def _render(target, shift=(40, -30, -40)):
    """The 'swap' result: ~1 MP, clean (no grain), colour-shifted face."""
    r = cv2.resize(cv2.GaussianBlur(target, (0, 0), 2.0), (768, 1024), interpolation=cv2.INTER_AREA).astype(np.float32)
    rm = cv2.resize(_mask(), (768, 1024)) > 128
    r[rm] += shift
    return np.clip(r, 0, 255).astype(np.uint8)


def test_colour_shift_corrected():
    t = _target(noise=0); m = _mask().astype(np.float32) / 255
    res = cv2.resize(_render(t), (W, H))
    skin = fb.skin_region(t, m, FACE)
    before = np.abs(res[skin].astype(float).mean(0) - t[skin].astype(float).mean(0)).max()
    out = fb.colour_match(res, t, m, FACE, 1.0)
    after = np.abs(out[skin].astype(float).mean(0) - t[skin].astype(float).mean(0)).max()
    assert before > 25 and after < 6


def test_blend_keeps_size_and_unmasked_pixels():
    t = _target(); mpng = fb.encode(_mask())
    for mode in ("Laplacian", "Poisson", "Poisson (mixed)"):
        out = fb.decode(fb.blend(fb.encode(_render(t)), fb.encode(t), mpng, FACE, {"harmonise": False, "seam_mode": mode}))
        assert out.shape == t.shape
        outside = _mask() == 0
        assert np.array_equal(out[outside], t[outside])
        inside = _mask() == 255
        assert not np.array_equal(out[inside], t[inside])   # the face did change


def test_grain_level_matched():
    t = _target(noise=8.0); m = _mask().astype(np.float32) / 255
    res = cv2.resize(_render(t, (0, 0, 0)), (W, H))
    inside, ring = m > 0.5, fb.ring(m, FACE)
    tn = fb.noise_stats(t, ring)[0]
    assert fb.noise_stats(res, inside)[0] < 0.5 * tn
    out = fb.calibrate_grain(res, t, m, FACE, 1.0)
    assert fb.noise_stats(out, inside)[0] == pytest.approx(tn, rel=0.2)


def test_harmonise_payload_mock_forge():
    t = _target(); raw = fb.encode(_render(t)); mpng = fb.encode(_mask())
    j = imagegen.Job("adult woman, park", "", 1024, 1024, 5)
    face = fb.scale_box(FACE, 768 / W, 1024 / H)
    fs.harmonise_job(j, raw, mpng, face, 0.25)
    p = imagegen.A1111("http://x").payload(j)
    assert p["denoising_strength"] == pytest.approx(0.25) and p["inpaint_full_res"] and p["init_images"] and p["mask"]
    args = (p.get("alwayson_scripts") or {}).get("controlnet", {}).get("args", [])
    assert not any("IPAdapter" in str(a.get("module", "")) for a in args)
    hm = fb.decode(__import__("base64").b64decode(p["mask"]), cv2.IMREAD_GRAYSCALE)
    assert hm.shape == (1024, 768)
    sw = cv2.resize(_mask(), (768, 1024))
    assert (hm > 127).sum() > (sw > 127).sum() * 1.2      # grown by the ring


def test_page_swap_blends_with_harmonise(win, srv):
    s, url = srv(["ip-adapter-plus-face_sdxl_vit-h"])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Face Swap"); _app().processEvents()
    t = _target()
    win.fs_set_source(fb.encode(t)); win.fs_face_box = FACE; win.fs_recrop()
    assert win.fs_check()["model"]
    win.fs_mode.setCurrentIndex(1)
    assert win.fs_blend_box.isVisibleTo(win) and win.fs_blend_box.isChecked()
    assert all(c.isChecked() for c in (win.fs_bl_colour, win.fs_bl_seam, win.fs_bl_harm, win.fs_bl_grain))
    assert "extra generation" in win.fs_bl_harm.toolTip()
    win.fs_canvas.set_image(fb.encode(t)); win.fs_target_face = FACE
    win.fs_canvas.mask = fs.mask_to_alpha(fb.encode(_mask())); assert win.fs_canvas.has_mask()
    win.fs_png = None; win.fs_generate()
    assert _wait(lambda: win.fs_png is not None, 20)
    assert s.last_endpoint == "/sdapi/v1/img2img" and s.last_payload["denoising_strength"] == pytest.approx(0.25)
    assert imagegen.png_size(win.fs_png) == (W, H)
    assert win.fs_before.isEnabled()
    win.fs_before.setChecked(True); win.fs_before.setChecked(False)
