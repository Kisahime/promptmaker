"""Interactive canvas for the pose & composition sketcher: draggable OpenPose keypoints and subject boxes."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import pose


class PoseCanvas(QWidget):
    changed = Signal()

    def __init__(self, aspect=0.75):
        super().__init__()
        self.figures, self.boxes = [], []
        self.aspect = aspect  # width / height
        self.mode = "edit"    # "edit" | "box"
        self.selected = None  # ("fig", i) | ("box", i)
        self._drag = None
        self._box_label = "subject"
        self.setMinimumSize(360, 420)
        self.setMouseTracking(True)

    # -------- geometry
    def area(self):
        w, h = self.width() - 20, self.height() - 20
        if w / max(h, 1) > self.aspect:
            w = h * self.aspect
        else:
            h = w / self.aspect
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_px(self, x, y):
        a = self.area(); return QPointF(a.x() + x * a.width(), a.y() + y * a.height())

    def to_norm(self, pt):
        a = self.area()
        return [min(1.0, max(0.0, (pt.x() - a.x()) / a.width())), min(1.0, max(0.0, (pt.y() - a.y()) / a.height()))]

    # -------- model
    def set_aspect(self, aspect):
        self.aspect = aspect; self.update()

    def add_figure(self, preset="Standing"):
        n = len(self.figures)
        self.figures.append(pose.new_figure(preset, dx=[0, -.22, .22, -.11, .11][n % 5], scale=1.0 if n == 0 else .9))
        self.selected = ("fig", len(self.figures) - 1); self.update(); self.changed.emit()

    def set_preset(self, preset):
        if self.selected and self.selected[0] == "fig":
            f = self.figures[self.selected[1]]
            cx = pose.figure_center(f)
            self.figures[self.selected[1]] = pose.new_figure(preset, dx=cx - .5)
            self.update(); self.changed.emit()

    def add_box(self, label="subject", rect=(.3, .55, .4, .35)):
        self.boxes.append({"label": label, "x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]})
        self.selected = ("box", len(self.boxes) - 1); self.update(); self.changed.emit()

    def remove_selected(self):
        if not self.selected:
            return
        kind, i = self.selected
        (self.figures if kind == "fig" else self.boxes).pop(i)
        self.selected = None; self.update(); self.changed.emit()

    def clear(self):
        self.figures, self.boxes, self.selected = [], [], None; self.update(); self.changed.emit()

    def state(self):
        return {"figures": self.figures, "boxes": self.boxes}

    def load_state(self, s):
        self.figures = [dict(points=[list(p) for p in f["points"]]) for f in (s or {}).get("figures", [])]
        self.boxes = [dict(b) for b in (s or {}).get("boxes", [])]
        self.selected = None; self.update(); self.changed.emit()

    # -------- interaction
    def _hit(self, pt):
        for fi in range(len(self.figures) - 1, -1, -1):
            for k, (x, y) in enumerate(self.figures[fi]["points"]):
                if (self.to_px(x, y) - pt).manhattanLength() < 12:
                    return ("kp", fi, k)
        for bi in range(len(self.boxes) - 1, -1, -1):
            b = self.boxes[bi]
            br = self.to_px(b["x"] + b["w"], b["y"] + b["h"])
            if (br - pt).manhattanLength() < 14:
                return ("resize", bi)
            tl = self.to_px(b["x"], b["y"])
            if QRectF(tl, br).contains(pt):
                return ("move", bi)
        return None

    def mousePressEvent(self, e):
        pt = e.position()
        if self.mode == "box":
            n = self.to_norm(pt); self.add_box(self._box_label, (n[0], n[1], .01, .01))
            self._drag = ("resize", len(self.boxes) - 1, n); return
        h = self._hit(pt)
        if h:
            self.selected = ("fig", h[1]) if h[0] == "kp" else ("box", h[1])
            self._drag = h + (self.to_norm(pt),)
        else:
            self.selected = None
        self.update()

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        n = self.to_norm(e.position())
        kind = self._drag[0]
        if kind == "kp":
            _, fi, k, _ = self._drag; self.figures[fi]["points"][k] = n
        elif kind == "move":
            _, bi, start = self._drag; b = self.boxes[bi]
            b["x"] = min(1 - b["w"], max(0, b["x"] + n[0] - start[0])); b["y"] = min(1 - b["h"], max(0, b["y"] + n[1] - start[1]))
            self._drag = ("move", bi, n)
        elif kind == "resize":
            bi = self._drag[1]; b = self.boxes[bi]
            b["w"], b["h"] = max(.03, n[0] - b["x"]), max(.03, n[1] - b["y"])
        self.update(); self.changed.emit()

    def mouseReleaseEvent(self, e):
        if self._drag:
            self.changed.emit()
        self._drag = None
        if self.mode == "box":
            self.mode = "edit"

    # -------- paint
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        a = self.area()
        p.fillRect(self.rect(), QColor("#14151b")); p.fillRect(a, QColor("#0b0c10"))
        p.setPen(QPen(QColor(255, 255, 255, 28), 1, Qt.DashLine))
        for t in (1 / 3, 2 / 3):
            p.drawLine(self.to_px(t, 0), self.to_px(t, 1)); p.drawLine(self.to_px(0, t), self.to_px(1, t))
        for bi, b in enumerate(self.boxes):
            sel = self.selected == ("box", bi)
            r = QRectF(self.to_px(b["x"], b["y"]), self.to_px(b["x"] + b["w"], b["y"] + b["h"]))
            p.setPen(QPen(QColor("#9479ff" if sel else "#7c5cff"), 2)); p.setBrush(QColor(124, 92, 255, 40)); p.drawRect(r)
            p.setPen(QColor("#ecedf5")); p.drawText(r.adjusted(6, 4, 0, 0), Qt.AlignLeft | Qt.AlignTop, b.get("label", ""))
            p.setBrush(QColor("#ecedf5")); p.drawRect(QRectF(r.bottomRight() - QPointF(5, 5), r.bottomRight() + QPointF(5, 5)))
        for fi, f in enumerate(self.figures):
            pts = [self.to_px(x, y) for x, y in f["points"]]
            for k, (i, j) in enumerate(pose.LIMBS):
                c = QColor(*pose.COLORS[k % len(pose.COLORS)]); c.setAlpha(200)
                p.setPen(QPen(c, 5, Qt.SolidLine, Qt.RoundCap)); p.drawLine(pts[i], pts[j])
            sel = self.selected == ("fig", fi)
            for k, pt in enumerate(pts):
                p.setPen(QPen(QColor("#ffffff"), 1.5) if sel else Qt.NoPen); p.setBrush(QColor(*pose.COLORS[k]))
                p.drawEllipse(pt, 6 if sel else 5, 6 if sel else 5)
        p.end()
