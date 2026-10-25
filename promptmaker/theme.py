"""Custom theme (dark / light) built from a small palette."""
ACCENT = "#7c5cff"
PALETTES = {
    "dark": dict(bg="#14151b", surface="#1d1f28", card="#232633", raised="#2c3040", border="#33384a",
                 text="#ecedf5", muted="#9aa0b8", accent=ACCENT, accent_hover="#9479ff", accent_soft="rgba(124,92,255,0.22)",
                 chip="#2a2e3d", chip_hover="#363b4f", danger="#ff6b81", good="#35d39a", warn="#ffc34d"),
    "light": dict(bg="#f3f4f9", surface="#ffffff", card="#ffffff", raised="#eef0f7", border="#dde0eb",
                  text="#1b1d27", muted="#6a7088", accent="#6a4cf0", accent_hover="#5a3de0", accent_soft="rgba(106,76,240,0.14)",
                  chip="#eef0f7", chip_hover="#e2e5f1", danger="#e0425d", good="#1fa776", warn="#d99a00"),
}

QSS = """
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {text}; }}
QMainWindow, QWidget#root {{ background: {bg}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {raised}; color: {text}; border: 1px solid {border}; padding: 6px; border-radius: 6px; }}
QListWidget#sidebar {{ background: {surface}; border: none; border-right: 1px solid {border}; padding: 10px 8px; outline: 0; }}
QListWidget#sidebar::item {{ padding: 7px 12px; margin: 1px 0; border-radius: 10px; color: {muted}; }}
QListWidget#sidebar::item:hover {{ background: {chip_hover}; color: {text}; }}
QListWidget#sidebar::item:selected {{ background: {accent_soft}; color: {text}; border-left: 3px solid {accent}; }}
QLabel#brand {{ font-size: 15pt; font-weight: 700; padding: 18px 16px 6px 16px; background: {surface}; }}
QLabel#brandSub {{ color: {muted}; padding: 0 16px 12px 16px; background: {surface}; font-size: 9pt; }}
QWidget#sideFoot {{ background: {surface}; border-right: 1px solid {border}; }}
QLabel#h1 {{ font-size: 18pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#groupLabel {{ color: {muted}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; padding-top: 6px; }}
QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 14px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox {{
    background: {raised}; border: 1px solid {border}; border-radius: 9px; padding: 6px 8px;
    selection-background-color: {accent}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {card}; border: 1px solid {border}; selection-background-color: {accent}; outline: 0; }}
QPushButton {{ background: {chip}; border: 1px solid {border}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ background: {chip_hover}; border-color: {accent}; }}
QPushButton:pressed {{ background: {accent_soft}; }}
QPushButton:disabled {{ color: {muted}; background: {raised}; border-color: {raised}; }}
QPushButton#primary {{ background: {accent}; color: white; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {muted}; }}
QPushButton#ghost:hover {{ color: {text}; background: {chip_hover}; }}
QPushButton#danger:hover {{ border-color: {danger}; color: {danger}; }}
QPushButton#dangerArmed {{ background: {danger}; border: 1px solid {danger}; color: white; font-weight: 600; }}
QPushButton#chip {{ background: {chip}; border: 1px solid {border}; border-radius: 14px; padding: 5px 12px; }}
QPushButton#chip:hover {{ background: {chip_hover}; border-color: {accent}; }}
QPushButton#chip:checked {{ background: {accent}; color: white; border-color: {accent}; }}
QPushButton#selChip {{ background: {accent_soft}; border: 1px solid {accent}; border-radius: 14px; padding: 4px 10px; }}
QPushButton#selChip:hover {{ border-color: {danger}; }}
QListWidget {{ background: {raised}; border: 1px solid {border}; border-radius: 10px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 8px; border-radius: 8px; }}
QListWidget::item:hover {{ background: {chip_hover}; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QListWidget#catList::item {{ padding: 7px 10px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator {{ border: 1px solid {border}; border-radius: 5px; background: {raised}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QSplitter::handle {{ background: transparent; }}
QProgressBar {{ background: {raised}; border: none; border-radius: 5px; height: 10px; text-align: center; font-size: 1pt; }}
QProgressBar::chunk {{ border-radius: 5px; background: {accent}; }}
QSlider::groove:horizontal {{ height: 6px; background: {raised}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; border: 2px solid {accent}; width: 14px; margin: -6px 0; border-radius: 8px; }}
QLabel#dropZone {{ border: 2px dashed {border}; border-radius: 14px; color: {muted}; background: {raised}; }}
QDoubleSpinBox {{ background: {raised}; border: 1px solid {border}; border-radius: 9px; padding: 6px 8px; }}
QLabel#toast {{ background: {raised}; color: {text}; border: 1px solid {accent}; border-radius: 12px; padding: 10px 16px; }}
QLabel#toastError {{ background: {raised}; color: {text}; border: 1px solid {danger}; border-radius: 12px; padding: 10px 16px; }}
QLabel#badge {{ background: {accent_soft}; color: {text}; border-radius: 8px; padding: 2px 8px; font-size: 8.5pt; }}
QLabel#scoreBig {{ font-size: 28pt; font-weight: 800; color: {accent}; }}
"""


def stylesheet(name):
    return QSS.format(**PALETTES[name])


def colors(name):
    return PALETTES[name]
