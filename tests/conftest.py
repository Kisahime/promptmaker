import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _qt_teardown():
    """Shut Qt down cleanly at the end of the session. Letting QApplication be garbage-collected during
    interpreter exit can crash on Windows (0xC0000409) even though every test passed."""
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.close(); w.deleteLater()
    app.processEvents()
    if hasattr(app, "shutdown"):
        app.shutdown()
    os.environ.setdefault("PROMPTMAKER_TESTS_DONE", "1")


@pytest.fixture(autouse=True)
def _delete_windows():
    """Destroy every top-level window after each test. Closed-but-alive MainWindows piled up and each
    app-wide setStyleSheet() restyled all of them, so window setup got slower test after test (4.1: ~9.6 → ~3 min)."""
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        for t in ("status_timer", "preview_timer"):
            if hasattr(w, t):
                getattr(w, t).stop()
        genq = getattr(w, "genq", None)
        if genq is not None:
            genq.clear(); genq.wait(3000)
        for wk in getattr(w, "_workers", []) or []:
            try:
                wk.wait(3000)
            except RuntimeError:
                pass
        w.close(); w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def pytest_unconfigure(config):
    """After pytest has reported results, exit without running interpreter teardown. PySide6 on CPython 3.10
    (Linux CI) can abort with "munmap_chunk(): invalid pointer" while freeing Qt objects at exit even though
    every test passed. Only affects the test process."""
    import sys
    sys.stdout.flush(); sys.stderr.flush()
    session = getattr(config, "_pm_session", None)
    status = getattr(session, "exitstatus", 0) if session is not None else 0
    os._exit(int(status))


def pytest_sessionfinish(session, exitstatus):
    session.config._pm_session = session
