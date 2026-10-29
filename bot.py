#!/usr/bin/env python3
"""Away-reply bot for Telegram (official Business-bot / Chat Automation method).

When you are offline, this bot replies to incoming private messages in YOUR
chats. The replies are sent through your account's business connection, so
your friends see them in the normal chat with you - not in a separate bot chat.

Key points
----------
* No userbot / no phone login. You connect the bot to your account from the
  Telegram app (Settings -> Chat Automation / Telegram Business -> Chatbots).
  This is a sanctioned Telegram feature - no ban risk.
* The bot receives BOTH sides of every connected chat (your messages and your
  friends' messages), so it can tell when you are really active.
* "Offline" means: you have not sent a message in that chat for
  OWNER_ACTIVE_MINUTES. While you are chatting, the bot stays silent.

Full setup guide: README.md
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

import ai_reply
from config import BASE_DIR, cfg
from state import State

log = logging.getLogger("awaybot")

API_URL = f"https://api.telegram.org/bot{cfg.BOT_TOKEN}"
ALLOWED_UPDATES = ["business_connection", "business_message", "message"]

# Set in main(): the bot's own user id (to recognise heartbeat pings).
_me_id = 0

_cooldown_help = (
    "I'll choose a different offline reply for every incoming text message."
    if cfg.REPLY_COOLDOWN_MINUTES <= 0
    else f"I reply at most once per chat every {cfg.REPLY_COOLDOWN_MINUTES} minutes."
)
HELP_TEXT = (
    f"🌙 Hello, {cfg.OWNER_NAME}! *Away-reply bot*\n\n"
    "I reply to your friends automatically while you are offline.\n\n"
    "Commands:\n"
    "/away on | off — turn auto-replies on or off\n"
    "/away — toggle\n"
    "/status — show current state\n\n"
    "How I decide you are offline: if you have not sent a message in a chat "
    f"for {cfg.OWNER_ACTIVE_MINUTES} minutes, I consider you away there.\n"
    f"{_cooldown_help}"
)


def api(method: str, *, _timeout: int = 30, **params):
    """Call the Telegram Bot API. Returns the 'result' field, or None."""
    body = {k: v for k, v in params.items() if v is not None}
    try:
        resp = requests.post(f"{API_URL}/{method}", json=body, timeout=_timeout)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.error("Telegram API call failed (%s): %s", method, exc)
        return None
    if not data.get("ok"):
        log.warning("%s failed: %s", method, data.get("description"))
    return data.get("result")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _owner_uid(state: State, conn: dict | None) -> int:
    if state.owner_id:
        return state.owner_id
    if conn:
        return int(conn.get("owner_user_id") or 0)
    return 0


def status_text(state: State) -> str:
    conns = state.data.get("connections", {})
    active = sum(1 for c in conns.values() if c.get("is_enabled"))

    if cfg.AI_PROVIDER == "none":
        ai = "none (varied local replies; private)"
    elif cfg.OPENAI_API_KEY:
        ai = f"OpenAI-compatible ({cfg.OPENAI_MODEL})"
    elif cfg.GEMINI_API_KEY:
        ai = f"Gemini ({cfg.GEMINI_MODEL})"
    else:
        ai = "none (varied local templates; private)"

    away = "ON ✅" if state.data.get("away_enabled", True) else "OFF ⛔"

    hb = float(state.data.get("last_heartbeat", 0.0) or 0.0)
    if cfg.HEARTBEAT_TIMEOUT_SECONDS <= 0 or hb <= 0:
        hb_line = "Phone heartbeat: not active (optional, see README)"
    else:
        age_sec = time.time() - hb
        if age_sec > cfg.HEARTBEAT_TIMEOUT_SECONDS:
            hb_line = (
                f"Phone heartbeat: MISSING → phone/data presumed OFFLINE "
                f"({int(age_sec)} sec ago)"
            )
        else:
            hb_line = f"Phone heartbeat: ok (last seen {int(age_sec)} sec ago)"

    cooldown_line = (
        "Auto-reply cooldown: off (reply on every incoming text message)\n"
        if cfg.REPLY_COOLDOWN_MINUTES <= 0
        else f"Auto-reply cooldown: {cfg.REPLY_COOLDOWN_MINUTES} min per chat\n"
    )
    return (
        f"{cfg.OWNER_NAME}, here's your status:\n"
        f"Away auto-replies: {away}\n"
        f"Connected business accounts: {active}\n"
        f"You count as 'offline' after {cfg.OWNER_ACTIVE_MINUTES} min of silence "
        f"in a chat\n"
        f"{cooldown_line}"
        f"{hb_line}\n"
        f"Smart replies: {ai}\n"
        f"Owner id: {state.owner_id or '(not bound yet - send /start)'}"
    )


# --------------------------------------------------------------------------
# update handlers
# --------------------------------------------------------------------------

def handle_business_connection(bc: dict, state: State) -> None:
    """Someone connected / disconnected the bot to their Telegram account."""
    user = bc.get("user") or {}
    owner_uid = int(user.get("id") or 0)
    if owner_uid and not state.owner_id:
        state.owner_id = owner_uid
        log.info("Learned owner id from business connection: %s", owner_uid)

    rights = bc.get("rights") or {}
    can_reply = bc.get("can_reply")
    if can_reply is None:
        can_reply = rights.get("can_reply", True)

    state.data["connections"][str(bc.get("id"))] = {
        "owner_user_id": owner_uid,
        "is_enabled": bool(bc.get("is_enabled", True)),
        "can_reply": bool(can_reply),
    }
    state.save()

    enabled = bool(bc.get("is_enabled", True))
    log.info(
        "Business connection %s %s (owner %s, can_reply=%s)",
        bc.get("id"),
        "ENABLED" if enabled else "DISABLED",
        owner_uid,
        can_reply,
    )

    if enabled and owner_uid:
        api(
            "sendMessage",
            chat_id=owner_uid,
            text=(
                "✅ Away-reply bot connected!\n\n"
                "I will auto-reply in your chats while you're offline.\n"
                "Send /start here, then /away on to enable.\n"
                "Send /status any time to see what I'm doing."
            ),
        )


def handle_business_message(msg: dict, state: State) -> None:
    """A message inside one of your connected private chats."""
    bcid = msg.get("business_connection_id")
    conn = state.data["connections"].get(str(bcid))
    if conn is None:
        # Connection predates state.json - assume enabled and let Telegram
        # enforce the real permissions.
        conn = {"is_enabled": True, "can_reply": True}
    if not conn.get("is_enabled", True):
        return

    sender = msg.get("from") or {}
    if sender.get("is_bot"):
        return

    # Telegram echoes our own auto-replies back with sender_business_bot set.
    # They are neither your message nor your friend's - ignore them so they
    # never count as "owner activity" and never trigger replies to ourselves.
    if msg.get("sender_business_bot"):
        return

    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    chat_id = chat.get("id")

    text = (msg.get("text") or msg.get("caption") or "").strip()
    now = time.time()
    msg_ts = msg.get("date") or now
    owner_uid = _owner_uid(state, conn)

    if owner_uid and sender.get("id") == owner_uid:
        # YOU typed this from your phone/app -> you are active in this chat.
        state.note_owner_msg(chat_id, msg_ts)
        state.note_heartbeat(msg_ts)  # chatting = your phone is online
        state.add_history(chat_id, "owner", text or "[media]")
        log.debug("Owner message in chat %s", chat_id)
        return

    # A message from your friend.
    state.add_history(chat_id, "them", text or "[media]")

    if cfg.AUTO_READ and bcid:
        api(
            "readBusinessMessage",
            business_connection_id=bcid,
            chat_id=chat_id,
            message_id=msg.get("message_id"),
        )

    # Stickers / photos / voice notes without text: stay silent.
    if not text:
        return

    if not state.data.get("away_enabled", True):
        log.debug("Away mode is off; staying silent in chat %s", chat_id)
        return

    mem = state.chat(chat_id)

    # Phone heartbeat: when the bot runs on another machine and your phone's
    # pings stop (mobile data off!), we KNOW you cannot reply anywhere - so we
    # skip the "owner was active recently" check and reply immediately.
    hb = float(state.data.get("last_heartbeat", 0.0) or 0.0)
    phone_offline = (
        cfg.HEARTBEAT_TIMEOUT_SECONDS > 0
        and hb > 0
        and now - hb > cfg.HEARTBEAT_TIMEOUT_SECONDS
    )
    if phone_offline:
        log.info(
            "No phone heartbeat for %.0f sec - treating you as offline "
            "everywhere (chat %s)",
            (now - hb) / 60,
            chat_id,
        )
    elif now - float(mem.get("last_owner_msg", 0.0)) < cfg.OWNER_ACTIVE_MINUTES * 60:
        log.debug("You were active in chat %s recently; staying silent", chat_id)
        return
    if now - float(mem.get("last_auto_reply", 0.0)) < cfg.REPLY_COOLDOWN_MINUTES * 60:
        log.debug("Cooldown active in chat %s; staying silent", chat_id)
        return

    log.info("Auto-replying in chat %s (connection %s)", chat_id, bcid)
    if cfg.SEND_TYPING and bcid:
        api(
            "sendChatAction",
            chat_id=chat_id,
            action="typing",
            business_connection_id=bcid,
        )

    reply = ai_reply.generate_reply(state.history(chat_id), cfg.OWNER_NAME)
    sent = api(
        "sendMessage",
        chat_id=chat_id,
        text=reply,
        business_connection_id=bcid,
    )
    if sent is not None:
        state.note_auto_reply(chat_id, now)
        state.add_history(chat_id, "us", reply)


def handle_control_message(msg: dict, state: State) -> None:
    """Commands in the bot's own chat (/start, /away, /status)."""
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return
    sender = msg.get("from") or {}

    chat_id = chat.get("id")
    from_id = int(sender.get("id") or 0)
    text = (msg.get("text") or "").strip()
    command = text.lower().split()[0].split("@")[0] if text else ""
    msg_ts = msg.get("date") or time.time()

    # Heartbeat ping. heartbeat.sh sends /ping *with the bot token*, so the
    # message arrives "from the bot itself" - we record it and delete it so
    # the chat stays clean. A manual /ping from the owner works too.
    if command == "/ping":
        if from_id == _me_id or (state.owner_id and from_id == state.owner_id):
            state.note_heartbeat(msg_ts)
            state.save()
            log.debug("Phone heartbeat received")
            if from_id == _me_id:
                api("deleteMessage", chat_id=chat_id, message_id=msg.get("message_id"))
        return

    if sender.get("is_bot"):
        return

    # First person to send /start becomes the owner.
    if not state.owner_id:
        if command == "/start":
            state.owner_id = from_id
            state.save()
            log.info("Bound owner id %s", from_id)
            api("sendMessage", chat_id=chat_id, text=HELP_TEXT, parse_mode="Markdown")
        else:
            api(
                "sendMessage",
                chat_id=chat_id,
                text="Send /start first to become the owner of this bot.",
            )
        return

    if from_id != state.owner_id:
        if command == "/start":
            api(
                "sendMessage",
                chat_id=chat_id,
                text="This bot manages its owner's away-replies. It won't reply here.",
            )
        return

    # Any message from you proves your phone is online.
    state.note_heartbeat(msg_ts)

    if command in ("/start", "/help"):
        api("sendMessage", chat_id=chat_id, text=HELP_TEXT, parse_mode="Markdown")
    elif command == "/away":
        parts = text.lower().split()
        if len(parts) > 1 and parts[1] in ("on", "off"):
            state.data["away_enabled"] = parts[1] == "on"
        else:
            state.data["away_enabled"] = not state.data.get("away_enabled", True)
        state.save()
        label = "ON ✅" if state.data["away_enabled"] else "OFF ⛔"
        api("sendMessage", chat_id=chat_id, text=f"{cfg.OWNER_NAME}, away auto-replies are now {label}")
    elif command == "/status":
        api("sendMessage", chat_id=chat_id, text=status_text(state))
    # anything else typed to the bot: ignore silently


# --------------------------------------------------------------------------
# phone heartbeat listener (optional)
# --------------------------------------------------------------------------

def start_heartbeat_server(state: State) -> None:
    """Tiny HTTP endpoint the phone pings (heartbeat.sh).

    If the pings stop (mobile data off!), `last_heartbeat` goes stale and the
    bot treats you as offline everywhere. Enabled only when HEARTBEAT_PORT is
    set AND HEARTBEAT_SECRET is non-empty (the secret must be in the URL).
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            parsed = urlparse(self.path)
            if parsed.path != "/ping":
                self.send_response(404)
                self.end_headers()
                return
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            if token != cfg.HEARTBEAT_SECRET:
                self.send_response(403)
                self.end_headers()
                return
            state.note_heartbeat()
            state.save()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")

        def log_message(self, *_args):
            pass  # keep the console clean

    server = ThreadingHTTPServer(("0.0.0.0", cfg.HEARTBEAT_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info(
        "Heartbeat listener on port %d (phone presumed offline after %d sec without a ping)",
        cfg.HEARTBEAT_PORT,
        cfg.HEARTBEAT_TIMEOUT_SECONDS,
    )


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------

def main() -> None:
    global _me_id

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not cfg.BOT_TOKEN:
        sys.exit("BOT_TOKEN is missing - copy .env.example to .env and fill it in.")

    me = api("getMe", _timeout=20)
    if not me:
        sys.exit("Could not reach Telegram - check BOT_TOKEN and your connection.")
    _me_id = int(me.get("id") or 0)
    log.info("Logged in as @%s (id %s)", me.get("username"), me.get("id"))

    state = State(BASE_DIR / "state.json", max_history=cfg.MAX_HISTORY)
    if state.owner_id:
        log.info("Owner id: %s", state.owner_id)
    else:
        log.info("Owner not bound yet - open the bot's chat and send /start")

    if cfg.HEARTBEAT_PORT > 0:
        if cfg.HEARTBEAT_SECRET:
            start_heartbeat_server(state)
        else:
            log.warning(
                "HEARTBEAT_PORT is set but HEARTBEAT_SECRET is empty - "
                "heartbeat listener NOT started (set a secret to enable it)."
            )

    offset = 0
    startup = True
    log.info("Listening for messages... (Ctrl+C to stop)")

    while True:
        updates = api(
            "getUpdates",
            offset=offset,
            timeout=cfg.POLL_TIMEOUT,
            allowed_updates=ALLOWED_UPDATES,
            _timeout=cfg.POLL_TIMEOUT + 20,
        )
        if updates is None:
            time.sleep(5)
            continue
        if not updates:
            continue

        # On the first poll, drop messages that arrived while we were stopped
        # (so the bot never floods old chats with late replies).
        if startup and not cfg.PROCESS_BACKLOG:
            log.info("Skipping %d old update(s) received while the bot was offline.",
                     len(updates))
            offset = updates[-1]["update_id"] + 1
            startup = False
            continue
        startup = False

        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "business_connection" in update:
                    handle_business_connection(update["business_connection"], state)
                elif "business_message" in update:
                    handle_business_message(update["business_message"], state)
                elif "message" in update:
                    handle_control_message(update["message"], state)
                # edited_business_message / deleted_business_messages: ignore
            except Exception:
                log.exception("Failed to handle update %s", update.get("update_id"))
        state.save()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
