"""5.0 Local LoRA training (optional extra) with kohya-ss/sd-scripts, run as an external process.

PromptMaker never trains anything itself: the user installs sd-scripts once with the 'Install trainer' button
(git clone + its own venv in <app>/tools/sd-scripts, after a confirmation), then picks 15-50 images, edits the
captions and starts a run. The finished .safetensors is written to Forge's models/Lora folder and linked to the
chosen Character."""
import os
import re
import shutil
import sys

REPO = "https://github.com/kohya-ss/sd-scripts.git"
BRANCH = "sd3"  # supports SDXL / Illustrious LoRA training (sdxl_train_network.py)
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
MIN_IMAGES, MAX_IMAGES = 15, 50
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")

# VRAM presets for SDXL / Illustrious LoRAs (rank, batch, optimiser, memory savers)
PRESETS = {
    "8 GB (slow, low memory)": {"dim": 8, "alpha": 4, "batch": 1, "optimizer": "Adafactor", "lr": 1e-4, "res": 768,
                                "unet_only": True, "cache_te": True, "grad_ckpt": True, "fp8": True},
    "12 GB": {"dim": 16, "alpha": 8, "batch": 1, "optimizer": "AdamW8bit", "lr": 1e-4, "res": 1024,
              "unet_only": True, "cache_te": True, "grad_ckpt": True, "fp8": False},
    "16 GB (recommended)": {"dim": 32, "alpha": 16, "batch": 2, "optimizer": "AdamW8bit", "lr": 1e-4, "res": 1024,
                            "unet_only": False, "cache_te": False, "grad_ckpt": True, "fp8": False},
    "24 GB+ (fast)": {"dim": 32, "alpha": 16, "batch": 4, "optimizer": "AdamW8bit", "lr": 1.5e-4, "res": 1024,
                      "unet_only": False, "cache_te": False, "grad_ckpt": False, "fp8": False},
}
DEFAULT_PRESET = "16 GB (recommended)"


def tools_dir(app_dir):
    return os.path.join(app_dir, "tools", "sd-scripts")


def venv_python(sd_dir):
    win = os.path.join(sd_dir, "venv", "Scripts", "python.exe")
    return win if os.name == "nt" or os.path.exists(win) else os.path.join(sd_dir, "venv", "bin", "python")


def is_installed(sd_dir):
    return os.path.exists(os.path.join(sd_dir, "sdxl_train_network.py")) and os.path.exists(venv_python(sd_dir))


def install_steps(sd_dir, python=None):
    """The commands the 'Install trainer' button runs, in order (shown to the user before they confirm).
    Downloads roughly 5-6 GB (PyTorch + dependencies)."""
    py = python or sys.executable
    vpy = venv_python(sd_dir)
    return [
        ["git", "clone", "--depth", "1", "-b", BRANCH, REPO, sd_dir],
        [py, "-m", "venv", os.path.join(sd_dir, "venv")],
        [vpy, "-m", "pip", "install", "--upgrade", "pip"],
        [vpy, "-m", "pip", "install", "torch", "torchvision", "--index-url", TORCH_INDEX],
        [vpy, "-m", "pip", "install", "-r", os.path.join(sd_dir, "requirements.txt")],
        [vpy, "-m", "pip", "install", "bitsandbytes", "xformers", "--index-url", TORCH_INDEX, "--extra-index-url", "https://pypi.org/simple"],
    ]


def slug(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_") or "lora"


def validate_images(paths):
    ok = [p for p in paths if p.lower().endswith(IMAGE_EXT) and os.path.exists(p)]
    if len(ok) < MIN_IMAGES:
        return ok, f"Pick at least {MIN_IMAGES} images (you have {len(ok)})"
    if len(ok) > MAX_IMAGES:
        return ok[:MAX_IMAGES], f"Using the first {MAX_IMAGES} images"
    return ok, ""


def default_caption(meta, trigger=""):
    """Caption from a gallery image's prompt (LoRA tags and weights removed), trigger word first."""
    txt = re.sub(r"<lora:[^>]+>", "", (meta or {}).get("prompt", ""))
    txt = re.sub(r"\(([^():]+):[\d.]+\)", r"\1", txt)
    parts = [p.strip() for p in re.split(r"[,\n]", txt) if p.strip()]
    if trigger:
        parts = [trigger] + [p for p in parts if p.lower() != trigger.lower()]
    return ", ".join(parts)


def caption_messages(image_png, trigger=""):
    import base64
    return [{"role": "system", "content": "You write training captions for image LoRAs. Reply with one line of "
             "comma-separated booru-style tags describing the subject's appearance, clothing, pose, setting and style. "
             "No sentences, no explanations." + (f" Start with the trigger word '{trigger}'." if trigger else "")},
            {"role": "user", "content": "Caption this image.", "images": [base64.b64encode(image_png).decode()]}]


def clean_caption(text, trigger=""):
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    t = re.sub(r"\s+", " ", first.strip().strip('"').strip())
    if trigger and not t.lower().startswith(trigger.lower()):
        t = f"{trigger}, {t}" if t else trigger
    return t


def prepare_dataset(work_dir, name, items, repeats=10):
    """items: [(image_path, caption)]. Writes the kohya layout <work>/img/<repeats>_<name>/ with .txt captions.
    Returns the train_data_dir."""
    root = os.path.join(work_dir, "img")
    if os.path.isdir(root):
        shutil.rmtree(root)
    d = os.path.join(root, f"{int(repeats)}_{slug(name)}")
    os.makedirs(d)
    for i, (src, cap) in enumerate(items):
        ext = os.path.splitext(src)[1].lower()
        dst = os.path.join(d, f"{i:03d}{ext}")
        shutil.copy2(src, dst)
        with open(dst[:-len(ext)] + ".txt", "w", encoding="utf-8") as f:
            f.write(cap or name)
    return root


def auto_repeats(n_images, target_steps_per_epoch=200):
    return max(1, min(40, round(target_steps_per_epoch / max(1, n_images))))


def build_command(sd_dir, checkpoint, train_dir, out_dir, name, preset=DEFAULT_PRESET, epochs=10, python=None,
                  script=None):
    """argv for one run of sdxl_train_network.py (single GPU, no accelerate config needed)."""
    pr = PRESETS.get(preset, PRESETS[DEFAULT_PRESET])
    cmd = [python or venv_python(sd_dir), script or os.path.join(sd_dir, "sdxl_train_network.py"),
           "--pretrained_model_name_or_path", checkpoint, "--train_data_dir", train_dir, "--output_dir", out_dir,
           "--output_name", slug(name), "--save_model_as", "safetensors", "--network_module", "networks.lora",
           "--network_dim", str(pr["dim"]), "--network_alpha", str(pr["alpha"]),
           "--resolution", f"{pr['res']},{pr['res']}", "--enable_bucket", "--min_bucket_reso", "512",
           "--max_bucket_reso", str(max(1024, pr["res"])), "--bucket_no_upscale",
           "--train_batch_size", str(pr["batch"]), "--max_train_epochs", str(int(epochs)), "--save_every_n_epochs", str(max(1, int(epochs) // 2)),
           "--learning_rate", f"{pr['lr']:g}", "--unet_lr", f"{pr['lr']:g}", "--lr_scheduler", "cosine",
           "--optimizer_type", pr["optimizer"], "--mixed_precision", "bf16", "--save_precision", "fp16",
           "--caption_extension", ".txt", "--cache_latents", "--sdpa", "--seed", "42", "--max_data_loader_n_workers", "0"]
    if pr["optimizer"] == "Adafactor":
        cmd += ["--optimizer_args", "scale_parameter=False", "relative_step=False", "warmup_init=False"]
    if pr["unet_only"]:
        cmd.append("--network_train_unet_only")
    if pr["cache_te"]:
        cmd.append("--cache_text_encoder_outputs")
    if pr["grad_ckpt"]:
        cmd.append("--gradient_checkpointing")
    if pr["fp8"]:
        cmd.append("--fp8_base")
    return cmd


STEP_RE = re.compile(r"steps:\s*(\d+)%.*?(\d+)/(\d+)")
EPOCH_RE = re.compile(r"epoch (\d+)/(\d+)")
LOSS_RE = re.compile(r"avr_loss=([\d.]+)")


def parse_progress(line):
    """{'pct', 'step', 'total', 'epoch', 'epochs', 'loss'} from a kohya/tqdm log line (missing keys = not in line)."""
    out = {}
    m = STEP_RE.search(line)
    if m:
        out.update(pct=int(m.group(1)), step=int(m.group(2)), total=int(m.group(3)))
    m = EPOCH_RE.search(line)
    if m:
        out.update(epoch=int(m.group(1)), epochs=int(m.group(2)))
    m = LOSS_RE.search(line)
    if m:
        out["loss"] = float(m.group(1))
    return out


def forge_lora_dir(forge_dir):
    return os.path.join(forge_dir, "models", "Lora")


def guess_forge_dir():
    for d in (r"C:\AI\sd-webui-forge-classic", r"C:\AI\stable-diffusion-webui-forge", r"C:\AI\forge",
              os.path.expanduser("~/stable-diffusion-webui-forge")):
        if os.path.isdir(os.path.join(d, "models")):
            return d
    return ""


def finished_file(out_dir, name):
    p = os.path.join(out_dir, slug(name) + ".safetensors")
    return p if os.path.exists(p) else ""


def install_output(out_dir, name, lora_dir):
    """Copy the trained LoRA into Forge's models/Lora. Returns the destination path ('' if training wrote nothing)."""
    src = finished_file(out_dir, name)
    if not src:
        return ""
    os.makedirs(lora_dir, exist_ok=True)
    dst = os.path.join(lora_dir, os.path.basename(src))
    shutil.copy2(src, dst)
    return dst
