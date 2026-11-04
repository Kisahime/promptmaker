"""5.3 Video maker / auto-detect screenshots with a synthetic demo project (drawn shapes only).

    QT_QPA_PLATFORM=offscreen python tools/screenshots_video.py
"""
import os, sys, json, random, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
os.environ.update(PROMPTMAKER_NO_NET="1", PROMPTMAKER_NO_TOUR="1", PROMPTMAKER_NO_SETUP="1", QT_QPA_PLATFORM="offscreen")
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication
app = QApplication([])
from promptmaker.app import MainWindow
from promptmaker.storage import Store
from promptmaker import videoproject as vp
OUT = os.path.join(ROOT, "docs", "screenshots")
DATA = tempfile.mkdtemp(prefix="pm53-")
st = Store(os.path.join(DATA, "promptmaker.db"))
st.set("setup_done", True); st.set("tour_done", True); st.set("img_backend", "comfyui")
w = MainWindow(st, DATA); w.resize(1600, 980); w.show()

def art(path, seed, wd=1344, ht=768):
    r = random.Random(seed); img = QImage(wd, ht, QImage.Format_RGB32); p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 0, ht); g.setColorAt(0, QColor.fromHsv(r.randint(180, 230), 120, 250)); g.setColorAt(1, QColor.fromHsv(r.randint(20, 50), 160, 255))
    p.fillRect(img.rect(), g); p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 240, 180, 220)); p.drawEllipse(QRectF(wd * r.uniform(.1, .8), ht * .1, 140, 140))
    p.setBrush(QColor.fromHsv(r.randint(90, 140), 120, 150)); p.drawRect(0, int(ht * .72), wd, ht)
    for k in range(2):  # two simple stylised figures
        x = wd * (.35 + .2 * k); p.setBrush(QColor(250, 220, 200)); p.drawEllipse(QRectF(x, ht * .34, 70, 80))
        p.setBrush(QColor.fromHsv([0, 210][k], 200, 220)); p.drawRoundedRect(QRectF(x - 15, ht * .45, 100, 200), 30, 30)
    p.end(); img.save(path)

def face(path):
    img = QImage(512, 512, QImage.Format_RGB32); img.fill(QColor("#cfe3f5")); p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen); p.setBrush(QColor("#c0c0d0")); p.drawEllipse(130, 70, 252, 300); p.setBrush(QColor("#f6d7c3")); p.drawEllipse(156, 120, 200, 250)
    p.setBrush(QColor("#2f8f5b")); p.drawEllipse(205, 220, 26, 18); p.drawEllipse(281, 220, 26, 18); p.end(); img.save(path)

w.go("Video maker"); w.vm_name.setText("Seaside Morning"); w.vm_new(); w.vm_name.setText("Seaside Morning")
w.vm_idea.setPlainText("Two adult friends cycle through a seaside town at sunrise, stop at a cafe and end with ice cream on the pier.")
w.vm_style.setText("anime style, soft pastel colours")
w.vm_char_add(); w.vm_ch_name.setText("Mira"); w.vm_ch_desc.setPlainText("adult woman, 25 years old, long silver hair, green eyes, red bomber jacket, black jeans")
w.vm_ch_seed.setValue(1234); ref = os.path.join(DATA, "face.png"); face(ref); w.vm_ch_ref.setText(ref); w.vm_ch_main.setChecked(True); w.vm_char_apply()
w.vm_char_add(); w.vm_ch_name.setText("Jo"); w.vm_ch_desc.setPlainText("adult man, 30 years old, short black hair, brown eyes, blue denim shirt"); w.vm_ch_seed.setValue(99); w.vm_char_apply()
plan = {"title": "Seaside Morning", "scenes": [
 {"prompt": "Mira and Jo cycle along a seaside road at sunrise, wide shot", "duration": 4, "camera": "Pan right", "caption": "Sun comes up", "animate": True, "characters": ["c1", "c2"], "motion": "they pedal forward, hair in the wind"},
 {"prompt": "Mira laughs at a cafe table, warm morning light, medium shot", "duration": 3.5, "camera": "Slow push in", "caption": "", "characters": ["c1"]},
 {"prompt": "the harbour with fishing boats, establishing shot", "duration": 3, "camera": "Pull out", "caption": "", "characters": []},
 {"prompt": "Jo hands Mira an ice cream on the pier, golden hour", "duration": 4, "camera": "Tilt up", "caption": "Ice cream time", "animate": True, "characters": ["c2", "c1"]}]}
w.vm_apply_plan(json.dumps(plan))
pdir = w.vm_dir()
for i, s in enumerate(w.vm_proj["scenes"]):
    art(os.path.join(pdir, s["id"] + ".png"), i); s["still"] = s["id"] + ".png"; s["status"] = vp.scene_status(s)
w.vm_proj["scenes"][0]["clip"] = ""; vp.save_project(w.vm_proj, pdir)
w.vm_cur = 0; w.vm_refresh(); w.vm_select(0)
w.vm_bar.setValue(100); w.vm_status.setText("✓ 4 stills · ready to animate the ticked scenes")
w.vm_char_cur = 0; w.vm_char_refresh()
pid = "anima"; w.profile_combo.setCurrentIndex(w.profile_combo.findData(pid)); app.processEvents()
w.vm_update_facelock_warning(); w.toast.hide(); app.processEvents()
w.grab().save(os.path.join(OUT, "video_maker.png"))
cards = [c for c in w.findChildren(type(w.vm_chars.parent())) if c.isAncestorOf(w.vm_fl_warn) and c.objectName() == "card"]
cards[0].grab().save(os.path.join(OUT, "video_characters.png"))
w.go("Settings"); app.processEvents()
w.detect_lbl.setText("Running: ComfyUI (http://127.0.0.1:8188)")
im = w.settings_img_card
if hasattr(w, "_settings_select"): pass
w.toast.hide(); app.processEvents()
im.grab().save(os.path.join(OUT, "settings_autodetect.png"))
print("ok", w.vm_fl_warn.text())
