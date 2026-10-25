"""Preset packs: loading, merging, enable/disable, import/export."""
import json
import os
import re

CATEGORY_ORDER = ["Subject", "Action / pose", "Setting", "Time & weather", "Style", "Art movement",
                  "Artist influence", "Lighting", "Camera", "Composition", "Mood", "Color palette",
                  "Detail / quality"]
LEGACY = {"Action": "Action / pose"}
PLACEHOLDERS = {
    "subject": "Subject", "action": "Action / pose", "setting": "Setting", "time": "Time & weather",
    "style": "Style", "movement": "Art movement", "artist": "Artist influence", "lighting": "Lighting",
    "camera": "Camera", "composition": "Composition", "mood": "Mood", "color": "Color palette",
    "detail": "Detail / quality",
}
CUSTOM_ID = "custom"


class PackError(Exception):
    pass


def validate_pack(data):
    if not isinstance(data, dict) or "categories" not in data or not isinstance(data["categories"], dict):
        raise PackError("Not a PromptMaker pack: needs a 'categories' object.")
    for cat, groups in data["categories"].items():
        if isinstance(groups, list):  # allow flat lists
            data["categories"][cat] = groups = {"General": groups}
        if not isinstance(groups, dict):
            raise PackError(f"Category '{cat}' must map group names to lists.")
        for g, items in groups.items():
            if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
                raise PackError(f"Group '{cat} / {g}' must be a list of strings.")
    data.setdefault("name", "Untitled pack")
    data.setdefault("description", "")
    data.setdefault("version", "1.0")
    return data


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "pack"


class Library:
    def __init__(self, packs_dir, disabled=(), user_dir=None):
        self.dir = packs_dir
        self.user_dir = user_dir or packs_dir
        os.makedirs(self.user_dir, exist_ok=True)
        self.disabled = set(disabled)
        self.reload()

    def reload(self):
        self.packs, self.paths, self.bundled = {}, {}, set()
        dirs = [self.dir] + ([self.user_dir] if os.path.abspath(self.user_dir) != os.path.abspath(self.dir) else [])
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d), key=lambda f: (f != "core.json", f != "custom.json", f)):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(d, fn), encoding="utf-8") as f:
                            self.packs[fn[:-5]] = validate_pack(json.load(f))
                        self.paths[fn[:-5]] = os.path.join(d, fn)
                        if d == self.dir and fn[:-5] != CUSTOM_ID and not fn.startswith("community_"):
                            self.bundled.add(fn[:-5])
                    except (OSError, ValueError, PackError):
                        continue
        if CUSTOM_ID not in self.packs:
            self.packs[CUSTOM_ID] = {"name": "My presets", "description": "Chips you added yourself.",
                                     "version": "1.0", "categories": {}}
        self._merge()

    def _merge(self):
        merged = {c: {} for c in CATEGORY_ORDER}
        for pid, pack in self.packs.items():
            if pid in self.disabled:
                continue
            for cat, groups in pack["categories"].items():
                cat = LEGACY.get(cat, cat)
                tgt = merged.setdefault(cat, {})
                for g, items in groups.items():
                    lst = tgt.setdefault(g, [])
                    for i in items:
                        if i not in lst:
                            lst.append(i)
        self.categories = {c: g for c, g in merged.items() if g or c in CATEGORY_ORDER}

    def items(self, cat):
        out = []
        for lst in self.categories.get(cat, {}).values():
            out.extend(lst)
        return out

    def all_items(self):
        return {c: self.items(c) for c in self.categories}

    def count(self):
        return sum(len(self.items(c)) for c in self.categories)

    def search(self, q, limit=300):
        q = q.lower().strip()
        res = []
        for cat in self.categories:
            for i in self.items(cat):
                if q in i.lower():
                    res.append((cat, i))
                    if len(res) >= limit:
                        return res
        return res

    def set_enabled(self, pid, on):
        (self.disabled.discard if on else self.disabled.add)(pid)
        self._merge()

    def pack_path(self, pid):
        return self.paths.get(pid) or os.path.join(self.user_dir, pid + ".json")

    def save_pack(self, pid):
        path = self.pack_path(pid)
        self.paths[pid] = path
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.packs[pid], f, indent=1, ensure_ascii=False)

    def add_custom(self, cat, item):
        p = self.packs[CUSTOM_ID]
        lst = p["categories"].setdefault(cat, {}).setdefault("My presets", [])
        if item not in lst:
            lst.append(item)
        self.save_pack(CUSTOM_ID)
        self._merge()

    def import_pack(self, path):
        with open(path, encoding="utf-8") as f:
            data = validate_pack(json.load(f))
        pid = slug(data["name"])
        base, n = pid, 2
        while pid in self.packs:
            pid = f"{base}_{n}"; n += 1
        self.packs[pid] = data
        self.save_pack(pid)
        self._merge()
        return pid

    def export_pack(self, pid, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.packs[pid], f, indent=1, ensure_ascii=False)

    def delete_pack(self, pid):
        if pid in self.bundled or pid == CUSTOM_ID:
            raise PackError("Built-in packs and My presets can't be deleted (disable them instead).")
        os.remove(self.pack_path(pid))
        self.paths.pop(pid, None)
        self.packs.pop(pid)
        self.disabled.discard(pid)
        self._merge()
