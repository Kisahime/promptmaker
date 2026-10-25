"""API key storage: OS keyring when available, otherwise a clearly-labelled local JSON file."""
import json
import os

SERVICE = "PromptMaker"

try:  # optional dependency
    import keyring  # type: ignore
    from keyring.errors import KeyringError  # type: ignore
except Exception:  # noqa: BLE001
    keyring = None
    KeyringError = Exception


def _usable():
    """False when keyring is installed but has no real backend (e.g. headless Linux)."""
    try:
        kr = keyring.get_keyring()
        prio = getattr(kr, "priority", 1)
        return prio > 0 and "fail" not in type(kr).__module__.lower()
    except Exception:  # noqa: BLE001
        return False


class KeyStore:
    def __init__(self, data_dir, use_keyring=True):
        self.path = os.path.join(data_dir, "secrets.json")
        self.use_keyring = bool(keyring) and use_keyring and _usable()

    @property
    def backend(self):
        return "OS keyring (Windows Credential Manager / Keychain / Secret Service)" if self.use_keyring else f"plain-text file ({self.path})"

    def _file(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def get(self, name):
        if self.use_keyring:
            try:
                v = keyring.get_password(SERVICE, name)
                if v:
                    return v
            except KeyringError:
                pass
        return self._file().get(name, "")

    def set(self, name, value):
        if self.use_keyring:
            try:
                keyring.set_password(SERVICE, name, value)
                return "keyring"
            except KeyringError:
                pass
        d = self._file()
        d[name] = value
        d["_warning"] = "API keys stored in plain text. Do not share this file. Install 'keyring' for secure storage."
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        return "file"

    def delete(self, name):
        if self.use_keyring:
            try:
                keyring.delete_password(SERVICE, name)
            except Exception:  # noqa: BLE001
                pass
        d = self._file()
        if name in d:
            d.pop(name)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1)
