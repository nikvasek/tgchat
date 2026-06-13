from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def bootstrap_runtime() -> None:
    _write_google_credentials()
    _ensure_config_yaml()


def _write_google_credentials() -> None:
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if not raw:
        return

    target = Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("GOOGLE_CREDENTIALS_JSON содержит невалидный JSON") from error

    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("credentials.json создан из переменной окружения")


def _ensure_config_yaml() -> None:
    config_path = Path(os.getenv("CONFIG_PATH", "config.yaml"))
    if config_path.exists():
        return

    example = Path("config.example.yaml")
    if example.exists():
        shutil.copy(example, config_path)
        logger.info("config.yaml создан из config.example.yaml")
        return

    config_path.write_text(
        "google_sheets_url: ''\nkeywords: []\nchats: []\n"
        "monitor:\n  messages_limit: 500\n  poll_interval: 300\n"
        "global_search:\n  limit_per_keyword: 100\n",
        encoding="utf-8",
    )
    logger.info("config.yaml создан с настройками по умолчанию")
