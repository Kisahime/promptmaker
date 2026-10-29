"""Render promptmaker/assets/icon.svg to PNGs and a multi-size icon.ico.

Sizes <= 32px use the simplified icon_small.svg so they stay crisp.
Run: python tools/build_icon.py  (needs PySide6 and Pillow)
"""
import io, os, sys
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QBuffer, QIODevice
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "promptmaker", "assets")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(svg, size):
    r = QSvgRenderer(os.path.join(ASSETS, svg))
    img = QImage(size, size, QImage.Format_ARGB32); img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); r.render(p); p.end()
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main(out_dir=None):
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    imgs = {s: render("icon_small.svg" if s <= 32 else "icon.svg", s) for s in SIZES}
    imgs[256].save(os.path.join(ASSETS, "icon_256.png"))
    imgs[256].save(os.path.join(ASSETS, "icon.ico"), sizes=[(s, s) for s in SIZES], append_images=[imgs[s] for s in SIZES[:-1]])
    if out_dir:
        for s, im in imgs.items():
            im.save(os.path.join(out_dir, f"icon_{s}.png"))
    return imgs


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
