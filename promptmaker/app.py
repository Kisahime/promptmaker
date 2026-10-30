"""PromptMaker – desktop UI (PySide6)."""
import base64
import html
import json
import os
import shutil
import re
import sys
import time

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QBuffer, QIODevice
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence, QFont, QPixmap, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QMessageBox, QGridLayout, QHBoxLayout, QInputDialog, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit, QRadioButton, QScrollArea, QSpinBox,
    QSplitter, QStackedWidget, QSlider, QFrame, QLabel, QProgressBar, QDoubleSpinBox, QTextBrowser, QVBoxLayout, QWidget,
)

from . import (__version__, abtest, builder, civitai, community, i18n, imagegen, ollama, paths, profiles, providers, scoring,
               theme, updates)
from .gallery import Gallery
from .i18n import tr
from .keystore import KeyStore
from .library import Library, PLACEHOLDERS, PackError
from .storage import Store
from .v3ui import V3Pages
from .v4ui import V4Pages
from .v41ui import GalleryList, V41Pages
from .widgets import (CallWorker, Card, CheckpointCombo, ChatWorker, ConfirmButton, DropLabel, strip_ckpt_hash, FlowLayout, GenQueue, ScoreBar, Toast, button, chip, hrow, label)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEGATIVE_PRESETS = {
    "Model default": None,
    "Standard": "blurry, low quality, lowres, deformed, bad anatomy, extra limbs, extra fingers, watermark, text, signature, jpeg artifacts",
    "Portrait": "bad hands, deformed face, asymmetric eyes, extra fingers, plastic skin, blurry, watermark",
    "Landscape": "people, text, watermark, oversaturated, blurry, low quality, frame",
    "Anime": "realistic, photo, 3d, bad anatomy, extra limbs, lowres, watermark",
    "Photo": "cartoon, illustration, painting, 3d render, cgi, oversaturated, blurry",
    "None": "",
}
NAV = [("🏠", "Home"), ("✨", "Create"), ("🎨", "Builder"), ("💬", "Refine"), ("🖼", "Image to Prompt"), ("🔄", "Auto-refine"), ("🧍", "Pose"), ("🖌", "Inpaint & Regions"), ("👤", "Presets"), ("🎲", "Wildcards"), ("🧩", "LoRAs"), ("🎬", "Video"), ("🔍", "Analyse"), ("📊", "Score"),
       ("⚖", "A/B Test"), ("🗂", "Gallery"), ("📋", "Templates"),
       ("🔁", "Batch"), ("🕘", "History"), ("⭐", "Favourites"), ("📦", "Packs"), ("🌐", "Community"), ("🎯", "Model profiles"), ("☁", "Library sync"), ("⚙", "Settings")]


def copy(text):
    QGuiApplication.clipboard().setText(text or "")


def scroll(widget):
    s = QScrollArea(); s.setWidgetResizable(True); s.setWidget(widget)
    s.setFrameShape(QScrollArea.NoFrame)
    return s


def page(title, subtitle=""):
    w = QWidget()
    v = QVBoxLayout(w); v.setContentsMargins(32, 26, 32, 24); v.setSpacing(16)
    head = QVBoxLayout(); head.setSpacing(2); head.setContentsMargins(0, 0, 0, 6)
    head.addWidget(label(title, "h1"))
    if subtitle:
        head.addWidget(label(subtitle, "muted", wrap=True))
    v.addLayout(head)
    return w, v


class MainWindow(V41Pages, V4Pages, V3Pages, QMainWindow):
    def __init__(self, store, data_dir):
        super().__init__()
        self.store, self.data_dir = store, data_dir
        self.worker = None
        self.ai_buttons = []
        self.sel = {}
        self.locks = set(self.store.get("locks", []))
        self.chip_map = {}
        self.suggestions = []
        self.chat = []
        _old, _new = os.path.join(APP_DIR, "packs", "custom.json"), os.path.join(data_dir, "packs", "custom.json")
        if os.path.exists(_old) and not os.path.exists(_new):  # v1 kept custom chips next to the bundled packs
            os.makedirs(os.path.dirname(_new), exist_ok=True); shutil.copy2(_old, _new); os.replace(_old, _old + ".migrated")
        self.lib = Library(os.path.join(APP_DIR, "packs"), self.store.get("packs_disabled", []), os.path.join(data_dir, "packs"))
        self.keys = KeyStore(data_dir)
        self.gallery = Gallery(os.path.join(data_dir, "gallery"))
        self.queue_jobs = []
        self.genq = GenQueue()
        imagegen.BEFORE_GENERATE[:] = [self._free_ollama_vram]
        self._refresh_unload_cfg()
        self.genq.progress.connect(self._gen_progress); self.genq.finished_job.connect(self._gen_done)
        self.genq.failed_job.connect(self._gen_failed)
        self.make_provider()
        self.profiles_path = profiles.ensure_user_file(os.path.join(data_dir, "profiles.json"))
        self.profiles = profiles.load(self.profiles_path)
        self.setWindowTitle("PromptMaker — AI Image Prompt Studio")
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        root = QWidget(); root.setObjectName("root")
        h = QHBoxLayout(root); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
        h.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        for builder_fn in (self._home_page, self._create_page, self._builder_page, self._refine_page, self._img2prompt_page, self._autorefine_page, self._pose_page,
                           self._inpaint_page, self._presets_page, self._wildcards_page, self._loras_page, self._video_page, self._analyse_page,
                           self._score_page, self._ab_page, self._gallery_page,
                           self._templates_page, self._batch_page, self._history_page, self._fav_page,
                           self._packs_page, self._community_page, self._profiles_page, self._sync_page, self._settings_page):
            self.stack.addWidget(builder_fn())
        self.toast = Toast(root)
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.nav.setCurrentRow(0)
        sc = QAction(self, shortcut=QKeySequence("Ctrl+T")); sc.triggered.connect(self.toggle_theme); self.addAction(sc)
        cp = QAction(self, shortcut=QKeySequence("Ctrl+Shift+C")); cp.triggered.connect(self.copy_prompt); self.addAction(cp)
        qk = QAction(self, shortcut=QKeySequence("Ctrl+K")); qk.triggered.connect(self.open_quickbar); self.addAction(qk)
        self.apply_theme(self.store.get("theme", "dark"))
        if self.store.get("sidebar_collapsed"):
            self.set_sidebar_collapsed(True)
        self.preview_timer = QTimer(self); self.preview_timer.timeout.connect(self._preview_tick); self.preview_timer.start(700)
        self.home_refresh()
        self.update_preview()
        self._create_profile_refresh()
        QTimer.singleShot(50, self.refresh_models_async)
        if self.store.get("check_updates", True) and not os.environ.get("PROMPTMAKER_NO_NET"):
            QTimer.singleShot(3000, self.check_updates)
        if not self.store.get("setup_done") and not os.environ.get("PROMPTMAKER_NO_TOUR") and not os.environ.get("PROMPTMAKER_NO_SETUP"):
            QTimer.singleShot(400, self.open_setup)
        elif not self.store.get("tour_done") and not os.environ.get("PROMPTMAKER_NO_TOUR"):
            QTimer.singleShot(600, self.start_tour)

    # ------------------------------------------------------------------ chrome
    def _sidebar(self):
        w = QWidget(); w.setFixedWidth(240); self.sidebar_w = w
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        brand = label("✦ PromptMaker", "brand")
        self.collapse_btn = button("«", lambda: self.set_sidebar_collapsed(not self.store.get("sidebar_collapsed")), "ghost",
                                   "Collapse sidebar to icons")
        self.collapse_btn.setFixedWidth(34)
        top = QWidget(); top.setObjectName("sideFoot"); th = QHBoxLayout(top); th.setContentsMargins(0, 0, 8, 0)
        th.addWidget(brand, 1); th.addWidget(self.collapse_btn)
        v.addWidget(top)
        self._side_expand_only = [brand]
        v.addWidget(label(f"AI image prompt studio · v{__version__}", "brandSub"))
        self.nav = QListWidget(); self.nav.setObjectName("sidebar"); self.nav.setIconSize(QSize(18, 18))
        for icon, name in NAV:
            it = QListWidgetItem(f"{icon}   {tr(name)}"); self.nav.addItem(it)
        v.addWidget(self.nav, 1)
        foot = QWidget(); foot.setObjectName("sideFootPanel")
        f = QVBoxLayout(foot); f.setContentsMargins(16, 12, 16, 16); f.setSpacing(6)
        self._status_widgets(f)
        _tm = label("TARGET MODEL", "groupLabel"); f.addWidget(_tm)
        self.profile_combo = QComboBox()
        for pid, p in self.profiles.items():
            self.profile_combo.addItem(p["name"], pid)
        idx = self.profile_combo.findData(self.store.get("profile", "generic"))
        self.profile_combo.setCurrentIndex(max(0, idx))
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        f.addWidget(self.profile_combo)
        _ap = label("AI PROVIDER", "groupLabel"); f.addWidget(_ap)
        self.prov_label = label("", "hint"); f.addWidget(self.prov_label)
        self.model = QComboBox(); self.model.setPlaceholderText("no models")
        self.model.currentTextChanged.connect(lambda m: m and self.store.set(f"model:{self.provider.pid}", m))
        f.addWidget(self.model)
        self.ai_dot = label("○ checking…", "hint", wrap=True)
        f.addLayout(hrow(self.ai_dot, None, button("⟳", self.refresh_models, "ghost", "Refresh Ollama models")))
        self.update_btn = button("", None, "ghost"); self.update_btn.setVisible(False); f.addWidget(self.update_btn)
        f.addWidget(button("🧭  Setup wizard", lambda: self.open_setup(), "ghost", "Check Ollama, download models, find Forge / ComfyUI"))
        self.theme_btn = button("🌙  Dark mode", self.toggle_theme, "ghost")
        f.addWidget(self.theme_btn)
        v.addWidget(foot)
        self._side_expand_only += [_tm, self.profile_combo, _ap, self.prov_label, self.model, self.ai_dot, self.theme_btn]
        return w

    def _nav_changed(self, i):
        self.stack.setCurrentIndex(i)
        self.fade_in(self.stack.currentWidget())
        name = NAV[i][1]
        if name == "Home":
            self.home_refresh()
        if name == "History":
            self.load_history()
        elif name == "Favourites":
            self.load_favs()
        elif name == "Score" and not self.score_in.toPlainText().strip():
            self.score_in.setPlainText(self.current_text())
        elif name == "Refine" and not self.work.toPlainText().strip():
            self.work.setPlainText(self.current_text())
        if name in ("Settings", "Pose", "Auto-refine", "Inpaint & Regions"):
            self._autoload_checkpoints()
        elif name == "Library sync":
            self.sy_refresh()
        elif name == "Wildcards":
            self.wc_reload()

    def go(self, name):
        self.nav.setCurrentRow([n for _, n in NAV].index(name))

    def notify(self, text, error=False):
        self.toast.show_message(text, error)

    def apply_theme(self, name):
        self.theme = name
        QApplication.instance().setStyleSheet(theme.stylesheet(name, self.store.get("accent", "purple")))
        self.store.set("theme", name)
        self.theme_btn.setText("☀️  Light mode" if name == "dark" else "🌙  Dark mode")
        if hasattr(self, "thread_view"):
            self.render_thread()

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    @property
    def profile(self):
        return self.profiles.get(self.profile_combo.currentData()) or next(iter(self.profiles.values()))

    def _profile_changed(self, *_):
        self.store.set("profile", self.profile["id"])
        p = self.profile
        self.mj_box.setVisible(p.get("param_style") == "midjourney")
        neg_ok = p.get("negative") != "unsupported" or p.get("family") in ("OpenAI", "Google")
        self.neg_hint.setText({"unsupported": "No negative prompt for this model" + (
            " – it is added as an 'Avoid:' constraint." if neg_ok else " – it will be left out."),
            "limited": "Negative prompt has limited effect on this model.",
            "param_no": "Sent as Midjourney --no."}.get(p.get("negative"), "Supported."))
        self.emph.setEnabled(p.get("weighting") == "parens")
        if self.negpreset.currentText() == "Model default":
            self.negative.blockSignals(True); self._neg_preset("Model default"); self.negative.blockSignals(False)
        self.profile_tips.setText(" · ".join(p.get("tips", [])[:3]))
        self.apply_profile_checkpoint()
        if hasattr(self, "sidebar_w"):
            self.apply_profile_image_settings()
            self._update_ckpt_link_label()
            self.home_refresh()
        self.update_preview()
        self._create_profile_refresh()
        if hasattr(self, "score_in"):
            self.quick_score()
        if hasattr(self, "lora_list"):
            self.lora_render()
        if hasattr(self, "pose_canvas"):
            w_, h_ = self._pose_size(); self.pose_canvas.set_aspect(w_ / h_); self.pose_update()

    # ------------------------------------------------------------------ AI plumbing
    def refresh_models(self, quiet=False):
        try:
            models = self.provider.list_models()
        except Exception as e:  # noqa: BLE001
            return self._models_failed(e, quiet)
        return self._models_loaded(models, quiet)

    def _free_ollama_vram(self):
        """Runs on the generation thread: drop Ollama's loaded text/vision models so the image model gets the VRAM.
        Only when the setting is on and the AI provider is a local Ollama. Settings are cached on the main thread."""
        cfg = getattr(self, "_unload_cfg", None)
        if not cfg or not cfg[0]:
            return []
        return ollama.unload_all(cfg[1])

    def _refresh_unload_cfg(self):
        pid = self.store.get("provider", "ollama")
        on = bool(self.store.get("img_unload_ollama", True)) and providers.PRESETS.get(pid, {}).get("kind", "ollama") == "ollama"
        url = self.store.get(f"provider_url:{pid}") or providers.PRESETS.get(pid, {}).get("base_url") or ollama.BASE
        self._unload_cfg = (on, url)

    def run_ai(self, messages, on_chunk, on_done, json_mode=False, temperature=0.7, model=None, vision=False):
        if self.worker and self.worker.isRunning():
            self.notify("The AI is still busy – press Stop first", error=True); return False
        if not model and not self.model.currentText() and not self.refresh_models(quiet=True):
            self.notify(tr("No AI model available – check the AI provider in Settings"), error=True); return False
        used = model or self.model.currentText()
        self.worker = ChatWorker(self.provider, used, messages, temperature, json_mode)
        self.worker.chunk.connect(on_chunk)
        self.worker.done.connect(lambda t: (self._busy(False), self._mark_model_ok(used), on_done(t)))
        self.worker.failed.connect(lambda e: (self._busy(False), self._ai_error(e, used, vision)))
        self._busy(True); self.worker.start()
        return True

    # ---- friendly handling of models the provider can't load (e.g. Ollama 'unknown model architecture')
    def _failed_models(self):
        return self.store.get(f"failed_models:{self.provider.pid}", {}) or {}

    def _mark_model_ok(self, model):
        f = self._failed_models()
        if model in f:
            f.pop(model); self.store.set(f"failed_models:{self.provider.pid}", f); self._mark_failed_in_pickers()

    def _mark_failed_in_pickers(self):
        from PySide6.QtGui import QColor
        failed = self._failed_models()
        notes = getattr(self.provider, "notes", {}) or {}
        for combo in (self.model, getattr(self, "vision_model", None)):
            if combo is None:
                continue
            for i in range(combo.count()):
                name = combo.itemText(i)
                tip = ("⚠ " + notes[name]) if name in notes else (
                    ("⚠ Failed to load last time: " + failed[name]) if name in failed else None)
                combo.setItemData(i, QColor("#ff6b6b") if tip else None, Qt.ForegroundRole)
                combo.setItemData(i, tip, Qt.ToolTipRole)

    def _ai_error(self, err, model, vision=False):
        if not providers.is_model_load_error(err):
            self.notify(err, error=True); return
        f = self._failed_models(); f[model] = providers.load_error_detail(err)
        self.store.set(f"failed_models:{self.provider.pid}", f)
        is_ollama = self.provider.kind == "ollama"
        combo = self.vision_model if vision and hasattr(self, "vision_model") else self.model
        models = [combo.itemText(i) for i in range(combo.count())]
        prefs = providers.VISION_PREFERENCE if vision else providers.CHAT_PREFERENCE
        alt = providers.pick_alternative(models, model, prefs, {**f, **(getattr(self.provider, "notes", {}) or {})})
        pull = providers.VISION_PULL if vision else providers.CHAT_PULL
        self._mark_failed_in_pickers()
        msg = providers.friendly_load_error(model, err, vision, is_ollama)
        self.notify(msg, error=True)
        box = QMessageBox(self); box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("Model couldn't load")); box.setText(msg)
        box.setDetailedText(str(err))
        switch = box.addButton(tr("Switch to") + f" {alt}", QMessageBox.AcceptRole) if alt else None
        copy_btn = box.addButton(tr("Copy") + f" `{pull}`", QMessageBox.ActionRole) if is_ollama else None
        box.addButton(QMessageBox.Close)
        def clicked(b):
            if switch is not None and b is switch:
                combo.setCurrentText(alt)
                if vision:
                    self.store.set(f"vision_model:{self.provider.pid}", alt); self.notify(tr("Switched to") + f" {alt}")
                    self._i2p_run()
                else:
                    self.notify(tr("Switched to") + f" {alt} – " + tr("try again"))
            elif copy_btn is not None and b is copy_btn:
                copy(pull); self.notify(tr("Copied") + f": {pull}")
        box.buttonClicked.connect(clicked)
        self._last_error_box = box
        box.open()

    def _busy(self, busy):
        for b in self.ai_buttons:
            b.setEnabled(not busy)
        for s in getattr(self, "stop_buttons", []):
            s.setEnabled(busy)

    def stop_ai(self):
        if self.worker:
            self.worker.stop()
        self._busy(False)

    def ai_btn(self, text, slot, kind=None, tip=None):
        b = button(text, slot, kind, tip); self.ai_buttons.append(b); return b

    def stop_btn(self):
        b = button("■ Stop", self.stop_ai, "ghost"); b.setEnabled(False)
        self.stop_buttons = getattr(self, "stop_buttons", []) + [b]
        return b

    # ------------------------------------------------------------------ Create (idea -> prompt)
    def _create_page(self):
        w, v = page("Create", "Describe what you want in plain words – the AI writes a finished prompt for your target model.")
        top = Card()
        self.idea = QPlainTextEdit(); self.idea.setFixedHeight(96)
        self.idea.setPlaceholderText("e.g. give me a prompt for an anime girl wearing an outfit in a setting   (Ctrl+Enter to create)")
        f = QFont(); f.setPointSize(12); self.idea.setFont(f)
        go = QAction(self.idea, shortcut=QKeySequence("Ctrl+Return")); go.triggered.connect(self.create_generate)
        self.idea.addAction(go)
        top.add(self.idea)
        self.creativity = QSlider(Qt.Horizontal); self.creativity.setRange(0, 100)
        self.creativity.setValue(self.store.get("creativity", 60)); self.creativity.setFixedWidth(180)
        self.creativity_lbl = label("", "muted")
        def _cl(val):
            self.creativity_lbl.setText(("Faithful" if val < 30 else "Balanced" if val < 70 else "Wild") + f" ({val})")
            self.store.set("creativity", val)
        self.creativity.valueChanged.connect(_cl); _cl(self.creativity.value())
        self.n_opts = QSpinBox(); self.n_opts.setRange(1, 5); self.n_opts.setValue(1); self.n_opts.setPrefix("Options: ")
        self.create_target = label("", "badge")
        top.add(hrow(label("Creativity"), self.creativity, self.creativity_lbl, self.n_opts, self.create_target, None,
                     button("⚡ Offline build", self.create_offline, tip="No AI – builds from matching presets"),
                     self.stop_btn(), self.ai_btn("✨ Create prompt", self.create_generate, "primary")))
        # Ollama offline banner
        self.ollama_banner = QWidget(); bl = QHBoxLayout(self.ollama_banner); bl.setContentsMargins(0, 0, 0, 0)
        self.banner_text = label("", "muted", wrap=True)
        self.start_btn = button("▶ Start Ollama", self.start_ollama, "primary")
        bl.addWidget(self.banner_text, 1); bl.addWidget(self.start_btn)
        top.add(self.ollama_banner)
        v.addWidget(top)

        res = Card()
        self.opt_pick = QComboBox(); self.opt_pick.currentIndexChanged.connect(self._show_option)
        self.create_status = label("", "hint")
        res.add(hrow(label("Result", "h2"), self.opt_pick, None, self.create_status))
        self.c_prompt = QPlainTextEdit(); f2 = QFont(); f2.setPointSize(11); self.c_prompt.setFont(f2)
        res.add(self.c_prompt, 2)
        self.c_neg_lbl = label("Negative prompt", "h2"); res.add(self.c_neg_lbl)
        self.c_neg = QPlainTextEdit(); self.c_neg.setFixedHeight(60); res.add(self.c_neg)
        self.c_settings = label("", "hint", wrap=True); self.c_settings.setTextInteractionFlags(Qt.TextSelectableByMouse)
        res.add(self.c_settings)
        res.add(hrow(button("📋 Copy", self.c_copy, "primary"), button("Copy negative", self.c_copy_neg),
                     button("💬 Refine in chat", self.c_refine), button("↩ Load into Builder", self.c_to_builder),
                     button("📊 Score", self.c_score), button("🕘 Save to history", self.c_hist),
                     button("⭐ Favourite", self.c_fav), button("🖼 Generate", lambda: self.generate_image(
                         self.c_prompt.toPlainText(), self.c_neg.toPlainText())), None, self.ai_btn("⟳ Regenerate", self.create_generate)))
        v.addWidget(res, 1)
        self.create_opts = []
        return w

    def _create_profile_refresh(self):
        if not hasattr(self, "create_target"):
            return
        p = self.profile
        self.create_target.setText("🎯 " + p["name"])
        has_neg = p.get("negative") in ("supported", "optional", "limited")
        self.c_neg_lbl.setVisible(has_neg); self.c_neg.setVisible(has_neg)
        self._create_settings()

    def _create_settings(self):
        p = self.profile
        aspect = self.aspect.currentText()
        res = profiles.resolution(p, aspect)
        if p.get("param_style") == "midjourney":
            txt = f"Recommended: --ar {aspect} --v 7 · " + p.get("settings", "")
        else:
            txt = f"Recommended: {res or aspect} ({aspect}) · " + p.get("settings", "")
        self.c_settings.setText("⚙ " + txt + "   (change aspect in Builder)")

    def _set_banner(self, ok, models=0):
        if not hasattr(self, "ollama_banner"):
            return
        if ok and models:
            self.ollama_banner.hide(); return
        self.ollama_banner.show()
        if ok:
            self.banner_text.setText("⚠️ Ollama is running but has no models. Open a terminal and run  <b>ollama pull llama3.2</b>"
                                     "  (or qwen2.5 / gemma3), then click ⟳. Meanwhile use ⚡ Offline build.")
            self.start_btn.hide()
        else:
            if self.provider.pid != "ollama":
                self.banner_text.setText("⚠️ " + tr("The AI provider isn't reachable – check it in Settings. ⚡ Offline build works without AI."))
                self.start_btn.hide(); return
            found = ollama.find_ollama_app()
            self.banner_text.setText("⚠️ Local AI is offline. " + ("Click Start Ollama to launch it." if found else
                                     "Ollama isn't installed – get it from ollama.com/download.") +
                                     " Needs a model, e.g. <b>ollama pull llama3.2</b>. ⚡ Offline build works without AI.")
            self.start_btn.setVisible(bool(found))

    def start_ollama(self):
        try:
            exe = ollama.start_ollama()
        except (ollama.OllamaError, OSError) as e:
            self.notify(str(e), error=True); return
        self.notify("Starting Ollama…"); self.start_btn.setEnabled(False)
        self._start_tries = 0
        def poll():
            self._start_tries += 1
            if self.refresh_models(quiet=True):
                self.notify("Ollama is ready"); self.start_btn.setEnabled(True); return
            try:
                self.provider.list_models(); running = True
            except Exception:  # noqa: BLE001
                running = False
            if running or self._start_tries > 20:
                self.start_btn.setEnabled(True)
                if not running:
                    self.notify(f"Ollama didn't respond ({exe}). Try starting it from the Start menu.", error=True)
                return
            QTimer.singleShot(1000, poll)
        QTimer.singleShot(1500, poll)

    def create_generate(self):
        idea = self.idea.toPlainText().strip()
        if not idea:
            self.notify("Type an idea first", error=True); self.idea.setFocus(); return
        if not self.model.currentText() and not self.refresh_models(quiet=True):
            self.notify("Local AI is offline – used ⚡ Offline build instead", error=True)
            self.create_offline(); return
        self.go("Create")
        n, temp = self.n_opts.value(), 0.3 + self.creativity.value() / 100
        self.c_prompt.clear(); self.c_neg.clear(); self.opt_pick.clear(); self.create_opts = []
        self.create_status.setText("✍ writing…")
        buf = []
        def chunk(c):
            buf.append(c)
            import re as _re
            shown = _re.sub(r"</?(prompt|negative)>", "\n", "".join(buf)).strip()
            self.c_prompt.setPlainText(shown); self.c_prompt.verticalScrollBar().setValue(self.c_prompt.verticalScrollBar().maximum())
        def done(t):
            self._set_options([self._finish_option(o) for o in ollama.parse_options(t)][:n], "by " + (self.worker.model if self.worker else "AI"))
        self.run_ai(ollama.create_messages(idea, self.profile, n, self.creativity.value()), chunk, done, temperature=temp)

    def _finish_option(self, o):
        p = self.profile
        if p.get("param_style") == "midjourney" and "--ar" not in o["prompt"]:
            o["prompt"] = o["prompt"].rstrip(". ") + f" --ar {self.aspect.currentText()} --v 7"
            if o["negative"]:
                o["prompt"] += " --no " + o["negative"]; o["negative"] = ""
        if p.get("negative") not in ("supported", "optional", "limited"):
            o["negative"] = ""
        return o

    def create_offline(self):
        idea = self.idea.toPlainText().strip()
        if not idea:
            self.notify("Type an idea first", error=True); return
        import random as _r
        low = idea.lower()
        sel = {}
        for cat, items in self.lib.all_items().items():
            hits = [i for i in items if len(i) > 3 and scoring._has(low, i.lower())]
            hits = [h for h in hits if not any(h != o and h.lower() in o.lower() for o in hits)]
            if hits:
                sel[cat] = hits[:2]
        import re as _re
        core = _re.sub(r"^(give me |make |create |write )?(a |an )?(prompt )?(for |of )?", "", low).strip(" .")
        opts = []
        fill_cats = ["Setting", "Style", "Lighting", "Camera", "Mood", "Color palette"]
        if self.creativity.value() >= 70:
            fill_cats += ["Time & weather", "Composition", "Detail / quality"]
        for k in range(self.n_opts.value()):
            s = {c: list(v) for c, v in sel.items()}
            if self.creativity.value() >= 30:
                missing = [c for c in fill_cats if c not in s]
                s = builder.randomize(s, missing, self.lib.all_items(), _r.Random(time.time_ns() + k))
            s.setdefault("Subject", [core or idea])
            r = builder.build(s, self.profile, negative=self.profile.get("negative_default", "").strip(),
                              aspect=self.aspect.currentText())
            opts.append({"prompt": r["prompt"], "negative": r["negative"], "sel": s})
        self._set_options(opts, "offline build from presets")

    def _set_options(self, opts, src):
        self.create_opts = opts
        self.opt_pick.blockSignals(True); self.opt_pick.clear()
        for i in range(len(opts)):
            self.opt_pick.addItem(f"Option {i + 1}")
        self.opt_pick.blockSignals(False)
        self.opt_pick.setVisible(len(opts) > 1)
        self.create_status.setText(f"{len(opts)} option(s) · {src}" if opts else "No prompt returned – try Regenerate")
        self._show_option(0)
        for o in opts:
            self.store.add_history(o["prompt"], self.profile["name"], "create")

    def _show_option(self, i):
        if 0 <= i < len(self.create_opts):
            o = self.create_opts[i]
            self.c_prompt.setPlainText(o["prompt"]); self.c_neg.setPlainText(o.get("negative", ""))
        self._create_settings()

    def _cur_create(self):
        t = self.c_prompt.toPlainText().strip()
        if not t:
            self.notify("Nothing created yet", error=True)
        return t

    def c_copy(self):
        t = self._cur_create()
        if t:
            copy(t); self.notify("Prompt copied")

    def c_copy_neg(self):
        copy(self.c_neg.toPlainText()); self.notify("Negative prompt copied")

    def c_refine(self):
        t = self._cur_create()
        if t:
            self.set_work(t, "from Create"); self.go("Refine")

    def c_score(self):
        t = self._cur_create()
        if t:
            self.score_in.setPlainText(t); self.go("Score")

    def c_hist(self):
        t = self._cur_create()
        if t:
            self.store.add_history(t + (("\n\nNegative prompt: " + self.c_neg.toPlainText()) if self.c_neg.toPlainText().strip() else ""),
                                   self.profile["name"], "create"); self.notify("Saved to history")

    def c_fav(self):
        t = self._cur_create()
        if t:
            name = self.idea.toPlainText().strip()[:50] or "Created prompt"
            self.store.add_favourite(name, t); self.notify("Saved to favourites")

    def c_to_builder(self):
        t = self._cur_create()
        if not t:
            return
        i = self.opt_pick.currentIndex()
        if 0 <= i < len(self.create_opts) and self.create_opts[i].get("sel"):
            self.load_state({"sel": self.create_opts[i]["sel"]}); self.go("Builder"); self.notify("Loaded into Builder"); return
        self.an_in.setPlainText(t)
        if self.model.currentText():
            self.ai_analyse()
            self._pending_builder_load = True
            self.notify("Analysing with AI – it will load into the Builder")
        else:
            self.quick_analyse(); self.load_analysis()

    # ------------------------------------------------------------------ Quick bar (Ctrl+K)
    def open_quickbar(self):
        if not hasattr(self, "qbar"):
            self.qbar = QFrame(self.centralWidget()); self.qbar.setObjectName("card")
            ql = QHBoxLayout(self.qbar); ql.setContentsMargins(14, 10, 14, 10)
            self.qbar_in = QLineEdit(); self.qbar_in.setPlaceholderText("✨ Describe an image idea and press Enter…  (Esc to close)")
            f = QFont(); f.setPointSize(12); self.qbar_in.setFont(f)
            self.qbar_in.returnPressed.connect(self._quickbar_go)
            esc = QAction(self.qbar_in, shortcut=QKeySequence("Escape")); esc.triggered.connect(self.qbar.hide)
            self.qbar_in.addAction(esc)
            ql.addWidget(label("✨", "h2")); ql.addWidget(self.qbar_in, 1)
        W = self.centralWidget().width()
        self.qbar.setGeometry(int(W * 0.2), 70, int(W * 0.6), 64)
        self.qbar.show(); self.qbar.raise_(); self.qbar_in.setFocus(); self.qbar_in.selectAll()

    def _quickbar_go(self):
        t = self.qbar_in.text().strip()
        self.qbar.hide()
        if t:
            self.idea.setPlainText(t); self.go("Create"); self.create_generate()

    # ------------------------------------------------------------------ Builder
    def _builder_page(self):
        w, v = page("Builder", "Pick chips from the library – your prompt is formatted for the target model as you go.")
        split = QSplitter(); split.setChildrenCollapsible(False)
        v.addWidget(split, 1)

        cats = Card("Categories")
        self.cat_list = QListWidget(); self.cat_list.setObjectName("catList")
        self.cat_list.setMinimumWidth(190)
        cats.add(self.cat_list, 1)
        cats.add(hrow(button("🎲 Randomise", self.randomise, "primary", "Randomise unlocked categories"),
                      button("✨ Surprise", lambda: self.randomise(True), tip="Randomise everything")))
        cats.add(button("Clear all", self.clear_builder, "ghost"))
        split.addWidget(cats)

        mid = Card()
        self.cat_title = label("", "h2")
        self.lock_btn = button("🔓 Lock", self.toggle_lock, "ghost", "Locked categories keep their value when randomising")
        mid.add(hrow(self.cat_title, None, self.lock_btn))
        self.search = QLineEdit(); self.search.setPlaceholderText(f"🔍  Search {self.lib.count()} presets in all categories…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search_changed)
        mid.add(self.search)
        self.sel_wrap = QWidget(); self.sel_flow = FlowLayout(self.sel_wrap, 6)
        mid.add(self.sel_wrap)
        self.chip_stack = QStackedWidget()
        mid.add(self.chip_stack, 1)
        self.cat_pages = {}
        self.search_page = QWidget(); self.search_flow = FlowLayout(self.search_page, 6)
        self.chip_stack.addWidget(scroll(self.search_page))
        self.custom = QLineEdit(); self.custom.setPlaceholderText("Add your own to this category and press Enter…")
        self.custom.returnPressed.connect(self.add_custom)
        mid.add(hrow(self.custom, button("＋ Add", self.add_custom)))
        split.addWidget(mid)

        right = Card("Output")
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(8)
        self.aspect = QComboBox(); self.aspect.addItems(profiles.ASPECTS)
        self.aspect.setCurrentText(self.store.get("aspect", "1:1"))
        self.aspect.currentTextChanged.connect(lambda a: (self.store.set("aspect", a),
                                                          getattr(self, "_restoring_img", False) or not hasattr(self, "be_status")
                                                          or self.save_profile_image(aspect=a), self.update_preview(), self._create_profile_refresh()))
        self.emph = QCheckBox("Emphasise subject"); self.emph.toggled.connect(self.update_preview)
        g.addWidget(label("Aspect"), 0, 0); g.addWidget(self.aspect, 0, 1); g.addWidget(self.emph, 0, 2)
        self.negpreset = QComboBox(); self.negpreset.addItems(list(NEGATIVE_PRESETS))
        self.negpreset.currentTextChanged.connect(self._neg_preset)
        g.addWidget(label("Negative"), 1, 0); g.addWidget(self.negpreset, 1, 1, 1, 2)
        right.add(g)
        self.negative = QPlainTextEdit(); self.negative.setFixedHeight(54)
        self.negative.textChanged.connect(self.update_preview)
        right.add(self.negative)
        self.neg_hint = label("", "hint", wrap=True); right.add(self.neg_hint)
        self.mj_box = QWidget(); mg = QHBoxLayout(self.mj_box); mg.setContentsMargins(0, 0, 0, 0)
        self.stylize = QSpinBox(); self.stylize.setRange(0, 1000); self.stylize.setValue(100); self.stylize.setPrefix("--s ")
        self.chaos = QSpinBox(); self.chaos.setRange(0, 100); self.chaos.setPrefix("--c ")
        self.exp = QSpinBox(); self.exp.setRange(0, 100); self.exp.setPrefix("--exp ")
        self.raw = QCheckBox("raw"); self.draft = QCheckBox("draft")
        for wdg in (self.stylize, self.chaos, self.exp):
            wdg.valueChanged.connect(self.update_preview); mg.addWidget(wdg)
        for wdg in (self.raw, self.draft):
            wdg.toggled.connect(self.update_preview); mg.addWidget(wdg)
        right.add(self.mj_box)
        self.extra = QLineEdit(); self.extra.setPlaceholderText("Extra details, e.g. 'wearing a red scarf'")
        self.extra.textChanged.connect(self.update_preview)
        right.add(self.extra)
        right.add(hrow(label("Prompt", "h2"), None, self._score_badge()))
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True)
        f = QFont(); f.setPointSize(11); self.preview.setFont(f)
        right.add(self.preview, 1)
        self.neg_view = label("", "muted", wrap=True); self.neg_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.settings_view = label("", "hint", wrap=True); self.settings_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.notes_view = label("", "hint", wrap=True)
        for x in (self.neg_view, self.settings_view, self.notes_view):
            right.add(x)
        self.profile_tips = label("", "hint", wrap=True); right.add(self.profile_tips)
        right.add(hrow(button("📋 Copy prompt", self.copy_prompt, "primary"), button("Copy negative", self.copy_negative),
                       button("⭐", self.save_fav, tip="Save favourite")))
        right.add(hrow(button("💬 Refine with AI", lambda: self.send_to("Refine")),
                       button("📊 Score", lambda: self.send_to("Score")),
                       button("🖼 Generate", lambda: self.generate_image(self.build_result()["prompt"], self.build_result()["negative"]))))
        split.addWidget(right)
        split.setSizes([210, 620, 520])

        for cat in self.lib.categories:
            self.cat_list.addItem(QListWidgetItem(cat))
        self.cat_list.currentRowChanged.connect(self._show_cat)
        self.cat_list.setCurrentRow(0)
        self._neg_preset("Model default")
        QTimer.singleShot(0, self._profile_changed)
        return w

    def _score_badge(self):
        self.live_score = button("Score –", lambda: self.send_to("Score"), "ghost", "Quick offline score – click for details")
        return self.live_score

    def _cat_page(self, cat):
        if cat in self.cat_pages:
            return self.cat_pages[cat]
        wrap = QWidget(); vl = QVBoxLayout(wrap); vl.setContentsMargins(0, 0, 6, 0); vl.setSpacing(4)
        for group, items in self.lib.categories.get(cat, {}).items():
            vl.addWidget(label(group.upper(), "groupLabel"))
            holder = QWidget(); fl = FlowLayout(holder, 6)
            for it in items:
                fl.addWidget(self._make_chip(cat, it))
            vl.addWidget(holder)
        vl.addStretch()
        sc = scroll(wrap)
        self.chip_stack.addWidget(sc)
        self.cat_pages[cat] = sc
        return sc

    def _make_chip(self, cat, item, show_cat=False):
        c = chip(f"{item}" + (f"  · {cat}" if show_cat else ""), item in self.sel.get(cat, []))
        c.toggled.connect(lambda on, cat=cat, item=item: self.toggle_item(cat, item, on))
        self.chip_map.setdefault((cat, item), []).append(c)
        c.destroyed.connect(lambda *_, k=(cat, item), c=c: self._forget_chip(k, c))
        return c

    def _forget_chip(self, key, c):
        lst = self.chip_map.get(key, [])
        if c in lst:
            lst.remove(c)

    def _show_cat(self, row):
        if row < 0:
            return
        cat = list(self.lib.categories)[row]
        self.current_cat = cat
        self.cat_title.setText(cat)
        self.lock_btn.setText("🔒 Locked" if cat in self.locks else "🔓 Lock")
        if self.search.text():
            self.search.clear()
        self.chip_stack.setCurrentWidget(self._cat_page(cat))

    def _search_changed(self, q):
        if not q.strip():
            self._show_cat(self.cat_list.currentRow()); return
        self.search_flow.clear()
        res = self.lib.search(q, 250)
        for cat, it in res:
            self.search_flow.addWidget(self._make_chip(cat, it, show_cat=True))
        if not res:
            self.search_flow.addWidget(label("No presets match – type it in 'Add your own' below.", "muted"))
        self.cat_title.setText(f"Search · {len(res)} result(s)")
        self.chip_stack.setCurrentIndex(0)

    def toggle_item(self, cat, item, on):
        lst = self.sel.setdefault(cat, [])
        if on and item not in lst:
            lst.append(item)
        elif not on and item in lst:
            lst.remove(item)
        if not lst:
            self.sel.pop(cat, None)
        self._sync_chips()

    def _sync_chips(self):
        for (cat, item), lst in list(self.chip_map.items()):
            state = item in self.sel.get(cat, [])
            for c in lst:
                try:
                    if c.isChecked() != state:
                        c.blockSignals(True); c.setChecked(state); c.blockSignals(False)
                except RuntimeError:
                    pass
        self.sel_flow.clear()
        for cat in self.lib.categories:
            for it in self.sel.get(cat, []):
                b = button(f"{it}  ✕", lambda _=False, c=cat, i=it: self.toggle_item(c, i, False), "selChip", f"{cat} – click to remove")
                self.sel_flow.addWidget(b)
        for row, cat in enumerate(self.lib.categories):
            n = len(self.sel.get(cat, []))
            self.cat_list.item(row).setText(("🔒 " if cat in self.locks else "") + cat + (f"   ●{n}" if n else ""))
        self.update_preview()

    def toggle_lock(self):
        c = self.current_cat
        (self.locks.discard if c in self.locks else self.locks.add)(c)
        self.store.set("locks", sorted(self.locks))
        self.lock_btn.setText("🔒 Locked" if c in self.locks else "🔓 Lock")
        self._sync_chips()

    def add_custom(self):
        t = self.custom.text().strip()
        if not t:
            return
        cat = self.current_cat
        self.lib.add_custom(cat, t)
        if cat in self.cat_pages:  # rebuild page to include new chip
            self.chip_stack.removeWidget(self.cat_pages[cat]); self.cat_pages.pop(cat).deleteLater()
            self.chip_stack.setCurrentWidget(self._cat_page(cat))
        self.custom.clear()
        self.toggle_item(cat, t, True)
        self.notify(f"Added '{t}' to {cat} (saved in My presets)")

    def _neg_preset(self, key):
        val = NEGATIVE_PRESETS.get(key)
        self.negative.setPlainText(self.profile.get("negative_default", "").strip() if val is None else val)

    def build_kwargs(self):
        return dict(extra=self.extra.text(), negative=self.negative.toPlainText(), aspect=self.aspect.currentText(),
                    emphasis=self.emph.isChecked() and self.emph.isEnabled(),
                    mj={"stylize": self.stylize.value(), "chaos": self.chaos.value(), "exp": self.exp.value(),
                        "raw": self.raw.isChecked(), "draft": self.draft.isChecked()})

    def build_result(self, sel=None):
        return builder.build(self.sel if sel is None else sel, self.profile, **self.build_kwargs())

    def current_text(self):
        return builder.as_text(self.build_result()) if self.sel or self.extra.text() else ""

    def update_preview(self, *_):
        if not hasattr(self, "settings_view"):
            return
        r = self.build_result()
        self.preview.setPlainText(r["prompt"] if (self.sel or self.extra.text()) else "")
        self.neg_view.setText(("<b>Negative:</b> " + html.escape(r["negative"])) if r["negative"] and self.sel else "")
        self.settings_view.setText(("⚙ " + html.escape(r["settings"])) if r["settings"] else "")
        self.notes_view.setText(" ".join(r["notes"]))
        if self.sel or self.extra.text():
            s = scoring.heuristic_score(r["prompt"], self.profile, self.lib.all_items())
            self.live_score.setText(f"Score {s['total']} · {scoring.grade(s['total'])}")
        else:
            self.live_score.setText("Score –")

    def randomise(self, all_=False):
        cats = [c for c in self.lib.categories if all_ or c not in self.locks]
        base = {} if all_ else {c: v for c, v in self.sel.items() if c in self.locks}
        if not all_:
            # keep empty-by-choice categories empty unless core ones
            core = ["Subject", "Action / pose", "Setting", "Style", "Lighting", "Camera", "Mood", "Color palette"]
            cats = [c for c in cats if c in core or c in self.sel]
        self.sel = builder.randomize(base, cats, self.lib.all_items())
        self._sync_chips()

    def clear_builder(self):
        self.sel = {}; self.extra.clear(); self._sync_chips()

    def copy_prompt(self):
        r = self.build_result()
        copy(r["prompt"]); self.store.add_history(r["prompt"], self.profile["name"], "builder")
        self.notify("Prompt copied · saved to history")

    def copy_negative(self):
        copy(self.build_result()["negative"]); self.notify("Negative prompt copied")

    def state(self):
        return {"sel": self.sel, "extra": self.extra.text(), "profile": self.profile["id"],
                "aspect": self.aspect.currentText(), "negative": self.negative.toPlainText()}

    def load_state(self, s):
        self.sel = builder.norm_sel(s.get("sel", {}))
        self.extra.setText(s.get("extra", ""))
        if s.get("profile"):
            i = self.profile_combo.findData(s["profile"])
            if i >= 0:
                self.profile_combo.setCurrentIndex(i)
        if s.get("aspect"):
            self.aspect.setCurrentText(s["aspect"])
        if "negative" in s:
            self.negative.setPlainText(s["negative"])
        self._sync_chips()

    def save_fav(self):
        name, ok = QInputDialog.getText(self, "Save favourite", "Name:", text=(self.sel.get("Subject") or ["My prompt"])[0])
        if ok:
            self.store.add_favourite(name, self.build_result()["prompt"], self.state())
            self.notify("Saved to favourites")

    def send_to(self, where):
        text = self.build_result()["prompt"]
        if where == "Refine":
            self.set_work(text, "from Builder")
        else:
            self.score_in.setPlainText(text)
        self.go(where)

    # ------------------------------------------------------------------ Refine (chat)
    def _refine_page(self):
        w, v = page("Refine", "Chat with your local AI about the working prompt. Apply suggestions, compare and revert versions.")
        split = QSplitter(); split.setChildrenCollapsible(False); v.addWidget(split, 1)
        chat = Card("Conversation")
        self.thread_view = QTextBrowser(); self.thread_view.setOpenLinks(False)
        self.thread_view.anchorClicked.connect(self._thread_link)
        chat.add(self.thread_view, 1)
        qa = QHBoxLayout()
        for a in ollama.ACTIONS:
            qa.addWidget(self.ai_btn(a, lambda _=False, a=a: self.quick_action(a)))
        self.nvar = QSpinBox(); self.nvar.setRange(2, 12); self.nvar.setValue(4); self.nvar.setPrefix("× ")
        qa.addWidget(self.nvar); qa.addStretch()
        chat.add(qa)
        self.chat_in = QPlainTextEdit(); self.chat_in.setFixedHeight(70)
        self.chat_in.setPlaceholderText("Ask for changes, e.g. 'make it moodier and move the camera lower'  (Ctrl+Enter to send)")
        send = QAction(self.chat_in, shortcut=QKeySequence("Ctrl+Return")); send.triggered.connect(self.send_chat)
        self.chat_in.addAction(send)
        chat.add(self.chat_in)
        chat.add(hrow(button("New chat", self.new_chat, "ghost"), None, self.stop_btn(),
                      self.ai_btn("Send ➤", self.send_chat, "primary")))
        split.addWidget(chat)

        side = Card("Working prompt")
        self.work = QPlainTextEdit(); self.work.setMinimumHeight(160)
        side.add(self.work, 1)
        side.add(hrow(button("📋 Copy", lambda: (copy(self.work.toPlainText()), self.notify("Copied"))),
                      button("💾 Save version", lambda: (self.store.add_version(self.work.toPlainText(), "manual edit"),
                                                         self.load_versions(), self.notify("Version saved"))),
                      button("📊 Score", lambda: (self.score_in.setPlainText(self.work.toPlainText()), self.go("Score")))))
        side.add(label("Version history", "h2"))
        side.add(label("Double-click a version to restore it.", "hint"))
        self.version_list = QListWidget(); self.version_list.setWordWrap(True)
        self.version_list.itemDoubleClicked.connect(self._restore_version)
        side.add(self.version_list, 1)
        side.add(hrow(button("↶ Revert to previous", self.revert_previous), None,
                      button("Clear", lambda: (self.store.clear_versions(), self.load_versions()), "ghost")))
        split.addWidget(side)
        split.setSizes([700, 480])
        self.load_versions()
        self.render_thread()
        return w

    def set_work(self, text, note):
        cur = self.work.toPlainText().strip()
        if cur and cur != text.strip():
            self.store.add_version(cur, "before: " + note)
        self.work.setPlainText(text)
        self.store.add_version(text, note)
        self.load_versions()

    def load_versions(self):
        self.version_list.clear()
        for vid, ts, prompt, note in self.store.versions():
            it = QListWidgetItem(f"{time.strftime('%d %b %H:%M', time.localtime(ts))} · {note}\n{prompt[:180]}")
            it.setData(Qt.UserRole, prompt); self.version_list.addItem(it)

    def _restore_version(self, it):
        self.set_work(it.data(Qt.UserRole), "restored version"); self.notify("Version restored")

    def revert_previous(self):
        cur = self.work.toPlainText().strip()
        for vid, ts, prompt, note in self.store.versions():
            if prompt.strip() != cur:
                self.set_work(prompt, "reverted"); self.notify("Reverted to previous version"); return
        self.notify("No earlier version", error=True)

    def render_thread(self, streaming=None):
        c = theme.colors(getattr(self, "theme", "dark"))
        parts = [f"<div style='color:{c['muted']}'>Target model: <b>{html.escape(self.profile['name'])}</b>. "
                 f"Ask anything about the working prompt on the right.</div>"]
        msgs = self.chat + ([{"role": "assistant", "content": streaming}] if streaming is not None else [])
        sidx = 0
        for m in msgs:
            mine = m["role"] == "user"
            bg = c["accent_soft"] if mine else c["raised"]
            body = html.escape(m["content"]).replace("\n", "<br>")
            body = body.replace("&lt;prompt&gt;", f"<div style='background:{c['card']};border:1px solid {c['accent']};padding:8px;margin:6px 0'><code>")
            body = body.replace("&lt;/prompt&gt;", "</code></div>")
            is_stream = streaming is not None and m is msgs[-1]
            if not mine and not is_stream:
                sugg = builder.extract_prompt(m["content"])
                if sugg:
                    body += (f"<br><a href='apply:{sidx}' style='color:{c['accent']};font-weight:600'>✓ Apply this suggestion</a>"
                             f" &nbsp; <a href='copy:{sidx}' style='color:{c['muted']}'>Copy</a>")
                    sidx += 1
            who = "You" if mine else "AI"
            parts.append(f"<table width='100%' cellpadding='10' style='margin:6px 0'><tr>"
                         f"{'<td width=15%></td>' if mine else ''}<td style='background:{bg};border-radius:10px'>"
                         f"<b style='color:{c['muted']}'>{who}</b><br>{body}</td>{'' if mine else '<td width=15%></td>'}</tr></table>")
        self.thread_view.setHtml("".join(parts))
        self.thread_view.verticalScrollBar().setValue(self.thread_view.verticalScrollBar().maximum())

    def _suggestions(self):
        return [s for s in (builder.extract_prompt(m["content"]) for m in self.chat if m["role"] == "assistant") if s]

    def _thread_link(self, url):
        kind, _, idx = url.toString().partition(":")
        s = self._suggestions()
        if not idx.isdigit() or int(idx) >= len(s):
            return
        if kind == "apply":
            self.set_work(s[int(idx)], "AI suggestion"); self.notify("Suggestion applied – use Revert to undo")
        else:
            copy(s[int(idx)]); self.notify("Copied")

    def send_chat(self, text=None):
        text = (text if isinstance(text, str) else self.chat_in.toPlainText()).strip()
        if not text:
            return
        if not self.work.toPlainText().strip():
            self.work.setPlainText(self.current_text())
        self.chat.append({"role": "user", "content": text})
        self.chat_in.clear()
        buf = []

        def chunk(c):
            buf.append(c); self.render_thread("".join(buf))

        def done(t):
            self.chat.append({"role": "assistant", "content": t}); self.render_thread()
        if not self.run_ai(ollama.chat_messages(self.chat, self.work.toPlainText(), self.profile), chunk, done):
            self.chat.pop(); self.chat_in.setPlainText(text)
        else:
            self.render_thread("…")

    def quick_action(self, action):
        n = self.nvar.value()
        msg = ollama.ACTIONS[action].format(n=n)
        if action == "Variations":
            msg = (f"Write {n} distinct variations of the current prompt, each changing setting, style or mood. "
                   f"Number them, and put the one you like best inside <prompt></prompt>.")
        self.send_chat(msg)

    def new_chat(self):
        self.chat = []; self.render_thread()

    # ------------------------------------------------------------------ Analyse
    def _analyse_page(self):
        w, v = page("Analyse", "Paste any prompt – break it into categories and load it into the Builder.")
        top = Card("Prompt to analyse")
        self.an_in = QPlainTextEdit(); self.an_in.setPlaceholderText("Paste a prompt you found or wrote…")
        top.add(self.an_in, 1)
        top.add(hrow(button("⚡ Quick analyse (offline)", self.quick_analyse),
                     self.ai_btn("🧠 Analyse with AI", self.ai_analyse, "primary"), self.stop_btn(), None))
        v.addWidget(top, 1)
        res = Card("Breakdown")
        self.an_view = QTextBrowser(); res.add(self.an_view, 1)
        res.add(hrow(button("↩ Load into Builder", self.load_analysis, "primary"),
                     button("Add unknown phrases to My presets", self.analysis_to_custom), None))
        v.addWidget(res, 2)
        self.analysis = {}
        return w

    def quick_analyse(self):
        text = self.an_in.toPlainText().lower()
        sel = {}
        for cat, items in self.lib.all_items().items():
            hits = [i for i in items if len(i) > 3 and scoring._has(text, i.lower())]
            hits = [h for h in hits if not any(h != o and h.lower() in o.lower() for o in hits)]
            if hits:
                sel[cat] = hits[:4]
        self.analysis = {"sel": sel, "extra": ""}
        self._show_analysis("Matched against your preset library (no AI).")

    def ai_analyse(self):
        text = self.an_in.toPlainText().strip()
        if not text:
            return
        self.an_view.setPlainText("Analysing…")
        def done(t):
            try:
                data = builder.parse_json_loose(t)
            except ValueError as e:
                self.notify(f"Couldn't read AI reply: {e}", error=True); self.an_view.setPlainText(t); return
            extra = data.get("Extra") or []
            self.analysis = {"sel": builder.analysis_to_selection(data, list(self.lib.categories)),
                             "extra": ", ".join(extra) if isinstance(extra, list) else str(extra)}
            self._show_analysis("Analysed by " + self.model.currentText())
            if getattr(self, "_pending_builder_load", False):
                self._pending_builder_load = False; self.load_analysis()
        self.run_ai(ollama.analysis_messages(text, list(self.lib.categories)), lambda c: None, done,
                    json_mode=True, temperature=0.1)

    def _show_analysis(self, src):
        sel = self.analysis.get("sel", {})
        known = self.lib.all_items()
        rows = []
        for cat in self.lib.categories:
            if sel.get(cat):
                chips = " ".join(("● " if i in known.get(cat, []) else "○ ") + html.escape(i) + " &nbsp;" for i in sel[cat])
                rows.append(f"<tr><td style='padding:4px 12px 4px 0'><b>{cat}</b></td><td>{chips}</td></tr>")
        if self.analysis.get("extra"):
            rows.append(f"<tr><td><b>Extra</b></td><td>{html.escape(self.analysis['extra'])}</td></tr>")
        self.an_view.setHtml(f"<p><i>{src}</i> &nbsp; ● in library · ○ new phrase</p><table>{''.join(rows) or '<tr><td>Nothing recognised.</td></tr>'}</table>")

    def load_analysis(self):
        if not self.analysis:
            self.notify("Analyse a prompt first", error=True); return
        self.load_state({"sel": self.analysis["sel"], "extra": self.analysis.get("extra", "")})
        self.go("Builder"); self.notify("Loaded into the Builder")

    def analysis_to_custom(self):
        known, n = self.lib.all_items(), 0
        for cat, items in self.analysis.get("sel", {}).items():
            for i in items:
                if i not in known.get(cat, []):
                    self.lib.add_custom(cat, i); n += 1
        self._reset_chip_pages()
        self.notify(f"Added {n} phrase(s) to My presets")

    def _reset_chip_pages(self):
        for cat, pg in list(self.cat_pages.items()):
            self.chip_stack.removeWidget(pg); pg.deleteLater()
        self.cat_pages = {}
        if hasattr(self, "current_cat"):
            self.chip_stack.setCurrentWidget(self._cat_page(self.current_cat))

    # ------------------------------------------------------------------ Score
    def _score_page(self):
        w, v = page("Score", "Rubric: clarity, specificity, composition, style coherence and fit for the target model.")
        top = Card("Prompt")
        self.score_in = QPlainTextEdit(); self.score_in.setFixedHeight(110)
        self.score_in.textChanged.connect(lambda: self.score_timer.start(250))
        self.score_timer = QTimer(self, singleShot=True, timeout=self.quick_score)
        top.add(self.score_in)
        top.add(hrow(button("Use Builder prompt", lambda: self.score_in.setPlainText(self.build_result()["prompt"])),
                     button("Use working prompt", lambda: self.score_in.setPlainText(self.work.toPlainText())), None,
                     self.stop_btn(), self.ai_btn("🧠 Deep score with AI", self.ai_score, "primary")))
        v.addWidget(top)
        row = QHBoxLayout(); row.setSpacing(14)
        quick = Card("Quick score · offline")
        self.big = label("–", "scoreBig"); self.grade = label("", "muted")
        quick.add(hrow(self.big, self.grade, None))
        self.bars = {k: ScoreBar(k) for k in scoring.RUBRIC}
        for b in self.bars.values():
            quick.add(b)
        quick.add(label("Fixes", "h2"))
        self.fix_view = label("", wrap=True); self.fix_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        quick.add(self.fix_view); quick.lay.addStretch()
        row.addWidget(scroll(quick), 1)
        deep = Card("AI review")
        self.ai_score_view = QTextBrowser(); deep.add(self.ai_score_view, 1)
        self.use_improved = button("Use improved prompt in Refine", self._use_improved); self.use_improved.setEnabled(False)
        deep.add(self.use_improved)
        row.addWidget(deep, 1)
        v.addLayout(row, 1)
        self.improved = ""
        return w

    def quick_score(self):
        text = self.score_in.toPlainText()
        if not text.strip():
            self.big.setText("–"); return
        s = scoring.heuristic_score(text, self.profile, self.lib.all_items())
        self.big.setText(str(s["total"])); self.grade.setText(f"/ 100 · {scoring.grade(s['total'])} for {self.profile['name']}")
        for k, (val, note) in s["criteria"].items():
            self.bars[k].set(val, note)
        self.fix_view.setText("\n".join("• " + f for f in s["fixes"]) or "Nothing obvious to fix – nice prompt!")

    def ai_score(self):
        text = self.score_in.toPlainText().strip()
        if not text:
            return
        self.ai_score_view.setPlainText("Reviewing…")
        def done(t):
            try:
                d = builder.parse_json_loose(t)
            except ValueError:
                self.ai_score_view.setPlainText(t); return
            sc = d.get("scores", {})
            rows, total = [], 0
            for k in scoring.RUBRIC:
                e = sc.get(k) or {}
                n = e.get("score", 0) if isinstance(e, dict) else e
                try:
                    n = max(0, min(10, int(float(n))))
                except (TypeError, ValueError):
                    n = 0
                total += n
                rows.append(f"<tr><td style='padding:3px 10px 3px 0'><b>{k}</b></td><td>{n}/10</td>"
                            f"<td style='padding-left:10px'>{html.escape(str(e.get('why', '')) if isinstance(e, dict) else '')}</td></tr>")
            fixes = "".join(f"<li>{html.escape(str(f))}</li>" for f in d.get("fixes", []))
            self.improved = str(d.get("improved_prompt", "")).strip()
            self.ai_score_view.setHtml(f"<h2>{total * 2} / 100</h2><table>{''.join(rows)}</table><h3>Fixes</h3><ul>{fixes}</ul>"
                                       + (f"<h3>Improved prompt</h3><p>{html.escape(self.improved)}</p>" if self.improved else ""))
            self.use_improved.setEnabled(bool(self.improved))
        self.run_ai(ollama.score_messages(text, self.profile), lambda c: None, done, json_mode=True, temperature=0.2)

    def _use_improved(self):
        self.set_work(self.improved, "AI score suggestion"); self.go("Refine")

    # ------------------------------------------------------------------ Templates
    def _templates_page(self):
        w, v = page("Templates", "Placeholders: " + " ".join("{" + p + "}" for p in PLACEHOLDERS) +
                    " – filled from Builder choices, or randomly when empty.")
        row = QHBoxLayout(); row.setSpacing(14); v.addLayout(row, 1)
        left = Card("Your templates")
        self.tpl_list = QListWidget(); self.tpl_list.currentItemChanged.connect(self._tpl_selected)
        left.add(self.tpl_list, 1)
        left.add(hrow(button("＋ New", self.tpl_new), ConfirmButton("🗑 Delete", self.tpl_delete, "Confirm delete", 4, "danger")))
        row.addWidget(left, 1)
        right = Card("Edit")
        self.tpl_name = QLineEdit(); self.tpl_name.setPlaceholderText("Template name")
        self.tpl_body = QPlainTextEdit()
        right.add(self.tpl_name); right.add(self.tpl_body, 1)
        right.add(hrow(button("💾 Save", self.tpl_save, "primary"), button("▶ Fill from Builder", self.tpl_fill),
                       button("🎲 Fill randomly", lambda: self.tpl_fill(True)), None))
        self.tpl_out = QPlainTextEdit(); right.add(label("Result", "h2")); right.add(self.tpl_out, 1)
        right.add(hrow(button("📋 Copy", lambda: (copy(self.tpl_out.toPlainText()),
                                                 self.store.add_history(self.tpl_out.toPlainText(), self.profile["name"], "template"),
                                                 self.notify("Copied"))),
                       button("💬 Refine", lambda: (self.set_work(self.tpl_out.toPlainText(), "from template"), self.go("Refine"))),
                       button("📊 Score", lambda: (self.score_in.setPlainText(self.tpl_out.toPlainText()), self.go("Score"))), None))
        row.addWidget(right, 2)
        self.load_templates()
        return w

    def load_templates(self, select=None):
        self.tpl_list.clear()
        for tid, name, body in self.store.templates():
            it = QListWidgetItem(name); it.setData(Qt.UserRole, (tid, name, body)); self.tpl_list.addItem(it)
            if name == select:
                self.tpl_list.setCurrentItem(it)

    def _tpl_selected(self, it, _=None):
        if it:
            _, n, b = it.data(Qt.UserRole); self.tpl_name.setText(n); self.tpl_body.setPlainText(b)

    def tpl_new(self):
        self.tpl_list.setCurrentItem(None)
        self.tpl_name.setText("New template"); self.tpl_body.setPlainText("{subject} {action} {setting}, {style}, {lighting}")

    def tpl_save(self):
        name = self.tpl_name.text().strip()
        if not name:
            return
        it = self.tpl_list.currentItem()
        try:
            self.store.save_template(name, self.tpl_body.toPlainText(), it.data(Qt.UserRole)[0] if it else None)
        except Exception as e:  # noqa: BLE001
            self.notify(f"Couldn't save: {e}", error=True); return
        self.load_templates(name); self.notify("Template saved")

    def tpl_delete(self):
        it = self.tpl_list.currentItem()
        if it:
            self.store.delete_template(it.data(Qt.UserRole)[0]); self.load_templates(); self.notify(f"Deleted '{it.text()}'")

    def tpl_fill(self, random_=False):
        sel = {} if random_ else self.sel
        vals = {k: sel.get(c) for k, c in PLACEHOLDERS.items()}
        self.tpl_out.setPlainText(builder.fill_template(self.tpl_body.toPlainText(), vals, self.lib.all_items()))

    # ------------------------------------------------------------------ Batch
    def _batch_page(self):
        w, v = page("Batch", "Generate many variations at once, formatted for the target model.")
        opts = Card("Randomise these categories (others keep your Builder choices)")
        holder = QWidget(); fl = FlowLayout(holder, 6)
        self.batch_cats = {}
        for c in self.lib.categories:
            b = chip(c, c in ("Style", "Lighting", "Mood", "Color palette")); self.batch_cats[c] = b; fl.addWidget(b)
        opts.add(holder)
        self.batch_rand = QRadioButton("From presets"); self.batch_rand.setChecked(True)
        self.batch_ai = QRadioButton("AI variations")
        self.batch_n = QSpinBox(); self.batch_n.setRange(1, 200); self.batch_n.setValue(10); self.batch_n.setPrefix("× ")
        self.batch_presets = QCheckBox(tr("Keep ticked characters & styles (Presets) on every variation"))
        self.batch_presets.setChecked(self.store.get("batch_presets", False))
        self.batch_presets.toggled.connect(lambda on: self.store.set("batch_presets", on))
        opts.add(hrow(self.batch_rand, self.batch_ai, self.batch_n, self.batch_presets, None, self.stop_btn(),
                      self.ai_btn("🔁 Generate", self.batch_generate, "primary")))
        v.addWidget(opts)
        res = Card("Results · double-click to copy")
        self.batch_list = QListWidget(); self.batch_list.setWordWrap(True)
        self.batch_list.itemDoubleClicked.connect(lambda it: (copy(it.text()), self.notify("Copied")))
        res.add(self.batch_list, 1)
        res.add(hrow(button("📋 Copy all", lambda: (copy(builder.export_txt(self.batch_items())), self.notify("All copied"))),
                     button("💾 Export .txt", lambda: self.batch_export("txt")),
                     button("💾 Export .csv", lambda: self.batch_export("csv")), None))
        v.addWidget(res, 1)
        return w

    def _batch_presets(self, items):
        if not self.batch_presets.isChecked():
            return items
        from . import presets
        chars, styles = self.active_presets()
        return presets.apply_to_batch(items, chars, styles, self.profile) if (chars or styles) else items

    def batch_items(self):
        return [self.batch_list.item(i).text() for i in range(self.batch_list.count())]

    def batch_generate(self):
        self.batch_list.clear()
        n = self.batch_n.value()
        if self.batch_rand.isChecked():
            cats = [c for c, b in self.batch_cats.items() if b.isChecked()]
            kw = self.build_kwargs()
            items = self._batch_presets(builder.batch_variations(self.sel, cats, n, self.lib.all_items(), self.profile, kw, seed=time.time_ns()))
            for p in items:
                self.batch_list.addItem(p); self.store.add_history(p, self.profile["name"], "batch")
            self.notify(f"Generated {len(items)} variations"); return
        base = self.build_result()["prompt"] or self.work.toPlainText()

        def done(t):
            for p in self._batch_presets(builder.parse_ai_list(t)[:n]):
                self.batch_list.addItem(p); self.store.add_history(p, self.profile["name"], "batch:ai")
            self.notify(f"{self.batch_list.count()} AI variations ready")
        self.run_ai(ollama.action_messages("Variations", base, self.profile, n), lambda c: None, done, temperature=0.9)

    def batch_export(self, kind):
        items = self.batch_items()
        if not items:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export", os.path.join(APP_DIR, f"prompts.{kind}"), f"*.{kind}")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(builder.export_txt(items) if kind == "txt" else builder.export_csv(items))
            self.notify(f"Exported {len(items)} prompts")

    # ------------------------------------------------------------------ History & favourites
    def _history_page(self):
        w, v = page("History", "Everything you copy or generate is kept here.")
        c = Card()
        self.hist_search = QLineEdit(); self.hist_search.setPlaceholderText("🔍  Search history (text or model)…")
        self.hist_search.setClearButtonEnabled(True); self.hist_search.textChanged.connect(self.load_history)
        c.add(self.hist_search)
        self.hist_list = QListWidget(); self.hist_list.setWordWrap(True)
        self.hist_list.itemDoubleClicked.connect(lambda it: (copy(it.data(Qt.UserRole)[1]), self.notify("Copied")))
        c.add(self.hist_list, 1)
        c.add(hrow(button("📋 Copy", self.hist_copy, "primary"), button("💬 Refine", self.hist_refine),
                   button("📊 Score", self.hist_score), None, ConfirmButton("🗑 Delete", self.hist_delete, "Confirm delete", 4, "danger"),
                   self._hist_clear_btn()))
        v.addWidget(c, 1)
        return w

    def load_history(self, *_):
        self.hist_list.clear()
        for hid, ts, prompt, fmt, src in self.store.history(self.hist_search.text()):
            it = QListWidgetItem(f"{time.strftime('%d %b %H:%M', time.localtime(ts))} · {src}{' · ' + fmt if fmt else ''}\n{prompt}")
            it.setData(Qt.UserRole, (hid, prompt)); self.hist_list.addItem(it)

    def _hist(self):
        it = self.hist_list.currentItem(); return it.data(Qt.UserRole) if it else None

    def hist_copy(self):
        h = self._hist()
        if h:
            copy(h[1]); self.notify("Copied")

    def hist_refine(self):
        h = self._hist()
        if h:
            self.set_work(h[1], "from history"); self.go("Refine")

    def hist_score(self):
        h = self._hist()
        if h:
            self.score_in.setPlainText(h[1]); self.go("Score")

    def hist_delete(self):
        h = self._hist()
        if h:
            self.store.delete_history(h[0]); self.load_history(); self.notify("Deleted")

    def _hist_clear_btn(self):
        self.hist_clear_btn = ConfirmButton("Clear all", self.hist_clear, "Confirm clear", 4, "ghost",
                                            "Delete all history – click twice to confirm")
        return self.hist_clear_btn

    def hist_clear(self):
        self.store.clear_history(); self.load_history(); self.notify(tr("History cleared"))

    def _fav_page(self):
        w, v = page("Favourites", "Saved Builder setups and prompts.")
        c = Card()
        self.fav_list = QListWidget(); self.fav_list.setWordWrap(True)
        self.fav_list.itemDoubleClicked.connect(lambda *_: self.fav_load())
        c.add(self.fav_list, 1)
        c.add(hrow(button("📋 Copy", self.fav_copy, "primary"), button("↩ Load into Builder", self.fav_load), None,
                   ConfirmButton("🗑 Delete", self.fav_delete, "Confirm delete", 4, "danger")))
        v.addWidget(c, 1)
        return w

    def load_favs(self):
        self.fav_list.clear()
        for fid, ts, name, prompt, st in self.store.favourites():
            it = QListWidgetItem(f"⭐ {name}\n{prompt}"); it.setData(Qt.UserRole, (fid, prompt, st)); self.fav_list.addItem(it)

    def _fav(self):
        it = self.fav_list.currentItem(); return it.data(Qt.UserRole) if it else None

    def fav_copy(self):
        f = self._fav()
        if f:
            copy(f[1]); self.notify("Copied")

    def fav_load(self):
        f = self._fav()
        if not f:
            return
        s = json.loads(f[2] or "{}")
        if s.get("sel"):
            self.load_state(s); self.go("Builder")
        else:
            self.set_work(f[1], "from favourite"); self.go("Refine")

    def fav_delete(self):
        f = self._fav()
        if f:
            self.store.delete_favourite(f[0]); self.load_favs(); self.notify("Deleted")

    # ------------------------------------------------------------------ Packs
    def _packs_page(self):
        w, v = page("Preset packs", "Turn packs on or off, import packs from friends, or export your own.")
        c = Card()
        self.pack_list = QListWidget(); self.pack_list.setWordWrap(True)
        self.pack_list.itemChanged.connect(self._pack_toggled)
        c.add(self.pack_list, 1)
        c.add(hrow(button("📥 Import pack…", self.pack_import, "primary"), button("📤 Export selected…", self.pack_export),
                   button("📂 Open packs folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.lib.dir))), None,
                   ConfirmButton("🗑 Delete", self.pack_delete, "Confirm delete", 4, "danger")))
        c.add(label('Pack format: {"name": "...", "description": "...", "categories": {"Style": {"Group": ["item", ...]}}}', "hint", wrap=True))
        v.addWidget(c, 1)
        self.load_packs()
        return w

    def load_packs(self):
        self.pack_list.blockSignals(True); self.pack_list.clear()
        for pid, p in self.lib.packs.items():
            n = sum(len(i) for g in p["categories"].values() for i in g.values())
            it = QListWidgetItem(f"{p['name']}  ·  {n} presets  ·  v{p.get('version', '1.0')}\n{p.get('description', '')}")
            it.setData(Qt.UserRole, pid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if pid in self.lib.disabled else Qt.Checked)
            self.pack_list.addItem(it)
        self.pack_list.blockSignals(False)

    def _library_changed(self):
        self.store.set("packs_disabled", sorted(self.lib.disabled))
        self.sel = {c: [i for i in v] for c, v in self.sel.items()}
        self._reset_chip_pages()
        self.search.setPlaceholderText(f"🔍  Search {self.lib.count()} presets in all categories…")
        self.update_preview()

    def _pack_toggled(self, it):
        self.lib.set_enabled(it.data(Qt.UserRole), it.checkState() == Qt.Checked)
        self._library_changed(); self.notify(("Enabled " if it.checkState() == Qt.Checked else "Disabled ") + it.text().split("  ·")[0])

    def pack_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import preset pack", APP_DIR, "Preset pack (*.json)")
        if not path:
            return
        try:
            pid = self.lib.import_pack(path)
        except (OSError, ValueError, PackError) as e:
            self.notify(f"Import failed: {e}", error=True); return
        self.load_packs(); self._library_changed(); self.notify(f"Imported '{self.lib.packs[pid]['name']}'")

    def pack_export(self):
        it = self.pack_list.currentItem()
        if not it:
            self.notify("Select a pack first", error=True); return
        pid = it.data(Qt.UserRole)
        path, _ = QFileDialog.getSaveFileName(self, "Export pack", os.path.join(os.path.expanduser("~"), "Desktop", pid + ".json"), "*.json")
        if path:
            self.lib.export_pack(pid, path); self.notify("Pack exported")

    def pack_delete(self):
        it = self.pack_list.currentItem()
        if not it:
            return
        try:
            self.lib.delete_pack(it.data(Qt.UserRole))
        except (PackError, OSError) as e:
            self.notify(str(e), error=True); return
        self.load_packs(); self._library_changed(); self.notify("Pack deleted")

    # ------------------------------------------------------------------ Profiles
    def _profiles_page(self):
        w, v = page("Model profiles", "How prompts are formatted, scored and refined for each image model. Stored in data/profiles.json – edit or add your own.")
        row = QHBoxLayout(); row.setSpacing(14); v.addLayout(row, 1)
        left = Card("Profiles")
        self.prof_list = QListWidget(); self.prof_list.currentRowChanged.connect(self._prof_selected)
        left.add(self.prof_list, 1)
        left.add(hrow(button("Use as target", self._prof_use, "primary"), button("Duplicate", self._prof_dup)))
        self.cv_refresh_btn = button("⟳ Refresh from Civitai", self.civitai_refresh, tip="Re-fetch this checkpoint's recommendations")
        left.add(hrow(button("🌐 Import from Civitai…", self.civitai_import, "primary"), self.cv_refresh_btn))
        row.addWidget(left, 1)
        right = Card("Details")
        self.prof_view = QTextBrowser(); self.prof_view.setOpenExternalLinks(True)
        right.add(self.prof_view, 1)
        right.add(label("Edit JSON", "h2"))
        self.prof_json = QPlainTextEdit(); f = QFont("Consolas"); f.setPointSize(9); self.prof_json.setFont(f)
        right.add(self.prof_json, 1)
        right.add(hrow(button("💾 Save profile", self._prof_save, "primary"), button("⟳ Reload file", self._prof_reload),
                       button("📂 Open file", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.profiles_path))), None))
        row.addWidget(right, 2)
        self._fill_prof_list()
        return w

    def _fill_prof_list(self, select=None):
        self.prof_list.blockSignals(True); self.prof_list.clear()
        for pid, p in self.profiles.items():
            it = QListWidgetItem(f"{p['name']}\n{p['family']} · {p['format']}"); it.setData(Qt.UserRole, pid)
            self.prof_list.addItem(it)
        self.prof_list.blockSignals(False)
        ids = list(self.profiles)
        self.prof_list.setCurrentRow(ids.index(select) if select in ids else 0)

    def _prof_selected(self, row):
        if row < 0:
            return
        p = self.profiles[self.prof_list.item(row).data(Qt.UserRole)]
        lo, hi = p.get("length", [0, 0])
        res = ", ".join(f"{k} → {v}" for k, v in p.get("resolutions", {}).items())
        src = "".join(f"<li><a href='{s}'>{html.escape(s)}</a></li>" for s in p.get("sources", []))
        tips = "".join(f"<li>{html.escape(t)}</li>" for t in p.get("tips", []))
        self.prof_view.setHtml(
            f"<h2>{html.escape(p['name'])}</h2><table cellpadding='3'>"
            f"<tr><td><b>Format</b></td><td>{p['format']}</td></tr><tr><td><b>Negative prompt</b></td><td>{p['negative']}</td></tr>"
            f"<tr><td><b>Weighting</b></td><td>{p['weighting']}</td></tr><tr><td><b>Length</b></td><td>{lo}–{hi} words</td></tr>"
            f"<tr><td><b>Quality prefix</b></td><td>{html.escape(p.get('quality_prefix') or '–')}</td></tr>"
            f"<tr><td><b>Settings</b></td><td>{html.escape(p.get('settings') or '–')}</td></tr>"
            + (f"<tr><td><b>Inherits</b></td><td>{html.escape(p['inherits'])}</td></tr>" if p.get("inherits") else "")
            + (f"<tr><td><b>Civitai</b></td><td>{html.escape(str(p['civitai'].get('model_name')))} · version "
               f"{html.escape(str(p['civitai'].get('version_name')))} (#{p['civitai'].get('version_id')}) · base "
               f"{html.escape(str(p['civitai'].get('base_model')))} · fetched {p['civitai'].get('fetched')}"
               + (f" · trained words: {html.escape(', '.join(p['civitai'].get('trained_words') or []))}" if p['civitai'].get('trained_words') else "")
               + "</td></tr>" if p.get("civitai") else "") +
            f"<tr><td><b>Negative default</b></td><td>{html.escape(p.get('negative_default') or '–')}</td></tr>"
            f"<tr><td><b>Resolutions</b></td><td>{html.escape(res)}</td></tr></table>"
            f"<h3>Tips</h3><ul>{tips}</ul><h3>Sources</h3><ul>{src or '<li>–</li>'}</ul>")
        raw = profiles.raw_profile(self.profiles_path, p["id"]) if p.get("inherits") else None
        self.prof_json.setPlainText(json.dumps(raw or {k: v for k, v in p.items()}, indent=1, ensure_ascii=False))
        if hasattr(self, "cv_refresh_btn"):
            self.cv_refresh_btn.setEnabled(bool(p.get("civitai")))

    def _prof_use(self):
        it = self.prof_list.currentItem()
        if it:
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(it.data(Qt.UserRole)))
            self.notify(f"Target model: {self.profile['name']}")

    def _prof_dup(self):
        try:
            p = json.loads(self.prof_json.toPlainText())
        except ValueError:
            return
        p["id"] = p.get("id", "custom") + "_copy"; p["name"] = p.get("name", "Custom") + " (copy)"
        self.prof_json.setPlainText(json.dumps(p, indent=1, ensure_ascii=False))
        self.notify("Edit the copy, then Save profile")

    def _prof_save(self):
        try:
            p = json.loads(self.prof_json.toPlainText())
            assert p.get("id") and p.get("name"), "profile needs 'id' and 'name'"
            profiles.save_profile(self.profiles_path, p)
        except (ValueError, AssertionError, OSError) as e:
            self.notify(f"Not saved: {e}", error=True); return
        self._prof_reload(p["id"]); self.notify("Profile saved")

    def _prof_reload(self, select=None):
        try:
            self.profiles = profiles.load(self.profiles_path)
        except (OSError, ValueError) as e:
            self.notify(f"profiles.json has an error: {e}", error=True); return
        cur = self.profile_combo.currentData()
        self.profile_combo.blockSignals(True); self.profile_combo.clear()
        for pid, p in self.profiles.items():
            self.profile_combo.addItem(p["name"], pid)
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(cur)))
        self.profile_combo.blockSignals(False)
        self._fill_prof_list(select if isinstance(select, str) else None)
        self._profile_changed()

    # ================================================================== v2: providers
    def make_provider(self):
        pid = self.store.get("provider", "ollama")
        url = self.store.get(f"provider_url:{pid}") or providers.PRESETS.get(pid, {}).get("base_url")
        key = self.keys.get(f"api_key:{pid}") if providers.PRESETS.get(pid, {}).get("key") else ""
        self.provider = providers.make(pid, url, key)
        self._refresh_unload_cfg()
        if hasattr(self, "prov_label"):
            self.prov_label.setText(providers.PRESETS.get(pid, providers.PRESETS["ollama"])["label"])
        return self.provider

    def refresh_models_async(self):
        if getattr(self, "_closing", False):
            return
        w = CallWorker(self.provider.list_models)
        w.ok.connect(lambda models: self._models_loaded(models, True))
        w.failed.connect(lambda e: self._models_failed(e, True))
        self._keep(w); w.start()

    def closeEvent(self, e):
        """Let background workers finish so no QThread is destroyed while running (crashes on Windows)."""
        self._closing = True
        for x in list(getattr(self, "_workers", [])) + [getattr(self, "worker", None)]:
            if x is not None and x.isRunning():
                if hasattr(x, "stop"):
                    x.stop()
                x.wait(5000)
        q = getattr(self, "genq", None)
        if q is not None and q.isRunning():
            q.clear(); q.cancel_current(); q.wait(5000)
        super().closeEvent(e)

    def _keep(self, w):
        # Hold a reference until the thread's queued signals have been delivered. Dropping a worker as soon as
        # it stopped running could garbage-collect it before its ok/failed signal reached the UI (4.0.1 fix).
        self._workers = [x for x in getattr(self, "_workers", []) if not getattr(x, "_pm_done", False)] + [w]
        w.finished.connect(lambda w=w: setattr(w, "_pm_done", True))

    def _models_loaded(self, models, quiet):
        pid = self.provider.pid
        self.model.blockSignals(True); self.model.clear(); self.model.addItems(models); self.model.blockSignals(False)
        saved = self.store.get(f"model:{pid}") or (self.store.get("model") if pid == "ollama" else None)
        if saved in models:
            self.model.setCurrentText(saved)
        self._set_banner(True, len(models)); self._mark_failed_in_pickers()
        name = providers.PRESETS.get(pid, {}).get("label", pid)
        if models:
            self.ai_dot.setText(f"<span style='color:#35d39a'>●</span> {tr('Connected')} · {len(models)} {tr('model(s)')}")
        else:
            self.ai_dot.setText("<span style='color:#ffc34d'>●</span> " + tr("No models found") +
                                (" – ollama pull llama3.2" if pid == "ollama" else ""))
        if not quiet:
            self.notify(f"{name}: " + (f"{len(models)} model(s)" if models else "connected, no models"))
        return models

    def _models_failed(self, err, quiet):
        self.model.clear()
        self.ai_dot.setText("<span style='color:#ff6b81'>●</span> " + tr("AI provider offline"))
        self.ai_dot.setToolTip(str(err)); self._set_banner(False)
        if not quiet:
            self.notify(str(err), error=True)
        return []

    # ================================================================== v2: image generation
    def image_backend(self):
        kind = self.store.get("img_backend", "none")
        if kind == "none":
            return None
        default = "http://127.0.0.1:8188" if kind == "comfyui" else "http://127.0.0.1:7860"
        return imagegen.make_backend(kind, self.store.get(f"img_url:{kind}", default))

    def _workflow(self):
        wfs = imagegen.list_workflows(os.path.join(self.data_dir, "workflows"))
        name = self.store.get("img_workflow", "sdxl_txt2img")
        path = wfs.get(name) or next(iter(wfs.values()))
        return imagegen.load_workflow(path) + (name,)

    def _size_for_profile(self):
        aspect = self.aspect.currentText()
        res = profiles.resolution(self.profile, aspect)
        if "x" not in res:
            res = profiles.resolution(self.profiles.get("sdxl", self.profile), aspect) or "1024x1024"
        try:
            w, h = (int(x) for x in res.lower().split("x"))
        except ValueError:
            w, h = 1024, 1024
        return w, h

    def generate_image(self, prompt, negative="", seed=None, tag="", quiet=False):
        prompt = (prompt or "").strip()
        if not prompt:
            self.notify(tr("Nothing to generate yet"), error=True); return None
        backend = self.image_backend()
        if not backend:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); self.go("Settings"); return None
        job, backend, wf = self.make_job(prompt, negative, seed, tag)
        self.genq.add(job, backend, wf)
        self.queue_jobs.append(job)
        self._render_queue()
        if not quiet:
            self.notify(tr("Queued for generation") + f" · seed {job.seed}")
        return job

    def _render_queue(self):
        if not hasattr(self, "queue_list"):
            return
        self.queue_list.clear()
        for j in self.queue_jobs[-30:]:
            st = getattr(j, "state", "queued")
            icon = {"queued": "⏳", "running": "⚙", "done": "✅", "failed": "⚠️"}.get(st, "•")
            self.queue_list.addItem(f"{icon} {j.width}×{j.height} · seed {j.seed} · {j.prompt[:70]}" +
                                    (f"  — {j.error}" if st == "failed" else ""))
        self.queue_list.scrollToBottom()

    def _gen_progress(self, jid, pct, msg):
        for j in self.queue_jobs:
            if j.id == jid:
                j.state = "running"
        self.gen_bar.setRange(0, 0 if pct < 0 else 100)
        if pct >= 0:
            self.gen_bar.setValue(pct)
        self.gen_status.setText(msg)
        self._render_queue()

    def _gen_done(self, job, imgs):
        job.state = "done"
        paths = []
        for b in imgs:
            meta = job.meta(); meta["backend"] = getattr(job, "backend_name", "")
            paths.append(self.gallery.save(b, meta))
        job.paths = paths
        self.store.add_history(job.prompt, self.profile["name"], "generated")
        self.gen_status.setText(tr("Done") + f" · {len(paths)} image(s)")
        self.gen_bar.setRange(0, 100); self.gen_bar.setValue(100)
        self._render_queue(); self.load_gallery()
        for cb in getattr(self, "_job_callbacks", {}).pop(job.id, []):
            cb(job)
        self.notify(tr("Image ready") + " – " + tr("saved to Gallery"))

    def _gen_failed(self, job, err):
        job.state, job.error = "failed", err
        self.gen_status.setText("⚠️ " + err[:160]); self.gen_bar.setRange(0, 100); self.gen_bar.setValue(0)
        self._render_queue()
        if err.startswith(imagegen.API_DISABLED):
            self.show_api_disabled(err)
        elif err != "Cancelled":
            self.notify(err, error=True)

    # ------------------------------------------------------------------ Gallery page
    def _gallery_page(self):
        w, v = page("Gallery", "Images you generate are saved in your data folder with their prompt, model profile, settings and seed.")
        q = Card()
        self.gen_status = label(tr("Idle"), "muted"); self.gen_bar = QProgressBar(); self.gen_bar.setFixedHeight(8)
        self.backend_lbl = label("", "badge")
        self.gen_preview = QLabel(); self.gen_preview.setFixedSize(120, 120); self.gen_preview.setAlignment(Qt.AlignCenter)
        self.gen_preview.setVisible(False); self.gen_preview.setToolTip(tr("Live preview of the image being generated"))
        q.add(hrow(label("Queue", "h2"), self.backend_lbl, None, self.gen_status, button("☰ Manage queue", self.open_queue, "ghost"),
                   button("■ Cancel current", lambda: self.genq.cancel_current(), "ghost"),
                   button("Clear queue", lambda: (self.genq.clear(), self.notify(tr("Queue cleared"))), "ghost")))
        q.add(self.gen_bar)
        self.queue_list = QListWidget(); self.queue_list.setFixedHeight(84)
        self.queue_list.itemDoubleClicked.connect(lambda *_: self.open_queue())
        q.add(hrow(self.queue_list, self.gen_preview))
        v.addWidget(q)
        row = QSplitter(); row.setChildrenCollapsible(False); v.addWidget(row, 1)
        left = Card()
        self.gal_list = GalleryList()
        self.gal_list.currentItemChanged.connect(self._gal_selected)
        self.gal_list.itemDoubleClicked.connect(lambda *_: self.gal_view())
        self.gal_list.customContextMenuRequested.connect(self.gal_context)
        left.add(self.gal_list, 1)
        row.addWidget(left)
        right = Card()
        self.gal_preview = QLabel(tr("Select an image")); self.gal_preview.setAlignment(Qt.AlignCenter)
        self.gal_preview.setMinimumHeight(280)
        right.add(self.gal_preview, 2)
        self.gal_meta = QTextBrowser(); right.add(self.gal_meta, 1)
        right.add(hrow(button("🔍 Open full size", self._gal_open), button("📋 Copy prompt", self._gal_copy),
                       button("♻ Reuse prompt", self._gal_reuse, "primary")))
        right.add(hrow(button("🖌 Inpaint this", lambda: self.gal_inpaint()), button("👁 Use as reference", lambda: self.gal_reference()),
                       button("🔍 Regenerate with hires", lambda: self.gal_hires()), button("⤢ Upscale…", lambda: self.gal_upscale())))
        right.add(hrow(button("🎲 Same seed again", self._gal_regen), button("⛶ Viewer", lambda: self.gal_view()), button("📂 Folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.gallery.root))), None, ConfirmButton("🗑 Delete", self._gal_delete, "Confirm delete", 4, "danger")))
        row.addWidget(right); row.setSizes([700, 480])
        self.load_gallery()
        return w

    def load_gallery(self):
        if not hasattr(self, "gal_list"):
            return
        from .v41ui import ROW_H
        self.gal_list.clear()
        items = self.gallery.items()[:400]
        for path, meta in items:  # justified rows: every thumbnail is ROW_H tall and keeps its aspect ratio
            pm = QPixmap(path)
            th = pm.scaledToHeight(ROW_H, Qt.SmoothTransformation) if not pm.isNull() else pm
            th = th.scaledToWidth(ROW_H * 2, Qt.SmoothTransformation) if th.width() > ROW_H * 2 else th
            it = QListWidgetItem(QIcon(th), "")
            it.setSizeHint(QSize(max(60, th.width()) + 6, ROW_H + 6))
            it.setData(Qt.UserRole, (path, meta)); it.setToolTip(meta.get("prompt", "")[:200])
            self.gal_list.addItem(it)
        b = self.image_backend()
        self.backend_lbl.setText((b.name if b else tr("No backend – see Settings")))

    def _gal_cur(self):
        it = self.gal_list.currentItem()
        return (it.data(Qt.UserRole) if it else None) or (None, {})

    def _gal_selected(self, it, _=None):
        if not it:
            return
        path, meta = it.data(Qt.UserRole)
        pm = QPixmap(path)
        self.gal_preview.setPixmap(pm.scaled(self.gal_preview.width(), max(280, self.gal_preview.height()),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation))
        when = time.strftime("%d %b %Y %H:%M", time.localtime(meta.get("saved", 0))) if meta.get("saved") else ""
        rows = "".join(f"<tr><td style='padding-right:10px'><b>{k}</b></td><td>{html.escape(str(meta.get(k, '')))}</td></tr>"
                       for k in ("profile", "backend", "workflow", "checkpoint", "seed", "steps", "cfg", "sampler", "width", "height"))
        self.gal_meta.setHtml(f"<p>{html.escape(meta.get('prompt', ''))}</p>" +
                              (f"<p><i>Negative:</i> {html.escape(meta['negative'])}</p>" if meta.get("negative") else "") +
                              f"<table>{rows}</table><p style='color:gray'>{when} · {html.escape(os.path.basename(path))}</p>")

    def _gal_open(self):
        p, _ = self._gal_cur()
        if p:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _gal_copy(self):
        _, m = self._gal_cur()
        if m.get("prompt"):
            copy(m["prompt"]); self.notify(tr("Copied"))

    def _gal_reuse(self):
        _, m = self._gal_cur()
        if m.get("prompt"):
            self.set_work(m["prompt"], "from Gallery"); self.go("Refine")

    def _gal_regen(self):
        _, m = self._gal_cur()
        if m.get("prompt"):
            self.generate_image(m["prompt"], m.get("negative", ""), m.get("seed"))

    def _gal_delete(self):
        p, _ = self._gal_cur()
        if p:
            self.gallery.delete(p); self.gal_preview.setText(tr("Deleted")); self.gal_meta.clear(); self.load_gallery()
            self.notify(tr("Deleted"))

    # ------------------------------------------------------------------ Image → Prompt
    def _img2prompt_page(self):
        w, v = page("Image to Prompt", "Drop, paste or open an image – a local vision model describes it as a prompt for your target model.")
        row = QHBoxLayout(); row.setSpacing(14); v.addLayout(row, 1)
        left = Card("Image")
        self.drop = DropLabel(tr("Drop an image here\nor use Paste / Open"))
        self.drop.dropped.connect(self._i2p_set_image)
        left.add(self.drop, 1)
        left.add(hrow(button("📋 Paste", self._i2p_paste), button("📂 Open…", self._i2p_open), None))
        self.vision_model = QComboBox(); self.vision_model.setMinimumWidth(220)
        left.add(hrow(label("Vision model"), self.vision_model, button("⟳", self._i2p_models, "ghost", "Find vision-capable models")))
        self.i2p_hint = label("", "hint", wrap=True); left.add(self.i2p_hint)
        self.i2p_detail = QComboBox(); self.i2p_detail.addItems(["Balanced", "Short", "Very detailed"])
        left.add(hrow(label("Detail"), self.i2p_detail, None, self.stop_btn(),
                      self.ai_btn("👁 Describe as prompt", self._i2p_run, "primary")))
        row.addWidget(left, 1)
        right = Card("Prompt")
        self.i2p_out = QPlainTextEdit(); right.add(self.i2p_out, 1)
        right.add(hrow(button("📋 Copy", lambda: (copy(self.i2p_out.toPlainText()), self.notify(tr("Copied"))), "primary"),
                       button("↩ Load into Builder", self._i2p_builder), button("💬 Refine", lambda: (
                           self.set_work(self.i2p_out.toPlainText(), "from image"), self.go("Refine"))),
                       button("📊 Score", lambda: (self.score_in.setPlainText(self.i2p_out.toPlainText()), self.go("Score"))),
                       button("🖼 Generate", lambda: self.generate_image(self.i2p_out.toPlainText()))))
        row.addWidget(right, 1)
        self.i2p_b64 = None
        return w

    def _i2p_set_image(self, img):
        if img.isNull():
            self.notify(tr("That isn't an image I can read"), error=True); return
        if max(img.width(), img.height()) > 1024:
            img = img.scaled(1024, 1024, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
        self.i2p_b64 = base64.b64encode(bytes(buf.data())).decode()
        self.drop.setPixmap(QPixmap.fromImage(img).scaled(self.drop.width() - 10, self.drop.height() - 10,
                                                          Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if not self.vision_model.count():
            self._i2p_models()

    def _i2p_paste(self):
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            self.notify(tr("No image on the clipboard"), error=True)
        else:
            self._i2p_set_image(img)

    def _i2p_open(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Open image"), os.path.expanduser("~"), "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._i2p_set_image(QImage(path))

    def _i2p_models(self):
        self.i2p_hint.setText(tr("Looking for vision models…"))
        w = CallWorker(self.provider.vision_models)
        def ok(models):
            failed = {**self._failed_models(), **(getattr(self.provider, "notes", {}) or {})}
            models = providers.sort_models(models, providers.VISION_PREFERENCE, failed)
            self.vision_model.clear(); self.vision_model.addItems(models)
            saved = self.store.get(f"vision_model:{self.provider.pid}")
            if saved in models and saved not in failed:
                self.vision_model.setCurrentText(saved)
            elif models and models[0] not in failed:
                self.vision_model.setCurrentIndex(0)
            self._mark_failed_in_pickers()
            if models:
                self.i2p_hint.setText(f"{len(models)} vision-capable model(s) found.")
            else:
                self.i2p_hint.setText("No vision model found. For Ollama try: ollama pull qwen2.5vl  (or gemma3, llava). "
                                      "LM Studio: load a vision model (e.g. Qwen2.5-VL).")
                self.vision_model.setEditable(True)
        w.ok.connect(ok); w.failed.connect(lambda e: self.i2p_hint.setText("⚠️ " + e[:200]))
        self._keep(w); w.start()

    def _i2p_run(self):
        if not self.i2p_b64:
            self.notify(tr("Add an image first"), error=True); return
        model = self.vision_model.currentText().strip()
        if not model:
            self.notify(tr("Pick a vision model first"), error=True); self._i2p_models(); return
        self.store.set(f"vision_model:{self.provider.pid}", model)
        detail = {"Short": "Keep it short (about 25 words).", "Very detailed": "Be very detailed (90-150 words).",
                  "Balanced": "Use the ideal length for the target model."}[self.i2p_detail.currentText()]
        msgs = [{"role": "system", "content": ollama.system_for(self.profile,
                 "Look at the image and write a prompt that would recreate it: subject, appearance, pose, setting, style/medium, "
                 f"lighting, camera/composition, colours and mood. {detail} Follow the target model's format exactly. "
                 "Reply with only the prompt.")},
                {"role": "user", "content": "Write the prompt for this image.", "images": [self.i2p_b64]}]
        self.i2p_out.clear()
        def chunk(c):
            self.i2p_out.insertPlainText(c)
        self.run_ai(msgs, chunk, lambda t: self.store.add_history(t.strip(), self.profile["name"], "image2prompt"),
                    temperature=0.4, model=model, vision=True)

    def _i2p_builder(self):
        t = self.i2p_out.toPlainText().strip()
        if not t:
            return
        self.an_in.setPlainText(t)
        if self.model.currentText():
            self._pending_builder_load = True; self.ai_analyse(); self.notify(tr("Analysing – it will load into the Builder"))
        else:
            self.quick_analyse(); self.load_analysis()

    # ------------------------------------------------------------------ A/B test
    def _ab_page(self):
        w, v = page("A/B Test", "Compare two prompts for the target model: scores, differences and (with a backend) images from the same seed.")
        row = QHBoxLayout(); row.setSpacing(14); v.addLayout(row, 1)
        self.ab = {}
        for side in "AB":
            c = Card(f"Prompt {side}")
            ed = QPlainTextEdit(); ed.setFixedHeight(110); c.add(ed)
            c.add(hrow(button("Builder", lambda _=False, e=ed: e.setPlainText(self.build_result()["prompt"]), "ghost"),
                       button("Working", lambda _=False, e=ed: e.setPlainText(self.work.toPlainText()), "ghost"),
                       button("Create", lambda _=False, e=ed: e.setPlainText(self.c_prompt.toPlainText()), "ghost"), None))
            score = label("–", "scoreBig"); detail = label("", "hint", wrap=True)
            c.add(hrow(score, detail, None))
            diff = QTextBrowser(); diff.setFixedHeight(110); c.add(diff)
            img = QLabel(tr("No image yet")); img.setAlignment(Qt.AlignCenter); img.setMinimumHeight(200); c.add(img, 1)
            c.add(button(f"🏆 {side} wins", lambda _=False, s=side: self._ab_pick(s), "primary"))
            row.addWidget(c, 1)
            self.ab[side] = dict(edit=ed, score=score, detail=detail, diff=diff, img=img, ai=None)
        bar = Card()
        self.ab_seed = QSpinBox(); self.ab_seed.setRange(0, 2**31 - 1); self.ab_seed.setSpecialValueText("random seed")
        self.ab_summary = label("", "muted", wrap=True)
        bar.add(hrow(button("⚖ Compare", self.ab_compare, "primary"), self.ai_btn("🧠 AI scores", self.ab_ai),
                     button("🖼 Generate both (same seed)", self.ab_generate), label("Seed"), self.ab_seed, None, self.ab_summary))
        v.addWidget(bar)
        return w

    def ab_compare(self):
        a, b = self.ab["A"]["edit"].toPlainText(), self.ab["B"]["edit"].toPlainText()
        if not a.strip() or not b.strip():
            self.notify(tr("Fill in both prompts"), error=True); return
        ha, hb = abtest.diff_html(a, b)
        self.ab["A"]["diff"].setHtml(ha); self.ab["B"]["diff"].setHtml(hb)
        res = {}
        for side, text in (("A", a), ("B", b)):
            s = scoring.heuristic_score(text, self.profile, self.lib.all_items())
            res[side] = s["total"]
            self.ab[side]["score"].setText(str(s["total"]))
            self.ab[side]["detail"].setText(" · ".join(f"{k[:5]} {v[0]}" for k, v in s["criteria"].items()) +
                                            (f"\nAI: {self.ab[side]['ai']}" if self.ab[side]["ai"] is not None else ""))
        win = abtest.verdict(res["A"], res["B"])
        self.ab_summary.setText(f"Heuristic for {self.profile['name']}: " + ("tie" if win == "tie" else f"{win} looks stronger") +
                                f" · {abtest.similarity(a, b)}% similar")

    def ab_ai(self):
        self.ab_compare()
        texts = {s: self.ab[s]["edit"].toPlainText() for s in "AB"}
        if not all(t.strip() for t in texts.values()):
            return
        def score_side(side, then=None):
            def done(t):
                try:
                    d = builder.parse_json_loose(t)
                    tot = 0
                    for k in scoring.RUBRIC:
                        e = d.get("scores", {}).get(k, {})
                        tot += max(0, min(10, int(float(e.get("score", 0) if isinstance(e, dict) else e))))
                    self.ab[side]["ai"] = tot * 2
                except (ValueError, TypeError):
                    self.ab[side]["ai"] = "?"
                self.ab_compare()
                if then:
                    then()
            self.run_ai(ollama.score_messages(texts[side], self.profile), lambda c: None, done, json_mode=True, temperature=0.2)
        score_side("A", lambda: QTimer.singleShot(100, lambda: score_side("B")))

    def ab_generate(self):
        seed = self.ab_seed.value() or imagegen.new_seed()
        self.ab_seed.setValue(seed)
        self._job_callbacks = getattr(self, "_job_callbacks", {})
        for side in "AB":
            job = self.generate_image(self.ab[side]["edit"].toPlainText(), self.negative.toPlainText()
                                      if self.profile.get("negative") in ("supported", "optional", "limited") else "",
                                      seed=seed, tag="ab" + side, quiet=True)
            if not job:
                return
            self.ab[side]["img"].setText(tr("Generating…"))
            self._job_callbacks.setdefault(job.id, []).append(
                lambda j, s=side: self.ab[s]["img"].setPixmap(QPixmap(j.paths[0]).scaled(
                    self.ab[s]["img"].width(), max(200, self.ab[s]["img"].height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        self.notify(f"Generating A and B with seed {seed}")

    def _ab_pick(self, side):
        t = self.ab[side]["edit"].toPlainText().strip()
        if t:
            self.store.add_history(t, self.profile["name"], f"A/B winner ({side})")
            self.notify(f"{side} saved to history as the winner")

    # ------------------------------------------------------------------ Community
    def _community_page(self):
        w, v = page("Community", "Browse packs and model profiles shared by the community. Downloads are verified with SHA-256 before installing.")
        c = Card()
        self.comm_list = QListWidget(); self.comm_list.setWordWrap(True)
        c.add(self.comm_list, 1)
        self.comm_status = label("", "hint", wrap=True)
        c.add(hrow(button("⟳ Refresh", self.comm_refresh), button("⬇ Install / update", self.comm_install, "primary"),
                   ConfirmButton("🗑 Uninstall", self.comm_uninstall, "Confirm uninstall", 4, "danger"), None, self.comm_status))
        c.add(label("Want to share a pack or profile? See CONTRIBUTING.md – submit it with a pull request.", "hint"))
        v.addWidget(c, 1)
        self.comm_items = []
        return w

    def comm_refresh(self):
        url = self.store.get("community_index") or community.DEFAULT_INDEX
        self.comm_status.setText(tr("Loading…"))
        wk = CallWorker(community.load_index, url)
        wk.ok.connect(self._comm_loaded); wk.failed.connect(lambda e: self.comm_status.setText("⚠️ " + e[:240]))
        self._keep(wk); wk.start()

    def _comm_loaded(self, items):
        self.comm_items = items
        inst = self.store.get("community_installed", {})
        self.comm_list.clear()
        for e in items:
            st = community.status(e, inst)
            badge = {"available": "", "installed": "✅ installed", "update": "⬆ update available"}[st]
            it = QListWidgetItem(f"{'📦' if e['kind'] == 'pack' else '🎯'}  {e['name']}  ·  v{e['version']}  ·  by {e.get('author', '?')}   {badge}\n"
                                 f"{e.get('description', '')}")
            it.setData(Qt.UserRole, e); self.comm_list.addItem(it)
        self.comm_status.setText(f"{len(items)} item(s)")

    def _comm_cur(self):
        it = self.comm_list.currentItem()
        if not it:
            self.notify(tr("Select an item first"), error=True)
        return it.data(Qt.UserRole) if it else None

    def comm_install(self):
        e = self._comm_cur()
        if not e:
            return
        inst = self.store.get("community_installed", {})
        def do():
            return community.install(e, self.lib, self.profiles_path, inst)
        wk = CallWorker(do)
        def ok(new):
            self.store.set("community_installed", new)
            self._library_changed(); self.load_packs()
            if e["kind"] == "profile":
                self._prof_reload()
            self._comm_loaded(self.comm_items); self.notify(f"Installed {e['name']} v{e['version']}")
        wk.ok.connect(ok); wk.failed.connect(lambda m: self.notify(m, error=True))
        self._keep(wk); wk.start()

    def comm_uninstall(self):
        e = self._comm_cur()
        if not e:
            return
        inst = community.uninstall(e["id"], self.lib, self.profiles_path, self.store.get("community_installed", {}))
        self.store.set("community_installed", inst)
        self._library_changed(); self.load_packs()
        if e["kind"] == "profile":
            self._prof_reload()
        self._comm_loaded(self.comm_items); self.notify(f"Uninstalled {e['name']}")

    # ------------------------------------------------------------------ Settings
    def _settings_page(self):
        w, v = page("Settings")
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 8, 0); iv.setSpacing(14)
        # General
        g = Card("General")
        self.lang = QComboBox()
        for code, name in i18n.available().items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.store.get("language", "en"))))
        self.lang.currentIndexChanged.connect(lambda: (self.store.set("language", self.lang.currentData()),
                                                       self.notify(tr("Language saved – restart PromptMaker to apply"))))
        g.add(hrow(label("Language"), self.lang, None))
        from . import theme as _th
        self.accent = QComboBox()
        for k in _th.ACCENTS:
            self.accent.addItem(tr(k.capitalize()), k)
        self.accent.setCurrentIndex(max(0, self.accent.findData(self.store.get("accent", "purple"))))
        self.accent.currentIndexChanged.connect(lambda _i: self.apply_accent(self.accent.currentData()))
        self.anim_on = QCheckBox(tr("Page fade animations")); self.anim_on.setChecked(bool(self.store.get("animations", True)))
        self.anim_on.toggled.connect(lambda on: self.store.set("animations", on))
        self.live_prev = QCheckBox(tr("Live preview while generating (Forge)")); self.live_prev.setChecked(bool(self.store.get("live_preview", True)))
        self.live_prev.toggled.connect(lambda on: (self.store.set("live_preview", on), setattr(imagegen, "LIVE_PREVIEW", on)))
        imagegen.LIVE_PREVIEW = bool(self.store.get("live_preview", True))
        g.add(hrow(label("Accent colour"), self.accent, self.anim_on, self.live_prev, None))
        self.chk_updates = QCheckBox(tr("Check GitHub for new versions at startup"))
        self.chk_updates.setChecked(self.store.get("check_updates", True))
        self.chk_updates.toggled.connect(lambda on: self.store.set("check_updates", on))
        g.add(hrow(self.chk_updates, button("Check now", lambda: self.check_updates(manual=True)), None))
        self.portable = QCheckBox(tr("Portable mode – keep data next to the app (off = user AppData folder)"))
        self.portable.setChecked(paths.is_portable(APP_DIR))
        g.add(hrow(self.portable, button("Apply", self._apply_portable), None))
        g.add(label(f"{tr('Data folder')}: {self.data_dir}", "hint", wrap=True))
        g.add(hrow(button("📂 Open data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.data_dir))),
                   button("🧭 Show the tour again", self.start_tour), button("🛠 Run setup wizard", lambda: self.open_setup()), None))
        iv.addWidget(g)
        # AI provider
        a = Card("AI provider")
        self.prov_combo = QComboBox()
        for pid, p in providers.PRESETS.items():
            self.prov_combo.addItem(p["label"], pid)
        self.prov_combo.setCurrentIndex(max(0, self.prov_combo.findData(self.store.get("provider", "ollama"))))
        self.prov_url = QLineEdit(); self.prov_key = QLineEdit(); self.prov_key.setEchoMode(QLineEdit.Password)
        self.prov_key.setPlaceholderText(tr("API key (stored locally, never uploaded except to that provider)"))
        self.prov_combo.currentIndexChanged.connect(self._prov_form)
        a.add(hrow(label("Provider"), self.prov_combo, label("Base URL"), self.prov_url))
        self.key_row = QWidget(); kr = QHBoxLayout(self.key_row); kr.setContentsMargins(0, 0, 0, 0)
        kr.addWidget(self.prov_key, 1); kr.addWidget(button("Save key", self._prov_save_key)); kr.addWidget(button("Clear key", self._prov_clear_key, "ghost"))
        a.add(self.key_row)
        self.key_note = label("", "hint", wrap=True); a.add(self.key_note)
        self.prov_test_lbl = label("", "muted", wrap=True)
        a.add(hrow(button("Use this provider", self._prov_apply, "primary"), button("Test connection", self._prov_test), None, self.prov_test_lbl))
        a.add(label("All AI features (Create, Refine, Analyse, Score, Batch, Image to Prompt, A/B) use this provider. "
                    "Cloud providers send your prompts to that company and may cost money on your account.", "hint", wrap=True))
        iv.addWidget(a)
        # Image generation
        im = Card("Image generation")
        self.img_kind = QComboBox()
        for k, n in (("none", "Off"), ("comfyui", "ComfyUI"), ("a1111", "Forge / AUTOMATIC1111")):
            self.img_kind.addItem(n, k)
        self.img_kind.setCurrentIndex(max(0, self.img_kind.findData(self.store.get("img_backend", "none"))))
        self.img_url = QLineEdit()
        self.img_kind.currentIndexChanged.connect(self._img_form)
        im.add(hrow(label("Backend"), self.img_kind, label("URL"), self.img_url))
        self.img_wf = QComboBox()
        for name in imagegen.list_workflows(os.path.join(self.data_dir, "workflows")):
            self.img_wf.addItem(name)
        self.img_wf.setCurrentText(self.store.get("img_workflow", "sdxl_txt2img"))
        self.img_ckpt = CheckpointCombo(loader=self._img_ckpts)
        self.img_ckpt.currentTextChanged.connect(lambda _t: self.set_checkpoint(self.img_ckpt.name(), self.img_ckpt, self._settings_ckpt_key()))
        self._ckpt_combos_list().append(self.img_ckpt)
        self.wf_row = QWidget(); wl = QHBoxLayout(self.wf_row); wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(label("Workflow")); wl.addWidget(self.img_wf); wl.addStretch()
        im.add(self.wf_row)
        self.img_steps = QSpinBox(); self.img_steps.setRange(0, 150); self.img_steps.setSpecialValueText("default")
        self.img_steps.setValue(self.store.get("img_steps") or 0)
        self.img_cfg = QDoubleSpinBox(); self.img_cfg.setRange(0, 30); self.img_cfg.setSingleStep(0.5); self.img_cfg.setSpecialValueText("default")
        self.img_cfg.setValue(self.store.get("img_cfg") or 0)
        self.ckpt_link_lbl = label("", "hint")
        self.ckpt_link_lbl.setToolTip(tr("Each target model remembers the checkpoint you pick. Choose 'Backend default' (clear the box) to unlink."))
        im.add(hrow(label("Checkpoint"), self.img_ckpt, button("⟳", self._img_ckpts, "ghost", "Reload checkpoint list")))
        im.add(self.ckpt_link_lbl)
        self.img_sampler = self._pick_combo("img_sampler"); self.img_scheduler = self._pick_combo("img_scheduler")
        im.add(hrow(label("Steps"), self.img_steps, label("CFG"), self.img_cfg, label("Sampler"), self.img_sampler,
                    button("⟳", lambda: self._load_picks("samplers", self.img_sampler), "ghost", "Load samplers from the backend"),
                    label("Scheduler"), self.img_scheduler,
                    button("⟳", lambda: self._load_picks("schedulers", self.img_scheduler), "ghost", "Load schedulers from the backend"), None))
        self.hr_on = QCheckBox(tr("Hires fix")); self.hr_on.setChecked(bool(self.store.get("hr_on", False)))
        self.hr_scale = QDoubleSpinBox(); self.hr_scale.setRange(1.0, 4.0); self.hr_scale.setSingleStep(0.25)
        self.hr_scale.setValue(float(self.store.get("hr_scale", 1.5))); self.hr_scale.setSuffix("×")
        self.hr_denoise = QDoubleSpinBox(); self.hr_denoise.setRange(0.0, 1.0); self.hr_denoise.setSingleStep(0.05)
        self.hr_denoise.setValue(float(self.store.get("hr_denoise", 0.4)))
        self.hr_steps = QSpinBox(); self.hr_steps.setRange(0, 150); self.hr_steps.setSpecialValueText("same")
        self.hr_steps.setValue(int(self.store.get("hr_steps", 0) or 0))
        self.hr_up = QComboBox(); self.hr_up.setEditable(False); self.hr_up.setMinimumWidth(220)
        self.hr_up.addItem(self.store.get("hr_upscaler", "Latent"))
        im.add(hrow(self.hr_on, label("Upscale"), self.hr_scale, label("Upscaler"), self.hr_up,
                    button("⟳", self._hr_upscalers, "ghost", "Load upscalers from Forge"), None))
        im.add(hrow(label("Hires steps"), self.hr_steps, label("Denoise"), self.hr_denoise,
                    label("0.3–0.5 keeps the picture, higher adds detail but can change it", "hint"), None))
        self.img_unload = QCheckBox(tr("Unload Ollama models from VRAM before each image (frees memory for the image model)"))
        self.img_unload.setChecked(bool(self.store.get("img_unload_ollama", True)))
        self.img_unload.toggled.connect(lambda on: (self.store.set("img_unload_ollama", bool(on)), self._refresh_unload_cfg()))
        im.add(self.img_unload)
        self.img_test_lbl = label("", "muted", wrap=True)
        im.add(hrow(button("Save", self._img_save, "primary"), button("Test connection", self._img_test), None, self.img_test_lbl))
        im.add(label("ComfyUI workflows are API-format JSON with {{prompt}} {{negative}} {{width}} {{height}} {{seed}} {{steps}} {{cfg}} "
                     "{{checkpoint}} {{sampler}} {{scheduler}} placeholders. Put your own in data/workflows/. "
                     "Start ComfyUI normally; for Forge/A1111 launch with --api.", "hint", wrap=True))
        iv.addWidget(im)
        # Community
        cv = Card("Civitai")
        self.cv_key = QLineEdit(); self.cv_key.setEchoMode(QLineEdit.Password)
        self.cv_key.setPlaceholderText(tr("key saved") if self.keys.get("api_key:civitai") else tr("Optional – needed only for NSFW / gated models"))
        cv.add(hrow(label("API key"), self.cv_key, button("Save key", self._cv_key_save), button("Clear key", self._cv_key_clear, "ghost")))
        cv.add(label("Used by Model profiles → Import from Civitai. Create a key at civitai.com/user/account (API Keys). "
                     "Keys are stored in " + self.keys.backend + ". Responses are cached for 24 h in data/cache/civitai.", "hint", wrap=True))
        iv.addWidget(cv)
        cm = Card("Community gallery")
        self.comm_url = QLineEdit(self.store.get("community_index") or community.DEFAULT_INDEX)
        cm.add(hrow(label("Index URL"), self.comm_url, button("Save", lambda: (self.store.set("community_index", self.comm_url.text().strip()),
                                                                            self.notify(tr("Saved"))))))
        iv.addWidget(cm)
        iv.addStretch()
        v.addWidget(scroll(inner), 1)
        self._prov_form(); self._img_form()
        return w

    def _cv_key_save(self):
        k = self.cv_key.text().strip()
        if k:
            self.keys.set("api_key:civitai", k); self.cv_key.clear(); self.cv_key.setPlaceholderText(tr("key saved")); self.notify(tr("Key saved"))

    def _cv_key_clear(self):
        self.keys.delete("api_key:civitai"); self.cv_key.setPlaceholderText(tr("Optional – needed only for NSFW / gated models"))
        self.notify(tr("Key removed"))

    # ---------------------------------------------------------------- Civitai import
    def civitai_client(self):
        return civitai.Client(self.keys.get("api_key:civitai"), os.path.join(self.data_dir, "cache", "civitai"),
                              base=self.store.get("civitai_api") or civitai.API)

    def civitai_import(self, _=False, ref=None, existing=None):
        from .civitai_dialog import CivitaiDialog
        dlg = CivitaiDialog(self, ref or "", existing)
        self._cv_dialog = dlg
        dlg.saved.connect(self._civitai_saved)
        dlg.show()
        if ref:
            dlg.fetch(force=existing is not None)
        return dlg

    def civitai_refresh(self):
        it = self.prof_list.currentItem()
        p = self.profiles.get(it.data(Qt.UserRole)) if it else None
        if not p or not p.get("civitai"):
            self.notify(tr("Select a profile imported from Civitai"), error=True); return None
        c = p["civitai"]
        return self.civitai_import(ref=f"https://civitai.com/models/{c.get('model_id')}?modelVersionId={c.get('version_id')}",
                                   existing=profiles.raw_profile(self.profiles_path, p["id"]) or p)

    def _civitai_saved(self, prof):
        profiles.save_profile(self.profiles_path, prof)
        self._prof_reload(prof["id"])
        i = self.profile_combo.findData(prof["id"])
        if i >= 0:
            self.profile_combo.setCurrentIndex(i)
        self.notify(tr("Profile saved") + f": {prof['name']}")

    def _prov_form(self, *_):
        pid = self.prov_combo.currentData(); p = providers.PRESETS[pid]
        self.prov_url.setText(self.store.get(f"provider_url:{pid}") or p["base_url"])
        self.key_row.setVisible(bool(p["key"]))
        has = bool(self.keys.get(f"api_key:{pid}")) if p["key"] else False
        self.prov_key.clear()
        self.prov_key.setPlaceholderText(("✓ " + tr("key saved") + " – ") if has else "" + tr("Paste API key"))
        warn = "" if self.keys.use_keyring else " ⚠️ " + tr("No secure keyring available – keys are saved in plain text in your data folder.")
        self.key_note.setText((tr("Keys are stored in") + f" {self.keys.backend}." + warn) if p["key"] else "")

    def _prov_save_key(self):
        k = self.prov_key.text().strip()
        if k:
            where = self.keys.set(f"api_key:{self.prov_combo.currentData()}", k)
            self.notify(tr("Key saved") + (" (" + tr("plain-text file") + ")" if where == "file" else ""), error=where == "file")
            self._prov_form()

    def _prov_clear_key(self):
        self.keys.delete(f"api_key:{self.prov_combo.currentData()}"); self._prov_form(); self.notify(tr("Key removed"))

    def _prov_apply(self):
        pid = self.prov_combo.currentData()
        self.store.set("provider", pid); self.store.set(f"provider_url:{pid}", self.prov_url.text().strip())
        if self.prov_key.text().strip():
            self._prov_save_key()
        self.make_provider(); self.model.clear(); self.refresh_models_async()
        self.notify(tr("Provider") + ": " + providers.PRESETS[pid]["label"])

    def _prov_test(self):
        pid = self.prov_combo.currentData()
        key = self.prov_key.text().strip() or self.keys.get(f"api_key:{pid}")
        prov = providers.make(pid, self.prov_url.text().strip(), key)
        self.prov_test_lbl.setText(tr("Testing…"))
        wk = CallWorker(prov.test)
        wk.ok.connect(lambda m: self.prov_test_lbl.setText("✅ " + m)); wk.failed.connect(lambda e: self.prov_test_lbl.setText("⚠️ " + e[:240]))
        self._keep(wk); wk.start()

    def _pick_combo(self, key):
        c = QComboBox(); c.setEditable(True); c.setMinimumWidth(170)
        c.addItem(imagegen.PROFILE_DEFAULT)
        cur = self.store.get(key) or imagegen.PROFILE_DEFAULT
        if cur != imagegen.PROFILE_DEFAULT:
            c.addItem(cur)
        c.setCurrentText(cur)
        if key == "img_scheduler":
            c.addItems([x for x in imagegen.DEFAULT_SCHEDULERS if x != cur])
        return c

    def _load_picks(self, what, combo):
        b = self.image_backend()
        fn = getattr(b, what, None)
        if fn is None:
            self.notify(tr("This backend has no list to load"), error=True); return None
        cur = combo.currentText()
        wk = CallWorker(fn)

        def done(names):
            combo.clear(); combo.addItem(imagegen.PROFILE_DEFAULT); combo.addItems([n for n in names if n])
            combo.setCurrentText(cur or imagegen.PROFILE_DEFAULT)
        wk.ok.connect(done); self._keep(wk); wk.start()
        return wk

    def _hr_upscalers(self):
        b = self.image_backend()
        if not isinstance(b, imagegen.A1111):
            self.notify(tr("The upscaler list is Forge-only – ComfyUI hires fix uses a latent upscale + second pass"), error=True); return None
        cur = self.hr_up.currentText()
        wk = CallWorker(b.upscalers)

        def done(names):
            self.hr_up.clear(); self.hr_up.addItems(names)
            i = self.hr_up.findText(cur); self.hr_up.setCurrentIndex(max(0, i))
        wk.ok.connect(done); self._keep(wk); wk.start()
        return wk

    def _img_form(self, *_):
        kind = self.img_kind.currentData()
        default = "http://127.0.0.1:8188" if kind == "comfyui" else "http://127.0.0.1:7860"
        self.img_url.setText(self.store.get(f"img_url:{kind}", default) if kind != "none" else "")
        self.img_url.setEnabled(kind != "none"); self.wf_row.setVisible(kind == "comfyui")
        self.img_ckpt.set_name(self.store.get(f"img_checkpoint:{self._settings_ckpt_key()}", ""))
        self.img_ckpt.set_items([])

    def _img_save(self):
        kind = self.img_kind.currentData()
        self.store.set("img_backend", kind)
        if kind != "none":
            self.store.set(f"img_url:{kind}", self.img_url.text().strip())
        self.store.set("img_workflow", self.img_wf.currentText())
        self.store.set(f"img_checkpoint:{self.img_wf.currentText() if kind == 'comfyui' else 'a1111'}", self.img_ckpt.name())
        self.link_profile_checkpoint(self.img_ckpt.name())
        self.save_profile_image(steps=self.img_steps.value() or None, cfg=self.img_cfg.value() or None,
                                sampler=self.img_sampler.currentText().strip(), scheduler=self.img_scheduler.currentText().strip())
        self.store.set("img_steps", self.img_steps.value() or None); self.store.set("img_cfg", self.img_cfg.value() or None)
        self.store.set("hr_on", self.hr_on.isChecked()); self.store.set("hr_scale", self.hr_scale.value())
        self.store.set("hr_denoise", self.hr_denoise.value()); self.store.set("hr_steps", self.hr_steps.value())
        self.store.set("hr_upscaler", self.hr_up.currentText() or "Latent")
        for k, c in (("img_sampler", self.img_sampler), ("img_scheduler", self.img_scheduler)):
            t = c.currentText().strip()
            self.store.set(k, None if not t or t == imagegen.PROFILE_DEFAULT else t)
        cur = self.store.get(f"img_checkpoint:{self.ckpt_key()}", "")
        for c in self._ckpt_combos_list():
            if c is not self.img_ckpt:
                c.set_name(cur)
        self.load_gallery(); self.notify(tr("Image generation settings saved"))

    def _img_test_failed(self, e):
        self.img_test_lbl.setText("⚠️ " + e[:240])
        if e.startswith(imagegen.API_DISABLED):
            self.show_api_disabled(e)

    def show_api_disabled(self, e):
        """Friendly 'Forge API is off' dialog with the exact fix and a Copy button."""
        box = QMessageBox(self); box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("Forge API is switched off"))
        bat = re.search(r"open (.+?webui-user\.bat)", e)
        bat = bat.group(1) if bat else "webui-user.bat"
        box.setText(tr("Forge is running, but its API isn't enabled, so PromptMaker can't send it prompts.") + "\n\n"
                    + tr("How to fix:") + f"\n1. {tr('Close the Forge window.')}\n2. {tr('Open')} {bat} {tr('in Notepad.')}"
                    f"\n3. {tr('Change the line')}  set COMMANDLINE_ARGS=  {tr('to')}  {imagegen.API_FIX}"
                    f"\n    ({tr('keep any other flags after --api')})\n4. {tr('Save, start Forge again, then click Test connection.')}")
        box.setDetailedText(e)
        cp = box.addButton(tr("Copy") + f" `{imagegen.API_FIX}`", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.buttonClicked.connect(lambda b: b is cp and (copy(imagegen.API_FIX), self.notify(tr("Copied") + f": {imagegen.API_FIX}")))
        self._last_error_box = box
        box.open()
        return box

    def _img_test(self):
        kind = self.img_kind.currentData()
        if kind == "none":
            return
        b = imagegen.make_backend(kind, self.img_url.text().strip())
        self.img_test_lbl.setText(tr("Testing…"))
        wk = CallWorker(b.test)
        wk.ok.connect(lambda m: (self.img_test_lbl.setText("✅ " + m), self._img_ckpts()))
        wk.failed.connect(self._img_test_failed)
        self._keep(wk); wk.start()

    def _settings_ckpt_key(self):
        kind = self.img_kind.currentData()
        return self.img_wf.currentText() if kind == "comfyui" else "a1111"

    def _img_ckpts(self):
        kind = self.img_kind.currentData()
        if kind == "none":
            return
        same = kind == self.store.get("img_backend", "none") and self.img_url.text().strip() == self.store.get(f"img_url:{kind}", self.img_url.text().strip())
        self.load_checkpoints(imagegen.make_backend(kind, self.img_url.text().strip()),
                              None if same else [self.img_ckpt], force=True)

    # ------------------------------------------------- shared checkpoint pickers (Settings / Pose / Auto-refine)
    def _ckpt_combos_list(self):
        if not hasattr(self, "_ckpt_combos"):
            self._ckpt_combos = []
        return self._ckpt_combos

    def ckpt_key(self):
        """Store key suffix for the active backend: 'a1111' or the ComfyUI workflow name."""
        return self.store.get("img_workflow", "sdxl_txt2img") if self.store.get("img_backend", "none") == "comfyui" else "a1111"

    def make_ckpt_combo(self):
        c = CheckpointCombo(loader=self.load_checkpoints)
        c.set_name(self.store.get(f"img_checkpoint:{self.ckpt_key()}", ""))
        c.currentTextChanged.connect(lambda _t, c=c: self.set_checkpoint(c.name(), c))
        self._ckpt_combos_list().append(c)
        return c

    def set_checkpoint(self, name, source=None, key=None):
        """Store the checkpoint and mirror it into every other picker using the same key."""
        key = key or self.ckpt_key()
        self.store.set(f"img_checkpoint:{key}", name)
        if source is not None and not getattr(self, "_applying_profile_ckpt", False):
            self.link_profile_checkpoint(name)
        if key != self.ckpt_key():
            return
        for c in self._ckpt_combos_list():
            if c is source:
                continue
            if c is getattr(self, "img_ckpt", None) and self._settings_ckpt_key() != key:
                continue
            if c.name() != name:
                c.set_name(name)

    # ------------------------------------------------- target model <-> checkpoint link (4.0.1)
    def profile_checkpoints(self):
        return dict(self.store.get("profile_checkpoints") or {})

    def link_profile_checkpoint(self, name, pid=None):
        """Remember `name` for the target model; an empty name (Backend default) unlinks it."""
        pid = pid or self.profile.get("id")
        m = self.profile_checkpoints()
        if name:
            m[pid] = name
        else:
            m.pop(pid, None)
        self.store.set("profile_checkpoints", m)
        self._update_ckpt_link_label()

    def _update_ckpt_link_label(self):
        lbl = getattr(self, "ckpt_link_lbl", None)
        if lbl is None:
            return
        bits = self.link_summary()
        name = self.profile_checkpoints().get(self.profile.get("id")) or bits
        lbl.setText(tr("Linked to") + f": {self.profile.get('name')}" + (f" · {' · '.join(map(str, bits))}" if bits else "") if name else
                    tr("Not linked to a target model – pick a checkpoint to link it to") + f" {self.profile.get('name')}")

    def apply_profile_checkpoint(self):
        """Target model changed: use its linked checkpoint, else a confident unique auto-match, else leave it."""
        if not hasattr(self, "img_ckpt"):
            return None
        name = self.profile_checkpoints().get(self.profile.get("id"))
        if not name:
            names = getattr(self, "_ckpt_names", None)
            if names is None and (self.profile.get("civitai") and not os.environ.get("PROMPTMAKER_NO_NET")
                                  and self.store.get("img_backend", "none") != "none"):
                self._ckpt_match_pending = True; self.load_checkpoints()  # background; re-runs when the list arrives
            from . import ckptmatch
            name = ckptmatch.match(self.profile, names or [])
            name = name and strip_ckpt_hash(name)
        if name and name != self.store.get(f"img_checkpoint:{self.ckpt_key()}", ""):
            self._applying_profile_ckpt = True
            try:
                self.set_checkpoint(name)
                if self._settings_ckpt_key() == self.ckpt_key() and self.img_ckpt.name() != name:
                    self.img_ckpt.set_name(name)
            finally:
                self._applying_profile_ckpt = False
        self._update_ckpt_link_label()
        return name

    def load_checkpoints(self, backend=None, combos=None, force=False):
        """Ask the backend for its checkpoints (in a worker) and fill the pickers."""
        backend = backend or self.image_backend()
        import time as _t
        busy = getattr(self, "_ckpt_loading", False) and _t.time() - getattr(self, "_ckpt_loading_since", 0) < 20
        if not backend or (busy and not force):
            return
        self._ckpt_loading = True; self._ckpt_loading_since = _t.time()
        self._ckpt_placeholder(tr("Loading checkpoints…"), combos)
        wk = CallWorker(backend.checkpoints)
        def ok(lst):
            self._ckpt_loading = False
            self._ckpt_placeholder(tr("Backend default (whatever is loaded)"))
            self._ckpt_names = list(lst or [])
            for c in combos or self._ckpt_combos_list():
                c.set_items(lst or [])
            if getattr(self, "_ckpt_match_pending", False):
                self._ckpt_match_pending = False; self.apply_profile_checkpoint()
        def failed(_e):
            self._ckpt_loading = False
            self._ckpt_placeholder(tr("Backend default (whatever is loaded)"))
        wk.ok.connect(ok); wk.failed.connect(failed); self._keep(wk); wk.start()

    def _ckpt_placeholder(self, text, combos=None):
        """Skeleton text in empty checkpoint pickers while the list loads."""
        for c in combos or self._ckpt_combos_list():
            if c.lineEdit() is not None:
                c.lineEdit().setPlaceholderText(text)

    def _autoload_checkpoints(self):
        if os.environ.get("PROMPTMAKER_NO_NET") or self.store.get("img_backend", "none") == "none":
            return
        if any(c.count() == 0 for c in self._ckpt_combos_list()):
            self.load_checkpoints()

    def _apply_portable(self):
        want = self.portable.isChecked()
        if want == paths.is_portable(APP_DIR):
            self.notify(tr("Already using that mode")); return
        try:
            new = paths.set_portable(APP_DIR, want)
        except OSError as e:
            self.notify(str(e), error=True); return
        self.notify(tr("Data will be stored in") + f" {new}. " + tr("Restart PromptMaker to switch."))

    # ------------------------------------------------------------------ updates & tour
    def check_updates(self, manual=False):
        wk = CallWorker(updates.check, __version__)
        def ok(res):
            if res:
                tag, url = res
                self.update_btn.setText(f"⬆ {tr('Update available')}: {tag}"); self.update_btn.setVisible(True)
                self.update_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
                self.notify(f"{tr('PromptMaker')} {tag} {tr('is available')}")
            elif manual:
                self.notify(tr("You're on the latest version") + f" ({__version__})")
        wk.ok.connect(ok)
        wk.failed.connect(lambda e: manual and self.notify(tr("Couldn't check for updates") + f": {e[:120]}", error=True))
        self._keep(wk); wk.start()

    TOUR = [("Home", "Your dashboard: target model, linked checkpoint, Forge / Ollama status, recent images and quick-start buttons. "
                     "The « button collapses the sidebar to icons; the dot below it shows the image backend – click it for settings, ☰ opens the queue."),
            ("Create", "Start here: describe an idea in plain words and the AI writes a finished prompt for your target model. Press Ctrl+K anywhere for the quick bar."),
            ("Builder", "Or build a prompt by clicking preset chips. Pick the target model in the sidebar – the output adapts automatically."),
            ("Refine", "Chat with the AI to improve a prompt. Apply suggestions with one click and revert any time."),
            ("Image to Prompt", "Drop an image and a vision model turns it into a prompt."),
            ("Auto-refine", "New in 3.0: generate, let a vision model check the image against your idea, and refine the prompt automatically."),
            ("Pose", "Sketch poses and subject boxes – they become composition tags, or an OpenPose image for ControlNet."),
            ("Inpaint & Regions", "New in 4.0: paint a mask to redraw part of an image, or draw boxes that each get their own prompt."),
            ("Wildcards", "New in 4.0: __wildcards__ and {a|b|c} turn one prompt into many varied ones – the AI can write lists for you."),
            ("Video", "New in 4.0: prompts for Wan, LTX-Video and HunyuanVideo with camera moves and the right structure for each."),
            ("Library sync", "New in 4.0: export or import everything, or sync it to a private GitHub gist."),
            ("Gallery", "Connect ComfyUI or Forge in Settings to generate images – they land here with full metadata."),
            ("Settings", "Choose your AI provider (Ollama, LM Studio, cloud…), image backend, language and data location. Enjoy!")]

    def start_tour(self):
        self._tour_i = 0
        if not hasattr(self, "tour"):
            self.tour = QFrame(self.centralWidget()); self.tour.setObjectName("card")
            tl = QVBoxLayout(self.tour); tl.setContentsMargins(20, 16, 20, 16)
            self.tour_title = label("", "h2"); self.tour_text = label("", wrap=True)
            tl.addWidget(self.tour_title); tl.addWidget(self.tour_text)
            self.tour_next = button(tr("Next"), self._tour_step, "primary")
            tl.addLayout(hrow(button(tr("Skip tour"), self._tour_end, "ghost"), None, self.tour_next))
        self.tour.setFixedWidth(420)
        self._tour_show()

    def _tour_show(self):
        name, text = self.TOUR[self._tour_i]
        self.go(name)
        self.tour_title.setText(f"{self._tour_i + 1}/{len(self.TOUR)} · {tr(name)}")
        self.tour_text.setText(tr(text))
        self.tour_next.setText(tr("Finish") if self._tour_i == len(self.TOUR) - 1 else tr("Next"))
        self.tour.adjustSize()
        cw = self.centralWidget()
        self.tour.move(cw.width() - self.tour.width() - 30, 80)
        self.tour.show(); self.tour.raise_()

    def _tour_step(self):
        self._tour_i += 1
        if self._tour_i >= len(self.TOUR):
            self._tour_end()
        else:
            self._tour_show()

    def _tour_end(self):
        self.tour.hide(); self.store.set("tour_done", True); self.go("Create")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "toast") and self.toast.isVisible():
            p = self.toast.parentWidget()
            self.toast.move(p.width() - self.toast.width() - 24, p.height() - self.toast.height() - 24)


ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def app_icon():
    from PySide6.QtGui import QIcon
    ico = QIcon()
    for name in ("icon.ico", "icon_256.png"):
        f = os.path.join(ICON_DIR, name)
        if os.path.exists(f):
            ico.addFile(f)
    return ico


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kisahime.PromptMaker")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(argv)
    app.setApplicationName("PromptMaker")
    app.setWindowIcon(app_icon())
    data_dir = paths.data_dir(APP_DIR)
    store = Store(os.path.join(data_dir, "promptmaker.db"))
    i18n.set_language(store.get("language", "en"))
    if "--smoke-test" in argv:
        os.environ.setdefault("PROMPTMAKER_NO_NET", "1"); os.environ.setdefault("PROMPTMAKER_NO_TOUR", "1")
    win = MainWindow(store, data_dir)
    win.show()
    if "--smoke-test" in argv:
        def tour():
            for i in range(len(NAV)):
                win.nav.setCurrentRow(i); app.processEvents()
            win.idea.setPlainText("an anime girl wearing an outfit in a setting"); win.create_offline(); win.open_quickbar()
            win.randomise(True); win.quick_analyse(); win.quick_score(); win.toggle_theme(); win.toggle_theme()
            win.notify("smoke ok")
        QTimer.singleShot(500, tour)
        QTimer.singleShot(2500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
