#!/data/data/com.termux/files/usr/bin/bash
# One-shot setup for the away-reply bot on Termux (Android).
set -e

echo "==> Updating packages..."
pkg update -y
pkg install -y python

echo "==> Installing Python dependencies + curl..."
pip install --upgrade pip
pip install -r requirements.txt
pkg install -y curl

echo "==> Keeping the phone awake while Termux runs (optional)..."
termux-wake-lock || true

echo ""
echo "Setup done. Next steps:"
echo "  1. cp .env.example .env   (then edit .env: BOT_TOKEN, OWNER_NAME...)"
echo "  2. python bot.py"
echo ""
echo "Tip: see README.md for the full guide (BotFather + connecting the"
echo "     bot to your Telegram account)."
