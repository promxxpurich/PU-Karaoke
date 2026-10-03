// eval_display.js — วัดว่า "ซับขึ้นทันไหม" ด้วยตรรกะจอจริง (บล็อก lyrcore ใน static/player.html)
// stdin: {"songs": [{"id", "lines": [{t,d,x}], "truth": [t ของบรรทัดเดียวกันตามที่ร้องจริง]}]}
// stdout: {"new": {...}, "old": {...}} ต่อเพลงและรวม
//   seen  = บรรทัดอยู่บนจอแล้ว (แถวไหนก็ได้) ตั้งแต่ 0.5 วิก่อนร้อง -> คนร้องอ่านทัน
//   lit   = บรรทัดสว่างภายใน 0.5 วิรอบเวลาที่ร้องจริง
//   evict = บรรทัดหายจากจอก่อนร้องไปอย่างน้อย min(1, d) วิ
// "old" = ตรรกะจอก่อนมี lyrcore (คัดลอกไว้ข้างล่างเป็นไม้บรรทัด)
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'static', 'player.html'), 'utf8');
const core = html.slice(html.indexOf('// <lyrcore>'), html.indexOf('// </lyrcore>'));
// eslint-disable-next-line no-eval
eval(core.replace(/^const /gm, 'var '));

function oldFrame(L, t){
  const LEAD = 0.25, HOLD = 2.0, GAPS = 6.0;
  let lo = 0, hi = L.length - 1, i = -1;
  while(lo <= hi){ const m = (lo + hi) >> 1; if(L[m].t - LEAD <= t){ i = m; lo = m + 1; } else hi = m - 1; }
  let gap = false;
  if(i >= 0){ const l = L[i], nx = L[i + 1]; if(t > l.t + l.d + HOLD && (!nx || nx.t - LEAD - t > GAPS)) gap = true; }
  const held = i > 0 && t < L[i - 1].t + L[i - 1].d;
  const par = j => ((j % 2) + 2) % 2;
  const rows = [{j: -2, on: false}, {j: -2, on: false}];
  if(i < 0){ rows[0] = {j: 0, on: false}; rows[1] = {j: -1, on: false}; }
  else { rows[par(i)] = gap ? {j: -1, on: false} : {j: i, on: true};
    const o = held ? i - 1 : i + 1; rows[par(o)] = {j: o < L.length ? o : -2, on: held}; }
  return {i, gap, rows};
}

function measure(lines, truth, frameOf){
  const n = lines.length, r = {n, seen: 0, lit: 0, evict: 0};
  for(let k = 0; k < n; k++){
    const T = truth[k];
    if(T == null) { r.n--; continue; }
    const F1 = frameOf(T - 0.5);
    if(F1.rows.some(x => x.j === k)) r.seen++;
    let lit = false;
    for(let dt = -0.5; dt <= 0.5; dt += 0.1){ const F = frameOf(T + dt); if(F.rows.some(x => x.j === k && x.on)){ lit = true; break; } }
    if(lit) r.lit++;
    // ร้องจริงนานเท่าไร: d แต่ไม่เกินบรรทัดถัดไป (d ของไฟล์เก่าถูกบังคับ ≥ 1 วิ)
    const nx = lines[k + 1], dEff = Math.min(+lines[k].d || 1, nx ? Math.max(0.1, nx.t - lines[k].t) : 99);
    const hold = Math.min(1, dEff);
    let gone = false;
    for(let dt = 0; dt < hold - 0.05; dt += 0.1){ const F = frameOf(T + dt); if(!F.rows.some(x => x.j === k)){ gone = true; break; } }
    if(gone) r.evict++;
  }
  return r;
}

const req = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = {new: {n: 0, seen: 0, lit: 0, evict: 0}, old: {n: 0, seen: 0, lit: 0, evict: 0}, songs: []};
for(const s of req.songs){
  const L0 = s.lines.map((l, i) => ({t: +l.t, d: +l.d, x: l.x, v: l.v, i})).sort((a, b) => a.t - b.t);
  const truth = L0.map(l => s.truth[l.i]);
  const Ln = lycPrep(L0.map(l => ({...l})));
  const a = measure(L0, truth, t => lycFrame(Ln, t, {}));
  const b = measure(L0, truth, t => oldFrame(L0, t));
  for(const k of ['n', 'seen', 'lit', 'evict']){ out.new[k] += a[k]; out.old[k] += b[k]; }
  out.songs.push({id: s.id, new: a, old: b});
}
process.stdout.write(JSON.stringify(out));
