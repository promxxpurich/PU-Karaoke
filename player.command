#!/usr/bin/env bash
# เปิด "จอหลัก" แบบเต็มจอ  ->  ดับเบิลคลิกไฟล์นี้ หรือสั่ง ./player.command
#   --kiosk  เปิดโหมดคีออสก์ (ออกยากขึ้น เหมาะกับตั้งทิ้งไว้เป็นจอทีวี)
cd "$(dirname "$0")"

PORT=8080

# หา PID ของ "เซิร์ฟเวอร์เราจริงๆ" เท่านั้น
#  - ยึดจากตัวที่ฟังพอร์ต (ไม่ใช่ตัวที่ต่อเข้ามาเป็นไคลเอนต์)
#  - ยืนยันว่า binary เป็น python และมี server.py เป็นอาร์กิวเมนต์
#    (ห้ามใช้ pgrep -f "server.py" เฉยๆ — มันจับเชลล์/เอดิเตอร์ที่บังเอิญมีคำนี้ใน args ด้วย)
is_our_server() {
  ps -p "$1" -o command= 2>/dev/null | grep -qE '^[^ ]*[Pp]ython[^ ]*( |$).*server\.py'
}
server_pids() {
  { lsof -nP -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null; pgrep -x Python 2>/dev/null; } \
    | grep -E '^[0-9]+$' | sort -u | while read -r p; do is_our_server "$p" && echo "$p"; done
}
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL="http://localhost:8080/"          # localhost เสมอ -> ผ่านด่านกันเครื่องอื่นแน่นอน
PROFILE="$PWD/.chrome-player"         # โปรไฟล์แยก: ถ้าใช้โปรไฟล์ปกติ Chrome จะส่งต่อไปยัง
                                      # instance เดิมแล้ว "เมิน flag ทั้งหมด" รวมถึง autoplay

[ -x "$CHROME" ] || { echo "❌ ไม่พบ Google Chrome ที่ $CHROME"; exit 1; }

# --- 1. เซิร์ฟเวอร์: ถ้ายังไม่รัน ให้เปิดให้เลย ---
if ! curl -sf --max-time 2 "${URL}api/health" >/dev/null 2>&1; then
  if [ -n "$(server_pids)" ]; then
    echo "⏳ เซิร์ฟเวอร์กำลังเริ่ม รออีกสักครู่…"
  else
    echo "▶️  เปิดเซิร์ฟเวอร์…"
    nohup ./run.sh > /tmp/kara.log 2>&1 &
  fi
  for i in $(seq 1 40); do
    curl -sf --max-time 2 "${URL}api/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  if ! curl -sf --max-time 2 "${URL}api/health" >/dev/null 2>&1; then
    echo "❌ เซิร์ฟเวอร์ไม่ขึ้น ดู log ที่ /tmp/kara.log"; exit 1
  fi
fi
echo "✅ เซิร์ฟเวอร์พร้อม"

# --- 2. กันเปิดจอหลักซ้อน (จอที่เปิดอยู่จะถูกแทนที่) ---
if pgrep -f "user-data-dir=$PROFILE" >/dev/null; then
  echo "ℹ️  จอหลักเปิดอยู่แล้ว — สลับไปที่หน้าต่างนั้นแทน"
  osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null
  exit 0
fi

# --- 3. เปิดจอหลัก ---
MODE="--start-fullscreen"
[ "$1" = "--kiosk" ] && MODE="--kiosk"

echo "🎤 เปิดจอหลัก… (ออกด้วย Cmd+Q  •  ปิดเซิร์ฟเวอร์ด้วย ./stop.command)"
exec "$CHROME" \
  --user-data-dir="$PROFILE" \
  --app="$URL" \
  $MODE \
  --autoplay-policy=no-user-gesture-required \
  --no-first-run --no-default-browser-check \
  --disable-session-crashed-bubble --hide-crash-restore-bubble \
  --disable-features=Translate,InfiniteSessionRestore \
  >/dev/null 2>&1
