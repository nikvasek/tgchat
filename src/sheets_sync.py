from __future__ import annotations

import logging

from .google_client import open_spreadsheet

logger = logging.getLogger(__name__)

SHEET_KEYWORDS = "Keywords"
SHEET_CHATS = "Чаты"
KEYWORD_HEADER = "Ключевое слово"
CHAT_HEADER = "Чат / канал"


def _clean_rows(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        result.append(item)
    return result


def lists_equal(left: list[str], right: list[str]) -> bool:
    return _clean_rows(left) == _clean_rows(right)


class SheetsConfigSync:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self._spreadsheet = open_spreadsheet(credentials_file, spreadsheet_id)

    def _get_or_create_sheet(self, title: str, header: str):
        try:
            worksheet = self._spreadsheet.worksheet(title)
        except Exception:
            worksheet = self._spreadsheet.add_worksheet(title=title, rows=200, cols=1)
            worksheet.append_row([header])
            return worksheet

        rows = worksheet.get_all_values()
        if not rows:
            worksheet.append_row([header])
        elif rows[0][0].strip() != header:
            worksheet.update("A1", [[header]])
        return worksheet

    def _read_column(self, sheet_title: str, header: str) -> list[str]:
        worksheet = self._get_or_create_sheet(sheet_title, header)
        rows = worksheet.get_all_values()
        if len(rows) <= 1:
            return []
        return _clean_rows(row[0] for row in rows[1:] if row and row[0].strip())

    def _write_column(self, sheet_title: str, header: str, values: list[str]) -> None:
        worksheet = self._get_or_create_sheet(sheet_title, header)
        cleaned = _clean_rows(values)
        worksheet.clear()
        worksheet.append_row([header])
        if cleaned:
            worksheet.append_rows([[value] for value in cleaned], value_input_option="USER_ENTERED")

    def read_settings(self) -> tuple[list[str], list[str]]:
        keywords = self._read_column(SHEET_KEYWORDS, KEYWORD_HEADER)
        chats = self._read_column(SHEET_CHATS, CHAT_HEADER)
        return keywords, chats

    def write_settings(self, keywords: list[str], chats: list[str]) -> None:
        self._write_column(SHEET_KEYWORDS, KEYWORD_HEADER, keywords)
        self._write_column(SHEET_CHATS, CHAT_HEADER, chats)
        logger.info(
            "Настройки отправлены в Google: %s keywords, %s чатов",
            len(_clean_rows(keywords)),
            len(_clean_rows(chats)),
        )
