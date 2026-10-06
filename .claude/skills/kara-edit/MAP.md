# แผนที่โค้ด PU KARAOKE

ใช้คู่กับ `kmap.py` ในโฟลเดอร์เดียวกัน: `find <คำ>` → หัวข้อที่ตรง + ไฟล์:บรรทัดปัจจุบันของทุก anchor
anchor = ข้อความในบรรทัดเดียวของไฟล์ (ไม่ใส่เลขบรรทัด เพราะเปลี่ยนทุกครั้งที่แก้)
แก้โค้ดแล้วโครงเปลี่ยน (เพิ่ม/เปลี่ยนชื่อ/ลบ ฟังก์ชัน, section, route) → อัปเดตไฟล์นี้แล้วรัน `kmap.py check`

## ภาพรวม
### ไฟล์หลักของโปรเจกต์ / หน้าไหนอยู่ไฟล์ไหน
คำค้น: ภาพรวม, overview, ไฟล์, โครงสร้าง, structure, หน้าไหน, ไฟล์ไหน
- `server.py` — FastAPI ตัวเดียว: หน้าเว็บทุกหน้า, websocket ห้อง/คิว, API ทั้งหมด, งานเบื้องหลัง (โหลด/แยกเสียง/สร้างเนื้อ/FA/ตรวจเวลา)
- `static/remote.html` — รีโมทมือถือของแขก (/r)
- `static/player.html` — จอทีวี (/ และ /tv/{key})
- `static/studio.html` — Studio หลังบ้าน (/studio มี PIN)
- `lyrics-in/README.md` — คู่มือระบบเนื้อเพลงภาษาไทย (ละเอียดที่สุด อ่านเฉพาะหัวข้อที่เกี่ยว)
! ห้ามอ่านทั้งไฟล์ server.py / studio.html / remote.html / player.html — ใช้ `kmap.py find` หรือ `kmap.py outline <ไฟล์> <คำ>`
! ไม่ต้องอ่าน: songs/ (สื่อ + เนื้อจริง), lyrics-in/*.json (เนื้อที่ผู้ใช้แก้เอง ห้ามทับ), ไฟล์ transcript *.txt ในราก

## รีโมท (static/remote.html — หน้า /r ของแขก)

### โครงหน้า + ล็อกซูม (iOS) + ช่องพิมพ์ 16px
คำค้น: หน้ารีโมท, remote, /r, มือถือแขก, ซูม, zoom, pinch, ซูมเอง, แตะสองที, double tap, iOS, Safari, viewport, ช่องพิมพ์ซูม, 16px, ธีมสี, สีหลัก, CSS variable
- `static/remote.html` `<meta name="viewport"` `// ===== 0. ล็อกซูม` — meta viewport + ดัก gesture/pinch/dblclick/ctrl+ล้อ ใน JS
- `static/remote.html` ` :root{` `input[type=text],input:not([type]){` — ตัวแปรสีหลัก (--accent, --barh, --hdrh) + ช่องพิมพ์ font-size 16px
! แก้ไฟล์นี้แล้วแค่รีโหลดหน้า — server.py อ่าน static/remote.html จากดิสก์ทุกคำขอ (Cache-Control: no-store) ไม่ต้องรีสตาร์ทเซิร์ฟเวอร์
! iOS Safari ไม่สน user-scalable=no ต้องดัก gesture ใน JS · ช่องพิมพ์ทุกช่อง (รวม textarea #repnote) ต้อง ≥16px ไม่งั้น iOS ซูมเข้าเองตอนแตะ

### หัวจอ + สถานะการเชื่อมต่อ (websocket)
คำค้น: หัวจอ, header, โลโก้, เชื่อมต่อแล้ว, กำลังเชื่อมต่อ, หลุด, ต่อใหม่, reconnect, websocket, ws, wss, Cloudflare, ส่งคำสั่ง, send, state, broadcast
- `static/remote.html` ` header{position:sticky` ` header .st{` `id="ststr"` — หัวจอติดบนสุด + ป้ายสถานะ (body.off = จุดกระพริบ หน้าจาง)
- `static/remote.html` `// ===== 11. websocket` `function connect(){` `function onMessage(ev){` `function schedule(st){` `function sendLater(o){` — ต่อ /ws (https → wss), backoff ≤6 วิ, รับ state/history/added, รวมหลาย broadcast เป็นเฟรมเดียว → renderAll, เก็บคำสั่งที่ส่งไม่ได้ไว้ยิงตอนต่อใหม่ (≤8)
! onMessage ต้องดัก type 'history'/'added' ก่อนเขียนทับ S.st · กลับมาที่หน้า (visibilitychange) = ต่อใหม่ทันที ไม่รอ backoff

### ช่องค้นหา (เกาะใต้หัวจอ) + ผลค้นหา / เพลงในเครื่อง
คำค้น: ค้นหา, search, ช่องค้นหา, sticky, เกาะ, ติดด้านบน, เลื่อนจอ, scroll, ผลค้นหา, วางลิงก์, YouTube link, เพลงที่มีอยู่แล้ว, คลัง, archive, กรองเพลง, ล้างคำค้น, เคล็ดลับ, ปิดการฝัง, ค้นหาไม่สำเร็จ, yt-dlp
- `static/remote.html` ` .search{display:flex` ` .search.stuck{` `@media (max-height:500px)` ` .sbox{` ` .tip{` — CSS sticky (top = --hdrh − 1px), พื้นหลังตอนติด (.stuck), แนวนอนจอเตี้ยไม่เกาะ, ไอคอน/ปุ่ม ✕, กล่องเคล็ดลับ
- `static/remote.html` `<div class="search">` `id="q"` `id="reshd"` `id="results"` — HTML ช่องค้นหา / หัวรายการ / รายการผล
- `static/remote.html` `const markStuck = ` `const measureBars = ` `function toResTop(){` — ใส่ .stuck ตอนติด, วัดความสูงหัวจอ/แถบล่างเข้า --hdrh/--barh (ResizeObserver), เลื่อนหัวรายการกลับมาใต้ช่องค้นหา
- `static/remote.html` `async function search(){` `function ytId(s){` `async function loadRecs(){` `function renderRecs(){` `function renderResults(){` — ค้น /api/search, วางลิงก์ → /api/embeddable แล้วเปิดพรีวิว, โหลดคลัง /api/archive, วาดรายการ ⭐ เพลงที่มีอยู่แล้ว / 🔎 ผลค้นหา
! พิมพ์ในช่อง = กรองเพลงในเครื่องแบบออฟไลน์ (listener 'input'); กด ค้นหา/Enter ถึงยิงเน็ต
! markStuck/measureBars อยู่ท้าย section 9 (mix sliders) ไม่ใช่ section 10 · toResTop ต้องเรียกซ้ำหลังรายการยาวกลับ (Chrome Android มี scroll anchoring) และห้ามเรียกจาก loadRecs (คนอื่นเพิ่มเพลงแล้วจอเราเด้ง)

### การ์ดเพลง + ชิปสถานะ (โหลด/ไกด์/เนื้อ/✅⚠️) + ปุ่ม 🔧 ลองใหม่
คำค้น: การ์ด, card, การ์ดเพลง, ชิป, chip, ป้าย, badge, สถานะเพลง, กำลังโหลด, รอแยกเสียง, มีไกด์, มีเนื้อ, ไม่มีเนื้อ, เนื้อตรงจังหวะ, ไม่ตรงจังหวะ, เนื้ออัตโนมัติ, รอตรวจเนื้อ, กำลังเทียบเนื้อ, ✅, ⚠️, error, ลองใหม่, ซ่อม, fix, รูปปก, thumbnail
- `static/remote.html` ` .card{background` ` .chip.ok{` ` .add{flex:none` ` .err{font-size` ` .skel{height` — CSS การ์ด / สีชิป / ปุ่ม ＋ / ข้อความ error / โครงรอโหลด
- `static/remote.html` `<template id="tpl-card">` — โครง HTML การ์ด (ใช้ร่วมทุกรายการ)
- `static/remote.html` `// ===== 4. สถานะเพลง` `const LYR_WAIT = {` `const LYR_CONF = {` `const LYR_CHECK = {` `function lyrInfo(i){` `function statusChips(i){` `const errText = ` `const fixBtn = ` — ทุกสถานะ = {tone, short = ชิป, long = แถวในหน้าสถานะ}, รวมชิป, ข้อความ error, ปุ่ม 🔧 (โผล่เมื่อเซิร์ฟเวอร์ส่ง fix)
- `static/remote.html` `function patchCard(n, it, o){` — เติมข้อมูลลงการ์ด (title/meta/chips/err/rowbtns/＋/แตะดูสถานะ)
! ป้ายความมั่นใจเนื้อ (lyrConf) คิดที่ scripts/lyrics_conf.py — ข้อความ/สีต้องสอดคล้องกับชิปใน static/studio.html (songChips)

### การ์ด "กำลังเล่น" (บนสุดของหน้า)
คำค้น: กำลังเล่น, now playing, เพลงตอนนี้, หยุดชั่วคราว, ยังไม่มีเพลงเล่นอยู่, กำลังสุ่มเพลง, eq, ปุ่มแจ้งซับไม่ตรง
- `static/remote.html` `#nowbox{margin-top` `#now{padding` ` .nowempty{` `@keyframes eq{` — CSS การ์ดชมพู + แท่ง eq + กรอบว่าง
- `static/remote.html` `<div id="nowbox"></div>` `function renderNow(st){` — วาดการ์ด (ว่าง / กำลังสุ่ม / กำลังเล่น) + ปุ่ม 🔧 ลองใหม่ และ 🚩 แจ้งซับไม่ตรง (เฉพาะเพลง YouTube)

### แถบล่าง: เสียงรวม + เริ่มใหม่ / เล่น-หยุด / ข้าม + ปุ่มคิว / ล่าสุด
คำค้น: แถบล่าง, dock, bottom bar, เสียงรวม, master volume, ความดัง, ปิดเสียง, mute, ลำโพง, หยุด, เล่น, play, pause, ข้าม, skip, next, เริ่มใหม่, restart, ปุ่มคิว, ตัวเลขคิว, slider, สไลเดอร์
- `static/remote.html` ` .dock{position:fixed` ` .vol{display:flex` ` .ctrls{display:grid` ` .ctrls em{` `input[type=range]{-webkit-appearance` — CSS แถบล่าง / ปุ่ม 5 ช่อง / ตัวนับคิว / สไลเดอร์ (--p = ความยาวแถบสี)
- `static/remote.html` `<nav class="dock" id="dock">` `id="master"` — HTML
- `static/remote.html` `function makeSlider(` `const volIcon = ` `$('#volbtn').onclick` `$('#toggle').onclick` `function renderAll(st){` — สไลเดอร์ส่ง action 'mix' (หน่วง 120ms + กัน echo ทับนิ้วที่ลาก), แตะลำโพง = ปิด/คืนระดับเดิม, ปุ่ม toggle/next/restart, สลับ ⏸/▶

### กรอบ sheet เลื่อนขึ้นเหนือแถบล่าง (เปิด/ปิด, ฉากมืด)
คำค้น: sheet, bottom sheet, แผ่นเลื่อนขึ้น, หน้าต่างล่าง, popup, ฉากมืด, scrim, ปิด, Esc, เปิดค้าง
- `static/remote.html` `#scrim{position:fixed` ` .sheet{position:fixed` ` .sheet.open{` ` .shd{display:flex` ` .sbody{` — CSS (bottom = --barh, สูงสุด 66vh, เลื่อนขึ้นด้วย .open)
- `static/remote.html` `// ===== 7. sheets` `function setSheet(name){` — เปิดได้ทีละอัน (queue/hist/set/report), ไฮไลต์ปุ่มแถบล่าง, blur ช่องพิมพ์, Esc / แตะฉากมืด = ปิด
! sheet ใหม่: เพิ่ม <section class="sheet" id="sh-ชื่อ"> แล้วใส่ชื่อในลิสต์ ['queue','hist','set','report'] ของ setSheet

### คิวเพลง (sheet 📋)
คำค้น: คิว, queue, รายการคิว, เลื่อนคิว, ขึ้น, ลง, ▲▼, เล่นเลย, play now, ลบเพลงจากคิว, remove, คิวว่าง, จำนวนคิว
- `static/remote.html` `id="sh-queue"` `id="qbtn"` — HTML sheet + ปุ่ม 📋 คิว (ตัวนับ #cnt)
- `static/remote.html` `function renderQueue(st){` — การ์ดคิว (เลขลำดับ) + ปุ่ม ▲ ▼ ▶ เล่นเลย / ลบ
- `static/remote.html` `const ACTIONS = {` `playnow: k => send` — ส่ง up/down/playnow/remove ไปที่ ws (remove ทำการ์ดจาง .pending ก่อน)

### ประวัติ "ใครร้องอะไร" (sheet 🗂 ล่าสุด)
คำค้น: ประวัติ, history, ล่าสุด, ใครร้องอะไร, ร้องไปแล้ว, สั่งซ้ำ, ×2, เมื่อสักครู่
- `static/remote.html` `id="sh-hist"` `id="histbtn"` — HTML sheet + ปุ่ม 🗂 ในแถบล่าง
- `static/remote.html` `function renderHist(){` `const fmtAgo = ` — ยุบรายการซ้ำติดกัน (×n), กด ＋ = เปิดพรีวิวเพื่อสั่งซ้ำ, "x นาทีที่แล้ว"
! ประวัติไม่มากับ state — เปิด sheet แล้ว setSheet ส่ง {action:'history'} → ws ตอบ type 'history' · renderHist ไม่วาดถ้า sheet ปิดอยู่

### ตั้งค่าละเอียด ⚙️ — ชื่อคนร้อง / ไกด์เสียงร้อง / ดนตรี / คีย์ 🎹
คำค้น: ตั้งค่า, settings, ⚙️, ชื่อคนร้อง, singer, noname, ไกด์, vocal guide, เสียงร้อง, ดนตรี, music, คีย์, key, transpose, ลดคีย์, เพิ่มคีย์, คีย์เดิม, ปิดสนิท, เบาๆ, preset
- `static/remote.html` `id="sh-set"` `id="singer"` `id="vocal"` `id="music"` `id="keyrow"` — HTML ช่องชื่อ / สไลเดอร์ / ปุ่มคีย์
- `static/remote.html` ` .fld{padding` ` .fl{display:flex` ` .mixpre{display:flex` ` .mixnote{` — CSS แถวตั้งค่า / ปุ่ม preset / โน้ตเตือน
- `static/remote.html` `function renderMix(st){` `send({action:'mix', key:` `const SL = { vocal:` — sync สไลเดอร์จาก state, ปิดไกด์/ดนตรีถ้ายังไม่แยกเสียง (#mixnote), คีย์ ±1 ในช่วง −6..+6 + ข้อความกำลังเตรียมคีย์ (#keynote)
- `static/remote.html` `$('#singer').value = ` `const DEFAULT_SINGER = ` `const singerName = ` — จำชื่อใน localStorage 'singer', ไม่กรอก = noname
! DEFAULT_SINGER ต้องตรงกับ server.py DEFAULT_SINGER · ไกด์กลับ 100% และคีย์กลับ 0 เองตอนขึ้นเพลงใหม่ (ฝั่งเซิร์ฟเวอร์) · เปลี่ยนคีย์ได้เฉพาะเพลงที่แยกเสียงแล้ว

### ตั้งค่าละเอียด ⚙️ — โหมดเนื้อบนจอ / 👥 แยกเสียงร้อง / 🔀 สุ่มเพลงต่อ
คำค้น: เนื้อเพลงบนจอ, โหมดเนื้อ, lyrics mode, เลื่อนขึ้น, 2 บรรทัดคงที่, คาราโอเกะ, karaoke, ปิดเนื้อ, แยกเสียงร้อง, voices, คนที่ 2, คอรัส, สุ่มเพลง, autoplay, คิวหมด, random
- `static/remote.html` `id="lyrmode"` `#lyrmode{display:grid` `id="voicerow"` `id="autorow"` — HTML/CSS ปุ่มตั้งค่า (โหมดเนื้อเป็นตาราง 2x2)
- `static/remote.html` `send({action:'lyrmode'` `send({action:'voices'` `send({action:'autoplay'` — ส่งคำสั่งไป ws (อยู่ใน ACTIONS)
- `static/remote.html` `const lm = ['scroll','dual','off']` — ไฮไลต์ปุ่มตาม state + โน้ต #lyrnote ตอนเพลงยังไม่มีเวลารายคำ
! โหมดเนื้อ (st.lyrMode) ตั้งได้จากรีโมทเท่านั้น · 👥 คือค่าเดียวกับใน Studio (st.tv.voices) · คาราโอเกะไล่สีได้เฉพาะเพลงที่มี wordsUrl — ไม่มีจอขึ้นแบบ 2 บรรทัดแทน

### 🃏 PU Match — ปัดหาเพลง (กองการ์ดสุ่มจากทุกเพลง / ❤️ ถูกใจ)
คำค้น: PU Match, ปัดเพลง, ปัดหาเพลง, swipe, tinder, การ์ดสุ่มเพลง, ปัดซ้าย, ปัดขวา, ปัดขึ้น, ถูกใจ, ❤️, liked, สุ่มเพลง, ไม่รู้จะร้องอะไร, ย้อนการปัด
- `static/remote.html` `id="swipebtn"` `id="swipe"` `id="swdeck"` `id="swliked"` — HTML: การ์ดทางเข้าใต้ "กำลังเล่น", overlay เต็มจอ, แผงถูกใจ (เลื่อนจากขวา)
- `static/remote.html` ` #swipebtn{width:100%` ` #swipe{position:fixed` ` .swcard{position:absolute` ` .swdeck{position:relative` — CSS (overlay z 35: ทับแถบล่าง แต่ต่ำกว่า toast/หน้าสถานะ #addov)
- `static/remote.html` `// ===== 7c. 🃏 PU Match` `const SW_KEYS =` `function swOpen(){` `async function swFill(){` `function swRender(){` `function swCommit(c, dir){` `function swFling(dir){` `function swUndo(){` `function swDragEnd(e){` — POST /api/swipe เติมการ์ดเมื่อเหลือ ≤3 ใบ, ลาก (pointer) เกิน 28% กว้าง = ซ้าย/ขวา, ขึ้นเกิน 18% สูง = ★ addItem เข้าคิว, แตะ = openPreview
- `static/remote.html` `function swRenderLiked(){` `function swAddAll(){` `function swOnAdded(vid){` — รายการ ❤️ (key w+videoId ใน addByKey), ＋ เปิดหน้าสถานะ เพิ่มแล้วเอาออกจากรายการเอง
! ไม่มีแนวเพลงแล้ว (ลบออก 2026-10-06) — การ์ดสุ่มจากทุกเพลงในเครื่อง · ❤️ / เพลงที่เห็นแล้ว เก็บใน localStorage ของมือถือเครื่องนั้นเท่านั้น (swipeLiked ≤100, swipeSeen ≤300) · ไม่มีปุ่มเปิด/ปิดใน tv.json เพราะไม่ได้แสดงบนจอทีวี
! swRender ห้ามถอด/ใส่การ์ดที่อยู่ถูกที่แล้ว (transition หาย ใบถัดไปกระตุก) · .swdeck ต้องมี z-index ไม่งั้นการ์ดลอยทับแผงถูกใจ

### ⏩ ข้ามอินโทร + 🎬 คอมโบ (การ์ดข้าง PU Match / แผ่นรายการคอมโบ)
คำค้น: ข้ามอินโทร, skip intro, อินโทรยาว, ปุ่มลอย, คอมโบ, combo, เพลย์ลิสต์, playlist, ชุดเพลง, เพิ่มทั้งชุด, addcombo
- `static/remote.html` ` /* ---------- ⏩ ข้ามอินโทร` ` #skipintro{position:fixed` `id="skipintro"` `function renderSkip(){` — ปุ่มลอยกลางเหนือแถบล่าง (z 22 ใต้ scrim/แผ่น) โผล่เมื่อ current.introEnd มี + ยังไม่พ้น (livePos) + ไม่ fading, แถบนับถอยหลัง --w, กดแล้วส่ง action skipintro
- `static/remote.html` ` /* ---------- 🎬 คอมโบ` ` .entries{display:grid` ` #combobtn{display:flex` `id="combobtn"` `id="sh-combo"` — การ์ด 🎬 ข้าง 🃏 (2 คอลัมน์เมื่อ st.combos > 0) + แผ่นรายการ
- `static/remote.html` `// ===== 7d. 🎬 คอมโบ` `async function loadCombos(){` `function renderCombos(){` `function addCombo(id){` `function renderEntries(st){` — GET /api/combos ตอนเปิดแผ่น, ＋ ส่ง addcombo พร้อมชื่อคนร้องจาก ⚙️, toast จาก event added (m.combo)
! ปุ่ม ⏩ ไม่มีสวิตช์ในรีโมท — เปิด/ปิด + เกณฑ์อยู่ใน Studio 📺 (tv.skipBtn / skipMin) และเซิร์ฟเวอร์เป็นคนตัดสินว่าโผล่ (introEnd) · การ์ดคิวจากคอมโบมีชิป 🎬 ใน statusChips

### ปุ่มบนจอล็อกมือถือ 🔒 (Media Session)
คำค้น: จอล็อก, lock screen, หน้าจอล็อก, Media Session, ปุ่มบนจอล็อก, เสียงเงียบ, silent audio, iPhone, Android, ⏮, ⏭, ลดเสียงทีวี, ปกเพลงบนจอล็อก
- `static/remote.html` `id="lockrow"` `id="lockbtns"` `<audio id="lsaudio"` — HTML เปิด/ปิด + เลือกคู่ปุ่ม + audio เงียบ
- `static/remote.html` `// ===== 12. หน้าจอล็อก` `function lsArm(){` `function lsHandlers(){` `function lsSync(st){` `function lsEnable(on){` `function renderLock(){` — สร้าง WAV เงียบในหน้า, play ครั้งแรกจากท่าทางผู้ใช้ (iOS), ปุ่ม play/pause/⏮⏭/⏪⏩ → toggle/restart/next/เสียงรวม ∓10, metadata ชื่อ/คนร้อง/ปก
! iPhone แสดงปุ่มได้ทีละคู่ (track หรือ vol) ต้อง set null คู่ที่ไม่ใช้ · คำสั่งจากจอล็อกใช้ sendLater (socket อาจถูกตัดตอนจอดับ)

### 🚩 แจ้งซับไม่ตรง (sheet รายงานเนื้อ)
คำค้น: แจ้งซับไม่ตรง, report, รายงาน, ซับช้า, ซับเร็ว, เนื้อผิด, พิมพ์ผิด, ขาดท่อน, ไม่มีเนื้อ, ผิดเพลง, ร้องซ้อน, ส่งให้หลังบ้าน, 🚩
- `static/remote.html` `id="sh-report"` `id="reptags"` `id="repnote"` `id="repsend"` — HTML ปุ่มอาการ (data-tag) + รายละเอียด + ปุ่มส่ง
- `static/remote.html` ` .reptags{display:grid` `#repnote{width:100%` — CSS
- `static/remote.html` `// ===== 7b. แจ้งซับไม่ตรง` `function livePos(){` `function openReport(){` `$('#repsend').onclick` — จำตำแหน่งเพลงตอนกดเปิด (ไม่ใช่ตอนส่ง), ส่ง {action:'report', t, tags, note, singer}
! แท็กอาการใหม่ต้องเพิ่ม 3 ที่: ปุ่ม data-tag ที่นี่ + TAGS ใน static/studio.html + REPORT_TAGS ใน server.py (เซิร์ฟเวอร์ทิ้งแท็กที่ไม่รู้จัก)

### หน้าสถานะเต็มจอ — พรีวิวก่อนเพิ่มคิว / ดูสถานะเพลงในคิว
คำค้น: หน้าสถานะ, overlay, เต็มจอ, preview, พรีวิว, กด ＋, เพิ่มเข้าคิว, ยืนยันก่อนเพิ่ม, แตะการ์ด, สถานะสด, ปิดการฝัง, embed, เพลงซ้ำในคิว, ลบออกจากคิว, เล่นเลย, songinfo, คิวที่
- `static/remote.html` `#addov{position:fixed` ` .ovcard{width` ` .ovrow{display:grid` ` .ovbtns{display:flex` — CSS
- `static/remote.html` `<div id="addov"` — HTML (รูป / ป้าย / ชื่อ / แถวสถานะ / คำเตือน / ปุ่ม)
- `static/remote.html` `// ===== 6. หน้าสถานะเต็มจอ` `function openPreview(req, warn){` `function itemRows(i){` `function previewRows(p){` `function dupNote(req){` `function renderOv(){` `function onAdded(m){` — 2 โหมด (preview = ก่อนเพิ่ม / item = แตะการ์ดคิว), ดึง /api/songinfo, แถววิดีโอ/ไกด์/เนื้อ, เตือนเพลงซ้ำ/ปิดการฝัง, ปุ่มตามโหมด, toast บอกลำดับคิวจริง
- `static/remote.html` `function addByKey(k){` `function addItem(o){` — ＋ บนการ์ด = เปิดพรีวิว (ยังไม่ส่ง) / ปุ่ม ＋ เพิ่มเข้าคิว ค่อยส่ง action 'add' พร้อม cid
! ＋ บนการ์ดไม่ได้เข้าคิวทันที — ส่งจริงที่ ovadd → addItem · cid = TAB_ID-ลำดับ ใช้จับคู่ event 'added' ของเครื่องตัวเอง

### กลไกกลางของหน้า: util / store / keyed diff / ปุ่ม data-act / toast
คำค้น: กระพริบ, flicker, รูปกระพริบ, render, วาดใหม่, reconcile, diff, key, setText, setHTML, setSrc, noart, state, store, ปุ่ม, data-act, กดแล้วไม่ทำงาน, action, event delegation, toast, ข้อความแจ้ง
- `static/remote.html` `// ===== 1. util` `const setText = ` `const setSrc` `const artUrl = ` — เขียน DOM เฉพาะตอนค่าเปลี่ยน (ไม่ให้จอกระพริบ), ตั้ง src ซ้ำ = รูปกระพริบ, url รูปปก
- `static/remote.html` `// ===== 2. store` `const TAB_ID = ` — state กลาง S + รหัสแท็บนี้
- `static/remote.html` `// ===== 3. keyed diff` `function reconcile(` `function emptyMsg(root, html){` — reconcile ตาม key (โหนดไม่มี key = skeleton/ข้อความว่าง ถูกลบ), รูปเสีย → คลาส noart
- `static/remote.html` `// ===== 8. actions (delegation)` `const ACTIONS = {` `document.addEventListener('click', e=>{` — ตัวรับคลิกตัวเดียวทั้งหน้า: data-act → ACTIONS, แตะตัวการ์ดคิว/กำลังเล่น = เปิดหน้าสถานะ
- `static/remote.html` `#toast{position:fixed` `function toast(msg){` — กล่องข้อความลอยเหนือแถบล่าง (2.5 วิ)
! key ห้ามชนกัน: เพลงในเครื่อง 'a'+videoId, ผลค้น 'r'+videoId, ประวัติ 'h'+… (addByKey แยกด้วยตัวอักษรแรก) · ห้ามแทน node ด้วย outerHTML (พัง reconcile)
! ปุ่มใหม่: ใส่ data-act="ชื่อ" แล้วเพิ่ม key ใน ACTIONS · ห้ามตั้ง b.disabled บนปุ่มในการ์ด (setHTML รอบหน้าล้างทิ้ง) ใช้คลาส .pending แทน

## จอทีวี (static/player.html — หน้า / , /tv/{key} และ /watch)

### เล่นเพลง: วิดีโอในเครื่อง / YouTube iframe + สลับเพลง / หยุด / เริ่มใหม่ (apply)
คำค้น: จอทีวี, player, เล่นเพลง, playback, วิดีโอ, video, YouTube, iframe, ไฟล์ในเครื่อง, local, หยุด, เล่นต่อ, เริ่มใหม่, restart, ข้ามเพลง, เพลงจบ, ended, จอดำ, เปลี่ยนเพลง, รีเฟรชแล้วเล่นต่อ, ตำแหน่งเพลง
- `static/player.html` `#yt,#local{position:absolute` `<video id="local"` — เวที: iframe YouTube กับ <video> ซ้อนกัน
- `static/player.html` `window.onYouTubeIframeAPIReady = ` `let curItem=null;` — สร้าง YT player (onError → showErr) + id ใบคิวที่แนบไปกับ 'ended' ทุกทาง
- `static/player.html` `function apply(st){` `function localUrlOf(c){` `function tryPlayLocal(){` `function resumeAt(st){` `function hideYt(){` — ตัวกลางรับ state ทุกครั้ง: เลือกแหล่ง (มีไฟล์ในเครื่อง = <video> ไม่งั้น YouTube), restartToken, เล่น/หยุด, รีเฟรชแล้วเล่นต่อจากตำแหน่งเดิม
- `static/player.html` `sendWs({action:'pos'` — รายงานตำแหน่งทุก 2 วิ (หลัง attached เท่านั้น)
! แก้ไฟล์นี้แล้วแค่รีโหลดจอ — server.py อ่าน static/player.html จากดิสก์ทุกคำขอ (no-store) ไม่ต้องรีสตาร์ท

### 📺 จอที่สอง /watch (ดูอย่างเดียว ภาพออกหลายจอ) + ลิงก์ในตั้งค่ารีโมท
คำค้น: จอที่สอง, จอสอง, 2 จอ, สองจอ, mirror, watch, /watch, ภาพออกหลายจอ, เปิดจอที่เครื่องอื่น, ลิงก์จอทีวี, ซิงก์ภาพ, เสียงซ้อน, เสียงก้อง, เปิดเสียงจอนี้
- `server.py` `@app.get("/watch"` `def watch_page():` — เสิร์ฟ player.html ให้ทุกเครื่อง (ไม่ต้องมีรหัส ต่างจาก /tv/<รหัส> ที่เป็นจอหลัก)
- `server.py` `if msg.get("role") == "mirror":` `mirrors = [o for o in list(room.clients)` — hello role=mirror ตั้ง ws._is_mirror (ไม่ evict ใคร), pos ของจอหลักถูกส่งต่อเป็น {type:'pos', t, id} ให้ทุกจอที่สองพร้อมกัน
- `static/player.html` `const MIRROR = ` `const MIRROR_MUTE = ` `// ===== 📺 จอที่สอง` `function mirrorSync(m){` `id="mirsnd"` — sendWs ทิ้ง pos/ended, เงียบ = ล็อก local.muted + ไม่ใช้สเต็ม (ไม่มีจอแตะเปิดเสียง), ?sound = เสียงเต็ม, ห่างเกิน 0.6 วิ seek ตาม (≤1 ครั้ง/5 วิ, ข้ามโหมด YouTube), จอ error ไม่นับถอยหลังข้ามเพลง
- `static/remote.html` `id="watchurl"` `const watchUrl = ` `copywatch:` — ล่างสุดของ ⚙️: ลิงก์ baseUrl/watch (Cloudflare ถ้าเปิดไว้ ไม่งั้นวงแลน) + คัดลอก/เปิด
! ลิงก์ที่โชว์ให้แขกต้องเป็น /watch เท่านั้น — /tv/<รหัส> ยังเป็นความลับ (จอที่ hello role=player ชนะเสมอ ยึดจอหลักได้) ห้ามใส่ใน state · ปิดจอหลัก = คิวไม่เดิน (จอที่สองไม่ส่ง ended)
! ส่ง 'ended' ต้องแนบ id: curItem เสมอ (เซิร์ฟเวอร์ทิ้ง ended ที่ค้าง/ซ้ำ — เพลงเดียวกันต่อกันสองรอบ URL เหมือนเดิม)

### เฟดเปลี่ยนเพลง (จอดำ + เสียงไล่ระดับ) + จุดจบโหมด Custom/คอมโบ + ⏩ ดำแวบ
คำค้น: เฟด, fade, เฟดเข้า, เฟดออก, จอดำ, blackout, ค่อยๆดำ, ค่อยๆเบา, เปลี่ยนเพลงนุ่ม, โหมด custom, จุดจบ, endAt, startAt, ข้ามอินโทร, seekToken
- `static/player.html` ` #blackout{position:absolute` `<div id="blackout">` — แผ่นดำทับแค่วิดีโอ (z 3) ชื่อเพลง/ซับ/♪●●● ยังเห็น
- `static/player.html` `// ===== เฟดเปลี่ยนเพลง` `function fadeTo(` `function armFadeIn(` `function fadeTick(){` `function seekDip(){` `function resetFade(){` — fadeK คูณเสียงรวมใน applyMix (ไม่แตะระหว่าง fadeUntil), เฟดเข้าเมื่อภาพเล่นจริงที่ตำแหน่งถูก (mediaLive, กันค้าง 6 วิ), เฟดออกเมื่อ st.fading = ใบนี้ หรือเหลือ ≤ fadeOut ก่อนจุดจบ, ถึง c.endAt ส่ง ended, seekToken เปลี่ยน = ดำแวบแล้ว seek
- `static/player.html` `function audOutSec(c){` `const fadeInSec =` — ค่ารายคลิป (c.fadeIn/c.fadeOut) ทับค่าใน 📺; โหมด Custom เสียงเฟดออกใช้ customAud
- `static/player.html` `startSeconds: at` — YouTube iframe เริ่มที่ตำแหน่งห้อง (จุดเริ่ม Custom / รีโหลดกลางเพลง)
! จุดเริ่มไม่มีโค้ดของตัวเอง — เซิร์ฟเวอร์ตั้ง room.pos = startAt แล้ว apply() seek เองผ่าน resumeAt · ทุกค่า 0/ปิด (fadeIn/fadeOut 0, custom ปิด) = resetFade ทันที จอเหมือนเดิม
! applyMix ห้ามตั้ง gMaster/volume ระหว่างเฟด (ทับ ramp) · fadeTick อยู่นอก // <lyrcore> และใช้ lyrPos()

### เครื่องผสมเสียงสเต็ม (Web Audio): ไกด์ / ดนตรี / เสียงรวม / คีย์ + แตะจอเพื่อเปิดเสียง
คำค้น: สเต็ม, stems, ไกด์เสียงร้อง, vocal guide, ดนตรี, instrumental, เสียงรวม, master, volume, Web Audio, AudioContext, mix, คีย์, key, เลื่อนคีย์, crossfade, เสียงสะดุด, เสียงกระโดด, เสียงซ้อน, drift, แตะจอเพื่อเปิดเสียง, unlock, autoplay, nostems
- `static/player.html` `// ===== เครื่องผสมเสียงสเต็ม` `function stemsOf(c){` `function ensureCtx(){` `function applyMix(m){` `function rampEl(target){` — เลือกชุดสเต็ม (tag = เพลง@คีย์), gain ไกด์/ดนตรี/รวม, ทางสำรองตั้ง volume ของ <video>/YouTube
- `static/player.html` `async function loadStems(c){` `function startStems(offset){` `function stopSources(){` `async function enterStems(st, c, live){` `function teardownStems(){` `function driftTick(){` — decode, เริ่มสองสเต็มพร้อมกันระดับ sample + crossfade 30ms, สลับชุดกลางเพลง (เปลี่ยนคีย์), ดุน playbackRate วิดีโอให้ตามเสียง
- `static/player.html` `const queueOp = ` `const withTimeout = ` — คิวงานเสียงทีละงาน มีเพดาน 15 วิ
- `static/player.html` `#unlock{position:absolute` `<div id="unlock"` `function onGesture(){` — overlay 🔊 แตะจอเพื่อเปิดเสียง (resume AudioContext)
! stopSources/startStems ต้องถอด onended ก่อน stop() ไม่งั้นยิง 'ended' หลอกให้ข้ามเพลง · applyMix ห้ามแตะ local.muted (apply() เป็นเจ้าของ) · onGesture ทำงานเฉพาะตอน needUnlock · ?nostems ใน URL = ปิดโหมดสเต็ม

### แถบชื่อเพลงบนสุด + ชิปสถานะ + การ์ด "ต่อไป"
คำค้น: ชื่อเพลง, แถบบน, title bar, now playing, คนร้อง, singer, ชิป, ไกด์ %, คำเตือน, กำลังเตรียมเสียง, กำลังแยกเสียง, ซ่อนแถบชื่อ, จางหาย, fade, ต่อไป, up next, เพลงถัดไป
- `static/player.html` `#now{position:absolute` `#now .ti{font-size` `#now .gd{` — CSS แถบบน (ชื่อ / คนร้อง / ชิป)
- `static/player.html` `const CH = {` `const keyWarn = ` `nowFadeKey = fk` — (ใน apply) ชิปตาม tv.chips + คำเตือนระบบขึ้นก่อนเสมอ + ซ่อนแถบหลัง N วิ (tv.titleHide)
- `static/player.html` `#next{position:absolute` `function renderNext(q){` — การ์ด "ต่อไป" มุมซ้ายล่าง (ซ่อนตอนขึ้นเนื้อ: body.lyrics)
! key ของชิป (guide/key/master/music/lyrsrc/next) ต้องตรงกับ TV_CHIPS ใน server.py และ TV_CHIP_LB / renderTvPreview ใน static/studio.html

### หน้าจอว่าง (QR กลางจอ) + QR ลอยมุมขวาล่าง + รูปมุมขวาบน
คำค้น: หน้าจอว่าง, idle, รอเพลง, QR, สแกน, ลิงก์รีโมท, ข้อความต้อนรับ, idleText, QR มุมขวาล่าง, ขนาด QR, โลโก้, logo, รูปมุมขวาบน
- `static/player.html` `#idle{position:absolute` `#idle .qcard{` `<div id="idle">` `id="idletext"` — หน้ารอ (สแกนเพื่อสั่งเพลง + ลิงก์ #idleurl + ข้อความจาก Studio)
- `static/player.html` `#qrflo{position:absolute` `#logo{position:absolute` `body.logo #addcard{` — QR ลอยตอนเล่น (--qrw) + รูป 1:1 (--logow) + การ์ด/ชื่อเพลงหลบรูป
- `static/player.html` `'/qr.png?v='` — ลิงก์เปลี่ยน (เปิด/ปิด Cloudflare) → โหลด QR ใหม่เอง ไม่ต้องรีเฟรชจอ
! เนื้อเพลงเว้นขอบซ้ายขวาเท่า --qrw (ไม่ทับ QR) — ปิด QR (body.no-qr) ซับกว้างเต็มจอ

### การ์ด "เพิ่มเข้าคิว" มุมขวาบน (มีคนกด ＋ จากรีโมท)
คำค้น: การ์ดเพิ่มเข้าคิว, added, มีคนสั่งเพลง, แจ้งเพลงใหม่, popup บนทีวี, addcard, เริ่มเล่นเลย, คิวที่
- `static/player.html` `#addcard{position:absolute` `#addcard .c.ok{` — CSS (เลื่อนเข้าจากขวา)
- `static/player.html` `// ===== การ์ด "เพิ่มเข้าคิว"` `const ADD_SHOW_MS = ` `function showAdded(id){` `function renderAdded(){` — โชว์ 5 วิ (เพิ่มติดกัน = แทนการ์ดเดิม), วาดใหม่ทุก state ให้เห็นไกด์/เนื้อเปลี่ยนสด, กันรูปกระพริบด้วย el._h
! เซิร์ฟเวอร์ส่ง {type:"added"} หลัง broadcast state เสมอ — ตอน showAdded window._state มีเพลงนั้นแล้ว

### ตั้งค่าหน้าจอจาก Studio (applyTv): สี / ขนาด / เงาซับ, ซ่อนชื่อ / QR / เวลา / การ์ด
คำค้น: ตั้งค่าจอ, tv settings, applyTv, สีซับ, ขนาดซับ, lyrScale, สีคาราโอเกะ, ความสว่างบรรทัดจาง, เงาตัวอักษร, ขอบตัวอักษร, พื้นหลังใต้ซับ, ยกซับ, ซ่อน QR, ซ่อนเวลา, ซ่อนชื่อเพลง, ซ่อนคนร้อง, CSS variable
- `static/player.html` `--qrscale:1;` `body.no-title #now` `body.sh3 #lyrcur` — ค่าเริ่มต้นตัวแปร CSS + คลาสซ่อน (no-*) + เงา sh0–sh3
- `static/player.html` `// ===== ตั้งค่าหน้าจอจาก Studio` `const tvScale = ` `function applyTv(tv){` — แปลง st.tv → CSS var + คลาสบน body (ทำเฉพาะตอนค่าเปลี่ยน: tvSig) แล้ววัดขนาดซับใหม่
! ค่าใหม่ต้องเพิ่ม 3 ที่: TV_SCHEMA ใน server.py + applyTv ที่นี่ + ฟอร์ม/renderTvPreview ใน static/studio.html (section 16d)

### เนื้อเพลงบนจอ: เลื่อนขึ้น / 2 บรรทัดคงที่ / ♪ ● ● ● นับถอยหลัง (lyrcore)
คำค้น: เนื้อเพลง, ซับ, lyrics, subtitle, บรรทัด, เลื่อนขึ้น, scroll, 2 บรรทัด, dual, นับถอยหลัง, countdown, ●●●, ♪, ช่วงดนตรี, ขนาดตัวอักษร, font size, ซับขึ้นช้า, ซับขึ้นเร็ว, offset, lyroffset, lyrcore, ร้องซ้อน
- `static/player.html` `#lyr{position:absolute` `#lyrcur{font-size` `#lyr.m-dual #lyrcur.on` `<div id="lyr"` — CSS/HTML (#lyrcur / #lyrnext = แถวบน/ล่าง, จาง/สว่าง)
- `static/player.html` `// ===== เนื้อเพลง` `async function loadLyrics(url){` `function lyFitDual(){` `const songOff = ` `const LYR_OFFSET = ` `function lyrTick(){` — โหลด (เรียงตาม t), ล็อกขนาดตัวอักษรทั้งเพลงด้วย canvas, offset ประจำเพลง + ?lyroffset=, วาดทุก 100ms
- `static/player.html` `// <lyrcore>` `const LYC = {` `function lycPrep(L){` `function lycIndex(L, t){` `function lycFrame(L, t, o){` `function lycParts(x){` — ตรรกะแถว / สว่าง-จาง / ♪ / ●●● (LEAD/HOLD/GAP/CD/OVER)
! บล็อก // <lyrcore> … // </lyrcore> (รวมคอมเมนต์ข้างใน) ต้องเหมือน static/studio.html ทุกตัวอักษร — แก้แล้วคัดลอกทั้งบล็อก ตรวจด้วย python3 scripts/eval_lyrics.py core · scripts/eval_display.js ตัดบล็อกนี้ไปรันใต้ node: ห้ามเปลี่ยนชื่อ marker และห้ามแตะ DOM/ตัวแปรนอกบล็อก
! เวลาในบล็อกเป็น "เวลาเนื้อ" — lyrTick หัก songOff() + LYR_OFFSET ครั้งเดียวก่อนเรียก lycFrame

### โหมดคาราโอเกะ (ไล่สีตามเวลาที่ร้องจริง) + 👥 แยกเสียงร้อง / คอรัส
คำค้น: คาราโอเกะ, karaoke, ไล่สี, colour fill, เวลารายคำ, words, word timing, FA, ตัวอักษร, กลุ่มอักษร, สระลอย, แยกเสียงร้อง, voices, คนที่ 2, สีฟ้า, คนที่ 3, คอรัส, วงเล็บ, ตัวเล็ก, ความหน่วงลำโพง, latency, บลูทูธ, ไล่สีนุ่ม, ค่อย ๆ ไล่, smooth, wipe, ทีละตัวอักษร, karaSmooth
- `static/player.html` `#lyr.m-kara .kara span.s{` `#lyr .bk{` `#lyr #lyrcur.v2,` — CSS สีที่ร้องแล้ว (--kara), ส่วนในวงเล็บ, สีคนที่ 2/3
- `static/player.html` `// ===== โหมดคาราโอเกะ` `async function loadWords(url){` `function kwAttach(){` `const kUse = ` `function kClusters(l){` — โหลด lyrics.words.json, ผูก k กับบรรทัด (ข้อความต้องตรงทุกตัว), แตกกลุ่มอักษรด้วย Intl.Segmenter + เกลี่ยเวลา
- `static/player.html` `function lyRow(el, text, j, line, vo){` `function karaPaint(el, pn){` `function karaLoop(){` `const outLat = ` — วาดแถว (span ทีละกลุ่มอักษร), ไล่สีทุกเฟรม (ย้อนได้), หักความหน่วงเสียงออก
- `static/player.html` `body.kara-smooth #lyr.m-kara .kara span.p::after{` `const KARA_WIPE = ` `let karaSmooth = ` — 🌈 ไล่สีนุ่ม (tv.karaSmooth, Studio 📺): กลุ่มที่กำลังร้องเติมสีซ้าย→ขวา ด้วยสำเนา ::after + clip-path (--kp %) ถึงเวลากลุ่มถัดไป (สูงสุด KARA_WIPE วิ)
- `static/player.html` `const voicesOn = ` `const VOICE_CLS = ` `function bkSpans(text){` — 👥 เปิด/ปิด (tv.voices) + คลาสสีตามเสียงของบรรทัด (v: 2/3/bg) + วงเล็บตัวเล็ก
! เวลารายตัวอักษรเป็นเวลาจริงในเสียง — บวกแค่ ?lyroffset= ไม่บวก offset ประจำเพลง · KARA_LEAD/KARA_GAP/kClusters มีสำเนาใน static/studio.html (อยู่นอก lyrcore — eval ไม่ตรวจ) แก้ต้องแก้ทั้งสองไฟล์
! ไล่สีนุ่ม: ::after ต้อง line-height:normal (สืบ 1.32 มาสำเนาจะเลื่อนลงไม่ทับตัวจริง) และ span ห้ามมี transition (สลับ .p→.s จะกะพริบ) · Studio พรีวิวยังเปลี่ยนสีทีละตัวแบบเดิม

### เวลาเพลงมุมซ้ายล่าง + ตัวอ่านตำแหน่งเพลง (posNow / ytNow / lyrPos)
คำค้น: เวลาเพลง, song time, 1:23 / 4:10, มุมซ้ายล่าง, ตำแหน่งเพลง, position, currentTime, posNow, ytNow, lyrPos, playPos, นาฬิกา
- `static/player.html` `#tme{position:absolute` `<div id="tme"` — CSS/HTML
- `static/player.html` `// ===== เวลาเพลงมุมซ้ายล่าง` `function playPos(){` `function tmeTick(){` — อัปเดตทุก 250ms ตามแหล่งที่เล่นจริง (ซ่อนได้: tv.time)
- `static/player.html` `function posNow(){` `function ytNow(){` `const ytMode = ` `const lyrPos = ` — นาฬิกาหลัก: สเต็ม = ctx.currentTime, วิดีโอ = currentTime, YouTube = getCurrentTime + ต่อเวลาเอง
! posNow() ใช้ไม่ได้ตอนเล่นผ่าน YouTube (อ่าน <video> ว่าง = 0) — เนื้อ/ไล่สีใช้ lyrPos(), เวลาบนจอใช้ playPos()

### จอ error / จอถูกแทนที่ / หลุดการเชื่อมต่อ + websocket ของจอ
คำค้น: error, เล่นไม่ได้, ปิดการฝัง, คลิปถูกลบ, ข้ามไปเพลงถัดไป, นับถอยหลัง 4 วิ, จอถูกแทนที่, evicted, หลายจอ, ยึดจอกลับ, กำลังเชื่อมต่อ, websocket, hello, /tv/รหัส, TV_KEY, clientlog, log
- `static/player.html` `#err{position:absolute` `#conn{position:absolute` `#evicted{position:absolute` — CSS overlay
- `static/player.html` `function showErr(msg){` `function becomeEvicted(){` `function clog(tag, msg){` — error นับ 4 วิแล้วส่ง ended, ถูกแทนที่ (แตะ = ส่ง hello ยึดกลับ), ส่ง log ขึ้น /api/clientlog
- `static/player.html` `function connect(){` `const TV_KEY = ` `const PLAYER_ID = ` — ws: hello role=player (id + รหัสจาก /tv/{key}), รับ state/added/evicted, ต่อใหม่ทุก 1.5 วิ
! ถูกแทนที่ต้องหยุดทุกอย่าง + hideErr() (นับถอยหลังค้างห้ามส่ง ended ไปข้ามเพลงของจอใหม่) · connect() ต้องเรียกท้ายไฟล์ (let ของเครื่องผสมเสียงต้องประกาศครบก่อน)

## Studio (static/studio.html — หน้า /studio)

### เข้า Studio ด้วย PIN + เรียก API + กล่อง dialog / toast
คำค้น: Studio, PIN, รหัส, login, เข้าสู่ระบบ, 401, .studio.json, api, fetch, dialog, กล่องยืนยัน, popup, toast, ข้อความแจ้ง
- `static/studio.html` ` .dlg{position:fixed` ` .pin input{` `#toast{position:fixed` — CSS กล่อง dialog / PIN / toast
- `static/studio.html` `id="pindlg"` `id="dlg"` — HTML กล่อง PIN + กล่อง dialog กลาง (#dlgcard)
- `static/studio.html` `// ===== 2. API + PIN` `async function api(path, opt = {}){` `async function login(){` — ทุกคำขอผ่าน api(): 401 → เปิดกล่อง PIN; login แล้วโหลดรายการ + เปิดเพลงเดิมแบบ 'bg'
- `static/studio.html` `function openDlg(html, cls){` `function closeDlg(){` `function toast(msg, ms = 2600){` — เปิด/ปิด dialog (คลิกพื้นหลัง / data-dlg=close / Esc), toast
! แก้ไฟล์นี้แล้วแค่รีโหลดหน้า — server.py อ่าน static/studio.html จากดิสก์ทุกคำขอ (no-store) ไม่ต้องรีสตาร์ท

### โครงหน้า + แท็บบนหัว + จอแคบ (มือถือ) + ล็อกซูม
คำค้น: layout, โครงหน้า, header, หัว, แท็บ, tab, เพลงทั้งหมด, กำลังเล่น & คิว, หน้าจอหลัก, สลับหน้า, data-view, มือถือ, mobile, จอแคบ, responsive, iPad, ← รายการ, back, ซูม, pinch, iOS ซูมเอง, 16px
- `static/studio.html` ` .app{display:grid` ` .main{display:grid` — CSS (ซ้ายรายการ 380px | ขวาตัวแก้)
- `static/studio.html` ` .tabs{display:flex` `body:not([data-view=songs]) .main` `<nav class="tabs" id="tabs">` — แท็บ + ซ่อน/โชว์ตาม body[data-view]
- `static/studio.html` `// ===== 16b. แท็บ` `function setView(v){` — สลับแท็บ (จำใน localStorage studioView), หยุดพรีวิวเมื่อออกจากแท็บเพลง, เข้าแท็บคิว/ทีวี/ตัดต่อแล้ววาด/โหลด
- `static/studio.html` `@media (max-width:999px){` `input,select,textarea{font-size:16px}` `$('#back').onclick` — จอ ≤999px โชว์ทีละฝั่ง (body.editing) + ปุ่ม ← รายการ (ถามก่อนทิ้งงาน)
- `static/studio.html` `<meta name="viewport"` `// ===== 0. ล็อกซูมบนมือถือ` — กัน pinch บนจอสัมผัส (iOS ไม่สน user-scalable=no)
! บนจอแคบช่องพิมพ์ต้อง ≥16px (กฎใน @media) ไม่งั้น iOS ซูมเข้าเองตอนแตะ

### รายการเพลง (ซ้าย): ค้นหา / ตัวกรอง / เรียง + ชิปสถานะเพลง
คำค้น: รายการเพลง, song list, ค้นหาเพลง, ตัวกรอง, filter, มีปัญหา, มีคนแจ้ง, ไม่มีเนื้อ, ไม่ตรง, ยังไม่ตรวจ, มีคำแนะนำ, เรียง, sort, ร้องบ่อย, ชิป, chip, ป้ายสถานะ, ✅ ตรงจังหวะ, ⚠️, 🔍 คะแนน, 🩺 เวลาอัด/เดา, 🎤 คาราโอเกะ, ✨ เลือกอัตโนมัติ, ✏️ แก้เอง, 🌐 ภาษา
- `static/studio.html` ` .side{display:flex` ` .filters{display:flex` ` .it{display:flex` ` .chip.ok{` — CSS รายการ / ปุ่มกรอง / แถวเพลง / สีชิป
- `static/studio.html` `<aside class="side">` `id="filters"` `<select id="sort">` — HTML
- `static/studio.html` `// ===== 3. สถานะเพลง -> ชิป` `const CONF = {` `const WORDS = {` `function songChips(i, full){` `const FILTERS = [` `const rank = ` — ข้อความ/สีทุกสถานะ (full = หัวเพลง), ปุ่มกรอง (เพิ่มตัวกรองใหม่ที่นี่), ลำดับ "มีปัญหาก่อน"
- `static/studio.html` `// ===== 5. รายการเพลง` `async function loadSongs(){` `async function loadSongsNow(){` `function renderList(){` — GET /api/studio/songs (กันยิงซ้อน, ไม่เปลี่ยน = ไม่วาดใหม่), อัปเดตหัวเพลง/รายงาน/เวลารายคำของเพลงที่เปิดอยู่
! สี/ความหมายป้ายความมั่นใจเนื้อต้องตรงกับรีโมท (LYR_CONF ใน static/remote.html)

### เปิดเพลง + กันงานที่ยังไม่บันทึกหาย (dirty / bg / force)
คำค้น: เปิดเพลง, open song, โหลดเพลง, เลือกเพลง, ยังไม่ได้บันทึก, งานหาย, unsaved, dirty, เปลี่ยนเพลง, โหลดฉบับในเครื่อง, เนื้อในเครื่องเปลี่ยน, state
- `static/studio.html` `id="blank"` — HTML "เลือกเพลงทางซ้าย"
- `static/studio.html` `// ===== 4. store` `const snapshot = ` `function pendingInput(){` `const dirty = ` `function commitInput(){` — state S ทั้งหมด, ตรวจงานค้าง (รวมช่องที่กำลังพิมพ์ค้าง)
- `static/studio.html` `// ===== 6. เปิดเพลง` `async function openSong(vid, mode){` — GET /api/studio/song/{vid}; mode ว่าง = ผู้ใช้กด, 'bg' = รีเฟรชเบื้องหลัง (ห้ามทับงานค้าง), 'force' = ยืนยันโหลดทับ
! งานเบื้องหลังต้องเรียก openSong(vid, 'bg') เสมอ — แบบไม่ใส่ mode จะทับงาน+undo ของผู้ใช้

### หัวเพลง: ข้อมูล / ภาษา 🌐 / 💡 แนะนำเลื่อน / ปุ่มซ่อม / 🗑 ลบเพลง
คำค้น: หัวเพลง, ข้อมูลเพลง, ปุ่มซ่อม, fix, ซ่อมอัตโนมัติ, โหลดใหม่, แยกเสียงใหม่, หาเนื้อใหม่, ตรวจเวลาเนื้อ, verify, เลือกเนื้อดีที่สุด, ทำเวลารายคำ, เลิกใช้เนื้อที่แก้เอง, ลบเพลง, delete, ภาษา, language, ตรวจภาษา, คำแนะนำเลื่อน, ลองฟัง, ใช้เลย, error
- `static/studio.html` ` .info{min-width:0` ` .acts{display:flex` ` .tip.sugg{` — CSS กล่องข้อมูล / ปุ่ม / คำแนะนำ
- `static/studio.html` `<div class="info">` `id="stchips"` `id="sugg"` `id="acts"` — HTML ชิป / คำแนะนำ / ปุ่ม
- `static/studio.html` `// ===== 7. หัวเพลง` `const ACT_INFO = {` `function renderInfo(){` `function showNote(html, btns){` — ปุ่มซ่อม (ชื่อ+คำอธิบาย), ปุ่มไหนโชว์เมื่อไร, error, 💡 ลองฟัง/ใช้เลย, ✨ ผลเลือกเนื้อ / 🩺 บรรทัดไม่มั่นใจ
- `static/studio.html` `$('#acts').addEventListener` `$('#meta').addEventListener('change'` `function openDeleteDlg(){` — POST /api/studio/song/{vid}/action {do:k}, เปลี่ยนภาษา/ตรวจภาษา, กล่องยืนยันลบ (เลือกลบ lyrics-in ด้วย) → DELETE
! ปุ่มซ่อมใหม่: เพิ่มใน ACT_INFO + เงื่อนไข acts ใน renderInfo + do:<ชื่อ> ใน server.py

### 🎤 เวลารายตัวอักษร (คาราโอเกะ) ในพรีวิว Studio
คำค้น: เวลารายคำ, word timing, คาราโอเกะ, karaoke, ไล่สี, FA, ตัวอักษร, กลุ่มอักษร, words.json, ขีดส้ม
- `static/studio.html` ` .pv.kara .ly span.s{` — CSS สีที่ร้องแล้ว (#ff6fa6 = --kara ของทีวี)
- `static/studio.html` `// ===== 7a.` `function kwBuild(){` `async function refreshWords(){` `function kFor(l){` `function kClusters(x, k){` `function pvRow(el, text, j, line, vo){` `function pvPaint(el, pos){` — ผูก k กับบรรทัดที่กำลังแก้ (ข้อความตรง + ใกล้เวลา), แตกกลุ่มอักษร, วาด/ไล่สีแถวพรีวิว (+ 👥 วงเล็บ/สีเสียง)
! KARA_LEAD/KARA_GAP/kClusters เป็นสำเนาจาก static/player.html (นอกบล็อก lyrcore — eval ไม่ตรวจให้) แก้ต้องแก้ทั้งสองไฟล์

### 🚩 รายงานซับไม่ตรงจากรีโมท
คำค้น: รายงาน, report, แจ้งซับไม่ตรง, 🚩, มีคนแจ้ง, แก้แล้ว, done, ข้ามไปจุดที่แจ้ง, แท็กอาการ, ธงแดงบนแถบคลื่น
- `static/studio.html` ` .reps{border` ` .rep{display:grid` `id="reps"` — CSS/HTML กล่องรายงานในหัวเพลง
- `static/studio.html` `const TAGS = {` — ชื่อแท็กอาการ (ตรงกับ data-tag ใน static/remote.html)
- `static/studio.html` `// ===== 7b.` `async function refreshReports(){` `function renderReports(){` `$('#reps').addEventListener` — ล่าสุดก่อน, กดเวลา = ข้ามไปก่อนจุดนั้น 3 วิ, ✓ แก้แล้ว/ทั้งหมด → POST …/reports
! แท็กใหม่ต้องเพิ่ม 3 ที่: TAGS ที่นี่ + ปุ่ม data-tag ใน static/remote.html + REPORT_TAGS ใน server.py

### 🗺 แผนที่ความคลาด + 🩺 ซ่อมช่วงเพี้ยน
คำค้น: ความคลาด, drift, แผนที่, วัดความคลาด, วัดละเอียด, 🎯 FA, whisper, ซับเร็วไป, ซับช้าไป, จุดสี, เขียว เหลือง แดง, ภาพรวมทั้งเพลง, overview, เลื่อนเป็นช่วง, ใช้ทุกช่วง, ท่อนซ้ำ, 🩺, ซ่อมเวลา, refine, เวลาอัด, เวลาเดา, ไม่มั่นใจ
- `static/studio.html` ` .drift{border` ` .seg1{display:flex` `#ov{display:block` — CSS กล่อง 🗺 + แถวช่วง + กราฟภาพรวม
- `static/studio.html` `id="drift"` `<canvas id="ov"` — HTML
- `static/studio.html` `// ===== 7c.` `async function measureDrift(engine){` `function scheduleRemeasure(){` `const driftAmb = ` `function segmentsOf(ds){` `function renderDrift(){` `function applySeg(g){` `function paintOV(){` — POST …/drift (auto/fa), วัดใหม่เมื่อข้อความเปลี่ยน, DP แบ่งช่วงค่าคงที่, ปุ่ม ▶ ฟัง/ใช้/ใช้ทุกช่วง, กราฟ ±3 วิ (คลิก = ข้ามเวลา)
- `static/studio.html` `async function runRefine(){` `$('#refineuse').onclick` `data-dr="refine"` — 🩺 POST …/refine (ตัวเดียวกับ scripts/lyrics_refine.py), กล่องสรุป, ใช้ข้อเสนอผ่าน mutate (เช็กว่าข้อความไม่เปลี่ยนก่อน)
! ความคลาด = วัดได้ − ขึ้นจอ (บวก = ซับขึ้นก่อนร้อง/เร็วไป) · บรรทัดท่อนซ้ำติดกัน (driftAmb) ไม่นับและไม่เสนอให้เลื่อน · เลื่อนเป็นช่วงต้องให้คนกดเอง (ไม่ทำอัตโนมัติ)

### 🔎 ห้องหาเนื้อจากทุกแหล่ง + 🔑 token Musixmatch
คำค้น: หาเนื้อ, ค้นเนื้อ, แหล่งเนื้อ, sources, JOOX, NetEase, YouTube Music, LRCLIB, ซับ YouTube, คำอธิบายคลิป, Musixmatch, token, ค้นใหม่, ชื่อเพลง ศิลปิน, ใช้ข้อความนี้ + เวลา FA, ใช้เวลาของแหล่งนี้, เข้ากับเพลง %, เวลาตรง %
- `static/studio.html` ` .srcq{display:flex` ` .src{border` — CSS
- `static/studio.html` `id="srcbtn"` — ปุ่ม 🔎 หาเนื้อ (แถบเครื่องมือแถว 2)
- `static/studio.html` `// ===== 7d.` `const PROV = {` `async function openSources(opts = {}){` `async function mxmRow(){` `function renderSources(){` — POST …/sources, ชื่อแหล่ง, การ์ดผล (% เข้ากับเพลง / คลุมเสียงร้อง / เวลาตรง), ⭐ ระบบเลือก (pick จากเซิร์ฟเวอร์) ขึ้นก่อน, 🕳 มีแค่บางช่วงไว้ท้าย, ตั้ง/ลบ token ผ่าน /api/studio/settings
- `static/studio.html` `const how = b.dataset.src;` — ใช้ผล: fa (ข้อความ+เวลา FA) / own (เวลาของแหล่ง) / text (แล้วกด ✨ AI จับเวลาต่อ)
! ใช้ผลแล้วยังไม่บันทึกจนกด 💾 (ผ่าน mutate จึง ↶ ได้)

### แก้ไข + ย้อน/ทำซ้ำ (undo/redo) + บันทึก 💾
คำค้น: undo, redo, ย้อน, ทำซ้ำ, ⌘Z, บันทึก, save, ⌘S, บันทึกไม่ได้, รวม offset เข้าเวลาเนื้อ, bake, mutate, ยังไม่ได้แก้อะไร
- `static/studio.html` `id="savebtn"` `#savebtn.dirty{` `id="undobtn"` — HTML/CSS ปุ่ม (• = มีงานค้าง)
- `static/studio.html` `// ===== 8. แก้ไข (undo/redo)` `function mutate(fn, keepRows){` `function after(keepRows){` `function updateUndo(){` `function rippleFrom(i, delta){` — ทุกการแก้ผ่าน mutate (snapshot ≤100) → after() วาดใหม่ทุกส่วน; rippleFrom = เลื่อนบรรทัด i ถึงท้ายเพลง
- `static/studio.html` `async function save(){` `id="bake"` — PUT /api/studio/song/{vid}/lyrics {lines, offset} (ติ๊ก bake = ใส่ offset เข้าเวลาทุกบรรทัด), เสร็จแล้วเปิดเพลงใหม่แบบ 'bg'
! save ไม่ส่งถ้าไม่ได้แก้ — บันทึกแล้วเพลงกลายเป็น "แก้เอง" หลุดจากระบบเลือกเนื้ออัตโนมัติและผลตรวจเดิมถูกลบ · แก้ S.lines ตรง ๆ ไม่ผ่าน mutate = ย้อนไม่ได้และจอไม่วาดใหม่

### ตารางบรรทัด (เวลาเริ่ม / ยาว / ข้อความ) + ปุ่มรายบรรทัด + 👤 เสียงร้อง
คำค้น: ตารางบรรทัด, line table, แถว, บรรทัด, เวลาเริ่ม, ความยาว, ข้อความ, แก้ข้อความ, พิมพ์เนื้อ, แทรกบรรทัด, ลบบรรทัด, ⏱ ตั้งเวลาเป็นหัวเล่น, 👤, เสียงร้อง, voice, คนที่ 2, คนที่ 3, คอรัส, bg, เลือกบรรทัด, ดับเบิลคลิก, เพิ่มบรรทัดแรก
- `static/studio.html` `#rows{overflow-y:auto` ` .row{display:grid` ` .rowhd{display:grid` — CSS (สีตามเสียง v2/v3/vbg, แถวที่เลือก/กำลังร้อง)
- `static/studio.html` `// ===== 9. ตารางบรรทัด` `const VOICES = [` `function lineOf(l){` `function renderRows(){` `function selectRow(i, scroll){` `$('#rows').addEventListener('change'` — วาดตาราง, ปุ่ม data-r (play/m/p/now/voice/ins/del), แก้ในช่อง → mutate, Enter = ไปบรรทัดถัดไป
! บรรทัดมีฟิลด์ v (2/3/'bg') — โค้ดที่แทนที่ S.lines ทั้งชุดต้องคัด v ตามไปเอง (ดู ✨ AI จับเวลา / 🔎 ใช้ผล) ไม่งั้น 👤 หาย

### เครื่องมือเลื่อนเวลา: ระยะ / ทั้งเพลง / จากบรรทัดนี้ / ⇤ / ⤓ / ↔ / offset ⏱
คำค้น: เลื่อนเวลา, shift, ทั้งเพลง, จากบรรทัดนี้, ระยะ, step, ต่อท้ายบรรทัดก่อน, close gap, ย้ายมาที่หัวเล่น, ความยาวอัตโนมัติ, offset ทั้งเพลง, พาทั้งแถบข้างหลัง, ripple, 🔗, ลองเลื่อน
- `static/studio.html` ` .tools{display:flex` `#ripbtn.on{` ` .offrow{display:flex` — CSS แถบเครื่องมือ / ช่อง offset
- `static/studio.html` `id="stepsel"` `data-ed="closegap"` `data-ed="toplay"` `id="offin"` — HTML ปุ่ม / ช่อง
- `static/studio.html` `// ===== 10. เครื่องมือ` `function closeGap(){` `function toPlayhead(){` `const autoDur = ` — ⇤ ต่อท้ายบรรทัดก่อน, ⤓ ย้ายมาที่หัวเล่น (ดูด onset), ↔ ความยาวจากบรรทัดถัดไป (DUR_MIN..DUR_MAX)
- `static/studio.html` `closest('[data-ed]')` `$('#offin').addEventListener` — ตัวรับทุกปุ่ม data-ed (off/shiftall/shiftfrom/closegap/toplay/redur/trial/usesugg/reload/addfirst) + ช่อง offset (−15..15 วิ)
! offset ทั้งเพลงเก็บแยกจากเวลาบรรทัด (บวก = ซับขึ้นช้าลง) — เวลาในตารางไม่รวม offset จนกว่าจะติ๊ก "รวมเข้าเวลาเนื้อตอนบันทึก"

### ✨ AI จับเวลา / 📋 นำเข้า LRC-เนื้อเปล่า / 🕘 ประวัติฉบับก่อน
คำค้น: AI จับเวลา, autotime, จับเวลาอัตโนมัติ, FA, whisper, ถอดเสียง, asr, นำเข้า, import, LRC, วางเนื้อ, เนื้อเปล่า, ประวัติ, versions, ฉบับก่อนหน้า, ย้อนรุ่น, 20 รุ่น
- `static/studio.html` `id="aibtn"` `id="aieng"` `id="impbtn"` `id="verbtn"` — HTML ปุ่มแถวที่ 2 (ตัวเลือกเครื่อง FA/whisper โชว์เมื่อ FA พร้อม)
- `static/studio.html` `$('#aibtn').onclick` — POST …/autotime {texts, engine}; ยังไม่เคยถอดเสียง (need asr) → ส่งเข้าคิว do:'asrtext'
- `static/studio.html` `function parseLRC(txt){` `$('#impbtn').onclick` — แปลง LRC (หลายแท็กเวลาต่อบรรทัด), เนื้อเปล่ายืมเวลาเดิมตามลำดับ
- `static/studio.html` `$('#verbtn').onclick` `closest('[data-ver]')` — รายการรุ่นที่บันทึก (S.detail.edits) → GET …/edit/{ts} โหลดเข้าตัวแก้ (ต้องกด 💾 อีกที)

### พรีวิวแบบจอทีวี + แถบเล่น (เล่น / ความเร็ว / วนบรรทัด / วิดีโอ-เสียงร้อง / โหมด) + lyrcore
คำค้น: พรีวิว, preview, จอทีวีจำลอง, เล่น, หยุด, play, seek, ความเร็ว, ช้าลง, ¼×, ½×, วนบรรทัด, loop, 🔁, เสียงร้องแยก, vocals, วิดีโอ, โหมดพรีวิว, เลื่อนขึ้น, 2 บรรทัด, ลองเลื่อน, trial, lyrcore, ●●●, ♪
- `static/studio.html` ` .pv{position:relative` ` .tp{display:flex` — CSS กรอบพรีวิว (หน่วย cqw) + แถบเล่น
- `static/studio.html` `<div class="pv dual kara" id="pv">` `id="tp"` — HTML พรีวิว + แถบเล่น (#play #seek #loopbtn #spd #msrc #pvm #fsbtn)
- `static/studio.html` `// ===== 11. สื่อ + พรีวิวแบบจอทีวี` `function setMedia(kind, at, first){` `function setLoop(on){` `const effOff = ` `function pvLines(){` `function renderPreview(pos){` `function tick(){` — เลือกไฟล์ /song/{vid}/video.mp4 | audio.m4a | vocals.m4a, วนบรรทัด, offset จริง = offset + trial, เฟรมซับจาก lycFrame, rAF loop ไฮไลต์แถวที่กำลังร้อง
- `static/studio.html` `// <lyrcore>` `const LYC = {` `function lycFrame(L, t, o){` — สำเนาบล็อกตรรกะซับของจอทีวี
! บล็อก // <lyrcore> … // </lyrcore> ต้องเหมือน static/player.html ทุกตัวอักษร — แก้ที่เดียวแล้วคัดลอกทั้งบล็อก ตรวจด้วย python3 scripts/eval_lyrics.py core · พรีวิวห้ามจับคู่บรรทัดเอง ใช้ lycPrep/lycFrame เท่านั้น

### แถบคลื่นเสียง (timeline) + คลื่นเสียงร้อง / จุดเริ่มร้อง 🧲
คำค้น: แถบคลื่น, waveform, timeline, คลื่นเสียง, คลื่นเสียงร้อง, PCM, envelope, onset, จุดเริ่มร้อง, ลาก, drag, ก้อนบรรทัด, ขอบ, แม่เหล็ก, ดูดติด, snap, magnet, Alt, Shift, ซูม, zoom, ⤢, ล้อเมาส์, หัวเล่น, playhead, ธง 🚩, ขีดส้ม
- `static/studio.html` ` .tlw{position:relative` `#tl{display:block` `<canvas id="tl">` `id="zfit"` — CSS/HTML แถบคลื่น + ปุ่มซูม
- `static/studio.html` `// ===== 13. แถบคลื่นเสียง` `function drawTL(){` `function paintTL(){` `function hit(x, y){` `function magnet(t, targets){` `function startTargets(i, off){` `cv.addEventListener('pointermove'` `function zoomTo(z, anchorT, anchorX){` — วาด (คลื่น/onset/ก้อน/จุดคลาด/ขีดส้ม/ธง/หัวเล่น), จับขอบ start/end/move, ดูดเข้าท้าย-ต้นบรรทัด/จุดที่วัดได้/จุดเริ่มร้อง/หัวเล่น, Shift หรือ 🔗 = พาทั้งแถบ, ล้อ = เลื่อน, Ctrl+ล้อ = ซูม
- `static/studio.html` `id="snap"` `id="tlmsg"` `// ===== 12. เสียงร้อง: PCM` `async function loadEnvelope(vid){` `function findOnsets(env){` `function snapTap(t){` — โหลด vocals.m4a (หรือ audio.m4a) → โมโน 8 kHz + RMS 100 Hz, หาจุดเริ่มร้อง, ดูดตอนแตะ
! เรียก drawTL() (รวบเป็นเฟรมละครั้ง) ไม่ใช่ paintTL() ตรง ๆ · Alt ค้าง = ปิดการดูดทุกแบบ · ลากคิดจากตำแหน่งตอนกด (drag.orig) จึงไม่สะสม

### โหมดแตะตามจังหวะ ⏺
คำค้น: แตะจังหวะ, tap, tap mode, ⏺, T, Enter, Space, ย้อนการแตะ, Backspace, จับเวลาด้วยมือ, แตะครบทุกบรรทัด
- `static/studio.html` ` .tapbar{margin` `#tapbtn.on{` `id="tapbtn"` — CSS/HTML ปุ่ม + แถบบอกบรรทัดถัดไป
- `static/studio.html` `// ===== 14. โหมดแตะตามจังหวะ` `function setTap(on){` `function updTapBar(){` `function tapStamp(){` `function tapBack(){` — แตะ = บรรทัดนี้เริ่มตอนนี้ (ดูด onset) + บรรทัดหลังเลื่อนตามทั้งแถบ + ตั้งความยาวบรรทัดก่อน; ⌫ ย้อน
! tapStamp push undo เอง (ไม่ผ่าน mutate) — tapBack ต้อง pop undo คู่กัน

### ⛶ โหมดแก้เต็มจอ
คำค้น: เต็มจอ, fullscreen, focus mode, ⛶, ปุ่ม F, โหมดแก้เต็มจอ, แถบคลื่นสูง
- `static/studio.html` `body.focus .ed{` `#fsbtn.on{` — CSS grid พรีวิว | ตาราง ด้านบน, แถบคลื่นสูง 30vh ด้านล่าง
- `static/studio.html` `// ===== 15.` `function setFocus(on){` — สลับ body.focus + requestFullscreen; ออก fullscreen ด้วย Esc ของเบราว์เซอร์ = ออกจากโหมดนี้ด้วย

### คีย์ลัด ⌨️
คำค้น: คีย์ลัด, shortcut, keyboard, ปุ่มลัด, Space, ลูกศร, [ ], ⌘S, ⌘Z, คีย์บอร์ดภาษาไทย, ช่วยเหลือ, help
- `static/studio.html` `// ===== 16. คีย์ลัด` `document.addEventListener('keydown', e => {` `const isTyping = ` — ตัวรับคีย์ทั้งหมด (⌘S / ⌘Z / แตะ / ลูกศร / [ ] / T L Z F G P)
- `static/studio.html` `$('#helpbtn').onclick` — กล่อง ⌨️ คีย์ลัด (ข้อความช่วยเหลือ)
! คีย์ตัวอักษรใช้ e.code (KeyT, BracketLeft) จึงใช้ได้กับคีย์บอร์ดภาษาไทย · ทำงานเฉพาะแท็บเพลงและตอนไม่ได้พิมพ์ (isTyping) · เพิ่มคีย์ใหม่ต้องแก้ข้อความใน $('#helpbtn').onclick ด้วย

### ▶ แท็บกำลังเล่น & คิว (เนื้อมาจากไหน + ✨ เลือกเนื้อดีที่สุด)
คำค้น: กำลังเล่น, คิว, queue, เนื้อมาจากไหน, ที่มาเนื้อ, เลือกเนื้อดีที่สุด, best, ✨, เปิดในตัวแก้, จำนวนคิวบนแท็บ
- `static/studio.html` ` .qcard{background` ` .qhead{display:grid` — CSS การ์ดคิว
- `static/studio.html` `id="vqueue"` `id="qcnt"` — HTML แท็บ + ตัวนับบนแท็บ
- `static/studio.html` `// ===== 16c.` `function fromText(i){` `function bestLine(i){` `function qHead(i, pos){` `function renderQueue(){` `$('#qlist').addEventListener` `function updateQCount(){` — ข้อมูลสดจาก ws (S.room), การ์ดไม่สร้างใหม่ (กันกระพริบ), ✨ POST action do:'best', ✏️ เปิดในตัวแก้
! เนื้อที่แก้เอง/เลือกเอง (MANUAL_SRC) ระบบไม่เปลี่ยนให้ — ปุ่ม ✨ ถูกปิด

### 📺 แท็บหน้าจอหลัก: ตั้งค่าทีวี + พรีวิวจำลอง + รูปมุมขวาบน
คำค้น: ตั้งค่าจอ, หน้าจอหลัก, tv settings, 📺, ทีวี, สีซับ, ขนาดซับ, สีคาราโอเกะ, ความสว่าง, พื้นหลังใต้ซับ, เงา, ขอบตัวอักษร, ยกซับ, QR, เวลาเพลง, การ์ดต่อไป, การ์ดเพิ่มเข้าคิว, โลโก้, รูปมุมขวาบน, อัปรูป, ข้อความหน้าจอว่าง, ชิปหลังชื่อเพลง, ซ่อนแถบชื่อ, นับถอยหลัง, แยกเสียงร้อง, คืนค่าเริ่มต้น
- `static/studio.html` ` .tvgrid{display:grid` ` .tvform fieldset{` ` .tvpv{position:relative` — CSS ฟอร์ม + พรีวิวจำลอง (cqw แทน vw ของทีวี)
- `static/studio.html` `id="vtv"` `id="tvpv"` — HTML
- `static/studio.html` `// ===== 16d.` `const TV_CHIP_LB = ` `async function loadTv(){` `function renderTvForm(){` `function fillTvForm(){` `function tvSet(patch){` `function renderTvPreview(){` — GET/POST /api/studio/tv (บันทึกเอง หน่วง 300ms), อัป/ลบรูป PUT/DELETE /api/studio/tv/logo (≤10 MB), คืนค่าเริ่มต้น
! ค่าใหม่ (data-tv="key") ต้องเพิ่มใน TV_SCHEMA ของ server.py + applyTv ใน static/player.html + renderTvPreview ที่นี่ · ชิปใหม่ต้องตรงกับ TV_CHIPS (server.py) และ CH ใน static/player.html

### ✂️ แท็บตัดต่อ & คอมโบ (แทร็กสองเพลง + จอทีวีเล็ก + แก้คอมโบ)
คำค้น: ตัดต่อ, ตัดคลิป, จุดเริ่ม, จุดจบ, trim, เฟดรายเพลง, คอมโบ, combo, เพลย์ลิสต์, ฟังรอยต่อ, จอเล็ก, บันทึกคิวเป็นคอมโบ, โหมด custom, หน้าอินโทร, มือถือ, iPad, จอสัมผัส, touch, ลากด้วยนิ้ว, ซูมแทร็ก, ปุ่มขยับละเอียด, ดูดเข้าท่อน, 🧲
- `static/studio.html` `id="vcut"` ` .cutgrid{display:grid` ` .ctrk .cv{` ` .cbx{background` — HTML/CSS: รายการซ้าย (คิว/คอมโบ), จอเล็ก #ctvv (+ #ctvv2 ไว้ฟังรอยต่อ) + แผ่นดำ #ctvbk + ซับ #cl1/#cl2, แทร็ก A/B, กล่องแก้คอมโบ
- `static/studio.html` ` .cgrip{position:absolute` `class="cstick"` `@media (max-width:999px) and (min-height:600px){` `@media (pointer:coarse){` — มือถือ/iPad: ที่จับเป็น DOM (นิ้ว 44px, touch-action none) บน canvas pan-y, จอแคบคอลัมน์เดียว + แถบแคปซูล + จอเล็ก/แถบเล่นติดด้านบน (#vcut overflow visible), ปุ่ม 44px, มือถือแถวปุ่ม ±วินาทีแยกบรรทัด
- `static/studio.html` `// ===== 16e. ✂️ ตัดต่อ` `function cutEntries(){` `function cutEff(e){` `async function cutEnsure(vid){` `async function cutEnv(vid){` `function renderCut(){` `function cutTrackHtml(` — รายการเพลงที่ตัด, ค่าที่ใช้จริง (ว่าง = อัตโนมัติ/ต้นคลิป/ท้ายคลิป/ค่า 📺), GET /api/studio/song/{vid}/clip + lyrics + คลื่นเสียงร้อง 10 จุด/วิ
- `static/studio.html` `function cutWin(` `function cutMap(` `function cutDraw(el){` `function cutSnap(` `function cutSave(e){` — ช่วงที่แสดง (ทั้งเพลง/🔍 ต้น/🔍 ท้าย ล็อกระหว่างลาก) + ตัวแปลงเวลา↔พิกเซลตัวเดียว, วาดคลื่น/ท่อนร้อง/ช่วงตัด/เส้นลาดเฟด + วางที่จับ DOM, ดูดต้นท่อน (🧲 / Alt = ไม่ดูด) รัศมีตามซูม, บันทึกหน่วง 400ms
- `static/studio.html` `function cutNudge(` `function cutSeekAt(` `function cutPointerEnd(` `const cutTyping = ` — ปุ่ม −1 −.1 +.1 +1 / เฟด ±0.5, แตะแทร็ก = ไปตรงนั้น (เมาส์ตอนกด / นิ้วตอนปล่อยถ้าขยับ < 8px), จบการลากทั้ง pointerup/pointercancel/lostpointercapture (จำ pointerId), พิมพ์เวลาอยู่ห้ามสร้างแทร็กใหม่
- `static/studio.html` `const cutVid = ` `function cutAudioOn(` `function cutLoadPv(` `function cutJoin(){` `function cutTick(){` — จอเล็กเล่นไฟล์ในเครื่อง + จำลองเฟด (iOS ปรับ volume ไม่ได้ -> GainNode) + ซับจาก lycFrame, play() เรียกตรงในจังหวะที่แตะ (#t= เริ่มตรงจุด), ▶ ฟังรอยต่อ (A จบ−8 วิ → B ในวิดีโอตัวที่สองที่ปลดล็อกไว้ จุดเริ่ม 8 วิ)
- `static/studio.html` `function renderCutCombo(){` `async function cutComboClick(b){` `async function cutComboSave(c){` `async function cutComboFromQueue(){` `function cutRoom(){` — ชื่อ/เรียง/ลบ/ค้นเพลงเพิ่ม, ▶ เพิ่มเข้าคิว (ws addcombo), 💾 คิว → คอมโบ (คัดค่าที่เห็นจริงรวมค่าอัตโนมัติไปเป็นค่าตัดเอง), วาดใหม่เมื่อคิว/ค่าจอเปลี่ยน
! state แยกจาก S ของตัวแก้เนื้อ (CUT) — แก้ที่นี่ไม่ทำให้เนื้อ dirty · เพลงในคิว = ค่าประจำเพลง (trim.json ใช้ตอนเปิด Custom) / ใบคิวจากคอมโบ = แก้รอบนี้ (queue clip) / โหมดคอมโบ = บันทึกทั้งคอมโบ
! SPAN_MIN (15 วิ) ต้องตรงกับ server.py · ซับในจอเล็กเรียก lycPrep/lycFrame อย่างเดียว ห้ามแก้บล็อก lyrcore
! คลื่นเสียงมาจาก /clip → env (แคช _va ฝั่งเซิร์ฟเวอร์) ไม่มีค่อยถอดรหัสไฟล์เองแบบเดิม · ทดสอบจอสัมผัสด้วย headless Chrome + Input.dispatchTouchEvent (แตะระหว่างหน้ายังไหล = เบราว์เซอร์นับเป็นหยุดหน้า)

### websocket ของ Studio (อัปเดตสด) + สถานะเชื่อมต่อ
คำค้น: websocket, ws, อัปเดตสด, live update, เชื่อมต่อแล้ว, กำลังเชื่อมต่อ, รีเฟรชรายการ, archiveRev, jobsRev, Studio หลายเครื่อง
- `static/studio.html` ` .st{margin-left:auto` `id="ststr"` — CSS/HTML ป้ายสถานะบนหัว
- `static/studio.html` `// ===== 17. websocket` `function scheduleRefresh(){` `function connect(){` — state → เทียบ sig (archiveRev/jobsRev/คิว) แล้วค่อยดึง /api/studio/songs (เว้น ≥1.5 วิ), อัปเดตแท็บคิว + ค่าจอที่ Studio เครื่องอื่นเปลี่ยน

## server.py — ตั้งค่า เครือข่าย และการเริ่มเซิร์ฟเวอร์

### พาธไฟล์ ค่าคงที่ และโฟลเดอร์เพลง (config / paths / song folders)
คำค้น: ตั้งค่า, config, พาธ, path, โฟลเดอร์เพลง, songs/yt, ชื่อโฟลเดอร์, videoId, lyrics-in, .studio.json, พอร์ต, port 8080, env, ตัวแปรแวดล้อม, KARA_ALLOWED_HOSTS, KARA_ASR_MODEL, KARA_STUDIO_PIN, KARA_REFINE, HF_HOME, แคชโมเดล, timeout, ย้ายโฟลเดอร์, migrate
- `server.py` `BASE = Path(__file__).parent` `DL_DIR = SONGS / "yt"` `LYRICS_IN = BASE / "lyrics-in"` `STUDIO_FILE = BASE / ".studio.json"` `PORT = 8080` — พาธหลัก (songs/, songs/yt/, songs/.thumbs, lyrics-in/, .studio.json) และพอร์ต
- `server.py` `os.environ.setdefault("HF_HOME"` `SEG_CACHE = BASE / "lyrics-preview" / "_seg"` `SEP_TIMEOUT = 30 * 60` — แคชโมเดล HF/torch อยู่ใน .cache/ ของโปรเจกต์, แคชผลถอดเสียง, timeout ของงานหนักแต่ละชนิด
- `server.py` `KARA_ALLOWED_HOSTS` `KARA_ASR_MODEL` `if os.environ.get("KARA_STUDIO_PIN"):` `REFINE_MODE = os.environ.get("KARA_REFINE"` — env ทั้งหมดที่ server.py อ่าน: Host เพิ่มเติมที่นับเป็นเครื่องตัวเอง / ชื่อโมเดล ASR (ที่นี่ใช้แค่แสดงใน /api/health) / PIN ของ Studio ที่ใช้แทนค่าในไฟล์ / โหมดซ่อมเวลา on|dry|off
- `server.py` `def _safe_name(` `def _song_dir(` `def _rescan_dirs(` `def _migrate_song_dirs(` `def _vid_ok(` — ตั้งชื่อโฟลเดอร์ "<ชื่อเพลง> [<videoId>]", แปลง videoId เป็นโฟลเดอร์จริง (สแกนใหม่ไม่เกินทุก 2 วิ), ตอนบูตเปลี่ยนชื่อโฟลเดอร์แบบเก่า <vid>/
! ผู้ใช้รันเซิร์ฟเวอร์จริงเองที่พอร์ต 8080: ห้ามรีสตาร์ท และห้ามเปิดซ้ำที่พอร์ตนี้ จะหาโฟลเดอร์เพลงต้องเรียก _song_dir(vid) เสมอ (ชื่อจริงมีชื่อเพลงนำหน้า ไม่ใช่ songs/yt/<vid>) ฟังก์ชันนี้ถูกเรียกทุก broadcast จึงห้าม raise

### ลิงก์เข้าใช้ / IP วงแลน / Cloudflare / QR (base URL / security)
คำค้น: ลิงก์, URL, base url, IP, LAN, วงแลน, QR, คิวอาร์, Cloudflare, tunnel, publicUrl, โดเมน, เปิดจากนอกบ้าน, trycloudflare, แบนเนอร์, เริ่มเซิร์ฟเวอร์, uvicorn, X-Forwarded-For, same-origin, CSRF, DNS rebinding, เครื่องตัวเอง, localhost
- `server.py` `def lan_ip(` `def lan_url(` `def base_url(` `@app.get("/qr.png")` — ลิงก์ที่ให้แขกเปิด: ใช้ publicUrl ใน .studio.json (Cloudflare) ก่อน ถ้าไม่มีใช้ http://<LAN IP>:8080, QR ชี้ไปที่ base_url()/r
- `server.py` `def _drop_stale_public_url(` `if __name__ == "__main__":` `uvicorn.run(app, host="0.0.0.0"` — ตอนสตาร์ท: ล้างลิงก์ *.trycloudflare.com เก่า, พิมพ์แบนเนอร์ลิงก์จอ/รีโมท/Studio/PIN, เปิด uvicorn ที่เชื่อ X-Forwarded-For จาก 127.0.0.1 เท่านั้น
- `server.py` `def _same_origin(` `def _is_local(` `def _host_is_local_name(` — ด่านความปลอดภัย: Origin ต้องตรงกับ Host (ws/POST), แยกเครื่องที่รันเซิร์ฟเวอร์ออกจากเครื่องอื่น, กัน DNS rebinding
! base_url() คำนวณใหม่ทุกครั้งเพราะ IP เปลี่ยนได้ และแก้ publicUrl ในไฟล์แล้วมีผลทันที จึงห้ามแคชลิงก์ แขกที่เข้าผ่าน Cloudflare ต้องไม่ถูกนับเป็นเครื่องตัวเอง (อย่าแก้ forwarded_allow_ips)

## server.py — หน้าเว็บและไฟล์ที่เสิร์ฟ

### หน้าเว็บจอทีวี / รีโมท / Studio และไฟล์สื่อ (pages / media / thumbs)
คำค้น: หน้าเว็บ, หน้าจอหลัก, จอทีวี, player, TV, /tv/รหัส, รีโมท, remote, /r, Studio, /studio, html, ไฟล์เพลง, video.mp4, ปก, cover, thumbnail, ภาพปก, thumb, media, ไฟล์ในเครื่อง, ไฟล์ซับ vtt, ไฟล์คีย์
- `server.py` `@app.get("/", response_class` `@app.get("/tv/{key}"` `@app.get("/r", response_class` `@app.get("/studio"` `def _tv_key_ok(` — เสิร์ฟ static/player.html, remote.html, studio.html: "/" เปิดได้เฉพาะเครื่องตัวเอง (เครื่องอื่นถูกส่งไป /r), /tv/<รหัส> ต้องตรงกับรหัส tv ใน .studio.json
- `server.py` `@app.get("/song/{vid}/{name}")` `@app.get("/media/yt/{vid}/{name}")` `@app.get("/media/{path:path}")` `_SONG_FILES = frozenset(` — ไฟล์ในคลังอ้างด้วย videoId (ชื่อไฟล์ต้องอยู่ในรายชื่อที่อนุญาต), URL เก่า /media/yt ถูก redirect, ไฟล์ที่วางเองใต้ songs/
- `server.py` `@app.get("/thumb/{video_id}")` `def _thumb_for(` `_THUMB_OK = re.compile(` — ดึงปกจาก i.ytimg มาแคชไว้ใน songs/.thumbs และกรอง URL ปกที่รีโมทส่งมา
! HTML อ่านจากดิสก์ใหม่ทุก request (no-store) แก้ static/*.html แล้วรีเฟรชก็เห็นผล ไม่ต้องรีสตาร์ท ถ้าจะเสิร์ฟไฟล์ชนิดใหม่ใต้ /song/ ต้องเพิ่มชื่อใน _SONG_FILES (หรือให้ตรง regex _VTT_NAME/_KEY_NAME) ไม่งั้นได้ 404

## server.py — ห้องคาราโอเกะ: สถานะ คิว และ WebSocket

### สถานะห้องและการ broadcast (Room state)
คำค้น: state, สถานะห้อง, room, broadcast, ส่งสถานะ, websocket, ws, เพลงที่เล่นอยู่, current, position, ตำแหน่งเพลง, jobsRev, archiveRev, baseUrl, ฟิลด์บนการ์ด, dlStatus, sepStatus, lyrStatus, มือถือค้าง
- `server.py` `class Room:` `def state(self)` `async def broadcast(self)` `async def send_all(self, msg` `room = Room()` — สถานะทั้งห้อง (queue/current/playing/mix/lyrMode/autoplay/tv/position) และ JSON ที่ส่งให้ทุกจอ
- `server.py` `async def _ws_send(` `def _ws_drop(` `WS_SEND_TIMEOUT = 5.0` `def _jobs_rev(` — ส่งให้แต่ละเครื่องโดยรอไม่เกิน 5 วิ (มือถือที่ล็อกจอจะไม่ถ่วงทั้งห้อง) และสร้างลายนิ้วมือของงานเบื้องหลังให้ Studio รู้ว่าต้องดึงรายการใหม่
! state() เรียก _dl_fields/_sep_fields/_lyr_fields/_fix_fields กับทุก item ในทุก broadcast ค่าที่เติมจึงต้องคำนวณเร็ว (แคชด้วย mtime) และห้าม raise ส่วน _fix_fields ต้องอยู่ท้ายสุด

### คำสั่งจากรีโมท/จอผ่าน /ws และคิวเพลง (queue / skip / play)
คำค้น: คิว, queue, เพิ่มเพลง, add, ข้ามเพลง, skip, next, เพลงต่อไป, เพลงจบ, ended, ลบออกจากคิว, remove, เลื่อนคิว, up, down, เล่นเลย, playnow, หยุด, เล่นต่อ, toggle, pause, เริ่มเพลงใหม่, restart, จอหลัก, hello, evicted, ยึดจอ, pos, คนร้อง, singer
- `server.py` `@app.websocket("/ws")` `if act == "hello":` `if act == "pos":` `if act == "add":` — จุดรับคำสั่งทั้งหมด: hello (จอหลักมีได้ทีละเครื่อง เครื่องใหม่ไล่เครื่องเก่า), pos (เวลาที่จอรายงาน), add (เข้าคิว + สั่งโหลด/แยกเสียง/หาเนื้อ + ลงประวัติ)
- `server.py` `elif act == "next":` `elif act == "ended":` `elif act == "playnow":` `elif act == "toggle":` `elif act == "restart":` `elif act == "remove":` — ข้ามเพลง/เพลงจบ/เล่นเลย/หยุด-เล่นต่อ/เริ่มใหม่/ลบออกจากคิว (up/down อยู่ถัดจาก remove)
- `server.py` `def add(self, item` `def next(self)` `def move(self, item_id` `def _targets_current(` `def _finite(` — เมธอดจัดคิวของ Room (next รีเซ็ตไกด์ร้องกับคีย์ทุกเพลง), กันข้ามสองเพลงจากคำสั่งที่มาช้า, กรองตัวเลข NaN/Inf
! ทุกคำสั่งรันภายใต้ room.lock ห้าม await งานยาวหรือยิงเน็ตข้างใน (ชื่อเพลงจาก oEmbed ดึงก่อนเข้า lock) คำสั่งที่เปลี่ยนลำดับคิวต้องเรียก _reprioritize() ด้วย การลบออกจากคิวไม่ยกเลิกการโหลด เพราะตั้งใจสะสมคลังไว้

### เฟดก่อนเปลี่ยนเพลง / โหมด Custom (จุดเริ่ม-จบ) / ⏩ ข้ามอินโทร / คอมโบเข้าคิว
คำค้น: เฟด, fade, fading, โหมด custom, จุดเริ่ม, จุดจบ, startAt, endAt, introEnd, ข้ามอินโทร, skipintro, seekToken, คอมโบ, addcombo
- `server.py` `def _play_span(` `def _span_fields(` `def _intro_end(` `def _auto_span(` `def _lyr_span(` `def _fade_out_sec(` — (เริ่ม, จบ, เฟดเข้า, เฟดออก) ของใบคิว: คอมโบ = clipStart/clipEnd เสมอ / เพลงทั่วไปเฉพาะ tv.custom: trim.json > อัตโนมัติ (เวลาเนื้อ + offset ∓ customLead/customTail) · state เติม endAt/fadeIn/fadeOut/introEnd ของเพลงที่เล่นอยู่ทุก broadcast
- `server.py` `self.fading: str | None` `def next(self)` — next() ตั้ง pos = startAt (จอ seek เองผ่าน resumeAt) + ล้าง fading
- `server.py` `def _begin_fade(` `async def _finish_fade(` `def _playnow(` — next/playnow ตอนกำลังเล่น + fadeOut > 0 = ตั้ง fading แล้ว sleep นอก lock ค่อยเปลี่ยนเพลง; กดซ้ำ = ทันที, restart = ยกเลิก
- `server.py` `elif act == "skipintro":` `elif act == "addcombo":` `async def _queue_yt(` `def _history_add(` — ⏩ ตั้ง pos = introEnd + seek_token += 1 (เฉพาะยังไม่พ้นอินโทร); คอมโบเข้าคิวทีละเพลงทางเดียวกับ add พร้อม clip* + combo
! _finish_fade ต้องตรวจ fade_token + current id ก่อนเปลี่ยนเพลง (งานเก่าค้าง/ถูกแทน) · ended ยังเปลี่ยนทันที (จอเฟดเองก่อนส่ง)

### เสียงไกด์ / ระดับเสียง / เปลี่ยนคีย์ / โหมดเนื้อ (mix / key / lyrMode)
คำค้น: เสียงร้องไกด์, vocal, ดนตรี, music, master, ระดับเสียง, volume, mix, คีย์, key, pitch, เปลี่ยนคีย์, เลื่อนคีย์, ครึ่งเสียง, pedalboard, โหมดเนื้อ, lyrMode, karaoke, scroll, dual, คอรัส, voices, 👥
- `server.py` `elif act == "mix":` `MIX_RANGE = {` `elif act == "lyrmode":` `LYR_MODES = (` `elif act == "voices":` — รับค่า mix (vocal/music/master 0-100, key -6..+6), โหมดแสดงเนื้อ scroll|dual|karaoke|off, สวิตช์ 👥 แยกเสียงร้อง (บันทึกลง tv.json)
- `server.py` `async def _enqueue_key(` `async def _key_worker(` `def _pitch_shift_file(` `def _key_path(` `def _drop_key_files(` — สร้างสเต็มของคีย์ใหม่ล่วงหน้าเป็นไฟล์ vocals.k+2.m4a / no_vocals.k+2.m4a (ใช้ pedalboard ถ้าไม่มีใช้ ffmpeg)
! แยกเสียงใหม่แล้วต้องลบไฟล์คีย์เก่า (_drop_key_files) และชื่อไฟล์คีย์ต้องตรง regex _KEY_NAME ไม่งั้น /song/ จะไม่เสิร์ฟ

### สุ่มเพลงอัตโนมัติเมื่อคิวหมด (autoplay)
คำค้น: สุ่มเพลง, autoplay, เล่นต่ออัตโนมัติ, คิวหมด, random, สุ่มจากคลัง, 🔀
- `server.py` `def _autoplay_pick(` `async def _autoplay_fill(` `AUTO_SINGER =` `elif act == "autoplay":` — เปิด/ปิดจากรีโมท เมื่อจอว่างจะสุ่มเพลงที่มี video.mp4 (เลี่ยงเพลงที่เพิ่งสุ่ม), ไม่ลงประวัติและไม่นับ plays, watchdog ก็เติมเพลงให้ด้วย

### ประวัติเพลงที่สั่ง (history)
คำค้น: ประวัติ, history, เพลงที่เคยร้อง, ใครร้องอะไร, history.json, ชื่อเพลง YouTube: id
- `server.py` `HISTORY_FILE = BASE / "history.json"` `HISTORY_MAX = 200` `def _load_history(` `def _save_history(` `def _fix_history_titles(` `if act == "history":` — ประวัติรวมของทุกเครื่อง (สูงสุด 200 รายการ เขียนแบบ atomic), แก้ชื่อ "YouTube: <id>" เป็นชื่อจริง, ส่งให้รีโมทผ่าน ws

### แจ้งซับไม่ตรงจากรีโมท 🚩 (reports)
คำค้น: แจ้งซับไม่ตรง, รายงาน, report, 🚩, ซับช้า, ซับเร็ว, พิมพ์ผิด, เนื้อผิด, แก้แล้ว, lyrics.reports.json
- `server.py` `elif act == "report":` `REPORT_TAGS = (` `def _add_user_report(` `def _read_reports(` `def _reports_file(` — แขกกดแจ้งบนการ์ดเพลงที่กำลังเล่น ระบบเก็บลง lyrics.reports.json (แท็ก late/early/typo/..., เก็บ 50 รายการ) โดยไม่ซ่อมอัตโนมัติ
- `server.py` `@app.post("/api/studio/song/{vid}/reports")` — Studio ติ๊ก "แก้แล้ว"/เปิดใหม่ ทีละ id หรือ all_done
! รายงานแยกไฟล์ออกจาก lyrics.check.json โดยตั้งใจ เพราะการบันทึกเนื้อใน Studio ลบ check.json ทุกครั้ง

## server.py — API ค้นหา คลัง และสถานะระบบ

### ค้นหา YouTube และเช็คฝังได้ (search / embeddable)
คำค้น: ค้นหา, search, ค้นเพลง, YouTube, yt-dlp, ผลค้นหา, ฝังได้, embeddable, embed, oEmbed, วางลิงก์, ชื่อเพลงจริง, ช่อง, channel, กรอง, ไม่ใช่เพลง, ซ่อน, ออกกำลังกาย, แอโรบิค, ตลก, รีแอค, สัมภาษณ์, ไลฟ์สด, 10 นาที, filter
- `server.py` `@app.get("/api/search")` `def _search(` `def _annotate(` — ค้นด้วย yt-dlp (ดึงแค่ metadata) เผื่อ 2 เท่า (ytsearch24) กรองแล้วเหลือ 12, ส่ง hidden = จำนวนที่ซ่อน, แล้วเช็คว่าฝังได้ไหมแบบขนาน 8 เธรด เรียงคลิปที่ฝังได้ขึ้นก่อน
- `server.py` `SEARCH_MAX_SEC = ` `_NOT_SONG_RE = re.compile(` `def _is_song_clip(` — ซ่อนคลิปที่ไม่ใช่เพลง: ยาวเกิน 10 นาที (= SEP_MAX_SEC), ไลฟ์ที่ยังออกอากาศ, ชื่อคลิป/ช่องมีคำออกกำลังกาย/ตลก/รีแอค/สอนร้อง-เล่น/สัมภาษณ์/เบื้องหลัง · รีโมทผลว่างแต่ hidden > 0 ขึ้น "ไม่พบเพลง — ซ่อน N คลิป" (ใน static/remote.html ฟังก์ชัน search)
! ซ่อนเสมอแม้แขกพิมพ์คำนั้นเอง (ผู้ใช้เลือก) · คำไทยห้ามสั้นจนชนชื่อเพลง ("ฮา", "สอน", "แกล้ง") · _swipe_yt (PU Match) ใช้ _search จึงโดนกรองด้วย · วางลิงก์ (/api/embeddable) ไม่กรอง
- `server.py` `@app.get("/api/embeddable")` `def _oembed(` `def _embeddable(` `def _yt_info(` — ตอนวางลิงก์: เช็คว่าเจ้าของปิดการฝังไหม (oEmbed ตอบ 401/403) และดึงชื่อจริง/ช่อง, แคช 1 ชม.

### คลังเพลงในเครื่องและสถานะเพลงก่อนเพิ่ม (archive / songinfo / library)
คำค้น: คลังเพลง, archive, เพลงที่โหลดแล้ว, เพลงยอดนิยม, plays, จำนวนครั้ง, songinfo, สถานะก่อนเพิ่ม, library, ไฟล์ในเครื่อง, info.json, duration
- `server.py` `@app.get("/api/archive")` `def _song_meta(` — ทุกเพลงที่มี video.mp4 เรียงตามจำนวนครั้งที่ถูกสั่ง (นับจากประวัติ) พร้อม stems/จำนวนบรรทัด/ชนิดเนื้อ, ชื่อและความยาวอ่านจาก info.json (แคชด้วย mtime)
- `server.py` `@app.get("/api/songinfo")` `@app.get("/api/library")` — สถานะเพลงก่อนกดเพิ่ม (ใช้ตัวเติมฟิลด์ชุดเดียวกับคิว, เพลงที่ยังไม่เข้าไปป์ไลน์จะได้ "new") / ไฟล์สื่อที่วางเองใน songs/ (ไม่รวม yt/)

### 🃏 PU Match ฝั่ง server (swipe)
คำค้น: PU Match, swipe, ปัดเพลง, การ์ดสุ่ม, คำค้น YouTube, สุ่มเพลง
- `server.py` `# ===== 🃏 PU Match` `@app.post("/api/swipe")` `def _swipe_pick(` `def _swipe_yt(` `SWIPE_YT_Q = ` — การ์ด PU Match: ทุกเพลงในเครื่อง (ตัด seen/คิว, สุ่มถ่วงน้ำหนัก plays/เนื้อ/ไกด์) ไม่พอเติมจาก YouTube ด้วยคำค้นเดียว SWIPE_YT_Q (แคช 30 นาที, ตัดคลิปปิดฝัง)
! _song_meta ห้ามเก็บ info.json ทั้งก้อน (ไฟล์ละหลายร้อย KB) · แนวเพลง (genres.json, แท็บ 🗂 ใน Studio) ถูกลบออกแล้ว 2026-10-06

### สุขภาพระบบและ log จากจอ (health / clientlog)
คำค้น: health, เช็คระบบ, สถานะระบบ, debug, ดีบัก, คิวงาน, demucs version, yt-dlp version, ffmpeg, GPU ทำอะไรอยู่, log, clientlog, error จากจอ, console
- `server.py` `@app.get("/api/health")` `def _lyr_health(` — เวอร์ชัน yt-dlp/demucs, ffmpeg, ลำดับคิว dl/sep, งานที่กำลังใช้ GPU, สรุปเนื้อแยกตามแหล่ง, ใส่ ?search=1 เพื่อทดสอบค้นหาจริง
- `server.py` `@app.post("/api/clientlog")` `@app.get("/api/clientlog")` — จอทีวีส่ง error ของ JS กลับมาเก็บ (50 รายการล่าสุด, ต้อง same-origin, ไม่เกิน 64KB) และพิมพ์ลง log ของเซิร์ฟเวอร์

## server.py — งานเบื้องหลัง (ไปป์ไลน์เตรียมเพลง)

### ลำดับงาน คิว GPU แย่งคิว และงานตอนบูต (priority / preempt / watchdog / backfill)
คำค้น: งานเบื้องหลัง, background job, คิวงาน, ลำดับความสำคัญ, priority, GPU, แย่งคิว, preempt, watchdog, งานค้าง, backfill, ตอนบูต, startup, subprocess, โปรเซสลูก, kill, เพลงถัดไปไม่มีไกด์
- `server.py` `class _Pending:` `def _prio_map(` `_BACKLOG = 1 << 20` `async def _reprioritize(` — คิวงานทุกชนิดเรียงตามลำดับคิวห้องปัจจุบัน (0 = เพลงที่เล่นอยู่, 1..N = ลำดับในคิว, เพลงนอกห้อง = backlog), ปลุกทุกไปป์ไลน์เมื่อคิวขยับ
- `server.py` `class _HeavyGate:` `def _preempt_heavy(` `def _run_child(` `def _kill_children(` — ให้สิทธิ์ GPU ทีละงานกับเพลงอันดับดีที่สุด, ฆ่างาน sep/lyr/verify ของเพลงท้ายคิวเมื่อเพลงที่เล่นอยู่/เพลงถัดไปรอ (เว้น 20 วิ, ไม่เกิน 2 ครั้งต่อเพลง), ทะเบียนโปรเซสลูก
- `server.py` `async def _lifespan(` `async def watchdog(` `WATCHDOG_EVERY = 10.0` — ตอนบูต: เปลี่ยนชื่อโฟลเดอร์ แล้ว backfill แยกเสียง/หาเนื้อ/best/words/verify ของเพลงเก่า แล้วตรวจภาษา, watchdog ทุก 10 วิเรียก reprioritize และ autoplay, ตอนปิดฆ่าโปรเซสลูกทั้งหมด
- `server.py` `def _drop_tail_junk(` `LYR_TAIL_JUNK = ` — backfill: ลบบรรทัดที่เวลาเลยท้ายคลิป > 2 นาที (เครดิต [999:00] ของ JOOX) จากเนื้ออัตโนมัติ สำรองลง 🕘 แล้วทำไล่สีใหม่ (เนื้อที่คนใส่เองไม่แตะ)
! เซิร์ฟเวอร์จริงรันสคริปต์ใน scripts/ (gen_lyrics, fa_align, lyrics_refine, ocr_lyrics) และ demucs เป็น subprocess ทุกงาน แก้สคริปต์แล้วงานถัดไปได้ผลทันที จึงต้องรักษา CLI/exit code/JSON บรรทัดสุดท้ายให้เข้ากันได้ ส่วนโมดูลที่ import เข้าโปรเซสหลัก (LS, LC, lyrics_refine.check_timing, gen_lyrics ใน autotime/sources, lyrics_more, verify_lyrics) จะใช้โค้ดเก่าจนกว่าผู้ใช้รีสตาร์ทเอง
! _preempt_heavy ห้ามมี await เพราะถูกเรียกตอนถือ room.lock และห้ามแคช _prio_map

### ดาวน์โหลดจาก YouTube ด้วย yt-dlp (download)
คำค้น: ดาวน์โหลด, โหลดเพลง, download, yt-dlp, video.mp4, audio.m4a, โหลดไม่สำเร็จ, โหลดใหม่, ซับ YouTube, auto-caption, sub.th.vtt, ลองใหม่, fragment, โหลดไม่ได้, บอท, not a bot, ล็อกอิน, คุกกี้, cookies, Chrome, Keychain, KARA_YT_COOKIES, node, js runtime
- `server.py` `async def _download_worker(` `async def _ensure_downloader(` `def _download_audio(` `def _download_video(` — โหลดทีละเพลงตามลำดับคิว: เสียง + metadata ก่อน (สั่งแยกเสียงทันที + ดึงคำบรรยายอัตโนมัติ + เริ่มหาเนื้อทันที) แล้วโหลดภาพมา mux กับ audio.m4a, ลองซ้ำ 2 รอบ
- `server.py` `def _since_add(` `_added_at: dict` — log ทุกขั้น (dl/lyr/sep/best) บอก "หลังกดเพิ่ม X วิ"
! YouTube ตอบ "Sign in to confirm you're not a bot" ได้ (เจอ 2026-10-05) = โหลดเพลงใหม่ไม่ได้เลย — ทดสอบอย่ายิงโหลดซ้ำรัว ๆ ใช้ไฟล์ที่มีในคลังจำลองแทน
- `server.py` `YT_COOKIES = os.environ` `def _yt_ck_load(` `def _yt_cookies(` `def _yt_ck_reset(` `def _yt_auth(` `_BOT_RE = ` — แก้บล็อกบอท: โหลด/ดึงซับด้วยล็อกอิน YouTube จาก Chrome (KARA_YT_COOKIES, "none" = แบบเดิม) อ่านในเธรดแยก เก็บเฉพาะคุกกี้ YouTube/Google ในหน่วยความจำ อ่านใหม่ทุก 10 นาที, ล็อกอินแล้วใช้ node + สคริปต์ ejs:github แก้โจทย์ JS, โดนบอทอีก = ล้างคุกกี้ + _BOT_HINT ขึ้นการ์ดผ่าน fixWhy (_fix_target), เปิดเซิร์ฟเวอร์แล้วอ่านทันที (Keychain ถามตอนนั้น)
! ทดสอบ/เซิร์ฟเวอร์ทดสอบต้องตั้ง KARA_YT_COOKIES=none — ไม่งั้นอ่านคุกกี้ Chrome จริง (Keychain เด้ง) · _search ไม่ใช้คุกกี้ (ค้นหาไม่โดนบล็อก)
- `server.py` `def _fetch_auto_caption(` `def _fetch_subs(` `_DL_COMMON = {` `def _dl_scrub(` `_DL_AUTO_MAX = 3` — auto-caption เป็น auto.th.vtt, ซับจริงตามภาษา, ตัวเลือก yt-dlp (โหลด 8 fragment พร้อมกัน), ล้างเศษไฟล์, ลองอัตโนมัติไม่เกิน 3 รอบแล้วรอคนกดซ่อม
- `server.py` `def _dl_fields(` — เติม dlStatus/localUrl/ชื่อจริงลงการ์ดตอน broadcast (อ่านจากดิสก์)

### แยกเสียงร้อง Demucs (stems / vocals)
คำค้น: แยกเสียง, แยกเสียงร้อง, stems, demucs, htdemucs, vocals.m4a, no_vocals.m4a, ไกด์ร้อง, ตัดเสียงร้อง, mps, cpu, แยกเสียงใหม่
- `server.py` `async def _enqueue_sep(` `async def _sep_worker(` `def _separate_one(` `DEMUCS_MODEL = "htdemucs"` — รัน demucs --two-stems vocals เป็น subprocess (ลอง mps ก่อนแล้ว cpu) ได้ vocals.m4a/no_vocals.m4a, เสร็จแล้วต่อไปหาเนื้อ/best/words
- `server.py` `SEP_MAX_SEC = ` `async def _sep_skip_long(` `_sep_gone: set` — คลิปยาวเกิน 10 นาทีไม่แยกเสียง/ไม่ถอดเสียง (sep = failed + _SEP_LONG_ERR, best/words ใช้ audio.m4a แทน, ไม่ขึ้นปุ่มซ่อม), เพลงที่ลบระหว่างแยกห้ามตกไป cpu
! จำ device เฉพาะ mps — เคยจำ cpu หลังเพลงถูกลบกลางทาง (demucs rc=-9) แล้วทุกเพลงแยกบน cpu จนรีสตาร์ท (เครื่องร้อน/ซับช้า) · cpu สำรองใช้ครึ่ง core + nice
- `server.py` `def _sep_fields(` `def _has_stems(` `def _purge_audio_caches(` — sepStatus บนการ์ด, เช็คว่ามีสเต็มครบ, ล้างแคช FA/เสียงร้องเก่าหลังแยกใหม่

### หาเนื้อเพลง gen_lyrics และโหลดเนื้อใหม่ (lyrics pipeline)
คำค้น: หาเนื้อ, เนื้อเพลง, lyrics, ซับ, gen_lyrics, lrclib, ถอดเสียง, whisper, ASR, ไม่มีเนื้อ, nolyr, โหลดเนื้อใหม่, relyr, lyrics.json, lyricsUrl, ป้ายความมั่นใจ, lyrConf, lyrStatus
- `server.py` `async def _enqueue_lyr(` `def _find_lyrics(` `async def _lyrfind_worker(` — เฟสที่ไม่ใช้ GPU (gen_lyrics --no-asr: ไฟล์ใน lyrics-in, ซับ YouTube, lrclib ตามลำดับ) ไม่ต้องรอ demucs
- `server.py` `def _build_lyrics(` `async def _lyr_worker(` `_NEED_ASR_RC = 3` `_NO_LYRICS_RC = 4` — เฟสถอดเสียง (gen_lyrics เต็ม ใช้ GPU และรอ vocals) พร้อม exit code ที่ต้องตรงกับ gen_lyrics
- `server.py` `async def _relyr(` `def _clear_lyrics(` — ปุ่มโหลดเนื้อใหม่: สำรองเนื้อเดิมลง lyrics.edits/ แล้วล้าง lyrics.json/check/offset/แคชถอดเสียง (ไม่แตะ lyrics-in/)
- `server.py` `def _lyr_fields(` `def _lyr_meta(` — เติม lyricsUrl/lyrStatus/ป้ายความมั่นใจลงการ์ด (LC.confidence คำนวณสดจากที่มาของเนื้อกับผลตรวจล่าสุด)
! เนื้อที่คนแก้เองใน lyrics-in/ ชนะทุกแหล่งเสมอ relyr/clear ห้ามลบ lyrics-in/ ส่วน exit code 3/4 และบรรทัดสรุปที่ขึ้นต้นด้วย ✓▲✗ ต้องตรงกับ scripts/gen_lyrics.py

### ภาษาของเพลง (song language)
คำค้น: ภาษา, language, lang.json, ตรวจภาษา, detect lang, เพลงอังกฤษ, เพลงญี่ปุ่น, เพลงเกาหลี, ภาษาผิด, เนื้อผิดภาษา, whisper ฟังภาษา
- `server.py` `def _song_lang(` `async def _ensure_lang(` `def _detect_lang_sync(` — อ่านภาษาจาก lang.json (เดาจากชื่อ/แทร็ก ASR ก่อน ถ้ายังไม่รู้ให้ whisper ฟังผ่าน gen_lyrics --detect-lang) ทำก่อนหาเนื้อ
- `server.py` `def _lang_migrate_needed(` `async def _lang_migrate(` — เพลงที่ไม่ใช่ภาษาไทยแต่ได้เนื้อมาตอนที่ระบบคิดว่าเป็นไทย จะหาเนื้อใหม่ครั้งเดียว (ปุ่มตั้งภาษาเองอยู่ใน Studio action "lang"/"detect-lang")

### ตรวจเวลาเนื้อ ป้าย ✅/⚠️ (verify / check v2)
คำค้น: ตรวจเวลา, ตรวจเนื้อ, verify, check, ความมั่นใจ, confidence, ✅, ⚠️, ป้าย, lyrics.check.json, เวลาตรงกี่เปอร์เซ็นต์, บรรทัดบกพร่อง, defects, lyrics_conf
- `server.py` `async def _enqueue_verify(` `async def _verify_worker(` `def _verify_one(` — ตรวจเวลาด้วย FA (วัดอย่างเดียว ไม่เปลี่ยนเนื้อ) อันดับต่ำสุด ถูกงานอื่นแย่ง GPU ได้เสมอ
- `server.py` `def _fa_measure2(` `def _write_check(` `CHECK_VERSION = 2` `def _chk_info(` `def _chk_verdict(` — check v2 ผ่าน lyrics_refine.check_timing เขียนผลลง lyrics.check.json (verdict ok/bad/unmeasurable ตามเกณฑ์ใน LC)
- `server.py` `import lyrics_conf as LC` — สูตรป้ายความมั่นใจ (import เข้าโปรเซสหลัก)
- `server.py` `def _lyr_sparse(` `def _va_for(` `def _cover_of(` `_lyr_cov: dict` — เนื้อแค่บางช่วง (ซับบทพูดในเอ็มวี): cover จากผลตรวจล่าสุด (ถ้าตรวจหลังเนื้อเปลี่ยน) ไม่งั้น Σd/คลิป, แผนที่เสียงร้องเฉพาะ vocals.m4a (โหลดใน thread), _write_check เก็บ cover
! เพิ่ม CHECK_VERSION แล้วเพลงเก่าทั้งคลังจะถูกตรวจใหม่ตอนบูต (lifespan backfill)

### เวลารายตัวอักษร โหมดคาราโอเกะไล่สี (words)
คำค้น: ไล่สี, คาราโอเกะ, karaoke, เวลารายคำ, เวลารายตัวอักษร, words, lyrics.words.json, wordsUrl, FA, forced alignment, ไล่สีไม่ตรง, คำอังกฤษ
- `server.py` `# ===== เวลารายตัวอักษร` `async def _enqueue_words(` `async def _words_worker(` `async def _run_words(` — คิวทำเวลารายตัวอักษร (รอ vocals ก่อน, ถ้ามีแคช FA แล้วเป็นงาน CPU ไม่จอง GPU)
- `server.py` `def _make_words(` `def _words_meta(` `def _words_status(` `def _words_stale_auto(` `WORDS_VERSION = 2` — รัน FA ทั้งเพลงโดยใช้เวลาบรรทัด + offset เป็นหมุด เขียนผลลง lyrics.words.json (ไม่แตะ lyrics.json), ใช้ได้เฉพาะเมื่อข้อความตรงกันทุกบรรทัด
! ถ้าข้อความเปลี่ยนระหว่างทำ ผลจะถูกทิ้ง ส่วนการแก้แค่เวลาใน Studio ไม่ทำ words ใหม่ (ตั้งใจ)

### เลือกเนื้อดีที่สุดจากทุกแหล่ง (best)
คำค้น: เลือกเนื้อดีที่สุด, best, เทียบเนื้อ, ทุกแหล่ง, JOOX, NetEase, YouTube Music, Musixmatch, lrclib, เปลี่ยนเนื้ออัตโนมัติ, lyrics.best.json, ซ่อมเวลาอัตโนมัติ, refine, manual-edit, เนื้อไม่ครบ, เนื้อแค่บางช่วง, บทพูด, เนื้อค้าง, sparse, cover, คลุมเสียงร้อง, gate
- `server.py` `# ===== เลือกเนื้อดีที่สุด` `async def _enqueue_best(` `async def _best_worker(` `async def _run_best(` — งานเบื้องหลังหลังได้เนื้อรอบแรก: รวมทุกแหล่ง + OCR, ให้ FA ให้คะแนน, ตัดสิน, ซ่อมเวลา, ตรวจ v2 แล้วสั่ง words ต่อ
- `server.py` `def _best_needed(` `def _best_decide(` `def _best_apply(` `def _best_record(` `async def _refine_dec(` `def _check_now(` — เช็คว่าต้องทำไหม, ตัดสิน keep|shift|retime|newtext|found|none, เขียน lyrics.json (สำรองลง 🕘 ก่อน), บันทึกผลลง lyrics.best.json
- `server.py` `BEST_MANUAL = frozenset(` `BEST_VERSION = 2` — แหล่งที่ห้ามแตะ (manual-edit/manual-lrc/manual-txt) และรุ่นของงาน
- `server.py` `def _best_pool(` `def _best_timed(` `BEST_MASS_FRAC = ` `BEST_SPARSE_V = ` — ให้คะแนน + ธง sparse (คลุมเสียงร้อง < 40 และ < ครึ่งของตัวที่คลุมสุด และตัวอักษร < 0.4 เท่า) + gate ตั้งจากตัวที่ข้อความมากพอ (บทพูด 9 บรรทัด match 81 เคยดัน gate จนเนื้อเต็มเพลงตกหมด) / เนื้อเดิม sparse ตัดสินแบบไม่มีเนื้อเดิม (กฎ weak ไม่ยุ่ง — คงไว้กันเพลงญี่ปุ่นถูกเปลี่ยนเป็นโรมาจิ) (ไม่มีแหล่งคน -> auto-caption ที่คลุม ≥ 60%) / เพลงเก่า sparse ทำใหม่ครั้งเดียว ("sv" ใน lyrics.best.json)
- `server.py` `def _prefetch_best(` `async def _best_sources(` `BEST_PRE_TTL = ` — เพลงใหม่: ดึงแหล่งออนไลน์ + OCR ไว้ก่อนระหว่างรอแยกเสียง (ไม่ใช้ GPU) แล้ว _run_best ใช้ชุดนั้นเมื่อ hash เนื้อ + ภาษายังเหมือนตอนดึง (ผู้สมัครชุดเดียวกัน = ผลตัดสินเดิม) ไม่งั้นดึงใหม่ · เพลงที่ต้องรอถอดเสียงไม่ดึงล่วงหน้า (OCR ซ้อน demucs/ถอดเสียงแล้วงานพวกนั้นช้าลง — ให้ไปซ้อนกับการคำนวณเสียง FA ในงานเลือกเนื้อแทน)
- `server.py` `async def _best_fa_warm(` `def _fa_warm_text(` — คำนวณแคชเสียงร้องของ FA ระหว่างรอผู้สมัคร: โมเดลอังกฤษเฉพาะเพลง lang=en หรือเนื้อปัจจุบัน/ผู้สมัครที่ดึงล่วงหน้า (_best_pre) มีคำอังกฤษ (ตัดสินก่อนสร้าง task เพราะ _best_sources หยิบ _best_pre ออกไป) แคชชุดเดียวกับที่ขั้นให้คะแนนใช้ (ข้อความต้องมีละติน ≥ 2 ตัว ไม่งั้น fa_align ไม่ทำรอบอังกฤษ)
! บรรทัด [best] ใน log แตกเวลาเป็นขั้น (รอคิว / แหล่ง / รอGPU / FA / ซ่อม / ตรวจ) + "เนื้อใหม่ขึ้นจอหลังกดเพิ่ม" — ดูตรงนี้ก่อนถ้าเนื้อเพลงใหม่ช้า
! "partial" ในงานนี้ = แหล่งออนไลน์ดึงไม่ครบ (ลองใหม่ได้) คนละเรื่องกับ sparse (เนื้อมีแค่บางช่วง) · เปลี่ยนกติกา sparse ต้องวัดด้วย scripts/eval_lyrics.py best + sparse
! งานอัตโนมัติห้ามเขียนทับเนื้อที่คนแก้หรือวางไฟล์เอง (BEST_MANUAL) เด็ดขาด แม้มีคนกดสั่ง (เช็คทั้งตอนเข้าคิวและตอนรัน) ถ้าเนื้อเปลี่ยนระหว่างทำ (hash ไม่ตรง) ต้องทิ้งผล และเพิ่ม BEST_VERSION แล้วจะทำซ้ำทั้งคลัง

## server.py — Studio (หน้าแอดมิน)

### เข้าสู่ระบบ PIN และสิทธิ์ Studio (.studio.json)
คำค้น: Studio, PIN, รหัส, ล็อกอิน, login, cookie, สิทธิ์, guard, .studio.json, รหัสจอทีวี, tv key, ใส่ PIN ผิด, ล็อก
- `server.py` `# ===== Studio: แก้เนื้อ` `def _studio_cfg(` `def _studio_token(` `PIN_TRIES, PIN_LOCK_S` — อ่าน .studio.json (pin/secret/tv/publicUrl/mxmToken, สร้าง PIN สุ่มตอนรันครั้งแรก, แคชด้วย mtime), cookie = sha256(secret:pin)
- `server.py` `@app.post("/api/studio/login")` `def _studio_guard(` `def _studio_vid(` — ล็อกอิน (ใส่ผิด 5 ครั้งล็อก 60 วิ, cookie อยู่ 30 วัน) ทุก API ของ Studio ผ่าน guard: เครื่องตัวเองเข้าได้เลย เครื่องอื่นต้องมี cookie และ POST ต้อง same-origin
! แก้ PIN/publicUrl/รหัส tv ใน .studio.json มีผลทันทีไม่ต้องรีสตาร์ท และเปลี่ยน PIN แล้ว cookie เก่าของทุกเครื่องใช้ไม่ได้

### รายการเพลงและรายละเอียดเพลงใน Studio
คำค้น: รายการเพลง Studio, ทุกเพลงในเครื่อง, สถานะเพลง, รายละเอียดเพลง, songs, song detail, ป้ายสถานะ, ไฟล์ที่มี
- `server.py` `@app.get("/api/studio/songs")` `def _studio_item(` `def _studio_ctx(` — สถานะทุกด้านของทุกเพลง (ใช้ตัวเติมฟิลด์ชุดเดียวกับคิว ป้ายจึงตรงกัน) ทำใน thread
- `server.py` `@app.get("/api/studio/song/{vid}")` `def _words_detail(` — รายละเอียดเพลงเดียว: lyrics, offset, check, เหตุผลที่ไม่มีเนื้อ, รายการรุ่น 🕘, ไฟล์ที่มี, ไฟล์ใน lyrics-in, สถานะ FA, รายงาน 🚩, words

### บันทึกเนื้อที่แก้ / ประวัติ 🕘 / เลื่อนเวลา / จับเวลาอัตโนมัติ
คำค้น: แก้เนื้อ, บันทึกเนื้อ, save lyrics, edit, manual-edit, lyrics-in, ประวัติแก้ไข, undo, ย้อนกลับ, 🕘, lyrics.edits, offset, เลื่อนเวลาซับ, ซับช้า, ซับเร็ว, autotime, จับเวลาอัตโนมัติ, เสียงที่ 2, คอรัส
- `server.py` `@app.put("/api/studio/song/{vid}/lyrics")` `def _write_edit(` `def _clean_edit_lines(` — บันทึกเนื้อที่แก้: เขียน lyrics.json และสำเนา lyrics-in/<vid>.json (src manual-edit), ลบ check/nolyr เก่า, สั่ง words ใหม่, broadcast ให้จอโหลดเนื้อใหม่
- `server.py` `def _backup_lyrics(` `EDITS_KEEP = 20` `@app.get("/api/studio/song/{vid}/edit/{ts}")` `def _write_json_atomic(` — สำรองแต่ละรุ่นลง lyrics.edits/<เวลา>.json (เก็บ 20 รุ่น ไม่เก็บซ้ำ) และอ่านรุ่นเก่ากลับมา
- `server.py` `@app.post("/api/studio/song/{vid}/offset")` `def _set_lyr_offset(` `def _lyr_offset(` `LYR_OFFSET_MAX = 15.0` — เลื่อนเวลาซับทั้งเพลง (lyrics.offset.json, ไม่เกิน ±15 วิ)
- `server.py` `@app.post("/api/studio/song/{vid}/autotime")` `def _autotime(` — จับเวลาข้อความที่แก้: ใช้ FA ถ้ามีโมเดล ไม่งั้นใช้ word timing จากแคช whisper/auto-caption (ไม่ใช้ GPU)
! งานเบื้องหลังห้ามเขียนทับเนื้อที่บันทึกจาก Studio (lyrics-in/*.json, src manual-edit) และ Studio ใช้ lyricsUrl ที่ส่งกลับไปเช็คว่ามีงานอื่นมาเขียนทับหรือไม่

### ตั้งค่าจอทีวีและโลโก้ (TV_SCHEMA / tv.json)
คำค้น: ตั้งค่าจอ, TV settings, ตั้งค่าทีวี, ขนาดซับ, สีซับ, สีไล่, เงาตัวอักษร, ยกซับ, QR, โลโก้, logo, ชื่อเพลงบนจอ, ชิป, chips, นับถอยหลัง, countdown, ข้อความหน้าจอว่าง, การ์ดเพลงถัดไป, tv.json
- `server.py` `TV_SCHEMA: dict` `TV_CHIPS = (` `def _clean_tv(` `def _load_tv(` `def _tv_public(` `TV_FILE = BASE / "tv.json"` — ทุกค่าตั้งของจอ (ชนิด, ค่าเริ่มต้น, ช่วง) ค่าผิดชนิดถูกทิ้ง ค่าเกินช่วงถูกบีบเข้าขอบ สีต้องเป็น #rrggbb
- `server.py` `@app.get("/api/studio/tv")` `@app.post("/api/studio/tv")` — อ่าน/ตั้งค่า (ส่งมาเฉพาะค่าที่เปลี่ยนก็ได้, reset = กลับค่าเริ่มต้น) แล้ว broadcast ให้จอเปลี่ยนสด
- `server.py` `@app.put("/api/studio/tv/logo")` `@app.delete("/api/studio/tv/logo")` `def _save_logo(` `@app.get("/tv/logo.png")` — อัป/ลบรูปมุมขวาบน (ครอปเป็นจัตุรัส PNG 512px เก็บที่ .tv/logo.png, ไม่เกิน 10MB)
! จะเพิ่มค่าตั้งใหม่ของจอ ต้องเพิ่มใน TV_SCHEMA ก่อน (คีย์ที่ไม่อยู่ใน schema ถูกทิ้งเงียบ ๆ) แล้วไปอ่านค่าใน static/player.html และ studio.html

### ✂️ จุดเริ่ม/จบรายเพลง (trim.json) + 🎬 คอมโบ (combos.json)
คำค้น: trim, trim.json, จุดเริ่ม, จุดจบ, ตัดต่อ, คอมโบ, combo, combos.json, clip, queue clip
- `server.py` `CLIP_KEYS = ` `def _clean_clip(` `def _trim(` `def _set_trim(` — {start, end, fadeIn, fadeOut} เป็นเวลาในเสียง ตรวจด้วย _finite (เฟด ≤ 10 วิ), ว่าง = ลบไฟล์
- `server.py` `@app.get("/api/studio/song/{vid}/clip")` `@app.post("/api/studio/song/{vid}/trim")` `@app.post("/api/studio/queue/{qid}/clip")` — ข้อมูลแทร็กของแท็บ ✂️ (trim + auto + ไฟล์สื่อ/เนื้อ), ตั้งค่าประจำเพลง, แก้ใบคิวคอมโบรอบนี้ (แทนที่ทั้ง 4 ค่า)
- `server.py` `COMBO_MAX_ITEMS = ` `def _combos()` `def _clean_combo(` `def _combo_public(` `@app.get("/api/combos")` `@app.get("/api/studio/combos")` `@app.post("/api/studio/combos")` `@app.delete("/api/studio/combos/{cid}")` — combos.json แคชตาม mtime, รีโมทเห็นชื่อ/เพลง/ความยาวรวมหลังตัด, Studio สร้าง/แก้ทั้งก้อน (คงลำดับ) แล้ว archive_rev += 1
! trim.json ไม่อยู่ในรายการลบของ _clear_lyrics / เลือกเนื้อใหม่ (เวลาในเสียง ใช้ต่อได้) · คอมโบไม่ใช้ trim.json/ค่าอัตโนมัติเลย

### FA จับเวลาละเอียด / แผนที่ความคลาด 🗺 / ซ่อมเวลา 🩺
คำค้น: FA, forced alignment, จับเวลาละเอียด, wav2vec2, fa_align, แผนที่ความคลาด, drift, 🗺, ซ่อมเวลา, refine, 🩺, lyrics_refine, เวลาเพี้ยน, KARA_REFINE, โหลดโมเดลค้าง, fa worker, --serve, KARA_FA_WORKER, KARA_FA_IDLE, เลือกเนื้อช้า, ไล่สีช้า, อุ่นเครื่อง, warm, เพลงแรกช้า, KARA_WARM
- `server.py` `# ===== Studio: แผนที่ความคลาด` `def _fa_call(` `async def _fa(` `def _fa_ready(` `def _fa_cached_for(` `def _audio_for(` — เรียก scripts/fa_align.py เป็น subprocess (ส่ง JSON ทาง stdin, อ่านผลจากบรรทัดสุดท้ายของ stdout), ครั้งแรกของแต่ละเพลงจองคิว GPU ครั้งต่อไปมีแคชเป็นงาน CPU, ใช้ vocals.m4a ก่อน audio.m4a
- `server.py` `async def _warmup(` `WARM = os.environ` `_warm_state: dict` — อุ่นเครื่องตอนเปิดโปรแกรม (8 วิหลังเปิด): import โมดูลหาเนื้อ + โหลดโมเดล FA ค้างไว้ (~17 วิ), log [warm], /api/health → warm, ปิดด้วย KARA_WARM=off (วัดแล้วไม่ทำ: รันโมเดลกับเสียงเงียบ / อุ่น whisper / demucs — ต่างไม่ถึง 1 วิ)
- `server.py` `class _FaWorker:` `_fa_worker = _FaWorker()` `FA_WORKER = ` `def preload_bg(` `def load_now(` — ตัวโหลดโมเดลค้าง (fa_align.py --serve): งานที่ต้องคำนวณเสียง (ยกเว้น verify) ส่งไปตัวนี้ ไม่ต้อง import+โหลดโมเดลใหม่ทุกเพลง (วัดแล้ว ไทย 16→5 วิ, ไทย+อังกฤษ 25→9.6 วิ, ทั้งสาย 45→30 วิ ผลเท่ากันทุกตัว), โหลดล่วงหน้าตอน demucs เริ่ม, ตาย/เปิดไม่ขึ้น = ถอยไปทางเดิม, /api/health → faWorker
! verify ต้องใช้ทางเดิม (subprocess ต่อครั้ง) เพื่อให้ _preempt_heavy ฆ่าแย่งคิวได้ · งานที่มีแคชแล้วก็ใช้ทางเดิม (CPU ล้วน ไม่ต้องต่อคิวหลังงาน GPU) · KARA_FA_WORKER=off = กลับแบบเดิมทั้งหมด, KARA_FA_IDLE ค่าเริ่มต้น 0 = ค้างไว้ตลอด (ผู้ใช้เลือก — ตั้งวินาทีได้ถ้าอยากคืน RAM ~2.6 GB เมื่อว่าง)
- `server.py` `@app.post("/api/studio/song/{vid}/drift")` `def _measure_whisper(` `FA_MIN_CONF = 0.12` — เวลาที่วัดได้ของทุกบรรทัด (ใช้ FA หรือ whisper สำรอง) ให้ Studio วาดแผนที่ความคลาดเอง
- `server.py` `@app.post("/api/studio/song/{vid}/refine")` `def _refine_call(` — 🩺 ซ่อมช่วงที่เวลาเพี้ยนผ่าน scripts/lyrics_refine.py คืนเป็นข้อเสนอเท่านั้น ไม่บันทึก
! 🩺 refine เป็นทางเดียวที่เนื้อ manual-edit ได้ใช้ตัวซ่อม (งานอัตโนมัติไม่แตะ) และ _refine_call ใช้เฉพาะแคช FA ที่มีอยู่แล้ว ไม่แย่ง GPU นอกคิว

### ห้องหาเนื้อ 🔎 และ Musixmatch token (sources)
คำค้น: ห้องหาเนื้อ, 🔎, หาเนื้อจากแหล่งอื่น, sources, ผู้สมัคร, candidates, lrclib, JOOX, NetEase, YouTube Music, Musixmatch, token, OCR, ตัวหนังสือในคลิป, Lyric Video, เพลงซ้ำในคลัง, settings
- `server.py` `@app.post("/api/studio/song/{vid}/sources")` `def _gather_sources(` `def _score_fa(` `def _score_whisper(` `SRC_TTL = 1800.0` — รวมผู้สมัครทุกแหล่ง (เนื้อปัจจุบัน, เพลงซ้ำในคลัง, ซับ/auto-caption, lrclib/JOOX/NetEase/YT Music/Musixmatch, OCR) ให้คะแนนด้วย FA (ถ้าพังใช้ whisper) + cover (คลุมเสียงร้อง, va โหลดใน thread), pick = ตัวที่งานเลือกเนื้อจะใช้ (ขึ้นก่อน), แคช 30 นาที (ส่ง fresh เพื่อข้ามแคช) · คำค้นท่อนเนื้อไม่ใช้เนื้อที่มีแค่บางช่วง (บทพูด)
- `server.py` `def _ocr_ensure(` `def _library_twins(` `ONLINE_PROVIDERS = (` — อ่านตัวหนังสือในคลิปด้วย OCR (scripts/ocr_lyrics.py, Apple Vision) และหาคลิปซ้ำของเพลงเดียวกันในคลัง
- `server.py` `@app.get("/api/studio/settings")` `@app.post("/api/studio/settings")` `def _mxm_token(` — ตั้ง/ลบ Musixmatch token (ทดสอบก่อนเก็บลง .studio.json แล้วล้างแคชห้องหาเนื้อ)

### ปุ่มซ่อม / ลองใหม่ / ลบเพลง (Studio action / fix / delete)
คำค้น: ปุ่มซ่อม, ซ่อม, fix, ลองใหม่, retry, โหลดใหม่, redl, แยกเสียงใหม่, resep, หาเนื้อใหม่, relyr, เลิกใช้เนื้อที่แก้เอง, drop-edit, ตั้งภาษา, ทำทั้งคลัง, best-all, words-all, ลบเพลง, delete, 🗑
- `server.py` `@app.post("/api/studio/song/{vid}/action")` `if do == "fix":` `elif do == "drop-edit":` — ปุ่มซ่อมใน Studio ใช้ได้กับทุกเพลงในเครื่อง: fix/redl/resep/relyr/verify/drop-edit/asrtext/words/best/best-all/lang/detect-lang/words-all (ล็อกแยกต่อเพลง ไม่ถือ room.lock)
- `server.py` `def _fix_target(` `async def _do_fix(` `def _fix_fields(` `elif act == "fix":` — หาขั้นที่พังค้างจริง (dl/audio/sep/lyr/verify) ใช้ร่วมกันทั้งป้ายบนการ์ดและปุ่ม "ลองใหม่" บนรีโมท
- `server.py` `@app.delete("/api/studio/song/{vid}")` `def _purge_song_files(` — 🗑 ลบโฟลเดอร์เพลงและแคชทุกที่ (ฆ่าโปรเซสลูกก่อน, ห้ามลบเพลงที่กำลังเล่น, ?edits=1 ลบไฟล์ใน lyrics-in ด้วย, ไม่แตะประวัติ)
! คำสั่งพวกนี้ห้ามถือ room.lock ระหว่างทำ เพราะต้องรอ yt-dlp หรือคิว GPU นาน จะทำให้ทั้งห้องค้าง

## สคริปต์ระบบเนื้อเพลง (scripts/)

### สร้างเนื้อเพลงอัตโนมัติ — ลำดับแหล่งเนื้อ (gen_lyrics)
คำค้น: สร้างเนื้อ, หาเนื้อ, โหลดเนื้อใหม่, สร้างใหม่ทั้งคลัง, ลำดับแหล่ง, แหล่งเนื้อ, ไม่มีเนื้อ, เนื้อหาย, gen_lyrics, generate lyrics, lyrics pipeline, source priority, exit code, NO_LYRICS, need-asr, skip-done, no-asr, nolyr
- `scripts/gen_lyrics.py` `def process(` `def main() -> None:` — process ไล่แหล่ง 0) lyrics-in/<vid>.json 1) .lrc 2) sub.<lang>.vtt 3) lrclib 4) auto-caption 5) whisper (+ เนื้อจาก description / lrclib-plain); main = CLI [vid…] --skip-done --no-asr --detect-lang
- `scripts/gen_lyrics.py` `def keep_sparse(` `sparse_fb: tuple` — ขั้น 2-3: ซับ/lrclib ที่มีแค่บางช่วง (คลุมคำที่ auto-caption ได้ยิน < 40% / ไม่มี auto-caption: Σd < 25% ของคลิป) พิมพ์ [sparse] แล้วข้ามไปแหล่งอื่น ใช้เป็นทางสุดท้ายที่ทางออก "ไม่มีเนื้อ" ของขั้น 5
- `scripts/lyrics_sources.py` `def sparse_why(` `def span_pct(` `def words_cover(` `SPARSE_SPAN = ` — ตัววัดเนื้อแค่บางช่วงก่อนมี vocals (ใช้ทั้ง gen_lyrics และ server)
- `scripts/gen_lyrics.py` `def write_out(` `def _no_lyrics(` — ตัวเขียน lyrics.json ของ gen_lyrics/verify_lyrics (atomic, สำรอง lyrics.prev.json เมื่อ src เปลี่ยน, ลบ lyrics.offset.json, พรีวิว _srt) / หมุด "ไม่มีเนื้อ" lyrics.nolyr.json
- `scripts/gen_lyrics.py` `def from_edit(` `def from_manual(` `def read_lines(` — lyrics-in/<vid>.json (manual-edit ชนะทุกแหล่ง), .lrc (manual-lrc), .txt (manual-txt) แล้วค่อยเนื้อจาก description
- `scripts/gen_lyrics.py` `NEED_ASR = 3` `NO_LYRICS = 4` `TRUSTED_TIME = frozenset` — exit 3 = แหล่งที่ไม่ใช้ GPU หมดแล้วต้องถอดเสียงต่อ / 4 = ลองครบแล้วไม่มีเนื้อ; ชุด src ที่เวลามาจากแหล่งตรง ๆ
- `lyrics-in/README.md` `# ที่วางไฟล์เนื้อเพลง` `## คำสั่งที่ใช้บ่อย` — ตารางลำดับแหล่งสำหรับผู้ใช้ + คำสั่งรันมือ
! videoId ขึ้นต้นด้วย "-" ได้ (เช่น -IkfnFeojFY) — ห้ามคัด argv ด้วย startswith("-") ไม่งั้นสั่งเพลงเดียวกลายเป็นทำทับทั้งคลัง
! server.py ผูกกับไฟล์นี้: exit code 3/4, TRUSTED_TIME, VOICES ต้องตรงกัน; server รันไฟล์นี้เป็น subprocess (แก้แล้วมีผลทันที ต้องคง CLI/ผลลัพธ์เดิม) และ import align/make_chunks/time_with/read_lines ฯลฯ เข้าโปรเซสด้วย (ห้ามเปลี่ยน signature, ส่วนนี้ผู้ใช้ต้องรีสตาร์ท)

### ภาษาของเพลง (lang.json) / ตรวจภาษา
คำค้น: ภาษาเพลง, ภาษา, เพลงอังกฤษ, เพลงญี่ปุ่น, เกาหลี, จีน, ตรวจภาษา, เดาภาษาผิด, lang, lang.json, language, detect language, detect-lang, ซับคำแปล, FA_LANGS
- `scripts/lyrics_sources.py` `def song_lang(` `def read_lang(` `def write_lang(` — ตัดสินภาษา: lang.json → อักษรในชื่อคลิป → lrclib → whisper → แทร็ก ASR ของ YouTube → th; lang.json = {lang, by, at}
- `scripts/lyrics_sources.py` `FA_LANGS = ` `def script_of(` `def asr_track(` `def lang_from_lrclib(` `def in_script(` — ภาษาที่มีโมเดล FA (th, en), ตารางอักษรต่อภาษา, แทร็ก ASR ของ YouTube, บรรทัดนี้เป็นภาษาเพลงไหม
- `scripts/gen_lyrics.py` `def detect_lang(` `args[:1] == ["--detect-lang"]` — whisper ฟัง 30 วิกลางเพลง; server เรียก gen_lyrics.py --detect-lang <ไฟล์เสียง> เป็น subprocess (บรรทัดสุดท้ายของ stdout = JSON {lang, prob})
- `lyrics-in/README.md` `**ภาษาของเพลง** ถูกตัดสินก่อนทุกขั้น` — คำอธิบายสำหรับผู้ใช้ (เลือกภาษาเองได้ใน Studio 🌐)
! write_out เขียน "lang": "th" ตายตัวใน lyrics.json — ภาษาจริงต้องอ่านจาก lang.json (server ใช้ song_lang/read_lang/write_lang ในโปรเซส)
! ja/ko/zh ไม่มีโมเดล FA: ได้เนื้อจากซับ/lrclib/คำบรรยาย แต่ไม่ไล่สีคาราโอเกะและไม่เทียบ/ตรวจอัตโนมัติ

### ซับ YouTube + คำบรรยายอัตโนมัติ (VTT)
คำค้น: ซับ, ซับยูทูบ, ซับ YouTube, คำบรรยายอัตโนมัติ, auto-caption, subtitle, vtt, sub.th.vtt, auto.th.vtt, yt-sub, yt-auto, ดึงซับ, ซับคำแปล, roll-up, fetch subs
- `scripts/fetch_subs.py` `def fetch(` `def fetch_auto(` `def main() -> None:` — เติมซับย้อนหลังให้เพลงเก่า: sub.<lang>.vtt (คนทำ) / auto.<lang>.vtt (ASR ของ YouTube); CLI [vid…] --auto --force (เพลงใหม่ server ดึงเองตอนโหลด)
- `scripts/lyrics_sources.py` `def from_vtt(` `def _cues_of(` `VTT_NONLATIN = ` — sub.<lang>.vtt → [{t,d,x}] กันซับที่เป็นคำแปล, ตัดบรรทัดซ้ำของซับแบบ roll-up
- `scripts/lyrics_sources.py` `def words_from_auto_vtt(` `def asr_caption_track(` `AUTO_MIN_WORDS = ` — auto-caption → [{start,end,word}] ใช้เป็นเส้นเวลาให้เนื้อจริง
- `scripts/gen_lyrics.py` `def lines_from_words(` — ไม่มีเนื้อจากแหล่งไหนเลย: ตัดคำ auto-caption เป็นบรรทัดบนจอ (src yt-auto)
- `scripts/ab_vtt.py` `def _ratio(` — ไม้บรรทัดเกณฑ์ from_vtt: sub.th.vtt ต้องผ่านทุกไฟล์ / sub.en.vtt (คำแปล) ต้องตก — รันทุกครั้งที่แก้เกณฑ์
! ห้ามเปลี่ยนชื่อ auto.<lang>.vtt เป็น sub.<lang>.vtt — gen_lyrics เชื่อว่า sub.* คือซับที่คนทำ (ชนะ lrclib); โค้ดโหลดซับตอนเพิ่มเพลงอยู่ใน server.py (_fetch_subs)
! fetch_subs.py / ab_vtt.py ชี้ songs/yt ตายตัว (ไม่รับ KARA_SONGS_DIR)

### lrclib + เนื้อจากคำอธิบายคลิป (description)
คำค้น: lrclib, LRC, synced lyrics, เนื้อมีเวลา, คำอธิบายคลิป, description, เนื้อใต้คลิป, web/description, lrclib-plain, ชื่อเพลง, ศิลปิน, เครดิต, ผิดเพลง, คัฟเวอร์, ความยาวเพลง, similarity
- `scripts/lyrics_sources.py` `def from_lrclib(` `def from_lrclib_text(` `def _lrclib_pool(` — ค้น lrclib.net แบบมีเวลา (กรองความยาวเพลง + ความเหมือนกับคำที่ถอดได้) / แบบเนื้อเปล่ายืนยันด้วยคำที่ถอดได้ (คลิปคัฟเวอร์/รีมิกซ์)
- `scripts/lyrics_sources.py` `def title_candidates(` `def credit_candidates(` `def similarity(` `def from_lrc(` — เดา (ชื่อเพลง, ศิลปิน) จากชื่อคลิป + เครดิตใน description, วัดความเหมือน, แปลง LRC → [{t,d,x}]
- `scripts/lyrics_sources.py` `DUR_TOL = 3.0` `ASR_SIM = 0.35` `MIN_LINES = 6` `MIN_DUR, MAX_DUR = 1.0, 14.0` — เกณฑ์รับเนื้อ + ความยาวบรรทัดที่จอรับได้
- `scripts/extract_src.py` `def extract(` `HEADER_FOOTER = (` `def looks_lyric(` — กรองเนื้อออกจาก description ใน info.json (ตัดเครดิต/ลิงก์/ช่องทางติดต่อ) → lyrics-preview/_src/<vid>.txt
- `scripts/gen_lyrics.py` `def _extract_src(` — สกัด description ให้เพลงที่โหลดผ่าน server (ไม่เคยผ่าน extract_src.py) แล้วแคช _src
! server.py import lyrics_sources ตั้งแต่เปิด และเรียกฟังก์ชันภายในตรง ๆ (_lrclib_pool, _plain_of, _finish, line_dur, from_vtt …) — ห้ามเปลี่ยนชื่อ/พารามิเตอร์, แก้แล้วผู้ใช้ต้องรีสตาร์ท
! ฟังก์ชันแหล่งเนื้อพังต้องคืน None เงียบ ๆ ห้าม raise (ทั้ง pipeline จะล้ม)

### แหล่งเนื้อออนไลน์ของงานหาเนื้อ: JOOX / NetEase / YouTube Music / Musixmatch
คำค้น: หาเนื้อ, ห้องหาเนื้อ, 🔎, แหล่งเนื้อเพิ่ม, เลือกเนื้อดีที่สุด, JOOX, NetEase, YouTube Music, ytmusic, Musixmatch, token, richsync, syncedlyrics, ผู้สมัคร, candidates, เปลี่ยนแหล่งเนื้อ, เครดิตในเนื้อ
- `scripts/lyrics_more.py` `def from_joox(` `def from_ytmusic(` `def from_syncedlyrics(` — JOOX (เนื้อไทยครบ แต่เวลาเป็นเวอร์ชันอัลบั้ม), YouTube Music (ถามจาก videoId + ค้นด้วยท่อนเนื้อได้), NetEase ผ่าน syncedlyrics
- `scripts/lyrics_more.py` `def from_musixmatch(` `def mxm_check(` `class MxmError` `def _richsync_lines(` — Musixmatch ต้องมี token (mxmToken ใน .studio.json), ทดสอบ token ก่อนเก็บ, เวลารายคำ richsync
- `scripts/lyrics_more.py` `def queries(` `def lyric_queries(` `def clean_lrc(` `def _cand(` — คำค้นจากชื่อคลิป/ท่อนเนื้อ, ตัดบรรทัดเครดิต, รูปผู้สมัคร {provider, label, synced, lines, texts, meta}
- `lyrics-in/README.md` `## ระบบเลือกเนื้อดีที่สุดจากทุกแหล่ง` `## แหล่งเนื้อใหม่` — ภาพรวมงานเลือกเนื้อดีที่สุด + แหล่ง Musixmatch / library / OCR
! API ไม่ทางการ พังได้ทุกเมื่อ: ห้าม raise ให้คืน [] (ยกเว้น MxmError ให้ Studio บอกว่า token เสีย); server import เข้าโปรเซส → แก้แล้วผู้ใช้ต้องรีสตาร์ท
! ผู้ใช้คือ server (_gather_sources ของ 🔎 หาเนื้อ + งานเลือกเนื้อดีที่สุด) ไม่ใช่ gen_lyrics; การรวม/ให้คะแนนผู้สมัคร และแหล่ง library (เพลงเดียวกันอีกคลิป) อยู่ใน server.py

### อ่านเนื้อจากตัวหนังสือในคลิป (OCR)
คำค้น: OCR, ตัวหนังสือในคลิป, เนื้อในภาพ, lyric video, Apple Vision, swift, swiftc, kara_ocr, อ่านภาพ, เวลาจากตัวหนังสือในคลิป, Xcode
- `scripts/ocr_lyrics.py` `def run(` `def cues_from(` `def probe(` `def main() -> None:` — ffmpeg 2 ภาพ/วิ → OCR → ช่วงข้อความ [{t0,t1,x}]; CLI <vid> [--video PATH] [--probe] [--force]
- `scripts/ocr_lyrics.py` `def retime(` `def cached(` — ใช้ข้อความ OCR เป็น "พยานเวลา" ให้เนื้อจากแหล่งอื่น (จับคู่บางส่วน) / อ่านแคช _ocr/<vid>.json ที่ผูกลายเซ็นวิดีโอ
- `scripts/ocr_lyrics.py` `def ensure_bin(` `BIN = BASE / ".cache" / "bin" / "kara_ocr"` — คอมไพล์ kara_ocr.swift ด้วย swiftc ครั้งแรก/เมื่อซอร์สใหม่กว่าไบนารี
- `scripts/kara_ocr.swift` `func recognize(` `req.recognitionLanguages` — Apple Vision (th-TH, en-US): stdout บรรทัดละ JSON {f, t: [[ข้อความ, conf, x, y, w, h]]}
! ต้องมี Xcode Command Line Tools (swiftc); ตัวสะกดจาก OCR เพี้ยนได้ — ไม่ถูกเลือกเป็นตัวเนื้อ ใช้แค่เวลา; server เรียก cached/retime ในโปรเซส และรัน ocr_lyrics.py เป็น subprocess

### ถอดเสียง whisper + จับคู่เนื้อกับเส้นเวลา (ASR alignment)
คำค้น: ถอดเสียง, whisper, mlx-whisper, ASR, transcribe, turbo, large-v3, KARA_ASR_MODEL, จับเวลาจากเสียง, anchorPct, align, เส้นเวลา, word timing, แคชถอดเสียง, _seg, whisper วนลูป, A/B โมเดล
- `scripts/gen_lyrics.py` `MODEL = os.environ.get("KARA_ASR_MODEL"` `ACCURATE_MODEL = ` `def model_tag(` — โมเดล whisper (ค่าเริ่ม large-v3-turbo; KARA_ASR_MODEL / KARA_ASR_MODEL_TEXT) + tag ในชื่อแคช
- `scripts/gen_lyrics.py` `def transcribe(` `def get_segments(` `def segment_cache_path(` `def _degenerate(` — ถอดเสียง + ทางหนีเมื่อ whisper วนลูป, แคช lyrics-preview/_seg/<vid>.<tag>.json
- `scripts/gen_lyrics.py` `def make_chunks(` `def align(` `def timings_for_lines(` `def time_with(` `def align_ok(` — จับคู่ตัวอักษรเนื้อจริงกับคำที่ถอด/auto-caption → เวลาเริ่มบรรทัด + anchorPct, เกณฑ์ยอมรับผล
- `scripts/ab_asr.py` `def panel(` `def cmd_run(` `def cmd_score(` — A/B โมเดลถอดเสียง (--list / --run --n N / --score) วัดกับเพลงที่เวลาไม่ได้มาจาก whisper; เขียนแค่ _seg กับ _ab.jsonl
! เลิกใช้ข้อความที่ whisper ถอดเป็นตัวเนื้อแล้ว (ใช้แค่เป็นเส้นเวลา/คำค้น lrclib) — ไม่มีเนื้อทุกแหล่ง = lyrics.nolyr.json
! server import make_chunks/align/time_with/timings_for_lines/norm_chars/segment_cache_path ในโปรเซส — ห้ามเปลี่ยน signature; ถอดเสียงกิน GPU (Apple Silicon)

### จับเวลาด้วย FA (forced alignment) + เวลารายตัวอักษรคาราโอเกะ
คำค้น: FA, forced alignment, wav2vec2, จับเวลา, AI จับเวลา, ไล่สี, คาราโอเกะ, karaoke, เวลารายคำ, word timing, lyrics.words.json, หมุด, anchors, คำอังกฤษ, วงเล็บ, คอรัส, ร้องซ้อน, voices, แคช FA, KARA_FA_MODEL
- `scripts/fa_align.py` `def time_lines(` `def main() -> None:` `def handle(` — จับเวลาต่อบรรทัด (t, d, conf; words=true ได้ k); CLI <vid> --audio PATH + stdin {"texts"} / {"sets"} (ให้คะแนนหลายผู้สมัคร) / --emit (คำนวณแคชอย่างเดียว)
- `scripts/fa_align.py` `def serve() -> None:` `def _load_model(` — --serve: บรรทัด JSON ทาง stdin/stdout ({"id","vid","audio","req"} / {"op":"load"}), โมเดลอยู่ใน _MODELS ตลอด, stdout จริงเหลือแต่คำตอบ (print อื่นไป stderr), ว่างเกิน KARA_FA_IDLE หรือ stdin ปิด = ออก
- `scripts/fa_align.py` `def emissions(` `def _cache_file(` `def _cache_ok(` `if os.environ.get("KARA_FA_NO_COMPUTE")` — log-prob จาก wav2vec2 แคช _fa/<vid>.<โมเดล>[.side].npz ผูกลายเซ็นไฟล์เสียง; NO_COMPUTE + ไม่มีแคช = raise
- `scripts/fa_align.py` `def align(` `STAR_PEN = ` `ANCHOR_TOL = ` `def paren_spans(` — CTC Viterbi + สถานะ "ข้ามได้" กลืนแอดลิบ, โทษเมื่อหลุดหมุดเวลา, ข้ามวงเล็บทั้งก้อน (opt paren)
- `scripts/fa_align.py` `MODEL = os.environ.get("KARA_FA_MODEL"` `MODEL_EN = ` `def tokenize_joint(` `def _k_from(` — โมเดลไทย + โมเดลอังกฤษ (คำละตินได้ k ด้วย); k = [[ตำแหน่งตัวอักษร, วินาที]] สำหรับไล่สี
- `scripts/fa_align.py` `def _time_by_voice(` `def model_ready(` — opt voices จับแยกเส้นทางต่อเสียง (มีในโค้ดแต่ไม่ได้เปิด) / เช็กโมเดลอยู่ใน .cache/hf (ไม่โหลดจากเน็ตกลางงาน)
- `lyrics-in/README.md` `## โหมดคาราโอเกะ` `## ท่อนเร็ว / ร้องซ้อน` — พฤติกรรมไล่สี/ร้องซ้อน + ตัวเลือกที่ทดลองแล้วไม่เปิด (paren/voices)
! opt ไม่ส่ง = พฤติกรรมเดิมทุกอย่าง (ต้องคงไว้); server ส่ง --audio เสมอ และอ่าน CACHE/MODEL/cached ในโปรเซส — เปลี่ยนชื่อไฟล์แคชต้องแก้ _purge_audio_caches ใน server.py ด้วย
! docstring ต้นไฟล์เขียน _fa/<vid>.npz แต่ชื่อจริงมีชื่อโมเดลต่อท้าย (คนละโมเดล = คนละไฟล์)

### ซ่อมเวลาอัตโนมัติ (refine) + แผนที่เสียงร้อง (ช่วงเงียบ/onset)
คำค้น: ซ่อมเวลา, refine, เลื่อนเป็นท่อน, เลื่อนทั้งท่อน, เวลาอัด, เกลี่ยเส้นตรง, บรรทัดบกพร่อง, defects, ช่วงเงียบ, onset, จุดเริ่มพยางค์, vocal activity, 🩺, ซ่อมช่วงเพี้ยน, KARA_REFINE, ท่อนแร็ป
- `scripts/lyrics_refine.py` `def refine_song(` `def main() -> None:` — ซ่อมเวลา (ไม่แตะข้อความ): stdin {"lines","timeSrc","duration","audio"} → stdout {"lines","record","note","changed"}
- `scripts/lyrics_refine.py` `def defects(` `def _segments(` `def _spread(` `def repeated(` — หาบรรทัดเวลาอัด/เกลี่ยเส้นตรง, เลื่อนทั้งท่อนเมื่อ FA มั่นใจ ≥ 4 บรรทัดเห็นตรงกัน, เกลี่ยตามพยางค์ + ดูดเข้า onset, ท่อนซ้ำ
- `scripts/lyrics_refine.py` `FAST_SPS = ` `SEG_MAX_SHIFT = ` `SEG_GAIN = ` `BREAK_SIL = ` — เกณฑ์ (พยางค์/วิที่ร้องไม่ทัน, เลื่อนท่อนได้ ≤ 3 วิ, ต้องดีขึ้น ≥ 20 จุด, ช่วงเงียบที่ตัดท่อนได้)
- `scripts/vocal_activity.py` `def analyze(` `def load(` `def gaps(` `def onset_rate(` `def voiced_at(` — แผนที่เสียงร้องจาก vocals.m4a (dB/voiced/onset ทุก 20 ms) แคช _va/<vid>.npz; CLI <vid> [--audio]
- `scripts/vocal_activity.py` `def cover(` `def envelope(` `MIN_VOICED = ` — % เสียงร้องที่บรรทัดคลุม (เนื้อแค่บางช่วง) / คลื่นเสียงร้อง 10 จุด/วิ ให้แท็บ ✂️
- `lyrics-in/README.md` `## ระบบซ่อมเวลาอัตโนมัติ` — กฎ + ผลวัด + ปิดด้วย KARA_REFINE=dry|off (env ของ server)
! กฎเหล็ก: ห้ามขยับบรรทัดเดี่ยว ๆ ตาม FA (เคยทำแล้วความตรงตก 97%→92%); timeSrc "fa" = ไม่เลื่อนเป็นท่อน (วัดตัวเอง); JSON stdin/stdout ต้องเข้ากันได้ย้อนหลัง (server เรียกเป็น subprocess)
! งานอัตโนมัติไม่แตะเพลง manual-edit (🩺 ใน Studio เป็นข้อเสนอ ยังไม่บันทึก); ผลซ่อมบันทึกไว้ใน lyrics.best.json → refine

### ป้ายความมั่นใจ ✅/⚠️ + ตรวจเวลาเนื้อ v2
คำค้น: ป้ายความมั่นใจ, ป้าย, ความมั่นใจ, ✅, ⚠️, ตรวจเวลา, ตรวจเวลาเนื้อ, 🔍, confidence, badge, onTime, score, check v2, เกณฑ์, ที่มาเนื้อ, ป้ายที่มา, src label, timeSrc, 🕳, เนื้อไม่ครบ, sparse
- `scripts/lyrics_conf.py` `def confidence(` `LEVELS = ` `SPARSE_COVER = ` — ระดับ good/check/bad/auto/sparse/unknown/none + เหตุผลสั้น (ไม่เคยวัด ≠ ดี, วัดตัวเองไม่นับ, เนื้อเครื่องถอด = auto, เนื้อแค่บางช่วง = sparse ทับ good ยกเว้นเนื้อที่คนใส่เอง) — รีโมท/Studio ขึ้น 🕳 เนื้อไม่ครบ
- `scripts/lyrics_conf.py` `HAND = frozenset` `SRC_LABEL = {` `def kind(` `def time_src_of(` — src ที่คนพิมพ์, ป้ายที่มาเนื้อภาษาไทย (รีโมท/จอใช้ชุดเดียวกัน), เดา timeSrc ให้ไฟล์รุ่นเก่า
- `scripts/lyrics_conf.py` `OK_SCORE, BAD_SCORE = 60, 30` `OK_SCORE_V2 = 70` `DEFECT_MIN = 2` — เกณฑ์ v1 / v2 (✅ = ตรง ≥ 70% และบรรทัดบกพร่อง < 2)
- `scripts/lyrics_refine.py` `def check_timing(` `CHECK_SLIDE = ` — ตรวจเวลา v2: FA ไม่มีหมุดหาเลื่อนรวม แล้ววัดต่อบรรทัด (ไหลเกิน 3 วิใช้ค่ามีหมุด), ไม่นับท่อนซ้ำ/บรรทัดวงเล็บล้วน, นับบรรทัดบกพร่อง
- `lyrics-in/README.md` `## ป้ายความมั่นใจ` — ตารางผลวัด v1 vs v2
! src ใหม่ต้องเพิ่มทั้ง HAND และ SRC_LABEL (ไม่งั้นป้ายเป็น auto / "ถอดเสียงร้องด้วย AI"); server import lyrics_conf ตั้งแต่เปิด และผูก CHECK_VERSION = 2 — แก้แล้วผู้ใช้ต้องรีสตาร์ท
! เกณฑ์คาลิเบรตด้วย scripts/eval_lyrics.py check — เปลี่ยนตัวเลขต้องวัดใหม่ก่อน

### ตรวจและซ่อมเนื้อด้วย whisper / auto-caption (verify_lyrics)
คำค้น: ตรวจเนื้อ, verify, ซ่อมเนื้อ, เนื้อผิดเพลง, เวลาเพี้ยน, เลื่อนทั้งเพลง, anchorPct, onTime, ไม้บรรทัด, ruler, dry-run, sweep, lyrics.check.json, แจ้งเนื้อไม่ตรง
- `scripts/verify_lyrics.py` `def verify(` `def main() -> None:` — วัดเนื้อที่ขึ้นจอจริง (รวม lyrics.offset.json) แล้วซ่อมถ้าผู้ท้าชิงดีกว่าชัด; CLI <vid> / --dry-run / --sweep / --gpu
- `scripts/verify_lyrics.py` `def measure(` `def ruler(` `def collect_candidates(` `def rank(` — anchorPct (เนื้อถูกเพลงไหม) / onTime (เวลาตรงไหม), ไม้บรรทัดอิสระ (auto-caption ก่อน whisper), ผู้ท้าชิง + หักคะแนนตัวที่จับเวลาจาก ASR
- `scripts/verify_lyrics.py` `def check_path(` `def save_check(` `OK_SCORE = 55` `RETIME_PENALTY = ` — เขียน lyrics.check.json (คง reports เดิม), เกณฑ์ผ่าน
- `lyrics-in/README.md` `## เจอเนื้อไม่ตรงตอนร้อง` — ปุ่ม 📝 แจ้งเนื้อไม่ตรง + 🔍 ตรวจเวลาเนื้อ + คำสั่งรันมือ
! ไม่เปลี่ยนเนื้อ manual-edit และเนื้อที่ระบบเลือกแล้ว (มี best) — วัดให้ดูอย่างเดียว; ห้ามใช้ไม้บรรทัดจากแหล่งเดียวกับเวลา (คะแนนสูงเทียม)
! ปุ่ม 🔍 ใน Studio วัดด้วย FA (lyrics_refine.check_timing ผ่าน server) ไม่ใช่สคริปต์นี้; server ใช้ measure/shifted ในโปรเซส

## ข้อมูล / ตั้งค่า

### รูปแบบไฟล์เนื้อ lyrics.json + lyrics-in/<vid>.json (เนื้อที่แก้เองใน Studio)
คำค้น: lyrics.json, รูปแบบไฟล์, format, schema, ฟิลด์, field, t d x v, เสียงร้อง, voice, src, timeSrc, manual-edit, lyrics-in, แก้เอง, Studio บันทึก, lrc, txt, WANTED.tsv, CHECK.tsv, เพลงไหนยังไม่มีเนื้อ
- `scripts/gen_lyrics.py` `out_json = {` `VOICES = (2, 3, "bg")` — lyrics.json = {v:1, videoId, lang, engine, src, timeSrc?, duration, anchorPct?, lines:[{t, d, x, v?}]}: t/d วินาที (ทศนิยม 2), x ข้อความ, v = 2/3 (คนร้องคนที่ 2/3) หรือ "bg" (คอรัสทั้งบรรทัด); server เติม best/editedAt/picked
- `scripts/lyrics_conf.py` `SRC_LABEL = {` — ค่า src ทั้งหมด (manual-edit/-lrc/-txt, yt-sub, yt-auto, lrclib, lrclib-plain, web/description, joox, ytmusic, netease, musixmatch, library, ocr); timeSrc = self / auto-cap / asr / fa
- `scripts/gen_lyrics.py` `def from_edit(` — อ่าน lyrics-in/<vid>.json ที่ Studio เขียน ({v, videoId, lang, engine, src:"manual-edit", timeSrc:"self", duration, editedAt, lines}) ใช้ตามไฟล์เป๊ะ ชนะทุกแหล่ง
- `lyrics-in/README.md` `## เมื่อเพลงไหนเนื้อผิดหรือเวลาเพี้ยน` `ที่ Studio บันทึกไว้` `จะ **ไม่ถูกเขียนทับ**` — แก้ใน Studio / วางไฟล์เอง (.json/.lrc/.txt) + กติกาไม่เขียนทับ / เลิกใช้เนื้อที่แก้เอง
- `make_wanted.py` — สร้าง lyrics-in/WANTED.tsv: ทุกเพลง + ชื่อ/ศิลปิน + src + จำนวนบรรทัด + สถานะ (ยังไม่มี/มีไฟล์วางเอง)
- `lyrics_check.py` — ตรวจ lyrics.json ทุกเพลงเป็นตัวเลข (เวลาเรียงผิด/ทับ/เลยจบเพลง/บรรทัดว่าง/คลุมน้อย) → lyrics-in/CHECK.tsv ไม่แสดงเนื้อ
! lyrics-in/*.json = เนื้อที่ผู้ใช้แก้เอง (manual-edit) — ห้ามเขียนทับ/แก้/ลบ และห้ามให้งานอัตโนมัติแทนที่ (บางไฟล์อาจยังไม่ commit ในโฟลเดอร์หลัก); ดูโครงด้วย head -c เท่านั้น
! ค่า v ต้องตรงกันสามที่: gen_lyrics.VOICES, server._clean_edit_lines, จอ VOICE_CLS (player.html/studio.html); make_wanted.py / lyrics_check.py ใช้ path สัมพัทธ์ ต้องรันจากรากโปรเจกต์

### โฟลเดอร์เพลง songs/yt/<ชื่อคลิป [videoId]>/ — ไฟล์ในแต่ละเพลง
คำค้น: โฟลเดอร์เพลง, songs, songs/yt, ไฟล์เพลง, videoId, info.json, vocals.m4a, no_vocals.m4a, audio.m4a, video.mp4, cover.jpg, สเต็ม, stems, แยกเสียง, demucs, lyrics.words.json, lyrics.best.json, lyrics.check.json, lang.json, lyrics.edits, lyrics.offset.json, คีย์, trim.json, จุดเริ่ม, จุดจบ
- `scripts/gen_lyrics.py` `RE_VID = re.compile` `def song_duration(` — ชื่อโฟลเดอร์ลงท้าย [videoId 11 ตัว]; info.json (yt-dlp: title/uploader/duration/description/automatic_captions), ไม่มี duration ค่อย ffprobe audio.m4a/video.mp4
- `scripts/fa_align.py` `def song_dir(` `def default_audio(` — หาโฟลเดอร์จาก vid; เสียงร้อง vocals.m4a (demucs) ไม่มีใช้ audio.m4a; no_vocals.m4a = ดนตรี, video.mp4, cover.jpg
- `scripts/fetch_subs.py` `ซับไทยของจริง (คนพิมพ์)` `auto-caption (ASR ของ YouTube) คนละชั้นคุณภาพ` — sub.<lang>.vtt / auto.<lang>.vtt
- `scripts/gen_lyrics.py` `def write_out(` `def _no_lyrics(` — lyrics.json, lyrics.prev.json (สำรองเมื่อแหล่งเปลี่ยน), lyrics.nolyr.json {v, videoId, at, why}, ลบ lyrics.offset.json เมื่อได้เวลาชุดใหม่
- `scripts/verify_lyrics.py` `off_f = folder / "lyrics.offset.json"` `def check_path(` — lyrics.offset.json {offset} (ปรับจากรีโมท/Studio), lyrics.check.json {v, score, shift, g, defects, verdict, measuredBy, reports…}
- `scripts/lyrics_sources.py` `def write_lang(` — lang.json {lang, by, at} (by = title/lrclib/whisper/manual …)
- `lyrics-in/README.md` `## โหมดคาราโอเกะ` `## ระบบเลือกเนื้อดีที่สุดจากทุกแหล่ง` `## เปลี่ยนคีย์เพลง` — lyrics.words.json {texts, k, conf, en, audio}, lyrics.best.json {action, reason, cands, refine}, vocals.k+N.m4a / no_vocals.k+N.m4a
- `server.py` `def _trim(` — trim.json {start, end, fadeIn, fadeOut, at} จุดเริ่ม/จบ/เฟดรายเพลง (แท็บ ✂️ ใช้ตอนเปิดโหมด Custom)
- `.gitignore` `songs/` — songs/ ไม่อยู่ใน git (ไม่มีใน worktree); lyrics.edits/ (ประวัติ 20 รุ่น), lyrics.reports.json (แจ้งเนื้อไม่ตรง), songs/.thumbs/ สร้างโดย server.py
! ห้ามอ่าน/แก้ไฟล์เนื้อจริงใน songs/yt (lyrics*.json) — ดูโครงด้วย ls / คีย์ JSON เท่านั้น; ทดสอบใช้คลังจำลองผ่าน KARA_SONGS_DIR
! แยกเสียงใหม่ = แคช FA/_va เดิมใช้ไม่ได้ (ผูกลายเซ็นไฟล์เสียง) — server ลบให้ใน _purge_audio_caches

### แคชใต้ lyrics-preview/ (_fa _va _ocr _seg _src _srt _eval)
คำค้น: แคช, cache, lyrics-preview, _fa, _va, _ocr, _seg, _src, _srt, _eval, ล้างแคช, ลบแคช, npz, KARA_FA_CACHE, KARA_VA_CACHE, KARA_OCR_CACHE, โมเดล, .cache
- `.gitignore` `lyrics-preview/` `.cache/` — แคชทั้งหมดไม่อยู่ใน git; .cache/ = โมเดล HuggingFace (~10 GB ใน .cache/hf) + ไบนารี .cache/bin/kara_ocr
- `scripts/fa_align.py` `CACHE = Path(os.environ.get("KARA_FA_CACHE")` — _fa/<vid>.<โมเดล>.npz (+ .side.npz) log-prob ของ FA
- `scripts/vocal_activity.py` `CACHE = Path(os.environ.get("KARA_VA_CACHE")` — _va/<vid>.npz แผนที่เสียงร้อง
- `scripts/ocr_lyrics.py` `CACHE = Path(os.environ.get("KARA_OCR_CACHE")` — _ocr/<vid>.json ผล OCR (จำคลิปที่ไม่มีเนื้อในภาพด้วย)
- `scripts/gen_lyrics.py` `SEG = Path(` `SRC = BASE / "lyrics-preview" / "_src"` `SRT = BASE / "lyrics-preview" / "_srt"` — _seg/<vid>.<tag>.json ผลถอดเสียง, _src/<vid>.txt เนื้อจาก description, _srt/<vid>.srt พรีวิว
- `scripts/eval_lyrics.py` `EVAL = Path(` — _eval/ (src/ = ผู้สมัครที่แช่ไว้) ของชุดวัดผล
- `scripts/ab_asr.py` `AB_LOG = ` — _ab.jsonl ผล A/B โมเดลถอดเสียง
! แคชผูกลายเซ็นไฟล์ (ชื่อ:ขนาด:mtime) — เปลี่ยนรูปแบบแคชต้องขึ้น VERSION / SEG_V; ลบ _seg = ต้องถอดเสียงใหม่ (GPU นาน), ลบ _fa = FA ใหม่ ~10 วิ/เพลง
! ตั้ง KARA_FA_CACHE อย่างเดียว → _va/_ocr ย้ายไปอยู่ข้างโฟลเดอร์ _fa นั้นอัตโนมัติ (เว้นแต่ตั้ง KARA_VA_CACHE/KARA_OCR_CACHE)

### ตั้งค่าจอทีวี tv.json + ไฟล์ลับ .studio.json
คำค้น: tv.json, combos.json, ตั้งค่าจอ, ตั้งค่าหน้าจอหลัก, จอทีวี, โลโก้, logo, .tv/logo.png, .studio.json, PIN, รหัส Studio, secret, token, mxmToken, publicUrl, gitignore, ความลับ, history.json
- `tv.json` — ค่าจอหลักที่ตั้งจาก Studio 📺 (title, titleHide, singer, chips, lyrScale, lyrColor, lyrDim, karaColor, lyrBg, lyrShadow, lyrLift, qr, qrSize, time, next, addCard, logo, logoSize, idleText, countdown, voices, fadeIn, fadeOut, custom, customLead, customTail, customAud, skipBtn, skipMin); รูปมุมขวาบนที่ .tv/logo.png
- `lyrics-in/README.md` `## ตั้งค่าหน้าจอหลัก` — ความหมายของแต่ละค่า (ลบไฟล์ = กลับค่าเริ่มต้น)
- `.gitignore` `.studio.json` `history.json` `.chrome-player/` — ไฟล์ลับ/ส่วนตัวนอก git: .studio.json = {pin, secret, tv (รหัสลิงก์จอ), publicUrl, mxmToken}, history.json = ประวัติเพลง + ชื่อคนร้อง, โปรไฟล์ Chrome ของจอหลัก
- `server.py` `COMBOS_FILE = ` — combos.json (สร้างเมื่อสร้างคอมโบแรก): 🎬 คอมโบที่จัดในแท็บ ✂️ [{id, name, items: [{videoId, title, start?, end?, fadeIn?, fadeOut?}]}]
- `cloudflare.command` `set_public_url() {` — ตัวอย่างแก้ .studio.json แบบรักษาฟิลด์อื่น (server อ่านใหม่เองตาม mtime ไม่ต้องรีสตาร์ท)
! คีย์ใหม่ใน tv.json ต้องเพิ่มใน TV_SCHEMA ของ server.py (_clean_tv ทิ้งคีย์ที่ไม่รู้จัก) + ปุ่มใน Studio 📺; ปิดแล้วจอต้องเหมือนเดิม
! ห้าม commit/แสดงค่าใน .studio.json (PIN, secret, token Musixmatch; KARA_STUDIO_PIN ทับ PIN ได้); tv.json อยู่ใน git แต่ผู้ใช้แก้จาก Studio บ่อย (มักมีการแก้ค้างที่ยังไม่ commit) — อย่า commit ทับ

## รัน / ติดตั้ง / ทดสอบ

### เปิด/ปิดเซิร์ฟเวอร์ + จอหลัก + ติดตั้ง
คำค้น: เปิดเซิร์ฟเวอร์, ปิดเซิร์ฟเวอร์, รีสตาร์ท, start, stop, run, จอหลัก, เปิดจอ, kiosk, Chrome, venv, ติดตั้ง, install, requirements, yt-dlp, ค้นหาไม่เจอ, อัปเดต, ลูกกำพร้า, demucs ค้าง, พอร์ต 8080
- `run.sh` `exec ./.venv/bin/python -u server.py` `pip install -q -r requirements.txt` — สร้าง .venv + ติดตั้งครั้งแรก แล้วรัน server.py
- `player.command` `server_pids() {` `nohup ./run.sh` `MODE="--start-fullscreen"` — เปิดเซิร์ฟเวอร์ถ้ายังไม่รัน (log /tmp/kara.log) → ลิงก์ Cloudflare → บอก IP ในบ้าน → Chrome แอปโหมดโปรไฟล์ .chrome-player (--kiosk, --no-tunnel)
- `stop.command` `is_our_server() {` `kill -TERM $targets` `orphans="$(pgrep` `lyr="$(pgrep` — ปิด Cloudflare → จอหลัก → TERM เซิร์ฟเวอร์ (เซฟ history.json) → KILL ถ้าค้าง → เก็บกวาด demucs / gen_lyrics / verify_lyrics / fa_align
- `update.sh` `--upgrade yt-dlp certifi` — ซ่อมค้นหา YouTube ไม่เจอ: อัปเดต yt-dlp + certifi แล้วลองค้นจริง
- `requirements.txt` `mlx-whisper` `demucs==4.1.0` `transformers` — dependency ทั้งหมด (ytmusicapi/syncedlyrics = แหล่งเนื้อ, transformers = FA, pedalboard = เปลี่ยนคีย์)
! ผู้ใช้รันเซิร์ฟเวอร์จริงเอง (python -u server.py พอร์ต 8080) — ห้ามรัน stop.command / player.command / run.sh เอง; ทดสอบใช้เซิร์ฟเวอร์พอร์ตอื่น + คลังจำลอง
! stop.command ฆ่า Python ทุกตัวที่ args มี server.py (รวมเซิร์ฟเวอร์ทดสอบ) และ gen_lyrics.py/verify_lyrics.py/fa_align.py ทุกตัว (รวมที่รันมือ/eval); player.command ใช้กติกาเดียวกันเช็กว่าเซิร์ฟเวอร์รันอยู่

### ลิงก์จากนอกบ้าน (Cloudflare Tunnel)
คำค้น: cloudflare, tunnel, ลิงก์นอกบ้าน, เข้าจากนอกบ้าน, โดเมน, trycloudflare, publicUrl, QR, https, cloudflared, quick tunnel, ลิงก์สาธารณะ
- `cloudflare.command` `--quick)` `ล้างลิงก์สาธารณะแล้ว` `--status)` — โหมดทดลอง (ลิงก์ *.trycloudflare.com สุ่ม, pid/log ที่ /tmp/kara-cloudflare.*), --stop ล้าง publicUrl, --status ดูสถานะ
- `cloudflare.command` `HOST="$1"; shift` `# 5. รันเป็นบริการตอนเปิดเครื่อง` — โหมดโดเมนจริง: login → สร้างอุโมงค์ pu-karaoke → config → DNS → ติดตั้ง service (--no-service ข้าม)
- `cloudflare.command` `set_public_url() {` `ensure_cloudflared() {` `need_server() {` — เขียน publicUrl ลง .studio.json, ติดตั้ง cloudflared ด้วย brew, เช็กว่าเซิร์ฟเวอร์รันอยู่
- `player.command` `elif ! ./cloudflare.command --quick` — เปิดลิงก์ทดลองเองตอนเปิดจอ (ข้ามด้วย --no-tunnel หรือ KARA_NO_TUNNEL=1)
- `stop.command` `./cloudflare.command --stop` — ปิดอุโมงค์ทดลองตอนปิดระบบ
! QR บนจอ/ลิงก์ในรีโมทอ่าน publicUrl จาก .studio.json (server อ่านใหม่ตาม mtime ไม่ต้องรีสตาร์ท); ลิงก์ทดลองเปลี่ยนทุกครั้งที่รัน

### ชุดวัดผล / ทดสอบระบบเนื้อเพลง (eval)
คำค้น: วัดผล, ทดสอบ, eval, evaluation, benchmark, gold, silver, ไม้บรรทัด, freeze, best, refine-synth, check, lyrcore, display, node, A/B, ab test, KARA_SONGS_DIR, KARA_FA_CACHE, KARA_FA_NO_COMPUTE, KARA_EVAL_DIR, คลังจำลอง
- `scripts/eval_lyrics.py` `def main():` `def refsets(` `def trusted(` `SILVER_MIN = ` — ตารางคำสั่ง + ชุดไม้บรรทัด gold (manual-edit ตัดบรรทัดเวลาเดา/อัด) / silver (yt-sub ที่ FA ตรง ≥ 75%) แยกหมวด fast/backing/overlap/repeated/normal
- `scripts/eval_lyrics.py` `def cmd_gold(` `def cmd_fa(` `def cmd_display(` `def cmd_core(` — gold สรุปไม้บรรทัด, fa [--opt paren] [--set gold|silver|all] [--side], display ตรรกะจอเก่า vs ใหม่ใต้ node, core เช็กบล็อก lyrcore ใน player.html = studio.html
- `scripts/eval_lyrics.py` `def cmd_freeze(` `def cmd_best(` `def cmd_check(` `def cmd_refine_synth(` — freeze แช่ผู้สมัครทุกแหล่งลง _eval/src, best [--refine] เล่นซ้ำงานเลือกเนื้อ, check [--nosynth] ป้าย v1 vs v2, refine-synth ทำเวลาเสียเองแล้ววัดการซ่อม
- `scripts/eval_lyrics.py` `def _server(` `os.environ.setdefault("KARA_FA_CACHE"` — import server.py แบบไม่เปิดเซิร์ฟเวอร์ (KARA_STUDIO_PIN=0000) ชี้คลังไป KARA_SONGS_DIR; env อื่น KARA_EVAL_DIR / KARA_NODE
- `scripts/eval_display.js` `const core = html.slice(` `function oldFrame(` `function measure(` — node: ดึงบล็อก lyrcore จาก static/player.html มาวัด seen/lit/evict (stdin {"songs"} → stdout {"new","old","songs"})
- `scripts/ab_asr.py` `def cmd_score(` — A/B โมเดลถอดเสียง (รายละเอียดในหัวข้อถอดเสียง whisper)
- `scripts/ab_vtt.py` `def main() -> None:` — เทสเกณฑ์คัดซับ from_vtt (ไม่ใช้เน็ต/GPU)
- `lyrics-in/README.md` `## ชุดวัดผล` `KARA_FA_NO_COMPUTE=1` — คำสั่งทั้งหมด + ใช้ก่อนเปลี่ยนอะไรที่กระทบเวลา
! ตั้ง KARA_FA_NO_COMPUTE=1 ระหว่างที่มีคนใช้เครื่อง (ไม่มีแคช FA = raise แทนคำนวณ ไม่แย่ง GPU); eval เขียนได้แค่ _eval/ กับแคช — ห้ามแตะเนื้อจริง
! eval เรียกของภายใน server.py ตรง ๆ (_gather_sources, _best_decide, _score_fa, DL_DIR, SEG_CACHE) — เปลี่ยนชื่อใน server ต้องแก้ที่นี่ด้วย
! ทดสอบกับคลังจำลอง: KARA_SONGS_DIR (+ KARA_SEG_DIR, KARA_LYRICS_IN ของ gen_lyrics, KARA_VA_CACHE / KARA_OCR_CACHE) ชี้ไปที่อื่นได้หมด
