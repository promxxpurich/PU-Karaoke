#!/usr/bin/env python3
"""to_h264.py — แปลง video.mp4 ที่เป็น AV1 ให้เป็น H.264 (iPad/ทีวีส่วนใหญ่ถอด AV1 ไม่ได้ ขึ้น "เปิดไฟล์เพลงนี้ไม่ได้")

ภาพเข้ารหัสด้วยชิปของ Mac (h264_videotoolbox) เสียง copy ตามเดิม — เพลง 5 นาที ~30 วิ
เขียนลง video.mp4.h264.part ก่อนแล้วค่อยแทนที่ = หยุดกลางทางไฟล์เดิมไม่เสีย, รันซ้ำได้ (ข้ามที่เป็น H.264 แล้ว)

ใช้:  ./scripts/to_h264.py                ทุกเพลงในคลัง (ข้ามเพลงที่จอกำลังเล่นอยู่)
      ./scripts/to_h264.py <video.mp4>    ไฟล์เดียว (server.py เรียกแบบนี้ตอนเพลงเข้าคิว)
      ./scripts/to_h264.py --dry          แค่นับว่าเหลือ AV1 กี่เพลง
"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DL = Path(os.environ.get("KARA_SONGS_DIR") or BASE / "songs") / "yt"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
PORT = int(os.environ.get("KARA_PORT") or 8080)


def vcodec(f: Path) -> str:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()


def duration(f: Path) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True, timeout=30)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def convert(f: Path) -> str:
    """'ok' / 'skip' (ไม่ใช่ AV1) / 'fail: ...' — ไม่ทับไฟล์เดิมจนกว่าไฟล์ใหม่ผ่านการตรวจ"""
    if not f.is_file():
        return "fail: ไม่มีไฟล์"
    if vcodec(f) != "av1":
        return "skip"
    part = f.with_name(f.name + ".h264.part")
    mt = f.stat().st_mtime
    try:
        r = subprocess.run(["nice", "-n", "10", FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-threads", "2",
                            "-i", str(f), "-map", "0:v:0", "-map", "0:a?",
                            "-c:v", "h264_videotoolbox", "-b:v", "2500k", "-profile:v", "high",
                            "-pix_fmt", "yuv420p", "-tag:v", "avc1", "-c:a", "copy",
                            "-movflags", "+faststart", "-f", "mp4", str(part)],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            return "fail: " + (r.stderr or "").strip()[-300:]
        # ความยาวต้องเท่าเดิม + เป็น H.264 จริง ไม่งั้นไม่แทนที่
        if vcodec(part) != "h264" or abs(duration(part) - duration(f)) > 1.0:
            return "fail: ไฟล์ที่ได้ไม่ผ่านการตรวจ"
        if f.stat().st_mtime != mt:
            return "fail: ไฟล์เดิมถูกเปลี่ยนระหว่างแปลง"
        if f"[{playing_now()}]" in f.parent.name:
            return "fail: เพลงนี้เริ่มเล่นระหว่างแปลง ไว้รอบหน้า"
        part.replace(f)                  # atomic
        return "ok"
    except subprocess.TimeoutExpired:
        return "fail: หมดเวลา"
    finally:
        part.unlink(missing_ok=True)


def playing_now() -> str | None:
    """videoId ของเพลงที่จอกำลังเล่น — ห้ามแทนที่ไฟล์ระหว่างเล่น (จอโหลดเป็นช่วงๆ จะได้ไบต์ของไฟล์ใหม่ปนมา)"""
    try:
        import asyncio, websockets

        async def get():
            async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", ping_interval=None, open_timeout=3) as ws:
                st = json.loads(await asyncio.wait_for(ws.recv(), 3))
                return (st.get("current") or {}).get("videoId")
        return asyncio.run(get())
    except Exception:
        return None


def main() -> int:
    if not FFMPEG or not FFPROBE:
        print("ไม่พบ ffmpeg/ffprobe (brew install ffmpeg)")
        return 2
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        res = convert(Path(args[0]))
        print(res)
        return 0 if res in ("ok", "skip") else 1
    files = sorted(DL.glob("*/video.mp4"))
    todo = [f for f in files if vcodec(f) == "av1"]
    print(f"AV1 เหลือ {len(todo)} จาก {len(files)} เพลง")
    if "--dry" in sys.argv:
        return 0
    n_ok = n_fail = 0
    t0 = time.monotonic()
    for i, f in enumerate(todo, 1):
        if f"[{playing_now()}]" in f.parent.name:
            print(f"[{i}/{len(todo)}] ข้าม (กำลังเล่น) {f.parent.name}")
            continue
        t = time.monotonic()
        res = convert(f)
        n_ok += res == "ok"
        n_fail += res.startswith("fail")
        print(f"[{i}/{len(todo)}] {res} {time.monotonic() - t:.0f}s {f.parent.name}", flush=True)
    print(f"เสร็จ: แปลงได้ {n_ok} · พัง {n_fail} · {time.monotonic() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
