"""Reusable widgets: flow layout, chips, cards, toasts, workers."""
from .i18n import tr
from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QThread, QTimer, Signal)
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget, QProgressBar)



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
    b = QPushButton(tr(text))
    b.setCursor(Qt.PointingHandCursor)
    if kind:
        b.setObjectName(kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tr(tip))
    return b


class ConfirmButton(QPushButton):
    """Destructive button with in-place confirmation: first click arms it ("Confirm clear (4s)", danger style,
    live countdown), a second click within the window runs the action, otherwise it reverts by itself."""

    def __init__(self, text, action, confirm_text="Confirm", secs=4, kind="ghost", tip=None):
        super().__init__(tr(text))
        self._label, self._confirm, self._secs, self._kind, self._action = tr(text), tr(confirm_text), secs, kind, action
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName(kind)
        if tip:
            self.setToolTip(tr(tip))
        self.left = 0
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.clicked.connect(self._clicked)

    @property
    def armed(self):
        return self.left > 0

    def _restyle(self, name):
        self.setObjectName(name); self.style().unpolish(self); self.style().polish(self)

    def _clicked(self):
        if self.armed:
            self.reset(); self._action()
        else:
            self.left = self._secs; self._restyle("dangerArmed"); self._show(); self.timer.start()

    def _show(self):
        self.setText(f"{self._confirm} ({self.left}s)")

    def _tick(self):
        self.left -= 1
        if self.left <= 0:
            self.reset()
        else:
            self._show()

    def reset(self):
        self.timer.stop(); self.left = 0; self.setText(self._label); self._restyle(self._kind)


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
    l = QLabel(tr(text))
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
        # Toasts are purely informational: never intercept clicks on whatever is underneath.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
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
        # Top-right, clear of the bottom action rows where most buttons live.
        self.move(p.width() - self.width() - 24, 16)
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

    def __init__(self, provider, model, messages, temperature=0.7, json_mode=False):
        super().__init__()
        self.provider, self.model, self.messages = provider, model, messages
        self.temperature, self.json_mode = temperature, json_mode
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        buf = []
        try:
            for c in self.provider.stream_chat(self.model, self.messages, temperature=self.temperature,
                                               json_mode=self.json_mode, stop_flag=lambda: self._stop):
                buf.append(c); self.chunk.emit(c)
            self.done.emit("".join(buf))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class CallWorker(QThread):
    """Run any blocking callable off the UI thread."""
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.ok.emit(self.fn(*self.args))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class GenQueue(QThread):
    """Processes image-generation jobs one at a time."""
    progress = Signal(str, int, str)        # job id, percent (-1 = busy), message
    finished_job = Signal(object, list)     # job, [png bytes]
    failed_job = Signal(object, str)
    idle = Signal()

    def __init__(self):
        super().__init__()
        self.jobs = []
        self.backend = None
        self.workflow = None
        self._cancel_current = False
        self.current = None

    def add(self, job, backend, workflow):
        self.jobs.append((job, backend, workflow))
        if not self.isRunning():
            self.start()

    def cancel_current(self):
        self._cancel_current = True

    def clear(self):
        self.jobs.clear()

    # 4.1 queue view
    def pending(self):
        return [j for j, _b, _w in list(self.jobs)]

    def move(self, job_id, delta):
        """Move a pending job up (-1) or down (+1). Returns its new index or -1."""
        ids = [j.id for j, _b, _w in self.jobs]
        if job_id not in ids:
            return -1
        i = ids.index(job_id); n = max(0, min(len(ids) - 1, i + delta))
        item = self.jobs.pop(i); self.jobs.insert(n, item)
        return n

    def remove(self, job_id):
        """Cancel one job: drop it if pending, stop it if running."""
        if self.current is not None and self.current.id == job_id:
            self.cancel_current(); return True
        for i, (j, _b, _w) in enumerate(list(self.jobs)):
            if j.id == job_id:
                del self.jobs[i]; return True
        return False

    def cancel_all(self):
        self.jobs.clear(); self.cancel_current()

    def run(self):
        from .imagegen import Cancelled
        while self.jobs:
            try:
                job, backend, wf = self.jobs.pop(0)
            except IndexError:
                break
            self.current, self._cancel_current = job, False
            self.progress.emit(job.id, -1, "Starting…")
            try:
                imgs = backend.generate(job, wf, progress=lambda pct, msg, j=job: self.progress.emit(j.id, pct, msg),
                                        cancelled=lambda: self._cancel_current)
                self.finished_job.emit(job, imgs)
            except Cancelled:
                self.failed_job.emit(job, "Cancelled")
            except Exception as e:  # noqa: BLE001
                self.failed_job.emit(job, str(e))
        self.current = None
        self.idle.emit()


def expanding(w):
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return w


class DropLabel(QLabel):
    """A label that accepts dropped image files or image data."""
    from PySide6.QtCore import Signal as _S
    dropped = _S(object)

    def __init__(self, text):
        super().__init__(text)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(260)
        self.setObjectName("dropZone")

    def dragEnterEvent(self, e):
        if e.mimeData().hasImage() or e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        from PySide6.QtGui import QImage
        md = e.mimeData()
        if md.hasImage():
            self.dropped.emit(QImage(md.imageData()))
        elif md.hasUrls():
            self.dropped.emit(QImage(md.urls()[0].toLocalFile()))


def strip_ckpt_hash(name):
    """'model.safetensors [fa486caafc]' -> 'model.safetensors' (Forge accepts the plain name)."""
    import re
    return re.sub(r"\s*\[[0-9a-fA-F]{6,}\]\s*$", "", (name or "").strip())


class CheckpointCombo(QComboBox):
    """Editable, wide checkpoint picker. Shows the start of long names, the full name as tooltip, and
    asks for the list (``loader``) the first time it is opened while empty."""
    def __init__(self, loader=None, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.setEditable(True); self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(360); self.setMinimumContentsLength(34)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lineEdit().setPlaceholderText(tr("Backend default (whatever is loaded)"))
        self.view().setMinimumWidth(460); self.view().setTextElideMode(Qt.ElideMiddle)
        self.currentTextChanged.connect(self._tip)
        self.lineEdit().installEventFilter(self)

    def _tip(self, t):
        self.setToolTip(t or "")
        le = self.lineEdit()
        if le and not le.hasFocus():
            le.setCursorPosition(0)

    def set_name(self, name):
        name = strip_ckpt_hash(name)
        self.blockSignals(True); self.setCurrentText(name); self.blockSignals(False)
        self._tip(name)

    def name(self):
        return strip_ckpt_hash(self.currentText())

    def set_items(self, names):
        cur = self.name()
        seen, clean = set(), []
        for n in names or []:
            n = strip_ckpt_hash(n)
            if n and n not in seen:
                seen.add(n); clean.append(n)
        self.blockSignals(True); self.clear(); self.addItems(clean)
        for i, n in enumerate(clean):
            self.setItemData(i, n, Qt.ToolTipRole)
        self.setCurrentText(cur); self.blockSignals(False); self._tip(cur)

    def _maybe_load(self):
        if self.count() == 0 and self.loader:
            self.loader()

    def showPopup(self):
        self._maybe_load()
        super().showPopup()

    def mousePressEvent(self, e):
        self._maybe_load(); super().mousePressEvent(e)

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.lineEdit():
            if e.type() == QEvent.FocusOut:
                obj.setCursorPosition(0)
            elif e.type() == QEvent.MouseButtonPress:
                self._maybe_load()
        return super().eventFilter(obj, e)
