import json, os, sys, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promptmaker import builder, profiles, scoring, ollama
from promptmaker.library import Library, PackError, validate_pack
from promptmaker.storage import Store

PROF = profiles.load()
LIB = Library(os.path.join(ROOT, "packs"))
ITEMS = LIB.all_items()
SEL = {"Subject": ["a red fox"], "Style": ["watercolor"], "Lighting": ["golden hour"], "Setting": ["in an enchanted forest"]}

def test_profiles_valid():
    assert len(PROF) >= 15
    for p in PROF.values():
        assert p["format"] in ("natural", "tags", "hybrid", "json")
        assert p["negative"] in ("supported", "optional", "limited", "unsupported", "param_no")
        assert p["weighting"] in ("parens", "mj", "none")
        assert p["id"] == "generic" or p["sources"], p["id"]
        for a in profiles.ASPECTS:
            assert a in p["resolutions"], (p["id"], a)

def test_library_big():
    assert LIB.count() > 700
    assert LIB.search("ghibli")

def test_natural_flux():
    r = builder.build(SEL, PROF["flux2"], negative="blurry")
    assert r["prompt"].startswith("A red fox in an enchanted forest.")
    assert r["negative"] == "" and r["notes"] and "1920x1088" not in r["settings"]
    assert "1024x1024" in r["settings"]

def test_tags_pony_weight():
    r = builder.build(SEL, PROF["pony"], negative="x", emphasis=True)
    assert r["prompt"].startswith("score_9, score_8_up, score_7_up, (red fox:1.2)")
    assert r["negative"] == "x"

def test_anima_hybrid_artist():
    s = dict(SEL, **{"Artist influence": ["inspired by Hayao Miyazaki"]})
    p = builder.build(s, PROF["anima"])["prompt"]
    assert p.startswith("masterpiece, best quality, score_7, safe") and "@hayao miyazaki" in p and "." in p

def test_mj():
    p = builder.build(SEL, PROF["mj7"], aspect="16:9", negative="text", mj={"exp": 10, "raw": True})["prompt"]
    assert p.endswith("--ar 16:9 --exp 10 --raw --no text --v 7")

def test_gpt_avoid_and_json():
    assert "Avoid: text." in builder.build(SEL, PROF["gpt_image"], negative="text")["prompt"]
    d = json.loads(builder.build(SEL, PROF["flux2_json"])["prompt"])
    assert d["subjects"][0]["description"] == "a red fox"

def test_legacy_selection():
    assert builder.norm_sel({"Action": "dancing", "Style": "(none)"}) == {"Action / pose": ["dancing"]}

def test_heuristic_scores():
    good = builder.build(dict(SEL, Camera=["low angle"], Mood=["serene"]), PROF["flux2"])["prompt"]
    bad = "nice cool thing, (fox:1.4), photorealistic, anime --ar 1:1"
    g = scoring.heuristic_score(good, PROF["flux2"], ITEMS); b = scoring.heuristic_score(bad, PROF["flux2"], ITEMS)
    assert g["total"] > b["total"] + 20 and b["fixes"]
    assert scoring.heuristic_score("a fox", PROF["pony"], ITEMS)["criteria"]["Model fit"][0] < 10

def test_packs_roundtrip():
    d = tempfile.mkdtemp(); shutil.copy(os.path.join(ROOT, "packs", "core.json"), d)
    lib = Library(d)
    src = os.path.join(d, "x.src"); json.dump({"name": "Test Pack", "categories": {"Style": ["zz style"]}}, open(src, "w"))
    pid = lib.import_pack(src); assert "zz style" in lib.items("Style")
    lib.set_enabled(pid, False); assert "zz style" not in lib.items("Style")
    lib.add_custom("Mood", "zz mood"); assert "zz mood" in Library(d).items("Mood")
    try:
        validate_pack({"x": 1}); assert False
    except PackError:
        pass
    lib.delete_pack(pid)

def test_parse_helpers():
    assert builder.extract_prompt("hi <prompt>new one</prompt>") == "new one"
    assert builder.parse_json_loose('ok {"a": 1}') == {"a": 1}
    s = builder.analysis_to_selection({"subject": ["cat"], "Lighting": "neon", "bogus": ["x"]}, list(ITEMS))
    assert s == {"Subject": ["cat"], "Lighting": ["neon"]}
    assert ollama.chat_messages([], "p", PROF["sdxl"])[0]["role"] == "system"

def test_template_and_batch():
    out = builder.fill_template("{subject} {time} {nope}", {"subject": "cat"}, ITEMS)
    assert out.startswith("cat ") and "{time}" not in out and "{nope}" in out
    v = builder.batch_variations(SEL, ["Style", "Mood"], 12, ITEMS, PROF["sdxl"], seed=3)
    assert len(set(v)) == 12

def test_store_migrates_v2():
    import sqlite3
    path = os.path.join(tempfile.mkdtemp(), "v2.db")
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE history(id INTEGER PRIMARY KEY, ts REAL, prompt TEXT, fmt TEXT, source TEXT);"
                     "CREATE TABLE templates(id INTEGER PRIMARY KEY, name TEXT UNIQUE, body TEXT);"
                     "CREATE TABLE favourites(id INTEGER PRIMARY KEY, ts REAL, name TEXT, prompt TEXT, state TEXT);"
                     "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);"
                     "INSERT INTO settings VALUES('seeded','true'); INSERT INTO history(ts,prompt) VALUES(1,'old');")
    db.commit(); db.close()
    s = Store(path)
    assert s.history()[0][2] == "old"
    s.add_version("v1"); s.add_version("v1"); assert len(s.versions()) == 1

def test_user_profiles_file():
    p = os.path.join(tempfile.mkdtemp(), "data", "profiles.json")
    profiles.ensure_user_file(p)
    prof = dict(PROF["sdxl"], id="mine", name="Mine"); profiles.save_profile(p, prof)
    assert "mine" in profiles.load(p)

def test_create_messages_and_parse():
    m = ollama.create_messages("anime girl in an outfit", PROF["anima"], 3, 80)
    assert "3 distinct" in m[0]["content"] and "<negative>" in m[0]["content"] and "invent" in m[0]["content"]
    assert "<negative>" not in ollama.create_messages("x", PROF["flux2"])[0]["content"].split("output exactly:")[1]
    o = ollama.parse_options("<prompt>a</prompt><negative>b</negative>\n<prompt>c</prompt>")
    assert o == [{"prompt": "a", "negative": "b"}, {"prompt": "c", "negative": ""}]
    assert ollama.parse_options("just text")[0]["prompt"] == "just text"
