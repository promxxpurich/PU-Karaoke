#!/usr/bin/env bash
# เปิด "จอหลัก" แบบเต็มจอ  ->  ดับเบิลคลิกไฟล์นี้ หรือสั่ง ./player.command
#   --kiosk      เปิดโหมดคีออสก์ (ออกยากขึ้น เหมาะกับตั้งทิ้งไว้เป็นจอทีวี)
#   --no-tunnel  ไม่เปิดลิงก์ Cloudflare (ตอนไม่มีเน็ต) — หรือตั้ง KARA_NO_TUNNEL=1
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"   # ดับเบิลคลิก .command แล้ว PATH ไม่มี brew/cloudflared

PORT=8080
case "${1:-}" in -h|--help) sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac

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

# --- 1.6 ลิงก์จากนอกบ้านผ่าน Cloudflare (สุ่มใหม่ทุกครั้งที่เปิด ไม่ต้องมีโดเมน/บัญชี) ---
# ล้มเหลวก็ไม่เป็นไร: ในบ้านยังเข้าผ่าน IP ในวงแลนได้เหมือนเดิม ปิดพร้อมเซิร์ฟเวอร์ด้วย ./stop.command
NO_TUNNEL=0
for a in "$@"; do [ "$a" = "--no-tunnel" ] && NO_TUNNEL=1; done
[ "${KARA_NO_TUNNEL:-0}" = "1" ] && NO_TUNNEL=1
if [ "$NO_TUNNEL" = 1 ]; then
  echo "🌐 ข้ามลิงก์ Cloudflare (--no-tunnel)"
elif ! ./cloudflare.command --quick; then
  echo "⚠️  เปิดลิงก์ Cloudflare ไม่ได้ — ใช้ในบ้านผ่าน Wi-Fi ได้ตามปกติ (ลองใหม่: ./cloudflare.command --quick)"
fi

# --- 1.5 บอก IP ทั้งหมดของเครื่องนี้ พร้อมอธิบายว่าแต่ละอันคืออะไร ---
# ชื่อพอร์ตจาก macOS เช่น en0 -> "Wi-Fi", en1 -> "Thunderbolt 1"
port_name() {
  networksetup -listallhardwareports 2>/dev/null \
    | awk -v d="$1" '/^Hardware Port:/{sub(/^Hardware Port: /,""); n=$0} /^Device:/{if($2==d){print n; exit}}'
}
describe_ip() {   # $1=อินเทอร์เฟซ  $2=IP
  local ifc="$1" ip="$2" hw kind
  hw="$(port_name "$ifc")"
  case "$ifc" in
    lo*)        echo "เครื่องนี้เท่านั้น (loopback) — ใช้เปิดจอหลักบนเครื่องนี้"; return ;;
    utun*|ppp*|ipsec*) kind="VPN / อุโมงค์ ($ifc)" ;;
    bridge1*)   kind="แชร์อินเทอร์เน็ต/ฮอตสปอตของ Mac ($ifc)" ;;
    *)          kind="${hw:-$ifc} ($ifc)" ;;
  esac
  case "$ip" in
    169.254.*)  echo "$kind — ที่อยู่ชั่วคราว (ไม่ได้รับ IP จากเราเตอร์) มือถือมักต่อไม่ได้" ;;
    100.6[4-9].*|100.[7-9][0-9].*|100.1[01][0-9].*|100.12[0-7].*)
                echo "$kind — เครือข่าย VPN แบบ Tailscale/CGNAT ใช้ได้เฉพาะเครื่องที่อยู่ใน VPN เดียวกัน" ;;
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*)
                echo "$kind — วงแลนในบ้าน/ร้าน ✅ มือถือที่ต่อ Wi-Fi เดียวกันใช้อันนี้" ;;
    *)          echo "$kind — IP สาธารณะ (ออกอินเทอร์เน็ตตรง) ระวังคนนอกเข้าถึง" ;;
  esac
}
echo ""
echo "🌐 IP ของเครื่องนี้ (พอร์ต $PORT):"
ifconfig 2>/dev/null | awk '
  /^[a-z0-9]+:/ { ifc=$1; sub(/:$/,"",ifc) }
  $1=="inet" { print ifc, $2 }' \
| while read -r ifc ip; do
    printf "   • %-16s %s\n" "$ip" "$(describe_ip "$ifc" "$ip")"
    [ "$ifc" = "lo0" ] || printf "       จอหลัก http://%s:%s/   รีโมตมือถือ http://%s:%s/r\n" "$ip" "$PORT" "$ip" "$PORT"
  done
LHN="$(scutil --get LocalHostName 2>/dev/null)"
[ -n "$LHN" ] && echo "   • $LHN.local      ชื่อเครื่องในวงแลน (ใช้แทน IP ได้บน iPhone/Mac) -> http://$LHN.local:$PORT/r"
echo ""

# --- 2. กันเปิดจอหลักซ้อน (จอที่เปิดอยู่จะถูกแทนที่) ---
if pgrep -f "user-data-dir=$PROFILE" >/dev/null; then
  echo "ℹ️  จอหลักเปิดอยู่แล้ว — สลับไปที่หน้าต่างนั้นแทน"
  osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null
  exit 0
fi

# --- 3. เปิดจอหลัก ---
MODE="--start-fullscreen"
for a in "$@"; do [ "$a" = "--kiosk" ] && MODE="--kiosk"; done

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
