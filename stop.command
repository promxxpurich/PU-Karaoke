#!/usr/bin/env bash
# ปิดเซิร์ฟเวอร์คาราโอเกะ + จอหลัก  ->  ดับเบิลคลิกไฟล์นี้ หรือสั่ง ./stop.command
cd "$(dirname "$0")"

PORT=8080
PROFILE="$PWD/.chrome-player"
did=0

# หา PID ของ "เซิร์ฟเวอร์เราจริงๆ" เท่านั้น
#  - ยึดจากตัวที่ฟังพอร์ต ไม่ใช่ตัวที่ต่อเข้ามาเป็นไคลเอนต์
#    (lsof -ti:8080 เฉยๆ จะคืน com.apple.WebKit.Networking ที่แค่ต่อเข้ามาด้วย)
#  - ยืนยันว่า binary เป็น python และมี server.py เป็นอาร์กิวเมนต์
#    (pgrep -f "server.py" เฉยๆ จับเชลล์/เอดิเตอร์ที่บังเอิญมีคำนี้ใน args ด้วย = อันตราย)
is_our_server() {
  ps -p "$1" -o command= 2>/dev/null | grep -qE '^[^ ]*[Pp]ython[^ ]*( |$).*server\.py'
}

server_pids() {
  { lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null
    pgrep -x Python 2>/dev/null
    pgrep -x python3 2>/dev/null
  } | grep -E '^[0-9]+$' | sort -u | while read -r p; do
    is_our_server "$p" && echo "$p"
  done
}

targets="$(server_pids | tr '\n' ' ')"

# --- ปิดจอหลักก่อน (เฉพาะโปรไฟล์ของเรา ไม่ยุ่ง Chrome ปกติ) ---
# ต้องมาก่อนการปิดเซิร์ฟเวอร์: uvicorn รอ WebSocket ปิดก่อนถึงจะจบด้วย TERM
# ถ้าปิดทีหลัง เซิร์ฟเวอร์จะค้างจนหมดเวลาแล้วโดน KILL = ไม่ได้ปิดอย่างสุภาพจริง
if pgrep -f "user-data-dir=$PROFILE" >/dev/null 2>&1; then
  echo "🖥  ปิดจอหลัก"
  pkill -f "user-data-dir=$PROFILE" 2>/dev/null
  did=1
  sleep 0.6   # เผื่อเวลาให้ WebSocket ปิดจริง
fi

# --- ปิดแบบสุภาพก่อน ให้เซฟ history.json และปิด WebSocket ให้เรียบร้อย ---
if [ -n "${targets// /}" ]; then
  echo "⏹  ปิดเซิร์ฟเวอร์ (PID:$targets)"
  kill -TERM $targets 2>/dev/null
  still=""
  for _ in $(seq 1 20); do
    still=""
    for pid in $targets; do kill -0 "$pid" 2>/dev/null && still="$still $pid"; done
    [ -z "${still// /}" ] && break
    sleep 0.25
  done
  if [ -n "${still// /}" ]; then
    echo "⚠️  ไม่ยอมปิดดีๆ บังคับปิด:$still"
    kill -KILL $still 2>/dev/null
  fi
  did=1
fi

# --- เก็บกวาดงานหนักที่อาจกลายเป็นลูกกำพร้า (กิน GPU ต่อโดยไม่มีใครคุม) ---
orphans="$(pgrep -f "[-]m demucs" 2>/dev/null | grep -E '^[0-9]+$' | sort -u)"
if [ -n "$orphans" ]; then
  echo "🧹 ปิดงานแยกเสียงที่ค้าง ($(echo $orphans | tr '\n' ' '))"
  kill -TERM $orphans 2>/dev/null; sleep 1; kill -KILL $orphans 2>/dev/null
  did=1
fi

lyr="$(pgrep -f "[g]en_lyrics[.]py|[v]erify_lyrics[.]py|[f]a_align[.]py" 2>/dev/null | grep -E '^[0-9]+$' | sort -u)"
if [ -n "$lyr" ]; then
  echo "🧹 ปิดงานหาเนื้อเพลงที่ค้าง ($(echo $lyr | tr '\n' ' '))"
  kill -TERM $lyr 2>/dev/null; sleep 1; kill -KILL $lyr 2>/dev/null
  did=1
fi

# --- ยืนยันผล ---
sleep 0.5
if [ -n "$(server_pids)" ]; then
  echo "❌ เซิร์ฟเวอร์ยังไม่ปิด — ลองรันอีกครั้ง"
  exit 1
fi
[ "$did" = "1" ] && echo "✅ ปิดเรียบร้อย" || echo "ℹ️  ไม่มีอะไรรันอยู่ ไม่ต้องปิด"
echo "   เปิดใหม่: ./player.command"
