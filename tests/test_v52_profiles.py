"""5.2: model-profile parsing, normalisation, validation, repair – regression tests from real bad profiles."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from promptmaker import civitai, civitai_browser as cb, imagegen, profilenorm as pn, profiles  # noqa: E402

# ---- (A) Fn-Moment Anima-Turbo: multi-version description, the V5 no-turbo line is the one that counts
FN_DESC = (
    "<h2>Fn-Moment Anima-Turbo</h2><p>Anime model based on Anima 2.9B. Turbo and no-turbo builds.</p>"
    "<p><strong>Recommended settings</strong></p>"
    "<p>Steps 12/30(V3.0 no turbo)</p><p>CFG 1/4-5(V3.0 no turbo)</p>"
    "<p>Sampler: er_sde / dpmpp_2m_sde_gpu</p><p>Scheduler: simple / beta)</p>"
    "<h3>V5.0 update</h3>"
    "<p>V5.0 turbo: euler_a + sgm_uniform, steps: 8, cfg: 1</p>"
    "<p>V5.0 no turbo: recommended to use dpmpp_2m_sde_gpu + beta1_1, steps: 25, cfg: 4</p>"
    "<p>No negative prompt needed.</p>")
FN_V = {"id": 3300001, "modelId": 2900001, "name": "V5.0-2.9B-no turbo", "baseModel": "Anima", "trainedWords": [],
        "description": "", "files": [{"id": 11, "name": "fnMomentAnimaTurbo_v502_9BNoTurbo.safetensors", "sizeKB": 4.4e6,
                                      "primary": True, "metadata": {"fp": "bf16", "format": "SafeTensor"}}]}
FN_M = {"id": 2900001, "name": "Fn-Moment Anima-Turbo", "type": "Checkpoint", "description": FN_DESC, "modelVersions": [FN_V]}
FN_BAD = {"id": "civitai_3300001", "name": "Fn-Moment Anima-Turbo V5.0-2.9B-no turbo (Civitai)", "inherits": "anima",
          "family": "Anima", "gen": {"steps": 12, "cfg": 1.0, "sampler": "dpmpp_2m_sde_gpu", "scheduler": "beta)",
                                     "a1111_sampler": "dpmpp_2m_sde_gpu"},
          "settings": "Steps 12/30(V3.0 no turbo) · CFG 1/4-5(V3.0 no turbo) · Sampler er_sde / dpmpp_2m_sde_gpu · Scheduler beta)",
          "ai_guidance": "Anima: tags. Checkpoint 'Fn-Moment Anima-Turbo V5.0-2.9B-no turbo' (Civitai, base Anima):",
          "tips": ["Recommended by the model creator on Civitai (n/a).", "Use natural language or tags."],
          "civitai": {"type": "Checkpoint", "negative_source": "", "file_name": "x.safetensors"}}

# ---- (B) Moody Moss Mix V3.3: diffusion-model-only fp8 file, 'Euler Simple', CFG range
MOSS_DESC = ("<p>Moody Moss Mix – raw, realistic portraits with moody light.</p>"
             "<p>Recommended:</p><p>Steps: 25 (Optimized for this speed)</p><p>CFG: 3.5 - 5.0</p>"
             "<p>Sampler: Euler Simple</p><p>免费下载 – free download</p>")
MOSS_V = {"id": 3435978, "modelId": 3007871, "name": "V3.3 25STEPS CFG3", "baseModel": "MOSS Image", "trainedWords": [],
          "description": "", "files": [
              {"id": 3332948, "name": "moodyMossMixFreeDownload_v3325STEPSCFG3_3332948.safetensors", "sizeKB": 4.73e9 / 1024,
               "type": "Model", "primary": True, "metadata": {"fp": "fp8", "format": "SafeTensor"}}]}
MOSS_M = {"id": 3007871, "name": "Moody Moss Mix (Free download 免费下载)", "type": "Checkpoint", "description": MOSS_DESC,
          "modelVersions": [MOSS_V]}
MOSS_BAD = {"id": "civitai_3435978", "name": "Moody Moss Mix V3.3 (Civitai)", "inherits": "moss", "family": "MOSS",
            "gen": {"a1111_sampler": "Euler Simple", "cfg": 3.5, "sampler": "euler", "scheduler": "normal", "steps": 25},
            "settings": "Steps 25 · CFG 3.5 · Sampler Euler Simple",
            "ai_guidance": "MOSS-Image: captions. Checkpoint 'Moody Moss Mix' (Civitai, base MOSS Image):",
            "tips": ["Recommended by the model creator on Civitai (n/a).", "Describe the finished image."],
            "civitai": {"type": "Checkpoint", "file_name": "moodyMossMixFreeDownload_v3325STEPSCFG3_fp8.safetensors"}}


def test_regression_a_fn_moment():
    prof = cb.build_profile(FN_M, FN_V, cb.files(FN_V)[0], profiles.load())
    g, src = prof["gen"], prof["source"]
    assert (g["steps"], g["cfg"], g["sampler"], g["scheduler"], g["a1111_sampler"], g["a1111_scheduler"]) == \
        (25, 4.0, "dpmpp_2m_sde_gpu", "beta", "DPM++ 2M SDE", "Beta")
    assert all(src[k] == "author" for k in ("steps", "cfg", "sampler", "scheduler"))
    assert "V5.0 no turbo" in prof["civitai"]["matched_section"]
    assert "V3.0" not in prof["settings"] and "12/30" not in prof["settings"] and ")" not in prof["settings"].replace("(", "")
    assert not any("n/a" in t for t in prof["tips"]) and not prof["ai_guidance"].endswith(":")
    assert prof["negative_default"] == "" and prof["civitai"]["author_negative"] == ""
    assert prof["civitai"]["negative_source"] == "author: not needed"
    assert pn.validate(prof) == []


def test_regression_a_turbo_variant_picks_turbo_line():
    v = dict(FN_V, name="V5.0-2.9B-turbo")
    s = civitai.suggest({"model": FN_M, "version": v, "images": [], "url": "u"})
    assert (s["steps"], s["cfg"], s["sampler"]) == (8, 1.0, "euler_ancestral") and s["scheduler"] == "sgm_uniform"


def test_regression_b_moody_moss():
    prof = cb.build_profile(MOSS_M, MOSS_V, cb.files(MOSS_V)[0], profiles.load(), "civitai.red",
                            file_name="moodyMossMixFreeDownload_v3325STEPSCFG3_fp8.safetensors")
    g, c = prof["gen"], prof["civitai"]
    assert (g["steps"], g["cfg"], g["cfg_range"], g["sampler"], g["scheduler"], g["a1111_sampler"], g["a1111_scheduler"]) == \
        (25, 3.5, "3.5–5", "euler", "simple", "Euler", "Simple")
    assert (g["workflow"], g["text_encoder"], g["vae"]) == ("moss_txt2img", "qwen3.5_9b_w4a8_gptq.safetensors", "flux2-vae_small.safetensors")
    assert prof["source"]["workflow"] == "family default" and prof["source"]["sampler"] == "author"
    assert c["file_name"] == "moodyMossMixFreeDownload_v3325STEPSCFG3_fp8.safetensors" and c["type"] == "Diffusion model"
    assert all(int(x) % 16 == 0 for r in prof["resolutions"].values() for x in r.split("x"))
    assert prof["negative_default"]  # inherited family negative is fine …
    assert c["author_negative"] == "" and c["negative_source"] == ""  # … but never recorded as the author's
    assert pn.validate(prof) == []


def test_repair_both_bad_profiles(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"profiles": [FN_BAD, MOSS_BAD, {"id": "ok", "name": "ok"}]}), encoding="utf-8")
    report = pn.repair_file(str(path), profiles.load())
    assert set(report) == {"civitai_3300001", "civitai_3435978"}
    assert any(p.name.startswith("profiles.json.bak-") for p in tmp_path.iterdir())
    fixed = {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))["profiles"]}
    a, b = fixed["civitai_3300001"], fixed["civitai_3435978"]
    assert a["gen"]["scheduler"] == "beta" and a["gen"]["a1111_sampler"] == "DPM++ 2M SDE"
    assert not any("n/a" in t for t in a["tips"]) and not a["ai_guidance"].endswith(":")
    assert b["gen"]["a1111_sampler"] == "Euler" and b["gen"]["scheduler"] == "simple"
    assert b["civitai"]["type"] == "Diffusion model"
    assert pn.validate(a) == [] and pn.validate(b) == []
    assert pn.repair_file(str(path), profiles.load()) == {}  # idempotent


@pytest.mark.parametrize("text,expect", [
    ("Euler Simple", ("euler", "simple")), ("dpmpp_2m_sde_gpu + beta1_1", ("dpmpp_2m_sde_gpu", "beta")),
    ("DPM++ 2M Karras", ("dpmpp_2m", "karras")), ("euler a or DPM++ 2M Karras", ("euler_ancestral", None)),
    ("Euler a nomal", ("euler_ancestral", "normal")), ("er_sde, simple", ("er_sde", "simple")),
    ("DPM++ 2M SDE Exponential", ("dpmpp_2m_sde", "exponential")), ("res_multistep simple", ("res_multistep", "simple")),
    ("beta)", (None, "beta")), ("garbled???", (None, None))])
def test_split_sampler(text, expect):
    assert pn.split_sampler(text) == expect


def test_extract_chinese_ranges_and_typos():
    r = pn.extract("采样器：Euler a，步数：20-30，提示词引导系数：5~7，调度器：karas")
    assert (r["sampler"], r["steps"], r["steps_text"], r["cfg"], r["scheduler"]) == ("euler_ancestral", 25, "20–30", 5.0, "karras")
    assert pn.extract("CFG 3.5 - 5.0")["cfg_text"] == "3.5–5" and pn.extract("CFG: 3-7")["cfg"] == 5.0
    assert pn.extract("不需要负面提示词").get("negative_none")


def test_normalise_never_stores_unknown_values():
    g, src, warn = pn.normalise_gen({"sampler": "my secret sauce", "scheduler": "wobbly", "steps": "abc"}, "MOSS")
    assert g["sampler"] == "er_sde" and src["sampler"] == "family default" and g["scheduler"] == "simple"
    assert "a1111_sampler" not in g and len(warn) >= 3  # Forge has no er_sde – warned, not invented
    assert all(v in pn.SAMPLERS for v in [g["sampler"]]) and isinstance(g["steps"], int)


def test_validate_catches_bad_profiles():
    errs = pn.validate(FN_BAD)
    assert any("scheduler" in e for e in errs) and any("a1111_sampler" in e for e in errs)
    assert any("n/a" in e for e in errs) and any("dangling" in e for e in errs)
    assert pn.validate(MOSS_BAD) and all(pn.validate(p) == [] for p in profiles.load().values())


def test_ai_json_is_constrained_by_normaliser():
    reply = 'Sure! {"steps": "25", "cfg": 4, "sampler": "DPM++ 2M SDE Beta", "scheduler": null, "extra": "x"}'
    g, src, warn = pn.parse_ai_json(reply, "Anima")
    assert (g["steps"], g["cfg"], g["sampler"], g["scheduler"]) == (25, 4.0, "dpmpp_2m_sde", "beta") and src["steps"] == "ai"
    g, src, _ = pn.parse_ai_json("no json here", "MOSS")
    assert src["sampler"] == "family default"
    msgs = pn.ai_extract_messages("text", "V5")
    assert "JSON only" in msgs[0]["content"]


def test_profile_text_encoder_vae_reach_the_moss_workflow(monkeypatch):
    c = imagegen.ComfyUI("http://x")
    files = {"CLIPLoader": ["qwen3.5_9b_bf16.safetensors", "moss/qwen3.5_9b_w4a8_gptq.safetensors"],
             "VAELoader": ["flux2-vae.safetensors", "flux2-vae_small.safetensors"]}
    monkeypatch.setattr(c, "node_files", lambda node, key=None: files.get(node, []))
    meta = {"defaults": {"text_encoder": "qwen3.5_9b_bf16.safetensors", "vae": "flux2-vae.safetensors"}}
    j = imagegen.Job("x"); j.text_encoder_pref, j.vae_pref = "qwen3.5_9b_w4a8_gptq.safetensors", "flux2-vae_small.safetensors"
    c.resolve_files(j, meta)
    assert (j.text_encoder, j.vae) == ("moss/qwen3.5_9b_w4a8_gptq.safetensors", "flux2-vae_small.safetensors")
    j2 = imagegen.Job("x"); j2.text_encoder_pref = "missing.safetensors"
    c.resolve_files(j2, meta)
    assert j2.text_encoder == "qwen3.5_9b_bf16.safetensors"  # profile file not installed → workflow default


def test_review_dialog_flags_defaults_and_validates(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    from promptmaker.profilereview import ProfileReviewDialog
    app = QApplication.instance() or QApplication([])
    prof = cb.build_profile(MOSS_M, MOSS_V, cb.files(MOSS_V)[0], profiles.load())
    parent = QWidget()
    d = ProfileReviewDialog(parent, prof)
    assert "workflow" in d.flagged and "sampler" not in d.flagged
    d.scheduler.setCurrentIndex(d.scheduler.findData("karras")); app.processEvents()
    out = d.profile()
    assert out["gen"]["scheduler"] == "karras" and out["gen"]["a1111_scheduler"] == "Karras" and out["source"]["scheduler"] == "user"
    got = []
    d.saved.connect(got.append); d.steps.setValue(30); d.save()
    assert got and got[0]["gen"]["steps"] == 30
    d2 = ProfileReviewDialog(parent, dict(prof, name=""))
    d2.name.setText(""); prof2 = d2.profile(); prof2["id"] = ""
    assert pn.validate(prof2)
