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
