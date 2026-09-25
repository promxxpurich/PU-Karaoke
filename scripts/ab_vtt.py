#!/usr/bin/env python3
"""ab_vtt.py — ไม้บรรทัดของเกณฑ์คัดซับใน lyrics_sources.from_vtt

ไม่ใช้เน็ต ไม่ใช้ GPU รันได้ทุกครั้งที่แก้เกณฑ์ ใช้ไฟล์ที่มีอยู่จริงบนดิสก์เป็นชุดทดสอบ

    positive: songs/yt/*/sub.th.vtt   ซับไทยของจริง   -> ต้องผ่านทุกไฟล์
    negative: songs/yt/*/sub.en.vtt   ซับแปลอังกฤษ    -> ต้องตกทุกไฟล์

พิมพ์ "ระยะห่าง" ระหว่างคะแนนต่ำสุดฝั่ง TH กับสูงสุดฝั่ง EN ด้วย — ยิ่งกว้างยิ่งปลอดภัย
ถ้าระยะห่างแคบลงหลังแก้เกณฑ์ แปลว่าเกณฑ์นั้นเปราะ แม้ตัวเลขผ่าน/ตกจะยังถูกอยู่ก็ตาม

    ./scripts/ab_vtt.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lyrics_sources as LS                      # noqa: E402

DL = Path(__file__).resolve().parent.parent / "songs" / "yt"


def _ratio(path: Path) -> tuple[float, int]:
    """(สัดส่วน cue ที่ผ่านตัวนับภาษา, จำนวน cue) — ใช้ตัวนับตัวเดียวกับ from_vtt"""
    cues = LS._cues_of(path) if hasattr(LS, "_cues_of") else None
    if cues is None:                              # ยังไม่ได้แยกฟังก์ชัน -> นับเอง
        cues = []
        block: list[str] = []
        for raw in path.read_text("utf-8", errors="replace").splitlines() + [""]:
            if raw.strip():
                block.append(raw)
                continue
            for i, l in enumerate(block):
                if LS._VTT_TS.search(l):
                    body = LS._clean(" ".join(LS._clean(x) for x in block[i + 1:]))
                    if body:
                        cues.append(body)
                    break
            block = []
    if not cues:
        return 0.0, 0
    ok = getattr(LS, "_nonlatin_letter", LS._has_thai)
    return 100.0 * sum(1 for c in cues if ok(c)) / len(cues), len(cues)


def main() -> None:
    pos = sorted(DL.glob("*/sub.th.vtt"))
    neg = sorted(DL.glob("*/sub.en.vtt"))
    if not pos:
        print("ไม่เจอไฟล์ซับเลย — รันจากโฟลเดอร์โปรเจกต์ไหม?")
        raise SystemExit(2)

    fails, th_scores, en_scores = [], [], []
    for f in pos:
        r, n = _ratio(f)
        th_scores.append(r)
        if LS.from_vtt(f, 0.0) is None:
            fails.append(("TH ควรผ่านแต่ตก", f, r, n))
    for f in neg:
        r, n = _ratio(f)
        en_scores.append(r)
        if LS.from_vtt(f, 0.0) is not None:
            fails.append(("EN ควรตกแต่ผ่าน", f, r, n))

    okp = len(pos) - sum(1 for k, *_ in fails if k.startswith("TH"))
    okn = len(neg) - sum(1 for k, *_ in fails if k.startswith("EN"))
    print(f"positive (sub.th.vtt) ผ่าน {okp}/{len(pos)}")
    print(f"negative (sub.en.vtt) ตก  {okn}/{len(neg)}")
    if th_scores and en_scores:
        lo, hi = min(th_scores), max(en_scores)
        print(f"\nTH ต่ำสุด {lo:5.1f}%   EN สูงสุด {hi:5.1f}%   ระยะห่าง {lo - hi:+.1f} pp")
    for kind, f, r, n in fails:
        print(f"  ✗ {kind}: {f.parent.name[:44]}  ({r:.1f}%, {n} cue)")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
