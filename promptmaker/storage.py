"""SQLite persistence (backwards compatible with v2 databases)."""
import json
import sqlite3
import time

DEFAULT_TEMPLATES = [
    ("Character portrait", "Portrait of {subject}, {style}, {lighting}, {camera}, {mood} mood, highly detailed"),
    ("Epic landscape", "Epic landscape {setting} {time}, {style}, {lighting}, {color}, {mood}, {composition}"),
    ("Product shot", "Studio product photo of {subject} on a clean background, softbox lighting, {color}, sharp focus"),
    ("Movie still", "Cinematic still of {subject} {action} {setting}, {lighting}, anamorphic lens, film grain"),
    ("Fantasy scene", "{subject} {action} {setting}, fantasy illustration, {artist}, {lighting}, {mood}"),
    ("Art-history remix", "{subject} painted in the manner of {movement}, {artist}, {color}, {composition}"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, ts REAL, prompt TEXT, fmt TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY, name TEXT UNIQUE, body TEXT);
CREATE TABLE IF NOT EXISTS favourites(id INTEGER PRIMARY KEY, ts REAL, name TEXT, prompt TEXT, state TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, ts REAL, prompt TEXT, note TEXT);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        if not self.get("seeded"):
            for name, body in DEFAULT_TEMPLATES:
                self.db.execute("INSERT OR IGNORE INTO templates(name, body) VALUES(?,?)", (name, body))
            self.set("seeded", True)
        if not self.get("seeded_v3"):
            self.db.execute("INSERT OR IGNORE INTO templates(name, body) VALUES(?,?)", DEFAULT_TEMPLATES[-1])
            self.set("seeded_v3", True)
        self.db.commit()
        self.migrate()

    SCHEMA_VERSION = 5
    MIGRATIONS = {
        3: """
        CREATE TABLE IF NOT EXISTS characters(id INTEGER PRIMARY KEY, name TEXT UNIQUE, appearance TEXT DEFAULT '',
            outfit TEXT DEFAULT '', lora TEXT DEFAULT '', lora_weight REAL DEFAULT 0.8, ref_image TEXT DEFAULT '',
            notes TEXT DEFAULT '', ts REAL);
        CREATE TABLE IF NOT EXISTS styles(id INTEGER PRIMARY KEY, name TEXT UNIQUE, tags TEXT DEFAULT '',
            negative TEXT DEFAULT '', ts REAL);
        """,
        4: """
        CREATE TABLE IF NOT EXISTS video_prompts(id INTEGER PRIMARY KEY, ts REAL, name TEXT, model TEXT, prompt TEXT,
            negative TEXT DEFAULT '', settings TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sync_log(id INTEGER PRIMARY KEY, ts REAL, direction TEXT, target TEXT, status TEXT,
            detail TEXT DEFAULT '');
        """,
        # 5.0: full Characters (outfits, references, LoRAs, triggers, per-model tag sets) live in a JSON column
        5: """
        ALTER TABLE characters ADD COLUMN extra TEXT DEFAULT '{}';
        """,
    }

    def schema_version(self):
        return int(self.get("schema_version", 2) or 2)

    def migrate(self):
        """Apply numbered migrations once each (v2 databases start at schema 2)."""
        cur = self.schema_version()
        for ver in sorted(self.MIGRATIONS):
            if ver > cur:
                self.db.executescript(self.MIGRATIONS[ver])
                self.set("schema_version", ver)
        self.db.commit()

    # ---------------------------------------------------------------- characters & styles
    CHAR_FIELDS = ("name", "appearance", "outfit", "lora", "lora_weight", "ref_image", "notes", "extra")

    def characters(self):
        cur = self.db.execute("SELECT id," + ",".join(self.CHAR_FIELDS) + " FROM characters ORDER BY name COLLATE NOCASE")
        return [dict(zip(("id",) + self.CHAR_FIELDS, r)) for r in cur.fetchall()]

    def character(self, name_or_id):
        return next((c for c in self.characters() if name_or_id in (c["id"], c["name"])), None)

    def save_character(self, data, cid=None):
        if cid and "extra" not in data:  # older callers (Presets page) keep the 5.0 Character details
            old = self.character(cid)
            data = dict(data, extra=(old or {}).get("extra") or "{}")
        vals = [data.get(k, 0.8 if k == "lora_weight" else ("{}" if k == "extra" else "")) for k in self.CHAR_FIELDS]
        if not isinstance(vals[-1], str):
            vals[-1] = json.dumps(vals[-1])
        if not str(vals[0]).strip():
            raise ValueError("A character needs a name")
        if cid:
            self.db.execute("UPDATE characters SET " + ",".join(f"{k}=?" for k in self.CHAR_FIELDS) + ",ts=? WHERE id=?",
                            (*vals, time.time(), cid))
        else:
            self.db.execute("INSERT OR REPLACE INTO characters(" + ",".join(self.CHAR_FIELDS) + ",ts) VALUES(?,?,?,?,?,?,?,?,?)",
                            (*vals, time.time()))
        self.db.commit()
        return self.character(vals[0])["id"]

    def delete_character(self, cid):
        self.db.execute("DELETE FROM characters WHERE id=?", (cid,)); self.db.commit()

    def styles(self):
        cur = self.db.execute("SELECT id,name,tags,negative FROM styles ORDER BY name COLLATE NOCASE")
        return [dict(zip(("id", "name", "tags", "negative"), r)) for r in cur.fetchall()]

    def style(self, name_or_id):
        return next((s for s in self.styles() if name_or_id in (s["id"], s["name"])), None)

    def save_style(self, data, sid=None):
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("A style needs a name")
        if sid:
            self.db.execute("UPDATE styles SET name=?,tags=?,negative=?,ts=? WHERE id=?",
                            (name, data.get("tags", ""), data.get("negative", ""), time.time(), sid))
        else:
            self.db.execute("INSERT OR REPLACE INTO styles(name,tags,negative,ts) VALUES(?,?,?,?)",
                            (name, data.get("tags", ""), data.get("negative", ""), time.time()))
        self.db.commit()
        return self.style(name)["id"]

    def delete_style(self, sid):
        self.db.execute("DELETE FROM styles WHERE id=?", (sid,)); self.db.commit()

    # ---------------------------------------------------------------- v4: video prompts & sync log
    def save_video_prompt(self, name, model, prompt, negative="", settings=None):
        cur = self.db.execute("INSERT INTO video_prompts(ts,name,model,prompt,negative,settings) VALUES(?,?,?,?,?,?)",
                              (time.time(), name or "Untitled", model, prompt, negative, json.dumps(settings or {})))
        self.db.commit()
        return cur.lastrowid

    def video_prompts(self):
        cur = self.db.execute("SELECT id,ts,name,model,prompt,negative,settings FROM video_prompts ORDER BY id DESC")
        out = []
        for r in cur.fetchall():
            d = dict(zip(("id", "ts", "name", "model", "prompt", "negative", "settings"), r))
            d["settings"] = json.loads(d["settings"] or "{}"); out.append(d)
        return out

    def delete_video_prompt(self, vid):
        self.db.execute("DELETE FROM video_prompts WHERE id=?", (vid,)); self.db.commit()

    def log_sync(self, direction, target, status, detail=""):
        self.db.execute("INSERT INTO sync_log(ts,direction,target,status,detail) VALUES(?,?,?,?,?)",
                        (time.time(), direction, target, status, detail)); self.db.commit()

    def sync_log(self, limit=50):
        return self.db.execute("SELECT ts,direction,target,status,detail FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def get(self, key, default=None):
        r = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))
        self.db.commit()

    def add_history(self, prompt, fmt="", source="builder"):
        if not prompt or not prompt.strip():
            return
        last = self.db.execute("SELECT prompt FROM history ORDER BY id DESC LIMIT 1").fetchone()
        if last and last[0] == prompt:
            return
        self.db.execute("INSERT INTO history(ts,prompt,fmt,source) VALUES(?,?,?,?)", (time.time(), prompt, fmt, source))
        self.db.commit()

    def history(self, query="", limit=500):
        return self.db.execute("SELECT id,ts,prompt,fmt,source FROM history WHERE prompt LIKE ? OR fmt LIKE ? "
                               "ORDER BY id DESC LIMIT ?", (f"%{query}%", f"%{query}%", limit)).fetchall()

    def delete_history(self, hid):
        self.db.execute("DELETE FROM history WHERE id=?", (hid,)); self.db.commit()

    def clear_history(self):
        self.db.execute("DELETE FROM history"); self.db.commit()

    def templates(self):
        return self.db.execute("SELECT id,name,body FROM templates ORDER BY name").fetchall()

    def save_template(self, name, body, tid=None):
        if tid:
            self.db.execute("UPDATE templates SET name=?, body=? WHERE id=?", (name, body, tid))
        else:
            self.db.execute("INSERT OR REPLACE INTO templates(name,body) VALUES(?,?)", (name, body))
        self.db.commit()

    def delete_template(self, tid):
        self.db.execute("DELETE FROM templates WHERE id=?", (tid,)); self.db.commit()

    def favourites(self):
        return self.db.execute("SELECT id,ts,name,prompt,state FROM favourites ORDER BY id DESC").fetchall()

    def add_favourite(self, name, prompt, state=None):
        self.db.execute("INSERT INTO favourites(ts,name,prompt,state) VALUES(?,?,?,?)",
                        (time.time(), name, prompt, json.dumps(state or {})))
        self.db.commit()

    def delete_favourite(self, fid):
        self.db.execute("DELETE FROM favourites WHERE id=?", (fid,)); self.db.commit()

    def add_version(self, prompt, note=""):
        last = self.db.execute("SELECT prompt FROM versions ORDER BY id DESC LIMIT 1").fetchone()
        if prompt.strip() and not (last and last[0] == prompt):
            self.db.execute("INSERT INTO versions(ts,prompt,note) VALUES(?,?,?)", (time.time(), prompt, note))
            self.db.commit()

    def versions(self, limit=200):
        return self.db.execute("SELECT id,ts,prompt,note FROM versions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def clear_versions(self):
        self.db.execute("DELETE FROM versions"); self.db.commit()
