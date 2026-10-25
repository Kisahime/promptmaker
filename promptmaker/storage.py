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
