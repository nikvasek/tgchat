from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

from .telegram_safety import telegram_safety
from .telegram_utils import entity_title

logger = logging.getLogger(__name__)


async def resolve_chat_entities(client: TelegramClient, chat_refs: list[str]) -> list:
    resolved = []
    for chat_ref in chat_refs:
        try:
            await telegram_safety.before_request(f"get_entity {chat_ref}")
            entity = await client.get_entity(chat_ref)
            resolved.append(entity)
            logger.info("Подключён чат: %s", entity_title(entity))
        except FloodWaitError as error:
            await telegram_safety.handle_flood_wait(error, chat_ref)
            try:
                entity = await client.get_entity(chat_ref)
                resolved.append(entity)
            except (ValueError, RPCError) as retry_error:
                logger.error("Не удалось найти чат '%s': %s", chat_ref, retry_error)
        except (ValueError, RPCError) as error:
            logger.error("Не удалось найти чат '%s': %s", chat_ref, error)
        await telegram_safety.between_chats()
    return resolved
