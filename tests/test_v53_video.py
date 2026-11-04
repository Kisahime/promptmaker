"""5.3 Video maker: scene plan parsing + song timing, project resume / redo, Wan2GP runner (fake wgp.py),
VRAM unload/reload, Forge payload extras, ffmpeg Ken Burns / crossfade / caption / audio build on synthetic
images, and the page. No real AI calls; all prompts are SFW with adult characters."""
import json
import os
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promptmaker import imagegen, wan2gp  # noqa: E402
from promptmaker import videoproject as vp  # noqa: E402
import test_v5  # noqa: E402

_app, _wait = test_v5._app, test_v5._wait
win = test_v5.win
FF = vp.find_ffmpeg()
needs_ff = pytest.mark.skipif(not FF, reason="ffmpeg not installed")

PLAN = json.dumps({"title": "Seaside Morning", "scenes": [
    {"prompt": "two adult women cycling along a seaside road at sunrise, wide shot", "duration": 3, "camera": "pan right",
     "motion": "they pedal forward, hair moving in the wind", "caption": "Morning", "animate": True},
    {"prompt": "adult woman laughing at a cafe table, warm light, medium shot", "duration": 20, "camera": "Bogus"},
    {"prompt": "", "duration": 2},
    {"prompt": "two adult friends eating ice cream on a pier, golden hour", "duration": "x", "camera": "Pull out"}]})


def _png(path, colour, w=640, h=360):
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    im = QImage(w, h, QImage.Format_RGB32); im.fill(QColor(colour))
    p = QPainter(im); p.fillRect(w // 4, h // 4, w // 2, h // 2, QColor("white")); p.end()
    im.save(str(path))
    with open(path, "rb") as f:
        return f.read()


# ------------------------------------------------------------------ plan / timing
def test_parse_plan_clamps_and_skips():
    title, sc = vp.parse_plan("```json\n" + PLAN + "\n```", vp.new_project())
    assert title == "Seaside Morning" and len(sc) == 3
    assert [s["id"] for s in sc] == ["s01", "s02", "s03"]
    assert sc[0]["camera"] == "Pan right" and sc[0]["animate"] and sc[0]["caption"] == "Morning"
    assert sc[1]["duration"] == vp.MAX_SECS and sc[1]["camera"] == "Slow push in"
    assert sc[2]["duration"] == 4.0 and sc[2]["camera"] == "Pull out"
    assert vp.parse_plan("not json", vp.new_project()) == ("", [])


def test_plan_fits_song_length():
    p = vp.new_project(); p["song_secs"] = 30.0
    _t, sc = vp.parse_plan(PLAN, p)
    assert abs(vp.total_secs({"scenes": sc}) - 30.0) < 1e-6


def test_lyrics_even_and_lrc():
    tl = vp.lyric_timeline("[Verse]\nline one\nline two\n\nline three", 9.0)
    assert [round(a, 2) for a, _b, _l in tl] == [0, 3, 6] and tl[-1][1] == 9.0
    lrc = vp.lyric_timeline("[00:00.50] hello\n[00:04.00] world\n[00:07.25] end", 10.0)
    assert lrc[0][:2] == (0.0, 4.0) and lrc[1][:2] == (4.0, 7.25) and lrc[2][:2] == (7.25, 10.0)


def test_plan_follows_lyrics():
    p = vp.new_project(); p.update(song_secs=12.0, lyrics="sun comes up\nwe ride\nby the sea\nice cream time")
    msgs = vp.plan_messages(p, 3, {"format": "tags"})
    assert "exactly one scene per lyric line" in msgs[1]["content"] and "adult" in msgs[0]["content"]
    _t, sc = vp.parse_plan(PLAN, p)
    assert len(sc) == 4 and [s["caption"] for s in sc] == ["sun comes up", "we ride", "by the sea", "ice cream time"]
    assert abs(vp.total_secs({"scenes": sc}) - 12.0) < 1e-6


# ------------------------------------------------------------------ project
def test_save_load_resume_and_redo(tmp_path):
    pdir = vp.project_dir(str(tmp_path), "My: Video?")
    assert os.path.basename(pdir) == "My_Video"
    p = vp.new_project("My: Video?"); p["scenes"] = vp.parse_plan(PLAN, p)[1]
    _png(os.path.join(pdir if os.makedirs(pdir, exist_ok=True) is None else pdir, "s01.png"), "red")
    p["scenes"][0]["still"] = "s01.png"; p["scenes"][1]["still"] = "gone.png"
    vp.save_project(p, pdir)
    q = vp.load_project(pdir)
    assert q["scenes"][0]["still"] == "s01.png" and q["scenes"][0]["status"] == "still"
    assert q["scenes"][1]["still"] == "" and q["scenes"][1]["status"] == "planned"  # missing file -> made again
    assert vp.list_projects(str(tmp_path))[0][0] == "My: Video?"
    vp.redo_scene(q["scenes"][0], pdir, "still")
    assert q["scenes"][0]["still"] == "" and not os.path.exists(os.path.join(pdir, "s01.png"))


# ------------------------------------------------------------------ Forge payload
def test_payload_restore_and_adetailer():
    j = imagegen.Job("adult woman reading in a park", checkpoint="x.safetensors")
    j.restore_settings = True; j.adetailer = "face_yolov8s.pt"
    a = imagegen.A1111("http://127.0.0.1:9"); a._modules = []
    p = a.payload(j)
    assert p["override_settings_restore_afterwards"] is True
    assert p["alwayson_scripts"]["ADetailer"]["args"][2]["ad_model"] == "face_yolov8s.pt"
    plain = a.payload(imagegen.Job("a lighthouse", checkpoint="x.safetensors"))
    assert "override_settings_restore_afterwards" not in plain and "alwayson_scripts" not in plain


def test_make_stills_saves_each(tmp_path):
    class B:
        def generate(self, job, progress=None, cancelled=None):
            return [_png(tmp_path / "g.png", "blue")]
    p = vp.new_project("t"); p["scenes"] = vp.parse_plan(PLAN, p)[1]
    jobs = [(s, imagegen.Job(s["prompt"], seed=7)) for s in p["scenes"]]
    assert vp.make_stills(p, str(tmp_path), jobs, B()) == 3
    assert all(os.path.exists(tmp_path / s["still"]) and s["seed"] == 7 for s in p["scenes"])
    assert json.load(open(tmp_path / "project.json"))["scenes"][2]["still"] == "s03.png"
    with pytest.raises(vp.Cancelled):
        vp.make_stills(p, str(tmp_path), jobs, B(), cancelled=lambda: True)


# ------------------------------------------------------------------ Wan2GP
def _fake_wan(tmp_path, body):
    d = tmp_path / "wan"; d.mkdir()
    (d / "wgp.py").write_text(body)
    return str(d)


FAKE_OK = """import json, sys, os
a = sys.argv; s = json.load(open(a[a.index('--process') + 1])); out = a[a.index('--output-dir') + 1]
assert s['model_type'] == 'ti2v_2_2_fastwan' and os.path.exists(s['image_start'])
open(os.path.join(out, 'clip_seed%d.mp4' % s['seed']), 'wb').write(b'MP4' + s['resolution'].encode())
"""


def test_wan_settings_and_run(tmp_path):
    img = tmp_path / "s.png"; _png(img, "green")
    cfg = wan2gp.settings("adult woman waves", str(img), seed=5)
    assert cfg["resolution"] == "1280x704" and cfg["video_length"] == 121 and cfg["num_inference_steps"] == 3
    assert cfg["image_start"] == str(img) and cfg["prompt"] == "adult woman waves"
    d = _fake_wan(tmp_path, FAKE_OK)
    out = wan2gp.run(sys.executable, d, cfg, str(tmp_path / "work"))
    assert open(out, "rb").read() == b"MP41280x704"
    with pytest.raises(wan2gp.WanError):
        wan2gp.run("", "", cfg, str(tmp_path / "w2"))


def test_wan_cancel_kills(tmp_path):
    d = _fake_wan(tmp_path, "import time\ntime.sleep(60)\n")
    img = tmp_path / "s.png"; _png(img, "green")
    ev = threading.Event(); threading.Timer(1.0, ev.set).start()
    with pytest.raises(wan2gp.WanError, match="Cancelled"):
        wan2gp.run(sys.executable, d, wan2gp.settings("x", str(img)), str(tmp_path / "w"), cancelled=ev.is_set)


def test_detect_python(tmp_path):
    d = tmp_path / "app"; (d / "venv" / "Scripts").mkdir(parents=True); (d / "wgp.py").write_text("")
    (d / "venv" / "Scripts" / "python.exe").write_text("")
    assert wan2gp.detect(str(d)) == (str(d), str(d / "venv" / "Scripts" / "python.exe"))


def test_animate_unloads_forge_and_reloads_even_on_error(tmp_path):
    calls = []

    class Forge:
        def unload_checkpoint(self):
            calls.append("unload"); return True

        def reload_checkpoint(self):
            calls.append("reload"); return True

    p = vp.new_project("t"); p["scenes"] = vp.parse_plan(PLAN, p)[1]
    for s in p["scenes"]:
        _png(tmp_path / f"{s['id']}.png", "red"); s["still"] = f"{s['id']}.png"
    p["scenes"][2]["animate"] = True

    def runner(py, d, cfg, work, cancelled=None, log=None):
        calls.append(os.path.basename(work)); os.makedirs(work, exist_ok=True)
        f = os.path.join(work, "o.mp4"); open(f, "wb").write(b"v"); return f
    assert vp.animate(p, str(tmp_path), {"dir": "d", "python": "p"}, Forge(), runner=runner) == 2
    assert calls == ["unload", "s01", "s03", "reload"]
    assert p["scenes"][0]["clip"] == "s01_wan.mp4" and p["scenes"][1]["clip"] == ""
    assert vp.animate(p, str(tmp_path), {}, Forge(), runner=runner) == 0  # resume: nothing left
    calls.clear(); vp.redo_scene(p["scenes"][2], str(tmp_path), "clip")

    def bad(*a, **k):
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        vp.animate(p, str(tmp_path), {}, Forge(), runner=bad)
    assert calls == ["unload", "reload"]


# ------------------------------------------------------------------ ffmpeg
def test_kenburns_filters():
    for cam in vp.CAMERAS:
        f = vp.kenburns_filter(cam, 2.0)
        assert "zoompan" in f and "d=48" in f and "s=1280x704" in f
    a = vp.xfade_args(["a", "b", "c"], [2, 3, 1], 0.5, "o.mp4")
    fc = a[a.index("-filter_complex") + 1]
    assert "offset=2.000" in fc and "offset=5.000" in fc and fc.endswith("[v]")


@needs_ff
def test_end_to_end_build(tmp_path):
    pdir = str(tmp_path / "proj"); os.makedirs(pdir)
    p = vp.new_project("Synthetic test"); p.update(size=[320, 176], fps=12, crossfade=0.3, captions=True)
    p["scenes"] = [vp.new_scene(i, f"synthetic {c}", d, cam, cap) for i, (c, d, cam, cap) in enumerate(
        [("red", 1.5, "Slow push in", "Hello"), ("green", 1.2, "Pan left", ""), ("blue", 1.0, "Pull out", "It's: done")])]
    for s, c in zip(p["scenes"], ("red", "green", "blue")):
        _png(os.path.join(pdir, s["id"] + ".png"), c); s["still"] = s["id"] + ".png"
    # scene 2 gets a "Wan" clip (a short synthetic video) that is shorter than the scene -> last frame is held
    clip = os.path.join(pdir, "s02_wan.mp4")
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=12:duration=0.6",
                    "-pix_fmt", "yuv420p", clip], check=True)
    p["scenes"][1].update(animate=True, clip="s02_wan.mp4")
    song = str(tmp_path / "song.wav")
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=10", song], check=True)
    p["song"] = song
    steps = []
    out = vp.build(p, pdir, FF, progress=lambda pct, m: steps.append(pct))
    assert os.path.exists(out) and steps[-1] == 100
    assert abs(vp.probe_secs(FF, out) - 3.7) < 0.15
    info = subprocess.run([FF, "-hide_banner", "-i", out], capture_output=True).stderr.decode()
    assert "320x176" in info and "Audio: aac" in info
    p["scenes"][0]["still"] = ""
    with pytest.raises(vp.VideoError, match="s01"):
        vp.build(p, pdir, FF)


# ------------------------------------------------------------------ page
def test_page_plan_edit_and_toggle(win, tmp_path):
    win.go("Video maker")
    assert win.vm_table.columnCount() == 6
    win.vm_name.setText("Page test"); win.vm_idea.setPlainText("two adult friends cycle by the sea")
    assert win.vm_apply_plan(PLAN) == 3
    assert win.vm_name.text() == "Page test" and win.vm_table.rowCount() == 3
    from PySide6.QtCore import Qt
    win.vm_table.item(1, 4).setCheckState(Qt.Checked)
    assert win.vm_proj["scenes"][1]["animate"]
    win.vm_cur = 2; win.vm_select(2); win.vm_caption.setText("The end"); win.vm_secs.setValue(2.5); win.vm_apply_scene()
    q = vp.load_project(win.vm_dir())
    assert q["scenes"][2]["caption"] == "The end" and q["scenes"][2]["duration"] == 2.5 and q["scenes"][1]["animate"]
    win.vm_add_scene(); assert win.vm_proj["scenes"][-1]["id"] == "s04"
    win.vm_new(); assert win.vm_table.rowCount() == 0
    win.vm_refresh_projects(); win.vm_open.setCurrentIndex(win.vm_open.findText("Page test"))
    assert win.vm_open_selected() and win.vm_table.rowCount() == 3


def test_page_stills_with_mock_backend(win, tmp_path, monkeypatch):
    win.go("Video maker"); win.vm_name.setText("Stills test"); win.vm_apply_plan(PLAN)

    class B(imagegen.A1111):
        def generate(self, job, workflow=None, progress=None, cancelled=None):
            assert job.restore_settings and job.width % 64 == 0 and job.adetailer == "face_yolov8s.pt"
            return [_png(tmp_path / "x.png", "purple")]
    b = B("http://127.0.0.1:9")
    monkeypatch.setattr(win, "make_job", lambda prompt, neg="", seed=None, tag="": (imagegen.Job(prompt, neg, 1024, 1024, seed), b, None))
    win.vm_ad.setChecked(True)
    assert win.vm_stills()
    assert _wait(lambda: "✓ 3" in win.vm_status.text(), 20), win.vm_status.text()
    assert all(s.get("still") for s in win.vm_proj["scenes"]) and win.vm_table.item(0, 5).text() == "still"


# ------------------------------------------------------------------ 5.3 fix: OOM when the image backend holds VRAM
OOM_LOG = """Traceback (most recent call last):
torch.AcceleratorError: CUDA error: out of memory
CUDA kernel errors might be asynchronously reported at some other API call, so the stacktrace below might be incorrect.
  [ERROR] The generation of the video has encountered an error: it is likely that you have unsufficient RAM
"""


def test_error_line_explains_oom_and_other_errors():
    assert "ran out of memory" in wan2gp.error_line(OOM_LOG)
    assert wan2gp.error_line("loading\nValueError: bad resolution 1x1\n") == "ValueError: bad resolution 1x1"


def test_runner_reports_real_error_and_keeps_log(tmp_path):
    d = _fake_wan(tmp_path, "import sys\nsys.stderr.write(%r)\nsys.exit(1)\n" % OOM_LOG)
    img = tmp_path / "s.png"; _png(img, "green")
    with pytest.raises(wan2gp.WanError) as e:
        wan2gp.run(sys.executable, d, wan2gp.settings("x", str(img)), str(tmp_path / "w"))
    assert "ran out of memory" in str(e.value) and "wan2gp.log" in str(e.value)
    assert "CUDA error: out of memory" in open(tmp_path / "w" / "wan2gp.log", encoding="utf-8").read()


def test_comfy_free_endpoint():
    seen = []
    import http.server
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
        def log_message(self, *a):
            pass
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        c = imagegen.ComfyUI(f"http://127.0.0.1:{s.server_address[1]}")
        assert c.unload_checkpoint() and c.reload_checkpoint()
        assert seen == [("/free", {"unload_models": True, "free_memory": True})]
    finally:
        s.shutdown()


def test_animate_retries_once_after_oom(tmp_path):
    calls = []

    class Comfy:
        def unload_checkpoint(self):
            calls.append("free"); return True

        def reload_checkpoint(self):
            calls.append("reload"); return True
    p = vp.new_project("t"); p["scenes"] = [vp.new_scene(0, "adult woman waving", 3, animate=True)]
    _png(tmp_path / "s01.png", "red"); p["scenes"][0]["still"] = "s01.png"
    n = {"k": 0}

    def runner(py, d, cfg, work, cancelled=None, log=None):
        n["k"] += 1; calls.append("run")
        if n["k"] == 1:
            raise wan2gp.WanError("Wan2GP made no clip (exit 1): " + wan2gp.OOM_HINT)
        os.makedirs(work, exist_ok=True); f = os.path.join(work, "o.mp4"); open(f, "wb").write(b"v"); return f
    import promptmaker.videoproject as m
    orig = m.time.sleep; m.time.sleep = lambda s: None
    try:
        assert vp.animate(p, str(tmp_path), {}, Comfy(), runner=runner) == 1
    finally:
        m.time.sleep = orig
    assert calls == ["free", "run", "free", "run", "reload"]
