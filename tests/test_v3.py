"""Tests for v3: setup wizard checks, auto-refine loop, LoRA manager, character/style presets, pose sketcher.

Every network service (Ollama, Forge, ComfyUI, Civitai) is a local mock server or a fake client."""
import base64
import json
import os
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promptmaker import autorefine, civitai, firstrun, imagegen, loras, pose, presets  # noqa: E402
from promptmaker.storage import Store  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
LOG = []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        p = self.path; LOG.append(("GET", p, b""))
        mode = self.server.mode
        if p == "/api/tags":
            return self._send({"models": [{"name": m} for m in self.server.models]})
        if p == "/api/version":
            return self._send({"version": "0.40.11"})
        if p == "/sdapi/v1/sd-models":
            if mode == "forge_noapi":
                return self._send({"detail": "Not Found"}, 404)
            return self._send([{"title": "anima.safetensors"}])
        if p == "/sdapi/v1/options":
            return self._send({"sd_model_checkpoint": "anima.safetensors"})
        if p == "/internal/sysinfo":
            return self._send({"Version": "f2.0.1v1.10.1-neo", "Script path": "C:\\AI\\sd-webui-forge-classic"})
        if p == "/openapi.json":
            return self._send({"paths": {"/queue/join": {}, "/internal/sysinfo": {}}} if mode == "forge_noapi" else {"paths": {}})
        if p == "/controlnet/model_list":
            if mode == "forge_nocnapi":
                return self._send({"detail": "Not Found"}, 404)
            if mode == "forge_nocn":
                return self._send({"model_list": ["None"]})
            if mode == "forge_anima":
                return self._send({"model_list": ["None", "anima-lllite-pose-1 [a1b2c3d4]", "xinsir_openpose_sdxl"]})
            return self._send({"model_list": ["None", "control_v11p_sd15_openpose", "xinsir_openpose_sdxl"]})
        if p == "/sdapi/v1/scripts":
            return self._send({"txt2img": ["controlnet", "refiner"], "img2img": []})
        if p == "/system_stats":
            if mode != "comfy":
                return self._send({}, 404)
            return self._send({"system": {"comfyui_version": "0.3.60"}, "devices": [{"name": "RTX"}]})
        if p == "/object_info/ControlNetLoader":
            return self._send({"ControlNetLoader": {"input": {"required": {"control_net_name": [["openpose_sdxl.safetensors"]]}}}})
        if p.startswith("/history/"):
            pid = p.split("/")[-1]
            return self._send({pid: {"status": {"status_str": "success", "completed": True},
                                     "outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}}})
        if p.startswith("/view"):
            return self._send(PNG, ctype="image/png")
        if p.startswith("/queue"):
            return self._send({"queue_running": [], "queue_pending": []})
        return self._send({"error": "nope"}, 404)

    def do_POST(self):
        p, body = self.path, self._body(); LOG.append(("POST", p, body))
        if p == "/api/pull":
            name = json.loads(body)["model"]
            if name == "nosuchmodel":
                return self._send(b'{"status":"pulling manifest"}\n{"error":"pull model manifest: file does not exist"}\n',
                                  ctype="application/x-ndjson")
            lines = [{"status": "pulling manifest"}, {"status": "pulling abc", "total": 200, "completed": 50},
                     {"status": "pulling abc", "total": 200, "completed": 200}, {"status": "verifying sha256 digest"},
                     {"status": "success"}]
            self.server.models.append(name + ":latest")
            return self._send(b"".join(json.dumps(x).encode() + b"\n" for x in lines), ctype="application/x-ndjson")
        if p == "/sdapi/v1/txt2img":
            self.server.last_payload = json.loads(body)
            info = {"seed": 7, "extra_generation_params": {}, "infotexts": ["a knight\nSteps: 20, Seed: 7"]}
            if self.server.mode == "forge_anima":  # ControlNet ran → it shows up in the generation params
                info["extra_generation_params"]["ControlNet 0"] = "Module: None, Model: anima-lllite-pose-1"
            return self._send({"images": [base64.b64encode(PNG).decode()], "info": json.dumps(info)})
        if p == "/upload/image":
            assert b'filename="pm_pose_' in body and PNG in body
            return self._send({"name": "pm_pose.png", "subfolder": "", "type": "input"})
        if p == "/prompt":
            self.server.last_prompt = json.loads(body)["prompt"]
            return self._send({"prompt_id": "p1", "number": 1, "node_errors": {}})
        return self._send({}, 200)


def _serve(mode, models=None):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Mock); srv.mode = mode; srv.models = list(models or [])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture()
def srv():
    made = []

    def make(mode="ollama", models=None):
        s = _serve(mode, models); made.append(s[0]); return s
    yield make
    for s in made:
        s.shutdown()


DEAD = "http://127.0.0.1:9"  # nothing listens on the discard port


# ---------------------------------------------------------------- 1. setup wizard
def test_check_ollama_running_with_models(srv):
    _, url = srv("ollama", ["llama3.2:latest", "qwen2.5vl:7b"])
    r = firstrun.check_ollama(url, binary="")
    assert r["running"] and r["installed"] and r["version"] == "0.40.11"
    assert r["has_text"] and r["has_vision"] and firstrun.has_model(r["models"], "qwen2.5vl")


def test_check_ollama_not_running():
    r = firstrun.check_ollama(DEAD, binary="")
    assert not r["running"] and not r["installed"] and r["models"] == [] and not r["has_text"]
    assert firstrun.check_ollama(DEAD, binary="/usr/bin/ollama")["installed"] is True


def test_pull_progress_and_error(srv):
    _, url = srv("ollama")
    seen = []
    assert firstrun.pull("qwen2.5vl", url, lambda p, s: seen.append((p, s))) is True
    assert (25, "pulling abc") in seen and (100, "pulling abc") in seen and seen[-1] == (-1, "success")
    with pytest.raises(firstrun.PullError, match="does not exist"):
        firstrun.pull("nosuchmodel", url)
    with pytest.raises(firstrun.PullError, match="isn't running"):
        firstrun.pull("x", DEAD)


def test_pull_can_stop(srv):
    _, url = srv("ollama")
    assert firstrun.pull("llama3.2", url, stop_flag=lambda: True) is False


def test_detect_forge_and_comfy(srv):
    _, forge = srv("forge")
    _, noapi = srv("forge_noapi")
    _, comfy = srv("comfy")
    ok = firstrun.detect_forge(forge)
    assert ok["found"] and ok["api"] and "Forge" in ok["message"] and "1 checkpoint" in ok["message"]
    bad = firstrun.detect_forge(noapi)
    assert bad["found"] and not bad["api"] and bad["hint"] == imagegen.API_FIX
    assert not firstrun.detect_forge(DEAD)["found"]
    assert firstrun.detect_comfy(comfy)["found"] and "0.3.60" in firstrun.detect_comfy(comfy)["message"]
    assert not firstrun.detect_comfy(DEAD)["found"]


def test_save_results_picks_backend(tmp_path, srv):
    _, forge = srv("forge")
    st = Store(str(tmp_path / "t.db"))
    res = firstrun.run_all(DEAD, forge, DEAD, binary="")
    assert firstrun.save_results(st, res, forge, DEAD) == "a1111"
    assert st.get("img_url:a1111") == forge and st.get("setup_done") is True
    assert st.get("setup_results")["forge"]["api"] is True
    st.set("img_backend", "comfyui")  # never overrides an existing choice
    assert firstrun.save_results(st, res, forge, DEAD) == "comfyui"


# ---------------------------------------------------------------- 2. auto-refine loop
def test_parse_judgement_variants():
    assert autorefine.parse_judgement('{"score": 72, "missing": ["red scarf"], "advice": "add it"}')["score"] == 72
    assert autorefine.parse_judgement('{"score": 7.5}')["score"] == 75  # 0-10 scale
    assert autorefine.parse_judgement("I'd give it 64/100")["score"] == 64
    j = autorefine.parse_judgement("garbage")
    assert j["score"] == 0 and j["missing"] == [] and j["advice"] == ""
    assert autorefine.parse_judgement('{"score": 250, "wrong": "hands"}') == {"score": 100, "matches": [], "missing": [],
                                                                            "wrong": ["hands"], "advice": ""}


def test_clean_prompt_and_messages():
    assert autorefine.clean_prompt('<think>hmm</think>\n"a cat on a mat"') == "a cat on a mat"
    assert autorefine.clean_prompt("Sure! <prompt>a dog</prompt>") == "a dog"
    m = autorefine.judge_messages("a cat", "cat, mat", PNG)
    assert m[1]["images"] == [base64.b64encode(PNG).decode()] and "a cat" in m[1]["content"]
    r = autorefine.rewrite_messages("a cat", "cat", {"score": 40, "missing": ["mat"], "wrong": [], "advice": "add mat"},
                                    {"name": "SDXL", "ai_guidance": "tags"})
    assert "Missing: mat" in r[1]["content"] and "SDXL" in r[0]["content"]


def _loop(scores, **kw):
    it = iter(scores)
    gens, rewrites = [], []
    res = autorefine.run("idea", "p0", lambda p: gens.append(p) or PNG,
                         lambda i, p, png: {"score": next(it), "matches": [], "missing": [], "wrong": [], "advice": ""},
                         lambda i, p, j: rewrites.append(p) or f"p{len(rewrites)}", **kw)
    return res, gens, rewrites


def test_loop_stops_at_threshold():
    res, gens, _ = _loop([40, 70, 90, 95], iterations=5, threshold=85)
    assert res["reason"] == "threshold" and len(res["steps"]) == 3 and gens == ["p0", "p1", "p2"]
    assert res["best"]["i"] == 3 and res["best"]["prompt"] == "p2"


def test_loop_keeps_best_and_no_rewrite_after_last():
    res, _, rewrites = _loop([60, 80, 50], iterations=3, threshold=99)
    assert res["reason"] == "iterations" and res["best"]["score"] == 80 and res["best"]["prompt"] == "p1"
    assert len(rewrites) == 2


def test_loop_stop_flag():
    calls = {"n": 0}

    def stop():
        calls["n"] += 1; return calls["n"] > 3
    res, _, _ = _loop([10, 20, 30, 40], iterations=4, threshold=99, stop_flag=stop)
    assert res["reason"] == "stopped" and 1 <= len(res["steps"]) < 4


# ---------------------------------------------------------------- 3. LoRA manager
class FakeCivitai:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None, force=False):
        self.calls.append(path)
        sha = path.rsplit("/", 1)[-1]
        if sha.startswith(self.known):
            return {"id": 55, "modelId": 11, "name": "v1", "baseModel": "Illustrious", "trainedWords": ["aiko", "silver hair "],
                    "model": {"name": "Aiko Character", "type": "LORA"},
                    "images": [{"url": "https://image.civitai.com/x.jpeg", "type": "image"}]}
        raise civitai.CivitaiError("Civitai: not found – check the link or ID")


def _models(tmp_path):
    root = tmp_path / "models"
    (root / "Lora" / "chars").mkdir(parents=True); (tmp_path / "embeddings").mkdir()
    (root / "Lora" / "chars" / "aiko.safetensors").write_bytes(b"aiko-weights")
    (root / "Lora" / "notes.txt").write_text("ignore me")
    (root / "Lora" / "mystery.safetensors").write_bytes(b"other")
    (tmp_path / "embeddings" / "easynegative.pt").write_bytes(b"emb")
    return str(root)


def test_scan_finds_forge_layout(tmp_path):
    items = loras.scan(_models(tmp_path))
    assert [(i["kind"], i["name"]) for i in items] == [("embedding", "easynegative"), ("lora", "aiko"), ("lora", "mystery")]


def test_hashes():
    import hashlib
    sha = hashlib.sha256(b"aiko-weights").hexdigest().upper()
    assert loras.autov2(sha) == sha[:10] and len(loras.autov2(sha)) == 10


def test_enrich_lookup_and_cache(tmp_path):
    import hashlib
    root = _models(tmp_path)
    cache_path = str(tmp_path / "cache" / "loras.json")
    client = FakeCivitai(); client.known = hashlib.sha256(b"aiko-weights").hexdigest().upper()[:10]
    items = loras.enrich(loras.scan(root), loras.Cache(cache_path), client)
    aiko = next(i for i in items if i["name"] == "aiko")
    assert aiko["info"]["name"] == "Aiko Character" and aiko["info"]["trained_words"] == ["aiko", "silver hair"]
    assert aiko["info"]["base_model"] == "Illustrious" and aiko["info"]["url"].endswith("modelVersionId=55")
    assert next(i for i in items if i["name"] == "mystery")["info"] == {"found": False, "checked": pytest.approx(0, abs=1e12)}
    assert all(c.startswith("/model-versions/by-hash/") for c in client.calls) and len(client.calls) == 3
    client2 = FakeCivitai(); client2.known = client.known
    again = loras.enrich(loras.scan(root), loras.Cache(cache_path), client2)
    assert client2.calls == [] and next(i for i in again if i["name"] == "aiko")["info"]["name"] == "Aiko Character"


def test_compatibility_and_insert():
    il = {"id": "illustrious", "format": "tags"}; flux = {"id": "flux1"}; gen = {"id": "generic"}
    child = {"id": "civitai_x", "inherits": "illustrious"}
    item = {"name": "aiko", "kind": "lora", "info": {"base_model": "Illustrious", "trained_words": ["aiko"]}}
    sdxl = {"name": "s", "kind": "lora", "info": {"base_model": "SDXL 1.0"}}
    assert loras.compatible(item, il) is True and loras.compatible(item, flux) is False and loras.compatible(item, gen) is True
    assert loras.compatible(item, child, {"illustrious": il}) is True
    assert loras.compatible(sdxl, il) is True and loras.compatible(sdxl, il, strict=True) is False
    assert loras.compatible({"name": "u", "info": {}}, il) is None
    assert loras.insert_text(item, 0.7) == "aiko, <lora:aiko:0.7>"
    assert loras.insert_text(item, 1, with_words=False) == "<lora:aiko:1>"
    assert loras.insert_text({"name": "easyneg", "kind": "embedding"}, 1.0) == "easyneg"
    assert loras.insert_text({"name": "easyneg", "kind": "embedding"}, 1.2) == "(easyneg:1.2)"
    assert loras.insert_into("1girl, ", "<lora:a:1>") == "1girl, <lora:a:1>"
    assert loras.used_loras("x <lora:a:0.5> <lora:b:1>") == [("a", 0.5), ("b", 1.0)]


# ---------------------------------------------------------------- 4. presets
def test_migration_from_v2_database(tmp_path):
    path = str(tmp_path / "v2.db")
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);"
                     "CREATE TABLE history(id INTEGER PRIMARY KEY, ts REAL, prompt TEXT, fmt TEXT, source TEXT);"
                     "INSERT INTO history(ts,prompt,fmt,source) VALUES(1,'old prompt','SDXL','builder');"
                     "INSERT INTO settings VALUES('seeded','true');")
    db.commit(); db.close()
    st = Store(path)
    assert st.schema_version() == Store.SCHEMA_VERSION >= 3 and st.history()[0][2] == "old prompt" and st.characters() == []
    st.save_style({"name": "Ink", "tags": "ink wash"})
    assert Store(path).style("Ink")["tags"] == "ink wash"  # migration runs once; data kept on reopen


def test_character_and_style_crud(tmp_path):
    st = Store(str(tmp_path / "t.db"))
    cid = st.save_character({"name": "Aiko", "appearance": "silver hair, red eyes", "outfit": "black kimono",
                             "lora": "aiko_v1", "lora_weight": 0.7, "ref_image": "C:/ref.png"})
    assert st.character("Aiko")["lora_weight"] == 0.7
    st.save_character({"name": "Aiko", "appearance": "silver hair", "outfit": "", "lora": ""}, cid)
    assert st.character(cid)["appearance"] == "silver hair" and len(st.characters()) == 1
    with pytest.raises(ValueError):
        st.save_character({"name": " "})
    sid = st.save_style({"name": "Watercolour", "tags": "watercolor, soft pastel", "negative": "photo"})
    st.delete_character(cid); st.delete_style(sid)
    assert st.characters() == [] and st.styles() == []


def test_compose_combines_and_dedupes():
    aiko = {"name": "Aiko", "appearance": "silver hair, red eyes", "outfit": "black kimono", "lora": "aiko_v1", "lora_weight": 0.7}
    ren = {"name": "Ren", "appearance": "black hair", "outfit": "school uniform", "lora": ""}
    style = {"name": "W", "tags": "watercolor, red eyes", "negative": "photo, 3d"}
    out = presets.compose("shrine at sunset", [aiko], [style], {"format": "tags"})
    assert out == "silver hair, red eyes, black kimono, <lora:aiko_v1:0.7>, shrine at sunset, watercolor"
    two = presets.compose("park", [aiko, ren], [], {"format": "tags"})
    assert two.startswith("2 characters, ") and "school uniform" in two
    assert presets.compose("park", [ren], [], {"format": "natural"}).startswith("Ren, black hair")
    assert presets.negative([style], "lowres, photo") == "lowres, photo, 3d"


def test_presets_consistent_across_batch():
    aiko = {"name": "Aiko", "appearance": "silver hair", "outfit": "kimono", "lora": ""}
    out = presets.apply_to_batch(["beach, noon", "forest, night", "city, rain"], [aiko], [{"tags": "anime screencap"}])
    assert len(out) == 3 and all(o.startswith("silver hair, kimono, ") and o.endswith("anime screencap") for o in out)


# ---------------------------------------------------------------- 5. pose sketcher
def test_pose_presets_describe():
    expect = {"Standing": "standing", "Arms up": "arms up", "Waving": "hand up, waving", "T-pose": "arms outstretched",
              "Hands on hips": "hands on hips", "Sitting": "sitting", "Walking": "walking", "Kneeling": "kneeling"}
    for name, tag in expect.items():
        tags = pose.describe_figure(pose.new_figure(name))
        assert tag in tags and "facing viewer" in tags, (name, tags)
    assert "hands on hips" not in pose.describe_figure(pose.new_figure("Standing"))


def test_pose_facing_and_framing():
    f = pose.new_figure()
    f["points"] = [[1 - x, y] for x, y in f["points"]]  # mirror → shoulders swapped → seen from behind
    assert "from behind" in pose.describe_figure(f)
    big = pose.new_figure(scale=2.2)  # legs run off the bottom edge
    assert pose.framing(big) in ("upper body", "cowboy shot", "close-up portrait")
    assert pose.framing(pose.new_figure(scale=0.4)) == "wide shot, full body"
    assert pose.framing(pose.new_figure()) == "full body"


def test_composition_tags_and_natural():
    figs = [pose.new_figure("Standing", dx=-.25), pose.new_figure("Arms up", dx=.25)]
    boxes = [{"label": "castle", "x": .4, "y": .05, "w": .2, "h": .2}]
    c = pose.composition(figs, boxes, {"format": "tags"})
    assert c["tags"][:2] == ["2people", "full body"] and "person on the left" in c["tags"] and "person on the right" in c["tags"]
    assert "castle in the center in the background" in c["tags"] and c["text"] == ", ".join(c["tags"])
    n = pose.composition(figs, boxes, {"format": "natural"})["text"]
    assert n.startswith("Full body composition: person 1 on the left") and n.endswith(".")
    assert pose.composition([pose.new_figure()], [], {})["tags"][:2] == ["solo", "full body"]


def test_render_openpose_png():
    from PySide6.QtGui import QGuiApplication, QImage
    QGuiApplication.instance() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication([])
    png = pose.render_openpose([pose.new_figure()], 64, 96)
    img = QImage.fromData(png)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and (img.width(), img.height()) == (64, 96)
    assert img.pixelColor(0, 0).red() == 0 and img.pixelColor(32, int(.22 * 96)).value() > 0  # black bg, coloured neck


def test_forge_controlnet_payload(srv):
    _, url = srv("forge")
    be = imagegen.A1111(url)
    job = imagegen.Job("a knight", width=512, height=768)
    job.controlnet = {"image": PNG, "model": "xinsir_openpose_sdxl", "weight": 0.8}
    be.generate(job)
    srv_payload = [s for s in LOG if s[1] == "/sdapi/v1/txt2img"][-1][2]
    unit = json.loads(srv_payload)["alwayson_scripts"]["controlnet"]["args"][0]
    assert unit["enabled"] and unit["module"] == "None" and unit["model"] == "xinsir_openpose_sdxl" and unit["weight"] == 0.8
    assert base64.b64decode(unit["image"]) == PNG
    assert be.controlnet_models() == ["control_v11p_sd15_openpose", "xinsir_openpose_sdxl"]
    assert "alwayson_scripts" not in imagegen.A1111(url).payload(imagegen.Job("x"))


def test_comfy_controlnet_workflow_patch(srv):
    wf = imagegen.load_workflow(os.path.join(imagegen.WORKFLOW_DIR, "sdxl_txt2img.json"))[0]
    patched = pose.add_comfy_controlnet(wf, "pose.png", "openpose.safetensors", 0.9)
    ks = next(n for n in patched.values() if n["class_type"] == "KSampler")
    ap = patched[ks["inputs"]["positive"][0]]
    assert ap["class_type"] == "ControlNetApplyAdvanced" and ks["inputs"]["negative"] == [ks["inputs"]["positive"][0], 1]
    assert patched[ap["inputs"]["image"][0]]["inputs"]["image"] == "pose.png" and ap["inputs"]["strength"] == 0.9
    assert patched[ap["inputs"]["control_net"][0]]["inputs"]["control_net_name"] == "openpose.safetensors"
    assert "ControlNetApplyAdvanced" not in json.dumps(wf)  # original untouched
    with pytest.raises(ValueError):
        pose.add_comfy_controlnet({"1": {"class_type": "SaveImage", "inputs": {}}}, "p.png", "m")
    s, url = srv("comfy")
    be = imagegen.ComfyUI(url)
    job = imagegen.Job("a knight"); job.controlnet = {"image": PNG, "model": "openpose_sdxl.safetensors", "weight": 1.0}
    assert be.generate(job, wf, poll=0.01) == [PNG]
    assert any(n["class_type"] == "ControlNetApplyAdvanced" for n in s.last_prompt.values())
    assert be.controlnet_models() == ["openpose_sdxl.safetensors"]


# ---------------------------------------------------------------- UI
@pytest.fixture()
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow(Store(str(tmp_path / "t.db")), str(tmp_path)); w.resize(1280, 800); w.show()
    yield w
    w.close()


def test_ui_v3_pages_present(win):
    from promptmaker import __version__
    from promptmaker.app import NAV
    assert int(__version__.split(".")[0]) >= 3  # v3 pages must survive later versions
    for name in ("Auto-refine", "Pose", "Presets", "LoRAs"):
        win.go(name); assert NAV[win.stack.currentIndex()][1] == name


def test_ui_setup_wizard(win, srv):
    from PySide6.QtWidgets import QApplication
    _, forge = srv("forge")
    win.store.set("img_url:a1111", forge)
    dlg = win.open_setup()
    res = firstrun.run_all(DEAD, forge, DEAD, binary="")
    dlg.show_results(res)
    assert "not found" in dlg.ol_status.text().lower() and not dlg.pull_text.isEnabled()
    assert dlg.forge_lbl.text().startswith("✅")
    dlg.finish(); QApplication.processEvents()
    assert win.store.get("setup_done") and win.store.get("img_backend") == "a1111"
    assert win.img_kind.currentData() == "a1111"


def test_ui_setup_wizard_pull(win, srv):
    import time
    from PySide6.QtWidgets import QApplication
    s, url = srv("ollama", [])
    dlg = win.open_setup()
    dlg._urls = lambda: (url, DEAD, DEAD)
    dlg.show_results(firstrun.run_all(url, DEAD, DEAD, binary=""))
    assert dlg.pull_vision.isEnabled()
    dlg.pull("qwen2.5vl")
    t = time.time()
    while (dlg.pull_worker.isRunning() or "qwen2.5vl:latest" not in s.models) and time.time() - t < 5:
        QApplication.processEvents(); time.sleep(0.01)
    dlg.pull_worker.wait(2000); QApplication.processEvents()
    assert dlg.pull_bar.value() == 100 and "qwen2.5vl:latest" in s.models


def test_ui_presets_and_batch(win):
    from PySide6.QtCore import Qt
    win.profile_combo.setCurrentIndex(win.profile_combo.findData("illustrious"))
    win.go("Presets")
    win.ch_name.setText("Aiko"); win.ch_app.setPlainText("silver hair, red eyes"); win.ch_outfit.setPlainText("kimono"); win.ch_save()
    win.st_name.setText("Ink"); win.st_tags.setPlainText("ink wash painting"); win.st_save()
    win.ch_list.item(0).setCheckState(Qt.Checked); win.st_list.item(0).setCheckState(Qt.Checked)
    win.pr_in.setPlainText("on a bridge")
    assert win.pr_combine() == "silver hair, red eyes, kimono, on a bridge, ink wash painting"
    win.batch_presets.setChecked(True); win.batch_rand.setChecked(True); win.batch_n.setValue(3); win.batch_generate()
    items = win.batch_items()
    assert len(items) == 3 and all(i.startswith("silver hair, red eyes, kimono") for i in items)
    win.ch_delete()  # the ConfirmButton wraps this; calling directly deletes
    assert win.store.characters() == []


def test_ui_pose_page(win):
    win.go("Pose")
    win.pose_canvas.clear(); win.pose_canvas.add_figure("Arms up"); win.pose_canvas.add_box("dragon", (.65, .1, .3, .3))
    t = win.pose_tags.toPlainText()
    assert "arms up" in t or "Arms up" in t or "arms up" in t.lower()
    assert "dragon" in t and win.store.get("pose_state")["boxes"][0]["label"] == "dragon"
    png = win.pose_png()
    assert png and png[:4] == b"\x89PNG"
    win.pose_canvas.selected = ("fig", 0); win.pose_canvas.set_preset("Sitting"); assert "sitting" in win.pose_tags.toPlainText().lower()
    win.pose_canvas.selected = ("box", 0); win.pose_canvas.remove_selected()
    assert "dragon" not in win.pose_tags.toPlainText()
    win.pose_target.setCurrentIndex(win.pose_target.findData("work"))
    win._insert_text(win.pose_tags.toPlainText(), "work")
    assert "sitting" in win.work.toPlainText().lower()


def test_ui_pose_generate_with_controlnet(win, srv):
    import time
    from PySide6.QtWidgets import QApplication
    s, url = srv("forge")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Pose"); win.pose_cn_model.setCurrentText("xinsir_openpose_sdxl")
    win.work.setPlainText("a knight")
    job = win.pose_generate()
    t = time.time()
    while win.genq.isRunning() and time.time() - t < 5:
        QApplication.processEvents(); time.sleep(0.02)
    QApplication.processEvents()
    assert job.controlnet["model"] == "xinsir_openpose_sdxl"
    assert s.last_payload["alwayson_scripts"]["controlnet"]["args"][0]["model"] == "xinsir_openpose_sdxl"
    assert s.last_payload["prompt"].startswith("a knight, ") and "composition" in s.last_payload["prompt"]


def test_ui_lora_page(win, tmp_path, monkeypatch):
    import hashlib
    import time
    from PySide6.QtWidgets import QApplication
    root = _models(tmp_path)
    client = FakeCivitai(); client.known = hashlib.sha256(b"aiko-weights").hexdigest().upper()[:10]
    monkeypatch.delenv("PROMPTMAKER_NO_NET")
    win.civitai_client = lambda: client
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))  # previews
    win.go("LoRAs"); win.lora_root.setText(root); win.lora_scan()
    t = time.time()
    while win.lora_worker.isRunning() and time.time() - t < 5:
        QApplication.processEvents(); time.sleep(0.01)
    win.lora_worker.wait(); QApplication.processEvents()
    assert "3 file(s)" in win.lora_status.text() and "1 identified" in win.lora_status.text()
    win.profile_combo.setCurrentIndex(win.profile_combo.findData("flux1"))
    names = [win.lora_list.item(i).text() for i in range(win.lora_list.count())]
    assert not any("Aiko Character" in n for n in names)  # Illustrious LoRA hidden for FLUX
    win.profile_combo.setCurrentIndex(win.profile_combo.findData("illustrious"))
    row = next(i for i in range(win.lora_list.count()) if "Aiko Character" in win.lora_list.item(i).text())
    win.lora_list.setCurrentRow(row); win.lora_weight.setValue(0.6)
    win.lora_target.setCurrentIndex(win.lora_target.findData("work")); win.work.setPlainText("1girl")
    win.lora_insert()
    assert win.work.toPlainText() == "1girl, aiko, silver hair, <lora:aiko:0.6>"
    assert os.path.exists(os.path.join(str(tmp_path), "cache", "loras.json"))


def test_ui_autorefine_loop(win, srv):
    import time
    from PySide6.QtWidgets import QApplication
    s, url = srv("forge")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)

    class FakeProvider:
        pid, kind, notes = "fake", "ollama", {}

        def __init__(self):
            self.n = 0

        def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
            if json_mode:
                self.n += 1
                yield json.dumps({"score": [55, 91][min(self.n - 1, 1)], "missing": ["lantern"], "advice": "add a lantern"})
            else:
                yield "<prompt>a lighthouse keeper holding a lantern at dusk</prompt>"
    win.provider = FakeProvider()
    win.model.clear(); win.model.addItem("llama3.2"); win.model.setCurrentIndex(0)
    win.go("Auto-refine"); win.ar_idea.setPlainText("a lighthouse keeper with a lantern"); win.ar_vision.setCurrentText("qwen2.5vl")
    win.ar_iters.setValue(4); win.ar_thresh.setValue(85)
    msgs = []; win.notify = lambda t, error=False: msgs.append(t)
    win.ar_run(); assert win.ar_worker is not None, msgs
    t = time.time()
    while win.ar_worker.isRunning() and time.time() - t < 10:
        QApplication.processEvents(); time.sleep(0.02)
    win.ar_worker.wait(); QApplication.processEvents()
    assert [r["score"] for r in win.ar_steps] == [55, 91], win.ar_status.text()
    assert win.ar_list.count() == 2
    assert "reached the target score" in win.ar_status.text()
    win.ar_keep_best()
    assert win.work.toPlainText() == "a lighthouse keeper holding a lantern at dusk"
    assert win.store.favourites()[0][3] == win.work.toPlainText()
    assert len(win.gallery.items()) == 2


# ---------------------------------------------------------------- ControlNet model checks
def test_cn_family_and_profile_family():
    assert pose.cn_family("control_v11p_sd15_openpose [cab727d4]") == "SD1.5"
    assert pose.cn_family("xinsir_openpose_sdxl") == "SDXL"
    assert pose.cn_family("anima-lllite-pose-1") == "Anima"
    assert pose.cn_family("flux-controlnet-union") == "FLUX"
    assert pose.cn_family("mystery") == "" and pose.cn_family("mystery", "Illustrious") == "SDXL"
    assert pose.profile_family({"name": "Anima (CircleStone Labs, anime)", "family": "Anima"}) == "Anima"
    assert pose.profile_family({"name": "Illustrious XL / NoobAI", "family": "Stable Diffusion"}) == "SDXL"
    assert pose.profile_family({"name": "Midjourney V7", "family": "Midjourney"}) == ""


def test_cn_compat_warning_anima():
    anima = {"name": "Anima (CircleStone Labs, anime)", "family": "Anima"}
    assert "Anima" in pose.cn_compat_warning("xinsir_openpose_sdxl", anima)
    assert "Anima" in pose.cn_compat_warning("mystery_model", anima)
    assert pose.cn_compat_warning("anima-lllite-pose-1", anima) == ""
    sdxl = {"name": "Stable Diffusion XL 1.0", "family": "Stable Diffusion"}
    assert "SD1.5" in pose.cn_compat_warning("control_v11p_sd15_openpose", sdxl)
    assert pose.cn_compat_warning("xinsir_openpose_sdxl", sdxl) == ""


def test_resolve_and_pick_cn_model():
    models = ["control_v11p_sd15_openpose [cab727d4]", "anima-lllite-pose-1 [a1b2c3d4]"]
    assert pose.resolve_cn_model("control_v11p_sd15_openpose", models) == models[0]
    assert pose.resolve_cn_model("Anima-LLLite-Pose-1.safetensors", models) == models[1]
    assert pose.resolve_cn_model("nope", models) == ""
    assert pose.pick_default_cn(models, {"name": "Anima", "family": "Anima"}) == models[1]
    assert pose.pick_default_cn([], None) == ""


def test_controlnet_applied_from_info():
    assert pose.controlnet_applied({"extra_generation_params": {"ControlNet 0": "Model: x"}}) is True
    assert pose.controlnet_applied(json.dumps({"infotexts": ["..., ControlNet 0: \"Module: none\""]})) is True
    assert pose.controlnet_applied({"seed": 1, "extra_generation_params": {}}) is False
    assert pose.controlnet_applied({"seed": 1}) is None and pose.controlnet_applied("not json") is None


def test_forge_cn_model_info_fallbacks(srv):
    _, url = srv("forge_nocn")
    assert imagegen.A1111(url).controlnet_model_info() == {"models": [], "known": True}
    _, url = srv("forge_nocnapi")
    assert imagegen.A1111(url).controlnet_model_info()["known"] is False  # can't tell → user may type a name
    assert imagegen.A1111(DEAD).controlnet_model_info()["known"] is False


def test_forge_records_controlnet_applied(srv):
    _, url = srv("forge_anima")
    job = imagegen.Job("x"); job.controlnet = {"image": PNG, "model": "anima-lllite-pose-1 [a1b2c3d4]"}
    imagegen.A1111(url).generate(job)
    assert job.controlnet_applied is True
    _, url = srv("forge")
    job = imagegen.Job("x"); job.controlnet = {"image": PNG, "model": "xinsir_openpose_sdxl"}
    imagegen.A1111(url).generate(job)
    assert job.controlnet_applied is False


def _wait(win):
    import time
    from PySide6.QtWidgets import QApplication
    t = time.time()
    time.sleep(0.05)
    while win.genq.isRunning() and time.time() - t < 5:
        QApplication.processEvents(); time.sleep(0.02)
    for _ in range(20):
        QApplication.processEvents(); time.sleep(0.01)


def test_ui_pose_blocks_when_no_controlnet_models(win, srv):
    s, url = srv("forge_nocn")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Pose"); win.work.setPlainText("a knight"); s.last_payload = None
    assert win.pose_generate() is None
    assert s.last_payload is None and "kohya-ss/Anima-LLLite" in win.pose_cn_status.text()


def test_ui_pose_anima_uses_exact_name_and_reports_applied(win, srv):
    s, url = srv("forge_anima")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.profile_combo.setCurrentIndex(next(i for i in range(win.profile_combo.count()) if "anima" in str(win.profile_combo.itemData(i)).lower()))
    assert win.profile["family"] == "Anima"
    win.go("Pose"); win.work.setPlainText("a knight")
    job = win.pose_generate()
    assert job and job.controlnet["model"] == "anima-lllite-pose-1 [a1b2c3d4]"
    assert not win.pose_cn_model.isEditable() and win.pose_cn_model.count() == 2
    _wait(win)
    assert s.last_payload["alwayson_scripts"]["controlnet"]["args"][0]["model"] == "anima-lllite-pose-1 [a1b2c3d4]"
    assert "applied" in win.pose_cn_status.text()
    win.pose_cn_model.setCurrentText("xinsir_openpose_sdxl")
    assert "Anima" in win.pose_cn_status.text()


def test_ui_pose_warns_when_not_applied(win, srv):
    s, url = srv("forge")
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Pose"); win.work.setPlainText("a knight")
    job = win.pose_generate()
    assert job
    _wait(win)
    assert job.controlnet_applied is False and "may not have been applied" in win.pose_cn_status.text()
