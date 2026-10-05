#!/usr/bin/env python3
"""kmap.py — ตัวช่วยแผนที่โค้ด PU KARAOKE (คู่กับ MAP.md ในโฟลเดอร์เดียวกัน)

  find <คำ...> [-n N]     หัวข้อใน MAP.md ที่ตรงที่สุด + ไฟล์:บรรทัด "ปัจจุบัน" ของทุก anchor
  topics                  รายชื่อหัวข้อทั้งหมด (ใช้ตอน find ไม่เจอ)
  outline <ไฟล์> [คำกรอง]  หัว section / ฟังก์ชัน / routes พร้อมเลขบรรทัด (คำนวณสด ไม่มีวันเก่า)
  check                   anchor หาย/ซ้ำ + ความครอบคลุม (routes, section ของ html, ไฟล์ใน scripts)
  status                  worktree นี้เก่ากว่าโฟลเดอร์หลักไหม + anchor หายกี่ตัว

anchor = ข้อความที่อยู่ในบรรทัดเดียวของไฟล์ (เทียบแบบ substring) — ใช้แทนเลขบรรทัดที่เปลี่ยนทุกครั้งที่แก้
ไฟล์ในแผนที่อ้างจากรากของ git repo ที่รันอยู่ (worktree ก็ได้) — รองรับ python 3.9+
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP = HERE / "MAP.md"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def git(*args, cwd=None):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def project_root():
    rc, top = git("rev-parse", "--show-toplevel")
    if rc == 0 and top and (Path(top) / "server.py").is_file():
        return Path(top)
    return HERE.parents[2]                       # .claude/skills/kara-edit -> รากโปรเจกต์


ROOT = project_root()
_cache = {}


def lines_of(rel):
    if rel not in _cache:
        p = ROOT / rel
        try:
            _cache[rel] = p.read_text("utf-8", errors="replace").splitlines()
        except Exception:
            _cache[rel] = None
    return _cache[rel]


def resolve(rel, anchor):
    """เลขบรรทัด (เริ่ม 1) ทุกบรรทัดที่มี anchor · None = ไม่มีไฟล์"""
    ls = lines_of(rel)
    if ls is None:
        return None
    return [i + 1 for i, s in enumerate(ls) if anchor in s]


# ---------- อ่าน MAP.md ----------
SPAN = re.compile(r"`([^`]*)`")


def parse_map():
    topics, group, cur = [], "", None
    for raw in MAP.read_text("utf-8").splitlines():
        s = raw.rstrip()
        if s.startswith("## "):
            group, cur = s[3:].strip(), None
        elif s.startswith("### "):
            cur = {"group": group, "title": s[4:].strip(), "kw": "", "refs": [], "notes": [], "info": []}
            topics.append(cur)
        elif cur is None:
            continue
        elif s.startswith(("คำค้น:", "keywords:")):
            cur["kw"] = s.split(":", 1)[1].strip()
        elif s.startswith("- `"):
            spans = SPAN.findall(s)
            tail = SPAN.sub("", s)[1:].strip().lstrip("—-– ").strip()
            cur["refs"].append({"path": spans[0], "anchors": spans[1:], "note": tail})
        elif s.startswith("! "):
            cur["notes"].append(s[2:].strip())
        elif s.strip():
            cur["info"].append(s.strip())
    return topics


def fmt_ref(ref, width=62):
    out, missing = [], 0
    if not ref["anchors"]:
        ok = lines_of(ref["path"]) is not None
        missing += 0 if ok else 1
        out.append(f"  {ref['path']}{'' if ok else '  ✗ ไม่มีไฟล์นี้'}" + (f"  — {ref['note']}" if ref["note"] else ""))
        return out, missing
    for a in ref["anchors"]:
        ln = resolve(ref["path"], a)
        if not ln:
            missing += 1
            where = f"{ref['path']}:?"
            flag = "  ✗ ไม่เจอ" if ln is not None else "  ✗ ไม่มีไฟล์นี้"
        else:
            where = f"{ref['path']}:{','.join(map(str, ln[:4]))}{'…' if len(ln) > 4 else ''}"
            flag = ""
        out.append(f"  {where:<34} {a.strip()[:width]}{flag}")
    if ref["note"]:
        out.append(f"  {'':<34} └ {ref['note']}")
    return out, missing


def cmd_find(args):
    n = 3
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    terms = [t.casefold() for a in args for t in a.split()]     # "ป้าย ตรวจเวลา" ก้อนเดียว = 2 คำ
    if not terms:
        print("ใช้: kmap.py find <คำ...>   เช่น  find ช่องค้นหา รีโมท")
        return 2
    scored = []
    for k, t in enumerate(parse_map()):
        title, kw = t["title"].casefold(), t["kw"].casefold()
        kws = {k.strip() for k in kw.split(",")}
        rest = " ".join([t["group"]] + t["notes"] + t["info"]
                        + [r["path"] + " " + " ".join(r["anchors"]) + " " + r["note"] for r in t["refs"]]).casefold()
        # ตรงทั้งคำในคำค้น (+2) ชนะแค่เป็นส่วนหนึ่งของคำอื่น เช่น "คิว" ตรงกว่า "ปุ่มคิว"
        sc = sum(3 * (x in title) + 2 * (x in kw) + 2 * (x in kws) + (x in rest) for x in terms)
        hits = sum((x in title) or (x in kw) or (x in rest) for x in terms)
        if sc:
            scored.append((-hits, -sc, k, t))
    if not scored:
        print("ไม่เจอหัวข้อที่ตรง — ลองคำอื่น (ไทย/อังกฤษ), `kmap.py topics`, หรือ `kmap.py outline <ไฟล์> <คำ>`")
        return 1
    scored.sort(key=lambda x: x[:3])
    miss_total = ref_total = 0
    for _, _, _, t in scored[:n]:
        print(f"### {t['title']}   [{t['group']}]")
        for line in t["info"]:
            print(f"  {line}")
        for r in t["refs"]:
            out, miss = fmt_ref(r)
            miss_total += miss
            ref_total += max(1, len(r["anchors"]))
            print("\n".join(out))
        for x in t["notes"]:
            print(f"  ! {x}")
        print()
    more = len(scored) - n
    if more > 0:
        print(f"(+ อีก {more} หัวข้อที่ตรงบางคำ — ใช้ -n {n + more} เพื่อดูทั้งหมด)")
    if ref_total and miss_total / ref_total >= 0.3:
        print("⚠ anchor หายหลายจุด — worktree อาจเก่ากว่าโค้ดจริง: รัน `kmap.py status`")
    return 0


def cmd_topics(_args):
    group = None
    for t in parse_map():
        if t["group"] != group:
            group = t["group"]
            print(f"\n## {group}")
        print(f"- {t['title']}" + (f"  ({t['kw'][:70]})" if t["kw"] else ""))
    return 0


# ---------- outline ----------
OUT_RULES = {
    "py": [r"^# ?(=====|-----).*", r"^@app\.\w+\(.*", r"^(async )?def \w+.*", r"^class \w+.*"],
    "js": [r"^\s*// ?=====.*", r"^\s*/\* ?-{3,}.*", r"^\s*// </?lyrcore>.*", r"^\s*(async )?function [\w$]+.*",
           r"^\s*(const|let) [\w$]+ ?= ?(async )?(\([^)]*\)|[\w$]+) ?=>.*", r"^\s*<(section|template|nav|header|main)\b[^>]*>.*"],
    "md": [r"^#{1,4} .*"],
    "sh": [r"^\s*[\w-]+\s*\(\)\s*\{.*", r"^# .*"],
    "swift": [r"^\s*(func|struct|class) .*"],
}


def cmd_outline(args):
    if not args:
        print("ใช้: kmap.py outline <ไฟล์> [คำกรอง]")
        return 2
    rel, flt = args[0], " ".join(args[1:]).casefold()
    ls = lines_of(rel)
    if ls is None:
        print(f"ไม่มีไฟล์ {rel} (อ้างจาก {ROOT})")
        return 1
    ext = rel.rsplit(".", 1)[-1]
    kind = {"html": "js", "js": "js", "py": "py", "md": "md", "sh": "sh", "command": "sh", "swift": "swift"}.get(ext, "py")
    pats = [re.compile(p) for p in OUT_RULES[kind]]
    n = 0
    for i, s in enumerate(ls):
        if any(p.match(s) for p in pats) and (not flt or flt in s.casefold()):
            print(f"{i + 1:>5}: {s.strip()[:130]}")
            n += 1
    print(f"-- {n} รายการ · {len(ls)} บรรทัด · {rel}")
    return 0


# ---------- check ----------
def cmd_check(_args):
    topics = parse_map()
    errors, warns, hit = [], [], {}
    for t in topics:
        for r in t["refs"]:
            if lines_of(r["path"]) is None:
                errors.append(f"ไม่มีไฟล์ {r['path']}  [{t['title']}]")
                continue
            hit.setdefault(r["path"], set()).add(0)
            for a in r["anchors"]:
                ln = resolve(r["path"], a)
                if not ln:
                    errors.append(f"anchor หาย  {r['path']}  `{a}`  [{t['title']}]")
                elif len(ln) > 1:
                    warns.append(f"anchor ซ้ำ {len(ln)} ที่ {r['path']}:{','.join(map(str, ln[:5]))}  `{a}`  [{t['title']}]")
                hit[r["path"]].update(ln or [])
    text = MAP.read_text("utf-8")

    def covered(rel, lo, hi):
        return any(lo <= x < hi for x in hit.get(rel, ()))

    # routes ใน server.py: ต้องมี anchor ชี้ที่ decorator ถึง def (ห่างไม่เกิน 3 บรรทัด)
    srv = lines_of("server.py") or []
    routes = [i + 1 for i, s in enumerate(srv) if re.match(r"^@app\.(get|post|put|delete|patch|websocket)\(", s)]
    miss_routes = [f"server.py:{n}  {srv[n - 1].strip()}" for n in routes if not covered("server.py", n, n + 4)]
    # section ของหน้า html: ทุก section ต้องมี anchor อย่างน้อย 1 ตัวอยู่ในช่วงของมัน
    miss_sec, n_sec = [], 0
    for page in sorted((ROOT / "static").glob("*.html")):
        rel = f"static/{page.name}"
        ls = lines_of(rel) or []
        for pat in (r"^\s*// ?=====", r"^\s*/\* ?-{3,}"):
            heads = [i + 1 for i, s in enumerate(ls) if re.match(pat, s)]
            for k, h in enumerate(heads):
                n_sec += 1
                end = heads[k + 1] if k + 1 < len(heads) else len(ls) + 1
                if not covered(rel, h, end):
                    miss_sec.append(f"{rel}:{h}  {ls[h - 1].strip()[:80]}")
    # ไฟล์โค้ดทุกไฟล์ต้องถูกพูดถึงในแผนที่
    files = [p for p in sorted(ROOT.glob("scripts/*")) if p.suffix in (".py", ".js", ".swift")]
    files += [p for p in sorted(ROOT.glob("*")) if p.suffix in (".py", ".sh", ".command") and p.is_file()]
    miss_files = [str(p.relative_to(ROOT)) for p in files if str(p.relative_to(ROOT)) not in text]

    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"routes ใน server.py มีหัวข้อ {len(routes) - len(miss_routes)}/{len(routes)}")
    for m in miss_routes:
        print("  ยังไม่มีในแผนที่:", m)
    print(f"section ของหน้า html มีหัวข้อ {n_sec - len(miss_sec)}/{n_sec}")
    for m in miss_sec:
        print("  ยังไม่มีในแผนที่:", m)
    print(f"ไฟล์โค้ดที่แผนที่พูดถึง {len(files) - len(miss_files)}/{len(files)}")
    for m in miss_files:
        print("  ยังไม่มีในแผนที่:", m)
    print(f"{len(topics)} หัวข้อ · ERROR {len(errors)} · WARN {len(warns)}")
    return 1 if errors else 0


# ---------- status ----------
def cmd_status(_args):
    rc, porcelain = git("worktree", "list", "--porcelain")
    main_path = main_head = main_branch = None
    if rc == 0 and porcelain:
        first = porcelain.split("\n\n")[0].splitlines()
        for s in first:
            if s.startswith("worktree "):
                main_path = s[9:]
            elif s.startswith("HEAD "):
                main_head = s[5:]
            elif s.startswith("branch "):
                main_branch = s[7:].replace("refs/heads/", "")
    _, head = git("rev-parse", "HEAD")
    _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    print(f"ที่นี่: {ROOT}  ({branch} @ {head[:7]})")
    if not main_head:
        print("หาโฟลเดอร์หลักไม่เจอ (ไม่ใช่ git?)")
    elif Path(main_path).resolve() == ROOT.resolve():
        print(f"นี่คือโฟลเดอร์หลัก ({main_branch}) — เซิร์ฟเวอร์จริงรันจากที่นี่")
    elif git("merge-base", "--is-ancestor", main_head, "HEAD")[0] == 0:
        print(f"✓ มีโค้ดล่าสุดของโฟลเดอร์หลักแล้ว ({main_branch} @ {main_head[:7]})")
    elif git("merge-base", "--is-ancestor", "HEAD", main_head)[0] == 0:
        print(f"⚠ worktree นี้เก่ากว่าโฟลเดอร์หลัก ({main_branch} @ {main_head[:7]}) — รันก่อนแก้อะไร:")
        print(f"    git merge --ff-only {main_branch}")
    else:
        print(f"⚠ worktree นี้แยกทางกับ {main_branch} @ {main_head[:7]} — ถามผู้ใช้ก่อน merge")
    total = miss = 0
    for t in parse_map():
        for r in t["refs"]:
            for a in r["anchors"]:
                total += 1
                miss += not resolve(r["path"], a)
    print(f"anchor ในแผนที่ {total} ตัว · หาไม่เจอ {miss}" + ("  (ถ้าเพิ่ง merge แล้วยังหาย = แผนที่ต้องอัปเดต)" if miss else ""))
    return 0


CMDS = {"find": cmd_find, "topics": cmd_topics, "outline": cmd_outline, "check": cmd_check, "status": cmd_status}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(CMDS[sys.argv[1]](sys.argv[2:]) or 0)
