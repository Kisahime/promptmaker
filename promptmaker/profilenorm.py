"""5.2: robust model-profile building – parse a creator's settings out of Civitai description text, normalise them to
canonical ComfyUI + Forge/A1111 names, record where every value came from, validate before saving and repair old files.

Nothing here invents a creator recommendation: values the author did not give come from the family defaults and are
marked as such in profile["source"]; unknown or garbled values are never stored (a warning is recorded instead).
"""
import copy
import datetime
import difflib
import json
import os
import re
import shutil

# ---------------------------------------------------------------- name tables
# ComfyUI sampler → Forge / A1111 display name (None: Forge has no equivalent)
SAMPLERS = {
    "euler": "Euler", "euler_ancestral": "Euler a", "euler_cfg_pp": "Euler", "euler_ancestral_cfg_pp": "Euler a",
    "heun": "Heun", "heunpp2": "Heun", "dpm_2": "DPM2", "dpm_2_ancestral": "DPM2 a", "lms": "LMS",
    "dpm_fast": "DPM fast", "dpm_adaptive": "DPM adaptive", "dpmpp_2s_ancestral": "DPM++ 2S a",
    "dpmpp_sde": "DPM++ SDE", "dpmpp_sde_gpu": "DPM++ SDE", "dpmpp_2m": "DPM++ 2M", "dpmpp_2m_sde": "DPM++ 2M SDE",
    "dpmpp_2m_sde_gpu": "DPM++ 2M SDE", "dpmpp_3m_sde": "DPM++ 3M SDE", "dpmpp_3m_sde_gpu": "DPM++ 3M SDE",
    "ddpm": "DDPM", "lcm": "LCM", "ipndm": "iPNDM", "ipndm_v": "iPNDM_V", "deis": "DEIS", "ddim": "DDIM",
    "uni_pc": "UniPC", "uni_pc_bh2": "UniPC", "res_multistep": None, "er_sde": None, "gradient_estimation": None,
    "restart": "Restart",
}
FORGE_SAMPLERS = {v for v in SAMPLERS.values() if v}
# ComfyUI scheduler → Forge "Schedule type"
SCHEDULERS = {"normal": "Normal", "karras": "Karras", "exponential": "Exponential", "sgm_uniform": "SGM Uniform",
              "simple": "Simple", "ddim_uniform": "DDIM", "beta": "Beta", "linear_quadratic": None, "kl_optimal": "KL Optimal",
              "align_your_steps": "Align Your Steps"}
FORGE_SCHEDULERS = {v for v in SCHEDULERS.values() if v}

# free-text aliases (lower case) → canonical ComfyUI sampler; longest match at the earliest position wins
SAMPLER_ALIASES = {
    "dpm++ 2m sde gpu": "dpmpp_2m_sde_gpu", "dpm++ 2m sde": "dpmpp_2m_sde", "dpm++2m sde": "dpmpp_2m_sde",
    "dpm++ 3m sde": "dpmpp_3m_sde", "dpm++ 2m": "dpmpp_2m", "dpm++2m": "dpmpp_2m", "dpm++ sde": "dpmpp_sde",
    "dpm++ 2s a": "dpmpp_2s_ancestral", "dpm++ 2s ancestral": "dpmpp_2s_ancestral", "dpm2 a": "dpm_2_ancestral",
    "dpm2": "dpm_2", "dpm fast": "dpm_fast", "dpm adaptive": "dpm_adaptive",
    "euler ancestral": "euler_ancestral", "euler a": "euler_ancestral", "euler_a": "euler_ancestral", "eulera": "euler_ancestral",
    "euler": "euler", "eular": "euler", "heun": "heun", "lms": "lms", "ddim": "ddim", "ddpm": "ddpm", "unipc": "uni_pc",
    "uni pc": "uni_pc", "lcm": "lcm", "deis": "deis", "ipndm": "ipndm", "er sde": "er_sde", "er-sde": "er_sde",
    "res multistep": "res_multistep", "res_multistep": "res_multistep", "restart": "restart",
}
SAMPLER_ALIASES.update({k: k for k in SAMPLERS})
SAMPLER_ALIASES.update({v.lower(): k for k, v in SAMPLERS.items() if v and v.lower() not in SAMPLER_ALIASES})

SCHEDULER_ALIASES = {"sgm uniform": "sgm_uniform", "ddim uniform": "ddim_uniform", "kl optimal": "kl_optimal",
                     "align your steps": "align_your_steps", "ays": "align_your_steps", "linear quadratic": "linear_quadratic",
                     "automatic": None, "uniform": "sgm_uniform"}
SCHEDULER_ALIASES.update({k: k for k in SCHEDULERS})

# ---------------------------------------------------------------- family defaults
# Generation defaults per profile family (used only when the creator gave nothing) – sources: official ComfyUI templates.
FAMILY_GEN = {
    "MOSS": {"steps": 25, "cfg": 2.5, "sampler": "er_sde", "scheduler": "simple"},
    "Anima": {"steps": 30, "cfg": 4.0, "sampler": "er_sde", "scheduler": "simple"},
    "FLUX": {"steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
    "Qwen": {"steps": 20, "cfg": 2.5, "sampler": "euler", "scheduler": "simple"},
    "HiDream": {"steps": 28, "cfg": 1.0, "sampler": "lcm", "scheduler": "normal"},
    "Stable Diffusion": {"steps": 28, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal"},
}
# Split (diffusion-model-only) files need separate loaders: workflow (when PromptMaker ships one), text encoder, VAE.
SPLIT_FILES = {
    "moss": {"workflow": "moss_txt2img", "text_encoder": "qwen3.5_9b_w4a8_gptq.safetensors", "vae": "flux2-vae_small.safetensors"},
    "anima": {"text_encoder": "qwen_3_06b_base.safetensors", "vae": "qwen_image_vae.safetensors"},
    "qwen_image": {"text_encoder": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "vae": "qwen_image_vae.safetensors"},
    "flux1": {"text_encoder": "t5xxl_fp8_e4m3fn.safetensors", "vae": "ae.safetensors"},
}
FAMILY_RES_MULTIPLE = {"MOSS": 16, "FLUX": 16, "Qwen": 16, "Anima": 16}
TYPES = ("Checkpoint", "Diffusion model", "LORA", "LoCon", "DoRA", "TextualInversion", "VAE", "Controlnet", "Upscaler",
         "Hypernetwork", "MotionModule", "Other")


# ---------------------------------------------------------------- text helpers
def clean_text(s):
    """Collapse whitespace, drop unbalanced brackets / stray punctuation at the ends."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    for o, c in ("()", "[]", "{}"):
        while s.count(c) > s.count(o) and s.endswith(c):
            s = s[:-1].rstrip()
        while s.count(o) > s.count(c) and s.startswith(o):
            s = s[1:].lstrip()
        if s.count(o) != s.count(c):
            s = s.replace(o, "").replace(c, "")
    s = re.sub(r"^[\s,;:·\-–|/]+|[\s,;:·\-–|/]+$", "", s)
    return s.strip()


def _find_alias(text, aliases):
    low = " " + re.sub(r"[()\[\]{}]", " ", (text or "").lower()) + " "
    best = None
    for k, v in aliases.items():
        for m in re.finditer(r"(?<![a-z0-9+_])" + re.escape(k) + r"(?![a-z0-9+])", low):
            if best is None or m.start() < best[0] or (m.start() == best[0] and len(k) > best[2]):
                best = (m.start(), v, len(k), m.end())
            break
    return best


def canon_sampler(text):
    """Canonical ComfyUI sampler name for free text ('DPM++ 2M Karras', 'dpmpp_2m_sde_gpu', 'Euler Simple') or None."""
    t = (text or "").strip()
    if not t:
        return None
    b = _find_alias(t, SAMPLER_ALIASES)
    if b:
        return b[1]
    w = re.sub(r"[^a-z0-9_+ ]", "", t.lower()).strip()
    m = difflib.get_close_matches(w, list(SAMPLERS), n=1, cutoff=0.85)
    return m[0] if m else None


def canon_scheduler(text):
    """Canonical ComfyUI scheduler for free text ('Karras', 'nomal', 'beta1_1', 'beta)') or None."""
    t = re.sub(r"[()\[\]{}.,;:]", " ", (text or "").lower()).strip()
    if not t:
        return None
    if re.search(r"\bbeta[\w.]*", t):
        return "beta"
    b = _find_alias(t, SCHEDULER_ALIASES)
    if b and b[1]:
        return b[1]
    for word in re.findall(r"[a-z_]+", t):
        m = difflib.get_close_matches(word, [k for k in SCHEDULERS if len(k) > 3], n=1, cutoff=0.75)
        if m:
            return m[0]
    return None


def split_sampler(text):
    """'Euler Simple' / 'dpmpp_2m_sde_gpu + beta1_1' / 'DPM++ 2M Karras' → (sampler, scheduler) canonical or None."""
    t = re.split(r"\s+or\s+|\s*/\s*|\s*\|\s*|\s+或\s*", text or "", maxsplit=1, flags=re.I)[0]
    sampler = canon_sampler(t)
    rest = t
    b = _find_alias(t, SAMPLER_ALIASES)
    if b:
        low = " " + re.sub(r"[()\[\]{}]", " ", t.lower()) + " "
        rest = low[:b[0]] + " " + low[b[3]:]
    sched = canon_scheduler(rest) if rest.strip() else None
    return sampler, sched


def forge_sampler(sampler):
    return SAMPLERS.get(sampler) if sampler else None


def forge_scheduler(sched):
    return SCHEDULERS.get(sched) if sched else None


def comfy_from_forge(name):
    """Forge display name ('DPM++ 2M SDE') → canonical ComfyUI sampler."""
    return canon_sampler(name)


# ---------------------------------------------------------------- numbers
_NUM = r"\d+(?:[.,]\d+)?"
_RANGE = rf"({_NUM})(?:\s*(?:-|–|—|~|to|至|到)\s*({_NUM}))?"


def _f(x):
    return float(str(x).replace(",", "."))


def parse_number(text, kind="cfg"):
    """'3.5 - 5.0' → (3.5, '3.5–5.0'); '25' → (25, '25'). Ranges: CFG uses the lower bound (midpoint when wider than 2), steps the midpoint."""
    m = re.search(_RANGE, text or "")
    if not m:
        return None, ""
    a = _f(m.group(1)); b = _f(m.group(2)) if m.group(2) else None
    if b is not None and b < a:
        a, b = b, a
    if kind == "steps":
        v = int(round((a + b) / 2)) if b is not None else int(round(a))
        if not 1 <= v <= 200:
            return None, ""
        return v, (f"{int(a)}–{int(b)}" if b is not None else str(int(a)))
    v = round(a, 2) if b is None or b - a <= 2 else round((a + b) / 2 * 2) / 2  # narrow range: the creator's start value
    if not 0 < v <= 30:
        return None, ""
    fmt = lambda x: ("%g" % x)  # noqa: E731
    return v, (f"{fmt(a)}–{fmt(b)}" if b is not None else fmt(a))


# ---------------------------------------------------------------- version-aware description parsing
_VER = re.compile(r"(?<![a-z0-9])v\s?(\d+)(?:\.(\d+))?", re.I)
_NOTURBO = re.compile(r"(no|non|without|w/o)[\s\-_]*turbo|无\s*turbo|非\s*turbo|不\s*带?\s*turbo", re.I)


def version_tags(text):
    t = text or ""
    vm = _VER.search(t)
    ver = (int(vm.group(1)), int(vm.group(2)) if vm.group(2) else None) if vm else None
    turbo = "noturbo" if _NOTURBO.search(t) else ("turbo" if re.search(r"turbo|lightning|加速", t, re.I) else None)
    return {"version": ver, "turbo": turbo}


def _score(sec, want):
    s = 0
    if sec["version"] and want["version"]:
        if sec["version"][0] != want["version"][0]:
            return -100
        s += 2
        if sec["version"][1] is not None and want["version"][1] is not None:
            s += 1 if sec["version"][1] == want["version"][1] else -1
    if sec["turbo"]:
        want_t = want["turbo"] or "noturbo"
        if sec["turbo"] != want_t:
            return -100
        s += 2
    return s


def sections(lines):
    """Split description lines into [(tags, [lines])]; a line naming a version/turbo variant starts a new section.
    Lines before any variant marker are the general section (tags None)."""
    out = [(None, [])]
    for ln in lines:
        if not ln:
            continue
        tg = version_tags(ln)
        if (tg["version"] or tg["turbo"]) and len(ln) < 400:
            # a line listing several variants ('12 (turbo) / 30 (V3.0 no turbo)') is ambiguous – keep it on its own
            many = len(_VER.findall(ln)) + len(re.findall(r"turbo", ln, re.I)) > 2
            out.append((tg, [ln]))
            if many:
                out.append(({"version": ("?", None), "turbo": None, "ambiguous": True}, []))
            continue
        out[-1][1].append(ln)
    return [(t, ls) for t, ls in out if ls]


def _label(text, names):
    return re.search(r"(?:" + names + r")\s*(?:[:：=]|is|of)?\s*(.*)", text, re.I)


def extract(text):
    """Settings found in one block of plain text (inline 'steps: 25, cfg: 4' or labelled lines)."""
    r = {}
    t = text or ""
    m = re.search(r"(?:sampling\s+)?steps?\s*[:：=]?\s*(" + _RANGE + r")|(" + _RANGE + r")\s*steps|(?:步数|步)\s*[:：]?\s*(" + _RANGE + ")",
                  t, re.I)
    if m:
        txt = next(g for g in (m.group(1), m.group(4), m.group(7)) if g)
        v, rt = parse_number(txt, "steps")
        if v:
            r["steps"], r["steps_text"] = v, rt
    m = re.search(r"(?:cfg(?:\s*scale)?|guidance(?:\s*scale)?|提示词引导系数|引导系数)\s*[:：=]?\s*(" + _RANGE + ")", t, re.I)
    if m:
        v, rt = parse_number(m.group(1), "cfg")
        if v:
            r["cfg"], r["cfg_text"] = v, rt
    m = re.search(r"(?:sampler|sampling method|采样器|采样方法)\s*(?:name)?\s*[:：=]?\s*([^,;·\n。，]+)", t, re.I)
    raw = m.group(1) if m else ""
    if not raw:
        m = re.search(r"(?:recommended?\s+(?:to\s+use|using|use)?|use|using|推荐(?:使用)?)\s*[:：]?\s*([A-Za-z][^,;·\n。，]*)", t, re.I)
        raw = m.group(1) if m and canon_sampler(m.group(1)) else ""
    if not raw:
        b = _find_alias(t, {k: v for k, v in SAMPLER_ALIASES.items() if "_" in k or "+" in k})
        if b:
            raw = t[max(0, b[0] - 1):][:60].split(",")[0]
    if raw:
        smp, sch = split_sampler(raw)
        if smp:
            r["sampler"], r["sampler_text"] = smp, clean_text(raw)
        if sch:
            r["scheduler"] = sch
    m = re.search(r"(?:scheduler|schedule\s*type|调度器)\s*[:：=]?\s*([A-Za-z_0-9 ]{2,20})", t, re.I)
    if m and canon_scheduler(m.group(1)):
        r["scheduler"] = canon_scheduler(m.group(1))
    m = re.search(r"clip\s*skip\s*[:：=]?\s*(\d+)", t, re.I)
    if m and 1 <= int(m.group(1)) <= 12:
        r["clip_skip"] = int(m.group(1))
    m = re.search(r"(\d{3,4})\s*[x×*]\s*(\d{3,4})", t)
    if m:
        r["resolution"] = f"{m.group(1)}x{m.group(2)}"
    if re.search(r"(no|don'?t|do not|without)\s+(need\s+(a\s+|any\s+)?|use\s+(a\s+|any\s+)?)?negative|negative\s+(prompt\s+)?"
                 r"(is\s+)?(not\s+(needed|required|necessary)|unnecessary|optional|none)|不需要\s*(负面|反向)|无需\s*(负面|反向)", t, re.I):
        r["negative_none"] = True
    return r


def parse_settings(lines, version_name=""):
    """Author settings for the selected version: the best-matching variant section first, then the general text.
    Sections for other versions / the other turbo variant are never used. Returns dict with 'section' (matched header)."""
    want = version_tags(version_name)
    secs = sections(lines)
    general = [ls for t, ls in secs if t is None]
    scored = [(_score(t, want), t, ls) for t, ls in secs if t is not None and not t.get("ambiguous")]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: -x[0])
    out = {}
    if scored:
        out = extract("\n".join(scored[0][2]))
        out["section"] = scored[0][2][0][:120]
        for sc, _, ls in scored[1:]:  # same-score siblings (e.g. 'V5 no turbo' header followed by a steps line)
            for k, v in extract("\n".join(ls)).items():
                out.setdefault(k, v)
    for ls in general:
        for k, v in extract("\n".join(ls)).items():
            out.setdefault(k, v)
    return out


# ---------------------------------------------------------------- normalisation
def family_defaults(family, base_gen=None):
    d = dict(FAMILY_GEN.get(family or "", {}))
    d.update({k: v for k, v in (base_gen or {}).items() if v not in (None, "")})
    return d


def normalise_gen(raw, family="", base_gen=None):
    """raw author values → (gen, source, warnings). gen has canonical sampler/scheduler + Forge names, numeric types."""
    raw = dict(raw or {})
    fam = family_defaults(family, base_gen)
    gen, src, warn = {}, {}, []

    def put(k, v, s):
        if v not in (None, ""):
            gen[k] = v; src[k] = s

    st = raw.get("steps")
    try:
        st = int(round(float(st))) if st not in (None, "") else None
    except (TypeError, ValueError):
        warn.append(f"steps '{st}' is not a number"); st = None
    if st is not None and not 1 <= st <= 200:
        warn.append(f"steps {st} out of range"); st = None
    put("steps", st, "author") if st else put("steps", fam.get("steps"), "family default")
    cfg = raw.get("cfg")
    try:
        cfg = round(float(cfg), 2) if cfg not in (None, "") else None
    except (TypeError, ValueError):
        warn.append(f"cfg '{cfg}' is not a number"); cfg = None
    if cfg is not None and not 0 < cfg <= 30:
        warn.append(f"cfg {cfg} out of range"); cfg = None
    put("cfg", cfg, "author") if cfg else put("cfg", fam.get("cfg"), "family default")
    if raw.get("cfg_text") and src.get("cfg") == "author" and "–" in str(raw["cfg_text"]):
        gen["cfg_range"] = str(raw["cfg_text"])
    smp, sch = None, None
    if raw.get("sampler"):
        smp, sch = split_sampler(str(raw["sampler"]))
        if not smp:
            warn.append(f"unknown sampler '{clean_text(raw['sampler'])}' – using the family default")
    if raw.get("scheduler"):
        s2 = canon_scheduler(str(raw["scheduler"]))
        if s2:
            sch = s2
        else:
            warn.append(f"unknown scheduler '{clean_text(raw['scheduler'])}' – using the family default")
    put("sampler", smp, "author") if smp else put("sampler", fam.get("sampler"), "family default")
    if sch:
        put("scheduler", sch, "author")
    elif smp and raw.get("sampler") and not raw.get("scheduler"):
        put("scheduler", fam.get("scheduler") or "normal", "family default")
    else:
        put("scheduler", fam.get("scheduler"), "family default")
    if gen.get("sampler"):
        fs = forge_sampler(gen["sampler"])
        if fs:
            gen["a1111_sampler"] = fs; src["a1111_sampler"] = src["sampler"]
        else:
            warn.append(f"Forge has no '{gen['sampler']}' sampler – Forge uses its own default")
    if gen.get("scheduler") and forge_scheduler(gen["scheduler"]):
        gen["a1111_scheduler"] = forge_scheduler(gen["scheduler"]); src["a1111_scheduler"] = src["scheduler"]
    cs = raw.get("clip_skip")
    if cs not in (None, ""):
        try:
            cs = int(cs)
            if 1 <= cs <= 12:
                put("clip_skip", cs, "author")
        except (TypeError, ValueError):
            warn.append(f"clip skip '{cs}' is not a number")
    return gen, src, warn


def settings_line(gen, src, raw=None):
    raw = raw or {}
    parts = []
    if gen.get("steps"):
        parts.append(f"Steps {raw.get('steps_text') if src.get('steps') == 'author' and raw.get('steps_text') else gen['steps']}")
    if gen.get("cfg"):
        parts.append(f"CFG {'%g' % gen['cfg']}" + (f" ({gen['cfg_range']})" if gen.get("cfg_range") else ""))
    if gen.get("sampler"):
        parts.append(f"Sampler {gen['sampler']}")
    if gen.get("scheduler"):
        parts.append(f"Scheduler {gen['scheduler']}")
    if gen.get("clip_skip"):
        parts.append(f"Clip skip {gen['clip_skip']}")
    line = " · ".join(parts)
    if any(src.get(k) == "family default" for k in ("steps", "cfg", "sampler", "scheduler")):
        line += " (" + ", ".join(k for k in ("steps", "cfg", "sampler", "scheduler") if src.get(k) == "family default") + \
            ": family default)"
    return line


def snap_res(res, mult):
    try:
        w, h = (int(x) for x in str(res).lower().split("x"))
    except ValueError:
        return res
    return f"{max(mult, round(w / mult) * mult)}x{max(mult, round(h / mult) * mult)}"


def family_resolutions(family, base_res):
    res = dict(base_res or {})
    mult = FAMILY_RES_MULTIPLE.get(family or "")
    if mult:
        res = {k: snap_res(v, mult) for k, v in res.items()}
    return res


def detect_type(civitai_type, file=None, base_model="", unet_only=None):
    """'Checkpoint' / 'Diffusion model' / 'LORA' … from the Civitai type, file format, size and base model."""
    t = civitai_type or "Checkpoint"
    if t != "Checkpoint":
        return t
    if unet_only is None and file is not None:
        from . import civitai_browser as cb
        unet_only = cb.is_unet_only(file, base_model)
    return "Diffusion model" if unet_only else "Checkpoint"


def dangling(text):
    """Trim a sentence that ends with ':' / ',' / '(' (nothing followed it)."""
    t = (text or "").rstrip()
    while t and t[-1] in ":：,(-–·":
        t = t[:-1].rstrip()
        # drop the incomplete trailing clause ("Checkpoint 'X' (Civitai, base Y)")
    return t if t.endswith((".", "!", "?", ")", "\"", "'")) or not t else t + "."


# ---------------------------------------------------------------- validation
def validate(prof):
    """Schema check before save → list of problems (empty = OK)."""
    errs = []
    for k in ("id", "name"):
        if not isinstance(prof.get(k), str) or not prof.get(k).strip():
            errs.append(f"'{k}' is missing")
    g = prof.get("gen") or {}
    if not isinstance(g, dict):
        return errs + ["'gen' must be an object"]
    if "steps" in g and not (isinstance(g["steps"], int) and 1 <= g["steps"] <= 200):
        errs.append(f"gen.steps must be a whole number 1–200 (got {g['steps']!r})")
    if "cfg" in g and not (isinstance(g["cfg"], (int, float)) and 0 < g["cfg"] <= 30):
        errs.append(f"gen.cfg must be a number 0–30 (got {g['cfg']!r})")
    if g.get("sampler") and g["sampler"] not in SAMPLERS:
        errs.append(f"gen.sampler '{g['sampler']}' is not a ComfyUI sampler")
    if g.get("scheduler") and g["scheduler"] not in SCHEDULERS:
        errs.append(f"gen.scheduler '{g['scheduler']}' is not a ComfyUI scheduler")
    if g.get("a1111_sampler") and g["a1111_sampler"] not in FORGE_SAMPLERS:
        errs.append(f"gen.a1111_sampler '{g['a1111_sampler']}' is not a Forge sampler name")
    if g.get("a1111_scheduler") and g["a1111_scheduler"] not in FORGE_SCHEDULERS:
        errs.append(f"gen.a1111_scheduler '{g['a1111_scheduler']}' is not a Forge schedule type")
    if "clip_skip" in g and not (isinstance(g["clip_skip"], int) and 1 <= g["clip_skip"] <= 12):
        errs.append("gen.clip_skip must be 1–12")
    for k, v in (prof.get("resolutions") or {}).items():
        if not re.fullmatch(r"\d{2,5}x\d{2,5}|\d{1,2}:\d{1,2}|auto", str(v)):
            errs.append(f"resolution {k} '{v}' must look like 1024x1024")
    for t in prof.get("tips") or []:
        if not isinstance(t, str) or re.search(r"\(n/a\)|\bn/a\b", t, re.I) or not t.strip():
            errs.append(f"tip '{t}' is empty or 'n/a'")
    for k in ("ai_guidance", "settings"):
        if str(prof.get(k) or "").rstrip().endswith((":", "：", ",")):
            errs.append(f"'{k}' ends with dangling punctuation")
    c = prof.get("civitai")
    if isinstance(c, dict) and c.get("type") and c["type"] not in TYPES:
        errs.append(f"civitai.type '{c['type']}' is unknown")
    return errs


# ---------------------------------------------------------------- repair existing profiles
def repair(prof, family="", base_gen=None):
    """Fix a saved profile in place-safe copy → (fixed, [changes]). Scheduler typos, combined sampler strings,
    Forge names, n/a tips, dangling text, numeric types."""
    p = copy.deepcopy(prof)
    ch = []
    g = p.get("gen")
    if isinstance(g, dict):
        old = dict(g)
        smp_raw = g.get("sampler") or ""
        smp, sch = split_sampler(smp_raw) if smp_raw else (None, None)
        if not smp and g.get("a1111_sampler"):
            smp, s2 = split_sampler(g["a1111_sampler"]); sch = sch or s2
        if smp_raw and not smp:
            g.pop("sampler"); ch.append(f"removed unknown sampler '{smp_raw}'")
        elif smp:
            g["sampler"] = smp
        if g.get("scheduler"):
            s3 = canon_scheduler(g["scheduler"])
            if s3:
                g["scheduler"] = s3
            else:
                ch.append(f"removed unknown scheduler '{g.pop('scheduler')}'")
        a1 = g.get("a1111_sampler") or ""
        if a1:
            a_smp, a_sch = split_sampler(a1)
            sch = sch or a_sch
        if sch and not g.get("scheduler"):
            g["scheduler"] = sch
        elif sch and old.get("scheduler") and canon_scheduler(old["scheduler"]) == "normal" and sch != "normal" and \
                old.get("a1111_sampler") and canon_scheduler(re.sub(r"(?i)^\s*\S+", "", old["a1111_sampler"])):
            g["scheduler"] = sch  # 'Euler Simple' + scheduler 'normal' → the author meant simple
        if g.get("sampler"):
            fs = forge_sampler(g["sampler"])
            if fs:
                g["a1111_sampler"] = fs
            else:
                g.pop("a1111_sampler", None)
        elif a1 and a1 not in FORGE_SAMPLERS:
            g.pop("a1111_sampler", None)
        if g.get("scheduler") and forge_scheduler(g["scheduler"]):
            g["a1111_scheduler"] = forge_scheduler(g["scheduler"])
        for k, typ in (("steps", int), ("clip_skip", int), ("cfg", float)):
            if k in g:
                try:
                    v = typ(round(float(g[k]))) if typ is int else round(float(g[k]), 2)
                    g[k] = v
                except (TypeError, ValueError):
                    ch.append(f"removed non-numeric {k} '{g.pop(k)}'")
        for k in sorted(set(old) | set(g)):
            if old.get(k) != g.get(k) and not k.startswith("a1111_scheduler"):
                ch.append(f"gen.{k}: {old.get(k)!r} → {g.get(k)!r}")
    tips = p.get("tips")
    if isinstance(tips, list):
        new = [t for t in tips if isinstance(t, str) and t.strip() and not re.search(r"\(n/a\)|\bn/a\b", t, re.I)]
        if len(new) != len(tips):
            ch.append(f"removed {len(tips) - len(new)} empty/'n/a' tip(s)"); p["tips"] = new
    for k in ("ai_guidance", "settings"):
        v = p.get(k)
        if isinstance(v, str) and v.rstrip().endswith((":", "：", ",")):
            p[k] = dangling(v); ch.append(f"{k}: trimmed dangling text")
    if isinstance(p.get("settings"), str):
        s = re.sub(r"\b(Scheduler|Sampler)\s+([^·]*?)\)\s*(?=·|$)", lambda m: f"{m.group(1)} {m.group(2)} ", p["settings"])
        s = re.sub(r"\s+·", " ·", s).strip()
        if s != p["settings"]:
            p["settings"] = s; ch.append("settings: removed stray ')'")
    c = p.get("civitai")
    if isinstance(c, dict) and c.get("type") == "Checkpoint" and (family or p.get("family")) in ("MOSS", "Anima") and \
            re.search(r"(fp8|int8|gguf|unet|dit|q\d_k)", str(c.get("file_name") or ""), re.I):
        c["type"] = "Diffusion model"; ch.append("civitai.type: Checkpoint → Diffusion model")
    return p, ch


def repair_file(path, base_profiles=None, backup=True):
    """Repair every profile in a profiles.json; writes a timestamped backup first. Returns {id: [changes]}."""
    data = json.load(open(path, encoding="utf-8"))
    raw = {q.get("id"): q for q in data.get("profiles", [])}
    report, out = {}, []
    for q in data.get("profiles", []):
        par = raw.get(q.get("inherits")) or (base_profiles or {}).get(q.get("inherits")) or {}
        fixed, ch = repair(q, q.get("family") or par.get("family", ""), par.get("gen"))
        if ch:
            report[q.get("id")] = ch
        out.append(fixed)
    if report:
        if backup:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, f"{path}.bak-{stamp}")
        data["profiles"] = out
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    return report


# ---------------------------------------------------------------- AI-assisted extraction (constrained JSON)
EXTRACT_SCHEMA = {"steps": "integer or null", "cfg": "number or null", "sampler": "string or null",
                  "scheduler": "string or null", "clip_skip": "integer or null", "negative": "string or null"}


def ai_extract_messages(description_text, version_name):
    """Chat messages asking a local model for JSON-only settings of one version (validated by normalise_gen)."""
    return [{"role": "system", "content": "Extract the image-generation settings the author recommends for ONE model version. "
             "Reply with JSON only, keys: " + json.dumps(EXTRACT_SCHEMA) + ". Use null when the author does not state a value "
             "for this version. Never guess; never copy settings of other versions."},
            {"role": "user", "content": f"Version: {version_name}\n\nDescription:\n{description_text[:6000]}"}]


def parse_ai_json(text, family="", base_gen=None):
    """Model reply → (gen, source, warnings) via the same normaliser; non-JSON / wrong types are dropped."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    if not isinstance(d, dict):
        d = {}
    d = {k: v for k, v in d.items() if k in EXTRACT_SCHEMA and v not in (None, "", "null")}
    gen, src, warn = normalise_gen(d, family, base_gen)
    src = {k: ("ai" if v == "author" else v) for k, v in src.items()}
    return gen, src, warn
