"""Checkpoint picker: hash stripping, visible arrow in the stylesheet, shared setting across pages, lazy loading."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LONG = "xxxXL_ilV190.safetensors [fa486caafc]"


def test_strip_hash():
    from promptmaker.widgets import strip_ckpt_hash
    assert strip_ckpt_hash(LONG) == "xxxXL_ilV190.safetensors"
    assert strip_ckpt_hash("anima [v2].safetensors") == "anima [v2].safetensors"
    assert strip_ckpt_hash("") == "" and strip_ckpt_hash(None) == ""


def test_stylesheet_has_arrow_image():
    pytest.importorskip("PySide6")
    from promptmaker import theme
    for name in ("dark", "light"):
        qss = theme.stylesheet(name)
        assert "QComboBox::down-arrow" in qss and "image: url(" in qss
        path = qss.split('QComboBox::down-arrow {{ image: url("'.replace("{{", "{"))[1].split('"')[0]
        assert os.path.exists(path)


@pytest.fixture
def win(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    for k in ("PROMPTMAKER_NO_NET", "PROMPTMAKER_NO_TOUR", "PROMPTMAKER_NO_SETUP"):
        monkeypatch.setenv(k, "1")
    from PySide6.QtWidgets import QApplication
    from promptmaker.app import MainWindow
    from promptmaker.storage import Store
    app = QApplication.instance() or QApplication([])
    st = Store(str(tmp_path / "t.db")); st.set("img_backend", "a1111"); st.set("img_checkpoint:a1111", LONG)
    w = MainWindow(st, str(tmp_path)); w.resize(1440, 900); w.show(); app.processEvents()
    yield w, st, app
    w.close()


def test_pickers_share_setting(win):
    w, st, app = win
    assert {w.img_ckpt, w.pose_ckpt, w.ar_ckpt} <= set(w._ckpt_combos)
    assert w.pose_ckpt.name() == "xxxXL_ilV190.safetensors" and w.img_ckpt.toolTip().startswith("xxxXL")
    w.pose_ckpt.setCurrentText("anima-preview3.safetensors"); app.processEvents()
    assert st.get("img_checkpoint:a1111") == "anima-preview3.safetensors"
    assert w.img_ckpt.name() == w.ar_ckpt.name() == "anima-preview3.safetensors"
    w.img_ckpt.setCurrentText("other.safetensors"); app.processEvents()
    assert w.pose_ckpt.name() == "other.safetensors"


def test_combo_is_wide_and_shows_start(win):
    w, st, app = win
    w.go("Settings"); app.processEvents()
    assert w.img_ckpt.width() >= 360 and w.img_ckpt.isEditable()
    assert w.img_ckpt.lineEdit().cursorPosition() == 0


def test_lazy_load_on_open(win, monkeypatch):
    w, st, app = win
    calls = []
    monkeypatch.setattr(w.pose_ckpt, "loader", lambda: (calls.append(1), [c.set_items(["a.safetensors [0123456789]", "b"]) for c in w._ckpt_combos]))
    w.pose_ckpt.showPopup(); app.processEvents(); w.pose_ckpt.hidePopup()
    assert calls == [1] and w.pose_ckpt.count() == 2 and w.pose_ckpt.itemText(0) == "a.safetensors"
    assert w.img_ckpt.count() == 2
    w.pose_ckpt.showPopup(); app.processEvents(); w.pose_ckpt.hidePopup()
    assert calls == [1]  # not reloaded once filled
