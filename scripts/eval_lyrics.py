#!/usr/bin/env python3
"""eval_lyrics.py — ชุดวัดผลเวลาเนื้อเพลง (อ่านอย่างเดียว: เขียนได้แค่ lyrics-preview/_eval/ กับแคช FA)

ไม้บรรทัด (ไม่ต้องจับเวลาเพิ่ม ใช้ของที่มีในคลัง):
  gold   = เพลงที่ผู้ใช้แก้เองใน Studio (manual-edit) แต่ "แก้เอง" ไม่ได้แปลว่าทุกบรรทัดจับเวลาเอง
           จึงตัดบรรทัดที่เวลาไม่น่าเชื่อออก: กลุ่มบรรทัดเริ่มห่างกัน < 0.5 วิ (d ≤ 1 = เวลาอัดกัน),
           ช่วงห่างเท่ากันเป๊ะ ≥ 4 บรรทัด (เกลี่ยเส้นตรง), เร็วเกิน 22 ตัว/วิ (ร้องไม่ทันจริง)
  silver = ซับ YouTube ที่คนทำมากับคลิป (yt-sub) และ FA ตรวจแล้วตรง ≥ 75%
หมวดของบรรทัด (บรรทัดหนึ่งอยู่ได้หลายหมวด): fast / backing (วงเล็บ, v) / overlap / repeated / normal

คำสั่ง:
  gold                         สรุปชุด gold/silver
  fa [--opt paren] [--set gold|silver|all] [--side]
                               FA (ไม่มีหมุด แบบที่งานเลือกเนื้อใช้) บนข้อความของไม้บรรทัด -> % ตรงภายใน 0.3/0.5/1 วิ ต่อหมวด
  display [--set ...]          ตรรกะจอจริง (lyrcore ใต้ node) เก่า vs ใหม่: ขึ้นทัน / สว่างตรง / หายก่อนร้องจบ
  freeze [--set ...] [--force] ดึงผู้สมัครทุกแหล่งเก็บไว้ (_eval/src/) ให้ทดลองซ้ำได้โดยไม่พึ่งเน็ต
  best [--set ...] [--opt paren] [--refine]
                               เล่นซ้ำงานเลือกเนื้อบนผู้สมัครที่แช่ไว้ (ไม่มีเนื้อเดิม, ไม่เอาไม้บรรทัดเป็นผู้สมัคร)
                               แล้ววัดเวลาที่ได้กับไม้บรรทัด
  core                         บล็อก lyrcore ใน player.html กับ studio.html ต้องเหมือนกันทุกตัวอักษร
ตัวแปรแวดล้อม: KARA_SONGS_DIR / KARA_FA_CACHE / KARA_EVAL_DIR (ค่าเริ่มต้น = ของโปรเจกต์นี้)
"""
import difflib
import json
import os
import re
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
SONGS = Path(os.environ.get("KARA_SONGS_DIR") or ROOT / "songs" / "yt")
os.environ.setdefault("KARA_SONGS_DIR", str(SONGS))
os.environ.setdefault("KARA_FA_CACHE", str(ROOT / "lyrics-preview" / "_fa"))
EVAL = Path(os.environ.get("KARA_EVAL_DIR") or ROOT / "lyrics-preview" / "_eval")
NODE = next((p for p in (os.environ.get("KARA_NODE"), str(Path.home() / ".local" / "node" / "bin" / "node"),
                         "/opt/homebrew/bin/node", "/usr/local/bin/node") if p and Path(p).is_file()), "node")
_VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")
_LET = re.compile(r"[฀-๿A-Za-z]")
_PAREN = re.compile(r"[(（]")
SILVER_MIN = 75.0


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def letters(s: str) -> int:
    return len(_LET.findall(s or ""))


def song_dirs():
    for d in sorted(SONGS.iterdir()):
        m = _VID.search(d.name)
        if d.is_dir() and m:
            yield m.group(1), d


def jload(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ไม้บรรทัด
# ---------------------------------------------------------------------------
def trusted(lines: list[dict]) -> list[bool]:
    """บรรทัดไหนเวลาน่าเชื่อ (ใช้วัดได้) — ตัดเวลาอัด/เกลี่ยเส้นตรง/เร็วเกินคนร้อง"""
    n = len(lines)
    ok = [bool(norm(l.get("x"))) and l.get("x") != "♪" for l in lines]
    ts = [float(l["t"]) for l in lines]
    for i in range(n):
        d = float(lines[i].get("d") or 0)
        close = (i > 0 and ts[i] - ts[i - 1] < 0.5) or (i + 1 < n and ts[i + 1] - ts[i] < 0.5)
        if close and d <= 1.0:
            ok[i] = False
        span = min(d if d > 0 else 99, (ts[i + 1] - ts[i]) if i + 1 < n and ts[i + 1] > ts[i] else 99)
        if span < 99 and letters(lines[i]["x"]) / max(span, 0.05) > 22:
            ok[i] = False
    gaps = [ts[i + 1] - ts[i] for i in range(n - 1)]
    i = 0
    while i < len(gaps):
        j = i
        while j + 1 < len(gaps) and abs(gaps[j + 1] - gaps[i]) <= 0.03:
            j += 1
        if j - i + 1 >= 3:                       # ช่วงห่างเท่ากัน 3 ช่วงขึ้นไป = 4 บรรทัด
            for k in range(i, j + 2):
                ok[k] = False
        i = j + 1
    return ok


def categories(lines: list[dict]) -> list[set]:
    n = len(lines)
    out = []
    keys = [norm(l.get("x")) for l in lines]
    for i, l in enumerate(lines):
        c = set()
        t, d = float(l["t"]), float(l.get("d") or 0)
        nxt = float(lines[i + 1]["t"]) if i + 1 < n else None
        gap = (nxt - t) if nxt is not None else None
        if gap is not None and gap < 1.5:
            c.add("fast")
        span = min(d if d > 0 else 99, gap if gap and gap > 0 else 99)
        if span < 99 and letters(l["x"]) / max(span, 0.05) >= 12:
            c.add("fast")
        if _PAREN.search(l.get("x") or "") or l.get("v") not in (None, 1, "1"):
            c.add("backing")
        if (nxt is not None and t + d > nxt + 0.3) or (i > 0 and float(lines[i - 1]["t"]) + float(lines[i - 1].get("d") or 0) > t + 0.3):
            c.add("overlap")
        if any(keys[j] == keys[i] for j in range(max(0, i - 2), min(n, i + 3)) if j != i) and keys[i]:
            c.add("repeated")
        if not c:
            c.add("normal")
        out.append(c)
    return out


def refsets(which: str = "all") -> list[dict]:
    """[{vid, dir, kind: gold|silver, lines, ok, cats, dur}]"""
    out = []
    for vid, d in song_dirs():
        j = jload(d / "lyrics.json")
        if not j or not j.get("lines"):
            continue
        src = j.get("src") or ""
        kind = None
        if src == "manual-edit":
            kind = "gold"
        elif src == "yt-sub":
            chk = jload(d / "lyrics.check.json") or {}
            if (chk.get("score") or 0) >= SILVER_MIN and chk.get("measuredBy") == "fa":
                kind = "silver"
        if not kind or (which != "all" and which != kind):
            continue
        lines = [l for l in j["lines"] if isinstance(l.get("t"), (int, float)) and (l.get("x") or "").strip()]
        lines.sort(key=lambda l: l["t"])
        out.append({"vid": vid, "dir": d, "kind": kind, "lines": lines, "ok": trusted(lines),
                    "cats": categories(lines), "dur": float(j.get("duration") or 0)})
    return out


# ---------------------------------------------------------------------------
# สถิติ
# ---------------------------------------------------------------------------
CATS = ("all", "normal", "fast", "backing", "overlap", "repeated")


class Tally:
    def __init__(self):
        self.d = {c: [0, 0, 0, 0] for c in CATS}       # n, ≤0.3, ≤0.5, ≤1.0

    def add(self, cats: set, err: float | None):
        for c in ("all", *cats):
            if c not in self.d:
                continue
            r = self.d[c]
            r[0] += 1
            if err is not None:
                r[1] += err <= 0.3
                r[2] += err <= 0.5
                r[3] += err <= 1.0

    def row(self, c):
        n, a, b, e = self.d[c]
        return f"{c:9s} n={n:5d}  ≤0.3 {100 * a / max(1, n):5.1f}%  ≤0.5 {100 * b / max(1, n):5.1f}%  ≤1.0 {100 * e / max(1, n):5.1f}%"

    def show(self, title: str):
        print(f"== {title}")
        for c in CATS:
            if self.d[c][0]:
                print("   " + self.row(c))

    def pct(self, c="all", k=2):
        n = self.d[c][0]
        return 100 * self.d[c][k] / max(1, n)


def arg(name: str, default=None):
    if name in sys.argv:
        k = sys.argv.index(name)
        return sys.argv[k + 1] if k + 1 < len(sys.argv) and not sys.argv[k + 1].startswith("--") else True
    return default


# ---------------------------------------------------------------------------
# คำสั่ง
# ---------------------------------------------------------------------------
def cmd_gold():
    R = refsets(arg("--set", "all"))
    tot = {}
    for r in R:
        n = sum(r["ok"])
        cs = {}
        for ok, c in zip(r["ok"], r["cats"]):
            if ok:
                for x in c:
                    cs[x] = cs.get(x, 0) + 1
        for x, v in cs.items():
            tot[(r["kind"], x)] = tot.get((r["kind"], x), 0) + v
        print(f"{r['kind']:6s} {r['vid']} ใช้ได้ {n:3d}/{len(r['lines']):3d}  {cs}  {r['dir'].name[:50]}")
    print("รวม:", {f"{k[0]}:{k[1]}": v for k, v in sorted(tot.items())})


def _fa():
    import fa_align as F
    return F


def cmd_fa():
    F = _fa()
    opt = {}
    if arg("--opt") in ("paren", "tail"):
        opt["paren"] = True if arg("--opt") == "paren" else "tail"
    if arg("--side"):
        opt["stem"] = "side"
    T = Tally()
    bias = []
    per = []
    for r in refsets(arg("--set", "all")):
        texts = [l["x"] for l in r["lines"]]
        audio = r["dir"] / "vocals.m4a"
        try:
            res = F.time_lines(r["vid"], texts, r["dur"], audio if audio.is_file() else None, opt=opt or None)
        except Exception as exc:
            print("skip", r["vid"], exc)
            continue
        errs = []
        for l, fl, ok, c in zip(r["lines"], res["lines"], r["ok"], r["cats"]):
            if not ok:
                continue
            e = abs(fl["t"] - float(l["t"])) if (fl.get("conf") or 0) > 0 and not fl.get("sk") else None
            if e is not None:
                errs.append(fl["t"] - float(l["t"]))
            T.add(c, e)
        if errs:
            bias.append(st.median(errs))
        per.append((r["vid"], r["kind"], 100 * sum(abs(x) <= 0.5 for x in errs) / max(1, len(errs)), len(errs)))
    T.show(f"FA ไม่มีหมุด opt={opt or '-'} (เวลาที่ FA ได้ vs ไม้บรรทัด)")
    if bias:
        print(f"   bias มัธยฐาน (FA − คน) = {st.median(bias):+.2f} วิ")
    worst = sorted(per, key=lambda x: x[2])[:8]
    print("   แย่สุด:", ", ".join(f"{v}({k[0]}) {p:.0f}%" for v, k, p, n in worst))
    return T


def cmd_display():
    R = refsets(arg("--set", "all"))
    songs = []
    for r in R:
        truth = [float(l["t"]) if ok else None for l, ok in zip(r["lines"], r["ok"])]
        songs.append({"id": r["vid"], "lines": r["lines"], "truth": truth})
    player = ROOT / "static" / "player.html"
    p = subprocess.run([NODE, str(ROOT / "scripts" / "eval_display.js"), str(player)],
                       input=json.dumps({"songs": songs}, ensure_ascii=False), capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-2000:])
        return
    out = json.loads(p.stdout)
    for k in ("old", "new"):
        o = out[k]
        n = max(1, o["n"])
        print(f"{k:3s}: บรรทัด {o['n']}  ขึ้นทัน(0.5 วิก่อน) {100 * o['seen'] / n:5.1f}%  สว่างตรง ±0.5 {100 * o['lit'] / n:5.1f}%"
              f"  หายก่อนร้องจบ {100 * o['evict'] / n:5.1f}%")
    worse = [s for s in out["songs"] if s["new"]["seen"] < s["old"]["seen"] or s["new"]["lit"] < s["old"]["lit"]]
    if worse:
        print("เพลงที่แย่ลง:", [(s["id"], s["old"], s["new"]) for s in worse[:10]])


def cmd_core():
    a = (ROOT / "static" / "player.html").read_text("utf-8")
    b = (ROOT / "static" / "studio.html").read_text("utf-8")
    def blk(s):
        i, j = s.find("// <lyrcore>"), s.find("// </lyrcore>")
        return s[i:j] if i >= 0 and j > i else None
    ok = blk(a) is not None and blk(a) == blk(b)
    print("lyrcore ตรงกัน" if ok else "lyrcore ไม่ตรงกัน! (แก้ทั้ง player.html และ studio.html ให้เหมือนกัน)")
    return ok


# --- ผู้สมัคร (แช่แข็ง) + เล่นซ้ำงานเลือกเนื้อ ---------------------------------
def _server():
    """นำเข้า server.py แบบไม่เปิดเซิร์ฟเวอร์ ชี้คลังไปที่ SONGS (อ่านอย่างเดียว)"""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("KARA_STUDIO_PIN", "0000")
    import server as SV                                   # noqa: E402
    SV.DL_DIR = SONGS
    SV.SONGS = SONGS.parent
    SV.SEG_CACHE = ROOT / "lyrics-preview" / "_seg" if (ROOT / "lyrics-preview" / "_seg").is_dir() \
        else SONGS.parent.parent / "lyrics-preview" / "_seg"
    SV._dir_cache = {}
    SV._dir_scan_at = 0.0
    import gen_lyrics as G
    real_src = SONGS.parent.parent / "lyrics-preview" / "_src"
    if real_src.is_dir():
        G.SRC = real_src
    return SV


def cmd_freeze():
    SV = _server()
    (EVAL / "src").mkdir(parents=True, exist_ok=True)
    for r in refsets(arg("--set", "all")):
        f = EVAL / "src" / f"{r['vid']}.json"
        if f.is_file() and not arg("--force"):
            continue
        t0 = time.time()
        errs: list = []
        try:
            cands, used = SV._gather_sources(r["vid"], "", "", errs)
        except Exception as exc:
            print("fail", r["vid"], exc)
            continue
        f.write_text(json.dumps({"vid": r["vid"], "at": int(time.time()), "cands": cands, "used": used, "errs": errs},
                                ensure_ascii=False), "utf-8")
        print(f"{r['vid']} {len(cands)} ผู้สมัคร ({', '.join(sorted({c['provider'] for c in cands}))}) {time.time() - t0:.0f}s"
              + (f" พัง: {errs}" if errs else ""), flush=True)


def pair_err(chosen: list[dict], ref: dict) -> list[tuple[int, float | None]]:
    """เวลาที่ระบบคิดว่า "ข้อความต้นบรรทัดของไม้บรรทัด" ถูกร้อง vs เวลาจริง -> [(ลำดับในไม้บรรทัด, |Δt| หรือ None)]
    จับคู่ระดับตัวอักษร (แหล่งต่าง ๆ ตัดบรรทัดไม่เหมือนกัน — จับคู่ทั้งบรรทัดจะนับเป็นพลาดหมดทั้งที่เวลาถูก)
    ตัวอักษรนั้นอยู่กลางบรรทัดของระบบ -> ประมาณเวลาด้วยสัดส่วนตำแหน่งในบรรทัด"""
    def build(lines):
        s_, own, off = [], [], []
        for i, l in enumerate(lines):
            k = norm(l["x"])
            for j, ch in enumerate(k):
                s_.append(ch); own.append(i); off.append(j)
        return "".join(s_), own, off
    cs, cown, coff = build(chosen)
    rs, rown, roff = build(ref["lines"])
    sm = difflib.SequenceMatcher(None, cs, rs, autojunk=False)
    r2c = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            r2c[blk.b + k] = blk.a + k
    starts = {}
    for p, (i, j) in enumerate(zip(rown, roff)):
        if j == 0:
            starts[i] = p
    out = []
    for i, l in enumerate(ref["lines"]):
        p = starts.get(i)
        e = None
        if p is not None:
            n = len(norm(l["x"]))
            for q in range(p, p + max(1, int(0.3 * n)) + 1):      # ตัวต้นบรรทัด (หรือใกล้ ๆ ภายใน 30% แรก)
                if q in r2c and q < len(rown) and rown[q] == i:
                    cq = r2c[q]
                    j = cown[cq]
                    cl = chosen[j]
                    ln = max(1, len(norm(cl["x"])))
                    nxt = chosen[j + 1]["t"] if j + 1 < len(chosen) else cl["t"] + float(cl.get("d") or 3)
                    dd = max(0.3, min(float(cl.get("d") or 3), nxt - cl["t"]))
                    pred = float(cl["t"]) + dd * (coff[cq] - (q - p)) / ln
                    e = abs(pred - float(l["t"]))
                    break
        out.append((i, e))
    return out


def score_cands(SV, F, vid: str, cands: list[dict], dur: float, audio: Path | None, opt: dict | None):
    sets = [(c["texts"] if not c["synced"] else [l["x"] for l in c["lines"]]) for c in cands]
    res = []
    for stt in sets:
        res.append(F.time_lines(vid, stt, dur, audio, opt=opt) if stt else None)
    SV._score_fa(cands, res)
    return res


def cmd_best():
    SV = _server()
    F = _fa()
    opt = {"paren": True} if arg("--opt") == "paren" else None
    refine = bool(arg("--refine"))
    RF = None
    if refine:
        import lyrics_refine as RF                     # noqa: F811
    T_old, T_new = Tally(), Tally()
    rows = []
    for r in refsets(arg("--set", "all")):
        f = EVAL / "src" / f"{r['vid']}.json"
        z = jload(f)
        if not z:
            continue
        drop = {"current"} | ({"yt-sub"} if r["kind"] == "silver" else set())
        cands = [c for c in z["cands"] if c["provider"] not in drop]
        if not cands:
            continue
        audio = r["dir"] / "vocals.m4a"
        audio = audio if audio.is_file() else None
        for c in cands:
            for k in ("match", "faConf", "faLines", "timing", "timingAfter", "shift", "score", "by"):
                c.pop(k, None)
        try:
            score_cands(SV, F, r["vid"], cands, r["dur"], audio, None)
        except Exception as exc:
            print("fa fail", r["vid"], exc)
            continue
        dec = SV._best_decide([dict(c) for c in cands], None)
        old_lines = dec.get("lines") or []
        new_lines, note = old_lines, ""
        if opt or refine:
            c2 = [dict(c) for c in cands]
            for c in c2:
                for k in ("match", "faConf", "faLines", "timing", "timingAfter", "shift", "score", "by"):
                    c.pop(k, None)
            if opt:
                score_cands(SV, F, r["vid"], c2, r["dur"], audio, opt)
            else:
                c2 = [dict(c) for c in cands]
            dec2 = SV._best_decide(c2, None)
            new_lines = dec2.get("lines") or []
            if refine and new_lines:
                rr = RF.refine_song(r["vid"], new_lines, dec2, r["dur"], audio, F)
                new_lines, note = rr["lines"], rr.get("note", "")
        po = pair_err(old_lines, r) if old_lines else [(i, None) for i in range(len(r["lines"]))]
        pn = pair_err(new_lines, r) if new_lines else [(i, None) for i in range(len(r["lines"]))]
        ho = hn = n = 0
        for (i, eo), (_, en) in zip(po, pn):
            if not r["ok"][i]:
                continue
            T_old.add(r["cats"][i], eo)
            T_new.add(r["cats"][i], en)
            n += 1
            ho += eo is not None and eo <= 0.5
            hn += en is not None and en <= 0.5
        rows.append((r["vid"], r["kind"], dec["action"], (dec.get("cand") or {}).get("provider", "-"),
                     100 * ho / max(1, n), 100 * hn / max(1, n), n, note))
        print(f"{r['vid']} {r['kind']:6s} {dec['action']:7s} {rows[-1][3]:16s} เดิม {rows[-1][4]:5.1f}%  ใหม่ {rows[-1][5]:5.1f}%"
              f"  (n={n}) {note}", flush=True)
    T_old.show("งานเลือกเนื้อ: ระบบเดิม")
    T_new.show("งานเลือกเนื้อ: ระบบใหม่")
    worse = [x for x in rows if x[5] < x[4] - 2]
    if worse:
        print("แย่ลงเกิน 2 จุด:", [(x[0], round(x[4], 1), round(x[5], 1)) for x in worse])
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "best_last.json").write_text(json.dumps(rows, ensure_ascii=False), "utf-8")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    {"gold": cmd_gold, "fa": cmd_fa, "display": cmd_display, "freeze": cmd_freeze, "best": cmd_best,
     "core": cmd_core, "refine-synth": cmd_refine_synth}.get(cmd, lambda: print(__doc__))()



# --- ทดสอบตัวซ่อมเวลาด้วยการ "ทำให้เสียเอง" บนซับที่คนทำ (silver) แล้วดูว่าซ่อมกลับได้แค่ไหน ----------
def _corrupt(lines: list[dict], kind: str, seed: int) -> tuple[list[dict], set]:
    import random
    R = random.Random(seed)
    L = [dict(l) for l in lines]
    n = len(L)
    hit: set = set()
    if kind == "collapse" and n > 12:                 # 3-5 บรรทัดอัดเหลือห่างกัน 0.2 วิ (เหมือนแหล่งไม่มีเวลาจริง)
        k = R.randint(3, 5); a = R.randint(2, n - k - 3)
        base = L[a]["t"]
        for j in range(k):
            L[a + j]["t"] = round(base + 0.2 * j, 2); L[a + j]["d"] = 1.0; hit.add(a + j)
    elif kind == "interp" and n > 14:                 # 6 บรรทัดเกลี่ยเส้นตรงระหว่างหัวท้าย
        k = 6; a = R.randint(2, n - k - 3)
        t0, t1 = L[a - 1]["t"], L[a + k]["t"]
        for j in range(k):
            L[a + j]["t"] = round(t0 + (t1 - t0) * (j + 1) / (k + 1), 2); hit.add(a + j)
    elif kind == "segshift" and n > 16:               # ครึ่งหลังของเพลงเลื่อน +1.8 วิ (เหมือน MV มีบริดจ์ยาวกว่า)
        gaps = [(L[i + 1]["t"] - L[i]["t"], i + 1) for i in range(n // 3, n - 6)]
        g, b = max(gaps)
        for j in range(b, n):
            L[j]["t"] = round(L[j]["t"] + 1.8, 2); hit.add(j)
    for i in range(n):
        nxt = L[i + 1]["t"] if i + 1 < n else L[i]["t"] + 6
        L[i]["d"] = round(max(0.3, min(14.0, nxt - L[i]["t"])), 2)
    return L, hit


def cmd_refine_synth():
    import lyrics_refine as RF
    F = _fa()
    kinds = [arg("--kind")] if arg("--kind") else ["none", "collapse", "interp", "segshift"]
    for kind in kinds:
        tot = {"hit_before": 0, "hit_after": 0, "n_hit": 0, "other_before": 0, "other_after": 0, "n_other": 0, "changed": 0, "songs": 0}
        for r in refsets("silver"):
            audio = r["dir"] / "vocals.m4a"
            if not audio.is_file():
                continue
            seed = sum(map(ord, r["vid"]))
            L, hit = _corrupt(r["lines"], kind, seed) if kind != "none" else ([dict(l) for l in r["lines"]], set())
            if kind != "none" and not hit:
                continue
            try:
                out = RF.refine_song(r["vid"], L, {"timeSrc": "self"}, r["dur"], audio, F)
            except Exception as exc:
                print("fail", r["vid"], exc)
                continue
            tot["songs"] += 1
            tot["changed"] += out["changed"]
            for i, (orig, bad_l, new_l) in enumerate(zip(r["lines"], L, out["lines"])):
                eb = abs(bad_l["t"] - orig["t"]) <= 0.5
                ea = abs(new_l["t"] - orig["t"]) <= 0.5
                if i in hit:
                    tot["n_hit"] += 1; tot["hit_before"] += eb; tot["hit_after"] += ea
                else:
                    tot["n_other"] += 1; tot["other_before"] += eb; tot["other_after"] += ea
            if out["note"] and arg("--v"):
                print("  ", r["vid"], out["note"])
        nh, no = max(1, tot["n_hit"]), max(1, tot["n_other"])
        print(f"{kind:9s} เพลง {tot['songs']:3d} เปลี่ยน {tot['changed']:3d} | บรรทัดที่ทำเสีย {tot['n_hit']:4d}: "
              f"ตรง≤0.5 ก่อนซ่อม {100 * tot['hit_before'] / nh:5.1f}% หลัง {100 * tot['hit_after'] / nh:5.1f}% | "
              f"บรรทัดดี {tot['n_other']:5d}: ก่อน {100 * tot['other_before'] / no:5.1f}% หลัง {100 * tot['other_after'] / no:5.1f}%", flush=True)


if __name__ == "__main__":
    main()
