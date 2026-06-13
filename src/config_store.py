from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .config import AppConfig, GlobalSearchSettings, MonitorSettings, load_config
from .sheets_sync import lists_equal

if TYPE_CHECKING:
    from .sheets_sync import SheetsConfigSync

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "keywords": [],
    "chats": [],
    "google_sheets_url": "",
    "monitor": {
        "messages_limit": 500,
        "poll_interval": 300,
    },
    "global_search": {
        "limit_per_keyword": 100,
    },
}


class ConfigStore:
    def __init__(self, path: str | Path, sheets_sync: SheetsConfigSync | None = None):
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._sheets_sync = sheets_sync
        if not self.path.exists():
            self._write(DEFAULT_CONFIG)

    def _read(self) -> dict:
        with self.path.open(encoding="utf-8") as file:
            return yaml.safe_load(file) or deepcopy(DEFAULT_CONFIG)

    def _write(self, data: dict) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            yaml.dump(data, file, allow_unicode=True, sort_keys=False)

    async def load(self) -> AppConfig:
        async with self._lock:
            return load_config(self.path)

    async def get_raw(self) -> dict:
        async with self._lock:
            return self._read()

    async def _update(self, mutator) -> dict:
        async with self._lock:
            data = self._read()
            mutator(data)
            self._write(data)
            self._push_to_sheets(data)
            return data

    def _push_to_sheets(self, data: dict) -> None:
        if not self._sheets_sync:
            return
        try:
            self._sheets_sync.write_settings(
                data.get("keywords", []),
                data.get("chats", []),
            )
        except Exception as error:
            logger.warning("Не удалось записать настройки в Google: %s", error)

    async def sync_from_google(self) -> tuple[bool, str]:
        if not self._sheets_sync:
            return False, "Google не настроен"

        async with self._lock:
            try:
                sheet_keywords, sheet_chats = self._sheets_sync.read_settings()
            except Exception as error:
                logger.warning("Не удалось прочитать настройки из Google: %s", error)
                return False, f"Ошибка чтения Google: {error}"

            data = self._read()
            local_keywords = data.get("keywords", [])
            local_chats = data.get("chats", [])

            if lists_equal(sheet_keywords, local_keywords) and lists_equal(sheet_chats, local_chats):
                return False, "Без изменений"

            data["keywords"] = sheet_keywords
            data["chats"] = sheet_chats
            self._write(data)
            return True, (
                f"Из Google: {len(sheet_keywords)} keywords, {len(sheet_chats)} чатов"
            )

    async def push_to_google(self) -> tuple[bool, str]:
        if not self._sheets_sync:
            return False, "Google не настроен"

        async with self._lock:
            data = self._read()
            try:
                self._push_to_sheets(data)
            except Exception as error:
                return False, f"Ошибка записи в Google: {error}"

        keywords = data.get("keywords", [])
        chats = data.get("chats", [])
        return True, f"В Google: {len(keywords)} keywords, {len(chats)} чатов"

    async def initial_sync(self) -> None:
        if not self._sheets_sync:
            return

        try:
            sheet_keywords, sheet_chats = self._sheets_sync.read_settings()
        except Exception as error:
            logger.warning("Начальная синхронизация пропущена: %s", error)
            return

        if sheet_keywords or sheet_chats:
            changed, message = await self.sync_from_google()
            logger.info("Начальная синхронизация из Google: %s", message if changed else "без изменений")
            return

        changed, message = await self.push_to_google()
        logger.info("Начальная синхронизация в Google: %s", message if changed else "без изменений")

    async def add_chat(self, chat: str) -> tuple[bool, str]:
        chat = chat.strip()
        if not chat:
            return False, "Пустое значение"

        def mutate(data: dict) -> None:
            chats = data.setdefault("chats", [])
            if chat in chats:
                raise ValueError("Чат уже в списке")
            chats.append(chat)

        try:
            await self._update(mutate)
            return True, f"Чат добавлен: {chat}"
        except ValueError as error:
            return False, str(error)

    async def remove_chat(self, ref: str) -> tuple[bool, str]:
        ref = ref.strip()

        def mutate(data: dict) -> None:
            chats = data.setdefault("chats", [])
            if ref.isdigit():
                index = int(ref) - 1
                if 0 <= index < len(chats):
                    chats.pop(index)
                    return
            if ref in chats:
                chats.remove(ref)
                return
            for idx, chat in enumerate(chats):
                if ref.lower() in chat.lower():
                    chats.pop(idx)
                    return
            raise ValueError(f"Чат не найден: {ref}")

        try:
            await self._update(mutate)
            return True, "Чат удалён"
        except ValueError as error:
            return False, str(error)

    async def add_keyword(self, keyword: str) -> tuple[bool, str]:
        keyword = keyword.strip()
        if not keyword:
            return False, "Пустое значение"

        def mutate(data: dict) -> None:
            keywords = data.setdefault("keywords", [])
            if any(k.lower() == keyword.lower() for k in keywords):
                raise ValueError("Ключевое слово уже есть")
            keywords.append(keyword)

        try:
            await self._update(mutate)
            return True, f"Добавлено: {keyword}"
        except ValueError as error:
            return False, str(error)

    async def remove_keyword(self, ref: str) -> tuple[bool, str]:
        ref = ref.strip()

        def mutate(data: dict) -> None:
            keywords = data.setdefault("keywords", [])
            if ref.isdigit():
                index = int(ref) - 1
                if 0 <= index < len(keywords):
                    keywords.pop(index)
                    return
            for idx, keyword in enumerate(keywords):
                if keyword.lower() == ref.lower():
                    keywords.pop(idx)
                    return
            raise ValueError(f"Ключевое слово не найдено: {ref}")

        try:
            await self._update(mutate)
            return True, "Ключевое слово удалено"
        except ValueError as error:
            return False, str(error)

    async def set_interval(self, minutes: int) -> tuple[bool, str]:
        if minutes < 1:
            return False, "Интервал должен быть не меньше 1 минуты"

        def mutate(data: dict) -> None:
            data.setdefault("monitor", {})["poll_interval"] = minutes * 60

        await self._update(mutate)
        return True, f"Интервал: {minutes} мин."

    async def set_google_url(self, url: str) -> tuple[bool, str]:
        url = url.strip()
        if url and "docs.google.com" not in url and "sheets.google.com" not in url:
            return False, "Укажите ссылку на Google Таблицу"

        def mutate(data: dict) -> None:
            data["google_sheets_url"] = url

        await self._update(mutate)
        return True, "Ссылка сохранена" if url else "Ссылка удалена"

    async def format_status(self) -> str:
        data = await self.get_raw()
        keywords = data.get("keywords", [])
        chats = data.get("chats", [])
        interval_sec = data.get("monitor", {}).get("poll_interval", 300)
        google_url = data.get("google_sheets_url", "")

        lines = [
            "<b>Текущие настройки</b>",
            "",
            f"<b>Keywords ({len(keywords)}):</b>",
        ]
        if keywords:
            lines.extend(f"  {i}. {k}" for i, k in enumerate(keywords, 1))
        else:
            lines.append("  — пусто")
        lines += ["", f"<b>Чаты ({len(chats)}):</b>"]
        if chats:
            lines.extend(f"  {i}. {c}" for i, c in enumerate(chats, 1))
        else:
            lines.append("  — пусто")
        lines += [
            "",
            f"<b>Интервал проверки:</b> {interval_sec // 60} мин.",
            f"<b>Google Таблица:</b> {google_url or '— не задана'}",
            "",
            "<i>Листы настроек: Keywords, Чаты</i>",
        ]
        return "\n".join(lines)
