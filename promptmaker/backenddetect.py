"""5.3 Auto-detect a running image backend at startup (Forge / A1111 / SD.Next, ComfyUI) – short parallel probes,
nothing ever blocks the UI. probe() returns what answered; choose() decides whether to switch."""
import json
import threading
import urllib.error
import urllib.request

KINDS = ("a1111", "comfyui")
NAMES = {"a1111": "Forge", "comfyui": "ComfyUI"}
DEFAULT_PORTS = {"a1111": (7860, 7861, 7862), "comfyui": (8188, 8000, 8189)}  # 8000 = ComfyUI Desktop
PRIORITY = ("a1111", "comfyui")


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "PromptMaker"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(200_000)
    return json.loads(body) if body.strip() else {}


def identify(url, timeout=0.8):
    """'comfyui' | 'a1111' | '' for a base URL. ComfyUI answers /system_stats; Forge/A1111 with --api answers
    /sdapi/v1/options. A WebUI without --api isn't usable, so it counts as not running."""
    url = url.rstrip("/")
    try:
        d = _get(url + "/system_stats", timeout)
        if isinstance(d, dict) and ("system" in d or "devices" in d):
            return "comfyui"
    except (urllib.error.URLError, OSError, ValueError):
        pass
    try:
        d = _get(url + "/sdapi/v1/options", timeout)
        if isinstance(d, dict) and d:
            return "a1111"
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return ""


def candidates(store_get):
    """[(kind, url)] – the configured URL of each kind first, then the usual local ports. No duplicates."""
    out, seen = [], set()
    for kind in KINDS:
        urls = [store_get(f"img_url:{kind}", "") or ""] + [f"http://127.0.0.1:{p}" for p in DEFAULT_PORTS[kind]]
        for u in urls:
            u = u.strip().rstrip("/")
            if u and u not in seen:
                seen.add(u); out.append((kind, u))
    return out


def probe(cands, timeout=0.8, ident=identify):
    """{url: kind} for every candidate that answered (checked in parallel; total ≈ one timeout)."""
    found, lock = {}, threading.Lock()

    def one(u):
        k = ident(u, timeout)
        if k:
            with lock:
                found[u] = k
    ts = [threading.Thread(target=one, args=(u,), daemon=True) for _k, u in cands]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout * 2 + 0.5)
    return dict(found)


def choose(current_kind, current_url, found, configured=None):
    """(kind, url) to use, or None to keep the current setup. Keeps the current backend when it is running;
    otherwise prefers each kind's configured URL, then PRIORITY order."""
    if not found:
        return None
    configured = configured or {}
    cur = (current_url or "").rstrip("/")
    if current_kind in KINDS and found.get(cur) == current_kind:
        return None  # current one is running – nothing to do
    by_kind = {}
    for u, k in found.items():
        by_kind.setdefault(k, []).append(u)
    order = ([current_kind] if current_kind in by_kind else []) + [k for k in PRIORITY if k in by_kind and k != current_kind]
    for k in order:
        urls = by_kind[k]
        conf = (configured.get(k) or "").rstrip("/")
        url = conf if conf in urls else sorted(urls)[0]
        if (k, url) != (current_kind, cur):
            return k, url
    return None
