"""Where user data lives: next to the app (portable, default) or in the user's AppData folder."""
import os
import shutil
import sys

FLAG = "use_appdata.flag"


def user_data_root():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PromptMaker")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/PromptMaker")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "PromptMaker")


def is_portable(app_dir):
    return not os.path.exists(os.path.join(app_dir, FLAG))


def data_dir(app_dir):
    d = os.path.join(app_dir, "data") if is_portable(app_dir) else user_data_root()
    os.makedirs(d, exist_ok=True)
    return d


def set_portable(app_dir, portable, copy_data=True):
    """Switch mode; copies existing data to the new location if it is empty. Returns new data dir."""
    old = data_dir(app_dir)
    flag = os.path.join(app_dir, FLAG)
    if portable and os.path.exists(flag):
        os.remove(flag)
    elif not portable:
        with open(flag, "w") as f:
            f.write("PromptMaker stores its data in the user's AppData folder while this file exists.\n")
    new = data_dir(app_dir)
    if copy_data and os.path.abspath(old) != os.path.abspath(new) and not os.listdir(new):
        for name in os.listdir(old):
            src = os.path.join(old, name)
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, os.path.join(new, name))
    return new
