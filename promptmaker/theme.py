"""PromptMaker design system (4.1.5): four themes (Graphite light/dark default, Pastel, Pastel dusk) built from palette +
scale tokens into one app-wide QSS, plus the app-chrome styles and shadow / hover helpers."""
import os

ACCENT = "#7c5cff"
PASTEL_ACCENT = "#a78bfa"
THEMES = {"light": "Graphite light", "dark": "Graphite dark", "pastel": "Pastel", "pastel_dusk": "Pastel dusk"}
DARK_THEMES = {"dark", "pastel_dusk"}
PAIR = {"light": "dark", "dark": "light", "pastel": "pastel_dusk", "pastel_dusk": "pastel"}

PASTEL_PALETTES = {
    "pastel": dict(bg="#fdf2f8", bg2="#f3ecff", bg3="#eaf4ff", surface="#fff5fa", surface2="#f1eaff",
                  card="rgba(255,255,255,0.86)", card_solid="#ffffff", raised="#fff7fb", border="#f3d3e6", border_soft="#f7e3ef",
                  text="#4a3b5c", muted="#8f7fa6", faint="#c0b2d3", accent="#9b7bf0", accent_hover="#b49afa",
                  accent_soft="rgba(155,123,240,0.16)", accent2="#f9a8d4", chip="#ffffff", chip_hover="#fde7f3",
                  pink="#f9a8d4", lavender="#c4b5fd", mint="#a7f3d0", blue="#bae6fd", peach="#fed7aa",
                  danger="#f472a0", good="#5fd3a5", warn="#f6b26b", on_accent="#ffffff", viewer="#1c1626",
                  head1="#ffd6ea", head2="#e5d9ff", head3="#d4f1ff",
                  rail_bg="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fff5fa, stop:1 #eaf4ff)", top_bg="rgba(255,255,255,0.6)"),
    "pastel_dusk": dict(bg="#221a2e", bg2="#1d1a33", bg3="#1a2333", surface="#2a2038", surface2="#221d36",
                 card="rgba(52,40,70,0.82)", card_solid="#33284a", raised="#3a2e50", border="#4d3d66", border_soft="#41345a",
                 text="#f6ecff", muted="#c3b1dc", faint="#8a789f", accent=PASTEL_ACCENT, accent_hover="#c4b5fd",
                 accent_soft="rgba(167,139,250,0.22)", accent2="#f9a8d4", chip="#3a2e50", chip_hover="#4a3a64",
                 pink="#f9a8d4", lavender="#c4b5fd", mint="#86efac", blue="#93c5fd", peach="#fdba74",
                 danger="#fb7aa8", good="#6ee7b7", warn="#fcd34d", on_accent="#ffffff", viewer="#120e18",
                 head1="#4a2a4f", head2="#3a2d5c", head3="#25365a",
                 rail_bg="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2038, stop:1 #1a2333)", top_bg="rgba(42,32,56,0.7)"),
}

PALETTES = {
    "light": dict(bg="#f6f7f9", surface="#ffffff", card="#ffffff", card_solid="#ffffff", raised="#f3f4f7", border="#e2e4ea",
                  border_soft="#eceef2", text="#111318", muted="#5f6573", faint="#9aa0ad", accent=ACCENT, accent_hover="#6a48ff",
                  accent_soft="rgba(124,92,255,0.12)", chip="#ffffff", chip_hover="#eef0f4", danger="#e5484d", good="#18a957",
                  warn="#d99a00", on_accent="#ffffff", viewer="#0b0c0f", rail_bg="#ffffff", top_bg="#ffffff", shadow="rgba(0,0,0,0.1)"),
    "dark": dict(bg="#0c0d10", surface="#111216", card="#15161b", card_solid="#15161b", raised="#1b1d23", border="#272a32",
                 border_soft="#1f2128", text="#e8e9ee", muted="#8b8f9c", faint="#5b5f6b", accent=ACCENT, accent_hover="#9479ff",
                 accent_soft="rgba(124,92,255,0.18)", chip="#1b1d23", chip_hover="#23262e", danger="#ff6b81", good="#35d39a",
                 warn="#ffc34d", on_accent="#ffffff", viewer="#07070a", rail_bg="#0f1013", top_bg="#0f1013", shadow="rgba(0,0,0,0.5)"),
}

RADIUS = dict(sm=6, md=8, lg=12, xl=16, pill=999)
FONT = dict(xs="8pt", sm="9pt", base="10pt", md="11pt", lg="13pt", xl="20pt", hero="28pt")
PASTEL_RADIUS = dict(sm=10, md=14, lg=18, xl=24, pill=999)
PASTEL_FONT = dict(xs="8.5pt", sm="9.5pt", base="10pt", md="11.5pt", lg="15pt", xl="22pt", hero="30pt")
SPACE = dict(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Inter", "Helvetica Neue", sans-serif'
PASTEL_FAMILY = '"Nunito", "Quicksand", "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", sans-serif'
PALETTES.update(PASTEL_PALETTES)

QSS_SLEEK = """
* {{ font-family: {family}; font-size: {f_base}; color: {text}; }}
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
QFrame#pageHeader {{ background: transparent; border: none; }}
QLabel#sparkles {{ color: transparent; font-size: 1pt; }}
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

QSS_PASTEL = """
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
QFrame#pageHeader {{ border-radius: {r_xl}px; border: 2px solid {border_soft}; padding: 8px 20px;
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

QSS_CHROME = """/* ---------- 4.1.5 app chrome: rail, top bar, page tabs, inspector, filmstrip, command palette ---------- */
QWidget#rail {{ background: {rail_bg}; border-right: 1px solid {border_soft}; }}
QLabel#railLogo {{ color: {accent}; font-size: 13pt; font-weight: 900; padding: 14px 0 12px 0; }}
QPushButton#railBtn {{ background: transparent; border: none; border-radius: {r_md}px; padding: 9px 12px; color: {muted};
    text-align: left; font-weight: 600; }}
QPushButton#railBtn:hover {{ background: {chip_hover}; color: {text}; }}
QPushButton#railBtn:checked {{ background: {accent_soft}; color: {accent}; font-weight: 700; }}
QWidget#topBar {{ background: {top_bg}; border-bottom: 1px solid {border_soft}; }}
QLineEdit#search {{ border-radius: {r_lg}px; padding: 7px 14px; background: {raised}; }}
QLabel#sectionTitle {{ font-size: {f_lg}; font-weight: 800; padding-right: 8px; }}
QPushButton#subTab {{ background: transparent; border: 1px solid transparent; border-radius: {r_md}px; padding: 5px 12px; color: {muted}; font-weight: 600; }}
QPushButton#subTab:hover {{ color: {text}; background: {chip_hover}; }}
QPushButton#subTab:checked {{ color: {on_accent}; background: {accent}; border-color: {accent}; }}
QFrame#inspector {{ background: {card_solid}; border: none; border-left: 1px solid {border_soft}; border-radius: 0; }}
QLabel#inspTitle {{ font-size: {f_md}; font-weight: 800; }}
QListWidget#filmstrip {{ background: {card_solid}; border: none; border-top: 1px solid {border_soft}; border-radius: 0; padding: 4px 10px; }}
QListWidget#filmstrip::item {{ padding: 2px; border-radius: {r_sm}px; }}
QListWidget#filmstrip::item:hover {{ background: {accent_soft}; }}
QFrame#palette {{ background: {card_solid}; border: 1px solid {border}; border-radius: {r_lg}px; }}
QListWidget#paletteList {{ background: transparent; border: none; }}
QListWidget#settingsNav {{ background: transparent; border: none; }}
QListWidget#settingsNav::item {{ padding: 10px 14px; border-radius: {r_md}px; color: {muted}; font-weight: 600; }}
QListWidget#settingsNav::item:selected {{ background: {accent_soft}; color: {text}; }}
QLabel#statValue {{ font-size: {f_xl}; font-weight: 800; color: {accent}; }}
QLabel#statLabel {{ color: {muted}; font-size: {f_sm}; font-weight: 600; }}
QFrame#vsep {{ background: {border}; border: none; }}
QPushButton#search {{ background: {raised}; border: 1px solid {border_soft}; border-radius: {r_lg}px; padding: 8px 14px; color: {muted}; font-weight: 500; }}
QPushButton#search:hover {{ border-color: {accent}; color: {text}; }}
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
    p.setBrush(QColor(PALETTES[normalise(name)]["text"]))
    p.drawPolygon(QPolygonF([QPointF(1, 1), QPointF(19, 1), QPointF(10, 11)])); p.end()
    img.save(path, "PNG")
    return path


# Pastel accents — (dark, dark hover, light, light hover). Keys are kept from 4.1 so saved choices still load.
ACCENTS = {"purple": ("#7c5cff", "#9479ff", "#6a48ff", "#5a3de0"),
           "blue": ("#3b82f6", "#60a5fa", "#2563eb", "#1d4ed8"),
           "teal": ("#14b8a6", "#2dd4bf", "#0d9488", "#0f766e"),
           "pink": ("#ec4899", "#f472b6", "#db2777", "#be185d"),
           "orange": ("#f97316", "#fb923c", "#ea580c", "#c2410c")}
PASTEL_ACCENTS = {"purple": ("#a78bfa", "#c4b5fd", "#9b7bf0", "#b49afa"),
           "pink": ("#f9a8d4", "#fbcfe8", "#f07ab8", "#f59ccb"),
           "teal": ("#6ee7b7", "#a7f3d0", "#3cc497", "#5fd3a5"),
           "blue": ("#93c5fd", "#bfdbfe", "#5fa8f0", "#86bdf5"),
           "orange": ("#fdba74", "#fed7aa", "#f59e5b", "#f8b67f")}
ACCENT_NAMES = {"purple": "Violet", "blue": "Blue", "teal": "Teal", "pink": "Pink", "orange": "Orange"}
PASTEL_ACCENT_NAMES = {"purple": "Lavender", "pink": "Sakura pink", "teal": "Mint", "blue": "Baby blue", "orange": "Peach"}

def _rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def normalise(name):
    return name if name in THEMES else "dark"


def is_pastel(name):
    return name in PASTEL_PALETTES


def colors(name, accent="purple"):
    name = normalise(name)
    pal = dict(PALETTES[name])
    table = PASTEL_ACCENTS if is_pastel(name) else ACCENTS
    a = table.get(accent) or table["purple"]
    dark = name in DARK_THEMES
    main, hover = (a[0], a[1]) if dark else (a[2], a[3])
    if is_pastel(name) and accent == "pink":
        pal["accent2"] = pal["lavender"]
    soft = (0.24 if dark else 0.18) if is_pastel(name) else (0.18 if dark else 0.12)
    pal.update(accent=main, accent_hover=hover, accent_soft=_rgba(main, soft))
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


def tokens(name="dark"):
    t = {f"r_{k}": v for k, v in (PASTEL_RADIUS if is_pastel(name) else RADIUS).items()}
    t.update({f"f_{k}": v for k, v in (PASTEL_FONT if is_pastel(name) else FONT).items()})
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
    name = normalise(name)
    load_fonts(); _CURRENT[0] = name
    kw = dict(arrow=arrow_png(name), check=check_png(), knob_on=knob_png(True), knob_off=knob_png(False),
              family=PASTEL_FAMILY if is_pastel(name) else FONT_FAMILY, **tokens(name), **colors(name, accent))
    return (QSS_PASTEL if is_pastel(name) else QSS_SLEEK).format(**kw) + QSS_CHROME.format(**kw)


def add_shadow(widget, blur=28, y=6, name=None):
    """Soft drop shadow for floating surfaces (cards, tiles, toasts). Skipped offscreen (tests) to keep them fast."""
    from PySide6.QtWidgets import QApplication
    if QApplication.platformName() in ("offscreen", "minimal") and not os.environ.get("PROMPTMAKER_SHADOWS"):
        return None
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget); eff.setBlurRadius(blur); eff.setOffset(0, y)
    if is_pastel(name or ""):
        eff.setColor(QColor(167, 139, 250, 110) if name == "pastel_dusk" else QColor(240, 122, 184, 70))
    else:
        eff.setColor(QColor(0, 0, 0, 110 if name in DARK_THEMES else 40))
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
