"""PromptMaker 4.0 UI: Wildcards, Inpaint & Regions, Video prompts, Library sync.

Mixed into MainWindow next to V3Pages; same Card / button / toast / ConfirmButton patterns."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QSpinBox, QSplitter, QWidget, QVBoxLayout, QHBoxLayout)

from . import regions, sync, video, wildcards
from .i18n import tr
from .inpaintcanvas import InpaintCanvas
from .v3ui import _page
from .widgets import CallWorker, Card, ChatWorker, ConfirmButton, button, hrow, label

GIST_KEY = "github_gist_token"


class V4Pages:
    # ================================================================ shared
    @property
    def wc_lib(self):
        if not hasattr(self, "_wc_lib"):
            self._wc_lib = wildcards.WildcardLib(self.store.get("wildcards_dir") or os.path.join(self.data_dir, "wildcards"))
            os.makedirs(self._wc_lib.root, exist_ok=True)
        return self._wc_lib

    def expand_wildcards(self, prompt, seed=None):
        """Used by make_job: expand __wildcards__ / {a|b} with the image seed so the picture and prompt match."""
        if not self.store.get("wildcards_auto", True) or not wildcards.has_syntax(prompt):
            return prompt
        try:
            return wildcards.expand(prompt, seed, self.wc_lib)
        except RecursionError:
            return prompt

    def _ai_model(self):
        return self.model.currentText().strip()

    def _chat(self, messages, done, temperature=0.8):
        model = self._ai_model()
        if not model:
            self.notify(tr("No AI model – start Ollama or pick a provider in Settings"), error=True); return None
        wk = ChatWorker(self.provider, model, messages, temperature)
        wk.done.connect(done); wk.failed.connect(lambda e: self.notify(e[:200], error=True))
        self._keep(wk); wk.start()
        return wk

    # ================================================================ Wildcards
    def _wildcards_page(self):
        w, v = _page("Wildcards", "Write __name__ to pick a random line from a wildcard file, {a|b|c} to pick one option, "
                                  "{2::a|b} for weights and {2$$a|b|c} to pick several. Same syntax as sd-dynamic-prompts, "
                                  "and the same seed always gives the same prompt.")
        split = QSplitter(Qt.Horizontal)
        lc = Card("Wildcard files")
        self.wc_filter = QLineEdit(); self.wc_filter.setPlaceholderText(tr("Filter…")); self.wc_filter.textChanged.connect(self.wc_reload)
        self.wc_list = QListWidget(); self.wc_list.currentRowChanged.connect(self._wc_selected)
        self.wc_name = QLineEdit(); self.wc_name.setPlaceholderText(tr("name or folder/name"))
        self.wc_edit = QPlainTextEdit(); self.wc_edit.setPlaceholderText(tr("One entry per line. Entries can use {a|b} and other __wildcards__."))
        self.wc_count = label("", "hint")
        lc.add(self.wc_filter); lc.add(self.wc_list, 1)
        lc.add(hrow(label("Name"), self.wc_name)); lc.add(self.wc_edit, 2); lc.add(self.wc_count)
        lc.add(hrow(button("💾 Save", self.wc_save, "primary"), button("New", self.wc_new, "ghost"), None,
                    ConfirmButton("🗑 Delete", self.wc_delete, "Confirm delete")))
        lc.add(hrow(button("📥 Import folder…", self.wc_import_folder, "ghost"), button("📦 Import zip…", self.wc_import_zip, "ghost"),
                    self._wc_policy(), None, button("📂", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.wc_lib.root)), "ghost",
                                                    "Open the wildcards folder")))
        split.addWidget(lc)
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(14)
        tc = Card("Try it")
        self.wc_prompt = QPlainTextEdit(); self.wc_prompt.setFixedHeight(80)
        self.wc_prompt.setPlainText(self.store.get("wc_prompt", "1girl, __hair__, {smiling|serious|surprised}, {2::outdoors|indoors}"))
        self.wc_seed = QSpinBox(); self.wc_seed.setRange(0, 2**31 - 1); self.wc_seed.setValue(self.store.get("wc_seed", 1))
        self.wc_n = QSpinBox(); self.wc_n.setRange(1, 200); self.wc_n.setValue(8)
        self.wc_presets = QCheckBox(tr("Keep ticked characters && styles")); self.wc_presets.setChecked(self.store.get("wc_presets", False))
        self.wc_auto = QCheckBox(tr("Expand wildcards when generating images")); self.wc_auto.setChecked(self.store.get("wildcards_auto", True))
        self.wc_auto.toggled.connect(lambda b: self.store.set("wildcards_auto", b))
        tc.add(self.wc_prompt)
        tc.add(hrow(label("Seed"), self.wc_seed, button("🎲", lambda: self.wc_seed.setValue(__import__("random").randint(0, 2**31 - 1)), "ghost"),
                    label("Variations"), self.wc_n, self.wc_presets, None))
        tc.add(hrow(button("👁 Preview", self.wc_preview, "ghost"), button("🔁 Batch", self.wc_batch, "primary"),
                    button("🖼 Generate images", self.wc_generate, "ghost", "Queue one image per variation"), None))
        self.wc_missing = label("", "hint", wrap=True); tc.add(self.wc_missing)
        self.wc_out = QListWidget(); self.wc_out.setWordWrap(True)
        self.wc_out.itemDoubleClicked.connect(lambda it: self._insert_text(it.data(Qt.UserRole) or it.text(), "copy"))
        tc.add(self.wc_out, 1)
        self.wc_target = self._target_combo()
        tc.add(hrow(label("Send selected to"), self.wc_target, button("➕ Insert", self.wc_insert), None))
        tc.add(self.wc_auto)
        rv.addWidget(tc, 3)
        ac = Card("✨ Write a list with AI")
        self.wc_desc = QLineEdit(); self.wc_desc.setPlaceholderText(tr("e.g. fantasy locations, 90s anime outfits, moody lighting setups"))
        self.wc_ai_n = QSpinBox(); self.wc_ai_n.setRange(5, 200); self.wc_ai_n.setValue(30)
        ac.add(hrow(self.wc_desc, label("Entries"), self.wc_ai_n, button("✨ Generate", self.wc_ai_generate, "primary")))
        ac.add(label("The list goes into the editor on the left – check it, then Save.", "hint"))
        rv.addWidget(ac)
        split.addWidget(right); split.setSizes([460, 640])
        v.addWidget(split, 1)
        self.wc_reload()
        return w

    def _wc_policy(self):
        self.wc_policy = QComboBox()
        for key, name in (("skip", "Keep existing files"), ("replace", "Overwrite existing"), ("rename", "Keep both")):
            self.wc_policy.addItem(tr(name), key)
        return self.wc_policy

    def wc_reload(self, *_):
        self.wc_lib.reload()
        flt = self.wc_filter.text().strip().lower() if hasattr(self, "wc_filter") else ""
        cur = self.wc_name.text().strip()
        self.wc_list.blockSignals(True); self.wc_list.clear()
        for n in self.wc_lib.names():
            if flt and flt not in n.lower():
                continue
            it = QListWidgetItem(f"__{n}__  ·  {len(self.wc_lib.get(n))}"); it.setData(Qt.UserRole, n)
            if not (self.wc_lib.path_of(n) or "").endswith(".txt"):
                it.setToolTip(tr("From a YAML file – read-only here")); it.setForeground(Qt.gray)
            self.wc_list.addItem(it)
            if n == cur:
                self.wc_list.setCurrentItem(it)
        self.wc_list.blockSignals(False)

    def _wc_selected(self, row):
        it = self.wc_list.item(row)
        if not it:
            return
        n = it.data(Qt.UserRole)
        self.wc_name.setText(n); self.wc_edit.setPlainText("\n".join(self.wc_lib.get(n)))
        yaml = not (self.wc_lib.path_of(n) or "").endswith(".txt")
        self.wc_edit.setReadOnly(yaml)
        self.wc_count.setText(f"{len(self.wc_lib.get(n))} " + tr("entries") + (" · " + tr("YAML (read-only – edit the file)") if yaml else "")
                              + f" · {self.wc_lib.path_of(n)}")

    def wc_new(self):
        self.wc_list.clearSelection(); self.wc_name.clear(); self.wc_edit.clear(); self.wc_edit.setReadOnly(False)
        self.wc_count.setText(""); self.wc_name.setFocus()

    def wc_save(self):
        name = self.wc_name.text().strip().strip("_")
        entries = wildcards.parse_lines(self.wc_edit.toPlainText())
        if not name or not entries:
            self.notify(tr("Give the wildcard a name and at least one entry"), error=True); return
        try:
            self.wc_lib.save(name, entries)
        except ValueError as e:
            self.notify(str(e), error=True); return
        sync.touch(self.store); self.wc_name.setText(name); self.wc_reload()
        self.notify(tr("Saved") + f" __{name}__ ({len(entries)})")

    def wc_delete(self):
        name = self.wc_name.text().strip()
        if name:
            self.wc_lib.delete(name); sync.touch(self.store); self.wc_new(); self.wc_reload(); self.notify(tr("Deleted"))

    def wc_import(self, src):
        try:
            st = self.wc_lib.import_path(src, self.wc_policy.currentData())
        except (ValueError, OSError) as e:
            self.notify(str(e), error=True); return None
        sync.touch(self.store); self.wc_reload()
        self.notify(tr("Imported") + f": {st['added']} new, {st['replaced']} replaced, {st['skipped']} skipped")
        return st

    def wc_import_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Choose a wildcards folder"))
        if d:
            self.wc_import(d)

    def wc_import_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Choose a wildcard pack"), "", "Wildcard packs (*.zip *.txt *.yaml *.yml)")
        if f:
            self.wc_import(f)

    def _wc_text(self):
        t = self.wc_prompt.toPlainText().strip()
        self.store.set("wc_prompt", t); self.store.set("wc_seed", self.wc_seed.value()); self.store.set("wc_presets", self.wc_presets.isChecked())
        if self.wc_presets.isChecked():
            chars, styles = self.active_presets()
            from . import presets
            t = presets.compose(t, chars, styles, self.profile) if (chars or styles) else t
        return t

    def _wc_show_missing(self, text):
        miss = [n for n in wildcards.references(text) if not self.wc_lib.get(n)]
        self.wc_missing.setText(("⚠️ " + tr("Unknown wildcards (left as text)") + ": " + ", ".join(f"__{m}__" for m in miss)) if miss else "")

    def wc_preview(self):
        t = self._wc_text()
        try:
            res = wildcards.expand(t, self.wc_seed.value(), self.wc_lib)
        except RecursionError as e:
            self.notify(str(e), error=True); return
        self._wc_show_missing(t)
        self.wc_out.clear(); it = QListWidgetItem(f"#{self.wc_seed.value()}  {res}"); it.setData(Qt.UserRole, res); self.wc_out.addItem(it)
        self.wc_out.setCurrentRow(0)
        return res

    def wc_batch(self):
        t = self._wc_text()
        try:
            res = wildcards.batch(t, self.wc_n.value(), self.wc_seed.value(), self.wc_lib)
        except RecursionError as e:
            self.notify(str(e), error=True); return []
        self._wc_show_missing(t)
        self.wc_out.clear()
        for s, p in res:
            it = QListWidgetItem(f"#{s}  {p}"); it.setData(Qt.UserRole, p); it.setData(Qt.UserRole + 1, s); self.wc_out.addItem(it)
            self.store.add_history(p, self.profile["name"], "wildcards")
        if len(res) < self.wc_n.value():
            self.notify(tr("Only") + f" {len(res)} " + tr("different prompts are possible with these lists"))
        return res

    def wc_insert(self):
        it = self.wc_out.currentItem() or self.wc_out.item(0)
        if it:
            self._insert_text(it.data(Qt.UserRole), self.wc_target.currentData())

    def wc_generate(self):
        res = [(self.wc_out.item(i).data(Qt.UserRole + 1), self.wc_out.item(i).data(Qt.UserRole)) for i in range(self.wc_out.count())]
        if not res or res[0][0] is None:
            res = self.wc_batch()
        jobs = []
        for s, p in res:
            made = self.make_job(p, self._default_negative(), s, "wildcards")
            if not made:
                self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return []
            job, backend, wf = made
            self.genq.add(job, backend, wf); self.queue_jobs.append(job); jobs.append(job)
        self._render_queue(); self.notify(f"{len(jobs)} " + tr("image(s) queued – see Gallery"))
        return jobs

    def wc_ai_generate(self):
        desc = self.wc_desc.text().strip()
        if not desc:
            self.notify(tr("Describe the list first"), error=True); return

        def done(text):
            entries = wildcards.parse_generated(text, self.wc_ai_n.value())
            if not entries:
                self.notify(tr("The AI didn't return a usable list – try again"), error=True); return
            self.wc_list.clearSelection(); self.wc_edit.setReadOnly(False)
            if not self.wc_name.text().strip() or self.wc_lib.get(self.wc_name.text().strip()):
                self.wc_name.setText(wildcards.suggest_name(desc))
            self.wc_edit.setPlainText("\n".join(entries))
            self.wc_count.setText(f"{len(entries)} " + tr("entries – not saved yet"))
            self.notify(tr("List ready – check it and press Save"))
        return self._chat(wildcards.generate_messages(desc, self.wc_ai_n.value()), done, 0.9)

    # ================================================================ Inpaint & Regions
    def _inpaint_page(self):
        w, v = _page("Inpaint & Regions", "Paint over part of an image to redraw it (inpaint), or draw boxes that each get their "
                                          "own prompt (regional prompting).")
        split = QSplitter(Qt.Horizontal)
        cc = Card("Canvas")
        self.ip_canvas = InpaintCanvas()
        self.ip_size = QComboBox()
        for name, wh in (("Model default", None), ("1024×1024 square", (1024, 1024)), ("1344×768 wide", (1344, 768)),
                         ("1216×832 landscape", (1216, 832)), ("832×1216 portrait", (832, 1216)), ("768×1344 tall", (768, 1344))):
            self.ip_size.addItem(tr(name), wh)
        self.ip_size.currentIndexChanged.connect(lambda _i: self.ip_blank() if self.ip_canvas.image is None else None)
        self.ip_mode = QComboBox()
        for key, name in (("brush", "🖌 Paint mask"), ("erase", "🧽 Erase mask"), ("region", "▭ Draw regions")):
            self.ip_mode.addItem(tr(name), key)
        self.ip_mode.currentIndexChanged.connect(lambda _i: setattr(self.ip_canvas, "mode", self.ip_mode.currentData()))
        self.ip_brush = QSpinBox(); self.ip_brush.setRange(2, 400); self.ip_brush.setValue(48); self.ip_brush.setSuffix(" px")
        self.ip_brush.valueChanged.connect(lambda n: setattr(self.ip_canvas, "brush", n))
        cc.add(hrow(button("📂 Open image…", lambda: self.ip_open(), "ghost"), button("🗂 Last generated", self.ip_last, "ghost"),
                    button("⬜ Blank", self.ip_blank, "ghost", "Blank canvas at the target model's size – for regions"),
                    label("Size"), self.ip_size, None))
        cc.add(hrow(self.ip_mode, label("Brush"), self.ip_brush, None, button("⇄ Invert", self.ip_canvas.invert_mask, "ghost"),
                    ConfirmButton("Clear mask", self.ip_canvas.clear_mask, "Confirm clear")))
        cc.add(self.ip_canvas, 1)
        self.ip_info = label("", "hint"); cc.add(self.ip_info)
        split.addWidget(cc)
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(12)
        gc = Card("Prompt & model")
        self.ip_prompt = QPlainTextEdit(); self.ip_prompt.setFixedHeight(64)
        self.ip_prompt.setPlaceholderText(tr("Prompt for the masked area / the whole image (empty = working prompt)"))
        self.ip_ckpt = self.make_ckpt_combo(); self.ip_ckpt.setMinimumWidth(260)
        gc.add(self.ip_prompt)
        gc.add(hrow(label("Checkpoint"), self.ip_ckpt, button("⟳", self.load_checkpoints, "ghost", "Reload checkpoint list")))
        rv.addWidget(gc)
        ic = Card("Inpaint")
        self.ip_denoise = QDoubleSpinBox(); self.ip_denoise.setRange(0.05, 1.0); self.ip_denoise.setSingleStep(0.05)
        self.ip_denoise.setValue(self.store.get("ip_denoise", 0.75))
        self.ip_blur = QSpinBox(); self.ip_blur.setRange(0, 64); self.ip_blur.setValue(self.store.get("ip_blur", 4))
        self.ip_area = QComboBox(); self.ip_area.addItems([tr(k) for k in regions.INPAINT_AREAS])
        self.ip_area.setCurrentIndex(self.store.get("ip_area", 1))
        self.ip_pad = QSpinBox(); self.ip_pad.setRange(0, 256); self.ip_pad.setValue(self.store.get("ip_pad", 32))
        self.ip_fill = QComboBox(); self.ip_fill.addItems(regions.FILL_MODES); self.ip_fill.setCurrentText(self.store.get("ip_fill", "original"))
        ic.add(hrow(label("Denoise"), self.ip_denoise, label("Mask blur"), self.ip_blur, None))
        ic.add(hrow(label("Inpaint area"), self.ip_area, label("Padding"), self.ip_pad, None))
        ic.add(hrow(label("Masked content"), self.ip_fill, None, button("🖌 Inpaint", self.ip_inpaint, "primary")))
        rv.addWidget(ic)
        rc = Card("Regions")
        self.rg_list = QListWidget(); self.rg_list.setMaximumHeight(110); self.rg_list.currentRowChanged.connect(self.ip_canvas.select)
        self.ip_canvas.selection_changed.connect(self._rg_selected); self.ip_canvas.regions_changed.connect(self.rg_refresh)
        self.rg_prompt = QLineEdit(); self.rg_prompt.setPlaceholderText(tr("Prompt for the selected region"))
        self.rg_prompt.textEdited.connect(self._rg_edit)
        self.rg_weight = QDoubleSpinBox(); self.rg_weight.setRange(0.1, 5.0); self.rg_weight.setSingleStep(0.1); self.rg_weight.setValue(1.0)
        self.rg_weight.valueChanged.connect(self._rg_edit)
        self.rg_base_w = QDoubleSpinBox(); self.rg_base_w.setRange(0.0, 1.5); self.rg_base_w.setSingleStep(0.1)
        self.rg_base_w.setValue(self.store.get("rg_base_weight", 0.2))
        self.rg_repeat = QCheckBox(tr("Repeat main prompt in every region (recommended)"))
        self.rg_repeat.setChecked(bool(self.store.get("rg_repeat_base", True)))
        rc.add(self.rg_list)
        rc.add(hrow(self.rg_prompt, label("Weight"), self.rg_weight))
        rc.add(hrow(button("＋ Region", lambda: self.ip_canvas.add_region("", (.55, .05, .4, .9)), "ghost"),
                    button("Remove", lambda: self.ip_canvas.remove_region(), "ghost"),
                    button("Mask it", self.rg_mask_selected, "ghost", "Turn the selected region into the inpaint mask"),
                    None, label("Base weight"), self.rg_base_w))
        rc.add(self.rg_repeat)
        self.rg_status = label(tr("Forge needs the Forge Couple extension for regions; ComfyUI works as is."), "hint", wrap=True)
        rc.add(self.rg_status)
        rc.add(hrow(button("🔎 Check support", self.rg_check, "ghost"), button("📋 Copy as one prompt", self.rg_copy_plain, "ghost"),
                    None, button("🗺 Generate with regions", lambda: self.rg_generate(), "primary")))
        rv.addWidget(rc, 1)
        split.addWidget(right); split.setSizes([640, 480])
        v.addWidget(split, 1)
        self.ip_canvas.changed.connect(self._ip_info)
        self.ip_canvas.set_blank(*self._ip_size())
        return w

    def _ip_size(self):
        wh = self.ip_size.currentData() if hasattr(self, "ip_size") else None
        if wh:
            return wh
        try:
            return self._size_for_profile()
        except Exception:  # noqa: BLE001
            return 1024, 1024

    def _ip_info(self):
        iw, ih = self.ip_canvas.img_size()
        self.ip_info.setText(f"{iw}×{ih} · " + (tr("image loaded") if self.ip_canvas.image is not None else tr("blank canvas")) +
                             f" · {len(self.ip_canvas.regions)} " + tr("region(s)"))

    def ip_open(self, path=None):
        f = path or QFileDialog.getOpenFileName(self, tr("Open image"), "", "Images (*.png *.jpg *.jpeg *.webp)")[0]
        if f:
            try:
                self.ip_canvas.set_image(f); self.ip_mode.setCurrentIndex(0)
            except ValueError as e:
                self.notify(str(e), error=True)

    def ip_last(self):
        items = self.gallery.items()
        if not items:
            self.notify(tr("The Gallery is empty – generate something first"), error=True); return
        path, meta = items[0]
        self.ip_open(path)
        if meta.get("prompt") and not self.ip_prompt.toPlainText().strip():
            self.ip_prompt.setPlainText(meta["prompt"])

    def ip_blank(self):
        self.ip_canvas.set_blank(*self._ip_size()); self.ip_mode.setCurrentIndex(2)

    def _ip_prompt_text(self):
        return self.ip_prompt.toPlainText().strip() or self.work.toPlainText().strip() or self.c_prompt.toPlainText().strip()

    def _ip_job(self, tag):
        prompt = self._ip_prompt_text()
        if not prompt:
            self.notify(tr("Write a prompt first"), error=True); return None
        made = self.make_job(prompt, self._default_negative(), None, tag)
        if not made:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return None
        job, backend, wf = made
        job.width, job.height = self.ip_canvas.img_size()
        return job, backend, wf

    def ip_inpaint(self):
        c = self.ip_canvas
        if c.image is None:
            self.notify(tr("Open an image first (or use the last generated one)"), error=True); return None
        if not c.has_mask():
            self.notify(tr("Paint over the part you want to change first"), error=True); return None
        made = self._ip_job("inpaint")
        if not made:
            return None
        job, backend, wf = made
        only = list(regions.INPAINT_AREAS.values())[self.ip_area.currentIndex()]
        for k, val in (("ip_denoise", self.ip_denoise.value()), ("ip_blur", self.ip_blur.value()), ("ip_area", self.ip_area.currentIndex()),
                       ("ip_pad", self.ip_pad.value()), ("ip_fill", self.ip_fill.currentText())):
            self.store.set(k, val)
        job.inpaint = {"image": c.image_png(), "mask": c.mask_png(), "denoise": self.ip_denoise.value(), "mask_blur": self.ip_blur.value(),
                       "only_masked": only, "padding": self.ip_pad.value(), "fill": self.ip_fill.currentText()}
        self.genq.add(job, backend, wf); self.queue_jobs.append(job); self._render_queue()
        self.notify(tr("Inpaint queued") + f" · seed {job.seed}")
        return job

    def rg_refresh(self):
        c = self.ip_canvas
        self.rg_list.blockSignals(True); self.rg_list.clear()
        for i, r in enumerate(c.regions):
            self.rg_list.addItem(f"{i + 1}. {r.get('prompt') or tr('(no prompt)')}  ·  w{r.get('weight', 1):g}")
        self.rg_list.setCurrentRow(c.selected); self.rg_list.blockSignals(False)
        self._ip_info()

    def _rg_selected(self, i):
        self.rg_list.blockSignals(True); self.rg_list.setCurrentRow(i); self.rg_list.blockSignals(False)
        r = self.ip_canvas.regions[i] if 0 <= i < len(self.ip_canvas.regions) else None
        self.rg_prompt.setText(r["prompt"] if r else ""); self.rg_prompt.setEnabled(bool(r))
        self.rg_weight.blockSignals(True); self.rg_weight.setValue(r["weight"] if r else 1.0); self.rg_weight.blockSignals(False)
        if r and self.ip_mode.currentData() != "region":
            self.ip_mode.setCurrentIndex(2)

    def _rg_edit(self, *_):
        i = self.ip_canvas.selected
        if 0 <= i < len(self.ip_canvas.regions):
            self.ip_canvas.regions[i].update(prompt=self.rg_prompt.text(), weight=self.rg_weight.value())
            item = self.rg_list.item(i)
            if item:
                item.setText(f"{i + 1}. {self.rg_prompt.text() or tr('(no prompt)')}  ·  w{self.rg_weight.value():g}")
            self.ip_canvas.update()

    def rg_mask_selected(self):
        i = self.ip_canvas.selected
        if 0 <= i < len(self.ip_canvas.regions):
            r = self.ip_canvas.regions[i]; self.ip_canvas.fill_rect_mask(r["x"], r["y"], r["w"], r["h"])
            if r.get("prompt") and not self.ip_prompt.toPlainText().strip():
                self.ip_prompt.setPlainText(r["prompt"])

    def rg_copy_plain(self):
        from .app import copy
        text = regions.plain_prompt(self._ip_prompt_text(), self.ip_canvas.regions)
        copy(text); self.notify(tr("Copied")); return text

    def rg_check(self):
        backend = self.image_backend()
        if not backend:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return None
        wk = CallWorker(backend.regional_support)
        wk.ok.connect(self._rg_support_shown); self._keep(wk); wk.start()
        return wk

    def _rg_support_shown(self, mode):
        self._rg_mode = mode
        self.rg_status.setText({"comfy": "✅ " + tr("ComfyUI: regions use ConditioningSetArea – nothing to install."),
                                regions.FORGE_COUPLE: "✅ " + tr("Forge Couple found – regions are sent in its Advanced mode.")}
                               .get(mode, "⚠️ " + tr(regions.NEEDS_EXTENSION)))
        return mode

    def rg_generate(self, mode=None):
        if not regions.valid_regions(self.ip_canvas.regions):
            self.notify(tr("Draw at least one region and give it a prompt"), error=True); return None
        made = self._ip_job("regions")
        if not made:
            return None
        job, backend, wf = made
        if mode is None:
            try:
                mode = backend.regional_support()
            except Exception:  # noqa: BLE001
                mode = ""
        self._rg_support_shown(mode)
        if not mode:
            box = QMessageBox(self); box.setIcon(QMessageBox.Information); box.setWindowTitle(tr("Regional prompts"))
            box.setText(tr(regions.NEEDS_EXTENSION))
            plain = box.addButton(tr("Send as one prompt instead"), QMessageBox.AcceptRole); box.addButton(QMessageBox.Cancel)
            self._last_rg_box = box
            if os.environ.get("PROMPTMAKER_NO_DIALOGS"):
                return None
            box.exec()
            if box.clickedButton() is not plain:
                return None
            mode = "plain"
        self.store.set("rg_base_weight", self.rg_base_w.value()); self.store.set("rg_repeat_base", self.rg_repeat.isChecked())
        job.regions = {"regions": [dict(r) for r in self.ip_canvas.regions], "mode": mode, "base_weight": self.rg_base_w.value(),
                       "repeat_base": self.rg_repeat.isChecked()}
        if self.ip_canvas.image is not None and self.ip_canvas.has_mask():
            job.inpaint = {"image": self.ip_canvas.image_png(), "mask": self.ip_canvas.mask_png(), "denoise": self.ip_denoise.value(),
                           "mask_blur": self.ip_blur.value(), "only_masked": False, "padding": self.ip_pad.value(),
                           "fill": self.ip_fill.currentText()}
        self.genq.add(job, backend, wf); self.queue_jobs.append(job); self._render_queue()
        self.notify(tr("Queued with regions") + f" ({mode}) · seed {job.seed}")
        return job

    # ================================================================ Video prompts
    def _video_page(self):
        w, v = _page("Video", "Write prompts for video models. Pick the model, describe the shot, choose a camera move – the prompt "
                              "is built in the structure that model prefers. Prompt writing only; render it in ComfyUI or your video tool.")
        split = QSplitter(Qt.Horizontal)
        fc = Card("Shot")
        self.vd_model = QComboBox()
        for mid, m in video.MODELS.items():
            self.vd_model.addItem(m["name"], mid)
        self.vd_model.setCurrentIndex(max(0, self.vd_model.findData(self.store.get("vd_model", "wan22"))))
        self.vd_idea = QPlainTextEdit(); self.vd_idea.setFixedHeight(54); self.vd_idea.setPlaceholderText(tr("Idea in plain words (optional, used by the AI writer)"))
        self.vd = {}
        for key, ph in (("subject", "Subject, e.g. a red fox with a thick winter coat"), ("action", "Action, e.g. trots through fresh snow"),
                        ("scene", "Scene, e.g. a quiet birch forest at dawn"), ("lighting", "Lighting, e.g. soft golden backlight"),
                        ("style", "Style, e.g. cinematic, 35mm film, shallow depth of field"), ("extra", "Anything else")):
            e = QLineEdit(); e.setPlaceholderText(tr(ph)); self.vd[key] = e
        self.vd_camera, self.vd_motion, self.vd_shot = QComboBox(), QComboBox(), QComboBox()
        for c, items in ((self.vd_camera, video.CAMERA), (self.vd_motion, video.MOTION), (self.vd_shot, video.SHOTS)):
            c.setEditable(True); c.addItem(""); c.addItems(list(items))
        self.vd_secs = QDoubleSpinBox(); self.vd_secs.setRange(1, 20); self.vd_secs.setSingleStep(0.5); self.vd_secs.setSuffix(" s")
        self.vd_size = QComboBox()
        self.vd_frames = label("", "hint")
        self.vd_use_char = QCheckBox(tr("Use ticked character"))
        self.vd_use_char.toggled.connect(self._vd_char)
        fc.add(hrow(label("Model"), self.vd_model, None, self.vd_use_char))
        fc.add(self.vd_idea)
        for k in ("subject", "action", "scene"):
            fc.add(self.vd[k])
        fc.add(hrow(label("Camera"), self.vd_camera, label("Motion"), self.vd_motion))
        fc.add(hrow(label("Shot"), self.vd_shot, None))
        for k in ("lighting", "style", "extra"):
            fc.add(self.vd[k])
        fc.add(hrow(label("Duration"), self.vd_secs, label("Size"), self.vd_size, self.vd_frames, None))
        fc.add(hrow(button("🧱 Build", self.vd_build, "ghost", "Build the prompt offline from the fields"),
                    button("✨ Write with AI", self.vd_write, "primary"), None))
        fc.lay.addStretch()
        split.addWidget(fc)
        oc = Card("Video prompt")
        self.vd_out = QPlainTextEdit(); self.vd_out.textChanged.connect(self._vd_check)
        self.vd_neg = QPlainTextEdit(); self.vd_neg.setFixedHeight(64)
        self.vd_warn = label("", "hint", wrap=True)
        self.vd_name = QLineEdit(); self.vd_name.setPlaceholderText(tr("Name to save as"))
        oc.add(self.vd_out, 2); oc.add(label("Negative", "h2")); oc.add(self.vd_neg); oc.add(self.vd_warn)
        oc.add(hrow(button("📋 Copy", lambda: self._insert_text(self.vd_out.toPlainText(), "copy"), "ghost"),
                    button("📋 Copy negative", lambda: self._insert_text(self.vd_neg.toPlainText(), "copy"), "ghost"),
                    None, self.vd_name, button("💾 Save", self.vd_save, "primary")))
        oc.add(label("Saved", "h2"))
        self.vd_saved = QListWidget(); self.vd_saved.setWordWrap(True); self.vd_saved.itemDoubleClicked.connect(self._vd_load)
        oc.add(self.vd_saved, 1)
        oc.add(hrow(None, ConfirmButton("🗑 Delete", self.vd_delete, "Confirm delete")))
        split.addWidget(oc); split.setSizes([560, 560])
        v.addWidget(split, 1)
        self.vd_model.currentIndexChanged.connect(self._vd_model_changed); self.vd_secs.valueChanged.connect(self._vd_frames)
        self._vd_model_changed(); self.vd_load_saved()
        return w

    def _vd_mid(self):
        return self.vd_model.currentData()

    def _vd_model_changed(self, *_):
        mid = self._vd_mid(); m = video.MODELS[mid]; self.store.set("vd_model", mid)
        self.vd_size.clear(); self.vd_size.addItems(m["sizes"])
        self.vd_secs.setValue(m["default_secs"])
        self.vd_neg.setEnabled(m["negative"])
        if not self.vd_neg.toPlainText().strip() or self.vd_neg.toPlainText() in [x["default_negative"] for x in video.MODELS.values()]:
            self.vd_neg.setPlainText(m["default_negative"])
        self.vd_neg.setPlaceholderText("" if m["negative"] else tr("This model doesn't use a negative prompt"))
        self._vd_frames(); self._vd_check()

    def _vd_frames(self, *_):
        mid = self._vd_mid(); m = video.MODELS[mid]
        n = video.frames_for(mid, self.vd_secs.value())
        self.vd_frames.setText(f"{n} " + tr("frames") + f" @ {m['fps']} fps ≈ {video.seconds_for(mid, n)} s")

    def _vd_char(self, on):
        if on:
            chars, _ = self.active_presets()
            if not chars:
                self.notify(tr("Tick a character on the Presets page first"), error=True); self.vd_use_char.setChecked(False); return
            from . import presets
            self.vd["subject"].setText(presets.character_text(chars[0], {"format": "natural"}, with_lora=False))

    def vd_fields(self):
        f = {k: e.text().strip() for k, e in self.vd.items()}
        f.update(camera=self.vd_camera.currentText().strip(), motion=self.vd_motion.currentText().strip(),
                 shot=self.vd_shot.currentText().strip(), duration=f"{self.vd_secs.value():g}")
        return f

    def vd_build(self):
        text = video.compose(self._vd_mid(), self.vd_fields())
        if not text:
            self.notify(tr("Fill in at least the subject"), error=True); return ""
        self.vd_out.setPlainText(text); return text

    def vd_write(self):
        f = self.vd_fields()
        idea = self.vd_idea.toPlainText().strip()
        if not idea and not f.get("subject"):
            self.notify(tr("Write an idea or a subject first"), error=True); return None
        msgs = video.writer_messages(self._vd_mid(), {k: video.CAMERA.get(val, video.MOTION.get(val, val)) for k, val in f.items()}, idea)

        def done(text):
            out = video.clean_output(text)
            if out:
                self.vd_out.setPlainText(out); self.store.add_history(out, video.MODELS[self._vd_mid()]["name"], "video")
                self.notify(tr("Video prompt ready"))
        self.vd_out.setPlainText(tr("Writing…"))
        return self._chat(msgs, done, 0.7)

    def _vd_check(self):
        if hasattr(self, "vd_warn"):
            warns = video.check(self._vd_mid(), self.vd_out.toPlainText())
            n = video.word_count(self.vd_out.toPlainText())
            self.vd_warn.setText((f"{n} " + tr("words") + (" · ⚠️ " + " ".join(warns) if warns else " · ✅")) if n else "")

    def vd_save(self):
        text = self.vd_out.toPlainText().strip()
        if not text:
            self.notify(tr("Nothing to save yet"), error=True); return None
        mid = self._vd_mid()
        settings = dict(self.vd_fields(), size=self.vd_size.currentText(), frames=video.frames_for(mid, self.vd_secs.value()),
                        fps=video.MODELS[mid]["fps"], idea=self.vd_idea.toPlainText().strip())
        vid = self.store.save_video_prompt(self.vd_name.text().strip() or (self.vd["subject"].text().strip()[:40] or "Video prompt"),
                                           mid, text, self.vd_neg.toPlainText().strip() if video.MODELS[mid]["negative"] else "", settings)
        self.vd_load_saved(); self.notify(tr("Saved")); return vid

    def vd_load_saved(self):
        self.vd_saved.clear()
        for d in self.store.video_prompts():
            it = QListWidgetItem(f"{d['name']} · {video.MODELS.get(d['model'], {}).get('name', d['model'])}\n{d['prompt'][:140]}")
            it.setData(Qt.UserRole, d); self.vd_saved.addItem(it)

    def _vd_load(self, it):
        d = it.data(Qt.UserRole); s = d.get("settings") or {}
        self.vd_model.setCurrentIndex(max(0, self.vd_model.findData(d["model"])))
        for k, e in self.vd.items():
            e.setText(s.get(k, ""))
        self.vd_camera.setCurrentText(s.get("camera", "")); self.vd_motion.setCurrentText(s.get("motion", "")); self.vd_shot.setCurrentText(s.get("shot", ""))
        if s.get("duration"):
            self.vd_secs.setValue(float(s["duration"]))
        self.vd_idea.setPlainText(s.get("idea", "")); self.vd_name.setText(d["name"])
        self.vd_out.setPlainText(d["prompt"]); self.vd_neg.setPlainText(d.get("negative", ""))

    def vd_delete(self):
        it = self.vd_saved.currentItem()
        if it:
            self.store.delete_video_prompt(it.data(Qt.UserRole)["id"]); self.vd_load_saved()

    # ================================================================ Library sync
    def _sync_page(self):
        w, v = _page("Library sync", "Back up or move your whole library – prompts, history, favourites, templates, characters, styles, "
                                     "video prompts, LoRA info, wildcards and settings. API keys are never exported.")
        row = QHBoxLayout(); row.setSpacing(14)
        ec = Card("Export")
        self.sy_summary = label("", "hint", wrap=True)
        ec.add(self.sy_summary)
        ec.add(hrow(button("📦 Export .zip…", lambda: self.sy_export(fmt="zip"), "primary"),
                    button("Export .json…", lambda: self.sy_export(fmt="json"), "ghost"), None))
        ec.add(label("The .zip keeps wildcards as normal files; the .json is one file. Neither contains API keys or your GitHub token.",
                     "hint", wrap=True))
        ec.lay.addStretch()
        row.addWidget(ec, 1)
        ic = Card("Import")
        self.sy_mode = QComboBox(); self.sy_mode.addItem(tr("Merge into my library"), "merge"); self.sy_mode.addItem(tr("Replace my library"), "replace")
        self.sy_policy = QComboBox()
        for key, name in (("skip", "Keep mine"), ("overwrite", "Take theirs"), ("rename", "Keep both (rename)")):
            self.sy_policy.addItem(tr(name), key)
        ic.add(hrow(label("Mode"), self.sy_mode, None)); ic.add(hrow(label("Same name, different content"), self.sy_policy, None))
        ic.add(hrow(button("📥 Import…", lambda: self.sy_import(), "primary"), None))
        self.sy_import_res = label("", "hint", wrap=True); ic.add(self.sy_import_res)
        ic.lay.addStretch()
        row.addWidget(ic, 1)
        v.addLayout(row)
        gc = Card("GitHub gist (private)")
        self.sy_token = QLineEdit(); self.sy_token.setEchoMode(QLineEdit.Password)
        self.sy_token.setPlaceholderText(tr("GitHub token with the 'gist' scope (stored only on this computer)"))
        if self.keys.get(GIST_KEY):
            self.sy_token.setPlaceholderText(tr("Token saved – paste a new one to replace it"))
        self.sy_gist = QLineEdit(self.store.get("gist_id", "") or ""); self.sy_gist.setPlaceholderText(tr("Gist ID (empty = create one on first push)"))
        self.sy_gist.editingFinished.connect(lambda: self.store.set("gist_id", self.sy_gist.text().strip() or None))
        gc.add(hrow(label("Token"), self.sy_token, button("💾 Save token", self.sy_save_token, "ghost"),
                    ConfirmButton("Forget", lambda: (self.keys.delete(GIST_KEY), self.notify(tr("Token removed"))), "Confirm")))
        gc.add(hrow(label("Gist"), self.sy_gist, button("🔌 Test", self.sy_test, "ghost")))
        gc.add(hrow(button("⬆ Push", lambda: self.sy_run("push"), "ghost"), button("⬇ Pull", lambda: self.sy_run("pull"), "ghost"),
                    button("🔄 Sync", lambda: self.sy_run("sync"), "primary"), None))
        self.sy_status = label("", "hint", wrap=True); gc.add(self.sy_status)
        gc.add(label("Sync compares last-modified times: if only one side changed it pushes or pulls; if both changed it asks whether "
                     "to keep this computer, keep the gist, or merge both. Create a token at github.com/settings/tokens "
                     "(classic: 'gist' scope; fine-grained: Gists read & write).", "hint", wrap=True))
        self.sy_log = QListWidget(); self.sy_log.setMaximumHeight(110); gc.add(self.sy_log)
        v.addWidget(gc); v.addStretch()
        self.sy_refresh()
        return w

    def _sy_paths(self):
        return {"wildcard_lib": self.wc_lib, "lora_cache": self._lora_cache_path(), "profiles_path": self.profiles_path}

    def sy_refresh(self):
        c = sync.counts(sync.build(self.store, **self._sy_paths()))
        self.sy_summary.setText(" · ".join(f"{n} {tr(k.replace('_', ' '))}" for k, n in c.items()))
        self.sy_log.clear()
        import time as _t
        for ts, d, target, st, detail in self.store.sync_log(20):
            self.sy_log.addItem(f"{_t.strftime('%Y-%m-%d %H:%M', _t.localtime(ts))} · {d} · {st} · {target} {detail[:80]}")

    def sy_export(self, path=None, fmt="zip"):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export library"), f"promptmaker-library.{fmt}",
                                                  "Zip (*.zip)" if fmt == "zip" else "JSON (*.json)")
        if not path:
            return None
        b = sync.build(self.store, **self._sy_paths())
        sync.export_file(path, b); self.store.log_sync("export", os.path.basename(path), "ok")
        self.sy_refresh(); self.notify(tr("Exported") + f" → {os.path.basename(path)}")
        return path

    def sy_import(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("Import library"), "", "PromptMaker library (*.zip *.json)")
        if not path:
            return None
        try:
            b = sync.read_file(path)
            st = sync.apply(self.store, b, self.sy_mode.currentData(), self.sy_policy.currentData(), **self._sy_paths())
        except (sync.SyncError, ValueError, OSError, KeyError) as e:
            self.notify(str(e), error=True); return None
        self.store.log_sync("import", os.path.basename(path), "ok", str(st))
        self.sy_import_res.setText(tr("Imported") + f": {st['added']} added, {st['skipped']} unchanged/skipped, "
                                   f"{st['overwritten']} overwritten, {st['renamed']} renamed")
        self._after_library_change(); self.notify(tr("Library imported"))
        return st

    def _after_library_change(self):
        self.wc_reload(); self.load_presets(); self.vd_load_saved(); self.sy_refresh()

    def sy_save_token(self):
        t = self.sy_token.text().strip()
        if not t:
            self.notify(tr("Paste a token first"), error=True); return
        where = self.keys.set(GIST_KEY, t); self.sy_token.clear()
        self.sy_token.setPlaceholderText(tr("Token saved – paste a new one to replace it"))
        self.notify(tr("Token saved") + (" (" + tr("OS keyring") + ")" if where == "keyring" else " (secrets.json)"))

    def _sy_client(self):
        t = self.sy_token.text().strip() or self.keys.get(GIST_KEY)
        return sync.Gist(t, self.store.get("gist_api", "https://api.github.com"))

    def sy_test(self):
        try:
            client = self._sy_client()
        except sync.SyncError as e:
            self.notify(str(e), error=True); return None
        wk = CallWorker(client.user)
        wk.ok.connect(lambda u: (self.sy_status.setText("✅ " + tr("Connected as") + f" {u}"), self.notify(tr("GitHub connected"))))
        wk.failed.connect(lambda e: (self.sy_status.setText("⚠️ " + e), self.notify(e, error=True)))
        self._keep(wk); wk.start(); return wk

    def sy_run(self, action, resolution=None, wait=False):
        try:
            gs = sync.GistSync(self.store, self._sy_client(), **self._sy_paths())
        except sync.SyncError as e:
            self.notify(str(e), error=True); return None
        self.store.set("gist_id", self.sy_gist.text().strip() or self.store.get("gist_id"))
        fn = {"push": gs.push, "pull": lambda: gs.pull("merge", self.sy_policy.currentData()),
              "sync": lambda: gs.sync(resolution)}[action]
        self.sy_status.setText(tr("Working…"))
        if wait:  # tests / screenshots
            try:
                return self._sy_done(fn())
            except sync.Conflict as c:
                return self._sy_conflict(c, action)
            except sync.SyncError as e:
                return self._sy_failed(str(e))
        wk = CallWorker(fn)
        wk.ok.connect(self._sy_done)
        wk.failed.connect(lambda e: self._sy_failed(e))
        self._keep(wk); wk.start(); return wk

    def _sy_done(self, res):
        if res.get("gist_id"):
            self.sy_gist.setText(res["gist_id"])
        msg = {"created": tr("Created a private gist and pushed"), "pushed": tr("Pushed to gist"), "pulled": tr("Pulled from gist"),
               "merged": tr("Merged both and pushed"), "in_sync": tr("Already in sync")}.get(res.get("action"), str(res))
        self.sy_status.setText("✅ " + msg)
        if res.get("action") in ("pulled", "merged"):
            self._after_library_change()
        else:
            self.sy_refresh()
        self.notify(msg); return res

    def _sy_failed(self, err):
        if "Both this computer and the gist changed" in err:
            return self._sy_conflict(None, "sync")
        self.store.log_sync("gist", self.store.get("gist_id") or "", "error", err)
        self.sy_status.setText("⚠️ " + err); self.notify(err, error=True); self.sy_refresh()
        return None

    def _sy_conflict(self, conflict, action):
        box = QMessageBox(self); box.setIcon(QMessageBox.Question); box.setWindowTitle(tr("Sync conflict"))
        box.setText(tr("Both this computer and the gist changed since the last sync. What should win?"))
        local = box.addButton(tr("Keep this computer"), QMessageBox.AcceptRole)
        remote = box.addButton(tr("Keep the gist"), QMessageBox.DestructiveRole)
        merge = box.addButton(tr("Merge both"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        self._last_sync_box = box
        self.sy_status.setText("⚠️ " + tr("Conflict – choose what to keep"))
        if os.environ.get("PROMPTMAKER_NO_DIALOGS"):
            return {"action": "conflict"}
        box.exec()
        res = {local: "local", remote: "remote", merge: "merge"}.get(box.clickedButton())
        if res:
            return self.sy_run("sync", res)
        return {"action": "conflict"}
