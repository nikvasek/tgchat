from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class MonitorSettings:
    messages_limit: int = 500
    poll_interval: int = 300


@dataclass
class GlobalSearchSettings:
    limit_per_keyword: int = 100


@dataclass
class AppConfig:
    keywords: list[str]
    chats: list[str]
    monitor: MonitorSettings
    global_search: GlobalSearchSettings
    google_sheets_url: str = ""


@dataclass
class EnvConfig:
    api_id: int
    api_hash: str
    session_name: str
    session_string: str
    bot_token: str
    admin_ids: list[int]
    google_credentials_file: str
    google_spreadsheet_id: str
    excel_output_file: str
    sheet_monitor: str
    sheet_global: str


def load_env() -> EnvConfig:
    load_dotenv()

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    admin_raw = os.getenv("BOT_ADMIN_IDS", "")

    if not api_id or not api_hash:
        raise ValueError(
            "Укажите TELEGRAM_API_ID и TELEGRAM_API_HASH в .env "
            "(получить на https://my.telegram.org/apps)"
        )

    admin_ids = [int(item.strip()) for item in admin_raw.split(",") if item.strip().isdigit()]

    return EnvConfig(
        api_id=int(api_id),
        api_hash=api_hash,
        session_name=os.getenv("TELEGRAM_SESSION", "tgchat_session"),
        session_string=os.getenv("TELEGRAM_SESSION_STRING", "").strip(),
        bot_token=bot_token,
        admin_ids=admin_ids,
        google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        google_spreadsheet_id=os.getenv("GOOGLE_SPREADSHEET_ID", "").strip(),
        excel_output_file=os.getenv("EXCEL_OUTPUT_FILE", "results.xlsx"),
        sheet_monitor=os.getenv("SHEET_MONITOR", "Мониторинг чатов"),
        sheet_global=os.getenv("SHEET_GLOBAL", "Глобальный поиск"),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Файл конфигурации не найден: {config_path}. "
            "Скопируйте config.example.yaml в config.yaml"
        )

    with config_path.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    keywords = [str(k).strip() for k in raw.get("keywords", []) if str(k).strip()]
    chats = [str(c).strip() for c in raw.get("chats", []) if str(c).strip()]

    monitor_raw = raw.get("monitor", {})
    global_raw = raw.get("global_search", {})

    return AppConfig(
        keywords=keywords,
        chats=chats,
        monitor=MonitorSettings(
            messages_limit=int(monitor_raw.get("messages_limit", 500)),
            poll_interval=int(monitor_raw.get("poll_interval", 300)),
        ),
        global_search=GlobalSearchSettings(
            limit_per_keyword=int(global_raw.get("limit_per_keyword", 100)),
        ),
        google_sheets_url=str(raw.get("google_sheets_url", "")).strip(),
    )
