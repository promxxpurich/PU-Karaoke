#!/usr/bin/env node
// ตรวจบท mv.json ก่อนใช้จริง (ไม่ต้องเปิดเบราว์เซอร์):
//   node scripts/mv_check.js <โฟลเดอร์เพลง>      (อ่าน mv.json + lyrics.json ในโฟลเดอร์นั้น)
// ตรวจ: JSON ถูกต้อง / ฉากมีจริง / เลขบรรทัดอยู่ในช่วง ไม่ทับกัน / รูปที่อ้างมีไฟล์ / regex คำใช้ได้และเจอในบรรทัด
//       / พารามิเตอร์ที่ฉากไม่รู้จัก / ฉากเดียวกันติดกันเกิน 3 บรรทัด
// พิมพ์ JSON {ok, errors[], warnings[], coverage} — exit 1 ถ้ามี error
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const dir = process.argv[2];
if(!dir){ console.error('ใช้: mv_check.js <โฟลเดอร์เพลง>'); process.exit(2); }
const errors = [], warnings = [];
const read = f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
let mv, ly;
try{ mv = read('mv.json'); }catch(e){ console.log(JSON.stringify({ ok: false, errors: ['อ่าน mv.json ไม่ได้: ' + e.message] })); process.exit(1); }
try{ ly = read('lyrics.json'); }catch(e){ console.log(JSON.stringify({ ok: false, errors: ['อ่าน lyrics.json ไม่ได้'] })); process.exit(1); }
const REG = JSON.parse(execFileSync('node', [path.join(__dirname, 'mv_catalog.js'), '--json'], { encoding: 'utf8' }));
const lines = ly.lines || [], N = lines.length, lib = path.join(__dirname, '..', 'static', 'mv');
const COMMON = new Set(['acc', 'pal', 'on', 'bg', 'fg']);

// รูป
const imgs = mv.images || {};
for(const [k, v] of Object.entries(imgs)){
  const src = typeof v === 'string' ? v : v && v.src;
  if(!src){ errors.push(`images.${k}: ไม่มี src`); continue; }
  const f = src.startsWith('lib/') ? path.join(lib, src) : path.join(dir, src);
  if(!/^https?:/.test(src) && !fs.existsSync(f)) errors.push(`images.${k}: ไม่มีไฟล์ ${src}`);
}
const IMG_KEYS = ['img', 'avatar', 'pip', 'bg'];
function checkEntry(e, where){
  const def = REG[e.scene];
  if(!def){ errors.push(`${where}: ไม่มีฉากชื่อ "${e.scene}"`); return; }
  const p = e.p || {};
  for(const k of Object.keys(p)) if(!(k in def.params) && !COMMON.has(k)) warnings.push(`${where} (${e.scene}): ไม่รู้จักพารามิเตอร์ "${k}"`);
  for(const k of IMG_KEYS) if(typeof p[k] === 'string' && /รูป/.test(def.params[k] || '') && !imgs[p[k]]) errors.push(`${where}: รูป "${p[k]}" ไม่มีใน images`);
  if(Array.isArray(p.imgs)) for(const k of p.imgs) if(!imgs[k]) errors.push(`${where}: รูป "${k}" ไม่มีใน images`);
  if('img' in def.params && !/ไม่ใส่/.test(def.params.img) && !p.img && !p.imgs)
    warnings.push(`${where} (${e.scene}): ไม่ได้ระบุ img (จะสุ่มรูปให้)`);
  return p;
}
for(const [k, e] of [['intro', mv.intro], ['outro', mv.outro]]) if(e) checkEntry(e, k);
for(const [k, e] of Object.entries(mv.gaps || {})) checkEntry(e, 'gaps.' + k);

const used = new Array(N).fill(null);
(mv.lines || []).forEach((e, n) => {
  const ii = Array.isArray(e.i) ? e.i : [e.i, e.i], where = `lines[${n}] i=${JSON.stringify(e.i)}`;
  if(!Number.isInteger(ii[0]) || !Number.isInteger(ii[1]) || ii[0] < 0 || ii[1] >= N || ii[1] < ii[0]){ errors.push(`${where}: เลขบรรทัดผิด (มี 0–${N - 1})`); return; }
  for(let k = ii[0]; k <= ii[1]; k++){ if(used[k]) errors.push(`${where}: บรรทัด ${k} ซ้ำกับ ${used[k]}`); used[k] = where; }
  const p = checkEntry(e, where); if(!p) return;
  for(const key of ['word', 'until']) if(p[key]){
    let rx; try{ rx = new RegExp(p[key], 'i'); }catch(err){ errors.push(`${where}: regex ${key} ใช้ไม่ได้ "${p[key]}"`); continue; }
    const target = key === 'word' && e.scene === 'ecg' ? lines[ii[1]].x : lines[ii[0]].x;
    if(!rx.test(target)) warnings.push(`${where}: ${key} "${p[key]}" ไม่เจอในบรรทัด "${target}"`);
  }
});
const missing = used.map((u, k) => u ? null : k).filter(k => k != null);
if(missing.length) warnings.push(`บรรทัดที่ไม่มีบท (จะใช้ kinetic): ${missing.join(', ')}`);
// ฉากเดิมติดกัน
let run = 1;
const seq = (mv.lines || []).slice().sort((a, b) => (Array.isArray(a.i) ? a.i[0] : a.i) - (Array.isArray(b.i) ? b.i[0] : b.i));
for(let k = 1; k < seq.length; k++){ run = seq[k].scene === seq[k - 1].scene ? run + 1 : 1;
  if(run === 4 && seq[k].scene !== 'camcorder') warnings.push(`ฉาก ${seq[k].scene} ติดกันเกิน 3 ช่วง (ถึงบรรทัด ${JSON.stringify(seq[k].i)})`); }
const scenesUsed = new Set(seq.map(e => e.scene));
console.log(JSON.stringify({ ok: !errors.length, errors, warnings, coverage: `${N - missing.length}/${N}`, scenes: scenesUsed.size }, null, 1));
process.exit(errors.length ? 1 : 0);
