from __future__ import annotations

import logging
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

from .config import AppConfig, EnvConfig
from .exporter import CombinedExporter, MessageExporter
from .messages import FoundMessage
from .telegram_safety import telegram_safety
from .telegram_utils import author_name, entity_title, entity_username, message_link

logger = logging.getLogger(__name__)


def _matches_keyword(text: str, keywords: list[str]) -> str | None:
    lowered = text.lower()
    for keyword in keywords:
        if keyword.lower() in lowered:
            return keyword
    return None


async def _message_to_found(
    client: TelegramClient,
    message,
    chat_entity,
    keyword: str,
    source: str = "monitor",
) -> FoundMessage | None:
    text = message.message or ""
    if not text.strip():
        return None

    msg_date = message.date
    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)

    try:
        sender = await message.get_sender()
    except RPCError:
        sender = None

    return FoundMessage(
        source=source,
        chat_title=entity_title(chat_entity),
        chat_username=entity_username(chat_entity),
        keyword=keyword,
        author=author_name(sender),
        message_date=msg_date,
        text=text,
        link=message_link(chat_entity, message.id),
        message_id=message.id,
    )


class ChatMonitor:
    def __init__(
        self,
        client: TelegramClient,
        app_config: AppConfig,
        env_config: EnvConfig,
        exporter: MessageExporter | CombinedExporter,
    ):
        self.client = client
        self.app_config = app_config
        self.env_config = env_config
        self.exporter = exporter
        self._resolved_chats: list = []

    async def resolve_chats(self) -> list:
        if self._resolved_chats:
            return self._resolved_chats

        resolved = []
        for chat_ref in self.app_config.chats:
            try:
                await telegram_safety.before_request(f"get_entity {chat_ref}")
                entity = await self.client.get_entity(chat_ref)
                resolved.append(entity)
                logger.info("Подключён чат: %s", entity_title(entity))
            except FloodWaitError as error:
                await telegram_safety.handle_flood_wait(error, chat_ref)
                try:
                    entity = await self.client.get_entity(chat_ref)
                    resolved.append(entity)
                except (ValueError, RPCError) as retry_error:
                    logger.error("Не удалось найти чат '%s': %s", chat_ref, retry_error)
            except (ValueError, RPCError) as error:
                logger.error("Не удалось найти чат '%s': %s", chat_ref, error)
            await telegram_safety.between_chats()

        self._resolved_chats = resolved
        return resolved

    def reset_cache(self) -> None:
        self._resolved_chats = []

    async def scan_once(self) -> int:
        if not self.app_config.chats:
            logger.info("Мониторинг: список чатов пуст")
            return 0
        if not self.app_config.keywords:
            logger.info("Мониторинг: список keywords пуст")
            return 0

        chats = await self.resolve_chats()
        if not chats:
            logger.warning("Мониторинг: ни один чат не найден")
            return 0

        found: list[FoundMessage] = []

        for chat_entity in chats:
            chat_name = entity_title(chat_entity)
            try:
                await telegram_safety.before_request(f"scan {chat_name}")
                async for message in self.client.iter_messages(
                    chat_entity,
                    limit=self.app_config.monitor.messages_limit,
                ):
                    keyword = _matches_keyword(message.message or "", self.app_config.keywords)
                    if not keyword:
                        continue

                    item = await _message_to_found(self.client, message, chat_entity, keyword)
                    if item:
                        found.append(item)
                    await telegram_safety.pause(0.3, "между сообщениями")

            except FloodWaitError as error:
                await telegram_safety.handle_flood_wait(error, chat_name)
            except RPCError as error:
                logger.error("Ошибка при сканировании '%s': %s", chat_name, error)

            await telegram_safety.between_chats()

        added = self.exporter.append_messages(self.env_config.sheet_monitor, found)
        logger.info("Мониторинг: найдено %s, добавлено в таблицу %s", len(found), added)
        return added

    async def watch(self) -> None:
        chats = await self.resolve_chats()
        chat_ids = {chat.id for chat in chats}

        @self.client.on(events.NewMessage(chats=chats))
        async def handler(event):
            keyword = _matches_keyword(event.message.message or "", self.app_config.keywords)
            if not keyword:
                return

            chat_entity = await event.get_chat()
            item = await _message_to_found(self.client, event.message, chat_entity, keyword)
            if not item:
                return

            added = self.exporter.append_messages(self.env_config.sheet_monitor, [item])
            if added:
                logger.info(
                    "Новое сообщение в '%s' по ключу '%s'",
                    entity_title(chat_entity),
                    keyword,
                )

        logger.info(
            "Режим watch: слушаю %s чатов. Ctrl+C для остановки.",
            len(chat_ids),
        )
        await self.client.run_until_disconnected()
