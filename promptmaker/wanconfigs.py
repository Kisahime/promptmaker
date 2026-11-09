"""Local Wan2GP model presets for the video maker.

Presets come from the installed Wan2GP folder: ``defaults/<id>.json`` is the model
definition and ``settings/<id>_settings.json`` is a version-matched export. The
FastWan image-to-video workflow is the exception: it keeps PromptMaker's existing
template (1280×704, 121 frames, 3 steps). Nothing here downloads or invents a
settings file for a model that does not already have one.
"""
import json
import os
import re
import struct

from . import wan2gp

FASTWAN_ID = "ti2v_2_2_fastwan"
# Read from the installed WanGP 18.84 handlers (models/wan/wan_handler.py,
# models/ltx_video/ltxv_handler.py, models/ltx2/ltx2_handler.py). True means a
# start image ("S") is allowed. False means this video maker's still cannot drive
# it. Missing keys are unverified, not a guess that it will work.
START_IMAGE_18_84 = {
    "ti2v_2_2": True,
    "t2v": False,
    "t2v_1.3B": False,
    "animate": False,
    "ltxv_13B": True,
    "ltx2_19B": True,
    "ltx2_25_22B_msr": False,
}
# family_handler.get_lora_dir in that same WanGP build.
LORA_DIR_18_84 = {
    "ti2v_2_2": "wan_5B",
    "t2v": "wan",
    "t2v_1.3B": "wan_1.3B",
    "animate": "wan_i2v",
}
WAN_5B = {"ti2v_2_2", "lucy_edit", "kiwi_edit"}
# Frames per second read from the installed WanGP 18.84 handlers. Wan 2.2 5B is 24,
# so 121 frames last 5.04 s. Other Wan models are 16 unless named here.
MODEL_FPS_18_84 = {
    "ti2v_2_2": 24, "lucy_edit": 24, "kiwi_edit": 24,
    "animate": 30, "fantasy": 23, "ltxv_13B": 30, "ltx2_19B": 24, "ltx2_25_22B_msr": 24,
}
# Wan's own frame grid for this install: minimum and step. Counts are 4n+1 for Wan (5, 9, …)
# and 8n+1 for LTX (17, 25, …). wgp.py fits a requested length upward ("ceil").
FRAME_GRID_18_84 = {
    "ti2v_2_2": (5, 4), "t2v": (5, 4), "t2v_1.3B": (5, 4), "animate": (5, 4),
    "ltxv_13B": (17, 8), "ltx2_19B": (17, 8), "ltx2_25_22B_msr": (17, 8),
}
WAN_OTHER = {"t2v", "t2v_1.3B", "t2v_2_2", "animate", "i2v", "i2v_2_2", "fun_inp", "fun_inp_1.3B"}
KEPT = "Completed clips were kept."
NO_DOWNLOAD = "Nothing was downloaded."


def default_animation():
    """Project animation defaults: the tested FastWan template, creative LoRA off."""
    with open(wan2gp.TEMPLATE, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "model_id": data.get("model_type") or FASTWAN_ID,
        "resolution": data.get("resolution") or "1280x704",
        "frames": int(data.get("video_length") or 121),
        "steps": int(data.get("num_inference_steps") or 3),
        "guidance": data.get("guidance_scale", 1),
        "flow_shift": data.get("flow_shift", 3),
        "creative_lora": "",
        "creative_strength": 1.0,
    }


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _quoted(text, name):
    token = name + " = \""
    i = text.find(token)
    if i < 0:
        token = name + "='"
        i = text.find(token)
    if i < 0:
        return ""
    i += len(token)
    end = text.find(token[-1], i)
    return text[i:end] if end > i else ""


def install_versions(wan_dir):
    """(WanGP version, settings_version) parsed from this folder's wgp.py. ('', '') if unreadable."""
    text = _read(os.path.join(wan_dir or "", "wgp.py"))
    version = _quoted(text, "WanGP_version")
    settings = ""
    for line in text.splitlines():
        if line.startswith("settings_version"):
            try:
                settings = str(float(line.split("=", 1)[1].strip()))
            except ValueError:
                settings = ""
            break
    if settings.endswith(".0"):
        settings = settings[:-2]
    return version, settings


def offline_support(wan_dir):
    """(True, '') when this install's own source defines --offline and sets HF_HUB_OFFLINE.

    Public documentation is not used. A missing switch is a blocker: the run is refused
    instead of dropping the flag or upgrading Wan2GP.
    """
    root = wan_dir or ""
    wgp = os.path.join(root, "wgp.py")
    cli = os.path.join(root, "shared", "cli_args.py")
    if not (root and os.path.isfile(wgp)):
        return False, "Wan2GP not found – set its folder in Video → Tools. " + NO_DOWNLOAD
    wgp_text, cli_text = _read(wgp), _read(cli)
    flag = "--offline" in cli_text and "store_true" in cli_text
    env = "HF_HUB_OFFLINE" in wgp_text and "--offline" in wgp_text
    if flag and env:
        return True, ""
    return False, (
        "Offline protection is not in this Wan2GP install (" + root + "). "
        "PromptMaker will not start it, because a missing file could otherwise be downloaded, "
        "and this copy will not upgrade Wan2GP. Use an install whose shared/cli_args.py defines "
        "--offline and whose wgp.py sets HF_HUB_OFFLINE. " + NO_DOWNLOAD
    )


def _config(wan_dir):
    data = _load(os.path.join(wan_dir or "", "wgp_config.json")) or {}
    paths = data.get("checkpoints_paths") or ["ckpts", "."]
    return {
        "transformer_quantization": str(data.get("transformer_quantization") or "int8"),
        "text_encoder_quantization": str(data.get("text_encoder_quantization") or "int8"),
        "checkpoints_paths": paths,
        "loras_root": data.get("loras_root") or "loras",
    }


def _abs(wan_dir, path):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(wan_dir, path))


def find_weight(wan_dir, config, filename, folders=()):
    """A checkpoint file that is already on disk, or '' . Does not download."""
    name = os.path.basename(str(filename).split("|", 1)[0])
    if not name:
        return ""
    roots = [_abs(wan_dir, p) for p in config.get("checkpoints_paths") or ["ckpts"]]
    app = os.path.normcase(os.path.abspath(wan_dir))
    for root in roots:
        if os.path.isfile(os.path.join(root, name)):
            return os.path.join(root, name)
        for folder in folders:
            nested = os.path.join(root, folder, name)
            if os.path.isfile(nested):
                return nested
    for root in roots:
        if os.path.normcase(os.path.abspath(root)) == app or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if name in files:
                return os.path.join(dirpath, name)
    return ""


def _url_list(defs, model_id, stack=()):
    if model_id in stack or model_id not in defs:
        return []
    model = (defs[model_id].get("model") or {})
    urls = model.get("URLs", [])
    if isinstance(urls, str):
        return _url_list(defs, urls, stack + (model_id,))
    return list(urls) if isinstance(urls, list) else []


def _pick_weight(urls, quantization):
    names = [os.path.basename(str(u).split("|", 1)[0]) for u in urls if u]
    quant = (quantization or "").lower()
    if quant and quant != "bf16":
        hit = [name for name in names if quant in name.lower()]
        if hit:
            return hit[0]
    return names[0] if names else ""


def _number(source, key):
    if not isinstance(source, dict) or key not in source or source[key] in (None, ""):
        return None
    return source[key]


def _controls_from(source, fallback):
    out = dict(fallback)
    mapping = (("resolution", "resolution"), ("frames", "video_length"), ("steps", "num_inference_steps"),
               ("guidance", "guidance_scale"), ("flow_shift", "flow_shift"))
    for dest, src in mapping:
        value = _number(source, src)
        if value is not None:
            out[dest] = int(value) if dest in ("frames", "steps") else value
    return out


def _lora_names(model):
    raw = model.get("loras") or []
    if isinstance(raw, str):
        raw = [raw]
    return [os.path.basename(str(item).split("|", 1)[0]) for item in raw if item]


def _companion_specs(architecture, text_quant):
    if architecture not in WAN_5B and architecture not in WAN_OTHER:
        return []
    quant = (text_quant or "int8").lower()
    encoder = ("models_t5_umt5-xxl-enc-quanto_int8.safetensors" if quant == "int8"
               else "models_t5_umt5-xxl-enc-bf16.safetensors")
    specs = [("text encoder", encoder, ("umt5-xxl",))]
    for name in ("special_tokens_map.json", "spiece.model", "tokenizer.json", "tokenizer_config.json"):
        specs.append(("tokenizer", name, ("umt5-xxl",)))
    if architecture in WAN_5B:
        specs.append(("VAE", "Wan2.2_VAE.safetensors", ()))
    elif architecture in WAN_OTHER:
        specs.append(("VAE", "Wan2.1_VAE.safetensors", ()))
        specs.append(("CLIP", "models_clip_open-clip-xlm-roberta-large-vit-huge-14-bf16.safetensors", ("xlm-roberta-large",)))
        for name in ("sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"):
            specs.append(("CLIP tokenizer", name, ("xlm-roberta-large",)))
    return specs


def _file_entry(role, name, path):
    return {"role": role, "name": name, "present": bool(path), "path": path}


def safetensors_metadata(path):
    """Header metadata only. A file without it is unverified, not compatible."""
    try:
        with open(path, "rb") as f:
            size = struct.unpack("<Q", f.read(8))[0]
            if size <= 0 or size > 2_000_000:
                return {}
            header = json.loads(f.read(size).decode("utf-8"))
    except (OSError, ValueError, struct.error, UnicodeError):
        return {}
    meta = header.get("__metadata__") if isinstance(header, dict) else None
    if not isinstance(meta, dict):
        return {}
    return {str(k): str(v) for k, v in meta.items() if v is not None}


def _family(architecture):
    arch = architecture or ""
    if arch in WAN_5B:
        return "wan5"
    if "1.3" in arch:
        return "wan13"
    if arch in WAN_OTHER or arch.startswith("t2v") or arch.startswith("i2v"):
        return "wan14"
    if arch.startswith("ltx"):
        return "ltx"
    return ""


def lora_status(path, architecture, required_names):
    """required | missing | incompatible | compatible | unverified.

    A folder name is not evidence. Compatible requires metadata that names this
    family. Conflicting metadata is incompatible. Empty metadata stays unverified.
    """
    name = os.path.basename(path or "")
    if name and name in set(required_names or []):
        return "required"
    if not path or not os.path.isfile(path):
        return "missing"
    if str(path).startswith(("http:", "https:")):
        return "missing"
    meta = safetensors_metadata(path)
    if not meta:
        return "unverified"
    blob = " ".join(meta.values()).lower()
    markers = {
        "wan5": ("ti2v", "wan2.2", "wan 2.2", "5b"),
        "wan13": ("1.3b", "1_3b"),
        "wan14": ("14b",),
        "ltx": ("ltx",),
    }
    foreign = ("sdxl", "illustrious", "pony", "flux", "qwen")
    family = _family(architecture)
    own = markers.get(family, ())
    has_own = any(token in blob for token in own)
    other_hit = False
    for key, tokens in markers.items():
        if key != family and any(token in blob for token in tokens):
            other_hit = True
    if any(token in blob for token in foreign) and family in ("wan5", "wan13", "wan14", "ltx"):
        other_hit = True
    if other_hit and not has_own:
        return "incompatible"
    if has_own and not other_hit:
        return "compatible"
    return "unverified"


def _load_defs(wan_dir, model_ids):
    """Read only the definition files this preset list names, plus one URL alias hop."""
    folder = os.path.join(wan_dir or "", "defaults")
    defs = {}
    pending = list(model_ids)
    seen = set()
    while pending:
        model_id = pending.pop()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        data = _load(os.path.join(folder, model_id + ".json"))
        if not data or not isinstance(data.get("model"), dict):
            continue
        defs[model_id] = data
        urls = data["model"].get("URLs")
        if isinstance(urls, str):
            pending.append(urls)
    return defs


def _start_image(version, architecture, model_id):
    if model_id == FASTWAN_ID and version == "18.84":
        return True
    if version != "18.84":
        return None
    return START_IMAGE_18_84.get(architecture)


def _one_preset(wan_dir, config, defs, model_id, version, settings_version, offline):
    definition = defs.get(model_id)
    if not definition and model_id != FASTWAN_ID:
        return None
    model = (definition or {}).get("model") or {}
    architecture = model.get("architecture") or ("ti2v_2_2" if model_id == FASTWAN_ID else "")
    export_path = os.path.join(wan_dir, "settings", model_id + "_settings.json")
    export = _load(export_path)
    bundled = default_animation()
    if model_id == FASTWAN_ID:
        controls = bundled
        template_id = "promptmaker:assets/wan2gp_fastwan_i2v.json"
        settings_path = wan2gp.TEMPLATE
        used_version = _load(wan2gp.TEMPLATE).get("settings_version")
    elif export:
        controls = _controls_from(export, _controls_from(definition, bundled))
        controls["model_id"] = model_id
        template_id = "wan2gp:settings/" + model_id + "_settings.json"
        settings_path = export_path
        used_version = export.get("settings_version")
    else:
        return None
    urls = _url_list(defs, model_id)
    weight_name = _pick_weight(urls, config["transformer_quantization"])
    files = []
    if weight_name:
        found = find_weight(wan_dir, config, weight_name)
        files.append(_file_entry("transformer", weight_name, found))
    elif definition:
        files.append(_file_entry("transformer", "(no weight listed in the model definition)", ""))
    lora_key = LORA_DIR_18_84.get(architecture, "") if version == "18.84" else ""
    lora_root = _abs(wan_dir, config["loras_root"])
    required = _lora_names(model)
    for name in required:
        found = ""
        if lora_key:
            candidate = os.path.join(lora_root, lora_key, name)
            if os.path.isfile(candidate):
                found = candidate
        if not found:
            found = find_weight(wan_dir, config, name)
        files.append(_file_entry("acceleration adapter", name, found))
    for role, name, folders in _companion_specs(architecture, config["text_encoder_quantization"]):
        files.append(_file_entry(role, name, find_weight(wan_dir, config, name, folders)))
    for item in model.get("preload_URLs") or []:
        name = os.path.basename(str(item).split("|", 1)[0])
        if name:
            files.append(_file_entry("preload", name, find_weight(wan_dir, config, name)))
    files_ready = bool(definition) and bool(files) and all(item["present"] for item in files)
    if model_id == FASTWAN_ID and not definition:
        files_ready = False
    creative = []
    if lora_key and os.path.isdir(os.path.join(lora_root, lora_key)):
        folder = os.path.join(lora_root, lora_key)
        for name in sorted(os.listdir(folder)):
            if not name.endswith((".safetensors", ".sft")) or name in required:
                continue
            path = os.path.join(folder, name)
            creative.append({"name": name, "path": path, "status": lora_status(path, architecture, required)})
    note = ""
    if architecture not in WAN_5B and architecture not in WAN_OTHER:
        note = "Only the files named by this model definition were checked, not every file that family can load."
    return {
        "id": model_id,
        "name": model.get("name") or model_id,
        "architecture": architecture,
        "description": model.get("description") or "",
        "definition": bool(definition),
        "definition_path": os.path.join(wan_dir, "defaults", model_id + ".json") if definition else "",
        "settings_path": settings_path,
        "template_id": template_id,
        "settings_version": used_version,
        "install_settings_version": settings_version,
        "wangp_version": version,
        "offline": offline,
        "tested": model_id == FASTWAN_ID,
        "start_image": _start_image(version, architecture, model_id),
        "resolution": str(controls["resolution"]),
        "frames": int(controls["frames"]),
        "steps": int(controls["steps"]),
        "guidance": controls["guidance"],
        "flow_shift": controls["flow_shift"],
        "files": files,
        "files_ready": files_ready,
        "required_loras": required,
        "lora_dir": os.path.join(lora_root, lora_key) if lora_key else "",
        "creative_loras": creative,
        "note": note,
        "export_present": bool(export),
        "fps": MODEL_FPS_18_84.get(architecture) if version == "18.84" else (24 if model_id == FASTWAN_ID else None),
        "frames_minimum": (FRAME_GRID_18_84.get(architecture) or (5, 4))[0],
        "frames_steps": (FRAME_GRID_18_84.get(architecture) or (5, 4))[1],
    }


def catalog(wan_dir):
    """Local presets: the bundled FastWan workflow, plus exports that match a definition."""
    version, settings_version = install_versions(wan_dir)
    offline, _reason = offline_support(wan_dir)
    config = _config(wan_dir)
    ids = [FASTWAN_ID]
    settings_dir = os.path.join(wan_dir or "", "settings")
    if os.path.isdir(settings_dir):
        for name in sorted(os.listdir(settings_dir)):
            if name.endswith("_settings.json"):
                model_id = name[: -len("_settings.json")]
                if model_id not in ids:
                    ids.append(model_id)
    defs = _load_defs(wan_dir, ids)
    presets = []
    for model_id in ids:
        preset = _one_preset(wan_dir, config, defs, model_id, version, settings_version, offline)
        if preset:
            presets.append(preset)
    if not any(p["id"] == FASTWAN_ID for p in presets):
        presets.insert(0, _bundled_stub())
    presets.sort(key=lambda p: (p["id"] != FASTWAN_ID, not p["files_ready"], not p["start_image"], p["name"].lower()))
    return presets


def _bundled_stub():
    base = default_animation()
    data = _load(wan2gp.TEMPLATE) or {}
    return {
        "id": FASTWAN_ID, "name": "Wan2.2 TextImage2video FastWan 5B", "architecture": "ti2v_2_2",
        "description": "", "definition": False, "definition_path": "", "settings_path": wan2gp.TEMPLATE,
        "template_id": "promptmaker:assets/wan2gp_fastwan_i2v.json", "settings_version": data.get("settings_version"),
        "install_settings_version": "", "wangp_version": "", "offline": False, "tested": True, "start_image": True,
        "resolution": base["resolution"], "frames": base["frames"], "steps": base["steps"],
        "guidance": base["guidance"], "flow_shift": base["flow_shift"], "files": [], "files_ready": False,
        "required_loras": [], "lora_dir": "", "creative_loras": [], "note": "", "export_present": False, "fps": 24,
        "frames_minimum": 5, "frames_steps": 4,
    }


def preset_by_id(wan_dir, model_id):
    for preset in catalog(wan_dir):
        if preset["id"] == model_id:
            return preset
    if model_id == FASTWAN_ID:
        return _bundled_stub()
    return None


def status_line(preset):
    if not preset:
        return "No model selected"
    definition = "present" if preset.get("definition") else "missing"
    missing = [item["name"] for item in preset.get("files") or [] if not item.get("present")]
    if preset.get("files_ready"):
        files = "ready"
    elif missing:
        files = "missing " + ", ".join(missing[:3])
        if len(missing) > 3:
            files += f" (+{len(missing) - 3} more)"
    elif not preset.get("definition"):
        files = "not checked (model definition missing)"
    else:
        files = "not checked"
    tested = "yes" if preset.get("tested") else "no"
    start = preset.get("start_image")
    mode = "image-to-video" if start is True else ("not image-to-video" if start is False else "image-to-video not verified")
    offline = "verified" if preset.get("offline") else "not available"
    return f"Definition: {definition} · Files: {files} · Tested: {tested} · {mode} · Offline: {offline}"


def _same(a, b):
    try:
        if float(a) == float(b):
            return True
    except (TypeError, ValueError):
        pass
    return str(a) == str(b)


def incompatible_changes(previous, preset):
    """Human-readable resets when leaving one model for another. Empty when the model is unchanged."""
    if not previous or not preset or previous.get("model_id") == preset.get("id"):
        return []
    notes = []
    for key, label in (("resolution", "resolution"), ("frames", "frames"), ("steps", "steps"),
                       ("guidance", "guidance"), ("flow_shift", "flow shift")):
        old, new = previous.get(key), preset.get(key)
        if old is not None and new is not None and not _same(old, new):
            notes.append(f"{label} {old} → {new}")
    if previous.get("creative_lora"):
        notes.append("creative LoRA cleared (it is not carried onto the new model)")
    return notes


def custom_notes(controls, preset):
    if not preset:
        return []
    notes = []
    for key, label in (("resolution", "resolution"), ("frames", "frames"), ("steps", "steps"),
                       ("guidance", "guidance"), ("flow_shift", "flow shift")):
        if controls.get(key) is not None and preset.get(key) is not None and not _same(controls.get(key), preset.get(key)):
            notes.append(f"{label} is {controls.get(key)} (this model's recorded value is {preset.get(key)})")
    return notes


def block_size(preset):
    """Wan VAE alignment for this install. Wan 2.2 5B is 32, so 720x1280 is sent as 704x1280."""
    arch = (preset or {}).get("architecture") or ""
    if arch in WAN_5B or (preset or {}).get("id") == FASTWAN_ID:
        return 32
    if arch in WAN_OTHER or arch in FRAME_GRID_18_84 and arch.startswith(("t2v", "i2v", "animate")):
        return 16
    return None


def align_resolution(value, block):
    if not value or not block:
        return str(value or "")
    width, height = [int(part) for part in str(value).lower().split("x")]
    block = int(block)
    width = max(block, width // block * block)
    height = max(block, height // block * block)
    return f"{width}x{height}"


def _builtin_resolutions(wan_dir):
    """The resolution menu from this WanGP install, without its 4K list (that switch is off in wgp_config)."""
    text = _read(os.path.join(wan_dir or "", "shared", "resolutions.py"))
    start = text.find("DEFAULT_RESOLUTION_CHOICES = [")
    if start < 0:
        return []
    end = text.find("\n]", start)
    block = text[start:end if end > start else start + 5000]
    found = []
    for width, height in re.findall(r'"(\d+)x(\d+)"', block):
        item = f"{int(width)}x{int(height)}"
        if item not in found:
            found.append(item)
    return found


def resolution_choices(preset, wan_dir=""):
    """Landscape and portrait sizes this model can be asked for. The model's own default stays first."""
    preset = preset or {}
    block = block_size(preset)
    default = align_resolution(preset.get("resolution") or "1280x704", block)
    values = []
    for item in [default, * _builtin_resolutions(wan_dir)]:
        value = align_resolution(item, block)
        if value and value not in values:
            values.append(value)
    width, height = default.split("x")
    swapped = align_resolution(f"{height}x{width}", block)
    if swapped not in values:
        values.insert(1, swapped)
    portrait = [v for v in values if int(v.split("x")[1]) > int(v.split("x")[0])]
    rest = [v for v in values if v not in portrait and v != default]
    ordered = [default]
    for value in portrait + rest:
        if value not in ordered:
            ordered.append(value)
    return ordered


def match_resolution(value, choices):
    """The list entry for a saved size, including one Wan has aligned to its block."""
    if not value or not choices:
        return ""
    text = str(value).lower()
    if text in choices:
        return text
    for block in (32, 16):
        aligned = align_resolution(text, block)
        if aligned in choices:
            return aligned
    return ""


def model_fps(preset):
    """Frames per second for this preset, or None when this WanGP version was not inspected."""
    if not preset:
        return None
    fps = preset.get("fps")
    return int(fps) if fps else None


def frames_to_seconds(frames, fps):
    """Playback length of `frames` at this model's frame rate. Wan counts every generated frame."""
    return int(frames) / float(fps)


def frames_for_seconds(seconds, fps, minimum=5, step=4):
    """Frames for one clip of `seconds`, fitted the way this WanGP does (round to a frame, then round up to the step).

    4 + 6 + 9 seconds at 24 fps is 456 frames. Wan will not generate 96, 144 or 216, because its
    step is 4 and the count has to land on 4n+1, so those become 97, 145 and 217.
    """
    import math
    raw = max(int(minimum), int(round(float(seconds) * float(fps))))
    step = max(1, int(step))
    if step <= 1:
        return raw
    return math.ceil(max(0, raw - 1) / step) * step + 1


def frame_grid(preset):
    """(minimum, step) for this preset, or Wan's 5 / 4 when the architecture is a known Wan model."""
    if not preset:
        return 5, 4
    if preset.get("frames_minimum") and preset.get("frames_steps"):
        return int(preset["frames_minimum"]), int(preset["frames_steps"])
    grid = FRAME_GRID_18_84.get(preset.get("architecture") or "")
    return grid if grid else (5, 4)


def scene_frame_plan(scenes, fps, minimum=5, step=4):
    """One line relating each animated scene's length to the frames Wan is given, plus the total."""
    secs_total = round(sum(float(s.get("duration") or 0) for s in scenes), 2)
    if not fps:
        return f"Total {secs_total:.2f} s. This model's frame rate was not verified, so frames are not calculated from the length."
    parts, raw_total, fit_total = [], 0, 0
    for s in scenes:
        if not s.get("animate"):
            continue
        secs = float(s.get("duration") or 0)
        raw = int(round(secs * float(fps)))
        fitted = frames_for_seconds(secs, fps, minimum, step)
        raw_total += raw
        fit_total += fitted
        parts.append(f"{s.get('id', '?')} {secs:.2f}s → {fitted}")
    if not parts:
        return f"Total {secs_total:.2f} s. Tick Animate and each scene's frames are its length × {int(fps)}."
    text = f"Total {secs_total:.2f} s · {raw_total} frames at {int(fps)} fps"
    if fit_total != raw_total:
        text += f", sent as {fit_total} ({', '.join(parts)}) because Wan's frame step rounds up"
    else:
        text += f" ({', '.join(parts)})"
    return text


def frames_length_text(frames, fps):
    if not fps:
        return f"{int(frames)} frames. This model's frame rate was not verified, so the seconds are not estimated."
    return f"{int(frames)} frames = {frames_to_seconds(frames, fps):.2f} s at {int(fps)} fps."


def describe(controls, preset=None):
    name = (preset or {}).get("name") or controls.get("name") or controls.get("model_id") or FASTWAN_ID
    lora = os.path.basename(controls.get("creative_lora") or "") or "None"
    body = (f"{name} · {controls.get('resolution')} · {controls.get('frames')} frames · "
            f"{controls.get('steps')} steps · guidance {controls.get('guidance')} · creative LoRA {lora}")
    source = controls.get("_source")
    if source == "recorded":
        return "Recorded for this clip: " + body + ". Resume uses this, not the current project defaults."
    if source == "override":
        return "Override: " + body
    return "Inherited from project: " + body


def _size(resolution):
    w, h = str(resolution).lower().split("x")
    return int(w), int(h)


def build_settings(preset, prompt, image, seed, controls):
    """A settings dict for wgp.py --process.

    FastWan with no creative LoRA goes through wan2gp.settings(), so the tested template
    stays intact. Other models start from their exported settings file. Creative LoRA None
    leaves activated_loras empty; required acceleration adapters are not copied into it.
    """
    controls = controls or {}
    creative = controls.get("creative_lora") or ""
    strength = controls.get("creative_strength", 1.0)
    if preset["id"] == FASTWAN_ID:
        cfg = wan2gp.settings(prompt, image, seed, int(controls.get("frames", preset["frames"])),
                              int(controls.get("steps", preset["steps"])),
                              _size(controls.get("resolution", preset["resolution"])))
        if not _same(controls.get("guidance", preset["guidance"]), preset["guidance"]):
            cfg["guidance_scale"] = controls.get("guidance")
        if not _same(controls.get("flow_shift", preset["flow_shift"]), preset["flow_shift"]):
            cfg["flow_shift"] = controls.get("flow_shift")
    else:
        cfg = _load(preset.get("settings_path") or "")
        if not cfg:
            raise wan2gp.WanError(
                f"No version-matched settings file for {preset.get('name') or preset['id']}. "
                "PromptMaker does not invent one. " + NO_DOWNLOAD)
        cfg = json.loads(json.dumps(cfg))
        cfg.update(prompt=prompt, image_start=os.path.abspath(image),
                   seed=int(seed if seed not in (None, -1, "") else 42),
                   video_length=int(controls.get("frames", preset["frames"])),
                   num_inference_steps=int(controls.get("steps", preset["steps"])),
                   resolution="{0}x{1}".format(*_size(controls.get("resolution", preset["resolution"]))),
                   sliding_window_size=int(controls.get("frames", preset["frames"])),
                   model_type=preset["id"],
                   guidance_scale=controls.get("guidance", preset["guidance"]),
                   flow_shift=controls.get("flow_shift", preset["flow_shift"]))
        if preset.get("start_image") is True and "S" not in str(cfg.get("image_prompt_type") or ""):
            cfg["image_prompt_type"] = "S"
    if creative:
        cfg["activated_loras"] = [os.path.abspath(creative)]
        cfg["loras_multipliers"] = _strength_text(strength)
    else:
        cfg["activated_loras"] = []
        cfg["loras_multipliers"] = ""
    return cfg


def _strength_text(strength):
    try:
        value = float(strength)
    except (TypeError, ValueError):
        value = 1.0
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def snapshot(preset, controls, image_rel):
    """What one clip was actually asked to use, so resume does not pick up later default edits."""
    return {
        "model_id": preset["id"],
        "name": preset.get("name") or preset["id"],
        "architecture": preset.get("architecture") or "",
        "template": preset.get("template_id") or "",
        "settings_version": preset.get("settings_version"),
        "wangp_version": preset.get("wangp_version") or "",
        "resolution": str(controls.get("resolution") or preset.get("resolution")),
        "frames": int(controls.get("frames") or preset.get("frames") or 0),
        "steps": int(controls.get("steps") or preset.get("steps") or 0),
        "guidance": controls.get("guidance", preset.get("guidance")),
        "flow_shift": controls.get("flow_shift", preset.get("flow_shift")),
        "creative_lora": controls.get("creative_lora") or "",
        "creative_strength": controls.get("creative_strength", 1.0),
        "required_loras": list(preset.get("required_loras") or []),
        "image": image_rel,
        "offline": bool(preset.get("offline")),
    }


def preflight(wan_dir, preset, controls, image):
    """Named problems that should stop a job before Wan2GP starts. Empty means the known checks passed.

    This is not a dry run and it does not prove every dependency or that the job fits in VRAM.
    """
    errors = []
    ok, reason = offline_support(wan_dir)
    if not ok:
        errors.append(reason if NO_DOWNLOAD in reason else reason + " " + NO_DOWNLOAD)
        return errors
    if not preset:
        errors.append("That model is not one of the local presets. " + NO_DOWNLOAD)
        return errors
    if not preset.get("definition"):
        errors.append(
            f"Model definition defaults/{preset['id']}.json is not in this Wan2GP folder. " + NO_DOWNLOAD)
    version, settings_version = install_versions(wan_dir)
    if not version or not settings_version:
        errors.append("Could not read WanGP_version and settings_version from this install's wgp.py. " + NO_DOWNLOAD)
    elif str(preset.get("settings_version")) != str(settings_version):
        errors.append(
            f"Settings file for {preset.get('name')} is version {preset.get('settings_version')}, "
            f"but this Wan2GP uses settings version {settings_version}. The file was not rewritten. " + NO_DOWNLOAD)
    elif version != "18.84" and preset["id"] != FASTWAN_ID:
        errors.append(
            f"Image-to-video support was inspected for WanGP 18.84, and this install is {version}. "
            f"{preset.get('name')} was not started. " + NO_DOWNLOAD)
    if preset.get("start_image") is False:
        errors.append(
            f"{preset.get('name')} does not accept a start image, so it cannot animate a still. "
            "Choose an image-to-video model such as FastWan 5B. " + NO_DOWNLOAD)
    elif preset.get("start_image") is not True:
        errors.append(
            f"Start-image support for {preset.get('name')} ({preset.get('architecture')}) "
            "was not verified in this Wan2GP version. " + NO_DOWNLOAD)
    missing = [f"{item['name']} ({item['role']})" for item in preset.get("files") or [] if not item.get("present")]
    if not preset.get("files_ready"):
        if missing:
            errors.append("Missing " + ", ".join(missing) + ". " + NO_DOWNLOAD)
        elif preset.get("definition"):
            errors.append(f"Required files for {preset.get('name')} are not all on disk. " + NO_DOWNLOAD)
    if not image or not os.path.isfile(image):
        errors.append("The scene still is missing. Make stills first. " + NO_DOWNLOAD)
    creative = (controls or {}).get("creative_lora") or ""
    if creative:
        if str(creative).startswith(("http:", "https:")):
            errors.append("Creative LoRA must be a local file. " + NO_DOWNLOAD)
        elif os.path.basename(creative) in set(preset.get("required_loras") or []):
            errors.append(
                f"{os.path.basename(creative)} is a required acceleration adapter. "
                "Choose None to leave it on without adding a creative LoRA. " + NO_DOWNLOAD)
        elif not os.path.isfile(creative):
            errors.append(f"Creative LoRA file is missing: {creative}. " + NO_DOWNLOAD)
        elif lora_status(creative, preset.get("architecture"), preset.get("required_loras")) == "incompatible":
            errors.append(
                f"Creative LoRA {os.path.basename(creative)} does not match {preset.get('architecture')} "
                "(its file metadata names a different model family). " + NO_DOWNLOAD)
    return errors
