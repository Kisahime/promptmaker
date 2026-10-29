"""Minimal Ollama client (standard library only)."""
import json
import urllib.error
import urllib.request

BASE = "http://localhost:11434"
INSTALL_HINT = ("Ollama isn't running. Start the Ollama app (or run 'ollama serve'), then click Refresh. "
                "Not installed? Get it free from https://ollama.com/download, then run 'ollama pull llama3.2'.")

BASE_SYSTEM = ("You are an expert prompt engineer for AI image generators. Target model: {name}. "
               "Guidance for this model: {guide}")

ACTIONS = {
    "Enhance": "Improve this image prompt: more vivid and effective, same intent, similar length.",
    "More detailed": "Expand this prompt with specific detail about composition, textures, lighting, colour and atmosphere.",
    "Simplify": "Rewrite this prompt short and punchy, keeping the key subject and style.",
    "Variations": "Write {n} distinct creative variations of this prompt, each changing setting, style or mood. "
                  "Output a numbered list, one prompt per line, nothing else.",
    "Fix for model": "Rewrite this prompt so it follows the target model's best practice exactly.",
}


class OllamaError(Exception):
    pass


def system_for(profile, extra=""):
    s = BASE_SYSTEM.format(name=profile["name"], guide=profile.get("ai_guidance", ""))
    lo, hi = profile.get("length", [15, 120])
    s += f" Ideal length about {lo}-{hi} words."
    return s + (" " + extra if extra else "")


def _open(req, timeout):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise OllamaError(f"Ollama error {e.code}: {e.read().decode(errors='ignore')[:300]}") from e
    except (urllib.error.URLError, OSError) as e:
        raise OllamaError(INSTALL_HINT) from e


def list_models(base=BASE, timeout=3):
    with _open(base + "/api/tags", timeout) as r:
        try:
            return [m["name"] for m in json.load(r).get("models", [])]
        except ValueError as e:
            raise OllamaError("Unexpected reply from Ollama") from e


def stream_chat(model, messages, base=BASE, temperature=0.7, json_mode=False, stop_flag=None):
    """messages: list of {role, content}. Yields text chunks."""
    payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
    if json_mode:
        payload["format"] = "json"
    req = urllib.request.Request(base + "/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with _open(req, 600) as resp:
        for line in resp:
            if stop_flag and stop_flag():
                break
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("error"):
                raise OllamaError(d["error"])
            yield d.get("message", {}).get("content", "")
            if d.get("done"):
                break


def action_messages(action, prompt, profile, n=5):
    instr = ACTIONS[action].format(n=n)
    return [{"role": "system", "content": system_for(profile, "Reply with only the prompt text, no preamble.")},
            {"role": "user", "content": f"{instr}\n\nPrompt:\n{prompt}"}]


CHAT_RULES = ("You are chatting with the user about refining their current image prompt. Be concise and practical. "
              "Whenever you propose a revised prompt, put the complete revised prompt between <prompt> and </prompt> tags "
              "(only one per reply). Keep Midjourney --parameters if the target is Midjourney.")


def chat_messages(history, current_prompt, profile):
    sys = system_for(profile, CHAT_RULES) + f"\n\nCurrent prompt:\n{current_prompt}"
    return [{"role": "system", "content": sys}] + history


def analysis_messages(prompt, categories):
    keys = ", ".join(f'"{c}"' for c in categories)
    return [{"role": "system", "content": "You analyse AI image prompts. Reply with JSON only."},
            {"role": "user", "content": f"Break this image prompt into categories. Return a JSON object with these keys: "
             f"{keys}, plus \"Extra\" for anything left over. Each value is a list of short phrases taken or "
             f"paraphrased from the prompt (empty list if absent). Artists go in \"Artist influence\" written as "
             f"'inspired by NAME'.\n\nPrompt:\n{prompt}"}]


def score_messages(prompt, profile):
    return [{"role": "system", "content": system_for(profile, "You are a strict prompt reviewer. Reply with JSON only.")},
            {"role": "user", "content": "Score this prompt for the target model, 0-10 per criterion: Clarity, Specificity, "
             "Composition, Style coherence, Model fit. Return JSON: {\"scores\": {\"Clarity\": {\"score\": n, \"why\": \"...\"}, ...}, "
             "\"fixes\": [\"concrete fix\", ...], \"improved_prompt\": \"...\"}\n\nPrompt:\n" + prompt}]


def create_messages(idea, profile, n=1, creativity=60):
    neg = profile.get("negative")
    if neg in ("supported", "optional", "limited"):
        neg_rule = ("Also write a short negative prompt for each option inside <negative></negative>"
                    + (f", based on: {profile['negative_default']}" if profile.get("negative_default", "").strip() else "") + ".")
    else:
        neg_rule = "This model has no negative prompt: do not write one; phrase exclusions positively inside the prompt."
    if profile.get("param_style") == "midjourney":
        param_rule = "Do not add --parameters; the app appends them."
    else:
        param_rule = "Do not include sizes, steps or settings in the prompt."
    level = ("Stay very close to the user's words; only fill gaps minimally." if creativity < 30 else
             "Fill vague parts with specific, fitting choices." if creativity < 70 else
             "Be bold and imaginative: invent striking, specific details for anything vague.")
    sys = system_for(profile, (
        "The user gives a rough idea. Turn it into finished, ready-to-paste prompt(s) for the target model. "
        "Whenever the idea is vague (e.g. 'an outfit', 'a setting', 'a character'), invent concrete specifics "
        f"(exact clothing, colours, place, time, lighting, camera). {level} Follow the target model's format exactly "
        f"(tags vs sentences, quality prefix, weighting rules). {neg_rule} {param_rule} "
        f"Write {n} distinct option(s). For each option output exactly: <prompt>...</prompt>"
        + ("<negative>...</negative>" if neg in ("supported", "optional", "limited") else "")
        + " and nothing else – no headings, no commentary."))
    return [{"role": "system", "content": sys}, {"role": "user", "content": f"Idea: {idea}"}]


def parse_options(text):
    import re
    blocks = re.findall(r"<prompt>(.*?)</prompt>\s*(?:<negative>(.*?)</negative>)?", text, re.S | re.I)
    opts = [{"prompt": p.strip(), "negative": (ng or "").strip()} for p, ng in blocks if p.strip()]
    if not opts and text.strip():
        opts = [{"prompt": re.sub(r"</?\w+>", "", text).strip(), "negative": ""}]
    return opts


def find_ollama_app():
    import os
    import shutil
    cands = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"),
             os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
             shutil.which("ollama") or ""]
    return next((c for c in cands if c and os.path.exists(c)), None)


def start_ollama():
    """Launch the installed Ollama (tray app, or 'ollama serve'). Returns a status string."""
    import os
    import subprocess
    exe = find_ollama_app()
    if not exe:
        raise OllamaError("Ollama isn't installed. Download it free from https://ollama.com/download.")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    if exe.lower().endswith("ollama app.exe"):
        subprocess.Popen([exe], creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([exe, "serve"], creationflags=flags | (0x08000000 if os.name == "nt" else 0),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return exe


def unload_all(base=BASE, timeout=5):
    """Ask Ollama to drop every loaded model from VRAM (keep_alive=0). Returns the names unloaded. Never raises."""
    import json as _json
    import urllib.request as _ur
    base = (base or BASE).rstrip("/")
    try:
        with _ur.urlopen(base + "/api/ps", timeout=timeout) as r:
            loaded = [m.get("name") or m.get("model") for m in (_json.loads(r.read() or b"{}").get("models") or [])]
    except Exception:  # noqa: BLE001 - Ollama not running: nothing to free
        return []
    done = []
    for name in filter(None, loaded):
        try:
            req = _ur.Request(base + "/api/generate", data=_json.dumps({"model": name, "keep_alive": 0}).encode(),
                              headers={"Content-Type": "application/json"})
            _ur.urlopen(req, timeout=max(timeout, 15)).read()
            done.append(name)
        except Exception:  # noqa: BLE001
            pass
    return done
