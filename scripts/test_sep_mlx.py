#!/usr/bin/env python3
"""ทดสอบการแยกเสียงด้วย demucs-mlx + ทางสำรอง บนคลิปปลอมสั้น ๆ ไม่แตะคลังจริง
ใช้:  .venv/bin/python scripts/test_sep_mlx.py <python ของ venv demucs-mlx>"""
import json, os, stat, subprocess, sys, tempfile, wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="kara-sepmlx-"))
os.environ.update({"KARA_YT_COOKIES": "none", "KARA_STUDIO_PIN": "0000", "KARA_WARM": "off"})
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import server as K  # noqa: E402

K.SONGS = TMP / "songs"
K.DL_DIR = K.SONGS / "yt"
K.LYRICS_IN = TMP / "lyrics-in"
K.SEG_CACHE = TMP / "seg"
for p in (K.DL_DIR, K.LYRICS_IN, K.SEG_CACHE):
    p.mkdir(parents=True, exist_ok=True)
K._purge_audio_caches = lambda vid: None
fails = 0


def check(name, ok, extra=""):
    global fails
    print(f"{'ผ่าน' if ok else 'ไม่ผ่าน'}  {name} {extra}".rstrip())
    fails += 0 if ok else 1


def make_audio(vid):
    K._dir_cache.clear()
    K._dir_scan_at = 0.0
    d = K.DL_DIR / f"TEST [{vid}]"
    d.mkdir()
    (d / "info.json").write_text(json.dumps({"id": vid, "title": "TEST", "uploader": "t", "duration": 8}), "utf-8")
    subprocess.run([K.FFMPEG or "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=330:d=8", "-f", "lavfi", "-i", "sine=f=110:d=8",
                    "-filter_complex", "[0][1]amerge=inputs=2", "-c:a", "aac", str(d / "audio.m4a")], check=True)
    K._dir_cache.clear()
    K._dir_scan_at = 0.0
    return d


def write_wav(path, value):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes((np.full(8000, value, dtype=np.float32) * 32767).astype(np.int16).tobytes())


# รวมสเต็มดนตรี: ไม่ดังเกินก็ไม่แตะ ดังเกินต้องลดแบบไม่แตก
root = TMP / "merge" / "a"
root.mkdir(parents=True)
write_wav(root / "vocals.wav", 0.1)
for n, v in (("drums", 0.1), ("bass", 0.2), ("other", 0.1)):
    write_wav(root / f"{n}.wav", v)
K._sep_merge_music(root.parent)
with wave.open(str(root / "no_vocals.wav")) as w:
    a = np.frombuffer(w.readframes(10), dtype=np.int16) / 32768
check("รวมดนตรี: ไม่แตกก็ไม่ลดความดัง", abs(float(a[0]) - 0.4) < 0.002, f"{float(a[0]):.3f}")
for n, v in (("drums", 0.6), ("bass", 0.6), ("other", 0.6)):
    write_wav(root / f"{n}.wav", v)
K._sep_merge_music(root.parent)
with wave.open(str(root / "no_vocals.wav")) as w:
    a = np.frombuffer(w.readframes(10), dtype=np.int16) / 32768
check("รวมดนตรี: ดังเกินลดลงไม่ให้แตก", 0.95 < float(a[0]) < 1.0, f"{float(a[0]):.3f}")

# ใช้ตัวใหม่จริง
K.SEP_MLX_PYTHON = Path(sys.argv[1])
d = make_audio("TESTsepmlx1")
K._sep_device = None
K._separate_one("TESTsepmlx1")
check("demucs-mlx: ได้ไฟล์เสียงร้องและดนตรี", (d / "vocals.m4a").is_file() and (d / "no_vocals.m4a").is_file() and not (d / ".sep").exists())
check("demucs-mlx: จำว่าใช้ mlx", K._sep_device == "mlx", str(K._sep_device))
dv = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(d / "no_vocals.m4a")], capture_output=True, text=True).stdout)
check("demucs-mlx: ความยาวไฟล์ดนตรีถูกต้อง", abs(dv - 8) < 0.5, f"{dv:.1f} วิ")

# ตัวใหม่พัง: ตกไปตัวเดิมและหยุดลองเมื่อพังซ้ำ
bad = TMP / "bad-python"
bad.write_text("#!/bin/sh\nmkdir -p x\nexit 3\n")
bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
K.SEP_MLX_PYTHON = bad
K._sep_device = None
K._sep_mlx_fails = 0
d = make_audio("TESTsepmlx2")
K._separate_one("TESTsepmlx2")
check("ตัวใหม่พัง: ตกไป demucs เดิมและได้ไฟล์", (d / "vocals.m4a").is_file() and K._sep_device == "mps" and K._sep_mlx_fails == 1, str(K._sep_device))
K._sep_mlx_fails = K.SEP_MLX_MAX_FAILS
calls = []
orig = K._run_child
K._run_child = lambda kind, vid, cmd, **kw: (calls.append(cmd), orig(kind, vid, cmd, **kw))[1]
d = make_audio("TESTsepmlx3")
K._separate_one("TESTsepmlx3")
check("พังซ้ำ: หยุดลองตัวใหม่ในรอบนี้", all(str(bad) not in " ".join(c) for c in calls) and (d / "vocals.m4a").is_file())
K._run_child = orig

# ปิดด้วย env
K.SEP_MLX_PYTHON = Path(sys.argv[1])
K._sep_mlx_fails = 0
os.environ["KARA_SEP_MLX"] = "off"
K._sep_device = None
d = make_audio("TESTsepmlx4")
K._separate_one("TESTsepmlx4")
check("KARA_SEP_MLX=off: ใช้ตัวเดิม", K._sep_device == "mps", str(K._sep_device))
print(f"สรุป: ไม่ผ่าน {fails}")
sys.exit(1 if fails else 0)
