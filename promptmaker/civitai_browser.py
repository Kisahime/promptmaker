"""5.2 Civitai model browser – the non-Qt half: search parameters, NSFW filtering, file / destination mapping,
resumable SHA256-verified downloads and model-profile building from a version.

Uses the public REST API v1 (/models, /model-versions/{id}); see civitai.py for the polite cached client.
"""
import hashlib
import html
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import civitai
from .civitai import CivitaiError

TYPES = [("All types", ""), ("Checkpoint", "Checkpoint"), ("LoRA", "LORA"), ("LoCon / LyCORIS", "LoCon"), ("DoRA", "DoRA"),
         ("Embedding", "TextualInversion"), ("VAE", "VAE"), ("ControlNet", "Controlnet"), ("Upscaler", "Upscaler"),
         ("Hypernetwork", "Hypernetwork"), ("Motion module", "MotionModule"), ("Workflow", "Workflows")]
BASE_MODELS = ["SDXL 1.0", "Pony", "Illustrious", "NoobAI", "Anima", "MOSS Image", "Flux.1 D", "Flux.1 S", "Flux.1 Kontext",
               "Flux.2 D", "Qwen", "HiDream", "SD 1.5", "SD 3.5", "Wan Video 2.2 I2V-A14B", "Wan Video 2.2 T2V-A14B"]
SORTS = ["Highest Rated", "Most Downloaded", "Newest"]
PERIODS = [("All time", "AllTime"), ("Year", "Year"), ("Month", "Month"), ("Week", "Week"), ("Day", "Day")]
HOSTS = ["civitai.com", "civitai.red"]
BROWSE_TTL = 15 * 60  # search pages change quickly; model-versions are still cached 24 h by the profile importer


def api_base(host):
    host = (host or "civitai.com").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    return f"https://{host.split('/')[0]}/api/v1"


def host_of(api):
    return urllib.parse.urlparse(api or civitai.API).hostname or "civitai.com"


# ---------------------------------------------------------------- search
def search_params(query="", types=(), base_models=(), sort="Highest Rated", period="AllTime", nsfw=False, limit=24, cursor=None):
    """Query for GET /models as a list of pairs (types / baseModels repeat). Civitai only supports cursor paging
    together with a text query, so `page` is never sent."""
    p = [("limit", int(limit)), ("sort", sort or "Highest Rated"), ("period", period or "AllTime"),
         ("nsfw", "true" if nsfw else "false")]
    if (query or "").strip():
        p.append(("query", query.strip()))
    for t in [types] if isinstance(types, str) else types or ():
        if t:
            p.append(("types", t))
    for b in [base_models] if isinstance(base_models, str) else base_models or ():
        if b:
            p.append(("baseModels", b))
    if cursor:
        p.append(("cursor", cursor))
    return p


def search(client, **kw):
    """→ (items, next_cursor). Items are already NSFW-filtered when kw['nsfw'] is false."""
    d = client.get("/models", search_params(**kw))
    items = d.get("items") or []
    meta = d.get("metadata") or {}
    cur = meta.get("nextCursor")
    if not cur and meta.get("nextPage"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(meta["nextPage"]).query)
        cur = (q.get("cursor") or [None])[0]
    return filter_models(items, kw.get("nsfw", False)), cur


def image_safe(img):
    """Safe-for-work preview: nsfwLevel 1 (PG). Unknown levels count as unsafe."""
    lvl = img.get("nsfwLevel")
    if isinstance(lvl, (int, float)):
        return lvl <= 1
    old = img.get("nsfw")
    return old in (False, "None", "none")


def safe_images(images, nsfw=False):
    out = [i for i in images or [] if isinstance(i, dict) and i.get("url")]
    return out if nsfw else [i for i in out if image_safe(i)]


def filter_models(items, nsfw=False):
    """With NSFW off, drop models flagged nsfw and strip every preview above nsfwLevel 1 (kept as `_hidden`)."""
    out = []
    for m in items or []:
        if not nsfw and m.get("nsfw") is True:
            continue
        m = dict(m)
        vs = []
        for v in m.get("modelVersions") or []:
            v = dict(v); imgs = v.get("images") or []
            v["images"] = safe_images(imgs, nsfw); v["_hidden"] = int(v.get("_hidden") or 0) + len(imgs) - len(v["images"])
            vs.append(v)
        m["modelVersions"] = vs
        out.append(m)
    return out


def thumb_url(url, width=320):
    if not url:
        return ""
    if re.search(r"/width=\d+/", url):
        return re.sub(r"/width=\d+/", f"/width={width}/", url)
    if "image.civitai.com" in url or "imagecache" in url:
        base, _, name = url.rpartition("/")
        return f"{base}/width={width}/{name}"
    return url


def card(m):
    """What a result card shows."""
    v = (m.get("modelVersions") or [{}])[0]
    imgs = [i for i in v.get("images") or [] if (i.get("type") or "image") == "image"]
    st = m.get("stats") or {}
    return {"id": m.get("id"), "name": m.get("name") or "?", "creator": (m.get("creator") or {}).get("username") or "?",
            "type": m.get("type") or "", "base": v.get("baseModel") or "", "downloads": int(st.get("downloadCount") or 0),
            "likes": int(st.get("thumbsUpCount") or st.get("favoriteCount") or 0),
            "thumb": thumb_url(imgs[0]["url"]) if imgs else "", "hidden": v.get("_hidden", 0),
            "early_access": early_access(v)}


def _parse_dt(s):
    if not s:
        return None
    try:
        import datetime as _dt
        d = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _num(x):
    try:
        n = int(float(x))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def early_access(version, now=None):
    """Early Access / paid-access info for a model version, or None when it's free to download.
    Civitai API v1 signals: availability == "EarlyAccess", earlyAccessEndsAt / earlyAccessDeadline (ISO),
    earlyAccessConfig {timeframe (days), chargeForDownload, downloadPrice (Buzz), donationGoal…}, and
    paidAccess {permanent, endsAt} (newer field). Returns {"ends": aware datetime|None, "price": int|None,
    "permanent": bool}."""
    import datetime as _dt
    v = version or {}
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cfg = v.get("earlyAccessConfig") if isinstance(v.get("earlyAccessConfig"), dict) else {}
    pa = v.get("paidAccess") if isinstance(v.get("paidAccess"), dict) else None
    flagged = (str(v.get("availability") or "").lower() == "earlyaccess" or bool(cfg) or pa is not None
               or bool(v.get("earlyAccessEndsAt") or v.get("earlyAccessDeadline")))
    if not flagged:
        return None
    ends = _parse_dt(v.get("earlyAccessEndsAt") or v.get("earlyAccessDeadline") or (pa or {}).get("endsAt"))
    if ends is None and _num(cfg.get("timeframe")):
        pub = _parse_dt(v.get("publishedAt"))
        if pub:
            ends = pub + _dt.timedelta(days=_num(cfg.get("timeframe")))
    permanent = bool((pa or {}).get("permanent")) and ends is None
    if ends is not None and ends <= now:
        return None  # early access is over – free now
    if ends is None and not permanent and str(v.get("availability") or "").lower() != "earlyaccess" and not cfg:
        return None
    price = _num(cfg.get("downloadPrice") or cfg.get("price")) if cfg.get("chargeForDownload", True) else None
    return {"ends": ends, "price": price, "permanent": permanent}


def local_date(d):
    return d.astimezone().strftime("%d %b %Y, %H:%M") if d else ""


def early_access_text(info):
    if not info:
        return ""
    if info["permanent"]:
        s = "Paid access: this version must be unlocked with Buzz on Civitai (no free date)"
    elif info["ends"]:
        s = f"Early Access: free from {local_date(info['ends'])}"
    else:
        s = "Early Access: not free to download yet"
    if info["price"]:
        s += f" (or costs {info['price']:,} Buzz to unlock now)"
    elif not info["permanent"]:
        s += " (or unlock it now with Buzz on Civitai)"
    return s


def latest_free_version(model, now=None):
    """The newest version that isn't early access (versions are listed newest first)."""
    return next((v for v in (model or {}).get("modelVersions") or [] if not early_access(v, now)), None)


def early_access_error(err, info=None):
    """Turn a 401/403 'early access' refusal into a friendly message; returns err unchanged otherwise."""
    m = re.search(r"Server said: “(.*?)”", err or "")
    low = (m.group(1) if m else "").lower()
    ea_server = any(k in low for k in ("early access", "earlyaccess", "buzz"))
    refused = bool(re.search(r"HTTP 40[13]", err or ""))
    if not (ea_server or (info and refused)):
        return err
    when = f" It becomes free on {local_date(info['ends'])}." if info and info.get("ends") else ""
    price = f" Unlocking it now costs {info['price']:,} Buzz on Civitai." if info and info.get("price") else \
        " You can unlock it now with Buzz on Civitai."
    return ("This version is in Civitai Early Access, so it can't be downloaded for free yet." + when + price +
            " Or pick an older free version.")


def short_count(n):
    n = int(n or 0)
    for div, suf in ((1_000_000, "M"), (1_000, "k")):
        if n >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suf
    return str(n)


def human_size(b):
    b = float(b or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{b:.0f} {unit}" if unit in ("B", "KB") else f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} GB"


# ---------------------------------------------------------------- version / files
def files(version):
    out = []
    for f in version.get("files") or []:
        if not isinstance(f, dict):
            continue
        md = f.get("metadata") or {}
        out.append({"id": f.get("id"), "name": f.get("name") or f"file_{f.get('id')}", "size": int(float(f.get("sizeKB") or 0) * 1024),
                    "fp": md.get("fp") or "", "format": md.get("format") or "", "pruned": md.get("size") or "",
                    "type": f.get("type") or "Model", "primary": bool(f.get("primary")),
                    "url": f.get("downloadUrl") or f"{civitai.API}/download/models/{version.get('id')}",
                    "sha256": ((f.get("hashes") or {}).get("SHA256") or "").lower()})
    out.sort(key=lambda f: (not f["primary"], f["type"] != "Model"))
    return out


def file_label(f):
    bits = [f["name"], human_size(f["size"])]
    bits += [x for x in (f["fp"], f["pruned"], f["format"]) if x]
    if f["type"] not in ("Model", ""):
        bits.append(f["type"])
    return " · ".join(bits)


_ALLOWED = {"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "h1", "h2", "h3", "h4", "code", "pre", "blockquote", "a", "hr"}


def sanitize_html(s):
    """Creator descriptions → safe rich text: no scripts, styles, iframes, images (no remote loads), handlers or
    non-http links."""
    s = re.sub(r"(?is)<(script|style|iframe|object|embed|svg|math)\b.*?</\1\s*>", "", s or "")
    s = re.sub(r"(?is)<!--.*?-->", "", s)

    def tag(m):
        close, name, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if name not in _ALLOWED:
            return ""
        if close:
            return f"</{name}>"
        if name == "a":
            h = re.search(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.I)
            href = html.unescape(next((g for g in h.groups() if g is not None), "")) if h else ""
            if re.match(r"(?i)^https?://", href):
                return f'<a href="{html.escape(href, quote=True)}">'
            return "<a>"
        return f"<{name}>"
    return re.sub(r"<\s*(/?)\s*([a-zA-Z0-9]+)([^>]*)>", tag, s).strip()


def plain_text(s):
    return "\n".join(ln for ln in civitai.html_to_lines(s) if ln)


def author_settings(model, version):
    """Settings the creator wrote in the description (steps, CFG, sampler …) as a short line."""
    d = civitai.parse_description(version.get("description") or "")
    for k, v in civitai.parse_description(model.get("description") or "").items():
        d.setdefault(k, v)
    out = []
    for key, lab in (("steps_text", "Steps"), ("cfg_text", "CFG"), ("sampler", "Sampler"), ("scheduler", "Scheduler"),
                     ("clip_skip", "Clip skip"), ("resolution", "Resolution")):
        if d.get(key):
            out.append(f"{lab} {d[key]}")
    return " · ".join(out)


def web_url(host, model_id, version_id=None):
    return f"https://{host or 'civitai.com'}/models/{model_id}" + (f"?modelVersionId={version_id}" if version_id else "")


# ---------------------------------------------------------------- destinations
# family key → (diffusion-model params in billions, text-encoder params in billions) – used to tell a UNet/DiT-only file
# from an all-in-one checkpoint by its size.
UNET_FAMILIES = {"moss": (4.7, 9.0), "anima": (2.9, 0.6), "flux": (12.0, 4.9), "qwen": (20.0, 7.0),
                 "hidream": (17.0, 8.0), "wan": (14.0, 5.7)}
BPP = {"fp32": 4.0, "fp16": 2.0, "bf16": 2.0, "fp8": 1.0, "int8": 1.0, "nf4": 0.55, "q8": 1.06, "q6": 0.82, "q5": 0.69, "q4": 0.56}


def unet_family(base_model):
    b = (base_model or "").lower()
    return next((k for k in UNET_FAMILIES if k in b), None)


def is_unet_only(f, base_model):
    """True when a checkpoint of a DiT family (MOSS, Anima, FLUX, Qwen, HiDream, Wan) is only the diffusion model and
    belongs in ComfyUI's diffusion_models: GGUF files, names saying unet/dit/transformer, or a size below
    'diffusion model + half the text encoder' at the file's precision."""
    fam = unet_family(base_model)
    if not fam:
        return False
    name = (f.get("name") or "").lower()
    if (f.get("format") or "").lower() == "gguf" or name.endswith(".gguf"):
        return True
    if re.search(r"(aio|all[-_ ]?in[-_ ]?one|full[-_ ]?checkpoint)", name):
        return False
    if re.search(r"(unet|_dit|transformer|diffusion[-_ ]?model)", name):
        return True
    params, te = UNET_FAMILIES[fam]
    fp = (f.get("fp") or "").lower() or next((k for k in BPP if k in name), "")
    size_gb = (f.get("size") or 0) / 1e9
    if not size_gb:
        return True
    bpp = BPP.get(fp) or (2.0 if size_gb > params * 1.5 else 1.0)
    return size_gb < params * bpp + 0.5 * te * bpp


# Civitai type → (Forge sub-folder relative to the Forge root, ComfyUI sub-folder of models/)
TYPE_DIRS = {"Checkpoint": ("models/Stable-diffusion", "checkpoints"), "LORA": ("models/Lora", "loras"),
             "LoCon": ("models/Lora", "loras"), "DoRA": ("models/Lora", "loras"), "VAE": ("models/VAE", "vae"),
             "Controlnet": ("models/ControlNet", "controlnet"), "TextualInversion": ("embeddings", "embeddings"),
             "Upscaler": ("models/ESRGAN", "upscale_models"), "Hypernetwork": ("models/hypernetworks", "hypernetworks"),
             "MotionModule": (None, "animatediff_models")}


def comfy_models_dir(comfy_dir):
    """Accept the portable root, its ComfyUI folder or the models folder itself."""
    if not comfy_dir:
        return ""
    d = os.path.normpath(comfy_dir)
    if os.path.basename(d).lower() == "models":
        return d
    for cand in (os.path.join(d, "ComfyUI", "models"), os.path.join(d, "models")):
        if os.path.isdir(cand):
            return cand
    return os.path.join(d, "models")


def guess_comfy_dir():
    for d in (r"C:\AI\ComfyUI\ComfyUI_windows_portable\ComfyUI", r"C:\AI\ComfyUI_windows_portable\ComfyUI", r"C:\AI\ComfyUI",
              os.path.expanduser("~/ComfyUI")):
        if os.path.isdir(os.path.join(d, "models")):
            return d
    return ""


def _j(root, rel):
    return os.path.join(root, *rel.split("/"))


def destinations(model_type, base_model, f, forge_dir="", comfy_dir="", prefer="forge", fallback=""):
    """Ordered [(label, folder)] for a file, best first. `prefer` is the active backend ('forge' or 'comfyui')."""
    forge, comfy = [], []
    cm = comfy_models_dir(comfy_dir)
    if model_type == "Checkpoint" and is_unet_only(f, base_model):
        if cm:
            comfy.append(("ComfyUI diffusion_models (diffusion model only)", os.path.join(cm, "diffusion_models")))
            comfy.append(("ComfyUI checkpoints", os.path.join(cm, "checkpoints")))
        if forge_dir:
            forge.append(("Forge models\\Stable-diffusion", _j(forge_dir, "models/Stable-diffusion")))
        order = comfy + forge  # Forge Classic can't load these – ComfyUI first regardless of the active backend
    else:
        fd, cd = TYPE_DIRS.get(model_type, (None, None))
        if fd and forge_dir:
            forge.append((f"Forge {fd.replace('/', chr(92))}", _j(forge_dir, fd)))
        if cd and cm:
            comfy.append((f"ComfyUI {cd}", os.path.join(cm, cd)))
        order = comfy + forge if prefer == "comfyui" else forge + comfy
    if fallback:
        order.append(("PromptMaker downloads folder", fallback))
    return order


# ---------------------------------------------------------------- download
class Cancelled(Exception):
    pass


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Civitai redirects downloads to a signed storage URL; never forward the API key to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            for k in list(new.headers):
                if k.lower() == "authorization":
                    del new.headers[k]
            new.unredirected_hdrs.pop("Authorization", None)
            new.full_url = strip_token(new.full_url)
        return new


CIVITAI_HOSTS = ("civitai.com", "civitai.red")


def _is_civitai(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(h == c or h.endswith("." + c) for c in CIVITAI_HOSTS)


def strip_token(url):
    """Remove any token= query parameter (used for logging and cross-host redirects)."""
    u = urllib.parse.urlsplit(url)
    if "token=" not in u.query:
        return url
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k.lower() != "token"]
    return urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(q)))


def with_token(url, api_key):
    """Civitai's documented download auth: ?token=<key> on the /api/download URL. Only added for Civitai hosts."""
    url = strip_token(url)
    if not api_key or not _is_civitai(url):
        return url
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True) + [("token", api_key)]
    return urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(q)))


def download_url(file_url, host="civitai.com"):
    """Point a file's downloadUrl at the chosen Civitai host (only Civitai hosts are rewritten)."""
    u = urllib.parse.urlsplit(file_url)
    if _is_civitai(file_url) and host in CIVITAI_HOSTS:
        u = u._replace(scheme="https", netloc=host)
    return urllib.parse.urlunsplit(u)


def _err_detail(e):
    try:
        body = e.read(2000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    try:
        import json as _json
        d = _json.loads(body)
        return str(d.get("message") or d.get("error") or "")[:200]
    except Exception:  # noqa: BLE001
        return ""


def default_opener(req, timeout):
    return urllib.request.build_opener(_StripAuthOnRedirect).open(req, timeout=timeout)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def safe_name(name):
    n = os.path.basename((name or "").replace("\\", "/"))
    n = re.sub(r'[<>:"|?*\x00-\x1f]', "_", n).strip(" .")
    return n or "download.safetensors"


def download(url, dest, api_key="", sha256="", progress=None, cancel=None, opener=default_opener, timeout=30,
             chunk=1 << 20, retries=3, user_agent=civitai.UA):
    """Like _download, but if a civitai.red download is refused (401/403) retry once via civitai.com
    (same accounts and API keys)."""
    api_key = (api_key or "").strip()
    kw = dict(api_key=api_key, sha256=sha256, progress=progress, cancel=cancel, opener=opener, timeout=timeout,
              chunk=chunk, retries=retries, user_agent=user_agent)
    try:
        return _download(url, dest, **kw)
    except AuthError:
        if urllib.parse.urlparse(url).hostname == "civitai.red":
            return _download(download_url(url, "civitai.com"), dest, **kw)
        raise


class AuthError(CivitaiError):
    pass


def _download(url, dest, api_key="", sha256="", progress=None, cancel=None, opener=default_opener, timeout=30,
              chunk=1 << 20, retries=3, user_agent=civitai.UA):
    """Download to dest (via dest.part, resumed with a Range request), verify SHA256, then move into place.
    progress(done, total); cancel is a threading.Event – on cancel the .part is kept for resuming."""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    attempt = 0
    while True:
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"User-Agent": user_agent}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            r = opener(urllib.request.Request(with_token(url, api_key), headers=headers), timeout)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # already complete
                break
            if e.code in (401, 403):
                where = urllib.parse.urlparse(getattr(e, "url", None) or getattr(e, "filename", None) or url).hostname or "?"
                detail = _err_detail(e)
                detail = f" Server said: “{detail}”." if detail else ""
                if not api_key:
                    msg = (f"Civitai needs you to be signed in for this download (HTTP {e.code}, no API key was sent).{detail} "
                           "Add your Civitai API key in Settings → Civitai (civitai.com/user/account → API Keys).")
                elif e.code == 401:
                    msg = (f"Civitai rejected your API key (HTTP 401 from {where}; a key was sent).{detail} Check the key in "
                           "Settings → Civitai – it may have been deleted or mistyped; create a new one at civitai.com/user/account.")
                else:
                    msg = (f"Civitai refused this download even with your API key (HTTP 403 from {where}; a key was sent).{detail} "
                           "It may be early access, need you to accept the model's terms on the website, or be restricted "
                           "for your account or region. Try downloading it once in your browser.")
                raise AuthError(msg) from e
            if e.code == 404:
                raise CivitaiError("Civitai: file not found (HTTP 404)") from e
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                attempt += 1
                ra = (e.headers or {}).get("Retry-After", "") if e.headers else ""
                time.sleep(min(float(ra) if str(ra).replace(".", "").isdigit() else 2.0 * attempt, 30)); continue
            raise CivitaiError(f"Civitai download failed (HTTP {e.code})") from e
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            if attempt < retries and not (cancel and cancel.is_set()):
                attempt += 1; time.sleep(min(2.0 * attempt, 10)); continue
            raise CivitaiError(f"Can't reach Civitai – check your connection ({e}). Download again to resume.") from e
        with r:
            code = getattr(r, "status", None) or r.getcode()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise CivitaiError("Civitai returned a web page instead of the file – this download probably needs a "
                                   "Civitai API key (Settings → Civitai).")
            if have and code != 206:  # server ignored the range: start over
                have = 0
            total = r.headers.get("Content-Length")
            total = int(total) + have if total and str(total).isdigit() else 0
            done = have
            try:
                with open(part, "ab" if have else "wb") as out:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise Cancelled("Download cancelled – download again to resume")
                        b = r.read(chunk)
                        if not b:
                            break
                        out.write(b); done += len(b)
                        if progress:
                            progress(done, total)
            except (socket.timeout, OSError) as e:
                if attempt < retries:
                    attempt += 1; continue
                raise CivitaiError(f"Download interrupted ({e}). Download again to resume.") from e
            if total and done < total:
                if attempt < retries:
                    attempt += 1; continue
                raise CivitaiError("Download ended early. Download again to resume.")
        break
    if sha256:
        got = sha256_file(part)
        if got.lower() != sha256.lower():
            os.remove(part)
            raise CivitaiError(f"SHA256 mismatch – the file was corrupted and has been deleted (expected {sha256[:12]}…, got {got[:12]}…)")
    os.replace(part, dest)
    return dest


# ---------------------------------------------------------------- profile
SCHEDULERS = ("karras", "exponential", "sgm_uniform", "simple", "beta", "normal", "ddim_uniform")
FAMILY_SCHEDULER = {"MOSS": "simple", "Anima": "simple", "FLUX": "simple", "Qwen": "simple", "HiDream": "simple"}
FAMILY_WORKFLOW = {"MOSS": "moss_txt2img"}


def map_sampler(text, family=""):
    """Creator sampler text → (comfy sampler, scheduler, Forge name). Raw ComfyUI names pass through."""
    t = (text or "").strip()
    low = t.lower()
    raw = re.match(r"^([a-z0-9_]+)(?:\s*[/+,]\s*|\s+)?([a-z_]+)?", low)
    if raw and "_" in raw.group(1):
        sampler = raw.group(1)
    else:
        sampler, _ = civitai.comfy_sampler(t)
    sched = next((s for s in SCHEDULERS if re.search(rf"\b{s}\b", low)), None) or FAMILY_SCHEDULER.get(family) or \
        (civitai.comfy_sampler(t)[1] if sampler else None)
    forge = civitai.a1111_sampler(t)
    if sampler and "_" in sampler:
        forge = {"dpmpp_2m_sde_gpu": "DPM++ 2M SDE", "dpmpp_2m_sde": "DPM++ 2M SDE", "dpmpp_2m": "DPM++ 2M",
                 "euler_ancestral": "Euler a", "dpmpp_sde": "DPM++ SDE", "er_sde": "Er SDE", "res_multistep": "Res Multistep"}.get(sampler, forge)
    forge = re.sub(r"(?i)\s+(karras|simple|beta|normal|exponential)$", "", forge or "").strip()
    return sampler, sched, forge


def build_profile(model, version, file, profiles_by_id, host="civitai.com"):
    """Model profile (id civitai_<versionId>) for a downloaded file, from the browser's version data."""
    info = {"model": model, "version": version, "images": [i for i in version.get("images") or [] if i.get("meta")],
            "url": web_url(host, model.get("id") or version.get("modelId"), version.get("id"))}
    s = civitai.suggest(info)
    base_id = civitai.base_profile_id(version.get("baseModel"), profiles_by_id)
    prof = civitai.build_profile(info, s, base_id, profiles_by_id)
    base = profiles_by_id.get(base_id) or {}
    fam = base.get("family", "")
    prof["family"] = fam or prof.get("family")
    gen = prof.setdefault("gen", {})
    if s.get("sampler"):
        cs, sch, forge = map_sampler(s["sampler"], fam)
        gen.update({k: v for k, v in (("sampler", cs), ("scheduler", s.get("scheduler") or sch), ("a1111_sampler", forge)) if v})
    elif fam in FAMILY_SCHEDULER and base.get("gen", {}).get("scheduler") is None:
        gen.setdefault("scheduler", FAMILY_SCHEDULER[fam])
    if FAMILY_WORKFLOW.get(fam):
        gen["workflow"] = FAMILY_WORKFLOW[fam]
    if base.get("resolutions") and "resolutions" not in prof:
        prof["resolutions"] = dict(base["resolutions"])
    unet = (model.get("type") == "Checkpoint") and is_unet_only(file, version.get("baseModel"))
    prof["civitai"].update(file_name=file.get("name"), type="Diffusion model" if unet else (model.get("type") or "Checkpoint"),
                           model_name=model.get("name") or prof["civitai"].get("model_name"))
    prof["tips"] = [t for t in prof.get("tips", []) if "(n/a)" not in t]
    if author_settings(model, version):
        prof["tips"].insert(0, "Creator's settings: " + author_settings(model, version) + ".")
    if FAMILY_WORKFLOW.get(fam):
        prof["tips"].insert(0, f"Use the {FAMILY_WORKFLOW[fam]} ComfyUI workflow; it does not run in Forge.")
    return prof
