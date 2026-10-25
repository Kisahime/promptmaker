"""Regenerate README screenshots:  QT_QPA_PLATFORM=offscreen python tools/screenshots.py  (run from repo root; uses ./data)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from promptmaker.app import MainWindow
from promptmaker.storage import Store
os.environ["PROMPTMAKER_NO_NET"] = "1"; os.environ["PROMPTMAKER_NO_TOUR"] = "1"
import os; os.makedirs("data", exist_ok=True); os.makedirs("docs/screenshots", exist_ok=True)
app = QApplication(sys.argv)
w = MainWindow(Store("data/promptmaker.db"), "data"); w.resize(1440, 900); w.show()
def g(n): app.processEvents(); w.grab().save(f"docs/screenshots/{n}.png")
def go():
    w.toast.hide()
    w.profile_combo.setCurrentIndex(w.profile_combo.findData("illustrious"))
    w.idea.setPlainText("an anime girl wearing an outfit in a setting"); w.n_opts.setValue(3); w.create_offline()
    w.ollama_banner.hide(); g("create")
    w.profile_combo.setCurrentIndex(w.profile_combo.findData("flux2"))
    w.go("Builder"); w.randomise(True); g("builder")
    w.chat=[{"role":"user","content":"Make it moodier and move the camera lower."},
            {"role":"assistant","content":"Here's a moodier take with a low-angle camera and heavier atmosphere:\n<prompt>A lone lighthouse keeper stands on a storm-lashed cliff at dusk, seen from a low angle as waves explode against the rocks below. Cinematic still, volumetric fog, cold teal and amber palette, ominous mood.</prompt>"}]
    w.go("Refine"); w.set_work("A lighthouse keeper on a cliff at dusk, cinematic", "from Builder"); w.render_thread(); w.toast.hide(); g("refine")
    w.go("Score"); w.score_in.setPlainText("nice cool lighthouse, (keeper:1.4), photorealistic, anime --ar 16:9"); w.quick_score(); g("score")
    w.go("Model profiles"); w.prof_list.setCurrentRow(list(w.profiles).index("anima")); g("profiles")
    w.go("Packs"); g("packs")
    v2_pages()
    w.toggle_theme(); w.go("Builder"); w.toast.hide(); g("builder_light")
    app.quit()
def art(seed, wd=768, ht=1024):
    """Abstract placeholder 'render' (no real model output is bundled)."""
    from PySide6.QtGui import QImage, QPainter, QLinearGradient, QRadialGradient, QColor
    from PySide6.QtCore import QBuffer, QIODevice
    import random
    r = random.Random(seed); img = QImage(wd, ht, QImage.Format_RGB32); p = QPainter(img)
    g1 = QLinearGradient(0, 0, 0, ht); g1.setColorAt(0, QColor.fromHsv(r.randint(180, 280), 160, 90)); g1.setColorAt(1, QColor.fromHsv(r.randint(0, 60), 200, 230))
    p.fillRect(img.rect(), g1)
    for _ in range(14):
        x, y, rad = r.randint(0, wd), r.randint(0, ht), r.randint(40, 260)
        rg = QRadialGradient(x, y, rad); c = QColor.fromHsv(r.randint(0, 359), 180, 255, 150); rg.setColorAt(0, c); c2 = QColor(c); c2.setAlpha(0); rg.setColorAt(1, c2)
        p.setPen(Qt.NoPen); p.setBrush(rg); p.drawEllipse(x - rad, y - rad, 2 * rad, 2 * rad)
    p.end(); buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG"); return img, bytes(buf.data())
def v2_pages():
    from promptmaker import community
    w.go("Image to Prompt"); img, _ = art(7); w._i2p_set_image(img)
    w.vision_model.clear(); w.vision_model.addItems(["llava:13b", "qwen2.5vl:7b"])
    w.i2p_out.setPlainText("1girl, solo, silver hair, floating among glowing orbs, twilight sky gradient, dreamy atmosphere, soft bokeh, "
                           "masterpiece, best quality, very aesthetic, absurdres")
    w.toast.hide(); g("img2prompt")
    w.ab["A"]["edit"].setPlainText("a lighthouse on a cliff at dusk, cinematic")
    w.ab["B"]["edit"].setPlainText("A lone lighthouse on a storm-lashed cliff at dusk, low angle, volumetric fog, teal and amber palette, cinematic still")
    w.ab_compare()
    for side, sd in (("A", 3), ("B", 4)):
        im, _ = art(sd, 512, 384); w.ab[side]["img"].setPixmap(QPixmap.fromImage(im).scaled(380, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    w.go("A/B Test"); w.toast.hide(); g("abtest")
    if not w.gallery.items():
        for i in range(8):
            _, data = art(100 + i); w.gallery.save(data, {"prompt": "abstract dreamscape, glowing orbs, twilight gradient", "negative": "lowres",
                                                          "seed": 1000 + i, "width": 768, "height": 1024, "profile": "sdxl", "backend": "comfyui", "steps": 28, "cfg": 6.0})
    w.load_gallery(); w.go("Gallery"); w.gal_list.setCurrentRow(0); w.toast.hide(); g("gallery")
    idx = "file://" + os.path.abspath("community/index.json")
    w._comm_loaded(community.load_index(idx)); w.comm_status.setText(f"{len(w.comm_items)} item(s)"); w.go("Community"); w.toast.hide(); g("community")
    w.go("Settings"); w.toast.hide(); g("settings")
    w.start_tour(); app.processEvents(); g("tour"); w.tour.hide()
QTimer.singleShot(400, go); app.exec()
