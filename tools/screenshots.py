"""Regenerate README screenshots:  QT_QPA_PLATFORM=offscreen python tools/screenshots.py  (run from repo root; uses ./data)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from promptmaker.app import MainWindow
from promptmaker.storage import Store
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
    w.toggle_theme(); w.go("Builder"); w.toast.hide(); g("builder_light")
    app.quit()
QTimer.singleShot(400, go); app.exec()
