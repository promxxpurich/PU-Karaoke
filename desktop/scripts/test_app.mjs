// ทดสอบแอปจริงบนคลังปลอม (videoId ขึ้นต้น TEST, พอร์ต 8765, ไม่แตะพอร์ต 8080 และไม่ปิดเซิร์ฟเวอร์ตัวไหนนอกพอร์ตทดสอบ)
//   node desktop/scripts/test_app.mjs <PY=python ของโปรเจกต์>
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DESK = path.dirname(HERE);
const ROOT = path.dirname(DESK);
const PY = process.argv[2];
const SHOTS = process.argv[3] || fs.mkdtempSync(path.join(os.tmpdir(), 'kara-app-shots-'));
const PORT = 8765;
const BASE = `http://localhost:${PORT}`;
const CDP = 9333;
const VID = 'TESTapp0001';
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'kara-apptest-'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let fails = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'ผ่าน' : 'ไม่ผ่าน'}  ${name}${extra ? ` ${extra}` : ''}`); if (!ok) fails += 1; };

// server.py อ่านเพลงจาก <โปรเจกต์>/songs/yt จึงวางเพลงปลอมใน worktree (ไฟล์นี้ต้องรันจาก worktree เท่านั้น)
const FIX = path.join(ROOT, 'songs', 'yt', `TEST app song [${VID}]`);
function makeFixtures() {
  if (fs.realpathSync(ROOT) === fs.realpathSync(path.join(os.homedir(), 'Documents', 'kara'))) throw new Error('ห้ามรันจากโฟลเดอร์จริง ใช้ worktree');
  fs.mkdirSync(FIX, { recursive: true });
  const ff = (...a) => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...a]);
  fs.writeFileSync(path.join(FIX, 'info.json'), JSON.stringify({ id: VID, title: 'TEST app song', uploader: 'test', duration: 40 }));
  ff('-f', 'lavfi', '-i', 'testsrc=s=320x180:r=10:d=40', '-f', 'lavfi', '-i', 'sine=f=440:d=40', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', path.join(FIX, 'video.mp4'));
  for (const n of ['audio', 'vocals', 'no_vocals']) ff('-f', 'lavfi', '-i', 'sine=f=330:d=40', '-c:a', 'aac', path.join(FIX, `${n}.m4a`));
  fs.writeFileSync(path.join(FIX, 'lyrics.json'), JSON.stringify({ v: 1, src: 'manual-edit', lines: [{ t: 0.5, d: 30, x: 'ทดสอบเนื้อเพลง' }] }));
}
const appEnv = (extra = {}) => ({
  ...process.env, KARA_APP_PORT: String(PORT), KARA_APP_PROJECT: ROOT, KARA_APP_PYTHON: PY, KARA_APP_NO_KILL: '1',
  KARA_APP_CLOUDFLARE: path.join(TMP, 'fake-cf.sh'), KARA_APP_TEST_ANSWERS: '', ELECTRON_RUN_AS_NODE: undefined,
  KARA_YT_COOKIES: 'none', KARA_WARM: 'off', KARA_STUDIO_PIN: '0000',
  ...extra,
});
function launch(env) {
  const log = fs.openSync(path.join(TMP, 'app.log'), 'a');
  const proc = spawn(path.join(DESK, 'node_modules', '.bin', 'electron'),
    ['.', `--remote-debugging-port=${CDP}`, `--user-data-dir=${path.join(TMP, 'profile')}`], { cwd: DESK, env, stdio: ['ignore', log, log] });
  return proc;
}
async function targets() {
  for (let i = 0; i < 100; i++) { try { return await (await fetch(`http://127.0.0.1:${CDP}/json`)).json(); } catch { await sleep(200); } }
  throw new Error('ต่อ CDP ไม่ได้');
}
function connect(url) {
  const ws = new WebSocket(url);
  let id = 0;
  const pend = new Map();
  const errors = [];
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
    if (d.method === 'Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text);
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    const timer = setTimeout(() => { pend.delete(i); rej(new Error(`CDP หมดเวลา: ${method}`)); }, 15000);
    pend.set(i, (d) => { clearTimeout(timer); res(d); });
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  const ev = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(`${expression}: ${JSON.stringify(r.result.exceptionDetails.exception?.description)}`);
    return r.result?.result?.value;
  };
  return new Promise((res) => { ws.onopen = async () => { await send('Runtime.enable'); await send('Page.enable'); res({ send, ev, errors, ws }); }; });
}
const until = async (fn, ms = 30000) => { const end = Date.now() + ms; while (Date.now() < end) { try { if (await fn()) return true; } catch { /* ยังไม่พร้อม */ } await sleep(150); } return false; };
const shot = async (c, name) => { const r = await c.send('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(r.result.data, 'base64')); };
async function pageOf(match) {
  let t;
  await until(async () => { t = (await targets()).find((x) => match(x.url)); return !!t; });
  return t ? connect(t.webSocketDebuggerUrl) : null;
}
function req(p, headers = {}, method = 'GET') {
  return new Promise((res, rej) => {
    const r = http.request({ host: '127.0.0.1', port: PORT, path: p, method, headers: { host: `localhost:${PORT}`, ...headers } }, (x) => { let b = ''; x.on('data', (d) => { b += d; }); x.on('end', () => res({ status: x.statusCode, body: b })); });
    r.on('error', rej);
    r.end();
  });
}
const GUEST = { 'x-forwarded-for': '8.8.8.8' };
const wsOpens = (headers) => new Promise((res) => {
  const r = http.request({ host: '127.0.0.1', port: PORT, path: '/ws', headers: { connection: 'Upgrade', upgrade: 'websocket', 'sec-websocket-key': 'dGhlIHNhbXBsZSBub25jZQ==', 'sec-websocket-version': '13', host: `localhost:${PORT}`, ...headers } });
  r.on('upgrade', (_a, s) => { s.destroy(); res(true); });
  r.on('response', () => res(false));
  r.on('error', () => res(false));
  r.end();
});
const pyPid = () => { try { return Number(execFileSync('/usr/sbin/lsof', ['-nP', `-iTCP:${PORT}`, '-sTCP:LISTEN', '-t']).toString().trim().split('\n')[0]); } catch { return 0; } };
// SIGTERM ครั้งเดียว = Electron สั่งออกตามปกติ ผ่าน before-quit และกล่องยืนยันเหมือนกด ⌘Q
async function quitApp(proc, expectAsk) {
  proc.kill('SIGTERM');
  const ok = await until(() => proc.exitCode !== null || proc.signalCode !== null, 15000);
  if (!ok) proc.kill('SIGKILL');
  check(`ออกจากแอป${expectAsk ? ' (ยืนยันแล้ว)' : ''} และปิด Python ตาม`, ok && await until(() => pyPid() === 0, 8000));
  await until(async () => { try { await fetch(`http://127.0.0.1:${CDP}/json`); return false; } catch { return true; } }, 8000);
}

async function mainRun() {
  fs.writeFileSync(path.join(TMP, 'fake-cf.sh'), `#!/bin/bash\necho "$@" >> "${TMP}/cf.log"\nexit 0\n`, { mode: 0o755 });
  // ลำดับคำตอบ: ปิดเซิร์ฟเวอร์ตอนมีเพลง ยกเลิก, ยืนยัน · ออกจากแอปตอนเปิด ยืนยัน
  const proc = launch(appEnv({ KARA_APP_TEST_ANSWERS: '1,0,0' }));
  const m = await pageOf((u) => u.endsWith('ui/index.html'));
  const S = () => m.ev('S');
  await until(async () => (await S())?.server === 'off', 90000);
  let s = await S();
  check('เปิดแอป: Python พร้อม โหมดเฉพาะเครื่อง', s.server === 'off' && s.ready);
  await shot(m, '01-home-off');
  check('ก่อนเปิด: เครื่องอื่นเข้าหน้ารีโมทไม่ได้ (503)', (await req('/r', GUEST)).status === 503);
  check('ก่อนเปิด: เครื่องอื่นต่อ WebSocket ไม่ได้', !(await wsOpens(GUEST)));
  check('ก่อนเปิด: เครื่องนี้เรียกหน้า Studio ได้', (await req('/studio')).status === 200);
  check('API ควบคุมแอป ไม่มี token = 404', (await req('/api/app/serve', {}, 'POST')).status === 404);
  check('API ควบคุมแอป token ผิด = 404', (await req('/api/app/serve', { 'x-kara-app': 'ผิด'.length ? 'nope' : '' }, 'POST')).status === 404);
  check('ไม่พบการเปิดจอทีวีก่อนกดเปิด', !(await S()).tv.open);

  await m.ev(`document.querySelector('[data-tab=remote]').click()`); await sleep(120);
  check('รีโมทล็อกก่อนเปิด', await m.ev(`!!document.querySelector('.locked') && !document.querySelector('iframe[data-frame=remote]')`));
  await m.ev(`document.querySelector('[data-tab=tv]').click()`); await sleep(120);
  check('จอทีวีล็อกก่อนเปิด', await m.ev(`!!document.querySelector('.locked')`));

  await m.ev(`document.querySelector('[data-tab=studio]').click()`);
  const studio = await pageOf((u) => u.includes(`:${PORT}/studio`));
  check('Studio จริงโหลดในแอป', !!studio && await until(() => studio.ev(`document.body.innerText.includes('TEST app song')`), 20000));
  await shot(m, '02-studio-off');

  await m.ev(`document.querySelector('[data-tab=settings]').click()`);
  const tvset = await pageOf((u) => u.includes(`:${PORT}/tvset`));
  check('หน้าตั้งค่าจอทีวีโหลดในแอป', !!tvset && await until(() => tvset.ev(`!!document.querySelector('#f-lyrScale')`), 15000));
  check('ค่าจอทีวีครบ 31 ค่า', await tvset.ev('TV_FIELDS.length') === 31);
  const schema = JSON.parse((await req('/api/studio/tv')).body);
  check('ชื่อและค่าเริ่มต้นตรงกับ TV_SCHEMA จริง', await tvset.ev(`JSON.stringify(TV_FIELDS.map(f=>[f.key,f.def]).sort())`) === JSON.stringify(Object.entries(schema.default).filter(([k]) => k !== 'logoUrl').sort()),
    '');
  await tvset.ev(`(()=>{const e=document.querySelector('#f-lyrScale');e.value=140;e.dispatchEvent(new Event('input'))})()`);
  check('ก่อนเปิด: ปรับค่าแล้วบันทึกจริงลงเซิร์ฟเวอร์', await until(async () => JSON.parse((await req('/api/studio/tv')).body).tv.lyrScale === 140, 5000));
  check('พรีวิวชี้จุดที่เปลี่ยน', await tvset.ev(`document.querySelector('#pvtag').textContent.includes('140')`));
  await shot(m, '03-tvset');
  check('tv.json ถูกเขียน', JSON.parse(fs.readFileSync(path.join(ROOT, 'tv.json'), 'utf8')).lyrScale === 140);
  await tvset.ev(`document.querySelector('#cfgreset').click()`);
  check('คืนค่าทั้งหมด', await until(async () => JSON.parse((await req('/api/studio/tv')).body).tv.lyrScale === 100, 5000));
  check('หน้าตั้งค่าไม่มี error', tvset.errors.length === 0, tvset.errors.join(' | ').slice(0, 300));

  for (const sec of ['system', 'network', 'python', 'theme']) {
    await m.ev(`document.querySelector('[data-sec=${sec}]').click()`); await sleep(350);
    await shot(m, `04-settings-${sec}`);
  }
  await m.ev(`document.querySelector('[data-sec=python]').click()`);
  check('โหมด Python อ่านค่าจริงได้', await until(() => m.ev(`!!document.querySelector('input[name=fa]:checked')`), 8000));
  await m.ev(`document.querySelector('input[name=fa][value=off]').click()`);
  check('โหมด Python บันทึกจริง', await until(async () => JSON.parse((await req('/api/studio/settings')).body).fa.mode === 'off', 5000));
  await m.ev(`document.querySelector('[data-sec=system]').click()`); await sleep(300);
  await until(() => m.ev(`document.querySelector('#pin').value.length>=4`), 3000);
  await m.ev(`(()=>{const p=document.querySelector('#pin');p.value='5678';document.querySelector('#pinsave').click()})()`);
  check('เปลี่ยน PIN ลงไฟล์ โดยฟิลด์อื่นยังอยู่', await until(() => { const j = JSON.parse(fs.readFileSync(path.join(ROOT, '.studio.json'), 'utf8')); return j.pin === '5678' && !!j.secret; }, 3000));

  // เปิดเซิร์ฟเวอร์
  const pidBefore = pyPid();
  await m.ev(`document.querySelector('#power').click()`);
  check('กดเปิด: เซิร์ฟเวอร์เปิด', await until(async () => (await S()).server === 'on', 15000));
  check('กดเปิด: โปรเซสเดิม ไม่รีสตาร์ท', pyPid() === pidBefore);
  check('หลังเปิด: เครื่องอื่นเข้ารีโมทได้', (await req('/r', GUEST)).status === 200);
  check('หลังเปิด: เครื่องอื่นต่อ WebSocket ได้', await wsOpens(GUEST));
  check('หลังเปิด: กันเครื่องหลับ', (await S()).sleepBlocked);
  check('จอทีวีเปิดเอง', (await S()).tv.open);
  check('จอทีวีเต็มจอ', await until(async () => (await S()).tv.fullscreen, 10000));
  const tv = await pageOf((u) => u === `${BASE}/`);
  check('จอทีวีโหลด player.html จริง', !!tv && await until(() => tv.ev(`!!document.querySelector('#idle')`), 10000));
  await sleep(600);
  await shot(tv, '05-tv-idle');
  check('รองรับ AV1', await tv.ev(`MediaSource.isTypeSupported('video/mp4; codecs="av01.0.05M.08"')`));
  check('รองรับ H.264 + AAC', await tv.ev(`document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"')!==''`));
  check('เล่น autoplay ได้โดยไม่ต้องแตะจอ', await tv.ev(`(async()=>{const a=new (window.AudioContext||webkitAudioContext)();await new Promise(r=>setTimeout(r,300));const st=a.state;a.close();return st==='running'})()`));

  await m.ev(`document.querySelector('[data-tab=remote]').click()`);
  const remote = await pageOf((u) => u.endsWith(`:${PORT}/r`));
  check('รีโมทจริงโหลดในแอป', !!remote && await until(() => remote.ev('document.readyState==="complete"'), 8000));
  await sleep(500);
  await shot(m, '06-remote-on');
  const guest = new WebSocket(`ws://localhost:${PORT}/ws`);
  await new Promise((r) => { guest.onopen = r; });
  guest.send(JSON.stringify({ action: 'add', videoId: VID, title: 'TEST app song', singer: 'แขกทดสอบ' }));
  check('สั่งเพลงแล้ววิดีโอเล่นเองบนจอทีวี', await until(() => tv.ev(`(()=>{const v=[...document.querySelectorAll('video')].find(x=>x.currentSrc);return !!v&&!v.paused&&v.currentTime>0.5})()`), 20000));
  const t1 = await tv.ev(`[...document.querySelectorAll('video')].find(x=>x.currentSrc).currentTime`);
  check('ระบบผสมเสียงสเต็มทำงาน', await until(() => tv.ev(`stemMode && ctx && ctx.state==='running'`), 10000));
  await m.ev(`document.querySelector('[data-tab=home]').click()`);  // ซ่อนหน้าหลักไม่กระทบจอ
  await sleep(1500);
  const t2 = await tv.ev(`[...document.querySelectorAll('video')].find(x=>x.currentSrc).currentTime`);
  check('วิดีโอเดินต่อเนื่อง', t2 > t1, `${t1.toFixed(1)} → ${t2.toFixed(1)}`);
  await until(() => tv.ev(`document.body.innerText.includes('ทดสอบเนื้อเพลง')`), 5000);
  await shot(tv, '07-tv-playing');
  await shot(m, '08-home-on');
  check('จอทีวีไม่มี error', tv.errors.length === 0, tv.errors.join(' | ').slice(0, 300));

  // ปิดตอนมีเพลง
  await m.ev(`document.querySelector('#power').click()`); await sleep(1500);
  check('ปิดตอนมีเพลง + ยกเลิก = ยังเปิดอยู่', (await S()).server === 'on');
  await m.ev(`document.querySelector('#power').click()`);
  check('ปิดตอนมีเพลง + ยืนยัน = กลับโหมดเฉพาะเครื่อง', await until(async () => (await S()).server === 'off', 40000));
  s = await S();
  check('ปิดแล้ว: จอทีวีปิด กันหลับปิด', !s.tv.open && !s.sleepBlocked);
  check('ปิดแล้ว: Python ตัวใหม่', pyPid() !== pidBefore && pyPid() !== 0);
  check('ปิดแล้ว: เครื่องอื่นเข้าไม่ได้อีก', (await req('/r', GUEST)).status === 503);
  await m.ev(`document.querySelector('[data-tab=studio]').click()`);
  check('Studio เดิมต่อกลับเอง', await until(() => studio.ev(`document.body.innerText.includes('TEST app song') && !document.body.classList.contains('off')`), 15000));

  await m.ev(`document.querySelector('#power').click()`);
  await until(async () => (await S()).server === 'on', 15000);

  // ล่ม 3 ครั้ง
  const kill9 = () => process.kill(pyPid(), 'SIGKILL');
  kill9();
  check('ล่มครั้ง 1: เปิดใหม่เอง', await until(async () => (await S()).server === 'restarting', 5000) && (await S()).notice.text.includes('1/2'));
  check('ล่มครั้ง 1: กลับมาและยังเปิดรับแขก', await until(async () => (await S()).server === 'on', 40000) && (await req('/r', GUEST)).status === 200);
  kill9();
  await until(async () => (await S()).notice?.text.includes('2/2'), 5000);
  check('ล่มครั้ง 2: เปิดใหม่เอง', await until(async () => (await S()).server === 'on', 40000));
  kill9();
  check('ล่มครั้ง 3: หยุด ปิดจอทีวี', await until(async () => { const x = await S(); return x.server === 'crashed' && !x.tv.open; }, 8000));
  await sleep(1000);
  check('ล่มครั้ง 3: ไม่เปิด Python เองอีก', pyPid() === 0);
  await m.ev(`document.querySelector('#showlog').click()`); await sleep(200);
  await shot(m, '09-crashed');
  await m.ev(`document.querySelector('#power').click()`);
  check('เปิดอีกครั้งได้', await until(async () => { const x = await S(); return x.server === 'on' && x.crashes === 0; }, 40000));
  await until(async () => (await S()).tv.fullscreen, 8000);
  check('หน้าหลักไม่มี error', m.errors.length === 0, m.errors.join(' | ').slice(0, 300));
  await quitApp(proc, true);
}

// ลิงก์นอกบ้าน: ค่าเริ่มต้นเปิดพร้อมเซิร์ฟเวอร์ (สคริปต์ปลอม ไม่เปิดอุโมงค์จริง)
async function tunnelRun() {
  const URL_ = 'https://test-link.trycloudflare.com';
  const cfLog = path.join(TMP, 'cf.log');
  fs.writeFileSync(path.join(TMP, 'fake-cf.sh'), `#!/bin/bash
echo "$@" >> "${cfLog}"
url=""; [ "$1" = "--quick" ] && url="${URL_}"
python3 - "$url" <<'PY'
import json,sys,pathlib
p=pathlib.Path('.studio.json'); c=json.loads(p.read_text()) if p.exists() else {}
c['publicUrl']=sys.argv[1]; p.write_text(json.dumps(c))
PY
`, { mode: 0o755 });
  const cf = () => (fs.existsSync(cfLog) ? fs.readFileSync(cfLog, 'utf8') : '');
  const proc = launch(appEnv({ KARA_APP_TEST_ANSWERS: '0,0,0' }));
  const m = await pageOf((u) => u.endsWith('ui/index.html'));
  const S = () => m.ev('S');
  await until(async () => (await S())?.server === 'off', 90000);
  check('ลิงก์: ค่าเริ่มต้นเปิด', (await S()).tunnel === true);
  check('ลิงก์: ก่อนเปิดเซิร์ฟเวอร์ยังไม่เรียก --quick', !cf().includes('--quick'));
  await m.ev(`document.querySelector('#power').click()`);
  check('ลิงก์: กดเปิดเซิร์ฟเวอร์แล้วเปิดเอง', await until(async () => (await S()).urls.publicUrl === URL_, 20000));
  const tv = await pageOf((u) => u === `${BASE}/`);
  check('ลิงก์: จอทีวีเปลี่ยน QR เป็นลิงก์นี้เอง', await until(() => tv.ev(`document.querySelector('.qcard img').src.includes(encodeURIComponent('${URL_}'))`), 10000));
  await m.ev(`document.querySelector('[data-tab=home]').click()`); await sleep(300);
  await shot(m, '20-home-tunnel');
  process.kill(pyPid(), 'SIGKILL');
  await until(async () => (await S()).server === 'restarting', 5000);
  check('ลิงก์: เซิร์ฟเวอร์ล่มแล้วเปิดใหม่ ลิงก์เดิมยังอยู่', await until(async () => { const x = await S(); return x.server === 'on' && x.urls.publicUrl === URL_; }, 40000));
  await m.ev(`document.querySelector('#power').click()`);
  await until(async () => (await S()).server === 'off', 40000);
  check('ลิงก์: ปิดเซิร์ฟเวอร์แล้วปิดอุโมงค์', cf().includes('--stop') && !(await S()).urls.publicUrl);
  check('ลิงก์: สวิตช์ยังเป็นค่าเดิมสำหรับรอบหน้า', (await S()).tunnel === true);
  await m.ev(`document.querySelector('#tunnel').click()`); await sleep(200);
  const quicks = cf().split('--quick').length;
  await m.ev(`document.querySelector('#power').click()`);
  await until(async () => (await S()).server === 'on', 15000);
  await sleep(800);
  check('ลิงก์: ปิดสวิตช์แล้วไม่เปิดอุโมงค์', cf().split('--quick').length === quicks);
  check('ลิงก์: แอปจำค่าที่ปิดไว้', JSON.parse(fs.readFileSync(path.join(TMP, 'profile', 'app-config.json'), 'utf8')).tunnel === false);
  check('ลิงก์: ไม่มี error', m.errors.length === 0, m.errors.join(' | ').slice(0, 200));
  await quitApp(proc, true);
}

async function foreignRun() {
  const blocker = http.createServer((_q, r) => r.end('x')).listen(PORT);
  await new Promise((r) => { blocker.on('listening', r); });
  const proc = launch(appEnv());
  const m = await pageOf((u) => u.endsWith('ui/index.html'));
  check('โปรแกรมอื่นใช้พอร์ต: แจ้งชื่อ และไม่ปิดให้', await until(async () => !!(await m.ev('S'))?.portBlockedBy, 15000) && blocker.listening, await m.ev('S.portBlockedBy'));
  check('โปรแกรมอื่นใช้พอร์ต: ปุ่มเปิดกดไม่ได้', await m.ev(`document.querySelector('#power').disabled`));
  await shot(m, '10-port-foreign');
  await new Promise((r) => { blocker.close(r); blocker.closeAllConnections?.(); });
  await m.ev(`document.querySelector('#retry').click()`);
  check('กดลองใหม่แล้วเปิดได้', await until(async () => (await m.ev('S')).server === 'off', 90000));
  await quitApp(proc, false);
}

// โค้ดรุ่นเก่าในโฟลเดอร์: ต้องไม่แตะเซิร์ฟเวอร์ที่รันอยู่ แม้จะเปิดให้ปิดตัวเก่าได้
async function oldCodeRun() {
  const oldDir = path.join(TMP, 'oldcode');
  fs.mkdirSync(oldDir);
  fs.writeFileSync(path.join(oldDir, 'server.py'), '# รุ่นเก่า\n');
  const stub = path.join(TMP, 'kara_old_stub.py');
  fs.writeFileSync(stub, `import http.server\nhttp.server.HTTPServer(('0.0.0.0',${PORT}),http.server.SimpleHTTPRequestHandler).serve_forever()\n`);
  const old = spawn(PY, ['-u', stub], { cwd: TMP, stdio: 'ignore' });
  await until(() => pyPid() === old.pid, 8000);
  const proc = launch(appEnv({ KARA_APP_PROJECT: oldDir, KARA_APP_NO_KILL: '', KARA_APP_OLD_SERVER: 'kara_old_stub\\.py' }));
  const m = await pageOf((u) => u.endsWith('ui/index.html'));
  check('โค้ดรุ่นเก่า: แจ้งเตือนและไม่เปิด Python', await until(async () => (await m.ev('S'))?.projectError?.includes('รุ่นเก่า'), 15000));
  await sleep(1500);
  check('โค้ดรุ่นเก่า: เซิร์ฟเวอร์ที่รันอยู่ไม่ถูกปิด', old.exitCode === null && old.signalCode === null && pyPid() === old.pid);
  await shot(m, '11-old-code');
  proc.kill('SIGTERM');
  await until(() => proc.exitCode !== null || proc.signalCode !== null, 10000);
  old.kill('SIGTERM');
  await until(() => pyPid() === 0, 5000);
  await until(async () => { try { await fetch(`http://127.0.0.1:${CDP}/json`); return false; } catch { return true; } }, 8000);
}

async function oldServerRun() {
  const stub = path.join(TMP, 'kara_old_stub.py');
  fs.writeFileSync(stub, `import http.server,socketserver\nsocketserver.TCPServer.allow_reuse_address=True\nhttp.server.HTTPServer(('0.0.0.0',${PORT}),http.server.SimpleHTTPRequestHandler).serve_forever()\n`);
  const old = spawn(PY, ['-u', stub], { cwd: TMP, stdio: 'ignore' });
  await until(() => pyPid() === old.pid, 8000);
  const proc = launch(appEnv({ KARA_APP_NO_KILL: '', KARA_APP_OLD_SERVER: 'kara_old_stub\\.py' }));
  const m = await pageOf((u) => u.endsWith('ui/index.html'));
  check('พบตัวเก่า: ปิดให้เอง แล้วเปิดของแอปแทน', await until(async () => (await m.ev('S'))?.server === 'off', 90000) && old.exitCode !== null || old.signalCode !== null);
  check('พบตัวเก่า: แจ้งให้รู้', (await m.ev('S')).notice?.title.includes('ตัวเก่า'));
  await quitApp(proc, false);
}

try {
  makeFixtures();
  const which = process.env.TEST_ONLY;
  if (!which || which === 'main') await mainRun();
  if (!which || which === 'tunnel') await tunnelRun();
  if (!which || which === 'foreign') await foreignRun();
  if (!which || which === 'oldcode') await oldCodeRun();
  if (!which || which === 'old') await oldServerRun();
} catch (e) {
  console.log(`ไม่ผ่าน  ทดสอบหยุดกลางคัน: ${e.message}`);
  console.log(fs.existsSync(path.join(TMP, 'app.log')) ? fs.readFileSync(path.join(TMP, 'app.log'), 'utf8').slice(-1500) : '');
  fails += 1;
} finally {
  execFileSync('/bin/bash', ['-c', `pkill -f 'user-data-dir=${path.join(TMP, 'profile')}' ; true`]);
  await sleep(7000);                 // Python ต้องปิดตามเองแม้แอปถูกฆ่า
  check('ไม่เหลือ Python ค้างที่พอร์ตทดสอบ', pyPid() === 0);
  for (const n of fs.readdirSync(path.join(ROOT, 'songs', 'yt'))) if (n.includes(VID)) fs.rmSync(path.join(ROOT, 'songs', 'yt', n), { recursive: true, force: true });
  execFileSync('git', ['-C', ROOT, 'checkout', 'tv.json']);
  console.log(`ภาพ: ${SHOTS}`);
  console.log(`สรุป: ไม่ผ่าน ${fails}`);
  process.exit(fails ? 1 : 0);
}
