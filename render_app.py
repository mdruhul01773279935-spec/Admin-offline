"""Render Web Service entry point for Telegram webhook delivery.

On Render Free, webhook requests can wake a sleeping service. The first reply
may be delayed by a cold start. This is best-effort hobby hosting, not 24/7 SLA.
"""
from __future__ import annotations

import logging
import os
import threading

from flask import Flask, abort, jsonify, request

import bot
from config import BASE_DIR, cfg
from state import State

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("awaybot.render")

app = Flask(__name__)
state = State(BASE_DIR / "state.json", max_history=cfg.MAX_HISTORY)
_state_lock = threading.RLock()

# Render's free filesystem is temporary. Set OWNER_ID in Render's environment
# so the bot can still recognize its owner after a cold start/restart.
if not state.owner_id and cfg.OWNER_ID:
    state.owner_id = cfg.OWNER_ID


def _register_webhook() -> None:
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if not cfg.BOT_TOKEN:
        log.error("BOT_TOKEN is not configured; webhook was not registered")
        return
    if not cfg.WEBHOOK_SECRET:
        log.error("WEBHOOK_SECRET is not configured; webhook was not registered")
        return
    if not cfg.OWNER_ID:
        log.error("OWNER_ID is required in Render to prevent another user claiming ownership")
        return
    if not host:
        log.info("No Render hostname yet; webhook registration will be skipped")
        return
    result = bot.api(
        "setWebhook",
        url=f"https://{host}/telegram/webhook",
        secret_token=cfg.WEBHOOK_SECRET,
        allowed_updates=bot.ALLOWED_UPDATES,
        drop_pending_updates=False,
        _timeout=20,
    )
    if result:
        log.info("Telegram webhook registered for https://%s/telegram/webhook", host)
    else:
        log.error("Could not register Telegram webhook; inspect the logs above")


_register_webhook()


@app.get("/")
def home():
    return "Telegram away bot is running.\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/health")
def health():
    return jsonify(status="ok", webhook_secret_configured=bool(cfg.WEBHOOK_SECRET)), 200


@app.post("/telegram/webhook")
def telegram_webhook():
    if not cfg.WEBHOOK_SECRET or not cfg.OWNER_ID:
        abort(503)
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if provided != cfg.WEBHOOK_SECRET:
        abort(403)

    update = request.get_json(silent=True)
    if not isinstance(update, dict):
        abort(400)

    try:
        with _state_lock:
            if "business_connection" in update:
                bot.handle_business_connection(update["business_connection"], state)
            elif "business_message" in update:
                bot.handle_business_message(update["business_message"], state)
            elif "message" in update:
                bot.handle_control_message(update["message"], state)
            # Other allowed/forwarded update types are intentionally ignored.
            state.save()
    except Exception:
        log.exception("Failed to process Telegram update %s", update.get("update_id"))
        # Non-2xx asks Telegram to retry delivery.
        return jsonify(ok=False), 500

    return jsonify(ok=True), 200
