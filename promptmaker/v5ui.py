"""PromptMaker 5.0 pages: Characters, Storyboard (comics), Live sketch and LoRA training."""
import json
import os

from PySide6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSlider, QSpinBox, QSplitter, QWidget)

from . import characters as ch
from . import sketch, storyboard as sbm, trainer
from .i18n import tr
from .widgets import CallWorker, Card, ChatWorker, ConfirmButton, FlowLayout, button, hrow, label


def _thumb(path, n=56):
    pm = QPixmap(path) if path and os.path.exists(path) else QPixmap()
    return pm.scaled(n, n, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull() else pm


def _ask(parent, title, text):
    from .v41ui import offscreen
    if offscreen():  # tests / headless: never block on a modal question
        return getattr(parent, "_auto_confirm", False)
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


class PanelPreview(QLabel):
    """Rendered comic page; gallery thumbnails / image files dropped on a panel become that panel's image."""
    def __init__(self, win):
        super().__init__(); self.win = win
        self.setAcceptDrops(True); self.setAlignment(Qt.AlignCenter); self.setMinimumSize(300, 360); self.setObjectName("dropZone")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.win.sb_drop(urls[0].toLocalFile(), e.position().toPoint())

    def mousePressEvent(self, e):
        self.win.sb_click(e.position().toPoint())


class V5Pages:
    # ================================================================== Characters
    def _characters_page(self):
        from .app import page
        w, v = page("Characters", "Save a person once – look, outfits, LoRAs, trigger words and reference images – "
                                  "and drop them into any prompt, region or storyboard the same way every time.")
        split = QSplitter(Qt.Horizontal)
        lc = Card("Cast")
        self.cr_list = QListWidget(); self.cr_list.setIconSize(QSize(40, 40)); self.cr_list.currentRowChanged.connect(self._cr_selected)
        lc.add(self.cr_list, 1)
        lc.add(hrow(button("＋ New", self.cr_new, "ghost"), None, ConfirmButton("🗑 Delete", self.cr_delete, "Confirm delete")))
        split.addWidget(lc)
        ec = Card("Character")
        self.cr_name = QLineEdit(); self.cr_name.setPlaceholderText(tr("Name, e.g. Mika"))
        self.cr_trig = QLineEdit(); self.cr_trig.setPlaceholderText(tr("Trigger words (from the LoRA), e.g. mika_pm"))
        self.cr_app = QPlainTextEdit(); self.cr_app.setFixedHeight(54)
        self.cr_app.setPlaceholderText(tr("Look (default tags), e.g. adult woman, short silver hair, green eyes, freckles"))
        ec.add(hrow(label("Name"), self.cr_name, label("Triggers"), self.cr_trig)); ec.add(self.cr_app)
        self.cr_ts_target = QComboBox()
        for pid, p in sorted(self.profiles.items(), key=lambda kv: kv[1].get("name", "")):
            self.cr_ts_target.addItem(p.get("name", pid), pid)
        self.cr_ts_tags = QLineEdit(); self.cr_ts_tags.setPlaceholderText(tr("Tags for this target model (empty = use the look above)"))
        self.cr_ts_target.currentIndexChanged.connect(self._cr_ts_show)
        self.cr_ts_tags.textEdited.connect(self._cr_ts_edit)
        ec.add(hrow(label("Per model"), self.cr_ts_target, self.cr_ts_tags))
        self.cr_outfits = QListWidget(); self.cr_outfits.setFixedHeight(104); self.cr_outfits.currentRowChanged.connect(self._cr_outfit_sel)
        self.cr_of_name, self.cr_of_tags = QLineEdit(), QLineEdit()
        self.cr_of_name.setPlaceholderText(tr("Outfit name")); self.cr_of_tags.setPlaceholderText(tr("Outfit tags, e.g. cream knit sweater, jeans"))
        ec.add(label("Outfits", "groupLabel")); ec.add(self.cr_outfits)
        ec.add(hrow(self.cr_of_name, self.cr_of_tags, button("＋", self.cr_outfit_add, "ghost", "Add / update outfit"),
                    button("−", self.cr_outfit_del, "ghost", "Remove outfit")))
        self.cr_loras = QListWidget(); self.cr_loras.setFixedHeight(84)
        self.cr_lo_name = QComboBox(); self.cr_lo_name.setEditable(True); self.cr_lo_name.setMinimumWidth(200)
        self.cr_lo_w = QDoubleSpinBox(); self.cr_lo_w.setRange(-2, 2); self.cr_lo_w.setSingleStep(0.05); self.cr_lo_w.setValue(0.8)
        ec.add(label("LoRAs", "groupLabel")); ec.add(self.cr_loras)
        ec.add(hrow(self.cr_lo_name, label("Weight"), self.cr_lo_w, button("＋", self.cr_lora_add, "ghost"),
                    button("−", lambda: self._cr_list_del(self.cr_loras), "ghost")))
        self.cr_refs = QListWidget(); self.cr_refs.setViewMode(QListWidget.IconMode); self.cr_refs.setIconSize(QSize(72, 72))
        self.cr_refs.setFixedHeight(96); self.cr_refs.setMovement(QListWidget.Static)
        self.cr_use_ref = QCheckBox(tr("Use as reference (IP-Adapter)"))
        self.cr_use_ref.setToolTip(tr("Send the first reference image with every prompt that uses this character – only when Forge/ComfyUI has IP-Adapter; otherwise skipped"))
        self.cr_ref_w = QDoubleSpinBox(); self.cr_ref_w.setRange(0.1, 1.5); self.cr_ref_w.setSingleStep(0.05); self.cr_ref_w.setValue(0.7)
        ec.add(label("Reference images / face", "groupLabel")); ec.add(self.cr_refs)
        ec.add(hrow(button("📂 Add…", self.cr_ref_add, "ghost"), button("🗂 From gallery", self.cr_ref_from_gallery, "ghost"),
                    button("−", lambda: self._cr_list_del(self.cr_refs), "ghost"), None, self.cr_use_ref, self.cr_ref_w))
        self.cr_autotag = QCheckBox(tr("Look for this character when auto-tagging the Gallery")); self.cr_autotag.setChecked(True)
        ec.add(self.cr_autotag)
        ec.add(hrow(button("💾 Save character", self.cr_save, "primary"), None))
        split.addWidget(ec)
        uc = Card("Use")
        self.cr_use_outfit = QComboBox()
        self.cr_use_target = QComboBox()
        for key, name in (("create", "Create prompt"), ("work", "Refine working prompt"),
                          ("region", "New region (Inpaint & Regions)"), ("copy", "Clipboard")):
            self.cr_use_target.addItem(tr(name), key)
        self.cr_preview = QPlainTextEdit(); self.cr_preview.setReadOnly(True); self.cr_preview.setFixedHeight(90)
        self.cr_use_outfit.currentIndexChanged.connect(lambda _i: self._cr_preview())
        uc.add(hrow(label("Outfit"), self.cr_use_outfit)); uc.add(hrow(label("Into"), self.cr_use_target))
        uc.add(self.cr_preview)
        uc.add(hrow(button("➕ Insert", self.cr_insert, "primary"), button("🖼 Portrait", self.cr_portrait, "ghost",
                                                                        "Generate a reference portrait of this character")))
        self.cr_ref_status = label(tr("Reference support: not checked"), "hint", wrap=True)
        uc.add(self.cr_ref_status); uc.add(hrow(button("🔎 Check reference support", self.cr_check_ref, "ghost"), None))
        uc.add(label("Gallery auto-tagging", "groupLabel"))
        self.cr_autotag_on = QCheckBox(tr("Auto-tag new images (vision model, background)"))
        self.cr_autotag_on.setChecked(bool(self.store.get("char_autotag", False)))
        self.cr_autotag_on.toggled.connect(lambda on: self.store.set("char_autotag", bool(on)))
        uc.add(self.cr_autotag_on)
        self.cr_tag_status = label("", "hint", wrap=True); uc.add(self.cr_tag_status)
        uc.add(hrow(button("🏷 Tag recent images now", lambda: self.autotag_paths([p for p, _m in self.gallery.items()[:30]], force=True), "ghost"), None))
        uc.lay.addStretch(1)
        split.addWidget(uc)
        split.setSizes([220, 620, 360])
        v.addWidget(split, 1)
        self.cr_id, self._cr_extra = None, ch.extra({})
        self.cr_load()
        return w

    def cr_load(self, select=None):
        self.cr_list.blockSignals(True); self.cr_list.clear()
        for c in self.store.characters():
            refs = ch.references(c)
            it = QListWidgetItem(QIcon(_thumb(refs[0], 40)) if refs else QIcon(), c["name"]); it.setData(Qt.UserRole, c["id"])
            self.cr_list.addItem(it)
        self.cr_list.blockSignals(False)
        for i in range(self.cr_list.count()):
            if self.cr_list.item(i).data(Qt.UserRole) == select:
                self.cr_list.setCurrentRow(i)

    def _cr_cur(self):
        return self.store.character(self.cr_id) if self.cr_id else None

    def _cr_selected(self, row):
        it = self.cr_list.item(row)
        c = self.store.character(it.data(Qt.UserRole)) if it else None
        if not c:
            return
        self.cr_id = c["id"]; ex = self._cr_extra = ch.extra(c)
        self.cr_name.setText(c["name"]); self.cr_trig.setText(ex["triggers"]); self.cr_app.setPlainText(c["appearance"])
        self.cr_outfits.clear()
        for o in ch.outfits(c):
            it2 = QListWidgetItem(f"{o['name']} — {o['tags']}"); it2.setData(Qt.UserRole, o); self.cr_outfits.addItem(it2)
        self.cr_loras.clear()
        for n, wt in ch.loras(c):
            it2 = QListWidgetItem(f"{n} : {wt:g}"); it2.setData(Qt.UserRole, {"name": n, "weight": wt}); self.cr_loras.addItem(it2)
        self.cr_refs.clear()
        for r in ch.references(c):
            it2 = QListWidgetItem(QIcon(_thumb(r, 72)), ""); it2.setData(Qt.UserRole, r); it2.setToolTip(r); self.cr_refs.addItem(it2)
        self.cr_use_ref.setChecked(bool(ex["use_reference"])); self.cr_ref_w.setValue(float(ex["ref_weight"]))
        self.cr_autotag.setChecked(bool(ex["autotag"]))
        self._cr_ts_show(); self._cr_fill_outfits(c); self._cr_preview()

    def _cr_fill_outfits(self, c):
        self.cr_use_outfit.blockSignals(True); self.cr_use_outfit.clear()
        self.cr_use_outfit.addItem(tr("(no outfit)"), "(none)")
        for o in ch.outfits(c):
            self.cr_use_outfit.addItem(o["name"], o["name"])
        self.cr_use_outfit.setCurrentIndex(1 if self.cr_use_outfit.count() > 1 else 0)
        self.cr_use_outfit.blockSignals(False)

    def _cr_ts_show(self, *_):
        self.cr_ts_tags.setText(self._cr_extra["tagsets"].get(self.cr_ts_target.currentData() or "", ""))

    def _cr_ts_edit(self, t):
        key = self.cr_ts_target.currentData()
        if key:
            if t.strip():
                self._cr_extra["tagsets"][key] = t
            else:
                self._cr_extra["tagsets"].pop(key, None)

    def _cr_outfit_sel(self, row):
        it = self.cr_outfits.item(row)
        if it:
            o = it.data(Qt.UserRole); self.cr_of_name.setText(o["name"]); self.cr_of_tags.setText(o["tags"])

    def cr_outfit_add(self):
        n, t = self.cr_of_name.text().strip(), self.cr_of_tags.text().strip()
        if not n or not t:
            self.notify(tr("Give the outfit a name and some tags"), error=True); return
        for i in range(self.cr_outfits.count()):
            if self.cr_outfits.item(i).data(Qt.UserRole)["name"].lower() == n.lower():
                self.cr_outfits.takeItem(i); break
        it = QListWidgetItem(f"{n} — {t}"); it.setData(Qt.UserRole, {"name": n, "tags": t}); self.cr_outfits.addItem(it)
        self.cr_of_name.clear(); self.cr_of_tags.clear()

    def cr_outfit_del(self):
        self._cr_list_del(self.cr_outfits)

    def _cr_list_del(self, lst):
        r = lst.currentRow()
        if r >= 0:
            lst.takeItem(r)

    def cr_lora_add(self):
        n = self.cr_lo_name.currentText().strip()
        if n:
            it = QListWidgetItem(f"{n} : {self.cr_lo_w.value():g}"); it.setData(Qt.UserRole, {"name": n, "weight": self.cr_lo_w.value()})
            self.cr_loras.addItem(it)

    def _cr_add_ref(self, path):
        if path and os.path.exists(path):
            it = QListWidgetItem(QIcon(_thumb(path, 72)), ""); it.setData(Qt.UserRole, path); it.setToolTip(path); self.cr_refs.addItem(it)

    def cr_ref_add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, tr("Reference images"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        for f in fs:
            self._cr_add_ref(f)

    def cr_ref_from_gallery(self):
        p, _m = self._gal_cur() if hasattr(self, "gal_list") else (None, {})
        p = p or (self.gallery.items()[0][0] if self.gallery.items() else None)
        if not p:
            self.notify(tr("No gallery image selected"), error=True); return
        self._cr_add_ref(p)

    def cr_new(self):
        self.cr_id, self._cr_extra = None, ch.extra({})
        for x in (self.cr_name, self.cr_trig, self.cr_of_name, self.cr_of_tags, self.cr_ts_tags):
            x.clear()
        self.cr_app.clear()
        for lst in (self.cr_outfits, self.cr_loras, self.cr_refs):
            lst.clear()
        self.cr_use_ref.setChecked(False); self.cr_list.clearSelection(); self.cr_use_outfit.clear(); self.cr_preview.clear()

    def cr_data(self):
        ex = dict(self._cr_extra)
        ex["triggers"] = self.cr_trig.text().strip()
        ex["outfits"] = [self.cr_outfits.item(i).data(Qt.UserRole) for i in range(self.cr_outfits.count())]
        los = [self.cr_loras.item(i).data(Qt.UserRole) for i in range(self.cr_loras.count())]
        refs = [self.cr_refs.item(i).data(Qt.UserRole) for i in range(self.cr_refs.count())]
        ex.update(loras=los[1:], refs=refs[1:], use_reference=self.cr_use_ref.isChecked(), ref_weight=self.cr_ref_w.value(),
                  autotag=self.cr_autotag.isChecked())
        return {"name": self.cr_name.text().strip(), "appearance": self.cr_app.toPlainText().strip(),
                "outfit": ex["outfits"][0]["tags"] if ex["outfits"] else "",
                "lora": los[0]["name"] if los else "", "lora_weight": los[0]["weight"] if los else 0.8,
                "ref_image": refs[0] if refs else "", "notes": (self._cr_cur() or {}).get("notes", ""), "extra": json.dumps(ex)}

    def cr_save(self):
        try:
            self.cr_id = self.store.save_character(self.cr_data(), self.cr_id)
        except ValueError as e:
            self.notify(tr(str(e)), error=True); return None
        self.cr_load(self.cr_id)
        if hasattr(self, "load_presets"):
            self.load_presets()
        if hasattr(self, "sb_cast"):
            self.sb_refresh_cast()
        if hasattr(self, "tr_char"):
            self.tr_refresh_chars()
        self.notify(tr("Character saved")); self.home_refresh()
        return self.cr_id

    def cr_delete(self):
        if self.cr_id:
            self.store.delete_character(self.cr_id); self.cr_new(); self.cr_load()
            if hasattr(self, "load_presets"):
                self.load_presets()

    def _cr_preview(self):
        c = self._cr_cur()
        self.cr_preview.setPlainText(ch.character_text(c, self.cr_use_outfit.currentData(), self.profile) if c else "")

    def insert_character(self, char, outfit=None, target="create"):
        """Put a character (+outfit) into a prompt or a new region. Returns the text inserted."""
        text = ch.character_text(char, outfit, self.profile)
        if target == "create" and hasattr(self, "c_prompt"):
            self.c_prompt.setPlainText(ch.insert(self.c_prompt.toPlainText(), char, outfit, self.profile)); self.go("Create")
        elif target == "work" and hasattr(self, "work"):
            self.set_work(ch.insert(self.work.toPlainText(), char, outfit, self.profile), "character"); self.go("Refine")
        elif target == "region" and hasattr(self, "ip_canvas"):
            n = len(self.ip_canvas.regions)
            r = ch.region(char, outfit, self.profile, x=0.05 + 0.5 * (n % 2), w=0.45)
            self.ip_canvas.add_region(r["prompt"], (r["x"], r["y"], r["w"], r["h"]), r["weight"])
            los = " ".join(f"<lora:{a}:{b:g}>" for a, b in ch.loras(char))
            if los and los not in self.ip_prompt.toPlainText():
                self.ip_prompt.setPlainText((self.ip_prompt.toPlainText().strip() + " " + los).strip())
            self.go("Inpaint & Regions")
        else:
            from .app import copy
            copy(text)
        self.notify(tr("Inserted") + f" · {char['name']}")
        return text

    def cr_insert(self):
        c = self._cr_cur()
        if not c:
            self.notify(tr("Pick or save a character first"), error=True); return None
        return self.insert_character(c, self.cr_use_outfit.currentData(), self.cr_use_target.currentData())

    def character_menu(self, target):
        """QMenu of characters × outfits that inserts into `target` (Create / Regions buttons)."""
        m = QMenu(self)
        cs = self.store.characters()
        if not cs:
            a = m.addAction(tr("No characters yet – open Characters")); a.triggered.connect(lambda: self.go("Characters"))
        for c in cs:
            outs = ch.outfits(c)
            if not outs:
                a = m.addAction(c["name"]); a.triggered.connect(lambda _=False, c=c: self.insert_character(c, None, target))
                continue
            sub = m.addMenu(c["name"])
            for o in outs:
                a = sub.addAction(o["name"]); a.triggered.connect(lambda _=False, c=c, o=o["name"]: self.insert_character(c, o, target))
        return m

    def show_character_menu(self, target, anchor=None):
        m = self.character_menu(target)
        from PySide6.QtGui import QCursor
        m.popup(anchor.mapToGlobal(anchor.rect().bottomLeft()) if anchor else QCursor.pos())
        return m

    def cr_portrait(self):
        c = self._cr_cur()
        if not c:
            return None
        prompt = ch.character_text(c, self.cr_use_outfit.currentData(), self.profile) + ", upper body portrait, looking at viewer, simple background"
        job = self.generate_image(prompt, self._default_negative(), tag="portrait")
        if job:
            self._job_callbacks = getattr(self, "_job_callbacks", {})
            self._job_callbacks.setdefault(job.id, []).append(lambda j: (self._cr_add_ref(j.paths[0]), self.notify(tr("Portrait added – Save to keep it"))))
        return job

    def reference_support(self, force=False):
        b = self.image_backend()
        if not b:
            return None, "no image backend"
        cache = self.__dict__.setdefault("_ref_support", {})
        if force or b.url not in cache:
            cache[b.url] = ch.detect_reference_support(b)
        return cache[b.url]

    def cr_check_ref(self):
        kind, info = self.reference_support(force=True)
        self.cr_ref_status.setText(tr("Reference support") + ": " + (f"✓ {kind} {info}".strip() if kind else f"✗ {info} – references are skipped"))
        return kind

    def apply_character_reference(self, job):
        """From make_job: if a character in the prompt wants its reference image used, add it when supported."""
        try:
            cs = [c for c in self.store.characters() if ch.extra(c)["use_reference"] and ch.references(c)]
        except Exception:
            return None
        if not cs:
            return None
        hits = set(ch.from_prompt(job.prompt, cs)) | {c["name"] for c in cs if c["name"].lower() in job.prompt.lower()}
        c = next((c for c in cs if c["name"] in hits), None)
        if not c:
            return None
        kind, model = self.reference_support()
        if not kind:
            job.reference_skipped = model
            return None
        with open(ch.references(c)[0], "rb") as f:
            job.reference = {"image": f.read(), "model": model, "weight": float(ch.extra(c)["ref_weight"]), "character": c["name"]}
        return job.reference

    # ---------------------------------------------------------------- gallery auto-tagging
    def _meta_update(self, path, names, ai=False):
        meta_p = path[:-4] + ".json"
        try:
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
        meta["characters"] = sorted(set(meta.get("characters", [])) | set(names))
        if ai:
            meta["characters_ai"] = True
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1, ensure_ascii=False)
        return meta["characters"]

    def tag_from_prompt(self, path):
        """Free tagging (always on): characters whose trigger word / LoRA is in the image's prompt."""
        try:
            with open(path[:-4] + ".json", encoding="utf-8") as f:
                prompt = json.load(f).get("prompt", "")
        except (OSError, ValueError):
            return []
        hits = ch.from_prompt(prompt, self.store.characters())
        if hits:
            self._meta_update(path, hits)
        return hits

    def autotag_paths(self, paths, force=False):
        if not (force or self.store.get("char_autotag", False)):
            return 0
        chars = [c for c in self.store.characters() if ch.extra(c)["autotag"]]
        if not chars:
            if force:
                self.notify(tr("Save a character first"), error=True)
            return 0
        q = self.__dict__.setdefault("_tag_queue", [])
        q.extend(p for p in paths if p not in q)
        n = len(q)
        self._autotag_next()
        return n

    def _autotag_next(self):
        w = getattr(self, "_tag_worker", None)
        if w is not None and w.isRunning():
            return
        q = self.__dict__.get("_tag_queue", [])
        if not q:
            if hasattr(self, "cr_tag_status"):
                self.cr_tag_status.setText(tr("Auto-tagging idle"))
            return
        path = q.pop(0)
        model = (self.vision_model.currentText().strip() if hasattr(self, "vision_model") else "") or self.model.currentText()
        if not model:
            self._tag_queue = []
            if hasattr(self, "cr_tag_status"):
                self.cr_tag_status.setText(tr("No vision model – pick one in Settings → AI"))
            return
        chars = [c for c in self.store.characters() if ch.extra(c)["autotag"]]
        img = QImage(path)
        if img.isNull():
            QTimer.singleShot(0, self._autotag_next); return
        png = sketch.png_bytes(img.scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if hasattr(self, "cr_tag_status"):
            self.cr_tag_status.setText(tr("Tagging") + f" {os.path.basename(path)} · {len(q)} " + tr("left"))
        self._tag_worker = ChatWorker(self.provider, model, ch.tag_messages(png, chars), 0.1, True)
        self._tag_worker.done.connect(lambda t, p=path, cs=chars: (self._meta_update(p, ch.parse_tags(t, cs), True),
                                                                    QTimer.singleShot(0, self._autotag_next)))
        self._tag_worker.failed.connect(self._autotag_failed)
        self._tag_worker.start()

    def _autotag_failed(self, e):
        self._tag_queue = []
        if hasattr(self, "cr_tag_status"):
            self.cr_tag_status.setText("⚠️ " + e[:120])

    def _v5_job_done(self, job):
        """Hook from _gen_done: tag the new images (prompt match always, vision model when opted in)."""
        paths = getattr(job, "paths", []) or []
        for p in paths:
            self.tag_from_prompt(p)
        if getattr(job, "tag", "") != "sketch":
            self.autotag_paths(paths)

    # ================================================================== Storyboard
    def _storyboard_page(self):
        from .app import page
        w, v = page("Storyboard", "Write a short story – the AI plans the panels using your Characters, PromptMaker "
                                  "generates each one, then lay them out as a comic page with speech bubbles.")
        top = Card()
        self.sb_title = QLineEdit(); self.sb_title.setPlaceholderText(tr("Title"))
        self.sb_story = QPlainTextEdit(); self.sb_story.setFixedHeight(64)
        self.sb_story.setPlaceholderText(tr("Story or idea, e.g. Mika finds a lost kitten on a rainy evening and takes it to the café"))
        self.sb_n = QSpinBox(); self.sb_n.setRange(1, 24); self.sb_n.setValue(4)
        self.sb_style = QLineEdit(); self.sb_style.setPlaceholderText(tr("Style for every panel, e.g. manga, clean lineart, soft colours"))
        self.sb_cast = QListWidget(); self.sb_cast.setFlow(QListWidget.LeftToRight); self.sb_cast.setFixedHeight(36)
        top.add(hrow(label("Title"), self.sb_title, label("Panels"), self.sb_n, label("Style"), self.sb_style))
        top.add(self.sb_story)
        top.add(hrow(label("Cast"), self.sb_cast, button("🧠 Plan panels with AI", self.sb_plan, "primary"),
                     button("＋ Blank panel", self.sb_add_panel, "ghost")))
        v.addWidget(top)
        split = QSplitter(Qt.Horizontal)
        pc = Card("Panels")
        self.sb_list = QListWidget(); self.sb_list.setIconSize(QSize(56, 56)); self.sb_list.currentRowChanged.connect(self._sb_selected)
        pc.add(self.sb_list, 1)
        pc.add(hrow(button("▲", lambda: self.sb_move(-1), "ghost", "Move up"), button("▼", lambda: self.sb_move(1), "ghost", "Move down"),
                    button("−", self.sb_del_panel, "ghost", "Remove panel"), None))
        pc.add(button("🖼 Generate all", self.sb_generate_all, "primary"))
        split.addWidget(pc)
        ed = Card("Panel")
        self.sb_shot = QComboBox(); self.sb_shot.setEditable(True); self.sb_shot.addItems(sbm.SHOTS)
        self.sb_chars = QLineEdit(); self.sb_chars.setPlaceholderText(tr("Characters, comma separated"))
        self.sb_action, self.sb_setting = QLineEdit(), QLineEdit()
        self.sb_action.setPlaceholderText(tr("Action – what we see")); self.sb_setting.setPlaceholderText(tr("Setting"))
        self.sb_dialogue = QPlainTextEdit(); self.sb_dialogue.setFixedHeight(54); self.sb_dialogue.setPlaceholderText(tr("Dialogue, one line each:  Mika: Oh! Who are you?"))
        self.sb_caption = QLineEdit(); self.sb_caption.setPlaceholderText(tr("Caption / narration (optional)"))
        self.sb_prompt = QPlainTextEdit(); self.sb_prompt.setFixedHeight(60); self.sb_prompt.setPlaceholderText(tr("Image prompt (built from the fields – edit freely)"))
        ed.add(hrow(label("Shot"), self.sb_shot, label("Who"), self.sb_chars))
        ed.add(self.sb_action); ed.add(self.sb_setting); ed.add(self.sb_dialogue); ed.add(self.sb_caption)
        ed.add(hrow(label("Prompt", "groupLabel"), None, button("↻ Rebuild", self.sb_rebuild_prompt, "ghost")))
        ed.add(self.sb_prompt)
        ed.add(hrow(button("✓ Apply", self.sb_apply, "ghost"), button("💬 Bubbles from dialogue", self.sb_rebuild_bubbles, "ghost"),
                    None, button("🖼 Generate panel", self.sb_generate_panel, "primary")))
        self.sb_bubbles = QListWidget(); self.sb_bubbles.setFixedHeight(60); self.sb_bubbles.currentRowChanged.connect(self._sb_bubble_sel)
        self.sb_b_text = QLineEdit(); self.sb_b_text.textEdited.connect(self._sb_bubble_edit)
        self.sb_bx, self.sb_by = QSlider(Qt.Horizontal), QSlider(Qt.Horizontal)
        for s in (self.sb_bx, self.sb_by):
            s.setRange(0, 90); s.valueChanged.connect(self._sb_bubble_edit)
        ed.add(label("Speech bubbles & captions", "groupLabel")); ed.add(self.sb_bubbles)
        ed.add(hrow(self.sb_b_text, label("x"), self.sb_bx, label("y"), self.sb_by))
        ed.add(hrow(button("＋ Speech", lambda: self.sb_add_bubble("speech"), "ghost"), button("＋ Caption", lambda: self.sb_add_bubble("caption"), "ghost"),
                    button("−", self.sb_del_bubble, "ghost"), None))
        split.addWidget(ed)
        lc = Card("Page")
        self.sb_layout = QComboBox(); self.sb_layout.addItems(list(sbm.LAYOUTS)); self.sb_layout.setCurrentText("4 grid")
        self.sb_size = QComboBox(); self.sb_size.addItems(list(sbm.PAGE_SIZES))
        self.sb_font = QComboBox(); self.sb_font.setEditable(True); self.sb_font.addItems(sbm.FONTS)
        self.sb_fsize = QSpinBox(); self.sb_fsize.setRange(10, 72); self.sb_fsize.setValue(26)
        self.sb_page = QSpinBox(); self.sb_page.setRange(1, 1); self.sb_page.setPrefix(tr("Page") + " ")
        for wdg in (self.sb_layout, self.sb_size, self.sb_font):
            wdg.currentTextChanged.connect(self._sb_page_opts)
        for wdg in (self.sb_fsize, self.sb_page):
            wdg.valueChanged.connect(self._sb_page_opts)
        lc.add(hrow(self.sb_layout, self.sb_size, self.sb_page))
        lc.add(hrow(label("Font"), self.sb_font, self.sb_fsize))
        self.sb_view = PanelPreview(self); lc.add(self.sb_view, 1)
        lc.add(label(tr("Drag a Gallery thumbnail onto a panel to use it · click a panel to edit it"), "hint", wrap=True))
        lc.add(hrow(button("💾 Save", lambda: self.sb_save_project(), "ghost"), button("📂 Open", lambda: self.sb_open_project(), "ghost"), None,
                    button("⬇ PNG", lambda: self.sb_export_png(), "ghost"), button("⬇ PDF", lambda: self.sb_export_pdf(), "primary")))
        split.addWidget(lc)
        split.setSizes([220, 440, 440])
        v.addWidget(split, 1)
        self.sb = sbm.new_storyboard(); self.sb_cur = -1
        self.sb_refresh_cast(); self.sb_refresh()
        return w

    def sb_refresh_cast(self):
        sel = {self.sb_cast.item(i).text() for i in range(self.sb_cast.count()) if self.sb_cast.item(i).checkState() == Qt.Checked}
        self.sb_cast.clear()
        for c in self.store.characters():
            it = QListWidgetItem(c["name"]); it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c["name"] in sel else Qt.Unchecked); self.sb_cast.addItem(it)

    def _sb_cast(self):
        names = {self.sb_cast.item(i).text() for i in range(self.sb_cast.count()) if self.sb_cast.item(i).checkState() == Qt.Checked}
        return [c for c in self.store.characters() if c["name"] in names]

    def _sb_chars_by_name(self):
        return {c["name"]: c for c in self.store.characters()}

    def sb_plan(self):
        story = self.sb_story.toPlainText().strip()
        if not story:
            self.notify(tr("Write the story first"), error=True); return False
        cast = self._sb_cast()
        self.sb["story"], self.sb["style"] = story, self.sb_style.text().strip()
        msgs = sbm.plan_messages(story, self.sb_n.value(), cast, self.profile, self.sb["style"])
        self.notify(tr("Planning panels…"))
        return self.run_ai(msgs, lambda _c: None, lambda t, cast=cast: self.sb_apply_plan(t, cast), json_mode=True, temperature=0.6)

    def sb_apply_plan(self, text, cast=()):
        title, panels = sbm.parse_plan(text, self.sb_n.value(), cast or self.store.characters())
        if not panels:
            self.notify(tr("The AI didn't return a usable plan – try again or add panels by hand"), error=True); return 0
        cbn = self._sb_chars_by_name()
        self.sb["style"] = self.sb_style.text().strip()
        for p in panels:
            p["prompt"] = sbm.panel_prompt(p, cbn, self.profile, self.sb["style"])
            p["bubbles"] = sbm.default_bubbles(p)
        self.sb["panels"] = panels
        if title and not self.sb_title.text().strip():
            self.sb_title.setText(title)
        self.sb_cur = 0; self.sb_refresh()
        self.notify(tr("Planned") + f" {len(panels)} " + tr("panels"))
        return len(panels)

    def sb_add_panel(self):
        self.sb["panels"].append(sbm.new_panel()); self.sb_cur = len(self.sb["panels"]) - 1; self.sb_refresh()

    def sb_del_panel(self):
        r = self.sb_list.currentRow()
        if 0 <= r < len(self.sb["panels"]):
            self.sb["panels"].pop(r); self.sb_cur = min(r, len(self.sb["panels"]) - 1); self.sb_refresh()

    def sb_move(self, d):
        r = self.sb_list.currentRow(); n = r + d
        ps = self.sb["panels"]
        if 0 <= r < len(ps) and 0 <= n < len(ps):
            ps[r], ps[n] = ps[n], ps[r]; self.sb_cur = n; self.sb_refresh()

    def sb_refresh(self):
        self.sb_list.blockSignals(True); self.sb_list.clear()
        for i, p in enumerate(self.sb["panels"]):
            it = QListWidgetItem(QIcon(_thumb(p.get("image"), 56)) if p.get("image") else QIcon(),
                                 f"{i + 1}. {p.get('shot', '')} · {(p.get('action') or '')[:40]}")
            self.sb_list.addItem(it)
        self.sb_list.blockSignals(False)
        self.sb_page.blockSignals(True); self.sb_page.setMaximum(max(1, len(sbm.pages(self.sb)))); self.sb_page.blockSignals(False)
        if 0 <= self.sb_cur < self.sb_list.count():
            self.sb_list.setCurrentRow(self.sb_cur); self._sb_selected(self.sb_cur)
        self.sb_render()

    def sb_render(self):
        if not hasattr(self, "sb_view"):
            return None
        img = sbm.render_page(self.sb, self.sb_page.value() - 1, scale=0.5)
        W = max(200, self.sb_view.width() - 8); H = max(240, self.sb_view.height() - 8)
        self.sb_view.setPixmap(QPixmap.fromImage(img).scaled(W, H, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return img

    def _sb_page_opts(self, *_):
        self.sb.update(layout=self.sb_layout.currentText(), page_size=self.sb_size.currentText(), font=self.sb_font.currentText(),
                       font_size=self.sb_fsize.value())
        self.sb_page.blockSignals(True); self.sb_page.setMaximum(max(1, len(sbm.pages(self.sb)))); self.sb_page.blockSignals(False)
        self.sb_render()

    def _sb_selected(self, row):
        if not (0 <= row < len(self.sb["panels"])):
            return
        self.sb_cur = row; p = self.sb["panels"][row]
        self.sb_shot.setCurrentText(p.get("shot", "")); self.sb_chars.setText(", ".join(p.get("characters", [])))
        self.sb_action.setText(p.get("action", "")); self.sb_setting.setText(p.get("setting", ""))
        self.sb_dialogue.setPlainText("\n".join((f"{d['speaker']}: " if d.get("speaker") else "") + d["text"] for d in p.get("dialogue", [])))
        self.sb_caption.setText(p.get("caption", "")); self.sb_prompt.setPlainText(p.get("prompt", ""))
        self._sb_bubbles_show()
        per = len(sbm.LAYOUTS.get(self.sb["layout"], sbm.LAYOUTS["4 grid"]))
        if self.sb_page.value() != row // per + 1:
            self.sb_page.setValue(row // per + 1)

    def _sb_panel(self):
        return self.sb["panels"][self.sb_cur] if 0 <= self.sb_cur < len(self.sb["panels"]) else None

    def sb_apply(self):
        p = self._sb_panel()
        if p is None:
            return None
        p["shot"] = self.sb_shot.currentText(); p["characters"] = [x.strip() for x in self.sb_chars.text().split(",") if x.strip()]
        p["action"], p["setting"], p["caption"] = self.sb_action.text(), self.sb_setting.text(), self.sb_caption.text()
        dl = []
        for line in self.sb_dialogue.toPlainText().splitlines():
            if line.strip():
                sp, _, tx = line.partition(":")
                dl.append({"speaker": sp.strip(), "text": tx.strip()} if tx.strip() else {"speaker": "", "text": line.strip()})
        p["dialogue"] = dl
        p["prompt"] = self.sb_prompt.toPlainText().strip() or sbm.panel_prompt(p, self._sb_chars_by_name(), self.profile, self.sb.get("style", ""))
        self.sb_refresh()
        return p

    def sb_rebuild_prompt(self):
        if self._sb_panel() is not None:
            self.sb_prompt.clear(); self.sb_apply()

    def sb_rebuild_bubbles(self):
        p = self.sb_apply()
        if p is not None:
            p["bubbles"] = sbm.default_bubbles(p); self._sb_bubbles_show(); self.sb_render()

    def _sb_bubbles_show(self):
        p = self._sb_panel(); self.sb_bubbles.clear()
        for b in (p or {}).get("bubbles", []):
            self.sb_bubbles.addItem(("💬 " if b.get("kind") != "caption" else "▭ ") + b.get("text", ""))

    def _sb_bubble_sel(self, row):
        p = self._sb_panel()
        if p and 0 <= row < len(p["bubbles"]):
            b = p["bubbles"][row]
            for wdg in (self.sb_b_text, self.sb_bx, self.sb_by):
                wdg.blockSignals(True)
            self.sb_b_text.setText(b["text"]); self.sb_bx.setValue(int(b["x"] * 100)); self.sb_by.setValue(int(b["y"] * 100))
            for wdg in (self.sb_b_text, self.sb_bx, self.sb_by):
                wdg.blockSignals(False)

    def _sb_bubble_edit(self, *_):
        p = self._sb_panel(); r = self.sb_bubbles.currentRow()
        if p and 0 <= r < len(p["bubbles"]):
            b = p["bubbles"][r]; b["text"] = self.sb_b_text.text(); b["x"] = self.sb_bx.value() / 100; b["y"] = self.sb_by.value() / 100
            self.sb_bubbles.item(r).setText(("💬 " if b.get("kind") != "caption" else "▭ ") + b["text"]); self.sb_render()

    def sb_add_bubble(self, kind):
        p = self._sb_panel()
        if p is None:
            return
        p["bubbles"].append({"kind": kind, "text": tr("Text"), "x": 0.05, "y": 0.05 if kind == "speech" else 0.84,
                             "w": 0.45 if kind == "speech" else 0.9, "h": 0.16 if kind == "speech" else 0.12})
        self._sb_bubbles_show(); self.sb_bubbles.setCurrentRow(len(p["bubbles"]) - 1); self.sb_render()

    def sb_del_bubble(self):
        p = self._sb_panel(); r = self.sb_bubbles.currentRow()
        if p and 0 <= r < len(p["bubbles"]):
            p["bubbles"].pop(r); self._sb_bubbles_show(); self.sb_render()

    def _sb_panel_at(self, pos):
        pm = self.sb_view.pixmap()
        if pm is None or pm.isNull():
            return -1
        ox, oy = (self.sb_view.width() - pm.width()) / 2, (self.sb_view.height() - pm.height()) / 2
        W, H = sbm.PAGE_SIZES.get(self.sb["page_size"], sbm.PAGE_SIZES["A4 portrait"])
        fx, fy = (pos.x() - ox) / pm.width() * W, (pos.y() - oy) / pm.height() * H
        per = len(sbm.LAYOUTS.get(self.sb["layout"], sbm.LAYOUTS["4 grid"]))
        for i, (x, y, w, h) in enumerate(sbm.layout_rects(self.sb["layout"], (W, H), 40, self.sb.get("gutter", 18))):
            if x <= fx <= x + w and y <= fy <= y + h:
                return (self.sb_page.value() - 1) * per + i
        return -1

    def sb_drop(self, path, pos):
        return self.sb_set_image(self._sb_panel_at(pos), path)

    def sb_set_image(self, i, path):
        if i < 0 or not path or not os.path.exists(path):
            return False
        while i >= len(self.sb["panels"]):
            self.sb["panels"].append(sbm.new_panel())
        self.sb["panels"][i]["image"] = path; self.sb_cur = i; self.sb_refresh()
        return True

    def sb_click(self, pos):
        i = self._sb_panel_at(pos)
        if 0 <= i < len(self.sb["panels"]):
            self.sb_cur = i; self.sb_list.setCurrentRow(i)

    def sb_generate_panel(self, i=None):
        if i is None or i is False:
            self.sb_apply(); i = self.sb_cur
        if not (0 <= i < len(self.sb["panels"])):
            return None
        p = self.sb["panels"][i]
        prompt = p.get("prompt") or sbm.panel_prompt(p, self._sb_chars_by_name(), self.profile, self.sb.get("style", ""))
        job = self.generate_image(prompt, self._default_negative(), seed=p.get("seed"), tag="story", quiet=True)
        if job:
            self._job_callbacks = getattr(self, "_job_callbacks", {})
            self._job_callbacks.setdefault(job.id, []).append(lambda j, i=i: self._sb_job_done(i, j))
        return job

    def _sb_job_done(self, i, job):
        if 0 <= i < len(self.sb["panels"]) and getattr(job, "paths", None):
            self.sb["panels"][i]["image"] = job.paths[0]; self.sb["panels"][i]["seed"] = job.seed; self.sb_refresh()

    def sb_generate_all(self):
        jobs = [j for j in (self.sb_generate_panel(i) for i, p in enumerate(self.sb["panels"]) if not p.get("image")) if j]
        if jobs:
            self.notify(tr("Queued") + f" {len(jobs)} " + tr("panels"))
        return jobs

    def _sb_sync(self):
        self.sb["title"] = self.sb_title.text().strip() or self.sb.get("title") or "Untitled story"
        self.sb["story"] = self.sb_story.toPlainText(); self.sb["style"] = self.sb_style.text()

    def _sb_dir(self):
        d = os.path.join(self.data_dir, "storyboards"); os.makedirs(d, exist_ok=True)
        return d

    def sb_save_project(self, path=None):
        self._sb_sync()
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Save storyboard"), os.path.join(self._sb_dir(), self.sb["title"] + ".pmstory"), "Storyboard (*.pmstory)")
        if path:
            sbm.save_project(self.sb, path); self.notify(tr("Saved") + f" · {os.path.basename(path)}")
        return path

    def sb_open_project(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("Open storyboard"), self._sb_dir(), "Storyboard (*.pmstory)")
        if not path:
            return None
        try:
            self.sb = sbm.load_project(path)
        except (OSError, ValueError) as e:
            self.notify(str(e), error=True); return None
        self.sb_title.setText(self.sb.get("title", "")); self.sb_story.setPlainText(self.sb.get("story", "")); self.sb_style.setText(self.sb.get("style", ""))
        for wdg, key in ((self.sb_layout, "layout"), (self.sb_size, "page_size"), (self.sb_font, "font")):
            wdg.blockSignals(True); wdg.setCurrentText(self.sb.get(key, "")); wdg.blockSignals(False)
        self.sb_cur = 0 if self.sb["panels"] else -1; self.sb_refresh()
        return self.sb

    def sb_export_png(self, base=None):
        self._sb_sync()
        if not base:
            base, _ = QFileDialog.getSaveFileName(self, tr("Export PNG"), os.path.join(self._sb_dir(), self.sb["title"] + ".png"), "PNG (*.png)")
            base = base[:-4] if base.lower().endswith(".png") else base
        if base:
            out = sbm.export_png(self.sb, base); self.notify(tr("Exported") + f" {len(out)} PNG"); return out
        return []

    def sb_export_pdf(self, path=None):
        self._sb_sync()
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export PDF"), os.path.join(self._sb_dir(), self.sb["title"] + ".pdf"), "PDF (*.pdf)")
        if path:
            sbm.export_pdf(self.sb, path); self.notify(tr("Exported") + " PDF")
        return path

    # ================================================================== Live sketch
    def _sketch_page(self):
        from .app import page
        w, v = page("Live sketch", "Block in shapes and colours – the image updates as you draw (fast img2img, or "
                                   "ControlNet scribble when installed).")
        split = QSplitter(Qt.Horizontal)
        cc = Card("Sketch")
        self.sk_canvas = sketch.SketchCanvas(640, 640)
        tools = FlowLayout(spacing=6)
        for col in sketch.PALETTE:
            b = QPushButton(); b.setFixedSize(24, 24); b.setCursor(Qt.PointingHandCursor); b.setToolTip(col); b.setObjectName("swatch")
            b.setStyleSheet(f"QPushButton#swatch {{ background:{col}; border:1px solid #888; border-radius:12px; padding:0; }}")
            b.clicked.connect(lambda _=False, c=col: self.sk_color(c)); tools.addWidget(b)
        tw = QWidget(); tw.setLayout(tools); cc.add(tw)
        self.sk_size = QSpinBox(); self.sk_size.setRange(2, 160); self.sk_size.setValue(14); self.sk_size.setSuffix(" px")
        self.sk_size.valueChanged.connect(lambda n: setattr(self.sk_canvas, "size", n))
        self.sk_eraser = QCheckBox(tr("Eraser")); self.sk_eraser.toggled.connect(lambda on: setattr(self.sk_canvas, "eraser", on))
        row2 = QWidget(); fl2 = FlowLayout(row2, spacing=6)  # wraps next to the inspector instead of clipping
        for x in (label("Brush"), self.sk_size, self.sk_eraser, button("↶ Undo", self.sk_canvas.undo, "ghost"),
                  button("🗂 Last image", self.sk_load_last, "ghost"), button("📂 Open", self.sk_open, "ghost", "Draw over an image"),
                  ConfirmButton("Clear", self.sk_canvas.clear, "Confirm clear")):
            fl2.addWidget(x)
        cc.add(row2)
        cc.add(self.sk_canvas, 1)
        split.addWidget(cc)
        rc = Card("Result")
        self.sk_prompt = QLineEdit(); self.sk_prompt.setPlaceholderText(tr("What it is, e.g. adult woman in a red coat on a hill at sunset, watercolor"))
        self.sk_mode = QComboBox(); self.sk_mode.addItem(tr("img2img"), "img2img"); self.sk_mode.addItem(tr("ControlNet scribble"), "scribble")
        self.sk_speed = QComboBox(); self.sk_speed.addItems(list(sketch.SPEED_PRESETS))
        self.sk_speed.setCurrentText(self.store.get("sk_speed", "Lightning / Turbo (fast)"))
        self.sk_speed.currentTextChanged.connect(lambda t: self.store.set("sk_speed", t))
        self.sk_denoise = QSlider(Qt.Horizontal); self.sk_denoise.setRange(20, 95); self.sk_denoise.setValue(int(self.store.get("sk_denoise", 0.65) * 100))
        self.sk_denoise.setToolTip(tr("How much the AI may change your drawing"))
        self.sk_denoise.valueChanged.connect(lambda n: self.store.set("sk_denoise", n / 100))
        self.sk_live = QCheckBox(tr("Live – regenerate while drawing")); self.sk_live.setChecked(bool(self.store.get("sk_live", True)))
        self.sk_live.toggled.connect(lambda on: self.store.set("sk_live", bool(on)))
        self.sk_cn = QComboBox(); self.sk_cn.setMinimumWidth(150); self.sk_cn.setToolTip(tr("ControlNet scribble model"))
        rc.add(self.sk_prompt)
        rc.add(hrow(label("Mode"), self.sk_mode, self.sk_cn, button("⟳", self.sk_detect, "ghost", "Look for ControlNet scribble models")))
        rc.add(hrow(label("Speed"), self.sk_speed, label("Change"), self.sk_denoise))
        rc.add(hrow(self.sk_live, None, button("⚡ Generate now", self.sk_generate, "primary")))
        self.sk_result = QLabel(tr("Draw something – the result appears here")); self.sk_result.setAlignment(Qt.AlignCenter)
        self.sk_result.setMinimumSize(320, 320); self.sk_result.setObjectName("dropZone")
        rc.add(self.sk_result, 1)
        self.sk_status = label("", "hint", wrap=True); rc.add(self.sk_status)
        rc.add(hrow(button("💾 Save to Gallery", self.sk_save, "ghost"), button("🖌 Send to Inpaint", self.sk_to_inpaint, "ghost"),
                    button("✨ Send to Studio", self.sk_to_studio, "ghost", "Write a prompt from the result (Image to Prompt)"), None))
        split.addWidget(rc); split.setSizes([560, 520])
        v.addWidget(split, 1)
        self.sk_timer = QTimer(self); self.sk_timer.setSingleShot(True); self.sk_timer.setInterval(800); self.sk_timer.timeout.connect(self.sk_generate)
        self.sk_canvas.changed.connect(lambda: self.sk_live.isChecked() and self.sk_timer.start())
        self.sk_png, self.sk_job, self._sk_pending, self._sk_worker = None, None, False, None
        return w

    def sk_color(self, c):
        from PySide6.QtGui import QColor
        self.sk_canvas.color = QColor(c); self.sk_eraser.setChecked(False)

    def sk_load_last(self):
        it = self.gallery.items()
        if it:
            self.sk_canvas.load(it[0][0])

    def sk_open(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Draw over an image"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        if f:
            self.sk_canvas.load(f)

    def sk_detect(self):
        b = self.image_backend(); self.sk_cn.clear()
        try:
            ms = sketch.scribble_models(b.controlnet_models()) if b else []
        except Exception:
            ms = []
        self.sk_cn.addItems(ms)
        self.sk_status.setText((tr("Scribble models") + f": {len(ms)}") if ms else tr("No ControlNet scribble model found – using img2img"))
        if ms:
            self.sk_mode.setCurrentIndex(1)
        else:
            self.sk_mode.setCurrentIndex(0)
        return ms

    def sk_build_job(self):
        made = self.make_job(self.sk_prompt.text().strip() or "detailed illustration", self._default_negative(), None, "sketch")
        if not made:
            return None
        job, backend, wf = made
        mode = self.sk_mode.currentData() if self.sk_cn.currentText() else "img2img"
        sketch.apply_to_job(job, self.sk_canvas.png(), mode, self.sk_denoise.value() / 100, self.sk_cn.currentText(), self.sk_speed.currentText())
        return job, backend, wf

    def sk_generate(self):
        if self._sk_worker is not None and self._sk_worker.isRunning():
            self._sk_pending = True; return None
        if self.sk_canvas.is_blank():
            self.sk_status.setText(tr("Draw something first")); return None
        if not self.image_backend():
            self.sk_status.setText(tr("Set up Forge or ComfyUI in Settings first")); return None
        made = self.sk_build_job()
        if not made:
            return None
        job, backend, wf = made
        self.sk_job = job; self._sk_pending = False
        self.sk_status.setText(tr("Generating") + f" · {job.width}×{job.height} · {job.steps} " + tr("steps"))
        self._sk_worker = CallWorker(lambda: backend.generate(job, wf))
        self._sk_worker.ok.connect(lambda imgs, j=job: self._sk_done(j, imgs))
        self._sk_worker.failed.connect(lambda e: (self.sk_status.setText("⚠️ " + e[:160]), self._sk_again()))
        self._sk_worker.start()
        return job

    def _sk_again(self):
        if self._sk_pending:
            QTimer.singleShot(50, self.sk_generate)

    def _sk_done(self, job, imgs):
        if imgs:
            self.sk_png = imgs[0]
            pm = QPixmap(); pm.loadFromData(imgs[0])
            self.sk_result.setPixmap(pm.scaled(max(200, self.sk_result.width() - 8), max(200, self.sk_result.height() - 8),
                                               Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.sk_status.setText(tr("Done") + f" · seed {job.seed}")
        self._sk_again()

    def sk_save(self):
        if not self.sk_png:
            self.notify(tr("Nothing to save yet"), error=True); return None
        meta = self.sk_job.meta() if self.sk_job else {}
        meta["source"] = "live sketch"
        p = self.gallery.save(self.sk_png, meta); self.load_gallery(); self.film_refresh(); self.notify(tr("Saved to Gallery"))
        return p

    def sk_to_inpaint(self):
        p = self.sk_save()
        if p:
            self.gal_inpaint(p)
        return p

    def sk_to_studio(self):
        p = self.sk_save()
        if p:
            self.gal_reference(p)
        return p

    # ================================================================== LoRA training
    def _training_page(self):
        from .app import APP_DIR, page
        w, v = page("LoRA training", "Optional: train your own SDXL / Illustrious LoRA from 15–50 images with kohya "
                                     "sd-scripts (installed separately), then link it to a Character.")
        st = Card("Trainer")
        self.tr_dir = QLineEdit(self.store.get("trainer_dir", "") or trainer.tools_dir(APP_DIR))
        self.tr_dir.editingFinished.connect(lambda: (self.store.set("trainer_dir", self.tr_dir.text().strip()), self.tr_status_refresh()))
        self.tr_forge = QLineEdit(self.store.get("forge_dir", "") or trainer.guess_forge_dir())
        self.tr_forge.setPlaceholderText(tr("Forge folder, e.g. C:\\AI\\sd-webui-forge-classic"))
        self.tr_forge.editingFinished.connect(lambda: (self.store.set("forge_dir", self.tr_forge.text().strip()), self.tr_load_ckpts()))
        self.tr_state = label("", "muted", wrap=True)
        st.add(hrow(label("sd-scripts"), self.tr_dir, button("⬇ Install trainer…", self.tr_install, "ghost")))
        st.add(hrow(label("Forge folder"), self.tr_forge)); st.add(self.tr_state)
        v.addWidget(st)
        split = QSplitter(Qt.Horizontal)
        dc = Card("Images & captions")
        self.tr_list = QListWidget(); self.tr_list.setIconSize(QSize(48, 48)); self.tr_list.currentRowChanged.connect(self._tr_sel)
        self.tr_cap = QPlainTextEdit(); self.tr_cap.setFixedHeight(54); self.tr_cap.textChanged.connect(self._tr_cap_edit)
        self.tr_cap.setPlaceholderText(tr("Caption for the selected image"))
        self.tr_count = label("", "hint")
        dc.add(hrow(button("🗂 Recent gallery images", self.tr_add_gallery, "ghost"), button("📂 Add images…", self.tr_add_files, "ghost"),
                    button("−", self.tr_remove, "ghost"), None, self.tr_count))
        dc.add(self.tr_list, 1); dc.add(self.tr_cap)
        dc.add(hrow(button("🏷 Captions from prompts", self.tr_caption_prompts, "ghost"),
                    button("👁 Auto-caption (vision model)", self.tr_caption_ai, "ghost"), None))
        split.addWidget(dc)
        sc = Card("Training")
        self.tr_name = QLineEdit(); self.tr_name.setPlaceholderText(tr("LoRA name, e.g. mika_v1"))
        self.tr_trigger = QLineEdit(); self.tr_trigger.setPlaceholderText(tr("Trigger word, e.g. mika_pm"))
        self.tr_char = QComboBox()
        self.tr_ckpt = QComboBox(); self.tr_ckpt.setEditable(True); self.tr_ckpt.setMinimumWidth(220)
        self.tr_preset = QComboBox(); self.tr_preset.addItems(list(trainer.PRESETS)); self.tr_preset.setCurrentText(trainer.DEFAULT_PRESET)
        self.tr_epochs = QSpinBox(); self.tr_epochs.setRange(1, 60); self.tr_epochs.setValue(10)
        sc.add(hrow(label("Name"), self.tr_name, label("Trigger"), self.tr_trigger))
        sc.add(hrow(label("Character"), self.tr_char, None))
        sc.add(hrow(label("Base"), self.tr_ckpt, button("⟳", self.tr_load_ckpts, "ghost", "List checkpoints in Forge's folder")))
        sc.add(hrow(label("VRAM"), self.tr_preset, label("Epochs"), self.tr_epochs))
        self.tr_bar = QProgressBar(); self.tr_bar.setRange(0, 100); self.tr_bar.setValue(0)
        self.tr_log = QPlainTextEdit(); self.tr_log.setReadOnly(True); self.tr_log.setMaximumBlockCount(2000)
        sc.add(hrow(button("▶ Start training", self.tr_start, "primary"), button("■ Cancel", self.tr_cancel, "ghost"), None))
        sc.add(self.tr_bar); sc.add(self.tr_log, 1)
        split.addWidget(sc); split.setSizes([560, 520])
        v.addWidget(split, 1)
        self.tr_items, self.tr_proc, self._tr_install_q = [], None, []
        self.tr_status_refresh(); self.tr_refresh_chars(); self.tr_load_ckpts()
        return w

    def tr_status_refresh(self):
        d = self.tr_dir.text().strip()
        ok = trainer.is_installed(d)
        self.tr_state.setText(("✓ " + tr("Trainer installed") + f" · {d}") if ok else
                              tr("Trainer not installed. 'Install trainer' clones kohya-ss/sd-scripts into the folder above and "
                                 "creates its own Python environment (~6 GB download, needs git and an NVIDIA GPU). "
                                 "Nothing is installed until you confirm."))
        return ok

    def tr_refresh_chars(self):
        cur = self.tr_char.currentText(); self.tr_char.clear(); self.tr_char.addItem(tr("(none)"), None)
        for c in self.store.characters():
            self.tr_char.addItem(c["name"], c["id"])
        self.tr_char.setCurrentText(cur)

    def tr_load_ckpts(self):
        fd = self.tr_forge.text().strip(); cur = self.tr_ckpt.currentText(); self.tr_ckpt.clear()
        d = os.path.join(fd, "models", "Stable-diffusion") if fd else ""
        if d and os.path.isdir(d):
            for root, _ds, fs in os.walk(d):
                for f in sorted(fs):
                    if f.lower().endswith((".safetensors", ".ckpt")) and "anima" not in f.lower():
                        self.tr_ckpt.addItem(f, os.path.join(root, f))
        if cur and self.tr_ckpt.findText(cur) >= 0:  # keep the choice only if it's in this Forge folder
            self.tr_ckpt.setCurrentIndex(self.tr_ckpt.findText(cur))
        return self.tr_ckpt.count()

    def _tr_add(self, path, caption=""):
        if any(p == path for p, _c in self.tr_items) or not path.lower().endswith(trainer.IMAGE_EXT):
            return
        self.tr_items.append([path, caption])
        it = QListWidgetItem(QIcon(_thumb(path, 48)), os.path.basename(path)); self.tr_list.addItem(it)
        self.tr_count.setText(f"{len(self.tr_items)} / {trainer.MIN_IMAGES}–{trainer.MAX_IMAGES}")

    def tr_add_gallery(self, n=30):
        for p, m in self.gallery.items()[:n]:
            self._tr_add(p, trainer.default_caption(m, self.tr_trigger.text().strip()))

    def tr_add_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, tr("Training images"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        for f in fs:
            self._tr_add(f)

    def tr_remove(self):
        r = self.tr_list.currentRow()
        if r >= 0:
            self.tr_list.takeItem(r); self.tr_items.pop(r)
            self.tr_count.setText(f"{len(self.tr_items)} / {trainer.MIN_IMAGES}–{trainer.MAX_IMAGES}")

    def _tr_sel(self, r):
        if 0 <= r < len(self.tr_items):
            self.tr_cap.blockSignals(True); self.tr_cap.setPlainText(self.tr_items[r][1]); self.tr_cap.blockSignals(False)

    def _tr_cap_edit(self):
        r = self.tr_list.currentRow()
        if 0 <= r < len(self.tr_items):
            self.tr_items[r][1] = self.tr_cap.toPlainText().strip()

    def tr_caption_prompts(self):
        metas = {p: m for p, m in self.gallery.items()}
        trig = self.tr_trigger.text().strip()
        for it in self.tr_items:
            it[1] = trainer.default_caption(metas.get(it[0], {}), trig) or trig
        self._tr_sel(self.tr_list.currentRow())

    def tr_caption_ai(self):
        self._tr_cap_q = list(range(len(self.tr_items))); self._tr_cap_next()

    def _tr_cap_next(self):
        q = getattr(self, "_tr_cap_q", [])
        if not q:
            self.tr_log.appendPlainText(tr("Captions done")); return
        i = q.pop(0)
        model = (self.vision_model.currentText().strip() if hasattr(self, "vision_model") else "") or self.model.currentText()
        png = sketch.png_bytes(QImage(self.tr_items[i][0]).scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        trig = self.tr_trigger.text().strip()
        self._tr_cap_worker = ChatWorker(self.provider, model, trainer.caption_messages(png, trig), 0.2)
        self._tr_cap_worker.done.connect(lambda t, i=i: (self.tr_items[i].__setitem__(1, trainer.clean_caption(t, trig)),
                                                         self._tr_sel(self.tr_list.currentRow()), QTimer.singleShot(0, self._tr_cap_next)))
        self._tr_cap_worker.failed.connect(lambda e: self.tr_log.appendPlainText("⚠️ " + e))
        self.tr_log.appendPlainText(tr("Captioning") + f" {i + 1}/{len(self.tr_items)}")
        self._tr_cap_worker.start()

    # ---- install (only after the user confirms)
    def tr_install(self):
        d = self.tr_dir.text().strip()
        if trainer.is_installed(d):
            self.notify(tr("Trainer already installed")); return False
        steps = trainer.install_steps(d)
        text = (tr("This downloads kohya-ss/sd-scripts and PyTorch (about 6 GB) into:") + f"\n{d}\n\n" +
                "\n".join(" ".join(s["cmd"]) for s in steps) + "\n\n" + tr("Continue?"))
        if not _ask(self, tr("Install trainer"), text):
            self.tr_log.appendPlainText(tr("Install cancelled")); return False
        if not steps:
            self.tr_status_refresh(); return False
        os.makedirs(os.path.dirname(os.path.abspath(d)), exist_ok=True)
        self._tr_install_q = list(steps); self._tr_run_next_install()
        return True

    def _tr_run_next_install(self):
        if not self._tr_install_q:
            self.tr_log.appendPlainText("✓ " + tr("Trainer installed")); self.tr_status_refresh(); return
        step = self._tr_install_q.pop(0)
        self.tr_log.appendPlainText(f"[{step['name']}]  $ " + " ".join(step["cmd"]))
        self._tr_start_proc(step["cmd"], lambda code: self._tr_run_next_install() if code == 0 else
                            self.tr_log.appendPlainText(tr("Install step failed") + f" (exit {code}) – " +
                                                        tr("fix the problem and press Install trainer again; finished steps are skipped")),
                            cwd=step["cwd"])

    def _tr_start_proc(self, cmd, on_exit, cwd=None):
        p = QProcess(self); env = QProcessEnvironment.systemEnvironment(); env.insert("PYTHONUNBUFFERED", "1")
        p.setProcessEnvironment(env); p.setProcessChannelMode(QProcess.MergedChannels)
        if cwd:
            p.setWorkingDirectory(cwd)
        p.readyReadStandardOutput.connect(lambda: self._tr_output(p))
        p.finished.connect(lambda code, _st: (self._tr_output(p), on_exit(code)))
        p.errorOccurred.connect(lambda e: self.tr_log.appendPlainText(tr("Could not start") + f": {cmd[0]}") if e == QProcess.FailedToStart else None)
        p.start(cmd[0], cmd[1:]); self.tr_proc = p
        return p

    def _tr_output(self, p):
        for line in bytes(p.readAllStandardOutput()).decode(errors="replace").replace("\r", "\n").splitlines():
            if not line.strip():
                continue
            pr = trainer.parse_progress(line)
            if "pct" in pr:
                self.tr_bar.setValue(pr["pct"])
                self.tr_bar.setFormat(f"%p%  ·  {pr['step']}/{pr['total']}" + (f"  ·  loss {pr['loss']:.4f}" if "loss" in pr else ""))
            else:
                self.tr_log.appendPlainText(line[:400])

    # ---- training
    def tr_start(self):
        d = self.tr_dir.text().strip()
        if not trainer.is_installed(d):
            self.notify(tr("Install the trainer first"), error=True); return None
        name = self.tr_name.text().strip()
        if not name:
            self.notify(tr("Name the LoRA first"), error=True); return None
        paths, msg = trainer.validate_images([p for p, _c in self.tr_items])
        if len(paths) < trainer.MIN_IMAGES:
            self.notify(tr(msg), error=True); return None
        ckpt = self.tr_ckpt.currentData() or self.tr_ckpt.currentText().strip()
        if not ckpt or not os.path.exists(ckpt):
            self.notify(tr("Pick the base checkpoint file (SDXL / Illustrious)"), error=True); return None
        if not _ask(self, tr("Start training"), tr("Train") + f" '{name}' " + tr("on") + f" {len(paths)} " +
                    tr("images? This uses the GPU for a while (keep Forge idle).")):
            return None
        lora_dir = trainer.forge_lora_dir(self.tr_forge.text().strip()) if self.tr_forge.text().strip() else ""
        work = os.path.join(self.data_dir, "training", trainer.slug(name)); out = os.path.join(work, "output"); os.makedirs(out, exist_ok=True)
        caps = dict((p, c) for p, c in self.tr_items)
        trig = self.tr_trigger.text().strip()
        items = [(p, trainer.clean_caption(caps.get(p) or "", trig) or name) for p in paths]
        train_dir = trainer.prepare_dataset(work, trig or name, items, trainer.auto_repeats(len(items)))
        cmd = trainer.build_command(d, ckpt, train_dir, out, name, self.tr_preset.currentText(), self.tr_epochs.value())
        self.tr_log.clear(); self.tr_log.appendPlainText("$ " + " ".join(cmd)); self.tr_bar.setValue(0)
        self._tr_job = {"name": name, "out": out, "lora_dir": lora_dir, "char": self.tr_char.currentData(), "trigger": trig}
        self._tr_cancelled = False
        self._tr_start_proc(cmd, self._tr_finished, cwd=d)
        return cmd

    def tr_cancel(self):
        if self.tr_proc is not None and self.tr_proc.state() != QProcess.NotRunning:
            self._tr_cancelled = True; self.tr_proc.kill(); self.tr_log.appendPlainText(tr("Cancelled")); return True
        return False

    def _tr_finished(self, code):
        job = getattr(self, "_tr_job", None) or {}
        if getattr(self, "_tr_cancelled", False):
            self._tr_cancelled = False; self.tr_bar.setValue(0); return None
        if code != 0:
            self.tr_log.appendPlainText(tr("Training failed") + f" (exit {code})"); self.notify(tr("Training failed – see the log"), error=True); return None
        dst = trainer.install_output(job["out"], job["name"], job["lora_dir"]) if job.get("lora_dir") else trainer.finished_file(job["out"], job["name"])
        if not dst:
            self.tr_log.appendPlainText(tr("Training finished but no LoRA file was written")); return None
        self.tr_bar.setValue(100); self.tr_log.appendPlainText("✓ " + dst); self.tr_last = dst
        c = self.store.character(job["char"]) if job.get("char") else None
        if c:
            ex = ch.extra(c); n = os.path.splitext(os.path.basename(dst))[0]
            if n not in [x for x, _ in ch.loras(c)]:
                ex["loras"].append({"name": n, "weight": 0.8})
            if job.get("trigger") and job["trigger"] not in ex["triggers"]:
                ex["triggers"] = ", ".join(x for x in (ex["triggers"], job["trigger"]) if x)
            self.store.save_character(dict(c, extra=json.dumps(ex)), c["id"])
            self.tr_log.appendPlainText(tr("Linked to character") + f" {c['name']}")
            if hasattr(self, "cr_list"):
                self.cr_load(c["id"])
        self.notify(tr("LoRA trained") + f" · {os.path.basename(dst)}")
        return dst

    # ================================================================== shared bits
    def _char_btn(self, target):
        b = button("👤 Character", None, "ghost", "Insert a saved character + outfit")
        b.clicked.connect(lambda _=False, b=b: self.show_character_menu(target, b))
        return b

    def sb_new(self):
        self.sb = sbm.new_storyboard(); self.sb_cur = -1
        for x in (self.sb_title, self.sb_style):
            x.clear()
        self.sb_story.clear(); self.sb_refresh()
