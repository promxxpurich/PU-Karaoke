// ธีมของแอป: ตั้งก่อนวาดหน้า จะได้ไม่เห็นสีเดิมแวบตอนเปิดแอป จำค่าต่อเครื่องใน localStorage
const THEMES = [
  { id: 'peach', name: 'พีชละมุน', desc: 'สว่าง อบอุ่น', c: ['#fff6f1', '#ffffff', '#d93a6e', '#e0653f'] },
  { id: 'mint', name: 'มินต์สดใส', desc: 'สว่าง สบายตา', c: ['#f0faf6', '#ffffff', '#0a7f69', '#1b9478'] },
  { id: 'lavender', name: 'ลาเวนเดอร์', desc: 'สว่าง นุ่มนวล', c: ['#f6f3ff', '#ffffff', '#6a4be0', '#a24fd0'] },
  { id: 'sweetnight', name: 'ราตรีหวาน', desc: 'มืด โทนชมพู', c: ['#211526', '#2e1f35', '#ff8db5', '#ffb38a'] },
  { id: 'classic', name: 'คลาสสิก', desc: 'มืด สีเดิมของรีโมท', c: ['#06060b', '#14141f', '#ff4d8d', '#7c5cff'] },
];
const DEFAULT_THEME = 'peach';

function loadTheme() {
  try {
    const t = localStorage.getItem('kara-theme');
    return THEMES.some((x) => x.id === t) ? t : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}
function applyTheme(id) {
  document.documentElement.dataset.theme = id;
  try { localStorage.setItem('kara-theme', id); } catch { /* จำไม่ได้ก็ยังใช้ธีมนี้จนปิดแอป */ }
}
document.documentElement.dataset.theme = loadTheme();
