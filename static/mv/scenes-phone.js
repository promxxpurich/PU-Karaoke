// ===== คลังฉาก: ตระกูล "มือถือ / ความทรงจำ / เมือง" (ต้นแบบจาก MV ไม่รักดีกว่า) =====
// เหมาะกับเพลงป๊อป/แร็ป/อกหัก ที่มีภาพนิ่งจากคลิปเป็นรูปคน — ตั้งธีมมืด (bg ดำ) จะเข้ากันที่สุด
(() => {
  const def = MVScenes.def;
  const pad2 = n => String(n).padStart(2, '0');

  def('lockscreen', {
    doc: 'ฉากเปิด: หน้าจอล็อกมือถือ วอลเปเปอร์เป็นรูป + แจ้งเตือนเด้ง (ชื่อเพลง/ข้อความ) + นับถอยหลังก่อนเข้าเนื้อ',
    params: { img: 'รูปวอลเปเปอร์', time: 'เวลาบนจอ เช่น "23:14"', date: 'วันที่', notes: '[{title, body, img?}] แจ้งเตือน (ค่าเริ่มต้น = ชื่อเพลง)' },
    draw(c, t, X){
      const { M, D, th, W, H, P, fx, meta } = X, { clamp, ease } = M;
      c.drawImage(fx(P.img, 'blur'), 0, 0);
      const x = W / 2 - 330, y = 40, w = 660, h = H - 80;
      c.save(); c.beginPath(); c.roundRect(x, y, w, h, 52); c.clip(); c.drawImage(fx(P.img, 'fit', w, h), x, y);
      c.fillStyle = 'rgba(0,0,0,.35)'; c.fillRect(x, y, w, h); c.restore();
      D.phone(c, x, y, w, h, 'rgba(0,0,0,0)');
      D.txt(c, D.F('thin', 34), '#fff', P.date || 'วันนี้', W / 2, y + 150);
      D.txt(c, D.F('ui', 170), '#fff', P.time || '23:14', W / 2, y + 320);
      const notes = P.notes || [{ title: meta.artist || '♪', body: (meta.title || '') + ' · กำลังเล่น' }];
      notes.forEach((n, k) => {
        const e = ease.back(clamp((t - 1.5 - k * 3.5) / .5)); if(e <= 0) return;
        const ny = y + 420 + k * 150; c.save(); c.globalAlpha = clamp(e); c.translate(0, (1 - e) * -60);
        c.fillStyle = 'rgba(40,40,48,.78)'; c.beginPath(); c.roundRect(x + 30, ny, w - 60, 126, 30); c.fill();
        if(n.img) D.avatar(c, fx(n.img, 'fit', 72, 72), x + 92, ny + 63, 36);
        else { c.fillStyle = X.acc; c.beginPath(); c.roundRect(x + 56, ny + 27, 72, 72, 18); c.fill(); D.txt(c, D.F('body', 44), '#fff', '♪', x + 92, ny + 79); }
        D.txt(c, D.F('bold', 36), '#fff', n.title || '', x + 150, ny + 56, { align: 'left' });
        D.txt(c, D.F('thin', 32), 'rgba(255,255,255,.8)', n.body || '', x + 150, ny + 100, { align: 'left' }); c.restore(); });
      const sw = clamp((t - (X.Lc.t0 - 1.2)) / 1);
      D.txt(c, D.F('thin', 28), 'rgba(255,255,255,.75)', 'ปัดขึ้นเพื่อเปิด', W / 2, y + h - 70 - sw * 40);
      c.fillStyle = 'rgba(255,255,255,.8)'; c.beginPath(); c.roundRect(W / 2 - 90, y + h - 40 - sw * 40, 180, 10, 5); c.fill();
      D.countdown(c, t, X.Lc, '#fff', y + h - 160);
    },
  });

  def('tear', {
    doc: 'รูปคู่ในโพลารอยด์ถูกฉีกครึ่งตรงคำที่กำหนด ครึ่งขวาลอยหายไป — "กลับไปอยู่กับเขา", "แยกทาง", "เลิกกัน"',
    params: { img: 'รูปคู่/รูปสองคน', word: 'คำที่ฉีก (regex)', acc: 'สีเน้น' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, { clamp, ease } = M;
      const tt = D.trig(Lc, P.word, .55).t, tp = clamp((t - tt) / .45), sl = ease.inOut(clamp((t - tt - .45) / 1.1));
      c.fillStyle = th.bg; c.fillRect(0, 0, W, H);
      const g = c.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, 900); g.addColorStop(0, acc + '33'); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(0, 0, W, H);
      const pw = 640, ph = 720, px = W / 2, py = 470, img = X.fx(P.img, 'fit', pw, ph);
      const cut = [[0, -ph / 2 - 20], [-30, -200], [24, -60], [-18, 80], [30, 220], [0, ph / 2 + 90]];
      const half = side => {
        c.save(); c.translate(px + (side > 0 ? sl * 520 : -sl * 60), py + (side > 0 ? sl * 80 : 0)); c.rotate(side > 0 ? sl * .32 : -sl * .05);
        if(tp > 0){ c.beginPath(); c.moveTo(side * 800, -800); for(const q of cut) c.lineTo(q[0], q[1]); c.lineTo(side * 800, 800); c.closePath(); c.clip(); }
        c.globalAlpha = side > 0 ? 1 - sl * .6 : 1; D.polaroid(c, img, 0, 0, pw, ph, -.03); c.restore();
      };
      if(tp > 0){ half(-1); half(1); } else half(-1);
      D.tape(c, px - 250, py - ph / 2 - 10, -.3);
      if(tp > 0 && sl < .2) D.marker(c, cut.map(q => [px + q[0], py + q[1]]), tp, acc, 8);
      D.lower(c, Lc, t, acc, H - 140, 80);
    },
  });

  def('chat', {
    doc: 'หน้าจอแชตในมือถือ: บรรทัดก่อนหน้าเป็นข้อความฝั่งเรา (ฟ้า) บรรทัดนี้คือข้อความอีกฝ่าย ขึ้น "กำลังพิมพ์…" ก่อน — ประโยคที่เหมือนบทสนทนา/คำพูดของอีกฝ่าย',
    params: { avatar: 'รูปอีกฝ่าย', name: 'ชื่อในแชต (ค่าเริ่มต้น "เธอ")', acc: 'สีตัวหนังสือ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc, L } = X, { clamp, ease } = M, prev = L[Lc.i - 1];
      c.drawImage(X.fx(P.avatar, 'blur'), 0, 0);
      const x = W / 2 - 360, y = 40, w = 720, h = H - 80; D.phone(c, x, y, w, h);
      D.avatar(c, X.fx(P.avatar, 'fit', 88, 88, { fy: .3 }), x + 90, y + 120, 44);
      D.txt(c, D.F('body', 40), '#fff', P.name || 'เธอ', x + 160, y + 112, { align: 'left' });
      const typing = t < Lc.tSing0;
      D.txt(c, D.F('thin', 28), typing ? acc : th.grey, typing ? 'กำลังพิมพ์…' : 'ออนไลน์', x + 160, y + 150, { align: 'left' });
      c.fillStyle = '#26262e'; c.fillRect(x, y + 190, w, 2);
      if(prev){ const b = D.bubbleText(c, prev, 9999, 470, D.F('thin', 38), '#fff', '#fff');
        c.fillStyle = '#2563eb'; c.beginPath(); c.roundRect(x + w - b.w - 80, y + 240, b.w + 50, b.h + 36, 30); c.fill(); b.draw(x + w - b.w - 55, y + 258); }
      const by = y + 520;
      if(typing){ c.fillStyle = '#2a2a33'; c.beginPath(); c.roundRect(x + 40, by, 150, 80, 40); c.fill();
        for(let k = 0; k < 3; k++){ c.fillStyle = `rgba(255,255,255,${.4 + .6 * Math.max(0, Math.sin(t * 8 - k))})`; c.beginPath(); c.arc(x + 80 + k * 35, by + 40, 10, 0, 6.3); c.fill(); } }
      else { const pop = ease.back(clamp((t - Lc.tSing0) / .3)), b = D.bubbleText(c, Lc, t, 560, D.F('body', 54), 'rgba(255,255,255,.35)', acc);
        c.save(); c.translate(x + 40, by); c.scale(pop, pop); c.fillStyle = '#2a2a33'; c.beginPath(); c.roundRect(0, 0, b.w + 60, b.h + 44, 34); c.fill(); b.draw(30, 22); c.restore(); }
      D.txt(c, D.F('thin', 26), th.grey, 'อ่านแล้ว 23:' + pad2(40 + Math.floor(Lc.t0 / 60) % 20), x + w - 40, y + 470, { align: 'right' });
    },
  });

  def('doodle', {
    doc: 'รูปคนในโพลารอยด์เม็ดสกรีน แล้วปากกาวาดลายมือทับ (เขาปีศาจ/มงกุฎ/วงนางฟ้า/หัวใจ/น้ำตา/กากบาท) ตรงคำที่กำหนด ข้อความอยู่ขวา — "ปีศาจ", "นางฟ้า", "ราชา", "ร้องไห้"',
    params: { img: 'รูปคน (ตั้ง head [x,y] ในรูปที่ images)', kind: 'horns|crown|halo|heart|tears|x|scribble', word: 'คำเริ่มวาด (regex)', until: 'คำที่วาดเสร็จ (regex, ไม่ใส่ = +0.7 วิ)', acc: 'สีปากกา' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, { clamp } = M;
      const t0 = D.trig(Lc, P.word, .4).t, t1 = P.until ? D.trig(Lc, P.until, .9).t : t0 + .7, dp = clamp((t - t0) / Math.max(.3, t1 - t0 + .1));
      const glow = t > t1 ? Math.exp(-(t - t1) * 2) : 0;
      c.fillStyle = th.light ? th.paper : '#140308'; c.fillRect(0, 0, W, H);
      const g = c.createRadialGradient(560, H / 2, 0, 560, H / 2, 900); g.addColorStop(0, acc + (glow > .3 ? '88' : '40')); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(0, 0, W, H);
      const pw = 520, ph = 720, px = 560, py = 470, rot = -.05, [hxF, hyF] = X.head(P.img);
      c.save(); if(t > t1) D.kick(t1, 10); D.doShake(c, t);
      D.polaroid(c, X.fx(P.img, 'ht', pw, ph, { fy: hyF }), px, py, pw, ph, rot);
      c.save(); c.translate(px, py); c.rotate(rot);
      D.doodle(c, P.kind || 'horns', (hxF - .5) * pw, -ph / 2 + ph * Math.min(.45, hyF * .9), 1, dp, acc, 14);
      c.restore(); c.restore();
      c.font = D.F('big', 108);
      M.karaRows(c, Lc, t, { maxW: 820, lh: 130, cx: 1390, cy: H / 2 - 20, dim: th.light ? 'rgba(0,0,0,.25)' : 'rgba(255,255,255,.3)', on: th.light ? th.ink : '#fff', glow: t > t1 ? acc : null, glowB: 30 });
    },
  });

  def('slam', {
    doc: 'ตัวหนังสือยักษ์แบบกลิตช์ ทีละวลี (แบ่งตามช่องว่างในเนื้อ) — ท่อนฮุก/ชื่อเพลง/คำเด็ด',
    params: { acc: 'สีวลีที่สองเป็นต้นไป', label: 'ข้อความเล็กมุมซ้ายบน (ไม่ใส่ = ชื่อเพลง)' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc, meta } = X;
      const on = D.lastOn(Lc, t), amt = Math.exp(-(t - on) * 7);
      c.fillStyle = th.bg; c.fillRect(0, 0, W, H);
      const wi = Math.max(0, M.wordAt(Lc, t)); let a = wi, b = wi;
      while(a > 0 && !Lc.words[a - 1].gap) a--; while(b < Lc.words.length - 1 && !Lc.words[b].gap) b++;
      const phrase = Lc.words.slice(a, b + 1).map(w => w.s).join('');
      c.font = D.F('big', 320); const s = Math.min(1, 1700 / c.measureText(phrase).width) * (1 + amt * .06) * (1 + M.beat(t) * .03);
      c.save(); c.translate(W / 2, H / 2 - 60); c.scale(s, s); D.glitch(c, D.F('big', 320), phrase, 0, 0, amt, a > 0 ? acc : th.fg, Lc.i); c.restore();
      c.drawImage(scanOf(M), 0, 0);
      c.font = D.F('body', 58);
      M.karaText(c, Lc.text, W / 2, H - 170, M.sung(Lc, t), { align: 'center', dim: th.dim, on: acc });
      D.txt(c, D.F('ui', 30), th.grey, P.label || `${meta.artist} — ${meta.title}`, 90, 100, { align: 'left' });
    },
  });
  // เส้นสแกน CRT (แคชครั้งเดียว)
  let scanC = null;
  function scanOf(M){ if(!scanC){ scanC = M.canvas(); const g = scanC.getContext('2d'); g.fillStyle = 'rgba(0,0,0,.22)'; for(let y = 0; y < M.H; y += 4) g.fillRect(0, y, M.W, 2); } return scanC; }

  def('strip', {
    doc: 'แถบรูปตู้สติกเกอร์ 4 ช่อง เลื่อนขึ้น รูปที่กำหนดโดนกากบาท + ตราประทับ ข้อความอยู่ขวา — "ผิด", "ไม่ใช่", ความทรงจำคู่',
    params: { imgs: 'รูป 4 รูป', word: 'คำที่กากบาท (regex)', mark: 'ลำดับรูปที่โดนกากบาท 0–3', stamp: 'คำในตราประทับ (เช่น "ผิด")', acc: 'สีปากกา' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, { clamp } = M;
      const tw = D.trig(Lc, P.word, .5).t, xp = clamp((t - tw) / .5), p = D.lp(Lc, t);
      c.drawImage(paperOf(M, th.paper), 0, 0);
      const sx = 520, sw = 420, fh = 300, y0 = 60 - p * 180, ims = (P.imgs || [P.img, P.img, P.img, P.img]).slice(0, 4), mk = P.mark ?? 2;
      c.save(); c.translate(sx, 0); c.rotate(.04);
      c.fillStyle = 'rgba(0,0,0,.25)'; c.fillRect(-sw / 2 + 14, y0 + 14, sw, ims.length * (fh + 24) + 120);
      c.fillStyle = '#111'; c.fillRect(-sw / 2, y0, sw, ims.length * (fh + 24) + 120);
      ims.forEach((n, k) => { const yy = y0 + 24 + k * (fh + 24); c.drawImage(X.fx(n, 'fit', sw - 48, fh), -sw / 2 + 24, yy);
        if(k === mk && xp > 0){ D.marker(c, [[-130, yy + 40], [130, yy + fh - 40]], xp * 2, acc, 18); D.marker(c, [[130, yy + 40], [-130, yy + fh - 40]], xp * 2 - 1, acc, 18); } });
      D.txt(c, D.F('ui', 30), '#fff', P.caption || 'PHOTO ♥ BOOTH', 0, y0 + ims.length * (fh + 24) + 76);
      c.restore(); D.tape(c, sx - 120, 70, -.4); D.tape(c, sx + 140, 76, .3);
      if(xp >= 1 && P.stamp !== ''){ c.save(); c.translate(1640, 330); c.rotate(-.18); c.globalAlpha = .9; c.strokeStyle = acc; c.lineWidth = 10;
        c.beginPath(); c.roundRect(-150, -70, 300, 140, 18); c.stroke(); D.txt(c, D.F('big', 90), acc, P.stamp || 'ผิด', 0, 34); c.restore(); }
      c.font = D.F('big', 104);
      M.karaRows(c, Lc, t, { maxW: 900, lh: 130, cx: 1300, cy: H / 2 + 60, dim: 'rgba(17,17,20,.25)', on: th.ink });
    },
  });
  const paperCache = {};
  function paperOf(M, tint){ return paperCache[tint] ||= M.paper(tint); }

  def('spotlight', {
    doc: 'ห้องมืด ไฟสปอตไลต์ส่องรูปใบเดียวที่แขวนแกว่ง ฝุ่นลอย — "อยู่คนเดียว", "เหงา", "ไม่มีใคร"',
    params: { img: 'รูป (คนเดียว)', label: 'ข้อความเล็กใต้เนื้อ เช่น "1 คน"' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, sway = Math.sin(t * 1.3) * .06;
      c.fillStyle = '#050507'; c.fillRect(0, 0, W, H);
      c.save(); c.globalCompositeOperation = 'lighter';
      const g = c.createLinearGradient(W / 2, 0, W / 2, H); g.addColorStop(0, 'rgba(255,255,255,.22)'); g.addColorStop(1, 'rgba(255,255,255,.02)');
      c.fillStyle = g; c.beginPath(); c.moveTo(W / 2 - 60, 0); c.lineTo(W / 2 + 60, 0); c.lineTo(W / 2 + 520, H); c.lineTo(W / 2 - 520, H); c.closePath(); c.fill();
      const r = M.rng('dust'); for(let k = 0; k < 60; k++){ const x = W / 2 + (r() - .5) * 700 * r(), y = (r() * H + t * 20 * (r() + .2)) % H; c.fillStyle = 'rgba(255,255,255,.35)'; c.fillRect(x, y, 3, 3); }
      c.restore();
      c.save(); c.strokeStyle = '#555'; c.lineWidth = 2; c.beginPath(); c.moveTo(W / 2, 0); c.lineTo(W / 2 + Math.sin(sway) * 260, 180); c.stroke(); c.restore();
      c.save(); c.translate(W / 2, 0); c.rotate(sway); D.polaroid(c, X.fx(P.img, 'fit', 300, 400), 0, 380, 300, 400, 0); c.restore();
      c.font = D.F('body', 76);
      M.karaRows(c, Lc, t, { maxW: 1500, lh: 100, cy: H - 200, dim: 'rgba(255,255,255,.25)', on: '#fff' });
      if(P.label) D.txt(c, D.F('ui', 28), acc, P.label, W / 2, H - 90);
    },
  });

  def('stickerWall', {
    doc: 'กำแพงสติกเกอร์ลายมือ (หน้าปีศาจ/หัวใจ/ดาว) ค่อย ๆ เต็มจอ กระพริบตรงคำที่กำหนด — คำซ้ำ/ท่อนฮุกรอบสอง',
    params: { kind: 'devil|heart|star|x', word: 'คำที่จอกระพริบ (regex)', acc: 'สีพื้น' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X;
      const tp = D.trig(Lc, P.word, .8).t, p = D.lp(Lc, t), flash = t > tp ? Math.exp(-(t - tp) * 4) : 0;
      c.fillStyle = flash > .5 ? '#fff' : acc; c.fillRect(0, 0, W, H);
      const cols = 9, rows = 5, n = Math.floor(p * cols * rows * 1.2), r = M.rng('wall' + Lc.i), kind = P.kind || 'devil';
      for(let k = 0; k < Math.min(n, cols * rows); k++){ const i = k % cols, j = Math.floor(k / cols);
        const x = 110 + i * 212 + (r() - .5) * 30, y = 110 + j * 215 + (r() - .5) * 30, s = .8 + r() * .4, rr = (r() - .5) * .5;
        c.save(); c.translate(x, y); c.rotate(rr + (flash > 0 ? Math.sin(t * 40 + k) * .1 : 0)); c.scale(s, s);
        c.strokeStyle = flash > .5 ? acc : '#fff'; c.lineWidth = 9; c.lineCap = 'round'; c.lineJoin = 'round';
        if(kind === 'heart'){ D.heartPath(c, 0, -60, 130); c.stroke(); }
        else if(kind === 'star'){ c.beginPath(); for(let q = 0; q < 10; q++){ const a = q * Math.PI / 5 - Math.PI / 2, rr2 = q % 2 ? 28 : 64; c.lineTo(Math.cos(a) * rr2, Math.sin(a) * rr2); } c.closePath(); c.stroke(); }
        else if(kind === 'x'){ c.beginPath(); c.moveTo(-50, -50); c.lineTo(50, 50); c.moveTo(50, -50); c.lineTo(-50, 50); c.stroke(); }
        else { c.beginPath(); c.arc(0, 0, 58, 0, 6.3); c.stroke();
          c.beginPath(); c.moveTo(-40, -40); c.lineTo(-62, -98); c.lineTo(-14, -56); c.moveTo(40, -40); c.lineTo(62, -98); c.lineTo(14, -56); c.stroke();
          c.beginPath(); c.moveTo(-30, -12); c.lineTo(-12, -2); c.moveTo(30, -12); c.lineTo(12, -2); c.stroke();
          c.beginPath(); c.arc(0, 14, 28, .2, Math.PI - .2); c.stroke(); }
        c.restore(); }
      c.fillStyle = 'rgba(10,10,13,.9)'; c.fillRect(0, H / 2 - 130, W, 260);
      c.font = D.F('big', 100);
      M.karaRows(c, Lc, t, { maxW: 1700, lh: 120, cy: H / 2 + 36, dim: 'rgba(255,255,255,.3)', on: '#fff' });
    },
  });

  def('gallery', {
    doc: 'แกลเลอรีรูปในมือถือ ขึ้นหน้าต่าง "ลบรูปภาพ?" ตรงคำที่กำหนดกดลบ รูปหายทีละใบ แล้วขึ้นคำใหญ่ — "Good bye", "ลืม", "ลบ", "จบ"',
    params: { imgs: 'รูป 6–12 รูป', word: 'คำที่กดลบ (regex)', big: 'คำใหญ่หลังลบ (ไม่ใส่ = ไม่มี)', title: 'หัวหน้าต่าง (ค่าเริ่มต้น "ลบรูปภาพ 12 รูป?")', acc: 'สีกรอบ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, { clamp, ease } = M;
      const tg = D.trig(Lc, P.word, .6).t, gone = t - tg, ims = P.imgs || [P.img];
      c.fillStyle = th.bg; c.fillRect(0, 0, W, H);
      const cols = 6, cw = 300, chh = 300, ox = (W - cols * (cw + 12)) / 2, n = Math.max(12, ims.length);
      for(let k = 0; k < 12; k++){ const im = ims[k % ims.length], i = k % cols, j = Math.floor(k / cols), d = clamp((gone - k * .06) / .25), s = 1 - ease.inOut(d);
        if(s <= 0) continue; const x = ox + i * (cw + 12) + cw / 2, y = 120 + j * (chh + 12) + chh / 2;
        c.save(); c.translate(x, y); c.scale(s, s); c.drawImage(X.fx(im, 'fit', cw, chh), -cw / 2, -chh / 2);
        c.strokeStyle = acc; c.lineWidth = 6; c.strokeRect(-cw / 2 + 3, -chh / 2 + 3, cw - 6, chh - 6);
        c.fillStyle = acc; c.beginPath(); c.arc(cw / 2 - 32, -chh / 2 + 32, 18, 0, 6.3); c.fill(); c.restore(); }
      D.txt(c, D.F('body', 36), '#fff', 'รูปภาพ · เลือก 12 รายการ', 90, 80, { align: 'left' });
      if(gone < .6){ const a = gone < 0 ? ease.out(clamp((t - Lc.t0 + .4) / .4)) : 1 - clamp(gone / .6);
        c.save(); c.globalAlpha = a; c.fillStyle = 'rgba(0,0,0,.55)'; c.fillRect(0, 0, W, H);
        c.fillStyle = '#1e1e26'; c.beginPath(); c.roundRect(W / 2 - 360, 300, 720, 330, 40); c.fill();
        D.txt(c, D.F('body', 50), '#fff', P.title || 'ลบรูปภาพ 12 รูป?', W / 2, 400);
        D.txt(c, D.F('thin', 32), th.grey, 'ลบแล้วกู้คืนไม่ได้', W / 2, 455);
        c.fillStyle = '#2b2b35'; c.fillRect(W / 2 - 360, 510, 720, 2); c.fillRect(W / 2, 512, 2, 118);
        D.txt(c, D.F('body', 44), '#4ea1ff', 'ยกเลิก', W / 2 - 180, 590);
        c.fillStyle = gone > -.25 ? 'rgba(255,46,77,.3)' : 'rgba(0,0,0,0)'; c.fillRect(W / 2 + 2, 512, 358, 118);
        D.txt(c, D.F('bold', 44), '#ff2e4d', 'ลบ', W / 2 + 180, 590); c.restore(); }
      if(P.big && gone > .4){ const a = ease.out(clamp((gone - .4) / .4)); c.save(); c.globalAlpha = a;
        D.glitch(c, D.F('big', 260), P.big, W / 2, H / 2 - 40, Math.exp(-(gone - .4) * 3), '#fff', 7); c.restore(); }
      D.lower(c, Lc, t, acc, H - 130, 70);
    },
  });

  // ---- กล้องวิดีโอ REC + ของประกอบเฉพาะท่อน ----
  const EXTRA = {
    cash(c, t, X, p){ const { M, D, W, H, Lc } = X, r = M.rng('cash'); for(let k = 0; k < 40; k++){ const x = r() * W, sp = 200 + r() * 300, ph = r() * 9, y = ((t - Lc.t0 + ph) * sp) % (H + 200) - 100;
      c.save(); c.translate(x + Math.sin(t * 3 + k) * 40, y); c.rotate(t * (r() - .5) * 6); c.scale(1, .5 + .5 * Math.abs(Math.sin(t * 4 + k)));
      c.fillStyle = '#5fa36b'; c.fillRect(-60, -30, 120, 60); c.strokeStyle = '#2d5a36'; c.lineWidth = 3; c.strokeRect(-54, -24, 108, 48); D.txt(c, D.F('bold', 30), '#2d5a36', '฿', 0, 11); c.restore(); } },
    dots(c, t, X){ const { W } = X; c.fillStyle = 'rgba(0,0,0,.6)'; c.beginPath(); c.roundRect(W / 2 + 230, 220, 190, 110, 50); c.fill();
      for(let k = 0; k < 3; k++){ c.fillStyle = `rgba(255,255,255,${.3 + .7 * Math.max(0, Math.sin(t * 6 - k))})`; c.beginPath(); c.arc(W / 2 + 280 + k * 45, 275, 12, 0, 6.3); c.fill(); } },
    tint(c, t, X){ c.save(); c.globalCompositeOperation = 'color'; c.fillStyle = X.P.tint || '#7b2cbf'; c.globalAlpha = .55; c.fillRect(0, 0, X.W, X.H); c.restore(); },
    bars(c, t, X){ const { M, W, H } = X, lv = M.levels(48, t); c.save(); c.globalCompositeOperation = 'lighter';
      lv.forEach((v, k) => { const h = 20 + v * 300; c.fillStyle = X.acc; c.globalAlpha = .35 + v * .5; c.fillRect(W / 2 - 24 * 24 + k * 24, H / 2 - h / 2, 14, h); }); c.restore(); },
    flare(c, t, X, p){ const { M, W, H } = X; c.save(); c.globalCompositeOperation = 'lighter'; const x = M.lerp(-200, W + 200, p), g = c.createRadialGradient(x, 260, 0, x, 260, 700);
      g.addColorStop(0, 'rgba(255,220,160,.75)'); g.addColorStop(.3, 'rgba(255,120,60,.25)'); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(0, 0, W, H);
      for(let k = 1; k < 5; k++){ c.fillStyle = 'rgba(255,200,150,.12)'; c.beginPath(); c.arc(M.lerp(x, W / 2, k * .35), M.lerp(260, H / 2, k * .35), 30 + k * 26, 0, 6.3); c.fill(); } c.restore(); },
    crack(c, t, X){ const { M, D, W, H, Lc, P } = X, th0 = D.trig(Lc, P.word, .5).t; if(t < th0) return; D.kick(th0, 18);
      const r = M.rng('crk'), cx = 1220, cy = 420; c.save(); c.strokeStyle = 'rgba(255,255,255,.85)'; c.lineWidth = 3;
      for(let k = 0; k < 14; k++){ let x = cx, y = cy, a = k / 14 * 6.28 + r() * .3; c.beginPath(); c.moveTo(x, y);
        const len = M.clamp((t - th0) / .25) * (300 + r() * 600); for(let d = 0; d < len; d += 60){ a += (r() - .5) * .5; x += Math.cos(a) * 60; y += Math.sin(a) * 60; c.lineTo(x, y); } c.stroke(); }
      c.fillStyle = 'rgba(255,46,77,.18)'; c.fillRect(0, 0, W, H); c.restore(); },
    rain(c, t, X){ const { M, W, H } = X, r = M.rng('rn'); c.save(); c.strokeStyle = 'rgba(200,220,255,.45)'; c.lineWidth = 2;
      for(let k = 0; k < 140; k++){ const x = r() * W, sp = 900 + r() * 700, y = ((t + r() * 9) * sp) % (H + 100) - 50; c.beginPath(); c.moveTo(x, y); c.lineTo(x - 8, y + 34); c.stroke(); } c.restore(); },
  };
  def('camcorder', {
    doc: 'ภาพกล้องวิดีโอ ● REC: รูปแนวตั้งกลางจอ + พื้นเบลอ + เส้นสแกน + เวลาวิ่ง ใส่ของประกอบได้ — ท่อนแร็ป/ท่อนเล่าเรื่อง (เปลี่ยนรูปทุกบรรทัด)',
    params: { img: 'รูป', fx: 'cash แบงก์ร่วง | dots กำลังพิมพ์ | tint ย้อมสี | bars แท่งเสียง | flare แสงวาบ | crack จอร้าว | rain ฝน', word: 'คำที่จอร้าว (fx=crack)', tint: 'สีย้อม (fx=tint)', rec: 'ข้อความมุมขวาล่าง' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X;
      const p = M.clamp((t - Lc.t0) / Math.max(1, Lc.t1 - Lc.t0));
      c.save(); D.doShake(c, t);
      c.drawImage(X.fx(P.img, 'blur'), 0, 0);
      const im = X.img(P.img), fh = H * .92, fw = im ? Math.min(W * .9, fh * im.width / im.height) : fh * .56, z = 1 + p * .06 + M.beat(t) * .015;
      c.save(); c.translate(W / 2, H / 2); c.scale(z, z); c.rotate(Math.sin(t * .9) * .006);
      if(im) c.drawImage(X.fx(P.img, 'fit', Math.round(fw), Math.round(fh)), -fw / 2, -fh / 2, fw, fh); c.restore();
      if(P.fx && EXTRA[P.fx]) EXTRA[P.fx](c, t, X, p);
      c.drawImage(scanOf(M), 0, 0); M.vignette(c, .6);
      if(Math.floor(t * 1.5) % 2){ c.fillStyle = '#ff2e4d'; c.beginPath(); c.arc(110, 100, 16, 0, 6.3); c.fill(); }
      D.txt(c, D.F('ui', 40), '#fff', 'REC', 140, 114, { align: 'left' });
      const ss = Math.floor(t); D.txt(c, D.F('ui', 36), '#fff', `23:${pad2(14 + Math.floor(ss / 60))}:${pad2(ss % 60)}`, W - 100, 114, { align: 'right' });
      D.txt(c, D.F('ui', 30), 'rgba(255,255,255,.7)', P.rec || '▶ SP', W - 100, H - 70, { align: 'right' });
      c.restore();
      D.lower(c, Lc, t, X.P.on || '#fff');
    },
  });

  def('ecg', {
    doc: 'จอวัดชีพจร: เส้นกราฟเต้นทุกคำที่ร้อง อ่อนลงทีละบรรทัด แล้วหยุดเต้นตรงคำที่กำหนด + "?" ใหญ่ — ใช้กับ 2–3 บรรทัดติดกัน (พรีฮุก, "ไม่มีหัวใจ", "ใจสลาย")',
    lines: 'หลายบรรทัด (i: [a, b])',
    params: { word: 'คำที่หัวใจหยุดเต้น ในบรรทัดสุดท้าย (regex)', acc: 'สีเส้น', mark: 'ตัวใหญ่จาง ๆ หลังหยุดเต้น (ค่าเริ่มต้น "?")' },
    noStrip: true,
    draw(c, t, X){
      const { M, D, th, W, H, P, Ls, acc } = X, { clamp, lerp } = M;
      const Lc = Ls.find(x => t < x.t1) || Ls[Ls.length - 1], li = Ls.indexOf(Lc);
      c.fillStyle = '#05080a'; c.fillRect(0, 0, W, H);
      c.strokeStyle = acc + '1f'; c.lineWidth = 1;
      for(let x = 0; x < W; x += 60){ c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke(); }
      for(let y = 0; y < H; y += 60){ c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
      const onsets = Ls.flatMap((x, k) => x.words.map(w => ({ t: w.t0, amp: 1 - k * .55 / Math.max(1, Ls.length - 1) })));
      const flat = D.trig(Ls[Ls.length - 1], P.word, .7).t;
      const span = 3, x0 = 80, x1 = W - 80, base = 470;
      c.save(); c.strokeStyle = acc; c.lineWidth = 6; c.shadowColor = acc; c.shadowBlur = 16; c.beginPath();
      for(let x = x0; x <= x1; x += 4){
        const tt = t - span + (x - x0) / (x1 - x0) * span; let y = 0;
        if(tt < flat) for(const o of onsets){ const d = tt - o.t; if(d > 0 && d < .18) y += Math.sin(d / .18 * Math.PI * 2) * -230 * o.amp * (d < .06 ? 1 : .5); }
        x === x0 ? c.moveTo(x, base + y) : c.lineTo(x, base + y);
      }
      c.stroke(); c.restore();
      const hr = t < flat ? Math.round(lerp(96, 42, clamp((t - Ls[0].t0) / Math.max(1, flat - Ls[0].t0)))) : 0;
      D.txt(c, D.F('ui', 44), acc, '♥ ' + (hr || '--') + ' bpm', W - 120, 110, { align: 'right' });
      D.txt(c, D.F('ui', 30), acc + 'b3', 'HEART MONITOR', 120, 110, { align: 'left' });
      if(t > flat){ c.save(); c.globalAlpha = clamp((t - flat) / .6) * .25; D.txt(c, D.F('big', 620), acc, P.mark ?? '?', W / 2, 760); c.restore(); }
      c.font = D.F('bold', 88);
      M.karaRows(c, Lc, t, { maxW: 1600, lh: 110, cy: 830, dim: 'rgba(255,255,255,.3)', on: '#fff' });
      const nx = Ls[li + 1] || Lc.next; if(nx){ c.font = D.F('thin', 40); c.fillStyle = 'rgba(255,255,255,.5)'; c.textAlign = 'center'; c.fillText(nx.text, W / 2, 960); }
    },
  });

  def('notebook', {
    doc: 'สมุดเขียนเนื้อเพลงด้วยลายมือ ปากกาเดินตามที่ร้อง บนโต๊ะมืด — "เขียนเพลง", "จดหมาย", ท่อนรำพึง',
    params: { title: 'หัวกระดาษ เช่น "เพลงรัก #27"', img: 'รูปจาง ๆ ด้านหลัง (ไม่ใส่ได้)', ink: 'สีหมึก' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X;
      c.fillStyle = '#16120f'; c.fillRect(0, 0, W, H);
      if(P.img){ c.save(); c.globalAlpha = .35; c.drawImage(X.fx(P.img, 'blur'), 0, 0); c.restore(); }
      c.save(); c.translate(W / 2, H / 2 + 20); c.rotate(-.025);
      c.fillStyle = 'rgba(0,0,0,.5)'; c.fillRect(-740, -396, 1520, 840);
      c.fillStyle = '#f7f3ea'; c.fillRect(-760, -420, 1520, 840);
      c.strokeStyle = 'rgba(37,99,235,.25)'; c.lineWidth = 2; for(let y = -320; y < 400; y += 80){ c.beginPath(); c.moveTo(-760, y); c.lineTo(760, y); c.stroke(); }
      c.strokeStyle = 'rgba(255,46,77,.5)'; c.beginPath(); c.moveTo(-620, -420); c.lineTo(-620, 420); c.stroke();
      if(P.title) D.txt(c, D.F('hand', 40), 'rgba(17,17,20,.6)', P.title, -580, -340, { align: 'left' });
      c.font = D.F('hand', 92);
      const rs = M.karaRows(c, Lc, t, { maxW: 1200, lh: 150, cx: 40, cy: 20, dim: 'rgba(17,17,20,.14)', on: P.ink || '#1d3fa8' });
      const r = rs.find(q => q.cut < q.x0 + q.w - 1) || rs[rs.length - 1], ri = rs.indexOf(r);
      const px = r.cut, py = 20 - (rs.length - 1) * 75 + ri * 150;
      c.save(); c.translate(px + 20, py - 10); c.rotate(-.7); c.fillStyle = '#222'; c.fillRect(-8, -150, 16, 150);
      c.fillStyle = '#c9a227'; c.fillRect(-8, -150, 16, 24); c.beginPath(); c.moveTo(-8, 0); c.lineTo(0, 20); c.lineTo(8, 0); c.fill(); c.restore();
      c.restore(); M.vignette(c, .5);
    },
  });

  def('videoCall', {
    doc: 'หน้าจอวิดีโอคอล: รูปอีกฝ่ายเต็มจอ "กำลังโทร…" + จอเล็กมุมขวา + ปุ่มวางสาย — "โทร", "application", "คุยกัน"',
    params: { img: 'รูปอีกฝ่าย', pip: 'รูปในจอเล็ก', name: 'ชื่อ', on: 'สีเนื้อ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X;
      c.drawImage(X.fx(P.img, 'blur'), 0, 0);
      const im = X.img(P.img), fh = H, fw = im ? Math.min(W, fh * im.width / im.height) : 600;
      c.drawImage(X.fx(P.img, 'fit', Math.round(fw), fh), W / 2 - fw / 2, 0);
      c.fillStyle = 'rgba(0,0,0,.35)'; c.fillRect(0, 0, W, H);
      const d = Math.max(0, t - Lc.t0);
      D.txt(c, D.F('body', 54), '#fff', P.name || 'เธอ', W / 2, 140);
      D.txt(c, D.F('thin', 34), 'rgba(255,255,255,.8)', d < 1.4 ? 'กำลังโทร' + '.'.repeat(1 + Math.floor(d * 3) % 3) : '00:0' + Math.min(9, Math.floor(d - 1.4)), W / 2, 190);
      if(P.pip){ c.save(); c.beginPath(); c.roundRect(W - 380, 60, 260, 380, 24); c.clip(); c.drawImage(X.fx(P.pip, 'fit', 260, 380), W - 380, 60); c.restore(); }
      for(const [x, col] of [[W / 2 - 220, 'rgba(255,255,255,.2)'], [W / 2, '#ff2e4d'], [W / 2 + 220, 'rgba(255,255,255,.2)']]){ c.fillStyle = col; c.beginPath(); c.arc(x, H - 120, 62, 0, 6.3); c.fill(); }
      D.txt(c, D.F('bold', 60), '#fff', '✆', W / 2, H - 98);
      D.lower(c, Lc, t, P.on || '#7fe3ff', H - 300, 78);
    },
  });

  def('voiceNote', {
    doc: 'แชตข้อความเสียง: คลื่นเสียงเดินตามที่ร้อง + สติกเกอร์หัวใจเด้งตรงคำที่กำหนด — "ฝากบอก", "ดูแลตัวเอง", คำห่วงใย',
    params: { avatar: 'รูปอีกฝ่าย', name: 'ชื่อ', word: 'คำที่หัวใจเด้ง (regex)', bg: 'รูปพื้นหลังเบลอ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, { clamp, ease } = M;
      c.drawImage(X.fx(P.bg || P.avatar, 'blur'), 0, 0);
      const x = W / 2 - 360, y = 40, w = 720, h = H - 80; D.phone(c, x, y, w, h);
      D.avatar(c, X.fx(P.avatar, 'fit', 88, 88, { fy: .3 }), x + 90, y + 120, 44); D.txt(c, D.F('body', 40), '#fff', P.name || 'เธอ', x + 160, y + 132, { align: 'left' });
      const p = D.lp(Lc, t), bx = x + w - 600, by = y + 300;
      c.fillStyle = '#2563eb'; c.beginPath(); c.roundRect(bx, by, 560, 130, 65); c.fill();
      c.fillStyle = '#fff'; c.beginPath(); c.moveTo(bx + 50, by + 40); c.lineTo(bx + 100, by + 65); c.lineTo(bx + 50, by + 90); c.fill();
      const lv = M.levels(26, t);
      for(let k = 0; k < 26; k++){ const hh = 16 + (k / 26 < p ? lv[k] * 70 + 10 : 12 + Math.abs(Math.sin(k * 1.7)) * 30);
        c.fillStyle = k / 26 < p ? '#fff' : 'rgba(255,255,255,.4)'; c.beginPath(); c.roundRect(bx + 130 + k * 15, by + 65 - hh / 2, 8, hh, 4); c.fill(); }
      D.txt(c, D.F('ui', 28), 'rgba(255,255,255,.85)', '0:0' + Math.min(9, Math.floor(p * 4)), bx + 545, by + 76, { align: 'right' });
      const hp = ease.elastic(clamp((t - D.trig(Lc, P.word, .7).t) / .8));
      if(hp > 0){ c.save(); c.translate(x + w - 170, by + 300); c.scale(hp, hp); c.rotate(-.2); c.fillStyle = '#ff2e4d';
        c.beginPath(); c.moveTo(0, 60); c.bezierCurveTo(-120, -20, -60, -110, 0, -50); c.bezierCurveTo(60, -110, 120, -20, 0, 60); c.fill(); c.strokeStyle = '#fff'; c.lineWidth = 10; c.stroke(); c.restore(); }
      c.font = D.F('body', 56);
      M.karaRows(c, Lc, t, { maxW: 600, lh: 74, cx: W / 2, cy: y + 760, dim: 'rgba(255,255,255,.35)', on: '#fff' });
    },
  });

  def('gridCross', {
    doc: 'ตาราง 10 รูป โดนกากบาททีละรูปตามที่ร้อง + ตัวนับ — "หาอีกสิบก็ไม่เหมือน", "ไม่มีใครแทน", การเปรียบเทียบ',
    params: { imgs: 'รูป 5–10 รูป', label: 'ข้อความตัวนับ เช่น "ไม่มีใครคล้าย"', acc: 'สีปากกา' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X;
      c.fillStyle = th.bg; c.fillRect(0, 0, W, H);
      const ims = P.imgs || [P.img], p = D.lp(Lc, t), n = Math.floor(p * 11);
      for(let k = 0; k < 10; k++){ const m = ims[k % ims.length], i = k % 5, j = Math.floor(k / 5), x = 160 + i * 330, y = 90 + j * 380;
        c.save(); c.globalAlpha = k < n ? .35 : 1; c.drawImage(X.fx(m, 'fit', 290, 340), x, y); c.restore();
        c.strokeStyle = '#333'; c.lineWidth = 3; c.strokeRect(x, y, 290, 340);
        if(k < n){ D.marker(c, [[x + 40, y + 60], [x + 250, y + 280]], 1, acc, 12); D.marker(c, [[x + 250, y + 60], [x + 40, y + 280]], 1, acc, 12); }
        D.txt(c, D.F('ui', 30), th.grey, pad2(k + 1), x + 16, y + 40, { align: 'left' }); }
      D.txt(c, D.F('ui', 40), acc, `${Math.min(10, n)}/10 · ${P.label || ''}`, W - 160, 60, { align: 'right' });
      D.lower(c, Lc, t, acc, H - 140, 80);
    },
  });

  def('dissolve', {
    doc: 'รูปในโพลารอยด์ค่อย ๆ สลายเป็นเม็ดปลิวหาย — "ไม่มีความหมาย", "จางหาย", "ลืม"',
    params: { img: 'รูป', acc: 'สีเม็ด' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, p = D.lp(Lc, t);
      c.fillStyle = th.bg; c.fillRect(0, 0, W, H);
      const pw = 560, ph = 720, x = W / 2, y = 460;
      c.save(); c.globalAlpha = 1 - p * .9; D.polaroid(c, X.fx(P.img, 'ht', pw, ph), x, y, pw, ph, .03); c.restore();
      const r = M.rng('dust2');
      for(let k = 0; k < 260; k++){ const sx = x - pw / 2 + r() * pw, sy = y - ph / 2 + r() * ph, d = M.clamp(p * 1.6 - r() * .6);
        if(d <= 0) continue; c.fillStyle = r() < .5 ? acc : '#ddd'; c.globalAlpha = 1 - d; c.beginPath(); c.arc(sx + d * 600 * (r() + .2), sy - d * 300 * r(), 4 + r() * 5, 0, 6.3); c.fill(); }
      c.globalAlpha = 1;
      D.lower(c, Lc, t, '#fff', H - 130, 76);
    },
  });

  def('crtOff', {
    doc: 'ฉากปิด: จอดับแบบทีวีเก่า (ยุบเป็นเส้นแล้วเป็นจุด) แล้วขึ้นชื่อเพลงแบบกลิตช์ + เครดิต',
    params: { img: 'รูปสุดท้ายก่อนดับ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, seg, meta, acc } = X, { clamp, ease } = M, d = t - seg.t0;
      c.fillStyle = '#000'; c.fillRect(0, 0, W, H);
      if(d < 1.2){ const sy = 1 - ease.inOut(clamp(d / .6)), sx = 1 - ease.inOut(clamp((d - .6) / .5));
        c.save(); c.translate(W / 2, H / 2); c.scale(Math.max(sx, .002), Math.max(sy, .004));
        c.drawImage(X.fx(P.img, 'fit'), -W / 2, -H / 2); c.fillStyle = `rgba(255,255,255,${1 - sy})`; c.fillRect(-W / 2, -H / 2, W, H); c.restore(); }
      c.globalAlpha = ease.out(clamp((d - 1.6) / 1.2));
      D.glitch(c, D.F('big', 170), meta.title, W / 2, H / 2 - 60, Math.exp(-(d - 1.6) * 2) * .6, '#fff', 99);
      D.txt(c, D.F('ui', 48), acc, meta.artist, W / 2, H / 2 + 80);
      D.txt(c, D.F('thin', 26), 'rgba(255,255,255,.55)', (meta.credit || '') + ' · PU KARAOKE', W / 2, H - 90);
      c.globalAlpha = 1;
    },
  });
})();
