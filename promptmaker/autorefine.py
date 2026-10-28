"""Generate → check → refine loop: render, let a vision model score the image against the idea, rewrite, repeat."""
import base64
import json
import re

from . import ollama

JUDGE_SYSTEM = ("You are a strict art director checking whether a generated image matches the user's idea. "
                "Reply with JSON only: {\"score\": 0-100, \"matches\": [..], \"missing\": [..], \"wrong\": [..], "
                "\"advice\": \"one or two sentences on how to change the prompt\"}.")


def judge_messages(idea, prompt, image_png):
    return [{"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": f"User's idea:\n{idea}\n\nPrompt used:\n{prompt}\n\nScore how well the image matches the idea.",
             "images": [base64.b64encode(image_png).decode()]}]


def parse_judgement(text):
    """Loose JSON parse; always returns a dict with an int score 0-100."""
    d = {}
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
        except ValueError:
            d = {}
    if not isinstance(d, dict):
        d = {}
    try:
        s = float(d.get("score", 0))
    except (TypeError, ValueError):
        s = 0
    if 0 < s <= 10 and not re.search(r'"score"\s*:\s*\d{2}', text or ""):
        s *= 10  # some models answer on a 0-10 scale
    if not m:
        n = re.search(r"(\d{1,3})\s*(?:/\s*100|%)", text or "")
        s = float(n.group(1)) if n else s
    d["score"] = int(max(0, min(100, round(s))))
    for k in ("matches", "missing", "wrong"):
        v = d.get(k) or []
        d[k] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
    d["advice"] = str(d.get("advice") or "")
    return d


def rewrite_messages(idea, prompt, judgement, profile):
    fb = (f"Score {judgement['score']}/100. Missing: {', '.join(judgement['missing']) or 'nothing'}. "
          f"Wrong: {', '.join(judgement['wrong']) or 'nothing'}. Advice: {judgement['advice']}")
    return [{"role": "system", "content": ollama.system_for(profile, "Reply with only the revised prompt, no preamble.")},
            {"role": "user", "content": f"The user's idea:\n{idea}\n\nCurrent prompt:\n{prompt}\n\nReview of the image it produced:\n{fb}\n\n"
                                        "Rewrite the prompt so the next image matches the idea better. Keep what works."}]


def clean_prompt(text):
    t = re.sub(r"(?is)<think>.*?</think>", "", text or "").strip()
    m = re.search(r"<prompt>(.*?)</prompt>", t, re.S)
    t = m.group(1).strip() if m else t
    return t.strip().strip('"').strip()


def run(idea, prompt, generate, judge, rewrite, iterations=4, threshold=85, stop_flag=None, on_step=None):
    """Drive the loop with injected callables (so it is testable and UI-agnostic).

    generate(prompt) -> png bytes; judge(idea, prompt, png) -> judgement dict; rewrite(idea, prompt, judgement) -> new prompt.
    on_step(record) is called after each iteration. Returns {"steps": [...], "best": record|None, "reason": str}.
    """
    steps, reason = [], "iterations"
    for i in range(max(1, int(iterations))):
        if stop_flag and stop_flag():
            reason = "stopped"; break
        png = generate(prompt)
        if stop_flag and stop_flag():
            reason = "stopped"; break
        j = judge(idea, prompt, png)
        rec = {"i": i + 1, "prompt": prompt, "image": png, "score": j["score"], "judgement": j}
        steps.append(rec)
        if on_step:
            on_step(rec)
        if j["score"] >= threshold:
            reason = "threshold"; break
        if i + 1 < iterations:
            if stop_flag and stop_flag():
                reason = "stopped"; break
            prompt = rewrite(idea, prompt, j) or prompt
    best = max(steps, key=lambda r: (r["score"], -r["i"])) if steps else None
    return {"steps": steps, "best": best, "reason": reason}
