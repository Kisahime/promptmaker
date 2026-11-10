"""6.1 quality of life: Start Forge / ComfyUI, ADetailer presets + top-bar toggle, ADetailer on ComfyUI (Impact Pack
FaceDetailer), and 127.0.0.1 instead of localhost. Everything is mocked: no backend is started or contacted."""
import copy
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import backenddetect as bd  # noqa: E402
from promptmaker import firstrun, imagegen, launchers, ollama, providers  # noqa: E402
from promptmaker.imagegen import BackendError  # noqa: E402
import test_v5  # noqa: E402

win, _wait = test_v5.win, test_v5._wait
FACE, HAND, PERSON = imagegen.AD_FACE, imagegen.AD_HAND, "person_yolov8n-seg.pt"
COMFY_DETECTORS = ["bbox/face_yolov8m.pt", "bbox/hand_yolov8s.pt", "segm/person_yolov8m-seg.pt"]


class _Store(dict):
    def get(self, k, d=None):
        return super().get(k, d)

    def set(self, k, v):
        self[k] = v


# ------------------------------------------------------------------ item 4: 127.0.0.1, not localhost
def test_defaults_use_127():
    assert ollama.BASE == "http://127.0.0.1:11434" and firstrun.OLLAMA_URL == "http://127.0.0.1:11434"
    assert not [p for p in providers.PRESETS.values() if "localhost" in p.get("base_url", "")]
    assert "localhost" not in "".join(u for _k, u in bd.candidates({}.get))


def test_migrate_localhost_only_old_defaults():
    st = _Store({"provider_url:ollama": "http://localhost:11434/", "provider_url:lmstudio": "http://localhost:1234/v1",
                 "provider_url:vllm": "http://localhost:9999/v1", "provider_url:openai": "https://api.openai.com/v1",
                 "img_url:a1111": "http://localhost:7860", "img_url:comfyui": "http://192.168.1.5:8188"})
    changed = providers.migrate_localhost(st)
    assert st["provider_url:ollama"] == "http://127.0.0.1:11434" and st["provider_url:lmstudio"] == "http://127.0.0.1:1234/v1"
    assert st["img_url:a1111"] == "http://127.0.0.1:7860"
    assert st["provider_url:vllm"] == "http://localhost:9999/v1"  # custom port: untouched
    assert st["img_url:comfyui"] == "http://192.168.1.5:8188" and st["provider_url:openai"] == "https://api.openai.com/v1"
    assert set(changed) == {"provider_url:ollama", "provider_url:lmstudio", "img_url:a1111"}
    assert providers.migrate_localhost(st) == []


def test_window_migrates_on_start(tmp_path, monkeypatch):
    from promptmaker.storage import Store
    st = Store(str(tmp_path / "m.db")); st.set("provider_url:ollama", "http://localhost:11434")
    providers.migrate_localhost(st)
    assert st.get("provider_url:ollama") == "http://127.0.0.1:11434"


# ------------------------------------------------------------------ item 2: launchers
def _bat(path, text="@echo off\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return str(path)


def test_find_saved_known_and_search(tmp_path):
    forge = tmp_path / "AI" / "my-forge"
    _bat(str(forge / "webui.py")); w = _bat(str(forge / "webui-user.bat"), "set COMMANDLINE_ARGS=--api --xformers\ncall webui.bat\n")
    _bat(str(forge / "run.bat"))
    comfy = tmp_path / "AI" / "ComfyUI_windows_portable"
    os.makedirs(comfy / "ComfyUI", exist_ok=True); c = _bat(str(comfy / "run_nvidia_gpu.bat")); _bat(str(comfy / "run_cpu.bat"))
    if launchers.WINDOWS:
        assert launchers.find("a1111", known=[], where=[str(tmp_path)]) == w  # webui-user.bat beats run.bat
        assert launchers.find("comfyui", known=[], where=[str(tmp_path)]) == c
        assert launchers.find("comfyui", known=[c], where=[]) == c
    saved = _bat(str(tmp_path / "elsewhere" / "start.bat"))
    assert launchers.find("a1111", saved=saved, known=[], where=[]) == saved
    assert launchers.find("a1111", saved=str(tmp_path / "gone.bat"), known=[], where=[str(tmp_path / "nothing")]) == ""
    assert launchers.forge_has_api(w) is True


def test_forge_api_flag(tmp_path):
    w = _bat(str(tmp_path / "f" / "webui-user.bat"), ":: set COMMANDLINE_ARGS=--api\nset COMMANDLINE_ARGS=--xformers\n")
    assert launchers.forge_has_api(w) is False
    assert launchers.forge_has_api(_bat(str(tmp_path / "g" / "run.bat"))) is None


def test_launch_uses_own_console_and_folder(tmp_path):
    p = _bat(str(tmp_path / "forge" / "webui-user.bat"))
    calls = []
    launchers.launch(p, popen=lambda *a, **k: calls.append((a, k)) or "proc")
    (args,), kw = calls[0]
    assert kw["cwd"] == os.path.dirname(p)
    if launchers.WINDOWS:
        assert args[:2] == ["cmd.exe", "/c"] and args[2] == p
        assert kw["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    with pytest.raises(OSError):
        launchers.launch(str(tmp_path / "missing.bat"), popen=lambda *a, **k: None)


@pytest.fixture
def lwin(win, tmp_path, monkeypatch):
    forge = _bat(str(tmp_path / "forge" / "webui-user.bat"), "set COMMANDLINE_ARGS=--api\n")
    comfy = _bat(str(tmp_path / "comfy" / "run_nvidia_gpu.bat"))
    launched = []

    class Proc:
        code = None

        def poll(self):
            return self.code
    monkeypatch.setattr(launchers, "launch", lambda path, popen=None: launched.append(path) or Proc())
    win._launch_found({"a1111": forge, "comfyui": comfy})
    win.launched, win.paths = launched, {"a1111": forge, "comfyui": comfy}
    return win


def test_start_buttons_follow_launchers(lwin):
    assert not lwin.launch_btns["a1111"].isHidden() and not lwin.launch_btns["comfyui"].isHidden()
    assert lwin.store.get("launcher:a1111") == lwin.paths["a1111"]
    lwin._launch_path_set("comfyui", "")
    assert lwin.launch_btns["comfyui"].isHidden() and not lwin.launch_btns["a1111"].isHidden()
    assert not lwin._launch_path_set("comfyui", lwin.paths["comfyui"] + ".nope")
    lwin._launch_path_set("a1111", "")
    assert lwin.launch_btns["a1111"].isHidden() and "weren't found" in lwin.launch_lbl.text()


def test_already_running_connects_instead(lwin):
    r = lwin._launch_checked("a1111", lwin.paths["a1111"], {"http://127.0.0.1:7861": "a1111"})
    assert r == "running" and not lwin.launched
    assert lwin.store.get("img_backend") == "a1111" and lwin.store.get("img_url:a1111") == "http://127.0.0.1:7861"
    assert "already running" in lwin.launch_lbl.text()


def test_other_running_asks_first(lwin, monkeypatch):
    asked = []
    monkeypatch.setattr(lwin, "_confirm_launch", lambda text: asked.append(text) or False)
    assert lwin._launch_checked("a1111", lwin.paths["a1111"], {"http://127.0.0.1:8188": "comfyui"}) == "cancelled"
    assert not lwin.launched and "ComfyUI" in asked[0] and "VRAM" in asked[0]
    monkeypatch.setattr(lwin, "_confirm_launch", lambda text: True)
    assert lwin._launch_checked("a1111", lwin.paths["a1111"], {"http://127.0.0.1:8188": "comfyui"}) == "started"
    assert lwin.launched == [lwin.paths["a1111"]] and lwin._launch_state["kind"] == "a1111"
    assert lwin._launch_timer.isActive()
    assert lwin.start_backend("comfyui") is None and "still starting" in lwin.launch_lbl.text()
    lwin._launch_stop()


def test_started_then_ready(lwin):
    assert lwin._launch_checked("comfyui", lwin.paths["comfyui"], {}) == "started"
    st = lwin._launch_state
    assert lwin._launch_polled(st, {}) is None and lwin._launch_state is st  # not up yet
    assert lwin._launch_polled(st, {"http://127.0.0.1:8188": "comfyui"}) == "http://127.0.0.1:8188"
    assert lwin._launch_state is None and not lwin._launch_timer.isActive()
    assert lwin.store.get("img_backend") == "comfyui" and "ready" in lwin.launch_lbl.text()


def test_start_timeout_and_crash(lwin):
    lwin._launch_checked("a1111", lwin.paths["a1111"], {})
    lwin._launch_state["start"] = time.time() - launchers.TIMEOUT_S - 1
    lwin._launch_poll()
    assert lwin._launch_state is None and "5 minutes" in lwin.launch_lbl.text()
    lwin._launch_checked("a1111", lwin.paths["a1111"], {})
    lwin._launch_state["proc"].code = 1
    lwin._launch_poll()
    assert lwin._launch_state is None and "stopped" in lwin.launch_lbl.text()


def test_start_backend_async_probe(lwin, monkeypatch):
    monkeypatch.setattr(bd, "probe", lambda cands, timeout=0.8, ident=None: {"http://127.0.0.1:7860": "a1111"})
    assert lwin.start_backend("a1111") is not None
    assert _wait(lambda: "already running" in lwin.launch_lbl.text(), 10)
    assert not lwin.launched


def test_top_bar_start_button(lwin):
    lwin.store.set("img_backend", "a1111")
    lwin._set_status("offline")
    assert not lwin.be_start.isHidden()
    lwin._set_status("online", "x")
    assert lwin.be_start.isHidden()
    lwin._launch_path_set("a1111", ""); lwin._set_status("offline")
    assert lwin.be_start.isHidden()  # nothing to start


# ------------------------------------------------------------------ item 3: presets + quick toggle
def test_presets_use_available_models():
    assert [p["ad_model"] for p in imagegen.adetailer_preset("face")] == [FACE]
    fb = imagegen.adetailer_preset("full_body", [FACE, HAND, PERSON])
    assert [p["ad_model"] for p in fb] == [PERSON, FACE] and fb[0]["ad_denoising_strength"] == 0.3
    assert [p["ad_model"] for p in imagegen.adetailer_preset("full_body", [FACE, HAND])] == [FACE]  # no person model
    assert [p["ad_model"] for p in imagegen.adetailer_preset("face_hands", COMFY_DETECTORS)] == COMFY_DETECTORS[:2]
    assert imagegen.adetailer_preset("face_hands", ["mediapipe_face_full.tflite"]) == [
        {"ad_model": "mediapipe_face_full.tflite", "ad_denoising_strength": 0.4, "ad_confidence": 0.3}]


def test_match_detector_across_backends():
    m = imagegen.match_detector
    assert m("face_yolov8s.pt", COMFY_DETECTORS) == "bbox/face_yolov8m.pt"
    assert m("bbox/hand_yolov8s.pt", ["face_yolov8n.pt", "hand_yolov8s.pt"]) == "hand_yolov8s.pt"
    assert m("person_yolov8n-seg.pt", COMFY_DETECTORS) == "segm/person_yolov8m-seg.pt"
    assert m("face_yolov8s.pt", ["hand_yolov8n.pt"]) == "" and m("", COMFY_DETECTORS) == ""
    assert imagegen.forge_detector("bbox/face_yolov8m.pt") == "face_yolov8m.pt"
    assert imagegen.forge_detector("bbox/face_yolov8m.pt", [FACE, HAND]) == FACE


def test_forge_payload_translates_comfy_names(monkeypatch):
    monkeypatch.setattr(imagegen, "_AD_CACHE", {"http://127.0.0.1:9": [FACE, HAND]})
    j = imagegen.Job("a cat", "", 512, 512, 1, 20, 6.0, "x", "")
    j.adetailer = [{"ad_model": "bbox/face_yolov8m.pt"}, {"ad_model": "bbox/hand_yolov8s.pt"}]
    args = imagegen.A1111("http://127.0.0.1:9").payload(j)["alwayson_scripts"]["ADetailer"]["args"]
    assert [a["ad_model"] for a in args[2:]] == [FACE, HAND]


def test_preset_ui(win):
    win.img_kind.setCurrentIndex(win.img_kind.findData("a1111"))
    win._ad_models_loaded([FACE, HAND, PERSON]); win.ad_on.setChecked(True)
    win.ad_preset.setCurrentIndex(win.ad_preset.findData("face_hands"))
    assert win.ad_model.currentText() == FACE and win.ad2_on.isChecked() and win.ad2_model.currentText() == HAND
    win.ad_preset.setCurrentIndex(win.ad_preset.findData("full_body"))
    assert win.ad_model.currentText() == PERSON and abs(win.ad_denoise.value() - 0.3) < 1e-6 and win.ad2_model.currentText() == FACE
    assert win.ad_preset.currentData() == "full_body"
    win.ad_denoise.setValue(0.45)
    assert win.ad_preset.currentData() == ""  # edited by hand -> Custom
    win._ad_models_loaded([FACE])
    win.ad_preset.setCurrentIndex(win.ad_preset.findData("face_hands"))
    assert not win.ad2_on.isChecked() and "left out" in win.ad_note.text()
    win._img_save()
    assert win.store.get("ad_preset") == "face_hands"


def test_quick_toggle_syncs_and_greys(win):
    win.store.set("img_backend", "a1111"); win._ad_quick_sync()
    assert win.ad_quick.isEnabled()
    win.ad_quick.setChecked(True)
    assert win.ad_on.isChecked() and win.store.get("ad_on") is True
    win.ad_on.setChecked(False)
    assert not win.ad_quick.isChecked() and win.store.get("ad_on") is False
    win._ad_states()["a1111"] = False; win._ad_quick_sync()
    assert not win.ad_quick.isEnabled() and "ADetailer" in win.ad_quick.toolTip()
    win.store.set("img_backend", "comfyui"); win._ad_quick_sync()
    assert not win.ad_quick.isEnabled()
    win._ad_states()["comfyui"] = False; win._ad_quick_sync()
    assert not win.ad_quick.isEnabled() and "Impact" in win.ad_quick.toolTip()
    win._ad_states()["comfyui"] = True; win._ad_quick_sync()
    assert win.ad_quick.isEnabled()
    win.store.set("img_backend", "none"); win._ad_quick_sync()
    assert not win.ad_quick.isEnabled()


def test_status_online_checks_adetailer_once(win, monkeypatch):
    calls = []
    monkeypatch.setattr(imagegen.A1111, "adetailer_models", lambda self, refresh=False: calls.append(1) or [FACE, HAND])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", "http://127.0.0.1:9")
    win.img_kind.setCurrentIndex(win.img_kind.findData("a1111"))
    win._set_status("online", "x")
    assert _wait(lambda: win._ad_states().get("a1111") is True, 10)
    win._set_status("online", "x")
    assert len(calls) == 1 and win.ad_model.count() == 2


# ------------------------------------------------------------------ item 7: ComfyUI FaceDetailer
def _req(**extra):
    r = {"image": ["IMAGE"], "model": ["MODEL"], "clip": ["CLIP"], "vae": ["VAE"],
         "guide_size": ["FLOAT", {"default": 512}], "guide_size_for": ["BOOLEAN", {"default": True}],
         "max_size": ["FLOAT", {"default": 1024}], "seed": ["INT", {"default": 0}], "steps": ["INT", {"default": 20}],
         "cfg": ["FLOAT", {"default": 8.0}], "sampler_name": [["euler", "dpmpp_2m"]],
         "scheduler": [["normal", "karras", "AYS SDXL"]], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
         "denoise": ["FLOAT", {"default": 0.5}], "feather": ["INT", {"default": 5}], "noise_mask": ["BOOLEAN", {"default": True}],
         "force_inpaint": ["BOOLEAN", {"default": True}], "bbox_threshold": ["FLOAT", {"default": 0.5}],
         "bbox_dilation": ["INT", {"default": 10}], "bbox_crop_factor": ["FLOAT", {"default": 3.0}],
         "sam_detection_hint": [["center-1", "horizontal-2", "none"]], "sam_dilation": ["INT", {"default": 0}],
         "sam_threshold": ["FLOAT", {"default": 0.93}], "sam_bbox_expansion": ["INT", {"default": 0}],
         "sam_mask_hint_threshold": ["FLOAT", {"default": 0.7}], "sam_mask_hint_use_negative": [["False", "Small", "Outter"]],
         "drop_size": ["INT", {"default": 10}], "bbox_detector": ["BBOX_DETECTOR"],
         "wildcard": ["STRING", {"multiline": True}], "cycle": ["INT", {"default": 1}]}
    r.update(extra)
    return r


INFO = {"FaceDetailer": {"input": {"required": _req(future_option=["INT", {"default": 7}]),
                                   "optional": {"sam_model_opt": ["SAM_MODEL"]}}},
        "UltralyticsDetectorProvider": {"input": {"required": {"model_name": [COMFY_DETECTORS]}}}}


def _wf():
    return {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                                                       "latent_image": ["5", 0], "seed": 42, "steps": 25, "cfg": 5.5,
                                                       "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "pm"}}}


def test_facedetailer_one_pass():
    wf = _wf(); before = copy.deepcopy(wf)
    out = imagegen.add_comfy_facedetailer(wf, [{"ad_model": FACE, "ad_denoising_strength": 0.35, "ad_confidence": 0.4}], INFO)
    assert wf == before  # input not modified
    assert out["9"]["inputs"]["images"] == ["pm_ad1_fd", 0]
    assert out["pm_ad1_det"] == {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}}
    fd = out["pm_ad1_fd"]["inputs"]
    assert out["pm_ad1_fd"]["class_type"] == "FaceDetailer"
    assert fd["image"] == ["8", 0] and fd["model"] == ["4", 0] and fd["clip"] == ["4", 1] and fd["vae"] == ["4", 2]
    assert fd["positive"] == ["6", 0] and fd["negative"] == ["7", 0] and fd["bbox_detector"] == ["pm_ad1_det", 0]
    assert fd["denoise"] == 0.35 and fd["bbox_threshold"] == 0.4
    assert (fd["seed"], fd["steps"], fd["cfg"], fd["sampler_name"], fd["scheduler"]) == (42, 25, 5.5, "dpmpp_2m", "karras")
    assert fd["guide_size"] == 512 and fd["max_size"] == 1024 and fd["guide_size_for"] is True and fd["feather"] == 5
    assert fd["noise_mask"] is True and fd["force_inpaint"] is True and fd["bbox_crop_factor"] == 3.0
    assert fd["sam_detection_hint"] == "center-1" and fd["sam_mask_hint_use_negative"] == "False" and fd["wildcard"] == ""
    assert fd["future_option"] == 7  # unknown required input: object_info default
    assert "sam_model_opt" not in fd  # optional inputs are left to the node
    assert set(fd) == set(INFO["FaceDetailer"]["input"]["required"])


def test_facedetailer_two_passes_with_prompt():
    out = imagegen.add_comfy_facedetailer(_wf(), [{"ad_model": FACE, "ad_prompt": "detailed eyes", "ad_negative_prompt": "ugly"},
                                                  {"ad_model": HAND, "ad_denoising_strength": 0.5}], INFO)
    assert out["pm_ad1_pos"] == {"class_type": "CLIPTextEncode", "inputs": {"text": "detailed eyes", "clip": ["4", 1]}}
    assert out["pm_ad1_fd"]["inputs"]["positive"] == ["pm_ad1_pos", 0] and out["pm_ad1_fd"]["inputs"]["negative"] == ["pm_ad1_neg", 0]
    f2 = out["pm_ad2_fd"]["inputs"]
    assert f2["image"] == ["pm_ad1_fd", 0] and f2["positive"] == ["6", 0] and f2["denoise"] == 0.5
    assert out["pm_ad2_det"]["inputs"]["model_name"] == "bbox/hand_yolov8s.pt"
    assert out["9"]["inputs"]["images"] == ["pm_ad2_fd", 0]


def test_facedetailer_after_hires_and_odd_values():
    wf = imagegen.add_comfy_hires(_wf(), 1.5, 0.4)
    wf[wf["8"]["inputs"]["samples"][0]]["inputs"]["scheduler"] = "beta"  # not offered by this FaceDetailer -> its default
    out = imagegen.add_comfy_facedetailer(wf, [{"ad_model": FACE}], INFO)
    fd = out["pm_ad1_fd"]["inputs"]
    assert fd["image"] == ["8", 0] and out["8"]["inputs"]["samples"][0] != "3"  # after the hires decode
    assert fd["scheduler"] == "normal"


def test_facedetailer_new_combo_format_and_errors():
    info = copy.deepcopy(INFO)
    info["UltralyticsDetectorProvider"]["input"]["required"]["model_name"] = ["COMBO", {"options": COMFY_DETECTORS}]
    assert imagegen.facedetailer_models(info) == COMFY_DETECTORS
    wf = _wf(); del wf["9"]
    with pytest.raises(ValueError):
        imagegen.add_comfy_facedetailer(wf, [{"ad_model": FACE}], INFO)
    assert imagegen.add_comfy_facedetailer(_wf(), [], INFO) == _wf()
    assert imagegen.add_comfy_facedetailer(_wf(), [{"ad_model": FACE}], {}) == _wf()


def test_impact_info(monkeypatch):
    monkeypatch.setattr(imagegen, "_IMPACT_CACHE", {})
    calls = []

    def have(url, data=None, timeout=30, **_k):
        calls.append(url)
        node = url.rsplit("/", 1)[1]
        return {node: INFO[node]}
    monkeypatch.setattr(imagegen, "_http", have)
    c = imagegen.ComfyUI("http://c:1")
    assert c.facedetailer_models() == COMFY_DETECTORS and c.adetailer_models() == COMFY_DETECTORS
    assert len(calls) == 2  # cached
    monkeypatch.setattr(imagegen, "_http", lambda url, *a, **k: {} if url.endswith("FaceDetailer") else {"UltralyticsDetectorProvider": {}})
    assert imagegen.ComfyUI("http://c:2").impact_info() == {} and imagegen._IMPACT_CACHE["http://c:2"] == {}

    def off(url, *a, **k):
        raise BackendError("Can't reach it")
    monkeypatch.setattr(imagegen, "_http", off)
    assert imagegen.ComfyUI("http://c:3").impact_info() == {} and "http://c:3" not in imagegen._IMPACT_CACHE


def test_comfy_ui_states(win):
    win.img_kind.setCurrentIndex(win.img_kind.findData("comfyui"))
    win._ad_models_loaded([])
    assert not win.ad_on.isEnabled() and "ComfyUI-Impact-Pack" in win.ad_note.text() and "Subpack" in win.ad_note.text()
    win._ad_models_loaded(COMFY_DETECTORS)
    assert win.ad_on.isEnabled() and win.ad_model.currentText() == "bbox/face_yolov8m.pt"
    assert win.ad2_model.currentText() == "bbox/hand_yolov8s.pt"


def test_translations_cover_new_strings():
    import json
    from promptmaker import i18n
    new = ["ADetailer (fix faces / hands after each image)", "Launcher paths", "Face + hands", "Full body",
           imagegen.IMPACT_HINT, "Second pass", "Detector models loaded"]
    for code in ("de", "es"):
        with open(os.path.join(i18n.DIR, code + ".json"), encoding="utf-8") as f:
            strings = json.load(f)["strings"]
        missing = [s for s in new if not strings.get(s)]
        assert not missing, (code, missing)


def test_inspector_still_fits_with_launch_rows(lwin):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
    lwin.go("Create"); QApplication.processEvents()
    lwin.launch_paths_btn.setChecked(True); lwin.launch_lbl.setText("Starting Forge in its own window... the first start can take a few minutes.")
    sc = lwin.inspector.findChild(QScrollArea); vp = sc.viewport(); card = lwin.settings_img_card
    for kind in ("a1111", "comfyui"):
        lwin.img_kind.setCurrentIndex(lwin.img_kind.findData(kind)); lwin.ad_on.setChecked(True); QApplication.processEvents()
        assert not lwin.launch_btns["a1111"].isHidden()
        assert sc.widget().minimumSizeHint().width() <= vp.width(), kind
        out = [type(c).__name__ for c in card.findChildren(QWidget)
               if c.isVisibleTo(card) and c.mapTo(vp, QPoint(c.width(), 0)).x() > vp.width() + 1]
        assert not out, (kind, out)


def test_top_bar_fits_minimum_window(win):
    from PySide6.QtWidgets import QWidget
    win.be_start.show()
    assert win.findChild(QWidget, "topBar").minimumSizeHint().width() <= win.minimumWidth()
