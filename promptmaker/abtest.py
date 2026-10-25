"""Helpers for prompt A/B comparison."""
import difflib
import html
import re


def _tokens(text):
    return re.findall(r"\s+|[^\s,.;]+|[,.;]", text)


def diff_html(a, b, add_color="#35d39a", del_color="#ff6b81"):
    """Return (html_a, html_b) with removed words highlighted in A and added words in B."""
    ta, tb = _tokens(a), _tokens(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    out_a, out_b = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        sa, sb = html.escape("".join(ta[i1:i2])), html.escape("".join(tb[j1:j2]))
        if op == "equal":
            out_a.append(sa); out_b.append(sb)
        else:
            if sa:
                out_a.append(f"<span style='background:{del_color}55;border-radius:3px'>{sa}</span>")
            if sb:
                out_b.append(f"<span style='background:{add_color}55;border-radius:3px'>{sb}</span>")
    return "".join(out_a).replace("\n", "<br>"), "".join(out_b).replace("\n", "<br>")


def similarity(a, b):
    return round(difflib.SequenceMatcher(None, _tokens(a), _tokens(b)).ratio() * 100)


def verdict(score_a, score_b, margin=3):
    if abs(score_a - score_b) < margin:
        return "tie"
    return "A" if score_a > score_b else "B"
