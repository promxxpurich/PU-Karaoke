// โปรเซสหลักของแอป Purich Karaoke: คุม Python, จอทีวี, ลิงก์นอกบ้าน และกันเครื่องหลับ
// เปิดแอป = Python โหมดเฉพาะเครื่องนี้ · กดเปิด = ปล่อยเครื่องอื่นเข้าในโปรเซสเดิม · กดปิด = รีสตาร์ทกลับโหมดเฉพาะเครื่อง (ล้างงานหนัก)
const { app, BrowserWindow, Menu, dialog, ipcMain, powerSaveBlocker, screen, shell } = require('electron');
const { execFile, spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const APP_NAME = 'Purich Karaoke';
app.setName(APP_NAME);
// จอทีวีต้องเล่นเสียงเองได้โดยไม่ต้องแตะจอ เหมือน player.command เดิม
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

// env สำหรับทดสอบบนคลังปลอม: ห้ามยุ่งพอร์ต 8080 และโฟลเดอร์จริง
const ENV = process.env;
const PORT = Number(ENV.KARA_APP_PORT) || 8080;
const BASE = `http://localhost:${PORT}`;
const NO_KILL = ENV.KARA_APP_NO_KILL === '1';
const OLD_SERVER_RE = new RegExp(`^\\S*[Pp]ython\\S*( |$).*${ENV.KARA_APP_OLD_SERVER || 'server\\.py'}`);
const TEST_ANSWERS = ENV.KARA_APP_TEST_ANSWERS?.split(',').map(Number) ?? null;
const TOKEN = crypto.randomBytes(24).toString('hex');
const SYS_PATH = `/opt/homebrew/bin:/usr/local/bin:${ENV.PATH || '/usr/bin:/bin'}`;

const MAX_AUTO_RESTART = 2;
const CRASH_RESET_MS = 10 * 60 * 1000;  // อยู่ได้นานเท่านี้ = ล่มครั้งถัดไปนับใหม่
const READY_TIMEOUT_MS = 120 * 1000;
const STOP_TIMEOUT_MS = 6000;
const LOG_LINES = 400;

const state = {
  server: 'boot',         // boot | off | starting | on | stopping | restarting | crashed
  ready: false,           // Python ตอบแล้ว หน้า Studio เปิดได้
  bootText: 'กำลังเตรียมระบบ…',
  portBlockedBy: null,    // ชื่อโปรแกรมอื่นที่ใช้พอร์ต
  projectError: null,
  project: '',
  crashes: 0,
  tunnel: false,
  tunnelBusy: false,
  displayId: 'auto',
  urls: { remoteUrl: '', tvUrl: '', publicUrl: '' },
  notice: null,           // { kind: info|ok|bad, title, text, log?: bool }
};

let mainWin = null;
let tvWin = null;
let py = null;            // { proc, stopping, startedAt }
let wantServing = false;
let sleepBlock = null;
let quitting = false;
let askingQuit = false;
const logLines = [];

/* ===== ค่าแอป ===== */
const configPath = () => path.join(app.getPath('userData'), 'app-config.json');
function readConfig() {
  try { return JSON.parse(fs.readFileSync(configPath(), 'utf8')); } catch { return {}; }
}
function writeConfig(patch) {
  fs.writeFileSync(configPath(), JSON.stringify({ ...readConfig(), ...patch }, null, 1));
}
// ลิงก์นอกบ้านเปิดพร้อมเซิร์ฟเวอร์เป็นค่าเริ่มต้น ปิดสวิตช์แล้วแอปจำไว้
const tunnelPref = () => readConfig().tunnel ?? true;
const logPath = () => path.join(app.getPath('logs'), 'server.log');
const pythonPath = () => ENV.KARA_APP_PYTHON || path.join(state.project, '.venv', 'bin', 'python');
const studioFile = () => path.join(state.project, '.studio.json');
const cloudflareCmd = () => ENV.KARA_APP_CLOUDFLARE || path.join(state.project, 'cloudflare.command');

function addLog(chunk) {
  const text = chunk.toString();
  try { fs.appendFileSync(logPath(), text); } catch { /* เขียน log ไม่ได้ก็ยังแสดงในแอป */ }
  logLines.push(...text.split('\n').filter(Boolean));
  logLines.splice(0, Math.max(0, logLines.length - LOG_LINES));
}

/* ===== สถานะส่งให้หน้าแอป ===== */
function displays() {
  const primary = screen.getPrimaryDisplay().id;
  return screen.getAllDisplays().map((d, i) => ({
    id: String(d.id), label: d.label || `จอ ${i + 1}`, size: `${d.size.width}×${d.size.height}`,
    internal: !!d.internal, primary: d.id === primary,
  }));
}
function targetDisplay() {
  const all = screen.getAllDisplays();
  return all.find((d) => String(d.id) === state.displayId) ?? all.find((d) => !d.internal) ?? screen.getPrimaryDisplay();
}
function snapshot() {
  return {
    ...state, base: BASE, port: PORT, displays: displays(), targetDisplayId: String(targetDisplay().id),
    tv: { open: !!tvWin, fullscreen: !!tvWin && tvWin.isFullScreen() }, sleepBlocked: sleepBlock !== null,
  };
}
function broadcast() {
  if (mainWin && !mainWin.isDestroyed()) mainWin.webContents.send('state', snapshot());
  buildMenu();
}
function notify(kind, title, text, extra = {}) {
  state.notice = { kind, title, text, ...extra };
}
async function ask(opts) {
  if (TEST_ANSWERS) {
    const response = TEST_ANSWERS.shift() ?? 0;
    console.log(`[กล่องยืนยัน] ${opts.message} → ${opts.buttons[response]}`);
    return response;
  }
  mainWin?.show();
  const { response } = await dialog.showMessageBox(mainWin, { type: 'warning', cancelId: 1, defaultId: 1, ...opts });
  return response;
}
const run = (file, args, opt = {}) => new Promise((resolve) => {
  execFile(file, args, { env: { ...ENV, PATH: SYS_PATH }, ...opt }, (err, stdout, stderr) => resolve({ err, stdout: String(stdout), stderr: String(stderr) }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ===== คุย API ของเซิร์ฟเวอร์ ===== */
async function appApi(pathname, method = 'GET') {
  const r = await fetch(BASE + pathname, { method, headers: { 'x-kara-app': TOKEN }, signal: AbortSignal.timeout(4000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
async function refreshUrls() {
  try {
    const s = await appApi('/api/app/state');
    state.urls = { remoteUrl: s.remoteUrl, tvUrl: s.tvUrl, publicUrl: s.publicUrl };
    return s;
  } catch { return null; }
}

/* ===== พอร์ตไม่ว่าง ===== */
// ระบุตัวด้วยวิธีเดียวกับ stop.command: ตัวที่ฟังพอร์ต + binary เป็น python + มี server.py เป็นอาร์กิวเมนต์
async function portOwners() {
  const { stdout } = await run('/usr/sbin/lsof', ['-nP', `-iTCP:${PORT}`, '-sTCP:LISTEN', '-t']);
  const out = [];
  for (const pid of stdout.split('\n').filter(Boolean)) {
    const { stdout: cmd } = await run('/bin/ps', ['-p', pid, '-o', 'command=']);
    out.push({ pid: Number(pid), command: cmd.trim(), ours: OLD_SERVER_RE.test(cmd.trim()) });
  }
  return out;
}
async function closeOldServer(owners) {
  await run('/usr/bin/pkill', ['-f', `user-data-dir=${path.join(state.project, '.chrome-player')}`]);
  await run(cloudflareCmd(), ['--stop'], { cwd: state.project, timeout: 15000 });
  await sleep(600);
  for (const o of owners) { try { process.kill(o.pid, 'SIGTERM'); } catch { /* ปิดไปแล้ว */ } }
  for (let i = 0; i < 40 && (await portOwners()).length; i++) await sleep(250);
  for (const o of await portOwners()) if (o.ours) { try { process.kill(o.pid, 'SIGKILL'); } catch { /* ปิดไปแล้ว */ } }
  if (PORT !== 8080) return;     // พอร์ตทดสอบ: ห้ามกวาดงานหนักของเซิร์ฟเวอร์จริงที่รันอยู่
  await run('/usr/bin/pkill', ['-f', '[-]m demucs']);
  await run('/usr/bin/pkill', ['-f', '[g]en_lyrics[.]py|[v]erify_lyrics[.]py|[f]a_align[.]py']);
}
const owns = (o) => py && o.pid === py.proc.pid;

/* ===== Python ===== */
function spawnPython() {
  const proc = spawn(pythonPath(), ['-u', 'server.py'], {
    cwd: state.project,
    env: { ...ENV, PATH: SYS_PATH, KARA_APP_MODE: '1', KARA_APP_TOKEN: TOKEN, KARA_PORT: String(PORT) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const me = { proc, stopping: false, startedAt: Date.now() };
  py = me;
  proc.stdout.on('data', addLog);
  proc.stderr.on('data', addLog);
  proc.on('error', (e) => addLog(`เปิด Python ไม่ได้: ${e.message}\n`));
  proc.on('exit', (code, sig) => {
    addLog(`[แอป] Python จบการทำงาน code=${code} signal=${sig}\n`);
    if (py === me) py = null;
    if (!me.stopping && !quitting) onCrash(me);
  });
  return me;
}
async function waitReady(me) {
  const end = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < end) {
    if (py !== me || me.proc.exitCode !== null) return false;
    if (await refreshUrls()) return true;
    await sleep(300);
  }
  return false;
}
async function stopPython() {
  const me = py;
  if (!me) return;
  me.stopping = true;
  py = null;
  state.ready = false;
  if (me.proc.exitCode !== null) return;
  const exited = new Promise((r) => me.proc.once('exit', r));
  me.proc.kill('SIGTERM');
  if (await Promise.race([exited.then(() => true), sleep(STOP_TIMEOUT_MS).then(() => false)])) return;
  me.proc.kill('SIGKILL');
  await exited;
}
// เปิด Python แล้วรอจนพร้อม ถ้า wantServing อยู่ก็ปล่อยเครื่องอื่นเข้าต่อให้เลย
async function bringUp() {
  const me = spawnPython();
  if (!(await waitReady(me))) {
    if (py === me) {
      me.stopping = true;
      me.proc.kill('SIGKILL');
      py = null;
      onCrash(me);
    }
    return false;
  }
  state.ready = true;
  if (wantServing) {
    try {
      await appApi('/api/app/serve', 'POST');
    } catch (e) {
      addLog(`[แอป] เปิดรับเครื่องอื่นไม่สำเร็จ: ${e.message}\n`);
      return false;
    }
    await refreshUrls();
  }
  return true;
}

async function boot() {
  state.server = 'boot';
  state.ready = false;
  state.bootText = 'กำลังเตรียมระบบ…';
  state.portBlockedBy = null;
  state.projectError = null;
  state.notice = null;
  broadcast();
  if (!fs.existsSync(path.join(state.project, 'server.py'))) {
    state.projectError = `ไม่พบโปรแกรมในโฟลเดอร์ ${state.project}`;
    broadcast();
    return;
  }
  if (!fs.existsSync(pythonPath())) {
    state.projectError = `ไม่พบ Python ของโปรเจกต์ (.venv) ในโฟลเดอร์ ${state.project}`;
    broadcast();
    return;
  }
  // โค้ดในโฟลเดอร์ยังไม่รองรับแอป: ต้องหยุดก่อนแตะเซิร์ฟเวอร์ที่รันอยู่ ไม่งั้นปิดตัวเก่าแล้วเปิดตัวใหม่ไม่ขึ้น
  if (!fs.existsSync(path.join(state.project, 'static', 'tvset', 'index.html'))) {
    state.projectError = 'โค้ดในโฟลเดอร์นี้ยังเป็นรุ่นเก่า ยังใช้กับแอปไม่ได้ เซิร์ฟเวอร์ที่รันอยู่ไม่ถูกแตะ';
    broadcast();
    return;
  }
  const owners = (await portOwners()).filter((o) => !owns(o));
  const foreign = owners.find((o) => !o.ours);
  if (foreign || (owners.length && NO_KILL)) {
    const who = foreign ?? owners[0];
    state.portBlockedBy = who.command.split(/\s+/)[0].split('/').pop() || `PID ${who.pid}`;
    broadcast();
    return;
  }
  if (owners.length) {
    state.bootText = 'พบเซิร์ฟเวอร์ตัวเก่า กำลังปิดให้…';
    broadcast();
    await closeOldServer(owners);
    if ((await portOwners()).length) {
      state.portBlockedBy = 'เซิร์ฟเวอร์ตัวเก่าที่ปิดไม่ได้';
      broadcast();
      return;
    }
    notify('info', 'ปิดเซิร์ฟเวอร์ตัวเก่าแล้ว', 'เปิดอยู่ก่อนเปิดแอป ตอนนี้แอปเป็นตัวคุมแทน');
  }
  wantServing = false;
  if (await bringUp()) {
    state.server = 'off';
    broadcast();
  }
}

function onCrash(me) {
  if (Date.now() - me.startedAt > CRASH_RESET_MS) state.crashes = 0;
  state.crashes += 1;
  state.ready = false;
  if (state.crashes <= MAX_AUTO_RESTART) {
    const prev = wantServing ? 'on' : 'off';
    // Python ตัวใหม่ล้างลิงก์ทดลองในไฟล์ตอนเริ่ม แต่อุโมงค์ยังรันอยู่ จึงต้องเขียนกลับ ไม่งั้น QR เปลี่ยนเป็นลิงก์ในบ้าน
    const liveLink = state.urls.publicUrl;
    state.server = 'restarting';
    notify('bad', 'เซิร์ฟเวอร์ล่ม', `กำลังเปิดใหม่อัตโนมัติ (ครั้งที่ ${state.crashes}/${MAX_AUTO_RESTART})`);
    broadcast();
    bringUp().then((ok) => {
      if (!ok) return;
      if (liveLink) {
        writeStudio({ publicUrl: liveLink });
        state.urls.publicUrl = liveLink;
      }
      state.server = prev;
      notify('ok', 'เซิร์ฟเวอร์กลับมาแล้ว', prev === 'on' ? 'เพลงที่เล่นอยู่อาจสะดุด จอทีวีต่อกลับเอง' : 'ใช้งานต่อได้');
      broadcast();
    });
    return;
  }
  state.server = 'crashed';
  wantServing = false;
  setSleepBlock(false);
  closeTv();
  stopTunnel();
  notify('bad', 'เซิร์ฟเวอร์ล่มซ้ำ แอปหยุดเปิดใหม่แล้ว', `ลองเปิดอัตโนมัติครบ ${MAX_AUTO_RESTART} ครั้ง กันเครื่องร้อนจากการเปิดวนซ้ำ`, { log: true });
  broadcast();
}

/* ===== เปิด / ปิดเซิร์ฟเวอร์ ===== */
function setSleepBlock(on) {
  if (on && sleepBlock === null) sleepBlock = powerSaveBlocker.start('prevent-display-sleep');
  if (!on && sleepBlock !== null) { powerSaveBlocker.stop(sleepBlock); sleepBlock = null; }
}
async function startServer() {
  if (!['off', 'crashed'].includes(state.server)) return;
  const fromCrash = state.server === 'crashed';
  state.server = 'starting';
  state.notice = null;
  state.crashes = 0;
  wantServing = true;
  broadcast();
  let ok;
  if (fromCrash || !py) {
    ok = await bringUp();
  } else {
    try {
      await appApi('/api/app/serve', 'POST');
      await refreshUrls();
      ok = true;
    } catch (e) {
      addLog(`[แอป] เปิดรับเครื่องอื่นไม่สำเร็จ: ${e.message}\n`);
      ok = false;
    }
  }
  if (!ok) {
    if (state.server === 'starting') {
      wantServing = false;
      state.server = py ? 'off' : 'crashed';
      notify('bad', 'เปิดเซิร์ฟเวอร์ไม่สำเร็จ', 'กดเปิดอีกครั้ง หรือดูบันทึกเพื่อหาสาเหตุ', { log: true });
      broadcast();
    }
    return;
  }
  state.server = 'on';
  setSleepBlock(true);
  openTv();                     // เจ้าของเลือก: เปิดจอทีวีอัตโนมัติทุกครั้ง
  if (state.tunnel) startTunnel();
  broadcast();
}
async function stopServer() {
  if (state.server !== 'on') return;
  const s = await refreshUrls();
  if (s?.playing) {
    const r = await ask({
      message: 'กำลังมีเพลงเล่นอยู่ จะปิดเซิร์ฟเวอร์เลยไหม?',
      detail: 'เพลงจะหยุดทันที จอทีวีจะปิด และมือถือแขกจะหลุดการเชื่อมต่อ Studio ยังใช้ต่อได้',
      buttons: ['ปิดเซิร์ฟเวอร์', 'ยกเลิก'],
    });
    if (r !== 0 || state.server !== 'on') return;
  }
  state.server = 'stopping';
  wantServing = false;
  state.notice = null;
  setSleepBlock(false);
  closeTv();
  broadcast();
  await stopTunnel();
  state.tunnel = tunnelPref();
  await stopPython();
  if (await bringUp()) {
    state.server = 'off';
    notify('info', 'กลับสู่โหมดเฉพาะเครื่องนี้แล้ว', 'เครื่องอื่นเข้าไม่ได้แล้ว และงานอัตโนมัติหยุดอยู่');
    broadcast();
  }
}

/* ===== ลิงก์นอกบ้าน (ใช้ cloudflare.command เดิม) ===== */
async function startTunnel() {
  state.tunnelBusy = true;
  broadcast();
  const { err, stdout, stderr } = await run(cloudflareCmd(), ['--quick'], { cwd: state.project, timeout: 180000 });
  state.tunnelBusy = false;
  addLog(stdout + stderr);
  if (err) {
    state.tunnel = false;
    notify('bad', 'เปิดลิงก์นอกบ้านไม่ได้', 'ในบ้านยังเข้าผ่าน Wi-Fi ได้ตามปกติ ดูบันทึกเพื่อหาสาเหตุ', { log: true });
  } else if (state.server !== 'on' || !state.tunnel) {
    // ระหว่างรอลิงก์ ผู้ใช้ปิดเซิร์ฟเวอร์หรือปิดสวิตช์ไปแล้ว: อย่าปล่อยอุโมงค์ค้าง
    await run(cloudflareCmd(), ['--stop'], { cwd: state.project, timeout: 15000 });
  } else {
    // จอทีวีโหลด QR ใหม่เมื่อได้รับสถานะ จึงต้องสั่ง broadcast ด้วยการบันทึกค่าเดิม
    await studioApi('/api/studio/tv', {}).catch((e) => addLog(`[แอป] แจ้งจอทีวีเรื่องลิงก์ไม่สำเร็จ: ${e.message}\n`));
  }
  await refreshUrls();
  broadcast();
}
async function stopTunnel() {
  state.tunnelBusy = false;
  const { stdout, stderr } = await run(cloudflareCmd(), ['--stop'], { cwd: state.project, timeout: 15000 });
  addLog(stdout + stderr);
  await refreshUrls();
}

/* ===== จอทีวี (หน้าต่างแยก เต็มจอปกติของ macOS) ===== */
function openTv() {
  if (tvWin) { tvWin.show(); return; }
  const { x, y, width, height } = targetDisplay().bounds;
  tvWin = new BrowserWindow({
    x: x + 40, y: y + 40, width: Math.min(width - 80, 1280), height: Math.min(height - 80, 720),
    title: `จอทีวี — ${APP_NAME}`, backgroundColor: '#000000', fullscreenable: true,
    // จออยู่คนละ Space กับแอปบน MacBook จอเดียว ถ้าถูกชะลอ เนื้อเพลงจะไม่ขยับ
    webPreferences: { sandbox: true, contextIsolation: true, backgroundThrottling: false },
  });
  lockWindow(tvWin);
  tvWin.loadURL(`${BASE}/`);
  tvWin.webContents.on('before-input-event', (_e, input) => {
    if (input.type === 'keyDown' && input.key === 'Escape' && tvWin?.isFullScreen()) tvWin.setFullScreen(false);
  });
  tvWin.once('ready-to-show', () => tvWin?.setFullScreen(true));
  for (const ev of ['enter-full-screen', 'leave-full-screen']) tvWin.on(ev, broadcast);
  tvWin.on('closed', () => { tvWin = null; broadcast(); });
}
function closeTv() {
  if (tvWin) tvWin.close();
}
// ย้ายจอ: ต้องออกจากเต็มจอก่อน macOS จึงยอมย้ายหน้าต่างข้ามจอ
function moveTv() {
  if (!tvWin) return;
  const place = () => {
    if (!tvWin) return;
    const { x, y } = targetDisplay().bounds;
    tvWin.setPosition(x + 40, y + 40);
    tvWin.setFullScreen(true);
  };
  if (tvWin.isFullScreen()) {
    tvWin.once('leave-full-screen', () => setTimeout(place, 250));
    tvWin.setFullScreen(false);
  } else {
    place();
  }
}

/* ===== ค่าระบบ ===== */
function readStudio() {
  try { return JSON.parse(fs.readFileSync(studioFile(), 'utf8')); } catch { return {}; }
}
// เขียนแบบสลับไฟล์ รักษาฟิลด์อื่น เซิร์ฟเวอร์อ่านใหม่เองตาม mtime
function writeStudio(patch) {
  const tmp = `${studioFile()}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify({ ...readStudio(), ...patch }, null, 1));
  fs.renameSync(tmp, studioFile());
}
async function studioApi(pathname, body) {
  const r = await fetch(BASE + pathname, {
    method: body ? 'POST' : 'GET', body: body && JSON.stringify(body), signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
function showLog() {
  const detail = logLines.slice(-40).join('\n') || 'ยังไม่มีบันทึก';
  if (TEST_ANSWERS) { console.log(`[บันทึก] ${logLines.length} บรรทัด`); return; }
  dialog.showMessageBox(mainWin, { type: 'info', message: 'บันทึกเซิร์ฟเวอร์ล่าสุด', detail, buttons: ['ปิด', 'เปิดไฟล์บันทึก'] })
    .then(({ response }) => { if (response === 1) shell.showItemInFolder(logPath()); });
}
async function chooseProject() {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWin, { title: 'เลือกโฟลเดอร์ Purich Karaoke', properties: ['openDirectory'], defaultPath: state.project });
  if (canceled || !filePaths[0] || filePaths[0] === state.project) return;
  if (state.server !== 'off' && !state.projectError && !state.portBlockedBy) {
    notify('info', 'ปิดเซิร์ฟเวอร์ก่อนเปลี่ยนโฟลเดอร์', 'กดปิดเซิร์ฟเวอร์แล้วลองอีกครั้ง');
    return;
  }
  state.project = filePaths[0];
  writeConfig({ project: state.project });
  await stopPython();
  boot();
}

/* ===== ออกจากแอป ===== */
async function requestQuit() {
  if (askingQuit || quitting) return;
  if (['starting', 'on', 'restarting'].includes(state.server)) {
    askingQuit = true;
    const r = await ask({
      message: 'เซิร์ฟเวอร์ยังเปิดอยู่ จะออกจากแอปไหม?',
      detail: 'แอปจะปิดเซิร์ฟเวอร์ จอทีวี และงานหนักทั้งหมดพร้อมกัน',
      buttons: ['ออกจากแอป', 'ยกเลิก'],
    });
    askingQuit = false;
    if (r !== 0) return;
  }
  quitting = true;
  setSleepBlock(false);
  closeTv();
  if (state.tunnel) await stopTunnel();
  await stopPython();
  app.quit();
}

/* ===== คำสั่งจากหน้าแอป (อนุญาตเฉพาะในตารางนี้) ===== */
const ACTIONS = {
  'server:start': startServer,
  'server:stop': stopServer,
  'server:retry': boot,
  'tv:open': () => { if (state.server === 'on') openTv(); },
  'tv:close': closeTv,
  'tv:show': () => tvWin?.show(),
  'tv:display': (id) => { state.displayId = String(id); moveTv(); },
  'tunnel:set': async (on) => {
    state.tunnel = !!on;
    writeConfig({ tunnel: state.tunnel });
    if (state.server !== 'on') return;
    if (on) startTunnel(); else await stopTunnel();
  },
  'notice:clear': () => { state.notice = null; },
  'log:show': showLog,
  'project:choose': chooseProject,
  'pin:get': () => String(readStudio().pin ?? ''),
  'pin:set': (pin) => {
    const v = String(pin).trim();
    if (!/^\d{4,8}$/.test(v)) throw new Error('PIN ต้องเป็นตัวเลข 4–8 หลัก');
    writeStudio({ pin: v });
  },
  'fa:get': async () => (await studioApi('/api/studio/settings')).fa,
  'fa:set': async (mode) => { await studioApi('/api/studio/settings', { faMode: mode }); },
  'link:open': (url) => { if (/^https?:\/\//.test(url)) shell.openExternal(url); },
};
ipcMain.handle('state:get', () => snapshot());
ipcMain.handle('state:do', async (_e, action, arg) => {
  const fn = Object.hasOwn(ACTIONS, action) ? ACTIONS[action] : null;
  if (!fn) throw new Error(`ไม่รู้จักคำสั่ง ${action}`);
  const out = await fn(arg);
  broadcast();
  return out;
});

/* ===== หน้าต่างหลัก + เมนู ===== */
function lockWindow(win) {
  // ลิงก์ที่จะเปิดหน้าต่างใหม่ เช่น YouTube ไปเปิดในเบราว์เซอร์ปกติ
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(`${BASE}/`)) e.preventDefault(); });
}
function createMain() {
  mainWin = new BrowserWindow({
    width: 1280, height: 840, minWidth: 980, minHeight: 640,
    title: APP_NAME, backgroundColor: '#fff6f1', show: false,
    titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 18, y: 19 },
    webPreferences: { preload: path.join(__dirname, 'preload.js'), sandbox: true, contextIsolation: true },
  });
  lockWindow(mainWin);
  mainWin.once('ready-to-show', () => mainWin?.show());
  mainWin.loadFile(path.join(__dirname, 'ui', 'index.html'));
  mainWin.on('close', (e) => {
    if (quitting) return;
    e.preventDefault();
    requestQuit();
  });
  mainWin.on('closed', () => { mainWin = null; });
}
function buildMenu() {
  const canStart = ['off', 'crashed'].includes(state.server);
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: APP_NAME, submenu: [
      { role: 'about', label: `เกี่ยวกับ ${APP_NAME}` }, { type: 'separator' },
      { role: 'hide', label: `ซ่อน ${APP_NAME}` }, { role: 'hideOthers', label: 'ซ่อนแอปอื่น' }, { type: 'separator' },
      { label: `ออกจาก ${APP_NAME}`, accelerator: 'Cmd+Q', click: requestQuit },
    ] },
    { label: 'แก้ไข', submenu: [
      { role: 'undo', label: 'เลิกทำ' }, { role: 'redo', label: 'ทำซ้ำ' }, { type: 'separator' },
      { role: 'cut', label: 'ตัด' }, { role: 'copy', label: 'คัดลอก' }, { role: 'paste', label: 'วาง' }, { role: 'selectAll', label: 'เลือกทั้งหมด' },
    ] },
    { label: 'เซิร์ฟเวอร์', submenu: [
      { label: 'เปิดเซิร์ฟเวอร์', enabled: canStart, accelerator: 'Cmd+Shift+S', click: startServer },
      { label: 'ปิดเซิร์ฟเวอร์', enabled: state.server === 'on', accelerator: 'Cmd+Shift+X', click: stopServer },
      { type: 'separator' }, { label: 'ดูบันทึก', click: showLog },
    ] },
    { label: 'หน้าต่าง', submenu: [
      { label: 'หน้าต่างหลัก', accelerator: 'Cmd+1', click: () => mainWin?.show() },
      { label: 'จอทีวี', accelerator: 'Cmd+2', enabled: !!tvWin, click: () => tvWin?.show() },
      { type: 'separator' }, { role: 'minimize', label: 'ย่อ' },
    ] },
  ]));
}

app.whenReady().then(() => {
  app.setAboutPanelOptions({ applicationName: APP_NAME, applicationVersion: app.getVersion() });
  app.dock?.setIcon(path.join(__dirname, 'assets', 'icon.png'));
  fs.mkdirSync(app.getPath('logs'), { recursive: true });
  state.project = ENV.KARA_APP_PROJECT || readConfig().project || path.join(os.homedir(), 'Documents', 'kara');
  state.tunnel = tunnelPref();
  buildMenu();
  createMain();
  for (const ev of ['display-added', 'display-removed', 'display-metrics-changed']) screen.on(ev, broadcast);
  app.on('activate', () => mainWin?.show());
  boot();
});
app.on('before-quit', (e) => {
  if (quitting) return;
  e.preventDefault();
  requestQuit();
});
