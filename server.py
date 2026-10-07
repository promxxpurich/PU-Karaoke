"""Karaoke MVP - Mode A (YouTube IFrame player).
Player:  http://<host>:8080/
Remote:  http://<host>:8080/r   (scan QR on the player screen)
"""
from contextlib import asynccontextmanager
import asyncio, json, math, random, re, socket, sys, unicodedata, uuid, io, os, time, shutil, subprocess
import hashlib, hmac, secrets, threading, queue
from pathlib import Path
from typing import Any

# --- macOS: Python มักไม่มี root certificate ทำให้ SSL ล้มเหลว -------
# ชี้ไปที่ CA bundle ของ certifi ก่อน import อย่างอื่นที่ใช้ network
try:
    import certifi
    _CA = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", _CA)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _CA)
    import ssl
    ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=_CA)
except Exception as _e:  # pragma: no cover
    _CA = f"certifi not available ({_e})"

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import qrcode

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import lyrics_sources as LS      # ตัวเลือก track ของ auto-caption ต้องใช้ร่วมกับ gen_lyrics
import lyrics_conf as LC        # สูตรป้ายความมั่นใจ ใช้ร่วมกับ verify_lyrics

BASE = Path(__file__).parent
# แคชโมเดล HuggingFace ที่เดียวกับ scripts/gen_lyrics.py + fa_align.py (ครบทุกโมเดลอยู่แล้วใน .cache/hf)
# ต้องตั้งตั้งแต่ต้น: ของเดิมปล่อยให้ import gen_lyrics/fa_align ตั้งให้กลางทาง (import ครั้งแรกตอน broadcast แรก)
# demucs ที่ spawn ก่อน/หลังจึงใช้แคชคนละที่ -> HTDemucs ถูกโหลดซ้ำไว้ทั้งใน ~/.cache และในโปรเจกต์
os.environ.setdefault("HF_HOME", str(BASE / ".cache" / "hf"))
os.environ.setdefault("HF_HUB_CACHE", str(BASE / ".cache" / "hf" / "hub"))
os.environ.setdefault("XDG_CACHE_HOME", str(BASE / ".cache"))
SONGS = BASE / "songs"
SONGS.mkdir(exist_ok=True)
DL_DIR = SONGS / "yt"   # อาร์ไคฟ์เพลงที่โหลดจาก YouTube (1 โฟลเดอร์/เพลง)
DL_DIR.mkdir(exist_ok=True)
THUMB_CACHE = SONGS / ".thumbs"   # แคชภาพปก ดึงมาไว้ในเครื่อง (กันภาพคิวไม่ขึ้น)
THUMB_CACHE.mkdir(exist_ok=True)
LYRICS_IN = BASE / "lyrics-in"   # ไฟล์เนื้อที่คนวาง/แก้เอง — gen_lyrics ให้สิทธิ์ก่อนทุกแหล่ง
STUDIO_FILE = BASE / ".studio.json"   # PIN + secret ของหน้า /studio (ไม่เข้า git)
# --- ชื่อโฟลเดอร์เพลง: "<ชื่อเพลง> [<videoId>]" -------------------
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SUF_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")      # ยึดท้ายสุด ชื่อเพลงที่มี [..] เองไม่หลอก
_BAD_CH = str.maketrans({c: "-" for c in '/\\:*?"<>|'})
_VTT_NAME = re.compile(r"^(sub|auto)\.[a-z]{2,3}\.vtt$")   # ซับ/คำบรรยายอัตโนมัติ ภาษาไหนก็ได้
_KEY_NAME = re.compile(r"^(vocals|no_vocals)\.k[+-]\d\.m4a$")  # สเต็มที่เลื่อนคีย์แล้ว (vocals.k+2.m4a)
_SONG_FILES = frozenset({"video.mp4", "audio.m4a", "vocals.m4a",
                         "no_vocals.m4a", "cover.jpg", "info.json",
                         "lyrics.json", "sub.th.vtt", "sub.en.vtt",
                         "auto.th.vtt",        # auto-caption ของ YouTube
                         "lyrics.words.json"})  # เวลารายตัวอักษร (โหมดคาราโอเกะไล่สี)


def _safe_name(title: str, vid: str, max_bytes: int = 180) -> str:
    t = unicodedata.normalize("NFC", title or "")
    # ตัด control + format char (U+200B ฯลฯ) — ภาษาไทยบางชื่อมีติดมาจริง
    t = "".join(c for c in t
                if ord(c) >= 32 and ord(c) != 127 and unicodedata.category(c) != "Cf")
    t = t.translate(_BAD_CH)
    t = " ".join(t.split())
    # ตัดเป็น "ไบต์" ไม่ใช่ตัวอักษร — ไทย 3 ไบต์/ตัว ขีดจำกัดจริงของ APFS คือ 255 ไบต์
    while len(t.encode("utf-8")) > max_bytes:
        t = t[:-1]
    t = t.strip(" .").lstrip(".")           # ท้ายมีจุด/ช่องว่าง = พังบน SMB, หน้ามีจุด = โฟลเดอร์ซ่อน
    return f"{t} [{vid}]" if t else vid


def _vid_ok(v: Any) -> bool:
    """videoId ที่มาจากภายนอก — ต้องเป็นสตริง 11 ตัวตามรูปแบบ YouTube เป๊ะ ๆ
    ใช้ fullmatch เพราะ `$` ของ re.match ยอมให้มี \\n ต่อท้าย
    ห้ามปล่อยค่าที่ไม่ผ่านไปถึง _song_dir: "../../x" หรือ "/abs" กลายเป็นโฟลเดอร์นอกคลัง
    แล้ว _dl_scrub จะลบรูป .png/.webp ในนั้น ส่วนค่าที่ไม่ใช่สตริงทำ room.state() พังทั้งห้อง"""
    return isinstance(v, str) and _VID_RE.fullmatch(v) is not None


_dir_cache: dict[str, Path] = {}
_dir_scan_at = 0.0


def _vid_of_dir(p: Path) -> str | None:
    if not p.is_dir() or p.name.startswith("."):
        return None
    m = _SUF_RE.search(p.name)
    if m:
        return m.group(1)
    return p.name if _VID_RE.match(p.name) else None


def _rescan_dirs() -> None:
    global _dir_cache, _dir_scan_at
    idx: dict[str, Path] = {}
    for p in sorted(DL_DIR.iterdir()):
        vid = _vid_of_dir(p)
        if not vid:
            continue
        old = idx.get(vid)
        if old is None or (((p / "video.mp4").is_file(), bool(_SUF_RE.search(p.name)))
                           > ((old / "video.mp4").is_file(), bool(_SUF_RE.search(old.name)))):
            idx[vid] = p
    # สลับทั้งก้อนทีเดียว ห้าม clear()+update() dict เดิม: worker (to_thread) กับ endpoint แบบ sync
    # อ่าน/วนลูป dict นี้พร้อมกัน จะเห็นมันว่างชั่วขณะ (ได้ path สำรองผิดโฟลเดอร์)
    # หรือเจอ "dictionary changed size during iteration" — dict ที่แจกออกไปแล้วต้องไม่ถูกแก้อีก
    _dir_cache = idx
    _dir_scan_at = time.monotonic()


def _invalidate_dirs() -> None:
    global _dir_scan_at
    _dir_scan_at = 0.0


def _dir_index() -> dict[str, Path]:
    if time.monotonic() - _dir_scan_at > 2.0:
        _rescan_dirs()
    return _dir_cache


def _song_dir(vid: str) -> Path:
    """videoId -> โฟลเดอร์จริง (ยังไม่มี -> คืนชื่อแบบเก่าไว้เป็นที่พัก)
    จำกัดการสแกนซ้ำไว้ 2 วิ เพราะฟังก์ชันนี้ถูกเรียกทุก item ทุก broadcast"""
    if not _vid_ok(vid):
        # ด่านสุดท้าย: ห้าม raise (ถูกเรียกทุก broadcast) — คืนที่ที่ไม่มีอยู่จริงและอยู่ในคลังเสมอ
        return DL_DIR / ".invalid"
    p = _dir_cache.get(vid)
    if p is not None and p.is_dir():
        return p
    if p is not None or time.monotonic() - _dir_scan_at > 2.0:
        _rescan_dirs()
        p = _dir_cache.get(vid)
        if p is not None:
            return p
    return DL_DIR / vid


HISTORY_FILE = BASE / "history.json"   # ประวัติเพลงที่เคยเพิ่ม (ทุกมือถือในห้อง)
TV_FILE = BASE / "tv.json"             # ตั้งค่าหน้าจอหลัก (ตั้งจาก Studio เท่านั้น)
TV_DIR = BASE / ".tv"                  # รูปมุมขวาบนของจอหลัก (logo.png)
COMBOS_FILE = BASE / "combos.json"     # 🎬 คอมโบ (ชุดเพลงที่ตัดจุดเริ่ม/จบไว้เอง) — จัดใน Studio แท็บ ✂️
HISTORY_MAX = 200


def _migrate_song_dirs(dry: bool = False) -> list[tuple[str, str]]:
    """เปลี่ยนชื่อโฟลเดอร์เก่า <videoId>/ -> <ชื่อเพลง> [<videoId>]/
    ปลอดภัย: rename อย่างเดียว ไม่ลบ ไม่ copy, ข้ามโฟลเดอร์ที่โหลดไม่ครบ
    idempotent: รันซ้ำได้ ครั้งที่สองเป็น no-op"""
    hist_title: dict[str, str] = {}
    for e in reversed(_load_history()):
        if e.get("videoId") and e.get("title"):
            hist_title[e["videoId"]] = e["title"]

    done: list[tuple[str, str]] = []
    for d in sorted(DL_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if _SUF_RE.search(d.name):
            continue                                   # ทำไปแล้ว
        if not _VID_RE.match(d.name):
            print(f"[migrate] ข้าม (ชื่อไม่รู้จัก): {d.name}")
            continue
        vid = d.name
        if not (d / "video.mp4").is_file():
            print(f"[migrate] ข้าม (โหลดไม่ครบ): {vid}")
            continue                                   # กำลังโหลดค้างอยู่ ห้ามแตะ
        title = ""
        ij = d / "info.json"
        if not ij.is_file():
            ij = next(iter(d.glob("*.info.json")), None)
        if ij:
            try:
                title = json.loads(ij.read_text("utf-8")).get("title") or ""
            except Exception:
                pass
        title = title or hist_title.get(vid, "")
        if not title:
            print(f"[migrate] ข้าม (ไม่รู้ชื่อเพลง): {vid}")
            continue
        tgt = DL_DIR / _safe_name(title, vid)
        if tgt == d:
            continue
        if tgt.exists():
            print(f"[migrate] ข้าม (ปลายทางมีอยู่แล้ว): {tgt.name}")
            continue
        done.append((d.name, tgt.name))
        if not dry:
            try:
                d.rename(tgt)
            except OSError as exc:
                print(f"[migrate] {vid} ล้มเหลว: {exc}")
                done.pop()
    if done and not dry:
        _invalidate_dirs()
    print(f"[migrate] {'จะเปลี่ยน' if dry else 'เปลี่ยน'}ชื่อ {len(done)} โฟลเดอร์")
    return done


def _load_history() -> list[dict[str, Any]]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


# --- ตั้งค่าหน้าจอหลัก (ทีวี) ------------------------------------------
# ค่าเริ่มต้น = หน้าตาเดิมทุกอย่าง / ตั้งจาก Studio แล้ว broadcast ไปกับ state ให้จอเปลี่ยนสด
# แต่ละค่ามีชนิด + ช่วงของมัน ค่าที่ส่งมาผิดชนิดทิ้ง ค่าเกินช่วงบีบเข้าขอบ (จอไม่พังเพราะค่าแปลก ๆ)
TV_CHIPS = ("guide", "master", "music", "key", "lyrsrc", "next")
TV_SCHEMA: dict[str, tuple] = {
    "title": (bool, True),           # แถบชื่อเพลงด้านบน
    "titleHide": (int, 0, 0, 60),    # 0 = โชว์ตลอด / N = เริ่มเพลงแล้วโชว์ N วิ แล้วจางหาย
    "singer": (bool, True),          # ชิปชื่อคนร้อง
    "chips": (list, ["guide"]),      # สถานะหลังชื่อเพลง (เลือกจาก TV_CHIPS)
    "lyrScale": (int, 100, 60, 160),  # ขนาดซับ %
    "lyrColor": (str, "#ffffff"),    # สีตัวอักษรซับ
    "lyrDim": (int, 55, 15, 100),    # ความสว่างบรรทัดที่ยังไม่ถึง %
    "karaColor": (str, "#ff6fa6"),   # สีที่ร้องไปแล้ว (โหมดคาราโอเกะ)
    "karaSmooth": (bool, True),      # ไล่สีนุ่ม: เติมสีทีละตัวอักษรจากซ้ายไปขวา (ปิด = เปลี่ยนสีทีละกลุ่มอักษรทันที)
    "lyrBg": (int, 100, 0, 100),     # ความเข้มพื้นไล่เฉดใต้ซับ %
    "lyrShadow": (int, 2, 0, 3),     # เงาตัวอักษร: 0 ไม่มี / 1 บาง / 2 ปกติ / 3 ขอบหนา
    "lyrLift": (int, 0, 0, 20),      # ยกซับขึ้นจากขอบล่าง (vh)
    "qr": (bool, True),
    "qrSize": (int, 100, 60, 200),
    "time": (bool, True),            # เวลาเพลงมุมซ้ายล่าง
    "next": (bool, True),            # การ์ดเพลงถัดไป (ตอนไม่มีเนื้อ)
    "addCard": (bool, True),         # การ์ด "เพิ่มเข้าคิว" ที่เด้งตอนมีคนสั่งเพลง
    "logo": (bool, False),           # รูปมุมขวาบน (อัปจาก Studio)
    "logoSize": (int, 100, 60, 200),
    "idleText": (str, ""),           # ข้อความหน้าจอว่าง (ตอนไม่มีเพลง)
    "countdown": (bool, True),       # ♪ ● ● ● นับถอยหลังก่อนเข้าท่อนแรก/หลังช่วงดนตรี
    "voices": (bool, True),          # 👥 แยกเสียงร้อง: คนที่ 2/3 คนละสี, (คอรัส/แอดลิบในวงเล็บ) ตัวเล็กจาง
    "fadeIn": (int, 2, 0, 5),        # เฟดเข้าตอนเริ่มทุกเพลง (วิ) 0 = ไม่เฟด
    "fadeOut": (int, 3, 0, 5),       # เฟดออกตอนจบ/ข้าม (ภาพ+เสียง) 0 = ตัดทันทีแบบเดิม
    "custom": (bool, False),         # ✂️ โหมด Custom: เล่นแต่ละเพลงจากจุดเริ่มถึงจุดจบ
    "customLead": (int, 4, 1, 10),   # อัตโนมัติ: เริ่มก่อนท่อนแรกกี่วิ
    "customTail": (int, 5, 0, 15),   # อัตโนมัติ: จบหลังท่อนสุดท้ายกี่วิ
    "customAud": (int, 0, 0, 5),     # โหมด Custom: เฟดเสียงออกกี่วิ (0 = ตัดเสียงทันที ภาพยังเฟด)
    "skipBtn": (bool, True),         # ⏩ ปุ่มข้ามอินโทรบนรีโมท
    "skipMin": (int, 15, 5, 60),     # อินโทรยาวเกินกี่วิถึงโผล่ปุ่ม
}
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_tv(raw: Any, base: dict | None = None) -> dict:
    out = dict(base) if base else {k: (list(v[1]) if isinstance(v[1], list) else v[1]) for k, v in TV_SCHEMA.items()}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        spec = TV_SCHEMA.get(k)
        if not spec:
            continue
        typ = spec[0]
        if typ is bool and isinstance(v, bool):
            out[k] = v
        elif typ is int and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = int(max(spec[2], min(spec[3], round(v))))
        elif typ is list and isinstance(v, list):
            out[k] = [c for c in TV_CHIPS if c in v]          # เรียงตามลำดับมาตรฐาน ตัดของแปลกทิ้ง
        elif typ is str and isinstance(v, str):
            if k.endswith("Color"):
                if _HEX_RE.match(v):
                    out[k] = v.lower()
            else:
                out[k] = " ".join(v.split())[:80]
    return out


def _load_tv() -> dict:
    try:
        return _clean_tv(json.loads(TV_FILE.read_text(encoding="utf-8")))
    except Exception:
        return _clean_tv({})


def _tv_logo() -> Path:
    return TV_DIR / "logo.png"


def _tv_public(tv: dict) -> dict:
    out = dict(tv)
    f = _tv_logo()
    if f.is_file():
        out["logoUrl"] = f"/tv/logo.png?v={int(f.stat().st_mtime * 1000)}"
    return out


def _save_history() -> None:
    try:
        # atomic: ปิดเครื่อง/โปรเซสตายกลางเขียน ไฟล์ครึ่ง ๆ อ่านไม่ออก = _load_history คืน [] ประวัติหายหมด
        _write_json_atomic(HISTORY_FILE, room.history)
    except Exception as _e:
        print(f"[history] save failed: {_e}")
MIX_RANGE = {"vocal": (0, 100), "music": (0, 100), "master": (0, 100), "key": (-6, 6)}
MIX_DEFAULT = {"vocal": 100, "music": 100, "master": 80, "key": 0}
DEFAULT_SINGER = "noname"              # คนที่ไม่ได้กรอกชื่อในตั้งค่าละเอียดของรีโมท
LYR_MODES = ("scroll", "dual", "karaoke", "off")   # เลื่อนขึ้นแบบเดิม / 2 บรรทัดคงที่ / 2 บรรทัด+ไล่สีตามเสียงร้อง / ไม่ขึ้นเนื้อ
MEDIA_EXT = {".mp4", ".m4v", ".mkv", ".webm", ".mp3", ".m4a", ".wav", ".flac", ".ogg"}
PORT = 8080
WATCHDOG_EVERY = 10.0   # วินาที — รอบกวาดงานตกหล่น/ประเมินลำดับคิวใหม่

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """เพลงเก่าที่โหลดไว้ก่อนมีฟีเจอร์นี้ -> ทยอยแยกเสียงตอนว่าง (ไม่แย่งคิวเพลงที่เพิ่งสั่ง)"""
    _migrate_song_dirs()            # ทำก่อน backfill และก่อน client ต่อเข้ามา

    async def run() -> None:
        await asyncio.sleep(5)          # ให้เซิร์ฟเวอร์ตั้งตัว/จอต่อเข้ามาก่อน
        if _fix_history_titles():       # ประวัติเก่าที่เก็บ "YouTube: <id>" ไว้ก่อนมีตัวดึงชื่อ
            await asyncio.to_thread(_save_history)
        n = m = w = b = 0
        for vid, d in sorted(_dir_index().items()):
            try:
                if await asyncio.to_thread(_drop_tail_junk, vid):
                    room.archive_rev += 1
                    await _enqueue_words(vid, force=True)    # บรรทัดเปลี่ยน -> ทำไล่สีคาราโอเกะใหม่
            except Exception as exc:
                print(f"[lyr] {vid} ลบบรรทัดเลยท้ายคลิปไม่ได้: {type(exc).__name__}: {exc}")
            if (d / "audio.m4a").is_file() and not _has_stems(vid):
                await _enqueue_sep(vid)
                n += 1
                continue
            if _lyr_meta(vid)[1] <= 0:
                await _enqueue_lyr(vid)
                m += 1
                continue
            if await _enqueue_best(vid):           # เลือกเนื้อดีที่สุดก่อน เสร็จแล้วมันสั่งเวลารายคำ + ตรวจเวลาต่อเอง
                b += 1
                continue
            if await _enqueue_words(vid, force=_words_stale_auto(vid)):
                w += 1
            ck = _chk_info(vid)
            if (ck.get("measuredBy") != "fa" or int(ck.get("v") or 1) < CHECK_VERSION) \
                    and _song_lang(vid)[0] in LS.FA_LANGS and _fa_scriptable(vid) and _audio_for(vid):
                # ป้ายความมั่นใจของเพลงเก่ายังมาจาก whisper / ตัวตรวจรุ่นเก่า / ยังไม่เคยตรวจ -> วัดใหม่ (CPU ลำดับต่ำสุด)
                await _enqueue_verify(vid)
        if n:
            print(f"[sep] backfill: เข้าคิวแยกเสียงเพลงเก่า {n} เพลง")
        if m:
            print(f"[lyr] backfill: เข้าคิวหาเนื้อเพลงเก่า {m} เพลง")
        if b:
            print(f"[best] backfill: เข้าคิวเทียบเนื้อจากทุกแหล่ง {b} เพลง")
        if w:
            print(f"[words] backfill: เข้าคิวทำเวลารายคำ (คาราโอเกะ) {w} เพลง")
        await _reprioritize()      # มีคนสั่งเพลงไว้ก่อน backfill เสร็จ -> เพลงในห้องต้องได้คิวก่อน
        # ภาษาของเพลงเก่า: ชื่อ/แทร็ก ASR ก่อน (ไม่ใช้ GPU) ที่ยังไม่รู้ค่อยให้ whisper ฟังตอนว่าง
        # แล้วเพลงที่ไม่ใช่ไทยซึ่งเนื้อได้มาแบบ "คิดว่าเป็นไทย" -> หาเนื้อใหม่ครั้งเดียว
        mig = 0
        for vid, d in sorted(_dir_index().items()):
            try:
                if not LS.read_lang(d):
                    LS.song_lang(d, save=True)
                    _lang_cache.pop(vid, None)
                if _song_lang(vid)[1] in ("unknown", "yt-asr", "default") and _audio_for(vid):
                    await _ensure_lang(vid)          # ยังไม่รู้/รู้แบบชั่วคราว -> lrclib / เนื้อที่ FA ยืนยัน / whisper
                if await _lang_migrate(vid):
                    mig += 1
            except Exception as exc:
                print(f"[lang] {vid} {type(exc).__name__}: {exc}")
        if mig:
            print(f"[lang] backfill: เพลงต่างภาษาที่สั่งหาเนื้อใหม่ {mig} เพลง")

    async def watchdog() -> None:
        """ตาข่ายรับของทุกไปป์ไลน์ — ของเดิม _reprioritize เดินเฉพาะตอนมีคนกดปุ่ม
        งานที่ตกหล่นระหว่างทาง (worker ตาย / คิวว่างเปล่าทั้งที่ยังไม่เสร็จ /
        จังหวะแย่งคิวติด cooldown) จึงค้างยาวจนกว่าจะมีคนแตะรีโมตอีกครั้ง"""
        while True:
            await asyncio.sleep(WATCHDOG_EVERY)
            try:
                async with room.lock:
                    await _reprioritize()
                    if await _autoplay_fill():     # จอว่างแต่เปิดสุ่มไว้ (เช่น เปิดไว้ก่อนจอหลักต่อเข้ามา)
                        await room.broadcast()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[watchdog] {type(exc).__name__}: {exc}")

    # อ่านล็อกอิน YouTube ไว้ตั้งแต่เปิดเซิร์ฟเวอร์ (ไม่รอ) — macOS ถามสิทธิ์ Keychain ตอนคนเพิ่งกดเปิดยังอยู่หน้าเครื่อง
    # ไม่ใช่ตอนแขกกดเพิ่มเพลงใหม่เพลงแรก
    _yt_cookies(wait=0)
    tasks = [asyncio.create_task(run()), asyncio.create_task(watchdog())]
    if WARM:                        # โหลดโมเดลหาเนื้อไว้รอ — เพลงแรกจะได้เร็วเหมือนเพลงหลัง ๆ
        tasks.append(asyncio.create_task(_warmup()))
    yield
    for t in tasks:
        t.cancel()
    _kill_children()     # demucs/gen_lyrics/fa_align ที่ทำค้างอยู่ — ไม่งั้นการปิดรอจนงานจบ และลูกกำพร้ากิน GPU ต่อ


app = FastAPI(lifespan=_lifespan)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


_local_ip_cache: tuple[float, set[str]] = (0.0, set())


def _local_ips() -> set[str]:
    """IP ทุกอันของเครื่องนี้ — แคช 30 วิ เพราะ IP เปลี่ยนได้จริง
    ต้องรวม LAN IP ด้วย ไม่ใช่แค่ loopback เพราะเจ้าของเครื่องมักเปิดผ่าน IP ตัวเอง"""
    global _local_ip_cache
    t, cached = _local_ip_cache
    if time.monotonic() - t < 30.0 and cached:
        return cached
    ips = {"127.0.0.1", "::1", "localhost"}
    try:
        for *_, sa in socket.getaddrinfo(socket.gethostname(), None):
            ips.add(sa[0])
    except Exception:
        pass
    try:
        ips.add(lan_ip())
    except Exception:
        pass
    _local_ip_cache = (time.monotonic(), ips)
    return ips


def _is_local(host: str | None) -> bool:
    if not host:
        return False
    return host.split("%")[0] in _local_ips()      # ตัด zone id ของ IPv6 link-local


def _host_name(host_header: str | None) -> str:
    """ค่า Host header -> ชื่อเครื่องล้วน (ตัดพอร์ต / วงเล็บของ IPv6)"""
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else h[1:]
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def _host_is_local_name(host_header: str | None) -> bool:
    """Host ที่พิมพ์เข้ามาเป็นชื่อ/IP ของเครื่องนี้จริงไหม — ใช้คู่กับสิทธิ์ "เครื่องตัวเองผ่านเลย"
    กัน DNS rebinding: เว็บอันตรายที่ชื่อโดเมนชี้กลับมา 127.0.0.1 จะมี Origin == Host ผ่านด่านแรกได้
    แต่ Host ของมันเป็นโดเมนแปลก ไม่ใช่ localhost/IP ของเครื่อง/ชื่อ .local"""
    h = _host_name(host_header)
    if not h:
        return False
    extra = {x.strip().lower() for x in os.environ.get("KARA_ALLOWED_HOSTS", "").split(",") if x.strip()}
    return (h in _local_ips() or h in extra or h.endswith(".local")
            or h == socket.gethostname().lower())


def _same_origin(headers) -> bool:
    """คำขอมาจากหน้าเว็บของเราเองไหม — เบราว์เซอร์แนบ Origin มาเสมอกับ WebSocket และ POST ข้ามเว็บ
    มี Origin: host:port ต้องตรงกับ Host / ไม่มี Origin: ยอมเฉพาะที่ Sec-Fetch-Site ไม่ได้บอกว่าข้ามเว็บ
    หน้า player/remote/studio ทั้งหมดเสิร์ฟจากเซิร์ฟเวอร์นี้ จึงผ่านเสมอ"""
    origin = headers.get("origin")
    if origin:
        if origin == "null":
            return False
        from urllib.parse import urlsplit
        try:
            return urlsplit(origin).netloc.lower() == (headers.get("host") or "").strip().lower()
        except ValueError:
            return False
    return headers.get("sec-fetch-site") in (None, "", "same-origin", "none")


def lan_url() -> str:
    """คำนวณใหม่ทุกครั้ง — IP เครื่องเปลี่ยนได้ ถ้าจำค่าไว้ QR จะชี้ไป IP ที่ตายแล้ว"""
    return f"http://{lan_ip()}:{PORT}"


def base_url() -> str:
    """ลิงก์ที่ให้แขกเปิด (QR บนจอ / idle URL): ถ้าตั้ง publicUrl ใน .studio.json ไว้ (โดเมนผ่าน Cloudflare Tunnel)
    ใช้อันนั้น ใช้ได้ทั้งในบ้านและนอกบ้าน — ไม่งั้น IP ในวงแลนแบบเดิม (แก้ไฟล์แล้วมีผลทันที ไม่ต้องรีสตาร์ท)"""
    try:
        pub = _studio_cfg().get("publicUrl") or ""
    except Exception:
        pub = ""
    return pub or lan_url()


BASE_URL = lan_url()      # ตอน import ยังไม่มี _studio_cfg — แบนเนอร์ใช้ base_url() ตอนรันจริง

# --- ส่งข้อความ WebSocket แบบมีเพดานเวลา ---------------------------------
# มือถือที่ล็อกจอ (แท็บถูกแช่แข็งแต่ TCP ยังตอบ) ไม่อ่านข้อมูล -> บัฟเฟอร์เต็ม -> send() ของ uvicorn
# รอ writable ไปเรื่อย ๆ และ ping timeout ก็ปลดไม่ได้เพราะ transport เลื่อน connection_lost
# ออกไปจนกว่าจะส่งข้อมูลที่ค้างหมด = ค้างได้ไม่มีกำหนด ของเดิมส่งทีละเครื่องขณะถือ room.lock
# จึงทำให้ทั้งห้อง (รวม "ended" ของจอหลัก) ค้างตามไปด้วย
WS_SEND_TIMEOUT = 5.0
_bg_tasks: set[asyncio.Task] = set()      # ถือ reference ไว้ ไม่งั้น task ที่ยังไม่จบถูก GC เก็บกลางทาง


def _bg(coro) -> None:
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


async def _ws_send(ws: WebSocket, msg: str) -> bool:
    """ส่ง 1 เครื่อง ไม่เกิน WS_SEND_TIMEOUT — ยกเลิกกลางทางได้ปลอดภัย เพราะจุดรอมีจุดเดียว
    (รอ writable) ก่อนจะแตะเฟรม/ตัวบีบอัดใด ๆ"""
    try:
        await asyncio.wait_for(ws.send_text(msg), WS_SEND_TIMEOUT)
        return True
    except Exception:
        return False


def _ws_drop(ws: WebSocket) -> None:
    """เครื่องที่ส่งไม่ทัน/พัง -> เอาออกจากห้องทันที แล้วค่อยปิดเบื้องหลัง (ห้าม await ตอนถือ lock)
    เครื่องนั้นต่อใหม่เองเมื่อกลับมา แล้วได้ state ล่าสุดตอนต่อ"""
    room.clients.discard(ws)

    async def _close() -> None:
        try:
            await asyncio.wait_for(ws.close(code=1011), WS_SEND_TIMEOUT)
        except Exception:
            pass
    _bg(_close())


class Room:
    def __init__(self) -> None:
        self.queue: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.playing = False
        self.restart_token = 0
        self.mix = dict(MIX_DEFAULT)
        self.lyr_mode = "karaoke"         # รูปแบบการขึ้นเนื้อเพลงบนจอ — ค่าระดับห้อง เหมือน mix (เริ่มต้น = ไล่สีตามที่ร้อง)
        self.autoplay = False             # คิวหมดแล้วสุ่มเพลงจากคลังมาเล่นต่อ (ตั้งจากรีโมท)
        self.auto_recent: list[str] = []  # เพลงที่เพิ่งสุ่มไป กันสุ่มซ้ำเร็วเกิน
        self.tv = _load_tv()              # ตั้งค่าหน้าจอหลัก (Studio)
        self.archive_rev = 0
        self.player_id: str | None = None
        self.pos = 0.0
        self.pos_at = time.monotonic()
        self.fading: str | None = None    # id ใบคิวที่กำลังเฟดออกก่อนเปลี่ยนเพลง (กดข้าม/เล่นเลย)
        self.fade_token = 0               # งานเฟดที่ค้างอยู่ — เลขไม่ตรง = ถูกแทน/ยกเลิกแล้ว
        self.seek_token = 0               # ⏩ ข้ามอินโทร: จอ seek ไป position เมื่อเลขเปลี่ยน
        self.clients: set[WebSocket] = set()
        self.lock = asyncio.Lock()
        self.history = _load_history()

    def position(self) -> float:
        """ตำแหน่งเพลงตอนนี้ — เดินต่อจากค่าที่จอหลักรายงานล่าสุดถ้ากำลังเล่นอยู่"""
        if not self.current:
            return 0.0
        if not self.playing:
            return max(0.0, self.pos)
        return max(0.0, self.pos + (time.monotonic() - self.pos_at))

    def state(self) -> dict[str, Any]:
        # เติมสถานะแยกเสียงล่าสุดลงทุก item ก่อนส่ง (แหล่งความจริงเดียวคือ _sep_state + ไฟล์บนดิสก์)
        for it in ([self.current] if self.current else []) + self.queue:
            _dl_fields(it)
            _sep_fields(it)
            _lyr_fields(it)
            _fix_fields(it)      # ต้องท้ายสุด: อ่านผลของสามตัวบน
        if self.current:
            _span_fields(self.current, self.tv)
        return {
            "type": "state",
            "current": self.current,
            "queue": self.queue,
            "playing": self.playing,
            "restartToken": self.restart_token,
            "mix": self.mix,
            "lyrMode": self.lyr_mode,
            "autoplay": self.autoplay,
            "tv": _tv_public(self.tv),
            "archiveRev": self.archive_rev,
            "jobsRev": _jobs_rev(),
            "position": self.position(),
            "fading": self.fading,
            "seekToken": self.seek_token,
            "combos": sum(1 for c in _combos() if c["items"]),   # รีโมทโชว์การ์ด 🎬 เมื่อมีคอมโบ
            "baseUrl": base_url(),
        }

    async def broadcast(self) -> None:
        await self.send_all(json.dumps(self.state()))

    async def send_all(self, msg: str) -> None:
        # ส่งพร้อมกันทุกเครื่อง แต่ละเครื่องมีเพดานเวลา — เครื่องเดียวช้าต้องไม่ถ่วงทั้งห้อง
        clients = list(self.clients)
        if not clients:
            return
        ok = await asyncio.gather(*(_ws_send(ws, msg) for ws in clients))
        for ws, good in zip(clients, ok):
            if not good:
                _ws_drop(ws)

    # --- queue ops -------------------------------------------------
    def add(self, item: dict[str, Any]) -> None:
        item["id"] = uuid.uuid4().hex[:8]
        item["addedAt"] = time.time()
        self.queue.append(item)
        if self.current is None:
            self.next()

    def next(self) -> None:
        self.mix["vocal"] = MIX_DEFAULT["vocal"]   # ไกด์เสียงร้อง = ค่าเริ่มต้นทุกเพลง
        self.mix["key"] = MIX_DEFAULT["key"]
        # master/music ไม่รีเซ็ต — เป็นค่าของห้อง ถ้าล้างทุกเพลงจะน่ารำคาญ
        self.current = self.queue.pop(0) if self.queue else None
        self.playing = self.current is not None
        self.fading = None
        self.fade_token += 1
        # โหมด Custom / คอมโบ: เริ่มที่จุดเริ่ม — จอ seek ไปเองผ่านกลไกเล่นต่อจากตำแหน่งเดิม (resumeAt)
        start = _play_span(self.current, self.tv)[0] if self.current else 0.0
        if self.current:
            self.current["startAt"] = start
        self.pos = start
        self.pos_at = time.monotonic()

    def remove(self, item_id: str) -> None:
        # เอาออกจากคิว ≠ ยกเลิกโหลด/แยกเสียง — โปรเจกต์นี้ตั้งใจสะสมอาร์ไคฟ์ไว้
        # งานที่ค้างอยู่จะตกไปอันดับ _BACKLOG เองเพราะ _prio_map() ไม่เห็นมันแล้ว
        self.queue = [q for q in self.queue if q["id"] != item_id]

    def find(self, item_id: str | None) -> dict[str, Any] | None:
        for it in ([self.current] if self.current else []) + self.queue:
            if it.get("id") == item_id:
                return it
        return None

    def move(self, item_id: str, delta: int) -> None:
        for i, q in enumerate(self.queue):
            if q["id"] == item_id:
                j = max(0, min(len(self.queue) - 1, i + delta))
                self.queue.insert(j, self.queue.pop(i))
                return


room = Room()


def _jobs_rev() -> str:
    """ลายนิ้วมือของสถานะงานเบื้องหลังทุกชนิด — Studio ใช้ตัดสินว่าต้องดึงรายการทั้งคลังใหม่ไหม
    (ของเดิมดึงทุกครั้งที่มี state แม้แค่มีคนลากสไลเดอร์เสียง = ทุก 1.5 วิ อ่านไฟล์ทั้งคลังบน event loop)"""
    h = hashlib.sha1()
    for st in (_dl_state, _sep_state, _lyr_state, _words_state, _best_state, _verify_state):
        h.update(json.dumps(st, sort_keys=True, default=str).encode())
    for q in (_dl_pending, _sep_pending, _lyr_pending, _lyrfind_pending, _words_pending, _best_pending):
        h.update(("|".join(sorted(q.items)) + "#").encode())
    return h.hexdigest()[:12]

# --- ลำดับความสำคัญของงานเบื้องหลัง -----------------------------------
# ทุกไปป์ไลน์ (โหลด/แยกเสียง/หาเนื้อ) ต้องเดินตาม "ลำดับคิวห้องตอนนี้" ไม่ใช่ลำดับที่กดเพิ่ม
# คนกดเลื่อนคิวแล้วคาดหวังว่าเพลงที่เลื่อนขึ้นมาจะถูกเตรียมก่อน — ของเดิมเป็น FIFO
# ตามลำดับ add จึงยังไล่ทำเพลงเดิมต่อ เพลงที่ถูกดันขึ้นมาเลยไม่มีเนื้อ/ไม่มีไกด์เสียงร้อง
_BACKLOG = 1 << 20          # ไม่ได้อยู่ในห้อง = งานตอนว่าง (สะสมอาร์ไคฟ์) ทำทีหลังเสมอ
_PREEMPT_RANK = 1           # แย่งงานให้เฉพาะเพลงที่เล่นอยู่ (0) กับเพลงถัดไป (1) เท่านั้น


def _prio_map() -> dict[str, int]:
    """videoId -> อันดับ: 0 = เพลงที่เล่นอยู่, 1..N = ตำแหน่งในคิว
    สร้างใหม่ทุกครั้งที่หยิบงาน — ห้ามแคช เพราะคิวเปลี่ยนได้ทุกวินาที"""
    m: dict[str, int] = {}
    cur = room.current or {}
    if cur.get("videoId"):
        m[cur["videoId"]] = 0
    for i, q in enumerate(room.queue):
        if q.get("videoId"):
            m.setdefault(q["videoId"], i + 1)      # เพลงซ้ำ -> ยึดตำแหน่งแรกสุด
    return m


def _prio(vid: str | None, m: dict[str, int] | None = None) -> int:
    return (m if m is not None else _prio_map()).get(vid or "", _BACKLOG)


class _Pending:
    """งานที่รออยู่ — เก็บเป็น dict ไม่ใช่ asyncio.Queue เพราะลำดับจริงคือ
    "ลำดับคิวห้องตอนนี้" ซึ่งเรียงใหม่ได้ตลอดเวลา แต่ Queue จัดลำดับใหม่ไม่ได้
    ระบบ urgent/backlog สองชั้นแบบเดิมยุบมาอยู่ในนี้: เพลงที่ไม่อยู่ในห้อง = _BACKLOG เอง"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.items: dict[str, int] = {}     # videoId -> ลำดับที่เข้าคิว (ตัวตัดสินเมื่ออันดับเท่ากัน)
        self.seq = 0
        self.wake = asyncio.Event()

    def __len__(self) -> int:
        return len(self.items)

    def has(self, vid: str) -> bool:
        return vid in self.items

    def push(self, vid: str) -> None:
        if vid not in self.items:
            self.seq += 1
            self.items[vid] = self.seq
        self.wake.set()

    def discard(self, vid: str) -> None:
        self.items.pop(vid, None)

    def best(self, m: dict[str, int] | None = None) -> tuple[str, int] | None:
        """(vid, อันดับ) ของงานที่ควรทำก่อน — ยังไม่ถอดออกจากคิว"""
        if not self.items:
            return None
        m = m if m is not None else _prio_map()
        vid = min(self.items, key=lambda v: (m.get(v, _BACKLOG), self.items[v]))
        return vid, m.get(vid, _BACKLOG)

    def take_now(self) -> str | None:
        hit = self.best()
        if hit:
            self.items.pop(hit[0], None)
        return hit[0] if hit else None

    def order(self) -> list[str]:
        """ลำดับงานที่จะทำ — ไว้ส่องใน /api/health"""
        m = _prio_map()
        return sorted(self.items, key=lambda v: (m.get(v, _BACKLOG), self.items[v]))

    async def wait(self) -> None:
        """รอจนมีงาน — นอนบน Event ไม่ busy-loop
        ห้ามมี await คั่นระหว่างเช็ค items กับ clear() ไม่งั้น push() ที่เข้ามาตรงนั้นจะหาย"""
        while not self.items:
            self.wake.clear()
            await self.wake.wait()

    def bump(self) -> None:
        """ลำดับห้องเปลี่ยน -> ปลุก worker ให้เลือกงานใหม่"""
        if self.items:
            self.wake.set()


_dl_pending = _Pending("dl")
_sep_pending = _Pending("sep")
_lyr_pending = _Pending("lyr")
_words_pending = _Pending("words")   # เวลารายตัวอักษรของโหมดคาราโอเกะ (FA)

# --- YouTube search (metadata only, via yt-dlp) ---------------------
import traceback

try:
    from yt_dlp import YoutubeDL, version as ytdlp_version
    _HAS_YTDLP = True
    _YTDLP_VER = ytdlp_version.__version__
except Exception as _e:
    _HAS_YTDLP = False
    _YTDLP_VER = f"not installed ({_e})"

# --- ดาวน์โหลดเพลง (โหลดทีละเพลง ตามลำดับคิว) -------------------------
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
_dl_task: asyncio.Task | None = None
_dl_state: dict[str, dict] = {}    # videoId -> {"status","error"} เหมือน _sep_state/_lyr_state
_added_at: dict[str, float] = {}   # videoId -> เวลาที่มีคนกดเพิ่มเพลงใหม่ (monotonic) ไว้ให้ log บอกว่าแต่ละขั้นเสร็จหลังกดกี่วิ


def _since_add(vid: str | None) -> str:
    t = _added_at.get(vid or "")
    return f" · หลังกดเพิ่ม {time.monotonic() - t:.0f}s" if t else ""


def _dl_fields(item: dict) -> None:
    """เติม dlStatus/localUrl ลง item ตอนจะ broadcast — อ่านจากดิสก์ + _dl_state
    ของเดิมเก็บไว้บน dict ของ item เอง ซึ่งผูกกับ "ใบการ์ด" ไม่ใช่ "เพลง":
    เพิ่มเพลงเดิมซ้ำตอนกำลังโหลด ใบที่สองจะค้างที่ 'รอโหลด' จนกว่า worker จะวนมาถึง
    ทั้งที่ไฟล์เสร็จไปแล้ว — และทำให้จัดลำดับตาม videoId ไม่ได้"""
    vid = item.get("videoId")
    if item.get("source") != "yt" or not vid:
        return
    d = _song_dir(vid)
    if (d / "video.mp4").is_file():
        item["dlStatus"] = "ready"
        item["dlError"] = ""
        item["localUrl"] = f"/song/{vid}/video.mp4"
        item["duration"] = _song_meta(vid)["duration"]     # แถบเวลาบนจอล็อกมือถือ (แคชด้วย mtime)
        if (d / "cover.jpg").is_file():
            item["localThumb"] = f"/song/{vid}/cover.jpg"
        # ชื่อจากคลัง (info.json) คือชื่อจริงเสมอ — เพลงที่วางลิงก์มาจะได้ "YouTube: <id>" ค้างไว้
        # จนโหลดเสร็จ ให้เปลี่ยนเป็นชื่อจริงตรงนี้ ทุกจอจะเห็นชื่อเดียวกับคลัง
        t = _song_meta(vid)["title"]
        if t:
            item["title"] = t
        return
    st = _dl_state.get(vid, {})
    item["dlStatus"] = st.get("status", "queued")
    item["dlError"] = st.get("error", "")
    item.pop("localUrl", None)


def _ffmpeg(args: list[str]) -> None:
    if not FFMPEG:
        raise RuntimeError("ไม่พบ ffmpeg (ติดตั้งผ่าน Homebrew: brew install ffmpeg)")
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
                           capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg หมดเวลา ({FFMPEG_TIMEOUT / 60:.0f} นาที)")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg ล้มเหลว: {(r.stderr or '').strip()[-400:]}")


_FRAG_RE = re.compile(r"\.f\d+$")      # "<vid>.f137" = ไฟล์ fragment ของ yt-dlp


def _in_archive(d: Path) -> bool:
    """โฟลเดอร์เพลงจริงในคลัง (ลูกตรงของ DL_DIR, ไม่ใช่โฟลเดอร์ซ่อน) — ด่านกันลบไฟล์ผิดที่"""
    try:
        return d.resolve().parent == DL_DIR.resolve() and not d.name.startswith(".")
    except OSError:
        return False


def _dl_scrub(d: Path) -> None:
    """ล้างเศษไฟล์ก่อน/หลังโหลด — ต้องทำก่อนลองใหม่ ไม่งั้น fragment เก่ากลายเป็น video.mp4"""
    if not _in_archive(d):
        raise RuntimeError(f"ปฏิเสธการล้างไฟล์นอกคลังเพลง: {d}")
    if not d.is_dir():
        return
    for f in list(d.glob("*.part")) + list(d.glob("*.ytdl")):
        f.unlink(missing_ok=True)
    for f in d.iterdir():
        if f.is_file() and (_FRAG_RE.search(f.stem)
                            or (f.suffix in (".webp", ".png") and f.name != "cover.jpg")):
            f.unlink(missing_ok=True)


_DL_COMMON = {
    "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
    "overwrites": False, "socket_timeout": 30, "retries": 3,
    # YouTube เสิร์ฟเป็น DASH fragment ทีละก้อน — ของเดิมโหลดทีละก้อน (ค่า default 1)
    "concurrent_fragment_downloads": 8,
}

# YouTube บล็อกการโหลดจาก IP บ้านได้ ("Sign in to confirm you're not a bot" — 2026-10-05 โหลดเพลงใหม่ไม่ได้เลย)
# -> โหลดด้วยล็อกอิน YouTube ที่มีอยู่แล้วในเบราว์เซอร์เครื่องนี้ (ค้นหาเพลงไม่โดนบล็อก _search จึงไม่ใช้)
# KARA_YT_COOKIES = "chrome" (ค่าเริ่ม) / "chrome:Profile 1" / "safari" / "none" = ไม่ใช้คุกกี้ (แบบเดิม)
YT_COOKIES = os.environ.get("KARA_YT_COOKIES", "chrome").strip()
_YT_CK_TTL = 600.0                 # Chrome หมุนคุกกี้ล็อกอินเรื่อย ๆ ของที่อ่านไว้นานใช้ไม่ได้ -> อ่านใหม่ทุก 10 นาที
_YT_CK_DOMAINS = ("youtube.com", "youtube-nocookie.com", "google.com")
_YT_LOGIN = ("SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID")   # yt-dlp นับว่าล็อกอินเมื่อมีตัวใดตัวหนึ่ง
_yt_ck: dict = {"t": 0.0, "txt": None, "job": None, "t0": 0.0}  # คุกกี้อยู่ในหน่วยความจำเท่านั้น ไม่เขียนลงดิสก์
_yt_ck_lock = threading.Lock()
_BOT_RE = re.compile(r"not a bot|Sign in to confirm", re.I)
_BOT_HINT = ("YouTube ขอให้ล็อกอินก่อนโหลด — ล็อกอิน YouTube ใน Chrome ของเครื่องเซิร์ฟเวอร์"
             " (Mac ถามสิทธิ์ Keychain ให้กด Always Allow) แล้วกด 🔧 ลองใหม่")   # ขึ้นการ์ดรีโมท/Studio แทน error ดิบ
# ล็อกอินแล้ว yt-dlp ใช้ client เว็บ/ทีวี ที่ต้องแก้โจทย์ JavaScript ของ YouTube (visionos ที่ใช้ตอนไม่ล็อกอินรับคุกกี้ไม่ได้)
# -> node ในเครื่อง (หรือ deno ถ้าติดตั้ง) + สคริปต์แก้โจทย์ของ yt-dlp (ejs: โหลดจาก GitHub ของ yt-dlp ครั้งแรก ตรวจ hash แล้วแคช)
_NODE = shutil.which("node") or next((str(p) for p in (Path.home() / ".local/node/bin/node",) if p.is_file()), None)


def _yt_ck_load() -> None:
    """อ่านคุกกี้จากเบราว์เซอร์จริง (เธรดแยก) — yt-dlp ค้นโฟลเดอร์ Chrome + ขอกุญแจจาก Keychain + ถอดรหัสคุกกี้
    ทุกเว็บ (หลายวิ) แล้วเก็บไว้เฉพาะของ YouTube/Google · ครั้งแรก macOS ถามสิทธิ์ "Chrome Safe Storage"
    เธรดนี้ค้างจนกว่าจะมีคนกด (ต้องกด Always Allow ไม่งั้นถามใหม่ทุก 10 นาที)"""
    browser, _, profile = YT_COOKIES.partition(":")
    txt, keep = None, False
    try:
        from yt_dlp.cookies import YoutubeDLCookieJar
        out, login = YoutubeDLCookieJar(io.StringIO()), False
        with YoutubeDL({"quiet": True, "no_warnings": True,
                        "cookiesfrombrowser": (browser.lower(), profile or None)}) as ydl:
            for c in ydl.cookiejar:
                dom = c.domain.lstrip(".")
                if any(dom == x or dom.endswith("." + x) for x in _YT_CK_DOMAINS):
                    out.set_cookie(c)
                    login = login or (c.name in _YT_LOGIN and dom.endswith("youtube.com"))
        if login:
            out.save()
            txt = out.filename.getvalue()
            print(f"[dl] ใช้ล็อกอิน YouTube จาก {YT_COOKIES} (คุกกี้ {len(out)} ตัว)")
        else:
            print(f"[dl] ไม่เจอล็อกอิน YouTube ในคุกกี้ของ {YT_COOKIES} (ยังไม่ล็อกอิน youtube.com"
                  f" หรือไม่ได้กดอนุญาต Keychain) — โหลดแบบไม่ล็อกอิน")
    except Exception as exc:
        keep = True                      # อ่านพลาดชั่วคราว (เช่น ไฟล์ถูกล็อก) -> คุกกี้รอบก่อนยังใช้ต่อได้
        print(f"[dl] อ่านคุกกี้ {YT_COOKIES} ไม่ได้: {type(exc).__name__}: {exc}")
    with _yt_ck_lock:
        _yt_ck.update(t=time.monotonic(), txt=_yt_ck["txt"] if keep else txt, job=None)


def _yt_cookies(wait: float = 60.0) -> str | None:
    """คุกกี้ล็อกอิน YouTube แบบ Netscape (None = ไม่ใช้/อ่านไม่ได้/ไม่ได้ล็อกอิน -> โหลดแบบเดิม)
    ครบ 10 นาทีแล้วใช้ของเดิมไปก่อนระหว่างเธรดอ่านของใหม่ · ยังไม่เคยได้ -> รอรวมกันไม่เกิน wait วิ
    นับจากเริ่มอ่าน (ค้างนาน = รอคนกดอนุญาต Keychain) แล้วโหลดแบบไม่ล็อกอินไปก่อน การโหลดจะได้ไม่ค้างตาม"""
    if not _HAS_YTDLP or YT_COOKIES.lower() in ("", "none", "off", "0"):
        return None
    with _yt_ck_lock:
        now = time.monotonic()
        if _yt_ck["t"] and now - _yt_ck["t"] < _YT_CK_TTL:
            return _yt_ck["txt"]
        if _yt_ck["job"] is None:
            _yt_ck["job"] = threading.Thread(target=_yt_ck_load, name="yt-cookies", daemon=True)
            _yt_ck["t0"] = now
            _yt_ck["job"].start()
        if _yt_ck["txt"] is not None:
            return _yt_ck["txt"]
        job, left = _yt_ck["job"], wait - (now - _yt_ck["t0"])
    if left > 0:
        job.join(left)
    return _yt_ck["txt"]


def _yt_ck_reset() -> None:
    """YouTube ยังถามว่าเป็นบอท -> คุกกี้อาจหมดอายุ/ถูกหมุน/เพิ่งล็อกอิน: รอบหน้าอ่านจากเบราว์เซอร์ใหม่"""
    with _yt_ck_lock:
        _yt_ck.update(t=0.0, txt=None)


def _yt_auth() -> dict:
    """ตัวเลือก yt-dlp เพิ่มสำหรับโหลดแบบล็อกอิน ({} = แบบเดิม) — ใส่ทุกที่ที่ยิง player ของ YouTube"""
    ck = _yt_cookies()
    if not ck:
        return {}
    return {"cookiefile": io.StringIO(ck),     # สตรีมใหม่ทุกครั้ง: yt-dlp เขียนคุกกี้กลับลงไปตอนปิด
            "js_runtimes": {"deno": {}, **({"node": {"path": _NODE}} if _NODE else {})},
            "remote_components": ["ejs:github"]}


def _pick_out(d: Path, vid: str, exts: tuple[str, ...]) -> Path | None:
    """ไฟล์ที่ yt-dlp เพิ่งเขียน — เอาชื่อตรงตาม outtmpl ก่อน
    เศษ fragment ชื่อ "<vid>.f137.mp4" เรียงมาก่อน "<vid>.mp4" ('f' < 'm')
    ของเดิมใช้ sorted(glob)[0] จึงหยิบไฟล์วิดีโอล้วนที่ไม่มีเสียงมาเป็น video.mp4 ได้"""
    for ext in exts:
        exact = d / f"{vid}{ext}"
        if exact.is_file():
            return exact
    cand = [f for ext in exts for f in sorted(d.glob(f"*{ext}"))
            if not _FRAG_RE.search(f.stem)]
    return cand[0] if cand else None


def _download_audio(vid: str) -> None:
    """เสียง + metadata ก่อน — demucs ต้องใช้แค่ audio.m4a จึงเริ่มแยกเสียงได้
    ระหว่างที่วิดีโอยังโหลดอยู่ และได้สตรีม AAC ต้นฉบับตรง ๆ
    (ของเดิมรอ merge เป็น mp4 เสร็จแล้วค่อยสกัดเสียงออกมาใหม่ = เสีย ffmpeg เต็มไฟล์ 1 รอบ)"""
    if not _HAS_YTDLP:
        raise RuntimeError("yt-dlp not installed")
    if not _vid_ok(vid):
        raise RuntimeError(f"videoId ไม่ถูกต้อง: {str(vid)[:40]!r}")
    d = _song_dir(vid)
    audio = d / "audio.m4a"
    if audio.is_file():
        return
    if not _in_archive(d):
        raise RuntimeError(f"โฟลเดอร์ไม่อยู่ในคลังเพลง: {d}")
    d.mkdir(parents=True, exist_ok=True)
    _dl_scrub(d)                         # เศษจากรอบที่พังกลางทางต้องไม่ปนมารอบนี้
    try:
        with YoutubeDL({**_DL_COMMON, **_yt_auth(),
                        "outtmpl": str(d / "%(id)s.%(ext)s"),
                        "format": "ba[ext=m4a]/ba/b",
                        "writeinfojson": True,
                        "writethumbnail": True,
                        "writesubtitles": True,   # ซับจริงเท่านั้น auto-caption เชื่อไม่ได้
                        "writeautomaticsub": False,
                        # ซับภาษาของเพลง (gen_lyrics เลือกใช้ตามภาษา) — รวมรหัสประเทศ (en-US/zh-Hant) ด้วย
                        # yt-dlp จับคู่แบบ fullmatch: "en" เฉย ๆ ไม่ได้ en-US ที่ 17 เพลงในคลังมี
                        "subtitleslangs": ["th(-.*)?", "en(-.*)?", "ja(-.*)?", "ko(-.*)?"],
                        "subtitlesformat": "vtt",
                        "convert_thumbnails": "jpg"}) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])

        src = _pick_out(d, vid, (".m4a", ".mp4", ".webm", ".opus", ".mka"))
        if src is None:
            raise RuntimeError("yt-dlp ไม่ได้ไฟล์เสียงมา")
        if src.suffix == ".m4a":
            src.rename(audio)            # AAC ต้นฉบับ ไม่ต้องเข้ารหัสใหม่
        else:
            part = d / "audio.m4a.part"
            _ffmpeg(["-i", str(src), "-vn", "-c:a", "aac", "-b:a", "192k",
                     "-movflags", "+faststart", "-f", "ipod", str(part)])
            part.rename(audio)           # atomic: ครึ่ง ๆ ต้องไม่ถูกนับว่าเสร็จ
            src.unlink(missing_ok=True)
        _tidy_sidecars(d)
    finally:
        _dl_scrub(d)


def _has_audio_stream(f: Path) -> bool:
    if not FFPROBE:
        return True                      # ตรวจไม่ได้ก็อย่าไปขวางทาง
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a",
                            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(f)],
                           capture_output=True, text=True, timeout=30)
        return "audio" in (r.stdout or "")
    except Exception:
        return True


def _download_video(vid: str) -> None:
    """วิดีโอ — โหลดเฉพาะภาพแล้ว mux กับ audio.m4a ที่มีอยู่แล้วด้วย -c copy
    ห้ามได้ไฟล์ที่ไม่มีเสียงเด็ดขาด: ตอนสเต็มยังไม่พร้อม จอเล่นเสียงจาก video.mp4
    (static/player.html:507 + 540) เพลงจะเงียบสนิททั้งเพลง"""
    if not _HAS_YTDLP:
        raise RuntimeError("yt-dlp not installed")
    if not _vid_ok(vid):
        raise RuntimeError(f"videoId ไม่ถูกต้อง: {str(vid)[:40]!r}")
    d = _song_dir(vid)
    video = d / "video.mp4"
    if video.is_file():
        return
    audio = d / "audio.m4a"
    if not _in_archive(d):
        raise RuntimeError(f"โฟลเดอร์ไม่อยู่ในคลังเพลง: {d}")
    d.mkdir(parents=True, exist_ok=True)
    try:
        # มี audio.m4a แล้วก็ขอแค่ภาพ ไม่ต้องโหลดเสียงซ้ำ
        # ขอ H.264 (avc1) ก่อน — ไม่ระบุ yt-dlp จะเลือก AV1 ซึ่ง iPad/ทีวีส่วนใหญ่เล่นไม่ได้
        fmt = ("bv*[vcodec^=avc1][height<=720]/bv*[ext=mp4][height<=720]/bv*[height<=720]/b[ext=mp4]/b"
               if audio.is_file()
               else "bv*[vcodec^=avc1][height<=720]+ba[ext=m4a]/bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4]/b")
        with YoutubeDL({**_DL_COMMON, **_yt_auth(),
                        "outtmpl": str(d / "%(id)s.v.%(ext)s"),
                        "format": fmt,
                        "merge_output_format": "mp4"}) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])

        src = _pick_out(d, f"{vid}.v", (".mp4", ".webm", ".mkv"))
        if src is None:
            raise RuntimeError("yt-dlp ไม่ได้ไฟล์วิดีโอมา")
        part = video.with_suffix(".mp4.part")
        if audio.is_file() and not _has_audio_stream(src):
            # ภาพล้วน + เสียงที่โหลดไว้แล้ว -> รวมร่างแบบ copy ไม่เข้ารหัสใหม่
            _ffmpeg(["-i", str(src), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                     "-c", "copy", "-shortest", "-movflags", "+faststart",
                     "-f", "mp4", str(part)])
        elif src.suffix == ".mp4":
            src.rename(part)
        else:
            _ffmpeg(["-i", str(src), "-c", "copy", "-movflags", "+faststart",
                     "-f", "mp4", str(part)])
        if not _has_audio_stream(part):
            part.unlink(missing_ok=True)
            raise RuntimeError("วิดีโอที่ได้ไม่มีแทร็กเสียง")
        part.rename(video)               # atomic: ถือว่าเล่นได้ต่อเมื่อครบจริง
        src.unlink(missing_ok=True)
        _tidy_sidecars(d)
        _fetch_auto_caption(d, vid)      # ต้องหลัง tidy — tidy rename ทุก *.vtt (ปกติดึงไปแล้วหลังโหลดเสียง = รอบสำรอง)
    finally:
        for f in d.glob("*.mp4.part"):
            f.unlink(missing_ok=True)
        _dl_scrub(d)


def _tidy_sidecars(d: Path) -> None:
    """จัดชื่อ cover.jpg / info.json / sub.<lang>.vtt ให้เป็นระเบียบ"""
    img = next((f for f in sorted(d.glob("*.jpg")) + sorted(d.glob("*.webp"))
                + sorted(d.glob("*.png"))), None)
    if img and img.name != "cover.jpg":
        cover = d / "cover.jpg"
        if img.suffix.lower() == ".jpg":
            img.rename(cover)
        else:
            _ffmpeg(["-i", str(img), str(cover)])
    for f in d.glob("*.info.json"):
        if f.name != "info.json":
            f.rename(d / "info.json")
    for f in d.glob("*.vtt"):
        # จัดชื่อเฉพาะไฟล์ใหม่ของ yt-dlp (<vid>.<lang>.vtt) — ชื่อที่จัดแล้ว (sub./auto.) กับไฟล์พักของ
        # _fetch_auto_caption/_fetch_subs (_auto./_sub.) ห้ามแตะ: ของเดิม rename ทุกไฟล์ ทำให้ตอนโหลดใหม่
        # auto.th.vtt (เครื่องถอด) กลายเป็น sub.th.vtt ที่ gen_lyrics เชื่อว่าเป็น "ซับที่คนทำ" และทับซับจริงได้
        if _VTT_NAME.match(f.name) or f.name.startswith(("_auto.", "_sub.")):
            continue
        parts = f.name.split(".")
        lang = (LS.norm_lang(parts[-2]) if len(parts) >= 3 else "") or "th"
        f.replace(d / f"sub.{lang}.vtt")


def _fetch_auto_caption(d: Path, vid: str) -> None:
    """auto-caption (ASR ของ YouTube) -> auto.th.vtt

    แยกไฟล์จาก sub.th.vtt เด็ดขาด เพราะคนละชั้นคุณภาพ: sub.th.vtt คนพิมพ์ เชื่อได้ทั้ง
    เนื้อและเวลา ตัวนี้เครื่องถอด เวลาแม่นแต่ตัวหนังสืออาจสะกดผิด ต้องอยู่หลัง lrclib
    ในลำดับเลือกแหล่ง และขึ้นป้ายความมั่นใจคนละระดับ

    ยิงแยกรอบจากการโหลดหลัก เพราะตอนตั้ง opts ยังไม่มี info.json จึงยังไม่รู้ว่าคีย์ไหน
    เป็น ASR ต้นฉบับจริง (ดู LS.asr_caption_track — ชื่อคีย์เชื่อไม่ได้)
    ต้องเรียก *หลัง* _tidy_sidecars เสมอ เพราะ _tidy_sidecars rename ทุก *.vtt เป็น
    sub.<lang>.vtt ซึ่งจะทับซับจริงถ้าไฟล์ของเราค้างอยู่ตอนนั้น"""
    try:
        info = json.loads((d / "info.json").read_text("utf-8"))
    except Exception:
        return
    key, alang = LS.asr_track(info)          # ภาษาที่ YouTube ได้ยินจริง (ไม่ใช่แค่ไทย)
    if not key or not alang:
        return                               # ~29/70 เพลงจบตรงนี้ ไม่ยิงเน็ตเลย
    if (d / f"auto.{alang}.vtt").is_file():
        return
    try:
        with YoutubeDL({**_DL_COMMON, **_yt_auth(), "skip_download": True,
                        "writesubtitles": False,        # ห้ามปนซับจริง
                        "writeautomaticsub": True,
                        "subtitleslangs": [key], "subtitlesformat": "vtt",
                        "outtmpl": str(d / "_auto")}) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
        got = next(iter(sorted(d.glob("_auto.*.vtt"))), None)
        if got:
            got.replace(d / f"auto.{alang}.vtt")
    except Exception as exc:
        print(f"[dl] {vid} auto-caption ไม่ได้: {type(exc).__name__}: {exc}")
    finally:
        for f in d.glob("_auto.*"):
            f.unlink(missing_ok=True)


def _fetch_subs(d: Path, vid: str, lang: str) -> bool:
    """ดึงซับจริงภาษาที่ระบุให้เพลงที่โหลดไว้แล้ว (ตอนโหลดครั้งแรกขอแค่ th/en) -> sub.<lang>.vtt"""
    if not lang or (d / f"sub.{lang}.vtt").is_file():
        return False
    try:
        with YoutubeDL({**_DL_COMMON, **_yt_auth(), "skip_download": True, "writesubtitles": True,
                        "writeautomaticsub": False, "subtitleslangs": [f"{lang}(-.*)?"], "subtitlesformat": "vtt",
                        "outtmpl": str(d / "_sub")}) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
        got = next(iter(sorted(d.glob("_sub.*.vtt"))), None)
        if got:
            got.replace(d / f"sub.{lang}.vtt")
            return True
    except Exception as exc:
        print(f"[dl] {vid} ซับ {lang} ไม่ได้: {type(exc).__name__}: {exc}")
    finally:
        for f in d.glob("_sub.*"):
            f.unlink(missing_ok=True)
    return False


def _download_one(vid: str) -> None:
    """โหลดครบทั้งเพลง — ใช้ตอนต้องการไฟล์ทั้งชุดในครั้งเดียว"""
    _download_audio(vid)
    _download_video(vid)


_DL_TRIES = 2                      # โหลดพังเพราะเน็ตสะดุดเป็นเรื่องปกติ ลองซ้ำเองก่อนยอมแพ้
_DL_AUTO_MAX = 3                   # ลองใหม่อัตโนมัติได้กี่รอบ ก่อนรอให้คนกดปุ่มซ่อมเอง
_dl_fails: dict[str, int] = {}     # videoId -> โหลดพังมาแล้วกี่รอบ (ล้างเมื่อสำเร็จ/กดซ่อม)


_h264_lock = threading.Lock()      # แปลงทีละเพลง (ถอด AV1 กิน CPU ~2 คอร์)
_h264_busy: set[str] = set()


def _h264_bg(vid: str) -> None:
    """video.mp4 ที่เป็น AV1 -> H.264 เบื้องหลัง (scripts/to_h264.py ข้ามเองถ้าไม่ใช่ AV1)
    ข้ามเพลงที่กำลังเล่น: แทนที่ไฟล์กลางเพลง จอที่โหลดเป็นช่วงๆ จะได้ไบต์ของไฟล์ใหม่ปนมา"""
    if vid in _h264_busy or (room.current or {}).get("videoId") == vid:
        return
    f = _song_dir(vid) / "video.mp4"
    if not f.is_file():
        return
    _h264_busy.add(vid)

    def run():
        try:
            with _h264_lock:
                if (room.current or {}).get("videoId") == vid:
                    return
                r = subprocess.run([sys.executable, str(BASE / "scripts" / "to_h264.py"), str(f)],
                                   capture_output=True, text=True, timeout=1900,
                                   env={**os.environ, "KARA_PORT": str(PORT)})
                res = (r.stdout or "").strip() or (r.stderr or "").strip()[-200:]
                if res != "skip":
                    print(f"[h264] {vid} {res}")
        except Exception as exc:
            print(f"[h264] {vid} {type(exc).__name__}: {exc}")
        finally:
            _h264_busy.discard(vid)
    threading.Thread(target=run, daemon=True).start()


async def _download_worker() -> None:
    while True:
        await _dl_pending.wait()
        vid = _dl_pending.take_now()       # เลือกตามลำดับคิวห้องตอนนี้ ไม่ใช่ลำดับที่กดเพิ่ม
        if vid is None:
            continue
        if not _vid_ok(vid):
            _dl_state.pop(vid, None)
            continue
        d = _song_dir(vid)
        if (d / "video.mp4").is_file() and (d / "audio.m4a").is_file():
            _dl_state.pop(vid, None)
            _h264_bg(vid)               # เพลงเก่าที่ยังเป็น AV1 -> แปลงก่อนถึงคิว (iPad เล่นได้)
            await _enqueue_sep(vid)     # ไฟล์ครบแล้ว แต่ยังอาจไม่เคยแยกเสียง
            await room.broadcast()
            continue
        _dl_state[vid] = {"status": "downloading", "error": ""}
        await room.broadcast()
        t0 = time.monotonic()
        for attempt in range(1, _DL_TRIES + 1):
            try:
                # เสียงก่อน แล้วสั่งแยกเสียงทันที — demucs (2-3 นาที) จะได้เดินขนาน
                # กับการโหลดวิดีโอ แทนที่จะต่อคิวกันแบบเดิม
                await asyncio.to_thread(_download_audio, vid)
                _invalidate_dirs()
                await _enqueue_sep(vid)
                # ได้ info.json + ซับจริงแล้ว -> ดึงคำบรรยายอัตโนมัติแล้วเริ่มหาเนื้อเลย ไม่ต้องรอวิดีโอ
                # (เดิมหาเนื้อได้หลังวิดีโอเสร็จ + รอ watchdog อีกรอบ สูงสุด 10 วิ และถ้า watchdog มาก่อน
                # คำบรรยายอัตโนมัติ เพลงที่มีแค่แหล่งนั้นจะถูกส่งไปทางถอดเสียงที่ต้องรอ GPU)
                try:
                    await asyncio.to_thread(_fetch_auto_caption, _song_dir(vid), vid)
                except Exception as exc:
                    print(f"[dl] {vid} auto-caption: {type(exc).__name__}: {exc}")
                _lyr_nosrc.discard(vid)
                await _enqueue_lyr(vid)
                await room.broadcast()
                await asyncio.to_thread(_download_video, vid)
                print(f"[dl] {vid} OK {time.monotonic() - t0:.0f}s{_since_add(vid)}")
                _h264_bg(vid)           # YouTube ไม่มี H.264 ให้ = ได้ AV1 มา -> แปลงเอง
                # ซับ/metadata เพิ่งมาถึง — ถ้าเคยค้นเนื้อไปแล้วตอนโฟลเดอร์ยังว่าง
                # ผลนั้นใช้ไม่ได้ ต้องให้ลองแหล่งที่ไม่ใช้ GPU ใหม่ก่อนจะไปถอดเสียง
                _lyr_nosrc.discard(vid)
                _dl_state.pop(vid, None)   # ไฟล์อยู่บนดิสก์แล้ว _dl_fields อ่านเองได้
                _invalidate_dirs()         # โฟลเดอร์เพิ่งเกิด อย่าให้แคช 2 วิบังไว้
                room.archive_rev += 1
                _dl_fails.pop(vid, None)
                if _fix_history_titles(vid):      # ประวัติที่เคยเก็บ "YouTube: <id>" -> ชื่อจริง
                    await asyncio.to_thread(_save_history)
                _prefetch_best(vid)               # วิดีโอมาแล้ว (OCR ใช้) -> ดึงแหล่งให้งานเลือกเนื้อไว้ก่อน
                break
            except Exception as exc:
                bot = bool(_BOT_RE.search(str(exc)))
                if bot:
                    _yt_ck_reset()
                if attempt < _DL_TRIES:
                    print(f"[dl] {vid} ลองใหม่ ({attempt}/{_DL_TRIES}): {exc}")
                    await asyncio.sleep(2)
                    continue
                _dl_fails[vid] = _dl_fails.get(vid, 0) + 1
                _dl_state[vid] = {"status": "failed",
                                  "error": _BOT_HINT if bot else f"{type(exc).__name__}: {exc}"}
                print(f"[dl] {vid} FAILED ({_dl_fails[vid]}/{_DL_AUTO_MAX}): {exc}")
        await room.broadcast()


async def _ensure_downloader() -> None:
    global _dl_task
    if _dl_task is None or _dl_task.done():
        _dl_task = asyncio.create_task(_download_worker())


# --- แยกเสียงร้อง (Demucs) ------------------------------------------
# โมเดลเก็บในโปรเจกต์ ไม่ปนกับ ~/.cache และต้องตั้งก่อน spawn demucs
os.environ.setdefault("TORCH_HOME", str(BASE / ".cache" / "torch"))
# HF_HOME/HF_HUB_CACHE ตั้งไว้ต้นไฟล์แล้ว (demucs 4.1 ดึง HTDemucs จาก huggingface — มีใน .cache/hf แล้ว)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

DEMUCS_MODEL = "htdemucs"
_sep_task: asyncio.Task | None = None
_sep_state: dict[str, dict] = {}                   # videoId -> {"status","error"}
_sep_device: str | None = None                     # จำ device ที่ใช้ได้ไว้ ไม่ต้องลองใหม่ทุกเพลง
_NEVER = 1 << 30                                   # อันดับ "ไม่มีใครรออยู่"
_VERIFY_RANK = _BACKLOG << 1                       # ตรวจเนื้อยอมให้ทุกอย่างแซงเสมอ


class _HeavyGate:
    """สิทธิ์ใช้ GPU — ให้คนที่รอ "เพลงอันดับดีที่สุดในห้องตอนนี้" ได้ก่อน

    ของเดิมเป็น asyncio.Lock ธรรมดาซึ่งปลุก waiter ตามลำดับที่มาขอ (FIFO) ผลคือ
    demucs ของเพลงท้ายคิว หรืองานตรวจเนื้อเพลงเก่า ตัดหน้าเพลงที่กำลังเล่นได้
    = เพลงขึ้นจอแล้วยังไม่มีไกด์เสียงร้อง/ไม่มีเนื้อ ซึ่งคืออาการที่ผู้ใช้เจอ

    อันดับของแต่ละคนเปลี่ยนได้ตลอด (คิวห้องขยับ) จึงเก็บเป็นฟังก์ชันแล้วเรียกสดทุกครั้ง
    ที่ประเมิน และต้องมี rethink() ให้คนอื่นปลุกตอนคิวเปลี่ยน ไม่งั้นไม่มีเหตุให้ตื่น"""

    def __init__(self) -> None:
        self._busy = False
        self._cv = asyncio.Condition()
        self._want: dict[str, Any] = {}        # ชื่อ worker -> ฟังก์ชันคืนอันดับที่รออยู่

    @property
    def busy(self) -> bool:
        return self._busy

    def _best_other(self, name: str) -> int:
        return min((f() for n, f in self._want.items() if n != name), default=_NEVER)

    @asynccontextmanager
    async def slot(self, name: str, rank):
        async with self._cv:
            self._want[name] = rank
            try:
                await self._cv.wait_for(
                    lambda: not self._busy and rank() <= self._best_other(name))
            finally:
                self._want.pop(name, None)
            self._busy = True
        try:
            yield
        finally:
            async with self._cv:
                self._busy = False
                self._cv.notify_all()

    async def rethink(self) -> None:
        """ลำดับห้องเปลี่ยน -> ให้ทุกคนที่รออยู่ประเมินอันดับกันใหม่"""
        async with self._cv:
            self._cv.notify_all()


_heavy = _HeavyGate()                              # demucs/whisper/ตรวจเนื้อ แย่ง GPU กัน ให้ทีละงาน
SEP_TIMEOUT = 30 * 60        # ต่อ device — cpu เพลงยาวยังจบทัน / ค้างเกินนี้ = ค้างจริง
SEP_MAX_SEC = 10 * 60        # คลิปยาวกว่านี้ (เมดเลย์/ไลฟ์) ไม่แยกเสียง ไม่ถอดเสียง — 40 นาทีบน cpu = 25 นาทีเครื่องร้อน
_SEP_LONG_ERR = "คลิปยาวเกิน 10 นาที — ไม่แยกเสียง"
_LYR_LONG_ERR = "คลิปยาวเกิน 10 นาที — ไม่ถอดเสียง"
LYR_TIMEOUT = 30 * 60        # gen_lyrics เต็ม (ถอดเสียง + ตรวจภาษา + ลองซ้ำเมื่อ whisper วนลูป)
FIND_TIMEOUT = 10 * 60       # gen_lyrics --no-asr (เน็ตล้วน)
LANG_TIMEOUT = 5 * 60        # whisper ฟัง 2 ช่วง ๆ ละ 30 วิ
FFMPEG_TIMEOUT = 10 * 60

# --- แย่งคิวงานหนัก ---------------------------------------------------
# demucs/whisper กินเวลาเป็นนาที ถ้าไม่ฆ่าทิ้ง เพลงที่เพิ่งถูกเลื่อนขึ้นมาเล่นต้องรอจนจบ
# = ขึ้นจอโดยไม่มีไกด์เสียงร้อง ซึ่งคืออาการที่ผู้ใช้เจอ
_heavy_job: tuple[str, str] | None = None          # (ชนิดงาน, videoId) ที่ถือ _heavy อยู่ตอนนี้
_preempt_kill: set[str] = set()                    # videoId ที่เพิ่งถูกสั่งฆ่า (ธงให้ฝั่ง thread อ่าน)
_sep_gone: set[str] = set()                        # videoId ที่ถูกลบจาก Studio ระหว่างแยกเสียง (ห้ามตกไป cpu)
_preempt_at = 0.0                                  # กันฆ่ารัว ตอนคนกดเลื่อนคิวหลายทีติด
_preempt_n: dict[str, int] = {}                    # เพลงนี้ถูกแย่งไปกี่ครั้งแล้ว (กันอดตาย)
_PREEMPT_COOLDOWN = 20.0
_PREEMPT_MAX = 2


class _Preempted(Exception):
    """งานถูกฆ่าเพราะมีเพลงที่ต้องใช้ก่อน — ไม่ใช่ความล้มเหลว ให้เข้าคิวใหม่"""


# --- โปรเซสลูกทั้งหมด (demucs / gen_lyrics / fa_align / ตรวจภาษา) ------------------
# ลงทะเบียนไว้ที่เดียว: แย่งคิวหาตัวที่จะฆ่าเจอ / ปิดเซิร์ฟเวอร์ฆ่าได้ครบ / ทุกตัวมีเพดานเวลา
# ของเดิมไม่มี timeout — demucs ค้างบน MPS ครั้งเดียว = ถือช่อง GPU ไว้ตลอด งานหนักทุกอย่างหยุดหมด
_children: dict[int, tuple[str, str, subprocess.Popen]] = {}   # pid -> (ชนิดงาน, videoId, proc)
_children_lock = threading.Lock()


def _run_child(kind: str, vid: str, cmd: list[str], timeout: float, input: str | None = None,
               **kw) -> tuple[int, str, str]:
    """รันโปรเซสลูกจนจบ -> (returncode, stdout, stderr) / หมดเวลา = ฆ่าแล้ว raise RuntimeError"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.PIPE if input is not None else None, text=True, **kw)
    with _children_lock:
        _children[proc.pid] = (kind, vid, proc)
    try:
        try:
            out, err = proc.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=10)   # หลานที่ถือ pipe ไว้ (ffmpeg ของ demucs) ต้องไม่ทำให้ค้างซ้ำ
            except subprocess.TimeoutExpired:
                pass
            raise RuntimeError(f"{kind} หมดเวลา ({timeout / 60:.0f} นาที)")
    finally:
        with _children_lock:
            _children.pop(proc.pid, None)
    return proc.returncode, out or "", err or ""


def _child_of(kind: str, vid: str) -> subprocess.Popen | None:
    with _children_lock:
        return next((p for k, v, p in _children.values() if k == kind and v == vid), None)


def _kill_children() -> None:
    """ปิดเซิร์ฟเวอร์: ฆ่าลูกทุกตัว — ไม่งั้น thread ที่รอ communicate() ถ่วงการปิดไปหลายนาที และลูกค้างกิน GPU ต่อ"""
    with _children_lock:
        procs = [p for _, _, p in _children.values()]
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass


def _preempt_heavy() -> None:
    """มีเพลงที่กำลังเล่น/เพลงถัดไปรออยู่ แต่ GPU ติดงานของเพลงท้ายคิว -> ฆ่าแล้วเริ่มใหม่
    เงื่อนไขแคบไว้ตั้งใจ: เริ่ม demucs/whisper ใหม่ = ทิ้งงานที่ทำมาทั้งหมด ห้ามฆ่าพร่ำเพรื่อ
    ไม่มี await ในฟังก์ชันนี้ จึงเรียกตอนถือ room.lock ได้"""
    global _preempt_at
    job = _heavy_job
    if not job or time.monotonic() - _preempt_at < _PREEMPT_COOLDOWN:
        return
    kind, vid = job
    m = _prio_map()
    best = min((b[1] for b in (_sep_pending.best(m), _lyr_pending.best(m)) if b), default=_BACKLOG)
    if best > _PREEMPT_RANK:
        return                                  # ไม่มีเพลงด่วนรออยู่ ปล่อยงานเดิมทำต่อ
    if kind not in ("sep", "lyr", "verify"):
        return                                  # งาน FA สั้น ๆ (words/best/fa/lang) ปล่อยให้จบเอง
    run = _BACKLOG if kind == "verify" else _prio(vid, m)   # ตรวจเนื้อเพลงยอมให้แย่งเสมอ
    if run <= best or _preempt_n.get(vid, 0) >= _PREEMPT_MAX:
        return
    proc = _child_of(kind, vid)
    if proc is None or proc.poll() is not None:
        return                                  # อยู่ช่วง ffmpeg/เขียนไฟล์ ฆ่าไปก็ไม่ได้อะไร
    _preempt_kill.add(vid)
    _preempt_n[vid] = _preempt_n.get(vid, 0) + 1
    _preempt_at = time.monotonic()
    print(f"[{kind}] แย่งคิว: หยุด {vid} (อันดับ {run}) ให้เพลงอันดับ {best} ก่อน")
    try:
        proc.kill()
    except Exception:
        pass


def _stem_paths(vid: str) -> tuple[Path, Path]:
    d = _song_dir(vid)
    return d / "vocals.m4a", d / "no_vocals.m4a"


def _has_stems(vid: str) -> bool:
    v, n = _stem_paths(vid)
    return v.is_file() and n.is_file()


_lyr_cache: dict[str, tuple[float, int, bool, str]] = {}
# ที่มาที่ให้เวลามาด้วย (ดูที่ scripts/gen_lyrics.py) -> เชื่อเวลาได้ ไม่ต้องขึ้นคำเตือน
_TRUSTED_LYR_TIME = frozenset({"manual-lrc", "manual-edit", "yt-sub", "lrclib", "yt-auto"})
# ต้องตรงกับ gen_lyrics.TRUSTED_TIME เสมอ (เวลามาจากแหล่งตรง ๆ ไม่ได้เดาเอง)
_chk_cache: dict[str, tuple[float, str]] = {}


def _chk_info(vid: str) -> dict:
    """ผลตรวจล่าสุดทั้งก้อน — {} = ยังไม่เคยตรวจ (แคชด้วย mtime)"""
    f = _song_dir(vid) / "lyrics.check.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return {}
    hit = _chk_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        j = json.loads(f.read_text("utf-8"))
    except Exception:
        j = {}
    _chk_cache[vid] = (mt, j)
    return j


def _chk_verdict(vid: str) -> str:
    """ผลตรวจล่าสุด — reported | ok | fixed | bad | unknown | unmeasurable (ว่าง = ยังไม่ตรวจ)"""
    return _chk_info(vid).get("verdict") or ""


_lyr_from: dict[str, dict | None] = {}     # videoId -> {"kind": picked|best, "label"} อัปเดตพร้อม _lyr_cache
_lyr_cov: dict[str, float | None] = {}     # videoId -> % ของคลิปที่มีบรรทัดขึ้น (Σd) อัปเดตพร้อม _lyr_cache


def _lyr_meta(vid: str) -> tuple[float, int, bool, str, str]:
    """(mtime, บรรทัด, เวลาน่าสงสัยไหม, ใครพิมพ์เนื้อ, ใครจับเวลา)
    แคชด้วย mtime เพราะถูกเรียกทุก item ทุก broadcast"""
    f = _song_dir(vid) / "lyrics.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return (0.0, 0, False, "", "")
    hit = _lyr_cache.get(vid)
    if hit and hit[0] == mt:
        return hit
    try:
        j = json.loads(f.read_text("utf-8"))
        L = j.get("lines") or []
        n = len(L)
        src = j.get("src") or ""
        if src in _TRUSTED_LYR_TIME:
            warn = False              # เวลามาจากแหล่งโดยตรง ไม่ได้เดาเอง
        else:
            # เวลาเพี้ยนสังเกตได้จาก 2 อาการ: บรรทัดทับกันเอง กับเนื้อคลุมเพลงน้อยผิดปกติ
            over = sum(1 for a, b in zip(L, L[1:]) if b["t"] < a["t"] + a["d"] - 0.2)
            song = j.get("duration") or 0
            cov = (sum(x["d"] for x in L) / song) if song else 1.0
            warn = bool(n and (over > n * 0.1 or cov < 0.45))
        tsrc = LC.time_src_of(j)
    except Exception:
        n, warn, src, tsrc = 0, False, "", ""
    _lyr_cache[vid] = (mt, n, warn, src, tsrc)
    try:
        frm = ({"kind": "picked", "label": j["picked"]} if j.get("picked")
               else {"kind": "best", "label": (j.get("best") or {}).get("label") or ""} if j.get("best") else None)
    except Exception:
        frm = None
    _lyr_from[vid] = frm
    try:                                       # ทุกแหล่ง (เดิมคิดเฉพาะแหล่งที่เวลาไม่น่าเชื่อ) — ไว้ดูว่าเนื้อมีแค่บางช่วงไหม
        _lyr_cov[vid] = LS.span_pct(L, float(j.get("duration") or 0) or float(_song_meta(vid)["duration"] or 0)) if n else None
    except Exception:
        _lyr_cov[vid] = None
    return _lyr_cache[vid]


def _lyr_sparse(vid: str) -> str:
    """เนื้อปัจจุบันมีแค่บางช่วงของเพลงไหม (ซับบทพูดในเอ็มวี) -> เหตุผลสั้น / "" = ครบ หรือไม่รู้
    วัดจากผลตรวจล่าสุดก่อน (เสียงร้องจริงที่มีบรรทัดคลุม — แม่นกว่า) ผลตรวจเก่า/ก่อนแก้เนื้อ ใช้สัดส่วนเวลาคลิป
    เนื้อที่คนใส่เองไม่นับ (ตั้งใจใส่แค่นั้นเอง) — ใช้ทั้งป้าย 🕳, จุดเริ่ม/จบอัตโนมัติ และงานเลือกเนื้อ"""
    mt, n, _, src, _ = _lyr_meta(vid)
    if not n or src in LC.MANUAL:
        return ""
    ck = _chk_info(vid)
    cv = ck.get("cover")
    if cv is not None and float(ck.get("at") or 0) >= mt - 1:
        return f"คลุมที่ร้อง {cv:.0f}%" if cv < LC.SPARSE_COVER else ""
    sp = _lyr_cov.get(vid)
    return f"คลุมแค่ {sp:.0f}% ของคลิป" if sp is not None and sp < LS.SPARSE_SPAN else ""


def _va_for(vid: str) -> dict | None:
    """แผนที่เสียงร้อง (scripts/vocal_activity.py แคชใน _va) — เฉพาะ vocals.m4a: เสียงเต็มเพลงมีดนตรีทั้งเพลง วัดไม่ได้
    ครั้งแรกของเพลงใช้ ffmpeg + CPU 2-4 วิ -> ห้ามเรียกบน event loop (asyncio.to_thread)"""
    a = _song_dir(vid) / "vocals.m4a"
    if not a.is_file():
        return None
    try:
        import vocal_activity as VA
        return VA.load(vid, a)
    except Exception as exc:
        print(f"[va] {vid} {type(exc).__name__}: {exc}")
        return None


def _cover_of(vid: str, lines: list[dict], off: float, va: dict | None = None) -> float | None:
    """% ของเสียงร้องที่เนื้อชุดนี้คลุม (เวลาเนื้อ + offset = เวลาในเสียง) — ไม่มี vocals = None"""
    va = va if va is not None else _va_for(vid)
    if not va or not lines:
        return None
    import vocal_activity as VA
    return VA.cover(va, [(float(l["t"]) + off, float(l["t"]) + off + float(l.get("d") or 0)) for l in lines
                         if isinstance(l.get("t"), (int, float))])


# offset ประจำเพลง: บวกเข้ากับ t ตอนแสดง (บวก = ซับขึ้นช้าลง) ทิศเดียวกับ ?lyroffset= ของจอหลัก
# แยกไฟล์จาก lyrics.json เพราะปรับสดจากรีโมทได้ระหว่างร้อง โดยไม่ต้องให้จอโหลดเนื้อใหม่
# และไม่ต้องสร้างเนื้อเวอร์ชันใหม่ทุกครั้งที่กด ± — เวลาเนื้อถูกสร้างใหม่ ไฟล์นี้ถูกลบตาม
LYR_OFFSET_MAX = 15.0
_off_cache: dict[str, tuple[float, float]] = {}


def _lyr_offset(vid: str) -> float:
    f = _song_dir(vid) / "lyrics.offset.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return 0.0
    hit = _off_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        off = float(json.loads(f.read_text("utf-8")).get("offset") or 0.0)
        off = max(-LYR_OFFSET_MAX, min(LYR_OFFSET_MAX, off))
    except Exception:
        off = 0.0
    _off_cache[vid] = (mt, off)
    return off


def _set_lyr_offset(vid: str, off: float) -> float:
    off = round(max(-LYR_OFFSET_MAX, min(LYR_OFFSET_MAX, float(off))), 2)
    f = _song_dir(vid) / "lyrics.offset.json"
    if abs(off) < 0.005:
        f.unlink(missing_ok=True)
    else:
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"offset": off, "at": int(time.time())}), encoding="utf-8")
        os.replace(tmp, f)
    _off_cache.pop(vid, None)
    return off


# ===== ✂️ จุดเริ่ม/จบ + เฟดรายเพลง (โหมด Custom / คอมโบ) =====
# trim.json = {start, end, fadeIn, fadeOut} เป็น "เวลาในเสียง" (ไม่ใช่เวลาเนื้อ) ตั้งในแท็บ ✂️ ของ Studio
# แยกจากไฟล์เนื้อโดยตั้งใจ: สร้าง/ล้างเนื้อใหม่แล้วไม่หาย และไม่แตะเนื้อที่ผู้ใช้แก้เอง
# คอมโบเก็บค่าของตัวเองในใบคิว (clipStart/clipEnd/clipFadeIn/clipFadeOut) — ตัดด้วยมือล้วน ไม่ใช้ค่าอัตโนมัติ
CLIP_KEYS = ("start", "end", "fadeIn", "fadeOut")
FADE_MAX = 10.0
SPAN_MIN = 15.0          # ช่วงเล่นสั้นกว่านี้ = ทิ้งจุดจบ (ตั้งผิด/เนื้อเพี้ยน) เล่นต่อจนจบคลิป
AUTO_SKIP_MIN = 5.0      # อัตโนมัติ: ข้ามได้ไม่ถึงนี้ = เริ่มจาก 0 ไม่คุ้มกระโดด
_trim_cache: dict[str, tuple[float, dict]] = {}
_span_cache: dict[str, tuple[float, tuple[float, float] | None]] = {}


def _clean_clip(raw: Any, dur: float) -> dict:
    """{start, end, fadeIn, fadeOut} จากภายนอก -> เฉพาะตัวเลขจริงในช่วง (ค่าอื่น/None = ไม่ตั้ง)"""
    out: dict[str, float] = {}
    if not isinstance(raw, dict):
        return out
    for k in CLIP_KEYS:
        v = raw.get(k)
        if v is None or isinstance(v, bool):
            continue
        x = _finite(v, 0.0, FADE_MAX if k.startswith("fade") else dur)
        if x is not None:
            out[k] = round(x, 2)
    if "start" in out and "end" in out and out["end"] <= out["start"]:
        del out["end"]
    return out


def _dur_of(vid: str) -> float:
    try:
        return float(_song_meta(vid)["duration"] or 0) or 86400.0
    except Exception:
        return 86400.0


def _trim(vid: str) -> dict:
    f = _song_dir(vid) / "trim.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return {}
    hit = _trim_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        t = _clean_clip(json.loads(f.read_text("utf-8")), 86400.0)
    except Exception:
        t = {}
    _trim_cache[vid] = (mt, t)
    return t


def _set_trim(vid: str, raw: Any) -> dict:
    t = _clean_clip(raw, _dur_of(vid))
    f = _song_dir(vid) / "trim.json"
    if t:
        _write_json_atomic(f, {**t, "at": int(time.time())})
    else:
        f.unlink(missing_ok=True)
    _trim_cache.pop(vid, None)
    return t


def _lyr_span(vid: str) -> tuple[float, float] | None:
    """(เวลาเริ่มบรรทัดแรก, เวลาจบบรรทัดสุดท้าย) เป็นเวลาเนื้อ — แคชด้วย mtime ของ lyrics.json"""
    f = _song_dir(vid) / "lyrics.json"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return None
    hit = _span_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1]
    sp = None
    try:
        L = [l for l in (json.loads(f.read_text("utf-8")).get("lines") or [])
             if isinstance(l.get("t"), (int, float)) and str(l.get("x") or "").strip()]
        if L:
            sp = (min(float(l["t"]) for l in L),
                  max(float(l["t"]) + float(l.get("d") or 0) for l in L))
    except Exception:
        sp = None
    _span_cache[vid] = (mt, sp)
    return sp


def _auto_span(vid: str, tv: dict) -> tuple[float, float | None]:
    """จุดเริ่ม/จบอัตโนมัติจากเวลาเนื้อ (เวลาเนื้อ + offset ประจำเพลง = เวลาในเสียง) — ไม่มีเนื้อ = ทั้งคลิป
    เนื้อแค่บางช่วง = ทั้งคลิปเหมือนกัน: บรรทัดแรก/สุดท้ายเป็นบทพูด ไม่ใช่ต้น/ท้ายเพลง (เคยตัดเพลงทิ้ง 100 วิสุดท้าย)"""
    sp = _lyr_span(vid)
    if not sp or _lyr_sparse(vid):
        return 0.0, None
    off = _lyr_offset(vid)
    s = sp[0] + off - tv.get("customLead", 4)
    if s < AUTO_SKIP_MIN:
        s = 0.0
    e: float | None = sp[1] + off + tv.get("customTail", 5)
    if e >= _dur_of(vid) - 1:
        e = None
    return round(s, 2), (round(e, 2) if e is not None else None)


def _intro_end(item: dict, tv: dict) -> float:
    """จุดที่ ⏩ ข้ามอินโทรกระโดดไป: จุดเริ่มที่ตั้งเอง > อัตโนมัติ (ใบคิวจากคอมโบ/ไม่ใช่ YouTube = 0)"""
    vid = item.get("videoId")
    if item.get("combo") or item.get("source") != "yt" or not vid:
        return 0.0
    st = _trim(vid).get("start")
    return st if st is not None else _auto_span(vid, tv)[0]


def _play_span(item: dict | None, tv: dict) -> tuple[float, float | None, float | None, float | None]:
    """(จุดเริ่ม, จุดจบ, เฟดเข้า, เฟดออก) ของใบคิว — None = ใช้ค่าปกติ (ต้นคลิป/ท้ายคลิป/ค่าใน 📺)
    คอมโบ = ค่าที่ตัดเองเสมอไม่ดูโหมด · เพลงทั่วไป = trim.json > อัตโนมัติ เฉพาะตอนเปิดโหมด Custom"""
    if not item:
        return 0.0, None, None, None
    if item.get("combo"):
        s, e = item.get("clipStart") or 0.0, item.get("clipEnd")
        fi, fo = item.get("clipFadeIn"), item.get("clipFadeOut")
    elif tv.get("custom") and item.get("source") == "yt" and item.get("videoId"):
        vid = item["videoId"]
        t, a = _trim(vid), _auto_span(vid, tv)
        s = t["start"] if "start" in t else a[0]
        e = t["end"] if "end" in t else a[1]
        fi, fo = t.get("fadeIn"), t.get("fadeOut")
    else:
        return 0.0, None, None, None
    if e is not None and e <= s + SPAN_MIN:
        e = None
    return float(s), e, fi, fo


def _span_fields(item: dict, tv: dict) -> None:
    """เติม endAt / fadeIn / fadeOut / introEnd ของเพลงที่เล่นอยู่ทุก broadcast (แก้ใน Studio = มีผลสด)"""
    for k in ("endAt", "fadeIn", "fadeOut", "introEnd"):
        item.pop(k, None)
    _, e, fi, fo = _play_span(item, tv)
    if e is not None:
        item["endAt"] = e
    if fi is not None:
        item["fadeIn"] = fi
    if fo is not None:
        item["fadeOut"] = fo
    # โหมด Custom เริ่มหลังอินโทรอยู่แล้ว / คอมโบตัดเองแล้ว -> ไม่ต้องมีปุ่ม
    if tv.get("skipBtn", True) and not tv.get("custom") and not item.get("combo"):
        ie = _intro_end(item, tv)
        if ie >= tv.get("skipMin", 15):
            item["introEnd"] = ie


def _fade_out_sec(item: dict | None, tv: dict) -> float:
    if not item:
        return 0.0
    fo = _play_span(item, tv)[3]
    return float(fo if fo is not None else tv.get("fadeOut", 0))


def _lyr_fields(item: dict) -> None:
    """lyrStatus: na | queued | working | ready | failed"""
    vid = item.get("videoId")
    for k in ("lyricsUrl", "lyrLines", "lyrWarn", "lyrSrc", "lyrCheck", "lyrError",
              "lyrConf", "lyrConfWhy", "lyrKind", "lyrOffset", "wordsUrl", "wordsStatus", "lyrBest",
              "lyrFrom", "lyrLang"):
        item.pop(k, None)
    if item.get("source") != "yt" or not vid:
        item["lyrStatus"] = "na"
        return
    _lg = _song_lang(vid)[0]
    if _lg != "th":
        item["lyrLang"] = _lg
    _bst = _best_state.get(vid, {}).get("status")
    if _bst in ("queued", "working"):
        item["lyrBest"] = _bst          # กำลังเทียบเนื้อจากทุกแหล่ง (เนื้ออาจเปลี่ยนเป็นตัวที่ดีกว่า)
    _vst = _verify_state.get(vid, {}).get("status")
    chk = _vst if _vst in ("queued", "waiting", "checking", "failed") else _chk_verdict(vid)
    if chk:
        item["lyrCheck"] = chk
    mt, n, warn, src, tsrc = _lyr_meta(vid)
    if mt and n:
        # ms ไม่ใช่วินาที: บันทึกจาก Studio 2 ครั้งในวินาทีเดียว URL ต้องเปลี่ยน ไม่งั้นจอไม่โหลดใหม่
        item["lyricsUrl"] = f"/song/{vid}/lyrics.json?v={int(mt * 1000)}"
        item["lyrLines"] = n
        item["lyrWarn"] = warn
        item["lyrSrc"] = src
        item["lyrKind"] = LC.kind(src, tsrc)
        item["lyrStatus"] = "ready"
        if _lyr_from.get(vid):
            item["lyrFrom"] = _lyr_from[vid]         # "เลือกจาก JOOX" / "ระบบเลือกจาก ..." (หน้าคิวใน Studio)
        off = _lyr_offset(vid)
        if off:
            item["lyrOffset"] = off
        wm = _words_meta(vid)
        if wm["ok"] and wm["nk"]:
            item["wordsUrl"] = f"/song/{vid}/lyrics.words.json?v={int(wm['mt'] * 1000)}"
        item["wordsStatus"] = _words_status(vid)     # รีโมทบอกได้ว่า "กำลังทำ" หรือ "ไม่มี"
        # ป้ายความมั่นใจ: คำนวณสดจาก "ที่มา + ผลวัดล่าสุด" จะได้เปลี่ยนเกณฑ์
        # โดยไม่ต้องสร้าง lyrics.json ใหม่ทั้งคลัง
        ck = _chk_info(vid)
        item["lyrConf"], item["lyrConfWhy"] = LC.confidence(
            src, tsrc,
            ck.get("score") if ck.get("verdict") not in ("", "unmeasurable", "reported") else None,
            ck.get("measuredBy") or "",
            measurable=ck.get("verdict") != "unmeasurable",
            defects=len(ck.get("defects") or []), version=int(ck.get("v") or 1), sparse=_lyr_sparse(vid))
        return
    if (_song_dir(vid) / "lyrics.nolyr.json").is_file():
        item["lyrStatus"] = "nolyr"   # ลองครบทุกแหล่งแล้วจริง ๆ ไม่ใช่ "ยังไม่ได้ลอง"
        return
    st = _lyr_state.get(vid, {})
    if st.get("status"):
        item["lyrStatus"] = st["status"]
    elif not _has_stems(vid):
        item["lyrStatus"] = "na"
    else:
        # มี vocals แล้วแต่ไม่มี state — ต้องดูคิวจริง ห้ามเดาว่า "queued"
        # สถานะปลอมนั้นคืออาการ "รอหาเนื้อ" ที่ไม่มีวันขยับ และยังไปซ่อนปุ่มโหลดเนื้อใหม่ด้วย
        item["lyrStatus"] = ("queued" if _lyr_pending.has(vid) or _lyrfind_pending.has(vid)
                             else "idle")
    if st.get("error"):
        item["lyrError"] = st["error"]


def _sep_fields(item: dict) -> None:
    """เติม sepStatus/sepError/stems ลงใน item ตามสถานะล่าสุด
    sepStatus: na | queued | separating | ready | failed"""
    vid = item.get("videoId")
    if item.get("source") != "yt" or not vid:
        item["sepStatus"] = "na"
        item["sepError"] = ""
        item.pop("stems", None)
        return
    if _has_stems(vid):
        item["sepStatus"] = "ready"
        item["sepError"] = ""
        item["stems"] = {"vocals": f"/song/{vid}/vocals.m4a",
                         "noVocals": f"/song/{vid}/no_vocals.m4a"}
        item.pop("stemsKey", None)
        item.pop("keyStatus", None)
        k = int(room.mix.get("key") or 0)
        if k:                                # คีย์ของห้อง ≠ 0: มีไฟล์เลื่อนคีย์แล้ว -> ส่ง URL ให้จอ ไม่งั้นบอกสถานะงาน
            if _key_ready(vid, k):
                item["stemsKey"] = {"key": k, "vocals": f"/song/{vid}/vocals.k{k:+d}.m4a",
                                    "noVocals": f"/song/{vid}/no_vocals.k{k:+d}.m4a"}
            else:
                ks = _key_state.get(vid, {})
                item["keyStatus"] = ks.get("status", "pending") if ks.get("key") == k else "pending"
                if ks.get("error") and ks.get("key") == k:
                    item["keyError"] = ks["error"]
        return
    st = _sep_state.get(vid, {})
    item["sepStatus"] = st.get("status", "queued")
    item["sepError"] = st.get("error", "")
    item.pop("stems", None)


# --- เปลี่ยนคีย์: เลื่อนระดับเสียงของสเต็ม (ดนตรี + ไกด์) ทำล่วงหน้าแล้วแคชเป็นไฟล์ต่อคีย์ ---
# ไม่ทำสดในเบราว์เซอร์: pitch shift คุณภาพดีกิน CPU มาก ทำครั้งเดียวต่อ (เพลง, คีย์) ด้วย pedalboard
# (Rubber Band ข้างใน) แล้วจอโหลดไฟล์ชุดใหม่แทนกลางเพลง — ไม่มี pedalboard ใช้ ffmpeg asetrate+atempo (คุณภาพพอใช้)
_key_state: dict[str, dict] = {}                   # videoId -> {"status": working|failed, "key", "error"}
_key_queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
_key_task: asyncio.Task | None = None
KEY_SR = 44100


def _key_path(vid: str, stem: str, k: int) -> Path:
    return _song_dir(vid) / f"{stem}.k{k:+d}.m4a"


def _key_ready(vid: str, k: int) -> bool:
    return k == 0 or all(_key_path(vid, st, k).is_file() for st in ("vocals", "no_vocals"))


def _pitch_shift_file(src: Path, dst: Path, k: int) -> str:
    """src -> dst เลื่อน k ครึ่งเสียง ความยาว/จังหวะเท่าเดิม คืนชื่อวิธีที่ใช้"""
    tmp = dst.with_name(dst.name + ".tmp.m4a")
    try:
        from pedalboard import PitchShift
        import numpy as np
        raw = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src),
                              "-f", "f32le", "-ac", "2", "-ar", str(KEY_SR), "-"],
                             capture_output=True, check=True, timeout=FFMPEG_TIMEOUT).stdout
        audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()
        out = PitchShift(semitones=float(k))(audio, KEY_SR)
        out = np.clip(out, -1.0, 1.0).T.astype(np.float32).tobytes()
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ac", "2",
                            "-ar", str(KEY_SR), "-i", "-", "-c:a", "aac", "-b:a", "192k", str(tmp)],
                           input=out, capture_output=True, timeout=FFMPEG_TIMEOUT)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or b"").decode(errors="replace")[-300:])
        how = "pedalboard"
    except ImportError:
        ratio = 2 ** (k / 12)
        _ffmpeg(["-i", str(src), "-af", f"asetrate={KEY_SR}*{ratio:.6f},aresample={KEY_SR},atempo={1 / ratio:.6f}",
                 "-c:a", "aac", "-b:a", "192k", str(tmp)])
        how = "ffmpeg"
    os.replace(tmp, dst)
    return how


def _make_key(vid: str, k: int) -> str:
    how = ""
    for st in ("vocals", "no_vocals"):
        dst = _key_path(vid, st, k)
        if not dst.is_file():
            how = _pitch_shift_file(_song_dir(vid) / f"{st}.m4a", dst, k)
    return how


async def _key_worker() -> None:
    while True:
        vid, k = await _key_queue.get()
        superseded = room.current and room.current.get("videoId") == vid and int(room.mix.get("key") or 0) != k
        if k == 0 or _key_ready(vid, k) or not _has_stems(vid) or superseded:
            if _key_state.get(vid, {}).get("key") == k:       # กด +1 +1 ติดกัน: งาน +1 ถูกแซง ไม่ต้องทำ
                _key_state.pop(vid, None)
            await room.broadcast()
            continue
        _key_state[vid] = {"status": "working", "key": k, "error": ""}
        await room.broadcast()
        t0 = time.monotonic()
        try:
            how = await asyncio.to_thread(_make_key, vid, k)
            _key_state.pop(vid, None)
            print(f"[key] {vid} คีย์ {k:+d} พร้อม ({how}) | {time.monotonic() - t0:.0f}s")
        except Exception as exc:
            _key_state[vid] = {"status": "failed", "key": k, "error": f"{type(exc).__name__}: {exc}"[:200]}
            print(f"[key] {vid} คีย์ {k:+d} FAILED: {exc}")
        await room.broadcast()


async def _enqueue_key(vid: str | None, k: int) -> None:
    global _key_task
    if not vid or not k or not _has_stems(vid) or _key_ready(vid, k):
        return
    ks = _key_state.get(vid)
    if ks and ks.get("key") == k and ks.get("status") == "working":
        return
    if _key_task is None or _key_task.done():
        _key_task = asyncio.create_task(_key_worker())
    _key_state[vid] = {"status": "pending", "key": k, "error": ""}
    _key_queue.put_nowait((vid, k))


def _drop_key_files(vid: str) -> None:
    for f in _song_dir(vid).glob("*.k[+-]*.m4a"):
        f.unlink(missing_ok=True)


def _purge_audio_caches(vid: str) -> None:
    """ผลวิเคราะห์เสียงที่ผูกกับเสียงร้องชุดเก่า (FA ทุกโมเดล/สเต็ม, แผนที่เสียงร้อง) — แยกเสียงใหม่แล้วต้องทิ้ง
    (แคชมีลายเซ็นไฟล์เสียงอยู่แล้ว ไฟล์นี้แค่เก็บกวาดไม่ให้ค้างกินที่)"""
    try:
        for f in _fa_mod().CACHE.glob(f"{vid}.*.npz"):
            f.unlink(missing_ok=True)
        import vocal_activity as VA
        (VA.CACHE / f"{vid}.npz").unlink(missing_ok=True)
    except Exception as exc:
        print(f"[sep] {vid} ล้างแคชเสียงไม่ได้: {exc}")


def _separate_one(vid: str) -> None:
    """แยก 1 เพลง -> songs/yt/<vid>/{vocals,no_vocals}.m4a
    รันเป็น subprocess: torch ไม่ค้างใน process หลัก และ kill ได้"""
    global _sep_device
    d = _song_dir(vid)
    audio = d / "audio.m4a"
    if not audio.is_file():
        raise RuntimeError("ไม่มี audio.m4a ให้แยก")
    if _has_stems(vid):
        return

    tmp = d / ".sep"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        err = ""
        devs = [_sep_device] if _sep_device else ["mps", "cpu"]
        if "cpu" not in devs:
            devs.append("cpu")   # จำ mps ได้แล้วก็ยังต้องมีทางลง ไม่งั้นเพลงที่ OOM ตายถาวร
        for dev in devs:
            cmd = [sys.executable, "-m", "demucs", "-n", DEMUCS_MODEL,
                   "--two-stems", "vocals", "-d", dev,
                   "-o", str(tmp), str(audio)]
            env = os.environ.copy()
            if dev == "cpu":
                # cpu = ทางสำรองที่ร้อนมาก: ใช้แค่ครึ่งหนึ่งของ core + nice เหลือเครื่องไว้ให้เพลงที่กำลังเล่น
                th = str(max(2, (os.cpu_count() or 4) // 2))
                env.update(OMP_NUM_THREADS=th, MKL_NUM_THREADS=th)
                cmd = ["nice", "-n", "10"] + cmd
            try:
                rc, _, err = _run_child("sep", vid, cmd, timeout=SEP_TIMEOUT, env=env)
            except RuntimeError as exc:    # หมดเวลา — MPS ค้างก็ยังได้ลอง cpu ต่อ
                rc, err = -1, str(exc)
            if vid in _preempt_kill:
                _preempt_kill.discard(vid)
                raise _Preempted()   # ห้ามตกไป dev ถัดไป ไม่งั้นโดนฆ่าแล้วไปเปิด demucs ตัวใหม่บน cpu
            if rc == 0:
                if dev == "mps":
                    _sep_device = dev   # จำแค่ mps — เคยจำ cpu ไว้ แล้วทุกเพลงหลังจากนั้นแยกบน cpu จนรีสตาร์ท
                break
            if vid in _sep_gone or not audio.is_file():
                # เพลงถูกลบจาก Studio ระหว่างแยก (demucs โดนฆ่า rc=-9) — ไม่ใช่ mps พัง ห้ามตกไป cpu
                # ธงตั้งก่อนฆ่า: thread ตื่นมาก่อนไฟล์ถูกลบจริงก็ยังรู้
                raise RuntimeError("เพลงถูกลบระหว่างแยกเสียง")
            print(f"[sep] {vid} device={dev} rc={rc}\n{(err or '')[-1500:]}")
        else:
            raise RuntimeError(f"demucs ล้มเหลว: {(err or '').strip()[-300:]}")

        # demucs ตั้งชื่อโฟลเดอร์ตามชื่อไฟล์ input -> .sep/htdemucs/audio/*.wav
        # ใช้ glob กันเหนียว เผื่อ layout ต่างกันตามเวอร์ชัน
        jobs = []
        for stem, final in (("vocals", d / "vocals.m4a"), ("no_vocals", d / "no_vocals.m4a")):
            wav = next(iter(sorted(tmp.rglob(f"{stem}.wav"))), None)
            if wav is None:
                raise RuntimeError(f"ไม่พบไฟล์ {stem}.wav ที่ demucs ควรสร้าง")
            jobs.append((wav, final.with_suffix(".m4a.part"), final))
        # ทั้งสองสเต็มเข้ารหัสด้วยค่าเดียวกัน -> priming delay เท่ากัน -> ยังตรงกันระดับ sample
        # -f ipod: ffmpeg เดาคอนเทนเนอร์จากนามสกุล .part ไม่ได้ ต้องบอกตรงๆ
        # สองไฟล์ไม่เกี่ยวกัน -> เข้ารหัสพร้อมกัน (ไฟล์ที่ได้เหมือนทำทีละไฟล์ทุกไบต์ แค่เสร็จเร็วขึ้น)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2) as ex:
            for f in [ex.submit(_ffmpeg, ["-i", str(w), "-c:a", "aac", "-b:a", "192k",
                                          "-movflags", "+faststart", "-f", "ipod", str(pt)]) for w, pt, _ in jobs]:
                f.result()
        for _w, pt, final in jobs:
            pt.rename(final)     # atomic: ถือว่า ready ต่อเมื่อครบทั้งสองไฟล์ (เข้ารหัสเสร็จทั้งคู่ก่อนค่อยย้าย)
        _purge_audio_caches(vid)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for f in d.glob("*.m4a.part"):
            f.unlink(missing_ok=True)      # โดนแย่งคิวกลางทางมิกซ์ -> ไฟล์ครึ่ง ๆ ต้องไม่ค้าง


async def _sep_worker() -> None:
    global _heavy_job
    while True:
        await _sep_pending.wait()
        preempted = False
        # จอง GPU ก่อน แล้วค่อยเลือกงาน — เลือกก่อนจองจะได้งานที่ลำดับล้าสมัยไปแล้ว
        async with _heavy.slot("sep", lambda: (_sep_pending.best() or ("", _NEVER))[1]):
            vid = _sep_pending.take_now()
            if vid is None:
                continue
            if _has_stems(vid):
                _sep_state[vid] = {"status": "ready", "error": ""}
                await _enqueue_lyr(vid)     # มี stems อยู่แล้ว -> ยังต้องต่อยอดไปหาเนื้อเหมือนกัน
                await room.broadcast()
                continue
            if await _sep_skip_long(vid):   # ค้างในคิวมาก่อน (เช่น backfill ตอนเปิดเซิร์ฟเวอร์)
                await room.broadcast()
                continue
            _sep_state[vid] = {"status": "separating", "error": ""}
            _heavy_job = ("sep", vid)
            _preempt_kill.discard(vid)       # ล้างธงค้างจากรอบก่อน ไม่งั้นรอบนี้ตายทันทีแล้ววนไม่จบ
            _sep_gone.discard(vid)           # เพลงที่ลบแล้วเพิ่มกลับมาใหม่
            await room.broadcast()
            _t0 = time.monotonic()
            _fa_worker.preload_bg(vid)       # โหลดโมเดล FA ซ้อนกับ demucs — vocals เสร็จแล้วงานเลือกเนื้อคำนวณได้ทันที
            try:
                _drop_key_files(vid)
                await asyncio.to_thread(_separate_one, vid)
                _sep_state[vid] = {"status": "ready", "error": ""}
                _preempt_n.pop(vid, None)
                room.archive_rev += 1
                print(f"[sep] {vid} OK {time.monotonic() - _t0:.0f}s (device={_sep_device}){_since_add(vid)}")
                await _enqueue_lyr(vid)          # มี vocals แล้ว ไปหาเนื้อเพลงต่อ
                if not await _enqueue_best(vid):  # เนื้อมีอยู่แล้ว -> รอแค่ vocals ก็เทียบทุกแหล่ง/ทำเวลารายคำได้
                    await _enqueue_words(vid)
            except _Preempted:
                # ถูกแย่งคิว: กลับเป็น queued ไม่ใช่ failed — จอยังขึ้น "กำลังแยกเสียง…" เหมือนเดิม
                preempted = True
                _sep_state[vid] = {"status": "queued", "error": ""}
                _sep_pending.push(vid)
                print(f"[sep] {vid} ถูกแย่งคิว -> เข้าคิวใหม่")
            except Exception as exc:
                _sep_state[vid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                print(f"[sep] {vid} FAILED: {exc}")
            finally:
                _heavy_job = None
        await room.broadcast()
        if preempted:
            await asyncio.sleep(1.0)   # ปล่อยให้ worker ที่ได้สิทธิ์คว้า _heavy ก่อน ไม่งั้นวนฆ่าเพลงเดิมซ้ำ


async def _ensure_separator() -> None:
    global _sep_task
    if _sep_task is None or _sep_task.done():
        _sep_task = asyncio.create_task(_sep_worker())


def _sep_too_long(vid: str) -> bool:
    try:
        return float(_song_meta(vid).get("duration") or 0) > SEP_MAX_SEC
    except Exception:
        return False      # ไม่รู้ความยาว = แยกตามปกติ


async def _sep_skip_long(vid: str) -> bool:
    """คลิปยาวเกิน SEP_MAX_SEC -> ไม่แยกเสียง: ตั้ง sep เป็น failed (งานเลือกเนื้อ/รายคำใช้ audio.m4a แทน vocals ได้เอง)"""
    if not _sep_too_long(vid):
        return False
    if _sep_state.get(vid, {}).get("error") != _SEP_LONG_ERR:
        _sep_state[vid] = {"status": "failed", "error": _SEP_LONG_ERR}
        print(f"[sep] {vid} ข้าม: {_SEP_LONG_ERR}")
        if not await _enqueue_best(vid):     # เหมือนตอนแยกเสร็จ แค่ไม่มี vocals
            await _enqueue_words(vid)
    return True


async def _enqueue_sep(vid: str | None) -> None:
    if not vid or _has_stems(vid):
        return
    if not (_song_dir(vid) / "audio.m4a").is_file():
        return   # ยังโหลดไม่เสร็จ เดี๋ยว _download_worker สั่งให้เองตอนได้ไฟล์แล้ว
    if await _sep_skip_long(vid):
        return
    await _ensure_separator()   # ต้องอยู่ก่อน early-return: worker ที่ตายไปแล้วต้องถูกปลุกใหม่
                                # แม้ vid จะยังค้างอยู่ใน _sep_pending (ไม่งั้นคิวล็อกถาวร)
    # ยึดตามคิวจริง ไม่ใช่ _sep_state — สถานะที่ค้าง (เช่น worker ตาย) จะได้ไม่ล็อกเพลงออกถาวร
    # เทียบทั้ง (ชนิดงาน, vid): ของเดิมเทียบแค่ vid จึงไปชนกับงาน sep ของเพลงเดียวกัน
    if _sep_pending.has(vid) or _heavy_job == ("sep", vid):
        return
    _sep_state[vid] = {"status": "queued", "error": ""}
    _sep_pending.push(vid)      # ไม่มี urgent แล้ว — เพลงที่ไม่อยู่ในห้องได้อันดับ _BACKLOG เอง


# --- หาเนื้อเพลง (ซับ YouTube -> lrclib -> ถอดเสียง) ------------------
# งานหนักเหมือน demucs จึงใช้โครงเดียวกัน: คิวด่วน + คิวเพลงเก่า + subprocess
_lyr_task: asyncio.Task | None = None
_lyr_state: dict[str, dict] = {}                   # videoId -> {"status","error"}
_lyrfind_task: asyncio.Task | None = None
_lyrfind_pending = _Pending("lyrfind")
_lyr_nosrc: set[str] = set()      # เฟสที่ไม่ใช้ GPU ลองครบแล้วไม่เจอ -> เหลือทางเดียวคือถอดเสียง
_NEED_ASR_RC = 3                  # ตรงกับ gen_lyrics.NEED_ASR
_NO_LYRICS_RC = 4                 # ตรงกับ gen_lyrics.NO_LYRICS — ลองครบทุกแหล่งแล้วไม่มีเนื้อ


def _find_lyrics(vid: str) -> tuple[bool, str]:
    """แหล่งที่ไม่ใช้ GPU: ไฟล์ผู้ใช้ -> ซับ YouTube -> lrclib
    คืน (ต้องถอดเสียงต่อไหม, บรรทัดสรุป) — 2 ใน 3 ของคลังจบที่นี่ในไม่กี่วินาที
    ไม่แตะ GPU และไม่ต้องรอ demucs จึงไม่ต้องจองคิวงานหนักเลย"""
    script = BASE / "scripts" / "gen_lyrics.py"
    if not script.is_file():
        raise RuntimeError("ไม่มี scripts/gen_lyrics.py")
    rc, out, err = _run_child("lyrfind", vid, [sys.executable, str(script), "--no-asr", vid],
                              timeout=FIND_TIMEOUT, cwd=str(BASE))
    for l in (out or "").splitlines():
        if l.startswith("[sparse]"):
            print(l)                # ซับ/lrclib ที่มีแค่บางช่วง (บทพูดในเอ็มวี) ถูกข้าม — ไปลองแหล่งอื่นก่อน
    if rc == _NEED_ASR_RC:
        return True, ""
    if rc != 0:
        raise RuntimeError(f"gen_lyrics --no-asr ล้มเหลว: {err.strip()[-300:]}")
    if not (_song_dir(vid) / "lyrics.json").is_file():
        return True, ""            # ไม่ได้เนื้อและไม่ได้บอกว่าต้องถอดเสียง -> ลองถอดดู
    return False, next((l for l in reversed(out.splitlines()) if l[:1] in "✓▲✗"), "")


async def _lyrfind_worker() -> None:
    while True:
        await _lyrfind_pending.wait()
        vid = _lyrfind_pending.take_now()
        if vid is None:
            continue
        if _lyr_meta(vid)[1] > 0:
            _lyr_state[vid] = {"status": "ready", "error": ""}
            await room.broadcast()
            continue
        if not (_song_dir(vid) / "info.json").is_file():
            # ยังไม่มี metadata -> ค้นไปก็ผิด และจะถูกจำว่า "ไม่มีแหล่ง" ทั้งที่ยังไม่ได้ลองจริง
            _lyr_state.pop(vid, None)
            await room.broadcast()
            continue
        _lyr_state[vid] = {"status": "searching", "error": ""}
        await room.broadcast()
        t0 = time.monotonic()
        try:
            await _ensure_lang(vid)          # gen_lyrics จะได้อ่านภาษาจาก lang.json ไม่ต้องเดาเอง
            need_asr, line = await asyncio.to_thread(_find_lyrics, vid)
            if (_song_dir(vid) / "lyrics.nolyr.json").is_file():
                _lyr_state[vid] = {"status": "nolyr", "error": ""}
                print(f"[lyr] {vid} ไม่มีเนื้อจากทุกแหล่ง ({time.monotonic() - t0:.0f}s){_since_add(vid)}")
            elif not need_asr:
                _lyr_state[vid] = {"status": "ready", "error": ""}
                room.archive_rev += 1
                print(f"[lyr] {line or vid + ' OK'} | {time.monotonic() - t0:.0f}s (ไม่ใช้ GPU){_since_add(vid)}")
                if not await _enqueue_best(vid):
                    await _enqueue_words(vid)
            else:
                _lyr_nosrc.add(vid)
                _lyr_state.pop(vid, None)
                print(f"[lyr] {vid} ต้องถอดเสียง ({time.monotonic() - t0:.0f}s){_since_add(vid)}")
                await _enqueue_lyr(vid)      # ไม่มี vocals? _enqueue_lyr จะสั่งแยกเสียงให้เอง
        except Exception as exc:
            _lyr_nosrc.add(vid)              # ค้นไม่ได้ก็ยังเหลือทางถอดเสียง
            _lyr_state.pop(vid, None)
            print(f"[lyr] {vid} ค้นเนื้อไม่สำเร็จ: {exc}")
            await _enqueue_lyr(vid)
        await room.broadcast()
        _prefetch_best(vid)              # เนื้อรอบแรกนิ่งแล้ว -> ดึงแหล่งให้งานเลือกเนื้อไว้ก่อน (ถ้าวิดีโอมาแล้ว)


async def _ensure_lyricfinder() -> None:
    global _lyrfind_task
    if _lyrfind_task is None or _lyrfind_task.done():
        _lyrfind_task = asyncio.create_task(_lyrfind_worker())


def _build_lyrics(vid: str) -> str:
    """เรียก scripts/gen_lyrics.py ของเพลงเดียว คืนบรรทัดสรุปที่มันพิมพ์ออกมา
    รันเป็น subprocess ด้วยเหตุผลเดียวกับ demucs: whisper ไม่ค้างใน process หลัก"""
    script = BASE / "scripts" / "gen_lyrics.py"
    if not script.is_file():
        raise RuntimeError("ไม่มี scripts/gen_lyrics.py")
    try:
        rc, out, err = _run_child("lyr", vid, [sys.executable, str(script), vid],
                                  timeout=LYR_TIMEOUT, cwd=str(BASE))
    except RuntimeError:
        if vid in _preempt_kill:
            _preempt_kill.discard(vid)
            raise _Preempted()
        raise
    if vid in _preempt_kill:
        _preempt_kill.discard(vid)
        raise _Preempted()
    for l in (out or "").splitlines():
        if l.startswith(("[asr]", "[sparse]")):
            print(l)                # เวลาถอดเสียงจริงของ whisper (เวลารวมของ gen_lyrics รวมเน็ต/ลองซ้ำด้วย) / ซับที่ข้าม
    if rc == _NO_LYRICS_RC:
        return ""                   # ลองครบทุกแหล่งแล้วไม่มีเนื้อ — ไม่ใช่ความล้มเหลว
    if rc != 0:
        raise RuntimeError(f"gen_lyrics ล้มเหลว: {(err or '').strip()[-300:]}")
    if not (_song_dir(vid) / "lyrics.json").is_file():
        raise RuntimeError("หาเนื้อเพลงไม่ได้จากทุกแหล่ง")
    return next((l for l in reversed((out or "").splitlines()) if l[:1] in "✓▲✗"), "")


async def _lyr_worker() -> None:
    global _heavy_job
    while True:
        await _lyr_pending.wait()
        preempted = False
        # โครงเดียวกับ _sep_worker: จอง GPU ก่อน แล้วค่อยเลือก
        async with _heavy.slot("lyr", lambda: (_lyr_pending.best() or ("", _NEVER))[1]):
            vid = _lyr_pending.take_now()
            if vid is None:
                continue
            if _lyr_meta(vid)[1] > 0:
                _lyr_state[vid] = {"status": "ready", "error": ""}
                await room.broadcast()
                continue
            _lyr_state[vid] = {"status": "working", "error": ""}
            _heavy_job = ("lyr", vid)
            _preempt_kill.discard(vid)
            await room.broadcast()
            _t0 = time.monotonic()
            try:
                line = await asyncio.to_thread(_build_lyrics, vid)
                nolyr = (_song_dir(vid) / "lyrics.nolyr.json").is_file()
                _lyr_state[vid] = {"status": "nolyr" if nolyr else "ready", "error": ""}
                _preempt_n.pop(vid, None)
                room.archive_rev += 1
                print(f"[lyr] {line or vid + (' ไม่มีเนื้อจากทุกแหล่ง' if nolyr else ' OK')}"
                      f" | {time.monotonic() - _t0:.0f}s{_since_add(vid)}")
                # ไม่มีเนื้อจากทางปกติ ก็ยังมีลุ้นจาก JOOX/YouTube Music/NetEase ในงานเลือกเนื้อ
                if not await _enqueue_best(vid) and not nolyr:
                    await _enqueue_words(vid)
            except _Preempted:
                preempted = True
                _lyr_state[vid] = {"status": "queued", "error": ""}
                _lyr_pending.push(vid)
                print(f"[lyr] {vid} ถูกแย่งคิว -> เข้าคิวใหม่")
            except Exception as exc:
                _lyr_state[vid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                print(f"[lyr] {vid} FAILED: {exc}")
            finally:
                _heavy_job = None
        await room.broadcast()
        if preempted:
            await asyncio.sleep(1.0)


async def _ensure_lyricist() -> None:
    global _lyr_task
    if _lyr_task is None or _lyr_task.done():
        _lyr_task = asyncio.create_task(_lyr_worker())


async def _enqueue_lyr(vid: str | None) -> None:
    if not vid or _lyr_meta(vid)[1] > 0:
        return   # "มีไฟล์" ไม่พอ — ไฟล์ที่เขียนค้างครึ่งเดียวต้องถือว่ายังไม่มี ไม่งั้นค้างถาวร
    if vid not in _lyr_nosrc:
        # ยังไม่ได้ลองแหล่งที่ไม่ใช้ GPU — ไม่ต้องรอ demucs และไม่ต้องจองคิวงานหนัก
        await _ensure_lyricfinder()
        if not _lyrfind_pending.has(vid):
            _lyr_state[vid] = {"status": "queued", "error": ""}
            _lyrfind_pending.push(vid)
        return
    if not _has_stems(vid):
        if _sep_too_long(vid):    # คลิปยาว: ไม่แยกเสียง จึงไม่ถอดเสียงด้วย (whisper ทั้งคลิปหนักเกิน)
            _lyr_state[vid] = {"status": "failed", "error": _LYR_LONG_ERR}
            return
        await _enqueue_sep(vid)   # เหลือทางถอดเสียงแล้ว -> ขอ vocals ก่อน เดี๋ยว sep ต่อให้เอง
        return
    await _ensure_lyricist()    # ต้องอยู่ก่อน early-return ด้วยเหตุผลเดียวกับ _enqueue_sep
    # เทียบทั้ง (ชนิดงาน, vid) — ของเดิมเทียบแค่ vid ทำให้ _sep_worker ที่เรียกฟังก์ชันนี้
    # ตอน _heavy_job ยังเป็น ("sep", vid) โดน return ทิ้งทุกครั้ง = ไม่เคยได้หาเนื้อเลย
    if _lyr_pending.has(vid) or _heavy_job == ("lyr", vid):
        return
    _lyr_state[vid] = {"status": "queued", "error": ""}
    _lyr_pending.push(vid)


# แคชผลถอดเสียงของ gen_lyrics.py — ต้องรู้จักที่นี่ด้วย 2 เหตุผล:
# 1) ตรวจเนื้อที่มีแคชแล้วใช้เวลาแค่ไม่กี่วิ และไม่แตะ GPU -> ไม่ต้องรอเพลงจบ
# 2) สั่งโหลดเนื้อใหม่แล้วไม่ล้างแคช = ได้ผลถอดเสียงชุดเดิม = ได้เนื้อหน้าตาเดิมเป๊ะ
SEG_CACHE = BASE / "lyrics-preview" / "_seg"


def _asr_cached(vid: str) -> bool:
    return (SEG_CACHE / f"{vid}.json").is_file() or any(SEG_CACHE.glob(f"{vid}.*.json"))


def _clear_lyrics(vid: str) -> None:
    """ล้างเนื้อเพลงเดิมทั้งชุด เพื่อให้สร้างใหม่ตั้งแต่ต้นจริง ๆ
    ลบผลตรวจด้วย ไม่งั้นป้าย "เนื้อไม่ตรง" เดิมจะค้างทับของใหม่
    เนื้อชุดปัจจุบันสำรองลง lyrics.edits/ ก่อนเสมอ — ของเดิมลบทิ้งเฉย ๆ ทำให้ "เลิกใช้เนื้อที่แก้เอง"
    ทำฉบับล่าสุดหายถาวร ทั้งที่กล่องยืนยันใน Studio บอกว่าย้อนกลับได้จากประวัติ"""
    d = _song_dir(vid)
    _backup_lyrics(d, _read_lyr(vid))
    for name in ("lyrics.json", "lyrics.json.tmp", "lyrics.check.json",
                 "lyrics.nolyr.json", "lyrics.offset.json"):
        (d / name).unlink(missing_ok=True)
    _off_cache.pop(vid, None)
    (SEG_CACHE / f"{vid}.json").unlink(missing_ok=True)
    for f in SEG_CACHE.glob(f"{vid}.*.json"):      # แคชของทุกโมเดล
        f.unlink(missing_ok=True)
    _lyr_cache.pop(vid, None)
    _chk_cache.pop(vid, None)
    _lyr_state.pop(vid, None)
    _verify_state.pop(vid, None)
    _lyr_nosrc.discard(vid)     # ให้ลองแหล่งที่ไม่ใช้ GPU ใหม่ด้วย (ผู้ใช้อาจเพิ่งวางไฟล์เอง)
    _dl_fails.pop(vid, None)


# --- ภาษาของเพลง ----------------------------------------------------------
# lang.json ต่อเพลง (ดู LS.song_lang) — ชื่อคลิป/แทร็ก ASR รู้ได้ทันที ไม่รู้ค่อยให้ whisper ฟัง (GPU)
_lang_cache: dict[str, tuple[float, str, str]] = {}


def _song_lang(vid: str) -> tuple[str, str]:
    """(ภาษา, ที่มา) — แคชด้วย mtime ของ lang.json; ยังไม่มีไฟล์ = เดาจากชื่อ/แทร็ก ASR (ไม่ใช้ GPU)"""
    d = _song_dir(vid)
    try:
        mt = (d / "lang.json").stat().st_mtime
    except OSError:
        mt = 0.0
    hit = _lang_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1], hit[2]
    try:
        lang, by = LS.song_lang(d, save=False)
    except Exception:
        lang, by = "th", "unknown"
    _lang_cache[vid] = (mt, lang, by)
    return lang, by


def _detect_lang_sync(vid: str) -> tuple[str, float] | None:
    """whisper ฟังเสียงร้องแล้วบอกภาษา — รันเป็น subprocess เหมือน demucs/gen_lyrics
    ของเดิม import gen_lyrics แล้วโหลด mlx-whisper ในโปรเซสหลัก: โมเดลหลาย GB ถูกโหลดเข้าหน่วยความจำเซิร์ฟเวอร์ทุกครั้ง"""
    audio = _audio_for(vid)
    if not audio:
        return None
    rc, out, err = _run_child("lang", vid, [sys.executable, str(BASE / "scripts" / "gen_lyrics.py"),
                                            "--detect-lang", str(audio.resolve())],
                              timeout=LANG_TIMEOUT, cwd=str(BASE))
    if rc != 0:
        tail = [l for l in err.strip().splitlines() if l.strip()]
        raise RuntimeError(tail[-1][:200] if tail else f"rc={rc}")
    j = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    return (str(j["lang"]), float(j.get("prob") or 0.0)) if j.get("lang") else None


def _whisper_done(rec: dict, audio: Path | None) -> bool:
    """whisper เคยฟังเพลงนี้แล้ว (แต่ไม่มั่นใจ) ด้วยเสียงที่ดีที่สุดที่มีตอนนี้ -> ไม่ต้องฟังซ้ำ
    เคยฟังเสียงรวม แล้วตอนนี้มีเสียงร้องแยกแล้ว = ฟังใหม่ได้อีกครั้ง (เสียงร้องล้วนตัดสินภาษาแม่นกว่า)"""
    if not rec.get("whisperTried"):
        return False
    return not (rec.get("audio") == "audio.m4a" and audio is not None and audio.name == "vocals.m4a")


_lang_locks: dict[str, asyncio.Lock] = {}


async def _ensure_lang(vid: str) -> str:
    """ให้แน่ใจว่ามี lang.json ก่อนหาเนื้อ — ชื่อ/แทร็ก ASR ตัดสินได้ก็จบ ไม่งั้นให้ whisper ฟัง (จองช่อง GPU ตามอันดับเพลง)
    ทำทีละงานต่อเพลง: สองงานพร้อมกัน (หาเนื้อ + ปุ่มตรวจภาษา) ใช้ชื่อช่อง GPU เดียวกันแล้วทับกันเอง"""
    async with _lang_locks.setdefault(vid, asyncio.Lock()):
        return await _ensure_lang_locked(vid)


async def _ensure_lang_locked(vid: str) -> str:
    global _heavy_job
    d = _song_dir(vid)
    rec = LS.read_lang(d)
    if rec and rec.get("by") not in ("yt-asr", "default"):
        return _song_lang(vid)[0]
    if rec and _whisper_done(rec, _audio_for(vid)):
        # ของเดิมลบแล้วให้ whisper ฟังใหม่ทุกครั้งที่หาเนื้อ + ทุกครั้งที่เปิดเซิร์ฟเวอร์ ได้ผลเดิมทุกรอบ
        # (อยากให้ฟังใหม่จริง ๆ ใช้ปุ่มตรวจภาษาใน Studio ซึ่งลบ lang.json ก่อน)
        return rec["lang"]
    if rec:                                  # ค่าชั่วคราวจากแทร็ก ASR (YouTube เดาผิดได้) -> ตรวจซ้ำด้วยหลักฐานที่ดีกว่า
        (d / "lang.json").unlink(missing_ok=True)
        _lang_cache.pop(vid, None)
    try:
        info = json.loads((d / "info.json").read_text("utf-8"))
    except Exception:
        info = {}
    lang, by = await asyncio.to_thread(LS.song_lang, d, info, None, True, True)   # ชื่อ -> lrclib (เน็ต ไม่ใช้ GPU)
    if by in ("title", "lrclib", "yt-asr+lrclib") or not _audio_for(vid):
        _lang_cache.pop(vid, None)
        return lang                          # ชื่อคลิป/lrclib บอกชัด / ไม่มีเสียงให้ฟัง = เท่านี้
    # เพลงเก่าที่มีเนื้อซึ่ง FA ยืนยันแล้วว่าตรงเสียง: อักษรของเนื้อนั้น = ภาษาที่ร้อง (แม่นกว่าให้ whisper ฟังใหม่)
    j = _read_lyr(vid)
    if j:
        txt = " ".join(l.get("x") or "" for l in j.get("lines") or [])
        tl = LS.text_lang(txt)
        ck = _chk_info(vid)
        agree = (ck.get("score") or 0) if ck.get("measuredBy") == "fa" else 0
        bb = _best_brief(vid) or {}
        if tl and (agree >= 60 or (bb.get("status") == "done" and bb.get("action") in ("keep", "shift"))):
            LS.write_lang(d, tl, "lyrics")
            _lang_cache.pop(vid, None)
            return tl
    audio = _audio_for(vid)
    failed = False
    async with _heavy.slot(f"lang:{vid}", lambda: _prio(vid) + 0.2):
        _heavy_job = ("lang", vid)
        try:
            r = await asyncio.to_thread(_detect_lang_sync, vid)
        except Exception as exc:
            print(f"[lang] {vid} ตรวจภาษาไม่ได้: {exc}")
            r, failed = None, True
        finally:
            _heavy_job = None
    _, asr = LS.asr_track(info)
    got = LS.norm_lang(r[0]) if r else ""
    if got and ((r[1] or 0) >= 0.75 or (got == asr and (r[1] or 0) >= 0.5)):
        LS.write_lang(d, got, "whisper", prob=round(float(r[1] or 0), 2))
        print(f"[lang] {vid} whisper ว่า {got} ({(r[1] or 0):.0%})")
    else:
        # จำว่า whisper ฟังแล้ว (ด้วยเสียงไฟล์ไหน) -> ไม่ฟังซ้ำอัตโนมัติ / ฟังไม่สำเร็จ (หมดเวลา/พัง) = ไม่จำ ลองใหม่ได้
        tried = {} if failed else {"whisperTried": int(time.time()), "audio": audio.name if audio else ""}
        LS.write_lang(d, asr or "th", "yt-asr" if asr else "default",
                      prob=round(float((r or (0, 0))[1] or 0), 2), **tried)
        print(f"[lang] {vid} whisper ไม่มั่นใจ ({got or '-'} {(r[1] if r else 0):.0%}) -> ใช้ {asr or 'th'}")
    _lang_cache.pop(vid, None)
    return _song_lang(vid)[0]


def _lang_migrate_needed(vid: str) -> str:
    """เพลงที่ไม่ใช่ไทยและเนื้อปัจจุบันได้มาจากขั้นที่ยังคิดว่าเป็นไทย -> เหตุผลที่ต้องหาใหม่ ("" = ไม่ต้อง)"""
    d = _song_dir(vid)
    lang, by = _song_lang(vid)
    if lang == "th" or by == "unknown":
        return ""
    rec = LS.read_lang(d)
    if rec.get("migrated"):
        return ""
    j = _read_lyr(vid)
    if not j:
        return "ไม่มีเนื้อ" if (d / "lyrics.nolyr.json").is_file() else ""
    src, tsrc = j.get("src") or "", LC.time_src_of(j)
    if src in BEST_MANUAL:
        return ""
    if src == "yt-sub" and not (d / f"sub.{lang}.vtt").is_file():
        return "เนื้อมาจากซับไทยซึ่งเป็นคำแปล"
    if src == "yt-auto":
        return "เนื้อจากคำบรรยายอัตโนมัติภาษาไทย"
    if tsrc in ("asr", "auto-cap"):
        return "จับเวลาด้วยการถอดเสียงภาษาไทย"
    return ""


async def _lang_migrate(vid: str) -> bool:
    why = _lang_migrate_needed(vid)
    if not why:
        return False
    d = _song_dir(vid)
    lang = _song_lang(vid)[0]
    await asyncio.to_thread(_fetch_subs, d, vid, lang)
    await asyncio.to_thread(_fetch_auto_caption, d, vid)
    LS.write_lang(d, lang, LS.read_lang(d).get("by") or "cache", migrated=int(time.time()))
    _lang_cache.pop(vid, None)
    print(f"[lang] {vid} ({lang}) หาเนื้อใหม่: {why}")
    await _relyr(vid)
    return True


async def _relyr(vid: str) -> None:
    """โหลดเนื้อใหม่ตั้งแต่ต้น — ใช้ทั้งปุ่มบนรีโมทและใน Studio
    ไฟล์ใน lyrics-in/ ไม่ถูกแตะ จึงยังมาก่อนทุกแหล่งเหมือนเดิม (เนื้อที่แก้เองไม่หาย)"""
    _clear_lyrics(vid)
    print(f"[lyr] {vid} สั่งโหลดเนื้อใหม่ (ล้างเนื้อเดิม+แคชถอดเสียง)")
    if _has_stems(vid):
        await _enqueue_lyr(vid)
    else:
        await _enqueue_sep(vid)   # ยังไม่มี vocals -> แยกเสียงก่อน เดี๋ยวมันต่อให้เอง


# --- ตรวจเนื้อเพลงตามที่มีคนรายงาน (ขั้นที่ 4) -------------------------
# ต่างจากขั้นอื่นตรงที่ "รอให้เพลงนั้นเล่นจบก่อน" — คนกำลังร้องอยู่ ห้ามแย่ง GPU
_verify_queue: asyncio.Queue[str] = asyncio.Queue()
_verify_task: asyncio.Task | None = None
_verify_state: dict[str, dict] = {}                # videoId -> {"status","error"}


# --- แจ้งซับไม่ตรงจากรีโมท -> กล่องรายงานใน Studio (คนแก้เอง ไม่ซ่อมอัตโนมัติ) ---------
# แยกไฟล์จาก lyrics.check.json เพราะบันทึกใน Studio ลบ check.json ทิ้งทุกครั้ง รายงานจะหายตาม
REPORT_TAGS = ("late", "early", "typo", "missing", "nolyr", "wrong", "fast", "overlap")
REPORTS_KEEP = 50


def _reports_file(vid: str) -> Path:
    return _song_dir(vid) / "lyrics.reports.json"


def _read_reports(vid: str) -> list[dict]:
    try:
        data = json.loads(_reports_file(vid).read_text("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_reports(vid: str, reps: list[dict]) -> None:
    f = _reports_file(vid)
    if not reps:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(reps[-REPORTS_KEEP:], ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def _add_user_report(vid: str, pos: float, tags: Any, note: Any, by: Any) -> dict:
    tags = [t for t in (tags if isinstance(tags, list) else []) if t in REPORT_TAGS][:len(REPORT_TAGS)]
    rep = {"id": uuid.uuid4().hex[:10], "at": round(time.time(), 3), "pos": round(max(0.0, pos), 1), "tags": tags,
           "note": " ".join(str(note or "").split())[:200],
           "by": " ".join(str(by or "").split())[:24] or DEFAULT_SINGER, "done": False}
    _write_reports(vid, _read_reports(vid) + [rep])
    return rep


CHECK_VERSION = 2            # 2 = lyrics_refine.check_timing (มีหมุดกันฮุคไหล + นับบรรทัดบกพร่อง)


def _write_check(vid: str, score: float | None, shift: float, by: str, n: int, note: str = "",
                 v2: dict | None = None) -> dict:
    """ผลตรวจเวลาเนื้อ -> lyrics.check.json (ป้ายความมั่นใจบนรีโมท/Studio อ่านจากนี่)
    เก็บรายงานจากรีโมทที่ค้างอยู่ในไฟล์เดิมไว้ด้วย"""
    d = _song_dir(vid)
    j = _read_lyr(vid) or {}
    old = _chk_info(vid)
    rec = {"vid": vid, "at": time.time(), "src": j.get("src") or "", "timeSrc": LC.time_src_of(j) if j else "",
           "measuredBy": by, "lines": n, "shift": round(shift, 2), "note": note}
    try:                    # เวลาตรงทุกบรรทัดไม่ได้แปลว่าเนื้อครบ — เก็บว่าคลุมเสียงร้องกี่ % ไว้ให้ป้าย 🕳 (ผู้เรียกอยู่ใน thread)
        cv = _cover_of(vid, j.get("lines") or [], _lyr_offset(vid)) if j else None
        if cv is not None:
            rec["cover"] = cv
    except Exception as exc:
        print(f"[check] {vid} วัดความคลุมไม่ได้: {type(exc).__name__}: {exc}")
    defects = list((v2 or {}).get("defects") or [])
    if v2 is not None:
        rec.update(v=CHECK_VERSION, defects=defects, g=v2.get("g") or 0.0)
    ok_at = LC.OK_SCORE_V2 if v2 is not None else LC.OK_SCORE
    if score is None:
        rec.update(verdict="unmeasurable", score=None)
    else:
        rec.update(verdict="ok" if score >= ok_at and len(defects) < LC.DEFECT_MIN else "bad", score=round(score, 1))
    for k in ("reports",):
        if old.get(k):
            rec[k] = old[k]
    _write_json_atomic(d / "lyrics.check.json", rec)
    _chk_cache.pop(vid, None)
    return rec


def _fa_measure2(vid: str, lines: list[dict], off: float, dur: float, kind: str = "verify") -> dict:
    """ตรวจเวลา v2 (scripts/lyrics_refine.check_timing) — FA สองรอบผ่าน subprocess เดิม (แคชเสียงแล้ว = CPU ไม่กี่วิ)"""
    import lyrics_refine as RF
    return RF.check_timing(lambda p: _fa_call(vid, p, kind=kind), lines, off, dur, FA_MIN_CONF)


def _verify_one(vid: str) -> str:
    """ตรวจเวลาเนื้อด้วย FA (เดิม whisper ~27% ภายใน 0.5 วิ / FA ~80%) — วัดอย่างเดียว ไม่เปลี่ยนเนื้อ
    เนื้อที่ FA จับเวลาเองก็ยังวัดได้ แต่ LC.confidence ถือเป็นการวัดตัวเอง (ไม่ขึ้นป้ายว่าตรวจแล้ว)"""
    j = _read_lyr(vid)
    L = (j or {}).get("lines") or []
    if not L:
        raise RuntimeError("ยังไม่มีเนื้อให้ตรวจ")
    if _song_lang(vid)[0] not in LS.FA_LANGS or not _fa_scriptable(vid):
        _write_check(vid, None, 0.0, "fa", 0, "ไม่มีโมเดล FA สำหรับภาษานี้")
        return f"{vid} วัดไม่ได้: ไม่มีโมเดล FA สำหรับภาษานี้"
    m = _fa_measure2(vid, L, _lyr_offset(vid), float(j.get("duration") or 0), "verify")
    score, shift, n, after = m["score"], m["shift"], m["n"], m["after"]
    rec = _write_check(vid, score, shift, "fa", n, v2=m)
    if score is None:
        return f"{vid} วัดไม่ได้ (FA มั่นใจแค่ {n}/{len(L)} บรรทัด)"
    return (f"{vid} เวลาตรง {score:.0f}% ({rec['verdict']})"
            + (f" เลื่อน {shift:+.2f} จะได้ {after:.0f}%" if shift else "")
            + (f" · บรรทัดบกพร่อง {len(m['defects'])}" if m["defects"] else ""))


async def _verify_worker() -> None:
    global _heavy_job
    while True:
        vid = await _verify_queue.get()
        # รอเพลงจบก่อนค่อยแย่ง GPU — แต่เฉพาะตอนที่ต้องถอดเสียงใหม่จริง ๆ
        # ถ้ามีแคชถอดเสียงอยู่แล้ว การตรวจใช้เวลาไม่กี่วิและไม่แตะ GPU เลย
        # (ของเดิมรอทุกกรณี จึงรู้สึกว่าปุ่มรายงานช้ามากทั้งที่งานจริงแป๊บเดียว)
        _verify_state[vid] = {"status": "checking", "error": ""}
        await room.broadcast()
        try:
            async with _heavy.slot("verify", lambda: _VERIFY_RANK):
                _heavy_job = ("verify", vid)
                _preempt_kill.discard(vid)
                try:
                    line = await asyncio.to_thread(_verify_one, vid)
                finally:
                    _heavy_job = None
            _verify_state.pop(vid, None)
            _preempt_n.pop(vid, None)
            _lyr_cache.pop(vid, None)          # เนื้ออาจถูกแก้ไปแล้ว ล้างแคชให้อ่านใหม่
            room.archive_rev += 1
            print(f"[verify] {line or vid}")
            if not await _enqueue_best(vid):   # ตรวจแล้วเปลี่ยนเนื้อ -> เวลารายคำชุดเก่าใช้ไม่ได้
                await _enqueue_words(vid)
        except _Preempted:
            # ตรวจเนื้อเป็นงานที่รอได้ที่สุด ยอมให้เพลงในคิวแย่งเสมอ แล้วค่อยกลับมาทำใหม่
            _verify_state[vid] = {"status": "checking", "error": ""}
            _verify_queue.put_nowait(vid)
            print(f"[verify] {vid} ถูกแย่งคิว -> เข้าคิวใหม่")
            await asyncio.sleep(1.0)
        except Exception as exc:
            _verify_state[vid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            print(f"[verify] {vid} FAILED: {exc}")
        await room.broadcast()


async def _ensure_verifier() -> None:
    global _verify_task
    if _verify_task is None or _verify_task.done():
        _verify_task = asyncio.create_task(_verify_worker())


async def _enqueue_verify(vid: str | None) -> None:
    if not vid or _lyr_meta(vid)[1] <= 0:
        return
    if _verify_state.get(vid, {}).get("status") in ("queued", "waiting", "checking"):
        return
    _verify_state[vid] = {"status": "queued", "error": ""}   # "checking" ต้องตั้งตอนเริ่มทำจริงเท่านั้น
    await _ensure_verifier()
    _verify_queue.put_nowait(vid)


def _fix_target(vid: str) -> tuple[str, str]:
    """ขั้นที่พังของเพลงนี้ + เหตุผลสั้น ๆ ("" = ไม่มีอะไรพัง)
    ใช้ที่เดียวทั้งตอน broadcast และตอนกดปุ่ม ปุ่มกับป้ายจะได้ไม่เถียงกันเอง
    บอกเฉพาะที่ "ตันจริง" — งานที่แค่รอคิวอยู่ watchdog จัดการเองอยู่แล้ว"""
    d = _song_dir(vid)
    if not (d / "video.mp4").is_file():
        if _dl_state.get(vid, {}).get("status") == "downloading":
            return "", ""
        if _dl_state.get(vid, {}).get("status") == "failed" or _dl_fails.get(vid):
            # หน้าเว็บโชว์ fixWhy ก่อน dlError — โดนบล็อกบอทต้องบอกวิธีแก้ตรงนี้ ไม่งั้นเห็นแค่ "ไม่สำเร็จ"
            return "dl", (_BOT_HINT if _dl_state.get(vid, {}).get("error") == _BOT_HINT else "โหลดวิดีโอไม่สำเร็จ")
        return "", ""
    if not (d / "audio.m4a").is_file():
        return "audio", "แยกไฟล์เสียงไม่สำเร็จ"
    # คลิปยาวที่ตั้งใจข้าม (SEP_MAX_SEC) ไม่ใช่ของพัง — กดซ่อมก็ข้ามซ้ำ ไม่ต้องโชว์ปุ่ม
    if not _has_stems(vid) and _sep_state.get(vid, {}).get("status") == "failed" \
            and _sep_state[vid].get("error") != _SEP_LONG_ERR:
        return "sep", "แยกเสียงร้องไม่สำเร็จ"
    if _lyr_meta(vid)[1] <= 0 and _lyr_state.get(vid, {}).get("status") == "failed" \
            and _lyr_state[vid].get("error") != _LYR_LONG_ERR:
        return "lyr", "หาเนื้อเพลงไม่สำเร็จ"
    if _verify_state.get(vid, {}).get("status") == "failed":
        return "verify", "ตรวจเนื้อไม่สำเร็จ"
    return "", ""


def _fix_fields(item: dict) -> None:
    item.pop("fix", None)
    item.pop("fixWhy", None)
    vid = item.get("videoId")
    if item.get("source") != "yt" or not vid:
        return
    f, why = _fix_target(vid)
    if f:
        item["fix"], item["fixWhy"] = f, why


async def _do_fix(vid: str) -> None:
    """ผู้ใช้กด "ลองใหม่" — เซิร์ฟเวอร์เลือกขั้นที่พังให้เอง
    ทุกทางล้วน idempotent: กดรัว ๆ ไม่ทำให้งานซ้อน (_Pending กันซ้ำให้อยู่แล้ว)"""
    what, _ = _fix_target(vid)
    _preempt_n.pop(vid, None)      # กดซ่อมเอง = ให้สิทธิ์ถูกแย่งคิวใหม่ ไม่ติดเพดานเดิม
    if what in ("dl", "audio"):
        _dl_fails.pop(vid, None)
        _dl_state.pop(vid, None)
        _dl_scrub(_song_dir(vid))
        _invalidate_dirs()
        await _ensure_downloader()
        _dl_pending.push(vid)
    elif what == "sep":
        _sep_state.pop(vid, None)  # ล้างธง failed -> _enqueue_sep รับต่อได้เอง
        await _enqueue_sep(vid)
    elif what == "lyr":
        _lyr_state.pop(vid, None)
        _lyr_nosrc.discard(vid)    # ให้ลองแหล่งที่ไม่ใช้ GPU ใหม่ก่อนถอดเสียง
        await _enqueue_lyr(vid)
    elif what == "verify":
        _verify_state.pop(vid, None)
        _chk_cache.pop(vid, None)
        await _enqueue_verify(vid)
    print(f"[fix] {vid} ผู้ใช้สั่งซ่อมขั้น {what or '-'}")


def _mark_ready_if_archived(item: dict) -> bool:
    """ถ้าเพลงนี้เคยโหลดเก็บไว้แล้ว → ติดสถานะ ready ไว้เลย ไม่ต้องโหลดซ้ำ"""
    vid = item.get("videoId")
    if not vid:
        return False
    d = _song_dir(vid)
    if not (d / "video.mp4").is_file():
        return False
    item["dlStatus"] = "ready"
    item["dlError"] = ""
    item["localUrl"] = f"/song/{vid}/video.mp4"
    if (d / "cover.jpg").is_file():
        item["localThumb"] = f"/song/{vid}/cover.jpg"
    return True


AUTO_SINGER = "🔀 สุ่มอัตโนมัติ"        # ป้ายคนร้องของเพลงที่ระบบสุ่มมาเอง


def _autoplay_pick() -> dict[str, Any] | None:
    """สุ่มเพลงจากคลัง (เกณฑ์เดียวกับ /api/archive: มี video.mp4) เลี่ยงเพลงที่เพิ่งสุ่มไป"""
    vids = [v for v, d in _dir_index().items() if (d / "video.mp4").is_file()]
    if not vids:
        return None
    pool = [v for v in vids if v not in room.auto_recent] or vids
    vid = random.choice(pool)
    room.auto_recent.append(vid)
    keep = min(20, len(vids) // 2)
    del room.auto_recent[:max(0, len(room.auto_recent) - keep)]
    return {
        "source": "yt",
        "videoId": vid,
        "title": _song_meta(vid)["title"],
        "thumb": f"/song/{vid}/cover.jpg",
        "singer": AUTO_SINGER,
        "dlStatus": "ready",
        "dlError": "",
        "auto": True,
    }


async def _autoplay_fill() -> bool:
    """จอว่าง + เปิดสุ่มไว้ -> หยิบเพลงจากคลังมาเล่นทันที (เรียกภายใต้ room.lock)
    ไม่ลงประวัติ "ใครร้องอะไร" และไม่นับ plays — เป็นเพลงที่ระบบเปิดเอง ไม่ใช่คนสั่ง"""
    if not room.autoplay or room.current is not None or room.queue:
        return False
    it = _autoplay_pick()
    if not it:
        return False
    room.add(it)                      # current ว่างอยู่ add() จะ next() ให้เอง
    _mark_ready_if_archived(it)
    await _enqueue_sep(it["videoId"])   # ส่วนใหญ่มีอยู่แล้ว = no-op
    await _enqueue_lyr(it["videoId"])
    return True


async def _reprioritize() -> None:
    """คิวห้องขยับ -> ให้ทุกไปป์ไลน์เดินตามลำดับใหม่ทันที
    เรียกหลังทุกคำสั่งที่ทำให้ลำดับเปลี่ยน (add/next/ended/remove/up/down/playnow)

    การกวาดห้องตรงนี้มีไว้ดึงเพลงที่ยัง "ไม่เคย" เข้าคิวงานเข้ามาเท่านั้น
    ตัวที่อยู่ใน _Pending แล้วเลื่อนอันดับเองอัตโนมัติ เพราะ best() อ่าน _prio_map() สดทุกครั้ง"""
    for it in ([room.current] if room.current else []) + room.queue:
        vid = it.get("videoId")
        if it.get("source") != "yt" or not vid:
            continue
        await _ensure_downloader()
        if not (_song_dir(vid) / "video.mp4").is_file() and not _dl_pending.has(vid) \
                and _dl_state.get(vid, {}).get("status") != "downloading" \
                and _dl_fails.get(vid, 0) < _DL_AUTO_MAX:
            # ของเดิม _reprioritize แตะแต่ sep/lyr — เพลงที่โหลดพังจึงค้างถาวร
            # ไม่มีใคร push กลับเข้าคิวให้เลย
            _dl_pending.push(vid)
        # เพลงที่พังแล้วไม่ลองใหม่อัตโนมัติ ไม่งั้นมันจะวนกินคิวทุกครั้งที่มีคนกดเลื่อน
        if _sep_state.get(vid, {}).get("status") != "failed":
            await _enqueue_sep(vid)
        if _lyr_state.get(vid, {}).get("status") != "failed":
            await _enqueue_lyr(vid)
        await _enqueue_best(vid)
        await _enqueue_words(vid)
    _dl_pending.bump()
    _sep_pending.bump()
    _lyr_pending.bump()
    _lyrfind_pending.bump()
    _words_pending.bump()
    _best_pending.bump()
    await _heavy.rethink()     # คนที่รอ GPU อยู่ต้องประเมินอันดับกันใหม่ด้วย
    _preempt_heavy()


SEARCH_MAX_SEC = SEP_MAX_SEC   # ผลค้นที่ยาวกว่านี้ (เมดเลย์/รวมเพลง/ไลฟ์ย้อนหลัง) ไม่ใช่เพลงเดียว -> ซ่อน
# ชื่อคลิป/ช่องที่ไม่ใช่เพลงให้ร้อง — ซ่อนเสมอแม้แขกพิมพ์คำนี้มาเอง (ผู้ใช้เลือก)
# ภาษาไทยไม่มีช่องว่างคั่นคำ: เลี่ยงคำสั้นที่ชนชื่อเพลงจริง เช่น "ฮา" (ฮาร์ท), "สอน" (สอนใจ), "แกล้ง" (แกล้งลืม)
_NOT_SONG_RE = re.compile(
    r"ออกกำลัง|แอโรบ[ิี][คก]|ฟิตเนส|ซุมบ้า|คาร์ดิโอ|โยคะ|พิลาทิส|ลดน้ำหนัก|ลดพุง|ลดไขมัน|เผาผลาญ"
    r"|กายบริหาร|บริหารร่างกาย|ยืดเหยียด"
    r"|\b(?:aerobics?|workouts?|exercises?|fitness|zumba|cardio|yoga|pilates|hiit)\b"
    r"|ตลก|ขำ|ฮา\s?ๆ|สุดฮา|ฮามาก|ฮาลั่น|ฮาก๊าก|คลิปฮา|พากย์ฮา|พากย์นรก|รวมคลิป|แกล้งคน|เดี่ยวไมโครโฟน|ทอล์[คก]โชว์"
    r"|😂|🤣|\b(?:comedy|funny|pranks?|lol)\b"
    r"|รีแอ็?ค|สอนร้อง|สอนเล่น|สอนกีตาร์|สอนเปียโน|สอนเต้น"
    r"|\b(?:reactions?|react(?:s|ing)? to|tutorial|how to (?:sing|play))\b"
    r"|สัมภาษณ์|เบื้องหลัง|\b(?:interview|behind the scenes?)\b",
    re.I)


def _is_song_clip(e: dict) -> bool:
    """ผลค้น (entry แบบ flat ของ yt-dlp) น่าจะเป็นเพลงให้ร้องไหม — ไลฟ์ที่ยังออกอากาศ/ยาวเกิน/ชื่อเข้า _NOT_SONG_RE = ไม่ใช่
    ไม่รู้ความยาว (ไม่ใช่ไลฟ์) ให้ผ่านไปก่อน"""
    if e.get("live_status") in ("is_live", "is_upcoming"):
        return False
    try:
        if float(e.get("duration") or 0) > SEARCH_MAX_SEC:
            return False
    except (TypeError, ValueError):
        pass
    text = f"{e.get('title') or ''} {e.get('uploader') or e.get('channel') or ''}"
    return not _NOT_SONG_RE.search(text)


def _search(q: str, n: int = 12, stats: dict | None = None) -> list[dict[str, Any]]:
    """ค้น YouTube แล้วกรองคลิปที่ไม่ใช่เพลงออก (_is_song_clip) — ดึงมาเผื่อ 2 เท่าให้ยังเหลือราว n
    stats (ถ้าส่งมา) ได้ "hidden" = จำนวนที่ซ่อนไป"""
    if not _HAS_YTDLP:
        return []
    opts = {
        "quiet": True, "no_warnings": True, "extract_flat": True,
        "skip_download": True, "noplaylist": True, "default_search": "ytsearch",
        "socket_timeout": 15,
        "extractor_args": {"youtube": {"player_client": ["web"]}},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n * 2}:{q}", download=False)
    out = []
    hidden = 0
    for e in (info or {}).get("entries", []) or []:
        if not e.get("id"):
            continue
        if not _is_song_clip(e):
            hidden += 1
            continue
        if len(out) >= n:
            continue
        out.append({
            "videoId": e["id"],
            "title": e.get("title") or e["id"],
            "channel": e.get("uploader") or e.get("channel") or "",
            "duration": e.get("duration"),
            "thumb": f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg",
        })
    if stats is not None:
        stats["hidden"] = hidden
    return out


_OEMBED_TTL = 3600.0
_oembed_cache: dict[str, tuple[float, dict | None]] = {}   # vid -> (เวลา, ข้อมูล | None=ปิดฝัง)


def _oembed(video_id: str) -> dict | None:
    """ข้อมูลคลิปจาก YouTube oEmbed (title/author_name) — ตอบ 401/403 = เจ้าของปิดฝัง -> None
    ต่อเน็ตไม่ได้/ผิดพลาดอื่น -> raise ให้คนเรียกตัดสินเอง · แคช 1 ชม. ยิงซ้ำไม่ถูกบล็อก"""
    import urllib.request, urllib.error
    hit = _oembed_cache.get(video_id)
    if hit and time.monotonic() - hit[0] < _OEMBED_TTL:
        return hit[1]
    url = ("https://www.youtube.com/oembed?format=json&url="
           f"https%3A//www.youtube.com/watch%3Fv%3D{video_id}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8")) if r.status == 200 else None
    except urllib.error.HTTPError:
        data = None
    if not isinstance(data, dict):
        data = None
    _oembed_cache[video_id] = (time.monotonic(), data)
    return data


def _embeddable(video_id: str) -> bool:
    """เช็คว่าเจ้าของคลิปเปิดให้ฝัง (embed) ไหม — oEmbed ตอบ 401/403 ถ้าปิด"""
    try:
        return _oembed(video_id) is not None
    except Exception:
        return True  # เช็คไม่ได้ ให้ผ่านไปก่อน เดี๋ยวจอหลักจัดการเอง


def _yt_info(video_id: str) -> dict[str, str]:
    """ชื่อจริง + ช่อง ของคลิป: คลังมีแล้วเอาจาก info.json ไม่ต้องยิงเน็ต / ยังไม่มีถาม oEmbed
    ได้ไม่ครบคืนค่าว่าง คนเรียกค่อย fallback เป็น videoId เอง"""
    if (_song_dir(video_id) / "video.mp4").is_file():
        m = _song_meta(video_id)
        return {"title": m["title"], "channel": m["uploader"]}
    try:
        o = _oembed(video_id) or {}
    except Exception:
        o = {}
    return {"title": " ".join(str(o.get("title") or "").split())[:200],
            "channel": " ".join(str(o.get("author_name") or "").split())[:100]}


def _yt_title(video_id: str) -> str:
    return _yt_info(video_id)["title"]


_PLACEHOLDER_RE = re.compile(r"^YouTube: [A-Za-z0-9_-]{11}$")


def _title_is_placeholder(title: Any, vid: str) -> bool:
    t = str(title or "").strip()
    return not t or t == vid or bool(_PLACEHOLDER_RE.match(t))


def _fix_history_titles(only_vid: str | None = None) -> bool:
    """ประวัติที่เก็บ "YouTube: <id>" (เพลงที่วางลิงก์ก่อนมีตัวดึงชื่อ) -> ชื่อจริงจาก info.json
    ทำเฉพาะเพลงที่โหลดเสร็จแล้ว (ชื่อจากคลังเชื่อถือได้) คืน True ถ้าแก้อะไรไป"""
    changed = False
    for e in room.history:
        vid = e.get("videoId")
        if e.get("source") != "yt" or not _vid_ok(vid) or (only_vid and vid != only_vid):
            continue
        if not _title_is_placeholder(e.get("title"), vid):
            continue
        if not (_song_dir(vid) / "video.mp4").is_file():
            continue
        t = _song_meta(vid)["title"]
        if t and t != e.get("title"):
            e["title"] = t
            changed = True
    if changed:
        print("[history] เปลี่ยนชื่อประวัติที่ค้างเป็น 'YouTube: <id>' ให้เป็นชื่อจริงแล้ว")
    return changed


def _annotate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        flags = list(ex.map(lambda r: _embeddable(r["videoId"]), results))
    for r, ok in zip(results, flags):
        r["embeddable"] = ok
    return sorted(results, key=lambda r: not r["embeddable"])


@app.get("/api/embeddable")
async def api_embeddable(videoId: str):
    if not _vid_ok(videoId):
        return JSONResponse({"error": "videoId ไม่ถูกต้อง"}, status_code=400)
    ok = await asyncio.to_thread(_embeddable, videoId)
    info = await asyncio.to_thread(_yt_info, videoId)     # ชื่อจริงตั้งแต่ตอนวางลิงก์ ไม่ใช่ "YouTube: <id>"
    return {"videoId": videoId, "embeddable": ok, "title": info["title"], "channel": info["channel"]}


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1)):
    if not _HAS_YTDLP:
        return JSONResponse({"error": "yt-dlp not installed", "results": []}, 200)
    try:
        st: dict = {}
        res = await asyncio.to_thread(_search, q, 12, st)
        res = await asyncio.to_thread(_annotate, res)
        if not res:
            print(f"[search] '{q}' -> 0 results (ซ่อนที่ไม่ใช่เพลง {st.get('hidden', 0)})")
        return {"results": res, "hidden": st.get("hidden", 0)}
    except Exception as exc:
        print(f"[search] '{q}' FAILED:\n{traceback.format_exc()}")
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}", "results": []}, 200)


def _demucs_version() -> str:
    try:
        from importlib.metadata import version
        return version("demucs")
    except Exception as exc:
        return f"not installed ({exc})"


# --- log จากฝั่งเบราว์เซอร์ -------------------------------------------
# จอหลักเป็น TV ไม่มีใครเปิด DevTools ดู error จึงส่งกลับมาให้เซิร์ฟเวอร์เก็บ
_client_log: list[dict] = []


def _printable(v: Any, n: int) -> str:
    return "".join(c for c in str(v if v is not None else "") if c.isprintable())[:n]


@app.post("/api/clientlog")
async def api_clientlog(request: Request):
    # ใครในวงแลนก็ยิงได้ -> เก็บแค่ tag/msg ตัดความยาว ไม่เก็บ dict ทั้งก้อนที่ส่งมา
    if not _same_origin(request.headers):
        return JSONResponse({"ok": False}, status_code=403)
    try:
        too_big = int(request.headers.get("content-length") or 0) > 64_000
    except ValueError:
        too_big = True
    if too_big:
        return JSONResponse({"ok": False}, status_code=413)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"ok": False}, status_code=400)
    entry = {"tag": _printable(body.get("tag") or "?", 40), "msg": _printable(body.get("msg"), 2000),
             "at": time.time()}
    _client_log.append(entry)
    del _client_log[:-50]
    print(f"[client] {entry['tag']}: {entry['msg']}")
    return {"ok": True}


@app.get("/api/clientlog")
def api_clientlog_get():
    return {"entries": _client_log}


def _lyr_health() -> dict:
    """สรุปสถานะเนื้อเพลง: มีกี่เพลง มาจากแหล่งไหนบ้าง ค้างคิวเท่าไร"""
    by_src: dict[str, int] = {}
    conf: dict[str, int] = {}
    nolyr = 0
    for vid in _dir_index():
        _, n, _, src, tsrc = _lyr_meta(vid)
        if not n:
            nolyr += (_song_dir(vid) / "lyrics.nolyr.json").is_file()
            continue
        by_src[src or "?"] = by_src.get(src or "?", 0) + 1
        ck = _chk_info(vid)
        lvl, _ = LC.confidence(
            src, tsrc,
            ck.get("score") if ck.get("verdict") not in ("", "unmeasurable", "reported") else None,
            ck.get("measuredBy") or "",
            measurable=ck.get("verdict") != "unmeasurable",
            defects=len(ck.get("defects") or []), version=int(ck.get("v") or 1), sparse=_lyr_sparse(vid))
        conf[lvl] = conf.get(lvl, 0) + 1
    return {
        "withLyrics": sum(by_src.values()),
        "bySource": dict(sorted(by_src.items(), key=lambda kv: -kv[1])),
        "queued": len(_lyr_pending),
        "order": _lyr_pending.order(),          # ลำดับจริงที่จะทำ = ลำดับคิวห้องตอนนี้
        "find": {"queued": len(_lyrfind_pending), "order": _lyrfind_pending.order(),
                 "noSrc": sorted(_lyr_nosrc)},  # เฟสที่ไม่ใช้ GPU
        "confidence": conf,
        "noLyrics": nolyr,
        "state": _lyr_state,
        "verify": {"queued": _verify_queue.qsize(), "state": _verify_state},
        "words": {"queued": len(_words_pending), "order": _words_pending.order(),
                  "state": _words_state},       # เวลารายตัวอักษร (โหมดคาราโอเกะ)
        "best": {"queued": len(_best_pending), "order": _best_pending.order(),
                 "state": _best_state},         # เลือกเนื้อดีที่สุดจากทุกแหล่ง
    }


@app.get("/api/health")
def health(search: int = 0):
    """เช็คสุขภาพระบบ — ใส่ ?search=1 ถ้าอยากทดสอบค้นหา YouTube จริง (ช้าหลายวินาที)"""
    # demucs 4.1 ดึง weights จาก huggingface (repo adefossez/HTDemucs) — ของเดิมเช็คที่
    # TORCH_HOME ซึ่งไม่เคยมีไฟล์ จึงรายงานว่าไม่ได้แคชตลอดทั้งที่แคชอยู่แล้ว
    _hf = Path(os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface"))
    _ckpts = [Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints",
              _hf / "hub", Path.home() / ".cache" / "huggingface" / "hub"]
    done = sum(1 for vid in _dir_index() if _has_stems(vid))
    info = {
        "ytdlp": _YTDLP_VER, "ffmpeg": bool(FFMPEG), "baseUrl": base_url(), "caBundle": _CA,
        "sep": {
            "demucs": _demucs_version(),
            "asrModel": os.environ.get("KARA_ASR_MODEL",
                                       "mlx-community/whisper-large-v3-turbo").rsplit("/", 1)[-1],
            "model": DEMUCS_MODEL,
            "device": _sep_device or "ยังไม่ได้ใช้",
            "modelCached": any(c.is_dir() and any(c.glob("*HTDemucs*")) or
                                  c.is_dir() and any(c.glob("*.th")) for c in _ckpts),
            "separated": done,
            "queued": len(_sep_pending),
            "order": _sep_pending.order(),
            "state": _sep_state,
        },
        "lyr": _lyr_health(),
        "dl": {"queued": len(_dl_pending), "order": _dl_pending.order(), "state": _dl_state},
        "heavyJob": list(_heavy_job) if _heavy_job else None,
        "faWorker": _fa_worker.status(),           # FA แบบโหลดโมเดลค้าง
        "warm": _warm_state,                       # อุ่นเครื่องตอนเปิดโปรแกรม (วินาทีต่อขั้น)
        "queueOrder": [q.get("videoId") for q in room.queue],
    }
    if search:
        try:
            info["sampleSearch"] = [r["title"] for r in _search("test", 3)]
        except Exception as exc:
            info["sampleSearch"] = f"{type(exc).__name__}: {exc}"
    return info


_meta_cache: dict[str, tuple[float, dict]] = {}


def _song_meta(vid: str) -> dict:
    """title/duration/uploader จาก info.json — แคชด้วย mtime
    (info.json เพลงละหลายร้อย KB ห้ามอ่านใหม่ทุก request)"""
    d = _song_dir(vid)
    ij = d / "info.json"
    try:
        mt = ij.stat().st_mtime
    except OSError:
        mt = 0.0
    hit = _meta_cache.get(vid)
    if hit and hit[0] == mt:
        return hit[1]
    meta = {"title": "", "duration": None, "uploader": "", "date": ""}
    if mt:
        try:
            j = json.loads(ij.read_text("utf-8"))
            meta = {"title": j.get("title") or "",
                    "duration": j.get("duration"),
                    "uploader": j.get("uploader") or j.get("channel") or "",
                    "date": str(j.get("upload_date") or "")}   # ปีบนการ์ด PU Match — เก็บแค่ส่วนที่ใช้ ไม่เก็บทั้งก้อน
        except Exception:
            pass
    if not meta["title"]:
        meta["title"] = _SUF_RE.sub("", d.name).strip() or vid   # ไม่มี info.json -> เอาชื่อโฟลเดอร์
    _meta_cache[vid] = (mt, meta)
    return meta


@app.get("/api/archive")
def api_archive(q: str = "", limit: int = 200):
    """เพลงที่โหลดเก็บไว้แล้ว + จำนวนครั้งที่ถูกสั่ง — เรียงตามความถี่
    ทุกเพลงในนี้กดแล้วเล่นได้ทันที ไม่ต้องรอโหลดหรือแยกเสียง"""
    plays: dict[str, int] = {}
    last: dict[str, float] = {}
    for e in room.history:
        v = e.get("videoId")
        if not v:
            continue
        plays[v] = plays.get(v, 0) + 1
        last[v] = max(last.get(v, 0.0), e.get("at") or 0.0)

    ql = q.lower().strip()
    out = []
    for vid, d in _dir_index().items():
        if not (d / "video.mp4").is_file():
            continue                       # ยังโหลดไม่เสร็จ
        m = _song_meta(vid)
        if ql and ql not in m["title"].lower() and ql not in m["uploader"].lower():
            continue
        _mt, lyr_n, _w, lyr_src, lyr_tsrc = _lyr_meta(vid)
        out.append({
            "source": "yt", "videoId": vid,
            "title": m["title"], "channel": m["uploader"], "duration": m["duration"],
            "thumb": f"/song/{vid}/cover.jpg",       # ปกในเครื่อง ไม่ต้องพึ่งอินเทอร์เน็ต
            "plays": plays.get(vid, 0), "lastAt": last.get(vid),
            "stems": _has_stems(vid),
            "lyrLines": lyr_n,
            "lyrKind": LC.kind(lyr_src, lyr_tsrc) if lyr_n else "",
        })
    out.sort(key=lambda r: (-r["plays"], -(r["lastAt"] or 0), r["title"]))
    return {"results": out[:limit], "total": len(out)}


# ===== 🃏 PU Match (ปัดหาเพลงบนรีโมท) =============================================
# สุ่มการ์ดจากทุกเพลงในเครื่อง (ถ่วงน้ำหนัก) — ไม่พอค่อยเติมจากผลค้น YouTube คำเดียว (SWIPE_YT_Q)
def _song_year(m: dict) -> int | None:
    d = m.get("date") or ""
    return int(d[:4]) if d[:4].isdigit() else None


def _archive_vids() -> list[str]:
    return [vid for vid, d in _dir_index().items() if (d / "video.mp4").is_file()]


SWIPE_YT_TTL = 1800.0
SWIPE_YT_Q = "เพลงใหม่ล่าสุด {year}"
_swipe_yt_cache: dict[str, tuple[float, list[dict]]] = {}


def _swipe_yt(q: str) -> list[dict]:
    """ผลค้น YouTube (เฉพาะคลิปที่ฝังได้) — แคช 30 นาที ไม่ยิงเน็ตทุกครั้งที่ปัด"""
    hit = _swipe_yt_cache.get(q)
    if hit and time.monotonic() - hit[0] < SWIPE_YT_TTL:
        return hit[1]
    res = [r for r in _annotate(_search(q, 20)) if r.get("embeddable") is not False]
    _swipe_yt_cache[q] = (time.monotonic(), res)
    return res


def _swipe_pick(seen: set[str], n: int) -> dict:
    busy = {it.get("videoId") for it in ([room.current] if room.current else []) + room.queue}
    plays: dict[str, int] = {}
    for e in room.history:
        v = e.get("videoId")
        if v:
            plays[v] = plays.get(v, 0) + 1

    # 1) เพลงในเครื่อง — สุ่มถ่วงน้ำหนัก (เคยถูกสั่ง / มีเนื้อ / มีไกด์ ได้ขึ้นบ่อยกว่า)
    pool = []
    for vid in _archive_vids():
        if vid in seen or vid in busy:
            continue
        m = _song_meta(vid)
        _mt, lyr_n, _w, _s, _t = _lyr_meta(vid)
        stems = _has_stems(vid)
        w = 1.0 + 0.5 * min(plays.get(vid, 0), 5) + (1.0 if lyr_n else 0.0) + (0.5 if stems else 0.0)
        pool.append((random.random() ** (1.0 / w), {
            "source": "yt", "videoId": vid, "title": m["title"], "channel": m["uploader"],
            "duration": m["duration"], "thumb": f"/song/{vid}/cover.jpg", "year": _song_year(m),
            "archived": True, "stems": stems, "lyrLines": lyr_n}))
    pool.sort(key=lambda x: -x[0])
    cards = [c for _k, c in pool[:n]]

    # 2) ไม่พอ -> เติมจาก YouTube
    yt_err = ""
    if len(cards) < n:
        taken = seen | busy | set(_dir_index()) | {c["videoId"] for c in cards}
        try:
            lst = list(_swipe_yt(SWIPE_YT_Q.format(year=time.localtime().tm_year)))
        except Exception as exc:
            lst, yt_err = [], f"{type(exc).__name__}: {exc}"
        random.shuffle(lst)
        for r in lst:
            if len(cards) >= n:
                break
            if r["videoId"] in taken:
                continue
            taken.add(r["videoId"])
            cards.append({"source": "yt", "videoId": r["videoId"], "title": r["title"],
                          "channel": r.get("channel") or "", "duration": r.get("duration"),
                          "thumb": r.get("thumb"), "year": None,
                          "archived": False, "embeddable": True})
    return {"cards": cards, "more": len(cards) >= n, "ytError": yt_err}


@app.post("/api/swipe")
async def api_swipe(request: Request):
    """การ์ดชุดถัดไปของ PU Match: body {seen: [videoId...], n}"""
    if not _same_origin(request.headers):
        return JSONResponse({"error": "คำขอข้ามเว็บ"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "ข้อมูลไม่ถูกต้อง"}, status_code=400)
    seen = {str(v) for v in (body.get("seen") or [])[-300:]} if isinstance(body.get("seen"), list) else set()
    try:
        n = max(1, min(int(body.get("n") or 10), 20))
    except (TypeError, ValueError):
        n = 10
    return await asyncio.to_thread(_swipe_pick, seen, n)


@app.get("/api/songinfo")
async def api_songinfo(videoId: str = ""):
    """สถานะเพลง "ก่อน" กดเพิ่มเข้าคิว (รีโมทให้เลือก เพิ่ม/ออก จากหน้านี้)
    ใช้ตัวเติมฟิลด์ชุดเดียวกับคิว ป้ายจึงตรงกันทุกที่ — ยกเว้นเพลงที่ยังไม่เคยเข้าไปป์ไลน์
    ตัวเติมฟิลด์จะเดาว่า "queued" ซึ่งไม่จริง (ยังไม่มีใครสั่ง) จึงแปลงเป็น "new" """
    if not _vid_ok(videoId):
        return JSONResponse({"error": "videoId ไม่ถูกต้อง"}, status_code=400)
    it: dict[str, Any] = {"source": "yt", "videoId": videoId}
    _dl_fields(it)
    _sep_fields(it)
    _lyr_fields(it)
    archived = it.get("dlStatus") == "ready"
    if not archived and videoId not in _dl_state:
        it["dlStatus"] = "new"
    if it.get("sepStatus") == "queued" and videoId not in _sep_state:
        it["sepStatus"] = "new"
    it["archived"] = archived
    # ชื่อจริงทุกกรณี: คลังมีแล้วจาก info.json / ยังไม่มีถาม oEmbed (ยังไม่ได้ก็ปล่อยให้รีโมทใช้ชื่อเดิม)
    info = await asyncio.to_thread(_yt_info, videoId)
    if info["title"]:
        it["title"] = info["title"]
    if info["channel"]:
        it["channel"] = info["channel"]
    return it


@app.get("/api/library")
def api_library(q: str = ""):
    """เพลงในโฟลเดอร์ songs/ — วางไฟล์ที่คุณมีสิทธิ์ใช้ลงไปได้เลย"""
    ql = q.lower().strip()
    out = []
    for f in sorted(SONGS.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in MEDIA_EXT:
            continue
        rel = f.relative_to(SONGS).as_posix()
        if rel.startswith("yt/"):
            continue  # อาร์ไคฟ์ที่โหลดจาก YouTube — ซ่อนจากไลบรารี
        if ql and ql not in rel.lower():
            continue
        out.append({
            "source": "local",
            "path": rel,
            "title": f.stem,
            "folder": f.parent.relative_to(SONGS).as_posix(),
            "audioOnly": f.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".ogg"},
            "sizeMB": round(f.stat().st_size / 1e6, 1),
        })
    return {"results": out[:200], "total": len(out)}


@app.get("/song/{vid}/{name}")
def song_file(vid: str, name: str):
    """ไฟล์ในอาร์ไคฟ์ อ้างด้วย videoId — เซิร์ฟเวอร์แปลงเป็นโฟลเดอร์จริงให้เอง
    URL จึงเป็น ASCII ล้วนและไม่เปลี่ยนแม้ตั้งชื่อเพลงใหม่"""
    from fastapi.responses import FileResponse
    if not _vid_ok(vid) or not (name in _SONG_FILES or _VTT_NAME.match(name) or _KEY_NAME.match(name)):
        return JSONResponse({"error": "not found"}, 404)
    f = (_song_dir(vid) / name).resolve()
    if not f.is_relative_to(DL_DIR.resolve()) or not f.is_file():
        return JSONResponse({"error": "not found"}, 404)
    return FileResponse(f)


@app.get("/media/yt/{vid}/{name}")
def media_yt_compat(vid: str, name: str):
    """URL แบบเก่าที่อาจค้างอยู่ในคิว/แคชของเครื่องลูก"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/song/{vid}/{name}", status_code=307)


@app.get("/media/{path:path}")
def media(path: str):
    from fastapi.responses import FileResponse
    f = (SONGS / path).resolve()
    if not f.is_relative_to(SONGS.resolve()) or not f.is_file():
        return JSONResponse({"error": "not found"}, 404)
    return FileResponse(f)


@app.get("/thumb/{video_id}")
def thumb(video_id: str):
    """ภาพปกผ่านเซิร์ฟเวอร์ (โหลดจาก i.ytimg แล้วแคชไว้) — เบราว์เซอร์ไม่ต้องเข้าอินเทอร์เน็ตตรง"""
    from fastapi.responses import FileResponse
    if not _vid_ok(video_id):
        return JSONResponse({"error": "no thumb"}, 404)
    path = THUMB_CACHE / f"{video_id}.jpg"
    if not path.is_file():
        import urllib.request, urllib.error
        try:
            url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=10).read()
            if len(data) > 2000 and b"<html" not in data[:200].lower():
                path.write_bytes(data)
            else:
                return JSONResponse({"error": "no thumb"}, 404)
        except Exception:
            return JSONResponse({"error": "no thumb"}, 404)
    return FileResponse(path)


@app.get("/tv/logo.png")
def tv_logo():
    from fastapi.responses import FileResponse
    f = _tv_logo()
    if not f.is_file():
        return JSONResponse({"error": "no logo"}, 404)
    return FileResponse(f, media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.get("/qr.png")
def qr_png():
    img = qrcode.make(f"{base_url()}/r")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def player_page(request: Request):
    """จอหลักเปิดได้เฉพาะเครื่องที่รันเซิร์ฟเวอร์ — หลายจอพร้อมกันจะแย่งเล่นเพลงกัน
    เครื่องอื่นเด้งไปหน้ารีโมทให้เลย"""
    from fastapi.responses import RedirectResponse
    if not _is_local(request.client.host if request.client else None):
        return RedirectResponse("/r", status_code=307)
    return HTMLResponse((BASE / "static" / "player.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


@app.get("/tv/{key}", response_class=HTMLResponse)
def tv_player_page(key: str):
    """ลิงก์จอหลักที่เปิดจากเครื่องไหนก็ได้ในวงแลน (เช่นทีวี) — ต้องมีรหัสใน .studio.json
    ไม่งั้นมือถือแขกคนไหนก็ยึดจอหลักได้ (จอใหม่ชนะเสมอ)"""
    from fastapi.responses import RedirectResponse
    if not _tv_key_ok(key):
        return RedirectResponse("/r", status_code=307)
    return HTMLResponse((BASE / "static" / "player.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


@app.get("/watch", response_class=HTMLResponse)
def watch_page():
    """📺 จอที่สอง: เปิดจากเครื่องไหนก็ได้ (ลิงก์อยู่ในตั้งค่ารีโมท) — ดูอย่างเดียว ปิดเสียงเป็นค่าเริ่มต้น
    ไม่ส่ง hello แบบจอหลัก จึงแย่งจอ/ข้ามเพลง/ทำเวลาเพี้ยนไม่ได้ ไม่ต้องมีรหัสเหมือน /tv/<รหัส>"""
    return HTMLResponse((BASE / "static" / "player.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


def _tv_key_ok(key: Any) -> bool:
    return isinstance(key, str) and bool(key) and hmac.compare_digest(key.lower(), _studio_cfg()["tv"].lower())


@app.get("/r", response_class=HTMLResponse)
def remote_page():
    return HTMLResponse((BASE / "static" / "remote.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


# ===== Studio: แก้เนื้อ / ปรับเวลาซับ / ดูสถานะและซ่อมทุกเพลงในเครื่อง =====
# เปิดได้ทุกเครื่องใน WiFi แต่ต้องใส่ PIN — เครื่องที่รันเซิร์ฟเวอร์ผ่านเลย (เหมือนจอหลัก)
_studio_cfg_cache: tuple[float, dict] | None = None
_pin_fail: dict[str, tuple[int, float]] = {}      # ip -> (ผิดติดกันกี่ครั้ง, ล็อกถึงเมื่อไร)
PIN_TRIES, PIN_LOCK_S = 5, 60.0


def _studio_cfg() -> dict:
    """อ่าน .studio.json (สร้าง PIN สุ่มครั้งแรก) — แก้ PIN ในไฟล์ได้เลยไม่ต้องรีสตาร์ท
    ตั้ง KARA_STUDIO_PIN ไว้ = ใช้ค่านั้นแทน"""
    global _studio_cfg_cache
    try:
        mt = STUDIO_FILE.stat().st_mtime
    except OSError:
        cfg = {"pin": f"{secrets.randbelow(10000):04d}", "secret": secrets.token_hex(16)}
        STUDIO_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
        mt = STUDIO_FILE.stat().st_mtime
    if not _studio_cfg_cache or _studio_cfg_cache[0] != mt:
        try:
            cfg = json.loads(STUDIO_FILE.read_text("utf-8"))
        except Exception:
            cfg = {}
        cfg.setdefault("secret", secrets.token_hex(16))
        cfg["pin"] = str(cfg.get("pin") or "0000")
        if not cfg.get("tv"):
            # รหัสลิงก์จอหลัก /tv/<รหัส> — สั้นพอพิมพ์ด้วยรีโมททีวีได้ แก้ในไฟล์ได้ (ลบทิ้ง = สุ่มใหม่)
            cfg["tv"] = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))
            try:
                STUDIO_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
                mt = STUDIO_FILE.stat().st_mtime
            except OSError:
                pass
        cfg["tv"] = str(cfg["tv"])
        # โดเมนสาธารณะจาก cloudflare.command (เช่น https://kara.example.com) — ว่าง = ใช้ IP ในวงแลน
        pub = str(cfg.get("publicUrl") or "").strip().rstrip("/")
        cfg["publicUrl"] = pub if re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", pub) else ""
        _studio_cfg_cache = (mt, cfg)
    cfg = dict(_studio_cfg_cache[1])
    if os.environ.get("KARA_STUDIO_PIN"):
        cfg["pin"] = os.environ["KARA_STUDIO_PIN"].strip()
    return cfg


def _drop_stale_public_url() -> None:
    """publicUrl ที่เป็นลิงก์ทดลองของ Cloudflare (quick tunnel) ใช้ข้ามการรีสตาร์ทไม่ได้ -> ล้างในไฟล์ (รักษาฟิลด์อื่น)"""
    try:
        cfg = json.loads(STUDIO_FILE.read_text("utf-8"))
    except Exception:
        return
    pub = str(cfg.get("publicUrl") or "")
    if pub.rstrip("/").endswith(".trycloudflare.com"):
        cfg["publicUrl"] = ""
        _write_json_atomic(STUDIO_FILE, cfg)
        print(f"[cloudflare] ล้างลิงก์ทดลองเก่า {pub}")


def _studio_token() -> str:
    c = _studio_cfg()        # เปลี่ยน PIN = cookie เก่าทุกเครื่องใช้ไม่ได้ทันที
    return hashlib.sha256(f'{c["secret"]}:{c["pin"]}'.encode()).hexdigest()


def _studio_guard(request: Request) -> None:
    # คำสั่งที่เปลี่ยนข้อมูลต้องมาจากหน้า Studio ของเราเอง: เครื่องตัวเองผ่าน PIN ได้เลย และ request.json()
    # ไม่สน Content-Type -> เว็บอื่นที่เปิดอยู่ในเครื่องนี้ยิง POST text/plain สั่ง drop-edit/redl แทนได้
    if request.method not in ("GET", "HEAD") and not _same_origin(request.headers):
        raise HTTPException(status_code=403, detail="คำขอข้ามเว็บ — ไม่อนุญาต")
    if _is_local(request.client.host if request.client else None) \
            and _host_is_local_name(request.headers.get("host")):
        return
    if hmac.compare_digest(request.cookies.get("studio", ""), _studio_token()):
        return
    raise HTTPException(status_code=401, detail="ต้องใส่ PIN")


def _studio_vid(vid: str) -> Path:
    if not _vid_ok(vid):
        raise HTTPException(status_code=400, detail="videoId ไม่ถูกต้อง")
    d = _song_dir(vid)
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="ไม่มีเพลงนี้ในเครื่อง")
    return d


def _studio_item(vid: str, d: Path, plays: dict[str, int], qpos: dict[str, int]) -> dict:
    """สถานะครบทุกด้านของ 1 เพลง — ใช้ตัวเติมฟิลด์ชุดเดียวกับคิว ป้ายจึงตรงกันทุกหน้า"""
    it: dict[str, Any] = {"source": "yt", "videoId": vid}
    _dl_fields(it)
    _sep_fields(it)
    _lyr_fields(it)
    _fix_fields(it)
    # ตัวเติมฟิลด์เดา "queued" ให้เพลงที่ไม่มีใครสั่ง — ในหน้านี้ต้องบอกตามจริงว่า "ว่าง"
    if it.get("dlStatus") == "queued" and vid not in _dl_state and not _dl_pending.has(vid):
        it["dlStatus"] = "idle"
    if it.get("sepStatus") == "queued" and vid not in _sep_state and not _sep_pending.has(vid):
        it["sepStatus"] = "idle"
    m = _song_meta(vid)
    ck = _chk_info(vid)
    lyr_mt = _lyr_meta(vid)[0]
    offp = d / "lyrics.offset.json"
    off_mt = offp.stat().st_mtime if offp.is_file() else 0.0
    shift = float(ck.get("shift") or 0.0)
    ck_at = float(ck.get("at") or 0.0)
    it.update({
        "title": m["title"], "channel": m["uploader"], "duration": m["duration"],
        "thumb": f"/song/{vid}/cover.jpg" if (d / "cover.jpg").is_file() else f"/thumb/{vid}",
        "plays": plays.get(vid, 0),
        "queuePos": qpos.get(vid),
        "edited": (LYRICS_IN / f"{vid}.json").is_file(),
        "reports": sum(1 for r in _read_reports(vid) if not r.get("done")),
        "hasVideo": (d / "video.mp4").is_file(),
        "hasVocals": _has_stems(vid),
        "words": _words_brief(vid),
        "best": _best_brief(vid),
        "lang": _song_lang(vid)[0], "langBy": _song_lang(vid)[1],
        "check": ({"verdict": ck.get("verdict") or "", "score": ck.get("score"),
                   "shift": shift, "reports": len(ck.get("reports") or []),
                   "measuredBy": ck.get("measuredBy") or "", "at": ck_at, "v": int(ck.get("v") or 1),
                   "defects": ck.get("defects") or []} if ck else None),
        # คำแนะนำเลื่อนใช้ได้เฉพาะตอนผลตรวจ "ใหม่กว่า" เนื้อและ offset ปัจจุบัน
        # เลื่อนเกิน 10 วิ = แทบไม่ใช่เวลาเลื่อน แต่เป็นเนื้อผิดเพลง/ผิดเวอร์ชัน -> ไม่แนะนำ
        "shiftOk": bool(ck and 0.3 <= abs(shift) <= 10 and lyr_mt and ck_at >= lyr_mt - 1
                        and off_mt <= ck_at + 1),
    })
    return it


def _best_brief(vid: str) -> dict | None:
    """ผลเลือกเนื้ออัตโนมัติของเพลงนี้ สำหรับ Studio (None = ยังไม่เคยทำ)"""
    st = _best_state.get(vid, {})
    rec = _best_rec(vid)
    if not st and not rec:
        return None
    j = _read_lyr(vid) or {}
    applied = bool(j.get("best")) and _lyr_hash(j) == rec.get("out")
    rf = rec.get("refine") or {}
    return {"status": st.get("status") or "done", "error": st.get("error") or "",
            "action": rec.get("action") or "", "reason": rec.get("reason") or "", "at": rec.get("at"),
            "applied": applied, "partial": bool(rec.get("partial")),
            "refine": {"segments": len(rf.get("segments") or []), "repaired": len(rf.get("repaired") or []),
                       "uncertain": rf.get("uncertain") or [], "note": rf.get("note") or "",
                       "mode": rf.get("mode") or ""} if rf else None}


def _words_brief(vid: str) -> dict:
    wm = _words_meta(vid)
    out = {"status": _words_status(vid), "nk": wm["nk"], "n": wm["n"]}
    err = _words_state.get(vid, {}).get("error")
    if err:
        out["error"] = err
    return out


def _studio_ctx() -> tuple[dict[str, int], dict[str, int]]:
    plays: dict[str, int] = {}
    for e in room.history:
        v = e.get("videoId")
        if v:
            plays[v] = plays.get(v, 0) + 1
    qpos: dict[str, int] = {}
    if room.current and room.current.get("videoId"):
        qpos[room.current["videoId"]] = 0
    for i, q in enumerate(room.queue):
        if q.get("videoId"):
            qpos.setdefault(q["videoId"], i + 1)
    return plays, qpos


LINE_VOICES = (2, 3, "bg")     # เสียงของบรรทัด (ไม่มี = เสียงหลัก): คนร้องคนที่ 2/3, คอรัสทั้งบรรทัด


def _voice_of(v: Any) -> int | str | None:
    """ค่า v ต่อบรรทัดที่รับได้ (ไม่รู้จัก = เสียงหลัก) — ตรงกับ gen_lyrics.VOICES และจอ (VOICE_CLS)"""
    if v in ("2", "3"):
        v = int(v)
    return v if v in LINE_VOICES else None


def _clean_edit_lines(raw: Any) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=400, detail="ต้องมีเนื้ออย่างน้อย 1 บรรทัด")
    if len(raw) > 3000:
        raise HTTPException(status_code=400, detail="บรรทัดเยอะเกินไป")
    out = []
    for i, l in enumerate(raw):
        try:
            t = float(l["t"])
            d = float(l.get("d") or 3.0)
            x = " ".join(str(l["x"]).split())[:300]
            if not (math.isfinite(t) and math.isfinite(d)):
                raise ValueError("nan")
            t, d = round(t, 2), round(max(0.3, min(30.0, d)), 2)
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"บรรทัดที่ {i + 1} ข้อมูลไม่ครบ")
        if t < 0 or not x:
            raise HTTPException(status_code=400, detail=f"บรรทัดที่ {i + 1} เวลาติดลบหรือไม่มีข้อความ")
        ln = {"t": t, "d": d, "x": x}
        v = _voice_of(l.get("v"))
        if v:
            ln["v"] = v
        out.append(ln)
    out.sort(key=lambda l: l["t"])           # เรียงให้เสมอ จอหลักค้นแบบ binary search
    return out


def _write_json_atomic(f: Path, obj: Any) -> None:
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


EDITS_KEEP = 20


def _backup_lyrics(d: Path, obj: dict | None) -> None:
    """สำรองเนื้อชุดหนึ่งลง lyrics.edits/<YYYYmmdd-HHMMSS-mmm>.json (เห็นใน 🕘 ประวัติของ Studio เก็บ 20 รุ่น)
    ใช้ทุกทางที่เนื้อจะถูกแทนที่หรือลบ: บันทึกใน Studio / ระบบเลือกเนื้ออัตโนมัติ / โหลดเนื้อใหม่ / เลิกใช้เนื้อที่แก้เอง
    - อ่านนาฬิกาครั้งเดียว ชื่อชนกัน (สำรองสองครั้งในมิลลิวินาทีเดียว) เลื่อนไปมิลลิวินาทีถัดไป -> ไม่ทับ และยังเรียงตามเวลา
    - เหมือนฉบับล่าสุดที่สำรองไว้เป๊ะ = ไม่ต้องเก็บซ้ำ (ไม่เปลืองช่องประวัติ)"""
    if not obj or not obj.get("lines") or not d.is_dir():
        return
    ed = d / "lyrics.edits"
    ed.mkdir(exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False)
    olds = sorted(ed.glob("*.json"))
    if olds:
        try:
            if olds[-1].read_text("utf-8") == body:
                return
        except OSError:
            pass
    ms = int(time.time() * 1000)
    while True:
        f = ed / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ms / 1000))}-{ms % 1000:03d}.json"
        if not f.exists():
            break
        ms += 1
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, f)
    for old in sorted(ed.glob("*.json"))[:-EDITS_KEEP]:
        old.unlink(missing_ok=True)


def _write_edit(vid: str, d: Path, lines: list[dict], offset: float | None, picked: str = "") -> None:
    """บันทึกเนื้อที่แก้ใน Studio
    - สำรองของเดิมไว้ใน lyrics.edits/ (ย้อนกลับได้ 20 รุ่น)
    - เขียนสำเนาไว้ lyrics-in/<vid>.json ด้วย -> โหลดเนื้อใหม่/สร้างใหม่ทั้งคลังก็ยังได้ฉบับนี้"""
    cur = d / "lyrics.json"
    old = None
    if cur.is_file():
        try:
            old = json.loads(cur.read_text("utf-8"))
        except Exception:
            old = None
    _backup_lyrics(d, old)
    dur = float((old or {}).get("duration") or _song_meta(vid)["duration"] or 0.0)
    out = {"v": 1, "videoId": vid, "lang": "th", "engine": "PU KARAOKE Studio",
           "src": "manual-edit", "timeSrc": "self", "duration": round(dur, 2),
           "lines": lines, "editedAt": int(time.time())}
    if picked:                          # เลือกแหล่งจากหน้าคิวของ Studio — จำไว้ว่ามาจากไหน
        out["picked"] = picked
    _write_json_atomic(cur, out)
    LYRICS_IN.mkdir(exist_ok=True)
    _write_json_atomic(LYRICS_IN / f"{vid}.json", out)
    # ผลตรวจ/หมุดเก่าพูดถึงเนื้อชุดก่อน — ค้างไว้จะขึ้นป้ายผิด
    for name in ("lyrics.check.json", "lyrics.nolyr.json"):
        (d / name).unlink(missing_ok=True)
    if offset is not None:
        _set_lyr_offset(vid, offset)
    _lyr_cache.pop(vid, None)
    _chk_cache.pop(vid, None)
    _lyr_state.pop(vid, None)
    _lyr_nosrc.discard(vid)


def _autotime(vid: str, texts: list[str]) -> dict:
    """จับเวลาข้อความที่แก้แล้ว ด้วย word timing ที่มีอยู่แล้ว — ไม่แตะ GPU
    ลำดับไม้บรรทัด: ผลถอดเสียงร้อง (แคช whisper) ก่อน แล้วค่อย auto-caption ของ YouTube"""
    import gen_lyrics as G          # import เบา (ASR โหลดตอนถอดเสียงจริงเท่านั้น)
    d = _song_dir(vid)
    dur = float(_song_meta(vid)["duration"] or 0.0) or G.song_duration(d)
    rulers: list[tuple[str, list[dict]]] = []
    seg_files = [G.segment_cache_path(vid)] + sorted(SEG_CACHE.glob(f"{vid}.*.json")) \
        + [SEG_CACHE / f"{vid}.json"]
    for f in seg_files:
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        words = [w for sg in data.get("segs") or [] for w in (sg.get("words") or [])
                 if w.get("start") is not None and w.get("end") is not None
                 and (w.get("word") or "").strip()]
        if words:
            rulers.append(("asr", words))
            break
    auto = d / "auto.th.vtt"
    if auto.is_file():
        w = LS.words_from_auto_vtt(auto)
        if w:
            rulers.append(("auto-cap", w))
    if not rulers:
        return {"need": "asr"}
    # ขั้นตอนเดียวกับ G.time_with แต่ไม่ตัดทิ้งเมื่อ align_ok ไม่ผ่าน — ใน Studio คนเป็นคนตัดสิน
    # (ลองฟังในพรีวิวก่อนบันทึกได้) จึงส่งผลที่ดีที่สุดกลับไปพร้อมบอกว่าผ่านเกณฑ์ไหม
    best = None
    for by, words in rulers:
        chunks = G.make_chunks([{"start": words[0]["start"], "end": words[-1]["end"],
                                 "text": "", "words": words}])
        anchors = G.align(chunks, texts, dur)
        starts = G.timings_for_lines(texts, anchors, dur)
        durs = []
        for i, st in enumerate(starts):
            nxt = starts[i + 1] if i + 1 < len(starts) else (dur if dur > st else st + 6.0)
            durs.append(LS.line_dur(st, nxt))
        covered = {a["line"] for a in anchors}
        tot = sum(len(G.norm_chars(l)) for l in texts)
        cov = 100.0 * sum(len(G.norm_chars(l)) for i, l in enumerate(texts) if i in covered) / tot if tot else 0.0
        res = {"lines": [{"t": round(t, 2), "d": d_, "x": x} for t, d_, x in zip(starts, durs, texts)],
               "by": by, "cov": round(cov, 1), "ok": G.align_ok(starts, durs, cov, dur)}
        if res["ok"]:
            return res
        if best is None or res["cov"] > best["cov"]:
            best = res
    return best


@app.get("/studio", response_class=HTMLResponse)
def studio_page():
    return HTMLResponse((BASE / "static" / "studio.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store"})


@app.post("/api/studio/login")
async def studio_login(request: Request):
    if not _same_origin(request.headers):
        return JSONResponse({"ok": False, "why": "คำขอข้ามเว็บ — ไม่อนุญาต"}, status_code=403)
    ip = request.client.host if request.client else "?"
    n, until = _pin_fail.get(ip, (0, 0.0))
    now = time.monotonic()
    if until > now:
        return JSONResponse({"ok": False, "why": f"ใส่ผิดหลายครั้ง รออีก {int(until - now) + 1} วินาที"},
                            status_code=429)
    try:
        pin = str((await request.json()).get("pin") or "").strip()
    except Exception:
        pin = ""
    if not hmac.compare_digest(pin, _studio_cfg()["pin"]):
        n += 1
        _pin_fail[ip] = (0, now + PIN_LOCK_S) if n >= PIN_TRIES else (n, 0.0)
        return JSONResponse({"ok": False, "why": "PIN ไม่ถูกต้อง"}, status_code=401)
    _pin_fail.pop(ip, None)
    r = JSONResponse({"ok": True})
    r.set_cookie("studio", _studio_token(), max_age=30 * 86400, httponly=True, samesite="lax",
                 secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return r


@app.get("/api/studio/songs")
async def studio_songs(request: Request):
    _studio_guard(request)
    plays, qpos = _studio_ctx()
    items = sorted(_dir_index().items())
    # อ่านไฟล์ 2-3 ไฟล์ต่อเพลงทั้งคลัง -> ทำใน thread ไม่ให้จอทีวี/รีโมทสะดุดระหว่างนั้น
    out = await asyncio.to_thread(lambda: [_studio_item(vid, d, plays, qpos) for vid, d in items])
    return {"songs": out, "archiveRev": room.archive_rev}


@app.get("/api/studio/song/{vid}")
async def studio_song(vid: str, request: Request):
    _studio_guard(request)
    d = _studio_vid(vid)
    plays, qpos = _studio_ctx()
    lyr = None
    if (d / "lyrics.json").is_file():
        try:
            lyr = json.loads((d / "lyrics.json").read_text("utf-8"))
        except Exception:
            lyr = None
    edits = []
    for f in sorted((d / "lyrics.edits").glob("*.json"), reverse=True) if (d / "lyrics.edits").is_dir() else []:
        try:
            j = json.loads(f.read_text("utf-8"))
            edits.append({"ts": f.stem, "src": j.get("src") or "", "n": len(j.get("lines") or [])})
        except Exception:
            continue
    nolyr = None
    if (d / "lyrics.nolyr.json").is_file():
        try:
            nolyr = json.loads((d / "lyrics.nolyr.json").read_text("utf-8")).get("why")
        except Exception:
            nolyr = ""
    return {
        "item": _studio_item(vid, d, plays, qpos),
        "lyrics": lyr,
        "offset": _lyr_offset(vid),
        "check": _chk_info(vid) or None,
        "nolyr": nolyr,
        "edits": edits,
        "files": {k: (d / k).is_file() for k in ("video.mp4", "audio.m4a", "vocals.m4a",
                                                 "auto.th.vtt", "sub.th.vtt")},
        "asrCache": _asr_cached(vid),
        "manual": {k: (LYRICS_IN / f"{vid}.{k}").is_file() for k in ("json", "lrc", "txt")},
        "fa": {"ready": _fa_ready(), "cached": _fa_cached(vid)},
        "reports": _read_reports(vid),
        "words": _words_detail(vid, d),
    }


def _words_detail(vid: str, d: Path) -> dict:
    """สถานะ + k ของทุกบรรทัด (ไว้พรีวิวโหมดคาราโอเกะ/ขีดเวลาคำใน Studio)"""
    out = _words_brief(vid)
    if _words_meta(vid)["ok"]:
        try:
            w = json.loads((d / "lyrics.words.json").read_text("utf-8"))
            out.update({"k": w.get("k") or [], "conf": w.get("conf") or [], "at": w.get("at"),
                        "audio": w.get("audio") or ""})
        except Exception:
            pass
    return out


@app.post("/api/studio/song/{vid}/reports")
async def studio_reports(vid: str, request: Request):
    """ติ๊ก "แก้แล้ว" / เปิดใหม่ ให้รายงานจากรีโมท — {id, done} หรือ {all_done:true}
    อ้างด้วย id ไม่ใช่เวลา: แจ้งติดกันเร็ว ๆ เวลาห่างกันไม่ถึงมิลลิวินาที จะติ๊กโดนหลายอัน"""
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    reps = _read_reports(vid)
    if body.get("all_done"):
        for r in reps:
            r["done"] = True
    else:
        rid = str(body.get("id") or "")
        hit = [r for r in reps if rid and r.get("id") == rid]
        if not hit:
            raise HTTPException(status_code=404, detail="ไม่มีรายงานนี้")
        for r in hit:
            r["done"] = bool(body.get("done", True))
    await asyncio.to_thread(_write_reports, vid, reps)
    room.archive_rev += 1
    await room.broadcast()             # ให้ Studio เครื่องอื่นอัปเดตตัวเลข 🚩
    return {"ok": True, "open": sum(1 for r in reps if not r.get("done"))}


@app.get("/api/studio/song/{vid}/edit/{ts}")
async def studio_edit_version(vid: str, ts: str, request: Request):
    _studio_guard(request)
    d = _studio_vid(vid)
    if not re.fullmatch(r"[0-9-]{10,24}", ts):
        raise HTTPException(status_code=400, detail="ชื่อรุ่นไม่ถูกต้อง")
    f = d / "lyrics.edits" / f"{ts}.json"
    if not f.is_file():
        raise HTTPException(status_code=404, detail="ไม่มีรุ่นนี้")
    return json.loads(f.read_text("utf-8"))


@app.put("/api/studio/song/{vid}/lyrics")
async def studio_save(vid: str, request: Request):
    _studio_guard(request)
    d = _studio_vid(vid)
    body = await request.json()
    lines = _clean_edit_lines(body.get("lines"))
    off = body.get("offset")
    if off is not None:
        off = _finite(off, -LYR_OFFSET_MAX, LYR_OFFSET_MAX)
        if off is None:
            raise HTTPException(status_code=400, detail="offset ไม่ใช่ตัวเลข")
    picked = " ".join(str(body.get("picked") or "").split())[:120]
    await asyncio.to_thread(_write_edit, vid, d, lines, off, picked)
    print(f"[studio] {vid} บันทึกเนื้อที่แก้เอง {len(lines)} บรรทัด"
          f"{f' offset {off:+.2f}s' if off else ''}")
    room.archive_rev += 1
    _words_state.pop(vid, None)
    await _enqueue_words(vid)          # แก้ข้อความ -> เวลารายคำชุดเก่าใช้ไม่ได้ (แก้แค่เวลา = ใช้ต่อได้ ไม่ทำซ้ำ)
    await room.broadcast()             # เพลงนี้กำลังเล่นอยู่ -> จอหลักโหลดเนื้อใหม่ทันที
    mt = _lyr_meta(vid)[0]
    # Studio จำ URL นี้ไว้ — การบันทึกของตัวเองจะได้ไม่ถูกมองว่า "มีงานเบื้องหลังเขียนเนื้อทับ"
    return {"ok": True, "n": len(lines), "lyricsUrl": f"/song/{vid}/lyrics.json?v={int(mt * 1000)}" if mt else ""}


@app.get("/api/studio/tv")
async def studio_tv_get(request: Request):
    _studio_guard(request)
    return {"tv": _tv_public(room.tv), "default": _clean_tv({}), "chips": list(TV_CHIPS)}


@app.post("/api/studio/tv")
async def studio_tv_set(request: Request):
    """ตั้งค่าจอหลัก — ส่งมาเฉพาะค่าที่เปลี่ยนก็ได้ / {"reset": true} = คืนค่าเริ่มต้น (รูปไม่ถูกลบ)"""
    _studio_guard(request)
    body = await request.json()
    room.tv = _clean_tv({}) if body.get("reset") else _clean_tv(body, room.tv)
    await asyncio.to_thread(_write_json_atomic, TV_FILE, room.tv)
    await room.broadcast()
    return {"tv": _tv_public(room.tv)}


TV_LOGO_MAX = 10 * 1024 * 1024
TV_LOGO_PX = 512


def _save_logo(raw: bytes) -> None:
    """รูปอะไรก็ได้ -> ครอปกลางเป็นจัตุรัส 512x512 PNG (เก็บพื้นใส) — เปิดไม่ได้ = ไม่ใช่รูป"""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        raise HTTPException(status_code=400, detail="ไฟล์นี้ไม่ใช่รูปที่เปิดได้")
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGBA")
    side = min(im.size)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((TV_LOGO_PX, TV_LOGO_PX), Image.LANCZOS)
    TV_DIR.mkdir(exist_ok=True)
    tmp = TV_DIR / "logo.tmp.png"
    im.save(tmp, format="PNG", optimize=True)
    os.replace(tmp, _tv_logo())


@app.put("/api/studio/tv/logo")
async def studio_tv_logo_put(request: Request):
    _studio_guard(request)
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="ไม่มีไฟล์")
    if len(raw) > TV_LOGO_MAX:
        raise HTTPException(status_code=413, detail="รูปใหญ่เกิน 10 MB")
    await asyncio.to_thread(_save_logo, raw)
    room.tv = _clean_tv({"logo": True}, room.tv)          # อัปแล้วโชว์เลย ไม่ต้องไปกดเปิดอีกที
    await asyncio.to_thread(_write_json_atomic, TV_FILE, room.tv)
    await room.broadcast()
    return {"tv": _tv_public(room.tv)}


@app.delete("/api/studio/tv/logo")
async def studio_tv_logo_del(request: Request):
    _studio_guard(request)
    _tv_logo().unlink(missing_ok=True)
    room.tv = _clean_tv({"logo": False}, room.tv)
    await asyncio.to_thread(_write_json_atomic, TV_FILE, room.tv)
    await room.broadcast()
    return {"tv": _tv_public(room.tv)}


@app.post("/api/studio/song/{vid}/offset")
async def studio_offset(vid: str, request: Request):
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    off = _finite(body.get("offset") or 0.0, -LYR_OFFSET_MAX, LYR_OFFSET_MAX)
    if off is None:
        raise HTTPException(status_code=400, detail="offset ไม่ใช่ตัวเลข")
    off = await asyncio.to_thread(_set_lyr_offset, vid, off)
    await room.broadcast()
    return {"ok": True, "offset": off}


# ===== ✂️ ตัดต่อ: จุดเริ่ม/จบรายเพลง + 🎬 คอมโบ =====
COMBO_MAX_ITEMS = 50
_combo_db: tuple[float, list[dict]] = (-1.0, [])


def _combos() -> list[dict]:
    """combos.json = [{id, name, items: [{videoId, title, start?, end?, fadeIn?, fadeOut?}], at}] — แคชตาม mtime"""
    global _combo_db
    try:
        mt = COMBOS_FILE.stat().st_mtime
    except OSError:
        mt = 0.0
    if mt == _combo_db[0]:
        return _combo_db[1]
    out: list[dict] = []
    if mt:
        try:
            raw = json.loads(COMBOS_FILE.read_text("utf-8"))
            out = [c for c in (_clean_combo(r) for r in (raw if isinstance(raw, list) else [])) if c]
        except Exception as e:
            print(f"[combo] อ่าน combos.json ไม่ได้: {e}")
    _combo_db = (mt, out)
    return out


def _clean_combo(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    cid = str(raw.get("id") or "")
    if not re.fullmatch(r"[a-z0-9]{6,16}", cid):
        cid = uuid.uuid4().hex[:8]
    name = " ".join(str(raw.get("name") or "").split())[:40] or "คอมโบใหม่"
    items = []
    for it in (raw.get("items") if isinstance(raw.get("items"), list) else [])[:COMBO_MAX_ITEMS]:
        if not isinstance(it, dict) or not _vid_ok(it.get("videoId")):
            continue
        vid = it["videoId"]
        title = " ".join(str(it.get("title") or "").split())[:200] or vid
        items.append({"videoId": vid, "title": title, **_clean_clip(it, _dur_of(vid))})
    return {"id": cid, "name": name, "items": items, "at": int(raw.get("at") or time.time())}


def _combos_save(db: list[dict]) -> None:
    global _combo_db
    _write_json_atomic(COMBOS_FILE, db)
    _combo_db = (COMBOS_FILE.stat().st_mtime, db)


def _combo_get(cid: str) -> dict | None:
    return next((c for c in _combos() if c["id"] == cid), None)


def _combo_public(c: dict) -> dict:
    """ข้อมูลที่รีโมทเห็น: ชื่อ เพลง ความยาวรวมหลังตัด (ว่าง = ต้นคลิป/ท้ายคลิป)"""
    items, total = [], 0.0
    for it in c["items"]:
        vid = it["videoId"]
        dur = float(_song_meta(vid)["duration"] or 0)
        s, e = it.get("start") or 0.0, it.get("end")
        total += max(0.0, (e if e is not None else dur) - s)
        items.append({"videoId": vid, "title": it["title"],
                      "thumb": f"/song/{vid}/cover.jpg" if (_song_dir(vid) / "cover.jpg").is_file() else f"/thumb/{vid}"})
    return {"id": c["id"], "name": c["name"], "n": len(items), "total": round(total), "items": items}


@app.get("/api/combos")
async def api_combos():
    return {"combos": await asyncio.to_thread(lambda: [_combo_public(c) for c in _combos() if c["items"]])}


@app.get("/api/studio/combos")
async def studio_combos(request: Request):
    _studio_guard(request)
    return {"combos": _combos()}


@app.post("/api/studio/combos")
async def studio_combo_save(request: Request):
    """สร้าง/แก้คอมโบทั้งก้อน (id ว่างหรือไม่มีในไฟล์ = สร้างใหม่)"""
    _studio_guard(request)
    body = await request.json()
    c = await asyncio.to_thread(_clean_combo, body)
    if not c:
        raise HTTPException(status_code=400, detail="ข้อมูลคอมโบไม่ถูกต้อง")
    # คงลำดับเดิมของคอมโบที่แก้ (ของใหม่ต่อท้าย)
    cur = _combos()
    idx = next((i for i, x in enumerate(cur) if x["id"] == c["id"]), len(cur))
    db = [x for x in cur if x["id"] != c["id"]]
    db.insert(min(idx, len(db)), c)
    await asyncio.to_thread(_combos_save, db)
    room.archive_rev += 1
    await room.broadcast()
    return {"combo": c}


@app.delete("/api/studio/combos/{cid}")
async def studio_combo_delete(cid: str, request: Request):
    _studio_guard(request)
    db = [x for x in _combos() if x["id"] != cid]
    await asyncio.to_thread(_combos_save, db)
    room.archive_rev += 1
    await room.broadcast()
    return {"ok": True}


@app.get("/api/studio/song/{vid}/clip")
async def studio_clip_info(vid: str, request: Request):
    """ข้อมูลที่แท็บ ✂️ ใช้วาดแทร็กของเพลงหนึ่ง: ค่าที่ตั้งเอง + ค่าอัตโนมัติ + ไฟล์สื่อ/เนื้อ"""
    _studio_guard(request)
    d = _studio_vid(vid)
    mt = _lyr_meta(vid)[0]
    a = _auto_span(vid, room.tv)
    # คลื่นเสียงร้อง 10 จุด/วิ จากแคชแผนที่เสียงร้อง (_va) — มือถือ/iPad ไม่ต้องโหลด+ถอดรหัส vocals.m4a ทั้งไฟล์เอง
    # (ครั้งแรกของเพลงคำนวณใน thread 2-4 วิ ไม่มี vocals = None แล้ว Studio ถอดรหัสเองแบบเดิม)
    env = None
    try:
        import vocal_activity as VA
        env = VA.envelope(await asyncio.to_thread(_va_for, vid))
    except Exception as exc:
        print(f"[clip] {vid} คลื่นเสียงไม่ได้: {type(exc).__name__}: {exc}")
    return {"videoId": vid, "title": _song_meta(vid)["title"] or vid,
            "duration": _song_meta(vid)["duration"], "trim": _trim(vid),
            "auto": {"start": a[0], "end": a[1]}, "lyrOffset": _lyr_offset(vid),
            "lyricsUrl": f"/song/{vid}/lyrics.json?v={int(mt * 1000)}" if mt else None,
            "video": (d / "video.mp4").is_file(), "audio": (d / "audio.m4a").is_file(),
            "vocals": (d / "vocals.m4a").is_file(), "env": env}


@app.post("/api/studio/song/{vid}/trim")
async def studio_trim(vid: str, request: Request):
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    t = await asyncio.to_thread(_set_trim, vid, body)
    await room.broadcast()             # เพลงที่เล่นอยู่ได้จุดจบ/เฟดใหม่สด
    return {"ok": True, "trim": t}


@app.post("/api/studio/queue/{qid}/clip")
async def studio_queue_clip(qid: str, request: Request):
    """แก้จุดเริ่ม/จบ/เฟดของใบคิวที่มาจากคอมโบ (เฉพาะรอบนี้ ไม่แตะไฟล์คอมโบ)"""
    _studio_guard(request)
    body = await request.json()
    async with room.lock:
        it = room.find(qid)
        if not it or not it.get("combo"):
            raise HTTPException(status_code=404, detail="ไม่พบเพลงคอมโบนี้ในคิว")
        t = _clean_clip(body, _dur_of(it.get("videoId") or ""))
        for k, q in (("start", "clipStart"), ("end", "clipEnd"), ("fadeIn", "clipFadeIn"), ("fadeOut", "clipFadeOut")):
            it.pop(q, None)
            if k in t:
                it[q] = t[k]
        await room.broadcast()
    return {"ok": True, "clip": t}


@app.post("/api/studio/song/{vid}/autotime")
async def studio_autotime(vid: str, request: Request):
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    texts = [" ".join(str(x).split()) for x in (body.get("texts") or [])]
    texts = [x for x in texts if x]
    if not texts:
        raise HTTPException(status_code=400, detail="ไม่มีข้อความให้จับเวลา")
    engine = body.get("engine") or ("fa" if _fa_ready() else "whisper")
    if engine == "fa" and _fa_ready() and _audio_for(vid):
        try:
            r = await _fa(vid, {"texts": texts, "duration": _song_meta(vid)["duration"] or 0})
        except Exception as exc:
            return {"fail": True, "why": f"จับเวลาละเอียดไม่สำเร็จ: {exc}"}
        r["lines"] = [{"t": l["t"], "d": l["d"], "x": l["x"]} for l in r["lines"]]
        return r
    return await asyncio.to_thread(_autotime, vid, texts)


# ===== Studio: แผนที่ความคลาด / ห้องหาเนื้อ / จับเวลาละเอียด (FA) =====
# FA = forced alignment ด้วย wav2vec2 ภาษาไทย (scripts/fa_align.py) รันเป็น subprocess
# ไม่ให้โมเดล 1.2 GB ค้างในโปรเซสหลัก — แคชผลวิเคราะห์เสียงไว้ต่อเพลง ครั้งถัดไปเร็วมาก
# วัดกับเวลาที่คนทำ (ซับ YouTube/lrclib): ตรงภายใน 0.5 วิ ~9 ใน 10 บรรทัด (whisper เดิม ~3 ใน 10)
FA_MIN_CONF = 0.12            # ต่ำกว่านี้ = ข้อความไม่ตรงกับเสียงจริงช่วงนั้น ไม่นับเป็นค่าที่วัดได้
_FA_RANK = 0.5                # ต่อคิว GPU หลังงานของเพลงที่กำลังเล่น แต่ก่อนเพลงในคิว/งานตอนว่าง


def _fa_mod():
    import fa_align                       # นำเข้าเบา (numpy) — torch/transformers โหลดเฉพาะตอนคำนวณเสียง
    return fa_align


def _fa_ready() -> bool:
    import importlib.util
    if importlib.util.find_spec("transformers") is None:
        return False
    hub = Path(os.environ.get("HF_HUB_CACHE") or BASE / ".cache" / "hf" / "hub")
    return (hub / ("models--" + _fa_mod().MODEL.replace("/", "--"))).is_dir()


def _fa_cached(vid: str) -> bool:
    try:
        return _fa_mod().cached(vid, audio=_audio_for(vid))
    except Exception:
        return False


def _fa_cached_for(vid: str, texts: list[str]) -> bool:
    """FA ข้อความชุดนี้ได้โดยไม่ต้องใช้ GPU ไหม: แคชไทยต้องมี + ถ้ามีคำอังกฤษ แคชโมเดลอังกฤษก็ต้องมี
    (ไม่มีโมเดลอังกฤษในเครื่อง = ไม่ทำรอบอังกฤษ จึงไม่ต้องรอแคชนั้น)"""
    try:
        F = _fa_mod()
        a = _audio_for(vid)
        if not F.cached(vid, audio=a):
            return False
        return not F.has_latin(texts) or not F.model_ready(F.MODEL_EN) or F.cached(vid, en=True, audio=a)
    except Exception:
        return False


def _audio_for(vid: str) -> Path | None:
    d = _song_dir(vid)
    for name in ("vocals.m4a", "audio.m4a"):
        if (d / name).is_file():
            return d / name
    return None


# --- FA แบบโหลดโมเดลค้าง (fa_align.py --serve) ------------------------------
# วัดแล้ว (เพลง 3.5 นาที): เปิดโปรเซสใหม่ = import + โหลดโมเดล 8-10 วิ/โมเดล + คำนวณ ~5 วิ/โมเดล
# -> ไทย 16 วิ, ไทย+อังกฤษ 25 วิ · โหลดค้างไว้ = 5 / 9.6 วิ (ผลตัวเลขเท่ากันทุกตัว — โค้ดคำนวณชุดเดียวกัน)
# ใช้เฉพาะงานที่ต้องคำนวณเสียง (ในช่อง GPU) — งานที่มีแคชแล้วยังเป็น subprocess เดิม (CPU ล้วน ไม่ต้องต่อคิว)
# verify ยังใช้ทางเดิม ให้ _preempt_heavy ฆ่าแย่งคิวได้ · ใช้ไม่ได้ (เปิดไม่ขึ้น/ตาย) = ถอยไปทางเดิมเอง
FA_WORKER = os.environ.get("KARA_FA_WORKER", "on") != "off"
_FA_LOGWORTHY = ("Error", "Traceback", 'File "', "Killed")   # stderr ของตัวโหลดค้าง: พิมพ์เฉพาะที่เป็นปัญหาจริง


class _FaWorkerDown(Exception):
    """ตัวโหลดค้างตาย/ปิดไป (ไม่ใช่ FA คำนวณพลาด) -> เปิดใหม่หรือถอยไปทางเดิม"""


class _FaWorker:
    def __init__(self) -> None:
        self.lock = threading.Lock()                # ทีละคำขอ (ถูกเรียกจาก thread ของ asyncio.to_thread)
        self.proc: subprocess.Popen | None = None
        self.q: queue.Queue | None = None
        self.n = 0
        self.loaded: list[str] = []
        self.last = 0.0

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _forget(self) -> None:
        p, self.proc, self.loaded = self.proc, None, []
        if p is not None:
            with _children_lock:
                _children.pop(p.pid, None)

    def _kill(self) -> None:
        p = self.proc
        self._forget()
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass

    def _start(self) -> None:
        self._forget()
        proc = subprocess.Popen([sys.executable, str(BASE / "scripts" / "fa_align.py"), "--serve"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", bufsize=1, cwd=str(BASE))
        q: queue.Queue = queue.Queue()

        def read_out() -> None:
            for line in proc.stdout:
                q.put(line)
            q.put(None)                             # EOF = ตัวโหลดค้างจบแล้ว

        def read_err() -> None:
            for line in proc.stderr:
                line = line.rstrip()
                if any(w in line for w in _FA_LOGWORTHY):   # แถบโหลด/คำเตือนของ transformers ไม่ต้องลง log
                    print(f"[fa] {line[:300]}")
        threading.Thread(target=read_out, daemon=True).start()
        threading.Thread(target=read_err, daemon=True).start()
        with _children_lock:
            _children[proc.pid] = ("faworker", "", proc)   # vid ว่าง: ลบเพลง/แย่งคิวไม่ฆ่าตัวนี้ ปิดเซิร์ฟเวอร์ฆ่า
        self.proc, self.q = proc, q

    def _ask(self, msg: dict, timeout: float) -> dict:
        """ถือ self.lock อยู่แล้ว — ส่งหนึ่งบรรทัด รอคำตอบ id เดียวกัน"""
        if not self.alive():
            self._start()
        self.n += 1
        msg = {**msg, "id": self.n}
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._kill()
            raise _FaWorkerDown(f"ส่งคำขอไม่ได้: {exc}")
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                self._kill()
                raise RuntimeError(f"fa หมดเวลา ({timeout / 60:.0f} นาที)")
            try:
                line = self.q.get(timeout=min(left, 5.0))
            except queue.Empty:
                continue
            if line is None:
                self._kill()
                raise _FaWorkerDown("ตัวโหลดค้างปิดไประหว่างทำงาน")
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("id") == msg["id"]:
                self.last = time.monotonic()
                self.loaded = list(r.get("loaded") or self.loaded)
                return r

    def request(self, vid: str, audio: Path, payload: dict, timeout: float = 900) -> dict:
        with self.lock:
            for attempt in (0, 1):                  # ปิดเองเพราะว่างนานพอดีจังหวะ -> เปิดใหม่ลองอีกครั้ง
                try:
                    r = self._ask({"vid": vid, "audio": str(audio), "req": payload}, timeout)
                except _FaWorkerDown:
                    if attempt:
                        raise
                    continue
                if not r.get("ok"):
                    raise RuntimeError(str(r.get("error") or "fa ผิดพลาด")[:200])
                return r["out"]
        raise _FaWorkerDown("ไม่ได้คำตอบ")

    def load_now(self) -> float | None:
        """เปิดตัวโหลดค้าง + โหลดโมเดลไว้ (op load) — บล็อกจนเสร็จ คืนวินาที / None = ไม่ได้ทำ"""
        if not self.lock.acquire(blocking=False):
            return None                             # กำลังทำงานอยู่ = โมเดลโหลดอยู่แล้ว
        try:
            t0 = time.monotonic()
            self._ask({"op": "load"}, 300)
            dt = time.monotonic() - t0
            print(f"[fa] โหลดโมเดลค้างไว้ {len(self.loaded)} ตัว | {dt:.0f}s")
            return dt
        except Exception as exc:
            print(f"[fa] โหลดโมเดลล่วงหน้าไม่ได้: {type(exc).__name__}: {exc}")
            return None
        finally:
            self.lock.release()

    def preload_bg(self, vid: str | None = None) -> None:
        """โหลดโมเดลไว้ก่อนระหว่าง demucs แยกเสียง (งานดิสก์/หน่วยความจำ) — vocals เสร็จแล้วคำนวณได้ทันที"""
        if not FA_WORKER or not _fa_ok_cached() or (vid and _song_lang(vid)[0] not in LS.FA_LANGS):
            return
        if self.alive() and self.loaded:
            return
        threading.Thread(target=self.load_now, daemon=True).start()

    def status(self) -> dict:
        return {"on": FA_WORKER, "alive": self.alive(), "pid": self.proc.pid if self.alive() else None,
                "loaded": [m.rsplit("/", 1)[-1] for m in self.loaded],
                "idleSec": round(time.monotonic() - self.last) if self.last else None}


_fa_worker = _FaWorker()


# --- อุ่นเครื่องตอนเปิดโปรแกรม ------------------------------------------------
# ผู้ใช้ขอ: เพลงแรกหลังเปิดโปรแกรมหาเนื้อได้เร็วเหมือนเพลงหลัง ๆ — โหลดโมเดล FA (2 ตัว ~17 วิ) ไว้ตั้งแต่เปิด
# และค้างไว้ตลอด (fa_align KARA_FA_IDLE ค่าเริ่มต้น 0) เดิมโหลดตอนเพลงแรกเข้ามาแล้วปิดเองหลังว่าง 15 นาที
# วัดแล้วไม่ทำ: รันโมเดลหนึ่งรอบกับเสียงเงียบ (FA ครั้งแรก 16.5 vs 16.7 วิ = ไม่ต่าง), อุ่น whisper ด้วยตรวจภาษา
# (2.6 -> 1.8 วิ ต่างไม่ถึง 1 วิ) และ demucs (โปรเซสต่อเพลง โมเดลเล็ก) — "รอเสียงFA 17" ใน log คือเวลาคำนวณจริง
WARM = os.environ.get("KARA_WARM", "on") != "off"
WARM_DELAY = 8.0              # วินาทีหลังเปิด — ให้เซิร์ฟเวอร์/จอตั้งตัวก่อน
_warm_state: dict = {}        # /api/health -> warm


async def _warmup() -> None:
    await asyncio.sleep(WARM_DELAY)
    t0 = time.monotonic()
    _warm_state.update(status="working", at=int(time.time()))
    steps: dict[str, Any] = {}

    def imports() -> None:            # โมดูลที่งานหาเนื้อ import ในโปรเซสหลัก (ครั้งแรกต้องอ่านดิสก์)
        import gen_lyrics, lyrics_more, lyrics_refine, verify_lyrics, vocal_activity  # noqa: F401
    try:
        await asyncio.to_thread(imports)
        steps["import"] = round(time.monotonic() - t0, 1)
    except Exception as exc:
        steps["import"] = type(exc).__name__
    if FA_WORKER and _fa_ok_cached():
        dt = await asyncio.to_thread(_fa_worker.load_now)
        steps["FA"] = round(dt, 1) if dt is not None else "ข้าม (กำลังทำงานอยู่)"
    total = time.monotonic() - t0
    _warm_state.update(status="done", steps=steps, sec=round(total, 1))
    print("[warm] พร้อมแล้ว: " + " · ".join(f"{k} {v}{'s' if isinstance(v, (int, float)) else ''}"
                                          for k, v in steps.items()) + f" | รวม {total:.0f}s")


def _fa_call(vid: str, payload: dict, kind: str = "fa") -> dict:
    """kind = ชื่องานที่ลงทะเบียนโปรเซส (verify ถูกแย่งคิวได้ — ฆ่าแล้วกลายเป็น _Preempted ไม่ใช่ failed)"""
    audio = _audio_for(vid)
    if not audio:
        raise RuntimeError("ไม่มีไฟล์เสียง")
    if FA_WORKER and kind != "verify":
        texts = list(payload.get("texts") or [x for st in (payload.get("sets") or []) for x in (st or [])])
        if not _fa_cached_for(vid, texts):          # ต้องคำนวณเสียง -> ตัวโหลดค้าง (ผลเท่ากับทางเดิม)
            try:
                return _fa_worker.request(vid, audio, payload)
            except _FaWorkerDown as exc:
                print(f"[fa] ตัวโหลดค้างใช้ไม่ได้ ({exc}) -> เปิดโปรเซสแบบเดิม")
    try:
        rc, out, err = _run_child(kind, vid, [sys.executable, str(BASE / "scripts" / "fa_align.py"), vid,
                                              "--audio", str(audio)],
                                  timeout=900, input=json.dumps(payload, ensure_ascii=False), cwd=str(BASE))
    finally:
        if kind == "verify" and vid in _preempt_kill:
            _preempt_kill.discard(vid)
            raise _Preempted()
    if rc != 0:
        tail = [l for l in err.strip().splitlines() if l.strip()]
        raise RuntimeError(tail[-1][:200] if tail else f"rc={rc}")
    return json.loads(out.strip().splitlines()[-1])


async def _fa(vid: str, payload: dict) -> dict:
    """ครั้งแรกของเพลงต้องวิเคราะห์เสียง (ใช้ GPU ~5-20 วิ) -> ต่อคิวเดียวกับ demucs/whisper
    ครั้งต่อไปมีแคชแล้วเหลือแค่ Viterbi บน CPU ไม่ต้องรอคิว"""
    global _heavy_job
    texts = list(payload.get("texts") or [x for st in (payload.get("sets") or []) for x in (st or [])])
    if _fa_cached_for(vid, texts):
        return await asyncio.to_thread(_fa_call, vid, payload)
    async with _heavy.slot(f"fa:{vid}", lambda: _FA_RANK):
        _heavy_job = ("fa", vid)                  # /api/health เห็นว่า GPU ไม่ว่าง (ไม่ถูกแย่งคิว: คนกดรออยู่)
        try:
            return await asyncio.to_thread(_fa_call, vid, payload)
        finally:
            _heavy_job = None


# ===== เวลารายตัวอักษร: โหมด "คาราโอเกะ" บนจอ (ไล่สีตามที่ร้องจริง) =====
# ท่อนร้องเร็ว เวลาเริ่มบรรทัดตรงอยู่แล้ว (FA คลาด ~0.1 วิ) แต่ทั้งบรรทัดขึ้นพร้อมกัน
# คนร้องตามไม่ทันว่าถึงคำไหน -> เก็บเวลาที่ "แต่ละตัวอักษรถูกร้อง" ไว้ให้จอไล่สี
# ไฟล์แยก lyrics.words.json ไม่แตะ lyrics.json — ใช้ได้เฉพาะตอนข้อความทุกบรรทัดตรงกัน
# (แก้เวลาใน Studio อย่างเดียว ไฟล์นี้ยังใช้ได้ เพราะ k เป็นเวลาจริงในเสียง ไม่ได้อิงเวลาบรรทัด)
WORDS_MIN_CONF = 0.15         # บรรทัดที่ FA ไม่มั่นใจ (เสียงไม่ตรงข้อความ) -> ไม่ไล่สี แสดงแบบ 2 บรรทัดปกติ
WORDS_MAX_GAP = 3.0           # k ตัวแรกห่างจากเวลาบรรทัดเกินนี้ = FA วางผิดรอบ (ฮุคซ้ำ) -> ไม่ไล่สี
WORDS_VERSION = 2             # 2 = มีคำอังกฤษด้วย (โมเดลอังกฤษรอบที่ 2) — รุ่นเก่าถือว่าต้องทำใหม่
_words_task: asyncio.Task | None = None
_words_state: dict[str, dict] = {}                 # videoId -> {"status": queued|working|failed, "error"}
_words_cache: dict[str, tuple] = {}
_fa_ok: tuple[float, bool] = (0.0, False)


def _fa_ok_cached() -> bool:
    """_fa_ready() ไปค้นแพ็กเกจ/โฟลเดอร์โมเดล — ถูกเรียกจาก _reprioritize ทุก 10 วิ จึงจำไว้ 60 วิ"""
    global _fa_ok
    if time.monotonic() - _fa_ok[0] > 60:
        try:
            _fa_ok = (time.monotonic(), _fa_ready())
        except Exception:
            _fa_ok = (time.monotonic(), False)
    return _fa_ok[1]


_en_ok: tuple[float, bool] = (0.0, False)


def _en_model_ok() -> bool:
    """โมเดลอังกฤษเพิ่งถูกโหลดมาไว้ -> ไฟล์ที่ทำตอนยังไม่มีโมเดลถือว่าเก่า (จำไว้ 60 วิ)"""
    global _en_ok
    if time.monotonic() - _en_ok[0] > 60:
        try:
            F = _fa_mod()
            _en_ok = (time.monotonic(), F.model_ready(F.MODEL_EN))
        except Exception:
            _en_ok = (time.monotonic(), False)
    return _en_ok[1]


def _words_meta(vid: str) -> dict:
    """{"ok": ใช้ได้ไหม, "mt", "nk": บรรทัดที่ไล่สีได้, "n": ทุกบรรทัด, "stale": มีไฟล์แต่ข้อความไม่ตรง}
    แคชด้วย mtime ของทั้งสองไฟล์ + offset เพราะถูกเรียกทุก item ทุก broadcast"""
    d = _song_dir(vid)
    try:
        wm = (d / "lyrics.words.json").stat().st_mtime
    except OSError:
        return {"ok": False, "mt": 0.0, "nk": 0, "n": 0, "stale": False}
    lm = _lyr_meta(vid)[0]
    off = _lyr_offset(vid)
    key = (wm, lm, off)
    hit = _words_cache.get(vid)
    if hit and hit[0] == key:
        return hit[1]
    out = {"ok": False, "mt": wm, "nk": 0, "n": 0, "stale": True}
    try:
        w = json.loads((d / "lyrics.words.json").read_text("utf-8"))
        L = json.loads((d / "lyrics.json").read_text("utf-8")).get("lines") or []
        texts = [x.get("x") or "" for x in L]
        en_missing = (w.get("en") or {}).get("why") == "no-model" and _en_model_ok()
        if texts and w.get("texts") == texts and w.get("v") == WORDS_VERSION and not en_missing:
            ks = w.get("k") or []
            # นับเหมือนที่จอจะใช้จริง: k ตัวแรกต้องอยู่ใกล้เวลาบรรทัด (+offset ประจำเพลง)
            nk = sum(1 for ln, k in zip(L, ks)
                     if k and abs(k[0][1] - (float(ln.get("t") or 0) + off)) <= WORDS_MAX_GAP)
            out = {"ok": True, "mt": wm, "nk": nk, "n": len(texts), "stale": False}
    except Exception:
        pass
    _words_cache[vid] = (key, out)
    return out


def _words_stale_auto(vid: str) -> bool:
    """งานเลือกเนื้อ/ซ่อมเวลาเปลี่ยนเวลาบรรทัด "หลัง" ทำเวลารายคำไปแล้ว -> หมุดของไล่สีเป็นชุดเก่า ต้องทำใหม่
    (เวลาที่คนแก้ใน Studio ไม่นับ — ตั้งใจไม่ทำใหม่ตามนโยบายเดิม; เนื้อที่คนแก้ไม่มี best อยู่แล้ว)"""
    d = _song_dir(vid)
    try:
        if not (_read_lyr(vid) or {}).get("best"):
            return False
        return (d / "lyrics.words.json").stat().st_mtime < (d / "lyrics.json").stat().st_mtime
    except OSError:
        return False


def _fa_scriptable(vid: str) -> bool:
    """เนื้อมีตัวไทยหรือละตินพอให้ FA จับได้ไหม (ญี่ปุ่น/เกาหลีล้วน = ไม่มีโมเดล)"""
    txt = " ".join(_lyr_texts(vid))
    return len(_TH_RE.findall(txt)) + len(_LAT_RE.findall(txt)) >= 20


def _lyr_texts(vid: str) -> list[str]:
    try:
        L = json.loads((_song_dir(vid) / "lyrics.json").read_text("utf-8")).get("lines") or []
        return [x.get("x") or "" for x in L]
    except Exception:
        return []


def _make_words(vid: str) -> tuple[int, int]:
    """FA ทั้งเพลงแบบขอเวลารายตัวอักษร -> lyrics.words.json คืน (บรรทัดที่ได้ k, ทุกบรรทัด)"""
    d = _song_dir(vid)
    j = json.loads((d / "lyrics.json").read_text("utf-8"))
    L = j.get("lines") or []
    texts = [x.get("x") or "" for x in L]
    if not texts:
        raise RuntimeError("ไม่มีเนื้อเพลง")
    # เวลาบรรทัดที่จอใช้จริง (+offset ประจำเพลง) เป็นหมุด: ท่อนซ้ำที่ FA ทั้งเพลงวางผิดรอบจะถูกจับใหม่รอบหมุด
    off = _lyr_offset(vid)
    anchors = [[round(float(x.get("t") or 0) + off, 2), float(x.get("d") or 0)] for x in L]
    r = _fa_call(vid, {"texts": texts, "duration": j.get("duration") or 0, "words": True, "anchors": anchors},
                 kind="words")
    lines = r.get("lines") or []
    if len(lines) != len(texts):
        raise RuntimeError("จำนวนบรรทัดจาก FA ไม่ตรง")
    ks: list = []
    confs: list = []
    for ln in lines:
        c = ln.get("conf")
        k = ln.get("k") or []
        ks.append(k if k and c is not None and c >= WORDS_MIN_CONF else None)
        confs.append(c)
    # เนื้อถูกแก้ระหว่างที่ FA ทำงาน -> ทิ้งผล ไม่งั้นไฟล์จะผูกกับข้อความเก่า (ตรวจซ้ำตอนเขียน)
    now = [x.get("x") or "" for x in (json.loads((d / "lyrics.json").read_text("utf-8")).get("lines") or [])]
    if now != texts:
        raise RuntimeError("เนื้อเพลงเปลี่ยนระหว่างทำ")
    audio = _audio_for(vid)
    out = {"v": WORDS_VERSION, "texts": texts, "k": ks, "conf": confs, "by": "fa", "en": r.get("en"),
           "audio": audio.name if audio else "", "at": int(time.time())}
    f = d / "lyrics.words.json"
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, f)
    _words_cache.pop(vid, None)
    return sum(1 for k in ks if k), len(ks)


def _words_status(vid: str) -> str:
    """ready | queued | working | failed | stale | none | na"""
    st = _words_state.get(vid, {}).get("status")
    if st in ("queued", "working"):
        return st
    wm = _words_meta(vid)
    if wm["ok"]:
        return "ready"
    if st == "failed":
        return "failed"
    if not _fa_ok_cached():
        return "na"
    return "stale" if wm["stale"] else "none"


async def _ensure_worder() -> None:
    global _words_task
    if _words_task is None or _words_task.done():
        _words_task = asyncio.create_task(_words_worker())


async def _enqueue_words(vid: str | None, force: bool = False) -> bool:
    """เข้าคิวทำเวลารายคำ — คืน True ถ้าเข้าคิวจริง
    ปกติรอให้แยกเสียงเสร็จก่อน (FA บนเสียงร้องล้วนแม่นกว่าเสียงรวมมาก) ยกเว้นแยกเสียงพังไปแล้ว
    หรือมีผลวิเคราะห์เสียงของเพลงนี้แคชอยู่แล้ว (Studio เคยกด FA) ซึ่งไม่ต้องใช้ GPU เลย"""
    if not vid or _lyr_meta(vid)[1] <= 0 or not _fa_ok_cached() or not _fa_scriptable(vid):
        return False
    if _words_pending.has(vid) or _words_state.get(vid, {}).get("status") == "working":
        return False
    if _best_pending.has(vid) or _best_state.get(vid, {}).get("status") == "working":
        return False                # ข้อความอาจเปลี่ยน — งานเลือกเนื้อเสร็จแล้วจะสั่งต่อเอง
    if not force:
        if _words_meta(vid)["ok"] or _words_state.get(vid, {}).get("status") == "failed":
            return False
        if not _has_stems(vid) and _sep_state.get(vid, {}).get("status") != "failed" \
                and not _fa_cached(vid):
            return False            # เดี๋ยว _sep_worker สั่งให้เองตอนได้ vocals
    if not _audio_for(vid):
        return False
    await _ensure_worder()
    _words_state[vid] = {"status": "queued", "error": ""}
    _words_pending.push(vid)
    return True


async def _words_worker() -> None:
    global _heavy_job
    while True:
        await _words_pending.wait()
        hit = _words_pending.best()
        if not hit:
            continue
        # มีแคชผลวิเคราะห์เสียงแล้ว = งาน CPU ไม่กี่วินาที ไม่ต้องจอง GPU
        # ยังไม่มี -> ต่อคิว GPU ตามอันดับเพลงในห้อง แต่หลังงานแยกเสียง/หาเนื้อของเพลงอันดับเดียวกัน
        if _fa_cached_for(hit[0], _lyr_texts(hit[0])):
            vid = hit[0]
            _words_pending.discard(vid)
            await _run_words(vid)
        else:
            async with _heavy.slot("words", lambda: (_words_pending.best() or ("", _NEVER))[1] + 0.5):
                vid = _words_pending.take_now()
                if vid is None:
                    continue
                _heavy_job = ("words", vid)
                try:
                    await _run_words(vid)
                finally:
                    _heavy_job = None
        await room.broadcast()


async def _run_words(vid: str) -> None:
    if _lyr_meta(vid)[1] <= 0:
        _words_state.pop(vid, None)
        return
    _words_state[vid] = {"status": "working", "error": ""}
    t0 = time.monotonic()
    try:
        nk, n = await asyncio.to_thread(_make_words, vid)
        _words_state.pop(vid, None)
        print(f"[words] {vid} ไล่สีได้ {nk}/{n} บรรทัด | {time.monotonic() - t0:.0f}s")
    except Exception as exc:
        _words_state[vid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(f"[words] {vid} FAILED: {exc}")


def _whisper_chunks(vid: str) -> tuple[list[dict] | None, str]:
    """ไม้บรรทัดสำรองเมื่อยังไม่มี FA: แคช whisper ก่อน แล้วค่อย auto-caption"""
    import gen_lyrics as G
    for f in [G.segment_cache_path(vid)] + sorted(SEG_CACHE.glob(f"{vid}.*.json")):
        if f.is_file():
            try:
                segs = json.loads(f.read_text("utf-8")).get("segs") or []
            except Exception:
                continue
            if segs:
                return G.make_chunks(segs), "asr"
    auto = _song_dir(vid) / "auto.th.vtt"
    if auto.is_file():
        w = LS.words_from_auto_vtt(auto)
        if w:
            return G.make_chunks([{"start": w[0]["start"], "end": w[-1]["end"], "text": "", "words": w}]), "auto-cap"
    return None, ""


def _measure_whisper(vid: str, texts: list[str], eff: list[float], dur: float) -> tuple[list, str]:
    """เวลาที่เสียงร้องบอกต่อบรรทัด (ไม้บรรทัด whisper) — เลือกจุดที่ "ใกล้เวลาปัจจุบันที่สุด"
    ไม่ใช่จุดแรก เพราะท่อนฮุคร้องซ้ำ จุดแรกจะชี้ไปท่อนแรกเสมอ"""
    import gen_lyrics as G
    chunks, by = _whisper_chunks(vid)
    if not chunks:
        return [None] * len(texts), ""
    hits: dict[int, list[float]] = {}
    for a in G.align(chunks, texts, dur):
        hits.setdefault(a["line"], []).append(a["t"])
    out = []
    for i, e in enumerate(eff):
        ts = [t for t in hits.get(i, []) if abs(t - e) <= 15]
        out.append(min(ts, key=lambda t: abs(t - e)) if ts else None)
    return out, by


@app.post("/api/studio/song/{vid}/drift")
async def studio_drift(vid: str, request: Request):
    """เวลาที่เสียงร้องบอกของทุกบรรทัด (ไว้ทำแผนที่ความคลาดใน Studio)
    engine: auto = ใช้ FA ถ้ามีแคช (เร็ว) ไม่งั้น whisper / fa = บังคับวิเคราะห์ละเอียด"""
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    raw = body.get("lines") or []
    off = _finite(body.get("offset") or 0.0, -LYR_OFFSET_MAX, LYR_OFFSET_MAX)
    if off is None or not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="ข้อมูลไม่ถูกต้อง")
    raw = [l for l in raw if isinstance(l, dict)]
    texts = [" ".join(str(l.get("x") or "").split()) for l in raw]
    eff = [(_finite(l.get("t") or 0, 0.0, 86400.0) or 0.0) + off for l in raw]
    dur = float(_song_meta(vid)["duration"] or 0)
    engine = body.get("engine") or "auto"
    if not texts:
        return {"by": "", "texts": [], "meas": [], "conf": []}
    use_fa = _fa_ready() and _audio_for(vid) and (engine == "fa" or (engine == "auto" and _fa_cached(vid)))
    conf: list = [None] * len(texts)
    if use_fa:
        try:
            r = await _fa(vid, {"texts": texts, "duration": dur})
            meas = [l["t"] if (l.get("conf") or 0) >= FA_MIN_CONF else None for l in r["lines"]]
            conf = [l.get("conf") for l in r["lines"]]
            by = "fa"
        except Exception as exc:
            return {"by": "", "texts": texts, "meas": [], "conf": [], "why": f"วิเคราะห์ละเอียดไม่สำเร็จ: {exc}"}
    else:
        meas, by = await asyncio.to_thread(_measure_whisper, vid, texts, eff, dur)
    # คืน "เวลาที่วัดได้" แบบสัมบูรณ์ — Studio คำนวณความคลาดและช่วงที่ควรเลื่อนเองสด ๆ
    # ระหว่างลาก/เลื่อนเวลา โดยไม่ต้องถามเซิร์ฟเวอร์ซ้ำ (ตราบใดที่ข้อความไม่เปลี่ยน)
    return {"by": by, "texts": texts, "meas": [round(m, 2) if m is not None else None for m in meas],
            "conf": conf, "fa": {"ready": _fa_ready(), "cached": _fa_cached(vid)}}


@app.post("/api/studio/song/{vid}/refine")
async def studio_refine(vid: str, request: Request):
    """🩺 ตรวจ/ซ่อมช่วงที่เวลาเพี้ยน (scripts/lyrics_refine.py) บนเนื้อที่กำลังแก้ใน Studio — ข้อเสนอเท่านั้น ไม่บันทึก
    ทางเดียวที่เพลงที่แก้เอง (manual-edit) ได้ใช้ตัวซ่อม: งานอัตโนมัติไม่แตะเนื้อพวกนี้เด็ดขาด"""
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    raw = body.get("lines") or []
    off = _finite(body.get("offset") or 0.0, -LYR_OFFSET_MAX, LYR_OFFSET_MAX)
    if off is None or not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="ข้อมูลไม่ถูกต้อง")
    lines = _clean_edit_lines(raw)
    # ตัวซ่อมทำงานบนเวลาที่จอใช้จริง (เวลา + offset ประจำเพลง) แล้วหักกลับก่อนส่งคืน
    eff = [{**l, "t": round(l["t"] + off, 2)} for l in lines]
    if not _fa_ready() or not _audio_for(vid):
        return {"ok": False, "why": "ยังไม่มีโมเดล FA หรือไฟล์เสียง"}
    texts = [l["x"] for l in eff]
    if not _fa_cached_for(vid, texts):
        try:                                       # ครั้งแรกของเพลงต้องวิเคราะห์เสียง (ต่อคิว GPU เหมือนปุ่ม FA)
            await _fa(vid, {"texts": texts, "duration": _song_meta(vid)["duration"] or 0})
        except Exception as exc:
            return {"ok": False, "why": f"วิเคราะห์เสียงไม่สำเร็จ: {exc}"}
    r = await asyncio.to_thread(_refine_call, vid, eff, "self", bool(body.get("segments", True)))
    if not r:
        return {"ok": False, "why": "ซ่อมไม่ได้ (ดู log ของเซิร์ฟเวอร์)"}
    out = [{**l, "t": round(max(0.0, l["t"] - off), 2)} for l in r["lines"]]
    return {"ok": True, "lines": out, "record": r.get("record") or {}, "note": r.get("note") or "",
            "changed": bool(r.get("changed"))}


# --- ตั้งค่าแหล่งเนื้อ (Musixmatch token) --------------------------------------
_mxm_state = {"err": "", "at": 0.0}


@app.get("/api/studio/settings")
def studio_settings_get(request: Request):
    _studio_guard(request)
    tok = _mxm_token()
    return {"mxm": {"set": bool(tok), "hint": (tok[:4] + "…" + tok[-3:]) if len(tok) > 10 else ("•••" if tok else ""),
                    "err": _mxm_state["err"]}}


@app.post("/api/studio/settings")
async def studio_settings_set(request: Request):
    """{"mxmToken": "..."} ("" = ลบ) — ทดสอบกับ Musixmatch ก่อนเก็บ ใช้ไม่ได้ก็บอกเลย"""
    _studio_guard(request)
    body = await request.json()
    if "mxmToken" in body:
        tok = "".join(str(body.get("mxmToken") or "").split())[:200]
        err = ""
        if tok:
            import lyrics_more as M
            err = await asyncio.to_thread(M.mxm_check, tok)
            if err:
                return {"ok": False, "why": err}
        cfg = json.loads(STUDIO_FILE.read_text("utf-8")) if STUDIO_FILE.is_file() else {}
        if tok:
            cfg["mxmToken"] = tok
        else:
            cfg.pop("mxmToken", None)
        await asyncio.to_thread(_write_json_atomic, STUDIO_FILE, cfg)
        _mxm_state.update(err="", at=time.time())
        _src_cache.clear()                         # ผลห้องหาเนื้อเดิมไม่มี Musixmatch -> หาใหม่
    return {"ok": True, **studio_settings_get(request)}


# --- ห้องหาเนื้อ -------------------------------------------------------------
_src_cache: dict[tuple, tuple[float, list[dict]]] = {}
ONLINE_PROVIDERS = ("lrclib", "joox", "netease", "ytmusic", "musixmatch")
TWIN_SIM = 0.8                # บรรทัดเนื้อเหมือนกัน (Jaccard) ตั้งแต่เท่านี้ = เพลงเดียวกันอีกคลิป
_twin_idx: dict[str, tuple[float, frozenset, dict]] = {}


def _norm_line(x: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFC", x or "").lower() if ch.isalnum())


def _library_twins(vid: str, texts: list[str]) -> list[tuple[float, str, Path, dict]]:
    """เพลงอื่นในคลังที่เนื้อเกือบเหมือนกันทุกบรรทัด (คลิปซ้ำของเพลงเดียวกัน) — มากสุด 2 เพลง
    คลังมีเพลงซ้ำแบบนี้ 6 คู่ เช่น ILLSLICK ตีหนึ่งที่คูเมือง (คลิปหนึ่งผู้ใช้แก้เวลาเอง อีกคลิปได้จากเครื่อง)"""
    mine = frozenset(k for k in (_norm_line(x) for x in texts) if len(k) >= 6)
    if len(mine) < 6:
        return []
    out = []
    for v2, d2 in list(_dir_index().items()):
        if v2 == vid:
            continue
        f = d2 / "lyrics.json"
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        hit = _twin_idx.get(v2)
        if not hit or hit[0] != mt:
            try:
                j2 = json.loads(f.read_text("utf-8"))
            except Exception:
                continue
            ks = frozenset(k for k in (_norm_line(l.get("x")) for l in j2.get("lines") or []) if len(k) >= 6)
            hit = (mt, ks, j2)
            _twin_idx[v2] = hit
        ks = hit[1]
        if not ks:
            continue
        jac = len(mine & ks) / len(mine | ks)
        if jac >= TWIN_SIM:
            out.append((jac, v2, d2, hit[2]))
    return sorted(out, key=lambda x: -x[0])[:2]


def _ocr_ensure(vid: str, nice: bool = False) -> dict | None:
    """อ่านตัวหนังสือในคลิป (scripts/ocr_lyrics.py — Apple Vision) ถ้ายังไม่เคยอ่าน — คลิปไม่มีเนื้อในภาพรู้ใน ~1 วิ
    Lyric Video ใช้ ~20-30 วิ ผลแคชไว้ (lyrics-preview/_ocr) ผูกกับไฟล์วิดีโอ
    nice: ลำดับความสำคัญ CPU ต่ำ — ตอนอ่านล่วงหน้าพร้อม demucs ไม่ให้แย่งจนแยกเสียงช้าลง"""
    d = _song_dir(vid)
    video = d / "video.mp4"
    if not video.is_file() or sys.platform != "darwin":
        return None
    try:
        import ocr_lyrics as O
        hit = O.cached(vid, video)
        if hit is not None:
            return hit
        cmd = [sys.executable, str(BASE / "scripts" / "ocr_lyrics.py"), vid, "--video", str(video)]
        if nice and shutil.which("nice"):
            cmd = ["nice", "-n", "10"] + cmd      # ffmpeg/kara_ocr ที่มันเรียกต่อได้ nice ไปด้วย
        rc, out, err = _run_child("ocr", vid, cmd, timeout=900, cwd=str(BASE))
        if rc != 0:
            tail = [l for l in err.strip().splitlines() if l.strip()]
            print(f"[ocr] {vid} ล้มเหลว: {tail[-1][:200] if tail else rc}")
            return None
        return O.cached(vid, video)
    except Exception as exc:
        print(f"[ocr] {vid} {type(exc).__name__}: {exc}")
        return None


def _ocr_cands(vid: str, cands: list[dict], dur: float) -> list[dict]:
    """ผู้สมัครจากตัวหนังสือในคลิป: (1) ข้อความที่อ่านได้ตรง ๆ (2) ข้อความของแหล่งอื่น + "เวลาที่ขึ้นจอในคลิปนี้"
    OCR สะกดเพี้ยนได้ แต่เวลาเป็นของคลิปนี้จริง — ข้อ 2 จึงเป็นตัวหลัก (FA ตัดสินอีกทีว่าเวลาใช้ได้ไหม)"""
    try:
        import ocr_lyrics as O
        d = _song_dir(vid)
        j = O.cached(vid, d / "video.mp4") if (d / "video.mp4").is_file() else None
    except Exception:
        j = None
    cues = (j or {}).get("cues") or []
    if len(cues) < LS.MIN_LINES:
        return []
    out = []
    raw = LS._finish([(c["t0"], " ".join(str(c["x"]).split()), c["t1"]) for c in cues
                      if len(_TH_RE.findall(c["x"])) + len(_LAT_RE.findall(c["x"])) >= 4], dur)
    if raw:
        out.append({"provider": "ocr", "label": "ตัวหนังสือในคลิป (OCR)", "synced": True, "lines": raw,
                    "texts": None, "meta": {"via": "ocr"}, "via": "local"})
    der = []
    for c in cands:
        if c["provider"] in ("ocr", "yt-auto") or c["provider"].startswith("ocr+"):
            continue
        base = [dict(l) for l in c["lines"]] if c["synced"] else \
            [{"t": float(i), "d": 1.0, "x": x} for i, x in enumerate(c["texts"] or [])]
        if len(base) < LS.MIN_LINES:
            continue
        lines, n = O.retime(base, cues)
        if n >= 0.6 * len(base):
            for i, l in enumerate(lines):
                nxt = lines[i + 1]["t"] if i + 1 < len(lines) else (dur if dur > l["t"] else l["t"] + 6.0)
                l["d"] = LS.line_dur(l["t"], nxt)
            der.append((n / len(base), {"provider": "ocr+" + c["provider"],
                                        "label": f"{c['label']} · เวลาจากตัวหนังสือในคลิป ({n}/{len(base)} บรรทัด)",
                                        "synced": True, "lines": lines, "texts": None,
                                        "meta": {**(c.get("meta") or {}), "via": "ocr"}, "via": "local"}))
    der.sort(key=lambda x: -x[0])
    return out + [c for _, c in der[:3]]


def _mxm_token() -> str:
    return str(_studio_cfg().get("mxmToken") or "").strip()
SRC_TTL = 1800.0


def _gather_sources(vid: str, track: str, artist: str, errs: list | None = None) -> list[dict]:
    """ผู้สมัครทุกแหล่ง (ยังไม่ให้คะแนน) — แหล่งออนไลน์ยิงพร้อมกัน แต่ละแหล่งพังได้โดยไม่ลากตัวอื่น
    errs: ส่ง list มา = ได้ชื่อแหล่งที่พัง (งานเลือกเนื้ออัตโนมัติใช้ตัดสินว่าผลยังไม่ครบ ต้องลองใหม่)"""
    import gen_lyrics as G
    import lyrics_more as M
    from concurrent.futures import ThreadPoolExecutor
    d = _song_dir(vid)
    meta = _song_meta(vid)
    dur = float(meta["duration"] or 0)
    try:
        info = json.loads((d / "info.json").read_text("utf-8"))
    except Exception:
        info = {}
    title = f"{artist} - {track}" if track else (meta["title"] or "")
    uploader = "" if track else (meta["uploader"] or "")
    # คำค้นจากชื่อ (สูงสุด 3) + ท่อนเนื้อ (สูงสุด 2) — ผลผิดเพลงไม่เป็นไร เพราะเรียงด้วยเสียงร้องจริงทีหลัง
    tq = [x for x in dict.fromkeys([f"{artist} {track}".strip(), track]) if x] if track \
        else M.queries(title, uploader)
    lyr_texts: list[str] = []
    try:
        if (d / "lyrics.json").is_file() and not _lyr_sparse(vid):     # เนื้อแค่บางช่วง = บทพูด ค้นไปก็ไม่เจอเพลง
            lyr_texts = [l["x"] for l in json.loads((d / "lyrics.json").read_text("utf-8")).get("lines") or []]
        if not lyr_texts:
            lyr_texts = G.read_lines(vid, d)[0] or []
        if not lyr_texts:                    # คำที่ YouTube ถอดได้ (auto-caption) — ได้ยินท่อนร้องทั้งเพลง
            auto = d / f"auto.{_song_lang(vid)[0] or 'th'}.vtt"
            w = LS.words_from_auto_vtt(auto, _song_lang(vid)[0] or "th") if auto.is_file() else None
            lyr_texts = [l["x"] for l in (G.lines_from_words(w, dur) or [])] if w else []
        if not lyr_texts:                    # ยังไม่มีเนื้อเลย -> ใช้สิ่งที่ whisper ได้ยิน
            for f in [G.segment_cache_path(vid)] + sorted(SEG_CACHE.glob(f"{vid}.*.json")):
                if f.is_file():
                    lyr_texts = [sg.get("text") or "" for sg in json.loads(f.read_text("utf-8")).get("segs") or []]
                    break
    except Exception:
        lyr_texts = []
    lq = M.lyric_queries(lyr_texts, 2)
    queries = [(x, "title") for x in tq] + [(x, "lyric") for x in lq]
    out: list[dict] = []

    def add(provider, label, lines=None, texts=None, extra=None):
        via = (extra or {}).get("via") or ("title" if provider in ONLINE_PROVIDERS else "local")
        if lines:
            out.append({"provider": provider, "label": label, "synced": True, "lines": lines,
                        "texts": None, "meta": extra or {}, "via": via})
        elif texts and len(texts) >= 2:
            out.append({"provider": provider, "label": label, "synced": False, "lines": None,
                        "texts": texts, "meta": extra or {}, "via": via})

    if not track:                                      # แหล่งในเครื่อง (ค้นเองไม่ต้องทำซ้ำ)
        lang = _song_lang(vid)[0] or "th"
        cur = d / "lyrics.json"
        if cur.is_file():
            try:
                j = json.loads(cur.read_text("utf-8"))
                add("current", "เนื้อที่ใช้อยู่ตอนนี้ · " + LC.kind(j.get("src") or "", LC.time_src_of(j)),
                    lines=j.get("lines"))
            except Exception:
                pass
        sub = d / f"sub.{lang}.vtt"
        if sub.is_file():
            add("yt-sub", "ซับที่คนทำบน YouTube", lines=LS.from_vtt(sub, dur, lang))
        try:
            desc, dsrc = G.read_lines(vid, d, lang)
            add(dsrc, "เนื้อจากคำอธิบายใต้คลิป" if dsrc == "web/description" else f"ไฟล์ที่วางเอง ({dsrc})", texts=desc)
        except Exception:
            pass
        auto = d / f"auto.{lang}.vtt"
        if auto.is_file():
            w = LS.words_from_auto_vtt(auto, lang)
            if w:
                add("yt-auto", "คำบรรยายอัตโนมัติของ YouTube", lines=G.lines_from_words(w, dur))
        # เพลงเดียวกันอีกคลิปในคลัง (MV/Lyric Video/คัฟเวอร์) — เวลาที่คนแก้ไว้คลิปหนึ่งใช้กับอีกคลิปได้หลังเลื่อน
        for jac, v2, d2, j2 in _library_twins(vid, lyr_texts):
            add("library", f"เพลงเดียวกันในคลัง · {d2.name[:60]} · "
                + LC.kind(j2.get("src") or "", LC.time_src_of(j2)), lines=j2.get("lines"),
                extra={"via": "library", "vid": v2, "sim": round(jac, 2)})

    def lrclib():
        res = []
        pool = LS._lrclib_pool(title, uploader, info.get("description") or "" if not track else "",
                               dur, need_synced=False, dur_tol=None)
        # เวอร์ชันที่ยาวใกล้คลิปนี้ก่อน (lrclib คืนเพลงชื่อซ้ำจากหลายศิลปินมาเยอะ)
        pool.sort(key=lambda r: abs((r.get("duration") or 0) - dur) if dur else 0)
        for rec in pool[:6]:
            lab = f'LRCLIB · {rec.get("artistName", "?")} – {rec.get("trackName", "?")}'
            ex = {"duration": rec.get("duration") or 0}
            ln = LS.from_lrc(rec["syncedLyrics"], dur) if rec.get("syncedLyrics") else None
            res.append(("lrclib", lab, ln, None if ln else LS._plain_of(rec), ex))
        return res

    def wrap(name, fn):
        try:
            return fn()
        except Exception as exc:
            print(f"[sources] {vid} {name}: {type(exc).__name__}: {exc}")
            if errs is not None:
                errs.append(name)
            return []
    mxm_tok = _mxm_token()
    jobs = {"lrclib": lrclib,
            "joox": lambda: M.from_joox(queries, dur, per=2, max_total=6),
            "netease": lambda: M.from_syncedlyrics([(x, "title") for x in tq[:2]], dur, providers=("NetEase",)),
            "ytmusic": lambda: M.from_ytmusic(vid, [(x, "title") for x in tq[:2]] + [(x, "lyric") for x in lq[:1]],
                                              dur, per=2)}
    if mxm_tok:                                        # มีบัญชี Musixmatch (ตั้งใน Studio) -> เนื้อมีเวลา/เวลารายคำ
        def mxm():
            try:
                r = M.from_musixmatch([(x, "title") for x in tq[:2]], mxm_tok, dur)
                _mxm_state["err"] = ""
                return r
            except M.MxmError as exc:
                _mxm_state.update(err=str(exc), at=time.time())
                raise
        jobs["musixmatch"] = mxm
    with ThreadPoolExecutor(len(jobs)) as ex:
        futs = {k: ex.submit(wrap, k, fn) for k, fn in jobs.items()}
        for k, f in futs.items():
            for c in f.result():
                if isinstance(c, tuple):
                    add(c[0], c[1], lines=c[2], texts=c[3], extra=c[4])
                else:
                    add(c["provider"], c["label"], lines=c["lines"], texts=c["texts"], extra=c["meta"])
    if not track:
        out.extend(_ocr_cands(vid, out, dur))             # 📷 เนื้อ/เวลาจากตัวหนังสือในคลิป (ถ้าเคยอ่านแล้ว)
    # ตัดซ้ำ (ข้อความเหมือนกันทุกตัวอักษร) เก็บตัวที่มาก่อน
    seen, uniq = set(), []
    for c in out:
        key = (c["synced"], "\n".join(l["x"] for l in c["lines"]) if c["synced"] else "\n".join(c["texts"]))
        if key in seen:
            continue
        seen.add(key)
        c["id"] = len(uniq)
        uniq.append(c)
    return uniq[:24], {"title": tq, "lyric": lq}


def _score_whisper(vid: str, cands: list[dict]) -> None:
    import verify_lyrics as V
    chunks, by = _whisper_chunks(vid)
    dur = float(_song_meta(vid)["duration"] or 0)
    for c in cands:
        if not chunks:
            continue
        lines = c["lines"] or [{"t": 0.0, "d": 1.0, "x": x} for x in c["texts"]]
        m = V.measure(lines, chunks, dur)
        c["match"] = round(m["anchorPct"], 1)
        if c["synced"]:
            c["timing"] = round(m["onTime"], 1)
            c["shift"] = m["shift"] or 0.0
            c["timingAfter"] = round(V.measure(V.shifted(lines, c["shift"], dur), chunks, dur)["onTime"], 1) \
                if c["shift"] else c["timing"]
        c["by"] = by


def _score_fa(cands: list[dict], results: list[dict | None], va: dict | None = None, off: float = 0.0) -> None:
    """คะแนนด้วย FA: match = ข้อความเข้ากับเสียงร้องแค่ไหน (ความมั่นใจเฉลี่ย)
    timing = % บรรทัดที่เวลาเดิมตรงกับที่ FA หาได้ภายใน 0.5 วิ / หลังเลื่อนทั้งเพลงค่าเดียว
    แนบ faLines = ข้อความชุดนั้นจับเวลาด้วย FA แล้ว (ใช้ได้ทันทีแม้เป็นเนื้อเปล่า)
    va (แผนที่เสียงร้อง _va_for — ผู้เรียกโหลดใน thread) -> cover = % เสียงร้องที่ชุดนี้คลุม
    match อย่างเดียวหลอกได้: บทพูด 9 บรรทัดในเอ็มวีได้ 81% (ชัดทุกคำ) สูงกว่าเนื้อเต็มเพลง 55%
    off = offset ประจำเพลงของเนื้อปัจจุบัน (ใช้กับผู้สมัคร current เมื่อหาค่าเลื่อนไม่ได้)"""
    import vocal_activity as VA
    for c, r in zip(cands, results):
        if not r:
            continue
        fl = r["lines"]
        confs = [l.get("conf") or 0 for l in fl]
        c["match"] = round(100 * sum(confs) / max(1, len(confs)), 1)
        c["by"] = "fa"
        c["faConf"] = [l.get("conf") for l in fl]         # ต่อบรรทัด (None = ไม่มีตัวที่โมเดลรู้จัก)
        if c["match"] < 5:                  # ข้อความไม่เข้ากับเสียงร้องเลย (ผิดเพลง/อังกฤษล้วน) ไม่ต้องเสนอ
            continue
        c["faLines"] = [{"t": l["t"], "d": l["d"], "x": l["x"]} for l in fl]
        if c["synced"]:
            ds = [a["t"] - b["t"] for a, b, cf in zip(fl, c["lines"], confs) if cf >= FA_MIN_CONF]
            if len(ds) >= max(4, 0.3 * len(fl)):
                m = sorted(ds)[len(ds) // 2]
                c["shift"] = round(m, 2) if abs(m) >= 0.3 else 0.0
                c["timing"] = round(100 * sum(abs(x) <= 0.5 for x in ds) / len(ds), 1)
                c["timingAfter"] = round(100 * sum(abs(x - c["shift"]) <= 0.5 for x in ds) / len(ds), 1)
        if va is not None:
            # คลุมเสียงร้อง = ค่าที่มากกว่าระหว่าง "ที่ FA วางบรรทัดที่มั่นใจ" กับ "เวลาของแหล่งเอง + ค่าเลื่อน"
            # (บรรทัดอังกฤษตอนไม่มีโมเดลอังกฤษ / แร็ปเร็ว FA ไม่มั่นใจ แต่เวลาของแหล่งยังบอกได้ว่าคลุมตรงไหน)
            cvs = [VA.cover(va, [(l["t"], l["t"] + l["d"]) for l, cf in zip(fl, confs) if cf >= FA_MIN_CONF])]
            if c["synced"]:
                sh = c["shift"] if "shift" in c else (off if c["provider"] == "current" else 0.0)
                cvs.append(VA.cover(va, [(float(l["t"]) + sh, float(l["t"]) + sh + float(l.get("d") or 0))
                                         for l in c["lines"]]))
            cvs = [x for x in cvs if x is not None]
            if cvs:
                c["cover"] = max(cvs)


@app.post("/api/studio/song/{vid}/sources")
async def studio_sources(vid: str, request: Request):
    """ห้องหาเนื้อ: ทุกแหล่ง + คะแนน (ข้อความตรงเพลงไหม / เวลาตรงไหม / ควรเลื่อนเท่าไร)"""
    _studio_guard(request)
    _studio_vid(vid)
    body = await request.json()
    track = " ".join(str(body.get("track") or "").split())
    artist = " ".join(str(body.get("artist") or "").split())
    key = (vid, track, artist)
    hit = _src_cache.get(key)
    if hit and not body.get("fresh") and time.time() - hit[0] < SRC_TTL:
        cands, used = hit[1]
    else:
        if not track:
            await asyncio.to_thread(_ocr_ensure, vid)
        cands, used = await asyncio.to_thread(_gather_sources, vid, track, artist)
        engine_fa = _fa_ready() and _audio_for(vid)
        if engine_fa and cands:
            try:
                sets = [(c["texts"] if not c["synced"] else [l["x"] for l in c["lines"]]) for c in cands]
                va = asyncio.create_task(asyncio.to_thread(_va_for, vid))   # แผนที่เสียงร้อง (ffmpeg) ซ้อนกับ FA
                r = await _fa(vid, {"sets": sets, "duration": _song_meta(vid)["duration"] or 0})
                _score_fa(cands, r.get("results") or [], va=await va, off=_lyr_offset(vid))
            except Exception as exc:
                print(f"[sources] {vid} FA ให้คะแนนไม่ได้ ({exc}) -> ใช้ whisper")
                await asyncio.to_thread(_score_whisper, vid, cands)
        else:
            await asyncio.to_thread(_score_whisper, vid, cands)
        _src_cache[key] = (time.time(), (cands, used))
    # ตัวที่งานเลือกเนื้ออัตโนมัติจะใช้ขึ้นก่อน (เดิมเรียงตาม match ล้วน -> บทพูด 9 บรรทัด 81% ขึ้นที่หนึ่ง)
    # แล้วตัวที่ครบทั้งเพลงตาม match / ตัวที่มีแค่บางช่วงไว้ท้าย
    pick = None
    try:
        dec = _best_decide(cands, None if track else _read_lyr(vid))
        pick = (dec.get("cand") or {}).get("id") if dec.get("action") != "none" else None
        if pick is None:
            pick = (_best_pool(cands)[3] or {}).get("id")
    except Exception as exc:
        print(f"[sources] {vid} เลือกตัวแนะนำไม่ได้: {type(exc).__name__}: {exc}")
    ranked = sorted(cands, key=lambda c: (c.get("id") != pick, bool(c.get("sparse")),
                                          -(c.get("match") or 0), -(c.get("timingAfter") or 0)))
    return {"candidates": ranked, "queries": used, "pick": pick,
            "fa": {"ready": _fa_ready(), "cached": _fa_cached(vid)}}


# ===== เลือกเนื้อดีที่สุดจากทุกแหล่ง (งานเบื้องหลัง "best") =====
# gen_lyrics เลือกแบบ "เจอตัวแรกที่ผ่านเกณฑ์ใช้เลย" เพื่อให้เพลงมีเนื้อขึ้นจอเร็ว
# งานนี้ตามมาทีหลัง: รวมทุกแหล่ง (ในเครื่อง + lrclib/JOOX/NetEase/YouTube Music) ให้ FA ให้คะแนน
# กับเสียงร้องจริง แล้วเปลี่ยนเฉพาะตอนที่ดีกว่าชัดเจน — ของเดิมสำรองไว้ใน lyrics.edits/ (🕘 ประวัติ)
# ไม่แตะเนื้อที่คนตั้งใจใส่เอง (แก้ใน Studio / วางไฟล์ใน lyrics-in)
BEST_MANUAL = frozenset({"manual-edit", "manual-lrc", "manual-txt"})
BEST_GOOD_CONF = 0.25         # บรรทัดที่ FA มั่นใจเท่านี้ขึ้นไป = ข้อความนั้นถูกร้องจริง
# ความเข้ากันเฉลี่ย (match) แยกเพลงผิดได้: วัดกับคลังจริง เพลงผิด 14-30 / เนื้อถูก 38-72
# (FA ไทยจับคู่ข้อความไทยอะไรก็ได้บางส่วน บรรทัดเพลงผิดจึงยังได้ ~0.3 — นับแค่ตัวอักษรที่ผ่านเกณฑ์ไม่พอ)
BEST_MIN_MATCH = 35.0         # ต่ำกว่านี้ไม่เอามาแทนเด็ดขาด
BEST_MATCH_SPREAD = 15.0      # และต้องไม่ห่างจากตัวที่เข้ากันที่สุดของเพลงนั้นเกินเท่านี้
BEST_WIN_RATIO, BEST_WIN_CHARS = 1.1, 20   # ข้อความใหม่ต้องชนะของเดิมชัด ๆ ไม่งั้นไม่เปลี่ยน (กันสลับไปมา)
BEST_WIN_HUMAN = 1.3          # ของเดิมคนพิมพ์+จับเวลาและตรงเสียงอยู่แล้ว (ซับของคลิปนี้เอง) ต้องชนะขาดกว่านี้
BEST_TIME_HUMAN = 60.0        # เวลาที่คนทำ: ตรงกับ FA >= เท่านี้ (หลังเลื่อน) = ใช้เวลาเดิม
BEST_TIME_SUB = 30.0          # ซับ YouTube ของคลิปนี้: เชื่อคนมากกว่า FA เว้นแต่ไม่ตรงเลยจริง ๆ
BEST_TIME_AI = 85.0           # เวลาที่เครื่องเดา (whisper/auto-cap): ต้องตรงมากกว่านี้ถึงเก็บไว้ ไม่งั้นใช้ FA
BEST_SHIFT_MIN, BEST_SHIFT_GAIN = 0.5, 15.0   # เลื่อนทั้งเพลงเมื่อเลื่อน >= 0.5 วิ และตรงขึ้น >= 15%
# เนื้อ "แค่บางช่วง" (ซับบทพูดในเอ็มวี h2nIHSgQ2Bs: 9 บรรทัด match 81 แต่คลุมเสียงร้อง 5%) — match เฉลี่ยของบรรทัดที่มี
# วัดว่า "ตรงไหม" ไม่ได้วัดว่า "ครบไหม" จึงเคยตั้งเกณฑ์ gate สูงจนเนื้อเต็มเพลงตกหมด ต้องดู 2 อย่างประกอบ:
BEST_MASS_FRAC = 0.4          # คะแนนตัวอักษร (_text_score) ไม่ถึงเท่านี้ของตัวที่มากที่สุด = เนื้อน้อย -> ห้ามตั้งเกณฑ์ gate
BEST_SPARSE_REL = 0.5         # sparse = คลุมเสียงร้อง < LC.SPARSE_COVER และ < เท่านี้ของตัวที่คลุมมากที่สุด และเนื้อน้อย
#                               (ครบทั้งสามข้อ — คลิปที่บทพูดยาว เนื้อดีคลุมได้แค่ ~35% แต่ตัวอักษรยังมากจึงไม่โดน)
BEST_AUTO_COVER = 60.0        # เนื้อเดิม sparse + ไม่มีแหล่งที่คนพิมพ์ -> ใช้ auto-caption ได้ถ้าคลุมเสียงร้องเท่านี้ขึ้นไป
BEST_AUTO_OVER = 3.0          # และตัวอักษรเข้ากับเสียงร้องมากกว่าเนื้อเดิมเท่านี้
BEST_SPARSE_V = 1             # รุ่นกติกา sparse ใน lyrics.best.json ("sv") — เพลงเก่าที่เนื้อแค่บางช่วงทำใหม่ครั้งเดียว
# ไม่มี "ขยับรายบรรทัด" ตั้งใจ: เคยลองขยับบรรทัดที่ FA เห็นต่าง 0.5-1.5 วิ ไปตาม FA
# วัดกับ 20 เพลงที่ผู้ใช้จับเวลาเอง ความตรงลดจาก 97% เหลือ 92% ทุกเพลง = ตรงนั้น FA ผิด ไม่ใช่คน
BEST_IDLE_GAP = 2.0           # งานตอนว่างเว้นระหว่างเพลง กันแหล่งออนไลน์ตัดการเชื่อมต่อ
# รุ่นของงานเลือกเนื้อ: 2 = มีขั้น "ซ่อมเวลา" (scripts/lyrics_refine.py) ต่อท้าย — ผลรุ่นเก่าถูกซ่อมเวลาย้อนหลังตอนว่าง
# (ซ่อมอย่างเดียว ไม่ดึงแหล่งใหม่ ข้อความเดิมไม่เปลี่ยน)
BEST_VERSION = 2
# ซ่อมเวลา: on = ใช้ผลเลย / dry = บันทึกข้อเสนอไว้ใน lyrics.best.json อย่างเดียว / off = ไม่ทำ
# วัดแล้ว (scripts/eval_lyrics.py): เพลงที่เวลาดีอยู่แล้วไม่ถูกแตะ 0/45, ช่วงเวลาอัดกู้คืน 26%->89%,
# ช่วงเกลี่ยเส้นตรง 24%->79%, ท่อนที่คลาดทั้งท่อน 0%->97%, รวมทั้งงานเลือกเนื้อ 76.1%->78.4% (69 เพลงอ้างอิง)
REFINE_MODE = os.environ.get("KARA_REFINE", "on")
_TH_RE = re.compile(r"[฀-๿]")
_LAT_RE = re.compile(r"[A-Za-z]")
_best_pending = _Pending("best")
_best_task: asyncio.Task | None = None
_best_state: dict[str, dict] = {}                  # videoId -> {"status": queued|working|failed, "error"}
_best_retried: set[str] = set()                    # ผลไม่ครบ (แหล่งออนไลน์เงียบ) ลองใหม่ได้ครั้งเดียวต่อรอบเปิดเซิร์ฟเวอร์
# ผู้สมัครที่ดึงไว้ล่วงหน้าระหว่างรอแยกเสียง: videoId -> (เวลา, hash เนื้อตอนดึง, ภาษา, ผู้สมัคร, คำค้น)
_best_pre: dict[str, tuple[float, str, str, list, dict]] = {}
_best_pre_task: dict[str, asyncio.Task] = {}
BEST_PRE_TTL = 900.0


def _prefetch_best(vid: str | None) -> None:
    """เพลงใหม่: ดึงแหล่งออนไลน์ + อ่านตัวหนังสือในคลิปไว้ก่อน ระหว่างที่ demucs ยังแยกเสียงอยู่ (ไม่ใช้ GPU)
    งานเลือกเนื้อเริ่มได้หลังมี vocals เท่านั้น — เดิมเริ่มแล้วค่อยนั่งรอเน็ต/OCR ต่ออีก ทั้งที่ทำล่วงหน้าได้
    เรียกจากท้ายงานหาเนื้อรอบแรกและท้ายงานโหลดวิดีโอ ตัวที่เสร็จทีหลังเป็นคนเริ่ม (ต้องมีทั้งสองอย่าง)"""
    if not vid or vid in _best_pre_task:
        return
    d = _song_dir(vid)
    if not (d / "video.mp4").is_file() or not (d / "info.json").is_file():
        return
    if _lyrfind_pending.has(vid) or _lyr_state.get(vid, {}).get("status") == "searching":
        return
    if _best_state.get(vid, {}).get("status") in ("queued", "working"):
        return                                    # งานเลือกเนื้อเริ่มเองแล้ว (แยกเสียงเสร็จก่อน)
    if not _fa_ok_cached() or _song_lang(vid)[0] not in LS.FA_LANGS:
        return
    # ยังไม่มีเนื้อรอบแรก (รอถอดเสียง) = คำค้นจากเนื้อจะเปลี่ยนหลังถอดเสียง -> ดึงแหล่งล่วงหน้าไม่ได้
    # และอย่าอ่าน OCR ล่วงหน้าด้วย: วัดแล้ว OCR (~50 วิ) ซ้อนกับ demucs/ถอดเสียงทำให้งานพวกนั้นช้าลง 10-30 วิ
    # (งานเลือกเนื้อของเพลงแบบนี้เริ่มหลังถอดเสียง แล้ว OCR ไปซ้อนกับการคำนวณเสียง FA ในงานนั้นแทน)
    gather = _best_needed(vid)
    if not gather:
        return
    for k in [k for k, v in _best_pre.items() if time.time() - v[0] > BEST_PRE_TTL]:
        del _best_pre[k]                          # เพลงที่ถูกลบจากคิวก่อนได้เทียบ — ไม่ต้องเก็บไว้
    h, lang = _lyr_hash(_read_lyr(vid)), _song_lang(vid)[0]
    hit = _best_pre.get(vid)
    if hit and hit[1:3] == (h, lang) and time.time() - hit[0] < BEST_PRE_TTL:
        return

    async def run() -> None:
        t0 = time.monotonic()
        try:
            await asyncio.to_thread(_ocr_ensure, vid, True)       # ซ้อนกับ demucs -> CPU ลำดับต่ำ (nice)
            cands, used = await asyncio.to_thread(_gather_sources, vid, "", "")
            _best_pre[vid] = (time.time(), h, lang, cands, used)
            print(f"[best] {vid} ดึงแหล่งล่วงหน้า {len(cands)} ผู้สมัคร | {time.monotonic() - t0:.0f}s{_since_add(vid)}")
        except Exception as exc:
            print(f"[best] {vid} ดึงแหล่งล่วงหน้าไม่ได้: {type(exc).__name__}: {exc}")
        finally:
            _best_pre_task.pop(vid, None)
    t = asyncio.create_task(run())
    _best_pre_task[vid] = t                       # ถือ reference ไว้ด้วย (กัน GC) และให้ _run_best รอได้


async def _best_sources(vid: str, base: str) -> tuple[list, dict, bool]:
    """ผู้สมัครของงานเลือกเนื้อ — ใช้ชุดที่ดึงล่วงหน้าถ้าเนื้อ (hash) และภาษายังเหมือนตอนดึง
    = ผู้สมัครชุดเดียวกับที่จะดึงเองตอนนี้ ผลตัดสินจึงไม่เปลี่ยน ไม่งั้นดึงใหม่แบบเดิม
    คืน (ผู้สมัคร, คำค้น, ใช้ชุดล่วงหน้าไหม)"""
    task = _best_pre_task.get(vid)
    if task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(task), 120)    # กำลังดึงอยู่ -> รอให้เสร็จ ดีกว่าดึงซ้ำ
        except Exception:
            pass
    pre = _best_pre.pop(vid, None)
    if pre and pre[1:3] == (base, _song_lang(vid)[0]) and time.time() - pre[0] < BEST_PRE_TTL:
        return pre[3], pre[4], True               # ดึงล่วงหน้าทำ OCR ก่อนดึงแหล่ง ลำดับเดียวกับข้างล่าง
    await asyncio.to_thread(_ocr_ensure, vid)          # 📷 Lyric Video: เวลาที่ตัวหนังสือขึ้นในคลิปนี้
    # ดึงเนื้อออนไลน์ก่อน (นอกช่อง GPU — รอเน็ตไม่ควรกันงานอื่น)
    cands, used = await asyncio.to_thread(_gather_sources, vid, "", "")
    return cands, used, False


def _fa_warm_text(vid: str) -> list[str]:
    """ข้อความหลอกสำหรับอุ่นแคช FA: "ก ab" (ไทย + ละติน ≥ 2 ตัว ตาม fa_align.has_latin) = ทั้งสองโมเดล
    เพลงไทยล้วนอุ่นแค่โมเดลไทย ("ก") — โมเดลอังกฤษ ~1.2 GB เคยโหลดทุกเพลงใหม่
    ผู้สมัครจาก OCR/ออนไลน์มีคำอังกฤษทีหลัง ขั้นให้คะแนนคำนวณรอบอังกฤษเองในช่อง GPU (ผลไม่เปลี่ยน)"""
    try:
        texts = list(_lyr_texts(vid))
        pre = _best_pre.get(vid)                    # ผู้สมัครที่ดึงไว้ระหว่างแยกเสียง (ชุดเดียวกับที่ขั้นให้คะแนนจะใช้)
        if pre:
            texts += [x for c in pre[3] for x in (c.get("texts") or [] if not c.get("synced")
                                                  else [l.get("x") or "" for l in c.get("lines") or []])]
        if _song_lang(vid)[0] == "en" or _fa_mod().has_latin(texts):
            return ["ก ab"]   # อุ่นสองโมเดลรอบเดียว — ไม่งั้นขั้นให้คะแนนต้องเปิดรอบอังกฤษแยกอีกรอบ
    except Exception:
        return ["ก ab"]   # ตัดสินไม่ได้ = ทำแบบเดิม
    return ["ก"]


async def _best_fa_warm(vid: str, warm_text: list[str] | None = None) -> None:
    """วิเคราะห์เสียงร้องของ FA ไว้ก่อน ระหว่างที่งานเลือกเนื้อยังรอ OCR/แหล่งออนไลน์ (ไม่ต้องรู้ผู้สมัคร)
    ได้แคชชุดเดียวกับที่ขั้นให้คะแนนจะคำนวณเอง (เสียงเดียวกัน โมเดลเดียวกัน) ผลให้คะแนนจึงไม่เปลี่ยน
    วัดแล้ว (เพลง 3.5 นาที): เปิดโปรเซสใหม่ ไทย 16 / ไทย+อังกฤษ 25 วิ · ผ่านตัวโหลดค้าง (_FaWorker) 5 / 9.6 วิ
    — เดิมเริ่มหลังได้ผู้สมัครครบ ต่อกันเป็นทอด ๆ"""
    global _heavy_job
    async with _heavy.slot(f"bestwarm:{vid}", lambda: _prio(vid) + 0.4):
        warm_text = warm_text or _fa_warm_text(vid)
        if _fa_cached_for(vid, warm_text):
            return
        _heavy_job = ("best", vid)
        try:
            await asyncio.to_thread(_fa_call, vid, {"texts": warm_text, "duration": 0}, "best")
        except Exception as exc:
            print(f"[best] {vid} เตรียมเสียง FA ไม่ได้: {type(exc).__name__}: {exc}")   # ขั้นให้คะแนนคำนวณเองอีกที
        finally:
            _heavy_job = None


LYR_TAIL_JUNK = 120.0         # วินาทีเลยท้ายคลิปที่ยังนับเป็นบรรทัดจริง (เวอร์ชันอัลบั้มยาวกว่าคลิปได้)


def _drop_tail_junk(vid: str) -> bool:
    """บรรทัดที่เวลาเลยท้ายคลิปไปไกล = เครดิต [999:00] ของ JOOX ที่ติดมากับเนื้อก่อน from_lrc กรอง (บรรทัดที่ 16 ชั่วโมง
    จอทีวีโชว์จาง ๆ เป็น "บรรทัดถัดไป" ตลอดท่อนจบ) — ลบออกครั้งเดียวตอนเปิดเซิร์ฟเวอร์ สำรองของเดิมลง 🕘 ก่อน
    ไม่แตะเนื้อที่คนใส่เอง (BEST_MANUAL) · เวลาบรรทัดอื่นไม่เปลี่ยน offset/ผลตรวจจึงยังใช้ได้ (ผู้ใช้เลือกให้ทำ 2026-10-06)"""
    j = _read_lyr(vid)
    if not j or (j.get("src") or "") in BEST_MANUAL:
        return False
    dur = float(j.get("duration") or 0) or float(_song_meta(vid)["duration"] or 0)
    L = j.get("lines") or []
    keep = [l for l in L if not (isinstance(l.get("t"), (int, float)) and l["t"] > dur + LYR_TAIL_JUNK)]
    if not dur or not keep or len(keep) == len(L):
        return False
    d = _song_dir(vid)
    _backup_lyrics(d, j)
    _write_json_atomic(d / "lyrics.json", {**j, "lines": keep})
    _lyr_cache.pop(vid, None)
    _span_cache.pop(vid, None)
    print(f"[lyr] {vid} ลบบรรทัดที่เลยท้ายคลิป {len(L) - len(keep)} บรรทัด (เครดิต [999:00] ของ JOOX) — ของเดิมอยู่ใน 🕘")
    return True


def _lyr_hash(j: dict | None) -> str:
    if not j:
        return "nolyr"
    body = json.dumps([j.get("src") or "", [[l.get("t"), l.get("d"), l.get("x")] for l in j.get("lines") or []]],
                      ensure_ascii=False)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def _read_lyr(vid: str) -> dict | None:
    try:
        return json.loads((_song_dir(vid) / "lyrics.json").read_text("utf-8"))
    except Exception:
        return None


def _best_rec(vid: str) -> dict:
    try:
        return json.loads((_song_dir(vid) / "lyrics.best.json").read_text("utf-8"))
    except Exception:
        return {}


def _best_needed(vid: str) -> bool:
    """ยังไม่เคยตัดสินเนื้อชุดนี้ -> ต้องทำ (เนื้อจากการเลือกอัตโนมัติเอง / เนื้อที่คนใส่ = ไม่ต้อง)"""
    d = _song_dir(vid)
    j = _read_lyr(vid)
    if j:
        if (j.get("src") or "") in BEST_MANUAL:
            return False
        # เนื้ออัตโนมัติที่มีแค่บางช่วง (ซับบทพูดในเอ็มวี) ตัดสินไว้ก่อนมีกติกา sparse -> ทำใหม่ครั้งเดียว
        # ต้องมาก่อนเช็ก "best" ข้างล่าง: เนื้อที่งานนี้เคยจับเวลาใหม่ (retime) มีฟิลด์ best อยู่แล้ว
        sp = LS.span_pct(j.get("lines") or [], float(j.get("duration") or 0) or float(_song_meta(vid)["duration"] or 0))
        if sp is not None and sp < LS.SPARSE_SPAN and int(_best_rec(vid).get("sv") or 0) < BEST_SPARSE_V:
            return True
        if j.get("best") and not (int(_best_rec(vid).get("v") or 1) < BEST_VERSION and REFINE_MODE != "off"):
            return False
    elif not (d / "lyrics.nolyr.json").is_file():
        return False                              # ยังหาเนื้อรอบแรกไม่เสร็จ
    rec = _best_rec(vid)
    h = _lyr_hash(j)
    if rec and h in (rec.get("base"), rec.get("out")):
        if j and int(rec.get("v") or 1) < BEST_VERSION and REFINE_MODE != "off":
            return True                           # ตัดสินไว้ก่อนมีขั้นซ่อมเวลา -> ซ่อมอย่างเดียว
        return bool(rec.get("partial")) and vid not in _best_retried
    return True


def _text_score(c: dict) -> int:
    """ตัวอักษรไทยของบรรทัดที่เข้ากับเสียงร้อง ลบ ตัวอักษรของบรรทัดที่ไม่เข้าเลย
    เนื้อครบทั้งเพลงชนะเนื้อที่ขาดท่อน / บรรทัดเกิน (เครดิต, ท่อนที่คลิปไม่มี) โดนหัก
    บรรทัดที่ไม่มีตัวไทย (อังกฤษ) โมเดลไทยวัดไม่ได้ -> ไม่นับทั้งบวกและลบ"""
    texts = [l["x"] for l in c["lines"]] if c["synced"] else c["texts"]
    good = bad = 0
    for x, cf in zip(texts, c.get("faConf") or []):
        n = len(_TH_RE.findall(x or "")) + len(_LAT_RE.findall(x or ""))   # ตัวละตินนับได้เพราะ FA ร่วมให้ conf แล้ว
        if not n or cf is None:
            continue
        if cf >= BEST_GOOD_CONF:
            good += n
        elif cf < FA_MIN_CONF:
            bad += n
    return good - bad


def _best_src(c: dict, cur: dict | None) -> str:
    p = c["provider"]
    if p == "current":
        return (cur or {}).get("src") or ""
    if p.startswith("ocr+"):                    # ข้อความของแหล่งเดิม + เวลาจากตัวหนังสือในคลิป
        p = p[4:]
        return (cur or {}).get("src") or "" if p == "current" else p
    if p == "lrclib" and not c["synced"]:
        return "lrclib-plain"
    return p


def _best_timed(c: dict) -> bool:
    """เวลาในตัวของแหล่งตรงกับเสียงร้องพอใช้ได้เลย (หลังเลื่อนทั้งเพลง)"""
    return c["synced"] and (c.get("timingAfter") or 0) >= BEST_TIME_HUMAN


def _best_pool(cands: list[dict]) -> tuple[list[dict], float, list[dict], dict | None]:
    """ให้คะแนนตัวอักษร + ติดธง sparse แล้วคืน (ผู้สมัครที่มีคะแนน, เกณฑ์ gate, ผู้สมัครที่แทนได้, ตัวที่ดีที่สุด)
    ใช้ร่วมกันระหว่างงานเลือกเนื้อ (_best_decide) กับ 🔎 ห้องหาเนื้อใน Studio (ตัวที่ระบบจะเลือกขึ้นก่อน)"""
    for c in cands:
        if c.get("faConf") is not None:
            c["score"] = _text_score(c)
    scored = [c for c in cands if "score" in c]
    mass_all = max((c["score"] for c in scored), default=0)
    mass_human = max((c["score"] for c in scored if c["provider"] not in ("yt-auto", "ocr")), default=0)
    ref_cover = max((c["cover"] for c in scored if c.get("cover") is not None
                     and (c.get("match") or 0) >= BEST_MIN_MATCH), default=None)
    for c in scored:                    # แค่บางช่วง = คลุมเสียงร้องน้อย (ทั้งตัวเลขเปล่าและเทียบตัวที่ดีที่สุด) และตัวอักษรน้อย
        cv = c.get("cover")
        c["sparse"] = bool(cv is not None and ref_cover is not None and cv < LC.SPARSE_COVER
                           and cv < BEST_SPARSE_REL * ref_cover and c["score"] < BEST_MASS_FRAC * mass_all)
    # เกณฑ์ gate ตั้งจากตัวที่ข้อความมากพอเท่านั้น — บรรทัดน้อยแต่ชัดได้ match สูงเกินจริง (บทพูด 9 บรรทัด = 81)
    gate = max(BEST_MIN_MATCH, max((c.get("match") or 0 for c in scored if c["provider"] not in ("yt-auto", "ocr")
                                    and c["score"] >= BEST_MASS_FRAC * mass_human), default=0) - BEST_MATCH_SPREAD)
    # ตัวหนังสือเครื่องถอด (yt-auto) / เครื่องอ่านจากภาพ (ocr) ไม่เอามาแทน — สะกดเพี้ยนได้
    # (เวลาจากภาพยังใช้ได้ผ่านผู้สมัคร "ocr+แหล่ง" = ข้อความของคน + เวลาที่ขึ้นจอในคลิป)
    # คะแนนเท่ากันให้ตัวที่เวลาในตัวตรงเสียงชนะ
    pool = [c for c in scored if c["provider"] not in ("current", "yt-auto", "ocr") and not c["sparse"]
            and (c.get("match") or 0) >= gate and c.get("faLines")]
    top = max(pool, key=lambda c: (c["score"] * (1.03 if _best_timed(c) else 1.0), c.get("match") or 0)) \
        if pool else None
    return scored, gate, pool, top


def _best_decide(cands: list[dict], cur: dict | None) -> dict:
    """ตัดสินจากผลให้คะแนนของ FA (ฟังก์ชันล้วน — ทดลองกับทั้งคลังได้โดยไม่เขียนไฟล์)
    คืน {"action": keep|shift|retime|newtext|found|none, "reason", "cand", "lines", "timeSrc", "shift"}"""
    scored, gate, pool, top = _best_pool(cands)
    timed = _best_timed
    cur_c = next((c for c in scored if c["provider"] == "current"), None)
    cur_src = (cur or {}).get("src") or ""
    cur_ts = LC.time_src_of(cur) if cur else ""
    thin = ""                                     # เหตุผลถ้าเนื้อเดิมมีแค่บางช่วง
    if cur_c is None:
        if cur:                                   # FA ให้คะแนนเนื้อเดิมไม่ได้ (เช่นภาษาอื่นล้วน) = ไม่แตะ
            return {"action": "keep", "reason": "วัดเนื้อเดิมกับเสียงร้องไม่ได้"}
        if top and top["score"] >= 200:
            chosen, action = top, "found"
        else:
            return {"action": "none", "reason": "ไม่เจอเนื้อที่เข้ากับเสียงร้องจากทุกแหล่ง"}
    elif cur_c.get("sparse"):
        # เนื้อเดิมแค่บางช่วง (ซับบทพูด/4 บรรทัดจากคำอธิบาย): ตัดสินแบบไม่มีเนื้อเดิม — กฎ "ของเดิมต้องแพ้ขาด" ไม่ใช้
        # ไม่มีแหล่งที่คนพิมพ์ผ่านเกณฑ์ -> คำบรรยายอัตโนมัติที่คลุมทั้งเพลง (ลำดับเดียวกับ gen_lyrics) ดีกว่าจอค้าง ♪ ทั้งเพลง
        thin = f"เนื้อเดิมมีแค่บางช่วง (คลุมเสียงร้อง {cur_c['cover']:.0f}%)"
        autos = [c for c in scored if c["provider"] == "yt-auto" and c.get("faLines")
                 and (c.get("cover") or 0) >= BEST_AUTO_COVER and (c.get("match") or 0) >= BEST_MIN_MATCH
                 and c["score"] >= BEST_AUTO_OVER * max(cur_c["score"], 1)]
        if top and top["score"] >= 200:
            chosen, action = top, "newtext"
        elif autos:
            chosen, action = max(autos, key=lambda c: c["score"]), "newtext"
        else:
            chosen, action = cur_c, "keep"
    else:
        cs = cur_c["score"]
        chosen, action = cur_c, "keep"
        if top:
            # FA ตัดสินเพลงนี้ไม่ได้ (ภาษาที่ไม่มีโมเดล) -> อย่าเปลี่ยน — เนื้อญี่ปุ่นได้คะแนนน้อยเพราะ FA อ่านไม่ออก
            # ไม่ใช่เพราะเนื้อน้อย (ลองยกเว้นตอนตัวใหม่ตัวอักษรมากกว่า 3 เท่าแล้ว เพลงญี่ปุ่นถูกเปลี่ยนเป็นโรมาจิ)
            # เนื้อ 4 บรรทัดของ ahkGRFhyxx4 ที่เคยติดกฎนี้ ไปทาง sparse ข้างบนแทน
            weak = (cur_c.get("match") or 0) < 30 and (top.get("match") or 0) < 45
            if weak:
                win = False
            elif cur_src == "yt-auto":            # ตัวหนังสือเครื่องถอด -> เนื้อที่คนพิมพ์ชนะง่ายกว่า
                win = top["score"] >= 0.9 * cs
            elif cur_ts == "self" and timed(cur_c):
                win = top["score"] >= cs * BEST_WIN_HUMAN and top["score"] >= cs + 3 * BEST_WIN_CHARS
            elif timed(top) and not timed(cur_c) and top["score"] >= 0.95 * cs:
                win = True                        # ข้อความเท่า ๆ กัน แต่ตัวนี้มีเวลาที่คนจับและตรงเสียง ของเดิมเวลาเดา
            else:
                win = top["score"] >= cs * BEST_WIN_RATIO and top["score"] >= cs + BEST_WIN_CHARS
            if win:
                chosen, action = top, "newtext"
    # --- เวลา: เวลาในตัวของแหล่ง (ถ้าตรงกับเสียงร้องพอ) หรือจับใหม่ด้วย FA
    if chosen is cur_c and (cur_ts in ("asr", "auto-cap") or cur_src == "yt-auto"):
        need = BEST_TIME_AI
    elif chosen is cur_c and cur_src == "yt-sub":
        need = BEST_TIME_SUB
    else:
        need = BEST_TIME_HUMAN
    ta, t0 = chosen.get("timingAfter"), chosen.get("timing")
    shift = chosen.get("shift") or 0.0
    if chosen["synced"] and ta is not None and ta >= need:
        lines = [dict(l) for l in chosen["lines"]]
        use_shift = abs(shift) >= BEST_SHIFT_MIN and (ta - (t0 or 0)) >= BEST_SHIFT_GAIN
        if use_shift:
            for l in lines:
                l["t"] = round(max(0.0, l["t"] + shift), 2)
            if action == "keep":
                action = "shift"
        tsrc = cur_ts if chosen is cur_c else "self"
        why_t = f"เวลาในตัวตรงกับเสียงร้อง {ta:.0f}%" + (f" หลังเลื่อน {shift:+.2f} วิ" if use_shift else "")
    elif chosen.get("faLines"):
        lines = [dict(l) for l in chosen["faLines"]]
        tsrc = "fa"
        if action == "keep":
            action = "retime"
        use_shift = False
        why_t = "จับเวลาใหม่ด้วย FA" + (f" (เวลาเดิมตรงแค่ {ta:.0f}%)" if ta is not None else "")
    else:
        return {"action": "keep", "reason": (thin + " แต่ " if thin else "") + "FA จับเวลาเนื้อนี้ไม่ได้"}
    if action == "keep":
        why_k = f"{thin} — ไม่เจอแหล่งที่ครบกว่า" if thin else "เนื้อเดิมดีที่สุดแล้ว"
        return {"action": "keep", "reason": f"{why_k} · {why_t}", "cand": chosen, "score": ta,
                "shift": shift if not use_shift and abs(shift) >= 0.3 else 0.0}
    if thin and action == "newtext":
        cv = chosen.get("cover")
        why_x = f"{thin} · ใช้ {chosen['label']}" + (f" (คลุม {cv:.0f}%)" if cv is not None else "")
    else:
        why_x = {"newtext": f"ข้อความจาก {chosen['label']} เข้ากับเสียงร้องมากกว่า ({chosen['score']} vs "
                            f"{cur_c['score'] if cur_c else 0} ตัวอักษร)",
                 "found": f"เจอเนื้อจาก {chosen['label']}"}.get(action, "")
    return {"action": action, "reason": " · ".join(x for x in (why_x, why_t) if x), "cand": chosen,
            "lines": lines, "src": _best_src(chosen, cur), "timeSrc": tsrc, "shift": shift if use_shift else 0.0,
            "score": ta}


def _best_apply(vid: str, dec: dict, cur: dict | None) -> str:
    """เขียนเนื้อที่เลือก + สำรองของเดิม (เห็นใน 🕘 ประวัติของ Studio) คืน hash ของเนื้อใหม่"""
    d = _song_dir(vid)
    _backup_lyrics(d, cur)
    lines = []
    for l in dec["lines"]:
        x = " ".join(str(l.get("x") or "").split())
        if x:
            ln = {"t": round(max(0.0, float(l["t"])), 2),
                  "d": round(max(0.3, min(30.0, float(l.get("d") or 3.0))), 2), "x": x}
            v = _voice_of(l.get("v"))
            if v:
                ln["v"] = v
            lines.append(ln)
    lines.sort(key=lambda l: l["t"])
    if not lines:
        raise RuntimeError("เนื้อที่เลือกว่างเปล่า")
    c = dec["cand"]
    dur = float((cur or {}).get("duration") or _song_meta(vid)["duration"] or 0.0)
    out = {"v": 1, "videoId": vid, "lang": "th", "engine": "PU KARAOKE auto-best",
           "src": dec["src"], "timeSrc": dec["timeSrc"], "duration": round(dur, 2), "lines": lines,
           "best": {"action": dec["action"], "from": (cur or {}).get("src") or "", "label": c.get("label") or "",
                    "match": c.get("match"), "score": c.get("score"), "timing": c.get("timingAfter"),
                    "shift": dec.get("shift") or 0.0, "at": int(time.time())}}
    _write_json_atomic(d / "lyrics.json", out)
    # ผลตรวจ/offset/หมุดไม่มีเนื้อ อ้างเนื้อชุดเก่า — ค้างไว้จะขึ้นป้ายผิดหรือเลื่อนซ้ำ
    for name in ("lyrics.check.json", "lyrics.nolyr.json", "lyrics.offset.json"):
        (d / name).unlink(missing_ok=True)
    _lyr_cache.pop(vid, None)
    _chk_cache.pop(vid, None)
    _off_cache.pop(vid, None)
    _lyr_state[vid] = {"status": "ready", "error": ""}
    return _lyr_hash(out)


def _best_record(vid: str, base: str, out: str, dec: dict, cands: list[dict], partial: bool,
                 refine: dict | None = None) -> None:
    rec = {"v": BEST_VERSION, "sv": BEST_SPARSE_V, "at": int(time.time()), "base": base, "out": out,
           "action": dec["action"], "reason": dec["reason"], "partial": partial,
           **({"refine": refine} if refine else {}),
           "cands": [{k: c.get(k) for k in ("provider", "label", "synced", "match", "score", "timing",
                                             "timingAfter", "shift", "cover", "sparse")} for c in cands]}
    _write_json_atomic(_song_dir(vid) / "lyrics.best.json", rec)


async def _ensure_bester() -> None:
    global _best_task
    if _best_task is None or _best_task.done():
        _best_task = asyncio.create_task(_best_worker())


async def _enqueue_best(vid: str | None, force: bool = False) -> bool:
    """เข้าคิวเลือกเนื้อดีที่สุด — รอ vocals ก่อนเหมือนเวลารายคำ (แคช FA ผูกกับเสียงชุดแรกที่วิเคราะห์)"""
    if not vid or not _fa_ok_cached() or _song_lang(vid)[0] not in LS.FA_LANGS:
        return False                              # ญี่ปุ่น/เกาหลี/ฯลฯ ยังไม่มีโมเดล FA ให้เทียบ
    if _best_pending.has(vid) or _best_state.get(vid, {}).get("status") == "working":
        return False
    j = _read_lyr(vid)
    if j and (j.get("src") or "") in BEST_MANUAL:
        return False                              # เนื้อที่คนใส่เอง ห้ามแตะแม้กดสั่ง
    if not force:
        if _best_state.get(vid, {}).get("status") == "failed" or not _best_needed(vid):
            return False
        if not _has_stems(vid) and _sep_state.get(vid, {}).get("status") != "failed" \
                and not _fa_cached(vid):
            return False                          # เดี๋ยว _sep_worker สั่งให้เองตอนได้ vocals
    elif not j and not (_song_dir(vid) / "lyrics.nolyr.json").is_file():
        return False
    if not _audio_for(vid):
        return False
    await _ensure_bester()
    _best_state[vid] = {"status": "queued", "error": "", "q": time.monotonic()}   # q = เวลาเข้าคิว (log)
    _best_pending.push(vid)
    return True


async def _best_worker() -> None:
    while True:
        await _best_pending.wait()
        hit = _best_pending.best()
        if not hit:
            continue
        vid, rank = hit
        _best_pending.discard(vid)
        await _run_best(vid)
        await room.broadcast()
        if rank >= _BACKLOG:
            await asyncio.sleep(BEST_IDLE_GAP)


def _check_now(vid: str, kind: str = "verify") -> None:
    """ตรวจเวลา v2 ของเนื้อปัจจุบันแล้วเขียน lyrics.check.json (พังก็แค่ไม่มีผลตรวจ ไม่ลากงานอื่น)"""
    try:
        j = _read_lyr(vid) or {}
        L = j.get("lines") or []
        if not L or _song_lang(vid)[0] not in LS.FA_LANGS or not _fa_cached_for(vid, [l.get("x") or "" for l in L]):
            return
        m = _fa_measure2(vid, L, _lyr_offset(vid), float(j.get("duration") or 0), kind)
        _write_check(vid, m["score"], m["shift"], "fa", m["n"], v2=m)
    except Exception as exc:
        print(f"[check] {vid} {type(exc).__name__}: {exc}")


def _refine_rec(ref: dict | None) -> dict | None:
    if not ref:
        return None
    return {**(ref.get("record") or {}), "note": ref.get("note") or "", "changed": bool(ref.get("changed")),
            "mode": REFINE_MODE}


async def _refine_dec(vid: str, dec: dict, cur: dict | None, cands: list[dict]) -> dict | None:
    """ขั้นซ่อมเวลาหลังตัดสินเลือกเนื้อ: แก้ dec ในที่ (ใช้ผลเมื่อ REFINE_MODE = on) คืนผลซ่อมไว้บันทึก"""
    if REFINE_MODE == "off" or dec["action"] == "none":
        return None
    if dec["action"] == "keep":
        if not cur or not cur.get("lines"):
            return None
        lines, tsrc = cur["lines"], LC.time_src_of(cur)
    else:
        lines, tsrc = dec.get("lines") or [], dec.get("timeSrc") or ""
    ref = await asyncio.to_thread(_refine_call, vid, lines, tsrc)
    if not ref or not ref.get("changed") or REFINE_MODE != "on":
        return ref
    if dec["action"] == "keep":
        cur_c = next((c for c in cands if c["provider"] == "current"), None) or {"label": "เนื้อเดิม"}
        dec.update({"action": "refine", "cand": cur_c, "src": cur.get("src") or "", "timeSrc": tsrc, "shift": 0.0})
    dec["lines"] = ref["lines"]
    dec["reason"] = " · ".join(x for x in (dec.get("reason") or "", "ซ่อมเวลา: " + (ref.get("note") or "")) if x)
    return ref


async def _refine_only(vid: str, cur: dict, rec0: dict, base: str, t0: float) -> None:
    """ผลเลือกเนื้อรุ่นก่อนมีขั้นซ่อมเวลา -> ซ่อมเวลาของเนื้อปัจจุบันอย่างเดียว (ไม่ดึงแหล่ง ไม่เปลี่ยนข้อความ)"""
    tsrc = LC.time_src_of(cur)
    ref = await asyncio.to_thread(_refine_call, vid, cur.get("lines") or [], tsrc)
    if _lyr_hash(_read_lyr(vid)) != base:
        _best_state.pop(vid, None)
        return
    out = base
    if ref and ref.get("changed") and REFINE_MODE == "on":
        b = cur.get("best") or {}
        dec = {"action": "refine", "reason": "ซ่อมเวลา: " + (ref.get("note") or ""), "lines": ref["lines"],
               "src": cur.get("src") or "", "timeSrc": tsrc, "shift": 0.0,
               "cand": {"label": b.get("label") or "เนื้อเดิม", "match": b.get("match"), "score": b.get("score"),
                        "timingAfter": b.get("timing")}}
        out = await asyncio.to_thread(_best_apply, vid, dec, cur)
        room.archive_rev += 1
    rec = {**rec0, "v": BEST_VERSION, "at": int(time.time()), "out": out, "refine": _refine_rec(ref)}
    if out != base:
        rec.update({"base": base, "action": "refine", "reason": "ซ่อมเวลา: " + (ref.get("note") or "")})
    await asyncio.to_thread(_write_json_atomic, _song_dir(vid) / "lyrics.best.json", rec)
    _best_state.pop(vid, None)
    if out != base:
        await asyncio.to_thread(_check_now, vid, "best")
        await _enqueue_words(vid, force=True)       # เวลาบรรทัดเปลี่ยน -> หมุดของเวลารายคำเปลี่ยน ทำไล่สีใหม่
    print(f"[best] {vid} ซ่อมเวลา: {(ref or {}).get('note') or 'ไม่มีอะไรต้องแก้'} | {time.monotonic() - t0:.0f}s")


async def _run_best(vid: str) -> None:
    global _heavy_job
    retimed = False                                # เวลาบรรทัดเปลี่ยน (เปลี่ยนเนื้อ/เลื่อน/จับใหม่/ซ่อม) -> ทำไล่สีใหม่
    q_at = _best_state.get(vid, {}).get("q")
    _best_state[vid] = {"status": "working", "error": ""}
    await room.broadcast()
    t0 = time.monotonic()
    # เวลาแต่ละขั้น (log) — ไว้ดูว่าเนื้อของเพลงใหม่ช้าตรงไหน
    ph: dict[str, float] = {"รอคิว": t0 - q_at} if q_at else {}
    shown = ""                                     # เนื้อใหม่ขึ้นจอเมื่อไร (นับจากกดเพิ่ม)

    def lap(k: str, t: float) -> float:
        now = time.monotonic()
        ph[k] = ph.get(k, 0.0) + now - t
        return now
    try:
        cur = _read_lyr(vid)
        if cur and (cur.get("src") or "") in BEST_MANUAL:
            _best_state.pop(vid, None)
            return
        base = _lyr_hash(cur)
        rec0 = _best_rec(vid)
        if cur and rec0 and base in (rec0.get("base"), rec0.get("out")) and int(rec0.get("v") or 1) < BEST_VERSION:
            await _refine_only(vid, cur, rec0, base, t0)      # ตัดสินไว้แล้วก่อนมีขั้นซ่อมเวลา: ซ่อมอย่างเดียว
            return
        t = time.monotonic()
        # OCR + แหล่งออนไลน์ (ดึงล่วงหน้าไว้แล้วถ้าทัน) ไปพร้อมกับวิเคราะห์เสียงร้องของ FA
        warm = None
        if not _fa_cached(vid):
            # ตัดสินว่าต้องอุ่นโมเดลอังกฤษไหมตอนนี้ — _best_sources ข้างล่างจะหยิบผู้สมัครล่วงหน้าออกจาก _best_pre ไป
            warm = asyncio.create_task(_best_fa_warm(vid, _fa_warm_text(vid)))
            _bg_tasks.add(warm)                    # อาจยังคำนวณรอบอังกฤษต่อหลังงานนี้จบ — ถือ reference ไว้
            warm.add_done_callback(_bg_tasks.discard)
        # แผนที่เสียงร้อง (ffmpeg + CPU 2-4 วิครั้งแรก) ไว้วัดว่าผู้สมัครคลุมเสียงร้องกี่ % — ทำใน thread ซ้อนกับ OCR/แหล่ง/FA
        # (ขั้นซ่อมเวลาข้างล่างก็ใช้แคชชุดนี้ต่อ)
        va_task = asyncio.create_task(asyncio.to_thread(_va_for, vid))
        cands, used, pre = await _best_sources(vid, base)
        t = lap("แหล่ง(ดึงไว้ก่อน)" if pre else "ocr+แหล่ง", t)
        online = sum(1 for c in cands if c["provider"] in ONLINE_PROVIDERS)
        sets = [(c["texts"] if not c["synced"] else [l["x"] for l in c["lines"]]) for c in cands]
        payload = {"sets": sets, "duration": _song_meta(vid)["duration"] or 0}
        texts_all = [x for st in sets for x in st]
        if warm is not None and cands and not _fa_cached_for(vid, texts_all):
            await warm                             # กำลังคำนวณแคชที่ต้องใช้อยู่ -> รอ ดีกว่าต่อคิวคำนวณซ้ำ
            t = lap("รอเสียงFA", t)
        if not cands:
            r = {"results": []}
        elif _fa_cached_for(vid, texts_all):
            r = await asyncio.to_thread(_fa_call, vid, payload, "best")
        else:
            async with _heavy.slot("best", lambda: _prio(vid) + 0.4):
                t = lap("รอGPU", t)
                _heavy_job = ("best", vid)
                try:
                    r = await asyncio.to_thread(_fa_call, vid, payload, "best")
                finally:
                    _heavy_job = None
        t = lap("FA", t)
        _score_fa(cands, r.get("results") or [], va=await va_task, off=_lyr_offset(vid))
        _src_cache[(vid, "", "")] = (time.time(), (cands, used))     # ห้องหาเนื้อใน Studio เปิดแล้วเห็นเลย
        dec = _best_decide(cands, cur)
        ref = await _refine_dec(vid, dec, cur, cands)
        t = lap("ซ่อม", t)
        if _lyr_hash(_read_lyr(vid)) != base:
            _best_state.pop(vid, None)             # เนื้อถูกเปลี่ยนระหว่างทำ (Studio/หาเนื้อใหม่) -> ทิ้งผลนี้
            print(f"[best] {vid} เนื้อเปลี่ยนระหว่างเทียบ ข้ามรอบนี้")
            return
        out = base
        if dec["action"] not in ("keep", "none"):
            out = await asyncio.to_thread(_best_apply, vid, dec, cur)
            room.archive_rev += 1
            retimed = True
            ta = _added_at.get(vid)
            shown = f" · เนื้อใหม่ขึ้นจอหลังกดเพิ่ม {time.monotonic() - ta:.0f}s" if ta else ""
        # ผลตรวจ v2 ของเนื้อที่ได้จริง (แคชเสียงพร้อมแล้ว = CPU ไม่กี่วิ) — เดิมใช้ค่าจากตอนให้คะแนนแบบไม่มีหมุด
        t = time.monotonic()
        if dec["action"] != "none":
            await asyncio.to_thread(_check_now, vid, "best")
        lap("ตรวจ", t)
        partial = online == 0
        if partial:
            _best_retried.add(vid)
        await asyncio.to_thread(_best_record, vid, base, out, dec, cands, partial, _refine_rec(ref))
        _best_state.pop(vid, None)
        steps = " · ".join(f"{k} {v:.0f}" for k, v in ph.items() if v >= 0.5)
        print(f"[best] {vid} {dec['action']}: {dec['reason']} | ผู้สมัคร {len(cands)} (ออนไลน์ {online})"
              f" | {time.monotonic() - t0:.0f}s ({steps}){shown or _since_add(vid)}")
    except Exception as exc:
        _best_state[vid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
        print(f"[best] {vid} FAILED: {exc}")
    # ข้อความสุดท้ายนิ่งแล้ว -> ทำเวลารายคำต่อ (เวลาบรรทัดเปลี่ยน = หมุดเปลี่ยน ต้องทำใหม่แม้ข้อความเดิม)
    await _enqueue_words(vid, force=retimed)


def _refine_call(vid: str, lines: list[dict], tsrc: str, segments: bool = True) -> dict | None:
    """scripts/lyrics_refine.py (subprocess) -> {"lines", "record", "note", "changed"} / None ถ้าทำไม่ได้
    ใช้แคช FA ที่มีอยู่แล้วเท่านั้น (ยังไม่มีแคช = ไม่ทำ จะได้ไม่แย่ง GPU นอกคิว)"""
    audio = _audio_for(vid)
    texts = [l.get("x") or "" for l in lines]
    if not audio or len(lines) < 2 or not _fa_cached_for(vid, texts):
        return None
    payload = {"lines": [{k: l[k] for k in ("t", "d", "x", "v") if k in l} for l in lines], "timeSrc": tsrc,
               "duration": _song_meta(vid)["duration"] or 0, "audio": str(audio), "segments": segments}
    try:
        rc, out, err = _run_child("refine", vid, [sys.executable, str(BASE / "scripts" / "lyrics_refine.py"), vid],
                                  timeout=300, input=json.dumps(payload, ensure_ascii=False), cwd=str(BASE))
        if rc != 0:
            tail = [l for l in err.strip().splitlines() if l.strip()]
            print(f"[refine] {vid} ล้มเหลว: {tail[-1][:200] if tail else rc}")
            return None
        r = json.loads(out.strip().splitlines()[-1])
        for a, b in zip(lines, r.get("lines") or []):      # เสียงของบรรทัด (v) ไม่ผ่านตัวซ่อม — คืนให้ครบ
            if "v" in a and "v" not in b:
                b["v"] = a["v"]
        return r
    except Exception as exc:
        print(f"[refine] {vid} {type(exc).__name__}: {exc}")
        return None


_act_locks: dict[str, asyncio.Lock] = {}


@app.post("/api/studio/song/{vid}/action")
async def studio_action(vid: str, request: Request):
    """ปุ่มซ่อมใน Studio — ใช้ได้กับทุกเพลงในเครื่อง ไม่ต้องอยู่ในคิว
    (ws fix/relyr ผูกกับการ์ดในคิว จึงสั่งเพลงที่ไม่อยู่ในห้องไม่ได้)"""
    _studio_guard(request)
    d = _studio_vid(vid)
    body = await request.json()
    do = body.get("do")
    msg = ""
    # ห้ามถือ room.lock ระหว่างทำคำสั่ง: ปุ่มตั้งภาษารอ yt-dlp ดึงซับ, ปุ่มตรวจภาษารอคิว GPU (อาจนานเท่า demucs
    # ทั้งเพลง) — ของเดิมถือไว้ตลอด add/next/ended จากทุกเครื่องจึงค้างหมด เพลงจบแล้วไม่ขึ้นเพลงถัดไป
    # คำสั่งพวกนี้ไม่แตะ queue/current เลย ใช้ lock ต่อเพลงแทน (ปุ่มของเพลงเดียวกันทำทีละอัน)
    async with _act_locks.setdefault(vid, asyncio.Lock()):
        if do == "fix":
            what, why = _fix_target(vid)
            if what:
                await _do_fix(vid)
                msg = f"สั่งซ่อมขั้น {what}: {why}"
            else:
                msg = "ไม่เจอขั้นที่พังค้าง — เลือกปุ่มซ่อมเฉพาะขั้นได้"
        elif do == "redl":
            for name in ("video.mp4", "audio.m4a"):
                (d / name).unlink(missing_ok=True)
            _dl_fails.pop(vid, None)
            _dl_state.pop(vid, None)
            _dl_scrub(d)
            _invalidate_dirs()
            await _ensure_downloader()
            _dl_pending.push(vid)
            msg = "เข้าคิวโหลดใหม่แล้ว"
        elif do == "resep":
            for f in _stem_paths(vid):
                f.unlink(missing_ok=True)
            _drop_key_files(vid)                       # สเต็มใหม่ = ไฟล์คีย์เก่าใช้ไม่ได้
            _sep_state.pop(vid, None)
            await _enqueue_sep(vid)
            msg = "เข้าคิวแยกเสียงใหม่แล้ว" if (d / "audio.m4a").is_file() else "ยังไม่มีไฟล์เสียง ต้องโหลดก่อน"
        elif do == "relyr":
            await _relyr(vid)
            msg = "เข้าคิวหาเนื้อใหม่แล้ว" + (" (จะได้เนื้อที่แก้เองกลับมา)" if (LYRICS_IN / f"{vid}.json").is_file() else "")
        elif do == "verify":
            if _lyr_meta(vid)[1] <= 0:
                msg = "ยังไม่มีเนื้อให้ตรวจ"
            else:
                await _enqueue_verify(vid)
                msg = "เข้าคิวตรวจเวลาเนื้อแล้ว"
        elif do == "drop-edit":
            (LYRICS_IN / f"{vid}.json").unlink(missing_ok=True)
            await _relyr(vid)
            msg = "เลิกใช้เนื้อที่แก้เองแล้ว กำลังหาเนื้อจากแหล่งเดิม"
        elif do == "asrtext":
            # AI จับเวลาไม่ได้เพราะยังไม่เคยถอดเสียง -> ส่งข้อความเข้าทาง manual-txt เดิม (ใช้ GPU)
            texts = [" ".join(str(x).split()) for x in (body.get("texts") or [])]
            texts = [x for x in texts if x]
            if not texts:
                raise HTTPException(status_code=400, detail="ไม่มีข้อความ")
            LYRICS_IN.mkdir(exist_ok=True)
            (LYRICS_IN / f"{vid}.txt").write_text("\n".join(texts) + "\n", encoding="utf-8")
            (LYRICS_IN / f"{vid}.json").unlink(missing_ok=True)
            lrc = LYRICS_IN / f"{vid}.lrc"
            if lrc.is_file():                    # .lrc มาก่อน .txt -> พักไว้ ไม่ลบทิ้ง
                lrc.replace(lrc.with_name(lrc.name + ".old"))
            await _relyr(vid)
            msg = "ส่งเข้าคิวถอดเสียงร้องแล้ว เสร็จแล้วเนื้อจะเปลี่ยนเอง"
        elif do == "words":
            if _lyr_meta(vid)[1] <= 0:
                msg = "ยังไม่มีเนื้อ"
            elif not _fa_ok_cached():
                msg = "ยังไม่ได้ติดตั้งโมเดล FA"
            else:
                _words_state.pop(vid, None)
                ok = await _enqueue_words(vid, force=True)
                msg = "เข้าคิวทำเวลารายคำแล้ว" if ok else "อยู่ในคิวแล้ว / ไม่มีไฟล์เสียง"
        elif do == "best":
            j = _read_lyr(vid)
            if j and (j.get("src") or "") in BEST_MANUAL:
                msg = "เนื้อนี้แก้เอง/วางไฟล์เอง — ระบบไม่เปลี่ยนให้ (ใช้ 🔎 หาเนื้อ เลือกเองได้)"
            elif not _fa_ok_cached():
                msg = "ยังไม่ได้ติดตั้งโมเดล FA"
            else:
                _best_state.pop(vid, None)
                _best_retried.discard(vid)
                ok = await _enqueue_best(vid, force=True)
                msg = "เข้าคิวเทียบเนื้อจากทุกแหล่งแล้ว" if ok else "อยู่ในคิวแล้ว / ยังไม่มีเนื้อหรือไฟล์เสียง"
        elif do == "best-all":
            if not _fa_ok_cached():
                msg = "ยังไม่ได้ติดตั้งโมเดล FA"
            else:
                n = 0
                for v in sorted(_dir_index()):
                    if _best_state.get(v, {}).get("status") == "failed":
                        _best_state.pop(v, None)
                    if await _enqueue_best(v):
                        n += 1
                msg = f"เข้าคิวเทียบเนื้อ {n} เพลง" if n else "ทุกเพลงที่ทำได้ เทียบแล้ว"
        elif do == "lang":
            lang = LS.norm_lang(body.get("lang"))
            if not lang:
                raise HTTPException(status_code=400, detail="รหัสภาษาไม่ถูกต้อง")
            LS.write_lang(d, lang, "manual")
            _lang_cache.pop(vid, None)
            j = _read_lyr(vid)
            if j and (j.get("src") or "") in BEST_MANUAL:
                msg = f"ตั้งภาษาเป็น {lang} แล้ว (เนื้อที่แก้เองไม่ถูกแตะ)"
            else:
                await asyncio.to_thread(_fetch_subs, d, vid, lang)
                await asyncio.to_thread(_fetch_auto_caption, d, vid)
                await _relyr(vid)
                msg = f"ตั้งภาษาเป็น {lang} แล้ว กำลังหาเนื้อใหม่ด้วยภาษานี้"
        elif do == "detect-lang":
            (d / "lang.json").unlink(missing_ok=True)
            _lang_cache.pop(vid, None)
            lang = await _ensure_lang(vid)
            msg = f"ตรวจแล้ว: ภาษา {lang} ({_song_lang(vid)[1]})"
        elif do == "words-all":
            if not _fa_ok_cached():
                msg = "ยังไม่ได้ติดตั้งโมเดล FA"
            else:
                n = 0
                for v in sorted(_dir_index()):
                    if _words_state.get(v, {}).get("status") == "failed":
                        _words_state.pop(v, None)
                    if await _enqueue_words(v):
                        n += 1
                msg = f"เข้าคิวทำเวลารายคำ {n} เพลง" if n else "ทุกเพลงที่ทำได้มีเวลารายคำแล้ว"
        else:
            raise HTTPException(status_code=400, detail="คำสั่งไม่รู้จัก")
    async with room.lock:
        await _reprioritize()
    print(f"[studio] {vid} {do}: {msg}")
    await room.broadcast()
    return {"ok": True, "msg": msg}


def _purge_song_files(vid: str, d: Path, edits: bool) -> list[str]:
    """ลบเพลงออกจากดิสก์จริง: โฟลเดอร์ในคลัง + แคชทุกที่ที่ตั้งชื่อตาม videoId
    (ทำใน thread — rmtree ของเพลงหนึ่งมีไฟล์สื่อหลายสิบ MB)
    edits=True ถึงจะลบเนื้อที่คนแก้เองใน lyrics-in ด้วย — ปกติเก็บไว้ โหลดเพลงนี้ใหม่จะได้เนื้อเดิมกลับมา"""
    gone: list[str] = []
    if _in_archive(d) and d.is_dir():          # ด่านสุดท้ายก่อน rmtree: ต้องเป็นลูกตรงของคลังเท่านั้น
        shutil.rmtree(d, ignore_errors=True)
        gone.append("song")
    pv = SEG_CACHE.parent                       # lyrics-preview/ (อ้างผ่าน SEG_CACHE ให้ harness ทดสอบชี้ที่อื่นได้)
    groups: list[tuple[str, list[Path]]] = [
        ("seg", [SEG_CACHE / f"{vid}.json", *SEG_CACHE.glob(f"{vid}.*.json")]),
        ("fa", list((pv / "_fa").glob(f"{vid}.*"))),
        ("va", list((pv / "_va").glob(f"{vid}.*"))),
        ("src", list((pv / "_src").glob(f"{vid}.*"))),
        ("srt", list((pv / "_srt").glob(f"{vid}.*"))),
        ("preview", list(pv.glob(f"*[[]{vid}[]]*"))),
        ("thumb", [THUMB_CACHE / f"{vid}.jpg"]),
    ]
    if edits:
        groups.append(("edits", list(LYRICS_IN.glob(f"{vid}.*"))))
    for name, files in groups:
        n = 0
        for f in files:
            try:
                if f.is_file():
                    f.unlink()
                    n += 1
            except OSError:
                pass
        if n:
            gone.append(f"{name}×{n}")
    return gone


@app.delete("/api/studio/song/{vid}")
async def studio_delete(vid: str, request: Request, edits: int = 0):
    """ปุ่ม 🗑 ลบออกจากเครื่อง ใน Studio — ลบโฟลเดอร์เพลง + แคชทั้งหมด (ย้อนกลับไม่ได้)
    ประวัติการร้อง (history) ไม่แตะ: กดจากประวัติในรีโมทจะโหลดใหม่ตามปกติ
    ?edits=1 = ลบเนื้อที่แก้เองใน lyrics-in ด้วย (Studio ถามทุกครั้ง)"""
    _studio_guard(request)
    d = _studio_vid(vid)
    if not _in_archive(d):
        raise HTTPException(status_code=400, detail="โฟลเดอร์เพลงอยู่นอกคลัง — ไม่ลบ")
    async with room.lock:
        if room.current and room.current.get("videoId") == vid:
            raise HTTPException(status_code=409, detail="เพลงนี้กำลังเล่นอยู่ — ข้ามเพลงก่อนแล้วค่อยลบ")
        n_q = sum(1 for q in room.queue if q.get("videoId") == vid)
        room.queue = [q for q in room.queue if q.get("videoId") != vid]
        room.auto_recent = [v for v in room.auto_recent if v != vid]
    async with _act_locks.setdefault(vid, asyncio.Lock()):
        # งานเบื้องหลังของเพลงนี้ที่กำลังรัน (demucs/whisper/yt-dlp) ต้องตายก่อน ไม่งั้นเขียนไฟล์กลับลงโฟลเดอร์ที่ลบไปแล้ว
        with _children_lock:
            procs = [p for _k, v, p in _children.values() if v == vid]
        if procs:
            _sep_gone.add(vid)        # ก่อนฆ่า — demucs ที่ตายจากการลบห้ามไปเปิดตัวใหม่บน cpu
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        for q in (_dl_pending, _sep_pending, _lyr_pending, _lyrfind_pending, _words_pending, _best_pending):
            q.discard(vid)
        for st in (_dl_state, _sep_state, _lyr_state, _words_state, _best_state, _verify_state, _key_state,
                   _dl_fails, _meta_cache, _lyr_cache, _chk_cache, _off_cache, _lang_cache):
            st.pop(vid, None)
        _lyr_nosrc.discard(vid)
        _best_retried.discard(vid)
        gone = await asyncio.to_thread(_purge_song_files, vid, d, bool(edits))
    _act_locks.pop(vid, None)
    _invalidate_dirs()
    room.archive_rev += 1
    async with room.lock:
        await _reprioritize()
    msg = "ลบออกจากเครื่องแล้ว" + (f" (เอาออกจากคิว {n_q} รายการ)" if n_q else "") \
        + (" รวมเนื้อที่แก้เอง" if edits else "")
    print(f"[studio] {vid} delete: {' '.join(gone) or '-'}")
    await room.broadcast()
    return {"ok": True, "msg": msg}


def _finite(v: Any, lo: float, hi: float) -> float | None:
    """ตัวเลขจากภายนอก -> float ในช่วง [lo, hi] / None ถ้าไม่ใช่ตัวเลขจริง
    NaN/Infinity ห้ามหลุดลงไฟล์หรือ state: JSON ของเบราว์เซอร์อ่านไม่ออก (Studio เปิดเพลงนั้นไม่ได้ / ทุกจอพัง)"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return max(lo, min(hi, x))


# ปกที่แขกส่งมากับคำสั่งเพิ่มเพลง — รับเฉพาะรูปแบบที่หน้าเว็บของเราสร้างจริง (ผลค้นหา/คลัง/พร็อกซีปก)
# ไม่งั้น URL อะไรก็ได้ไปโผล่ใน <img>/CSS ของทุกจอ (รั่ว IP เครื่อง Studio ให้เว็บภายนอก)
_THUMB_OK = re.compile(r"https://i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/[A-Za-z0-9_]+\.jpg"
                       r"|/song/([A-Za-z0-9_-]{11})/cover\.jpg|/thumb/([A-Za-z0-9_-]{11})")


def _thumb_for(vid: str, thumb: Any) -> str:
    if isinstance(thumb, str):
        m = _THUMB_OK.fullmatch(thumb)
        if m and vid in m.groups():
            return thumb
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"


def _targets_current(msg: dict) -> bool:
    """คำสั่งที่เลื่อนเพลง (ended/next) หมายถึงเพลงที่เล่นอยู่จริงไหม
    ไม่มี id = ไคลเอนต์รุ่นเก่า -> ยอมไว้ก่อน (รีสตาร์ทเซิร์ฟเวอร์แล้วจอ/มือถือต่อใหม่ แต่ยังรัน JS ชุดเดิมจนกว่าจะรีโหลด)
    มี id แต่ไม่ตรง = คำสั่งค้าง (ended ซ้ำ / ended มาหลังคนกดข้าม / กดข้ามรัว) -> ไม่ทำ ไม่งั้นข้ามสองเพลง"""
    if "id" not in msg:
        return True
    cur = room.current or {}
    return msg.get("id") is not None and msg.get("id") == cur.get("id")


async def _queue_yt(vid: str, title: str, thumb: str, singer: str,
                    extra: dict | None = None) -> dict:
    """เพลง YouTube เข้าคิว + สั่งโหลด/แยกเสียง/หาเนื้อ (ใช้ร่วมกันระหว่าง add กับ addcombo) — เรียกภายใต้ room.lock"""
    room.add({
        "source": "yt",
        "videoId": vid,
        "title": title,
        "thumb": thumb,
        "singer": singer,
        "dlStatus": "queued",
        "dlError": "",
        **(extra or {}),
    })
    it = room.queue[-1] if room.queue else room.current
    now = time.monotonic()
    for k in [k for k, t in _added_at.items() if now - t > 3600]:
        del _added_at[k]
    _added_at[it["videoId"]] = now
    if not _mark_ready_if_archived(it):
        await _ensure_downloader()
        _dl_pending.push(it["videoId"])
    # เพลงที่มีในอาร์ไคฟ์แล้ว -> แยกเสียงได้เลย
    # เพลงที่เพิ่งเข้าคิวโหลด -> no-op เพราะยังไม่มี audio.m4a
    # แล้ว _download_worker จะสั่งซ้ำให้เองตอนโหลดเสร็จ
    await _enqueue_sep(it.get("videoId"))
    # เพลงที่แยกเสียงไว้แล้วแต่ยังไม่มีเนื้อ -> หาเนื้อให้ทันที
    await _enqueue_lyr(it.get("videoId"))
    return it


def _history_add(it: dict) -> None:
    room.history.insert(0, {
        "videoId": it.get("videoId"),
        "path": it.get("path"),
        "source": it.get("source"),
        "title": it.get("title"),
        "thumb": it.get("thumb"),
        "singer": it.get("singer") or "",
        "at": time.time(),
    })
    del room.history[HISTORY_MAX:]


def _playnow(item_id: Any) -> bool:
    for i, q in enumerate(room.queue):
        if q["id"] == item_id:
            room.queue.insert(0, room.queue.pop(i))
            room.next()
            return True
    return False


def _begin_fade(cmd: tuple[str, Any]) -> bool:
    """กดข้าม/เล่นเลย -> จอค่อย ๆ ดำ + เสียงเบาก่อน แล้วค่อยเปลี่ยนเพลงจริงใน _finish_fade
    คืน False = เปลี่ยนทันทีแบบเดิม (ปิดเฟด / ห้องหยุดอยู่ / กดซ้ำระหว่างเฟด)"""
    cur = room.current
    if not cur or not room.playing or room.fading == cur.get("id"):
        return False
    sec = _fade_out_sec(cur, room.tv)
    if sec <= 0:
        return False
    room.fading = cur.get("id")
    room.fade_token += 1
    _bg(_finish_fade(cur.get("id"), room.fade_token, cmd, sec))
    return True


async def _finish_fade(item_id: str, token: int, cmd: tuple[str, Any], sec: float) -> None:
    await asyncio.sleep(sec)               # รอนอก lock — ห้ามถือห้องไว้ระหว่างเฟด
    async with room.lock:
        if room.fade_token != token or room.fading != item_id \
                or (room.current or {}).get("id") != item_id:
            return                         # เปลี่ยนเพลงไปแล้ว / เริ่มใหม่ / ถูกงานใหม่แทน
        if not (cmd[0] == "playnow" and _playnow(cmd[1])):
            room.next()                    # เพลงที่สั่งเล่นเลยถูกลบระหว่างเฟด -> ข้ามไปเพลงถัดไปแทน (จอดำไปแล้ว)
            await _autoplay_fill()
        await _reprioritize()
        await room.broadcast()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # เว็บอื่น (แท็บไหนก็ได้ในเครื่องนี้/มือถือในวงแลน) เปิด WebSocket ข้ามเว็บได้โดยไม่ติด CORS
    # จึงต้องตรวจ Origin เอง — ปิดก่อน accept = uvicorn ตอบ HTTP 403
    if not _same_origin(ws.headers):
        await ws.close(code=1008)
        return
    await ws.accept()
    room.clients.add(ws)
    if not await _ws_send(ws, json.dumps(room.state())):
        _ws_drop(ws)
        return
    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                # socket ถูกปิดจากฝั่งเราแล้ว (_ws_drop ตอนส่งไม่ทัน) -> receive raise ทันทีทุกรอบ
                # ห้าม continue: จะกลายเป็นลูปเปล่ากิน CPU 100% จนทั้งเซิร์ฟเวอร์ค้าง
                break
            msg = None                     # ให้ except ข้างล่างอ้างถึงได้แม้ parse ยังไม่ผ่าน
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
                act = msg.get("action")
                if act == "hello":
                    if msg.get("role") == "mirror":
                        # 📺 จอที่สอง (/watch): ดูอย่างเดียว ไม่แย่งจอหลัก — ได้ state เหมือนทุกคน + ตำแหน่งเพลงไว้ซิงก์
                        ws._is_mirror = True
                        await _ws_send(ws, json.dumps(room.state()))
                        continue
                    # เฉพาะเครื่องนี้ หรือเครื่องที่เปิดผ่านลิงก์ /tv/<รหัส> ที่เป็นจอหลักได้ มีได้ทีละตัว ตัวใหม่ชนะ
                    if msg.get("role") != "player":
                        continue
                    if not _is_local(ws.client.host if ws.client else None) \
                            and not _tv_key_ok(msg.get("tv")):
                        await _ws_send(ws, json.dumps({"type": "evicted", "why": "remote"}))
                        continue
                    room.player_id = msg.get("id")
                    for other in list(room.clients):
                        if other is not ws and getattr(other, "_is_player", False):
                            await _ws_send(other, json.dumps({"type": "evicted", "why": "replaced"}))
                            other._is_player = False
                    ws._is_player = True
                    # ยึดจอคืน/ต่อใหม่ -> ส่ง state ให้วาดใหม่ทันที ไม่ต้องรอ broadcast ครั้งถัดไป
                    await _ws_send(ws, json.dumps(room.state()))
                    continue
                if act == "pos":
                    if getattr(ws, "_is_player", False):
                        t = _finite(msg.get("t"), 0.0, 86400.0)
                        if t is not None:
                            room.pos = t
                            room.pos_at = time.monotonic()
                            # ส่งต่อให้จอที่สองไว้ซิงก์ภาพ (ข้อความเล็ก ไม่ broadcast state ทั้งก้อน)
                            cur_id = (room.current or {}).get("id")
                            pm = json.dumps({"type": "pos", "t": t, "id": cur_id})
                            mirrors = [o for o in list(room.clients) if getattr(o, "_is_mirror", False)]
                            if mirrors:            # พร้อมกันทุกจอ — จอช้า (ผ่าน Cloudflare) ห้ามถ่วงข้อความของจอหลัก
                                await asyncio.gather(*(_ws_send(o, pm) for o in mirrors))
                    continue
                if act == "history":
                    await _ws_send(ws, json.dumps({"type": "history", "items": room.history}))
                    continue
                added = None               # {"type":"added"} ส่งหลัง broadcast ให้ทุกจอมี state ของเพลงนี้ก่อน
                # ชื่อเพลงแก้ก่อนเข้า lock: รีโมทวางลิงก์มาอาจส่ง "YouTube: <id>" — ถามชื่อจริง
                # (oEmbed ยิงเน็ต ~ไม่กี่ร้อย ms) โดยไม่ล็อกห้องไว้ทั้งก้อน
                title = " ".join(str(msg.get("title") or "").split())[:200] if act == "add" else ""
                if act == "add" and msg.get("source") != "local":
                    _v = msg.get("videoId")
                    if _vid_ok(_v) and _title_is_placeholder(title, _v):
                        title = await asyncio.to_thread(_yt_title, _v) or title
                async with room.lock:
                    if act == "add":
                        # ทุกฟิลด์มาจากมือถือใครก็ได้ในวงแลน -> แปลงเป็นสตริง + จำกัดความยาวก่อนเข้าคิว/ประวัติ
                        singer = " ".join(str(msg.get("singer") or "").split())[:24] or DEFAULT_SINGER
                        if msg.get("source") == "local":
                            path = msg.get("path")
                            if not isinstance(path, str) or not path.strip() or len(path) > 500:
                                raise ValueError("path ไม่ถูกต้อง")
                            room.add({
                                "source": "local",
                                "path": path,
                                "title": title or path,
                                "audioOnly": bool(msg.get("audioOnly")),
                                "singer": singer,
                            })
                            it = room.queue[-1] if room.queue else room.current
                        else:
                            vid = msg.get("videoId")
                            if not _vid_ok(vid):
                                # ต้องตรวจก่อน room.add: ค่าที่ไม่ใช่สตริงเข้าคิวแล้ว room.state() พังทุก broadcast
                                raise ValueError(f"videoId ไม่ถูกต้อง: {str(vid)[:40]!r}")
                            it = await _queue_yt(vid, title or vid, _thumb_for(vid, msg.get("thumb")), singer)
                        _history_add(it)
                        await asyncio.to_thread(_save_history)
                        # cid = แท็บรีโมทที่กด -> เครื่องนั้นเปิดหน้าสถานะเต็มจอ ส่วนจอทีวีขึ้นการ์ด
                        added = {"type": "added", "id": it.get("id"),
                                 "cid": str(msg.get("cid") or "")[:40]}
                    elif act == "mix":
                        for _k, (_lo, _hi) in MIX_RANGE.items():
                            if _k in msg:
                                v = _finite(msg[_k], _lo, _hi)
                                if v is not None:
                                    room.mix[_k] = int(round(v))
                        if "key" in msg and room.current:      # เตรียมสเต็มคีย์ใหม่ให้เพลงที่เล่นอยู่
                            await _enqueue_key(room.current.get("videoId"), room.mix["key"])
                    elif act == "lyrmode":
                        if msg.get("mode") in LYR_MODES:
                            room.lyr_mode = msg["mode"]
                    elif act == "voices":                  # 👥 แยกเสียงร้อง/คอรัส เปิด-ปิดจากรีโมท (ค่าเดียวกับ Studio)
                        room.tv = _clean_tv({"voices": bool(msg.get("on"))}, room.tv)
                        await asyncio.to_thread(_write_json_atomic, TV_FILE, room.tv)
                    elif act == "ended":
                        # ต้องมาจากจอหลักเท่านั้น: จอที่ถูกไล่ไปแล้วยังนับถอยหลัง error แล้วส่ง ended ได้
                        if getattr(ws, "_is_player", False) and _targets_current(msg):
                            room.next()
                            await _autoplay_fill()
                    elif act == "next":
                        if _targets_current(msg) and not _begin_fade(("next", None)):
                            room.next()
                            await _autoplay_fill()
                    elif act == "autoplay":
                        room.autoplay = bool(msg.get("on"))
                        await _autoplay_fill()         # เปิดตอนจอว่าง = ขึ้นเพลงเลย
                    elif act == "restart":
                        room.fading = None             # กดเริ่มใหม่ระหว่างเฟดออก = ยกเลิกการเปลี่ยนเพลง
                        room.fade_token += 1
                        room.pos = 0.0
                        room.pos_at = time.monotonic()
                        room.restart_token += 1
                        room.playing = True
                    elif act == "toggle":
                        # ตรึงตำแหน่ง ณ ตอนสลับ — ไม่งั้นหยุดนาน ๆ แล้วเล่นต่อ position() กระโดดไปข้างหน้า
                        # เท่าเวลาที่หยุด (จอใช้ค่านี้ตอนเริ่มสเต็มใหม่ รีโมทใช้เป็นเวลาในรายงาน)
                        room.pos = room.position()
                        room.pos_at = time.monotonic()
                        room.playing = not room.playing
                    elif act == "remove":
                        room.remove(msg.get("id") or "")
                    elif act == "up":
                        room.move(msg.get("id") or "", -1)
                    elif act == "down":
                        room.move(msg.get("id") or "", 1)
                    elif act == "playnow":
                        # เล่นเฉพาะตอนเจอ id — กดรัวสองที ครั้งที่สองเพลงนั้นกลายเป็นเพลงที่เล่นอยู่แล้ว
                        # ของเดิมเรียก next() ทุกกรณี = ข้ามเพลงที่เพิ่งกดเล่นทิ้ง
                        pid = msg.get("id")
                        if any(q["id"] == pid for q in room.queue) and not _begin_fade(("playnow", pid)):
                            _playnow(pid)
                    elif act == "skipintro":
                        # ⏩ จากรีโมท: กระโดดไปก่อนท่อนแรก — กดรัว/มาช้า (พ้นอินโทรแล้ว) = ไม่ทำ
                        cur = room.current
                        ie = (cur or {}).get("introEnd")
                        if cur and _targets_current(msg) and not room.fading and ie \
                                and room.position() < ie - 1:
                            room.pos = float(ie)
                            room.pos_at = time.monotonic()
                            room.seek_token += 1
                            room.playing = True
                    elif act == "addcombo":
                        # 🎬 เพิ่มทั้งคอมโบเข้าคิว — แต่ละเพลงจำจุดเริ่ม/จบ/เฟดที่ตัดไว้ในใบคิว
                        cb = _combo_get(str(msg.get("id") or ""))
                        if not cb:
                            raise ValueError("ไม่พบคอมโบนี้")
                        singer = " ".join(str(msg.get("singer") or "").split())[:24] or DEFAULT_SINGER
                        first = None
                        for ci in cb["items"]:
                            extra = {"combo": cb["name"], "comboId": cb["id"]}
                            for k, q in (("start", "clipStart"), ("end", "clipEnd"),
                                         ("fadeIn", "clipFadeIn"), ("fadeOut", "clipFadeOut")):
                                if ci.get(k) is not None:
                                    extra[q] = ci[k]
                            it = await _queue_yt(ci["videoId"], ci.get("title") or ci["videoId"],
                                                 _thumb_for(ci["videoId"], None), singer, extra)
                            _history_add(it)
                            first = first or it
                        await asyncio.to_thread(_save_history)
                        if first:
                            added = {"type": "added", "id": first.get("id"),
                                     "cid": str(msg.get("cid") or "")[:40], "combo": cb["name"],
                                     "n": len(cb["items"])}
                    elif act == "fix":
                        # "มีอะไรพัง -> กดทีเดียว" เซิร์ฟเวอร์เลือกขั้นที่พังให้เอง
                        it = room.find(msg.get("id")) or room.current
                        vid = (it or {}).get("videoId")
                        if vid and (it or {}).get("source") == "yt":
                            await _do_fix(vid)
                    elif act == "report":
                        # แขกแจ้งซับไม่ตรง -> เก็บไว้ให้คนดูแลแก้ใน Studio (ไม่สั่งตรวจ/ซ่อมอัตโนมัติ)
                        # ปุ่มอยู่บนการ์ดเพลงที่เล่นอยู่ จึงอ้างจาก room.current เสมอ
                        vid = (room.current or {}).get("videoId")
                        if vid and (room.current or {}).get("source") == "yt":
                            dur = float(_song_meta(vid)["duration"] or 0) or 86400.0
                            pos = _finite(msg.get("t"), 0.0, dur)
                            if pos is None:
                                pos = min(room.position(), dur)
                            rep = await asyncio.to_thread(_add_user_report, vid, pos, msg.get("tags"),
                                                          msg.get("note"), msg.get("singer"))
                            room.archive_rev += 1          # ตัวเลข 🚩 ใน Studio ต้องอัปเดต
                            print(f"[report] {vid} แจ้งซับไม่ตรงที่ {pos:.0f}s "
                                  f"{','.join(rep['tags']) or '-'} {rep['note']!r} โดย {rep['by']}")
                    if act in ("add", "next", "ended", "remove", "up", "down",
                               "playnow", "fix", "autoplay", "addcombo"):
                        await _reprioritize()
                    await room.broadcast()     # คำสั่งที่ถูกเมินก็ broadcast ด้วย ให้เครื่องที่ส่งตามทัน
                    if added:
                        await room.send_all(json.dumps(added))
            except WebSocketDisconnect:
                break                      # ตัดการเชื่อมต่อจริง -> ออกจากลูป
            except Exception as exc:
                # ข้อความเพี้ยน/ฟิลด์หาย ต้องไม่ฆ่า socket ของมือถือเครื่องนั้นทั้งเครื่อง
                # (ของเดิม KeyError หลุดออกมาแล้วจอรีเฟรชเงียบ ๆ โดยไม่มีอะไรเกิดขึ้น)
                print(f"[ws] {_printable(msg.get('action'), 20) if isinstance(msg, dict) else '?'} "
                      f"ล้มเหลว: {type(exc).__name__}: {exc}")
                continue
    finally:
        room.clients.discard(ws)


if __name__ == "__main__":
    if "--migrate-dry-run" in sys.argv:
        for a, b in _migrate_song_dirs(dry=True):
            print(f"  {a}\n   -> {b}")
        raise SystemExit
    import uvicorn
    # ลิงก์ทดลอง *.trycloudflare.com ตายทุกครั้งที่ปิดโปรแกรม — ล้างทิ้งก่อน ไม่งั้น QR ชี้ลิงก์ผี
    # (player.command จะเปิดอุโมงค์ใหม่แล้วเขียนลิงก์ใหม่ให้เองหลังเซิร์ฟเวอร์ขึ้น)
    _drop_stale_public_url()
    _cfg = _studio_cfg()
    BASE_URL = base_url()
    print(f"\n  Player screen : http://localhost:{PORT}/   (จอหลักเปิดในเครื่องนี้/ในบ้านเท่านั้น — วิดีโอไม่ต้องวิ่งออกเน็ต)"
          f"\n  Phone remote  : {BASE_URL}/r"
          f"\n  TV screen     : {BASE_URL}/tv/{_cfg['tv']}   (เปิดจากทีวี/เครื่องไหนก็ได้)"
          f"\n  Studio        : {BASE_URL}/studio   (PIN {_cfg['pin']})")
    if _cfg["publicUrl"]:
        print(f"  🌐 Public      : {_cfg['publicUrl']}/r   (ผ่าน Cloudflare Tunnel — ./cloudflare.command)"
              f"\n                  {_cfg['publicUrl']}/studio\n")
    else:
        print("  🌐 เปิดจากนอกบ้าน: ./cloudflare.command --quick (ทดลอง) หรือ ./cloudflare.command kara.โดเมนของคุณ\n")
    # cloudflared ต่อเข้ามาจาก 127.0.0.1 แล้วแนบ X-Forwarded-For = IP จริงของแขก -> uvicorn แทน client.host ให้
    # ด่าน _is_local (จอหลัก / Studio ไม่ต้อง PIN / ยึดจอ) จึงไม่เห็นแขกจากเน็ตเป็น "เครื่องตัวเอง"
    # เชื่อ header นี้เฉพาะจาก loopback: เครื่องอื่นในแลนปลอม header มาก็ไม่มีผล
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")
