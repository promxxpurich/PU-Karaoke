// ===== MV จากเนื้อเพลง: เครื่องยนต์กลาง (ใช้กับ static/mv/scenes.js + บทของเพลง mv.json) =====
// ใช้ได้ 2 แบบ: หน้าเดี่ยว static/mv/mv.html (มีเสียง + แถบควบคุม) / ฝังในจอทีวี (o.canvas + o.clock = เวลาจากวิดีโอ)
// - โหลดเนื้อ (lyrics.json) + เวลารายตัวอักษร (lyrics.words.json) -> บรรทัด / คำ (Intl.Segmenter) / เวลาแต่ละตัว
// - นาฬิกาเพลง = audio.currentTime (?t=วินาที เริ่มกลางเพลง, ?still=วินาที ภาพนิ่งไม่เล่นเสียง ไว้แคปจอ)
// - ตัวช่วยภาพ: เม็ดสกรีน (halftone) / ลายเส้น (line art) / กระดาษ / เกรนฟิล์ม / ดอกจำปา — คำนวณครั้งเดียวตอนโหลด
// - วาดทั้งหมดบน canvas 2D ขนาดคงที่ 1920×1080 แล้วย่อให้พอดีจอ (ไม่มีไฟล์วิดีโอ ไม่แปลงอะไรในเครื่อง)
const MV = (() => {
  const W = 1920, H = 1080;
  const qs = new URLSearchParams(location.search);
  const STILL = qs.has('still') ? +qs.get('still') : null;
  let cv, ctx, audio, buf, bctx, lines = [], beats = [], scenes = [], curScene = -1, fps = 0;

  // ---------- สุ่มแบบคงที่ (seed เดียวกัน = ได้ฉากเหมือนเดิมทุกครั้ง) ----------
  function rng(seed){
    let s = 0; for(const ch of String(seed)) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
    return () => { s = (s + 0x6D2B79F5) >>> 0; let x = s; x = Math.imul(x ^ x >>> 15, x | 1);
      x ^= x + Math.imul(x ^ x >>> 7, x | 61); return ((x ^ x >>> 14) >>> 0) / 4294967296; };
  }
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, p) => a + (b - a) * p;
  const ease = {
    out: p => 1 - Math.pow(1 - clamp(p), 3),
    inOut: p => { p = clamp(p); return p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; },
    back: p => { p = clamp(p); const c = 1.9; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); },
    elastic: p => { p = clamp(p); return p === 0 || p === 1 ? p : Math.pow(2, -10 * p) * Math.sin((p * 10 - .75) * 2.094) + 1; },
  };

  // ---------- เนื้อเพลง ----------
  const segW = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('th', { granularity: 'word' }) : null;
  const segG = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('th', { granularity: 'grapheme' }) : null;

  // off = ค่าเลื่อนเวลาเนื้อประจำเพลง (lyrOffset): เวลาบรรทัดใน lyrics.json = เวลาเนื้อ, เวลารายตัว (k) = เวลาในเสียง -> หัก off ให้เป็นเวลาเนื้อ
  let kOff = 0;
  async function loadSong(base, off = 0){
    kOff = off;
    const [ly, wd] = await Promise.all([
      fetch(base + 'lyrics.json', { cache: 'no-store' }).then(r => r.json()),
      fetch(base + 'lyrics.words.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    beats = await fetch(base + 'mv_beats.json').then(r => r.ok ? r.json() : null).catch(() => null);
    beats = beats && Array.isArray(beats.beats) ? beats.beats : [];
    lines = ly.lines.map((L, i) => buildLine(L, i, wd));
    for(let i = 0; i < lines.length; i++) lines[i].next = lines[i + 1] || null;
    return { lines, duration: ly.duration || 0, meta: ly };
  }

  function buildLine(L, i, wd){
    const text = L.x, n = text.length;
    let k = wd && wd.texts && wd.texts[i] === text ? wd.k[i] : null;
    const ct = new Array(n).fill(null);
    if(k && k.length){ for(const [ci, t] of k) if(ci < n) ct[ci] = t - kOff; }
    else for(let c = 0; c < n; c++) ct[c] = L.t + L.d * 0.85 * c / n;   // ไม่มีเวลารายตัว -> เกลี่ยทั้งบรรทัด
    // เติมช่องว่าง: ใช้เวลาตัวก่อนหน้า (ช่องว่าง/สระที่ FA ไม่ได้จับ)
    let last = ct.find(v => v != null) ?? L.t;
    for(let c = 0; c < n; c++){ if(ct[c] == null) ct[c] = last; else last = ct[c]; }
    const tEnd = Math.min(L.t + L.d, ct[n - 1] + 0.6);
    // กลุ่มอักษร (สระ/วรรณยุกต์ติดกับตัวหน้า) — ใช้ตัดสีไล่คาราโอเกะ
    const gs = [];
    if(segG) for(const g of segG.segment(text)) gs.push({ i0: g.index, i1: g.index + g.segment.length });
    else for(let c = 0; c < n; c++) gs.push({ i0: c, i1: c + 1 });
    gs.forEach((g, j) => { g.t0 = ct[g.i0]; g.t1 = j + 1 < gs.length ? Math.max(ct[gs[j + 1].i0], g.t0 + .04) : tEnd; g.t1 = Math.min(g.t1, g.t0 + 0.7); });
    // คำ
    const words = [];
    const parts = segW ? [...segW.segment(text)].map(s => ({ s: s.segment, i0: s.index }))
                       : text.split(/(\s+)/).reduce((a, s) => { a.push({ s, i0: a.length ? a[a.length - 1].i0 + a[a.length - 1].s.length : 0 }); return a; }, []);
    for(const p of parts){
      if(/^\s+$/.test(p.s)){ if(words.length) words[words.length - 1].gap = true; continue; }
      words.push({ s: p.s, i0: p.i0, i1: p.i0 + p.s.length, t0: ct[p.i0], gap: false });
    }
    words.forEach((w, j) => { w.t1 = j + 1 < words.length ? words[j + 1].t0 : tEnd; w.idx = j; });
    return { i, text, t0: L.t, t1: L.t + L.d, tSing0: ct[0], tSing1: tEnd, ct, gs, words };
  }

  // จำนวนตัวอักษรที่ร้องไปแล้ว (มีเศษ) ณ เวลา t
  function sung(line, t){
    if(t <= line.gs[0].t0) return 0;
    for(const g of line.gs){
      if(t < g.t0) return g.i0;
      if(t < g.t1) return g.i0 + (g.i1 - g.i0) * (t - g.t0) / (g.t1 - g.t0);
    }
    return line.text.length;
  }
  // บีตกลอง (mv_beats.json จาก scripts/mv_prep.py): 0..1 ลดลงหลังบีตล่าสุด / ไม่มีไฟล์ = 0
  function beat(t, k = 8){
    if(!beats.length) return 0;
    let lo = 0, hi = beats.length - 1;
    if(t < beats[0]) return 0;
    while(lo < hi){ const m = (lo + hi + 1) >> 1; if(beats[m] <= t) lo = m; else hi = m - 1; }
    return Math.exp(-(t - beats[lo]) * k);
  }
  const lineAt = t => { let r = null; for(const L of lines){ if(L.t0 - 0.05 <= t) r = L; else break; } return r; };
  const activeLine = t => lines.find(L => t >= L.t0 - .05 && t < L.t1) || null;
  const nextLine = t => lines.find(L => L.t0 > t) || null;
  const wordAt = (line, t) => { let r = -1; for(const w of line.words) if(t >= w.t0) r = w.idx; return r; };

  // ---------- ตัวอักษร ----------
  // วาดข้อความแบบไล่สีคาราโอเกะ: ทั้งบรรทัดเป็นสีจาง แล้วตัด clip ทับด้วยสีที่ร้องแล้ว (ปลอดภัยกับสระบน/ล่าง)
  function karaText(c, text, x, y, done, o = {}){
    c.save();
    c.textAlign = 'left'; c.textBaseline = o.baseline || 'alphabetic';
    const full = c.measureText(text).width;
    const x0 = o.align === 'center' ? x - full / 2 : o.align === 'right' ? x - full : x;
    const fl = Math.floor(done), pre = c.measureText(text.slice(0, fl)).width;
    const nxt = fl < text.length ? c.measureText(text.slice(0, fl + 1)).width : pre;
    const cut = x0 + pre + (nxt - pre) * (done - fl);
    if(o.stroke){ c.lineJoin = 'round'; c.lineWidth = o.strokeW || 10; c.strokeStyle = o.stroke; c.strokeText(text, x0, y); }
    c.fillStyle = o.dim || 'rgba(255,255,255,.45)'; c.fillText(text, x0, y);
    if(done > 0){
      c.beginPath(); c.rect(x0 - 40, y - 400, cut - x0 + 40, 800); c.clip();
      if(o.glow){ c.shadowColor = o.glow; c.shadowBlur = o.glowB || 24; }
      c.fillStyle = o.on || '#fff'; c.fillText(text, x0, y);
    }
    c.restore();
    return { x0, w: full, cut };
  }

  // บรรทัดยาว -> ตัดเป็นหลายแถวตามคำ แล้วไล่สีคาราโอเกะต่อเนื่องข้ามแถว
  function karaRows(c, line, t, o){
    const pos = layoutWords(c, line.words, o.maxW || 1600, o.lh || 120, o.cx ?? W / 2, o.cy ?? H / 2);
    const rows = [];
    for(const p of pos){ (rows[p.row] ||= { i0: p.w.i0, i1: p.w.i1, y: p.y }).i1 = p.w.i1; }
    const done = sung(line, t), out = [];
    for(const r of rows){
      const txt = line.text.slice(r.i0, r.i1).trim();
      out.push(karaText(c, txt, o.cx ?? W / 2, r.y, clamp(done - r.i0, 0, txt.length), { ...o, align: 'center' }));
    }
    return out;
  }
  // จัดคำเป็นหลายบรรทัดให้กว้างไม่เกิน maxW -> [{w, x, y, width}] (x,y = มุมซ้าย baseline)
  function layoutWords(c, words, maxW, lh, cx = W / 2, cy = H / 2, align = 'center', balance = true){
    if(balance){
      const n = layoutWords(c, words, maxW, lh, cx, cy, align, false).rows;
      if(n > 1){
        // ไม่บีบให้แคบกว่าวลีที่ยาวที่สุด (กันวลีถูกหั่นกลาง เช่น วัน|นี้)
        let ph = 0, acc = 0;
        for(const w of words){ acc += c.measureText(w.s).width; if(w.gap){ ph = Math.max(ph, acc); acc = 0; } }
        ph = Math.max(ph, acc);
        let lo = Math.max(maxW / n, ph <= maxW ? ph : 0), hi = maxW;
        for(let k = 0; k < 10; k++){ const mid = (lo + hi) / 2; if(layoutWords(c, words, mid, lh, cx, cy, align, false).rows > n) lo = mid; else hi = mid; }
        maxW = hi + 1; }
    }
    // ตัดแถวที่ช่องว่างในเนื้อก่อน (ช่องว่าง = จบวลี) ตัดกลางวลีเฉพาะวลีที่ยาวเกินแถวเดียว
    const sp = c.measureText(' ').width * .9, units = [];
    let cur = [];
    for(const w of words){ cur.push(w); if(w.gap){ units.push(cur); cur = []; } }
    if(cur.length) units.push(cur);
    const unitsW = [];
    for(const u of units){
      const ws = u.map(w => c.measureText(w.s).width), tw = ws.reduce((a, b) => a + b, 0);
      if(tw > maxW && u.length > 1) u.forEach((w, k) => unitsW.push({ ws: [w], wd: [ws[k]], tw: ws[k], gap: k === u.length - 1 }));
      else unitsW.push({ ws: u, wd: ws, tw, gap: true });
    }
    const rows = [[]]; let rw = 0, lastGap = false;
    for(const u of unitsW){
      const row0 = rows[rows.length - 1], gap = row0.length && lastGap ? sp : 0;
      if(rw + gap + u.tw > maxW && row0.length){ rows.push([]); rw = 0; }
      const row = rows[rows.length - 1], g2 = row.length && lastGap ? sp : 0;
      let off = rw + g2;
      u.ws.forEach((w, k) => { row.push({ w, width: u.wd[k], off }); off += u.wd[k]; });
      rw = off; row.rw = rw; lastGap = u.gap;
    }
    const out = [], top = cy - (rows.length - 1) * lh / 2;
    rows.forEach((row, ri) => {
      const rwid = row.rw || 0;
      const x0 = align === 'left' ? cx : align === 'right' ? cx - rwid : cx - rwid / 2;
      for(const it of row) out.push({ w: it.w, x: x0 + it.off, y: top + ri * lh, width: it.width, row: ri });
    });
    out.rows = rows.length;
    return out;
  }
  // ขนาดฟอนต์ที่ใหญ่สุดที่บรรทัดยังไม่เกิน maxRows แถว
  function fitFont(c, words, fam, maxW, maxRows, big, small = 40){
    for(let px = big; px >= small; px -= 6){
      c.font = fam.replace('#', px);
      if(layoutWords(c, words, maxW, px * 1.25, W / 2, H / 2, 'center', false).rows <= maxRows) return px;
    }
    return small;
  }

  // ---------- รูป ----------
  const imgCache = {};
  function loadImg(src){
    if(imgCache[src]) return imgCache[src];
    return imgCache[src] = new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = src; });
  }
  function canvas(w = W, h = H){ const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
  // วางรูปแบบ cover/contain ลง canvas ขนาด w×h (fx,fy = จุดโฟกัส 0..1)
  function fit(img, w, h, mode = 'cover', bg = '#fff', fx = .5, fy = .5, pad = 0){
    const c = canvas(w, h), g = c.getContext('2d');
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    const s = mode === 'cover' ? Math.max(w / img.width, h / img.height) : Math.min((w - pad * 2) / img.width, (h - pad * 2) / img.height);
    const dw = img.width * s, dh = img.height * s;
    g.drawImage(img, (w - dw) * fx, (h - dh) * fy, dw, dh);
    return c;
  }
  // ตัดขอบขาว/ขอบกระดาษของภาพพฤกษศาสตร์ให้พื้นหลังโปร่ง (ไว้วางบนพื้นสีอื่น)
  function knockout(img, thr = 225){
    const c = canvas(img.width, img.height), g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
    for(let i = 0; i < p.length; i += 4){
      const m = Math.min(p[i], p[i + 1], p[i + 2]), sat = Math.max(p[i], p[i + 1], p[i + 2]) - m;
      p[i + 3] = sat > 55 ? 255 : Math.round(255 * clamp((thr + 15 - m) / 30));   // ขาว/ครีม -> โปร่ง
    }
    g.putImageData(d, 0, 0);
    return c;
  }
  function lumData(src, w, h){
    const g = src.getContext('2d'), d = g.getImageData(0, 0, w, h).data, L = new Float32Array(w * h);
    for(let i = 0, j = 0; i < d.length; i += 4, j++) L[j] = (d[i] * .299 + d[i + 1] * .587 + d[i + 2] * .114) / 255;
    return L;
  }
  // เม็ดสกรีน: layers = [{color, angle, cell, ch:'lum'|'r'|'g'|'b'|'inv', gain}] ซ้อนแบบ multiply เหมือนงานพิมพ์ riso
  function halftone(img, o = {}){
    const w = o.w || W, h = o.h || H;
    const base = img.width === w && img.height === h && img.getContext ? img : fit(img, w, h, o.mode || 'cover', o.bg || '#fff', o.fx ?? .5, o.fy ?? .5, o.pad || 0);
    const bd = base.getContext('2d').getImageData(0, 0, w, h).data;
    const out = canvas(w, h), g = out.getContext('2d');
    g.fillStyle = o.paper || '#f3ead8'; g.fillRect(0, 0, w, h);
    const contrast = o.contrast ?? 1.25, gamma = o.gamma ?? 1;
    for(const L of (o.layers || [{ color: o.ink || '#1d1a2e', angle: 45, cell: o.cell || 10 }])){
      const cell = L.cell || 10, a = (L.angle || 0) * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
      const R = Math.hypot(w, h) / 2 + cell, cx = w / 2, cy = h / 2;
      g.save(); g.globalCompositeOperation = L.blend || (L.inv ? 'screen' : 'multiply'); g.fillStyle = L.color; g.beginPath();
      const ox = L.ox || 0, oy = L.oy || 0;
      for(let v = -R; v < R; v += cell) for(let u = -R; u < R; u += cell){
        const x = cx + u * ca - v * sa, y = cy + u * sa + v * ca;
        if(x < -cell || y < -cell || x > w + cell || y > h + cell) continue;
        const xi = clamp(Math.round(x), 0, w - 1), yi = clamp(Math.round(y), 0, h - 1), p = (yi * w + xi) * 4;
        let r = bd[p] / 255, gg = bd[p + 1] / 255, b = bd[p + 2] / 255, val;
        const lum = r * .299 + gg * .587 + b * .114;
        switch(L.ch){
          case 'r': val = 1 - r; break; case 'g': val = 1 - gg; break; case 'b': val = 1 - b; break;
          case 'sat': val = Math.max(r, gg, b) - Math.min(r, gg, b); break;
          default: val = 1 - lum;
        }
        if(L.inv) val = 1 - val;   // พิมพ์หมึกสว่างบนพื้นมืด
        val = clamp(((val - .5) * contrast + .5) * (L.gain || 1));
        val = Math.pow(val, gamma);
        const rad = cell * .62 * Math.sqrt(val);
        if(rad < .35) continue;
        g.moveTo(x + ox + rad, y + oy); g.arc(x + ox, y + oy, rad, 0, 6.2832);
      }
      g.fill(); g.restore();
    }
    return out;
  }
  // ลายเส้น: ขอบ Sobel + เส้นแรเงาเฉียงในที่มืด, พื้นโปร่ง (วางบนกระดาษ/สีอะไรก็ได้)
  function lineArt(img, o = {}){
    const w = o.w || W, h = o.h || H, sc = o.scale || .5, sw = Math.round(w * sc), sh = Math.round(h * sc);
    const base = fit(img, sw, sh, o.mode || 'cover', o.bg || '#fff', o.fx ?? .5, o.fy ?? .5, (o.pad || 0) * sc);
    const L = lumData(base, sw, sh), E = new Float32Array(sw * sh);
    for(let y = 1; y < sh - 1; y++) for(let x = 1; x < sw - 1; x++){
      const i = y * sw + x;
      const gx = -L[i - sw - 1] - 2 * L[i - 1] - L[i + sw - 1] + L[i - sw + 1] + 2 * L[i + 1] + L[i + sw + 1];
      const gy = -L[i - sw - 1] - 2 * L[i - sw] - L[i - sw + 1] + L[i + sw - 1] + 2 * L[i + sw] + L[i + sw + 1];
      E[i] = Math.hypot(gx, gy);
    }
    const out = canvas(sw, sh), g = out.getContext('2d'), d = g.createImageData(sw, sh), p = d.data;
    const [ir, ig, ib] = hex(o.ink || '#1b1b2f'), thr = o.thr ?? .28, hatch = o.hatch ?? .38;
    for(let y = 0; y < sh; y++) for(let x = 0; x < sw; x++){
      const i = y * sw + x;
      let a = clamp((E[i] - thr) / .35);
      if(hatch && L[i] < hatch && (x + y) % 7 === 0) a = Math.max(a, .75);
      if(hatch && L[i] < hatch * .55 && (x - y + 999) % 7 === 0) a = Math.max(a, .75);
      p[i * 4] = ir; p[i * 4 + 1] = ig; p[i * 4 + 2] = ib; p[i * 4 + 3] = a * 255;
    }
    g.putImageData(d, 0, 0);
    if(sc === 1) return out;
    const big = canvas(w, h), bg = big.getContext('2d'); bg.imageSmoothingQuality = 'high'; bg.drawImage(out, 0, 0, w, h);
    return big;
  }
  // ย้อมสองสี (เงา = dark, สว่าง = light)
  function duotone(img, dark, light, o = {}){
    const w = o.w || W, h = o.h || H, c = fit(img, w, h, o.mode || 'cover', o.bg || '#fff', o.fx ?? .5, o.fy ?? .5, o.pad || 0);
    const g = c.getContext('2d'), d = g.getImageData(0, 0, w, h), p = d.data, A = hex(dark), B = hex(light);
    const k = o.contrast ?? 1.2;
    for(let i = 0; i < p.length; i += 4){
      const l = clamp(((p[i] * .299 + p[i + 1] * .587 + p[i + 2] * .114) / 255 - .5) * k + .5);
      p[i] = A[0] + (B[0] - A[0]) * l; p[i + 1] = A[1] + (B[1] - A[1]) * l; p[i + 2] = A[2] + (B[2] - A[2]) * l;
    }
    g.putImageData(d, 0, 0);
    return c;
  }
  function hex(h){ const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }

  // กระดาษเก่า: ลายเยื่อ + จุดด่าง (สร้างครั้งเดียว ใช้เป็น pattern)
  let paperC = null;
  function paper(tint = '#efe4cc'){
    const c = canvas(W, H), g = c.getContext('2d'), r = rng('paper');
    g.fillStyle = tint; g.fillRect(0, 0, W, H);
    if(!paperC){
      paperC = canvas(512, 512); const pg = paperC.getContext('2d'), d = pg.createImageData(512, 512);
      for(let i = 0; i < d.data.length; i += 4){ const v = 128 + (r() - .5) * 46; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
      pg.putImageData(d, 0, 0);
    }
    g.save(); g.globalCompositeOperation = 'overlay'; g.globalAlpha = .35; g.fillStyle = g.createPattern(paperC, 'repeat'); g.fillRect(0, 0, W, H); g.restore();
    g.save(); g.globalCompositeOperation = 'multiply';
    for(let i = 0; i < 90; i++){ g.globalAlpha = .015 + r() * .025; g.fillStyle = '#8a6a3a';
      g.beginPath(); g.ellipse(r() * W, r() * H, 8 + r() * 60, 6 + r() * 40, r() * 3, 0, 6.3); g.fill(); }
    const vg = g.createRadialGradient(W / 2, H / 2, H * .35, W / 2, H / 2, H * .95);
    vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(90,60,20,.35)');
    g.globalAlpha = 1; g.fillStyle = vg; g.fillRect(0, 0, W, H); g.restore();
    return c;
  }
  // เกรนฟิล์มขยับทุกเฟรม (3 แผ่นสลับกัน ถูกมาก)
  const grains = [];
  function grain(c, a = .07){
    if(!grains.length) for(let k = 0; k < 3; k++){
      const gcv = canvas(480, 270), g = gcv.getContext('2d'), d = g.createImageData(480, 270), r = rng('g' + k);
      for(let i = 0; i < d.data.length; i += 4){ const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
      g.putImageData(d, 0, 0); grains.push(gcv);
    }
    c.save(); c.globalAlpha = a; c.globalCompositeOperation = 'overlay';
    c.drawImage(grains[(frame >> 1) % 3], 0, 0, W, H); c.restore();
  }
  const vigCache = {};
  function vignette(c, a = .5, col = '0,0,0'){
    const k = a + col;
    if(!vigCache[k]){ const v = canvas(480, 270), g = v.getContext('2d'), vg = g.createRadialGradient(240, 135, 270 * .3, 240, 135, 270 * 1.05);
      vg.addColorStop(0, `rgba(${col},0)`); vg.addColorStop(1, `rgba(${col},${a})`); g.fillStyle = vg; g.fillRect(0, 0, 480, 270); vigCache[k] = v; }
    c.drawImage(vigCache[k], 0, 0, W, H);
  }
  // Ken Burns: วาดภาพพร้อมซูม/เลื่อนช้า ๆ ตาม p (0..1)
  function kenBurns(c, img, p, o = {}){
    const z0 = o.z0 ?? 1.04, z1 = o.z1 ?? 1.16, z = lerp(z0, z1, ease.inOut(p));
    const dx = (o.dx ?? 0) * W * (p - .5), dy = (o.dy ?? 0) * H * (p - .5);
    const w = W * z, h = H * z;
    c.drawImage(img, (W - w) / 2 + dx, (H - h) / 2 + dy, w, h);
  }

  // ดอกจำปา (ลีลาวดีแบบลาว) 5 กลีบ บิดเวียน — วาดเป็นสไปรต์ครั้งเดียว
  const flowerCache = {};
  function flowerSprite(size = 256, petal = '#fffaf0', heart = '#ffc93c', edge = 'rgba(0,0,0,.18)'){
    const key = size + petal + heart;
    if(flowerCache[key]) return flowerCache[key];
    const c = canvas(size, size), g = c.getContext('2d'), R = size * .47;
    g.translate(size / 2, size / 2);
    for(let i = 0; i < 5; i++){
      g.save(); g.rotate(i * Math.PI * 2 / 5);
      g.beginPath(); g.moveTo(0, 0);
      g.bezierCurveTo(R * .15, -R * .15, R * .55, -R * .62, R * .2, -R * .98);
      g.bezierCurveTo(-R * .05, -R * 1.08, -R * .42, -R * .7, -R * .28, -R * .38);
      g.bezierCurveTo(-R * .2, -R * .18, -R * .08, -R * .06, 0, 0);
      const gr = g.createLinearGradient(0, 0, 0, -R);
      gr.addColorStop(0, heart); gr.addColorStop(.42, petal); gr.addColorStop(1, petal);
      g.fillStyle = gr; g.fill(); g.lineWidth = size / 160; g.strokeStyle = edge; g.stroke();
      g.restore();
    }
    g.beginPath(); g.arc(0, 0, R * .07, 0, 6.3); g.fillStyle = heart; g.fill();
    return flowerCache[key] = c;
  }

  // ---------- ฉาก + การเปลี่ยนฉาก ----------
  // scene = {t0, t1, name, draw(ctx, t, sc), trans:'fade'|'wipe'|'iris'|'slide'|'cut', td}
  function setScenes(list){ scenes = list.sort((a, b) => a.t0 - b.t0); }
  function sceneIdx(t){ let r = 0; for(let i = 0; i < scenes.length; i++) if(scenes[i].t0 <= t) r = i; return r; }
  function renderScenes(t){
    const i = sceneIdx(t), sc = scenes[i];
    if(i !== curScene){ curScene = i; sc.enter && sc.enter(); }
    const td = sc.td ?? .7, p = i > 0 ? (t - sc.t0) / td : 1;
    if(p >= 1 || sc.trans === 'cut'){ sc.draw(ctx, t, sc); return sc; }
    const prev = scenes[i - 1];
    prev.draw(ctx, t, prev);
    bctx.setTransform(1, 0, 0, 1, 0, 0); bctx.globalAlpha = 1; bctx.globalCompositeOperation = 'source-over';
    bctx.clearRect(0, 0, W, H); sc.draw(bctx, t, sc);
    const e = ease.inOut(p);
    ctx.save();
    switch(sc.trans){
      case 'wipe': ctx.beginPath(); ctx.rect(0, 0, W * e, H); ctx.clip(); ctx.drawImage(buf, 0, 0); break;
      case 'iris': ctx.beginPath(); ctx.arc(sc.ix ?? W / 2, sc.iy ?? H / 2, e * Math.hypot(W, H) * .6, 0, 6.3); ctx.clip(); ctx.drawImage(buf, 0, 0); break;
      case 'slide': ctx.drawImage(buf, 0, (1 - e) * H); break;
      case 'blinds': for(let k = 0; k < 12; k++){ ctx.save(); ctx.beginPath(); ctx.rect(0, k * H / 12, W, H / 12 * e); ctx.clip(); ctx.drawImage(buf, 0, 0); ctx.restore(); } break;
      case 'glitch': {   // แถบภาพสุ่มเลื่อนเข้ามาทีละชิ้น + สีเหลื่อม
        const r = rng('gl' + i);
        for(let k = 0; k < 18; k++){ const y = r() * H, h = 20 + r() * 90, on = r() < e * 1.3, dx = (1 - e) * (r() - .5) * 400;
          if(on) ctx.drawImage(buf, 0, y, W, h, dx, y, W, h); }
        if(e > .7){ ctx.globalAlpha = (e - .7) / .3; ctx.drawImage(buf, 0, 0); }
        break; }
      default: ctx.globalAlpha = e; ctx.drawImage(buf, 0, 0);
    }
    ctx.restore();
    return sc;
  }

  // ---------- เวลา / เล่น / แถบควบคุม ----------
  let frame = 0, stillT = STILL, t0wall = performance.now();
  let clock = null, running = false, rafId = 0;
  const now = () => stillT != null ? stillT : clock ? clock() : audio ? audio.currentTime : (performance.now() - t0wall) / 1000;

  function ui(meta){
    const st = document.createElement('style');
    st.textContent = `
      html,body{margin:0;height:100%;background:#000;overflow:hidden;font-family:Kanit,system-ui,sans-serif}
      #mv{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%)}
      #bar{position:fixed;left:0;right:0;bottom:0;display:flex;gap:14px;align-items:center;padding:12px 18px;
        background:linear-gradient(0deg,rgba(0,0,0,.85),transparent);color:#fff;font-size:15px;opacity:0;transition:opacity .3s}
      body.ui #bar{opacity:1}
      #bar button{background:rgba(255,255,255,.14);color:#fff;border:0;border-radius:999px;padding:7px 16px;font:inherit;cursor:pointer}
      #bar input{flex:1;accent-color:#ff4d8d}
      #bar .sc{min-width:220px;opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #go{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;
        background:rgba(0,0,0,.72);color:#fff;cursor:pointer;z-index:5;text-align:center}
      #go b{font-size:46px;font-weight:600}#go span{opacity:.7;font-size:18px}
      #go i{font-style:normal;font-size:64px;width:120px;height:120px;border-radius:50%;display:grid;place-items:center;
        background:linear-gradient(135deg,#ff4d8d,#7c5cff)}`;
    document.head.appendChild(st);
    const bar = document.createElement('div'); bar.id = 'bar';
    bar.innerHTML = `<button id="pp">⏯</button><span id="tm">0:00</span><input id="sk" type="range" min="0" step="0.1" value="0">
      <span class="sc" id="scn"></span><span id="fps"></span>`;
    document.body.appendChild(bar);
    let hideT; const show = () => { document.body.classList.add('ui'); clearTimeout(hideT); hideT = setTimeout(() => document.body.classList.remove('ui'), 2500); };
    addEventListener('mousemove', show); addEventListener('touchstart', show);
    const sk = bar.querySelector('#sk'); sk.max = meta.duration || 240;
    sk.oninput = () => { if(audio) audio.currentTime = +sk.value; else stillT = +sk.value; };
    bar.querySelector('#pp').onclick = () => audio && (audio.paused ? audio.play() : audio.pause());
    addEventListener('keydown', e => {
      if(!audio) return;
      if(e.key === ' '){ e.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
      if(e.key === 'ArrowRight') audio.currentTime += 5;
      if(e.key === 'ArrowLeft') audio.currentTime -= 5;
    });
    setInterval(() => {
      const t = now(), m = Math.floor(t / 60), s = Math.floor(t % 60);
      bar.querySelector('#tm').textContent = `${m}:${String(s).padStart(2, '0')}`;
      if(document.activeElement !== sk) sk.value = t;
      bar.querySelector('#scn').textContent = scenes[curScene] ? scenes[curScene].name || '' : '';
      bar.querySelector('#fps').textContent = fps + ' fps';
    }, 250);
  }

  function resize(){
    const s = Math.min(innerWidth / W, innerHeight / H);
    cv.style.width = W * s + 'px'; cv.style.height = H * s + 'px';
  }

  // เริ่ม: fonts = รายชื่อ font ที่ต้องโหลดก่อนวาด, setup(api) -> คืน list ฉาก
  let gen = 0;
  async function start(o){
    const my = ++gen; running = false; cancelAnimationFrame(rafId);
    const embed = !!o.canvas;
    cv = o.canvas || document.createElement('canvas'); cv.width = W; cv.height = H;
    if(!embed){ cv.id = 'mv'; document.body.appendChild(cv); resize(); addEventListener('resize', resize); }
    ctx = cv.getContext('2d'); buf = canvas(); bctx = buf.getContext('2d');
    clock = o.clock || null; curScene = -1;
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    if(!embed){ ctx.fillStyle = '#fff'; ctx.font = '40px system-ui'; ctx.textAlign = 'center'; ctx.fillText('กำลังเตรียมฉาก…', W / 2, H / 2); }
    await Promise.all((o.fonts || []).map(f => document.fonts.load(f, 'ดอกจำปา Aa').catch(() => null)));
    const song = await loadSong(o.base, o.offset || 0);
    if(my !== gen) return null;   // ระหว่างโหลดมีการเริ่มเพลงใหม่แล้ว
    const list = await o.setup({ ...api, song, base: o.base });
    if(my !== gen) return null;
    setScenes(list);
    // อุ่นทุกฉากล่วงหน้า (แปลงรูปเป็นเม็ดสกรีน/ลายเส้นตอนนี้เลย ไม่ให้กระตุกตอนเปลี่ยนฉากกลางเพลง)
    for(const sc of scenes){ try{ bctx.setTransform(1, 0, 0, 1, 0, 0); sc.draw(bctx, Math.min(sc.t1, sc.t0 + 1.5), sc); }catch(e){} }
    if(!embed){
      ui(song.meta);
      if(STILL == null){
        audio = new Audio(o.base + 'audio.m4a'); audio.preload = 'auto';
        if(qs.has('t')) audio.addEventListener('loadedmetadata', () => { audio.currentTime = +qs.get('t'); }, { once: true });
        const go = document.createElement('div'); go.id = 'go';
        go.innerHTML = `<i>▶</i><b>${o.title || ''}</b><span>กดเพื่อเริ่ม · เว้นวรรค = เล่น/หยุด · ← → = กรอ 5 วิ</span>`;
        document.body.appendChild(go);
        go.onclick = () => {
          go.remove();
          try{   // ตัววัดเสียง (แท่งกราฟช่วงดนตรี) — ต้องสร้างตอนกดเท่านั้น ไม่งั้นเบราว์เซอร์ปิดเสียง
            const ac = new AudioContext(), src = ac.createMediaElementSource(audio);
            an = ac.createAnalyser(); an.fftSize = 256; an.smoothingTimeConstant = .75;
            src.connect(an); an.connect(ac.destination); anData = new Uint8Array(an.frequencyBinCount);
          }catch(e){ an = null; }
          audio.play();
        };
      }
    }
    let last = performance.now(), acc = 0, cnt = 0;
    running = true;
    const loop = ts => {
      if(!running || my !== gen) return;
      frame++; cnt++; acc += ts - last; last = ts;
      if(acc > 1000){ fps = Math.round(cnt * 1000 / acc); acc = 0; cnt = 0; }
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      try{ renderScenes(now()); }catch(e){ console.error('mv', e); }
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
    window.__mvReady = true;
    if(qs.has('sheet')) sheet(qs.get('sheet').split(',').map(Number));
    return song;
  }
  function stop(){ gen++; running = false; cancelAnimationFrame(rafId); scenes = []; curScene = -1; }
  // ระดับเสียงจากภายนอก (จอทีวีส่ง analyser ของวิดีโอมาให้ได้)
  function setAnalyser(a){ an = a; anData = a ? new Uint8Array(a.frequencyBinCount) : null; }

  // แคปจอ: ตั้งเวลาแล้ววาดทันที (ใช้กับ headless)
  function seekStill(t){ stillT = t; ctx.setTransform(1, 0, 0, 1, 0, 0); renderScenes(t); }

  // ระดับเสียง n ช่อง 0..1 (ไม่มีตัววัด/ภาพนิ่ง -> คลื่นจำลอง)
  let an = null, anData = null;
  function levels(n, t){
    const out = new Array(n);
    if(an && anData && (!audio || !audio.paused)){
      an.getByteFrequencyData(anData);
      const m = Math.floor(anData.length * .7);
      for(let i = 0; i < n; i++){ const a = Math.floor(i * m / n), b = Math.max(a + 1, Math.floor((i + 1) * m / n));
        let s = 0; for(let j = a; j < b; j++) s += anData[j]; out[i] = s / (b - a) / 255; }
    } else for(let i = 0; i < n; i++) out[i] = .35 + .3 * Math.sin(t * 6 + i * .7) * Math.sin(t * 2.3 + i * .21);
    return out;
  }

  // ตารางภาพย่อหลายช่วงเวลา (ไว้ตรวจงาน: MV.sheet([10,20,30]) / ?sheet=10,20,30)
  function sheet(times, cols = 3){
    let s = document.getElementById('sheet');
    if(!s){ s = document.createElement('canvas'); s.id = 'sheet';
      s.style.cssText = 'position:fixed;inset:0;z-index:9;width:100vw;height:100vh;object-fit:contain;background:#222';
      s.onclick = () => s.remove(); document.body.appendChild(s); }
    const rows = Math.ceil(times.length / cols); s.width = cols * 640; s.height = rows * 360;
    const g = s.getContext('2d'); g.fillStyle = '#222'; g.fillRect(0, 0, s.width, s.height);
    times.forEach((t, i) => { seekStill(t); const x = (i % cols) * 640, y = Math.floor(i / cols) * 360;
      g.drawImage(cv, x, y, 636, 356); g.fillStyle = '#ff0'; g.font = '22px sans-serif'; g.fillText(t + 's', x + 8, y + 26); });
  }

  const api = { W, H, rng, clamp, lerp, ease, beat, sung, lineAt, activeLine, nextLine, wordAt, karaText, karaRows, layoutWords, fitFont,
    levels, loadImg, canvas, fit, knockout, halftone, lineArt, duotone, paper, grain, vignette, kenBurns, flowerSprite,
    get lines(){ return lines; }, get frame(){ return frame; } };
  return { start, stop, setAnalyser, seekStill, sheet, ...api, get lines(){ return lines; } };
})();
