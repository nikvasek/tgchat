#!/usr/bin/env python3
"""Экспорт Telethon-сессии в строку для Railway (TELEGRAM_SESSION_STRING)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

from src.config import load_env
from src.telegram_client import create_telegram_client


async def main() -> None:
    load_dotenv()
    env = load_env()
    async with create_telegram_client(env) as client:
        session_string = StringSession.save(client.session)
        if not session_string:
            raise RuntimeError("Не удалось экспортировать сессию. Сначала войдите локально.")
        print(session_string)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
