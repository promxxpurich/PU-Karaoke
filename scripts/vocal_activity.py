#!/usr/bin/env python3
"""vocal_activity.py — แผนที่เสียงร้องจาก vocals.m4a: ช่วงที่มีเสียงร้อง / ช่วงเงียบ / จุดเริ่มพยางค์ (onset)

ใช้เป็นหลักฐานเวลาอีกชิ้นนอกจาก FA (ไม่ต้องรู้เนื้อเลย):
  - บรรทัดไม่ควรเริ่มกลางช่วงเงียบ / ขอบท่อนที่เลื่อนได้ต้องอยู่ตรงช่วงเงียบ (lyrics_refine)
  - ท่อนแร็ป = onset ถี่ ใช้เกลี่ยเวลาบรรทัดที่เวลาอัดกันให้ลงจังหวะพยางค์จริง
numpy + scipy + ffmpeg เท่านั้น (~2-4 วิ CPU ต่อเพลง) แคชไว้ที่ lyrics-preview/_va/<vid>.npz ผูกกับลายเซ็นไฟล์เสียง

ใช้งาน: vocal_activity.py <videoId> [--audio PATH]   -> สรุป JSON (ช่วงเงียบ ≥1.5 วิ, onset/วิ)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("KARA_VA_CACHE") or (Path(os.environ["KARA_FA_CACHE"]).parent / "_va"
                                                 if os.environ.get("KARA_FA_CACHE") else BASE / "lyrics-preview" / "_va"))
SR = 16000
HOP = 320                      # 20 ms ต่อเฟรม (เท่ากับ FA)
WIN = 640
VERSION = 2


def _sig(audio: Path) -> str:
    st = audio.stat()
    return f"v{VERSION}:{audio.name}:{st.st_size}:{st.st_mtime_ns}"


def _load(audio: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _frames(x: np.ndarray) -> np.ndarray:
    n = max(0, 1 + (len(x) - WIN) // HOP)
    if n <= 0:
        return np.zeros((0, WIN), np.float32)
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx]


def analyze(audio: Path) -> dict:
    """{fsec, db[T], voiced[T], onsets[sec]}"""
    x = _load(audio)
    fr = _frames(x)
    if not len(fr):
        return {"fsec": HOP / SR, "db": np.zeros(0, np.float32), "voiced": np.zeros(0, bool), "onsets": np.zeros(0, np.float32)}
    rms = np.sqrt((fr.astype(np.float64) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    # เกณฑ์อิงความดังของเสียงร้องจริง (p97) ไม่ใช่ความเงียบ: สเต็มเสียงร้องของ demucs มีเสียงดนตรีรั่ว
    # ช่วงดนตรีล้วนจึงไม่เงียบจริง (วัดได้ ~-28 dB เทียบเสียงร้อง ~-10 dB) — เกณฑ์แบบ "ดังกว่าความเงียบ" เห็นเป็นเสียงร้องหมด
    ref = np.percentile(db, 97)
    on_t, off_t = ref - 15.0, ref - 21.0                            # hysteresis: เข้าเสียงต้องดังกว่าออก
    voiced = np.zeros(len(db), bool)
    state = False
    for i, v in enumerate(db):
        state = v > on_t if not state else v > off_t
        voiced[i] = state
    # รูเล็ก ๆ (< 240 ms) ในเสียงร้อง = หายใจ/พยัญชนะ ไม่ใช่ช่วงเงียบ / เสียงสั้นโดด ๆ (< 60 ms) = เสียงหลุด
    voiced = _fill(voiced, 12, True)
    voiced = _fill(voiced, 3, False)
    # spectral flux บน log-magnitude -> จุดเริ่มพยางค์
    win = np.hanning(WIN)
    mag = np.abs(np.fft.rfft(fr * win, axis=1))
    lm = np.log1p(mag * 10)
    flux = np.maximum(0.0, np.diff(lm, axis=0)).sum(axis=1)
    flux = np.concatenate(([0.0], flux))
    k = 25                                                          # ±0.5 วิ เกณฑ์ปรับตามท้องถิ่น
    pad = np.pad(flux, (k, k), mode="edge")
    cs = np.cumsum(np.concatenate(([0.0], pad)))
    mean = (cs[2 * k + 1:] - cs[:-2 * k - 1]) / (2 * k + 1)
    thr = mean * 1.5 + 1e-6
    peaks = []
    last = -10
    for i in range(1, len(flux) - 1):
        if flux[i] > thr[i] and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1] and voiced[i] and i - last >= 4:
            peaks.append(i)
            last = i
    fsec = HOP / SR
    return {"fsec": fsec, "db": db.astype(np.float32), "voiced": voiced,
            "onsets": (np.array(peaks, np.float32) * fsec + WIN / 2 / SR).astype(np.float32)}


def _fill(mask: np.ndarray, n: int, value: bool) -> np.ndarray:
    """เติมรูของค่า (not value) ที่สั้นกว่า n เฟรม ให้เป็น value"""
    m = mask.copy()
    i = 0
    L = len(m)
    while i < L:
        if m[i] != value:
            j = i
            while j < L and m[j] != value:
                j += 1
            if i > 0 and j < L and j - i < n:
                m[i:j] = value
            i = j
        else:
            i += 1
    return m


def load(vid: str, audio: Path) -> dict | None:
    """แผนที่เสียงร้อง (แคช) — ไม่มีไฟล์เสียง = None"""
    if not audio or not audio.is_file():
        return None
    f = CACHE / f"{vid}.npz"
    sig = _sig(audio)
    if f.is_file():
        try:
            z = np.load(f, allow_pickle=False)
            if str(z["src"]) == sig:
                return {"fsec": float(z["fsec"]), "db": z["db"], "voiced": z["voiced"].astype(bool), "onsets": z["onsets"]}
        except Exception:
            pass
    r = analyze(audio)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp.npz")
    np.savez_compressed(tmp, fsec=np.float32(r["fsec"]), db=r["db"].astype(np.float16), voiced=r["voiced"],
                        onsets=r["onsets"], src=np.array(sig))
    os.replace(tmp, f)
    return r


def gaps(va: dict, min_len: float = 1.5) -> list[tuple[float, float]]:
    """ช่วงเงียบ (ไม่มีเสียงร้อง) ยาว ≥ min_len วิ -> [(เริ่ม, จบ)]"""
    v = va["voiced"]
    fs = va["fsec"]
    out = []
    i = 0
    while i < len(v):
        if not v[i]:
            j = i
            while j < len(v) and not v[j]:
                j += 1
            if (j - i) * fs >= min_len:
                out.append((i * fs, j * fs))
            i = j
        else:
            i += 1
    return out


def voiced_at(va: dict, t: float) -> bool:
    i = int(t / va["fsec"])
    return 0 <= i < len(va["voiced"]) and bool(va["voiced"][i])


def onset_rate(va: dict, t0: float, t1: float) -> float:
    on = va["onsets"]
    if t1 <= t0:
        return 0.0
    return float(((on >= t0) & (on < t1)).sum()) / (t1 - t0)


MIN_VOICED = 10.0              # วินาที — เสียงร้องรวมน้อยกว่านี้ (บรรเลง/แยกเสียงพัง) วัดความคลุมไม่ได้


def cover(va: dict | None, spans, pad: float = 0.3) -> float | None:
    """% ของเวลาที่มีเสียงร้องจริง ที่มีบรรทัดเนื้อคลุมอยู่ — spans = [(เริ่ม, จบ)] เป็นเวลาในเสียง
    เนื้อครบทั้งเพลงได้ ~90+ (คลังจริง: ต่ำสุด 61) / ซับแค่บทพูดในเอ็มวีได้ 5 — ไม่มีแผนที่เสียงร้อง = None"""
    if not va or not len(va["voiced"]):
        return None
    v = va["voiced"]
    fs = va["fsec"]
    tot = int(v.sum())
    if tot * fs < MIN_VOICED:
        return None
    m = np.zeros(len(v), bool)
    for a, b in spans:
        i, j = max(0, int((a - pad) / fs)), min(len(v), int((b + pad) / fs) + 1)
        if j > i:
            m[i:j] = True
    return round(100.0 * int((v & m).sum()) / tot, 1)


def envelope(va: dict | None, per_sec: int = 10) -> list[float] | None:
    """คลื่นเสียงร้องแบบหยาบ (0..1, per_sec จุด/วิ) จากแคชเดียวกัน — แท็บ ✂️ ไม่ต้องโหลด/ถอดรหัส vocals.m4a ทั้งไฟล์"""
    if not va or not len(va["db"]):
        return None
    db = np.asarray(va["db"], np.float32)
    k = max(1, int(round(1.0 / (per_sec * va["fsec"]))))
    n = len(db) // k
    if not n:
        return None
    g = db[:n * k].reshape(n, k).max(axis=1)
    ref = float(np.percentile(g, 97))
    lin = np.power(10.0, (g - ref) / 20.0)                   # dB -> สัดส่วนความดังเทียบช่วงดังของเพลง
    return [round(float(x), 2) for x in np.clip(lin, 0.0, 1.0)]


def main() -> None:
    argv = sys.argv[1:]
    audio = None
    if "--audio" in argv:
        k = argv.index("--audio")
        audio = Path(argv[k + 1])
        del argv[k:k + 2]
    if not argv:
        print(__doc__)
        sys.exit(2)
    vid = argv[0]
    if audio is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fa_align as F
        audio = F.default_audio(vid)
    va = load(vid, audio)
    if va is None:
        print(json.dumps({"error": "ไม่มีไฟล์เสียง"}))
        return
    dur = len(va["voiced"]) * va["fsec"]
    print(json.dumps({"dur": round(dur, 1), "voiced": round(float(va["voiced"].mean()) * 100, 1),
                      "gaps": [[round(a, 2), round(b, 2)] for a, b in gaps(va)],
                      "onsets_per_s": round(len(va["onsets"]) / max(1.0, dur), 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
