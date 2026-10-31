#!/usr/bin/env python3
"""ทดสอบปุ่ม 🎞 โหลดคลิปใหม่บนคลังปลอม โดยไม่ต่อ YouTube (แทน YoutubeDL ด้วยตัวปลอมที่สร้างไฟล์ด้วย ffmpeg)
ใช้:  .venv/bin/python scripts/test_revideo.py"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="kara-revideo-"))
os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off",
                   "KARA_SONGS_DIR": str(TMP / "songs" / "yt"), "KARA_SEG_DIR": str(TMP / "seg"),
                   "KARA_LYRICS_IN": str(TMP / "lyrics-in"), "KARA_FA_CACHE": str(TMP / "fa")})
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server as K  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

K.SONGS = TMP / "songs"
K.DL_DIR = K.SONGS / "yt"
K.THUMB_CACHE = K.SONGS / ".thumbs"
K.LYRICS_IN = TMP / "lyrics-in"
K.SEG_CACHE = TMP / "seg"
K.STUDIO_FILE = TMP / "studio.json"
K.HISTORY_FILE = TMP / "history.json"
K.TV_FILE = TMP / "tv.json"
K.TV_DIR = TMP / "tvdir"
K.COMBOS_FILE = TMP / "combos.json"
for p in (K.DL_DIR, K.THUMB_CACHE, K.LYRICS_IN, K.SEG_CACHE):
    p.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _no_lifespan(app):
    yield
K.app.router.lifespan_context = _no_lifespan

VID = "TESTrevideo"
D = K.DL_DIR / f"TEST revideo [{VID}]"
D.mkdir()
FF = K.FFMPEG or "ffmpeg"


def clip(path, h, dur=6, audio=True, br="600k"):
    args = [FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=s={h * 16 // 9 // 2 * 2}x{h}:r=10:d={dur}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=440:d={dur}", "-c:a", "aac"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-b:v", br, "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True)


(D / "info.json").write_text(json.dumps({"id": VID, "title": "TEST revideo", "uploader": "t", "duration": 6}), "utf-8")
ORIG = TMP / "orig.mp4"
clip(ORIG, 180, br="60k")
PROTECTED = {"audio.m4a": b"AUDIO", "vocals.m4a": b"V", "no_vocals.m4a": b"N", "lyrics.json": b'{"v":1,"lines":[]}'}
for n, b in PROTECTED.items():
    (D / n).write_bytes(b)
PLAN = {}


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        assert "vcodec^=avc1" in self.opts["format"] and "height<=1080" in self.opts["format"], self.opts["format"]
        if PLAN.get("error"):
            raise RuntimeError(PLAN["error"])
        out = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        clip(out, PLAN["h"], dur=PLAN.get("dur", 6), audio=False, br=PLAN.get("br", "2000k"))


K.YoutubeDL = FakeYDL
sha = lambda f: hashlib.sha256(Path(f).read_bytes()).hexdigest()
client = TestClient(K.app, base_url="http://localhost")
client.cookies.set("studio", K._studio_token())
fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ผ่าน' if ok else 'ไม่ผ่าน'}  {name} {extra}")
    fails += 0 if ok else 1


def press(**plan):
    PLAN.clear()
    PLAN.update(plan)
    r = client.post(f"/api/studio/song/{VID}/action", json={"do": "revideo"})
    assert r.status_code == 200, r.text
    return r.json()["msg"]


def reset():
    shutil.copy(ORIG, D / "video.mp4")


def untouched():
    return all((D / n).read_bytes() == b for n, b in PROTECTED.items()) and not (D / "_revideo").exists()


reset(); before = sha(D / "video.mp4")
msg = press(error="ERROR: Unable to download")
check("โหลดพลาด: ไฟล์เดิมอยู่ครบ", sha(D / "video.mp4") == before and untouched(), msg)
msg = press(error="Sign in to confirm you're not a bot")
check("โดนบล็อก: บอกชัดและไฟล์เดิมอยู่", "บล็อก" in msg and sha(D / "video.mp4") == before, msg)
msg = press(error="Requested format is not available")
check("ไม่มี H.264: ไฟล์เดิมอยู่", "H.264" in msg and sha(D / "video.mp4") == before, msg)
msg = press(h=120, br="30k")
check("ชัดน้อยกว่า: ไม่เปลี่ยน", "ไม่เปลี่ยน" in msg and sha(D / "video.mp4") == before, msg)
msg = press(h=720, dur=9)
check("ความยาวต่าง: ไม่เปลี่ยน", "ยาวไม่เท่า" in msg and sha(D / "video.mp4") == before, msg)
K.room.current = {"videoId": VID}
msg = press(h=720)
check("เพลงกำลังเล่น: โหลดเก็บไว้ ยังไม่เปลี่ยนไฟล์", "ตอนเพลงนี้จบ" in msg and sha(D / "video.mp4") == before, msg)
K._revideo_apply()
check("เพลงยังเล่นอยู่: ยังไม่เปลี่ยน", sha(D / "video.mp4") == before)
K.room.current = None
K._revideo_apply()
check("เพลงจบแล้ว: เปลี่ยนเป็นคลิปใหม่", K._probe_video(D / "video.mp4")["height"] == 720 and not (D / K.REVIDEO_READY).exists())
reset(); before = sha(D / "video.mp4")

audio_before = subprocess.run([FF, "-v", "error", "-i", str(D / "video.mp4"), "-map", "0:a:0", "-f", "md5", "-"], capture_output=True, text=True).stdout
msg = press(h=720)
new = K._probe_video(D / "video.mp4")
check("ชัดกว่า: เปลี่ยนเป็น 720p", "เปลี่ยนคลิปแล้ว" in msg and new["height"] == 720, msg)
audio_after = subprocess.run([FF, "-v", "error", "-i", str(D / "video.mp4"), "-map", "0:a:0", "-f", "md5", "-"], capture_output=True, text=True).stdout
check("เสียงในคลิปเหมือนเดิม", audio_before == audio_after and audio_before != "")
check("เสียงแยก เนื้อ ไม่ถูกแตะ และไม่เหลือไฟล์พัก", untouched())
reset()
msg = press(h=180, br="2000k")
check("ความละเอียดเท่าเดิม บิตเรตสูงกว่า: เปลี่ยน", "เปลี่ยนคลิปแล้ว" in msg, msg)
shutil.rmtree(TMP, ignore_errors=True)
print(f"สรุป: ไม่ผ่าน {fails}")
sys.exit(1 if fails else 0)
