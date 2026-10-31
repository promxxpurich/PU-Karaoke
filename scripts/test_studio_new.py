#!/usr/bin/env python3
"""ทดสอบ Studio ใหม่ (/studio) บนคลังปลอมด้วย headless Chrome โดยไม่ต่อเน็ตและไม่ใช้ GPU
ใช้:  .venv/bin/python scripts/test_studio_new.py [โฟลเดอร์เก็บภาพ]"""
import asyncio, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="kara-studionew-"))
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else TMP / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
PORT, CDP_PORT = 8097, 9337
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off"})
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


@asynccontextmanager
async def _no_lifespan(app):
    yield
K.app.router.lifespan_context = _no_lifespan

VIDS = ["TESTstud001", "TESTstud002", "TESTstud003"]
CALLS = {"gather": 0}
FF = K.FFMPEG or "ffmpeg"
first = None
for n, vid in enumerate(VIDS):
    d = K.DL_DIR / f"TEST studio {n} [{vid}]"
    d.mkdir()
    (d / "info.json").write_text(json.dumps({"id": vid, "title": f"TEST studio {n}", "uploader": "ทดสอบ", "duration": 12}), "utf-8")
    if first is None:
        subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:r=10:d=12", "-f", "lavfi", "-i", "sine=f=440:d=12",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "video.mp4")], check=True)
        first = d / "video.mp4"
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(first), "-vn", "-c:a", "copy", str(d / "audio.m4a")], check=True)
    else:
        shutil.copy(first, d / "video.mp4")
        shutil.copy(first.with_name("audio.m4a"), d / "audio.m4a")
    (d / "lyrics.json").write_text(json.dumps({"v": 1, "src": "lrclib", "lines": [
        {"t": 0.5, "d": 3, "x": "เนื้อเดิมบรรทัดหนึ่ง"}, {"t": 4, "d": 3, "x": "เนื้อเดิมบรรทัดสอง"}]}), "utf-8")


def fake_sources(vid, track, artist, errs=None):
    CALLS["gather"] += 1
    return ([
        {"id": "a", "provider": "joox", "label": "JOOX", "synced": True, "match": 88, "cover": 90, "shift": 0.5,
         "lines": [{"t": 1, "d": 2, "x": "เนื้อจาก JOOX หนึ่ง"}, {"t": 5, "d": 2, "x": "เนื้อจาก JOOX สอง"}],
         "faLines": [{"t": 1.2, "d": 2, "x": "เนื้อจาก JOOX หนึ่ง"}, {"t": 5.2, "d": 2, "x": "เนื้อจาก JOOX สอง"}]},
        {"id": "b", "provider": "lrclib", "label": "LRCLIB", "synced": True, "match": 40, "cover": 50, "shift": 0,
         "lines": [{"t": 2, "d": 2, "x": "เนื้อจาก LRCLIB"}]},
        {"id": "c", "provider": "web/description", "label": "คำอธิบาย", "synced": False, "match": 30, "texts": ["เนื้อเปล่าบรรทัดเดียว"]},
    ], {"title": ["TEST"], "lyric": []})


K._gather_sources = fake_sources
K._ocr_ensure = lambda vid: None
K._score_whisper = lambda vid, cands: None
K._fa_ready = lambda: False
K.ONLINE_PROVIDERS = frozenset({"joox", "lrclib"})
K._best_decide = lambda cands, cur: {"action": "use", "cand": cands[0]}


async def _no_words(*a, **k):
    return False
K._enqueue_words = _no_words

fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ผ่าน' if ok else 'ไม่ผ่าน'}  {name} {extra}".rstrip())
    fails += 0 if ok else 1


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
                self.errors.append((d.get("exception") or {}).get("description") or d.get("text") or "?")

    async def call(self, method, **params):
        self.i += 1
        fut = asyncio.get_running_loop().create_future()
        self.pend[self.i] = fut
        await self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        r = await asyncio.wait_for(fut, 30)
        if "error" in r:
            raise RuntimeError(f"{method}: {r['error']}")
        return r["result"]

    async def ev(self, expr):
        r = await self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('text')} {r['exceptionDetails'].get('exception', {}).get('description', '')[:160]} :: {expr[:90]}")
        return r["result"].get("value")

    async def wait(self, expr, timeout=8):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if await self.ev(expr):
                return time.monotonic() - t0
            await asyncio.sleep(0.05)
        return None

    async def shot(self, name):
        import base64
        r = await self.call("Page.captureScreenshot", format="png")
        (SHOTS / f"{name}.png").write_bytes(base64.b64decode(r["data"]))


def lyr(vid):
    return json.loads(next(K.DL_DIR.glob(f"*{vid}*")).joinpath("lyrics.json").read_text("utf-8"))


async def main():
    import uvicorn
    import websockets
    srv = uvicorn.Server(uvicorn.Config(K.app, host="127.0.0.1", port=PORT, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.05)
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={TMP / 'chrome'}", "--no-first-run",
                               "--mute-audio", "--autoplay-policy=no-user-gesture-required", "--window-size=1280,860", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(100):
            try:
                tg = await asyncio.to_thread(lambda: json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json")))
                page = next(t for t in tg if t.get("type") == "page")
                break
            except Exception:
                await asyncio.sleep(0.1)
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            c = CDP(ws)
            asyncio.create_task(c.run())
            await c.call("Runtime.enable")
            await c.call("Page.enable")
            base = f"http://localhost:{PORT}"

            # คลังเกิน 200 เพลงต้องส่งครบ
            r = await asyncio.to_thread(lambda: json.load(urllib.request.urlopen(f"{base}/api/archive")))
            check("รีโมท: ไม่มีเพดานจำนวนเพลงเดิม", K.api_archive.__defaults__[1] == 0 and len(r["results"]) == r["total"] == 3)

            # เพลงแรกเล่นอยู่ อีกเพลงอยู่ในคิว
            async with K.room.lock:
                K.room.current = {"id": "c1", "source": "yt", "videoId": VIDS[0], "title": "TEST studio 0", "singer": "แขก"}
                K.room.queue = [{"id": "c2", "source": "yt", "videoId": VIDS[1], "title": "TEST studio 1", "singer": "แขก"}]
                K.room.playing = True
                K.room.pos, K.room.pos_at = 4.2, time.monotonic()
            # เตรียมล่วงหน้าเหมือน watchdog
            K._src_warm_tick()
            await K._src_warm_task
            K._src_warm_tick()
            await K._src_warm_task
            check("เตรียมล่วงหน้า: เพลงที่เล่นและเพลงถัดไป", CALLS["gather"] == 2 and all((v, "", "") in K._src_cache for v in VIDS[:2]), f"ค้น {CALLS['gather']} ครั้ง")
            K._src_warm_tick()
            check("เตรียมแล้วไม่ทำซ้ำ", K._src_warm_task.done() and CALLS["gather"] == 2)

            await c.call("Page.navigate", url=f"{base}/studio?view=now&theme=peach")
            shown = await c.wait("!!document.querySelector('#now .src [data-a=useSrc]')")
            check("กำลังเล่น: แหล่งเนื้อขึ้นโดยไม่ต้องค้นใหม่", shown is not None and CALLS["gather"] == 2, f"{shown and round(shown, 2)} วิ")
            check("กำลังเล่น: เห็นเนื้อเดิม", await c.ev("document.querySelector('#now .line input').value") == "เนื้อเดิมบรรทัดหนึ่ง")
            check("กำลังเล่น: เน้นบรรทัดตามเวลาเพลง", await c.wait("document.querySelector('#now .line.now')?.dataset.k === '1'", 3) is not None)
            check("ไม่มีเครื่องมือจับเวลาเดิม", await c.ev("!document.querySelector('canvas') && !document.body.innerText.includes('แตะ')"))
            await c.shot("01-now")

            # ใช้แหล่งเนื้อ
            await c.ev("document.querySelector('#now [data-a=useSrc][data-v=\"0\"]').click()")
            await c.wait("!document.querySelector('#now [data-a=undo]').disabled && document.querySelector('#now .line input').value.includes('JOOX')")
            j = lyr(VIDS[0])
            check("ใช้เลย: เนื้อเปลี่ยนและใช้เวลา FA", j["lines"][0]["x"] == "เนื้อจาก JOOX หนึ่ง" and j["lines"][0]["t"] == 1.2)
            check("ใช้เลย: บอกที่มา", "JOOX" in (j.get("picked") or ""))
            check("ใช้เลย: มีไฟล์สำรองเนื้อเดิม", any(next(K.DL_DIR.glob(f"*{VIDS[0]}*")).joinpath("lyrics.edits").glob("*.json")))
            check("ใช้เลย: ขึ้นว่าใช้อยู่", await c.wait("document.querySelector('#now .src.active')?.innerText.includes('JOOX')", 3) is not None)

            # ย้อนกลับ
            await c.ev("document.querySelector('#now [data-a=undo]').click()")
            await c.wait("document.querySelector('#now .line input').value === 'เนื้อเดิมบรรทัดหนึ่ง'")
            check("ย้อนฉบับก่อน: กลับเนื้อเดิม", lyr(VIDS[0])["lines"][0]["x"] == "เนื้อเดิมบรรทัดหนึ่ง")

            # แก้คำผิด: เวลาเดิมต้องอยู่
            await c.ev("(()=>{const i=document.querySelector('#now .line input');i.value='แก้คำผิดแล้ว';i.dispatchEvent(new Event('input',{bubbles:true}))})()")
            check("แก้ข้อความ: ปุ่มบันทึกกดได้", await c.ev("!document.querySelector('#now [data-a=save]').disabled"))

            # เพลงเปลี่ยนระหว่างแก้ค้าง
            async with K.room.lock:
                K.room.current = {"id": "c2", "source": "yt", "videoId": VIDS[1], "title": "TEST studio 1", "singer": "แขก"}
                K.room.queue = []
            await K.room.broadcast()
            got = await c.wait("document.querySelector('#now .notice')?.innerText.includes('เพลงเปลี่ยนแล้ว')", 4)
            check("เพลงเปลี่ยนระหว่างแก้: งานไม่หายและมีปุ่มไปเพลงใหม่", got is not None and await c.ev("document.querySelector('#now .line input').value") == "แก้คำผิดแล้ว")
            await c.shot("02-song-changed")
            await c.ev("document.querySelector('#now [data-a=save]').click()")
            for _ in range(80):
                if lyr(VIDS[0])["lines"][0]["x"] == "แก้คำผิดแล้ว":
                    break
                await asyncio.sleep(0.05)
            j = lyr(VIDS[0])
            check("แก้คำผิด: บันทึกแล้วเวลาเดิมอยู่", j["lines"][0]["x"] == "แก้คำผิดแล้ว" and j["lines"][0]["t"] == 0.5)

            # เนื้อเปล่าที่จับเวลาไม่ได้ต้องไม่ทับของเดิม
            before = lyr(VIDS[0])["lines"]
            await c.ev("fetch=(o=>(u,p)=>String(u).endsWith('/autotime')?Promise.resolve(new Response('{\"need\":\"asr\"}',{status:200})):o(u,p))(fetch);0")
            await c.ev("document.querySelector('#now [data-a=useSrc][data-v=\"2\"]').click()")
            await c.wait("document.querySelector('#toast').textContent.includes('จับเวลา')", 4)
            check("เนื้อเปล่าจับเวลาไม่ได้: ไม่ทับเนื้อเดิม", lyr(VIDS[0])["lines"] == before)

            # คลังเพลง
            await c.ev("document.querySelector('#tabs [data-v=lib]').click()")
            await c.wait("document.querySelectorAll('#songs .song').length > 0 || document.querySelector('#songs p')")
            await c.ev("document.querySelector('#filters [data-f=all]').click()")
            check("คลังเพลง: ตัวกรองทั้งหมดเห็นครบ", await c.wait("document.querySelectorAll('#songs .song').length === 3") is not None)
            await c.ev("document.querySelector('#q').value='studio 2';document.querySelector('#q').dispatchEvent(new Event('input',{bubbles:true}))")
            check("คลังเพลง: ค้นหาได้", await c.wait("document.querySelectorAll('#songs .song').length === 1") is not None)
            await c.ev("document.querySelector('#songs .song').click()")
            check("คลังเพลง: เปิดเพลงที่เลือกพร้อมวิดีโอ", await c.wait("!!document.querySelector('#libedit video') && !!document.querySelector('#libedit [data-a=tryOn]')", 6) is not None)
            await c.ev("document.querySelector('#libedit [data-a=tryOn]').click()")
            await c.wait("!!document.querySelector('#libedit .notice')", 3)
            await c.ev("(()=>{const v=document.querySelector('#libedit video');v.currentTime=1.5;v.pause()})()")
            check("ลองฟัง: ซับเปลี่ยนตามแหล่งที่ลอง โดยยังไม่บันทึก", await c.wait("document.querySelector('#libedit .sub').textContent.includes('JOOX')", 4) is not None and "JOOX" not in lyr(VIDS[2])["lines"][0]["x"])
            await c.shot("03-library")

            for tab, sel in (("cut", "#cut iframe"), ("screen", "#screen iframe")):
                await c.ev(f"document.querySelector('#tabs [data-v={tab}]').click()")
                check(f"แท็บ {tab} เปิดได้", await c.wait(f"!!document.querySelector('{sel}')", 3) is not None)
                await asyncio.sleep(1.2)
                await c.shot(f"04-{tab}")
            for path in ("/studio/old", "/tvset"):
                st = await asyncio.to_thread(lambda: urllib.request.urlopen(base + path).status)
                check(f"{path} ยังใช้ได้", st == 200)
            check("หน้าไม่มี error", not c.errors, " | ".join(c.errors)[:300])
    finally:
        chrome.terminate()
        srv.should_exit = True
        await task
    shutil.rmtree(TMP / "songs", ignore_errors=True)
    print(f"ภาพ: {SHOTS}\nสรุป: ไม่ผ่าน {fails}")
    return 1 if fails else 0


sys.exit(asyncio.run(main()))
