// ===== คลังฉาก: ตระกูล "ภาพเก่า / งานพิมพ์ / ไทย-อีสาน" (ต้นแบบจาก MV เจ้าดอกจำปา) =====
// เหมาะกับลูกทุ่ง/หมอลำ/เพลงช้า/เพลงธรรมชาติ ใช้รูปสาธารณสมบัติ (lib/...) หรือภาพนิ่งจากคลิป — ธีมสว่าง (light: true, bg กระดาษ) เข้ากันที่สุด
// ฉากที่มี pal ใช้ชุดสี theme.pals[ชื่อ] = {bg, band, hi, fg, alt} (ฮุกแต่ละรอบเปลี่ยน pal ได้ เช่น day / sunset / night)
(() => {
  const def = MVScenes.def;
  const PAL0 = { bg: '#c8352c', band: '#1d2a5c', hi: '#f2b632', fg: '#fff6e3', alt: '#2f6b4a' };
  const palOf = X => (typeof X.P.pal === 'object' ? X.P.pal : (X.th.pals || {})[X.P.pal]) || (X.th.pals || {}).day || PAL0;
  const paperC = {};
  const paper = (M, tint) => paperC[tint] ||= M.paper(tint);
  const sprites = {};
  const grayFlower = M => sprites.g ||= M.flowerSprite(256, '#cfc8ba', '#a39a86', 'rgba(0,0,0,.25)');

  def('titleCard', {
    doc: 'ฉากเปิด: แผ่นภาพ (ลายเส้น + เม็ดสกรีน) ค่อย ๆ ถูกวาดทางซ้าย ชื่อเพลงพิมพ์สองสีทางขวา + กรอบ + นับถอยหลัง',
    params: { img: 'รูปแผ่นภาพ (ภาพพฤกษศาสตร์/ภาพเก่า/รูปศิลปิน)', sub: 'บรรทัดรอง เช่น ชื่อภาษาลาว/อังกฤษ', style: 'line (ลายเส้น) | photo (รูปจริง)' },
    noStrip: true,
    prep(X){ X.fx(X.P.img, 'line', 1000, 1080, { mode: 'contain', pad: 90 }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, meta } = X, { clamp, ease } = M, p = clamp(t / 10);
      c.drawImage(paper(M, th.light ? th.paper : '#15131b'), 0, 0);
      if(!th.light){ c.fillStyle = 'rgba(10,10,13,.7)'; c.fillRect(0, 0, W, H); }
      c.save(); c.beginPath(); c.arc(560, H / 2, ease.out(p) * 800, 0, 6.3); c.clip();
      if(P.style === 'photo') c.drawImage(X.fx(P.img, 'fit', 1000, 1080, { mode: 'contain' }), 60, 0);
      else { c.globalCompositeOperation = th.light ? 'multiply' : 'screen'; c.drawImage(X.fx(P.img, 'line', 1000, 1080, { mode: 'contain', pad: 90, ink: th.light ? th.ink : '#ece6f5' }), 60, 0); }
      c.restore();
      const a = ease.out(clamp((t - 1) / 1.6));
      c.save(); c.globalAlpha = a; c.translate(0, (1 - a) * 30);
      c.font = D.F('serif', 136); const s = Math.min(1, 820 / c.measureText(meta.title).width);
      c.save(); c.translate(1420, H / 2 - 30); c.scale(s, s); D.riso(c, D.F('serif', 136), meta.title, 0, 0, th.light ? th.ink : '#fff', th.acc[0], 7); c.restore();
      if(P.sub) D.txt(c, D.F('script', 64), th.acc[0], P.sub, 1420, H / 2 + 70);
      c.restore();
      c.globalAlpha = ease.out(clamp((t - 3) / 1.5));
      D.txt(c, D.F('thin', 36), th.light ? th.ink : '#fff', meta.artist, 1420, H / 2 + 150); c.globalAlpha = 1;
      D.frame(c, th.light ? th.ink : '#ffffff55', 46, X.flower);
      D.countdown(c, t, X.Lc, th.acc[0], H - 140);
    },
  });

  def('outroCard', {
    doc: 'ฉากปิด: แผ่นภาพ + ชื่อเพลง + เครดิตรูป + ดอกไม้ร่วง',
    params: { img: 'รูปแผ่นภาพ', petals: 'true/false ดอกไม้ร่วง' },
    noStrip: true,
    draw(c, t, X){
      const { M, D, th, W, H, P, meta, seg } = X, p = M.clamp((t - seg.t0) / 4);
      c.drawImage(paper(M, th.light ? th.paper : '#15131b'), 0, 0);
      if(!th.light){ c.fillStyle = 'rgba(10,10,13,.7)'; c.fillRect(0, 0, W, H); }
      c.save(); c.globalCompositeOperation = th.light ? 'multiply' : 'screen';
      c.drawImage(X.fx(P.img, 'line', 1000, 1080, { mode: 'contain', pad: 90, ink: th.light ? th.ink : '#ece6f5' }), 60, 0); c.restore();
      if(P.petals !== false) D.petals(c, t, 16, 'outro', X.flower, { s: 30, sv: 40, a: .8 });
      c.globalAlpha = M.ease.out(p);
      c.font = D.F('serif', 130); const s = Math.min(1, 820 / c.measureText(meta.title).width);
      c.save(); c.translate(1420, H / 2 - 60); c.scale(s, s); D.riso(c, D.F('serif', 130), meta.title, 0, 0, th.light ? th.ink : '#fff', th.acc[0]); c.restore();
      D.txt(c, D.F('thin', 36), th.light ? th.ink : '#fff', meta.artist, 1420, H / 2 + 20);
      c.font = D.F('thin', 24); const cs = Math.min(1, 860 / Math.max(1, c.measureText(meta.credit || '').width));
      c.save(); c.translate(1420, H / 2 + 110); c.scale(cs, cs); D.txt(c, D.F('thin', 24), th.light ? 'rgba(0,0,0,.6)' : 'rgba(255,255,255,.6)', meta.credit || '', 0, 0); c.restore();
      D.txt(c, D.F('body', 30), th.acc[0], 'PU KARAOKE', 1420, H / 2 + 200);
      c.globalAlpha = 1; D.frame(c, th.light ? th.ink : '#ffffff55', 46, X.flower);
    },
  });

  def('bees', {
    doc: 'แผ่นภาพดอกไม้เม็ดสกรีนทางขวา ผึ้งบินวน แล้วบินหนีตรงคำที่กำหนด ข้อความทางซ้าย — "ไร้ผึ้ง", "หมดกลิ่น", "ไม่มีใครสน"',
    params: { img: 'รูปดอกไม้', word: 'คำที่ผึ้งบินหนี (regex)', label: 'ป้ายเล็กเหนือเนื้อ เช่น "บทที่ ๑"' },
    prep(X){ X.fx(X.P.img, 'htcolor', 900, 1000, { mode: 'contain', pad: 30 }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, { clamp, lerp, ease } = M, tg = D.trig(Lc, P.word, .6).t;
      c.drawImage(paper(M, th.paper), 0, 0);
      c.save(); c.globalCompositeOperation = 'multiply'; c.drawImage(X.fx(P.img, 'htcolor', 900, 1000, { mode: 'contain', pad: 30 }), W - 960, 40); c.restore();
      for(let k = 0; k < 6; k++){
        const ph = k * 1.1, gone = clamp((t - tg - k * .12) / 2.2);
        const ox = W - 520 + Math.cos(t * 1.7 + ph) * (120 + k * 18), oy = 420 + Math.sin(t * 2.3 + ph) * (90 + k * 10);
        const x = lerp(ox, ox + 900 + k * 120, ease.inOut(gone)), y = lerp(oy, oy - 500 - k * 60, ease.inOut(gone));
        bee(c, x, y, 3.2, t + k, gone > 0 ? 1 : (Math.sin(t * 1.7 + ph) > 0 ? -1 : 1), th);
      }
      c.font = D.F('script', 96);
      M.karaRows(c, Lc, t, { maxW: 900, lh: 130, cx: 560, cy: H / 2, dim: 'rgba(29,42,92,.28)', on: th.ink });
      if(P.label) D.txt(c, D.F('body', 30), th.acc[0], P.label, 560, 250);
      D.frame(c, th.ink, 46, X.flower);
    },
  });
  function bee(c, x, y, s, t, dir, th){
    c.save(); c.translate(x, y); c.scale(s * dir, s);
    const flap = Math.sin(t * 60) * .5;
    c.fillStyle = 'rgba(255,255,255,.75)'; c.strokeStyle = th.ink; c.lineWidth = 1.5;
    for(const sgn of [-1, 1]){ c.save(); c.rotate(sgn * (.5 + flap)); c.beginPath(); c.ellipse(0, -12, 7, 14, 0, 0, 6.3); c.fill(); c.stroke(); c.restore(); }
    c.fillStyle = '#f2b632'; c.beginPath(); c.ellipse(0, 0, 16, 10, 0, 0, 6.3); c.fill(); c.stroke();
    c.fillStyle = th.ink; c.fillRect(-4, -9, 4, 18); c.fillRect(5, -8, 3, 16); c.restore();
  }

  def('wordsFall', {
    doc: 'คำที่ร้องจบแล้วร่วงหล่นลงพื้นดินทีละคำ เด้งแล้วกองอยู่ — "ร่วง", "หล่น", "ตกต่ำ", "พังทลาย"',
    params: { img: 'รูปพื้นดิน/ทุ่ง (แถบล่าง)' },
    prep(X){ if(X.P.img) X.fx(X.P.img, 'ht1', 1920, 1080, { fy: .8, paper: '#dccaa4', c1: '#3b2a1a', cell: 9 }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, p = D.lp(Lc, t), L0 = th.light;
      c.fillStyle = L0 ? `rgb(${M.lerp(239, 214, p)},${M.lerp(228, 205, p)},${M.lerp(204, 190, p)})` : th.bg; c.fillRect(0, 0, W, H);
      if(P.img){ c.save(); c.globalCompositeOperation = L0 ? 'multiply' : 'source-over'; c.globalAlpha = L0 ? 1 : .5;
        c.drawImage(X.fx(P.img, 'ht1', 1920, 1080, { fy: .8, paper: '#dccaa4', c1: '#3b2a1a', cell: 9 }), 0, H - 260, W, 260); c.restore(); }
      c.fillStyle = L0 ? 'rgba(59,42,26,.85)' : X.acc; c.fillRect(0, H - 262, W, 6);
      D.petals(c, t, 14, 'p2', grayFlower(M), { s: 30, sv: 40, a: .7 });
      c.font = D.F('script', 120);
      const pos = M.layoutWords(c, Lc.words, 1600, 150, W / 2, 330), r = M.rng('fall');
      c.textBaseline = 'alphabetic'; c.textAlign = 'left';
      pos.forEach(q => {
        const w = q.w, dt = t - (w.t1 + .25), rr = r(), r2 = r(); let x = q.x, y = q.y, rot = 0;
        if(dt > 0){ const ground = H - 290 + rr * 60, fall = ground - q.y, tf = Math.sqrt(2 * fall / 2600);
          if(dt < tf){ y = q.y + 1300 * dt * dt; rot = dt / tf * (r2 - .5) * 1.4; } else { const b = dt - tf; y = ground - Math.abs(Math.sin(b * 9)) * 40 * Math.exp(-b * 5); rot = (r2 - .5) * 1.4; }
          x += (r2 - .5) * 160 * M.clamp(dt); }
        c.save(); c.translate(x + q.width / 2, y); c.rotate(rot);
        c.fillStyle = dt > 0 ? (L0 ? '#3b2a1a' : th.grey) : t >= w.t0 ? (L0 ? th.ink : '#fff') : (L0 ? 'rgba(29,42,92,.3)' : th.dim);
        c.fillText(w.s, -q.width / 2, 0); c.restore();
      });
    },
  });

  def('heartCrack', {
    doc: 'หัวใจใหญ่ (ลายรูปข้างใน) ร้าวตรงคำที่กำหนด แล้วแยกเป็นสองซีก — "ใจสลาย", "เซาฮัก", "หมดรัก", "เจ็บ"',
    params: { img: 'รูปลายในหัวใจ (ไม่ใส่ได้)', word: 'คำที่ร้าว (regex)', acc: 'สีหัวใจ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, { clamp, ease } = M;
      const tc = D.trig(Lc, P.word, .4).t, cp = clamp((t - tc) / .9), sep = ease.out(clamp((t - tc - .9) / 1.2));
      c.fillStyle = th.light ? th.ink : th.bg; c.fillRect(0, 0, W, H);
      const hx = W / 2, hy = 90, hs = 600, crack = [[hx, hy + hs * .32]], r = M.rng('crack');
      for(let k = 1; k <= 8; k++) crack.push([hx + (k % 2 ? 1 : -1) * (20 + r() * 40), hy + hs * .32 + k * (hs * .68 / 8)]);
      const tex = P.img ? X.fx(P.img, 'htcolor') : null;
      const half = side => {
        c.save(); c.translate(side * sep * 60, sep * 20); c.rotate(side * sep * .06);
        c.beginPath(); c.moveTo(side < 0 ? 0 : W, 0); for(const p of crack) c.lineTo(p[0], p[1]); c.lineTo(crack[crack.length - 1][0], H); c.lineTo(side < 0 ? 0 : W, H); c.closePath();
        if(cp > 0) c.clip();
        D.heartPath(c, hx, hy, hs); c.fillStyle = acc; c.fill();
        if(tex){ c.save(); D.heartPath(c, hx, hy, hs); c.clip(); c.globalCompositeOperation = 'multiply'; c.drawImage(tex, 0, 0); c.restore(); }
        D.heartPath(c, hx, hy, hs); c.lineWidth = 10; c.strokeStyle = '#fff6e3'; c.stroke(); c.restore();
      };
      if(cp > 0){ half(-1); half(1); } else half(-1);
      if(cp > 0 && sep < 1){ c.save(); c.strokeStyle = '#fff6e3'; c.lineWidth = 7; c.beginPath();
        const n = Math.max(1, Math.floor(cp * crack.length)); crack.slice(0, n).forEach((p, i) => i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])); c.stroke(); c.restore(); }
      c.font = D.F('bold', 92);
      M.karaRows(c, Lc, t, { maxW: 1500, lh: 116, cy: 860, dim: 'rgba(255,246,227,.35)', on: '#fff6e3', stroke: th.light ? th.ink : '#000', strokeW: 14 });
    },
  });

  def('letter', {
    doc: 'จดหมายเขียนมือบนโต๊ะ เนื้อเขียนตามที่ร้อง แล้วตราประทับสีแดงกระแทกลงตรงคำที่กำหนด — "บอกลา", "ขอโทษ", "สัญญา", จดหมายถึงใครสักคน',
    params: { to: 'หัวจดหมาย เช่น "ถึง… เธอ"', stamp: 'คำในตราประทับ', word: 'คำที่ประทับ (regex)', img: 'รูปจาง ๆ พื้นหลัง' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, ts = D.trig(Lc, P.word, .85).t + .1, sp = M.clamp((t - ts) / .18);
      if(t > ts) D.kick(ts, 16);
      c.fillStyle = '#8a3b2e'; c.fillRect(0, 0, W, H);
      if(P.img){ c.save(); c.globalAlpha = .18; c.drawImage(X.fx(P.img, 'htcolor'), 0, 0); c.restore(); }
      c.save(); D.doShake(c, t); c.translate(W / 2, H / 2); c.rotate(-.03);
      c.fillStyle = 'rgba(0,0,0,.3)'; c.fillRect(-700, -376, 1440, 800);
      c.drawImage(paper(M, '#efe4cc'), 0, 0, W, H, -720, -400, 1440, 800);
      c.strokeStyle = 'rgba(29,42,92,.18)'; c.lineWidth = 2; for(let y = -260; y < 380; y += 90){ c.beginPath(); c.moveTo(-640, y); c.lineTo(640, y); c.stroke(); }
      c.strokeStyle = '#c8352c'; c.lineWidth = 3; c.beginPath(); c.moveTo(-560, -380); c.lineTo(-560, 380); c.stroke();
      D.txt(c, D.F('hand', 40), 'rgba(29,42,92,.75)', P.to || 'ถึง… เธอ', -500, -300, { align: 'left' });
      c.font = D.F('hand', 104);
      M.karaRows(c, Lc, t, { maxW: 1100, lh: 150, cx: 40, cy: 0, dim: 'rgba(29,42,92,.16)', on: '#1d2a5c' });
      if(t > ts && P.stamp !== ''){ const s = M.lerp(2.4, 1, M.ease.out(sp)), st = P.stamp || Lc.words[Lc.words.length - 1].s;
        c.save(); c.translate(380, 210); c.rotate(-.2); c.scale(s, s); c.globalAlpha = .88 * sp; c.globalCompositeOperation = 'multiply';
        c.font = D.F('big', 104); const bw = Math.max(420, c.measureText(st).width + 80);
        c.strokeStyle = '#c8352c'; c.lineWidth = 12; c.beginPath(); c.roundRect(-bw / 2, -90, bw, 180, 22); c.stroke();
        c.lineWidth = 4; c.beginPath(); c.roundRect(-bw / 2 + 20, -70, bw - 40, 140, 14); c.stroke();
        D.txt(c, D.F('big', 104), '#c8352c', st, 0, 36); c.restore(); }
      c.restore(); M.vignette(c, .45);
    },
  });

  // เศษภาพแตก (แคชต่อรูป)
  const shardsC = {};
  function shardsOf(M){
    return shardsC.s ||= (() => { const r = M.rng('shards'), cols = 9, rows = 5, P = [], W = M.W, H = M.H;
      for(let j = 0; j <= rows; j++) for(let i = 0; i <= cols; i++){ const e = i === 0 || j === 0 || i === cols || j === rows;
        P.push([i * W / cols + (e ? 0 : (r() - .5) * 140), j * H / rows + (e ? 0 : (r() - .5) * 120)]); }
      const out = [], at = (i, j) => P[j * (cols + 1) + i];
      for(let j = 0; j < rows; j++) for(let i = 0; i < cols; i++)
        for(const tri of [[at(i, j), at(i + 1, j), at(i, j + 1)], [at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)]]){
          const cx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3, cy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
          out.push({ tri, cx, cy, dx: (cx - W / 2) / W, dy: (cy - H / 2) / H, rot: (r() - .5) * .6, sp: .6 + r() * .8 }); }
      return out; })();
  }
  def('shatter', {
    doc: 'ภาพเต็มจอแตกเป็นเสี่ยง ๆ ตรงคำที่กำหนด เศษลอยห่างออก (บรรทัดที่สองตัวหนังสือเซไปมา) — "ใจพัง", "แตกสลาย", "โลเล"; ใช้ได้ 1–2 บรรทัด',
    lines: '1–2 บรรทัด',
    params: { img: 'รูปเต็มจอ', word: 'คำที่แตก (regex)', sway: 'true = บรรทัดที่สองโยกไปมา' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Ls } = X, L4 = Ls[0], L5 = Ls[1];
      const tb = D.trig(L4, P.word, .6).t, bp = M.ease.out(M.clamp((t - tb) / 1.4)), drift = Math.max(0, t - tb), img = X.fx(P.img, 'htcolor');
      c.fillStyle = '#120e1f'; c.fillRect(0, 0, W, H); if(t > tb) D.kick(tb, 22);
      c.save(); D.doShake(c, t);
      for(const s of shardsOf(M)){ const d = bp * 70 * s.sp + drift * 6 * s.sp;
        c.save(); c.translate(s.cx + s.dx * d * 4, s.cy + s.dy * d * 4 + Math.sin(t * 1.3 + s.cx) * bp * 6); c.rotate(s.rot * bp + Math.sin(t + s.cy) * .02 * bp); c.translate(-s.cx, -s.cy);
        c.beginPath(); c.moveTo(...s.tri[0]); c.lineTo(...s.tri[1]); c.lineTo(...s.tri[2]); c.closePath();
        c.save(); c.clip(); c.drawImage(img, 0, 0); c.restore();
        if(bp > 0){ c.strokeStyle = 'rgba(255,246,227,.8)'; c.lineWidth = 2; c.stroke(); } c.restore(); }
      c.restore();
      c.fillStyle = 'rgba(18,14,31,.82)'; c.fillRect(0, H / 2 - 170, W, 340);
      const Lc = L5 && t >= L5.t0 - .3 ? L5 : L4;
      c.save(); if(Lc === L5 && P.sway !== false){ const sw = Math.sin(t * 2.6); c.translate(W / 2 + sw * 50, H / 2); c.rotate(sw * .04); c.translate(-W / 2, -H / 2); }
      c.font = D.F('big', 110);
      M.karaRows(c, Lc, t, { maxW: 1700, lh: 130, cy: H / 2 + 38, dim: 'rgba(255,246,227,.32)', on: Lc === L5 ? (th.acc[1] || '#f2b632') : '#fff6e3' });
      c.restore();
    },
  });

  def('bloom', {
    doc: 'สองบรรทัด: บรรทัดแรกทั้งภาพเป็นสีเทา ดอกเหี่ยว / บรรทัดที่สองดอกบานทีละดอกตามคำ สีไหลกลับ — "เหี่ยวเฉา…แตกช่อใหม่", "เริ่มใหม่", "ยังสู้"',
    lines: '2 บรรทัด (เศร้า -> หวัง)',
    params: { petal: 'สีกลีบ', glow: 'สีพื้นตอนบาน' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Ls } = X, { clamp, ease } = M, L6 = Ls[0], L7 = Ls[1] || Ls[0];
      const col = ease.inOut(clamp((t - L7.t0 + .2) / 1.4));
      c.fillStyle = '#d8d3c8'; c.fillRect(0, 0, W, H);
      if(col > 0){ const g = c.createRadialGradient(W / 2, H * .55, 0, W / 2, H * .55, col * 1300);
        g.addColorStop(0, '#ffe08a'); g.addColorStop(.6, P.glow || '#f6b94a'); g.addColorStop(1, 'rgba(246,185,74,0)'); c.fillStyle = g; c.fillRect(0, 0, W, H); }
      const bx = W / 2 + 330, by = H + 20, grow = clamp((t - L6.t0 + .4) / 2.5);
      const blooms = [[0, -560, 1.2], [-180, -420, .9], [190, -470, 1], [-300, -250, .7], [300, -280, .8], [-90, -300, .75], [110, -170, .65]];
      c.save(); c.strokeStyle = col > .3 ? '#2f6b4a' : '#7d776b'; c.lineCap = 'round';
      c.lineWidth = 26; c.beginPath(); c.moveTo(bx, by); c.quadraticCurveTo(bx - 60, by - 300, bx, by - 300 - 260 * grow); c.stroke();
      c.lineWidth = 12; for(const [x, y] of blooms){ if(y < -500) continue; c.beginPath(); c.moveTo(bx - 20, by + y * .6); c.quadraticCurveTo(bx + x * .4, by + y * .9, bx + x * grow, by + y * grow); c.stroke(); }
      c.restore();
      blooms.forEach(([x, y, s], k) => {
        const w = L7.words[Math.min(k, L7.words.length - 1)], bt = L7 === L6 ? 0 : clamp((t - w.t0) / .7), px = bx + x * grow, py = by + y * grow, size = 210 * s;
        c.save(); c.translate(px, py);
        if(bt > 0){ const e = ease.elastic(bt); c.rotate((1 - e) * 1.2 + k); c.scale(e, e); c.drawImage(X.flower, -size / 2, -size / 2, size, size); }
        else { c.rotate(k + 2.6); c.globalAlpha = .9; c.drawImage(grayFlower(M), -size * .32, -size * .32 + 20, size * .64, size * .64); }
        c.restore();
      });
      if(col < 1) D.petals(c, t, 6, 'wilt', grayFlower(M), { s: 30, sv: 20, a: .6 * (1 - col) });
      const Lc = t < L7.t0 - .3 ? L6 : L7;
      c.font = D.F('serif', 112);
      M.karaRows(c, Lc, t, { maxW: 900, lh: 150, cx: 560, cy: H / 2 - 20, dim: col > .5 ? 'rgba(29,42,92,.3)' : 'rgba(80,76,68,.35)', on: col > .5 ? '#c8352c' : '#5c574d' });
    },
  });

  def('drift', {
    doc: 'ภาพกลางคืนเม็ดสกรีนทอง คำลอยตามสายลมเหมือนกลิ่นหอม/ควัน แสงทองระยิบ — "กลิ่นหอม", "ลอยไป", "คิดถึง", "ฝัน"',
    params: { img: 'รูปกลางคืน/ภูมิทัศน์', acc: 'สีคำที่ร้องแล้ว' },
    prep(X){ X.fx(X.P.img, 'htdark', 1920, 1080, { c1: '#f2b632' }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, p = M.clamp((t - Lc.t0) / 8);
      c.fillStyle = '#0b1030'; c.fillRect(0, 0, W, H);
      M.kenBurns(c, X.fx(P.img, 'htdark', 1920, 1080, { c1: '#f2b632' }), p, { z0: 1.05, z1: 1.18, dx: -.06 });
      c.save(); c.globalCompositeOperation = 'lighter';
      for(let k = 0; k < 120; k++){ const u = ((k * 37.7 + t * 40) % (W + 200)) - 100, y = 640 + Math.sin(u * .004 + t * .8 + k * .31) * 160 - k * 2;
        c.fillStyle = `rgba(242,182,50,${.25 + .25 * Math.sin(t * 3 + k)})`; c.beginPath(); c.arc(u, y, 2 + (k % 4), 0, 6.3); c.fill(); }
      c.restore();
      c.font = D.F('script', 104);
      const pos = M.layoutWords(c, Lc.words, 1700, 140, W / 2, 470);
      c.textAlign = 'left'; c.textBaseline = 'middle';
      pos.forEach((q, k) => { const on = t >= q.w.t0, age = t - q.w.t0;
        const y = q.y + Math.sin(t * 1.4 + k * .9) * 16 - (on ? Math.min(age, 4) * 8 : 0), x = q.x + (on ? Math.min(age, 4) * 6 : 0);
        c.save(); if(on){ c.shadowColor = '#f2b632'; c.shadowBlur = 30; } c.fillStyle = on ? (P.on || '#ffe6a8') : 'rgba(242,236,255,.35)'; c.fillText(q.w.s, x, y); c.restore(); });
      M.vignette(c, .55);
    },
  });

  // ผ้าซิ่นลายขิดต่อชุดสี
  const texC = {};
  function textileOf(M, pal){
    return texC[pal.bg + pal.band] ||= (() => { const c = M.canvas(960, 200), g = c.getContext('2d');
      g.fillStyle = pal.band; g.fillRect(0, 0, 960, 200); g.fillStyle = pal.hi; g.fillRect(0, 18, 960, 10); g.fillRect(0, 172, 960, 10);
      for(let x = 0; x < 960; x += 80){
        g.fillStyle = pal.bg; g.beginPath(); g.moveTo(x + 40, 40); g.lineTo(x + 80, 100); g.lineTo(x + 40, 160); g.lineTo(x, 100); g.closePath(); g.fill();
        g.fillStyle = pal.hi; g.beginPath(); g.moveTo(x + 40, 70); g.lineTo(x + 60, 100); g.lineTo(x + 40, 130); g.lineTo(x + 20, 100); g.closePath(); g.fill();
        g.fillStyle = pal.fg; g.fillRect(x + 37, 97, 6, 6);
        g.fillStyle = pal.alt; for(let k = 0; k < 4; k++) g.fillRect(x + k * 20 + 6, 4, 8, 8), g.fillRect(x + k * 20 + 6, 188, 8, 8); }
      return c; })();
  }
  function textileBand(c, M, pal, y, t, dir){ const tx = textileOf(M, pal), off = ((t * 60 * dir) % 960 + 960) % 960; for(let x = -off; x < M.W; x += 960) c.drawImage(tx, x, y, 960, 200); }

  def('houses', {
    doc: 'ลายผ้าซิ่นขอบบน-ล่าง + บ้านใต้ถุนสูง 5 หลัง ดอกไม้กระโดดไปผิดหลัง — "ไปผิดบ้าน", "ผิดที่", "หลงทาง" (ลูกทุ่ง/อีสาน)',
    params: { pal: 'ชุดสี (theme.pals)', wrong: 'หลังที่ผิด 0–4 (ค่าเริ่มต้น 3)' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, pal = palOf(X), p = D.lp(Lc, t), wr = P.wrong ?? 3;
      c.fillStyle = pal.bg; c.fillRect(0, 0, W, H); textileBand(c, M, pal, 40, t, 1); textileBand(c, M, pal, H - 240, t, -1);
      const hy = 690;
      for(let k = 0; k < 5; k++){ const x = 360 + k * 300;
        c.save(); c.translate(x, hy); c.fillStyle = k === wr ? pal.band : 'rgba(0,0,0,.18)';
        c.fillRect(-70, -60, 140, 70); c.beginPath(); c.moveTo(-95, -55); c.lineTo(0, -130); c.lineTo(95, -55); c.closePath(); c.fill();
        c.fillRect(-60, 10, 10, 50); c.fillRect(50, 10, 10, 50); c.restore(); }
      const fxp = M.lerp(360, 360 + wr * 300, M.ease.inOut(p)), fyp = hy - 190 - Math.abs(Math.sin(p * 3 * Math.PI)) * 110;
      c.save(); c.translate(fxp, fyp); c.rotate(t * 2); c.drawImage(X.flower, -60, -60, 120, 120); c.restore();
      if(p > .95) D.txt(c, D.F('big', 70), pal.hi, '?', 360 + wr * 300 + 90, hy - 200, { stroke: pal.band, sw: 10 });
      c.font = D.F('big', 120);
      M.karaRows(c, Lc, t, { maxW: 1600, lh: 140, cy: 380, dim: 'rgba(255,246,227,.4)', on: pal.hi, stroke: pal.band, strokeW: 18 });
    },
  });

  def('fog', {
    doc: 'หมอกค่อย ๆ ลอยมาบังคำ ตั้งแต่คำที่กำหนดเป็นต้นไปจางหาย — "มองไม่เห็น", "เลือนลาง", "ไม่ชัดเจน"',
    params: { pal: 'ชุดสี', word: 'คำแรกที่ถูกหมอกบัง (regex)', img: 'รูปพื้นจาง ๆ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, pal = palOf(X), hid = D.trig(Lc, P.word, .55).idx;
      c.fillStyle = pal.band; c.fillRect(0, 0, W, H);
      if(P.img){ c.save(); c.globalAlpha = .25; c.globalCompositeOperation = 'screen'; c.drawImage(X.fx(P.img, 'htdark'), 0, 0); c.restore(); }
      c.font = D.F('bold', 112);
      const pos = M.layoutWords(c, Lc.words, 1500, 140, W / 2, H / 2); c.textAlign = 'left'; c.textBaseline = 'middle';
      pos.forEach((q, k) => { const on = t >= q.w.t0, fade = k >= hid ? M.clamp((t - q.w.t1 - .2) / 1) : 0;
        c.save(); c.globalAlpha = 1 - fade * .85; c.fillStyle = on ? pal.hi : 'rgba(255,255,255,.35)'; c.fillText(q.w.s, q.x, q.y + fade * 10); c.restore(); });
      const fogA = M.clamp((t - Lc.words[hid].t0) / 1.5), spr = fogSpr(M);
      for(let k = 0; k < 9; k++){ const x = ((k * 260 + t * (30 + k * 6)) % (W + 600)) - 300, y = H / 2 + Math.sin(k * 2 + t * .5) * 200, r = 260 + (k % 3) * 80;
        c.globalAlpha = .12 + .3 * fogA; c.drawImage(spr, x - r, y - r, r * 2, r * 2); }
      c.globalAlpha = 1;
    },
  });
  let fogC = null;
  function fogSpr(M){ if(!fogC){ fogC = M.canvas(256, 256); const g = fogC.getContext('2d'), gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    gr.addColorStop(0, '#fff'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 256, 256); } return fogC; }

  def('wordSlam', {
    doc: 'ทีละคำเต็มจอ พื้นเปลี่ยนสีทุกคำ รัศมีหมุน — บรรทัดสั้นที่อยากเน้นทุกคำ "ความฮักต้องฉักให้เป็น"',
    params: { pal: 'ชุดสี' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, pal = palOf(X), wi = Math.max(0, M.wordAt(Lc, t)), w = Lc.words[wi], age = t - w.t0;
      const cols = [pal.bg, pal.band, pal.alt, pal.hi], bg = cols[wi % cols.length];
      c.fillStyle = bg; c.fillRect(0, 0, W, H);
      c.save(); c.translate(W / 2, H / 2 - 40); c.rotate(-.05 + wi * .03);
      for(let k = 0; k < 14; k++){ c.rotate(Math.PI / 7); c.fillStyle = 'rgba(255,255,255,.07)'; c.fillRect(0, -30, 1400, 60); } c.restore();
      c.font = D.F('big', 300); const s = Math.min(1, 1500 / c.measureText(w.s).width) * (1 + .25 * Math.exp(-age * 8)), fg = bg === pal.hi ? pal.band : pal.fg;
      c.save(); c.translate(W / 2, H / 2 + 60); c.scale(s, s); c.textAlign = 'center';
      c.fillStyle = 'rgba(0,0,0,.25)'; c.fillText(w.s, 14, 14); c.fillStyle = fg; c.fillText(w.s, 0, 0); c.restore();
      c.font = D.F('body', 54); M.karaText(c, Lc.text, W / 2, H - 130, M.sung(Lc, t), { align: 'center', dim: 'rgba(255,255,255,.4)', on: fg });
    },
  });

  def('mapPath', {
    doc: 'แผนที่เก่า เส้นทางประแดงเดินไป แล้วเลี้ยวผิดทางตรงคำที่กำหนด + กากบาท — "เลือกผิดทาง", "หลงทาง", "เส้นทาง", "ระยะทาง"',
    params: { img: 'รูปแผนที่ (lib/map_siam.jpg)', word: 'คำที่เลี้ยวผิด (regex)', pal: 'ชุดสีแถบบน', dark: 'true = มืดลง (ฮุกกลางคืน)' },
    prep(X){ X.fx(X.P.img, 'ht1', 1920, 1080, { fy: .45, c1: '#4a3a28', cell: 6, paper: '#efe4cc', contrast: 1.6 }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, pal = palOf(X), { clamp, lerp } = M, p = D.lp(Lc, t), fork = clamp((t - D.trig(Lc, P.word, .5).t) / 1.5);
      c.drawImage(X.fx(P.img, 'ht1', 1920, 1080, { fy: .45, c1: '#4a3a28', cell: 6, paper: '#efe4cc', contrast: 1.6 }), 0, 0);
      if(P.dark){ c.fillStyle = 'rgba(15,20,51,.55)'; c.fillRect(0, 0, W, H); }
      const path = [[260, 860], [520, 760], [720, 800], [900, 640], [1060, 600]], right = [[1060, 600], [1300, 420], [1540, 300]], wrong = [[1060, 600], [1260, 760], [1500, 900], [1640, 960]];
      const drawP = (pts, prog, col, dash) => { c.save(); c.strokeStyle = col; c.lineWidth = 12; c.lineCap = 'round'; c.setLineDash(dash); c.beginPath(); const n = (pts.length - 1) * clamp(prog);
        pts.forEach((q, i) => { if(i > Math.ceil(n)) return; const f = i <= n ? 1 : n - (i - 1); const x = i ? lerp(pts[i - 1][0], q[0], Math.min(1, f)) : q[0], y = i ? lerp(pts[i - 1][1], q[1], Math.min(1, f)) : q[1]; i ? c.lineTo(x, y) : c.moveTo(x, y); });
        c.stroke(); c.restore(); };
      drawP(path, clamp(p * 1.8), '#c8352c', [24, 22]); drawP(right, fork * .9, 'rgba(47,107,74,.55)', [6, 22]); drawP(wrong, fork, '#c8352c', [24, 22]);
      c.save(); c.translate(1540, 300); c.drawImage(X.flower, -55, -55, 110, 110); c.restore();
      if(fork >= 1){ c.save(); c.translate(1640, 960); c.rotate(.2); c.strokeStyle = '#c8352c'; c.lineWidth = 16; c.lineCap = 'round'; c.beginPath(); c.moveTo(-40, -40); c.lineTo(40, 40); c.moveTo(40, -40); c.lineTo(-40, 40); c.stroke(); c.restore(); }
      c.fillStyle = pal.band; c.fillRect(0, 80, W, 210);
      c.font = D.F('bold', 96); M.karaRows(c, Lc, t, { maxW: 1700, lh: 110, cy: 220, dim: 'rgba(255,255,255,.4)', on: pal.hi });
    },
  });

  def('sunburst', {
    doc: 'ท่อนฮุกใหญ่: รัศมีหมุน ดอกไม้ยักษ์กลางจอเต้นตามคำ ดอกเล็กโคจร กลีบระเบิดตรงคำที่กำหนด — ฮุก/ชื่อเพลง/ท่อนที่ทุกคนร้องตาม',
    params: { pal: 'ชุดสี', word: 'คำที่กลีบระเบิด (regex)', img: 'รูปกลางวงกลมแทนดอกไม้ (ไม่ใส่ = ดอกไม้)' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, pal = palOf(X), { clamp, ease } = M;
      const th0 = D.trig(Lc, P.word, .5).t, w = M.wordAt(Lc, t), pul = w < 0 ? 0 : Math.exp(-(t - Lc.words[w].t0) * 5), burst = t - th0, bt = M.beat(t, 6);
      c.fillStyle = pal.bg; c.fillRect(0, 0, W, H);
      c.save(); c.translate(W / 2, 420); c.rotate(t * .15);
      for(let k = 0; k < 20; k++){ c.rotate(Math.PI / 10); if(k % 2) continue; c.beginPath(); c.moveTo(0, 0); c.lineTo(1500, -170); c.lineTo(1500, 170); c.closePath(); c.fillStyle = pal.hi; c.globalAlpha = .35 + bt * .2; c.fill(); }
      c.restore();
      const fs = 520 * (1 + pul * .08 + bt * .04) * ease.back(clamp((t - Lc.t0 + .4) / .8));
      if(P.img){ c.save(); c.beginPath(); c.arc(W / 2, 420, fs * .5, 0, 6.3); c.clip(); c.drawImage(X.fx(P.img, 'fit', 600, 600), W / 2 - fs / 2, 420 - fs / 2, fs, fs); c.restore();
        c.save(); c.strokeStyle = pal.fg; c.lineWidth = 14; c.beginPath(); c.arc(W / 2, 420, fs * .5, 0, 6.3); c.stroke(); c.restore(); }
      else { c.save(); c.translate(W / 2, 420); c.rotate(t * .25); c.drawImage(X.flower, -fs / 2, -fs / 2, fs, fs); c.restore(); }
      for(let k = 0; k < 6; k++){ const a = t * .6 + k * Math.PI / 3; c.save(); c.translate(W / 2 + Math.cos(a) * 546, 420 + Math.sin(a) * 231); c.rotate(-t); c.drawImage(X.flower, -45, -45, 90, 90); c.restore(); }
      if(burst > 0 && burst < 3){ const r = M.rng('burst' + Lc.i);
        for(let k = 0; k < 40; k++){ const a = r() * 6.3, v = 500 + r() * 900, d = v * burst - 200 * burst * burst;
          c.save(); c.globalAlpha = clamp(1 - burst / 3); c.translate(W / 2 + Math.cos(a) * d, 420 + Math.sin(a) * d + 300 * burst * burst); c.rotate(burst * 5 * (r() - .5));
          const s = 30 + r() * 40; c.drawImage(X.flower, -s / 2, -s / 2, s, s); c.restore(); } }
      c.font = D.F('serif', 124);
      M.karaRows(c, Lc, t, { maxW: 1500, lh: 150, cy: 860, dim: 'rgba(255,246,227,.45)', on: pal.hi, stroke: pal.band, strokeW: 18 });
    },
  });

  def('interlude', {
    doc: 'ช่วงดนตรี (ไม่มีเนื้อ): รูปเม็ดสกรีนทองบนพื้นเข้ม + แท่งเสียงจริงจากเพลง + ข้อความกลางจอ + บรรทัดถัดไป + นับถอยหลัง — ระบบใส่ให้เองทุกช่วงเงียบเกิน 7 วิ',
    params: { img: 'รูป (เช่น หมอลำเป่าแคน / วงดนตรี)', text: 'ข้อความใหญ่ เช่น "♪ ม่วนซื่น ♪"' },
    noStrip: true,
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, seg, meta, acc } = X, p = M.clamp((t - seg.t0) / 24), nx = Lc;
      c.fillStyle = th.light ? '#1d2a5c' : th.bg; c.fillRect(0, 0, W, H);
      if(P.img){ M.kenBurns(c, X.fx(P.img, 'htdark', 1920, 1080, { paper: th.light ? '#1d2a5c' : '#0b0b12', c1: th.acc[1] || '#f2b632' }), p, { z0: 1.2, z1: 1.02, dy: .05 });
        c.fillStyle = 'rgba(0,0,0,.3)'; c.fillRect(0, 0, W, H); }
      const lv = M.levels(36, t), bw = W / 36;
      c.save(); c.globalCompositeOperation = 'lighter';
      lv.forEach((v, k) => { const h = 30 + v * 360; c.fillStyle = k % 2 ? (th.acc[1] || '#f2b632') : acc; c.globalAlpha = .55; c.fillRect(k * bw + 6, H - h, bw - 12, h); });
      c.restore();
      D.txt(c, D.F('big', 80), th.acc[1] || '#f2b632', P.text || '♪  ดนตรี  ♪', W / 2, 200, { stroke: '#000', sw: 14 });
      D.txt(c, D.F('thin', 34), '#fff', `${meta.title} · ${meta.artist}`, W / 2, 260);
      if(nx && t > nx.t0 - 6){ c.globalAlpha = M.clamp((t - nx.t0 + 6) / 1); c.fillStyle = 'rgba(0,0,0,.6)'; c.fillRect(0, H - 300, W, 120);
        D.txt(c, D.F('thin', 50), '#fff', nx.text, W / 2, H - 222); c.globalAlpha = 1; }
      D.countdown(c, t, nx, th.acc[1] || '#f2b632', H - 330);
    },
  });

  def('river', {
    doc: 'สายน้ำยามค่ำ คลื่นเส้นทองเคลื่อน ดอกไม้ลอยตามน้ำพร้อมเงาสะท้อน — "ลอยล่อง", "สายน้ำ", "ปล่อยไป", "แม่น้ำ"',
    params: { img: 'รูปท้องฟ้า/ภูมิทัศน์ครึ่งบน' },
    prep(X){ X.fx(X.P.img, 'htdark', 1920, 1080, { c1: '#f2b632' }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc } = X, p = M.clamp((t - Lc.t0) / Math.max(1, Lc.t1 - Lc.t0));
      c.fillStyle = '#0b1030'; c.fillRect(0, 0, W, H);
      c.save(); c.beginPath(); c.rect(0, 0, W, 640); c.clip(); M.kenBurns(c, X.fx(P.img, 'htdark', 1920, 1080, { c1: '#f2b632' }), p, { z0: 1.1, z1: 1.2, dy: -.05 }); c.restore();
      const wg = c.createLinearGradient(0, 600, 0, H); wg.addColorStop(0, '#16205a'); wg.addColorStop(1, '#070a20'); c.fillStyle = wg; c.fillRect(0, 600, W, H - 600);
      c.save(); c.strokeStyle = 'rgba(242,182,50,.45)'; c.lineWidth = 3;
      for(let k = 0; k < 14; k++){ const y = 630 + k * 32, amp = 6 + k * 1.5; c.beginPath(); for(let x = 0; x <= W; x += 20) c.lineTo(x, y + Math.sin(x * .012 + t * (1.2 + k * .05) + k) * amp); c.globalAlpha = .9 - k * .05; c.stroke(); }
      c.restore();
      const fx = M.lerp(-100, W + 100, p), fy = 690 + Math.sin(t * 1.8) * 12;
      c.save(); c.translate(fx, fy); c.rotate(Math.sin(t * 1.2) * .15); c.drawImage(X.flower, -80, -80, 160, 160); c.restore();
      c.save(); c.globalAlpha = .3; c.translate(fx, fy + 90); c.scale(1, -.4); c.drawImage(X.flower, -80, -80, 160, 160); c.restore();
      c.fillStyle = 'rgba(7,10,32,.6)'; c.fillRect(0, 170, W, 270);
      c.font = D.F('script', 92); M.karaRows(c, Lc, t, { maxW: 1350, lh: 124, cy: 300, dim: 'rgba(242,236,255,.32)', on: '#ffe6a8', glow: '#f2b632', glowB: 20 });
    },
  });

  def('toss', {
    doc: 'ดอกไม้ถูกโยนทิ้งโค้งข้ามจอ เส้นความเร็ว คำกระเด็นเข้ามาเอียง ๆ — "โยนทิ้ง", "ทิ้งขว้าง", "ไม่เหลียวแล" (บรรทัดสั้น เร็ว)',
    params: { acc: 'สีคำ' },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X, p = M.clamp((t - Lc.t0) / 2.6);
      c.drawImage(paper(M, th.light ? th.paper : '#15131b'), 0, 0);
      c.save(); c.strokeStyle = acc + '8c'; c.lineWidth = 6; const r0 = M.rng('speed');
      for(let k = 0; k < 26; k++){ const y = r0() * H, x = (r0() * W + t * 2400) % (W + 400) - 200; c.beginPath(); c.moveTo(x, y); c.lineTo(x - 260, y); c.stroke(); } c.restore();
      const fx = M.lerp(300, W + 200, p), fy = 760 - Math.sin(p * Math.PI) * 600;
      c.save(); c.translate(fx, fy); c.rotate(p * 14); c.drawImage(X.flower, -110, -110, 220, 220); c.restore();
      c.font = D.F('big', 120);
      const pos = M.layoutWords(c, Lc.words, 1600, 140, W / 2, 560), r = M.rng('toss'); c.textAlign = 'left'; c.textBaseline = 'middle';
      pos.forEach(q => { const a = r() - .5, on = t >= q.w.t0, k = on ? M.ease.back(M.clamp((t - q.w.t0) / .3)) : 0;
        c.save(); c.translate(q.x + q.width / 2, q.y + a * 40); c.rotate(a * .5 * (on ? 1 : .3)); c.scale(on ? .6 + .4 * k : 1, on ? .6 + .4 * k : 1);
        c.fillStyle = on ? acc : (th.light ? 'rgba(29,42,92,.3)' : th.dim); c.fillText(q.w.s, -q.width / 2, 0); c.restore(); });
    },
  });

  def('poster', {
    doc: 'โปสเตอร์ให้กำลังใจ: รูปเม็ดสกรีนทางขวา ตราวงกลมหมุนมีข้อความรอบวง ข้อความใหญ่ทางซ้าย — ประโยคปลอบใจ/ยืนยันตัวตน "ยังเป็นฉัน", "อย่าเศร้า"',
    params: { img: 'รูป', ring: 'ข้อความรอบตรา (ลงท้ายด้วย " · ")', acc: 'สีเน้น' },
    prep(X){ X.fx(X.P.img, 'htcolor', 860, 1000, { mode: 'contain', pad: 20 }); },
    draw(c, t, X){
      const { M, D, th, W, H, P, Lc, acc } = X;
      c.drawImage(paper(M, th.paper), 0, 0);
      c.save(); c.globalCompositeOperation = 'multiply'; c.drawImage(X.fx(P.img, 'htcolor', 860, 1000, { mode: 'contain', pad: 20 }), W - 960, 40); c.restore();
      c.save(); c.translate(W - 520, 760); c.rotate(t * .4);
      c.fillStyle = th.acc[1] || '#f2b632'; c.beginPath(); c.arc(0, 0, 160, 0, 6.3); c.fill();
      c.strokeStyle = th.ink; c.lineWidth = 5; c.beginPath(); c.arc(0, 0, 150, 0, 6.3); c.stroke(); c.beginPath(); c.arc(0, 0, 92, 0, 6.3); c.stroke();
      c.font = D.F('body', 34); c.fillStyle = th.ink; c.textAlign = 'center';
      const ring = P.ring || '♥ · ♥ · ♥ · ♥ · ';
      [...ring].forEach((ch, k) => { c.save(); c.rotate(k / ring.length * 6.283); c.fillText(ch, 0, -112); c.restore(); });
      c.drawImage(X.flower, -70, -70, 140, 140); c.restore();
      c.font = D.F('big', 92); M.karaRows(c, Lc, t, { maxW: 1000, lh: 120, cx: 590, cy: H / 2, dim: 'rgba(29,42,92,.28)', on: acc });
      D.frame(c, acc, 46, X.flower);
    },
  });
})();
