#!/usr/bin/env bash
# ซ่อมค้นหาไม่เจอ: อัปเดต yt-dlp + ติดตั้ง certificate + ทดสอบค้นหาจริง
cd "$(dirname "$0")"
./.venv/bin/pip install -q --upgrade yt-dlp certifi
export SSL_CERT_FILE="$(./.venv/bin/python -c 'import certifi;print(certifi.where())')"
echo "yt-dlp : $(./.venv/bin/python -c 'import yt_dlp;print(yt_dlp.version.__version__)')"
echo "certs  : $SSL_CERT_FILE"
echo "--- ทดสอบค้นหา ---"
./.venv/bin/python -m yt_dlp --flat-playlist --print "%(title)s" "ytsearch3:ลูกทุ่ง" 2>&1 | tail -6
