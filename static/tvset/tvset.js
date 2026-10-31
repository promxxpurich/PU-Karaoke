// หน้าตั้งค่าจอทีวีชุดเดียว ใช้ทั้งในแอป Mac และ Studio 📺: ปรับแล้วบันทึกเอง เห็นบนพรีวิวและจอทีวีทันที
const $ = (q, el = document) => el.querySelector(q);
const $$ = (q, el = document) => [...el.querySelectorAll(q)];
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const S = { cfg: {}, logoUrl: '', room: null };
const ui = { setQuery: '' };

// ค่าจอทีวีทั้งหมดจาก TV_SCHEMA ใน server.py: ชื่อ ชนิด และค่าเริ่มต้นตรงกับของจริง
const TV_GROUPS = [
  { title: 'แถบชื่อเพลง', fields: [
    { key: 'title', type: 'bool', def: true, label: 'แถบชื่อเพลงด้านบน' },
    { key: 'titleHide', type: 'int', def: 0, min: 0, max: 60, unit: 'วิ', label: 'ซ่อนแถบชื่อหลังเริ่มเพลง', hint: '0 = แสดงตลอด' },
    { key: 'singer', type: 'bool', def: true, label: 'ชิปชื่อคนร้อง' },
    { key: 'chips', type: 'chips', def: ['guide'], label: 'สถานะหลังชื่อเพลง',
      options: [['guide', 'ไกด์'], ['master', 'เสียงรวม'], ['music', 'ดนตรี'], ['key', 'คีย์'], ['lyrsrc', 'ที่มาเนื้อ'], ['next', 'เพลงถัดไป']] },
  ] },
  { title: 'เนื้อเพลงบนจอ', fields: [
    { key: 'lyrScale', type: 'int', def: 100, min: 60, max: 160, unit: '%', label: 'ขนาดซับ' },
    { key: 'lyrColor', type: 'color', def: '#ffffff', label: 'สีตัวอักษรซับ' },
    { key: 'lyrDim', type: 'int', def: 55, min: 15, max: 100, unit: '%', label: 'ความสว่างบรรทัดที่ยังไม่ถึง' },
    { key: 'karaColor', type: 'color', def: '#ff6fa6', label: 'สีส่วนที่ร้องไปแล้ว' },
    { key: 'karaSmooth', type: 'bool', def: true, label: 'ไล่สีนุ่มทีละตัวอักษร' },
    { key: 'lyrBg', type: 'int', def: 100, min: 0, max: 100, unit: '%', label: 'ความเข้มพื้นใต้ซับ' },
    { key: 'lyrShadow', type: 'select', def: 2, label: 'เงาตัวอักษร', options: [[0, 'ไม่มี'], [1, 'บาง'], [2, 'ปกติ'], [3, 'ขอบหนา']] },
    { key: 'lyrLift', type: 'int', def: 0, min: 0, max: 20, unit: 'vh', label: 'ยกซับขึ้นจากขอบล่าง' },
    { key: 'countdown', type: 'bool', def: true, label: 'นับถอยหลัง ♪ ● ● ● ก่อนเข้าท่อนร้อง' },
    { key: 'voices', type: 'bool', def: true, label: 'แยกสีเสียงร้องคนที่ 2 และ 3' },
  ] },
  { title: 'องค์ประกอบบนจอ', fields: [
    { key: 'qr', type: 'bool', def: true, label: 'QR มุมขวาล่างตอนเล่นเพลง', hint: 'QR กลางจอตอนไม่มีเพลงขึ้นเสมอ' },
    { key: 'qrSize', type: 'int', def: 100, min: 60, max: 200, unit: '%', label: 'ขนาด QR' },
    { key: 'time', type: 'bool', def: true, label: 'เวลาเพลงมุมซ้ายล่าง' },
    { key: 'next', type: 'bool', def: true, label: 'การ์ดเพลงถัดไป (ตอนไม่มีเนื้อ)' },
    { key: 'addCard', type: 'bool', def: true, label: 'การ์ด "เพิ่มเข้าคิว" ตอนมีคนสั่งเพลง' },
    { key: 'logo', type: 'bool', def: false, label: 'รูปมุมขวาบน', upload: true },
    { key: 'logoSize', type: 'int', def: 100, min: 60, max: 200, unit: '%', label: 'ขนาดรูปมุมขวาบน' },
    { key: 'idleText', type: 'text', def: '', label: 'ข้อความหน้าจอว่าง', hint: 'แสดงใต้หัวข้อตอนยังไม่มีเพลง', maxlength: 80 },
    { key: 'mv', type: 'bool', def: false, label: 'MV จากเนื้อเพลงแทนวิดีโอ', hint: 'เฉพาะเพลงที่มีบท mv.json' },
  ] },
  { title: 'การเปลี่ยนเพลง', fields: [
    { key: 'fadeIn', type: 'int', def: 2, min: 0, max: 5, unit: 'วิ', label: 'เฟดเข้าตอนเริ่มเพลง', hint: '0 = ไม่เฟด' },
    { key: 'fadeOut', type: 'int', def: 3, min: 0, max: 5, unit: 'วิ', label: 'เฟดออกตอนจบหรือข้าม', hint: '0 = ตัดทันที' },
    { key: 'custom', type: 'bool', def: false, label: 'โหมด Custom: เล่นจากจุดเริ่มถึงจุดจบ' },
    { key: 'customLead', type: 'int', def: 4, min: 1, max: 10, unit: 'วิ', label: 'เริ่มก่อนท่อนแรก' },
    { key: 'customTail', type: 'int', def: 5, min: 0, max: 15, unit: 'วิ', label: 'จบหลังท่อนสุดท้าย' },
    { key: 'customAud', type: 'int', def: 0, min: 0, max: 5, unit: 'วิ', label: 'เฟดเสียงออกในโหมด Custom', hint: '0 = ตัดเสียงทันที' },
  ] },
  { title: 'ปุ่มข้ามอินโทร', fields: [
    { key: 'skipBtn', type: 'bool', def: true, label: 'ปุ่มข้ามอินโทรบนรีโมท' },
    { key: 'skipMin', type: 'int', def: 15, min: 5, max: 60, unit: 'วิ', label: 'แสดงปุ่มเมื่ออินโทรยาวเกิน' },
  ] },
];

const TV_FIELDS = TV_GROUPS.flatMap((g) => g.fields);
const cfgOf = (s) => {
  const out = {};
  for (const f of TV_FIELDS) out[f.key] = Object.hasOwn(s.cfg, f.key) ? s.cfg[f.key] : f.def;
  return out;
};


const defaults = () => cfgOf({ cfg: {} });

// แต่ละค่าเห็นผลในฉากไหน และชี้ไปส่วนไหนของจอ (scene: null = อยู่ฉากเดิม, panel = แผงอธิบายใต้จอ)
const FIELD_VIEW = {
  title: { scene: 'sing', part: 'title' },
  titleHide: { scene: 'sing', part: 'title', dep: 'title' },
  singer: { scene: 'sing', part: 'singer', dep: 'title' },
  chips: { scene: 'sing', part: 'chips', dep: 'title' },
  lyrScale: { scene: 'sing', part: 'lyrics' },
  lyrColor: { scene: 'sing', part: 'now-line' },
  lyrDim: { scene: 'sing', part: 'next-line' },
  karaColor: { scene: 'sing', part: 'now-line' },
  karaSmooth: { scene: 'sing', part: 'now-line' },
  lyrBg: { scene: 'sing', part: 'lyrics' },
  lyrShadow: { scene: 'sing', part: 'lyrics' },
  lyrLift: { scene: 'sing', part: 'lyrics' },
  countdown: { scene: 'intro', part: 'countdown' },
  voices: { scene: 'sing', part: 'next-line' },
  qr: { scene: 'sing', part: 'qr' },
  qrSize: { scene: 'sing', part: 'qr', dep: 'qr' },
  time: { scene: 'sing', part: 'time' },
  next: { scene: 'nolyrics', part: 'next' },
  addCard: { scene: 'sing', part: 'add', add: true },
  logo: { scene: null, part: 'logo' },
  logoSize: { scene: null, part: 'logo', dep: 'logo' },
  idleText: { scene: 'idle', part: 'idle-title' },
  mv: { scene: 'sing', part: 'sky' },
  fadeIn: { scene: 'sing', panel: 'fade' },
  fadeOut: { scene: 'sing', panel: 'fade' },
  custom: { scene: 'sing', panel: 'custom' },
  customLead: { scene: 'sing', panel: 'custom', dep: 'custom' },
  customTail: { scene: 'sing', panel: 'custom', dep: 'custom' },
  customAud: { scene: 'sing', panel: 'custom', dep: 'custom' },
  skipBtn: { scene: null, panel: 'skip' },
  skipMin: { scene: null, panel: 'skip', dep: 'skipBtn' },
};

// ภาพจอทีวีจำลอง สัดส่วนชุดเดียวกับจอจริง (หน่วย cqw = % ความกว้างจอ)
const CHIP_TEXT = (c, m, nx) => ({
  guide: `🎤 ไกด์ ${m.vocal ?? 100}%`, master: `🔊 เสียงรวม ${m.master ?? 80}%`, music: `🎵 ดนตรี ${m.music ?? 100}%`,
  key: `🎹 คีย์ ${(m.key || 0) > 0 ? '+' : ''}${m.key || 0}`,
  lyrsrc: `📝 ${((c && c.lyrKind) || 'ซับที่คนทำบน YouTube').split(' · ')[0]}`,
  next: `⏭ ${nx ? nx.title.slice(0, 30) : 'เพลงถัดไป'}`,
});
const SAMPLE = { title: 'ชื่อเพลงที่กำลังเล่น', singer: 'noname', title2: 'เพลงตัวอย่างถัดไป' };

function renderTvView(el, s, o = {}) {
  const c = o.cfg ?? cfgOf(s);
  const scene = o.scene ?? 'sing';
  const cur = s.room?.current;
  const next = s.room?.queue?.[0] ?? { title: SAMPLE.title2 };
  const hex = (h, a) => { const n = parseInt(String(h || '#ffffff').slice(1), 16) || 0xffffff; return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
  const logoOn = !!(c.logo && s.logoUrl);
  el.className = `preview tvv sh${c.lyrShadow}${c.qr ? '' : ' noqr'}${logoOn ? ' haslogo' : ''}`;
  const vars = {
    '--lyr': c.lyrColor, '--lyrdim': hex(c.lyrColor, c.lyrDim / 100), '--kara': c.karaColor, '--scale': c.lyrScale / 100,
    '--lift': c.lyrLift, '--bgpow': c.lyrBg / 100, '--qr': c.qrSize / 100, '--logo': c.logoSize / 100,
    '--v2': c.voices ? '#6fd3ff' : hex(c.lyrColor, c.lyrDim / 100),
    // อิงนาฬิกาจริง วาดใหม่แล้วแอนิเมชันเดินต่อจากเดิม ไม่เริ่มใหม่ตอนลากปรับค่า
    '--fillt': `-${Date.now() % 7000}ms`, '--skyt': `-${Date.now() % 32000}ms`,
  };
  for (const [k, v] of Object.entries(vars)) el.style.setProperty(k, v);
  const logo = logoOn ? `<div class="tvv-logo" data-part="logo"><img src="${esc(s.logoUrl)}" alt=""></div>` : '';

  if (scene === 'idle') {
    el.innerHTML = `<div class="tvv-sky" data-part="sky"></div>${logo}<div class="tvv-idle">
      <div class="tvv-idle-title">สแกนเพื่อ<b>สั่งเพลง</b></div>
      ${c.idleText ? `<div class="tvv-idle-text" data-part="idle-title">${esc(c.idleText)}</div>` : ''}
      <div class="tvv-idle-qr"><img src="/qr.png" alt="QR สั่งเพลง"></div>
    </div>`;
    return;
  }
  const chips = CHIP_TEXT(cur, s.room?.mix ?? {}, next);
  const mv = c.mv ? '<div class="tvv-mv"><i></i><i></i><i></i><span>ฉาก MV จากเนื้อเพลง (ภาพตัวอย่าง)</span></div>' : '';
  const hide = c.titleHide > 0 ? ` style="animation-delay:${c.titleHide}s"` : '';
  const top = c.title ? `<div class="tvv-top${c.titleHide > 0 ? ' autohide' : ''}" data-part="title"${hide}><b>${esc(cur?.title ?? SAMPLE.title)}</b>
    ${c.singer ? `<span class="tvv-chip singer" data-part="singer">🎤 ${esc(cur?.singer || SAMPLE.singer)}</span>` : ''}
    ${c.chips.length ? `<span class="tvv-chips" data-part="chips">${c.chips.map((k) => `<span class="tvv-chip">${esc(chips[k])}</span>`).join('')}</span>` : ''}</div>` : '';
  let middle = '';
  if (scene === 'intro') {
    middle = `<div class="tvv-lyrics" data-part="lyrics">
      ${c.countdown ? '<div class="tvv-count" data-part="countdown">♪ ● ● ●</div>' : ''}
      <div class="tvv-line" data-part="next-line">เนื้อเพลงบรรทัดแรก</div></div>`;
  } else if (scene === 'nolyrics') {
    middle = c.next ? `<div class="tvv-next" data-part="next"><small>ต่อไป</small><b>${esc(next.title)}</b></div>` : '';
  } else {
    const line = 'เนื้อเพลงบรรทัดที่กำลังร้อง';
    middle = `<div class="tvv-lyrics${c.karaSmooth ? '' : ' stepped'}" data-part="lyrics">
      <div class="tvv-line now" data-part="now-line"><span data-t="${line}">${line}</span></div>
      <div class="tvv-line v2" data-part="next-line">บรรทัดถัดไป เสียงร้องคนที่ 2</div></div>`;
  }
  const thumb = cur && (cur.localThumb || cur.thumb);
  el.innerHTML = `<div class="tvv-sky playing" data-part="sky"${thumb ? ` style="background:#000 center/cover url('${esc(thumb)}');animation:none"` : ''}></div>${mv}${logo}${top}${middle}
    ${c.time ? '<div class="tvv-time" data-part="time">1:23 / 4:10</div>' : ''}
    ${c.qr ? '<div class="tvv-float-qr" data-part="qr"><img src="/qr.png" alt="QR"></div>' : ''}
    ${c.addCard && o.showAdd ? `<div class="tvv-add" data-part="add"><b>➕ เพิ่มเข้าคิว · คิวที่ 2</b><div>${esc(SAMPLE.title2)}</div></div>` : ''}`;
}

const SCENES = [['idle', 'ตอนว่าง'], ['intro', 'ก่อนเข้าท่อนร้อง'], ['sing', 'กำลังร้อง'], ['nolyrics', 'เพลงไม่มีเนื้อ']];
const fieldOf = (key) => TV_FIELDS.find((f) => f.key === key);
const isChanged = (f, c) => JSON.stringify(c[f.key]) !== JSON.stringify(f.def);

function fmtValue(f, v) {
  if (f.type === 'bool') return v ? 'เปิด' : 'ปิด';
  if (f.type === 'int') return f.key === 'titleHide' && v === 0 ? 'แสดงตลอด' : (v === 0 && f.hint ? f.hint.split('= ')[1] : `${v} ${f.unit}`);
  if (f.type === 'select') return f.options.find(([o]) => o === v)[1];
  if (f.type === 'chips') return v.length ? v.map((k) => f.options.find(([o]) => o === k)[1]).join(', ') : 'ไม่แสดง';
  if (f.type === 'text') return v || 'ข้อความเริ่มต้น';
  return v;
}

function fieldHtml(f, c) {
  const v = c[f.key];
  const reset = `<button class="rowreset" data-reset="${f.key}" aria-label="คืนค่าเริ่มต้นของ ${esc(f.label)}" title="คืนค่าเริ่มต้น" ${isChanged(f, c) ? '' : 'hidden'}>↺</button>`;
  const lbl = `<div class="lbl"><label for="f-${f.key}">${esc(f.label)}</label>${f.hint ? `<small>${esc(f.hint)}</small>` : ''}</div>`;
  let ctl;
  if (f.type === 'bool') ctl = `<label class="switch"><input id="f-${f.key}" data-k="${f.key}" type="checkbox" ${v ? 'checked' : ''}><i></i></label>`;
  else if (f.type === 'int') ctl = `<input id="f-${f.key}" data-k="${f.key}" type="range" min="${f.min}" max="${f.max}" value="${v}"><output>${esc(fmtValue(f, v))}</output>`;
  else if (f.type === 'color') ctl = `<input id="f-${f.key}" data-k="${f.key}" type="color" value="${esc(v)}">`;
  else if (f.type === 'text') ctl = `<input id="f-${f.key}" data-k="${f.key}" type="text" value="${esc(v)}" maxlength="${f.maxlength || 80}" placeholder="เช่น ยินดีต้อนรับสู่ห้อง 5">`;
  else if (f.type === 'select') ctl = `<select id="f-${f.key}" data-k="${f.key}">${f.options.map(([o, t]) => `<option value="${o}" ${o === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  else return `<div class="field wide" data-row="${f.key}"><div class="lbl">${esc(f.label)}</div><div class="ctl chips" role="group" aria-label="${esc(f.label)}">${f.options.map(([o, t]) => `<label><input type="checkbox" data-chip="${o}" ${v.includes(o) ? 'checked' : ''}>${esc(t)}</label>`).join('')}</div>${reset}</div>`;
  const upload = f.upload ? `<div class="logoctl"><div class="logosq">${S.logoUrl ? `<img src="${esc(S.logoUrl)}" alt="">` : 'ยังไม่มีรูป'}</div><button class="btn" id="logopick">เลือกรูป</button><button class="btn" id="logodel" ${S.logoUrl ? '' : 'disabled'}>ลบรูป</button><input type="file" id="logofile" accept="image/*" hidden><small class="muted">ครอปเป็น 1:1 อัตโนมัติ สูงสุด 10 MB</small></div>` : '';
  return `<div class="field${f.upload ? ' wide' : ''}" data-row="${f.key}">${lbl}<div class="ctl">${ctl}</div>${reset}${upload}</div>`;
}

function tvSectionHtml() {
  const c = cfgOf(S);
  const q = ui.setQuery.trim().toLowerCase();
  const groups = TV_GROUPS.map((g) => ({ ...g, fields: g.fields.filter((f) => !q || f.label.toLowerCase().includes(q)) })).filter((g) => g.fields.length);
  if (!groups.length) return '<div class="card empty">ไม่พบค่าที่ตรงกับคำค้น</div>';
  return groups.map((g) => `<section class="card" data-group="${esc(g.title)}"><h2>${esc(g.title)}</h2>${g.fields.map((f) => fieldHtml(f, c)).join('')}</section>`).join('');
}

function tvSettingsHtml() {
  return `<div class="tvset">
    <div class="tvset-controls">
      <input class="setsearch" id="setq" type="text" placeholder="ค้นหาค่า เช่น สีซับ" aria-label="ค้นหาค่าจอทีวี" value="${esc(ui.setQuery)}">
      <div class="setmain" id="tvfields">${tvSectionHtml()}</div>
    </div>
    <aside class="tvset-stage">
      <div class="stage-bar">
        <div class="scenes" role="group" aria-label="ฉากบนจอ">${SCENES.map(([k, t]) => `<button data-scene="${k}">${esc(t)}</button>`).join('')}</div>
        <button class="btn hold" id="compare" title="กดค้างเพื่อดูภาพด้วยค่าเริ่มต้น">กดค้างดูค่าเดิม</button>
      </div>
      <div class="pv" id="pv">
        <div class="preview" id="preview"></div>
        <div class="pv-black" id="pvblack"></div>
        <div class="pv-box" id="pvbox" hidden></div>
        <div class="pv-tag" id="pvtag" hidden></div>
      </div>
      <p class="muted small" id="tvlive"></p>
      <div id="stagepanel"></div>
      <section class="card changes"><div class="row"><h2 id="chtitle"></h2><div class="grow"></div><button class="btn" id="cfgreset">คืนค่าทั้งหมด</button></div><div id="chlist"></div></section>
    </aside>
  </div>`;
}

/* ----- เวทีพรีวิว: วาดจอ ชี้จุดที่เปลี่ยน แผงอธิบาย รายการที่เปลี่ยน ----- */
const stage = { scene: 'sing', panel: null, showAdd: false, comparing: false, songId: 'TEST01', addTimer: null, tagTimer: null, fadeToken: 0 };

function paintStage() {
  const p = $('#preview');
  if (!p) return;
  renderTvView(p, S, {
    scene: stage.scene,
    songId: stage.songId,
    showAdd: stage.showAdd,
    cfg: stage.comparing ? defaults() : undefined,
  });
  for (const b of $$('[data-scene]')) b.setAttribute('aria-pressed', b.dataset.scene === stage.scene);
}

function rectIn(el) {
  const pv = $('#pv').getBoundingClientRect();
  const r = el.getBoundingClientRect();
  return { left: r.left - pv.left, top: r.top - pv.top, width: r.width, height: r.height };
}
const partEl = (part) => $(`#preview [data-part="${part}"]`);

// ตีกรอบส่วนของจอ พร้อมป้ายบอกค่า ถ้าส่วนนั้นถูกปิดไป (ghost = ตำแหน่งเดิม) ก็ตีกรอบเส้นประตรงที่มันเคยอยู่
function pointAt(part, text, ghost = null, keep = false) {
  const box = $('#pvbox');
  const tag = $('#pvtag');
  if (!box) return;
  clearTimeout(stage.tagTimer);
  const el = part ? partEl(part) : null;
  const r = el ? rectIn(el) : ghost;
  box.hidden = !r;
  if (r) {
    box.classList.toggle('ghost', !el);
    Object.assign(box.style, { left: `${r.left - 3}px`, top: `${r.top - 3}px`, width: `${r.width + 6}px`, height: `${r.height + 6}px` });
  }
  tag.hidden = !text;
  if (text) {
    tag.textContent = text;
    const pvW = $('#pv').clientWidth;
    const pvH = $('#pv').clientHeight;
    const tw = tag.offsetWidth;
    const th = tag.offsetHeight;
    const x = r ? r.left + r.width / 2 - tw / 2 : (pvW - tw) / 2;
    let y = r ? r.top - th - 8 : 12;
    if (y < 6) y = r ? Math.min(r.top + r.height + 8, pvH - th - 6) : 12;
    tag.style.left = `${Math.max(6, Math.min(x, pvW - tw - 6))}px`;
    tag.style.top = `${y}px`;
  }
  if (!keep) stage.tagTimer = setTimeout(clearPoint, 2200);
}
function clearPoint() {
  const box = $('#pvbox');
  if (!box) return;
  box.hidden = true;
  $('#pvtag').hidden = true;
}

function setScene(scene) {
  stage.scene = scene;
  paintStage();
}

async function playFade(mode) {
  const black = $('#pvblack');
  if (!black) return;
  const token = ++stage.fadeToken;
  const c = cfgOf(S);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const to = async (opacity, sec) => {
    black.style.transition = `opacity ${sec}s linear`;
    black.style.opacity = opacity;
    await wait(sec * 1000 + 30);
  };
  black.style.transition = 'none';
  black.style.opacity = mode === 'in' ? 1 : 0;
  await wait(30);
  if (mode !== 'in') {
    await to(1, c.fadeOut);
    if (token !== stage.fadeToken) return;
    await wait(350);
    if (token !== stage.fadeToken) return;
  }
  if (mode === 'both') {
    stage.songId = stage.songId === 'TEST01' ? 'TEST03' : 'TEST01';
    paintStage();
  }
  await to(0, mode === 'out' ? 0 : c.fadeIn);
}

function renderPanel() {
  const box = $('#stagepanel');
  if (!box) return;
  const c = cfgOf(S);
  if (stage.panel === 'fade') {
    box.innerHTML = `<section class="card panel"><h2>เฟดตอนเปลี่ยนเพลง</h2>
      <p class="muted small">เฟดออก ${esc(fmtValue(fieldOf('fadeOut'), c.fadeOut))} แล้วเฟดเข้า ${esc(fmtValue(fieldOf('fadeIn'), c.fadeIn))}</p>
      <button class="btn" id="playfade">▶ ลองเปลี่ยนเพลงบนจอ</button></section>`;
    $('#playfade').onclick = () => playFade('both');
  } else if (stage.panel === 'custom') {
    const seg = (cls, t, flex) => `<div class="tl ${cls}" style="flex:${flex}">${esc(t)}</div>`;
    box.innerHTML = `<section class="card panel"><h2>โหมด Custom</h2>
      ${c.custom ? `<div class="timeline" role="img" aria-label="ช่วงที่เล่นของเพลงในโหมด Custom">${seg('cut', 'ตัดทิ้ง', 3)}${seg('keep', `${c.customLead} วิ`, Math.max(c.customLead, 2))}${seg('sing', 'ท่อนร้อง', 12)}${seg('keep', `${c.customTail} วิ`, Math.max(c.customTail, 2))}${seg('cut', 'ตัดทิ้ง', 3)}</div>
      <p class="muted small">เริ่มก่อนท่อนแรก ${c.customLead} วิ จบหลังท่อนสุดท้าย ${c.customTail} วิ ${c.customAud ? `เสียงเฟดออก ${c.customAud} วิ` : 'เสียงตัดทันที'}</p>`
    : '<p class="muted small">ปิดอยู่ เล่นแต่ละเพลงเต็มตั้งแต่ต้นจนจบ</p>'}</section>`;
  } else if (stage.panel === 'skip') {
    box.innerHTML = `<section class="card panel"><h2>ปุ่มบนรีโมท (ไม่แสดงบนจอทีวี)</h2>
      <div class="phone">${c.skipBtn ? `<button class="btn primary" tabindex="-1" aria-hidden="true">${icon('skip')}ข้ามอินโทร</button>` : '<span class="muted small">ไม่มีปุ่มข้ามอินโทร</span>'}</div>
      <p class="muted small">${c.skipBtn ? `ปุ่มจะโผล่เมื่ออินโทรยาวเกิน ${c.skipMin} วิ` : 'ปิดอยู่ ต้องรอจนจบอินโทร'}</p></section>`;
  } else {
    box.innerHTML = '';
  }
}

function renderChanges() {
  const title = $('#chtitle');
  if (!title) return;
  const c = cfgOf(S);
  const changed = TV_FIELDS.filter((f) => isChanged(f, c));
  title.textContent = changed.length ? `เปลี่ยนจากค่าเริ่มต้น ${changed.length} ค่า` : 'ยังใช้ค่าเริ่มต้นทั้งหมด';
  $('#cfgreset').hidden = !changed.length;
  const show = (f, v) => (f.type === 'color' ? `<i class="swatch" style="background:${esc(v)}"></i>` : esc(fmtValue(f, v)));
  $('#chlist').innerHTML = changed.map((f) => `<div class="chg"><button class="chg-go" data-go="${f.key}"><b>${esc(f.label)}</b><span>${show(f, f.def)} → ${show(f, c[f.key])}</span></button><button class="rowreset" data-reset="${f.key}" aria-label="คืนค่าเริ่มต้นของ ${esc(f.label)}" title="คืนค่าเริ่มต้น">↺</button></div>`).join('');
  bindResets($('#chlist'));
  for (const b of $$('[data-go]')) b.onclick = () => revealField(b.dataset.go);
}

function revealField(key) {
  const row = $(`[data-row="${key}"]`);
  if (!row) return;
  row.scrollIntoView({ block: 'center', behavior: 'smooth' });
  row.classList.remove('flash');
  void row.offsetWidth;
  row.classList.add('flash');
}

// ค่าลูกใช้ไม่ได้เมื่อค่าแม่ปิดอยู่ เช่น ขนาด QR ตอนปิด QR
function syncDeps() {
  const c = cfgOf(S);
  for (const row of $$('[data-row]')) {
    const dep = FIELD_VIEW[row.dataset.row]?.dep;
    if (!dep) continue;
    const off = !c[dep];
    row.classList.toggle('off', off);
    for (const i of $$('input,select', row)) i.disabled = off;
  }
}

// ทุกการปรับค่าผ่านจุดนี้: พาไปฉากที่เห็นผล วาดจอใหม่ แล้วชี้จุดที่เปลี่ยน
function applyField(key, value) {
  const f = fieldOf(key);
  const view = FIELD_VIEW[key];
  const before = view.part && partEl(view.part) ? rectIn(partEl(view.part)) : null;
  S.cfg[key] = value;
  saveLater({ [key]: value });
  if (view.scene && view.scene !== stage.scene) stage.scene = view.scene;
  if (view.add) {
    stage.showAdd = true;
    clearTimeout(stage.addTimer);
    stage.addTimer = setTimeout(() => { stage.showAdd = false; paintStage(); }, 3500);
  }
  stage.panel = view.panel ?? null;
  paintStage();
  renderPanel();
  renderChanges();
  syncDeps();
  const row = $(`[data-row="${key}"]`);
  if (row) {
    const reset = $('.rowreset', row);
    if (reset) reset.hidden = !isChanged(f, cfgOf(S));
  }
  if (view.part) pointAt(view.part, `${f.label}: ${fmtValue(f, value)}`, before);
  else clearPoint();
  if (key === 'fadeIn') playFade('in');
  if (key === 'fadeOut') playFade('out');
}

function bindResets(root) {
  for (const b of $$('[data-reset]', root)) {
    b.onclick = () => {
      const key = b.dataset.reset;
      const f = fieldOf(key);
      const value = Array.isArray(f.def) ? [...f.def] : f.def;
      applyField(key, value);
      const row = $(`[data-row="${key}"]`);
      if (row) {
        row.outerHTML = fieldHtml(f, cfgOf(S));
        bindTvFields();
        syncDeps();
      }
    };
  }
}

function bindTvFields() {
  for (const el of $$('[data-k]')) {
    const key = el.dataset.k;
    const f = fieldOf(key);
    if (f.type === 'bool') el.onchange = () => applyField(key, el.checked);
    else if (f.type === 'int') el.oninput = () => { el.nextElementSibling.textContent = fmtValue(f, +el.value); applyField(key, +el.value); };
    else if (f.type === 'select') el.onchange = () => applyField(key, +el.value);
    else el.oninput = () => applyField(key, el.value);
  }
  for (const el of $$('[data-chip]')) {
    el.onchange = () => applyField('chips', $$('[data-chip]').filter((x) => x.checked).map((x) => x.dataset.chip));
  }
  bindResets($('#tvfields'));
  bindLogo();
  // ชี้เมาส์ที่แถวไหน จอตีกรอบส่วนนั้นให้ ไม่สลับฉากเพื่อไม่ให้จอกระโดดไปมา
  for (const row of $$('[data-row]')) {
    row.onmouseenter = () => {
      const view = FIELD_VIEW[row.dataset.row];
      if (view.part && partEl(view.part)) pointAt(view.part, '', null, true);
    };
    row.onmouseleave = clearPoint;
  }
  syncDeps();
}

function bindTvStage() {
  paintStage();
  renderPanel();
  renderChanges();
  bindTvFields();
  for (const b of $$('[data-scene]')) b.onclick = () => { stage.panel = null; renderPanel(); clearPoint(); setScene(b.dataset.scene); };
  const cmp = $('#compare');
  const hold = (on) => {
    if (stage.comparing === on) return;
    stage.comparing = on;
    cmp.classList.toggle('active', on);
    clearPoint();
    paintStage();
    if (on) pointAt(null, 'ค่าเริ่มต้น', null, true);
  };
  cmp.onpointerdown = () => hold(true);
  for (const ev of ['pointerup', 'pointerleave', 'pointercancel']) cmp.addEventListener(ev, () => hold(false));
  cmp.onkeydown = (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); hold(true); } };
  cmp.onkeyup = () => hold(false);
  cmp.onblur = () => hold(false);
  // คลิกส่วนบนจอ = ไปยังค่าของส่วนนั้น
  $('#preview').onclick = (e) => {
    const part = e.target.closest('[data-part]')?.dataset.part;
    const key = part && Object.keys(FIELD_VIEW).find((k) => FIELD_VIEW[k].part === part);
    if (key) revealField(key);
  };
  $('#cfgreset').onclick = async () => {
    await save({ reset: true });
    stage.panel = null;
    drawAll();
  };
  const q = $('#setq');
  q.oninput = () => {
    ui.setQuery = q.value;
    $('#tvfields').innerHTML = tvSectionHtml();
    bindTvFields();
  };
}


/* ----- บันทึกจริง + รูปมุมขวาบน + เชื่อมกับแอป ----- */
const saving = { timer: null, pending: {} };

function setStatus(text, bad = false) {
  const el = $('#tvlive');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('bad', bad);
}

function takeTv(tv) {
  const { logoUrl, ...cfg } = tv;
  S.cfg = cfg;
  S.logoUrl = logoUrl || '';
}

async function api(path, opt = {}) {
  const r = await fetch(path, { credentials: 'same-origin', ...opt });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) throw new Error('ต้องใส่ PIN ใน Studio ก่อน');
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
  return j;
}

async function save(body) {
  setStatus('กำลังบันทึก…');
  try {
    const r = await api('/api/studio/tv', { method: 'POST', body: JSON.stringify(body) });
    if (!Object.keys(saving.pending).length) takeTv(r.tv);
    setStatus('บันทึกแล้ว จอทีวีเปลี่ยนตามทันที · คลิกส่วนบนจอเพื่อไปยังค่าของส่วนนั้น');
    return true;
  } catch (e) {
    setStatus(`บันทึกไม่ได้: ${e.message}`, true);
    return false;
  }
}

function saveLater(patch) {
  Object.assign(saving.pending, patch);
  setStatus('กำลังบันทึก…');
  clearTimeout(saving.timer);
  saving.timer = setTimeout(() => {
    const body = saving.pending;
    saving.pending = {};
    save(body);
  }, 300);
}

function bindLogo() {
  const pick = $('#logopick');
  if (!pick) return;
  const file = $('#logofile');
  pick.onclick = () => file.click();
  file.onchange = async () => {
    const f = file.files[0];
    file.value = '';
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { setStatus('รูปใหญ่เกิน 10 MB', true); return; }
    setStatus('กำลังอัปรูป…');
    try {
      const r = await api('/api/studio/tv/logo', { method: 'PUT', headers: { 'Content-Type': f.type || 'application/octet-stream' }, body: f });
      takeTv(r.tv);
      drawAll();
      setStatus('อัปรูปแล้ว ขึ้นมุมขวาบนของจอทีวีเมื่อเปิดสวิตช์');
    } catch (e) { setStatus(`อัปรูปไม่ได้: ${e.message}`, true); }
  };
  $('#logodel').onclick = async () => {
    try {
      const r = await api('/api/studio/tv/logo', { method: 'DELETE' });
      takeTv(r.tv);
      drawAll();
      setStatus('ลบรูปแล้ว');
    } catch (e) { setStatus(`ลบรูปไม่ได้: ${e.message}`, true); }
  };
}

function drawAll() {
  $('#app').innerHTML = tvSettingsHtml();
  bindTvStage();
}

// เครื่องอื่นเปลี่ยนค่า / เพลงเปลี่ยน -> ตามให้ทันโดยไม่ทับค่าที่กำลังลากอยู่
function connectWs() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type !== 'state') return;
    S.room = m;
    if (m.tv && !Object.keys(saving.pending).length && !saving.timer) {
      const before = JSON.stringify([S.cfg, S.logoUrl]);
      takeTv(m.tv);
      if (before !== JSON.stringify([S.cfg, S.logoUrl])) drawAll();
    }
    if (!stage.comparing) paintStage();
  };
  ws.onclose = () => setTimeout(connectWs, 2500);
  ws.onerror = () => { try { ws.close(); } catch { /* กำลังปิดอยู่แล้ว */ } };
}

// ธีมมาจากหน้าที่ฝังอยู่: ?theme= ตอนเปิด, postMessage ตอนผู้ใช้เปลี่ยนธีมในแอป
const THEME_IDS = ['peach', 'mint', 'lavender', 'sweetnight', 'classic'];
function setTheme(id) { if (THEME_IDS.includes(id)) document.documentElement.dataset.theme = id; }
setTheme(new URLSearchParams(location.search).get('theme') || 'classic');
window.addEventListener('message', (e) => { if (e.source === window.parent && e.data?.type === 'kara-theme') setTheme(e.data.theme); });

(async function start() {
  try {
    const r = await api('/api/studio/tv');
    takeTv(r.tv);
    drawAll();
    connectWs();
  } catch (e) {
    $('#app').innerHTML = `<div class="card empty">${esc(e.message)} <a href="/studio" target="_top">เปิด Studio</a></div>`;
  }
}());
