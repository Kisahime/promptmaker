"""Check GitHub releases for a newer PromptMaker version."""
import json
import re
import urllib.request

REPO = "Kisahime/promptmaker"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(v):
    nums = [int(x) for x in re.findall(r"\d+", str(v))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def check(current, timeout=6, url=API):
    """Return (latest_tag, html_url) if a newer release exists, else None. Raises on network errors."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "PromptMaker"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    if tag and is_newer(tag, current) and not data.get("draft") and not data.get("prerelease"):
        return tag, data.get("html_url", f"https://github.com/{REPO}/releases")
    return None
