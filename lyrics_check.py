#!/usr/bin/env python3
"""ตรวจไฟล์เนื้อเพลงทุกเพลง -> บอกว่าเพลงไหนพร้อมใช้ เพลงไหนต้องดู
ไม่แสดงเนื้อเพลง รายงานเป็นตัวเลขล้วน"""
import json, glob, os, re, subprocess, unicodedata

VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
W = lambda s: sum(1 for c in s if unicodedata.category(c) != "Mn")

def dur_of(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","csv=p=0", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0

rows = []
for d in sorted(glob.glob("songs/yt/*/")):
    d = d.rstrip("/")
    m = VID.search(os.path.basename(d))
    if not m or not os.path.isfile(os.path.join(d, "vocals.m4a")):
        continue
    vid = m.group(1)
    p = os.path.join(d, "lyrics.json")
    if not os.path.isfile(p):
        rows.append((vid, "-", 0, 0, 0, 0, 0.0, "-", "ยังไม่มีเนื้อ")); continue
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        rows.append((vid, "-", 0, 0, 0, 0, 0.0, "-", f"อ่านไม่ได้: {type(e).__name__}")); continue

    L = j.get("lines") or []
    anchor = j.get("anchorPct")
    song = float(j.get("duration") or 0) or dur_of(os.path.join(d, "vocals.m4a"))
    bad = []
    if not L: bad.append("ไม่มีบรรทัด")
    order = sum(1 for a, b in zip(L, L[1:]) if b["t"] < a["t"] - 1e-6)
    if order: bad.append(f"เวลาเรียงผิด {order}")
    over = sum(1 for a, b in zip(L, L[1:]) if b["t"] < a["t"] + a["d"] - 0.2)
    # บรรทัดสุดท้ายคาบเกี่ยวปลายเพลงนิดหน่อยเป็นเรื่องปกติ นับเฉพาะที่หลุดไปจริง ๆ
    past = sum(1 for x in L if song > 0 and x["t"] >= song + 0.5)
    if past: bad.append(f"เลยจบเพลง {past}")
    empty = sum(1 for x in L if not (x.get("x") or "").strip())
    if empty: bad.append(f"บรรทัดว่าง {empty}")
    widths = [W(x.get("x") or "") for x in L] or [0]
    longl = sum(1 for w in widths if w > 40)
    cov = sum(x["d"] for x in L) / song if song else 0.0
    if song and cov < 0.15: bad.append(f"เนื้อคลุมน้อย {cov:.0%}")
    gaps = [b["t"] - (a["t"] + a["d"]) for a, b in zip(L, L[1:])]
    gmax = max(gaps) if gaps else 0.0

    rows.append((vid, j.get("src", "?"), len(L), over, longl, max(widths),
                 round(cov, 2), "-" if anchor is None else f"{anchor:.0f}%",
                 "; ".join(bad) if bad else "ok"))

hdr = f"{'videoId':13}{'ที่มา':17}{'บรรทัด':>7}{'ทับ':>5}{'ยาว>40':>7}{'กว้างสุด':>9}{'คลุม':>6}{'anchor':>8}  ผล"
print(hdr); print("-" * len(hdr))
for r in rows:
    print(f"{r[0]:13}{r[1]:17}{r[2]:7d}{r[3]:5d}{r[4]:7d}{r[5]:9d}{r[6]:6.2f}{r[7]:>8}  {r[8]}")
ok = sum(1 for r in rows if r[8] == "ok")
print(f"\nพร้อมใช้ {ok}/{len(rows)} เพลง")
with open("lyrics-in/CHECK.tsv", "w", encoding="utf-8") as f:
    f.write("videoId\tsrc\tlines\toverlap\tlong\tmaxWidth\tcoverage\tanchorPct\tresult\n")
    for r in rows: f.write("\t".join(str(x) for x in r) + "\n")
