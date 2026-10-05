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
         fa_align.py --serve   ตัวโหลดโมเดลค้าง (server เปิดไว้ใช้ซ้ำ): stdin/stdout ทีละบรรทัด JSON
                               {"id","vid","audio","req"} -> {"id","ok","out"|"error"} · {"id","op":"load"} = โหลดโมเดลไว้ก่อน
                               ผลเหมือนเรียกทีละครั้งทุกอย่าง แค่ไม่ต้องโหลดโมเดลใหม่ (~8-10 วิ/โมเดล) ทุกเพลง
         server ส่ง --audio มาเสมอ (โฟลเดอร์จริงของเพลงอยู่ที่ server รู้ดีที่สุด)
         + "opt": {...} (ไม่ส่ง = พฤติกรรมเดิมทุกอย่าง)
             "paren": true      ส่วนในวงเล็บ (คอรัส/แอดลิบ) "ข้ามได้" — ได้ยินก็จับ ไม่ได้ยินก็ข้าม ไม่ดันบรรทัดถัดไปให้ช้า
             "optional": [i]    บรรทัดที่ข้ามได้ทั้งบรรทัด (เสียงที่ 2 / คอรัสทั้งบรรทัด)
             "window": [t0,t1]  จับเฉพาะช่วงเวลานี้ (ซ่อมเฉพาะท่อน)
             "stem": "side"     ใช้เสียงด้านข้างของสเตอริโอ (L-R) — เสียงประสาน/คอรัสที่แพนออกข้าง เสียงหลักกลางหายไป
             "voices": [v...]   เสียงของแต่ละบรรทัด (ไม่มี/1 = เสียงหลัก, 2/3/"bg" = อีกคน) — จับเวลาแยกเส้นทาง
                                ต่อเสียง บรรทัดของสองคนที่ร้องพร้อมกันจึงไม่ถูกบังคับให้เรียงต่อกัน
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
SPAN_PEN = float(os.environ.get("KARA_FA_SPAN_PEN") or 3.0)   # ข้ามส่วนในวงเล็บทั้งก้อน เสียครั้งเดียวเท่านี้
LINE_PEN = float(os.environ.get("KARA_FA_LINE_PEN") or 8.0)   # ข้ามทั้งบรรทัด (บรรทัดที่บอกว่าข้ามได้เท่านั้น)
_PAREN = re.compile(r"[(（][^)）]*[)）]")


def song_dir(vid: str) -> Path | None:
    for d in DL.iterdir():
        if d.is_dir() and not d.name.startswith(".") and (d.name == vid or d.name.endswith(f"[{vid}]")):
            return d
    return None


def load_audio(path: Path, side: bool = False) -> np.ndarray:
    # side: ช่องข้าง (L−R)/2 — ไฟล์โมโนจะได้ความเงียบ (ผู้เรียกควรเช็กเองว่าเป็นสเตอริโอ)
    af = ["-af", "pan=mono|c0=0.5*c0-0.5*c1"] if side else ["-ac", "1"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), *af, "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _cache_file(vid: str, model: str = MODEL, stem: str = "") -> Path:
    tag = model.rsplit("/", 1)[-1]
    return CACHE / (f"{vid}.{tag}.{stem}.npz" if stem else f"{vid}.{tag}.npz")


def _sig(audio: Path | None) -> str:
    """ลายเซ็นไฟล์เสียงที่แคชผูกอยู่ — แยกเสียงใหม่/โหลดใหม่ = แคชเก่าใช้ไม่ได้"""
    try:
        st = audio.stat()
        return f"{audio.name}:{st.st_size}:{st.st_mtime_ns}"
    except (OSError, AttributeError):
        return ""


_OK_MEMO: dict = {}


def _cache_ok(cf: Path, audio: Path | None, z=None) -> bool:
    """แคชนี้ใช้กับไฟล์เสียงนี้ได้ไหม — ของเดิมผูกแค่ vid ทำให้ FA ที่เคยรันบนเสียงรวม (ก่อนแยกเสียงเสร็จ)
    หรือบนเสียงร้องชุดเก่า (ก่อนแยกเสียงใหม่) ถูกใช้ต่อไปเรื่อย ๆ
    แคชรุ่นใหม่มี src = ลายเซ็นไฟล์ / แคชรุ่นเก่าไม่มี -> ใช้ได้เมื่อสร้างหลังไฟล์เสียง (เผื่อ 60 วิ)"""
    if not cf.is_file():
        return False
    if audio is None or not audio.is_file():
        return True                                  # ไม่รู้ว่าเสียงไหน (เรียกแบบเก่า) -> เชื่อแคชเหมือนเดิม
    key = (str(cf), cf.stat().st_mtime_ns, _sig(audio))   # server ถามซ้ำบ่อย -> จำผลตามเวลาแก้ไขของทั้งสองไฟล์
    if key in _OK_MEMO:
        return _OK_MEMO[key]
    try:
        if z is None:
            with np.load(cf, allow_pickle=False) as zz:
                src = str(zz["src"]) if "src" in zz.files else ""
        else:
            src = str(z["src"]) if "src" in z.files else ""
    except Exception:
        return False
    ok = (src == key[2]) if src else (cf.stat().st_mtime + 60 >= audio.stat().st_mtime)
    if len(_OK_MEMO) > 4000:
        _OK_MEMO.clear()
    _OK_MEMO[key] = ok
    return ok


_MODELS: dict = {}


def _load_model(model_name: str):
    """โหลดครั้งเดียวต่อโปรเซส (~1.2 GB, วัดแล้ว 8-10 วิ) — โหมด --serve จึงจ่ายครั้งเดียวต่อการเปิดตัว"""
    if model_name not in _MODELS:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _MODELS[model_name] = (Wav2Vec2Processor.from_pretrained(model_name),
                               Wav2Vec2ForCTC.from_pretrained(model_name).eval().to(dev), dev)
    return _MODELS[model_name]


def model_ready(model: str) -> bool:
    """โมเดลอยู่ในเครื่องแล้วไหม — ไม่มีก็ข้ามไป ไม่โหลดจากเน็ตกลางงาน (1.2 GB)"""
    hub = Path(os.environ.get("HF_HUB_CACHE") or BASE / ".cache" / "hf" / "hub")
    return (hub / ("models--" + model.replace("/", "--"))).is_dir()


def default_audio(vid: str) -> Path | None:
    d = song_dir(vid)
    if not d:
        return None
    return d / "vocals.m4a" if (d / "vocals.m4a").is_file() else (d / "audio.m4a" if (d / "audio.m4a").is_file() else None)


def emissions(vid: str, audio_path: Path | None = None,
              model_name: str = MODEL, stem: str = "") -> tuple[np.ndarray, list[str], float]:
    """log-prob [T, V], vocab (index -> ตัวอักษร), วินาทีต่อเฟรม — แคชไว้ใช้ซ้ำ (แยกไฟล์ต่อโมเดล/สเต็ม)
    stem="side": ใช้ช่องข้าง (L−R)/2 ของสเตอริโอ — เสียงที่อยู่กลาง (ร้องนำ) หักล้างกันหาย เหลือคอรัส/เสียงประสานที่แพนออกข้าง"""
    audio_path = audio_path or default_audio(vid)
    cf = _cache_file(vid, model_name, stem)
    if cf.is_file():
        z = np.load(cf, allow_pickle=False)
        if _cache_ok(cf, audio_path, z):
            return z["lp"].astype(np.float32), [str(v) for v in z["vocab"]], float(z["fsec"])
    if os.environ.get("KARA_FA_NO_COMPUTE"):          # ชุดวัดผล: ห้ามแย่ง GPU/เขียนแคชใหม่ระหว่างที่คนใช้เครื่องอยู่
        raise RuntimeError(f"ไม่มีแคช FA ({cf.name}) และห้ามคำนวณใหม่")
    import torch
    if not audio_path or not audio_path.is_file():
        raise FileNotFoundError("ไม่มีไฟล์เสียงร้อง")
    wav = load_audio(audio_path, side=(stem == "side"))
    proc, model, dev = _load_model(model_name)
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
    np.savez_compressed(tmp, lp=lp.astype(np.float16), vocab=np.array(vocab), fsec=np.float32(fsec),
                        src=np.array(_sig(audio_path)))
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
          lps: list | None = None, blanks: list | None = None,
          spans: list | None = None) -> list[tuple | None]:
    """CTC Viterbi ทั้งเพลงครั้งเดียว — บรรทัดต้องเรียงตามลำดับ ระหว่างบรรทัดมีสถานะ * ที่กลืนอะไรก็ได้
    คืนต่อบรรทัด (เฟรมเริ่ม, เฟรมจบ, ความมั่นใจเฉลี่ย, [(ลำดับ token, เฟรมแรก)], {โมเดล: ความมั่นใจ}, token ที่ถูกข้าม)
    หรือ None ถ้าบรรทัดนั้นไม่มีตัวที่โมเดลรู้จัก / "skip" ถ้าทั้งบรรทัดถูกข้าม (ข้ามได้เฉพาะบรรทัดที่บอกไว้)
    เฟรมแรกของแต่ละ token = ตอนที่ตัวอักษรนั้นถูกร้อง

    anchors[i] = [t, d] เวลาบรรทัดที่เชื่อได้อยู่แล้ว (หรือ None) -> ใส่โทษแบบนุ่มให้บรรทัดที่ไปอยู่ไกลจากหมุด
    ไม่มีหมุด ฮุคที่วนซ้ำท้ายเพลงทำให้ทั้งท่อนไหลไปทั้งรอบได้ (THE TOYS - 04:00 ไหลไป 2 ท่อน ~8 วิ)
    ต่างจากจับใหม่ทีละบรรทัดในหน้าต่าง: ลำดับบรรทัดยังบังคับอยู่ บรรทัดติดกันจึงแย่งเสียงเดียวกันไม่ได้

    หลายโมเดล (lps/blanks): token เป็น (โมเดล, id) — ตัวไทยให้คะแนนด้วยโมเดลไทย ตัวละตินด้วยโมเดลอังกฤษ
    ในเส้นทางเดียวกัน คำอังกฤษกลางบรรทัดไทยจึงได้ที่ของตัวเอง ไม่โดนตัวไทยข้าง ๆ ยืดทับ
    (แยกจับทีละภาษาเคยลองแล้ว: โมเดลไทยไม่รู้ว่ามีคำอังกฤษ เลยยืดตัวไทยตัวท้ายคลุมท่อนอังกฤษไปหมด)

    spans[i] = [(token แรก, token สุดท้าย, โทษ), ...] ช่วง token ของบรรทัด i ที่ "ข้ามได้" (วงเล็บ = คอรัสตามหลัง)
    เส้นทางกระโดดจาก blank ก่อนช่วงไป blank หลังช่วงได้ เสียโทษครั้งเดียว — คอรัสที่ได้ยินชัดยังถูกจับ
    ที่ไม่ได้ยิน (เบา/โดนเสียงหลักกลบ) ถูกข้าม แทนที่จะลากเวลาบรรทัดถัดไปให้ช้า"""
    if lps is None:
        lps, blanks = [lp], [blank]
        lines_tok = [[(0, t) for t in toks] for toks in lines_tok]
    T = min(x.shape[0] for x in lps)
    # สถานะ: * (ข้ามได้) ต้นเพลง / ต่อบรรทัด: blank, c1, blank, c2, ..., cn, blank, * ...
    kind, tok, mdl, line, tix = [], [], [], [], []   # kind: 0=blank 1=token 2=star, tix = ลำดับ token ในบรรทัด
    base: dict[int, int] = {}                         # บรรทัด -> สถานะ blank ตัวแรกของบรรทัด
    def add(k, m, t, li, ti=-1):
        kind.append(k); mdl.append(m); tok.append(t); line.append(li); tix.append(ti)
    add(2, 0, -1, -1)
    for li, toks in enumerate(lines_tok):
        if not toks:
            continue
        base[li] = len(kind)
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
    # ทางลัดข้ามช่วง: jsrc[ปลายทาง] = ต้นทาง (blank ก่อนช่วง -> blank หลังช่วง)
    jsrc = np.full(S, -1, np.int64)
    jpen = np.zeros(S)
    for li, sp in enumerate(spans or []):
        if li not in base or not sp:
            continue
        n = len(lines_tok[li])
        for ta, tb, pen in sp:
            ta, tb = max(0, int(ta)), min(n - 1, int(tb))
            if ta > tb:
                continue
            src, dst = base[li] + 2 * ta, base[li] + 2 * tb + 2
            if jsrc[dst] < 0 or pen < jpen[dst]:
                jsrc[dst], jpen[dst] = src, float(pen)
    has_j = bool((jsrc >= 0).any())
    jsel = np.where(jsrc >= 0)[0]
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
    back = np.zeros((T, S), np.int8)        # 0=อยู่ที่เดิม 1=มาจาก s-1 2=มาจาก s-2 3=ทางลัดข้ามช่วง
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
        bk = np.where(best == stay, 0, np.where(best == one, 1, 2)).astype(np.int8)
        if has_j:
            jv = score[jsrc[jsel]] - jpen[jsel]
            win = jv > best[jsel]
            if win.any():
                w = jsel[win]
                best = best.copy()
                best[w] = jv[win]
                bk[w] = 3
        back[t] = bk
        score = best + e
    s = S - 1 if score[S - 1] >= score[S - 2] else S - 2
    path = np.empty(T, np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        b = int(back[t, s])                 # int() กัน numpy คิดเป็น int8 แล้วล้น
        s = int(jsrc[s]) if b == 3 else s - b
    # เฟรมแรกที่ path เข้าสถานะ token แต่ละตัว (Viterbi บังคับผ่านทุก token ตามลำดับ ยกเว้นช่วงที่ข้าม)
    first: dict[int, int] = {}
    for t in range(T):
        st = int(path[t])
        if kind[st] == 1 and st not in first:
            first[st] = t
    out: list = []
    for li, toks in enumerate(lines_tok):
        if not toks:
            out.append(None)
            continue
        fr = np.where((line[path] == li) & (kind[path] == 1))[0]
        if not len(fr):
            out.append("skip")
            continue
        sp = path[fr]
        pr = np.empty(len(fr))
        for m in range(len(lps)):
            sel = mdl[sp] == m
            if sel.any():
                pr[sel] = np.exp(lps[m][fr[sel], tok[sp[sel]]])
        by_m = {m: float(pr[mdl[sp] == m].mean()) for m in range(len(lps)) if (mdl[sp] == m).any()}
        tf = sorted((int(tix[st]), f) for st, f in first.items() if line[st] == li)
        seen = {ti for ti, _ in tf}
        skipped = [ti for ti in range(len(toks)) if ti not in seen]
        out.append((int(fr[0]), int(fr[-1]), float(pr.mean()), tf, by_m, skipped))
    return out


def paren_spans(text: str, pos: list[int], pen: float = SPAN_PEN) -> list[tuple[int, int, float]]:
    """ช่วง token ที่อยู่ในวงเล็บ (ตำแหน่งตัวอักษร NFC เดียวกับ tokenize) -> [(token แรก, token สุดท้าย, โทษ)]"""
    out = []
    t = unicodedata.normalize("NFC", text)
    for m in _PAREN.finditer(t):
        idx = [i for i, p in enumerate(pos) if m.start() <= p < m.end()]
        if idx:
            out.append((idx[0], idx[-1], pen))
    return out


def line_dur(t: float, nxt: float, sung: float | None) -> float:
    """เท่าที่ร้องจริง + หาง แต่ไม่ล้ำบรรทัดถัดไป (สูตรเดียวกับ lyrics_sources.line_dur)
    ขั้นต่ำ 1 วิ เฉพาะเมื่อบรรทัดถัดไปห่างพอ — ท่อนเร็วเดิมถูกยืดจนทับกัน จอเลยค้างบรรทัดเก่า"""
    d = nxt - t if sung is None else min(nxt - t, max(sung, MIN_DUR))
    lo = min(MIN_DUR, max(0.3, nxt - t))
    return max(lo, min(MAX_DUR, d))


def cached(vid: str, en: bool = False, audio: Path | None = None, stem: str = "") -> bool:
    """มีแคชที่ใช้กับไฟล์เสียงนี้ได้ไหม (audio=None = ไม่ตรวจลายเซ็น เหมือนเดิม)"""
    return _cache_ok(_cache_file(vid, MODEL_EN if en else MODEL, stem), audio)


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
               audio_path: Path | None = None, words: bool = False, anchors: list | None = None,
               opt: dict | None = None) -> dict:
    """words=True: แต่ละบรรทัดได้ k = [[ตำแหน่งตัวอักษร, วินาที], ...] ตอนที่ตัวนั้นถูกร้อง (ไล่สีคาราโอเกะ)
    anchors: เวลาบรรทัดที่เชื่อถือได้อยู่แล้ว [[t, d], ...] -> บรรทัดที่ผลไหลไปไกลถูกจับใหม่รอบเวลานั้น
    opt: ดู docstring ต้นไฟล์ (paren / optional / window / stem) — ไม่ส่ง = พฤติกรรมเดิม"""
    opt = opt or {}
    voices = opt.get("voices")
    if isinstance(voices, list) and len(voices) == len(texts) and any(_alt_voice(v) for v in voices):
        return _time_by_voice(vid, texts, duration, audio_path, words, anchors, opt, voices)
    t0 = time.time()
    stem = "side" if opt.get("stem") == "side" else ""
    lp, vocab, fsec = emissions(vid, audio_path, stem=stem)
    # จับเฉพาะช่วง: ตัดเฟรมนอกหน้าต่างทิ้ง แล้วบวกเวลาเริ่มหน้าต่างกลับตอนท้าย
    f_off = 0
    win = opt.get("window")
    if win and len(win) == 2:
        f0 = max(0, int(float(win[0]) / fsec)); f1 = min(lp.shape[0], max(f0 + 1, int(float(win[1]) / fsec)))
        f_off = f0
    w_sec = f_off * fsec
    if anchors and f_off:
        anchors = [[float(a[0]) - w_sec, a[1]] if a else None for a in anchors]
    index = {c: i for i, c in enumerate(vocab) if c}
    # blank ของ CTC = โทเคน pad (ชื่อแล้วแต่โมเดล: [PAD] / <pad>) — เฟรมส่วนใหญ่ของเพลงเป็นตัวนี้
    blank = next((index[k] for k in ("[PAD]", "<pad>") if k in index), 0)
    delim = index.get("|")
    tp = [tokenize(x, index, delim, with_pos=True) for x in texts]
    optional = {int(i) for i in (opt.get("optional") or []) if isinstance(i, (int, float))}

    def spans_for(tpx):
        if not opt.get("paren") and not optional:
            return None
        out = []
        mode = opt.get("paren")
        for i, (x, (toks, pos)) in enumerate(zip(texts, tpx)):
            sp = paren_spans(x, pos) if mode else []
            if mode == "tail":                         # เฉพาะวงเล็บท้ายบรรทัด (เสียงตามหลัง) — ต้นบรรทัด/ทั้งบรรทัดไม่ข้าม
                sp = [q for q in sp if q[0] > 0 and q[1] >= len(toks) - 1]
            if i in optional and toks:
                sp = [(0, len(toks) - 1, LINE_PEN)]
            elif sp and len(sp) == 1 and sp[0][0] == 0 and sp[0][1] == len(toks) - 1:
                sp = [(0, len(toks) - 1, LINE_PEN)]     # ทั้งบรรทัดอยู่ในวงเล็บ = คอรัสทั้งบรรทัด ข้ามได้แต่แพงกว่า
            out.append(sp)
        return out
    lp_w = lp[f_off:f1] if f_off or (win and len(win) == 2) else lp
    # คำอังกฤษ (โหมดคาราโอเกะ): จับพร้อมกันกับตัวไทยในเส้นทางเดียว ด้วยโมเดลอังกฤษอีกตัว
    # ไม่มีโมเดลในเครื่อง/พัง = จับแค่ตัวไทยเหมือนเดิม (จอเกลี่ยเวลาตัวอังกฤษระหว่างตัวไทยเอง)
    en_note, joint = "", False
    if has_latin(texts):                        # ทุกโหมด (ให้คะแนน/ความคลาด/จับเวลา/ไล่สี) ไม่ใช่แค่ words
        if not model_ready(MODEL_EN):
            en_note = "no-model"
        else:
            try:
                lpe, vocab_e, _ = emissions(vid, audio_path, MODEL_EN, stem=stem)
                if win and len(win) == 2:
                    lpe = lpe[f_off:f1]
                idx_e = {c: i for i, c in enumerate(vocab_e) if c}
                blank_e = next((idx_e[k] for k in ("<pad>", "[PAD]") if k in idx_e), 0)
                tpj = [tokenize_joint(x, index, delim, idx_e, idx_e.get("|")) for x in texts]
                res = align(None, [a for a, _ in tpj], None, anchors, fsec, lps=[lp_w, lpe], blanks=[blank, blank_e],
                            spans=spans_for(tpj))
                tp, joint = tpj, True
            except Exception as exc:
                en_note = f"{type(exc).__name__}: {exc}"[:200]
    if not joint:
        res = align(lp_w, [a for a, _ in tp], blank, anchors, fsec, spans=spans_for(tp))
    dur = duration or lp.shape[0] * fsec
    starts: list[float | None] = [None if (r is None or r == "skip") else (r[0] + f_off) * fsec for r in res]
    # บรรทัดที่ไม่มีตัวที่โมเดลรู้จัก (อังกฤษล้วน) / ถูกข้ามทั้งบรรทัด -> แทรกเวลาจากบรรทัดข้าง ๆ
    known = [i for i, s_ in enumerate(starts) if s_ is not None]
    for i, s_ in enumerate(starts):
        if s_ is None:
            p_ = max((k for k in known if k < i), default=None)
            n_ = min((k for k in known if k > i), default=None)
            if p_ is not None and n_ is not None:
                starts[i] = starts[p_] + (starts[n_] - starts[p_]) * (i - p_) / (n_ - p_)
            elif p_ is not None:
                starts[i] = starts[p_] + 2.0 * (i - p_)
            elif n_ is not None:
                starts[i] = max(0.0, starts[n_] - 2.0 * (n_ - i))
            else:
                starts[i] = w_sec
    lines = []
    for i, x in enumerate(texts):
        t = round(max(0.0, starts[i]), 2)
        nxt = starts[i + 1] if i + 1 < len(texts) else (dur if dur > t else t + 6.0)
        r = res[i]
        rr = r if (r is not None and r != "skip") else None
        sung = (rr[1] - rr[0] + 1) * fsec + 0.3 if rr else None   # ยาวเท่าที่ร้องจริง + หางนิดหน่อย
        d = line_dur(t, nxt, sung)
        ln = {"t": t, "d": round(d, 2), "x": x, "conf": round(rr[2], 3) if rr else (0.0 if r == "skip" else None)}
        if r == "skip":
            ln["sk"] = True                         # ข้ามทั้งบรรทัด (ไม่ได้ยินเสียงนี้) — เวลาเป็นค่าแทรก
        if rr and joint and 1 in rr[4]:
            ln["en"] = round(rr[4][1], 3)            # ความมั่นใจเฉพาะตัวละติน
        if rr:
            ntok = sum(1 for q in tp[i][1] if q >= 0)
            span_s = (rr[1] - rr[0] + 1) * fsec
            if span_s > 0:
                ln["rate"] = round(ntok / span_s, 1)    # ตัวอักษรต่อวินาทีที่ร้องจริง (ท่อนแร็ป ~12+)
            if rr[5]:
                ln["skip"] = _skip_ranges(rr[5], tp[i][1])
        if words and rr:
            k = _k_from(rr, tp[i][1], fsec, f_off)
            if k:
                ln["k"] = k
        lines.append(ln)
    cov = 100.0 * sum(1 for r in res if r is not None and r != "skip") / max(1, len(res))
    out = {"lines": lines, "by": "fa", "cov": round(cov, 1), "ok": cov >= 60,
           "sec": round(time.time() - t0, 1)}
    if stem:
        out["stem"] = stem
    if has_latin(texts):
        out["en"] = {"lines": sum(1 for l in lines if "en" in l), "model": MODEL_EN,
                     **({"why": en_note} if en_note else {})}
    return out


def _alt_voice(v) -> bool:
    return v not in (None, "", 1, "1")


def _time_by_voice(vid, texts, duration, audio_path, words, anchors, opt, voices) -> dict:
    """ร้องซ้อน: แยกบรรทัดเสียงหลักกับเสียงอื่นเป็นสองเส้นทาง แต่ละเส้นทางยังเรียงลำดับในตัวเอง
    เสียงอื่น (คนที่ 2/คอรัส) ลองทั้งเสียงร้องปกติและช่องข้างสเตอริโอ (L−R: เสียงที่แพนออกข้างชัดขึ้น
    เพราะเสียงหลักที่อยู่กลางหักล้างหาย) เลือกต่อบรรทัดตัวที่มั่นใจกว่า"""
    t0 = time.time()
    base_opt = {k: v for k, v in opt.items() if k != "voices"}
    main_i = [i for i, v in enumerate(voices) if not _alt_voice(v)]
    alt_i = [i for i, v in enumerate(voices) if _alt_voice(v)]
    sub = lambda idx: [texts[i] for i in idx]
    anc = lambda idx: [anchors[i] for i in idx] if anchors else None
    out_lines: list = [None] * len(texts)
    res_main = time_lines(vid, sub(main_i), duration, audio_path, words, anc(main_i), base_opt) if main_i else None
    if res_main:
        for k, i in enumerate(main_i):
            out_lines[i] = res_main["lines"][k]
    res_alt = time_lines(vid, sub(alt_i), duration, audio_path, words, anc(alt_i), base_opt)
    picked_side = 0
    side_note = ""
    try:
        res_side = time_lines(vid, sub(alt_i), duration, audio_path, words, anc(alt_i), {**base_opt, "stem": "side"})
    except Exception as exc:                      # สเตอริโอไม่มี/คำนวณไม่ได้ -> ใช้เสียงร้องปกติอย่างเดียว
        res_side, side_note = None, f"{type(exc).__name__}: {exc}"[:120]
    for k, i in enumerate(alt_i):
        a = res_alt["lines"][k]
        b = res_side["lines"][k] if res_side else None
        if b and (b.get("conf") or 0) > (a.get("conf") or 0) + 0.05:
            b = dict(b)
            b["stem"] = "side"
            out_lines[i] = b
            picked_side += 1
        else:
            out_lines[i] = a
    for ln, v in zip(out_lines, voices):
        if _alt_voice(v):
            ln["v"] = v
    known = sum(1 for l in out_lines if l.get("conf") is not None)
    cov = 100.0 * known / max(1, len(out_lines))
    out = {"lines": out_lines, "by": "fa", "cov": round(cov, 1), "ok": cov >= 60, "sec": round(time.time() - t0, 1),
           "voices": {"alt": len(alt_i), "side": picked_side, **({"why": side_note} if side_note else {})}}
    if res_main and res_main.get("en"):
        out["en"] = res_main["en"]
    return out


def _skip_ranges(skipped: list[int], pos: list[int]) -> list[list[int]]:
    """token ที่ถูกข้าม -> ช่วงตำแหน่งตัวอักษร [[ต้น, ปลาย], ...] (ไว้บอกจอ/Studio ว่าส่วนไหนไม่ได้ยิน)"""
    ps = sorted({pos[t] for t in skipped if t < len(pos) and pos[t] >= 0})
    out: list[list[int]] = []
    for q in ps:
        if out and q <= out[-1][1] + 2:
            out[-1][1] = q
        else:
            out.append([q, q])
    return out


def handle(vid: str, audio: Path | None, req: dict) -> dict:
    """คำขอหนึ่งครั้ง (stdin ของโหมดปกติ / หนึ่งบรรทัดของ --serve) -> ผลที่พิมพ์ออก stdout"""
    dur = float(req.get("duration") or 0)
    opt = req.get("opt") if isinstance(req.get("opt"), dict) else None
    if "sets" in req:                               # หลายชุดในครั้งเดียว (ให้คะแนนผู้สมัครในห้องหาเนื้อ)
        return {"results": [time_lines(vid, t, dur, audio, opt=opt) if t else None for t in req["sets"]]}
    return time_lines(vid, req.get("texts") or [], dur, audio, words=bool(req.get("words")),
                      anchors=req.get("anchors"), opt=opt)


def serve() -> None:
    """ตัวโหลดโมเดลค้าง: server เปิดไว้หนึ่งตัว ส่งคำขอทีละบรรทัด — ใช้ emissions()/time_lines() ตัวเดียวกับทางปกติ
    ว่างเกิน KARA_FA_IDLE วิ หรือ stdin ปิด (server ปิด/ตาย) = ออกเอง คืนหน่วยความจำ"""
    import select
    idle = float(os.environ.get("KARA_FA_IDLE") or 900)
    out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)                                   # print หลง (ไลบรารี) ไปทาง stderr — stdout จริงเหลือแต่คำตอบ
    sys.stdout = sys.stderr
    while True:
        r, _, _ = select.select([sys.stdin], [], [], idle)
        if not r:
            return                                  # ว่างนาน -> ออก คำขอถัดไป server เปิดตัวใหม่เอง
        line = sys.stdin.readline()
        if not line:
            return                                  # server ปิด/ตาย
        if not line.strip():
            continue
        rid = None
        try:
            msg = json.loads(line)
            rid = msg.get("id")
            if msg.get("op") == "load":
                for m in (MODEL, MODEL_EN):
                    if model_ready(m):
                        _load_model(m)
                res = {"id": rid, "ok": True, "out": {}}
            else:
                audio = Path(msg["audio"]) if msg.get("audio") else None
                res = {"id": rid, "ok": True, "out": handle(str(msg["vid"]), audio, msg.get("req") or {})}
        except Exception as exc:
            res = {"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
        if "torch" in sys.modules:
            try:
                import torch
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()             # คืนหน่วยความจำชั่วคราวของการคำนวณ (โมเดลยังอยู่)
            except Exception:
                pass
        res["loaded"] = sorted(_MODELS)                 # server โชว์ใน /api/health
        out.write(json.dumps(res, ensure_ascii=False) + "\n")


def main() -> None:
    argv = sys.argv[1:]
    if "--serve" in argv:
        serve()
        return
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
        lp, _, fsec = emissions(vid, audio, stem="side" if "--side" in argv else "")
        print(json.dumps({"frames": lp.shape[0], "fsec": fsec, "sec": round(time.time() - t0, 1)}))
        return
    req = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(handle(vid, audio, req), ensure_ascii=False))


if __name__ == "__main__":
    main()
