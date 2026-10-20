# สถาปัตยกรรม PU KARAOKE (สำหรับนักพัฒนา)

ภาพรวมสั้น ๆ ว่าระบบประกอบด้วยอะไร ถ้าจะหาว่าเรื่องไหนอยู่บรรทัดไหน ให้ใช้แผนที่โค้ด:

```bash
python3 .claude/skills/kara-edit/kmap.py topics          # รายชื่อหัวข้อทั้งหมด (~90)
python3 .claude/skills/kara-edit/kmap.py find คิว รีโมท   # ค้นด้วยคำไทยหรืออังกฤษ ได้ไฟล์:บรรทัด + ข้อควรระวัง
```

## ส่วนประกอบ

| ส่วน | ไฟล์ | หน้าที่ |
|---|---|---|
| เซิร์ฟเวอร์ | `server.py` (~6.5k บรรทัด, FastAPI) | เสิร์ฟหน้าเว็บ, REST API, WebSocket `/ws`, สถานะห้อง (คิว/เพลงที่เล่น/เสียง/คีย์), งานเบื้องหลังทั้งหมด |
| รีโมท | `static/remote.html` | หน้า `/r` ของแขก: ค้นหา, คิว, ตั้งค่าเสียง, PU Match, แจ้งซับไม่ตรง |
| จอทีวี | `static/player.html` | หน้า `/` และ `/tv/<รหัส>`: เล่นวิดีโอ, ผสมเสียงสเต็ม (Web Audio), วาดเนื้อ, เฟดเปลี่ยนเพลง |
| Studio | `static/studio.html` | หน้า `/studio` (PIN): แก้เนื้อ/เวลา, ซ่อม, ตั้งค่าจอ, ตัดต่อและคอมโบ |
| MV จากเนื้อ | `static/mv/` + `scripts/mv_*` | วาดฉากประกอบจากเนื้อเพลงแทนวิดีโอ (เปิด/ปิดได้) |
| ไปป์ไลน์เนื้อ | `scripts/gen_lyrics.py`, `lyrics_sources.py`, `lyrics_more.py`, `fetch_subs.py` | หาเนื้อจากทุกแหล่ง + Whisper |
| จับเวลา | `scripts/fa_align.py` (wav2vec2), `lyrics_refine.py`, `vocal_activity.py` | เวลารายตัวอักษร, ซ่อมเวลา, แผนที่เสียงร้อง |
| ตรวจคุณภาพ | `lyrics_check.py`, `scripts/verify_lyrics.py`, `scripts/lyrics_conf.py` | ป้าย ✅/⚠️, ตรวจและซ่อมเนื้อ |
| OCR (Mac) | `scripts/ocr_lyrics.py` + `kara_ocr.swift` | อ่านเนื้อจากตัวหนังสือในคลิป Lyric Video |

## การสื่อสาร

- ทุกหน้าเปิด WebSocket `/ws` ไปที่เซิร์ฟเวอร์ เซิร์ฟเวอร์ broadcast สถานะห้องทั้งก้อน (`room.state()`) ทุกครั้งที่มีอะไรเปลี่ยน
- จอทีวีเป็นตัวเล่นจริง ส่งตำแหน่งเพลงกลับมา เซิร์ฟเวอร์ใช้คำนวณเวลาให้ทุกจอตรงกัน
- จอหลักเปิดได้จากเครื่องที่รันเท่านั้น (`/`) หรือจากเครื่องอื่นผ่าน `/tv/<รหัส>` (รหัสใน `.studio.json`)
- Studio ใช้ REST `/api/studio/*` (ต้องล็อกอิน PIN ยกเว้นเครื่องที่รัน) + WebSocket สำหรับอัปเดตสด

## งานเบื้องหลัง

เมื่อมีเพลงเข้าคิว เซิร์ฟเวอร์ทำงานต่อไปนี้เป็นลำดับ แต่ละขั้นเป็น **subprocess** แยก (แก้สคริปต์แล้วงานถัดไปได้ผลทันที):

1. **download** (yt-dlp) → `video.mp4`, `audio.m4a`, `info.json`, `cover.jpg`, ซับ `.vtt`
2. **sep** (demucs htdemucs `--two-stems vocals`) → `vocals.m4a`, `no_vocals.m4a`
3. **lyr** (`gen_lyrics.py`) ไล่แหล่ง: `lyrics-in/<vid>.json` → `.lrc` → ซับ YouTube → lrclib → YouTube Music/JOOX → auto-caption → Whisper → `lyrics.json`
4. **best** เทียบเนื้อทุกแหล่ง เลือกตัวที่ตรงเสียงร้องที่สุด → `lyrics.best.json`
5. **words** (`fa_align.py`) เวลารายตัวอักษร → `lyrics.words.json`
6. **verify** ตรวจเวลา → `lyrics.check.json` (ป้าย ✅/⚠️)

ลำดับความสำคัญ: เพลงที่กำลังเล่น > เพลงถัดไปในคิว > เพลงที่เหลือ > เพลงเก่าในคลัง งาน GPU ทำทีละงาน (`_HeavyGate`) และงานของเพลงท้ายคิวถูกหยุดได้ถ้าเพลงที่กำลังจะเล่นยังไม่พร้อม (`_preempt_heavy`)

## ข้อมูลในโฟลเดอร์เพลง `songs/yt/<ชื่อคลิป [videoId]>/`

| ไฟล์ | มาจาก |
|---|---|
| `info.json`, `video.mp4`, `audio.m4a`, `cover.jpg`, `sub.*.vtt`, `auto.*.vtt` | yt-dlp |
| `vocals.m4a`, `no_vocals.m4a`, `vocals.k+N.m4a` | demucs / เปลี่ยนคีย์ |
| `lyrics.json` | เนื้อปัจจุบัน `{v, videoId, lang, src, duration, lines: [{t, d, x}]}` |
| `lyrics.words.json` | เวลารายตัวอักษร (โหมดคาราโอเกะ) |
| `lyrics.offset.json` | เลื่อนเวลาทั้งเพลง (จากรีโมท/Studio) |
| `lyrics.check.json` | ผลตรวจเวลา + รายงานจากแขก |
| `lyrics.best.json`, `lyrics.prev.json`, `lyrics.edits/` | ผลเลือกเนื้อ, ฉบับก่อน, ประวัติแก้ 20 รุ่น |
| `lang.json`, `trim.json`, `mv.json` | ภาษา, จุดตัดต่อ, บท MV |

เนื้อที่แก้เองใน Studio (`src: manual-edit`) ถูกสำรองที่ `lyrics-in/<videoId>.json` ด้วย งานอัตโนมัติจะไม่เขียนทับ

## ไฟล์ตั้งค่าที่ราก

| ไฟล์ | ใน git | เนื้อหา |
|---|---|---|
| `tv.json` | ✅ | หน้าตาจอทีวี (ตั้งจาก Studio แท็บ 📺) |
| `.studio.json` | ❌ | PIN, secret, รหัสจอ `tv`, `publicUrl` |
| `history.json` | ❌ | ประวัติใครร้องอะไร |
| `combos.json` | ❌ | คอมโบเพลง (Studio แท็บ ✂️) |

## การทดสอบ

- `scripts/test_tv_lyrics.py` เปิด server ในโปรเซสที่พอร์ต 8099 + คลังชั่วคราว + headless Chrome ทดสอบว่าเนื้อขึ้นจอทีวีทุกกรณี
- `scripts/test_tv_mv.py` ทดสอบ MV บนจอทีวี
- `scripts/eval_lyrics.py` วัดคุณภาพเนื้อทั้งคลัง (ตั้ง `KARA_FA_NO_COMPUTE=1` ถ้าไม่อยากให้ใช้ GPU)

รายละเอียดอัลกอริทึมเนื้อเพลง (แหล่ง, ระบบเลือกเนื้อ, โหมดคาราโอเกะ, เปลี่ยนคีย์) อยู่ใน [`lyrics-in/README.md`](../lyrics-in/README.md)
