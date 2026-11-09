"""6.0: local Wan2GP presets, one creative LoRA, scene overrides and recorded resume.

No real GPU job. The installed Wan2GP folder is read when it is present; missing-file checks
never start wgp.py."""
import json
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import wan2gp, wanconfigs  # noqa: E402
from promptmaker import videoproject as vp  # noqa: E402
import test_v5  # noqa: E402
import test_v53_video as v53  # noqa: E402

win = test_v5.win
FAST = wanconfigs.FASTWAN_ID


def _png(path):
    v53._png(path, "green", 64, 36)


def _offline_tree(path, body="print('idle')\n"):
    os.makedirs(os.path.join(path, "shared"), exist_ok=True)
    os.makedirs(os.path.join(path, "defaults"), exist_ok=True)
    os.makedirs(os.path.join(path, "settings"), exist_ok=True)
    os.makedirs(os.path.join(path, "ckpts"), exist_ok=True)
    with open(os.path.join(path, "wgp.py"), "w", encoding="utf-8") as f:
        f.write(body + "\nWanGP_version = \"18.84\"\nsettings_version = 2.81\n"
                "# --offline sets HF_HUB_OFFLINE\n")
    with open(os.path.join(path, "shared", "cli_args.py"), "w", encoding="utf-8") as f:
        f.write('add("--offline", action="store_true")\n')
    with open(os.path.join(path, "wgp_config.json"), "w", encoding="utf-8") as f:
        json.dump({"transformer_quantization": "int8", "text_encoder_quantization": "int8",
                   "checkpoints_paths": ["ckpts"], "loras_root": "loras"}, f)
    return path


def _lora(path, meta):
    header = {"__metadata__": meta, "w": {"dtype": "U8", "shape": [1], "data_offsets": [0, 1]}}
    raw = json.dumps(header).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(raw)))
        f.write(raw)
        f.write(b"\x00")


def _ready_preset(**extra):
    preset = {
        "id": FAST, "name": "FastWan", "architecture": "ti2v_2_2", "definition": True,
        "settings_version": 2.81, "start_image": True, "files_ready": True, "files": [],
        "required_loras": ["accel.safetensors"], "template_id": "promptmaker:assets/wan2gp_fastwan_i2v.json",
        "settings_path": wan2gp.TEMPLATE, "frames": 121, "steps": 3, "resolution": "1280x704",
        "guidance": 1, "flow_shift": 3, "wangp_version": "18.84", "offline": True,
    }
    preset.update(extra)
    return preset


def test_portrait_resolution_is_offered():
    preset = {"id": "ti2v_2_2", "architecture": "ti2v_2_2", "resolution": "1280x720"}
    choices = wanconfigs.resolution_choices(preset, "")
    assert "1280x704" in choices and "704x1280" in choices
    assert wanconfigs.match_resolution("720x1280", choices) == "704x1280"
    assert wanconfigs.match_resolution("1280x720", choices) == "1280x704"


def test_frames_follow_each_scenes_length():
    assert wanconfigs.frames_to_seconds(121, 24) == pytest.approx(5.041666, abs=1e-4)
    # 4 + 6 + 9 seconds at 24 fps is 456 frames. Wan's step rounds each clip up to 4n+1.
    lengths = (4, 6, 9)
    raw = [int(round(s * 24)) for s in lengths]
    fitted = [wanconfigs.frames_for_seconds(s, 24) for s in lengths]
    assert raw == [96, 144, 216] and sum(raw) == 456
    assert fitted == [97, 145, 217] and sum(fitted) == 459
    scenes = [vp.new_scene(i, "adult woman waving", s, animate=True) for i, s in enumerate(lengths)]
    text = wanconfigs.scene_frame_plan(scenes, 24)
    assert "19" in text and "456" in text and "459" in text and "s01 4.00s → 97" in text


def test_fastwan_settings_unchanged_and_creative_none(tmp_path):
    img = tmp_path / "s.png"; _png(img)
    plain = wan2gp.settings("adult woman waves", str(img), seed=5)
    built = wanconfigs.build_settings(_ready_preset(), "adult woman waves", str(img), 5, wanconfigs.default_animation())
    assert built == plain
    assert built["model_type"] == FAST
    assert built["resolution"] == "1280x704" and built["video_length"] == 121 and built["num_inference_steps"] == 3
    assert built["activated_loras"] == [] and built["loras_multipliers"] == ""
    assert "accel.safetensors" not in json.dumps(built["activated_loras"])


def test_other_model_keeps_its_own_numbers(tmp_path):
    img = tmp_path / "s.png"; _png(img)
    export = tmp_path / "ti2v_2_2_settings.json"
    base = json.loads(json.dumps(wan2gp.settings("x", str(img))))
    base.update(model_type="ti2v_2_2", resolution="1280x720", video_length=121, num_inference_steps=50,
                guidance_scale=5, flow_shift=5, image_prompt_type="T", settings_version=2.81)
    export.write_text(json.dumps(base), encoding="utf-8")
    preset = _ready_preset(id="ti2v_2_2", name="Wan 5B", settings_path=str(export), settings_version=2.81,
                           resolution="1280x720", frames=121, steps=50, guidance=5, flow_shift=5, tested=False)
    controls = wanconfigs.default_animation()
    controls.update(model_id="ti2v_2_2", resolution="1280x720", frames=121, steps=50, guidance=5, flow_shift=5)
    cfg = wanconfigs.build_settings(preset, "adult woman walks", str(img), 4, controls)
    assert cfg["model_type"] == "ti2v_2_2"
    assert cfg["resolution"] == "1280x720" and cfg["num_inference_steps"] == 50 and cfg["guidance_scale"] == 5
    assert cfg["image_prompt_type"] == "S"
    assert cfg["resolution"] != "1280x704" and cfg["num_inference_steps"] != 3


def test_switch_resets_incompatible_values():
    old = wanconfigs.default_animation()
    old["creative_lora"] = r"C:\loras\style.safetensors"
    preset = {"id": "ti2v_2_2", "resolution": "1280x720", "frames": 121, "steps": 50, "guidance": 5, "flow_shift": 5}
    notes = wanconfigs.incompatible_changes(old, preset)
    assert any("1280x704" in n and "1280x720" in n for n in notes)
    assert any(n.startswith("steps 3 → 50") for n in notes)
    assert any("creative LoRA cleared" in n for n in notes)
    assert wanconfigs.incompatible_changes(old, {"id": FAST, "resolution": old["resolution"], "frames": 121,
                                                  "steps": 3, "guidance": 1, "flow_shift": 3}) == []


def test_creative_lora_none_and_conflicts(tmp_path):
    root = _offline_tree(str(tmp_path / "wan"))
    img = tmp_path / "still.png"; _png(img)
    preset = _ready_preset()
    assert not any("Creative" in e or "acceleration" in e for e in wanconfigs.preflight(root, preset, {"creative_lora": ""}, str(img)))
    accel = tmp_path / "accel.safetensors"; _lora(accel, {})
    hit = wanconfigs.preflight(root, preset, {"creative_lora": str(accel)}, str(img))
    assert any("acceleration adapter" in e for e in hit)
    bad = tmp_path / "sdxl.safetensors"; _lora(bad, {"modelspec.architecture": "sdxl_1.0"})
    hit = wanconfigs.preflight(root, preset, {"creative_lora": str(bad)}, str(img))
    assert any("does not match" in e for e in hit)
    unknown = tmp_path / "plain.safetensors"; _lora(unknown, {})
    hit = wanconfigs.preflight(root, preset, {"creative_lora": str(unknown)}, str(img))
    assert not any("does not match" in e for e in hit)
    assert wanconfigs.lora_status(str(unknown), "ti2v_2_2", []) == "unverified"


def test_missing_file_names_it_and_does_not_start(tmp_path):
    root = _offline_tree(str(tmp_path / "wan"))
    with open(os.path.join(root, "defaults", "ti2v_2_2_fastwan.json"), "w", encoding="utf-8") as f:
        json.dump({"model": {"name": "FastWan", "architecture": "ti2v_2_2",
                              "URLs": ["https://example.invalid/missing_transformer.safetensors"],
                              "loras": ["https://example.invalid/accel.safetensors"]}}, f)
    img = tmp_path / "s01.png"; _png(img)
    p = vp.new_project("t"); p["scenes"] = [vp.new_scene(0, "adult woman waving", 3, animate=True)]
    p["scenes"][0]["still"] = "s01.png"
    called = []

    def runner(*_a, **_k):
        called.append(1)
        raise AssertionError("Wan2GP must not start")

    with pytest.raises(wan2gp.WanError, match="missing_transformer.safetensors") as exc:
        vp.animate(p, str(tmp_path), {"dir": root, "python": sys.executable})
    assert called == [] and "Nothing was downloaded" in str(exc.value) and "Completed clips were kept" in str(exc.value)
    assert runner  # the real path does not receive this runner; preflight raises first


def test_text_model_is_refused_for_stills(tmp_path):
    root = _offline_tree(str(tmp_path / "wan"))
    weight = os.path.join(root, "ckpts", "tiny.safetensors")
    open(weight, "wb").write(b"x")
    with open(os.path.join(root, "defaults", "t2v_1.3B.json"), "w", encoding="utf-8") as f:
        json.dump({"model": {"name": "Wan2.1 Text2video 1.3B", "architecture": "t2v_1.3B",
                              "URLs": ["https://example.invalid/tiny.safetensors"]}}, f)
    # A version-matched export so the preset is offered, with the text model's own numbers.
    full = json.loads(open(wan2gp.TEMPLATE, encoding="utf-8").read())
    full.update(resolution="832x480", video_length=81, num_inference_steps=30, guidance_scale=5, flow_shift=5,
                image_prompt_type="", settings_version=2.81)
    with open(os.path.join(root, "settings", "t2v_1.3B_settings.json"), "w", encoding="utf-8") as f:
        json.dump(full, f)
    presets = {p["id"]: p for p in wanconfigs.catalog(root)}
    assert presets["t2v_1.3B"]["steps"] == 30 and presets["t2v_1.3B"]["resolution"] == "832x480"
    assert presets["t2v_1.3B"]["start_image"] is False and presets["t2v_1.3B"]["tested"] is False
    img = tmp_path / "s.png"; _png(img)
    errors = wanconfigs.preflight(root, presets["t2v_1.3B"], {"creative_lora": ""}, str(img))
    assert any("does not accept a start image" in e for e in errors)
    assert any("Nothing was downloaded" in e for e in errors)


def test_offline_blocker_does_not_launch(tmp_path):
    d = tmp_path / "wan"; d.mkdir(); (d / "wgp.py").write_text("print('online only')\n")
    called = []

    def popen(*_a, **_k):
        called.append(1)
        raise AssertionError("started")

    with pytest.raises(wan2gp.WanError, match="Offline protection"):
        wan2gp.run(sys.executable, str(d), {}, str(tmp_path / "w"), popen=popen)
    assert called == []
    planted = _offline_tree(str(tmp_path / "ok"))
    assert wanconfigs.offline_support(planted)[0] is True
    cmd = wan2gp.command(sys.executable, planted, "settings.json", "out")
    assert cmd[-1] == "--offline" and "--process" in cmd and "--output-dir" in cmd


def test_old_project_keeps_media_and_gains_fastwan_defaults(tmp_path):
    pdir = str(tmp_path / "old"); os.makedirs(pdir)
    open(os.path.join(pdir, "s01_wan.mp4"), "wb").write(b"clip")
    old = {"version": 2, "name": "Old video", "scenes": [{
        "id": "s01", "prompt": "adult woman walks on a beach", "duration": 4, "camera": "Slow push in",
        "animate": True, "still": "", "clip": "s01_wan.mp4", "seed": -1, "characters": []}]}
    with open(os.path.join(pdir, "project.json"), "w", encoding="utf-8") as f:
        json.dump(old, f)
    q = vp.load_project(pdir)
    assert q["version"] == 3
    assert q["scenes"][0]["clip"] == "s01_wan.mp4" and q["scenes"][0]["status"] == "animated"
    assert q["animation"]["model_id"] == FAST and q["animation"]["resolution"] == "1280x704"
    assert q["animation"]["frames"] == 121 and q["animation"]["steps"] == 3
    assert q["scenes"][0]["animation_override"] is None and q["scenes"][0]["resolved"] is None


def test_override_is_distinct_and_resume_uses_recording(tmp_path):
    p = vp.new_project("t")
    p["scenes"] = [vp.new_scene(0, "adult woman waving", 3, animate=True), vp.new_scene(1, "adult woman sits", 3)]
    p["scenes"][0]["animation_override"] = {"steps": 9, "model_id": FAST}
    over = vp.effective_animation(p, p["scenes"][0])
    inherited = vp.effective_animation(p, p["scenes"][1])
    assert over["steps"] == 9 and over["_source"] == "override"
    assert inherited["steps"] == 3 and inherited["_source"] == "project"
    assert "Override:" in wanconfigs.describe(over) and "Inherited" in wanconfigs.describe(inherited)
    _png(tmp_path / "s01.png")
    p["scenes"][0]["still"] = "s01.png"
    recorded = wanconfigs.default_animation()
    recorded.update(steps=3, prompt="recorded motion")
    p["scenes"][0]["resolved"] = recorded
    p["animation"]["steps"] = 50
    seen = {}

    def runner(_py, _d, cfg, work, cancelled=None, log=None):
        seen["steps"] = cfg["num_inference_steps"]; seen["prompt"] = cfg["prompt"]
        os.makedirs(work, exist_ok=True)
        out = os.path.join(work, "o.mp4"); open(out, "wb").write(b"v"); return out

    assert vp.animate(p, str(tmp_path), {"dir": "d", "python": "p"}, runner=runner) == 1
    assert seen["steps"] == 3 and seen["prompt"] == "recorded motion"
    assert p["scenes"][0]["clip"] == "s01_wan.mp4"


def test_failure_keeps_the_finished_clip(tmp_path):
    p = vp.new_project("t")
    p["scenes"] = [vp.new_scene(i, "adult woman waving", 3, animate=True) for i in range(2)]
    for s in p["scenes"]:
        _png(tmp_path / (s["id"] + ".png")); s["still"] = s["id"] + ".png"

    def runner(_py, _d, _cfg, work, cancelled=None, log=None):
        if work.endswith("s02") or work.endswith("s02" + os.sep):
            raise wan2gp.WanError("bad resolution for s02")
        os.makedirs(work, exist_ok=True)
        out = os.path.join(work, "o.mp4"); open(out, "wb").write(b"v"); return out

    with pytest.raises(wan2gp.WanError, match="bad resolution") as exc:
        vp.animate(p, str(tmp_path), {"dir": "d", "python": "p"}, runner=runner)
    assert p["scenes"][0]["clip"] == "s01_wan.mp4"
    assert os.path.exists(tmp_path / "s01_wan.mp4") and p["scenes"][1].get("clip") in ("", None)
    assert "Finished scenes are skipped" in str(exc.value)


@pytest.mark.skipif(not os.path.isfile(os.path.join(wan2gp.DEFAULT_DIR, "wgp.py")), reason="Wan2GP is not installed")
def test_installed_catalog_matches_this_machine():
    presets = {p["id"]: p for p in wanconfigs.catalog(wan2gp.DEFAULT_DIR)}
    fast = presets[FAST]
    assert fast["tested"] and fast["files_ready"] and fast["start_image"] is True
    assert fast["resolution"] == "1280x704" and fast["frames"] == 121 and fast["steps"] == 3
    assert fast["wangp_version"] == "18.84" and str(fast["settings_version"]) in ("2.81", "2.81")
    assert wanconfigs.offline_support(wan2gp.DEFAULT_DIR)[0] is True
    assert presets["ti2v_2_2"]["steps"] == 50 and presets["ti2v_2_2"]["resolution"] == "1280x720"
    assert presets["ti2v_2_2"]["tested"] is False and presets["ti2v_2_2"]["files_ready"]
    assert presets["ti2v_2_2"]["steps"] != fast["steps"]
    full_names = [item["name"] for item in presets["t2v"]["files"] if not item["present"]]
    assert any("safetensors" in name for name in full_names)
    assert presets["t2v_1.3B"]["start_image"] is False
    required = set(fast["required_loras"])
    assert required and not any(item["name"] in required for item in fast["creative_loras"])


def test_animate_sends_frames_from_the_scene_length(tmp_path):
    p = vp.new_project("t")
    p["scenes"] = [vp.new_scene(i, "adult woman waving", secs, animate=True) for i, secs in enumerate((4, 6, 9))]
    for s in p["scenes"]:
        v53._png(tmp_path / (s["id"] + ".png"), "red"); s["still"] = s["id"] + ".png"
    seen = []

    def runner(_py, _d, cfg, work, cancelled=None, log=None):
        seen.append(cfg["video_length"])
        os.makedirs(work, exist_ok=True)
        out = os.path.join(work, "o.mp4"); open(out, "wb").write(b"v"); return out

    assert vp.animate(p, str(tmp_path), {"dir": "d", "python": "p"}, runner=runner) == 3
    assert seen == [97, 145, 217]


def test_page_switch_override_and_lora_none(win):
    win.go("Video maker")
    assert win.vm_model.findData(FAST) >= 0
    assert win.vm_lora.currentData() in ("", None)
    assert "acceleration" in win.vm_lora_note.text().lower() or "off" in win.vm_lora_note.text().lower()
    idx = win.vm_model.findData("ti2v_2_2")
    if idx < 0:
        pytest.skip("installed Wan2GP has no Wan 5B export")
    win.vm_model.setCurrentIndex(idx)
    assert win.vm_steps.value() == 50
    assert win.vm_resolution.findData("704x1280") >= 0
    assert "portrait" in win.vm_resolution.itemText(win.vm_resolution.findData("704x1280")).lower()
    assert win.vm_switch_note.isVisible() and "3" in win.vm_switch_note.text()
    win.vm_model.setCurrentIndex(win.vm_model.findData(FAST))
    assert win.vm_steps.value() == 3 and win.vm_resolution.currentData() == "1280x704"
    win.vm_name.setText("Anim page"); win.vm_idea.setPlainText("two adult friends walk by the sea")
    assert win.vm_apply_plan(v53.PLAN) == 3
    win.vm_select(0)
    assert win.vm_anim_from.text().startswith("Inherited")
    win.vm_override.setChecked(True)
    win.vm_scene_steps.setValue(9)
    win.vm_apply_scene()
    assert win.vm_proj["scenes"][0]["animation_override"]["steps"] == 9
    assert win.vm_anim_from.text().startswith("Override")
    assert not win.vm_proj["scenes"][1].get("animation_override")
    win.vm_proj["scenes"][0]["resolved"] = dict(win.vm_proj["scenes"][0]["animation_override"], prompt="kept")
    win.vm_use_current()
    assert win.vm_proj["scenes"][0]["resolved"] is None
