import http.server, io, threading, urllib.error, urllib.request
import pytest
from promptmaker import civitai_browser as cb
from promptmaker.keystore import KeyStore

KEY = "abc123SECRET"


def test_with_token_added_only_for_civitai():
    u = cb.with_token("https://civitai.com/api/download/models/1?fileId=2", KEY)
    assert "fileId=2" in u and f"token={KEY}" in u
    assert cb.with_token("https://example.com/x", KEY) == "https://example.com/x"
    assert cb.with_token("https://civitai.com/x", "") == "https://civitai.com/x"
    assert cb.strip_token(u) == "https://civitai.com/api/download/models/1?fileId=2"


def test_download_url_host():
    assert cb.download_url("https://civitai.com/api/download/models/1?fileId=2", "civitai.red") == \
        "https://civitai.red/api/download/models/1?fileId=2"
    assert cb.download_url("https://other.net/a", "civitai.red") == "https://other.net/a"


def _server():
    seen = []

    class S(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append((self.headers.get("Host"), self.path, self.headers.get("Authorization")))
            if self.path.startswith("/api/"):
                self.send_response(307)
                self.send_header("Location", f"http://localhost:{self.server.server_port}/blob?sig=1&token=leak")
                self.end_headers(); return
            b = b"data"
            self.send_response(200); self.send_header("Content-Length", "4"); self.end_headers(); self.wfile.write(b)
    srv = http.server.HTTPServer(("127.0.0.1", 0), S)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_token_and_auth_stripped_on_cross_host_redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "_is_civitai", lambda u: "127.0.0.1" in u)
    srv, seen = _server()
    dest = str(tmp_path / "m.safetensors")
    cb.download(f"http://127.0.0.1:{srv.server_port}/api/download/models/1?fileId=2", dest, api_key=KEY)
    srv.shutdown()
    assert open(dest, "rb").read() == b"data"
    first, second = seen
    assert f"token={KEY}" in first[1] and first[2] == f"Bearer {KEY}"
    assert KEY not in second[1] and "token" not in second[1] and second[2] is None


def _http_error(url, code, body=b'{"message":"nope"}'):
    return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(body))


def test_fallback_to_civitai_com_and_messages(tmp_path):
    calls = []

    def opener(req, timeout):
        calls.append(req.full_url)
        if "civitai.red" in req.full_url:
            raise _http_error(req.full_url, 403)
        raise _http_error(req.full_url, 401)
    with pytest.raises(cb.AuthError) as ei:
        cb.download("https://civitai.red/api/download/models/1?fileId=2", str(tmp_path / "f"), api_key=KEY, opener=opener)
    assert "civitai.red" in calls[0] and "civitai.com" in calls[1]
    msg = str(ei.value)
    assert "401" in msg and "a key was sent" in msg and KEY not in msg and "nope" in msg

    def op403(req, timeout):
        raise _http_error(req.full_url, 403)
    with pytest.raises(cb.AuthError) as ei:
        cb.download("https://civitai.com/api/download/models/1", str(tmp_path / "g"), api_key=KEY, opener=op403)
    assert "403" in str(ei.value) and KEY not in str(ei.value)
    with pytest.raises(cb.AuthError) as ei:
        cb.download("https://civitai.com/api/download/models/1", str(tmp_path / "h"), api_key="", opener=op403)
    assert "no API key was sent" in str(ei.value)


def test_key_read_from_same_store_as_settings(tmp_path):
    ks = KeyStore(str(tmp_path), use_keyring=False)
    ks.set("api_key:civitai", KEY)  # what Settings → Civitai saves (app.py)
    import inspect
    from promptmaker import civitaibrowserui
    src = inspect.getsource(civitaibrowserui.CivitaiBrowserPage.cvb_download)
    assert 'self.keys.get("api_key:civitai")' in src
    assert KeyStore(str(tmp_path), use_keyring=False).get("api_key:civitai") == KEY
