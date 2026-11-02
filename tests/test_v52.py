"""Tests for 5.2: Wallpaper mode (base size + hires maths, composition text, exact-size output, page)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import imagegen, wallpaper as wp  # noqa: E402
import test_v5  # noqa: E402

_app, _wait = test_v5._app, test_v5._wait
win, srv = test_v5.win, test_v5.srv
SD, ANIMA, FLUX = "Stable Diffusion", "Anima", "FLUX"


@pytest.mark.parametrize("fam", [SD, ANIMA, FLUX])
@pytest.mark.parametrize("tw,th,base,hires,up", [
    (1920, 1080, (1280, 720), 1.5, 1.0),
    (2560, 1440, (1280, 720), 2.0, 1.0),
    (3840, 2160, (1280, 720), 1.5, 2.0),
    (1080, 1920, (720, 1280), 1.5, 1.0),
])
def test_exact_16_9_plans(fam, tw, th, base, hires, up):
    p = wp.plan(tw, th, fam)
    assert p["base"] == base and p["hires"] == hires and p["upscale"] == up
    assert p["before_crop"] == (tw, th) and p["crop"] == (0, 0)


@pytest.mark.parametrize("fam", [SD, ANIMA, FLUX, "Qwen", "MOSS", "HiDream", "Generic"])
@pytest.mark.parametrize("tw,th", [(tw, th) for _n, tw, th in wp.PRESETS] + [(1366, 768), (1280, 1024), (3000, 1000)])
def test_every_plan_is_sane(fam, tw, th):
    p = wp.plan(tw, th, fam)
    bw, bh = p["base"]; mult = wp.grid_for(fam)[0]
    assert bw % mult == 0 and bh % mult == 0
    assert 0.7 * wp.MP <= bw * bh <= 1.15 * wp.MP          # ~1 MP, 8 GB friendly
    assert 1.0 <= p["hires"] <= wp.MAX_HIRES                 # never more than ×2 in one hires pass
    ow, oh = p["before_crop"]
    assert ow >= tw and oh >= th                             # at or just over the target, then crop
    assert ow <= tw * 1.08 + 8 and oh <= th * 1.08 + 8
    assert abs(bw / bh - tw / th) / (tw / th) < 0.03


def test_ultrawide_and_custom():
    p = wp.plan(2560, 1080, SD)
    assert p["upscale"] == 1.0 and p["hires"] <= 2.0 and abs(p["base"][0] / p["base"][1] - 2560 / 1080) < 0.01
    p = wp.plan(3440, 1440, SD)
    assert p["hires"] == wp.SAFE_HIRES and p["upscale"] > 1
    assert wp.plan(1024, 1024, SD)["base"] == (1024, 1024) and wp.plan(1024, 1024, SD)["hires"] == 1.0
    assert "1280×720 → hires ×1.5 = 1920×1080 → 1920×1080" == wp.describe(wp.plan(1920, 1080, SD))
    with pytest.raises(ValueError):
        wp.plan(1920, 1080, "Midjourney")
    with pytest.raises(ValueError):
        wp.base_size(0, 100)


def test_hires_output_matches_backend_rounding():
    for _n, tw, th in wp.PRESETS:
        p = wp.plan(tw, th, SD)
        if p["hires"] > 1:
            assert imagegen.scaled_size(*p["base"], p["hires"]) == p["after_hires"]


def test_composition_by_prompt_style():
    t = wp.add_composition("1girl, autumn forest", "right", "tags")
    assert t.startswith("1girl, autumn forest, wide shot") and "character on right side" in t and "empty left side" in t
    n = wp.add_composition("A woman walks through an autumn forest.", "left", "natural")
    assert n.endswith("leaving the right side open and uncluttered with sky and scenery.") and "wide shot," not in n
    h = wp.add_composition("1girl, autumn forest. She walks slowly.", "right", "hybrid")
    assert h.startswith("1girl, autumn forest, wide shot") and "She walks slowly." in h and h.endswith("scenery.")
    assert wp.add_composition("x", "", "tags") == "x"
    assert wp.add_composition(t, "right", "tags") == t  # not added twice
    assert "centered" in wp.composition("center", "tags")


def _png(w, h):
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    from promptmaker.regions import _png as enc
    QApplication.instance() or QApplication([])
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor("#c86432"))
    return enc(im)


@pytest.mark.parametrize("src,dst", [((2016, 1152), (1920, 1080)), ((1000, 600), (1920, 1080)), ((1112, 1952), (1080, 1920))])
def test_fit_png_exact_size(src, dst):
    out = wp.fit_png(_png(*src), *dst)
    assert imagegen.png_size(out) == dst


def test_save_and_desktop_guard(tmp_path, monkeypatch):
    path = wp.save(_png(64, 36), str(tmp_path), 64, 36, 5)
    assert os.path.dirname(path) == os.path.join(str(tmp_path), "Wallpapers") and os.path.exists(path)
    monkeypatch.setattr(wp.sys, "platform", "linux")
    assert not wp.can_set_desktop()
    with pytest.raises(OSError):
        wp.set_desktop(path)


def test_wallpaper_page_generates_exact_size(win, srv, tmp_path):
    s, url = srv()
    win.store.set("img_backend", "a1111"); win.store.set("img_url:a1111", url)
    win.profile_combo.setCurrentIndex(win.profile_combo.findData("illustrious")); _app().processEvents()
    from promptmaker.app import NAV
    assert "Wallpaper" in [n for _i, n in NAV]
    win.go("Wallpaper"); _app().processEvents(); assert win.page_name() == "Wallpaper"
    win.wp_preset.setCurrentIndex(0)
    assert "1280×720 → hires ×1.5" in win.wp_plan_view.text()
    assert win.wp_generate() is None and "⚠️" in win.wp_status.text()  # no prompt yet
    win.wp_prompt.setPlainText("1girl, adult woman, autumn forest path")
    win.wp_side.setCurrentIndex(win.wp_side.findData("right"))
    assert win.wp_generate() is not None
    assert _wait(lambda: win.wp_png is not None, 10)
    p = s.last_payload
    assert (p["width"], p["height"]) == (1280, 720) and p["enable_hr"] and p["hr_scale"] == 1.5
    assert "character on right side" in p["prompt"]
    assert imagegen.png_size(win.wp_png) == (1920, 1080)
    assert win.wp_path and win.wp_path.startswith(os.path.join(str(tmp_path), "Wallpapers"))
    win.wp_preset.setCurrentIndex(win.wp_preset.count() - 1)  # Custom
    win.wp_w.setValue(2560); win.wp_h.setValue(1080)
    assert "→ 2560×1080" in win.wp_plan_view.text()
    assert win.wp_set_btn.isVisible() == wp.can_set_desktop()
