#!/usr/bin/env python3
"""fa_align.py — จับเวลาเนื้อด้วย forced alignment (wav2vec2 CTC ภาษาไทย) — ใช้ใน Studio เท่านั้น

ต่างจากทาง whisper เดิมตรงที่ "รู้เนื้ออยู่แล้ว" แล้วบังคับหาว่าแต่ละตัวอักษรถูกร้องตอนไหน
แทนที่จะถอดเสียงออกมาเป็นคำก่อนแล้วค่อยเดาจับคู่ (whisper จับเวลาคำไทยคลาดราว 1 วิ)

ขั้นตอน
  1. vocals.m4a -> 16 kHz โมโน -> wav2vec2 -> log-prob ต่อเฟรม (20ms) แคชไว้ใน _fa/<vid>.npz
     (ส่วนที่ช้า ~ครั้งเดียวต่อเพลง) — แก้ข้อความแล้วจับเวลาใหม่ใช้แคช เหลือแค่ขั้น 2
  2. CTC Viterbi บังคับเรียงตัวอักษรของทุกบรรทัดตามลำดับ -> เวลาเริ่ม/จบ + ความมั่นใจต่อบรรทัด
     ระหว่างบรรทัดมีสถานะ "ข้ามได้" (garbage) ไว้กลืนเสียงร้องที่ไม่มีในเนื้อ (ad-lib/ฮุคซ้ำ)
     ไม่งั้นท่อนที่เนื้อขาดจะดึงทุกบรรทัดหลังจากนั้นให้เพี้ยนตาม

ใช้งาน:  fa_align.py <videoId> [--audio PATH]  (stdin = {"texts": [...]})        -> {"lines", "cov", ...}
         fa_align.py <videoId> [--audio PATH]  (stdin = {"sets": [[...], [...]]})  -> {"results": [...]}
         + "words": true    -> แต่ละบรรทัดมี k = [[ตำแหน่งตัวอักษร, วินาที], ...] (โหมดคาราโอเกะ)
         + "anchors": [[t, d], ...]  -> เวลาบรรทัดที่เชื่อได้เป็นหมุด กันท่อนซ้ำไหลผิดรอบ
         words มีรอบที่ 2 ด้วยโมเดลอังกฤษ (MODEL_EN) ให้ตัวละตินในเนื้อได้ k ด้วย — มีเฉพาะเพลงที่มีคำอังกฤษ
         fa_align.py <videoId> --emit [--audio PATH]   คำนวณแคชอย่างเดียว
         server ส่ง --audio มาเสมอ (โฟลเดอร์จริงของเพลงอยู่ที่ server รู้ดีที่สุด)
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(BASE / ".cache" / "hf"))          # ที่เดียวกับ gen_lyrics
os.environ.setdefault("HF_HUB_CACHE", str(BASE / ".cache" / "hf" / "hub"))
MODEL = os.environ.get("KARA_FA_MODEL", "airesearch/wav2vec2-large-xlsr-53-th")
# โมเดลไทยไม่รู้จักตัวละติน -> บรรทัด/คำอังกฤษในเพลงไทยจับเวลาด้วยโมเดลอังกฤษอีกตัว (ไล่สีคาราโอเกะ)
MODEL_EN = os.environ.get("KARA_FA_MODEL_EN", "facebook/wav2vec2-large-960h-lv60-self")   # วัดแล้วดีกว่า xlsr-53-english
CACHE = Path(os.environ.get("KARA_FA_CACHE") or BASE / "lyrics-preview" / "_fa")
DL = Path(os.environ["KARA_SONGS_DIR"]) if os.environ.get("KARA_SONGS_DIR") else BASE / "songs" / "yt"   # override ไว้ทดสอบกับคลังจำลอง
SR = 16000
CHUNK_S, CTX_S = 20.0, 1.0        # หน้าต่างละ 20 วิ + บริบทซ้ายขวาอย่างละ 1 วิ (ตัดทิ้งตอนต่อ)
STAR_PEN = 3.0                    # โทษต่อเฟรมของสถานะ "ข้ามได้" — ต่ำไปจะกลืนเนื้อจริง สูงไปจะไม่ช่วย
MIN_DUR, MAX_DUR = 1.0, 14.0      # ความยาวบรรทัดเท่ากับแหล่งอื่น (lyrics_sources)
ANCHOR_TOL = 1.5                  # หมุดเวลาบรรทัด: อยู่ในช่วง [t-1.5, t+d+1.5] ไม่เสียอะไร
ANCHOR_W = 1.0                    # ออกนอกช่วง: โทษต่อเฟรม = วินาทีที่ห่างออกไป x ค่านี้ (หลักฐานเสียงชัด ๆ ยังชนะได้)


def song_dir(vid: str) -> Path | None:
    for d in DL.iterdir():
        if d.is_dir() and not d.name.startswith(".") and (d.name == vid or d.name.endswith(f"[{vid}]")):
            return d
    return None


def load_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _cache_file(vid: str, model: str = MODEL) -> Path:
    tag = model.rsplit("/", 1)[-1]
    return CACHE / f"{vid}.{tag}.npz"


_MODELS: dict = {}


def model_ready(model: str) -> bool:
    """โมเดลอยู่ในเครื่องแล้วไหม — ไม่มีก็ข้ามไป ไม่โหลดจากเน็ตกลางงาน (1.2 GB)"""
    hub = Path(os.environ.get("HF_HUB_CACHE") or BASE / ".cache" / "hf" / "hub")
    return (hub / ("models--" + model.replace("/", "--"))).is_dir()


def emissions(vid: str, audio_path: Path | None = None,
              model_name: str = MODEL) -> tuple[np.ndarray, list[str], float]:
    """log-prob [T, V], vocab (index -> ตัวอักษร), วินาทีต่อเฟรม — แคชไว้ใช้ซ้ำ (แยกไฟล์ต่อโมเดล)"""
    cf = _cache_file(vid, model_name)
    if cf.is_file():
        z = np.load(cf, allow_pickle=False)
        return z["lp"].astype(np.float32), [str(v) for v in z["vocab"]], float(z["fsec"])
    import torch
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    d = song_dir(vid)
    audio_path = audio_path or (d / "vocals.m4a" if d and (d / "vocals.m4a").is_file() else
                                (d / "audio.m4a" if d else None))
    if not audio_path or not audio_path.is_file():
        raise FileNotFoundError("ไม่มีไฟล์เสียงร้อง")
    wav = load_audio(audio_path)
    if model_name not in _MODELS:                   # โหลดครั้งเดียวต่อโปรเซส (~1.2 GB)
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _MODELS[model_name] = (Wav2Vec2Processor.from_pretrained(model_name),
                               Wav2Vec2ForCTC.from_pretrained(model_name).eval().to(dev), dev)
    proc, model, dev = _MODELS[model_name]
    vocab_map = proc.tokenizer.get_vocab()
    vocab = [""] * len(vocab_map)
    for ch, i in vocab_map.items():
        if i < len(vocab):
            vocab[i] = str(ch)
    step, ctx = int(CHUNK_S * SR), int(CTX_S * SR)
    parts: list[np.ndarray] = []
    fsec = None
    with torch.inference_mode():
        for st in range(0, len(wav), step):
            a, b = max(0, st - ctx), min(len(wav), st + step + ctx)
            seg = wav[a:b]
            if len(seg) < SR // 4:
                break
            x = proc(seg, sampling_rate=SR, return_tensors="pt").input_values.to(dev)
            lp = torch.log_softmax(model(x).logits[0].float(), dim=-1).cpu().numpy()
            fs = len(seg) / SR / lp.shape[0]              # วินาทีต่อเฟรม (~0.02)
            fsec = fsec or fs
            lo = int(round((st - a) / SR / fs))
            hi = lo + int(round(min(step, len(wav) - st) / SR / fs))
            parts.append(lp[lo:hi])
    lp = np.concatenate(parts, axis=0).astype(np.float32)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = cf.with_name(cf.name + ".tmp.npz")
    np.savez_compressed(tmp, lp=lp.astype(np.float16), vocab=np.array(vocab), fsec=np.float32(fsec))
    os.replace(tmp, cf)
    return lp, vocab, float(fsec)


def tokenize(text: str, index: dict[str, int], delim: int | None,
             with_pos: bool = False) -> list[int] | tuple[list[int], list[int]]:
    """ข้อความ -> token id ของตัวอักษรที่โมเดลรู้จัก (อังกฤษ/ตัวเลข/เครื่องหมายข้ามไป)
    ช่องว่างเป็นตัวแบ่งคำ "|" ถ้าโมเดลมี
    with_pos=True คืนตำแหน่งตัวอักษร (code point ในข้อความ) ของแต่ละ token ด้วย — ไว้ทำไล่สีคาราโอเกะ
    ตำแหน่งของตัวแบ่งคำเป็น -1 (ไม่ใช่ตัวที่ร้อง)"""
    out: list[int] = []
    pos: list[int] = []
    for ci, ch in enumerate(unicodedata.normalize("NFC", text)):
        if ch.isspace():
            if delim is not None and out and out[-1] != delim:
                out.append(delim)
                pos.append(-1)
            continue
        if ch in index:
            out.append(index[ch])
            pos.append(ci)
        else:                                   # เช่น "ำ" ในบางโมเดลเก็บเป็น ํ + า
            for c2 in unicodedata.normalize("NFKD", ch):
                if c2 in index:
                    out.append(index[c2])
                    pos.append(ci)
    while out and out[-1] == delim:
        out.pop()
        pos.pop()
    return (out, pos) if with_pos else out


def align(lp: np.ndarray | None, lines_tok: list, blank: int | None,
          anchors: list | None = None, fsec: float = 0.02,
          lps: list | None = None, blanks: list | None = None) -> list[tuple | None]:
    """CTC Viterbi ทั้งเพลงครั้งเดียว — บรรทัดต้องเรียงตามลำดับ ระหว่างบรรทัดมีสถานะ * ที่กลืนอะไรก็ได้
    คืนต่อบรรทัด (เฟรมเริ่ม, เฟรมจบ, ความมั่นใจเฉลี่ย, [(ลำดับ token, เฟรมแรก)], {โมเดล: ความมั่นใจ}) หรือ None
    ถ้าบรรทัดนั้นไม่มีตัวที่โมเดลรู้จัก — เฟรมแรกของแต่ละ token = ตอนที่ตัวอักษรนั้นถูกร้อง

    anchors[i] = [t, d] เวลาบรรทัดที่เชื่อได้อยู่แล้ว (หรือ None) -> ใส่โทษแบบนุ่มให้บรรทัดที่ไปอยู่ไกลจากหมุด
    ไม่มีหมุด ฮุคที่วนซ้ำท้ายเพลงทำให้ทั้งท่อนไหลไปทั้งรอบได้ (THE TOYS - 04:00 ไหลไป 2 ท่อน ~8 วิ)
    ต่างจากจับใหม่ทีละบรรทัดในหน้าต่าง: ลำดับบรรทัดยังบังคับอยู่ บรรทัดติดกันจึงแย่งเสียงเดียวกันไม่ได้

    หลายโมเดล (lps/blanks): token เป็น (โมเดล, id) — ตัวไทยให้คะแนนด้วยโมเดลไทย ตัวละตินด้วยโมเดลอังกฤษ
    ในเส้นทางเดียวกัน คำอังกฤษกลางบรรทัดไทยจึงได้ที่ของตัวเอง ไม่โดนตัวไทยข้าง ๆ ยืดทับ
    (แยกจับทีละภาษาเคยลองแล้ว: โมเดลไทยไม่รู้ว่ามีคำอังกฤษ เลยยืดตัวไทยตัวท้ายคลุมท่อนอังกฤษไปหมด)"""
    if lps is None:
        lps, blanks = [lp], [blank]
        lines_tok = [[(0, t) for t in toks] for toks in lines_tok]
    T = min(x.shape[0] for x in lps)
    # สถานะ: * (ข้ามได้) ต้นเพลง / ต่อบรรทัด: blank, c1, blank, c2, ..., cn, blank, * ...
    kind, tok, mdl, line, tix = [], [], [], [], []   # kind: 0=blank 1=token 2=star, tix = ลำดับ token ในบรรทัด
    def add(k, m, t, li, ti=-1):
        kind.append(k); mdl.append(m); tok.append(t); line.append(li); tix.append(ti)
    add(2, 0, -1, -1)
    for li, toks in enumerate(lines_tok):
        if not toks:
            continue
        add(0, toks[0][0], blanks[toks[0][0]], li)
        for ti, (m, t) in enumerate(toks):
            add(1, m, t, li, ti)
            nm = toks[ti + 1][0] if ti + 1 < len(toks) else m     # blank คั่น = ของโมเดลตัวถัดไป
            add(0, nm, blanks[nm], li)
        add(2, 0, -1, li)
    S = len(kind)
    if S < 3:                               # ไม่มีตัวที่โมเดลรู้จักเลย (เช่นเนื้ออังกฤษล้วน) -> วัดไม่ได้
        return [None] * len(lines_tok)
    kind = np.array(kind); tok = np.array(tok); mdl = np.array(mdl); line = np.array(line)
    star_em = lps[0][:T].max(axis=1) - STAR_PEN     # * = เสียงอะไรก็ได้ แต่เสียค่าปรับทุกเฟรม
    lo = hi = None
    if anchors:
        # ช่วงไม่เสียโทษของแต่ละสถานะ (วินาที) — * ไม่มีโทษ, บรรทัดที่ไม่มีหมุดไม่มีโทษ
        lo = np.full(S, -np.inf); hi = np.full(S, np.inf)
        for st in range(S):
            li = line[st]
            a = anchors[li] if 0 <= li < len(anchors) and kind[st] != 2 else None
            if a:
                lo[st] = float(a[0]) - ANCHOR_TOL
                hi[st] = float(a[0]) + float(a[1] or 0) + ANCHOR_TOL
    em_idx = np.where(kind == 2, 0, tok)
    idx_m = [np.where(mdl == m, em_idx, 0) for m in range(len(lps))]   # id ของโมเดลอื่นอาจเกินขนาด vocab
    # s-2 -> s ได้เมื่อ s เป็น token/star และไม่ใช่ตัวเดียวกับ s-2 (กฎ CTC)
    skip_ok = np.zeros(S, bool)
    skip_ok[2:] = (kind[2:] != 0) & ~((kind[2:] == 1) & (tok[2:] == tok[:-2]) & (mdl[2:] == mdl[:-2]))

    def emit(t):
        if len(lps) == 1:
            e = lps[0][t, em_idx]
        else:
            e = lps[0][t, idx_m[0]]
            for m in range(1, len(lps)):
                e = np.where(mdl == m, lps[m][t, idx_m[m]], e)
        return np.where(kind == 2, star_em[t], e)
    NEG = -1e30
    score = np.full(S, NEG, np.float64)
    e0 = emit(0)
    score[0] = star_em[0]
    score[1] = e0[1]
    if S > 2 and kind[2] == 1:
        score[2] = e0[2]
    back = np.zeros((T, S), np.int8)        # 0=อยู่ที่เดิม 1=มาจาก s-1 2=มาจาก s-2
    for t in range(1, T):
        e = emit(t)
        if lo is not None:
            ts = t * fsec
            e = e - ANCHOR_W * np.maximum(0.0, np.maximum(lo - ts, ts - hi))
        stay = score
        one = np.concatenate(([NEG], score[:-1]))
        two = np.concatenate(([NEG, NEG], score[:-2]))
        two = np.where(skip_ok, two, NEG)
        best = np.maximum(stay, np.maximum(one, two))
        back[t] = np.where(best == stay, 0, np.where(best == one, 1, 2))
        score = best + e
    s = S - 1 if score[S - 1] >= score[S - 2] else S - 2
    path = np.empty(T, np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(back[t, s])            # int() กัน numpy คิดเป็น int8 แล้วล้น
    # เฟรมแรกที่ path เข้าสถานะ token แต่ละตัว (Viterbi บังคับผ่านทุก token ตามลำดับ)
    first: dict[int, int] = {}
    for t in range(T):
        st = int(path[t])
        if kind[st] == 1 and st not in first:
            first[st] = t
    out: list[tuple | None] = []
    for li, toks in enumerate(lines_tok):
        if not toks:
            out.append(None)
            continue
        fr = np.where((line[path] == li) & (kind[path] == 1))[0]
        if not len(fr):
            out.append(None)
            continue
        sp = path[fr]
        pr = np.empty(len(fr))
        for m in range(len(lps)):
            sel = mdl[sp] == m
            if sel.any():
                pr[sel] = np.exp(lps[m][fr[sel], tok[sp[sel]]])
        by_m = {m: float(pr[mdl[sp] == m].mean()) for m in range(len(lps)) if (mdl[sp] == m).any()}
        tf = sorted((int(tix[st]), f) for st, f in first.items() if line[st] == li)
        out.append((int(fr[0]), int(fr[-1]), float(pr.mean()), tf, by_m))
    return out


def cached(vid: str, en: bool = False) -> bool:
    return _cache_file(vid, MODEL_EN if en else MODEL).is_file()


_LATIN = re.compile(r"[A-Za-z]")


def has_latin(texts: list[str]) -> bool:
    return any(len(_LATIN.findall(x or "")) >= 2 for x in texts)


def tokenize_joint(text: str, idx0: dict[str, int], d0: int | None,
                   idx1: dict[str, int], d1: int | None) -> tuple[list[tuple[int, int]], list[int]]:
    """ทั้งบรรทัด -> [(โมเดล, token)] + ตำแหน่ง code point: ตัวไทย/ตัวที่โมเดลไทยรู้จัก = 0, ตัวละติน = 1
    ช่องว่าง = ตัวแบ่งคำ "|" ของโมเดลตัวก่อนหน้า (ตำแหน่ง -1)"""
    out: list[tuple[int, int]] = []
    pos: list[int] = []
    dl = {0: d0, 1: d1}
    for ci, ch in enumerate(unicodedata.normalize("NFC", text)):
        if ch.isspace():
            if out and out[-1][1] != dl[out[-1][0]] and dl[out[-1][0]] is not None:
                out.append((out[-1][0], dl[out[-1][0]]))
                pos.append(-1)
            continue
        latin = "a" <= ch.lower() <= "z" or ch == "'"
        if latin:
            c = ch if ch in idx1 else ch.lower() if ch.lower() in idx1 else ch.upper()
            if c not in idx1:
                continue
            if ch == "'" and (not out or pos[-1] < 0 or out[-1][0] != 1):
                continue                        # ' ต้นคำ (เครื่องหมายคำพูด) ไม่ได้ออกเสียง
            out.append((1, idx1[c]))
            pos.append(ci)
        elif ch in idx0:
            out.append((0, idx0[ch]))
            pos.append(ci)
        else:                                   # เช่น "ำ" ในบางโมเดลเก็บเป็น ํ + า
            for c2 in unicodedata.normalize("NFKD", ch):
                if c2 in idx0:
                    out.append((0, idx0[c2]))
                    pos.append(ci)
    while out and pos[-1] < 0:
        out.pop()
        pos.pop()
    return out, pos


def _k_from(r, pos: list[int], fsec: float, f_off: int = 0) -> list[list[float]]:
    """ผล align ของบรรทัด -> [[ตำแหน่งตัวอักษร, วินาที], ...] (ข้ามตัวแบ่งคำ, ตัวที่แตกหลาย token เอาเวลาแรก)"""
    k: list[list[float]] = []
    for ti, f in r[3]:
        p = pos[ti] if ti < len(pos) else -1
        if p < 0:
            continue
        tt = round((f + f_off) * fsec, 2)
        if k and p == k[-1][0]:
            continue
        if k and tt < k[-1][1]:
            tt = k[-1][1]
        k.append([p, tt])
    return k


def time_lines(vid: str, texts: list[str], duration: float = 0.0,
               audio_path: Path | None = None, words: bool = False, anchors: list | None = None) -> dict:
    """words=True: แต่ละบรรทัดได้ k = [[ตำแหน่งตัวอักษร, วินาที], ...] ตอนที่ตัวนั้นถูกร้อง (ไล่สีคาราโอเกะ)
    anchors: เวลาบรรทัดที่เชื่อถือได้อยู่แล้ว [[t, d], ...] -> บรรทัดที่ผลไหลไปไกลถูกจับใหม่รอบเวลานั้น"""
    t0 = time.time()
    lp, vocab, fsec = emissions(vid, audio_path)
    index = {c: i for i, c in enumerate(vocab) if c}
    # blank ของ CTC = โทเคน pad (ชื่อแล้วแต่โมเดล: [PAD] / <pad>) — เฟรมส่วนใหญ่ของเพลงเป็นตัวนี้
    blank = next((index[k] for k in ("[PAD]", "<pad>") if k in index), 0)
    delim = index.get("|")
    tp = [tokenize(x, index, delim, with_pos=True) for x in texts]
    # คำอังกฤษ (โหมดคาราโอเกะ): จับพร้อมกันกับตัวไทยในเส้นทางเดียว ด้วยโมเดลอังกฤษอีกตัว
    # ไม่มีโมเดลในเครื่อง/พัง = จับแค่ตัวไทยเหมือนเดิม (จอเกลี่ยเวลาตัวอังกฤษระหว่างตัวไทยเอง)
    en_note, joint = "", False
    if has_latin(texts):                        # ทุกโหมด (ให้คะแนน/ความคลาด/จับเวลา/ไล่สี) ไม่ใช่แค่ words
        if not model_ready(MODEL_EN):
            en_note = "no-model"
        else:
            try:
                lpe, vocab_e, _ = emissions(vid, audio_path, MODEL_EN)
                idx_e = {c: i for i, c in enumerate(vocab_e) if c}
                blank_e = next((idx_e[k] for k in ("<pad>", "[PAD]") if k in idx_e), 0)
                tpj = [tokenize_joint(x, index, delim, idx_e, idx_e.get("|")) for x in texts]
                res = align(None, [a for a, _ in tpj], None, anchors, fsec, lps=[lp, lpe], blanks=[blank, blank_e])
                tp, joint = tpj, True
            except Exception as exc:
                en_note = f"{type(exc).__name__}: {exc}"[:200]
    if not joint:
        res = align(lp, [a for a, _ in tp], blank, anchors, fsec)
    dur = duration or lp.shape[0] * fsec
    starts: list[float | None] = [None if r is None else r[0] * fsec for r in res]
    # บรรทัดที่ไม่มีตัวที่โมเดลรู้จัก (อังกฤษล้วน) -> แทรกเวลาจากบรรทัดข้าง ๆ
    known = [i for i, s in enumerate(starts) if s is not None]
    for i, s in enumerate(starts):
        if s is None:
            p = max((k for k in known if k < i), default=None)
            n = min((k for k in known if k > i), default=None)
            if p is not None and n is not None:
                starts[i] = starts[p] + (starts[n] - starts[p]) * (i - p) / (n - p)
            elif p is not None:
                starts[i] = starts[p] + 2.0 * (i - p)
            elif n is not None:
                starts[i] = max(0.0, starts[n] - 2.0 * (n - i))
            else:
                starts[i] = 0.0
    lines = []
    for i, x in enumerate(texts):
        t = round(max(0.0, starts[i]), 2)
        nxt = starts[i + 1] if i + 1 < len(texts) else (dur if dur > t else t + 6.0)
        r = res[i]
        sung = (r[1] - r[0] + 1) * fsec + 0.3 if r else nxt - t   # ยาวเท่าที่ร้องจริง + หางนิดหน่อย
        d = max(MIN_DUR, min(MAX_DUR, min(nxt - t, max(sung, MIN_DUR))))
        ln = {"t": t, "d": round(d, 2), "x": x, "conf": round(r[2], 3) if r else None}
        if r and joint and 1 in r[4]:
            ln["en"] = round(r[4][1], 3)            # ความมั่นใจเฉพาะตัวละติน
        if words and r:
            k = _k_from(r, tp[i][1], fsec)
            if k:
                ln["k"] = k
        lines.append(ln)
    cov = 100.0 * sum(1 for r in res if r) / max(1, len(res))
    out = {"lines": lines, "by": "fa", "cov": round(cov, 1), "ok": cov >= 60,
           "sec": round(time.time() - t0, 1)}
    if has_latin(texts):
        out["en"] = {"lines": sum(1 for l in lines if "en" in l), "model": MODEL_EN,
                     **({"why": en_note} if en_note else {})}
    return out


def main() -> None:
    argv = sys.argv[1:]
    audio = None
    if "--audio" in argv:
        k = argv.index("--audio")
        audio = Path(argv[k + 1])
        del argv[k:k + 2]
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    vid = args[0]
    if "--emit" in argv:
        t0 = time.time()
        lp, _, fsec = emissions(vid, audio)
        print(json.dumps({"frames": lp.shape[0], "fsec": fsec, "sec": round(time.time() - t0, 1)}))
        return
    req = json.loads(sys.stdin.read() or "{}")
    dur = float(req.get("duration") or 0)
    if "sets" in req:                               # หลายชุดในครั้งเดียว (ให้คะแนนผู้สมัครในห้องหาเนื้อ)
        out = [time_lines(vid, t, dur, audio) if t else None for t in req["sets"]]
        print(json.dumps({"results": out}, ensure_ascii=False))
        return
    print(json.dumps(time_lines(vid, req.get("texts") or [], dur, audio, words=bool(req.get("words")),
                                anchors=req.get("anchors")), ensure_ascii=False))


if __name__ == "__main__":
    main()
