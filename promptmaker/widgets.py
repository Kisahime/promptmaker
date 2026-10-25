"""Reusable widgets: flow layout, chips, cards, toasts, workers."""
from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QThread, QTimer, Signal)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget, QProgressBar)

from . import ollama


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s + QSize(2, 2)

    def clear(self):
        while self._items:
            it = self._items.pop()
            if it.widget():
                it.widget().deleteLater()

    def _do(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self._items:
            w = it.sizeHint()
            if x + w.width() > rect.right() and line > 0:
                x, y, line = rect.x(), y + line + sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), w))
            x += w.width() + sp
            line = max(line, w.height())
        return y + line - rect.y()


def button(text, slot=None, kind=None, tip=None):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if kind:
        b.setObjectName(kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def chip(text, checked=False, slot=None):
    b = QPushButton(text)
    b.setObjectName("chip")
    b.setCheckable(True)
    b.setChecked(checked)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.toggled.connect(slot)
    return b


def label(text, kind=None, wrap=False):
    l = QLabel(text)
    if kind:
        l.setObjectName(kind)
    l.setWordWrap(wrap)
    return l


class Card(QFrame):
    def __init__(self, title=None, parent=None, spacing=10):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 16)
        self.lay.setSpacing(spacing)
        if title:
            self.lay.addWidget(label(title, "h2"))

    def add(self, w, stretch=0):
        if isinstance(w, QLayout):
            self.lay.addLayout(w, stretch)
        else:
            self.lay.addWidget(w, stretch)
        return w


def hrow(*widgets, stretch_end=False, spacing=8):
    h = QHBoxLayout()
    h.setSpacing(spacing)
    for w in widgets:
        if w is None:
            h.addStretch()
        elif isinstance(w, QLayout):
            h.addLayout(w)
        else:
            h.addWidget(w)
    if stretch_end:
        h.addStretch()
    return h


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.hide()
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer(self, singleShot=True, timeout=self._fade_out)

    def show_message(self, text, error=False, ms=2600):
        self.setObjectName("toastError" if error else "toast")
        self.style().unpolish(self); self.style().polish(self)
        self.setText(("⚠️  " if error else "✓  ") + text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(p.width() - self.width() - 24, p.height() - self.height() - 24)
        self.raise_(); self.show()
        self.anim.stop(); self.anim.setDuration(180)
        self.anim.setStartValue(0.0); self.anim.setEndValue(1.0); self.anim.start()
        self.timer.start(ms + (2500 if error else 0))

    def _fade_out(self):
        self.anim.stop(); self.anim.setDuration(400)
        self.anim.setStartValue(1.0); self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._hide_once)
        self.anim.start()

    def _hide_once(self):
        try:
            self.anim.finished.disconnect(self._hide_once)
        except (RuntimeError, TypeError):
            pass
        if self.effect.opacity() < 0.05:
            self.hide()


class ScoreBar(QWidget):
    """Label + progress bar + note for a rubric criterion."""
    def __init__(self, name):
        super().__init__()
        v = QVBoxLayout(self); v.setContentsMargins(0, 2, 0, 2); v.setSpacing(3)
        self.title = label(name); self.val = label("–", "muted")
        v.addLayout(hrow(self.title, None, self.val))
        self.bar = QProgressBar(); self.bar.setRange(0, 10); self.bar.setTextVisible(False); self.bar.setFixedHeight(8)
        v.addWidget(self.bar)
        self.note = label("", "hint", wrap=True)
        v.addWidget(self.note)

    def set(self, score, note=""):
        self.bar.setValue(int(score)); self.val.setText(f"{int(score)}/10"); self.note.setText(note)


class ChatWorker(QThread):
    chunk = Signal(str)
    failed = Signal(str)
    done = Signal(str)

    def __init__(self, model, messages, temperature=0.7, json_mode=False):
        super().__init__()
        self.model, self.messages, self.temperature, self.json_mode = model, messages, temperature, json_mode
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        buf = []
        try:
            for c in ollama.stream_chat(self.model, self.messages, temperature=self.temperature,
                                        json_mode=self.json_mode, stop_flag=lambda: self._stop):
                buf.append(c); self.chunk.emit(c)
            self.done.emit("".join(buf))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def expanding(w):
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return w
