"""5.3 Video maker page (Tools → Video maker): idea / story (+ optional song & lyrics) -> AI scene plan -> stills
(Forge / ComfyUI) -> Wan2GP clips for ticked scenes, Ken Burns for the rest -> ffmpeg MP4."""
import os
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QProgressBar, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget)

from . import imagegen, wan2gp, wanconfigs
from . import videoproject as vp
from .i18n import tr
from .widgets import Card, button, hrow, label

FACELOCK_INFO = ("Face lock only works with SDXL / Illustrious / Pony checkpoints. With other models (Anima, MOSS, "
                 "FLUX, Qwen …) the reference face is ignored – descriptions and seeds still apply.")
COLS = ["#", "Prompt", "Secs", "Camera", "Animate", "Status"]


class VideoWorker(QThread):
    """Runs one pipeline step off the UI thread; cancel() stops it between (and inside) scenes."""
    progress = Signal(int, str)
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn, self.cancel_event = fn, threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            self.ok.emit(self.fn(lambda pct, msg: self.progress.emit(int(pct), str(msg)), self.cancel_event.is_set))
        except Exception as e:  # noqa: BLE001
            self.failed.emit("Cancelled" if isinstance(e, vp.Cancelled) or str(e) == "Cancelled" else str(e))


class VideoMakerPage:
    def _videomaker_page(self):
        from .app import page
        w, v = page("Video maker", "Turn an idea or story into a short video: the AI plans scenes, each gets a still, "
                                   "ticked scenes are animated with Wan2GP and the rest get a slow zoom or pan, then "
                                   "ffmpeg joins them with crossfades, captions and your song.")
        split = QSplitter(Qt.Horizontal)
        # ---------------- project / idea
        pc = Card("Project")
        self.vm_name = QLineEdit(self.store.get("vm_last", "") or tr("My video")); self.vm_name.setPlaceholderText(tr("Project name"))
        self.vm_open = QComboBox(); self.vm_open.setMinimumWidth(140)
        pc.add(hrow(label("Name"), self.vm_name, button("💾 Save", self.vm_save, "ghost")))
        pc.add(hrow(label("Open"), self.vm_open, button("📂 Open", self.vm_open_selected, "ghost"), button("＋ New", self.vm_new, "ghost")))
        self.vm_idea = QPlainTextEdit(); self.vm_idea.setPlaceholderText(tr("Idea or story, e.g. two adult friends cycle "
                                                                            "through a seaside town at sunrise and end with ice cream on the pier"))
        pc.add(label("Idea / story", "muted")); pc.add(self.vm_idea, 1)
        self.vm_style = QLineEdit(); self.vm_style.setPlaceholderText(tr("Style prefix (optional), e.g. anime style, soft pastel colours"))
        pc.add(hrow(label("Style"), self.vm_style))
        self.vm_n = QSpinBox(); self.vm_n.setRange(1, 40); self.vm_n.setValue(int(self.store.get("vm_n", 8)))
        self.vm_xf = QDoubleSpinBox(); self.vm_xf.setRange(0, 2); self.vm_xf.setSingleStep(0.1); self.vm_xf.setValue(float(self.store.get("vm_xf", 0.4)))
        pc.add(hrow(label("Scenes"), self.vm_n, label("Crossfade s"), self.vm_xf, None))
        self.vm_song = QLineEdit(); self.vm_song.setPlaceholderText(tr("Song (optional) – mp3 / wav"))
        self.vm_song_secs = QDoubleSpinBox(); self.vm_song_secs.setRange(0, 3600); self.vm_song_secs.setDecimals(2)
        self.vm_song_secs.setToolTip(tr("Song length in seconds – scenes are fitted to it (0 = no song)"))
        pc.add(hrow(label("Song"), self.vm_song, button("…", self.vm_pick_song, "ghost")))
        pc.add(hrow(label("Length s"), self.vm_song_secs, None))
        self.vm_lyrics = QPlainTextEdit(); self.vm_lyrics.setPlaceholderText(tr("Lyrics (optional) – one line per scene; "
                                                                                "[mm:ss] LRC timestamps are used for timing"))
        self.vm_lyrics.setMaximumHeight(110); pc.add(self.vm_lyrics)
        self.vm_captions = QCheckBox(tr("Show captions")); self.vm_captions.setChecked(True)
        self.vm_ad = QCheckBox(tr("ADetailer faces (Forge)")); self.vm_ad.setChecked(bool(self.store.get("vm_ad", False)))
        self.vm_ad.setToolTip(tr("Runs the ADetailer passes set in Settings - Image generation on every still ""(face_yolov8s.pt when none are set). Forge only."))
        pc.add(hrow(self.vm_captions, self.vm_ad, None))
        pc.add(hrow(button("🧠 Plan scenes with AI", self.vm_plan, "primary"), None))
        cc = Card("Characters")
        self.vm_chars = QListWidget(); self.vm_chars.setMinimumHeight(56); self.vm_chars.setMaximumHeight(90)
        self.vm_chars.currentRowChanged.connect(self.vm_char_select)
        cc.add(self.vm_chars)
        self.vm_ch_name = QLineEdit(); self.vm_ch_name.setPlaceholderText(tr("Name"))
        self.vm_ch_main = QCheckBox(tr("Main"))
        self.vm_ch_desc = QPlainTextEdit(); self.vm_ch_desc.setMaximumHeight(70)
        self.vm_ch_desc.setPlaceholderText(tr("Fixed description, used word for word in every scene: adult woman, "
                                              "long silver hair, green eyes, red jacket, jeans"))
        self.vm_ch_ref = QLineEdit(); self.vm_ch_ref.setPlaceholderText(tr("Reference face (optional) – face lock"))
        self.vm_ch_ref.setToolTip(tr(FACELOCK_INFO))
        self.vm_ch_ref.textChanged.connect(lambda _t: self.vm_update_facelock_warning())
        self.vm_ch_seed = QSpinBox(); self.vm_ch_seed.setRange(-1, 2 ** 31 - 1); self.vm_ch_seed.setSpecialValueText(tr("random"))
        cc.add(hrow(self.vm_ch_name, self.vm_ch_main)); cc.add(self.vm_ch_desc)
        cc.add(hrow(self.vm_ch_ref, button("…", self.vm_char_pick_ref, "ghost")))
        self.vm_fl_info = label(FACELOCK_INFO, "hint", wrap=True); cc.add(self.vm_fl_info)
        self.vm_fl_warn = QLabel(); self.vm_fl_warn.setWordWrap(True); self.vm_fl_warn.setVisible(False); self.vm_fl_warn.setMinimumHeight(66)
        self.vm_fl_warn.setStyleSheet("QLabel{background:#4a3200;color:#ffc94d;border:1px solid #e0a000;"
                                      "border-radius:6px;padding:6px;font-weight:600;}")
        cc.add(self.vm_fl_warn)
        cc.add(hrow(label("Seed"), self.vm_ch_seed, button("🎲", lambda: self.vm_ch_seed.setValue(imagegen.new_seed() % (2 ** 31 - 1)), "ghost"), None))
        self.vm_ch_import = QComboBox(); self.vm_ch_import.setMinimumWidth(120)
        cc.add(hrow(button("＋ Add", self.vm_char_add, "ghost"), button("✓ Apply", self.vm_char_apply, "ghost"),
                    button("🗑 Delete", self.vm_char_del, "ghost"), None))
        cc.add(hrow(self.vm_ch_import, button("↙ Import from Characters", self.vm_char_import, "ghost")))
        lv = QSplitter(Qt.Vertical); lv.addWidget(pc); lv.addWidget(cc)
        split.addWidget(lv)
        # ---------------- scenes
        sc = Card("Scenes")
        self.vm_table = QTableWidget(0, len(COLS)); self.vm_table.setHorizontalHeaderLabels([tr(c) for c in COLS])
        hh = self.vm_table.horizontalHeader(); hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (0, 2, 4, 5):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.vm_table.setIconSize(self.vm_table.iconSize().expandedTo(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(64, 36)))
        self.vm_table.setSelectionBehavior(QTableWidget.SelectRows); self.vm_table.setSelectionMode(QTableWidget.SingleSelection)
        self.vm_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vm_table.currentCellChanged.connect(lambda r, *_: self.vm_select(r))
        self.vm_table.itemChanged.connect(self._vm_item_changed)
        sc.add(self.vm_table, 1)
        sc.add(hrow(button("＋ Add", self.vm_add_scene, "ghost"), button("🗑 Delete", self.vm_del_scene, "ghost"),
                    button("▲", lambda: self.vm_move(-1), "ghost"), button("▼", lambda: self.vm_move(1), "ghost"), None,
                    label("", "hint")))
        self.vm_prompt = QPlainTextEdit(); self.vm_prompt.setMaximumHeight(90); self.vm_prompt.setPlaceholderText(tr("Still image prompt"))
        self.vm_motion = QLineEdit(); self.vm_motion.setPlaceholderText(tr("Motion for Wan2GP, e.g. her hair moves in the wind"))
        self.vm_caption = QLineEdit(); self.vm_caption.setPlaceholderText(tr("Caption (optional)"))
        self.vm_secs = QDoubleSpinBox(); self.vm_secs.setRange(0.5, 60); self.vm_secs.setDecimals(2)
        self.vm_cam = QComboBox(); self.vm_cam.addItems(vp.CAMERAS)
        self.vm_anim = QCheckBox(tr("Animate with Wan2GP"))
        self.vm_scene_chars = QListWidget(); self.vm_scene_chars.setMaximumHeight(70)
        self.vm_scene_seed = QSpinBox(); self.vm_scene_seed.setRange(-1, 2 ** 31 - 1)
        self.vm_scene_seed.setSpecialValueText(tr("character's seed")); self.vm_scene_seed.setMinimumWidth(130)
        sc.add(self.vm_prompt); sc.add(hrow(label("Motion"), self.vm_motion)); sc.add(hrow(label("Caption"), self.vm_caption))
        sc.add(hrow(label("Secs"), self.vm_secs, label("Camera"), self.vm_cam, self.vm_anim, None))
        self.vm_anim_from = label("", "hint", wrap=True)
        self.vm_override = QCheckBox(tr("Override animation for this scene"))
        self.vm_override.toggled.connect(self._vm_override_toggled)
        sc.add(self.vm_anim_from)
        sc.add(self.vm_override)
        self.vm_override_box = QWidget()
        ov = QVBoxLayout(self.vm_override_box); ov.setContentsMargins(0, 0, 0, 0)
        self.vm_scene_model = QComboBox()
        self.vm_scene_model.currentIndexChanged.connect(self._vm_scene_model_changed)
        self.vm_scene_frames = QSpinBox(); self.vm_scene_frames.setRange(1, 1800)
        self.vm_scene_steps = QSpinBox(); self.vm_scene_steps.setRange(1, 100)
        self.vm_scene_guidance = QDoubleSpinBox(); self.vm_scene_guidance.setRange(0, 30); self.vm_scene_guidance.setDecimals(2)
        self.vm_scene_lora = QComboBox(); self.vm_scene_strength = QDoubleSpinBox()
        self.vm_scene_strength.setRange(0, 4); self.vm_scene_strength.setSingleStep(0.05); self.vm_scene_strength.setValue(1)
        self.vm_scene_switch = QLabel(); self.vm_scene_switch.setWordWrap(True); self.vm_scene_switch.setVisible(False)
        self.vm_scene_switch.setStyleSheet("QLabel{background:#4a3200;color:#ffc94d;border:1px solid #e0a000;border-radius:6px;padding:6px;font-weight:600;}")
        ov.addLayout(hrow(label("Model"), self.vm_scene_model))
        ov.addLayout(hrow(label("Frames"), self.vm_scene_frames, label("Steps"), self.vm_scene_steps, label("Guidance"), self.vm_scene_guidance))
        ov.addLayout(hrow(label("Creative LoRA"), self.vm_scene_lora, label("Strength"), self.vm_scene_strength))
        ov.addWidget(self.vm_scene_switch)
        self.vm_override_box.setVisible(False)
        sc.add(self.vm_override_box)
        sc.add(hrow(button("Use current settings", self.vm_use_current, "ghost"), None))
        sc.add(hrow(label("In this scene"), self.vm_scene_chars, label("Seed"), self.vm_scene_seed))
        self.vm_facelock = label("", "hint", wrap=True); sc.add(self.vm_facelock)
        sc.add(hrow(button("✓ Apply", self.vm_apply_scene, "ghost"), button("⟳ Redo still", lambda: self.vm_redo("still"), "ghost"),
                    button("⟳ Redo clip", lambda: self.vm_redo("clip"), "ghost"), None))
        split.addWidget(sc)
        # ---------------- run / preview / tools
        rc = Card("Make")
        self.vm_preview = QLabel(tr("Scene preview")); self.vm_preview.setAlignment(Qt.AlignCenter)
        self.vm_preview.setMinimumSize(320, 180); self.vm_preview.setObjectName("dropZone")
        rc.add(self.vm_preview, 1)
        self.vm_bar = QProgressBar(); self.vm_bar.setRange(0, 100); rc.add(self.vm_bar)
        self.vm_status = label("", "hint", wrap=True); rc.add(self.vm_status)
        rc.add(hrow(button("🖼 Make stills", self.vm_stills, "primary"), button("🎞 Animate ticked", self.vm_animate, "primary")))
        rc.add(hrow(button("🎬 Build video", self.vm_build, "primary"), button("▶ Run all", self.vm_run_all, "ghost")))
        rc.add(hrow(button("■ Cancel", self.vm_cancel, "ghost"), button("📂 Folder", self.vm_open_folder, "ghost"), None))
        tc = Card("Tools")
        wd, py = wan2gp.detect(self.store.get("vm_wan_dir", ""), self.store.get("vm_wan_python", ""))
        self.vm_wan_dir = QLineEdit(wd); self.vm_wan_dir.setPlaceholderText(wan2gp.DEFAULT_DIR)
        self.vm_wan_py = QLineEdit(py); self.vm_wan_py.setPlaceholderText(r"…\wan.git\app\venv\Scripts\python.exe")
        self.vm_ffmpeg = QLineEdit(vp.find_ffmpeg(self.store.get("vm_ffmpeg", ""), wd)); self.vm_ffmpeg.setPlaceholderText("ffmpeg.exe")
        self.vm_model = QComboBox(); self.vm_model.currentIndexChanged.connect(self._vm_model_changed)
        self.vm_model_status = label("", "hint", wrap=True)
        self.vm_resolution = QComboBox()
        self.vm_frames = QSpinBox(); self.vm_frames.setRange(1, 1800); self.vm_frames.setValue(int(self.store.get("vm_frames", vp.WAN_FRAMES)))
        self.vm_frames.setEnabled(False)
        self.vm_frames.setToolTip(tr("Frames are calculated from each scene's length. This model's own recorded count is shown here and is not sent."))
        self.vm_steps = QSpinBox(); self.vm_steps.setRange(1, 100); self.vm_steps.setValue(int(self.store.get("vm_steps", 3)))
        self.vm_guidance = QDoubleSpinBox(); self.vm_guidance.setRange(0, 30); self.vm_guidance.setDecimals(2)
        self.vm_guidance.setValue(float(self.store.get("vm_guidance", 1)))
        self.vm_flow = QDoubleSpinBox(); self.vm_flow.setRange(0, 30); self.vm_flow.setDecimals(2)
        self.vm_flow.setValue(float(self.store.get("vm_flow", 3)))
        self.vm_lora = QComboBox(); self.vm_lora.currentIndexChanged.connect(self._vm_lora_changed)
        self.vm_lora_strength = QDoubleSpinBox(); self.vm_lora_strength.setRange(0, 4); self.vm_lora_strength.setSingleStep(0.05)
        self.vm_lora_strength.setValue(float(self.store.get("vm_lora_strength", 1)))
        self.vm_lora_strength.setToolTip(tr("Constant strength for this one creative LoRA. There is no guaranteed safe range, "
                                            "and this does not turn the model's acceleration adapter off."))
        self.vm_lora_note = label("", "hint", wrap=True)
        self.vm_switch_note = QLabel(); self.vm_switch_note.setWordWrap(True); self.vm_switch_note.setVisible(False)
        self.vm_switch_note.setStyleSheet("QLabel{background:#4a3200;color:#ffc94d;border:1px solid #e0a000;border-radius:6px;padding:6px;font-weight:600;}")
        tc.add(hrow(label("Wan2GP folder"), self.vm_wan_dir)); tc.add(hrow(label("Wan2GP python"), self.vm_wan_py))
        tc.add(hrow(label("ffmpeg"), self.vm_ffmpeg))
        tc.add(hrow(label("Model"), self.vm_model))
        tc.add(self.vm_model_status)
        tc.add(hrow(label("Resolution"), self.vm_resolution, label("Guidance"), self.vm_guidance, label("Flow"), self.vm_flow))
        tc.add(hrow(label("Frames"), self.vm_frames, label("Steps"), self.vm_steps, None))
        self.vm_frames_hint = label("", "hint", wrap=True)
        self.vm_frames.valueChanged.connect(self._vm_frames_changed)
        tc.add(self.vm_frames_hint)
        tc.add(hrow(label("Creative LoRA"), self.vm_lora, label("Strength"), self.vm_lora_strength, button("…", self.vm_pick_lora, "ghost")))
        tc.add(self.vm_lora_note)
        tc.add(self.vm_switch_note)
        tc.add(hrow(button("⟳ Detect", self.vm_detect_tools, "ghost"), button("Save", self.vm_save_tools), None))
        tc.add(label("FastWan 5B stays the default model: 1280×704 and 3 steps. Each animated scene's frames are its "
                     "length in seconds times the model's frame rate. Other models keep their own resolution, steps and "
                     "guidance. Switching models resets values they do not share, including "
                     "a creative LoRA. None leaves any acceleration adapter on. No VRAM estimate, and missing files are "
                     "reported by name — nothing is downloaded. A dry run is not used and would not prove the job fits.",
                     "hint", wrap=True))
        rv = QSplitter(Qt.Vertical); rv.addWidget(rc); rv.addWidget(tc)
        split.addWidget(rv); split.setSizes([360, 560, 420])
        v.addWidget(split, 1)
        self.vm_proj = vp.new_project(self.vm_name.text()); self.vm_cur = -1; self._vm_worker = None; self._vm_chain = []
        self.vm_char_cur = -1
        self._vm_presets = {}; self._vm_model_id = ""; self._vm_scene_model_id = ""
        self._vm_loading_model = False; self._vm_loading_scene = False
        self._vm_reload_presets()
        self.vm_refresh_projects(); self.vm_char_refresh(); self.vm_refresh()
        return w

    # ------------------------------------------------------------------ project
    def vm_dir(self):
        return vp.project_dir(self.data_dir, self.vm_name.text().strip() or self.vm_proj.get("name") or "Untitled video")

    def _vm_collect(self):
        p = self.vm_proj
        p.update(name=self.vm_name.text().strip() or "Untitled video", idea=self.vm_idea.toPlainText().strip(),
                 style=self.vm_style.text().strip(), song=self.vm_song.text().strip(), lyrics=self.vm_lyrics.toPlainText(),
                 song_secs=float(self.vm_song_secs.value()), crossfade=float(self.vm_xf.value()),
                 captions=self.vm_captions.isChecked(), adetailer=self.vm_ad.isChecked(),
                 family=(getattr(self, "profile", None) or {}).get("family", ""),
                 animation=self._vm_animation_from_widgets())
        res = str(p["animation"].get("resolution") or "1280x704")
        try:
            p["size"] = [int(x) for x in res.lower().split("x")]
        except ValueError:
            pass
        self.store.set("vm_n", self.vm_n.value()); self.store.set("vm_xf", float(self.vm_xf.value())); self.store.set("vm_ad", self.vm_ad.isChecked())
        return p

    def vm_save(self):
        self._vm_collect()
        path = vp.save_project(self.vm_proj, self.vm_dir())
        self.store.set("vm_last", self.vm_proj["name"]); self.vm_refresh_projects()
        self.vm_status.setText(tr("Saved") + " · " + path)
        return path

    def vm_refresh_projects(self):
        self.vm_open.clear()
        for name, d in vp.list_projects(self.data_dir):
            self.vm_open.addItem(name, d)

    def vm_new(self):
        self.vm_proj = vp.new_project(tr("My video")); self._vm_load_fields(); self.vm_cur = -1; self.vm_refresh()

    def vm_open_selected(self):
        d = self.vm_open.currentData()
        return self.vm_load(d) if d else False

    def vm_load(self, pdir):
        try:
            self.vm_proj = vp.load_project(pdir)
        except (OSError, ValueError) as e:
            self.notify(str(e), error=True); return False
        self._vm_load_fields(); self.vm_cur = 0 if self.vm_proj["scenes"] else -1; self.vm_refresh()
        self.store.set("vm_last", self.vm_proj["name"])
        return True

    def _vm_load_fields(self):
        p = self.vm_proj
        self.vm_name.setText(p["name"]); self.vm_idea.setPlainText(p.get("idea", "")); self.vm_style.setText(p.get("style", ""))
        self.vm_song.setText(p.get("song", "")); self.vm_song_secs.setValue(float(p.get("song_secs") or 0))
        self.vm_lyrics.setPlainText(p.get("lyrics", "")); self.vm_xf.setValue(float(p.get("crossfade", 0.4)))
        self.vm_captions.setChecked(bool(p.get("captions", True))); self.vm_ad.setChecked(bool(p.get("adetailer")))
        self._vm_apply_controls(p.get("animation") or wanconfigs.default_animation(), reset_note=False)
        self.vm_char_refresh()

    def vm_pick_song(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Song"), "", "Audio (*.mp3 *.wav *.m4a *.ogg *.flac)")
        if path:
            self.vm_set_song(path)

    def vm_set_song(self, path):
        self.vm_song.setText(path)
        ff = self.vm_ffmpeg.text().strip()
        if ff and os.path.isfile(path):
            secs = vp.probe_secs(ff, path)
            if secs:
                self.vm_song_secs.setValue(round(secs, 2))

    # ------------------------------------------------------------------ plan
    def vm_plan(self):
        self._vm_collect()
        if not self.vm_proj["idea"]:
            self.notify(tr("Write the idea or story first"), error=True); return False
        msgs = vp.plan_messages(self.vm_proj, self.vm_n.value(), getattr(self, "profile", None))
        self.vm_status.setText(tr("Planning scenes…"))
        return self.run_ai(msgs, lambda _c: None, self.vm_apply_plan, json_mode=True, temperature=0.6)

    def vm_apply_plan(self, text):
        self._vm_collect()
        title, scenes = vp.parse_plan(text, self.vm_proj)
        if not scenes:
            self.notify(tr("The AI didn't return a usable plan – try again or add scenes by hand"), error=True); return 0
        if title and self.vm_name.text().strip() in ("", tr("My video")):
            self.vm_name.setText(title); self.vm_proj["name"] = title
        self.vm_proj["scenes"] = scenes; self.vm_cur = 0
        self.vm_save(); self.vm_refresh()
        self.vm_status.setText(f"{tr('Planned')} {len(scenes)} {tr('scenes')} · {vp.total_secs(self.vm_proj):.1f} s")
        return len(scenes)

    # ------------------------------------------------------------------ scene list
    def vm_refresh(self):
        t = self.vm_table; t.blockSignals(True); t.setRowCount(len(self.vm_proj["scenes"]))
        pdir = self.vm_dir()
        for r, s in enumerate(self.vm_proj["scenes"]):
            it = QTableWidgetItem(s["id"])
            if s.get("still"):
                pm = QPixmap(os.path.join(pdir, s["still"]))
                if not pm.isNull():
                    it.setIcon(QIcon(pm.scaled(64, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            t.setItem(r, 0, it)
            t.setItem(r, 1, QTableWidgetItem(s["prompt"][:120]))
            t.setItem(r, 2, QTableWidgetItem(f"{float(s['duration']):.2f}"))
            t.setItem(r, 3, QTableWidgetItem(tr(s.get("camera", ""))))
            a = QTableWidgetItem(); a.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            a.setCheckState(Qt.Checked if s.get("animate") else Qt.Unchecked); t.setItem(r, 4, a)
            t.setItem(r, 5, QTableWidgetItem(tr(vp.scene_status(s))))
        t.blockSignals(False)
        if 0 <= self.vm_cur < t.rowCount():
            t.selectRow(self.vm_cur)
        self.vm_select(self.vm_cur)
        self._vm_update_frames_hint()

    def _vm_item_changed(self, item):
        if item.column() == 4 and 0 <= item.row() < len(self.vm_proj["scenes"]):
            self.vm_proj["scenes"][item.row()]["animate"] = item.checkState() == Qt.Checked
            self._vm_update_frames_hint()
            if item.row() == self.vm_cur:
                self.vm_anim.setChecked(self.vm_proj["scenes"][item.row()]["animate"])

    def vm_select(self, r):
        self.vm_cur = r
        ok = 0 <= r < len(self.vm_proj["scenes"])
        s = self.vm_proj["scenes"][r] if ok else vp.new_scene()
        self.vm_prompt.setPlainText(s["prompt"]); self.vm_motion.setText(s.get("motion", "")); self.vm_caption.setText(s.get("caption", ""))
        self.vm_secs.setValue(float(s.get("duration") or 4)); self.vm_cam.setCurrentText(s.get("camera", vp.CAMERAS[0]))
        self.vm_anim.setChecked(bool(s.get("animate")))
        self._vm_show_scene_animation(s if ok else None)
        self.vm_scene_seed.setValue(int(s.get("seed", -1)))
        self.vm_scene_chars.clear()
        for c in self.vm_proj.get("characters") or []:
            it = QListWidgetItem(c["name"] + (" ★" if c.get("main") else "")); it.setData(Qt.UserRole, c["id"])
            it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(Qt.Checked if c["id"] in (s.get("characters") or []) else Qt.Unchecked)
            self.vm_scene_chars.addItem(it)
        self.vm_facelock.setText(s.get("facelock", "") if ok else "")
        pm = QPixmap(os.path.join(self.vm_dir(), s["still"])) if ok and s.get("still") else QPixmap()
        if pm.isNull():
            self.vm_preview.setText(tr("Scene preview"))
        else:
            self.vm_preview.setPixmap(pm.scaled(max(200, self.vm_preview.width() - 8), max(120, self.vm_preview.height() - 8),
                                                Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def vm_apply_scene(self):
        if not 0 <= self.vm_cur < len(self.vm_proj["scenes"]):
            return False
        s = self.vm_proj["scenes"][self.vm_cur]
        new_prompt = self.vm_prompt.toPlainText().strip()
        chars = [self.vm_scene_chars.item(i).data(Qt.UserRole) for i in range(self.vm_scene_chars.count())
                 if self.vm_scene_chars.item(i).checkState() == Qt.Checked]
        seed = int(self.vm_scene_seed.value())
        if new_prompt != s["prompt"] or chars != list(s.get("characters") or []) or seed != int(s.get("seed", -1)):
            vp.redo_scene(s, self.vm_dir(), "still")
        s["characters"], s["seed"] = chars, seed
        motion = self.vm_motion.text().strip()
        override = self._vm_scene_animation() if self.vm_override.isChecked() else None
        new_duration = float(self.vm_secs.value())
        if (motion != (s.get("motion") or "") or override != s.get("animation_override")
                or abs(new_duration - float(s.get("duration") or 0)) > 0.01):
            s["resolved"] = None
            if abs(new_duration - float(s.get("duration") or 0)) > 0.01 and s.get("clip"):
                vp.redo_scene(s, self.vm_dir(), "clip")
        s["animation_override"] = override
        s.update(prompt=new_prompt, motion=motion, caption=self.vm_caption.text().strip(),
                 duration=new_duration, camera=self.vm_cam.currentText(), animate=self.vm_anim.isChecked())
        self.vm_save(); self.vm_refresh()
        return True

    def vm_add_scene(self):
        n = len(self.vm_proj["scenes"])
        ids = {s["id"] for s in self.vm_proj["scenes"]}
        s = vp.new_scene(n); i = n
        while s["id"] in ids:
            i += 1; s["id"] = f"s{i + 1:02d}"
        self.vm_proj["scenes"].append(s); self.vm_cur = n; self.vm_refresh()

    def vm_del_scene(self):
        if 0 <= self.vm_cur < len(self.vm_proj["scenes"]):
            self.vm_proj["scenes"].pop(self.vm_cur); self.vm_cur = min(self.vm_cur, len(self.vm_proj["scenes"]) - 1); self.vm_refresh()

    def vm_move(self, d):
        ss, r = self.vm_proj["scenes"], self.vm_cur
        if 0 <= r < len(ss) and 0 <= r + d < len(ss):
            ss[r], ss[r + d] = ss[r + d], ss[r]; self.vm_cur = r + d; self.vm_refresh()

    def vm_redo(self, what):
        if not 0 <= self.vm_cur < len(self.vm_proj["scenes"]):
            return False
        vp.redo_scene(self.vm_proj["scenes"][self.vm_cur], self.vm_dir(), what)
        self.vm_save(); self.vm_refresh()
        self.vm_status.setText(tr("Scene cleared – it is made again on the next run"))
        return True

    # ------------------------------------------------------------------ tools
    def vm_detect_tools(self):
        wd, py = wan2gp.detect(self.vm_wan_dir.text().strip(), self.vm_wan_py.text().strip())
        self.vm_wan_dir.setText(wd); self.vm_wan_py.setText(py)
        self.vm_ffmpeg.setText(vp.find_ffmpeg(self.vm_ffmpeg.text().strip(), wd))
        self._vm_reload_presets()
        self.vm_status.setText(f"Wan2GP: {wd or tr('not found')} · ffmpeg: {self.vm_ffmpeg.text() or tr('not found')}")

    def vm_save_tools(self):
        for k, wdg in (("vm_wan_dir", self.vm_wan_dir), ("vm_wan_python", self.vm_wan_py), ("vm_ffmpeg", self.vm_ffmpeg)):
            self.store.set(k, wdg.text().strip())
        anim = self._vm_animation_from_widgets()
        self.store.set("vm_model", anim["model_id"]); self.store.set("vm_frames", anim["frames"]); self.store.set("vm_steps", anim["steps"])
        self.store.set("vm_guidance", anim["guidance"]); self.store.set("vm_flow", anim["flow_shift"])
        self.store.set("vm_lora", anim["creative_lora"]); self.store.set("vm_lora_strength", anim["creative_strength"])
        self.store.set("vm_resolution", anim["resolution"])
        self.notify(tr("Saved"))

    def _vm_preset(self, model_id):
        return (getattr(self, "_vm_presets", {}) or {}).get(model_id) or wanconfigs.preset_by_id(
            self.vm_wan_dir.text().strip() if hasattr(self, "vm_wan_dir") else "", model_id)

    def _vm_fill_model_combo(self, combo, current):
        combo.blockSignals(True)
        combo.clear()
        for preset in self._vm_presets.values():
            combo.addItem(preset["name"], preset["id"])
        if combo.count() == 0:
            combo.addItem("Wan2.2 TextImage2video FastWan 5B", wanconfigs.FASTWAN_ID)
        idx = combo.findData(current) if current else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _vm_reload_presets(self):
        wan_dir = self.vm_wan_dir.text().strip()
        ordered = wanconfigs.catalog(wan_dir)
        self._vm_presets = {p["id"]: p for p in ordered}
        current = self.vm_model.currentData() or self.store.get("vm_model", wanconfigs.FASTWAN_ID)
        scene_current = self.vm_scene_model.currentData() or current
        self._vm_loading_model = True
        self._vm_fill_model_combo(self.vm_model, current)
        self._vm_fill_model_combo(self.vm_scene_model, scene_current)
        self._vm_model_id = self.vm_model.currentData() or ""
        self._vm_scene_model_id = self.vm_scene_model.currentData() or ""
        preset = self._vm_preset(self._vm_model_id)
        if preset:
            chosen = self.vm_resolution.currentData() or self.store.get("vm_resolution") or preset["resolution"]
            self._vm_set_resolution(self.vm_resolution, preset, chosen)
            self._vm_fill_lora(self.vm_lora, preset, self.store.get("vm_lora", ""))
        self._vm_show_model_status()
        self._vm_loading_model = False

    def _vm_set_resolution(self, combo, preset, selected):
        choices = wanconfigs.resolution_choices(preset, self.vm_wan_dir.text().strip() if hasattr(self, "vm_wan_dir") else "")
        selected = wanconfigs.match_resolution(selected, choices) or (choices[0] if choices else "")
        combo.blockSignals(True)
        combo.clear()
        for value in choices:
            width, height = [int(part) for part in value.split("x")]
            kind = "portrait" if height > width else ("square" if width == height else "landscape")
            combo.addItem(f"{width}×{height} ({kind})", value)
        idx = combo.findData(selected)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _vm_fill_lora(self, combo, preset, current):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(tr("None"), "")
        for item in (preset or {}).get("creative_loras") or []:
            combo.addItem(item["name"] + " · " + item["status"], item["path"])
        if current and combo.findData(current) < 0:
            combo.addItem(os.path.basename(current), current)
        idx = combo.findData(current or "")
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _vm_animation_from_widgets(self):
        preset = self._vm_preset(self.vm_model.currentData())
        return {
            "model_id": self.vm_model.currentData() or wanconfigs.FASTWAN_ID,
            "resolution": self.vm_resolution.currentData() or (preset or {}).get("resolution") or "1280x704",
            "frames": int(self.vm_frames.value()),
            "steps": int(self.vm_steps.value()),
            "guidance": float(self.vm_guidance.value()),
            "flow_shift": float(self.vm_flow.value()),
            "creative_lora": self.vm_lora.currentData() or "",
            "creative_strength": float(self.vm_lora_strength.value()),
        }

    def _vm_scene_animation(self):
        preset = self._vm_preset(self.vm_scene_model.currentData())
        base = preset or wanconfigs.default_animation()
        return {
            "model_id": self.vm_scene_model.currentData() or wanconfigs.FASTWAN_ID,
            "resolution": str(getattr(self, "_vm_scene_resolution", "") or base.get("resolution") or "1280x704"),
            "frames": int(self.vm_scene_frames.value()),
            "steps": int(self.vm_scene_steps.value()),
            "guidance": float(self.vm_scene_guidance.value()),
            "flow_shift": getattr(self, "_vm_scene_flow", base.get("flow_shift", 3)),
            "creative_lora": self.vm_scene_lora.currentData() or "",
            "creative_strength": float(self.vm_scene_strength.value()),
        }

    def _vm_apply_preset_values(self, preset, frames, steps, guidance, flow, resolution, lora, strength, keep_resolution=""):
        choices = wanconfigs.resolution_choices(preset, self.vm_wan_dir.text().strip())
        selected = wanconfigs.match_resolution(keep_resolution, choices) or preset.get("resolution")
        self._vm_set_resolution(resolution, preset, selected)
        frames.setValue(int(preset["frames"])); steps.setValue(int(preset["steps"]))
        guidance.setValue(float(preset["guidance"])); flow.setValue(float(preset["flow_shift"]))
        self._vm_fill_lora(lora, preset, "")
        strength.setValue(1.0)

    def _vm_apply_controls(self, anim, reset_note=False):
        """Load a saved animation into the project tools without treating it as a model switch."""
        self._vm_loading_model = True
        model_id = anim.get("model_id") or wanconfigs.FASTWAN_ID
        idx = self.vm_model.findData(model_id)
        if idx >= 0:
            self.vm_model.setCurrentIndex(idx)
        preset = self._vm_preset(self.vm_model.currentData())
        if preset:
            self._vm_set_resolution(self.vm_resolution, preset, anim.get("resolution") or preset["resolution"])
            self._vm_fill_lora(self.vm_lora, preset, anim.get("creative_lora") or "")
        self.vm_frames.setValue(int(anim.get("frames") or 121))
        self.vm_steps.setValue(int(anim.get("steps") or 3))
        self.vm_guidance.setValue(float(anim.get("guidance") if anim.get("guidance") is not None else 1))
        self.vm_flow.setValue(float(anim.get("flow_shift") if anim.get("flow_shift") is not None else 3))
        self.vm_lora_strength.setValue(float(anim.get("creative_strength") if anim.get("creative_strength") is not None else 1))
        self._vm_model_id = self.vm_model.currentData() or ""
        self._vm_loading_model = False
        if reset_note:
            self.vm_switch_note.clear(); self.vm_switch_note.setVisible(False)
        self._vm_show_model_status()

    def _vm_show_model_status(self):
        preset = self._vm_preset(self.vm_model.currentData())
        extra = wanconfigs.custom_notes(self._vm_animation_from_widgets(), preset)
        text = wanconfigs.status_line(preset)
        if extra:
            text += " · " + "; ".join(extra)
        if preset and preset.get("note"):
            text += " · " + preset["note"]
        self.vm_model_status.setText(text)
        self._vm_lora_changed()
        self._vm_update_frames_hint()

    def _vm_update_frames_hint(self):
        if not hasattr(self, "vm_frames_hint"):
            return
        preset = self._vm_preset(self.vm_model.currentData()) if hasattr(self, "vm_model") else None
        fps = wanconfigs.model_fps(preset)
        minimum, step = wanconfigs.frame_grid(preset)
        scenes = self.vm_proj.get("scenes") if hasattr(self, "vm_proj") else []
        self.vm_frames_hint.setText(wanconfigs.scene_frame_plan(scenes or [], fps, minimum, step))

    def _vm_frames_changed(self):
        self._vm_update_frames_hint()

    def _vm_model_changed(self):
        if self._vm_loading_model:
            return
        preset = self._vm_preset(self.vm_model.currentData())
        if not preset:
            return
        previous = self._vm_animation_from_widgets()
        previous["model_id"] = self._vm_model_id
        notes = wanconfigs.incompatible_changes(previous, preset)
        choices = wanconfigs.resolution_choices(preset, self.vm_wan_dir.text().strip())
        if wanconfigs.match_resolution(previous.get("resolution"), choices):
            notes = [note for note in notes if not note.startswith("resolution")]
        self._vm_loading_model = True
        self._vm_apply_preset_values(preset, self.vm_frames, self.vm_steps, self.vm_guidance, self.vm_flow,
                                     self.vm_resolution, self.vm_lora, self.vm_lora_strength,
                                     keep_resolution=previous.get("resolution"))
        self._vm_model_id = preset["id"]
        self._vm_loading_model = False
        if notes:
            self.vm_switch_note.setText("Switched to " + preset["name"] + ". Reset " + "; ".join(notes) + ".")
            self.vm_switch_note.setVisible(True)
        else:
            self.vm_switch_note.clear(); self.vm_switch_note.setVisible(False)
        self._vm_show_model_status()
        self._vm_frames_changed()
        if hasattr(self, "vm_proj"):
            self._vm_show_scene_animation(self.vm_proj["scenes"][self.vm_cur] if 0 <= self.vm_cur < len(self.vm_proj["scenes"]) else None)

    def _vm_lora_changed(self):
        if not hasattr(self, "vm_lora_note"):
            return
        path = self.vm_lora.currentData() or ""
        preset = self._vm_preset(self.vm_model.currentData()) or {}
        if not path:
            self.vm_lora_note.setText(tr("Creative LoRA is off. A required acceleration adapter, if this model has one, stays on."))
            return
        status = wanconfigs.lora_status(path, preset.get("architecture"), preset.get("required_loras"))
        if status == "required":
            self.vm_lora_note.setText(tr("That file is an acceleration adapter. Choose None to keep it on without adding a creative LoRA."))
        elif status == "incompatible":
            self.vm_lora_note.setText(tr("This file's metadata does not match the selected model. Animate will stop before starting Wan2GP."))
        elif status == "compatible":
            self.vm_lora_note.setText(tr("Metadata matches this model family. Strength is constant; there is no guaranteed range."))
        elif status == "missing":
            self.vm_lora_note.setText(tr("That creative LoRA file is not on disk. Nothing will be downloaded."))
        else:
            self.vm_lora_note.setText(tr("Compatibility is not proven: the file has no architecture metadata, and its folder name is not evidence."))

    def vm_pick_lora(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Creative LoRA"), "", "LoRA (*.safetensors *.sft)")
        if not path:
            return
        if self.vm_lora.findData(path) < 0:
            self.vm_lora.addItem(os.path.basename(path), path)
        self.vm_lora.setCurrentIndex(self.vm_lora.findData(path))

    def _vm_override_toggled(self, on):
        self.vm_override_box.setVisible(bool(on))
        if on and not self._vm_loading_scene:
            self._vm_copy_project_to_scene()

    def _vm_copy_project_to_scene(self):
        anim = self._vm_animation_from_widgets()
        self._vm_load_scene_controls(anim, quiet=True)

    def _vm_load_scene_controls(self, anim, quiet=False):
        self._vm_loading_scene = True
        model_id = (anim or {}).get("model_id") or wanconfigs.FASTWAN_ID
        idx = self.vm_scene_model.findData(model_id)
        if idx >= 0:
            self.vm_scene_model.setCurrentIndex(idx)
        preset = self._vm_preset(self.vm_scene_model.currentData()) or {}
        self._vm_fill_lora(self.vm_scene_lora, preset, (anim or {}).get("creative_lora") or "")
        self._vm_scene_resolution = str((anim or {}).get("resolution") or preset.get("resolution") or "1280x704")
        self._vm_scene_flow = (anim or {}).get("flow_shift") if (anim or {}).get("flow_shift") is not None else preset.get("flow_shift", 3)
        self.vm_scene_frames.setValue(int((anim or {}).get("frames") or preset.get("frames") or 121))
        self.vm_scene_steps.setValue(int((anim or {}).get("steps") or preset.get("steps") or 3))
        self.vm_scene_guidance.setValue(float((anim or {}).get("guidance") if (anim or {}).get("guidance") is not None else preset.get("guidance") or 1))
        self.vm_scene_strength.setValue(float((anim or {}).get("creative_strength") if (anim or {}).get("creative_strength") is not None else 1))
        self._vm_scene_model_id = self.vm_scene_model.currentData() or ""
        self._vm_loading_scene = False
        if quiet:
            self.vm_scene_switch.clear(); self.vm_scene_switch.setVisible(False)

    def _vm_scene_model_changed(self):
        if self._vm_loading_scene or self._vm_loading_model:
            return
        preset = self._vm_preset(self.vm_scene_model.currentData())
        if not preset:
            return
        previous = self._vm_scene_animation()
        previous["model_id"] = self._vm_scene_model_id
        notes = wanconfigs.incompatible_changes(previous, preset)
        choices = wanconfigs.resolution_choices(preset, self.vm_wan_dir.text().strip())
        kept = wanconfigs.match_resolution(self.vm_resolution.currentData(), choices)
        if kept:
            notes = [note for note in notes if not note.startswith("resolution")]
        self._vm_loading_scene = True
        self._vm_scene_resolution = kept or wanconfigs.align_resolution(preset.get("resolution"), wanconfigs.block_size(preset))
        self._vm_scene_flow = preset["flow_shift"]
        self.vm_scene_frames.setValue(int(preset["frames"]))
        self.vm_scene_steps.setValue(int(preset["steps"]))
        self.vm_scene_guidance.setValue(float(preset["guidance"]))
        self._vm_fill_lora(self.vm_scene_lora, preset, "")
        self.vm_scene_strength.setValue(1.0)
        self._vm_scene_model_id = preset["id"]
        self._vm_loading_scene = False
        if notes:
            self.vm_scene_switch.setText("Switched to " + preset["name"] + ". Reset " + "; ".join(notes) + ".")
            self.vm_scene_switch.setVisible(True)
        else:
            self.vm_scene_switch.clear(); self.vm_scene_switch.setVisible(False)

    def _vm_show_scene_animation(self, scene):
        if not hasattr(self, "vm_anim_from"):
            return
        scene = scene or {}
        recorded = scene.get("resolved")
        if recorded:
            preset = self._vm_preset(recorded.get("model_id"))
            text = wanconfigs.describe(dict(recorded, _source="recorded"), preset)
        else:
            eff = vp.effective_animation(self.vm_proj, scene if scene.get("animation_override") else None)
            preset = self._vm_preset(eff.get("model_id"))
            text = wanconfigs.describe(eff, preset)
        self.vm_anim_from.setText(text)
        self._vm_loading_scene = True
        self.vm_override.setChecked(bool(scene.get("animation_override")))
        self._vm_loading_scene = False
        self.vm_override_box.setVisible(bool(scene.get("animation_override")))
        self._vm_load_scene_controls(scene.get("animation_override") or vp.effective_animation(self.vm_proj, None), quiet=True)

    def vm_use_current(self):
        if not 0 <= self.vm_cur < len(self.vm_proj["scenes"]):
            return False
        self.vm_proj["scenes"][self.vm_cur]["resolved"] = None
        self.vm_save(); self.vm_refresh()
        self.vm_status.setText(tr("This scene will use the current project or override settings on the next clip."))
        return True

    def vm_open_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        os.makedirs(self.vm_dir(), exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.vm_dir()))

    # ------------------------------------------------------------------ pipeline
    def _vm_busy(self):
        return bool(self._vm_worker and self._vm_worker.isRunning())

    def _vm_start(self, fn, done, name):
        if self._vm_busy():
            self.notify(tr("Video maker is still busy – press Cancel first"), error=True); return False
        self.vm_save()
        wk = VideoWorker(fn)
        wk.progress.connect(lambda pct, msg: (self.vm_bar.setValue(pct), self.vm_status.setText(tr(name) + " · " + msg)))
        wk.ok.connect(lambda r: (self._vm_after(), done(r)))
        wk.failed.connect(lambda e: (self._vm_after(), self._vm_chain.clear(), self.vm_status.setText("⚠️ " + e[:600])))
        self._vm_worker = wk; wk.start()
        return True

    def _vm_after(self):
        vp.save_project(self.vm_proj, self.vm_dir()); self.vm_refresh()

    def _vm_next(self):
        if self._vm_chain:
            self._vm_chain.pop(0)()

    def vm_cancel(self):
        self._vm_chain.clear()
        if self._vm_busy():
            self._vm_worker.cancel(); self.vm_status.setText(tr("Cancelling…"))

    def _vm_adetailer(self, backend):
        """6.1: ticked = the Settings ADetailer passes (face_yolov8s.pt if none are saved); unticked = none."""
        if self.vm_ad.isChecked() and isinstance(backend, imagegen.A1111):
            if not self.store.get("ad_model"):  # nothing saved in Settings yet: the 5.3 face pass
                return imagegen.AD_FACE
            return imagegen.adetailer_from_store(self.store, force=True)
        return None

    def vm_stills(self):
        todo = [s for s in self.vm_proj["scenes"] if not s.get("still") and s["prompt"].strip()]
        if not todo:
            self.vm_status.setText(tr("Every scene has a still")); self._vm_next(); return True
        jobs, backend, info, notes = [], None, None, []
        pdir = self.vm_dir()
        for s in todo:
            made = self.make_job(vp.scene_prompt(self.vm_proj, s), self._default_negative(), vp.scene_seed(self.vm_proj, s), "video")
            if not made:
                self.notify(tr("Set up Forge or ComfyUI in Settings first"), error=True); self._vm_chain.clear(); return False
            job, backend, wf = made
            job.workflow_obj = wf
            w, h = self._vm_still_size(job, s)
            job.width, job.height = w, h
            job.restore_settings = True
            job.adetailer = self._vm_adetailer(backend)
            if vp.main_character(self.vm_proj, s) and info is None:
                from . import faceswap as fs
                info = fs.detect(backend)
            note = self._vm_facelock(job, s, pdir, info) if info is not None else ""
            s["facelock"] = note
            if note:
                notes.append(f"{s['id']}: {note}")
            jobs.append((s, job))
        if notes:
            self.vm_facelock.setText("\n".join(notes[:6]))

        def gen_backend():
            return backend if isinstance(backend, imagegen.A1111) else _ComfyAdapter(backend)

        b = gen_backend()
        return self._vm_start(lambda prog, canc: vp.make_stills(self.vm_proj, pdir, jobs, b, prog, canc),
                              lambda n: (self.vm_status.setText(f"✓ {n} {tr('stills')}"), self._vm_next()), "Stills")

    def _vm_facelock(self, job, s, pdir, info):
        """Face Swap's generate mode (IP-Adapter Plus Face) with the main character's reference. Returns the note."""
        from . import faceswap as fs
        ref, note = vp.facelock_plan(self.vm_proj, s, pdir, info,
                                     vp.facelock_model_warning(getattr(self, "profile", None), getattr(job, "workflow", "")))
        if not ref:
            return note
        cache = getattr(self, "_vm_face_cache", {})
        self._vm_face_cache = cache
        key = (ref, os.path.getmtime(ref))
        if key not in cache:
            with open(ref, "rb") as f:
                src = f.read()
            try:
                cache[key] = fs.crop_face(src, None, cache_dir=self._fs_cache() if hasattr(self, "_fs_cache") else None)[0]
            except Exception:  # noqa: BLE001 – no face detector: the whole reference still works
                cache[key] = src
        model = info.get("model") or ""
        fs.apply_to_job(job, cache[key], model, fs.classify(model) or info.get("type") or "plus_face")
        return note

    def _vm_still_size(self, job, scene=None):
        """Same shape as that scene's animation resolution, about the profile's pixel count, multiple of 64."""
        anim = vp.effective_animation(self.vm_proj, scene)
        try:
            vw, vh = [int(x) for x in str(anim.get("resolution") or "1280x704").lower().split("x")]
        except ValueError:
            vw, vh = self.vm_proj.get("size") or vp.SIZE
        area = max(job.width * job.height, 1024 * 576)
        import math
        h = math.sqrt(area * vh / vw); w = h * vw / vh
        return int(round(w / 64) * 64), int(round(h / 64) * 64)

    # ------------------------------------------------------------------ characters
    def vm_facelock_model(self):
        """(model label, workflow) for the current target model / backend, as used for still generation."""
        p = getattr(self, "profile", None) or {}
        kind = self.store.get("img_backend", "none")
        wf = self.store.get("img_workflow", "") if kind == "comfyui" else "a1111"
        ckpt = self.store.get(f"img_checkpoint:{wf}", "") or ""
        name = p.get("name") or p.get("family") or "?"
        return (f"{name}{' · ' + os.path.basename(ckpt) if ckpt else ''}", "" if wf == "a1111" else wf)

    def vm_update_facelock_warning(self):
        """Amber warning, live: shown when a character has a reference face but the current model can't use it."""
        if not (hasattr(self, "vm_fl_warn") and hasattr(self, "vm_proj")):
            return ""
        has_ref = any(c.get("ref") for c in self.vm_proj.get("characters") or []) or bool(self.vm_ch_ref.text().strip())
        model, wf = self.vm_facelock_model()
        why = vp.facelock_model_warning(getattr(self, "profile", None), wf) if has_ref else ""
        text = (f"⚠️ {tr('Face lock is off')}: {tr('current model')} ({model}) {tr('isn’t SDXL / Illustrious / Pony.')} "
                f"{tr('Descriptions and seeds still apply.')}") if why else ""
        self.vm_fl_warn.setText(text); self.vm_fl_warn.setVisible(bool(text))
        return text

    def vm_char_refresh(self):
        self.vm_chars.blockSignals(True); self.vm_chars.clear()
        for c in self.vm_proj.get("characters") or []:
            self.vm_chars.addItem(c["name"] + (" ★" if c.get("main") else "") + (" 🖼" if c.get("ref") else ""))
        self.vm_chars.blockSignals(False)
        self.vm_ch_import.clear()
        try:
            for c in self.store.characters():
                self.vm_ch_import.addItem(c["name"], c["id"])
        except Exception:  # noqa: BLE001
            pass
        r = getattr(self, "vm_char_cur", -1)
        r = r if 0 <= r < self.vm_chars.count() else (0 if self.vm_chars.count() else -1)
        self.vm_chars.setCurrentRow(r); self.vm_char_select(r)
        self.vm_update_facelock_warning()

    def vm_char_select(self, r):
        self.vm_char_cur = r
        cs = self.vm_proj.get("characters") or []
        c = cs[r] if 0 <= r < len(cs) else vp.new_character()
        self.vm_ch_name.setText(c["name"] if 0 <= r < len(cs) else ""); self.vm_ch_desc.setPlainText(c.get("description", ""))
        self.vm_ch_ref.setText(c.get("ref", "")); self.vm_ch_seed.setValue(int(c.get("seed", -1))); self.vm_ch_main.setChecked(bool(c.get("main")))

    def vm_char_add(self, c=None):
        cs = self.vm_proj.setdefault("characters", [])
        c = c or vp.new_character(cs, main=not cs)
        cs.append(c); self.vm_char_cur = len(cs) - 1; self.vm_char_refresh()
        return c

    def vm_char_apply(self):
        cs = self.vm_proj.get("characters") or []
        r = self.vm_char_cur
        if not 0 <= r < len(cs):
            return False
        c = cs[r]
        old = (c["description"], c.get("ref"), c.get("seed"), c.get("main"))
        c.update(name=self.vm_ch_name.text().strip() or c["name"], description=self.vm_ch_desc.toPlainText().strip(),
                 seed=int(self.vm_ch_seed.value()), main=self.vm_ch_main.isChecked())
        ref = self.vm_ch_ref.text().strip()
        if ref != c.get("ref"):
            src = ref if os.path.isabs(ref) else os.path.join(self.vm_dir(), ref)
            vp.set_reference(c, self.vm_dir(), src if ref and os.path.isfile(src) else "")
        if c["main"]:
            for o in cs:
                if o is not c:
                    o["main"] = False
        if old != (c["description"], c.get("ref"), c.get("seed"), c.get("main")):  # its scenes need new stills
            for s in self.vm_proj["scenes"]:
                if c["id"] in (s.get("characters") or []):
                    vp.redo_scene(s, self.vm_dir(), "still")
        self.vm_save(); self.vm_char_refresh(); self.vm_refresh()
        return True

    def vm_char_del(self):
        cs = self.vm_proj.get("characters") or []
        r = self.vm_char_cur
        if 0 <= r < len(cs):
            cid = cs.pop(r)["id"]
            for s in self.vm_proj["scenes"]:
                s["characters"] = [x for x in s.get("characters") or [] if x != cid]
            self.vm_char_cur = min(r, len(cs) - 1); self.vm_char_refresh(); self.vm_refresh()

    def vm_char_pick_ref(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Reference face"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.vm_ch_ref.setText(path)

    def vm_char_import(self):
        cid = self.vm_ch_import.currentData()
        char = self.store.character(cid) if cid is not None else None
        if not char:
            self.notify(tr("Save a character in Characters first"), error=True); return None
        cs = self.vm_proj.setdefault("characters", [])
        c = vp.character_from_store(char, cs, getattr(self, "profile", None))
        c["main"] = not cs
        if c["ref"]:
            vp.set_reference(c, self.vm_dir(), c["ref"])
        self.vm_char_add(c); self.vm_save()
        return c

    def vm_animate(self):
        if not any(s.get("animate") and s.get("still") and not s.get("clip") for s in self.vm_proj["scenes"]):
            self.vm_status.setText(tr("No ticked scenes waiting for a clip (make stills first)")); self._vm_next(); return True
        wan = {"dir": self.vm_wan_dir.text().strip(), "python": self.vm_wan_py.text().strip()}
        b = self.image_backend()  # Forge: unload-checkpoint; ComfyUI: /free – either one must let go of the GPU
        forge = b if hasattr(b, "unload_checkpoint") else None
        pdir = self.vm_dir()
        return self._vm_start(lambda prog, canc: vp.animate(self.vm_proj, pdir, wan, forge, prog, canc),
                              lambda n: (self.vm_status.setText(f"✓ {n} {tr('clips')}"), self._vm_next()), "Animate")

    def vm_build(self):
        ff = self.vm_ffmpeg.text().strip() or vp.find_ffmpeg("", self.vm_wan_dir.text().strip())
        pdir = self.vm_dir()
        return self._vm_start(lambda prog, canc: vp.build(self.vm_proj, pdir, ff, prog, canc),
                              lambda out: (self.vm_status.setText("✓ " + str(out)), self.notify(tr("Video ready")), self._vm_next()),
                              "Build")

    def vm_run_all(self):
        self._vm_chain = [self.vm_animate, self.vm_build]
        return self.vm_stills()


class _ComfyAdapter:
    """ComfyUI.generate needs the workflow too; give it the same generate(job, progress, cancelled) shape as A1111."""
    def __init__(self, backend):
        self.b = backend

    def generate(self, job, progress=None, cancelled=None):
        return self.b.generate(job, getattr(job, "workflow_obj", None), progress=progress, cancelled=cancelled)
