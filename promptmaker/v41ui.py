"""4.1 additions: Home dashboard, backend status, queue view, gallery actions + viewer, upscale,
per-target-model image settings, accent colours, collapsible sidebar, page fades and live previews."""
import os

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QProgressBar,
                               QPushButton, QSizePolicy, QVBoxLayout)

from . import imagegen
from .i18n import tr
from .widgets import CallWorker, Card, button, hrow, label

ROW_H = 160          # gallery row height (justified rows keep each image's aspect ratio)
STATUS_EVERY_MS = 10000
IMG_KEYS = ("aspect", "steps", "cfg", "sampler", "scheduler")


def _empty_item(icon, title, sub=""):
    """Centred, non-selectable empty-state row for lists (4.1.5)."""
    it = QListWidgetItem(f"{icon}\n{title}" + (f"\n{sub}" if sub else ""))
    it.setTextAlignment(Qt.AlignCenter); it.setFlags(Qt.NoItemFlags)
    return it


def offscreen():
    return QApplication.platformName() in ("offscreen", "minimal")


class GalleryList(QListWidget):
    """Icon list whose thumbnails can be dragged out as files (e.g. onto the inpaint canvas), with a hover preview."""
    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.IconMode); self.setFlow(QListWidget.LeftToRight); self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust); self.setMovement(QListWidget.Static); self.setSpacing(6)
        self.setUniformItemSizes(False); self.setIconSize(QSize(int(ROW_H * 2), ROW_H))
        self.setDragEnabled(True); self.setDragDropMode(QListWidget.DragOnly)
        self.setMouseTracking(True); self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hover = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint); self.hover.setObjectName("card")
        self.itemEntered.connect(self._hover)

    def mimeData(self, items):
        md = super().mimeData(items)
        md.setUrls([QUrl.fromLocalFile(i.data(Qt.UserRole)[0]) for i in items if i.data(Qt.UserRole)])
        return md

    def _hover(self, it):
        if offscreen() or not it or not it.data(Qt.UserRole):
            return
        pm = QPixmap(it.data(Qt.UserRole)[0])
        if pm.isNull():
            return
        self.hover.setPixmap(pm.scaled(380, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation)); self.hover.adjustSize()
        self.hover.move(QCursor.pos() + QPoint(18, 18)); self.hover.show()

    def leaveEvent(self, e):
        self.hover.hide(); super().leaveEvent(e)

    def mousePressEvent(self, e):
        self.hover.hide(); super().mousePressEvent(e)


class Viewer(QDialog):
    """Full-screen image viewer: ←/→ or the mouse wheel to browse, Esc to close.
    The picture is always fitted to the window (aspect kept, centred) and switches instantly. The image label
    ignores its pixmap's size hint – otherwise each new pixmap grew the label, which grew the window, which
    rescaled the next image bigger (the "zoom-in" effect in 4.1.0)."""
    def __init__(self, parent, paths, index=0):
        super().__init__(parent)
        self.paths, self.i, self._pm = list(paths), index, QPixmap()
        self.setWindowTitle(tr("Viewer")); self.setObjectName("viewer")
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        self.img = QLabel(); self.img.setAlignment(Qt.AlignCenter)
        self.img.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored); self.img.setMinimumSize(1, 1)
        v.addWidget(self.img, 1)
        self.cap = QLabel(); self.cap.setObjectName("viewerCaption"); self.cap.setAlignment(Qt.AlignCenter); v.addWidget(self.cap)
        if parent is not None and hasattr(parent, "gal_list"):
            parent.gal_list.hover.hide()
        self.resize(1400, 860)
        self.show_i(index)

    def show_i(self, i):
        if not self.paths:
            return
        self.i = i % len(self.paths)
        self._pm = QPixmap(self.paths[self.i])
        self.cap.setText(f"{self.i + 1}/{len(self.paths)} · {os.path.basename(self.paths[self.i])}  ·  ← → / wheel  ·  Esc")
        self._fit()

    def _fit(self):
        if self._pm.isNull():
            self.img.clear(); return
        box = self.img.size()
        if box.width() < 10 or box.height() < 10:
            box = QSize(max(10, self.width()), max(10, self.height() - 30))
        self.img.setPixmap(self._pm.scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Right, Qt.Key_Space, Qt.Key_PageDown):
            self.show_i(self.i + 1)
        elif k in (Qt.Key_Left, Qt.Key_PageUp):
            self.show_i(self.i - 1)
        elif k == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        if d:
            self.show_i(self.i + (1 if d < 0 else -1))
        e.accept()

    def resizeEvent(self, e):
        super().resizeEvent(e); self._fit()


class QueueDialog(QDialog):
    """Pending + running image jobs: reorder, cancel one, cancel all; the running one shows its progress."""
    def __init__(self, win):
        super().__init__(win)
        self.win = win; self.setWindowTitle(tr("Image queue")); self.resize(640, 420)
        v = QVBoxLayout(self)
        self.list = QListWidget(); v.addWidget(self.list, 1)
        self.bar = QProgressBar(); self.bar.setFixedHeight(8); v.addWidget(self.bar)
        v.addLayout(hrow(button("▲ Up", lambda: self._move(-1), "ghost"), button("▼ Down", lambda: self._move(1), "ghost"),
                         None, button("✕ Cancel selected", self._cancel_one, "ghost"),
                         button("Cancel all", self._cancel_all, "danger"), button("Close", self.close)))
        win.genq.progress.connect(self._progress)
        win.genq.finished_job.connect(lambda *_: self.refresh()); win.genq.failed_job.connect(lambda *_: self.refresh())
        self.refresh()

    def rows(self):
        cur = self.win.genq.current
        out = [(cur, True)] if cur is not None else []
        return out + [(j, False) for j in self.win.genq.pending()]

    def refresh(self):
        sel = self.selected_id()
        self.list.clear()
        for j, running in self.rows():
            origin = getattr(j, "tag", "") or tr("generate")
            it = QListWidgetItem(("⚙ " if running else "⏳ ") + f"{j.width}×{j.height} · {origin} · {j.prompt[:70]}")
            it.setData(Qt.UserRole, j.id); self.list.addItem(it)
            if j.id == sel:
                self.list.setCurrentItem(it)
        if not self.rows():
            self.list.addItem(_empty_item("✿ ･ﾟ✧", tr("Queue is empty"), tr("Images you generate will line up here.") + "  ♡")); self.bar.setValue(0)

    def selected_id(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _move(self, d):
        jid = self.selected_id()
        if jid and self.win.genq.move(jid, d) >= 0:
            self.refresh()

    def _cancel_one(self):
        jid = self.selected_id()
        if jid and self.win.genq.remove(jid):
            for j in self.win.queue_jobs:
                if j.id == jid and getattr(j, "state", "queued") == "queued":
                    j.state, j.error = "failed", "Cancelled"
            self.win._render_queue(); self.refresh()

    def _cancel_all(self):
        for j in self.win.genq.pending():
            j.state, j.error = "failed", "Cancelled"
        self.win.genq.cancel_all(); self.win._render_queue(); self.refresh()

    def _progress(self, jid, pct, _msg):
        self.bar.setRange(0, 0 if pct < 0 else 100)
        if pct >= 0:
            self.bar.setValue(pct)


class V41Pages:
    # ================================================================ Home
    def _home_page(self):
        from .app import page
        w, v = page("Home", "Your studio at a glance – pick up where you left off.")
        from . import theme
        stats = QHBoxLayout(); stats.setSpacing(14); v.addLayout(stats)
        self.home_stats = {}
        for key, title in (("images", "Images in Gallery"), ("prompts", "Prompts in History"), ("favs", "Favourites"), ("chars", "Characters")):
            c = Card(); c.lay.setSpacing(2)
            val = QLabel("0"); val.setObjectName("statValue"); c.add(val); c.add(label(title, "statLabel"))
            self.home_stats[key] = val; stats.addWidget(c, 1)
        top = QHBoxLayout(); top.setSpacing(14); v.addLayout(top)
        st = Card("Status")
        self.home_target = label("", "h2"); self.home_ckpt = label("", "muted", wrap=True)
        self.home_backend = label("", "muted", wrap=True); self.home_ai = label("", "muted", wrap=True)
        for x in (self.home_target, self.home_ckpt, self.home_backend, self.home_ai):
            st.add(x)
        st.add(hrow(button("☰ Queue", self.open_queue, "ghost"), button("⚙ Image settings", lambda: self.go("Settings"), "ghost"), None))
        top.addWidget(st, 1)
        qs = Card("Quick start"); g = QGridLayout(); g.setSpacing(10)
        tiles = [("✨  Create", lambda: self.go("Create")), ("🎨  Builder", lambda: self.go("Builder")),
                 ("🖼  Generate last prompt", self.home_generate_last), ("🔄  Auto-refine", lambda: self.go("Auto-refine")),
                 ("🖌  Inpaint", lambda: self.go("Inpaint & Regions")), ("🗂  Gallery", lambda: self.go("Gallery")),
                 ("👤  Characters", lambda: self.go("Characters")), ("📖  Storyboard", lambda: self.go("Storyboard")),
                 ("✏  Live sketch", lambda: self.go("Live sketch"))]
        for i, (t, fn) in enumerate(tiles):
            b = QPushButton(tr(t)); b.setObjectName("homeTile"); b.setCursor(Qt.PointingHandCursor); b.clicked.connect(lambda _=False, f=fn: f())
            b.setMinimumHeight(56); theme.lift(b)
            g.addWidget(b, i // 3, i % 3)
        qs.add(g)
        top.addWidget(qs, 2)
        rc = Card("Recent images")
        self.home_recent = QListWidget(); self.home_recent.setViewMode(QListWidget.IconMode); self.home_recent.setIconSize(QSize(200, 150))
        self.home_recent.setMovement(QListWidget.Static); self.home_recent.setFlow(QListWidget.LeftToRight); self.home_recent.setWrapping(False)
        self.home_recent.setFixedHeight(190); self.home_recent.setSpacing(6)
        self.home_recent.itemClicked.connect(lambda it: self.gal_view(it.data(Qt.UserRole)))
        rc.add(self.home_recent)
        v.addWidget(rc); v.addStretch(1)
        return w

    def home_refresh(self):
        if not hasattr(self, "home_target"):
            return
        p = self.profile
        self.home_target.setText(tr("Target model") + f": {p.get('name')}")
        ck = self.profile_checkpoints().get(p.get("id")) if hasattr(self, "profile_checkpoints") else None
        cur = self.store.get(f"img_checkpoint:{self.ckpt_key()}", "") or tr("backend default")
        self.home_ckpt.setText(tr("Checkpoint") + f": {cur}" + (f"  ·  🔗 {tr('linked')}" if ck else ""))
        self.home_backend.setText(self._status_text())
        for key, fn in (("images", lambda: len(self.gallery.items())), ("prompts", lambda: len(self.store.history())),
                        ("favs", lambda: len(self.store.favourites())), ("chars", lambda: len(self.store.characters()))):
            try:
                self.home_stats[key].setText(str(fn()))
            except Exception:
                self.home_stats[key].setText("–")
        self.home_ai.setText(self.ai_dot.text())
        self.home_recent.clear()
        for path, _m in self.gallery.items()[:8]:
            it = QListWidgetItem(QIcon(QPixmap(path).scaled(200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)), "")
            it.setData(Qt.UserRole, path); self.home_recent.addItem(it)
        if not self.home_recent.count():
            self.home_recent.addItem(_empty_item("(｡•ᴗ•｡) ✧", tr("No images yet – generate one from Create or Builder"), "★ ･ﾟ✿ ♡ ✿ﾟ･ ★"))

    def home_generate_last(self):
        text = self.current_text().strip() if hasattr(self, "current_text") else ""
        if not text:
            rows = self.store.history(limit=1)
            text = rows[0][2] if rows else ""
        if not text:
            self.notify(tr("No prompt yet – write one in Create first"), error=True); return None
        return self.generate_image(text, self._default_negative())

    # ================================================================ backend status (sidebar)
    def _status_widgets(self, f):
        self.be_status = QPushButton("○ " + tr("Image backend: off")); self.be_status.setObjectName("statusDot")
        self.be_status.setCursor(Qt.PointingHandCursor); self.be_status.setToolTip(tr("Image backend · click for Settings → Image generation"))
        self.be_status.clicked.connect(lambda: self.go("Settings"))
        self.queue_btn = button("☰", self.open_queue, "ghost", "Image queue")
        f.addLayout(hrow(self.be_status, None, self.queue_btn))
        self._status = ("off", "")
        self._status_busy = False
        self.status_timer = QTimer(self); self.status_timer.timeout.connect(self.poll_status)
        if not os.environ.get("PROMPTMAKER_NO_NET"):
            self.status_timer.start(STATUS_EVERY_MS); QTimer.singleShot(800, self.poll_status)

    def _status_text(self):
        kind, txt = getattr(self, "_status", ("off", ""))
        b = self.image_backend()
        name = "Forge" if isinstance(b, imagegen.A1111) else (b.name if b else "")
        return {"off": "○ " + tr("Image backend: off"), "loading": "◌ " + tr("Loading…"),
                "offline": f"<span style='color:#ff6b81'>●</span> {name} · " + tr("Offline"),
                "online": f"<span style='color:#35d39a'>●</span> {name} · {txt}"}.get(kind, "")

    def _set_status(self, kind, txt=""):
        self._status = (kind, txt)
        plain = self._status_text().split("</span>")[-1].strip()
        dot = {"online": "🟢", "offline": "🔴", "loading": "◌"}.get(kind, "○")
        self.be_status.setText(f"{dot} {plain}"[:42]); self.be_status.setToolTip(f"{plain}\n" + tr("Click for Settings → Image generation"))

    def poll_status(self):
        """One cheap status request in a worker; never stacks (skips while one is in flight)."""
        if self._status_busy:
            return None
        b = self.image_backend()
        if not b:
            self._set_status("off"); return None
        if self._status[0] == "off":
            self._set_status("loading")
        self._status_busy = True
        wk = CallWorker(b.status)

        def ok(r):
            self._status_busy = False; self._set_status("online", str(r[1]))

        def failed(_e):
            self._status_busy = False; self._set_status("offline")
        wk.ok.connect(ok); wk.failed.connect(failed); self._keep(wk); wk.start()
        return wk

    # ================================================================ queue view
    def open_queue(self):
        dlg = getattr(self, "_queue_dlg", None)
        if dlg is None:
            dlg = self._queue_dlg = QueueDialog(self)
        dlg.refresh()
        if not os.environ.get("PROMPTMAKER_NO_DIALOGS"):
            dlg.show(); dlg.raise_()
        return dlg

    # ================================================================ gallery actions
    def gal_context(self, pos):
        it = self.gal_list.itemAt(pos)
        if not it:
            return
        self.gal_list.setCurrentItem(it)
        m = QMenu(self)
        for text, fn in (("🔍 View", lambda: self.gal_view()), ("🖌 Inpaint this", self.gal_inpaint),
                         ("👁 Use as reference", self.gal_reference), ("🔍 Regenerate with hires", self.gal_hires),
                         ("⤢ Upscale…", self.gal_upscale), ("♻ Reuse prompt", self._gal_reuse)):
            m.addAction(tr(text), fn)
        m.exec(self.gal_list.viewport().mapToGlobal(pos))

    def _gal_target(self, path=None):
        if path:
            for p, meta in self.gallery.items():
                if os.path.normcase(p) == os.path.normcase(path):
                    return p, meta
            return path, {}
        return self._gal_cur()

    def gal_view(self, path=None):
        paths = [p for p, _m in self.gallery.items()[:400]]
        p, _m = self._gal_target(path)
        if not p or p not in paths:
            return None
        v = Viewer(self, paths, paths.index(p))
        self._viewer = v
        if not os.environ.get("PROMPTMAKER_NO_DIALOGS"):
            v.showFullScreen()
        return v

    def gal_inpaint(self, path=None):
        p, m = self._gal_target(path)
        if not p:
            return
        self.ip_open(p)
        if m.get("prompt"):
            self.ip_prompt.setPlainText(m["prompt"])
        self.go("Inpaint & Regions")

    def gal_reference(self, path=None):
        p, _m = self._gal_target(path)
        if p:
            self._i2p_set_image(QImage(p)); self.go("Image to Prompt")

    def _gal_job(self, meta, tag):
        made = self.make_job(meta.get("prompt", ""), meta.get("negative", ""), meta.get("seed"), tag)
        if not made:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return None
        job, backend, wf = made
        for k in ("steps", "cfg", "sampler", "scheduler", "width", "height"):
            if meta.get(k) not in (None, ""):
                setattr(job, k, type(getattr(job, k))(meta[k]))
        if meta.get("checkpoint"):
            job.checkpoint = meta["checkpoint"]
        return job, backend, wf

    def _queue(self, job, backend, wf, msg):
        self.genq.add(job, backend, wf); self.queue_jobs.append(job); self._render_queue()
        self.notify(msg + f" · seed {job.seed}")
        return job

    def gal_hires(self, path=None):
        p, m = self._gal_target(path)
        if not m.get("prompt"):
            self.notify(tr("This image has no saved prompt"), error=True); return None
        made = self._gal_job(m, "hires")
        if not made:
            return None
        job, backend, wf = made
        job.hires = {"scale": self.store.get("hr_scale", 1.5), "upscaler": self.store.get("hr_upscaler", "Latent"),
                     "steps": self.store.get("hr_steps", 0), "denoise": self.store.get("hr_denoise", 0.4)}
        return self._queue(job, backend, wf, tr("Hires version queued"))

    def gal_upscale(self, path=None, scale=None, upscaler=None, denoise=None):
        p, m = self._gal_target(path)
        if not p:
            return None
        if scale is None:
            opts = self._upscale_dialog()
            if not opts:
                return None
            scale, upscaler, denoise = opts
        m = dict(m); m.setdefault("prompt", "upscale")
        made = self._gal_job(m, "upscale")
        if not made:
            return None
        job, backend, wf = made
        with open(p, "rb") as fh:
            png = fh.read()
        try:
            w, h = imagegen.png_size(png)
        except ValueError:
            self.notify(tr("Only PNG images can be upscaled"), error=True); return None
        job.width, job.height = imagegen.scaled_size(w, h, scale)
        job.upscale = {"image": png, "scale": float(scale), "upscaler": upscaler or self.store.get("up_upscaler", "R-ESRGAN 4x+"),
                       "denoise": float(denoise or 0), "source": p}
        if isinstance(backend, imagegen.ComfyUI) and job.upscale["denoise"]:
            self.notify(tr("ComfyUI: only Pure upscale (denoise 0) is supported – switched to it"))
            job.upscale["denoise"] = 0.0
        return self._queue(job, backend, wf, tr("Upscale queued") + f" · {job.width}×{job.height}")

    def _upscale_dialog(self):
        sc, up, dn = float(self.store.get("up_scale", 1.5)), self.store.get("up_upscaler", "R-ESRGAN 4x+"), float(self.store.get("up_denoise", 0.3))
        if os.environ.get("PROMPTMAKER_NO_DIALOGS"):
            return sc, up, dn
        d = QDialog(self); d.setWindowTitle(tr("Upscale image")); v = QVBoxLayout(d)
        s = QDoubleSpinBox(); s.setRange(1.1, 4.0); s.setSingleStep(0.25); s.setValue(sc); s.setSuffix("×")
        u = QComboBox(); u.setEditable(True); u.addItems(list(dict.fromkeys([up, "R-ESRGAN 4x+", "R-ESRGAN 4x+ Anime6B", "4x-UltraSharp", "Lanczos"])))
        n = QDoubleSpinBox(); n.setRange(0.0, 1.0); n.setSingleStep(0.05); n.setValue(dn)
        pure = QCheckBox(tr("Pure upscale (no redraw, Extras tab)")); pure.toggled.connect(lambda on: n.setEnabled(not on))
        v.addLayout(hrow(label("Scale"), s, label("Upscaler"), u, None))
        v.addLayout(hrow(label("Denoise"), n, label("0.2–0.35 adds detail, keeps the picture", "hint"), None)); v.addWidget(pure)
        v.addLayout(hrow(None, button("Cancel", d.reject, "ghost"), button("⤢ Upscale", d.accept, "primary")))
        if d.exec() != QDialog.Accepted:
            return None
        dn = 0.0 if pure.isChecked() else n.value()
        self.store.set("up_scale", s.value()); self.store.set("up_upscaler", u.currentText()); self.store.set("up_denoise", n.value())
        return s.value(), u.currentText(), dn

    # ================================================================ per-target-model image settings
    def profile_image_settings(self):
        return dict(self.store.get("profile_image_settings") or {})

    def save_profile_image(self, **vals):
        pid = self.profile.get("id")
        allp = self.profile_image_settings(); cur = dict(allp.get(pid) or {})
        for k, val in vals.items():
            if k in IMG_KEYS:
                if val in (None, "", 0, imagegen.PROFILE_DEFAULT):
                    cur.pop(k, None)
                else:
                    cur[k] = val
        if cur:
            allp[pid] = cur
        else:
            allp.pop(pid, None)
        self.store.set("profile_image_settings", allp)
        self._update_ckpt_link_label()

    def image_settings_for(self, pid=None):
        return dict(self.profile_image_settings().get(pid or self.profile.get("id")) or {})

    def apply_profile_image_settings(self):
        """Profile switch: restore its remembered aspect / steps / CFG / sampler / scheduler (unset ones are left as they are)."""
        ps = self.image_settings_for()
        self._restoring_img = True
        try:
            if ps.get("aspect") and hasattr(self, "aspect"):
                self.aspect.setCurrentText(ps["aspect"])
            if hasattr(self, "img_steps"):
                if ps.get("steps"):
                    self.img_steps.setValue(int(ps["steps"]))
                if ps.get("cfg"):
                    self.img_cfg.setValue(float(ps["cfg"]))
                if ps.get("sampler"):
                    self.img_sampler.setCurrentText(ps["sampler"])
                if ps.get("scheduler"):
                    self.img_scheduler.setCurrentText(ps["scheduler"])
        finally:
            self._restoring_img = False

    def link_summary(self):
        ps = self.image_settings_for()
        ck = self.profile_checkpoints().get(self.profile.get("id"))
        bits = ([ck] if ck else []) + ([ps["aspect"]] if ps.get("aspect") else []) + \
            ([f"{ps['steps']} {tr('steps')}"] if ps.get("steps") else []) + ([f"CFG {ps['cfg']}"] if ps.get("cfg") else []) + \
            [ps[k] for k in ("sampler", "scheduler") if ps.get(k)]
        return bits

    # ================================================================ look & feel
    def apply_accent(self, name):
        self.store.set("accent", name); self.apply_theme(getattr(self, "theme", "light"))

    def fade_in(self, widget):
        if offscreen() or not self.store.get("animations", True):
            return None
        eff = QGraphicsOpacityEffect(widget); widget.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", widget); a.setDuration(150); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: widget.setGraphicsEffect(None)); a.start()
        self._fade = a
        return a

    # ================================================================ live preview
    def _preview_tick(self):
        lp = dict(imagegen.LAST_PREVIEW)
        if not lp.get("png") or lp.get("png") is getattr(self, "_last_preview_png", None):
            return
        self._last_preview_png = lp["png"]
        img = QImage.fromData(lp["png"])
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        if hasattr(self, "gen_preview"):
            self.gen_preview.setPixmap(pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)); self.gen_preview.setVisible(True)
        if lp.get("tag") == "autorefine" and hasattr(self, "ar_img"):
            self.ar_img.setPixmap(pm.scaled(230, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation))

