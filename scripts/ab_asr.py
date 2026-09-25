#!/usr/bin/env python3
"""เทียบโมเดลถอดเสียง (whisper large-v3 vs turbo) ด้วยเมตริกเดียวกับที่ระบบใช้ตัดสินจริง

    ./scripts/ab_asr.py --list                 # ดูกลุ่มทดสอบก่อนเผา GPU
    KARA_ASR_MODEL=mlx-community/whisper-large-v3-turbo ./scripts/ab_asr.py --run --n 12
    ./scripts/ab_asr.py --score                # เทียบทุก tag ที่มีใน _seg/

วัดกับเพลงที่ "เวลาไม่ได้มาจาก whisper" เท่านั้น (yt-sub / lrclib / manual-lrc)
เพลง src=asr ใช้วัดไม่ได้ เพราะ lyrics.json ของมันสร้างจากผลถอดเสียงของ large-v3 เอง
เทียบกับแคชตัวเดิมย่อมได้คะแนนสูงเทียม = สรุปผิดว่า large-v3 ชนะทุกครั้ง

--run เขียนแค่ _seg/<vid>.<tag>.json กับ _ab.jsonl ไม่แตะ lyrics.json ของเพลงไหนเลย
"""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_lyrics as G                       # noqa: E402
import verify_lyrics as V                    # noqa: E402

AB_LOG = G.BASE / "lyrics-preview" / "_ab.jsonl"
GROUND_TRUTH = {"yt-sub", "lrclib", "manual-lrc"}
MIN_LINES, MIN_DUR = 20, 120.0


def panel() -> list[tuple[str, Path, dict]]:
    """กลุ่มทดสอบแบบกำหนดตายตัว (เรียงตาม videoId ไม่สุ่ม) -> รันซ้ำได้ผลเดิม"""
    out = []
    for d in sorted(G.DL.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        f = d / "lyrics.json"
        if not f.is_file():
            continue
        try:
            lj = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        if lj.get("src") not in GROUND_TRUTH:
            continue
        if len(lj.get("lines") or []) < MIN_LINES or float(lj.get("duration") or 0) < MIN_DUR:
            continue
        if not (d / "vocals.m4a").is_file():
            continue        # ต้องใช้ไฟล์เสียงชนิดเดียวกันทุกโมเดล ไม่งั้นเทียบกันไม่ได้
        out.append((G.vid_of(d.name), d, lj))
    return sorted(out, key=lambda r: r[0])


def cmd_list(n: int) -> None:
    rows = panel()
    print(f"เพลงที่ใช้เป็น ground truth ได้ {len(rows)} เพลง (จะใช้ {min(n, len(rows))} ตัวแรก)\n")
    for i, (vid, d, lj) in enumerate(rows[:n], 1):
        print(f"{i:3}. {vid}  {lj['src']:<10} {len(lj['lines']):3} เส้น  "
              f"{float(lj['duration']):6.0f}s  {d.name[:48]}")


def cmd_run(n: int) -> None:
    # เอาเฉพาะเพลงที่มีแคช large-v3 อยู่แล้ว -> เทียบกันตัวต่อตัวบนเพลงชุดเดียวกัน
    # (ถ้าคนละชุด ค่าเฉลี่ยจะต่างกันเพราะเพลงต่างกัน ไม่ใช่เพราะโมเดล)
    rows = [r for r in panel() if (G.SEG / f"{r[0]}.json").is_file()][:n]
    tag = G.MODEL_TAG
    print(f"ถอดเสียง {len(rows)} เพลงด้วย {G.MODEL}  (tag={tag})\n", flush=True)
    for i, (vid, d, _lj) in enumerate(rows, 1):
        if G.segment_cache_path(vid).is_file():
            print(f"[{i}/{len(rows)}] {vid} มีแคชแล้ว ข้าม", flush=True)
            continue
        t0 = time.monotonic()
        try:
            data = G.get_segments(vid, d / "vocals.m4a")
        except Exception as e:
            print(f"[{i}/{len(rows)}] {vid} ล้มเหลว: {type(e).__name__}: {e}", flush=True)
            continue
        sec = time.monotonic() - t0
        rec = {"vid": vid, "tag": tag, "sec": round(sec, 1), "nsegs": len(data["segs"]),
               "degenerate": G._degenerate({"segments": data["segs"]})}
        with AB_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(rows)}] {vid} {sec:5.0f}s  {len(data['segs']):3} ก้อน"
              f"{'  ⚠️ เสีย' if rec['degenerate'] else ''}", flush=True)


def _tags_for(vid: str) -> list[str]:
    tags = []
    if (G.SEG / f"{vid}.json").is_file():
        tags.append("legacy(large-v3)")      # แคชรุ่นเก่า ชื่อไม่มี tag = large-v3 ทั้งหมด
    for f in sorted(G.SEG.glob(f"{vid}.*.json")):
        t = f.name[len(vid) + 1:-len(".json")]
        if t and not t.endswith(".tmp"):
            tags.append(t)
    return tags


def _load(vid: str, tag: str) -> dict | None:
    f = (G.SEG / f"{vid}.json") if tag.startswith("legacy") else G.SEG / f"{vid}.{tag}.json"
    try:
        return json.loads(f.read_text("utf-8"))
    except Exception:
        return None


def cmd_score() -> None:
    times: dict[str, list[float]] = {}
    for line in (AB_LOG.read_text("utf-8").splitlines() if AB_LOG.is_file() else []):
        try:
            r = json.loads(line)
            times.setdefault(r["tag"], []).append(r["sec"])
        except Exception:
            pass

    per_tag: dict[str, list[float]] = {}
    drops: list[tuple[str, str, float, float]] = []
    print(f"{'videoId':<13} {'tag':<26} {'onTime':>7} {'anchor':>7} {'shift':>7}  เสีย")
    print("-" * 74)
    for vid, d, lj in panel():
        tags = _tags_for(vid)
        if len(tags) < 1:
            continue
        lines, dur = lj["lines"], float(lj["duration"])
        base = None
        for tag in tags:
            data = _load(vid, tag)
            if not data:
                continue
            m = V.measure(lines, G.make_chunks(data["segs"]), dur)
            bad = G._degenerate({"segments": data["segs"]})
            per_tag.setdefault(tag, []).append(m["onTime"])
            print(f"{vid:<13} {tag:<26} {m['onTime']:7.1f} {m['anchorPct']:7.1f} "
                  f"{m['shift']:7.2f}  {'⚠️' if bad else ''}")
            if base is None:
                base = (tag, m["onTime"])
            elif m["onTime"] < base[1] - 15:
                drops.append((vid, tag, base[1], m["onTime"]))

    print("\n" + "=" * 74)
    print(f"{'tag':<26} {'n':>3} {'mean':>7} {'median':>7} {'min':>7} {'เวลาเฉลี่ย':>10}")
    for tag, xs in sorted(per_tag.items()):
        t = times.get(tag) or []
        print(f"{tag:<26} {len(xs):3} {sum(xs)/len(xs):7.1f} {V._median(xs):7.1f} "
              f"{min(xs):7.1f} {(sum(t)/len(t) if t else 0):9.0f}s")
    if drops:
        print("\n⚠️ เพลงที่ตกเกิน 15 จุด (เกณฑ์บอกว่าห้ามเปลี่ยนโมเดล):")
        for vid, tag, a, b in drops:
            print(f"   {vid} {tag}: {a:.1f} -> {b:.1f}")
    else:
        print("\nไม่มีเพลงไหนตกเกิน 15 จุด")


if __name__ == "__main__":
    args = sys.argv[1:]
    n = int(args[args.index("--n") + 1]) if "--n" in args else 12
    if "--run" in args:
        cmd_run(n)
    elif "--score" in args:
        cmd_score()
    else:
        cmd_list(n)
