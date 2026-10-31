#!/usr/bin/env bash
# สร้าง assets/icon.png + icon.icns จาก assets/icon.svg (ใช้ Chrome แบบ headless, sips, iconutil)
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf '<!doctype html><html><body style="margin:0;background:transparent">%s</body></html>' "$(cat assets/icon.svg)" > "$TMP/icon.html"
# โปรไฟล์ชั่วคราว ไม่ยุ่ง Chrome ที่เปิดอยู่
"$CHROME" --headless=new --disable-gpu --user-data-dir="$TMP/profile" --window-size=1024,1024 \
  --default-background-color=00000000 --screenshot="$TMP/icon.png" "file://$TMP/icon.html" >/dev/null 2>&1
cp "$TMP/icon.png" assets/icon.png
SET="$TMP/icon.iconset"; mkdir "$SET"
for s in 16 32 128 256 512; do
  sips -z "$s" "$s" assets/icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z "$d" "$d" assets/icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o assets/icon.icns
echo "สร้าง assets/icon.png และ assets/icon.icns แล้ว"
