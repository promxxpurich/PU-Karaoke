#!/usr/bin/env python3
"""api_check.py — ตรวจ "เนื้อถูกเพลงไหม" ด้วย API ออนไลน์ฟรี (วัดอย่างเดียว ไม่เปลี่ยนเนื้อ)

ของในเครื่องตอบได้แค่ "ตรงจังหวะไหม" (FA) — เนื้อผิดเพลงได้ anchorPct 56.5% เทียบเนื้อถูก 66.8% แยกไม่ออก
(ดู lyrics_conf.py) จึงให้ตัวที่ฟังเสียงร้องเป็นอิสระจากเครื่องเราช่วยตัดสินแทน:

  gemini   ส่งเสียงร้อง (vocals.m4a) + เนื้อทั้งชุดให้ Gemini ฟังแล้วตอบ JSON:
           ใช่เพลงเดียวกันไหม / บรรทัดไหนผิด (ได้ยินว่าอะไร) / ท่อนที่ร้องแต่ไม่มีในเนื้อ
           ฟรีใน AI Studio (~250 ครั้ง/วัน แล้วแต่รุ่น) · ฟรี = Google เอาข้อมูลไปเทรนได้ (ผู้ใช้ยอมแล้ว)
  typhoon  ถอดเสียงไทยด้วย Typhoon ASR (SCB 10X — คนละตระกูลกับ whisper ในเครื่อง)
           แล้วเทียบตัวอักษรต่อบรรทัด (lyrics_sources.similarity) · ฝึกด้วยเสียงพูด ต้องวัดก่อนว่าใช้กับเพลงได้

ไม่ใช้ Groq/Cloudflare whisper: โมเดลเดียวกับ mlx-whisper ในเครื่อง ไม่ได้มุมมองใหม่
เกณฑ์ verdict ยังไม่คาลิเบรต — วัดด้วย scripts/eval_lyrics.py content ก่อนเอาไปต่อป้าย ✅/⚠️

key: env KARA_GEMINI_KEY / KARA_TYPHOON_KEY หรือ .studio.json {"geminiKey", "typhoonKey"} (ไม่เข้า git)
แคช: <เพลง>/lyrics.apicheck.json {provider: ผล} ตาม hash เนื้อ (เนื้อเปลี่ยน = ตรวจใหม่)
โควตา: lyrics-preview/_api/quota.json นับต่อวัน กันยิงเกินฟรี (KARA_GEMINI_RPD / KARA_TYPHOON_RPD)

คำสั่ง:
  api_check.py <vid…> [--provider gemini|typhoon] [--fresh] [--dry-run]
บรรทัดสุดท้าย = JSON {"results": [...]} · exit 0 ปกติ / 2 ไม่มี key / 5 โควตาวันนี้หมด
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lyrics_sources as LS

ROOT = Path(__file__).resolve().parent.parent
SONGS = Path(os.environ.get("KARA_SONGS_DIR") or ROOT / "songs" / "yt")
STUDIO_FILE = Path(os.environ.get("KARA_STUDIO_FILE") or ROOT / ".studio.json")
API_DIR = Path(os.environ.get("KARA_API_DIR") or ROOT / "lyrics-preview" / "_api")
CACHE_NAME = "lyrics.apicheck.json"
VERSION = 1                     # เปลี่ยน prompt/เกณฑ์แล้วเพิ่มเลขนี้ = แคชเก่าใช้ไม่ได้

RC_NOKEY, RC_QUOTA = 2, 5
TIMEOUT = 180                   # Gemini ฟังเพลงทั้งเพลงใช้เวลาเป็นสิบวิ
INLINE_MAX = 18 * 1024 * 1024   # Gemini รับไฟล์แนบตรงได้ 20 MB (นับทั้งคำขอ) เกินนี้ย่อเสียงก่อน

PROVIDERS = {
    "gemini": {"key_env": "KARA_GEMINI_KEY", "cfg": "geminiKey",
               "rpd": int(os.environ.get("KARA_GEMINI_RPD") or 200),
               "gap": float(os.environ.get("KARA_GEMINI_GAP") or 7.0)},     # ฟรี ~10 ครั้ง/นาที
    "typhoon": {"key_env": "KARA_TYPHOON_KEY", "cfg": "typhoonKey",
                "rpd": int(os.environ.get("KARA_TYPHOON_RPD") or 500),
                "gap": float(os.environ.get("KARA_TYPHOON_GAP") or 1.0)},
}
GEMINI_MODEL = os.environ.get("KARA_GEMINI_MODEL") or "gemini-flash-latest"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TYPHOON_URL = "https://api.opentyphoon.ai/v1/audio/transcriptions"
TYPHOON_MODEL = os.environ.get("KARA_TYPHOON_MODEL") or "typhoon-asr-realtime"

# เกณฑ์ (ยังไม่คาลิเบรต — eval_lyrics.py content จะบอกค่าที่ควรใช้)
SAME_CONF = 0.7                 # gemini: บอกว่าไม่ใช่เพลงเดียวกันด้วยความมั่นใจเท่านี้ขึ้นไป = ผิดเพลง
OK_PCT_MIN = 50.0               # บรรทัดที่ได้ยินจริงต่ำกว่านี้ = ผิดเพลง/ผิดเวอร์ชัน
BAD_LINES_MIN = 2               # บรรทัดผิดตั้งแต่เท่านี้ = ควรเช็ก (เท่ากับ LC.DEFECT_MIN)
LINE_HEARD = 0.5                # typhoon: ชิ้นส่วนตัวอักษรของบรรทัดโผล่ในผลถอดเสียง ≥ เท่านี้ = ได้ยิน
TY_COVER_MIN = 0.25             # typhoon: ผลถอดเสียงเจอในเนื้อน้อยกว่านี้ = ร้องคนละเนื้อ

_VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
_last_call: dict = {}


class QuotaOut(Exception):
    """โควตาฟรีของวันนี้หมด — หยุดทั้งชุด พรุ่งนี้ค่อยต่อ"""


# ---------------------------------------------------------------------------
# ของในเครื่อง
# ---------------------------------------------------------------------------
def song_dir(vid: str) -> Path | None:
    for d in SONGS.iterdir():
        m = _VID.search(d.name)
        if m and m.group(1) == vid and d.is_dir():
            return d
    return None


def _jload(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def _jsave(p: Path, val) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(val, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def read_lines(d: Path) -> list[dict]:
    j = _jload(d / "lyrics.json") or {}
    L = [l for l in j.get("lines") or [] if (l.get("x") or "").strip() and isinstance(l.get("t"), (int, float))]
    return sorted(L, key=lambda l: l["t"])


def lyr_hash(lines: list[dict]) -> str:
    raw = "\n".join(f"{float(l['t']):.1f}|{l['x'].strip()}" for l in lines)
    return hashlib.sha1(f"{VERSION}\n{raw}".encode("utf-8")).hexdigest()[:16]


def api_key(provider: str) -> str:
    p = PROVIDERS[provider]
    k = os.environ.get(p["key_env"]) or str((_jload(STUDIO_FILE) or {}).get(p["cfg"]) or "")
    return "".join(k.split())


def audio_of(d: Path) -> Path | None:
    """เสียงร้องที่แยกแล้วฟังชัดกว่า (ไม่มีดนตรีกลบ) ยังไม่แยกค่อยใช้เสียงเต็ม"""
    for n in ("vocals.m4a", "audio.m4a"):
        if (d / n).is_file():
            return d / n
    return None


def _ffmpeg_audio(src: Path, ext: str, args: list[str]) -> bytes | None:
    """แปลงเฉพาะเสียงเพลงเดียว (ไม่กี่วิ ไม่ร้อน) — พังคืน None"""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"a.{ext}"
        try:
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1",
                            "-ar", "16000", *args, str(out)], check=True, timeout=120,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return out.read_bytes()
        except Exception:
            return None


def gemini_audio(src: Path) -> tuple[bytes, str] | None:
    if src.stat().st_size <= INLINE_MAX:
        return src.read_bytes(), "audio/mp4"
    b = _ffmpeg_audio(src, "m4a", ["-c:a", "aac", "-b:a", "48k"])
    return (b, "audio/mp4") if b and len(b) <= INLINE_MAX else None


# ---------------------------------------------------------------------------
# โควตา
# ---------------------------------------------------------------------------
def _quota_file() -> Path:
    return API_DIR / "quota.json"


def quota_left(provider: str) -> int:
    q = _jload(_quota_file()) or {}
    day = q.get(date.today().isoformat()) or {}
    if day.get(provider + ":out"):
        return 0
    return max(0, PROVIDERS[provider]["rpd"] - int(day.get(provider) or 0))


def _quota_use(provider: str, out: bool = False) -> None:
    q = _jload(_quota_file()) or {}
    today = date.today().isoformat()
    q = {today: q.get(today) or {}}                 # เก็บแค่วันนี้
    if out:
        q[today][provider + ":out"] = True
    else:
        q[today][provider] = int(q[today].get(provider) or 0) + 1
    try:
        _jsave(_quota_file(), q)
    except Exception:
        pass


def _pace(provider: str) -> None:
    gap = PROVIDERS[provider]["gap"] - (time.time() - _last_call.get(provider, 0.0))
    if gap > 0:
        time.sleep(gap)
    _last_call[provider] = time.time()


def _retry_delay(r) -> float:
    """429 ของ Gemini บอก retryDelay ("34s") มาใน details"""
    try:
        for det in (r.json().get("error") or {}).get("details") or []:
            m = re.match(r"([\d.]+)s", str(det.get("retryDelay") or ""))
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 0.0


def _post(provider: str, send):
    """send() -> requests.Response · โดนจำกัดรายนาทีรอแล้วลองใหม่ / หมดรายวัน -> QuotaOut"""
    for attempt in range(3):
        if quota_left(provider) <= 0:
            raise QuotaOut(provider)
        _pace(provider)
        r = send()
        _quota_use(provider)
        if r.status_code != 429:
            return r
        wait = _retry_delay(r)
        body = r.text.lower().replace("_", "").replace(" ", "")
        if "perday" in body or wait > 90 or attempt == 2:
            _quota_use(provider, out=True)
            raise QuotaOut(provider)
        time.sleep(max(wait, 15.0))
    raise QuotaOut(provider)


# ---------------------------------------------------------------------------
# Gemini — ฟังแล้วตัดสินเอง
# ---------------------------------------------------------------------------
_LANG_NAME = {"th": "Thai", "en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese",
              "lo": "Lao", "vi": "Vietnamese"}

PROMPT = """You are checking karaoke lyrics against a song recording.
The audio is the {what} of the song. The lyrics below claim to be this song's lyrics ({lang}).
Each line is "index [mm:ss] text"; the times are only approximate, do NOT judge timing.

Decide:
1. same_song: are these lyrics (mostly) the words actually sung in this recording?
   false if they belong to a different song or a clearly different version/language.
2. bad_lines: lines whose words are NOT what is sung. Use status
   "wrong_text" = something is sung around there but the words differ substantially,
   "not_sung"   = nothing like this line is sung anywhere in the recording.
   Put what you actually hear in "heard" (in the sung language/script, "" if nothing).
   Do NOT flag: small spelling/tone-mark/transliteration differences, repeated chorus lines,
   ad-libs, backing vocals in parentheses, or lines that are sung but at a different time.
3. missing: sung passages (longer than one short phrase) that no lyrics line covers,
   with start time in seconds and what is heard.
4. confidence: 0..1 how sure you are about same_song.
Be conservative: only report what you can clearly hear.

LYRICS:
{lyrics}"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "same_song": {"type": "BOOLEAN"},
        "confidence": {"type": "NUMBER"},
        "bad_lines": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"i": {"type": "INTEGER"},
                           "status": {"type": "STRING", "enum": ["wrong_text", "not_sung"]},
                           "heard": {"type": "STRING"}},
            "required": ["i", "status", "heard"]}},
        "missing": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"t": {"type": "NUMBER"}, "heard": {"type": "STRING"}},
            "required": ["t", "heard"]}},
        "note": {"type": "STRING"},
    },
    "required": ["same_song", "confidence", "bad_lines", "missing"],
}


def _mmss(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def gemini_prompt(lines: list[dict], lang: str, vocals: bool) -> str:
    body = "\n".join(f"{i} [{_mmss(l['t'])}] {l['x'].strip()}" for i, l in enumerate(lines))
    return PROMPT.format(what="isolated vocal track" if vocals else "full mix",
                         lang=_LANG_NAME.get(lang, lang or "unknown"), lyrics=body)


def check_gemini(lines: list[dict], audio: Path, lang: str, key: str) -> dict:
    blob = gemini_audio(audio)
    if not blob:
        return {"verdict": "error", "note": "ไฟล์เสียงใหญ่เกินส่งตรง/ย่อไม่ได้"}
    data, mime = blob
    body = {
        "contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}},
                                {"text": gemini_prompt(lines, lang, audio.name == "vocals.m4a")}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": SCHEMA},
    }
    r = _post("gemini", lambda: requests.post(GEMINI_URL.format(model=GEMINI_MODEL), json=body, timeout=TIMEOUT,
                                              headers={"x-goog-api-key": key}))
    if r.status_code != 200:
        return {"verdict": "error", "note": f"Gemini ตอบ {r.status_code}: {_err_msg(r)}"}
    j = r.json()
    try:
        cand = (j.get("candidates") or [{}])[0]
        txt = "".join(p.get("text") or "" for p in (cand.get("content") or {}).get("parts") or [])
        out = json.loads(txt)
    except Exception:
        why = ((j.get("promptFeedback") or {}).get("blockReason")
               or ((j.get("candidates") or [{}])[0].get("finishReason")) or "อ่าน JSON ไม่ได้")
        return {"verdict": "error", "note": f"Gemini ไม่ตอบผล ({why})"}
    n = len(lines)
    bad, seen = [], set()
    for b in out.get("bad_lines") or []:
        try:
            i = int(b.get("i"))
        except Exception:
            continue
        if 0 <= i < n and i not in seen:
            seen.add(i)
            bad.append({"i": i, "status": b.get("status") or "wrong_text", "heard": str(b.get("heard") or "")[:200]})
    bad.sort(key=lambda b: b["i"])
    miss = [{"t": round(float(m.get("t") or 0), 1), "heard": str(m.get("heard") or "")[:200]}
            for m in out.get("missing") or [] if isinstance(m, dict)][:30]
    res = {"model": (j.get("modelVersion") or GEMINI_MODEL), "sameSong": bool(out.get("same_song")),
           "conf": round(float(out.get("confidence") or 0), 2), "n": n, "bad": bad, "missing": miss,
           "okPct": round(100 * (n - len(bad)) / max(1, n), 1), "note": str(out.get("note") or "")[:300]}
    res["verdict"] = verdict("gemini", res)
    return res


# ---------------------------------------------------------------------------
# Typhoon ASR — ถอดเสียงไทยอีกตัวแล้วเทียบตัวอักษร
# ---------------------------------------------------------------------------
def line_scores(lines: list[dict], heard: str) -> tuple[list[float], float]:
    """(ต่อบรรทัด: สัดส่วนชิ้นส่วนตัวอักษรของบรรทัดที่โผล่ในผลถอดเสียง, cover: ผลถอดเสียงเจอในเนื้อแค่ไหน)
    cover คือตัวแยกผิดเพลง: เนื้อเพลงอื่นอาจบังเอิญมีคำซ้ำกับที่ร้อง แต่สิ่งที่ร้องทั้งหมดจะไม่อยู่ในเนื้อนั้น"""
    allx = " ".join(l["x"] for l in lines)
    per = [round(LS.similarity(l["x"], heard), 3) if len(LS._norm(l["x"])) >= 4 else 1.0 for l in lines]
    return per, round(LS.similarity(heard, allx), 3)


def check_typhoon(lines: list[dict], audio: Path, lang: str, key: str) -> dict:
    if lang and lang != "th":
        return {"verdict": "skip", "note": "Typhoon ASR ฟังภาษาไทยเท่านั้น"}
    wav = _ffmpeg_audio(audio, "wav", [])
    if not wav:
        return {"verdict": "error", "note": "แปลงเสียงเป็น wav ไม่ได้"}
    r = _post("typhoon", lambda: requests.post(
        TYPHOON_URL, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT,
        files={"file": ("vocals.wav", wav, "audio/wav")}, data={"model": TYPHOON_MODEL, "language": "th"}))
    if r.status_code != 200:
        return {"verdict": "error", "note": f"Typhoon ตอบ {r.status_code}: {_err_msg(r)}"}
    try:
        heard = str(r.json().get("text") or "")
    except Exception:
        heard = r.text
    if len(LS._norm(heard)) < 20:
        return {"verdict": "error", "note": "Typhoon ถอดเสียงได้น้อยเกินไป", "heardLen": len(heard)}
    per, cover = line_scores(lines, heard)
    n = len(lines)
    bad = [{"i": i, "status": "not_heard", "score": s} for i, s in enumerate(per) if s < LINE_HEARD]
    res = {"model": TYPHOON_MODEL, "n": n, "bad": bad, "cover": cover,
           "okPct": round(100 * (n - len(bad)) / max(1, n), 1), "heard": heard[:4000]}
    res["verdict"] = verdict("typhoon", res)
    return res


def _err_msg(r) -> str:
    try:
        e = r.json().get("error")
        return str((e or {}).get("message") if isinstance(e, dict) else e or r.text)[:200]
    except Exception:
        return r.text[:200]


def verdict(provider: str, res: dict) -> str:
    """ok | some-wrong | wrong-song (เกณฑ์ชั่วคราว — คาลิเบรตด้วย eval_lyrics.py content)"""
    if provider == "gemini" and not res.get("sameSong") and (res.get("conf") or 0) >= SAME_CONF:
        return "wrong-song"
    if provider == "typhoon" and (res.get("cover") or 0) < TY_COVER_MIN:
        return "wrong-song"
    if (res.get("okPct") or 0) < OK_PCT_MIN:
        return "wrong-song"
    return "some-wrong" if len(res.get("bad") or []) >= BAD_LINES_MIN else "ok"


# ---------------------------------------------------------------------------
# ตรวจหนึ่งเพลง
# ---------------------------------------------------------------------------
CHECKERS = {"gemini": check_gemini, "typhoon": check_typhoon}


def check_lines(provider: str, lines: list[dict], audio: Path, lang: str, key: str) -> dict:
    """ตรวจเนื้อชุดใดก็ได้ (eval ส่งเนื้อที่ทำเสียเองมาได้) — ไม่แคช ไม่ raise ยกเว้น QuotaOut"""
    try:
        res = CHECKERS[provider](lines, audio, lang, key)
    except QuotaOut:
        raise
    except Exception as exc:
        res = {"verdict": "error", "note": f"{type(exc).__name__}: {exc}"[:300]}
    return {"provider": provider, "v": VERSION, "at": round(time.time()), "hash": lyr_hash(lines), **res}


def check_song(vid: str, provider: str = "gemini", fresh: bool = False, dry: bool = False) -> dict:
    """ตรวจเนื้อปัจจุบันของเพลง + แคชใน <เพลง>/lyrics.apicheck.json"""
    d = song_dir(vid)
    if not d:
        return {"vid": vid, "provider": provider, "verdict": "error", "note": "ไม่พบเพลงในคลัง"}
    lines = read_lines(d)
    if not lines:
        return {"vid": vid, "provider": provider, "verdict": "skip", "note": "ยังไม่มีเนื้อ"}
    audio = audio_of(d)
    if not audio:
        return {"vid": vid, "provider": provider, "verdict": "skip", "note": "ยังไม่มีไฟล์เสียง"}
    h = lyr_hash(lines)
    cache = _jload(d / CACHE_NAME) or {}
    old = cache.get(provider) or {}
    if not fresh and old.get("hash") == h and old.get("verdict") not in ("error", None):
        return {"vid": vid, "cached": True, **old}
    lang = (_jload(d / "lang.json") or {}).get("lang") or "th"
    if dry:
        return {"vid": vid, "provider": provider, "verdict": "dry-run", "lines": len(lines), "lang": lang,
                "audio": audio.name, "mb": round(audio.stat().st_size / 1e6, 1), "quotaLeft": quota_left(provider)}
    res = check_lines(provider, lines, audio, lang, api_key(provider))
    if res.get("verdict") not in ("error", "skip"):
        cache[provider] = res
        try:
            _jsave(d / CACHE_NAME, cache)
        except Exception as exc:
            res["note"] = (res.get("note") or "") + f" (เขียนแคชไม่ได้: {exc})"
    return {"vid": vid, **res}


def _summary(r: dict) -> str:
    v = r.get("verdict")
    if v in ("error", "skip", "dry-run"):
        return f"{r['vid']} [{r.get('provider')}] {v}: {r.get('note') or json.dumps({k: r.get(k) for k in ('lines', 'lang', 'audio', 'mb', 'quotaLeft')}, ensure_ascii=False)}"
    extra = f" ใช่เพลงนี้={r.get('sameSong')} ({r.get('conf')})" if r.get("provider") == "gemini" else f" cover={r.get('cover')}"
    return (f"{r['vid']} [{r['provider']}] {v} · ได้ยินตรง {r.get('okPct')}% · บรรทัดผิด {len(r.get('bad') or [])}"
            f"{extra}{' (แคช)' if r.get('cached') else ''}")


def main() -> None:
    args = sys.argv[1:]
    provider, vids, i = "gemini", [], 0
    while i < len(args):                    # videoId ขึ้นต้น "-" ได้ — ตัดเฉพาะธงที่รู้จัก
        a = args[i]
        if a == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
            continue
        if a not in ("--fresh", "--dry-run"):
            vids.append(a)
        i += 1
    if provider not in PROVIDERS or not vids:
        print(__doc__)
        sys.exit(1)
    dry = "--dry-run" in args
    if not dry and not api_key(provider):
        print(f"ไม่มี key ของ {provider}: ตั้ง {PROVIDERS[provider]['key_env']} หรือ "
              f"\"{PROVIDERS[provider]['cfg']}\" ใน .studio.json")
        print(json.dumps({"results": [], "error": "nokey"}))
        sys.exit(RC_NOKEY)
    out, rc = [], 0
    for vid in vids:
        try:
            r = check_song(vid, provider, fresh="--fresh" in args, dry=dry)
        except QuotaOut:
            print(f"โควตาฟรีของ {provider} วันนี้หมดแล้ว — พรุ่งนี้ค่อยต่อ")
            rc = RC_QUOTA
            break
        out.append(r)
        print(_summary(r), flush=True)
    print(json.dumps({"results": out}, ensure_ascii=False))
    sys.exit(rc)


if __name__ == "__main__":
    main()
