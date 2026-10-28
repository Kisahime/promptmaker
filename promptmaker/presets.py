"""Character and style presets: turn saved characters/styles into prompt text and keep them fixed across batches."""
import re


def _parts(text):
    return [p.strip() for p in re.split(r"[,\n]", text or "") if p.strip()]


def character_text(char, profile=None, with_lora=True):
    parts = _parts(char.get("appearance")) + _parts(char.get("outfit"))
    natural = (profile or {}).get("format") == "natural"
    if natural and parts:
        body = f"{char['name']}, " + ", ".join(parts)
    else:
        body = ", ".join(parts) or char.get("name", "")
    if with_lora and char.get("lora"):
        body += ", " + f"<lora:{char['lora']}:{float(char.get('lora_weight') or 0.8):g}>"
    return body


def style_text(style):
    return ", ".join(_parts(style.get("tags")))


def dedupe(parts):
    seen, out = set(), []
    for p in parts:
        k = p.strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(p.strip())
    return out


def compose(prompt, characters=(), styles=(), profile=None):
    """Prepend characters (in order), append styles; drop duplicate tags so combining presets stays clean."""
    chars = [character_text(c, profile) for c in characters]
    if len(chars) > 1 and (profile or {}).get("format") != "natural":
        chars = [f"{len(chars)} characters"] + chars
    sty = [style_text(s) for s in styles]
    body = _parts(prompt)
    pieces = []
    for block in chars + [", ".join(body)] + sty:
        pieces.extend(_parts(block))
    return ", ".join(dedupe(pieces))


def negative(styles, base=""):
    return ", ".join(dedupe(_parts(base) + [p for s in styles for p in _parts(s.get("negative"))]))


def apply_to_batch(variations, characters=(), styles=(), profile=None):
    """Same characters/styles on every variation, so the character stays consistent image to image."""
    return [compose(v, characters, styles, profile) for v in variations]
