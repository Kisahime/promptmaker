"""6.1: ADetailer passes for Forge / A1111: payload, detector list, Settings controls and the Video maker tick.

No real Forge: _http is monkeypatched, and no image is generated."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import imagegen  # noqa: E402
from promptmaker.imagegen import A1111, BackendError, Job  # noqa: E402
import test_v5  # noqa: E402

win = test_v5.win
FACE, HAND = imagegen.AD_FACE, imagegen.AD_HAND


class _Store(dict):
    def get(self, k, d=None):
        return super().get(k, d)


def _job(ad=None):
    j = Job("a cat", "", 512, 512, 1, 20, 6.0, "x", "")
    j.adetailer = ad
    return j


def _ad(job):
    return A1111("http://127.0.0.1:9").payload(job).get("alwayson_scripts", {}).get("ADetailer")


def test_disabled_sends_nothing():
    for v in (None, "", [], [{"ad_model": ""}, {"ad_model": "None"}]):
        assert _ad(_job(v)) is None
    assert "adetailer" not in _job().meta()


def test_legacy_string_is_unchanged():
    assert _ad(_job("face_yolov8s.pt")) == {"args": [True, False, {"ad_model": "face_yolov8s.pt"}]}


def test_one_pass_gets_defaults():
    args = _ad(_job([{"ad_model": FACE, "ad_prompt": "   ", "ad_negative_prompt": ""}]))["args"]
    assert args[:2] == [True, False] and len(args) == 3
    assert args[2] == {"ad_model": FACE, "ad_denoising_strength": 0.4, "ad_confidence": 0.3,
                       "ad_inpaint_only_masked": True, "ad_inpaint_padding": 32}


def test_two_passes_and_cap():
    passes = [{"ad_model": FACE, "ad_denoising_strength": 0.35, "ad_confidence": 0.5, "ad_prompt": " detailed eyes ",
               "ad_negative_prompt": "blurry"},
              {"ad_model": HAND, "ad_denoising_strength": "0.5"},
              {"ad_model": "person_yolov8n-seg.pt"}]
    args = _ad(_job(passes))["args"]
    assert len(args) == 4  # enable, skip_img2img, 2 passes (the third is dropped)
    assert args[2]["ad_prompt"] == "detailed eyes" and args[2]["ad_negative_prompt"] == "blurry"
    assert args[2]["ad_denoising_strength"] == 0.35 and args[2]["ad_confidence"] == 0.5
    assert args[3]["ad_model"] == HAND and args[3]["ad_denoising_strength"] == 0.5 and "ad_prompt" not in args[3]
    assert imagegen.adetailer_passes({"ad_model": HAND})[0]["ad_model"] == HAND  # a single dict works too


def test_inpaint_job_keeps_adetailer():
    j = _job([{"ad_model": FACE}])
    j.inpaint = {"image": b"x", "mask": b"y"}
    assert A1111("http://127.0.0.1:9").payload(j)["alwayson_scripts"]["ADetailer"]["args"][2]["ad_model"] == FACE


def test_meta_records_passes():
    m = _job([{"ad_model": FACE, "ad_denoising_strength": 0.35, "ad_prompt": "detailed eyes"},
              {"ad_model": HAND}]).meta()
    assert m["adetailer"] == [{"model": FACE, "denoise": 0.35, "prompt": "detailed eyes"}, {"model": HAND, "denoise": 0.4}]
    json.dumps(m)
    assert _job("face_yolov8s.pt").meta()["adetailer"] == [{"model": FACE, "denoise": 0.4}]


def test_model_list_and_cache(monkeypatch):
    calls = []

    def fake(url, data=None, timeout=30, **_k):
        calls.append(url)
        return {"ad_model": [FACE, HAND, "None", ""]}
    monkeypatch.setattr(imagegen, "_http", fake); monkeypatch.setattr(imagegen, "_AD_CACHE", {})
    be = A1111("http://fake:1")
    assert be.adetailer_models() == [FACE, HAND] and be.has_adetailer()
    assert A1111("http://fake:1/").adetailer_models() == [FACE, HAND]
    assert calls == ["http://fake:1/adetailer/v1/ad_model"]  # cached per URL
    be.adetailer_models(refresh=True)
    assert len(calls) == 2


def test_model_list_fallbacks(monkeypatch):
    monkeypatch.setattr(imagegen, "_AD_CACHE", {})
    calls = []

    def old(url, data=None, timeout=30, **_k):  # older ADetailer: no route, but the script is installed
        calls.append(url)
        if url.endswith("/adetailer/v1/ad_model"):
            raise BackendError("HTTP 404 from x: Not Found")
        return {"txt2img": ["ADetailer", "controlnet"], "img2img": []}
    monkeypatch.setattr(imagegen, "_http", old)
    assert A1111("http://old:1").adetailer_models() == list(imagegen.AD_DEFAULT_MODELS)

    def missing(url, data=None, timeout=30, **_k):
        if url.endswith("/adetailer/v1/ad_model"):
            raise BackendError("HTTP 404 from x: Not Found")
        return {"txt2img": ["controlnet"]}
    monkeypatch.setattr(imagegen, "_http", missing)
    assert A1111("http://bare:1").adetailer_models() == []

    calls.clear()

    def offline(url, data=None, timeout=30, **_k):
        calls.append(url)
        raise BackendError("Can't reach it")
    monkeypatch.setattr(imagegen, "_http", offline)
    assert A1111("http://off:1").adetailer_models() == [] and len(calls) == 1  # no second request when Forge is down
    monkeypatch.setattr(imagegen, "_http", lambda *a, **k: ["not", "a", "dict"])
    assert A1111("http://odd:1").adetailer_models() == []


def test_from_store():
    assert imagegen.adetailer_from_store(_Store()) is None
    forced = imagegen.adetailer_passes(imagegen.adetailer_from_store(_Store(), force=True))
    assert [p["ad_model"] for p in forced] == [FACE]
    s = _Store(ad_on=True, ad_model="mediapipe_face_full", ad_denoise=0.3, ad_confidence=0.45, ad_prompt="freckles",
               ad2_on=True, ad2_model=HAND, ad2_denoise=0.5)
    p = imagegen.adetailer_passes(imagegen.adetailer_from_store(s))
    assert [x["ad_model"] for x in p] == ["mediapipe_face_full", HAND]
    assert p[0]["ad_denoising_strength"] == 0.3 and p[0]["ad_confidence"] == 0.45 and p[0]["ad_prompt"] == "freckles"
    assert p[1]["ad_denoising_strength"] == 0.5 and p[1]["ad_confidence"] == 0.3
    s["ad2_on"] = False
    assert len(imagegen.adetailer_from_store(s)) == 1


def _forge(win):
    win.img_kind.setCurrentIndex(win.img_kind.findData("a1111"))


def test_settings_controls_exist_and_grey_out(win):
    for n in ("ad_on", "ad_reload", "ad_model", "ad_denoise", "ad_conf", "ad_prompt", "ad2_on", "ad2_model", "ad2_denoise", "ad_note"):
        assert hasattr(win, n), n
    win.img_kind.setCurrentIndex(win.img_kind.findData("comfyui"))
    assert not win.ad_on.isEnabled() and not win.ad_reload.isEnabled() and "Forge" in win.ad_note.text()
    _forge(win)
    assert win.ad_on.isEnabled() and win.ad_reload.isEnabled()
    assert not win.ad_box.isEnabled()  # only once ADetailer is ticked
    win.ad_on.setChecked(True)
    assert win.ad_box.isEnabled() and not win.ad2_model.isEnabled()
    win.ad2_on.setChecked(True)
    assert win.ad2_model.isEnabled()
    win._ad_models_loaded([])
    assert not win.ad_on.isEnabled() and not win.ad_box.isEnabled() and win.ad_reload.isEnabled()
    assert "wasn't found" in win.ad_note.text() and win.ad_on.toolTip()
    win._ad_models_loaded([HAND, "mediapipe_face_mesh", FACE])
    assert win.ad_on.isEnabled() and win.ad_box.isEnabled() and "3" in win.ad_note.text()
    assert win.ad_model.currentText() == FACE and win.ad2_model.currentText() == HAND


def test_settings_persist_and_reach_the_job(win):
    _forge(win)
    win.ad_on.setChecked(True)
    win._ad_models_loaded([FACE, HAND, "mediapipe_face_full"])
    win.ad_model.setCurrentText("mediapipe_face_full")
    win.ad_denoise.setValue(0.35); win.ad_conf.setValue(0.4); win.ad_prompt.setText("detailed eyes")
    win.ad2_on.setChecked(True); win.ad2_denoise.setValue(0.5)
    win._img_save()
    st = win.store
    assert st.get("ad_on") is True and st.get("ad_model") == "mediapipe_face_full" and st.get("ad_prompt") == "detailed eyes"
    assert abs(st.get("ad_denoise") - 0.35) < 1e-6 and abs(st.get("ad_confidence") - 0.4) < 1e-6
    assert st.get("ad2_on") is True and st.get("ad2_model") == HAND and abs(st.get("ad2_denoise") - 0.5) < 1e-6
    st.set("img_url:a1111", "http://127.0.0.1:9")
    job = win.make_job("a cat")[0]
    args = imagegen.adetailer_args(job.adetailer)
    assert [p["ad_model"] for p in args[2:]] == ["mediapipe_face_full", HAND] and args[2]["ad_prompt"] == "detailed eyes"
    win.ad_on.setChecked(False); win._img_save()
    assert win.make_job("a cat")[0].adetailer is None
    st.set("img_backend", "comfyui"); st.set("ad_on", True)
    made = win.make_job("a cat")
    assert made is None or getattr(made[0], "adetailer", None) is None  # Forge only


def test_settings_reload_after_restart(win, tmp_path):
    from promptmaker.app import MainWindow
    win.store.set("ad_on", True); win.store.set("ad_model", "face_yolov8n.pt"); win.store.set("ad_denoise", 0.25)
    win.store.set("ad2_on", True); win.store.set("ad2_model", "hand_yolov8s.pt")
    w2 = MainWindow(win.store, str(tmp_path))
    try:
        assert w2.ad_on.isChecked() and w2.ad_model.currentText() == "face_yolov8n.pt"
        assert abs(w2.ad_denoise.value() - 0.25) < 1e-6 and w2.ad2_on.isChecked() and w2.ad2_model.currentText() == "hand_yolov8s.pt"
    finally:
        w2.close()


def test_video_maker_uses_settings(win):
    forge = A1111("http://127.0.0.1:9")
    win.vm_ad.setChecked(False)
    assert win._vm_adetailer(forge) is None
    win.vm_ad.setChecked(True)
    assert [p["ad_model"] for p in imagegen.adetailer_passes(win._vm_adetailer(forge))] == [FACE]  # nothing saved yet
    win.store.set("ad_model", "mediapipe_face_full"); win.store.set("ad2_on", True); win.store.set("ad2_model", HAND)
    assert [p["ad_model"] for p in imagegen.adetailer_passes(win._vm_adetailer(forge))] == ["mediapipe_face_full", HAND]
    assert win._vm_adetailer(imagegen.ComfyUI("http://127.0.0.1:9")) is None
    assert win.vm_ad.toolTip()


def test_face_swap_drops_adetailer():
    from promptmaker import faceswap
    j = _job([{"ad_model": FACE}])
    faceswap.harmonise_job(j, _png(), _png())
    assert j.adetailer is None


def _png():
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    img = QImage(64, 64, QImage.Format_RGB32); img.fill(QColor("white"))
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    return bytes(buf.data())
