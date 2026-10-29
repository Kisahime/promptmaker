"""Canvas for the Inpaint & Regions page: paint an inpaint mask over a base image and draw prompt regions."""
from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

REGION_COLOURS = ["#ff6b81", "#4dabf7", "#35d39a", "#ffc34d", "#b197fc", "#ff922b", "#63e6be", "#f783ac"]


def png_bytes(img):
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    return bytes(buf.data())


class InpaintCanvas(QWidget):
    changed = Signal()
    regions_changed = Signal()
    selection_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.image = None             # QImage – the base image (None = blank canvas of self.size_wh)
        self.size_wh = (1024, 1024)
        self.mask = self._blank_mask()
        self.regions = []             # [{prompt, x, y, w, h, weight}] normalised
        self.selected = -1
        self.mode = "brush"           # brush | erase | region
        self.brush = 48               # in image pixels
        self._last = None
        self._drag = None
        self.setMinimumSize(380, 380)
        self.setMouseTracking(True)

    # ------------------------------------------------ image & mask
    def img_size(self):
        return (self.image.width(), self.image.height()) if self.image is not None else self.size_wh

    def _blank_mask(self):
        w, h = self.img_size() if hasattr(self, "image") else (1024, 1024)
        m = QImage(w, h, QImage.Format_ARGB32_Premultiplied); m.fill(Qt.transparent)
        return m

    def set_image(self, img):
        """img: QImage, path or PNG bytes. Resets the mask (a new picture needs a new mask)."""
        if isinstance(img, (bytes, bytearray)):
            img = QImage.fromData(bytes(img))
        elif isinstance(img, str):
            img = QImage(img)
        if img is None or img.isNull():
            raise ValueError("Couldn't open that image")
        self.image = img.convertToFormat(QImage.Format_RGB32)
        self.mask = self._blank_mask(); self.update(); self.changed.emit()

    def set_blank(self, w, h):
        self.image, self.size_wh = None, (int(w), int(h))
        self.mask = self._blank_mask(); self.update(); self.changed.emit()

    def clear_mask(self):
        self.mask = self._blank_mask(); self.update(); self.changed.emit()

    def invert_mask(self):
        w, h = self.img_size()
        inv = QImage(w, h, QImage.Format_ARGB32_Premultiplied); inv.fill(QColor(255, 255, 255))
        p = QPainter(inv); p.setCompositionMode(QPainter.CompositionMode_DestinationOut); p.drawImage(0, 0, self.mask); p.end()
        self.mask = inv; self.update(); self.changed.emit()

    def fill_rect_mask(self, x, y, w, h):
        """Mask a normalised rectangle (used by 'mask selected region' and tests)."""
        iw, ih = self.img_size()
        p = QPainter(self.mask); p.fillRect(QRectF(x * iw, y * ih, w * iw, h * ih), QColor(255, 255, 255)); p.end()
        self.update(); self.changed.emit()

    def has_mask(self):
        from .regions import mask_coverage
        return mask_coverage(self.mask_png()) > 0

    def mask_png(self):
        """White = repaint, black = keep – the format Forge/A1111 expects."""
        w, h = self.img_size()
        out = QImage(w, h, QImage.Format_RGB32); out.fill(QColor(0, 0, 0))
        p = QPainter(out); p.drawImage(0, 0, self.mask); p.end()
        return png_bytes(out)

    def image_png(self):
        if self.image is None:
            return None
        return png_bytes(self.image)

    # ------------------------------------------------ regions
    def add_region(self, prompt="", rect=(.05, .05, .45, .9), weight=1.0):
        self.regions.append({"prompt": prompt, "x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3], "weight": weight})
        self.select(len(self.regions) - 1); self.regions_changed.emit(); self.update()

    def remove_region(self, i=None):
        i = self.selected if i is None else i
        if 0 <= i < len(self.regions):
            self.regions.pop(i); self.select(min(i, len(self.regions) - 1)); self.regions_changed.emit(); self.update()

    def select(self, i):
        self.selected = i; self.selection_changed.emit(i); self.update()

    def state(self):
        return {"regions": self.regions, "size": list(self.size_wh)}

    # ------------------------------------------------ geometry
    def area(self):
        iw, ih = self.img_size()
        aspect = iw / max(ih, 1)
        w, h = self.width() - 16, self.height() - 16
        if w / max(h, 1) > aspect:
            w = h * aspect
        else:
            h = w / aspect
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_img(self, pt):
        a = self.area(); iw, ih = self.img_size()
        return QPointF((pt.x() - a.x()) / a.width() * iw, (pt.y() - a.y()) / a.height() * ih)

    def to_norm(self, pt):
        a = self.area()
        return min(1.0, max(0.0, (pt.x() - a.x()) / a.width())), min(1.0, max(0.0, (pt.y() - a.y()) / a.height()))

    def region_rect(self, r):
        a = self.area()
        return QRectF(a.x() + r["x"] * a.width(), a.y() + r["y"] * a.height(), r["w"] * a.width(), r["h"] * a.height())

    # ------------------------------------------------ painting the mask
    def _stroke(self, a, b):
        p = QPainter(self.mask); p.setRenderHint(QPainter.Antialiasing)
        if self.mode == "erase":
            p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.setPen(QPen(QColor(255, 255, 255), self.brush, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(a, b) if a != b else p.drawPoint(a)
        p.end(); self.update()

    def mousePressEvent(self, e):
        pos = e.position()
        if self.mode in ("brush", "erase"):
            self._last = self.to_img(pos); self._stroke(self._last, self._last); return
        nx, ny = self.to_norm(pos)
        for i in reversed(range(len(self.regions))):
            rr = self.region_rect(self.regions[i])
            if rr.adjusted(-6, -6, 6, 6).contains(pos):
                corner = (pos - rr.bottomRight()).manhattanLength() < 18
                self.select(i)
                self._drag = ("resize" if corner else "move", i, nx, ny, dict(self.regions[i]))
                return
        self.add_region("", (nx, ny, 0.01, 0.01))
        self._drag = ("new", len(self.regions) - 1, nx, ny, dict(self.regions[-1]))

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.mode in ("brush", "erase") and self._last is not None and e.buttons():
            cur = self.to_img(pos); self._stroke(self._last, cur); self._last = cur; return
        if not self._drag:
            return
        kind, i, sx, sy, orig = self._drag
        nx, ny = self.to_norm(pos)
        r = self.regions[i]
        if kind == "move":
            r["x"] = min(max(orig["x"] + nx - sx, 0), 1 - orig["w"]); r["y"] = min(max(orig["y"] + ny - sy, 0), 1 - orig["h"])
        elif kind == "resize":
            r["w"] = max(.03, min(orig["w"] + nx - sx, 1 - orig["x"])); r["h"] = max(.03, min(orig["h"] + ny - sy, 1 - orig["y"]))
        else:
            r["x"], r["y"] = min(sx, nx), min(sy, ny); r["w"], r["h"] = max(abs(nx - sx), .01), max(abs(ny - sy), .01)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._last is not None:
            self._last = None; self.changed.emit()
        if self._drag:
            kind, i = self._drag[:2]
            if kind == "new" and (self.regions[i]["w"] < .04 or self.regions[i]["h"] < .04):
                self.regions[i].update(w=max(self.regions[i]["w"], .25), h=max(self.regions[i]["h"], .25))
                self.regions[i]["x"] = min(self.regions[i]["x"], .75); self.regions[i]["y"] = min(self.regions[i]["y"], .75)
            self._drag = None; self.regions_changed.emit(); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        a = self.area()
        if self.image is not None:
            p.drawImage(a, self.image)
        else:
            p.fillRect(a, QColor("#1d1f2b"))
            p.setPen(QColor("#5b5f7a")); p.drawText(a, Qt.AlignCenter, "Blank canvas – load an image to inpaint,\nor draw regions")
        tint = QImage(self.mask.size(), QImage.Format_ARGB32_Premultiplied); tint.fill(QColor(255, 70, 110))
        tp = QPainter(tint); tp.setCompositionMode(QPainter.CompositionMode_DestinationIn); tp.drawImage(0, 0, self.mask); tp.end()
        p.setOpacity(0.5); p.drawImage(a, tint); p.setOpacity(1.0)
        for i, r in enumerate(self.regions):
            col = QColor(REGION_COLOURS[i % len(REGION_COLOURS)])
            rr = self.region_rect(r)
            fill = QColor(col); fill.setAlpha(45 if i != self.selected else 80)
            p.fillRect(rr, fill)
            p.setPen(QPen(col, 3 if i == self.selected else 2, Qt.SolidLine if i == self.selected else Qt.DashLine)); p.drawRect(rr)
            p.setPen(QColor("white"))
            txt = f"{i + 1}. {(r.get('prompt') or '…')[:40]}"
            p.drawText(rr.adjusted(6, 4, -6, -4), Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, txt)
            if i == self.selected:
                p.fillRect(QRectF(rr.right() - 7, rr.bottom() - 7, 10, 10), col)
        p.setPen(QPen(QColor("#5b5f7a"), 1)); p.drawRect(a)
