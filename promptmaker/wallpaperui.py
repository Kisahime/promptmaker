"""5.2 Wallpaper mode page (Tools): exact-size desktop / phone wallpapers from a ~1 MP base + hires fix."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QPlainTextEdit, QSpinBox, QSplitter, QWidget

from . import imagegen
from . import wallpaper as wp
from .i18n import tr
from .widgets import Card, CallWorker, button, hrow, label

SIDE_ITEMS = [("Off", ""), ("Subject on the right (icons left)", "right"), ("Subject on the left (icons right)", "left"),
              ("Subject in the centre", "center")]


class WallpaperPage:
    def _wallpaper_page(self):
        from .app import page
        w, v = page("Wallpaper", "Make a wallpaper at your exact screen size: the image is made at about 1 MP in the "
                                 "screen's shape, hires-fixed up, then upscaled / Lanczos-resized and centre-cropped.")
        split = QSplitter(Qt.Horizontal)
        sc = Card("Screen")
        self.wp_preset = QComboBox()
        for name, tw, th in wp.PRESETS:
            self.wp_preset.addItem(name, (tw, th))
        self.wp_preset.addItem(tr("Custom…"), None)
        self.wp_w = QSpinBox(); self.wp_w.setRange(256, 8192); self.wp_w.setValue(int(self.store.get("wp_w", 1920)))
        self.wp_h = QSpinBox(); self.wp_h.setRange(256, 8192); self.wp_h.setValue(int(self.store.get("wp_h", 1080)))
        i = self.wp_preset.findText(self.store.get("wp_preset", wp.PRESETS[0][0]))
        self.wp_preset.setCurrentIndex(max(0, i))
        self.wp_preset.currentIndexChanged.connect(self._wp_preset_changed)
        for s in (self.wp_w, self.wp_h):
            s.valueChanged.connect(lambda _n: self.wp_update_plan())
        sc.add(hrow(label("Target"), self.wp_preset, None))
        sc.add(hrow(label("Custom"), self.wp_w, label("×"), self.wp_h, None))
        self.wp_side = QComboBox()
        for text, side in SIDE_ITEMS:
            self.wp_side.addItem(tr(text), side)
        self.wp_side.setCurrentIndex(max(0, self.wp_side.findData(self.store.get("wp_side", "right"))))
        self.wp_side.setToolTip(tr("Icon-safe composition: adds wide-shot / empty-space wording in your model's prompt style"))
        self.wp_side.currentIndexChanged.connect(lambda _i: (self.store.set("wp_side", self.wp_side.currentData()), self.wp_update_plan()))
        sc.add(hrow(label("Composition"), self.wp_side, None))
        self.wp_denoise = QDoubleSpinBox(); self.wp_denoise.setRange(0.1, 0.8); self.wp_denoise.setSingleStep(0.05)
        self.wp_denoise.setValue(float(self.store.get("wp_denoise", 0.35)))
        self.wp_denoise.valueChanged.connect(lambda x: self.store.set("wp_denoise", float(x)))
        self.wp_final = QComboBox()
        self.wp_final.addItem(tr("Forge upscaler, then Lanczos"), "backend"); self.wp_final.addItem(tr("Lanczos resize only"), "lanczos")
        self.wp_final.setCurrentIndex(max(0, self.wp_final.findData(self.store.get("wp_final", "backend"))))
        self.wp_final.setToolTip(tr("Used when more than ×2 is needed (4K): Forge runs its hires-fix upscaler model "
                                    "(e.g. 4x-UltraSharp) on the result; ComfyUI and 'Lanczos only' resize locally"))
        self.wp_final.currentIndexChanged.connect(lambda _i: self.store.set("wp_final", self.wp_final.currentData()))
        sc.add(hrow(label("Hires denoise"), self.wp_denoise, label("Final step"), self.wp_final, None))
        self.wp_plan_view = label("", "hint", wrap=True); self.wp_plan_view.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sc.add(self.wp_plan_view)
        self.wp_save_folder = QCheckBox(tr("Also save to the Wallpapers folder"))
        self.wp_save_folder.setChecked(bool(self.store.get("wp_save_folder", True)))
        self.wp_save_folder.toggled.connect(lambda on: self.store.set("wp_save_folder", bool(on)))
        sc.add(self.wp_save_folder)
        sc.add(QWidget(), 1)
        split.addWidget(sc)
        pc = Card("Prompt")
        self.wp_prompt = QPlainTextEdit(); self.wp_prompt.setPlaceholderText(tr("Scene, e.g. adult woman in a camel coat on an autumn forest path, falling leaves, golden hour"))
        self.wp_prompt.setPlainText(self.store.get("wp_prompt", ""))
        self.wp_prompt.textChanged.connect(lambda: self.wp_update_plan())
        pc.add(hrow(button("↙ Use Refine prompt", self.wp_use_work, "ghost"), None))
        pc.add(self.wp_prompt, 1)
        pc.add(label("Sent to the model:", "muted"))
        self.wp_final_prompt = label("", "hint", wrap=True); self.wp_final_prompt.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pc.add(self.wp_final_prompt)
        pc.add(hrow(None, button("🖼 Make wallpaper", self.wp_generate, "primary")))
        self.wp_status = label("", "hint", wrap=True); pc.add(self.wp_status)
        split.addWidget(pc)
        rc = Card("Result")
        self.wp_result = QLabel(tr("The wallpaper appears here")); self.wp_result.setAlignment(Qt.AlignCenter)
        self.wp_result.setMinimumSize(360, 220); self.wp_result.setObjectName("dropZone")
        rc.add(self.wp_result, 1)
        self.wp_set_btn = button("🖥 Set as desktop wallpaper", self.wp_set_desktop, "ghost")
        self.wp_set_btn.setVisible(wp.can_set_desktop())
        rc.add(hrow(button("💾 Save to Gallery", self.wp_save_gallery, "ghost"),
                    button("📂 Wallpapers folder", self.wp_open_folder, "ghost"), self.wp_set_btn, None))
        split.addWidget(rc); split.setSizes([360, 420, 520])
        v.addWidget(split, 1)
        self.wp_png = self.wp_job = self.wp_path = None; self._wp_worker = None
        self._wp_preset_changed()
        return w

    # ------------------------------------------------------------------ plan
    def wp_target(self):
        d = self.wp_preset.currentData()
        return tuple(d) if d else (self.wp_w.value(), self.wp_h.value())

    def _wp_preset_changed(self, _i=None):
        d = self.wp_preset.currentData()
        custom = d is None
        self.wp_w.setEnabled(custom); self.wp_h.setEnabled(custom)
        if d:
            self.wp_w.blockSignals(True); self.wp_h.blockSignals(True)
            self.wp_w.setValue(d[0]); self.wp_h.setValue(d[1])
            self.wp_w.blockSignals(False); self.wp_h.blockSignals(False)
        self.store.set("wp_preset", self.wp_preset.currentText())
        self.wp_update_plan()

    def wp_plan(self):
        tw, th = self.wp_target()
        return wp.plan(tw, th, (getattr(self, "profile", None) or {}).get("family", "Stable Diffusion"))

    def wp_full_prompt(self):
        fmt = (getattr(self, "profile", None) or {}).get("format", "tags")
        return wp.add_composition(self.wp_prompt.toPlainText(), self.wp_side.currentData(), "natural" if fmt == "json" else fmt)

    def wp_update_plan(self):
        if not hasattr(self, "wp_plan_view"):
            return None
        self.store.set("wp_w", self.wp_w.value()); self.store.set("wp_h", self.wp_h.value())
        self.store.set("wp_prompt", self.wp_prompt.toPlainText())
        try:
            p = self.wp_plan()
        except ValueError as e:
            self.wp_plan_view.setText("⚠️ " + str(e)); return None
        name = (getattr(self, "profile", None) or {}).get("name", "")
        extra = ""
        if p["upscale"] > 1:
            extra = "\n" + tr("More than ×2 is needed, so hires stays at ×1.5 (8 GB friendly) and the rest is a final upscale.")
        self.wp_plan_view.setText(f"{tr('Plan for')} {name}:\n{wp.describe(p)}{extra}")
        self.wp_final_prompt.setText(self.wp_full_prompt() or "–")
        return p

    def wp_use_work(self):
        if hasattr(self, "work"):
            self.wp_prompt.setPlainText(self.work.toPlainText())

    # ------------------------------------------------------------------ generate
    def wp_build_job(self):
        p = self.wp_plan()
        if not self.wp_prompt.toPlainText().strip():
            raise ValueError(tr("Write a prompt first (or ↙ use the Refine prompt)"))
        made = self.make_job(self.wp_full_prompt(), self._default_negative(), None, "wallpaper")
        if not made:
            raise ValueError(tr("Write a prompt and set up Forge or ComfyUI in Settings first"))
        job, backend, wf = made
        job.width, job.height = p["base"]
        job.hires = None
        if p["hires"] > 1:
            up = self.store.get("hr_upscaler", "Latent")
            job.hires = {"scale": p["hires"], "upscaler": up, "steps": self.store.get("hr_steps", 0),
                         "denoise": self.wp_denoise.value()}
        job.wallpaper = p
        return job, backend, wf

    def wp_generate(self):
        if self._wp_worker is not None and self._wp_worker.isRunning():
            return None
        try:
            job, backend, wf = self.wp_build_job()
        except ValueError as e:
            self.wp_status.setText("⚠️ " + str(e)); return None
        p = job.wallpaper
        self.wp_job = job
        self.wp_status.setText(tr("Generating") + " · " + wp.describe(p))
        use_backend_up = p["upscale"] > 1 and self.wp_final.currentData() == "backend" and isinstance(backend, imagegen.A1111)
        upscaler = self.store.get("hr_upscaler", "") or ""
        if not upscaler or upscaler.lower().startswith("latent"):
            upscaler = "R-ESRGAN 4x+"

        def work():
            out = backend.generate(job, wf)
            if not out:
                raise imagegen.BackendError("The backend returned no image")
            img = out[0]
            if use_backend_up:  # Forge Extras: pure ESRGAN-style upscale (no diffusion, light on VRAM)
                uj = imagegen.Job("upscale", "", *imagegen.png_size(img))
                uj.upscale = {"image": img, "scale": p["upscale"], "upscaler": upscaler, "denoise": 0}
                up = backend.generate(uj, None)
                img = up[0] if up else img
            return wp.fit_png(img, *p["target"])
        self._wp_worker = CallWorker(work)
        self._wp_worker.ok.connect(lambda png, j=job: self._wp_done(j, png))
        self._wp_worker.failed.connect(lambda e: self.wp_status.setText("⚠️ " + e[:240]))
        self._wp_worker.start()
        return job

    def _wp_done(self, job, png):
        self.wp_png = png
        pm = QPixmap(); pm.loadFromData(png)
        if not pm.isNull():
            self.wp_result.setPixmap(pm.scaled(max(200, self.wp_result.width() - 8), max(120, self.wp_result.height() - 8),
                                               Qt.KeepAspectRatio, Qt.SmoothTransformation))
        tw, th = job.wallpaper["target"]
        msg = f"✓ {tw}×{th}"
        if self.wp_save_folder.isChecked():
            self.wp_path = wp.save(png, self.data_dir, tw, th, job.seed)
            msg += " · " + tr("saved to") + " " + self.wp_path
        self.wp_status.setText(msg)

    # ------------------------------------------------------------------ result actions
    def wp_save_gallery(self):
        if not self.wp_png:
            self.notify(tr("Nothing to save yet"), error=True); return None
        meta = self.wp_job.meta() if self.wp_job else {}
        meta["source"] = "wallpaper"
        p = self.gallery.save(self.wp_png, meta); self.load_gallery()
        self.notify(tr("Saved to Gallery"))
        return p

    def wp_open_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(wp.wallpaper_dir(self.data_dir)))

    def wp_set_desktop(self):
        if not self.wp_png:
            self.notify(tr("Make a wallpaper first"), error=True); return False
        if not self.wp_path or not os.path.exists(self.wp_path):
            tw, th = self.wp_job.wallpaper["target"] if self.wp_job else (0, 0)
            self.wp_path = wp.save(self.wp_png, self.data_dir, tw, th, getattr(self.wp_job, "seed", 0))
        try:
            wp.set_desktop(self.wp_path)
        except OSError as e:
            self.notify(str(e), error=True); return False
        self.notify(tr("Desktop wallpaper set"))
        return True
