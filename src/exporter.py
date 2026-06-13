from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Protocol

from .config import AppConfig, EnvConfig
from .excel_exporter import ExcelExporter
from .messages import FoundMessage
from .sheets_exporter import SheetsExporter

logger = logging.getLogger(__name__)


class MessageExporter(Protocol):
    def append_messages(self, sheet_title: str, messages: list[FoundMessage]) -> int: ...


def extract_spreadsheet_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    if not value:
        return ""
    if re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        return value
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", value)
    if match:
        return match.group(1)
    raise ValueError(f"Некорректная ссылка Google Таблицы: {url_or_id}")


class CombinedExporter:
    def __init__(self, backends: list[MessageExporter]):
        if not backends:
            raise ValueError("Нет доступных экспортёров")
        self._backends = backends

    def append_messages(self, sheet_title: str, messages: list[FoundMessage]) -> int:
        if not messages:
            return 0

        added = 0
        for index, backend in enumerate(self._backends):
            try:
                added = max(added, backend.append_messages(sheet_title, messages))
            except Exception as error:
                if index == 0:
                    raise
                logger.warning(
                    "Резервный экспорт не удался (%s): %s",
                    type(backend).__name__,
                    error,
                )
        return added


def create_exporter(env: EnvConfig, app_config: AppConfig | None = None) -> CombinedExporter:
    backends: list[MessageExporter] = []

    spreadsheet_id = env.google_spreadsheet_id
    if not spreadsheet_id and app_config and app_config.google_sheets_url:
        spreadsheet_id = extract_spreadsheet_id(app_config.google_sheets_url)

    if spreadsheet_id:
        creds_path = Path(env.google_credentials_file)
        if creds_path.exists():
            try:
                backends.append(SheetsExporter(str(creds_path), spreadsheet_id))
                logger.info("Экспорт в Google Таблицу: %s", spreadsheet_id)
            except Exception as error:
                logger.error("Google Sheets недоступен: %s. Данные пойдут в Excel.", error)
        else:
            logger.warning(
                "Файл %s не найден. Данные только в Excel. "
                "Таблица: https://docs.google.com/spreadsheets/d/%s/edit",
                creds_path,
                spreadsheet_id,
            )
    else:
        logger.warning("Google Таблица не настроена, данные только в Excel")

    backends.append(ExcelExporter(env.excel_output_file))
    return CombinedExporter(backends)
