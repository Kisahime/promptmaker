"""5.0 Live sketch-to-image: a simple paint canvas whose drawing is sent (debounced) to the image backend as a
fast low-step img2img – or as a ControlNet scribble when a scribble model is installed – with the result beside it."""
from PySide6.QtCore import QBuffer, QByteArray, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

SPEED_PRESETS = {
    "Lightning / Turbo (fast)": {"steps": 6, "cfg": 1.8, "sampler": "DPM++ SDE", "scheduler": "Karras", "size": 640},
    "Balanced": {"steps": 12, "cfg": 4.5, "sampler": "Euler a", "scheduler": "", "size": 768},
    "Quality (slow)": {"steps": 22, "cfg": 5.5, "sampler": "DPM++ 2M", "scheduler": "Karras", "size": 896},
}
SCRIBBLE_HINTS = ("scribble", "sketch", "lineart")
PALETTE = ["#1b1b1f", "#ffffff", "#e63946", "#f4a261", "#e9c46a", "#2a9d8f", "#4cc9f0", "#4361ee", "#9d4edd", "#ff8fab",
           "#8d6e63", "#a7c957"]


def scribble_models(cn_models):
    return [m for m in (cn_models or []) if any(h in m.lower() for h in SCRIBBLE_HINTS)]


def png_bytes(img):
    ba = QByteArray(); b = QBuffer(ba); b.open(QBuffer.WriteOnly); img.save(b, "PNG")
    return bytes(ba)


def full_mask(w, h):
    m = QImage(w, h, QImage.Format_RGB32); m.fill(QColor("white"))
    return png_bytes(m)


def scribble_image(img):
    """ControlNet scribble wants white strokes on black: anything not near-white becomes a white line."""
    out = img.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_RGB32)
    out.invertPixels()
    return out


def apply_to_job(job, sketch_png, mode="img2img", denoise=0.65, cn_model="", preset=None, size=None):
    """Turn a normal txt2img job into a fast sketch job. mode 'img2img' sends the drawing as the init image (full
    mask, so it works on Forge and ComfyUI alike); mode 'scribble' sends it as a ControlNet scribble hint."""
    pr = SPEED_PRESETS.get(preset) or {}
    if pr:
        job.steps, job.cfg = pr["steps"], pr["cfg"]
        if pr.get("sampler"):
            job.sampler = pr["sampler"]
        if pr.get("scheduler"):
            job.scheduler, job.scheduler_set = pr["scheduler"], True
    side = int(size or pr.get("size") or 640)
    src = QImage.fromData(sketch_png)
    if src.width() and src.height():
        r = src.width() / src.height()
        w, h = (side, int(side / r)) if r >= 1 else (int(side * r), side)
        job.width, job.height = max(256, w // 64 * 64), max(256, h // 64 * 64)
        src = src.scaled(job.width, job.height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    job.hires = None
    job.tag = "sketch"
    if mode == "scribble" and cn_model:
        job.controlnet = {"image": png_bytes(scribble_image(src)), "model": cn_model, "weight": 0.9}
    else:
        job.inpaint = {"image": png_bytes(src), "mask": full_mask(job.width, job.height), "denoise": float(denoise),
                       "mask_blur": 0, "only_masked": False, "padding": 0, "fill": "original"}
    return job


class SketchCanvas(QWidget):
    """Paint canvas: brush colour/size, eraser, undo, clear, load an image to draw over."""
    changed = Signal()

    def __init__(self, w=640, h=640, parent=None):
        super().__init__(parent)
        self.img = QImage(w, h, QImage.Format_RGB32); self.img.fill(QColor("white"))
        self.color, self.size, self.eraser = QColor("#1b1b1f"), 14, False
        self._last, self._undo = None, []
        self.setMinimumSize(320, 320); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor); self.setAttribute(Qt.WA_StaticContents)

    # mapping widget <-> image (image is letterboxed to keep aspect)
    def _geom(self):
        s = min(self.width() / self.img.width(), self.height() / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        return s, (self.width() - w) / 2, (self.height() - h) / 2

    def _to_img(self, pos):
        s, ox, oy = self._geom()
        return QPoint(int((pos.x() - ox) / s), int((pos.y() - oy) / s))

    def paintEvent(self, _e):
        from PySide6.QtCore import QRectF
        p = QPainter(self); s, ox, oy = self._geom()
        p.fillRect(self.rect(), self.palette().window())
        p.drawImage(QRectF(ox, oy, self.img.width() * s, self.img.height() * s), self.img)

    def _push_undo(self):
        self._undo.append(self.img.copy()); self._undo = self._undo[-30:]

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._push_undo(); self._last = self._to_img(e.position().toPoint()); self.stroke(self._last, self._last)

    def mouseMoveEvent(self, e):
        if self._last is not None:
            pt = self._to_img(e.position().toPoint()); self.stroke(self._last, pt); self._last = pt

    def mouseReleaseEvent(self, _e):
        if self._last is not None:
            self._last = None; self.changed.emit()

    def stroke(self, a, b):
        p = QPainter(self.img); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("white") if self.eraser else self.color, self.size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(a, b); p.end(); self.update()

    def fill_rect(self, x, y, w, h, color):
        """Block in a colour area (used by the 'shape' tools and tests)."""
        self._push_undo(); p = QPainter(self.img); p.fillRect(x, y, w, h, QColor(color)); p.end(); self.update(); self.changed.emit()

    def fill_ellipse(self, x, y, w, h, color):
        self._push_undo(); p = QPainter(self.img); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
        p.setBrush(QColor(color)); p.drawEllipse(x, y, w, h); p.end(); self.update(); self.changed.emit()

    def undo(self):
        if self._undo:
            self.img = self._undo.pop(); self.update(); self.changed.emit()

    def clear(self):
        self._push_undo(); self.img.fill(QColor("white")); self.update(); self.changed.emit()

    def load(self, path_or_img):
        im = path_or_img if isinstance(path_or_img, QImage) else QImage(path_or_img)
        if im.isNull():
            return False
        self._push_undo()
        self.img = im.convertToFormat(QImage.Format_RGB32).scaled(self.img.width(), self.img.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.update(); self.changed.emit()
        return True

    def is_blank(self):
        g = self.img.convertToFormat(QImage.Format_Grayscale8)
        step = max(1, g.width() // 64)
        for y in range(0, g.height(), step):
            row = g.constScanLine(y)
            if any(row[x] < 240 for x in range(0, g.width(), step)):
                return False
        return True

    def png(self):
        return png_bytes(self.img)
