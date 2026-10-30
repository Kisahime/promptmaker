"""4.1.0: ComfyUI websocket previews/progress, Comfy hires fix."""
import base64
import hashlib
import socket
import struct
import threading

from promptmaker import comfyws, imagegen
from promptmaker.imagegen import ComfyUI, Job

import test_v4


def _ws_server(frames):
    """One-shot WebSocket server that answers the handshake then sends `frames` [(opcode, bytes)]."""
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    port = srv.getsockname()[1]
    seen = {}

    def run():
        c, _ = srv.accept()
        req = b""
        while b"\r\n\r\n" not in req:
            req += c.recv(1024)
        seen["path"] = req.split(b" ")[1].decode()
        key = [ln.split(b": ")[1] for ln in req.split(b"\r\n") if ln.lower().startswith(b"sec-websocket-key")][0]
        acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
        c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
        for op, data in frames:
            ln = len(data)
            head = bytes([0x80 | op]) + (bytes([ln]) if ln < 126 else bytes([126]) + struct.pack(">H", ln) if ln < 65536
                                         else bytes([127]) + struct.pack(">Q", ln))
            c.sendall(head + data)
        threading.Event().wait(0.5); c.close(); srv.close()
    threading.Thread(target=run, daemon=True).start()
    return f"http://127.0.0.1:{port}", seen


def _wait(pred, t=3):
    import time
    end = time.time() + t
    while not pred() and time.time() < end:
        time.sleep(0.02)


def test_ws_previews_and_progress():
    jpeg = b"\xff\xd8fakejpeg" * 5000  # > 64 KiB: exercises the 8-byte length
    url, seen = _ws_server([(1, b'{"type":"status","data":{"status":{}}}'),
                            (1, b'{"type":"progress","data":{"value":3,"max":20,"prompt_id":"p1"}}'),
                            (2, struct.pack(">II", 1, 1) + jpeg),
                            (1, b'{"type":"executing","data":{"node":null,"prompt_id":"p1"}}')])
    ws = comfyws.connect(url, "abc 123")
    assert ws is not None
    ws.prompt_id = "p1"
    _wait(lambda: ws.done)
    assert seen["path"] == "/ws?clientId=abc%20123"
    assert ws.progress == (3, 20) and ws.previews == 1 and ws.preview == jpeg and ws.done
    ws.close()


def test_ws_ignores_other_prompts_and_bad_frames():
    ws = comfyws.ComfyWS.__new__(comfyws.ComfyWS)
    ws.preview, ws.previews, ws.progress, ws.prompt_id, ws.done, ws.error = None, 0, None, "mine", False, None
    ws._lock = threading.Lock()
    ws.handle(1, b'{"type":"progress","data":{"value":5,"max":9,"prompt_id":"other"}}'); assert ws.progress is None
    ws.handle(2, b"\x00\x00"); ws.handle(1, b"not json"); assert ws.previews == 0
    assert comfyws.parse_binary(struct.pack(">II", 3, 0) + b"x") == (3, None)


def test_connect_failure_is_graceful():
    assert comfyws.connect("http://127.0.0.1:9", "x") is None


def test_comfy_hires_workflow():
    import json
    import os
    path = os.path.join(os.path.dirname(imagegen.__file__), "workflows", "sdxl_txt2img.json")
    wf = json.load(open(path, encoding="utf-8"))["workflow"]
    out = imagegen.add_comfy_hires(wf, 1.5, 0.45, 12)
    up = [n for n in out.values() if n["class_type"] == "LatentUpscaleBy"][0]
    ks = [k for k, n in out.items() if n["class_type"] == "KSampler"]
    assert up["inputs"]["scale_by"] == 1.5 and len(ks) == 2
    second = out[[k for k in ks if k != "3"][0]]
    assert second["inputs"]["denoise"] == 0.45 and second["inputs"]["steps"] == 12
    assert out["8"]["inputs"]["samples"][0] != "3" and wf["8"]["inputs"]["samples"] == ["3", 0]  # original untouched
    assert imagegen.add_comfy_hires({"1": {"class_type": "Foo", "inputs": {}}}) == {"1": {"class_type": "Foo", "inputs": {}}}


def test_comfy_generate_uses_ws_preview(monkeypatch):
    png = test_v4.PNG
    url, _ = _ws_server([(1, b'{"type":"progress","data":{"value":10,"max":20,"prompt_id":"p1"}}'),
                         (2, struct.pack(">II", 1, 2) + png)])
    c = ComfyUI(url)
    state = {"n": 0}

    def fake(u, data=None, timeout=30, **k):
        if u.endswith("/prompt"):
            assert data["client_id"] == c.client_id
            return {"prompt_id": "p1"}
        if "/history/" in u:
            state["n"] += 1
            if state["n"] < 15:
                return {}
            return {"p1": {"status": {"completed": True}, "outputs": {"9": {"images": [{"filename": "a.png"}]}}}}
        if "/view" in u:
            return png
        return {}
    monkeypatch.setattr(imagegen, "_http", fake); monkeypatch.setattr(imagegen, "BEFORE_GENERATE", [])
    msgs = []
    j = Job("p", tag="create")
    assert c.generate(j, {"1": {"class_type": "SaveImage", "inputs": {}}}, progress=lambda p, m: msgs.append((p, m)), poll=0.05) == [png]
    assert j.preview == png and (50, "Step 10/20") in msgs


def test_comfy_names_from_forge_settings():
    assert imagegen.comfy_names("DPM++ 2M", "Karras") == ("dpmpp_2m", "karras")
    assert imagegen.comfy_names("Euler a", "SGM Uniform") == ("euler_ancestral", "sgm_uniform")
    assert imagegen.comfy_names("DPM++ 2M Karras", "normal") == ("dpmpp_2m", "karras")
    assert imagegen.comfy_names("dpmpp_2m_sde", "beta") == ("dpmpp_2m_sde", "beta")  # comfy names untouched
    assert imagegen.comfy_names("euler", "Automatic") == ("euler", "normal")
