#!/usr/bin/env python3
"""สร้างรายการเพลงทั้งหมดกับที่มาของเนื้อ -> lyrics-in/WANTED.tsv
ดูได้ว่าเพลงไหนได้เนื้อมาจากไหน และเพลงไหนยังไม่มี (ต้องวางไฟล์ให้เองใน lyrics-in/)"""
import json, os, re, glob

VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
rows = []
for info in sorted(glob.glob("songs/yt/*/info.json")):
    d = os.path.dirname(info)
    if not os.path.isfile(os.path.join(d, "vocals.m4a")):
        continue                                  # ยังไม่มีสเต็ม = ยังจับเวลาไม่ได้
    m = VID.search(os.path.basename(d))
    if not m:
        continue
    vid = m.group(1)
    try:
        j = json.load(open(info, encoding="utf-8"))
    except Exception:
        j = {}
    # ที่มาจริงอยู่ใน lyrics.json ไม่ใช่ที่ lyrics-in/ (นั่นเหลือไว้แค่ตอนอยากแก้เอง)
    src, lines = "-", 0
    ly = os.path.join(d, "lyrics.json")
    if os.path.isfile(ly):
        try:
            k = json.load(open(ly, encoding="utf-8"))
            src, lines = k.get("src") or "?", len(k.get("lines") or [])
        except Exception:
            src = "อ่านไม่ได้"
    manual = os.path.isfile(os.path.join("lyrics-in", vid + ".txt")) or \
             os.path.isfile(os.path.join("lyrics-in", vid + ".lrc"))
    rows.append((vid, (j.get("title") or "").replace("\t", " "),
                 (j.get("uploader") or j.get("channel") or "").replace("\t", " "),
                 j.get("duration") or 0, src, lines,
                 "มีไฟล์วางเอง" if manual else ("มีแล้ว" if lines else "ยังไม่มี")))

os.makedirs("lyrics-in", exist_ok=True)
with open("lyrics-in/WANTED.tsv", "w", encoding="utf-8") as f:
    f.write("videoId\ttitle\tartist\tduration_sec\tsrc\tlines\tstatus\n")
    for r in rows:
        f.write("\t".join(str(x) for x in r) + "\n")

need = sum(1 for r in rows if r[-1] == "ยังไม่มี")
print(f"เขียน lyrics-in/WANTED.tsv แล้ว: {len(rows)} เพลง (ยังไม่มีเนื้อ {need} เพลง)")
