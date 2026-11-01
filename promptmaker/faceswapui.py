"""5.1 Face Swap page (Tools): Fooocus-style face IP-Adapter, with a face + hair crop and an automatic face + hair mask."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit, QSpinBox,
                               QSplitter, QStackedWidget, QWidget)

from . import characters as ch
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
        self.fs_hair = QComboBox(); self.fs_hair.addItems(list(fs.HAIR_LENGTHS)); self.fs_hair.setCurrentText(self.store.get("fs_hair", "Medium"))
        self.fs_refine = QCheckBox(tr("Follow hair edges")); self.fs_refine.setChecked(bool(self.store.get("fs_refine", True)))
        self.fs_refine.setToolTip(tr("GrabCut refine – the mask hugs the real hair outline instead of a plain oval"))
        for wdg, key in ((self.fs_grow, "fs_grow"), (self.fs_feather, "fs_feather")):
            wdg.valueChanged.connect(lambda n, k=key: (self.store.set(k, int(n)), self.fs_remask()))
        self.fs_hair.currentTextChanged.connect(lambda t: (self.store.set("fs_hair", t), self.fs_remask()))
        self.fs_refine.toggled.connect(lambda on: (self.store.set("fs_refine", bool(on)), self.fs_remask()))
        for x in (button("📂 Open image…", self.fs_open_target, "ghost"), button("🗂 Last image", self.fs_target_last, "ghost"),
                  button("🎭 Auto-mask face + hair", self.fs_automask, "primary"), label("Hair"), self.fs_hair,
                  label("Grow"), self.fs_grow, label("Feather"), self.fs_feather, self.fs_refine):
            fl.addWidget(x)
        row2 = QWidget(); fl2 = FlowLayout(row2, spacing=6)
        self.fs_brush = QSpinBox(); self.fs_brush.setRange(4, 300); self.fs_brush.setValue(48); self.fs_brush.setSuffix(" px")
        self.fs_brush.valueChanged.connect(lambda n: setattr(self.fs_canvas, "brush", n))
        self.fs_erase = QCheckBox(tr("Eraser")); self.fs_erase.toggled.connect(lambda on: setattr(self.fs_canvas, "mode", "erase" if on else "brush"))
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
        rc.add(hrow(button("↺ Fooocus defaults", self.fs_defaults, "ghost"), None, button("🎭 Swap face", self.fs_generate, "primary")))
        self.fs_status = label(tr("Press ⟳ Check models to see if Forge / ComfyUI is ready"), "hint", wrap=True)
        self.fs_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rc.add(self.fs_status)
        self.fs_result = QLabel(tr("The result appears here")); self.fs_result.setAlignment(Qt.AlignCenter)
        self.fs_result.setMinimumSize(300, 300); self.fs_result.setObjectName("dropZone")
        rc.add(self.fs_result, 1)
        rc.add(hrow(button("💾 Save to Gallery", self.fs_save, "ghost"), button("↪ Use as target", self.fs_result_to_target, "ghost",
                                                                         "Swap again into the result"), None))
        split.addWidget(rc); split.setSizes([300, 560, 420])
        v.addWidget(split, 1)
        self.fs_src_png = self.fs_face_png = self.fs_png = self.fs_job = None
        self.fs_face_box = None; self.fs_target_face = None; self._fs_worker = None; self._fs_info = None
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
        self.fs_face_png, box = fs.crop_face(self.fs_src_png, self.fs_face_box, self.fs_margin.value(), 512, self._fs_cache())
        _show(self.fs_crop_view, self.fs_face_png, 220)
        found = tr("Face found") if self.fs_face_box else tr("No face found – using the centre; pick a closer picture if it looks wrong")
        self.fs_src_status.setText(" · ".join(x for x in (note, found, tr("this square (face + hair) is what the AI sees")) if x))
        return self.fs_face_png

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
        self.fs_target_face = None
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

    def fs_automask(self):
        png = self.fs_canvas.image_png()
        if not png:
            self.fs_mask_status.setText(tr("Open the image to swap into first")); return None
        if self.fs_target_face is None:
            faces = fs.detect_faces(png, self._fs_cache())
            self.fs_target_face = faces[0] if faces else None
        if self.fs_target_face is None:
            if self.vision_ok():
                self.fs_mask_status.setText(tr("No face found by the quick detector – asking the vision model…"))
                self._fs_vision_box(png, "target")
            else:
                self.fs_mask_status.setText(tr("No face found – paint over the face and hair with the brush"))
            return None
        return self.fs_remask()

    def fs_remask(self):
        png = self.fs_canvas.image_png()
        if not png or self.fs_target_face is None:
            return None
        m = fs.auto_mask(png, self.fs_target_face, self.fs_hair.currentText(), self.fs_grow.value(), self.fs_feather.value(),
                         self.fs_refine.isChecked())
        self.fs_canvas.mask = fs.mask_to_alpha(m); self.fs_canvas.update()
        hint = "" if fs.cv2_available() else " " + tr("(install opencv-python-headless for hair-following edges)")
        self.fs_mask_status.setText(tr("Face + hair masked – fix it with the brush if needed") + hint)
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
        self.fs_status.setText("\n".join(lines))
        return info

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
        kind = fs.classify(model) or (info.get("type") or "plus_face")
        fs.apply_to_job(job, self.fs_face_png, model, kind, self.fs_weight.value(), self.fs_stop.value(), tgt, mask,
                        self.fs_denoise.value(), self.fs_feather.value())
        return job, backend, wf

    def fs_generate(self):
        if self._fs_worker is not None and self._fs_worker.isRunning():
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
        self.fs_png = imgs[0]
        _show(self.fs_result, imgs[0])
        note = ""
        if getattr(job, "controlnet_applied", None) is False:
            note = " · ⚠️ " + tr("Forge didn't record the IP-Adapter – is the ControlNet extension enabled?")
        self.fs_status.setText(tr("Done") + f" · seed {job.seed}" + note)

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
