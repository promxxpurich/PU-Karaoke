#!/usr/bin/env python3
"""fetch_subs.py — ดึง subtitle ของ YouTube มาเก็บไว้กับเพลง

  songs/yt/<เพลง>/sub.th.vtt   ซับไทยของจริง (คนพิมพ์) = แหล่งที่ดีที่สุด
  songs/yt/<เพลง>/sub.en.vtt   สำรอง
  songs/yt/<เพลง>/auto.th.vtt  auto-caption (ASR ของ YouTube) คนละชั้นคุณภาพ เก็บคนละไฟล์

เพลงที่โหลดใหม่ server.py ดึงให้เองตอนโหลด สคริปต์นี้ไว้เติมย้อนหลังให้เพลงเก่า
ใช้:  ./scripts/fetch_subs.py [vid ...]     ซับจริง (ไม่ใส่ vid = ทุกเพลงที่ยังไม่มี)
      ./scripts/fetch_subs.py --auto        auto-caption
      ./scripts/fetch_subs.py --force       ดึงใหม่ทับของเดิม
"""
import json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lyrics_sources as LS

BASE = Path(__file__).resolve().parent.parent
DL = BASE / "songs" / "yt"
RE_VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
LANGS = ("th", "en")


def vid_of(name: str) -> str:
    m = RE_VID.search(name)
    return m.group(1) if m else name


def langs_available(d: Path) -> list[str]:
    """ภาษาที่ YouTube มี sub จริง (info.json แยก subtitles ออกจาก automatic_captions ให้แล้ว)"""
    try:
        j = json.loads((d / "info.json").read_text("utf-8"))
    except Exception:
        return list(LANGS)                      # ไม่รู้ ก็ลองดึงดู
    have = j.get("subtitles") or {}
    return [l for l in LANGS if l in have]


def fetch(vid: str, d: Path, force: bool = False) -> str:
    want = langs_available(d)
    if not want:
        return "ไม่มีซับจริงบน YouTube"
    if not force and all((d / f"sub.{l}.vtt").is_file() for l in want):
        return "มีแล้ว"

    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "skip_download": True,
        "writesubtitles": True,                 # เฉพาะซับจริง
        "writeautomaticsub": False,             # auto-caption เชื่อไม่ได้ ไม่เอา
        "subtitleslangs": want,
        "subtitlesformat": "vtt",
        "outtmpl": str(d / "_sub"),
        "socket_timeout": 30, "retries": 3,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={vid}"])

    got = []
    for f in sorted(d.glob("_sub.*.vtt")):
        lang = f.name.split(".")[-2]
        f.replace(d / f"sub.{lang}.vtt")
        got.append(lang)
    for f in d.glob("_sub.*"):                  # เศษไฟล์ภาษาที่ไม่ได้ขอ
        f.unlink(missing_ok=True)
    return ("ได้ " + "+".join(got)) if got else "ดึงไม่ได้"


def fetch_auto(vid: str, d: Path, force: bool = False) -> str:
    """auto-caption ของ YouTube -> auto.th.vtt (ตรรกะเดียวกับ server._fetch_auto_caption)

    ห้ามเขียนลง sub.*.vtt — ซับจริงกับ auto-caption คนละชั้นคุณภาพ และ server จัดลำดับ
    แหล่งต่างกัน (auto-caption อยู่หลัง lrclib)"""
    out = d / "auto.th.vtt"
    if out.is_file() and not force:
        return "มีแล้ว"
    try:
        info = json.loads((d / "info.json").read_text("utf-8"))
    except Exception:
        return "อ่าน info.json ไม่ได้"
    key = LS.asr_caption_track(info)
    if not key:
        return "ไม่มี ASR ไทยต้นฉบับ"           # ไม่ยิงเน็ตเลย

    from yt_dlp import YoutubeDL
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "skip_download": True,
        "writesubtitles": False,                # ห้ามปนซับจริง
        "writeautomaticsub": True,
        "subtitleslangs": [key], "subtitlesformat": "vtt",
        "outtmpl": str(d / "_auto"),
        "socket_timeout": 30, "retries": 3,
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
        got = next(iter(sorted(d.glob("_auto.*.vtt"))), None)
        if got:
            got.replace(out)
    finally:
        for f in d.glob("_auto.*"):
            f.unlink(missing_ok=True)
    if not out.is_file():
        return "ดึงไม่ได้"
    return "ได้ " + ("ใช้ได้" if LS.words_from_auto_vtt(out) else "แต่ไฟล์ใช้ไม่ได้")


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    auto = "--auto" in args
    only = [a for a in args if a not in ("--force", "--auto")] or None   # vid ขึ้นต้นด้วย - ได้
    n_ok = 0
    for d in sorted(DL.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        vid = vid_of(d.name)
        if only and vid not in only:
            continue
        if not (d / "info.json").is_file():
            continue
        try:
            msg = fetch_auto(vid, d, force) if auto else fetch(vid, d, force)
        except Exception as exc:
            msg = f"ล้มเหลว: {type(exc).__name__}: {exc}"
        if (d / ("auto.th.vtt" if auto else "sub.th.vtt")).is_file():
            n_ok += 1
        print(f"  {vid}  {msg:26s} {d.name[:44]}", flush=True)
        if auto and msg.startswith("ได้"):
            time.sleep(0.5)                     # กัน rate-limit ตอนยิงติดกัน 41 ครั้ง
    print(f"\n{'มี auto-caption' if auto else 'มีซับไทย'}แล้ว {n_ok} เพลง")


if __name__ == "__main__":
    main()
