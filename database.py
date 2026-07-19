"""SQLite persistence for the ZIP/Unzip bot."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from config import config


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            parent = Path(self.path).parent
            if str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)
            async with self.connection() as db:
                await db.executescript(
                    """
                    PRAGMA journal_mode=WAL;

                    CREATE TABLE IF NOT EXISTS users (
                        user_id     INTEGER PRIMARY KEY,
                        first_name  TEXT    NOT NULL DEFAULT '',
                        username    TEXT    NOT NULL DEFAULT '',
                        created_at  INTEGER NOT NULL,
                        last_seen   INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS admins (
                        user_id    INTEGER PRIMARY KEY,
                        added_by   INTEGER NOT NULL,
                        added_at   INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS bans (
                        user_id    INTEGER PRIMARY KEY,
                        reason     TEXT    NOT NULL DEFAULT '',
                        until_ts   INTEGER NOT NULL DEFAULT 0,
                        created_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS mutes (
                        user_id    INTEGER PRIMARY KEY,
                        until_ts   INTEGER NOT NULL,
                        reason     TEXT    NOT NULL DEFAULT '',
                        created_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS settings (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS shortener_overrides (
                        user_id INTEGER PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 1
                    );

                    CREATE TABLE IF NOT EXISTS approvals (
                        user_id    INTEGER PRIMARY KEY,
                        approved   INTEGER NOT NULL DEFAULT 0,
                        decided_by INTEGER,
                        decided_at INTEGER,
                        request_msg_id INTEGER,
                        requested_at   INTEGER
                    );

                    CREATE TABLE IF NOT EXISTS pending_tokens (
                        token      TEXT    PRIMARY KEY,
                        user_id    INTEGER NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        used       INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS access_sessions (
                        user_id    INTEGER PRIMARY KEY,
                        granted_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS bypass_events (
                        event_key  TEXT    NOT NULL,
                        user_id    INTEGER NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY(event_key, user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_pending_tokens_user ON pending_tokens(user_id);
                    """
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('bot_enabled', '1')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('shortener_overall', '1')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('min_verify_seconds', '180')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('max_verify_seconds', '300')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('access_duration_seconds', '21600')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('approval_required', '0')"
                )
                await db.commit()
            self._initialized = True

    # ------------------------------------------------------------------ #
    #  Users
    # ------------------------------------------------------------------ #
    async def touch_user(self, user_id: int, first_name: str, username: str) -> None:
        now = int(time.time())
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO users(user_id, first_name, username, created_at, last_seen)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username   = excluded.username,
                    last_seen  = excluded.last_seen
                """,
                (user_id, first_name, username, now, now),
            )
            await db.commit()

    async def get_user_by_username(self, username: str):
        username = username.lstrip("@").strip()
        async with self.connection() as db:
            return await (
                await db.execute(
                    "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
                )
            ).fetchone()

    async def all_user_ids(self) -> list[int]:
        async with self.connection() as db:
            rows = await (await db.execute("SELECT user_id FROM users")).fetchall()
            return [int(r["user_id"]) for r in rows]

    async def user_count(self) -> int:
        async with self.connection() as db:
            row = await (await db.execute("SELECT COUNT(*) c FROM users")).fetchone()
            return int(row["c"])

    # ------------------------------------------------------------------ #
    #  Admins (dynamic, in addition to the single env OWNER_ID)
    # ------------------------------------------------------------------ #
    async def add_admin(self, user_id: int, added_by: int) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO admins(user_id, added_by, added_at) VALUES(?, ?, ?)",
                (user_id, added_by, int(time.time())),
            )
            await db.commit()

    async def remove_admin(self, user_id: int) -> bool:
        async with self.connection() as db:
            cur = await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def is_admin_db(self, user_id: int) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
            ).fetchone()
            return row is not None

    async def list_admins(self) -> list[int]:
        async with self.connection() as db:
            rows = await (await db.execute("SELECT user_id FROM admins")).fetchall()
            return [int(r["user_id"]) for r in rows]

    # ------------------------------------------------------------------ #
    #  Bans / Mutes
    # ------------------------------------------------------------------ #
    async def ban_user(self, user_id: int, reason: str, seconds: int = 0) -> None:
        until_ts = (int(time.time()) + seconds) if seconds > 0 else 0
        async with self.connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO bans(user_id, reason, until_ts, created_at) VALUES(?, ?, ?, ?)",
                (user_id, reason, until_ts, int(time.time())),
            )
            await db.commit()

    async def unban_user(self, user_id: int) -> bool:
        async with self.connection() as db:
            cur = await db.execute("DELETE FROM bans WHERE user_id=?", (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def is_banned(self, user_id: int) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT until_ts FROM bans WHERE user_id=?", (user_id,))
            ).fetchone()
        if not row:
            return False
        until_ts = int(row["until_ts"])
        if until_ts and until_ts < int(time.time()):
            await self.unban_user(user_id)
            return False
        return True

    async def mute_user(self, user_id: int, seconds: int, reason: str) -> None:
        until_ts = int(time.time()) + seconds
        async with self.connection() as db:
            await db.execute(
                "INSERT OR REPLACE INTO mutes(user_id, until_ts, reason, created_at) VALUES(?, ?, ?, ?)",
                (user_id, until_ts, reason, int(time.time())),
            )
            await db.commit()

    async def unmute_user(self, user_id: int) -> bool:
        async with self.connection() as db:
            cur = await db.execute("DELETE FROM mutes WHERE user_id=?", (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def is_muted(self, user_id: int) -> tuple[bool, int]:
        """Returns (is_muted, seconds_remaining)."""
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT until_ts FROM mutes WHERE user_id=?", (user_id,))
            ).fetchone()
        if not row:
            return False, 0
        remaining = int(row["until_ts"]) - int(time.time())
        if remaining <= 0:
            await self.unmute_user(user_id)
            return False, 0
        return True, remaining

    # ------------------------------------------------------------------ #
    #  Settings (generic key/value)
    # ------------------------------------------------------------------ #
    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            ).fetchone()
            return str(row["value"]) if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            await db.commit()

    async def get_int_setting(self, key: str, default: int) -> int:
        raw = await self.get_setting(key, str(default))
        try:
            return int(raw)
        except ValueError:
            return default

    async def get_bool_setting(self, key: str, default: bool) -> bool:
        raw = await self.get_setting(key, "1" if default else "0")
        return raw == "1"

    # Force-subscribe channels (max 6, enforced by caller)
    async def request_channel_id(self) -> str:
        return await self.get_setting("request_channel_id", "")

    async def log_channel_id(self) -> str:
        return await self.get_setting("log_channel_id", "")

    async def dump_channel_id(self) -> str:
        return await self.get_setting("dump_channel_id", "")

    async def get_fsub_channels(self) -> list[dict]:
        raw = await self.get_setting("fsub_channels", "[]")
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def set_fsub_channels(self, channels: list[dict]) -> None:
        await self.set_setting("fsub_channels", json.dumps(channels))

    async def add_fsub_channel(self, chat_id: int, title: str) -> tuple[bool, str]:
        channels = await self.get_fsub_channels()
        if len(channels) >= 6:
            return False, "Maximum of 6 force-subscribe channels already set."
        if any(c["chat_id"] == chat_id for c in channels):
            return False, "That channel is already added."
        channels.append({"chat_id": chat_id, "title": title})
        await self.set_fsub_channels(channels)
        return True, "Channel added."

    async def remove_fsub_channel(self, chat_id: int) -> bool:
        channels = await self.get_fsub_channels()
        new_channels = [c for c in channels if c["chat_id"] != chat_id]
        changed = len(new_channels) != len(channels)
        if changed:
            await self.set_fsub_channels(new_channels)
        return changed

    # ------------------------------------------------------------------ #
    #  Per-user shortener override
    # ------------------------------------------------------------------ #
    async def set_user_shortener(self, user_id: int, enabled: bool) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO shortener_overrides(user_id, enabled) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled",
                (user_id, 1 if enabled else 0),
            )
            await db.commit()

    async def clear_user_shortener(self, user_id: int) -> None:
        async with self.connection() as db:
            await db.execute("DELETE FROM shortener_overrides WHERE user_id=?", (user_id,))
            await db.commit()

    async def get_user_shortener_override(self, user_id: int) -> bool | None:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT enabled FROM shortener_overrides WHERE user_id=?", (user_id,)
                )
            ).fetchone()
            return bool(row["enabled"]) if row else None

    # ------------------------------------------------------------------ #
    #  Approvals (simple manual allow-list; used only if approval_required=1)
    # ------------------------------------------------------------------ #
    async def record_approval_request(self, user_id: int, request_msg_id: int | None) -> None:
        now = int(time.time())
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO approvals(user_id, approved, request_msg_id, requested_at) "
                "VALUES(?, 0, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET request_msg_id=excluded.request_msg_id, requested_at=excluded.requested_at",
                (user_id, request_msg_id, now),
            )
            await db.commit()

    async def has_requested(self, user_id: int) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT 1 FROM approvals WHERE user_id=?", (user_id,))
            ).fetchone()
            return row is not None

    async def approve_user(self, user_id: int, decided_by: int) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO approvals(user_id, approved, decided_by, decided_at) VALUES(?, 1, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET approved=1, decided_by=excluded.decided_by, decided_at=excluded.decided_at",
                (user_id, decided_by, int(time.time())),
            )
            await db.commit()

    async def unapprove_user(self, user_id: int, decided_by: int) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO approvals(user_id, approved, decided_by, decided_at) VALUES(?, 0, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET approved=0, decided_by=excluded.decided_by, decided_at=excluded.decided_at",
                (user_id, decided_by, int(time.time())),
            )
            await db.commit()

    async def is_approved(self, user_id: int) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT approved FROM approvals WHERE user_id=?", (user_id,))
            ).fetchone()
            return bool(row["approved"]) if row else False

    # ------------------------------------------------------------------ #
    #  Shortener verification tokens (min/max verify window)
    # ------------------------------------------------------------------ #
    async def create_pending_token(self, user_id: int) -> str:
        import secrets

        now = int(time.time())
        max_seconds = await self.get_int_setting("max_verify_seconds", 300)
        expires_at = now + max_seconds
        async with self.connection() as db:
            await db.execute("DELETE FROM pending_tokens WHERE user_id=? AND used=0", (user_id,))
            for _ in range(10):
                token = secrets.token_urlsafe(20).replace("-", "A").replace("_", "B")
                try:
                    await db.execute(
                        "INSERT INTO pending_tokens(token, user_id, created_at, expires_at, used) "
                        "VALUES(?, ?, ?, ?, 0)",
                        (token, user_id, now, expires_at),
                    )
                    await db.commit()
                    return token
                except aiosqlite.IntegrityError:
                    continue
        raise RuntimeError("Could not generate a unique verify token")

    async def claim_token(self, token: str, user_id: int) -> str:
        """Returns: 'ok' | 'missing' | 'expired' | 'user_mismatch' | 'used' | 'too_fast'."""
        now = int(time.time())
        min_seconds = await self.get_int_setting("min_verify_seconds", 180)
        async with self.connection() as db:
            row = await (
                await db.execute("SELECT * FROM pending_tokens WHERE token=?", (token,))
            ).fetchone()
            if not row:
                return "missing"
            if int(row["user_id"]) != user_id:
                return "user_mismatch"
            if int(row["used"]) == 1:
                return "used"
            if int(row["expires_at"]) < now:
                return "expired"

            elapsed = now - int(row["created_at"])
            if elapsed < min_seconds:
                await db.execute("UPDATE pending_tokens SET used=1 WHERE token=?", (token,))
                await db.commit()
                return "too_fast"

            await db.execute("UPDATE pending_tokens SET used=1 WHERE token=?", (token,))
            await db.commit()
            return "ok"

    # ------------------------------------------------------------------ #
    #  Bot-access sessions (granted after a successful shortener verify)
    # ------------------------------------------------------------------ #
    async def grant_access_session(self, user_id: int) -> int:
        duration = await self.get_int_setting("access_duration_seconds", 21600)
        now = int(time.time())
        expires_at = now + duration
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO access_sessions(user_id, granted_at, expires_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET granted_at=excluded.granted_at, expires_at=excluded.expires_at",
                (user_id, now, expires_at),
            )
            await db.commit()
        return expires_at

    async def has_valid_access_session(self, user_id: int) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT expires_at FROM access_sessions WHERE user_id=?", (user_id,)
                )
            ).fetchone()
            return bool(row) and int(row["expires_at"]) > int(time.time())

    # ------------------------------------------------------------------ #
    #  Bypass strikes
    # ------------------------------------------------------------------ #
    async def record_bypass(self, user_id: int, event_key: str) -> bool:
        """Returns True if this was a newly recorded bypass event (not a dup)."""
        async with self.connection() as db:
            try:
                await db.execute(
                    "INSERT INTO bypass_events(event_key, user_id, created_at) VALUES(?, ?, ?)",
                    (event_key, user_id, int(time.time())),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False


database = Database(config.database_path)
