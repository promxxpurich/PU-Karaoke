#!/usr/bin/env bash
# เปิด PU KARAOKE ให้เข้าจากนอกบ้านผ่าน Cloudflare Tunnel (https ฟรี ไม่ต้องเปิดพอร์ตเราเตอร์)
#
#   ./cloudflare.command --quick              ทดลองทันที ไม่ต้องมีโดเมน/บัญชี (ได้ลิงก์ *.trycloudflare.com สุ่มใหม่ทุกครั้ง)
#   ./cloudflare.command kara.example.com     ใช้โดเมนของตัวเองที่อยู่บน Cloudflare (ตั้งครั้งเดียว รันเองตอนเปิดเครื่อง)
#   ./cloudflare.command --stop               ปิดอุโมงค์ทดลอง / ล้างลิงก์สาธารณะออกจากจอ
#   ./cloudflare.command --status             ดูว่าตอนนี้เปิดอยู่ไหม ลิงก์อะไร
#
# ทำอะไรบ้าง: ติดตั้ง cloudflared (brew) -> ล็อกอิน -> สร้างอุโมงค์ "pu-karaoke" -> ชี้โดเมนมาที่พอร์ต 8080
#              -> เขียน publicUrl ลง .studio.json ให้ QR บนจอ/ลิงก์ในรีโมทชี้โดเมนนั้นทันที (ไม่ต้องรีสตาร์ทเซิร์ฟเวอร์)
# จอหลักในบ้านยังเปิดผ่าน http://localhost:8080/ เหมือนเดิม (วิดีโอไม่ต้องวิ่งออกอินเทอร์เน็ต)
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"   # ดับเบิลคลิก .command แล้ว PATH ไม่มี brew/cloudflared

PORT=8080
ORIGIN="http://localhost:$PORT"
TUNNEL="pu-karaoke"
CFDIR="$HOME/.cloudflared"
QUICK_LOG="/tmp/kara-cloudflare.log"
QUICK_PID="/tmp/kara-cloudflare.pid"
STUDIO_JSON=".studio.json"

say()  { printf '%s\n' "$*"; }
die()  { say "❌ $*"; exit 1; }

# เขียน/ล้าง publicUrl ใน .studio.json โดยรักษาฟิลด์อื่น (pin/secret/tv) ไว้ — เซิร์ฟเวอร์อ่านใหม่เองตาม mtime
set_public_url() {
  python3 - "$STUDIO_JSON" "$1" <<'PY'
import json, sys, pathlib
import re
p = pathlib.Path(sys.argv[1]); url = sys.argv[2].strip().rstrip("/")
if url and not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", url):
    sys.exit(f"publicUrl ไม่ใช่ URL: {url!r}")
try: cfg = json.loads(p.read_text("utf-8"))
except Exception: cfg = {}
cfg["publicUrl"] = url
p.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
PY
}
get_public_url() { python3 -c "import json;print(json.load(open('$STUDIO_JSON')).get('publicUrl') or '')" 2>/dev/null; }
tv_key()         { python3 -c "import json;print(json.load(open('$STUDIO_JSON')).get('tv') or '')" 2>/dev/null; }

print_links() {   # $1 = URL สาธารณะ
  say ""
  say "🌐 ลิงก์สำหรับเปิดจากที่ไหนก็ได้:"
  say "   รีโมทมือถือ : $1/r"
  say "   Studio      : $1/studio   (ต้องใส่ PIN)"
  say "   จอทีวี      : $1/tv/$(tv_key)"
  say "   (จอหลักในบ้านยังใช้ http://localhost:$PORT/ — ไม่ควรเปิดจอหลักผ่านโดเมน วิดีโอจะวิ่งออกเน็ตแล้วกลับเข้ามา)"
  say ""
}

need_server() {
  curl -sf --max-time 2 "$ORIGIN/api/health" >/dev/null 2>&1 \
    || say "⚠️  เซิร์ฟเวอร์คาราโอเกะยังไม่รันอยู่ที่พอร์ต $PORT — เปิดด้วย ./player.command ก่อน ลิงก์ถึงจะใช้ได้"
}

ensure_cloudflared() {
  command -v cloudflared >/dev/null 2>&1 && return
  command -v brew >/dev/null 2>&1 || die "ไม่มี Homebrew — ติดตั้งจาก https://brew.sh ก่อน แล้วรันไฟล์นี้ใหม่"
  say "⬇️  ติดตั้ง cloudflared ด้วย Homebrew (ครั้งแรกครั้งเดียว อาจใช้เวลา 1-2 นาที)…"
  brew install cloudflared || die "ติดตั้ง cloudflared ไม่สำเร็จ"
}

quick_running() { [ -f "$QUICK_PID" ] && kill -0 "$(cat "$QUICK_PID")" 2>/dev/null; }

stop_quick() {
  if quick_running; then kill "$(cat "$QUICK_PID")" 2>/dev/null; say "⏹  ปิดอุโมงค์ทดลองแล้ว"; fi
  rm -f "$QUICK_PID"
}

# ---------------------------------------------------------------- โหมดต่าง ๆ
case "${1:-}" in
  --status)
    pub="$(get_public_url)"
    if quick_running; then say "🟢 อุโมงค์ทดลองเปิดอยู่ (pid $(cat "$QUICK_PID"))"; fi
    if launchctl list 2>/dev/null | grep -q com.cloudflare.cloudflared; then say "🟢 บริการ cloudflared (โดเมนจริง) ทำงานอยู่"; fi
    [ -n "$pub" ] && print_links "$pub" || say "ยังไม่ได้ตั้งลิงก์สาธารณะ (publicUrl ว่าง) — QR บนจอชี้ IP ในบ้าน"
    exit 0 ;;

  --stop)
    stop_quick
    set_public_url ""
    say "✓ ล้างลิงก์สาธารณะแล้ว — QR บนจอกลับไปใช้ IP ในบ้าน"
    say "  (ถ้าติดตั้งเป็นบริการด้วยโดเมนจริง ปิดด้วย: sudo cloudflared service uninstall)"
    exit 0 ;;

  --quick)
    ensure_cloudflared; need_server
    stop_quick
    say "🚀 เปิดอุโมงค์ทดลอง (ลิงก์สุ่ม ใช้ได้จนกว่าจะปิดหน้าต่างนี้/สั่ง --stop)…"
    : > "$QUICK_LOG"
    nohup cloudflared tunnel --url "$ORIGIN" --no-autoupdate > "$QUICK_LOG" 2>&1 &
    echo $! > "$QUICK_PID"
    url=""
    for i in $(seq 1 40); do
      url="$(grep -aoE 'https://[a-z0-9-]+\.trycloudflare\.com' "$QUICK_LOG" | head -1)"   # -a: log มีอักขระวาดกรอบ grep จะนึกว่าเป็นไบนารี
      [ -n "$url" ] && break
      sleep 0.5
    done
    [ -n "$url" ] || { stop_quick; die "ไม่ได้ลิงก์จาก Cloudflare ดู log ที่ $QUICK_LOG"; }
    set_public_url "$url"
    say "✅ เปิดแล้ว"
    print_links "$url"
    say "ℹ️  ลิงก์นี้เปลี่ยนทุกครั้งที่รัน และหายเมื่อปิดเครื่อง — ใช้โดเมนจริงเมื่อพร้อม: ./cloudflare.command kara.โดเมนของคุณ"
    exit 0 ;;

  ""|-h|--help)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 0 ;;
esac

# ---------------------------------------------------------------- โดเมนจริง
HOST="$1"; shift
NO_SERVICE=0; [ "${1:-}" = "--no-service" ] && NO_SERVICE=1
echo "$HOST" | grep -qE '^[a-z0-9.-]+\.[a-z]{2,}$' || die "ชื่อโดเมนไม่ถูกต้อง: $HOST  (ตัวอย่าง kara.example.com)"

ensure_cloudflared; need_server
stop_quick

# 1. ล็อกอิน (เปิดเบราว์เซอร์ให้เลือกโดเมนที่อยู่บนบัญชี Cloudflare)
if [ ! -f "$CFDIR/cert.pem" ]; then
  say "🔑 ล็อกอิน Cloudflare — เบราว์เซอร์จะเปิดขึ้น เลือกโดเมนที่จะใช้ (ต้องเพิ่มโดเมนไว้ในบัญชีก่อน)"
  cloudflared tunnel login || die "ล็อกอินไม่สำเร็จ"
fi

# 2. สร้างอุโมงค์ (ครั้งเดียว)
UUID="$(cloudflared tunnel list -o json 2>/dev/null | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    if t.get('name')=='$TUNNEL': print(t['id']); break" 2>/dev/null)"
if [ -z "$UUID" ]; then
  say "🛠  สร้างอุโมงค์ $TUNNEL…"
  cloudflared tunnel create "$TUNNEL" || die "สร้างอุโมงค์ไม่สำเร็จ"
  UUID="$(cloudflared tunnel list -o json | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    if t.get('name')=='$TUNNEL': print(t['id']); break")"
fi
[ -n "$UUID" ] || die "หา UUID ของอุโมงค์ไม่เจอ"
CRED="$CFDIR/$UUID.json"
[ -f "$CRED" ] || die "ไม่พบไฟล์สิทธิ์ $CRED (ลองลบอุโมงค์แล้วสร้างใหม่: cloudflared tunnel delete $TUNNEL)"

# 3. config: โดเมน -> พอร์ต 8080 ของเครื่องนี้
cat > "$CFDIR/config.yml" <<YML
tunnel: $UUID
credentials-file: $CRED
ingress:
  - hostname: $HOST
    service: $ORIGIN
  - service: http_status:404
YML
say "📝 เขียน $CFDIR/config.yml แล้ว"

# 4. DNS: ชี้โดเมนมาที่อุโมงค์ (ถ้ามีอยู่แล้วคำสั่งจะบอกเอง ไม่เป็นไร)
cloudflared tunnel route dns "$TUNNEL" "$HOST" 2>&1 | grep -v '^$' || true

# 5. รันเป็นบริการตอนเปิดเครื่อง
if [ "$NO_SERVICE" = 1 ]; then
  say "ℹ️  ไม่ติดตั้งเป็นบริการ — รันเองด้วย:  cloudflared tunnel run $TUNNEL"
else
  if launchctl list 2>/dev/null | grep -q com.cloudflare.cloudflared; then
    say "🔁 บริการ cloudflared มีอยู่แล้ว รีสตาร์ทให้ใช้ config ใหม่ (ถามรหัสผ่าน Mac)"
    sudo launchctl kickstart -k system/com.cloudflare.cloudflared 2>/dev/null || true
  else
    say "⚙️  ติดตั้งเป็นบริการให้รันเองตอนเปิดเครื่อง (ถามรหัสผ่าน Mac)"
    sudo cloudflared service install || die "ติดตั้งบริการไม่สำเร็จ (ลอง: ./cloudflare.command $HOST --no-service)"
  fi
fi

# 6. บอกเซิร์ฟเวอร์ให้ใช้ลิงก์นี้ + ตรวจว่าเข้าถึงได้จริง
set_public_url "https://$HOST"
say "⏳ รอ DNS/อุโมงค์พร้อม…"
ok=0
for i in $(seq 1 30); do
  curl -sf --max-time 5 "https://$HOST/api/health" >/dev/null 2>&1 && { ok=1; break; }
  sleep 2
done
if [ "$ok" = 1 ]; then say "✅ เข้าถึง https://$HOST ได้แล้ว"
else say "⚠️  ยังเข้า https://$HOST ไม่ได้ — DNS อาจใช้เวลา 1-2 นาที ลองใหม่: ./cloudflare.command --status"; fi
print_links "https://$HOST"
