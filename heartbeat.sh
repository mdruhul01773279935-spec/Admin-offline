#!/data/data/com.termux/files/usr/bin/bash
# Phone heartbeat: tells the away bot "my internet connection is alive".
#
# Run this on your PHONE (Termux) while bot.py runs on ANOTHER machine
# (home PC / VPS / cloud). If the pings stop (mobile data off, no signal),
# the bot assumes you are offline everywhere and auto-replies immediately -
# even in chats where you were recently active. When the pings come back,
# it goes quiet again.
#
# Setup: put these in .env next to this script:
#   HEARTBEAT_PORT=8765        (must match the bot's .env)
#   HEARTBEAT_SECRET=some-long-random-string   (must match the bot's .env)
#   HB_HOST=1.2.3.4            (IP/hostname of the machine running bot.py)
#
# Usage:  bash heartbeat.sh [interval_seconds]      (default 10 sec)
set -u
cd "$(dirname "$0")"

getenv() {
  grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"' "
}

HB_HOST=$(getenv HB_HOST)
HB_PORT=$(getenv HEARTBEAT_PORT)
HB_SECRET=$(getenv HEARTBEAT_SECRET)
HB_HOST=${HB_HOST:-127.0.0.1}
HB_PORT=${HB_PORT:-8765}

if [ -z "$HB_SECRET" ]; then
  echo "HEARTBEAT_SECRET is not set in .env - the bot will ignore open pings."
  echo "Set HEARTBEAT_PORT + HEARTBEAT_SECRET in .env on BOTH machines first."
  exit 1
fi

INTERVAL=${1:-10}
URL="http://${HB_HOST}:${HB_PORT}/ping?token=${HB_SECRET}"

termux-wake-lock 2>/dev/null || true
echo "Pinging ${HB_HOST}:${HB_PORT} every ${INTERVAL}s (Ctrl+C to stop)"
echo "If the bot stops receiving pings, it treats your phone as offline."

while true; do
  curl -s -m 8 "${URL}" >/dev/null 2>&1 || true
  sleep "${INTERVAL}"
done
