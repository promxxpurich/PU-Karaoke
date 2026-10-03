#!/usr/bin/env python3
"""lyrics_refine.py — ซ่อมเวลาของเนื้อที่เลือกแล้ว (ไม่แตะข้อความ): เลื่อนเป็นท่อน + ซ่อมช่วงที่เวลาเสีย

บทเรียนเดิม: เคยขยับทีละบรรทัดตาม FA แล้ววัดกับเพลงที่คนจับเวลาเอง ความตรงตก 97% -> 92%
(FA ผิดเองได้ทีละบรรทัด: ฮุคซ้ำ, แร็ป, คอรัส) — ไฟล์นี้จึงมีกฎเหล็ก:
  1. ไม่มีบรรทัดไหนขยับเดี่ยว ๆ ตาม FA
  2. "เลื่อนทั้งท่อน" ได้เมื่อบรรทัดที่ FA มั่นใจ ≥ 4 บรรทัดในท่อนเห็นตรงกัน (MAD ≤ 0.35 วิ) ดีขึ้น ≥ 20 จุด
     และขอบท่อนต้องอยู่ตรงช่วงเงียบ (≥ 1.5 วิ) หรือช่วงห่างของเนื้อ (≥ 4 วิ) — ไม่ตัดกลางท่อนร้อง
     (MV มักต่างจากเวอร์ชันอัลบั้มเป็นท่อน ๆ: อินโทรยาว/บริดจ์เพิ่ม — เลื่อนทั้งเพลงค่าเดียวไม่พอ)
  3. "ซ่อม" เฉพาะบรรทัดที่เวลาเสียแน่ ๆ: อัดกันจนร้องไม่ทัน (> 22 ตัว/วิ) / เกลี่ยเส้นตรง (ช่วงห่างเท่ากันเป๊ะ
     ≥ 4 บรรทัด และ FA เห็นต่าง) — ด้วย FA เฉพาะช่วงระหว่างบรรทัดดีสองข้าง (หมุดหัวท้าย) ไม่ผ่านเกณฑ์ก็
     เกลี่ยตามจำนวนตัวอักษรแล้วดูดเข้าจุดเริ่มพยางค์ (onset) ไม่งั้นคงเดิม

ใช้งาน (subprocess จาก server): stdin {"lines","timeSrc","duration","audio"} -> stdout {"lines","record"}
"""
import json
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

EV_CONF = 0.35            # บรรทัดที่ FA มั่นใจเท่านี้ขึ้นไปถึงนับเป็นหลักฐาน
SEG_MIN_EV = 4
SEG_MIN_SHIFT = 0.4
SEG_MAX_MAD = 0.35
SEG_GAIN = 20.0           # % บรรทัดที่ตรงภายใน 0.5 วิ ต้องดีขึ้นอย่างน้อยเท่านี้
SEG_MAX = 4
SEG_LAMBDA = 2.5          # ค่าปรับต่อท่อน (เหมือน segmentsOf ใน Studio)
BREAK_SIL = 1.5           # ช่วงเงียบที่ตัดท่อนได้
BREAK_SRC = 4.0           # หรือช่วงห่างระหว่างบรรทัดในเนื้อ
FAST_SPS = 24.0           # "พยางค์"/วินาทีที่คนร้องไม่ทันแล้ว = เวลาอัด (ซับที่คนทำ 2,149 บรรทัด: p99.9 15.9 สูงสุด 20.9)
SEG_MAX_SHIFT = 3.0       # เลื่อนเป็นท่อนได้ไม่เกินนี้ (ไกลกว่านี้ = งานเลื่อนทั้งเพลง/คนแก้เอง) กัน FA ไหลไปท่อนฮุคซ้ำ
REPAIR_CONF = 0.2
_LET = re.compile(r"[฀-๿A-Za-z]")
_SYL = re.compile("[\u0e01-\u0e2e]|[A-Za-z]+")
_PAREN_ALL = re.compile(r"^\s*[(（][^)）]*[)）]\s*$")


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def letters(s: str) -> int:
    return len(_LET.findall(s or ""))


def syllables(s: str) -> int:
    """จำนวนพยางค์คร่าว ๆ: พยัญชนะไทย + กลุ่มสระของคำละติน (ไม่นับสระ/วรรณยุกต์ไทยที่เป็นเครื่องหมาย)"""
    n = 0
    for m in _SYL.finditer(s or ""):
        g = m.group(0)
        n += 1 if len(g) == 1 and "\u0e01" <= g <= "\u0e2e" else max(1, len(re.findall(r"[aeiouyAEIOUY]+", g)))
    return n


def _line_dur(t: float, nxt: float) -> float:
    try:
        import lyrics_sources as LS
        return LS.line_dur(t, nxt)
    except Exception:
        return round(max(min(1.0, max(0.3, nxt - t)), min(14.0, nxt - t)), 2)


def repeated(texts: list[str]) -> list[bool]:
    k = [_norm(x) for x in texts]
    n = len(k)
    return [bool(k[i]) and any(k[j] == k[i] for j in range(max(0, i - 2), min(n, i + 3)) if j != i) for i in range(n)]


def defects(lines: list[dict], fa: list[dict] | None) -> list[str | None]:
    """เหตุผลต่อบรรทัดว่าเวลาเสีย (None = ปกติ)"""
    n = len(lines)
    out: list[str | None] = [None] * n
    ts = [float(l["t"]) for l in lines]
    for i in range(n - 1):
        g = ts[i + 1] - ts[i]
        sy = syllables(lines[i]["x"])
        if g < 0.35 and (sy >= 2 or syllables(lines[i + 1]["x"]) >= 2):
            out[i] = out[i + 1] = "collapsed"            # เริ่มแทบพร้อมกัน = ทั้งกลุ่มไม่มีเวลาจริง (รวมตัวท้ายกลุ่ม)
        elif sy >= 2 and sy / max(g, 0.05) > FAST_SPS:
            out[i] = "collapsed"
    gaps = [ts[i + 1] - ts[i] for i in range(n - 1)]
    i = 0
    while i < len(gaps):
        j = i
        while j + 1 < len(gaps) and abs(gaps[j + 1] - gaps[i]) <= 0.02 and gaps[i] > 0:
            j += 1
        if j - i + 1 >= 4:                                   # 5 บรรทัดขึ้นไปห่างเท่ากันเป๊ะ = เกลี่ยเส้นตรง
            run = range(i, j + 2)
            dis = [k for k in run if fa is None or (fa[k].get("conf") or 0) < EV_CONF or abs(fa[k]["t"] - ts[k]) > 0.5]
            if len(dis) * 2 >= len(run):                     # FA เห็นต่างเกินครึ่ง ถึงเชื่อว่าเป็นเวลาเดา
                for k in dis:
                    if out[k] is None:
                        out[k] = "interp"
        i = j + 1
    return out


def _segments(lines, fa, va, rep, bad) -> tuple[list[float], list[dict]]:
    """เลื่อนเป็นท่อน: คืน (ค่าเลื่อนต่อบรรทัด, บันทึกท่อนที่เลื่อน)"""
    import vocal_activity as VA
    n = len(lines)
    shifts = [0.0] * n
    if not fa or n < SEG_MIN_EV:
        return shifts, []
    ts = [float(l["t"]) for l in lines]
    ev = {}
    for i, (l, f) in enumerate(zip(lines, fa)):
        if bad[i] or rep[i] or _PAREN_ALL.match(l["x"] or "") or f.get("sk"):
            continue
        if (f.get("conf") or 0) >= EV_CONF:
            ev[i] = float(f["t"]) - ts[i]
    # ขอบท่อนที่อนุญาต: ระหว่างบรรทัด b-1 กับ b มีช่วงเงียบยาว หรือเนื้อเว้นยาว
    sil = VA.gaps(va, BREAK_SIL) if va else []
    cut = [0]
    for b in range(1, n):
        a0, a1 = ts[b - 1], ts[b]
        if a1 - a0 >= BREAK_SRC or any(g0 < a1 and g1 > a0 and (min(g1, a1) - max(g0, a0)) >= BREAK_SIL * 0.8 for g0, g1 in sil):
            cut.append(b)
    cut.append(n)
    blocks = [(cut[k], cut[k + 1]) for k in range(len(cut) - 1) if cut[k + 1] > cut[k]]
    m = len(blocks)
    if m == 0:
        return shifts, []

    def cost(a, b):                                       # บล็อก a..b-1 รวมเป็นท่อนเดียว
        ds = [ev[i] for i in range(blocks[a][0], blocks[b - 1][1]) if i in ev]
        if not ds:
            return 0.0, None, ds
        med = st.median(ds)
        return sum(abs(x - med) for x in ds), med, ds
    best = [0.0] + [float("inf")] * m
    prev = [0] * (m + 1)
    for b in range(1, m + 1):
        for a in range(b):
            c = best[a] + cost(a, b)[0] + SEG_LAMBDA
            if c < best[b]:
                best[b], prev[b] = c, a
    parts = []
    b = m
    while b > 0:
        parts.append((prev[b], b))
        b = prev[b]
    parts.reverse()
    rec = []
    for a, b in parts:
        _, med, ds = cost(a, b)
        i0, i1 = blocks[a][0], blocks[b - 1][1]
        if med is None or len(ds) < SEG_MIN_EV or abs(med) < SEG_MIN_SHIFT or abs(med) > SEG_MAX_SHIFT:
            continue
        mad = st.median([abs(x - med) for x in ds])
        before = 100 * sum(abs(x) <= 0.5 for x in ds) / len(ds)
        after = 100 * sum(abs(x - med) <= 0.5 for x in ds) / len(ds)
        if mad > SEG_MAX_MAD or after - before < SEG_GAIN:
            continue
        rec.append({"from": i0, "to": i1 - 1, "shift": round(med, 2), "n": len(ds),
                    "before": round(before, 1), "after": round(after, 1)})
    rec.sort(key=lambda r: -r["n"])
    rec = sorted(rec[:SEG_MAX], key=lambda r: r["from"])
    for r in rec:
        for i in range(r["from"], r["to"] + 1):
            shifts[i] = r["shift"]
    # ห้ามลำดับเวลาไขว้กันหลังเลื่อน — ท่อนไหนทำให้ไขว้ ไม่เลื่อนท่อนนั้น
    ok = []
    for r in rec:
        a, b = r["from"], r["to"]
        lo = ts[a - 1] + shifts[a - 1] if a > 0 else -1e9
        hi = ts[b + 1] + shifts[b + 1] if b + 1 < n else 1e9
        if ts[a] + r["shift"] > lo and ts[b] + r["shift"] < hi and ts[a] + r["shift"] >= 0:
            ok.append(r)
        else:
            for i in range(a, b + 1):
                shifts[i] = 0.0
    return shifts, ok


def _spread(ts_new: list[float], a: int, b: int, lo: float, hi: float, texts: list[str], va) -> list[float] | None:
    """เกลี่ยเวลาบรรทัด a..b ระหว่าง lo..hi ตามจำนวนตัวอักษร แล้วดูดเข้าจุดเริ่มพยางค์ที่ใกล้ที่สุด (±0.25 วิ)"""
    if hi - lo < 0.3 * (b - a + 1):
        return None
    w = [max(1, letters(texts[i])) for i in range(a - 1 if a > 0 else a, b + 1)]
    tot = sum(w)
    out = []
    span = hi - lo
    acc = w[0] if a > 0 else 0                      # บรรทัดดีก่อนหน้า (เริ่มที่ lo) กินเวลาส่วนแรก
    for i in range(a, b + 1):
        t = lo + span * acc / tot
        out.append(t)
        acc += max(1, letters(texts[i]))
    if va is not None and len(va["onsets"]):
        on = va["onsets"]
        snapped = []
        for k, t in enumerate(out):
            j = int(abs(on - t).argmin())
            tt = float(on[j]) if abs(on[j] - t) <= 0.25 else t
            if snapped and tt <= snapped[-1] + 0.2:
                tt = t if t > snapped[-1] + 0.2 else snapped[-1] + 0.2
            snapped.append(tt)
        out = snapped
    if any(t >= hi for t in out):
        return None
    return out


def refine_song(vid: str, lines: list[dict], dec: dict | None, dur: float, audio: Path | None, F=None,
                va=None, fa_res: dict | None = None, segments: bool = True) -> dict:
    """lines = เนื้อที่ถูกเลือกแล้ว [{t,d,x}] -> {"lines", "record", "note", "changed"}
    dec["timeSrc"] == "fa" = เวลามาจาก FA อยู่แล้ว: ไม่เลื่อนเป็นท่อน (วัดตัวเอง) ซ่อมได้แค่ช่วงที่อัด"""
    if F is None:
        import fa_align as F                              # noqa: N811
    import vocal_activity as VA
    lines = [dict(l) for l in lines]
    n = len(lines)
    rec = {"v": 1, "segments": [], "repaired": [], "uncertain": []}
    if n < 2:
        return {"lines": lines, "record": rec, "note": "", "changed": False}
    texts = [l["x"] for l in lines]
    ts = [float(l["t"]) for l in lines]
    if va is None and audio:
        try:
            va = VA.load(vid, Path(audio))
        except Exception:
            va = None
    if fa_res is None:
        # มีหมุดที่เวลาปัจจุบัน (±1.5 วิไม่เสียอะไร): ท่อนฮุคซ้ำจะไม่ไหลไปรอบอื่นไกล ๆ แบบ FA ไม่มีหมุด
        # ยังเห็นท่อนที่คลาดไม่กี่วิได้ (MV ต่างจากอัลบั้มเป็นท่อน ๆ) — ที่ไกลกว่านั้นเป็นงานเลื่อนทั้งเพลง
        anchors = [[float(l["t"]), float(l.get("d") or 1.0)] for l in lines]
        fa_res = F.time_lines(vid, texts, dur, Path(audio) if audio else None, anchors=anchors)
    fa = fa_res["lines"]
    rep = repeated(texts)
    bad = defects(lines, fa)
    tsrc = (dec or {}).get("timeSrc") or ""
    note = []
    # 1) เลื่อนเป็นท่อน (เฉพาะเวลาที่ไม่ได้มาจาก FA เอง)
    shifts = [0.0] * n
    if segments and tsrc != "fa":
        shifts, rec["segments"] = _segments(lines, fa, va, rep, bad)
        if rec["segments"]:
            note.append("เลื่อน " + ", ".join(f"บรรทัด {r['from'] + 1}-{r['to'] + 1} {r['shift']:+.2f} วิ" for r in rec["segments"]))
    new_t = [ts[i] + shifts[i] for i in range(n)]
    # 2) ซ่อมช่วงที่เวลาเสีย
    i = 0
    while i < n:
        if not bad[i]:
            i += 1
            continue
        a = i
        while i < n and bad[i]:
            i += 1
        b = i - 1
        lo = new_t[a - 1] if a > 0 else max(0.0, new_t[a] - 8.0)
        hi = new_t[b + 1] if b + 1 < n else (dur or new_t[b] + 8.0)
        how, conf = "", None
        # 2a) FA เฉพาะช่วง มีหมุดที่บรรทัดดีหัว/ท้าย
        try:
            i0, i1 = max(0, a - 1), min(n - 1, b + 1)
            sub = texts[i0:i1 + 1]
            anchors = [[new_t[k], float(lines[k].get("d") or 1.0)] if (k < a or k > b) else None for k in range(i0, i1 + 1)]
            w0 = max(0.0, lo - 0.5)
            w1 = (hi + float(lines[i1].get("d") or 1.0) + 0.5) if b + 1 < n else (dur or hi + 8.0)
            r = F.time_lines(vid, sub, dur, Path(audio) if audio else None, anchors=anchors,
                             opt={"window": [w0, w1]})
            got = r["lines"][a - i0:b - i0 + 1]
            cs = [g.get("conf") or 0 for g in got]
            tt = [g["t"] for g in got]
            mono = all(x < y for x, y in zip([lo] + tt, tt + [hi])) if a > 0 else all(x < y for x, y in zip(tt, tt[1:] + [hi]))
            rate_ok = all(syllables(texts[a + k]) / max(0.05, (tt[k + 1] if k + 1 < len(tt) else hi) - tt[k]) <= FAST_SPS
                          for k in range(len(tt)))
            if sum(cs) / len(cs) >= REPAIR_CONF and mono and rate_ok:
                for k, t in enumerate(tt):
                    new_t[a + k] = t
                how, conf = "fa", round(sum(cs) / len(cs), 3)
        except Exception as exc:
            note.append(f"FA ช่วง {a + 1}-{b + 1} พัง: {type(exc).__name__}")
        # 2b) เกลี่ยตามตัวอักษร + onset
        if not how and b + 1 < n:
            sp = _spread(new_t, a, b, lo, hi, texts, va)
            if sp:
                for k, t in enumerate(sp):
                    new_t[a + k] = t
                how = "spread"
        if how:
            rec["repaired"].append([a, b, how, conf, bad[a]])
        else:
            rec["uncertain"].extend(range(a, b + 1))
    if rec["repaired"]:
        note.append("ซ่อม " + ", ".join(f"{x[0] + 1}-{x[1] + 1}({x[2]})" for x in rec["repaired"]))
    for k, f in enumerate(fa):
        if (f.get("conf") or 0) < REPAIR_CONF and k not in rec["uncertain"] and not any(x[0] <= k <= x[1] for x in rec["repaired"]):
            rec["uncertain"].append(k)
    rec["uncertain"] = sorted(set(rec["uncertain"]))
    changed = any(abs(new_t[k] - ts[k]) > 0.005 for k in range(n))
    if changed:
        order = sorted(range(n), key=lambda k: new_t[k])
        if order != list(range(n)):                       # กันลำดับไขว้ (ไม่ควรเกิด) -> ไม่เปลี่ยนอะไร
            return {"lines": [dict(l) for l in lines], "record": rec, "note": "ลำดับไขว้ ไม่ใช้ผล", "changed": False}
        for k in range(n):
            lines[k]["t"] = round(max(0.0, new_t[k]), 2)
        for k in range(n):
            nxt = lines[k + 1]["t"] if k + 1 < n else (dur if dur and dur > lines[k]["t"] else lines[k]["t"] + 6.0)
            if abs(new_t[k] - ts[k]) > 0.005 or (k + 1 < n and abs(new_t[k + 1] - ts[k + 1]) > 0.005):
                lines[k]["d"] = _line_dur(lines[k]["t"], nxt)
    return {"lines": lines, "record": rec, "note": "; ".join(note), "changed": changed}


def main() -> None:
    req = json.loads(sys.stdin.read() or "{}")
    vid = sys.argv[1] if len(sys.argv) > 1 else req.get("vid")
    audio = req.get("audio")
    out = refine_song(vid, req.get("lines") or [], {"timeSrc": req.get("timeSrc") or ""},
                      float(req.get("duration") or 0), Path(audio) if audio else None,
                      segments=req.get("segments", True))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
