#!/usr/bin/env python3
"""เทียบตัวแยกเสียง demucs เดิมกับ demucs-mlx บนสำเนาไฟล์เสียง (ไม่แตะคลังเพลง)
demucs สุ่มตำแหน่งตัดทุกครั้ง จึงวัดเดิมเทียบเดิมเป็นฐาน แล้วดูว่าตัวใหม่ต่างจากเดิมมากกว่าฐานไหม
วัด: เวลา แรม ความเหมือนของเสียง (SDR) และเวลาที่ FA จับได้จากเสียงร้องแต่ละชุด
ใช้:  .venv/bin/python scripts/eval_sep.py --mlx-python <python ของ venv demucs-mlx> --out <โฟลเดอร์> <videoId>...
รันตอนไม่มีเพลงเล่น: ใช้ GPU เต็มที่ทีละตัว"""
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--mlx-python", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--songs", default=str(ROOT / "songs" / "yt"))
ap.add_argument("vids", nargs="+")
a = ap.parse_args()
OUT = Path(a.out)
OUT.mkdir(parents=True, exist_ok=True)
FF = shutil.which("ffmpeg")


def timed(cmd):
    t0 = time.monotonic()
    r = subprocess.run(["/usr/bin/time", "-l"] + cmd, capture_output=True, text=True)
    m = re.search(r"(\d+)\s+maximum resident set size", r.stderr)
    return {"sec": round(time.monotonic() - t0, 1), "mb": round(int(m.group(1)) / 1048576) if m else 0, "rc": r.returncode}, r.stderr[-300:]


def pcm(f):
    r = subprocess.run([FF, "-v", "error", "-i", str(f), "-f", "f32le", "-ac", "2", "-ar", "44100", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def stem(root, name):
    hits = sorted(p for p in Path(root).rglob("*") if p.is_file() and p.stem == name)
    return pcm(hits[0]) if hits else None


def sdr(ref, est):
    n = min(len(ref), len(est))
    return round(float(10 * np.log10(np.sum(ref[:n] ** 2) / max(np.sum((ref[:n] - est[:n]) ** 2), 1e-12))), 1)


def fa_times(vid, audio, texts, work, tag):
    """เวลาเริ่มต่อบรรทัดจาก FA แคชแยกต่อชุดเสียงในโฟลเดอร์ชั่วคราว"""
    env = {**os.environ, "KARA_FA_CACHE": str(work / f"fa-{tag}"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fa_align.py"), vid, "--audio", str(audio)],
                       input=json.dumps({"texts": texts}), capture_output=True, text=True, env=env, timeout=400)
    last = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
    if r.returncode or not last:
        return None
    return [l.get("t") for l in json.loads(last[-1]).get("lines") or []]


def wav_vocals(root, dest):
    src = next(p for p in Path(root).rglob("*") if p.is_file() and p.stem == "vocals")
    subprocess.run([FF, "-y", "-v", "error", "-i", str(src), "-c:a", "aac", "-b:a", "192k", "-f", "ipod", str(dest)], check=True)
    return dest


def time_diff(ref, est):
    pairs = [(x, y) for x, y in zip(ref or [], est or []) if x is not None and y is not None]
    if not pairs:
        return None
    d = np.abs(np.array([x - y for x, y in pairs]))
    return {"lines": len(pairs), "within0.5s%": round(float((d <= 0.5).mean() * 100)), "meanSec": round(float(d.mean()), 2)}


for vid in a.vids:
    src = next(Path(a.songs).glob(f"*{vid}*"))
    work = OUT / vid
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    audio = work / "audio.m4a"
    shutil.copy(src / "audio.m4a", audio)
    stock = [sys.executable, "-m", "demucs", "-n", "htdemucs", "--two-stems", "vocals", "-d", "mps", "-o"]
    row = {"vid": vid}
    row["stockA"], _ = timed(stock + [str(work / "A"), str(audio)])
    row["stockB"], _ = timed(stock + [str(work / "B"), str(audio)])
    row["mlx"], err = timed([a.mlx_python, "-m", "demucs_mlx", "-n", "htdemucs", "-o", str(work / "M"), str(audio)])
    if row["mlx"]["rc"]:
        row["err"] = err
    else:
        va, vb, vm = stem(work / "A", "vocals"), stem(work / "B", "vocals"), stem(work / "M", "vocals")
        na, nb = stem(work / "A", "no_vocals"), stem(work / "B", "no_vocals")
        parts = [stem(work / "M", s) for s in ("drums", "bass", "other")]
        n = min(len(p) for p in parts)
        nm = sum(p[:n] for p in parts)
        row["sdr"] = {"เสียงร้อง เดิมเทียบเดิม": sdr(va, vb), "เสียงร้อง ใหม่เทียบเดิม": sdr(va, vm),
                      "ดนตรี เดิมเทียบเดิม": sdr(na, nb), "ดนตรี ใหม่เทียบเดิม": sdr(na, nm)}
        lyr = json.loads((src / "lyrics.json").read_text("utf-8"))
        texts = [l["x"] for l in lyr.get("lines") or []]
        if texts:
            ta = fa_times(vid, wav_vocals(work / "A", work / "a.m4a"), texts, work, "a")
            tb = fa_times(vid, wav_vocals(work / "B", work / "b.m4a"), texts, work, "b")
            tm = fa_times(vid, wav_vocals(work / "M", work / "m.m4a"), texts, work, "m")
            row["fa"] = {"เดิมเทียบเดิม": time_diff(ta, tb), "ใหม่เทียบเดิม": time_diff(ta, tm)}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    shutil.rmtree(work, ignore_errors=True)
