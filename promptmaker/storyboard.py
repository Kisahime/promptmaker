"""5.0 Storyboards & comics: an idea -> AI panel plan (shot, characters, action, dialogue) -> one image per panel ->
page layout (grid templates, speech bubbles, captions) -> PNG/PDF export, plus a .pmstory project file."""
import json
import os
import re
import time

VERSION = 1
SHOTS = ["wide shot", "medium shot", "close-up", "extreme close-up", "over-the-shoulder", "low angle", "high angle", "establishing shot"]

# Layout templates: name -> list of (x, y, w, h) fractions of the page's content area, in reading order.
LAYOUTS = {
    "1 panel": [(0, 0, 1, 1)],
    "2 stacked": [(0, 0, 1, .5), (0, .5, 1, .5)],
    "2 side by side": [(0, 0, .5, 1), (.5, 0, .5, 1)],
    "3 strip": [(0, 0, 1, 1 / 3), (0, 1 / 3, 1, 1 / 3), (0, 2 / 3, 1, 1 / 3)],
    "3 big top": [(0, 0, 1, .55), (0, .55, .5, .45), (.5, .55, .5, .45)],
    "4 grid": [(0, 0, .5, .5), (.5, 0, .5, .5), (0, .5, .5, .5), (.5, .5, .5, .5)],
    "5 manga": [(0, 0, .6, .34), (.6, 0, .4, .34), (0, .34, 1, .33), (0, .67, .4, .33), (.4, .67, .6, .33)],
    "6 grid": [(c * .5, r / 3, .5, 1 / 3) for r in range(3) for c in range(2)],
}
PAGE_SIZES = {"A4 portrait": (1240, 1754), "Square": (1600, 1600), "Webtoon strip": (800, 2400), "Landscape 16:9": (1920, 1080)}
FONTS = ["Comic Sans MS", "Nunito", "Arial", "Georgia", "Impact"]


def new_panel(i=0):
    return {"shot": "medium shot", "characters": [], "outfits": {}, "action": "", "setting": "", "dialogue": [],
            "caption": "", "prompt": "", "image": "", "seed": None, "bubbles": []}


def new_storyboard(title="Untitled story", story=""):
    return {"version": VERSION, "title": title, "story": story, "layout": "4 grid", "page_size": "A4 portrait",
            "font": "Comic Sans MS", "font_size": 26, "gutter": 18, "style": "", "panels": [], "created": time.time()}


def plan_messages(story, n, chars, profile=None, style=""):
    """Ask the AI for a JSON panel plan. Known characters are listed by name so it reuses them (consistency)."""
    cast = "\n".join(f"- {c['name']}: {c.get('appearance', '')}" for c in chars) or "(none – invent adults only)"
    return [{"role": "system", "content": (
        "You are a storyboard artist. Split the user's story into exactly {n} comic panels. Characters are adults. "
        "Keep it safe for work. Reply ONLY with JSON: {{\"title\": str, \"panels\": [{{\"shot\": one of {shots}, "
        "\"characters\": [names from the cast that appear], \"setting\": short place/time, \"action\": what happens, "
        "visual only, \"dialogue\": [{{\"speaker\": name, \"text\": short line}}], \"caption\": optional narration}}]}}. "
        "Use the cast names exactly; at most 2 characters per panel; dialogue lines under 15 words.").format(
            n=n, shots=json.dumps(SHOTS))},
        {"role": "user", "content": f"Cast:\n{cast}\n\nStyle: {style or 'any'}\n\nStory:\n{story}"}]


def parse_plan(text, n=None, chars=()):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    names = {c["name"].lower(): c["name"] for c in chars}
    panels = []
    for i, p in enumerate((d.get("panels") if isinstance(d, dict) else None) or []):
        if not isinstance(p, dict):
            continue
        q = new_panel(i)
        q["shot"] = str(p.get("shot") or q["shot"])
        q["setting"], q["action"], q["caption"] = (str(p.get(k) or "") for k in ("setting", "action", "caption"))
        q["characters"] = [names.get(str(c).lower(), str(c)) for c in (p.get("characters") or []) if str(c).strip()][:3]
        dl = p.get("dialogue") or []
        if isinstance(dl, str):
            dl = [{"speaker": "", "text": dl}]
        q["dialogue"] = [{"speaker": str(x.get("speaker", "")), "text": str(x.get("text", ""))}
                         for x in dl if isinstance(x, dict) and x.get("text")]
        panels.append(q)
    if n:
        panels = panels[:n]
    return (d.get("title") if isinstance(d, dict) else "") or "", panels


def panel_prompt(panel, chars_by_name, profile=None, style=""):
    """Prompt for one panel: characters (consistent text from their Character), shot, action, setting, style."""
    from . import characters as ch
    parts, los = [], []
    people = [chars_by_name[n] for n in panel.get("characters", []) if n in chars_by_name]
    if len(panel.get("characters", [])) > 1:
        parts.append(f"{len(panel['characters'])} people")
    for c in people:
        parts.append(ch.character_text(c, panel.get("outfits", {}).get(c["name"]), profile, with_lora=False))
        los += [f"<lora:{n}:{w:g}>" for n, w in ch.loras(c)]
    unknown = [n for n in panel.get("characters", []) if n not in chars_by_name]
    if unknown:
        parts.append(", ".join(f"adult {n}" for n in unknown))
    parts += [panel.get("action", ""), panel.get("setting", ""), panel.get("shot", ""), style]
    txt = ", ".join(p.strip() for p in parts if p and p.strip())
    return txt + ("" if not los else " " + " ".join(dict.fromkeys(los)))


def default_bubbles(panel):
    """Speech bubbles for a panel's dialogue, placed top-left to right; caption box at the bottom."""
    out = []
    for i, d in enumerate(panel.get("dialogue", [])[:3]):
        out.append({"kind": "speech", "text": d["text"], "speaker": d.get("speaker", ""),
                    "x": 0.04 + (i % 2) * 0.48, "y": 0.04 + (i // 2) * 0.22, "w": 0.46, "h": 0.18})
    if panel.get("caption"):
        out.append({"kind": "caption", "text": panel["caption"], "x": 0.03, "y": 0.84, "w": 0.94, "h": 0.13})
    return out


def layout_rects(layout, size, margin=40, gutter=18):
    """Pixel rects (x, y, w, h) for a layout on a page of `size`."""
    W, H = size
    cw, chh = W - 2 * margin, H - 2 * margin
    out = []
    for fx, fy, fw, fh in LAYOUTS.get(layout, LAYOUTS["4 grid"]):
        x, y = margin + fx * cw, margin + fy * chh
        w, h = fw * cw, fh * chh
        g = gutter / 2
        out.append((int(x + g), int(y + g), int(w - gutter), int(h - gutter)))
    return out


def pages(sb):
    """Split panels into pages of the layout's panel count."""
    n = len(LAYOUTS.get(sb.get("layout"), LAYOUTS["4 grid"]))
    ps = sb.get("panels", [])
    return [ps[i:i + n] for i in range(0, max(1, len(ps)), n)] or [[]]


def render_page(sb, page_index=0, scale=1.0):
    """QImage of one page: panel images (cropped to fill), borders, speech bubbles and captions."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
    W, H = PAGE_SIZES.get(sb.get("page_size"), PAGE_SIZES["A4 portrait"])
    W, H = int(W * scale), int(H * scale)
    img = QImage(W, H, QImage.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
    rects = layout_rects(sb.get("layout"), (W, H), int(40 * scale), int(sb.get("gutter", 18) * scale))
    pg = pages(sb)[page_index] if page_index < len(pages(sb)) else []
    font = QFont(sb.get("font") or "Comic Sans MS"); font.setPixelSize(max(8, int(sb.get("font_size", 26) * scale)))
    for (x, y, w, h), panel in zip(rects, pg + [None] * (len(rects) - len(pg))):
        r = QRectF(x, y, w, h)
        p.fillRect(r, QColor("#f2f2f2"))
        if panel and panel.get("image") and os.path.exists(panel["image"]):
            src = QImage(panel["image"])
            if not src.isNull():
                s = max(w / src.width(), h / src.height())
                sw, sh = w / s, h / s
                p.drawImage(r, src, QRectF((src.width() - sw) / 2, (src.height() - sh) / 2, sw, sh))
        elif panel:
            p.setPen(QColor("#999")); p.setFont(font)
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, panel.get("action") or "")
        p.setPen(QPen(QColor("black"), max(2, 4 * scale))); p.setBrush(Qt.NoBrush); p.drawRect(r)
        for b in (panel or {}).get("bubbles", []):
            br = QRectF(x + b["x"] * w, y + b["y"] * h, b["w"] * w, b["h"] * h)
            p.setFont(font)
            fm_rect = p.boundingRect(br.adjusted(10, 6, -10, -6), Qt.AlignCenter | Qt.TextWordWrap, b.get("text", ""))
            if fm_rect.height() > br.height() - 12:  # grow the bubble to fit the text
                br.setHeight(fm_rect.height() + 18)
            p.setPen(QPen(QColor("black"), max(1.5, 2.5 * scale)))
            if b.get("kind") == "caption":
                p.setBrush(QColor("#fff7d6")); p.drawRect(br)
            else:
                path = QPainterPath(); path.addRoundedRect(br, br.height() / 2.2, br.height() / 2.2)
                tail = QPainterPath(); cx = br.center().x()
                tail.moveTo(cx - br.width() * .08, br.bottom() - 2); tail.lineTo(cx - br.width() * .02, br.bottom() + br.height() * .35)
                tail.lineTo(cx + br.width() * .06, br.bottom() - 2); tail.closeSubpath()
                p.setBrush(QColor("white")); p.drawPath(path.united(tail))
            p.setPen(QColor("black"))
            p.drawText(br.adjusted(10, 6, -10, -6), Qt.AlignCenter | Qt.TextWordWrap, b.get("text", ""))
    p.end()
    return img


def export_png(sb, path_base):
    """One PNG per page: <base>_p1.png ... Returns the paths."""
    out = []
    for i in range(len(pages(sb))):
        path = f"{path_base}_p{i + 1}.png" if len(pages(sb)) > 1 else f"{path_base}.png"
        render_page(sb, i).save(path); out.append(path)
    return out


def export_pdf(sb, path):
    from PySide6.QtCore import QMarginsF, QRectF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    W, H = PAGE_SIZES.get(sb.get("page_size"), PAGE_SIZES["A4 portrait"])
    pdf = QPdfWriter(path); pdf.setResolution(150)
    pdf.setPageLayout(QPageLayout(QPageSize(QSizeF(W / 150 * 25.4, H / 150 * 25.4), QPageSize.Millimeter),
                                  QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    pdf.setTitle(sb.get("title", "Storyboard"))
    p = QPainter(pdf)
    for i in range(len(pages(sb))):
        if i:
            pdf.newPage()
        img = render_page(sb, i)
        p.drawImage(QRectF(0, 0, pdf.width(), pdf.height()), img)
    p.end()
    return path


def save_project(sb, path):
    d = dict(sb, version=VERSION, saved=time.time())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    return path


def load_project(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict) or "panels" not in d:
        raise ValueError("Not a PromptMaker storyboard file")
    base = new_storyboard()
    base.update(d)
    base["panels"] = [dict(new_panel(), **p) for p in d.get("panels", []) if isinstance(p, dict)]
    return base
