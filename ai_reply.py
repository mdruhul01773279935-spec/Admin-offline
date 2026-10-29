"""Private local away replies, with optional AI providers.

When AI_PROVIDER=none (the default), this module chooses a varied reply
locally. No Telegram message text is sent to Gemini/OpenAI.
"""
import logging
import random

import requests

from config import cfg

log = logging.getLogger("awaybot.ai")

MAX_REPLY_CHARS = 800
AI_TIMEOUT_SECONDS = 25

# A pool of short, neutral away messages. They are formatted locally and do
# not depend on or inspect the incoming message.
LOCAL_REPLIES = (
    "{owner} is offline right now 😴 He'll reply when he's back online.",
    "{owner} is currently offline 📵 He'll message you when he comes online.",
    "{owner} is offline at the moment 🌙 He'll get back to you when he's online again.",
    "{owner} is offline now 📴 He'll respond as soon as he comes online.",
    "{owner} is offline for now ⏳ He'll reply when he's back online.",
    "{owner} is offline right now 💤 He'll answer once he's online again.",
    "{owner} is currently offline 🌐 He'll reply when he returns online.",
    "{owner} is offline at present 📱 He'll get back to you when he comes online.",
    "{owner} is offline right now 🔕 He'll message you when he's back online.",
    "{owner} is offline at the moment ✨ He'll respond when he gets online.",
    "{owner} is offline for now 🌙 He'll reply as soon as he's back online.",
    "{owner} is offline 📴 He'll get back to you when he's online again.",
    "{owner} is offline right now 📡 He'll answer when he comes online.",
    "{owner} is currently offline 💤 He'll reply once he's back online.",
    "{owner} is offline at the moment ⏰ He'll message you when he's online again.",
)

DEFAULT_AUTO_REPLY_TEMPLATE = (
    "Hey! {owner} isn't online right now — "
    "they'll reply as soon as they're back. (Automated away message)"
)


def _system_prompt(owner_name: str) -> str:
    reveal = ""
    if cfg.REVEAL_AUTOMATION:
        reveal = (
            "- If asked whether this is an automated reply or a bot, be honest: "
            f"it is {owner_name}'s automated away assistant.\n"
        )
    return (
        f"You write short Telegram auto-replies on behalf of {owner_name}, "
        "who is offline right now.\n"
        "Rules:\n"
        f"- Sound like {owner_name} texting a friend: warm, casual, natural.\n"
        "- Always answer in the same language the friend used "
        "(Bangla -> Bangla, English -> English, etc.).\n"
        "- 1-2 short sentences. Never longer than that.\n"
        f"- Make it clear {owner_name} is offline and will reply personally "
        "when they are back.\n"
        f"- Never answer questions that need {owner_name} themselves "
        "(plans, money, decisions, promises) - say they will reply when back.\n"
        "- Never share personal details (phone, address, passwords, codes, money).\n"
        f"- Never invent facts about where {owner_name} is or what they are doing.\n"
        + reveal
    )


def _openai_reply(history, owner_name: str):
    """Chat completions via any OpenAI-compatible endpoint."""
    messages = [{"role": "system", "content": _system_prompt(owner_name)}]
    for role, text in history:
        messages.append(
            {"role": "user" if role == "them" else "assistant", "content": text}
        )
    try:
        resp = requests.post(
            cfg.OPENAI_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {cfg.OPENAI_API_KEY}"},
            json={
                "model": cfg.OPENAI_MODEL,
                "messages": messages,
                "max_tokens": 160,
                "temperature": 0.7,
            },
            timeout=AI_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001 - fall back to local reply on any failure
        log.warning("OpenAI-compatible reply failed: %s", exc)
        return None


def _gemini_reply(history, owner_name: str):
    """Google Gemini generateContent REST call."""
    contents = []
    for role, text in history:
        contents.append(
            {"role": "user" if role == "them" else "model", "parts": [{"text": text}]}
        )
    if not contents:
        contents = [{"role": "user", "parts": [{"text": "(no previous messages)"}]}]
    payload = {
        "system_instruction": {"parts": [{"text": _system_prompt(owner_name)}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 160, "temperature": 0.7},
    }
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.GEMINI_MODEL}:generateContent",
            params={"key": cfg.GEMINI_API_KEY},
            json=payload,
            timeout=AI_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini reply failed: %s", exc)
        return None


def _local_reply(owner_name: str, history=None) -> str:
    """Pick a varied local template, avoiding the previous bot reply."""
    # Respect an explicitly customized template. The shipped default is
    # treated as unset so users get the requested varied wording.
    template = cfg.AUTO_REPLY_TEMPLATE
    normalized_template = (template or "").strip().replace("—", "-")
    normalized_default = DEFAULT_AUTO_REPLY_TEMPLATE.replace("—", "-")
    if normalized_template and normalized_template != normalized_default:
        try:
            return template.format(owner=owner_name)
        except (KeyError, IndexError):
            return template

    previous_reply = next(
        (text for role, text in reversed(history or []) if role == "us"), None
    )
    choices = [
        message for message in LOCAL_REPLIES
        if message.format(owner=owner_name) != previous_reply
    ]
    return random.choice(choices or list(LOCAL_REPLIES)).format(owner=owner_name)


def generate_reply(history, owner_name: str) -> str:
    """Return the text of the auto-reply. Never raises."""
    provider = cfg.AI_PROVIDER

    if provider != "none" and provider in ("auto", "openai") and cfg.OPENAI_API_KEY:
        text = _openai_reply(history, owner_name)
        if text:
            return text[:MAX_REPLY_CHARS]

    if provider != "none" and provider in ("auto", "gemini") and cfg.GEMINI_API_KEY:
        text = _gemini_reply(history, owner_name)
        if text:
            return text[:MAX_REPLY_CHARS]

    return _local_reply(owner_name, history)[:MAX_REPLY_CHARS]
