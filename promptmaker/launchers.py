"""6.1 Start Forge / Start ComfyUI: find each backend's launcher script and start it in its own console window.

Nothing here talks to the network; the window polls backenddetect after launching."""
import os
import subprocess
import sys

KINDS = ("a1111", "comfyui")
NAMES = {"a1111": "Forge", "comfyui": "ComfyUI"}
WINDOWS = sys.platform == "win32"
# Launcher file names, best first. webui-user.bat holds COMMANDLINE_ARGS (--api) for Forge / A1111.
SCRIPTS = {
    "a1111": ("webui-user.bat", "run.bat", "webui.bat") if WINDOWS else ("webui-user.sh", "webui.sh"),
    "comfyui": ("run_nvidia_gpu.bat", "run_nvidia_gpu_fast_fp16_accumulation.bat", "run_amd_gpu.bat", "run_cpu.bat")
    if WINDOWS else ("run.sh", "start.sh"),
}
KNOWN = {
    "a1111": [r"C:\AI\sd-webui-forge-classic\webui-user.bat", r"C:\AI\sd-webui-forge-classic\run.bat",
              r"C:\AI\stable-diffusion-webui-forge\webui-user.bat", r"C:\AI\webui_forge_cu121_torch231\run.bat"],
    "comfyui": [r"C:\AI\ComfyUI\ComfyUI_windows_portable\run_nvidia_gpu.bat", r"C:\AI\ComfyUI_windows_portable\run_nvidia_gpu.bat",
                r"C:\ComfyUI_windows_portable\run_nvidia_gpu.bat"],
}
TIMEOUT_S = 300  # first starts (Forge installing its venv) can take minutes


def roots():
    """Folders searched (two levels deep) when no known path exists."""
    home = os.path.expanduser("~")
    out = [home, os.path.join(home, "Desktop"), os.path.join(home, "Documents"), os.path.join(home, "Downloads")]
    if WINDOWS:
        for d in "CDE":
            out += [f"{d}:\\AI", f"{d}:\\", f"{d}:\\Stable Diffusion", f"{d}:\\SD", f"{d}:\\pinokio\\api"]
    return [r for r in out if os.path.isdir(r)]


def _looks_like(kind, folder):
    try:
        names = set(os.listdir(folder))
    except OSError:
        return False
    low = {n.lower() for n in names}
    if kind == "a1111":
        return ("webui.py" in low or "launch.py" in low or "webui" in low) and any(s in low for s in SCRIPTS["a1111"])
    return ("comfyui" in low or "main.py" in low) and any(s in low for s in SCRIPTS["comfyui"])


def script_in(kind, folder):
    """The launcher file in `folder` for `kind`, or ''."""
    for s in SCRIPTS[kind]:
        p = os.path.join(folder, s)
        if os.path.isfile(p):
            return p
    # Forge one-click packages keep webui-user.bat one level down (webui\) next to their own run.bat
    return ""


def search(kind, where=None, depth=2):
    """First launcher found under `where` (default roots()), at most `depth` folder levels down."""
    for root in (where if where is not None else roots()):
        level = [root]
        for _ in range(depth + 1):
            nxt = []
            for folder in level:
                if _looks_like(kind, folder):
                    hit = script_in(kind, folder)
                    if hit:
                        return hit
                try:
                    subs = [os.path.join(folder, n) for n in os.listdir(folder)]
                except OSError:
                    continue
                nxt += [d for d in subs if os.path.isdir(d) and not os.path.basename(d).startswith((".", "$"))
                        and os.path.basename(d).lower() not in ("windows", "program files", "program files (x86)",
                                                                  "programdata", "appdata", "node_modules", "venv", ".venv")]
            level = nxt[:400]
    return ""


def find(kind, saved="", known=None, where=None):
    """Launcher for `kind`: the saved path if it still exists, else a known location, else a search. '' = not installed."""
    if saved and os.path.isfile(saved):
        return saved
    for p in (KNOWN.get(kind, []) if known is None else known):
        if os.path.isfile(p):
            return p
    return search(kind, where)


def forge_has_api(path):
    """True / False whether webui-user's COMMANDLINE_ARGS include --api; None when that can't be read."""
    folder = os.path.dirname(path)
    for name in ("webui-user.bat", "webui-user.sh", os.path.join("webui", "webui-user.bat")):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    lines = [ln for ln in f if "COMMANDLINE_ARGS" in ln and not ln.strip().startswith(("::", "#", "rem ", "REM "))]
            except OSError:
                return None
            return any("--api" in ln.split("#")[0] for ln in lines)
    return None


def launch(path, popen=subprocess.Popen):
    """Start the launcher detached in its own console window, in its own folder. Returns the process."""
    if not path or not os.path.isfile(path):
        raise OSError(f"Launcher not found: {path}")
    folder = os.path.dirname(os.path.abspath(path))
    if WINDOWS:
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return popen(["cmd.exe", "/c", path], cwd=folder, creationflags=flags, close_fds=True)
    shell = ["bash", path] if path.endswith(".sh") else [path]
    return popen(shell, cwd=folder, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
