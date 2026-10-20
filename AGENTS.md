# AGENTS.md — คู่มือสำหรับ AI ที่ทำงานกับ PU KARAOKE

ไฟล์นี้สำหรับ AI coding agent ทุกตัว (Claude Code, Codex, Cursor, Copilot ฯลฯ) อ่านก่อนแก้อะไรในโปรเจกต์นี้
ผู้สร้างโปรเจกต์: **Purich Sa** (@promxxpurich) ภาพรวมสำหรับคนอยู่ใน [README.md](README.md)

## ภาษา

- ผู้ใช้หลักเป็นคนไทย: **ตอบ อธิบาย และเขียนแผนเป็นภาษาไทย** ข้อความบนหน้าเว็บทุกจุดเป็นภาษาไทย
- คอมเมนต์ในโค้ดเขียนภาษาไทยเป็นหลัก ให้เขียนตามสไตล์เดิมของไฟล์

## หาโค้ดด้วยแผนที่ (สำคัญที่สุด)

`server.py` ~6,500 บรรทัด, `studio.html` ~2,400, `remote.html` ~1,200, `player.html` ~1,100, `scripts/` ~5,000
**อย่าอ่านทั้งไฟล์** ใช้แผนที่โค้ดแทน:

```bash
python3 .claude/skills/kara-edit/kmap.py status              # เช็กว่า worktree ไม่เก่ากว่าโฟลเดอร์หลัก
python3 .claude/skills/kara-edit/kmap.py find <คำ 1–3 คำ>      # ไทยหรืออังกฤษ ได้ ไฟล์:บรรทัด + ข้อควรระวัง (!)
python3 .claude/skills/kara-edit/kmap.py topics              # หัวข้อทั้งหมด
python3 .claude/skills/kara-edit/kmap.py outline <ไฟล์> [คำ]  # โครงไฟล์
python3 .claude/skills/kara-edit/kmap.py check               # หลังแก้: anchor ในแผนที่ยังหาเจอไหม
```

แล้วอ่านเฉพาะช่วงบรรทัดที่ได้ **อ่านข้อควรระวัง `!` ทุกครั้ง** เรื่องเดียวมักกินหลายไฟล์ (CSS + HTML + JS ในหน้าเดียว, หน้าเว็บ + route ใน server.py)
ถ้าเพิ่มหรือย้ายฟังก์ชัน ให้อัปเดต `.claude/skills/kara-edit/MAP.md` ด้วย (รายละเอียดใน `SKILL.md` โฟลเดอร์เดียวกัน)

## กฎความปลอดภัยของข้อมูลเจ้าของเครื่อง

1. **ห้ามปิดหรือรีสตาร์ทเซิร์ฟเวอร์ที่พอร์ต 8080** เจ้าของเครื่องเปิดเองและอาจกำลังร้องอยู่ แก้เสร็จแล้วให้บอกว่าต้องรีสตาร์ทเอง
   - หน้า HTML อ่านจากดิสก์ทุกครั้ง (รีเฟรชก็เห็น) แต่ `server.py` ต้องรีสตาร์ท
   - สคริปต์ใน `scripts/` ถูกเรียกเป็น subprocess งานถัดไปใช้โค้ดใหม่ทันที → **รักษา CLI / exit code / JSON บรรทัดสุดท้ายให้เข้ากันได้กับ server.py ตัวเก่าที่รันอยู่**
2. **ห้ามแก้เนื้อจริง** ใน `songs/yt/**/lyrics*.json` และ `lyrics-in/*.json` ที่ `src: manual-edit` (เจ้าของแก้มือไว้) งานอัตโนมัติต้องข้ามเนื้อที่คนแก้เอง
3. **ทดสอบบนคลังปลอมเสมอ**: videoId ขึ้นต้น `TEST*`, เซิร์ฟเวอร์ทดสอบพอร์ตอื่น, ตั้ง env ก่อน `import server`:
   `KARA_YT_COOKIES=none KARA_WARM=off KARA_STUDIO_PIN=0000 KARA_SONGS_DIR=… KARA_SEG_DIR=… KARA_LYRICS_IN=… KARA_FA_CACHE=…`
   แล้ว patch `server.SONGS / DL_DIR / THUMB_CACHE / LYRICS_IN / SEG_CACHE / STUDIO_FILE / HISTORY_FILE / TV_FILE / TV_DIR / COMBOS_FILE` และปิด lifespan ดูตัวอย่างครบใน `scripts/test_tv_lyrics.py`
4. **ชื่อไฟล์ทดสอบห้ามมีคำว่า `server.py`** เพราะ `stop.command`/`player.command` ฆ่า python ที่มีคำนี้ในอาร์กิวเมนต์
5. `KARA_YT_COOKIES=none` ทุกครั้งที่ทดสอบ ไม่งั้นจะอ่านคุกกี้ Chrome จริงและเด้งหน้าต่าง Keychain ห้ามเปิดดูข้อมูลคุกกี้เอง
6. อย่ายิงดาวน์โหลด YouTube จริงในการทดสอบ (โดนบล็อก IP ได้)

## การทดสอบ

- แก้ `player.html` หรือการ broadcast → `.venv/bin/python scripts/test_tv_lyrics.py` (headless Chrome, ต้องผ่านทุกข้อ)
- แก้ MV → `.venv/bin/python scripts/test_tv_mv.py`
- แก้ไปป์ไลน์เนื้อ → `KARA_FA_NO_COMPUTE=1 .venv/bin/python scripts/eval_lyrics.py` (ไม่แย่ง GPU) เทียบตัวเลขก่อน/หลัง
- ทดสอบจาก git worktree: worktree ไม่มี `.cache/` ให้ตั้ง `HF_HOME=<โฟลเดอร์หลัก>/.cache/hf` และ `HF_HUB_CACHE=<โฟลเดอร์หลัก>/.cache/hf/hub` ไม่งั้นโมเดลอังกฤษถูกข้ามเงียบ ๆ และตัวเลขผิด
- ระวัง: ชื่อฟังก์ชันระดับบนสุดใน `server.py` ที่ตั้งซ้ำจะถูกตัวหลังทับเงียบ ๆ ให้ grep ก่อนเพิ่มฟังก์ชันใหม่
- หน้าเว็บทดสอบด้วย headless Chrome + CDP ดีกว่า browser pane (pane ที่ซ่อนอยู่ทำให้ `requestAnimationFrame` ไม่ทำงาน)

## หลักการออกแบบที่เจ้าของเลือกไว้ (อย่าย้อนเปลี่ยนโดยไม่ถาม)

- **ทุกอย่างที่เปลี่ยนหน้าตาจอทีวีต้องมีสวิตช์เปิด/ปิด** ใน `tv.json` (`TV_SCHEMA` ใน server.py) + Studio แท็บ 📺 (และรีโมท ⚙️ ถ้าแขกอาจอยากสลับเอง) ค่า "ปิด" ต้องได้หน้าตาเดิมเป๊ะ
- **เครื่องต้องไม่ร้อน**: ห้ามเสนอแปลงไฟล์วิดีโอทั้งคลังด้วย ffmpeg (เช่น AV1 → H.264), คลิปยาวเกิน 10 นาทีไม่แยกเสียง (`SEP_MAX_SEC`), demucs ต้องอยู่บน GPU และห้ามจำ device `cpu`
- **ไม่มีจอที่สอง `/watch`** (เอาออกแล้วตามคำขอ อย่าใส่กลับ)
- **คอมโบ** = จุดตัดที่ตั้งเองล้วน ใช้เสมอ; จุดเริ่ม-จบรายเพลง (`trim.json`) ใช้เฉพาะตอนเปิดโหมด Custom
- **การค้นหา** ซ่อนคลิปที่ไม่ใช่เพลงเสมอ (ยาวเกิน 10 นาที, ไลฟ์, ออกกำลังกาย, ตลก, รีแอค/สอน, สัมภาษณ์) แก้ที่ `_NOT_SONG_RE` / `_is_song_clip` อย่าใส่คำไทยสั้น ๆ ที่ชนชื่อเพลงจริง ("ฮา", "สอน", "แกล้ง")
- **MV จากเนื้อเพลง**: ฉากใหม่เพิ่มใน `static/mv/scenes-*.js` แล้วรัน `node scripts/mv_catalog.js`; สวิตช์ `tv.mv` ปิดเป็นค่าเริ่มต้น

## Git

- Branch หลักคือ `main` งานใหม่ทำใน branch แยกแล้ว merge แบบ `--ff-only`
- **ห้าม commit หรือ push เองถ้าเจ้าของไม่ได้สั่ง**
- งานเสร็จแล้วแต่ยังไม่ได้ merge เข้าโฟลเดอร์ที่เซิร์ฟเวอร์รันอยู่ ให้บอกชัด ๆ ว่า "ยังไม่ขึ้นเซิร์ฟเวอร์จริง" แล้วถามว่าจะ merge ไหม
- ไฟล์ที่ห้ามเข้า git (มีใน `.gitignore` แล้ว): `songs/`, `.cache/`, `.venv/`, `.studio.json`, `history.json`, `combos.json`, `.chrome-player/`

## แพลตฟอร์ม

พัฒนาบน macOS Apple Silicon ใช้ `mlx-whisper` และ GPU ผ่าน `mps` ถ้าต้องทำให้รันบน Linux/Windows ดู [docs/PORTING.md](docs/PORTING.md) ห้ามทำให้ทางของ Mac ช้าลงหรือพัง (เลือกตามระบบด้วย `sys.platform` / `torch.cuda.is_available()`)
