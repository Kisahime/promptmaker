"""5.3 Headless Wan2GP runner: `python wgp.py --process settings.json --output-dir <dir>` for one image-to-video
clip at a time (FastWan 5B i2v, 1280x704, 121 frames, 3 steps by default). Cancelling kills the process."""
import copy
import glob
import json
import os
import subprocess
import sys
import time

TEMPLATE = os.path.join(os.path.dirname(__file__), "assets", "wan2gp_fastwan_i2v.json")
DEFAULT_DIR = r"C:\pinokio\api\wan.git\app"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class WanError(Exception):
    pass


def find_python(wan_dir):
    for rel in (("venv", "Scripts", "python.exe"), ("env", "Scripts", "python.exe"), ("..", "env", "Scripts", "python.exe"),
                ("venv", "bin", "python"), ("env", "bin", "python")):
        p = os.path.normpath(os.path.join(wan_dir or "", *rel))
        if wan_dir and os.path.isfile(p):
            return p
    return ""


def detect(wan_dir="", python=""):
    """(wan_dir, python) with defaults filled in when they exist on disk; '' for anything not found."""
    d = wan_dir or (DEFAULT_DIR if os.path.isfile(os.path.join(DEFAULT_DIR, "wgp.py")) else "")
    if d and not os.path.isfile(os.path.join(d, "wgp.py")):
        d = ""
    py = python if python and os.path.isfile(python) else find_python(d)
    return d, py


def settings(prompt, image, seed=42, frames=121, steps=3, size=(1280, 704), negative="", template=TEMPLATE):
    with open(template, encoding="utf-8") as f:
        s = json.load(f)
    s = copy.deepcopy(s)
    s.update(prompt=prompt, image_start=os.path.abspath(image), seed=int(seed if seed not in (None, -1, "") else 42),
             video_length=int(frames), num_inference_steps=int(steps), resolution=f"{size[0]}x{size[1]}",
             sliding_window_size=int(frames))
    if negative:
        s["negative_prompt"] = negative
    return s


def command(python, wan_dir, settings_path, out_dir):
    return [python, os.path.join(wan_dir, "wgp.py"), "--process", settings_path, "--output-dir", out_dir]


def run(python, wan_dir, cfg, work_dir, cancelled=None, log=None, timeout=1800, popen=subprocess.Popen):
    """Render one clip. Returns the path of the new .mp4 in work_dir."""
    if not (python and wan_dir and os.path.isfile(os.path.join(wan_dir, "wgp.py"))):
        raise WanError("Wan2GP not found – set its folder in Video → Tools")
    os.makedirs(work_dir, exist_ok=True)
    sp = os.path.join(work_dir, "settings.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    before = set(glob.glob(os.path.join(work_dir, "**", "*.mp4"), recursive=True))
    start = time.time()
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    logf = open(os.path.join(work_dir, "wan2gp.log"), "w", encoding="utf-8", errors="replace")
    try:
        p = popen(command(python, wan_dir, sp, work_dir), cwd=wan_dir, stdout=logf, stderr=subprocess.STDOUT, env=env,
                  creationflags=CREATE_NO_WINDOW)
        while p.poll() is None:
            if cancelled and cancelled():
                p.kill(); p.wait()
                raise WanError("Cancelled")
            if time.time() - start > timeout:
                p.kill(); p.wait()
                raise WanError("Wan2GP timed out")
            if log:
                log(int(time.time() - start))
            time.sleep(0.5)
    finally:
        logf.close()
    new = [f for f in glob.glob(os.path.join(work_dir, "**", "*.mp4"), recursive=True)
           if f not in before and os.path.getmtime(f) >= start - 1]
    if p.returncode or not new:
        tail, log_path = "", os.path.join(work_dir, "wan2gp.log")
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                tail = f.read()
        except OSError:
            pass
        raise WanError(f"Wan2GP made no clip (exit {p.returncode}): {error_line(tail)} – full log: {log_path}")
    return max(new, key=os.path.getmtime)


OOM_HINT = ("the GPU ran out of memory (CUDA out of memory). Close other GPU apps (ComfyUI / Forge with a model loaded, "
            "games, video players) or lower Frames")


def is_oom(text):
    t = (text or "").lower()
    return "out of memory" in t or "cudaerrormemoryallocation" in t or "unsufficient ram" in t


def error_line(log):
    """The line that says what went wrong, not CUDA's generic 'might be asynchronously reported' text."""
    if is_oom(log):
        return OOM_HINT
    lines = [l.strip() for l in (log or "").splitlines() if l.strip()]
    for pat in ("[ERROR]", "Error:", "Exception:", "error:"):
        hits = [l for l in lines if pat in l and "CUDA kernel errors might be" not in l]
        if hits:
            return hits[-1][:300]
    return (lines[-1][:300] if lines else "no output")
