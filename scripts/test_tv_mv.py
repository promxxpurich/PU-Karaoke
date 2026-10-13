#!/usr/bin/env python3
"""test_tv_mv.py — ทดสอบ 🎬 MV จากเนื้อเพลงบนจอทีวีจริง (Chrome แบบไม่มีหน้าต่าง) โดยไม่แตะเซิร์ฟเวอร์/คลังจริง

เปิด server.py ในโปรเซสนี้ที่พอร์ตทดสอบ คลังชั่วคราว 2 เพลง:
  TESTmvwith1 = มีบท MV (คัดลอกเนื้อ/เวลา/ภาพนิ่ง/บทจากโฟลเดอร์ทดสอบที่ให้มา + วิดีโอดำเงียบ)
  TESTmvnone1 = ไม่มีบท (เนื้ออย่างเดียว)
ข้อทดสอบ: ปิดสวิตช์ = จอเดิม / เปิด = MV วาดจริง / กรอแล้วฉากตาม / เพลงไม่มีบท = จอเดิม / ปิดกลางเพลง = กลับเดิม
           / สวิตช์จาก Studio (POST /api/studio/tv) และรีโมท (action mv) / ไฟล์ /mv/ และ /song/<id>/frames/ เสิร์ฟได้ / ไม่มี error JS

ใช้:  .venv/bin/python scripts/test_tv_mv.py --src demos/mv/songs/z9 [--port 8098] [--cdp 9334] [--shots DIR]
ออก:  0 = ผ่านทุกข้อ · 1 = มีข้อไม่ผ่าน
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def arg(name: str, default=None):
    if name in sys.argv:
        k = sys.argv.index(name)
        return sys.argv[k + 1] if k + 1 < len(sys.argv) else True
    return default


PORT = int(arg("--port", 8098))
CDP_PORT = int(arg("--cdp", 9334))
SRC = (ROOT / arg("--src", "demos/mv/songs/z9")).resolve()
SHOTS = Path(arg("--shots")) if arg("--shots") else None
TMP = Path(tempfile.mkdtemp(prefix="kara-mvtest-"))
WITH, NONE = "TESTmvwith1", "TESTmvnone1"

os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off",
                   "KARA_SONGS_DIR": str(TMP / "songs" / "yt"), "KARA_SEG_DIR": str(TMP / "seg"),
                   "KARA_LYRICS_IN": str(TMP / "lyrics-in"), "KARA_FA_CACHE": str(TMP / "fa")})
_made = [p for p in (ROOT / "songs", ROOT / "songs" / "yt", ROOT / "songs" / ".thumbs") if not p.exists()]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server as K  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

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
K._dir_cache.clear()
K._dir_scan_at = 0.0
K.room.tv = K._clean_tv({})          # ค่าเริ่มต้น (mv ปิด) ไม่ใช่ tv.json ของเครื่อง


@asynccontextmanager
async def _no_lifespan(app):
    yield
K.app.router.lifespan_context = _no_lifespan


def song_dir(vid: str) -> Path:
    return K.DL_DIR / f"TEST mv {vid[-5:]} [{vid}]"


def make_songs() -> float:
    ly = json.loads((SRC / "lyrics.json").read_text("utf-8"))
    dur = float(ly.get("duration") or ly["lines"][-1]["t"] + 20)
    first = None
    for vid in (WITH, NONE):
        d = song_dir(vid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "info.json").write_text(json.dumps({"id": vid, "title": f"TEST mv {vid}", "uploader": "test", "duration": dur}), "utf-8")
        for n in ("lyrics.json", "lyrics.words.json"):
            shutil.copyfile(SRC / n, d / n)
        if first is None:
            subprocess.run([K.FFMPEG or "ffmpeg", "-y", "-loglevel", "error",
                            "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=10:d={dur}",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(dur),
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", str(d / "video.mp4")], check=True)
            first = d / "video.mp4"
        else:
            shutil.copyfile(first, d / "video.mp4")
    d = song_dir(WITH)
    shutil.copyfile(SRC / "mv.json", d / "mv.json")
    if (SRC / "mv_beats.json").is_file():
        shutil.copyfile(SRC / "mv_beats.json", d / "mv_beats.json")
    if (SRC / "frames").is_dir():
        shutil.copytree(SRC / "frames", d / "frames")
    K._dir_cache.clear()
    K._dir_scan_at = 0.0
    return dur


_n = 0


async def play(vid: str) -> None:
    global _n
    _n += 1
    K.room.current = {"id": f"m{_n}", "source": "yt", "videoId": vid, "title": f"TEST {vid}"}
    K.room.playing = True
    K.room.pos, K.room.pos_at = 0.0, time.monotonic()
    K.room.lyr_mode = "karaoke"
    await K.room.broadcast()


async def set_mv(on: bool) -> None:
    K.room.tv = K._clean_tv({"mv": on}, K.room.tv)
    await K.room.broadcast()


class CDP:
    def __init__(self, ws):
        self.ws, self.i, self.pend, self.errors = ws, 0, {}, []

    async def run(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if m.get("id") in self.pend:
                self.pend.pop(m["id"]).set_result(m)
            elif m.get("method") == "Runtime.exceptionThrown":
                d = m["params"]["exceptionDetails"]
                self.errors.append(((d.get("exception") or {}).get("description") or d.get("text") or "?")[:200])
            elif m.get("method") == "Runtime.consoleAPICalled" and m["params"].get("type") == "error":
                self.errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"]["args"])[:200])

    async def call(self, method: str, **params):
        self.i += 1
        fut = asyncio.get_running_loop().create_future()
        self.pend[self.i] = fut
        await self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        r = await asyncio.wait_for(fut, 30)
        if "error" in r:
            raise RuntimeError(f"{method}: {r['error']}")
        return r["result"]

    async def ev(self, expr: str):
        r = await self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('text')} :: {expr[:80]}")
        return r["result"].get("value")

    async def wait(self, expr: str, timeout: float = 10) -> float | None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                if await self.ev(expr):
                    return time.monotonic() - t0
            except RuntimeError:
                pass
            await asyncio.sleep(0.1)
        return None

    async def shot(self, name: str) -> None:
        if not SHOTS:
            return
        SHOTS.mkdir(parents=True, exist_ok=True)
        r = await self.call("Page.captureScreenshot", format="jpeg", quality=70)
        (SHOTS / f"{name}.jpg").write_bytes(base64.b64decode(r["data"]))


MV_ON = "document.body.classList.contains('mv-on') && getComputedStyle(document.querySelector('#mvc')).display !== 'none'"
MV_OFF = "!document.body.classList.contains('mv-on') && getComputedStyle(document.querySelector('#mvc')).display === 'none'"
# canvas มีภาพจริง (ไม่ใช่ดำล้วน) — สุ่มจุดหลายจุด
DRAWN = """(() => { const c = document.querySelector('#mvc'), g = c.getContext('2d'); let lit = 0;
  for(let k = 0; k < 40; k++){ const d = g.getImageData(48 * k % 1920, 27 * k % 1080 + 10, 1, 1).data; if(d[0] + d[1] + d[2] > 40) lit++; }
  return lit >= 4; })()"""
SIG = """(() => { const c = document.querySelector('#mvc'), g = c.getContext('2d'); let s = 0;
  for(let k = 0; k < 60; k++){ const d = g.getImageData(31 * k % 1920, 17 * k % 1080, 1, 1).data; s = (s * 31 + d[0] * 3 + d[1] * 5 + d[2]) % 1e9; }
  return s; })()"""

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((name, ok, note))
    print(f"  {'✓' if ok else '✗'} {name}{' · ' + note if note else ''}", flush=True)


def _http(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


async def http(*a, **kw) -> tuple[int, bytes]:
    return await asyncio.to_thread(_http, *a, **kw)   # เซิร์ฟเวอร์อยู่ใน event loop เดียวกัน ห้ามเรียกแบบบล็อก


async def scenarios(cdp: CDP) -> None:
    # ไฟล์ที่ MV ต้องใช้
    st, _ = await http("/mv/engine.js")
    st2, _ = await http(f"/song/{WITH}/mv.json")
    frames = sorted((song_dir(WITH) / "frames").glob("f*.jpg"))
    st3 = (await http(f"/song/{WITH}/frames/{frames[0].name}"))[0] if frames else 200
    st4, _ = await http("/mv/../server.py")
    record("เสิร์ฟ /mv/engine.js, mv.json, frames/ (และกันออกนอกโฟลเดอร์)", (st, st2, st3) == (200, 200, 200) and st4 == 404, f"{st} {st2} {st3} {st4}")

    await play(WITH)
    await cdp.call("Page.navigate", url=f"http://127.0.0.1:{PORT}/")
    await cdp.wait("document.readyState === 'complete' && !!window._state && !!window._state.current", 15)
    await cdp.wait("!!(window._state.current.mvUrl)", 5)
    has_url = await cdp.ev("!!window._state.current.mvUrl")
    record("เพลงที่มีบทได้ mvUrl ใน state", bool(has_url))

    await asyncio.sleep(1.5)
    off_ok = await cdp.ev(MV_OFF)
    record("สวิตช์ปิด (ค่าเริ่มต้น) → จอเดิม ไม่มี MV", bool(off_ok))
    await cdp.shot("1-off")

    await set_mv(True)
    t_on = await cdp.wait(MV_ON, 8)
    t_draw = await cdp.wait(DRAWN, 20)
    record("เปิดสวิตช์ → MV ขึ้นจอ + วาดภาพจริง", t_on is not None and t_draw is not None,
           f"ขึ้น {t_on and round(t_on, 2)} วิ · วาด {t_draw and round(t_draw, 2)} วิ")
    lyr_hidden = await cdp.ev("getComputedStyle(document.querySelector('#lyr')).display === 'none'")
    record("เปิด MV → ซ่อนเนื้อแบบเดิม (MV วาดเนื้อเอง)", bool(lyr_hidden))
    await asyncio.sleep(1)
    await cdp.shot("2-on-start")

    # กรอ: เวลาที่ MV ใช้ต้องตามวิดีโอ
    lines = json.loads((SRC / "lyrics.json").read_text("utf-8"))["lines"]
    tgt = round(lines[min(6, len(lines) - 1)]["t"] + 0.8, 2)
    sig0 = await cdp.ev(SIG)
    await cdp.ev(f"local.currentTime = {tgt}; true")
    await cdp.wait(f"Math.abs(lyrPos() - songOff() - {tgt}) < 1.5", 5)
    await asyncio.sleep(1.2)
    sig1 = await cdp.ev(SIG)
    clk = await cdp.ev("lyrPos() - songOff()")
    record("กรอวิดีโอ → ภาพ MV เปลี่ยนตาม", sig0 != sig1 and abs((clk or 0) - tgt) < 3, f"เวลา {clk and round(clk, 1)} (เป้า {tgt})")
    await cdp.shot("3-after-seek")

    # เพลงที่ไม่มีบท: สวิตช์เปิดอยู่ก็ต้องเป็นจอเดิม
    await play(NONE)
    await cdp.wait(f"window._state.current && window._state.current.videoId === '{NONE}'", 5)
    t_none = await cdp.wait(MV_OFF, 6)
    record("เพลงที่ไม่มีบท (สวิตช์เปิด) → จอเดิม", t_none is not None)

    # กลับมาเพลงที่มีบท แล้วปิดกลางเพลง
    await play(WITH)
    await cdp.wait(MV_ON, 8)
    await cdp.wait(DRAWN, 15)
    await set_mv(False)
    t_off = await cdp.wait(MV_OFF + " && getComputedStyle(document.querySelector('#lyr')).display !== 'none'", 6)
    record("ปิดสวิตช์กลางเพลง → กลับจอเดิม + เนื้อแบบเดิมกลับมา", t_off is not None)
    await cdp.shot("4-off-again")

    # สวิตช์จาก Studio (POST) — บันทึกลง tv.json และจอเปลี่ยนตาม
    st5, body = await http("/api/studio/tv", "POST", {"mv": True})
    saved = st5 == 200 and json.loads(body or b"{}").get("tv", {}).get("mv") is True
    t_st = await cdp.wait(MV_ON, 8)
    record("Studio 📺 เปิด mv → บันทึก + จอเปลี่ยน", saved and t_st is not None, f"HTTP {st5}")
    await http("/api/studio/tv", "POST", {"mv": False})
    await cdp.wait(MV_OFF, 6)

    # รีโมท ⚙️ (websocket action mv)
    import websockets
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", ping_interval=None, origin=f"http://127.0.0.1:{PORT}") as ws:
        await ws.send(json.dumps({"action": "mv", "on": True}))
        t_rm = await cdp.wait(MV_ON, 8)
        record("รีโมท ⚙️ เปิด mv → จอเปลี่ยน", t_rm is not None and K.room.tv.get("mv") is True)
        await ws.send(json.dumps({"action": "mv", "on": False}))
        await cdp.wait(MV_OFF, 6)

    errs = [e for e in cdp.errors if "mv_beats.json" not in e and "favicon" not in e and "Failed to load resource" not in e]
    record("ไม่มี error JS", not errs, "; ".join(errs[:3]))


async def main() -> int:
    import uvicorn
    import websockets
    make_songs()
    srv = uvicorn.Server(uvicorn.Config(K.app, host="127.0.0.1", port=PORT, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.05)
    prof = TMP / "chrome"
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={prof}",
                               "--autoplay-policy=no-user-gesture-required", "--window-size=1280,720", "--mute-audio", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1).read())
                page = next(t for t in tabs if t.get("type") == "page")
                break
            except Exception:
                await asyncio.sleep(0.1)
        async with websockets.connect(page["webSocketDebuggerUrl"], ping_interval=None, max_size=50_000_000) as ws:
            cdp = CDP(ws)
            reader = asyncio.create_task(cdp.run())
            await cdp.call("Runtime.enable")
            await cdp.call("Page.enable")
            await scenarios(cdp)
            reader.cancel()
    finally:
        chrome.terminate()
        srv.should_exit = True
        await task
        shutil.rmtree(TMP, ignore_errors=True)
        for p in reversed(_made):
            try:
                p.rmdir()
            except OSError:
                pass
    bad = [r for r in RESULTS if not r[1]]
    print(f"\nผ่าน {len(RESULTS) - len(bad)}/{len(RESULTS)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
