from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import config
from database import database
import keyboards as kb
import zip_utils

LOG = logging.getLogger("zipbot")

if config.local_bot_api_base:
    session = AiohttpSession(api=TelegramAPIServer.from_base(config.local_bot_api_base))
    bot = Bot(token=config.bot_token, session=session, default=DefaultBotProperties(parse_mode="HTML"))
else:
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode="HTML"))

dp = Dispatcher()
router = Router()
dp.include_router(router)

DEFAULT_WELCOME_TEXT = (
    "🔮 𝖶ᴇʟᴄᴏᴍᴇ 𝖳ᴏ 𝖳ʜᴇ 𝖹ɪᴘ𝖵ᴏʀᴛᴇx 𝖧ᴜʙ 🌌\n\n"
    "💎 𝖨 ᴍᴀᴋᴇ ᴀɴᴅ ᴜɴᴢɪᴘ ʏᴏᴜʀ ᴀʀᴄʜɪᴠᴇ𝗌 ɪɴ ᴀ ᴍᴀᴛᴛᴇʀ ᴏғ 𝗌ᴇᴄᴏɴᴅ𝗌 ⚡\n"
    "🧬 𝖲ᴍᴀʀᴛ ғɪʟᴛᴇʀ𝗌 · 𝖨𝖦 ǫᴜᴀʟɪᴛʏ sᴘᴇᴇᴅ · 𝖹ᴇʀᴏ sᴛᴏʀᴀɢᴇ sʟᴏᴡᴅᴏᴡɴ 🧩\n\n"
    "🌟 𝖶ʜᴀᴛ 𝖨 𝖢ᴀɴ 𝖶ʜɪᴘ 𝖴ᴘ 𝖥ᴏʀ 𝖸ᴏᴜ\n\n"
    "🔓 𝖴ɴᴢɪᴘ & 𝖤xᴛʀᴀᴄᴛ 𝖠ʀᴄʜɪᴠᴇ𝗌\n"
    "💼 𝖢ʀᴇᴀᴛᴇ & 𝖬ᴀᴋᴇ 𝖭ᴇᴡ 𝖹𝖨𝖯𝗌\n"
    "🛡️ 𝖯ʀɪᴠᴀᴛᴇ 𝖲ᴇ𝗌𝗌ɪᴏɴ 𝖯ʀᴏᴄᴇ𝗌𝗌ɪɴɢ\n"
    "🧹 𝖨ɴ𝗌ᴛᴀɴᴛ 𝖠ᴜᴛᴏ-𝖢ʟᴇᴀɴᴜᴘ\n\n"
    "⚡️ 𝖫ᴇᴛ'𝗌 𝖦ᴇᴛ 𝖲ᴛᴀʀᴛᴇᴅ\n\n"
    "1️⃣ 𝖳ᴏ 𝖴ɴᴢɪᴘ ➔ 𝖥ᴏʀᴡᴀʀᴅ ᴏʀ ᴅʀᴏᴘ ᴀɴʏ .ᴢɪᴘ 𝖿ɪʟᴇ ʜᴇʀᴇ 👇\n"
    "2️⃣ 𝖳ᴏ 𝖬ᴀᴋᴇ 𝖹𝖨𝖯 ➔ 𝖴ᴘʟᴏᴀᴅ ᴀʟʟ ʏᴏᴜʀ ᴍᴇᴅɪᴀ ᴏʀ ғɪʟᴇ𝗌\n"
    "3️⃣ 𝖳ʏᴘᴇ /batchzip ᴛᴏ sᴇᴀʟ ᴛʜᴇᴍ ɪɴᴛᴏ ᴏɴᴇ ғɪʟᴇ 🪄\n\n"
    "🔻 𝖯ɪᴄᴋ ʏᴏᴜʀ ᴀᴄᴛɪᴏɴ ᴀɴᴅ ʟᴇᴛ's ʀᴏʟʟ 🎬"
)

# In-memory state (fine to lose on restart)
BATCH_SESSIONS: dict[int, list[dict]] = {}      # user_id -> [{file_id, name, kind}]
AWAITING: dict[int, str] = {}                    # user_id -> setting key being edited


# ------------------------------------------------------------------ #
#  Permission helpers
# ------------------------------------------------------------------ #
def is_owner(user_id: int) -> bool:
    return user_id == config.owner_id


async def is_admin(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    return await database.is_admin_db(user_id)


def parse_duration(text: str) -> int | None:
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?", text)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2) or "m"
    if unit.startswith("s"):
        return value
    if unit.startswith("m"):
        return value * 60
    if unit.startswith("h"):
        return value * 3600
    if unit.startswith("d"):
        return value * 86400
    return None


def human_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if secs and not parts: parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


async def resolve_target_user_id(arg: str) -> int | None:
    arg = arg.strip()
    if arg.startswith("@"):
        arg = arg[1:]
    if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
        return int(arg)
    row = await database.get_user_by_username(arg)
    return int(row["user_id"]) if row else None


def mention(user) -> str:
    name = html.escape(user.first_name or "there")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


# ------------------------------------------------------------------ #
#  Welcome / start animation
# ------------------------------------------------------------------ #
async def play_start_animation(message: Message, user) -> None:
    m = mention(user)
    msg = await message.answer(f"Hᴇʏ {m} 👋...")
    await asyncio.sleep(1)
    await msg.edit_text("Sᴛᴀʀᴛ... !!")
    await asyncio.sleep(1)
    await msg.edit_text("Sᴛᴀʀᴛɪɴɢ...‼️")
    await asyncio.sleep(1)
    await msg.edit_text(f"🔑 {m} ᴠᴇʀɪғʏɪɴɢ...")
    await asyncio.sleep(1)

    sticker_id = await database.get_setting("start_sticker", "")
    if sticker_id:
        try:
            sticker_msg = await message.answer_sticker(sticker_id)
            await asyncio.sleep(1)
            await sticker_msg.delete()
        except Exception:
            pass

    try:
        await msg.delete()
    except Exception:
        pass


async def send_welcome(message: Message, user) -> None:
    text = await database.get_setting("welcome_text", DEFAULT_WELCOME_TEXT)
    text = text.replace("{mention}", mention(user))
    photo_id = await database.get_setting("welcome_photo", "")

    rows = []
    owner_username = await database.get_setting("owner_username", "")
    admin_username = await database.get_setting("admin_username", "")
    support_link = await database.get_setting("support_link", "")
    website_link = await database.get_setting("website_link", "")

    row1 = []
    if owner_username:
        row1.append(InlineKeyboardButton(text="👑 Owner", url=f"https://t.me/{owner_username.lstrip('@')}"))
    if admin_username:
        row1.append(InlineKeyboardButton(text="🥷 Admin", url=f"https://t.me/{admin_username.lstrip('@')}"))
    if row1:
        rows.append(row1)

    row2 = []
    if support_link:
        row2.append(InlineKeyboardButton(text="🤝 Support", url=support_link))
    if website_link:
        row2.append(InlineKeyboardButton(text="🌐 Website", url=website_link))
    if row2:
        rows.append(row2)

    rows.append([InlineKeyboardButton(text="📖 Help", callback_data="help:show")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    if photo_id:
        try:
            await message.answer_photo(photo_id, caption=text, reply_markup=keyboard)
        except TelegramBadRequest:
            await message.answer_photo(photo_id, caption=text, reply_markup=keyboard, parse_mode=None)
    else:
        try:
            await message.answer(text, reply_markup=keyboard)
        except TelegramBadRequest:
            await message.answer(text, reply_markup=keyboard, parse_mode=None)


# ------------------------------------------------------------------ #
#  Force-Subscribe
# ------------------------------------------------------------------ #
async def missing_fsub_channels(user_id: int) -> list[dict]:
    channels = await database.get_fsub_channels()
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in {"left", "kicked"}:
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return missing


async def send_fsub_prompt(message: Message, missing: list[dict]) -> None:
    rows = []
    for ch in missing:
        try:
            invite = await bot.export_chat_invite_link(ch["chat_id"])
        except Exception:
            invite = ""
        if invite:
            rows.append([InlineKeyboardButton(text=f"🔒 Join {ch['title']}", url=invite)])
    rows.append([InlineKeyboardButton(text="✅ I've Joined", callback_data="fsub:recheck")])
    await message.answer(
        "🔒 <b>Join Required</b>\n<i>Please join the channel(s)/group(s) below to use this bot, then tap "
        "\"I've Joined\".</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ------------------------------------------------------------------ #
#  Shortener verification (anti-bypass, min/max window)
# ------------------------------------------------------------------ #
async def shorten_url(long_url: str) -> str:
    domain = await database.get_setting("shortener_domain", "")
    api_token = await database.get_setting("shortener_api", "")
    if not domain or not api_token:
        return long_url
    api_url = f"https://{domain}/api?api={api_token}&url={long_url}"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                for key in ("shortenedUrl", "shorten_url", "short"):
                    if data.get(key):
                        return data[key]
    except Exception as e:
        LOG.warning(f"Shortener API failed: {e}")
    return long_url


async def requires_shortener(user_id: int) -> bool:
    if await is_admin(user_id):
        return False
    if not await database.get_bool_setting("shortener_overall", True):
        return False
    override = await database.get_user_shortener_override(user_id)
    if override is False:
        return False
    return True


async def send_verify_prompt(message: Message, user_id: int) -> None:
    token = await database.create_pending_token(user_id)
    deep_link = f"https://t.me/{config.bot_username}?start=verify_{token}"
    verify_url = await shorten_url(deep_link)
    tutorial_url = await database.get_setting("tutorial_url", "")
    duration = await database.get_int_setting("access_duration_seconds", 21600)
    await message.answer(
        "🔐 <b>Please complete the verification process to gain access to the bot features.</b>\n"
        f"<i>For {human_duration(duration)}</i>",
        reply_markup=kb.verify_keyboard(verify_url, tutorial_url),
    )


async def notify_admins_bypass(user) -> None:
    text = (
        f"🚨 <b>Bypass Detected</b>\n\n"
        f"👤 {mention(user)} (<code>{user.id}</code>) attempted to bypass shortener verification "
        f"and has been auto-muted."
    )
    log_channel = await database.log_channel_id()
    targets = []
    if log_channel:
        targets.append(int(log_channel))
    targets.append(config.owner_id)
    for admin_id in await database.list_admins():
        targets.append(admin_id)
    for chat_id in set(targets):
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            pass


async def log_verification(user) -> None:
    log_channel = await database.log_channel_id()
    if not log_channel:
        return
    text = (
        "✅ <b>Verification Completed</b>\n\n"
        f"👤 Name: {html.escape(user.first_name or '')}\n"
        f"🔗 Username: @{user.username if user.username else '—'}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
    )
    try:
        await bot.send_message(int(log_channel), text)
    except Exception:
        pass


async def handle_verify_payload(message: Message, user, token: str) -> None:
    result = await database.claim_token(token, user.id)
    if result == "ok":
        expires_at = await database.grant_access_session(user.id)
        duration = await database.get_int_setting("access_duration_seconds", 21600)
        await message.answer(f"✅ <b>Verification complete.</b> You can use the bot for {human_duration(duration)} ✅")
        await log_verification(user)
    elif result == "too_fast":
        mute_seconds = 3600
        await database.mute_user(user.id, mute_seconds, "Anti-bypass triggered")
        await database.record_bypass(user.id, token)
        await message.answer(
            "🚨 <b>Bypass Detected!</b>\n\n"
            "You have used a bypass tool. I am sending your report to the admin and muting you. "
            "If you want to use the bot again, contact the admin."
        )
        await notify_admins_bypass(user)
    elif result == "expired":
        await message.answer("⌛ <b>This verification link has expired.</b> Send /start to get a new one.")
    else:
        await message.answer("❌ <b>Invalid or already-used verification link.</b> Send /start to get a new one.")


# ------------------------------------------------------------------ #
#  Approval gate (request channel)
# ------------------------------------------------------------------ #
async def send_approval_request(user) -> bool:
    channel_id = await database.request_channel_id()
    if not channel_id:
        return False
    text = (
        "🆕 <b>New Access Request</b>\n\n"
        f"👤 <b>User:</b> {mention(user)}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🔗 <b>Username:</b> {'@' + user.username if user.username else '—'}\n\n"
        "⬇️ Approve or reject this user's access to the bot."
    )
    try:
        sent = await bot.send_message(int(channel_id), text, reply_markup=kb.approval_request_keyboard(user.id))
        await database.record_approval_request(user.id, sent.message_id)
        return True
    except Exception as e:
        LOG.warning(f"Could not post approval request: {e}")
        await database.record_approval_request(user.id, None)
        return False


async def notify_approval_decision(target_id: int, approved: bool) -> None:
    text = (
        "✅ <b>You've been approved!</b> You can now use the bot — send /start to begin."
        if approved else
        "❌ <b>Your access has been unapproved.</b> Contact the admin if you think this is a mistake."
    )
    try:
        await bot.send_message(target_id, text)
    except Exception as e:
        LOG.warning(f"Could not notify user {target_id}: {e}")


# ------------------------------------------------------------------ #
#  /start
# ------------------------------------------------------------------ #
@router.message(Command("start"))
async def start_handler(message: Message, command: CommandObject):
    user = message.from_user
    await database.touch_user(user.id, user.first_name or "", user.username or "")

    if not await database.get_bool_setting("bot_enabled", True) and not await is_admin(user.id):
        await message.answer("🔴 <b>The bot is currently offline for maintenance.</b> Please check back later.")
        return

    if await database.is_banned(user.id):
        await message.answer("⛔ <b>You are banned from using this bot.</b>")
        return

    muted, remaining = await database.is_muted(user.id)
    if muted:
        await message.answer(
            f"🔇 <b>You cannot use the bot.</b>\n<b>Reason:</b> Admin has muted you.\n"
            f"<i>Time remaining: {human_duration(remaining)}. Contact admin.</i>"
        )
        return

    payload = (command.args or "").strip()
    if payload.startswith("verify_"):
        await handle_verify_payload(message, user, payload[len("verify_"):])
        return

    if await database.get_bool_setting("approval_required", False) and not await is_admin(user.id):
        if not await database.is_approved(user.id):
            if await database.has_requested(user.id):
                await message.answer("⏳ <b>Your access request is still pending admin approval.</b>")
            else:
                posted = await send_approval_request(user)
                if posted:
                    await message.answer("📨 <b>Access request sent!</b> An admin will review it shortly.")
                else:
                    await message.answer("⚠️ <b>Approval is required, but no request channel is configured.</b> Contact the admin.")
            return

    await play_start_animation(message, user)
    await send_welcome(message, user)

    missing = await missing_fsub_channels(user.id)
    if missing:
        await send_fsub_prompt(message, missing)
        return

    if await requires_shortener(user.id) and not await database.has_valid_access_session(user.id):
        await send_verify_prompt(message, user.id)


@router.callback_query(F.data == "fsub:recheck")
async def fsub_recheck_handler(cb: CallbackQuery):
    missing = await missing_fsub_channels(cb.from_user.id)
    if missing:
        await cb.answer("❌ You still haven't joined all required channels.", show_alert=True)
        return
    await cb.answer("✅ Thanks for joining!")
    try:
        await cb.message.delete()
    except Exception:
        pass
    if await requires_shortener(cb.from_user.id) and not await database.has_valid_access_session(cb.from_user.id):
        await send_verify_prompt(cb.message, cb.from_user.id)
    else:
        await cb.message.answer("✅ <b>You're all set!</b> Send a file to get started.")


# ------------------------------------------------------------------ #
#  Access gate used before any file / zip action
# ------------------------------------------------------------------ #
async def ensure_access(message: Message) -> bool:
    user = message.from_user
    if not await database.get_bool_setting("bot_enabled", True) and not await is_admin(user.id):
        await message.answer("🔴 <b>The bot is currently offline for maintenance.</b>")
        return False
    if await database.is_banned(user.id):
        await message.answer("⛔ <b>You are banned from using this bot.</b>")
        return False
    muted, remaining = await database.is_muted(user.id)
    if muted:
        await message.answer(f"🔇 <b>You are muted.</b> Time remaining: {human_duration(remaining)}.")
        return False
    if await database.get_bool_setting("approval_required", False) and not await is_admin(user.id):
        if not await database.is_approved(user.id):
            await message.answer("⏳ <b>You need admin approval first.</b> Send /start to request access.")
            return False
    missing = await missing_fsub_channels(user.id)
    if missing:
        await send_fsub_prompt(message, missing)
        return False
    if await requires_shortener(user.id) and not await database.has_valid_access_session(user.id):
        await send_verify_prompt(message, user.id)
        return False
    return True


# ------------------------------------------------------------------ #
#  /single, /batchzip, /cancelmy, /cancelall
# ------------------------------------------------------------------ #
@router.message(Command("single"))
async def single_handler(message: Message):
    if not await ensure_access(message):
        return
    BATCH_SESSIONS.pop(message.from_user.id, None)
    await message.answer("📤 <b>Send me a file.</b> I'll create a ZIP file and send it back to you.")


@router.message(Command("batchzip"))
async def batchzip_handler(message: Message):
    if not await ensure_access(message):
        return
    user_id = message.from_user.id
    if user_id in BATCH_SESSIONS:
        await message.answer(f"📦 <b>Batch mode already active</b> — {len(BATCH_SESSIONS[user_id])} file(s) queued.\nSend more files, or use the buttons below.", reply_markup=kb.batch_progress_keyboard())
        return
    BATCH_SESSIONS[user_id] = []
    await message.answer(
        "📦 <b>Batch ZIP mode started!</b>\n<i>Send your files one by one, in order. "
        "When you're done, tap \"Create ZIP\".</i>"
    )


async def _cancel_batch(user_id: int) -> None:
    BATCH_SESSIONS.pop(user_id, None)


@router.message(Command("cancelmy"))
async def cancel_my_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in BATCH_SESSIONS:
        await message.answer("ℹ️ You don't have an active task.")
        return
    await _cancel_batch(user_id)
    await message.answer("❌ <b>Your task has been cancelled.</b>")


@router.message(Command("cancelall"))
async def cancel_all_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return
    count = len(BATCH_SESSIONS)
    BATCH_SESSIONS.clear()
    await message.answer(f"❌ <b>Cancelled {count} active task(s) bot-wide.</b>")


@router.callback_query(F.data == "batch:cancel")
async def batch_cancel_callback(cb: CallbackQuery):
    await _cancel_batch(cb.from_user.id)
    await cb.answer("❌ Task cancelled.")
    try:
        await cb.message.edit_text("❌ <b>Task cancelled.</b>")
    except Exception:
        pass


def _extract_file(message: Message):
    """Returns (file_id, filename, kind) or None."""
    if message.document:
        return message.document.file_id, message.document.file_name or "file", "document"
    if message.video:
        return message.video.file_id, message.video.file_name or "video.mp4", "video"
    if message.audio:
        return message.audio.file_id, message.audio.file_name or "audio.mp3", "audio"
    if message.animation:
        return message.animation.file_id, message.animation.file_name or "animation.mp4", "animation"
    if message.photo:
        return message.photo[-1].file_id, "photo.jpg", "photo"
    return None


async def _download_to(file_id: str, dest: Path) -> bool:
    try:
        await bot.download(file_id, destination=dest)
        return True
    except TelegramBadRequest as e:
        LOG.warning(f"Download failed (file may exceed Bot API size limit): {e}")
        return False


@router.message(F.document | F.video | F.audio | F.animation)
async def file_handler(message: Message):
    if not await ensure_access(message):
        return
    user = message.from_user
    extracted = _extract_file(message)
    if not extracted:
        return
    file_id, filename, kind = extracted

    if message.document and filename.lower().endswith(".zip"):
        await unzip_flow(message, file_id, filename)
        return

    if user.id in BATCH_SESSIONS:
        BATCH_SESSIONS[user.id].append({"file_id": file_id, "name": filename, "kind": kind})
        count = len(BATCH_SESSIONS[user.id])
        listing = "\n".join(f"{i}. {f['name']}" for i, f in enumerate(BATCH_SESSIONS[user.id], start=1))
        await message.answer(
            f"📥 <b>File {count} queued:</b> <code>{filename}</code>\n\n<b>Current order:</b>\n{listing}",
            reply_markup=kb.batch_progress_keyboard(),
        )
        return

    await single_zip_flow(message, file_id, filename)


async def single_zip_flow(message: Message, file_id: str, filename: str) -> None:
    status = await message.answer("⏳ <b>Downloading & creating your ZIP...</b>")
    task_dir = zip_utils.new_task_dir()
    try:
        local_path = task_dir / zip_utils.safe_name(filename)
        ok = await _download_to(file_id, local_path)
        if not ok:
            await status.edit_text("❌ <b>Couldn't download that file</b> — it may be too large for this bot's current server limits.")
            return
        zip_name = f"{Path(filename).stem}.zip"
        zip_path = zip_utils.create_zip(task_dir, [(local_path, filename)], zip_name)
        await status.edit_text("📤 <b>Uploading ZIP...</b>")
        sent = await message.answer_document(
            zip_path.open("rb"), caption=f"✅ <code>{zip_path.name}</code>"
        )
        await status.delete()
        await forward_to_dump(sent)
    finally:
        zip_utils.cleanup_dir(task_dir)


@router.callback_query(F.data == "batch:create")
async def batch_create_callback(cb: CallbackQuery):
    user_id = cb.from_user.id
    files = BATCH_SESSIONS.get(user_id, [])
    if not files:
        await cb.answer("⚠️ No files queued yet.", show_alert=True)
        return
    await cb.answer("📦 Creating ZIP...")
    try:
        await cb.message.edit_text(f"⏳ <b>Downloading {len(files)} file(s) & creating your ZIP...</b>", reply_markup=None)
    except Exception:
        pass

    task_dir = zip_utils.new_task_dir()
    try:
        ordered = []
        for f in files:
            local_path = task_dir / zip_utils.safe_name(f["name"])
            ok = await _download_to(f["file_id"], local_path)
            if not ok:
                await cb.message.answer(f"❌ Skipped <code>{f['name']}</code> — too large to download.")
                continue
            ordered.append((local_path, f["name"]))
        if not ordered:
            await cb.message.answer("❌ <b>None of the queued files could be downloaded.</b>")
            return
        user_label = cb.from_user.username or cb.from_user.first_name or str(user_id)
        zip_name = f"{zip_utils.safe_name(user_label)}_{int(time.time())}.zip"
        zip_path = zip_utils.create_zip(task_dir, ordered, zip_name)
        sent = await cb.message.answer_document(zip_path.open("rb"), caption="✅ <b>Your ZIP File Is Ready!</b>")
        await forward_to_dump(sent)
    finally:
        zip_utils.cleanup_dir(task_dir)
        BATCH_SESSIONS.pop(user_id, None)


async def unzip_flow(message: Message, file_id: str, filename: str) -> None:
    status = await message.answer("⏳ <b>Downloading & extracting archive...</b>")
    task_dir = zip_utils.new_task_dir()
    try:
        zip_path = task_dir / zip_utils.safe_name(filename)
        ok = await _download_to(file_id, zip_path)
        if not ok:
            await status.edit_text("❌ <b>Couldn't download that archive</b> — it may be too large for this bot's current server limits.")
            return
        extract_dir = task_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        files = zip_utils.extract_zip(zip_path, extract_dir)
        if not files:
            await status.edit_text("⚠️ <b>That archive appears to be empty.</b>")
            return
        await status.edit_text(f"📤 <b>Sending {len(files)} extracted file(s)...</b>")
        for f in files:
            if f.is_file():
                sent = await message.answer_document(f.open("rb"), caption=f"📄 <code>{f.name}</code>")
                await forward_to_dump(sent)
        await status.delete()
    finally:
        zip_utils.cleanup_dir(task_dir)


async def forward_to_dump(sent_message: Message) -> None:
    dump_channel = await database.dump_channel_id()
    if not dump_channel:
        return
    try:
        await bot.copy_message(int(dump_channel), sent_message.chat.id, sent_message.message_id)
    except Exception as e:
        LOG.warning(f"Could not forward to dump channel: {e}")


# ------------------------------------------------------------------ #
#  Admin: mute / unmute / ban / unban
# ------------------------------------------------------------------ #
@router.message(Command("mute"))
async def mute_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    parts = (command.args or "").strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ <b>Usage:</b> <code>/mute [username|user_id] [time]</code> e.g. <code>/mute 12345 1h</code>")
        return
    target_id = await resolve_target_user_id(parts[0])
    seconds = parse_duration(parts[1])
    if target_id is None:
        await message.answer("❌ Could not resolve that user.")
        return
    if seconds is None:
        await message.answer("❌ Invalid duration. Use formats like <code>30m</code>, <code>1h</code>, <code>2d</code>.")
        return
    await database.mute_user(target_id, seconds, "Muted by admin")
    await message.answer(f"🔇 User <code>{target_id}</code> muted for {human_duration(seconds)}.")
    try:
        await bot.send_message(target_id, f"🔇 <b>You cannot use the bot.</b>\n<b>Reason:</b> Admin has muted you for {human_duration(seconds)}. Contact admin.")
    except Exception:
        pass


@router.message(Command("unmute"))
async def unmute_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/unmute [username|user_id]</code>")
        return
    ok = await database.unmute_user(target_id)
    await message.answer(f"🔊 User <code>{target_id}</code> unmuted." if ok else "ℹ️ That user wasn't muted.")


@router.message(Command("ban"))
async def ban_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    parts = (command.args or "").strip().split()
    if not parts:
        await message.answer("⚠️ <b>Usage:</b> <code>/ban [username|user_id] [time (optional)]</code>")
        return
    target_id = await resolve_target_user_id(parts[0])
    if target_id is None:
        await message.answer("❌ Could not resolve that user.")
        return
    seconds = 0
    if len(parts) > 1:
        parsed = parse_duration(parts[1])
        if parsed is None:
            await message.answer("❌ Invalid duration. Use formats like <code>30m</code>, <code>1h</code>, <code>2d</code>.")
            return
        seconds = parsed
    await database.ban_user(target_id, "Banned by admin", seconds)
    duration_text = f" for {human_duration(seconds)}" if seconds else " permanently"
    await message.answer(f"⛔ User <code>{target_id}</code> banned{duration_text}.")
    try:
        await bot.send_message(target_id, f"⛔ <b>You have been banned{duration_text}.</b>")
    except Exception:
        pass


@router.message(Command("unban"))
async def unban_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/unban [username|user_id]</code>")
        return
    ok = await database.unban_user(target_id)
    await message.answer(f"✅ User <code>{target_id}</code> unbanned." if ok else "ℹ️ That user wasn't banned.")


# ------------------------------------------------------------------ #
#  Owner-only: add/remove admin
# ------------------------------------------------------------------ #
@router.message(Command("addadmin"))
async def add_admin_handler(message: Message, command: CommandObject):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Owner only.")
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/addadmin [username|user_id]</code>")
        return
    await database.add_admin(target_id, message.from_user.id)
    await message.answer(f"✅ User <code>{target_id}</code> is now an admin.")


@router.message(Command("removeadmin"))
async def remove_admin_handler(message: Message, command: CommandObject):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Owner only.")
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/removeadmin [username|user_id]</code>")
        return
    ok = await database.remove_admin(target_id)
    await message.answer(f"✅ User <code>{target_id}</code> removed from admins." if ok else "ℹ️ That user wasn't an admin.")


# ------------------------------------------------------------------ #
#  Approve / Unapprove
# ------------------------------------------------------------------ #
@router.message(Command("approve"))
async def approve_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/approve [username|user_id]</code>")
        return
    await database.approve_user(target_id, message.from_user.id)
    await notify_approval_decision(target_id, approved=True)
    await message.answer(f"✅ User <code>{target_id}</code> approved and notified.")


@router.message(Command("unapprove"))
async def unapprove_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip()
    target_id = await resolve_target_user_id(arg) if arg else None
    if target_id is None:
        await message.answer("⚠️ <b>Usage:</b> <code>/unapprove [username|user_id]</code>")
        return
    await database.unapprove_user(target_id, message.from_user.id)
    await notify_approval_decision(target_id, approved=False)
    await message.answer(f"✅ User <code>{target_id}</code> unapproved and notified.")


@router.callback_query(F.data.startswith("appr:"))
async def approve_callback(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    target_id = int(cb.data.split(":")[1])
    await database.approve_user(target_id, cb.from_user.id)
    await notify_approval_decision(target_id, approved=True)
    await cb.answer("✅ Approved!")
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n✅ Approved by {html.escape(cb.from_user.first_name or '')}", reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("rej:"))
async def reject_callback(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    target_id = int(cb.data.split(":")[1])
    await database.unapprove_user(target_id, cb.from_user.id)
    await notify_approval_decision(target_id, approved=False)
    await cb.answer("❌ Rejected.")
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n❌ Rejected by {html.escape(cb.from_user.first_name or '')}", reply_markup=None)
    except Exception:
        pass


# ------------------------------------------------------------------ #
#  Broadcast
# ------------------------------------------------------------------ #
@router.message(Command("broadcast"))
async def broadcast_handler(message: Message, command: CommandObject):
    if not await is_admin(message.from_user.id):
        return
    text = (command.args or "").strip()
    if not text and not message.reply_to_message:
        await message.answer("⚠️ <b>Usage:</b> <code>/broadcast [message]</code> or reply to a message with <code>/broadcast</code>")
        return
    user_ids = await database.all_user_ids()
    status = await message.answer(f"📢 <b>Broadcasting to {len(user_ids)} user(s)...</b>")
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            if message.reply_to_message:
                await bot.copy_message(uid, message.chat.id, message.reply_to_message.message_id)
            else:
                await bot.send_message(uid, text)
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"📢 <b>Broadcast complete.</b>\n✅ Sent: {sent}\n❌ Failed: {failed}")


# ------------------------------------------------------------------ #
#  /help
# ------------------------------------------------------------------ #
async def send_help(target: Message, user_id: int) -> None:
    caller_id = user_id
    text = (
        "<b>📖 Available Commands</b>\n\n"
        "<b>👤 Everyone</b>\n"
        "<blockquote>"
        "• /start — wake up the bot\n"
        "• /single — zip one file\n"
        "• /batchzip — zip multiple files in order\n"
        "• /cancelmy — cancel your current task\n"
        "• Send a .zip file to unzip it\n"
        "</blockquote>\n"
    )
    if await is_admin(caller_id):
        text += (
            "<b>🛡️ Admin / Owner</b>\n"
            "<blockquote>"
            "• /mute [user] [time], /unmute [user]\n"
            "• /ban [user] [time], /unban [user]\n"
            "• /approve [user], /unapprove [user]\n"
            "• /broadcast [text]\n"
            "• /cancelall — cancel every active task\n"
            "• /setsticker — reply to a sticker to set the /start animation sticker\n"
            "• /setting — open the settings dashboard\n"
            "</blockquote>\n"
        )
    if is_owner(caller_id):
        text += (
            "<b>👑 Owner only</b>\n"
            "<blockquote>"
            "• /addadmin [user], /removeadmin [user]\n"
            "</blockquote>"
        )
    await target.answer(text)


@router.callback_query(F.data == "help:show")
async def help_button_handler(cb: CallbackQuery):
    await cb.answer()
    await send_help(cb.message, cb.from_user.id)


# ------------------------------------------------------------------ #
#  /setting dashboard
# ------------------------------------------------------------------ #
@router.message(Command("setsticker"))
async def set_sticker_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return
    if not message.reply_to_message or not message.reply_to_message.sticker:
        await message.answer("⚠️ <b>Usage:</b> Reply to a sticker with <code>/setsticker</code>.")
        return
    file_id = message.reply_to_message.sticker.file_id
    await database.set_setting("start_sticker", file_id)
    await message.answer("✅ <b>Start animation sticker updated!</b>\n<i>It'll now play during the /start sequence.</i>")


@router.message(Command("removesticker"))
async def remove_sticker_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await database.set_setting("start_sticker", "")
    await message.answer("✅ <b>Start animation sticker removed.</b>\n<i>The /start sequence will skip the sticker step.</i>")


@router.message(Command("setting"))
async def setting_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("⚙️ <b>Settings Dashboard</b>", reply_markup=kb.main_settings_keyboard())


@router.callback_query(F.data == "set:main")
async def set_main_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING.pop(cb.from_user.id, None)
    await cb.answer()
    await cb.message.edit_text("⚙️ <b>Settings Dashboard</b>", reply_markup=kb.main_settings_keyboard())


@router.callback_query(F.data == "set:welcome")
async def set_welcome_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text("🎨 <b>Welcome Message Settings</b>", reply_markup=kb.welcome_settings_keyboard())


@router.callback_query(F.data == "set:welcomephoto")
async def set_welcomephoto_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "welcome_photo"
    await cb.answer()
    await cb.message.edit_text("🖼️ <b>Send the new welcome photo now.</b>", reply_markup=kb.back_keyboard("set:welcome"))


@router.callback_query(F.data == "set:welcometext")
async def set_welcometext_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "welcome_text"
    await cb.answer()
    await cb.message.edit_text(
        "✍️ <b>Send the new welcome text now.</b>\n<i>Use <code>{mention}</code> where the user's name should appear.</i>",
        reply_markup=kb.back_keyboard("set:welcome"),
    )


@router.callback_query(F.data == "set:ownerusername")
async def set_ownerusername_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "owner_username"
    current = await database.get_setting("owner_username", "not set")
    await cb.answer()
    await cb.message.edit_text(
        f"👑 <b>Owner Button</b>\n<i>Current: @{current}</i>\n\nSend the owner's Telegram @username (no need to include the @).",
        reply_markup=kb.back_keyboard("set:welcome"),
    )


@router.callback_query(F.data == "set:adminusername")
async def set_adminusername_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "admin_username"
    current = await database.get_setting("admin_username", "not set")
    await cb.answer()
    await cb.message.edit_text(
        f"🥷 <b>Admin Button</b>\n<i>Current: @{current}</i>\n\nSend the admin's Telegram @username (no need to include the @).",
        reply_markup=kb.back_keyboard("set:welcome"),
    )


@router.callback_query(F.data == "set:supportlink")
async def set_supportlink_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "support_link"
    current = await database.get_setting("support_link", "not set")
    await cb.answer()
    await cb.message.edit_text(
        f"🤝 <b>Support Button</b>\n<i>Current: {current}</i>\n\nSend the full support link (e.g. a Telegram group/channel URL).",
        reply_markup=kb.back_keyboard("set:welcome"),
    )


@router.callback_query(F.data == "set:websitelink")
async def set_websitelink_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "website_link"
    current = await database.get_setting("website_link", "not set")
    await cb.answer()
    await cb.message.edit_text(
        f"🌐 <b>Website Button</b>\n<i>Current: {current}</i>\n\nSend the full website URL.",
        reply_markup=kb.back_keyboard("set:welcome"),
    )


@router.callback_query(F.data == "set:shortener")
async def set_shortener_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    overall_on = await database.get_bool_setting("shortener_overall", True)
    await cb.answer()
    await cb.message.edit_text("🔗 <b>Shortener Settings</b>", reply_markup=kb.shortener_settings_keyboard(overall_on))


@router.callback_query(F.data == "set:toggleoverall")
async def toggle_overall_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    current = await database.get_bool_setting("shortener_overall", True)
    await database.set_setting("shortener_overall", "0" if current else "1")
    overall_on = not current
    await cb.answer(f"Shortener turned {'ON' if overall_on else 'OFF'}.")
    await cb.message.edit_text("🔗 <b>Shortener Settings</b>", reply_markup=kb.shortener_settings_keyboard(overall_on))


@router.callback_query(F.data == "set:accesstime")
async def set_accesstime_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "access_duration"
    current = await database.get_int_setting("access_duration_seconds", 21600)
    await cb.answer()
    await cb.message.edit_text(
        f"⏱️ <b>Bot Access Duration</b>\n<i>Current: {human_duration(current)}</i>\n\n"
        "Send the new duration, e.g. <code>6h</code>, <code>30m</code>, <code>1d</code>.",
        reply_markup=kb.back_keyboard("set:shortener"),
    )


@router.callback_query(F.data == "set:verifytime")
async def set_verifytime_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "verify_minmax"
    mn = await database.get_int_setting("min_verify_seconds", 180)
    mx = await database.get_int_setting("max_verify_seconds", 300)
    await cb.answer()
    await cb.message.edit_text(
        f"🛡️ <b>Anti-Bypass Verify Window</b>\n<i>Current: min {human_duration(mn)}, max {human_duration(mx)}</i>\n\n"
        "Send new <b>min</b> and <b>max</b> time separated by a space, e.g. <code>3m 5m</code>.",
        reply_markup=kb.back_keyboard("set:shortener"),
    )


@router.callback_query(F.data == "set:useroverride")
async def set_useroverride_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "user_override"
    await cb.answer()
    await cb.message.edit_text(
        "👤 <b>Per-User Shortener Override</b>\n\n"
        "Send <code>username on</code> or <code>username off</code> (or a numeric user ID) to control "
        "whether that specific user needs to complete the shortener.",
        reply_markup=kb.back_keyboard("set:shortener"),
    )


@router.callback_query(F.data == "set:shortenercreds")
async def set_shortenercreds_cb(cb: CallbackQuery):
    if not is_owner(cb.from_user.id):
        await cb.answer("⛔ Owner only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "shortener_domain_api"
    domain = await database.get_setting("shortener_domain", "not set")
    await cb.answer()
    await cb.message.edit_text(
        f"🌐 <b>Shortener Domain / API</b>\n<i>Current domain: {domain}</i>\n\n"
        "Send the domain and API token separated by a space, e.g.:\n"
        "<code>arolinks.com 4279ddecc0d54699dda07188a...</code>",
        reply_markup=kb.back_keyboard("set:shortener"),
    )


@router.callback_query(F.data == "set:channels")
async def set_channels_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text("📋 <b>Channel Settings</b>", reply_markup=kb.channels_settings_keyboard())


@router.callback_query(F.data == "set:logchannel")
async def set_logchannel_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "log_channel"
    await cb.answer()
    await cb.message.edit_text(
        "📝 <b>Log Channel</b>\n<i>Bot must be an admin there.</i>\n\nSend the channel's numeric ID, e.g. <code>-1001234567890</code>.",
        reply_markup=kb.back_keyboard("set:channels"),
    )


@router.callback_query(F.data == "set:dumpchannel")
async def set_dumpchannel_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "dump_channel"
    await cb.answer()
    await cb.message.edit_text(
        "📦 <b>Dump Channel</b>\n<i>Bot must be an admin there. All zips/files will be copied here.</i>\n\n"
        "Send the channel's numeric ID.",
        reply_markup=kb.back_keyboard("set:channels"),
    )


@router.callback_query(F.data == "set:requestchannel")
async def set_requestchannel_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "request_channel"
    await cb.answer()
    await cb.message.edit_text(
        "📨 <b>Request Channel</b>\n<i>Bot must be an admin there. Access requests will be posted here.</i>\n\n"
        "Send the channel's numeric ID.",
        reply_markup=kb.back_keyboard("set:channels"),
    )


@router.callback_query(F.data == "set:botswitch")
async def set_botswitch_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    enabled = await database.get_bool_setting("bot_enabled", True)
    await cb.answer()
    await cb.message.edit_text("🤖 <b>Bot On/Off Switch</b>", reply_markup=kb.bot_switch_keyboard(enabled))


@router.callback_query(F.data == "set:togglebot")
async def toggle_bot_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    current = await database.get_bool_setting("bot_enabled", True)
    await database.set_setting("bot_enabled", "0" if current else "1")
    enabled = not current
    await cb.answer(f"Bot turned {'ON' if enabled else 'OFF'}.")
    await cb.message.edit_text("🤖 <b>Bot On/Off Switch</b>", reply_markup=kb.bot_switch_keyboard(enabled))


@router.callback_query(F.data == "set:fsub")
async def set_fsub_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    channels = await database.get_fsub_channels()
    rows = [[InlineKeyboardButton(text=f"❌ {c['title']}", callback_data=f"fsub:remove:{c['chat_id']}")] for c in channels]
    rows.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="fsub:add")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")])
    text = f"🔒 <b>Force-Subscribe Channels</b> ({len(channels)}/6)\n<i>Tap a channel to remove it.</i>"
    await cb.answer()
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "fsub:add")
async def fsub_add_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    AWAITING[cb.from_user.id] = "fsub_add"
    await cb.answer()
    await cb.message.edit_text(
        "➕ <b>Add Force-Subscribe Channel</b>\n<i>Bot must be an admin there (max 6 total).</i>\n\n"
        "Forward any message from that channel/group here, or send its numeric chat ID.",
        reply_markup=kb.back_keyboard("set:fsub"),
    )


@router.callback_query(F.data.startswith("fsub:remove:"))
async def fsub_remove_cb(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("⛔ Admins only.", show_alert=True)
        return
    chat_id = int(cb.data.split(":")[2])
    await database.remove_fsub_channel(chat_id)
    await cb.answer("✅ Removed.")
    channels = await database.get_fsub_channels()
    rows = [[InlineKeyboardButton(text=f"❌ {c['title']}", callback_data=f"fsub:remove:{c['chat_id']}")] for c in channels]
    rows.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="fsub:add")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")])
    await cb.message.edit_text(
        f"🔒 <b>Force-Subscribe Channels</b> ({len(channels)}/6)\n<i>Tap a channel to remove it.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# ------------------------------------------------------------------ #
#  Captures free-text / photo replies for whichever setting is AWAITING
# ------------------------------------------------------------------ #
@router.message(F.photo)
async def awaiting_photo_handler(message: Message):
    user_id = message.from_user.id
    if AWAITING.get(user_id) != "welcome_photo":
        return
    await database.set_setting("welcome_photo", message.photo[-1].file_id)
    AWAITING.pop(user_id, None)
    await message.answer("✅ <b>Welcome photo updated!</b>", reply_markup=kb.welcome_settings_keyboard())


@router.message(F.forward_from_chat)
async def awaiting_forward_handler(message: Message):
    user_id = message.from_user.id
    if AWAITING.get(user_id) != "fsub_add":
        return
    chat = message.forward_from_chat
    ok, note = await database.add_fsub_channel(chat.id, chat.title or str(chat.id))
    AWAITING.pop(user_id, None)
    await message.answer(("✅ " if ok else "❌ ") + note, reply_markup=kb.back_keyboard("set:fsub"))


@router.message(F.text & ~F.text.startswith("/"))
async def awaiting_text_handler(message: Message):
    user_id = message.from_user.id
    key = AWAITING.get(user_id)
    if not key:
        return
    text = message.text.strip()

    if key in {"owner_username", "admin_username", "support_link", "website_link"}:
        value = text.lstrip("@") if key in {"owner_username", "admin_username"} else text
        await database.set_setting(key, value)
        AWAITING.pop(user_id, None)
        await message.answer(f"✅ <b>{key.replace('_', ' ').title()} saved.</b>", reply_markup=kb.back_keyboard("set:welcome"))

    elif key == "welcome_text":
        await database.set_setting("welcome_text", message.html_text or text)
        AWAITING.pop(user_id, None)
        await message.answer("✅ <b>Welcome text updated!</b>", reply_markup=kb.welcome_settings_keyboard())

    elif key == "access_duration":
        seconds = parse_duration(text)
        if seconds is None:
            await message.answer("❌ Invalid format. Try e.g. <code>6h</code>.")
            return
        await database.set_setting("access_duration_seconds", str(seconds))
        AWAITING.pop(user_id, None)
        await message.answer(f"✅ <b>Access duration set to {human_duration(seconds)}.</b>", reply_markup=kb.back_keyboard("set:shortener"))

    elif key == "verify_minmax":
        parts = text.split()
        if len(parts) != 2:
            await message.answer("❌ Send two values separated by a space, e.g. <code>3m 5m</code>.")
            return
        mn, mx = parse_duration(parts[0]), parse_duration(parts[1])
        if mn is None or mx is None or mn >= mx:
            await message.answer("❌ Invalid values — min must be less than max.")
            return
        await database.set_setting("min_verify_seconds", str(mn))
        await database.set_setting("max_verify_seconds", str(mx))
        AWAITING.pop(user_id, None)
        await message.answer(
            f"✅ <b>Anti-bypass window set:</b> min {human_duration(mn)}, max {human_duration(mx)}.",
            reply_markup=kb.back_keyboard("set:shortener"),
        )

    elif key == "user_override":
        parts = text.split()
        if len(parts) != 2 or parts[1].lower() not in {"on", "off"}:
            await message.answer("❌ Format: <code>username on</code> or <code>username off</code>.")
            return
        target_id = await resolve_target_user_id(parts[0])
        if target_id is None:
            await message.answer("❌ Could not resolve that user (they must have used /start at least once).")
            return
        await database.set_user_shortener(target_id, parts[1].lower() == "on")
        AWAITING.pop(user_id, None)
        state = "ON (must verify)" if parts[1].lower() == "on" else "OFF (direct access)"
        await message.answer(f"✅ Shortener for <code>{target_id}</code> set to {state}.", reply_markup=kb.back_keyboard("set:shortener"))

    elif key == "shortener_domain_api":
        parts = text.split()
        if len(parts) != 2:
            await message.answer("❌ Send domain and API token separated by a space.")
            return
        domain = parts[0].replace("https://", "").replace("http://", "").rstrip("/")
        await database.set_setting("shortener_domain", domain)
        await database.set_setting("shortener_api", parts[1])
        AWAITING.pop(user_id, None)
        await message.answer(f"✅ <b>Shortener credentials saved.</b>\nDomain: <code>{domain}</code>", reply_markup=kb.back_keyboard("set:shortener"))

    elif key in {"log_channel", "dump_channel", "request_channel"}:
        try:
            int(text)
        except ValueError:
            await message.answer("❌ Must be a numeric chat ID, e.g. <code>-1001234567890</code>.")
            return
        setting_key = {"log_channel": "log_channel_id", "dump_channel": "dump_channel_id", "request_channel": "request_channel_id"}[key]
        await database.set_setting(setting_key, text)
        AWAITING.pop(user_id, None)
        await message.answer("✅ <b>Channel saved.</b>", reply_markup=kb.back_keyboard("set:channels"))

    elif key == "fsub_add":
        try:
            chat_id = int(text)
        except ValueError:
            await message.answer("❌ Send a numeric chat ID, or forward a message from the channel instead.")
            return
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title or str(chat_id)
        except Exception:
            title = str(chat_id)
        ok, note = await database.add_fsub_channel(chat_id, title)
        AWAITING.pop(user_id, None)
        await message.answer(("✅ " if ok else "❌ ") + note, reply_markup=kb.back_keyboard("set:fsub"))



@router.message(Command("help"))
async def help_handler(message: Message):
    await send_help(message, message.from_user.id)
