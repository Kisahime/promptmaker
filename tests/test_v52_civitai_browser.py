"""5.2 Civitai model browser – all HTTP is mocked (no real Civitai calls, no real images)."""
import hashlib
import io
import os
import threading
import urllib.error
import urllib.parse

import pytest

from promptmaker import civitai, profiles
from promptmaker import civitai_browser as cb

PAYLOAD = os.urandom(300_000)
SHA = hashlib.sha256(PAYLOAD).hexdigest()

MOSS_V = {"id": 3435978, "modelId": 3007871, "name": "V3.3 25STEPS CFG3", "baseModel": "MOSS Image", "trainedWords": [],
          "description": "<p>Steps: 25</p><p>CFG: 3.5</p><p>Sampler: Euler Simple</p>",
          "images": [{"url": "https://image.civitai.com/x/abc/width=832/1.jpeg", "nsfwLevel": 1},
                     {"url": "https://image.civitai.com/x/abc/width=832/2.jpeg", "nsfwLevel": 8}],
          "files": [{"id": 1, "name": "moodyMoss_bf16.safetensors", "sizeKB": 9.5e9 / 1024, "type": "Model",
                     "metadata": {"fp": "bf16", "format": "SafeTensor"}, "hashes": {"SHA256": "AA"},
                     "downloadUrl": "https://civitai.com/api/download/models/3435978?fp=bf16"},
                    {"id": 2, "name": "moodyMoss_fp8.safetensors", "sizeKB": 4.73e9 / 1024, "type": "Model", "primary": True,
                     "metadata": {"fp": "fp8", "format": "SafeTensor"}, "hashes": {"SHA256": SHA.upper()},
                     "downloadUrl": "https://civitai.com/api/download/models/3435978?fp=fp8"}]}
MOSS_M = {"id": 3007871, "name": "Moody Moss Mix", "type": "Checkpoint", "nsfw": False, "creator": {"username": "moody"},
          "description": "<p>Raw portraits.</p><script>alert(1)</script><img src='https://evil/x.png'>"
                         "<a href='javascript:alert(1)' onclick='x()'>bad</a> <a href='https://civitai.com/x'>ok</a>",
          "stats": {"downloadCount": 12345, "thumbsUpCount": 678}, "modelVersions": [MOSS_V]}
NSFW_M = {"id": 9, "name": "Spicy", "type": "LORA", "nsfw": True, "modelVersions": [{"id": 10, "baseModel": "Pony", "images": []}]}


class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, path, params=None, force=False):
        self.calls.append((path, params))
        if path == "/models":
            cur = dict(params).get("cursor")
            return self.pages[cur]
        if path.startswith("/models/"):
            return MOSS_M
        raise civitai.CivitaiError("not found")


# ---------------------------------------------------------------- search params / nsfw
def test_search_params_repeat_filters_and_nsfw_off():
    p = cb.search_params("moss", ["Checkpoint", "LORA"], ["MOSS Image"], "Most Downloaded", "Month", False, 24, "abc")
    assert ("types", "Checkpoint") in p and ("types", "LORA") in p and ("baseModels", "MOSS Image") in p
    assert ("nsfw", "false") in p and ("query", "moss") in p and ("cursor", "abc") in p and ("limit", 24) in p
    assert ("sort", "Most Downloaded") in p and ("period", "Month") in p and not any(k == "page" for k, _ in p)
    q = urllib.parse.parse_qs(urllib.parse.urlencode(p))
    assert q["types"] == ["Checkpoint", "LORA"]
    assert ("nsfw", "true") in cb.search_params(nsfw=True) and not any(k == "query" for k, _ in cb.search_params(""))


def test_search_filters_nsfw_models_and_images_and_paginates():
    c = FakeClient({None: {"items": [MOSS_M, NSFW_M], "metadata": {"nextCursor": "c2"}},
                    "c2": {"items": [], "metadata": {}}})
    items, cur = cb.search(c, query="moss", nsfw=False)
    assert cur == "c2" and [m["id"] for m in items] == [3007871]
    v = items[0]["modelVersions"][0]
    assert [i["nsfwLevel"] for i in v["images"]] == [1] and v["_hidden"] == 1
    assert ("nsfw", "false") in c.calls[0][1]
    items2, cur2 = cb.search(c, query="moss", nsfw=False, cursor="c2")
    assert items2 == [] and cur2 is None
    allm, _ = cb.search(c, nsfw=True)
    assert len(allm) == 2 and len(allm[0]["modelVersions"][0]["images"]) == 2


def test_image_safe_unknown_is_hidden():
    assert cb.image_safe({"nsfwLevel": 1}) and not cb.image_safe({"nsfwLevel": 2})
    assert cb.image_safe({"nsfw": "None"}) and not cb.image_safe({"nsfw": "Soft"}) and not cb.image_safe({})


def test_card_and_thumb_url():
    c = cb.card(cb.filter_models([MOSS_M])[0])
    assert c["creator"] == "moody" and c["base"] == "MOSS Image" and c["downloads"] == 12345 and c["likes"] == 678
    assert "/width=320/" in c["thumb"] and c["thumb"].endswith("1.jpeg")
    assert cb.short_count(12345) == "12.3k" and cb.short_count(2_000_000) == "2M"


def test_sanitize_html_strips_scripts_images_and_bad_links():
    s = cb.sanitize_html(MOSS_M["description"])
    assert "script" not in s and "<img" not in s and "javascript" not in s and "onclick" not in s
    assert '<a href="https://civitai.com/x">ok</a>' in s and "<p>Raw portraits.</p>" in s


# ---------------------------------------------------------------- files / destinations
def test_files_primary_first_and_labels():
    fs = cb.files(MOSS_V)
    assert fs[0]["name"] == "moodyMoss_fp8.safetensors" and fs[0]["sha256"] == SHA
    assert "fp8" in cb.file_label(fs[0]) and "GB" in cb.file_label(fs[0])


def test_destination_mapping(tmp_path):
    forge, comfy = r"C:\AI\sd-webui-forge-classic", str(tmp_path / "ComfyUI")
    os.makedirs(os.path.join(comfy, "models"))
    cm = os.path.join(comfy, "models")
    fs = cb.files(MOSS_V)
    d = cb.destinations("Checkpoint", "MOSS Image", fs[0], forge, comfy, "forge")
    assert d[0][1] == os.path.join(cm, "diffusion_models")
    assert cb.is_unet_only(fs[1], "MOSS Image")  # bf16 9.5 GB is still the DiT alone
    aio = {"name": "mossAnime.safetensors", "size": 15.5e9, "fp": "fp8"}
    assert not cb.is_unet_only(aio, "MOSS Image")
    assert cb.destinations("Checkpoint", "MOSS Image", aio, forge, comfy)[0][1].endswith("Stable-diffusion")
    sdxl = {"name": "x.safetensors", "size": 6.9e9, "fp": "fp16"}
    d = cb.destinations("Checkpoint", "Illustrious", sdxl, forge, comfy, "forge")
    assert d[0][1].replace("\\", "/").endswith("models/Stable-diffusion") and d[1][1] == os.path.join(cm, "checkpoints")
    d = cb.destinations("Checkpoint", "SDXL 1.0", sdxl, forge, comfy, "comfyui")
    assert d[0][1] == os.path.join(cm, "checkpoints")
    assert cb.destinations("LORA", "Pony", sdxl, forge, comfy)[0][1].replace("\\", "/").endswith("models/Lora")
    assert cb.destinations("VAE", "SDXL 1.0", sdxl, "", comfy)[0][1] == os.path.join(cm, "vae")
    assert cb.destinations("Controlnet", "SDXL 1.0", sdxl, forge, "")[0][1].replace("\\", "/").endswith("models/ControlNet")
    assert cb.destinations("Checkpoint", "Anima", {"name": "a.gguf", "size": 2e9}, forge, comfy)[0][1].endswith("diffusion_models")
    assert cb.destinations("Checkpoint", "Flux.1 D", {"name": "f.safetensors", "size": 11.9e9, "fp": "fp8"}, forge, comfy)[0][1].endswith("diffusion_models")
    assert cb.destinations("Other", "", sdxl, forge, comfy, fallback="/dl")[-1][1] == "/dl"
    assert cb.comfy_models_dir(cm) == cm and cb.comfy_models_dir(comfy) == cm


# ---------------------------------------------------------------- download
class Resp(io.BytesIO):
    def __init__(self, data, status=200, total=None, ctype="application/octet-stream"):
        super().__init__(data); self.status = status
        self.headers = {"Content-Length": str(len(data) if total is None else total), "Content-Type": ctype}

    def getcode(self):
        return self.status


def make_opener(seen, fail_after=None, status_code=None):
    def opener(req, timeout):
        seen.append(dict(req.header_items()))
        if status_code:
            raise urllib.error.HTTPError(req.full_url, status_code, "x", {}, None)
        rng = req.get_header("Range")
        start = int(rng.split("=")[1].rstrip("-")) if rng else 0
        data = PAYLOAD[start:]
        if fail_after is not None and not rng:
            return Resp(data[:fail_after], 200, total=len(data))
        return Resp(data, 206 if rng else 200)
    return opener


def test_download_verifies_sha_and_sends_bearer(tmp_path):
    seen, prog = [], []
    dest = str(tmp_path / "m" / "a.safetensors")
    out = cb.download("https://civitai.com/api/download/models/1", dest, "KEY", SHA, progress=lambda d, t: prog.append((d, t)),
                      opener=make_opener(seen), chunk=65536)
    assert out == dest and open(dest, "rb").read() == PAYLOAD and not os.path.exists(dest + ".part")
    assert seen[0]["Authorization"] == "Bearer KEY" and prog[-1] == (len(PAYLOAD), len(PAYLOAD))


def test_download_resumes_with_range(tmp_path):
    dest = str(tmp_path / "a.safetensors")
    with open(dest + ".part", "wb") as f:
        f.write(PAYLOAD[:100_000])
    seen = []
    cb.download("https://civitai.com/api/download/models/1", dest, "", SHA, opener=make_opener(seen), chunk=50_000)
    assert seen[0]["Range"] == "bytes=100000-" and open(dest, "rb").read() == PAYLOAD


def test_download_short_read_retries_with_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(cb.time, "sleep", lambda s: None)
    dest = str(tmp_path / "a.safetensors"); seen = []
    cb.download("https://civitai.com/api/download/models/1", dest, "", SHA, opener=make_opener(seen, fail_after=120_000), chunk=40_000)
    assert "Range" not in seen[0] and seen[1]["Range"] == "bytes=120000-" and open(dest, "rb").read() == PAYLOAD


def test_download_hash_mismatch_deletes(tmp_path):
    dest = str(tmp_path / "a.safetensors")
    with pytest.raises(civitai.CivitaiError, match="SHA256 mismatch"):
        cb.download("https://civitai.com/api/download/models/1", dest, "", "00" * 32, opener=make_opener([]))
    assert not os.path.exists(dest) and not os.path.exists(dest + ".part")


def test_download_401_is_clear(tmp_path):
    with pytest.raises(civitai.CivitaiError, match="API key"):
        cb.download("https://civitai.com/api/download/models/1", str(tmp_path / "a"), "", SHA, opener=make_opener([], status_code=401))


def test_download_html_login_page_is_clear(tmp_path):
    with pytest.raises(civitai.CivitaiError, match="API key"):
        cb.download("https://civitai.com/api/download/models/1", str(tmp_path / "a"), "", SHA, opener=lambda r, t: Resp(b"<html>", ctype="text/html"))


def test_download_cancel_keeps_part(tmp_path):
    ev = threading.Event(); dest = str(tmp_path / "a.safetensors")

    def prog(d, t):
        if d >= 100_000:
            ev.set()
    with pytest.raises(cb.Cancelled):
        cb.download("https://civitai.com/api/download/models/1", dest, "", SHA, progress=prog, cancel=ev, opener=make_opener([]), chunk=50_000)
    assert os.path.getsize(dest + ".part") == 100_000 and not os.path.exists(dest)
    cb.download("https://civitai.com/api/download/models/1", dest, "", SHA, opener=make_opener([]))
    assert open(dest, "rb").read() == PAYLOAD


def test_redirect_strips_auth_on_other_host():
    import urllib.request
    h = cb._StripAuthOnRedirect()
    req = urllib.request.Request("https://civitai.com/api/download/models/1", headers={"Authorization": "Bearer K"})
    new = h.redirect_request(req, None, 302, "Found", {}, "https://b2.example.com/file?sig=1")
    assert "Authorization" not in dict(new.header_items())


# ---------------------------------------------------------------- profile
def test_build_profile_moss():
    raw = profiles.load()
    prof = cb.build_profile(MOSS_M, MOSS_V, cb.files(MOSS_V)[0], raw, "civitai.red")
    assert prof["id"] == "civitai_3435978" and prof["inherits"] == "moss" and prof["family"] == "MOSS"
    g = prof["gen"]
    assert (g["steps"], g["cfg"], g["sampler"], g["scheduler"], g["a1111_sampler"], g["workflow"]) == \
        (25, 3.5, "euler", "simple", "Euler", "moss_txt2img")
    c = prof["civitai"]
    assert c["file_name"] == "moodyMoss_fp8.safetensors" and c["type"] == "Diffusion model" and c["base_model"] == "MOSS Image"
    assert c["url"].startswith("https://civitai.red/models/3007871") and prof["resolutions"]["16:9"]
    assert not any("(n/a)" in t for t in prof["tips"])


def test_map_sampler():
    assert cb.map_sampler("dpmpp_2m_sde_gpu beta", "Anima") == ("dpmpp_2m_sde_gpu", "beta", "DPM++ 2M SDE")
    assert cb.map_sampler("DPM++ 2M Karras") == ("dpmpp_2m", "karras", "DPM++ 2M")
    assert cb.map_sampler("Euler a", "Stable Diffusion") == ("euler_ancestral", "normal", "Euler a")


def test_build_profile_lora_illustrious():
    v = {"id": 77, "modelId": 70, "name": "v1", "baseModel": "Illustrious", "trainedWords": ["chibi"], "files": [
        {"id": 3, "name": "chibi.safetensors", "sizeKB": 200000, "primary": True}]}
    m = {"id": 70, "name": "Chibi", "type": "LORA", "modelVersions": [v]}
    prof = cb.build_profile(m, v, cb.files(v)[0], profiles.load())
    assert prof["inherits"] == "illustrious" and prof["civitai"]["type"] == "LORA" and "workflow" not in prof["gen"]
    assert "chibi" in prof["quality_prefix"]


def test_api_base_hosts():
    assert cb.api_base("civitai.red") == "https://civitai.red/api/v1" and cb.host_of("https://civitai.red/api/v1") == "civitai.red"


# ---------------------------------------------------------------- UI
def test_ui_browser_search_detail_download_profile(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    from PySide6.QtWidgets import QApplication
    from promptmaker import civitaibrowserui as ui
    from promptmaker.app import MainWindow
    from promptmaker.storage import Store
    app = QApplication.instance() or QApplication([])
    fake = FakeClient({None: {"items": [MOSS_M, NSFW_M], "metadata": {"nextCursor": "c2"}},
                       "c2": {"items": [dict(MOSS_M, id=5, name="Other")], "metadata": {}}})
    fetched = []
    monkeypatch.setattr(ui.CivitaiBrowserPage, "cvb_fetch", staticmethod(lambda url: fetched.append(url) or b"notanimage"))
    monkeypatch.setattr(ui.CivitaiBrowserPage, "cvb_client", lambda self: fake)
    monkeypatch.setattr(ui.CivitaiBrowserPage, "cvb_opener", staticmethod(make_opener([])))
    st = Store(str(tmp_path / "t.db")); comfy = tmp_path / "ComfyUI"; (comfy / "models").mkdir(parents=True)
    st.set("comfy_dir", str(comfy)); st.set("forge_dir", "")
    w = MainWindow(st, str(tmp_path))
    w.go("Model browser"); app.processEvents()
    assert not w.cvb_nsfw.isChecked()
    w.cvb_query.setText("moss"); wk = w.cvb_search(); wk.wait(5000); app.processEvents()
    assert w.cvb_grid.count() == 1 and ("nsfw", "false") in fake.calls[-1][1]
    assert "NSFW previews hidden" in w.cvb_status.text()
    w.cvb_more.click(); w._cvb_search_w.wait(5000); app.processEvents()
    assert w.cvb_grid.count() == 2 and not w.cvb_more.isEnabled()
    import time
    t0 = time.time()
    while not fetched and time.time() - t0 < 3:
        app.processEvents(); time.sleep(0.02)
    assert fetched and all("2.jpeg" not in u for u in fetched)  # the nsfwLevel 8 preview is never requested
    w.cvb_grid.setCurrentRow(0); app.processEvents()
    w._cvb_detail_w.wait(5000); app.processEvents()
    assert w.cvb_version.count() == 1 and w.cvb_file.count() == 2 and "Steps 25" in w.cvb_settings.text()
    assert w.cvb_dest_dir() == str(comfy / "models" / "diffusion_models")
    assert "alert" not in w.cvb_desc.toHtml()
    dl = w.cvb_download(); dl.wait(10000); app.processEvents()
    path = comfy / "models" / "diffusion_models" / "moodyMoss_fp8.safetensors"
    assert path.read_bytes() == PAYLOAD and w.cvb_profile_btn.isEnabled()
    prof = w.cvb_create_profile(); app.processEvents()
    assert w.profile["id"] == "civitai_3435978" and prof["gen"]["workflow"] == "moss_txt2img"
    w.cvb_thumbs.stop(); w.cvb_thumbs.wait(3000)
    w.close(); w.deleteLater(); app.processEvents()
