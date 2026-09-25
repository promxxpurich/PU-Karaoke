#!/usr/bin/env python3
"""lyrics_more.py — แหล่งเนื้อเพิ่มเติมสำหรับ "ห้องหาเนื้อ" ใน Studio เท่านั้น

ไม่ถูกเรียกจากไปป์ไลน์อัตโนมัติ (gen_lyrics/verify) — คนเลือกเองว่าจะใช้อันไหน
ทุกแหล่งเป็น API ไม่ทางการ พังได้ทุกเมื่อ จึงห้าม raise ออกไป: พังแล้วคืน [] เงียบ ๆ

ทุกฟังก์ชันคืน list ของผู้สมัคร:
    {"provider", "label", "synced": bool, "lines": [{t,d,x}] | None, "texts": [str] | None,
     "meta": {"track", "artist", "duration"}}
"""
import base64
import json
import re

import requests

import lyrics_sources as LS

TIMEOUT = 12
_H = {"User-Agent": "Mozilla/5.0"}
# บรรทัดเครดิตที่แหล่งพวกนี้ใส่มาในเนื้อ (JOOX/NetEase) — ไม่ใช่เนื้อที่ร้อง ห้ามขึ้นจอ
_CREDIT = re.compile(r"(?i)^\s*(lyrics?|lyricist|composed|composer|compose|music|written|words|"
                     r"arrange[dr]?|arrangement|produced|producer|mix(ed|ing)?|master(ed|ing)?|"
                     r"artist|song|title|album|singer|"
                     r"作词|作詞|作曲|编曲|編曲|制作|製作|混音|"
                     r"เพลง|ศิลปิน|คำร้อง|ทำนอง|เรียบเรียง|ขับร้อง|ร้องโดย|ผู้แต่ง|แต่ง|โปรดิวเซอร์|"
                     r"โปรดิวซ์|ดนตรี|มิกซ์|มาสเตอร์|อัลบั้ม|ค่าย)[^:：]{0,20}[:：]")   # "คำร้อง/ทำนอง : …"


def clean_lrc(lrc: str, track: str = "") -> str:
    """ตัดบรรทัดเครดิตกับหัวเพลง ("ชื่อเพลง - ศิลปิน") ออกจาก LRC ก่อนแปลง"""
    out = []
    for line in (lrc or "").splitlines():
        body = re.sub(r"\[[^\]]*\]", "", line).strip()
        if body and _CREDIT.search(body):
            continue
        if body and track and body.startswith(track.strip()) and " - " in body:
            continue
        out.append(line)
    return "\n".join(out)


def _cand(provider: str, label: str, meta: dict, lrc: str = "", texts: list[str] | None = None,
          duration: float = 0.0) -> dict | None:
    """LRC ที่มีเวลา -> ผู้สมัครแบบ synced, ไม่มีเวลา -> แบบเนื้อเปล่า"""
    lrc = clean_lrc(lrc, meta.get("track") or "")
    if lrc and LS._LRC_TS.search(lrc):
        lines = LS.from_lrc(lrc, duration)
        if lines:
            return {"provider": provider, "label": label, "synced": True, "lines": lines,
                    "texts": None, "meta": meta}
        texts = [LS._LRC_TS.sub("", l).strip() for l in lrc.splitlines()]
    texts = [t for t in (texts or []) if t and not _CREDIT.search(t)]
    if len(texts) >= LS.MIN_LINES:
        return {"provider": provider, "label": label, "synced": False, "lines": None,
                "texts": texts, "meta": meta}
    return None


# --- JOOX (แอปฟังเพลงที่คนไทยใช้เยอะ มีเนื้อพร้อมเวลาเกือบทุกเพลงไทย) -------------
# ค้นหา: cache.api.joox.com/openjoox/v1/search (เว็บ joox.com เรียกตัวเดียวกัน)
# เนื้อ: api.joox.com/web-fcgi-bin/web_lyric -> JSONP ที่ field "lyric" เป็น LRC แบบ base64
def _joox_search(query: str) -> list[dict]:
    try:
        r = requests.get("https://cache.api.joox.com/openjoox/v1/search",
                         params={"country": "th", "lang": "th", "key": query},
                         headers={**_H, "Referer": "https://www.joox.com/"}, timeout=TIMEOUT)
        return ((r.json() or {}).get("tracks") or {}).get("items") or []
    except Exception:
        return []


def from_joox(queries: list[tuple[str, str]] | str, duration: float = 0.0, per: int = 3,
              max_total: int = 6) -> list[dict]:
    """queries = [(คำค้น, ที่มา)] ที่มา = "title" (ชื่อเพลง) / "lyric" (ท่อนเนื้อ)
    ผลจากทุกคำค้นรวมกันก่อน (ตัดซ้ำด้วย track id) แล้วค่อยดึงเนื้อ ไม่เกิน max_total เพลง"""
    if isinstance(queries, str):
        queries = [(queries, "title")]
    picked: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for q, via in queries:
        for it in _joox_search(q)[:per]:
            if it.get("id") and it["id"] not in seen:
                seen.add(it["id"])
                picked.append((it, via))
    out: list[dict] = []
    for it, via in picked[:max_total]:
        try:
            t = requests.get("https://api.joox.com/web-fcgi-bin/web_lyric",
                             params={"musicid": it["id"], "country": "th", "lang": "th"},
                             headers={**_H, "Referer": "https://www.joox.com/"}, timeout=TIMEOUT).text
            ly = json.loads(t[t.find("{"):t.rfind("}") + 1]).get("lyric")
            if not ly:
                continue
            lrc = base64.b64decode(ly).decode("utf-8", "replace")
        except Exception:
            continue
        artist = ", ".join(a.get("name", "") for a in it.get("artist_list") or [])
        meta = {"track": it.get("name") or "", "artist": artist,
                "duration": it.get("play_duration") or 0, "id": it.get("id"), "via": via}
        c = _cand("joox", f"JOOX · {artist} – {meta['track']}", meta, lrc=lrc, duration=duration)
        if c:
            out.append(c)
    return out


# --- YouTube Music (ytmusicapi) — เนื้อจาก LyricFind บางเพลงมีเวลา ---------------------
# คลิป MV มักไม่ผูกกับเนื้อ จึงค้น "เพลง" (ATV) ด้วยชื่อเพิ่มอีกทาง
_ytm = None


def _yt():
    global _ytm
    if _ytm is None:
        from ytmusicapi import YTMusic
        _ytm = YTMusic()
    return _ytm


def _ytm_cand(browse_id: str, label: str, meta: dict, duration: float) -> dict | None:
    l = _yt().get_lyrics(browse_id, timestamps=True) or {}
    ly = l.get("lyrics")
    if not ly:
        return None
    if l.get("hasTimestamps") and isinstance(ly, list):
        rows = [(x.start_time / 1000.0, (x.text or "").strip(), x.end_time / 1000.0) for x in ly]
        rows = [r for r in rows if r[1] and not _CREDIT.search(r[1])]
        lines = LS._finish(rows, duration)
        if lines:
            return {"provider": "ytmusic", "label": label, "synced": True, "lines": lines,
                    "texts": None, "meta": meta}
        return None
    texts = ly if isinstance(ly, list) else str(ly).splitlines()
    texts = [getattr(t, "text", t) for t in texts]
    return _cand("ytmusic", label, meta, texts=[str(t).strip() for t in texts], duration=duration)


def from_ytmusic(vid: str, queries: list[tuple[str, str]] | str, duration: float = 0.0,
                 per: int = 2) -> list[dict]:
    """ถามจาก videoId ของคลิปก่อน แล้วค้น "เพลง" ด้วยทุกคำค้น (ชื่อเพลง/ท่อนเนื้อ — YT Music ค้นด้วยเนื้อได้)"""
    if isinstance(queries, str):
        queries = [(queries, "title")]
    out: list[dict] = []
    seen: set[str] = set()
    try:
        tries = [(vid, "YouTube Music · คลิปนี้", {"track": "", "artist": "", "duration": duration,
                                                    "via": "video"})]
        vids = {vid}
        for q, via in queries:
            for s in (_yt().search(q, filter="songs", limit=3) or [])[:per]:
                sv = s.get("videoId")
                if sv and sv not in vids:
                    vids.add(sv)
                    artist = ", ".join(a.get("name", "") for a in s.get("artists") or [])
                    tries.append((sv, f"YouTube Music · {artist} – {s.get('title', '')}",
                                  {"track": s.get("title") or "", "artist": artist,
                                   "duration": s.get("duration_seconds") or 0, "via": via}))
        for v, label, meta in tries:
            lid = (_yt().get_watch_playlist(v, limit=1) or {}).get("lyrics")
            if not lid or lid in seen:
                continue
            seen.add(lid)
            c = _ytm_cand(lid, label, meta, duration)
            if c:
                out.append(c)
    except Exception:
        pass
    return out


# --- syncedlyrics: NetEase / Musixmatch / Megalobiz / Deezer ---------------------------
# เรียกทีละ provider (ไม่ใช้ syncedlyrics.search) จะได้รู้ว่าเนื้อมาจากไหน
SL_PROVIDERS = ("NetEase", "Musixmatch", "Megalobiz", "Deezer")


def from_syncedlyrics(queries: list[tuple[str, str]] | str, duration: float = 0.0,
                      providers=SL_PROVIDERS) -> list[dict]:
    if isinstance(queries, str):
        queries = [(queries, "title")]
    out: list[dict] = []
    try:
        import syncedlyrics.providers as P
    except Exception:
        return out
    for name in providers:
        for q, via in queries:
            try:
                r = getattr(P, name)().get_lrc(q)
            except Exception:
                continue
            if not r:
                continue
            meta = {"track": "", "artist": "", "duration": 0, "via": via, "q": q}
            if getattr(r, "synced", None):
                c = _cand(name.lower(), f"{name} · ค้นด้วย “{q}”", meta, lrc=r.synced, duration=duration)
            elif getattr(r, "unsynced", None):
                c = _cand(name.lower(), f"{name} · ค้นด้วย “{q}”", meta,
                          texts=str(r.unsynced).splitlines(), duration=duration)
            else:
                c = None
            if c:
                out.append(c)
    return out


def queries(title: str, uploader: str = "", n: int = 3) -> list[str]:
    """คำค้นจากชื่อคลิป สูงสุด n คำ: "ส่วนแรก ส่วนหลัง" แล้วแต่ละส่วนเดี่ยว ๆ
    ไม่รู้ว่าศิลปินอยู่หน้าหรือหลัง ' - ' จึงลองชื่อเดี่ยวทั้งสองฝั่ง
    ชื่อช่องใช้เฉพาะตอนชื่อคลิปมีส่วนเดียว (ชื่อช่องมักเป็นค่าย เช่น Whattheduck ไม่ใช่ศิลปิน)"""
    parts = LS.title_parts(title)
    uploader = re.sub(r"\s*-\s*Topic$", "", uploader or "")     # ช่องอัตโนมัติ "ศิลปิน - Topic"
    if len(parts) >= 2:
        qs = [f"{parts[0]} {parts[1]}", parts[1], parts[0]]
    elif parts:
        qs = ([f"{uploader} {parts[0]}"] if uploader else []) + [parts[0]]
    else:
        qs = [title]
    out: list[str] = []
    for q in qs:
        q = " ".join(q.split())
        if len(q) >= 2 and q not in out:
            out.append(q)
    return out[:n]


_THAI = re.compile(r"[\u0e00-\u0e7f]")


def lyric_queries(texts: list[str], n: int = 2) -> list[str]:
    """ท่อนเนื้อไว้ค้น (JOOX/YouTube Music ค้นด้วยเนื้อได้ ใช้กับคลิปคัฟเวอร์/ตั้งชื่อแปลก)
    เลือกท่อนไทยยาวพอให้เจาะจง (12-48 ตัว) ไม่ซ้ำกัน — ท่อนสั้นหรือฮุคซ้ำ ๆ ค้นแล้วเจอเพลงอื่นเต็มไปหมด"""
    cand, seen = [], set()
    for x in texts or []:
        x = " ".join(str(x).split())
        thai = len(_THAI.findall(x))
        if 12 <= len(x) <= 48 and thai >= 0.7 * len(x.replace(" ", "")) and x not in seen:
            seen.add(x)
            cand.append(x)
    counts = {x: sum(1 for y in texts if " ".join(str(y).split()) == x) for x in cand}
    cand = [x for x in cand if counts[x] == 1] or cand          # ท่อนที่ร้องครั้งเดียวเจาะจงกว่า
    cand.sort(key=len, reverse=True)
    return cand[:n]
