"""Tests for v4: wildcards & dynamic prompts, inpaint & regional prompts, library sync (file + gist), video prompts.

Every network service (Forge, ComfyUI, GitHub gist API, Ollama) is a local mock server or a fake client."""
import base64
import json
import os
import sqlite3
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promptmaker import imagegen, providers, regions, sync, video, wildcards  # noqa: E402
from promptmaker.keystore import KeyStore  # noqa: E402
from promptmaker.storage import Store  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


# ================================================================ mock server: Forge + ComfyUI + Ollama + GitHub gists
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
        s, p = self.server, self.path
        s.log.append(("GET", p, None))
        if p == "/sdapi/v1/scripts":
            return self._send({"txt2img": ["forge couple", "controlnet"] if s.mode == "couple" else ["controlnet"], "img2img": []})
        if p.startswith("/history/"):
            pid = p.split("/")[-1]
            return self._send({pid: {"status": {"status_str": "success", "completed": True},
                                     "outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}}})
        if p.startswith("/view"):
            return self._send(PNG, ctype="image/png")
        if p.startswith("/queue"):
            return self._send({"queue_running": [], "queue_pending": []})
        if p.startswith("/sdapi/v1/progress"):
            return self._send({"progress": 0.5, "state": {}})
        if p == "/user":
            return self._auth() or self._send({"login": "Kisahime"})
        if p.startswith("/gists/"):
            if self._auth():
                return
            gid = p.split("/")[-1]
            if gid not in s.gists:
                return self._send({"message": "Not Found"}, 404)
            return self._send({"id": gid, "files": {k: {"content": v, "truncated": False} for k, v in s.gists[gid].items()}})
        return self._send({"error": "nope"}, 404)

    def _auth(self):
        if self.headers.get("Authorization") != "Bearer ghp_TESTTOKEN1234567890":
            self._send({"message": "Bad credentials"}, 401); return True
        return False

    def do_PATCH(self):
        s, p, body = self.server, self.path, self._body()
        s.log.append(("PATCH", p, body))
        if self._auth():
            return
        gid = p.split("/")[-1]
        for k, v in json.loads(body)["files"].items():
            s.gists.setdefault(gid, {})[k] = v["content"]
        return self._send({"id": gid})

    def do_POST(self):
        s, p, body = self.server, self.path, self._body()
        s.log.append(("POST", p, body))
        if p in ("/sdapi/v1/txt2img", "/sdapi/v1/img2img"):
            s.last_endpoint, s.last_payload = p, json.loads(body)
            return self._send({"images": [base64.b64encode(PNG).decode()], "info": json.dumps({"seed": 7})})
        if p == "/upload/image":
            s.uploads.append(body)
            return self._send({"name": "pm_inpaint.png", "subfolder": "", "type": "input"})
        if p == "/prompt":
            s.last_prompt = json.loads(body)["prompt"]
            return self._send({"prompt_id": "p1", "number": 1, "node_errors": {}})
        if p == "/api/chat":
            s.last_chat = json.loads(body)
            text = s.chat_reply
            lines = [{"message": {"content": text[i:i + 9]}, "done": False} for i in range(0, len(text), 9)] + [{"done": True}]
            return self._send(b"".join(json.dumps(x).encode() + b"\n" for x in lines), ctype="application/x-ndjson")
        if p == "/gists":
            if self._auth():
                return
            d = json.loads(body); gid = f"g{len(s.gists) + 1}"
            assert d["public"] is False
            s.gists[gid] = {k: v["content"] for k, v in d["files"].items()}
            return self._send({"id": gid}, 201)
        return self._send({}, 200)


@pytest.fixture()
def srv():
    made = []

    def make(mode=""):
        s = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        s.mode, s.log, s.gists, s.uploads, s.chat_reply = mode, [], {}, [], ""
        threading.Thread(target=s.serve_forever, daemon=True).start(); made.append(s)
        return s, f"http://127.0.0.1:{s.server_address[1]}"
    yield make
    for s in made:
        s.shutdown()


def _qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _img(w=64, h=48, colour="red"):
    _qt()
    from PySide6.QtGui import QColor, QImage
    from promptmaker.inpaintcanvas import png_bytes
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor(colour))
    return png_bytes(im)


# ================================================================ 1. wildcards
@pytest.fixture()
def lib(tmp_path):
    root = tmp_path / "wildcards"
    (root / "people").mkdir(parents=True)
    (root / "hair.txt").write_text("red hair\nblue hair\n# a comment\n\n{light|dark} green hair\n", encoding="utf-8")
    (root / "people" / "job.txt").write_text("knight\nwizard\nbaker\n", encoding="utf-8")
    (root / "pack.yaml").write_text("places:\n  indoor:\n    - library\n    - kitchen\n  outdoor: [forest, beach]\nmood:\n- calm\n- tense\n",
                                    encoding="utf-8")
    (root / "loop.txt").write_text("again __loop__\n", encoding="utf-8")
    return wildcards.WildcardLib(str(root))


def test_wildcard_files_folders_and_yaml(lib):
    names = lib.names()
    assert {"hair", "people/job", "places/indoor", "places/outdoor", "pack/places/indoor", "mood"} <= set(names)
    assert lib.get("hair") == ["red hair", "blue hair", "{light|dark} green hair"]  # comments / blanks skipped
    assert lib.get("HAIR") == lib.get("hair")  # case-insensitive
    assert sorted(lib.get("places/*")) == ["beach", "forest", "kitchen", "library"]  # glob
    assert lib.get("nope") == []


def test_mini_yaml_matches_pyyaml():
    text = "a:\n- x\n- 'y'\nb:\n  c:\n    - z\n  d: [p, q]\n"
    assert wildcards._mini_yaml(text) == {"a": ["x", "y"], "b": {"c": ["z"], "d": ["p", "q"]}}
    yaml = pytest.importorskip("yaml")
    assert wildcards._mini_yaml(text) == yaml.safe_load(text)


def test_expand_is_seeded_and_reproducible(lib):
    t = "1girl, __hair__, __people/job__, {smiling|serious}, __places/*__"
    a = [wildcards.expand(t, s, lib) for s in range(20)]
    assert a == [wildcards.expand(t, s, lib) for s in range(20)]
    assert len(set(a)) > 5
    for x in a:
        assert "__" not in x and "{" not in x and x.startswith("1girl, ")


def test_weights_multi_pick_and_nesting():
    picks = [wildcards.expand("{9::a|1::b}", s) for s in range(400)]
    assert 0.8 < picks.count("a") / 400 < 0.97
    for s in range(50):
        r = wildcards.expand("{2$$a|b|c}", s).split(", ")
        assert len(r) == 2 and len(set(r)) == 2 and set(r) <= {"a", "b", "c"}
        r = wildcards.expand("{1-3$$ and $$x|y|z}", s).split(" and ")
        assert 1 <= len(r) <= 3 and set(r) <= {"x", "y", "z"}
        assert wildcards.expand("{red|{light|dark} blue}", s) in {"red", "light blue", "dark blue"}
    assert wildcards.expand("{0::never|always}", 3) == "always"
    assert wildcards.expand("no syntax {here", 1) == "no syntax {here"  # unbalanced braces stay as text


def test_recursion_and_missing(lib):
    seen = set()
    assert wildcards.expand("__nothere__ cat", 1, lib, seen) == "__nothere__ cat" and seen == {"nothere"}
    with pytest.raises(RecursionError):
        wildcards.expand("__loop__", 1, lib)
    # nested: hair entry contains {light|dark}
    outs = {wildcards.expand("__hair__", s, lib) for s in range(60)}
    assert {"light green hair", "dark green hair"} & outs


def test_has_syntax_leaves_plain_braces():
    assert wildcards.has_syntax("__hair__") and wildcards.has_syntax("{a|b}") and wildcards.has_syntax("{2$$a|b}")
    assert not wildcards.has_syntax("{masterpiece}, best quality") and not wildcards.has_syntax("")


def test_batch_unique_and_seeds():
    res = wildcards.batch("{a|b|c}", 10, 100)
    assert len(res) == 3 and {p for _, p in res} == {"a", "b", "c"} and res[0][0] == 100
    assert len(wildcards.batch("{a|b|c}", 5, 1, unique=False)) == 5


def test_with_presets_keeps_character(lib):
    char = {"name": "Aiko", "appearance": "silver hair, red eyes", "outfit": "{kimono|hoodie}", "lora": "", "lora_weight": .8}
    outs = [wildcards.with_presets("__people/job__, standing", [char], [], None, s, lib) for s in range(10)]
    assert all(o.startswith("silver hair, red eyes, ") for o in outs)
    assert {o.split(", ")[2] for o in outs} <= {"kimono", "hoodie"}


def test_save_delete_and_import(tmp_path, lib):
    lib.save("colours/warm", "red\norange\n\nyellow")
    assert lib.get("colours/warm") == ["red", "orange", "yellow"]
    with pytest.raises(ValueError):
        lib.save("../evil", ["x"])
    lib.delete("colours/warm"); assert lib.get("colours/warm") == []
    # a Civitai-style zip: wildcards/ prefix, a nested zip, junk files
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("animals/cats.txt", "tabby\nsiamese\n")
    pack = tmp_path / "pack.zip"
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("wildcards/hair.txt", "pink hair\n"); z.writestr("wildcards/eyes.txt", "green eyes\n")
        z.writestr("readme.md", "hi"); z.writestr("__MACOSX/._eyes.txt", "x"); z.write(inner, "more.zip")
    st = lib.import_path(str(pack), "skip")
    assert st == {"added": 2, "skipped": 1, "replaced": 0}
    assert lib.get("eyes") == ["green eyes"] and lib.get("animals/cats") == ["tabby", "siamese"] and "red hair" in lib.get("hair")
    assert lib.import_path(str(pack), "replace")["replaced"] == 3 and lib.get("hair") == ["pink hair"]
    assert lib.import_path(str(pack), "rename")["added"] == 3 and lib.get("hair_2") == ["pink hair"]
    folder = tmp_path / "f"; (folder / "sub").mkdir(parents=True); (folder / "sub" / "x.txt").write_text("1\n2\n")
    assert lib.import_path(str(folder))["added"] == 1 and lib.get("sub/x") == ["1", "2"]


def test_ai_list_via_ollama(srv):
    s, url = srv()
    s.chat_reply = "Here you go:\n1. misty harbour\n2. Misty harbour\n- desert ruins\n* crystal cave\n\nfloating island"
    prov = providers.make("ollama", url)
    text = "".join(prov.stream_chat("llama3.2", wildcards.generate_messages("fantasy locations", 4)))
    assert wildcards.parse_generated(text, 4) == ["misty harbour", "desert ruins", "crystal cave", "floating island"]
    assert "4 entries for: fantasy locations" in s.last_chat["messages"][1]["content"]
    assert wildcards.suggest_name("50 fantasy locations") == "fantasy_locations"


# ================================================================ 2. inpaint & regions
def test_forge_inpaint_payload_goes_to_img2img(srv):
    s, url = srv()
    job = imagegen.Job("a red scarf", "lowres", 64, 48, 5, checkpoint="anima.safetensors")
    job.inpaint = {"image": PNG, "mask": PNG, "denoise": 0.6, "mask_blur": 8, "only_masked": True, "padding": 40, "fill": "original"}
    assert imagegen.A1111(url).generate(job) == [PNG]
    p = s.last_payload
    assert s.last_endpoint == "/sdapi/v1/img2img"
    assert p["init_images"] == [base64.b64encode(PNG).decode()] and p["mask"] == base64.b64encode(PNG).decode()
    assert p["denoising_strength"] == 0.6 and p["mask_blur"] == 8 and p["inpaint_full_res"] is True
    assert p["inpaint_full_res_padding"] == 40 and p["inpainting_fill"] == 1
    assert p["override_settings"]["sd_model_checkpoint"] == "anima.safetensors"
    job2 = imagegen.Job("plain", seed=1); imagegen.A1111(url).generate(job2)
    assert s.last_endpoint == "/sdapi/v1/txt2img" and "mask" not in s.last_payload


def test_forge_regional_detection_and_couple_payload(srv):
    _, plain = srv("")
    _, couple = srv("couple")
    assert imagegen.A1111(plain).regional_support() == ""
    assert imagegen.A1111(couple).regional_support() == regions.FORGE_COUPLE
    assert imagegen.A1111("http://127.0.0.1:9").regional_support() == ""
    assert imagegen.ComfyUI(plain).regional_support() == "comfy"
    job = imagegen.Job("two girls in a park", seed=1)
    job.regions = {"mode": regions.FORGE_COUPLE, "base_weight": 0.4,
                   "regions": [{"prompt": "girl, blonde", "x": 0, "y": 0, "w": .5, "h": 1},
                               {"prompt": "girl, black hair", "x": .5, "y": 0, "w": .5, "h": 1, "weight": 1.2},
                               {"prompt": "", "x": 0, "y": 0, "w": 1, "h": 1}]}
    p = imagegen.A1111(couple).payload(job)
    assert p["prompt"] == "two girls in a park\ntwo girls in a park, girl, blonde\ntwo girls in a park, girl, black hair"
    job.regions["repeat_base"] = False
    assert imagegen.A1111(couple).payload(job)["prompt"] == "two girls in a park\ngirl, blonde\ngirl, black hair"
    job.regions["repeat_base"] = True
    args = p["alwayson_scripts"]["forge couple"]["args"]
    assert args[:4] == [True, True, "Advanced", "\n"] and len(args) == 17
    assert args[7] == [[0.0, 1.0, 0.0, 1.0, 0.4], [0.0, 0.5, 0.0, 1.0, 1.0], [0.5, 1.0, 0.0, 1.0, 1.2]]
    job.regions["mode"] = "plain"
    p = imagegen.A1111(plain).payload(job)
    assert "alwayson_scripts" not in p and p["prompt"] == "two girls in a park, (girl, blonde) on the left, (girl, black hair) on the right"
    assert "sd-forge-couple" in regions.NEEDS_EXTENSION


def test_position_words():
    assert regions.position_words({"x": 0, "y": 0, "w": .3, "h": .3}) == "top left"
    assert regions.position_words({"x": .35, "y": .35, "w": .3, "h": .3}) == "center"
    assert regions.position_words({"x": .4, "y": .7, "w": .2, "h": .3}) == "bottom"


def _wf():
    path = imagegen.list_workflows()["sdxl_txt2img"]
    return imagegen.load_workflow(path)[0]


def test_comfy_area_conditioning():
    regs = [{"prompt": "a cat", "x": 0, "y": 0, "w": .5, "h": 1}, {"prompt": "a dog", "x": .5, "y": .25, "w": .5, "h": .75, "weight": .8}]
    wf = regions.add_comfy_regions(_wf(), regs, 1024, 768)
    by = {k: n for k, n in wf.items()}
    areas = [n for n in by.values() if n["class_type"] == "ConditioningSetArea"]
    assert [(a["inputs"]["x"], a["inputs"]["y"], a["inputs"]["width"], a["inputs"]["height"]) for a in areas] == \
        [(0, 0, 512, 768), (512, 192, 512, 576)]
    assert areas[1]["inputs"]["strength"] == .8
    encs = [n for n in by.values() if n["class_type"] == "CLIPTextEncode" and n["inputs"]["text"] in ("a cat", "a dog")]
    assert len(encs) == 2 and all(e["inputs"]["clip"] == ["4", 1] for e in encs)
    # KSampler positive → Combine(Combine(original, cat), dog)
    top = by[by["3"]["inputs"]["positive"][0]]
    assert top["class_type"] == "ConditioningCombine"
    inner = by[top["inputs"]["conditioning_1"][0]]
    assert inner["class_type"] == "ConditioningCombine" and inner["inputs"]["conditioning_1"] == ["6", 0]
    with pytest.raises(ValueError):
        regions.add_comfy_regions(_wf(), [{"prompt": ""}], 512, 512)


def test_comfy_inpaint_and_regions_end_to_end(srv):
    s, url = srv()
    job = imagegen.Job("a hat", width=64, height=48, seed=3)
    job.inpaint = {"image": _img(), "mask": _img(colour="white"), "denoise": 0.55, "mask_blur": 6}
    job.regions = {"regions": [{"prompt": "blue sky", "x": 0, "y": 0, "w": 1, "h": .5}], "mode": "comfy"}
    assert imagegen.ComfyUI(url).generate(job, _wf(), poll=0.01) == [PNG]
    wf = s.last_prompt
    kinds = sorted(n["class_type"] for n in wf.values())
    for k in ("LoadImage", "VAEEncode", "SetLatentNoiseMask", "GrowMask", "ConditioningSetArea", "ConditioningCombine"):
        assert k in kinds
    assert wf["3"]["inputs"]["denoise"] == 0.55 and wf[wf["3"]["inputs"]["latent_image"][0]]["class_type"] == "SetLatentNoiseMask"
    assert len(s.uploads) == 1 and b'filename="pm_inpaint_' in s.uploads[0]


def test_comfy_masked_png_alpha():
    _qt()
    from PySide6.QtGui import QColor, QImage, QPainter
    from promptmaker.inpaintcanvas import png_bytes
    m = QImage(64, 48, QImage.Format_RGB32); m.fill(QColor("black"))
    p = QPainter(m); p.fillRect(0, 0, 32, 48, QColor("white")); p.end()
    out = QImage.fromData(regions.comfy_masked_png(_img(), png_bytes(m)))
    assert out.pixelColor(4, 4).alpha() == 0 and out.pixelColor(60, 4).alpha() == 255
    assert regions.mask_coverage(png_bytes(m)) == pytest.approx(0.5, abs=.05)


def test_inpaint_canvas_mask_and_regions():
    _qt()
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage
    from promptmaker.inpaintcanvas import InpaintCanvas
    c = InpaintCanvas(); c.resize(400, 400)
    c.set_image(_img(200, 100))
    assert c.img_size() == (200, 100) and not c.has_mask()
    c.mode = "brush"; c.brush = 20; c._stroke(QPointF(10, 50), QPointF(90, 50))
    assert c.has_mask()
    mask = QImage.fromData(c.mask_png())
    assert (mask.width(), mask.height()) == (200, 100) and mask.pixelColor(50, 50).red() == 255 and mask.pixelColor(150, 50).red() == 0
    c.invert_mask(); mask = QImage.fromData(c.mask_png())
    assert mask.pixelColor(50, 50).red() == 0 and mask.pixelColor(150, 50).red() == 255
    c.clear_mask(); assert not c.has_mask()
    c.add_region("sky", (0, 0, 1, .4)); c.add_region("sea", (0, .6, 1, .4))
    assert c.selected == 1 and [r["prompt"] for r in c.regions] == ["sky", "sea"]
    c.remove_region(0); assert [r["prompt"] for r in c.regions] == ["sea"]
    c.fill_rect_mask(0, .5, 1, .5); assert QImage.fromData(c.mask_png()).pixelColor(100, 90).red() == 255


# ================================================================ 3. library sync
def _filled(tmp_path):
    st = Store(str(tmp_path / "a.db"))
    st.add_history("a castle at dawn", "SDXL"); st.add_favourite("Fav", "a red fox")
    st.save_template("My tpl", "{subject} in rain")
    st.save_character({"name": "Aiko", "appearance": "silver hair", "outfit": "kimono"}); st.save_style({"name": "Ink", "tags": "ink wash"})
    st.save_video_prompt("Fox", "wan22", "A red fox trots", "", {"camera": "Tracking"})
    st.set("theme", "light"); st.set("openai_api_key", "sk-abcdefghijklmnop1234"); st.set("img_url:a1111", "http://x:7860")
    st.set("some_setting", "sk-abcdefghijklmnopqrstu")  # a secret-looking value under an innocent name
    lib = wildcards.WildcardLib(str(tmp_path / "wc_a")); lib.save("hair", ["red hair", "blue hair"]); lib.save("authors/list", ["x"])
    return st, lib


def test_export_never_contains_secrets(tmp_path):
    st, lib = _filled(tmp_path)
    keys = KeyStore(str(tmp_path), use_keyring=False); keys.set("openai", "sk-REALKEYshouldneverleave123"); keys.set("github_gist_token", "ghp_secret123456789")
    b = sync.build(st, lib)
    blob = json.dumps(b)
    for secret in ("sk-REALKEY", "ghp_secret", "sk-abcdefghijklmnop", "openai_api_key"):
        assert secret not in blob
    assert b["settings"]["theme"] == "light" and b["settings"]["img_url:a1111"] == "http://x:7860"
    assert "schema_version" not in b["settings"] and "authors/list.txt" in b["wildcards"]
    assert sync.counts(b)["characters"] == 1 and sync.counts(b)["video_prompts"] == 1
    for fmt in ("zip", "json"):
        path = str(tmp_path / f"lib.{fmt}"); sync.export_file(path, b)
        raw = open(path, "rb").read() if fmt == "json" else b"".join(zipfile.ZipFile(path).read(n) for n in zipfile.ZipFile(path).namelist())
        assert b"sk-REALKEY" not in raw and b"ghp_secret" not in raw and b"sk-abcdefghij" not in raw
        assert sync.read_file(path)["wildcards"]["hair.txt"] == "red hair\nblue hair\n"


def test_import_merge_replace_and_duplicates(tmp_path):
    st, lib = _filled(tmp_path)
    path = str(tmp_path / "lib.zip"); sync.export_file(path, sync.build(st, lib))
    b = sync.read_file(path)
    dst = Store(str(tmp_path / "b.db")); dlib = wildcards.WildcardLib(str(tmp_path / "wc_b"))
    dst.save_character({"name": "Aiko", "appearance": "black hair"}); dst.add_history("mine only")
    dlib.save("hair", ["green hair"])
    r = sync.apply(dst, b, "merge", "skip", dlib)
    assert dst.character("Aiko")["appearance"] == "black hair" and dlib.get("hair") == ["green hair"]
    assert {h[2] for h in dst.history()} == {"mine only", "a castle at dawn"} and dst.style("Ink") and dlib.get("authors/list") == ["x"]
    assert dst.video_prompts()[0]["settings"] == {"camera": "Tracking"} and dst.get("theme") == "light"
    assert r["skipped"] >= 2
    again = sync.apply(dst, b, "merge", "skip", dlib)  # importing twice adds nothing
    assert again["added"] == 0 and len(dst.history()) == 2
    sync.apply(dst, b, "merge", "rename", dlib)
    assert dst.character("Aiko (2)")["appearance"] == "silver hair" and dlib.get("hair_2") == ["red hair", "blue hair"]
    sync.apply(dst, b, "merge", "overwrite", dlib)
    assert dst.character("Aiko")["appearance"] == "silver hair" and dlib.get("hair") == ["red hair", "blue hair"]
    sync.apply(dst, b, "replace", "overwrite", dlib)
    assert [c["name"] for c in dst.characters()] == ["Aiko"] and [h[2] for h in dst.history()] == ["a castle at dawn"]
    assert dlib.get("hair_2") == [] and dst.get("openai_api_key") is None
    with pytest.raises(sync.SyncError):
        sync.validate({"format": "something else"})


def test_status_logic():
    assert sync.status(100, 100, 100) == "in_sync"
    assert sync.status(200, 100, 100) == "push"
    assert sync.status(100, 200, 100) == "pull"
    assert sync.status(200, 300, 100) == "conflict"


def test_gist_push_pull_and_conflict(tmp_path, srv):
    s, url = srv()
    a, alib = _filled(tmp_path)
    client = sync.Gist("ghp_TESTTOKEN1234567890", url)
    assert client.user() == "Kisahime"
    with pytest.raises(sync.SyncError, match="401"):
        sync.Gist("ghp_wrongwrongwrong123", url).user()
    ga = sync.GistSync(a, client, alib)
    r = ga.push(); gid = r["gist_id"]
    assert r["action"] == "created" and a.get("gist_id") == gid
    stored = s.gists[gid][sync.GIST_FILE]
    assert "sk-abcdefghij" not in stored and "TESTTOKEN" not in stored and "Aiko" in stored
    # second computer pulls
    b = Store(str(tmp_path / "b.db")); blib = wildcards.WildcardLib(str(tmp_path / "wc_b")); b.set("gist_id", gid)
    gb = sync.GistSync(b, client, blib)
    assert gb.sync()["action"] == "pulled" and b.character("Aiko") and blib.get("hair") == ["red hair", "blue hair"]
    assert gb.sync()["action"] == "in_sync"
    # B changes → pushes
    time.sleep(1.1); b.save_style({"name": "Neon", "tags": "neon"}); time.sleep(1.1)
    assert gb.sync()["action"] == "pushed"
    # A and the gist both changed → conflict
    time.sleep(1.1); a.save_style({"name": "Pastel", "tags": "pastel"}); time.sleep(1.1)
    with pytest.raises(sync.Conflict):
        ga.sync()
    with pytest.raises(sync.Conflict):
        ga.push()
    r = ga.sync("merge")
    assert r["action"] == "merged" and a.style("Neon") and a.style("Pastel")
    assert "Pastel" in s.gists[gid][sync.GIST_FILE]
    assert [x[1] for x in a.sync_log()][:2] == ["merge", "push"]
    assert any(m == "PATCH" for m, *_ in s.log)


# ================================================================ 4. video prompts
def test_video_frames_rules():
    assert video.frames_for("wan22", 5) == 81 and (video.frames_for("wan22", 7) - 1) % 4 == 0
    assert video.frames_for("wan21", 20) == 81  # clamped to the model maximum
    assert video.frames_for("ltxv", 5) == 121 and (video.frames_for("ltxv", 3.3) - 1) % 8 == 0
    assert video.frames_for("hunyuan", 5) == 121 and video.frames_for("hunyuan", 10) == 129
    assert video.seconds_for("ltxv", 121) == 5.04


def test_video_compose_structure_per_model():
    f = {"subject": "a red fox", "action": "trots through snow", "scene": "a birch forest at dawn", "camera": "Tracking",
         "motion": "Natural", "shot": "Medium shot", "lighting": "soft golden backlight", "style": "cinematic, 35mm film"}
    wan = video.compose("wan22", f)
    assert wan.startswith("A red fox trots through snow. Setting: a birch forest at dawn.") and "tracking shot following the subject" in wan
    ltx = video.compose("ltxv", f)
    assert ltx.startswith("A red fox trots through snow.") and "The lighting is soft golden backlight" in ltx
    hy = video.compose("hunyuan", f)
    assert hy.startswith("a red fox, trots through snow, ") and "." not in hy.replace("35mm", "")
    assert video.compose("wan22", {"subject": "", "camera": "My own move"}) == "My own move."
    assert not video.MODELS["hunyuan"]["negative"] and video.MODELS["wan22"]["default_negative"]


def test_video_writer_via_ollama(srv):
    s, url = srv()
    s.chat_reply = "Here's your prompt:\n\"A red fox trots through fresh snow as the camera tracks alongside.\""
    msgs = video.writer_messages("ltxv", {"subject": "a fox", "camera": "tracking shot", "duration": "5"}, "fox in snow")
    out = video.clean_output("".join(providers.make("ollama", url).stream_chat("llama3.2", msgs)))
    assert out == "A red fox trots through fresh snow as the camera tracks alongside."
    sysmsg = s.last_chat["messages"][0]["content"]
    assert "LTX-Video" in sysmsg and "5 seconds" in sysmsg and "chronological" in sysmsg
    assert "- camera: tracking shot" in s.last_chat["messages"][1]["content"]
    assert video.clean_output("<prompt>x y</prompt>") == "x y"


def test_video_check_warnings():
    assert any("No camera" in w for w in video.check("wan22", "a fox " * 40))
    assert any("Short" in w for w in video.check("ltxv", "a fox walks, camera pans"))
    assert any("Long" in w for w in video.check("hunyuan", "fox camera " * 120))


# ================================================================ storage migration
def test_schema_4_migration_from_v3_db(tmp_path):
    p = str(tmp_path / "old.db")
    db = sqlite3.connect(p)
    db.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);"
                     "INSERT INTO settings VALUES('schema_version','3');"
                     "CREATE TABLE characters(id INTEGER PRIMARY KEY, name TEXT UNIQUE, appearance TEXT DEFAULT '', outfit TEXT DEFAULT '',"
                     " lora TEXT DEFAULT '', lora_weight REAL DEFAULT 0.8, ref_image TEXT DEFAULT '', notes TEXT DEFAULT '', ts REAL);"
                     "INSERT INTO characters(name) VALUES('Old');")
    db.commit(); db.close()
    st = Store(p)
    assert st.schema_version() == 4 and st.character("Old")
    vid = st.save_video_prompt("x", "ltxv", "p", "n", {"a": 1})
    assert st.video_prompts()[0]["id"] == vid
    st.log_sync("push", "gist:1", "ok"); assert st.sync_log()[0][1:4] == ("push", "gist:1", "ok")


# ================================================================ UI
@pytest.fixture()
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTMAKER_NO_NET", "1"); monkeypatch.setenv("PROMPTMAKER_NO_TOUR", "1")
    monkeypatch.setenv("PROMPTMAKER_NO_DIALOGS", "1")
    _qt()
    from promptmaker.app import MainWindow
    w = MainWindow(Store(str(tmp_path / "t.db")), str(tmp_path)); w.resize(1280, 800); w.show()
    from PySide6.QtWidgets import QApplication
    t = time.time()
    while time.time() - t < 0.3:  # let the start-up model refresh finish before tests swap in a fake provider
        QApplication.processEvents(); time.sleep(0.02)
    for wk in getattr(w, "_workers", []):
        wk.wait(3000)
    QApplication.processEvents()
    yield w
    w.close()


def _wait(win, timeout=5):
    from PySide6.QtWidgets import QApplication
    t = time.time()
    while win.genq.isRunning() and time.time() - t < timeout:
        QApplication.processEvents(); time.sleep(0.02)
    QApplication.processEvents()


class FakeProvider:
    pid, kind, notes = "fake", "ollama", {}

    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        self.seen.append(messages); yield self.reply

    def list_models(self):
        return ["llama3.2"]


def _wait_worker(pred, timeout=5):
    from PySide6.QtWidgets import QApplication
    t = time.time()
    while not pred() and time.time() - t < timeout:
        QApplication.processEvents(); time.sleep(0.02)


def test_ui_v4_pages_present(win):
    from promptmaker import __version__
    from promptmaker.app import NAV
    assert __version__ == "4.1.5"
    names = [n for _, n in NAV]
    for name in ("Inpaint & Regions", "Wildcards", "Video", "Library sync"):
        win.go(name); assert names[win.stack.currentIndex()] == name
    assert win.store.schema_version() == 4


def test_ui_wildcards_page(win, srv):
    win.go("Wildcards")
    win.wc_name.setText("hair"); win.wc_edit.setPlainText("red hair\nblue hair\nsilver hair"); win.wc_save()
    assert win.wc_lib.get("hair") == ["red hair", "blue hair", "silver hair"]
    win.wc_prompt.setPlainText("1girl, __hair__, {smiling|serious}, __nothing__"); win.wc_seed.setValue(5)
    one = win.wc_preview()
    assert one == win.wc_preview() and "__nothing__" in one and "nothing" in win.wc_missing.text()
    win.wc_n.setValue(4); res = win.wc_batch()
    assert len(res) == 4 and win.wc_out.count() == 4 and res[0][0] == 5
    # presets stay fixed
    cid = win.store.save_character({"name": "Aiko", "appearance": "red eyes"}); win.store.set("presets_active_chars", [cid])
    win.wc_presets.setChecked(True); win.wc_prompt.setPlainText("__hair__")
    assert all("red eyes" in p for _, p in win.wc_batch())
    # AI list
    win.provider = FakeProvider("1. misty harbour\n2. desert ruins\n3. crystal cave")
    win.model.clear(); win.model.addItem("llama3.2"); win.model.setCurrentIndex(0)
    win.wc_name.setText(""); win.wc_desc.setText("fantasy locations"); win.wc_ai_n.setValue(3)
    wk = win.wc_ai_generate(); wk.wait(3000); _wait_worker(lambda: win.wc_edit.toPlainText().startswith("misty"))
    assert win.wc_edit.toPlainText() == "misty harbour\ndesert ruins\ncrystal cave" and win.wc_name.text() == "fantasy_locations"
    # generate images: the queued prompts are the expanded ones, with matching seeds
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.wc_presets.setChecked(False); win.wc_prompt.setPlainText("a __hair__ girl"); win.wc_n.setValue(2); win.wc_batch()
    jobs = win.wc_generate()
    assert [j.seed for j in jobs] == [win.wc_out.item(i).data(0x0101) for i in range(2)]  # same seed as the preview row
    _wait(win)
    assert len(jobs) == 2 and all("__" not in j.prompt and j.prompt.endswith("hair girl") for j in jobs)
    assert "__" not in s.last_payload["prompt"]


def test_ui_make_job_expands_wildcards_with_seed(win, srv):
    _, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.wc_lib.save("animal", ["cat", "dog", "owl", "fox"])
    a = win.make_job("a __animal__ in {rain|snow}", seed=42)[0]
    b = win.make_job("a __animal__ in {rain|snow}", seed=42)[0]
    assert a.prompt == b.prompt and "__" not in a.prompt and a.seed == 42
    assert win.make_job("{masterpiece}, a cat", seed=1)[0].prompt == "{masterpiece}, a cat"
    win.store.set("wildcards_auto", False)
    assert win.make_job("a __animal__", seed=1)[0].prompt == "a __animal__"


def test_ui_inpaint_and_regions(win, srv, tmp_path):
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.store.set("img_checkpoint:a1111", "anima.safetensors")
    win.go("Inpaint & Regions")
    assert win.ip_inpaint() is None  # no image yet
    f = tmp_path / "base.png"; f.write_bytes(_img(128, 96, "blue")); win.ip_open(str(f))
    assert win.ip_inpaint() is None  # no mask yet
    win.ip_canvas.fill_rect_mask(.25, .25, .5, .5); win.ip_prompt.setPlainText("a golden crown"); win.ip_denoise.setValue(.5)
    job = win.ip_inpaint(); _wait(win)
    assert job.inpaint and s.last_endpoint == "/sdapi/v1/img2img" and s.last_payload["denoising_strength"] == .5
    assert (s.last_payload["width"], s.last_payload["height"]) == (128, 96)
    assert s.last_payload["override_settings"]["sd_model_checkpoint"] == "anima.safetensors"
    # regions without Forge Couple → explains the extension, nothing sent
    win.ip_blank(); win.ip_canvas.add_region("a cat", (0, 0, .5, 1)); win.ip_canvas.add_region("a dog", (.5, 0, .5, 1))
    n = len(s.log)
    assert win.rg_generate() is None and "sd-forge-couple" in win.rg_status.text()
    assert not [x for x in s.log[n:] if x[0] == "POST"]
    assert "(a cat) on the left" in win.rg_copy_plain()
    job = win.rg_generate("plain"); _wait(win)
    assert "(a dog) on the right" in s.last_payload["prompt"] and s.last_endpoint == "/sdapi/v1/txt2img"
    # with Forge Couple
    s2, url2 = srv("couple"); win.store.set("img_url:a1111", url2)
    job = win.rg_generate(); _wait(win)
    assert job.regions["mode"] == "forge couple" and "forge couple" in s2.last_payload["alwayson_scripts"]
    # rows in the list follow the canvas
    win.ip_canvas.select(0); win.rg_prompt.setText("a tabby cat"); win._rg_edit()
    assert win.ip_canvas.regions[0]["prompt"] == "a tabby cat" and win.rg_list.item(0).text().startswith("1. a tabby cat")


def test_ui_video_page(win):
    win.go("Video")
    win.vd_model.setCurrentIndex(win.vd_model.findData("ltxv"))
    assert "121 frames" in win.vd_frames.text() and win.vd_size.itemText(0) == "768x512"
    win.vd["subject"].setText("a red fox"); win.vd["action"].setText("trots through snow"); win.vd_camera.setCurrentText("Orbit")
    text = win.vd_build()
    assert text.startswith("A red fox trots through snow.") and "orbits" in text and "words" in win.vd_warn.text()
    win.vd_name.setText("Fox"); vid = win.vd_save()
    assert win.store.video_prompts()[0]["id"] == vid and win.vd_saved.count() == 1
    win.provider = FakeProvider("Sure:\n<prompt>A fox in snow, the camera orbits slowly.</prompt>")
    win.model.clear(); win.model.addItem("llama3.2"); win.model.setCurrentIndex(0)
    win.vd_write(); _wait_worker(lambda: win.vd_out.toPlainText().startswith("A fox in snow"))
    assert win.vd_out.toPlainText() == "A fox in snow, the camera orbits slowly."
    assert "LTX-Video" in win.provider.seen[0][0]["content"]
    win.vd_model.setCurrentIndex(win.vd_model.findData("hunyuan")); assert not win.vd_neg.isEnabled()
    win._vd_load(win.vd_saved.item(0)); assert win.vd_model.currentData() == "ltxv" and win.vd_camera.currentText() == "Orbit"
    cid = win.store.save_character({"name": "Aiko", "appearance": "silver hair"}); win.store.set("presets_active_chars", [cid])
    win.vd_use_char.setChecked(True); assert win.vd["subject"].text().startswith("Aiko")


def test_ui_library_sync(win, srv, tmp_path):
    win.store.save_style({"name": "Ink", "tags": "ink"}); win.wc_lib.save("hair", ["red"])
    win.keys.set("openai", "sk-REALKEYshouldneverleave123")
    win.go("Library sync")
    path = win.sy_export(str(tmp_path / "out.zip"))
    raw = b"".join(zipfile.ZipFile(path).read(n) for n in zipfile.ZipFile(path).namelist())
    assert b"sk-REALKEY" not in raw and b"Ink" in raw
    win.store.delete_style(win.store.style("Ink")["id"]); win.wc_lib.delete("hair")
    st = win.sy_import(path)
    assert st["added"] >= 2 and win.store.style("Ink") and win.wc_lib.get("hair") == ["red"] and "Imported" in win.sy_import_res.text()
    # gist
    s, url = srv()
    win.store.set("gist_api", url); win.sy_token.setText("ghp_TESTTOKEN1234567890"); win.sy_save_token()
    assert win.sy_token.text() == "" and win.keys.get("github_gist_token") == "ghp_TESTTOKEN1234567890"
    r = win.sy_run("push", wait=True)
    gid = r["gist_id"]
    assert r["action"] == "created" and win.sy_gist.text() == gid and "TESTTOKEN" not in s.gists[gid][sync.GIST_FILE]
    assert "sk-REALKEY" not in s.gists[gid][sync.GIST_FILE]
    assert win.sy_run("sync", wait=True)["action"] == "in_sync"
    # remote changed elsewhere and local changed → conflict prompt (no dialog in tests)
    remote = json.loads(s.gists[gid][sync.GIST_FILE]); remote["modified"] = time.time() + 50
    remote["styles"].append({"name": "Remote", "tags": "r", "negative": ""}); s.gists[gid][sync.GIST_FILE] = json.dumps(remote)
    time.sleep(1.1); win.store.save_style({"name": "Local", "tags": "l"}); time.sleep(1.1)
    assert win.sy_run("sync", wait=True) == {"action": "conflict"} and "Conflict" in win.sy_status.text()
    assert win.sy_run("sync", "merge", wait=True)["action"] == "merged" and win.store.style("Remote") and win.store.style("Local")
    assert win.sy_log.count() >= 3


def test_unload_ollama_before_image(monkeypatch):
    import json as _j
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from promptmaker import ollama
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = _j.dumps({"models": [{"name": "qwen3:8b"}, {"name": "llava:7b"}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            d = _j.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(d); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    assert ollama.unload_all(base) == ["qwen3:8b", "llava:7b"]
    assert calls == [{"model": "qwen3:8b", "keep_alive": 0}, {"model": "llava:7b", "keep_alive": 0}]
    assert ollama.unload_all("http://127.0.0.1:9") == []
    srv.shutdown()
    hit = []
    monkeypatch.setattr(imagegen, "BEFORE_GENERATE", [lambda: hit.append(1), lambda: 1 / 0])
    imagegen._before_generate()
    assert hit == [1]


def test_hires_fix_payload():
    job = imagegen.Job("a cat", seed=1, cfg=5)
    job.hires = {"scale": 2, "upscaler": "R-ESRGAN 4x+ Anime6B", "steps": 12, "denoise": 0.35}
    p = imagegen.A1111("http://x").payload(job)
    assert p["enable_hr"] is True and p["hr_scale"] == 2.0 and p["hr_upscaler"] == "R-ESRGAN 4x+ Anime6B"
    assert p["hr_second_pass_steps"] == 12 and p["denoising_strength"] == 0.35
    assert p["hr_additional_modules"] == ["Use same choices"]
    job.inpaint = {"image": b"x", "mask": b"y"}
    assert "enable_hr" not in imagegen.A1111("http://x").payload(job)
    job2 = imagegen.Job("a cat", seed=1)
    assert "enable_hr" not in imagegen.A1111("http://x").payload(job2)


def test_upscalers_on_forge_backend():
    assert hasattr(imagegen.A1111("http://x"), "upscalers")
    assert imagegen.A1111("http://127.0.0.1:9").upscalers()  # fallback list when Forge is offline


def test_sampler_scheduler_pickers(win, srv):
    from promptmaker import imagegen
    _, url = srv()
    assert win.img_sampler.currentText() == imagegen.PROFILE_DEFAULT
    assert win.img_scheduler.findText("Karras") >= 0
    win.img_sampler.setCurrentText("DPM++ 2M SDE"); win.img_scheduler.setCurrentText("Karras")
    win._img_save()
    assert win.store.get("img_sampler") == "DPM++ 2M SDE" and win.store.get("img_scheduler") == "Karras"
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    job = win.make_job("a cat")[0]
    assert job.sampler == "DPM++ 2M SDE" and job.scheduler == "Karras"
    assert imagegen.A1111(url).payload(job)["scheduler"] == "Karras"
    win.store.set("img_sampler", None); win.store.set("img_scheduler", None)
    win.store.set("profile_image_settings", {})  # 4.1: Save also remembers them per target model
    job = win.make_job("a cat")[0]
    assert job.sampler != "DPM++ 2M SDE" and job.scheduler != "Karras"
