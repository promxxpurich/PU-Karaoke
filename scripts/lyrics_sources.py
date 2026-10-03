#!/usr/bin/env python3
"""lyrics_sources.py — แหล่งเนื้อเพลงที่ "มีเวลามาให้แล้ว"

ทุกฟังก์ชันคืน list[{t, d, x}] รูปแบบเดียวกับที่ lyrics.json เก็บ หรือ None ถ้าใช้ไม่ได้
(ไม่ต้องพึ่ง ASR เลย เวลาจึงแม่นกว่าการ align เองมาก)

  from_vtt      ซับจริงของ YouTube (songs/yt/<เพลง>/sub.th.vtt) — แหล่งที่ดีที่สุด
  from_lrc      ข้อความ .lrc ไม่ว่าจะมาจากไฟล์ที่ผู้ใช้วางเอง หรือจาก lrclib
  from_lrclib   ค้น lrclib.net ด้วยชื่อเพลง แล้วกรองด้วยความยาวเพลง

ล้มเหลวเมื่อไหร่คืน None เงียบ ๆ ให้ผู้เรียกไปใช้ทางสำรองต่อ ห้ามทำทั้ง pipeline ล้ม
"""
import html, json, re, unicodedata, urllib.parse
from pathlib import Path

MIN_DUR, MAX_DUR = 1.0, 14.0      # ความยาวบรรทัดที่ผู้เล่นรับได้ (เท่ากับ gen_lyrics.py)
MIN_LINES = 6                     # น้อยกว่านี้ไม่น่าใช่เนื้อเพลงทั้งเพลง
DUR_TOL = 3.0                     # lrclib: ความยาวเพลงต่างกันได้กี่วินาที
ASR_SIM = 0.35                    # เนื้อจาก lrclib ต้องเหมือนคำที่ถอดจากเสียงร้องแค่ไหน
VTT_NONLATIN = 0.6                # ซับต้องมีบรรทัดที่ไม่ใช่ภาษาละตินอย่างน้อยเท่านี้

_TAG = re.compile(r"</?[cvbi][^>]*>|<\d{2}:\d{2}[:.]\d{2}[.,]\d{3}>")
_VTT_TS = re.compile(r"(\d{1,3}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,3}):(\d{2}):(\d{2})[.,](\d{1,3})")
_LRC_TS = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def _has_thai(s: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in s)


# ---------------------------------------------------------------------------
# ภาษาของเพลง — ทุกขั้น (whisper / ซับ / auto-caption / คำอธิบาย / FA) ต้องรู้ก่อน
# ของเดิมทุกขั้นสมมติว่าเป็นไทย เพลงอังกฤษ/ญี่ปุ่นจึงพังเงียบ ๆ (whisper ถอดเป็นไทยมั่ว,
# เอาซับไทยที่เป็น "คำแปล" มาเป็นเนื้อร้อง, ซับอังกฤษถูกทิ้งเพราะเป็นละติน)
# ---------------------------------------------------------------------------
_SCRIPTS = {
    "th": re.compile(r"[\u0e00-\u0e7f]"),
    "ja": re.compile(r"[\u3040-\u30ff]"),        # ฮิรางานะ/คาตากานะ (คันจิล้วนแยกจากจีนไม่ได้)
    "ko": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
    "zh": re.compile(r"[\u4e00-\u9fff]"),
    "en": re.compile(r"[A-Za-z]"),
}
FA_LANGS = ("th", "en")                # ภาษาที่มีโมเดล FA (forced alignment) ในเครื่อง


def norm_lang(code: str | None) -> str:
    """'en-US' -> 'en', 'zh-Hans' -> 'zh', 'th-orig' -> 'th'"""
    c = (code or "").lower().split("-")[0].split("_")[0]
    return c if re.fullmatch(r"[a-z]{2,3}", c) else ""


def letters(text: str, lang: str) -> int:
    """จำนวน "ตัวอักษรของภาษานั้น" ในข้อความ (ภาษาที่ไม่มีตารางอักษร = ตัวอักษรใด ๆ ที่ไม่ใช่ละติน)"""
    rx = _SCRIPTS.get(lang)
    if rx:
        return len(rx.findall(text or ""))
    return sum(1 for ch in (text or "") if ch.isalpha() and not ("A" <= ch <= "Z" or "a" <= ch <= "z"))


def script_of(text: str) -> str | None:
    """ภาษาจากตัวอักษรที่เห็น — ละตินไม่ตัดสิน (เพลงไทยตั้งชื่ออังกฤษเยอะ) คืน None ถ้าไม่รู้"""
    t = text or ""
    if len(_SCRIPTS["th"].findall(t)) >= 2:
        return "th"
    if len(_SCRIPTS["ja"].findall(t)) >= 2:
        return "ja"
    if len(_SCRIPTS["ko"].findall(t)) >= 2:
        return "ko"
    if len(_SCRIPTS["zh"].findall(t)) >= 3:
        return "zh"
    return None


def asr_track(info: dict) -> tuple[str | None, str]:
    """(คีย์ของ auto-caption ที่เป็น ASR ต้นฉบับจริง, ภาษาของมัน) — ("", "") ถ้าไม่มี
    ภาษาของแทร็ก ASR = ภาษาที่ YouTube ได้ยินจากคลิปจริง ๆ เป็นหลักฐานภาษาเพลงที่ดีที่สุดที่ได้ฟรี"""
    best, blang = None, ""
    for key, fmts in (info.get("automatic_captions") or {}).items():
        for f in fmts or ():
            if f.get("ext") != "vtt":
                continue
            q = urllib.parse.parse_qs(urllib.parse.urlparse(f.get("url") or "").query)
            if q.get("kind") != ["asr"] or q.get("tlang"):
                break                       # คำแปล หรือเงาของซับจริง
            lang = norm_lang((q.get("lang") or [""])[0])
            if not lang:
                break
            if best is None or (key.endswith("-orig") and not best.endswith("-orig")):
                best, blang = key, lang     # ชอบคีย์ -orig เพราะ yt-dlp การันตีว่าต้นฉบับ
            break
    return best, blang


def text_lang(text: str, min_latin: int = 40) -> str | None:
    """ภาษาจากตัวอักษรของเนื้อทั้งชุด — ต่างจาก script_of ตรงที่ละตินล้วนพอสรุปว่าอังกฤษได้"""
    sc = script_of(text)
    if sc:
        return sc
    return "en" if len(_SCRIPTS["en"].findall(text or "")) >= min_latin else None


def _name_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return bool(na and nb) and (na in nb or nb in na)


def lang_from_lrclib(title: str, uploader: str, duration: float) -> str | None:
    """ภาษาของเพลงจาก lrclib: เนื้อใน lrclib เป็นภาษาต้นฉบับเสมอ (ไม่ใช่คำแปล)
    รับเฉพาะ record ที่ชื่อเพลง+ศิลปินตรงกับชื่อคลิป และยาวใกล้กัน — เพลงชื่อซ้ำของศิลปินอื่นจะได้ภาษาผิด
    ใช้ตัดสินเพลงที่ชื่อคลิปเป็นละตินล้วน (ชื่ออังกฤษไม่ได้แปลว่าร้องอังกฤษ)"""
    try:
        for track, artist in title_candidates(title, uploader)[:4]:
            if not artist:
                continue
            res = _get("https://lrclib.net/api/search", {"track_name": track, "artist_name": artist}) or []
            for rec in res:
                if not isinstance(rec, dict):
                    continue
                if not _name_match(track, rec.get("trackName") or "") or not _name_match(artist, rec.get("artistName") or ""):
                    continue
                if duration and abs((rec.get("duration") or 0) - duration) > 8:
                    continue
                lang = text_lang(_LRC_TS.sub("", rec.get("syncedLyrics") or "") or rec.get("plainLyrics") or "")
                if lang:
                    return lang
    except Exception:
        return None
    return None


def read_lang(folder: Path) -> dict:
    try:
        j = json.loads((folder / "lang.json").read_text("utf-8"))
        return j if norm_lang(j.get("lang")) else {}
    except Exception:
        return {}


def write_lang(folder: Path, lang: str, by: str, **extra) -> dict:
    import os, time
    rec = {**read_lang(folder), "lang": norm_lang(lang) or "th", "by": by, "at": int(time.time()), **extra}
    tmp = folder / "lang.json.tmp"
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, folder / "lang.json")
    return rec


def song_lang(folder: Path, info: dict | None = None, detect=None, save: bool = True,
              lrclib: bool = False) -> tuple[str, str]:
    """(ภาษา, ที่มา) ของเพลง — หยุดที่หลักฐานแรกที่รู้:
      lang.json (แคช/คนตั้งเอง) -> อักษรในชื่อคลิป -> detect() (whisper ฟังเสียงร้อง) -> แทร็ก ASR ของ YouTube -> "th"
    แทร็ก ASR อยู่หลัง whisper เพราะ YouTube เดาผิดได้ (เพลงไทยชื่ออังกฤษที่มีฮุคอังกฤษถูกแท็ก en)
    จึงบันทึกเฉพาะที่มาที่เชื่อได้ (title/whisper/manual) — ค่าจาก ASR ใช้ชั่วคราว รอ whisper ยืนยันทีหลัง
    detect ต้องคืน (lang, prob) หรือ None; ไม่ส่งมา = ไม่ใช้ GPU"""
    rec = read_lang(folder)
    if rec:
        return rec["lang"], rec.get("by") or "cache"
    if info is None:
        try:
            info = json.loads((folder / "info.json").read_text("utf-8"))
        except Exception:
            info = {}
    lang, by = script_of(info.get("title") or folder.name), "title"
    _, asr = asr_track(info)
    if not lang and lrclib:
        # เนื้อใน lrclib ของเพลงนี้เป็นภาษาอะไร = ร้องภาษานั้น (แม่นกว่าให้เครื่องฟัง: whisper บนเสียงร้องไทยชอบตอบ en)
        # ยกเว้น "ละตินล้วน" ซึ่งอาจเป็นโรมาจิของเพลงญี่ปุ่น/เกาหลี -> ถ้า YouTube ได้ยินเป็นภาษาอื่น เชื่อ YouTube
        lang, by = lang_from_lrclib(info.get("title") or folder.name, info.get("uploader") or "",
                                    float(info.get("duration") or 0)), "lrclib"
        if lang == "en" and asr and asr != "en":
            lang, by = asr, "yt-asr+lrclib"
    if not lang and detect:
        try:
            r = detect()
        except Exception:
            r = None
        got = norm_lang(r[0]) if r else ""
        if got and (r[1] is None or r[1] >= 0.75):
            lang, by = got, "whisper"
        elif got and got == asr and (r[1] or 0) >= 0.5:
            lang, by = got, "whisper"       # ไม่มั่นใจมาก แต่ตรงกับที่ YouTube ได้ยิน
    if not lang and asr:
        return asr, "yt-asr"                # ใช้ไปก่อน ไม่บันทึก — ให้ตรวจยืนยันตอนมีเสียง
    if not lang:
        return "th", "unknown"
    if save:
        write_lang(folder, lang, by)
    return lang, by


def in_script(text: str, lang: str) -> bool:
    """บรรทัดนี้เป็นภาษาของเพลงไหม — ไทยใช้กฎเดิม (ตัวอักษรที่ไม่ใช่ละติน รับท่อนเกาหลี/ลาวในเพลงไทย)
    ภาษาอื่นดูอักษรของภาษานั้น (อังกฤษ = ละติน)"""
    if lang == "th" or not lang:
        return _nonlatin_letter(text)
    return letters(text, lang) > 0


def _nonlatin_letter(s: str) -> bool:
    """มี "ตัวอักษร" ที่ไม่ใช่ละตินอย่างน้อยหนึ่งตัว

    ใช้คัดซับแปลออกจากซับเนื้อร้อง — ตัวนับเดิมคือ _has_thai ซึ่งตกเพลงหลายภาษา
    (เพลงไทยที่มีท่อนเกาหลี/ลาว ได้ไทย 54.2% < 60% ทั้งที่ทุกบรรทัดเป็นเนื้อร้องจริง)
    ส่วนการนับ "ไม่ใช่ ASCII" หลวมเกินไป เพราะซับอังกฤษมี ’ — … ปนเยอะ
    (วัดกับไฟล์จริง 43 ไฟล์: en สูงสุดพุ่งเป็น 51.2% เทียบ th ต่ำสุด 83.6% = ระยะห่างแคบ)
    เกณฑ์นี้วัดได้ th ต่ำสุด 81.8% / en สูงสุด 42.0% -> ห่างกันราว 40 จุด
    ขอบล่าง 0x02B0 ข้ามบล็อก Latin Extended + IPA + spacing modifier ทั้งหมด"""
    return any(unicodedata.category(c)[0] == "L" and ord(c) >= 0x02B0 for c in s)


def _clean(s: str) -> str:
    s = html.unescape(_TAG.sub("", s))
    s = "".join(c for c in s if unicodedata.category(c) != "Cf")
    return re.sub(r"\s+", " ", s).strip()


def line_dur(t: float, nxt: float, end: float = 0.0) -> float:
    """ความยาวบรรทัด (วินาที): ถึงบรรทัดถัดไป หรือถึงเวลาจบที่แหล่งบอกมา (ถ้ามี) ภายในกรอบ MIN_DUR..MAX_DUR
    แต่ "ขั้นต่ำ 1 วิ" ห้ามล้ำเวลาเริ่มบรรทัดถัดไป — ท่อนเร็วที่บรรทัดห่างกันไม่ถึง 1 วิ เดิมถูกยืดจนทับกัน
    จอเลยเข้าใจว่าร้องซ้อน (ค้างบรรทัดเก่าไว้ บรรทัดถัดไปไม่ได้ขึ้นล่วงหน้า) — 77 จาก 97 คู่ที่ทับกันในคลังมาจากตรงนี้
    ต่ำสุดจริง 0.3 วิ (เท่ากับ Studio) กันบรรทัดยาว 0 เมื่อแหล่งให้เวลาซ้ำกัน"""
    d = nxt - t
    if end > t:
        d = min(d, end - t)
    lo = min(MIN_DUR, max(0.3, nxt - t))
    return round(max(lo, min(MAX_DUR, d)), 2)


def _finish(rows: list[tuple[float, str, float]], duration: float) -> list[dict] | None:
    """(เวลาเริ่ม, ข้อความ, เวลาจบที่รู้/0) -> [{t,d,x}]
    ตัดซ้ำติดกัน เรียงเวลา แล้วปิดท้ายด้วยความยาวบรรทัด (ไม่ลากไปชนบรรทัดถัดไป)"""
    rows = [(t, x, e) for t, x, e in rows if x]
    rows.sort(key=lambda r: r[0])
    out: list[tuple[float, str, float]] = []
    for t, x, e in rows:
        if out and out[-1][1] == x:       # ซับแบบไล่บรรทัด (rolling) ส่งข้อความเดิมซ้ำ
            continue
        out.append((t, x, e))
    if len(out) < MIN_LINES:
        return None
    lines = []
    for i, (t, x, e) in enumerate(out):
        nxt = out[i + 1][0] if i + 1 < len(out) else (duration if duration > t else t + 6.0)
        lines.append({"t": round(t, 2), "d": line_dur(t, nxt, e), "x": x})
    return lines


def _cues_of(text: str) -> list[tuple[float, float, list[str]]]:
    """ไฟล์ VTT -> [(เริ่ม, จบ, [บรรทัดเนื้อดิบ])]
    cue เริ่มที่บรรทัดเวลา และจบที่ "บรรทัดว่างจริง" เท่านั้น — บรรทัดที่มีแต่ช่องว่างเป็นส่วนหนึ่งของ cue
    (YouTube ใส่ " " เป็นที่ว่างของบรรทัดบนใน rolling caption ของเดิมนับเป็นตัวคั่น ทำให้วลีแรกหลังช่วงเงียบ
     ทุกครั้งหลุด — วัดกับ auto-caption 97 ไฟล์ หาย 457 จาก 3746 บรรทัดคำ ≈ 12%)"""
    cues: list[tuple[float, float, list[str]]] = []
    cur: list | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = _VTT_TS.search(line)
        if m:
            g = [int(x) for x in m.groups()]
            st = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 10 ** len(m.group(4))
            en = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 10 ** len(m.group(8))
            cur = [st, en, []]
            cues.append(cur)
            continue
        if line == "":
            cur = None
            continue
        if cur is not None:
            cur[2].append(line)
    return [(c[0], c[1], c[2]) for c in cues]


# ---------------------------------------------------------------------------
# ซับ YouTube
# ---------------------------------------------------------------------------
_SOUND_ONLY = re.compile(r"(\[[^\]]{1,24}\]|[♪♫♬\s])+")


def from_vtt(path: Path, duration: float = 0.0, lang: str = "th") -> list[dict] | None:
    """อ่าน .vtt -> บรรทัดพร้อมเวลา (ซับต้องเป็นภาษาของเพลง ไม่ใช่คำแปล)
    cue ที่มีหลายบรรทัดต่อกันเป็นบรรทัดเดียวเหมือนเดิม (ส่วนใหญ่คือแร็ปสองท่อนติดกัน ไม่ใช่ร้องพร้อมกัน)
    แต่ซับแบบ roll-up (บรรทัดบนคือบรรทัดล่างของ cue ก่อน) ตัดบรรทัดที่ซ้ำออก ไม่งั้นข้อความซ้ำสองรอบ"""
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    cues: list[tuple[float, str, float]] = []
    prev_last = ""
    for st, en, body in _cues_of(text):
        parts = [x for x in (_clean(b) for b in body) if x]
        if not parts:
            continue
        last = parts[-1]
        if len(parts) >= 2 and parts[0] == prev_last:
            parts = parts[1:]
        prev_last = last
        if en - st <= 0.02 and len(parts) == 1 and cues and cues[-1][1].endswith(parts[0]):
            continue                          # เฟรมเปลี่ยนผ่าน 10 ms ของ roll-up (ข้อความเดิม)
        body_txt = _clean(" ".join(parts))
        if body_txt and not _SOUND_ONLY.fullmatch(body_txt):     # cue ที่มีแต่ [เพลง] / ♪ ไม่ใช่เนื้อร้อง
            cues.append((st, body_txt, en))
    if len(cues) < MIN_LINES:
        return None
    good = sum(1 for _, x, _ in cues if in_script(x, lang))
    if good < len(cues) * VTT_NONLATIN:   # ซับคำแปล/ภาษาอื่น ไม่เอามาเป็นเนื้อร้อง
        return None
    return _finish(cues, duration)


# ---------------------------------------------------------------------------
# LRC
# ---------------------------------------------------------------------------
_ASR_LANG_OK = ("th",)               # ค่าเริ่มต้นเดิม — ตอนนี้ผู้เรียกส่งภาษาของเพลงมาเอง
_WORD = re.compile(r"<(\d{1,3}):(\d{2}):(\d{2})[.,](\d{1,3})>(?:<c>)?([^<]*)")
_SOUND = re.compile(r"\[[^\]]{1,24}\]")      # [เพลง] [เสียงร้องเพลง] [ดนตรี] [Applause]
AUTO_MIN_WORDS = 12                          # น้อยกว่านี้ไม่พอใช้เป็นเส้นเวลา
AUTO_MAX_GAP = 2.0                           # เพดานความยาวของคำหนึ่งคำ


def words_from_auto_vtt(path: Path, lang: str = "th") -> list[dict] | None:
    """auto-caption VTT ของ YouTube -> [{start, end, word}]

    รูปแบบเดียวกับ sg["words"] ของ whisper จึงป้อน gen_lyrics.make_chunks() ได้ตรง ๆ
    ทำให้จับเวลาให้เนื้อเพลงได้โดยไม่ต้องแยกเสียงและไม่ต้องถอดเสียงเลย

    ไฟล์นี้เป็น rolling caption: cue ของบรรทัดใหม่จะมี "บรรทัดเก่า" เป็น plain text
    นำหน้า แล้วตามด้วยบรรทัดใหม่ที่มี <c> + timestamp ระดับคำ
        คนอื่นเขามองผมว่าอันตราย[เพลง]        <- บรรทัดเก่า ต้องข้าม
        แต่<00:00:04.000><c>ผม</c>...          <- บรรทัดใหม่ เอาอันนี้
    ต้องหยิบเฉพาะบรรทัดที่มี <c> ไม่งั้นบรรทัดเก่าทั้งบรรทัดจะกลายเป็น "คำ" เดียวยาว ๆ
    แล้ว anchor จะเพี้ยนหมด (วัดจริง: กรองแล้ว onTime ขึ้นจาก 33.5 เป็น 36.1)

    คืน None เมื่อไฟล์ใช้ไม่ได้ — auto-caption เสียได้จริง เคยเจอคลิปที่ยัดทั้งท่อน
    เป็น cue เดียวยาว 8 วินาทีโดยไม่มี timestamp ระดับคำเลย"""
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    words: list[dict] = []
    for st, en, block in _cues_of(text):
        body = next((x for x in block if "<c>" in x), None)
        if body is None:
            continue                         # เฟรมสรุปซ้ำของ roll-up
        hits = list(_WORD.finditer(body))
        rows = [(st, body[:hits[0].start()] if hits else body)]
        for h in hits:
            t = int(h[1]) * 3600 + int(h[2]) * 60 + int(h[3]) + int(h[4]) / 10 ** len(h[4])
            rows.append((t, h[5]))
        for t, w in rows:
            raw_w = html.unescape(_TAG.sub("", _SOUND.sub(" ", w)))
            w = _clean(raw_w)
            # แท็กเสียงถูกล้างเป็นว่าง -> คำนั้นหายไปพร้อมเวลา ซึ่งถูกแล้ว
            # ช่องว่างที่เหลือคือท่อนดนตรี ใช้เป็นจุดตัดบรรทัดได้
            if not w or (words and t <= words[-1]["start"]):
                continue                     # rolling ส่งคำเดิมซ้ำใน cue ถัดไป
            # คำละติน (อังกฤษ) ที่ YouTube ใส่ช่องว่างนำหน้ามา -> คงไว้ ตอนต่อเป็นบรรทัดจะได้ไม่ติดกันเป็นพืด
            # ("about it just" ไม่ใช่ "aboutitjust") — คำไทยไม่มีช่องว่างนำหน้าอยู่แล้ว
            if words and re.match(r"[A-Za-z0-9'’]", w) and (
                    raw_w[:1].isspace() or re.search(r"[A-Za-z0-9'’.,!?]$", words[-1]["word"])):
                w = " " + w              # คำแรกของ cue ใหม่ก็ต้องเว้นจากคำก่อนหน้าถ้าเป็นละตินทั้งคู่
            words.append({"start": round(t, 3), "end": round(en, 3), "word": w})
    if len(words) < AUTO_MIN_WORDS:
        return None
    for i, w in enumerate(words[:-1]):        # end จริง = จุดที่คำถัดไปเริ่ม
        w["end"] = round(min(words[i + 1]["start"], w["start"] + AUTO_MAX_GAP), 3)
    good = sum(1 for w in words if in_script(w["word"], lang))
    if good < len(words) * VTT_NONLATIN:
        return None                          # ASR ภาษาอื่น/คำแปล กฎเดียวกับ from_vtt
    return words


def asr_caption_track(info: dict, langs: tuple = _ASR_LANG_OK) -> str | None:
    """ชื่อคีย์ของ auto-caption ที่เป็น ASR ต้นฉบับจริง และอยู่ในภาษาที่ขอ ("" = ไม่มี) — ดู asr_track"""
    key, lang = asr_track(info)
    return key if key and lang in langs else None


def from_lrc(text: str, duration: float = 0.0) -> list[dict] | None:
    rows = []
    for raw in text.splitlines():
        ts = _LRC_TS.findall(raw)
        body = _clean(_LRC_TS.sub("", raw))
        if "^" in body:                   # บาง LRC ต่อคำแปลอังกฤษท้ายบรรทัดด้วย ^
            head = body.split("^", 1)[0].strip()
            if _has_thai(head):
                body = head
        if not ts or not body:
            continue
        for mm, ss, fr in ts:
            rows.append((int(mm) * 60 + int(ss) + (int(fr) / 10 ** len(fr) if fr else 0.0), body, 0.0))
    return _finish(rows, duration)


# ---------------------------------------------------------------------------
# lrclib.net
# ---------------------------------------------------------------------------
_PAREN = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|「[^」]*」")
_NOISE = re.compile(r"(?i)\s*(official.*|feat\..*|ft\..*|full version.*|4k.*|mv\b.*"
                    r"|cover(ed)?\s*(by|version).*|cover$|remix.*|re-?produced\s*by.*"
                    r"|prod\.?\s*by.*|lyric\s*video.*|visualizer.*|live\s*(at|session).*"
                    r"|\+\s*lyrics?.*|not\s+a\s+mv.*"
                    r"|คัฟเวอร์.*)$")


_CREDIT = re.compile(r"(?im)^\s*([^\n:：]{2,30})\s*[:：]\s*(.+?)\s*$")
_K_TRACK = ("song", "track", "title", "เพลง", "ชื่อเพลง", "ต้นฉบับ")
_K_ARTIST = ("artist", "original song by", "original artist", "original by",
             "ศิลปิน", "ขับร้อง", "ต้นฉบับโดย")


def credit_candidates(desc: str) -> list[tuple[str, str]]:
    """อ่านเครดิตแบบ "Song : xxx" / "Original Song by : yyy" ใน description

    คลิปคัฟเวอร์มักไม่ได้ใส่ชื่อเพลงต้นฉบับไว้ในชื่อคลิป แต่เขียนบอกไว้ตรงนี้เสมอ
    """
    track, artist = "", ""
    for k, v in _CREDIT.findall(desc or ""):
        key = k.strip().lower()
        v = _PAREN.sub(" ", v).strip(" -–—|")
        if not v or len(v) > 60:
            continue
        if not track and any(key == t or key.startswith(t) for t in _K_TRACK):
            track = v
        elif not artist and any(key == a or key.startswith(a) for a in _K_ARTIST):
            artist = v
    out = []
    if track:
        out.append((track, artist))
        if artist:
            out.append((track, ""))
    return out


def title_parts(title: str) -> list[str]:
    """ชื่อคลิป -> ส่วนที่คั่นด้วย ' - ' / ' | ' ที่ตัดคำรกแล้ว เช่น ['BOWKYLION', 'ลามปาม']

    ต้องแยกก่อนแล้วค่อยตัดคำรกทีละส่วน: ของเดิมตัดทั้งประโยคก่อน -> "BOWKYLION Ft. Jeff Satur - ลามปาม"
    โดน "ft. …" กินไปจนสุดประโยค ชื่อเพลงหายไปทั้งท่อน เหลือแต่ชื่อศิลปินไปค้น"""
    t = _PAREN.sub(" ", title or "")
    out = []
    # ตัวคั่น: " - " / " | " / "|" (ไม่มีช่องว่างก็ได้ เช่น "เซิ้ง|Music") / " : " (ต้องมีช่องว่าง
    # สองข้าง ไม่งั้น "GAVIN:D" จะแตก)
    for p in re.split(r"\s+[-–—]\s+|\s*\|\s*|\s+[:：]\s+", t):
        p = _NOISE.sub("", p.strip(" -–—|/")).strip(" -–—|/")
        p = re.sub(r"^เพลง\s+", "", p)                  # "เพลง กูว่าแล้ว" -> "กูว่าแล้ว"
        if p:
            out.append(p)
    return out


def title_candidates(title: str, uploader: str = "") -> list[tuple[str, str]]:
    """เดา (ชื่อเพลง, ศิลปิน) จากชื่อคลิป — info.json ของ YouTube ไม่มีฟิลด์ artist/track ให้ใช้
    คืนหลายคู่เพราะไม่รู้ว่าศิลปินอยู่หน้าหรือหลัง ' - '"""
    parts = title_parts(title)
    out: list[tuple[str, str]] = []
    if len(parts) >= 2:
        out.append((parts[1], parts[0]))      # "ศิลปิน - เพลง"
        out.append((parts[0], parts[1]))      # "เพลง - ศิลปิน"
    if parts:
        out.append((parts[-1], uploader or ""))
        out.append((parts[0], uploader or ""))
    seen, uniq = set(), []
    for track, artist in out:
        track = _NOISE.sub("", track).strip()
        if len(track) < 2 or (track, artist) in seen:
            continue
        seen.add((track, artist))
        uniq.append((track, artist))
    return uniq[:4]


_TONE = re.compile(r"[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\u0e30]")


def _norm(s: str) -> str:
    """ตัดวรรณยุกต์/สระบน/ช่องว่าง เหลือแกนตัวอักษรไว้เทียบสองเนื้อว่าเป็นเพลงเดียวกันไหม"""
    return "".join(c.lower() for c in unicodedata.normalize("NFKC", s or "")
                   if not c.isspace() and not _TONE.match(c)
                   and ("\u0e00" <= c <= "\u0e7f" or c.isalnum()))


def similarity(a: str, b: str, k: int = 4) -> float:
    """สัดส่วนชิ้นส่วน k ตัวอักษรของ a ที่โผล่ใน b (0-1)"""
    na, nb = _norm(a), _norm(b)
    if len(na) < k or len(nb) < k:
        return 0.0
    grams = {na[i:i + k] for i in range(len(na) - k + 1)}
    return sum(1 for g in grams if g in nb) / len(grams)


_SESSION = None
_LRCLIB_TIMEOUT = (4, 6)        # (เชื่อมต่อ, อ่าน) — ต่อ 1 เพลงยิงได้ถึง ~12 ครั้ง
                                # ของเดิม 8 วิทุกครั้ง = รอเปล่าได้เป็นนาทีเวลา lrclib ไม่ตอบ


def _get(url: str, params: dict) -> list | dict | None:
    global _SESSION
    try:
        import requests
        if _SESSION is None:    # ใช้ connection เดิมซ้ำ ไม่ต้อง TLS handshake ใหม่ทุกคำค้น
            _SESSION = requests.Session()
            _SESSION.headers["User-Agent"] = "kara/0.1 (personal karaoke)"
        r = _SESSION.get(url, params=params, timeout=_LRCLIB_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _lrclib_pool(title: str, uploader: str, desc: str, duration: float,
                 need_synced: bool, dur_tol: float | None) -> list[dict]:
    """ยิง lrclib ด้วยทุกคำค้นที่เดาได้ แล้วรวม record ที่ผ่านเกณฑ์เบื้องต้น (ไม่ซ้ำ id)"""
    pool: dict[int, dict] = {}
    pairs = title_candidates(title, uploader) + credit_candidates(desc)
    seen: set[tuple[str, str]] = set()
    for track, artist in pairs:
        if (track, artist) in seen:
            continue
        seen.add((track, artist))
        params = {"track_name": track}
        if artist:
            params["artist_name"] = artist
        res = _get("https://lrclib.net/api/search", params)
        if not res and artist:              # ชื่อศิลปินเขียนไม่ตรงกัน -> ค้นด้วยชื่อเพลงล้วน
            res = _get("https://lrclib.net/api/search", {"track_name": track})
        for rec in (res or []):
            if not isinstance(rec, dict):
                continue
            if need_synced and not rec.get("syncedLyrics"):
                continue
            if not need_synced and not (rec.get("plainLyrics") or rec.get("syncedLyrics")):
                continue
            if dur_tol is not None and abs((rec.get("duration") or 0) - duration) > dur_tol:
                continue
            pool.setdefault(rec.get("id") or len(pool), rec)
    return list(pool.values())


def from_lrclib(title: str, uploader: str, duration: float,
                verify: str = "", desc: str = "") -> tuple[list[dict], str] | None:
    """ค้นเนื้อพร้อมเวลาจาก lrclib.net

    กรอง 2 ชั้น เพราะชื่อเพลงไทยซ้ำกันเยอะและ lrclib มีเพลงฝรั่งชื่อคล้ายกันเต็มไปหมด
      1. ความยาวเพลงต้องต่างกันไม่เกิน DUR_TOL วินาที
      2. ถ้ามีเนื้อจาก description อยู่แล้ว ตัวอักษรต้องตรงกันพอ (ไม่งั้นได้คนละเพลง)
    """
    if duration <= 0:
        return None
    pool = _lrclib_pool(title, uploader, desc, duration, need_synced=True, dur_tol=DUR_TOL)
    if not pool:
        return None

    scored = []
    for rec in pool:
        lines = from_lrc(rec["syncedLyrics"], duration)
        if not lines:
            continue
        sim = similarity(verify, "\n".join(l["x"] for l in lines)) if verify else 0.0
        delta = abs((rec.get("duration") or 0) - duration)
        scored.append((sim, -delta, lines, rec))
    if not scored:
        return None
    scored.sort(key=lambda r: (r[0], r[1]), reverse=True)
    sim, _, lines, rec = scored[0]
    if verify and sim < 0.45:               # เนื้อไม่ตรงกับที่รู้อยู่ = คนละเพลง
        return None
    return lines, f'{rec.get("artistName","?")} \u2013 {rec.get("trackName","?")}'


def _plain_of(rec: dict) -> list[str]:
    """เนื้อเปล่าของ record — ถ้ามีแต่แบบมีเวลา ก็ถอด [mm:ss] ทิ้งเอาข้อความ"""
    txt = rec.get("plainLyrics") or ""
    if not txt.strip():
        txt = _LRC_TS.sub("", rec.get("syncedLyrics") or "")
    return [l.strip() for l in txt.splitlines() if l.strip()]


def from_lrclib_text(title: str, uploader: str, desc: str,
                     asr_text: str) -> tuple[list[str], str] | None:
    """เนื้อเปล่าจาก lrclib สำหรับเพลงที่ตกทุกแหล่ง — ให้ผู้เรียกไปจับเวลาเอง

    ต่างจาก from_lrclib() สองข้อ เพราะเคสนี้คือคลิปคัฟเวอร์/รีมิกซ์เป็นส่วนใหญ่
      1. รับ plainLyrics ด้วย (lrclib มีเนื้อเปล่าเยอะกว่าเนื้อมีเวลามาก) และไม่กรองความยาวเพลง
      2. ตัวกันเพลงผิดเปลี่ยนไปใช้ "คำที่ถอดจากเสียงร้องของคลิปนั้นเอง" ซึ่งตรงกว่าความยาวเพลง
    """
    if not (asr_text or "").strip():
        return None
    pool = _lrclib_pool(title, uploader, desc, 0.0, need_synced=False, dur_tol=None)
    scored = []
    for rec in pool:
        lines = _plain_of(rec)
        if len(lines) < MIN_LINES:
            continue
        sim = similarity(asr_text, "\n".join(lines))
        scored.append((sim, lines, rec))
    if not scored:
        return None
    scored.sort(key=lambda r: r[0], reverse=True)
    sim, lines, rec = scored[0]
    if sim < ASR_SIM:                       # ไม่เหมือนเสียงที่ร้องจริง = คนละเพลง
        return None
    return lines, f'{rec.get("artistName","?")} \u2013 {rec.get("trackName","?")} (sim {sim:.2f})'
