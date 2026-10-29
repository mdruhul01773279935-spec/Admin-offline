# 🌙 Telegram Away-Reply Bot

Replies to your friends **from your own chats** when you're offline —
for example, "Master is offline right now. He'll reply when he's back."

Built on Telegram's **official Business-bot / Chat Automation** feature:
no userbot, no phone login, **no ban risk**. Your friends see the replies
inside their normal chat with you.

```
Friend:  "hey, are you there?"
                │
                ▼
      Telegram (YOUR account, business connection)
                │  business_message update
                ▼
      this bot (running on your phone via Termux)
                │  • are you away? (no msg from you in this chat for X min)
                │  • cooldown OK? (no auto-reply in the last Y min)
                │  • varied local reply (AI optional)
                ▼
      sendMessage(business_connection_id=…)
                │
                ▼
Friend sees:  "Master is offline right now. He'll reply when he's back."
```

---

## How "offline detection" works

Telegram does **not** expose your real online/offline status to bots — only
Telegram itself knows that. But there's a solid trick:

> When you connect a bot to your account, it receives **both sides** of every
> connected chat: your friends' messages **and the messages you type from your
> own phone**. So the bot knows exactly when you last spoke in each chat.

- If you **sent a message in a chat within the last `OWNER_ACTIVE_MINUTES`**
  (default 30) → you're "online" there → the bot stays silent.
- Otherwise you're treated as away → it auto-replies.
- `REPLY_COOLDOWN_MINUTES` (default 120) caps it at **one auto-reply per chat
  per 2 hours**, so it never spams.

Want true presence-based detection? Telegram's built-in *Business → Away
Messages* has an "only if offline" switch (needs Telegram Premium) — but it
can only send one fixed text. Many people run just this bot instead.

## What if my mobile data is off? 📵

Two honest facts first:

1. **Telegram never exposes your phone's data/online status to bots** — there
   is no direct "is his mobile data on?" check.
2. **If the bot runs on your phone, it's cut off too** when your data dies —
   it physically cannot send replies at that moment.

But there's a clean way to get exactly the behaviour you want:

> **Run the bot on a machine with its own internet** (home PC on WiFi, an old
> phone/tablet at home, a free cloud VM, or a cheap VPS). Then your phone
> going dark doesn't matter — the bot still receives your friends' messages
> (Telegram delivers them independently of your phone) and replies through
> your account while you're disconnected.

With that topology, "mobile data off" already works via the silence rule
(you can't send messages → after `OWNER_ACTIVE_MINUTES` the bot takes over).
To detect a lost connection in about 30 seconds, use the **phone heartbeat**:

```
 PHONE (Termux)                       BOT MACHINE (home PC / VPS)
 ┌──────────────────┐                 ┌──────────────────────────┐
 │ heartbeat.sh     │  GET /ping      │ bot.py                   │
 │ every 10 sec ────┼────────────────►│  • pings flowing = alive │
 │ (internet on)    │                 │  • 30 sec without ping   │
 └──────────────────┘                 │    = presume offline     │
        ╳ internet lost...            │      reply when messaged │
        ╳ pings stop                  └──────────────────────────┘
```

- Phone pings `http://<bot-host>:<port>/ping?token=<secret>` every 10 seconds
  by default (`heartbeat.sh` — run it on the phone).
- No ping for `HEARTBEAT_TIMEOUT_SECONDS` (default 30) → the bot assumes your
  phone has lost internet → it replies to the next incoming friend message,
  even in a chat where you were active recently. It does not send messages
  proactively; it replies when someone writes to you.
- Any message you send also counts as a heartbeat, so normal chatting keeps
  the bot quiet.
- When your data returns, pings resume and the bot goes silent again.

Setup: set `HEARTBEAT_PORT=8765`, `HEARTBEAT_SECRET=<random string>` in the
**bot machine's** `.env`; on the **phone's** `.env` add the same two values
plus `HB_HOST=<bot machine IP>`, then run `bash heartbeat.sh`.

> Home PC behind a router? Forward the port (or use a free tunnel like
> cloudflared), or just host on a small VPS — the heartbeat needs the phone
> to *reach* the bot. If you skip the heartbeat entirely, everything still
> works — just with the 30-minute "silent = away" rule.

**If you keep everything on the phone:** when data is off the bot queues up
(see the messages when you reconnect). Set `PROCESS_BACKLOG=true` if you'd
like it to send the late auto-replies as soon as you're back on WiFi/data.

## What your friends see

Replies are sent **through your account's business connection**, so they
appear in the friend's normal private chat with you — not in a bot chat.
Telegram may show a small "via @yourbot" marker on those messages depending
on the client. If you absolutely cannot tolerate any marker, the only
alternative is a *userbot* (Telethon), which breaks Telegram's ToS and risks
your account — not recommended now that this official path exists.

---

## Requirements

- Android phone + [Termux](https://f-droid.org/en/packages/com.termux/)
  (F-Droid version is best) — or any always-on Python environment.
- A Telegram bot token (free, from [@BotFather](https://t.me/BotFather)).
- No AI key is needed: the default uses varied replies built into the program.
  Optionally enable Gemini/OpenAI; in that mode Telegram chat text is sent to
  the selected AI provider to generate replies.

## Setup

### 1. Create the bot with @BotFather

1. Open Telegram → chat with [@BotFather](https://t.me/BotFather) → send `/newbot`.
2. Pick any display name (e.g. `Master Away Bot`) and a username ending in `bot`.
3. Copy the **token** it gives you.

### 2. Install on Termux

```bash
pkg install git -y
git clone <this-repo>        # or copy the folder to your phone
cd telegram-away-bot
bash setup_termux.sh
```

(Or manually: `pkg install python && pip install -r requirements.txt`.)

### 3. Configure

```bash
cp .env.example .env
nano .env      # set BOT_TOKEN and OWNER_NAME; keep AI_PROVIDER=none for privacy
```

Minimum required: `BOT_TOKEN` and `OWNER_NAME`. The default `AI_PROVIDER=none`
chooses varied local templates. Telegram chat text is not sent to Gemini or
another AI service. The bot does not request SMS permission; it only processes
Telegram messages you grant it access to.

### 4. Connect the bot to YOUR Telegram account

This is the magic step that lets it reply inside *your* chats:

1. In Telegram, open **Settings** →
   - newer apps: **Chat Automation**
   - or **Telegram Business** → **Chatbots**
2. Add your bot by @username.
3. Enable its rights: **Reply to messages** and **Read messages**.
4. Choose which chats it can access (your friends / everyone except work…).

The bot learns your account automatically at this moment.

### 5. Run it

```bash
python bot.py
```

Then open the bot's own chat and send `/start`, then `/away on`.
Test with a friend's account — message yourself from there and watch the
auto-reply arrive in that chat.

Keep it running in the background:

```bash
termux-wake-lock
nohup python bot.py > bot.log 2>&1 &
```

**Autostart after reboot** — install the *Termux:Boot* add-on and create
`~/.termux/boot/start-bot.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/telegram-away-bot && nohup python bot.py > bot.log 2>&1 &
```

Also exclude Termux from Android battery optimization, or the system will
kill it.

---

## Commands (in the bot's own chat)

| Command | Effect |
|---|---|
| `/start` | Bind yourself as owner (first time) + help |
| `/away on` / `/away off` | Turn auto-replies on/off |
| `/away` | Toggle |
| `/status` | Current state, AI provider, timings |

## Configuration reference (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather (**required**) |
| `OWNER_ID` | `0` (auto) | Your numeric Telegram id |
| `OWNER_NAME` | `Master` | Name/title inserted into local reply templates |
| `AI_PROVIDER` | `none` | `none` = local/private templates; optional `auto` / `openai` / `gemini` sends Telegram text to an AI provider |
| `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` | — | Any OpenAI-compatible API (OpenAI, Groq, OpenRouter, DeepSeek…) |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | `gemini-2.5-flash` | Google Gemini (free key) |
| `AUTO_REPLY_TEMPLATE` | blank | Optional custom fixed reply; blank = varied templates |
| `OWNER_ACTIVE_MINUTES` | `30` | Silent this long in a chat → "offline" |
| `REPLY_COOLDOWN_MINUTES` | `120` | Max one auto-reply per chat per this |
| `HEARTBEAT_PORT` | `0` (off) | Port for the phone's alive-pings (needs a secret) |
| `HEARTBEAT_SECRET` | — | Random string; required to enable the heartbeat |
| `HEARTBEAT_TIMEOUT_SECONDS` | `30` | No ping this long → presume phone offline |
| `HB_HOST` | `127.0.0.1` | Bot's address, used by `heartbeat.sh` on the phone |
| `REVEAL_AUTOMATION` | `true` | Optional AI admits it is automated if asked |
| `AUTO_READ` | `true` | Mark incoming messages read as you |
| `SEND_TYPING` | `true` | Show "typing…" before replying |
| `PROCESS_BACKLOG` | `false` | Reply to msgs that arrived while bot was off |
| `MAX_HISTORY` | `12` | Recent chat context sent only when AI is enabled |

## Put the project on GitHub and deploy to Render Free

### Upload to GitHub

1. Create a **private** repository on GitHub.
2. Upload the project files from this folder. **Do not upload `.env` or `state.json`**; they contain secrets/private chat data. The included `.gitignore` excludes them when using Git.
3. Make sure `render.yaml`, `render_app.py`, `requirements.txt`, and the bot modules are at the repository root.

I can't push to GitHub directly from this chat, so use GitHub's **Add file → Upload files** page or Git locally.

### Create the Render service

1. Stop `python bot.py` in Termux first. Telegram can't use long polling and a webhook at the same time.
2. In Render, choose **New → Blueprint** (or create a Web Service connected to the repository). Render reads `render.yaml`; choose the **Free** plan.
3. Enter the requested environment values:
   - `BOT_TOKEN`: the token from @BotFather — keep it private.
   - `OWNER_ID`: your numeric Telegram user ID (for example, get it from @userinfobot).
   - `OWNER_NAME`: the name you want in the replies.
   - `WEBHOOK_SECRET` is generated by the Blueprint; leave it private.
4. Deploy and check the Render logs for “Telegram webhook registered”. Then open your bot in Telegram, send `/start`, and `/away on`.

No Gemini key is needed: the Render configuration sets `AI_PROVIDER=none`, which uses varied local templates.

**Free-plan caveat:** Render Free web services sleep after 15 minutes without incoming traffic and can take about a minute to wake. The incoming Telegram webhook should wake the service, but the first reply can be delayed and this is not guaranteed always-on hosting. Render also clears local files when a free service sleeps, so per-chat cooldowns/history may reset; setting `OWNER_ID` in Render keeps the bot able to recognize you after a restart. For dependable prompt replies, use an always-on host/paid service instead. [Render Free limits](https://render.com/docs/free)

## Limitations (Telegram's rules, not ours)

- **Private chats only** — never groups, channels or secret chats.
- The bot can only act in chats with **incoming messages in the last 24h**.
- Only **text messages and captions** trigger replies (stickers/photos/voice
  without text are ignored, to avoid noise).
- A small **"via @bot"** marker may appear on your auto-replies.
- Chat access follows what you granted in step 4 — revoking a chat there
  instantly silences the bot there too.
- Historical messages before connecting are not visible to the bot.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot never replies in my chats | Check step 4: bot connected, **Reply** right enabled, chat included in access |
| Replies even when I'm online | Raise `OWNER_ACTIVE_MINUTES`; make sure you actually *send* a message in that chat (typing alone doesn't count) |
| Replies too often | Raise `REPLY_COOLDOWN_MINUTES` |
| AI answers weird / wrong language | It mirrors the friend's language by design; tune the prompt in `ai_reply.py` |
| Termux bot stopped after phone sleep | `termux-wake-lock`, disable battery optimization for Termux, use Termux:Boot |
| `Could not reach Telegram` | Wrong `BOT_TOKEN`, or no internet |

## Security notes

- `.env` holds your bot token and any optional AI key — **never share it**.
- `AI_PROVIDER=none` keeps reply generation local; enabling Gemini/OpenAI sends recent Telegram chat text to that provider. SMS access is not requested or needed.
- `state.json` stores your owner id and Telegram chat history snippets — keep private.
- The bot ignores control commands from anyone but the owner.

## Project layout

```
telegram-away-bot/
├── bot.py            # main loop + reply logic + heartbeat listener
├── ai_reply.py       # varied local replies; optional OpenAI-compatible / Gemini
├── config.py         # .env loading + settings
├── state.py          # JSON state (owner, connections, per-chat memory)
├── heartbeat.sh      # run on your PHONE: pings the bot to prove data is on
├── render_app.py     # Render webhook entry point
├── render.yaml       # Render Blueprint (Free web service)
├── .gitignore        # prevents committing secrets/runtime data
├── requirements.txt  # requests, Flask, gunicorn
├── .env.example      # configuration template
├── setup_termux.sh   # Termux one-shot installer
└── README.md
```
