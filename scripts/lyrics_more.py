#!/usr/bin/env python3
"""lyrics_more.py — แหล่งเนื้อเพิ่มเติมสำหรับ "ห้องหาเนื้อ" ใน Studio + งานเลือกเนื้อดีที่สุด

gen_lyrics ใช้ YouTube Music / JOOX ตอนหาเนื้อรอบแรกด้วย (เฉพาะข้อความ ยืนยันด้วยคำที่ได้ยินในคลิป)
ทุกแหล่งเป็น API ไม่ทางการ พังได้ทุกเมื่อ จึงห้าม raise ออกไป: พังแล้วคืน [] เงียบ ๆ

ทุกฟังก์ชันคืน list ของผู้สมัคร:
    {"provider", "label", "synced": bool, "lines": [{t,d,x}] | None, "texts": [str] | None,
     "meta": {"track", "artist", "duration"}}
"""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

import lyrics_sources as LS

TIMEOUT = 12
# แคชผลเน็ตร่วมกันข้ามโปรเซส: gen_lyrics (หาเนื้อรอบแรก) กับ server (งานเลือกเนื้อ/ห้องหาเนื้อ) ถามคำขอเดียวกันเกือบทุกเพลง
# เก็บเฉพาะผลที่ได้ของจริง — ว่าง/พัง ไม่จำ (ลองใหม่ได้เสมอ) · ลบทั้งโฟลเดอร์ได้ไม่เสียอะไร
NET_CACHE = Path(os.environ.get("KARA_NET_CACHE") or Path(__file__).resolve().parent.parent / "lyrics-preview" / "_src" / "_net")
NET_TTL = 6 * 3600


def _net(kind: str, key, fetch):
    """fetch() ผ่านแคช — ผลต้องเป็นค่า JSON ธรรมดา · fetch โยน exception = ไม่จำ ส่งต่อให้ผู้เรียก"""
    h = hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    f = NET_CACHE / f"{kind}-{h}.json"
    try:
        if time.time() - f.stat().st_mtime < NET_TTL:
            return json.loads(f.read_text("utf-8"))
    except Exception:
        pass
    val = fetch()
    if val:
        try:
            NET_CACHE.mkdir(parents=True, exist_ok=True)
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(val, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except Exception:
            pass
    return val
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
    def fetch():
        r = requests.get("https://cache.api.joox.com/openjoox/v1/search",
                         params={"country": "th", "lang": "th", "key": query},
                         headers={**_H, "Referer": "https://www.joox.com/"}, timeout=TIMEOUT)
        return ((r.json() or {}).get("tracks") or {}).get("items") or []
    try:
        return _net("joox-s", query, fetch)
    except Exception:
        return []


def _joox_lrc(music_id: str) -> str:
    def fetch():
        t = requests.get("https://api.joox.com/web-fcgi-bin/web_lyric",
                         params={"musicid": music_id, "country": "th", "lang": "th"},
                         headers={**_H, "Referer": "https://www.joox.com/"}, timeout=TIMEOUT).text
        ly = json.loads(t[t.find("{"):t.rfind("}") + 1]).get("lyric")
        return base64.b64decode(ly).decode("utf-8", "replace") if ly else ""
    return _net("joox-l", music_id, fetch)


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
            lrc = _joox_lrc(it["id"])
            if not lrc:
                continue
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


def _ytm_lyrics(browse_id: str) -> dict:
    """{"rows": [[เริ่ม, ข้อความ, จบ]]} (มีเวลา) / {"texts": [...]} / {} — แปลงเป็นค่าธรรมดาก่อน จะได้เก็บแคชได้"""
    def fetch():
        l = _yt().get_lyrics(browse_id, timestamps=True) or {}
        ly = l.get("lyrics")
        if not ly:
            return {}
        if l.get("hasTimestamps") and isinstance(ly, list):
            return {"rows": [[x.start_time / 1000.0, (x.text or "").strip(), x.end_time / 1000.0] for x in ly]}
        texts = ly if isinstance(ly, list) else str(ly).splitlines()
        return {"texts": [str(getattr(t, "text", t)).strip() for t in texts]}
    return _net("ytm-l", browse_id, fetch)


def _ytm_cand(browse_id: str, label: str, meta: dict, duration: float) -> dict | None:
    l = _ytm_lyrics(browse_id)
    if l.get("rows") is not None:
        rows = [tuple(r) for r in l["rows"] if r[1] and not _CREDIT.search(r[1])]
        lines = LS._finish(rows, duration)
        if lines:
            return {"provider": "ytmusic", "label": label, "synced": True, "lines": lines,
                    "texts": None, "meta": meta}
        return None
    if not l.get("texts"):
        return None
    return _cand("ytmusic", label, meta, texts=l["texts"], duration=duration)


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
            for s in (_net("ytm-s", q, lambda: _yt().search(q, filter="songs", limit=3) or []) or [])[:per]:
                sv = s.get("videoId")
                if sv and sv not in vids:
                    vids.add(sv)
                    artist = ", ".join(a.get("name", "") for a in s.get("artists") or [])
                    tries.append((sv, f"YouTube Music · {artist} – {s.get('title', '')}",
                                  {"track": s.get("title") or "", "artist": artist,
                                   "duration": s.get("duration_seconds") or 0, "via": via}))
        for v, label, meta in tries:
            lid = _net("ytm-w", v, lambda: (_yt().get_watch_playlist(v, limit=1) or {}).get("lyrics") or "")
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


# --- Musixmatch (ต้องมี usertoken ของบัญชีผู้ใช้ — แบบไม่ล็อกอินถูกบล็อกแล้ว: token.get คืนเลขศูนย์ล้วน) ----
# เนื้อมีเวลารายบรรทัด (subtitle) และบางเพลงมีเวลา "รายคำ" (richsync) — ข้อมูลชุดเดียวกับที่ Spotify/Instagram ใช้
MXM_ROOT = "https://apic-desktop.musixmatch.com/ws/1.1/"


class MxmError(Exception):
    """token ใช้ไม่ได้/โดนจำกัด — ผู้เรียกบอกผู้ใช้ใน Studio"""


def _mxm(action: str, token: str, **q) -> dict:
    params = {**q, "app_id": "web-desktop-app-v1.0", "usertoken": token, "format": "json"}
    r = requests.get(MXM_ROOT + action, params=params, timeout=TIMEOUT,
                     headers={**_H, "authority": "apic-desktop.musixmatch.com", "cookie": "x-mxm-token-guid="})
    j = r.json()
    hdr = (j.get("message") or {}).get("header") or {}
    code = hdr.get("status_code")
    if code in (401, 402, 403):
        raise MxmError(f"Musixmatch ปฏิเสธ token ({code}{' ' + hdr.get('hint') if hdr.get('hint') else ''})")
    if code != 200:
        return {}
    body = (j.get("message") or {}).get("body")
    return body if isinstance(body, dict) else {}


def _richsync_lines(raw: str) -> list[tuple[float, str, float, list]]:
    """richsync -> [(เริ่ม, ข้อความ, จบ, [[ตำแหน่งตัวอักษร, วินาที], ...])] (เวลารายคำ เก็บไว้ใช้ไล่สีภายหลัง)"""
    out = []
    try:
        for ln in json.loads(raw or "[]"):
            ts, te = float(ln.get("ts") or 0), float(ln.get("te") or 0)
            text, k, pos = "", [], 0
            for w in ln.get("l") or []:
                c = str(w.get("c") or "")
                if c.strip():
                    k.append([len(text), round(ts + float(w.get("o") or 0), 2)])
                text += c
            text = " ".join(text.split())
            if text:
                out.append((ts, text, te, k))
    except Exception:
        return []
    return out


def from_musixmatch(queries: list[tuple[str, str]] | str, token: str, duration: float = 0.0,
                    per: int = 2, max_total: int = 3) -> list[dict]:
    """ค้นทุกคำค้น (ชื่อเพลง) -> เนื้อมีเวลาของแต่ละเพลงที่เจอ (richsync ก่อน ไม่มีค่อย subtitle)
    token ใช้ไม่ได้ -> raise MxmError (ให้ server บอกใน Studio) / พังอย่างอื่น -> คืนเท่าที่ได้"""
    if not token:
        return []
    if isinstance(queries, str):
        queries = [(queries, "title")]
    out: list[dict] = []
    seen: set = set()
    for q, via in queries:
        if len(seen) >= max_total:
            break
        body = _mxm("track.search", token, q=q, page_size=str(per + 1), page="1", f_has_lyrics="1",
                    s_track_rating="desc")
        for it in (body.get("track_list") or [])[:per]:
            t = it.get("track") or {}
            tid = t.get("track_id")
            if not tid or tid in seen or len(seen) >= max_total:
                continue
            seen.add(tid)
            meta = {"track": t.get("track_name") or "", "artist": t.get("artist_name") or "",
                    "duration": t.get("track_length") or 0, "via": via, "id": tid}
            label = f"Musixmatch · {meta['artist']} – {meta['track']}"
            rows = []
            if t.get("has_richsync"):
                rs = _mxm("track.richsync.get", token, track_id=str(tid))
                rows = _richsync_lines(((rs.get("richsync") or {}).get("richsync_body")) or "")
            if rows:
                lines = LS._finish([(a, x, e) for a, x, e, _ in rows if not _CREDIT.search(x)], duration)
                if lines:
                    words = {x: k for _, x, _, k in rows}
                    for l in lines:
                        if words.get(l["x"]):
                            l["k"] = words[l["x"]]          # เวลารายคำจากแหล่ง (ยังไม่ใช้ไล่สีตรง ๆ — FA ทำต่อ)
                    out.append({"provider": "musixmatch", "label": label + " (เวลารายคำ)", "synced": True,
                                "lines": lines, "texts": None, "meta": {**meta, "richsync": True}})
                    continue
            if t.get("has_subtitles"):
                sb = _mxm("track.subtitle.get", token, track_id=str(tid), subtitle_format="lrc")
                lrc = ((sb.get("subtitle") or {}).get("subtitle_body")) or ""
                c = _cand("musixmatch", label, meta, lrc=lrc, duration=duration)
                if c:
                    out.append(c)
                    continue
            ly = _mxm("track.lyrics.get", token, track_id=str(tid))
            txt = ((ly.get("lyrics") or {}).get("lyrics_body")) or ""
            c = _cand("musixmatch", label, meta, texts=[x.strip() for x in txt.splitlines()], duration=duration)
            if c:
                out.append(c)
    return out


def mxm_check(token: str) -> str:
    """ทดสอบ token -> "" = ใช้ได้ / ข้อความปัญหา
    token ที่ใช้ไม่ได้ Musixmatch ยังตอบ 200 พร้อม "เพลงสำรอง" เพลงเดิมทุกคำค้น (ทดสอบแล้ว: ได้ Doja Cat ทุกคำ)
    จึงค้นสองคำที่ต่างกันมาก ผลต้องไม่ใช่เพลงเดียวกัน"""
    try:
        a = _mxm("track.search", token, q="Three Man Down ถ้าเธอรักฉันจริง", page_size="1", page="1")
        b = _mxm("track.search", token, q="Bodyslam ความรักทำให้คนตาบอด", page_size="1", page="1")
        ta = [(t.get("track") or {}).get("track_id") for t in a.get("track_list") or []]
        tb = [(t.get("track") or {}).get("track_id") for t in b.get("track_list") or []]
        if not ta and not tb:
            return "Musixmatch ไม่ตอบผลค้นหา (token อาจหมดอายุ)"
        if ta and tb and ta[0] == tb[0]:
            return "Musixmatch ตอบเพลงเดิมทุกคำค้น = token ใช้ไม่ได้/ถูกจำกัด (ลองเอา token ใหม่จากแอป)"
        return ""
    except MxmError as exc:
        return str(exc)
    except Exception as exc:
        return f"ต่อ Musixmatch ไม่ได้: {type(exc).__name__}"


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
