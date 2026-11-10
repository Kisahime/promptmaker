import numpy as np
import pytest
cv2 = pytest.importorskip("cv2")
from promptmaker import faceswap as fs


def _png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def test_clean_face_crops_tight_and_drops_flat_background(monkeypatch):
    img = np.full((200, 200, 3), (255, 0, 0), np.uint8)  # synthetic blue "background"
    img[60:140, 70:130] = (0, 200, 0)                     # synthetic green "head"
    m = np.zeros((200, 200), np.uint8); m[60:140, 70:130] = 255
    monkeypatch.setattr(fs, "seg_mask", lambda *a, **k: (_png(m), "face parsing"))
    out, method = fs.clean_face(_png(img), (70, 60, 60, 80), "Photo", size=128)
    o = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert method == "face parsing" and o.shape[:2] == (128, 128)
    assert all(tuple(int(v) for v in o[y, x]) == (255, 255, 255) for y, x in ((1, 1), (1, 126), (126, 1), (126, 126)))  # white, no scenery
    assert tuple(int(v) for v in o[64, 64]) == (0, 200, 0)
    assert int((o[:, :, 1] > 150).mean() * 100) > 50   # the head fills most of the square


def test_clean_face_falls_back(monkeypatch):
    png = _png(np.zeros((8, 8, 3), np.uint8))
    monkeypatch.setattr(fs, "seg_mask", lambda *a, **k: (None, "onnxruntime not installed"))
    assert fs.clean_face(png, (1, 1, 4, 4), "Photo") == (None, "onnxruntime not installed")
    assert fs.clean_face(png, None) == (None, "no face")

def test_clean_face_fill_colours(monkeypatch):
    img = np.full((100, 100, 3), (255, 0, 0), np.uint8); img[30:70, 40:60] = (0, 200, 0)
    m = np.zeros((100, 100), np.uint8); m[30:70, 40:60] = 255
    monkeypatch.setattr(fs, "seg_mask", lambda *a, **k: (_png(m), "face parsing"))
    for name, bgr in fs.BG_FILLS.items():
        o = cv2.imdecode(np.frombuffer(fs.clean_face(_png(img), (40, 30, 20, 40), "Photo", size=64, fill=name)[0], np.uint8), 1)
        assert tuple(int(v) for v in o[1, 1]) == bgr