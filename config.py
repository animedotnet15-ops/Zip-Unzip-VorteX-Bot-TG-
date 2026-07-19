"""Environment-backed configuration for the ZIP/Unzip bot."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    bot_username: str
    owner_id: int
    database_path: str
    work_dir: str
    local_bot_api_base: str  # optional, blank = official cloud Bot API
    max_upload_mb: int

    @classmethod
    def from_env(cls) -> "Config":
        try:
            owner_id = int(_required("OWNER_ID"))
        except ValueError as exc:
            raise RuntimeError("OWNER_ID must be a numeric Telegram user ID.") from exc

        try:
            max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "2000"))
        except ValueError as exc:
            raise RuntimeError("MAX_UPLOAD_MB must be a whole number.") from exc

        return cls(
            bot_token=_required("BOT_TOKEN"),
            bot_username=_required("BOT_USERNAME").lstrip("@"),
            owner_id=owner_id,
            database_path=os.getenv("DATABASE_PATH", "zipbot.db").strip(),
            work_dir=os.getenv("WORK_DIR", "zip_workdir").strip(),
            local_bot_api_base=os.getenv("LOCAL_BOT_API_BASE", "").strip().rstrip("/"),
            max_upload_mb=max_upload_mb,
        )


config = Config.from_env()
