#!/usr/bin/env python3
"""ดึงเนื้อเพลงจริงออกจาก info.json (YouTube description) ลง lyrics-preview/_src/<vid>.txt
เนื้อเป็นบรรทัด (1 บรรทัดของเนื้อร้อง = 1 บรรทัด) เพื่อใช้สำหรับ alignment ต่อไป
"""
import json, os, re, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DL = Path(os.environ["KARA_SONGS_DIR"]) if os.environ.get("KARA_SONGS_DIR") else BASE / "songs" / "yt"   # override ไว้ทดสอบกับคลังจำลอง
SRC = BASE / "lyrics-preview" / "_src"
SRC.mkdir(parents=True, exist_ok=True)

RE_VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
RE_NUM = re.compile(r"(?<!\d)[\d]{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}(?!\d)|[*#]\d{6,}")

HEADER_FOOTER = (
    "digital", "official audio", "official video", "official visualizer",
    "official lyric", "official mv", "ติดต่องาน", "ดาวน์โหลด", "download",
    "mixed", "mixing", "mastered", "mastering", "recorded", "recording",
    "produced", "producer", "production", "directed", "composer", "arrang",
    "lyrics by", "lyricist", "writer", "commposer", "vocal", "drum",
    "guitar", "keyboard", "piano", "bass", "saxophone", "string", "synthesiz",
    "artist", "song", "single", "album", "ทำนอง", "คำร้อง", "เรียบเรียง",
    "ศิลปิน", "ประพันธ์", "เนื้อร้อง", "instagram", "facebook", "twitter",
    "tiktok", "social", "copyright", "sound recording", "phonographic",
    "kktix", "apple music", "spotify", "joox", "youtube", "bfan.link",
    "itunes", "kkbox", "goo.gl", "bit.ly", "ติดตาม", "ซัพพอร์ต", "สนับสนุน",
    "สมัคร", "teaser", "coming soon", "mv:", "bangkok legacy",
    "special thanks", "public relations", "management", "ติดต่อ", "jkt48",
    "hashtag", "sxsw", "ช่องทาง", "ฟังเพลง", "กด", "subscribe",
)

RE_SECTION = re.compile(r"^[\(\[]*[\*]?\s*(hook|verse|chorus|pre\s*[-–\s]*chorus|bridge|rap|solo|intro|outro|interlude|pre|ดนตรี|音乐|เพลง)?\s*[\d\-\*]?\s*[\*\)\]]*$", re.I)


def has_thai(s: str) -> bool:
    return any("\u0e00" <= ch <= "\u0e7f" for ch in s)


def is_marker(line: str) -> bool:
    low = line.strip().lower()
    if not low:
        return True
    if re.fullmatch(r"[\.。…\s\-—_~=*:()\[\]【】]+", low):
        return True
    if RE_SECTION.fullmatch(low):
        return True
    if re.fullmatch(r"[\(\[]?[\*]?\s*(hook|verse|chorus|bridge)\s*[\d\-\*]?\s*[\*\)\]]?", low, re.I):
        return True
    return False


def is_credit(line: str) -> bool:
    low = line.strip().lower()
    if not low:
        return False
    if "http" in low or "www." in low or "@" in low or "#" in low:
        return True
    if RE_NUM.search(line):
        return True
    return low.startswith(HEADER_FOOTER)


def in_lang(line: str, lang: str = "th") -> bool:
    """บรรทัดนี้เขียนด้วยอักษรของภาษาเพลงไหม (ไทย = มีตัวไทย / อังกฤษ = ตัวละติน ≥6 / อื่น = อักษรภาษานั้น)"""
    if lang == "th" or not lang:
        return has_thai(line)
    import lyrics_sources as LS
    return LS.letters(line, lang) >= (6 if lang == "en" else 2)


def looks_lyric(line: str, lang: str = "th") -> bool:
    ln = line.strip()
    if not ln or not in_lang(ln, lang):
        return False
    if lang != "th" and (re.search(r"https?://|www\.|@\w|#\w", ln) or ln.isupper() and len(ln) > 40):
        return False                                 # ลิงก์/แท็ก/หัวข้อตัวพิมพ์ใหญ่ยาว ๆ ไม่ใช่เนื้อ
    if re.fullmatch(r"[\(\[].{0,14}[\)\]]", ln):
        return False
    return 6 <= len(ln) <= 130


_EMOJI = re.compile(r"[\u2600-\u27bf\u2190-\u21ff\U0001f000-\U0001faff\u266a-\u266b]")


def extract(desc: str, lang: str = "th") -> list[str]:
    lines = [_EMOJI.sub("", l).strip() for l in desc.split("\n")]
    n = len(lines)

    # 1) มี marker ชัดเจน (บรรทัดลอยๆ เช่น "LYRICS:" / "เนื้อเพลง" / "歌词")
    #    ระวัง "Lyrics: Pisarn..." คือเครดิต ไม่ใช่ marker
    start = None
    for i, l in enumerate(lines):
        low = l.lower().strip()
        if re.search(r"^(lyrics?|เนื้อเพลง|歌词)\s*[:\-]?\s*$", low):
            start = i + 1
            break
    # 2) ไม่มี marker -> หาบรรทัดไทยติดกัน 3 บรรทัดแรกที่ไม่ใช่ชื่อ/เครดิต
    if start is None:
        for i in range(n - 2):
            if all(looks_lyric(lines[i + k], lang) and not is_credit(lines[i + k]) for k in range(3)):
                start = i
                break
    if start is None:
        return []

    out: list[str] = []
    for l in lines[start:]:
        if is_credit(l):
            break
        if is_marker(l):
            continue
        if l == "":
            continue
        out.append(l)
    return out


def main() -> None:
    only = sys.argv[1:] or None
    for d in sorted(DL.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        vid = vid_of(d.name)
        if not (d / "video.mp4").is_file() or not (d / "audio.m4a").is_file():
            continue
        if only and vid not in only:
            continue
        ij = d / "info.json"
        if not ij.is_file():
            print(f"[x] {vid} {d.name} no info.json")
            continue
        desc = json.loads(ij.read_text("utf-8")).get("description") or ""
        lyric_lines = extract(desc)
        th = sum(1 for l in lyric_lines if has_thai(l))
        if not lyric_lines or th < 4:
            print(f"[--] {vid} เนื้อไม่พอ (th={th}) {d.name}")
            continue
        (SRC / f"{vid}.txt").write_text("\n".join(lyric_lines) + "\n", encoding="utf-8")
        print(f"[ok] {vid} {len(lyric_lines):3d} บรรทัด ({th}ไทย) {d.name}")


def vid_of(name: str) -> str:
    m = RE_VID.search(name)
    return m.group(1) if m else name


if __name__ == "__main__":
    main()