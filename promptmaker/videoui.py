"""5.3 Video maker page (Tools → Video maker): idea / story (+ optional song & lyrics) -> AI scene plan -> stills
(Forge / ComfyUI) -> Wan2GP clips for ticked scenes, Ken Burns for the rest -> ffmpeg MP4."""
import os
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QProgressBar, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QWidget)

from . import imagegen, wan2gp
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
        self.vm_frames = QSpinBox(); self.vm_frames.setRange(17, 241); self.vm_frames.setSingleStep(4); self.vm_frames.setValue(int(self.store.get("vm_frames", vp.WAN_FRAMES)))
        self.vm_steps = QSpinBox(); self.vm_steps.setRange(1, 50); self.vm_steps.setValue(int(self.store.get("vm_steps", 3)))
        tc.add(hrow(label("Wan2GP folder"), self.vm_wan_dir)); tc.add(hrow(label("Wan2GP python"), self.vm_wan_py))
        tc.add(hrow(label("ffmpeg"), self.vm_ffmpeg)); tc.add(hrow(label("Frames"), self.vm_frames, label("Steps"), self.vm_steps, None))
        tc.add(hrow(button("⟳ Detect", self.vm_detect_tools, "ghost"), button("Save", self.vm_save_tools), None))
        tc.add(label("FastWan 5B image-to-video, 1280×704, 121 frames (~5 s), 3 steps: about 2 minutes per clip on 8 GB. "
                     "Forge's checkpoint is unloaded while Wan2GP runs and reloaded after.", "hint", wrap=True))
        rv = QSplitter(Qt.Vertical); rv.addWidget(rc); rv.addWidget(tc)
        split.addWidget(rv); split.setSizes([360, 560, 420])
        v.addWidget(split, 1)
        self.vm_proj = vp.new_project(self.vm_name.text()); self.vm_cur = -1; self._vm_worker = None; self._vm_chain = []
        self.vm_char_cur = -1
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
                 family=(getattr(self, "profile", None) or {}).get("family", ""))
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

    def _vm_item_changed(self, item):
        if item.column() == 4 and 0 <= item.row() < len(self.vm_proj["scenes"]):
            self.vm_proj["scenes"][item.row()]["animate"] = item.checkState() == Qt.Checked
            if item.row() == self.vm_cur:
                self.vm_anim.setChecked(self.vm_proj["scenes"][item.row()]["animate"])

    def vm_select(self, r):
        self.vm_cur = r
        ok = 0 <= r < len(self.vm_proj["scenes"])
        s = self.vm_proj["scenes"][r] if ok else vp.new_scene()
        self.vm_prompt.setPlainText(s["prompt"]); self.vm_motion.setText(s.get("motion", "")); self.vm_caption.setText(s.get("caption", ""))
        self.vm_secs.setValue(float(s.get("duration") or 4)); self.vm_cam.setCurrentText(s.get("camera", vp.CAMERAS[0]))
        self.vm_anim.setChecked(bool(s.get("animate")))
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
        s.update(prompt=new_prompt, motion=self.vm_motion.text().strip(), caption=self.vm_caption.text().strip(),
                 duration=float(self.vm_secs.value()), camera=self.vm_cam.currentText(), animate=self.vm_anim.isChecked())
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
        self.vm_status.setText(f"Wan2GP: {wd or tr('not found')} · ffmpeg: {self.vm_ffmpeg.text() or tr('not found')}")

    def vm_save_tools(self):
        for k, wdg in (("vm_wan_dir", self.vm_wan_dir), ("vm_wan_python", self.vm_wan_py), ("vm_ffmpeg", self.vm_ffmpeg)):
            self.store.set(k, wdg.text().strip())
        self.store.set("vm_frames", self.vm_frames.value()); self.store.set("vm_steps", self.vm_steps.value())
        self.notify(tr("Saved"))

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
            w, h = self._vm_still_size(job)
            job.width, job.height = w, h
            job.restore_settings = True
            if self.vm_ad.isChecked() and isinstance(backend, imagegen.A1111):
                job.adetailer = "face_yolov8s.pt"
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

    def _vm_still_size(self, job):
        """Same shape as the video (16:9-ish), about the profile's pixel count, multiple of 64."""
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
        wan = {"dir": self.vm_wan_dir.text().strip(), "python": self.vm_wan_py.text().strip(),
               "frames": self.vm_frames.value(), "steps": self.vm_steps.value()}
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
