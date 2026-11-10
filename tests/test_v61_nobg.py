import numpy as np
import pytest
cv2 = pytest.importorskip("cv2")
from promptmaker import faceswap as fs


def _png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def test_clean_background_greys_outside_mask(monkeypatch):
    img = np.full((64, 64, 3), (0, 200, 0), np.uint8)  # synthetic green image
    m = np.zeros((64, 64), np.uint8); m[16:48, 16:48] = 255
    monkeypatch.setattr(fs, "seg_mask", lambda *a, **k: (_png(m), "face parsing"))
    out, method = fs.clean_background(_png(img), (20, 20, 24, 24), "Photo")
    o = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert method == "face parsing"
    assert tuple(int(v) for v in o[2, 2]) == fs.BG_GREY
    assert tuple(int(v) for v in o[32, 32]) == (0, 200, 0)


def test_clean_background_falls_back(monkeypatch):
    png = _png(np.zeros((8, 8, 3), np.uint8))
    monkeypatch.setattr(fs, "seg_mask", lambda *a, **k: (None, "onnxruntime not installed"))
    assert fs.clean_background(png, (1, 1, 4, 4), "Photo") == (png, "onnxruntime not installed")
    assert fs.clean_background(png, None) == (png, "no face")