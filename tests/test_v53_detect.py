"""5.3 backend auto-detect: identification, candidates, choice rules, and the window switching (all local mocks)."""
import http.server
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import backenddetect as bd  # noqa: E402
import test_v5  # noqa: E402

win, _wait = test_v5.win, test_v5._wait


def _server(kind):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = None
            if kind == "comfyui" and self.path == "/system_stats":
                body = {"system": {"os": "nt"}, "devices": []}
            if kind == "a1111" and self.path == "/sdapi/v1/options":
                body = {"sd_model_checkpoint": "x.safetensors"}
            if body is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


@pytest.fixture
def servers(monkeypatch):
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost"); monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    made = []
    yield lambda k: (made.append(_server(k)) or made[-1])
    for s, _u in made:
        s.shutdown()


def test_identify(servers):
    _s, cu = servers("comfyui"); _s2, fu = servers("a1111"); _s3, nu = servers("none")
    assert bd.identify(cu) == "comfyui" and bd.identify(fu) == "a1111" and bd.identify(nu) == ""
    assert bd.identify("http://127.0.0.1:9", 0.3) == ""


def test_probe_is_parallel_and_quick(servers):
    _s, cu = servers("comfyui")
    dead = [("a1111", f"http://10.255.255.1:{p}") for p in range(7860, 7866)]  # unroutable: each one times out
    t = time.time()
    found = bd.probe(dead + [("comfyui", cu)], timeout=0.5)
    assert found == {cu: "comfyui"} and time.time() - t < 2.5


def test_candidates_configured_first_no_dupes():
    st = {"img_url:a1111": "http://127.0.0.1:7860/", "img_url:comfyui": "http://192.168.1.5:8188"}
    c = bd.candidates(lambda k, d=None: st.get(k, d))
    assert c[0] == ("a1111", "http://127.0.0.1:7860") and ("comfyui", "http://192.168.1.5:8188") in c
    assert len({u for _k, u in c}) == len(c) and ("comfyui", "http://127.0.0.1:8000") in c


@pytest.mark.parametrize("kind,url,found,want", [
    ("a1111", "http://127.0.0.1:7860", {"http://127.0.0.1:7860": "a1111", "http://127.0.0.1:8188": "comfyui"}, None),
    ("a1111", "http://127.0.0.1:7860", {"http://127.0.0.1:8188": "comfyui"}, ("comfyui", "http://127.0.0.1:8188")),
    ("comfyui", "http://127.0.0.1:8188", {"http://127.0.0.1:7860": "a1111"}, ("a1111", "http://127.0.0.1:7860")),
    ("none", "", {"http://127.0.0.1:7860": "a1111", "http://127.0.0.1:8188": "comfyui"}, ("a1111", "http://127.0.0.1:7860")),
    ("comfyui", "http://127.0.0.1:8188", {"http://127.0.0.1:8000": "comfyui"}, ("comfyui", "http://127.0.0.1:8000")),
    ("a1111", "http://127.0.0.1:7860", {}, None),
])
def test_choose(kind, url, found, want):
    assert bd.choose(kind, url, found) == want


def test_window_switches_and_reuses_profile(win, servers, monkeypatch):
    # 6.1: only the mock servers count - a real Forge / ComfyUI on 7860 / 8188 must not change the result
    monkeypatch.setattr(bd, "DEFAULT_PORTS", {k: () for k in bd.KINDS})
    _s, cu = servers("comfyui")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", "http://127.0.0.1:9")
    win.store.set("img_url:comfyui", cu); win.store.set("backend_profile:comfyui", "moss")
    assert win.store.get("auto_detect_backend", True) and win.auto_detect.isChecked()
    win.detect_backend(manual=True)
    assert _wait(lambda: win.store.get("img_backend") == "comfyui", 10)
    assert win.profile["id"] == "moss" and win.img_kind.currentData() == "comfyui"
    assert "ComfyUI" in win.detect_lbl.text()
    # current one running -> kept, nothing switched
    win.detect_backend(manual=True)
    assert _wait(lambda: not win._detect_worker.isRunning(), 10)
    _wait(lambda: False, 0.3)
    assert win.store.get("img_backend") == "comfyui"


def test_auto_detect_setting_off(win):
    win.auto_detect.setChecked(False)
    assert win.store.get("auto_detect_backend") is False
