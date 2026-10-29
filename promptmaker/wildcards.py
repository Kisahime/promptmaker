"""Wildcards and dynamic prompts, compatible with the sd-dynamic-prompts syntax.

    __name__            a random line from wildcards/name.txt (folders: __animals/cats__, globs: __animals/*__)
    {a|b|c}             pick one
    {2::a|b}            weighted pick (a is twice as likely)
    {2$$a|b|c}          pick 2 different ones, joined with ", "
    {1-3$$a|b|c}        pick 1 to 3;  {2$$ and $$a|b|c} uses " and " as the separator
    nesting             {red|{light|dark} blue} __hair__ – expanded recursively (wildcard files can contain syntax too)

YAML files are flattened: animals.yaml with {cats: [..], dogs: {big: [..]}} gives __animals/cats__ and __animals/dogs/big__
(and also __cats__ / __dogs/big__ like sd-dynamic-prompts does for the top-level keys).
Everything is driven by random.Random(seed), so the same seed always gives the same prompt.
"""
import fnmatch
import io
import os
import random
import re
import shutil
import zipfile

MAX_DEPTH = 40
WILDCARD_RE = re.compile(r"__([\w\-./*?\\ ]+?)__")
EXTS = (".txt", ".yaml", ".yml")


# ---------------------------------------------------------------- tiny YAML fallback (PyYAML is optional)
def _yaml_load(text):
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


def _scalar(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _mini_yaml(text):
    """Enough YAML for wildcard packs: nested mappings whose leaves are '- item' lists (or [a, b] flow lists)."""
    lines = [(len(r) - len(r.lstrip(" ")), r.strip()) for r in text.splitlines() if r.strip() and not r.lstrip().startswith("#")]

    def block(i, ind):
        if i >= len(lines):
            return None, i
        if lines[i][1].startswith("-"):
            out = []
            while i < len(lines) and lines[i][0] == ind and lines[i][1].startswith("-"):
                out.append(_scalar(lines[i][1][1:])); i += 1
            return out, i
        out = {}
        while i < len(lines) and lines[i][0] == ind and not lines[i][1].startswith("-"):
            k, _, v = lines[i][1].partition(":")
            k, v = _scalar(k), v.strip(); i += 1
            if v.startswith("[") and v.endswith("]"):
                out[k] = [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
            elif v and v not in ("|", ">"):
                out[k] = [_scalar(v)]
            elif i < len(lines) and (lines[i][0] > ind or (lines[i][0] == ind and lines[i][1].startswith("-"))):
                out[k], i = block(i, lines[i][0])
            else:
                out[k] = []
        return out, i
    return block(0, lines[0][0])[0] if lines else {}


def flatten_yaml(data, prefix=""):
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}/{k}" if prefix else str(k)
            out.update(flatten_yaml(v, key))
    elif isinstance(data, list):
        if all(not isinstance(x, (dict, list)) for x in data):
            out[prefix] = [str(x) for x in data if str(x).strip()]
        else:
            for x in data:
                out.update(flatten_yaml(x, prefix))
    elif data is not None and prefix:
        out[prefix] = [str(data)]
    return out


def parse_lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


# ---------------------------------------------------------------- library on disk
class WildcardLib:
    def __init__(self, root):
        self.root = root
        self._cache = None

    def reload(self):
        self._cache = None

    def _load(self):
        if self._cache is not None:
            return self._cache
        data, files = {}, {}
        if self.root and os.path.isdir(self.root):
            for dp, _dirs, fns in os.walk(self.root):
                for fn in sorted(fns):
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in EXTS:
                        continue
                    path = os.path.join(dp, fn)
                    rel = os.path.relpath(path, self.root)[: -len(ext)].replace(os.sep, "/")
                    try:
                        with open(path, encoding="utf-8", errors="replace") as f:
                            text = f.read()
                    except OSError:
                        continue
                    if ext == ".txt":
                        data[rel] = parse_lines(text); files[rel] = path
                    else:
                        try:
                            flat = flatten_yaml(_yaml_load(text) or {})
                        except Exception:  # noqa: BLE001 – a broken pack shouldn't break the rest
                            continue
                        base = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
                        for k, v in flat.items():
                            data.setdefault(base + k, v); files.setdefault(base + k, path)
                            data.setdefault(rel + "/" + k, v); files.setdefault(rel + "/" + k, path)
        self._cache = (data, files)
        return self._cache

    def names(self):
        return sorted(self._load()[0], key=str.lower)

    def file_names(self):
        """Editable .txt wildcards only (YAML entries are read-only in the manager)."""
        d, f = self._load()
        return sorted((n for n in d if f[n].endswith(".txt")), key=str.lower)

    def path_of(self, name):
        return self._load()[1].get(name)

    def get(self, name):
        """Entries for a wildcard name (case-insensitive, globs merge all matches). [] if unknown."""
        data = self._load()[0]
        name = name.strip().replace("\\", "/")
        if name in data:
            return data[name]
        low = {k.lower(): k for k in data}
        if name.lower() in low:
            return data[low[name.lower()]]
        if any(c in name for c in "*?"):
            out = []
            for k in sorted(data):
                if fnmatch.fnmatch(k.lower(), name.lower()):
                    out.extend(data[k])
            return out
        return []

    # -------- editing
    def _txt_path(self, name):
        name = name.strip().strip("_").replace("\\", "/")
        if not name or ".." in name.split("/") or name.startswith("/"):
            raise ValueError("Invalid wildcard name")
        return os.path.join(self.root, *name.split("/")) + ".txt"

    def save(self, name, entries):
        path = self._txt_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = entries if isinstance(entries, list) else parse_lines(entries)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(x.strip() for x in lines if x.strip()) + "\n")
        self.reload()
        return path

    def delete(self, name):
        path = self.path_of(name)
        if path and path.endswith(".txt") and os.path.exists(path):
            os.remove(path)
        self.reload()

    def import_path(self, src, mode="skip"):
        """Import .txt/.yaml files from a folder or a .zip (e.g. a Civitai wildcard pack).
        mode: 'skip' keeps existing files, 'replace' overwrites, 'rename' keeps both (name_2.txt).
        Returns {'added': n, 'skipped': n, 'replaced': n}."""
        stats = {"added": 0, "skipped": 0, "replaced": 0}
        os.makedirs(self.root, exist_ok=True)

        def put(rel, data):
            rel = rel.replace("\\", "/").lstrip("/")
            parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
            if not parts or os.path.splitext(parts[-1])[1].lower() not in EXTS or parts[0] == "__MACOSX":
                return
            if parts[0].lower() == "wildcards" and len(parts) > 1:  # packs often wrap everything in wildcards/
                parts = parts[1:]
            dest = os.path.join(self.root, *parts)
            if os.path.exists(dest):
                if mode == "skip":
                    stats["skipped"] += 1; return
                if mode == "rename":
                    b, e = os.path.splitext(dest); i = 2
                    while os.path.exists(f"{b}_{i}{e}"):
                        i += 1
                    dest = f"{b}_{i}{e}"; stats["added"] += 1
                else:
                    stats["replaced"] += 1
            else:
                stats["added"] += 1
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)

        if os.path.isdir(src):
            for dp, _d, fns in os.walk(src):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    with open(p, "rb") as f:
                        put(os.path.relpath(p, src), f.read())
        elif zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    data = z.read(info)
                    if info.filename.lower().endswith(".zip"):  # zip inside a zip (common on Civitai)
                        with zipfile.ZipFile(io.BytesIO(data)) as inner:
                            for ii in inner.infolist():
                                if not ii.is_dir():
                                    put(ii.filename, inner.read(ii))
                    else:
                        put(info.filename, data)
        elif os.path.isfile(src):
            with open(src, "rb") as f:
                put(os.path.basename(src), f.read())
        else:
            raise ValueError(f"Not found: {src}")
        self.reload()
        return stats

    def export_files(self):
        """{relative path: text} for every wildcard file (used by library sync)."""
        out = {}
        if self.root and os.path.isdir(self.root):
            for dp, _d, fns in os.walk(self.root):
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() in EXTS:
                        p = os.path.join(dp, fn)
                        with open(p, encoding="utf-8", errors="replace") as f:
                            out[os.path.relpath(p, self.root).replace(os.sep, "/")] = f.read()
        return out

    def clear(self):
        if self.root and os.path.isdir(self.root):
            shutil.rmtree(self.root)
        os.makedirs(self.root, exist_ok=True); self.reload()


# ---------------------------------------------------------------- expansion
def _split_top(s, sep="|"):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


_COUNT_RE = re.compile(r"^\s*(\d*)\s*(?:-\s*(\d*))?\s*\$\$")


def _variant(body, rng, depth, lib, missing):
    count = None
    sep = ", "
    m = _COUNT_RE.match(body)
    if m:
        lo = int(m.group(1)) if m.group(1) else 1
        hi = int(m.group(2)) if m.group(2) else (lo if m.group(2) is None else None)
        body = body[m.end():]
        if "$$" in body.split("|", 1)[0]:  # custom separator: {2$$ and $$a|b}
            sep, _, body = body.partition("$$")
        count = (lo, hi)
    options = []
    for opt in _split_top(body):
        w = 1.0
        mm = re.match(r"^\s*(\d+(?:\.\d+)?)::", opt)
        if mm:
            w, opt = float(mm.group(1)), opt[mm.end():]
        options.append((opt.strip() if count else opt, w))
    if not options:
        return ""
    if count is None:
        choice = _weighted(rng, options)
        return _expand(choice, rng, depth + 1, lib, missing)
    lo, hi = count
    hi = len(options) if hi is None else min(hi, len(options))
    lo = min(lo, hi)
    n = rng.randint(lo, hi) if hi > lo else hi
    pool, picked = list(options), []
    for _ in range(n):
        c = _weighted(rng, pool)
        picked.append(c)
        pool = [o for o in pool if o[0] != c]
        if not pool:
            break
    return sep.join(_expand(p, rng, depth + 1, lib, missing) for p in picked)


def _weighted(rng, options):
    total = sum(max(w, 0) for _, w in options)
    if total <= 0:
        return options[0][0]
    r = rng.random() * total
    for opt, w in options:
        r -= max(w, 0)
        if r < 0:
            return opt
    return options[-1][0]


def _expand(text, rng, depth, lib, missing):
    if depth > MAX_DEPTH:
        raise RecursionError("Wildcards nest too deeply (a wildcard probably refers to itself)")
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            d, j = 0, i
            while j < len(text):
                if text[j] == "{":
                    d += 1
                elif text[j] == "}":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            if j >= len(text):  # unbalanced – leave as text
                out.append(text[i:]); break
            out.append(_variant(text[i + 1:j], rng, depth, lib, missing))
            i = j + 1
            continue
        if text.startswith("__", i):
            m = WILDCARD_RE.match(text, i)
            if m:
                name = m.group(1)
                entries = lib.get(name) if lib else []
                if entries:
                    out.append(_expand(rng.choice(entries), rng, depth + 1, lib, missing))
                else:
                    missing.add(name); out.append(m.group(0))
                i = m.end()
                continue
        out.append(ch); i += 1
    return "".join(out)


def has_syntax(text):
    """True if the text uses wildcards or {a|b} choices (a lone {tag} – NovelAI-style emphasis – is left alone)."""
    return bool(text) and (bool(WILDCARD_RE.search(text)) or bool(re.search(r"\{[^{}]*(\||\$\$)", text)))


def expand(text, seed=None, lib=None, missing=None):
    """Expand one prompt. Same seed + same files = same result. `missing` (a set) collects unknown wildcard names."""
    rng = random.Random(seed)
    miss = set() if missing is None else missing
    res = _expand(text or "", rng, 0, lib, miss)
    return re.sub(r"\s*,\s*(,\s*)+", ", ", res).strip()


def batch(text, n, seed=0, lib=None, unique=True):
    """N variations with seeds seed, seed+1, … Returns [(seed, prompt)]. With unique=True, duplicates are skipped
    (up to 5×n tries) so you get as many different prompts as the lists allow."""
    out, seen, s, tries = [], set(), int(seed or 0), 0
    while len(out) < n and tries < max(5 * n, n + 1):
        p = expand(text, s, lib)
        tries += 1
        if not unique or p not in seen:
            seen.add(p); out.append((s, p))
        s += 1
    return out


def references(text):
    return sorted(set(m.group(1) for m in WILDCARD_RE.finditer(text or "")))


def with_presets(text, characters=(), styles=(), profile=None, seed=None, lib=None):
    """Keep character/style presets fixed while the wildcards change: compose first, then expand
    (wildcards inside a preset's fields are expanded too)."""
    from . import presets
    return expand(presets.compose(text, characters, styles, profile) if (characters or styles) else text, seed, lib)


# ---------------------------------------------------------------- Ollama: write a list
def generate_messages(description, n=30):
    return [{"role": "system", "content": "You write wildcard lists for AI image prompts. Reply with ONLY the list: one short entry "
                                          "per line (a few words, tag style, no numbering, no bullets, no commentary, no duplicates)."},
            {"role": "user", "content": f"Write {int(n)} entries for: {description}"}]


def parse_generated(text, limit=None):
    out, seen = [], set()
    for ln in (text or "").splitlines():
        ln = re.sub(r"^\s*(?:[-*•]+|\d+[.)]|#+)\s*", "", ln).strip().strip('"').strip()
        if not ln or ln.endswith(":") or len(ln) > 120:
            continue
        k = ln.lower()
        if k not in seen:
            seen.add(k); out.append(ln)
    return out[:limit] if limit else out


def suggest_name(description):
    words = re.findall(r"[a-z0-9]+", (description or "").lower())
    stop = {"a", "an", "the", "of", "for", "and", "with", "list", "some", "different", "50", "100", "30"}
    return "_".join([w for w in words if w not in stop][:3]) or "new_list"
