"""PromptMaker 3.0 UI: setup wizard, auto-refine loop, LoRA manager, character/style presets, pose sketcher.

Mixed into MainWindow; uses the same Card / button / toast / ConfirmButton patterns as the rest of the app."""
import os
import urllib.request

from PySide6.QtCore import QThread, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QSpinBox, QSplitter,
                               QVBoxLayout, QWidget)

from . import autorefine, firstrun, imagegen, loras, pose, presets
from .i18n import tr
from .posecanvas import PoseCanvas
from .widgets import Card, ConfirmButton, button, hrow, label


def _page(title, subtitle=""):
    w = QWidget()
    v = QVBoxLayout(w); v.setContentsMargins(26, 20, 26, 20); v.setSpacing(14)
    v.addWidget(label(title, "h1"))
    if subtitle:
        v.addWidget(label(subtitle, "muted", wrap=True))
    return w, v


def _pix(png_or_path, size):
    img = QImage(png_or_path) if isinstance(png_or_path, str) else QImage.fromData(png_or_path)
    return QPixmap.fromImage(img).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not img.isNull() else QPixmap()


# ================================================================ workers
class PullWorker(QThread):
    progress = Signal(int, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, name, base):
        super().__init__(); self.name, self.base, self._stop = name, base, False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            ok = firstrun.pull(self.name, self.base, lambda p, s: self.progress.emit(p, s), lambda: self._stop)
            self.done.emit(self.name if ok else "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class LoopWorker(QThread):
    step = Signal(object)
    status = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, idea, prompt, make_job, backend, wf, provider, vision_model, text_model, profile, iters, threshold):
        super().__init__()
        self.a = (idea, prompt); self.make_job, self.backend, self.wf = make_job, backend, wf
        self.provider, self.vm, self.tm, self.profile = provider, vision_model, text_model, profile
        self.iters, self.threshold, self._stop = iters, threshold, False
        self.seed = imagegen.new_seed()

    def stop(self):
        self._stop = True
        if hasattr(self.backend, "cancel"):
            self.backend.cancel()

    def _chat(self, model, msgs, json_mode=False):
        return "".join(self.provider.stream_chat(model, msgs, temperature=0.3 if json_mode else 0.6, json_mode=json_mode,
                                                 stop_flag=lambda: self._stop))

    def run(self):
        def gen(p):
            self.status.emit(tr("Generating image…"))
            job = self.make_job(p, self.seed)
            return self.backend.generate(job, self.wf, cancelled=lambda: self._stop)[0]

        def judge(idea, p, png):
            self.status.emit(tr("Vision model is checking the image…"))
            return autorefine.parse_judgement(self._chat(self.vm, autorefine.judge_messages(idea, p, png), True))

        def rewrite(idea, p, j):
            self.status.emit(tr("Rewriting the prompt…"))
            return autorefine.clean_prompt(self._chat(self.tm, autorefine.rewrite_messages(idea, p, j, self.profile)))
        try:
            res = autorefine.run(*self.a, gen, judge, rewrite, self.iters, self.threshold, lambda: self._stop, self.step.emit)
            self.done.emit(res)
        except imagegen.Cancelled:
            self.done.emit({"steps": [], "best": None, "reason": "stopped"})
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, root, cache, client, preview_dir):
        super().__init__(); self.root, self.cache, self.client, self.preview_dir, self._stop = root, cache, client, preview_dir, False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            items = loras.scan(self.root)
            loras.enrich(items, self.cache, self.client, self.progress.emit, lambda: self._stop)
            for it in items:
                url = (it.get("info") or {}).get("preview")
                dest = os.path.join(self.preview_dir, it.get("sha256", "x")[:16] + ".img")
                if url and self.client is not None and not os.path.exists(dest) and not self._stop:
                    try:
                        os.makedirs(self.preview_dir, exist_ok=True)
                        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PromptMaker"}), timeout=15) as r:
                            data = r.read()
                        with open(dest, "wb") as f:
                            f.write(data)
                    except OSError:
                        pass
                it["preview_file"] = dest if os.path.exists(dest) else ""
            self.done.emit(items)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# ================================================================ setup wizard
class SetupWizard(QDialog):
    def __init__(self, win, auto_check=True):
        super().__init__(win)
        self.win, self.res, self.pull_worker = win, None, None
        self.setWindowTitle(tr("PromptMaker setup")); self.resize(720, 560)
        v = QVBoxLayout(self); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(12)
        v.addWidget(label("Welcome to PromptMaker 3.0", "h1"))
        v.addWidget(label("This checks what's on your PC. Everything is optional except an AI model for the AI features – "
                          "the offline Builder works without anything.", "muted", wrap=True))
        o = Card("1 · Ollama (local AI)")
        self.ol_status = label("…", wrap=True); o.add(self.ol_status)
        self.ol_models = label("", "hint", wrap=True); o.add(self.ol_models)
        self.pull_text = button(f"⬇ Pull {firstrun.RECOMMENDED_TEXT} (text)", lambda: self.pull(firstrun.RECOMMENDED_TEXT))
        self.pull_vision = button(f"⬇ Pull {firstrun.RECOMMENDED_VISION} (vision)", lambda: self.pull(firstrun.RECOMMENDED_VISION))
        self.pull_stop = button("■ Stop", self.stop_pull, "ghost"); self.pull_stop.setEnabled(False)
        o.add(hrow(self.pull_text, self.pull_vision, self.pull_stop, None))
        self.pull_bar = QProgressBar(); self.pull_bar.setVisible(False); o.add(self.pull_bar)
        self.pull_lbl = label("", "hint", wrap=True); o.add(self.pull_lbl)
        v.addWidget(o)
        g = Card("2 · Image generation (optional)")
        self.forge_lbl = label("…", wrap=True); g.add(self.forge_lbl)
        self.forge_hint = label("", "hint", wrap=True); g.add(self.forge_hint)
        self.comfy_lbl = label("…", wrap=True); g.add(self.comfy_lbl)
        v.addWidget(g)
        v.addStretch()
        self.recheck = button("⟳ Check again", self.check)
        v.addLayout(hrow(button("Skip", self.reject, "ghost"), None, self.recheck, button("✓ Save && finish", self.finish, "primary")))
        if auto_check:
            QTimer.singleShot(0, self.check)

    def _urls(self):
        st = self.win.store
        return (getattr(self.win.provider, "base_url", firstrun.OLLAMA_URL) if self.win.provider.kind == "ollama" else firstrun.OLLAMA_URL,
                st.get("img_url:a1111", firstrun.FORGE_URL), st.get("img_url:comfyui", firstrun.COMFY_URL))

    def check(self):
        self.ol_status.setText(tr("Checking…")); self.recheck.setEnabled(False)
        from .widgets import CallWorker
        w = CallWorker(firstrun.run_all, *self._urls())
        w.ok.connect(self.show_results); w.failed.connect(lambda e: self.ol_status.setText("⚠️ " + e))
        self.win._keep(w); w.start()

    def show_results(self, res):
        self.res = res; self.recheck.setEnabled(True)
        o = res["ollama"]
        if o["running"]:
            self.ol_status.setText(f"✅ {tr('Ollama is running')}" + (f" · v{o['version']}" if o["version"] else ""))
        elif o["installed"]:
            self.ol_status.setText("⚠️ " + tr("Ollama is installed but not running – start the Ollama app, then Check again."))
        else:
            self.ol_status.setText("❌ " + tr("Ollama not found. Install it free from https://ollama.com/download, then Check again."))
        self.ol_models.setText((tr("Models") + ": " + ", ".join(o["models"])) if o["models"] else tr("No models yet."))
        self.pull_text.setEnabled(o["running"] and not firstrun.has_model(o["models"], firstrun.RECOMMENDED_TEXT))
        self.pull_vision.setEnabled(o["running"] and not firstrun.has_model(o["models"], firstrun.RECOMMENDED_VISION))
        f, c = res["forge"], res["comfyui"]
        self.forge_lbl.setText(("✅ " + f["message"]) if f["api"] else ("⚠️ " + tr("Forge/A1111 found but its API is off")) if f["found"]
                               else "○ " + tr("Forge / A1111 not detected on") + f" {self._urls()[1]}")
        self.forge_hint.setText((tr("Fix: add --api in webui-user.bat") + f" ({f['hint']}) " + tr("and restart the WebUI.")) if f["found"] and not f["api"] else "")
        self.comfy_lbl.setText(("✅ " + c["message"]) if c["found"] else "○ " + tr("ComfyUI not detected on") + f" {self._urls()[2]}")

    def pull(self, name):
        if self.pull_worker and self.pull_worker.isRunning():
            return
        self.pull_worker = PullWorker(name, self._urls()[0])
        self.pull_bar.setVisible(True); self.pull_bar.setRange(0, 0); self.pull_stop.setEnabled(True)
        self.pull_worker.progress.connect(self._pull_progress)
        self.pull_worker.done.connect(lambda n: (self._pull_end(), n and self.pull_bar.setValue(100), self.win.notify(f"{n} " + tr("downloaded")) if n else None, self.check()))
        self.pull_worker.failed.connect(lambda e: (self._pull_end(), self.pull_lbl.setText("⚠️ " + e), self.win.notify(e, error=True)))
        self.win._keep(self.pull_worker); self.pull_worker.start()

    def _pull_progress(self, pct, status):
        if pct < 0:
            self.pull_bar.setRange(0, 0)
        else:
            self.pull_bar.setRange(0, 100); self.pull_bar.setValue(pct)
        self.pull_lbl.setText(status)

    def _pull_end(self):
        self.pull_stop.setEnabled(False); self.pull_bar.setRange(0, 100)

    def stop_pull(self):
        if self.pull_worker:
            self.pull_worker.stop()

    def finish(self):
        if self.res:
            kind = firstrun.save_results(self.win.store, self.res, *self._urls()[1:])
            if hasattr(self.win, "img_kind"):
                self.win.img_kind.setCurrentIndex(max(0, self.win.img_kind.findData(kind)))
            self.win.refresh_models_async()
        else:
            self.win.store.set("setup_done", True)
        self.win.notify(tr("Setup saved"))
        self.accept()

    def closeEvent(self, e):
        self.stop_pull(); super().closeEvent(e)


# ================================================================ mixin
class V3Pages:
    # ---------------------------------------------------------------- helpers shared by the v3 features
    def open_setup(self, auto_check=True):
        self.setup_dlg = SetupWizard(self, auto_check); self.setup_dlg.open()
        return self.setup_dlg

    SIZE_CHOICES = (("Model default", None), ("1024×1024 square", (1024, 1024)), ("1344×768 wide", (1344, 768)),
                    ("1216×832 landscape", (1216, 832)), ("1152×896 landscape", (1152, 896)), ("832×1216 portrait", (832, 1216)),
                    ("896×1152 portrait", (896, 1152)), ("768×1344 tall", (768, 1344)), ("512×768 portrait (SD1.5)", (512, 768)),
                    ("512×512 square (SD1.5)", (512, 512)))

    def make_size_combo(self, store_key=None):
        """Image size picker. 'Model default' = the profile's size for the aspect picked on the main page."""
        c = QComboBox()
        for name, wh in self.SIZE_CHOICES:
            c.addItem(tr(name), wh)
        if store_key:
            c.setCurrentIndex(max(0, min(int(self.store.get(store_key, 0) or 0), c.count() - 1)))
            c.currentIndexChanged.connect(lambda i: self.store.set(store_key, i))
        c.setToolTip(tr("Model default uses the profile's size for the aspect ratio chosen on the main page"))
        return c

    def make_job(self, prompt, negative="", seed=None, tag=""):
        """Build an imagegen.Job for the current profile/backend. Returns (job, backend, workflow) or None."""
        import re
        prompt = (prompt or "").strip()
        backend = self.image_backend()
        if not prompt or not backend:
            return None
        if seed in (None, "", -1):
            seed = imagegen.new_seed()
        if hasattr(self, "expand_wildcards"):  # v4: __wildcards__ / {a|b} use the image seed, so they're reproducible
            prompt = self.expand_wildcards(prompt, seed)
        a1 = isinstance(backend, imagegen.A1111)
        wf, meta, wf_name = (None, {}, "") if a1 else self._workflow()
        d = meta.get("defaults", {})
        w, h = self._size_for_profile()
        clean = re.sub(r"\s--\w+(\s+[^-\s][^\s]*)?", "", prompt) if "--" in prompt else prompt
        g = self.profile.get("gen") or {}
        job = imagegen.Job(clean, negative, w, h, seed, g.get("steps") or self.store.get("img_steps") or d.get("steps", 25),
                           g.get("cfg") or self.store.get("img_cfg") or d.get("cfg", 6.0), self.profile["name"],
                           self.store.get(f"img_checkpoint:{wf_name or 'a1111'}") or d.get("checkpoint", ""), wf_name or "a1111",
                           (g.get("a1111_sampler") if a1 else g.get("sampler")) or self.store.get("img_sampler") or d.get("sampler", "euler"),
                           g.get("scheduler") or d.get("scheduler", "normal"), tag)
        if g.get("clip_skip"):
            job.clip_skip = g["clip_skip"]
        job.backend_name = backend.name
        return job, backend, wf

    def _default_negative(self):
        return self.negative.toPlainText() if self.profile.get("negative") in ("supported", "optional", "limited") else ""

    def _insert_text(self, text, target):
        if target == "work":
            self.set_work(loras.insert_into(self.work.toPlainText(), text), "inserted"); self.go("Refine")
        elif target == "create" and hasattr(self, "c_prompt"):
            self.c_prompt.setPlainText(loras.insert_into(self.c_prompt.toPlainText(), text))
        else:
            from .app import copy
            copy(text)
        self.notify(tr("Inserted") if target in ("work", "create") else tr("Copied"))

    def _target_combo(self):
        c = QComboBox()
        for key, name in (("work", "Working prompt (Refine)"), ("create", "Create result"), ("copy", "Clipboard")):
            c.addItem(tr(name), key)
        return c

    # ---------------------------------------------------------------- Auto-refine
    def _autorefine_page(self):
        w, v = _page("Auto-refine", "Generate → a vision model checks the image against your idea → the AI rewrites the prompt → "
                                    "repeat until it's good enough. Needs ComfyUI or Forge/A1111 and a vision model.")
        top = Card()
        self.ar_idea = QPlainTextEdit(); self.ar_idea.setPlaceholderText(tr("Your idea, in plain words")); self.ar_idea.setFixedHeight(60)
        self.ar_prompt = QPlainTextEdit(); self.ar_prompt.setPlaceholderText(tr("Starting prompt (leave empty to use the idea)"))
        self.ar_prompt.setFixedHeight(70)
        top.add(label("Idea", "groupLabel")); top.add(self.ar_idea)
        top.add(hrow(label("Starting prompt", "groupLabel"), None,
                     button("From Create", lambda: self.ar_prompt.setPlainText(self.c_prompt.toPlainText()), "ghost"),
                     button("From Refine", lambda: self.ar_prompt.setPlainText(self.work.toPlainText()), "ghost")))
        top.add(self.ar_prompt)
        self.ar_vision = QComboBox(); self.ar_vision.setEditable(True); self.ar_vision.setMinimumWidth(200)
        self.ar_vision.setCurrentText(self.store.get(f"vision_model:{self.provider.pid}") or firstrun.RECOMMENDED_VISION)
        self.ar_iters = QSpinBox(); self.ar_iters.setRange(1, 12); self.ar_iters.setValue(self.store.get("ar_iters", 4))
        self.ar_thresh = QSpinBox(); self.ar_thresh.setRange(10, 100); self.ar_thresh.setSuffix(" / 100")
        self.ar_thresh.setValue(self.store.get("ar_threshold", 85))
        self.ar_start = button("▶ Start loop", self.ar_run, "primary")
        self.ar_stop = button("■ Stop", self.ar_stop_loop, "ghost"); self.ar_stop.setEnabled(False)
        self.ar_ckpt = self.make_ckpt_combo()
        self.ar_size = self.make_size_combo("ar_size")
        top.add(hrow(label("Checkpoint"), self.ar_ckpt, button("⟳", self.load_checkpoints, "ghost", "Reload checkpoint list"),
                     label("Shared with Settings and Pose", "hint"), None, label("Size"), self.ar_size))
        top.add(hrow(label("Vision model"), self.ar_vision, label("Iterations"), self.ar_iters, label("Stop at score"), self.ar_thresh,
                     None, self.ar_stop, self.ar_start))
        self.ar_status = label("", "muted", wrap=True); top.add(self.ar_status)
        v.addWidget(top)
        split = QSplitter(Qt.Horizontal)
        lc = Card("Iterations"); self.ar_list = QListWidget(); self.ar_list.setIconSize(QSize(72, 72))
        self.ar_list.currentRowChanged.connect(self._ar_show); lc.add(self.ar_list, 1); split.addWidget(lc)
        dc = Card("Selected iteration")
        self.ar_img = label("No image yet"); self.ar_img.setAlignment(Qt.AlignCenter); self.ar_img.setMinimumHeight(235)
        self.ar_detail = label("", "hint", wrap=True); self.ar_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dc.add(self.ar_img, 1); dc.add(self.ar_detail)
        dc.add(hrow(button("🏆 Keep best", self.ar_keep_best, "primary"), button("Use selected", self.ar_use_selected),
                    button("📋 Copy prompt", lambda: self._ar_cur() and self._insert_text(self._ar_cur()["prompt"], "copy"), "ghost"), None))
        split.addWidget(dc); split.setSizes([380, 620])
        v.addWidget(split, 1)
        self.ar_steps, self.ar_worker = [], None
        return w

    def _ar_cur(self):
        r = self.ar_list.currentRow()
        return self.ar_steps[r] if 0 <= r < len(self.ar_steps) else None

    def ar_run(self):
        idea = self.ar_idea.toPlainText().strip()
        if not idea:
            self.notify(tr("Describe your idea first"), error=True); return
        backend = self.image_backend()
        if not backend:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return
        tm, vm = self.model.currentText(), self.ar_vision.currentText().strip()
        if not tm or not vm:
            self.notify(tr("Pick a text model in the sidebar and a vision model here"), error=True); return
        self.store.set("ar_iters", self.ar_iters.value()); self.store.set("ar_threshold", self.ar_thresh.value())
        neg = self._default_negative()
        tmpl, _, wf = self.make_job("x", neg, None, "autorefine")  # read settings here: SQLite is main-thread only
        wh = self.ar_size.currentData()
        if wh:
            tmpl.width, tmpl.height = wh

        def job_for(p, seed):
            import copy as _copy
            import re
            import uuid
            j = _copy.copy(tmpl)
            j.prompt = re.sub(r"\s--\w+(\s+[^-\s][^\s]*)?", "", p) if "--" in p else p
            j.seed, j.id = seed, uuid.uuid4().hex[:8]
            return j
        self.ar_steps = []; self.ar_list.clear()
        self.ar_worker = LoopWorker(idea, self.ar_prompt.toPlainText().strip() or idea,
                                    job_for, backend, wf, self.provider,
                                    vm, tm, self.profile, self.ar_iters.value(), self.ar_thresh.value())
        self.ar_worker.step.connect(self._ar_step); self.ar_worker.status.connect(self.ar_status.setText)
        self.ar_worker.done.connect(self._ar_done)
        self.ar_worker.failed.connect(lambda e: (self._ar_end(), self.ar_status.setText("⚠️ " + e[:300]), self.notify(e[:200], error=True)))
        self.ar_start.setEnabled(False); self.ar_stop.setEnabled(True)
        self._keep(self.ar_worker); self.ar_worker.start()

    def _ar_step(self, rec):
        path = self.gallery.save(rec["image"], {"prompt": rec["prompt"], "profile": self.profile["name"], "tag": "autorefine",
                                                "score": rec["score"], "iteration": rec["i"]})
        rec["path"] = path
        self.ar_steps.append(rec)
        it = QListWidgetItem(QIcon(_pix(rec["image"], 72)), f"#{rec['i']} · {rec['score']}/100\n{rec['prompt'][:90]}")
        self.ar_list.addItem(it); self.ar_list.setCurrentRow(self.ar_list.count() - 1)
        self.store.add_history(rec["prompt"], self.profile["name"], f"autorefine #{rec['i']} ({rec['score']})")

    def _ar_show(self, row):
        rec = self._ar_cur()
        if not rec:
            return
        self.ar_img.setPixmap(_pix(rec["image"], 230))
        j = rec["judgement"]
        self.ar_detail.setText(f"{tr('Score')}: {rec['score']}/100\n{tr('Matches')}: {', '.join(j['matches']) or '–'}\n"
                               f"{tr('Missing')}: {', '.join(j['missing']) or '–'}\n{tr('Wrong')}: {', '.join(j['wrong']) or '–'}\n"
                               f"{tr('Advice')}: {j['advice'] or '–'}\n\n{rec['prompt']}")

    def _ar_done(self, res):
        self._ar_end()
        best = res.get("best")
        why = {"threshold": tr("reached the target score"), "stopped": tr("stopped"), "iterations": tr("finished all iterations")}[res["reason"]]
        self.ar_status.setText(f"{why}" + (f" · {tr('best')}: #{best['i']} ({best['score']}/100)" if best else ""))
        if best:
            self.ar_list.setCurrentRow(best["i"] - 1)
        self.load_gallery()

    def _ar_end(self):
        self.ar_start.setEnabled(True); self.ar_stop.setEnabled(False)

    def ar_stop_loop(self):
        if self.ar_worker:
            self.ar_worker.stop(); self.ar_status.setText(tr("Stopping after the current step…"))

    def ar_keep_best(self):
        if not self.ar_steps:
            return
        best = max(self.ar_steps, key=lambda r: (r["score"], -r["i"]))
        self.ar_list.setCurrentRow(best["i"] - 1); self.ar_use_selected()
        self.store.add_favourite(f"Auto-refine best ({best['score']})", best["prompt"])

    def ar_use_selected(self):
        rec = self._ar_cur()
        if rec:
            self.set_work(rec["prompt"], f"auto-refine #{rec['i']} ({rec['score']}/100)"); self.notify(tr("Sent to Refine"))

    # ---------------------------------------------------------------- LoRA manager
    def _loras_page(self):
        w, v = _page("LoRAs", "Scan your LoRA and embedding folders. Files are hashed (SHA256 / AutoV2) and looked up on Civitai for "
                              "names, trigger words and previews; results are cached.")
        top = Card()
        self.lora_root = QLineEdit(self.store.get("lora_root") or loras.DEFAULT_ROOT)
        top.add(hrow(label("Models folder"), self.lora_root, button("📂", self._lora_browse, "ghost"),
                     button("⟳ Scan", self.lora_scan, "primary")))
        self.lora_online = QCheckBox(tr("Look up on Civitai")); self.lora_online.setChecked(self.store.get("lora_online", True))
        self.lora_filter = QComboBox()
        for k, n in (("compat", "Compatible with target model"), ("all", "All")):
            self.lora_filter.addItem(tr(n), k)
        self.lora_strict = QCheckBox(tr("Exact base model only"))
        self.lora_search = QLineEdit(); self.lora_search.setPlaceholderText(tr("Search name or trigger word"))
        for sig in (self.lora_filter.currentIndexChanged, self.lora_strict.toggled, self.lora_search.textChanged):
            sig.connect(self.lora_render)
        top.add(hrow(self.lora_online, label("Show"), self.lora_filter, self.lora_strict, self.lora_search))
        self.lora_bar = QProgressBar(); self.lora_bar.setVisible(False); top.add(self.lora_bar)
        self.lora_status = label("", "hint", wrap=True); top.add(self.lora_status)
        v.addWidget(top)
        split = QSplitter(Qt.Horizontal)
        lc = Card(); self.lora_list = QListWidget(); self.lora_list.setIconSize(QSize(56, 56))
        self.lora_list.currentRowChanged.connect(self._lora_show); lc.add(self.lora_list, 1); split.addWidget(lc)
        dc = Card("Details")
        self.lora_prev = label(""); self.lora_prev.setAlignment(Qt.AlignCenter); self.lora_prev.setMinimumHeight(200)
        self.lora_info = label("", wrap=True); self.lora_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lora_weight = QDoubleSpinBox(); self.lora_weight.setRange(-2, 2); self.lora_weight.setSingleStep(0.05); self.lora_weight.setValue(0.8)
        self.lora_words = QCheckBox(tr("Include trigger words")); self.lora_words.setChecked(True)
        self.lora_target = self._target_combo()
        dc.add(self.lora_prev, 1); dc.add(self.lora_info)
        dc.add(hrow(label("Weight"), self.lora_weight, self.lora_words, None))
        dc.add(hrow(label("Insert into"), self.lora_target, None, button("➕ Insert", self.lora_insert, "primary")))
        split.addWidget(dc); split.setSizes([460, 540])
        v.addWidget(split, 1)
        self.lora_items, self.lora_shown, self.lora_worker = [], [], None
        cache = loras.Cache(self._lora_cache_path())
        if cache.data["hashes"]:
            self.lora_status.setText(tr("Click Scan to load your LoRAs (hashes are cached, so rescans are quick)."))
        return w

    def _lora_cache_path(self):
        return os.path.join(self.data_dir, "cache", "loras.json")

    def _lora_browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("Choose your models folder"), self.lora_root.text())
        if d:
            self.lora_root.setText(d)

    def lora_scan(self):
        root = self.lora_root.text().strip()
        self.store.set("lora_root", root); self.store.set("lora_online", self.lora_online.isChecked())
        if not any(loras.folders(root).values()):
            self.notify(tr("No Lora or embeddings folder found there"), error=True)
            self.lora_status.setText(tr("Expected") + f" {os.path.join(root, 'Lora')} " + tr("or") + f" {os.path.join(root, 'embeddings')}")
            return
        client = None
        if self.lora_online.isChecked() and not os.environ.get("PROMPTMAKER_NO_NET"):
            client = self.civitai_client()
        self.lora_worker = ScanWorker(root, loras.Cache(self._lora_cache_path()), client,
                                      os.path.join(self.data_dir, "cache", "lora_previews"))
        self.lora_bar.setVisible(True); self.lora_bar.setRange(0, 0)
        self.lora_worker.progress.connect(lambda i, n, name: (self.lora_bar.setRange(0, n), self.lora_bar.setValue(i),
                                                              self.lora_status.setText(f"{tr('Hashing')} {name}…")))
        self.lora_worker.done.connect(self._lora_loaded)
        self.lora_worker.failed.connect(lambda e: (self.lora_bar.setVisible(False), self.lora_status.setText("⚠️ " + e[:300])))
        self._keep(self.lora_worker); self.lora_worker.start()

    def _lora_loaded(self, items):
        self.lora_bar.setVisible(False); self.lora_items = items
        found = sum(1 for i in items if (i.get("info") or {}).get("found"))
        self.lora_status.setText(f"{len(items)} {tr('file(s)')} · {found} {tr('identified on Civitai')}")
        self.lora_render()

    def lora_render(self, *_):
        if not hasattr(self, "lora_list"):
            return
        q = self.lora_search.text().strip().lower(); mode = self.lora_filter.currentData()
        self.lora_shown = []
        self.lora_list.clear()
        for it in self.lora_items:
            info = it.get("info") or {}
            comp = loras.compatible(it, self.profile, self.profiles, self.lora_strict.isChecked())
            if mode == "compat" and comp is False:
                continue
            hay = " ".join([it["name"], info.get("name", ""), *info.get("trained_words", [])]).lower()
            if q and q not in hay:
                continue
            mark = {True: "✅", False: "⛔", None: "❔"}[comp]
            text = f"{mark} {info.get('name') or it['name']}  ·  {it['kind']}" + (f" · {info['base_model']}" if info.get("base_model") else "")
            li = QListWidgetItem(text)
            if it.get("preview_file"):
                li.setIcon(QIcon(_pix(it["preview_file"], 56)))
            self.lora_list.addItem(li); self.lora_shown.append(it)

    def _lora_cur(self):
        r = self.lora_list.currentRow()
        return self.lora_shown[r] if 0 <= r < len(self.lora_shown) else None

    def _lora_show(self, _):
        it = self._lora_cur()
        if not it:
            return
        info = it.get("info") or {}
        self.lora_prev.setPixmap(_pix(it["preview_file"], 260) if it.get("preview_file") else QPixmap())
        if not it.get("preview_file"):
            self.lora_prev.setText(tr("No preview"))
        lines = [f"<b>{info.get('name') or it['name']}</b> {info.get('version', '')}", f"{tr('File')}: {it['path']}",
                 f"AutoV2: {it.get('autov2', '?')} · SHA256: {it.get('sha256', '?')[:16]}…",
                 f"{tr('Base model')}: {info.get('base_model') or tr('unknown')}",
                 f"{tr('Trigger words')}: {', '.join(info.get('trained_words') or []) or '–'}"]
        if info.get("url"):
            lines.append(f"<a style='color:#9479ff' href='{info['url']}'>{tr('Open on Civitai')}</a>")
        elif info.get("found") is False:
            lines.append(tr("Not found on Civitai (private or renamed file)."))
        self.lora_info.setText("<br>".join(lines)); self.lora_info.setOpenExternalLinks(True)

    def lora_insert(self):
        it = self._lora_cur()
        if it:
            self._insert_text(loras.insert_text(it, self.lora_weight.value(), self.lora_words.isChecked()), self.lora_target.currentData())

    # ---------------------------------------------------------------- Presets
    def _presets_page(self):
        w, v = _page("Presets", "Save characters and styles once and drop them into any prompt. Tick several to combine them – "
                                "Batch can keep them fixed on every variation.")
        row = QHBoxLayout(); row.setSpacing(14)
        cc = Card("Characters")
        self.ch_list = QListWidget(); self.ch_list.currentRowChanged.connect(self._ch_selected); self.ch_list.setMaximumHeight(170)
        cc.add(self.ch_list)
        self.ch_name, self.ch_app, self.ch_outfit = QLineEdit(), QPlainTextEdit(), QPlainTextEdit()
        self.ch_app.setFixedHeight(54); self.ch_outfit.setFixedHeight(44)
        self.ch_app.setPlaceholderText(tr("Appearance tags, e.g. silver hair, red eyes, freckles"))
        self.ch_outfit.setPlaceholderText(tr("Outfit, e.g. black kimono, red obi"))
        self.ch_lora = QComboBox(); self.ch_lora.setEditable(True)
        self.ch_lw = QDoubleSpinBox(); self.ch_lw.setRange(-2, 2); self.ch_lw.setSingleStep(0.05); self.ch_lw.setValue(0.8)
        self.ch_ref = QLineEdit(); self.ch_ref.setPlaceholderText(tr("Reference image (optional)"))
        self.ch_thumb = label(""); self.ch_thumb.setFixedSize(64, 64)
        cc.add(hrow(label("Name"), self.ch_name)); cc.add(self.ch_app); cc.add(self.ch_outfit)
        cc.add(hrow(label("LoRA"), self.ch_lora, label("Weight"), self.ch_lw))
        cc.add(hrow(self.ch_ref, button("📂", self._ch_browse, "ghost"), self.ch_thumb))
        cc.add(hrow(button("💾 Save", self.ch_save, "primary"), button("New", self.ch_new, "ghost"), None,
                    ConfirmButton("🗑 Delete", self.ch_delete, "Confirm delete")))
        row.addWidget(cc, 1)
        sc = Card("Styles")
        self.st_list = QListWidget(); self.st_list.currentRowChanged.connect(self._st_selected); self.st_list.setMaximumHeight(170)
        sc.add(self.st_list)
        self.st_name, self.st_tags, self.st_neg = QLineEdit(), QPlainTextEdit(), QPlainTextEdit()
        self.st_tags.setPlaceholderText(tr("Style tags, e.g. watercolor, soft pastel palette, film grain"))
        self.st_neg.setPlaceholderText(tr("Extra negative (optional)"))
        self.st_tags.setFixedHeight(70); self.st_neg.setFixedHeight(44)
        sc.add(hrow(label("Name"), self.st_name)); sc.add(self.st_tags); sc.add(self.st_neg)
        sc.lay.addStretch()
        sc.add(hrow(button("💾 Save", self.st_save, "primary"), button("New", self.st_new, "ghost"), None,
                    ConfirmButton("🗑 Delete", self.st_delete, "Confirm delete")))
        row.addWidget(sc, 1)
        v.addLayout(row)
        uc = Card("Use · ticked characters and styles are combined")
        self.pr_in = QPlainTextEdit(); self.pr_in.setPlaceholderText(tr("Scene prompt, e.g. standing in a shrine at sunset"))
        self.pr_in.setFixedHeight(56)
        self.pr_out = QPlainTextEdit(); self.pr_out.setReadOnly(True); self.pr_out.setFixedHeight(70)
        self.pr_target = self._target_combo()
        uc.add(self.pr_in)
        uc.add(hrow(button("✨ Combine", self.pr_combine, "primary"), label("Send to"), self.pr_target,
                    button("➕ Insert", lambda: self.pr_out.toPlainText() and self._insert_text(self.pr_out.toPlainText(), self.pr_target.currentData())),
                    None))
        uc.add(self.pr_out)
        v.addWidget(uc)
        v.addStretch()
        self.ch_id = self.st_id = None
        self.load_presets()
        self.ch_list.itemChanged.connect(self._presets_checked); self.st_list.itemChanged.connect(self._presets_checked)
        return w

    def load_presets(self):
        checked_c = set(self.store.get("presets_active_chars", [])); checked_s = set(self.store.get("presets_active_styles", []))
        for lst, rows, checked in ((self.ch_list, self.store.characters(), checked_c), (self.st_list, self.store.styles(), checked_s)):
            lst.blockSignals(True); lst.clear()
            for r in rows:
                it = QListWidgetItem(r["name"]); it.setData(Qt.UserRole, r["id"]); it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if r["id"] in checked else Qt.Unchecked); lst.addItem(it)
            lst.blockSignals(False)

    def _presets_checked(self, *_):
        self.store.set("presets_active_chars", [self.ch_list.item(i).data(Qt.UserRole) for i in range(self.ch_list.count())
                                                if self.ch_list.item(i).checkState() == Qt.Checked])
        self.store.set("presets_active_styles", [self.st_list.item(i).data(Qt.UserRole) for i in range(self.st_list.count())
                                                 if self.st_list.item(i).checkState() == Qt.Checked])

    def active_presets(self):
        chars = [c for c in self.store.characters() if c["id"] in set(self.store.get("presets_active_chars", []))]
        styles = [s for s in self.store.styles() if s["id"] in set(self.store.get("presets_active_styles", []))]
        return chars, styles

    def _ch_selected(self, row):
        it = self.ch_list.item(row)
        c = self.store.character(it.data(Qt.UserRole)) if it else None
        if not c:
            return
        self.ch_id = c["id"]; self.ch_name.setText(c["name"]); self.ch_app.setPlainText(c["appearance"])
        self.ch_outfit.setPlainText(c["outfit"]); self.ch_lora.setCurrentText(c["lora"]); self.ch_lw.setValue(c["lora_weight"] or 0.8)
        self.ch_ref.setText(c["ref_image"]); self._ch_thumb()

    def _ch_thumb(self):
        p = self.ch_ref.text().strip()
        self.ch_thumb.setPixmap(_pix(p, 64) if p and os.path.exists(p) else QPixmap())

    def _ch_browse(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Reference image"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        if f:
            self.ch_ref.setText(f); self._ch_thumb()

    def ch_new(self):
        self.ch_id = None
        for x in (self.ch_name, self.ch_ref):
            x.clear()
        self.ch_app.clear(); self.ch_outfit.clear(); self.ch_lora.setCurrentText(""); self.ch_lw.setValue(0.8); self._ch_thumb()

    def ch_save(self):
        try:
            self.ch_id = self.store.save_character({"name": self.ch_name.text().strip(), "appearance": self.ch_app.toPlainText(),
                                                    "outfit": self.ch_outfit.toPlainText(), "lora": self.ch_lora.currentText().strip(),
                                                    "lora_weight": self.ch_lw.value(), "ref_image": self.ch_ref.text().strip()}, self.ch_id)
        except ValueError as e:
            self.notify(tr(str(e)), error=True); return
        self.load_presets(); self.notify(tr("Character saved"))

    def ch_delete(self):
        if self.ch_id:
            self.store.delete_character(self.ch_id); self.ch_new(); self.load_presets(); self.notify(tr("Deleted"))

    def _st_selected(self, row):
        it = self.st_list.item(row)
        s = self.store.style(it.data(Qt.UserRole)) if it else None
        if s:
            self.st_id = s["id"]; self.st_name.setText(s["name"]); self.st_tags.setPlainText(s["tags"]); self.st_neg.setPlainText(s["negative"])

    def st_new(self):
        self.st_id = None; self.st_name.clear(); self.st_tags.clear(); self.st_neg.clear()

    def st_save(self):
        try:
            self.st_id = self.store.save_style({"name": self.st_name.text(), "tags": self.st_tags.toPlainText(),
                                                "negative": self.st_neg.toPlainText()}, self.st_id)
        except ValueError as e:
            self.notify(tr(str(e)), error=True); return
        self.load_presets(); self.notify(tr("Style saved"))

    def st_delete(self):
        if self.st_id:
            self.store.delete_style(self.st_id); self.st_new(); self.load_presets(); self.notify(tr("Deleted"))

    def pr_combine(self):
        chars, styles = self.active_presets()
        if not chars and not styles:
            self.notify(tr("Tick at least one character or style"), error=True); return
        out = presets.compose(self.pr_in.toPlainText(), chars, styles, self.profile)
        neg = presets.negative(styles)
        self.pr_out.setPlainText(out + (f"\n\nNegative: {neg}" if neg else ""))
        return out

    # ---------------------------------------------------------------- Pose sketcher
    def _pose_page(self):
        w, v = _page("Pose", "Sketch poses and where things go. Drag the joints; draw boxes for other subjects. PromptMaker turns it into "
                             "composition tags, and can send an OpenPose image to ControlNet.")
        split = QSplitter(Qt.Horizontal)
        cc = Card()
        self.pose_canvas = PoseCanvas(); self.pose_canvas.changed.connect(self.pose_update)
        self.pose_preset = QComboBox(); self.pose_preset.addItems(list(pose.PRESETS))
        self.pose_box_label = QLineEdit("castle"); self.pose_box_label.setMaximumWidth(140)
        cc.add(hrow(button("🧍 Add figure", lambda: self.pose_canvas.add_figure(self.pose_preset.currentText())),
                    self.pose_preset, button("Apply to selected", lambda: self.pose_canvas.set_preset(self.pose_preset.currentText()), "ghost"),
                    None))
        cc.add(hrow(button("▭ Draw box", self._pose_box_mode), self.pose_box_label, None,
                    button("Remove selected", self.pose_canvas.remove_selected, "ghost"),
                    ConfirmButton("Clear", self.pose_canvas.clear, "Confirm clear")))
        cc.add(self.pose_canvas, 1)
        split.addWidget(cc)
        oc = Card("Composition")
        self.pose_tags = QPlainTextEdit(); self.pose_tags.setFixedHeight(110)
        self.pose_target = self._target_combo()
        oc.add(self.pose_tags)
        oc.add(hrow(label("Insert into"), self.pose_target, None, button("➕ Insert", lambda: self.pose_tags.toPlainText().strip() and
                                                                         self._insert_text(self.pose_tags.toPlainText().strip(), self.pose_target.currentData()), "primary")))
        oc.add(label("ControlNet (OpenPose)", "h2"))
        self.pose_cn_model = QComboBox(); self.pose_cn_model.setEditable(True); self.pose_cn_model.setMinimumWidth(220)
        self.pose_cn_model.setCurrentText(self.store.get("pose_cn_model", ""))
        self.pose_cn_weight = QDoubleSpinBox(); self.pose_cn_weight.setRange(0, 2); self.pose_cn_weight.setSingleStep(0.05)
        self.pose_cn_weight.setValue(self.store.get("pose_cn_weight", 1.0))
        self.pose_ckpt = self.make_ckpt_combo(); self.pose_ckpt.setMinimumWidth(300)
        oc.add(hrow(label("Checkpoint"), self.pose_ckpt, button("⟳", self.load_checkpoints, "ghost", "Reload checkpoint list")))
        oc.add(hrow(label("Model"), self.pose_cn_model, button("⟳", self.pose_cn_models, "ghost", "Load ControlNet models from the backend")))
        oc.add(hrow(label("Weight"), self.pose_cn_weight, None))
        self.pose_cn_status = label("", "hint", wrap=True); oc.add(self.pose_cn_status)
        self.pose_cn_model.currentTextChanged.connect(lambda _t: self.pose_cn_check())
        self.pose_preview = label(""); self.pose_preview.setAlignment(Qt.AlignCenter); self.pose_preview.setMinimumHeight(180)
        oc.add(self.pose_preview, 1)
        oc.add(hrow(button("💾 Export OpenPose PNG", self.pose_export), None,
                    button("🖼 Generate with ControlNet", self.pose_generate, "primary")))
        oc.add(label("Forge/A1111: uses alwayson_scripts → controlnet (needs ControlNet, built into Forge). ComfyUI: the pose is "
                     "uploaded and a ControlNetApplyAdvanced node is added to your workflow.", "hint", wrap=True))
        split.addWidget(oc); split.setSizes([620, 420])
        v.addWidget(split, 1)
        self.pose_canvas.load_state(self.store.get("pose_state") or {"figures": [pose.new_figure()], "boxes": []})
        return w

    def _pose_box_mode(self):
        self.pose_canvas.mode = "box"; self.pose_canvas._box_label = self.pose_box_label.text().strip() or "subject"
        self.notify(tr("Drag on the canvas to draw the box"))

    def _pose_size(self):
        try:
            return self._size_for_profile()
        except Exception:  # noqa: BLE001
            return 768, 1024

    def pose_update(self):
        c = self.pose_canvas
        self.pose_tags.setPlainText(pose.composition(c.figures, c.boxes, self.profile)["text"])
        self.store.set("pose_state", c.state())
        if c.figures:
            self._pose_png = pose.render_openpose(c.figures, 384, int(384 / max(c.aspect, .1)))
            self.pose_preview.setPixmap(_pix(self._pose_png, 180))
        else:
            self._pose_png = None; self.pose_preview.clear()

    def pose_png(self):
        if not self.pose_canvas.figures:
            return None
        w, h = self._pose_size()
        return pose.render_openpose(self.pose_canvas.figures, w, h)

    def pose_export(self):
        png = self.pose_png()
        if not png:
            self.notify(tr("Add a figure first"), error=True); return
        f, _ = QFileDialog.getSaveFileName(self, tr("Save OpenPose image"), "openpose.png", "PNG (*.png)")
        if f:
            with open(f, "wb") as fh:
                fh.write(png)
            self.notify(tr("Saved"))

    CN_HELP = ("No ControlNet models found in Forge's models\\ControlNet folder. Download one that matches your checkpoint "
               "(SD1.5 / SDXL OpenPose, or for Anima an Anima ControlNet-LLLite model from huggingface.co/kohya-ss/Anima-LLLite), "
               "put it in models\\ControlNet and restart Forge.")

    def _apply_cn_list(self, info):
        """Fill the dropdown with the exact names the backend returned. Returns the list."""
        models, known = info.get("models", []), info.get("known", True)
        cur = self.pose_cn_model.currentText().strip() or self.store.get("pose_cn_model", "")
        self.pose_cn_model.blockSignals(True)
        self.pose_cn_model.clear(); self.pose_cn_model.addItems(models)
        self.pose_cn_model.setEditable(not known)  # only free text when the WebUI can't list its models
        pick = pose.resolve_cn_model(cur, models) or pose.pick_default_cn(models, self.profile)
        if known:
            self.pose_cn_model.setCurrentIndex(max(0, self.pose_cn_model.findText(pick)) if models else -1)
        else:
            self.pose_cn_model.setCurrentText(cur)
        self.pose_cn_model.blockSignals(False)
        self._pose_cn_info = info
        self.pose_cn_check()
        return models

    def pose_cn_check(self):
        """Show a status/warning line for the chosen ControlNet model. Returns the warning text ('' = fine)."""
        info = getattr(self, "_pose_cn_info", None)
        name = self.pose_cn_model.currentText().strip()
        if info and info.get("known") and not info.get("models"):
            msg = tr("Forge has no ControlNet extension enabled.") if info.get("no_extension") else tr(self.CN_HELP)
        else:
            msg = pose.cn_compat_warning(name, self.profile) if name else ""
            if msg:
                msg = "⚠️ " + tr(msg)
        if hasattr(self, "pose_cn_status"):
            self.pose_cn_status.setText(msg)
        return msg

    def pose_cn_models(self):
        backend = self.image_backend()
        if not backend:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return
        from .widgets import CallWorker
        fetch = backend.controlnet_model_info if hasattr(backend, "controlnet_model_info") else \
            (lambda: (lambda m: {"models": m, "known": bool(m)})(backend.controlnet_models()))
        wk = CallWorker(fetch)
        def ok(info):
            models = self._apply_cn_list(info)
            self.notify(f"{len(models)} ControlNet model(s)" if models else
                        tr("No ControlNet models found") if info.get("known") else
                        tr("This WebUI can't list ControlNet models – type the name"), error=not models)
        wk.ok.connect(ok); self._keep(wk); wk.start()

    def pose_generate(self):
        png = self.pose_png()
        if not png:
            self.notify(tr("Add a figure first"), error=True); return
        backend = self.image_backend()
        if not backend:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return
        # Ask the backend what it actually has before sending anything, so the unit carries its exact model name.
        try:
            info = backend.controlnet_model_info() if hasattr(backend, "controlnet_model_info") else \
                (lambda m: {"models": m, "known": bool(m)})(backend.controlnet_models())
        except Exception:  # noqa: BLE001 – fall back to whatever the user typed
            info = {"models": [], "known": False}
        models = self._apply_cn_list(info)
        if info.get("known") and not models:
            self.notify(tr("Forge has no ControlNet extension enabled.") if info.get("no_extension") else
                        tr("No ControlNet models installed – nothing sent. See the note on the Pose page."), error=True)
            return
        typed = self.pose_cn_model.currentText().strip()
        model = pose.resolve_cn_model(typed, models) if models else typed
        if not model:
            self.notify(tr("Choose a ControlNet model first"), error=True); return
        warn = self.pose_cn_check()
        self.store.set("pose_cn_model", model); self.store.set("pose_cn_weight", self.pose_cn_weight.value())
        base = self.work.toPlainText().strip() or self.c_prompt.toPlainText().strip()
        prompt = loras.insert_into(base, self.pose_tags.toPlainText().strip())
        made = self.make_job(prompt, self._default_negative(), None, "pose")
        if not made:
            self.notify(tr("Set up ComfyUI or Forge/A1111 in Settings first"), error=True); return
        job, backend, wf = made
        job.controlnet = {"image": png, "model": model, "weight": self.pose_cn_weight.value()}
        self._job_callbacks = getattr(self, "_job_callbacks", {})
        self._job_callbacks.setdefault(job.id, []).append(self._pose_job_done)
        self.genq.add(job, backend, wf); self.queue_jobs.append(job); self._render_queue()
        self.notify((tr("Queued with ControlNet") + f" · seed {job.seed}") + (" · ⚠️ " + tr("model mismatch, see Pose page") if warn else ""),
                    error=bool(warn))
        return job

    def _pose_job_done(self, job):
        applied = getattr(job, "controlnet_applied", None)
        if applied is False:
            msg = tr("Forge didn't record ControlNet for this image, so the pose may not have been applied. "
                     "Check the Forge console and that the ControlNet model matches your checkpoint.")
            self.pose_cn_status.setText("⚠️ " + msg); self.notify(msg, error=True)
        elif applied is True:
            self.pose_cn_status.setText("✅ " + tr("ControlNet was applied") + f" ({job.controlnet['model']})")
