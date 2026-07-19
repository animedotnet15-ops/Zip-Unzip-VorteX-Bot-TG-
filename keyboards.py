"""Inline keyboards for the ZIP/Unzip bot's settings dashboard."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎨 Welcome Message", callback_data="set:welcome")],
        [InlineKeyboardButton(text="🔗 Shortener Settings", callback_data="set:shortener")],
        [InlineKeyboardButton(text="🔒 Force-Subscribe", callback_data="set:fsub")],
        [InlineKeyboardButton(text="📋 Channels (Log/Dump/Request)", callback_data="set:channels")],
        [InlineKeyboardButton(text="🤖 Bot On/Off", callback_data="set:botswitch")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def welcome_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🖼️ Set Welcome Photo", callback_data="set:welcomephoto")],
        [InlineKeyboardButton(text="✍️ Set Welcome Text", callback_data="set:welcometext")],
        [InlineKeyboardButton(text="👑 Set Owner Username", callback_data="set:ownerusername")],
        [InlineKeyboardButton(text="🥷 Set Admin Username", callback_data="set:adminusername")],
        [InlineKeyboardButton(text="🤝 Set Support Link", callback_data="set:supportlink")],
        [InlineKeyboardButton(text="🌐 Set Website Link", callback_data="set:websitelink")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shortener_settings_keyboard(overall_on: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"🔀 Shortener: {'🟢 ON' if overall_on else '🔴 OFF'}",
            callback_data="set:toggleoverall"
        )],
        [InlineKeyboardButton(text="⏱️ Access Duration", callback_data="set:accesstime")],
        [InlineKeyboardButton(text="🛡️ Anti-Bypass Min/Max Time", callback_data="set:verifytime")],
        [InlineKeyboardButton(text="👤 Per-User Access Override", callback_data="set:useroverride")],
        [InlineKeyboardButton(text="🌐 Set Domain/API (owner only)", callback_data="set:shortenercreds")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📝 Set Log Channel", callback_data="set:logchannel")],
        [InlineKeyboardButton(text="📦 Set Dump Channel", callback_data="set:dumpchannel")],
        [InlineKeyboardButton(text="📨 Set Request Channel", callback_data="set:requestchannel")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard(target: str = "set:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data=target)]])


def bot_switch_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"🤖 Bot: {'🟢 ON' if enabled else '🔴 OFF'}",
            callback_data="set:togglebot"
        )],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="set:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def batch_progress_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📦 Create ZIP", callback_data="batch:create")],
        [InlineKeyboardButton(text="❌ Cancel Task", callback_data="batch:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def verify_keyboard(verify_url: str, tutorial_url: str = "") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔑 Verify", url=verify_url)]]
    if tutorial_url:
        rows.append([InlineKeyboardButton(text="🎬 How to Verify", url=tutorial_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def approval_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"appr:{user_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"rej:{user_id}"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)
    
