"""Regenerate the README screenshots from the current app, using fresh demo data in a temp folder.

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py        (run from the repo root)

Nothing touches the network: AI, image backends and Civitai are faked with fixed demo content.
Gallery and A/B images are abstract placeholders drawn here, not real model output.
"""
import os
import random
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)
os.environ["PROMPTMAKER_NO_NET"] = "1"; os.environ["PROMPTMAKER_NO_TOUR"] = "1"
random.seed(2026)

from PySide6.QtCore import QBuffer, QIODevice, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from promptmaker import community, imagegen  # noqa: E402
from promptmaker.app import MainWindow  # noqa: E402
from promptmaker.storage import Store  # noqa: E402

OUT = os.path.join(ROOT, "docs", "screenshots")
W, H = 1440, 900
DATA = tempfile.mkdtemp(prefix="pm-shots-")
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith(".png"):
        os.remove(os.path.join(OUT, f))

app = QApplication(sys.argv)
store = Store(os.path.join(DATA, "promptmaker.db"))
w = MainWindow(store, DATA); w.resize(W, H); w.show()
shots = []


def save(widget, name):
    app.processEvents()
    pm = widget.grab()
    pm.save(os.path.join(OUT, name + ".png"), "PNG", 9)
    shots.append(name)


def g(name):
    w.toast.hide()
    if hasattr(w, "ollama_banner"):
        w.ollama_banner.hide()
    save(w, name)


def art(seed, wd=768, ht=1024):
    """Abstract placeholder 'render' – deliberately not a real image."""
    r = random.Random(seed); img = QImage(wd, ht, QImage.Format_RGB32); p = QPainter(img)
    g1 = QLinearGradient(0, 0, 0, ht); g1.setColorAt(0, QColor.fromHsv(r.randint(180, 280), 160, 90))
    g1.setColorAt(1, QColor.fromHsv(r.randint(0, 60), 200, 230)); p.fillRect(img.rect(), g1)
    for _ in range(14):
        x, y, rad = r.randint(0, wd), r.randint(0, ht), r.randint(40, 260)
        rg = QRadialGradient(x, y, rad); c = QColor.fromHsv(r.randint(0, 359), 180, 255, 150); rg.setColorAt(0, c)
        c2 = QColor(c); c2.setAlpha(0); rg.setColorAt(1, c2)
        p.setPen(Qt.NoPen); p.setBrush(rg); p.drawEllipse(x - rad, y - rad, 2 * rad, 2 * rad)
    p.end(); buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG"); return img, bytes(buf.data())


def demo_data():
    for t in ["a lighthouse keeper on a cliff at dusk, cinematic", "1girl, silver hair, glowing orbs, twilight sky",
              "a cosy reading nook in a treehouse, warm light", "isometric cyberpunk noodle bar at night, neon rain"]:
        store.add_history(t, "SDXL", "demo")
    store.add_favourite("Moody lighthouse", "A lone lighthouse on a storm-lashed cliff at dusk, low angle, volumetric fog")
    for i in range(8):
        _, data = art(100 + i)
        w.gallery.save(data, {"prompt": "abstract dreamscape, glowing orbs, twilight gradient", "negative": "lowres",
                              "seed": 1000 + i, "width": 768, "height": 1024, "profile": "SDXL", "backend": "comfyui",
                              "steps": 28, "cfg": 6.0})


def civitai_profile():
    """Civitai review screen from a fixed copy of a real API response (no network)."""
    from test_civitai import MODEL, VERSION
    from promptmaker.civitai_dialog import CivitaiDialog
    info = {"model": dict(MODEL), "version": dict(VERSION), "images": [{"id": 1, "meta": None}] * 25,
            "url": "https://civitai.com/models/2087823?modelVersionId=3338156"}
    dlg = CivitaiDialog(w, "https://civitai.red/models/2087823/screen-chantv-merge-illustriousoranima?modelVersionId=3338156")
    dlg.resize(860, 760); dlg.show(); dlg._loaded(info)
    save(dlg, "civitai")
    dlg.saved.connect(w._civitai_saved); dlg.save(); app.processEvents()


def v3_shots():
    """3.0 pages, filled with fixed demo data (no Ollama / Forge / Civitai needed)."""
    from promptmaker import firstrun
    # setup wizard with a typical first-run result
    dlg = w.open_setup(auto_check=False); dlg.resize(720, 600)
    dlg.show_results({"ollama": {"installed": True, "running": True, "version": "0.40.11", "models": ["llama3.2:latest"],
                                 "has_text": True, "has_vision": False, "error": ""},
                      "forge": {"found": True, "api": False, "message": "", "hint": imagegen.API_FIX},
                      "comfyui": {"found": False, "message": ""}})
    dlg.pull_bar.setVisible(True); dlg.pull_bar.setRange(0, 100); dlg.pull_bar.setValue(62)
    dlg.pull_lbl.setText(f"pulling {firstrun.RECOMMENDED_VISION} · 3.6 GB / 5.9 GB")
    save(dlg, "setup"); dlg.reject()
    # auto-refine with three iterations
    w.profile_combo.setCurrentIndex(w.profile_combo.findData("illustrious"))
    w.go("Auto-refine"); w.ar_idea.setPlainText("a lighthouse keeper holding a lantern on a cliff at dusk")
    w.ar_prompt.setPlainText("1girl, lighthouse keeper, cliff, dusk"); w.ar_vision.setCurrentText("qwen2.5vl:7b")
    demo = [(52, "1girl, lighthouse keeper, cliff, dusk", ["lantern", "sea"], "Add the lantern and the sea below."),
            (74, "1girl, lighthouse keeper, holding lantern, cliff edge, stormy sea below, dusk", ["warm lantern glow"], "Make the lantern the light source."),
            (88, "1girl, lighthouse keeper, holding glowing lantern, cliff edge, stormy sea below, dusk, rim light, lantern light, "
                 "masterpiece, best quality", [], "Matches the idea well.")]
    for i, (sc, pr, miss, adv) in enumerate(demo):
        _, data = art(300 + i, 512, 640)
        w._ar_step({"i": i + 1, "prompt": pr, "image": data, "score": sc,
                    "judgement": {"score": sc, "matches": ["lighthouse keeper", "cliff", "dusk"], "missing": miss, "wrong": [], "advice": adv}})
    w._ar_done({"steps": [], "best": {"i": 3, "score": 88}, "reason": "threshold"}); g("autorefine")
    # LoRA manager
    words = {"Aiko Character": (["aiko", "silver hair"], "Illustrious"), "Ink Wash Style": (["inkwash"], "Illustrious"),
             "Detail Tweaker XL": ([], "SDXL 1.0"), "Flux Realism": (["realism"], "Flux.1 D")}
    items = []
    for n, (name, (tw, base)) in enumerate(words.items()):
        prev = os.path.join(DATA, f"prev{n}.png"); im, _ = art(400 + n, 256, 320); im.save(prev)
        items.append({"name": name.lower().replace(" ", "_"), "kind": "lora", "path": f"C:\\AI\\sd-webui-forge-classic\\models\\Lora\\{name.lower().replace(' ', '_')}.safetensors",
                      "sha256": f"{n:02d}" * 32, "autov2": (f"{n:02d}" * 5).upper(), "preview_file": prev,
                      "info": {"found": True, "name": name, "version": "v1.0", "trained_words": tw, "base_model": base,
                               "url": f"https://civitai.com/models/{1000 + n}?modelVersionId={2000 + n}"}})
    items.append({"name": "easynegative", "kind": "embedding", "path": "C:\\AI\\sd-webui-forge-classic\\embeddings\\easynegative.pt",
                  "sha256": "AB" * 32, "autov2": "ABABABABAB", "info": {"found": False}})
    w.go("LoRAs"); w._lora_loaded(items); w.lora_list.setCurrentRow(0); g("loras")
    # presets
    st = w.store
    a = st.save_character({"name": "Aiko", "appearance": "silver hair, long hair, red eyes, small freckles",
                           "outfit": "black kimono, red obi, hair ribbon", "lora": "aiko_character", "lora_weight": 0.8})
    st.save_character({"name": "Ren", "appearance": "short black hair, green eyes", "outfit": "school uniform, scarf"})
    s1 = st.save_style({"name": "Ink wash", "tags": "ink wash painting, muted colours, paper texture", "negative": "photo, 3d"})
    st.save_style({"name": "Neon noir", "tags": "neon lighting, rain, cinematic, high contrast"})
    st.set("presets_active_chars", [a]); st.set("presets_active_styles", [s1])
    w.go("Presets"); w.load_presets(); w.ch_list.setCurrentRow(0); w.st_list.setCurrentRow(0)
    w.pr_in.setPlainText("standing on a bridge over a koi pond, cherry blossoms"); w.pr_combine(); g("presets")
    # pose
    w.go("Pose"); c = w.pose_canvas; c.clear(); c.add_figure("Waving"); c.add_figure("Hands on hips")
    c.add_box("torii gate", (.30, .04, .40, .30)); c.selected = ("fig", 0); c.update(); w.pose_update()
    w.pose_cn_model.setCurrentText("xinsir_openpose_sdxl"); g("pose")


def go():
    demo_data()
    w.profile_combo.setCurrentIndex(w.profile_combo.findData("illustrious"))
    w.idea.setPlainText("an anime girl wearing an outfit in a setting"); w.n_opts.setValue(3); w.create_offline()
    g("create")
    w.profile_combo.setCurrentIndex(w.profile_combo.findData("flux2"))
    w.go("Builder"); w.randomise(True); g("builder")
    w.chat = [{"role": "user", "content": "Make it moodier and move the camera lower."},
              {"role": "assistant", "content": "Here's a moodier take with a low-angle camera and heavier atmosphere:\n<prompt>A lone "
               "lighthouse keeper stands on a storm-lashed cliff at dusk, seen from a low angle as waves explode against the rocks "
               "below. Cinematic still, volumetric fog, cold teal and amber palette, ominous mood.</prompt>"}]
    w.go("Refine"); w.set_work("A lighthouse keeper on a cliff at dusk, cinematic", "from Builder"); w.render_thread(); g("refine")
    w.go("Analyse"); w.an_in.setPlainText("masterpiece, best quality, 1girl, silver hair, kimono, cherry blossoms, "
                                          "shrine at sunset, soft rim light, watercolor, wide shot"); w.quick_analyse(); g("analyse")
    w.go("Score"); w.score_in.setPlainText("nice cool lighthouse, (keeper:1.4), photorealistic, anime --ar 16:9"); w.quick_score(); g("score")
    # Image to Prompt, with an unsupported model marked in the picker
    w.go("Image to Prompt"); img, _ = art(7); w._i2p_set_image(img)
    w.vision_model.clear(); w.vision_model.addItems(["qwen2.5vl:7b", "gemma3:4b", "llama3.2-vision:latest"])
    w.provider.notes = {"llama3.2-vision:latest": "Not supported on Ollama 0.30+ (llama.cpp engine has no mllama support, see ollama/ollama#16547)"}
    w._mark_failed_in_pickers(); w.i2p_hint.setText("3 vision-capable model(s) found.")
    w.i2p_out.setPlainText("1girl, solo, silver hair, floating among glowing orbs, twilight sky gradient, dreamy atmosphere, "
                           "soft bokeh, masterpiece, best quality, very aesthetic, absurdres")
    g("img2prompt")
    w.ab["A"]["edit"].setPlainText("a lighthouse on a cliff at dusk, cinematic")
    w.ab["B"]["edit"].setPlainText("A lone lighthouse on a storm-lashed cliff at dusk, low angle, volumetric fog, teal and amber palette, cinematic still")
    w.ab_compare()
    for side, sd in (("A", 3), ("B", 4)):
        im, _ = art(sd, 512, 384)
        w.ab[side]["img"].setPixmap(QPixmap.fromImage(im).scaled(380, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    w.go("A/B Test"); g("abtest")
    w.load_gallery(); w.go("Gallery"); w.gal_list.setCurrentRow(0); g("gallery")
    w.go("Templates"); w.tpl_list.setCurrentRow(0); w.tpl_fill(True); g("templates")
    w.go("Batch"); w.batch_n.setValue(8); w.batch_generate(); g("batch")
    w.load_history(); w.go("History"); w.hist_clear_btn.click(); g("history"); w.hist_clear_btn.reset()
    w.go("Packs"); g("packs")
    idx = "file://" + os.path.abspath("community/index.json")
    w._comm_loaded(community.load_index(idx)); w.comm_status.setText(f"{len(w.comm_items)} item(s)"); w.go("Community"); g("community")
    civitai_profile()
    v3_shots()
    w.go("Model profiles"); app.processEvents(); g("profiles")
    w.go("Settings"); g("settings")
    w.start_tour(); app.processEvents(); g("tour"); w.tour.hide()
    # troubleshooting dialogs
    box = w.show_api_disabled(str(imagegen.ApiDisabled("Forge Neo", "2.31", "C:\\AI\\sd-webui-forge-classic")))
    app.processEvents(); save(box, "forge_api"); box.close()
    w.go("Image to Prompt")
    w._ai_error("HTTP 500 from http://localhost:11434/api/chat: {\"error\":\"llama-server process has terminated: exit status 1: "
                "error loading model: unknown model architecture: 'mllama'\"}", "llama3.2-vision:latest", vision=True)
    app.processEvents(); save(w._last_error_box, "model_error"); w._last_error_box.close()
    w.toggle_theme(); w.go("Builder"); g("builder_light")
    # App icon as shown on the window, taskbar and desktop shortcut
    from promptmaker.app import app_icon
    app_icon().pixmap(256, 256).save(os.path.join(OUT, "icon.png"), "PNG", 9); shots.append("icon")
    print("saved:", ", ".join(shots))
    w.close(); app.quit()


QTimer.singleShot(400, go)
app.exec()
shutil.rmtree(DATA, ignore_errors=True)
