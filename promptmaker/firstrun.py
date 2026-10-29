"""First-run setup checks: Ollama (installed / running / models), model pulls, Forge/A1111 and ComfyUI detection."""
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

from . import imagegen

OLLAMA_URL = "http://localhost:11434"
FORGE_URL = "http://127.0.0.1:7860"
COMFY_URL = "http://127.0.0.1:8188"
RECOMMENDED_TEXT = "llama3.2"
RECOMMENDED_VISION = "qwen2.5vl"
TEXT_FAMILIES = ("llama3", "qwen2.5", "qwen3", "gemma", "mistral", "phi", "deepseek")


class PullError(Exception):
    pass


def ollama_binary():
    """Path to the ollama executable, or "" if it can't be found."""
    p = shutil.which("ollama")
    if p:
        return p
    if sys.platform == "win32":
        cand = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
        if os.path.exists(cand):
            return cand
    for cand in ("/usr/local/bin/ollama", "/usr/bin/ollama", "/Applications/Ollama.app"):
        if os.path.exists(cand):
            return cand
    return ""


def _get(url, timeout=3):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PromptMaker"}), timeout=timeout) as r:
        return json.load(r)


def has_model(models, name):
    base = name.split(":")[0]
    return any(m == name or m.split(":")[0] == base for m in models)


def check_ollama(base=OLLAMA_URL, binary=None):
    res = {"installed": bool(binary if binary is not None else ollama_binary()), "running": False, "version": "",
           "models": [], "error": ""}
    try:
        res["models"] = [m["name"] for m in _get(base + "/api/tags").get("models", [])]
        res["running"] = res["installed"] = True
        try:
            res["version"] = str(_get(base + "/api/version").get("version", ""))
        except (OSError, ValueError, urllib.error.URLError):
            pass
    except (OSError, ValueError, urllib.error.URLError) as e:
        res["error"] = str(e)
    res["has_text"] = any(m.split(":")[0].startswith(TEXT_FAMILIES) and "vl" not in m and "vision" not in m
                          for m in res["models"])
    res["has_vision"] = has_model(res["models"], RECOMMENDED_VISION) or any(
        k in m for m in res["models"] for k in ("qwen2.5vl", "qwen3-vl", "gemma3", "llava", "minicpm-v"))
    return res


def pull(name, base=OLLAMA_URL, progress=None, stop_flag=None):
    """Stream POST /api/pull. progress(percent 0-100 or -1, status). Returns True when done, False if stopped."""
    req = urllib.request.Request(base + "/api/pull", data=json.dumps({"model": name, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=3600)
    except urllib.error.HTTPError as e:
        raise PullError(f"Ollama error {e.code}: {e.read().decode(errors='ignore')[:200]}") from e
    except (urllib.error.URLError, OSError) as e:
        raise PullError("Ollama isn't running – start it, then try again") from e
    with resp:
        for line in resp:
            if stop_flag and stop_flag():
                return False
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("error"):
                raise PullError(d["error"])
            total, done = d.get("total"), d.get("completed")
            pct = int(done * 100 / total) if total and done is not None else -1
            if progress:
                progress(pct, d.get("status", ""))
            if d.get("status") == "success":
                return True
    return True


def detect_forge(url=FORGE_URL):
    """{"found", "api", "message", "hint"}"""
    be = imagegen.A1111(url)
    try:
        return {"found": True, "api": True, "message": be.test(), "hint": ""}
    except imagegen.ApiDisabled as e:
        return {"found": True, "api": False, "message": str(e), "hint": imagegen.API_FIX}
    except imagegen.BackendError as e:
        msg = str(e)
        if msg.startswith("HTTP 404"):
            return {"found": True, "api": False, "message": "Forge/A1111 answered but /sdapi/v1 is missing",
                    "hint": imagegen.API_FIX}
        return {"found": False, "api": False, "message": msg, "hint": ""}


def detect_comfy(url=COMFY_URL):
    try:
        return {"found": True, "message": imagegen.ComfyUI(url).test()}
    except imagegen.BackendError as e:
        return {"found": False, "message": str(e)}


def run_all(ollama_url=OLLAMA_URL, forge_url=FORGE_URL, comfy_url=COMFY_URL, binary=None):
    return {"ollama": check_ollama(ollama_url, binary), "forge": detect_forge(forge_url), "comfyui": detect_comfy(comfy_url)}


def save_results(store, res, forge_url=FORGE_URL, comfy_url=COMFY_URL):
    """Persist results; pick an image backend if none is configured yet."""
    store.set("setup_results", {k: {kk: vv for kk, vv in v.items() if kk != "models"} for k, v in res.items()})
    store.set("setup_done", True)
    if store.get("img_backend", "none") == "none":
        if res["forge"].get("api"):
            store.set("img_backend", "a1111"); store.set("img_url:a1111", forge_url)
        elif res["comfyui"].get("found"):
            store.set("img_backend", "comfyui"); store.set("img_url:comfyui", comfy_url)
    return store.get("img_backend", "none")
