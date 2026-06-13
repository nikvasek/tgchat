from __future__ import annotations

from datetime import datetime

from .google_client import open_spreadsheet
from .messages import HEADERS, FoundMessage


class SheetsExporter:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self._spreadsheet = open_spreadsheet(credentials_file, spreadsheet_id)
        self._known_ids: dict[str, set[str]] = {}

    def _get_worksheet(self, title: str):
        try:
            return self._spreadsheet.worksheet(title)
        except Exception:
            worksheet = self._spreadsheet.add_worksheet(title=title, rows=1000, cols=len(HEADERS))
            worksheet.append_row(HEADERS)
            return worksheet

    def _load_existing_ids(self, sheet_title: str) -> set[str]:
        if sheet_title in self._known_ids:
            return self._known_ids[sheet_title]

        worksheet = self._get_worksheet(sheet_title)
        records = worksheet.get_all_values()

        ids: set[str] = set()
        if len(records) > 1:
            header = records[0]
            try:
                id_index = header.index("ID сообщения")
                source_index = header.index("Источник")
                chat_index = header.index("Username чата")
                title_index = header.index("Чат")
            except ValueError:
                id_index = len(HEADERS) - 1
                source_index = 1
                chat_index = 3
                title_index = 2

            for row in records[1:]:
                if len(row) <= id_index or not row[id_index]:
                    continue
                source = row[source_index] if len(row) > source_index else ""
                chat = row[chat_index] if len(row) > chat_index else ""
                if not chat and len(row) > title_index:
                    chat = row[title_index]
                ids.add(f"{source}:{chat}:{row[id_index]}")

        self._known_ids[sheet_title] = ids
        return ids

    def append_messages(self, sheet_title: str, messages: list[FoundMessage]) -> int:
        if not messages:
            return 0

        existing = self._load_existing_ids(sheet_title)
        worksheet = self._get_worksheet(sheet_title)

        rows: list[list[str]] = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for message in messages:
            if message.dedup_key in existing:
                continue
            rows.append(message.to_row(now))
            existing.add(message.dedup_key)

        if rows:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        self._known_ids[sheet_title] = existing
        return len(rows)
