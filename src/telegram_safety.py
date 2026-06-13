from __future__ import annotations

import asyncio
import logging
import time

from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)


class TelegramSafety:
    """Защита от блокировок Telegram: паузы и обработка FloodWait."""

    REQUEST_DELAY = 1.2
    CHAT_DELAY = 2.5
    KEYWORD_DELAY = 4.0
    FLOOD_BUFFER = 5
    MAX_FLOOD_WAIT = 3600

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def pause(self, seconds: float, reason: str = "") -> None:
        if seconds <= 0:
            return
        if reason:
            logger.debug("Пауза %.1f сек.: %s", seconds, reason)
        await asyncio.sleep(seconds)

    async def before_request(self, reason: str = "") -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.REQUEST_DELAY:
                await asyncio.sleep(self.REQUEST_DELAY - elapsed)
            self._last_request = time.monotonic()
        if reason:
            logger.debug("Запрос: %s", reason)

    async def between_chats(self) -> None:
        await self.pause(self.CHAT_DELAY, "между чатами")

    async def between_keywords(self) -> None:
        await self.pause(self.KEYWORD_DELAY, "между keywords")

    async def handle_flood_wait(self, error: FloodWaitError, context: str = "") -> None:
        wait_seconds = min(int(error.seconds) + self.FLOOD_BUFFER, self.MAX_FLOOD_WAIT)
        logger.warning(
            "FloodWait %s сек.%s — ждём %s сек.",
            error.seconds,
            f" ({context})" if context else "",
            wait_seconds,
        )
        await asyncio.sleep(wait_seconds)


telegram_safety = TelegramSafety()
