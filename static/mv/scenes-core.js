// ===== คลังฉาก MV: แกนกลาง — ตัวช่วยวาด + ตัวอ่านบทของเพลง (mv.json) =====
// ฉากแต่ละแบบลงทะเบียนด้วย MVScenes.def(ชื่อ, {doc, params, lines, draw}) ในไฟล์ scenes-*.js
// draw(c, t, X): X = { M ตัวช่วยจาก engine, D ตัวช่วยวาด (helpers), Lc บรรทัดแรกของช่วง, Ls ทุกบรรทัดของช่วง, P พารามิเตอร์จากบท,
//                     th ธีม, acc สีเน้นของช่วงนี้, img(key) รูป, fx(key, แบบ, w, h) รูปที่แปลงแล้ว (แคช), seg ช่วงเวลา }
// บท (mv.json) ดูรูปแบบใน static/mv/CATALOG.md — สร้างจากรายการฉากด้วย node scripts/mv_catalog.js
const MVScenes = (() => {
  const REG = {};
  function def(name, spec){ REG[name] = { name, lines: 1, params: {}, ...spec }; }

  // ---------- ธีม ----------
  const TH0 = {
    bg: '#0a0a0d', fg: '#f5f5f7', dim: 'rgba(255,255,255,.35)', paper: '#f1ede6', ink: '#111114', grey: '#8b8b95',
    acc: ['#ff2e4d', '#b06cff', '#3fd0ff', '#ffd23f'], light: false,
    fonts: { big: '900 #px Kanit', bold: '800 #px Kanit', body: '600 #px Kanit', thin: '400 #px Kanit', hand: '#px Sriracha',
             ui: '700 #px "Chakra Petch"', serif: '#px Chonburi', script: '700 #px Charm' },
    grain: .07, lead: .06, tr: 'cut', td: .35, nextStrip: true,
  };
  const FONT_FILES = ['900 100px Kanit', '800 100px Kanit', '600 60px Kanit', '400 40px Kanit', '80px Sriracha',
    '700 60px "Chakra Petch"', '500 40px "Chakra Petch"', '80px Chonburi', '700 80px Charm', '400 80px Charm'];

  // ---------- ตัวช่วยวาด (ใช้ร่วมทุกฉาก) ----------
  function helpers(M, th){
    const { W, H, clamp, lerp, ease } = M;
    const F = (kind, px) => (th.fonts[kind] || th.fonts.bold).replace('#', px);
    const H_ = {
      F,
      txt(c, font, fill, s, x, y, o = {}){
        c.save(); c.font = font; c.textAlign = o.align || 'center'; c.textBaseline = o.base || 'alphabetic';
        if(o.stroke){ c.lineJoin = 'round'; c.lineWidth = o.sw || 10; c.strokeStyle = o.stroke; c.strokeText(s, x, y); }
        if(o.glow){ c.shadowColor = o.glow; c.shadowBlur = o.glowB || 24; }
        c.fillStyle = fill; c.fillText(s, x, y); c.restore();
      },
      // พิมพ์สองสีเหลื่อมแบบ riso
      riso(c, font, s, x, y, a, b, off = 6){
        c.save(); c.font = font; c.textAlign = 'center'; c.globalCompositeOperation = th.light ? 'multiply' : 'screen';
        c.fillStyle = b; c.fillText(s, x + off, y + off * .6); c.fillStyle = a; c.fillText(s, x, y); c.restore();
      },
      glitch(c, font, s, x, y, amt, col, seed = 0){
        c.save(); c.font = font; c.textAlign = 'center'; c.textBaseline = 'middle';
        const o = 4 + amt * 22;
        c.globalCompositeOperation = th.light ? 'multiply' : 'lighter';
        c.fillStyle = th.light ? 'rgba(255,0,80,.6)' : 'rgba(255,40,80,.85)'; c.fillText(s, x - o, y);
        c.fillStyle = th.light ? 'rgba(0,160,255,.6)' : 'rgba(40,200,255,.85)'; c.fillText(s, x + o, y);
        c.globalCompositeOperation = 'source-over'; c.fillStyle = col; c.fillText(s, x, y);
        if(amt > .05){ const r = M.rng('g' + seed + Math.floor(M.frame / 3));
          for(let k = 0; k < 5; k++){ const yy = y - 160 + r() * 320, hh = 10 + r() * 40, dx = (r() - .5) * 120 * amt;
            c.save(); c.beginPath(); c.rect(0, yy, W, hh); c.clip(); c.fillStyle = th.bg; c.fillRect(0, yy, W, hh);
            c.fillStyle = col; c.fillText(s, x + dx, y); c.restore(); } }
        c.restore();
      },
      polaroid(c, im, x, y, w, h, rot = 0, cap){
        c.save(); c.translate(x, y); c.rotate(rot);
        c.fillStyle = 'rgba(0,0,0,.45)'; c.fillRect(-w / 2 - 20 + 16, -h / 2 - 20 + 20, w + 40, h + 110);
        c.fillStyle = '#fbfaf7'; c.fillRect(-w / 2 - 20, -h / 2 - 20, w + 40, h + 110);
        if(im) c.drawImage(im, -w / 2, -h / 2, w, h);
        if(cap) H_.txt(c, F('hand', 44), '#333', cap, 0, h / 2 + 66);
        c.restore();
      },
      tape(c, x, y, rot){ c.save(); c.translate(x, y); c.rotate(rot); c.fillStyle = 'rgba(255,240,200,.7)'; c.fillRect(-70, -18, 140, 36); c.restore(); },
      // เส้นปากกาเมจิก วาดตามความคืบหน้า p
      marker(c, pts, p, col, wd = 12){
        if(p <= 0) return;
        let tot = 0; const seg = []; for(let i = 1; i < pts.length; i++){ const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); tot += d; }
        let left = tot * clamp(p);
        c.save(); c.strokeStyle = col; c.lineWidth = wd; c.lineCap = 'round'; c.lineJoin = 'round'; c.beginPath(); c.moveTo(...pts[0]);
        for(let i = 1; i < pts.length && left > 0; i++){ const f = Math.min(1, left / seg[i - 1]);
          c.lineTo(lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)); left -= seg[i - 1]; }
        c.stroke(); c.restore();
      },
      // ลายมือวาดบนรูป รอบจุดหัว (hx,hy) ขนาด s: horns เขาปีศาจ / crown มงกุฎ / halo วงนางฟ้า / heart หัวใจ / tears น้ำตา / x กากบาท / scribble ขีดฆ่า
      doodle(c, kind, hx, hy, s, p, col, wd = 13){
        const P = (pts) => pts.map(([x, y]) => [hx + x * s, hy + y * s]);
        const m = (pts, a, b) => H_.marker(c, P(pts), clamp((p - a) / (b - a)), col, wd);
        switch(kind){
          case 'crown': m([[-90, -60], [-100, -170], [-50, -110], [0, -190], [50, -110], [100, -170], [90, -60], [-90, -60]], 0, 1); break;
          case 'halo': c.save(); c.strokeStyle = col; c.lineWidth = wd; c.beginPath(); c.ellipse(hx, hy - 150 * s, 110 * s, 30 * s, 0, 0, 6.283 * clamp(p)); c.stroke(); c.restore(); break;
          case 'heart': m([[0, -60], [-60, -130], [-120, -60], [0, 60], [120, -60], [60, -130], [0, -60]], 0, 1); break;
          case 'tears': m([[-40, 10], [-46, 60], [-38, 90]], 0, .5); m([[40, 10], [46, 60], [38, 90]], .4, 1); break;
          case 'x': m([[-120, -120], [120, 120]], 0, .5); m([[120, -120], [-120, 120]], .5, 1); break;
          case 'scribble': m([[-140, -40], [120, -60], [-120, 0], [140, -10], [-110, 50], [130, 40]], 0, 1); break;
          default:   // horns + หาง + ตา
            m([[-90, -40], [-150, -150], [-120, -200], [-40, -70]], 0, .45);
            m([[90, -40], [150, -150], [120, -200], [40, -70]], .3, .75);
            m([[160, 530], [260, 480], [300, 370], [250, 320], [330, 290], [300, 360]], .6, 1);
            if(p > .9){ c.fillStyle = col; for(const ex of [-34, 34]){ c.beginPath(); c.arc(hx + ex * s, hy + 10 * s, 8 * s, 0, 6.3); c.fill(); } }
        }
      },
      phone(c, x, y, w, h, fill = '#0f0f14'){
        c.save(); c.fillStyle = '#000'; c.beginPath(); c.roundRect(x - 14, y - 14, w + 28, h + 28, 64); c.fill();
        c.strokeStyle = '#3a3a44'; c.lineWidth = 4; c.stroke();
        c.fillStyle = fill; c.beginPath(); c.roundRect(x, y, w, h, 52); c.fill();
        c.fillStyle = '#000'; c.beginPath(); c.roundRect(x + w / 2 - 70, y + 16, 140, 36, 18); c.fill(); c.restore();
      },
      avatar(c, im, x, y, r){ if(!im) return; c.save(); c.beginPath(); c.arc(x, y, r, 0, 6.3); c.clip(); c.drawImage(im, x - r, y - r, r * 2, r * 2); c.restore(); },
      bubbleText(c, Lc, t, maxW, font, dim, on){
        c.font = font; const lh = parseInt(font.match(/(\d+)px/)[1]) * 1.3;
        const pos = M.layoutWords(c, Lc.words, maxW, lh, 0, 0, 'left'), rows = pos.rows, w = Math.max(...pos.map(q => q.x + q.width));
        return { w, h: rows * lh, draw: (bx, by) => { c.font = font; M.karaRows(c, Lc, t, { maxW, lh, cx: bx + w / 2, cy: by + rows * lh / 2 + lh * .32, dim, on }); } };
      },
      frame(c, col, inset = 46, spr){
        c.save(); c.strokeStyle = col; c.lineWidth = 4; c.strokeRect(inset, inset, W - inset * 2, H - inset * 2);
        c.lineWidth = 1.5; c.strokeRect(inset + 12, inset + 12, W - inset * 2 - 24, H - inset * 2 - 24);
        if(spr) for(const [x, y] of [[inset, inset], [W - inset, inset], [inset, H - inset], [W - inset, H - inset]]) c.drawImage(spr, x - 34, y - 34, 68, 68);
        c.restore();
      },
      petals(c, t, n, seed, spr, o = {}){
        const r = M.rng(seed);
        for(let k = 0; k < n; k++){
          const sp = 50 + r() * 80, x0 = r() * W, ph = r() * 50, s = (o.s || 40) + r() * (o.sv || 60), rs = (r() - .5) * 3;
          const y = ((t + ph) * sp) % (H + 200) - 100, x = x0 + Math.sin((t + ph) * .9) * 70;
          c.save(); c.translate(x, y); c.rotate((t + ph) * rs); c.globalAlpha = o.a ?? .9; c.drawImage(spr, -s / 2, -s / 2, s, s); c.restore();
        }
      },
      heartPath(c, x, y, s){
        c.beginPath(); c.moveTo(x, y + s * .32);
        c.bezierCurveTo(x, y - s * .1, x - s * .5, y - s * .1, x - s * .5, y + s * .28);
        c.bezierCurveTo(x - s * .5, y + s * .6, x - s * .1, y + s * .78, x, y + s);
        c.bezierCurveTo(x + s * .1, y + s * .78, x + s * .5, y + s * .6, x + s * .5, y + s * .28);
        c.bezierCurveTo(x + s * .5, y - s * .1, x, y - s * .1, x, y + s * .32); c.closePath();
      },
      countdown(c, t, Ln, col, y){
        if(!Ln) return; const left = Ln.t0 - t; if(left > 3.2 || left < 0) return;
        c.save(); c.fillStyle = col;
        for(let k = 0; k < 3; k++){ c.globalAlpha = left > (3 - k) - .2 ? .25 : 1; c.beginPath(); c.arc(W / 2 - 60 + k * 60, y, 14, 0, 6.3); c.fill(); }
        c.restore();
      },
      // เนื้อตัวใหญ่ขอบดำด้านล่าง อ่านง่ายทุกพื้น
      lower(c, Lc, t, col, y = H - 200, px = 84, o = {}){
        c.font = F('bold', px);
        M.karaRows(c, Lc, t, { maxW: o.maxW || 1640, lh: px * 1.25, cy: y, cx: o.cx, dim: o.dim || 'rgba(255,255,255,.42)', on: col,
          stroke: o.stroke === false ? null : (o.stroke || 'rgba(0,0,0,.85)'), strokeW: 14, glow: o.glow, glowB: o.glowB });
      },
      shake: { t: -9, a: 0 },
      kick(t0, a){ if(H_.shake.t !== t0){ H_.shake.t = t0; H_.shake.a = a; } },
      doShake(c, t){ const d = t - H_.shake.t; if(d < 0 || d > .45) return; const a = H_.shake.a * (1 - d / .45); c.translate(Math.sin(t * 97) * a, Math.cos(t * 83) * a); },
      // คำในบรรทัดที่ตรงกับ re (สตริงจากบท) -> {t, idx}; ไม่เจอ = ตามสัดส่วน frac ของบรรทัด
      trig(Lc, re, frac = .6){
        if(re){ let rx; try{ rx = new RegExp(re, 'i'); }catch(e){ rx = null; }
          if(rx){ const k = Lc.words.findIndex(w => rx.test(w.s));
            if(k >= 0) return { t: Lc.words[k].t0, idx: k };
            const ci = Lc.text.search(rx); if(ci >= 0){ const w = Lc.words.find(w => w.i1 > ci); if(w) return { t: Lc.ct[ci], idx: w.idx }; } } }
        const t = lerp(Lc.tSing0, Lc.tSing1, frac);
        return { t, idx: Math.max(0, M.wordAt(Lc, t)) };
      },
      lp: (Lc, t) => clamp((t - Lc.tSing0) / Math.max(.3, Lc.tSing1 - Lc.tSing0)),
      lastOn(Lc, t){ const w = M.wordAt(Lc, t); return w < 0 ? -9 : Lc.words[w].t0; },
      // บรรทัดที่กำลังร้องในช่วงหลายบรรทัด
      curOf(Ls, t){ let r = Ls[0]; for(const x of Ls) if(t >= x.t0 - .3) r = x; return r; },
    };
    return H_;
  }

  // ---------- โหลดบท -> รายการฉากให้ engine ----------
  async function build(M, mv, base, libBase){
    const th = { ...TH0, ...(mv.theme || {}), fonts: { ...TH0.fonts, ...((mv.theme || {}).fonts || {}) } };
    if(typeof th.acc === 'string') th.acc = [th.acc];
    const Hh = helpers(M, th), L = M.song.lines, W = M.W, H = M.H;
    // รูป: "lib/x.jpg" = คลังรูปสาธารณะกลาง, อย่างอื่น = ในโฟลเดอร์เพลง
    const IM = {}, specs = mv.images || {};
    const srcOf = s => /^lib\//.test(s) ? libBase + s : /^(https?:|\/)/.test(s) ? s : base + s;
    await Promise.all(Object.entries(specs).map(async ([k, v]) => {
      const sp = typeof v === 'string' ? { src: v } : v;
      try{ IM[k] = { im: await M.loadImg(srcOf(sp.src)), ...sp }; }catch(e){ console.warn('mv: โหลดรูปไม่ได้', sp.src); }
    }));
    const keys = Object.keys(IM);
    const pick = k => IM[k] ? k : keys.length ? keys[Math.abs([...String(k || '')].reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7)) % keys.length] : null;
    const cache = new Map();
    const fx = (k, kind = 'fit', w = W, h = H, extra = {}) => {
      k = pick(k); if(!k) return null;
      const key = k + '|' + kind + '|' + w + 'x' + h + '|' + JSON.stringify(extra);
      if(cache.has(key)) return cache.get(key);
      const S = IM[k], im = S.im, fy = extra.fy ?? S.fy ?? .4, mode = extra.mode || 'cover', pad = extra.pad || 0;
      let out;
      switch(kind){
        case 'blur': { const s = M.fit(im, 32, 18, 'cover', '#000'); out = M.canvas(w, h); const g = out.getContext('2d');
          g.imageSmoothingQuality = 'high'; g.drawImage(s, 0, 0, w, h); g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(0, 0, w, h); break; }
        case 'ht': out = M.halftone(im, { w, h, fy, mode, pad, paper: extra.paper || th.paper, contrast: 1.35,
          layers: [{ color: extra.c1 || th.acc[0], angle: 15, cell: extra.cell || 9, ch: extra.ch1 || 'lum', gain: .75 }, { color: extra.c2 || th.ink, angle: 45, cell: (extra.cell || 9) - 2, ch: 'lum', gain: .95 }] }); break;
        case 'ht1': out = M.halftone(im, { w, h, fy, mode, pad, paper: extra.paper || th.paper, layers: [{ color: extra.c1 || th.ink, angle: 45, cell: extra.cell || 8 }], contrast: extra.contrast || 1.3 }); break;
        case 'htcolor': out = M.halftone(im, { w, h, fy, mode, pad, paper: extra.paper || th.paper,
          layers: [{ color: extra.c1 || th.acc[0], angle: 15, cell: extra.cell || 10, ch: 'sat', gain: 1.4 }, { color: extra.c2 || th.ink, angle: 45, cell: (extra.cell || 10) - 2 }] }); break;
        case 'htdark': out = M.halftone(im, { w, h, fy, mode, pad, paper: extra.paper || '#0b1030',
          layers: [{ color: extra.c1 || th.acc[0], angle: 20, cell: extra.cell || 10, inv: true, gain: .9 }, { color: extra.c2 || '#5b6bd6', angle: 60, cell: 13, inv: true, gain: .6, ox: 4 }] }); break;
        case 'line': out = M.lineArt(im, { w, h, ink: extra.ink || th.ink, mode, pad, fy, thr: .16, hatch: .45 }); break;
        case 'duo': out = M.duotone(im, extra.dark || '#05031a', extra.lite || '#4b3796', { w, h, fy, mode, contrast: 1.4 }); break;
        case 'knock': out = M.knockout(M.fit(im, w, h, 'contain', '#fff', .5, fy, pad)); break;
        default: out = M.fit(im, w, h, mode, '#000', .5, fy, pad);
      }
      cache.set(key, out); return out;
    };
    const head = k => { k = pick(k); return (k && IM[k].head) || [.5, .3]; };
    const accOf = a => a == null ? th.acc[0] : typeof a === 'number' ? th.acc[a % th.acc.length] : a;
    const flower = M.flowerSprite(256, th.flower || '#fff6e3', th.flowerHeart || '#f2b632');
    const ctxBase = { M, th, D: Hh, img: k => (k = pick(k)) ? IM[k].im : null, fx, head, flower, L, W, H };

    // ช่วงของบท
    const segs = [];
    const entries = (mv.lines || []).map(e => ({ ...e, ii: Array.isArray(e.i) ? e.i : [e.i, e.i] })).sort((a, b) => a.ii[0] - b.ii[0]);
    const covered = new Set(); entries.forEach(e => { for(let k = e.ii[0]; k <= e.ii[1]; k++) covered.add(k); });
    // บรรทัดที่บทไม่ได้ระบุ -> ใช้ฉากสำรอง (ไม่ให้จอว่าง)
    for(let k = 0; k < L.length; k++) if(!covered.has(k)) entries.push({ ii: [k, k], scene: mv.fallback || 'kinetic', p: {}, auto: true });
    entries.sort((a, b) => a.ii[0] - b.ii[0]);
    for(const e of entries){
      const Ls = L.slice(e.ii[0], e.ii[1] + 1); if(!Ls.length) continue;
      const def = REG[e.scene] || REG[mv.fallback || 'kinetic'];
      segs.push({ t0: Math.max(.01, Ls[0].t0 - (e.lead ?? th.lead)), name: `${e.ii[0]}${e.ii[1] > e.ii[0] ? '–' + e.ii[1] : ''} · ${def.name}`,
        def, Ls, P: e.p || {}, trans: e.tr || th.tr, td: e.td ?? th.td, acc: accOf((e.p || {}).acc) });
    }
    // ช่วงดนตรียาว (ไม่มีบทกำหนด) -> ฉาก interlude อัตโนมัติ
    const gapsDef = mv.gaps || {};
    for(let k = 0; k + 1 < L.length; k++){
      const gap = L[k + 1].t0 - L[k].tSing1;
      if(gap < (th.gapMin || 7)) continue;
      const g = gapsDef[k] || { scene: 'interlude', p: {} };
      const def = REG[g.scene] || REG.interlude;
      segs.push({ t0: L[k].tSing1 + .8, name: 'ดนตรี · ' + def.name, def, Ls: [L[k + 1]], P: g.p || {}, trans: g.tr || 'fade', td: .8, acc: accOf((g.p || {}).acc), gap: true });
    }
    const intro = mv.intro || { scene: 'titleCard', p: {} }, outro = mv.outro || { scene: 'outroCard', p: {} };
    segs.push({ t0: 0, name: 'เปิด · ' + intro.scene, def: REG[intro.scene] || REG.titleCard, Ls: [L[0]], P: intro.p || {}, trans: 'cut', td: 0, acc: accOf((intro.p || {}).acc), intro: true });
    // อินโทรยาว (เกิน 16 วิ) -> ฉากเปิด 10 วิ แล้วต่อด้วยช่วงดนตรี (แท่งเสียง + นับถอยหลัง) จนถึงบรรทัดแรก
    if(L[0].t0 > 16){
      const g = mv.introGap || { scene: 'interlude', p: {} }, def = REG[g.scene] || REG.interlude;
      segs.push({ t0: 10, name: 'อินโทร · ' + def.name, def, Ls: [L[0]], P: g.p || {}, trans: g.tr || 'fade', td: 1, acc: accOf((g.p || {}).acc), gap: true });
    }
    const lastL = L[L.length - 1];
    segs.push({ t0: lastL.tSing1 + .6, name: 'ปิด · ' + outro.scene, def: REG[outro.scene] || REG.outroCard, Ls: [lastL], P: outro.p || {}, trans: outro.tr || 'fade', td: 1, acc: accOf((outro.p || {}).acc), outro: true });
    segs.sort((a, b) => a.t0 - b.t0);
    segs.forEach((s, k) => { s.t1 = segs[k + 1] ? segs[k + 1].t0 : 1e9; });

    // อุ่นแคชรูปที่ต้องแปลง (ฉากบอกเองว่าต้องใช้อะไร)
    for(const s of segs) if(s.def.prep) try{ s.def.prep({ ...ctxBase, P: s.P, Lc: s.Ls[0], Ls: s.Ls, acc: s.acc }); }catch(e){ console.warn('mv prep', s.name, e); }

    const meta = { title: mv.title || '', artist: mv.artist || '', credit: mv.credit || '' };
    function nextStrip(c, t){
      const cur = M.lineAt(t); if(!cur) return;
      const nx = cur.next; if(!nx || nx.t0 - t > 6) return;
      const a = M.clamp((t - (cur.t0 + (cur.t1 - cur.t0) * .45)) / .3); if(a <= 0) return;
      c.save(); c.font = '400 36px Kanit'; const w = c.measureText(nx.text).width + 60;
      c.globalAlpha = a * .92; c.fillStyle = 'rgba(0,0,0,.6)'; c.beginPath(); c.roundRect(W / 2 - w / 2, H - 70, w, 54, 27); c.fill();
      c.fillStyle = '#fff'; c.textAlign = 'center'; c.fillText(nx.text, W / 2, H - 31); c.restore();
    }
    return segs.map(s => {
      const X = { ...ctxBase, P: s.P, Lc: s.Ls[0], Ls: s.Ls, acc: s.acc, seg: s, meta };
      return { t0: s.t0, t1: s.t1, name: s.name, trans: s.trans, td: s.td,
        draw: (c, t) => {
          try{ s.def.draw(c, t, X); }catch(e){ c.fillStyle = th.bg; c.fillRect(0, 0, W, H); Hh.lower(c, s.Ls[0], t, th.acc[0], H / 2); if(!s.err){ s.err = 1; console.error('mv scene', s.name, e); (window.__mvErrors ||= []).push(s.name + ': ' + e.message); } }
          if(th.nextStrip && !s.intro && !s.outro && !s.gap && !s.def.noStrip) nextStrip(c, t);
          if(th.grain) M.grain(c, th.grain);
        } };
    });
  }

  return { def, build, REG, TH0, FONT_FILES };
})();
