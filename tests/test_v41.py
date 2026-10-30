"""4.1.0: status, queue view, gallery actions, upscale, per-profile image settings, look & feel, live preview."""
import base64
import json
import os
import time

import test_v4
from promptmaker import imagegen, theme
from promptmaker.imagegen import A1111, ComfyUI, Job
from promptmaker.widgets import GenQueue

win = test_v4.win  # shared fixtures
srv = test_v4.srv


def _png(w=64, h=48):
    return test_v4._img(w, h)


def _pump(pred, timeout=5):
    from PySide6.QtWidgets import QApplication
    t = time.time()
    while not pred() and time.time() - t < timeout:
        QApplication.processEvents(); time.sleep(0.02)
    QApplication.processEvents()


# ---------------------------------------------------------------- backend units (mock HTTP)
def test_status_a1111_and_comfy(monkeypatch):
    def fake(url, data=None, timeout=30, **k):
        assert timeout <= 3  # cheap poll
        if url.endswith("/sdapi/v1/options"):
            return {"sd_model_checkpoint": "lustify.safetensors [abc]"}
        if url.endswith("/system_stats"):
            return {"system": {"comfyui_version": "0.3"}}
        raise imagegen.BackendError("offline")
    monkeypatch.setattr(imagegen, "_http", fake)
    assert A1111().status() == ("online", "lustify.safetensors [abc]")
    assert ComfyUI().status()[1].startswith("ComfyUI 0.3")


def test_upscale_payloads(monkeypatch):
    monkeypatch.setattr(imagegen, "_http", lambda *a, **k: [])
    j = Job("a cat", "", 64, 48, 5, 20, 6.0, "x", "ck.safetensors")
    j.hires = {"scale": 2}
    j.upscale = {"image": _png(64, 48), "scale": 1.5, "upscaler": "4x-UltraSharp", "denoise": 0.3, "source": "/g/a.png"}
    ep, p = A1111().upscale_payload(j)
    assert ep == "/sdapi/v1/img2img" and (p["width"], p["height"]) == (96, 72)
    assert p["denoising_strength"] == 0.3 and p["seed"] == 5 and p["prompt"] == "a cat" and "enable_hr" not in p
    assert p["init_images"] and p["override_settings"]["upscaler_for_img2img"] == "4x-UltraSharp"
    j.upscale["denoise"] = 0
    ep, p = A1111().upscale_payload(j)
    assert ep == "/sdapi/v1/extra-single-image" and p["upscaling_resize"] == 1.5 and p["upscaler_1"] == "4x-UltraSharp"
    m = j.meta()
    assert m["source_image"] == "/g/a.png" and m["upscaled"] == 1.5 and m["upscale_mode"] == "pure"


def test_pure_upscale_generate_uses_extras(monkeypatch):
    calls = []

    def fake(url, data=None, timeout=30, **k):
        calls.append(url)
        if "extra-single-image" in url:
            return {"image": base64.b64encode(test_v4.PNG).decode()}
        if "progress" in url:
            return {"progress": 0.5, "current_image": base64.b64encode(test_v4.PNG).decode()}
        return {}
    monkeypatch.setattr(imagegen, "_http", fake)
    monkeypatch.setattr(imagegen, "BEFORE_GENERATE", [])
    j = Job("p", "", 64, 48, 1); j.upscale = {"image": _png(), "scale": 2, "denoise": 0}
    assert A1111().generate(j, progress=lambda *a: None) == [test_v4.PNG]
    assert any("extra-single-image" in c for c in calls)


def test_comfy_pure_upscale_workflow_and_refuses_denoise(monkeypatch):
    c = ComfyUI(); sent = {}
    monkeypatch.setattr(c, "upload_image", lambda png, name: "up.png")

    def fake(url, data=None, timeout=30, **k):
        if url.endswith("/prompt"):
            sent.update(data["prompt"]); return {"prompt_id": "p"}
        if "/history/" in url:
            return {"p": {"status": {"completed": True}, "outputs": {"3": {"images": [{"filename": "a.png"}]}}}}
        return test_v4.PNG
    monkeypatch.setattr(imagegen, "_http", fake); monkeypatch.setattr(imagegen, "BEFORE_GENERATE", [])
    j = Job("p", "", 64, 48, 1); j.upscale = {"image": _png(), "scale": 2.0, "denoise": 0}
    assert c.generate(j, {}) == [test_v4.PNG]
    assert sent["2"]["class_type"] == "ImageScaleBy" and sent["2"]["inputs"]["scale_by"] == 2.0
    j.upscale["denoise"] = 0.3
    try:
        c.generate(j, {}); assert False
    except imagegen.BackendError as e:
        assert "Pure upscale" in str(e)


def test_live_preview_recorded(monkeypatch):
    def fake(url, data=None, timeout=30, **k):
        if "progress" in url:
            assert "skip_current_image=false" in url
            return {"progress": 0.4, "current_image": base64.b64encode(test_v4.PNG).decode()}
        time.sleep(0.3)
        return {"images": [base64.b64encode(test_v4.PNG).decode()]}
    monkeypatch.setattr(imagegen, "_http", fake); monkeypatch.setattr(imagegen, "BEFORE_GENERATE", [])
    imagegen.LAST_PREVIEW.clear()
    j = Job("p", tag="autorefine")
    A1111().generate(j, progress=lambda *a: None, poll=0.05)
    assert j.preview == test_v4.PNG and imagegen.LAST_PREVIEW["tag"] == "autorefine"


def test_genqueue_reorder_and_cancel():
    q = GenQueue()
    jobs = [Job(f"p{i}") for i in range(3)]
    q.jobs = [(j, None, None) for j in jobs]
    assert q.move(jobs[2].id, -1) == 1 and [j.prompt for j in q.pending()] == ["p0", "p2", "p1"]
    assert q.move("nope", 1) == -1
    assert q.remove(jobs[0].id) and [j.prompt for j in q.pending()] == ["p2", "p1"]
    q.current = jobs[1]; q.remove(jobs[1].id); assert q._cancel_current
    q.cancel_all(); assert q.pending() == []


def test_accent_colours():
    for name in ("dark", "light"):
        css = theme.stylesheet(name, "teal")
        assert theme.ACCENTS["teal"][0 if name == "dark" else 2] in css
    assert theme.colors("dark")["accent"] == theme.ACCENT  # purple default


# ---------------------------------------------------------------- UI
def _gallery_img(win, prompt="a red fox", w=64, h=48):
    return win.gallery.save(_png(w, h), {"prompt": prompt, "seed": 42, "steps": 20, "cfg": 5.0, "width": w, "height": h})


def test_home_is_first_and_quick_start(win):
    from promptmaker.app import NAV
    assert NAV[0][1] == "Home" and win.stack.currentIndex() == 0
    _gallery_img(win); win.home_refresh()
    assert win.home_recent.count() == 1 and win.profile["name"] in win.home_target.text()
    assert win.home_generate_last() is None or True  # no backend: notifies, must not crash


def test_status_poll_never_stacks(win, srv, monkeypatch):
    _, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    monkeypatch.setattr(imagegen.A1111, "status", lambda self: (time.sleep(0.2), ("online", "nova.safetensors"))[1])
    wk = win.poll_status()
    assert wk is not None and win.poll_status() is None  # second call skipped while one is in flight
    _pump(lambda: not win._status_busy)
    assert "nova.safetensors" in win.be_status.text()
    monkeypatch.setattr(imagegen.A1111, "status", lambda self: (_ for _ in ()).throw(imagegen.BackendError("down")))
    win.poll_status(); _pump(lambda: not win._status_busy)
    assert "Offline" in win.be_status.text()
    win.be_status.click(); assert win.stack.currentIndex() == [n for _, n in __import__("promptmaker.app", fromlist=["NAV"]).NAV].index("Settings")


def test_gallery_layout_actions_and_viewer(win):
    a = _gallery_img(win, "wide", 128, 48); _gallery_img(win, "tall", 48, 128)
    win.load_gallery(); win.go("Gallery")
    sizes = sorted(win.gal_list.item(i).sizeHint().width() for i in range(win.gal_list.count()))
    assert sizes[0] < sizes[1]  # aspect ratios kept
    md = win.gal_list.mimeData([win.gal_list.item(0)])
    assert md.urls() and md.urls()[0].toLocalFile()
    v = win.gal_view(a)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    start = v.i
    v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)); assert v.i == (start + 1) % 2
    v.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier)); assert v.i == start
    win.gal_inpaint(a)
    assert win.ip_canvas.image is not None and win.ip_prompt.toPlainText() == "wide"
    win.ip_canvas.image = None; win._ip_dropped(a)  # drag a thumbnail onto the canvas
    assert win.ip_canvas.image is not None
    win.gal_reference(a); assert win.i2p_b64


def test_hires_and_upscale_from_gallery(win, srv):
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    a = _gallery_img(win)
    job = win.gal_hires(a); test_v4._wait(win)
    assert job.hires and s.last_payload["enable_hr"] and s.last_payload["seed"] == 42 and s.last_payload["steps"] == 20
    job = win.gal_upscale(a, 1.5, "4x-UltraSharp", 0.3); test_v4._wait(win)
    assert s.last_endpoint == "/sdapi/v1/img2img" and (s.last_payload["width"], s.last_payload["height"]) == (96, 72)
    assert s.last_payload["denoising_strength"] == 0.3
    metas = [m for _p, m in win.gallery.items() if m.get("source_image")]
    assert metas and os.path.samefile(metas[0]["source_image"], a)


def test_queue_dialog(win, srv):
    _, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.genq.jobs = [(Job(f"job {i}", tag="batch"), None, None) for i in range(3)]
    d = win.open_queue()
    assert d.list.count() == 3 and "batch" in d.list.item(0).text()
    d.list.setCurrentRow(2); d._move(-1)
    assert [j.prompt for j in win.genq.pending()] == ["job 0", "job 2", "job 1"]
    d.list.setCurrentRow(0); d._cancel_one(); assert len(win.genq.pending()) == 2
    d._cancel_all(); assert win.genq.pending() == [] and "empty" in d.list.item(0).text()


def test_per_profile_image_settings(win, srv):
    _, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    ids = list(win.profiles); a, b = ids[0], ids[1]
    sel = lambda pid: win.profile_combo.setCurrentIndex(win.profile_combo.findData(pid))  # noqa: E731
    sel(a)
    win.img_steps.setValue(33); win.img_cfg.setValue(4.5); win.img_sampler.setCurrentText("DPM++ 2M"); win._img_save()
    win.aspect.setCurrentText("16:9")
    assert win.store.get("profile_image_settings")[a] == {"steps": 33, "cfg": 4.5, "sampler": "DPM++ 2M", "aspect": "16:9"}
    assert "33" in win.ckpt_link_lbl.text() and "Linked to" in win.ckpt_link_lbl.text()
    sel(b); win.aspect.setCurrentText("1:1"); win.img_steps.setValue(12); win._img_save()
    sel(a)
    assert win.aspect.currentText() == "16:9" and win.img_steps.value() == 33
    win.store.set("img_backend", "a1111")  # _img_save stored the Settings form's backend (off)
    job = win.make_job("x")[0]
    assert (job.steps, job.cfg, job.sampler) == (33, 4.5, "DPM++ 2M")
    sel(b); assert win.make_job("x")[0].steps == 12
    from promptmaker import sync, wildcards
    bundle = json.loads(json.dumps(sync.build(win.store, wildcards.WildcardLib(win.data_dir + "/wc"))))
    assert bundle["settings"]["profile_image_settings"][a]["steps"] == 33


def test_sidebar_collapse_accent_and_fade(win):
    win.set_sidebar_collapsed(True)
    assert win.sidebar_w.width() == 64 and win.nav.item(1).toolTip() == "Create" and not win.profile_combo.isVisible()
    assert win.store.get("sidebar_collapsed") is True
    win.set_sidebar_collapsed(False); assert win.sidebar_w.width() == 240
    win.apply_accent("pink")
    from PySide6.QtWidgets import QApplication
    assert theme.ACCENTS["pink"][0] in QApplication.instance().styleSheet()
    assert win.fade_in(win.stack.currentWidget()) is None  # skipped offscreen


def test_live_preview_tick(win):
    imagegen.LAST_PREVIEW.update(job="x", tag="autorefine", png=_png(), pct=40)
    win._preview_tick()
    assert win.gen_preview.pixmap() is not None and not win.gen_preview.pixmap().isNull()
    assert not win.ar_img.pixmap().isNull()
    imagegen.LAST_PREVIEW.clear()


def test_viewer_no_zoom_and_wheel(win):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    a = _gallery_img(win, "big", 1600, 1200); _gallery_img(win, "small", 64, 48); _gallery_img(win, "tall", 300, 900)
    v = win.gal_view(a); v.show(); v.resize(800, 600)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    sizes = []
    for _ in range(6):
        ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                         Qt.NoScrollPhase, False)
        v.wheelEvent(ev); QApplication.processEvents()
        pm = v.img.pixmap()
        assert pm.width() <= v.img.width() and pm.height() <= v.img.height()  # always fits
        sizes.append((v.size().width(), v.size().height()))
    assert len(set(sizes)) == 1 and sizes[0] == (800, 600)  # window never grows (old zoom bug)
    assert v.i == (v.paths.index(a) + 6) % 3
    v.close()
