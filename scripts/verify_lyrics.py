#!/usr/bin/env python3
"""verify_lyrics.py — ตรวจว่าเนื้อเพลงที่ใช้อยู่ "ตรงกับที่ร้องจริง" ไหม แล้วซ่อมให้

  ตัวตัดสินเดียวที่เชื่อได้คือเสียงร้องในไฟล์ จึงถอดเสียงด้วย whisper
  แล้วเอาเนื้อที่ใช้อยู่ไป align กับเส้นเวลานั้น (ใช้เครื่องมือชุดเดียวกับ gen_lyrics.py)

  เนื้อพังได้ 2 แบบ ต้องแยกให้ออกเพราะซ่อมคนละทาง:
    เนื้อผิดเพลง   -> align แล้วแทบไม่เจอที่ลง (anchorPct ต่ำ)   -> ไปเอาแหล่งอื่น
    เวลาเพี้ยน     -> เจอที่ลงเยอะ แต่เวลาไม่ตรง (onTime ต่ำ)    -> เลื่อน/จับเวลาใหม่

  ใช้:  ./scripts/verify_lyrics.py <vid>           ตรวจและซ่อม
        ./scripts/verify_lyrics.py --dry-run       ตรวจทุกเพลง ไม่แก้อะไร (ไว้คาลิเบรตเกณฑ์)
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_lyrics as G
import lyrics_sources as LS
import lyrics_conf as C

TOL = 1.5          # เวลาที่ align เจอ ห่างจากที่ไฟล์บอกได้กี่วินาทีถึงนับว่า "ตรง"
MIN_SHIFT = 0.3    # เลื่อนน้อยกว่านี้ไม่ต้องสนใจ
OK_SCORE = 55      # ได้เท่านี้ถือว่าเนื้อใช้ได้ ไม่ต้องแตะ
MIN_SCORE = 40     # ของใหม่ต้องได้อย่างน้อยเท่านี้ถึงยอมเปลี่ยน
MARGIN = 10        # และต้องดีกว่าของเดิมอย่างน้อยเท่านี้
# หมายเหตุจากการวัดจริง: anchorPct บอกไม่ได้ว่าเนื้อถูกเพลงไหม — เอาเนื้อเพลงอื่นมาใส่
# ยังได้ 56.5% (เพลงถูกได้ 66.8%) เพราะอักษรไทยซ้ำกันเยอะและ align ยอมเพี้ยนได้ 45%
# ตัวที่แยกออกจริงคือ onTime: เนื้อผิดเพลงได้ 0.0% เพราะไม่มีบรรทัดไหนตรงเวลาเลย
RETIME_PENALTY = 0.85   # ตัวที่จับเวลาจาก ASR เอง คะแนนมันเข้าข้างตัวเอง หักไว้ก่อน


# ---------------------------------------------------------------------------
# ให้คะแนน
# ---------------------------------------------------------------------------
def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return 0.0
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def measure(lines: list[dict], chunks: list[dict], duration: float) -> dict:
    """เทียบเนื้อชุดหนึ่งกับเส้นเวลาจริง คืน
       anchorPct  กี่ % ของตัวอักษรที่หาที่ลงในเสียงจริงเจอ  (เนื้อถูกเพลงไหม)
       onTime     กี่ % ที่เจอ *และ* เวลาตรงด้วย             (เวลาถูกไหม)
       shift      ถ้าเลื่อนทั้งเพลงเท่านี้จะดีขึ้น (0 = เลื่อนแล้วไม่ช่วย)"""
    texts = [l["x"] for l in lines]
    weights = [len(G.norm_chars(t)) for t in texts]
    tot = sum(weights)
    out = {"anchorPct": 0.0, "onTime": 0.0, "shift": 0.0, "anchors": []}
    if not tot:
        return out
    anchors = G.align(chunks, texts, duration)
    hits: dict[int, list[float]] = {}       # บรรทัด -> เวลาที่ align เจอ (อาจมีหลายจุด)
    for a in anchors:
        hits.setdefault(a["line"], []).append(a["t"])
    if not hits:
        return out
    out["anchors"] = anchors
    out["anchorPct"] = 100.0 * sum(weights[i] for i in hits) / tot

    def on_time(shift: float) -> float:
        """บรรทัดถือว่าตรงถ้า *จุดใดจุดหนึ่ง* ที่เจอ อยู่ใกล้เวลาที่ไฟล์บอก
        (เนื้อที่ร้องซ้ำจะมีหลายจุด เอาแค่จุดแรกจะตัดสินผิด)"""
        return 100.0 * sum(weights[i] for i, ts in hits.items()
                           if any(abs(t - (lines[i]["t"] + shift)) <= TOL for t in ts)) / tot

    # คะแนนต้องวัดจากไฟล์ "ตามที่เป็นอยู่จริง" — ถ้าเอาคะแนนหลังเลื่อนมาตอบ
    # เพลงที่เวลาเพี้ยนทั้งเพลงจะถูกตัดสินว่าปกติ แล้วไม่มีอะไรถูกซ่อมเลย
    out["onTime"] = on_time(0.0)
    # ค่าเลื่อนที่น่าจะช่วย: ใช้จุดแรกของแต่ละบรรทัด (เพลงเดินไปข้างหน้า) ไม่งั้นค่าจะเอนเข้าหา 0
    med = round(_median([min(ts) - lines[i]["t"] for i, ts in hits.items()]), 2)
    if abs(med) >= MIN_SHIFT and on_time(med) > out["onTime"]:
        out["shift"] = med                      # ไว้ให้ collect_candidates สร้างตัวท้าชิง
    return out


def shifted(lines: list[dict], by: float, duration: float) -> list[dict]:
    out = []
    for l in lines:
        t = max(0.0, round(l["t"] + by, 2))
        out.append({"t": t, "d": l["d"], "x": l["x"]})
    return out


def retime(texts: list[str], anchors: list[dict], duration: float) -> list[dict]:
    """เก็บข้อความเดิมไว้ทุกตัวอักษร จับเวลาใหม่จากเส้นเวลา ASR"""
    starts = G.timings_for_lines(texts, anchors, duration)
    out = []
    for i, st in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else (duration if duration > st else st + 6.0)
        out.append({"t": st, "d": round(max(1.0, min(14.0, nxt - st)), 2), "x": texts[i]})
    return out


# ---------------------------------------------------------------------------
# เก็บผล
# ---------------------------------------------------------------------------
def check_path(folder: Path) -> Path:
    return folder / "lyrics.check.json"


def load_check(folder: Path) -> dict:
    try:
        return json.loads(check_path(folder).read_text("utf-8"))
    except Exception:
        return {}


def save_check(folder: Path, data: dict) -> None:
    check_path(folder).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
def collect_candidates(vid: str, folder: Path, cur: list[dict], cur_src: str,
                       chunks: list[dict], duration: float, cur_m: dict) -> list[dict]:
    """ผู้ท้าชิง: แหล่งอื่นที่มีเวลามาให้ + เนื้อเดิม/เนื้อ description ที่จับเวลาใหม่"""
    cands: list[dict] = []

    def add(kind: str, src: str, lines: list[dict] | None, note: str = "", timed: bool = True):
        if not lines:
            return
        m = measure(lines, chunks, duration)
        m.pop("anchors", None)
        cands.append({"kind": kind, "src": src, "lines": lines, "note": note,
                      "timed": timed, **m})

    if cur_m["shift"]:
        add("shift", cur_src, shifted(cur, cur_m["shift"], duration),
            note=f'เลื่อน {cur_m["shift"]:+.2f}s')

    sub = folder / "sub.th.vtt"
    if sub.is_file() and cur_src != "yt-sub":
        add("source", "yt-sub", LS.from_vtt(sub, duration))

    try:
        info = json.loads((folder / "info.json").read_text("utf-8"))
    except Exception:
        info = {}
    # ใช้เนื้อจาก description เป็นตัวเทียบให้ lrclib — ไม่ใช้เนื้อที่ใช้อยู่ เพราะกำลังสงสัยมันอยู่
    desc, desc_src = G.read_lines(vid)
    baseline = "\n".join(desc) if desc else ""
    got = LS.from_lrclib(info.get("title") or folder.name, info.get("uploader") or "",
                         duration, baseline, info.get("description") or "")
    if got and cur_src != "lrclib":
        add("source", "lrclib", got[0], note=got[1])

    # จับเวลาใหม่ให้เนื้อเดิม — ใช้ตอนเนื้อถูกแต่เวลาเพี้ยนแบบเลื่อนไม่ได้
    if cur_m["anchors"]:
        add("retime", cur_src, retime([l["x"] for l in cur], cur_m["anchors"], duration),
            note="จับเวลาใหม่จากเสียงร้อง", timed=False)

    # เนื้อจาก description (คนละชุดกับที่ใช้อยู่) จับเวลาใหม่
    if desc and [l["x"] for l in cur] != desc:
        dm = measure([{"t": 0.0, "d": 1.0, "x": t} for t in desc], chunks, duration)
        if dm["anchors"]:
            add("retime", desc_src, retime(desc, dm["anchors"], duration),
                note="เนื้อจาก description จับเวลาใหม่", timed=False)
    return cands


def rank(c: dict) -> float:
    """ตัวที่จับเวลาเองจาก ASR คะแนนมันเข้าข้างตัวเอง (วางบรรทัดตรงจุดที่ align เจอพอดี)
    จึงหักคะแนนก่อนเทียบ ไม่งั้นทุกครั้งที่มีคนรายงานจะไหลไปใช้ ASR หมด"""
    return c["onTime"] * (1.0 if c.get("timed", True) else RETIME_PENALTY)


def ruler(folder: Path, vid: str, time_src: str, src: str = "",
          allow_gpu: bool = True) -> tuple[list[dict] | None, str]:
    """ไม้บรรทัดสำหรับวัดเวลา — คืน (chunks, ชื่อไม้บรรทัด) หรือ (None, เหตุผล) ถ้าไม่มี

    ห้ามใช้ไม้บรรทัดที่มาจากแหล่งเดียวกับเวลาที่กำลังจะวัด ไม่งั้นได้คะแนนสูงเทียมทุกครั้ง
    ต้องกันทั้ง timeSrc ("เวลามาจาก auto-caption") และ src ("ตัวหนังสือมาจาก auto-caption")
    เพราะ yt-auto มี timeSrc=self แต่ทั้งเนื้อและเวลามาจากไฟล์ auto.th.vtt ไฟล์เดียวกัน
    auto-caption เร็วกว่ามาก (~0.1s เทียบกับถอดเสียง ~40s) จึงลองก่อนเสมอ"""
    auto = folder / "auto.th.vtt"
    if time_src != "auto-cap" and src != "yt-auto" and auto.is_file():
        w = LS.words_from_auto_vtt(auto)
        if w:
            return G.make_chunks([{"start": w[0]["start"], "end": w[-1]["end"],
                                   "text": "", "words": w}]), "auto-cap"
    if time_src == "asr":
        return None, "เวลามาจากการถอดเสียง จะใช้การถอดเสียงมาวัดตัวเองไม่ได้"
    if not allow_gpu:
        return None, "ไม่มี auto-caption (ใส่ --gpu เพื่อยอมถอดเสียงมาวัด)"
    audio = folder / "vocals.m4a"
    if not audio.is_file():
        audio = folder / "audio.m4a"
    if not audio.is_file():
        return None, "ไม่มีเสียงให้ถอด"
    data = G.get_segments(vid, audio, lang=LS.song_lang(folder, save=False)[0])
    if G._degenerate({"segments": data["segs"]}):
        return None, "ถอดเสียงไม่ได้ผล ตัดสินไม่ได้"
    return G.make_chunks(data["segs"]), "asr"


def verify(vid: str, dry: bool = False, allow_gpu: bool = True) -> dict:
    folder = next((d for d in G.DL.iterdir()
                   if d.is_dir() and not d.name.startswith(".") and G.vid_of(d.name) == vid), None)
    if folder is None:
        return {"vid": vid, "verdict": "unknown", "why": "หาโฟลเดอร์ไม่เจอ"}
    lf = folder / "lyrics.json"
    if not lf.is_file():
        return {"vid": vid, "verdict": "unknown", "why": "ยังไม่มีเนื้อเพลง"}
    j = json.loads(lf.read_text("utf-8"))
    cur, cur_src = j.get("lines") or [], j.get("src") or "?"
    duration = float(j.get("duration") or 0) or G.song_duration(folder)
    # วัด "สิ่งที่ขึ้นจอจริง" = เวลาในไฟล์ + offset ประจำเพลง (ปรับจากรีโมท/Studio)
    # ไม่งั้นคำแนะนำ shift จะนับ offset ซ้ำ และตัวซ่อมจะทิ้งสิ่งที่คนปรับไว้
    try:
        off_f = folder / "lyrics.offset.json"
        off = float(json.loads(off_f.read_text("utf-8")).get("offset") or 0) if off_f.is_file() else 0.0
    except Exception:
        off = 0.0
    if off:
        cur = shifted(cur, off, duration)

    tsrc = C.time_src_of(j)
    chunks, by = ruler(folder, vid, tsrc, cur_src, allow_gpu=allow_gpu)
    if chunks is None:
        # ไม่มีไม้บรรทัดที่เป็นอิสระ -> ต้องบอกว่า "ตรวจไม่ได้" ตรง ๆ ห้ามเดา
        return {"vid": vid, "verdict": "unmeasurable", "src": cur_src, "timeSrc": tsrc,
                "at": time.time(), "why": by}

    m = measure(cur, chunks, duration)
    res = {"vid": vid, "at": time.time(), "src": cur_src, "timeSrc": tsrc,
           "measuredBy": by,
           "score": round(m["onTime"], 1), "anchorPct": round(m["anchorPct"], 1),
           "shift": m["shift"], "lines": len(cur)}

    if m["onTime"] >= OK_SCORE:
        res["verdict"] = "ok"
        return res
    if dry:
        res["verdict"] = "bad"          # โหมดตรวจอย่างเดียว ไม่ต้องไปหาตัวมาแทน
        return res
    if cur_src == "manual-edit":
        # คนแก้เองใน Studio = คนชนะเครื่อง: วัดผลให้ดูอย่างเดียว ไม่เปลี่ยนเนื้อให้เอง
        res["verdict"] = "bad"
        res["why"] = "เนื้อที่แก้เองใน Studio — ไม่เปลี่ยนให้อัตโนมัติ (ดูคำแนะนำเลื่อนใน Studio)"
        return res
    if j.get("best"):
        # เลือกมาแล้วด้วย FA จากทุกแหล่ง — ไม้บรรทัดของที่นี่ (whisper/auto-caption) หยาบกว่า FA
        # ถ้าให้เปลี่ยน จะได้ตัวที่ "เข้ากับไม้บรรทัด" ซึ่งมักแย่กว่า -> วัดให้ดูอย่างเดียว
        res["verdict"] = "bad"
        res["why"] = "เนื้อที่ระบบเลือกจากทุกแหล่งแล้ว — ไม่เปลี่ยนซ้ำ (ใช้ 🔎 หาเนื้อ ใน Studio ถ้าอยากเลือกเอง)"
        return res

    cands = collect_candidates(vid, folder, cur, cur_src, chunks, duration, m)
    cands.sort(key=rank, reverse=True)
    res["tried"] = [{"kind": c["kind"], "src": c["src"], "onTime": round(c["onTime"], 1),
                     "anchorPct": round(c["anchorPct"], 1), "note": c["note"]} for c in cands]

    best = cands[0] if cands else None
    if best and rank(best) >= MIN_SCORE and rank(best) >= m["onTime"] + MARGIN:
        res.update(verdict="fixed", to=best["src"], how=best["kind"],
                   scoreAfter=round(best["onTime"], 1), note=best["note"])
        if not dry:
            (folder / "lyrics.prev.json").write_text(lf.read_text("utf-8"), encoding="utf-8")
            G.write_out(folder, vid, best["lines"], duration, best["src"],
                        j.get("engine") or "", note=f'ซ่อมจากรายงาน: {best["note"]}'.strip(),
                        cov=best["anchorPct"])
    else:
        res["verdict"] = "bad"
    return res


def line_of(r: dict) -> str:
    icon = {"ok": "✓", "fixed": "🔧", "bad": "⚠️",
            "unknown": "?", "unmeasurable": "—"}.get(r["verdict"], "?")
    bits = [f'{icon} {r["vid"]} [{r.get("src","-")}]',
            f'ตรงเวลา {r.get("score","-")}%', f'เนื้อตรง {r.get("anchorPct","-")}%']
    if r.get("shift"):
        bits.append(f'เลื่อน {r["shift"]:+.2f}s')
    if r["verdict"] == "fixed":
        bits.append(f'-> {r["to"]} ({r["how"]}) {r.get("scoreAfter")}%')
    if r.get("why"):
        bits.append(r["why"])
    return " | ".join(bits)


_FLAGS = {"--dry-run", "--sweep", "--gpu"}


def main() -> None:
    args = sys.argv[1:]
    sweep = "--sweep" in args                      # ตรวจอย่างเดียว แต่ *บันทึกผล*
    dry = "--dry-run" in args or sweep             # ห้ามแตะ lyrics.json ทั้งสองโหมด
    allow_gpu = "--gpu" in args or not sweep       # กวาดทั้งคลังใช้ไม้บรรทัดฟรีเป็นค่าตั้งต้น
    only = [a for a in args if a not in _FLAGS]    # vid ขึ้นต้นด้วย - ได้ ห้ามคัดด้วย startswith
    vids = only or [G.vid_of(d.name) for d in sorted(G.DL.iterdir())
                    if d.is_dir() and not d.name.startswith(".") and (d / "lyrics.json").is_file()]
    tally: dict[str, int] = {}
    for vid in vids:
        t0 = time.monotonic()
        try:
            r = verify(vid, dry, allow_gpu=allow_gpu)
        except Exception as exc:
            print(f"[ERR] {vid}: {type(exc).__name__}: {exc}", flush=True)
            continue
        tally[r.get("verdict", "?")] = tally.get(r.get("verdict", "?"), 0) + 1
        print(line_of(r) + f' | {time.monotonic()-t0:.0f}s', flush=True)
        if dry and not sweep:
            continue
        # บันทึกผลทุกกรณีรวมถึง unknown ไม่งั้นป้ายในหน้า remote จะค้างที่ "รอตรวจ" ตลอดไป
        folder = next((d for d in G.DL.iterdir()
                       if d.is_dir() and not d.name.startswith(".") and G.vid_of(d.name) == vid), None)
        if folder is None:
            continue
        r["reports"] = load_check(folder).get("reports", [])
        save_check(folder, r)
    if sweep:
        print("\nสรุป: " + "  ".join(f"{k} {v}" for k, v in sorted(tally.items())), flush=True)


if __name__ == "__main__":
    main()
