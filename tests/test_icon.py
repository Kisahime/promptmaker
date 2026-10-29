import os
A = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "promptmaker", "assets")


def test_icon_files_exist_and_load():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QIcon
    QApplication.instance() or QApplication([])
    for f in ("icon.svg", "icon.ico", "icon_256.png"):
        assert os.path.exists(os.path.join(A, f)), f
    img = QImage(os.path.join(A, "icon_256.png"))
    assert not img.isNull() and img.width() == 256
    with open(os.path.join(A, "icon.ico"), "rb") as fh:
        head = fh.read(6)
    assert head[:4] == b"\x00\x00\x01\x00" and int.from_bytes(head[4:6], "little") >= 7
    assert not QIcon(os.path.join(A, "icon.svg")).isNull()
    from promptmaker.app import app_icon
    assert not app_icon().isNull()
