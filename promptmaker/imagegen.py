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

    def generate(self, job, workflow, progress=None, cancelled=None, poll=0.7, timeout=1800):
        wf = inject(workflow, job.values())
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


class A1111:
    name = "Forge / A1111"

    def __init__(self, url="http://127.0.0.1:7860"):
        self.url = url.rstrip("/")

    def test(self):
        models = _http(self.url + "/sdapi/v1/sd-models", timeout=6)
        opts = _http(self.url + "/sdapi/v1/options", timeout=6)
        return f"Connected · {len(models)} checkpoint(s) · active: {opts.get('sd_model_checkpoint', '?')}"

    def checkpoints(self):
        try:
            return [m.get("title") or m.get("model_name") for m in _http(self.url + "/sdapi/v1/sd-models", timeout=8)]
        except BackendError:
            return []

    def payload(self, job):
        p = {"prompt": job.prompt, "negative_prompt": job.negative, "width": job.width, "height": job.height,
             "seed": job.seed, "steps": job.steps, "cfg_scale": job.cfg, "sampler_name": job.sampler or "Euler a",
             "batch_size": 1, "n_iter": 1, "send_images": True, "save_images": False}
        if getattr(job, "clip_skip", None):
            p["override_settings"] = {"CLIP_stop_at_last_layers": int(job.clip_skip)}
        if job.checkpoint:
            p["override_settings"] = {"sd_model_checkpoint": job.checkpoint}
        return p

    def generate(self, job, workflow=None, progress=None, cancelled=None, poll=0.8, timeout=1800):
        import threading
        result, err = {}, {}

        def run():
            try:
                result["r"] = _http(self.url + "/sdapi/v1/txt2img", self.payload(job), timeout=timeout)
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
            pass
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
