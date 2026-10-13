// ===== คลังฉาก: ทั่วไป (ใช้กับเพลงไหนก็ได้) + บรรยากาศ (ฝน / ถนนกลางคืน / ทะเล / ดาว / ปาร์ตี้ / ตัวอักษรเต้นตามบีต) =====
// 5 แบบแรกมาจากแม่แบบอัตโนมัติ (แบบ A) — "kinetic" เป็นฉากสำรองเวลาบทไม่ได้ระบุบรรทัดนั้น
(() => {
  const def = MVScenes.def;
  const paperC = {};
  const paper = (M, tint) => paperC[tint] ||= M.paper(tint);

  // คำทีละคำแบบ kinetic: ยังไม่ร้อง = ขอบจาง (อ่านล่วงหน้าได้), คำที่ร้อง = เด้ง+สี, ร้องแล้ว = ทึบ
  function kineticWords(c, M, Lc, t, o){
    c.font = o.fam.replace('#', o.px);
    const pos = M.layoutWords(c, Lc.words, o.maxW, o.px * 1.22, o.cx ?? M.W / 2, o.cy ?? M.H / 2);
    const enter = M.clamp((t - (Lc.t0 - .45)) / .5), wi = M.wordAt(Lc, t), bt = o.beat ? M.beat(t, 7) : 0;
    c.textBaseline = 'middle'; c.textAlign = 'left'; c.lineJoin = 'round';
    pos.forEach((p, k) => {
      const w = p.w, st = M.ease.out(M.clamp(enter * 1.6 - k * .06)), age = t - w.t0, on = k === wi, done = k < wi || (k === wi && t > w.t1);
      const pop = (on ? 1 + .32 * (1 - M.ease.back(M.clamp(age / .28))) : 1) * (1 + bt * .06 * ((k % 2) ? 1 : -1));
      c.save(); c.translate(p.x + p.width / 2, p.y + (1 - st) * 60 - (on ? 10 * Math.exp(-age * 5) : 0) - bt * 14 * ((k % 2) ? 1 : 0));
      c.scale(pop, pop); c.rotate(on ? (o.tilt || 0) * Math.exp(-age * 4) : 0); c.globalAlpha = st;
      if(o.shadow && (on || done)){ c.fillStyle = o.shadow; c.fillText(w.s, -p.width / 2 + 8, 8); }
      if(!(on || done) || o.alwaysStroke){ c.lineWidth = o.strokeW || 4; c.strokeStyle = o.ghost; c.strokeText(w.s, -p.width / 2, 0); }
      if(on || done){ c.fillStyle = on ? o.on : o.done; c.fillText(w.s, -p.width / 2, 0); } else if(o.ghostFill){ c.fillStyle = o.ghostFill; c.fillText(w.s, -p.width / 2, 0); }
      c.restore();
    });
  }
  const pulseOf = (M, D, Lc, t, k = 5) => Math.exp(-(t - D.lastOn(Lc, t)) * k);

  def('kinetic', {
    doc: 'ทั่วไป: ตัวหนังสือใหญ่เด้งทีละคำบนพื้นสีเรียบ วงแหวนหมุน — ใช้ได้กับทุกบรรทัด (ฉากสำรอง)',
    params: { bg: 'สีพื้น (ไม่ใส่ = สีเน้นของช่วง)', on: 'สีคำที่ร้อง' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, pulse = pulseOf(M, D, Lc, t);
      const bg = P.bg || acc, fg = P.fg || '#fff';
      c.fillStyle = bg; c.fillRect(0, 0, W, H);
      c.save(); c.translate(W / 2, H / 2); c.rotate(t * .08 + Lc.i);
      for(let r = 0; r < 9; r++){ c.beginPath(); c.arc(0, 0, 140 + r * 130 + pulse * 18 + M.beat(t) * 20, 0, 6.3); c.lineWidth = 46; c.strokeStyle = r % 2 ? 'rgba(255,255,255,.06)' : 'rgba(0,0,0,.06)'; c.stroke(); }
      c.restore();
      const px = M.fitFont(c, Lc.words, D.F('big', '#'), 1580, 3, 170, 80);
      kineticWords(c, M, Lc, t, { fam: D.F('big', '#'), px, maxW: 1580, cy: H / 2 - 30, on: P.on || '#ffe14d', done: fg, ghost: fg, ghostFill: 'rgba(0,0,0,.18)', strokeW: 3, shadow: 'rgba(0,0,0,.35)', tilt: .08, beat: true });
    },
  });

  def('print', {
    doc: 'ทั่วไป: รูปเต็มจอพิมพ์เม็ดสกรีนสองสีซูมช้า + ป้ายเนื้อแบบโปสเตอร์ — บรรทัดเล่าเรื่องที่มีรูปประกอบ',
    params: { img: 'รูป' },
    prep(X){ X.fx(X.P.img, 'htcolor', 1920, 1080, { paper: '#f2e6cf' }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, seg, acc } = X, p = (t - seg.t0) / Math.max(1, seg.t1 - seg.t0), kick = Math.exp(-(t - D.lastOn(Lc, t)) * 9);
      c.fillStyle = '#f2e6cf'; c.fillRect(0, 0, W, H);
      c.save(); c.translate(kick * 3, -kick * 2); M.kenBurns(c, X.fx(P.img, 'htcolor', 1920, 1080, { paper: '#f2e6cf' }), p, { dx: .05, dy: -.03 }); c.restore();
      c.font = D.F('serif', 84);
      const two = c.measureText(Lc.text).width > 1500, bh = two ? 250 : 150;
      const pos = M.layoutWords(c, Lc.words, two ? 1300 : 1700, 100, 0, two ? -50 : 0);
      const bw = Math.max(...pos.map(q => q.x + q.width)) - Math.min(...pos.map(q => q.x)) + 100, st = M.ease.back(M.clamp((t - (Lc.t0 - .45)) / .45));
      c.save(); c.translate(W / 2, H - 240); c.rotate(-.025); c.scale(st, st);
      c.fillStyle = '#22306b'; c.fillRect(-bw / 2 + 14, -bh / 2 + 14, bw, bh); c.fillStyle = '#f7efdc'; c.fillRect(-bw / 2, -bh / 2, bw, bh);
      c.lineWidth = 5; c.strokeStyle = '#22306b'; c.strokeRect(-bw / 2, -bh / 2, bw, bh);
      M.karaRows(c, Lc, t, { maxW: two ? 1300 : 1700, lh: 100, cx: 0, cy: 0, baseline: 'middle', dim: '#a89a80', on: acc });
      c.restore();
    },
  });

  def('sketch', {
    doc: 'ทั่วไป: รูปกลายเป็นลายเส้นดินสอค่อย ๆ ถูกวาดจากซ้ายไปขวา + ลายมือขีดเส้นใต้ — ท่อนช้า/ท่อนเปิดเรื่อง',
    params: { img: 'รูป', dark: 'true = ชอล์กบนกระดานดำ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, seg, acc } = X, dark = P.dark ?? !th.light, p = M.clamp((t - seg.t0) / Math.min(7, Math.max(1, seg.t1 - seg.t0)));
      const bg = dark ? '#15131b' : '#efe3c8', ink = dark ? '#ece6f5' : '#2b2118';
      c.drawImage(dark ? (paperC.dk ||= (() => { const k = M.canvas(); const g = k.getContext('2d'); g.fillStyle = bg; g.fillRect(0, 0, W, H); return k; })()) : paper(M, bg), 0, 0);
      const art = X.fx(P.img, 'line', W, H, { mode: 'contain', pad: 60, ink });
      c.save(); c.beginPath(); c.moveTo(0, 0); const edge = W * M.ease.inOut(p) * 1.15;
      for(let y = 0; y <= H; y += 40) c.lineTo(edge + Math.sin(y * .05 + t * 2) * 30, y); c.lineTo(0, H); c.closePath(); c.clip();
      M.kenBurns(c, art, p, { z0: 1, z1: 1.05 }); c.restore();
      c.fillStyle = dark ? 'rgba(21,19,27,.6)' : 'rgba(239,227,200,.55)'; c.fillRect(0, H - 330, W, 330);
      c.font = D.F('hand', 96);
      const rs = M.karaRows(c, Lc, t, { maxW: 1600, lh: 110, cy: H - 185, dim: dark ? 'rgba(255,255,255,.3)' : 'rgba(43,33,24,.3)', on: ink });
      c.save(); c.strokeStyle = acc; c.lineWidth = 6; c.lineCap = 'round';
      rs.forEach((r, k) => { c.beginPath(); const y = H - 185 - (rs.length - 1) * 55 + k * 110 + 30; for(let x = r.x0; x < r.cut; x += 12) c.lineTo(x, y + Math.sin(x * .07) * 4); c.stroke(); });
      c.restore();
    },
  });

  def('neon', {
    doc: 'ทั่วไป: กลางคืนนีออน รูปจาง ๆ ย้อมม่วง โบเก้ลอย ตัวหนังสือเรืองแสง + กรอบนีออน — เพลงรัก/เพลงกลางคืน',
    params: { img: 'รูป', glow: 'สีนีออน' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, seg, acc } = X, p = (t - seg.t0) / Math.max(1, seg.t1 - seg.t0), glow = P.glow || acc;
      c.fillStyle = '#05031a'; c.fillRect(0, 0, W, H);
      if(P.img){ c.globalAlpha = .42; M.kenBurns(c, X.fx(P.img, 'duo'), p, { dx: -.04 }); c.globalAlpha = 1; }
      c.save(); c.globalCompositeOperation = 'lighter'; const r = M.rng('nb' + Lc.i);
      for(let k = 0; k < 26; k++){ const x = (r() * W + t * (10 + r() * 30)) % W, y = (r() * H - t * (8 + r() * 20) % H + H) % H, s = 20 + r() * 70;
        const gr = c.createRadialGradient(x, y, 0, x, y, s); gr.addColorStop(0, k % 2 ? glow + '59' : 'rgba(76,201,240,.3)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = gr; c.fillRect(x - s, y - s, s * 2, s * 2); }
      c.restore();
      const since = t - (Lc.t0 - .45), flick = since < .5 && (Math.floor(since * 30) % 3 === 0);
      c.font = D.F('body', 112);
      if(!flick) M.karaRows(c, Lc, t, { maxW: 1440, lh: 150, cy: H / 2, baseline: 'middle', dim: 'rgba(255,255,255,.22)', on: '#fff', glow, glowB: 34 });
      c.save(); c.strokeStyle = glow; c.shadowColor = glow; c.shadowBlur = 20; c.lineWidth = 5; c.globalAlpha = .8; c.strokeRect(120, 150, W - 240, H - 300); c.restore();
    },
  });

  def('molamPoster', {
    doc: 'ทั่วไป: โปสเตอร์หมอลำ/คอนเสิร์ต — รัศมีหมุนสีจัด รูปในวงกลมกลางบน ตัวหนังสือหนาขอบเข้มเด้งทีละคำ — เพลงสนุก/ลูกทุ่ง/ท่อนฮุก',
    params: { img: 'รูปในวงกลม', bg: 'สีพื้น', ray: 'สีรัศมี' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, pulse = pulseOf(M, D, Lc, t, 6), bt = M.beat(t);
      c.fillStyle = P.bg || acc; c.fillRect(0, 0, W, H);
      c.save(); c.translate(W / 2, 400); c.rotate(t * .12);
      for(let k = 0; k < 24; k++){ c.rotate(Math.PI / 12); if(k % 2) continue; c.beginPath(); c.moveTo(0, 0); c.lineTo(1600, -210); c.lineTo(1600, 210); c.closePath(); c.fillStyle = P.ray || '#ffd23f'; c.globalAlpha = .55; c.fill(); }
      c.restore();
      const rr = 270 + pulse * 10 + bt * 12;
      if(P.img){ c.save(); c.beginPath(); c.arc(W / 2, 360, rr, 0, 6.3); c.clip(); c.drawImage(X.fx(P.img, 'ht1', 700, 700, { paper: '#fff4d6', c1: '#2a0a3a' }), W / 2 - 350, 10, 700, 700); c.restore(); }
      c.save(); c.lineWidth = 16; c.strokeStyle = '#2a0a3a'; c.beginPath(); c.arc(W / 2, 360, rr, 0, 6.3); c.stroke();
      c.lineWidth = 6; c.strokeStyle = '#fff'; c.setLineDash([2, 22]); c.lineCap = 'round'; c.beginPath(); c.arc(W / 2, 360, rr + 30, 0, 6.3); c.stroke(); c.restore();
      const px = M.fitFont(c, Lc.words, D.F('big', '#'), 1700, 2, 140, 70);
      kineticWords(c, M, Lc, t, { fam: D.F('big', '#'), px, maxW: 1700, cy: 820, on: '#ffe14d', done: '#fff', ghost: '#2a0a3a', ghostFill: 'rgba(255,255,255,.55)', alwaysStroke: true, strokeW: 16, shadow: '#2a0a3a', tilt: -.1, beat: true });
    },
  });

  // ---------- บรรยากาศใหม่ ----------
  def('rain', {
    doc: 'หน้าต่างยามฝนตก: เม็ดฝนไหลบนกระจก ไฟเมืองเบลอข้างหลัง (หรือรูปเบลอ) — "ฝน", "น้ำตา", "เหงา", "คิดถึง"',
    params: { img: 'รูปหลังกระจก (ไม่ใส่ = ไฟเมือง)', tint: 'สีไฟ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X;
      if(P.img) c.drawImage(X.fx(P.img, 'blur'), 0, 0);
      else { c.fillStyle = '#0b0f1a'; c.fillRect(0, 0, W, H); const r = M.rng('city');
        c.save(); c.globalCompositeOperation = 'lighter';
        for(let k = 0; k < 60; k++){ const x = r() * W, y = 300 + r() * 600, s = 30 + r() * 110, col = [acc, '#ffb347', '#4cc9f0', '#ffffff'][k % 4];
          const g = c.createRadialGradient(x, y, 0, x, y, s); g.addColorStop(0, col + '55'); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(x - s, y - s, s * 2, s * 2); }
        c.restore(); }
      c.fillStyle = 'rgba(10,20,40,.35)'; c.fillRect(0, 0, W, H);
      // หยดน้ำบนกระจก: หยดนิ่ง + หยดไหลเป็นทาง
      const r = M.rng('drops');
      c.save();
      for(let k = 0; k < 160; k++){ const x = r() * W, y = r() * H, s = 2 + r() * 7; c.fillStyle = 'rgba(220,235,255,.35)'; c.beginPath(); c.ellipse(x, y, s * .8, s, 0, 0, 6.3); c.fill(); }
      for(let k = 0; k < 26; k++){ const x = r() * W, sp = 60 + r() * 160, y = ((t + r() * 20) * sp) % (H + 200) - 100, s = 6 + r() * 6;
        c.strokeStyle = 'rgba(220,235,255,.25)'; c.lineWidth = s * .6; c.beginPath(); c.moveTo(x, y - 140); c.lineTo(x + Math.sin(y * .02) * 6, y); c.stroke();
        c.fillStyle = 'rgba(235,245,255,.6)'; c.beginPath(); c.ellipse(x, y, s, s * 1.3, 0, 0, 6.3); c.fill(); }
      c.restore();
      D.lower(c, Lc, t, P.on || '#cfe8ff', H / 2 + 40, 92, { glow: acc, glowB: 18 });
    },
  });

  def('drive', {
    doc: 'ขับรถกลางคืน: ถนนมุมมองไกล เส้นถนนวิ่งเข้าหา ไฟรถสวนทาง เสาไฟผ่าน — "ขับรถ", "ทางกลับบ้าน", "หนีไป", เพลงจังหวะกลาง-เร็ว',
    params: { sky: 'สีฟ้า', acc: 'สีไฟท้าย' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, hz = 470, vx = W / 2;
      const g = c.createLinearGradient(0, 0, 0, hz); g.addColorStop(0, '#05030f'); g.addColorStop(1, P.sky || '#3a1c5c'); c.fillStyle = g; c.fillRect(0, 0, W, hz);
      c.fillStyle = '#0a0a10'; c.fillRect(0, hz, W, H - hz);
      // ถนน
      c.fillStyle = '#16161e'; c.beginPath(); c.moveTo(vx - 30, hz); c.lineTo(vx + 30, hz); c.lineTo(W + 600, H); c.lineTo(-600, H); c.closePath(); c.fill();
      const sp = 1.4 + M.beat(t) * .3;
      for(let k = 0; k < 14; k++){ const z = ((k / 14 + t * sp * .25) % 1), zz = z * z, y = hz + zz * (H - hz), w = 6 + zz * 40, h = 4 + zz * 90;
        c.fillStyle = '#f5f5f7'; c.globalAlpha = .3 + zz * .7; c.fillRect(vx - w / 2, y, w, h); }
      c.globalAlpha = 1;
      for(let k = 0; k < 8; k++){ const z = ((k / 8 + t * sp * .18) % 1), zz = z * z, y = hz + zz * (H - hz);
        for(const side of [-1, 1]){ const x = vx + side * (40 + zz * 1400), ph = 20 + zz * 520;
          c.fillStyle = '#20202a'; c.fillRect(x - 3 - zz * 6, y - ph, 6 + zz * 12, ph);
          const lg = c.createRadialGradient(x, y - ph, 0, x, y - ph, 20 + zz * 180); lg.addColorStop(0, 'rgba(255,200,120,.8)'); lg.addColorStop(1, 'rgba(255,200,120,0)');
          c.save(); c.globalCompositeOperation = 'lighter'; c.fillStyle = lg; c.fillRect(x - 200, y - ph - 200, 400, 400); c.restore(); } }
      const r = M.rng('cars');
      c.save(); c.globalCompositeOperation = 'lighter';
      for(let k = 0; k < 3; k++){ const z = ((r() + t * .35) % 1), zz = z * z, x = vx - 60 - zz * 500, y = hz + zz * (H - hz), s = 4 + zz * 60;
        for(const dx of [-1, 1]){ const lg = c.createRadialGradient(x + dx * s, y, 0, x + dx * s, y, s * 3); lg.addColorStop(0, 'rgba(255,255,230,.9)'); lg.addColorStop(1, 'rgba(255,255,230,0)'); c.fillStyle = lg; c.fillRect(x + dx * s - s * 3, y - s * 3, s * 6, s * 6); } }
      c.restore();
      c.fillStyle = 'rgba(0,0,0,.35)'; c.fillRect(0, H - 360, W, 360);
      D.lower(c, Lc, t, acc, H - 200, 88);
    },
  });

  def('sea', {
    doc: 'ทะเลยามพระอาทิตย์ตก/กลางคืน: ดวงอาทิตย์หรือดวงจันทร์ แสงสะท้อนบนคลื่น คลื่นซ้อนชั้น — "ทะเล", "คลื่น", "ไกลแสนไกล", เพลงช้า',
    params: { night: 'true = กลางคืน ดวงจันทร์', acc: 'สีท้องฟ้า' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, hz = 560, night = !!P.night;
      const g = c.createLinearGradient(0, 0, 0, hz); g.addColorStop(0, night ? '#05081a' : '#2a1a4a'); g.addColorStop(1, night ? '#1b2a5c' : (P.sky || acc)); c.fillStyle = g; c.fillRect(0, 0, W, hz);
      const sx = W / 2 + 280, sy = hz - 120, sr = night ? 90 : 160;
      c.fillStyle = night ? '#f4f1e0' : '#ffd36b'; c.beginPath(); c.arc(sx, sy, sr, 0, 6.3); c.fill();
      if(night){ const r = M.rng('st'); for(let k = 0; k < 120; k++){ c.fillStyle = `rgba(255,255,255,${.3 + .5 * Math.abs(Math.sin(t + k))})`; c.fillRect(r() * W, r() * (hz - 80), 2, 2); } }
      const wg = c.createLinearGradient(0, hz, 0, H); wg.addColorStop(0, night ? '#0e1a3e' : '#3a2458'); wg.addColorStop(1, '#05060f'); c.fillStyle = wg; c.fillRect(0, hz, W, H - hz);
      // แสงสะท้อนเป็นเส้นสั้น ๆ
      c.save(); c.globalCompositeOperation = 'lighter';
      for(let k = 0; k < 70; k++){ const y = hz + 10 + k * 7, w = (40 + k * 6) * (.6 + .4 * Math.sin(t * 2 + k)), x = sx + Math.sin(t * 1.3 + k * .7) * (10 + k);
        c.fillStyle = night ? 'rgba(244,241,224,.35)' : 'rgba(255,211,107,.4)'; c.fillRect(x - w / 2, y, w, 3); }
      c.restore();
      c.strokeStyle = 'rgba(255,255,255,.12)'; c.lineWidth = 2;
      for(let k = 0; k < 10; k++){ const y = hz + 30 + k * 50; c.beginPath(); for(let x = 0; x <= W; x += 24) c.lineTo(x, y + Math.sin(x * .01 + t * (1 + k * .1) + k) * (4 + k)); c.stroke(); }
      c.font = D.F('script', 104);
      M.karaRows(c, Lc, t, { maxW: 1500, lh: 130, cy: 240, dim: 'rgba(255,255,255,.3)', on: '#fff', glow: night ? '#9fb6ff' : '#ffb347', glowB: 22 });
    },
  });

  def('stars', {
    doc: 'อวกาศ/ท้องฟ้าดาว: ดาวพุ่งเข้าหาจอ คำที่ร้องแล้วกลายเป็นกลุ่มดาวเชื่อมเส้น — "ดาว", "ฟ้า", "ฝัน", "จักรวาล", "ไกล"',
    params: { acc: 'สีเส้นกลุ่มดาว' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X;
      c.fillStyle = '#03030a'; c.fillRect(0, 0, W, H);
      const r = M.rng('warp'), sp = .12 + M.beat(t) * .05;
      for(let k = 0; k < 260; k++){ const a = r() * 6.283, z = ((r() + t * sp) % 1), d = z * z * 1200, s = .5 + z * 3.5;
        c.fillStyle = `rgba(255,255,255,${z})`; c.fillRect(W / 2 + Math.cos(a) * d, H / 2 + Math.sin(a) * d * .6, s, s); }
      c.font = D.F('bold', 100);
      const pos = M.layoutWords(c, Lc.words, 1500, 130, W / 2, H / 2 - 40);
      const pts = pos.filter(q => t >= q.w.t0).map(q => [q.x + q.width / 2, q.y - 60]);
      c.save(); c.strokeStyle = acc; c.globalAlpha = .7; c.lineWidth = 2; c.beginPath(); pts.forEach((p, k) => k ? c.lineTo(...p) : c.moveTo(...p)); c.stroke();
      c.fillStyle = '#fff'; c.shadowColor = acc; c.shadowBlur = 20; pts.forEach(p => { c.beginPath(); c.arc(p[0], p[1], 7, 0, 6.3); c.fill(); }); c.restore();
      M.karaRows(c, Lc, t, { maxW: 1500, lh: 130, cy: H / 2 - 40, dim: 'rgba(255,255,255,.28)', on: '#fff', glow: acc, glowB: 26 });
    },
  });

  def('confetti', {
    doc: 'ปาร์ตี้: กระดาษสีโปรยตามบีต พื้นสีสด ไฟสปอตกวาด ตัวหนังสือเด้ง — เพลงสนุก/วันเกิด/ฉลอง/ท่อนฮุกเต้น',
    params: { bg: 'สีพื้น', colors: 'รายการสีกระดาษ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, bt = M.beat(t, 6), cols = P.colors || ['#ff4d6d', '#ffd23f', '#4cc9f0', '#7bf1a8', '#b06cff', '#ffffff'];
      c.fillStyle = P.bg || '#1a0b2e'; c.fillRect(0, 0, W, H);
      c.save(); c.globalCompositeOperation = 'lighter';
      for(let k = 0; k < 3; k++){ const a = Math.sin(t * .9 + k * 2) * .6, x = W * (k + .5) / 3;
        c.save(); c.translate(x, -50); c.rotate(a); const g = c.createLinearGradient(0, 0, 0, H * 1.3); g.addColorStop(0, cols[k] + '66'); g.addColorStop(1, 'rgba(0,0,0,0)');
        c.fillStyle = g; c.beginPath(); c.moveTo(-30, 0); c.lineTo(30, 0); c.lineTo(260, H * 1.3); c.lineTo(-260, H * 1.3); c.closePath(); c.fill(); c.restore(); }
      c.restore();
      const r = M.rng('cf');
      for(let k = 0; k < 120; k++){ const x0 = r() * W, sp = 120 + r() * 200, ph = r() * 30, y = ((t + ph) * sp) % (H + 100) - 50, x = x0 + Math.sin((t + ph) * 2) * 40;
        c.save(); c.translate(x, y); c.rotate((t + ph) * (2 + r() * 4)); c.scale(1, Math.sin((t + ph) * 6) * (1 + bt)); c.fillStyle = cols[k % cols.length]; c.fillRect(-9, -5, 18, 10); c.restore(); }
      const px = M.fitFont(c, Lc.words, D.F('big', '#'), 1600, 2, 150, 80);
      kineticWords(c, M, Lc, t, { fam: D.F('big', '#'), px, maxW: 1600, cy: H / 2, on: P.on || '#ffd23f', done: '#fff', ghost: '#fff', ghostFill: 'rgba(255,255,255,.18)', strokeW: 3, shadow: 'rgba(0,0,0,.4)', tilt: .1, beat: true });
    },
  });

  def('beatType', {
    doc: 'ตัวอักษรเต้นตามบีตกลองจริง: คำซ้อนเป็นแถวใหญ่ สลับสีขาว-ดำทุกบีต กระพริบ — ท่อนแร็ปเร็ว/EDM/ฮุกที่ซ้ำคำ (ต้องมี mv_beats.json ถึงจะเต้น)',
    params: { acc: 'สีเน้น' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, bt = M.beat(t, 10), inv = bt > .6;
      c.fillStyle = inv ? acc : th.bg; c.fillRect(0, 0, W, H);
      c.font = D.F('big', 150); c.textBaseline = 'middle'; c.textAlign = 'left';
      const word = (Lc.words[Math.max(0, M.wordAt(Lc, t))] || Lc.words[0]).s + '  ';
      const ww = c.measureText(word).width;
      for(let row = 0; row < 7; row++){ const y = 80 + row * 150, off = ((t * (row % 2 ? 260 : -260)) % ww + ww) % ww;
        c.fillStyle = (row === 3) ? (inv ? '#000' : acc) : (inv ? 'rgba(0,0,0,.18)' : 'rgba(255,255,255,.08)');
        for(let x = -off - ww; x < W + ww; x += ww) c.fillText(word, x, y); }
      D.lower(c, Lc, t, inv ? '#000' : acc, H - 150, 76, { stroke: inv ? 'rgba(255,255,255,.9)' : 'rgba(0,0,0,.85)' });
    },
  });
})();
