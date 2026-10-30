import json

from promptmaker import ckptmatch, sync, wildcards
from promptmaker.storage import Store
from test_v4 import win  # noqa: F401  (fixture)

NOVA = {"id": "civitai_1", "name": "Nova Cross AM v3.0 (Civitai)",
        "civitai": {"model_name": "Nova Cross AM", "version_name": "v3.0"}}
CKS = ["novaCrossAM_v30.safetensors [abc123ff]", "lustifySDXL_v7.safetensors", "anima-preview.safetensors"]


def test_match_positive():
    assert ckptmatch.match(NOVA, CKS) == CKS[0]
    p = dict(NOVA, civitai=dict(NOVA["civitai"], file_name="novaCrossAM_v30.safetensors"))
    assert ckptmatch.match(p, ["sub/novaCrossAM_v30.safetensors", "x.safetensors"]) == "sub/novaCrossAM_v30.safetensors"
    assert ckptmatch.match(NOVA, ["Nova-Cross-AM-v3.0.safetensors"]) == "Nova-Cross-AM-v3.0.safetensors"


def test_match_negative():
    assert ckptmatch.match(NOVA, ["novaCrossAM_v20.safetensors", "novaCrossAM_v10.safetensors"]) is None  # ambiguous
    assert ckptmatch.match(NOVA, ["lustifySDXL.safetensors"]) is None
    assert ckptmatch.match({"id": "illustrious", "name": "Illustrious XL"}, ["illustriousXL.safetensors"]) is None
    assert ckptmatch.match(NOVA, []) is None


def _profiles(win):
    ids = list(win.profiles)
    return ids[0], ids[1]


def _select(win, pid):
    win.profile_combo.setCurrentIndex(win.profile_combo.findData(pid))


def test_mapping_set_restore_and_clear(win):
    a, b = _profiles(win)
    _select(win, a)
    win.img_ckpt.setCurrentText("alpha.safetensors")  # user picks -> linked to a
    assert win.store.get("profile_checkpoints")[a] == "alpha.safetensors"
    assert "Linked to" in win.ckpt_link_lbl.text()
    _select(win, b)
    win.img_ckpt.setCurrentText("beta.safetensors")
    _select(win, a)
    assert win.store.get("img_checkpoint:a1111") == "alpha.safetensors" and win.img_ckpt.name() == "alpha.safetensors"
    assert all(c.name() == "alpha.safetensors" for c in win._ckpt_combos_list())
    _select(win, b)
    assert win.img_ckpt.name() == "beta.safetensors"
    win.img_ckpt.setCurrentText("")  # Backend default -> unlink
    assert b not in win.store.get("profile_checkpoints")
    _select(win, a); _select(win, b)
    assert win.img_ckpt.name() == "alpha.safetensors"  # no link: left unchanged


def test_auto_match_on_profile_change(win):
    win.profiles["civitai_1"] = dict(win.profiles[_profiles(win)[0]], **NOVA)
    win.profile_combo.addItem(NOVA["name"], "civitai_1")
    win._ckpt_names = list(CKS)
    win.set_checkpoint("lustifySDXL_v7.safetensors")
    _select(win, "civitai_1")
    assert win.store.get("img_checkpoint:a1111") == "novaCrossAM_v30.safetensors"
    assert "civitai_1" not in (win.store.get("profile_checkpoints") or {})  # auto-match isn't saved as a link
    win._ckpt_names = ["novaCrossAM_v20.safetensors", "novaCrossAM_v10.safetensors"]
    win.set_checkpoint("lustifySDXL_v7.safetensors")
    _select(win, _profiles(win)[0]); _select(win, "civitai_1")
    assert win.store.get("img_checkpoint:a1111") == "lustifySDXL_v7.safetensors"


def test_mapping_in_sync(tmp_path):
    st = Store(str(tmp_path / "a.db")); st.set("profile_checkpoints", {"civitai_1": "nova.safetensors"})
    lib = wildcards.WildcardLib(str(tmp_path / "wc"))
    b = json.loads(json.dumps(sync.build(st, lib)))
    assert b["settings"]["profile_checkpoints"] == {"civitai_1": "nova.safetensors"}
    dst = Store(str(tmp_path / "b.db"))
    sync.apply(dst, b, wildcard_lib=wildcards.WildcardLib(str(tmp_path / "wc2")))
    assert dst.get("profile_checkpoints") == {"civitai_1": "nova.safetensors"}
