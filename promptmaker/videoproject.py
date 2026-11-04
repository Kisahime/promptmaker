"""5.3 Video mode: an idea / story (optional song + lyrics) -> Ollama scene plan -> a Forge still per scene ->
Wan2GP image-to-video for ticked scenes, Ken Burns zoom/pan for the rest -> ffmpeg build (trim, captions,
crossfades, audio) to one MP4. Projects live in data/videos/<name>/project.json with their stills and clips,
so every step resumes and any scene can be redone on its own."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

VERSION = 2                        # 2: character sheet, scene.characters, seed override vs used_seed
FPS = 24
SIZE = (1280, 704)                 # FastWan 5B native size
WAN_FRAMES = 121                   # ~5 s at 24 fps
CAMERAS = ["Slow push in", "Pull out", "Pan left", "Pan right", "Tilt up", "Tilt down", "Static"]
MIN_SECS, MAX_SECS = 1.5, 12.0
FONT = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Nunito.ttf")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class VideoError(Exception):
    pass


class Cancelled(VideoError):
    pass


# ------------------------------------------------------------------ project data
def slug(name):
    s = re.sub(r"[^\w\- ]+", "", (name or "").strip()).strip().replace(" ", "_")
    return s[:60] or "untitled"


def videos_dir(data_dir):
    d = os.path.join(data_dir, "videos"); os.makedirs(d, exist_ok=True)
    return d


def new_scene(i=0, prompt="", duration=4.0, camera="Slow push in", caption="", animate=False, motion="", characters=None):
    # seed: -1 = use the main character's seed (or random); used_seed = the seed the still was actually made with
    return {"id": f"s{i + 1:02d}", "prompt": prompt, "negative": "", "seed": -1, "used_seed": -1,
            "characters": list(characters or []), "facelock": "", "duration": float(duration),
            "camera": camera if camera in CAMERAS else "Slow push in", "caption": caption, "motion": motion,
            "animate": bool(animate), "still": "", "clip": "", "status": "planned"}


def new_project(name="Untitled video", idea=""):
    return {"version": VERSION, "name": name, "idea": idea, "style": "", "song": "", "lyrics": "", "song_secs": 0.0,
            "size": list(SIZE), "fps": FPS, "crossfade": 0.4, "captions": True, "adetailer": False,
            "checkpoint": "", "family": "", "characters": [], "scenes": [], "output": "", "created": time.time()}


# ------------------------------------------------------------------ character sheet
def new_character(chars=(), name="", description="", ref="", seed=-1, main=False):
    ids = {c["id"] for c in chars}
    i = 1
    while f"c{i}" in ids:
        i += 1
    return {"id": f"c{i}", "name": name or f"Character {i}", "description": description, "ref": ref,
            "seed": int(seed), "main": bool(main)}


def character_from_store(char, chars=(), profile=None):
    """A project character from the app's Characters library (its text for the target model + first reference)."""
    from . import characters as ch
    ref = (ch.references(char) or [""])[0]
    desc = ch.character_text(char, None, profile, with_lora=False, with_triggers=True)
    return new_character(chars, char.get("name", ""), desc, ref)


def char_by_id(proj, cid):
    return next((c for c in proj.get("characters") or [] if c["id"] == cid), None)


def scene_characters(proj, s):
    """The scene's characters in sheet order with the main character first (that one gets the face lock / seed)."""
    want = set(s.get("characters") or [])
    cs = [c for c in proj.get("characters") or [] if c["id"] in want]
    return sorted(cs, key=lambda c: not c.get("main"))


def main_character(proj, s):
    cs = scene_characters(proj, s)
    return cs[0] if cs else None


def scene_seed(proj, s):
    """Scene override, else the main character's fixed seed, else -1 (random)."""
    if int(s.get("seed", -1)) >= 0:
        return int(s["seed"])
    m = main_character(proj, s)
    return int(m["seed"]) if m and int(m.get("seed", -1)) >= 0 else -1


def ref_path(proj, pdir, c):
    r = (c or {}).get("ref") or ""
    if r and not os.path.isabs(r):
        r = os.path.join(pdir, r)
    return os.path.normpath(r) if r and os.path.isfile(r) else ""


def set_reference(c, pdir, src):
    """Copy a reference image into the project (chars/<id>.png) so the project stays self-contained."""
    if not src:
        c["ref"] = ""; return ""
    os.makedirs(os.path.join(pdir, "chars"), exist_ok=True)
    ext = os.path.splitext(src)[1].lower() or ".png"
    rel = os.path.join("chars", c["id"] + ext)
    if os.path.abspath(src) != os.path.abspath(os.path.join(pdir, rel)):
        shutil.copyfile(src, os.path.join(pdir, rel))
    c["ref"] = rel.replace("\\", "/")
    return c["ref"]


def migrate(p):
    """Older project.json -> current version (in place)."""
    v = int(p.get("version") or 1)
    if v < 2:
        p.setdefault("characters", [])
        for s in p.get("scenes") or []:
            s["used_seed"] = s.get("used_seed", s.get("seed", -1))  # v1 stored the generated seed in 'seed'
            s["seed"] = -1
            s.setdefault("characters", [])
    p["version"] = VERSION
    return p


def project_dir(data_dir, name):
    return os.path.join(videos_dir(data_dir), slug(name))


def save_project(proj, pdir):
    os.makedirs(pdir, exist_ok=True)
    proj["version"] = VERSION
    tmp = os.path.join(pdir, "project.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(pdir, "project.json"))
    return os.path.join(pdir, "project.json")


def load_project(pdir):
    with open(os.path.join(pdir, "project.json"), encoding="utf-8") as f:
        p = json.load(f)
    migrate(p)
    base = new_project()
    base.update(p)
    base["characters"] = [dict(new_character(), **c) for c in p.get("characters") or []]
    base["scenes"] = [dict(new_scene(i), **s) for i, s in enumerate(p.get("scenes") or [])]
    for s in base["scenes"]:  # resume: files that vanished are simply made again
        for k in ("still", "clip"):
            if s.get(k) and not os.path.exists(os.path.join(pdir, s[k])):
                s[k] = ""
        s["status"] = scene_status(s)
    return base


def list_projects(data_dir):
    out = []
    for f in sorted(glob.glob(os.path.join(videos_dir(data_dir), "*", "project.json")), key=os.path.getmtime, reverse=True):
        try:
            with open(f, encoding="utf-8") as fh:
                out.append((json.load(fh).get("name") or os.path.basename(os.path.dirname(f)), os.path.dirname(f)))
        except (OSError, ValueError):
            pass
    return out


def scene_status(s):
    if s.get("animate") and s.get("clip"):
        return "animated"
    if s.get("still"):
        return "still"
    return "planned"


def redo_scene(s, pdir, what="still"):
    """Forget a scene's still (and its clip, which came from it) or only its clip so the next run makes it again."""
    keys = ("still", "clip") if what == "still" else ("clip",)
    for k in keys:
        if s.get(k):
            try:
                os.remove(os.path.join(pdir, s[k]))
            except OSError:
                pass
            s[k] = ""
    s["status"] = scene_status(s)


def total_secs(proj):
    return round(sum(float(s.get("duration") or 0) for s in proj["scenes"]), 3)


# ------------------------------------------------------------------ song / lyrics timing
_LRC = re.compile(r"^\s*\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$")


def parse_lyrics(text):
    """[(start_secs or None, line)] – LRC '[mm:ss.xx] line' timestamps are kept, plain lines get None."""
    out = []
    for raw in (text or "").splitlines():
        m = _LRC.match(raw)
        if m:
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
        elif raw.strip() and not re.match(r"^\s*\[[^\]]*\]\s*$", raw):  # skip [Chorus] style tags
            out.append((None, raw.strip()))
    return out


def lyric_timeline(lyrics, song_secs):
    """[(start, end, line)] covering the song. Timestamped lines are used as-is; otherwise lines share it evenly."""
    lines = parse_lyrics(lyrics)
    if not lines or not song_secs:
        return []
    if all(t is not None for t, _ in lines):
        starts = [t for t, _ in lines]
        out = []
        for i, (t, ln) in enumerate(lines):
            end = starts[i + 1] if i + 1 < len(lines) else song_secs
            out.append((0.0 if i == 0 else t, max(end, t + 0.5), ln))
        return out
    step = song_secs / len(lines)
    return [(i * step, (i + 1) * step, ln) for i, (_, ln) in enumerate(lines)]


def fit_durations(scenes, target):
    """Scale scene durations so they add up to `target` seconds (song length), each within MIN..MAX where possible."""
    if not scenes or not target:
        return scenes
    cur = sum(max(0.1, float(s.get("duration") or 4)) for s in scenes)
    for s in scenes:
        s["duration"] = max(0.1, float(s.get("duration") or 4)) * target / cur
    drift = target - sum(s["duration"] for s in scenes)
    scenes[-1]["duration"] += drift
    for s in scenes:
        s["duration"] = round(s["duration"], 3)
    scenes[-1]["duration"] = round(target - sum(s["duration"] for s in scenes[:-1]), 3)
    return scenes


# ------------------------------------------------------------------ Ollama plan
def plan_messages(proj, n=8, profile=None):
    fmt = (profile or {}).get("format", "tags")
    style = "comma-separated booru-style tags" if fmt == "tags" else "one or two descriptive sentences"
    timeline = lyric_timeline(proj.get("lyrics"), proj.get("song_secs"))
    lines = ""
    if timeline:
        n = len(timeline)
        lines = ("\nThe video follows a song. Make exactly one scene per lyric line, in order; use the lyric line as "
                 "the caption and show what it says:\n" +
                 "\n".join(f"{i + 1}. ({b - a:.1f}s) {ln}" for i, (a, b, ln) in enumerate(timeline)))
    sys_msg = (
        "You plan short videos as a list of scenes. Reply with JSON only: {\"title\": str, \"scenes\": [{\"prompt\": str, "
        "\"duration\": seconds (2-8), \"camera\": one of " + json.dumps(CAMERAS) + ", \"motion\": str, \"caption\": str, "
        "\"animate\": bool}]}. 'prompt' is a still-image prompt written as " + style + ": subject, action, setting, "
        "lighting, shot type – no camera moves. Keep the same characters, outfits and colours in every scene. Every "
        "person is an adult. Keep it safe for work. 'motion' is one sentence describing how the scene moves for an "
        "image-to-video model. Set 'animate' true for the 2-4 scenes with the most movement. 'caption' is short "
        "on-screen text or empty.")
    cast = ""
    if proj.get("characters"):
        sys_msg += (" Each scene also has \"characters\": a list of the character ids (from the cast list) who appear "
                    "in it. Refer to them by name in the prompt but do NOT describe their looks, hair, eyes or clothes – "
                    "their fixed description is added automatically.")
        cast = "\n\nCast (id: name):\n" + "\n".join(f"{c['id']}: {c['name']}" for c in proj["characters"])
    user = (f"Idea / story:\n{proj.get('idea', '').strip()}\n\nStyle: {proj.get('style') or 'model default'}\n"
            f"Number of scenes: {n}{cast}{lines}")
    return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]


def _json_from(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                return None
    return None


def parse_plan(text, proj):
    """Turn the AI's JSON into scenes (applies song timing / captions). Returns (title, scenes)."""
    d = _json_from(text)
    if isinstance(d, list):
        d = {"scenes": d}
    if not isinstance(d, dict):
        return "", []
    raw = [s for s in (d.get("scenes") or []) if isinstance(s, dict) and str(s.get("prompt") or "").strip()]
    scenes = []
    for i, s in enumerate(raw):
        try:
            dur = float(s.get("duration") or 4)
        except (TypeError, ValueError):
            dur = 4.0
        cam = next((c for c in CAMERAS if c.lower() == str(s.get("camera", "")).strip().lower()), "Slow push in")
        scenes.append(new_scene(i, str(s["prompt"]).strip(), min(MAX_SECS, max(MIN_SECS, dur)), cam,
                                str(s.get("caption") or "").strip(), bool(s.get("animate")), str(s.get("motion") or "").strip(),
                                _plan_chars(s.get("characters"), proj)))
    timeline = lyric_timeline(proj.get("lyrics"), proj.get("song_secs"))
    if timeline and scenes:
        scenes = scenes[:len(timeline)]
        while len(scenes) < len(timeline):  # AI returned too few: repeat the last look for the remaining lines
            last = scenes[-1]
            scenes.append(new_scene(len(scenes), last["prompt"], 4, last["camera"], "", False, last["motion"], last["characters"]))
        for s, (a, b, ln) in zip(scenes, timeline):
            s["duration"] = round(b - a, 3)
            s["caption"] = ln
        scenes[-1]["duration"] = round(proj["song_secs"] - sum(s["duration"] for s in scenes[:-1]), 3)
    elif proj.get("song_secs") and scenes:
        fit_durations(scenes, float(proj["song_secs"]))
    return str(d.get("title") or "").strip(), scenes


def _plan_chars(raw, proj):
    """AI's character refs (ids or names, any case) -> known ids, in order, no repeats."""
    if isinstance(raw, str):
        raw = [x for x in re.split(r"[,;]", raw)]
    out = []
    for r in raw or []:
        key = str(r.get("id") if isinstance(r, dict) else r).strip().lower()
        c = next((c for c in proj.get("characters") or [] if key in (c["id"].lower(), c["name"].strip().lower())), None)
        if c and c["id"] not in out:
            out.append(c["id"])
    return out


def scene_prompt(proj, s):
    """Style prefix, then each character's fixed description verbatim (main first), then the scene prompt."""
    parts = [(proj.get("style") or "").strip()]
    parts += [(c.get("description") or "").strip() for c in scene_characters(proj, s)]
    parts.append((s.get("prompt") or "").strip())
    return ", ".join(x.strip(" ,") for x in parts if x and x.strip(" ,"))


def motion_prompt(proj, s):
    from .video import CAMERA
    cam = {"Slow push in": "Slow push in", "Pull out": "Pull out", "Pan left": "Pan left", "Pan right": "Pan right",
           "Tilt up": "Tilt up", "Tilt down": "Tilt down", "Static": "Static"}.get(s.get("camera"), "Slow push in")
    parts = [s["prompt"], s.get("motion") or "natural, smooth motion", CAMERA.get(cam, "")]
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()) + "."


# ------------------------------------------------------------------ ffmpeg
def find_ffmpeg(configured="", wan_dir=""):
    cands = [configured, shutil.which("ffmpeg") or ""]
    if wan_dir:
        cands.append(os.path.join(wan_dir, "ffmpeg_bins", "ffmpeg.exe"))
    cands += [r"C:\pinokio\bin\ffmpeg-env\Library\bin\ffmpeg.exe", r"C:\pinokio\api\wan.git\app\ffmpeg_bins\ffmpeg.exe",
              r"C:\ffmpeg\bin\ffmpeg.exe"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return ""


def run_ffmpeg(ffmpeg, args, cancelled=None, timeout=3600):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + [str(a) for a in args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    end = time.time() + timeout
    while p.poll() is None:
        if (cancelled and cancelled()) or time.time() > end:
            p.kill(); p.wait()
            raise Cancelled("Cancelled") if cancelled and cancelled() else VideoError("ffmpeg timed out")
        time.sleep(0.1)
    if p.returncode:
        raise VideoError("ffmpeg failed: " + (p.stderr.read().decode("utf-8", "replace").strip()[-600:] or str(p.returncode)))


def probe_secs(ffmpeg, path):
    """Media duration in seconds, from ffmpeg's own banner (no ffprobe needed)."""
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, creationflags=CREATE_NO_WINDOW)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr.decode("utf-8", "replace"))
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _fpath(p):
    """A path inside an ffmpeg filter argument (drawtext fontfile / textfile)."""
    return p.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def kenburns_filter(camera, secs, size=SIZE, fps=FPS):
    w, h = size
    n = max(1, int(round(secs * fps)))
    z0, z1 = 1.0, 1.18
    zin = f"{z0}+({z1 - z0})*on/{n}"
    zout = f"{z1}-({z1 - z0})*on/{n}"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    moves = {
        "Slow push in": (zin, cx, cy),
        "Pull out": (zout, cx, cy),
        "Pan left": ("1.15", f"(iw-iw/zoom)*(1-on/{n})", cy),
        "Pan right": ("1.15", f"(iw-iw/zoom)*on/{n}", cy),
        "Tilt up": ("1.15", cx, f"(ih-ih/zoom)*(1-on/{n})"),
        "Tilt down": ("1.15", cx, f"(ih-ih/zoom)*on/{n}"),
        "Static": ("1.0", cx, cy),
    }
    z, x, y = moves.get(camera, moves["Slow push in"])
    # upscale first so the sub-pixel zoom doesn't jitter
    return (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")


def caption_filter(textfile, font=FONT):
    return (f"drawtext=fontfile='{_fpath(font)}':textfile='{_fpath(textfile)}':fontcolor=white:fontsize=h/16:"
            f"borderw=3:bordercolor=black@0.8:x=(w-text_w)/2:y=h-text_h-h/12")


def segment_args(src, out, secs, camera, is_video, size=SIZE, fps=FPS, caption_file=""):
    """ffmpeg args that turn a still (Ken Burns) or a Wan clip (fit/hold last frame) into an exact-length segment."""
    w, h = size
    if is_video:
        vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={secs:.3f},trim=duration={secs:.3f},setpts=PTS-STARTPTS,format=yuv420p")
        inp = ["-i", src]
    else:
        vf = kenburns_filter(camera, secs, size, fps) + f",trim=duration={secs:.3f},setpts=PTS-STARTPTS"
        inp = ["-loop", "1", "-framerate", str(fps), "-t", f"{secs + 0.5:.3f}", "-i", src]
    if caption_file:
        vf += "," + caption_filter(caption_file)
    return inp + ["-an", "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-t", f"{secs:.3f}", out]


def xfade_args(segs, durs, xf, out, audio="", total=0.0):
    """Join segments with crossfades of `xf` seconds. Segment k (except the last) must be durs[k] + xf long,
    so the result is exactly sum(durs)."""
    args = []
    for s in segs:
        args += ["-i", s]
    if audio:
        args += ["-i", audio]
    if len(segs) == 1 or xf <= 0:
        fc = "".join(f"[{i}:v]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]"
    else:
        fc, prev, off = [], "[0:v]", 0.0
        for k in range(1, len(segs)):
            off += durs[k - 1]
            lab = "[v]" if k == len(segs) - 1 else f"[x{k}]"
            fc.append(f"{prev}[{k}:v]xfade=transition=fade:duration={xf:.3f}:offset={off - 0:.3f}{lab}")
            prev = lab
        fc = ";".join(fc)
    args += ["-filter_complex", fc, "-map", "[v]"]
    if audio:
        fade_at = max(0.0, total - 1.5)
        args += ["-map", f"{len(segs)}:a", "-af", f"afade=t=out:st={fade_at:.3f}:d=1.5", "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if total:
        args += ["-t", f"{total:.3f}"]
    return args + [out]


def build(proj, pdir, ffmpeg, progress=None, cancelled=None):
    """Assemble the final MP4. Every scene needs a still (or a clip). Returns the output path."""
    if not ffmpeg:
        raise VideoError("ffmpeg not found – set its path in Video → Tools")
    scenes = [s for s in proj["scenes"] if float(s.get("duration") or 0) > 0]
    missing = [s["id"] for s in scenes if not (s.get("still") or s.get("clip"))]
    if not scenes:
        raise VideoError("No scenes to build")
    if missing:
        raise VideoError("Make stills first – missing: " + ", ".join(missing))
    size, fps = tuple(proj.get("size") or SIZE), int(proj.get("fps") or FPS)
    xf = max(0.0, float(proj.get("crossfade") or 0))
    xf = min(xf, min(float(s["duration"]) for s in scenes) / 2)
    seg_dir = os.path.join(pdir, "segments"); os.makedirs(seg_dir, exist_ok=True)
    segs, durs = [], []
    for i, s in enumerate(scenes):
        if cancelled and cancelled():
            raise Cancelled("Cancelled")
        if progress:
            progress(int(90 * i / len(scenes)), f"Segment {i + 1}/{len(scenes)}")
        d = float(s["duration"]); seg_len = d + (xf if i < len(scenes) - 1 else 0)
        cap = ""
        if proj.get("captions", True) and (s.get("caption") or "").strip():
            cap = os.path.join(seg_dir, f"{s['id']}.txt")
            with open(cap, "w", encoding="utf-8") as f:
                f.write(s["caption"].strip())
        use_clip = bool(s.get("animate") and s.get("clip"))
        src = os.path.join(pdir, s["clip"] if use_clip else s["still"])
        out = os.path.join(seg_dir, f"{i:03d}_{s['id']}.mp4")
        run_ffmpeg(ffmpeg, segment_args(src, out, seg_len, s.get("camera"), use_clip, size, fps, cap), cancelled)
        segs.append(out); durs.append(d)
    total = round(sum(durs), 3)
    song = proj.get("song") if proj.get("song") and os.path.isfile(proj.get("song")) else ""
    out = os.path.join(pdir, slug(proj.get("name")) + ".mp4")
    if progress:
        progress(92, "Joining")
    run_ffmpeg(ffmpeg, xfade_args(segs, durs, xf, out, song, total), cancelled)
    proj["output"] = os.path.basename(out)
    if progress:
        progress(100, "Done")
    return out


# ------------------------------------------------------------------ pipeline steps (run in a worker thread)
def make_stills(proj, pdir, jobs, backend, progress=None, cancelled=None, save=None):
    """jobs: [(scene, imagegen.Job)] built on the UI thread. Saves sNN.png per scene and the project after each."""
    done = 0
    for i, (s, job) in enumerate(jobs):
        if cancelled and cancelled():
            raise Cancelled("Cancelled")
        if progress:
            progress(int(100 * i / max(1, len(jobs))), f"Still {i + 1}/{len(jobs)} · {s['id']}")
        imgs = backend.generate(job, progress=None, cancelled=cancelled)
        name = f"{s['id']}.png"
        with open(os.path.join(pdir, name), "wb") as f:
            f.write(imgs[0])
        if s.get("clip"):  # a new still makes the old clip stale
            redo_scene(s, pdir, "clip")
        s["still"], s["used_seed"] = name, int(getattr(job, "seed", -1) or -1)
        s["status"] = scene_status(s); done += 1
        (save or (lambda: save_project(proj, pdir)))()
    if progress:
        progress(100, "Stills done")
    return done


def animate(proj, pdir, wan, forge=None, progress=None, cancelled=None, save=None, redo=False, runner=None):
    """Wan2GP clips for ticked scenes, one at a time. Forge's checkpoint is unloaded first (8 GB GPUs can't hold both)
    and reloaded afterwards, even on error / cancel. wan: {"dir", "python", "frames", "steps"}."""
    from . import wan2gp
    todo = [s for s in proj["scenes"] if s.get("animate") and s.get("still") and (redo or not s.get("clip"))]
    if not todo:
        return 0
    runner = runner or wan2gp.run
    unloaded = False
    if forge is not None:
        if progress:
            progress(0, "Freeing VRAM (unloading the image model in Forge / ComfyUI)")
        unloaded = forge.unload_checkpoint()
    done = 0
    try:
        for i, s in enumerate(todo):
            if cancelled and cancelled():
                raise Cancelled("Cancelled")
            label = f"Clip {i + 1}/{len(todo)} · {s['id']}"
            if progress:
                progress(int(100 * i / len(todo)), label + " (about 2 min)")
            cfg = wan2gp.settings(motion_prompt(proj, s), os.path.join(pdir, s["still"]), s.get("used_seed", 42),
                                  wan.get("frames", WAN_FRAMES), wan.get("steps", 3), tuple(proj.get("size") or SIZE))
            work = os.path.join(pdir, "wan", s["id"])
            lg = (lambda t, l=label, i=i: progress(int(100 * i / len(todo)), f"{l} · {t}s")) if progress else None
            try:
                clip = runner(wan.get("python"), wan.get("dir"), cfg, work, cancelled=cancelled, log=lg)
            except wan2gp.WanError as e:
                if not wan2gp.is_oom(str(e)) or forge is None:
                    raise
                # out of memory: the image backend may have loaded a model again – free it and try this clip once more
                if progress:
                    progress(int(100 * i / len(todo)), label + " · out of memory, freeing VRAM and retrying")
                unloaded = forge.unload_checkpoint() or unloaded
                time.sleep(3)
                clip = runner(wan.get("python"), wan.get("dir"), cfg, work, cancelled=cancelled, log=lg)
            name = f"{s['id']}_wan.mp4"
            shutil.copyfile(clip, os.path.join(pdir, name))
            s["clip"] = name; s["status"] = scene_status(s); done += 1
            (save or (lambda: save_project(proj, pdir)))()
    except Exception as e:  # noqa: BLE001
        if "Cancelled" in str(e):
            raise Cancelled("Cancelled") from e
        raise
    finally:
        if unloaded and forge is not None:
            forge.reload_checkpoint()
    if progress:
        progress(100, "Clips done")
    return done


# ------------------------------------------------------------------ face lock (IP-Adapter Plus Face, via Face Swap's code)
def facelock_plan(proj, s, pdir, info, family_warning=""):
    """(reference path or '', note) for a scene. info = faceswap.detect(backend). Only the scene's main character is
    locked; anything that can't work is skipped with a note instead of failing the still."""
    m = main_character(proj, s)
    if not m:
        return "", ""
    ref = ref_path(proj, pdir, m)
    if not ref:
        return "", ""
    others = len(scene_characters(proj, s)) - 1
    extra = f" · only {m['name']} is face-locked ({others} other character{'s' if others > 1 else ''} use text only)" if others else ""
    kind = (info or {}).get("kind")
    if not kind:
        return "", "face lock skipped: no image backend"
    if family_warning:
        return "", "face lock skipped: needs an SDXL / Illustrious / Pony checkpoint"
    if kind == "forge":
        if not info.get("model"):
            return "", "face lock skipped: no face IP-Adapter in Forge's ControlNet models"
        return ref, f"face lock: {m['name']} (Forge ControlNet IP-Adapter)" + extra
    if info.get("type") not in ("plus_face", "faceid_v2"):
        return "", "face lock skipped: " + (info.get("problem") or "no Plus Face IP-Adapter in ComfyUI")
    return ref, f"face lock: {m['name']} (ComfyUI IP-Adapter Plus Face)" + extra


SDXL_FAMILIES = ("stable diffusion", "sdxl", "illustrious", "pony", "noob")


def facelock_model_warning(profile, workflow=""):
    """'' when the target model can use the SDXL face IP-Adapter, else why not. Stricter than Face Swap's check:
    the family has to be SDXL-like (MOSS, Qwen, HiDream … are not), and a ComfyUI workflow mustn't be FLUX / MOSS."""
    from .faceswap import family_warning
    w = family_warning(profile)
    if w:
        return w
    fam = ((profile or {}).get("family") or "").lower()
    if fam and not any(f in fam for f in SDXL_FAMILIES):
        return f"face lock needs an SDXL / Illustrious / Pony model (target is {profile.get('family')})"
    wf = (workflow or "").lower()
    if any(x in wf for x in ("moss", "flux", "qwen", "anima", "hidream")):
        return f"face lock needs an SDXL workflow (current: {workflow})"
    return ""
