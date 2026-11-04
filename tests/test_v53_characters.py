"""5.3 Video maker character consistency: sheet, migration, plan refs, verbatim prompt assembly, seeds, face lock
rules and the face-lock job (IP-Adapter Plus Face via Face Swap's code). SFW, adult characters only."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import faceswap as fs, imagegen  # noqa: E402
from promptmaker import videoproject as vp  # noqa: E402
import test_v5  # noqa: E402
from test_v53_video import _png  # noqa: E402

_wait = test_v5._wait
win = test_v5.win
MIRA = "adult woman, 25 years old, long silver hair, green eyes, red bomber jacket, black jeans"
JO = "adult man, 30 years old, short black hair, brown eyes, blue denim shirt"


def _proj():
    p = vp.new_project("Cast test")
    p["characters"] = [vp.new_character([], "Mira", MIRA, seed=1234, main=True)]
    p["characters"].append(vp.new_character(p["characters"], "Jo", JO, seed=99))
    return p


def test_character_ids_and_scene_order():
    p = _proj()
    assert [c["id"] for c in p["characters"]] == ["c1", "c2"]
    s = vp.new_scene(0, "they share an umbrella in the rain", characters=["c2", "c1"])
    assert [c["name"] for c in vp.scene_characters(p, s)] == ["Mira", "Jo"]  # main first


def test_prompt_injects_descriptions_verbatim():
    p = _proj(); p["style"] = "anime style, soft colours"
    s = vp.new_scene(0, "Mira waves at Jo across a sunny park", characters=["c1", "c2"])
    out = vp.scene_prompt(p, s)
    assert out == f"anime style, soft colours, {MIRA}, {JO}, Mira waves at Jo across a sunny park"
    assert vp.scene_prompt(p, vp.new_scene(0, "an empty beach at dawn")) == "anime style, soft colours, an empty beach at dawn"


def test_seeds_character_then_override():
    p = _proj()
    s = vp.new_scene(0, "x", characters=["c2", "c1"])
    assert vp.scene_seed(p, s) == 1234
    s["seed"] = 5; assert vp.scene_seed(p, s) == 5
    assert vp.scene_seed(p, vp.new_scene(0, "x")) == -1
    p["characters"][0]["seed"] = -1; assert vp.scene_seed(p, vp.new_scene(0, "x", characters=["c1"])) == -1


def test_plan_uses_cast_ids_and_names():
    p = _proj()
    msgs = vp.plan_messages(p, 2)
    assert "c1: Mira" in msgs[1]["content"] and "do NOT describe their looks" in msgs[0]["content"]
    plan = json.dumps({"scenes": [{"prompt": "Mira reads a book", "characters": ["c1"]},
                                  {"prompt": "Jo and Mira cook", "characters": ["jo", "MIRA", "c1", "nobody"]},
                                  {"prompt": "city at night", "characters": "Jo"}]})
    _t, sc = vp.parse_plan(plan, p)
    assert [s["characters"] for s in sc] == [["c1"], ["c2", "c1"], ["c2"]]


def test_migrate_v1_project(tmp_path):
    old = {"version": 1, "name": "Old", "scenes": [{"id": "s01", "prompt": "a lighthouse", "seed": 777, "still": ""}]}
    (tmp_path / "project.json").write_text(json.dumps(old))
    p = vp.load_project(str(tmp_path))
    assert p["version"] == 2 and p["characters"] == []
    s = p["scenes"][0]
    assert s["seed"] == -1 and s["used_seed"] == 777 and s["characters"] == []
    vp.save_project(p, str(tmp_path))
    assert json.load(open(tmp_path / "project.json"))["version"] == 2


def test_reference_copied_into_project(tmp_path):
    src = tmp_path / "face.png"; _png(src, "pink", 256, 256)
    c = vp.new_character()
    pdir = str(tmp_path / "proj")
    assert vp.set_reference(c, pdir, str(src)) == "chars/c1.png"
    assert vp.ref_path({}, pdir, c) == os.path.normpath(os.path.join(pdir, "chars", "c1.png"))


@pytest.mark.parametrize("info,warn,want_ref,note", [
    ({"kind": "comfy", "type": "plus_face", "model": "ip-adapter-plus-face_sdxl_vit-h.safetensors"}, "", True, "ComfyUI IP-Adapter Plus Face"),
    ({"kind": "comfy", "type": "plus_face", "model": "x"}, "Face Swap needs an SDXL", False, "needs an SDXL"),
    ({"kind": "comfy", "type": "", "problem": "ComfyUI_IPAdapter_plus is not installed."}, "", False, "not installed"),
    ({"kind": "forge", "model": "ip-adapter-plus-face_sdxl [abc]", "type": "plus_face"}, "", True, "Forge ControlNet"),
    ({"kind": "forge", "model": "", "type": ""}, "", False, "no face IP-Adapter in Forge"),
    ({"kind": None}, "", False, "no image backend"),
])
def test_facelock_rules(tmp_path, info, warn, want_ref, note):
    p = _proj(); pdir = str(tmp_path)
    src = tmp_path / "f.png"; _png(src, "pink", 256, 256); vp.set_reference(p["characters"][0], pdir, str(src))
    s = vp.new_scene(0, "x", characters=["c1", "c2"])
    ref, msg = vp.facelock_plan(p, s, pdir, info, warn)
    assert bool(ref) == want_ref and note in msg
    if want_ref:
        assert "only Mira is face-locked (1 other character use text only)" in msg
    assert vp.facelock_plan(p, vp.new_scene(0, "x", characters=["c2"]), pdir, info, warn) == ("", "")  # Jo has no ref


def test_comfy_facelock_workflow_from_job():
    """The job the Video maker builds goes through the same ComfyUI path as Face Swap's generate mode."""
    j = imagegen.Job("adult woman portrait")
    fs.apply_to_job(j, b"PNG", "ip-adapter-plus-face_sdxl_vit-h.safetensors", "plus_face")
    wf = {"3": {"class_type": "KSampler", "inputs": {"model": ["4", 0]}}, "4": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    out = fs.add_comfy_face(wf, "pm_face.png", j.faceswap["weight"], j.faceswap["stop_at"], j.faceswap["kind"])
    loaders = [n for n in out.values() if n["class_type"] == "IPAdapterUnifiedLoader"]
    assert loaders and loaders[0]["inputs"]["preset"] == "PLUS FACE (portraits)" and j.inpaint is None


# ------------------------------------------------------------------ page
def test_page_characters_and_facelocked_stills(win, tmp_path, monkeypatch):
    win.go("Video maker"); win.vm_name.setText("Cast page")
    win.vm_char_add()
    win.vm_ch_name.setText("Mira"); win.vm_ch_desc.setPlainText(MIRA); win.vm_ch_seed.setValue(4321)
    face = tmp_path / "face.png"; _png(face, "pink", 256, 256); win.vm_ch_ref.setText(str(face))
    assert win.vm_char_apply()
    c = win.vm_proj["characters"][0]
    assert c["main"] and c["ref"] == "chars/c1.png" and os.path.exists(os.path.join(win.vm_dir(), "chars", "c1.png"))
    plan = json.dumps({"scenes": [{"prompt": "Mira waves from a balcony", "characters": ["c1"]},
                                  {"prompt": "a quiet street at dawn", "characters": []}]})
    assert win.vm_apply_plan(plan) == 2
    win.vm_cur = 1; win.vm_select(1)
    from PySide6.QtCore import Qt
    assert win.vm_scene_chars.count() == 1 and win.vm_scene_chars.item(0).checkState() == Qt.Unchecked
    win.vm_scene_chars.item(0).setCheckState(Qt.Checked); win.vm_scene_seed.setValue(55); win.vm_apply_scene()
    assert win.vm_proj["scenes"][1]["characters"] == ["c1"] and win.vm_proj["scenes"][1]["seed"] == 55
    seen = []

    class B(imagegen.ComfyUI):
        def generate(self, job, workflow=None, progress=None, cancelled=None):
            seen.append(job); return [_png(tmp_path / "o.png", "teal")]
    b = B("http://127.0.0.1:9")
    monkeypatch.setattr(win, "make_job", lambda prompt, neg="", seed=None, tag="": (imagegen.Job(prompt, neg, 1024, 1024, seed), b, {}))
    monkeypatch.setattr(fs, "detect", lambda backend: {"kind": "comfy", "type": "plus_face", "problem": "",
                                                       "model": "ip-adapter-plus-face_sdxl_vit-h.safetensors"})
    monkeypatch.setattr(vp, "facelock_model_warning", lambda profile, wf="": "")
    assert win.vm_stills()
    assert _wait(lambda: "✓ 2" in win.vm_status.text(), 20), win.vm_status.text()
    assert all(j.prompt.startswith(MIRA) for j in seen)
    assert seen[0].seed == 4321 and seen[1].seed == 55
    assert all(j.faceswap and j.faceswap["kind"] == "plus_face" for j in seen)
    assert "face lock: Mira" in win.vm_proj["scenes"][0]["facelock"]
    # Anima / non-SDXL target: stills still made, face lock skipped with a note
    for s in win.vm_proj["scenes"]:
        s["still"] = ""
    seen.clear(); monkeypatch.setattr(vp, "facelock_model_warning", lambda profile, wf="": "Face Swap needs an SDXL checkpoint")
    assert win.vm_stills()
    assert _wait(lambda: len(seen) == 2 and not win._vm_busy(), 20)
    assert all(j.faceswap is None for j in seen) and "needs an SDXL" in win.vm_facelock.text()


def test_import_from_characters_library(win, tmp_path):
    face = tmp_path / "lib.png"; _png(face, "orange", 256, 256)
    win.store.save_character({"name": "Ava", "appearance": "adult woman, short pink hair, grey eyes", "outfit": "yellow raincoat",
                              "ref_image": str(face)})
    win.go("Video maker"); win.vm_name.setText("Import test"); win.vm_char_refresh()
    win.vm_ch_import.setCurrentIndex(win.vm_ch_import.findText("Ava"))
    c = win.vm_char_import()
    assert c and c["name"] == "Ava" and "short pink hair" in c["description"] and "yellow raincoat" in c["description"]
    assert c["ref"] == "chars/c1.png" and c["main"]


@pytest.mark.parametrize("profile,wf,ok", [
    ({"family": "Stable Diffusion"}, "sdxl_txt2img", True), ({"family": "Illustrious"}, "a1111", True),
    ({"family": "MOSS"}, "moss_txt2img", False), ({"family": "Anima"}, "a1111", False),
    ({"family": "Stable Diffusion"}, "flux_txt2img", False), ({"family": "Qwen"}, "", False)])
def test_facelock_model_warning(profile, wf, ok):
    assert (vp.facelock_model_warning(profile, wf) == "") == ok
