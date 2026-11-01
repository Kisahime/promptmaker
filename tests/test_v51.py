"""Tests for 5.1: Face Swap (Fooocus-style face IP-Adapter with face + hair crop and mask)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import faceswap as fs, imagegen  # noqa: E402
import test_v5  # noqa: E402

_app, _wait = test_v5._app, test_v5._wait
win, srv = test_v5.win, test_v5.srv


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _portrait(w=512, h=640):
    """Synthetic 'head': skin oval with dark hair around it on a light background (no real person)."""
    _qapp()
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from promptmaker.regions import _png
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor("#dfe8f0"))
    p = QPainter(im); p.setRenderHint(QPainter.Antialiasing); p.setPen(QColor("#3a2416"))
    p.setBrush(QColor("#3a2416")); p.drawEllipse(QRectF(140, 90, 232, 330)); p.drawRect(QRectF(150, 250, 212, 220))
    p.setBrush(QColor("#f1c7a8")); p.setPen(QColor("#f1c7a8")); p.drawEllipse(QRectF(186, 170, 140, 180))
    p.end()
    return _png(im)


FACE = (190, 180, 132, 160)


def test_fooocus_defaults_and_model_pick():
    assert (fs.STOP_AT, fs.WEIGHT) == (0.9, 0.75)
    assert fs.classify("ip-adapter-plus-face_sdxl_vit-h [abc]") == "plus_face"
    assert fs.classify("ip-adapter-faceid-plusv2_sdxl") == "faceid_v2"
    assert fs.classify("ip-adapter-plus_sdxl_vit-h") == "plus" and fs.classify("control_canny") == ""
    ms = ["ip-adapter_sd15", "ip-adapter-plus_sdxl_vit-h", "ip-adapter-plus-face_sd15", "ip-adapter-plus-face_sdxl_vit-h"]
    assert fs.pick_model(ms) == ("ip-adapter-plus-face_sdxl_vit-h", "plus_face")
    assert fs.pick_model(["control_canny"]) == ("", "")
    assert "Anima" in fs.family_warning({"family": "anima"}) and fs.family_warning({"family": "sdxl"}) == ""
    h = fs.install_help("forge")
    assert "ip-adapter-plus-face_sdxl_vit-h.safetensors" in h and "models\\ControlNet" in h and "huggingface.co" in h
    assert "models\\ipadapter" in fs.install_help("comfy") and "models\\clip_vision" in fs.install_help("comfy")


def test_forge_payload_has_face_unit_and_inpaint():
    _qapp()
    face, _box = fs.crop_face(_portrait(), FACE)
    j = imagegen.Job("adult woman, park", "", 1024, 1024, 5)
    fs.apply_to_job(j, face, "ip-adapter-plus-face_sdxl_vit-h", "plus_face", target_png=_portrait(), mask_png=fs.auto_mask(_portrait(), FACE))
    p = imagegen.A1111("http://x").payload(j)
    u = p["alwayson_scripts"]["controlnet"]["args"][-1]
    assert u["module"] == "CLIP-ViT-H (IPAdapter)" and u["guidance_end"] == 0.9 and u["weight"] == 0.75 and u["image"]
    assert p["denoising_strength"] == pytest.approx(0.8) and p["inpaint_full_res"] and p["init_images"] and p["mask"]
    assert (j.width, j.height) == (512, 640) and j.reference is None
    j2 = imagegen.Job("x", "", 1024, 1024, 5)
    fs.apply_to_job(j2, face, "ip-adapter-faceid-plusv2_sdxl", "faceid_v2")
    u2 = imagegen.A1111("http://x").payload(j2)["alwayson_scripts"]["controlnet"]["args"][-1]
    assert u2["module"] == "InsightFace+CLIP-H (IPAdapter)" and j2.inpaint is None


def test_comfy_face_nodes():
    wf = {"3": {"class_type": "KSampler", "inputs": {"model": ["4", 0]}}, "4": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    out = fs.add_comfy_face(wf, "face.png", 0.75, 0.9)
    loader = next(n for n in out.values() if n["class_type"] == "IPAdapterUnifiedLoader")
    ap = next(n for n in out.values() if n["class_type"] == "IPAdapter")
    assert loader["inputs"]["preset"] == "PLUS FACE (portraits)" and ap["inputs"]["end_at"] == 0.9 and ap["inputs"]["weight"] == 0.75
    assert out["3"]["inputs"]["model"][0] != "4" and wf["3"]["inputs"]["model"] == ["4", 0]
    fid = fs.add_comfy_face(wf, "face.png", kind="faceid_v2")
    assert any(n["class_type"] == "IPAdapterFaceID" for n in fid.values())
    with pytest.raises(ValueError):
        fs.add_comfy_face({}, "x.png")


def test_crop_keeps_hair_and_pads():
    from promptmaker.imagegen import png_size
    png = _portrait()
    face, box = fs.crop_face(png, FACE, 2.2, 512)
    assert png_size(face) == (512, 512)
    x, y, w, h = box
    assert w == int(160 * 2.2) and y < 90 + 20 and x < 150  # reaches the top of the hair and its sides
    tight = fs.crop_box(FACE, 512, 640, 1.6)
    assert tight[2] < w
    edge, ebox = fs.crop_face(png, (0, 0, 120, 120), 3.0, 256)  # off-image parts padded, no crash
    assert png_size(edge) == (256, 256) and ebox[0] < 0


@pytest.mark.parametrize("opencv", [True, False])
def test_auto_mask_covers_face_and_hair(monkeypatch, opencv):
    _qapp()
    if opencv and not fs.cv2_available():
        pytest.skip("OpenCV not installed")
    if not opencv:
        monkeypatch.setattr(fs, "cv2_available", lambda: False)
    from PySide6.QtGui import QColor
    from promptmaker.regions import _qimage, mask_coverage
    png = _portrait()
    m = fs.auto_mask(png, FACE, "Long", grow=8, feather=4, refine=opencv)
    img = _qimage(m)
    white = lambda x, y: QColor(img.pixel(x, y)).red() > 200  # noqa: E731
    assert white(256, 260) and white(256, 120) and white(160, 400)   # face, top of hair, long hair at the side
    assert not white(20, 20) and not white(500, 630)                 # background stays
    assert 0.1 < mask_coverage(m) < 0.6
    small = fs.auto_mask(png, FACE, "Short", grow=0, feather=0, refine=False)
    assert mask_coverage(small) < mask_coverage(m)
    a = fs.mask_to_alpha(m)
    assert a.width() == 512 and a.pixelColor(256, 260).alpha() > 200 and a.pixelColor(10, 10).alpha() == 0


def test_vision_box_parse():
    assert fs.parse_vision_box('{"bbox_2d": [100, 50, 300, 260]}', 512, 512) == (100, 50, 200, 210)
    assert fs.parse_vision_box("[0.25, 0.1, 0.75, 0.6]", 400, 400) == (100, 40, 200, 200)
    assert fs.parse_vision_box("no face", 100, 100) is None
    assert fs.vision_messages(b"x")[0]["images"]


def test_detect_forge_and_comfy(srv, monkeypatch):
    s, url = srv(["control_canny", "ip-adapter-plus-face_sdxl_vit-h [1234]"])
    d = fs.detect(imagegen.A1111(url))
    assert d["kind"] == "forge" and d["type"] == "plus_face" and not d["problem"]
    s2, url2 = srv(["control_canny"])
    d2 = fs.detect(imagegen.A1111(url2))
    assert d2["kind"] == "forge" and not d2["model"] and "ControlNet" in d2["problem"]
    info = {"IPAdapterModelLoader": {"input": {"required": {"ipadapter_file": [["ip-adapter-plus-face_sdxl_vit-h.safetensors"]]}}}}
    monkeypatch.setattr(imagegen, "_http", lambda *a, **k: info)
    d3 = fs.detect(imagegen.ComfyUI("http://x"))
    assert d3["kind"] == "comfy" and d3["type"] == "plus_face"
    assert fs.detect(None)["problem"]


def test_face_swap_page_generate_and_swap(win, srv, tmp_path):
    s, url = srv(["ip-adapter-plus-face_sdxl_vit-h"])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    from promptmaker.app import NAV
    assert "Face Swap" in [n for _i, n in NAV]
    win.go("Face Swap"); _app().processEvents(); assert win.page_name() == "Face Swap"
    assert win.fs_generate() is None and "source face" in win.fs_status.text().lower()
    win.fs_set_source(_portrait())
    win.fs_face_box = FACE; win.fs_recrop()
    assert win.fs_face_png and "Face found" in win.fs_src_status.text()
    assert win.fs_check()["model"] == "ip-adapter-plus-face_sdxl_vit-h" and "✓" in win.fs_status.text()
    win.fs_prompt.setText("adult woman, smiling, park, watercolor")
    assert win.fs_generate() is not None
    assert _wait(lambda: win.fs_png is not None, 10)
    assert s.last_endpoint == "/sdapi/v1/txt2img"
    assert s.last_payload["alwayson_scripts"]["controlnet"]["args"][-1]["guidance_end"] == 0.9
    # swap mode: target + auto mask (face given, detector not needed) + brush fix
    win.fs_mode.setCurrentIndex(1)
    win.fs_canvas.set_image(_portrait()); win.fs_target_face = FACE
    assert win.fs_remask() and win.fs_canvas.has_mask()
    win.fs_png = None; win.fs_generate()
    assert _wait(lambda: win.fs_png is not None, 10)
    assert s.last_endpoint == "/sdapi/v1/img2img" and s.last_payload["mask"] and s.last_payload["inpaint_full_res"]
    assert win.fs_save() and win.fs_result_to_target()


def test_character_reference_to_face_swap(win, tmp_path):
    from test_v5 import _png_file
    win.go("Characters")
    win.cr_new(); win.cr_name.setText("Mika"); win.cr_app.setPlainText("adult woman, short silver hair")
    win._cr_add_ref(_png_file(tmp_path / "ref.png", "#f1c7a8", 256, 256))
    win.cr_save()
    assert win.cr_to_faceswap() is not None
    assert win.page_name() == "Face Swap" and win.fs_char.currentText() == "Mika" and "silver hair" in win.fs_prompt.text()


def test_anima_profile_blocks_swap(win, srv):
    s, url = srv(["ip-adapter-plus-face_sdxl_vit-h"])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Face Swap"); win.fs_set_source(_portrait())
    win.profile_combo.setCurrentIndex(win.profile_combo.findData("anima"))
    assert win.profile["family"] == "Anima"
    assert win.fs_generate() is None and "Anima" in win.fs_status.text()
