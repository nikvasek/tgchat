from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from telethon import TelegramClient

from .chat_monitor import ChatMonitor
from .config import EnvConfig
from .config_store import ConfigStore
from .exporter import create_exporter

logger = logging.getLogger(__name__)


class MonitorScheduler:
    CONFIG_SYNC_INTERVAL = 60

    def __init__(
        self,
        client: TelegramClient,
        store: ConfigStore,
        env: EnvConfig,
        bot: Bot | None = None,
    ):
        self.client = client
        self.store = store
        self.env = env
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None
        self._running = False

    async def _notify_admins(self, text: str) -> None:
        if not self.bot or not self.env.admin_ids:
            return
        for admin_id in self.env.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception as error:
                logger.warning("Не удалось отправить уведомление %s: %s", admin_id, error)

    async def _config_sync_loop(self) -> None:
        while self._running:
            try:
                changed, message = await self.store.sync_from_google()
                if changed:
                    await self._notify_admins(
                        f"Настройки обновлены из Google Таблицы.\n{message}"
                    )
            except Exception as error:
                logger.warning("Ошибка синхронизации настроек: %s", error)
            await asyncio.sleep(self.CONFIG_SYNC_INTERVAL)

    async def run_monitor(self) -> int:
        await self.store.sync_from_google()
        app_config = await self.store.load()
        exporter = create_exporter(self.env, app_config)
        monitor = ChatMonitor(self.client, app_config, self.env, exporter)
        monitor.reset_cache()
        return await monitor.scan_once()

    async def _loop(self) -> None:
        while self._running:
            if not await self.store.is_scanning_enabled():
                await asyncio.sleep(5)
                continue

            app_config = await self.store.load()
            interval = max(app_config.monitor.poll_interval, 60)

            try:
                monitor_added = await self.run_monitor()
                if monitor_added:
                    app_config = await self.store.load()
                    google_url = app_config.google_sheets_url or (
                        f"https://docs.google.com/spreadsheets/d/{self.env.google_spreadsheet_id}/edit"
                        if self.env.google_spreadsheet_id
                        else ""
                    )
                    text = f"Проверка завершена.\nМониторинг: +{monitor_added}"
                    if google_url:
                        text += f"\n\nGoogle Таблица:\n{google_url}"
                    await self._notify_admins(text)
            except Exception as error:
                logger.exception("Ошибка планировщика: %s", error)
                short_error = str(error).split("\n", maxsplit=1)[0]
                await self._notify_admins(f"Ошибка проверки: {short_error}")

            await asyncio.sleep(interval)

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._running = True
        self._sync_task = asyncio.create_task(self._config_sync_loop())
        self._task = asyncio.create_task(self._loop())
        return self._task

    def stop(self) -> None:
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
        if self._task:
            self._task.cancel()
