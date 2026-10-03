#!/usr/bin/env python3
"""ocr_lyrics.py — เนื้อที่ "ฝังอยู่ในวิดีโอ" (Lyric Video / MV ที่มีซับในภาพ) -> บรรทัดพร้อมเวลาที่ขึ้นจอจริงของคลิปนี้

แหล่งเดียวที่ได้เวลาของ "คลิปนี้" ตรง ๆ โดยไม่ต้องมีบัญชีอะไร: ตัวหนังสือขึ้นตอนร้อง (วัดแล้วคลาด ≲ 0.5 วิ)
อ่านด้วย Apple Vision (ภาษาไทย th-TH) ผ่านโปรแกรมเล็ก ๆ scripts/kara_ocr.swift (คอมไพล์ครั้งแรกเองด้วย swiftc)
ตัวสะกดจาก OCR เพี้ยนได้ (ภาพพื้นหลัง/ฟอนต์ตกแต่ง) จึงใช้เป็น "พยานเวลา" เป็นหลัก: server จับคู่บรรทัดของ
แหล่งอื่นกับข้อความที่อ่านได้ (ไม่ต้องตรงทุกตัว) แล้วใช้เวลาที่ขึ้นจอของคลิป

ขั้นตอน: ffmpeg 2 ภาพ/วิ กว้าง 960 -> OCR -> ต่อเฟรมที่ข้อความเดิม (คล้ายกัน ≥ 70%) เป็นช่วงเดียว
-> ทิ้งข้อความที่ค้างทั้งคลิป (โลโก้/ชื่อเพลง) -> [{t0, t1, x}]
แคช lyrics-preview/_ocr/<vid>.json ผูกกับไฟล์วิดีโอ — คลิปที่ไม่มีตัวหนังสือก็จำว่า "ไม่มี" (ไม่อ่านซ้ำ)

ใช้งาน: ocr_lyrics.py <videoId> [--video PATH] [--probe]   (--probe = ดูแค่ 12 ภาพว่ามีเนื้อในภาพไหม)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "kara_ocr.swift"
BIN = BASE / ".cache" / "bin" / "kara_ocr"
CACHE = Path(os.environ.get("KARA_OCR_CACHE") or (Path(os.environ["KARA_FA_CACHE"]).parent / "_ocr"
                                                   if os.environ.get("KARA_FA_CACHE") else BASE / "lyrics-preview" / "_ocr"))
DL = Path(os.environ["KARA_SONGS_DIR"]) if os.environ.get("KARA_SONGS_DIR") else BASE / "songs" / "yt"
FPS = 2.0
WIDTH = 960
VERSION = 1
_LET = re.compile(r"[฀-๿A-Za-z]")
_THAI = re.compile(r"[฀-๿]")


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", s or "").lower() if c.isalnum())


def ensure_bin() -> Path:
    """คอมไพล์ kara_ocr ครั้งแรก (หรือเมื่อซอร์สใหม่กว่า) — ต้องมี Xcode Command Line Tools (swiftc)"""
    if BIN.is_file() and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return BIN
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise RuntimeError("ไม่มี swiftc (ติดตั้ง Xcode Command Line Tools: xcode-select --install)")
    BIN.parent.mkdir(parents=True, exist_ok=True)
    tmp = BIN.with_name(BIN.name + ".tmp")
    subprocess.run([swiftc, "-O", str(SRC), "-o", str(tmp)], check=True, capture_output=True, timeout=300)
    os.replace(tmp, BIN)
    return BIN


def song_dir(vid: str) -> Path | None:
    for d in DL.iterdir():
        if d.is_dir() and (d.name == vid or d.name.endswith(f"[{vid}]")):
            return d
    return None


def _sig(video: Path) -> str:
    st = video.stat()
    return f"v{VERSION}:{st.st_size}:{st.st_mtime_ns}"


def _frames(video: Path, out: Path, fps: float = FPS, start: float = 0.0, count: int = 0) -> list[Path]:
    args = ["ffmpeg", "-v", "error"]
    if start:
        args += ["-ss", f"{start:.2f}"]
    args += ["-i", str(video), "-vf", f"fps={fps},scale={WIDTH}:-2", "-q:v", "3"]
    if count:
        args += ["-frames:v", str(count)]
    args += [str(out / "f_%05d.jpg")]
    subprocess.run(args, check=True, capture_output=True, timeout=600)
    return sorted(out.glob("f_*.jpg"))


def _ocr(files: list[Path]) -> dict[str, list]:
    b = ensure_bin()
    got: dict[str, list] = {}
    for k in range(0, len(files), 150):
        chunk = files[k:k + 150]
        p = subprocess.run([str(b), *map(str, chunk)], capture_output=True, text=True, timeout=600)
        for line in p.stdout.splitlines():
            try:
                j = json.loads(line)
                got[j["f"]] = j.get("t") or []
            except Exception:
                pass
    return got


def _items(raw: list) -> list[tuple[str, float]]:
    """ข้อความที่น่าจะเป็นเนื้อ (≥ 4 ตัวอักษร) -> [(ข้อความ, ตำแหน่งแนวตั้ง)]"""
    out = []
    for t in raw:
        x = " ".join(str(t[0]).split())
        if len(_LET.findall(x)) >= 4:
            out.append((x, float(t[3]) + float(t[5]) / 2))
    return out


def _sim(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz
        return fuzz.ratio(a, b)
    except Exception:
        import difflib
        return 100 * difflib.SequenceMatcher(None, a, b).ratio()


def cues_from(frames: list[tuple[float, list[tuple[str, float]]]], dur: float) -> list[dict]:
    """[(เวลา, [(ข้อความ, y)])] -> ช่วงที่ข้อความเดียวกันค้างบนจอ [{t0, t1, x, n}]"""
    step = 1.0 / FPS
    active: list[dict] = []
    done: list[dict] = []
    for t, items in frames:
        seen = set()
        for x, y in items:
            k = norm(x)
            best, bs = None, 0.0
            for c in active:
                if id(c) in seen:
                    continue
                s = _sim(k, c["k"])
                if s > bs:
                    best, bs = c, s
            if best is not None and bs >= 70 and abs(best["y"] - y) < 0.15:
                best["t1"] = t + step
                best["var"][x] = best["var"].get(x, 0) + 1
                best["n"] += 1
                seen.add(id(best))
            else:
                c = {"t0": t, "t1": t + step, "k": k, "y": y, "var": {x: 1}, "n": 1}
                active.append(c)
                seen.add(id(c))
        for c in list(active):
            if id(c) not in seen and t - c["t1"] > step * 1.5:     # หายไปเกิน ~1 วิ = จบช่วง
                active.remove(c)
                done.append(c)
    done += active
    out = []
    for c in done:
        if c["n"] < 2:                                     # โผล่เฟรมเดียว = เปลี่ยนฉาก/อ่านพลาด
            continue
        if dur and (c["t1"] - c["t0"]) > max(30.0, 0.3 * dur):
            continue                                       # ค้างทั้งคลิป = โลโก้/ชื่อเพลง ไม่ใช่เนื้อ
        x = max(c["var"].items(), key=lambda kv: kv[1])[0]
        out.append({"t0": round(c["t0"], 2), "t1": round(c["t1"], 2), "x": x, "n": c["n"], "y": round(c["y"], 3)})
    out.sort(key=lambda c: (c["t0"], -c["y"]))
    # ข้อความเดียวกันที่โผล่ซ้ำทั้งเพลงหลายสิบครั้ง (ลายน้ำที่กะพริบ) -> ทิ้ง
    cnt: dict[str, int] = {}
    for c in out:
        cnt[norm(c["x"])] = cnt.get(norm(c["x"]), 0) + 1
    return [c for c in out if cnt[norm(c["x"])] <= 12]


def probe(video: Path, dur: float) -> int:
    """จำนวนภาพ (จาก 12 ภาพกลางเพลง) ที่มีข้อความไทยยาวพอจะเป็นเนื้อ"""
    with tempfile.TemporaryDirectory() as td:
        n = 0
        for k in range(12):
            t = dur * (0.15 + 0.7 * k / 11)
            fs = _frames(video, Path(td), 1.0, t, 1)
            for f in fs:
                f.rename(Path(td) / f"p_{k:02d}.jpg")
        got = _ocr(sorted(Path(td).glob("p_*.jpg")))
        for raw in got.values():
            if any(len(_THAI.findall(x)) >= 6 for x, _ in _items(raw)):
                n += 1
        return n


def run(vid: str, video: Path | None = None, force: bool = False) -> dict:
    d = song_dir(vid) if video is None else video.parent
    video = video or (d / "video.mp4" if d else None)
    if not video or not video.is_file():
        return {"error": "ไม่มีวิดีโอ"}
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{vid}.json"
    sig = _sig(video)
    if f.is_file() and not force:
        try:
            j = json.loads(f.read_text("utf-8"))
            if j.get("sig") == sig:
                return j
        except Exception:
            pass
    dur = 0.0
    try:
        info = json.loads((video.parent / "info.json").read_text("utf-8"))
        dur = float(info.get("duration") or 0)
    except Exception:
        pass
    if not dur:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True)
        dur = float(p.stdout.strip() or 0)
    hits = probe(video, dur)
    out = {"v": VERSION, "sig": sig, "probe": hits, "cues": []}
    if hits >= 4:                                     # มีเนื้อในภาพจริง -> อ่านทั้งคลิป
        with tempfile.TemporaryDirectory() as td:
            files = _frames(video, Path(td))
            got = _ocr(files)
            frames = [((i) / FPS, _items(got.get(p.name) or [])) for i, p in enumerate(files)]
        out["cues"] = cues_from(frames, dur)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    os.replace(tmp, f)
    return out


def retime(lines: list[dict], cues: list[dict], min_sim: float = 62.0) -> tuple[list[dict], int]:
    """เวลาของ "ข้อความจากแหล่งอื่น" ตามที่ตัวหนังสือขึ้นในคลิป -> (บรรทัดใหม่, จำนวนบรรทัดที่จับคู่ได้)
    จับคู่แบบเรียงลำดับ (ไม่ย้อนหลัง) ด้วยความคล้ายบางส่วน — OCR สะกดเพี้ยนได้ ไม่ต้องตรงทุกตัว
    บรรทัดที่ไม่เจอในภาพ: เกลี่ยระหว่างบรรทัดที่เจอข้างหน้า-ข้างหลัง (หรือคงเวลาเดิม + offset ใกล้สุด)"""
    try:
        from rapidfuzz import fuzz
        score = lambda a, b: max(fuzz.ratio(a, b), fuzz.partial_ratio(a, b) - 8) if a and b else 0.0
    except Exception:
        import difflib
        score = lambda a, b: 100 * difflib.SequenceMatcher(None, a, b).ratio()
    ck = [norm(c["x"]) for c in cues]
    out = [dict(l) for l in lines]
    hit: dict[int, float] = {}
    j0 = 0
    for i, l in enumerate(out):
        k = norm(l["x"])
        if len(k) < 4:
            continue
        best, bs = None, min_sim
        for j in range(j0, min(len(cues), j0 + 8)):
            sc = score(k, ck[j])
            if sc > bs:
                best, bs = j, sc
        if best is not None:
            hit[i] = float(cues[best]["t0"])
            j0 = best + 1
    if len(hit) < 2:
        return out, len(hit)
    idx = sorted(hit)
    for i in range(len(out)):
        if i in hit:
            out[i]["t"] = round(hit[i], 2)
            continue
        p = max((k for k in idx if k < i), default=None)
        n = min((k for k in idx if k > i), default=None)
        if p is not None and n is not None and lines[n]["t"] > lines[p]["t"]:
            f = (lines[i]["t"] - lines[p]["t"]) / (lines[n]["t"] - lines[p]["t"])
            out[i]["t"] = round(hit[p] + f * (hit[n] - hit[p]), 2)
        else:
            ref = p if p is not None else n
            out[i]["t"] = round(max(0.0, lines[i]["t"] + (hit[ref] - lines[ref]["t"])), 2)
    for i in range(len(out) - 1):                       # เรียงลำดับเสมอ
        if out[i + 1]["t"] <= out[i]["t"]:
            out[i + 1]["t"] = round(out[i]["t"] + 0.3, 2)
    return out, len(hit)


def cached(vid: str, video: Path) -> dict | None:
    f = CACHE / f"{vid}.json"
    try:
        j = json.loads(f.read_text("utf-8"))
        return j if j.get("sig") == _sig(video) else None
    except Exception:
        return None


def main() -> None:
    argv = sys.argv[1:]
    video = None
    if "--video" in argv:
        k = argv.index("--video")
        video = Path(argv[k + 1])
        del argv[k:k + 2]
    if not argv:
        print(__doc__)
        sys.exit(2)
    vid = argv[0]
    if "--probe" in argv:
        d = song_dir(vid)
        v = video or (d / "video.mp4")
        print(json.dumps({"probe": probe(v, float(json.loads((v.parent / "info.json").read_text()).get("duration") or 200))}))
        return
    r = run(vid, video, force="--force" in argv)
    print(json.dumps({"probe": r.get("probe"), "cues": len(r.get("cues") or []), **({"error": r["error"]} if "error" in r else {})},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
