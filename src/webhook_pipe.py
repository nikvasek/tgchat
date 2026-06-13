from __future__ import annotations

import asyncio
import logging
from datetime import timezone

import aiohttp
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

from .chat_resolver import resolve_chat_entities
from .config_store import ConfigStore
from .pipe_buffer import PipeBuffer
from .telegram_safety import telegram_safety
from .telegram_utils import author_name, entity_title, entity_username, message_link

logger = logging.getLogger(__name__)


class WebhookPipe:
    SENDER_INTERVAL = 2
    CHAT_REFRESH_INTERVAL = 60

    def __init__(
        self,
        client: TelegramClient,
        store: ConfigStore,
        buffer: PipeBuffer,
    ):
        self.client = client
        self.store = store
        self.buffer = buffer
        self._running = False
        self._allowed_chat_ids: set[int] = set()
        self._sender_task: asyncio.Task | None = None
        self._refresh_task: asyncio.Task | None = None
        self._handler = None

    async def _refresh_chats(self) -> None:
        app_config = await self.store.load()
        if not app_config.chats:
            self._allowed_chat_ids = set()
            return

        try:
            entities = await resolve_chat_entities(self.client, app_config.chats)
        except Exception as error:
            logger.warning("ТРУБА: не удалось обновить чаты: %s", error)
            return

        self._allowed_chat_ids = {entity.id for entity in entities}
        logger.info("ТРУБА: слушаю %s чатов", len(self._allowed_chat_ids))

    async def _build_payload(self, event) -> dict:
        chat_entity = await event.get_chat()
        try:
            sender = await event.get_sender()
        except RPCError:
            sender = None

        msg_date = event.message.date
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)

        return {
            "message_id": event.message.id,
            "chat_id": chat_entity.id,
            "chat_title": entity_title(chat_entity),
            "chat_username": entity_username(chat_entity),
            "author": author_name(sender),
            "date": msg_date.isoformat(),
            "text": event.message.message or "",
            "link": message_link(chat_entity, event.message.id),
            "source": "pipe",
        }

    def _register_handler(self) -> None:
        @self.client.on(events.NewMessage())
        async def handler(event):
            if not self._running:
                return

            app_config = await self.store.load()
            if not app_config.pipe_enabled or not app_config.webhook_url:
                return

            try:
                chat = await event.get_chat()
            except RPCError:
                return

            if chat.id not in self._allowed_chat_ids:
                return

            try:
                await telegram_safety.before_request("pipe message")
                payload = await self._build_payload(event)
                dedup_key = f"{payload['chat_id']}:{payload['message_id']}"
                added = await self.buffer.enqueue(dedup_key, payload)
                if added:
                    logger.debug(
                        "ТРУБА: в буфер chat=%s msg=%s",
                        payload["chat_title"],
                        payload["message_id"],
                    )
            except FloodWaitError as error:
                await telegram_safety.handle_flood_wait(error, "pipe")
            except Exception as error:
                logger.error("ТРУБА: ошибка обработки сообщения: %s", error)

        self._handler = handler

    async def _send_payload(self, session: aiohttp.ClientSession, url: str, payload: dict) -> None:
        timeout = aiohttp.ClientTimeout(total=30)
        async with session.post(url, json=payload, timeout=timeout) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(f"HTTP {response.status}: {body[:200]}")

    async def _sender_loop(self) -> None:
        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    app_config = await self.store.load()
                    url = app_config.webhook_url
                    if not app_config.pipe_enabled or not url:
                        await asyncio.sleep(self.SENDER_INTERVAL)
                        continue

                    pending = await self.buffer.fetch_pending()
                    for item in pending:
                        try:
                            await self._send_payload(session, url, item["payload"])
                            await self.buffer.mark_sent(item["id"])
                            logger.debug("ТРУБА: отправлено %s", item["dedup_key"])
                        except Exception as error:
                            attempts = item["attempts"] + 1
                            await self.buffer.mark_retry(item["id"], attempts, str(error))
                            logger.warning(
                                "ТРУБА: retry %s (%s) — %s",
                                item["dedup_key"],
                                attempts,
                                error,
                            )
                        await asyncio.sleep(0.3)
                except Exception as error:
                    logger.exception("ТРУБА: ошибка sender loop: %s", error)

                await asyncio.sleep(self.SENDER_INTERVAL)

    async def _refresh_loop(self) -> None:
        while self._running:
            try:
                await self._refresh_chats()
            except Exception as error:
                logger.warning("ТРУБА: refresh loop: %s", error)
            await asyncio.sleep(self.CHAT_REFRESH_INTERVAL)

    async def start(self) -> None:
        if self._running:
            return
        await self.buffer.connect()
        await self._refresh_chats()
        self._running = True
        self._register_handler()
        self._sender_task = asyncio.create_task(self._sender_loop())
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("ТРУБА запущена (real-time → PostgreSQL → webhook)")

    async def stop(self) -> None:
        self._running = False
        if self._sender_task:
            self._sender_task.cancel()
        if self._refresh_task:
            self._refresh_task.cancel()
        await self.buffer.close()
        logger.info("ТРУБА остановлена")
