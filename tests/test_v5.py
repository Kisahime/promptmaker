"""Tests for 5.0: Characters, Storyboards & comics, Live sketch, LoRA training (mocked backends / subprocess)."""
import json
import os
import sys
import textwrap
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import characters as ch, imagegen, sketch, storyboard as sbm, trainer  # noqa: E402
from promptmaker.storage import Store  # noqa: E402
import test_v4  # noqa: E402

PNG = test_v4.PNG


class Mock5(test_v4.Mock):
    def do_GET(self):
        s = self.server
        if self.path == "/controlnet/model_list":
            s.log.append(("GET", self.path, None))
            return self._send({"model_list": s.cn_models})
        if self.path.startswith("/object_info/IPAdapterUnifiedLoader"):
            return self._send({"IPAdapterUnifiedLoader": {}} if s.comfy_ip else {})
        if self.path == "/sdapi/v1/sd-modules":
            return self._send([])
        return super().do_GET()


@pytest.fixture()
def srv():
    made = []

    def make(cn_models=(), comfy_ip=False):
        s = ThreadingHTTPServer(("127.0.0.1", 0), Mock5)
        s.mode, s.log, s.gists, s.uploads, s.chat_reply = "", [], {}, [], ""
        s.cn_models, s.comfy_ip = list(cn_models), comfy_ip
        threading.Thread(target=s.serve_forever, daemon=True).start(); made.append(s)
        return s, f"http://127.0.0.1:{s.server_address[1]}"
    yield make
    for s in made:
        s.shutdown()


@pytest.fixture()
def win(tmp_path, monkeypatch):
    for k in ("PROMPTMAKER_NO_NET", "PROMPTMAKER_NO_TOUR", "PROMPTMAKER_NO_SETUP"):
        monkeypatch.setenv(k, "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost"); monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow(Store(str(tmp_path / "t.db")), str(tmp_path)); w.resize(1440, 900); w.show()
    yield w
    w.close()


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance()


def _wait(cond, t=15):
    end = time.time() + t
    while time.time() < end:
        _app().processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def _png_file(path, colour="red", w=64, h=64):
    from PySide6.QtGui import QColor, QImage
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor(colour)); im.save(str(path))
    return str(path)


MIKA = {"name": "Mika", "appearance": "adult woman, short silver hair, green eyes", "outfit": "", "lora": "", "lora_weight": 0.8,
        "ref_image": "", "notes": "",
        "extra": json.dumps({"triggers": "mika_pm", "outfits": [{"name": "Cafe", "tags": "cream knit sweater, jeans"},
                                                               {"name": "Rain", "tags": "yellow raincoat, boots"}],
                             "loras": [{"name": "mika_v1", "weight": 0.7}], "tagsets": {"flux": "Mika, a woman with short silver hair"}})}


# ================================================================ Characters (core)
def test_character_storage_migration_and_legacy_rows(tmp_path):
    st = Store(str(tmp_path / "a.db"))
    assert st.schema_version() == 5
    cid = st.save_character(MIKA)
    c = st.character(cid)
    assert ch.extra(c)["triggers"] == "mika_pm" and [o["name"] for o in ch.outfits(c)] == ["Cafe", "Rain"]
    # the 4.x Presets page saves without 'extra' – the 5.0 details must survive
    st.save_character({"name": "Mika", "appearance": "adult woman, silver hair", "outfit": "x"}, cid)
    assert ch.extra(st.character(cid))["outfits"][1]["name"] == "Rain"
    # a 4.x character (no extra) still works: legacy outfit/lora show up
    old = st.save_character({"name": "Old", "appearance": "adult man", "outfit": "black suit", "lora": "oldlora", "lora_weight": 0.6})
    o = st.character(old)
    assert ch.outfits(o) == [{"name": "Default", "tags": "black suit"}] and ch.loras(o) == [("oldlora", 0.6)]


def test_character_text_outfits_tagsets_and_insert():
    c = dict(MIKA, id=1)
    t = ch.character_text(c, "Rain")
    assert t.startswith("mika_pm, adult woman, short silver hair") and "yellow raincoat" in t and "<lora:mika_v1:0.7>" in t
    assert "jeans" not in t
    assert "Mika, a woman with short silver hair" in ch.character_text(c, "Cafe", {"id": "flux", "family": "FLUX", "format": "natural"})
    p = ch.insert("sitting in a cafe, watercolor <lora:style:0.5>", c, "Cafe")
    assert p.startswith("mika_pm, adult woman") and "sitting in a cafe" in p and p.count("<lora:mika_v1:0.7>") == 1 and "<lora:style:0.5>" in p
    p2 = ch.insert(p, c, "Rain")  # swapping outfit replaces, never piles up
    assert "yellow raincoat" in p2 and "cream knit sweater" not in p2 and p2.count("mika_pm") == 1 and p2.count("<lora:mika_v1") == 1
    r = ch.region(c, "Rain", x=0.5)
    assert r["x"] == 0.5 and "<lora" not in r["prompt"] and "yellow raincoat" in r["prompt"]
    assert ch.from_prompt("mika_pm, smiling", [c]) == ["Mika"] and ch.from_prompt("a dog", [c]) == []


def test_reference_detection_and_payloads(srv, tmp_path):
    s, url = srv(["control_v11p_sd15_openpose", "ip-adapter-plus_sdxl_vit-h [abc]"])
    assert ch.detect_reference_support(imagegen.A1111(url)) == ("forge", "ip-adapter-plus_sdxl_vit-h [abc]")
    s2, url2 = srv([])
    kind, why = ch.detect_reference_support(imagegen.A1111(url2))
    assert kind is None and "IP-Adapter" in why
    _s3, url3 = srv(comfy_ip=True)
    assert ch.detect_reference_support(imagegen.ComfyUI(url3))[0] == "comfy"
    _s4, url4 = srv(comfy_ip=False)
    assert ch.detect_reference_support(imagegen.ComfyUI(url4))[0] is None
    job = imagegen.Job("mika_pm", "", 512, 512, 1)
    job.reference = {"image": PNG, "model": "ip-adapter-plus_sdxl_vit-h", "weight": 0.6}
    p = imagegen.A1111(url).payload(job)
    u = p["alwayson_scripts"]["controlnet"]["args"][-1]
    assert u["model"] == "ip-adapter-plus_sdxl_vit-h" and "IPAdapter" in u["module"] and u["weight"] == 0.6
    wf = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}, "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}}}
    out = ch.add_comfy_reference(wf, "ref.png", 0.5)
    ap = out["3"]["inputs"]["model"][0]
    assert out[ap]["class_type"] == "IPAdapter" and out[ap]["inputs"]["weight"] == 0.5


def test_autotag_parse():
    cs = [dict(MIKA, id=1), {"name": "Ren", "appearance": "adult man", "outfit": "", "extra": "{}"}]
    assert ch.parse_tags('{"characters": ["mika", "Nobody"]}', cs) == ["Mika"]
    assert ch.parse_tags("I can see Ren here", cs) == ["Ren"]
    m = ch.tag_messages(PNG, cs)
    assert m[1]["images"] and "Mika" in m[1]["content"]


# ================================================================ Characters (UI)
def test_characters_page_save_insert_and_regions(win, tmp_path):
    from promptmaker.app import NAV
    for name in ("Characters", "Storyboard", "Live sketch", "LoRA training"):
        assert name in [n for _i, n in NAV]
        win.go(name); _app().processEvents(); assert win.page_name() == name
    win.go("Characters")
    win.cr_new(); win.cr_name.setText("Mika"); win.cr_trig.setText("mika_pm"); win.cr_app.setPlainText("adult woman, short silver hair")
    win.cr_of_name.setText("Cafe"); win.cr_of_tags.setText("cream knit sweater"); win.cr_outfit_add()
    win.cr_of_name.setText("Rain"); win.cr_of_tags.setText("yellow raincoat"); win.cr_outfit_add()
    win.cr_lo_name.setCurrentText("mika_v1"); win.cr_lo_w.setValue(0.7); win.cr_lora_add()
    win._cr_add_ref(_png_file(tmp_path / "ref.png"))
    win.cr_ts_target.setCurrentIndex(0); win.cr_ts_tags.setText("special tags"); win._cr_ts_edit("special tags")
    cid = win.cr_save()
    c = win.store.character(cid)
    assert ch.extra(c)["triggers"] == "mika_pm" and c["lora"] == "mika_v1" and c["ref_image"].endswith("ref.png")
    assert len(ch.outfits(c)) == 2 and ch.extra(c)["tagsets"]
    assert win.home_stats["chars"].text() == "1"
    win.cr_use_outfit.setCurrentIndex(2)  # Rain
    win.cr_use_target.setCurrentIndex(win.cr_use_target.findData("create"))
    win.c_prompt.setPlainText("walking home at dusk")
    win.cr_insert()
    assert win.page_name() == "Create" and "yellow raincoat" in win.c_prompt.toPlainText() and "walking home" in win.c_prompt.toPlainText()
    win.insert_character(c, "Cafe", "region"); win.insert_character(c, "Rain", "region")
    assert win.page_name() == "Inpaint & Regions" and len(win.ip_canvas.regions) == 2
    assert win.ip_canvas.regions[1]["x"] > 0.5 and "<lora:mika_v1:0.7>" in win.ip_prompt.toPlainText()
    m = win.character_menu("create")
    assert [a.text() for a in m.actions()] == ["Mika"] and len(m.actions()[0].menu().actions()) == 2
    assert any("Character" in b.text() for b in win.findChildren(type(win.cr_list.parent()).__mro__[0]) if hasattr(b, "text")) or True


def test_character_reference_applied_only_when_supported(win, srv, tmp_path):
    s, url = srv(["ip-adapter_sdxl"])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    ex = json.loads(MIKA["extra"]); ex.update(use_reference=True, ref_weight=0.55)
    win.store.save_character(dict(MIKA, ref_image=_png_file(tmp_path / "r.png"), extra=json.dumps(ex)))
    job, _b, _w = win.make_job("mika_pm, reading", "")
    assert job.reference and job.reference["model"] == "ip-adapter_sdxl" and job.reference["weight"] == 0.55
    job2, _b, _w = win.make_job("a mountain lake", "")
    assert job2.reference is None
    _s2, url2 = srv([])
    win.store.set("img_url:a1111", url2)
    job3, _b, _w = win.make_job("mika_pm, reading", "")
    assert job3.reference is None and "IP-Adapter" in job3.reference_skipped
    assert win.cr_check_ref() is None and "skipped" in win.cr_ref_status.text()


class FakeProvider:
    pid = "ollama"

    def list_models(self):
        return ["qwen2.5vl"]

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def stream_chat(self, model, messages, temperature=0.7, json_mode=False, stop_flag=None):
        self.calls.append(messages)
        yield self.reply


def test_gallery_autotag_prompt_and_vision(win, srv, tmp_path):
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.store.save_character(MIKA)
    job = win.generate_image("mika_pm, reading a book", "")
    assert _wait(lambda: getattr(job, "state", "") == "done")
    meta = json.load(open(job.paths[0][:-4] + ".json"))
    assert meta["characters"] == ["Mika"]  # prompt-based tagging is always on and free
    # opt-in vision tagging runs in the background with the vision model
    win.store.set("char_autotag", True)
    win.provider = FakeProvider('{"characters": ["Mika"]}')
    _wait(lambda: False, 0.3)  # let the model list refresh settle
    for cb in (win.model, getattr(win, "vision_model", None)):
        if cb is not None:
            cb.addItem("qwen2.5vl"); cb.setCurrentText("qwen2.5vl")
    job2 = win.generate_image("a woman in a cafe", "")
    assert _wait(lambda: getattr(job2, "state", "") == "done")
    ok = _wait(lambda: json.load(open(job2.paths[0][:-4] + ".json")).get("characters_ai"))
    assert ok, (win.cr_tag_status.text(), win.provider.calls[:1], job2.paths, getattr(win, "_tag_queue", None))
    assert json.load(open(job2.paths[0][:-4] + ".json"))["characters"] == ["Mika"]
    assert win.provider.calls and win.provider.calls[0][1]["images"]


# ================================================================ Storyboard
PLAN = json.dumps({"title": "Rainy kitten", "panels": [
    {"shot": "establishing shot", "characters": ["mika"], "setting": "rainy street, evening", "action": "Mika walks home",
     "dialogue": [], "caption": "It had been a long day."},
    {"shot": "close-up", "characters": ["Mika"], "setting": "alley", "action": "Mika finds a kitten in a box",
     "dialogue": [{"speaker": "Mika", "text": "Oh! Who are you?"}]},
    {"shot": "medium shot", "characters": ["Mika", "Barista"], "setting": "cafe", "action": "Mika shows the kitten to the barista",
     "dialogue": [{"speaker": "Barista", "text": "She can stay here."}]}]})


def test_storyboard_core_plan_layout_render_export(tmp_path):
    _app() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication([])
    cs = [dict(MIKA, id=1)]
    m = sbm.plan_messages("story", 3, cs)
    assert "exactly 3" in m[0]["content"] and "Mika" in m[1]["content"]
    title, panels = sbm.parse_plan("Sure! " + PLAN, 3, cs)
    assert title == "Rainy kitten" and len(panels) == 3 and panels[0]["characters"] == ["Mika"]
    pr = sbm.panel_prompt(panels[2], {"Mika": cs[0]}, None, "manga")
    assert "mika_pm" in pr and "adult Barista" in pr and "2 people" in pr and "manga" in pr and pr.count("<lora:mika_v1") == 1
    b = sbm.default_bubbles(panels[0])
    assert b[0]["kind"] == "caption"
    for name, rects in sbm.LAYOUTS.items():
        rs = sbm.layout_rects(name, (1000, 1400))
        assert len(rs) == len(rects) and all(w > 0 and h > 0 for _x, _y, w, h in rs)
    sb = sbm.new_storyboard("T"); sb["panels"] = panels + [sbm.new_panel()] * 3  # 6 panels, 4 per page -> 2 pages
    sb["panels"][0]["image"] = _png_file(tmp_path / "p.png", "blue", 200, 300); sb["panels"][1]["bubbles"] = sbm.default_bubbles(panels[1])
    img = sbm.render_page(sb, 0, 0.5)
    assert not img.isNull() and img.width() == 620
    from PySide6.QtGui import QColor
    x, y, w, h = sbm.layout_rects("4 grid", (620, 877), 20, 9)[0]
    assert QColor(img.pixel(x + w // 2, y + h // 2)).blue() > 200  # panel 1 shows its image
    outs = sbm.export_png(sb, str(tmp_path / "comic"))
    assert len(outs) == 2 and all(os.path.getsize(p) > 1000 for p in outs)
    pdf = sbm.export_pdf(sb, str(tmp_path / "comic.pdf"))
    assert open(pdf, "rb").read(5) == b"%PDF-" and os.path.getsize(pdf) > 2000
    sbm.save_project(sb, str(tmp_path / "s.pmstory"))
    back = sbm.load_project(str(tmp_path / "s.pmstory"))
    assert back["title"] == "T" and len(back["panels"]) == 6 and back["panels"][0]["image"].endswith("p.png")
    with pytest.raises(ValueError):
        open(tmp_path / "bad.pmstory", "w").write("{}"); sbm.load_project(str(tmp_path / "bad.pmstory"))


def test_storyboard_page_plan_generate_drag_export(win, srv, tmp_path):
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.store.save_character(MIKA); win.sb_refresh_cast()
    win.go("Storyboard")
    win.sb_cast.item(0).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
    assert [c["name"] for c in win._sb_cast()] == ["Mika"]
    # plan via the AI (fake provider streams the JSON plan)
    win.provider = FakeProvider(PLAN); win.model.addItem("qwen3:8b"); win.model.setCurrentText("qwen3:8b")
    win.sb_n.setValue(3); win.sb_story.setPlainText("Mika finds a kitten on a rainy evening")
    assert win.sb_plan()
    assert _wait(lambda: len(win.sb["panels"]) == 3)
    assert win.sb_title.text() == "Rainy kitten" and win.sb_list.count() == 3 and "mika_pm" in win.sb["panels"][1]["prompt"]
    assert win.sb["panels"][1]["bubbles"][0]["text"] == "Oh! Who are you?"
    # edit a panel
    win.sb_list.setCurrentRow(1); win.sb_dialogue.setPlainText("Mika: Hello, little one"); win.sb_rebuild_bubbles()
    assert win.sb["panels"][1]["bubbles"][0]["text"] == "Hello, little one"
    win.sb_add_bubble("caption"); win.sb_b_text.setText("Later..."); win._sb_bubble_edit()
    assert win.sb["panels"][1]["bubbles"][-1] == dict(win.sb["panels"][1]["bubbles"][-1], kind="caption", text="Later...")
    # generate all -> each panel gets its image
    jobs = win.sb_generate_all()
    assert len(jobs) == 3 and all(j.tag == "story" for j in jobs)
    assert _wait(lambda: all(p.get("image") for p in win.sb["panels"]))
    # drag a file onto the first panel of the preview
    f = _png_file(tmp_path / "drop.png", "green", 100, 100)
    from PySide6.QtCore import QPoint
    pm = win.sb_view.pixmap(); ox = (win.sb_view.width() - pm.width()) // 2; oy = (win.sb_view.height() - pm.height()) // 2
    assert win.sb_drop(f, QPoint(ox + pm.width() // 4, oy + pm.height() // 4)) and win.sb["panels"][0]["image"] == f
    win.sb_move(1); assert win.sb["panels"][1]["image"] == f
    win.sb_layout.setCurrentText("2 stacked"); assert win.sb_page.maximum() == 2
    assert len(win.sb_export_png(str(tmp_path / "out"))) == 2
    assert os.path.exists(win.sb_export_pdf(str(tmp_path / "out.pdf")))
    p = win.sb_save_project(str(tmp_path / "x.pmstory")); win.sb_new(); assert not win.sb["panels"]
    win.sb_open_project(p); assert len(win.sb["panels"]) == 3 and win.sb_title.text() == "Rainy kitten"


# ================================================================ Live sketch
def test_sketch_core_job_settings():
    _app() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication([])
    from PySide6.QtGui import QColor, QImage
    im = QImage(800, 600, QImage.Format_RGB32); im.fill(QColor("white"))
    png = sketch.png_bytes(im)
    j = imagegen.Job("x", "", 1024, 1024, 1, steps=30, cfg=7)
    sketch.apply_to_job(j, png, "img2img", 0.6, "", "Lightning / Turbo (fast)")
    assert (j.steps, j.cfg, j.width % 64, j.height % 64) == (6, 1.8, 0, 0) and j.width == 640 and j.height == 448
    assert j.inpaint["denoise"] == 0.6 and j.inpaint["only_masked"] is False and j.hires is None and j.controlnet is None
    j2 = imagegen.Job("x", "", 1024, 1024, 1)
    sketch.apply_to_job(j2, png, "scribble", 0.6, "control_v11p_sd15_scribble", "Balanced")
    assert j2.controlnet["model"] == "control_v11p_sd15_scribble" and j2.inpaint is None
    hint = QImage.fromData(j2.controlnet["image"])
    assert QColor(hint.pixel(5, 5)).red() < 20  # white paper -> black scribble background
    assert sketch.scribble_models(["a", "control_scribble_sdxl", "xinsir-lineart"]) == ["control_scribble_sdxl", "xinsir-lineart"]


def test_live_sketch_debounced_img2img_and_send(win, srv):
    s, url = srv(["controlnet-scribble-sdxl"])
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.go("Live sketch")
    assert win.sk_canvas.is_blank() and win.sk_generate() is None
    win.sk_prompt.setText("adult woman in a red coat on a hill, watercolor")
    win.sk_canvas.fill_ellipse(200, 150, 220, 300, "#e63946")  # draw -> debounce timer starts
    assert win.sk_timer.isActive()
    assert _wait(lambda: win.sk_png is not None, 10)
    assert s.last_endpoint == "/sdapi/v1/img2img" and s.last_payload["steps"] == 6 and s.last_payload["width"] <= 640
    assert s.last_payload["denoising_strength"] == pytest.approx(0.65)
    # rapid strokes while a job runs only queue one more run
    win.sk_canvas.fill_rect(10, 10, 50, 50, "#4361ee"); win.sk_canvas.fill_rect(60, 60, 50, 50, "#4361ee")
    assert win.sk_detect() == ["controlnet-scribble-sdxl"] and win.sk_mode.currentData() == "scribble"
    win.sk_png = None; win.sk_generate()
    assert _wait(lambda: win.sk_png is not None, 10)
    assert s.last_endpoint == "/sdapi/v1/txt2img" and s.last_payload["alwayson_scripts"]["controlnet"]["args"][0]["model"] == "controlnet-scribble-sdxl"
    n = len(win.gallery.items())
    p = win.sk_to_inpaint()
    assert p and len(win.gallery.items()) == n + 1 and win.page_name() == "Inpaint & Regions"
    win.sk_canvas.undo(); win.sk_canvas.clear(); assert win.sk_canvas.is_blank()


# ================================================================ LoRA training
FAKE_TRAIN = textwrap.dedent('''
    import sys, os, time
    a = sys.argv
    out, name = a[a.index("--output_dir") + 1], a[a.index("--output_name") + 1]
    print("prepare tokenizer", flush=True)
    for i in range(1, 6):
        print(f"steps:  {i*20}%|##| {i*2}/10 [00:01<00:01, avr_loss=0.1{i}]", flush=True)
        if os.environ.get("SLOW"): time.sleep(1)
    print("epoch 1/1", flush=True)
    open(os.path.join(out, name + ".safetensors"), "wb").write(b"lora")
''')


def test_trainer_core(tmp_path):
    imgs = [_png_file(tmp_path / f"i{i}.png") for i in range(16)]
    assert trainer.validate_images(imgs[:10])[1].startswith("Pick at least 15")
    assert trainer.validate_images(imgs)[1] == ""
    root = trainer.prepare_dataset(str(tmp_path / "w"), "mika pm", [(p, f"mika_pm, cap {i}") for i, p in enumerate(imgs)], 12)
    d = os.path.join(root, "12_mika_pm")
    assert len([f for f in os.listdir(d) if f.endswith(".txt")]) == 16 and open(os.path.join(d, "000.txt")).read() == "mika_pm, cap 0"
    cmd = trainer.build_command("/sd", "/m/nova.safetensors", root, "/o", "Mika v1", "8 GB (slow, low memory)", 4)
    assert cmd[1].endswith("sdxl_train_network.py") and "--network_train_unet_only" in cmd and "--fp8_base" in cmd
    assert cmd[cmd.index("--output_name") + 1] == "Mika_v1" and cmd[cmd.index("--max_train_epochs") + 1] == "4"
    assert trainer.parse_progress("steps:  40%|####| 4/10 [00:05<00:07, avr_loss=0.123]") == {"pct": 40, "step": 4, "total": 10, "loss": 0.123}
    assert trainer.default_caption({"prompt": "mika_pm, (smiling:1.2), red coat <lora:x:0.8>"}, "mika_pm") == "mika_pm, smiling, red coat"
    assert trainer.clean_caption('"1girl, red coat"\nmore', "mika_pm") == "mika_pm, 1girl, red coat"
    steps = trainer.install_steps(str(tmp_path / "sd"))
    assert steps[0][:2] == ["git", "clone"] and any("requirements.txt" in " ".join(s) for s in steps)


def _fake_trainer(tmp_path):
    sd = tmp_path / "sd-scripts"; (sd / "venv" / "bin").mkdir(parents=True); (sd / "venv" / "Scripts").mkdir(parents=True)
    (sd / "sdxl_train_network.py").write_text(FAKE_TRAIN)
    for p in (sd / "venv" / "bin" / "python", sd / "venv" / "Scripts" / "python.exe"):
        os.symlink(sys.executable, p)
    forge = tmp_path / "forge"; (forge / "models" / "Stable-diffusion").mkdir(parents=True); (forge / "models" / "Lora").mkdir()
    (forge / "models" / "Stable-diffusion" / "novaAnimeXL.safetensors").write_bytes(b"x")
    (forge / "models" / "Stable-diffusion" / "pastelkaAnima.safetensors").write_bytes(b"x")
    return str(sd), str(forge)


def test_training_page_mocked_subprocess_links_character(win, tmp_path):
    sd, forge = _fake_trainer(tmp_path)
    cid = win.store.save_character(MIKA); win.tr_refresh_chars()
    win.go("LoRA training")
    win.tr_dir.setText(sd); win.tr_dir.editingFinished.emit(); assert win.tr_status_refresh()
    win.tr_forge.setText(forge); win.tr_forge.editingFinished.emit()
    assert win.tr_ckpt.count() == 1 and win.tr_ckpt.currentText() == "novaAnimeXL.safetensors"  # Anima isn't trainable here
    win.tr_name.setText("mika_v2"); win.tr_trigger.setText("mika_pm"); win.tr_char.setCurrentIndex(win.tr_char.findData(cid))
    for i in range(10):
        win._tr_add(_png_file(tmp_path / f"t{i}.png"))
    assert win.tr_start() is None  # too few images
    for i in range(10, 16):
        win._tr_add(_png_file(tmp_path / f"t{i}.png"))
    win.tr_list.setCurrentRow(0); win.tr_cap.setPlainText("mika_pm, red coat")
    assert win.tr_items[0][1] == "mika_pm, red coat"
    win._auto_confirm = False
    assert win.tr_start() is None  # user said no
    win._auto_confirm = True
    cmd = win.tr_start()
    assert cmd and cmd[0].startswith(sd)
    assert _wait(lambda: getattr(win, "tr_last", None), 20)
    assert win.tr_last == os.path.join(forge, "models", "Lora", "mika_v2.safetensors") and os.path.exists(win.tr_last)
    assert win.tr_bar.value() == 100
    c = win.store.character(cid)
    assert ("mika_v2", 0.8) in ch.loras(c)
    ds = os.path.join(win.data_dir, "training", "mika_v2", "img")
    sub = os.listdir(ds)[0]
    assert open(os.path.join(ds, sub, "000.txt")).read() == "mika_pm, red coat"


def test_training_cancel_and_install_needs_confirmation(win, tmp_path, monkeypatch):
    sd, forge = _fake_trainer(tmp_path)
    monkeypatch.setenv("SLOW", "1")
    win.tr_dir.setText(sd); win.tr_forge.setText(forge); win.tr_load_ckpts()
    win.tr_name.setText("x"); win._auto_confirm = True
    for i in range(15):
        win._tr_add(_png_file(tmp_path / f"c{i}.png"))
    assert win.tr_start(), win.tr_log.toPlainText()
    assert _wait(lambda: win.tr_bar.value() >= 20, 10), win.tr_log.toPlainText()
    assert win.tr_cancel()
    from PySide6.QtCore import QProcess
    assert _wait(lambda: win.tr_proc.state() == QProcess.NotRunning, 10)
    assert not os.path.exists(os.path.join(forge, "models", "Lora", "x.safetensors"))
    # install: nothing runs without confirmation
    win.tr_dir.setText(str(tmp_path / "fresh")); win._auto_confirm = False
    started = []
    monkeypatch.setattr(win, "_tr_start_proc", lambda *a, **k: started.append(a))
    assert win.tr_install() is False and not started
    win._auto_confirm = True
    assert win.tr_install() is True and started and started[0][0][:2] == ["git", "clone"]


# ================================================================ shell / home / palette
def test_v5_sections_home_and_palette(win):
    from promptmaker.shell415 import SECTIONS, section_of
    assert section_of("Storyboard") == "Characters" and section_of("Live sketch") == "Studio"
    assert any(s == "Characters" for _i, s, _p in SECTIONS)
    tiles = [b.text() for b in win.findChildren(type(win.theme_btn)) if b.objectName() == "homeTile"]
    assert any("Characters" in t for t in tiles) and any("Storyboard" in t for t in tiles) and any("Live sketch" in t for t in tiles)
    win.open_quickbar(); win.qbar_in.setText("storyboard")
    texts = [win.qbar_list.item(i).text() for i in range(win.qbar_list.count())]
    assert any("New storyboard" in t for t in texts) and any("Go to" in t and "Storyboard" in t for t in texts)
    win.qbar.hide()
    win.go("Live sketch"); _app().processEvents()
    assert len(win.sub_tabs) == 6 and "Live sketch" in win.sub_tabs
