"""Prompt library sync: export / import everything as one .zip or .json, and optional private GitHub gist sync.

What is included: history, favourites, templates, prompt versions, characters, styles, video prompts, LoRA metadata
(the Civitai cache), wildcard files, model profiles and settings. API keys are NEVER included: they live in the
KeyStore (keyring / secrets.json), which this module does not read, and settings whose name looks like a secret are
dropped as well.

Duplicates on import: history/favourites/versions are matched by content; templates, characters, styles and wildcard
files by name. `policy` decides what happens to a name clash: 'skip' (keep mine), 'overwrite' (take theirs) or
'rename' (keep both, theirs gets " (2)").
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile

from . import __version__

FORMAT = "promptmaker-library"
FORMAT_VERSION = 1
GIST_FILE = "promptmaker-library.json"
SECRET_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|auth|bearer|credential)", re.I)
# settings that only make sense on this machine (paths, window state, sync bookkeeping)
LOCAL_ONLY = {"seeded", "seeded_v3", "schema_version", "setup_results", "lora_root", "gist_id", "gist_last_sync",
              "gist_last_remote", "community_index", "tour_done", "setup_done"}
KEY_LIKE = re.compile(r"^(sk-|sk_|ghp_|github_pat_|gho_|AIza|xox[abp]-|hf_)[A-Za-z0-9_\-]{8,}")


class SyncError(Exception):
    pass


class Conflict(SyncError):
    def __init__(self, local_modified, remote_modified):
        self.local_modified, self.remote_modified = local_modified, remote_modified
        super().__init__("Both this computer and the gist changed since the last sync")


def _is_secret(key, value):
    if SECRET_RE.search(key):
        return True
    return isinstance(value, str) and bool(KEY_LIKE.match(value.strip()))


def clean_settings(settings):
    return {k: v for k, v in settings.items() if k not in LOCAL_ONLY and not _is_secret(k, v)}


def scrub(obj):
    """Belt and braces: remove any secret-looking key or value anywhere in the bundle."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if not (isinstance(k, str) and SECRET_RE.search(k) and not isinstance(v, (list, dict)))
                and not (isinstance(v, str) and KEY_LIKE.match(v.strip()))}
    if isinstance(obj, list):
        return [scrub(v) for v in obj if not (isinstance(v, str) and KEY_LIKE.match(v.strip()))]
    return obj


# ---------------------------------------------------------------- collect
def _rows(store, sql, cols):
    return [dict(zip(cols, r)) for r in store.db.execute(sql).fetchall()]


def local_modified(store, wildcard_lib=None):
    vals = [store.get("library_modified", 0) or 0]
    for t in ("history", "favourites", "versions", "characters", "styles", "video_prompts"):
        try:
            v = store.db.execute(f"SELECT MAX(ts) FROM {t}").fetchone()[0]
        except Exception:  # noqa: BLE001
            v = None
        if v:
            vals.append(v)
    if wildcard_lib and wildcard_lib.root and os.path.isdir(wildcard_lib.root):
        for dp, _d, fns in os.walk(wildcard_lib.root):
            vals += [os.path.getmtime(os.path.join(dp, f)) for f in fns]
    return float(max(vals))


def touch(store):
    """Mark the library as changed now (templates and settings have no timestamps of their own)."""
    store.set("library_modified", time.time())


def build(store, wildcard_lib=None, lora_cache=None, profiles_path=None):
    b = {"format": FORMAT, "format_version": FORMAT_VERSION, "app_version": __version__, "exported": time.time()}
    b["history"] = _rows(store, "SELECT ts,prompt,fmt,source FROM history ORDER BY id", ("ts", "prompt", "fmt", "source"))
    b["favourites"] = _rows(store, "SELECT ts,name,prompt,state FROM favourites ORDER BY id", ("ts", "name", "prompt", "state"))
    b["templates"] = _rows(store, "SELECT name,body FROM templates ORDER BY id", ("name", "body"))
    b["versions"] = _rows(store, "SELECT ts,prompt,note FROM versions ORDER BY id", ("ts", "prompt", "note"))
    b["characters"] = [{k: v for k, v in c.items() if k != "id"} for c in store.characters()]
    b["styles"] = [{k: v for k, v in s.items() if k != "id"} for s in store.styles()]
    b["video_prompts"] = [{k: v for k, v in d.items() if k != "id"} for d in store.video_prompts()]
    settings = {k: json.loads(v) for k, v in store.db.execute("SELECT key,value FROM settings").fetchall()}
    b["settings"] = clean_settings(settings)
    b["wildcards"] = wildcard_lib.export_files() if wildcard_lib else {}
    b["loras"] = {}
    if lora_cache and os.path.exists(lora_cache):
        try:
            with open(lora_cache, encoding="utf-8") as f:
                b["loras"] = json.load(f)
        except (OSError, ValueError):
            pass
    b["profiles"] = None
    if profiles_path and os.path.exists(profiles_path):
        try:
            with open(profiles_path, encoding="utf-8") as f:
                b["profiles"] = json.load(f)
        except (OSError, ValueError):
            pass
    b["modified"] = local_modified(store, wildcard_lib)
    wc = {k: v for k, v in b.pop("wildcards").items() if not KEY_LIKE.match(v.strip())}  # file names like authors.txt are fine
    b = scrub(b); b["wildcards"] = wc
    return b


def counts(bundle):
    return {k: len(bundle.get(k) or {}) for k in ("history", "favourites", "templates", "versions", "characters", "styles",
                                                    "video_prompts", "wildcards", "settings")}


# ---------------------------------------------------------------- files
def export_file(path, bundle):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("library.json", json.dumps({k: v for k, v in bundle.items() if k != "wildcards"}, indent=1))
            for rel, text in (bundle.get("wildcards") or {}).items():
                z.writestr("wildcards/" + rel, text)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=1)
    return path


def read_file(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            b = json.loads(z.read("library.json"))
            b["wildcards"] = {n[len("wildcards/"):]: z.read(n).decode("utf-8", "replace")
                              for n in z.namelist() if n.startswith("wildcards/") and not n.endswith("/")}
    else:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)
    validate(b)
    return b


def validate(b):
    if not isinstance(b, dict) or b.get("format") != FORMAT:
        raise SyncError("This isn't a PromptMaker library export")
    if int(b.get("format_version", 0)) > FORMAT_VERSION:
        raise SyncError("This export was made by a newer PromptMaker – update first")


# ---------------------------------------------------------------- apply
def _unique(name, taken):
    i, n = 2, f"{name} (2)"
    while n in taken:
        i += 1; n = f"{name} ({i})"
    return n


def apply(store, bundle, mode="merge", policy="skip", wildcard_lib=None, lora_cache=None, profiles_path=None):
    """mode 'merge' adds to what you have; 'replace' clears prompts/presets/wildcards first. Returns a stats dict."""
    validate(bundle)
    wc = bundle.get("wildcards") or {}
    bundle = scrub({k: v for k, v in bundle.items() if k != "wildcards"}); bundle["wildcards"] = wc
    st = {"added": 0, "skipped": 0, "overwritten": 0, "renamed": 0}
    db = store.db
    if mode == "replace":
        for t in ("history", "favourites", "templates", "versions", "characters", "styles", "video_prompts"):
            db.execute(f"DELETE FROM {t}")
        if wildcard_lib:
            wildcard_lib.clear()
    # content-matched tables
    have = {r for r in db.execute("SELECT prompt FROM history").fetchall()}
    for h in bundle.get("history", []):
        if (h.get("prompt"),) in have:
            st["skipped"] += 1; continue
        db.execute("INSERT INTO history(ts,prompt,fmt,source) VALUES(?,?,?,?)", (h.get("ts") or time.time(), h.get("prompt", ""),
                                                                                 h.get("fmt", ""), h.get("source", "import")))
        st["added"] += 1
    have = set(db.execute("SELECT name,prompt FROM favourites").fetchall())
    for f in bundle.get("favourites", []):
        if (f.get("name"), f.get("prompt")) in have:
            st["skipped"] += 1; continue
        db.execute("INSERT INTO favourites(ts,name,prompt,state) VALUES(?,?,?,?)", (f.get("ts") or time.time(), f.get("name", ""),
                                                                                    f.get("prompt", ""), f.get("state") or "{}"))
        st["added"] += 1
    have = {r[0] for r in db.execute("SELECT prompt FROM versions").fetchall()}
    for v in bundle.get("versions", []):
        if v.get("prompt") in have:
            st["skipped"] += 1; continue
        db.execute("INSERT INTO versions(ts,prompt,note) VALUES(?,?,?)", (v.get("ts") or time.time(), v.get("prompt", ""), v.get("note", "")))
        st["added"] += 1
    have = {(d["name"], d["prompt"]) for d in store.video_prompts()}
    for d in bundle.get("video_prompts", []):
        if (d.get("name"), d.get("prompt")) in have:
            st["skipped"] += 1; continue
        db.execute("INSERT INTO video_prompts(ts,name,model,prompt,negative,settings) VALUES(?,?,?,?,?,?)",
                   (d.get("ts") or time.time(), d.get("name", ""), d.get("model", ""), d.get("prompt", ""), d.get("negative", ""),
                    json.dumps(d.get("settings") or {})))
        st["added"] += 1
    db.commit()

    # name-matched
    def named(items, existing, save, update):
        taken = {e["name"]: e for e in existing}
        for it in items:
            name = it.get("name") or ""
            if not name:
                continue
            same = taken.get(name)
            if same is None:
                save(it); st["added"] += 1
            elif all(str(same.get(k, "")) == str(it.get(k, "")) for k in it if k not in ("id", "ts")):
                st["skipped"] += 1
            elif policy == "overwrite":
                update(it, same); st["overwritten"] += 1
            elif policy == "rename":
                new = dict(it, name=_unique(name, taken)); save(new); taken[new["name"]] = new; st["renamed"] += 1
            else:
                st["skipped"] += 1

    tpls = [{"id": i, "name": n, "body": b} for i, n, b in store.templates()]
    named(bundle.get("templates", []), tpls, lambda t: store.save_template(t["name"], t.get("body", "")),
          lambda t, s: store.save_template(t["name"], t.get("body", ""), s["id"]))
    named(bundle.get("characters", []), store.characters(), lambda c: store.save_character(c),
          lambda c, s: store.save_character(c, s["id"]))
    named(bundle.get("styles", []), store.styles(), lambda c: store.save_style(c), lambda c, s: store.save_style(c, s["id"]))

    # wildcards
    if wildcard_lib is not None:
        root = wildcard_lib.root
        for rel, text in (bundle.get("wildcards") or {}).items():
            parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".", "..")]
            if not parts:
                continue
            dest = os.path.join(root, *parts)
            if os.path.exists(dest):
                with open(dest, encoding="utf-8", errors="replace") as f:
                    if f.read() == text:
                        st["skipped"] += 1; continue
                if policy == "skip":
                    st["skipped"] += 1; continue
                if policy == "rename":
                    b, e = os.path.splitext(dest); i = 2
                    while os.path.exists(f"{b}_{i}{e}"):
                        i += 1
                    dest = f"{b}_{i}{e}"; st["renamed"] += 1
                else:
                    st["overwritten"] += 1
            else:
                st["added"] += 1
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        wildcard_lib.reload()

    # settings (never secrets, never machine-local keys)
    for k, v in clean_settings(bundle.get("settings") or {}).items():
        if mode == "replace" or policy == "overwrite" or store.get(k) is None:
            store.set(k, v)
    # LoRA metadata: union, theirs only fills gaps unless overwrite
    if lora_cache and bundle.get("loras"):
        mine = {}
        if os.path.exists(lora_cache):
            try:
                with open(lora_cache, encoding="utf-8") as f:
                    mine = json.load(f)
            except (OSError, ValueError):
                mine = {}
        for sect, vals in bundle["loras"].items():
            if isinstance(vals, dict):
                tgt = mine.setdefault(sect, {})
                for k, v in vals.items():
                    if k not in tgt or policy == "overwrite":
                        tgt[k] = v
        os.makedirs(os.path.dirname(lora_cache), exist_ok=True)
        with open(lora_cache, "w", encoding="utf-8") as f:
            json.dump(mine, f)
    if profiles_path and bundle.get("profiles") and (mode == "replace" or policy == "overwrite" or not os.path.exists(profiles_path)):
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(bundle["profiles"], f, indent=1)
    touch(store)
    return st


# ---------------------------------------------------------------- GitHub gist
class Gist:
    def __init__(self, token, api="https://api.github.com"):
        if not token:
            raise SyncError("Add a GitHub token first (Library sync → GitHub gist)")
        self.token, self.api = token.strip(), api.rstrip("/")

    def _req(self, method, path, data=None, raw_url=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(raw_url or self.api + path, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "PromptMaker", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                content = r.read()
        except urllib.error.HTTPError as e:
            msg = {401: "GitHub rejected the token (401) – check it hasn't expired",
                   403: "GitHub refused (403) – the token needs the 'gist' scope (classic) or Gists: read & write (fine-grained)",
                   404: "Gist not found (404) – it may have been deleted, or the token can't see it"}.get(e.code, f"HTTP {e.code} from GitHub")
            raise SyncError(msg) from e
        except (urllib.error.URLError, OSError) as e:
            raise SyncError(f"Can't reach GitHub ({e})") from e
        return content if raw_url else (json.loads(content) if content.strip() else {})

    def user(self):
        return self._req("GET", "/user").get("login", "")

    def create(self, bundle):
        r = self._req("POST", "/gists", {"description": "PromptMaker library (synced by PromptMaker)", "public": False,
                                          "files": {GIST_FILE: {"content": json.dumps(bundle, indent=1)}}})
        return r["id"]

    def update(self, gist_id, bundle):
        self._req("PATCH", f"/gists/{gist_id}", {"files": {GIST_FILE: {"content": json.dumps(bundle, indent=1)}}})

    def fetch(self, gist_id):
        g = self._req("GET", f"/gists/{gist_id}")
        f = (g.get("files") or {}).get(GIST_FILE)
        if not f:
            raise SyncError(f"That gist has no {GIST_FILE}")
        content = f.get("content", "")
        if f.get("truncated") and f.get("raw_url"):
            content = self._req("GET", "", raw_url=f["raw_url"]).decode("utf-8")
        b = json.loads(content)
        validate(b)
        return b


def status(local_mod, remote_mod, last_sync):
    """'in_sync' | 'push' | 'pull' | 'conflict' from last-modified times (seconds) and the last successful sync."""
    last = float(last_sync or 0)
    lc, rc = local_mod > last + 1, (remote_mod or 0) > last + 1
    if lc and rc:
        return "conflict"
    return "push" if lc else "pull" if rc else "in_sync"


class GistSync:
    """push / pull / sync against one private gist. Keeps gist_id and gist_last_sync in settings."""

    def __init__(self, store, client, wildcard_lib=None, lora_cache=None, profiles_path=None):
        self.store, self.client = store, client
        self.kw = {"wildcard_lib": wildcard_lib, "lora_cache": lora_cache, "profiles_path": profiles_path}

    def _bundle(self):
        return build(self.store, **self.kw)

    def _done(self, direction, remote_mod, detail=""):
        self.store.set("gist_last_sync", max(time.time(), remote_mod or 0, local_modified(self.store, self.kw["wildcard_lib"])))
        self.store.log_sync(direction, "gist:" + (self.store.get("gist_id") or ""), "ok", detail)

    def push(self, force=False):
        b = self._bundle()
        gid = self.store.get("gist_id")
        if not gid:
            gid = self.client.create(b); self.store.set("gist_id", gid)
            self._done("push", b["modified"], "created gist"); return {"action": "created", "gist_id": gid}
        if not force:
            remote = self.client.fetch(gid)
            if status(b["modified"], remote.get("modified", 0), self.store.get("gist_last_sync", 0)) == "conflict":
                raise Conflict(b["modified"], remote.get("modified", 0))
        self.client.update(gid, b)
        self._done("push", b["modified"]); return {"action": "pushed", "gist_id": gid}

    def pull(self, mode="merge", policy="skip", force=False):
        gid = self.store.get("gist_id")
        if not gid:
            raise SyncError("No gist yet – push first, or paste an existing gist ID")
        remote = self.client.fetch(gid)
        lm = local_modified(self.store, self.kw["wildcard_lib"])
        if not force and mode == "replace" and status(lm, remote.get("modified", 0), self.store.get("gist_last_sync", 0)) == "conflict":
            raise Conflict(lm, remote.get("modified", 0))
        stats = apply(self.store, remote, mode, policy, **self.kw)
        self._done("pull", remote.get("modified", 0), json.dumps(stats)); return {"action": "pulled", **stats}

    def sync(self, resolution=None):
        """Decide automatically. On a conflict: resolution 'local' (push over), 'remote' (replace with gist),
        'merge' (merge gist in, keep mine on clashes, then push); None raises Conflict."""
        gid = self.store.get("gist_id")
        if not gid:
            return self.push()
        remote = self.client.fetch(gid)
        lm = local_modified(self.store, self.kw["wildcard_lib"])
        s = status(lm, remote.get("modified", 0), self.store.get("gist_last_sync", 0))
        if s == "in_sync":
            return {"action": "in_sync"}
        if s == "push":
            return self.push(force=True)
        if s == "pull":
            return self.pull("merge", "overwrite", force=True)
        if resolution == "local":
            return self.push(force=True)
        if resolution == "remote":
            return self.pull("replace", "overwrite", force=True)
        if resolution == "merge":
            stats = apply(self.store, remote, "merge", "skip", **self.kw)
            self.client.update(gid, self._bundle())
            self._done("merge", remote.get("modified", 0), json.dumps(stats)); return {"action": "merged", **stats}
        raise Conflict(lm, remote.get("modified", 0))
