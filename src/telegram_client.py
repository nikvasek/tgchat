from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import EnvConfig


def create_telegram_client(env: EnvConfig) -> TelegramClient:
    if env.session_string:
        return TelegramClient(
            StringSession(env.session_string),
            env.api_id,
            env.api_hash,
        )
    return TelegramClient(env.session_name, env.api_id, env.api_hash)
