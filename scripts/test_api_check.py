#!/usr/bin/env python3
"""ทดสอบ scripts/api_check.py บนคลังปลอม (videoId ขึ้นต้น TEST) — ไม่ยิง API จริง (mock requests.post)

  .venv/bin/python scripts/test_api_check.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="kara-apicheck-"))
os.environ.update(KARA_YT_COOKIES="none", KARA_SONGS_DIR=str(TMP / "songs"), KARA_API_DIR=str(TMP / "api"),
                  KARA_STUDIO_FILE=str(TMP / "studio.json"), KARA_GEMINI_GAP="0", KARA_TYPHOON_GAP="0",
                  KARA_GEMINI_RPD="4")
os.environ.pop("KARA_GEMINI_KEY", None)
os.environ.pop("KARA_TYPHOON_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_check as A  # noqa: E402

LINES = [{"t": 5.0 + 4 * i, "d": 3.5, "x": x} for i, x in enumerate(
    ["ฉันยังรักเธอเหมือนเดิมทุกวัน", "ไม่ว่าจะนานเท่าไหร่ก็ตาม", "หัวใจดวงนี้ยังเป็นของเธอ",
     "ขอแค่เธอหันกลับมามองกัน", "คืนนี้ดาวเต็มฟ้าสวยงาม", "อยากให้เธออยู่ตรงนี้ด้วยกัน"])]


def make_song(vid: str, lines=LINES, lang="th") -> Path:
    d = TMP / "songs" / f"เพลงทดสอบ [{vid}]"
    d.mkdir(parents=True, exist_ok=True)
    (d / "lyrics.json").write_text(json.dumps({"src": "lrclib", "lines": lines, "duration": 30.0},
                                              ensure_ascii=False), "utf-8")
    (d / "lang.json").write_text(json.dumps({"lang": lang}), "utf-8")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:a", "aac", str(d / "vocals.m4a")], check=True)
    return d


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._b, str):
            raise ValueError("not json")
        return self._b


calls = []


def fake_post(responses):
    it = iter(responses)

    def post(url, **kw):
        calls.append((url, kw))
        return next(it)
    return post


def gem_ok(out):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(out, ensure_ascii=False)}]}}],
                      "modelVersion": "gemini-test"})


fails = 0


def ok(cond, name):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    fails += not cond


def main():
    vid = "TESTapi0001"
    make_song(vid)
    (TMP / "studio.json").write_text(json.dumps({"geminiKey": "k-test", "typhoonKey": "t-test"}), "utf-8")

    print("== ไม่มี key -> exit 2")
    env = {**os.environ, "KARA_STUDIO_FILE": str(TMP / "nokey.json")}
    p = subprocess.run([sys.executable, str(Path(A.__file__)), vid], env=env, capture_output=True, text=True)
    ok(p.returncode == A.RC_NOKEY and json.loads(p.stdout.strip().splitlines()[-1])["error"] == "nokey", "exit 2 + JSON")

    print("== dry-run ไม่ยิงเน็ต")
    r = A.check_song(vid, "gemini", dry=True)
    ok(r["verdict"] == "dry-run" and r["lines"] == 6 and r["audio"] == "vocals.m4a", "dry-run บอกสิ่งที่จะส่ง")

    print("== Gemini ตอบว่าเพลงถูก มีบรรทัดผิด 2")
    A.requests.post = fake_post([gem_ok({"same_song": True, "confidence": 0.9, "missing": [{"t": 40, "heard": "ลาลา"}],
                                         "bad_lines": [{"i": 2, "status": "wrong_text", "heard": "หัวใจดวงเก่า"},
                                                       {"i": 4, "status": "not_sung", "heard": ""},
                                                       {"i": 99, "status": "not_sung", "heard": ""}]})])
    r = A.check_song(vid, "gemini")
    ok(r["verdict"] == "some-wrong" and [b["i"] for b in r["bad"]] == [2, 4], "บรรทัดเกินช่วงถูกทิ้ง, ได้ some-wrong")
    ok(r["okPct"] == round(100 * 4 / 6, 1) and r["missing"][0]["t"] == 40.0, "okPct + missing")
    url, kw = calls[-1]
    ok(kw["headers"]["x-goog-api-key"] == "k-test" and "key=" not in url, "key อยู่ใน header ไม่อยู่ใน URL")
    parts = kw["json"]["contents"][0]["parts"]
    ok(parts[0]["inline_data"]["mime_type"] == "audio/mp4" and "isolated vocal" in parts[1]["text"]
       and "4 [00:21] คืนนี้ดาวเต็มฟ้าสวยงาม" in parts[1]["text"], "แนบเสียง + เนื้อมีเลข/เวลา")
    cache = json.loads((A.song_dir(vid) / A.CACHE_NAME).read_text("utf-8"))
    ok(cache["gemini"]["hash"] == A.lyr_hash(LINES), "แคชตาม hash เนื้อ")

    print("== เรียกซ้ำใช้แคช / --fresh ยิงใหม่")
    n0 = len(calls)
    r = A.check_song(vid, "gemini")
    ok(r.get("cached") and len(calls) == n0, "ไม่ยิงซ้ำ")

    print("== Gemini บอกผิดเพลง")
    A.requests.post = fake_post([gem_ok({"same_song": False, "confidence": 0.95, "bad_lines": [], "missing": []})])
    r = A.check_song(vid, "gemini", fresh=True)
    ok(r["verdict"] == "wrong-song", "wrong-song")

    print("== Gemini พัง / JSON เสีย -> error ไม่แคชทับ")
    A.requests.post = fake_post([Resp(500, {"error": {"message": "boom"}})])
    r = A.check_song(vid, "gemini", fresh=True)
    ok(r["verdict"] == "error" and "500" in r["note"], "error 500")
    A.requests.post = fake_post([Resp(200, {"candidates": [{"finishReason": "SAFETY"}]})])
    r = A.check_song(vid, "gemini", fresh=True)
    ok(r["verdict"] == "error" and "SAFETY" in r["note"], "บอกเหตุผลที่ไม่ตอบ")
    cache = json.loads((A.song_dir(vid) / A.CACHE_NAME).read_text("utf-8"))
    ok(cache["gemini"]["verdict"] == "wrong-song", "แคชเดิมไม่ถูกทับด้วย error")

    print("== โควตารายวัน (RPD=4) หมด -> QuotaOut, exit 5")
    try:
        A.check_song(vid, "gemini", fresh=True)
        ok(False, "ควร raise QuotaOut")
    except A.QuotaOut:
        ok(True, "QuotaOut เมื่อครบ 4 ครั้ง")
    env = {**os.environ}
    p = subprocess.run([sys.executable, str(Path(A.__file__)), vid, "--fresh"], env=env, capture_output=True, text=True)
    ok(p.returncode == A.RC_QUOTA, "CLI exit 5")

    print("== 429 รายวัน -> ปิดโควตาวันนี้")
    A.PROVIDERS["gemini"]["rpd"] = 100
    (TMP / "api" / "quota.json").unlink()
    A.requests.post = fake_post([Resp(429, {"error": {"message": "Quota exceeded for metric: "
                                                       "generate_requests_per_day_per_project_per_model-FreeTier"}})])
    try:
        A.check_song(vid, "gemini", fresh=True)
        ok(False, "ควร raise")
    except A.QuotaOut:
        ok(A.quota_left("gemini") == 0, "quota_left = 0 หลังโดน 429 รายวัน")
    (TMP / "api" / "quota.json").unlink()

    print("== Typhoon: เนื้อถูก vs เนื้อผิดเพลง")
    heard = "".join(l["x"] for l in LINES[:5]) + "ลาลาลา"
    A.requests.post = fake_post([Resp(200, {"text": heard})])
    r = A.check_song(vid, "typhoon")
    ok(r["verdict"] == "ok" and r["cover"] > 0.8 and [b["i"] for b in r["bad"]] == [5],
       f"เนื้อถูก cover={r.get('cover')} บรรทัดที่ไม่ได้ยิน = 5")
    _, kw = calls[-1]
    ok(kw["headers"]["Authorization"] == "Bearer t-test" and kw["files"]["file"][2] == "audio/wav", "ส่ง wav + Bearer")
    A.requests.post = fake_post([Resp(200, {"text": "เดินทางไกลแสนไกลไปหาดวงดาวบนฟากฟ้าที่แสนกว้างใหญ่ไม่มีวันสิ้นสุด"})])
    r = A.check_song(vid, "typhoon", fresh=True)
    ok(r["verdict"] == "wrong-song", f"เนื้อผิดเพลง cover={r.get('cover')}")

    print("== Typhoon ข้ามเพลงที่ไม่ใช่ภาษาไทย")
    make_song("TESTapi0002", [{"t": 1.0 + i, "d": 1, "x": "hello world line"} for i in range(6)], lang="en")
    n0 = len(calls)
    r = A.check_song("TESTapi0002", "typhoon")
    ok(r["verdict"] == "skip" and len(calls) == n0, "skip ไม่ยิง")

    print("== videoId ขึ้นต้น '-' ไม่ถูกตีเป็นธง")
    make_song("-TESTapi003")
    p = subprocess.run([sys.executable, str(Path(A.__file__)), "-TESTapi003", "--dry-run"], env=env,
                       capture_output=True, text=True)
    res = json.loads(p.stdout.strip().splitlines()[-1])["results"]
    ok(p.returncode == 0 and res and res[0]["vid"] == "-TESTapi003" and res[0]["verdict"] == "dry-run", "dry-run vid '-…'")

    print(f"\n{'ผ่านทุกข้อ' if not fails else f'ไม่ผ่าน {fails} ข้อ'}  ({TMP})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
