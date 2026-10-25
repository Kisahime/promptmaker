"""Community gallery: browse an index of packs/profiles, install with SHA-256 verification."""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .library import PackError, validate_pack

DEFAULT_INDEX = "https://raw.githubusercontent.com/Kisahime/promptmaker/main/community/index.json"


class CommunityError(Exception):
    pass


def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PromptMaker"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise CommunityError(f"Couldn't download {url}: {e}") from e


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_index(url=DEFAULT_INDEX):
    try:
        idx = json.loads(fetch(url))
    except ValueError as e:
        raise CommunityError("The community index isn't valid JSON") from e
    items = []
    for kind in ("packs", "profiles"):
        for e in idx.get(kind, []):
            if not all(k in e for k in ("id", "name", "url", "sha256", "version")):
                continue
            e = dict(e, kind=kind[:-1], url=urllib.parse.urljoin(url, e["url"]))
            items.append(e)
    return items


def download_verified(entry):
    data = fetch(entry["url"])
    digest = sha256(data)
    if digest.lower() != entry["sha256"].lower():
        raise CommunityError(f"Hash mismatch for '{entry['name']}' – expected {entry['sha256'][:12]}…, got {digest[:12]}…. Not installed.")
    try:
        return json.loads(data)
    except ValueError as e:
        raise CommunityError("Downloaded file isn't valid JSON") from e


def install(entry, library, profiles_path, installed):
    """Install or update an index entry. `installed` is a dict id -> record (persist it yourself)."""
    data = download_verified(entry)
    if entry["kind"] == "pack":
        try:
            validate_pack(data)
        except PackError as e:
            raise CommunityError(str(e)) from e
        pid = "community_" + entry["id"]
        library.packs[pid] = data
        library.save_pack(pid)
        library._merge()
        installed[entry["id"]] = {"kind": "pack", "version": entry["version"], "file": pid}
    else:
        new = data.get("profiles", [data] if "id" in data else [])
        if not new or not all("id" in p and "name" in p for p in new):
            raise CommunityError("Profile file needs 'id' and 'name'")
        with open(profiles_path, encoding="utf-8") as f:
            cur = json.load(f)
        ids = [p["id"] for p in new]
        cur["profiles"] = [p for p in cur.get("profiles", []) if p.get("id") not in ids] + new
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=1, ensure_ascii=False)
        installed[entry["id"]] = {"kind": "profile", "version": entry["version"], "ids": ids}
    return installed


def uninstall(entry_id, library, profiles_path, installed):
    rec = installed.pop(entry_id, None)
    if not rec:
        return installed
    if rec["kind"] == "pack":
        path = library.pack_path(rec["file"])
        if os.path.exists(path):
            os.remove(path)
        library.packs.pop(rec["file"], None)
        library._merge()
    else:
        with open(profiles_path, encoding="utf-8") as f:
            cur = json.load(f)
        cur["profiles"] = [p for p in cur.get("profiles", []) if p.get("id") not in rec.get("ids", [])]
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=1, ensure_ascii=False)
    return installed


def status(entry, installed):
    rec = installed.get(entry["id"])
    if not rec:
        return "available"
    return "installed" if str(rec.get("version")) == str(entry["version"]) else "update"
