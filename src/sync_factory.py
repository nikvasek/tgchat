from __future__ import annotations

import logging
from pathlib import Path

from .config import AppConfig, EnvConfig
from .exporter import extract_spreadsheet_id
from .sheets_sync import SheetsConfigSync

logger = logging.getLogger(__name__)


def create_sheets_sync(
    env: EnvConfig,
    app_config: AppConfig | None = None,
) -> SheetsConfigSync | None:
    spreadsheet_id = env.google_spreadsheet_id
    if not spreadsheet_id and app_config and app_config.google_sheets_url:
        try:
            spreadsheet_id = extract_spreadsheet_id(app_config.google_sheets_url)
        except ValueError as error:
            logger.warning("%s", error)
            return None

    if not spreadsheet_id:
        return None

    creds_path = Path(env.google_credentials_file)
    if not creds_path.exists():
        logger.warning("credentials.json не найден — синхронизация настроек отключена")
        return None

    try:
        return SheetsConfigSync(str(creds_path), spreadsheet_id)
    except Exception as error:
        logger.warning("Не удалось подключить синхронизацию Google: %s", error)
        return None
