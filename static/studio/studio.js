// Studio ใหม่: 2 งานหลัก คือหาเพลงที่มีปัญหา กับเปลี่ยนแหล่งเนื้อ/แก้ข้อความให้จบในไม่กี่คลิก
// การจับเวลาให้ระบบทำเอง หน้าละเอียดของเดิมอยู่ที่ /studio/old
const $ = (q, el = document) => el.querySelector(q);
const $$ = (q, el = document) => [...el.querySelectorAll(q)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const params = new URLSearchParams(location.search);

const TABS = [['now', 'กำลังเล่น', 'play'], ['lib', 'คลังเพลง', 'list'], ['cut', 'ตัดต่อ & คอมโบ', 'cut'], ['screen', 'หน้าจอหลัก', 'tv']];
const FILTERS = [
  ['fix', 'ต้องแก้', (i) => i.reports > 0 || !i.lyrLines || ['bad', 'sparse'].includes(i.lyrConf) || i.fix],
  ['reports', 'แขกแจ้ง', (i) => i.reports > 0],
  ['nolyr', 'ไม่มีเนื้อ', (i) => !i.lyrLines],
  ['all', 'ทั้งหมด', () => true],
];
const PROV = { current: 'เนื้อที่ใช้อยู่', 'yt-sub': 'ซับ YouTube', joox: 'JOOX', netease: 'NetEase', ytmusic: 'YouTube Music', lrclib: 'LRCLIB',
  'yt-auto': 'YouTube อัตโนมัติ', 'web/description': 'คำอธิบายคลิป', musixmatch: 'Musixmatch', library: 'เพลงเดียวกันในคลัง', ocr: 'ตัวหนังสือในคลิป' };
const TAGS = { late: 'ซับขึ้นช้า', early: 'ซับขึ้นเร็ว', typo: 'เนื้อผิด', missing: 'ขาดบางท่อน', nolyr: 'ไม่มีเนื้อ', wrong: 'เนื้อผิดเพลง', fast: 'ท่อนเร็วขึ้นไม่ทัน', overlap: 'ร้องซ้อนแล้วซับไม่ขึ้น' };

const S = {
  view: 'now', room: null, songs: [], filter: 'fix', q: '', libVid: null, nowVid: null, posAt: 0, pos: 0,
  eds: new Map(),  // videoId -> เอกสารแก้เพลง เก็บแยกต่อเพลง งานที่แก้ค้างจึงไม่หายตอนสลับเพลง
};

function toast(msg, ms = 2800) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove('show'), ms);
}
const fmt = (t) => { const s = Math.max(0, Math.floor(t || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const norm = (s) => String(s).replace(/\s+/g, '').toLowerCase();

async function api(path, opt = {}) {
  const r = await fetch(path, { credentials: 'same-origin', ...opt });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { askPin(); throw new Error('ต้องใส่ PIN'); }
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
  return j;
}
const post = (path, body, method = 'POST') => api(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function askPin() {
  const d = $('#pin');
  if (!d.open) d.showModal();
}
$('#pinform').onsubmit = async (e) => {
  e.preventDefault();
  try {
    const r = await post('/api/studio/login', { pin: $('#pinin').value });
    if (!r.ok) throw new Error(r.why || 'PIN ไม่ถูกต้อง');
    $('#pin').close();
    loadSongs();
    drawEditors();
  } catch (err) { $('#pinerr').textContent = err.message; }
};

/* ===== เอกสารแก้เพลง ===== */
function ed(vid) {
  let e = S.eds.get(vid);
  if (!e) {
    e = { vid, detail: null, lines: [], saved: '', cands: null, pick: null, srcBusy: false, srcErr: '', busy: '', trial: null, loadedUrl: '' };
    S.eds.set(vid, e);
  }
  return e;
}
const lineKey = (lines) => JSON.stringify(lines.map((l) => l.x));
const isDirty = (e) => !!e.detail && lineKey(e.lines) !== e.saved;

async function loadDetail(e) {
  const d = await api(`/api/studio/song/${e.vid}`);
  e.detail = d;
  if (!isDirtyBefore(e)) {
    e.lines = (d.lyrics?.lines || []).map((l) => ({ ...l }));
    e.saved = lineKey(e.lines);
  }
  e.loadedUrl = d.item?.lyricsUrl || '';
}
const isDirtyBefore = (e) => e.saved !== '' && lineKey(e.lines) !== e.saved;

// แหล่งเนื้อ: ถ้าเตรียมไว้แล้วตอบทันที ถ้ากำลังเตรียมอยู่ เซิร์ฟเวอร์ให้รอผลชุดเดียวกัน ไม่ค้นซ้ำ
async function loadSources(e, opts = {}) {
  e.srcBusy = true;
  e.srcErr = '';
  if (opts.fresh) e.cands = null;
  drawEditors();
  try {
    const r = await post(`/api/studio/song/${e.vid}/sources`, { track: opts.track || '', artist: opts.artist || '', fresh: !!opts.fresh });
    e.cands = r.candidates || [];
    e.pick = r.pick;
  } catch (err) { e.srcErr = err.message; }
  e.srcBusy = false;
  drawEditors();
}
async function openEd(vid) {
  const e = ed(vid);
  try {
    if (!e.detail) await loadDetail(e);
    if (!e.cands && !e.srcBusy) loadSources(e);
  } catch (err) { toast(err.message); }
  drawEditors();
}

const provName = (c) => (c.provider.startsWith('ocr+') ? `${PROV[c.provider.slice(4)] || c.provider.slice(4)} + เวลาจากคลิป` : PROV[c.provider] || c.label || c.provider);

// ใช้ได้ทันทีเมื่อมีเวลา: เวลา FA จากเสียงร้องจริงก่อน ไม่มีค่อยใช้เวลาของแหล่ง ไม่มีเวลาเลยให้ระบบจับให้
async function linesFromCand(e, c) {
  if (c.faLines) return c.faLines.map((l, i) => ({ t: +l.t, d: +l.d, x: l.x, ...(c.lines?.[i]?.v ? { v: c.lines[i].v } : {}) }));
  if (c.synced) return c.lines.map((l) => ({ ...l, t: Math.round(Math.max(0, +l.t + (c.shift || 0)) * 100) / 100 }));
  return timeTexts(e, c.texts);
}
async function timeTexts(e, texts) {
  const r = await post(`/api/studio/song/${e.vid}/autotime`, { texts });
  if (!r.lines) throw new Error('ยังจับเวลาให้เนื้อนี้ไม่ได้ เนื้อเดิมยังอยู่');
  return r.lines.map((l) => ({ t: +l.t, d: +l.d, x: l.x }));
}
async function saveLines(e, lines, offset, picked) {
  await post(`/api/studio/song/${e.vid}/lyrics`, { lines: lines.map((l) => ({ t: l.t, d: l.d, x: l.x, ...(l.v ? { v: l.v } : {}) })), offset, ...(picked ? { picked } : {}) }, 'PUT');
  e.saved = '';
  e.lines = lines;
  e.saved = lineKey(lines);
  await loadDetail(e);
}
async function withBusy(e, label, job) {
  if (e.busy) return;
  e.busy = label;
  drawEditors();
  try { await job(); } catch (err) { toast(err.message, 5000); }
  e.busy = '';
  drawEditors();
}
const onScreen = (e) => S.room?.current?.videoId === e.vid;
const savedMsg = (e) => (onScreen(e) ? 'ขึ้นจอทีวีแล้ว' : 'บันทึกแล้ว');

const ACT = {
  useSrc: (e, k) => withBusy(e, 'กำลังเปลี่ยนแหล่งเนื้อ…', async () => {
    const c = e.cands[+k];
    const lines = await linesFromCand(e, c);
    await saveLines(e, lines, 0, `เนื้อจาก ${provName(c)}`);
    e.trial = null;
    toast(`ใช้ ${provName(c)} แล้ว · ${savedMsg(e)}`);
  }),
  tryOn: async (e, k) => {
    const c = e.cands[+k];
    if (!c.faLines && !c.synced) { toast('แหล่งนี้ไม่มีเวลา ลองฟังไม่ได้'); return; }
    e.trial = { name: provName(c), lines: await linesFromCand(e, c) };
    const v = $('video', editorHost(e));
    drawEditors();
    if (v) { const nv = $('video', editorHost(e)); nv?.play?.().catch(() => {}); }
  },
  tryOff: (e) => { e.trial = null; drawEditors(); },
  save: (e) => withBusy(e, 'กำลังบันทึก…', async () => {
    let lines = e.lines.map((l) => ({ ...l, x: l.x.trim() })).filter((l) => l.x);
    if (!lines.length) throw new Error('ยังไม่มีเนื้อให้บันทึก');
    // แก้แค่คำผิด เวลาเดิมยังใช้ได้ · เพิ่มบรรทัดใหม่ต้องให้ระบบจับเวลาใหม่ทั้งเพลง
    if (lines.some((l) => l.t == null)) lines = await timeTexts(e, lines.map((l) => l.x));
    await saveLines(e, lines, null);
    toast(savedMsg(e));
  }),
  discard: (e) => { e.lines = (e.detail.lyrics?.lines || []).map((l) => ({ ...l })); drawEditors(); },
  addLine: (e) => { e.lines.push({ t: null, d: null, x: '' }); drawEditors(); $$('.line input', editorHost(e)).pop()?.focus(); },
  delLine: (e, k) => { e.lines.splice(+k, 1); drawEditors(); },
  undo: (e) => withBusy(e, 'กำลังย้อนกลับ…', async () => {
    const ts = e.detail.edits?.[0]?.ts;
    if (!ts) throw new Error('ยังไม่มีฉบับก่อนหน้า');
    const v = await api(`/api/studio/song/${e.vid}/edit/${ts}`);
    await saveLines(e, v.lines || [], null);
    toast(`ย้อนเป็นฉบับก่อนแล้ว · ${savedMsg(e)}`);
  }),
  shift: (e, d) => withBusy(e, '', async () => {
    const off = Math.round(((e.detail.offset || 0) + +d) * 100) / 100;
    await post(`/api/studio/song/${e.vid}/offset`, { offset: off });
    e.detail.offset = off;
    toast(`เลื่อนซับเป็น ${off > 0 ? '+' : ''}${off} วิ`);
  }),
  action: (e, what) => withBusy(e, what === 'revideo' ? 'กำลังโหลดคลิป…' : 'กำลังซ่อม…', async () => {
    const r = await post(`/api/studio/song/${e.vid}/action`, { do: what });
    toast(r.msg || 'สั่งแล้ว', 7000);
    e.detail = null;
    await loadDetail(e);
  }),
  researchSrc: (e) => loadSources(e, { track: $('.sqt', editorHost(e)).value.trim(), artist: $('.sqa', editorHost(e)).value.trim(), fresh: true }),
  remove: (e) => {
    if (!confirm(`ลบ "${e.detail.item.title}" ออกจากเครื่อง?\n\nลบวิดีโอ เสียง และเนื้อของเพลงนี้ ย้อนกลับไม่ได้`)) return;
    withBusy(e, 'กำลังลบ…', async () => {
      await api(`/api/studio/song/${e.vid}?edits=0`, { method: 'DELETE' });
      S.eds.delete(e.vid);
      S.libVid = null;
      toast('ลบเพลงแล้ว');
      await loadSongs();
    });
  },
  repDone: async (e, id) => {
    try {
      await post(`/api/studio/song/${e.vid}/reports`, { id, done: true });
      await loadDetail(e);
      loadSongs();
      drawEditors();
    } catch (err) { toast(err.message); }
  },
  seek: (e, t) => { const v = $('video', editorHost(e)); if (v) { v.currentTime = Math.max(0, +t - 2); v.play().catch(() => {}); } },
};

/* ===== วาดส่วนแก้เพลง ===== */
function sourcesHtml(e) {
  if (e.srcErr) return `<p class="bad">${esc(e.srcErr)}</p>`;
  if (!e.cands) return `<div class="wait">กำลังเตรียมแหล่งเนื้อ…<br><span class="small">ถ้าเพลงอยู่ในคิว ระบบเตรียมไว้ล่วงหน้าให้แล้ว</span></div>`;
  if (!e.cands.length) return '<div class="wait">ไม่เจอเนื้อจากแหล่งไหน ลองค้นเองด้านล่าง</div>';
  const cur = lineKeyN(e.detail?.lyrics?.lines);
  return e.cands.map((c, k) => {
    const texts = c.synced ? c.lines.map((l) => l.x) : c.texts;
    const active = c.provider === 'current' || lineKeyN(texts.map((x) => ({ x }))) === cur;
    const tone = (v) => (v >= 45 ? 'ok' : v >= 20 ? 'warn' : 'bad');
    const canTry = c.faLines || c.synced;
    return `<div class="src${active ? ' active' : ''}">
      <div class="h">${c.id === e.pick ? '<span class="chip star">⭐ แนะนำ</span>' : ''}<b>${esc(provName(c))}</b>
        ${active ? '<span class="chip ok">✓ ใช้อยู่</span>' : ''}
        ${c.match != null ? `<span class="chip ${tone(c.match)}">เข้ากับเพลง ${c.match}%</span>` : ''}
        ${c.cover != null ? `<span class="chip ${c.sparse ? 'bad' : ''}">${c.sparse ? 'มีแค่บางช่วง ' : 'คลุมเสียงร้อง '}${c.cover}%</span>` : ''}
        ${c.synced || c.faLines ? '' : '<span class="chip">ไม่มีเวลา ระบบจับให้</span>'}
        <span class="chip">${texts.length} บรรทัด</span></div>
      <div class="p">${esc(texts.slice(0, 3).join(' / '))}${texts.length > 3 ? ' …' : ''}</div>
      ${active ? '' : `<div class="b"><button class="btn primary tiny" data-a="useSrc" data-v="${k}" ${e.busy ? 'disabled' : ''}>ใช้เลย</button>
        ${e.preview && canTry ? `<button class="btn tiny" data-a="tryOn" data-v="${k}">ลองฟังก่อน</button>` : ''}</div>`}
    </div>`;
  }).join('');
}
const lineKeyN = (lines) => (lines || []).map((l) => norm(l.x)).join('|');

function editorHtml(e, { preview }) {
  const d = e.detail;
  if (!d) return '<div class="wait">กำลังโหลด…</div>';
  e.preview = preview;
  const it = d.item;
  const lines = e.lines;
  const reports = (d.reports || []).filter((r) => !r.done);
  const off = d.offset || 0;
  const pv = preview && it.hasVideo ? `<div class="preview"><video src="/song/${e.vid}/video.mp4" controls preload="metadata"></video><div class="sub" aria-live="off"></div></div>
    ${e.trial ? `<div class="notice">กำลังลองฟังเนื้อจาก ${esc(e.trial.name)} ยังไม่ได้บันทึก <button class="btn tiny" data-a="tryOff">เลิกลอง</button></div>` : ''}` : '';
  const rep = reports.length ? `<section class="card" style="margin-bottom:14px"><h2>แขกแจ้ง ${reports.length} จุด</h2>${reports.map((r) => `<div class="report">
      ${preview ? `<button class="btn tiny" data-a="seek" data-v="${r.pos}">▶ ${fmt(r.pos)}</button>` : `<span class="chip">${fmt(r.pos)}</span>`}
      <span class="grow">${esc((r.tags || []).map((t) => TAGS[t] || t).join(', '))}${r.note ? ` · ${esc(r.note)}` : ''}</span>
      <button class="btn tiny" data-a="repDone" data-v="${esc(r.id)}">แก้แล้ว</button></div>`).join('')}</section>` : '';
  return `${pv}${rep}<div class="editgrid">
    <section class="card"><h2>แหล่งเนื้อ</h2>${sourcesHtml(e)}
      <details class="more"><summary>หาไม่เจอ ค้นด้วยชื่อเอง</summary><div class="searchrow">
        <input class="sqt" placeholder="ชื่อเพลง" aria-label="ชื่อเพลง"><input class="sqa" placeholder="ศิลปิน" aria-label="ศิลปิน">
        <button class="btn tiny" data-a="researchSrc" ${e.srcBusy ? 'disabled' : ''}>ค้นใหม่</button></div></details>
    </section>
    <section class="card"><h2>เนื้อที่ใช้อยู่ ${lines.length ? `<span class="muted small">${lines.length} บรรทัด</span>` : ''}</h2>
      <div class="toolbar">
        <button class="btn primary tiny" data-a="save" ${isDirty(e) && !e.busy ? '' : 'disabled'}>${icon('save')}บันทึก</button>
        ${isDirty(e) ? '<button class="btn tiny" data-a="discard">ทิ้งที่แก้</button>' : ''}
        <button class="btn tiny" data-a="undo" ${d.edits?.length && !e.busy ? '' : 'disabled'}>↶ ย้อนฉบับก่อน</button>
        <span class="shift"><span class="muted small">ซับ</span>
          <button class="btn tiny" data-a="shift" data-v="-0.5" aria-label="ให้ซับขึ้นเร็วขึ้นครึ่งวินาที">เร็วขึ้น</button>
          <span class="small">${off > 0 ? '+' : ''}${off} วิ</span>
          <button class="btn tiny" data-a="shift" data-v="0.5" aria-label="ให้ซับขึ้นช้าลงครึ่งวินาที">ช้าลง</button></span>
      </div>
      <div class="lines">${lines.map((l, k) => `<div class="line" data-k="${k}"><span class="t">${l.t == null ? 'ใหม่' : fmt(l.t)}</span>
        <input value="${esc(l.x)}" data-k="${k}" aria-label="บรรทัด ${k + 1}"><button class="x" data-a="delLine" data-v="${k}" aria-label="ลบบรรทัด ${k + 1}">✕</button></div>`).join('') || '<div class="wait">เพลงนี้ยังไม่มีเนื้อ เลือกจากแหล่งเนื้อได้เลย</div>'}</div>
      <button class="btn tiny" data-a="addLine" style="margin-top:8px">＋ เพิ่มบรรทัด</button>
    </section></div>`;
}
function headHtml(e) {
  const it = e.detail?.item;
  if (!it) return '';
  return `<div class="songhead"><div class="grow"><h1>${esc(it.title)}</h1><p class="muted small">${esc(it.channel || '')}${it.duration ? ` · ${fmt(it.duration)}` : ''}${e.busy ? ` · <b>${esc(e.busy)}</b>` : ''}</p></div>
    <div class="acts"><button class="btn" data-a="action" data-v="revideo" ${e.busy ? 'disabled' : ''} title="โหลดคลิปใหม่ให้ชัดขึ้น เปลี่ยนเฉพาะเมื่อชัดกว่าเดิม เสียงและเนื้อไม่เปลี่ยน">${icon('film')}โหลดวิดีโอใหม่</button>
      <button class="btn" data-a="action" data-v="fix" ${e.busy ? 'disabled' : ''} title="ให้ระบบเลือกขั้นที่พังแล้วทำใหม่">${icon('spark')}ซ่อมอัตโนมัติ</button>
      <button class="btn danger" data-a="remove" ${e.busy || S.room?.current?.videoId === e.vid ? 'disabled' : ''}>ลบเพลง</button></div></div>`;
}
const editorHost = (e) => (S.view === 'now' && S.nowVid === e.vid ? $('#now') : $('#libedit'));

function capture(host) {
  const f = document.activeElement;
  return { top: host.scrollTop, k: f?.matches?.('.line input') && host.contains(f) ? f.dataset.k : null, pos: f?.selectionStart };
}
function restore(host, c) {
  host.scrollTop = c.top;
  if (c.k != null) {
    const i = $(`.line input[data-k="${c.k}"]`, host);
    if (i) { i.focus(); try { i.setSelectionRange(c.pos, c.pos); } catch { /* ช่องชนิดนี้ไม่มี selection */ } }
  }
}
// วาดส่วนแก้เพลงใหม่ แต่ไม่รื้อวิดีโอพรีวิวที่กำลังเล่นอยู่
function drawEditors() {
  drawNow();
  drawLib();
}
function drawNow() {
  if (S.view !== 'now') return;
  const host = $('#now');
  const c = capture(host);
  const cur = S.room?.current;
  const upcoming = (S.room?.queue || []).filter((q) => q.videoId).slice(0, 3);
  const chips = [cur, ...upcoming].filter((q) => q?.videoId);
  if (!chips.length) {
    host.innerHTML = '<div class="empty"><h1>ยังไม่มีเพลงเล่นอยู่</h1><p>พอมีเพลงเล่น หน้านี้จะเปิดเพลงนั้นให้เอง พร้อมแหล่งเนื้อที่เตรียมไว้</p></div>';
    return;
  }
  const e = ed(S.nowVid);
  const moved = cur?.videoId && cur.videoId !== S.nowVid && !upcoming.some((q) => q.videoId === S.nowVid);
  host.innerHTML = `<div class="nextbar">${chips.map((q, k) => `<button class="btn tiny${q.videoId === S.nowVid ? ' primary' : ''}" data-now="${esc(q.videoId)}">${k === 0 && cur ? `▶ ${fmt(curPos())}` : `ต่อไป ${k}`} · ${esc(String(q.title).slice(0, 26))}</button>`).join('')}</div>
    ${moved ? `<div class="notice">เพลงเปลี่ยนแล้ว แต่คุณยังแก้เพลงนี้ค้างอยู่ <button class="btn tiny" data-now="${esc(cur.videoId)}">ไปเพลงที่เล่นอยู่</button></div>` : ''}
    ${headHtml(e)}${editorHtml(e, { preview: false })}`;
  restore(host, c);
  markNowLine();
}
function drawLib() {
  if (S.view !== 'lib') return;
  drawSongList();
  const host = $('#libedit');
  if (!S.libVid) { host.innerHTML = '<div class="empty"><h1>เลือกเพลงทางซ้าย</h1><p>เปลี่ยนแหล่งเนื้อ แก้ข้อความ หรือโหลดวิดีโอใหม่ได้เลย</p></div>'; return; }
  const e = ed(S.libVid);
  const c = capture(host);
  const video = $('video', host);
  const keep = video && video.dataset.vid === e.vid ? { t: video.currentTime, playing: !video.paused } : null;
  host.innerHTML = headHtml(e) + editorHtml(e, { preview: true });
  const v = $('video', host);
  if (v) {
    v.dataset.vid = e.vid;
    if (keep) { v.currentTime = keep.t; if (keep.playing) v.play().catch(() => {}); }
  }
  restore(host, c);
}
function drawSongList() {
  const rows = S.songs.filter((i) => FILTERS.find((f) => f[0] === S.filter)[2](i))
    .filter((i) => !S.q || `${i.title} ${i.channel} ${i.videoId}`.toLowerCase().includes(S.q));
  $('#filters').innerHTML = FILTERS.map(([k, t, fn]) => `<button data-f="${k}" aria-pressed="${k === S.filter}">${t} ${S.songs.filter(fn).length}</button>`).join('');
  const state = (i) => (i.reports ? `แขกแจ้ง ${i.reports}` : !i.lyrLines ? 'ไม่มีเนื้อ' : i.lyrConf === 'bad' ? 'เนื้อไม่ตรง' : i.lyrConf === 'sparse' ? 'เนื้อไม่ครบ' : i.fix ? 'ต้องซ่อม' : 'ปกติ');
  const box = $('#songs');
  const top = box.scrollTop;
  box.innerHTML = rows.map((i) => `<button class="song" data-song="${esc(i.videoId)}" aria-current="${i.videoId === S.libVid}"><b>${esc(i.title)}</b><span>${esc(state(i))}${i.channel ? ` · ${esc(i.channel)}` : ''}</span></button>`).join('')
    || '<p class="muted small" style="padding:10px">ไม่มีเพลงในหมวดนี้</p>';
  box.scrollTop = top;
}

/* ===== เวลาเพลงสด ===== */
const curPos = () => (S.room?.playing ? S.pos + (performance.now() - S.posAt) / 1000 : S.pos);
function markNowLine() {
  if (S.view !== 'now' || S.room?.current?.videoId !== S.nowVid) return;
  const e = ed(S.nowVid);
  const t = curPos() - (e.detail?.offset || 0);
  let on = -1;
  e.lines.forEach((l, k) => { if (l.t != null && l.t <= t) on = k; });
  for (const row of $$('#now .line')) {
    const active = +row.dataset.k === on;
    if (active && !row.classList.contains('now') && !isDirty(e)) row.scrollIntoView({ block: 'nearest' });
    row.classList.toggle('now', active);
  }
  const b = $('#now [data-now] ');
  if (b) b.firstChild.textContent = `▶ ${fmt(curPos())} · ${String(S.room.current.title).slice(0, 26)}`;
}
setInterval(markNowLine, 500);
function tickPreview() {
  const v = S.view === 'lib' ? $('#libedit video') : null;
  if (v) {
    const e = ed(S.libVid);
    const lines = e.trial?.lines || e.lines;
    const off = e.trial ? 0 : e.detail?.offset || 0;
    const t = v.currentTime - off;
    const l = lines.find((x) => x.t != null && t >= x.t && t < x.t + (x.d || 3));
    const sub = $('#libedit .sub');
    if (sub && sub.textContent !== (l?.x || '')) sub.textContent = l?.x || '';
  }
  requestAnimationFrame(tickPreview);
}
tickPreview();

/* ===== แท็บ + เหตุการณ์ ===== */
function setView(v) {
  S.view = v;
  for (const [k] of TABS) {
    $(`#${k}`).hidden = k !== v;
    $(`#tabs [data-v="${k}"]`).setAttribute('aria-selected', k === v);
  }
  if (v !== 'lib') $('#libedit video')?.pause();
  const lazy = { cut: '/studio/old?view=cut&embed=1', screen: `/tvset?theme=${document.documentElement.dataset.theme}` }[v];
  if (lazy && !$(`#${v} iframe`)) {
    const f = document.createElement('iframe');
    f.src = lazy;
    f.title = TABS.find((t) => t[0] === v)[1];
    $(`#${v}`).append(f);
  }
  if (v === 'lib' && !S.songs.length) loadSongs();
  try { localStorage.setItem('studioNewView', v); } catch { /* จำไม่ได้ก็เปิดหน้าแรก */ }
  drawEditors();
}
$('#tabs').innerHTML = TABS.map(([k, t, ic]) => `<button role="tab" data-v="${k}">${icon(ic)}${t}</button>`).join('');
$('#tabs').onclick = (e) => { const b = e.target.closest('[data-v]'); if (b) setView(b.dataset.v); };
document.addEventListener('click', (ev) => {
  const song = ev.target.closest('[data-song]');
  if (song) { S.libVid = song.dataset.song; openEd(S.libVid); drawEditors(); return; }
  const now = ev.target.closest('[data-now]');
  if (now) { S.nowVid = now.dataset.now; openEd(S.nowVid); drawEditors(); return; }
  const f = ev.target.closest('[data-f]');
  if (f) { S.filter = f.dataset.f; S.filterTouched = true; drawSongList(); return; }
  const a = ev.target.closest('[data-a]');
  if (!a) return;
  const vid = a.closest('#now') ? S.nowVid : S.libVid;
  if (vid) ACT[a.dataset.a](ed(vid), a.dataset.v);
});
document.addEventListener('input', (ev) => {
  if (ev.target.id === 'q') { S.q = ev.target.value.trim().toLowerCase(); drawSongList(); return; }
  if (!ev.target.matches('.line input')) return;
  const host = ev.target.closest('#now') ? S.nowVid : S.libVid;
  const e = ed(host);
  e.lines[+ev.target.dataset.k].x = ev.target.value;
  const root = ev.target.closest('.card');
  const save = $('[data-a=save]', root);
  if (save) save.disabled = !isDirty(e) || !!e.busy;
});

async function loadSongs() {
  try {
    S.songs = (await api('/api/studio/songs')).songs || [];
    // เปิดครั้งแรกถ้าไม่มีเพลงต้องแก้ แสดงทั้งคลังแทนหน้าว่าง
    if (!S.filterTouched && S.filter === 'fix' && !S.songs.some(FILTERS[0][2])) S.filter = 'all';
    drawLib();
  } catch { /* แจ้งผ่านกล่อง PIN แล้ว */ }
}

// เพลงที่เปิดอยู่ถูกเปลี่ยนเนื้อจากทางอื่น เช่นงานอัตโนมัติ: โหลดใหม่เมื่อยังไม่ได้แก้ค้าง
async function followLyrics() {
  for (const q of [S.room?.current, ...(S.room?.queue || [])]) {
    const e = q?.videoId && S.eds.get(q.videoId);
    if (e?.detail && q.lyricsUrl && q.lyricsUrl !== e.loadedUrl && !isDirty(e)) {
      e.loadedUrl = q.lyricsUrl;
      e.saved = '';
      await loadDetail(e).catch(() => {});
      drawEditors();
    }
  }
}
let lastRev = null;
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { document.body.classList.remove('off'); $('#conn').textContent = 'เชื่อมต่อแล้ว'; };
  ws.onmessage = (m) => {
    let st;
    try { st = JSON.parse(m.data); } catch { return; }
    if (st.type !== 'state') return;
    const prevCur = S.room?.current?.videoId;
    const curVid = st.current?.videoId;
    S.room = st;
    S.pos = st.position || 0;
    S.posAt = performance.now();
    if (curVid !== prevCur || !S.nowVid) {
      // เพลงเปลี่ยน: ตามไปเพลงใหม่ เว้นแต่ยังแก้เพลงเดิมค้าง งานจะได้ไม่หาย
      const stay = S.nowVid && isDirty(ed(S.nowVid));
      if (!stay) S.nowVid = curVid || st.queue?.[0]?.videoId || null;
      if (S.nowVid) openEd(S.nowVid);
      drawNow();
    }
    followLyrics();
    if (st.archiveRev !== lastRev) { lastRev = st.archiveRev; if (S.view === 'lib') loadSongs(); }
  };
  ws.onclose = () => { document.body.classList.add('off'); $('#conn').textContent = 'กำลังเชื่อมต่อใหม่…'; setTimeout(connect, 2000); };
  ws.onerror = () => { try { ws.close(); } catch { /* ปิดอยู่แล้ว */ } };
}

// ธีมมาจากหน้าที่ฝังอยู่: ?theme= ตอนเปิด, postMessage ตอนผู้ใช้เปลี่ยนธีมในแอป
const THEME_IDS = ['peach', 'mint', 'lavender', 'sweetnight', 'classic'];
const setTheme = (id) => { if (THEME_IDS.includes(id)) document.documentElement.dataset.theme = id; };
setTheme(params.get('theme') || 'classic');
window.addEventListener('message', (e) => {
  if (e.source !== window.parent || e.data?.type !== 'kara-theme') return;
  setTheme(e.data.theme);
  $('#screen iframe')?.contentWindow.postMessage(e.data, location.origin);
});
if (params.get('embed')) document.body.classList.add('embed');

let startView = params.get('view');
if (!startView) { try { startView = localStorage.getItem('studioNewView'); } catch { /* ใช้หน้าแรก */ } }
setView(TABS.some((t) => t[0] === startView) ? startView : 'now');
connect();
loadSongs();
