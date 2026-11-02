"""5.2: moss_txt2img ComfyUI workflow (UNETLoader + CLIPLoader moss_image + FLUX.2 VAE, optional SLG)."""
import pytest

from promptmaker import imagegen

OBJ = {
    "UNETLoader": {"UNETLoader": {"input": {"required": {"unet_name": [["moodyMoss_fp8.safetensors", "moss_image_sft_int8_convrot.safetensors"]]}}}},
    "CheckpointLoaderSimple": {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["novaAnime.safetensors"]]}}}},
    "CLIPLoader": {"CLIPLoader": {"input": {"required": {"clip_name": [["clip_l.safetensors", "qwen3.5_9b_w4a8_gptq.safetensors"]]}}}},
    "VAELoader": {"VAELoader": {"input": {"required": {"vae_name": [["sdxl_vae.safetensors", "flux2-vae_small.safetensors"]]}}}},
}


class Sent(Exception):
    pass


@pytest.fixture
def comfy(monkeypatch):
    sent = {}

    def fake(url, data=None, **_k):
        if "/object_info/" in url:
            return OBJ.get(url.rsplit("/", 1)[1], {})
        if url.endswith("/prompt"):
            sent["wf"] = data["prompt"]
            raise Sent()
        return {}
    monkeypatch.setattr(imagegen, "_http", fake)
    monkeypatch.setenv("PROMPTMAKER_NO_WS", "1")
    return imagegen.ComfyUI("http://x"), sent


def _moss():
    return imagegen.load_workflow(imagegen.list_workflows()["moss_txt2img"])


def _job(meta, **kw):
    d = meta["defaults"]
    j = imagegen.Job("1girl, autumn", d["negative"], 1280, 720, 42, d["steps"], d["cfg"], checkpoint="moodyMoss_fp8.safetensors",
                     workflow="moss_txt2img", sampler=d["sampler"], scheduler=d["scheduler"])
    j.workflow_meta = meta
    for k, v in kw.items():
        setattr(j, k, v)
    return j


def test_workflow_loads_with_defaults():
    wf, meta = _moss()
    assert "moss_txt2img" in imagegen.list_workflows()
    types = {n["class_type"] for n in wf.values()}
    assert {"UNETLoader", "CLIPLoader", "VAELoader", "EmptyFlux2LatentImage", "KSampler", "VAEDecode",
            "SkipLayerGuidanceDiTSimple", "SaveImage"} <= types
    assert meta["model_loader"] == "UNETLoader" and meta["family"] == "MOSS"
    d = meta["defaults"]
    assert (d["steps"], d["cfg"], d["sampler"], d["scheduler"], d["width"], d["height"]) == (25, 3.5, "euler", "simple", 1024, 1024)
    assert d["negative"] == "worst quality, bad anatomy, watermark, jpeg artifact" and d["slg"] is False
    assert wf["2"]["inputs"]["type"] == "moss_image"


def test_injection_and_autodetect_slg_off(comfy):
    b, sent = comfy
    wf, meta = _moss()
    with pytest.raises(Sent):
        b.generate(_job(meta), wf)
    w = sent["wf"]
    assert w["1"]["inputs"] == {"unet_name": "moodyMoss_fp8.safetensors", "weight_dtype": "default"}
    assert w["2"]["inputs"]["clip_name"] == "qwen3.5_9b_w4a8_gptq.safetensors"
    assert w["3"]["inputs"]["vae_name"] == "flux2-vae_small.safetensors"
    assert w["6"]["inputs"] == {"width": 1280, "height": 720, "batch_size": 1}
    k = w["7"]["inputs"]
    assert (k["seed"], k["steps"], k["cfg"], k["sampler_name"], k["scheduler"]) == (42, 25, 3.5, "euler", "simple")
    assert w["4"]["inputs"]["text"] == "1girl, autumn" and w["5"]["inputs"]["text"].startswith("worst quality")
    assert "15" not in w and k["model"] == ["1", 0]            # SLG bypassed by default
    assert "{{" not in str(w)


def test_slg_on_and_hires(comfy):
    b, sent = comfy
    wf, meta = _moss()
    j = _job(meta, slg=True)
    j.hires = {"scale": 1.5, "denoise": 0.3, "steps": 0}
    with pytest.raises(Sent):
        b.generate(j, wf)
    w = sent["wf"]
    assert w["15"]["inputs"]["model"] == ["1", 0] and w["15"]["inputs"]["single_layers"] == "22"
    assert w["7"]["inputs"]["model"] == ["15", 0]
    hr = [n for n, v in w.items() if n.endswith("pm_hr_ks")]
    assert hr and w["8"]["inputs"]["samples"] == [hr[0], 0]
    assert w[hr[0]]["inputs"]["denoise"] == 0.3 and w[hr[0]]["inputs"]["model"] == ["15", 0]


def test_explicit_files_and_fallback(comfy, monkeypatch):
    b, sent = comfy
    wf, meta = _moss()
    with pytest.raises(Sent):
        b.generate(_job(meta, text_encoder="my_te.safetensors", vae="my_vae.safetensors"), wf)
    assert sent["wf"]["2"]["inputs"]["clip_name"] == "my_te.safetensors" and sent["wf"]["3"]["inputs"]["vae_name"] == "my_vae.safetensors"
    assert imagegen.pick_file(["moss/qwen3.5_9b_w4a8_gptq.safetensors"], "qwen3.5_9b_w4a8_gptq.safetensors") == "moss/qwen3.5_9b_w4a8_gptq.safetensors"
    assert imagegen.pick_file(["a.safetensors", "qwen3.5_9b_bf16.safetensors"], "x.safetensors", ("qwen3.5",)) == "qwen3.5_9b_bf16.safetensors"
    assert imagegen.pick_file([], "x.safetensors") == "x.safetensors"


def test_model_list_uses_unet_loader(comfy):
    b, _ = comfy
    assert b.checkpoints() == ["novaAnime.safetensors"]
    b.model_loader = "UNETLoader"
    assert b.checkpoints() == ["moodyMoss_fp8.safetensors", "moss_image_sft_int8_convrot.safetensors"]


def test_suggest_workflow():
    assert imagegen.suggest_workflow("MOSS", "sdxl_txt2img") == "moss_txt2img"
    assert imagegen.suggest_workflow("MOSS", "moss_txt2img") is None
    assert imagegen.suggest_workflow("Anima", "sdxl_txt2img") is None


def test_sdxl_workflow_unchanged(comfy):
    b, sent = comfy
    wf, meta = imagegen.load_workflow(imagegen.list_workflows()["sdxl_txt2img"])
    j = imagegen.Job("x", "", 1024, 1024, 1, 20, 6, checkpoint="novaAnime.safetensors")
    j.workflow_meta = meta
    with pytest.raises(Sent):
        b.generate(j, wf)
    assert "{{" not in str(sent["wf"])
