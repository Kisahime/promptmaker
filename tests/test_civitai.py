"""Civitai import – all HTTP is served by a local mock (no real Civitai calls)."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promptmaker import civitai, imagegen, profiles  # noqa: E402

POS = ("newest,very awa,masterpiece,high quality,high resolution,amazing quality,best quality, good lighting,"
       "detailed eyes,anime coloring,anime screencap")
NEG = ("worst quality,bad quality,low quality,lowres,scan artifacts,jpeg artifacts,sketch,bad quality,jpeg,artifacts,"
       "signature,username,text,logo,bad anatomy,artist name,artist logo,extra limbs,extra digit,extra legs,extra arms,"
       "blurry background,simple background ")
# shape copied from the real /api/v1/models/2087823 response (Oct 2026)
DESC = ('<p><span style="color:rgb(255, 167, 39)"><strong>Steps:</strong> </span>15-30+ </p>'
        '<p><span style="color:rgb(255, 167, 39)"><strong>CFG scale:</strong> </span>3-7 </p>'
        '<p><span style="color:rgb(255, 167, 39)"><strong>Sampler: </strong></span>euler a or&nbsp;DPM++ 2M Karras</p>'
        '<p><strong><u>Vae Included</u></strong></p><p><strong>positive prompts:</strong></p>'
        f'<pre><code>{POS}</code></pre><p><strong>negative prompts:</strong></p><pre><code>{NEG}</code></pre><p></p>')
MODEL = {"id": 2087823, "name": "Screen-chanTV Merge Illustrious|Anima", "type": "Checkpoint", "nsfw": False,
         "description": DESC, "modelVersions": [
             {"id": 3338156, "name": "v2.0", "baseModel": "Anima", "trainedWords": [], "description": None},
             {"id": 3061342, "name": "v1.0", "baseModel": "Anima", "trainedWords": ["anime coloring", "anime screencap"]}]}
VERSION = {"id": 3338156, "modelId": 2087823, "name": "v2.0", "baseModel": "Anima", "trainedWords": [], "description": None,
           "model": {"name": MODEL["name"], "type": "Checkpoint", "nsfw": False}}
LORA_V = {"id": 77, "modelId": 70, "name": "v1", "baseModel": "Illustrious", "trainedWords": ["chibi style", "sd_chibi"],
          "description": "<p>Clip skip: 2</p><p>Resolution: 832x1216</p>"}
LORA_M = {"id": 70, "name": "Chibi LoRA", "type": "LORA", "description": "<p>Use with Illustrious.</p>", "modelVersions": [LORA_V]}
IMAGES = {"items": [
    {"id": i, "meta": {"prompt": f"masterpiece, best quality, (very aesthetic:1.2), chibi style, subject {i}",
                       "negativePrompt": "lowres, worst quality, bad hands" + (", text" if i % 2 else ""),
                       "sampler": "Euler a", "cfgScale": 5 + (i % 2), "steps": 28, "Size": "832x1216", "clipSkip": 2}}
    for i in range(5)] + [{"id": 99, "meta": None}]}
HITS = []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, headers=None):
        b = json.dumps(obj).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        HITS.append((self.path, self.headers.get("Authorization")))
        p = self.path.split("?")[0]
        if p == "/api/v1/model-versions/3338156":
            return self._send(VERSION)
        if p == "/api/v1/models/2087823":
            return self._send(MODEL)
        if p == "/api/v1/model-versions/77":
            return self._send(LORA_V)
        if p == "/api/v1/models/70":
            return self._send(LORA_M)
        if p == "/api/v1/images":
            if "modelVersionId=77" in self.path:
                return self._send(IMAGES)
            return self._send({"items": [{"id": 1, "meta": None}]})
        if p == "/api/v1/models/429":
            if sum(1 for h in HITS if h[0].startswith("/api/v1/models/429")) < 2:
                return self._send({"error": "slow down"}, 429, {"Retry-After": "0"})
            return self._send({"id": 429, "name": "Busy", "type": "Checkpoint", "modelVersions": [
                {"id": 4290, "name": "v1", "baseModel": "SDXL 1.0"}]})
        if p == "/api/v1/model-versions/4290":
            return self._send({"id": 4290, "modelId": 429, "name": "v1", "baseModel": "SDXL 1.0"})
        if p == "/api/v1/models/401":
            return self._send({"error": "Unauthorized"}, 401)
        self._send({"error": "Not found"}, 404)


@pytest.fixture(scope="module")
def api():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/v1"
    srv.shutdown()


def client(api, tmp_path, key=""):
    return civitai.Client(key, str(tmp_path / "cache"), base=api, min_interval=0)


def test_parse_ref():
    u = "https://civitai.red/models/2087823/screen-chantv-merge-illustriousoranima?modelVersionId=3338156"
    assert civitai.parse_ref(u) == (2087823, 3338156)
    assert civitai.parse_ref("civitai.com/models/2087823") == (2087823, None)
    assert civitai.parse_ref("https://civitai.green/models/5?modelVersionId=6") == (5, 6)
    assert civitai.parse_ref("https://civitai.com/api/download/models/3338156") == (None, 3338156)
    assert civitai.parse_ref("2087823") == (2087823, None)
    assert civitai.parse_ref("v3338156") == (None, 3338156)
    assert civitai.parse_ref("urn:air:anima:checkpoint:civitai:2087823@3338156") == (2087823, 3338156)
    for bad in ("", "https://example.com/models/1", "https://civitai.com/user/foo"):
        with pytest.raises(civitai.CivitaiError):
            civitai.parse_ref(bad)


def test_parse_description_matches_creator_prompts():
    d = civitai.parse_description(DESC)
    assert d["positive"] == ", ".join(civitai.clean_tags(POS))
    assert d["positive"].startswith("newest, very awa, masterpiece") and d["positive"].endswith("anime screencap")
    assert d["negative"].startswith("worst quality, bad quality, low quality") and d["negative"].endswith("simple background")
    assert d["negative"].count("bad quality") == 1  # duplicates removed
    assert d["steps_text"] == "15-30+" and d["steps"] == 22 and d["cfg"] == 5.0 and d["cfg_text"] == "3-7"
    assert d["sampler"] == "euler a or DPM++ 2M Karras"
    inline = civitai.parse_description("<p>Positive: masterpiece, best quality</p><p>Negative prompt: lowres</p>"
                                       "<p>Clip skip: 2</p><p>Resolution: 896 x 1152</p>")
    assert inline == {"positive": "masterpiece, best quality", "negative": "lowres", "clip_skip": 2, "resolution": "896x1152"}


def test_fetch_suggest_and_cache(api, tmp_path):
    HITS.clear()
    c = client(api, tmp_path, key="secret")
    info = civitai.fetch("https://civitai.red/models/2087823/x?modelVersionId=3338156", c)
    s = civitai.suggest(info)
    assert s["positive_source"] == "description" and "anime screencap" in s["positive"]
    assert s["base_model"] == "Anima" and civitai.base_profile_id(s["base_model"]) == "anima"
    assert s["mined"]["images_with_meta"] == 0
    assert all(h[1] == "Bearer secret" for h in HITS)
    n = len(HITS)
    civitai.fetch("https://civitai.com/models/2087823?modelVersionId=3338156", c)  # civitai.com / .red share IDs
    assert len(HITS) == n  # served from cache
    civitai.fetch((2087823, 3338156), c, force=True)
    assert len(HITS) > n


def test_mining_and_lora_trained_words(api, tmp_path):
    info = civitai.fetch("v77", client(api, tmp_path))
    s = civitai.suggest(info)
    assert s["positive_source"] == "sample images"
    assert "masterpiece" in s["positive"] and "very aesthetic" in s["positive"] and "subject 1" not in s["positive"]
    assert s["negative"].startswith("lowres") or "lowres" in s["negative"]
    assert s["sampler"] == "Euler a" and s["steps"] == 28 and s["cfg"] == 5.0
    assert s["clip_skip"] == 2 and s["resolution"] == "832x1216"
    assert s["trained_words"] == ["chibi style", "sd_chibi"] and s["type"] == "LORA"


def test_rate_limit_and_errors(api, tmp_path):
    c = client(api, tmp_path)
    assert c.get("/models/429")["name"] == "Busy"  # retried after HTTP 429
    with pytest.raises(civitai.CivitaiError, match="API key"):
        c.get("/models/401")
    with pytest.raises(civitai.CivitaiError, match="not found"):
        c.get("/models/404404")


def test_build_profile_inherits_and_is_used(api, tmp_path):
    info = civitai.fetch("https://civitai.com/models/2087823?modelVersionId=3338156", client(api, tmp_path))
    s = civitai.suggest(info)
    bundled = profiles.load()
    prof = civitai.build_profile(info, s, "anima", bundled)
    assert prof["id"] == "civitai_3338156" and prof["inherits"] == "anima"
    assert prof["gen"] == {"steps": 22, "cfg": 5.0, "sampler": "euler_ancestral", "scheduler": "normal", "a1111_sampler": "Euler a"}
    assert prof["civitai"]["version_id"] == 3338156 and prof["sources"][0].startswith("https://civitai.com/models/2087823")
    path = str(tmp_path / "profiles.json")
    profiles.ensure_user_file(path)
    profiles.save_profile(path, prof)
    loaded = profiles.load(path)[prof["id"]]
    # inherited from Anima, overridden by Civitai
    assert loaded["format"] == bundled["anima"]["format"] and loaded["resolutions"] == bundled["anima"]["resolutions"]
    assert loaded["quality_prefix"].startswith("newest, very awa") and loaded["negative_default"].startswith("worst quality")
    from promptmaker import builder, ollama, scoring
    out = builder.build({"Subject": ["1girl"]}, loaded) if hasattr(builder, "build") else None
    if out:
        assert out["prompt"].startswith("newest, very awa")
    assert "newest, very awa" in ollama.system_for(loaded)
    fixes = scoring.heuristic_score("1girl, smile", loaded, [])["fixes"]
    assert any("newest, very awa" in f for f in fixes)
    # LoRA trained words are kept and added to the prefix
    linfo = civitai.fetch("v77", client(api, tmp_path))
    lp = civitai.build_profile(linfo, civitai.suggest(linfo), civitai.base_profile_id("Illustrious"), bundled)
    assert lp["civitai"]["trained_words"] == ["chibi style", "sd_chibi"] and "sd_chibi" in lp["quality_prefix"]
    assert lp["gen"]["clip_skip"] == 2


def test_a1111_payload_clip_skip():
    j = imagegen.Job("x"); j.clip_skip = 2
    assert imagegen.A1111("http://x").payload(j)["override_settings"] == {"CLIP_stop_at_last_layers": 2}


def test_ui_import_review_and_refresh(api, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    from promptmaker.storage import Store
    app = QApplication.instance() or QApplication([])
    st = Store(str(tmp_path / "t.db")); st.set("civitai_api", api)
    w = MainWindow(st, str(tmp_path))
    dlg = w.civitai_import(ref="https://civitai.red/models/2087823/x?modelVersionId=3338156")
    dlg._worker.wait(10000); app.processEvents()
    assert dlg.base.currentData() == "anima" and dlg.pos.toPlainText().startswith("newest, very awa")
    dlg.neg.setPlainText(dlg.neg.toPlainText() + ", my extra negative")  # user edit on the review screen
    dlg.save(); app.processEvents()
    assert w.profile["id"] == "civitai_3338156" and w.profile["negative_default"].endswith("my extra negative")
    w.go("Builder"); app.processEvents()
    assert w.negative.toPlainText().endswith("my extra negative")
    assert w.build_result()["prompt"].startswith("newest, very awa")
    w.go("Model profiles"); app.processEvents()
    assert w.cv_refresh_btn.isEnabled()
    d2 = w.civitai_refresh(); d2._worker.wait(10000); app.processEvents()
    assert d2.existing["id"] == "civitai_3338156"
    d2.save(); app.processEvents()
    assert sum(1 for p in w.profiles if p.startswith("civitai_")) == 1
    w.close(); w.deleteLater(); app.processEvents()
