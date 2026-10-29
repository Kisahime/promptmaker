"""Video prompts: model profiles, camera / motion presets and an Ollama-assisted writer for Wan 2.x, LTX-Video and
HunyuanVideo. Prompt writing only – PromptMaker doesn't render video (use the prompt in ComfyUI / Wan2GP / etc.)."""
import re

MODELS = {
    "wan22": {"name": "Wan 2.2 (A14B / 5B)", "fps": 16, "frames_rule": (4, 1), "max_frames": 121, "default_secs": 5,
              "sizes": ["1280x720", "832x480", "720x1280", "480x832"], "negative": True, "words": (60, 150),
              "style": "sentences",
              "guide": "Wan prefers clear descriptive sentences in this order: subject and appearance, scene, the motion "
                       "(what moves and how), camera language (shot size, angle, movement), lighting and atmosphere, "
                       "visual style. Name camera moves explicitly (e.g. 'the camera slowly dollies in'). 80–120 words.",
              "default_negative": "static, blurry details, subtitles, text, watermark, overexposed, worst quality, low quality, "
                                  "jpeg artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, "
                                  "fused fingers, cluttered background, three legs, walking backwards, still frame"},
    "wan21": {"name": "Wan 2.1", "fps": 16, "frames_rule": (4, 1), "max_frames": 81, "default_secs": 5,
              "sizes": ["832x480", "1280x720", "480x832"], "negative": True, "words": (50, 120), "style": "sentences",
              "guide": "Wan 2.1: subject → scene → motion → camera → atmosphere/style, as plain sentences, 60–100 words.",
              "default_negative": "static, blurry, subtitles, text, watermark, worst quality, low quality, deformed, still frame"},
    "ltxv": {"name": "LTX-Video (0.9.x / 2)", "fps": 24, "frames_rule": (8, 1), "max_frames": 257, "default_secs": 5,
             "sizes": ["768x512", "1216x704", "512x768", "704x1216"], "negative": True, "words": (100, 200), "style": "paragraph",
             "guide": "LTX-Video wants one flowing, chronological paragraph under 200 words: start with the main action in a "
                      "single sentence, then specific movements and gestures, character/object appearance, background and "
                      "environment, camera angle and movement, lighting and colour, and any change or event over time. "
                      "Literal and precise, like a cinematographer's shot description.",
             "default_negative": "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, text"},
    "hunyuan": {"name": "HunyuanVideo", "fps": 24, "frames_rule": (4, 1), "max_frames": 129, "default_secs": 5,
                "sizes": ["1280x720", "960x544", "720x1280", "544x960"], "negative": False, "words": (50, 120), "style": "structured",
                "guide": "HunyuanVideo: subject, scene, motion, camera movement, atmosphere and style, as short comma-joined "
                         "clauses or two to three sentences. No negative prompt (guidance-distilled).",
                "default_negative": ""},
}

CAMERA = {
    "Static": "static camera, locked-off shot",
    "Slow push in": "the camera slowly pushes in",
    "Pull out": "the camera pulls back to reveal the scene",
    "Pan left": "the camera pans left",
    "Pan right": "the camera pans right",
    "Tilt up": "the camera tilts up",
    "Tilt down": "the camera tilts down",
    "Orbit": "the camera orbits around the subject",
    "Tracking": "tracking shot following the subject",
    "Dolly zoom": "dolly zoom (vertigo effect)",
    "Crane up": "crane shot rising upward",
    "Handheld": "handheld camera with slight natural shake",
    "FPV drone": "fast FPV drone flythrough",
    "Aerial": "aerial drone shot gliding over the scene",
}
MOTION = {
    "Subtle": "subtle, gentle movement",
    "Natural": "natural, smooth motion",
    "Dynamic": "dynamic, energetic motion",
    "Slow motion": "slow motion",
    "Timelapse": "timelapse, clouds and light moving quickly",
    "Wind & hair": "hair and clothes moving in the wind",
    "Walk cycle": "walking towards the camera",
    "Turn to camera": "turns her head toward the camera",
    "Particles": "floating particles and drifting dust",
    "Water": "rippling water and flowing waves",
}
SHOTS = ["Extreme close-up", "Close-up", "Medium close-up", "Medium shot", "Cowboy shot", "Full shot", "Wide shot",
         "Extreme wide shot", "Over-the-shoulder", "Low angle", "High angle", "Bird's-eye view"]


def frames_for(model_id, seconds, fps=None):
    """Frame count that the model accepts (4n+1 for Wan/Hunyuan, 8n+1 for LTX), clamped to its maximum."""
    m = MODELS[model_id]
    fps = fps or m["fps"]
    step, plus = m["frames_rule"]
    raw = max(1, round(float(seconds) * fps))
    n = max(step + plus, round((raw - plus) / step) * step + plus)
    n = min(n, m["max_frames"])
    return ((n - plus) // step) * step + plus


def seconds_for(model_id, frames, fps=None):
    return round(frames / float(fps or MODELS[model_id]["fps"]), 2)


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").strip()).strip(" ,.")


def compose(model_id, fields):
    """Offline structured prompt from the form fields, in the order the model prefers.
    fields: subject, action, scene, camera, motion, shot, lighting, style, extra, duration."""
    m = MODELS[model_id]
    f = {k: _clean(v) for k, v in fields.items() if isinstance(v, str)}
    cam = CAMERA.get(f.get("camera", ""), f.get("camera", ""))
    mot = MOTION.get(f.get("motion", ""), f.get("motion", ""))
    shot = f.get("shot", "")
    if m["style"] == "structured":
        parts = [f.get("subject"), f.get("action"), f.get("scene"), mot, shot.lower() if shot else "", cam, f.get("lighting"),
                 f.get("style"), f.get("extra")]
        return ", ".join(p for p in parts if p)
    sents = []
    if m["style"] == "paragraph":  # LTX: main action first, then detail, camera, light
        lead = " ".join(p for p in (f.get("subject"), f.get("action")) if p)
        if lead:
            sents.append(lead[0].upper() + lead[1:])
        if mot:
            sents.append(mot[0].upper() + mot[1:])
        if f.get("scene"):
            sents.append(f"The scene is {f['scene']}")
        if shot or cam:
            sents.append(", ".join(p for p in (f"{shot}" if shot else "", cam) if p).capitalize())
        if f.get("lighting"):
            sents.append(f"The lighting is {f['lighting']}")
        if f.get("style"):
            sents.append(f"The footage looks {f['style']}")
    else:  # Wan: subject → scene → motion → camera → atmosphere → style
        if f.get("subject"):
            sents.append(f["subject"][0].upper() + f["subject"][1:] + (f" {f['action']}" if f.get("action") else ""))
        if f.get("scene"):
            sents.append(f"Setting: {f['scene']}")
        if mot:
            sents.append(mot.capitalize())
        if shot or cam:
            sents.append(", ".join(p for p in (shot, cam) if p).capitalize())
        if f.get("lighting"):
            sents.append(f["lighting"].capitalize())
        if f.get("style"):
            sents.append(f["style"].capitalize())
    if f.get("extra"):
        sents.append(f["extra"])
    return ". ".join(s.rstrip(".") for s in sents if s) + ("." if sents else "")


def writer_messages(model_id, fields, idea=""):
    m = MODELS[model_id]
    lo, hi = m["words"]
    secs = fields.get("duration") or m["default_secs"]
    spec = "\n".join(f"- {k}: {v}" for k, v in fields.items() if v and k != "duration")
    return [{"role": "system", "content":
             f"You write text-to-video prompts for {m['name']}. {m['guide']} The clip is about {secs} seconds long, so "
             f"describe one continuous shot with motion that fits that time – no scene cuts. Aim for {lo}–{hi} words. "
             "Reply with ONLY the prompt text, no title, no quotes, no lists, no commentary."},
            {"role": "user", "content": (f"Idea: {idea}\n" if idea else "") + "Use these details:\n" + (spec or "- (none)")}]


def clean_output(text):
    t = (text or "").strip()
    m = re.search(r"<prompt>(.*?)</prompt>", t, re.S)
    if m:
        t = m.group(1)
    t = re.sub(r"^(here('| i)s|sure)[^\n:]*:\s*", "", t, flags=re.I)
    t = re.sub(r"^\**prompt\**\s*:\s*", "", t, flags=re.I)
    return t.strip().strip('"').strip()


def word_count(text):
    return len(re.findall(r"\w+", text or ""))


def check(model_id, prompt):
    """Short warnings for the chosen model (length, missing camera/motion)."""
    m, out = MODELS[model_id], []
    n = word_count(prompt)
    lo, hi = m["words"]
    if n and n < lo * 0.6:
        out.append(f"Short for {m['name']} ({n} words) – aim for {lo}–{hi}.")
    if n > hi * 1.3:
        out.append(f"Long for {m['name']} ({n} words) – it may ignore the end; aim for {lo}–{hi}.")
    low = (prompt or "").lower()
    if n and not any(w in low for w in ("camera", "shot", "pan", "tilt", "dolly", "zoom", "tracking", "orbit", "drone")):
        out.append("No camera direction – add one so the model doesn't guess.")
    return out
