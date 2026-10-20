# คู่มือใช้ PU KARAOKE บน Linux และ Windows

PU KARAOKE สร้างและใช้งานจริงบน **MacBook Apple Silicon** ส่วนใหญ่ของโค้ดเป็น Python/HTML ธรรมดาที่รันได้ทุกระบบ แต่มีบางส่วนผูกกับ Mac คู่มือนี้บอกว่า**ส่วนไหน**ผูกกับ Mac, **ทำไม**, และ**ต้องแก้อย่างไร** ให้คนหรือ AI ที่รับงานต่อทำตามได้ทีละขั้น

> สถานะ: ณ วันที่เขียน (ต.ค. 2026) ยังไม่มีใครรันบน Linux/Windows จริง ทุกอย่างด้านล่างวิเคราะห์จากโค้ด ถ้าทำสำเร็จแล้วช่วยอัปเดตไฟล์นี้ด้วย

---

## สรุปสั้น: ควรเลือกทางไหน

| เครื่อง | ทางที่แนะนำ | ความเร็ว (เตรียมเพลงใหม่ 1 เพลง) | แก้โค้ด |
|---|---|---|---|
| Mac Apple Silicon | ใช้ตามเดิม | ~30–60 วิ | ไม่ต้อง |
| Linux + NVIDIA GPU (VRAM ≥ 6 GB) | Linux native | ~30–60 วิ | 3 จุด (ข้อ A–C) |
| Windows + NVIDIA GPU | **WSL2 + Ubuntu** แล้วทำแบบ Linux | ~30–60 วิ | 3 จุด + ตั้งค่าเครือข่าย |
| Windows/Linux ไม่มี GPU | แบบเดียวกัน แต่ใช้ CPU | ~3–6 นาที | 3 จุด + ใช้โมเดลเล็ก |
| Mac Intel | ใช้ CPU (เหมือนไม่มี GPU) | ~3–6 นาที | ข้อ A |

สเปกขั้นต่ำ: RAM 16 GB, ดิสก์ว่าง ~20 GB สำหรับโมเดลและแพ็กเกจ (บวกพื้นที่เพลง ~30–50 MB ต่อเพลง)

---

## ส่วนที่ผูกกับ Mac

| # | ส่วน | ไฟล์ / ฟังก์ชัน | บน Mac | บน Linux/Windows | ต้องทำ |
|---|---|---|---|---|---|
| A | ถอดเสียง Whisper | `scripts/gen_lyrics.py`: `_asr()`, `detect_lang()` | `mlx-whisper` (Apple Silicon เท่านั้น) | **ติดตั้งไม่ได้** ไม่มีตัวถอดเสียง | เพิ่ม `faster-whisper` |
| B | แยกเสียง Demucs | `server.py`: `_separate_one()` บรรทัด `devs = … ["mps", "cpu"]` | GPU ผ่าน `mps` | ไม่มี `mps` → ตกไป `cpu` เสมอ | เพิ่ม `cuda` |
| C | จับเวลาละเอียด (FA) | `scripts/fa_align.py`: `_load_model()` และ `torch.mps.empty_cache()` ในโหมด `--serve` | `mps` | ตกไป `cpu` | เพิ่ม `cuda` |
| D | OCR อ่านเนื้อในคลิป | `scripts/ocr_lyrics.py` + `scripts/kara_ocr.swift` (Apple Vision) | ทำงาน | ปิดเองอยู่แล้ว (`_ocr_ensure` เช็ก `sys.platform != "darwin"`) | ไม่ต้องทำ (เสียแค่แหล่งเนื้อจาก Lyric Video) |
| E | ล็อกอิน YouTube | `server.py`: `KARA_YT_COOKIES` (`_yt_ck_load`) | อ่านคุกกี้ Chrome ผ่าน Keychain | Windows: Chrome ≥ 127 เข้ารหัสแบบ app-bound ทำให้ yt-dlp อ่านไม่ได้ | ใช้ `firefox` หรือ `none` |
| F | ปุ่มดับเบิลคลิก | `player.command`, `stop.command`, `cloudflare.command` | bash + `lsof` + `osascript` + path Chrome ของ Mac + Homebrew | Linux: ใช้ได้บางส่วน / Windows: ใช้ไม่ได้ | ดูหัวข้อ "สคริปต์เปิด-ปิด" |
| G | `run.sh` | `.venv/bin/python` | ได้ | Linux ได้ / Windows native ต้องใช้ `.venv\Scripts\python.exe` | Windows native: เขียน `run.ps1` |
| H | IP ใน QR | `server.py`: `lan_ip()` | IP WiFi ของ Mac | WSL2 ได้ IP ภายใน (172.x) มือถือเข้าไม่ได้ | ตั้ง `publicUrl` หรือ mirrored networking |

ส่วนอื่นข้ามระบบได้อยู่แล้ว: FastAPI/uvicorn, yt-dlp, ffmpeg (หาผ่าน `shutil.which`), `nice` (เช็กก่อนใช้), การฆ่า subprocess (`Popen.kill()`), path ทั้งหมดใช้ `pathlib`, หน้าเว็บทั้งหมดเป็น HTML/JS ล้วน

---

## ขั้นตอน: Linux (Ubuntu 24.04) + NVIDIA

### 1. ติดตั้งระบบ

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip ffmpeg git curl
# node: yt-dlp ใช้แก้โจทย์ JavaScript ของ YouTube ตอนโหลดแบบล็อกอิน
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
# ไดรเวอร์ NVIDIA (ถ้ายังไม่มี) แล้วรีบูต
sudo ubuntu-drivers install && sudo reboot
nvidia-smi        # ต้องเห็นการ์ดจอ
```

### 2. โหลดโค้ดและติดตั้ง Python packages

`requirements.txt` มี `mlx-whisper` ซึ่งติดตั้งบน Linux ไม่ได้ ให้ติดตั้งเองแทน `./run.sh` ครั้งแรก:

```bash
git clone https://github.com/promxxpurich/PU-Karaoke.git && cd PU-Karaoke
python3.12 -m venv .venv
# torch แบบ CUDA ก่อน (ดูเวอร์ชัน CUDA ที่ตรงกับไดรเวอร์ที่ https://pytorch.org)
.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
# ที่เหลือ ยกเว้น mlx-whisper + ตัวถอดเสียงแทน
grep -v mlx-whisper requirements.txt > /tmp/req-linux.txt
.venv/bin/pip install -r /tmp/req-linux.txt faster-whisper
```

แนะนำให้แยกไฟล์ถาวรเป็น `requirements-linux.txt` (หรือใส่ marker `mlx-whisper; sys_platform == "darwin"` ใน `requirements.txt`) แล้วแก้ `run.sh` ให้เลือกตามระบบ

### 3. แก้โค้ด 3 จุด

#### A. ตัวถอดเสียง (`scripts/gen_lyrics.py`)

โค้ดที่เหลือของไฟล์ใช้ผลถอดเสียงในรูปแบบของ openai-whisper/mlx-whisper:
`{"text": str, "language": str, "segments": [{"start", "end", "text", "words": [{"word", "start", "end", "probability"}]}]}`
เลยต้องแปลงผลของ faster-whisper ให้เป็นรูปเดียวกัน ตัวอย่างแนวทาง:

```python
ENGINE = os.environ.get("KARA_ASR_ENGINE") or ("mlx" if sys.platform == "darwin" else "faster")
_FW = {}

def _fw_model(model: str):
    from faster_whisper import WhisperModel
    import torch
    name = os.environ.get("KARA_FW_MODEL", "large-v3-turbo")   # ชื่อ mlx-community/* ใช้ไม่ได้กับ faster-whisper
    if name not in _FW:
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _FW[name] = WhisperModel(name, device=dev, compute_type="float16" if dev == "cuda" else "int8")
    return _FW[name]

def _asr(audio, model, lang="th", **kw):
    if ENGINE == "mlx":
        ...  # โค้ดเดิม
    m = _fw_model(model)
    segs, info = m.transcribe(str(audio), language=lang or "th", word_timestamps=True,
                              condition_on_previous_text=kw.get("condition_on_previous_text", True))
    out = []
    for s in segs:
        out.append({"start": s.start, "end": s.end, "text": s.text,
                    "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                              for w in (s.words or [])]})
    return {"text": "".join(s["text"] for s in out), "language": info.language, "segments": out}
```

`detect_lang()` ใช้ส่วนภายในของ mlx (`load_models`, `decoding.detect_language`) ให้เขียนใหม่ด้วย `WhisperModel.detect_language()` หรือเรียก `transcribe()` กับเสียง 30 วินาทีแล้วอ่าน `info.language` / `info.language_probability`

ข้อควรระวัง:
- ชื่อแคชถอดเสียง (`segment_cache_path`) ขึ้นกับ `MODEL_TAG` ถ้าเปลี่ยนโมเดล แคชเก่าจะไม่ถูกใช้ (ตั้งใจ)
- `server.py` แสดงชื่อโมเดลจาก `KARA_ASR_MODEL` ใน `/api/health` ปรับข้อความได้ตามสะดวก
- ระวังเรื่อง timestamp ของ faster-whisper กับ VAD: **อย่าเปิด `vad_filter`** เพราะจะตัดช่วงดนตรีแล้วเวลาเลื่อน

#### B. Demucs ใช้ CUDA (`server.py` → `_separate_one`)

```python
# เดิม
devs = [_sep_device] if _sep_device else ["mps", "cpu"]
# ใหม่
import torch
gpu = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else None)
devs = [_sep_device] if _sep_device else ([gpu] if gpu else []) + ["cpu"]
```

และในลูปเดียวกันที่จำ device (`if dev == "mps": _sep_device = dev`) ให้จำ `cuda` ด้วย (`if dev in ("mps", "cuda")`) **อย่าจำ `cpu`** (เคยเป็นบั๊กทำให้ทุกเพลงแยกบน CPU จนรีสตาร์ท)

> หมายเหตุ: import torch ในโปรเซสหลักใช้ RAM เพิ่ม ~300 MB ถ้าไม่อยากได้ ให้เช็กครั้งเดียวด้วย subprocess `python -c "import torch;print(torch.cuda.is_available())"` แล้วเก็บผลไว้

#### C. FA ใช้ CUDA (`scripts/fa_align.py`)

```python
# _load_model()
dev = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
# ในโหมด --serve หลังคำนวณ
if torch.backends.mps.is_available():
    torch.mps.empty_cache()
elif torch.cuda.is_available():
    torch.cuda.empty_cache()
```

### 4. โหลดโมเดล

```bash
HF_HOME=.cache/hf HF_HUB_CACHE=.cache/hf/hub .venv/bin/python -c "
from huggingface_hub import snapshot_download as d
for m in ['airesearch/wav2vec2-large-xlsr-53-th', 'facebook/wav2vec2-large-960h-lv60-self']:
    d(m)"
# faster-whisper โหลดโมเดลเองตอนใช้ครั้งแรก
```

### 5. รัน

```bash
KARA_YT_COOKIES=none .venv/bin/python -u server.py
```

เปิดพอร์ตใน firewall ถ้ามี: `sudo ufw allow 8080/tcp`

### 6. คุกกี้ YouTube บน Linux

ถ้าโดน "Sign in to confirm you're not a bot":
- ล็อกอิน YouTube ใน **Firefox** แล้วตั้ง `KARA_YT_COOKIES=firefox` (ไม่ต้องใช้ keyring)
- Chrome บน Linux ต้องมี GNOME Keyring/KWallet ทำงานอยู่ ใช้ `KARA_YT_COOKIES=chrome` ได้ถ้ามีหน้าจอ desktop

---

## ขั้นตอน: Windows

### ทางที่แนะนำ: WSL2 (Ubuntu)

ได้ Linux เต็มตัวในเครื่อง Windows และใช้ GPU NVIDIA ได้

1. เปิด PowerShell แบบ Administrator:
   ```powershell
   wsl --install -d Ubuntu-24.04
   ```
   รีบูต แล้วตั้งชื่อผู้ใช้/รหัสผ่าน Ubuntu
2. ติดตั้งไดรเวอร์ NVIDIA **บน Windows** ตามปกติ (ไม่ต้องลงใน Ubuntu) แล้วใน Ubuntu เช็ก `nvidia-smi`
3. ทำตาม "ขั้นตอน: Linux" ข้อ 1–5 ทั้งหมดใน Ubuntu (ข้ามการลงไดรเวอร์)
4. **เก็บโปรเจกต์ไว้ใน Linux** (`~/PU-Karaoke`) ไม่ใช่ใน `/mnt/c/...` เพราะอ่านเขียนไฟล์ข้ามระบบช้ามาก
5. **ให้มือถือเข้าได้** (สำคัญ) WSL2 ใช้เครือข่ายภายในแยก เลือกวิธีใดวิธีหนึ่ง:
   - **Mirrored networking** (Windows 11 22H2+): สร้างไฟล์ `%UserProfile%\.wslconfig`
     ```ini
     [wsl2]
     networkingMode=mirrored
     ```
     แล้ว `wsl --shutdown` และเปิดใหม่ WSL จะใช้ IP เดียวกับ Windows
   - **Port proxy** (Windows 10): ใน PowerShell Administrator
     ```powershell
     $ip = (wsl hostname -I).Split()[0]
     netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=$ip
     New-NetFirewallRule -DisplayName "PU KARAOKE" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
     ```
     IP ของ WSL เปลี่ยนทุกครั้งที่รีบูต ต้องสั่งใหม่
6. **QR บนจอชี้ IP ผิด** (ถ้าไม่ได้ใช้ mirrored): ใส่ IP WiFi ของ Windows ลง `.studio.json`
   ```json
   "publicUrl": "http://192.168.1.50:8080"
   ```
   (ดู IP ด้วย `ipconfig` ใน Windows) เซิร์ฟเวอร์อ่านค่านี้ทันทีโดยไม่ต้องรีสตาร์ท
7. **จอหลัก:** เปิด Chrome บน Windows ไปที่ `http://localhost:8080/` (กด F11 เต็มจอ) หรือใช้ลิงก์ `/tv/<รหัส>` จากเครื่องไหนก็ได้

### ทางเลือก: Windows native (ไม่ผ่าน WSL)

ทำได้ แต่ต้องทำเพิ่มจาก Linux:
- ติดตั้ง Python 3.12 จาก python.org, `winget install Gyan.FFmpeg`, `winget install OpenJS.NodeJS`
- สร้าง `run.ps1`:
  ```powershell
  Set-Location $PSScriptRoot
  if (-not (Test-Path .venv)) {
    py -3.12 -m venv .venv
    .\.venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
    (Get-Content requirements.txt) -notmatch 'mlx-whisper' | Set-Content req-win.txt
    .\.venv\Scripts\pip install -r req-win.txt faster-whisper
  }
  $env:KARA_YT_COOKIES = "firefox"
  .\.venv\Scripts\python -u server.py
  ```
- แก้ A–C เหมือน Linux
- **คุกกี้:** Chrome บน Windows อ่านไม่ได้ (app-bound encryption) ใช้ `firefox` หรือ `none`
- ชื่อโฟลเดอร์เพลงปลอดภัยกับ Windows แล้ว (`server.py` `_safe_name` แทน `/ \ : * ? " < > |` ด้วย `-` และตัดจุด/ช่องว่างท้ายชื่อ) แต่ path รวมอาจยาวเกิน 260 ตัวอักษร ให้เปิด Long Paths: `reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f`
- Windows Defender อาจสแกนไฟล์วิดีโอทุกไฟล์ ทำให้ช้า เพิ่มโฟลเดอร์โปรเจกต์ใน Exclusions ได้

---

## สคริปต์เปิด-ปิด (`.command`)

| ไฟล์ | ทำอะไร | Linux | Windows |
|---|---|---|---|
| `player.command` | เปิด Chrome เต็มจอเป็นจอหลัก (+ Cloudflare) | แก้ `CHROME=` เป็น `$(command -v google-chrome \|\| command -v chromium)` และลบบรรทัด `osascript` | เปิด Chrome เองแล้วกด F11 หรือทำ shortcut `chrome.exe --kiosk http://localhost:8080/` |
| `stop.command` | ปิดเซิร์ฟเวอร์เฉพาะของโปรเจกต์นี้ | ใช้ได้ถ้ามี `lsof` (`sudo apt install lsof`); `pgrep -x Python` (ตัวใหญ่) บน Linux เป็น `python3` | ปิดหน้าต่าง PowerShell / Ctrl+C |
| `cloudflare.command` | ลิงก์นอกบ้าน | ติดตั้ง `cloudflared` จาก [pkg.cloudflare.com](https://pkg.cloudflare.com) แทน `brew` | `winget install Cloudflare.cloudflared` แล้วสั่ง `cloudflared tunnel --url http://localhost:8080` เอง |

บน Linux เปลี่ยนชื่อเป็น `.sh` แล้ว `chmod +x` ได้เลย

---

## เครื่องที่ไม่มี GPU

ใช้ได้ทุกฟีเจอร์ แค่ช้าลง ปรับให้เบาลง:
- `KARA_FW_MODEL=small` หรือ `medium` (ตัวถอดเสียงเล็กลง ความแม่นลดลงบ้าง)
- `KARA_FA_IDLE=600` ให้ปิดโมเดล FA หลังว่าง 10 นาที คืน RAM ~2.6 GB
- `KARA_WARM=off` ไม่โหลดโมเดลล่วงหน้า
- ให้เวลาเพลงเตรียมตัว: เพิ่มคิวล่วงหน้า 2–3 เพลง ระหว่างนี้ร้องกับวิดีโอต้นฉบับได้

---

## เช็กลิสต์หลังย้ายระบบ

1. `.venv/bin/python -m py_compile server.py scripts/*.py` ผ่าน
2. รันเซิร์ฟเวอร์ เปิด `/`, `/r`, `/studio` ขึ้นครบ
3. `/api/health` ไม่มี error สำคัญ
4. ค้นเพลง 1 เพลงจากรีโมทแล้วเพิ่มคิว ดู log:
   - `[sep] … (device=cuda)` (หรือ `mps`) ไม่ใช่ `cpu`
   - `[asr] … s (…, th)` มีเวลาออกมา
   - มีไฟล์ `lyrics.json` และ `lyrics.words.json` ในโฟลเดอร์เพลง
5. เปิดจอทีวี เนื้อไล่สีตามเสียง
6. รันชุดทดสอบจอทีวี: `.venv/bin/python scripts/test_tv_lyrics.py` (ต้องแก้ `CHROME =` ในไฟล์ให้ชี้ Chrome ของระบบนั้นก่อน)

ทำเสร็จแล้วอย่าลืมอัปเดต badge ใน README และตารางสรุปด้านบนของไฟล์นี้
