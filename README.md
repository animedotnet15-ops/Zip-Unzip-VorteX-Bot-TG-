# ZipVortex Hub Bot

A Telegram bot that zips single/multiple files (in order) into one `.zip`, unzips
`.zip` archives you send it, and includes an admin panel with mute/ban,
shortener-based anti-bypass verification, force-subscribe, a request-channel
approval system, and log/dump channels.

## ⚠️ Important: file size limit

Telegram's **official cloud Bot API only allows bots to download files up to ~20MB**
and upload up to ~50MB. To handle bigger files (up to ~2GB) you must run your own
[local Bot API server](https://github.com/tdlib/telegram-bot-api) and point
`LOCAL_BOT_API_BASE` at it in `.env`. **True 4GB is not achievable through the Bot
API at all** — that limit only applies to Telegram Premium users uploading through
the official apps, not to bots. Please don't advertise "4GB support" to your users
unless you've set up a local Bot API server and tested it — the honest ceiling is
~2GB with that server, ~20MB without it.

## Deploying

### Railway
1. Push this folder to a GitHub repo, then **New Project → Deploy from GitHub repo** in Railway.
2. Railway auto-detects Python via `railway.json`/`requirements.txt` and runs `python3 main.py`.
3. Go to your service → **Variables** tab and add the environment variables listed below.
4. **Important — persistence:** Railway's filesystem resets on every redeploy. Go to your
   service → **Volumes → New Volume**, mount it at e.g. `/data`, then set:
   - `DATABASE_PATH=/data/zipbot.db`
   - `WORK_DIR=/data/zip_workdir`
   Without a volume, your bans/settings/admins reset every time you redeploy.

### Render
1. Push this folder to a GitHub repo, then **New → Background Worker** (not "Web Service" —
   this bot doesn't serve HTTP traffic) and connect the repo.
2. `render.yaml` is included, so Render can auto-configure the service via **Blueprint**
   deploy if you prefer (New → Blueprint → select repo).
3. Add the environment variables listed below in the **Environment** tab.
4. **Important — persistence:** Render's disk is ephemeral by default. `render.yaml`
   already attaches a small persistent disk at `/var/data` and points `DATABASE_PATH`/
   `WORK_DIR` there — keep that if you deploy manually instead of via the blueprint.
5. If you deploy as a "Web Service" instead of "Background Worker" (e.g. because your
   plan doesn't offer workers), Render requires binding to `$PORT` — `main.py` already
   starts a tiny health-check server automatically whenever `PORT` is set, so it'll pass
   Render's health check either way.

### Environment variables to set on either platform

| Variable | Required | Example | Notes |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | `123456:AAExample...` | From @BotFather |
| `BOT_USERNAME` | ✅ | `YourZipVortexBot` | No `@` |
| `OWNER_ID` | ✅ | `123456789` | Your numeric Telegram ID, from @userinfobot |
| `DATABASE_PATH` | recommended | `/data/zipbot.db` or `/var/data/zipbot.db` | Point into your mounted volume/disk |
| `WORK_DIR` | recommended | `/data/zip_workdir` or `/var/data/zip_workdir` | Same volume/disk |
| `LOCAL_BOT_API_BASE` | optional | *(blank)* | Only if you're self-hosting a local Bot API server for >20MB files |
| `MAX_UPLOAD_MB` | optional | `2000` | Informational only |
| `PORT` | auto-set by Render | — | Don't set manually; Render/Railway inject this. `main.py` uses it only if present. |

Don't commit your real `.env` file — use each platform's dashboard to set these instead.

## Setup (local)

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in `BOT_TOKEN`, `BOT_USERNAME`, `OWNER_ID`.
3. `python main.py`

## Command reference

**Everyone**
- `/start` — animated welcome + access checks
- `/single` — prompt to zip one file
- `/batchzip` — start an ordered multi-file zip session
- `/cancelmy` — cancel your own active task
- send a `.zip` — bot unzips and returns the contents
- `/help`

**Admin / Owner**
- `/mute [user] [time]`, `/unmute [user]`
- `/ban [user] [time?]`, `/unban [user]`
- `/approve [user]`, `/unapprove [user]`
- `/broadcast [text]` (or reply to a message with `/broadcast`)
- `/cancelall` — clears every user's active batch task
- `/setsticker` — reply to a sticker with this to set the `/start` animation sticker
- `/removesticker` — removes it
- `/setting` — full settings dashboard (welcome message, shortener, force-sub,
  log/dump/request channels, bot on/off)

**Owner only**
- `/addadmin [user]`, `/removeadmin [user]`

## Notes on the approval / request-channel flow

If `Approval Required` is turned on (via `/setting`), new users can't use the bot
until an admin/owner runs `/approve` — a request card (with inline Approve/Reject
buttons) is posted to your configured Request Channel automatically.

## Notes on the shortener anti-bypass system

- `min_verify_seconds` / `max_verify_seconds` control the verification window.
  Completing it too fast triggers a bypass report + auto-mute; too slow expires
  the link.
- `access_duration_seconds` controls how long a completed verification grants
  bot access for, before the user has to verify again.
- Per-user overrides let you exempt specific users from the shortener entirely.
- Admins/owner never need to verify.
- 
