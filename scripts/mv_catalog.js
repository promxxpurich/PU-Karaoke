#!/usr/bin/env node
// สร้าง static/mv/CATALOG.md จากรายการฉากที่ลงทะเบียนจริงใน static/mv/scenes-*.js
// = คู่มือสำหรับคน (หรือ Claude) ที่เขียนบท mv.json ของแต่ละเพลง — รันใหม่ทุกครั้งที่เพิ่ม/แก้ฉาก
//   node scripts/mv_catalog.js            -> เขียน CATALOG.md
//   node scripts/mv_catalog.js --json     -> พิมพ์รายชื่อฉาก + params เป็น JSON (ไว้ให้ mv_check ใช้)
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = path.join(__dirname, '..', 'static', 'mv');
const ctx = vm.createContext({ console });
const files = ['scenes-core.js', 'scenes-phone.js', 'scenes-classic.js', 'scenes-general.js'];
vm.runInContext(files.map(f => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n;\n') + '\n;this.MVScenes = MVScenes;', ctx);
const REG = ctx.MVScenes.REG, TH0 = ctx.MVScenes.TH0;
const byFile = {};
for(const f of files.slice(1)){ const src = fs.readFileSync(path.join(dir, f), 'utf8'); byFile[f] = [...src.matchAll(/def\('(\w+)'/g)].map(m => m[1]); }

if(process.argv.includes('--json')){
  console.log(JSON.stringify(Object.fromEntries(Object.values(REG).map(s => [s.name, { lines: s.lines, params: s.params || {} }]))));
  process.exit(0);
}
const FAM = { 'scenes-phone.js': 'มือถือ / ความทรงจำ / เมือง (ธีมมืด)', 'scenes-classic.js': 'ภาพเก่า / งานพิมพ์ / ไทย-อีสาน (ธีมสว่าง)', 'scenes-general.js': 'ทั่วไป + บรรยากาศ (ใช้ได้ทุกธีม)' };
let md = `# คลังฉาก MV — คู่มือเขียนบท \`mv.json\`

> ไฟล์นี้สร้างอัตโนมัติจาก \`static/mv/scenes-*.js\` ด้วย \`node scripts/mv_catalog.js\` — ห้ามแก้มือ

## รูปแบบ mv.json (วางในโฟลเดอร์เพลง คู่กับ lyrics.json)

\`\`\`json
{
  "v": 1, "title": "ชื่อเพลง", "artist": "ศิลปิน", "credit": "ที่มาของรูป",
  "theme": { "bg": "#0a0a0d", "acc": ["#ff2e4d", "#b06cff"], "light": false, "tr": "cut", "td": 0.35, "lead": 0.06,
             "pals": { "day": {"bg":"..","band":"..","hi":"..","fg":"..","alt":".."} } },
  "images": { "ชื่อรูป": { "src": "frames/f156.jpg", "fy": 0.4, "head": [0.5, 0.25] }, "plate": { "src": "lib/plumeria_alba.jpg" } },
  "intro": { "scene": "lockscreen", "p": { ... } },
  "outro": { "scene": "crtOff", "p": { ... } },
  "gaps":  { "13": { "scene": "interlude", "p": { "img": "..", "text": "♪ ดนตรี ♪" } } },
  "lines": [ { "i": 0, "scene": "tear", "p": { "img": "couple", "word": "คน", "acc": 0 }, "tr": "glitch" },
             { "i": [16, 18], "scene": "ecg", "p": { "word": "จริง" } } ]
}
\`\`\`

- \`i\` = ลำดับบรรทัดใน lyrics.json (เริ่ม 0) หรือ \`[a, b]\` สำหรับฉากหลายบรรทัด — บรรทัดที่ไม่ได้ระบุ ระบบใช้ฉาก \`kinetic\` ให้เอง
- \`p.word\` / \`p.until\` = regex ของคำในบรรทัดที่เป็นจังหวะเอฟเฟกต์ (ไม่เจอ = ใช้สัดส่วนของบรรทัด) · \`p.acc\` = เลขสีใน theme.acc หรือรหัสสี
- \`tr\` เปลี่ยนฉาก: cut / fade / wipe / iris / slide / blinds / glitch · \`td\` = วินาที · \`lead\` = เข้าฉากก่อนบรรทัดกี่วิ (เพลงเร็ว 0.06 / ช้า 0.4)
- รูป: \`frames/fSSS.jpg\` = ภาพนิ่งจากคลิป (scripts/mv_prep.py) · \`lib/x.jpg\` = คลังรูปสาธารณะกลาง (static/mv/lib) · \`fy\` = จุดโฟกัสแนวตั้ง 0–1 · \`head\` = ตำแหน่งหัวคน [x, y] 0–1 (ฉาก doodle ใช้)
- ช่วงดนตรีเงียบเกิน 7 วิ ระบบใส่ \`interlude\` ให้เอง (กำหนดเองได้ใน \`gaps\` โดยใช้เลขบรรทัดก่อนช่วงนั้น)\n- อินโทรยาวเกิน 16 วิ: ฉาก intro เล่น 10 วิแรก แล้วต่อด้วย \`interlude\` จนถึงบรรทัดแรก (กำหนดเองได้ที่ \`introGap\`)
- \`theme.light: true\` = พื้นกระดาษ (ฉากตระกูลภาพเก่า) · ค่าเริ่มต้นธีม: \`${JSON.stringify({ bg: TH0.bg, acc: TH0.acc, tr: TH0.tr, td: TH0.td, lead: TH0.lead })}\`

## หลักการเขียนบท
1. อ่านเนื้อทั้งเพลง หาโครง (ท่อน A / แร็ป / พรีฮุก / ฮุก) — ฮุกที่ซ้ำหลายรอบใช้ชุดฉากเดียวกันแต่เปลี่ยน \`acc\`/\`pal\` ทุกรอบ
2. เลือกฉากที่ "ตรงความหมาย" ของบรรทัดนั้น (ดูคำแนะนำในแต่ละฉาก) ไม่ใช่สุ่ม; คำเด็ดของบรรทัดใส่เป็น \`word\`
3. ดู frames/sheet.jpg แล้วตั้งชื่อรูปตามสิ่งที่เห็น (her / couple / street …) เลือกรูปให้เข้ากับบรรทัด อย่าใช้รูปที่มีตัวหนังสือ/โลโก้ฝังเยอะ
4. ไม่ใช้ฉากเดิมติดกันเกิน 2 บรรทัด (ยกเว้น camcorder ในท่อนแร็ปที่เปลี่ยนรูปทุกบรรทัด)
5. ห้ามแต่งเนื้อเพลงเพิ่ม — ข้อความประกอบ (ชื่อในแชต, ตราประทับ, ป้าย) สั้น ๆ และมาจากเนื้อเพลง

## รายการฉาก
`;
for(const [f, names] of Object.entries(byFile)){
  md += `\n### ${FAM[f] || f}\n`;
  for(const n of names){ const s = REG[n]; if(!s) continue;
    md += `\n**\`${n}\`** — ${s.doc || ''}${s.lines && s.lines !== 1 ? `  \n_บรรทัด: ${s.lines}_` : ''}\n`;
    for(const [k, v] of Object.entries(s.params || {})) md += `- \`${k}\`: ${v}\n`;
  }
}
const lib = fs.readdirSync(path.join(dir, 'lib')).filter(f => f.endsWith('.jpg'));
md += `\n## คลังรูปสาธารณะกลาง (static/mv/lib)\n${lib.map(f => '- `lib/' + f + '`').join('\n')}\n`;
fs.writeFileSync(path.join(dir, 'CATALOG.md'), md);
console.log(JSON.stringify({ scenes: Object.keys(REG).length, file: 'static/mv/CATALOG.md' }));
