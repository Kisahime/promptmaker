"""6.1 quality of life: the ADetailer form (Forge ADetailer or ComfyUI Impact Pack FaceDetailer), its presets,
the top-bar ADetailer toggle, and Start Forge / Start ComfyUI."""
import os
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QFileDialog, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from . import backenddetect as bd
from . import imagegen, launchers
from .i18n import tr
from .widgets import CallWorker, button, hrow, label

AD_KINDS = ("a1111", "comfyui")


class QolPages:
    # ================================================================ ADetailer form (Settings -> Image generation)
    def _ad_states(self):
        """{backend kind: None (not checked) / False (no ADetailer) / True (detector list loaded)}."""
        if not hasattr(self, "_ad_state"):
            self._ad_state = {}
        return self._ad_state

    def _ad_form(self, *_):
        """ADetailer works with Forge / A1111 (ADetailer extension) or ComfyUI (Impact Pack FaceDetailer); greyed out otherwise."""
        if not hasattr(self, "ad_on"):
            return
        kind = self.img_kind.currentData()
        found = self._ad_found
        ok = (kind == "a1111" and found is not False) or (kind == "comfyui" and found is True)
        self.ad_on.setEnabled(ok); self.ad_reload.setEnabled(kind in AD_KINDS)
        self.ad_box.setEnabled(ok and self.ad_on.isChecked())
        self.ad2_model.setEnabled(self.ad2_on.isChecked()); self.ad2_denoise.setEnabled(self.ad2_on.isChecked())
        if kind not in AD_KINDS:
            note = tr("ADetailer needs Forge / A1111, or ComfyUI with the Impact Pack.")
        elif kind == "comfyui" and found is False:
            note = tr(imagegen.IMPACT_HINT)
        elif kind == "comfyui" and found is None:
            note = tr("On ComfyUI, ADetailer uses the Impact Pack's FaceDetailer. Press the reload button to check whether ComfyUI has it.")
        elif found is False:
            note = tr("ADetailer wasn't found in Forge. Install the ADetailer extension in Forge, restart it, then reload the list.")
        elif found:
            note = tr("Detector models loaded") + f": {self.ad_model.count()}. " + tr(
                "Denoise 0.3-0.4 keeps the face, confidence 0.3 finds most faces.")
        else:
            note = tr("Runs on every Forge image (not Face Swap). Press the reload button to load your detector models from Forge.")
        self.ad_note.setText(note)
        tip = "" if ok else note
        for wdg in (self.ad_on, self.ad_box):
            wdg.setToolTip(tip)
        self._ad_quick_sync()

    def _ad_models(self):
        kind = self.img_kind.currentData()
        if kind not in AD_KINDS:
            self._ad_form(); return None
        b = imagegen.make_backend(kind, self.img_url.text().strip())
        wk = CallWorker(lambda: b.adetailer_models(refresh=True))
        wk.ok.connect(self._ad_models_loaded); wk.failed.connect(lambda _e: self._ad_models_loaded([]))
        self._keep(wk); wk.start()
        return wk

    def _ad_models_loaded(self, names):
        names = [n for n in (names or []) if n]
        self._ad_found = bool(names)
        if hasattr(self, "img_kind"):
            self._ad_states()[self.img_kind.currentData()] = bool(names)
        for combo, want in ((self.ad_model, imagegen.AD_FACE), (self.ad2_model, imagegen.AD_HAND)):
            if not names:
                break
            cur = combo.currentText()
            pick = cur if cur in names else (imagegen.match_detector(cur, names) or imagegen.match_detector(want, names) or names[0])
            combo.blockSignals(True)
            combo.clear(); combo.addItems(names); combo.setCurrentText(pick)
            combo.blockSignals(False)
        self._ad_form()

    @staticmethod
    def _ad_set_combo(combo, text):
        if combo.findText(text) < 0:
            combo.addItem(text)
        combo.setCurrentText(text)

    def _ad_preset_apply(self, *_):
        """Fill the pass fields from the chosen preset, using only detectors the backend has."""
        key = self.ad_preset.currentData()
        if not key:
            return None
        avail = [self.ad_model.itemText(i) for i in range(self.ad_model.count())] if self._ad_found else None
        passes = imagegen.adetailer_preset(key, avail)
        if not passes:
            self.notify(tr("None of this preset's detectors are installed"), error=True); return None
        self._ad_applying = True
        try:
            self._ad_set_combo(self.ad_model, passes[0]["ad_model"])
            self.ad_denoise.setValue(passes[0]["ad_denoising_strength"]); self.ad_conf.setValue(passes[0]["ad_confidence"])
            if len(passes) > 1:
                self.ad2_on.setChecked(True)
                self._ad_set_combo(self.ad2_model, passes[1]["ad_model"]); self.ad2_denoise.setValue(passes[1]["ad_denoising_strength"])
            else:
                self.ad2_on.setChecked(False)
        finally:
            self._ad_applying = False
        self.store.set("ad_preset", key)
        if len(passes) < len(imagegen.AD_PRESETS[key][1]):
            self.ad_note.setText(tr("Some detectors of this preset aren't installed, so they were left out."))
        return passes

    def _ad_custom(self, *_):
        """Editing a pass by hand turns the preset back to Custom."""
        if getattr(self, "_ad_applying", False) or not hasattr(self, "ad_preset") or self.ad_preset.currentIndex() == 0:
            return
        self.ad_preset.blockSignals(True); self.ad_preset.setCurrentIndex(0); self.ad_preset.blockSignals(False)
        self.store.set("ad_preset", "")

    def _ad_on_toggled(self, on):
        self.store.set("ad_on", bool(on))
        q = getattr(self, "ad_quick", None)
        if q is not None and q.isChecked() != bool(on):
            q.blockSignals(True); q.setChecked(bool(on)); q.blockSignals(False)
        self._ad_form()

    # ================================================================ top bar: quick ADetailer toggle + Start
    def _status_extras(self):
        """Widgets next to the backend status in the top bar."""
        self.be_start = button("▶", self.start_active_backend, "ghost", "Start the image backend")
        self.be_start.hide()
        self.ad_quick = QCheckBox(tr("ADetailer"))
        self.ad_quick.setChecked(bool(self.store.get("ad_on", False)))
        self.ad_quick.toggled.connect(self._ad_quick_toggled)
        self._ad_quick_sync()
        return [self.be_start, self.ad_quick]

    def _ad_quick_toggled(self, on):
        self.store.set("ad_on", bool(on))
        if hasattr(self, "ad_on") and self.ad_on.isChecked() != bool(on):
            self.ad_on.setChecked(bool(on))

    def _ad_quick_sync(self):
        q = getattr(self, "ad_quick", None)
        if q is None:
            return
        kind = self.store.get("img_backend", "none")
        st = self._ad_states().get(kind)
        ok = (kind == "a1111" and st is not False) or (kind == "comfyui" and st is True)
        q.setEnabled(ok)
        if ok:
            tip = tr("ADetailer on / off for every image (the same switch as in Settings - Image generation)")
        elif kind == "a1111":
            tip = tr("ADetailer wasn't found in Forge. Install the ADetailer extension in Forge, restart it, then reload the list.")
        elif kind == "comfyui":
            tip = tr(imagegen.IMPACT_HINT) if st is False else tr("Checking ComfyUI for the Impact Pack FaceDetailer...")
        else:
            tip = tr("ADetailer needs Forge / A1111, or ComfyUI with the Impact Pack.")
        q.setToolTip(tip)

    def _status_changed(self, state):
        """Hook from the backend status poll."""
        self._be_start_sync()
        if state == "online":
            self._ad_check_active()
        self._ad_quick_sync()

    def _ad_check_active(self):
        """Once per backend: ask the running backend for its detector list (fills Settings when it's the same kind)."""
        kind = self.store.get("img_backend", "none")
        if kind not in AD_KINDS or self._ad_states().get(kind) is not None or getattr(self, "_ad_checking", False):
            return None
        b = self.image_backend()
        if not b or not hasattr(b, "adetailer_models"):
            return None
        self._ad_checking = True
        wk = CallWorker(b.adetailer_models)

        def done(names, k=kind):
            self._ad_checking = False
            if hasattr(self, "img_kind") and self.img_kind.currentData() == k:
                self._ad_models_loaded(names)
            else:
                self._ad_states()[k] = bool(names); self._ad_quick_sync()
        wk.ok.connect(done); wk.failed.connect(lambda _e: setattr(self, "_ad_checking", False))
        self._keep(wk); wk.start()
        return wk

    # ================================================================ Start Forge / Start ComfyUI
    def _launcher_rows(self, im):
        self.launch_btns = {
            "a1111": button("▶ Start Forge", lambda: self.start_backend("a1111"), "ghost", "Start Forge in its own window and connect to it"),
            "comfyui": button("▶ Start ComfyUI", lambda: self.start_backend("comfyui"), "ghost", "Start ComfyUI in its own window and connect to it"),
        }
        for b in self.launch_btns.values():
            b.hide()
        self.launch_lbl = label("", "hint", wrap=True)
        self.launch_paths_btn = button("Launcher paths", None, "ghost", "Where Start Forge / Start ComfyUI find their .bat")
        self.launch_paths_btn.setCheckable(True)
        self.launch_box = QWidget(); lay = QVBoxLayout(self.launch_box); lay.setContentsMargins(0, 0, 0, 0)
        self.launch_edit = {}
        for k in launchers.KINDS:
            e = QLineEdit(self.store.get(f"launcher:{k}", "") or ""); e.setMinimumWidth(60)
            e.setPlaceholderText(tr("Not found - choose the launcher"))
            e.editingFinished.connect(lambda k=k: self._launch_path_set(k, self.launch_edit[k].text()))
            name = label(launchers.NAMES[k], "muted"); name.setFixedWidth(84)
            lay.addLayout(hrow(name, e, button("...", lambda k=k: self._launch_browse(k), "ghost", "Choose the launcher (.bat)")))
            self.launch_edit[k] = e
        self.launch_box.hide()
        self.launch_paths_btn.toggled.connect(self.launch_box.setVisible)
        self._launch_timer = QTimer(self); self._launch_timer.timeout.connect(self._launch_poll)
        self._launch_state = None
        im.add(hrow(self.launch_btns["a1111"], self.launch_btns["comfyui"], None))
        im.add(self.launch_lbl)
        im.add(hrow(self.launch_paths_btn, None)); im.add(self.launch_box)
        if os.environ.get("PROMPTMAKER_NO_NET"):
            self._launch_found({k: self._launcher(k) for k in launchers.KINDS})
        else:
            QTimer.singleShot(0, self.launch_scan)

    def _launcher(self, kind):
        p = self.store.get(f"launcher:{kind}", "") or ""
        return p if p and os.path.isfile(p) else ""

    def launch_scan(self, sync=False):
        """Find each backend's launcher (saved path, known folders, then a short search) off the UI thread."""
        saved = {k: self.store.get(f"launcher:{k}", "") or "" for k in launchers.KINDS}

        def scan():
            return {k: launchers.find(k, saved[k]) for k in launchers.KINDS}
        if sync:
            return self._launch_found(scan())
        wk = CallWorker(scan); wk.ok.connect(self._launch_found); self._keep(wk); wk.start()
        return wk

    def _launch_found(self, paths):
        if getattr(self, "_closing", False):
            return None
        for k, p in (paths or {}).items():
            if p:
                self.store.set(f"launcher:{k}", p)
            e = getattr(self, "launch_edit", {}).get(k)
            if e is not None and not e.hasFocus():
                e.setText(p or "")
        self._launch_buttons_sync()
        return paths

    def _launch_buttons_sync(self):
        found = {k: bool(self._launcher(k)) for k in launchers.KINDS}
        for k, b in getattr(self, "launch_btns", {}).items():
            b.setVisible(found[k])
        if hasattr(self, "launch_lbl") and not any(found.values()) and not self._launch_state:
            self.launch_lbl.setText(tr("Forge / ComfyUI weren't found on this PC. Use Launcher paths to choose their .bat file."))
        self._be_start_sync()

    def _launch_path_set(self, kind, path):
        path = (path or "").strip().strip('"')
        if path and not os.path.isfile(path):
            self.notify(tr("That launcher file doesn't exist") + f": {path}", error=True); return False
        self.store.set(f"launcher:{kind}", path)
        self._launch_buttons_sync()
        return True

    def _launch_browse(self, kind):
        start = os.path.dirname(self._launcher(kind)) or os.path.expanduser("~")
        path, _f = QFileDialog.getOpenFileName(self, tr("Choose the launcher"), start,
                                               tr("Launchers") + " (*.bat *.cmd *.sh);;" + tr("All files") + " (*)")
        if path:
            path = os.path.normpath(path)
            self.launch_edit[kind].setText(path); self._launch_path_set(kind, path)
        return path

    def _be_start_sync(self):
        b = getattr(self, "be_start", None)
        if b is None:
            return
        kind = self.store.get("img_backend", "none")
        status = getattr(self, "_status", ("off", ""))[0]
        b.setVisible(bool(self._launcher(kind)) and status == "offline" and not self._launch_state_kind())
        b.setToolTip(tr("Start") + f" {launchers.NAMES.get(kind, '')}")

    def _launch_state_kind(self):
        st = getattr(self, "_launch_state", None)
        return st["kind"] if st else ""

    def start_active_backend(self):
        return self.start_backend(self.store.get("img_backend", "none"))

    def _launch_say(self, text, error=False):
        if hasattr(self, "launch_lbl"):
            self.launch_lbl.setText(text)
        self.notify(text, error=error)

    def start_backend(self, kind):
        """Start Forge / ComfyUI unless it's already running (then just connect); warn when the other one runs."""
        if kind not in launchers.KINDS:
            return None
        name = launchers.NAMES[kind]
        path = self._launcher(kind)
        if not path:
            self._launch_say(tr("No launcher found for") + f" {name}. " + tr("Use Launcher paths to choose its .bat file."), True)
            return None
        if self._launch_state:
            self._launch_say(launchers.NAMES[self._launch_state["kind"]] + " " + tr("is still starting - wait for it first."), True)
            return None
        if hasattr(self, "launch_lbl"):
            self.launch_lbl.setText(tr("Checking what's already running..."))
        cands = bd.candidates(self.store.get)
        wk = CallWorker(lambda: bd.probe(cands, 0.8))
        wk.ok.connect(lambda found, k=kind, p=path: self._launch_checked(k, p, found))
        wk.failed.connect(lambda _e, k=kind, p=path: self._launch_checked(k, p, {}))
        self._keep(wk); wk.start()
        return wk

    def _confirm_launch(self, text):
        if os.environ.get("PROMPTMAKER_NO_DIALOGS"):
            return False
        return QMessageBox.question(self, tr("Start anyway?"), text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def _launch_checked(self, kind, path, found):
        name = launchers.NAMES[kind]
        same = sorted(u for u, k in (found or {}).items() if k == kind)
        other = sorted(u for u, k in (found or {}).items() if k != kind)
        if same:
            self.switch_backend(kind, same[0])
            self._launch_say(f"{name} " + tr("is already running at") + f" {same[0]}. " +
                             tr("Connected to it instead of starting a second copy."))
            return "running"
        if other:
            oname = bd.NAMES.get(found[other[0]], found[other[0]])
            text = (f"{oname} " + tr("is already running") + f" ({other[0]}).\n\n" +
                    tr("Running Forge and ComfyUI at the same time on one GPU can run out of video memory (VRAM), "
                       "especially on an 8 GB card. Close the other one first if images fail or get slow.") + "\n\n" +
                    tr("Start") + f" {name} " + tr("anyway?"))
            if not self._confirm_launch(text):
                self._launch_say(tr("Not started") + f": {name}")
                return "cancelled"
        try:
            proc = launchers.launch(path)
        except OSError as e:
            self._launch_say(tr("Couldn't start") + f" {name}: {e}", True)
            return "failed"
        self._launch_state = {"kind": kind, "start": time.time(), "proc": proc, "busy": False}
        msg = tr("Starting") + f" {name} " + tr("in its own window... the first start can take a few minutes.")
        if kind == "a1111" and launchers.forge_has_api(path) is False:
            msg += " " + tr("Its webui-user.bat has no --api in COMMANDLINE_ARGS, so PromptMaker can't connect until you add it.")
        self._launch_say(msg)
        self._be_start_sync()
        self._launch_timer.start(2000)
        return "started"

    def _launch_stop(self):
        self._launch_timer.stop()
        self._launch_state = None
        self._be_start_sync()

    def _launch_poll(self):
        st = self._launch_state
        if not st:
            self._launch_timer.stop(); return None
        name = launchers.NAMES[st["kind"]]
        proc = st.get("proc")
        if time.time() - st["start"] > launchers.TIMEOUT_S:
            self._launch_stop()
            self._launch_say(f"{name} " + tr("didn't answer within 5 minutes. Check its console window for errors."), True)
            return None
        if proc is not None and getattr(proc, "poll", lambda: None)() is not None:
            self._launch_stop()
            self._launch_say(f"{name} " + tr("stopped before it was ready. Check its console window for errors."), True)
            return None
        if st["busy"]:
            return None
        st["busy"] = True
        cands = [(k, u) for k, u in bd.candidates(self.store.get) if k == st["kind"]]
        wk = CallWorker(lambda: bd.probe(cands, 0.8))
        wk.ok.connect(lambda found, s=st: self._launch_polled(s, found))
        wk.failed.connect(lambda _e, s=st: s.update(busy=False))
        self._keep(wk); wk.start()
        return wk

    def _launch_polled(self, st, found):
        st["busy"] = False
        if st is not self._launch_state:
            return None
        urls = sorted(u for u, k in (found or {}).items() if k == st["kind"])
        if not urls:
            return None
        kind = st["kind"]
        self._launch_stop()
        self.switch_backend(kind, urls[0])
        self._launch_say(f"{launchers.NAMES[kind]} " + tr("is ready") + f" ({urls[0]})")
        self._ad_states().pop(kind, None)
        self._ad_check_active()
        return urls[0]
