"""Configuration for the away-reply bot.

All settings come from environment variables; the easiest way is to copy
`.env.example` to `.env` (next to this file) and edit it.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (kept dependency-free on purpose)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # Real environment variables always win over the file.
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self) -> None:
        # ---- identity -------------------------------------------------
        self.BOT_TOKEN = _str("BOT_TOKEN")
        # Used by Render webhook mode; not needed for Termux long polling.
        self.WEBHOOK_SECRET = _str("WEBHOOK_SECRET")
        # Your numeric user id (0 = learn automatically when you connect
        # the bot in Telegram, or on the first /start you send the bot).
        self.OWNER_ID = _int("OWNER_ID", 0)
        self.OWNER_NAME = _str("OWNER_NAME", "Master")

        # ---- AI reply generation -------------------------------------
        # auto | openai | gemini | none
        self.AI_PROVIDER = _str("AI_PROVIDER", "none").lower()
        self.OPENAI_API_KEY = _str("OPENAI_API_KEY")
        self.OPENAI_BASE_URL = _str("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL = _str("OPENAI_MODEL", "gpt-4o-mini")
        self.GEMINI_API_KEY = _str("GEMINI_API_KEY")
        self.GEMINI_MODEL = _str("GEMINI_MODEL", "gemini-2.5-flash")

        # ---- behaviour ------------------------------------------------
        # "Offline" = you have not sent a message in that chat for N minutes.
        self.OWNER_ACTIVE_MINUTES = _int("OWNER_ACTIVE_MINUTES", 30)
        # At most one auto-reply per chat per N minutes (anti-spam).
        self.REPLY_COOLDOWN_MINUTES = _int("REPLY_COOLDOWN_MINUTES", 0)

        # ---- phone heartbeat (optional) -------------------------------
        # When the bot runs on a DIFFERENT machine than your phone, the phone
        # can ping HEARTBEAT_PORT/HEARTBEAT_SECRET (see heartbeat.sh). If the
        # pings stop (mobile data off!), the bot treats you as offline
        # EVERYWHERE and replies immediately - even in chats where you were
        # recently active. 0 = disabled. Secret is required to enable.
        self.HEARTBEAT_PORT = _int("HEARTBEAT_PORT", 0)
        self.HEARTBEAT_SECRET = _str("HEARTBEAT_SECRET")
        # No ping for this many seconds -> phone presumed offline.
        # With 10-second pings, 30 seconds tolerates two missed pings.
        self.HEARTBEAT_TIMEOUT_SECONDS = _int("HEARTBEAT_TIMEOUT_SECONDS", 30)
        # Let the AI admit it is an automated away reply when asked.
        self.REVEAL_AUTOMATION = _bool("REVEAL_AUTOMATION", True)
        # Mark incoming messages as read on your behalf (looks human).
        self.AUTO_READ = _bool("AUTO_READ", True)
        # Show "typing..." before replying.
        self.SEND_TYPING = _bool("SEND_TYPING", True)
        # Process messages that arrived while the bot was stopped.
        self.PROCESS_BACKLOG = _bool("PROCESS_BACKLOG", False)
        # How much chat context the AI sees.
        self.MAX_HISTORY = _int("MAX_HISTORY", 12)
        self.POLL_TIMEOUT = _int("POLL_TIMEOUT", 50)
        # Used when no AI key is configured or the AI call fails.
        self.AUTO_REPLY_TEMPLATE = os.environ.get(
            "AUTO_REPLY_TEMPLATE",
            "Hey! {owner} isn't online right now \u2014 "
            "they'll reply as soon as they're back. (Automated away message)",
        )


cfg = Config()
