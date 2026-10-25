"""Review screen for 'Import from Civitai'."""
import html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QSpinBox, QTextBrowser, QVBoxLayout)

from . import civitai
from .i18n import tr
from .widgets import CallWorker, button, hrow, label


class CivitaiDialog(QDialog):
    saved = Signal(dict)

    def __init__(self, win, ref="", existing=None):
        super().__init__(win)
        self.win, self.existing, self.info, self.sugg = win, existing, None, None
        self.setWindowTitle(tr("Import from Civitai")); self.resize(860, 760)
        v = QVBoxLayout(self)
        v.addWidget(label("Paste a Civitai model link (civitai.com, civitai.red …) or an ID. "
                          "A bare number is a model ID; use v123 for a version ID.", "hint", wrap=True))
        self.ref = QLineEdit(ref); self.ref.setPlaceholderText("https://civitai.com/models/…?modelVersionId=…")
        self.fetch_btn = button("⬇ Fetch", lambda: self.fetch(force=False), "primary")
        v.addLayout(hrow(self.ref, self.fetch_btn, button("⟳", lambda: self.fetch(force=True), "ghost", "Fetch again, bypassing the cache")))
        self.status = label("", "hint", wrap=True); v.addWidget(self.status)
        self.summary = QTextBrowser(); self.summary.setOpenExternalLinks(True); self.summary.setMaximumHeight(150)
        v.addWidget(self.summary)
        f = QFormLayout(); v.addLayout(f)
        self.name = QLineEdit(); f.addRow(label("Profile name"), self.name)
        self.base = QComboBox()
        for pid, p in win.profiles.items():
            if not p.get("civitai"):
                self.base.addItem(p["name"], pid)
        f.addRow(label("Inherits from"), self.base)
        self.pos = QPlainTextEdit(); self.pos.setFixedHeight(70); f.addRow(label("Quality prefix (positive)"), self.pos)
        self.neg = QPlainTextEdit(); self.neg.setFixedHeight(90); f.addRow(label("Negative prompt"), self.neg)
        self.steps = QSpinBox(); self.steps.setRange(0, 200); self.steps.setSpecialValueText("–")
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(0, 30); self.cfg.setSingleStep(0.5); self.cfg.setSpecialValueText("–")
        self.clip = QSpinBox(); self.clip.setRange(0, 12); self.clip.setSpecialValueText("–")
        row = QHBoxLayout()
        for lab, wdg in (("Steps", self.steps), ("CFG", self.cfg), ("Clip skip", self.clip)):
            row.addWidget(label(lab)); row.addWidget(wdg)
        row.addStretch(); f.addRow(label("Settings"), row)
        self.sampler = QLineEdit(); f.addRow(label("Sampler"), self.sampler)
        self.res = QLineEdit(); self.res.setPlaceholderText("e.g. 832x1216"); f.addRow(label("Resolution"), self.res)
        self.trained = QLineEdit(); self.trained.setPlaceholderText(tr("trigger words, comma separated (LoRAs)"))
        f.addRow(label("Trained words"), self.trained)
        self.save_btn = button("💾 Save profile", self.save, "primary"); self.save_btn.setEnabled(False)
        v.addLayout(hrow(label("Review and edit, then save. Recommendations come from the creator's description and "
                               "sample images; check the model's licence on Civitai.", "hint", wrap=True), None,
                         button("Close", self.close, "ghost"), self.save_btn))

    # -------------------------------------------------------------- fetching
    def fetch(self, force=False):
        self.status.setText(tr("Loading…")); self.fetch_btn.setEnabled(False)
        ref = self.ref.text().strip()
        client = self.win.civitai_client()
        wk = CallWorker(lambda: civitai.fetch(ref, client, force=force))
        wk.ok.connect(self._loaded)
        wk.failed.connect(lambda e: (self.status.setText("⚠️ " + e[:300]), self.fetch_btn.setEnabled(True)))
        self.win._keep(wk); wk.start()
        self._worker = wk

    def _loaded(self, info):
        self.fetch_btn.setEnabled(True)
        self.info, s = info, civitai.suggest(info)
        self.sugg = s
        v, m = info["version"], info["model"]
        mined = s["mined"]
        base_id = (self.existing or {}).get("inherits") or civitai.base_profile_id(s["base_model"], self.win.profiles)
        self.base.setCurrentIndex(max(0, self.base.findData(base_id)))
        self.name.setText((self.existing or {}).get("name") or f"{s['name']} (Civitai)")
        self.pos.setPlainText(s["positive"]); self.neg.setPlainText(s["negative"])
        self.steps.setValue(int(s.get("steps") or 0)); self.cfg.setValue(float(s.get("cfg") or 0))
        self.clip.setValue(int(s.get("clip_skip") or 0))
        self.sampler.setText(s.get("sampler") or ""); self.res.setText(s.get("resolution") or "")
        self.trained.setText(", ".join(s.get("trained_words") or []))
        src = lambda k: s.get(k + "_source") or "not found"  # noqa: E731
        self.summary.setHtml(
            f"<b>{html.escape(str(m.get('name')))}</b> · {html.escape(str(m.get('type')))} · version {html.escape(str(v.get('name')))} "
            f"(#{v.get('id')}) · base model <b>{html.escape(str(v.get('baseModel')))}</b><br>"
            f"<a href='{info['url']}'>{info['url']}</a><br>"
            f"Positive: {src('positive')} · Negative: {src('negative')} · "
            f"sample images: {mined.get('images_with_meta', 0)} of {mined.get('images_total', 0)} with generation data"
            + (f"<br>Steps {html.escape(s['steps_text'])}" if s.get("steps_text") else "")
            + (f" · CFG {html.escape(s['cfg_text'])}" if s.get("cfg_text") else "")
            + ("<br>⚠️ NSFW model" if m.get("nsfw") else ""))
        self.status.setText(tr("Fetched – review and save") if not self.existing else tr("Fetched again – review the changes and save"))
        self.save_btn.setEnabled(True)

    # -------------------------------------------------------------- saving
    def profile(self):
        s = dict(self.sugg)
        orig_steps, orig_cfg = s.get("steps"), s.get("cfg")
        s.update(positive=self.pos.toPlainText().strip(), negative=self.neg.toPlainText().strip(),
                 steps=self.steps.value() or None, cfg=self.cfg.value() or None, clip_skip=self.clip.value() or None,
                 sampler=self.sampler.text().strip(), resolution=self.res.text().strip().lower().replace(" ", ""),
                 trained_words=[t.strip() for t in self.trained.text().split(",") if t.strip()])
        if s["steps"] != orig_steps:
            s["steps_text"] = ""  # edited by hand – describe the new value, not the creator's range
        if s["cfg"] != (float(orig_cfg) if orig_cfg else None):
            s["cfg_text"] = ""
        raw = {pid: p for pid, p in self.win.profiles.items()}
        prof = civitai.build_profile(self.info, s, self.base.currentData(), raw, pid=(self.existing or {}).get("id"))
        prof["name"] = self.name.text().strip() or prof["name"]
        return prof

    def save(self):
        if not self.info:
            return
        self.saved.emit(self.profile()); self.close()
