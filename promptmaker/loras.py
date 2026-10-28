"""LoRA / embedding manager: scan a models folder, hash files, look them up on Civitai by hash, cache, insert."""
import hashlib
import json
import os
import re
import time

from . import civitai

EXTS = (".safetensors", ".pt", ".ckpt", ".bin", ".pth")
DEFAULT_ROOT = r"C:\AI\sd-webui-forge-classic\models"
KINDS = {"lora": ("Lora", "LyCORIS", "lora"), "embedding": ("embeddings", "../embeddings", "embedding")}
# base-model families that can usually share LoRAs
FAMILIES = [{"sdxl", "pony", "illustrious"}, {"flux1", "flux_kontext"}]


def folders(root):
    """Forge layout: models/Lora (+ LyCORIS) and embeddings (models/../embeddings or models/embeddings)."""
    root = root or DEFAULT_ROOT
    out = {"lora": [], "embedding": []}
    for sub in ("Lora", "LyCORIS"):
        p = os.path.join(root, sub)
        if os.path.isdir(p):
            out["lora"].append(p)
    for p in (os.path.join(root, "embeddings"), os.path.join(os.path.dirname(root.rstrip("\\/")), "embeddings")):
        if os.path.isdir(p) and p not in out["embedding"]:
            out["embedding"].append(p)
    return out


def scan(root):
    """[{"name", "path", "kind", "size", "mtime"}] sorted by name."""
    items = []
    for kind, dirs in folders(root).items():
        for d in dirs:
            for dp, _, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(EXTS):
                        p = os.path.join(dp, fn); st = os.stat(p)
                        items.append({"name": os.path.splitext(fn)[0], "path": p, "kind": kind,
                                      "size": st.st_size, "mtime": st.st_mtime})
    return sorted(items, key=lambda x: (x["kind"], x["name"].lower()))


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest().upper()


def autov2(sha256):
    """AUTOMATIC1111's AutoV2 short hash = first 10 hex chars of the full SHA256."""
    return sha256[:10].upper()


class Cache:
    """JSON cache: hashes keyed by path+size+mtime, Civitai info keyed by SHA256."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("hashes", {}); self.data.setdefault("info", {})

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)

    @staticmethod
    def _key(item):
        return f"{item['path']}|{item['size']}|{int(item['mtime'])}"

    def sha(self, item):
        k = self._key(item)
        if k not in self.data["hashes"]:
            self.data["hashes"][k] = sha256_file(item["path"])
        return self.data["hashes"][k]

    def info(self, sha):
        return self.data["info"].get(sha)

    def set_info(self, sha, info):
        self.data["info"][sha] = info


def parse_version(v):
    model = v.get("model") or {}
    imgs = [i.get("url") for i in v.get("images") or [] if i.get("url") and i.get("type", "image") == "image"]
    words = [w.strip() for w in v.get("trainedWords") or [] if str(w).strip()]
    return {"found": True, "name": model.get("name") or v.get("name", ""), "version": v.get("name", ""),
            "type": model.get("type", ""), "trained_words": words, "base_model": v.get("baseModel", ""),
            "preview": imgs[0] if imgs else "", "model_id": v.get("modelId"), "version_id": v.get("id"),
            "url": f"https://civitai.com/models/{v.get('modelId')}?modelVersionId={v.get('id')}" if v.get("modelId") else "",
            "checked": time.time()}


def lookup(sha, client):
    """Civitai /model-versions/by-hash/{hash}; returns parsed info, {"found": False} for unknown files."""
    try:
        return parse_version(client.get(f"/model-versions/by-hash/{sha}"))
    except civitai.CivitaiError as e:
        if "not found" in str(e).lower():
            return {"found": False, "checked": time.time()}
        raise


def enrich(items, cache, client=None, progress=None, stop_flag=None):
    """Hash every item and attach Civitai info (cached). Mutates and returns items."""
    for n, it in enumerate(items):
        if stop_flag and stop_flag():
            break
        if progress:
            progress(n, len(items), it["name"])
        it["sha256"] = cache.sha(it); it["autov2"] = autov2(it["sha256"])
        info = cache.info(it["sha256"])
        if info is None and client is not None:
            info = lookup(it["sha256"], client); cache.set_info(it["sha256"], info)
        it["info"] = info or {}
    cache.save()
    return items


def base_id_of(profile, profiles=None):
    """Follow "inherits" to the base profile id (Civitai-imported profiles inherit from e.g. illustrious)."""
    p, seen = profile, set()
    while p.get("inherits") and p["inherits"] not in seen:
        seen.add(p["inherits"]); nxt = (profiles or {}).get(p["inherits"])
        if not nxt:
            return p["inherits"]
        p = nxt
    return p.get("id", "generic")


def compatible(item, profile, profiles=None, strict=False):
    """True/False, or None when unknown (no Civitai info). Generic profile accepts anything."""
    bm = (item.get("info") or {}).get("base_model")
    target = base_id_of(profile, profiles)
    if target == "generic":
        return True
    if not bm:
        return None
    lid = civitai.base_profile_id(bm)
    if lid == target:
        return True
    if strict:
        return False
    return any(lid in fam and target in fam for fam in FAMILIES)


def insert_text(item, weight=0.8, with_words=True):
    """<lora:name:weight> plus trigger words; embeddings insert their name (optionally weighted)."""
    name = item["name"]
    words = (item.get("info") or {}).get("trained_words") or [] if with_words else []
    if item.get("kind") == "embedding":
        tok = name if abs(weight - 1.0) < 1e-6 else f"({name}:{weight:g})"
    else:
        tok = f"<lora:{name}:{weight:g}>"
    return ", ".join([*words, tok]) if words else tok


def insert_into(prompt, text):
    prompt = (prompt or "").rstrip().rstrip(",")
    return f"{prompt}, {text}" if prompt else text


LORA_RE = re.compile(r"<lora:([^:>]+):([-\d.]+)>")


def used_loras(prompt):
    return [(m.group(1), float(m.group(2))) for m in LORA_RE.finditer(prompt or "")]
