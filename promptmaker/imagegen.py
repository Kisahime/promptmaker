"""Image generation backends: ComfyUI (API workflows) and Forge / AUTOMATIC1111 (/sdapi/v1)."""
import base64
import copy
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

WORKFLOW_DIR = os.path.join(os.path.dirname(__file__), "workflows")
PLACEHOLDERS = ("prompt", "negative", "width", "height", "seed", "steps", "cfg", "checkpoint", "sampler", "scheduler")
NUMERIC = {"width", "height", "seed", "steps", "cfg"}


# Called (no args) right before any image is sent to a backend, e.g. to free VRAM held by Ollama.
BEFORE_GENERATE = []


def _before_generate():
    for fn in list(BEFORE_GENERATE):
        try:
            fn()
        except Exception:  # noqa: BLE001 - a hook must never block generation
            pass


class BackendError(Exception):
    pass


class Cancelled(BackendError):
    pass


def _http(url, data=None, timeout=30, raw=False, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json", "User-Agent": "PromptMaker"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
    except urllib.error.HTTPError as e:
        raise BackendError(f"HTTP {e.code} from {url}: {e.read().decode(errors='ignore')[:400]}") from e
    except (urllib.error.URLError, OSError) as e:
        raise BackendError(f"Can't reach {url} – is the backend running? ({e})") from e
    return content if raw else (json.loads(content) if content.strip() else {})


def new_seed():
    return random.randint(1, 2**32 - 1)


def inject(workflow, values):
    """Replace "{{name}}" placeholders anywhere in a ComfyUI API-format workflow.

    A string that is exactly "{{seed}}" (etc.) becomes the typed value; placeholders inside longer
    strings are substituted as text.
    """
    wf = copy.deepcopy(workflow)

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and "{{" in node:
            stripped = node.strip()
            for k in PLACEHOLDERS:
                if stripped == "{{" + k + "}}":
                    v = values.get(k, "")
                    if k in NUMERIC:
                        return float(v) if k == "cfg" else int(v)
                    return v
            for k in PLACEHOLDERS:
                node = node.replace("{{" + k + "}}", str(values.get(k, "")))
            return node
        return node
    return walk(wf)


def list_workflows(extra_dir=None):
    out = {}
    for d in [WORKFLOW_DIR] + ([extra_dir] if extra_dir else []):
        if d and os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".json"):
                    out[fn[:-5]] = os.path.join(d, fn)
    return out


def load_workflow(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("workflow", data), data.get("_meta", {})


class Job:
    def __init__(self, prompt, negative="", width=1024, height=1024, seed=None, steps=25, cfg=6.0,
                 profile="", checkpoint="", workflow="", sampler="euler", scheduler="normal", tag=""):
        self.prompt, self.negative = prompt, negative
        self.width, self.height = int(width), int(height)
        self.seed = int(seed) if seed not in (None, "", -1) else new_seed()
        self.steps, self.cfg = int(steps), float(cfg)
        self.profile, self.checkpoint, self.workflow = profile, checkpoint, workflow
        self.sampler, self.scheduler, self.tag = sampler, scheduler, tag
        self.clip_skip = None
        self.controlnet_applied = None  # True/False/None after a Forge run with ControlNet
        self.controlnet = None  # {"image": png bytes, "model": str, "weight": float} – OpenPose from the sketcher
        self.inpaint = None     # {"image": png, "mask": png (white = repaint), "denoise", "mask_blur", "only_masked", "padding", "fill"}
        self.hires = None       # Forge/A1111 hires fix: {"scale", "upscaler", "steps", "denoise"}
        self.regions = None     # {"regions": [{prompt,x,y,w,h,weight}], "mode": "forge couple"|"plain"|"comfy", "base_weight"}
        self.id = uuid.uuid4().hex[:8]

    def values(self):
        return {k: getattr(self, k) for k in PLACEHOLDERS}

    def meta(self):
        d = self.values()
        d.update(profile=self.profile, workflow=self.workflow, created=time.time())
        return d


class ComfyUI:
    name = "ComfyUI"

    def __init__(self, url="http://127.0.0.1:8188"):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._prompt_id = None

    def test(self):
        s = _http(self.url + "/system_stats", timeout=5)
        dev = (s.get("devices") or [{}])[0].get("name", "")
        ver = s.get("system", {}).get("comfyui_version", "")
        return f"ComfyUI {ver} connected" + (f" · {dev}" if dev else "")

    def checkpoints(self):
        try:
            info = _http(self.url + "/object_info/CheckpointLoaderSimple", timeout=10)
            return info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        except (BackendError, KeyError, IndexError, TypeError):
            return []

    def regional_support(self):
        return "comfy"  # ConditioningSetArea is a core node

    def upscalers(self):
        """Names for the hires-fix upscaler list: latent modes + installed upscalers (ESRGAN etc)."""
        names = []
        for path, key in (("/sdapi/v1/latent-upscale-modes", "name"), ("/sdapi/v1/upscalers", "name")):
            try:
                names += [u.get(key) for u in _http(self.url + path, timeout=8) if u.get(key) and u.get(key) != "None"]
            except (BackendError, AttributeError, TypeError):
                pass
        return list(dict.fromkeys(names)) or ["Latent", "R-ESRGAN 4x+ Anime6B", "4x-UltraSharp"]

    def controlnet_models(self):
        try:
            info = _http(self.url + "/object_info/ControlNetLoader", timeout=10)
            return info["ControlNetLoader"]["input"]["required"]["control_net_name"][0]
        except (BackendError, KeyError, IndexError, TypeError):
            return []

    def upload_image(self, png, name="promptmaker_pose.png"):
        """POST /upload/image (multipart). Returns the name ComfyUI stored it under."""
        boundary = "----PromptMaker" + uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode() + png + \
            (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.url + "/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "PromptMaker"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise BackendError(f"HTTP {e.code} uploading the pose image to ComfyUI") from e
        except (urllib.error.URLError, OSError) as e:
            raise BackendError(f"Can't reach {self.url} – is ComfyUI running? ({e})") from e
        return (d.get("subfolder") + "/" if d.get("subfolder") else "") + d.get("name", name)

    def generate(self, job, workflow, progress=None, cancelled=None, poll=0.7, timeout=1800):
        _before_generate()
        wf = inject(workflow, job.values())
        rg = getattr(job, "regions", None)
        ip = getattr(job, "inpaint", None)
        if rg or ip:
            from . import regions as _rg
            try:
                if rg and rg.get("regions"):
                    wf = _rg.add_comfy_regions(wf, rg["regions"], job.width, job.height)
                if ip and ip.get("image") and ip.get("mask"):
                    name = self.upload_image(_rg.comfy_masked_png(ip["image"], ip["mask"]), f"pm_inpaint_{job.id}.png")
                    wf = _rg.add_comfy_inpaint(wf, name, ip.get("denoise", 0.75), ip.get("mask_blur", 6))
            except ValueError as e:
                raise BackendError(str(e)) from e
        cn = getattr(job, "controlnet", None)
        if cn and cn.get("image") and cn.get("model"):
            from .pose import add_comfy_controlnet
            try:
                wf = add_comfy_controlnet(wf, self.upload_image(cn["image"], f"pm_pose_{job.id}.png"), cn["model"], cn.get("weight", 1.0))
            except ValueError as e:
                raise BackendError(str(e)) from e
        r = _http(self.url + "/prompt", {"prompt": wf, "client_id": self.client_id})
        if r.get("node_errors"):
            raise BackendError("Workflow error: " + json.dumps(r["node_errors"])[:400])
        pid = self._prompt_id = r["prompt_id"]
        start = time.time()
        while True:
            if cancelled and cancelled():
                self.cancel()
                raise Cancelled("Cancelled")
            hist = _http(f"{self.url}/history/{pid}")
            if pid in hist:
                entry = hist[pid]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    raise BackendError("ComfyUI execution error: " + (json.dumps(msgs[-1][1])[:300] if msgs else "unknown"))
                images = []
                for out in entry.get("outputs", {}).values():
                    for im in out.get("images", []):
                        if im.get("type", "output") != "output":
                            continue
                        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                    "type": im.get("type", "output")})
                        images.append(_http(f"{self.url}/view?{q}", raw=True, timeout=60))
                if images:
                    return images
                if status.get("completed"):
                    raise BackendError("Workflow finished but produced no output images (needs a SaveImage node).")
            if progress:
                try:
                    q = _http(self.url + "/queue", timeout=5)
                    running = any(item[1] == pid for item in q.get("queue_running", []))
                    pending = len(q.get("queue_pending", []))
                    progress(-1, "Generating…" if running else f"Waiting in ComfyUI queue ({pending} ahead)")
                except BackendError:
                    pass
            if time.time() - start > timeout:
                raise BackendError("Timed out waiting for ComfyUI")
            time.sleep(poll)

    def cancel(self):
        try:
            if self._prompt_id:
                _http(self.url + "/queue", {"delete": [self._prompt_id]})
            _http(self.url + "/interrupt", {})
        except BackendError:
            pass


API_DISABLED = "API not enabled"
API_FIX = "set COMMANDLINE_ARGS=--api"


class ApiDisabled(BackendError):
    """The WebUI is running (Gradio answers) but /sdapi/v1 is missing – it was started without --api."""

    def __init__(self, variant="Forge / A1111", version="", script_path=""):
        self.variant, self.version, self.script_path = variant, version, script_path
        bat = (script_path.rstrip("\\/") + "\\webui-user.bat") if script_path else "webui-user.bat"
        self.bat = bat
        super().__init__(
            f"{API_DISABLED}: {variant}{(' ' + version) if version else ''} is running, but its API is switched off "
            f"(/sdapi/v1 returns 404). Fix: open {bat}, change the line to  {API_FIX}  (keep any other flags after it, "
            "e.g. set COMMANDLINE_ARGS=--api --xformers), save, then close the Forge window and start it again.")


def webui_variant(version="", script_path="", sdapi=True):
    """Human name for an A1111-family WebUI from /internal/sysinfo 'Version' and 'Script path'."""
    v, sp = (version or "").lower(), (script_path or "").lower()
    if v.startswith("neo") or "forge-neo" in sp:
        name = "Forge Neo"
    elif "reforge" in v or "reforge" in sp:
        name = "reForge"
    elif "classic" in v or "forge-classic" in sp:
        name = "Forge Classic"
    elif v.startswith("f") or "forge" in sp:
        name = "Forge"
    elif v:
        name = "AUTOMATIC1111"
    else:
        name = "Forge / A1111"
    ver = version.split(" ", 1)[1] if v.startswith("neo ") else version
    return name, ver


class A1111:
    name = "Forge / A1111"

    def __init__(self, url="http://127.0.0.1:7860"):
        self.url = url.rstrip("/")

    def _sysinfo(self):
        try:
            d = _http(self.url + "/internal/sysinfo", timeout=8)
            return d if isinstance(d, dict) else {}
        except (BackendError, ValueError):
            return {}

    def diagnose(self):
        """Explain why /sdapi/v1 is unavailable. Raises a specific BackendError."""
        try:
            oa = _http(self.url + "/openapi.json", timeout=6)
            paths = list((oa or {}).get("paths", {}))
        except (BackendError, ValueError):
            paths = []
        if any(p.startswith("/sdapi/v1/") for p in paths):
            raise BackendError("The WebUI lists /sdapi/v1 routes but this one failed – update Forge or check its console")
        gradio = any(p in paths for p in ("/queue/join", "/info", "/config", "/internal/ping"))
        if not paths:
            try:
                _http(self.url + "/system_stats", timeout=4)
                raise BackendError("That address is ComfyUI, not Forge/A1111 – choose ComfyUI as the backend in Settings")
            except BackendError as e:
                if "ComfyUI" in str(e):
                    raise
            try:
                _http(self.url + "/API/GetNewSession", {}, timeout=4)
                raise BackendError("That address is SwarmUI, which has its own API – point PromptMaker at SwarmUI's "
                                   "ComfyUI backend instead (choose ComfyUI as the backend)")
            except BackendError as e:
                if "SwarmUI" in str(e):
                    raise
        if gradio or "/internal/sysinfo" in paths:
            si = self._sysinfo()
            name, ver = webui_variant(si.get("Version", ""), si.get("Script path", ""))
            raise ApiDisabled(name, ver, si.get("Script path", ""))
        raise BackendError(f"{self.url} answered, but it doesn't look like Forge/A1111 (no /sdapi/v1 API)")

    def _api(self, path, data=None, timeout=30):
        try:
            return _http(self.url + path, data, timeout=timeout)
        except BackendError as e:
            if str(e).startswith("HTTP 404"):
                self.diagnose()
            raise

    def test(self):
        models = self._api("/sdapi/v1/sd-models", timeout=6)
        opts = self._api("/sdapi/v1/options", timeout=6)
        si = self._sysinfo()
        name, ver = webui_variant(si.get("Version", ""), si.get("Script path", ""))
        return (f"Connected · {name}{(' ' + ver) if ver else ''} · {len(models)} checkpoint(s) · "
                f"active: {opts.get('sd_model_checkpoint', '?')}")

    def checkpoints(self):
        try:
            return [m.get("title") or m.get("model_name") for m in self._api("/sdapi/v1/sd-models", timeout=8)]
        except BackendError:
            return []

    def payload(self, job):
        p = {"prompt": job.prompt, "negative_prompt": job.negative, "width": job.width, "height": job.height,
             "seed": job.seed, "steps": job.steps, "cfg_scale": job.cfg, "sampler_name": job.sampler or "Euler a",
             "batch_size": 1, "n_iter": 1, "send_images": True, "save_images": False}
        ov = {}
        if getattr(job, "clip_skip", None):
            ov["CLIP_stop_at_last_layers"] = int(job.clip_skip)
        if job.checkpoint:
            ov["sd_model_checkpoint"] = job.checkpoint
        if ov:
            p["override_settings"] = ov
        cn = getattr(job, "controlnet", None)
        if cn and cn.get("image"):
            from .pose import add_forge_controlnet
            add_forge_controlnet(p, base64.b64encode(cn["image"]).decode(), cn.get("model", ""), cn.get("weight", 1.0))
        hr = getattr(job, "hires", None)
        if hr and not (getattr(job, "inpaint", None) or {}).get("image"):  # hires fix is txt2img only
            p.update({"enable_hr": True, "hr_scale": float(hr.get("scale", 1.5)), "hr_upscaler": hr.get("upscaler") or "Latent",
                      "hr_second_pass_steps": int(hr.get("steps", 0)), "denoising_strength": float(hr.get("denoise", 0.4)),
                      "hr_cfg": job.cfg, "hr_sampler_name": p["sampler_name"]})
            if job.checkpoint:
                p["hr_checkpoint_name"] = "Use same checkpoint"
        rg = getattr(job, "regions", None)
        if rg and rg.get("regions"):
            from . import regions as _rg
            if rg.get("mode") == _rg.FORGE_COUPLE:
                _rg.forge_couple(p, job.prompt, rg["regions"], rg.get("base_weight", 0.2), rg.get("repeat_base", True))
            else:
                p["prompt"] = _rg.plain_prompt(job.prompt, rg["regions"])
        ip = getattr(job, "inpaint", None)
        if ip and ip.get("image") and ip.get("mask"):
            from . import regions as _rg
            _rg.forge_inpaint(p, base64.b64encode(ip["image"]).decode(), base64.b64encode(ip["mask"]).decode(),
                              ip.get("denoise", 0.75), ip.get("mask_blur", 4), ip.get("only_masked", True),
                              ip.get("padding", 32), ip.get("fill", "original"))
        return p

    def regional_support(self):
        """'forge couple' if the Forge Couple extension is installed, else '' (Forge has no built-in regional prompting)."""
        from . import regions as _rg
        try:
            return _rg.detect_forge_regional(_http(self.url + "/sdapi/v1/scripts", timeout=8))
        except (BackendError, AttributeError):
            return ""

    def controlnet_models(self):
        """sd-webui-controlnet / Forge: GET /controlnet/model_list (empty if the extension API isn't there)."""
        return self.controlnet_model_info()["models"]

    def controlnet_model_info(self):
        """{'models': [exact names Forge uses], 'known': bool}. known=False means the WebUI has no ControlNet list
        API, so we can't tell what is installed (the user may type a name)."""
        try:
            d = _http(self.url + "/controlnet/model_list", timeout=8)
            return {"models": [m for m in d.get("model_list", []) if m and m != "None"], "known": True}
        except (BackendError, AttributeError):
            pass
        try:  # fallback: does the WebUI have a ControlNet script at all?
            s = _http(self.url + "/sdapi/v1/scripts", timeout=8)
            names = [n.lower() for n in (s.get("txt2img") or [])]
            if names and not any("controlnet" in n for n in names):
                return {"models": [], "known": True, "no_extension": True}
        except (BackendError, AttributeError):
            pass
        return {"models": [], "known": False}

    def generate(self, job, workflow=None, progress=None, cancelled=None, poll=0.8, timeout=1800):
        _before_generate()
        import threading
        result, err = {}, {}

        def run():
            try:
                ep = "/sdapi/v1/img2img" if (getattr(job, "inpaint", None) or {}).get("image") else "/sdapi/v1/txt2img"
                result["r"] = self._api(ep, self.payload(job), timeout=timeout)
            except BackendError as e:
                err["e"] = e
        t = threading.Thread(target=run, daemon=True)
        t.start()
        while t.is_alive():
            if cancelled and cancelled():
                self.cancel()
                t.join(10)
                raise Cancelled("Cancelled")
            if progress:
                try:
                    pr = _http(self.url + "/sdapi/v1/progress?skip_current_image=true", timeout=5)
                    progress(int(pr.get("progress", 0) * 100), f"Step {pr.get('state', {}).get('sampling_step', 0)}"
                             f"/{pr.get('state', {}).get('sampling_steps', job.steps)}")
                except BackendError:
                    pass
            t.join(poll)
        if "e" in err:
            raise err["e"]
        r = result.get("r", {})
        try:
            info = json.loads(r.get("info") or "{}")
            if info.get("seed"):
                job.seed = int(info["seed"])
        except (ValueError, TypeError):
            info = None
        if getattr(job, "controlnet", None):
            from .pose import controlnet_applied
            job.controlnet_applied = controlnet_applied(info)
        imgs = [base64.b64decode(i.split(",", 1)[-1]) for i in r.get("images", [])]
        if not imgs:
            raise BackendError("Backend returned no images")
        return imgs

    def cancel(self):
        try:
            _http(self.url + "/sdapi/v1/interrupt", {})
        except BackendError:
            pass


def make_backend(kind, url):
    return ComfyUI(url) if kind == "comfyui" else A1111(url)
