from promptmaker import imagegen
from promptmaker.imagegen import A1111, Job

MODS = [{"model_name": "qwen_image_vae.safetensors", "filename": "C:/F/models/VAE/qwen_image_vae.safetensors"},
        {"model_name": "qwen_3_06b_base.safetensors", "filename": "C:/F/models/text_encoder/qwen_3_06b_base.safetensors"},
        {"model_name": "qwen3vl_4b.safetensors", "filename": "C:/F/models/text_encoder/qwen3vl_4b.safetensors"}]


def _job(ck="lustifySDXL.safetensors", fam="Stable Diffusion", base="sdxl"):
    j = Job("p", "", 1024, 1024, 1, 20, 6.0, "x", ck)
    j.profile_family, j.profile_base = fam, base
    return j


def _be(monkeypatch, mods=MODS, fail=False):
    calls = []
    def fake(url, data=None, timeout=30):
        calls.append(url)
        if fail:
            raise imagegen.BackendError("HTTP 404: Not Found")
        return mods
    monkeypatch.setattr(imagegen, "_http", fake)
    return A1111(), calls


def test_sdxl_clears_modules(monkeypatch):
    be, _ = _be(monkeypatch)
    assert be.payload(_job())["override_settings"]["forge_additional_modules"] == []


def test_anima_picks_vae_and_te(monkeypatch):
    be, calls = _be(monkeypatch)
    ov = be.payload(_job("anima-preview.safetensors", "Anima", "anima"))["override_settings"]
    assert ov["forge_additional_modules"] == [MODS[0]["filename"], MODS[1]["filename"]]
    be.payload(_job())
    assert len(calls) == 1  # cached


def test_anima_by_checkpoint_name(monkeypatch):
    be, _ = _be(monkeypatch)
    assert len(be.payload(_job("my_anima_v2.safetensors", "", ""))["override_settings"]["forge_additional_modules"]) == 2


def test_anima_without_modules_skips(monkeypatch):
    be, _ = _be(monkeypatch, mods=[MODS[2]])
    assert "forge_additional_modules" not in be.payload(_job("anima.safetensors", "Anima", "anima"))["override_settings"]


def test_plain_a1111_skips(monkeypatch):
    be, _ = _be(monkeypatch, fail=True)
    assert be.modules() == []
    assert "forge_additional_modules" not in be.payload(_job())["override_settings"]


def test_flux_untouched(monkeypatch):
    be, _ = _be(monkeypatch)
    assert "forge_additional_modules" not in be.payload(_job("flux1-dev.safetensors", "FLUX", "flux"))["override_settings"]


def test_profile_override_wins(monkeypatch):
    be, _ = _be(monkeypatch)
    j = _job(); j.forge_modules = ["qwen_image_vae"]
    assert be.payload(j)["override_settings"]["forge_additional_modules"] == [MODS[0]["filename"]]


def test_no_checkpoint_no_key(monkeypatch):
    be, calls = _be(monkeypatch)
    assert "override_settings" not in be.payload(_job(ck=""))
    assert calls == []


def test_hires_keeps_same_choices(monkeypatch):
    be, _ = _be(monkeypatch)
    j = _job(); j.hires = {"scale": 1.5}
    assert be.payload(j)["hr_additional_modules"] == ["Use same choices"]


def test_scheduler_in_payload(monkeypatch):
    be, _ = _be(monkeypatch)
    j = _job(); j.scheduler = "Karras"
    assert be.payload(j)["scheduler"] == "Karras"
    j.scheduler = "normal"
    assert "scheduler" not in be.payload(j)  # comfy-style fallback: let Forge choose (Automatic)


def test_sampler_scheduler_lists(monkeypatch):
    def fake(url, data=None, timeout=30):
        if url.endswith("/samplers"):
            return [{"name": "DPM++ 2M"}, {"name": "Euler a"}]
        if url.endswith("/schedulers"):
            raise imagegen.BackendError("HTTP 404")
        if "KSampler" in url:
            return {"KSampler": {"input": {"required": {"sampler_name": [["euler", "dpmpp_2m"]], "scheduler": [["karras"]]}}}}
    monkeypatch.setattr(imagegen, "_http", fake)
    assert A1111().samplers() == ["DPM++ 2M", "Euler a"]
    assert A1111().schedulers() == imagegen.DEFAULT_SCHEDULERS
    c = imagegen.ComfyUI()
    assert c.samplers() == ["euler", "dpmpp_2m"] and c.schedulers() == ["karras"]
