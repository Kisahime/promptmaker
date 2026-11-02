"""5.2: Jib Mix Moss Realistic regression (real Civitai description) + sampler/scheduler pair, ranges, custom nodes,
honest source map / tips, repair of the bad saved profile, generation-time fallback."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from promptmaker import civitai, civitai_browser as cb, imagegen, profilenorm as pn, profiles  # noqa: E402

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "civitai_jibmix_moss_3435334.json"), encoding="utf-8"))
JM, JV = FIX["model"], FIX["version"]

JIB_BAD = {  # the profile 5.2 (8a6150a) actually saved
    "id": "civitai_3435334", "inherits": "moss", "family": "MOSS", "name": "Jib Mix Moss Realistic V2 - Reality Renew (Civitai)",
    "ai_guidance": "MOSS-Image: captions. Checkpoint 'Jib Mix Moss Realistic V2 - Reality Renew' (Civitai, base MOSS Image).",
    "quality_prefix": "", "negative_default": "nsfw, worst quality",
    "civitai": {"matched_section": "V2 Improves the overall look,", "type": "Diffusion model", "version_id": 3435334, "model_id": 3016339,
                "warnings": ["unknown scheduler 'Bong tangent' – using the family default",
                             "Forge has no 'er_sde' sampler – Forge uses its own default"]},
    "gen": {"a1111_scheduler": "Simple", "cfg": 1.0, "sampler": "er_sde", "scheduler": "simple", "steps": 12,
            "text_encoder": "qwen3.5_9b_w4a8_gptq.safetensors", "vae": "flux2-vae_small.safetensors", "workflow": "moss_txt2img"},
    "settings": "Steps 12 · CFG 1 · Sampler er_sde · Scheduler simple",
    "source": {"a1111_scheduler": "family default", "cfg": "author", "sampler": "author", "scheduler": "user", "steps": "author",
               "workflow": "family default"},
    "tips": ["Creator's settings: Steps 12 · CFG 1 · Sampler er_sde · Scheduler simple.",
             "Use the moss_txt2img ComfyUI workflow; it does not run in Forge."]}


def _jib():
    return cb.build_profile(JM, JV, cb.files(JV)[0], profiles.load())


def test_jib_mix_real_description():
    p = _jib(); g, src, c = p["gen"], p["source"], p["civitai"]
    # V2's own changelog says 'Recommended 12 steps' – that wins; the general (V1-era) '4- 9 steps' is kept as other info
    assert (g["steps"], g["cfg"], g["sampler"], g["scheduler"]) == (12, 1.0, "er_sde", "bong_tangent")
    assert g["custom_nodes"] == {"bong_tangent": "RES4LYF"} and "a1111_scheduler" not in g and "a1111_sampler" not in g
    assert all(src[k] == "author" for k in ("steps", "cfg", "sampler", "scheduler")) and "user" not in src.values()
    assert c["other_author_values"] == {"steps": "4–9"}
    assert "12 steps" in c["matched_section"] and "er_sde/Bong_tangent" in c["matched_section"]
    assert "overall look" not in c["matched_section"]
    assert not any("unknown scheduler" in w for w in c.get("warnings", []))
    assert p["tips"][0] == "Creator's settings: Steps 12 · CFG 1 · Sampler er_sde · Scheduler bong_tangent."
    assert any("RES4LYF" in t for t in p["tips"]) and any("4–9" in t for t in p["tips"])
    assert "simple" not in p["settings"] and "needs RES4LYF" in p["settings"]
    assert pn.validate(p) == []


def test_jib_general_text_alone_gives_range():
    lines = civitai.html_to_lines(JM["description"].split("<hr />")[1])
    st = pn.parse_settings(lines, "V1: One to One")
    g, src, _ = pn.normalise_gen({k: st.get(k) for k in ("steps", "cfg", "sampler", "scheduler", "steps_text", "cfg_text")}, "MOSS")
    assert (g["steps"], g["steps_range"], g["cfg"], g["sampler"], g["scheduler"]) == (6, "4–9", 1.0, "er_sde", "bong_tangent")
    assert "4- 9 steps er_sde/Bong_tangent" in st["section"]


@pytest.mark.parametrize("txt", ["4- 9 steps", "4 -9 steps", "4~9 steps", "4 to 9 steps", "steps: 4–9", "Steps 4 - 9"])
def test_step_range_spacing(txt):
    r = pn.extract(txt)
    assert (r["steps"], r["steps_text"]) == (6, "4–9")


def test_to_needs_word_boundary():
    assert pn.extract("steps: 8 tomorrow 30")["steps_text"] == "8"


@pytest.mark.parametrize("text,expect", [
    ("er_sde/Bong_tangent", ("er_sde", "bong_tangent")), ("euler/beta", ("euler", "beta")), ("Euler / Beta", ("euler", "beta")),
    ("ER_SDE / bong tangent", ("er_sde", "bong_tangent")), ("res_2s/beta57", ("res_2s", "beta57")),
    ("res_multistep / simple", ("res_multistep", "simple")), ("er_sde / dpmpp_2m_sde_gpu", ("er_sde", None)),
    ("dpmpp_2m_sde_gpu + beta57", ("dpmpp_2m_sde_gpu", "beta57"))])
def test_slash_pairs(text, expect):
    assert pn.split_sampler(text) == expect


def test_unknown_plausible_kept_garbage_rejected():
    g, src, w = pn.normalise_gen({"sampler": "euler", "scheduler": "my_fancy_sched"}, "MOSS")
    assert g["scheduler"] == "my_fancy_sched" and src["scheduler"] == "author"
    assert g["custom_nodes"] == {"my_fancy_sched": "unknown custom node"} and any("custom node" in x for x in w)
    prof = {"id": "x", "name": "x", "gen": g}
    assert pn.validate(prof) == []
    g2, src2, w2 = pn.normalise_gen({"scheduler": "garbled???"}, "MOSS")
    assert g2["scheduler"] == "simple" and src2["scheduler"] == "family default" and any("unreadable" in x for x in w2)
    assert pn.validate({"id": "x", "name": "x", "gen": {"scheduler": "my_fancy_sched"}})  # no custom_nodes note → invalid


def test_settings_tips_are_honest():
    g, src, _ = pn.normalise_gen({"cfg": 1}, "MOSS")
    tips = pn.creator_tips(g, src)
    assert tips[0] == "Creator's settings: CFG 1."
    assert tips[1].startswith("Defaults used: steps 25 (family default)") and "scheduler simple" in tips[1]
    assert "family default" in pn.settings_line(g, src)


def test_user_only_when_accepted(monkeypatch):
    info = {"model": JM, "version": JV, "images": [], "url": "u"}
    s = civitai.suggest(info)
    s2 = dict(s, scheduler="garbled???", user_edited=["scheduler"])
    p = civitai.build_profile(info, s2, "moss", profiles.load())
    assert p["source"]["scheduler"] == "family default"  # rejected input is not labelled 'user'
    s3 = dict(s, steps=10, steps_text="", user_edited=["steps"])
    p = civitai.build_profile(info, s3, "moss", profiles.load())
    assert p["source"]["steps"] == "user" and "steps_range" not in p["gen"]
    assert any(t.startswith("Your settings: Steps 10") for t in p["tips"])
    assert not any("Steps 10" in t for t in p["tips"] if t.startswith("Creator's"))


def test_repair_fixes_saved_jib_profile(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"profiles": [JIB_BAD]}), encoding="utf-8")
    rep = pn.repair_file(str(path), profiles.load())
    assert "civitai_3435334" in rep
    p = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]
    g = p["gen"]
    assert g["scheduler"] == "bong_tangent" and p["source"]["scheduler"] == "author" and "a1111_scheduler" not in g
    assert g["custom_nodes"] == {"bong_tangent": "RES4LYF"}
    assert "matched_section" not in p["civitai"]
    assert not any("unknown scheduler" in w for w in p["civitai"]["warnings"])
    assert p["tips"][0] == "Creator's settings: Steps 12 · CFG 1 · Sampler er_sde · Scheduler bong_tangent."
    assert "simple" not in p["settings"]
    assert pn.validate(p) == [] and pn.repair_file(str(path), profiles.load()) == {}


def test_recheck_rebuild_matches_fresh():
    # ⟳ Re-check from Civitai re-runs suggest + build_profile on the fetched data, keeping the existing id
    info = {"model": JM, "version": JV, "images": [], "url": "u"}
    p = civitai.build_profile(info, civitai.suggest(info), "moss", profiles.load(), pid=JIB_BAD["id"])
    assert p["id"] == "civitai_3435334" and p["gen"]["scheduler"] == "bong_tangent" and pn.validate(p) == []


@pytest.mark.parametrize("desc,want", [
    ("<p>Settings: 6-8 steps, CFG 1, sampler res_2s, scheduler beta57</p>", (7, 1.0, "res_2s", "beta57")),
    ("<p>I use euler/beta 20 to 30 steps cfg 3.5</p>", (25, 3.5, "euler", "beta")),
    ("<p>Recommended: 8 Steps · CFG=1.0 · res_multistep / Bong Tangent</p>", (8, 1.0, "res_multistep", "bong_tangent")),
    ("<p>Steps ~ 4~6</p><p>dpmpp_2m_sde_gpu/karras</p><p>cfg 1-1.5</p>", (5, 1.0, "dpmpp_2m_sde_gpu", "karras")),
])
def test_realistic_variants(desc, want):
    st = pn.parse_settings(civitai.html_to_lines(desc), "V1")
    g, _, _ = pn.normalise_gen({k: st.get(k) for k in ("steps", "cfg", "sampler", "scheduler", "steps_text", "cfg_text")}, "MOSS")
    assert (g["steps"], g["cfg"], g["sampler"], g["scheduler"]) == want


def test_generation_time_fallback(monkeypatch):
    be = imagegen.ComfyUI("http://x")
    lists = {"sampler_name": ["euler", "er_sde"], "scheduler": ["simple", "normal", "beta"]}
    monkeypatch.setattr(be, "_ksampler", lambda k: lists[k])

    class J:
        pass
    j = J(); vals = {"sampler": "er_sde", "scheduler": "bong_tangent"}
    be.check_installed(j, vals)
    assert vals == {"sampler": "er_sde", "scheduler": "simple"} and "RES4LYF" in j.warnings[0]
    lists["scheduler"].append("bong_tangent"); be._ks_cache = {}
    vals = {"sampler": "er_sde", "scheduler": "bong_tangent"}; be.check_installed(J(), vals)
    assert vals["scheduler"] == "bong_tangent"
