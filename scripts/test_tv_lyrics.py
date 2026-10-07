#!/usr/bin/env python3
"""test_tv_lyrics.py — ทดสอบว่า "เนื้อที่หาเจอแล้ว ขึ้นบนจอทีวีจริง" ด้วย Chrome แบบไม่มีหน้าต่าง

ไม่แตะเซิร์ฟเวอร์จริง (8080) และคลังจริง: เปิด server.py ในโปรเซสนี้ที่พอร์ตทดสอบ ชี้คลัง/ไฟล์ตั้งค่าไปโฟลเดอร์ชั่วคราว
สร้างเพลงทดสอบ TESTtvlyr0x (วิดีโอดำเงียบ) แล้วเปิดหน้าจอทีวี (/ และ /tv/<รหัส>) คุมผ่าน CDP
ทุกข้อวัด "เขียนไฟล์เนื้อ + broadcast แบบที่งานเบื้องหลังทำ → เห็นเนื้อบนจอภายในกี่วิ" (ผ่าน = ไม่เกิน PASS_SEC)

ใช้:  .venv/bin/python scripts/test_tv_lyrics.py [--port 8099] [--cdp 9333] [--only S1,S6] [--keep]
ออก:  0 = ผ่านทุกข้อ · 1 = มีข้อไม่ผ่าน
"""
import asyncio
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
PASS_SEC = 2.0                    # เนื้อต้องขึ้นจอภายในเท่านี้หลัง broadcast
WAIT_SEC = 8.0                    # รอนานสุดก่อนตัดสินว่า "ไม่ขึ้นเลย"
VIDS = ("TESTtvlyr01", "TESTtvlyr02", "TESTtvlyr03")
DUR = 150.0


def arg(name: str, default=None):
    if name in sys.argv:
        k = sys.argv.index(name)
        return sys.argv[k + 1] if k + 1 < len(sys.argv) and not sys.argv[k + 1].startswith("--") else True
    return default


PORT = int(arg("--port", 8099))
CDP_PORT = int(arg("--cdp", 9333))
ONLY = {x.strip() for x in str(arg("--only", "")).split(",") if x.strip()}
TMP = Path(tempfile.mkdtemp(prefix="kara-tvtest-"))

# ---- ชี้ทุกอย่างไปโฟลเดอร์ชั่วคราว ก่อน import server ----------------------------
os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off",
                   "KARA_SONGS_DIR": str(TMP / "songs" / "yt"), "KARA_SEG_DIR": str(TMP / "seg"),
                   "KARA_LYRICS_IN": str(TMP / "lyrics-in"), "KARA_FA_CACHE": str(TMP / "fa")})
_made = [p for p in (ROOT / "songs", ROOT / "songs" / "yt", ROOT / "songs" / ".thumbs") if not p.exists()]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server as K  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

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


@asynccontextmanager
async def _no_lifespan(app):
    yield                          # ไม่เปิดงานเบื้องหลัง (โหลด/แยกเสียง/หาเนื้อ) — สถานการณ์คุมเองทั้งหมด
K.app.router.lifespan_context = _no_lifespan

# ทำให้ไฟล์เนื้อ "โหลดพัง" ตามสั่ง (S6) — ทดสอบว่าจอลองใหม่เอง
FAIL = {"n": 0, "kind": ""}


@K.app.middleware("http")
async def _failer(request, call_next):
    if FAIL["n"] > 0 and request.url.path.endswith("/lyrics.json"):
        FAIL["n"] -= 1
        if FAIL["kind"] == "500":
            return Response("boom", status_code=500)
        if FAIL["kind"] == "404":
            return JSONResponse({"error": "not found"}, status_code=404)
        if FAIL["kind"] == "nan":
            return Response('{"v": 1, "lines": [{"t": NaN, "d": 1, "x": "x"}]}', media_type="application/json")
    return await call_next(request)


# ---- เพลงทดสอบ ----------------------------------------------------------------
def song_dir(vid: str) -> Path:
    return K.DL_DIR / f"TEST tv lyrics {vid[-2:]} [{vid}]"


def make_songs() -> None:
    first = None
    for vid in VIDS:
        d = song_dir(vid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "info.json").write_text(json.dumps({"id": vid, "title": f"TEST tv lyrics {vid[-2:]}",
                                                 "uploader": "test", "duration": DUR}), "utf-8")
        if first is None:
            subprocess.run([K.FFMPEG or "ffmpeg", "-y", "-loglevel", "error",
                            "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=10:d={DUR}",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(DUR),
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", str(d / "video.mp4")], check=True)
            first = d / "video.mp4"
        else:
            shutil.copyfile(first, d / "video.mp4")
    K._dir_cache.clear()
    K._dir_scan_at = 0.0


def write_lyrics(vid: str, tag: str, n: int = 70) -> None:
    """เขียนแบบ atomic เหมือนงานจริง — ทุกบรรทัดยาว 1.8 วิ ห่าง 2 วิ เริ่ม 0.5 วิ"""
    lines = [{"t": round(0.5 + 2 * i, 2), "d": 1.8, "x": f"{tag} บรรทัด {i}"} for i in range(n)]
    d = song_dir(vid)
    tmp = d / "lyrics.json.tmp"
    tmp.write_text(json.dumps({"v": 1, "videoId": vid, "lang": "th", "engine": "test", "src": "lrclib",
                               "duration": DUR, "lines": lines}, ensure_ascii=False), "utf-8")
    os.replace(tmp, d / "lyrics.json")


def write_words(vid: str) -> None:
    j = json.loads((song_dir(vid) / "lyrics.json").read_text("utf-8"))
    texts = [l["x"] for l in j["lines"]]
    k = [[[0, l["t"]], [len(l["x"]) // 2, l["t"] + 0.8]] for l in j["lines"]]
    (song_dir(vid) / "lyrics.words.json").write_text(
        json.dumps({"v": K.WORDS_VERSION, "texts": texts, "k": k}, ensure_ascii=False), "utf-8")


def clear_lyrics(vid: str) -> None:
    for name in ("lyrics.json", "lyrics.words.json", "lyrics.offset.json"):
        (song_dir(vid) / name).unlink(missing_ok=True)


_n = 0


async def play(vid: str, mode: str = "karaoke") -> None:
    """ให้ห้องเล่นเพลงนี้จากต้นเพลง แล้ว broadcast (ใบคิวใหม่ทุกครั้ง เหมือนกดเล่นเพลงใหม่)"""
    global _n
    _n += 1
    K.room.current = {"id": f"t{_n}", "source": "yt", "videoId": vid, "title": f"TEST {vid}"}
    K.room.playing = True
    K.room.pos, K.room.pos_at = 0.0, time.monotonic()
    K.room.lyr_mode = mode
    await K.room.broadcast()


# ---- CDP ----------------------------------------------------------------------
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

    async def wait(self, expr: str, timeout: float = WAIT_SEC) -> float | None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if await self.ev(expr):
                return time.monotonic() - t0
            await asyncio.sleep(0.05)
        return None

    async def open(self, path: str) -> None:
        await self.call("Page.navigate", url=f"http://127.0.0.1:{PORT}{path}")
        if await self.wait("document.readyState === 'complete' && !!window._state", 15) is None:
            raise RuntimeError(f"เปิด {path} ไม่ขึ้น")


SHOWN = """(() => { const e = document.querySelector('#lyr');
  return !!e && !e.classList.contains('hide') && getComputedStyle(e).display !== 'none'
         && (e.innerText || '').trim().length > 0; })()"""
HIDDEN = "(() => { const e = document.querySelector('#lyr'); return !e || e.classList.contains('hide'); })()"


def has_text(s: str) -> str:
    return f"({SHOWN}) && document.querySelector('#lyr').innerText.includes({json.dumps(s)})"


# ---- สถานการณ์ -----------------------------------------------------------------
RESULTS: list[tuple[str, str, bool, str]] = []


def record(key: str, name: str, took: float | None, limit: float = PASS_SEC, note: str = "") -> None:
    ok = took is not None and took <= limit
    RESULTS.append((key, name, ok, (f"{took:.2f} วิ" if took is not None else f"ไม่ขึ้นใน {WAIT_SEC:.0f} วิ")
                    + (f" · {note}" if note else "")))
    print(f"  {'✓' if ok else '✗'} {key} {name}: {RESULTS[-1][3]}", flush=True)


async def fresh_no_lyrics(cdp: CDP, vid: str = VIDS[0], path: str = "/", mode: str = "karaoke") -> None:
    clear_lyrics(vid)
    await play(vid, mode)
    await cdp.open(path)
    await cdp.wait(f"window._state.current && window._state.current.videoId === '{vid}'", 5)
    await asyncio.sleep(0.5)


async def s1(cdp: CDP):
    """เนื้อมาระหว่างเพลงเล่นอยู่ (อาการหลักที่ผู้ใช้เจอ)"""
    await fresh_no_lyrics(cdp)
    hidden0 = await cdp.ev(HIDDEN)
    write_lyrics(VIDS[0], "แรก")
    await K.room.broadcast()
    record("S1", "เนื้อมาระหว่างเล่น → ขึ้นจอเอง", await cdp.wait(SHOWN), note="" if hidden0 else "ก่อนมีเนื้อจอไม่ได้ซ่อน?")


async def s2(cdp: CDP):
    """เนื้อถูกเปลี่ยนกลางเพลง (งานเลือกเนื้อ newtext / บันทึกจาก Studio)"""
    if not await cdp.ev(SHOWN):
        write_lyrics(VIDS[0], "แรก")
        await K.room.broadcast()
        await cdp.wait(SHOWN)
    write_lyrics(VIDS[0], "ใหม่")
    await K.room.broadcast()
    record("S2", "เนื้อเปลี่ยนกลางเพลง → ข้อความใหม่ขึ้น", await cdp.wait(has_text("ใหม่")))


async def s3(cdp: CDP):
    """ไฟล์ไล่สีคาราโอเกะ (words) มาทีหลัง — เนื้อต้องยังขึ้นและผูก k ได้"""
    write_words(VIDS[0])
    await K.room.broadcast()
    took = await cdp.wait(f"({SHOWN}) && !!LY && LY.lines.some(l => l.k)")
    record("S3", "ไฟล์ไล่สีมาทีหลัง → ยังขึ้น + ผูกเวลารายคำ", took)


async def s4(cdp: CDP):
    """ทุกโหมดเนื้อ + ปิด/เปิด"""
    for mode, want in (("off", False), ("scroll", True), ("dual", True), ("karaoke", True)):
        K.room.lyr_mode = mode
        await K.room.broadcast()
        took = await cdp.wait(SHOWN if want else HIDDEN)
        record("S4", f"โหมด {mode} → {'ขึ้น' if want else 'ซ่อน'}", took)


async def s5(cdp: CDP):
    """offset ประจำเพลง (ปรับจากรีโมท/Studio) ต้องถึงจอ"""
    (song_dir(VIDS[0]) / "lyrics.offset.json").write_text(json.dumps({"offset": 1.5}), "utf-8")
    await K.room.broadcast()
    record("S5", "offset ประจำเพลงถึงจอ", await cdp.wait(f"({SHOWN}) && songOff() === 1.5"))
    (song_dir(VIDS[0]) / "lyrics.offset.json").unlink(missing_ok=True)
    await K.room.broadcast()


async def s6(cdp: CDP):
    """โหลดไฟล์เนื้อพัง 1 ครั้ง (500 / 404 / JSON เสีย) — จอต้องลองใหม่เองจนขึ้น"""
    for kind in ("500", "404", "nan"):
        await fresh_no_lyrics(cdp)
        FAIL.update(n=1, kind=kind)
        write_lyrics(VIDS[0], f"พัง{kind}")
        await K.room.broadcast()
        took = await cdp.wait(has_text(f"พัง{kind}"))
        FAIL.update(n=0)
        record("S6", f"โหลดพัง ({kind}) ครั้งเดียว → ลองใหม่เองจนขึ้น", took, limit=6.0)


async def s7(cdp: CDP):
    """websocket หลุด ระหว่างนั้นเนื้อมา → ต่อใหม่แล้วต้องขึ้น"""
    await fresh_no_lyrics(cdp)
    for ws in list(K.room.clients):
        try:
            await ws.close()
        except Exception:
            pass
    await asyncio.sleep(0.2)
    write_lyrics(VIDS[0], "หลังต่อใหม่")
    await K.room.broadcast()
    record("S7", "ws หลุดแล้วต่อใหม่ → เนื้อที่มาระหว่างหลุดขึ้น", await cdp.wait(has_text("หลังต่อใหม่")), limit=4.0)


async def s8(cdp: CDP):
    """iPad: แผ่น "แตะเพื่อเปิดเสียง" ค้างหลังเปลี่ยนไปเพลงที่ไม่มีสเต็ม (บังเนื้อ แตะแล้วไม่หาย)"""
    stuck = await cdp.ev("needUnlock = true; showUnlock(); teardownStems(); onGesture();"
                         " !document.querySelector('#unlock').classList.contains('hide')")
    record("S8", "แผ่นปลดเสียงไม่ค้างหลัง teardownStems", 0.0 if not stuck else None,
           note="" if not stuck else "แผ่นยังค้างบังเนื้อ")
    await cdp.ev("hideUnlock(); true")


async def s9(cdp: CDP):
    """หน้า /tv/<รหัส> (ทีวี/iPad) — เนื้อมาระหว่างเล่น"""
    key = K._studio_cfg()["tv"]
    await fresh_no_lyrics(cdp, path=f"/tv/{key}")
    write_lyrics(VIDS[0], "ทีวี")
    await K.room.broadcast()
    record("S9", "/tv/<รหัส> เนื้อมาระหว่างเล่น → ขึ้นจอ", await cdp.wait(has_text("ทีวี")))


async def s10(cdp: CDP):
    """แก้ไฟล์เนื้อนอกงานเซิร์ฟเวอร์ (รันสคริปต์เอง/แก้มือ) — watchdog ต้องส่งให้จอ"""
    if not await cdp.ev(SHOWN):
        write_lyrics(VIDS[0], "แรก")
        await K.room.broadcast()
        await cdp.wait(SHOWN)
    write_lyrics(VIDS[0], "แก้มือ")                 # ไม่มี broadcast
    watch = getattr(K, "_lyr_watch", None)
    if watch is None:
        record("S10", "แก้ไฟล์ตรง ๆ → watchdog ส่งให้จอ", None, note="ไม่มี _lyr_watch ใน server.py")
        return
    await watch()
    record("S10", "แก้ไฟล์ตรง ๆ → watchdog ส่งให้จอ", await cdp.wait(has_text("แก้มือ")))


async def s11(cdp: CDP):
    """เปลี่ยนเพลง: มีเนื้อ → ไม่มีเนื้อ (ต้องไม่ค้างเนื้อเพลงก่อน) → มีเนื้อ"""
    write_lyrics(VIDS[0], "เพลงหนึ่ง")
    await play(VIDS[0])
    await cdp.wait(has_text("เพลงหนึ่ง"))
    clear_lyrics(VIDS[1])
    await play(VIDS[1])
    record("S11", "เปลี่ยนไปเพลงไม่มีเนื้อ → ไม่ค้างเนื้อเก่า", await cdp.wait(f"({HIDDEN}) && !LY"), limit=1.0)
    write_lyrics(VIDS[2], "เพลงสาม")
    await play(VIDS[2])
    record("S11", "เปลี่ยนไปเพลงที่มีเนื้อ → ขึ้นจอ", await cdp.wait(has_text("เพลงสาม")))


async def s12(cdp: CDP):
    """เพลงที่มีเนื้ออยู่แล้วเริ่มเล่น (ไม่มีสเต็ม ไม่มี broadcast อื่นตามมา)"""
    await fresh_no_lyrics(cdp, VIDS[1])
    write_lyrics(VIDS[2], "พร้อมก่อนเล่น")
    await play(VIDS[2])
    record("S12", "เพลงมีเนื้ออยู่แล้วเริ่มเล่น → ขึ้นจอ", await cdp.wait(has_text("พร้อมก่อนเล่น")))


SCENARIOS = [("S1", s1), ("S2", s2), ("S3", s3), ("S4", s4), ("S5", s5), ("S6", s6), ("S7", s7),
             ("S8", s8), ("S9", s9), ("S10", s10), ("S11", s11), ("S12", s12)]


# ---- main ---------------------------------------------------------------------
def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=2) as r:
        return json.loads(r.read())


async def main() -> int:
    import uvicorn
    import websockets
    make_songs()
    srv = uvicorn.Server(uvicorn.Config(K.app, host="127.0.0.1", port=PORT, log_level="warning"))
    srv_task = asyncio.create_task(srv.serve())
    while not srv.started:
        if srv_task.done():
            raise RuntimeError(f"เปิดเซิร์ฟเวอร์ทดสอบที่พอร์ต {PORT} ไม่ได้")
        await asyncio.sleep(0.05)
    hosts = ", ".join(f"MAP {h} 127.0.0.1" for h in ("www.youtube.com", "*.youtube.com", "*.ytimg.com",
                                                     "*.googlevideo.com", "fonts.googleapis.com", "fonts.gstatic.com"))
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
                               f"--user-data-dir={TMP / 'chrome'}", "--autoplay-policy=no-user-gesture-required",
                               "--no-first-run", "--no-default-browser-check", "--mute-audio",
                               f"--host-resolver-rules={hosts}", "--window-size=1280,720", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                pages = [t for t in await asyncio.to_thread(_get_json, f"http://127.0.0.1:{CDP_PORT}/json/list")
                         if t.get("type") == "page"]
                if pages:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("เปิด Chrome ไม่ขึ้น")
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], ping_interval=None, max_size=None) as ws:
            cdp = CDP(ws)
            reader = asyncio.create_task(cdp.run())
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            for key, fn in SCENARIOS:
                if ONLY and key not in ONLY:
                    continue
                print(f"[{key}] {fn.__doc__.strip().splitlines()[0]}", flush=True)
                try:
                    await fn(cdp)
                except Exception as exc:
                    RESULTS.append((key, "ล้มกลางทาง", False, f"{type(exc).__name__}: {exc}"))
                    print(f"  ✗ {key} ล้มกลางทาง: {type(exc).__name__}: {exc}", flush=True)
            reader.cancel()
            errs = sorted(set(cdp.errors))
    finally:
        chrome.terminate()
        try:
            chrome.wait(5)
        except Exception:
            chrome.kill()
        srv.should_exit = True
        await asyncio.wait_for(srv_task, 10)
    bad = [r for r in RESULTS if not r[2]]
    print(f"\nผล: ผ่าน {len(RESULTS) - len(bad)}/{len(RESULTS)} ข้อ" + (f" · JS error {len(errs)}" if errs else ""))
    for e in errs:
        print("  JS:", e)
    return 1 if bad or errs else 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        if not arg("--keep"):
            shutil.rmtree(TMP, ignore_errors=True)
        else:
            print("เก็บไฟล์ทดสอบไว้ที่", TMP)
        for p in reversed(_made):               # import server สร้างโฟลเดอร์ว่างใน repo — ลบคืนเฉพาะที่เราสร้าง
            try:
                p.rmdir()
            except OSError:
                pass
    sys.exit(rc)
