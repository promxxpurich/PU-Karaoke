#!/usr/bin/env python3
"""เตรียมวัตถุดิบให้ MV จากเนื้อเพลง (static/mv/) — ไม่ใช้ AI ไม่แตะไฟล์เนื้อเพลง

    mv_prep.py <โฟลเดอร์เพลง> [--out DIR] [--frames 30]

ทำ 3 อย่าง:
  1. ภาพนิ่งจากคลิป ~30 ภาพ (กระจายทั้งเพลง ข้ามเฟรมมืด/ซ้ำ, ตัดขอบดำของคลิปแนวตั้งออกเอง) -> <out>/frames/fSSS.jpg
  2. ตารางภาพย่อพร้อมเลขภาพ -> <out>/frames/sheet.jpg (ให้คนเขียนบทดูว่ามีรูปอะไรบ้าง)
  3. จังหวะกลองจากดนตรีที่แยกเสียงร้องออก (no_vocals.m4a, ไม่มีก็ใช้ audio.m4a) -> <out>/mv_beats.json {bpm, beats[], onsets[]}
--out = โฟลเดอร์ปลายทาง (ค่าเริ่มต้น = โฟลเดอร์เพลง) ถ้าเป็นที่อื่นจะคัดลอก lyrics.json / lyrics.words.json / cover.jpg และลิงก์ audio.m4a ไปให้ด้วย (ไว้ทดสอบ)
พิมพ์ JSON สรุปบรรทัดสุดท้าย · รันด้วย nice เบา ๆ ทีละเพลง (ffmpeg กระโดดอ่านเฉพาะเฟรม ไม่ถอดทั้งไฟล์)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

NICE = ["nice", "-n", "15"]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(NICE + cmd, capture_output=True, **kw)


def duration(f: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def crop_box(video: Path, dur: float) -> str | None:
    """หาขอบดำ (คลิปแนวตั้ง/จอกว้าง) จากหลายช่วงของคลิป -> 'w:h:x:y' ที่กว้างที่สุดที่เจอบ่อย"""
    boxes: dict[str, int] = {}
    for f in (.2, .4, .6, .8):
        r = run(["ffmpeg", "-v", "info", "-ss", f"{dur * f:.1f}", "-i", str(video), "-t", "2", "-vf", "cropdetect=24:2:0", "-an", "-f", "null", "-"], text=True)
        for line in r.stderr.splitlines():
            if "crop=" in line:
                b = line.rsplit("crop=", 1)[1].strip()
                boxes[b] = boxes.get(b, 0) + 1
    if not boxes:
        return None
    return max(boxes.items(), key=lambda kv: kv[1])[0]


def grab_frames(video: Path, out: Path, n: int) -> list[dict]:
    from PIL import Image, ImageStat
    dur = duration(video)
    if dur <= 0:
        return []
    out.mkdir(parents=True, exist_ok=True)
    crop = crop_box(video, dur)
    vf = (f"crop={crop}," if crop else "") + "scale=-2:'min(720,ih)'"
    got, prev = [], None
    # เป้ากระจายเท่า ๆ กันทั้งเพลง เฟรมไหนมืด/ซ้ำก็ขยับหาใกล้ ๆ
    for t0 in np.linspace(dur * .04, dur * .96, n):
        for dt in (0, 1.5, -1.5, 3, -3):
            t = float(min(max(t0 + dt, 0), dur - .5))
            name = f"f{int(t):03d}.jpg"
            if any(g["file"] == "frames/" + name for g in got):
                continue
            dst = out / name
            r = run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", vf, "-q:v", "3", str(dst)])
            if r.returncode or not dst.is_file():
                continue
            im = Image.open(dst).convert("L")
            st = ImageStat.Stat(im)
            small = np.asarray(im.resize((32, 18)), dtype=np.float32)
            if st.mean[0] < 28 or st.stddev[0] < 14 or (prev is not None and np.abs(small - prev).mean() < 7):
                dst.unlink(missing_ok=True)
                continue
            prev = small
            w, h = Image.open(dst).size
            got.append({"file": "frames/" + name, "t": round(t, 1), "w": w, "h": h, "bright": round(st.mean[0])})
            break
    return got


def contact_sheet(frames: list[dict], out: Path, sheet: Path) -> None:
    from PIL import Image, ImageDraw
    if not frames:
        return
    cw, ch = 256, 160
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    s = Image.new("RGB", (cols * cw, rows * (ch + 22)), "black")
    d = ImageDraw.Draw(s)
    for i, f in enumerate(frames):
        im = Image.open(out / f["file"]).convert("RGB")
        im.thumbnail((cw - 4, ch))
        x, y = (i % cols) * cw, (i // cols) * (ch + 22)
        s.paste(im, (x + (cw - im.width) // 2, y))
        d.text((x + 6, y + ch + 4), Path(f["file"]).stem, fill="yellow")
    s.save(sheet, quality=82)


def beats_of(audio: Path) -> dict:
    """จังหวะแบบง่าย (ไม่ต้องมี librosa): spectral flux ย่านเสียงต่ำ -> หา onset -> tempo จาก autocorrelation -> กริดบีตที่ตรงกับ onset ที่สุด"""
    sr = 11025
    r = run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"])
    x = np.frombuffer(r.stdout, dtype=np.float32)
    if x.size < sr * 5:
        return {"bpm": 0, "beats": [], "onsets": []}
    hop, win = 256, 1024
    nfr = 1 + (x.size - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(nfr)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(win), axis=1))
    lo = spec[:, 1:int(200 / (sr / win))]                 # ย่านกลองเบส/กระเดื่อง
    flux = np.maximum(0, np.diff(np.log1p(lo * 10), axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    fps = sr / hop
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    thr = uniform_filter1d(flux, int(fps * .5)) + .8
    peaks = np.where((flux == maximum_filter1d(flux, int(fps * .1))) & (flux > thr))[0]
    onsets = peaks / fps
    # tempo 70–180 bpm จาก autocorrelation ของ flux
    ac = np.correlate(flux, flux, mode="full")[flux.size - 1:]
    lags = np.arange(int(fps * 60 / 180), int(fps * 60 / 70))
    lag = lags[np.argmax(ac[lags])]
    period = lag / fps
    bpm = 60 / period
    # เฟสของกริดที่ทับ onset ได้มากที่สุด
    best, phase = -1, 0.0
    for ph in np.linspace(0, period, 40, endpoint=False):
        grid = np.arange(ph, x.size / sr, period)
        score = sum(np.min(np.abs(onsets - g)) < .07 for g in grid) if onsets.size else 0
        if score > best:
            best, phase = score, ph
    beats = np.arange(phase, x.size / sr, period)
    return {"bpm": round(float(bpm), 1), "beats": [round(float(b), 3) for b in beats], "onsets": [round(float(o), 3) for o in onsets]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("--out")
    ap.add_argument("--frames", type=int, default=30)
    a = ap.parse_args()
    song = Path(a.song)
    out = Path(a.out) if a.out else song
    out.mkdir(parents=True, exist_ok=True)
    if out.resolve() != song.resolve():
        for n in ("lyrics.json", "lyrics.words.json", "cover.jpg", "info.json"):
            if (song / n).is_file():
                shutil.copy2(song / n, out / n)
        link = out / "audio.m4a"
        if not link.exists() and (song / "audio.m4a").is_file():
            os.symlink((song / "audio.m4a").resolve(), link)
    summary: dict = {"song": song.name, "out": str(out)}
    video = next((song / n for n in ("video.mp4", "video.webm", "video.mkv") if (song / n).is_file()), None)
    if video:
        frames = grab_frames(video, out / "frames", a.frames)
        contact_sheet(frames, out, out / "frames" / "sheet.jpg")
        (out / "frames" / "frames.json").write_text(json.dumps(frames, ensure_ascii=False))
        summary["frames"] = len(frames)
        summary["portrait"] = bool(frames) and frames[0]["h"] > frames[0]["w"]
    aud = song / "no_vocals.m4a" if (song / "no_vocals.m4a").is_file() else song / "audio.m4a"
    if aud.is_file():
        b = beats_of(aud)
        (out / "mv_beats.json").write_text(json.dumps(b))
        summary["bpm"] = b["bpm"]
        summary["beats"] = len(b["beats"])
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
