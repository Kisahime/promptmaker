"""PromptMaker design system (4.1.5): palette + scale tokens -> one app-wide QSS, plus shadow / hover helpers."""
import os
ACCENT = "#7c5cff"
# 4.1.5 design system. Neutral ramps are slightly cool and low-contrast so the accent carries the hierarchy:
#   bg (window) < surface (sidebar) < card (panels) < raised (inputs) < chip (buttons) < chip_hover.
PALETTES = {
    "dark": dict(bg="#0f1016", surface="#14151d", card="#191b24", raised="#1f222d", border="#2a2e3c", border_soft="#22252f",
                 text="#eceef6", muted="#8d93ab", faint="#5d6378", accent=ACCENT, accent_hover="#9479ff",
                 accent_soft="rgba(124,92,255,0.18)", chip="#232633", chip_hover="#2c3040", danger="#ff6b81",
                 good="#35d39a", warn="#ffc34d", shadow="rgba(0,0,0,0.55)", on_accent="#ffffff", viewer="#07070a"),
    "light": dict(bg="#f4f5f9", surface="#fbfbfd", card="#ffffff", raised="#f3f4f8", border="#e1e4ed", border_soft="#eceef4",
                  text="#171923", muted="#646a82", faint="#9ba0b3", accent="#6a4cf0", accent_hover="#5a3de0",
                  accent_soft="rgba(106,76,240,0.12)", chip="#ffffff", chip_hover="#f0f1f7", danger="#e0425d",
                  good="#1fa776", warn="#d99a00", shadow="rgba(23,25,35,0.10)", on_accent="#ffffff", viewer="#07070a"),
}

# Scale tokens (px / pt) – every radius and font size in the QSS comes from here.
RADIUS = dict(sm=6, md=8, lg=12, xl=16, pill=999)
FONT = dict(xs="8pt", sm="9pt", base="10pt", md="11pt", lg="13pt", xl="20pt", hero="28pt")
SPACE = dict(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)

QSS = """
* {{ font-family: "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
     font-size: {f_base}; color: {text}; }}
QMainWindow, QWidget#root, QDialog, QMessageBox {{ background: {bg}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {card}; color: {text}; border: 1px solid {border}; padding: 6px 10px; border-radius: {r_md}px; font-size: {f_sm}; }}
QMenu {{ background: {card}; border: 1px solid {border}; border-radius: {r_lg}px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: {r_sm}px; }}
QMenu::item:selected {{ background: {accent_soft}; }}
QMenu::separator {{ height: 1px; background: {border_soft}; margin: 5px 8px; }}

/* ---------- sidebar ---------- */
QListWidget#sidebar {{ background: {surface}; border: none; border-right: 1px solid {border_soft}; padding: 6px 10px; outline: 0; }}
QListWidget#sidebar::item {{ padding: 8px 12px; margin: 1px 0; border-radius: {r_md}px; color: {muted}; border: none; }}
QListWidget#sidebar::item:hover {{ background: {chip}; color: {text}; }}
QListWidget#sidebar::item:selected {{ background: {accent_soft}; color: {text}; font-weight: 600; border-left: 3px solid {accent}; }}
QListWidget#sidebar QScrollBar:vertical {{ width: 6px; }}
QLabel#brand {{ font-size: {f_lg}; font-weight: 700; padding: 20px 16px 2px 18px; background: {surface}; color: {text}; }}
QLabel#brandSub {{ color: {faint}; padding: 0 18px 12px 18px; background: {surface}; font-size: {f_xs};
    border-right: 1px solid {border_soft}; }}
QWidget#sideFoot {{ background: {surface}; border-right: 1px solid {border_soft}; }}
QWidget#sideFootPanel {{ background: {surface}; border-right: 1px solid {border_soft}; border-top: 1px solid {border_soft}; }}

/* ---------- type scale ---------- */
QLabel#h1 {{ font-size: {f_xl}; font-weight: 700; padding-bottom: 2px; }}
QLabel#h2 {{ font-size: {f_md}; font-weight: 600; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#hint {{ font-size: {f_sm}; }}
QLabel#groupLabel {{ color: {faint}; font-size: {f_xs}; font-weight: 700; letter-spacing: 1.2px; padding-top: 8px; }}
QLabel#emptyState {{ color: {muted}; font-size: {f_md}; padding: 28px; border: 1px dashed {border}; border-radius: {r_lg}px; }}
QLabel#scoreBig {{ font-size: {f_hero}; font-weight: 800; color: {accent}; }}
QLabel#badge {{ background: {accent_soft}; color: {text}; border-radius: {r_md}px; padding: 2px 9px; font-size: {f_xs}; font-weight: 600; }}

/* ---------- surfaces ---------- */
QFrame#card {{ background: {card}; border: 1px solid {border_soft}; border-radius: {r_xl}px; }}
QFrame#skeleton {{ background: {raised}; border-radius: {r_lg}px; }}
QPushButton#statusDot {{ text-align: left; border: none; background: transparent; padding: 3px 0; color: {muted}; font-size: {f_sm}; }}
QPushButton#statusDot:hover {{ color: {text}; }}
QPushButton#homeTile {{ background: {raised}; border: 1px solid {border_soft}; border-radius: {r_lg}px; padding: 16px 14px;
    font-size: {f_md}; font-weight: 600; text-align: left; }}
QPushButton#homeTile:hover {{ border-color: {accent}; background: {accent_soft}; }}
QPushButton#homeTile:pressed {{ background: {chip_hover}; }}
QDialog#viewer {{ background: {viewer}; }}
QLabel#viewerCaption {{ color: #a9adbd; padding: 8px; font-size: {f_sm}; background: {viewer}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {raised}; border: 1px solid {border}; border-radius: {r_md}px; padding: 7px 10px;
    selection-background-color: {accent}; selection-color: {on_accent}; }}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {faint}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {accent}; background: {card}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {faint}; }}
QComboBox {{ padding-right: 30px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none;
    border-top-right-radius: {r_md}px; border-bottom-right-radius: {r_md}px; }}
QComboBox::drop-down:hover {{ background: {chip_hover}; }}
QComboBox::down-arrow {{ image: url("{arrow}"); width: 10px; height: 6px; }}
QComboBox::down-arrow:on {{ top: 1px; }}
QComboBox QAbstractItemView {{ background: {card}; border: 1px solid {border}; border-radius: {r_md}px; padding: 4px;
    selection-background-color: {accent_soft}; selection-color: {text}; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {chip}; border: 1px solid {border}; border-radius: {r_md}px; padding: 7px 15px; font-weight: 500; }}
QPushButton:hover {{ background: {chip_hover}; border-color: {faint}; }}
QPushButton:pressed {{ background: {accent_soft}; border-color: {accent}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {faint}; background: {raised}; border-color: {border_soft}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border: 1px solid {accent}; font-weight: 600; padding: 8px 18px; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent}; padding-top: 9px; padding-bottom: 7px; }}
QPushButton#primary:disabled {{ background: {accent_soft}; border-color: transparent; color: {muted}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {muted}; padding: 6px 10px; }}
QPushButton#ghost:hover {{ color: {text}; background: {chip}; }}
QPushButton#ghost:pressed {{ background: {chip_hover}; }}
QPushButton#danger:hover {{ border-color: {danger}; color: {danger}; }}
QPushButton#dangerArmed {{ background: {danger}; border: 1px solid {danger}; color: {on_accent}; font-weight: 600; }}
QPushButton#chip {{ background: {raised}; border: 1px solid {border}; border-radius: 15px; padding: 5px 13px; font-weight: 500; }}
QPushButton#chip:hover {{ background: {chip_hover}; border-color: {accent}; }}
QPushButton#chip:checked {{ background: {accent}; color: {on_accent}; border-color: {accent}; }}
QPushButton#selChip {{ background: {accent_soft}; border: 1px solid {accent}; border-radius: 15px; padding: 4px 11px; }}
QPushButton#selChip:hover {{ border-color: {danger}; }}

/* ---------- lists ---------- */
QListWidget {{ background: {raised}; border: 1px solid {border_soft}; border-radius: {r_lg}px; padding: 5px; outline: 0; }}
QListWidget::item {{ padding: 8px 10px; border-radius: {r_md}px; }}
QListWidget::item:hover {{ background: {chip_hover}; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QListWidget#catList::item {{ padding: 7px 10px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator {{ border: 1px solid {border}; border-radius: 5px; background: {raised}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QRadioButton::indicator {{ border: 1px solid {border}; border-radius: 9px; background: {raised}; }}
QRadioButton::indicator:checked {{ border: 5px solid {accent}; background: {on_accent}; }}

/* ---------- scroll / split / progress / slider ---------- */
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 3px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {faint}; margin: 0; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {accent_soft}; }}
QProgressBar {{ background: {raised}; border: none; border-radius: 4px; height: 8px; max-height: 8px; text-align: center; font-size: 1pt; }}
QProgressBar::chunk {{ border-radius: 4px; background: {accent}; }}
QSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {on_accent}; border: 3px solid {accent}; width: 12px; height: 12px; margin: -7px 0; border-radius: 9px; }}
QSlider::handle:horizontal:hover {{ border-color: {accent_hover}; }}
QTabWidget::pane {{ border: 1px solid {border_soft}; border-radius: {r_lg}px; top: -1px; background: {card}; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 8px 16px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; font-weight: 600; }}
QGroupBox {{ border: 1px solid {border_soft}; border-radius: {r_lg}px; margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {muted}; font-weight: 600; }}

/* ---------- feedback ---------- */
QLabel#dropZone {{ border: 2px dashed {border}; border-radius: {r_xl}px; color: {muted}; background: {raised}; }}
QLabel#dropZone:hover {{ border-color: {accent}; }}
QLabel#toast {{ background: {card}; color: {text}; border: 1px solid {border}; border-left: 3px solid {good};
    border-radius: {r_lg}px; padding: 11px 18px; }}
QLabel#toastError {{ background: {card}; color: {text}; border: 1px solid {border}; border-left: 3px solid {danger};
    border-radius: {r_lg}px; padding: 11px 18px; }}
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


# 4.1: accent colours — (dark, dark hover, light, light hover)
ACCENTS = {"purple": ("#7c5cff", "#9479ff", "#6a4cf0", "#5a3de0"),
           "teal": ("#14b8a6", "#2dd4bf", "#0d9488", "#0f766e"),
           "pink": ("#ec4899", "#f472b6", "#db2777", "#be185d"),
           "orange": ("#f97316", "#fb923c", "#ea580c", "#c2410c")}


def _rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def colors(name, accent="purple"):
    pal = dict(PALETTES[name])
    a = ACCENTS.get(accent) or ACCENTS["purple"]
    main, hover = (a[0], a[1]) if name == "dark" else (a[2], a[3])
    pal.update(accent=main, accent_hover=hover, accent_soft=_rgba(main, 0.18 if name == "dark" else 0.12))
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


def stylesheet(name, accent="purple"):
    return QSS.format(arrow=arrow_png(name), check=check_png(), **tokens(), **colors(name, accent))


def add_shadow(widget, blur=28, y=6, name=None):
    """Soft drop shadow for floating surfaces (cards, tiles, toasts). Skipped offscreen (tests) to keep them fast."""
    from PySide6.QtWidgets import QApplication
    if QApplication.platformName() in ("offscreen", "minimal") and not os.environ.get("PROMPTMAKER_SHADOWS"):
        return None
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget); eff.setBlurRadius(blur); eff.setOffset(0, y)
    eff.setColor(QColor(0, 0, 0, 90 if (name or "dark") == "dark" else 28))
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
                a = QPropertyAnimation(eff, b"blurRadius", obj); a.setDuration(160); a.setEasingCurve(QEasingCurve.OutCubic)
                a.setEndValue(40.0 if ev.type() == QEvent.Enter else 18.0); a.start(QPropertyAnimation.DeleteWhenStopped)
                return False
        self.filter = _F()

    def attach(self, widget, name=None):
        if add_shadow(widget, blur=18, y=4, name=name) is not None:
            widget.installEventFilter(self.filter)
        return widget
