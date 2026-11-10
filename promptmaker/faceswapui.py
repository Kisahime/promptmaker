"""5.1 Face Swap page (Tools): Fooocus-style face IP-Adapter, with a face + hair crop and an automatic face + hair mask."""
import os

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit, QSpinBox,
                               QSplitter, QStackedWidget, QWidget)

from . import characters as ch
from . import faceblend as fb
from . import faceswap as fs
from .i18n import tr
from .inpaintcanvas import InpaintCanvas
from .widgets import CallWorker, Card, ChatWorker, FlowLayout, button, hrow, label


def _show(lbl, png, n=None):
    pm = QPixmap(); pm.loadFromData(png or b"")
    if pm.isNull():
        return
    w = n or max(200, lbl.width() - 8); h = n or max(200, lbl.height() - 8)
    lbl.setPixmap(pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def fb_ok():
    return fs.cv2_available()


class _Progress(QObject):
    """Thread-safe progress text (model downloads run in a worker thread)."""
    text = Signal(str)

    def __call__(self, label, done, total):
        self.text.emit(f"⬇ {label}: {done / 1e6:.0f} / {total / 1e6:.0f} MB")


class FaceSwapPage:
    def _faceswap_page(self):
        from .app import page
        w, v = page("Face Swap", "Put a face – and its hair – on a new image or into an existing one. Works like Fooocus' "
                                 "FaceSwap: the IP-Adapter Plus Face model, stop at 0.9, weight 0.75. SDXL / Illustrious "
                                 "checkpoints only (not Anima).")
        split = QSplitter(Qt.Horizontal)
        # ---------------------------------------------------------- source face
        sc = Card("Source face")
        self.fs_char = QComboBox(); self.fs_char.setToolTip(tr("Use a saved character's first reference image as the face"))
        self.fs_char.activated.connect(lambda _i: self.fs_from_character())
        sc.add(hrow(label("Character"), self.fs_char, button("⟳", self.fs_load_characters, "ghost", "Reload characters")))
        sc.add(hrow(button("📂 Open face…", self.fs_open_source, "ghost"), button("🗂 Last image", self.fs_source_last, "ghost"), None))
        self.fs_margin = QDoubleSpinBox(); self.fs_margin.setRange(1.3, 3.5); self.fs_margin.setSingleStep(0.1)
        self.fs_margin.setValue(float(self.store.get("fs_margin", fs.HAIR_MARGIN)))
        self.fs_margin.setToolTip(tr("How much around the face is sent: 1.6 ≈ Fooocus (face only), 2.2 = face + hair, 3 = head and shoulders"))
        self.fs_margin.valueChanged.connect(lambda x: (self.store.set("fs_margin", float(x)), self.fs_recrop()))
        sc.add(hrow(label("Hair margin"), self.fs_margin, None))
        self.fs_nobg = QCheckBox(tr("Remove background")); self.fs_nobg.setChecked(bool(self.store.get("fs_nobg", False)))
        self.fs_nobg.setToolTip(tr("Paint everything except the head (face, hair, neck) plain grey before it is sent, so the background and clothes don't leak into the swap"))
        self.fs_nobg.toggled.connect(lambda on: (self.store.set("fs_nobg", bool(on)), self.fs_recrop()))
        sc.add(self.fs_nobg)
        self.fs_crop_view = QLabel(tr("Pick a clear picture of the face")); self.fs_crop_view.setAlignment(Qt.AlignCenter)
        self.fs_crop_view.setMinimumSize(220, 220); self.fs_crop_view.setObjectName("dropZone")
        sc.add(self.fs_crop_view, 1)
        self.fs_src_status = label("", "hint", wrap=True); sc.add(self.fs_src_status)
        split.addWidget(sc)
        # ---------------------------------------------------------- target
        tc = Card("Target")
        self.fs_mode = QComboBox()
        self.fs_mode.addItem(tr("Generate a new image with this face"), "generate")
        self.fs_mode.addItem(tr("Swap into an existing image"), "swap")
        self.fs_mode.currentIndexChanged.connect(self._fs_mode_changed)
        tc.add(hrow(label("Mode"), self.fs_mode, None))
        self.fs_target_stack = QStackedWidget()
        gen = QWidget(); gl = FlowLayout(gen, spacing=6)
        gl.addWidget(label("A new image from the prompt on the right, wearing the source face and hair.", "hint", wrap=True))
        self.fs_target_stack.addWidget(gen)
        sw = QWidget()
        from PySide6.QtWidgets import QVBoxLayout
        sl = QVBoxLayout(sw); sl.setContentsMargins(0, 0, 0, 0)
        self.fs_canvas = InpaintCanvas(); self.fs_canvas.file_dropped.connect(self.fs_open_target)
        row = QWidget(); fl = FlowLayout(row, spacing=6)
        self.fs_grow = QSpinBox(); self.fs_grow.setRange(-40, 120); self.fs_grow.setSuffix(" px"); self.fs_grow.setValue(int(self.store.get("fs_grow", 16)))
        self.fs_feather = QSpinBox(); self.fs_feather.setRange(0, 80); self.fs_feather.setSuffix(" px"); self.fs_feather.setValue(int(self.store.get("fs_feather", 12)))
        self.fs_style = QComboBox(); self.fs_style.addItems(["Auto", "Photo", "Anime"])
        self.fs_style.setCurrentText(self.store.get("fs_style", "Auto"))
        self.fs_style.setToolTip(tr("Photo: face-parsing model · Anime: anime character cut-out + hair colour · Auto: decided by which face detector finds the face"))
        self.fs_hair = QCheckBox(tr("Include hair")); self.fs_hair.setChecked(bool(self.store.get("fs_hair_on", True)))
        self.fs_neck = QCheckBox(tr("Include neck")); self.fs_neck.setChecked(bool(self.store.get("fs_neck", False)))
        for wdg, key in ((self.fs_grow, "fs_grow"), (self.fs_feather, "fs_feather")):
            wdg.valueChanged.connect(lambda n, k=key: (self.store.set(k, int(n)), self.fs_remask()))
        self.fs_hair.toggled.connect(lambda on: (self.store.set("fs_hair_on", bool(on)), self.fs_remask()))
        self.fs_neck.toggled.connect(lambda on: (self.store.set("fs_neck", bool(on)), self.fs_remask()))
        self.fs_style.currentTextChanged.connect(lambda t: (self.store.set("fs_style", t), self.fs_automask()))
        self.fs_pick_btn = button("👆 Pick face", self.fs_pick_mode, "ghost", "Click a numbered face on the image to mask that person")
        for x in (button("📂 Open image…", self.fs_open_target, "ghost"), button("🗂 Last image", self.fs_target_last, "ghost"),
                  button("🎭 Auto-mask face + hair", self.fs_automask, "primary"), self.fs_pick_btn, label("Style"), self.fs_style,
                  self.fs_hair, self.fs_neck, label("Grow"), self.fs_grow, label("Feather"), self.fs_feather):
            fl.addWidget(x)
        row2 = QWidget(); fl2 = FlowLayout(row2, spacing=6)
        self.fs_brush = QSpinBox(); self.fs_brush.setRange(4, 300); self.fs_brush.setValue(48); self.fs_brush.setSuffix(" px")
        self.fs_brush.valueChanged.connect(lambda n: setattr(self.fs_canvas, "brush", n))
        self.fs_erase = QCheckBox(tr("Eraser")); self.fs_erase.toggled.connect(lambda on: setattr(self.fs_canvas, "mode", "erase" if on else "brush"))
        self.fs_canvas.face_clicked.connect(self.fs_pick_at)
        for x in (label("Fix mask: brush"), self.fs_brush, self.fs_erase, button("Clear", self.fs_canvas.clear_mask, "ghost"),
                  button("Invert", self.fs_canvas.invert_mask, "ghost")):
            fl2.addWidget(x)
        sl.addWidget(row); sl.addWidget(row2); sl.addWidget(self.fs_canvas, 1)
        self.fs_target_stack.addWidget(sw)
        tc.add(self.fs_target_stack, 1)
        self.fs_mask_status = label("", "hint", wrap=True); tc.add(self.fs_mask_status)
        split.addWidget(tc)
        # ---------------------------------------------------------- settings + result
        rc = Card("Swap")
        self.fs_prompt = QLineEdit(); self.fs_prompt.setPlaceholderText(tr("Scene / what to keep, e.g. adult woman, smiling, park, watercolor"))
        rc.add(self.fs_prompt)
        self.fs_model = QComboBox(); self.fs_model.setMinimumWidth(200)
        rc.add(hrow(label("Face model"), self.fs_model, button("⟳ Check models", self.fs_check, "ghost")))
        self.fs_weight = QDoubleSpinBox(); self.fs_weight.setRange(0.1, 1.5); self.fs_weight.setSingleStep(0.05); self.fs_weight.setValue(fs.WEIGHT)
        self.fs_stop = QDoubleSpinBox(); self.fs_stop.setRange(0.1, 1.0); self.fs_stop.setSingleStep(0.05); self.fs_stop.setValue(fs.STOP_AT)
        self.fs_denoise = QDoubleSpinBox(); self.fs_denoise.setRange(0.3, 1.0); self.fs_denoise.setSingleStep(0.05); self.fs_denoise.setValue(fs.DENOISE)
        self.fs_denoise.setToolTip(tr("Swap mode: how much of the masked head is redrawn"))
        rc.add(hrow(label("Weight"), self.fs_weight, label("Stop at"), self.fs_stop, label("Denoise"), self.fs_denoise))
        rc.add(self._fs_blend_box())
        rc.add(hrow(button("↺ Fooocus defaults", self.fs_defaults, "ghost"), None, button("🎭 Swap face", self.fs_generate, "primary")))
        self.fs_status = label(tr("Press ⟳ Check models to see if Forge / ComfyUI is ready"), "hint", wrap=True)
        self.fs_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rc.add(self.fs_status)
        self.fs_result = QLabel(tr("The result appears here")); self.fs_result.setAlignment(Qt.AlignCenter)
        self.fs_result.setMinimumSize(300, 300); self.fs_result.setObjectName("dropZone")
        rc.add(self.fs_result, 1)
        self.fs_before = QCheckBox(tr("Show before")); self.fs_before.setEnabled(False)
        self.fs_before.setToolTip(tr("Compare the blended result with the original target"))
        self.fs_before.toggled.connect(lambda _on: self._fs_show_result())
        rc.add(hrow(button("💾 Save to Gallery", self.fs_save, "ghost"), button("↪ Use as target", self.fs_result_to_target, "ghost",
                                                                         "Swap again into the result"), self.fs_before, None))
        split.addWidget(rc); split.setSizes([300, 560, 420])
        v.addWidget(split, 1)
        self.fs_src_png = self.fs_face_png = self.fs_png = self.fs_job = None
        self.fs_face_box = None; self.fs_target_face = None; self._fs_worker = None; self._fs_info = None
        self.fs_faces = []; self.fs_face_idx = None; self.fs_target_style = "Auto"; self._fs_raw = None; self._fs_seg = None
        self._fs_seg_pending = False; self.fs_mask_method = ""
        self.fs_before_png = None; self._fs_swap_ctx = None; self._fs_blend_worker = None
        self._fs_mode_changed()
        self._fs_progress = _Progress(); self._fs_progress.text.connect(lambda t: self.fs_mask_status.setText(t))
        self.fs_load_characters()
        return w

    # ---------------------------------------------------------- helpers
    def _fs_cache(self):
        return os.path.join(getattr(self, "data_dir", "") or "", "models")

    def _fs_read(self, path_or_png):
        from .regions import _png, _qimage
        if isinstance(path_or_png, (bytes, bytearray)):
            return _png(_qimage(bytes(path_or_png)))
        with open(path_or_png, "rb") as f:
            return _png(_qimage(f.read()))

    def _fs_mode_changed(self, _i=None):
        self.fs_target_stack.setCurrentIndex(0 if self.fs_mode.currentData() == "generate" else 1)
        if hasattr(self, "fs_blend_box"):
            self.fs_blend_box.setVisible(self.fs_mode.currentData() == "swap")

    # ---------------------------------------------------------- auto-blend
    def _fs_blend_box(self):
        from PySide6.QtWidgets import QGroupBox, QVBoxLayout
        st, d = self.store, fb.DEFAULTS
        box = QGroupBox(tr("Auto-blend")); box.setCheckable(True); box.setChecked(bool(st.get("fs_bl_on", d["on"])))
        box.setToolTip(tr("Blend the new face into the original image: lighting, skin tone, grain and edges. "
                          "Only the masked area changes and the image keeps its original size."))
        box.toggled.connect(lambda on: st.set("fs_bl_on", bool(on)))
        lay = QVBoxLayout(box); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(4)

        def chk(key, text, tip):
            c = QCheckBox(tr(text)); c.setChecked(bool(st.get("fs_bl_" + key, d[key]))); c.setToolTip(tr(tip))
            c.toggled.connect(lambda on, k=key: st.set("fs_bl_" + k, bool(on))); return c

        def spin(key, lo, hi, tip):
            sp = QDoubleSpinBox(); sp.setRange(lo, hi); sp.setSingleStep(0.05); sp.setValue(float(st.get("fs_bl_" + key, d[key])))
            sp.setToolTip(tr(tip)); sp.valueChanged.connect(lambda x, k=key: st.set("fs_bl_" + k, float(x))); return sp
        self.fs_bl_harm = chk("harmonise", "Harmonise pass", "A second, light redraw (no face model) over the face and a "
                              "ring around it, so lighting and grain match the scene. Costs one extra generation.")
        self.fs_bl_harm_dn = spin("harmonise_denoise", 0.05, 0.6, "Harmonise denoise (0.25 = light touch). "
                                  "Costs one extra generation.")
        self.fs_bl_colour = chk("colour", "Colour match", "Shift the new face's skin tone and brightness to the original "
                                "skin's colour (LAB mean / spread)")
        self.fs_bl_colour_s = spin("colour_strength", 0.0, 1.0, "How strongly to match the original skin colour")
        self.fs_bl_grain = chk("grain", "Grain / sharpness match", "Add the original photo's noise and softness (or "
                               "sharpen) so the face isn't cleaner than the rest")
        self.fs_bl_grain_s = spin("grain_strength", 0.0, 1.0, "How much of the measured grain / blur difference to apply")
        self.fs_bl_seam = chk("seam", "Seam blend", "Blend the edge into the original at full resolution so there's no "
                              "visible line; everything outside the mask stays exactly as it was")
        self.fs_bl_seam_mode = QComboBox(); self.fs_bl_seam_mode.addItems(["Laplacian", "Poisson", "Poisson (mixed)"])
        self.fs_bl_seam_mode.setCurrentText(st.get("fs_bl_seam_mode", d["seam_mode"]))
        self.fs_bl_seam_mode.setToolTip(tr("Laplacian: soft multi-band blend (safe) · Poisson: matches the edge colours (can "
                                           "shift the face's tone) · mixed: keeps the stronger texture"))
        self.fs_bl_seam_mode.currentTextChanged.connect(lambda t: st.set("fs_bl_seam_mode", t))
        lay.addLayout(hrow(self.fs_bl_harm, label("Denoise"), self.fs_bl_harm_dn, None))
        lay.addLayout(hrow(self.fs_bl_colour, label("Strength"), self.fs_bl_colour_s, None))
        lay.addLayout(hrow(self.fs_bl_grain, label("Strength"), self.fs_bl_grain_s, None))
        lay.addLayout(hrow(self.fs_bl_seam, self.fs_bl_seam_mode, None))
        self.fs_blend_box = box
        return box

    def fs_blend_opts(self):
        return {"on": self.fs_blend_box.isChecked(), "colour": self.fs_bl_colour.isChecked(),
                "colour_strength": self.fs_bl_colour_s.value(), "seam": self.fs_bl_seam.isChecked(),
                "seam_mode": self.fs_bl_seam_mode.currentText(), "harmonise": self.fs_bl_harm.isChecked(),
                "harmonise_denoise": self.fs_bl_harm_dn.value(), "grain": self.fs_bl_grain.isChecked(),
                "grain_strength": self.fs_bl_grain_s.value()}

    def _fs_show_result(self):
        png = self.fs_before_png if (self.fs_before.isChecked() and self.fs_before_png) else self.fs_png
        if png:
            _show(self.fs_result, png)

    def fs_defaults(self):
        self.fs_weight.setValue(fs.WEIGHT); self.fs_stop.setValue(fs.STOP_AT); self.fs_denoise.setValue(fs.DENOISE)
        self.fs_margin.setValue(fs.HAIR_MARGIN)

    def fs_load_characters(self):
        self.fs_char.blockSignals(True); self.fs_char.clear(); self.fs_char.addItem(tr("— none —"), None)
        try:
            for c in self.store.characters():
                if ch.references(c):
                    self.fs_char.addItem(c["name"], c["id"])
        except Exception:
            pass
        self.fs_char.blockSignals(False)

    # ---------------------------------------------------------- source
    def fs_set_source(self, path_or_png, note=""):
        try:
            self.fs_src_png = self._fs_read(path_or_png)
        except (OSError, ValueError) as e:
            self.fs_src_status.setText("⚠️ " + str(e)); return None
        faces = fs.detect_faces(self.fs_src_png, self._fs_cache())
        self.fs_face_box = faces[0] if faces else None
        if self.fs_face_box is None and self.vision_ok():
            self._fs_vision_box(self.fs_src_png, "source")
        self.fs_recrop(note)
        return self.fs_face_png

    def vision_ok(self):
        try:
            return bool(self.vision_for()[0]) and hasattr(self, "provider")
        except Exception:
            return False

    def fs_recrop(self, note=""):
        if not self.fs_src_png:
            return None
        png, bg_note = None, ""
        if getattr(self, "fs_nobg", None) is not None and self.fs_nobg.isChecked():
            png, bg_note = self._fs_clean_face()
        if png is None:
            png, _box = fs.crop_face(self.fs_src_png, self.fs_face_box, self.fs_margin.value(), 512, self._fs_cache())
        self.fs_face_png = png
        _show(self.fs_crop_view, self.fs_face_png, 220)
        found = tr("Face found") if self.fs_face_box else tr("No face found — using the centre; pick a closer picture if it looks wrong")
        self.fs_src_status.setText(" · ".join(x for x in (note, found, bg_note, tr("this square (face + hair) is what the AI sees")) if x))
        return self.fs_face_png

    def _fs_clean_face(self):
        """(cut-out head PNG or None, status note) — cached per source + face + style."""
        key = (hash(self.fs_src_png), tuple(self.fs_face_box) if self.fs_face_box else None, self.fs_style.currentText())
        cache = self.__dict__.setdefault("_fs_bg_cache", {})
        if key not in cache:
            cache.clear()
            try:
                cache[key] = fs.clean_face(self.fs_src_png, self.fs_face_box, self.fs_style.currentText(), self._fs_cache())
            except Exception as e:  # noqa: BLE001
                cache[key] = (None, str(e))
        png, method = cache[key]
        if png is None:
            return None, tr("Background kept ({reason})").format(reason=method)
        return png, tr("Background removed")

    def fs_open_source(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Source face"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        return self.fs_set_source(p) if p else None

    def fs_source_last(self):
        it = self.gallery.items()
        return self.fs_set_source(it[0][0], tr("Last gallery image")) if it else None

    def fs_from_character(self, cid=None):
        cid = cid if cid is not None else self.fs_char.currentData()
        if not cid:
            return None
        c = self.store.character(cid)
        refs = ch.references(c) if c else []
        if not refs:
            self.fs_src_status.setText(tr("This character has no reference image yet")); return None
        if not self.fs_prompt.text().strip():
            self.fs_prompt.setText(ch.character_text(c, None, self.profile, with_lora=True))
        return self.fs_set_source(refs[0], c["name"])

    # ---------------------------------------------------------- target + mask
    def fs_set_target(self, path_or_png):
        try:
            self.fs_canvas.set_image(self._fs_read(path_or_png))
        except (OSError, ValueError) as e:
            self.fs_mask_status.setText("⚠️ " + str(e)); return False
        self.fs_target_face = None; self.fs_faces = []; self.fs_face_idx = None; self._fs_raw = None
        self.fs_canvas.faces = []; self.fs_canvas.face_sel = -1
        self.fs_mode.setCurrentIndex(1)
        self.fs_automask()
        return True

    def fs_open_target(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("Target image"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        return self.fs_set_target(path) if path else False

    def fs_target_last(self):
        it = self.gallery.items()
        return self.fs_set_target(it[0][0]) if it else False

    def _fs_opts(self):
        return (self.fs_target_style, bool(self.fs_hair.isChecked()), bool(self.fs_neck.isChecked()), self.fs_face_idx,
                tuple(self.fs_target_face or ()))

    def _fs_busy(self):
        return self._fs_seg is not None and self._fs_seg.isRunning()

    def fs_automask(self):
        """Detect every face (in a worker – first use downloads the small detectors), then mask the largest."""
        png = self.fs_canvas.image_png()
        if not png:
            self.fs_mask_status.setText(tr("Open the image to swap into first")); return None
        if self._fs_busy():
            self._fs_seg_pending = True; return None
        self.fs_mask_status.setText(tr("Finding faces…"))
        style, cache, prog = self.fs_style.currentText(), self._fs_cache(), self._fs_progress

        def work():
            faces, st = fs.detect_all(png, cache, style, prog)
            return (faces or fs.cascade_faces(png, cache)), st
        self._fs_seg = wk = CallWorker(work)
        wk.ok.connect(lambda r, png=png: self._fs_faces_found(png, *r))
        wk.failed.connect(lambda e: self.fs_mask_status.setText("⚠️ " + e[:160]))
        wk.finished.connect(self._fs_seg_finished)
        wk.start()
        return wk

    def _fs_seg_finished(self):
        if self._fs_seg_pending:
            self._fs_seg_pending = False; self.fs_remask()

    def _fs_faces_found(self, png, faces, style):
        if png != self.fs_canvas.image_png():
            return
        self.fs_faces = list(faces); self.fs_target_style = style if style in ("Photo", "Anime") else "Photo"
        self.fs_canvas.faces = self.fs_faces
        if not faces:
            self.fs_target_face = None; self.fs_face_idx = None; self.fs_canvas.face_sel = -1; self.fs_canvas.update()
            if self.vision_ok():
                self.fs_mask_status.setText(tr("No face found by the quick detector – asking the vision model…"))
                self._fs_vision_box(png, "target")
            else:
                self.fs_mask_status.setText(tr("No face found – paint over the face and hair with the brush"))
            return
        self.fs_select_face(0)

    def fs_select_face(self, i):
        if not (0 <= i < len(self.fs_faces)):
            return None
        self.fs_face_idx = i; self.fs_target_face = self.fs_faces[i]; self._fs_raw = None
        self.fs_canvas.face_sel = i; self.fs_canvas.update()
        return self.fs_remask()

    def fs_pick_mode(self):
        if len(self.fs_faces) < 1:
            self.fs_mask_status.setText(tr("No faces found to pick from – paint the mask with the brush")); return
        self.fs_canvas.mode = "pick"
        self.fs_mask_status.setText(tr("Click the face to swap (numbered boxes)"))

    def fs_pick_at(self, x, y):
        from . import faceseg
        self.fs_canvas.mode = "erase" if self.fs_erase.isChecked() else "brush"
        i = faceseg.face_at(self.fs_faces, x, y)
        return self.fs_select_face(i) if i is not None else None

    def fs_remask(self):
        """(Re)build the mask for the chosen face. Grow / feather changes reuse the cached segmentation instantly;
        new faces / hair / neck options segment again in a worker (first use downloads the model)."""
        png = self.fs_canvas.image_png()
        if not png or self.fs_target_face is None:
            return None
        if not self.fs_faces or self.fs_face_idx is None:  # face box set directly (vision model / tests)
            self.fs_faces = [tuple(self.fs_target_face)]; self.fs_face_idx = 0
            self.fs_canvas.faces = self.fs_faces; self.fs_canvas.face_sel = 0
        opts = self._fs_opts()
        if self._fs_raw and self._fs_raw[0] == opts and self._fs_raw[1] == png:
            m = fs.finish_mask(self._fs_raw[2], self.fs_grow.value(), self.fs_feather.value())
            self._fs_apply_mask(m, self._fs_raw[3]); return m
        if self._fs_busy():
            self._fs_seg_pending = True; return None
        self.fs_mask_status.setText(tr("Masking face + hair…"))
        faces, idx, (style, hair, neck) = list(self.fs_faces), self.fs_face_idx, opts[:3]
        grow, feather, cache, prog = self.fs_grow.value(), self.fs_feather.value(), self._fs_cache(), self._fs_progress
        self._fs_seg = wk = CallWorker(lambda: fs.smart_mask(png, faces, idx, style, cache, hair, neck, grow, feather, prog))
        wk.ok.connect(lambda r, o=opts, png=png: self._fs_mask_done(o, png, *r))
        wk.failed.connect(lambda e: self.fs_mask_status.setText("⚠️ " + e[:160]))
        wk.finished.connect(self._fs_seg_finished)
        wk.start()
        return wk

    def _fs_mask_done(self, opts, png, mask, raw, method):
        if png != self.fs_canvas.image_png() or mask is None:
            return
        if opts != self._fs_opts():   # options changed while it ran – the pending remask redoes it
            self._fs_seg_pending = True; return
        self._fs_raw = (opts, png, raw, method) if raw else None
        if raw:  # grow / feather may have moved while it ran
            mask = fs.finish_mask(raw, self.fs_grow.value(), self.fs_feather.value())
        self._fs_apply_mask(mask, method)

    def _fs_apply_mask(self, m, method):
        self.fs_canvas.mask = fs.mask_to_alpha(m); self.fs_canvas.update(); self.fs_canvas.changed.emit()
        self.fs_mask_method = method
        n = len(self.fs_faces)
        who = (tr("face") + f" {self.fs_face_idx + 1}/{n} · " + tr("👆 Pick face to choose another") + " · ") if n > 1 else ""
        hint = "" if fs.cv2_available() else " " + tr("(install opencv-python-headless for hair-following edges)")
        if method.startswith("shape"):
            hint += " · " + tr("rough shape mask") + f" – {method[7:-1]}"
        self.fs_mask_status.setText(who + tr("Face + hair masked") + f" ({method.split(' (')[0]}) – " +
                                    tr("fix it with the brush if needed") + hint)
        return m

    def _fs_vision_box(self, png, which):
        model, _note = self.vision_for()
        wk = ChatWorker(self.provider, model, fs.vision_messages(png), 0.1, True)
        self._fs_vworker = wk

        def done(text, png=png, which=which):
            from .imagegen import png_size
            w, h = png_size(png)
            box = fs.parse_vision_box(text, w, h)
            if which == "source":
                self.fs_face_box = box; self.fs_recrop()
            else:
                self.fs_target_face = box
                if box:
                    self.fs_remask()
                else:
                    self.fs_mask_status.setText(tr("No face found – paint over the face and hair with the brush"))
        wk.done.connect(done)
        wk.failed.connect(lambda e: self.fs_mask_status.setText("⚠️ " + e[:120]))
        wk.start()

    # ---------------------------------------------------------- models
    def fs_check(self):
        info = fs.detect(self.image_backend())
        self._fs_info = info
        self.fs_model.clear(); self.fs_model.addItems(info["models"])
        if info["model"]:
            self.fs_model.setCurrentText(info["model"])
        warn = fs.family_warning(getattr(self, "profile", None))
        lines = []
        if info["model"] and not info["problem"]:
            lines.append("✓ " + tr("Ready") + f": {info['model']} ({info['kind']})")
        if info["problem"]:
            lines.append("✗ " + info["problem"])
            if info["kind"]:
                lines.append(fs.install_help(info["kind"]))
        if warn:
            lines.append("⚠️ " + warn)
        if info["kind"] == "forge":
            dev = fs.forge_device_warning(self._fs_forge_dir())
            if dev:
                lines.append("⚠️ " + dev)
        self.fs_status.setText("\n".join(lines))
        return info

    def _fs_forge_dir(self):
        try:
            from . import trainer
            return (self.store.get("forge_dir", "") or trainer.guess_forge_dir()) if hasattr(self, "store") else trainer.guess_forge_dir()
        except Exception:  # noqa: BLE001
            return ""

    # ---------------------------------------------------------- generate
    def fs_build_job(self):
        if not self.fs_face_png:
            raise ValueError(tr("Pick a source face first"))
        info = self._fs_info or self.fs_check()
        model = self.fs_model.currentText() or info.get("model", "")
        if info.get("kind") == "forge" and not model:
            raise ValueError(tr("No face IP-Adapter model in Forge – see the install steps above"))
        if info.get("kind") is None:
            raise ValueError(info.get("problem") or tr("Set up Forge or ComfyUI in Settings first"))
        warn = fs.family_warning(getattr(self, "profile", None))
        if warn:
            raise ValueError(warn)
        swap = self.fs_mode.currentData() == "swap"
        prompt = self.fs_prompt.text().strip() or ("face, hair, detailed" if swap else "portrait of an adult person, detailed")
        made = self.make_job(prompt, self._default_negative(), None, "faceswap")
        if not made:
            raise ValueError(tr("Set up Forge or ComfyUI in Settings first"))
        job, backend, wf = made
        tgt = mask = None
        if swap:
            tgt = self.fs_canvas.image_png()
            if not tgt or not self.fs_canvas.has_mask():
                raise ValueError(tr("Open a target image and mask the face + hair first"))
            mask = self.fs_canvas.mask_png()
        self._fs_swap_ctx = {"target": tgt, "mask": mask, "face": tuple(self.fs_target_face) if self.fs_target_face else None,
                             "prompt": prompt, "opts": self.fs_blend_opts()} if swap else None
        kind = fs.classify(model) or (info.get("type") or "plus_face")
        fs.apply_to_job(job, self.fs_face_png, model, kind, self.fs_weight.value(), self.fs_stop.value(), tgt, mask,
                        self.fs_denoise.value(), self.fs_feather.value())
        return job, backend, wf

    def fs_generate(self):
        if any(w is not None and w.isRunning() for w in (self._fs_worker, self._fs_blend_worker)):
            return None
        try:
            job, backend, wf = self.fs_build_job()
        except ValueError as e:
            self.fs_status.setText("⚠️ " + str(e)); return None
        self.fs_job = job
        self.fs_status.setText(tr("Swapping") + f" · {job.width}×{job.height} · {job.steps} " + tr("steps"))
        self._fs_worker = CallWorker(lambda: backend.generate(job, wf))
        self._fs_worker.ok.connect(lambda imgs, j=job: self._fs_done(j, imgs))
        self._fs_worker.failed.connect(lambda e: self.fs_status.setText("⚠️ " + e[:240]))
        self._fs_worker.start()
        return job

    def _fs_done(self, job, imgs):
        if not imgs:
            return
        ctx = self._fs_swap_ctx
        if ctx and ctx["opts"].get("on") and fb_ok():
            return self._fs_blend_start(job, imgs[0], ctx)
        self.fs_png = imgs[0]; self.fs_before_png = ctx["target"] if ctx else None
        self.fs_before.setEnabled(bool(self.fs_before_png)); self.fs_before.setChecked(False)
        _show(self.fs_result, imgs[0])
        self._fs_done_status(job)

    def _fs_blend_start(self, job, raw, ctx):
        """Swap done → (harmonise generation) → colour → grain → seam blend onto the original, in a worker."""
        o = ctx["opts"]
        self.fs_status.setText(tr("Blending…") if not o.get("harmonise") else tr("Harmonise pass (extra generation)…"))
        backend = wf = hjob = None
        if o.get("harmonise"):
            made = self.make_job(ctx["prompt"], self._default_negative(), job.seed, "faceswap")
            if made:
                hjob, backend, wf = made
                from .imagegen import png_size
                rw, rh = png_size(raw); tw, th = png_size(ctx["target"])
                face = fb.scale_box(ctx["face"], rw / tw, rh / th) if ctx["face"] else None
                fs.harmonise_job(hjob, raw, ctx["mask"], face, o.get("harmonise_denoise", 0.25))
                self.fs_harmonise_job = hjob

        def work():
            img = raw
            if hjob is not None:
                out = backend.generate(hjob, wf)
                img = out[0] if out else raw
            return fb.blend(img, ctx["target"], ctx["mask"], ctx["face"], o)
        self._fs_blend_worker = wk = CallWorker(work)
        wk.ok.connect(lambda png, j=job, c=ctx: self._fs_blend_done(j, png, c))
        wk.failed.connect(lambda e: self.fs_status.setText("⚠️ " + tr("Auto-blend failed: ") + e[:200]))
        wk.start()
        return wk

    def _fs_blend_done(self, job, png, ctx):
        self.fs_png = png; self.fs_before_png = ctx["target"]
        self.fs_before.setEnabled(True); self.fs_before.setChecked(False)
        _show(self.fs_result, png)
        self._fs_done_status(job, " · " + tr("blended"))

    def _fs_done_status(self, job, extra=""):
        note = ""
        if getattr(job, "controlnet_applied", None) is False:
            note = " · ⚠️ " + tr("Forge didn't record the IP-Adapter – is the ControlNet extension enabled?")
        if not note and getattr(self, "_fs_info", None) and self._fs_info.get("kind") == "forge" \
                and fs.forge_device_warning(self._fs_forge_dir()):
            note = " · ⚠️ " + tr("If the face was ignored and Forge's console shows 'same device … cuda:0 … cpu', see the fix under ⟳ Check models")
        self.fs_status.setText(tr("Done") + f" · seed {job.seed}" + extra + note)

    def fs_save(self):
        if not self.fs_png:
            self.notify(tr("Nothing to save yet"), error=True); return None
        meta = self.fs_job.meta() if self.fs_job else {}
        meta["source"] = "face swap"
        p = self.gallery.save(self.fs_png, meta); self.load_gallery()
        if hasattr(self, "film_refresh"):
            self.film_refresh()
        self.notify(tr("Saved to Gallery"))
        return p

    def fs_result_to_target(self):
        if self.fs_png:
            return self.fs_set_target(self.fs_png)
        return False
