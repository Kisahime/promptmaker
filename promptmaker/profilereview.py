"""5.2: review a built model profile before saving – parsed values are editable, values that came from a family default
or sample images (not the creator) are highlighted, and the profile is schema-checked before it is written."""
import copy
import html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QSpinBox, QVBoxLayout)

from . import profilenorm as pn
from .i18n import tr
from .widgets import button, hrow, label

UNCERTAIN = "background: rgba(255, 170, 0, 0.18); border: 1px solid rgba(255, 170, 0, 0.7);"


def _combo(items, current, editable=False):
    c = QComboBox(); c.setEditable(editable)
    c.addItem("–", "")
    for it in items:
        c.addItem(it, it)
    i = c.findData(current or "")
    if i >= 0:
        c.setCurrentIndex(i)
    elif current:
        c.addItem(str(current), current); c.setCurrentIndex(c.count() - 1)
    return c


class ProfileReviewDialog(QDialog):
    saved = Signal(dict)

    def __init__(self, win, prof):
        super().__init__(win)
        self.win, self.orig = win, copy.deepcopy(prof)
        self.setWindowTitle(tr("Review model profile")); self.resize(720, 720)
        g, src, c = prof.get("gen") or {}, prof.get("source") or {}, prof.get("civitai") or {}
        v = QVBoxLayout(self)
        v.addWidget(label("Check the values before saving. Highlighted fields were not stated by the creator "
                          "(family default or sample images) – hover for where each value came from.", "hint", wrap=True))
        if c.get("matched_section"):
            v.addWidget(label("Matched the creator's section: " + c["matched_section"], "hint", wrap=True))
        f = QFormLayout(); v.addLayout(f)
        self.name = QLineEdit(prof.get("name", "")); f.addRow(label("Profile name"), self.name)
        self.steps = QSpinBox(); self.steps.setRange(0, 200); self.steps.setSpecialValueText("–"); self.steps.setValue(int(g.get("steps") or 0))
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(0, 30); self.cfg.setSingleStep(0.5); self.cfg.setSpecialValueText("–")
        self.cfg.setValue(float(g.get("cfg") or 0))
        self.cfg_range = QLineEdit(g.get("cfg_range", "")); self.cfg_range.setPlaceholderText("e.g. 3.5–5")
        self.sampler = _combo(list(pn.SAMPLERS), g.get("sampler"))
        self.scheduler = _combo(list(pn.SCHEDULERS), g.get("scheduler"))
        self.forge = QLabel(); self.nodes = QLabel(); self.nodes.setWordWrap(True); self._forge()
        self.sampler.currentIndexChanged.connect(self._forge); self.scheduler.currentIndexChanged.connect(self._forge)
        self.neg = QPlainTextEdit(prof.get("negative_default", "")); self.neg.setFixedHeight(60)
        self.prefix = QPlainTextEdit(prof.get("quality_prefix", "")); self.prefix.setFixedHeight(50)
        self.file = QLineEdit(c.get("file_name") or "")
        self.type = _combo(list(pn.TYPES), c.get("type"))
        self.workflow = QLineEdit(g.get("workflow", "")); self.te = QLineEdit(g.get("text_encoder", "")); self.vae = QLineEdit(g.get("vae", ""))
        rows = [("Steps", self.steps, "steps"), ("CFG", self.cfg, "cfg"), ("CFG range (creator)", self.cfg_range, "cfg"),
                ("Sampler (ComfyUI)", self.sampler, "sampler"), ("Scheduler (ComfyUI)", self.scheduler, "scheduler"),
                ("Forge / A1111", self.forge, "a1111_sampler"), ("Custom nodes", self.nodes, None), ("Negative prompt", self.neg, "negative_default"),
                ("Quality prefix", self.prefix, "quality_prefix"), ("File name", self.file, None), ("Type", self.type, None),
                ("Workflow", self.workflow, "workflow"), ("Text encoder", self.te, "text_encoder"), ("VAE", self.vae, "vae")]
        self.flagged = []
        for lab, wdg, key in rows:
            s = src.get(key) if key else None
            if s and s not in ("author", "user", "description"):
                wdg.setStyleSheet(UNCERTAIN); self.flagged.append(key)
            wdg.setToolTip(tr("Source") + f": {s or 'creator / Civitai'}")
            f.addRow(label(lab + (" ⚠" if key in self.flagged else "")), wdg)
        warn = list(c.get("warnings") or [])
        self.msg = label("<br>".join("⚠️ " + html.escape(w) for w in warn), "hint", wrap=True); v.addWidget(self.msg)
        v.addLayout(hrow(None, button("Cancel", self.close, "ghost"), button("💾 Save profile", self.save, "primary")))

    def _forge(self, *_):
        s, sc = pn.forge_sampler(self.sampler.currentData()), pn.forge_scheduler(self.scheduler.currentData())
        self.forge.setText(f"{s or '– (Forge default)'} · {sc or '–'}")
        need = {n: pn.needs_node(n) or (self.orig.get("gen") or {}).get("custom_nodes", {}).get(n)
                for n in (self.sampler.currentData(), self.scheduler.currentData()) if n}
        need = {k: v for k, v in need.items() if v}
        self.nodes.setText(", ".join(f"{k} → {v}" for k, v in need.items()) or tr("none (ComfyUI core)"))

    def profile(self):
        p = copy.deepcopy(self.orig)
        g, src, c = p.setdefault("gen", {}), p.setdefault("source", {}), p.setdefault("civitai", {})
        new = {"steps": self.steps.value() or None, "cfg": round(self.cfg.value(), 2) or None,
               "sampler": self.sampler.currentData() or None, "scheduler": self.scheduler.currentData() or None,
               "workflow": self.workflow.text().strip() or None, "text_encoder": self.te.text().strip() or None,
               "vae": self.vae.text().strip() or None, "cfg_range": self.cfg_range.text().strip() or None}
        old_cn = dict(g.get("custom_nodes") or {})
        for k, val in new.items():
            if val != g.get(k):
                src[k] = "user"
                if k in ("sampler", "scheduler") and val:
                    src["a1111_" + k] = "user"
                if k == "steps":
                    g.pop("steps_range", None)
            if val is None:
                g.pop(k, None)
            else:
                g[k] = val
        for k, fn in (("a1111_sampler", pn.forge_sampler), ("a1111_scheduler", pn.forge_scheduler)):
            val = fn(g.get("sampler" if k == "a1111_sampler" else "scheduler"))
            if val:
                g[k] = val
            else:
                g.pop(k, None)
        for k, wdg in (("negative_default", self.neg), ("quality_prefix", self.prefix)):
            t = wdg.toPlainText().strip()
            if t != (p.get(k) or ""):
                p[k] = t; src[k] = "user"
        p["name"] = self.name.text().strip() or p.get("name")
        c["file_name"] = self.file.text().strip() or c.get("file_name")
        if self.type.currentData():
            c["type"] = self.type.currentData()
        cn = {n: pn.needs_node(n) or old_cn.get(n) for n in (g.get("sampler"), g.get("scheduler")) if n}
        cn = {k: v for k, v in cn.items() if v}
        if cn:
            g["custom_nodes"] = cn
        else:
            g.pop("custom_nodes", None)
        p["settings"] = pn.settings_line(g, src, {})
        p["tips"] = pn.refresh_tips(p)
        return p

    def save(self):
        p = self.profile()
        errs = pn.validate(p)
        if errs:
            self.msg.setText("<b>" + tr("Not saved") + ":</b><br>" + "<br>".join("✖ " + html.escape(e) for e in errs))
            return None
        self.saved.emit(p); self.close()
        return p
