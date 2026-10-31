// หน้าหลักของแอป: วาดจากสถานะที่โปรเซสหลักส่งมา · Studio รีโมท และตั้งค่าจอทีวีเป็นหน้าจริงจากเซิร์ฟเวอร์ใน iframe
const $ = (q, el = document) => el.querySelector(q);
const $$ = (q, el = document) => [...el.querySelectorAll(q)];
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const page = $('#page');
const act = (name, arg) => window.kara.do(name, arg);

const SERVER_TEXT = {
  boot: ['กำลังเตรียมระบบ…', 'wait'],
  off: ['โหมดเฉพาะเครื่องนี้', ''],
  starting: ['กำลังเปิดเซิร์ฟเวอร์…', 'wait'],
  on: ['เซิร์ฟเวอร์เปิดอยู่', 'ok'],
  stopping: ['กำลังปิดเซิร์ฟเวอร์…', 'wait'],
  restarting: ['กำลังเปิดใหม่อัตโนมัติ…', 'wait'],
  crashed: ['เซิร์ฟเวอร์ล่ม', 'bad'],
};
const SET_SECTIONS = [['tv', 'จอทีวี', 'tv'], ['system', 'ระบบ', 'system'], ['network', 'เครือข่าย', 'network'], ['python', 'โหมด Python', 'python'], ['theme', 'ธีม', 'theme']];

const ui = { tab: 'home', setSection: 'tv', pageKey: null, faMode: null, frames: {} };
let S = null;

function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove('show'), 2400);
}

const blocked = () => S.portBlockedBy || S.projectError;
const canStart = () => ['off', 'crashed'].includes(S.server) && !blocked();
function powerProps(btn) {
  btn.textContent = S.server === 'on' ? 'ปิดเซิร์ฟเวอร์' : S.server === 'crashed' ? 'เปิดอีกครั้ง' : S.server === 'off' ? 'เปิดเซิร์ฟเวอร์' : SERVER_TEXT[S.server][0];
  btn.classList.toggle('stop', S.server === 'on');
  btn.disabled = !(S.server === 'on' || canStart());
}
const onPower = () => act(S.server === 'on' ? 'server:stop' : 'server:start');

/* ===== หน้าจริงจากเซิร์ฟเวอร์: สร้างครั้งเดียวแล้วซ่อน/แสดง งานที่แก้ค้างใน Studio จึงไม่หายตอนสลับแท็บ ===== */
function frame(name, src, title) {
  let f = ui.frames[name];
  if (!f) {
    f = document.createElement('iframe');
    f.title = title;
    f.src = src;
    f.dataset.frame = name;
    $('#frames').append(f);
    ui.frames[name] = f;
  }
  return f;
}
function dropFrame(name) {
  ui.frames[name]?.remove();
  delete ui.frames[name];
}
function syncFrames() {
  const box = $('#frames');
  let show = null;
  if (S.ready && !blocked()) {
    if (ui.tab === 'studio') show = frame('studio', `${S.base}/studio`, 'Studio');
    if (ui.tab === 'remote' && S.server === 'on') show = frame('remote', `${S.base}/r`, 'รีโมท');
    if (ui.tab === 'settings' && ui.setSection === 'tv') show = frame('tvset', `${S.base}/tvset?theme=${document.documentElement.dataset.theme}`, 'ตั้งค่าจอทีวี');
  }
  if (S.server !== 'on') dropFrame('remote');
  for (const f of Object.values(ui.frames)) f.hidden = f !== show;
  box.classList.toggle('active', !!show);
  box.classList.toggle('below-nav', ui.tab === 'settings');
  // หน้าจริงเริ่มใต้แถบที่เห็นอยู่ ความสูงเปลี่ยนตามป้ายแจ้งเตือน
  const above = (ui.tab === 'settings' && $('.setnav')) || ($('#notice').children.length ? $('#notice') : $('.tabs'));
  box.style.top = `${above.getBoundingClientRect().bottom + (above.matches('.tabs') ? 0 : 8)}px`;
  page.classList.toggle('behind', !!show && ui.tab !== 'settings');
}

/* ===== หัว แท็บ ป้ายแจ้งเตือน ===== */
function renderChrome() {
  const [text, cls] = SERVER_TEXT[S.server];
  const label = blocked() ? 'ยังใช้งานไม่ได้' : S.server === 'boot' ? S.bootText : text;
  $('#status').innerHTML = `<span class="dot ${blocked() ? 'bad' : cls}"></span>${esc(label)}`;
  powerProps($('#power'));
  const unlocked = S.server === 'on';
  for (const b of $$('.tabs button')) {
    const t = b.dataset.tab;
    b.setAttribute('aria-selected', t === ui.tab);
    const lock = (t === 'remote' || t === 'tv') && !unlocked;
    b.innerHTML = `${icon(b.dataset.icon)}<span>${esc(b.dataset.label)}</span>${lock ? `<span class="lock" role="img" aria-label="ล็อกอยู่">${icon('lock')}</span>` : ''}`;
  }
  const box = $('#notice');
  if (S.projectError) {
    box.innerHTML = `<div class="notice bad"><div class="grow"><b>${esc(S.projectError)}</b><span>เลือกโฟลเดอร์ PU KARAOKE ที่ถูกต้อง</span></div><button class="btn" id="pickproject">เลือกโฟลเดอร์</button></div>`;
    $('#pickproject').onclick = () => act('project:choose');
  } else if (S.portBlockedBy) {
    box.innerHTML = `<div class="notice bad"><div class="grow"><b>พอร์ต ${S.port} ถูกโปรแกรมอื่นใช้อยู่: ${esc(S.portBlockedBy)}</b><span>แอปจะไม่ปิดโปรแกรมนั้นให้ ปิดโปรแกรมนั้นเองแล้วกดลองใหม่</span></div><button class="btn" id="retry">ลองใหม่</button></div>`;
    $('#retry').onclick = () => act('server:retry');
  } else if (S.notice) {
    const n = S.notice;
    box.innerHTML = `<div class="notice ${esc(n.kind)}"><div class="grow"><b>${esc(n.title)}</b><span>${esc(n.text)}</span></div>
      ${n.log ? '<button class="btn" id="showlog">ดูบันทึก</button>' : ''}<button class="btn" id="dismiss">ปิด</button></div>`;
    $('#dismiss').onclick = () => act('notice:clear');
    if (n.log) $('#showlog').onclick = () => act('log:show');
  } else {
    box.innerHTML = '';
  }
}

/* ===== หน้าแรก ===== */
const displayOptions = () => [['auto', 'อัตโนมัติ (จอนอกก่อน)'], ...S.displays.map((d) => [d.id, `${d.label} · ${d.size}${d.internal ? ' · MacBook' : ''}`])];
const displaySelect = (id) => `<select id="${id}" style="width:100%;margin-top:4px">${displayOptions().map(([v, t]) => `<option value="${esc(v)}" ${v === S.displayId ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
function tunnelText() {
  if (S.tunnelBusy) return 'กำลังเปิดลิงก์…';
  if (!S.tunnel) return 'ปิดอยู่ เข้าได้เฉพาะ Wi-Fi เดียวกัน';
  return S.server === 'on' ? 'เปิดอยู่ คนที่มีลิงก์เข้าได้จากนอกบ้าน' : 'จะเปิดพร้อมเซิร์ฟเวอร์';
}
function homeHtml() {
  const on = S.server === 'on';
  const cap = (ok, title, text) => `<div class="cap"><span class="dot ${ok ? 'ok' : ''}"></span><div><b>${esc(title)}</b><span>${esc(text)}</span></div></div>`;
  const hero = blocked() ? ['ยังเริ่มระบบไม่ได้', 'แก้ตามข้อความด้านบน แล้วลองอีกครั้ง'] : {
    boot: ['กำลังเตรียมระบบ', 'อีกสักครู่ก็แก้เนื้อและตั้งค่าได้'],
    off: ['พร้อมตั้งค่า แต่แขกยังเข้าไม่ได้', 'แก้เนื้อและตั้งค่าได้เลย กดเปิดเซิร์ฟเวอร์เมื่อพร้อมร้อง'],
    starting: ['กำลังเปิดเซิร์ฟเวอร์', 'อีกครู่จอทีวีจะเปิดเต็มจอโดยอัตโนมัติ'],
    on: ['พร้อมร้องแล้ว', 'แขกสแกน QR สั่งเพลงได้เลย'],
    stopping: ['กำลังปิดเซิร์ฟเวอร์', 'จอทีวีและการเชื่อมต่อของแขกกำลังถูกปิด'],
    restarting: ['เซิร์ฟเวอร์กำลังกลับมา', 'แอปกำลังเปิดใหม่ให้อัตโนมัติ'],
    crashed: ['เซิร์ฟเวอร์หยุดทำงาน', 'กดเปิดอีกครั้งเมื่อพร้อม หรือเปิดดูบันทึกเพื่อหาสาเหตุ'],
  }[S.server];
  const target = S.displays.find((d) => d.id === S.targetDisplayId);
  const link = S.urls.publicUrl ? `${S.urls.publicUrl}/r` : S.urls.remoteUrl;
  return `<div class="home">
    <section class="card hero"><div class="grow"><h1>${esc(hero[0])}</h1><p>${esc(hero[1])}</p></div><button class="power" id="heropower"></button></section>
    <section class="card"><h2>ตอนนี้ใช้อะไรได้บ้าง</h2><div class="caps">
      ${cap(S.ready, 'Studio', S.ready ? 'แก้เนื้อและงานที่กดสั่งเอง' : 'รอระบบพร้อม')}
      ${cap(S.ready, 'ตั้งค่า', S.ready ? 'ปรับได้ทุกค่า' : 'รอระบบพร้อม')}
      ${cap(on, 'รีโมทในแอป', on ? 'สั่งเพลงได้' : 'รอกดเปิดเซิร์ฟเวอร์')}
      ${cap(on, 'จอทีวี', S.tv.open ? 'เปิดอยู่' : on ? 'ปิดอยู่' : 'รอกดเปิดเซิร์ฟเวอร์')}
      ${cap(on, 'มือถือแขก', on ? 'เข้าได้ทาง QR' : 'ยังเข้าไม่ได้')}
      ${cap(on, 'งานอัตโนมัติ', on ? 'แยกเสียงและหาเนื้อตามคิว' : 'หยุดรอ เครื่องไม่ร้อน')}
      ${cap(S.sleepBlocked, 'กันเครื่องหลับ', S.sleepBlocked ? 'เปิดอยู่' : 'ปิดอยู่')}
    </div></section>
    <div class="stack">
      <section class="card"><h2>ให้แขกเข้าใช้</h2>
        <div class="qrbox ${on ? '' : 'off'}"><div class="qr">${S.ready ? `<img src="${esc(S.base)}/qr.png?v=${encodeURIComponent(link)}" alt="QR สั่งเพลง">` : ''}</div>
          <div><div class="link">${esc(link || '-')}</div><div class="muted small">${on ? 'สแกนด้วยมือถือ หรือเปิดลิงก์นี้' : 'ใช้ได้เมื่อเปิดเซิร์ฟเวอร์'}</div></div></div>
        <div class="split"><div><b>ลิงก์นอกบ้าน</b><div class="muted small">${esc(tunnelText())}</div></div>
          <label class="switch"><input id="tunnel" type="checkbox" aria-label="ลิงก์นอกบ้าน" ${S.tunnel ? 'checked' : ''} ${S.tunnelBusy ? 'disabled' : ''}><i></i></label></div>
      </section>
      <section class="card"><h2>จอทีวี</h2>
        <label class="muted small" for="disp">แสดงบนจอ</label>${displaySelect('disp')}
        <p class="muted small" style="margin-top:7px">จะเปิดบน: ${esc(target ? target.label : '-')} แบบเต็มจอ</p>
      </section>
    </div>
  </div>`;
}
function bindHome() {
  powerProps($('#heropower'));
  $('#heropower').onclick = onPower;
  $('#tunnel').onchange = (e) => act('tunnel:set', e.target.checked);
  $('#disp').onchange = (e) => act('tv:display', e.target.value);
}

/* ===== ล็อก / รอระบบ ===== */
function lockedHtml(title) {
  return `<div class="locked"><div class="ic">${icon('lock')}</div><h1>${esc(title)}ยังล็อกอยู่</h1>
    <p>กดเปิดเซิร์ฟเวอร์ก่อน ระหว่างนี้แก้เนื้อใน Studio และปรับตั้งค่าได้ตามปกติ</p><button class="power" id="lockpower"></button></div>`;
}
function bindLocked() {
  powerProps($('#lockpower'));
  $('#lockpower').onclick = onPower;
}
const waitingHtml = (title) => `<div class="locked"><h1>${esc(title)}</h1><p>${blocked() ? 'แก้ตามข้อความด้านบนก่อน' : 'รอระบบพร้อมสักครู่'}</p></div>`;

/* ===== จอทีวี ===== */
function tvHtml() {
  const state = !S.tv.open ? 'ปิดอยู่' : S.tv.fullscreen ? 'เปิดเต็มจอ' : 'เปิดเป็นหน้าต่าง';
  return `<div class="tvpage">
    <section class="card"><h2>หน้าต่างจอทีวี</h2>
      <p style="margin-bottom:10px"><span class="dot ${S.tv.open ? 'ok' : ''}" style="display:inline-block;margin-right:7px"></span>${esc(state)}</p>
      <label class="muted small" for="tvdisp">แสดงบนจอ</label>${displaySelect('tvdisp')}
      <div class="btns">${S.tv.open ? `<button class="btn" id="tvshow">ไปที่จอทีวี</button><button class="btn" id="tvclose">ปิดจอทีวี</button>` : '<button class="btn primary" id="tvopen">เปิดจอทีวี</button>'}</div>
      <p class="muted small" style="margin-top:10px">บน MacBook จอเดียว ปัดสามนิ้วหรือกด ⌘1 เพื่อกลับมาแอป เพลงยังเล่นต่อ กด Esc ออกจากเต็มจอ</p>
    </section>
    <section class="card"><h2>ใช้ iPad หรือทีวีเป็นจอ</h2>
      <p class="link">${esc(S.urls.tvUrl || '-')}</p>
      <p class="muted small" style="margin-top:6px">เปิดลิงก์นี้บนอุปกรณ์ในบ้าน จอที่เปิดล่าสุดจะเป็นจอหลัก และจอเดิมจะหลุด</p>
      <div class="warn" style="margin-top:12px">การกดเปิดเซิร์ฟเวอร์จะเปิดจอในแอปอัตโนมัติ และแทนที่ iPad ที่เป็นจอหลักอยู่ เปิดลิงก์บน iPad อีกครั้งเพื่อยึดจอกลับ</div>
    </section>
  </div>`;
}
function bindTv() {
  $('#tvdisp').onchange = (e) => act('tv:display', e.target.value);
  if (S.tv.open) {
    $('#tvshow').onclick = () => act('tv:show');
    $('#tvclose').onclick = () => act('tv:close');
  } else {
    $('#tvopen').onclick = () => act('tv:open');
  }
}

/* ===== ตั้งค่า ===== */
function themeHtml() {
  const cur = document.documentElement.dataset.theme;
  return `<section class="card"><h2>เลือกธีมของแอป</h2>
    <div class="themes">${THEMES.map((t) => `<button class="theme" data-theme-id="${t.id}" aria-pressed="${t.id === cur}">
      <div class="theme-mock" style="background:${t.c[0]}"><i style="background:${t.c[1]}"></i><u style="background:linear-gradient(135deg,${t.c[2]},${t.c[3]})"></u></div>
      ${t.id === cur ? '<em>✓ ใช้อยู่</em>' : ''}<b>${esc(t.name)}</b><span>${esc(t.desc)}</span></button>`).join('')}</div>
    <p class="muted small" style="margin-top:12px">ธีมเปลี่ยนเฉพาะหน้าต่างแอป ไม่กระทบภาพบนจอทีวี แอปจะจำธีมที่เลือกไว้</p></section>`;
}
function settingsBody() {
  if (ui.setSection === 'tv') return S.ready && !blocked() ? '' : waitingHtml('รอระบบพร้อม');
  if (ui.setSection === 'theme') return themeHtml();
  if (ui.setSection === 'system') return `<section class="card"><h2>การเข้าใช้งาน</h2>
    <div class="field"><div class="lbl"><label for="pin">PIN ของ Studio</label><small>ใช้เมื่อเปิด Studio จากเครื่องอื่น แอปบนเครื่องนี้เข้าได้เลย เปลี่ยนแล้วเครื่องอื่นต้องใส่ใหม่</small></div>
      <div class="ctl"><input id="pin" type="password" inputmode="numeric" maxlength="8" autocomplete="off"><button class="btn" id="pinshow">แสดง</button><button class="btn primary" id="pinsave">บันทึก</button></div></div>
    <div class="field"><div class="lbl">พอร์ตเซิร์ฟเวอร์</div><div class="ctl"><b>${S.port}</b></div></div>
    <div class="field"><div class="lbl">โฟลเดอร์โปรเจกต์<small>เพลง เนื้อ และค่าต่าง ๆ อยู่ที่นี่</small></div><div class="ctl"><span class="muted small path">${esc(S.project)}</span><button class="btn" id="project">เปลี่ยน</button></div></div></section>
    <section class="card"><h2>พฤติกรรมของแอป</h2>
      <div class="field"><div class="lbl">เปิดจอทีวีเมื่อเปิดเซิร์ฟเวอร์</div><div class="ctl"><b>อัตโนมัติ เต็มจอ</b></div></div>
      <div class="field"><div class="lbl">กันเครื่องหลับ</div><div class="ctl"><b>เฉพาะตอนเซิร์ฟเวอร์เปิด</b></div></div>
      <div class="field"><div class="lbl">เมื่อเซิร์ฟเวอร์ล่ม</div><div class="ctl"><b>เปิดใหม่เองไม่เกิน 2 ครั้ง</b></div></div>
      <div class="field"><div class="lbl">บันทึกเซิร์ฟเวอร์</div><div class="ctl"><button class="btn" id="showlog2">ดูบันทึก</button></div></div></section>`;
  if (ui.setSection === 'network') return `<section class="card"><h2>การเข้าถึง</h2>
    <div class="field"><div class="lbl"><label for="tunnel2">ลิงก์นอกบ้าน (Cloudflare)</label><small>${esc(tunnelText())} ค่าเริ่มต้นคือเปิดพร้อมเซิร์ฟเวอร์ ถ้าปิดสวิตช์ แอปจะจำไว้</small></div><div class="ctl"><label class="switch"><input id="tunnel2" type="checkbox" ${S.tunnel ? 'checked' : ''} ${S.tunnelBusy ? 'disabled' : ''}><i></i></label></div></div>
    <div class="field"><div class="lbl">ลิงก์รีโมท</div><div class="ctl"><span class="muted small path">${esc(S.urls.remoteUrl || '-')}</span></div></div>
    <div class="field"><div class="lbl">ลิงก์จอหลักสำหรับ iPad หรือทีวี</div><div class="ctl"><span class="muted small path">${esc(S.urls.tvUrl || '-')}</span></div></div>
    <div class="field"><div class="lbl">ลิงก์นอกบ้าน</div><div class="ctl"><span class="muted small path">${esc(S.urls.publicUrl || 'ปิดอยู่')}</span></div></div></section>`;
  const opt = (m, t, d) => `<label class="radio"><input type="radio" name="fa" value="${m}" ${ui.faMode === m ? 'checked' : ''} ${S.ready ? '' : 'disabled'}><span><b>${t}</b><small>${d}</small></span></label>`;
  return `<section class="card"><h2>โหมด Python รอจับเวลาเนื้อ</h2>
    ${opt('keep', 'ค้างตลอด', 'จับเวลาเนื้อเริ่มเร็วที่สุด แต่ใช้แรมตลอด')}
    ${opt('idle', 'ปิดเองเมื่อว่าง', 'เก็บไว้ช่วงหนึ่งแล้วปิดเมื่อไม่มีงาน')}
    ${opt('off', 'ไม่ค้าง', 'โหลดเมื่อมีงานแล้วปิด ประหยัดแรมที่สุด แต่เริ่มช้ากว่า')}
  </section>`;
}
function settingsHtml() {
  return `<div class="settings">
    <nav class="setnav" aria-label="หมวดตั้งค่า">${SET_SECTIONS.map(([k, t, ic]) => `<button data-sec="${k}" aria-pressed="${k === ui.setSection}">${icon(ic)}${esc(t)}</button>`).join('')}</nav>
    <div class="setbody">${settingsBody()}</div></div>`;
}
function bindSettings() {
  for (const b of $$('[data-sec]')) b.onclick = () => { ui.setSection = b.dataset.sec; renderPage(true); syncFrames(); };
  for (const b of $$('[data-theme-id]')) {
    b.onclick = () => {
      applyTheme(b.dataset.themeId);
      ui.frames.tvset?.contentWindow.postMessage({ type: 'kara-theme', theme: b.dataset.themeId }, S.base);
      renderPage(true);
    };
  }
  const t = $('#tunnel2');
  if (t) t.onchange = () => act('tunnel:set', t.checked);
  if ($('#project')) {
    $('#project').onclick = () => act('project:choose');
    $('#showlog2').onclick = () => act('log:show');
    const pin = $('#pin');
    act('pin:get').then((v) => { pin.value = v; });
    $('#pinshow').onclick = () => {
      pin.type = pin.type === 'password' ? 'text' : 'password';
      $('#pinshow').textContent = pin.type === 'password' ? 'แสดง' : 'ซ่อน';
    };
    $('#pinsave').onclick = async () => {
      try { await act('pin:set', pin.value); toast('บันทึก PIN แล้ว'); } catch (e) { toast(String(e.message).replace(/^.*Error: /, '')); }
    };
  }
  for (const r of $$('input[name=fa]')) {
    r.onchange = async () => {
      ui.faMode = r.value;
      try { await act('fa:set', r.value); toast('บันทึกแล้ว'); } catch { toast('บันทึกไม่ได้ ลองอีกครั้ง'); }
    };
  }
  if (ui.setSection === 'python' && S.ready && !ui.faMode) {
    act('fa:get').then((fa) => { ui.faMode = fa?.mode ?? 'keep'; renderPage(true); }).catch(() => {});
  }
}

/* ===== วาดหน้า ===== */
const PAGE_KEYS = {
  home: () => [S.server, S.ready, S.tunnel, S.tunnelBusy, S.displayId, S.displays, S.targetDisplayId, S.tv, S.urls, S.sleepBlocked, blocked()],
  studio: () => [S.ready, blocked()],
  remote: () => [S.server, S.ready, blocked()],
  tv: () => [S.server, S.tv, S.displayId, S.displays, S.urls],
  settings: () => (ui.setSection === 'system' ? [S.ready, S.project] : [S.tunnel, S.tunnelBusy, S.urls, S.ready, blocked(), ui.setSection]),
};
function renderPage(force = false) {
  const key = JSON.stringify([ui.tab, PAGE_KEYS[ui.tab]()]);
  if (!force && key === ui.pageKey) return;
  ui.pageKey = key;
  if (ui.tab === 'home') { page.innerHTML = homeHtml(); bindHome(); return; }
  if (ui.tab === 'settings') { page.innerHTML = settingsHtml(); bindSettings(); return; }
  if (ui.tab === 'studio') { page.innerHTML = S.ready && !blocked() ? '' : waitingHtml('รอระบบพร้อม'); return; }
  if (S.server !== 'on') { page.innerHTML = lockedHtml(ui.tab === 'remote' ? 'รีโมท' : 'จอทีวี'); bindLocked(); return; }
  if (ui.tab === 'remote') { page.innerHTML = ''; return; }
  page.innerHTML = tvHtml();
  bindTv();
}
function go(tab) {
  ui.tab = tab;
  renderChrome();
  renderPage(true);
  syncFrames();
  page.scrollTop = 0;
}
function onState(s) {
  S = s;
  renderChrome();
  renderPage();
  syncFrames();
}
for (const b of $$('.tabs button')) b.onclick = () => go(b.dataset.tab);
$('#power').onclick = onPower;
window.kara.on(onState);
window.kara.get().then(onState);
