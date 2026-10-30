"""4.1.5 app shell: slim icon rail with sections, top bar (command palette, backend / AI status, target model),
page tabs per section, a Studio workspace (prompt pages centre, collapsible generation inspector on the right,
filmstrip of recent results at the bottom), two-pane Settings and the theme picker."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from . import theme
from .i18n import tr
from .widgets import button, label

# (icon, section, pages) – every page in NAV belongs to exactly one section.
SECTIONS = [("⌂", "Home", ["Home"]),
            ("✦", "Studio", ["Create", "Builder", "Refine", "Batch", "Templates"]),
            ("▦", "Gallery", ["Gallery", "A/B Test"]),
            ("◐", "Tools", ["Image to Prompt", "Auto-refine", "Pose", "Inpaint & Regions", "Video", "Analyse", "Score"]),
            ("❖", "Library", ["Presets", "Wildcards", "LoRAs", "History", "Favourites", "Packs", "Community"]),
            ("⚙", "Settings", ["Settings", "Model profiles", "Library sync"])]
STUDIO_PAGES = {"Create", "Builder", "Refine", "Batch", "Templates"}
RAIL_W, RAIL_W_COLLAPSED = 184, 64
INSPECTOR_MIN_W = 1360


def section_of(page):
    for _i, s, pages in SECTIONS:
        if page in pages:
            return s
    return "Home"


class Shell415:
    # ------------------------------------------------------------------ build
    def _build_chrome(self, root_layout, stack):
        root_layout.addWidget(self._rail())
        right = QVBoxLayout(); right.setContentsMargins(0, 0, 0, 0); right.setSpacing(0)
        right.addWidget(self._top_bar())
        right.addWidget(self._page_bar())
        work = QHBoxLayout(); work.setContentsMargins(0, 0, 0, 0); work.setSpacing(0)
        work.addWidget(stack, 1); work.addWidget(self._inspector())
        right.addLayout(work, 1)
        self.filmstrip = QListWidget(); self.filmstrip.setObjectName("filmstrip")
        self.filmstrip.setViewMode(QListWidget.IconMode); self.filmstrip.setFlow(QListWidget.LeftToRight)
        self.filmstrip.setWrapping(False); self.filmstrip.setMovement(QListWidget.Static)
        self.filmstrip.setIconSize(QSize(64, 64)); self.filmstrip.setFixedHeight(82); self.filmstrip.setSpacing(4)
        self.filmstrip.setToolTip(tr("Recent results – click to open"))
        self.filmstrip.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.gal_view(it.data(Qt.UserRole)))
        right.addWidget(self.filmstrip)
        root_layout.addLayout(right, 1)

    def _rail(self):
        from .app import NAV
        from . import __version__
        w = QWidget(); w.setObjectName("rail"); w.setAttribute(Qt.WA_StyledBackground, True); w.setFixedWidth(RAIL_W)
        self.sidebar_w = w
        v = QVBoxLayout(w); v.setContentsMargins(10, 0, 10, 12); v.setSpacing(4)
        self.rail_logo = QLabel("◆  PromptMaker"); self.rail_logo.setObjectName("railLogo"); v.addWidget(self.rail_logo)
        # The page list stays the single source of truth for navigation (go(), tests, shortcuts); the rail and
        # page tabs drive it. It is kept hidden.
        self.nav = QListWidget(); self.nav.setObjectName("sidebar")
        for icon, name in NAV:
            self.nav.addItem(QListWidgetItem(f"{icon}   {tr(name)}"))
        self.nav.hide(); v.addWidget(self.nav)
        self.rail_btns = {}
        for icon, sec, pages in SECTIONS:
            b = QPushButton(); b.setObjectName("railBtn"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=sec: self.open_section(s))
            b.setProperty("icon_txt", icon); b.setProperty("label_txt", tr(sec))
            self.rail_btns[sec] = b; v.addWidget(b)
        v.addStretch(1)
        self.collapse_btn = QPushButton("«"); self.collapse_btn.setObjectName("railBtn"); self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(lambda: self.set_sidebar_collapsed(not self.store.get("sidebar_collapsed")))
        v.addWidget(self.collapse_btn)
        self.rail_ver = label(f"v{__version__}", "hint"); self.rail_ver.setAlignment(Qt.AlignCenter); v.addWidget(self.rail_ver)
        self._rail_texts(False)
        return w

    def _rail_texts(self, collapsed):
        for sec, b in self.rail_btns.items():
            ic, lb = b.property("icon_txt"), b.property("label_txt")
            b.setText(ic if collapsed else f"{ic}    {lb}"); b.setToolTip(lb if collapsed else "")
            b.setStyleSheet("text-align: center;" if collapsed else "")
        self.rail_logo.setText("◆" if collapsed else "◆  PromptMaker")
        self.rail_logo.setAlignment(Qt.AlignCenter if collapsed else Qt.AlignLeft | Qt.AlignVCenter)
        self.collapse_btn.setText("»" if collapsed else "«   " + tr("Collapse"))
        self.collapse_btn.setToolTip(tr("Expand sidebar") if collapsed else tr("Collapse sidebar to icons"))

    def set_sidebar_collapsed(self, on):
        from .app import NAV
        self.store.set("sidebar_collapsed", bool(on))
        self.sidebar_w.setFixedWidth(RAIL_W_COLLAPSED if on else RAIL_W)
        for i, (_icon, name) in enumerate(NAV):
            self.nav.item(i).setToolTip(tr(name) if on else "")
        self._rail_texts(bool(on))

    def _top_bar(self):
        w = QWidget(); w.setObjectName("topBar"); w.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(w); h.setContentsMargins(18, 10, 14, 10); h.setSpacing(10)
        self.search_btn = QPushButton("⌕   " + tr("Search pages and actions, or type an idea…") + "        Ctrl+K")
        self.search_btn.setObjectName("search"); self.search_btn.setCursor(Qt.IBeamCursor); self.search_btn.setMinimumWidth(260)
        self.search_btn.setStyleSheet("text-align: left;")
        self.search_btn.clicked.connect(self.open_quickbar)
        h.addWidget(self.search_btn, 2)
        h.addStretch(1)
        f = QHBoxLayout(); f.setSpacing(4)
        self._status_widgets(f)
        h.addLayout(f)
        h.addWidget(_vsep())
        self.profile_combo = QComboBox(); self.profile_combo.setToolTip(tr("Target model"))
        for pid, p in self.profiles.items():
            self.profile_combo.addItem(p["name"], pid)
        idx = self.profile_combo.findData(self.store.get("profile", "generic"))
        self.profile_combo.setCurrentIndex(max(0, idx)); self.profile_combo.setMinimumWidth(170); self.profile_combo.setMaximumWidth(240)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        h.addWidget(label("Target", "hint")); h.addWidget(self.profile_combo)
        self.prov_label = label("", "hint"); h.addWidget(self.prov_label)
        self.model = QComboBox(); self.model.setPlaceholderText("no models"); self.model.setMinimumWidth(130); self.model.setMaximumWidth(200)
        self.model.currentTextChanged.connect(lambda m: m and self.store.set(f"model:{self.provider.pid}", m))
        h.addWidget(self.model)
        self.ai_dot = label("○ checking…", "hint"); h.addWidget(self.ai_dot)
        h.addWidget(button("⟳", self.refresh_models, "ghost", "Refresh Ollama models"))
        self.update_btn = button("", None, "ghost"); self.update_btn.setVisible(False); h.addWidget(self.update_btn)
        h.addWidget(_vsep())
        self.insp_btn = button("◨", self.toggle_inspector, "ghost", "Show / hide the generation inspector (Studio)")
        h.addWidget(self.insp_btn)
        h.addWidget(button("🧭", lambda: self.open_setup(), "ghost", "Setup wizard: check Ollama, download models, find Forge / ComfyUI"))
        self.theme_btn = button("☾", self.toggle_theme, "ghost", "Light / dark (Ctrl+T)"); h.addWidget(self.theme_btn)
        return w

    def _page_bar(self):
        w = QWidget(); w.setObjectName("pageBar"); self.page_bar = w
        self.page_bar_lay = QHBoxLayout(w); self.page_bar_lay.setContentsMargins(24, 12, 24, 0); self.page_bar_lay.setSpacing(4)
        self.section_title = QLabel(""); self.section_title.setObjectName("sectionTitle")
        self.page_bar_lay.addWidget(self.section_title)
        self.sub_tabs = {}
        self._tab_section = None
        self.page_bar_lay.addStretch(1)
        return w

    def _inspector(self):
        f = QFrame(); f.setObjectName("inspector"); f.setFixedWidth(380); self.inspector = f
        v = QVBoxLayout(f); v.setContentsMargins(14, 14, 8, 8); v.setSpacing(8)
        head = QHBoxLayout(); head.addWidget(label("Generation", "inspTitle")); head.addStretch(1)
        head.addWidget(button("✕", self.toggle_inspector, "ghost", "Hide inspector")); v.addLayout(head)
        v.addWidget(label("Image backend, checkpoint, size and sampler for Generate.", "hint", wrap=True))
        holder = QWidget(); self._insp_lay = QVBoxLayout(holder); self._insp_lay.setContentsMargins(0, 0, 6, 0); self._insp_lay.addStretch(1)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(holder); sc.setFrameShape(QScrollArea.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); v.addWidget(sc, 1)
        f.hide()
        return f

    # ------------------------------------------------------------------ behaviour
    def resizeEvent(self, e):
        super().resizeEvent(e)
        _resize_hook(self)

    def open_section(self, sec):
        last = self.store.get(f"section_page:{sec}")
        pages = next(p for _i, s, p in SECTIONS if s == sec)
        self.go(last if last in pages else pages[0])

    def _build_tabs(self, sec):
        if self._tab_section == sec:
            return
        self._tab_section = sec
        for b in self.sub_tabs.values():
            b.setParent(None); b.deleteLater()
        self.sub_tabs = {}
        pages = next(p for _i, s, p in SECTIONS if s == sec)
        if len(pages) > 1:
            for i, p in enumerate(pages):
                b = QPushButton(tr(p).replace("&", "&&")); b.setObjectName("subTab"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, n=p: self.go(n))
                self.page_bar_lay.insertWidget(1 + i, b); self.sub_tabs[p] = b

    def _chrome_sync(self, name):
        sec = section_of(name)
        self.store.set(f"section_page:{sec}", name)
        for s, b in self.rail_btns.items():
            b.setChecked(s == sec)
        self.section_title.setText(tr(sec))
        self._build_tabs(sec)
        self.page_bar.setVisible(bool(self.sub_tabs))
        # The page bar already names the section and page, so the page's own big title would repeat it.
        names = {name, tr(name)}
        for h1 in self.stack.currentWidget().findChildren(QLabel, "h1"):
            if h1.text() in names:
                h1.setVisible(not self.sub_tabs)
        for hd in self.stack.currentWidget().findChildren(QFrame, "pageHeader"):
            hd.setVisible(not self.sub_tabs or bool(hd.property("has_sub")))
        for p, b in self.sub_tabs.items():
            b.setChecked(p == name)
        studio = name in STUDIO_PAGES
        self.filmstrip.setVisible(studio)
        self.insp_btn.setVisible(studio)
        # Narrow windows (< INSPECTOR_MIN_W) keep the centre usable: the inspector only shows when asked for.
        wide = self.width() >= INSPECTOR_MIN_W
        show_insp = studio and (bool(self.store.get("inspector_open", True)) if wide else getattr(self, "_insp_force", False))
        card = getattr(self, "settings_img_card", None)
        if card is not None:
            if show_insp:
                self._insp_lay.insertWidget(0, card)
            elif name == "Settings" or card.parent() is None or not studio:
                self._img_home_lay.insertWidget(0, card)
            self._img_note.setVisible(card.parent() is not self._img_home)
        self.inspector.setVisible(show_insp)
        if studio:
            self.film_refresh()

    def toggle_inspector(self):
        if self.width() >= INSPECTOR_MIN_W:
            self.store.set("inspector_open", not self.store.get("inspector_open", True))
        else:
            self._insp_force = not getattr(self, "_insp_force", False)
        self._chrome_sync(self.page_name())

    def page_name(self):
        from .app import NAV
        return NAV[max(0, self.nav.currentRow())][1]

    def film_refresh(self):
        if not hasattr(self, "filmstrip"):
            return
        self.filmstrip.clear()
        for path, _m in self.gallery.items()[:24]:
            it = QListWidgetItem(QIcon(QPixmap(path).scaled(64, 64, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)), "")
            it.setData(Qt.UserRole, path); it.setToolTip(path); self.filmstrip.addItem(it)
        if not self.filmstrip.count():
            it = QListWidgetItem(tr("Your results will appear here – press Generate in Create or Builder"))
            it.setFlags(Qt.NoItemFlags); self.filmstrip.addItem(it)

    # ------------------------------------------------------------------ settings: two panes + appearance
    def _settings_two_pane(self, v, cards):
        """Turn the settings cards into a category list (left) and one page per category (right)."""
        body = QHBoxLayout(); body.setSpacing(18)
        self.settings_nav = QListWidget(); self.settings_nav.setObjectName("settingsNav"); self.settings_nav.setFixedWidth(210)
        self.settings_stack = QStackedWidget()
        for title, card in cards:
            self.settings_nav.addItem(tr(title))
            pg = QWidget(); lay = QVBoxLayout(pg); lay.setContentsMargins(0, 0, 8, 0); lay.setSpacing(14)
            lay.addWidget(card)
            if card is getattr(self, "settings_img_card", None):
                self._img_home, self._img_home_lay = pg, lay
                self._img_note = QWidget(); nl = QVBoxLayout(self._img_note); nl.setContentsMargins(0, 0, 0, 0)
                nl.addWidget(label("These settings are open in the Studio inspector right now; they come back here when you open Settings.", "hint", wrap=True))
                lay.addWidget(self._img_note); self._img_note.hide()
            lay.addStretch(1)
            sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(pg); sc.setFrameShape(QScrollArea.NoFrame)
            self.settings_stack.addWidget(sc)
        self.settings_nav.currentRowChanged.connect(self.settings_stack.setCurrentIndex)
        self.settings_nav.setCurrentRow(0)
        body.addWidget(self.settings_nav); body.addWidget(self.settings_stack, 1)
        v.addLayout(body, 1)

    def _appearance_card(self, card, accent_combo, extra):
        self.theme_pick = QComboBox()
        for k, n in theme.THEMES.items():
            self.theme_pick.addItem(tr(n), k)
        self.theme_pick.currentIndexChanged.connect(lambda _i: self.apply_theme(self.theme_pick.currentData()))
        from .widgets import hrow
        card.add(hrow(label("Theme"), self.theme_pick, label("Accent colour"), accent_combo, None))
        card.add(label("Graphite is the default look; Pastel and Pastel dusk are the cute pastel themes. Ctrl+T switches light ⇄ dark.", "hint", wrap=True))
        for w in extra:
            card.add(w)
        return card

    def _sync_theme_widgets(self, name):
        if hasattr(self, "theme_pick"):
            self.theme_pick.blockSignals(True)
            self.theme_pick.setCurrentIndex(max(0, self.theme_pick.findData(name))); self.theme_pick.blockSignals(False)
        if hasattr(self, "accent"):
            names = theme.PASTEL_ACCENT_NAMES if theme.is_pastel(name) else theme.ACCENT_NAMES
            for i in range(self.accent.count()):
                k = self.accent.itemData(i); self.accent.setItemText(i, tr(names.get(k, k.capitalize())))
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText("☀" if name in theme.DARK_THEMES else "☾")

    # ------------------------------------------------------------------ command palette (Ctrl+K)
    def palette_entries(self):
        from .app import NAV
        e = [(f"{ic}  {tr('Go to')} {tr(n)}", (lambda n=n: self.go(n))) for ic, n in NAV]
        e += [("☾  " + tr("Toggle light / dark theme"), self.toggle_theme), ("☰  " + tr("Open image queue"), self.open_queue),
              ("🧭  " + tr("Run setup wizard"), lambda: self.open_setup()), ("◨  " + tr("Show / hide inspector"), self.toggle_inspector)]
        e += [(f"🎨  {tr('Theme')}: {tr(n)}", (lambda k=k: self.apply_theme(k))) for k, n in theme.THEMES.items()]
        return e

    def palette_filter(self, text):
        q = text.strip().lower()
        self.qbar_list.clear()
        hits = [(t, fn) for t, fn in self.palette_entries() if len(q) >= 2 and q in t.lower()][:8]
        for t, fn in hits:
            it = QListWidgetItem(t); it.setData(Qt.UserRole, len(self._qbar_fns)); self._qbar_fns.append(fn); self.qbar_list.addItem(it)
        if hits:
            self.qbar_list.setCurrentRow(0)
        idea = QListWidgetItem("✨  " + (tr("Write a prompt for") + f" “{text.strip()}”" if q else tr("Type an idea to write a prompt, or a page name to jump")))
        idea.setData(Qt.UserRole, -1); self.qbar_list.addItem(idea)
        self.qbar_list.setFixedHeight(min(9, self.qbar_list.count()) * 34 + 10)
        self.qbar.adjustSize()


def _vsep():
    s = QFrame(); s.setObjectName("vsep"); s.setFixedSize(1, 22)
    return s


def _resize_hook(win):
    """Re-evaluate the inspector when the window crosses INSPECTOR_MIN_W."""
    wide = win.width() >= INSPECTOR_MIN_W
    if getattr(win, "_was_wide", None) != wide and hasattr(win, "inspector"):
        win._was_wide = wide
        win._chrome_sync(win.page_name())
