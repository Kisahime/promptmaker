"""PromptMaker design system (4.1.5): palette + scale tokens -> one app-wide QSS, plus shadow / hover helpers."""
import os
ACCENT = "#a78bfa"
# 4.1.5 "pastel" design system: sakura pink, lavender, mint, baby blue and peach.
# Light is the default look (pastel-tinted); dark is a dusky plum-pastel version of the same palette.
PALETTES = {
    "light": dict(bg="#fdf2f8", bg2="#f3ecff", bg3="#eaf4ff", surface="#fff5fa", surface2="#f1eaff",
                  card="rgba(255,255,255,0.86)", card_solid="#ffffff", raised="#fff7fb", border="#f3d3e6", border_soft="#f7e3ef",
                  text="#4a3b5c", muted="#8f7fa6", faint="#c0b2d3", accent="#9b7bf0", accent_hover="#b49afa",
                  accent_soft="rgba(155,123,240,0.16)", accent2="#f9a8d4", chip="#ffffff", chip_hover="#fde7f3",
                  pink="#f9a8d4", lavender="#c4b5fd", mint="#a7f3d0", blue="#bae6fd", peach="#fed7aa",
                  danger="#f472a0", good="#5fd3a5", warn="#f6b26b", on_accent="#ffffff", viewer="#1c1626",
                  head1="#ffd6ea", head2="#e5d9ff", head3="#d4f1ff"),
    "dark": dict(bg="#221a2e", bg2="#1d1a33", bg3="#1a2333", surface="#2a2038", surface2="#221d36",
                 card="rgba(52,40,70,0.82)", card_solid="#33284a", raised="#3a2e50", border="#4d3d66", border_soft="#41345a",
                 text="#f6ecff", muted="#c3b1dc", faint="#8a789f", accent=ACCENT, accent_hover="#c4b5fd",
                 accent_soft="rgba(167,139,250,0.22)", accent2="#f9a8d4", chip="#3a2e50", chip_hover="#4a3a64",
                 pink="#f9a8d4", lavender="#c4b5fd", mint="#86efac", blue="#93c5fd", peach="#fdba74",
                 danger="#fb7aa8", good="#6ee7b7", warn="#fcd34d", on_accent="#ffffff", viewer="#120e18",
                 head1="#4a2a4f", head2="#3a2d5c", head3="#25365a"),
}

RADIUS = dict(sm=10, md=14, lg=18, xl=24, pill=999)
FONT = dict(xs="8.5pt", sm="9.5pt", base="10pt", md="11.5pt", lg="15pt", xl="22pt", hero="30pt")
SPACE = dict(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
FONT_FAMILY = '"Nunito", "Quicksand", "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", sans-serif'

QSS = """
* {{ font-family: {family}; font-size: {f_base}; color: {text}; }}
QMainWindow, QDialog, QMessageBox {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {bg}, stop:0.55 {bg2}, stop:1 {bg3}); }}
QWidget#root {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {bg}, stop:0.55 {bg2}, stop:1 {bg3}); }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {card_solid}; color: {text}; border: 2px solid {lavender}; padding: 6px 12px; border-radius: {r_md}px; }}
QMenu {{ background: {card_solid}; border: 2px solid {border}; border-radius: {r_lg}px; padding: 8px; }}
QMenu::item {{ padding: 8px 20px 8px 14px; border-radius: {r_sm}px; }}
QMenu::item:selected {{ background: {accent_soft}; }}
QMenu::separator {{ height: 2px; background: {border_soft}; margin: 5px 10px; }}

/* ---------- sidebar ---------- */
QWidget#sideFoot, QWidget#sideFootPanel, QLabel#brandSub, QListWidget#sidebar {{ border: none; }}
QWidget#sidebarPane {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {surface}, stop:0.6 {surface2}, stop:1 {bg3});
    border-right: 2px solid {border_soft}; }}
QListWidget#sidebar {{ background: transparent; padding: 4px 12px; outline: 0; }}
QListWidget#sidebar::item {{ padding: 9px 14px; margin: 2px 0; border-radius: 12px; color: {muted}; font-weight: 600; }}
QListWidget#sidebar::item:hover {{ background: {chip_hover}; color: {text}; }}
QListWidget#sidebar::item:selected {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2});
    color: {on_accent}; font-weight: 800; }}
QListWidget#sidebar QScrollBar:vertical {{ width: 6px; }}
QLabel#brand {{ font-size: {f_lg}; font-weight: 900; padding: 20px 10px 0 18px; color: {accent}; background: transparent; }}
QLabel#brandSub {{ color: {muted}; padding: 0 18px 12px 18px; font-size: {f_xs}; font-weight: 700; background: transparent; }}
QWidget#sideFootPanel {{ border-top: 2px dashed {border}; }}

/* ---------- page header banner ---------- */
QFrame#pageHeader {{ border-radius: {r_xl}px; border: 2px solid {border_soft};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {head1}, stop:0.5 {head2}, stop:1 {head3}); }}
QLabel#sparkles {{ color: {accent}; font-size: {f_lg}; font-weight: 800; letter-spacing: 4px; }}
QLabel#h1 {{ font-size: {f_xl}; font-weight: 900; color: {text}; }}
QLabel#h2 {{ font-size: {f_md}; font-weight: 800; color: {text}; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#hint {{ font-size: {f_sm}; }}
QLabel#groupLabel {{ color: {accent}; font-size: {f_xs}; font-weight: 900; letter-spacing: 1.5px; padding-top: 8px; }}
QLabel#scoreBig {{ font-size: {f_hero}; font-weight: 900; color: {accent}; }}
QLabel#badge {{ background: {accent_soft}; color: {text}; border-radius: 10px; padding: 2px 10px; font-size: {f_xs}; font-weight: 800; }}

/* ---------- surfaces ---------- */
QFrame#card {{ background: {card}; border: 2px solid {border_soft}; border-radius: {r_xl}px; }}
QFrame#skeleton {{ background: {chip_hover}; border-radius: {r_lg}px; }}
QPushButton#statusDot {{ text-align: left; border: none; background: transparent; padding: 3px 0; color: {muted}; font-weight: 700; }}
QPushButton#statusDot:hover {{ color: {accent}; }}
QPushButton#homeTile {{ border: 2px solid {border_soft}; border-radius: {r_xl}px; padding: 18px 16px; font-size: {f_md}; font-weight: 800;
    text-align: left; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {card_solid}, stop:1 {chip_hover}); }}
QPushButton#homeTile:hover {{ border-color: {accent2}; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {head1}, stop:1 {head2}); }}
QPushButton#homeTile:pressed {{ background: {accent_soft}; }}
QDialog#viewer {{ background: {viewer}; }}
QLabel#viewerCaption {{ color: #e9dcf7; padding: 8px; font-size: {f_sm}; background: {viewer}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {raised}; border: 2px solid {border}; border-radius: {r_md}px; padding: 7px 12px;
    selection-background-color: {accent2}; selection-color: {text}; }}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {lavender}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 2px solid {accent}; background: {card_solid}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {faint}; }}
QComboBox {{ padding-right: 32px; border-radius: 15px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 30px; border: none;
    border-top-right-radius: 15px; border-bottom-right-radius: 15px; }}
QComboBox::drop-down:hover {{ background: {accent_soft}; }}
QComboBox::down-arrow {{ image: url("{arrow}"); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{ background: {card_solid}; border: 2px solid {border}; border-radius: {r_md}px; padding: 6px;
    selection-background-color: {accent_soft}; selection-color: {text}; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}

/* ---------- buttons (pills) ---------- */
QPushButton {{ background: {chip}; border: 2px solid {border}; border-radius: 12px; padding: 6px 10px; font-weight: 600; }}
QPushButton:hover {{ background: {chip_hover}; border-color: {accent2}; color: {accent}; }}
QPushButton:pressed {{ background: {accent_soft}; border-color: {accent}; padding-top: 9px; padding-bottom: 5px; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {faint}; background: {raised}; border-color: {border_soft}; }}
QPushButton#primary {{ color: {on_accent}; border: none; font-weight: 900; padding: 9px 22px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2}); }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_hover}, stop:1 {pink}); color: {on_accent}; }}
QPushButton#primary:pressed {{ background: {accent}; padding-top: 11px; padding-bottom: 7px; }}
QPushButton#primary:disabled {{ background: {accent_soft}; color: {muted}; }}
QPushButton#ghost {{ background: transparent; border: 2px solid transparent; color: {muted}; padding: 6px 12px; }}
QPushButton#ghost:hover {{ color: {accent}; background: {chip_hover}; }}
QPushButton#danger:hover {{ border-color: {danger}; color: {danger}; }}
QPushButton#dangerArmed {{ background: {danger}; border: 2px solid {danger}; color: {on_accent}; font-weight: 900; }}
QPushButton#chip {{ background: {card_solid}; border: 2px solid {border}; border-radius: 13px; padding: 5px 14px; font-weight: 700; }}
QPushButton#chip:hover {{ background: {head1}; border-color: {accent2}; }}
QPushButton#chip:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2}); color: {on_accent}; border-color: transparent; }}
QPushButton#selChip {{ background: {head2}; border: 2px solid {lavender}; border-radius: 13px; padding: 4px 12px; font-weight: 700; }}
QPushButton#selChip:hover {{ border-color: {danger}; background: {head1}; }}

/* ---------- lists ---------- */
QListWidget {{ background: {raised}; border: 2px solid {border_soft}; border-radius: {r_lg}px; padding: 6px; outline: 0; }}
QListWidget::item {{ padding: 8px 12px; border-radius: {r_md}px; }}
QListWidget::item:hover {{ background: {chip_hover}; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QCheckBox, QRadioButton {{ spacing: 9px; font-weight: 600; }}
QCheckBox::indicator {{ width: 34px; height: 18px; border-radius: 11px; border: 2px solid {border}; background: {chip_hover}; image: url("{knob_off}"); }}
QCheckBox::indicator:hover {{ border-color: {accent2}; }}
QCheckBox::indicator:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2}); border-color: {accent}; image: url("{knob_on}"); }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 2px solid {border}; border-radius: 10px; background: {raised}; }}
QRadioButton::indicator:checked {{ border: 5px solid {accent}; background: {on_accent}; }}

/* ---------- scroll / progress / slider ---------- */
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {lavender}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {accent2}; margin: 0; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QSplitter::handle {{ background: transparent; }}
QProgressBar {{ background: {chip_hover}; border: 2px solid {border_soft}; border-radius: 8px; height: 14px; max-height: 14px; text-align: center; font-size: 1pt; }}
QProgressBar::chunk {{ border-radius: 6px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {mint}, stop:0.5 {blue}, stop:1 {lavender}); }}
QSlider {{ min-height: 26px; }}
QSlider::groove:horizontal {{ height: 10px; background: {chip_hover}; border: 2px solid {border_soft}; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {pink}, stop:1 {accent}); border-radius: 7px; }}
QSlider::handle:horizontal {{ background: {card_solid}; border: 3px solid {accent}; width: 18px; height: 18px; margin: -8px 0; border-radius: 12px; }}
QSlider::handle:horizontal:hover {{ border-color: {accent2}; background: {head1}; }}
QTabWidget::pane {{ border: 2px solid {border_soft}; border-radius: {r_lg}px; top: -1px; background: {card}; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 8px 18px; border-radius: 16px; font-weight: 700; margin: 2px; }}
QTabBar::tab:hover {{ background: {chip_hover}; }}
QTabBar::tab:selected {{ background: {accent}; color: {on_accent}; }}
QGroupBox {{ border: 2px solid {border_soft}; border-radius: {r_lg}px; margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {accent}; font-weight: 800; }}

/* ---------- feedback ---------- */
QLabel#dropZone {{ border: 3px dashed {accent2}; border-radius: {r_xl}px; color: {muted}; background: {raised}; font-weight: 700; }}
QLabel#dropZone:hover {{ border-color: {accent}; background: {head1}; }}
QLabel#toast {{ background: {card_solid}; color: {text}; border: 2px solid {mint}; border-radius: 20px; padding: 11px 20px; font-weight: 700; }}
QLabel#toastError {{ background: {card_solid}; color: {text}; border: 2px solid {danger}; border-radius: 20px; padding: 11px 20px; font-weight: 700; }}
QLabel#emptyState {{ color: {muted}; font-size: {f_md}; padding: 28px; border: 2px dashed {accent2}; border-radius: {r_xl}px; }}
"""

def arrow_png(name):
    """Draw the combo-box arrow as a small PNG (no SVG plugin needed). Qt hides the native arrow as soon as
    ::drop-down is styled, so without an explicit image editable combos showed no arrow at all."""
    import os, tempfile
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
    path = os.path.join(tempfile.gettempdir(), f"promptmaker_arrow_{name}.png").replace(os.sep, "/")
    img = QImage(20, 12, QImage.Format_ARGB32); img.fill(Qt.transparent)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
    p.setBrush(QColor(PALETTES[name]["text"]))
    p.drawPolygon(QPolygonF([QPointF(1, 1), QPointF(19, 1), QPointF(10, 11)])); p.end()
    img.save(path, "PNG")
    return path


# Pastel accents — (dark, dark hover, light, light hover). Keys are kept from 4.1 so saved choices still load.
ACCENTS = {"purple": ("#a78bfa", "#c4b5fd", "#9b7bf0", "#b49afa"),
           "pink": ("#f9a8d4", "#fbcfe8", "#f07ab8", "#f59ccb"),
           "teal": ("#6ee7b7", "#a7f3d0", "#3cc497", "#5fd3a5"),
           "blue": ("#93c5fd", "#bfdbfe", "#5fa8f0", "#86bdf5"),
           "orange": ("#fdba74", "#fed7aa", "#f59e5b", "#f8b67f")}
ACCENT_NAMES = {"purple": "Lavender", "pink": "Sakura pink", "teal": "Mint", "blue": "Baby blue", "orange": "Peach"}

def _rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def colors(name, accent="purple"):
    pal = dict(PALETTES[name])
    a = ACCENTS.get(accent) or ACCENTS["purple"]
    main, hover = (a[0], a[1]) if name == "dark" else (a[2], a[3])
    if accent == "pink":
        pal["accent2"] = pal["lavender"]
    pal.update(accent=main, accent_hover=hover, accent_soft=_rgba(main, 0.24 if name == "dark" else 0.18))
    return pal


def check_png():
    """White tick for checked checkboxes (drawn, like the arrow, so no SVG plugin is needed)."""
    import os, tempfile
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    path = os.path.join(tempfile.gettempdir(), "promptmaker_check.png").replace(os.sep, "/")
    img = QImage(32, 32, QImage.Format_ARGB32); img.fill(Qt.transparent)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#ffffff"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(7, 17), QPointF(13, 23), QPointF(25, 9)]); p.end()
    img.save(path, "PNG")
    return path


def tokens():
    t = {f"r_{k}": v for k, v in RADIUS.items()}
    t.update({f"f_{k}": v for k, v in FONT.items()})
    return t


def knob_png(on):
    """Round white knob for the pill toggle switches (checkboxes) – left when off, right when on."""
    import tempfile
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    path = os.path.join(tempfile.gettempdir(), f"promptmaker_knob_{int(on)}.png").replace(os.sep, "/")
    img = QImage(68, 36, QImage.Format_ARGB32); img.fill(Qt.transparent)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 30)); p.drawEllipse(38 if on else 4, 6, 28, 28)
    p.setBrush(QColor("#ffffff")); p.drawEllipse(36 if on else 2, 3, 28, 28); p.end()
    img.save(path, "PNG")
    return path


_FONTS_LOADED = []


def load_fonts():
    """Register the bundled Nunito (SIL OFL, see assets/fonts/OFL.txt). Missing file → system fallback fonts."""
    if _FONTS_LOADED:
        return _FONTS_LOADED[0]
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    if QGuiApplication.instance() is None:  # the font database needs a running app (else Qt crashes)
        return False
    f = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Nunito.ttf")
    ok = os.path.exists(f) and QFontDatabase.addApplicationFont(f) >= 0
    _FONTS_LOADED.append(ok)
    return ok


_CURRENT = ["light"]


def stylesheet(name, accent="purple"):
    load_fonts(); _CURRENT[0] = name
    return QSS.format(arrow=arrow_png(name), check=check_png(), knob_on=knob_png(True), knob_off=knob_png(False),
                      family=FONT_FAMILY, **tokens(), **colors(name, accent))


def add_shadow(widget, blur=28, y=6, name=None):
    """Soft drop shadow for floating surfaces (cards, tiles, toasts). Skipped offscreen (tests) to keep them fast."""
    from PySide6.QtWidgets import QApplication
    if QApplication.platformName() in ("offscreen", "minimal") and not os.environ.get("PROMPTMAKER_SHADOWS"):
        return None
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget); eff.setBlurRadius(blur); eff.setOffset(0, y)
    eff.setColor(QColor(167, 139, 250, 110) if (name or "light") == "dark" else QColor(240, 122, 184, 70))
    widget.setGraphicsEffect(eff)
    return eff


class HoverLift:
    """Event filter that animates a widget's shadow on hover – the 'smooth transition' QSS can't do."""

    def __init__(self):
        from PySide6.QtCore import QObject

        class _F(QObject):
            def eventFilter(s, obj, ev):
                from PySide6.QtCore import QEvent, QPropertyAnimation, QEasingCurve
                eff = obj.graphicsEffect()
                if eff is None or not hasattr(eff, "setBlurRadius") or ev.type() not in (QEvent.Enter, QEvent.Leave):
                    return False
                a = QPropertyAnimation(eff, b"blurRadius", obj); a.setDuration(260); a.setEasingCurve(QEasingCurve.OutBack)
                a.setEndValue(42.0 if ev.type() == QEvent.Enter else 18.0); a.start(QPropertyAnimation.DeleteWhenStopped)
                b = QPropertyAnimation(eff, b"offset", obj); b.setDuration(320); b.setEasingCurve(QEasingCurve.OutBack)
                from PySide6.QtCore import QPointF
                b.setEndValue(QPointF(0, 10) if ev.type() == QEvent.Enter else QPointF(0, 4)); b.start(QPropertyAnimation.DeleteWhenStopped)
                return False
        self.filter = _F()

    def attach(self, widget, name=None):
        if add_shadow(widget, blur=18, y=4, name=name) is not None:
            widget.installEventFilter(self.filter)
        return widget


_LIFT = []


def lift(widget):
    """Bouncy coloured hover shadow for primary buttons and tiles (no-op offscreen)."""
    if not _LIFT:
        _LIFT.append(HoverLift())
    return _LIFT[0].attach(widget, _CURRENT[0])
