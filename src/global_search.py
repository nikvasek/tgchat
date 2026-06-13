from __future__ import annotations

import asyncio
import logging
from datetime import timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import (
    InputMessagesFilterEmpty,
    InputPeerEmpty,
    PeerChannel,
    PeerChat,
    PeerUser,
)

from .config import AppConfig, EnvConfig
from .exporter import CombinedExporter, MessageExporter
from .messages import FoundMessage
from .telegram_utils import author_name, entity_title, entity_username, message_link

logger = logging.getLogger(__name__)


class GlobalSearcher:
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

    async def search_once(self) -> int:
        if not self.app_config.keywords:
            logger.info("Глобальный поиск: список keywords пуст")
            return 0

        found: list[FoundMessage] = []
        limit = self.app_config.global_search.limit_per_keyword

        for keyword in self.app_config.keywords:
            logger.info("Глобальный поиск: '%s'", keyword)
            try:
                result = await self.client(
                    SearchGlobalRequest(
                        q=keyword,
                        filter=InputMessagesFilterEmpty(),
                        min_date=None,
                        max_date=None,
                        offset_rate=0,
                        offset_peer=InputPeerEmpty(),
                        offset_id=0,
                        limit=limit,
                    )
                )
            except FloodWaitError as error:
                logger.warning("FloodWait %s сек. при поиске '%s'", error.seconds, keyword)
                await asyncio.sleep(error.seconds)
                continue
            except RPCError as error:
                logger.error("Ошибка глобального поиска '%s': %s", keyword, error)
                continue

            chats_map = {chat.id: chat for chat in result.chats}
            users_map = {user.id: user for user in result.users}

            for message in result.messages:
                text = message.message or ""
                if not text.strip():
                    continue

                peer = message.peer_id
                if isinstance(peer, PeerUser):
                    logger.debug("Пропуск личного чата user_id=%s", peer.user_id)
                    continue

                chat_entity = None
                if isinstance(peer, PeerChannel):
                    chat_entity = chats_map.get(peer.channel_id)
                elif isinstance(peer, PeerChat):
                    chat_entity = chats_map.get(peer.chat_id)

                if chat_entity is None:
                    logger.debug("Не удалось сопоставить чат для peer %s", peer)
                    continue

                sender = None
                from_id = message.from_id
                if isinstance(from_id, PeerUser):
                    sender = users_map.get(from_id.user_id)
                elif isinstance(from_id, PeerChannel):
                    sender = chats_map.get(from_id.channel_id)

                msg_date = message.date
                if msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)

                found.append(
                    FoundMessage(
                        source="global",
                        chat_title=entity_title(chat_entity),
                        chat_username=entity_username(chat_entity),
                        keyword=keyword,
                        author=author_name(sender),
                        message_date=msg_date,
                        text=text,
                        link=message_link(chat_entity, message.id),
                        message_id=message.id,
                    )
                )

        added = self.exporter.append_messages(self.env_config.sheet_global, found)
        logger.info("Глобальный поиск: найдено %s, добавлено в таблицу %s", len(found), added)
        return added
