#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from telethon import TelegramClient

from src.bootstrap import bootstrap_runtime
from src.bot_app import BotApp
from src.chat_monitor import ChatMonitor
from src.config import load_config, load_env
from src.config_store import ConfigStore
from src.pipe_buffer import PipeBuffer
from src.sync_factory import create_sheets_sync
from src.global_search import GlobalSearcher
from src.exporter import create_exporter
from src.scheduler import MonitorScheduler
from src.telegram_client import create_telegram_client
from src.webhook_pipe import WebhookPipe


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_monitor(args) -> None:
    env = load_env()
    app_config = load_config(args.config)
    exporter = create_exporter(env, app_config)

    async with create_telegram_client(env) as client:
        monitor = ChatMonitor(client, app_config, env, exporter)

        if args.mode == "scan":
            await monitor.scan_once()
            return

        await monitor.scan_once()
        await monitor.watch()


async def run_bot(args) -> None:
    from aiogram import Bot

    env = load_env()
    if not env.bot_token:
        raise ValueError("Укажите TELEGRAM_BOT_TOKEN в .env")
    if not env.admin_ids:
        raise ValueError("Укажите BOT_ADMIN_IDS в .env (для уведомлений админу)")

    app_config = load_config(args.config)
    sheets_sync = create_sheets_sync(env, app_config)
    store = ConfigStore(args.config, sheets_sync=sheets_sync)
    await store.initial_sync()

    async with create_telegram_client(env) as client:
        bot = Bot(token=env.bot_token)
        scheduler = MonitorScheduler(client=client, store=store, env=env, bot=bot)
        scheduler.start()

        pipe = None
        if env.database_url:
            buffer = PipeBuffer(env.database_url)
            pipe = WebhookPipe(client=client, store=store, buffer=buffer)
            await pipe.start()
        else:
            logging.getLogger(__name__).warning(
                "DATABASE_URL не задан — ТРУБА (webhook) отключена"
            )

        app = BotApp(env, store, client, scheduler, bot=bot)
        try:
            await app.run()
        finally:
            scheduler.stop()
            if pipe:
                await pipe.stop()


async def run_global(args) -> None:
    env = load_env()
    app_config = load_config(args.config)
    exporter = create_exporter(env, app_config)

    async with create_telegram_client(env) as client:
        searcher = GlobalSearcher(client, app_config, env, exporter)
        await searcher.search_once()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Парсер Telegram: мониторинг чатов и глобальный поиск → Excel",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Путь к config.yaml (по умолчанию: config.yaml)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Подробные логи")

    subparsers = parser.add_subparsers(dest="command", required=True)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Мониторинг ваших чатов/каналов по ключевым словам",
    )
    monitor_parser.add_argument(
        "mode",
        choices=["scan", "watch"],
        help="scan — однократная проверка, watch — непрерывный мониторинг новых сообщений",
    )

    subparsers.add_parser(
        "global",
        help="Глобальный поиск по открытому Telegram (публичные каналы/чаты)",
    )

    subparsers.add_parser(
        "bot",
        help="Telegram-бот для управления настройками и автопроверки",
    )

    return parser


def main() -> int:
    bootstrap_runtime()
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        if args.command == "monitor":
            asyncio.run(run_monitor(args))
        elif args.command == "global":
            asyncio.run(run_global(args))
        elif args.command == "bot":
            asyncio.run(run_bot(args))
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Остановлено пользователем")
        return 0
    except Exception as error:
        logging.getLogger(__name__).error("%s", error)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
