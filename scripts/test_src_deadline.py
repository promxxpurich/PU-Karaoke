#!/usr/bin/env python3
"""ทดสอบเส้นตายของการรวมแหล่งเนื้อ ด้วยแหล่งปลอมที่หน่วงเวลา ไม่ต่อเน็ต
ใช้:  .venv/bin/python scripts/test_src_deadline.py"""
import json, os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="kara-srcdl-"))
os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off"})
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server as K  # noqa: E402
import lyrics_more as M  # noqa: E402

K.SONGS = TMP / "songs"
K.DL_DIR = K.SONGS / "yt"
K.LYRICS_IN = TMP / "lyrics-in"
K.SEG_CACHE = TMP / "seg"
for p in (K.DL_DIR, K.LYRICS_IN, K.SEG_CACHE):
    p.mkdir(parents=True, exist_ok=True)
K._dir_cache.clear()
K._dir_scan_at = 0.0
VID = "TESTsrcdead"
d = K.DL_DIR / f"TEST [{VID}]"
d.mkdir()
(d / "info.json").write_text(json.dumps({"id": VID, "title": "TEST", "uploader": "t", "duration": 60}), "utf-8")
(d / "lyrics.json").write_text(json.dumps({"v": 1, "src": "lrclib", "lines": [{"t": 1, "d": 2, "x": "เนื้อเดิมทดสอบ"}]}), "utf-8")
SLOW = {"joox": 0.0}
DONE = []


def cand(name):
    return {"provider": name, "label": name, "lines": [{"t": 1, "d": 2, "x": f"เนื้อจาก {name} {i}"} for i in range(3)], "texts": None, "meta": {}}


def fake_joox(*a, **k):
    time.sleep(SLOW["joox"])
    DONE.append("joox")
    return [cand("joox")]


M.from_joox = fake_joox
M.from_syncedlyrics = lambda *a, **k: [cand("netease")]
M.from_ytmusic = lambda *a, **k: [cand("ytmusic")]
K.LS._lrclib_pool = lambda *a, **k: []
K._mxm_token = lambda: ""
K._ocr_cands = lambda vid, out, dur: []
fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ผ่าน' if ok else 'ไม่ผ่าน'}  {name} {extra}".rstrip())
    fails += 0 if ok else 1


K.SRC_ONLINE_DEADLINE = 1.0
SLOW["joox"] = 0.1
errs = []
c, _ = K._gather_sources(VID, "", "", errs)
provs = {x["provider"] for x in c}
check("ทุกแหล่งทันเวลา: ได้ครบ ไม่นับว่าไม่ครบ", {"joox", "netease", "ytmusic"} <= provs and not errs and VID not in K._src_late)

SLOW["joox"] = 2.5
DONE.clear()
errs = []
t0 = time.monotonic()
c, _ = K._gather_sources(VID, "", "", errs)
took = time.monotonic() - t0
provs = {x["provider"] for x in c}
check("แหล่งช้า: จบตามเส้นตาย", took < 1.4, f"{took:.2f} วิ")
check("แหล่งช้า: ได้ผลจากแหล่งที่ตอบแล้ว", {"netease", "ytmusic"} <= provs and "joox" not in provs)
check("แหล่งช้า: นับว่าผลไม่ครบ เพื่อให้ลองใหม่", errs == ["joox"] and VID in K._src_late)
time.sleep(1.8)
check("แหล่งช้า: ทำต่อเบื้องหลังจนจบ", DONE == ["joox"])

SLOW["joox"] = 0.0
c, _ = K._gather_sources(VID, "", "")
check("รอบถัดไป: ได้ครบและเลิกนับว่าไม่ครบ", "joox" in {x["provider"] for x in c} and VID not in K._src_late)
print(f"สรุป: ไม่ผ่าน {fails}")
sys.exit(1 if fails else 0)
