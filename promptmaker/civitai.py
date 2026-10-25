"""Civitai import: checkpoint-specific prompt guidance from the public REST API.

Docs: https://github.com/civitai/civitai/wiki/REST-API-Reference  (endpoints used: /models/{id}, /model-versions/{id}, /images)
civitai.com and its sister domains (civitai.red, civitai.green …) serve the same API and the same IDs.
"""
import hashlib
import html
import json
import os
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from . import __version__

API = "https://civitai.com/api/v1"
UA = f"PromptMaker/{__version__} (+https://github.com/Kisahime/promptmaker)"
CACHE_TTL = 24 * 3600


class CivitaiError(Exception):
    pass


# ---------------------------------------------------------------- references
def parse_ref(text):
    """Return (model_id, version_id) from a Civitai URL (any civitai.* domain), 'v123' / 'version:123'
    (version id), a bare number (model id), or an AIR like urn:air:sdxl:checkpoint:civitai:123@456."""
    t = (text or "").strip()
    if not t:
        raise CivitaiError("Paste a Civitai model URL or ID")
    m = re.search(r"civitai:(\d+)@(\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"(?:v|version|versionid|modelversionid)[\s:=#]*(\d+)", t, re.I)
    if m:
        return None, int(m.group(1))
    if t.isdigit():
        return int(t), None
    if "://" not in t:
        t = "https://" + t
    u = urllib.parse.urlparse(t)
    host = (u.hostname or "").lower()
    if not re.search(r"(^|\.)civitai\.[a-z]+$", host):
        raise CivitaiError(f"{host or t} isn't a Civitai address")
    q = urllib.parse.parse_qs(u.query)
    vid = int(q["modelVersionId"][0]) if q.get("modelVersionId", [""])[0].isdigit() else None
    mm = re.search(r"/models/(\d+)", u.path)
    mv = re.search(r"/(?:api/download/models|model-versions)/(\d+)", u.path)
    if mv:
        return None, int(mv.group(1))
    if mm or vid:
        return (int(mm.group(1)) if mm else None), vid
    raise CivitaiError("Couldn't find a model or version ID in that link")


# ---------------------------------------------------------------- client
class Client:
    """Tiny polite client: one request at a time, spaced out, cached on disk, backs off on HTTP 429."""

    def __init__(self, api_key="", cache_dir=None, base=API, min_interval=0.6, ttl=CACHE_TTL, timeout=20):
        self.key, self.cache_dir, self.base = api_key or "", cache_dir, base.rstrip("/")
        self.min_interval, self.ttl, self.timeout = min_interval, ttl, timeout
        self._lock, self._last = threading.Lock(), 0.0
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, url):
        # the key changes what's visible (NSFW / gated), so it is part of the cache key
        h = hashlib.sha256((url + "|" + hashlib.sha256(self.key.encode()).hexdigest()).encode()).hexdigest()[:24]
        return os.path.join(self.cache_dir, h + ".json") if self.cache_dir else None

    def get(self, path, params=None, force=False):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        cp = self._cache_path(url)
        if cp and not force and os.path.exists(cp) and time.time() - os.path.getmtime(cp) < self.ttl:
            try:
                with open(cp, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        headers = {"User-Agent": UA, "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        for attempt in range(3):
            with self._lock:
                wait = self.min_interval - (time.time() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=self.timeout) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    ra = e.headers.get("Retry-After", "")
                    time.sleep(min(float(ra) if ra.replace(".", "").isdigit() else 2.0 * (attempt + 1), 30))
                    continue
                body = e.read().decode(errors="ignore")[:200]
                if e.code in (401, 403):
                    raise CivitaiError(f"Civitai refused access (HTTP {e.code}). This model may be gated or NSFW – "
                                       "add a Civitai API key in Settings.") from e
                if e.code == 404:
                    raise CivitaiError("Civitai: not found – check the link or ID") from e
                raise CivitaiError(f"Civitai HTTP {e.code}: {body}") from e
            except (urllib.error.URLError, OSError, ValueError) as e:
                raise CivitaiError(f"Can't reach Civitai ({e})") from e
        else:
            raise CivitaiError("Civitai rate limit – try again in a minute")
        if cp:
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(data, f)
        return data


def fetch(ref, client, force=False, images=40):
    """Everything needed for a profile: {"model", "version", "images", "url"}."""
    mid, vid = parse_ref(ref) if not isinstance(ref, tuple) else ref
    version = client.get(f"/model-versions/{vid}", force=force) if vid else None
    mid = mid or (version or {}).get("modelId")
    model = client.get(f"/models/{mid}", force=force) if mid else {}
    if not version:
        vs = model.get("modelVersions") or []
        if not vs:
            raise CivitaiError("That model has no versions")
        version = vs[0]
    # model-versions/{id} has no description on some models; the model's version list sometimes does
    for v in model.get("modelVersions") or []:
        if v.get("id") == version.get("id") and not version.get("description"):
            version["description"] = v.get("description")
    imgs = []
    if images:
        try:
            d = client.get("/images", {"modelVersionId": version["id"], "limit": images, "sort": "Most Reactions"}, force=force)
            imgs = d.get("items", [])
        except CivitaiError:
            imgs = []
    url = f"https://civitai.com/models/{mid}?modelVersionId={version['id']}"
    return {"model": model, "version": version, "images": imgs, "url": url}


# ---------------------------------------------------------------- description parsing
def html_to_lines(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s or "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</?(p|div|pre|li|ul|ol|h\d|blockquote|tr|table)[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return [ln.strip() for ln in s.replace("\r", "").split("\n")]


_POS = re.compile(r"^(?:recommended\s+)?(?:positive(?:\s+prompts?)?|quality\s+(?:tags|prompts?)|prompts?|pos)\s*[:：]\s*(.*)$", re.I)
_NEG = re.compile(r"^(?:recommended\s+)?(?:negative(?:\s+prompts?)?|neg(?:ative)?\s*prompts?|neg|negatives)\s*[:：]\s*(.*)$", re.I)
LABEL = re.compile(r"^[A-Za-z][A-Za-z \-/]{1,30}[:：]")


def _next_value(lines, i):
    for j in range(i + 1, min(i + 4, len(lines))):
        if lines[j]:
            return "" if LABEL.match(lines[j]) and not ("," in lines[j] and len(lines[j]) > 40) else lines[j]
    return ""


def _num_range(text):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)[:2]]
    if not nums:
        return None
    v = sum(nums) / len(nums)
    return v


def clean_tags(text):
    out, seen = [], set()
    for t in re.split(r",", text or ""):
        t = re.sub(r"\s+", " ", t).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); out.append(t)
    return out


def parse_description(desc):
    """Pull recommended positive/negative prompts and settings out of a Civitai description (HTML)."""
    lines = html_to_lines(desc)
    r = {}
    for i, ln in enumerate(lines):
        if not ln:
            continue
        low = ln.lower()
        m = _NEG.match(ln)
        if m and "negative" not in r:
            v = m.group(1).strip() or _next_value(lines, i)
            if v:
                r["negative"] = ", ".join(clean_tags(v))
            continue
        m = _POS.match(ln)
        if m and "positive" not in r:
            v = m.group(1).strip() or _next_value(lines, i)
            if v:
                r["positive"] = ", ".join(clean_tags(v))
            continue
        if re.match(r"^(sampling\s+)?steps\s*[:：]", low) and "steps" not in r:
            r["steps_text"] = ln.split(":", 1)[1].strip()
            v = _num_range(r["steps_text"]); r["steps"] = int(round(v)) if v else None
        elif re.match(r"^cfg(\s*scale)?\s*[:：]", low) and "cfg" not in r:
            r["cfg_text"] = ln.split(":", 1)[1].strip()
            v = _num_range(r["cfg_text"]); r["cfg"] = round(v, 1) if v else None
        elif re.match(r"^(sampler|sampling method)\s*[:：]", low) and "sampler" not in r:
            r["sampler"] = (ln.split(":", 1)[1].strip() or _next_value(lines, i))
        elif re.match(r"^clip\s*skip\s*[:：]", low) and "clip_skip" not in r:
            v = re.findall(r"\d+", ln)
            if v:
                r["clip_skip"] = int(v[0])
        elif re.match(r"^(scheduler|schedule type)\s*[:：]", low) and "scheduler" not in r:
            r["scheduler"] = ln.split(":", 1)[1].strip()
        elif re.match(r"^(hires|hi-res|upscal)", low) and "hires" not in r:
            r["hires"] = ln
        if "resolution" not in r:
            m = re.search(r"(\d{3,4})\s*[x×*]\s*(\d{3,4})", ln)
            if m and ("resolution" in low or "size" in low or len(ln) < 40):
                r["resolution"] = f"{m.group(1)}x{m.group(2)}"
    return {k: v for k, v in r.items() if v not in (None, "")}


# ---------------------------------------------------------------- sample image mining
def mine_images(items, min_share=0.4, min_images=2):
    metas = [i.get("meta") for i in items or [] if isinstance(i.get("meta"), dict)]
    metas = [m for m in metas if m.get("prompt") or m.get("negativePrompt")]
    out = {"images_total": len(items or []), "images_with_meta": len(metas)}
    if len(metas) < min_images:
        return out

    def common(field):
        c = Counter()
        n = 0
        for m in metas:
            tags = {t.lower() for t in clean_tags(re.sub(r"[()\[\]{}]|:\d+(\.\d+)?", "", m.get(field) or "")) if len(t) < 40}
            if tags:
                n += 1; c.update(tags)
        return [(t, k / n) for t, k in c.most_common() if n and k / n >= min_share], n
    out["positive_common"], _ = common("prompt")
    out["negative_common"], _ = common("negativePrompt")
    samplers = Counter(m.get("sampler") for m in metas if m.get("sampler"))
    if samplers:
        out["sampler"] = samplers.most_common(1)[0][0]
    for key, name in (("cfgScale", "cfg"), ("steps", "steps"), ("clipSkip", "clip_skip")):
        vals = [float(m[key]) for m in metas if isinstance(m.get(key), (int, float)) or str(m.get(key, "")).replace(".", "").isdigit()]
        if vals:
            v = statistics.median(vals); out[name] = round(v, 1) if name == "cfg" else int(v)
    sizes = Counter(m.get("Size") for m in metas if m.get("Size"))
    if sizes:
        out["resolution"] = sizes.most_common(1)[0][0]
    return out


# ---------------------------------------------------------------- base model → profile
BASE_MAP = [("illustrious", "illustrious"), ("noobai", "illustrious"), ("pony", "pony"), ("anima", "anima"),
            ("flux.2", "flux2"), ("flux2", "flux2"), ("flux.1 kontext", "flux_kontext"), ("flux", "flux1"),
            ("sd 3.5", "sd35"), ("sd3.5", "sd35"), ("qwen", "qwen_image"), ("hidream", "hidream"),
            ("sdxl", "sdxl"), ("sd 1", "sdxl")]


def base_profile_id(base_model, available=()):
    b = (base_model or "").lower()
    for key, pid in BASE_MAP:
        if key in b and (not available or pid in available):
            return pid
    return "generic"


SAMPLER_COMFY = {"euler a": ("euler_ancestral", "normal"), "euler": ("euler", "normal"),
                 "dpm++ 2m karras": ("dpmpp_2m", "karras"), "dpm++ 2m": ("dpmpp_2m", "normal"),
                 "dpm++ 2m sde karras": ("dpmpp_2m_sde", "karras"), "dpm++ sde karras": ("dpmpp_sde", "karras"),
                 "dpm++ 2s a": ("dpmpp_2s_ancestral", "normal"), "ddim": ("ddim", "ddim_uniform"),
                 "uni_pc": ("uni_pc", "normal"), "lcm": ("lcm", "sgm_uniform"), "er_sde": ("er_sde", "normal")}


def comfy_sampler(name):
    """A1111-style sampler text ('euler a or DPM++ 2M Karras') → (comfy sampler, scheduler) for the first match."""
    n = (name or "").lower()
    best = None
    for k, v in SAMPLER_COMFY.items():
        i = n.find(k)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(k) > best[2])):
            best = (i, v, len(k))
    return best[1] if best else (None, None)


def a1111_sampler(name):
    first = re.split(r"\s+or\s+|/|,", name or "")[0].strip()
    return {"euler a": "Euler a", "euler": "Euler"}.get(first.lower(), first)


# ---------------------------------------------------------------- suggestion + profile
def suggest(info):
    """Merge description parsing (preferred) with sample-image mining into editable suggestions."""
    v, m = info["version"], info["model"]
    desc = parse_description(v.get("description") or "")
    mdesc = parse_description(m.get("description") or "")
    for k, val in mdesc.items():
        desc.setdefault(k, val)
    mined = mine_images(info.get("images"))
    s = {"positive": desc.get("positive", ""), "negative": desc.get("negative", ""),
         "positive_source": "description" if desc.get("positive") else "", "negative_source": "description" if desc.get("negative") else ""}
    if not s["positive"] and mined.get("positive_common"):
        s["positive"] = ", ".join(t for t, _ in mined["positive_common"][:20]); s["positive_source"] = "sample images"
    if not s["negative"] and mined.get("negative_common"):
        s["negative"] = ", ".join(t for t, _ in mined["negative_common"][:30]); s["negative_source"] = "sample images"
    for k in ("steps", "cfg", "sampler", "clip_skip", "resolution", "scheduler"):
        s[k] = desc.get(k) if desc.get(k) is not None else mined.get(k)
    s["steps_text"], s["cfg_text"] = desc.get("steps_text", ""), desc.get("cfg_text", "")
    s["trained_words"] = [w for w in (v.get("trainedWords") or []) if w]
    s["mined"] = mined
    s["base_model"] = v.get("baseModel", "")
    s["type"] = m.get("type", "")
    s["name"] = f"{m.get('name') or 'Civitai model'} {v.get('name', '')}".strip()
    return s


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40] or "model"


def build_profile(info, s, base_id, profiles_by_id, pid=None):
    """New profile that inherits from base_id and overrides prefix / negative / settings."""
    base = profiles_by_id.get(base_id) or {}
    v, m = info["version"], info["model"]
    pid = pid or f"civitai_{v['id']}"
    prefix = s.get("positive", "").strip()
    trained = [w for w in s.get("trained_words") or [] if w.lower() not in prefix.lower()]
    settings = []
    if s.get("steps_text") or s.get("steps"):
        settings.append(f"Steps {s.get('steps_text') or s['steps']}")
    if s.get("cfg_text") or s.get("cfg"):
        settings.append(f"CFG {s.get('cfg_text') or s['cfg']}")
    if s.get("sampler"):
        settings.append(f"Sampler {s['sampler']}")
    if s.get("clip_skip"):
        settings.append(f"Clip skip {s['clip_skip']}")
    if s.get("resolution"):
        settings.append(f"Resolution {s['resolution']}")
    gen = {}
    if s.get("steps"):
        gen["steps"] = int(s["steps"])
    if s.get("cfg"):
        gen["cfg"] = float(s["cfg"])
    if s.get("sampler"):
        cs, sch = comfy_sampler(s["sampler"])
        gen.update({k: val for k, val in (("sampler", cs), ("scheduler", s.get("scheduler") or sch),
                                          ("a1111_sampler", a1111_sampler(s["sampler"]))) if val})
    if s.get("clip_skip"):
        gen["clip_skip"] = int(s["clip_skip"])
    guide = (base.get("ai_guidance", "") + f" Checkpoint '{s.get('name')}' (Civitai, base {v.get('baseModel', '?')}): "
             + (f"always start with the creator's quality tags: {prefix}. " if prefix else "")
             + (f"Trigger words: {', '.join(trained)}. " if trained else "")).strip()
    prof = {
        "id": pid, "name": f"{s.get('name')} (Civitai)", "inherits": base_id,
        "family": base.get("family", "Civitai"),
        "quality_prefix": ", ".join(clean_tags(", ".join([prefix] + trained))) if (prefix or trained) else base.get("quality_prefix", ""),
        "negative_default": s.get("negative", "").strip() or base.get("negative_default", ""),
        "settings": " · ".join(settings) or base.get("settings", ""),
        "ai_guidance": guide,
        "tips": [f"Recommended by the model creator on Civitai ({s.get('positive_source') or 'n/a'})."] + list(base.get("tips", []))[:3],
        "sources": [info["url"]] + [x for x in base.get("sources", []) if x != info["url"]][:2],
        "gen": gen,
        "civitai": {"model_id": m.get("id") or v.get("modelId"), "version_id": v["id"], "version_name": v.get("name"),
                    "model_name": m.get("name"), "type": m.get("type"), "base_model": v.get("baseModel"),
                    "trained_words": s.get("trained_words") or [], "url": info["url"],
                    "fetched": time.strftime("%Y-%m-%d"), "positive_source": s.get("positive_source"),
                    "negative_source": s.get("negative_source")},
    }
    if s.get("resolution") and re.fullmatch(r"\d+x\d+", str(s["resolution"])):
        w, h = map(int, s["resolution"].split("x"))
        res = dict(base.get("resolutions", {}))
        key = {1: "1:1"}.get(1 if w == h else 0)
        if key:
            res[key] = s["resolution"]
        prof["resolutions"] = res
    return prof
