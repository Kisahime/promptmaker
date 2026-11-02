"""5.2 Civitai model browser page (Library → Model browser): search, filter, inspect and download models into the
Forge / ComfyUI folders, then make a model profile. All network work runs in worker threads."""
import hashlib
import os
import threading
import urllib.request

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QSizePolicy,
                               QSplitter, QTextBrowser)

from . import civitai, profiles, trainer
from . import civitai_browser as cb
from .i18n import tr
from .widgets import Card, CallWorker, button, hrow, label

THUMB_W, THUMB_H = 200, 260


def fetch_bytes(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": civitai.UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(8 * 1024 * 1024)


class ThumbLoader(QThread):
    """One background thread, one thumbnail at a time, cached on disk in data/cache/civitai_thumbs."""
    loaded = Signal(str, bytes)

    def __init__(self, cache_dir, fetch=fetch_bytes):
        super().__init__()
        self.cache_dir, self.fetch = cache_dir, fetch
        self._q, self._cv, self._stop = [], threading.Condition(), False
        os.makedirs(cache_dir, exist_ok=True)

    def path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest()[:32] + ".img")

    def want(self, url):
        with self._cv:
            if url not in self._q:
                self._q.append(url); self._cv.notify()

    def stop(self):
        with self._cv:
            self._stop = True; self._cv.notify()

    def run(self):
        while True:
            with self._cv:
                while not self._q and not self._stop:
                    self._cv.wait(0.5)
                if self._stop:
                    return
                url = self._q.pop(0)
            p = self.path(url)
            try:
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        data = f.read()
                else:
                    data = self.fetch(url)
                    with open(p, "wb") as f:
                        f.write(data)
                self.loaded.emit(url, data)
            except Exception:  # noqa: BLE001 – a missing thumbnail is not an error worth showing
                continue


class DownloadWorker(QThread):
    progress = Signal(object, object)
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, url, dest, key, sha, opener=None):
        super().__init__()
        self.args = (url, dest, key, sha); self.cancel = threading.Event(); self.opener = opener

    def stop(self):
        self.cancel.set()

    def run(self):
        url, dest, key, sha = self.args
        kw = {"opener": self.opener} if self.opener else {}
        try:
            self.ok.emit(cb.download(url, dest, key, sha, progress=lambda d, t: self.progress.emit(d, t), cancel=self.cancel, **kw))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def placeholder_icon(text="", hidden=False):
    pm = QPixmap(THUMB_W, THUMB_H); pm.fill(QColor("#2a2440"))
    p = QPainter(pm); p.setPen(QColor("#b9a8e8"))
    p.drawText(pm.rect(), Qt.AlignCenter | Qt.TextWordWrap, ("🔒 " + tr("Preview hidden (NSFW off)")) if hidden else (text or "…"))
    p.end()
    return QIcon(pm)


class CivitaiBrowserPage:
    cvb_fetch = staticmethod(fetch_bytes)   # tests / screenshots replace this (no real thumbnails)
    cvb_opener = None                       # download opener override for tests

    def _civitai_browser_page(self):
        from .app import page
        w, v = page("Model browser", "Search Civitai, check a model's versions, files and the creator's settings, then download "
                                     "it straight into your Forge or ComfyUI folders and make a model profile.")
        top = Card()
        self.cvb_query = QLineEdit(); self.cvb_query.setPlaceholderText(tr("Search Civitai models, e.g. moss, anima, watercolor lora"))
        self.cvb_query.returnPressed.connect(lambda: self.cvb_search())
        self.cvb_type = QComboBox()
        for name, val in cb.TYPES:
            self.cvb_type.addItem(tr(name), val)
        self.cvb_base = QComboBox(); self.cvb_base.addItem(tr("All base models"), "")
        for b in cb.BASE_MODELS:
            self.cvb_base.addItem(b, b)
        self.cvb_sort = QComboBox()
        for s in cb.SORTS:
            self.cvb_sort.addItem(tr(s), s)
        self.cvb_period = QComboBox()
        for name, val in cb.PERIODS:
            self.cvb_period.addItem(tr(name), val)
        self.cvb_nsfw = QCheckBox(tr("Show NSFW")); self.cvb_nsfw.setChecked(False)
        self.cvb_nsfw.setToolTip(tr("Off: asks Civitai for SFW models only and hides every preview above PG"))
        for cmb, key in ((self.cvb_type, "cvb_type"), (self.cvb_base, "cvb_base"), (self.cvb_sort, "cvb_sort"), (self.cvb_period, "cvb_period")):
            cmb.setCurrentIndex(max(0, cmb.findData(self.store.get(key, cmb.currentData()))))
            cmb.currentIndexChanged.connect(lambda _i, c=cmb, k=key: (self.store.set(k, c.currentData()), self.cvb_search()))
        self.cvb_nsfw.toggled.connect(lambda _on: self.cvb_search())
        self.cvb_host_lbl = label("", "hint")
        top.add(hrow(self.cvb_query, button("⌕ Search", lambda: self.cvb_search(), "primary")))
        top.add(hrow(self.cvb_type, self.cvb_base, self.cvb_sort, self.cvb_period, self.cvb_nsfw, None, self.cvb_host_lbl))
        v.addWidget(top)
        split = QSplitter(Qt.Horizontal)
        gc = Card("Results")
        self.cvb_grid = QListWidget(); self.cvb_grid.setObjectName("cvbGrid")
        self.cvb_grid.setViewMode(QListWidget.IconMode); self.cvb_grid.setResizeMode(QListWidget.Adjust)
        self.cvb_grid.setMovement(QListWidget.Static); self.cvb_grid.setIconSize(QSize(THUMB_W, THUMB_H))
        self.cvb_grid.setGridSize(QSize(THUMB_W + 22, THUMB_H + 78)); self.cvb_grid.setWordWrap(True); self.cvb_grid.setSpacing(6)
        self.cvb_grid.setMinimumHeight(520); self.cvb_grid.setUniformItemSizes(True)
        self.cvb_grid.currentItemChanged.connect(lambda it, _p: it and self.cvb_select(it.data(Qt.UserRole)))
        self.cvb_grid.verticalScrollBar().valueChanged.connect(self._cvb_scrolled)
        gc.add(self.cvb_grid, 1)
        self.cvb_status = label("", "hint", wrap=True)
        self.cvb_more = button("Load more", lambda: self.cvb_search(more=True), "ghost"); self.cvb_more.setEnabled(False)
        gc.add(hrow(self.cvb_status, None, self.cvb_more))
        split.addWidget(gc)
        dc = Card("Details")
        self.cvb_title = label(tr("Pick a model"), "h2"); self.cvb_title.setWordWrap(True); dc.add(self.cvb_title)
        self.cvb_meta = label("", "hint", wrap=True); dc.add(self.cvb_meta)
        self.cvb_version = QComboBox(); self.cvb_version.currentIndexChanged.connect(self._cvb_version_changed)
        self.cvb_web = button("🌐 Open on Civitai", self.cvb_open_web, "ghost")
        dc.add(hrow(label("Version"), self.cvb_version, self.cvb_web))
        self.cvb_file = QComboBox(); self.cvb_file.currentIndexChanged.connect(lambda _i: self._cvb_file_changed())
        dc.add(hrow(label("File"), self.cvb_file))
        self.cvb_words = label("", "hint", wrap=True); self.cvb_words.setTextInteractionFlags(Qt.TextSelectableByMouse); dc.add(self.cvb_words)
        self.cvb_settings = label("", "hint", wrap=True); self.cvb_settings.setTextInteractionFlags(Qt.TextSelectableByMouse); dc.add(self.cvb_settings)
        self.cvb_desc = QTextBrowser(); self.cvb_desc.setOpenExternalLinks(True); self.cvb_desc.setMinimumHeight(140)
        dc.add(self.cvb_desc, 1)
        self.cvb_dest = QComboBox(); self.cvb_dest.setEditable(True); self.cvb_dest.setMinimumContentsLength(24)
        dc.add(hrow(label("Save to"), self.cvb_dest, button("…", self.cvb_browse_dest, "ghost", "Choose another folder")))
        self.cvb_dl = button("⬇ Download", self.cvb_download, "primary"); self.cvb_dl.setEnabled(False)
        self.cvb_cancel = button("✕ Cancel", self.cvb_cancel_download, "ghost"); self.cvb_cancel.setEnabled(False)
        self.cvb_bar = QProgressBar(); self.cvb_bar.setRange(0, 100); self.cvb_bar.setValue(0); self.cvb_bar.setTextVisible(True)
        dc.add(hrow(self.cvb_dl, self.cvb_cancel, self.cvb_bar))
        self.cvb_dl_status = label("", "hint", wrap=True); dc.add(self.cvb_dl_status)
        self.cvb_refresh_btn = button("⟳ Refresh models", self.cvb_refresh_models, "ghost")
        self.cvb_profile_btn = button("🦄 Create model profile", self.cvb_create_profile, "ghost")
        self.cvb_refresh_btn.setEnabled(False); self.cvb_profile_btn.setEnabled(False)
        dc.add(hrow(self.cvb_refresh_btn, self.cvb_profile_btn, None))
        for c in (self.cvb_version, self.cvb_file, self.cvb_dest):
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); c.setMinimumContentsLength(20)
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        split.addWidget(dc); split.setSizes([760, 520])
        v.addWidget(split, 1)
        self.cvb_items, self.cvb_cursor, self.cvb_model, self.cvb_ver = [], None, None, None
        self._cvb_search_w = self._cvb_detail_w = self._cvb_dl_w = None
        self._cvb_seq = 0; self._cvb_downloaded = None
        self._cvb_thumb_items = {}
        self.cvb_thumbs = ThumbLoader(os.path.join(self.data_dir, "cache", "civitai_thumbs"), self.cvb_fetch)
        self.cvb_thumbs.loaded.connect(self._cvb_thumb_loaded)
        self._keep(self.cvb_thumbs)
        self._cvb_host_label()
        return w

    # ------------------------------------------------------------------ helpers
    def cvb_client(self):
        return civitai.Client(self.keys.get("api_key:civitai"), os.path.join(self.data_dir, "cache", "civitai"),
                              base=self.store.get("civitai_api") or civitai.API, ttl=cb.BROWSE_TTL)

    def cvb_host(self):
        return cb.host_of(self.store.get("civitai_api") or civitai.API)

    def _cvb_host_label(self):
        self.cvb_host_lbl.setText(tr("Host") + f": {self.cvb_host()}" + ("" if self.keys.get("api_key:civitai") else " · " + tr("no API key")))

    def cvb_forge_dir(self):
        return self.store.get("forge_dir", "") or trainer.guess_forge_dir()

    def cvb_comfy_dir(self):
        return self.store.get("comfy_dir", "") or cb.guess_comfy_dir()

    def cvb_filters(self):
        return {"query": self.cvb_query.text(), "types": [self.cvb_type.currentData()] if self.cvb_type.currentData() else [],
                "base_models": [self.cvb_base.currentData()] if self.cvb_base.currentData() else [],
                "sort": self.cvb_sort.currentData(), "period": self.cvb_period.currentData(), "nsfw": self.cvb_nsfw.isChecked()}

    # ------------------------------------------------------------------ search
    def cvb_search(self, more=False):
        if more and not self.cvb_cursor:
            return None
        if self._cvb_search_w is not None and self._cvb_search_w.isRunning():
            if more:
                return None
        self._cvb_seq += 1; seq = self._cvb_seq
        kw = self.cvb_filters(); kw["cursor"] = self.cvb_cursor if more else None
        if not more:
            self.cvb_grid.clear(); self.cvb_items = []; self._cvb_thumb_items = {}; self.cvb_cursor = None
        self.cvb_status.setText(tr("Searching Civitai…")); self.cvb_more.setEnabled(False)
        client = self.cvb_client()
        wk = CallWorker(lambda: cb.search(client, **kw))
        wk.ok.connect(lambda res, s=seq, n=kw["nsfw"]: self._cvb_results(s, res, n))
        wk.failed.connect(lambda e, s=seq: s == self._cvb_seq and (self.cvb_status.setText("⚠️ " + e[:300]), self.cvb_more.setEnabled(bool(self.cvb_cursor))))
        self._keep(wk); wk.start(); self._cvb_search_w = wk
        return wk

    def _cvb_results(self, seq, res, nsfw):
        if seq != self._cvb_seq:
            return  # a newer search replaced this one
        items, cursor = res
        items = cb.filter_models(items, nsfw)  # second guard, also when filters were changed mid-flight
        self.cvb_cursor = cursor
        hidden = 0
        for m in items:
            c = cb.card(m); hidden += c["hidden"]
            it = QListWidgetItem(placeholder_icon(c["type"], hidden=not c["thumb"] and c["hidden"] > 0),
                                 f"{c['name']}\n{tr('by')} {c['creator']} · {c['type']}\n{c['base']}  ⬇ {cb.short_count(c['downloads'])}  ♥ {cb.short_count(c['likes'])}")
            it.setData(Qt.UserRole, len(self.cvb_items)); it.setToolTip(f"{c['name']} – {c['type']} · {c['base']}")
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.cvb_grid.addItem(it); self.cvb_items.append(m)
            if c["thumb"]:
                self._cvb_thumb_items.setdefault(c["thumb"], []).append(it)
                self.cvb_thumbs.want(c["thumb"])
        if not self.cvb_thumbs.isRunning():
            self.cvb_thumbs.start()
        n = len(self.cvb_items)
        self.cvb_status.setText((tr("No models found") if not n else f"{n} " + (tr("model") if n == 1 else tr("models")))
                                + (f" · {hidden} " + tr("NSFW previews hidden") if hidden and not nsfw else ""))
        self.cvb_more.setEnabled(bool(cursor))

    def _cvb_scrolled(self, value):
        sb = self.cvb_grid.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 40 and self.cvb_cursor:
            self.cvb_search(more=True)

    def _cvb_thumb_loaded(self, url, data):
        pm = QPixmap(); pm.loadFromData(data)
        if pm.isNull():
            return
        pm = pm.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        pm = pm.copy((pm.width() - THUMB_W) // 2, (pm.height() - THUMB_H) // 2, THUMB_W, THUMB_H)
        for it in self._cvb_thumb_items.get(url, []):
            try:
                it.setIcon(QIcon(pm))
            except RuntimeError:
                pass

    # ------------------------------------------------------------------ details
    def cvb_select(self, idx):
        if idx is None or idx >= len(self.cvb_items):
            return
        m = self.cvb_items[idx]
        self._cvb_show_model(m)
        # the search list carries versions without full descriptions on some models – fetch the full model in the background
        client = self.cvb_client(); nsfw = self.cvb_nsfw.isChecked()
        wk = CallWorker(lambda: client.get(f"/models/{m['id']}"))
        wk.ok.connect(lambda full, mid=m["id"]: self.cvb_model and self.cvb_model.get("id") == mid and
                      self._cvb_show_model(cb.filter_models([full], True)[0] if nsfw else (cb.filter_models([full], False) or [m])[0], keep=True))
        wk.failed.connect(lambda e: None)
        self._keep(wk); wk.start(); self._cvb_detail_w = wk

    def _cvb_show_model(self, m, keep=False):
        prev = self.cvb_version.currentData() if keep else None
        self.cvb_model = m
        st = m.get("stats") or {}
        self.cvb_title.setText(m.get("name") or "?")
        self.cvb_meta.setText(f"{m.get('type', '')} · {tr('by')} {(m.get('creator') or {}).get('username', '?')} · "
                              f"⬇ {cb.short_count(st.get('downloadCount'))} · ♥ {cb.short_count(st.get('thumbsUpCount'))}"
                              + (" · ⚠️ NSFW" if m.get("nsfw") else ""))
        self.cvb_version.blockSignals(True); self.cvb_version.clear()
        for v in m.get("modelVersions") or []:
            self.cvb_version.addItem(f"{v.get('name')} · {v.get('baseModel', '')}", v.get("id"))
        self.cvb_version.setCurrentIndex(max(0, self.cvb_version.findData(prev)) if prev else 0)
        self.cvb_version.blockSignals(False)
        self._cvb_version_changed()

    def _cvb_version_changed(self, *_):
        m = self.cvb_model or {}
        vid = self.cvb_version.currentData()
        v = next((x for x in m.get("modelVersions") or [] if x.get("id") == vid), None)
        self.cvb_ver = v
        self.cvb_file.blockSignals(True); self.cvb_file.clear()
        for f in cb.files(v or {}):
            self.cvb_file.addItem(cb.file_label(f), f)
        self.cvb_file.blockSignals(False)
        if not v:
            self.cvb_dl.setEnabled(False); return
        words = [w for w in v.get("trainedWords") or [] if w]
        self.cvb_words.setText(tr("Trained words") + ": " + (", ".join(words) if words else tr("none")))
        sett = cb.author_settings(m, v)
        self.cvb_settings.setText(tr("Author settings") + ": " + (sett or tr("none given in the description")))
        desc = (v.get("description") or "") + ("<hr>" if v.get("description") and m.get("description") else "") + (m.get("description") or "")
        self.cvb_desc.setHtml(cb.sanitize_html(desc) or tr("No description"))
        self._cvb_file_changed()

    def cvb_file_info(self):
        return self.cvb_file.currentData()

    def cvb_destinations(self):
        f = self.cvb_file_info() or {}
        prefer = "comfyui" if self.store.get("img_backend", "none") == "comfyui" else "forge"
        return cb.destinations((self.cvb_model or {}).get("type", ""), (self.cvb_ver or {}).get("baseModel", ""), f,
                               self.cvb_forge_dir(), self.cvb_comfy_dir(), prefer,
                               fallback=os.path.join(self.data_dir, "downloads"))

    def _cvb_file_changed(self):
        self.cvb_dest.clear()
        for lab, path in self.cvb_destinations():
            self.cvb_dest.addItem(f"{lab} – {path}", path)
        self.cvb_dl.setEnabled(self.cvb_file_info() is not None and not (self._cvb_dl_w and self._cvb_dl_w.isRunning()))

    def cvb_dest_dir(self):
        i = self.cvb_dest.currentIndex()
        txt = self.cvb_dest.currentText().strip()
        if i >= 0 and txt == self.cvb_dest.itemText(i):
            return self.cvb_dest.itemData(i)
        return txt

    def cvb_browse_dest(self):
        d = QFileDialog.getExistingDirectory(self, tr("Save to folder"), self.cvb_dest_dir() or self.data_dir)
        if d:
            self.cvb_dest.addItem(d, d); self.cvb_dest.setCurrentIndex(self.cvb_dest.count() - 1)

    def cvb_open_web(self):
        if self.cvb_model:
            QDesktopServices.openUrl(QUrl(cb.web_url(self.cvb_host(), self.cvb_model.get("id"), self.cvb_version.currentData())))

    # ------------------------------------------------------------------ download
    def cvb_download(self):
        f = self.cvb_file_info()
        if not f or (self._cvb_dl_w and self._cvb_dl_w.isRunning()):
            return None
        folder = self.cvb_dest_dir()
        if not folder:
            self.notify(tr("Choose a folder to save to"), error=True); return None
        dest = os.path.join(folder, cb.safe_name(f["name"]))
        if os.path.exists(dest):
            self.cvb_dl_status.setText("✓ " + tr("Already downloaded") + f": {dest}")
            self._cvb_finished(dest); return None
        url = cb.download_url(f["url"], self.cvb_host())
        wk = DownloadWorker(url, dest, (self.keys.get("api_key:civitai") or "").strip(), f.get("sha256", ""), self.cvb_opener)
        wk.progress.connect(self._cvb_progress)
        wk.ok.connect(self._cvb_finished)
        wk.failed.connect(self._cvb_failed)
        self.cvb_dl.setEnabled(False); self.cvb_cancel.setEnabled(True); self.cvb_bar.setValue(0)
        part = dest + ".part"
        self.cvb_dl_status.setText((tr("Resuming") if os.path.exists(part) else tr("Downloading")) + f" {f['name']} → {folder}")
        self._cvb_dl_meta = (self.cvb_model, self.cvb_ver, f)
        self._keep(wk); wk.start(); self._cvb_dl_w = wk
        return wk

    def _cvb_progress(self, done, total):
        if total:
            self.cvb_bar.setRange(0, 1000); self.cvb_bar.setValue(int(done * 1000 / total))
            self.cvb_bar.setFormat(f"{cb.human_size(done)} / {cb.human_size(total)}")
        else:
            self.cvb_bar.setRange(0, 0); self.cvb_bar.setFormat(cb.human_size(done))

    def cvb_cancel_download(self):
        if self._cvb_dl_w and self._cvb_dl_w.isRunning():
            self._cvb_dl_w.stop()

    def _cvb_finished(self, path):
        self.cvb_bar.setRange(0, 1000); self.cvb_bar.setValue(1000); self.cvb_bar.setFormat(tr("Done"))
        self.cvb_dl.setEnabled(True); self.cvb_cancel.setEnabled(False)
        if not getattr(self, "_cvb_dl_meta", None) or self._cvb_dl_meta[2].get("name") != os.path.basename(path):
            self._cvb_dl_meta = (self.cvb_model, self.cvb_ver, self.cvb_file_info())
        self._cvb_downloaded = path
        self.cvb_dl_status.setText("✓ " + tr("Saved and SHA256-verified") + f": {path}")
        self.cvb_refresh_btn.setEnabled(True); self.cvb_profile_btn.setEnabled(True)
        self.notify(tr("Download finished") + f": {os.path.basename(path)}")

    def _cvb_failed(self, err):
        self.cvb_dl.setEnabled(True); self.cvb_cancel.setEnabled(False); self.cvb_bar.setRange(0, 1000)
        self.cvb_dl_status.setText(("⏸ " if "cancel" in err.lower() else "⚠️ ") + err[:400])

    def cvb_refresh_models(self):
        if self.store.get("img_backend", "none") == "none":
            self.notify(tr("Set up Forge or ComfyUI in Settings first"), error=True); return
        self.load_checkpoints(force=True)
        self.notify(tr("Refreshing the model list…"))

    def cvb_create_profile(self):
        meta = getattr(self, "_cvb_dl_meta", None)
        if not meta or not meta[0] or not meta[1] or not meta[2]:
            self.notify(tr("Download a model first"), error=True); return None
        m, v, f = meta
        prof = cb.build_profile(m, v, f, dict(self.profiles), self.cvb_host())
        profiles.save_profile(self.profiles_path, prof)
        self._prof_reload(prof["id"])
        i = self.profile_combo.findData(prof["id"])
        if i >= 0:
            self.profile_combo.setCurrentIndex(i)
        self.notify(tr("Profile saved") + f": {prof['name']}")
        return prof
