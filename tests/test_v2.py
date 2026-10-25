"""Tests for v2 logic: providers, image backends, gallery, community, updates, paths, A/B, i18n.

All network services are mocked with a local HTTP server.
"""
import base64
import hashlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promptmaker import abtest, community, gallery, i18n, imagegen, paths, providers, updates  # noqa: E402
from promptmaker.keystore import KeyStore  # noqa: E402
from promptmaker.library import Library  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
LOG = []
MLLAMA = ("llama-server process has terminated: exit status 1: error loading model: "
          "unknown model architecture: 'mllama'")


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, ctype="application/json", code=200):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body)

    def _sse(self, events):
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for e in events:
            self.wfile.write(b"data: " + (e if isinstance(e, bytes) else json.dumps(e).encode()) + b"\n\n")

    def do_GET(self):
        p = self.path
        LOG.append(("GET", p, dict(self.headers)))
        if p == "/api/tags":
            return self._send({"models": [{"name": "llama3.2"}, {"name": "llava:7b"}, {"name": "gemma3:4b"}]})
        if p == "/v1/models":
            return self._send({"data": [{"id": "qwen2.5-vl-7b"}, {"id": "mistral-7b"}]})
        if p == "/anthropic/models":
            return self._send({"data": [{"id": "claude-x"}]})
        if p == "/gemini/models":
            return self._send({"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                                          {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]})
        if p == "/system_stats":
            return self._send({"system": {"comfyui_version": "0.9"}, "devices": [{"name": "RTX"}]})
        if p.startswith("/history/"):
            pid = p.split("/")[-1]
            return self._send({pid: {"status": {"status_str": "success", "completed": True},
                                     "outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}}})
        if p.startswith("/view"):
            return self._send(PNG, "image/png")
        if p == "/queue":
            return self._send({"queue_running": [], "queue_pending": []})
        if p == "/sdapi/v1/sd-models":
            return self._send([{"title": "sdxl.safetensors"}])
        if p == "/sdapi/v1/options":
            return self._send({"sd_model_checkpoint": "sdxl.safetensors"})
        if p.startswith("/sdapi/v1/progress"):
            return self._send({"progress": 0.5, "state": {"sampling_step": 5, "sampling_steps": 10}})
        if p == "/api/version":
            return self._send({"version": self.server.__dict__.get("ollama_version", "0.30.1")})
        if p == "/releases/latest":
            return self._send({"tag_name": "v9.0.0", "html_url": "https://example/rel", "draft": False, "prerelease": False})
        if p == "/community/index.json":
            return self._send(self.server.index)
        if p.startswith("/community/"):
            return self._send(self.server.files[p])
        self._send({"error": "nope"}, code=404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        LOG.append(("POST", self.path, body, dict(self.headers)))
        p = self.path
        if p == "/api/chat" and body.get("model") == "llama3.2-vision":
            return self._send({"error": MLLAMA}, code=500)
        if p == "/api/chat":
            self.send_response(200); self.end_headers()
            for w in ["Hel", "lo"]:
                self.wfile.write((json.dumps({"message": {"content": w}, "done": False}) + "\n").encode())
            return self.wfile.write(b'{"done": true}\n')
        if p == "/api/show":
            if "llama3.2-vision" in body["model"]:
                return self._send({"capabilities": ["completion", "vision"], "model_info": {"general.architecture": "mllama"}})
            return self._send({"capabilities": ["completion", "vision"] if "llava" in body["model"] else ["completion"]})
        if p == "/v1/chat/completions":
            return self._sse([{"choices": [{"delta": {"content": "Hi"}}]}, {"choices": [{"delta": {"content": " there"}}]}, b"[DONE]"])
        if p == "/anthropic/messages":
            return self._sse([{"type": "message_start"}, {"type": "content_block_delta", "delta": {"text": "Clau"}},
                              {"type": "content_block_delta", "delta": {"text": "de"}}, {"type": "message_stop"}])
        if p.startswith("/gemini/models/gemini-x:streamGenerateContent"):
            return self._sse([{"candidates": [{"content": {"parts": [{"text": "Gem"}]}}]},
                              {"candidates": [{"content": {"parts": [{"text": "ini"}]}}]}])
        if p == "/prompt":
            return self._send({"prompt_id": "abc", "node_errors": {}})
        if p == "/sdapi/v1/txt2img":
            return self._send({"images": [base64.b64encode(PNG).decode()], "info": json.dumps({"seed": 777})})
        if p in ("/interrupt", "/queue", "/sdapi/v1/interrupt"):
            return self._send({})
        self._send({"error": "nope"}, code=404)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_ollama_provider(server):
    _, url = server
    p = providers.make("ollama", url)
    assert p.list_models()[0] == "llama3.2"
    assert "".join(p.stream_chat("llama3.2", [{"role": "user", "content": "x", "images": ["b64"]}])) == "Hello"
    assert LOG[-1][2]["messages"][0]["images"] == ["b64"]
    assert p.vision_models() == ["llava:7b"]


def test_openai_compat_provider(server):
    _, url = server
    p = providers.make("lmstudio", url + "/v1", "sk-test")
    assert p.list_models() == ["mistral-7b", "qwen2.5-vl-7b"]
    assert p.vision_models() == ["qwen2.5-vl-7b"]
    out = "".join(p.stream_chat("m", [{"role": "user", "content": "describe", "images": ["QUJD"]}], json_mode=True))
    assert out == "Hi there"
    post = LOG[-1]
    assert post[2]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,QUJD")
    assert post[2]["response_format"] == {"type": "json_object"}
    assert post[3]["Authorization"] == "Bearer sk-test"


def test_anthropic_provider(server):
    _, url = server
    p = providers.make("anthropic", url + "/anthropic", "key")
    out = "".join(p.stream_chat("claude-x", [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]))
    assert out == "Claude"
    body, headers = LOG[-1][2], LOG[-1][3]
    assert body["system"] == "sys" and body["messages"][0]["role"] == "user" and headers["X-Api-Key"] == "key"
    assert p.list_models() == ["claude-x"]


def test_gemini_provider(server):
    _, url = server
    p = providers.make("gemini", url + "/gemini", "gk")
    assert p.list_models() == ["gemini-x"]
    out = "".join(p.stream_chat("gemini-x", [{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"},
                                             {"role": "user", "content": "u"}]))
    assert out == "Gemini"
    body = LOG[-1][2]
    assert body["systemInstruction"]["parts"][0]["text"] == "s" and body["contents"][0]["role"] == "model"


def test_provider_offline_error():
    with pytest.raises(providers.ProviderError):
        providers.make("lmstudio", "http://127.0.0.1:9/v1").list_models()


def test_inject_workflow():
    wf, meta = imagegen.load_workflow(imagegen.list_workflows()["sdxl_txt2img"])
    job = imagegen.Job("a cat", "blurry", 832, 1216, 42, 20, 5.5, checkpoint="x.safetensors")
    out = imagegen.inject(wf, job.values())
    assert out["3"]["inputs"]["seed"] == 42 and out["3"]["inputs"]["cfg"] == 5.5 and out["5"]["inputs"]["width"] == 832
    assert out["6"]["inputs"]["text"] == "a cat" and out["4"]["inputs"]["ckpt_name"] == "x.safetensors"
    assert "{{" not in json.dumps(out)
    assert "flux_txt2img" in imagegen.list_workflows()


def test_comfyui_backend(server):
    _, url = server
    b = imagegen.ComfyUI(url)
    assert "ComfyUI 0.9" in b.test()
    wf, _ = imagegen.load_workflow(imagegen.list_workflows()["sdxl_txt2img"])
    imgs = b.generate(imagegen.Job("dog", seed=5), wf, poll=0.01)
    assert imgs == [PNG]
    sent = [e for e in LOG if e[0] == "POST" and e[1] == "/prompt"][-1][2]
    assert sent["prompt"]["3"]["inputs"]["seed"] == 5


def test_a1111_backend(server):
    _, url = server
    b = imagegen.A1111(url)
    assert "1 checkpoint" in b.test()
    job = imagegen.Job("dog", "bad", 512, 768, 1, 10, 7, checkpoint="sdxl.safetensors")
    seen = []
    imgs = b.generate(job, progress=lambda pct, msg: seen.append(pct), poll=0.01)
    assert imgs == [PNG] and job.seed == 777
    body = [e for e in LOG if e[0] == "POST" and e[1] == "/sdapi/v1/txt2img"][-1][2]
    assert body["negative_prompt"] == "bad" and body["override_settings"]["sd_model_checkpoint"] == "sdxl.safetensors"


def test_cancel():
    class Slow(imagegen.A1111):
        def generate(self, job, workflow=None, progress=None, cancelled=None, **kw):
            if cancelled():
                raise imagegen.Cancelled("Cancelled")
    with pytest.raises(imagegen.Cancelled):
        Slow("http://x").generate(imagegen.Job("x"), cancelled=lambda: True)


def test_gallery_roundtrip():
    g = gallery.Gallery(tempfile.mkdtemp())
    p = g.save(PNG, {"prompt": "a cat", "seed": 3, "profile": "SDXL"})
    items = g.items()
    assert items[0][0] == p and items[0][1]["prompt"] == "a cat" and items[0][1]["seed"] == 3
    g.delete(p)
    assert g.items() == []


def test_community_install_verify(server):
    srv, url = server
    pack = json.dumps({"name": "Test", "categories": {"Mood": {"G": ["zz-mood"]}}}).encode()
    prof = json.dumps({"profiles": [{"id": "zz", "name": "ZZ model"}]}).encode()
    srv.files = {"/community/p.json": pack, "/community/prof.json": prof}
    srv.index = {"packs": [{"id": "t", "name": "Test", "version": "1", "url": "p.json", "sha256": hashlib.sha256(pack).hexdigest()},
                           {"id": "bad", "name": "Bad", "version": "1", "url": "p.json", "sha256": "0" * 64}],
                 "profiles": [{"id": "zz", "name": "ZZ", "version": "2", "url": "prof.json", "sha256": hashlib.sha256(prof).hexdigest()}]}
    items = community.load_index(url + "/community/index.json")
    assert [i["id"] for i in items] == ["t", "bad", "zz"] and items[0]["url"].endswith("/community/p.json")
    d = tempfile.mkdtemp()
    lib = Library(os.path.join(ROOT, "packs"), user_dir=os.path.join(d, "packs"))
    prof_path = os.path.join(d, "profiles.json"); json.dump({"profiles": []}, open(prof_path, "w"))
    inst = community.install(items[0], lib, prof_path, {})
    assert "zz-mood" in lib.items("Mood") and community.status(items[0], inst) == "installed"
    assert os.path.exists(os.path.join(d, "packs", "community_t.json"))
    with pytest.raises(community.CommunityError):
        community.install(items[1], lib, prof_path, inst)
    inst = community.install(items[2], lib, prof_path, inst)
    assert json.load(open(prof_path))["profiles"][0]["id"] == "zz"
    assert community.status(dict(items[2], version="3"), inst) == "update"
    inst = community.uninstall("t", lib, prof_path, inst)
    inst = community.uninstall("zz", lib, prof_path, inst)
    assert "zz-mood" not in lib.items("Mood") and json.load(open(prof_path))["profiles"] == [] and inst == {}


def test_repo_community_index_hashes():
    idx = json.load(open(os.path.join(ROOT, "community", "index.json")))
    for e in idx["packs"] + idx["profiles"]:
        rel = e["url"].split("/main/", 1)[-1] if "/main/" in e["url"] else os.path.join("community", e["url"])
        data = open(os.path.join(ROOT, rel), "rb").read()
        assert hashlib.sha256(data).hexdigest() == e["sha256"], e["id"]


def test_updates(server):
    _, url = server
    assert updates.is_newer("v2.0.1", "2.0.0") and not updates.is_newer("v1.0.0", "1.0.0")
    assert updates.check("1.0.0", url=url + "/releases/latest") == ("v9.0.0", "https://example/rel")
    assert updates.check("9.0.0", url=url + "/releases/latest") is None


def test_portable_paths(monkeypatch):
    app = tempfile.mkdtemp(); home = tempfile.mkdtemp()
    monkeypatch.setattr(paths, "user_data_root", lambda: home)
    d = paths.data_dir(app)
    assert d == os.path.join(app, "data") and paths.is_portable(app)
    open(os.path.join(d, "x.txt"), "w").write("hi")
    new = paths.set_portable(app, False)
    assert new == home and os.path.exists(os.path.join(home, "x.txt")) and not paths.is_portable(app)
    assert paths.set_portable(app, True) == os.path.join(app, "data")


def test_keystore_file_fallback():
    d = tempfile.mkdtemp()
    ks = KeyStore(d, use_keyring=False)
    assert ks.set("api_key:openai", "sk-1") == "file" and ks.get("api_key:openai") == "sk-1"
    assert "_warning" in json.load(open(os.path.join(d, "secrets.json")))
    ks.delete("api_key:openai"); assert ks.get("api_key:openai") == ""


def test_abtest_diff():
    a, b = abtest.diff_html("a red fox in snow", "a blue fox in snow")
    assert "red" in a and "blue" in b and "span" in a and "span" in b
    assert abtest.verdict(80, 70) == "A" and abtest.verdict(70, 71) == "tie"
    assert 0 < abtest.similarity("a b c", "a b d") < 100


def test_i18n():
    langs = i18n.available()
    assert {"en", "es", "de"} <= set(langs) and "machine-translated" in langs["es"]
    i18n.set_language("es")
    assert i18n.tr("Settings") != "Settings"
    assert i18n.tr("unknown string xyz") == "unknown string xyz"
    i18n.set_language("en")
    assert i18n.tr("Settings") == "Settings"


def _dispose(w, app):
    """Finish background threads and delete the window so Qt doesn't crash at interpreter exit (Windows)."""
    app.processEvents()
    w.close()  # MainWindow.closeEvent waits for its worker threads
    w.deleteLater(); app.processEvents()


# ---------------------------------------------------------------- model load failures
def test_model_load_error_detection(server):
    _, url = server
    p = providers.make("ollama", url)
    with pytest.raises(providers.ProviderError) as ei:
        list(p.stream_chat("llama3.2-vision", [{"role": "user", "content": "x"}]))
    err = str(ei.value)
    assert "HTTP 500" in err and providers.is_model_load_error(err)
    assert providers.load_error_detail(err) == "unknown model architecture: 'mllama'"
    for m in ("llama runner process has terminated: signal: killed", "error loading model: x", "failed to load model"):
        assert providers.is_model_load_error(m)
    for m in ("Can't reach http://localhost:11434", "HTTP 404: model 'x' not found, try pulling it first", "timed out"):
        assert not providers.is_model_load_error(m)
    msg = providers.friendly_load_error("llama3.2-vision", err, vision=True)
    assert "can't run on this Ollama version" in msg and "mllama" in msg and "ollama/ollama#16547" in msg
    assert "update Ollama" in providers.friendly_load_error("foo", "error loading model: x")


def test_vision_preference_and_alternative():
    ms = ["llama3.2-vision:latest", "llava:7b", "gemma3:4b", "qwen2.5vl:7b", "mystery-vl"]
    assert providers.sort_models(ms)[0] == "qwen2.5vl:7b"
    assert providers.sort_models(ms)[:3] == ["qwen2.5vl:7b", "gemma3:4b", "llava:7b"]
    failed = {"qwen2.5vl:7b": "x"}
    assert providers.sort_models(ms, failed=failed)[-1] == "qwen2.5vl:7b"
    assert providers.pick_alternative(ms, "llama3.2-vision:latest") == "qwen2.5vl:7b"
    assert providers.pick_alternative(ms, "llama3.2-vision:latest", failed=failed) == "gemma3:4b"
    assert providers.pick_alternative(["only"], "only") is None
    assert providers.pick_alternative(["llama3.2", "mistral"], "mistral", providers.CHAT_PREFERENCE) == "llama3.2"


def test_ollama_vision_models_sorted(server):
    _, url = server
    p = providers.make("ollama", url)
    # /api/show in the mock marks only llava as vision; gemma3 falls back to name hints only if no caps
    assert p.vision_models()[0] == "llava:7b"


def test_ui_friendly_model_error(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    from promptmaker.storage import Store
    app = QApplication.instance() or QApplication([])
    w = MainWindow(Store(str(tmp_path / "t.db")), str(tmp_path))
    w.vision_model.clear(); w.vision_model.addItems(["llama3.2-vision:latest", "gemma3:4b", "qwen2.5vl:7b"])
    w._ai_error("HTTP 500 from http://x/api/chat: {\"error\":\"" + MLLAMA + "\"}", "llama3.2-vision:latest", vision=True)
    assert "llama3.2-vision:latest" in w._failed_models()
    box = w._last_error_box
    labels = [b.text() for b in box.buttons()]
    assert any("qwen2.5vl:7b" in t for t in labels) and any("ollama pull qwen2.5vl" in t for t in labels)
    from PySide6.QtCore import Qt
    assert "Failed to load" in (w.vision_model.itemData(0, Qt.ToolTipRole) or "")
    switch = next(b for b in box.buttons() if "qwen2.5vl:7b" in b.text())
    switch.click(); app.processEvents()
    assert w.vision_model.currentText() == "qwen2.5vl:7b"
    copy_btn = next(b for b in box.buttons() if "ollama pull" in b.text())
    copy_btn.click(); app.processEvents()
    assert QApplication.clipboard().text() == "ollama pull qwen2.5vl"
    w._mark_model_ok("llama3.2-vision:latest")
    assert "llama3.2-vision:latest" not in w._failed_models()
    w._ai_error("Can't reach the server", "x")  # ordinary errors: toast only, no dialog change
    assert w._last_error_box is box
    box.close(); _dispose(w, app)


def test_toast_never_blocks_and_inplace_confirm(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    from promptmaker.storage import Store
    app = QApplication.instance() or QApplication([])
    st = Store(str(tmp_path / "t.db"))
    w = MainWindow(st, str(tmp_path)); w.resize(1280, 800); w.show(); w.go("History")
    st.add_history("a cat", "Generic", "test"); st.add_history("a dog", "Generic", "test"); w.load_history()
    app.processEvents()
    btn = w.hist_clear_btn
    btn.click(); app.processEvents()
    # in-place confirmation, no data lost yet
    assert btn.armed and btn.text().startswith("Confirm clear (4s)") and btn.objectName() == "dangerArmed"
    assert len(st.history()) == 2
    # any toast shown must not cover the button and must let clicks through
    w.notify("hello", error=True); app.processEvents()
    assert w.toast.testAttribute(Qt.WA_TransparentForMouseEvents)
    cw = w.centralWidget()
    b_rect = btn.rect().translated(btn.mapTo(cw, QPoint(0, 0)))
    t_rect = w.toast.geometry() if w.toast.parentWidget() is cw else w.toast.rect().translated(w.toast.mapTo(cw, QPoint(0, 0)))
    assert not t_rect.intersects(b_rect)
    btn._tick(); assert btn.text().startswith("Confirm clear (3s)")
    btn.click(); app.processEvents()
    assert not btn.armed and btn.text() == "Clear all" and btn.objectName() == "ghost"
    assert w.hist_list.count() == 0 and len(st.history()) == 0
    # reverts on its own when not confirmed
    btn.click(); [btn._tick() for _ in range(4)]
    assert not btn.armed and btn.text() == "Clear all"
    _dispose(w, app)


def test_ollama_version_marks_mllama_unsupported(server):
    srv, url = server
    assert providers.unsupported_reason("llama3.2-vision:latest", "0.30.0") == providers.MLLAMA_NOTE
    assert providers.unsupported_reason("x", "0.31.2", arch="mllama") == providers.MLLAMA_NOTE
    assert providers.unsupported_reason("llama3.2-vision", "0.12.6") == ""
    assert providers.unsupported_reason("llama3.2-vision", "") == ""
    assert providers.unsupported_reason("qwen2.5vl:7b", "0.30.1") == ""
    assert "ollama/ollama#16547" in providers.MLLAMA_NOTE and "0.30+" in providers.MLLAMA_NOTE
    orig = Mock.do_GET
    def tags_get(self):
        if self.path == "/api/tags":
            return self._send({"models": [{"name": "llama3.2-vision:latest"}, {"name": "llava:7b"}]})
        return orig(self)
    Mock.do_GET = tags_get
    try:
        p = providers.make("ollama", url)
        assert p.version() == "0.30.1"
        vm = p.vision_models()
        assert vm == ["llava:7b", "llama3.2-vision:latest"]
        assert p.notes == {"llama3.2-vision:latest": providers.MLLAMA_NOTE}
        srv.ollama_version = "0.12.0"
        p.vision_models(); assert p.notes == {}
    finally:
        Mock.do_GET = orig; srv.__dict__.pop("ollama_version", None)
