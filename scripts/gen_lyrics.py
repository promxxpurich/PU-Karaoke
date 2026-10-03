#!/usr/bin/env python3
"""gen_lyrics.py — สร้าง lyrics.json ของแต่ละเพลง

  เลือกแหล่งที่ "คนพิมพ์เนื้อ" ก่อนเสมอ และเลี่ยงการถอดเสียงเองให้มากที่สุด:
    1. lyrics-in/<vid>.lrc|.txt   ผู้ใช้วางเอง (สำคัญสุด)
    2. songs/yt/<เพลง>/sub.th.vtt ซับจริงของ YouTube — เวลาเป๊ะ ไม่ต้องคำนวณ
    3. lrclib.net                 synced LRC กรองด้วยความยาวเพลง + ความเหมือนของเนื้อ
    4. songs/yt/<เพลง>/auto.th.vtt  auto-caption (ASR ของ YouTube) มี timestamp ระดับคำ
       4a. มีเนื้อจริงแล้ว -> ใช้เป็น "เส้นเวลา" จับเวลาให้เนื้อนั้น (ไม่แตะ GPU)
       4b. ยังไม่มีเนื้อ   -> ใช้คำที่ถอดได้เป็นคำค้น lrclib ก่อน ถ้ายังไม่เจอค่อยใช้เป็นเนื้อ
    5. ถอดเสียงเอง (mlx-whisper, ตั้งโมเดลด้วย KARA_ASR_MODEL) -> ใช้เป็นเส้นเวลาเท่านั้น

  ไม่มีแหล่งไหนให้เนื้อเลย = เขียน lyrics.nolyr.json แล้วออกด้วย NO_LYRICS
  (เลิกเอาคำที่เครื่องถอดได้มาเป็นตัวเนื้อเพลง เพราะอ่านแล้วไม่เป็นภาษา)

  ผลลัพธ์:
    songs/yt/<เพลง>/lyrics.json   src = ใครพิมพ์เนื้อ, timeSrc = ใครจับเวลา
    songs/yt/<เพลง>/lyrics.nolyr.json  หมุดว่าลองครบทุกแหล่งแล้วไม่เจอ
    lyrics-preview/<vid>.srt      (พรีวิวดูผล)
    lyrics-preview/_seg/<vid>.<โมเดล>.json (แคช segment — รันซ้ำไม่ต้องถอดใหม่)

  exit code: 0 สำเร็จ | 3 ต้องถอดเสียงต่อ (เฉพาะ --no-asr) | 4 ไม่มีเนื้อจากทุกแหล่ง

  ใช้:  ./scripts/gen_lyrics.py [vid ...]     (ไม่ใส่ vid = ทำทุกเพลง)
        ./scripts/gen_lyrics.py --no-asr      เฉพาะแหล่งที่ไม่ใช้ GPU
        ./scripts/gen_lyrics.py --skip-done   (เฉพาะเพลงที่ยังไม่มี lyrics.json)
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lyrics_sources as LS
import extract_src as EX

BASE = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(BASE / ".cache" / "hf"))
os.environ.setdefault("HF_HUB_CACHE", str(BASE / ".cache" / "hf" / "hub"))
os.environ.setdefault("XDG_CACHE_HOME", str(BASE / ".cache"))

# วัดจริง 24 เพลงด้วย onTime (scripts/ab_asr.py): turbo เร็วกว่า 3.5 เท่า (145s -> 41s)
# คะแนนเฉลี่ย +2.0 ดีขึ้น 13 เพลง แย่ลง 7 -> เลือก turbo เป็นค่าเริ่มต้น
# เพลงที่ผลออกมาไม่ดีใช้ปุ่ม "โหลดเนื้อใหม่" หรือสลับโมเดลชั่วคราวด้วย:
#   KARA_ASR_MODEL=mlx-community/whisper-large-v3-mlx ./run.sh
LEGACY_MODEL = "mlx-community/whisper-large-v3-mlx"   # แคชชื่อ "<vid>.json" ถอดด้วยตัวนี้
MODEL = os.environ.get("KARA_ASR_MODEL", "mlx-community/whisper-large-v3-turbo")
# ข้อควรรู้: onTime วัดได้แค่ "เวลาตรงไหม" ไม่ได้วัด "ตัวหนังสือถูกไหม"
# เพลงที่ไม่มีเนื้อจากแหล่งไหนเลย ตัวหนังสือที่ถอดได้ *คือ* เนื้อเพลง — ยังไม่มีตัวเลขว่าโมเดลไหนดีกว่า
# ในบทบาทนั้น (ลองเทียบแล้วผลแกว่งระหว่างรอบมากกว่าต่างระหว่างโมเดล เพราะ whisper มี
# temperature fallback จึงไม่ deterministic) จึงใช้ตัวเดียวกันไปก่อน แต่เปิดช่องไว้สลับได้
ACCURATE_MODEL = os.environ.get("KARA_ASR_MODEL_TEXT", MODEL)
# tag สั้น ๆ ไว้ใส่ในชื่อแคช — คนละโมเดลต้องคนละไฟล์ ไม่งั้นสลับโมเดลแล้วได้ผลเก่าคืนมาเงียบ ๆ
def model_tag(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name.rsplit("/", 1)[-1]).strip("-")


MODEL_TAG = model_tag(MODEL)
DL = Path(os.environ["KARA_SONGS_DIR"]) if os.environ.get("KARA_SONGS_DIR") else BASE / "songs" / "yt"   # override ไว้ทดสอบกับคลังจำลอง
SRC = BASE / "lyrics-preview" / "_src"
SEG = Path(os.environ["KARA_SEG_DIR"]) if os.environ.get("KARA_SEG_DIR") else BASE / "lyrics-preview" / "_seg"   # override ไว้ทดสอบกับคลังจำลอง
SRT = BASE / "lyrics-preview" / "_srt"
MANUAL = Path(os.environ["KARA_LYRICS_IN"]) if os.environ.get("KARA_LYRICS_IN") else BASE / "lyrics-in"   # override ไว้ทดสอบกับคลังจำลอง
# แหล่งที่ให้ "เวลา" มาด้วย (ไม่ได้จับเวลาเอง) -> ไม่ต้องเตือนผู้ใช้ว่าเวลาอาจเพี้ยน
# แหล่งที่เวลามาจากตัวมันเอง ไม่ได้เดา -> ไม่ต้องขึ้นคำเตือนเรื่องเวลา
# "asr" อยู่ในนี้เพราะเวลามาจากเสียงของคลิปนั้นเองตรง ๆ ที่ไม่ชัวร์คือ "ตัวหนังสือ" ไม่ใช่ "เวลา"
# "yt-auto" อยู่ในนี้เพราะ *เวลา* มาจากแหล่งตรง ๆ ไม่ได้เดาเอง — ส่วนที่ไม่ชัวร์คือ
# ตัวหนังสือ ซึ่งไปแสดงผ่านป้ายความมั่นใจแทน ไม่ใช่ผ่านคำเตือนเรื่องเวลา
# "asr" ถูกถอดออก: ไม่มีเส้นทางไหนผลิตมันอีกแล้ว (เลิกใช้คำที่เครื่องถอดเป็นตัวเนื้อ)
TRUSTED_TIME = frozenset({"manual-lrc", "manual-edit", "yt-sub", "lrclib", "yt-auto"})
MIN_DUR_L, MAX_DUR_L = 1.0, 14.0   # ความยาวบรรทัดที่จอรับได้ (เท่ากับ lyrics_sources)
SEG_V = 2                       # ขึ้นเวอร์ชันเมื่อรูปแบบแคชเปลี่ยน (v1 ไม่ได้เก็บ words)
FLAGS = {"--skip-done", "--no-asr"}   # ที่เหลือคือ videoId ทั้งหมด
NEED_ASR = 3                    # exit code: แหล่งที่ไม่ใช้ GPU หมดแล้ว ต้องถอดเสียงต่อ
NO_LYRICS = 4                   # exit code: ลองครบทุกแหล่งแล้วไม่มีเนื้อ ถอดเสียงอีกก็ไม่ช่วย
_NOLYR: list[str] = []          # vid ที่จบด้วย "ไม่มีเนื้อ" ในรอบนี้
SEG.mkdir(parents=True, exist_ok=True)
SRT.mkdir(parents=True, exist_ok=True)

RE_VID = re.compile(r"\[([A-Za-z0-9_-]{11})\]$")

# เครื่องหมายวรรณยุกต์ / สระบนที่เสียงพูดไม่ตรงการเขียน → ตัดออกตอนเทียบ เก็บข้อความเดิมไว้แสดง
_TONE_RE = re.compile(r"[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e\u0e30]")


def vid_of(name: str) -> str:
    m = RE_VID.search(name)
    return m.group(1) if m else name


def norm_chars(s: str) -> list[str]:
    s = s or ""
    s = unicodedata_normalize(s)
    out = []
    for ch in s:
        if ch.isspace():
            continue
        if _TONE_RE.match(ch):
            continue
        if "\u0e00" <= ch <= "\u0e7f" or ch.isalnum():
            out.append(ch.lower())
    return out


def unicodedata_normalize(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", s)


# ---------------------------------------------------------------------------
# 1) ถอดเสียง
# ---------------------------------------------------------------------------
def _degenerate(res: dict) -> bool:
    """whisper วนลูปคายข้อความเดิมซ้ำ ๆ (เคยเจอทั้งเพลงเป็น "!") — ผลแบบนี้ใช้ไม่ได้"""
    segs = [(sg.get("text") or "").strip() for sg in (res.get("segments") or [])]
    segs = [t for t in segs if t]
    if len(segs) < 4:
        return True
    top = max(segs.count(t) for t in set(segs))
    return top > len(segs) * 0.6


def _asr(audio: Path, model: str, lang: str = "th", **kw) -> dict:
    import mlx_whisper
    return mlx_whisper.transcribe(
        str(audio), path_or_hf_repo=model, language=lang or "th", task="transcribe",
        word_timestamps=True, verbose=False, **kw)


def detect_lang(audio: Path, model: str = "") -> tuple[str, float] | None:
    """ให้ whisper ฟัง 30 วิกลางเพลงแล้วบอกภาษา -> (รหัสภาษา, ความน่าจะเป็น) — ใช้ GPU ~2-3 วิ
    กลางเพลงเพราะต้นเพลงมักเป็นดนตรี/เงียบ (แยกเสียงแล้วยิ่งเงียบ)"""
    import mlx_whisper
    from mlx_whisper import audio as A, decoding as D, load_models as L
    wav = A.load_audio(str(audio))
    n = A.N_SAMPLES
    m = L.load_model(model or MODEL)
    total: dict[str, float] = {}
    # ฟัง 2 ช่วง (30% กับ 60% ของเพลง) แล้วรวมความน่าจะเป็น — ท่อนเดียวอาจเป็นฮุคอังกฤษของเพลงไทย
    for frac in (0.3, 0.6):
        st = max(0, int(len(wav) * frac)) if len(wav) > n else 0
        seg = wav[st:st + n]
        mel = A.log_mel_spectrogram(A.pad_or_trim(seg), n_mels=m.dims.n_mels)
        _, probs = D.detect_language(m, mel)
        probs = probs[0] if isinstance(probs, list) else probs
        for k, v in probs.items():
            total[k] = total.get(k, 0.0) + float(v) / 2
        if len(wav) <= n:
            break
    lang, p = max(total.items(), key=lambda kv: kv[1])
    return lang, float(p)


def transcribe(vid: str, audio: Path, model: str = "", lang: str = "th") -> dict:
    """ถอดเสียง 1 เพลง พร้อมทางหนีทีไล่เมื่อ whisper วนลูป"""
    model = model or MODEL
    t0 = time.monotonic()
    res = _asr(audio, model, lang, condition_on_previous_text=True)
    if _degenerate(res):
        # condition_on_previous_text คือตัวที่ทำให้วนซ้ำ ปิดแล้วลองใหม่
        print(f"[asr] {vid} ผลวนซ้ำ ลองใหม่แบบไม่อิงท่อนก่อนหน้า", flush=True)
        res = _asr(audio, model, lang, condition_on_previous_text=False)
    if _degenerate(res) and audio.name == "vocals.m4a" and audio.with_name("audio.m4a").is_file():
        # เสียงร้องที่แยกออกมาอาจบางเกินไป -> ใช้เสียงเต็มแทน
        print(f"[asr] {vid} ยังวนซ้ำ ลองที่เสียงเต็ม", flush=True)
        res = _asr(audio.with_name("audio.m4a"), model, lang, condition_on_previous_text=False)
    print(f"[asr] {vid} {time.monotonic()-t0:.1f}s ({model_tag(model)}, {lang})", flush=True)
    return res


def segment_cache_path(vid: str, tag: str = "", lang: str = "th") -> Path:
    """แคชแยกภาษา: ไทยชื่อเดิม ภาษาอื่นต่อท้าย (แคชที่เคยถอดเพลงอังกฤษเป็นไทยจะไม่ถูกใช้ซ้ำ)"""
    sfx = "" if (lang or "th") == "th" else f".{lang}"
    return SEG / f"{vid}.{tag or MODEL_TAG}{sfx}.json"


def get_segments(vid: str, audio: Path, model: str = "", lang: str = "th") -> dict:
    """คืน {'segs':[{start,end,text}], 'duration': float} — แคชใน _seg/<vid>.<tag>.json
    แคชรุ่นเก่าชื่อ "<vid>.json" ทั้งหมดถอดด้วย large-v3 -> อ่านต่อได้เฉพาะตอนใช้โมเดลนั้น
    (อ่านอย่างเดียว ไม่เขียนทับ ย้อนกลับได้เสมอ)"""
    model = model or MODEL
    lang = lang or "th"
    cache = segment_cache_path(vid, model_tag(model), lang)
    legacy = SEG / f"{vid}.json"
    for f in ((cache, legacy) if model == LEGACY_MODEL and lang == "th" else (cache,)):
        if f.is_file():
            try:
                old = json.loads(f.read_text("utf-8"))
                if old.get("v", 1) >= SEG_V:
                    return old
            except Exception:
                pass                        # แคชพัง/เก่า -> ถอดใหม่
    res = transcribe(vid, audio, model, lang)
    segs = []
    for sg in res.get("segments") or []:
        text = (sg.get("text") or "").strip()
        if not text:
            continue
        # ต้องเก็บ words ด้วย ไม่งั้น make_chunks ตกไปใช้ทั้ง segment เป็นก้อนเดียว
        # แล้ว anchor จะหยาบจนเวลาเพี้ยนกลางเพลง
        words = [{"start": w.get("start"), "end": w.get("end"), "word": w.get("word")}
                 for w in (sg.get("words") or [])]
        segs.append({"start": sg["start"], "end": sg["end"], "text": text, "words": words})
    data = {
        "v": SEG_V,
        "segs": segs,
        "duration": float(res.get("duration") or (segs[-1]["end"] if segs else 0.0)),
    }
    tmp = cache.with_suffix(".json.tmp")   # เขียนแบบ atomic: โดนฆ่ากลางทางต้องไม่เหลือ JSON พัง
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)
    return data


# ---------------------------------------------------------------------------
# 2) อ่านเนื้อจริง
# ---------------------------------------------------------------------------
def _extract_src(vid: str, folder: Path, lang: str = "th") -> list[str]:
    """สกัดเนื้อจาก description ของคลิปแล้วแคชไว้ที่ _src/<vid>.txt

    เพลงที่โหลดผ่านเซิร์ฟเวอร์ไม่เคยผ่าน extract_src.py มาก่อน ถ้าไม่ทำตรงนี้
    แหล่งที่ 3 จะหายไปเงียบ ๆ และตอนซ่อมก็จะไม่มีตัวท้าชิงจาก description
    """
    ij = folder / "info.json"
    if not ij.is_file():
        return []
    try:
        desc = json.loads(ij.read_text("utf-8")).get("description") or ""
    except Exception:
        return []
    lines = EX.extract(desc, lang)
    if sum(1 for l in lines if EX.in_lang(l, lang)) < 4:   # เกณฑ์เดียวกับ extract_src.main()
        return []
    SRC.mkdir(parents=True, exist_ok=True)
    (SRC / f"{vid}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def read_lines(vid: str, folder: Path | None = None, lang: str = "th") -> tuple[list[str], str]:
    """เนื้อเปล่า (ยังไม่มีเวลา) -> (บรรทัด, ที่มา)
    ไฟล์ที่ผู้ใช้วางเองใน lyrics-in/ มาก่อนเนื้อที่สกัดจาก description เสมอ"""
    for f, src in ((MANUAL / f"{vid}.txt", "manual-txt"), (SRC / f"{vid}.txt", "web/description")):
        if f.is_file():
            lines = [l.strip() for l in f.read_text("utf-8").splitlines() if l.strip()]
            if lines:
                return lines, src
    if folder is None:
        folder = next((d for d in DL.iterdir()
                       if d.is_dir() and not d.name.startswith(".") and vid_of(d.name) == vid), None)
    if folder is not None:
        lines = _extract_src(vid, folder, lang)
        if lines:
            return lines, "web/description"
    return [], ""


# ---------------------------------------------------------------------------
# 3) Fuzzy align: จับคู่ chunk ของ ASR กับเนื้อจริง (แบบ monotonic)
# ---------------------------------------------------------------------------
def build_stream(lines: list[str]):
    """คืน (chars, line_index_of_char)"""
    chars: list[str] = []
    line_of: list[int] = []
    for i, ln in enumerate(lines):
        for ch in norm_chars(ln):
            chars.append(ch)
            line_of.append(i)
    return chars, line_of


def make_chunks(segs: list[dict], max_chars: int = 6) -> list[dict]:
    """แบ่ง segment/text ให้เป็น chunk ขนาดพอดี (หลายคำ) — มีเวลาเริ่มของคำแรก
    คืน [{t, chars:[...]}] โดย chars ผ่าน norm แล้ว

    max_chars=6 มาจากการวัดจริงกับเพลงที่ต้องพึ่ง ASR: 6 ได้ anchor เฉลี่ย 56%
    ส่วน 10 ได้ 51% และ 20 ขึ้นไปได้ไม่ถึง 46% (ก้อนใหญ่ไปจะหาที่ลงไม่เจอ)"""
    words = []
    for sg in segs:
        for w_ in sg.get("words") or []:
            t = w_.get("start")
            te = w_.get("end")
            txt = norm_chars(w_.get("word") or "")
            if not txt:
                continue
            words.append({"t": t if t is not None else sg["start"],
                          "end": te if te is not None else sg["end"],
                          "chars": txt})
    if not words:                       # ไม่มี word timestamp -> ใช้ทั้ง segment
        for sg in segs:
            txt = norm_chars(sg["text"])
            if len(txt) >= 2:
                words.append({"t": sg["start"], "end": sg["end"], "chars": txt})
    ch = []
    cur = []
    first_t = None
    for w in words:
        if first_t is None:
            first_t = w["t"]
        cur.extend(w["chars"])
        if len(cur) >= max_chars:
            if len(cur) >= 2:
                ch.append({"t": first_t, "chars": cur})
            cur = []
            first_t = None
    if len(cur) >= 2:
        ch.append({"t": first_t if first_t is not None else words[-1]["t"], "chars": cur})
    return ch


ASR_MAX_CHARS = 34          # บรรทัดยาวกว่านี้ตัดย่อย ไม่งั้นจอต้องย่อตัวอักษรจนเล็ก
ASR_MIN_LINES = 4           # คลิปสั้นบางอันมีไม่กี่ท่อนจริง ๆ จึงไม่ใช้เกณฑ์ MIN_LINES ของแหล่งอื่น


def align_ok(starts: list[float], durs: list[float], cov: float, duration: float) -> bool:
    """เวลาที่จับได้ใช้ได้จริงไหม — เกณฑ์เดียวกับที่ server ใช้ตัดสินว่า "เวลาน่าสงสัย"

    เคสที่ต้องดักคือเนื้อต้นฉบับยาวกว่าคลิป (คัฟเวอร์ตัดท่อน/รีมิกซ์สั้น) แล้ว align
    จะยัดบรรทัดที่เหลือไปกองท้ายเพลงทับกันหมด ซึ่งแย่กว่าไม่มีเนื้อ
    """
    n = len(starts)
    if n < 2 or duration <= 0:
        return False
    over = sum(1 for i in range(n - 1) if starts[i + 1] < starts[i] + durs[i] - 0.2)
    return cov >= 45 and over <= 0.10 * (n - 1) and starts[0] / duration <= 0.35


AUTO_GAP = 1.2          # เงียบนานกว่านี้ = ขึ้นบรรทัดใหม่ (ตรงกับการหายใจของคนร้อง)
AUTO_MAX_CHARS = 26     # ความยาวบรรทัดที่ "ตาเห็น" — ต้องนับตัวอักษรดิบ ไม่ใช่ norm_chars
                        # เพราะ norm_chars ตัดสระ/วรรณยุกต์ออก บรรทัดไทยจึงยาวเกินจอ
                        # (วัดกับเพลงจริง: 26 ได้ยาวสุด 29 เฉลี่ย 21 ใกล้เคียงของ whisper
                        #  ที่ยาวสุด 35 เฉลี่ย 20 ส่วน 34 ได้ยาวสุด 37 ซึ่งล้นจอ)


def lines_from_words(words: list[dict], duration: float,
                     max_chars: int = AUTO_MAX_CHARS, gap: float = AUTO_GAP,
                     min_lines: int = ASR_MIN_LINES) -> list[dict]:
    """[{start,end,word}] -> [{t,d,x}] ตัดบรรทัดให้อ่านบนจอคาราโอเกะได้

    ตัด 2 เงื่อนไข เรียงตามความสำคัญ:
      1. ช่องเงียบ >= gap — ตรงกับการหายใจ/จบวรรคของคนร้องจริง ดีกว่าหั่นตามจำนวนตัวอักษร
         (auto-caption ทิ้งช่องไว้ตรงท่อนดนตรีให้เอง หลังล้างแท็ก [เพลง] ออก)
      2. ยาวเกิน max_chars — กันบรรทัดล้นจอ

    ต้องต่อคำด้วยสตริงว่าง: token ภาษาไทยไม่มีช่องว่าง ส่วนภาษาอังกฤษตัวถอดเสียงใส่
    ช่องว่างนำหน้ามาให้อยู่แล้ว — ถ้าใส่ช่องว่างเองคำไทยจะแตกเป็นตัว ๆ"""
    rows: list[tuple[float, str]] = []
    cur: list[str] = []
    t0 = prev_end = None
    for w in words:
        txt = w.get("word") or ""
        st = float(w["start"])
        if cur and (st - (prev_end or st) >= gap
                    or len("".join(cur)) >= max_chars):
            rows.append((t0, "".join(cur).strip()))
            cur, t0 = [], None
        if t0 is None:
            t0 = st
        cur.append(txt)
        prev_end = float(w.get("end") or st)
    if cur and t0 is not None:
        rows.append((t0, "".join(cur).strip()))

    out: list[dict] = []
    for t, x in rows:
        if not x or not norm_chars(x) or (out and out[-1]["x"] == x):
            continue
        if out and t < out[-1]["t"]:                # กันเวลาถอยหลัง
            continue
        out.append({"t": round(float(t), 2), "d": 0.0, "x": x})
    if len(out) < min_lines:
        return []
    for i, ln in enumerate(out):
        nxt = out[i + 1]["t"] if i + 1 < len(out) else (duration if duration > ln["t"]
                                                       else ln["t"] + 6.0)
        ln["d"] = LS.line_dur(ln["t"], nxt)       # ขั้นต่ำ 1 วิ แต่ไม่ล้ำบรรทัดถัดไป (ท่อนเร็ว)
    return out


def find_candidates(chars, tgt, k=8):
    """หา candidate (cost, start) ที่ดีหลายตำแหน่ง (แก้ปัญหาเนื้อซ้ำ: อยากได้ทุก occurrence)
    จัดเรียงตาม cost จากน้อยไปมาก (Semi-global DP ซ้ำ โดยกัน prefix ที่เคยเจอแล้ว)"""
    n = len(chars)
    m = len(tgt)
    if n == 0 or m == 0:
        return []
    INF = 10 ** 9
    excluded = []
    out = []
    for _ in range(k):
        prev = [0] * (n + 1)
        # กัน prefix-start ใน excluded ไม่ให้เริ่มที่นั่น: ทำให้ dp[0][j] เป็น INF ถ้า j-1 ตกใน excluded
        start_mask = [False] * (n + 1)
        for s in excluded:
            start_mask[s] = True
        prev[0] = 0
        for j in range(1, n + 1):
            prev[j] = INF if start_mask[j - 1] else 0
        dec = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            cur = [INF] * (n + 1)
            cur[0] = i
            dec[i][0] = 1
            ci = tgt[i - 1]
            for j in range(1, n + 1):
                cj = chars[j - 1]
                sub = prev[j - 1] + (0 if ci == cj else 1)
                dele = prev[j] + 1
                skip = cur[j - 1] + 1
                if sub <= dele and sub <= skip:
                    cur[j], dec[i][j] = sub, 0
                elif dele <= skip:
                    cur[j], dec[i][j] = dele, 1
                else:
                    cur[j], dec[i][j] = skip, 2
            prev = cur
        best_j = min(range(1, n + 1), key=lambda j: prev[j])
        best_cost = prev[best_j]
        i, j = m, best_j
        while i > 0:
            act = dec[i][j]
            if act == 0:
                i -= 1
                j -= 1
            elif act == 1:
                i -= 1
            else:
                j -= 1
        start = j
        out.append((best_cost, start))
        excluded.append(start)
    return out


def fuzzy_match(chars, lo, hi, tgt):
    """หาตำแหน่ง start ใน chars[lo:hi] ที่ align tgt ได้นอยที่สุด (semi-global Levenshtein)
    คืน (best_cost, start) หรือ None ถ้าไม่ match เกิน threshold"""
    n = len(tgt)
    if n == 0:
        return None
    m = hi - lo
    if m < 1:
        return None
    INF = 10 ** 9
    # dp[i][j] ใช้ 2 แถวสลับ เก็บ decision เพื่อ backtrack ตำแหน่งเริ่ม
    prev = [0] * (m + 1)                 # dp[0][*] = 0 (ข้าม prefix ได้ฟรี)
    dec = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        dec[0][j] = 0
    for i in range(1, n + 1):
        cur = [INF] * (m + 1)
        cur[0] = i                       # ลบทุกตัวของ tgt
        dec[i][0] = 1
        ci = tgt[i - 1]
        for j in range(1, m + 1):
            cj = chars[lo + j - 1]
            sub = prev[j - 1] + (0 if ci == cj else 1)
            dele = prev[j] + 1           # ลบตัว tgt (ไม่จับคู่)
            skip = cur[j - 1] + 1        # ข้ามตัวจริง (เริ่มช้า/ยาวเกิน)
            best = sub
            act = 0
            if dele < best:
                best, act = dele, 1
            if skip < best:
                best, act = skip, 2
            cur[j] = best if best < INF else INF
            dec[i][j] = act
        prev = cur
    # ตำแหน่งจบที่ดีสุด
    best_j = min(range(1, m + 1), key=lambda j: prev[j])
    best_cost = prev[best_j]
    # เกณฑ์รับ: ยอมเพี้ยนได้ ~45% (สั้นๆ ถึงเผื่อ 2 ตัว)
    thr = 2 if n <= 3 else int(round(0.45 * n)) + (0 if n <= 8 else 1)
    if best_cost > thr:
        return None
    # backtrack หา start
    i, j = n, best_j
    while i > 0:
        act = dec[i][j]
        if act == 0:
            i -= 1
            j -= 1
        elif act == 1:
            i -= 1
        else:
            j -= 1
    return best_cost, lo + j


def _cost_ok(n: int, cost: int) -> bool:
    thr = 2 if n <= 3 else int(round(0.45 * n)) + (0 if n <= 8 else 1)
    return cost <= thr


def align(chunks: list[dict], lines: list[str], duration: float) -> list[dict]:
    """จับคู่ทีละ chunk หาเนื้อจริงทั่วทั้งเพลง (tolerant ต่อ ASR เพี้ยน/ซ้ำ)
    กันไม่ให้ chunk หลายตัวมากองที่เนื้อเดียวกัน แล้วเก็บ [{t, line}]"""
    if not lines:
        return []
    chars, line_of = build_stream(lines)
    n = len(chars)
    anchors = []
    committed: list[tuple[int, int]] = []
    for c in chunks:
        tgt = c["chars"]
        m = len(tgt)
        cand = find_candidates(chars, tgt)
        got = None
        for cost, start in cand:
            if not _cost_ok(m, cost):
                break
            # รับถ้าไม่ทับเนื้อที่เคย commit ไปแล้วเกินครึ่ง
            o = sum(max(0, min(e, start + m) - max(s, start)) for s, e in committed)
            if o * 2 < m or len(committed) == 0:
                got = (cost, start)
                break
        if got is None:
            continue
        cost, start = got
        committed.append((start, start + m))
        anchors.append({"t": c["t"], "line": line_of[min(start, n - 1)]})
    return anchors


def timings_for_lines(lines: list[str], anchors: list[dict], duration: float) -> list[float]:
    """เวลเริ่มแต่ละบรรทัด = lerp ตามตำแหน่งอักษรของบรรทัดใน stream ระหว่างจุด (char, time) ที่รู้
    (anchor จาก ASR + จุดต้น (0,0) + จุดปลาย (n, duration)) — monotonic โดยโครงสร้าง"""
    chars, line_of = build_stream(lines)
    starts_part = []
    acc = 0
    pos = [0]
    for l in lines:
        acc += len(norm_chars(l))
        pos.append(acc)
    n_char = pos[-1]
    # จุด (char, time):
    by_line: dict[int, list[float]] = {}
    for a in anchors:
        by_line.setdefault(a["line"], []).append(a["t"])
    # น้ำหนัก = จำนวนจุดที่ ASR ยืนยันบรรทัดนั้น — บรรทัดที่มีหลายจุดเห็นพ้องกันเชื่อได้กว่า
    points = []
    for li, ts in by_line.items():
        points.append((pos[li], min(ts), len(ts)))
    if duration > 0:
        points.append((0, 0.0, 3))          # ขอบทั้งสองข้างเป็นความจริงตามนิยาม ให้น้ำหนักสูงไว้
        points.append((n_char, duration, 3))
    if not points:
        return [0.0] * len(lines)
    # char เดียวกันเหลือจุดเดียว (เอาเวลาน้อยสุด รวมน้ำหนัก)
    merged: dict[int, tuple[float, int]] = {}
    for c, t, w in points:
        old = merged.get(c)
        merged[c] = (t if old is None or t < old[0] else old[0], w + (old[1] if old else 0))
    pts = [(c, tw[0], tw[1]) for c, tw in sorted(merged.items())]
    # เลือก "ลำดับย่อยที่เวลาไม่ถอยหลัง และยาวที่สุด" (LIS)
    # ของเดิมไล่รับแบบมาก่อนได้ก่อน แล้วทิ้งทุกจุดที่เวลาน้อยกว่าจุดที่รับไว้
    # -> anchor หลงผิดเพียงจุดเดียวที่อยู่ต้น ๆ (เช่นบรรทัดที่ 4 ไปเจอที่ 153s)
    #    ทำให้จุดที่ถูกต้องหลังจากนั้นถูกทิ้งหมด แล้วเนื้อทั้งเพลงไปกองอยู่ท้ายเพลง
    # จุดมีหลักสิบ O(n^2) จึงเหลือเฟือ
    m = len(pts)
    best = [p[2] for p in pts]
    prev = [-1] * m
    for i in range(m):
        for jj in range(i):
            if pts[jj][1] <= pts[i][1] and best[jj] + pts[i][2] > best[i]:
                best[i] = best[jj] + pts[i][2]
                prev[i] = jj
    chain = []
    k = max(range(m), key=lambda i: best[i]) if m else -1
    while k >= 0:
        chain.append((pts[k][0], pts[k][1]))
        k = prev[k]
    dedup = chain[::-1]
    starts = []
    for li in range(len(lines)):
        c = pos[li]
        # หาจุดซ้ายสุดที่มี char <= c และจุดขวาถัดไป
        le = None
        ge = None
        for cj, tj in dedup:
            if cj <= c:
                le = (cj, tj)
            if cj >= c and ge is None:
                ge = (cj, tj)
        if le is None:
            le = dedup[0]
        if ge is None:
            ge = dedup[-1]
        if ge[0] > le[0]:
            t = le[1] + (c - le[0]) * (ge[1] - le[1]) / (ge[0] - le[0])
        else:
            t = ge[1]
        starts.append(round(max(0.0, t), 2))
    for li in range(1, len(starts)):
        if starts[li] < starts[li - 1]:
            starts[li] = starts[li - 1]
    return starts


# ---------------------------------------------------------------------------
# 4) สร้างไฟล์ผลลัพธ์
# ---------------------------------------------------------------------------
def make_srt(lines: list[str], starts: list[float], durs: list[float]) -> str:
    def ts(x: float) -> str:
        sec, ms = divmod(int(round(x * 1000)), 1000)
        mnt, sec = divmod(sec, 60)
        hr, mnt = divmod(mnt, 60)
        return f"{hr:02d}:{mnt:02d}:{sec:02d},{ms:03d}"
    out = []
    for i, (ln, st, du) in enumerate(zip(lines, starts, durs), 1):
        out.append(str(i))
        out.append(f"{ts(st)} --> {ts(st + du)}")
        out.append(ln)
        out.append("")
    return "\n".join(out)


def song_duration(folder: Path) -> float:
    """ความยาวเพลงจาก info.json ก่อน ไม่มีค่อยถาม ffprobe"""
    try:
        j = json.loads((folder / "info.json").read_text("utf-8"))
        if j.get("duration"):
            return float(j["duration"])
    except Exception:
        pass
    for name in ("audio.m4a", "video.mp4"):
        f = folder / name
        if f.is_file():
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(f)], capture_output=True, text=True)
            try:
                return float(r.stdout.strip())
            except ValueError:
                pass
    return 0.0


def _no_lyrics(folder: Path, vid: str, note: str) -> None:
    """หมุดว่า "ลองครบทุกแหล่งแล้วไม่มีเนื้อ" — ต่างจาก "ยังไม่ได้ลอง" และต่างจาก "พัง"
    server อ่านไฟล์นี้เพื่อขึ้นป้าย "ไม่มีเนื้อ" แทนที่จะรายงานว่าหาเนื้อล้มเหลว"""
    cur = folder / "lyrics.json"
    if cur.is_file():
        # สรุปว่าไม่มีเนื้อจากแหล่งไหนเลย -> ของเดิมที่ค้างอยู่ใช้ไม่ได้แล้ว
        # เก็บเป็น prev ไว้ก่อนลบ จะได้ถอยกลับได้ถ้าตัดสินผิด
        (folder / "lyrics.prev.json").write_text(cur.read_text("utf-8"), encoding="utf-8")
        cur.unlink(missing_ok=True)
        (SRT / f"{vid}.srt").unlink(missing_ok=True)
    (folder / "lyrics.nolyr.json").write_text(json.dumps(
        {"v": 1, "videoId": vid, "at": int(time.time()), "why": note},
        ensure_ascii=False), encoding="utf-8")
    _NOLYR.append(vid)


def write_out(folder: Path, vid: str, lines: list[dict], duration: float,
              src: str, engine: str, note: str = "", cov: float | None = None,
              time_src: str = "") -> None:
    """เขียน lyrics.json + .srt พรีวิว แล้วพิมพ์การ์ด QA — ทุกแหล่งออกทางนี้ทางเดียว

    src      = ใครพิมพ์ "ตัวหนังสือ"
    time_src = ใครจับ "เวลา"  (self = มาคู่กับเนื้อ / auto-cap / asr)
    แยกสองแกนนี้เพราะคำถาม "เนื้อถูกไหม" กับ "ตรงจังหวะไหม" ตอบคนละวิธี"""
    (folder / "lyrics.nolyr.json").unlink(missing_ok=True)   # ได้เนื้อแล้ว หมุดเก่าต้องหาย
    if src != "manual-edit":
        # offset ประจำเพลง (ปรับจากรีโมท/Studio) ใช้กับเวลาชุดเก่า — เวลาชุดใหม่ต้องเริ่มที่ 0
        # manual-edit คือฉบับที่คนตั้งเวลาไว้เดิม offset ที่คู่กันจึงยังใช้ได้
        (folder / "lyrics.offset.json").unlink(missing_ok=True)
    out_json = {
        "v": 1,
        "videoId": vid,
        "lang": "th",
        "engine": engine,
        "src": src,
        "duration": round(duration, 2),
        "lines": lines,
    }
    if time_src:
        out_json["timeSrc"] = time_src
    if cov is not None:
        out_json["anchorPct"] = round(cov, 1)
    # เขียนแบบ atomic: ถูกฆ่ากลางเขียน (แย่งคิว/ปิดเครื่อง) จะได้ไม่เหลือไฟล์ขาดครึ่ง
    # ซึ่งอ่านไม่ออกแต่ is_file() เป็นจริง -> เพลงนั้นจะค้างไม่มีเนื้อถาวร
    tmp = folder / "lyrics.json.tmp"
    cur = folder / "lyrics.json"
    try:                            # ของเดิมมาจากคนละแหล่ง -> เก็บไว้ถอยกลับ/เทียบผลได้
        if cur.is_file() and json.loads(cur.read_text("utf-8")).get("src") != src:
            (folder / "lyrics.prev.json").write_text(cur.read_text("utf-8"), encoding="utf-8")
    except Exception:
        pass
    tmp.write_text(json.dumps(out_json, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cur)
    (SRT / f"{vid}.srt").write_text(
        make_srt([l["x"] for l in lines], [l["t"] for l in lines], [l["d"] for l in lines]),
        encoding="utf-8")

    span = (sum(l["d"] for l in lines) / duration * 100) if duration else 0.0
    if src in TRUSTED_TIME:
        qa = "✓"                                    # เวลามาจากแหล่งโดยตรง ไม่ได้เดาเอง
    else:
        qa = "✓" if (cov or 0) >= 55 else "▲" if (cov or 0) >= 35 else "✗"
    detail = f"anchor {cov:.0f}%" if cov is not None else f"คลุม {span:.0f}%"
    print(f"{qa} {vid} [{src}] เส้น {len(lines)} | {detail}"
          f"{' | ' + note if note else ''} | {folder.name}", flush=True)


VOICES = (2, 3, "bg")         # ค่า v ต่อบรรทัดที่รับ (ไม่มี = เสียงหลัก) — ตรงกับ server._clean_edit_lines


def from_edit(vid: str) -> list[dict] | None:
    """lyrics-in/<vid>.json = เนื้อที่แก้ใน Studio — ใช้ตามไฟล์เป๊ะ ไม่ผ่าน _finish
    (ไม่ตัดบรรทัดซ้ำ/ไม่คำนวณความยาวใหม่ เพราะคนตั้งมาเองแล้วทุกค่า)"""
    f = MANUAL / f"{vid}.json"
    if not f.is_file():
        return None
    try:
        rows = json.loads(f.read_text("utf-8")).get("lines") or []
        lines = []
        for l in rows:
            if not str(l.get("x") or "").strip():
                continue
            ln = {"t": round(float(l["t"]), 2), "d": round(float(l["d"]), 2), "x": str(l["x"])}
            if l.get("v") in VOICES:                 # เสียงที่ร้อง (คนที่ 2/3, คอรัส) ที่ตั้งไว้ใน Studio — ห้ามทิ้ง
                ln["v"] = l["v"]
            lines.append(ln)
    except Exception as exc:
        print(f"[manual-edit] {vid} อ่านไฟล์ไม่ได้: {exc}", flush=True)
        return None
    return sorted(lines, key=lambda l: l["t"]) or None


def from_manual(vid: str, duration: float) -> list[dict] | None:
    """ไฟล์ที่ผู้ใช้วางเองใน lyrics-in/ — สำคัญกว่าทุกแหล่ง (เป็นทางแก้เพลงที่ระบบทำพลาด)"""
    f = MANUAL / f"{vid}.lrc"
    if f.is_file():
        return LS.from_lrc(f.read_text("utf-8"), duration)
    return None


def auto_text(words: list[dict]) -> str:
    """ต่อคำจาก auto-caption เป็นข้อความเดียว ไว้ใช้เป็นคำค้น/ตัวยืนยันเพลง"""
    return " ".join(w["word"] for w in words)


def time_with(src_lines: list[str], words: list[dict],
              duration: float) -> tuple[list[dict], float] | None:
    """จับเวลาให้ "เนื้อจริง" ด้วยเส้นเวลาชุดใดก็ได้ที่มี word timing

    ใช้ได้ทั้ง auto-caption ของ YouTube และผลถอดเสียงของ whisper — ตัวหนังสือที่แสดง
    ยังเป็นของคนพิมพ์เสมอ เส้นเวลาเป็นแค่ไม้บรรทัดบอกว่าแต่ละบรรทัดร้องตอนไหน
    คืน None เมื่อจับเวลาแล้วไม่ลง (align_ok ไม่ผ่าน) ให้ผู้เรียกไปลองเส้นเวลาชุดอื่นต่อ"""
    chunks = make_chunks([{"start": words[0]["start"], "end": words[-1]["end"],
                           "text": "", "words": words}])
    anchors = align(chunks, src_lines, duration)
    starts = timings_for_lines(src_lines, anchors, duration)
    durs = []
    for i, st in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else (duration if duration > st else st + 6.0)
        durs.append(LS.line_dur(st, nxt))
    covered = {a["line"] for a in anchors}
    tot = sum(len(norm_chars(l)) for l in src_lines)
    cov = 100.0 * sum(len(norm_chars(l)) for i, l in enumerate(src_lines)
                      if i in covered) / tot if tot else 0.0
    if not align_ok(starts, durs, cov, duration):
        return None
    return [{"t": t, "d": d_, "x": x} for t, d_, x in zip(starts, durs, src_lines)], cov


def process(vid: str, no_asr: bool = False) -> bool:
    """คืน True ถ้ายังต้องถอดเสียงต่อ (เรียกด้วย --no-asr แล้วแหล่งที่ไม่ใช้ GPU หมดก่อน)

    แหล่ง 1-3 (ไฟล์ผู้ใช้ / ซับ YouTube / lrclib) ไม่แตะ GPU และไม่ต้องใช้ vocals เลย
    แยกให้รันก่อนได้ = 2 ใน 3 ของคลังได้เนื้อภายในไม่กี่วินาที โดยไม่ต้องรอคิว demucs"""
    # หาโฟลเดอร์จริง
    folder = next(
        (cand for cand in DL.iterdir()
         if cand.is_dir() and not cand.name.startswith(".") and vid_of(cand.name) == vid),
        None,
    )
    if folder is None:
        print(f"[skip] {vid} หาโฟลเดอร์ไม่เจอ")
        return False

    duration = song_duration(folder)
    try:
        info = json.loads((folder / "info.json").read_text("utf-8"))
    except Exception:
        info = {}
    audio = folder / "vocals.m4a"
    if not audio.is_file():
        audio = folder / "audio.m4a"
    # ภาษาของเพลงก่อนทุกอย่าง — ไม่รู้จากชื่อ/แทร็ก ASR ค่อยให้ whisper ฟัง (server มักทำไว้ให้แล้วใน lang.json)
    lang, lang_by = LS.song_lang(folder, info, detect=(lambda: detect_lang(audio)) if audio.is_file() and not no_asr else None,
                                 lrclib=True)
    if lang != "th":
        print(f"[lang] {vid} {lang} ({lang_by})", flush=True)

    # ---- 0) เนื้อที่แก้ใน Studio (lyrics-in/<vid>.json) — ชนะทุกแหล่ง ------
    lines = from_edit(vid)
    if lines:
        write_out(folder, vid, lines, duration, "manual-edit", "PU KARAOKE Studio",
                  time_src="self")
        return False

    # ---- 1) ผู้ใช้วางไฟล์เอง ----------------------------------------------
    lines = from_manual(vid, duration)
    if lines:
        write_out(folder, vid, lines, duration, "manual-lrc", "ไฟล์ผู้ใช้ (lyrics-in/*.lrc)")
        return False
    src_lines, text_src = read_lines(vid, folder, lang)
    manual_text = text_src == "manual-txt"        # .txt ที่ผู้ใช้วางเอง -> ข้ามแหล่งอื่น ไปจับเวลาเลย

    # ---- 2) ซับจริงของ YouTube — เฉพาะภาษาของเพลง (ซับภาษาอื่นคือคำแปล ร้องตามไม่ได้) ----
    sub = folder / f"sub.{lang}.vtt"
    if not manual_text and sub.is_file():
        lines = LS.from_vtt(sub, duration, lang)
        if lines:
            write_out(folder, vid, lines, duration, "yt-sub", f"youtube subtitle ({lang})")
            return False

    # ---- 3) lrclib.net ----------------------------------------------------
    j = info
    if not manual_text:
        got = LS.from_lrclib(j.get("title") or folder.name, j.get("uploader") or "",
                             duration, "\n".join(src_lines), j.get("description") or "")
        if got:
            lines, who = got
            write_out(folder, vid, lines, duration, "lrclib", "lrclib.net synced", note=who)
            return False

    # ---- 4) auto-caption ของ YouTube (ASR ของ Google) ---------------------
    # ไม่แตะ GPU จึงต้องอยู่ "ก่อน" ประตู --no-asr ไม่งั้นเพลงที่มี auto-caption
    # จะยังเข้าคิวแยกเสียง+ถอดเสียงเหมือนเดิมทั้งที่ไม่จำเป็น
    # อยู่ "หลัง" lrclib เพราะ lrclib คือเนื้อที่คนพิมพ์ + เวลาที่คนจับ แม่นกว่าเสมอ
    auto = folder / f"auto.{lang}.vtt"
    auto_words = LS.words_from_auto_vtt(auto, lang) if auto.is_file() else None
    if auto_words and not manual_text:
        if not src_lines:
            # ยังไม่มีเนื้อ -> ลอง lrclib แบบผ่อนเกณฑ์ โดยใช้ "คำที่ YouTube ถอดจากคลิปนี้"
            # เป็นตัวยืนยันว่าใช่เพลงเดียวกัน = ได้เนื้อที่ "คนพิมพ์" โดยไม่ต้องแตะ GPU
            got = LS.from_lrclib_text(j.get("title") or folder.name, j.get("uploader") or "",
                                      j.get("description") or "", auto_text(auto_words))
            if got:
                src_lines, who = got
                text_src = "lrclib-plain"
                print(f"[lrclib-plain] {vid} <- {who} (ยืนยันด้วย auto-caption)", flush=True)
        if src_lines:
            # มีเนื้อจริงแล้ว -> auto-caption เป็นแค่ "เส้นเวลา"
            # ตัวหนังสือของคนพิมพ์ถูกกว่าของเครื่องถอดเสมอ
            got = time_with(src_lines, auto_words, duration)
            if got:
                lines, cov = got
                write_out(folder, vid, lines, duration, text_src,
                          "youtube auto-caption alignment",
                          note=f"{len(auto_words)} คำ", cov=cov, time_src="auto-cap")
                return False
            # จับเวลาไม่ลง -> ปล่อยตกไปให้ whisper จับเวลาให้เนื้อจริงแทน
            # ห้ามถอยไปใช้ตัวหนังสือของเครื่อง เพราะเนื้อที่คนพิมพ์ดีกว่าเสมอ
        else:
            # ไม่มีเนื้อจากแหล่งไหนเลยจริง ๆ -> ตัวหนังสือของ auto-caption "คือ" เนื้อ
            lines = lines_from_words(auto_words, duration)
            if lines:
                write_out(folder, vid, lines, duration, "yt-auto",
                          "youtube auto-caption (th ASR)", time_src="self")
                return False

    # ---- 5) ถอดเสียงเอง แล้ว align กับเนื้อจาก description ------------------
    if no_asr:
        print(f"[need-asr] {vid} แหล่งที่ไม่ใช้ GPU หมดแล้ว ต้องถอดเสียงต่อ", flush=True)
        return True
    if not audio.is_file():
        print(f"[skip] {vid} ไม่มีเสียงให้ถอด")
        _no_lyrics(folder, vid, "ไม่มีเสียงให้ถอด")
        return False
    # เลือกโมเดลตาม "บทบาทของตัวหนังสือ": มีเนื้อจริงแล้ว -> ผลถอดเป็นแค่เส้นเวลา
    # ไม่มีเนื้อเลย -> ตัวที่ถอดได้จะถูกใช้เป็นคำค้น lrclib ต่อ ต้องเอาตัวแม่น
    model = MODEL if src_lines else ACCURATE_MODEL
    data = get_segments(vid, audio, model, lang)
    if not src_lines:
        # ลอง lrclib อีกรอบแบบผ่อนเกณฑ์ โดยใช้ "คำที่ถอดจากเสียงร้องของคลิปนี้เอง"
        # เป็นตัวยืนยันว่าใช่เพลงเดียวกัน แทนการเทียบความยาวเพลง
        asr_text = " ".join(sg.get("text") or "" for sg in data["segs"])
        got = LS.from_lrclib_text(j.get("title") or folder.name, j.get("uploader") or "",
                                  j.get("description") or "", asr_text)
        if got:
            src_lines, who = got
            text_src = "lrclib-plain"
            print(f"[lrclib-plain] {vid} <- {who}", flush=True)
    if not src_lines:
        # หมดทุกแหล่งแล้ว — ของเดิมจะเอาคำที่ whisper ถอดได้มาเป็นเนื้อเลย
        # แต่เนื้อที่เครื่องเดาเองอ่านแล้วไม่เป็นภาษา จึงเลิกทำ ขึ้นว่าไม่มีเนื้อแทน
        print(f"[skip] {vid} ไม่มีเนื้อจากแหล่งไหนเลย (วางไฟล์เองได้ที่ lyrics-in/{vid}.txt)")
        _no_lyrics(folder, vid, "ลองครบทุกแหล่งแล้วไม่เจอเนื้อ")
        return False

    words = [w for sg in data["segs"] for w in (sg.get("words") or [])
             if w.get("start") is not None]
    if duration <= 1.0:
        duration = float(data.get("duration") or 0.0)
    if duration <= 1.0 and data["segs"]:
        duration = float(data["segs"][-1]["end"])
    got = time_with(src_lines, words, duration) if words else None
    if not got:
        # เนื้อจาก lrclib แบบไม่มีเวลาเป็นของ "เพลงต้นฉบับ" ซึ่งอาจยาวไม่เท่าคลิปนี้
        # จับเวลาไม่ลง = แสดงไปก็ผิดจังหวะทั้งเพลง ขึ้นว่าไม่มีเนื้อดีกว่า
        print(f"[skip] {vid} [{text_src}] จับเวลาไม่ลง", flush=True)
        _no_lyrics(folder, vid, f"มีเนื้อจาก {text_src} แต่จับเวลาไม่ลง")
        return False
    lines, cov = got
    write_out(folder, vid, lines, duration, text_src,
              f"mlx-whisper/{model_tag(model)} + lyrics alignment",
              note=f"{len(src_lines)} เส้น", cov=cov, time_src="asr")
    return False


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--detect-lang"]:
        # server เรียกตรวจภาษาเป็น subprocess (โมเดล whisper ไม่ค้างในโปรเซสหลัก) — รับ path ไฟล์เสียงเต็ม
        # ไม่รับ videoId เพราะ vid ขึ้นต้นด้วย - ได้ / พิมพ์ JSON บรรทัดสุดท้ายของ stdout (progress ของ HF ไป stderr)
        audio = Path(args[1]) if len(args) > 1 else None
        if audio is None or not audio.is_file():
            print("ไม่มีไฟล์เสียง", file=sys.stderr)
            sys.exit(2)
        r = detect_lang(audio)
        print(json.dumps({"lang": r[0], "prob": r[1]} if r else {}), flush=True)
        return
    skip_done = "--skip-done" in args          # เติมเฉพาะเพลงที่ยังไม่มีเนื้อ
    no_asr = "--no-asr" in args                # เฉพาะแหล่งที่ไม่ใช้ GPU -> ออกด้วย NEED_ASR ถ้ายังไม่พอ
    # ห้ามคัดด้วย startswith("-") — videoId ของ YouTube ขึ้นต้นด้วย - ได้ (เช่น -IkfnFeojFY)
    # ถ้าพลาดตรงนี้ สั่งเพลงเดียวจะกลายเป็นไล่ทำใหม่ทับทั้งคลัง
    only = [a for a in args if a not in FLAGS] or None
    t0 = time.monotonic()
    need_asr = False
    for d in sorted(DL.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        vid = vid_of(d.name)
        if only and vid not in only:
            continue
        # เฟสที่ไม่ใช้ GPU ขอแค่ metadata — เพลงที่วิดีโอยังโหลดไม่เสร็จก็หาเนื้อไปพลางได้
        # ส่วนเฟสถอดเสียงขอแค่ไฟล์เสียง (video.mp4 มาทีหลัง audio.m4a เสมอหลังทำ audio-first
        # ถ้าไปบังคับว่าต้องมี video.mp4 จะข้ามเพลงแบบเงียบ ๆ ทั้งกระดาน)
        if no_asr:
            if not (d / "info.json").is_file() and not next(d.glob("*.info.json"), None):
                continue
        elif not (d / "audio.m4a").is_file():
            continue
        if skip_done and (d / "lyrics.json").is_file():
            continue
        try:
            need_asr = process(vid, no_asr=no_asr) or need_asr
        except Exception as e:
            print(f"[ERR] {vid}: {type(e).__name__}: {e}", flush=True)
    print(f"--- เสร็จ {time.monotonic()-t0:.0f}s ---", flush=True)
    # NEED_ASR ต้องชนะเสมอ: งานยังไม่จบ ห้ามรายงานว่า "ไม่มีเนื้อ" ทั้งที่ยังไม่ได้ลองถอดเสียง
    # (เฟส --no-asr จึงคืนได้แค่ 0 หรือ 3 เท่านั้น เพราะ from_lrclib_text ต้องใช้คำที่ถอดได้
    #  เป็นคำค้น — ตอนนั้นยังไม่รู้ว่า lrclib-plain จะเจอหรือไม่)
    if need_asr:
        sys.exit(NEED_ASR)
    if _NOLYR:
        sys.exit(NO_LYRICS)


if __name__ == "__main__":
    main()